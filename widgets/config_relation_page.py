# widgets/config_relation_page.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit


class ConfigRelationPage(QWidget):
    def __init__(self, name: str, comment: str, expr: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"配置项：{name}"))
        layout.addWidget(QLabel("注释："))
        c = QTextEdit(); c.setReadOnly(True); c.setText(comment)
        layout.addWidget(c)

        layout.addWidget(QLabel("表达式："))
        e = QTextEdit(); e.setReadOnly(True); e.setText(expr)
        layout.addWidget(e)

        layout.addWidget(QLabel("关联关系（占位）：这里将显示该配置项在全局的依赖/反向依赖/引用位置等。"))
