# -*- coding: utf-8 -*-
"""\
pc_mqtt_gui.py

GUI + 托盘 + 热键（方案 A）：
- HA 永远只发 mi_event_name 原文（例如 pc_mode_study）到 MQTT payload
- PC 映射表用事件名作为 key：event_name -> BAT
- 启动后默认隐藏到托盘，并自动开始监听
- 提供：停止监听 / 重新监听
- MQTT 参数、重连策略可编辑
- 映射表可增删改（两列；双击编辑；Delete 删除）
- 日志：文件 + GUI 实时显示
- 全局热键：Ctrl+Alt+M 显示/隐藏窗口；Ctrl+Alt+Q 退出
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

from pc_mqtt_core import (
    AppConfig, load_config, save_config, setup_logger,
    MqttBatRunner
)


# ---------------------------
# Win Hotkey
# ---------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
VK_M = 0x4D
VK_Q = 0x51

HOTKEY_ID_TOGGLE = 1
HOTKEY_ID_QUIT = 2


class GlobalHotkeyThread(threading.Thread):
    def __init__(self, on_toggle, on_quit, logger: logging.Logger):
        super().__init__(name="hotkey_thread", daemon=True)
        self.on_toggle = on_toggle
        self.on_quit = on_quit
        self.logger = logger
        self._stop_evt = threading.Event()
        self._tid = None

    def stop(self):
        self._stop_evt.set()
        if self._tid is not None:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    def run(self):
        self._tid = kernel32.GetCurrentThreadId()

        ok1 = user32.RegisterHotKey(None, HOTKEY_ID_TOGGLE, MOD_CONTROL | MOD_ALT, VK_M)
        ok2 = user32.RegisterHotKey(None, HOTKEY_ID_QUIT, MOD_CONTROL | MOD_ALT, VK_Q)

        if ok1:
            self.logger.info("已注册全局热键：Ctrl+Alt+M（显示/隐藏窗口）")
        else:
            self.logger.warning("注册全局热键 Ctrl+Alt+M 失败（可能被占用/被策略禁止）")

        if ok2:
            self.logger.info("已注册全局热键：Ctrl+Alt+Q（退出）")
        else:
            self.logger.warning("注册全局热键 Ctrl+Alt+Q 失败（可能被占用/被策略禁止）")

        msg = wt.MSG()
        while not self._stop_evt.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0:
                break
            if ret == -1:
                self.logger.error("GetMessageW 发生错误。")
                break

            if msg.message == WM_HOTKEY:
                hk_id = msg.wParam
                if hk_id == HOTKEY_ID_TOGGLE:
                    self.logger.info("收到热键 Ctrl+Alt+M：切换窗口显示/隐藏。")
                    try:
                        self.on_toggle()
                    except Exception:
                        pass
                elif hk_id == HOTKEY_ID_QUIT:
                    self.logger.info("收到热键 Ctrl+Alt+Q：退出。")
                    try:
                        self.on_quit()
                    except Exception:
                        pass

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, HOTKEY_ID_TOGGLE)
        user32.UnregisterHotKey(None, HOTKEY_ID_QUIT)
        self.logger.info("已注销全局热键。")


# ---------------------------
# Tk log handler
# ---------------------------

class TkTextHandler(logging.Handler):
    def __init__(self, text_widget: tk.Text):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.configure(state="disabled")

    def emit(self, record):
        msg = self.format(record)

        def append():
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg + "\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        try:
            self.text_widget.after(0, append)
        except Exception:
            pass


# ---------------------------
# Tray icon
# ---------------------------

def make_tray_image():
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, size - 4, size - 4), fill=(0, 120, 215, 255))
    d.text((12, 18), "PC", fill=(255, 255, 255, 255))
    return img


# ---------------------------
# GUI App
# ---------------------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PC MQTT Runner")
        self.root.geometry("980x720")

        self.logger = setup_logger("pc_mqtt_gui")
        self.cfg = load_config()

        self.status_var = tk.StringVar(value="未启动")
        self.runner = MqttBatRunner(self.cfg, self.logger, on_status=self._set_status)

        self._tray_icon = None
        self._tray_thread = None

        self._hotkey_thread = GlobalHotkeyThread(
            on_toggle=self.toggle_window,
            on_quit=self.exit_app,
            logger=self.logger
        )
        self._hotkey_thread.start()

        self._build_ui()
        self._install_logging_to_text()
        self.start_tray()

        # 关闭窗口不退出：隐藏到托盘
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        # 启动后默认隐藏到托盘
        self.root.after(0, self.hide_window)

        # 启动后自动开始监听
        if self.cfg.auto_start:
            self.root.after(200, self.start_listening)

        self.logger.info("GUI 已启动（默认隐藏到托盘）。Ctrl+Alt+M 显示/隐藏；Ctrl+Alt+Q 退出。")

    # ---------- UI ----------
    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)

        # MQTT 配置
        cfg_frame = ttk.LabelFrame(frm, text="MQTT / 重连配置", padding=10)
        cfg_frame.pack(fill="x")
        cfg_frame.columnconfigure(1, weight=1)
        cfg_frame.columnconfigure(3, weight=1)

        def grid_row(r, c, label, var, show=None):
            ttk.Label(cfg_frame, text=label, width=14).grid(row=r, column=c, sticky="w", padx=4, pady=3)
            ent = ttk.Entry(cfg_frame, textvariable=var, show=show) if show else ttk.Entry(cfg_frame, textvariable=var)
            ent.grid(row=r, column=c + 1, sticky="ew", padx=4, pady=3)
            return ent

        self.broker = tk.StringVar(value=self.cfg.broker)
        self.port = tk.StringVar(value=str(self.cfg.port))
        self.username = tk.StringVar(value=self.cfg.username)
        self.password = tk.StringVar(value=self.cfg.password)
        self.topic = tk.StringVar(value=self.cfg.topic_cmd)
        self.client_id = tk.StringVar(value=self.cfg.client_id)
        self.keepalive = tk.StringVar(value=str(self.cfg.keepalive))
        self.re_min = tk.StringVar(value=str(self.cfg.reconnect_min_delay))
        self.re_max = tk.StringVar(value=str(self.cfg.reconnect_max_delay))

        self.pop_cmd = tk.BooleanVar(value=self.cfg.pop_cmd_window)
        self.auto_start = tk.BooleanVar(value=self.cfg.auto_start)

        grid_row(0, 0, "Broker/IP", self.broker)
        grid_row(0, 2, "Port", self.port)
        grid_row(1, 0, "Username", self.username)
        grid_row(1, 2, "Password", self.password, show="*")
        grid_row(2, 0, "Topic", self.topic)
        grid_row(2, 2, "Client ID", self.client_id)
        grid_row(3, 0, "Keepalive", self.keepalive)
        grid_row(3, 2, "重连(min)", self.re_min)
        grid_row(4, 2, "重连(max)", self.re_max)

        ttk.Checkbutton(cfg_frame, text="调试：执行 BAT 时弹出 cmd 窗口", variable=self.pop_cmd).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=4, pady=3
        )
        ttk.Checkbutton(cfg_frame, text="启动后自动开始监听", variable=self.auto_start).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=4, pady=3
        )

        # 映射表
        map_frame = ttk.LabelFrame(frm, text="事件名(mi_event_name) → BAT 映射（双击可编辑；Delete 删除）", padding=10)
        map_frame.pack(fill="both", expand=False, pady=(10, 6))

        self.tree = ttk.Treeview(map_frame, columns=("event", "bat"), show="headings", height=8)
        self.tree.heading("event", text="事件名 / payload")
        self.tree.heading("bat", text="BAT 文件路径")
        self.tree.column("event", width=240, anchor="w")
        self.tree.column("bat", width=660, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        ysb = ttk.Scrollbar(map_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        ysb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._begin_edit_cell)
        self.tree.bind("<Delete>", lambda e: self.delete_selected_mapping())

        # 新增/更新
        edit_frame = ttk.Frame(frm)
        edit_frame.pack(fill="x", pady=(0, 8))
        edit_frame.columnconfigure(1, weight=1)
        edit_frame.columnconfigure(3, weight=1)

        ttk.Label(edit_frame, text="事件名", width=12).grid(row=0, column=0, sticky="w", padx=4, pady=3)
        self.new_event = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.new_event).grid(row=0, column=1, sticky="ew", padx=4, pady=3)

        ttk.Label(edit_frame, text="BAT 路径", width=12).grid(row=0, column=2, sticky="w", padx=4, pady=3)
        self.new_bat = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.new_bat).grid(row=0, column=3, sticky="ew", padx=4, pady=3)
        ttk.Button(edit_frame, text="浏览...", command=self.browse_bat_file).grid(row=0, column=4, padx=6)

        ttk.Button(edit_frame, text="添加/更新", command=self.add_or_update_mapping).grid(row=1, column=0, padx=4, pady=4, sticky="w")
        ttk.Button(edit_frame, text="删除选中", command=self.delete_selected_mapping).grid(row=1, column=1, padx=4, pady=4, sticky="w")
        ttk.Button(edit_frame, text="保存配置", command=self.save_cfg).grid(row=1, column=2, padx=4, pady=4, sticky="w")

        # 控制区
        ctrl = ttk.Frame(frm)
        ctrl.pack(fill="x", pady=(6, 6))
        ttk.Button(ctrl, text="停止监听", command=self.stop_listening).pack(side="left")
        ttk.Button(ctrl, text="重新监听", command=self.restart_listening).pack(side="left", padx=8)
        ttk.Button(ctrl, text="显示窗口", command=self.show_window).pack(side="left", padx=8)
        ttk.Button(ctrl, text="隐藏到托盘", command=self.hide_window).pack(side="right")

        status_frame = ttk.Frame(frm)
        status_frame.pack(fill="x")
        ttk.Label(status_frame, text="状态：").pack(side="left")
        ttk.Label(status_frame, textvariable=self.status_var, foreground="#0a66c2").pack(side="left")

        # 日志
        log_frame = ttk.LabelFrame(frm, text="日志（同时写入 pc_mqtt_runner.log）", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=18, wrap="none")
        self.log_text.pack(fill="both", expand=True)

        self._refresh_tree_from_cfg()

    def _install_logging_to_text(self):
        handler = TkTextHandler(self.log_text)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        self.logger.addHandler(handler)

    # ---------- Mapping ----------
    def _refresh_tree_from_cfg(self):
        self.tree.delete(*self.tree.get_children())
        mapping = (self.cfg.event_to_bat or {})
        for k in sorted(mapping.keys()):
            self.tree.insert("", "end", values=(k, mapping[k]))

    def browse_bat_file(self):
        p = filedialog.askopenfilename(
            title="选择 BAT 文件",
            filetypes=[("BAT files", "*.bat"), ("All files", "*.*")]
        )
        if p:
            self.new_bat.set(p)

    def add_or_update_mapping(self):
        event_name = (self.new_event.get() or "").strip()
        bat = (self.new_bat.get() or "").strip()
        if not event_name:
            messagebox.showwarning("提示", "事件名不能为空")
            return
        if not bat:
            messagebox.showwarning("提示", "BAT 路径不能为空")
            return

        if not self.cfg.event_to_bat:
            self.cfg.event_to_bat = {}
        self.cfg.event_to_bat[event_name.lower()] = bat

        self._refresh_tree_from_cfg()
        self.new_event.set("")
        self.new_bat.set("")
        self.logger.info("映射已添加/更新：%s -> %s", event_name.lower(), bat)

    def delete_selected_mapping(self):
        sel = self.tree.selection()
        if not sel:
            return
        for iid in sel:
            event_name = self.tree.item(iid, "values")[0]
            if self.cfg.event_to_bat and event_name in self.cfg.event_to_bat:
                del self.cfg.event_to_bat[event_name]
                self.logger.info("映射已删除：%s", event_name)
        self._refresh_tree_from_cfg()

    def _begin_edit_cell(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)  # '#1' event, '#2' bat
        if not row_id or col not in ("#1", "#2"):
            return

        x, y, w, h = self.tree.bbox(row_id, col)
        old_values = list(self.tree.item(row_id, "values"))
        col_index = 0 if col == "#1" else 1
        old_text = old_values[col_index]

        entry = ttk.Entry(self.tree)
        entry.insert(0, old_text)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()

        def commit(_=None):
            new_text = entry.get().strip()
            entry.destroy()

            event_name = old_values[0]
            bat = old_values[1]

            if col_index == 0:
                new_event = new_text.lower()
                if not new_event:
                    return
                if not self.cfg.event_to_bat:
                    self.cfg.event_to_bat = {}
                if event_name in self.cfg.event_to_bat:
                    val = self.cfg.event_to_bat[event_name]
                    del self.cfg.event_to_bat[event_name]
                else:
                    val = bat
                self.cfg.event_to_bat[new_event] = val
                self.logger.info("事件名已编辑：%s -> %s", event_name, new_event)
            else:
                if not new_text:
                    return
                if not self.cfg.event_to_bat:
                    self.cfg.event_to_bat = {}
                self.cfg.event_to_bat[event_name] = new_text
                self.logger.info("BAT 路径已编辑：%s -> %s", event_name, new_text)

            self._refresh_tree_from_cfg()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)

    # ---------- Config ----------
    def _collect_cfg(self) -> AppConfig:
        mapping = {}
        if self.cfg.event_to_bat:
            for k, v in self.cfg.event_to_bat.items():
                kk = (k or "").strip().lower()
                vv = (v or "").strip()
                if kk and vv:
                    mapping[kk] = vv

        cfg = AppConfig(
            broker=self.broker.get().strip(),
            port=int(self.port.get()),
            username=self.username.get().strip(),
            password=self.password.get(),
            topic_cmd=self.topic.get().strip(),
            client_id=self.client_id.get().strip(),
            keepalive=int(self.keepalive.get()),
            reconnect_min_delay=int(self.re_min.get()),
            reconnect_max_delay=int(self.re_max.get()),
            bat_dir=self.cfg.bat_dir,
            event_to_bat=mapping,
            pop_cmd_window=bool(self.pop_cmd.get()),
            auto_start=bool(self.auto_start.get()),
        ).normalized()
        return cfg

    def save_cfg(self):
        try:
            self.cfg = self._collect_cfg()
            save_config(self.cfg)
            self.logger.info("配置已保存：pc_mqtt_config.json")
            messagebox.showinfo("保存成功", "配置已保存到 pc_mqtt_config.json（位于 exe 同目录）")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    # ---------- Listening control ----------
    def start_listening(self):
        try:
            self.cfg = self._collect_cfg()
            save_config(self.cfg)
            self.runner.stop()
            self.runner = MqttBatRunner(self.cfg, self.logger, on_status=self._set_status)
            self.runner.start()
            self.logger.info("监听已启动。")
        except Exception as e:
            self.logger.exception("启动监听失败：%s", str(e))

    def stop_listening(self):
        try:
            self.runner.stop()
        except Exception:
            pass

    def restart_listening(self):
        try:
            self.stop_listening()
            self.root.after(250, self.start_listening)
        except Exception:
            pass

    def _set_status(self, text: str):
        self.status_var.set(text)

    # ---------- Window / Tray ----------
    def show_window(self):
        def _do():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        self.root.after(0, _do)

    def hide_window(self):
        self.root.after(0, self.root.withdraw)

    def toggle_window(self):
        if self.root.state() == "withdrawn":
            self.show_window()
        else:
            self.hide_window()

    def start_tray(self):
        if self._tray_icon is not None:
            return
        menu = pystray.Menu(
            item("显示窗口 (Ctrl+Alt+M)", lambda icon, it: self.show_window(), default=True),
            item("隐藏窗口", lambda icon, it: self.hide_window()),
            item("停止监听", lambda icon, it: self.stop_listening()),
            item("重新监听", lambda icon, it: self.restart_listening()),
            item("退出 (Ctrl+Alt+Q)", lambda icon, it: self.exit_app()),
        )
        self._tray_icon = pystray.Icon(
            "pc_mqtt_runner",
            make_tray_image(),
            "PC MQTT Runner",
            menu=menu,
        )

        def run_tray():
            self.logger.info("托盘图标已启动（可能在右下角“∧”折叠区）。")
            self._tray_icon.run()

        self._tray_thread = threading.Thread(target=run_tray, name="tray_thread", daemon=True)
        self._tray_thread.start()

    def exit_app(self):
        try:
            self.logger.info("收到退出请求，正在清理资源...")
            try:
                self.stop_listening()
            except Exception:
                pass
            try:
                self._hotkey_thread.stop()
            except Exception:
                pass
            try:
                if self._tray_icon:
                    self._tray_icon.stop()
            except Exception:
                pass
            self.root.after(0, self.root.destroy)
        finally:
            pass


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
