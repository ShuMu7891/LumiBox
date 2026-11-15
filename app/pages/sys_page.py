"""系统增强页：启动项/服务、定时任务、端口扫描测速、窗口与托盘控制。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtWidgets import QTabWidget, QListWidgetItem

from ..glass import PageScaffold, GlassCard, label
from .. import power as pw
from .common import (on_click, tab_container, row, btn, editor, mono, field,
                     combo, checkbox, spin, ask, warn, info_box, notify,
                     make_table, fill_table, start_worker)


class _Bridge(QObject):
    progress = Signal(int, int)


class SysPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("系统增强", "启动项与服务 · 定时任务 · 端口扫描 · 窗口控制", parent)
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_port_progress)
        self._port_stop = False
        self._startup_items: list[dict] = []
        self._services: list[dict] = []
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._remain = 0
        self._pending_action = ""

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._startup_tab(), "  启动项 & 服务  ")
        tabs.addTab(self._schedule_tab(), "  定时任务  ")
        tabs.addTab(self._net_tab(), "  端口扫描 & 测速  ")
        tabs.addTab(self._window_tab(), "  窗口 & 托盘  ")
        self.add_widget(tabs, 1)
        self._load_startup()
        self._load_services()

    # ================================================================ 启动项 / 服务
    def _startup_tab(self):
        w, lay = tab_container()
        card = GlassCard("开机启动项", "查看自启动程序；禁用前会保留原值，便于手动恢复", spacing=10)
        self._startup_table = make_table(["名称", "状态", "来源", "命令"])
        card.add(self._startup_table)
        rf = btn("刷新")
        dis = btn("禁用选中", True)
        en = btn("启用选中")
        cp = btn("复制命令")
        on_click(rf, self._load_startup)
        on_click(dis, lambda: self._toggle_startup(False))
        on_click(en, lambda: self._toggle_startup(True))
        on_click(cp, self._copy_startup_cmd)
        card.add_layout(row(rf, dis, en, cp))
        self._startup_status = label("", 9, False, True)
        card.add(self._startup_status)
        lay.addWidget(card)

        svc = GlassCard("系统服务", "列出服务状态；启动/停止操作通常需要管理员权限", spacing=10)
        self._svc_filter = field("", "按名称筛选服务")
        self._svc_filter.textChanged.connect(self._render_services)
        svc.add(self._svc_filter)
        self._svc_table = make_table(["服务名", "状态", "说明"])
        svc.add(self._svc_table)
        srf = btn("刷新服务")
        start = btn("启动")
        stop = btn("停止")
        restart = btn("重启")
        on_click(srf, self._load_services)
        on_click(start, lambda: self._service_act("start"))
        on_click(stop, lambda: self._service_act("stop"))
        on_click(restart, lambda: self._service_act("restart"))
        svc.add_layout(row(srf, start, stop, restart))
        self._svc_status = label("", 9, False, True)
        svc.add(self._svc_status)
        lay.addWidget(svc)
        lay.addStretch(1)
        return w

    def _load_startup(self):
        self._startup_items = pw.startup_items()
        rows = [[i["name"], "启用" if i["enabled"] else "已禁用", i["source"], i["command"]]
                for i in self._startup_items]
        fill_table(self._startup_table, rows, 28, 1200)
        self._startup_status.setText(f"共 {len(rows)} 项 · 平台：{'Windows' if pw.IS_WINDOWS else 'Linux/macOS'}"
                                     if rows else "未发现自启动项（或需要相应权限）")

    def _toggle_startup(self, enable: bool):
        row_idx = self._startup_table.currentRow()
        if row_idx < 0 or row_idx >= len(self._startup_items):
            notify(self, "请先选中一项")
            return
        item = self._startup_items[row_idx]
        if not ask(self, "确认", f"{'启用' if enable else '禁用'}「{item['name']}」？\n"
                                  "修改启动项可能影响系统行为，请谨慎操作。"):
            return
        r = pw.toggle_startup(item, enable)
        if r.get("ok"):
            notify(self, f"{item['name']} 已{'启用' if enable else '禁用'}")
            item["enabled"] = enable
            self._startup_status.setText(r.get("note", "操作已生效"))
            self._load_startup()
        else:
            warn(self, "操作失败", r.get("error", "未知错误"))

    def _copy_startup_cmd(self):
        row_idx = self._startup_table.currentRow()
        if 0 <= row_idx < len(self._startup_items):
            from .common import copy_text
            copy_text(self, self._startup_items[row_idx]["command"])

    def _load_services(self):
        self._services = pw.services()
        self._render_services()
        self._svc_status.setText(f"共 {len(self._services)} 个服务")

    def _render_services(self, *_):
        kw = self._svc_filter.text().strip().lower()
        rows = [[s["name"], s["status"], s["display"]]
                for s in self._services if not kw or kw in s["name"].lower() or kw in s["display"].lower()]
        fill_table(self._svc_table, rows[:200], 26, 1600)

    def _service_act(self, action: str):
        r = self._svc_table.currentRow()
        if r < 0:
            notify(self, "请先选中一个服务")
            return
        name = self._svc_table.item(r, 0).text()
        if not ask(self, "确认", f"对服务「{name}」执行 {action}？\n需要管理员权限，失败会显示错误输出。"):
            return
        res = pw.service_action(name, action)
        self._svc_status.setText(f"{res['command']} → {res.get('output', '')[:180]}")
        notify(self, f"服务操作{'成功' if res['ok'] else '失败'}")
        if res["ok"]:
            self._load_services()

    # ================================================================ 定时任务
    def _schedule_tab(self):
        w, lay = tab_container()
        card = GlassCard("定时提醒 / 定时关机", "倒计时在应用内运行；关机操作会调用系统命令，可随时取消", spacing=12)
        self._sched_min = spin(25, 1, 600, 100)
        self._sched_action = combo(["仅应用内提醒", "定时关机", "定时重启", "执行自定义命令"], "仅应用内提醒", 180)
        self._sched_cmd = field("", "自定义命令（选择「执行自定义命令」时生效）")
        self._sched_msg = field("休息一下，起来活动活动吧", "提醒内容")
        card.add_layout(row(label("时长", 10, True), self._sched_min, label("分钟"), self._sched_action))
        card.add(self._sched_msg)
        card.add(self._sched_cmd)

        self._sched_display = label("00:00", 34, True)
        self._sched_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.add(self._sched_display)
        self._sched_note = label("设置时长后点「开始」", 9, False, True)
        card.add(self._sched_note)

        go = btn("开始倒计时", True)
        cancel = btn("取消任务")
        sys_cancel = btn("取消系统已排定的关机")
        now_off = btn("立即取消关机命令")
        on_click(go, self._start_schedule)
        on_click(cancel, self._cancel_schedule)
        on_click(sys_cancel, self._cancel_system_shutdown)
        on_click(now_off, self._cancel_system_shutdown)
        card.add_layout(row(go, cancel, sys_cancel))
        lay.addWidget(card)

        info_card = GlassCard("说明", "", spacing=8)
        info_card.add(label("· 应用内提醒：倒计时结束弹出通知，不修改系统。", 9))
        info_card.add(label("· 定时关机/重启：倒计时结束时调用 shutdown 命令（Windows 为 /s /t，Linux 为 -h +分钟）。", 9))
        info_card.add(label("· 若系统已排定关机，点「取消系统已排定的关机」可执行 shutdown /a 撤回。", 9))
        info_card.add(label("· 自定义命令：倒计时结束执行你填写的命令，请谨慎填写。", 9))
        lay.addWidget(info_card)
        lay.addStretch(1)
        return w

    def _start_schedule(self):
        self._remain = self._sched_min.value() * 60
        self._pending_action = self._sched_action.currentText()
        self._timer.start()
        self._sched_note.setText(f"任务进行中：{self._pending_action}")
        notify(self, "倒计时已开始")
        self._tick()

    def _cancel_schedule(self):
        self._timer.stop()
        self._remain = 0
        self._sched_display.setText("00:00")
        self._sched_note.setText("已取消")
        notify(self, "定时任务已取消")

    def _tick(self):
        if self._remain <= 0:
            self._timer.stop()
            self._finish_schedule()
            return
        self._sched_display.setText(pw.human_countdown(self._remain))
        self._remain -= 1

    def _finish_schedule(self):
        action = self._pending_action
        self._sched_note.setText(f"任务完成：{action}")
        if action == "仅应用内提醒":
            info_box(self, "定时提醒", self._sched_msg.text() or "时间到！")
        elif action in ("定时关机", "定时重启"):
            cmd = pw.shutdown_command(60, "关机" if action == "定时关机" else "重启")
            r = pw.run_system_command(cmd)
            notify(self, f"已提交系统{'关机' if action == '定时关机' else '重启'}命令")
            self._sched_note.setText(f"{r['command']} → {r.get('output', '')[:120]}")
        elif action == "执行自定义命令":
            c = self._sched_cmd.text().strip()
            if c:
                try:
                    import subprocess
                    subprocess.Popen(c, shell=True)  # noqa: S602
                    notify(self, "自定义命令已执行")
                except Exception as exc:  # noqa: BLE001
                    warn(self, "执行失败", str(exc))
            else:
                notify(self, "未填写自定义命令")

    def _cancel_system_shutdown(self):
        r = pw.run_system_command(pw.cancel_shutdown_command())
        notify(self, "已发送取消关机命令")
        self._sched_note.setText(f"{r['command']} → {r.get('output', '')[:120]}")

    # ================================================================ 端口扫描 / 测速
    def _net_tab(self):
        w, lay = tab_container()
        card = GlassCard("端口扫描", "并发 TCP 连接探测；仅扫描你有权限的目标主机", spacing=10)
        self._port_host = field("127.0.0.1", "主机 IP 或域名")
        self._port_spec = field("常用端口", "如 80,443,8000-8100 或「常用端口」")
        self._port_timeout = combo(["0.3", "0.5", "1.0", "2.0"], "0.5", 90)
        self._port_threads = spin(120, 8, 512, 100)
        scan = btn("开始扫描", True)
        stop = btn("停止")
        on_click(scan, self._scan_ports)
        on_click(stop, lambda: setattr(self, "_port_stop", True))
        card.add_layout(row(label("主机", 10, True), self._port_host, self._port_spec))
        card.add_layout(row(label("超时", 10, True), self._port_timeout,
                            label("并发", 10, True), self._port_threads, scan, stop))
        self._port_status = label("尚未扫描", 9, False, True)
        card.add(self._port_status)
        self._port_table = make_table(["端口", "状态", "服务", "延迟(ms)", "目标 IP"])
        card.add(self._port_table)
        lay.addWidget(card)

        speed = GlassCard("网络测速", "TCP 连接延迟 + 下载吞吐量（需联网）", spacing=10)
        self._speed_host = field("www.baidu.com", "延迟测试主机")
        self._speed_port = spin(443, 1, 65535, 100)
        self._speed_url = combo(pw.SPEED_URLS, pw.SPEED_URLS[0], 300)
        lat = btn("测试延迟")
        dl = btn("测试下载速度")
        on_click(lat, self._test_latency)
        on_click(dl, self._test_download)
        speed.add_layout(row(label("主机", 10, True), self._speed_host,
                             label("端口", 10, True), self._speed_port, lat))
        speed.add_layout(row(label("测速源", 10, True), self._speed_url, dl))
        self._speed_out = editor("测速结果将显示在这里", 150, readonly=True)
        speed.add(self._speed_out)
        lay.addWidget(speed)
        lay.addStretch(1)
        return w

    def _on_port_progress(self, done, total):
        self._port_status.setText(f"扫描中… {done}/{total} 端口")

    def _scan_ports(self):
        host = self._port_host.text().strip()
        ports = pw.parse_port_spec(self._port_spec.text())
        if not ports:
            warn(self, "端口无效", "请输入有效的端口范围")
            return
        if len(ports) > 2000 and not ask(self, "确认", f"将扫描 {len(ports)} 个端口，可能较慢，继续？"):
            return
        self._port_stop = False
        self._port_status.setText("解析主机…")
        start_worker(self, pw.scan_ports,
                     (host, ports, float(self._port_timeout.currentText()),
                      self._port_threads.value(), self._bridge.progress.emit,
                      lambda: self._port_stop),
                     self._on_ports_done)

    def _on_ports_done(self, rows):
        rows = rows or []
        fill_table(self._port_table,
                   [[r["port"], r["state"], r["service"], r["latency"], r["ip"]] for r in rows],
                   28, 1400)
        self._port_status.setText(f"扫描结束：发现 {len(rows)} 个开放端口")

    def _test_latency(self):
        host = self._speed_host.text().strip()
        port = self._speed_port.value()
        self._speed_out.setPlainText(f"正在测试 {host}:{port} …")
        start_worker(self, pw.tcp_latency, (host, port, 4, 1.5), self._on_latency_done)

    def _on_latency_done(self, r):
        if not r.get("ok"):
            self._speed_out.setPlainText(f"测试失败：{r.get('error', '全部超时')}")
            return
        self._speed_out.setPlainText(
            f"TCP 延迟测试  {r['host']} ({r['ip']}):{r['port']}\n"
            f"样本(ms)：{r['samples']}\n"
            f"最小 {r['min']} ms  ·  平均 {r['avg']} ms  ·  最大 {r['max']} ms  ·  丢包 {r['loss']}%")

    def _test_download(self):
        url = self._speed_url.currentText().strip()
        self._speed_out.setPlainText(f"正在从测速源下载…\n{url}")
        start_worker(self, pw.download_speed, (url, 8.0), self._on_speed_done)

    def _on_speed_done(self, r):
        if not r.get("ok"):
            self._speed_out.setPlainText(f"下载测速失败：{r.get('error')}")
            return
        self._speed_out.setPlainText(
            f"下载测速  {r['url']}\n"
            f"已下载 {r['bytes'] / 1024 / 1024:.2f} MB  ·  用时 {r['seconds']} s\n"
            f"≈ {r['mbps']} Mbps（{r['mbs']} MB/s）")

    # ================================================================ 窗口 / 托盘
    def _window_tab(self):
        w, lay = tab_container()
        card = GlassCard("窗口控制", "对 LumiBox 主窗口生效", spacing=12)
        self._on_top = checkbox("窗口置顶（始终显示在最前）", False)
        self._on_top.stateChanged.connect(self._apply_on_top)
        card.add(self._on_top)
        self._opacity = spin(100, 30, 100, 100, "")
        self._opacity.setSuffix(" %")
        self._opacity.valueChanged.connect(self._apply_opacity)
        card.add_layout(row(label("窗口不透明度", 10, True), self._opacity))
        lay.addWidget(card)

        tray = GlassCard("系统托盘 & 全局快捷键", "托盘常驻后可隐藏窗口，随时用快捷键或双击托盘唤出", spacing=10)
        tray.add(label("· 主窗口标题栏最小化 / 关闭时，可通过托盘菜单再次显示。", 9))
        tray.add(label("· Ctrl + 1 ~ 9 快速切换前 9 个页面；托盘菜单提供常用工具直达。", 9))
        tray.add(label("· 全局热键（应用获得焦点时）：Ctrl+Alt+S 截图，Ctrl+` 显示/隐藏窗口。", 9))
        hide = btn("隐藏到托盘")
        show = btn("显示窗口")
        on_click(hide, self._hide_to_tray)
        on_click(show, self._show_window)
        tray.add_layout(row(hide, show))
        self._tray_status = label("", 9, False, True)
        tray.add(self._tray_status)
        self._check_tray()
        lay.addWidget(tray)
        lay.addStretch(1)
        return w

    def _win(self):
        return self.window()

    def _apply_on_top(self, *_):
        fn = getattr(self._win(), "set_always_on_top", None)
        if callable(fn):
            fn(self._on_top.isChecked())

    def _apply_opacity(self, value):
        fn = getattr(self._win(), "set_opacity", None)
        if callable(fn):
            fn(value / 100.0)

    def _hide_to_tray(self):
        fn = getattr(self._win(), "hide_to_tray", None)
        if callable(fn):
            fn()
            notify(self, "已隐藏到系统托盘")
        else:
            notify(self, "当前环境不支持系统托盘")

    def _show_window(self):
        fn = getattr(self._win(), "show_from_tray", None)
        if callable(fn):
            fn()

    def _check_tray(self):
        from PySide6.QtWidgets import QSystemTrayIcon
        ok = QSystemTrayIcon.isSystemTrayAvailable()
        self._tray_status.setText("系统托盘：可用" if ok else "系统托盘：当前环境不可用（Windows 11 正常可用）")
