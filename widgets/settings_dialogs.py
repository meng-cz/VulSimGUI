# widgets/settings_dialogs.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class PreferencesDialog(QDialog):
    def __init__(self, preferences: dict, current_theme_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.resize(620, 420)

        prefs = preferences or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        summary = QLabel("调整前端预览模式下的界面行为。这些设置会保存在本机，下次打开仍会生效。")
        summary.setWordWrap(True)
        summary.setStyleSheet("color:#94a3b8;")
        root.addWidget(summary)

        general_group = QGroupBox("常规")
        general_form = QFormLayout(general_group)
        general_form.setContentsMargins(12, 12, 12, 12)
        general_form.setSpacing(8)

        self.chk_auto_switch_output = QCheckBox("Build / Run 后自动切到输出页")
        self.chk_auto_switch_output.setChecked(bool(prefs.get("auto_switch_output_tab", True)))

        self.chk_clear_output_before_build = QCheckBox("Build 前清空旧输出")
        self.chk_clear_output_before_build.setChecked(bool(prefs.get("clear_output_before_build", True)))

        self.chk_clear_terminal_before_run = QCheckBox("执行终端脚本前清空终端结果")
        self.chk_clear_terminal_before_run.setChecked(bool(prefs.get("clear_terminal_before_run", False)))

        self.chk_auto_open_logs_on_terminal_error = QCheckBox("终端脚本报错时自动切到日志页")
        self.chk_auto_open_logs_on_terminal_error.setChecked(bool(prefs.get("auto_open_logs_on_terminal_error", True)))

        self.cmb_default_bottom_tab = QComboBox()
        self.cmb_default_bottom_tab.addItem("日志记录", 0)
        self.cmb_default_bottom_tab.addItem("终端", 1)
        self.cmb_default_bottom_tab.addItem("输出", 2)
        default_tab = int(prefs.get("default_bottom_tab", 0))
        for idx in range(self.cmb_default_bottom_tab.count()):
            if self.cmb_default_bottom_tab.itemData(idx) == default_tab:
                self.cmb_default_bottom_tab.setCurrentIndex(idx)
                break

        general_form.addRow(self.chk_auto_switch_output)
        general_form.addRow(self.chk_clear_output_before_build)
        general_form.addRow(self.chk_clear_terminal_before_run)
        general_form.addRow(self.chk_auto_open_logs_on_terminal_error)
        general_form.addRow("启动后默认显示底边栏标签：", self.cmb_default_bottom_tab)
        root.addWidget(general_group)

        info_group = QGroupBox("当前状态")
        info_form = QFormLayout(info_group)
        info_form.setContentsMargins(12, 12, 12, 12)
        info_form.setSpacing(8)
        info_form.addRow("当前主题：", QLabel(current_theme_label))
        info_form.addRow("当前模式：", QLabel("前端开发模式优先"))
        root.addWidget(info_group)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def get_preferences(self) -> dict:
        return {
            "auto_switch_output_tab": self.chk_auto_switch_output.isChecked(),
            "clear_output_before_build": self.chk_clear_output_before_build.isChecked(),
            "clear_terminal_before_run": self.chk_clear_terminal_before_run.isChecked(),
            "auto_open_logs_on_terminal_error": self.chk_auto_open_logs_on_terminal_error.isChecked(),
            "default_bottom_tab": int(self.cmb_default_bottom_tab.currentData()),
        }


class ThemeDialog(QDialog):
    _THEME_DESCRIPTIONS = {
        "dark": "深色界面，延续当前项目的主色和对比度风格。",
        "light": "浅色界面，适合白天或长时间阅读。",
    }

    def __init__(self, current_theme: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme")
        self.setModal(True)
        self.resize(520, 260)

        self._theme_buttons: dict[str, QRadioButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("选择界面主题")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        hint = QLabel("主题会立即应用到主窗口，并保存为下次启动的默认主题。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8;")
        root.addWidget(hint)

        for theme_name, desc in self._THEME_DESCRIPTIONS.items():
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            radio = QRadioButton("深色主题" if theme_name == "dark" else "浅色主题")
            radio.setChecked(theme_name == current_theme)
            self._theme_buttons[theme_name] = radio

            label = QLabel(desc)
            label.setWordWrap(True)
            label.setStyleSheet("color:#94a3b8;")

            row.addWidget(radio)
            row.addWidget(label, 1)
            root.addLayout(row)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addStretch(1)
        root.addWidget(btns)

    def selected_theme(self) -> str:
        for theme_name, btn in self._theme_buttons.items():
            if btn.isChecked():
                return theme_name
        return "dark"


class ShortcutsDialog(QDialog):
    def __init__(self, shortcuts: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shortcuts")
        self.setModal(True)
        self.resize(720, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        hint = QLabel("以下快捷键已经在主窗口中生效。若焦点在文本输入框内，编辑类快捷键优先交给输入控件自身处理。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8;")
        root.addWidget(hint)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["操作", "快捷键", "说明"])
        table.setRowCount(len(shortcuts))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        for row, item in enumerate(shortcuts):
            table.setItem(row, 0, QTableWidgetItem(item.get("action", "")))
            table.setItem(row, 1, QTableWidgetItem(item.get("shortcut", "")))
            table.setItem(row, 2, QTableWidgetItem(item.get("description", "")))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        btns.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        root.addWidget(btns)
