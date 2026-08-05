# PC MQTT Runner（事件名 -> BAT）说明（Windows）

一个小型 Windows 桌面工具：订阅 MQTT 的命令 Topic，根据收到的 payload（事件名）映射并执行本地 BAT 文件。常用于 Home Assistant 与 PC 的联动（例如米家中枢产生虚拟事件 -> HA 转发到 MQTT -> PC 执行对应的 BAT 来切换显示模式或触发 Quicker）。

> 注：本项目为 Windows 专用（使用 WinAPI 注册全局热键、以 cmd.exe 执行 BAT、支持无窗口运行等）。

---

## 主要特性

- 订阅指定 MQTT topic（默认 `ha/pc/cmd/display_mode`）。
- 将 payload（事件名）映射为本地 BAT 路径并触发执行（非阻塞）。
- GUI 管理映射表（增删改、双击编辑、Delete 删除）、保存到配置文件。
- 托盘运行，支持全局热键：
  - Ctrl+Alt+M：显示/隐藏窗口
  - Ctrl+Alt+Q：退出程序
- 日志：写入 `pc_mqtt_runner.log`，且在 GUI 中实时显示。
- 打包为单文件 exe（PyInstaller --onefile）时，配置文件与日志位于 exe 同目录，程序可直接运行。

---

## 要求（依赖）

- 操作系统：Windows（Windows 7/10/11 等）
- Python（开发/运行源码）：
  - 建议 Python 3.8+
  - 依赖包：
    - paho-mqtt
    - pystray
    - pillow
    - pyinstaller（仅用于打包）
  - tkinter（标准库，Windows Python 通常自带）
- 已打包为 exe 的二进制不需要安装 Python 环境

安装示例（开发环境）：
```bash
python -m venv .venv
.venv\Scripts\activate
pip install paho-mqtt pystray pillow pyinstaller
```

---

## 文件说明

- `pc_mqtt_core.py`：核心功能
  - 配置加载/保存（`pc_mqtt_config.json`，与 exe 同目录）
  - 日志（`pc_mqtt_runner.log`）
  - MQTT 客户端（paho-mqtt，Callback API v2）
  - 事件名 -> BAT 映射与执行（`run_bat`）
  - `MqttBatRunner` 提供 `start()` / `stop()` 接口供 GUI 控制
- `pc_mqtt_gui.py`：GUI（tkinter） + 托盘（pystray） + 全局热键（ctypes.WinDLL）
  - 映射表编辑、保存、启动/停止监听、日志显示等
- `version_info.txt`：用于 PyInstaller 的版本信息（可在打包时通过 `--version-file` 指定）
- `YAML_BACKUP.txt`：Home Assistant 自动化示例（如何把米家虚拟事件转发到 MQTT）
- `pc_mqtt_config.json`（运行时生成/读取）: 程序配置信息，见下方配置说明
- `pc_mqtt_runner.log`（运行时生成）: 程序日志，位于 exe/脚本同目录

---

## 配置说明（pc_mqtt_config.json）

程序在启动时会在 exe/脚本当前目录查找 `pc_mqtt_config.json`，并在 GUI 中编辑/保存。默认字段如下（示例）:

```json
{
  "broker": "192.168.1.25",
  "port": 1883,
  "username": "pc_subscriber",
  "password": "1qaz2wsx3edc",
  "topic_cmd": "ha/pc/cmd/display_mode",
  "client_id": "pc-quicker-runner-01",
  "keepalive": 60,
  "reconnect_min_delay": 1,
  "reconnect_max_delay": 30,
  "bat_dir": "F:\\\\Display Switch",
  "event_to_bat": {
    "pc_mode_study": "F:\\\\Display Switch\\\\Study_internal.bat",
    "pc_mode_livingroom": "F:\\\\Display Switch\\\\TV_external.bat"
  },
  "pop_cmd_window": false,
  "auto_start": true
}
```

字段说明：
- broker / port：MQTT Broker 的地址与端口
- username / password：MQTT 登录
- topic_cmd：订阅的 Topic（程序会在此 Topic 上等待 payload）
- client_id：MQTT 客户端 ID
- keepalive：keepalive 秒数
- reconnect_min_delay / reconnect_max_delay：paho-mqtt 的重连延迟区间
- bat_dir：默认 BAT 存放目录（界面引用）
- event_to_bat：事件名（小写）到 BAT 路径的映射（键会被视为小写）
- pop_cmd_window：是否在执行 BAT 时弹出 cmd 窗口（用于调试，默认 False）
- auto_start：启动 GUI 后是否自动开始监听

注意：
- GUI 在保存配置时会把事件名统一转换为小写；所以保证在 HA 发布的 payload 与配置中的 key 小写一致或 GUI 中也使用小写。
- 如果旧版本配置使用 `mode_to_bat` 字段，程序会自动迁移到 `event_to_bat`。

---

## 使用（运行与打包）

运行源码（开发/测试）：
```bash
# 在激活虚拟环境并安装依赖后：
python pc_mqtt_gui.py
```

已打包的 exe：
- 将 exe 放在任意目录（通常建议创建一个文件夹），第一次运行会在同目录生成/读取 `pc_mqtt_config.json` 与 `pc_mqtt_runner.log`。
- 建议把 BAT 文件放在独立目录（可在 GUI 中指定），并在映射表中使用绝对路径。

