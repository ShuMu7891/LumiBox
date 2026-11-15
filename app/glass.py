"""Liquid Glass 控件库：玻璃背景、卡片、按钮、进度条、标题栏、侧边栏、页面骨架。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize
from PySide6.QtGui import (QPainter, QPainterPath, QColor, QPen, QLinearGradient,
                           QRadialGradient, QFontMetrics, QPixmap)
from PySide6.QtWidgets import (QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
                               QSizePolicy, QScrollArea, QFrame, QSizeGrip, QApplication)

from . import theme
from .utils import set_clipboard


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def notify(widget: QWidget, message: str) -> None:
    win = widget.window()
    fn = getattr(win, "notify", None)
    if callable(fn):
        fn(message)


def copy_action(widget: QWidget, text) -> None:
    value = text() if callable(text) else text
    if value is None or value == "":
        notify(widget, "没有可复制的内容")
        return
    set_clipboard(str(value))
    notify(widget, "已复制到剪贴板")


def copy_button(widget: QWidget, text, label: str = "复制") -> "GlassButton":
    btn = GlassButton(label)
    btn.setFixedHeight(30)
    btn.setToolTip("复制到剪贴板")
    btn.clicked.connect(lambda: copy_action(widget, text))
    return btn


def label(text: str, size: int = 10, bold: bool = False, dim: bool = False) -> QLabel:
    lbl = QLabel(text)
    f = theme.app_font(size, bold)
    lbl.setFont(f)
    if dim:
        lbl.setProperty("dim", True)
    lbl.setWordWrap(True)
    return lbl


def divider() -> QFrame:
    line = QFrame()
    line.setProperty("hr", True)
    line.setFixedHeight(1)
    return line


# ---------------------------------------------------------------- 窗口背景
class GlassBackground(QWidget):
    """绘制彩色流体渐变背景、玻璃光斑与窗口投影。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._maximized = False
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(18, 18)

    def set_maximized(self, value: bool):
        self._maximized = value
        m = 0 if value else 14
        lay = self.layout()
        if lay is not None:
            lay.setContentsMargins(m + 1, m + 1, m + 1, m + 1)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        m = 0 if self._maximized else 14
        self._grip.setGeometry(self.width() - m - 20, self.height() - m - 20, 18, 18)

    def paintEvent(self, event):
        t = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QRectF(self.rect())
        m = 0 if self._maximized else 14
        inner = full.adjusted(m, m, -m, -m)
        radius = 0 if self._maximized else 22

        if not self._maximized:
            sr, sg, sb, sa = t["shadow"]
            for i in range(12, 0, -2):
                alpha = max(2, int(sa * (1 - i / 15) + 2))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(sr, sg, sb, alpha))
                p.drawRoundedRect(inner.adjusted(-i, -i, i, i), radius + i, radius + i)

        path = rounded_path(inner, radius)
        p.save()
        p.setClipPath(path)

        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        stops = t["bg_stops"]
        for i, c in enumerate(stops):
            grad.setColorAt(i / max(1, len(stops) - 1), QColor(c))
        p.fillRect(full, grad)

        for rx, ry, rr, col in t["blobs"]:
            cx = inner.left() + rx * inner.width()
            cy = inner.top() + ry * inner.height()
            rad = rr * max(inner.width(), inner.height())
            g = QRadialGradient(QPointF(cx, cy), rad)
            g.setColorAt(0, QColor(*col))
            g.setColorAt(1, QColor(col[0], col[1], col[2], 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, cy), rad, rad)

        # 顶边柔光，制造玻璃厚度
        sheen = QLinearGradient(inner.left(), inner.top(), inner.left(), inner.top() + inner.height() * 0.5)
        sheen.setColorAt(0, QColor(255, 255, 255, 42 if t["dark"] else 70))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(sheen)
        p.drawRect(inner)
        p.restore()

        p.setPen(QPen(QColor(*t["glass_border"]), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


# ---------------------------------------------------------------- 玻璃卡片
class GlassCard(QWidget):
    def __init__(self, title: str = "", subtitle: str = "", radius: float = 20,
                 spacing: int = 12, parent=None):
        super().__init__(parent)
        self._radius = radius
        self._box = QVBoxLayout(self)
        self._box.setContentsMargins(20, 18, 20, 20)
        self._box.setSpacing(spacing)
        self._title_lbl = None
        self._sub_lbl = None
        self._head_actions = None
        if title:
            self.set_header(title, subtitle)

    def set_header(self, title: str, subtitle: str = ""):
        head = QHBoxLayout()
        head.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        self._title_lbl = label(title, 12, True)
        col.addWidget(self._title_lbl)
        if subtitle:
            self._sub_lbl = label(subtitle, 9, False, True)
            col.addWidget(self._sub_lbl)
        head.addLayout(col, 1)
        self._head_actions = QHBoxLayout()
        self._head_actions.setSpacing(8)
        head.addLayout(self._head_actions)
        self._box.insertLayout(0, head)

    def header_actions(self) -> QHBoxLayout:
        if self._head_actions is None:
            self.set_header("")
        return self._head_actions

    def add(self, widget: QWidget, stretch: int = 0):
        self._box.addWidget(widget, stretch)

    def add_layout(self, layout):
        self._box.addLayout(layout)

    # 兼容 QLayout 命名习惯
    def addWidget(self, widget: QWidget, stretch: int = 0):
        self.add(widget, stretch)

    def addLayout(self, layout):
        self.add_layout(layout)

    def body(self) -> QVBoxLayout:
        return self._box

    def paintEvent(self, event):
        t = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        r = min(self._radius, rect.height() / 2)
        path = rounded_path(rect, r)

        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor(*t["glass_top"]))
        grad.setColorAt(1, QColor(*t["glass_bottom"]))
        p.fillPath(path, grad)

        p.save()
        p.setClipPath(path)
        sheen = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + min(90, rect.height() * 0.55))
        sheen.setColorAt(0, QColor(255, 255, 255, t["glass_sheen"]))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(rect, sheen)
        p.restore()

        p.setPen(QPen(QColor(*t["glass_border"]), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        inner = rect.adjusted(1.6, 1.6, -1.6, -1.6)
        p.setPen(QPen(QColor(255, 255, 255, t["glass_inner"]), 0.8))
        p.drawRoundedRect(inner, max(1, r - 1.6), max(1, r - 1.6))
        p.end()


# ---------------------------------------------------------------- 玻璃按钮
class GlassButton(QPushButton):
    def __init__(self, text: str = "", primary: bool = False, parent=None):
        super().__init__(text, parent)
        self._primary = primary
        self._active = False
        self._hover = False
        self.setFont(theme.app_font(10, True))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_primary(self, value: bool):
        self._primary = value
        self.update()

    def set_active(self, value: bool):
        self._active = value
        self.update()

    def is_active(self) -> bool:
        return self._active

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(max(78, fm.horizontalAdvance(self.text()) + 44), 38)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        t = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        r = rect.height() / 2
        path = rounded_path(rect, r)

        enabled = self.isEnabled()
        if self._primary:
            g = QLinearGradient(rect.topLeft(), rect.bottomRight())
            g.setColorAt(0, QColor("#4a8bff"))
            g.setColorAt(1, QColor("#9a68ff"))
            brush = g
            border = QColor(255, 255, 255, 95)
            text_color = QColor("#ffffff")
        elif self._active:
            brush = QColor(t["qss"]["accent"])
            brush.setAlpha(58)
            border = QColor(t["qss"]["accent"])
            text_color = QColor(t["text"])
        else:
            r0, g0, b0, a0 = t["btn_hover"] if self._hover else t["btn_normal"]
            brush = QColor(r0, g0, b0, a0)
            border = QColor(*t["btn_border"])
            text_color = QColor(t["btn_text"])
        if self.isDown() and enabled:
            pressed = QColor("#5b8dff") if self._primary else QColor(*t["btn_normal"])
            pressed.setAlpha(215)
            brush = pressed
        if not enabled:
            text_color.setAlpha(130)

        p.setBrush(brush)
        p.setPen(QPen(border, 1.1))
        p.drawPath(path)

        if not self._active and not self._primary:
            p.save()
            p.setClipPath(path)
            sheen = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + rect.height() * 0.6)
            sheen.setColorAt(0, QColor(255, 255, 255, 55 if not t["dark"] else 22))
            sheen.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(rect, sheen)
            p.restore()

        p.setPen(text_color)
        p.setFont(self.font())
        p.drawText(rect.adjusted(14, 0, -14, 0), Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class TitleButton(QPushButton):
    """标题栏圆形图标按钮。"""

    def __init__(self, symbol: str, danger: bool = False, parent=None):
        super().__init__(symbol, parent)
        self._danger = danger
        self._hover = False
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(theme.app_font(11, True))
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        t = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self._hover:
            if self._danger:
                fill = QColor(t["close_hover"])
                fill.setAlpha(220)
            else:
                fill = QColor(255, 255, 255, 120 if not t["dark"] else 55)
            p.setBrush(fill)
        else:
            p.setBrush(QColor(255, 255, 255, 40 if not t["dark"] else 20))
        p.setPen(QPen(QColor(255, 255, 255, 90 if not t["dark"] else 35), 1))
        p.drawEllipse(rect)
        p.setPen(QColor("#ffffff") if (self._danger and self._hover) else QColor(t["text"]))
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


# ---------------------------------------------------------------- 进度条
class GlassProgress(QWidget):
    def __init__(self, parent=None, show_text: bool = True, height: int = 12):
        super().__init__(parent)
        self._value = 0.0
        self._show_text = show_text
        self.setFixedHeight(height)
        self.setMinimumWidth(60)

    def set_value(self, value: float):
        self._value = max(0.0, min(100.0, float(value)))
        self.update()

    def value(self) -> float:
        return self._value

    def paintEvent(self, event):
        t = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        r = rect.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*t["slot"]))
        p.drawRoundedRect(rect, r, r)
        if self._value > 0:
            fill = QRectF(rect)
            fill.setWidth(max(rect.height(), rect.width() * self._value / 100.0))
            v = self._value
            c1 = QColor("#3aa9ff") if v < 70 else (QColor("#ffb547") if v < 90 else QColor("#ff5f6d"))
            c2 = QColor("#8a6bff") if v < 70 else (QColor("#ff7a59") if v < 90 else QColor("#ff2d55"))
            g = QLinearGradient(fill.topLeft(), fill.bottomRight())
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.setBrush(g)
            p.drawRoundedRect(fill, r, r)
        if self._show_text:
            p.setPen(QColor(t["dim"]))
            f = theme.app_font(8, True)
            p.setFont(f)
            p.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{self._value:.0f}%  ")
        p.end()


