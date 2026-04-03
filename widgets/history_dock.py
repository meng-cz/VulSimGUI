# widgets/history_dock.py
from __future__ import annotations

import copy
import json
from datetime import datetime

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction, QUndoCommand, QUndoStack
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QLabel,
    QGroupBox,
    QTextEdit,
)


class _SnapshotCommand(QUndoCommand):
    """
    基于前端状态快照的撤销命令。
    push 到 QUndoStack 时，当前状态已经是 after_state，所以首次 redo 只跳过即可。
    """

    def __init__(
        self,
        text: str,
        before_state: dict,
        after_state: dict,
        apply_cb,
        params: dict | None = None,
        timestamp: str | None = None,
        parent=None,
    ):
        super().__init__(text, parent)
        self.before_state = copy.deepcopy(before_state)
        self.after_state = copy.deepcopy(after_state)
        self.apply_cb = apply_cb
        self.params = copy.deepcopy(params or {})
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._skip_first_redo = True

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        if callable(self.apply_cb):
            self.apply_cb(copy.deepcopy(self.after_state))

    def undo(self):
        if callable(self.apply_cb):
            self.apply_cb(copy.deepcopy(self.before_state))


class HistoryDock(QWidget):
    """
    Edit History（文档 2.4.1）：
    - 展示可撤销 / 可重做列表
    - 单击预览时间戳与操作参数
    - 右键支持 Undo / Undo to Here / Redo / Redo to Here
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("编辑历史")

        self._apply_callback = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.hint = QLabel("当前没有可撤销的前端编辑操作。")
        self.hint.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.hint)

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self.list.currentRowChanged.connect(self._update_preview)
        layout.addWidget(self.list, 3)

        preview_group = QGroupBox("操作预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)

        self.preview_title = QLabel("未选择")
        self.preview_title.setObjectName("pageTitle")

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(180)

        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_text, 1)
        layout.addWidget(preview_group, 2)

        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self.refresh)

        self.refresh()

    def set_apply_callback(self, callback):
        self._apply_callback = callback

    def clear_history(self):
        self.undo_stack.clear()
        self.refresh()

    def can_undo(self) -> bool:
        return self.undo_stack.canUndo()

    def can_redo(self) -> bool:
        return self.undo_stack.canRedo()

    def undo(self):
        if self.undo_stack.canUndo():
            self.undo_stack.undo()

    def redo(self):
        if self.undo_stack.canRedo():
            self.undo_stack.redo()

    def push_snapshot_command(
        self,
        text: str,
        before_state: dict,
        after_state: dict,
        params: dict | None = None,
    ) -> bool:
        if not callable(self._apply_callback):
            return False
        if before_state == after_state:
            return False

        self.undo_stack.push(
            _SnapshotCommand(
                text=text,
                before_state=before_state,
                after_state=after_state,
                apply_cb=self._apply_callback,
                params=params,
            )
        )
        return True

    def refresh(self):
        """
        将 QUndoStack 映射到 QListWidget：
        - index 之前的是已执行（可 Undo）
        - index 之后的是未执行（可 Redo）
        """
        current_row = self.list.currentRow()
        self.list.clear()

        count = self.undo_stack.count()
        idx = self.undo_stack.index()

        undo_count = idx
        redo_count = max(0, count - idx)
        if count == 0:
            self.hint.setText("当前没有可撤销的前端编辑操作。")
        else:
            self.hint.setText(f"可撤销 {undo_count} 项，可重做 {redo_count} 项。")

        for i in range(count):
            cmd = self.undo_stack.command(i)
            item = QListWidgetItem(cmd.text())
            item.setData(Qt.ItemDataRole.UserRole, i)
            if i < idx:
                item.setForeground(self.list.palette().text().color())
            else:
                item.setForeground(Qt.GlobalColor.gray)
            self.list.addItem(item)

        if count == 0:
            self.preview_title.setText("未选择")
            self.preview_text.clear()
            return

        if 0 <= current_row < count:
            sel = current_row
        else:
            sel = max(0, min(idx - 1, count - 1))
        self.list.setCurrentRow(sel)
        self._update_preview(sel)

    def _command_for_row(self, row: int):
        if row < 0 or row >= self.undo_stack.count():
            return None
        return self.undo_stack.command(row)

    def _update_preview(self, row: int):
        cmd = self._command_for_row(row)
        if cmd is None:
            self.preview_title.setText("未选择")
            self.preview_text.clear()
            return

        status = "已执行，可撤销" if row < self.undo_stack.index() else "未执行，可重做"
        timestamp = getattr(cmd, "timestamp", "")
        params = getattr(cmd, "params", {}) or {}
        try:
            params_text = json.dumps(params, ensure_ascii=False, indent=2, sort_keys=True)
        except TypeError:
            params_text = str(params)

        lines = [
            f"状态：{status}",
            f"时间：{timestamp or '（未知）'}",
            "",
            "参数：",
            params_text or "{}",
        ]
        self.preview_title.setText(cmd.text())
        self.preview_text.setPlainText("\n".join(lines))

    def _on_context_menu(self, pos: QPoint):
        item = self.list.itemAt(pos)
        row = self.list.row(item) if item is not None else self.list.currentRow()
        if row < 0 or self.undo_stack.count() == 0:
            return

        self.list.setCurrentRow(row)

        idx = self.undo_stack.index()
        menu = QMenu(self)

        act_undo = QAction("Undo", self)
        act_undo.setEnabled(self.undo_stack.canUndo())
        act_undo.triggered.connect(self.undo_stack.undo)

        act_redo = QAction("Redo", self)
        act_redo.setEnabled(self.undo_stack.canRedo())
        act_redo.triggered.connect(self.undo_stack.redo)

        act_undo_to = QAction("Undo to Here", self)
        act_redo_to = QAction("Redo to Here", self)

        def undo_to_here():
            target_index = row
            while self.undo_stack.index() > target_index:
                self.undo_stack.undo()

        def redo_to_here():
            target_index = row + 1
            while self.undo_stack.index() < target_index:
                self.undo_stack.redo()

        act_undo_to.setEnabled(idx > 0 and row < idx)
        act_redo_to.setEnabled(row >= idx)
        act_undo_to.triggered.connect(undo_to_here)
        act_redo_to.triggered.connect(redo_to_here)

        menu.addAction(act_undo)
        menu.addAction(act_undo_to)
        menu.addSeparator()
        menu.addAction(act_redo)
        menu.addAction(act_redo_to)

        menu.exec(self.list.mapToGlobal(pos))
