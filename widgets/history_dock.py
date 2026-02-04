# widgets/history_dock.py
from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QMenu, QLabel
)
from PyQt6.QtGui import QUndoStack, QUndoCommand


class _LabelCommand(QUndoCommand):
    """示例命令：你后续可替换成真实的模型/后端操作命令。"""
    def __init__(self, text: str, do_cb=None, undo_cb=None, parent=None):
        super().__init__(text, parent)
        self._do_cb = do_cb
        self._undo_cb = undo_cb

    def redo(self):
        if callable(self._do_cb):
            self._do_cb()

    def undo(self):
        if callable(self._undo_cb):
            self._undo_cb()


class HistoryDock(QWidget):
    """
    Edit History（文档 2.4.1）：展示可撤销/可重做列表，支持右键：
      - Undo
      - Undo to Here
      - Redo
      - Redo to Here
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("编辑历史")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.hint = QLabel("可视化展示当前所有的可撤销操作列表和可重做操作列表")
        self.hint.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.hint)

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.list)

        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self.refresh)

        # 示例：先塞几条历史，便于你运行看到效果（可删）
        self.push_demo_commands()

        self.refresh()

    def push_demo_commands(self):
        # 这些 demo 命令只为了让历史列表有内容；你接入真实编辑操作后可删除
        for t in ["Added Request_Port", "Connected Instance_A -> Pipe_01", "Moved Pipe_01"]:
            self.undo_stack.push(_LabelCommand(t))

    def refresh(self):
        """
        将 QUndoStack 映射到 QListWidget：
        - index 之前的是已执行（可 Undo）
        - index 之后的是未执行（可 Redo）
        """
        self.list.clear()
        count = self.undo_stack.count()
        idx = self.undo_stack.index()  # 下一个将要 redo 的位置

        for i in range(count):
            text = self.undo_stack.command(i).text()
            item = QListWidgetItem(text)
            # 已执行区域：高亮；未执行区域：置灰
            if i < idx:
                item.setForeground(Qt.GlobalColor.white)
            else:
                item.setForeground(Qt.GlobalColor.gray)
            self.list.addItem(item)

        # 默认选中“当前状态”的上一条（常见 IDE 习惯）
        if count > 0:
            sel = max(0, min(idx - 1, count - 1))
            self.list.setCurrentRow(sel)

    def _on_context_menu(self, pos: QPoint):
        row = self.list.currentRow()
        if row < 0 or self.undo_stack.count() == 0:
            return

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

        # “Undo to Here”：把 stack index 回退到 row（row 及其之后都撤销）
        # 注意：QUndoStack 的 index 是“下一次 redo 的位置”
        # 若要让 row 成为“最后已执行”，则目标 index = row + 1
        def undo_to_here():
            target_index = row  # 撤销到 row 之前（即 row 也撤销）
            while self.undo_stack.index() > target_index:
                self.undo_stack.undo()

        def redo_to_here():
            target_index = row + 1
            while self.undo_stack.index() < target_index:
                self.undo_stack.redo()

        act_undo_to.setEnabled(idx > 0 and row < idx)      # row 在已执行区
        act_redo_to.setEnabled(row >= idx)                 # row 在未执行区（含 idx）
        act_undo_to.triggered.connect(undo_to_here)
        act_redo_to.triggered.connect(redo_to_here)

        menu.addAction(act_undo)
        menu.addAction(act_undo_to)
        menu.addSeparator()
        menu.addAction(act_redo)
        menu.addAction(act_redo_to)

        menu.exec(self.list.mapToGlobal(pos))
