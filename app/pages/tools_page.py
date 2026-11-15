"""实用工具页：二维码生成/解析、转盘决定、局域网扫描、磁盘健康、PDF/PPT/PPTX 互转。"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPointF, QRectF, QUrl
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QDesktopServices, QPixmap)
from PySide6.QtWidgets import (QTabWidget, QComboBox, QSpinBox, QSlider, QTextEdit, QLineEdit,
                               QLabel, QFileDialog, QApplication, QColorDialog, QListWidget,
                               QHBoxLayout, QVBoxLayout, QWidget, QSizePolicy)

from ..glass import PageScaffold, GlassCard, label, divider, notify
from ..utils import Worker, human_bytes, pil_to_pixmap, pixmap_to_pil
from .. import extra
from .. import system_extra as se
from ..extra import WHEEL_COLORS
from .image_page import ColorSwatch
from .common import (on_click, changed, tab_container, editor, row, make_table, fill_table,
                     btn, pick_file, export_text, copy_text, start_worker, mono, field)


# ================================================================ 转盘控件
class WheelWidget(QWidget):
    """自绘彩色转盘：扇区随角度旋转，顶部固定指针指示结果。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._options: list[str] = []
        self._angle = 0.0
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_options(self, options: list[str]):
        self._options = [o for o in options if o.strip()][:16]
        self.update()

    def angle(self) -> float:
        return self._angle

    def set_angle(self, value: float):
        self._angle = float(value) % 360.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w - 24, h - 24)
        r = side / 2.0
        cx, cy = w / 2.0, h / 2.0
        box = QRectF(cx - r, cy - r, r * 2, r * 2)

        # 外圈阴影与底盘
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawEllipse(QRectF(box.adjusted(-7, -7, 7, 7)))
        p.setBrush(QColor(255, 255, 255, 225))
        p.drawEllipse(box.adjusted(-3, -3, 3, 3))

        if not self._options:
            p.setPen(QPen(QColor("#5b6b88"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(box)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, "请在右侧输入选项")
            p.end()
            return

        n = len(self._options)
        seg = 360.0 / n
        for i, opt in enumerate(self._options):
            start = 90.0 + self._angle + i * seg
            color = QColor(WHEEL_COLORS[i % len(WHEEL_COLORS)])
            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor(255, 255, 255, 170), 1.4))
            p.drawPie(box, int(start * 16), int(seg * 16))

        # 扇区文字（水平绘制，不随转盘倾斜）
        f = self.font()
        f.setPointSize(10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        for i, opt in enumerate(self._options):
            mid = 90.0 + self._angle + (i + 0.5) * seg
            import math
            rad = math.radians(mid)
            tx = cx + r * 0.60 * math.cos(rad)
            ty = cy - r * 0.60 * math.sin(rad)
            text = opt if len(opt) <= 9 else opt[:8] + "…"
            tw = 116
            p.drawText(QRectF(tx - tw / 2, ty - 14, tw, 28),
                       Qt.AlignmentFlag.AlignCenter, text)

        # 中心轴
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(cx, cy), 30, 30)
        p.setBrush(QColor("#3b7dff"))
        p.drawEllipse(QPointF(cx, cy), 22, 22)
        p.setPen(QColor("#ffffff"))
        p.setFont(f)
        p.drawText(QRectF(cx - 22, cy - 12, 44, 24), Qt.AlignmentFlag.AlignCenter, "GO")

        # 顶部固定指针（正上方，向下指）
        from PySide6.QtGui import QPolygonF
        tri = QPolygonF([QPointF(cx - 13, 4), QPointF(cx + 13, 4), QPointF(cx, 30)])
        p.setBrush(QColor("#ff4d6d"))
        p.setPen(QPen(QColor("#ffffff"), 1.6))
        p.drawPolygon(tri)
        p.end()


class _Bridge(QObject):
    """后台线程向 UI 汇报进度的信号桥（Qt 自动跨线程排队）。"""
    progress = Signal(int, int)
    doc_progress = Signal(int, int)


