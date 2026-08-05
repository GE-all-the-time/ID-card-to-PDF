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
        self.root.title("身份证 1:1 精准透视校正与 PDF 拼版工具 (极速单点流版)")
        self.root.geometry("1180x830")

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

        # 已完成校正处理的图片列表
        self.processed_records = []

        self._build_ui()

    def _build_ui(self):
        # 顶端控制面板 (步骤 1 与 翻页)
        top_frame = ttk.Frame(self.root, padding=(10, 8))
        top_frame.pack(side=tk.TOP, fill=tk.X)

        # 步骤 1 主按钮
        btn_load = tk.Button(
            top_frame,
            text="📁 1. 选择身份证图片 (可多选)",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="#0078D4",
            fg="white",
            activebackground="#005A9E",
            activeforeground="white",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.load_images,
        )
        btn_load.pack(side=tk.LEFT, padx=(5, 10))

        self.lbl_file_info = ttk.Label(
            top_frame, text="未加载图片", font=("Microsoft YaHei UI", 10, "bold")
        )
        self.lbl_file_info.pack(side=tk.LEFT, padx=10)

        # 翻页控制 (备用/回溯按钮)
        self.btn_next = ttk.Button(
            top_frame, text="下一张 ▶", command=self.next_image, state=tk.DISABLED
        )
        self.btn_next.pack(side=tk.RIGHT, padx=5)

        self.btn_prev = ttk.Button(
            top_frame, text="◀ 上一张", command=self.prev_image, state=tk.DISABLED
        )
        self.btn_prev.pack(side=tk.RIGHT, padx=2)

        # 右侧参数设置与核心流程面板
        right_frame = ttk.Frame(self.root, padding=10, width=310)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
        right_frame.pack_propagate(False)

        # === 区块 1：基本尺寸与去黑边参数 ===
        param_frame = ttk.LabelFrame(right_frame, text="⚙️ 校正参数设置", padding=8)
        param_frame.pack(fill=tk.X, pady=(0, 10))

        grid_p = ttk.Frame(param_frame)
        grid_p.pack(fill=tk.X)

        ttk.Label(grid_p, text="目标宽度(mm):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.entry_w = ttk.Entry(grid_p, width=8)
        self.entry_w.insert(0, "85.6")
        self.entry_w.grid(row=0, column=1, sticky=tk.E, pady=2)

        ttk.Label(grid_p, text="目标高度(mm):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.entry_h = ttk.Entry(grid_p, width=8)
        self.entry_h.insert(0, "54.0")
        self.entry_h.grid(row=1, column=1, sticky=tk.E, pady=2)

        ttk.Separator(param_frame, orient="horizontal").pack(fill=tk.X, pady=6)

        self.var_remove_dark = tk.BooleanVar(value=True)
        chk_dark = ttk.Checkbutton(
            param_frame,
            text="去除/白化边缘黑边",
            variable=self.var_remove_dark,
        )
        chk_dark.pack(anchor=tk.W)

        sub_dark_frame = ttk.Frame(param_frame)
        sub_dark_frame.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(sub_dark_frame, text="黑边阈值:").pack(side=tk.LEFT)
        self.spin_thresh = ttk.Spinbox(
            sub_dark_frame, from_=10, to=150, increment=5, width=6
        )
        self.spin_thresh.set(80)
        self.spin_thresh.pack(side=tk.RIGHT)

        # === 区块 2：辅助工具栏（横向紧凑收纳） ===
        aux_frame = ttk.LabelFrame(right_frame, text="🛠️ 辅助微调 (可选)", padding=6)
        aux_frame.pack(fill=tk.X, pady=(0, 15))

        btn_grid = ttk.Frame(aux_frame)
        btn_grid.pack(fill=tk.X)

        btn_auto_detect = ttk.Button(
            btn_grid, text="🤖 重新识别", width=9, command=self.auto_detect_and_update
        )
        btn_auto_detect.grid(row=0, column=0, padx=2, pady=2)

        btn_reset_pts = ttk.Button(
            btn_grid, text="🔄 重置", width=7, command=self.reset_points
        )
        btn_reset_pts.grid(row=0, column=1, padx=2, pady=2)

        btn_preview = ttk.Button(
            btn_grid, text="🔍 预览", width=7, command=self.preview_crop
        )
        btn_preview.grid(row=0, column=2, padx=2, pady=2)

        # === 区块 3：主流程 - 步骤 2 (一键保存并跳下一张) ===
        btn_crop = tk.Button(
            right_frame,
            text="✔ 2. 确认并保存当前页",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="#0078D4",
            fg="white",
            activebackground="#005A9E",
            activeforeground="white",
            bd=0,
            pady=10,
            cursor="hand2",
            command=self.process_current,
        )
        btn_crop.pack(fill=tk.X, pady=(5, 15))

        # === 区块 4：卡片管理区 ===
        status_frame = ttk.LabelFrame(right_frame, text="📋 已添加卡片列表", padding=8)
        status_frame.pack(fill=tk.X, pady=(0, 15))

        self.lbl_status = ttk.Label(
            status_frame,
            text="当前已就绪: 0 张",
            font=("Microsoft YaHei UI", 9, "bold"),
            foreground="#107C41",
        )
        self.lbl_status.pack(anchor=tk.W, pady=(0, 5))

        btn_manage = ttk.Button(
            status_frame, text="📑 管理 / 调整已就绪卡片", command=self.open_manager_window
        )
        btn_manage.pack(fill=tk.X)

        # === 区块 5：主流程 - 步骤 3 (终极导出) ===
        btn_export = tk.Button(
            right_frame,
            text="🚀 3. 导出为 A4 PDF",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="#107C41",
            fg="white",
            activebackground="#0B5A2F",
            activeforeground="white",
            bd=0,
            pady=12,
            cursor="hand2",
            command=self.export_pdf,
        )
        btn_export.pack(fill=tk.X, side=tk.BOTTOM, pady=10)

        # 中央 Canvas 画布区域
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 10), pady=10
        )

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 绑定鼠标拖拽事件
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)

    def _order_points(self, pts):
        """对 4 个坐标点按照 [左上, 右上, 右下, 左下] 进行排序"""
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]  # 左上
        rect[2] = pts[np.argmax(s)]  # 右下

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # 右上
        rect[3] = pts[np.argmax(diff)]  # 左下
        return rect

    def _calc_line_intersection(self, line1, line2):
        """计算两条直线的延长线交点 (Ax + By + C = 0)"""
        vx1, vy1, x1, y1 = (
            float(line1[0][0]),
            float(line1[1][0]),
            float(line1[2][0]),
            float(line1[3][0]),
        )
        vx2, vy2, x2, y2 = (
            float(line2[0][0]),
            float(line2[1][0]),
            float(line2[2][0]),
            float(line2[3][0]),
        )

        A1, B1 = vy1, -vx1
        C1 = vx1 * y1 - vy1 * x1

        A2, B2 = vy2, -vx2
        C2 = vx2 * y2 - vy2 * x2

        det = A1 * B2 - A2 * B1
        if abs(det) < 1e-5:
            return None  # 平行无交点

        x = (B1 * C2 - B2 * C1) / det
        y = (A2 * C1 - A1 * C2) / det
        return [x, y]

    def auto_detect_card_corners(self):
        """高阶算法：剔除圆角 + 直线方程拟合 + 延长线求交点"""
        if self.raw_bgr_img is None:
            return None

        h, w = self.raw_bgr_img.shape[:2]
        img_area = w * h

        # 1. 灰度与高斯降噪
        gray = cv2.cvtColor(self.raw_bgr_img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)

        # 2. Otsu 二值化分割前景与背景
        _, thresh = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # 3. 闭运算填充卡片内部杂色
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # 4. 提取轮廓并锁定最大卡片连通域
        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        if not contours:
            return None

        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        card_cnt = None
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 0.10 * img_area < area < 0.95 * img_area:
                card_cnt = cnt
                break

        if card_cnt is None:
            return None

        # 5. 获取带角度的外接矩形作为参考边框
        rect_rot = cv2.minAreaRect(card_cnt)
        box = cv2.boxPoints(rect_rot)
        ref_pts = self._order_points(box)  # 顺序: [TL, TR, BR, BL]

        # 6. 对 4 条边分别收集中间 60% 的直线段点集（避开两端 R 弧角）
        cnt_pts = card_cnt.reshape(-1, 2)
        fitted_lines = []  # 顺序：0:Top, 1:Right, 2:Bottom, 3:Left

        for i in range(4):
            p_a = ref_pts[i]
            p_b = ref_pts[(i + 1) % 4]

            vec_e = p_b - p_a
            length = np.linalg.norm(vec_e)
            if length < 1e-5:
                fitted_lines.append(None)
                continue
            dir_e = vec_e / length

            edge_pts = []
            for pt in cnt_pts:
                v = pt - p_a
                t = np.dot(v, dir_e)  # 投影轴坐标

                # 仅提取距离边线近且在 20% ~ 80% 之间的点，彻底舍弃两头圆角
                if 0.20 * length <= t <= 0.80 * length:
                    dist = abs(v[0] * dir_e[1] - v[1] * dir_e[0])
                    if dist <= max(12.0, length * 0.04):
                        edge_pts.append(pt)

            if len(edge_pts) >= 5:
                pts_arr = np.array(edge_pts, dtype=np.float32)
                # 最小二乘法拟合直线
                line = cv2.fitLine(pts_arr, cv2.DIST_L2, 0, 0.01, 0.01)
                fitted_lines.append(line)
            else:
                fitted_lines.append(None)

        # 7. 计算四条拟合直线的两两延长线交点
        intersection_corners = []
        for i in range(4):
            line_prev = fitted_lines[(i - 1) % 4]
            line_curr = fitted_lines[i]

            if line_prev is not None and line_curr is not None:
                pt_inter = self._calc_line_intersection(line_prev, line_curr)
                if pt_inter is not None:
                    intersection_corners.append(pt_inter)
                else:
                    intersection_corners.append(ref_pts[i].tolist())
            else:
                intersection_corners.append(ref_pts[i].tolist())

        # 8. 缩放到 Canvas 画布当前比例
        scale = self.display_scale
        disp_pts = [
            [float(p[0] * scale), float(p[1] * scale)]
            for p in intersection_corners
        ]
        return disp_pts

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
        self.lbl_status.config(text="当前已就绪: 0 张")

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

        # 优先使用自动识别贴合
        auto_pts = self.auto_detect_card_corners()
        if auto_pts is not None:
            self.points = auto_pts
        else:
            margin_w = disp_w * 0.12
            margin_h = disp_h * 0.12
            self.points = [
                [margin_w, margin_h],
                [disp_w - margin_w, margin_h],
                [disp_w - margin_w, disp_h - margin_h],
                [margin_w, disp_h - margin_h],
            ]

        self.draw_handles()

    def auto_detect_and_update(self):
        """用户点击按钮重新自动识别"""
        auto_pts = self.auto_detect_card_corners()
        if auto_pts is not None:
            self.points = auto_pts
            self.draw_handles()
        else:
            messagebox.showwarning(
                "识别提示",
                "未能自动识别到明显的证件边缘轮廓，请手动拖动角点对齐。",
            )

    def reset_points(self):
        if self.raw_bgr_img is not None:
            disp_w = self.canvas.winfo_width()
            disp_h = self.canvas.winfo_height()
            margin_w = disp_w * 0.12
            margin_h = disp_h * 0.12
            self.points = [
                [margin_w, margin_h],
                [disp_w - margin_w, margin_h],
                [disp_w - margin_w, disp_h - margin_h],
                [margin_w, disp_h - margin_h],
            ]
            self.draw_handles()

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
            font=("Microsoft YaHei UI", 10, "bold"),
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
            "name": card_name,
        }

        self.processed_records.append(record)
        self.lbl_status.config(
            text=f"当前已就绪: {len(self.processed_records)} 张"
        )

        # 💡 优化交互：如果不为最后一张，保存后自动切换至下一张
        if self.current_idx < len(self.image_paths) - 1:
            self.next_image()
        else:
            messagebox.showinfo(
                "全部处理完成",
                f"🎉 当前所有图片均已保存完毕！\n列表中共有 {len(self.processed_records)} 张卡片已就绪。\n现在可以点击『3. 导出为 A4 PDF』进行排版导出。",
            )

    def open_manager_window(self):
        if not self.processed_records:
            messagebox.showinfo("提示", "当前没有已就绪的卡片！")
            return

        manager_win = tk.Toplevel(self.root)
        manager_win.title("卡片排版管理与 PDF 分组预览")
        manager_win.geometry("600x650")
        manager_win.transient(self.root)

        top_tip = ttk.Label(
            manager_win,
            text="💡 提示：每页 A4 放置 2 张卡片。您可以拖动排序或删除卡片。",
            font=("Microsoft YaHei UI", 9),
            foreground="gray",
        )
        top_tip.pack(anchor=tk.W, padx=15, pady=(10, 5))

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
            for widget in scroll_frame.winfo_children():
                widget.destroy()

            if not self.processed_records:
                ttk.Label(
                    scroll_frame, text="暂无卡片", font=("Microsoft YaHei UI", 11)
                ).pack(pady=30)
                self.lbl_status.config(text="当前已就绪: 0 张")
                return

            self.lbl_status.config(
                text=f"当前已就绪: {len(self.processed_records)} 张"
            )

            manager_win.thumbnails = []

            for idx, item in enumerate(self.processed_records):
                page_num = (idx // 2) + 1
                slot_name = "【正面/上部】" if (idx % 2 == 0) else "【背面/下部】"

                if idx % 2 == 0:
                    group_frame = ttk.Frame(scroll_frame)
                    group_frame.pack(fill=tk.X, pady=(15, 5), padx=5)
                    ttk.Label(
                        group_frame,
                        text=f"📄 PDF 第 {page_num} 页",
                        font=("Microsoft YaHei UI", 10, "bold"),
                        foreground="#0055AA",
                    ).pack(side=tk.LEFT)
                    ttk.Separator(group_frame, orient="horizontal").pack(
                        side=tk.LEFT, fill=tk.X, expand=True, padx=10
                    )

                row_frame = ttk.Frame(
                    scroll_frame, padding=6, relief="groove", borderwidth=1
                )
                row_frame.pack(fill=tk.X, pady=3, padx=5)

                lbl_pos = ttk.Label(
                    row_frame,
                    text=slot_name,
                    width=13,
                    font=("Microsoft YaHei UI", 9, "bold"),
                    foreground="#333333",
                )
                lbl_pos.pack(side=tk.LEFT, padx=2)

                thumb_bgr = cv2.resize(item["img"], (70, 44))
                thumb_rgb = cv2.cvtColor(thumb_bgr, cv2.COLOR_BGR2RGB)
                thumb_pil = Image.fromarray(thumb_rgb)
                thumb_tk = ImageTk.PhotoImage(thumb_pil)
                manager_win.thumbnails.append(thumb_tk)

                lbl_thumb = ttk.Label(row_frame, image=thumb_tk)
                lbl_thumb.pack(side=tk.LEFT, padx=5)

                info_text = f"{item['name']}\n尺寸: {item['w']}mm x {item['h']}mm"
                lbl_info = ttk.Label(
                    row_frame, text=info_text, font=("Microsoft YaHei UI", 9)
                )
                lbl_info.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

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
