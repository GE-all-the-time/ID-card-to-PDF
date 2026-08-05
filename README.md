# little_tool

一个收集“单文件 Python 小工具”的仓库 —— 每个工具尽量做小、单一、可直接运行或打包成 exe，便于快速复用、分享与学习。

本仓库当前包含三个主要工具目录：
- ID_to_PDF：带 GUI 的图片（或身份证/证件）批量处理与导出 PDF 工具。
- movie_sorter：用于扫描影视库、统计子文件夹体积并按体积排序的 GUI 工具。
- pc_mqtt：Windows 专用的 MQTT 事件 -> 本地 BAT 映射执行器（带 GUI、托盘、全局热键），常用于 Home Assistant 与 PC 联动。

---

## 目录结构（简要）
```text
ID_to_PDF/         # 图像 -> PDF，带预览、裁切、DPI/尺寸调整、导出 PDF（含用于打包的 PowerShell 脚本）
  ├─ core.py       # 主脚本：Tkinter GUI + 图像处理（Pillow / OpenCV / numpy / reportlab 等）
  └─ package.ps1   # Windows 下使用 PyInstaller 打包的示例脚本

movie_sorter/      # 影视文件夹体积扫描与排序工具（GUI）
  ├─ movie_sorter_gui.py  # 主脚本：Tkinter GUI，实现目录选择、递归计算大小、导出排序 TXT
  └─ dist_exe.rar  # （已打包的 exe 的归档，供参考）

pc_mqtt/           # Windows 专用：订阅 MQTT 事件并映射执行本地 BAT（带 GUI、托盘、全局热键）
  ├─ pc_mqtt_gui.py   # GUI + 托盘 + 全局热键
  ├─ pc_mqtt_core.py  # MQTT 客户端与事件 -> BAT 执行核心逻辑
  ├─ pc_mqtt_config.json (运行时生成) # 配置示例存放位置
  └─ version_info.txt  # PyInstaller 版本信息（打包时使用）
```

---

## 公共信息 / 技术栈
- 语言：Python（主），PowerShell（用于打包脚本）
- 运行时：CPython 3.x（建议 3.8+）
- GUI：Tkinter（跨平台，Windows/macOS/Linux 均可运行，但打包/兼容性以 Windows 为主）
- 常见第三方库（仓内脚本使用到）：
  - Pillow (PIL) —— 图像读取/保存/缩放/旋转/合成
  - OpenCV (cv2) —— 高级图像处理（检测、透视变换等）
  - numpy —— 数组与数值处理（图像数组运算）
  - reportlab —— 生成 PDF（可合并图像到 PDF）
  - paho-mqtt / pystray / pillow —— pc_mqtt 的运行时依赖（详见 pc_mqtt/README.md）
  - 其它：tkinter（标准库 GUI），tkinter.ttk（主题控件）

注意：各工具的具体依赖会在各自目录的 README 中列出，安装前请参考对应目录说明。

---

## 已有小工具详述

### 1) ID_to_PDF（路径：ID_to_PDF/）
功能亮点：
- 带图形界面（Tkinter），支持选择多张图片进行处理与导出 PDF。
- 支持常见图片格式（jpg, jpeg, png, bmp, webp 等），可设置导出 DPI / 页面尺寸 / 排版方式。
- 包含图像预处理功能：缩放、旋转、裁切、自动/手动检测证件卡片角点并做透视校正（适合身份证类证件拍照转换）。
- 可在界面预览效果，支持单页或合并多页输出为 PDF。
- 提供打包脚本（package.ps1）示例用于在 Windows 下用 PyInstaller 生成 exe。

运行（开发/调试）：
```bash
# 进入仓库后：
python3 ID_to_PDF/core.py
# 或在 Windows 上用 double-click 运行 core.py（若系统已关联 .py）
```

主要文件：
- core.py：主 GUI 与图像处理逻辑（入口点在文件末尾有 if __name__ == "__main__"），对 Pillow、cv2、numpy、reportlab 有调用。
- package.ps1：PowerShell 打包示例，基于 PyInstaller（请按需修改规格与图标等）。

常见依赖安装示例：
```bash
pip install pillow opencv-python numpy reportlab
# tkinter 通常为 Python 自带（系统包），Windows/Mac 通常已包含；Linux 可能需额外安装系统包（如 apt install python3-tk）
```

注意与提示：
- 大图/高分辨率图片处理时会占用较多内存和 CPU，建议在内存允许的机器上操作或先缩小图片。
- 若要生成适用于不同纸张尺寸的 PDF，请在导出时调整页面尺寸与 DPI。

---

### 2) movie_sorter（路径：movie_sorter/）
功能亮点：
- GUI 工具，选择影视库根目录后会扫描每个一级子文件夹（认为每个子文件夹为一个影片或分组），递归统计子文件夹总字节数。
- 计算完成后按体积从大到小排序并生成一个文本报告（默认保存到程序所在目录，文件名如 `电影文件夹体积排序.txt`）。
- 采用后台线程扫描（避免网络盘或大目录扫描时阻塞 GUI），有进度条与提示。
- 简洁易用，适合快速找出占用磁盘空间的影视目录。

