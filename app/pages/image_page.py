"""图片与颜色页：压缩、缩放、变换、格式转换、取色与配色。"""
from __future__ import annotations

import colorsys
import os
import random

from PIL import Image, ImageFilter, ImageOps
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit,
                               QSpinBox, QComboBox, QCheckBox, QSlider, QFileDialog, QLabel)

from ..glass import (PageScaffold, GlassCard, GlassButton, label, copy_button, divider, notify)
from ..utils import pil_to_pixmap, human_bytes, set_clipboard


class ColorSwatch(QWidget):
    clicked = Signal(str)

    def __init__(self, hex_color: str, size: int = 36, parent=None):
        super().__init__(parent)
        self._hex = hex_color
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{hex_color} · 点击复制")

    def color(self) -> str:
        return self._hex

    def set_color(self, hex_color: str):
        self._hex = hex_color
        self.setToolTip(f"{hex_color} · 点击复制")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setBrush(QColor(self._hex))
        p.setPen(QPen(QColor(255, 255, 255, 170), 1))
        p.drawRoundedRect(rect, 9, 9)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._hex)


class PreviewLabel(QLabel):
    clicked_pixel = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(280)
        self.setText("打开一张图片后在此预览\n点击图片任意位置可拾取颜色")
        self.setStyleSheet("background: rgba(128,140,170,0.13); "
                           "border: 1px solid rgba(255,255,255,0.28); "
                           "border-radius: 14px; padding: 8px;")
        self._src = None
        self._scale = 1.0
        self._offx = 0.0
        self._offy = 0.0

    def set_image(self, img: Image.Image):
        self._src = img.copy()
        self._render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def _render(self):
        if self._src is None:
            return
        pm = pil_to_pixmap(self._src)
        shown = pm.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(shown)
        self._scale = shown.width() / max(1, self._src.width)
        self._offx = (self.width() - shown.width()) / 2
        self._offy = (self.height() - shown.height()) / 2

    def mousePressEvent(self, event):
        if self._src is None:
            return
        pos = event.position().toPoint()
        x = int((pos.x() - self._offx) / max(self._scale, 1e-6))
        y = int((pos.y() - self._offy) / max(self._scale, 1e-6))
        if 0 <= x < self._src.width and 0 <= y < self._src.height:
            self.clicked_pixel.emit(x, y)


def _hex_of(rgb) -> str:
    r, g, b = rgb[0], rgb[1], rgb[2]
    return f"#{r:02X}{g:02X}{b:02X}"


def _describe(hex_color: str) -> str:
    c = QColor(hex_color)
    r, g, b = c.red(), c.green(), c.blue()
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return (f"HEX  {hex_color.upper()}\n"
            f"RGB  {r}, {g}, {b}\n"
            f"HSL  {h * 360:.0f}°, {s * 100:.0f}%, {l * 100:.0f}%\n"
            f"HSV  {c.hue():.0f}°")