# ---------------------------------------------------------------- 导航按钮
class NavButton(QPushButton):
    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._text = text
        self._active = False
        self._hover = False
        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_active(self, value: bool):
        self._active = value
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        t = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        if self._active:
            p.setBrush(QColor(*t["nav_active"]))
            p.setPen(QPen(QColor(*t["glass_border"]), 1))
            p.drawRoundedRect(rect, 13, 13)
            bar = QRectF(rect.left() + 9, rect.top() + 12, 3, rect.height() - 24)
            p.setBrush(QColor(t["qss"]["accent"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bar, 1.5, 1.5)
        elif self._hover:
            p.setBrush(QColor(255, 255, 255, 70 if not t["dark"] else 26))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 13, 13)
        p.setPen(QColor(t["nav_active_text"] if self._active else t["nav_text"]))
        f = theme.app_font(10, self._active)
        p.setFont(f)
        icon_rect = QRectF(rect.left() + 18, rect.top(), 28, rect.height())
        p.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, self._icon)
        text_rect = QRectF(rect.left() + 48, rect.top(), rect.width() - 52, rect.height())
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        p.end()


# ---------------------------------------------------------------- 标题栏
class TitleBar(QWidget):
    theme_toggled = Signal()

    def __init__(self, window: QWidget, parent=None):
        super().__init__(parent)
        self._win = window
        self._drag_offset = None
        self.setFixedHeight(54)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 4, 18, 0)
        lay.setSpacing(10)

        logo = QLabel()
        logo.setFixedSize(30, 30)
        logo.setPixmap(QPixmap())
        lay.addWidget(logo)
        self._logo = logo

        name = label("LumiBox", 15, True)
        lay.addWidget(name)
        tag = label("Windows 综合工具箱", 9, False, True)
        lay.addWidget(tag)
        lay.addStretch(1)

        self._theme_btn = TitleButton("◐")
        self._theme_btn.setToolTip("切换亮色 / 暗色主题")
        self._theme_btn.clicked.connect(self.theme_toggled.emit)
        lay.addWidget(self._theme_btn)

        min_btn = TitleButton("−")
        min_btn.setToolTip("最小化")
        min_btn.clicked.connect(self._win.showMinimized)
        lay.addWidget(min_btn)

        self._max_btn = TitleButton("□")
        self._max_btn.setToolTip("最大化 / 还原")
        self._max_btn.clicked.connect(self._win.toggle_maximize)
        lay.addWidget(self._max_btn)

        close_btn = TitleButton("✕", danger=True)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self._win.close)
        lay.addWidget(close_btn)

    def set_logo(self, pixmap: QPixmap):
        self._logo.setPixmap(pixmap.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))

    def mousePressEvent(self, event):
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and not isinstance(child, QPushButton):
            self._drag_offset = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self._win.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        child = self.childAt(event.position().toPoint())
        if not isinstance(child, QPushButton):
            self._win.toggle_maximize()
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------- 侧边栏
class SideBar(QWidget):
    page_changed = Signal(int)

    def __init__(self, items: list, parent=None):
        """items: [(emoji, 名称)]"""
        super().__init__(parent)
        self.setFixedWidth(218)
        self._buttons = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 22, 12, 16)
        lay.setSpacing(5)

        cap = label("工 作 台", 9, True, True)
        cap.setContentsMargins(14, 0, 0, 6)
        lay.addWidget(cap)

        # 导航按钮放进可滚动区域，页面多时不会挤出侧栏
        nav_area = QScrollArea()
        nav_area.setWidgetResizable(True)
        nav_area.setFrameShape(QFrame.Shape.NoFrame)
        nav_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_area.setStyleSheet("background: transparent;")
        nav_area.viewport().setStyleSheet("background: transparent;")
        nav_host = QWidget()
        nav_host.setStyleSheet("background: transparent;")
        nav_lay = QVBoxLayout(nav_host)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(5)
        for idx, (icon, text) in enumerate(items):
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda checked=False, i=idx: self._on_click(i))
            nav_lay.addWidget(btn)
            self._buttons.append(btn)
        nav_lay.addStretch(1)
        nav_area.setWidget(nav_host)
        lay.addWidget(nav_area, 1)

        status = GlassCard(radius=16, spacing=6)
        status.body().setContentsMargins(16, 12, 16, 12)
        status.add(label("● 本地运行", 9, True))
        status.add(label("所有计算均在本机完成，数据不上传", 8, False, True))
        lay.addWidget(status)

        from . import __version__
        ver = label(f"LumiBox  v{__version__} · PySide6", 8, False, True)
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)

    def _on_click(self, idx: int):
        for i, b in enumerate(self._buttons):
            b.set_active(i == idx)
        self.page_changed.emit(idx)

    def set_index(self, idx: int):
        for i, b in enumerate(self._buttons):
            b.set_active(i == idx)

    def paintEvent(self, event):
        t = theme.CURRENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        g.setColorAt(0, QColor(*t["glass_top"]))
        g.setColorAt(1, QColor(*t["glass_bottom"]))
        p.fillPath(rounded_path(rect, 18), g)
        p.setPen(QPen(QColor(*t["glass_border"]), 1))
        p.drawPath(rounded_path(rect, 18))
        p.end()


# ---------------------------------------------------------------- 页面骨架
class PageScaffold(QWidget):
    """带大标题的滚动页面容器。"""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(self._scroll)

        content = QWidget()
        content.setObjectName("page_content")
        self._content = content
        self._box = QVBoxLayout(content)
        self._box.setContentsMargins(32, 28, 32, 40)
        self._box.setSpacing(18)

        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label(title, 20, True))
        head.addWidget(label(subtitle, 10, False, True))
        self._box.addLayout(head)
        self._scroll.setWidget(content)

        self._box.addSpacing(4)

    def add_card(self, card: GlassCard, stretch: int = 0):
        self._box.addWidget(card, stretch)

    def add_widget(self, widget: QWidget, stretch: int = 0):
        self._box.addWidget(widget, stretch)

    def add_layout(self, layout):
        self._box.addLayout(layout)

    def add_stretch(self, stretch: int = 1):
        self._box.addStretch(stretch)

    def content_layout(self) -> QVBoxLayout:
        return self._box
