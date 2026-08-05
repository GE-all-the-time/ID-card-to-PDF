# -*- coding: utf-8 -*-
"""\
pc_mqtt_core.py

核心功能（适配 PyInstaller --onefile）：
- 配置加载/保存（pc_mqtt_config.json，位于 exe 同目录）
- Rotating 日志（pc_mqtt_runner.log，位于 exe 同目录）
- MQTT 订阅（paho-mqtt Callback API v2）
- 事件名(payload) -> BAT 映射，触发 cmd.exe /c bat（默认无黑窗）
- Runner.start()/stop() 供 GUI 控制

方案 A：HA 只发送 mi_event_name 原文（例如 pc_mode_study），PC 映射表用该事件名作为 key。
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion


# ---------------------------
# 路径（兼容 PyInstaller --onefile）
# ---------------------------

def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def app_dir() -> Path:
    """EXE: 返回 exe 所在目录；源码运行：返回脚本所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# ---------------------------
# 配置
# ---------------------------

DEFAULT_BAT_DIR = r"F:\\Display Switch"

# 方案 A：默认 key 使用米家事件名（暗号）
DEFAULT_EVENT_TO_BAT = {
    "pc_mode_study": str(Path(DEFAULT_BAT_DIR) / "Study_internal.bat"),
    "pc_mode_livingroom": str(Path(DEFAULT_BAT_DIR) / "TV_external.bat"),
    "pc_mode_livingroom_game": str(Path(DEFAULT_BAT_DIR) / "TV_Gaming_external.bat"),
}


@dataclass
class AppConfig:
    # MQTT
    broker: str = "192.168.1.25"
    port: int = 1883
    username: str = "pc_subscriber"
    password: str = "1qaz2wsx3edc"
    topic_cmd: str = "ha/pc/cmd/display_mode"
    client_id: str = "pc-quicker-runner-01"
    keepalive: int = 60

    # 重连策略
    reconnect_min_delay: int = 1
    reconnect_max_delay: int = 30

    # BAT
    bat_dir: str = DEFAULT_BAT_DIR
    event_to_bat: dict | None = None  # {"pc_mode_xxx": "C:\\...\\x.bat"}

    # 行为
    pop_cmd_window: bool = False  # True: 调试弹 cmd 窗口

    # GUI 行为
    auto_start: bool = True  # 启动后自动监听

    def normalized(self) -> "AppConfig":
        if not self.event_to_bat:
            self.event_to_bat = dict(DEFAULT_EVENT_TO_BAT)
        return self


def config_path() -> Path:
    return app_dir() / "pc_mqtt_config.json"


def _migrate_legacy_keys(data: dict) -> dict:
    """兼容旧字段 mode_to_bat（上一版），自动迁移为 event_to_bat。"""
    if isinstance(data, dict) and "mode_to_bat" in data and "event_to_bat" not in data:
        data["event_to_bat"] = data.pop("mode_to_bat")
    return data


def load_config() -> AppConfig:
    p = config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data = _migrate_legacy_keys(data)
            return AppConfig(**data).normalized()
        except Exception:
            return AppConfig().normalized()
    return AppConfig().normalized()


def save_config(cfg: AppConfig) -> None:
    p = config_path()
    p.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------
# 日志
# ---------------------------

def setup_logger(name: str = "pc_mqtt_runner") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    log_file = app_dir() / "pc_mqtt_runner.log"
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if not logger.handlers:
        fh = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        fh.setLevel(logging.INFO)

        sh = logging.StreamHandler(sys.stdout)  # --noconsole 时不会显示，但无副作用
        sh.setFormatter(fmt)
        sh.setLevel(logging.INFO)

        logger.addHandler(fh)
        logger.addHandler(sh)
        logger.info("日志初始化完成：%s", str(log_file))

    return logger


# ---------------------------
# BAT 执行
# ---------------------------

