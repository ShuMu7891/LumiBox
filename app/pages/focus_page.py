"""截图 & 效率页：屏幕截图/贴图、番茄钟、待办清单。"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRect, QPoint, Signal
from PySide6.QtGui import QGuiApplication, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (QTabWidget, QWidget, QLabel, QListWidgetItem, QFileDialog,
                              QInputDialog, QVBoxLayout, QLineEdit)

from ..glass import PageScaffold, GlassCard, label
from .. import doc_extra as dx
from ..utils import set_clipboard
from .common import (on_click, tab_container, row, btn, editor, mono, field,
                     combo, checkbox, spin, ask, warn, info_box, notify,
                     save_path, export_text, copy_text, make_table, fill_table)


# ================================================================ 区域截图遮罩
class RegionSelector(QWidget):
    """全屏半透明遮罩，拖拽框选区域后回调截图。"""
    captured = Signal(QPixmap)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._start = QPoint()
        self._end = QPoint()
        self._dragging = False
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
            self._full = screen.grabWindow(0)
        else:
            self._full = QPixmap()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self._dragging or (self._start != self._end):
            r = QRect(self._start, self._end).normalized()
            if not self._full.isNull():
                p.drawPixmap(r, self._full, r)
            p.setPen(QPen(QColor("#5b8dff"), 2))
            p.drawRect(r)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(91, 141, 255, 45))
            p.drawRect(r)
        p.setPen(QColor("#ffffff"))
        p.drawText(14, 26, "拖拽选择区域  ·  Esc 取消")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self._end = event.position().toPoint()
            self._dragging = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            r = QRect(self._start, self._end).normalized()
            if r.width() > 4 and r.height() > 4 and not self._full.isNull():
                self.captured.emit(self._full.copy(r))
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()


# ================================================================ 置顶贴图窗口
class PinWindow(QWidget):
    """无边框置顶贴图，可拖动、缩放、滚轮调透明度。"""
    def __init__(self, pix: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._pix = pix
        self._scale = 1.0
        self._opacity = 1.0
        self._drag = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._img = QLabel()
        self._img.setPixmap(pix)
        lay.addWidget(self._img)
        self.resize(pix.size())
        self.setWindowTitle("LumiBox 贴图（双击关闭 · 滚轮缩放）")
        self.setToolTip("拖动移动 · 双击关闭 · 滚轮缩放")

    def _apply(self):
        s = max(0.2, min(4.0, self._scale))
        pm = self._pix.scaled(int(self._pix.width() * s), int(self._pix.height() * s),
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        self._img.setPixmap(pm)
        self.resize(pm.size())
        self.setWindowOpacity(max(0.25, min(1.0, self._opacity)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None

    def mouseDoubleClickEvent(self, event):
        self.close()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._opacity += 0.05 if delta > 0 else -0.05
        else:
            self._scale += 0.1 if delta > 0 else -0.1
        self._apply()


class FocusPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("截图 & 效率", "屏幕截图 / 置顶贴图 · 番茄钟 · 待办清单", parent)
        self._shot: QPixmap | None = None
        self._pin_windows: list[PinWindow] = []
        self._region: RegionSelector | None = None

        # 番茄钟状态
        self._pomo_timer = QTimer(self)
        self._pomo_timer.setInterval(1000)
        self._pomo_timer.timeout.connect(self._pomo_tick)
        self._pomo_remain = 0
        self._pomo_mode = "专注"
        self._pomo_minutes = 25
        self._todos: list[dict] = dx.load_todos()

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._shot_tab(), "  截图 & 贴图  ")
        tabs.addTab(self._pomo_tab(), "  番茄钟  ")
        tabs.addTab(self._todo_tab(), "  待办清单  ")
        self.add_widget(tabs, 1)
        self._render_todos()
        self._render_pomo_stats()

    # ================================================================ 截图
    def _shot_tab(self):
        w, lay = tab_container()
        card = GlassCard("屏幕截图", "全屏 / 区域截图，可复制、保存或置顶为贴图", spacing=10)
        full = btn("全屏截图", True)
        region = btn("区域截图")
        clip = btn("从剪贴板导入")
        on_click(full, self._capture_full)
        on_click(region, self._capture_region)
        on_click(clip, self._from_clipboard)
        card.add_layout(row(full, region, clip))
        self._shot_preview = QLabel("尚未截图")
        self._shot_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._shot_preview.setMinimumHeight(260)
        self._shot_preview.setStyleSheet(
            "background: rgba(255,255,255,0.28); border-radius: 14px; color: #8896ad;")
        card.add(self._shot_preview)
        save = btn("保存 PNG")
        cp = btn("复制到剪贴板")
        pin = btn("置顶贴图", True)
        on_click(save, self._save_shot)
        on_click(cp, self._copy_shot)
        on_click(pin, self._pin_shot)
        card.add_layout(row(save, cp, pin))
        self._shot_status = label("就绪", 9, False, True)
        card.add(self._shot_status)
        card.add(label("贴图窗口：拖动移动 · 滚轮缩放 · Ctrl+滚轮调透明度 · 双击关闭", 9, False, True))
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    def _set_shot(self, pix: QPixmap, source: str):
        if pix.isNull():
            notify(self, "截图为空（当前环境可能不支持屏幕捕获）")
            return
        self._shot = pix
        thumb = pix.scaled(760, 260, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self._shot_preview.setPixmap(thumb)
        self._shot_status.setText(f"{source} · {pix.width()}×{pix.height()}")

    def _capture_full(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            notify(self, "未检测到屏幕")
            return
        self._set_shot(screen.grabWindow(0), "全屏截图")

    def _capture_region(self):
        try:
            self._region = RegionSelector()
            self._region.captured.connect(lambda pm: self._set_shot(pm, "区域截图"))
            self._region.showFullScreen()
        except Exception as exc:  # noqa: BLE001
            warn(self, "区域截图失败", str(exc))

    def _from_clipboard(self):
        from PySide6.QtWidgets import QApplication
        self._set_shot(QApplication.clipboard().pixmap(), "剪贴板图片")

    def _save_shot(self):
        if not self._shot:
            notify(self, "请先截图")
            return
        out = save_path(self, "保存截图", f"lumibox_{datetime.now():%Y%m%d_%H%M%S}.png", "PNG (*.png)")
        if out:
            self._shot.save(out, "PNG")
            notify(self, f"已保存 {os.path.basename(out)}")

    def _copy_shot(self):
        if not self._shot:
            notify(self, "请先截图")
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setPixmap(self._shot)
        notify(self, "截图已复制到剪贴板")

    def _pin_shot(self):
        if not self._shot:
            notify(self, "请先截图")
            return
        win = PinWindow(self._shot)
        win.show()
        self._pin_windows.append(win)
        notify(self, "已置顶贴图（双击关闭）")

    # ================================================================ 番茄钟
    def _pomo_tab(self):
        w, lay = tab_container()
        card = GlassCard("番茄钟", "专注 / 短休 / 长休循环，统计自动保存到本机", spacing=12)
        self._pomo_mode_combo = combo(["专注 25 分", "短休 5 分", "长休 15 分", "自定义"], "专注 25 分", 160)
        self._pomo_custom = spin(25, 1, 180, 100)
        card.add_layout(row(label("模式", 10, True), self._pomo_mode_combo,
                            label("自定义分钟", 10, True), self._pomo_custom))
        self._pomo_display = label("25:00", 44, True)
        self._pomo_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.add(self._pomo_display)
        self._pomo_state = label("准备开始", 10, False, True)
        self._pomo_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.add(self._pomo_state)
        go = btn("开始", True)
        pause = btn("暂停")
        reset = btn("重置")
        on_click(go, self._pomo_start)
        on_click(pause, self._pomo_pause)
        on_click(reset, self._pomo_reset)
        card.add_layout(row(go, pause, reset))
        lay.addWidget(card)

        stat = GlassCard("专注统计", "", spacing=8)
        self._pomo_stats = label("", 10)
        stat.add(self._pomo_stats)
        self._pomo_hist = make_table(["日期", "时间", "模式", "分钟"])
        stat.add(self._pomo_hist)
        lay.addWidget(stat)
        lay.addStretch(1)
        self._pomo_reset()
        return w

    def _pomo_minutes_for(self) -> int:
        m = self._pomo_mode_combo.currentText()
        if m.startswith("专注"):
            return 25
        if m.startswith("短休"):
            return 5
        if m.startswith("长休"):
            return 15
        return self._pomo_custom.value()

    def _pomo_start(self):
        if self._pomo_remain <= 0:
            self._pomo_minutes = self._pomo_minutes_for()
            self._pomo_remain = self._pomo_minutes * 60
            self._pomo_mode = self._pomo_mode_combo.currentText().split()[0]
        self._pomo_timer.start()
        self._pomo_state.setText(f"{self._pomo_mode}中… 保持专注")

    def _pomo_pause(self):
        self._pomo_timer.stop()
        self._pomo_state.setText("已暂停")

    def _pomo_reset(self):
        self._pomo_timer.stop()
        self._pomo_minutes = self._pomo_minutes_for()
        self._pomo_remain = self._pomo_minutes * 60
        m, s = divmod(self._pomo_remain, 60)
        self._pomo_display.setText(f"{m:02d}:{s:02d}")
        self._pomo_state.setText("准备开始")

    def _pomo_tick(self):
        if self._pomo_remain <= 0:
            self._pomo_timer.stop()
            self._pomo_display.setText("00:00")
            self._pomo_state.setText("本轮完成！")
            if self._pomo_mode == "专注":
                dx.pomo_record(self._pomo_minutes, "专注")
                self._render_pomo_stats()
            info_box(self, "番茄钟", f"{self._pomo_mode} {self._pomo_minutes} 分钟已完成！")
            return
        self._pomo_remain -= 1
        m, s = divmod(self._pomo_remain, 60)
        self._pomo_display.setText(f"{m:02d}:{s:02d}")

    def _render_pomo_stats(self):
        s = dx.pomo_stats()
        self._pomo_stats.setText(f"累计 {s['sessions']} 个番茄 · {s['minutes']} 分钟 · 今日 {s['today']} 个")
        rows = [[h.get("date", ""), h.get("time", ""), h.get("mode", ""), h.get("minutes", "")]
                for h in reversed(s["history"][-30:])]
        fill_table(self._pomo_hist, rows, 26, 700)

    # ================================================================ 待办
    def _todo_tab(self):
        w, lay = tab_container()
        card = GlassCard("待办清单", "自动保存到本机，勾选即标记完成", spacing=10)
        self._todo_input = field("", "输入新待办，回车或点添加")
        self._todo_input.returnPressed.connect(self._todo_add)
        self._todo_prio = combo(["普通", "重要", "紧急"], "普通", 110)
        add = btn("添加", True)
        on_click(add, self._todo_add)
        card.add_layout(row(self._todo_input, self._todo_prio, add))
        self._todo_list = None
        from PySide6.QtWidgets import QListWidget
        self._todo_list = QListWidget()
        self._todo_list.setMinimumHeight(260)
        self._todo_list.itemChanged.connect(self._todo_changed)
        self._todo_list.itemDoubleClicked.connect(self._todo_edit)
        card.add(self._todo_list)
        rm = btn("删除选中")
        clear_done = btn("清除已完成")
        exp = btn("导出 TXT")
        on_click(rm, self._todo_remove)
        on_click(clear_done, self._todo_clear_done)
        on_click(exp, self._todo_export)
        card.add_layout(row(rm, clear_done, exp))
        self._todo_stats = label("", 9, False, True)
        card.add(self._todo_stats)
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    def _todo_add(self):
        text = self._todo_input.text().strip()
        if not text:
            return
        self._todos.append(dx.add_todo(text, self._todo_prio.currentText()))
        self._todo_input.clear()
        self._sync_todos()

    def _render_todos(self):
        if self._todo_list is None:
            return
        self._todo_list.blockSignals(True)
        self._todo_list.clear()
        for t in self._todos:
            mark = {"普通": "", "重要": "❗", "紧急": "🔥"}.get(t.get("priority"), "")
            it = QListWidgetItem(f"{mark} {t['text']}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
            it.setCheckState(Qt.CheckState.Checked if t.get("done") else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, t["id"])
            if t.get("done"):
                it.setForeground(QColor("#8896ad"))
            self._todo_list.addItem(it)
        self._todo_list.blockSignals(False)
        done = sum(1 for t in self._todos if t.get("done"))
        self._todo_stats.setText(f"共 {len(self._todos)} 项 · 已完成 {done} 项 · 待办 {len(self._todos) - done} 项")

    def _sync_todos(self):
        dx.save_todos(self._todos)
        self._render_todos()

    def _todo_by_id(self, tid):
        return next((t for t in self._todos if t["id"] == tid), None)

    def _todo_changed(self, item):
        t = self._todo_by_id(item.data(Qt.ItemDataRole.UserRole))
        if t:
            t["done"] = item.checkState() == Qt.CheckState.Checked
            t["text"] = item.text().lstrip("❗🔥 ").strip() or t["text"]
            dx.save_todos(self._todos)
            done = sum(1 for x in self._todos if x.get("done"))
            self._todo_stats.setText(f"共 {len(self._todos)} 项 · 已完成 {done} 项 · 待办 {len(self._todos) - done} 项")

    def _todo_edit(self, item):
        t = self._todo_by_id(item.data(Qt.ItemDataRole.UserRole))
        if not t:
            return
        text, ok = QInputDialog.getText(self, "编辑待办", "内容：", text=t["text"])
        if ok and text.strip():
            t["text"] = text.strip()
            self._sync_todos()

    def _todo_remove(self):
        items = self._todo_list.selectedItems()
        if not items:
            notify(self, "请先选中待办")
            return
        ids = {i.data(Qt.ItemDataRole.UserRole) for i in items}
        self._todos = [t for t in self._todos if t["id"] not in ids]
        self._sync_todos()

    def _todo_clear_done(self):
        self._todos = [t for t in self._todos if not t.get("done")]
        self._sync_todos()
        notify(self, "已清除已完成项")

    def _todo_export(self):
        lines = [f"LumiBox 待办清单  ·  {datetime.now():%Y-%m-%d %H:%M}", "=" * 40]
        for t in self._todos:
            lines.append(f"[{'x' if t.get('done') else ' '}] ({t.get('priority')}) {t['text']}  {t.get('created','')}")
        export_text(self, "\n".join(lines), "lumibox_todos.txt")
