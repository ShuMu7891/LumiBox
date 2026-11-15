"""文档工坊页：结构化格式互转、Markdown 预览导出、OCR、密码保险箱。"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QTabWidget, QFileDialog, QListWidgetItem, QInputDialog, QLineEdit

from ..glass import PageScaffold, GlassCard, label
from .. import doc_extra as dx
from .common import (on_click, tab_container, row, btn, editor, mono, field,
                     combo, checkbox, spin, ask, warn, info_box, notify,
                     pick_file, save_path, export_text, copy_text, make_table,
                     fill_table, start_worker)


class _Bridge(QObject):
    progress = Signal(int, int)


class DocPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("文档工坊", "格式互转 · Markdown · OCR · 密码保险箱", parent)
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_ocr_progress)
        self._vault_entries: list[dict] = []
        self._vault_password = ""
        self._vault_unlocked = False
        self._md_html = ""

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._convert_tab(), "  格式互转  ")
        tabs.addTab(self._markdown_tab(), "  Markdown  ")
        tabs.addTab(self._ocr_tab(), "  OCR 识别  ")
        tabs.addTab(self._vault_tab(), "  密码保险箱  ")
        self.add_widget(tabs, 1)
        self._check_ocr()
        self._check_vault()

    # ================================================================ 格式互转
    def _convert_tab(self):
        w, lay = tab_container()
        card = GlassCard("结构化数据互转", "JSON / YAML / TOML / XML / CSV 互相转换，本地完成", spacing=10)
        self._conv_src = combo(dx.FORMATS, "JSON", 110)
        self._conv_dst = combo(dx.FORMATS, "YAML", 110)
        swap = btn("⇄ 交换")
        on_click(swap, self._swap_formats)
        card.add_layout(row(label("源格式", 10, True), self._conv_src,
                            label("→ 目标格式", 10, True), self._conv_dst, swap))
        self._conv_in = editor("在此粘贴源数据，例如：\n{\"name\": \"LumiBox\", \"items\": [1, 2, 3]}", 190)
        card.add(self._conv_in)
        go = btn("转换", True)
        cl = btn("清空")
        cc = btn("复制结果")
        ex = btn("导出结果")
        on_click(go, self._do_convert)
        on_click(cl, lambda: (self._conv_in.clear(), self._conv_out.clear()))
        on_click(cc, lambda: copy_text(self, self._conv_out.toPlainText()))
        on_click(ex, lambda: export_text(self, self._conv_out.toPlainText(), "lumibox_convert.txt"))
        card.add_layout(row(go, cl, cc, ex))
        self._conv_out = editor("转换结果", 210, readonly=True)
        card.add(self._conv_out)
        lay.addWidget(card)

        xl = GlassCard("CSV ↔ Excel", "读取 .csv / .xlsx 互转，多工作表可选", spacing=10)
        self._xl_path = field("", "选择 .csv 或 .xlsx 文件")
        cho = btn("选择文件")
        on_click(cho, self._choose_xl)
        xl.add_layout(row(self._xl_path, cho))
        self._xl_sheet = combo([], "", 170)
        c2e = btn("CSV → Excel")
        e2c = btn("Excel → CSV")
        on_click(c2e, self._csv_to_xlsx)
        on_click(e2c, self._xlsx_to_csv)
        xl.add_layout(row(label("工作表", 10, True), self._xl_sheet, c2e, e2c))
        self._xl_status = label("就绪", 9, False, True)
        xl.add(self._xl_status)
        lay.addWidget(xl)
        lay.addStretch(1)
        return w

    def _swap_formats(self):
        a, b = self._conv_src.currentText(), self._conv_dst.currentText()
        self._conv_src.setCurrentText(b)
        self._conv_dst.setCurrentText(a)

    def _do_convert(self):
        text = self._conv_in.toPlainText().strip()
        if not text:
            notify(self, "请先输入源数据")
            return
        try:
            out = dx.convert_data(text, self._conv_src.currentText(), self._conv_dst.currentText())
            self._conv_out.setPlainText(out)
            notify(self, "转换完成")
        except Exception as exc:  # noqa: BLE001
            self._conv_out.setPlainText(f"转换失败：{exc}")

    def _choose_xl(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择表格文件", "",
                                           "表格文件 (*.csv *.xlsx *.xls);;所有文件 (*)")
        if not p:
            return
        self._xl_path.setText(p)
        if p.lower().endswith((".xlsx", ".xls")):
            try:
                sheets = dx.excel_sheets(p)
                self._xl_sheet.clear()
                self._xl_sheet.addItems(sheets)
                self._xl_status.setText(f"检测到 {len(sheets)} 个工作表：{', '.join(sheets)}")
            except Exception as exc:  # noqa: BLE001
                self._xl_status.setText(f"读取工作表失败：{exc}")

    def _csv_to_xlsx(self):
        src = self._xl_path.text().strip()
        if not src.lower().endswith(".csv") or not os.path.isfile(src):
            notify(self, "请先选择一个 CSV 文件")
            return
        out = save_path(self, "保存为 Excel", os.path.splitext(src)[0] + ".xlsx", "Excel (*.xlsx)")
        if not out:
            return
        try:
            with open(src, "r", encoding="utf-8-sig", errors="replace") as f:
                dx.csv_to_excel(f.read(), out)
            self._xl_status.setText(f"已生成 {out}")
            notify(self, "CSV → Excel 完成")
        except Exception as exc:  # noqa: BLE001
            warn(self, "转换失败", str(exc))

    def _xlsx_to_csv(self):
        src = self._xl_path.text().strip()
        if not src.lower().endswith((".xlsx", ".xls")) or not os.path.isfile(src):
            notify(self, "请先选择一个 Excel 文件")
            return
        out = save_path(self, "保存为 CSV", os.path.splitext(src)[0] + ".csv", "CSV (*.csv)")
        if not out:
            return
        try:
            sheet = self._xl_sheet.currentText() or None
            text = dx.excel_to_csv(src, sheet)
            with open(out, "w", encoding="utf-8-sig", newline="") as f:
                f.write(text)
            self._xl_status.setText(f"已生成 {out}")
            notify(self, "Excel → CSV 完成")
        except Exception as exc:  # noqa: BLE001
            warn(self, "转换失败", str(exc))

    # ================================================================ Markdown
    def _markdown_tab(self):
        w, lay = tab_container()
        card = GlassCard("Markdown 编辑器", "支持表格、代码高亮、任务列表；可导出 HTML / PDF", spacing=10)
        self._md_in = editor("# 欢迎使用 LumiBox\n\n这是一份 **Markdown** 文档。\n\n"
                             "| 功能 | 状态 |\n|---|---|\n| 预览 | ✅ |\n\n"
                             "```python\nprint('Hello')\n```\n", 230)
        self._md_in.textChanged.connect(self._render_md)
        card.add(self._md_in)
        pv = btn("刷新预览", True)
        h = btn("导出 HTML")
        pdf = btn("导出 PDF")
        on_click(pv, self._render_md)
        on_click(h, self._export_md_html)
        on_click(pdf, self._export_md_pdf)
        card.add_layout(row(pv, h, pdf))
        self._md_stats = label("", 9, False, True)
        card.add(self._md_stats)
        lay.addWidget(card)

        prev = GlassCard("实时预览", "", spacing=8)
        from PySide6.QtWidgets import QTextBrowser
        self._md_view = QTextBrowser()
        self._md_view.setOpenExternalLinks(True)
        self._md_view.setMinimumHeight(300)
        self._md_view.setStyleSheet("background: transparent; border: none;")
        prev.add(self._md_view)
        lay.addWidget(prev)
        lay.addStretch(1)
        self._render_md()
        return w

    def _render_md(self):
        text = self._md_in.toPlainText()
        try:
            self._md_html = dx.md_to_html(text)
            self._md_view.setHtml(self._md_html)
            s = dx.md_stats(text)
            self._md_stats.setText(
                f"{s['chars']} 字符 · {s['words']} 词 · {s['lines']} 行 · "
                f"{s['h']} 标题 · {s['code']} 代码块 · {s['links']} 链接 · {s['images']} 图片")
        except Exception as exc:  # noqa: BLE001
            self._md_stats.setText(f"渲染失败：{exc}")

    def _export_md_html(self):
        out = save_path(self, "导出 HTML", "lumibox_doc.html", "HTML (*.html)")
        if out:
            with open(out, "w", encoding="utf-8") as f:
                f.write(self._md_html)
            notify(self, f"已导出 {os.path.basename(out)}")

    def _export_md_pdf(self):
        out = save_path(self, "导出 PDF", "lumibox_doc.pdf", "PDF (*.pdf)")
        if not out:
            return
        self._md_stats.setText("正在生成 PDF…")
        start_worker(self, self._pdf_job, (self._md_html, out), self._on_pdf_done)

    @staticmethod
    def _pdf_job(html, out):
        return dx.html_to_pdf(html, out)

    def _on_pdf_done(self, out):
        notify(self, f"PDF 已生成：{os.path.basename(str(out))}")
        self._render_md()

    # ================================================================ OCR
    def _ocr_tab(self):
        w, lay = tab_container()
        cap = GlassCard("OCR 文字识别", "图片 / 截图 / PDF 提取文字；识别引擎自动探测", spacing=10)
        self._ocr_lang = combo(["eng", "chi_sim", "chi_sim+eng", "chi_tra", "jpn", "kor"], "eng", 150)
        self._ocr_status = label("", 9, False, True)
        cap.add_layout(row(label("识别语言", 10, True), self._ocr_lang))
        cap.add(self._ocr_status)
        img = btn("识别图片")
        pdf = btn("识别 PDF")
        clip = btn("识别剪贴板图片")
        on_click(img, self._ocr_image)
        on_click(pdf, self._ocr_pdf)
        on_click(clip, self._ocr_clipboard)
        cap.add_layout(row(img, pdf, clip))
        self._ocr_out = editor("识别结果", 300)
        cap.add(self._ocr_out)
        cc = btn("复制结果")
        ex = btn("导出 TXT")
        on_click(cc, lambda: copy_text(self, self._ocr_out.toPlainText()))
        on_click(ex, lambda: export_text(self, self._ocr_out.toPlainText(), "lumibox_ocr.txt"))
        cap.add_layout(row(cc, ex))
        lay.addWidget(cap)
        lay.addStretch(1)
        return w

    def _check_ocr(self):
        cap = dx.ocr_capabilities()
        if cap["ok"]:
            langs = ", ".join(cap["langs"][:12])
            extra = "（含中文）" if cap.get("chi") else "（未安装中文包，可装 tesseract-ocr-chi-sim）"
            self._ocr_status.setText(f"引擎就绪 {extra}· 可用语言：{langs}")
        else:
            self._ocr_status.setText(f"OCR 引擎不可用：{cap.get('error')} · 请安装 tesseract-ocr 与 pytesseract")

    def _ocr_run_image(self, source, tag):
        lang = self._ocr_lang.currentText()
        self._ocr_status.setText(f"正在识别 {tag} …")
        start_worker(self, dx.ocr_image, (source, lang), self._on_ocr_image_done)

    def _on_ocr_image_done(self, r):
        if isinstance(r, dict) and "text" in r:
            self._ocr_out.setPlainText(r["text"] or "（未识别到文字）")
            self._ocr_status.setText(f"完成 · 尺寸 {r['size']} · 置信度 {r['confidence']} · {r['chars']} 字符")
        else:
            self._ocr_status.setText(f"识别失败：{r}")

    def _ocr_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择图片", "",
                                           "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif);;所有文件 (*)")
        if p:
            self._ocr_run_image(p, os.path.basename(p))

    def _ocr_clipboard(self):
        from PySide6.QtWidgets import QApplication
        pix = QApplication.clipboard().pixmap()
        if pix.isNull():
            notify(self, "剪贴板中没有图片")
            return
        from ..utils import pixmap_to_pil
        self._ocr_run_image(pixmap_to_pil(pix), "剪贴板图片")

    def _ocr_pdf(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF (*.pdf);;所有文件 (*)")
        if not p:
            return
        lang = self._ocr_lang.currentText()
        self._ocr_status.setText("正在处理 PDF（有文本层直接提取，扫描页走 OCR）…")
        start_worker(self, dx.ocr_pdf, (p, lang, 20, self._bridge.progress.emit),
                     self._on_ocr_pdf_done)

    def _on_ocr_progress(self, done, total):
        self._ocr_status.setText(f"PDF 处理中… {done}/{total} 页")

    def _on_ocr_pdf_done(self, r):
        self._ocr_out.setPlainText(r["text"] or "（未提取到文字）")
        self._ocr_status.setText(f"完成 · {r['total_pages']} 页 · {r['chars']} 字符")

    # ================================================================ 密码保险箱
    def _vault_tab(self):
        w, lay = tab_container()
        self._vault_lock = GlassCard("解锁保险箱", "使用主密码本地加密保存（Fernet + PBKDF2 48 万次迭代）", spacing=10)
        self._vault_pw = field("", "主密码")
        self._vault_pw.setEchoMode(QLineEdit.EchoMode.Password)
        unlock = btn("创建 / 解锁", True)
        on_click(unlock, self._vault_unlock)
        self._vault_lock.add_layout(row(self._vault_pw, unlock))
        self._vault_hint = label("", 9, False, True)
        self._vault_lock.add(self._vault_hint)
        lay.addWidget(self._vault_lock)

        self._vault_body = GlassCard("条目管理", "解锁后可增删改查；数据只写入本机 ~/.lumibox/vault.bin", spacing=10)
        self._vault_table = make_table(["分类", "标题", "账号", "密码", "网址"])
        self._vault_body.add(self._vault_table)
        add = btn("添加条目")
        edit = btn("编辑选中")
        cp = btn("复制密码")
        rm = btn("删除选中")
        save = btn("保存到磁盘", True)
        exp = btn("导出明文")
        lock = btn("锁定")
        on_click(add, self._vault_add)
        on_click(edit, self._vault_edit)
        on_click(cp, self._vault_copy)
        on_click(rm, self._vault_remove)
        on_click(save, self._vault_save)
        on_click(exp, self._vault_export)
        on_click(lock, self._vault_lock_now)
        self._vault_body.add_layout(row(add, edit, cp, rm))
        self._vault_body.add_layout(row(save, exp, lock))
        self._vault_status = label("未解锁", 9, False, True)
        self._vault_body.add(self._vault_status)
        lay.addWidget(self._vault_body)
        lay.addStretch(1)
        return w

    def _check_vault(self):
        if dx.vault_exists():
            self._vault_hint.setText("检测到已有保险箱，请输入主密码解锁")
        else:
            self._vault_hint.setText("尚未创建保险箱：输入一个新主密码即可创建")

    def _vault_unlock(self):
        pw = self._vault_pw.text()
        if not pw:
            notify(self, "请输入主密码")
            return
        try:
            if dx.vault_exists():
                self._vault_entries = dx.vault_load(pw)
            else:
                self._vault_entries = []
                dx.vault_save(self._vault_entries, pw)
        except ValueError as exc:
            warn(self, "解锁失败", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            warn(self, "解锁失败", str(exc))
            return
        self._vault_password = pw
        self._vault_unlocked = True
        self._vault_pw.clear()
        self._vault_status.setText(f"已解锁 · {len(self._vault_entries)} 个条目")
        self._vault_hint.setText("已解锁，可管理条目；离开前记得「保存到磁盘」")
        self._render_vault()
        notify(self, "保险箱已解锁")

    def _render_vault(self):
        rows = [[e.get("category", ""), e.get("title", ""), e.get("username", ""),
                 "••••••••", e.get("url", "")] for e in self._vault_entries]
        fill_table(self._vault_table, rows, 28, 1200)

    def _vault_need(self) -> bool:
        if not self._vault_unlocked:
            notify(self, "请先解锁保险箱")
            return False
        return True

    def _vault_add(self):
        if not self._vault_need():
            return
        d = self._vault_dialog()
        if d:
            self._vault_entries.append(d)
            self._render_vault()
            self._vault_status.setText(f"新增「{d['title']}」· 共 {len(self._vault_entries)} 条（未保存）")

    def _vault_edit(self):
        if not self._vault_need():
            return
        r = self._vault_table.currentRow()
        if r < 0 or r >= len(self._vault_entries):
            notify(self, "请先选中一条")
            return
        d = self._vault_dialog(self._vault_entries[r])
        if d:
            self._vault_entries[r] = d
            self._render_vault()
            self._vault_status.setText("已修改（未保存）")

    def _vault_dialog(self, cur: dict | None = None):
        cur = cur or {}
        title, ok1 = QInputDialog.getText(self, "条目", "标题：", text=cur.get("title", ""))
        if not ok1 or not title.strip():
            return None
        user, ok2 = QInputDialog.getText(self, "条目", "账号：", text=cur.get("username", ""))
        if not ok2:
            return None
        passwd, ok3 = QInputDialog.getText(self, "条目", "密码：", QLineEdit.EchoMode.Normal,
                                           cur.get("password", ""))
        if not ok3:
            return None
        cat, ok4 = QInputDialog.getText(self, "条目", "分类：", text=cur.get("category", "未分类"))
        url, ok5 = QInputDialog.getText(self, "条目", "网址：", text=cur.get("url", ""))
        note, ok6 = QInputDialog.getMultiLineText(self, "条目", "备注：", cur.get("note", ""))
        return {"title": title.strip(), "username": user, "password": passwd,
                "category": cat or "未分类", "url": url, "note": note}

    def _vault_copy(self):
        if not self._vault_need():
            return
        r = self._vault_table.currentRow()
        if 0 <= r < len(self._vault_entries):
            copy_text(self, self._vault_entries[r].get("password", ""))
        else:
            notify(self, "请先选中一条")

    def _vault_remove(self):
        if not self._vault_need():
            return
        r = self._vault_table.currentRow()
        if r < 0 or r >= len(self._vault_entries):
            notify(self, "请先选中一条")
            return
        e = self._vault_entries[r]
        if ask(self, "确认删除", f"删除「{e['title']}」？"):
            self._vault_entries.pop(r)
            self._render_vault()
            self._vault_status.setText("已删除（未保存）")

    def _vault_save(self):
        if not self._vault_need():
            return
        try:
            p = dx.vault_save(self._vault_entries, self._vault_password)
            self._vault_status.setText(f"已加密保存 {len(self._vault_entries)} 条 → {p}")
            notify(self, "保险箱已加密保存")
        except Exception as exc:  # noqa: BLE001
            warn(self, "保存失败", str(exc))

    def _vault_export(self):
        if not self._vault_need():
            return
        if not ask(self, "安全提示", "明文导出会包含所有密码，确认继续？"):
            return
        export_text(self, dx.vault_export_plain(self._vault_entries), "lumibox_vault_plain.txt")

    def _vault_lock_now(self):
        self._vault_unlocked = False
        self._vault_password = ""
        self._vault_entries = []
        self._vault_table.setRowCount(0)
        self._vault_status.setText("已锁定（内存中的明文已清除）")
        self._vault_hint.setText("已锁定，重新输入主密码解锁")
        notify(self, "保险箱已锁定")