def _creation_flags(pop_cmd_window: bool) -> int:
    if pop_cmd_window:
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_bat(bat_path: Path, logger: logging.Logger, pop_cmd_window: bool = False) -> bool:
    """运行 bat（非阻塞），默认不弹黑窗；cwd 设为 bat 所在目录。"""
    try:
        bat_path = Path(bat_path)
        if not bat_path.exists():
            logger.error("BAT 不存在：%s", str(bat_path))
            return False

        logger.info("准备运行 BAT：%s", str(bat_path))
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            cwd=str(bat_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creation_flags(pop_cmd_window),
        )
        logger.info("已触发 BAT：%s", bat_path.name)
        return True
    except Exception as e:
        logger.exception("运行 BAT 失败：%s，错误：%s", str(bat_path), str(e))
        return False


# ---------------------------
# MQTT Runner（可 start/stop）
# ---------------------------

class MqttBatRunner:
    def __init__(self, cfg: AppConfig, logger: logging.Logger, on_status=None) -> None:
        self.cfg = cfg.normalized()
        self.logger = logger
        self.on_status = on_status  # GUI 回调
        self._client: mqtt.Client | None = None
        self._running = threading.Event()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def _emit_status(self, text: str) -> None:
        if callable(self.on_status):
            try:
                self.on_status(text)
            except Exception:
                pass

    # --- callbacks v2 ---
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.logger.info("MQTT 已连接（rc=%s）。订阅 Topic：%s", reason_code, self.cfg.topic_cmd)
        client.subscribe(self.cfg.topic_cmd, qos=1)
        self.logger.info("✅ 已订阅命令 Topic，等待事件名 payload ...")
        self._emit_status("已连接 & 已订阅")

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        event_name = payload.lower()
        self.logger.info("收到消息：topic=%s payload=%s", msg.topic, payload)
        self.run_event(event_name)

    def _on_disconnect(self, client, userdata, reason_code, properties):
        self.logger.warning("MQTT 已断开（rc=%s）。将按重连策略自动重连。", reason_code)
        self._emit_status("已断开，重连中...")

    def run_event(self, event_name: str) -> None:
        event_name = (event_name or "").strip().lower()
        mapping = self.cfg.event_to_bat or {}
        bat = mapping.get(event_name)
        if not bat:
            self.logger.warning("收到未知事件名：%s（未执行任何 BAT）", event_name)
            return
        self.logger.info("执行 event=%s -> %s", event_name, bat)
        run_bat(Path(bat), self.logger, pop_cmd_window=self.cfg.pop_cmd_window)

    def start(self) -> None:
        with self._lock:
            if self._running.is_set():
                return
            self._running.set()

            self._client = mqtt.Client(
                client_id=self.cfg.client_id,
                callback_api_version=CallbackAPIVersion.VERSION2
            )
            self._client.username_pw_set(self.cfg.username, self.cfg.password)
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect

            self._client.reconnect_delay_set(
                min_delay=int(self.cfg.reconnect_min_delay),
                max_delay=int(self.cfg.reconnect_max_delay),
            )

            self.logger.info(
                "启动监听：mqtt://%s:%s user=%s keepalive=%s 重连延迟=%s~%s",
                self.cfg.broker, self.cfg.port, self.cfg.username,
                self.cfg.keepalive, self.cfg.reconnect_min_delay, self.cfg.reconnect_max_delay
            )
            self._emit_status("连接中...")

            self._client.connect_async(self.cfg.broker, int(self.cfg.port), keepalive=int(self.cfg.keepalive))
            self._client.loop_start()

    def stop(self) -> None:
        with self._lock:
            if not self._running.is_set():
                return
            self._running.clear()

            try:
                if self._client:
                    self.logger.info("停止监听：正在停止 MQTT ...")
                    self._client.disconnect()
                    self._client.loop_stop()
            except Exception:
                pass
            finally:
                self._client = None
                self._emit_status("已停止监听")
                self.logger.info("已停止监听。")
