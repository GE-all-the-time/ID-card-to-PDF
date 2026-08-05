# little_tool

一个收集“单文件 Python 小工具”的仓库 —— 每个工具尽量做小、单一、可直接运行或打包成 exe，便于快速复用、分享与学习。

本仓库当前包含两个主要工具目录：
- ID_to_PDF：带 GUI 的图片（或身份证/证件）批量处理与导出 PDF 工具。
- movie_sorter：用于扫描影视库、统计子文件夹体积并按体积排序的 GUI 工具。

---

## 目录结构（简要）
```text
ID_to_PDF/         # 图像 -> PDF，带预览、裁切、DPI/尺寸调整、导出 PDF（含用于打包的 PowerShell 脚本）
  ├─ core.py       # 主脚本：Tkinter GUI + 图像处理（Pillow / OpenCV / numpy / reportlab 等）
  └─ package.ps1   # Windows 下使用 PyInstaller 打包的示例脚本

movie_sorter/      # 影视文件夹体积扫描与排序工具（GUI）
  ├─ movie_sorter_gui.py  # 主脚本：Tkinter GUI，实现目录选择、递归计算大小、导出排序 TXT
  └─ dist_exe.rar  # （已打包的 exe 的归档，供参考）
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

## 如何运行（最短路径）
1. 克隆仓库：
```bash
git clone https://github.com/GE-all-the-time/little_tool.git
cd little_tool
```
2. 安装依赖（根据你要运行的工具选择）：
```bash
pip install pillow opencv-python numpy reportlab
# 若只运行 movie_sorter，通常只需要 pillow（若无额外依赖）或仅标准库即可
```
3. 运行工具：
- ID_to_PDF：python3 ID_to_PDF/core.py
- movie_sorter：python3 movie_sorter/movie_sorter_gui.py

---

## 打包/分发
- movie_sorter 目录里已经有 dist_exe.rar（历史打包结果）；可直接参考或使用其中 exe。
- ID_to_PDF 提供了 package.ps1（PowerShell），示例使用 PyInstaller 打包为单文件 exe。通用流程（示例）：
  1. Windows 环境：安装 pyinstaller
     pip install pyinstaller
  2. 修改 package.ps1 中的图标/版本信息（如需要），运行 package.ps1（PowerShell）。
  3. 检查 dist/ 下生成的 exe 并使用 UPX / NSIS 做进一步打包或安装器制作（可选）。

---

## 贡献指南（简要）
- 新增脚本请保持“单文件”风格（一个 .py 做一类工具），文件名使用小写和下划线（例如 `csv_cleaner.py`）。
- 在脚本顶部写明：用途、用法示例、依赖（pip 列表）以及兼容的平台/Python 版本。
- 发起 Pull Request 时在说明中写明测试步骤与主要行为（输入/输出示例）。
- 若要添加独立子目录（带多个文件），请在 README 中补充说明目录用途。

---

## 许可与联系方式
- 当前仓库未指定许可证（若你打算开源/允许他人使用，请在仓库根目录添加 LICENSE，推荐 MIT）。
- 如需我将本 README 提交到仓库或希望我按更正式/更简洁/英文的风格重写，告诉我你的偏好，我可以直接帮你提交（需要你确认目标仓库是 GE-all-the-time/little_tool，并授权我进行写操作）。

---

如果你愿意，我下一步可以：
- 直接把上面的 README.md 提交到仓库（我可以为你创建/更新文件），或者
- 根据你的口味把 README 改成更技术向、或更入门向、或英文版。你想怎样继续？
