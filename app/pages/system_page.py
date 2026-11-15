"""系统信息 & 监控页（真实数据）。"""
from __future__ import annotations

import platform
import socket
import time
from datetime import datetime

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QWidget)

from ..glass import (PageScaffold, GlassCard, GlassButton, GlassProgress, label,
                     copy_button, notify)
from ..utils import Worker, human_bytes, format_duration


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:  # noqa: BLE001
            return "无法获取"


def _public_ip() -> str:
    import requests
    r = requests.get("https://api.ipify.org?format=json", timeout=(1.5, 2.5))
    r.raise_for_status()
    return r.json().get("ip", "未知")


def _top_processes(limit: int = 12):
    rows = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            rss = info["memory_info"].rss if info["memory_info"] else 0
            rows.append((str(info["pid"]), info["name"] or "-",
                        f"{info['cpu_percent'] or 0:.1f}", f"{rss / 1024 / 1024:.1f}"))
        except Exception:  # noqa: BLE001
            continue
    rows.sort(key=lambda r: float(r[3]), reverse=True)
    return rows[:limit]


class SystemPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("系统信息 & 监控", "实时掌握这台设备的运行状态与硬件信息", parent)
        self._workers = []
        self._prev_net = None
        self._prev_t = time.time()
        self._boot = psutil.boot_time()

        # ---------- 实时性能 ----------
        perf = GlassCard("实时性能", "每秒刷新 · 网络速率按两次采样间隔计算", spacing=14)
        grid = QGridLayout()
        grid.setSpacing(16)
        self._bars = {}
        for idx, (key, name) in enumerate([("cpu", "CPU 使用率"), ("mem", "内存占用"),
                                           ("disk", "系统盘占用"), ("swap", "交换 / 虚拟内存")]):
            cell = QVBoxLayout()
            cell.setSpacing(6)
            cell.addWidget(label(name, 10, True))
            bar = GlassProgress(height=13)
            cell.addWidget(bar)
            val = label("-", 9, False, True)
            cell.addWidget(val)
            grid.addLayout(cell, idx // 2, idx % 2)
            self._bars[key] = (bar, val)
        perf.add_layout(grid)

        netline = QHBoxLayout()
        netline.setSpacing(24)
        self._up = label("↑ 上行  -", 10, True)
        self._down = label("↓ 下行  -", 10, True)
        self._uptime = label("运行时长  -", 10, False, True)
        netline.addWidget(self._up)
        netline.addWidget(self._down)
        netline.addStretch(1)
        netline.addWidget(self._uptime)
        perf.add_layout(netline)
        self.add_card(perf)

        # ---------- 系统详情 ----------
        info_card = GlassCard("系统详情", "操作系统、硬件与网络标识", spacing=12)
        self._info_table = self._make_table(["项目", "信息"])
        info_card.add(self._info_table)
        row = QHBoxLayout()
        row.addStretch(1)
        refresh_ip = GlassButton("重新获取公网 IP")
        refresh_ip.setFixedHeight(32)
        refresh_ip.clicked.connect(self.fetch_public_ip)
        row.addWidget(refresh_ip)
        row.addWidget(copy_button(self, lambda: self._table_text(self._info_table), "复制表格"))
        info_card.add_layout(row)
        self.add_card(info_card)
        self._fill_static_info()

        # ---------- 磁盘分区 ----------
        disk_card = GlassCard("磁盘分区", "各挂载点的容量与使用率", spacing=12)
        self._disk_table = self._make_table(["盘符 / 挂载点", "文件系统", "总容量", "已用", "使用率"])
        self._disk_table.setColumnCount(5)
        self._disk_table.setHorizontalHeaderLabels(["盘符 / 挂载点", "文件系统", "总容量", "已用", "使用率"])
        disk_card.add(self._disk_table)
        self.add_card(disk_card)

        # ---------- 进程 ----------
        proc_card = GlassCard("占用内存最高的进程", "按常驻内存排序 · 每 5 秒刷新", spacing=12)
        self._proc_table = self._make_table(["PID", "进程名", "CPU %", "内存 (MB)"])
        proc_card.add(self._proc_table)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn = GlassButton("立即刷新")
        btn.setFixedHeight(32)
        btn.clicked.connect(self.refresh_processes)
        btn_row.addWidget(btn)
        proc_card.add_layout(btn_row)
        self.add_card(proc_card)
        self.add_stretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self._proc_timer = QTimer(self)
        self._proc_timer.setInterval(5000)
        self._proc_timer.timeout.connect(self.refresh_processes)
        self._proc_timer.start()

        self.refresh()
        self.refresh_disk()
        self.refresh_processes()
        self.fetch_public_ip()

    # ---------------------------------------------------------------- 表格辅助
    def _make_table(self, headers) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(False)
        t.setShowGrid(False)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.setMinimumHeight(140)
        return t

    @staticmethod
    def _table_text(t: QTableWidget) -> str:
        lines = []
        for r in range(t.rowCount()):
            cells = []
            for c in range(t.columnCount()):
                item = t.item(r, c)
                w = t.cellWidget(r, c)
                if item:
                    cells.append(item.text())
                elif w is not None and hasattr(w, "value"):
                    cells.append(f"{w.value():.1f}%")
                else:
                    cells.append("")
            lines.append("  |  ".join(cells))
        return "\n".join(lines)

    def _set_row(self, t: QTableWidget, row: int, values):
        for c, value in enumerate(values):
            t.setItem(row, c, QTableWidgetItem(str(value)))

    # ---------------------------------------------------------------- 静态信息
    def _fill_static_info(self):
        try:
            mem = psutil.virtual_memory()
            scr = QGuiApplication.primaryScreen()
            geo = scr.geometry() if scr else None
            rows = [
                ("操作系统", f"{platform.system()} {platform.release()}"),
                ("系统版本", platform.version()),
                ("系统架构", platform.machine()),
                ("计算机名", platform.node()),
                ("处理器", platform.processor() or platform.uname().processor or "未知"),
                ("CPU 核心", f"{psutil.cpu_count(logical=True)} 逻辑 / {psutil.cpu_count(logical=False)} 物理"),
                ("物理内存", human_bytes(mem.total)),
                ("开机时间", datetime.fromtimestamp(self._boot).strftime("%Y-%m-%d %H:%M:%S")),
                ("屏幕分辨率", f"{geo.width()} × {geo.height()}" if geo else "未知"),
                ("本机内网 IP", _local_ip()),
                ("公网 IP", "获取中…"),
                ("Python 版本", platform.python_version()),
                ("界面框架", f"PySide6 {self._pyside_version()}"),
            ]
        except Exception as exc:  # noqa: BLE001
            rows = [("读取失败", str(exc))]
        self._info_table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self._set_row(self._info_table, i, (k, v))
        self._info_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._info_table.setFixedHeight(len(rows) * 30 + 40)

    @staticmethod
    def _pyside_version() -> str:
        try:
            import PySide6
            return PySide6.__version__
        except Exception:  # noqa: BLE001
            return "未知"

    def fetch_public_ip(self):
        w = Worker(_public_ip)
        self._workers.append(w)
        w.done.connect(self._on_public_ip)
        w.failed.connect(lambda e: self._set_info_value("公网 IP", "获取失败（可能处于离线环境）"))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.start()

    def _on_public_ip(self, ip):
        self._set_info_value("公网 IP", str(ip))

    def _set_info_value(self, key, value):
        for r in range(self._info_table.rowCount()):
            item = self._info_table.item(r, 0)
            if item and item.text() == key:
                self._info_table.setItem(r, 1, QTableWidgetItem(str(value)))
                return

    # ---------------------------------------------------------------- 动态刷新
    def refresh(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            sw = psutil.swap_memory()
            self._bars["cpu"][0].set_value(cpu)
            self._bars["cpu"][1].setText(f"{cpu:.1f}%  ·  {psutil.cpu_count()} 逻辑核心")
            self._bars["mem"][0].set_value(mem.percent)
            self._bars["mem"][1].setText(f"{human_bytes(mem.used)} / {human_bytes(mem.total)}  ·  可用 {human_bytes(mem.available)}")
            self._bars["disk"][0].set_value(disk.percent)
            self._bars["disk"][1].setText(f"{human_bytes(disk.used)} / {human_bytes(disk.total)}")
            self._bars["swap"][0].set_value(sw.percent)
            self._bars["swap"][1].setText(f"{human_bytes(sw.used)} / {human_bytes(sw.total)}")
            self._uptime.setText(f"已运行  {format_duration(time.time() - self._boot)}")

            cur = psutil.net_io_counters()
            now = time.time()
            if self._prev_net and now > self._prev_t:
                dt = max(0.05, now - self._prev_t)
                up = (cur.bytes_sent - self._prev_net.bytes_sent) / dt
                down = (cur.bytes_recv - self._prev_net.bytes_recv) / dt
                self._up.setText(f"↑ 上行  {human_bytes(up)}/s")
                self._down.setText(f"↓ 下行  {human_bytes(down)}/s")
            self._prev_net, self._prev_t = cur, now
        except Exception as exc:  # noqa: BLE001
            notify(self, f"读取性能数据失败：{exc}")

    def refresh_disk(self):
        parts = []
        try:
            for p in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    parts.append((p.device, p.fstype, u.total, u.used, u.percent))
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        if not parts:
            try:
                u = psutil.disk_usage("/")
                parts.append(("/", "-", u.total, u.used, u.percent))
            except Exception:  # noqa: BLE001
                parts = []
        parts = parts[:10]
        t = self._disk_table
        t.setRowCount(len(parts))
        for i, (dev, fs, total, used, pct) in enumerate(parts):
            self._set_row(t, i, (dev, fs, human_bytes(total), human_bytes(used), ""))
            bar = GlassProgress(height=10, show_text=True)
            bar.set_value(pct)
            t.setCellWidget(i, 4, bar)
        t.setFixedHeight(max(80, len(parts) * 32 + 40))

    def refresh_processes(self):
        w = Worker(_top_processes, 12)
        self._workers.append(w)
        w.done.connect(self._on_processes)
        w.failed.connect(lambda e: notify(self, f"读取进程失败：{e}"))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.start()

    def _on_processes(self, rows):
        t = self._proc_table
        t.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._set_row(t, i, row)
        t.setFixedHeight(max(80, len(rows) * 30 + 40))
