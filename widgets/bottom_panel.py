# widgets/bottom_panel.py
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTextEdit,
    QPushButton,
    QLabel,
    QSplitter,
)


class _TerminalEditor(QTextEdit):
    runRequested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.runRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class BottomPanel(QWidget):
    terminalRunRequested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("底边栏")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.logs = QTextEdit()
        self.logs.setReadOnly(True)

        self.terminal = _TerminalEditor()
        self.terminal.setPlaceholderText(
            "# 终端脚本示例\n"
            "status\n"
            "list modules\n"
            "build\n"
            "run\n"
            "repeat 2 echo hello\n"
            "if project_open list configs"
        )
        self.terminal.runRequested.connect(self._emit_terminal_run)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)

        self._build_logs_tab()
        self._build_terminal_tab()
        self._build_output_tab()

    def _build_logs_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        hint = QLabel("显示界面日志和后端交互日志。")
        hint.setStyleSheet("color: #94a3b8;")

        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self.logs.clear)

        top.addWidget(hint)
        top.addStretch(1)
        top.addWidget(btn_clear)
        root.addLayout(top)
        root.addWidget(self.logs, 1)

        self.tabs.addTab(page, "日志记录")

    def _build_terminal_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        hint = QLabel("直接执行前端终端脚本，支持多行命令、repeat 和简单条件。")
        hint.setStyleSheet("color: #94a3b8;")

        self.terminal_status = QLabel("待执行")
        self.terminal_status.setStyleSheet("color: #64748b;")

        btn_run = QPushButton("执行脚本")
        btn_run.clicked.connect(self._emit_terminal_run)
        btn_clear_script = QPushButton("清空脚本")
        btn_clear_script.clicked.connect(self.terminal.clear)
        btn_clear_result = QPushButton("清空结果")
        btn_clear_result.clicked.connect(self.terminal_output.clear)

        top.addWidget(hint)
        top.addStretch(1)
        top.addWidget(self.terminal_status)
        top.addWidget(btn_run)
        top.addWidget(btn_clear_script)
        top.addWidget(btn_clear_result)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.terminal)
        splitter.addWidget(self.terminal_output)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.tabs.addTab(page, "终端")

    def _build_output_tab(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self.output_status = QLabel("显示最近一次 Build / Run 的标准输出。")
        self.output_status.setStyleSheet("color: #94a3b8;")

        btn_clear = QPushButton("清空输出")
        btn_clear.clicked.connect(self.output.clear)

        top.addWidget(self.output_status)
        top.addStretch(1)
        top.addWidget(btn_clear)
        root.addLayout(top)
        root.addWidget(self.output, 1)

        self.tabs.addTab(page, "输出")

    def _emit_terminal_run(self):
        script = self.terminal.toPlainText()
        self.terminalRunRequested.emit(script)

    def append_terminal_line(self, text: str):
        self.terminal_output.append(text)

    def set_terminal_status(self, text: str):
        self.terminal_status.setText(text)

    def set_output_status(self, text: str):
        self.output_status.setText(text)
