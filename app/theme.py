"""Liquid Glass 主题：配色方案与全局样式表。

所有自定义绘制控件在 paintEvent 中读取 CURRENT，
切换主题时由主窗口重新 setStyleSheet 并触发重绘。
"""
import os
import tempfile

from PySide6.QtGui import QColor, QFont

# 下拉箭头用真实 PNG（CSS border 三角在部分平台/离屏渲染会变成实心小方块）
_ARROW_CACHE: dict[str, str] = {}


def _arrow_url(color: str) -> str:
    color = color.strip()
    if color in _ARROW_CACHE:
        return _ARROW_CACHE[color]
    path = ""
    try:
        from PIL import Image, ImageDraw
        if color.startswith("#") and len(color) == 7:
            rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        else:
            rgb = (105, 120, 143)
        img = Image.new("RGBA", (14, 9), (0, 0, 0, 0))
        ImageDraw.Draw(img).polygon([(1, 2), (12, 2), (6, 8)], fill=rgb + (255,))
        p = os.path.join(tempfile.gettempdir(), f"lumibox_arrow_{color.lstrip('#')}.png")
        img.save(p)
        path = p.replace("\\", "/")
    except Exception:  # noqa: BLE001
        path = ""
    _ARROW_CACHE[color] = path
    return path

APP_FONT_FAMILY = '"Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", sans-serif'

LIGHT = {
    "dark": False,
    # 背景渐变（左上 -> 右下）
    "bg_stops": ["#e7f0ff", "#f1ecff", "#ffe9f2", "#e4fbf8"],
    # 光斑：(相对x, 相对y, 相对半径, 颜色)
    "blobs": [
        (0.10, 0.14, 0.62, (88, 148, 255, 125)),
        (0.86, 0.08, 0.46, (168, 118, 255, 115)),
        (0.80, 0.86, 0.55, (255, 136, 182, 110)),
        (0.16, 0.92, 0.48, (78, 214, 206, 100)),
        (0.52, 0.46, 0.40, (255, 214, 130, 55)),
    ],
    "glass_top": (255, 255, 255, 172),
    "glass_bottom": (255, 255, 255, 108),
    "glass_sheen": 105,
    "glass_border": (255, 255, 255, 225),
    "glass_inner": 135,
    "shadow": (52, 78, 130, 16),
    "text": "#172132",
    "dim": "#69788f",
    "btn_text": "#172132",
    "btn_normal": (255, 255, 255, 130),
    "btn_hover": (255, 255, 255, 215),
    "btn_border": (255, 255, 255, 205),
    "nav_active": (255, 255, 255, 205),
    "nav_text": "#4c5a70",
    "nav_active_text": "#172132",
    "slot": (255, 255, 255, 150),
    "close_hover": "#e5484d",
    "divider": (255, 255, 255, 150),
    "qss": {
        "text": "#172132",
        "dim": "#69788f",
        "accent": "#3b7dff",
        "field": "rgba(255,255,255,0.55)",
        "field_focus": "rgba(255,255,255,0.80)",
        "field_border": "rgba(255,255,255,0.85)",
        "sel": "rgba(59,125,255,0.30)",
        "tab": "rgba(255,255,255,0.38)",
        "tab_active": "rgba(255,255,255,0.85)",
        "tab_hover": "rgba(255,255,255,0.60)",
        "track": "rgba(110,130,170,0.25)",
        "scroll": "rgba(110,130,170,0.48)",
        "table": "rgba(255,255,255,0.42)",
        "table_head": "rgba(255,255,255,0.34)",
        "grid": "rgba(255,255,255,0.55)",
        "popup": "#fbfcff",
        "popup_text": "#172132",
    },
}

DARK = {
    "dark": True,
    "bg_stops": ["#0a1126", "#121a36", "#1b1334", "#07252c"],
    "blobs": [
        (0.10, 0.14, 0.66, (60, 110, 255, 110)),
        (0.86, 0.08, 0.48, (140, 84, 255, 105)),
        (0.80, 0.86, 0.58, (255, 84, 150, 82)),
        (0.14, 0.92, 0.50, (30, 190, 190, 85)),
        (0.52, 0.46, 0.42, (255, 170, 80, 40)),
    ],
    "glass_top": (255, 255, 255, 34),
    "glass_bottom": (255, 255, 255, 15),
    "glass_sheen": 34,
    "glass_border": (255, 255, 255, 62),
    "glass_inner": 34,
    "shadow": (0, 0, 0, 30),
    "text": "#eef3ff",
    "dim": "#9aa9c4",
    "btn_text": "#eef3ff",
    "btn_normal": (255, 255, 255, 30),
    "btn_hover": (255, 255, 255, 62),
    "btn_border": (255, 255, 255, 58),
    "nav_active": (255, 255, 255, 52),
    "nav_text": "#a3b1cc",
    "nav_active_text": "#ffffff",
    "slot": (255, 255, 255, 32),
    "close_hover": "#ff5f57",
    "divider": (255, 255, 255, 34),
    "qss": {
        "text": "#eef3ff",
        "dim": "#9aa9c4",
        "accent": "#5b8dff",
        "field": "rgba(255,255,255,0.08)",
        "field_focus": "rgba(255,255,255,0.15)",
        "field_border": "rgba(255,255,255,0.20)",
        "sel": "rgba(91,141,255,0.45)",
        "tab": "rgba(255,255,255,0.07)",
        "tab_active": "rgba(255,255,255,0.17)",
        "tab_hover": "rgba(255,255,255,0.12)",
        "track": "rgba(255,255,255,0.13)",
        "scroll": "rgba(255,255,255,0.30)",
        "table": "rgba(255,255,255,0.055)",
        "table_head": "rgba(255,255,255,0.10)",
        "grid": "rgba(255,255,255,0.09)",
        "popup": "#1b2440",
        "popup_text": "#eef3ff",
    },
}

