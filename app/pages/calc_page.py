"""计算器页：标准四则、科学函数、程序员模式（进制/位运算/位视图）与计算历史。"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QPen
from PySide6.QtWidgets import (QTabWidget, QLineEdit, QGridLayout, QComboBox, QListWidget,
                               QListWidgetItem, QWidget, QSizePolicy)

from ..glass import PageScaffold, GlassCard, label, divider, notify
from ..utils import safe_eval
from .. import extra
from .. import theme
from .common import (on_click, changed, tab_container, row, btn, editor, mono,
                      copy_text, export_text, make_table, fill_table)


def _fmt(value) -> str:
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e16:
            return str(int(value))
        return f"{value:.12g}"
    return str(value)


# ================================================================ 位视图
class BitView(QWidget):
    """把数值按位画成方块阵列，高位在左，每 4 位一组。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._width = 32
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value: int, width: int = 32):
        self._value = int(value)
        self._width = int(width)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme.CURRENT
        n = self._width
        gap = 2
        cell = max(4.0, (self.width() - gap * (n - 1)) / n)
        h = 24.0
        f = QFont()
        f.setPointSize(7)
        p.setFont(f)
        accent = QColor(t["qss"]["accent"])
        for i in range(n):
            bit_index = n - 1 - i
            on = bool((self._value >> bit_index) & 1)
            x = i * (cell + gap)
            rect = QRectF(x, 4, cell, h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent if on else QColor(*t["slot"]))
            p.drawRoundedRect(rect, 3, 3)
            if i % 4 == 0 and n <= 32:
                p.setPen(QColor(t["dim"]))
                p.drawText(QRectF(x - 2, h + 7, 34, 14),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           str(bit_index))
            if on and cell >= 12:
                p.setPen(QColor("#ffffff"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "1")
        p.end()


# ================================================================ 页面
class CalcPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("计算器", "标准 · 科学 · 程序员（进制 / 位运算）", parent)
        self._history: list[tuple[str, str]] = []

        disp = GlassCard("计算器", "支持键盘直接输入，回车即算；所有运算在本地完成", spacing=10)
        self._expr = QLineEdit("")
        self._expr.setPlaceholderText("输入表达式，例如  2 + 3 * 4  或  sqrt(2) ** 8")
        f = QFont()
        f.setPointSize(15)
        self._expr.setFont(f)
        self._expr.setMinimumHeight(46)
        self._expr.returnPressed.connect(self._equals)
        disp.add(self._expr)
        self._result = label("0", 26, True)
        self._result.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        disp.add(self._result)
        self.add_card(disp)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._standard_tab(), "  标准  ")
        self._tabs.addTab(self._science_tab(), "  科学  ")
        self._tabs.addTab(self._programmer_tab(), "  程序员  ")
        self.add_widget(self._tabs, 1)

        hist = GlassCard("计算历史", "点击任意记录可回填表达式", spacing=10)
        self._hist_list = QListWidget()
        self._hist_list.setMinimumHeight(130)
        self._hist_list.itemClicked.connect(
            lambda item: self._expr.setText(item.data(Qt.ItemDataRole.UserRole)))
        hist.add(self._hist_list)
        c = btn("清空历史")
        e = btn("导出历史")
        on_click(c, self._clear_history)
        on_click(e, self._export_history)
        hist.add_layout(row(c, e))
        self.add_card(hist)

    # ---------------------------------------------------------------- 键盘
    def _numpad(self, parent_layout, with_parens: bool = False):
        grid = QGridLayout()
        grid.setSpacing(8)
        keys = [
            [("C", "clear"), ("⌫", "back"), ("( )", "paren"), ("÷", "/")],
            [("7", "7"), ("8", "8"), ("9", "9"), ("×", "*")],
            [("4", "4"), ("5", "5"), ("6", "6"), ("−", "-")],
            [("1", "1"), ("2", "2"), ("3", "3"), ("+", "+")],
            [("±", "neg"), ("0", "0"), (".", "."), ("=", "equals")],
        ]
        if not with_parens:
            keys[0][2] = ("%", "%")
        for r, line in enumerate(keys):
            for c, (text, action) in enumerate(line):
                b = btn(text, primary=(action == "equals"))
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                b.setMinimumHeight(42)
                if action == "equals":
                    on_click(b, self._equals)
                elif action in ("clear", "back", "neg", "paren", "%"):
                    on_click(b, self._special, action)
                else:
                    on_click(b, self._insert, action)
                grid.addWidget(b, r, c)
        parent_layout.addLayout(grid)

    def _standard_tab(self):
        w, lay = tab_container()
        card = GlassCard("标准模式", "四则运算、百分比、正负号与退格", spacing=10)
        self._numpad(card.body(), with_parens=False)
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    def _science_tab(self):
        w, lay = tab_container()
        funcs = GlassCard("科学函数", "点击插入到表达式（AST 白名单求值，不使用 eval）", spacing=8)
        grid = QGridLayout()
        grid.setSpacing(8)
        items = [
            ("sin", "sin("), ("cos", "cos("), ("tan", "tan("), ("asin", "asin("), ("acos", "acos("), ("atan", "atan("),
            ("ln", "log("), ("log₁₀", "log10("), ("log₂", "log2("), ("eˣ", "exp("), ("√", "sqrt("), ("x²", "**2"),
            ("xʸ", "**"), ("abs", "abs("), ("floor", "floor("), ("ceil", "ceil("), ("π", "pi"), ("e", "e"),
        ]
        for i, (text, ins) in enumerate(items):
            b = btn(text)
            b.setMinimumHeight(36)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            on_click(b, self._insert, ins)
            grid.addWidget(b, i // 6, i % 6)
        funcs.add_layout(grid)
        lay.addWidget(funcs)
        num = GlassCard("数字键盘", "", spacing=10)
        self._numpad(num.body(), with_parens=True)
        lay.addWidget(num)
        lay.addStretch(1)
        return w

    def _programmer_tab(self):
        w, lay = tab_container()
        card = GlassCard("程序员模式", "支持 0x / 0b / 0o 前缀，AND OR XOR NOT 与移位运算", spacing=10)
        self._prog_width = QComboBox()
        self._prog_width.addItems(["8", "16", "32", "64"])
        self._prog_width.setCurrentText("32")
        self._prog_width.setMinimumWidth(90)
        card.add_layout(row(label("位宽", 10, True), self._prog_width))
        ops = [("AND", "&"), ("OR", "|"), ("XOR", "^"), ("NOT ~", "~"),
               ("<< 左移", "<<"), (">> 右移", ">>"), ("+", "+"), ("−", "-"),
               ("×", "*"), ("÷", "//"), ("H 0x", "0x"), ("B 0b", "0b")]
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (text, ins) in enumerate(ops):
            b = btn(text)
            b.setMinimumHeight(36)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            on_click(b, self._insert_prog, ins)
            grid.addWidget(b, i // 6, i % 6)
        card.add_layout(grid)
        go = btn("= 计算", True)
        on_click(go, self._equals)
        card.add_layout(row(go))
        self._prog_table = make_table(["进制", "结果"])
        card.add(self._prog_table)
        self._bits = BitView()
        card.add(self._bits)
        card.add(label("位视图：高位在左，每 4 位一组；蓝色代表 1。", 9, False, True))
        changed(self._prog_width, "currentIndexChanged", lambda: self._refresh_bits())
        self._refresh_bits()
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- 交互
    def _insert(self, text: str):
        self._expr.insert(text)
        self._expr.setFocus()

    def _insert_prog(self, text: str):
        cur = self._expr.text().strip()
        if text == "~":
            self._expr.setText("~ " + cur if cur else "~ ")
        else:
            self._expr.setText((cur + " " if cur else "") + text + " ")
        self._expr.setFocus()

    def _special(self, action: str):
        cur = self._expr.text()
        if action == "clear":
            self._expr.clear()
            self._result.setText("0")
        elif action == "back":
            self._expr.setText(cur[:-1])
        elif action == "neg":
            self._expr.setText(cur[1:] if cur.startswith("-") else "-" + cur)
        elif action == "paren":
            self._expr.insert("(" if cur.count("(") <= cur.count(")") else ")")
        elif action == "%":
            self._expr.insert("*0.01")
        self._expr.setFocus()

    def _equals(self):
        expr = self._expr.text().strip()
        if not expr:
            return
        try:
            if self._tabs.currentIndex() == 2:
                value = self._prog_eval(expr, int(self._prog_width.currentText()))
            else:
                value = safe_eval(expr)
            text = _fmt(value)
            self._result.setText(text)
            self._history.insert(0, (expr, text))
            self._history = self._history[:50]
            self._render_history()
            if self._tabs.currentIndex() == 2:
                self._refresh_bits(value)
        except Exception as exc:  # noqa: BLE001
            self._result.setText("错误")
            notify(self, f"计算失败：{exc}")

    @staticmethod
    def _prog_eval(expr: str, width: int) -> int:
        """解析 'A op B' / '~ A' / 单值，返回按位宽截断的无符号整数。"""
        parts = expr.replace("×", "*").replace("÷", "//").replace("−", "-").split()
        if len(parts) == 1:
            val = extra.parse_number(parts[0])
        elif len(parts) == 2 and parts[0] in ("~", "NOT", "-"):
            val = ~extra.parse_number(parts[1]) if parts[0] != "-" else -extra.parse_number(parts[1])
        elif len(parts) == 3:
            a, op, b = extra.parse_number(parts[0]), parts[1], extra.parse_number(parts[2])
            ops = {"&": lambda x, y: x & y, "|": lambda x, y: x | y,
                   "^": lambda x, y: x ^ y, "<<": lambda x, y: x << min(y, 1024),
                   ">>": lambda x, y: x >> min(y, 1024), "+": lambda x, y: x + y,
                   "-": lambda x, y: x - y, "*": lambda x, y: x * y,
                   "//": lambda x, y: x // y if y else 0}
            if op not in ops:
                raise ValueError(f"不支持的运算符 {op}")
            val = ops[op](a, b)
        else:
            raise ValueError("格式应为：数值  或  A 运算符 B（空格分隔）")
        return val & ((1 << width) - 1)

    def _refresh_bits(self, value=None):
        try:
            v = int(self._result.text()) if value is None else int(value)
        except ValueError:
            v = 0
        width = int(self._prog_width.currentText())
        rep = extra.base_report(str(v), 10)
        rows = [(k, val) for k, val in rep["rows"] if k in
                ("BIN 二进制", "OCT 八进制", "DEC 十进制", "HEX 十六进制")]
        fill_table(self._prog_table, rows)
        self._bits.set_value(v, width)

    def _render_history(self):
        self._hist_list.clear()
        for expr, result in self._history:
            item = QListWidgetItem(f"{expr}   =   {result}")
            item.setData(Qt.ItemDataRole.UserRole, expr)
            item.setToolTip(f"{expr} = {result}")
            self._hist_list.addItem(item)

    def _clear_history(self):
        self._history.clear()
        self._render_history()

    def _export_history(self):
        text = "\n".join(f"{e} = {r}" for e, r in self._history)
        export_text(self, text, "lumibox_calc_history.txt")
