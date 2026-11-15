"""网络与效率页：二维码、时间戳、密码、计算器、单位换算、IP 检测。"""
from __future__ import annotations

import io
import math
import secrets
import socket
import string
import time
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QGridLayout, QLineEdit, QTextEdit,
                              QComboBox, QCheckBox, QSlider, QSpinBox, QLabel, QFileDialog,
                              QColorDialog, QSizePolicy)
from PySide6.QtGui import QColor

from ..glass import (PageScaffold, GlassCard, GlassButton, label, copy_button, divider, notify)
from ..utils import Worker, safe_eval, human_bytes, set_clipboard, pil_to_pixmap

from .image_page import ColorSwatch


# ---------------------------------------------------------------- 单位定义
UNITS = {
    "长度": {"米": 1, "千米": 1000, "厘米": 0.01, "毫米": 0.001,
             "英寸": 0.0254, "英尺": 0.3048, "英里": 1609.344, "海里": 1852},
    "质量": {"千克": 1, "克": 0.001, "毫克": 1e-6, "吨": 1000,
             "磅": 0.45359237, "盎司": 0.0283495231},
    "数据存储": {"字节": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3,
                 "TB": 1024 ** 4, "bit": 0.125},
    "时间": {"秒": 1, "毫秒": 0.001, "微秒": 1e-6, "分钟": 60,
             "小时": 3600, "天": 86400, "周": 604800},
    "面积": {"平方米": 1, "平方千米": 1e6, "平方厘米": 1e-4, "公顷": 10000,
             "亩": 666.6667, "平方英尺": 0.09290304},
    "速度": {"米/秒": 1, "千米/小时": 1 / 3.6, "英里/小时": 0.44704, "节": 0.514444},
    "温度": {"摄氏度": 1, "华氏度": 1, "开尔文": 1},
}


def _to_celsius(value: float, unit: str) -> float:
    if unit == "摄氏度":
        return value
    if unit == "华氏度":
        return (value - 32) * 5 / 9
    return value - 273.15


def _from_celsius(value: float, unit: str) -> float:
    if unit == "摄氏度":
        return value
    if unit == "华氏度":
        return value * 9 / 5 + 32
    return value + 273.15


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return "无法获取"


def _public_ip() -> str:
    import requests
    r = requests.get("https://api.ipify.org?format=json", timeout=(1.5, 2.5))
    r.raise_for_status()
    return r.json().get("ip", "未知")


def _check_url(url: str) -> str:
    import requests
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    t0 = time.time()
    r = requests.get(url, timeout=(2, 4), allow_redirects=True, stream=True)
    cost = (time.time() - t0) * 1000
    return (f"状态码   {r.status_code} {r.reason}\n"
            f"耗时     {cost:.0f} ms\n"
            f"最终地址 {r.url}\n"
            f"类型     {r.headers.get('Content-Type', '未知')}\n"
            f"大小     {r.headers.get('Content-Length', '未知')}")


def _make_qr(text: str, level: str, box: int, fg: str, bg: str):
    import qrcode
    levels = {
        "L · 低 (7%)": qrcode.constants.ERROR_CORRECT_L,
        "M · 中 (15%)": qrcode.constants.ERROR_CORRECT_M,
        "Q · 较高 (25%)": qrcode.constants.ERROR_CORRECT_Q,
        "H · 高 (30%)": qrcode.constants.ERROR_CORRECT_H,
    }
    qr = qrcode.QRCode(error_correction=levels[level], box_size=box, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fg, back_color=bg)
    pil = img.get_image() if hasattr(img, "get_image") else img
    return pil.convert("RGB")


class NetPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("网络与效率", "二维码 · 时间戳 · 密码 · 计算器 · 单位换算 · IP 检测", parent)
        self._workers = []
        self._qr_image = None
        self._qr_fg = "#172132"
        self._qr_bg = "#FFFFFF"
        self._qr_timer = QTimer(self)
        self._qr_timer.setSingleShot(True)
        self._qr_timer.setInterval(350)
        self._qr_timer.timeout.connect(self._generate_qr)

        row1 = QHBoxLayout()
        row1.setSpacing(16)
        row1.addWidget(self._qr_card(), 1)
        row1.addWidget(self._timestamp_card(), 1)
        self.add_layout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(16)
        row2.addWidget(self._password_card(), 1)
        row2.addWidget(self._calc_card(), 1)
        self.add_layout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(16)
        row3.addWidget(self._unit_card(), 1)
        row3.addWidget(self._ip_card(), 1)
        self.add_layout(row3)
        self.add_stretch(1)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)
        self._clock.start()
        self._tick()
        self._generate_qr()
        self._generate_passwords()
        self._convert_unit()
        self._fill_ip()

    def _button_row(self, *buttons) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        for b in buttons:
            row.addWidget(b)
        return row

    # ================================================================ 二维码
    def _qr_card(self):
        card = GlassCard("二维码生成器", "完全离线生成，内容不会上传到任何服务器", spacing=10)
        self._qr_text = QTextEdit()
        self._qr_text.setPlaceholderText("输入网址、文本、Wi-Fi 信息等…")
        self._qr_text.setMaximumHeight(76)
        self._qr_text.setPlainText("https://example.com")
        self._qr_text.textChanged.connect(lambda: self._qr_timer.start())
        card.add(self._qr_text)

        opt = QHBoxLayout()
        opt.setSpacing(8)
        self._qr_level = QComboBox()
        self._qr_level.addItems(["L · 低 (7%)", "M · 中 (15%)", "Q · 较高 (25%)", "H · 高 (30%)"])
        self._qr_level.currentIndexChanged.connect(lambda: self._qr_timer.start())
        opt.addWidget(self._qr_level, 1)
        opt.addWidget(label("尺寸", 9))
        self._qr_size = QSlider(Qt.Orientation.Horizontal)
        self._qr_size.setRange(4, 14)
        self._qr_size.setValue(8)
        self._qr_size.setFixedWidth(90)
        self._qr_size.valueChanged.connect(lambda: self._qr_timer.start())
        opt.addWidget(self._qr_size)
        card.add_layout(opt)

        colors = QHBoxLayout()
        colors.setSpacing(8)
        colors.addWidget(label("前景", 9))
        self._fg_swatch = ColorSwatch(self._qr_fg, 28)
        self._fg_swatch.clicked.connect(self._choose_fg)
        colors.addWidget(self._fg_swatch)
        colors.addWidget(label("背景", 9))
        self._bg_swatch = ColorSwatch(self._qr_bg, 28)
        self._bg_swatch.clicked.connect(self._choose_bg)
        colors.addWidget(self._bg_swatch)
        colors.addStretch(1)
        card.add_layout(colors)

        self._qr_preview = QLabel("生成中…")
        self._qr_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_preview.setMinimumHeight(190)
        self._qr_preview.setStyleSheet("background: rgba(255,255,255,0.55); border-radius: 12px; padding: 10px;")
        card.add(self._qr_preview)

        save = GlassButton("保存 PNG")
        save.clicked.connect(self._save_qr)
        card.add_layout(self._button_row(save))
        return card

    def _choose_fg(self, _=None):
        c = QColorDialog.getColor(QColor(self._qr_fg), self, "选择二维码前景色")
        if c.isValid():
            self._qr_fg = c.name()
            self._fg_swatch.set_color(self._qr_fg)
            self._generate_qr()

    def _choose_bg(self, _=None):
        c = QColorDialog.getColor(QColor(self._qr_bg), self, "选择二维码背景色")
        if c.isValid():
            self._qr_bg = c.name()
            self._bg_swatch.set_color(self._qr_bg)
            self._generate_qr()

    def _generate_qr(self):
        text = self._qr_text.toPlainText().strip()
        if not text:
            self._qr_preview.setText("请输入要编码的内容")
            self._qr_image = None
            return
        try:
            img = _make_qr(text, self._qr_level.currentText(), self._qr_size.value(),
                           self._qr_fg, self._qr_bg)
            self._qr_image = img
            pm = pil_to_pixmap(img)
            maxw = max(160, self._qr_preview.width() - 24)
            shown = pm.scaled(maxw, 178, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.FastTransformation)
            self._qr_preview.setPixmap(shown)
        except Exception as exc:  # noqa: BLE001
            self._qr_preview.setText(f"生成失败：{exc}")

    def _save_qr(self):
        if self._qr_image is None:
            notify(self, "请先生成二维码")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存二维码", "qrcode.png", "PNG 图片 (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            self._qr_image.save(path, "PNG")
            notify(self, "二维码已保存")
        except Exception as exc:  # noqa: BLE001
            notify(self, f"保存失败：{exc}")

    # ================================================================ 时间戳
    def _timestamp_card(self):
        card = GlassCard("时间戳换算", "Unix 时间戳与日期时间双向转换", spacing=12)
        self._ts_now = label("", 14, True)
        card.add(self._ts_now)

        opt = QHBoxLayout()
        opt.addWidget(label("单位", 9, True))
        self._ts_unit = QComboBox()
        self._ts_unit.addItems(["秒 (10 位)", "毫秒 (13 位)", "微秒 (16 位)"])
        opt.addWidget(self._ts_unit, 1)
        self._ts_utc = QCheckBox("使用 UTC")
        opt.addWidget(self._ts_utc)
        card.add_layout(opt)

        card.addWidget(label("时间戳 → 日期", 10, True))
        line1 = QHBoxLayout()
        self._ts_in = QLineEdit()
        self._ts_in.setPlaceholderText("输入时间戳…")
        line1.addWidget(self._ts_in, 1)
        to_date = GlassButton("转换", primary=True)
        to_date.setFixedWidth(76)
        to_date.clicked.connect(self._ts_to_date)
        line1.addWidget(to_date)
        card.add_layout(line1)
        self._ts_date_out = QLineEdit()
        self._ts_date_out.setReadOnly(True)
        self._ts_date_out.setPlaceholderText("转换结果…")
        card.add(self._ts_date_out)

        card.addWidget(label("日期 → 时间戳", 10, True))
        line2 = QHBoxLayout()
        self._date_in = QLineEdit()
        self._date_in.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        line2.addWidget(self._date_in, 1)
        now_btn = GlassButton("现在")
        now_btn.setFixedWidth(60)
        now_btn.clicked.connect(lambda: self._date_in.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        line2.addWidget(now_btn)
        to_ts = GlassButton("转换", primary=True)
        to_ts.setFixedWidth(76)
        to_ts.clicked.connect(self._date_to_ts)
        line2.addWidget(to_ts)
        card.add_layout(line2)
        self._ts_out = QLineEdit()
        self._ts_out.setReadOnly(True)
        self._ts_out.setPlaceholderText("转换结果…")
        card.add(self._ts_out)
        card.add_layout(self._button_row(
            copy_button(self, lambda: self._ts_now.text(), "复制当前时间戳"),
            copy_button(self, lambda: self._ts_out.text(), "复制结果")))
        card.body().addStretch(1)
        return card

    def _unit_factor(self) -> float:
        return [1, 1000, 1_000_000][self._ts_unit.currentIndex()]

    def _tick(self):
        now = time.time()
        f = self._unit_factor()
        self._ts_now.setText(f"当前时间戳  {int(now * f)}")

    def _ts_to_date(self):
        try:
            v = float(self._ts_in.text().strip()) / self._unit_factor()
            dt = (datetime.fromtimestamp(v, timezone.utc) if self._ts_utc.isChecked()
                  else datetime.fromtimestamp(v))
            self._ts_date_out.setText(dt.strftime("%Y-%m-%d %H:%M:%S") + ("  UTC" if self._ts_utc.isChecked() else "  本地"))
        except Exception as exc:  # noqa: BLE001
            notify(self, f"转换失败：{exc}")

    def _date_to_ts(self):
        try:
            s = self._date_in.text().strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            if self._ts_utc.isChecked():
                dt = dt.replace(tzinfo=timezone.utc)
            self._ts_out.setText(str(int(dt.timestamp() * self._unit_factor())))
        except Exception as exc:  # noqa: BLE001
            notify(self, f"日期格式应为 YYYY-MM-DD HH:MM:SS（{exc}）")

    # ================================================================ 密码
    def _password_card(self):
        card = GlassCard("强密码生成器", "使用系统安全随机源（secrets），不联网、不记录", spacing=12)
        row = QHBoxLayout()
        row.addWidget(label("长度", 10, True))
        self._pwd_len = QSlider(Qt.Orientation.Horizontal)
        self._pwd_len.setRange(8, 64)
        self._pwd_len.setValue(20)
        self._pwd_len.valueChanged.connect(self._generate_passwords)
        row.addWidget(self._pwd_len, 1)
        self._pwd_len_lbl = label("20", 10, True)
        row.addWidget(self._pwd_len_lbl)
        card.add_layout(row)

        checks = QHBoxLayout()
        self._pwd_upper = QCheckBox("A-Z")
        self._pwd_lower = QCheckBox("a-z")
        self._pwd_digit = QCheckBox("0-9")
        self._pwd_symbol = QCheckBox("!@#$")
        for c in (self._pwd_upper, self._pwd_lower, self._pwd_digit, self._pwd_symbol):
            c.setChecked(True)
            c.stateChanged.connect(self._generate_passwords)
            checks.addWidget(c)
        checks.addStretch(1)
        card.add_layout(checks)
        self._pwd_exclude = QCheckBox("排除易混淆字符（0/O/1/l/I）")
        self._pwd_exclude.stateChanged.connect(self._generate_passwords)
        card.add(self._pwd_exclude)

        self._pwd_out = QTextEdit()
        self._pwd_out.setReadOnly(True)
        self._pwd_out.setMinimumHeight(110)
        card.add(self._pwd_out)
        self._pwd_strength = label("", 9, False, True)
        card.add(self._pwd_strength)

        gen = GlassButton("重新生成", primary=True)
        gen.clicked.connect(self._generate_passwords)
        card.add_layout(self._button_row(gen,
                                        copy_button(self, lambda: self._pwd_out.toPlainText(), "复制全部")))
        card.body().addStretch(1)
        return card

    def _generate_passwords(self):
        length = self._pwd_len.value()
        self._pwd_len_lbl.setText(str(length))
        pool = ""
        if self._pwd_upper.isChecked():
            pool += string.ascii_uppercase
        if self._pwd_lower.isChecked():
            pool += string.ascii_lowercase
        if self._pwd_digit.isChecked():
            pool += string.digits
        if self._pwd_symbol.isChecked():
            pool += "!@#$%^&*()-_=+[]{};:,.?"
        if self._pwd_exclude.isChecked():
            pool = "".join(ch for ch in pool if ch not in "0O1lI")
        if not pool:
            self._pwd_out.setPlainText("请至少勾选一种字符类型")
            self._pwd_strength.setText("")
            return
        lines = ["".join(secrets.choice(pool) for _ in range(length)) for _ in range(5)]
        self._pwd_out.setPlainText("\n".join(lines))
        bits = length * math.log2(len(pool))
        level = "较弱" if bits < 50 else ("良好" if bits < 80 else ("很强" if bits < 120 else "极强"))
        self._pwd_strength.setText(f"字符集 {len(pool)} 种 · 熵约 {bits:.0f} bit · 强度：{level} · 每次生成 5 条")

    # ================================================================ 计算器
    def _calc_card(self):
        card = GlassCard("科学计算器", "支持 + - * / % ^ 与常用数学函数，AST 白名单求值", spacing=12)
        self._calc_in = QLineEdit()
        self._calc_in.setPlaceholderText("例如：sqrt(2) * 10 + sin(pi/6)")
        self._calc_in.returnPressed.connect(self._calculate)
        card.add(self._calc_in)
        self._calc_out = label("结果：—", 16, True)
        card.add(self._calc_out)

        quick = QGridLayout()
        quick.setSpacing(8)
        for i, (text, ins) in enumerate([
            ("sqrt(", "sqrt("), ("pow(", "pow("), ("π", "pi"), ("^ 幂", "**"),
            ("sin(", "sin("), ("cos(", "cos("), ("log(", "log("), ("清空", ""),
        ]):
            b = GlassButton(text)
            b.setFixedHeight(32)
            b.clicked.connect(lambda checked=False, s=ins: self._insert_calc(s))
            quick.addWidget(b, i // 4, i % 4)
        card.add_layout(quick)

        eq = GlassButton("= 计算", primary=True)
        eq.clicked.connect(self._calculate)
        card.add_layout(self._button_row(copy_button(self, lambda: self._calc_out.text().replace("结果：", ""), "复制结果"), eq))
        self._calc_history = label("", 9, False, True)
        card.add(self._calc_history)
        card.addWidget(label("可用函数：sqrt abs round pow sin cos tan asin acos atan log log10 log2 exp floor ceil min max", 8, False, True))
        card.body().addStretch(1)
        return card

    def _insert_calc(self, s: str):
        if not s:
            self._calc_in.clear()
            self._calc_out.setText("结果：—")
            return
        self._calc_in.insert(s)
        self._calc_in.setFocus()

    def _calculate(self):
        expr = self._calc_in.text().strip()
        try:
            value = safe_eval(expr)
            text = f"{value:.10g}"
            self._calc_out.setText(f"结果：{text}")
            self._calc_history.setText(f"最近：{expr} = {text}")
            set_clipboard(text)
        except Exception as exc:  # noqa: BLE001
            self._calc_out.setText("结果：计算出错")
            notify(self, f"计算失败：{exc}")

    # ================================================================ 单位换算
    def _unit_card(self):
        card = GlassCard("单位换算", "长度 / 质量 / 温度 / 存储 / 时间 / 面积 / 速度", spacing=12)
        cat = QHBoxLayout()
        cat.addWidget(label("类别", 10, True))
        self._unit_cat = QComboBox()
        self._unit_cat.addItems(list(UNITS.keys()))
        self._unit_cat.currentIndexChanged.connect(self._on_cat_changed)
        cat.addWidget(self._unit_cat, 1)
        card.add_layout(cat)

        row = QHBoxLayout()
        self._unit_from = QComboBox()
        self._unit_to = QComboBox()
        self._unit_from.currentIndexChanged.connect(self._convert_unit)
        self._unit_to.currentIndexChanged.connect(self._convert_unit)
        row.addWidget(self._unit_from, 1)
        swap = GlassButton("⇄")
        swap.setFixedWidth(44)
        swap.clicked.connect(self._swap_units)
        row.addWidget(swap)
        row.addWidget(self._unit_to, 1)
        card.add_layout(row)

        self._unit_in = QLineEdit()
        self._unit_in.setPlaceholderText("输入数值…")
        self._unit_in.setText("1")
        self._unit_in.textChanged.connect(self._convert_unit)
        card.add(self._unit_in)
        self._unit_out = QLineEdit()
        self._unit_out.setReadOnly(True)
        self._unit_out.setPlaceholderText("换算结果…")
        card.add(self._unit_out)
        card.add_layout(self._button_row(copy_button(self, lambda: self._unit_out.text(), "复制结果")))

        presets = QHBoxLayout()
        for v in ("1", "10", "100", "1024"):
            b = GlassButton(v)
            b.setFixedHeight(30)
            b.clicked.connect(lambda checked=False, x=v: self._unit_in.setText(x))
            presets.addWidget(b)
        presets.addStretch(1)
        card.add_layout(presets)
        self._on_cat_changed()
        card.body().addStretch(1)
        return card

    def _on_cat_changed(self, *_):
        units = list(UNITS[self._unit_cat.currentText()].keys())
        for combo in (self._unit_from, self._unit_to):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(units)
            combo.blockSignals(False)
        if len(units) > 1:
            self._unit_to.setCurrentIndex(1)
        self._convert_unit()

    def _swap_units(self):
        a, b = self._unit_from.currentIndex(), self._unit_to.currentIndex()
        self._unit_from.setCurrentIndex(b)
        self._unit_to.setCurrentIndex(a)

    def _convert_unit(self, *_):
        cat = self._unit_cat.currentText()
        frm, to = self._unit_from.currentText(), self._unit_to.currentText()
        if not frm or not to:
            return
        try:
            value = float(self._unit_in.text().strip() or "0")
            if cat == "温度":
                result = _from_celsius(_to_celsius(value, frm), to)
            else:
                result = value * UNITS[cat][frm] / UNITS[cat][to]
            self._unit_out.setText(f"{result:.10g}")
        except Exception:  # noqa: BLE001
            self._unit_out.setText("请输入有效数值")

    # ================================================================ IP / 网络
    def _ip_card(self):
        card = GlassCard("IP 与网络检测", "本机网络标识与网址可达性测试", spacing=12)
        self._ip_local = label("", 10, True)
        self._ip_public = label("公网 IP  获取中…", 10, True)
        card.add(self._ip_local)
        card.add(self._ip_public)

        row = QHBoxLayout()
        row.addWidget(label("网址", 10, True))
        self._url_in = QLineEdit()
        self._url_in.setPlaceholderText("example.com")
        self._url_in.setText("www.baidu.com")
        self._url_in.returnPressed.connect(self._test_url)
        row.addWidget(self._url_in, 1)
        card.add_layout(row)
        test = GlassButton("测试连接", primary=True)
        test.clicked.connect(self._test_url)
        card.add_layout(self._button_row(test))
        self._url_out = QTextEdit()
        self._url_out.setReadOnly(True)
        self._url_out.setMinimumHeight(140)
        self._url_out.setPlaceholderText("检测结果…")
        card.add(self._url_out)
        card.body().addStretch(1)
        return card

    def _fill_ip(self):
        local = _local_ip()
        self._ip_local.setText(f"本机内网 IP  {local}")
        w = Worker(_public_ip)
        self._workers.append(w)
        w.done.connect(lambda ip: self._ip_public.setText(f"公网 IP  {ip}"))
        w.failed.connect(lambda e: self._ip_public.setText("公网 IP  获取失败（可能离线）"))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.start()

    def _test_url(self):
        url = self._url_in.text().strip()
        if not url:
            notify(self, "请输入网址")
            return
        self._url_out.setPlainText("正在请求…")
        w = Worker(_check_url, url)
        self._workers.append(w)
        w.done.connect(lambda text: self._url_out.setPlainText(str(text)))
        w.failed.connect(lambda e: self._url_out.setPlainText(f"请求失败：{e}\n请检查网络或网址是否正确。"))
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.start()
