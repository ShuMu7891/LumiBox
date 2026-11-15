#!/usr/bin/env python3
"""LumiBox · Windows 综合工具箱 —— 程序入口。"""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from app.main_window import MainWindow
from app.utils import make_app_icon


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LumiBox")
    app.setApplicationDisplayName("LumiBox · Windows 综合工具箱")
    app.setWindowIcon(make_app_icon())

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
