"""新增页面共用的 UI 辅助（信号绑定、Tab 容器、表格、文件对话框、后台线程）。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QTableWidget,
                              QTableWidgetItem, QHeaderView, QScrollArea, QFrame,
                              QFileDialog, QSizePolicy, QApplication, QLineEdit,
                              QListWidget, QListWidgetItem, QCheckBox, QSpinBox,
                              QComboBox, QMessageBox)

from ..glass import GlassButton, label, notify
from ..utils import Worker, set_clipboard


def on_click(button, fn, *args):
    """安全连接 clicked：显式吞掉 checked 参数，避免默认参数被信号覆盖。"""
    button.clicked.connect(lambda _checked=False, a=args: fn(*a))
    return button


def changed(widget, signal_name: str, fn, *args):
    """连接无参回调到带参信号（currentIndexChanged / valueChanged 等）。"""
    getattr(widget, signal_name).connect(lambda _v=None, a=args: fn(*a))
    return widget


def tab_container() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    outer = QVBoxLayout(w)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("background: transparent;")
    scroll.viewport().setStyleSheet("background: transparent;")
    content = QWidget()
    content.setObjectName("page_content")
    lay = QVBoxLayout(content)
    lay.setContentsMargins(0, 14, 8, 0)
    lay.setSpacing(16)
    scroll.setWidget(content)
    outer.addWidget(scroll)
    return w, lay


def plain_tab() -> tuple[QWidget, QVBoxLayout]:
    """无内层滚动条的轻量 Tab 容器（供卡片内嵌的二级 Tab 使用）。"""
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 12, 4, 0)
    lay.setSpacing(10)
    return w, lay


def editor(placeholder: str = "", height: int = 100, readonly: bool = False) -> QTextEdit:
    e = QTextEdit()
    e.setPlaceholderText(placeholder)
    e.setMinimumHeight(height)
    e.setMaximumHeight(height)
    e.setReadOnly(readonly)
    e.setAcceptRichText(False)
    e.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap if readonly else QTextEdit.LineWrapMode.WidgetWidth)
    return e


def row(*widgets, stretch: bool = True) -> QHBoxLayout:
    """水平行：可伸展控件（输入框等）拿剩余空间，按钮保持自然宽度。"""
    lay = QHBoxLayout()
    lay.setSpacing(8)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        else:
            lay.addWidget(w)
            if isinstance(w, QLineEdit):
                lay.setStretchFactor(w, 1)
    if stretch:
        lay.addStretch(1)
    return lay


def make_table(headers, stretch: bool = True) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(list(headers))
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.setShowGrid(False)
    t.setAlternatingRowColors(False)
    t.verticalHeader().setVisible(False)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    hh = t.horizontalHeader()
    for i in range(len(headers)):
        hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if stretch
                                else QHeaderView.ResizeMode.ResizeToContents)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return t


def fill_table(t: QTableWidget, rows, row_height: int = 30, max_height: int = 2200):
    t.setRowCount(len(rows))
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            t.setItem(r, c, item)
    t.setFixedHeight(min(max(38, len(rows) * row_height + 36), max_height))
    return t


def btn(text: str, primary: bool = False) -> GlassButton:
    b = GlassButton(text, primary)
    b.setFixedHeight(34)
    return b


def pick_file(parent, title: str, pattern: str) -> str:
    path, _ = QFileDialog.getOpenFileName(parent, title, "", pattern)
    return path


def export_text(parent, text: str, default_name: str = "lumibox_export.txt") -> str:
    path, _ = QFileDialog.getSaveFileName(parent, "导出到文件", default_name,
                                          "文本文件 (*.txt);;CSV 文件 (*.csv);;所有文件 (*)")
    if not path:
        return ""
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(text))
    notify(parent, f"已导出到 {os.path.basename(path)}")
    return path


def copy_text(widget, text) -> None:
    value = text() if callable(text) else text
    if not value:
        notify(widget, "没有可复制的内容")
        return
    set_clipboard(str(value))
    notify(widget, "已复制到剪贴板")


def clipboard_text() -> str:
    return QApplication.clipboard().text()


def start_worker(page, fn, args, on_done, on_fail=None):
    w = Worker(fn, *args)
    w.done.connect(on_done)
    w.failed.connect(on_fail or (lambda msg: notify(page, f"操作失败：{msg}")))
    if not hasattr(page, "_workers"):
        page._workers = []
    page._workers.append(w)
    w.start()
    return w


def mono(text: str, size: int = 9):
    l = label(text, size)
    l.setStyleSheet("font-family: Consolas, 'Cascadia Mono', 'Noto Sans Mono CJK SC', monospace;")
    return l


def field(text: str = "", placeholder: str = "") -> QLineEdit:
    e = QLineEdit(text)
    e.setPlaceholderText(placeholder)
    e.setMinimumHeight(32)
    return e


# ---------------------------------------------------------------- 通用小控件
def combo(items, current: str = "", width: int = 150) -> QComboBox:
    c = QComboBox()
    c.addItems([str(x) for x in items])
    if current:
        c.setCurrentText(str(current))
    c.setFixedWidth(width)
    return c


def checkbox(text: str, checked: bool = False) -> QCheckBox:
    c = QCheckBox(text)
    c.setChecked(checked)
    return c


def spin(value: int, low: int, high: int, width: int = 100, prefix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(low, high)
    s.setValue(value)
    s.setFixedWidth(width)
    if prefix:
        s.setPrefix(prefix)
    return s


def ask(parent, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes


def warn(parent, title: str, text: str):
    QMessageBox.warning(parent, title, text)


def info_box(parent, title: str, text: str):
    QMessageBox.information(parent, title, text)


def pick_dir(parent, title: str = "选择目录") -> str:
    return QFileDialog.getExistingDirectory(parent, title, "") or ""


def save_path(parent, title: str, default_name: str, pattern: str) -> str:
    p, _ = QFileDialog.getSaveFileName(parent, title, default_name, pattern)
    return p


class DropList(QListWidget):
    """支持从资源管理器拖入文件/目录的列表。"""
    files_dropped = Signal(list)

    def __init__(self, parent=None, directories: bool = False):
        super().__init__(parent)
        self._dirs = directories
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setMinimumHeight(110)
        self.setMaximumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("可直接把文件拖进这里")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for u in event.mimeData().urls():
            p = u.toLocalFile()
            if not p:
                continue
            if self._dirs or os.path.isfile(p):
                paths.append(p)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def paths(self) -> list[str]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.count())
                if self.item(i).data(Qt.ItemDataRole.UserRole)]

    def add_paths(self, paths: list[str]):
        have = set(self.paths())
        for p in paths:
            if p in have:
                continue
            it = QListWidgetItem(os.path.basename(p) + ("  ·  " + p if len(p) < 90 else ""))
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.addItem(it)
            have.add(p)

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeItem(self.row(it))