class ImagePage(PageScaffold):
    PRESET = ["#4A8BFF", "#8B6BFF", "#FF7AA8", "#FFB547", "#38C6B4", "#5FD37D",
              "#FF6B6B", "#2F3B57", "#F7F9FF", "#A8D8FF", "#FFD6A5", "#C9B6FF"]

    def __init__(self, parent=None):
        super().__init__("图片与颜色", "图片压缩 / 缩放 / 格式转换 · 屏幕取色与配色方案", parent)
        self._img: Image.Image | None = None
        self._original: Image.Image | None = None
        self._path = ""

        work = GlassCard("图片工作台", "所有处理都在本地内存完成，点击「保存结果」才会写入磁盘", spacing=12)
        split = QHBoxLayout()
        split.setSpacing(16)

        left = QVBoxLayout()
        self._preview = PreviewLabel()
        left.addWidget(self._preview, 1)
        self._img_info = label("尚未打开图片", 9, False, True)
        left.addWidget(self._img_info)
        split.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(10)
        open_btn = GlassButton("打开图片", primary=True)
        open_btn.clicked.connect(self._open_image)
        right.addWidget(open_btn)

        right.addWidget(label("基础变换", 10, True))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (text, fn) in enumerate([
            ("灰度", self._gray), ("反色", self._invert),
            ("水平翻转", self._flip_h), ("垂直翻转", self._flip_v),
            ("旋转 90°", self._rotate), ("锐化", self._sharpen),
            ("柔和模糊", self._blur), ("还原原图", self._reset),
        ]):
            b = GlassButton(text)
            b.setFixedHeight(32)
            b.clicked.connect(fn)
            grid.addWidget(b, i // 2, i % 2)
        right.addLayout(grid)

        right.addWidget(divider())
        right.addWidget(label("尺寸缩放", 10, True))
        size_row = QHBoxLayout()
        self._w = QSpinBox()
        self._h = QSpinBox()
        for sb in (self._w, self._h):
            sb.setRange(1, 20000)
            sb.setValue(800)
            sb.setFixedWidth(88)
        self._keep_ratio = QCheckBox("保持比例")
        self._keep_ratio.setChecked(True)
        size_row.addWidget(label("宽", 9))
        size_row.addWidget(self._w)
        size_row.addWidget(label("高", 9))
        size_row.addWidget(self._h)
        size_row.addStretch(1)
        right.addLayout(size_row)
        right.addWidget(self._keep_ratio)
        resize_btn = GlassButton("应用缩放")
        resize_btn.setFixedHeight(32)
        resize_btn.clicked.connect(self._resize)
        right.addWidget(resize_btn)

        right.addWidget(divider())
        right.addWidget(label("输出设置", 10, True))
        out_row = QHBoxLayout()
        self._fmt = QComboBox()
        self._fmt.addItems(["PNG", "JPEG", "WEBP", "BMP"])
        out_row.addWidget(self._fmt)
        out_row.addStretch(1)
        out_row.addWidget(label("质量", 9))
        self._quality = QSlider(Qt.Orientation.Horizontal)
        self._quality.setRange(10, 100)
        self._quality.setValue(85)
        self._quality.setFixedWidth(110)
        out_row.addWidget(self._quality)
        right.addLayout(out_row)
        save_btn = GlassButton("保存结果", primary=True)
        save_btn.clicked.connect(self._save)
        right.addWidget(save_btn)
        right.addStretch(1)
        split.addLayout(right, 2)
        work.add_layout(split)
        self.add_card(work)

        color = GlassCard("取色与颜色换算", "点击上方图片任意像素即可拾取颜色", spacing=12)
        crow = QHBoxLayout()
        crow.setSpacing(16)

        c1 = QVBoxLayout()
        c1.addWidget(label("拾取的颜色", 10, True))
        pick_row = QHBoxLayout()
        self._pick_swatch = ColorSwatch("#4A8BFF", 62)
        pick_row.addWidget(self._pick_swatch)
        self._pick_text = label("尚未取色", 10)
        pick_row.addWidget(self._pick_text, 1)
        c1.addLayout(pick_row)
        c1.addLayout(self._button_row(copy_button(self,
                                                  lambda: self._pick_text.text().split("\n")[0].replace("HEX  ", ""),
                                                  "复制 HEX")))
        crow.addLayout(c1, 1)

        c2 = QVBoxLayout()
        c2.addWidget(label("HEX 颜色换算", 10, True))
        hex_row = QHBoxLayout()
        self._hex_input = QLineEdit()
        self._hex_input.setPlaceholderText("#4A8BFF 或 4A8BFF")
        self._hex_input.setText("#4A8BFF")
        self._hex_input.textChanged.connect(self._convert_hex)
        hex_row.addWidget(self._hex_input, 1)
        self._hex_swatch = ColorSwatch("#4A8BFF", 34)
        hex_row.addWidget(self._hex_swatch)
        c2.addLayout(hex_row)
        self._hex_out = label("", 9)
        c2.addWidget(self._hex_out)
        crow.addLayout(c2, 1)
        color.add_layout(crow)

        color.add(divider())
        color.add(label("调色板 · 点击色块复制色值", 10, True))
        self._palette = QHBoxLayout()
        self._palette.setSpacing(10)
        self._palette.addStretch(1)
        color.add_layout(self._palette)
        rand = GlassButton("生成随机配色")
        rand.clicked.connect(self._random_palette)
        color.add_layout(self._button_row(rand))
        self.add_card(color)
        self.add_stretch(1)

        self._preview.clicked_pixel.connect(self._pick)
        self._set_palette(self.PRESET)
        self._convert_hex()

    def _button_row(self, *buttons) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        for b in buttons:
            row.addWidget(b)
        return row

    # ---------------------------------------------------------------- 图片操作
    def _require_image(self) -> bool:
        if self._img is None:
            notify(self, "请先打开一张图片")
            return False
        return True

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff);;所有文件 (*.*)")
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
            self._original = img.copy()
            self._img = img.copy()
            self._path = path
            self._w.setValue(img.width)
            self._h.setValue(img.height)
            self._preview.set_image(self._img)
            self._update_info()
            notify(self, f"已打开 {os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            notify(self, f"打开图片失败：{exc}")

    def _update_info(self):
        if self._img is None:
            return
        size = os.path.getsize(self._path) if self._path and os.path.isfile(self._path) else 0
        self._img_info.setText(
            f"{os.path.basename(self._path)}  ·  {self._img.width} × {self._img.height} px  ·  "
            f"模式 {self._img.mode}  ·  文件 {human_bytes(size)}")

    def _apply(self, img: Image.Image):
        self._img = img
        self._preview.set_image(self._img)
        self._w.setValue(img.width)
        self._h.setValue(img.height)

    def _gray(self):
        if self._require_image():
            self._apply(ImageOps.grayscale(self._img.convert("RGB")).convert("RGB"))

    def _invert(self):
        if self._require_image():
            self._apply(ImageOps.invert(self._img.convert("RGB")))

    def _flip_h(self):
        if self._require_image():
            self._apply(ImageOps.mirror(self._img))

    def _flip_v(self):
        if self._require_image():
            self._apply(ImageOps.flip(self._img))

    def _rotate(self):
        if self._require_image():
            self._apply(self._img.transpose(Image.Transpose.ROTATE_270))

    def _sharpen(self):
        if self._require_image():
            self._apply(self._img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140)))

    def _blur(self):
        if self._require_image():
            self._apply(self._img.filter(ImageFilter.GaussianBlur(radius=2)))

    def _reset(self):
        if self._original is not None:
            self._apply(self._original.copy())
            notify(self, "已还原为打开时的原图")

    def _resize(self):
        if not self._require_image():
            return
        w, h = self._w.value(), self._h.value()
        if self._keep_ratio.isChecked():
            ratio = self._img.width / self._img.height
            h = int(w / ratio)
        try:
            self._apply(self._img.resize((w, h), Image.Resampling.LANCZOS))
        except Exception as exc:  # noqa: BLE001
            notify(self, f"缩放失败：{exc}")

    def _save(self):
        if not self._require_image():
            return
        fmt = self._fmt.currentText().lower()
        ext = "jpg" if fmt == "jpeg" else fmt
        default = os.path.splitext(os.path.basename(self._path or "image"))[0] + "_out." + ext
        path, _ = QFileDialog.getSaveFileName(self, "保存图片", default, f"{fmt.upper()} 图片 (*.{ext})")
        if not path:
            return
        if not path.lower().endswith("." + ext):
            path += "." + ext
        try:
            img = self._img
            if fmt in ("jpeg", "bmp"):
                img = img.convert("RGB")
            kwargs = {}
            if fmt in ("jpeg", "webp"):
                kwargs["quality"] = self._quality.value()
            img.save(path, format=self._fmt.currentText(), **kwargs)
            notify(self, f"已保存 {os.path.basename(path)}（{human_bytes(os.path.getsize(path))}）")
        except Exception as exc:  # noqa: BLE001
            notify(self, f"保存失败：{exc}")

    # ---------------------------------------------------------------- 颜色
    def _pick(self, x: int, y: int):
        if self._img is None:
            return
        try:
            px = self._img.convert("RGBA").getpixel((x, y))
            hexc = _hex_of(px)
            self._pick_swatch.set_color(hexc)
            self._pick_text.setText(_describe(hexc) + f"\n坐标  {x}, {y}")
            self._hex_input.setText(hexc)
        except Exception as exc:  # noqa: BLE001
            notify(self, f"取色失败：{exc}")

    def _convert_hex(self, *_):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
            self._hex_out.setText("请输入有效的 6 位 HEX 颜色值，例如 #4A8BFF")
            return
        hexc = "#" + text.upper()
        self._hex_swatch.set_color(hexc)
        self._hex_out.setText(_describe(hexc))

    def _set_palette(self, colors):
        while self._palette.count():
            item = self._palette.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for c in colors:
            sw = ColorSwatch(c, 38)
            sw.clicked.connect(self._on_swatch)
            self._palette.addWidget(sw)
        self._palette.addStretch(1)

    def _on_swatch(self, hexc: str):
        set_clipboard(hexc)
        self._hex_input.setText(hexc)
        notify(self, f"已复制 {hexc}")

    def _random_palette(self):
        base = random.random()
        colors = []
        for i in range(12):
            h = (base + i / 12) % 1.0
            s = 0.55 + random.random() * 0.3
            l = 0.5 + random.random() * 0.18
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            colors.append(_hex_of((int(r * 255), int(g * 255), int(b * 255))))
        self._set_palette(colors)
        notify(self, "已生成一组和谐配色")
