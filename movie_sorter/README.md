# 🎬 影视库文件夹体积排序工具 (Movie Folder Sorter)

![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-green.svg)
![Build](https://img.shields.io/badge/Executable-10MB%20Standalone-orange.svg)
![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)

专门针对 **NAS / Samba 网络映射盘** 及 **本地大量独立电影文件夹** 开发的轻量级体积排序工具。

解决 Windows 资源管理器、Jellyfin/Emby 或 NAS 网页端在面对数百个独立电影文件夹时无法按**文件夹总体积**降序排列的痛点，帮助你快速定位占用空间最大的影片，高效清理磁盘。

---

## ✨ 核心特性

- 🚀 **极致扫描速度**：底层采用 Python `os.scandir` 递归遍历，扫描速度比传统 `os.walk` 快数倍，专为网络挂载盘优化。
- 🎨 **原生 GUI 界面**：基于 Python 原生 `tkinter` / `ttk` 开发，自动适配 Windows 系统原生外观，操作直观简单。
- 🧵 **多线程防卡死**：采用后台独立线程计算递归体积，即使扫描 1000+ 个网络盘大文件夹，界面依然流畅响应且带有实时进度条。
- 📦 **极轻量打包**：采用原生库编写，打包后的单文件 `.exe` **仅约 10MB**，无需在目标电脑安装 Python 或任何第三方环境。
- 📄 **自动报告输出**：按文件夹体积从大到小严格排序，结果自动导出为对齐排版的 `.txt` 文本，并直接保存在程序所在同级目录下。

---

## 🖥️ 界面与效果预览

### 输出报告示例 (`电影文件夹体积排序.txt`)

```text
======================================================================
 影视库子文件夹体积排序报告
 扫描路径: Z:\Movies
 文件夹总数: 800
======================================================================

001. [  65.42 GB]  Avatar.The.Way.of.Water.2022.2160p.UHD.BluRay
002. [  48.15 GB]  Oppenheimer.2023.2160p.UHD.BluRay
003. [  32.10 GB]  Interstellar.2014.1080p.BluRay
...
799. [ 700.25 MB]  An.Unknown.Short.Film.2010
800. [ 120.10 KB]  Empty.Movie.Folder.Sample
```

---

## 🚀 快速上手 (普通用户)

1. 从 [Releases](../../releases) 页面下载最新版的 `MovieFolderSorter.exe`。
2. 双击运行 `MovieFolderSorter.exe`。
3. 点击 **“浏览...”** 按钮选择你的影视库根目录（支持本地硬盘、网络映射盘符如 `Z:\Movies` 或局域网 UNC 路径如 `\192.168.1.100\Volume1\Movies`）。
4. 点击 **“开始扫描并排序”**。
5. 扫描完成后，点击 **“打开排序 TXT”** 或直接在软件所在目录下查看生成的 `电影文件夹体积排序.txt` 文件。

---

## 🛠️ 构建与打包教程 (开发者)

如果你需要自行修改源代码并打包为 `.exe` 文件，请按以下步骤操作。

### 1. 环境准备

确保本机已安装 Python 3.x 环境，并安装打包工具 `PyInstaller`：

```bash
pip install pyinstaller
```

### 2. 源码文件结构

项目结构非常简单：

```text
.
├── movie_sorter_gui.py     # 完整 Python 源码
└── README.md               # 说明文档
```

### 3. 执行打包命令

在 PowerShell 或 CMD 中运行以下打包命令：

```powershell
# 推荐调用方式（解决 PyInstaller 环境变量未配置问题）
python -m PyInstaller --noconsole --onefile --clean --name "MovieFolderSorter" movie_sorter_gui.py
```

#### 打包参数解析：
- `--noconsole` (`-w`)：隐藏黑色控制台 (CMD) 窗口，仅显示 GUI 图形界面。
- `--onefile` (`-F`)：将程序及所有依赖打包为单一的独立 `.exe` 文件。
- `--clean`：清理临时缓存，确保最终打包文件干净且体积最小。
- `--name "MovieFolderSorter"`：指定输出可执行文件的名称。

打包完成后，生成的可执行文件位于 `dist/MovieFolderSorter.exe`。

---

## 📜 源代码 (`movie_sorter_gui.py`)

```python
import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

def get_exe_dir():
    """获取 exe 文件或当前脚本所在的真实目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_dir_size(path):
    """递归计算整个文件夹（包含所有子文件和子文件夹）的总字节数"""
    total_size = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total_size += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total_size += get_dir_size(entry.path)
                except (PermissionError, FileNotFoundError):
                    continue
    except (PermissionError, FileNotFoundError):
        pass
    return total_size

def format_size(size_in_bytes):
    """格式化文件大小为易读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

class MovieSorterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("影视库文件夹体积排序工具")
        self.geometry("580x310")
        self.resizable(False, False)

        self.style = ttk.Style(self)
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")

        self.create_widgets()

    def create_widgets(self):
        frame_path = ttk.LabelFrame(self, text=" 影视库路径选择 ", padding=12)
        frame_path.pack(fill="x", padx=15, pady=10)

        self.path_var = tk.StringVar()
        self.entry_path = ttk.Entry(frame_path, textvariable=self.path_var, width=50)
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ttk.Button(frame_path, text="浏览...", command=self.browse_folder)
        btn_browse.pack(side="right")

        frame_status = ttk.LabelFrame(self, text=" 扫描进度 ", padding=12)
        frame_status.pack(fill="x", padx=15, pady=5)

        self.lbl_status = ttk.Label(frame_status, text="请选择影视库根目录，然后点击“开始扫描”。")
        self.lbl_status.pack(anchor="w", pady=(0, 8))

        self.progress = ttk.Progressbar(frame_status, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x")

        frame_actions = ttk.Frame(self, padding=10)
        frame_actions.pack(fill="x", padx=15, pady=10)

        self.btn_start = ttk.Button(frame_actions, text="开始扫描并排序", command=self.start_scan_thread)
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_open_txt = ttk.Button(frame_actions, text="打开排序 TXT", command=self.open_result_file, state="disabled")
        self.btn_open_txt.pack(side="left")

        self.output_file_path = None

    def browse_folder(self):
        folder_selected = filedialog.askdirectory(title="选择影视库根目录")
        if folder_selected:
            folder_selected = os.path.normpath(folder_selected)
            self.path_var.set(folder_selected)

    def start_scan_thread(self):
        target_dir = self.path_var.get().strip()
        if not target_dir:
            messagebox.showwarning("提示", "请先选择或粘贴影视库路径！")
            return

        if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
            messagebox.showerror("错误", "指定的路径不存在或不是有效的文件夹！")
            return

        self.btn_start.config(state="disabled")
        self.btn_open_txt.config(state="disabled")

        thread = threading.Thread(target=self.run_scan, args=(target_dir,), daemon=True)
        thread.start()

    def run_scan(self, target_dir):
        try:
            target_path = Path(target_dir)
            subdirs = [p for p in target_path.iterdir() if p.is_dir()]
            total_dirs = len(subdirs)

            if total_dirs == 0:
                self.update_status("⚠️ 指定目录下没有包含任何子文件夹！", 0)
                self.reset_btn()
                return

            dir_sizes = []
            for idx, subdir in enumerate(subdirs, 1):
                percent = int((idx / total_dirs) * 100)
                display_name = subdir.name if len(subdir.name) <= 30 else subdir.name[:27] + "..."
                self.update_status(f"正在扫描 [{idx}/{total_dirs}]: {display_name}", percent)

                size = get_dir_size(subdir)
                dir_sizes.append((subdir.name, size))

            self.update_status("正在进行体积排序并生成文件...", 100)
            dir_sizes.sort(key=lambda x: x[1], reverse=True)

            exe_dir = get_exe_dir()
            output_txt_path = os.path.join(exe_dir, "电影文件夹体积排序.txt")
            
            with open(output_txt_path, "w", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                f.write(f" 影视库子文件夹体积排序报告\n")
                f.write(f" 扫描路径: {target_dir}\n")
                f.write(f" 文件夹总数: {total_dirs}\n")
                f.write("=" * 70 + "\n\n")

                for rank, (dir_name, size) in enumerate(dir_sizes, 1):
                    formatted = format_size(size)
                    line = f"{rank:03d}. [{formatted:>10}]  {dir_name}\n"
                    f.write(line)

            self.output_file_path = output_txt_path
            self.update_status(f"🎉 扫描完成！共处理 {total_dirs} 个文件夹。结果已保存至程序所在目录。", 100)
            self.btn_open_txt.config(state="normal")
            messagebox.showinfo("完成", f"排序已完成！\n报告已保存至软件所在文件夹：\n{output_txt_path}")

        except Exception as e:
            self.update_status(f"❌ 发生错误: {str(e)}", 0)
            messagebox.showerror("异常", f"扫描过程中发生错误：\n{str(e)}")

        finally:
            self.reset_btn()

    def update_status(self, text, progress_val):
        self.lbl_status.config(text=text)
        self.progress['value'] = progress_val
        self.update_idletasks()

    def reset_btn(self):
        self.btn_start.config(state="normal")

    def open_result_file(self):
        if self.output_file_path and os.path.exists(self.output_file_path):
            os.startfile(self.output_file_path)

if __name__ == "__main__":
    app = MovieSorterApp()
    app.mainloop()
```

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 协议，欢迎自由使用、修改及二次分发。
