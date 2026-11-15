"""概览页：欢迎、实时时钟、系统状态与快捷入口。"""
from datetime import datetime

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QGridLayout, QSizePolicy

from ..glass import (PageScaffold, GlassCard, GlassButton, GlassProgress, label, divider)
from ..utils import human_bytes


class HomePage(PageScaffold):
    def __init__(self, go_page, parent=None):
        super().__init__("概览", "欢迎使用 LumiBox · 一站式 Windows 效率工具箱", parent)
        self._go = go_page

        hero = GlassCard("欢迎回来", "所有工具均在本机离线运行，无需联网、无需登录", spacing=16)
        row = QHBoxLayout()
        row.setSpacing(20)
        col = QVBoxLayout()
        col.setSpacing(2)
        self._clock = label("--:--:--", 30, True)
        self._date = label("", 10, False, True)
        self._sys = label("", 10, False, True)
        col.addWidget(self._clock)
        col.addWidget(self._date)
        col.addSpacing(8)
        col.addWidget(self._sys)
        col.addStretch(1)
        row.addLayout(col, 1)

        quick = QGridLayout()
        quick.setSpacing(8)
        for i, (icon, text, page) in enumerate([
            ("🖥", "系统监控", 1), ("📝", "文本 / 哈希", 2),
            ("🖼", "图片 / 配色", 3), ("🌐", "网络 / 效率", 4),
            ("🧰", "开发者工具", 5), ("🛠", "实用工具", 6),
            ("🧮", "计算器", 7), ("📁", "文件管家", 8),
            ("⚙", "系统增强", 9), ("📄", "文档工坊", 10),
            ("🎯", "截图 & 效率", 11), ("ℹ", "关于", 12),
        ]):
            b = GlassButton(f"{icon}  {text}")
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda checked=False, p=page: self._go(p))
            quick.addWidget(b, i // 2, i % 2)
        row.addLayout(quick, 1)
        hero.add_layout(row)
        self.add_card(hero)

        status = GlassCard("实时状态", "每秒自动刷新", spacing=14)
        self._bars = {}
        for key, name in (("cpu", "CPU 使用率"), ("mem", "内存占用"), ("disk", "系统盘占用")):
            line = QHBoxLayout()
            line.setSpacing(12)
            name_lbl = label(name, 10, True)
            name_lbl.setFixedWidth(96)
            bar = GlassProgress(height=14)
            val = label("-", 10, True)
            val.setFixedWidth(140)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            line.addWidget(name_lbl)
            line.addWidget(bar, 1)
            line.addWidget(val)
            status.add_layout(line)
            self._bars[key] = (bar, val)
        self.add_card(status)

        grid = QGridLayout()
        grid.setSpacing(16)
        for i, (icon, title, desc, page) in enumerate([
            ("🖥", "系统信息 & 监控", "CPU、内存、磁盘、网络速率、进程列表与硬件信息", 1),
            ("📝", "文本与开发", "SHA 哈希、Base64、JSON、正则、URL 编解码", 2),
            ("🖼", "图片与颜色", "压缩、缩放、格式转换、取色与配色方案", 3),
            ("🌐", "网络与效率", "二维码、时间戳、密码、计算器、单位换算", 4),
            ("🧰", "开发者工具", "进制、编码、随机数、UUID、反编译、剪贴板", 5),
            ("🛠", "实用工具", "二维码解析、转盘、局域网扫描、磁盘健康", 6),
            ("📁", "文件管家", "重复文件清理、批量重命名、文件粉碎、hosts 编辑", 8),
            ("⚙", "系统增强", "启动项与服务、定时任务、端口扫描、窗口控制", 9),
            ("📄", "文档工坊", "格式互转、Markdown 预览导出、OCR、密码保险箱", 10),
            ("🎯", "截图 & 效率", "屏幕截图与置顶贴图、番茄钟、待办清单", 11),
        ]):
            card = GlassCard(radius=18, spacing=10)
            emoji = label(icon, 22)
            card.add(emoji)
            card.add(label(title, 11, True))
            d = label(desc, 9, False, True)
            d.setMinimumHeight(46)
            card.add(d)
            btn = GlassButton("打开 →")
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda checked=False, p=page: self._go(p))
            card.add(btn)
            card.body().addStretch(0)
            grid.addWidget(card, i // 3, i % 3)
        self.add_layout(grid)

        tips = GlassCard("使用小贴士", "", spacing=8)
        tips.add(label("· 按 Ctrl + 1 ~ 9 切换前九个页面，Ctrl+` 隐藏/显示窗口，Ctrl+Alt+S 快速截图", 10))
        tips.add(label("· 标题栏可拖拽移动窗口，双击标题栏可最大化 / 还原", 10))
        tips.add(label("· 「系统增强」页可开启窗口置顶、调整透明度、隐藏到系统托盘", 10))
        tips.add(label("· 点击右上角 ◐ 可在亮色 / 暗色液态玻璃主题间切换", 10))
        tips.add(label("· 所有「复制」按钮都会把结果写入系统剪贴板，多处支持拖拽文件", 10))
        self.add_card(tips)
        self.add_stretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self):
        now = datetime.now()
        self._clock.setText(now.strftime("%H:%M:%S"))
        week = "一二三四五六日"[now.weekday()]
        self._date.setText(f"{now.year} 年 {now.month} 月 {now.day} 日 · 星期{week}")
        try:
            import platform
            self._sys.setText(f"{platform.system()} {platform.release()}  ·  {platform.machine()}  ·  Python {platform.python_version()}")
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            self._bars["cpu"][0].set_value(cpu)
            self._bars["cpu"][1].setText(f"{cpu:.1f}%  ·  {psutil.cpu_count()} 核心")
            self._bars["mem"][0].set_value(mem.percent)
            self._bars["mem"][1].setText(f"{human_bytes(mem.used)} / {human_bytes(mem.total)}")
            self._bars["disk"][0].set_value(disk.percent)
            self._bars["disk"][1].setText(f"{human_bytes(disk.used)} / {human_bytes(disk.total)}")
        except Exception as exc:  # noqa: BLE001
            self._sys.setText(f"系统信息读取失败：{exc}")
