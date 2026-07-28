import os
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


class IDCardScannerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("身份证 1:1 精准透视校正与 PDF 拼版工具")
        self.root.geometry("1100x780")

        # 数据状态
        self.image_paths = []
        self.current_idx = 0
        self.raw_bgr_img = None  # 当前原图 (BGR)
        self.display_scale = 1.0  # 画布缩放比例

        # 四角控制点坐标 [(x1, y1), (x2, y2), (x3, y3), (x4, y4)] -> 顺序: 左上, 右上, 右下, 左下
        self.points = []
        self.handle_ids = []
        self.line_ids = []
        self.drag_idx = None

        # 已完成校正处理的图片列表: 元组 (numpy_bgr_array, width_mm, height_mm)
        self.processed_records = []

        self._build_ui()

    def _build_ui(self):
        # 顶端控制面板
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        btn_load = ttk.Button(
            top_frame, text="1. 选择身份证图片(可多选)", command=self.load_images
        )
        btn_load.pack(side=tk.LEFT, padx=5)

        self.lbl_file_info = ttk.Label(
            top_frame, text="未加载图片", font=("Arial", 10, "bold")
        )
        self.lbl_file_info.pack(side=tk.LEFT, padx=15)

        self.btn_prev = ttk.Button(
            top_frame, text="◀ 上一张", command=self.prev_image, state=tk.DISABLED
        )
        self.btn_prev.pack(side=tk.LEFT, padx=2)

        self.btn_next = ttk.Button(
            top_frame, text="下一张 ▶", command=self.next_image, state=tk.DISABLED
        )
        self.btn_next.pack(side=tk.LEFT, padx=2)

        # 右侧参数设置与操作面板
        right_frame = ttk.LabelFrame(
            self.root, text="设置与导出", padding=10
        )
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        # 尺寸输入 (默认中国二代身份证物理尺寸 85.6mm x 54.0mm)
        ttk.Label(
            right_frame, text="目标物理宽度 (mm):", font=("SimSun", 9)
        ).pack(anchor=tk.W, pady=(10, 2))
        self.entry_w = ttk.Entry(right_frame, width=12)
        self.entry_w.insert(0, "85.6")
        self.entry_w.pack(anchor=tk.W)

        ttk.Label(
            right_frame, text="目标物理高度 (mm):", font=("SimSun", 9)
        ).pack(anchor=tk.W, pady=(10, 2))
        self.entry_h = ttk.Entry(right_frame, width=12)
        self.entry_h.insert(0, "54.0")
        self.entry_h.pack(anchor=tk.W)

        ttk.Separator(right_frame, orient="horizontal").pack(
            fill=tk.X, pady=15
        )

        btn_reset_pts = ttk.Button(
            right_frame, text="重置裁剪框", command=self.reset_points
        )
        btn_reset_pts.pack(fill=tk.X, pady=4)

        btn_crop = ttk.Button(
            right_frame, text="2. 校正并保存当前页", command=self.process_current
        )
        btn_crop.pack(fill=tk.X, pady=4)

        ttk.Separator(right_frame, orient="horizontal").pack(
            fill=tk.X, pady=15
        )

        self.lbl_status = ttk.Label(
            right_frame, text="已就绪页数: 0", foreground="blue"
        )
        self.lbl_status.pack(anchor=tk.W, pady=5)

        btn_export = ttk.Button(
            right_frame, text="3. 导出为 A4 PDF", command=self.export_pdf
        )
        btn_export.pack(fill=tk.X, pady=10)

        # 中央 Canvas 画布区域 (拖拽剪裁)
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10
        )

        self.canvas = tk.Canvas(canvas_frame, bg="#333333")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 绑定鼠标事件
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)

    def load_images(self):
        paths = filedialog.askopenfilenames(
            title="选择身份证照片",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp")],
        )
        if not paths:
            return

        self.image_paths = list(paths)
        self.current_idx = 0
        self.processed_records = []
        self.lbl_status.config(text="已就绪页数: 0")

        self.show_image()

    def show_image(self):
        if not self.image_paths:
            return

        # 更新导航按钮
        self.btn_prev.config(
            state=tk.NORMAL if self.current_idx > 0 else tk.DISABLED
        )
        self.btn_next.config(
            state=tk.NORMAL
            if self.current_idx < len(self.image_paths) - 1
            else tk.DISABLED
        )
        self.lbl_file_info.config(
            text=f"图片 ({self.current_idx + 1}/{len(self.image_paths)}): {os.path.basename(self.image_paths[self.current_idx])}"
        )

        # 读取图片
        imgPath = self.image_paths[self.current_idx]
        self.raw_bgr_img = cv2.imread(imgPath)
        if self.raw_bgr_img is None:
            messagebox.showerror("错误", f"无法加载图片: {imgPath}")
            return

        h, w = self.raw_bgr_img.shape[:2]

        # 调整适应 Canvas 尺寸
        canvas_w = self.canvas.winfo_width() or 700
        canvas_h = self.canvas.winfo_height() or 550

        scale_w = canvas_w / w
        scale_h = canvas_h / h
        self.display_scale = min(scale_w, scale_h, 1.0)  # 不放大超出原图

        disp_w = int(w * self.display_scale)
        disp_h = int(h * self.display_scale)

        # 转换并展示图片
        rgb_img = cv2.cvtColor(
            cv2.resize(self.raw_bgr_img, (disp_w, disp_h)), cv2.COLOR_BGR2RGB
        )
        self.photo_image = ImageTk.PhotoImage(Image.fromarray(rgb_img))

        self.canvas.delete("all")
        self.canvas.config(width=disp_w, height=disp_h)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)

        # 设置默认四角锚点 (按左上, 右上, 右下, 左下)
        margin_w = disp_w * 0.15
        margin_h = disp_h * 0.15
        self.points = [
            [margin_w, margin_h],  # 左上
            [disp_w - margin_w, margin_h],  # 右上
            [disp_w - margin_w, disp_h - margin_h],  # 右下
            [margin_w, disp_h - margin_h],  # 左下
        ]

        self.draw_handles()

    def reset_points(self):
        if self.raw_bgr_img is not None:
            self.show_image()

    def draw_handles(self):
        # 清除旧的控制线与节点
        for item in self.handle_ids + self.line_ids:
            self.canvas.delete(item)
        self.handle_ids.clear()
        self.line_ids.clear()

        # 绘制四条连接边线
        for i in range(4):
            line = self.canvas.create_line(
                0, 0, 0, 0, fill="#00FF00", width=2, dash=(4, 4)
            )
            self.line_ids.append(line)

        # 绘制 4 个可拖拽圆点
        r = 7
        for i in range(4):
            handle = self.canvas.create_oval(
                0, 0, 0, 0, fill="#FFD700", outline="#FF0000", width=2
            )
            self.handle_ids.append(handle)

        self.update_shapes()

    def update_shapes(self):
        r = 7
        for i in range(4):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % 4]
            # 更新线段
            self.canvas.coords(
                self.line_ids[i], p1[0], p1[1], p2[0], p2[1]
            )
            # 更新锚点
            self.canvas.coords(
                self.handle_ids[i],
                p1[0] - r,
                p1[1] - r,
                p1[0] + r,
                p1[1] + r,
            )

    def on_mouse_press(self, event):
        r = 15
        for i, (x, y) in enumerate(self.points):
            if (event.x - x) ** 2 + (event.y - y) ** 2 <= r**2:
                self.drag_idx = i
                break

    def on_mouse_drag(self, event):
        if self.drag_idx is not None:
            # 限制拖动范围在 Canvas 内部
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            nx = max(0, min(event.x, cw))
            ny = max(0, min(event.y, ch))
            self.points[self.drag_idx] = [nx, ny]
            self.update_shapes()

    def on_mouse_release(self, event):
        self.drag_idx = None

    def prev_image(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.show_image()

    def next_image(self):
        if self.current_idx < len(self.image_paths) - 1:
            self.current_idx += 1
            self.show_image()

    def process_current(self):
        if self.raw_bgr_img is None:
            return

        try:
            target_w_mm = float(self.entry_w.get())
            target_h_mm = float(self.entry_h.get())
        except ValueError:
            messagebox.showerror("输入错误", "请确认宽度和高度数值填写正确！")
            return

        # 计算映射回原图的高清坐标
        src_pts = np.float32(
            [
                [p[0] / self.display_scale, p[1] / self.display_scale]
                for p in self.points
            ]
        )

        # 300 DPI 下的标准输出分辨率
        dpi = 300
        out_w_px = int(round(target_w_mm / 25.4 * dpi))
        out_h_px = int(round(target_h_mm / 25.4 * dpi))

        dst_pts = np.float32(
            [
                [0, 0],
                [out_w_px - 1, 0],
                [out_w_px - 1, out_h_px - 1],
                [0, out_h_px - 1],
            ]
        )

        # 梯形透视校正变换
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(
            self.raw_bgr_img,
            M,
            (out_w_px, out_h_px),
            flags=cv2.INTER_CUBIC,
        )

        # 记录处理结果
        self.processed_records.append((warped, target_w_mm, target_h_mm))
        self.lbl_status.config(
            text=f"已就绪页数: {len(self.processed_records)}"
        )
        messagebox.showinfo(
            "提示",
            f"当前图片已校正保存！\n累计保存: {len(self.processed_records)} 张",
        )

    def export_pdf(self):
        if not self.processed_records:
            messagebox.showwarning("警告", "尚未保存任何校正好的图片！")
            return

        save_path = filedialog.asksaveasfilename(
            title="保存 PDF 文件",
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf")],
        )
        if not save_path:
            return

        pdf_canvas = canvas.Canvas(save_path, pagesize=A4)
        a4_w_pt, a4_h_pt = A4

        temp_files = []

        # 默认一页 A4 排版最多 2 张卡片 (正面在上，背面在下)
        max_per_page = 2

        for idx, (warped_bgr, w_mm, h_mm) in enumerate(self.processed_records):
            page_slot = idx % max_per_page

            # 保存临时图片文件供 ReportLab 使用
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            cv2.imwrite(tmp.name, warped_bgr)
            temp_files.append(tmp.name)
            tmp.close()

            # 将物理毫米转换为 ReportLab 的 pt 单位
            card_w_pt = w_mm * mm
            card_h_pt = h_mm * mm

            # 居中水平对齐
            x_pt = (a4_w_pt - card_w_pt) / 2.0

            # 垂直位置计算: 第一张置于上半页，第二张置于下半页
            if page_slot == 0:
                y_pt = (a4_h_pt * 0.65) - (card_h_pt / 2.0)
            else:
                y_pt = (a4_h_pt * 0.35) - (card_h_pt / 2.0)

            pdf_canvas.drawImage(
                temp_files[-1],
                x_pt,
                y_pt,
                width=card_w_pt,
                height=card_h_pt,
            )

            # 满两张或已是最后一张时换页
            if page_slot == 1 or idx == len(self.processed_records) - 1:
                pdf_canvas.showPage()

        pdf_canvas.save()

        # 清理临时文件
        for tf in temp_files:
            try:
                os.remove(tf)
            except Exception:
                pass

        messagebox.showinfo(
            "导出成功",
            f"PDF 文件已生成！\n保存位置：{save_path}\n\n⚠️ 打印注意：\n请在 PDF 打印设置中勾选『实际大小』或『100% 缩放』，切勿勾选『适合可打印区域』！",
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = IDCardScannerApp(root)
    root.mainloop()
