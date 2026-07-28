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
        self.root.title("身份证 1:1 精准透视校正与 PDF 拼版工具 (专业版)")
        self.root.geometry("1150x820")

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

        # 已完成校正处理的图片列表，存放字典：
        # {"img": numpy_bgr, "w": w_mm, "h": h_mm, "name": title_str}
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
        right_frame = ttk.LabelFrame(self.root, text="设置与操作", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        # 1. 尺寸设置
        ttk.Label(
            right_frame, text="目标物理宽度 (mm):", font=("SimSun", 9)
        ).pack(anchor=tk.W, pady=(5, 2))
        self.entry_w = ttk.Entry(right_frame, width=12)
        self.entry_w.insert(0, "85.6")
        self.entry_w.pack(anchor=tk.W)

        ttk.Label(
            right_frame, text="目标物理高度 (mm):", font=("SimSun", 9)
        ).pack(anchor=tk.W, pady=(5, 2))
        self.entry_h = ttk.Entry(right_frame, width=12)
        self.entry_h.insert(0, "54.0")
        self.entry_h.pack(anchor=tk.W)

        ttk.Separator(right_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # 2. 边缘深色去除设置
        self.var_remove_dark = tk.BooleanVar(value=True)
        chk_dark = ttk.Checkbutton(
            right_frame,
            text="去除/白化边缘深色残余",
            variable=self.var_remove_dark,
        )
        chk_dark.pack(anchor=tk.W, pady=2)

        ttk.Label(
            right_frame, text="深色阈值 (0-255):", font=("SimSun", 8)
        ).pack(anchor=tk.W)
        self.spin_thresh = ttk.Spinbox(
            right_frame, from_=10, to=150, increment=5, width=8
        )
        self.spin_thresh.set(80)
        self.spin_thresh.pack(anchor=tk.W, pady=(0, 5))

        ttk.Separator(right_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # 3. 辅助与导出按钮
        btn_reset_pts = ttk.Button(
            right_frame, text="重置裁剪框", command=self.reset_points
        )
        btn_reset_pts.pack(fill=tk.X, pady=3)

        btn_preview = ttk.Button(
            right_frame, text="🔍 预览校正效果", command=self.preview_crop
        )
        btn_preview.pack(fill=tk.X, pady=3)

        btn_crop = ttk.Button(
            right_frame,
            text="2. 确认并保存当前页",
            command=self.process_current,
        )
        btn_crop.pack(fill=tk.X, pady=3)

        ttk.Separator(right_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # 4. 卡片管理与状态显示
        self.lbl_status = ttk.Label(
            right_frame, text="已就绪卡片: 0 张", foreground="blue"
        )
        self.lbl_status.pack(anchor=tk.W, pady=2)

        btn_manage = ttk.Button(
            right_frame, text="📋 管理/排序已就绪卡片", command=self.open_manager_window
        )
        btn_manage.pack(fill=tk.X, pady=5)

        ttk.Separator(right_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        btn_export = ttk.Button(
            right_frame, text="3. 导出为 A4 PDF", command=self.export_pdf
        )
        btn_export.pack(fill=tk.X, pady=10)

        # 中央 Canvas 画布区域
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10
        )

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 绑定鼠标拖拽事件
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
        self.lbl_status.config(text="已就绪卡片: 0 张")

        self.show_image()

    def show_image(self):
        if not self.image_paths:
            return

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

        imgPath = self.image_paths[self.current_idx]
        self.raw_bgr_img = cv2.imread(imgPath)
        if self.raw_bgr_img is None:
            messagebox.showerror("错误", f"无法加载图片: {imgPath}")
            return

        h, w = self.raw_bgr_img.shape[:2]

        canvas_w = self.canvas.winfo_width() or 700
        canvas_h = self.canvas.winfo_height() or 550

        scale_w = canvas_w / w
        scale_h = canvas_h / h
        self.display_scale = min(scale_w, scale_h, 1.0)

        disp_w = int(w * self.display_scale)
        disp_h = int(h * self.display_scale)

        rgb_img = cv2.cvtColor(
            cv2.resize(self.raw_bgr_img, (disp_w, disp_h)), cv2.COLOR_BGR2RGB
        )
        self.photo_image = ImageTk.PhotoImage(Image.fromarray(rgb_img))

        self.canvas.delete("all")
        self.canvas.config(width=disp_w, height=disp_h)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)

        margin_w = disp_w * 0.12
        margin_h = disp_h * 0.12
        self.points = [
            [margin_w, margin_h],
            [disp_w - margin_w, margin_h],
            [disp_w - margin_w, disp_h - margin_h],
            [margin_w, disp_h - margin_h],
        ]

        self.draw_handles()

    def reset_points(self):
        if self.raw_bgr_img is not None:
            self.show_image()

    def draw_handles(self):
        for item in self.handle_ids + self.line_ids:
            self.canvas.delete(item)
        self.handle_ids.clear()
        self.line_ids.clear()

        for i in range(4):
            line = self.canvas.create_line(
                0, 0, 0, 0, fill="#00FF00", width=2, dash=(4, 4)
            )
            self.line_ids.append(line)

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
            self.canvas.coords(
                self.line_ids[i], p1[0], p1[1], p2[0], p2[1]
            )
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

    def _get_processed_image(self):
        if self.raw_bgr_img is None:
            return None, 0, 0

        try:
            target_w_mm = float(self.entry_w.get())
            target_h_mm = float(self.entry_h.get())
        except ValueError:
            messagebox.showerror("输入错误", "请确认宽度和高度数值填写正确！")
            return None, 0, 0

        src_pts = np.float32(
            [
                [p[0] / self.display_scale, p[1] / self.display_scale]
                for p in self.points
            ]
        )

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

        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(
            self.raw_bgr_img,
            M,
            (out_w_px, out_h_px),
            flags=cv2.INTER_CUBIC,
        )

        if self.var_remove_dark.get():
            try:
                thresh_val = float(self.spin_thresh.get())
            except ValueError:
                thresh_val = 80.0

            gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            _, dark_mask = cv2.threshold(
                gray, thresh_val, 255, cv2.THRESH_BINARY_INV
            )

            ff_mask = np.zeros(
                (out_h_px + 2, out_w_px + 2), dtype=np.uint8
            )
            dark_seed_mask = dark_mask.copy()

            seed_points = []
            for x in range(0, out_w_px, 3):
                if dark_seed_mask[0, x] == 255:
                    seed_points.append((x, 0))
                if dark_seed_mask[out_h_px - 1, x] == 255:
                    seed_points.append((x, out_h_px - 1))
            for y in range(0, out_h_px, 3):
                if dark_seed_mask[y, 0] == 255:
                    seed_points.append((0, y))
                if dark_seed_mask[y, out_w_px - 1] == 255:
                    seed_points.append((out_w_px - 1, y))

            for sx, sy in seed_points:
                if dark_seed_mask[sy, sx] == 255:
                    cv2.floodFill(
                        dark_seed_mask,
                        ff_mask,
                        (sx, sy),
                        128,
                        flags=4 | (128 << 8),
                    )

            border_dark_pixels = dark_seed_mask == 128
            warped[border_dark_pixels] = [255, 255, 255]

            shrink_px = 2
            warped[:shrink_px, :] = [255, 255, 255]
            warped[-shrink_px:, :] = [255, 255, 255]
            warped[:, :shrink_px] = [255, 255, 255]
            warped[:, -shrink_px:] = [255, 255, 255]

        return warped, target_w_mm, target_h_mm

    def preview_crop(self):
        warped, w_mm, h_mm = self._get_processed_image()
        if warped is None:
            return

        preview_win = tk.Toplevel(self.root)
        preview_win.title("校正效果预览")
        preview_win.geometry("700x500")

        h, w = warped.shape[:2]
        max_preview_size = 600
        scale = min(max_preview_size / w, max_preview_size / h, 1.0)
        disp_w = int(w * scale)
        disp_h = int(h * scale)

        preview_bgr = cv2.resize(warped, (disp_w, disp_h))
        preview_rgb = cv2.cvtColor(preview_bgr, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(preview_rgb)
        img_tk = ImageTk.PhotoImage(img_pil)

        lbl_img = ttk.Label(preview_win, image=img_tk)
        lbl_img.image = img_tk
        lbl_img.pack(padx=20, pady=20, expand=True)

        lbl_tip = ttk.Label(
            preview_win,
            text=f"实际物理导出尺寸：{w_mm} mm x {h_mm} mm",
            font=("Arial", 10, "bold"),
        )
        lbl_tip.pack(pady=5)

    def process_current(self):
        warped, w_mm, h_mm = self._get_processed_image()
        if warped is None:
            return

        filename = os.path.basename(self.image_paths[self.current_idx])
        card_name = f"卡片 #{len(self.processed_records)+1} ({filename})"

        record = {
            "img": warped,
            "w": w_mm,
            "h": h_mm,
            "name": card_name
        }

        self.processed_records.append(record)
        self.lbl_status.config(
            text=f"已就绪卡片: {len(self.processed_records)} 张"
        )
        messagebox.showinfo(
            "提示",
            f"当前卡片已保存！\n当前共有 {len(self.processed_records)} 张已就绪卡片。",
        )

    def open_manager_window(self):
        """打开已就绪卡片管理与排序窗口"""
        if not self.processed_records:
            messagebox.showinfo("提示", "当前没有已就绪的卡片！")
            return

        manager_win = tk.Toplevel(self.root)
        manager_win.title("卡片排版管理与 PDF 分组预览")
        manager_win.geometry("600x650")
        manager_win.transient(self.root)

        # 头部说明
        top_tip = ttk.Label(
            manager_win,
            text="💡 提示：每页 A4 放置 2 张卡片。你可以调整顺序或删除卡片。",
            font=("Arial", 9),
            foreground="gray",
        )
        top_tip.pack(anchor=tk.W, padx=15, pady=(10, 5))

        # 带滚动条的容器
        container = ttk.Frame(manager_win)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas_mgr = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            container, orient="vertical", command=canvas_mgr.yview
        )
        scroll_frame = ttk.Frame(canvas_mgr)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas_mgr.configure(
                scrollregion=canvas_mgr.bbox("all")
            ),
        )
        canvas_mgr.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas_mgr.configure(yscrollcommand=scrollbar.set)

        canvas_mgr.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def move_item(index, direction):
            new_idx = index + direction
            if 0 <= new_idx < len(self.processed_records):
                self.processed_records[index], self.processed_records[new_idx] = (
                    self.processed_records[new_idx],
                    self.processed_records[index],
                )
                refresh_list()

        def delete_item(index):
            item_name = self.processed_records[index]["name"]
            if messagebox.askyesno(
                "确认删除",
                f"确定要删除 '{item_name}' 吗？",
                parent=manager_win,
            ):
                self.processed_records.pop(index)
                refresh_list()

        def refresh_list():
            # 清理旧组件
            for widget in scroll_frame.winfo_children():
                widget.destroy()

            if not self.processed_records:
                ttk.Label(
                    scroll_frame, text="暂无卡片", font=("Arial", 11)
                ).pack(pady=30)
                self.lbl_status.config(text="已就绪卡片: 0 张")
                return

            self.lbl_status.config(
                text=f"已就绪卡片: {len(self.processed_records)} 张"
            )

            manager_win.thumbnails = []  # 保持图片引用防止 GC

            for idx, item in enumerate(self.processed_records):
                page_num = (idx // 2) + 1
                slot_name = "【正面/上部】" if (idx % 2 == 0) else "【背面/下部】"

                # 遇到每一页的第一张时，绘制 PDF 页码分组标题
                if idx % 2 == 0:
                    group_frame = ttk.Frame(scroll_frame)
                    group_frame.pack(fill=tk.X, pady=(15, 5), padx=5)
                    ttk.Label(
                        group_frame,
                        text=f"📄 PDF 第 {page_num} 页",
                        font=("Arial", 10, "bold"),
                        foreground="#0055AA",
                    ).pack(side=tk.LEFT)
                    ttk.Separator(group_frame, orient="horizontal").pack(
                        side=tk.LEFT, fill=tk.X, expand=True, padx=10
                    )

                # 单张卡片卡槽
                row_frame = ttk.Frame(
                    scroll_frame, padding=6, relief="groove", borderwidth=1
                )
                row_frame.pack(fill=tk.X, pady=3, padx=5)

                # 1. 位置标识
                lbl_pos = ttk.Label(
                    row_frame,
                    text=slot_name,
                    width=13,
                    font=("SimSun", 9, "bold"),
                    foreground="#333333",
                )
                lbl_pos.pack(side=tk.LEFT, padx=2)

                # 2. 缩略图生成
                thumb_bgr = cv2.resize(item["img"], (70, 44))
                thumb_rgb = cv2.cvtColor(thumb_bgr, cv2.COLOR_BGR2RGB)
                thumb_pil = Image.fromarray(thumb_rgb)
                thumb_tk = ImageTk.PhotoImage(thumb_pil)
                manager_win.thumbnails.append(thumb_tk)

                lbl_thumb = ttk.Label(row_frame, image=thumb_tk)
                lbl_thumb.pack(side=tk.LEFT, padx=5)

                # 3. 卡片名称与尺寸
                info_text = f"{item['name']}\n尺寸: {item['w']}mm x {item['h']}mm"
                lbl_info = ttk.Label(
                    row_frame, text=info_text, font=("SimSun", 9)
                )
                lbl_info.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

                # 4. 操作按钮组
                btn_frame = ttk.Frame(row_frame)
                btn_frame.pack(side=tk.RIGHT)

                btn_up = ttk.Button(
                    btn_frame,
                    text="▲ 上移",
                    width=6,
                    command=lambda i=idx: move_item(i, -1),
                )
                if idx == 0:
                    btn_up.config(state=tk.DISABLED)
                btn_up.pack(side=tk.LEFT, padx=2)

                btn_down = ttk.Button(
                    btn_frame,
                    text="▼ 下移",
                    width=6,
                    command=lambda i=idx: move_item(i, 1),
                )
                if idx == len(self.processed_records) - 1:
                    btn_down.config(state=tk.DISABLED)
                btn_down.pack(side=tk.LEFT, padx=2)

                btn_del = ttk.Button(
                    btn_frame,
                    text="🗑️ 删除",
                    width=6,
                    command=lambda i=idx: delete_item(i),
                )
                btn_del.pack(side=tk.LEFT, padx=4)

        refresh_list()

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
        max_per_page = 2

        for idx, item in enumerate(self.processed_records):
            warped_bgr = item["img"]
            w_mm = item["w"]
            h_mm = item["h"]

            page_slot = idx % max_per_page

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            cv2.imwrite(tmp.name, warped_bgr)
            temp_files.append(tmp.name)
            tmp.close()

            card_w_pt = w_mm * mm
            card_h_pt = h_mm * mm
            x_pt = (a4_w_pt - card_w_pt) / 2.0

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

            if page_slot == 1 or idx == len(self.processed_records) - 1:
                pdf_canvas.showPage()

        pdf_canvas.save()

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
