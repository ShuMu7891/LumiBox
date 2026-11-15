"""文件管家页：重复文件去重、批量重命名、文件粉碎、hosts 编辑器。"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (QTabWidget, QTableWidgetItem, QFileDialog, QHBoxLayout)

from ..glass import PageScaffold, GlassCard, label, divider
from .. import power as pw
from .common import (on_click, changed, tab_container, row, btn, editor, mono, field,
                     combo, checkbox, spin, ask, warn, info_box, pick_dir, save_path,
                     pick_file, export_text, copy_text, start_worker, DropList,
                     make_table, fill_table, notify)


class _Bridge(QObject):
    progress = Signal(int, int)


class FilesPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("文件管家", "重复文件清理 · 批量重命名 · 安全粉碎 · hosts 编辑", parent)
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_dup_progress)
        self._dup_groups: list[dict] = []
        self._rename_plan: list[dict] = []
        self._undo: list[dict] = []
        self._dup_stop = False

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._dup_tab(), "  重复文件  ")
        tabs.addTab(self._rename_tab(), "  批量重命名  ")
        tabs.addTab(self._shred_tab(), "  文件粉碎  ")
        tabs.addTab(self._hosts_tab(), "  hosts 编辑  ")
        self.add_widget(tabs, 1)

    # ================================================================ Tab 1 去重
    def _dup_tab(self):
        w, lay = tab_container()
        card = GlassCard("重复文件查找", "先按大小分组，再用哈希精确比对；只删除你勾选的副本", spacing=10)
        self._dup_dir = field("", "选择要扫描的目录（也可把文件夹拖到下一点「开始扫描」）")
        b1 = btn("选择目录")
        on_click(b1, self._choose_dup_dir)
        self._dup_min = spin(1, 0, 1_000_000, 110, "最小 ")
        self._dup_recursive = checkbox("包含子目录", True)
        self._dup_scan = btn("开始扫描", True)
        on_click(self._dup_scan, self._scan_dup)
        card.add_layout(row(self._dup_dir, b1))
        card.add_layout(row(label("最小体积", 10, True), self._dup_min, self._dup_recursive,
                            self._dup_scan))
        self._dup_status = label("尚未扫描", 9, False, True)
        card.add(self._dup_status)
        lay.addWidget(card)

        res = GlassCard("扫描结果", "勾选要删除的副本，建议每组至少保留一个原件", spacing=10)
        self._dup_table = make_table(["删除", "组", "大小", "路径", "修改时间"])
        self._dup_table.setColumnWidth(0, 52)
        res.add(self._dup_table)
        b2 = btn("删除勾选", True)
        b3 = btn("导出报告")
        b4 = btn("打开所在文件夹")
        on_click(b2, self._delete_dups)
        on_click(b3, self._export_dups)
        on_click(b4, self._open_dup_folder)
        res.add_layout(row(b2, b3, b4))
        lay.addWidget(res)
        lay.addStretch(1)
        return w

    def _choose_dup_dir(self):
        d = pick_dir(self, "选择要扫描重复文件的目录")
        if d:
            self._dup_dir.setText(d)

    def _on_dup_progress(self, done, total):
        self._dup_status.setText(f"正在比对… {done}/{total} 组")

    def _scan_dup(self):
        root = self._dup_dir.text().strip()
        if not root or not os.path.isdir(root):
            warn(self, "目录无效", "请先选择一个存在的目录")
            return
        self._dup_stop = False
        self._dup_scan.setEnabled(False)
        self._dup_status.setText("正在枚举文件…")
        start_worker(self, pw.find_duplicates,
                     (root, self._dup_min.value(), self._dup_recursive.isChecked(),
                      self._bridge.progress.emit, lambda: self._dup_stop),
                     self._on_dup_done)

    def _on_dup_done(self, groups):
        self._dup_scan.setEnabled(True)
        self._dup_groups = groups or []
        t = self._dup_table
        t.setRowCount(0)
        r = 0
        for gi, g in enumerate(self._dup_groups, 1):
            for fi, f in enumerate(g["files"]):
                t.insertRow(r)
                chk = QTableWidgetItem("")
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                # 默认勾选每组的第 2 个及以后的副本，保留第一个原件
                chk.setCheckState(Qt.CheckState.Unchecked if fi == 0 else Qt.CheckState.Checked)
                t.setItem(r, 0, chk)
                t.setItem(r, 1, QTableWidgetItem(f"#{gi}"))
                sz = QTableWidgetItem(f"{g['size']:,} B")
                sz.setToolTip(g["hash"])
                t.setItem(r, 2, sz)
                p = QTableWidgetItem(f["path"])
                p.setToolTip(f["path"])
                t.setItem(r, 3, p)
                t.setItem(r, 4, QTableWidgetItem(f["mtime"]))
                r += 1
        t.setFixedHeight(min(max(120, r * 30 + 36), 900))
        wasted = sum(g["size"] * (len(g["files"]) - 1) for g in self._dup_groups)
        self._dup_status.setText(
            f"扫描完成：{len(self._dup_groups)} 组重复、{r} 个文件，"
            f"最多可释放约 {wasted / 1024 / 1024:.2f} MB" if self._dup_groups
            else "扫描完成：未发现重复文件")
        if not self._dup_groups:
            notify(self, "没有发现重复文件")

    def _checked_dup_paths(self) -> list[str]:
        out = []
        for r in range(self._dup_table.rowCount()):
            it = self._dup_table.item(r, 0)
            p = self._dup_table.item(r, 3)
            if it and p and it.checkState() == Qt.CheckState.Checked:
                out.append(p.text())
        return out

    def _delete_dups(self):
        paths = self._checked_dup_paths()
        if not paths:
            notify(self, "没有勾选任何文件")
            return
        if not ask(self, "确认删除", f"将永久删除 {len(paths)} 个文件，此操作不可撤销。\n确认继续？"):
            return
        res = pw.delete_paths(paths)
        notify(self, f"已删除 {len(res['deleted'])} 个文件，失败 {len(res['failed'])} 个")
        self._on_dup_done(self._dup_groups)

    def _export_dups(self):
        if not self._dup_groups:
            notify(self, "没有可导出的结果")
            return
        lines = ["LumiBox 重复文件报告", "=" * 60]
        for gi, g in enumerate(self._dup_groups, 1):
            lines.append(f"\n组 {gi} · {g['size']:,} B · SHA256 {g['hash']}")
            for f in g["files"]:
                lines.append(f"  {f['path']}  ({f['mtime']})")
        export_text(self, "\n".join(lines), "lumibox_duplicates.txt")

    def _open_dup_folder(self):
        for r in range(self._dup_table.rowCount()):
            p = self._dup_table.item(r, 3)
            if p and self._dup_table.item(r, 0).isSelected():
                self._reveal(p.text())
                return
        paths = self._checked_dup_paths()
        if paths:
            self._reveal(paths[0])

    @staticmethod
    def _reveal(path: str):
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        if not os.path.isdir(folder):
            return
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    # ================================================================ Tab 2 重命名
    def _rename_tab(self):
        w, lay = tab_container()
        src = GlassCard("文件列表", "从资源管理器把文件拖进下方列表，或用按钮添加", spacing=10)
        self._rename_list = DropList()
        self._rename_list.files_dropped.connect(self._rename_list.add_paths)
        src.add(self._rename_list)
        a = btn("添加文件")
        d = btn("添加目录内文件")
        rm = btn("移除选中")
        cl = btn("清空")
        on_click(a, self._add_rename_files)
        on_click(d, self._add_rename_dir)
        on_click(rm, self._rename_list.remove_selected)
        on_click(cl, self._rename_list.clear)
        src.add_layout(row(a, d, rm, cl))
        lay.addWidget(src)

        rule = GlassCard("命名规则", "设置规则后先预览，确认无误再执行；支持一键撤销", spacing=10)
        self._rn_mode = combo(["序号", "前缀后缀", "查找替换", "大小写", "时间戳"], "序号", 130)
        changed(self._rn_mode, "currentIndexChanged", self._on_rn_mode)
        rule.add_layout(row(label("模式", 10, True), self._rn_mode))

        self._rn_prefix = field("", "前缀")
        self._rn_suffix = field("", "后缀")
        self._rn_base = field("IMG_", "序号前缀，如 IMG_")
        self._rn_start = spin(1, 0, 999999, 90)
        self._rn_pad = spin(3, 0, 10, 80)
        self._rn_find = field("", "查找内容")
        self._rn_replace = field("", "替换为")
        self._rn_regex = checkbox("正则", False)
        self._rn_case = combo(["不变", "全部大写", "全部小写", "首字母大写", "标题化"], "不变", 130)
        self._rn_extcase = combo(["不变", "小写", "大写"], "不变", 100)
        self._rn_keepext = checkbox("保留扩展名", True)

        self._rn_rows = {
            "序号": [row(label("基础名", 10, True), self._rn_base, label("起始", 10, True),
                         self._rn_start, label("补零", 10, True), self._rn_pad)],
            "前缀后缀": [row(label("前缀", 10, True), self._rn_prefix, label("后缀", 10, True), self._rn_suffix)],
            "查找替换": [row(label("查找", 10, True), self._rn_find, label("替换", 10, True),
                           self._rn_replace, self._rn_regex)],
            "大小写": [row(label("文件名", 10, True), self._rn_case, label("扩展名", 10, True), self._rn_extcase)],
            "时间戳": [],
        }
        self._rn_holder = GlassCard(radius=14, spacing=8)
        self._rn_holder.body().setContentsMargins(16, 10, 16, 12)
        self._rn_holder.add(label("参数", 10, True))
        for lays in self._rn_rows.values():
            for l in lays:
                self._rn_holder.add_layout(l)
        rule.add(self._rn_holder)
        rule.add(self._rn_keepext)
        pv = btn("生成预览", True)
        ex = btn("执行重命名", False)
        un = btn("撤销上次")
        on_click(pv, self._preview_rename)
        on_click(ex, self._apply_rename)
        on_click(un, self._undo_rename)
        rule.add_layout(row(pv, ex, un))
        lay.addWidget(rule)

        prev = GlassCard("预览", "红色「冲突」行不会被重命名", spacing=10)
        self._rn_table = make_table(["原文件名", "新文件名", "状态"])
        prev.add(self._rn_table)
        self._rn_status = label("尚未生成预览", 9, False, True)
        prev.add(self._rn_status)
        lay.addWidget(prev)
        lay.addStretch(1)
        self._on_rn_mode()
        return w

    def _on_rn_mode(self):
        cur = self._rn_mode.currentText()
        for mode, lays in self._rn_rows.items():
            for l in lays:
                for i in range(l.count()):
                    item = l.itemAt(i)
                    if item and item.widget():
                        item.widget().setVisible(mode == cur)
        self._rn_keepext.setVisible(cur in ("查找替换", "大小写"))

    def _add_rename_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", "所有文件 (*)")
        if paths:
            self._rename_list.add_paths(paths)

    def _add_rename_dir(self):
        d = pick_dir(self, "选择目录")
        if not d:
            return
        paths = [os.path.join(d, n) for n in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, n))]
        self._rename_list.add_paths(paths)

    def _preview_rename(self):
        files = self._rename_list.paths()
        if not files:
            notify(self, "请先添加文件")
            return
        try:
            self._rename_plan = pw.build_rename_plan(
                files, self._rn_mode.currentText(),
                prefix=self._rn_prefix.text(), suffix=self._rn_suffix.text(),
                find=self._rn_find.text(), replace=self._rn_replace.text(),
                use_regex=self._rn_regex.isChecked(), base=self._rn_base.text(),
                start=self._rn_start.value(), pad=self._rn_pad.value(),
                case=self._rn_case.currentText(), ext_case=self._rn_extcase.currentText(),
                keep_ext=self._rn_keepext.isChecked())
        except re.error as exc:
            warn(self, "正则错误", str(exc))
            return
        rows = [[e["old_name"], e["new_name"],
                 "冲突" if e["conflict"] else ("改名" if e["changed"] else "不变")]
                for e in self._rename_plan]
        fill_table(self._rn_table, rows, 28, 1400)
        bad = sum(1 for e in self._rename_plan if e["conflict"])
        self._rn_status.setText(f"共 {len(rows)} 项，{bad} 项冲突会被跳过")

    def _apply_rename(self):
        if not self._rename_plan:
            notify(self, "请先生成预览")
            return
        active = sum(1 for e in self._rename_plan if e["changed"] and not e["conflict"])
        if not active:
            notify(self, "没有需要执行的更改")
            return
        if not ask(self, "确认重命名", f"将重命名 {active} 个文件，确认继续？"):
            return
        res = pw.apply_rename(self._rename_plan)
        self._undo = res["undo"]
        notify(self, f"成功 {len(res['ok'])} 个，失败 {len(res['failed'])} 个")
        self._rename_list.clear()
        self._rename_list.add_paths([e["new"] for e in self._rename_plan
                                     if e["old"] in res["ok"]])
        self._preview_rename()

    def _undo_rename(self):
        if not self._undo:
            notify(self, "没有可撤销的操作")
            return
        res = pw.undo_rename(self._undo)
        ok_from = set(res["ok"])
        restored = [e["to"] for e in self._undo if e["from"] in ok_from] + \
                   [e["from"] for e in self._undo if e["from"] not in ok_from]
        notify(self, f"已撤销 {len(res['ok'])} 个，失败 {len(res['failed'])} 个")
        self._undo = []
        self._rename_plan = []
        self._rename_list.clear()
        self._rename_list.add_paths(restored)
        self._rn_table.setRowCount(0)
        self._rn_status.setText("已撤销上次重命名")

    # ================================================================ Tab 3 粉碎
    def _shred_tab(self):
        w, lay = tab_container()
        card = GlassCard("文件粉碎机", "多轮覆写内容后删除文件，降低被数据恢复软件还原的可能", spacing=10)
        self._shred_list = DropList()
        self._shred_list.files_dropped.connect(self._shred_list.add_paths)
        card.add(self._shred_list)
        a = btn("添加文件")
        rm = btn("移除选中")
        cl = btn("清空")
        on_click(a, self._add_shred_files)
        on_click(rm, self._shred_list.remove_selected)
        on_click(cl, self._shred_list.clear)
        card.add_layout(row(a, rm, cl))
        self._shred_passes = spin(3, 1, 35, 100)
        self._shred_confirm = checkbox("我已确认：粉碎后无法恢复，且列表内文件均已备份", False)
        go = btn("开始粉碎", True)
        on_click(go, self._do_shred)
        card.add_layout(row(label("覆写轮数", 10, True), self._shred_passes, go))
        card.add(self._shred_confirm)
        self._shred_status = label("等待操作", 9, False, True)
        card.add(self._shred_status)
        card.add(label("提示：SSD、日志型文件系统与云同步盘无法保证物理不可恢复，"
                       "敏感数据请优先使用全盘加密。", 9, False, True))
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    def _add_shred_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要粉碎的文件", "", "所有文件 (*)")
        if paths:
            self._shred_list.add_paths(paths)

    def _do_shred(self):
        paths = self._shred_list.paths()
        if not paths:
            notify(self, "请先添加文件")
            return
        if not self._shred_confirm.isChecked():
            warn(self, "需要确认", "请先勾选确认框")
            return
        if not ask(self, "危险操作", f"将不可恢复地粉碎 {len(paths)} 个文件，确认继续？"):
            return
        passes = self._shred_passes.value()
        results = []
        for i, p in enumerate(paths, 1):
            r = pw.shred_file(p, passes)
            results.append(r)
            self._shred_status.setText(f"正在粉碎 {i}/{len(paths)}：{os.path.basename(p)}")
        ok = sum(1 for r in results if "error" not in r)
        for r in results:
            if "error" in r:
                notify(self, f"{os.path.basename(r['path'])} 失败：{r['error']}")
        notify(self, f"粉碎完成：成功 {ok} 个，失败 {len(results) - ok} 个")
        self._shred_list.clear()
        self._shred_confirm.setChecked(False)
        self._shred_status.setText(f"完成：{ok}/{len(results)} 个文件已安全删除")

    # ================================================================ Tab 4 hosts
    def _hosts_tab(self):
        w, lay = tab_container()
        card = GlassCard("hosts 文件编辑器", "保存时自动备份；修改系统 hosts 通常需要管理员权限", spacing=10)
        self._hosts_path = field(pw.hosts_path(), "hosts 文件完整路径")
        b1 = btn("读取")
        b2 = btn("另存为")
        b3 = btn("保存到该路径", True)
        on_click(b1, self._load_hosts)
        on_click(b2, self._save_hosts_as)
        on_click(b3, self._save_hosts)
        card.add_layout(row(self._hosts_path, b1))
        self._hosts_edit = editor("# 点击「读取」加载 hosts 内容", 300)
        self._hosts_edit.setLineWrapMode(self._hosts_edit.LineWrapMode.NoWrap)
        card.add(self._hosts_edit)
        self._hosts_preset = combo(list(pw.HOST_PRESETS), "", 170)
        ins = btn("插入预设")
        on_click(ins, self._insert_preset)
        card.add_layout(row(label("预设", 10, True), self._hosts_preset, ins, b2, b3))
        self._hosts_status = label("就绪", 9, False, True)
        card.add(self._hosts_status)
        lay.addWidget(card)

        bak = GlassCard("备份与恢复", "每次保存都会在此留下时间戳备份", spacing=10)
        self._bak_list = DropList(directories=False)
        self._bak_list.setMinimumHeight(90)
        self._bak_list.itemDoubleClicked.connect(self._restore_backup)
        bak.add(self._bak_list)
        rf = btn("刷新备份列表")
        rb = btn("恢复选中备份")
        on_click(rf, self._refresh_backups)
        on_click(rb, self._restore_backup)
        bak.add_layout(row(rf, rb))
        lay.addWidget(bak)
        lay.addStretch(1)
        self._refresh_backups()
        return w

    def _load_hosts(self):
        p = self._hosts_path.text().strip()
        try:
            self._hosts_edit.setPlainText(pw.read_hosts(p))
            self._hosts_status.setText(f"已读取 {p}")
        except Exception as exc:  # noqa: BLE001
            warn(self, "读取失败", str(exc))

    def _save_hosts_as(self):
        out = save_path(self, "另存为 hosts 副本", "hosts.txt", "文本文件 (*.txt);;所有文件 (*)")
        if out:
            with open(out, "w", encoding="utf-8") as f:
                f.write(self._hosts_edit.toPlainText())
            notify(self, f"已另存为 {os.path.basename(out)}")

    def _save_hosts(self):
        p = self._hosts_path.text().strip()
        if not ask(self, "确认写入", f"将写入 {p}\n（自动备份原文件）\n确认继续？"):
            return
        try:
            r = pw.write_hosts(self._hosts_edit.toPlainText(), p)
            self._hosts_status.setText(f"已保存 {r['bytes']} 字节，备份：{r['backup']}")
            notify(self, "hosts 已保存")
            self._refresh_backups()
        except Exception as exc:  # noqa: BLE001
            warn(self, "保存失败", f"{exc}\n（Windows 需以管理员身份运行，Linux 需 root）")

    def _insert_preset(self):
        name = self._hosts_preset.currentText()
        if name:
            self._hosts_edit.append("\n" + pw.HOST_PRESETS[name])

    def _refresh_backups(self):
        self._bak_list.clear()
        from PySide6.QtWidgets import QListWidgetItem
        for b in pw.list_hosts_backups():
            li = QListWidgetItem(f"{b['name']}  ·  {b['size']} B")
            li.setData(Qt.ItemDataRole.UserRole, b["path"])
            li.setToolTip(b["path"])
            self._bak_list.addItem(li)

    def _restore_backup(self, *_):
        items = self._bak_list.selectedItems()
        if not items:
            notify(self, "请先在备份列表中选择一项")
            return
        src = items[0].data(Qt.ItemDataRole.UserRole)
        try:
            self._hosts_edit.setPlainText(pw.read_hosts(src))
            self._hosts_status.setText(f"已载入备份 {os.path.basename(src)}（尚未写入系统）")
            notify(self, "备份已载入编辑区")
        except Exception as exc:  # noqa: BLE001
            warn(self, "读取备份失败", str(exc))