# ================================================================ 页面
class ToolsPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("实用工具", "二维码 · 转盘决定 · 局域网扫描 · 磁盘健康 · 文档格式转换", parent)
        self._workers = []
        self._qr_image = None
        self._qr_fg, self._qr_bg = "#172132", "#FFFFFF"
        self._wheel_angle = 0.0
        self._spin_start = 0.0
        self._spin_final = 0.0
        self._spin_t0 = 0
        self._spin_target: tuple[int, str] | None = None
        self._scan_stop = False
        self._scan_rows = []
        self._doc_result = None
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_scan_progress)
        self._bridge.doc_progress.connect(self._on_doc_progress)

        self._qr_timer = QTimer(self)
        self._qr_timer.setSingleShot(True)
        self._qr_timer.setInterval(320)
        self._qr_timer.timeout.connect(self._render_qr)
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(16)
        self._spin_timer.timeout.connect(self._spin_step)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._qr_tab(), "  二维码 & 转盘  ")
        tabs.addTab(self._system_tab(), "  磁盘 & 局域网  ")
        tabs.addTab(self._doc_tab(), "  文档格式转换  ")
        self.add_widget(tabs, 1)

    # ================================================================ Tab 1
    def _qr_tab(self):
        w, lay = tab_container()
        pair = QHBoxLayout()
        pair.setSpacing(16)
        pair.addWidget(self._qr_card(), 1)
        pair.addWidget(self._wheel_card(), 1)
        lay.addLayout(pair)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- 二维码
    def _qr_card(self):
        card = GlassCard("二维码 生成 / 解析", "离线生成 + 本地图片 / 剪贴板图片解析，不上传任何数据", spacing=10)
        inner = QTabWidget()
        inner.setDocumentMode(True)
        inner.addTab(self._qr_generate_tab(), "  生成  ")
        inner.addTab(self._qr_decode_tab(), "  解析  ")
        card.add(inner)
        return card

    def _qr_generate_tab(self):
        from .common import plain_tab
        w, lay = plain_tab()
        self._qr_text = editor("输入网址、文本、Wi-Fi 信息…", 76)
        self._qr_text.setPlainText("https://example.com")
        changed(self._qr_text, "textChanged", self._qr_timer.start)
        lay.addWidget(self._qr_text)
        self._qr_level = QComboBox()
        self._qr_level.addItems(extra.QR_LEVELS)
        self._qr_level.setCurrentIndex(1)
        self._qr_level.setMinimumWidth(150)
        self._qr_size = QSlider(Qt.Orientation.Horizontal)
        self._qr_size.setRange(4, 14)
        self._qr_size.setValue(8)
        self._qr_size.setFixedWidth(110)
        fg_btn = btn("前景色")
        bg_btn = btn("背景色")
        on_click(fg_btn, self._pick_fg)
        on_click(bg_btn, self._pick_bg)
        changed(self._qr_level, "currentIndexChanged", self._qr_timer.start)
        changed(self._qr_size, "valueChanged", self._qr_timer.start)
        lay.addLayout(row(self._qr_level, self._qr_size, fg_btn, bg_btn, stretch=False))
        self._fg_swatch = ColorSwatch(self._qr_fg, 26)
        self._bg_swatch = ColorSwatch(self._qr_bg, 26)
        lay.addLayout(row(label("前景", 9), self._fg_swatch, 12,
                          label("背景", 9), self._bg_swatch, stretch=False))
        self._qr_preview = QLabel("生成中…")
        self._qr_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_preview.setMinimumHeight(200)
        self._qr_preview.setStyleSheet("background: rgba(255,255,255,0.55); border-radius: 12px; padding: 10px;")
        lay.addWidget(self._qr_preview)
        save = btn("保存 PNG")
        on_click(save, self._save_qr)
        lay.addLayout(row(save))
        self._qr_timer.start()
        return w

    def _qr_decode_tab(self):
        from .common import plain_tab
        w, lay = plain_tab()
        choose = btn("选择图片")
        paste = btn("从剪贴板读取")
        on_click(choose, self._choose_qr_image)
        on_click(paste, self._paste_qr_image)
        lay.addLayout(row(choose, paste))
        self._qr_src_preview = QLabel("待解析的图片预览")
        self._qr_src_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_src_preview.setMinimumHeight(150)
        self._qr_src_preview.setStyleSheet("background: rgba(255,255,255,0.45); border-radius: 12px; padding: 8px;")
        lay.addWidget(self._qr_src_preview)
        self._qr_result = editor("解析结果会显示在这里…", 130, readonly=True)
        lay.addWidget(self._qr_result)
        c = btn("复制内容")
        o = btn("打开链接")
        on_click(c, lambda: copy_text(self, self._qr_result.toPlainText()))
        on_click(o, self._open_qr_link)
        lay.addLayout(row(c, o))
        lay.addWidget(label("支持 QR Code、EAN、Code128、DataMatrix 等常见格式；"
                            "由 zxing-cpp 本地解码，OpenCV 作为备选引擎。", 9, False, True))
        return w

    def _render_qr(self):
        text = self._qr_text.toPlainText().strip()
        if not text:
            self._qr_preview.setText("请输入要编码的内容")
            self._qr_image = None
            return
        try:
            img = extra.make_qr(text, self._qr_level.currentText(), self._qr_size.value(),
                                self._qr_fg, self._qr_bg)
            self._qr_image = img
            pix = pil_to_pixmap(img)
            self._qr_preview.setPixmap(pix.scaled(190, 190, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.FastTransformation))
        except Exception as exc:  # noqa: BLE001
            self._qr_preview.setText(f"生成失败：{exc}")

    def _pick_fg(self):
        c = QColorDialog.getColor(QColor(self._qr_fg), self, "选择二维码前景色")
        if c.isValid():
            self._qr_fg = c.name()
            self._fg_swatch.set_color(self._qr_fg)
            self._render_qr()

    def _pick_bg(self):
        c = QColorDialog.getColor(QColor(self._qr_bg), self, "选择二维码背景色")
        if c.isValid():
            self._qr_bg = c.name()
            self._bg_swatch.set_color(self._qr_bg)
            self._render_qr()

    def _save_qr(self):
        if self._qr_image is None:
            notify(self, "请先生成二维码")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存二维码", "qrcode.png", "PNG 图片 (*.png)")
        if path:
            self._qr_image.save(path)
            notify(self, f"已保存 {os.path.basename(path)}")

    def _choose_qr_image(self):
        path = pick_file(self, "选择含二维码的图片", "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        if path:
            self._decode_qr_path(path)

    def _paste_qr_image(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            notify(self, "剪贴板中没有图片")
            return
        self._show_qr_source(QPixmap.fromImage(img))
        try:
            self._show_qr_results(extra.decode_qr(pixmap_to_pil(QPixmap.fromImage(img))))
        except Exception as exc:  # noqa: BLE001
            self._qr_result.setPlainText(f"解析失败：{exc}")

    def _decode_qr_path(self, path: str):
        try:
            from PIL import Image
            img = Image.open(path)
            self._show_qr_source(pil_to_pixmap(img))
            self._show_qr_results(extra.decode_qr(img))
        except Exception as exc:  # noqa: BLE001
            self._qr_result.setPlainText(f"解析失败：{exc}")

    def _show_qr_source(self, pix: QPixmap):
        self._qr_src_preview.setPixmap(
            pix.scaled(220, 140, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation))

    def _show_qr_results(self, results: list[dict]):
        if not results:
            self._qr_result.setPlainText("未识别到条码 / 二维码。请换一张更清晰、无遮挡的图片。")
            self._qr_content = ""
            return
        parts = [f"识别到 {len(results)} 个码：", "=" * 50]
        for i, r in enumerate(results, 1):
            parts.append(f"[{i}] 格式 {r['format']}  ·  引擎 {r['engine']}\n{r['text']}\n")
        self._qr_result.setPlainText("\n".join(parts))
        self._qr_content = results[0]["text"]

    def _open_qr_link(self):
        text = (getattr(self, "_qr_content", "") or self._qr_result.toPlainText()).strip()
        url = text if text.startswith(("http://", "https://")) else "https://" + text
        if not text or " " in url:
            notify(self, "解析结果不是网址")
            return
        QDesktopServices.openUrl(QUrl(url))

    # ---------------------------------------------------------------- 转盘
    def _wheel_card(self):
        card = GlassCard("转盘决定", "选择困难症救星 · 本地随机，结果公平可复核", spacing=10)
        self._wheel = WheelWidget()
        card.add(self._wheel)
        self._wheel_result = label("等待开始…", 13, True)
        self._wheel_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.add(self._wheel_result)
        self._wheel_options = editor("每行一个选项，最多 16 个…", 96)
        self._wheel_options.setPlainText("火锅\n烧烤\n日料\n沙拉\n奶茶\n回家吃")
        changed(self._wheel_options, "textChanged", self._sync_wheel_options)
        card.add(self._wheel_options)
        spin = btn("开始转动", True)
        on_click(spin, self._start_spin)
        card.add_layout(row(spin, btn("复制结果")))
        acts = card.body().itemAt(card.body().count() - 1).layout()
        on_click(acts.itemAt(1).widget(), lambda: copy_text(self, self._wheel_result.text()))
        self._wheel_history = QListWidget()
        self._wheel_history.setMaximumHeight(96)
        card.add(label("开奖记录", 9, False, True))
        card.add(self._wheel_history)
        self._sync_wheel_options()
        return card

    def _sync_wheel_options(self):
        self._wheel.set_options(self._wheel_options.toPlainText().splitlines())

    def _start_spin(self):
        opts = [o.strip() for o in self._wheel_options.toPlainText().splitlines() if o.strip()]
        if not opts:
            notify(self, "请至少输入一个选项")
            return
        if self._spin_timer.isActive():
            return
        idx, text = extra.wheel_pick(opts)
        self._spin_target = (idx, text)
        base = self._wheel.angle()
        target = extra.wheel_angle_for(idx, len(opts))
        delta = (target - (base % 360.0)) % 360.0 + 360.0 * 6
        self._spin_start, self._spin_final = base, base + delta
        self._spin_t0 = datetime.now().timestamp() * 1000
        self._wheel_result.setText("转动中…")
        self._spin_timer.start()

    def _spin_step(self):
        elapsed = datetime.now().timestamp() * 1000 - self._spin_t0
        duration = 4200.0
        t = min(1.0, elapsed / duration)
        eased = 1 - (1 - t) ** 3
        self._wheel.set_angle(self._spin_start + (self._spin_final - self._spin_start) * eased)
        if t >= 1.0:
            self._spin_timer.stop()
            idx, text = self._spin_target
            self._wheel.set_angle(self._spin_final)
            self._wheel_result.setText(f"结果：{text}")
            self._wheel_history.insertItem(0, f"{datetime.now():%H:%M:%S}   →   {text}")
            notify(self, f"转盘结果：{text}")

    # ================================================================ Tab 2
    def _system_tab(self):
        w, lay = tab_container()
        lay.addWidget(self._disk_card())
        lay.addWidget(self._lan_card())
        lay.addStretch(1)
        return w

    def _disk_card(self):
        card = GlassCard("磁盘健康状态查看器", "分区容量、S.M.A.R.T. 概览与磁盘 I/O 统计", spacing=12)
        refresh = btn("刷新状态", True)
        self._disk_time = label("", 9, False, True)
        on_click(refresh, self._refresh_disk)
        card.add_layout(row(refresh, self._disk_time))
        self._part_table = make_table(["设备", "挂载点", "文件系统", "总容量", "已用", "可用", "使用率"])
        card.add(self._part_table)
        self._phys_table = make_table(["物理磁盘", "介质", "健康状态", "容量", "温度", "通电时间"])
        card.add(self._phys_table)
        self._io_info = mono("—")
        card.add(self._io_info)
        self._disk_notes = label("", 9, False, True)
        card.add(self._disk_notes)
        self._refresh_disk()
        return card

    def _refresh_disk(self):
        self._disk_time.setText("读取中…")
        start_worker(self, se.disk_health, (), self._on_disk)

    def _on_disk(self, data: dict):
        parts = data["partitions"]
        fill_table(self._part_table, [
            [p["device"], p["mount"], p["fstype"], human_bytes(p["total"]),
             human_bytes(p["used"]), human_bytes(p["free"]), f"{p['percent']:.1f}%"]
            for p in parts[:15]])
        part_note = f"共 {len(parts)} 个分区，表格显示前 15 个  ·  " if len(parts) > 15 else ""
        fill_table(self._phys_table, [
            [p["name"], p["media"], p["health"], human_bytes(p["size"]), p["temp"], p["power_on"]]
            for p in data["physical"]])
        io = data["io"]
        if io:
            self._io_info.setText(
                f"累计读取 {human_bytes(io.get('read_bytes', 0))}  ·  "
                f"写入 {human_bytes(io.get('write_bytes', 0))}  ·  "
                f"读 {io.get('read_count', 0)} 次  ·  写 {io.get('write_count', 0)} 次")
        else:
            self._io_info.setText("当前平台未提供磁盘 I/O 计数器")
        self._disk_notes.setText(
            f"平台 {data['platform']}  ·  " + part_note
            + ("；".join(data["notes"]) if data["notes"] else "状态读取正常")
            + "  ·  Windows 端由 PowerShell / WMI 读取健康与温度，Linux 端需 smartctl（通常需管理员权限）")
        self._disk_time.setText(f"更新于 {datetime.now():%H:%M:%S}")

    # ---------------------------------------------------------------- 局域网
    def _lan_card(self):
        card = GlassCard("局域网设备扫描器", "ping 探测 + ARP 表 + 反向 DNS，找出网段内在线设备", spacing=12)
        self._lan_net = QComboBox()
        self._lan_net.setEditable(True)
        self._lan_net.setMinimumWidth(290)
        for n in se.local_networks():
            self._lan_net.addItem(f"{n['network']}   ({n['interface']} · 本机 {n['ip']})", n["network"])
        if self._lan_net.count() == 0:
            self._lan_net.addItem("192.168.1.0/24")
        self._lan_threads = QSpinBox()
        self._lan_threads.setRange(8, 96)
        self._lan_threads.setValue(64)
        self._lan_threads.setPrefix("并发 ")
        scan = btn("开始扫描", True)
        stop = btn("停止")
        on_click(scan, self._start_scan)
        on_click(stop, self._stop_scanning)
        card.add_layout(row(self._lan_net, self._lan_threads, scan, stop))
        self._lan_progress = label("就绪 · 扫描通常耗时 5~20 秒", 9, False, True)
        card.add(self._lan_progress)
        self._lan_table = make_table(["IP 地址", "MAC 地址", "厂商", "主机名", "状态"])
        card.add(self._lan_table)
        exp = btn("导出 CSV")
        on_click(exp, self._export_lan)
        card.add_layout(row(exp))
        fill_table(self._lan_table, [])
        return card

    def _start_scan(self):
        text = self._lan_net.currentText().strip()
        network = text.split("(")[0].strip() if "(" in text else text
        try:
            import ipaddress
            ipaddress.ip_network(network, strict=False)
        except ValueError as exc:
            self._lan_progress.setText(f"网段格式错误：{exc}")
            return
        self._scan_stop = False
        self._lan_progress.setText("扫描中…")
        start_worker(self, se.scan_lan,
                      (network, self._bridge.progress.emit, lambda: self._scan_stop,
                       self._lan_threads.value()),
                      self._on_scan_done)

    def _stop_scanning(self):
        self._scan_stop = True
        self._lan_progress.setText("正在停止…")

    def _on_scan_progress(self, done, total):
        self._lan_progress.setText(f"扫描进度 {done} / {total}")

    def _on_scan_done(self, rows):
        self._scan_rows = rows
        fill_table(self._lan_table, [
            [r["ip"], r["mac"], r["vendor"], r["hostname"], r["status"]] for r in rows])
        self._lan_progress.setText(f"扫描完成 · 发现 {len(rows)} 台在线设备"
                                   + ("（已手动停止）" if self._scan_stop else ""))

    def _export_lan(self):
        lines = ["IP,MAC,厂商,主机名,状态"] + [
            ",".join(f'"{r[k].replace(chr(34), chr(39))}"'
                     for k in ("ip", "mac", "vendor", "hostname", "status"))
            for r in self._scan_rows]
        export_text(self, "\n".join(lines), "lumibox_lan_devices.csv")

    # ================================================================ Tab 3
    def _doc_tab(self):
        w, lay = tab_container()
        card = GlassCard("PDF / PPT / PPTX 互转", "本地离线转换，文件不会上传到任何服务器", spacing=12)
        self._doc_src = field("", "选择 .pdf / .ppt / .pptx 源文件")
        self._doc_src.setReadOnly(True)
        choose = btn("选择文件")
        on_click(choose, self._choose_doc)
        card.add_layout(row(choose, self._doc_src, stretch=False))
        self._doc_target = QComboBox()
        self._doc_target.setMinimumWidth(180)
        self._doc_out = field("", "输出目录（留空则与源文件同目录）")
        outdir_btn = btn("选择目录")
        on_click(outdir_btn, self._choose_doc_outdir)
        card.add_layout(row(label("目标格式", 10, True), self._doc_target, 14,
                            label("输出目录", 10, True), self._doc_out, outdir_btn,
                            stretch=False))
        changed(self._doc_target, "currentIndexChanged", self._sync_doc_hint)
        conv = btn("开始转换", True)
        on_click(conv, self._start_convert)
        open_btn = btn("打开输出目录")
        on_click(open_btn, self._open_doc_result)
        card.add_layout(row(conv, open_btn))
        self._doc_log = editor("转换日志与结果…", 150, readonly=True)
        card.add(self._doc_log)
        caps = se.doc_capabilities()
        self._doc_caps = mono("本机能力：" + "   ".join(
            f"{k} {'✓' if v else '✗'}" for k, v in caps.items()))
        card.add(self._doc_caps)
        self._doc_hint = label("", 9, False, True)
        card.add(self._doc_hint)
        card.add(label("· PDF → PPTX：每页渲染为高清图片嵌入，版式完全保真（文字不可编辑）。", 9))
        card.add(label("· PPTX → PDF：优先用本机 LibreOffice；未安装时生成「文本版」PDF（含中文）。", 9))
        card.add(label("· PPT（旧二进制）/ PPTX → PPT / PDF：需要本机安装免费的 LibreOffice。", 9))
        card.add(label("· 转换由 PyMuPDF + python-pptx + Pillow + reportlab 完成，全部离线。", 9, False, True))
        lay.addWidget(card)
        lay.addStretch(1)
        self._sync_doc_target()
        return w

    def _sync_doc_target(self):
        ext = os.path.splitext(self._doc_src.text().strip())[1].lower()
        self._doc_target.clear()
        self._doc_target.addItems(se.DOC_MATRIX.get(ext, ["PDF"]))
        self._sync_doc_hint()

    def _sync_doc_hint(self):
        t = self._doc_target.currentText()
        lo = se.find_libreoffice()
        if t.startswith("PPTX") and self._doc_src.text().lower().endswith(".pdf"):
            self._doc_hint.setText("将使用 PyMuPDF 逐页渲染，输出 PPTX（无需 LibreOffice）。")
        elif t.startswith("PDF") and self._doc_src.text().lower().endswith(".pptx") and not lo:
            self._doc_hint.setText("未检测到 LibreOffice，将生成文本版 PDF；安装 LibreOffice 可获得完整版式。")
        elif "LibreOffice" in t or (self._doc_src.text().lower().endswith(".ppt")):
            self._doc_hint.setText("需要本机 LibreOffice：" + ("已检测到 ✓" if lo else "未安装 ✗（请到 libreoffice.org 免费下载）"))
        else:
            self._doc_hint.setText("就绪。")

    def _choose_doc(self):
        path = pick_file(self, "选择要转换的文档",
                         "PDF / PPT / PPTX (*.pdf *.ppt *.pptx);;所有文件 (*)")
        if path:
            self._doc_src.setText(path)
            self._sync_doc_target()
            self._doc_log.setPlainText(f"已选择：{path}\n目标格式：{self._doc_target.currentText()}")

    def _choose_doc_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", "")
        if d:
            self._doc_out.setText(d)

    def _start_convert(self):
        src = self._doc_src.text().strip()
        if not src:
            notify(self, "请先选择源文件")
            return
        target = self._doc_target.currentText()
        outdir = self._doc_out.text().strip() or None
        self._doc_log.setPlainText(f"正在转换 {os.path.basename(src)} → {target} …")
        start_worker(self, se.convert_document,
                      (src, target, outdir, self._bridge.doc_progress.emit), self._on_converted)

    def _on_doc_progress(self, done, total):
        self._doc_log.setPlainText(f"正在处理第 {done} / {total} 页…")

    def _on_converted(self, res: dict):
        self._doc_result = res["path"]
        lines = [f"完成 ✓   {res['path']}", f"转换方式  {res['method']}",
                 f"文件大小  {human_bytes(os.path.getsize(res['path']))}", ""]
        lines += [f"· {n}" for n in res["notes"]]
        self._doc_log.setPlainText("\n".join(lines))
        notify(self, f"转换完成：{os.path.basename(res['path'])}")

    def _open_doc_result(self):
        folder = (os.path.dirname(self._doc_result) if self._doc_result
                  else (self._doc_out.text().strip() or os.path.dirname(self._doc_src.text())))
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            notify(self, "请先完成一次转换")
