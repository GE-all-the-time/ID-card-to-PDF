import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

def get_exe_dir():
    """获取 exe 文件或当前脚本所在的真实目录"""
    if getattr(sys, 'frozen', False):
        # 如果是被 PyInstaller 打包后的 exe 环境
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行 .py 脚本的环境
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

        # 尝试使用 Windows 原生皮肤样式
        self.style = ttk.Style(self)
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")

        self.create_widgets()

    def create_widgets(self):
        # 1. 路径选择区域
        frame_path = ttk.LabelFrame(self, text=" 影视库路径选择 ", padding=12)
        frame_path.pack(fill="x", padx=15, pady=10)

        self.path_var = tk.StringVar()
        self.entry_path = ttk.Entry(frame_path, textvariable=self.path_var, width=50)
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ttk.Button(frame_path, text="浏览...", command=self.browse_folder)
        btn_browse.pack(side="right")

        # 2. 状态与进度条区域
        frame_status = ttk.LabelFrame(self, text=" 扫描进度 ", padding=12)
        frame_status.pack(fill="x", padx=15, pady=5)

        self.lbl_status = ttk.Label(frame_status, text="请选择影视库根目录，然后点击“开始扫描”。")
        self.lbl_status.pack(anchor="w", pady=(0, 8))

        self.progress = ttk.Progressbar(frame_status, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x")

        # 3. 底部控制按钮
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
            # 转换为 Windows 规范路径格式
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

        # 使用后台独立线程计算，防止网络盘扫描卡死 GUI 界面
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

            # 修改点：保存在 exe 程序所在的目录中
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