打包建议（使用 PyInstaller）：
- 常用命令示例（在项目根目录）：
```bash
pyinstaller --noconsole --onefile --windowed --version-file=version_info.txt pc_mqtt_gui.py
```
说明：
- `--onefile`：生成单文件 exe（程序会在临时目录解压运行）
- `--noconsole` / `--windowed`：不弹控制台窗口（适合桌面托盘程序）
- `--version-file=version_info.txt`：使用仓库中的版本信息（可选）
- 若需要包含额外文件（示例配置或图标），可以使用 `--add-data` 参数把这些文件复制到 exe 打包内或在发布包中一并放置（注意路径分隔和 platform 语法）。

打包常见注意：
- pystray 在 Windows 上通常正常工作，但有时需要额外的依赖或注意运行环境（例如打包后图标显示问题）。
- 若使用 `--onefile`，配置文件建议放在 exe 同目录（而不是打包到内部资源），方便用户编辑；因此发布时把 `pc_mqtt_config.json` 和 BAT 文件与 exe 同放在目录内，而不要把它们“嵌入”到 exe 内。

---

## Home Assistant 示例（来自 YAML_BACKUP.txt）
下面是一个简化示例，说明 HA 如何把“米家虚拟事件”映射并通过 MQTT 发布到 PC 的 topic：

```yaml
alias: 米家虚拟事件 -> PC 模式（MQTT）
trigger:
  - platform: state
    entity_id: event.xiaomi_cn_1179623348_hub1_virtual_event_e_4_1
action:
  - variables:
      mi_event_name: "{{ trigger.to_state.attributes['事件名称'] | default('') | trim }}"
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ mi_event_name == 'pc_mode_study' }}"
        sequence:
          - service: mqtt.publish
            data:
              topic: ha/pc/cmd/display_mode
              payload: "pc_mode_study"
              qos: 1
      - conditions:
          - condition: template
            value_template: "{{ mi_event_name == 'pc_mode_livingroom' }}"
        sequence:
          - service: mqtt.publish
            data:
              topic: ha/pc/cmd/display_mode
              payload: "pc_mode_livingroom"
              qos: 1
      # ... 更多分支
mode: single
```

关键点：
- HA 向 `ha/pc/cmd/display_mode` 发布的 payload 应为事件名（字符串）。PC 端使用小写 event_name 去匹配映射表并执行对应 BAT。

---

## 日志与调试

- 日志文件：`pc_mqtt_runner.log`（位于 exe/脚本同目录）
- GUI 日志窗口会实时显示日志内容（与文件同步）。
- 常见日志信息：
  - 已连接 / 已订阅 / 已断开（重连中）
  - 收到消息：topic=... payload=...
  - 收到未知事件名（未执行任何 BAT）
  - 执行 BAT 成功 / 失败（如果 BAT 不存在，会有错误）

---

## 常见问题（FAQ）

Q: 程序没有响应热键或热键注册失败？
A: 全局热键使用 Windows RegisterHotKey 实现，可能被其他程序占用或被组策略限制。日志会提示注册失败。可在托盘或 GUI 通过图形操作打开窗口并退出；若热键冲突，请选择其他热键或关闭占用程序。

Q: 收到 MQTT 消息但没有执行 BAT？
A: 请确认：
- payload 与映射表中的 key 完全一致（程序内部会把事件名转换为小写，请在 GUI 中用小写 key）；
- 映射中对应的 BAT 路径存在且可执行；
- 检查日志 `pc_mqtt_runner.log`，查看是否有“收到未知事件名”或“BAT 不存在”的提示。

Q: 打包后找不到配置文件或日志文件？
A: 如果使用 `--onefile`，程序会在运行目录（exe 所在目录）查找 `pc_mqtt_config.json` 和写入 `pc_mqtt_runner.log`。确保把配置文件与 exe 放在同一目录，或首次通过 GUI 保存配置以生成配置文件。

Q: 为什么程序弹出黑色 cmd 窗口？
A: 默认以不弹黑窗方式运行（CREATE_NO_WINDOW）。如果需要看到执行过程，可在 GUI 的“调试：执行 BAT 时弹出 cmd 窗口”选项勾选后保存并重新启动监听。

---

## 安全与注意事项

- 程序会直接执行您配置的 BAT 文件，请务必只在受信任的环境中使用并确保 BAT 内容安全。
- 不要把敏感凭据写入公开的配置或提交到版本控制（当前示例配置包含明文密码，仅作测试示例）。
- 如果将程序作为服务或放在开机自启中，确保以合适权限运行且配置路径可访问。

---

## 开发与贡献

欢迎提出 Issue 或 PR。若要开发/打包该程序，建议：
- 在虚拟环境中安装依赖并运行 `pc_mqtt_gui.py` 进行调试；
- 若修改打包行为，更新 `version_info.txt` 或提供适合的 PyInstaller spec 文件；
- 编写更完善的单元/集成测试（当前仓库未包含测试用例）。

---

## 许可（License）
仓库中未包含明确的 LICENSE 文件（截至编写时），请在发布之前补充适当许可证以明确信息和使用约束。

---

如果你希望，我可以：
- 把上面的内容直接替换到仓库根目录的 `README.md`（我可以生成并提交 PR 或创建/更新文件），
- 或者为该项目生成一个 PyInstaller spec 文件和/或 Windows 服务安装脚本（如果你要把它作为服务长期运行）。
