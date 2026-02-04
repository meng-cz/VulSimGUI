# widgets/bottom_panel.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QTextEdit

class BottomPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("底边栏")

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.logs = QTextEdit(); self.logs.setReadOnly(True)
        self.terminal = QTextEdit()
        self.output = QTextEdit(); self.output.setReadOnly(True)

        self.tabs.addTab(self.logs, "日志记录")
        self.tabs.addTab(self.terminal, "终端显示")
        self.tabs.addTab(self.output, "输出结果")
