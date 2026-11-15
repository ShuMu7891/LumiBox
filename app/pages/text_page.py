"""文本与开发页（重点：SHA 哈希计算、Base64 编解码，另含 URL/JSON/正则工具）。"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import urllib.parse
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
                              QLineEdit, QTextEdit, QComboBox, QCheckBox, QFileDialog,
                              QSizePolicy, QScrollArea, QFrame)

from ..glass import (PageScaffold, GlassCard, GlassButton, label, copy_button, notify)
from ..utils import (Worker, HASH_ALGOS, hash_text, _HASH_MAP, human_bytes, set_clipboard)


def _hash_file_all(path: str):
    hs = [(a, hashlib.new(_HASH_MAP[a])) for a in HASH_ALGOS]
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            for _, h in hs:
                h.update(block)
    return {a: h.hexdigest() for a, h in hs}, size


def _clean_b64(s: str) -> str:
    return re.sub(r"\s+", "", s)


class TextPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("文本与开发", "SHA 哈希 · Base64 编解码 · JSON · 正则 · URL 转义", parent)
        self._workers = []
        self._hash_results = {}
        self._decoded_bytes = None

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._hash_tab(), "  SHA 哈希  ")
        tabs.addTab(self._base64_tab(), "  Base64 编解码  ")
        tabs.addTab(self._url_tab(), "  URL / 字符编码  ")
        tabs.addTab(self._json_tab(), "  JSON 工具  ")
        tabs.addTab(self._regex_tab(), "  正则 & 统计  ")
        self.add_widget(tabs, 1)

    # ---------------------------------------------------------------- 布局辅助
    @staticmethod
    def _tab() -> tuple[QWidget, QVBoxLayout]:
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

    @staticmethod
    def _editor(placeholder: str = "", height: int = 110, readonly: bool = False) -> QTextEdit:
        e = QTextEdit()
        e.setPlaceholderText(placeholder)
        e.setMinimumHeight(height)
        e.setReadOnly(readonly)
        e.setAcceptRichText(False)
        return e

    def _button_row(self, *buttons) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        for b in buttons:
            row.addWidget(b)
        return row

    # ================================================================ SHA 哈希
    def _hash_tab(self):
        w, lay = self._tab()

        card = GlassCard("文本哈希", "一次计算 10 种常见摘要算法，结果可直接复制", spacing=12)
        self._hash_input = self._editor("在此输入要计算哈希的文本…", 100)
        self._hash_input.setPlainText("Hello, LumiBox!")
        card.add(self._hash_input)

        calc = GlassButton("计算哈希", primary=True)
        calc.clicked.connect(self._calc_text_hash)
        clear = GlassButton("清空")
        clear.clicked.connect(self._hash_input.clear)
        sample = GlassButton("填入示例")
        sample.clicked.connect(lambda: self._hash_input.setPlainText("Hello, LumiBox! 中文测试 123"))
        card.add_layout(self._button_row(sample, clear, calc))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self._hash_fields = {}
        for i, algo in enumerate(HASH_ALGOS):
            name = label(algo, 9, True)
            name.setFixedWidth(80)
            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText("—")
            field.setMinimumHeight(30)
            cp = copy_button(self, lambda a=algo: self._hash_results.get(a, ""), "复制")
            cp.setFixedWidth(64)
            grid.addWidget(name, i, 0)
            grid.addWidget(field, i, 1)
            grid.addWidget(cp, i, 2)
            self._hash_fields[algo] = field
        card.add_layout(grid)
        self._hash_note = label("", 9, False, True)
        card.add(self._hash_note)
        lay.addWidget(card)

        file_card = GlassCard("文件哈希", "分块读取，支持超大文件；所有算法一次扫描完成", spacing=12)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._hash_path = QLineEdit()
        self._hash_path.setReadOnly(True)
        self._hash_path.setPlaceholderText("选择一个文件…")
        row.addWidget(self._hash_path, 1)
        pick = GlassButton("选择文件")
        pick.clicked.connect(self._pick_hash_file)
        run = GlassButton("计算", primary=True)
        run.clicked.connect(self._calc_file_hash)
        row.addWidget(pick)
        row.addWidget(run)
        file_card.add_layout(row)
        self._file_hash_out = self._editor("文件哈希结果会显示在这里…", 190, True)
        file_card.add(self._file_hash_out)
        copy_all = copy_button(self, lambda: self._file_hash_out.toPlainText(), "复制全部结果")
        file_card.add_layout(self._button_row(copy_all))
        lay.addWidget(file_card)

        lay.addStretch(1)
        self._calc_text_hash()
        return w

    def _calc_text_hash(self):
        text = self._hash_input.toPlainText()
        self._hash_results = {}
        for algo in HASH_ALGOS:
            try:
                value = hash_text(text, algo)
                self._hash_results[algo] = value
                self._hash_fields[algo].setText(value)
            except Exception as exc:  # noqa: BLE001
                self._hash_fields[algo].setText(f"不支持：{exc}")
        size = len(text.encode("utf-8"))
        self._hash_note.setText(f"输入 {len(text)} 个字符 / {human_bytes(size)}（UTF-8） · 共 {len(HASH_ALGOS)} 种算法")

    def _pick_hash_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择要计算哈希的文件", "", "所有文件 (*.*)")
        if path:
            self._hash_path.setText(path)

    def _calc_file_hash(self):
        path = self._hash_path.text()
        if not path or not os.path.isfile(path):
            notify(self, "请先选择一个有效的文件")
            return
        self._file_hash_out.setPlainText("正在计算，请稍候…")
        worker = Worker(_hash_file_all, path)
        self._workers.append(worker)
        worker.done.connect(self._on_file_hash)
        worker.failed.connect(lambda e: self._file_hash_out.setPlainText(f"计算失败：{e}"))
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        worker.start()

    def _on_file_hash(self, result):
        values, size = result
        lines = [f"文件：{self._hash_path.text()}", f"大小：{human_bytes(size)}", ""]
        lines += [f"{a:<10}  {v}" for a, v in values.items()]
        self._file_hash_out.setPlainText("\n".join(lines))
        notify(self, "文件哈希计算完成")

    # ================================================================ Base64
    def _base64_tab(self):
        w, lay = self._tab()
        card = GlassCard("Base64 编解码", "支持标准 / URL-safe Base64、Base32 与 Base16(Hex)", spacing=12)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(label("编码方式", 10, True))
        self._b64_mode = QComboBox()
        self._b64_mode.addItems(["Base64（标准）", "Base64 URL-safe", "Base32", "Base16 (Hex)"])
        self._b64_mode.setMinimumWidth(190)
        top.addWidget(self._b64_mode)
        top.addStretch(1)
        file_btn = GlassButton("文件 → Base64")
        file_btn.setToolTip("把任意文件的二进制内容编码为文本")
        file_btn.clicked.connect(self._file_to_base64)
        save_btn = GlassButton("结果另存为文件")
        save_btn.setToolTip("把解码得到的原始字节写入文件")
        save_btn.clicked.connect(self._save_decoded)
        top.addWidget(file_btn)
        top.addWidget(save_btn)
        card.add_layout(top)

        split = QHBoxLayout()
        split.setSpacing(12)
        left = QVBoxLayout()
        left.addWidget(label("输入", 10, True))
        self._b64_in = self._editor("输入明文，或粘贴要解码的编码串…", 210)
        left.addWidget(self._b64_in)
        right = QVBoxLayout()
        right.addWidget(label("输出", 10, True))
        self._b64_out = self._editor("结果…", 210, True)
        right.addWidget(self._b64_out)
        split.addLayout(left, 1)
        split.addLayout(right, 1)
        card.add_layout(split)

        enc = GlassButton("编码 →", primary=True)
        enc.clicked.connect(lambda: self._b64_convert(True))
        dec = GlassButton("← 解码", primary=True)
        dec.clicked.connect(lambda: self._b64_convert(False))
        swap = GlassButton("交换输入输出")
        swap.clicked.connect(self._b64_swap)
        clear = GlassButton("清空")
        clear.clicked.connect(self._b64_clear)
        card.add_layout(self._button_row(clear, swap, dec, enc,
                                         copy_button(self, lambda: self._b64_out.toPlainText(), "复制结果")))

        self._b64_status = label("就绪", 9, False, True)
        card.add(self._b64_status)
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    def _b64_convert(self, encode: bool):
        mode = self._b64_mode.currentIndex()
        raw = self._b64_in.toPlainText()
        try:
            if encode:
                data = raw.encode("utf-8")
                if mode == 0:
                    out = base64.b64encode(data).decode("ascii")
                elif mode == 1:
                    out = base64.urlsafe_b64encode(data).decode("ascii")
                elif mode == 2:
                    out = base64.b32encode(data).decode("ascii")
                else:
                    out = base64.b16encode(data).decode("ascii")
                self._decoded_bytes = None
                self._b64_out.setPlainText(out)
                self._b64_status.setText(f"已编码：输入 {human_bytes(len(data))} → 输出 {human_bytes(len(out))}")
            else:
                text = _clean_b64(raw)
                if mode == 0:
                    data = base64.b64decode(text, validate=True)
                elif mode == 1:
                    text += "=" * (-len(text) % 4)
                    data = base64.urlsafe_b64decode(text)
                elif mode == 2:
                    text += "=" * (-len(text) % 8)
                    data = base64.b32decode(text)
                else:
                    data = base64.b16decode(text.upper())
                self._decoded_bytes = data
                try:
                    out = data.decode("utf-8")
                    self._b64_out.setPlainText(out)
                    self._b64_status.setText(f"已解码：{human_bytes(len(data))} · UTF-8 文本")
                except UnicodeDecodeError:
                    preview = data[:256].hex(" ")
                    self._b64_out.setPlainText(
                        "解码结果是二进制数据，无法按 UTF-8 显示。\n"
                        "可点击「结果另存为文件」保存原始字节。\n\n"
                        f"前 {min(256, len(data))} 字节（HEX）：\n{preview}")
                    self._b64_status.setText(f"已解码：{human_bytes(len(data))} · 二进制数据")
        except Exception as exc:  # noqa: BLE001
            self._b64_out.setPlainText("")
            self._b64_status.setText("")
            notify(self, f"转换失败：{exc}")

    def _b64_swap(self):
        a = self._b64_in.toPlainText()
        self._b64_in.setPlainText(self._b64_out.toPlainText())
        self._b64_out.setPlainText(a)

    def _b64_clear(self):
        self._b64_in.clear()
        self._b64_out.clear()
        self._decoded_bytes = None
        self._b64_status.setText("就绪")

    def _file_to_base64(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "所有文件 (*.*)")
        if not path:
            return
        try:
            size = os.path.getsize(path)
            if size > 8 * 1024 * 1024:
                notify(self, "文件超过 8 MB，为避免卡顿已取消（文本工具建议用于小文件）")
                return
            with open(path, "rb") as f:
                data = f.read()
            out = base64.b64encode(data).decode("ascii")
            self._b64_in.setPlainText(path)
            self._b64_out.setPlainText(out)
            self._decoded_bytes = None
            self._b64_mode.setCurrentIndex(0)
            self._b64_status.setText(f"文件 {os.path.basename(path)}（{human_bytes(size)}）已转为标准 Base64，长度 {len(out)}")
        except Exception as exc:  # noqa: BLE001
            notify(self, f"读取文件失败：{exc}")

    def _save_decoded(self):
        if self._decoded_bytes is None:
            notify(self, "请先执行一次解码")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存解码结果", "decoded.bin", "所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(self._decoded_bytes)
            notify(self, f"已保存 {human_bytes(len(self._decoded_bytes))}")
        except Exception as exc:  # noqa: BLE001
            notify(self, f"保存失败：{exc}")

    # ================================================================ URL / 字符编码
    def _url_tab(self):
        w, lay = self._tab()
        card = GlassCard("URL / 字符编码", "网址转义、HTML 实体与 Unicode 转义互转", spacing=12)
        self._url_in = self._editor("输入文本…", 130)
        self._url_out = self._editor("结果…", 130, True)
        card.add(self._url_in)
        card.add(self._url_out)

        def btn(text, fn):
            b = GlassButton(text)
            b.clicked.connect(fn)
            return b

        def transform(kind):
            s = self._url_in.toPlainText()
            try:
                if kind == "url_enc":
                    out = urllib.parse.quote(s, safe="")
                elif kind == "url_dec":
                    out = urllib.parse.unquote(s)
                elif kind == "html_enc":
                    out = html.escape(s, quote=True)
                elif kind == "html_dec":
                    out = html.unescape(s)
                elif kind == "uni_enc":
                    out = "".join(ch if ord(ch) < 128 else f"\\u{ord(ch):04x}" for ch in s)
                else:
                    out = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
                self._url_out.setPlainText(out)
            except Exception as exc:  # noqa: BLE001
                notify(self, f"转换失败：{exc}")

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addStretch(1)
        for text, kind in [("URL 编码", "url_enc"), ("URL 解码", "url_dec"),
                           ("HTML 转义", "html_enc"), ("HTML 还原", "html_dec"),
                           ("Unicode 转义", "uni_enc"), ("Unicode 还原", "uni_dec")]:
            row1.addWidget(btn(text, lambda checked=False, k=kind: transform(k)))
        card.add_layout(row1)
        card.add_layout(self._button_row(copy_button(self, lambda: self._url_out.toPlainText(), "复制结果")))
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    # ================================================================ JSON
    def _json_tab(self):
        w, lay = self._tab()
        card = GlassCard("JSON 格式化 / 校验", "格式化、压缩、转义与语法校验", spacing=12)
        top = QHBoxLayout()
        top.addWidget(label("缩进", 10, True))
        self._json_indent = QComboBox()
        self._json_indent.addItems(["2 空格", "4 空格", "制表符"])
        top.addWidget(self._json_indent)
        top.addStretch(1)
        card.add_layout(top)

        split = QHBoxLayout()
        split.setSpacing(12)
        self._json_in = self._editor("粘贴 JSON…", 240)
        self._json_out = self._editor("结果…", 240, True)
        split.addWidget(self._json_in, 1)
        split.addWidget(self._json_out, 1)
        card.add_layout(split)

        def fmt():
            indent = [2, 4, "\t"][self._json_indent.currentIndex()]
            try:
                obj = json.loads(self._json_in.toPlainText())
                self._json_out.setPlainText(json.dumps(obj, ensure_ascii=False, indent=indent))
                self._json_status.setText(f"✓ 合法 JSON · {len(obj) if isinstance(obj, (dict, list)) else 1} 个顶层元素")
            except Exception as exc:  # noqa: BLE001
                notify(self, f"JSON 解析失败：{exc}")
                self._json_status.setText(f"✗ {exc}")

        def compact():
            try:
                obj = json.loads(self._json_in.toPlainText())
                self._json_out.setPlainText(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
                self._json_status.setText("✓ 已压缩为单行")
            except Exception as exc:  # noqa: BLE001
                notify(self, f"JSON 解析失败：{exc}")

        def escape():
            s = self._json_in.toPlainText()
            self._json_out.setPlainText(json.dumps(s, ensure_ascii=False))

        def unescape():
            try:
                self._json_out.setPlainText(json.loads(self._json_in.toPlainText()))
            except Exception as exc:  # noqa: BLE001
                notify(self, f"还原失败：{exc}")

        fmt_btn = GlassButton("格式化", primary=True)
        fmt_btn.clicked.connect(fmt)
        cp_btn = GlassButton("压缩")
        cp_btn.clicked.connect(compact)
        es_btn = GlassButton("转义为字符串")
        es_btn.clicked.connect(escape)
        un_btn = GlassButton("字符串还原")
        un_btn.clicked.connect(unescape)
        card.add_layout(self._button_row(un_btn, es_btn, cp_btn, fmt_btn,
                                         copy_button(self, lambda: self._json_out.toPlainText(), "复制结果")))
        self._json_status = label("等待输入", 9, False, True)
        card.add(self._json_status)
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    # ================================================================ 正则 & 统计
    def _regex_tab(self):
        w, lay = self._tab()
        card = GlassCard("正则表达式测试", "实时匹配，支持常用标志位", spacing=12)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(label("表达式", 10, True))
        self._re_pattern = QLineEdit()
        self._re_pattern.setPlaceholderText(r"例如：\b\w+@\w+\.\w+\b")
        self._re_pattern.setText(r"\b\w+@\w+\.\w+\b")
        top.addWidget(self._re_pattern, 1)
        self._re_i = QCheckBox("忽略大小写")
        self._re_m = QCheckBox("多行")
        self._re_s = QCheckBox("点匹配换行")
        top.addWidget(self._re_i)
        top.addWidget(self._re_m)
        top.addWidget(self._re_s)
        card.add_layout(top)

        split = QHBoxLayout()
        split.setSpacing(12)
        left = QVBoxLayout()
        left.addWidget(label("测试文本", 10, True))
        self._re_text = self._editor("在这里粘贴待匹配的文本…", 190)
        self._re_text.setPlainText("联系我：hello@example.com 或 support@lumibox.cn\n无效：abc@ / @test")
        left.addWidget(self._re_text)
        right = QVBoxLayout()
        right.addWidget(label("匹配结果", 10, True))
        self._re_out = self._editor("结果…", 190, True)
        right.addWidget(self._re_out)
        split.addLayout(left, 1)
        split.addLayout(right, 1)
        card.add_layout(split)

        run = GlassButton("执行匹配", primary=True)
        run.clicked.connect(self._run_regex)
        card.add_layout(self._button_row(run,
                                         copy_button(self, lambda: self._re_out.toPlainText(), "复制结果")))
        lay.addWidget(card)

        stat = GlassCard("文本统计 & 处理", "字数统计与常用文本清洗", spacing=12)
        self._stat_in = self._editor("输入要统计 / 处理的文本…", 130)
        stat.add(self._stat_in)
        self._stat_labels = {}
        grid = QGridLayout()
        grid.setSpacing(8)
        stat_keys = [("chars", "字符数"), ("nospace", "不含空白"), ("words", "单词数"),
                     ("lines", "行数"), ("cjk", "中文字符"), ("bytes", "UTF-8 字节")]
        for i, (k, name) in enumerate(stat_keys):
            grid.addWidget(label(name, 9, False, True), i // 3, (i % 3) * 2)
            v = label("-", 10, True)
            grid.addWidget(v, i // 3, (i % 3) * 2 + 1)
            self._stat_labels[k] = v
        stat.add_layout(grid)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(label("处理", 10, True))
        self._stat_op = QComboBox()
        self._stat_op.addItems(["去除重复行", "删除空行", "行排序（升序）", "行排序（降序）",
                               "转为大写", "转为小写", "去除行首尾空格", "反转行顺序"])
        self._stat_op.setMinimumWidth(170)
        row.addWidget(self._stat_op)
        apply = GlassButton("应用到输出", primary=True)
        apply.clicked.connect(self._apply_stat_op)
        row.addWidget(apply)
        self._stat_out = QLineEdit()
        self._stat_out.setReadOnly(False)
        self._stat_out.setPlaceholderText("统计结果 / 处理结果…")
        row.addWidget(self._stat_out, 1)
        stat.add_layout(row)
        lay.addWidget(stat)
        lay.addStretch(1)

        self._re_text.textChanged.connect(self._run_regex)
        self._re_pattern.textChanged.connect(self._run_regex)
        self._stat_in.textChanged.connect(self._refresh_stats)
        self._run_regex()
        self._refresh_stats()
        return w

    def _run_regex(self):
        pattern = self._re_pattern.text()
        text = self._re_text.toPlainText()
        if not pattern:
            self._re_out.setPlainText("")
            return
        flags = 0
        if self._re_i.isChecked():
            flags |= re.IGNORECASE
        if self._re_m.isChecked():
            flags |= re.MULTILINE
        if self._re_s.isChecked():
            flags |= re.DOTALL
        try:
            matches = list(re.finditer(pattern, text, flags))
            lines = [f"共 {len(matches)} 处匹配", ""]
            for i, m in enumerate(matches[:100], 1):
                groups = "  组: " + " | ".join(str(g) for g in m.groups() if g is not None) if m.groups() else ""
                lines.append(f"{i:>3}. [{m.start():>4}, {m.end():>4})  {m.group(0)!r}{groups}")
            if len(matches) > 100:
                lines.append(f"… 还有 {len(matches) - 100} 处匹配未显示")
            self._re_out.setPlainText("\n".join(lines))
        except re.error as exc:
            self._re_out.setPlainText(f"正则表达式错误：{exc}")

    def _refresh_stats(self):
        s = self._stat_in.toPlainText()
        cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
        words = len(re.findall(r"\b[\w'-]+\b", s))
        values = {
            "chars": str(len(s)),
            "nospace": str(len(re.sub(r"\s", "", s))),
            "words": str(words),
            "lines": str(len(s.splitlines()) if s else 0),
            "cjk": str(cjk),
            "bytes": human_bytes(len(s.encode("utf-8"))),
        }
        for k, v in values.items():
            self._stat_labels[k].setText(v)
        if not self._stat_out.text():
            self._stat_out.setText("")

    def _apply_stat_op(self):
        s = self._stat_in.toPlainText()
        op = self._stat_op.currentIndex()
        lines = s.splitlines()
        if op == 0:
            lines = list(dict.fromkeys(lines))
        elif op == 1:
            lines = [x for x in lines if x.strip()]
        elif op == 2:
            lines = sorted(lines)
        elif op == 3:
            lines = sorted(lines, reverse=True)
        elif op == 4:
            lines = [x.upper() for x in lines]
        elif op == 5:
            lines = [x.lower() for x in lines]
        elif op == 6:
            lines = [x.strip() for x in lines]
        elif op == 7:
            lines = lines[::-1]
        out = "\n".join(lines)
        self._stat_out.setText(out.replace("\n", " ⏎ "))
        set_clipboard(out)
        notify(self, "处理完成，完整结果已复制到剪贴板")
