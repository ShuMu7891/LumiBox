"""主窗口：无边框液态玻璃外壳、侧边导航、页面栈与全局提示。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QGuiApplication, QPalette, QColor, QShortcut, QKeySequence, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QStackedWidget, QFrame, QApplication, QSystemTrayIcon, QMenu)

from . import theme
from .glass import GlassBackground, TitleBar, SideBar
from .utils import make_app_icon
from .pages.home_page import HomePage
from .pages.system_page import SystemPage
from .pages.text_page import TextPage
from .pages.image_page import ImagePage
from .pages.net_page import NetPage
from .pages.dev_page import DevPage
from .pages.tools_page import ToolsPage
from .pages.calc_page import CalcPage
from .pages.files_page import FilesPage
from .pages.sys_page import SysPage
from .pages.doc_page import DocPage
from .pages.focus_page import FocusPage
from .pages.about_page import AboutPage


NAV_ITEMS = [
    ("🏠", "概览"),
    ("🖥", "系统信息 & 监控"),
    ("📝", "文本与开发"),
    ("🖼", "图片与颜色"),
    ("🌐", "网络与效率"),
    ("🧰", "开发者工具"),
    ("🛠", "实用工具"),
    ("🧮", "计算器"),
    ("📁", "文件管家"),
    ("⚙", "系统增强"),
    ("📄", "文档工坊"),
    ("🎯", "截图 & 效率"),
    ("ℹ", "关于"),
]


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LumiBox · Windows 综合工具箱")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(1060, 680)
        self.resize(1280, 840)
        self._maximized = False
        self._normal_geom: QRect | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._bg = GlassBackground()
        root.addWidget(self._bg)

        bg_lay = QVBoxLayout(self._bg)
        bg_lay.setContentsMargins(15, 15, 15, 15)
        bg_lay.setSpacing(0)
        self._title = TitleBar(self)
        self._title.theme_toggled.connect(self.toggle_theme)
        self._title.set_logo(make_app_icon(96).pixmap(96, 96))
        bg_lay.addWidget(self._title)

        body = QHBoxLayout()
        body.setContentsMargins(14, 4, 14, 14)
        body.setSpacing(14)
        self._side = SideBar(NAV_ITEMS)
        self._side.page_changed.connect(self.go_page)
        body.addWidget(self._side)

        self._stack = QStackedWidget()
        self._stack.setFrameShape(QFrame.Shape.NoFrame)
        self._stack.setStyleSheet("background: transparent;")
        self._pages = [
            HomePage(self.go_page),
            SystemPage(),
            TextPage(),
            ImagePage(),
            NetPage(),
            DevPage(),
            ToolsPage(),
            CalcPage(),
            FilesPage(),
            SysPage(),
            DocPage(),
            FocusPage(),
            AboutPage(),
        ]
        for page in self._pages:
            self._stack.addWidget(page)
        body.addWidget(self._stack, 1)
        bg_lay.addLayout(body, 1)

        # ---------- 全局浮动提示 ----------
        self._toast = QLabel(self._bg)
        self._toast.setWordWrap(True)
        self._toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast.setStyleSheet(
            "background: rgba(22,30,50,0.90); color: #ffffff;"
            "border: 1px solid rgba(255,255,255,0.28); border-radius: 20px;"
            "padding: 10px 20px; font-size: 13px;")
        self._toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)

        for i in range(1, 10):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda idx=i: self.go_page(idx - 1))

        # 应用内全局热键：显示/隐藏窗口、快速截图
        sc_toggle = QShortcut(QKeySequence("Ctrl+`"), self)
        sc_toggle.activated.connect(self.toggle_visibility)
        sc_shot = QShortcut(QKeySequence("Ctrl+Alt+S"), self)
        sc_shot.activated.connect(self.quick_shot)

        self._tray = None
        self._always_on_top = False
        self._init_tray()

        self.apply_theme(False)
        self.go_page(0)
        center = QGuiApplication.primaryScreen()
        if center:
            self.move(center.availableGeometry().center() - self.rect().center())

    # ---------------------------------------------------------------- 系统托盘
    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        try:
            self._tray = QSystemTrayIcon(make_app_icon(64), self)
            self._tray.setToolTip("LumiBox · Windows 综合工具箱")
            menu = QMenu()
            menu.addAction("显示 / 隐藏窗口", self.toggle_visibility)
            menu.addSeparator()
            quick = [("系统监控", 1), ("文本与开发", 2), ("计算器", 7),
                     ("文件管家", 8), ("系统增强", 9), ("截图 & 效率", 11)]
            for name, idx in quick:
                menu.addAction(name, lambda i=idx: self._tray_open_page(i))
            menu.addSeparator()
            menu.addAction("快速截图", self.quick_shot)
            menu.addAction("退出", QApplication.instance().quit)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(
                lambda reason: self.show_from_tray()
                if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
            self._tray.show()
        except Exception:  # noqa: BLE001
            self._tray = None

    def _tray_open_page(self, index: int):
        self.show_from_tray()
        self.go_page(index)

    def hide_to_tray(self):
        self.hide()
        if self._tray:
            self._tray.showMessage("LumiBox", "已最小化到系统托盘，双击图标可恢复",
                                   QSystemTrayIcon.MessageIcon.Information, 2500)

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide_to_tray()
        else:
            self.show_from_tray()

    def quick_shot(self):
        """Ctrl+Alt+S：切到截图页并触发全屏截图。"""
        self.show_from_tray()
        self.go_page(11)
        page = self._pages[11]
        fn = getattr(page, "_capture_full", None)
        if callable(fn):
            fn()

    # ---------------------------------------------------------------- 窗口控制
    def set_always_on_top(self, value: bool):
        self._always_on_top = bool(value)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._always_on_top)
        self.show()  # 修改 window flags 后需重新 show

    def set_opacity(self, value: float):
        self.setWindowOpacity(max(0.3, min(1.0, float(value))))

    # ---------------------------------------------------------------- 导航
    def go_page(self, index: int):
        index = max(0, min(len(self._pages) - 1, int(index)))
        self._stack.setCurrentIndex(index)
        self._side.set_index(index)

    # ---------------------------------------------------------------- 主题
    def toggle_theme(self):
        self.apply_theme(not theme.is_dark())

    def apply_theme(self, dark: bool):
        theme.set_dark(dark)
        self.setStyleSheet(theme.qss())
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.CURRENT["dim"]))
        self.setPalette(pal)
        self._title._theme_btn.setText("☀" if dark else "◐")
        for widget in self.findChildren(QWidget):
            widget.update()
        self.update()

    # ---------------------------------------------------------------- 窗口控制
    def toggle_maximize(self):
        if not self._maximized:
            self._normal_geom = self.geometry()
            screen = QGuiApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.availableGeometry())
            self._maximized = True
            self._bg.set_maximized(True)
            self._title._max_btn.setText("❐")
        else:
            self._maximized = False
            self._bg.set_maximized(False)
            if self._normal_geom is not None:
                self.setGeometry(self._normal_geom)
            self._title._max_btn.setText("□")
        self.update()

    # ---------------------------------------------------------------- 提示
    def notify(self, message: str):
        self._toast.setText(str(message))
        width = min(560, max(230, self._toast.fontMetrics().horizontalAdvance(str(message)) + 56))
        self._toast.setFixedWidth(int(width))
        self._toast.adjustSize()
        self._toast.move((self.width() - int(width)) // 2, self.height() - 96)
        self._toast.raise_()
        self._toast.show()
        self._toast_timer.start(2300)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._toast.isVisible():
            self._toast.move((self.width() - self._toast.width()) // 2, self.height() - 96)

    def closeEvent(self, event):
        """退出前停止所有定时器与后台线程，避免 QThread 析构告警。"""
        for page in self._pages:
            for timer in page.findChildren(QTimer):
                timer.stop()
            for worker in list(getattr(page, "_workers", [])):
                if worker.isRunning():
                    worker.requestInterruption()
                    # 等待后台线程自然收尾；网络请求已设短超时，不会对 Python 线程使用
                    # terminate()（在持有 GIL 时可能导致死锁）
                    worker.wait(3000)
        event.accept()
