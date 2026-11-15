"""开发者工具页：进制转换、随机数、编码转换、UUID 批量、反编译、剪贴板。"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QTabWidget, QLineEdit, QComboBox, QSpinBox, QCheckBox,
                              QFileDialog, QListWidget, QListWidgetItem, QSizePolicy)

from ..glass import PageScaffold, GlassCard, label, divider, notify
from .. import extra
from .. import system_extra as se
from .common import (on_click, changed, tab_container, plain_tab, editor, row, make_table,
                     fill_table, btn, pick_file, export_text, copy_text, clipboard_text,
                     start_worker, mono, field)


class DevPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("开发者工具", "进制 · 编码 · 随机 · UUID · 字节码反编译 · 剪贴板", parent)
        self._workers = []
        self._archive_info = None
        self._clip_history: list[str] = []

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._number_tab(), "  进制 & 随机  ")
        tabs.addTab(self._encoding_tab(), "  编码 & UUID  ")
        tabs.addTab(self._bytecode_tab(), "  反编译 & 剪贴板  ")
        self.add_widget(tabs, 1)

        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().dataChanged.connect(self._on_clip_changed)

    # ================================================================ Tab 1
    def _number_tab(self):
        w, lay = tab_container()
        lay.addWidget(self._base_card())
        lay.addWidget(self._random_card())
        lay.addStretch(1)
        return w

    def _base_card(self):
        card = GlassCard("进制转换器", "输入即时联动换算，支持 2~36 进制、位运算与字符码点", spacing=12)

        self._base_input = field("255", "输入数值，支持 0x / 0b / 0o 前缀与空格分组")
        self._base_spin = QSpinBox()
        self._base_spin.setRange(2, 36)
        self._base_spin.setValue(10)
        self._base_spin.setPrefix("输入进制 ")
        self._base_spin.setFixedWidth(130)
        card.add_layout(row(self._base_input, self._base_spin, stretch=False))
        changed(self._base_input, "textChanged", self._update_base)
        changed(self._base_spin, "valueChanged", self._update_base)

        self._base_table = make_table(["进制", "结果"])
        card.add(self._base_table)
        self._base_meta = mono("")
        card.add(self._base_meta)

        card.add(divider())
        card.add(label("位运算", 10, True))
        ops = QComboBox()
        ops.addItems(list(extra._BITWISE.keys()))
        ops.setMinimumWidth(130)
        self._bit_op = ops
        widths = QComboBox()
        widths.addItems(["8", "16", "32", "64"])
        widths.setCurrentText("64")
        widths.setMinimumWidth(80)
        self._bit_width = widths
        self._bit_a = field("0b1100", "A")
        self._bit_b = field("0b1010", "B")
        calc_btn = btn("计算", True)
        card.add_layout(row(label("A", 9), self._bit_a, label("B", 9), self._bit_b,
                            ops, widths, calc_btn, stretch=False))
        on_click(calc_btn, self._update_bitwise)
        self._bit_result = mono("—")
        card.add(self._bit_result)

        card.add(divider())
        card.add(label("字符 ↔ 码点", 10, True))
        self._char_input = field("A中😀", "输入字符，查看 Unicode 码点与 UTF-8 字节")
        card.add(self._char_input)
        changed(self._char_input, "textChanged", self._update_chars)
        self._char_table = make_table(["字符", "码点", "十进制", "UTF-8 字节"])
        card.add(self._char_table)

        self._update_base()
        self._update_bitwise()
        self._update_chars()
        return card

    def _update_base(self):
        try:
            rep = extra.base_report(self._base_input.text(), self._base_spin.value())
        except ValueError as exc:
            fill_table(self._base_table, [["输入错误", str(exc)]])
            self._base_meta.setText("")
            return
        fill_table(self._base_table, rep["rows"])
        fl = f" (IEEE754 单精度 {rep['float_bits']:.6g})" if rep["float_bits"] is not None else ""
        self._base_meta.setText(
            f"位宽 {rep['bit_length']} bit  ·  对齐宽度 {rep['width']} bit  ·  "
            f"无符号 {rep['unsigned']}  ·  有符号 {rep['signed']}{fl}\n"
            f"大端字节 {rep['bytes_hex']}  ·  ASCII 可视 {rep['ascii']}")

    def _update_bitwise(self):
        try:
            a = extra.parse_number(self._bit_a.text(), 10)
            b = extra.parse_number(self._bit_b.text(), 10)
            res = extra.bitwise(a, b, self._bit_op.currentText(), int(self._bit_width.currentText()))
            self._bit_result.setText(
                f"DEC {res['dec']}   ·   HEX {res['hex']}   ·   BIN {res['bin']}   "
                f"({res['width']} 位截断显示，完整结果 {res['result']})")
        except (ValueError, KeyError) as exc:
            self._bit_result.setText(f"错误：{exc}")

    def _update_chars(self):
        rows = extra.char_codes(self._char_input.text())
        fill_table(self._char_table, rows)

    # ---------------------------------------------------------------- 随机数
    def _random_card(self):
        card = GlassCard("随机数生成器", "整数 / 浮点 / 正态分布 / 抽签，可选密码学安全随机", spacing=12)
        self._rand_mode = QComboBox()
        self._rand_mode.addItems(["整数", "浮点（均匀）", "浮点（正态）", "列表抽签"])
        self._rand_mode.setMinimumWidth(140)
        self._rand_low = field("1", "最小")
        self._rand_high = field("100", "最大")
        self._rand_count = QSpinBox()
        self._rand_count.setRange(1, 10000)
        self._rand_count.setValue(10)
        self._rand_count.setPrefix("数量 ")
        self._rand_decimals = QSpinBox()
        self._rand_decimals.setRange(0, 10)
        self._rand_decimals.setValue(4)
        self._rand_decimals.setPrefix("小数位 ")
        self._rand_unique = QCheckBox("不重复")
        self._rand_sort = QCheckBox("排序")
        self._rand_secure = QCheckBox("密码学安全 (secrets)")
        card.add_layout(row(self._rand_mode, self._rand_low, self._rand_high,
                            self._rand_count, self._rand_decimals, stretch=False))
        card.add_layout(row(self._rand_unique, self._rand_sort, self._rand_secure))
        self._rand_list = editor("列表抽签模式：每行输入一个选项…", 66)
        self._rand_list.setPlainText("火锅\n烧烤\n日料\n沙拉\n回家吃")
        card.add(self._rand_list)
        gen_btn = btn("生成随机数", True)
        copy_btn = btn("复制结果")
        export_btn = btn("导出 TXT")
        on_click(gen_btn, self._gen_random)
        on_click(copy_btn, lambda: copy_text(self, self._rand_out.toPlainText()))
        on_click(export_btn, lambda: export_text(self, self._rand_out.toPlainText(),
                                                "lumibox_random.txt"))
        card.add_layout(row(gen_btn, copy_btn, export_btn))
        self._rand_out = editor("", 110, readonly=True)
        card.add(self._rand_out)
        self._rand_stats = mono("—")
        card.add(self._rand_stats)
        changed(self._rand_mode, "currentIndexChanged", self._sync_rand_mode)
        self._gen_random()
        self._sync_rand_mode()
        return card

    def _sync_rand_mode(self):
        is_int = self._rand_mode.currentText() == "整数"
        is_list = self._rand_mode.currentText() == "列表抽签"
        self._rand_unique.setEnabled(is_int)
        self._rand_sort.setEnabled(is_int)
        self._rand_decimals.setEnabled(not is_int and not is_list)
        self._rand_list.setVisible(is_list)

    def _gen_random(self):
        try:
            low, high = float(self._rand_low.text()), float(self._rand_high.text())
            count = self._rand_count.value()
            mode = self._rand_mode.currentText()
            if mode == "整数":
                values = extra.random_integers(int(low), int(high), count,
                                               self._rand_unique.isChecked(),
                                               self._rand_secure.isChecked(),
                                               self._rand_sort.isChecked())
                text = "\n".join(str(v) for v in values)
            elif mode == "列表抽签":
                opts = self._rand_list.toPlainText().splitlines()
                values = extra.pick_from_list(opts, count, unique=self._rand_unique.isChecked())
                text = "\n".join(values)
            else:
                values = extra.random_floats(low, high, count, self._rand_decimals.value(),
                                            normal="正态" in mode, secure=self._rand_secure.isChecked())
                text = "\n".join(str(v) for v in values)
            self._rand_out.setPlainText(text)
            self._rand_stats.setText(extra.random_summary(values))
        except (ValueError, TypeError) as exc:
            self._rand_out.setPlainText("")
            self._rand_stats.setText(f"错误：{exc}")

    # ================================================================ Tab 2
    def _encoding_tab(self):
        w, lay = tab_container()
        lay.addWidget(self._encoding_card())
        lay.addWidget(self._uuid_card())
        lay.addStretch(1)
        return w

    def _encoding_card(self):
        card = GlassCard("编码转换工具", "UTF-8 / GBK / GB18030 / Big5 / Shift-JIS … 互转与乱码修复", spacing=12)
        self._enc_combo = QComboBox()
        self._enc_combo.addItems(extra.ENCODINGS)
        self._enc_combo.setCurrentText("UTF-8")
        self._enc_combo.setMinimumWidth(140)
        self._enc_input = editor("输入要转换的文本…", 76)
        self._enc_input.setPlainText("LumiBox 中文测试 · Windows 工具箱")
        card.add_layout(row(label("目标编码", 10, True), self._enc_combo))
        card.add(self._enc_input)
        changed(self._enc_combo, "currentIndexChanged", self._update_encoding)
        changed(self._enc_input, "textChanged", self._update_encoding)
        self._enc_out = editor("", 120, readonly=True)
        card.add(self._enc_out)
        fix = btn("乱码修复")
        on_click(fix, self._fix_mojibake)
        card.add_layout(row(
            btn("复制 HEX", False), fix, btn("打开文件（按此编码解码）", False),
            btn("另存为编码文件", False)))
        acts = card.body().itemAt(card.body().count() - 1).layout()
        on_click(acts.itemAt(0).widget(), lambda: copy_text(self, self._enc_hex))
        on_click(acts.itemAt(2).widget(), self._open_encoded_file)
        on_click(acts.itemAt(3).widget(), self._save_encoded_file)
        self._fix_out = editor("", 90, readonly=True)
        card.add(self._fix_out)
        card.add(label("提示：把「UTF-8 字节被 GBK/Latin-1 误读」形成的乱码粘到上方输入框，"
                      "点「乱码修复」可尝试还原。", 9, False, True))
        self._enc_hex = ""
        self._update_encoding()
        return card

    def _update_encoding(self):
        try:
            rep = extra.encoding_report(self._enc_input.toPlainText(), self._enc_combo.currentText())
            self._enc_hex = rep["hex"]
            self._enc_out.setPlainText(
                f"编码      {self._enc_combo.currentText()}\n"
                f"字节数    {rep['count']}\n"
                f"BOM / 头  {rep['bom']}\n"
                f"Base64    {rep['base64']}\n"
                f"SHA-256   {rep['sha256']}\n"
                + "-" * 60 + f"\n{rep['hex']}")
        except (LookupError, UnicodeError, ValueError) as exc:
            self._enc_out.setPlainText(f"错误：{exc}")
            self._enc_hex = ""

    def _fix_mojibake(self):
        found = extra.fix_mojibake(self._enc_input.toPlainText())
        if not found:
            self._fix_out.setPlainText("未找到可信的乱码还原方案。常见组合："
                                       "UTF-8↔GBK、UTF-8↔Latin-1、UTF-8↔CP1252。")
            return
        lines = []
        for i, (text, wrong, right) in enumerate(found, 1):
            lines.append(f"[{i}] 视为「{wrong} 字节被 {right} 误读」→  {wrong} → {right}\n{text}\n")
        self._fix_out.setPlainText("\n".join(lines))

    def _open_encoded_file(self):
        path = pick_file(self, "选择文本文件", "所有文件 (*)")
        if not path:
            return
        try:
            text, raw = extra.read_encoded_file(path, self._enc_combo.currentText())
            self._enc_input.setPlainText(text)
            notify(self, f"已按 {self._enc_combo.currentText()} 读取 {len(raw)} 字节")
        except Exception as exc:  # noqa: BLE001
            self._enc_out.setPlainText(f"读取失败：{exc}")

    def _save_encoded_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "另存为编码文件", "output.txt", "所有文件 (*)")
        if not path:
            return
        try:
            n = extra.write_encoded_file(path, self._enc_input.toPlainText(),
                                         self._enc_combo.currentText())
            notify(self, f"已写入 {n} 字节（{self._enc_combo.currentText()}）")
        except Exception as exc:  # noqa: BLE001
            self._enc_out.setPlainText(f"写入失败：{exc}")

    # ---------------------------------------------------------------- UUID
    def _uuid_card(self):
        card = GlassCard("UUID 批量生成器", "v1 / v3 / v4 / v5 / v6 / v7，一次最多 10 万条", spacing=12)
        self._uuid_ver = QComboBox()
        self._uuid_ver.addItems(["UUID v4 · 随机", "UUID v1 · 时间+MAC", "UUID v3 · 名称 MD5",
                                 "UUID v5 · 名称 SHA1", "UUID v6 · 时间有序", "UUID v7 · 时间有序"])
        self._uuid_ver.setMinimumWidth(180)
        self._uuid_count = QSpinBox()
        self._uuid_count.setRange(1, 100000)
        self._uuid_count.setValue(20)
        self._uuid_count.setPrefix("数量 ")
        self._uuid_style = QComboBox()
        self._uuid_style.addItems(["标准", "大写", "无连字符", "带花括号", "URN"])
        self._uuid_name = field("lumibox", "v3 / v5 名称")
        card.add_layout(row(self._uuid_ver, self._uuid_count, self._uuid_style, self._uuid_name,
                            stretch=False))
        gen = btn("批量生成", True)
        card.add_layout(row(gen, btn("复制"), btn("导出 TXT"), btn("校验文本框")))
        acts = card.body().itemAt(card.body().count() - 1).layout()
        on_click(gen, self._gen_uuids)
        on_click(acts.itemAt(1).widget(), lambda: copy_text(self, self._uuid_out.toPlainText()))
        on_click(acts.itemAt(2).widget(),
                 lambda: export_text(self, self._uuid_out.toPlainText(), "lumibox_uuids.txt"))
        on_click(acts.itemAt(3).widget(), self._validate_uuids)
        self._uuid_out = editor("", 170, readonly=True)
        card.add(self._uuid_out)
        self._uuid_info = mono("—")
        card.add(self._uuid_info)
        changed(self._uuid_ver, "currentIndexChanged", self._sync_uuid_name)
        self._gen_uuids()
        self._sync_uuid_name()
        return card

    def _sync_uuid_name(self):
        self._uuid_name.setEnabled("v3" in self._uuid_ver.currentText()
                                   or "v5" in self._uuid_ver.currentText())

    def _gen_uuids(self):
        values = extra.generate_uuids(self._uuid_ver.currentText(), self._uuid_count.value(),
                                       self._uuid_style.currentText(), self._uuid_name.text())
        self._uuid_out.setPlainText("\n".join(values))
        self._uuid_info.setText(f"共 {len(values)} 条  ·  去重后 {len(set(values))} 条  ·  "
                                f"格式 {self._uuid_style.currentText()}")

    def _validate_uuids(self):
        ok, bad, errs = extra.validate_uuids(self._uuid_out.toPlainText().splitlines())
        self._uuid_info.setText(f"合法 {ok} 条  ·  非法 {bad} 条"
                                + ("" if not errs else "  ·  " + errs[0]))

    # ================================================================ Tab 3
    def _bytecode_tab(self):
        w, lay = tab_container()
        lay.addWidget(self._decompile_card())
        lay.addWidget(self._clip_card())
        lay.addStretch(1)
        return w

    def _decompile_card(self):
        card = GlassCard("反编译工具", ".pyc 字节码反汇编 + PyInstaller EXE 归档提取", spacing=12)
        self._dec_path = field("", "选择 .pyc 或 PyInstaller 打包的 .exe 文件")
        self._dec_path.setReadOnly(True)
        card.add_layout(row(btn("选择文件"), self._dec_path, btn("分析", True), stretch=False))
        head = card.body().itemAt(card.body().count() - 1).layout()
        on_click(head.itemAt(0).widget(), self._choose_dec_file)
        on_click(head.itemAt(2).widget(), self._analyze_dec)

        inner = QTabWidget()
        inner.setDocumentMode(True)
        textw, textlay = plain_tab()
        self._dec_out = editor("", 300, readonly=True)
        textlay.addWidget(self._dec_out)
        inner.addTab(textw, "  分析文本  ")
        filesw, filelay = plain_tab()
        self._dec_table = make_table(["名称", "类型", "压缩后", "原始大小", "压缩"])
        filelay.addWidget(self._dec_table)
        inner.addTab(filesw, "  归档文件表  ")
        self._dec_inner = inner
        card.add(inner)

        self._dec_tool = QComboBox()
        self._dec_tool.setMinimumWidth(190)
        card.add_layout(row(btn("导出归档文件"), btn("导出报告"), self._dec_tool,
                            btn("调用外部反编译器")))
        acts = card.body().itemAt(card.body().count() - 1).layout()
        on_click(acts.itemAt(0).widget(), self._extract_archive)
        on_click(acts.itemAt(1).widget(),
                 lambda: export_text(self, self._dec_out.toPlainText(), "lumibox_decompile.txt"))
        on_click(acts.itemAt(3).widget(), self._call_decompiler)
        card.add(label("· 内置 dis 反汇编（无需外部工具）；可选调用 uncompyle6 / decompyle3 / pycdc 还原源码。",
                       9, False, True))
        card.add(label("· 归档解析参考 GitHub 开源项目 pyinstxtractor 的 CArchive / PYZ 格式规范，代码为独立实现。",
                       9, False, True))
        card.add(label("· 仅用于分析你自己编写或已获授权的文件，请遵守软件许可与适用法律。",
                       9, False, True))
        self._refresh_decompilers()
        return card

    def _refresh_decompilers(self):
        self._dec_tool.clear()
        tools = [t["name"] for t in se.detect_decompilers()]
        self._dec_tool.addItems(tools or ["（未安装外部反编译器）"])

    def _choose_dec_file(self):
        path = pick_file(self, "选择 .pyc / .exe 文件",
                         "Python / 可执行文件 (*.pyc *.exe *.bin);;所有文件 (*)")
        if path:
            self._dec_path.setText(path)

    def _analyze_dec(self):
        path = self._dec_path.text().strip()
        if not path or not os.path.isfile(path):
            notify(self, "请先选择文件")
            return
        self._dec_out.setPlainText("分析中…")
        if path.lower().endswith(".pyc"):
            try:
                info = se.read_pyc(path)
                parts = [se.pyc_summary(info)]
                if info["code"] is not None:
                    parts += ["", "=" * 72, "CODE 对象结构", "=" * 72]
                    parts += se.code_tree_lines(se.code_tree(info["code"]))
                    parts += ["", "=" * 72, "字节码反汇编 (dis)", "=" * 72]
                    parts.append(se.disassemble(info["code"]))
                self._dec_out.setPlainText("\n".join(parts))
                fill_table(self._dec_table, [])
                self._archive_info = None
                self._dec_inner.setCurrentIndex(0)
                notify(self, "pyc 分析完成")
            except Exception as exc:  # noqa: BLE001
                self._dec_out.setPlainText(f"分析失败：{exc}")
        else:
            start_worker(self, se.parse_pyinstaller_archive, (path,),
                          self._on_archive_parsed)

    def _on_archive_parsed(self, info):
        self._archive_info = info
        rows = [[e["name"], e["type_name"], str(e["csize"]), str(e["usize"]),
                 "是" if e["compressed"] else "否"] for e in info["entries"]]
        fill_table(self._dec_table, rows)
        lines = [
            "PYINSTALLER CARCHIVE",
            "=" * 72,
            f"文件          {os.path.basename(info['path'])}",
            f"归档大小      {info['pkg_len']} 字节",
            f"Python 版本   {info['python_version']}",
            f"运行时库      {info['pylib'] or '内嵌'}",
            f"顶层条目      {len(info['entries'])}",
            "",
            "提示：切到「归档文件表」查看全部文件；点「导出归档文件」可把内容解包到本地，",
            "其中 PYZ 内的 Python 模块会导出为 .pyc，可再用本页反汇编。",
            "",
            "本工具仅用于分析自有或已获授权的程序，请遵守软件许可与适用法律。",
        ]
        self._dec_out.setPlainText("\n".join(lines))
        self._dec_inner.setCurrentIndex(0)
        notify(self, f"归档解析完成，共 {len(rows)} 个条目")

    def _extract_archive(self):
        path = self._dec_path.text().strip()
        if not path:
            notify(self, "请先分析一个归档文件")
            return
        outdir = QFileDialog.getExistingDirectory(self, "选择导出目录", "")
        if not outdir:
            return
        self._dec_out.setPlainText("正在导出…")
        start_worker(self, se.extract_archive, (path, outdir), self._on_extracted)

    def _on_extracted(self, res):
        notes = res["notes"]
        self._dec_out.setPlainText("\n".join(notes) + f"\n\n共导出 {len(res['files'])} 个文件：\n"
                                  + "\n".join(f["path"] for f in res["files"][:200]))
        notify(self, f"已导出 {len(res['files'])} 个文件")

    def _call_decompiler(self):
        path = self._dec_path.text().strip()
        tool = self._dec_tool.currentText().split(" ")[0]
        if not path or tool.startswith("（"):
            notify(self, "请先选择 .pyc 文件并安装 uncompyle6 / decompyle3 / pycdc")
            return
        self._dec_out.setPlainText(f"正在调用 {tool}…")
        start_worker(self, se.decompile_source, (path, tool), self._on_source)

    def _on_source(self, text):
        self._dec_out.setPlainText("还原的源码：\n" + "=" * 72 + "\n" + text)

    # ---------------------------------------------------------------- 剪贴板
    def _clip_card(self):
        card = GlassCard("剪贴板工具", "自动记录复制历史、快速回写、统计与导出", spacing=12)
        self._clip_auto = QCheckBox("自动捕获系统剪贴板变化")
        self._clip_auto.setChecked(True)
        card.add(self._clip_auto)
        self._clip_input = editor("在此输入内容，点「写入剪贴板」…", 70)
        card.add(self._clip_input)
        card.add_layout(row(btn("写入剪贴板", True), btn("读取当前剪贴板"),
                            btn("清空历史"), btn("导出历史")))
        acts = card.body().itemAt(card.body().count() - 1).layout()
        on_click(acts.itemAt(0).widget(), self._clip_write)
        on_click(acts.itemAt(1).widget(), self._clip_read)
        on_click(acts.itemAt(2).widget(), self._clip_clear)
        on_click(acts.itemAt(3).widget(), self._clip_export)
        self._clip_stats = mono("—")
        card.add(self._clip_stats)
        card.add(label("历史记录（双击任意条目即可重新复制，最多保留 100 条）", 9, False, True))
        self._clip_list = QListWidget()
        self._clip_list.setMinimumHeight(190)
        self._clip_list.itemDoubleClicked.connect(
            lambda _item: copy_text(self, _item.data(Qt.ItemDataRole.UserRole)))
        card.add(self._clip_list)
        self._render_clip_history()
        return card

    def _on_clip_changed(self):
        if not self._clip_auto.isChecked():
            return
        text = clipboard_text()
        if not text or (self._clip_history and self._clip_history[0] == text):
            return
        self._clip_history = [text] + [h for h in self._clip_history if h != text][:99]
        self._render_clip_history()

    def _render_clip_history(self):
        self._clip_list.clear()
        for text in self._clip_history:
            item = QListWidgetItem(f"{extra.clip_preview(text)}   ·   {len(text)} 字符")
            item.setData(Qt.ItemDataRole.UserRole, text)
            item.setToolTip(text[:500])
            self._clip_list.addItem(item)
        cur = clipboard_text()
        self._clip_stats.setText(extra.clip_stats(cur) + f"   ·   历史 {len(self._clip_history)} 条")

    def _clip_write(self):
        text = self._clip_input.toPlainText()
        if not text:
            notify(self, "请输入内容")
            return
        from ..utils import set_clipboard
        set_clipboard(text)
        notify(self, "已写入剪贴板")

    def _clip_read(self):
        text = clipboard_text()
        self._clip_input.setPlainText(text)
        self._on_clip_changed()
        self._render_clip_history()

    def _clip_clear(self):
        self._clip_history.clear()
        self._render_clip_history()

    def _clip_export(self):
        text = "\n\n".join(f"[{i}] {datetime.now():%Y-%m-%d %H:%M:%S}\n{h}"
                           for i, h in enumerate(self._clip_history, 1))
        export_text(self, text, "lumibox_clipboard.txt")