CURRENT = LIGHT


def set_dark(enabled: bool):
    global CURRENT
    CURRENT = DARK if enabled else LIGHT


def is_dark() -> bool:
    return CURRENT["dark"]


def color(key: str) -> QColor:
    return QColor(CURRENT[key])


def rgba(key: str, alpha: int = 255) -> QColor:
    r, g, b, a = CURRENT[key]
    return QColor(r, g, b, alpha if alpha != 255 else a)


def app_font(point: int = 10, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamily("Segoe UI")
    f.setPointSize(point)
    f.setBold(bold)
    return f


_QSS = """
/* 字体由全局 QFont 与各控件 setFont 控制，此处只统一颜色 */
QWidget { color: @text; }
QLabel { background: transparent; }
QLabel[dim="true"] { color: @dim; }
QPushButton { background: transparent; border: none; color: @text; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateTimeEdit {
    background: @field;
    border: 1px solid @field_border;
    border-radius: 10px;
    padding: 7px 11px;
    color: @text;
    selection-background-color: @sel;
    selection-color: @text;
}
QTextEdit, QPlainTextEdit { padding: 10px; line-height: 140%; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateTimeEdit:focus {
    border: 1px solid @accent;
    background: @field_focus;
}
QLineEdit:disabled, QTextEdit:disabled { color: @dim; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: 0px; width: 22px; subcontrol-origin: padding; subcontrol-position: right center; }
QComboBox::down-arrow {
    image: url("@arrow");
    width: 12px; height: 8px;
    border: none; margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: @popup;
    color: @popup_text;
    border: 1px solid @field_border;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: @accent;
    selection-color: #ffffff;
    outline: 0px;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 18px; border: none; }
QSpinBox:focus, QDoubleSpinBox:focus { outline: 0px; }
QCheckBox, QRadioButton { spacing: 9px; background: transparent; color: @text; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 17px; height: 17px;
    border: 1px solid @field_border;
    background: @field;
}
QCheckBox::indicator { border-radius: 5px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: @accent; border: 1px solid @accent;
}
QCheckBox::indicator:hover { border-color: @accent; }
QSlider::groove:horizontal { height: 6px; background: @track; border-radius: 3px; }
QSlider::groove:vertical { width: 6px; background: @track; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @accent; border-radius: 3px; }
QSlider::add-page:vertical { background: @accent; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #ffffff; border: 2px solid @accent;
    width: 15px; margin: -6px 0; border-radius: 9px;
}
QSlider::handle:vertical {
    background: #ffffff; border: 2px solid @accent;
    height: 15px; margin: 0 -6px; border-radius: 9px;
}
QTabWidget::pane { border: none; background: transparent; top: 0px; }
QTabBar::tab {
    background: @tab; color: @dim;
    padding: 9px 18px; margin-right: 6px;
    border-radius: 11px; font-weight: 600; font-size: 13px;
}
QTabBar::tab:selected { background: @tab_active; color: @text; }
QTabBar::tab:hover:!selected { background: @tab_hover; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QWidget#page_content { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px 2px 2px 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 2px 2px 2px; }
QScrollBar::handle:vertical { background: @scroll; border-radius: 5px; min-height: 32px; }
QScrollBar::handle:horizontal { background: @scroll; border-radius: 5px; min-width: 32px; }
QScrollBar::handle:hover { background: @accent; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QTableWidget, QTableView {
    background: @table; border: none; border-radius: 10px;
    gridline-color: @grid; color: @text; outline: 0px;
}
QHeaderView::section {
    background: @table_head; color: @dim; border: none;
    padding: 8px 10px; font-weight: 600;
}
QTableWidget::item { padding: 5px 9px; border-bottom: 1px solid @grid; }
QTableWidget::item:selected { background: @sel; color: @text; }
QToolTip {
    background: @popup; color: @popup_text;
    border: 1px solid @field_border; border-radius: 8px; padding: 6px 9px;
}
QSizeGrip { background: transparent; }
QFrame[hr="true"] { background: @grid; border: none; }
"""


def qss() -> str:
    out = _QSS
    for key in sorted(CURRENT["qss"], key=len, reverse=True):
        out = out.replace("@" + key, CURRENT["qss"][key])
    arrow = _arrow_url(CURRENT["dim"])
    # 没有可用图片时退回无箭头（避免方块伪影）
    out = out.replace('url("@arrow")', f'url("{arrow}")' if arrow else "none")
    return out