运行：
```bash
python3 movie_sorter/movie_sorter_gui.py
```

运行后操作：
1. 点击“浏览...”选择影视库根目录（包含多个影片子文件夹）。
2. 点击“开始扫描并排序”开启后台计算。
3. 扫描完成后会在程序目录生成 TXT 报告，并可通过 “打开排序 TXT” 按钮直接打开。

注意：
- 对于包含大量小文件或网络挂载（NAS）的路径，扫描耗时较长，请耐心等待。
- movie_sorter 代码中使用了 os.scandir / pathlib 等高效遍历方法，但仍需注意权限与文件系统错误（脚本已对常见异常做了容错处理）。

仓内资源：
- movie_sorter/movie_sorter_gui.py：主程序。
- movie_sorter/dist_exe.rar：已打包生成的 exe（归档），如果你需要直接运行 exe 可解压查看。

---

### 3) pc_mqtt（路径：pc_mqtt/）
功能亮点：
- Windows 专用工具：订阅指定 MQTT Topic，根据收到的 payload（事件名）映射并执行本地 BAT 文件，常用于 Home Assistant 与 PC 的联动场景。
- 带 GUI（映射表管理）、托盘运行与全局热键（例如 Ctrl+Alt+M 显示/隐藏，Ctrl+Alt+Q 退出）。
- 配置文件（pc_mqtt_config.json）在 exe/脚本同目录生成/读取，日志（pc_mqtt_runner.log）可在 GUI 中实时查看。
- 支持将配置与映射表保存在本地，常用打包为单文件 exe（PyInstaller --onefile）。

运行（开发/调试）：
```bash
python pc_mqtt/pc_mqtt_gui.py
```

常见依赖安装示例：
```bash
pip install paho-mqtt pystray pillow
```

运行注意：
- 该工具为 Windows 专用（使用 WinAPI 注册全局热键、以 cmd.exe 执行 BAT、托盘图标等）。
- 在打包为 single-file exe 时，建议将 pc_mqtt_config.json 放在 exe 同目录以便编辑与持久化配置。

---

## 如何运行（最短路径）
1. 克隆仓库：
```bash
git clone https://github.com/GE-all-the-time/little_tool.git
cd little_tool
```
2. 安装依赖（根据你要运行的工具选择）：
```bash
# ID_to_PDF 相关依赖
pip install pillow opencv-python numpy reportlab
# pc_mqtt（Windows）依赖
pip install paho-mqtt pystray pillow
# movie_sorter 仅使用标准库/少量第三方库，通常无需额外安装
```
3. 运行工具：
- ID_to_PDF：python3 ID_to_PDF/core.py
- movie_sorter：python3 movie_sorter/movie_sorter_gui.py
- pc_mqtt（Windows）：python pc_mqtt/pc_mqtt_gui.py

---

## 打包/分发
- movie_sorter 目录里已经有 dist_exe.rar（历史打包结果）；可直接参考或使用其中 exe。
- ID_to_PDF 提供了 package.ps1（PowerShell），示例使用 PyInstaller 打包为单文件 exe。
- pc_mqtt 提供了 version_info.txt，可在使用 PyInstaller 打包时通过 `--version-file` 指定以嵌入版本信息。常用打包命令示例：
```bash
python -m PyInstaller --noconsole --onefile --version-file=pc_mqtt/version_info.txt pc_mqtt/pc_mqtt_gui.py
```

打包提示：
- 对于 GUI 桌面程序，建议使用 `--noconsole`（或 `--windowed`）参数以隐藏控制台窗口。
- 若使用 `--onefile`，把需要外部编辑的配置文件（如 `pc_mqtt_config.json`）与 exe 放在同一目录，避免将其打包到内部资源中。

---

## 贡献指南（简要）
- 新增脚本请保持“单文件”风格（一个 .py 做一类工具），文件名使用小写和下划线（例如 `csv_cleaner.py`）。
- 在脚本顶部写明：用途、用法示例、依赖（pip 列表）以及兼容的平台/Python 版本。
- 发起 Pull Request 时在说明中写明测试步骤与主要行为（输入/输出示例）。
- 若要添加独立子目录（带多个文件），请在 README 中补充说明目录用途。

---

## 许可与联系方式
- 当前仓库未指定许可证（若你打算开源/允许他人使用，请在仓库根目录添加 LICENSE，推荐 MIT）。
- 如需我将本 README 提交到仓库或希望我按更正式/更简洁/英文的风格重写，我可以直接帮你提交（需要你确认目标仓库是 GE-all-the-time/little_tool 并允许我执行提交）。

---

如果你愿意，我下一步可以：
- 把本 README 的更新提交到仓库（我已准备好提交），或
- 把 README 同步为英文版或更技术向的版本，或者
- 为 pc_mqtt 生成一个 PyInstaller spec 示例和一个示意的 `pc_mqtt_config.json` 示例文件并提交.
