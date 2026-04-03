# widgets/explorer_dock.py
from __future__ import annotations

from typing import Any
import copy
import json
import re
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QAction, QColor, QBrush, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTreeWidget, QTreeWidgetItem,
    QPushButton, QDialog, QFormLayout, QLineEdit, QTextEdit,
    QDialogButtonBox, QMessageBox, QToolTip, QLabel, QMenu,
    QCheckBox, QComboBox, QGroupBox, QTableWidget, QTableWidgetItem
)
from .module_dialog import ModuleDialog
from .harness_dialog import HarnessDialog

# =========================
# Config Dialog
# =========================
class ConfigDialog(QDialog):
    """新增/编辑配置项对话框：配置名 + 注释 + 表达式"""
    def __init__(self, title: str, name: str = "", comment: str = "", expr: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 320)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：sys_v1.config")
        self.name_edit.setText(name)

        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("该配置项的注释信息（用于悬浮提示）")
        self.comment_edit.setFixedHeight(90)
        self.comment_edit.setText(comment)

        self.expr_edit = QTextEdit()
        self.expr_edit.setPlaceholderText("填写表达式（字符串）")
        self.expr_edit.setFixedHeight(110)
        self.expr_edit.setText(expr)

        form.addRow("配置名：", self.name_edit)
        form.addRow("注释：", self.comment_edit)
        form.addRow("表达式：", self.expr_edit)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


    def get_data(self) -> tuple[str, str, str]:
        return (
            self.name_edit.text().strip(),
            self.comment_edit.toPlainText().strip(),
            self.expr_edit.toPlainText().strip(),
        )


class RenameDialog(QDialog):
    """仅修改名称"""
    def __init__(self, title: str, name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(420, 120)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        self.name_edit.selectAll()

        form.addRow("新名称：", self.name_edit)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_name(self) -> str:
        return self.name_edit.text().strip()


class CommentEditDialog(QDialog):
    """仅修改注释"""
    def __init__(self, title: str, comment: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("输入注释（留空表示清空注释）")
        self.comment_edit.setText(comment or "")
        self.comment_edit.setFixedHeight(120)

        form.addRow("注释：", self.comment_edit)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_comment(self) -> str:
        return self.comment_edit.toPlainText().strip()


class ConfigRefDialog(QDialog):
    """
    展示 configlib.listref 的结果（正向引用 + 反向引用）。
    forward/reverse 数据结构：{
        "names": [...],
        "childs": [...],
        "values": [...],
        "realvalues": [...]
    }
    """
    def __init__(self, cfg_name: str, forward: dict, reverse: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"配置项引用关系 - {cfg_name}")
        self.setModal(True)
        self.resize(860, 520)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        tabs.addTab(self._make_table(forward, mode="引用（依赖）"), "引用（依赖）")
        tabs.addTab(self._make_table(reverse, mode="反向引用（被依赖）"), "反向引用（被依赖）")

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

    def _make_table(self, data: dict, mode: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        table = QTableWidget()
        lay.addWidget(table)

        names = data.get("names", []) or []
        kinds = data.get("kinds", []) or []
        childs = data.get("childs", []) or []
        values = data.get("values", []) or []
        realvalues = data.get("realvalues", []) or []

        row_count = len(names)
        table.setRowCount(row_count)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["名称", "类型", "关联项(childs)", "表达式/说明", "实值(realvalue)"])

        for i in range(row_count):
            n = names[i] if i < len(names) else ""
            k = kinds[i] if i < len(kinds) else "配置"
            c = childs[i] if i < len(childs) else ""
            v = values[i] if i < len(values) else ""
            rv = realvalues[i] if i < len(realvalues) else ""

            table.setItem(i, 0, QTableWidgetItem(str(n)))
            table.setItem(i, 1, QTableWidgetItem(str(k)))
            table.setItem(i, 2, QTableWidgetItem(str(c)))
            table.setItem(i, 3, QTableWidgetItem(str(v)))
            table.setItem(i, 4, QTableWidgetItem(str(rv)))

        table.resizeColumnsToContents()
        table.setWordWrap(True)
        table.setSortingEnabled(False)

        if row_count == 0:
            hint = QLabel(f"{mode}：无数据")
            hint.setStyleSheet("color:#666;")
            lay.addWidget(hint)

        return w


class DebugPointDialog(QDialog):
    """新增/编辑调试检查点信息。"""

    def __init__(self, title: str, data: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(560, 320)

        payload = copy.deepcopy(data or {})

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：cpu_pc_trace")
        self.name_edit.setText(str(payload.get("name", "") or ""))

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("波形观察", "wave")
        self.kind_combo.addItem("条件检查", "assert")
        self.kind_combo.addItem("文本跟踪", "trace")
        kind_value = str(payload.get("kind", "wave") or "wave")
        idx = max(0, self.kind_combo.findData(kind_value))
        self.kind_combo.setCurrentIndex(idx)

        self.expr_edit = QLineEdit()
        self.expr_edit.setPlaceholderText("例如：CPU_Cluster_A.pc / top.u_core.state")
        self.expr_edit.setText(str(payload.get("expr", "") or ""))

        self.trigger_edit = QLineEdit()
        self.trigger_edit.setPlaceholderText("例如：posedge(clk) / always / cycle % 16 == 0")
        self.trigger_edit.setText(str(payload.get("trigger", "") or ""))

        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("调试检查点说明")
        self.comment_edit.setFixedHeight(110)
        self.comment_edit.setText(str(payload.get("comment", "") or ""))

        form.addRow("检查点名：", self.name_edit)
        form.addRow("类型：", self.kind_combo)
        form.addRow("观察表达式：", self.expr_edit)
        form.addRow("触发条件：", self.trigger_edit)
        form.addRow("注释：", self.comment_edit)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "kind": self.kind_combo.currentData() or "wave",
            "expr": self.expr_edit.text().strip(),
            "trigger": self.trigger_edit.text().strip(),
            "comment": self.comment_edit.toPlainText().strip(),
        }


# =========================
# Explorer Dock
# =========================
class ExplorerDock(QWidget):
    """
    - 配置 / 线束：
      - 标题与 +/− 同行
      - 双击：打开详情页（发信号给 MainWindow）
      - 右键：打开 / 编辑
      - 删除模式：复选框多选 + 删除/取消；同时禁用 +/−
      - 悬停：显示注释
    """
    openConfigRequested = pyqtSignal(str, dict)    # (config_name, config_data)
    openHarnessRequested = pyqtSignal(str, dict)   # (harness_name, harness_data)
    openModuleRequested = pyqtSignal(str, dict)  # (module_name, module_data)

    # 信号 请求添加配置 (name, value/expr, comment)
    addConfigRequested = pyqtSignal(str, str, str)
    # 信号 请求删除配置（names）
    removeConfigRequested = pyqtSignal(list)
    # 信号 防止重复点击，临时禁用删除按钮
    removeConfigResult = pyqtSignal(list, list)  # success_names, failed_items[(name,msg)]

    # 配置项更新
    updateConfigRequested = pyqtSignal(str, str)          # (name, value)
    # / 注释
    commentConfigRequested = pyqtSignal(str, str)         # (name, comment)
    # / 重命名
    renameConfigRequested = pyqtSignal(str, str, str, str)  # (old_name, new_name, old_value, old_comment)
    # / 引用查询
    listRefRequested = pyqtSignal(str)                    # (name)

    # 回传：listref 结果
    listRefResult = pyqtSignal(str, dict, dict, str)      # (name, forward_dict, reverse_dict, err_msg)

    # 线束
    ## 添加操作
    addHarnessRequested = pyqtSignal(str, str, str, dict)
    updateHarnessRequested = pyqtSignal(str, str, str, str, dict)
    removeHarnessRequested = pyqtSignal(list)
    addDebugRequested = pyqtSignal(dict)
    updateDebugRequested = pyqtSignal(str, dict)
    removeDebugRequested = pyqtSignal(list)
    moduleLibraryChanged = pyqtSignal(object)
    mainModuleChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("浏览")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 独立删除模式，避免配置/线束互相干扰
        self._cfg_delete_mode = False
        self._harness_delete_mode = False
        self._module_delete_mode = False
        self._debug_delete_mode = False
        self._harnesses: dict[str, dict] = {}
        self._harness_view_mode = "flat"
        self._module_view_mode = "tree"
        self._main_module_name = ""
        self._main_module_manual = False
        self._debug_points: dict[str, dict] = {}

        # =========================
        # Tab 1: 全局配置
        # =========================
        cfg_tab = QWidget()
        cfg_layout = QVBoxLayout(cfg_tab)
        cfg_layout.setContentsMargins(0, 0, 0, 0)
        cfg_layout.setSpacing(8)

        cfg_header = QHBoxLayout()
        cfg_header.setContentsMargins(0, 0, 0, 0)
        cfg_header.setSpacing(6)

        self.cfg_title = QLabel("全局配置库列表")
        cfg_header.addWidget(self.cfg_title, 0, Qt.AlignmentFlag.AlignVCenter)

        cfg_header.addStretch(1)

        self.btn_add_cfg = QPushButton("+")
        self.btn_add_cfg.setFixedSize(26, 26)
        self.btn_add_cfg.setToolTip("新增配置项")
        self.btn_add_cfg.setObjectName("miniIcon")

        self.btn_del_cfg_mode = QPushButton("−")
        self.btn_del_cfg_mode.setFixedSize(26, 26)
        self.btn_del_cfg_mode.setToolTip("进入删除模式（复选框多选）")
        self.btn_del_cfg_mode.setObjectName("miniIcon")

        cfg_header.addWidget(self.btn_add_cfg, 0, Qt.AlignmentFlag.AlignRight)
        cfg_header.addWidget(self.btn_del_cfg_mode, 0, Qt.AlignmentFlag.AlignRight)
        cfg_layout.addLayout(cfg_header)

        self.global_cfg = QTreeWidget()
        self.global_cfg.setHeaderHidden(True)
        self.global_cfg.setRootIsDecorated(False)
        self.global_cfg.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        self.global_cfg.setMouseTracking(True)
        self.global_cfg.viewport().setMouseTracking(True)
        self.global_cfg.itemEntered.connect(self._on_cfg_item_hover)

        self.global_cfg.itemDoubleClicked.connect(self._on_cfg_item_double_clicked)
        self.global_cfg.itemClicked.connect(self._on_cfg_item_clicked)

        self.global_cfg.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.global_cfg.customContextMenuRequested.connect(self._on_cfg_context_menu)

        cfg_layout.addWidget(self.global_cfg, 1)

        self.cfg_action_bar = QWidget()
        cfg_bar = QHBoxLayout(self.cfg_action_bar)
        cfg_bar.setContentsMargins(0, 0, 0, 0)
        cfg_bar.setSpacing(8)

        self.btn_cfg_delete_checked = QPushButton("删除")
        self.btn_cfg_cancel_delete = QPushButton("取消")
        cfg_bar.addStretch(1)
        cfg_bar.addWidget(self.btn_cfg_delete_checked)
        cfg_bar.addWidget(self.btn_cfg_cancel_delete)

        self.cfg_action_bar.setVisible(False)
        cfg_layout.addWidget(self.cfg_action_bar)

        self.tabs.addTab(cfg_tab, "全局配置")

        # =========================
        # Tab 2: 全局线束
        # =========================
        harness_tab = QWidget()
        harness_layout = QVBoxLayout(harness_tab)
        harness_layout.setContentsMargins(0, 0, 0, 0)
        harness_layout.setSpacing(8)

        harness_header = QHBoxLayout()
        harness_header.setContentsMargins(0, 0, 0, 0)
        harness_header.setSpacing(6)

        self.harness_title = QLabel("全局线束库列表")
        harness_header.addWidget(self.harness_title, 0, Qt.AlignmentFlag.AlignVCenter)

        self.cmb_harness_view = QComboBox()
        self.cmb_harness_view.addItem("平铺模式", "flat")
        self.cmb_harness_view.addItem("树模式", "tree")
        self.cmb_harness_view.setCurrentIndex(0)
        self.cmb_harness_view.setToolTip("切换全局线束的显示模式")
        harness_header.addWidget(self.cmb_harness_view, 0, Qt.AlignmentFlag.AlignVCenter)

        harness_header.addStretch(1)

        self.btn_add_harness = QPushButton("+")
        self.btn_add_harness.setFixedSize(26, 26)
        self.btn_add_harness.setToolTip("新增线束")
        self.btn_add_harness.setObjectName("miniIcon")

        self.btn_del_harness_mode = QPushButton("−")
        self.btn_del_harness_mode.setFixedSize(26, 26)
        self.btn_del_harness_mode.setToolTip("进入删除模式（复选框多选）")
        self.btn_del_harness_mode.setObjectName("miniIcon")

        harness_header.addWidget(self.btn_add_harness, 0, Qt.AlignmentFlag.AlignRight)
        harness_header.addWidget(self.btn_del_harness_mode, 0, Qt.AlignmentFlag.AlignRight)
        harness_layout.addLayout(harness_header)

        self.global_harness = QTreeWidget()
        self.global_harness.setHeaderHidden(True)
        self.global_harness.setRootIsDecorated(False)
        self.global_harness.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        self.global_harness.setMouseTracking(True)
        self.global_harness.viewport().setMouseTracking(True)
        self.global_harness.itemEntered.connect(self._on_harness_item_hover)

        self.global_harness.itemDoubleClicked.connect(self._on_harness_item_double_clicked)
        self.global_harness.itemClicked.connect(self._on_harness_item_clicked)

        self.global_harness.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.global_harness.customContextMenuRequested.connect(self._on_harness_context_menu)

        harness_layout.addWidget(self.global_harness, 1)

        self.harness_action_bar = QWidget()
        hb = QHBoxLayout(self.harness_action_bar)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(8)

        self.btn_harness_delete_checked = QPushButton("删除")
        self.btn_harness_cancel_delete = QPushButton("取消")
        hb.addStretch(1)
        hb.addWidget(self.btn_harness_delete_checked)
        hb.addWidget(self.btn_harness_cancel_delete)

        self.harness_action_bar.setVisible(False)
        harness_layout.addWidget(self.harness_action_bar)

        self.tabs.addTab(harness_tab, "全局线束")

        # =========================
        # Tab 3: 全局模块（保持你的示例）
        # =========================
        # self.modules = QTreeWidget()
        # self.modules.setHeaderLabels(["全局模块库列表"])
        # self.tabs.addTab(self.modules, "全局模块")
        #
        # root = QTreeWidgetItem(["Core_Logic"])
        # root.addChild(QTreeWidgetItem(["CPU_Cluster_A"]))
        # root.addChild(QTreeWidgetItem(["Memory_Bus_64"]))
        # self.modules.addTopLevelItem(root)
        # self.modules.expandAll()

        # =========================
        # Tab 3: 全局模块（同配置/线束风格）
        # =========================

        # 全局模块库（模块名 -> module_data）
        self._modules: dict[str, dict] = {}

        module_tab = QWidget()
        module_layout = QVBoxLayout(module_tab)
        module_layout.setContentsMargins(0, 0, 0, 0)
        module_layout.setSpacing(8)

        module_header = QHBoxLayout()
        module_header.setContentsMargins(0, 0, 0, 0)
        module_header.setSpacing(6)

        self.module_title = QLabel("全局模块库列表")
        module_header.addWidget(self.module_title, 0, Qt.AlignmentFlag.AlignVCenter)

        self.cmb_module_view = QComboBox()
        self.cmb_module_view.addItem("平铺模式", "flat")
        self.cmb_module_view.addItem("树模式", "tree")
        self.cmb_module_view.setCurrentText("树模式")
        self.cmb_module_view.setToolTip("切换全局模块的显示模式")
        module_header.addWidget(self.cmb_module_view, 0, Qt.AlignmentFlag.AlignVCenter)
        module_header.addStretch(1)

        self.btn_add_module = QPushButton("+")
        self.btn_add_module.setFixedSize(26, 26)
        self.btn_add_module.setToolTip("新增模块")
        self.btn_add_module.setObjectName("miniIcon")

        self.btn_del_module = QPushButton("−")
        self.btn_del_module.setFixedSize(26, 26)
        self.btn_del_module.setToolTip("进入删除模式（复选框多选）")
        self.btn_del_module.setObjectName("miniIcon")

        module_header.addWidget(self.btn_add_module, 0, Qt.AlignmentFlag.AlignRight)
        module_header.addWidget(self.btn_del_module, 0, Qt.AlignmentFlag.AlignRight)

        module_layout.addLayout(module_header)

        self.global_modules = QTreeWidget()
        self.global_modules.setHeaderHidden(True)
        self.global_modules.setRootIsDecorated(True)
        self.global_modules.setItemsExpandable(True)
        self.global_modules.setExpandsOnDoubleClick(True)
        # self.global_modules.setRootIsDecorated(False)
        self.global_modules.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        self.global_modules.setMouseTracking(True)
        self.global_modules.viewport().setMouseTracking(True)
        self.global_modules.itemEntered.connect(self._on_module_item_hover)

        self.global_modules.itemDoubleClicked.connect(self._on_module_item_double_clicked)
        self.global_modules.itemClicked.connect(self._on_module_item_clicked)

        self.global_modules.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.global_modules.customContextMenuRequested.connect(self._on_module_context_menu)

        module_layout.addWidget(self.global_modules, 1)

        self.module_action_bar = QWidget()
        mbar = QHBoxLayout(self.module_action_bar)
        mbar.setContentsMargins(0, 0, 0, 0)
        mbar.setSpacing(8)

        self.btn_delete_checked_module = QPushButton("删除")
        self.btn_cancel_delete_module = QPushButton("取消")
        mbar.addStretch(1)
        mbar.addWidget(self.btn_delete_checked_module)
        mbar.addWidget(self.btn_cancel_delete_module)

        self.module_action_bar.setVisible(False)
        module_layout.addWidget(self.module_action_bar)

        self.tabs.addTab(module_tab, "全局模块")

        # =========================
        # Tab 4: 调试信息
        # =========================
        debug_tab = QWidget()
        debug_layout = QVBoxLayout(debug_tab)
        debug_layout.setContentsMargins(0, 0, 0, 0)
        debug_layout.setSpacing(8)

        debug_header = QHBoxLayout()
        debug_header.setContentsMargins(0, 0, 0, 0)
        debug_header.setSpacing(6)

        self.debug_title = QLabel("调试信息列表")
        debug_header.addWidget(self.debug_title, 0, Qt.AlignmentFlag.AlignVCenter)
        debug_header.addStretch(1)

        self.btn_add_debug = QPushButton("+")
        self.btn_add_debug.setFixedSize(26, 26)
        self.btn_add_debug.setToolTip("新增调试检查点")
        self.btn_add_debug.setObjectName("miniIcon")

        self.btn_del_debug_mode = QPushButton("−")
        self.btn_del_debug_mode.setFixedSize(26, 26)
        self.btn_del_debug_mode.setToolTip("进入删除模式（复选框多选）")
        self.btn_del_debug_mode.setObjectName("miniIcon")

        debug_header.addWidget(self.btn_add_debug, 0, Qt.AlignmentFlag.AlignRight)
        debug_header.addWidget(self.btn_del_debug_mode, 0, Qt.AlignmentFlag.AlignRight)
        debug_layout.addLayout(debug_header)

        self.debug_points = QTreeWidget()
        self.debug_points.setHeaderHidden(True)
        self.debug_points.setRootIsDecorated(False)
        self.debug_points.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.debug_points.setMouseTracking(True)
        self.debug_points.viewport().setMouseTracking(True)
        self.debug_points.itemEntered.connect(self._on_debug_item_hover)
        self.debug_points.itemDoubleClicked.connect(self._on_debug_item_double_clicked)
        self.debug_points.itemClicked.connect(self._on_debug_item_clicked)
        self.debug_points.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.debug_points.customContextMenuRequested.connect(self._on_debug_context_menu)
        debug_layout.addWidget(self.debug_points, 1)

        self.debug_action_bar = QWidget()
        dbar = QHBoxLayout(self.debug_action_bar)
        dbar.setContentsMargins(0, 0, 0, 0)
        dbar.setSpacing(8)

        self.btn_delete_checked_debug = QPushButton("删除")
        self.btn_cancel_delete_debug = QPushButton("取消")
        dbar.addStretch(1)
        dbar.addWidget(self.btn_delete_checked_debug)
        dbar.addWidget(self.btn_cancel_delete_debug)

        self.debug_action_bar.setVisible(False)
        debug_layout.addWidget(self.debug_action_bar)

        self.tabs.addTab(debug_tab, "调试信息")

        # 绑定模块事件
        self.btn_add_module.clicked.connect(self._on_add_module_clicked)
        self.btn_del_module.clicked.connect(self._enter_module_delete_mode)
        self.btn_cancel_delete_module.clicked.connect(self._exit_module_delete_mode)
        self.btn_delete_checked_module.clicked.connect(self._delete_checked_module_items)
        self.btn_add_debug.clicked.connect(self._on_add_debug_clicked)
        self.btn_del_debug_mode.clicked.connect(self._enter_debug_delete_mode)
        self.btn_cancel_delete_debug.clicked.connect(self._exit_debug_delete_mode)
        self.btn_delete_checked_debug.clicked.connect(self._delete_checked_debug_items)

        # =========================
        # 示例数据
        # =========================

        self._add_harness_item("AXI_Lite_Req", {
            "name": "AXI_Lite_Req",
            "comment": "AXI-Lite 请求线束示例",
            "alias": False,
            "members": [
                {"name": "addr", "type": "", "int_len": "ADDR_W", "comment": "地址", "default": "0", "dims": ""},
                {"name": "data", "type": "", "int_len": "DATA_W", "comment": "数据", "default": "0", "dims": ""},
            ],
            "enums": []
        })

        self._add_module_item({
            "name": "Core_Logic",
            "comment": "核心逻辑模块",
            "submodules": [
                {"inst": "CPU_Cluster_A", "module": "CPU", "comment": ""},
                {"inst": "Memory_Bus_64", "module": "Bus64", "comment": ""},
            ],
            "local_cfgs": [], "local_harnesses": [], "rpcs": [], "pipe_ports": [],
            "pipes": [], "storages": [],
        })

        self._add_module_item({
            "name": "CPU",
            "comment": "CPU 子模块",
            "submodules": [],
            "local_cfgs": [], "local_harnesses": [], "rpcs": [], "pipe_ports": [],
            "pipes": [], "storages": [],
        })

        self._add_module_item({
            "name": "Bus64",
            "comment": "总线子模块",
            "submodules": [],
            "local_cfgs": [], "local_harnesses": [], "rpcs": [], "pipe_ports": [],
            "pipes": [], "storages": [],
        })


        # =========================
        # 事件绑定：配置
        # =========================
        self.btn_add_cfg.clicked.connect(self._on_add_cfg_clicked)
        self.btn_del_cfg_mode.clicked.connect(self._enter_cfg_delete_mode)
        self.btn_cfg_cancel_delete.clicked.connect(self._exit_cfg_delete_mode)
        self.btn_cfg_delete_checked.clicked.connect(self._delete_checked_cfg_items)

        # =========================
        # 事件绑定：线束
        # =========================
        self.btn_add_harness.clicked.connect(self._on_add_harness_clicked)
        self.btn_del_harness_mode.clicked.connect(self._enter_harness_delete_mode)
        self.btn_harness_cancel_delete.clicked.connect(self._exit_harness_delete_mode)
        self.btn_harness_delete_checked.clicked.connect(self._delete_checked_harness_items)
        self.cmb_harness_view.currentIndexChanged.connect(self._on_harness_view_mode_changed)

        self.removeConfigResult.connect(self._apply_cfg_remove_result)
        self.listRefResult.connect(self._on_listref_result)
        self.cmb_module_view.currentIndexChanged.connect(self._on_module_view_mode_changed)

    # =========================
    # 调试信息：CRUD + UI
    # =========================
    def _iter_debug_items(self):
        for i in range(self.debug_points.topLevelItemCount()):
            yield self.debug_points.topLevelItem(i)

    def _find_debug_by_name(self, name: str) -> QTreeWidgetItem | None:
        for it in self._iter_debug_items():
            payload = it.data(0, Qt.ItemDataRole.UserRole) or {}
            if (payload.get("name") or it.text(0)).strip() == name:
                return it
        return None

    def _debug_kind_label(self, kind: str) -> str:
        return {
            "wave": "波形观察",
            "assert": "条件检查",
            "trace": "文本跟踪",
        }.get((kind or "").strip(), kind or "波形观察")

    def _debug_tooltip(self, data: dict) -> str:
        lines = [
            f"类型：{self._debug_kind_label(data.get('kind', 'wave'))}",
            f"表达式：{data.get('expr', '') or '（未填写）'}",
            f"触发：{data.get('trigger', '') or '（未填写）'}",
            "",
            f"注释：{data.get('comment', '') or '（无注释）'}",
        ]
        return "\n".join(lines)

    def _make_debug_item(self, data: dict) -> QTreeWidgetItem:
        payload = copy.deepcopy(data)
        name = (payload.get("name") or "").strip()
        expr = (payload.get("expr") or "").strip()
        text = name or "未命名检查点"
        if expr:
            text = f"{text}  [{expr}]"
        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, payload)
        item.setToolTip(0, self._debug_tooltip(payload))
        self._set_item_checkable(item, enabled=False)
        return item

    def clear_debug_points(self):
        if self._debug_delete_mode:
            self._exit_debug_delete_mode()
        self._debug_points.clear()
        self.debug_points.clear()

    def get_debug_snapshot(self) -> list[dict]:
        return [copy.deepcopy(self._debug_points[name]) for name in sorted(self._debug_points.keys(), key=str.lower)]

    def update_debug_list(self, debug_data_list: list[dict]):
        if self._debug_delete_mode:
            self._exit_debug_delete_mode()
        self.debug_points.blockSignals(True)
        try:
            self._debug_points.clear()
            self.debug_points.clear()
            for row in debug_data_list or []:
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                payload = {
                    "name": name,
                    "kind": str(row.get("kind", "wave") or "wave"),
                    "expr": str(row.get("expr", "") or ""),
                    "trigger": str(row.get("trigger", "") or ""),
                    "comment": str(row.get("comment", "") or ""),
                }
                self._debug_points[name] = payload
                self.debug_points.addTopLevelItem(self._make_debug_item(payload))
            self.debug_points.sortItems(0, Qt.SortOrder.AscendingOrder)
        finally:
            self.debug_points.blockSignals(False)

    def _show_debug_preview(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        lines = [
            f"名称：{data.get('name', '') or '（未命名）'}",
            f"类型：{self._debug_kind_label(data.get('kind', 'wave'))}",
            f"表达式：{data.get('expr', '') or '（未填写）'}",
            f"触发：{data.get('trigger', '') or '（未填写）'}",
            "",
            f"注释：{data.get('comment', '') or '（无注释）'}",
        ]
        QMessageBox.information(self, "调试检查点信息", "\n".join(lines))

    def _on_add_debug_clicked(self):
        if self._debug_delete_mode:
            return
        dlg = DebugPointDialog("新增调试检查点", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        name = data.get("name", "")
        if not name:
            QMessageBox.warning(self, "输入无效", "检查点名称不能为空。")
            return
        if name in self._debug_points:
            QMessageBox.warning(self, "重复项", f"调试检查点“{name}”已存在。")
            return
        self.addDebugRequested.emit(data)

    def _edit_debug_item(self, item: QTreeWidgetItem):
        if self._debug_delete_mode:
            return
        data = copy.deepcopy(item.data(0, Qt.ItemDataRole.UserRole) or {})
        old_name = (data.get("name") or "").strip()
        dlg = DebugPointDialog("编辑调试检查点", data=data, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_data = dlg.get_data()
        new_name = new_data.get("name", "")
        if not new_name:
            QMessageBox.warning(self, "输入无效", "检查点名称不能为空。")
            return
        if new_name != old_name and new_name in self._debug_points:
            QMessageBox.warning(self, "重复项", f"调试检查点“{new_name}”已存在。")
            return
        self.updateDebugRequested.emit(old_name, new_data)

    def _on_debug_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        self._edit_debug_item(item)

    def _on_debug_item_hover(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        QToolTip.showText(QCursor.pos(), self._debug_tooltip(data), self.debug_points)

    def _on_debug_item_clicked(self, item: QTreeWidgetItem, column: int):
        if not self._debug_delete_mode:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        want_checked = (item.checkState(0) != Qt.CheckState.Checked)
        for it in self._iter_debug_items():
            it.setCheckState(0, Qt.CheckState.Unchecked)
        item.setCheckState(0, Qt.CheckState.Checked if want_checked else Qt.CheckState.Unchecked)

    def _on_debug_context_menu(self, pos):
        item = self.debug_points.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_preview = QAction("预览", self)
        act_edit = QAction("编辑", self)
        act_preview.setEnabled(not self._debug_delete_mode)
        act_edit.setEnabled(not self._debug_delete_mode)
        act_preview.triggered.connect(lambda: self._show_debug_preview(item))
        act_edit.triggered.connect(lambda: self._edit_debug_item(item))
        menu.addAction(act_preview)
        menu.addAction(act_edit)
        menu.exec(self.debug_points.viewport().mapToGlobal(pos))

    def _enter_debug_delete_mode(self):
        if self._debug_delete_mode:
            return
        self._debug_delete_mode = True
        self.btn_add_debug.setEnabled(False)
        self.btn_del_debug_mode.setEnabled(False)
        self.debug_action_bar.setVisible(True)
        self.debug_points.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        for it in self._iter_debug_items():
            self._set_item_checkable(it, enabled=True)

    def _exit_debug_delete_mode(self):
        if not self._debug_delete_mode:
            return
        self._debug_delete_mode = False
        self.btn_add_debug.setEnabled(True)
        self.btn_del_debug_mode.setEnabled(True)
        self.debug_action_bar.setVisible(False)
        self.debug_points.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        for it in self._iter_debug_items():
            self._set_item_checkable(it, enabled=False)
        QToolTip.hideText()

    def _delete_checked_debug_items(self):
        if not self._debug_delete_mode:
            return
        checked = [it for it in self._iter_debug_items() if it.checkState(0) == Qt.CheckState.Checked]
        if not checked:
            QMessageBox.information(self, "未选择", "请勾选要删除的调试检查点。")
            return

        names = sorted({(it.data(0, Qt.ItemDataRole.UserRole) or {}).get("name", "").strip() for it in checked if (it.data(0, Qt.ItemDataRole.UserRole) or {}).get("name", "").strip()})
        if not names:
            QMessageBox.warning(self, "删除失败", "选中的调试检查点名称无效。")
            return

        confirm = QMessageBox.question(
            self,
            "确认删除",
            "将删除以下调试检查点：\n\n" + "\n".join(names) + "\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.removeDebugRequested.emit(names)

    def _parse_dims(self, dims_value) -> list:
        """
        dims 可能来自 dialog 的不同形态：
        - [] / [1,2]
        - "" / None
        - "4,8" / "4 8"
        - "[4, 8]"
        这里尽量转成 list；纯数字转 int，否则保留字符串（兼容表达式）。
        """
        if dims_value is None:
            return []
        if isinstance(dims_value, list):
            out = []
            for x in dims_value:
                if isinstance(x, int):
                    out.append(x)
                else:
                    s = str(x).strip()
                    if s == "":
                        continue
                    out.append(int(s) if re.fullmatch(r"\d+", s) else s)
            return out

        s = str(dims_value).strip()
        if not s:
            return []
        # 去掉外层括号
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1].strip()
        if not s:
            return []
        # 逗号/空白分隔
        parts = [p.strip() for p in re.split(r"[,\s]+", s) if p.strip()]
        out = []
        for p in parts:
            out.append(int(p) if re.fullmatch(r"\d+", p) else p)
        return out

    def _build_vul_bundle_definition(self, harness_data: dict) -> str:
        """
        将 HarnessDialog 返回的 data 转为 VulBundleItem JSON 字符串：
        {
          "members": [...],
          "enum_members": [...],
          "is_alias": true/false
        }
        """
        is_alias = bool(harness_data.get("alias", False))

        members_in = harness_data.get("members") or []
        enums_in = harness_data.get("enums") or []

        # 三种合法形态约束（先在前端拦一下，避免后端 EOPBundAddDefinitionInvalid）
        if is_alias:
            if len(members_in) != 1:
                raise ValueError("别名(bundle alias)要求 members 仅包含 1 项。")
            if enums_in:
                raise ValueError("别名(bundle alias)不允许 enum_members 非空。")
        else:
            if enums_in and members_in:
                raise ValueError("枚举(bundle enum)要求 members 为空；结构体(bundle struct)要求 enum_members 为空。")
            if (not enums_in) and (not members_in):
                raise ValueError("非别名 bundle 必须是：枚举(enum_members非空) 或 结构体(members非空)。")

        members_out = []
        for m in members_in:
            m_name = (m.get("name") or "").strip()
            if not m_name:
                raise ValueError("members 中存在空的成员名称。")

            m_type = (m.get("type") or "").strip()
            uint_len = (m.get("int_len") or "").strip()  # 你示例里叫 int_len
            default_val = (m.get("default") or "").strip()

            # VulBundleItem 规则：命名类型 => uint_length 为空字符串；无符号整数 => type 为空、uint_length 非空
            if m_type:
                uint_length = ""
            else:
                if not uint_len:
                    raise ValueError(f"成员 {m_name} 的 type 为空时，uint_length(int_len) 不能为空。")
                uint_length = uint_len

            dims = self._parse_dims(m.get("dims", ""))

            members_out.append({
                "name": m_name,
                "comment": (m.get("comment") or ""),
                "type": m_type,  # 命名类型：基础类型或其他 bundle 名
                "value": default_val,  # 默认值（字符串）
                "uint_length": uint_length,  # 无符号整数位宽表达式字符串
                "dims": dims,  # 维度数组
            })

        enums_out = []
        for e in enums_in:
            e_name = (e.get("name") or "").strip()
            if not e_name:
                raise ValueError("enum_members 中存在空的枚举名称。")
            enums_out.append({
                "name": e_name,
                "comment": (e.get("comment") or ""),
                "value": (e.get("value") or ""),
            })

        vul = {
            "members": members_out if (not enums_out) else [],
            "enum_members": enums_out if enums_out else [],
            "is_alias": is_alias,
        }

        return json.dumps(vul, ensure_ascii=False)

    # =========================
    # 通用：checkbox
    # =========================
    def _set_item_checkable(self, item: QTreeWidgetItem, enabled: bool):
        flags = item.flags()
        if enabled:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            flags &= ~Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            item.setData(0, Qt.ItemDataRole.CheckStateRole, None)

    def _lock_cfg_delete_ui(self, locked: bool):
        """
        删除请求发出后锁 UI，防止重复点击/重复发请求
        """
        self.btn_cfg_delete_checked.setEnabled(not locked)
        self.btn_cfg_cancel_delete.setEnabled(not locked)
        self.global_cfg.setEnabled(not locked)

    # =========================
    # 配置：CRUD + UI
    # =========================
    def _iter_cfg_items(self):
        for i in range(self.global_cfg.topLevelItemCount()):
            yield self.global_cfg.topLevelItem(i)

    def _find_cfg_by_name(self, name: str) -> QTreeWidgetItem | None:
        for it in self._iter_cfg_items():
            if it.text(0) == name:
                return it
        return None

    def _add_cfg_item(self, name: str, comment: str, expr: str):
        item = QTreeWidgetItem([name])
        item.setData(0, Qt.ItemDataRole.UserRole, {"name": name, "comment": comment, "expr": expr})
        item.setToolTip(0, comment if comment else "（无注释）")
        self._set_item_checkable(item, enabled=False)
        self.global_cfg.addTopLevelItem(item)

    def _get_cfg_data(self, item: QTreeWidgetItem) -> dict:
        return item.data(0, Qt.ItemDataRole.UserRole) or {
            "name": item.text(0),
            "comment": "",
            "expr": "",
            "realvalue": "",
        }

    def _on_add_cfg_clicked(self):
        if self._cfg_delete_mode:
            return
        dlg = ConfigDialog("新增配置项", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, comment, expr = dlg.get_data()
        if not name:
            QMessageBox.warning(self, "输入无效", "配置名不能为空。")
            return
        
        # 将 expr 作为 value 传递
        self.addConfigRequested.emit(name, expr, comment)


    def _edit_cfg_item(self, item: QTreeWidgetItem):
        if self._cfg_delete_mode:
            return
        data = self._get_cfg_data(item)
        old_name = data.get("name", item.text(0))
        old_comment = data.get("comment", "") or ""
        old_expr = data.get("expr", "") or ""
        dlg = ConfigDialog("编辑配置项", name=old_name, comment=data.get("comment", ""), expr=data.get("expr", ""), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name, new_comment, new_expr = dlg.get_data()
        if not new_name:
            QMessageBox.warning(self, "输入无效", "配置名不能为空。")
            return
        if new_name != old_name and self._find_cfg_by_name(new_name) is not None:
            QMessageBox.warning(self, "重复项", f"配置项“{new_name}”已存在。")
            return

        if new_name != old_name:
            self.renameConfigRequested.emit(old_name, new_name, new_expr, new_comment)
            return

        if new_expr != old_expr:
            self.updateConfigRequested.emit(old_name, new_expr)
        if new_comment != old_comment:
            self.commentConfigRequested.emit(old_name, new_comment)

    def _open_cfg_relation(self, item: QTreeWidgetItem):
        if self._cfg_delete_mode:
            return
        data = self._get_cfg_data(item)
        name = data.get("name", item.text(0))
        self.openConfigRequested.emit(name, data)

    def _on_cfg_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        self._open_cfg_relation(item)

    def _on_cfg_context_menu(self, pos):
        item = self.global_cfg.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_open = QAction("打开", self)
        act_edit = QAction("编辑", self)
        act_rename = QAction("重命名", self)
        act_refs = QAction("查看关联引用", self)
        act_comment = QAction("修改注释", self)

        act_open.setEnabled(not self._cfg_delete_mode)
        act_edit.setEnabled(not self._cfg_delete_mode)
        act_rename.setEnabled(not self._cfg_delete_mode)
        act_refs.setEnabled(not self._cfg_delete_mode)
        act_comment.setEnabled(not self._cfg_delete_mode)

        act_open.triggered.connect(lambda: self._open_cfg_relation(item))
        act_edit.triggered.connect(lambda: self._edit_cfg_item(item))
        act_rename.triggered.connect(lambda: self._rename_cfg_item(item))
        act_refs.triggered.connect(lambda: self._show_cfg_refs(item))
        act_comment.triggered.connect(lambda: self._edit_cfg_comment(item))

        menu.addAction(act_open)
        menu.addAction(act_edit)
        menu.addSeparator()
        menu.addAction(act_rename)
        menu.addAction(act_comment)
        menu.addAction(act_refs)

        menu.exec(self.global_cfg.viewport().mapToGlobal(pos))

    def _rename_cfg_item(self, item: QTreeWidgetItem):
        if self._cfg_delete_mode:
            return
        data = self._get_cfg_data(item)
        old_name = data.get("name", item.text(0))
        old_comment = data.get("comment", "") or ""
        old_expr = data.get("expr", "") or ""

        dlg = RenameDialog("重命名配置项", name=old_name, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = dlg.get_name()
        if not new_name:
            QMessageBox.warning(self, "输入无效", "名称不能为空。")
            return
        if new_name != old_name and self._find_cfg_by_name(new_name) is not None:
            QMessageBox.warning(self, "重复项", f"配置项“{new_name}”已存在。")
            return

        # ✅ 交给后端做：这里采用“add(new)+remove(old)”组合实现重命名（后端无 rename 接口时最稳）
        self.renameConfigRequested.emit(old_name, new_name, old_expr, old_comment)

    def _edit_cfg_comment(self, item: QTreeWidgetItem):
        if self._cfg_delete_mode:
            return
        data = self._get_cfg_data(item)
        name = data.get("name", item.text(0))
        comment = data.get("comment", "") or ""

        dlg = CommentEditDialog("修改注释", comment=comment, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_comment = dlg.get_comment()

        # 交给后端：configlib.comment(name, comment)
        self.commentConfigRequested.emit(name, new_comment)

    def _show_cfg_refs(self, item: QTreeWidgetItem):
        if self._cfg_delete_mode:
            return
        data = self._get_cfg_data(item)
        name = data.get("name", item.text(0))
        # 交给后端：拉取 forward + reverse
        self.listRefRequested.emit(name)

    def _on_listref_result(self, name: str, forward: dict, reverse: dict, err_msg: str):
        if err_msg:
            QMessageBox.warning(self, "查看引用失败", f"配置项：{name}\n\n失败原因：{err_msg}")
            return
        dlg = ConfigRefDialog(name, forward=forward or {}, reverse=reverse or {}, parent=self)
        dlg.exec()

    def _on_cfg_item_hover(self, item: QTreeWidgetItem, column: int):
        data = self._get_cfg_data(item)
        lines = [
            f"表达式：{data.get('expr', '') or '（空）'}",
        ]
        realvalue = data.get("realvalue", "") or ""
        if realvalue:
            lines.append(f"实值：{realvalue}")
        lines.append("")
        lines.append(f"注释：{data.get('comment', '') or '（无注释）'}")
        QToolTip.showText(QCursor.pos(), "\n".join(lines), self.global_cfg)

    # ---- cfg delete mode
    def _enter_cfg_delete_mode(self):
        if self._cfg_delete_mode:
            return
        self._cfg_delete_mode = True
        self.btn_add_cfg.setEnabled(False)
        self.btn_del_cfg_mode.setEnabled(False)

        self.cfg_action_bar.setVisible(True)
        self.global_cfg.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        for it in self._iter_cfg_items():
            self._set_item_checkable(it, enabled=True)

    def _exit_cfg_delete_mode(self):
        if not self._cfg_delete_mode:
            return
        self._cfg_delete_mode = False
        self.btn_add_cfg.setEnabled(True)
        self.btn_del_cfg_mode.setEnabled(True)

        self.cfg_action_bar.setVisible(False)
        self.global_cfg.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        for it in self._iter_cfg_items():
            self._set_item_checkable(it, enabled=False)
        QToolTip.hideText()

    def _on_cfg_item_clicked(self, item: QTreeWidgetItem, column: int):
        if not self._cfg_delete_mode:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return

        # 当前点击想要的目标状态：若已勾选则取消，否则勾选
        want_checked = (item.checkState(0) != Qt.CheckState.Checked)

        # ✅ 单选：先全部取消
        for it in self._iter_cfg_items():
            it.setCheckState(0, Qt.CheckState.Unchecked)

        # 再按需设置当前项
        item.setCheckState(0, Qt.CheckState.Checked if want_checked else Qt.CheckState.Unchecked)

    def _delete_checked_cfg_items(self):
        if not self._cfg_delete_mode:
            return

        checked = [it for it in self._iter_cfg_items() if it.checkState(0) == Qt.CheckState.Checked]
        if not checked:
            QMessageBox.information(self, "未选择", "请勾选要删除的配置项。")
            return

        # ✅ 强制单选（防御：即便未来哪里没控住也只取第一个）
        it = checked[0]
        name = it.text(0)

        confirm = QMessageBox.question(
            self, "确认删除",
            f"将删除配置项：\n\n{name}\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._lock_cfg_delete_ui(True)
        self.removeConfigRequested.emit([name])  # 仍复用 list 信号，长度=1

    def _apply_cfg_remove_result(self, success_names: list[str], failed: list[tuple[str, str]]):
        # 解除锁
        self._lock_cfg_delete_ui(False)

        # 失败：弹窗显示原因；用户点 OK 后退出删除模式
        if failed:
            # 单删场景：只取第一个
            n, msg = failed[0]
            QMessageBox.warning(self, "删除失败", f"配置项：{n}\n\n失败原因：{msg}")
            self._exit_cfg_delete_mode()
            return

        # 成功：从树上移除并退出删除模式
        if success_names:
            name = success_names[0]
            it = self._find_cfg_by_name(name)
            if it is not None:
                idx = self.global_cfg.indexOfTopLevelItem(it)
                if idx >= 0:
                    self.global_cfg.takeTopLevelItem(idx)

        self._exit_cfg_delete_mode()

    # =========================
    # 线束：CRUD + UI
    # =========================
    def _iter_harness_items(self):
        def walk(item: QTreeWidgetItem):
            yield item
            for i in range(item.childCount()):
                yield from walk(item.child(i))

        for i in range(self.global_harness.topLevelItemCount()):
            yield from walk(self.global_harness.topLevelItem(i))

    def _find_harness_by_name(self, name: str) -> QTreeWidgetItem | None:
        for it in self._iter_harness_items():
            data = it.data(0, Qt.ItemDataRole.UserRole) or {}
            if (data.get("name") or it.text(0)).strip() == name:
                return it
        return None

    def _bundle_ref_names(self, harness_data: dict) -> set[str]:
        refs: set[str] = set()
        members = harness_data.get("members") or []
        for member in members:
            target = (member.get("type") or "").strip()
            if target:
                refs.add(target)
        return refs

    def _make_harness_tree_item(self, harness_name: str) -> QTreeWidgetItem:
        payload = copy.deepcopy(self._harnesses.get(harness_name, {}))
        payload.setdefault("name", harness_name)

        item = QTreeWidgetItem([harness_name])
        item.setData(0, Qt.ItemDataRole.UserRole, payload)
        item.setToolTip(0, payload.get("comment", "") or "（无注释）")
        self._set_item_checkable(item, enabled=False)
        return item

    def _refresh_harness_tree(self):
        self.global_harness.blockSignals(True)
        try:
            self.global_harness.clear()
            self.global_harness.setRootIsDecorated(self._harness_view_mode == "tree")

            if not self._harnesses:
                return

            names = sorted(self._harnesses.keys(), key=str.lower)
            if self._harness_view_mode == "flat":
                for name in names:
                    self.global_harness.addTopLevelItem(self._make_harness_tree_item(name))
                return

            refs_map: dict[str, list[str]] = {}
            referenced: set[str] = set()
            for name in names:
                refs = sorted(
                    {ref for ref in self._bundle_ref_names(self._harnesses.get(name, {})) if ref in self._harnesses},
                    key=str.lower,
                )
                refs_map[name] = refs
                referenced.update(refs)

            roots = [name for name in names if name not in referenced]
            if not roots:
                roots = names

            def build_children(parent_item: QTreeWidgetItem, parent_name: str, path: set[str]):
                for child_name in refs_map.get(parent_name, []):
                    child_item = self._make_harness_tree_item(child_name)
                    parent_item.addChild(child_item)
                    if child_name in path:
                        child_item.setToolTip(0, child_item.toolTip(0) + "\n\n[警告] 检测到循环引用，已停止展开。")
                        continue
                    build_children(child_item, child_name, path | {child_name})

            for root_name in roots:
                root_item = self._make_harness_tree_item(root_name)
                self.global_harness.addTopLevelItem(root_item)
                build_children(root_item, root_name, {root_name})

            self.global_harness.expandAll()
        finally:
            self.global_harness.blockSignals(False)

    def _on_harness_view_mode_changed(self, index: int = -1):
        self._harness_view_mode = self.cmb_harness_view.currentData() or "flat"
        self._refresh_harness_tree()

    def _get_harness_data(self, item: QTreeWidgetItem) -> dict:
        return item.data(0, Qt.ItemDataRole.UserRole) or {"name": item.text(0), "comment": "", "alias": False, "members": [], "enums": []}

    def _add_harness_item(self, name: str, data: dict):
        payload = copy.deepcopy(data)
        payload["name"] = name
        self._harnesses[name] = payload
        self._refresh_harness_tree()

    def clear_harnesses(self):
        """清空全局线束树"""
        self._harnesses.clear()
        self.global_harness.clear()

    def get_harness_snapshot(self) -> list[dict]:
        return [copy.deepcopy(self._harnesses[name]) for name in sorted(self._harnesses.keys(), key=str.lower)]

    def _bundle_definition_to_harness_data(self, name: str, comment: str, definition_json: str | None,
                                           tags: str = "") -> dict:
        """
        将后端 VulBundleItem JSON 定义反序列化为你当前 UI 使用的 harness_data 结构：
        {
          "name": ...,
          "comment": ...,
          "alias": bool,
          "members": [{"name","type","int_len","comment","default","dims"}, ...],
          "enums": [{"name","comment","value"}, ...],
          "tags": "..."  # 可选：保留给 UI 未来显示
        }
        """
        data = {
            "name": name,
            "comment": comment or "",
            "alias": False,
            "members": [],
            "enums": [],
            "tags": tags or "",
        }

        if not definition_json:
            return data

        try:
            obj = json.loads(definition_json)
        except Exception:
            # 定义损坏/不是 JSON：不让 UI 崩，直接返回基础信息
            return data

        is_alias = bool(obj.get("is_alias", False))
        data["alias"] = is_alias

        members = obj.get("members", []) or []
        enums = obj.get("enum_members", []) or []
        data["enums"] = [{"name": (e.get("name") or ""),
                          "comment": (e.get("comment") or ""),
                          "value": (e.get("value") or "")} for e in enums]

        # 你 UI member 的字段名：type / int_len / default / dims
        ui_members = []
        for m in members:
            m_name = (m.get("name") or "")
            m_comment = (m.get("comment") or "")
            m_type = (m.get("type") or "")
            m_value = (m.get("value") or "")
            uint_length = (m.get("uint_length") or "")  # 后端字段
            dims = m.get("dims", []) or []

            # dims UI 里你示例用 "" 或 list，都能兼容；这里统一转成 list 更好
            ui_members.append({
                "name": m_name,
                "type": m_type,
                "int_len": uint_length,  # 注意：你 add 时把 UI 的 int_len 写到 uint_length
                "comment": m_comment,
                "default": m_value,
                "dims": dims,
            })

        data["members"] = ui_members
        return data

    def update_harness_list(self, bundle_data_list: list[dict]):
        """
        bundle_data_list 元素结构建议：
        {
          "name": str,
          "comment": str,
          "tags": str,
          "definition": str | None,   # 可选
          "references": str,          # 可选
          "config_references": str,   # 可选
          "reverse_references": str,  # 可选
        }
        """
        self.global_harness.blockSignals(True)
        try:
            self._harnesses.clear()
            self.global_harness.clear()

            for b in bundle_data_list:
                name = (b.get("name") or "").strip()
                if not name:
                    continue

                comment = b.get("comment", "") or ""
                tags = b.get("tags", "") or ""
                definition = b.get("definition", "") or ""

                harness_data = self._bundle_definition_to_harness_data(
                    name=name,
                    comment=comment,
                    definition_json=definition,
                    tags=tags,
                )
                self._harnesses[name] = harness_data
        finally:
            self.global_harness.blockSignals(False)
        self._refresh_harness_tree()

    def apply_harness_update(self, old_name: str, data: dict) -> bool:
        old_item = self._harnesses.get(old_name)
        if old_item is None:
            return False

        new_name = (data.get("name") or old_name).strip() or old_name
        payload = copy.deepcopy(old_item)
        payload.update(copy.deepcopy(data))
        payload["name"] = new_name
        self._harnesses.pop(old_name, None)
        self._harnesses[new_name] = payload
        self._refresh_harness_tree()
        return True

    def remove_harness_names(self, names: list[str]) -> list[str]:
        removed: list[str] = []
        for name in names or []:
            if name in self._harnesses:
                self._harnesses.pop(name, None)
                removed.append(name)
        if removed:
            self._refresh_harness_tree()
        return removed

    def _on_add_harness_clicked(self):
        if self._harness_delete_mode:
            return
        dlg = HarnessDialog("新增线束", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        name = (data.get("name") or "").strip()
        comment = (data.get("comment") or "").strip()

        if not name:
            QMessageBox.warning(self, "输入无效", "线束名不能为空。")
            return
        if name in self._harnesses:
            QMessageBox.warning(self, "重复项", f"线束“{name}”已存在。")
            return

        try:
            definition_json = self._build_vul_bundle_definition(data)
        except Exception as e:
            QMessageBox.warning(self, "定义无效", f"线束定义不合法：\n{e}")
            return

        # 交给 MainWindow 调后端 bundlelib.add
        self.addHarnessRequested.emit(name, comment, definition_json, data)

    def _edit_harness_item(self, item: QTreeWidgetItem):
        if self._harness_delete_mode:
            return
        old = self._get_harness_data(item)
        dlg = HarnessDialog("编辑线束", harness_data=old, parent=self)
        # 编辑时线束名是唯一索引：通常允许改名，但要做查重；若你希望禁止改名，可直接 setEnabled(False)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_data = dlg.get_data()
        new_name = new_data.get("name", "")
        if not new_name:
            QMessageBox.warning(self, "输入无效", "线束名不能为空。")
            return
        if new_name != old.get("name") and new_name in self._harnesses:
            QMessageBox.warning(self, "重复项", f"线束“{new_name}”已存在。")
            return

        try:
            definition_json = self._build_vul_bundle_definition(new_data)
        except Exception as e:
            QMessageBox.warning(self, "定义无效", f"线束定义不合法：\n{e}")
            return

        self.updateHarnessRequested.emit(
            old.get("name", ""),
            new_name,
            new_data.get("comment", "") or "",
            definition_json,
            new_data,
        )

    def _open_harness_detail(self, item: QTreeWidgetItem):
        if self._harness_delete_mode:
            return
        data = self._get_harness_data(item)
        name = data.get("name", item.text(0))
        self.openHarnessRequested.emit(name, data)

    def _on_harness_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        self._open_harness_detail(item)

    def _on_harness_context_menu(self, pos):
        item = self.global_harness.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_open = QAction("打开", self)
        act_edit = QAction("编辑", self)
        act_open.setEnabled(not self._harness_delete_mode)
        act_edit.setEnabled(not self._harness_delete_mode)
        act_open.triggered.connect(lambda: self._open_harness_detail(item))
        act_edit.triggered.connect(lambda: self._edit_harness_item(item))
        menu.addAction(act_open)
        menu.addAction(act_edit)
        menu.exec(self.global_harness.viewport().mapToGlobal(pos))

    def _on_harness_item_hover(self, item: QTreeWidgetItem, column: int):
        comment = (self._get_harness_data(item).get("comment", "") or "（无注释）")
        QToolTip.showText(QCursor.pos(), comment, self.global_harness)

    # ---- harness delete mode
    def _enter_harness_delete_mode(self):
        if self._harness_delete_mode:
            return
        self._harness_delete_mode = True

        self.btn_add_harness.setEnabled(False)
        self.btn_del_harness_mode.setEnabled(False)
        self.cmb_harness_view.setEnabled(False)

        self.harness_action_bar.setVisible(True)
        self.global_harness.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        for it in self._iter_harness_items():
            self._set_item_checkable(it, enabled=True)

    def _exit_harness_delete_mode(self):
        if not self._harness_delete_mode:
            return
        self._harness_delete_mode = False

        self.btn_add_harness.setEnabled(True)
        self.btn_del_harness_mode.setEnabled(True)
        self.cmb_harness_view.setEnabled(True)

        self.harness_action_bar.setVisible(False)
        self.global_harness.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        for it in self._iter_harness_items():
            self._set_item_checkable(it, enabled=False)
        QToolTip.hideText()

    def _on_harness_item_clicked(self, item: QTreeWidgetItem, column: int):
        if not self._harness_delete_mode:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        cur = item.checkState(0)
        item.setCheckState(0, Qt.CheckState.Unchecked if cur == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def _delete_checked_harness_items(self):
        if not self._harness_delete_mode:
            return
        targets = {
            (self._get_harness_data(it).get("name") or it.text(0)).strip()
            for it in self._iter_harness_items()
            if it.checkState(0) == Qt.CheckState.Checked
        }
        targets.discard("")
        if not targets:
            QMessageBox.information(self, "未选择", "请勾选要删除的线束。")
            return

        names = sorted(targets)
        confirm = QMessageBox.question(
            self, "确认删除",
            "将删除以下线束：\n\n" + "\n".join(names) + "\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.removeHarnessRequested.emit(names)
        self._exit_harness_delete_mode()

    # =========================
    # 全局模块：树形（父子）展示
    # 规则：父模块节点 = 模块定义；子节点由 submodules(模块实例) 构建： "inst -> module"
    # =========================

    def _node_kind(self, item: QTreeWidgetItem) -> str:
        """module_def / submodule_inst"""
        return (item.data(0, Qt.ItemDataRole.UserRole) or {}).get("_kind", "")

    def _node_module_name(self, item: QTreeWidgetItem) -> str:
        """返回该节点对应的“模块定义名”（根节点=自身，实例节点=引用模块）"""
        payload = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if payload.get("_kind") == "submodule_inst":
            return (payload.get("module") or "").strip()
        return (payload.get("name") or item.text(0)).strip()

    def _module_roots(self) -> list[str]:
        referenced: set[str] = set()
        for module_data in self._modules.values():
            for sm in (module_data.get("submodules") or []):
                mod = (sm.get("module") or "").strip()
                if mod:
                    referenced.add(mod)

        roots = [name for name in self._modules.keys() if name not in referenced]
        if not roots:
            roots = list(self._modules.keys())
        return sorted(roots, key=str.lower)

    def _sync_main_module_name(self):
        if self._main_module_manual:
            if self._main_module_name and self._main_module_name in self._modules:
                return
            if not self._main_module_name:
                return
            self._main_module_name = ""
            self._main_module_manual = False

        if self._main_module_name and self._main_module_name in self._modules:
            return

        roots = self._module_roots()
        if len(roots) == 1:
            self._main_module_name = roots[0]
        elif len(self._modules) == 1:
            self._main_module_name = next(iter(self._modules.keys()))
        else:
            self._main_module_name = ""

    def _node_tooltip_for(self, module_name: str, inst_name: str | None = None, parent_name: str | None = None) -> str:
        m = self._modules.get(module_name, {})
        c = (m.get("comment") or "").strip() or "（无注释）"
        main_hint = "\n[主模块]" if module_name == self._main_module_name else ""
        if inst_name:
            return f"实例：{inst_name}\n模块：{module_name}{main_hint}\n父模块：{parent_name or ''}\n\n注释：{c}"
        return f"模块：{module_name}{main_hint}\n\n注释：{c}"

    def _format_module_item_label(self, module_name: str, kind: str, inst_name: str | None = None) -> str:
        is_main = module_name == self._main_module_name
        if kind == "submodule_inst":
            label = f"{inst_name or ''}  →  {module_name}"
            return f"{label}  [主模块]" if is_main else label
        return f"★ {module_name}" if is_main else module_name

    def _apply_module_item_style(self, item: QTreeWidgetItem):
        module_name = self._node_module_name(item)
        kind = self._node_kind(item)
        payload = item.data(0, Qt.ItemDataRole.UserRole) or {}
        inst_name = (payload.get("inst") or "").strip() if kind == "submodule_inst" else None
        item.setText(0, self._format_module_item_label(module_name, kind, inst_name=inst_name))

        font = QFont(item.font(0))
        font.setBold(module_name == self._main_module_name)
        item.setFont(0, font)
        if module_name == self._main_module_name:
            item.setForeground(0, QBrush(QColor("#C77800")))
        else:
            item.setForeground(0, QBrush())

    def _make_module_tree_item(self, module_name: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([module_name])
        item.setData(0, Qt.ItemDataRole.UserRole, {"_kind": "module_def", **copy.deepcopy(self._modules.get(module_name, {}))})
        item.setToolTip(0, self._node_tooltip_for(module_name))
        self._set_item_checkable(item, enabled=False)
        self._apply_module_item_style(item)
        return item

    def _on_module_view_mode_changed(self, index: int = -1):
        self._module_view_mode = self.cmb_module_view.currentData() or "tree"
        self._refresh_module_tree()

    def _set_main_module_name(self, module_name: str):
        self._main_module_manual = True
        self._main_module_name = module_name if module_name in self._modules else ""
        self._refresh_module_tree()
        self.mainModuleChanged.emit(self._main_module_name)

    def set_main_module_name(self, module_name: str, emit_signal: bool = False):
        self._main_module_manual = True
        self._main_module_name = module_name if module_name in self._modules else ""
        self._refresh_module_tree()
        if emit_signal:
            self.mainModuleChanged.emit(self._main_module_name)

    def get_main_module_name(self) -> str:
        return self._main_module_name

    def _iter_all_module_tree_items(self):
        """遍历树上所有节点（含子节点）"""
        def walk(it: QTreeWidgetItem):
            yield it
            for i in range(it.childCount()):
                yield from walk(it.child(i))

        for i in range(self.global_modules.topLevelItemCount()):
            yield from walk(self.global_modules.topLevelItem(i))

    def _find_module_by_name(self, name: str) -> bool:
        return name in self._modules

    def _refresh_module_tree(self):
        """根据 self._modules 的定义，重建树形结构"""
        self.global_modules.blockSignals(True)
        try:
            self.global_modules.clear()
            self.global_modules.setRootIsDecorated(self._module_view_mode == "tree")

            if not self._modules:
                self._main_module_name = ""
                return

            self._sync_main_module_name()

            if self._module_view_mode == "flat":
                for module_name in sorted(self._modules.keys(), key=str.lower):
                    self.global_modules.addTopLevelItem(self._make_module_tree_item(module_name))
                return

            roots = self._module_roots()

            # 递归构树：parent_node 下挂 “实例 -> 子模块”
            def build_children(parent_item: QTreeWidgetItem, parent_module_name: str, path: set[str]):
                parent_data = self._modules.get(parent_module_name, {})
                submods = parent_data.get("submodules") or []
                for sm in submods:
                    inst = (sm.get("inst") or "").strip()
                    child_mod = (sm.get("module") or "").strip()
                    if not inst or not child_mod:
                        continue

                    child_item = QTreeWidgetItem([child_mod])
                    child_item.setData(0, Qt.ItemDataRole.UserRole, {
                        "_kind": "submodule_inst",
                        "inst": inst,
                        "module": child_mod,
                        "parent": parent_module_name,
                    })
                    child_item.setToolTip(0, self._node_tooltip_for(child_mod, inst_name=inst, parent_name=parent_module_name))
                    self._set_item_checkable(child_item, enabled=False)
                    self._apply_module_item_style(child_item)
                    parent_item.addChild(child_item)

                    # 环检测：如果 child_mod 已经在当前路径里，停止深入，避免无限递归
                    if child_mod in path:
                        # 提示一下循环引用
                        child_item.setToolTip(0, child_item.toolTip(0) + "\n\n[警告] 检测到循环引用，已停止展开。")
                        continue

                    # 如果子模块在库中存在，则继续展开它的子实例
                    if child_mod in self._modules:
                        build_children(child_item, child_mod, path | {child_mod})

            # 构建 root 节点
            for root_name in roots:
                root_item = self._make_module_tree_item(root_name)
                self.global_modules.addTopLevelItem(root_item)

                build_children(root_item, root_name, path={root_name})

            self.global_modules.expandAll()
        finally:
            self.global_modules.blockSignals(False)

    def _add_module_item(self, module_data: dict):
        """新增模块定义 -> 写入库 -> 刷新树"""
        name = (module_data.get("name") or "").strip()
        if not name:
            return
        self._modules[name] = copy.deepcopy(module_data)
        self._refresh_module_tree()
        self._emit_module_library_changed()

    def clear_modules(self):
        self._modules.clear()
        self._main_module_name = ""
        self._main_module_manual = False
        self._refresh_module_tree()
        self._emit_module_library_changed()

    def update_module_list(self, modules: dict[str, dict] | list[dict]):
        if isinstance(modules, dict):
            self._modules = copy.deepcopy(modules)
        else:
            self._modules = {}
            for module_data in modules or []:
                name = (module_data.get("name") or "").strip()
                if name:
                    self._modules[name] = copy.deepcopy(module_data)
        if self._main_module_name and self._main_module_name not in self._modules:
            self._main_module_name = ""
            self._main_module_manual = False
        self._refresh_module_tree()
        self._emit_module_library_changed()

    def export_modules(self) -> dict[str, dict]:
        return copy.deepcopy(self._modules)

    def _emit_module_library_changed(self):
        self.moduleLibraryChanged.emit(self.export_modules())

    def _on_add_module_clicked(self):
        if self._module_delete_mode:
            return
        dlg = ModuleDialog("新增模块", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        name = (data.get("name") or "").strip()
        if not name:
            QMessageBox.warning(self, "输入无效", "模块名不能为空。")
            return
        if self._find_module_by_name(name):
            QMessageBox.warning(self, "重复项", f"模块“{name}”已存在。")
            return

        self._add_module_item(data)

    def _edit_module_by_name(self, module_name: str):
        """按模块名编辑模块定义，并支持重命名 + 引用更新"""
        if self._module_delete_mode:
            return
        old = self._modules.get(module_name)
        if not old:
            QMessageBox.warning(self, "不存在", f"模块“{module_name}”不存在或已被删除。")
            return

        old_name = (old.get("name") or module_name).strip()

        dlg = ModuleDialog("编辑模块", module_data=old, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new = dlg.get_data()
        merged = copy.deepcopy(old)
        merged.update(new)
        new = merged
        new_name = (new.get("name") or "").strip()
        if not new_name:
            QMessageBox.warning(self, "输入无效", "模块名不能为空。")
            return
        if new_name != old_name and self._find_module_by_name(new_name):
            QMessageBox.warning(self, "重复项", f"模块“{new_name}”已存在。")
            return

        # 写回：支持改名
        if new_name != old_name:
            # 1) 移动 key
            self._modules.pop(old_name, None)
            self._modules[new_name] = new

            # 2) 更新所有父模块 submodules 引用（module 字段）
            for m in self._modules.values():
                for sm in (m.get("submodules") or []):
                    if (sm.get("module") or "").strip() == old_name:
                        sm["module"] = new_name
            if self._main_module_name == old_name:
                self._main_module_name = new_name
        else:
            self._modules[old_name] = copy.deepcopy(new)

        self._refresh_module_tree()
        self._emit_module_library_changed()

    def _open_module_by_name(self, module_name: str):
        """按模块名打开详情页（发信号给 MainWindow）"""
        if self._module_delete_mode:
            return
        data = self._modules.get(module_name)
        if not data:
            QMessageBox.warning(self, "不存在", f"模块“{module_name}”不存在或已被删除。")
            return
        self.openModuleRequested.emit(module_name, data)

    def _on_module_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        target = self._node_module_name(item)
        if target:
            self._open_module_by_name(target)

    def _on_module_context_menu(self, pos):
        item = self.global_modules.itemAt(pos)
        if item is None:
            return

        target = self._node_module_name(item)
        if not target:
            return

        menu = QMenu(self)

        act_open = QAction("打开", self)
        act_edit = QAction("编辑", self)
        act_set_main = QAction("设为主模块", self)
        act_clear_main = QAction("取消主模块", self)

        act_open.setEnabled(not self._module_delete_mode)
        act_edit.setEnabled(not self._module_delete_mode)
        act_set_main.setEnabled((not self._module_delete_mode) and target != self._main_module_name)
        act_clear_main.setEnabled((not self._module_delete_mode) and target == self._main_module_name)

        act_open.triggered.connect(lambda: self._open_module_by_name(target))
        act_edit.triggered.connect(lambda: self._edit_module_by_name(target))
        act_set_main.triggered.connect(lambda: self._set_main_module_name(target))
        act_clear_main.triggered.connect(lambda: self._set_main_module_name(""))

        menu.addAction(act_open)
        menu.addAction(act_edit)
        menu.addSeparator()
        menu.addAction(act_set_main)
        menu.addAction(act_clear_main)

        menu.exec(self.global_modules.viewport().mapToGlobal(pos))

    def clear_configs(self):
        """
        清空全局配置树
        """
        self.global_cfg.clear()

    def get_config_snapshot(self) -> list[dict]:
        return [copy.deepcopy(self._get_cfg_data(item)) for item in self._iter_cfg_items()]

    def update_config_list(self, config_data_list: list[dict]):
        """
        根据传入的配置列表重新构建树节点
        """
        self.global_cfg.blockSignals(True)  # 插入时阻塞信号提高性能
        try:
            self.clear_configs()
            for cfg in config_data_list:
                name = cfg.get("name", "")
                comment = cfg.get("comment", "")
                expr = cfg.get("value", "")  # 将后端的 values 对应到前端的 expr
                realvalue = cfg.get("realvalue", "")

                # 使用类中已有的私有方法创建节点
                self._add_cfg_item(name, comment, expr)
                item = self._find_cfg_by_name(name)
                if item is not None:
                    data = self._get_cfg_data(item)
                    data["realvalue"] = realvalue
                    item.setData(0, Qt.ItemDataRole.UserRole, data)

            # 可选：按名称自动排序
            self.global_cfg.sortItems(0, Qt.SortOrder.AscendingOrder)
        finally:
            self.global_cfg.blockSignals(False)

    def edit_config_by_name(self, name: str) -> bool:
        item = self._find_cfg_by_name(name)
        if item is None:
            return False
        self._edit_cfg_item(item)
        return True

    def edit_harness_by_name(self, name: str) -> bool:
        item = self._find_harness_by_name(name)
        if item is None:
            return False
        self._edit_harness_item(item)
        return True

    # ---- delete mode：允许树上任意节点勾选（根/实例都可勾选），删除时按模块名去重删除模块定义
    def _enter_module_delete_mode(self):
        if self._module_delete_mode:
            return
        self._module_delete_mode = True

        self.btn_add_module.setEnabled(False)
        self.btn_del_module.setEnabled(False)
        self.cmb_module_view.setEnabled(False)

        self.module_action_bar.setVisible(True)
        self.global_modules.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)

        for it in self._iter_all_module_tree_items():
            self._set_item_checkable(it, enabled=True)

    def _exit_module_delete_mode(self):
        if not self._module_delete_mode:
            return
        self._module_delete_mode = False

        self.btn_add_module.setEnabled(True)
        self.btn_del_module.setEnabled(True)
        self.cmb_module_view.setEnabled(True)

        self.module_action_bar.setVisible(False)
        self.global_modules.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        for it in self._iter_all_module_tree_items():
            self._set_item_checkable(it, enabled=False)

        QToolTip.hideText()

    def _on_module_item_clicked(self, item: QTreeWidgetItem, column: int):
        if not self._module_delete_mode:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        cur = item.checkState(0)
        item.setCheckState(0, Qt.CheckState.Unchecked if cur == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def _delete_checked_module_items(self):
        if not self._module_delete_mode:
            return

        # 收集勾选节点对应的模块名（根节点=自身，实例节点=引用模块）
        targets: set[str] = set()
        for it in self._iter_all_module_tree_items():
            if it.checkState(0) == Qt.CheckState.Checked:
                mn = self._node_module_name(it)
                if mn:
                    targets.add(mn)

        if not targets:
            QMessageBox.information(self, "未选择", "请勾选要删除的模块。")
            return

        names = sorted(targets)
        confirm = QMessageBox.question(
            self, "确认删除",
            "将删除以下模块定义：\n\n" + "\n".join(names) + "\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # 删除模块定义
        for n in names:
            self._modules.pop(n, None)
            if self._main_module_name == n:
                self._main_module_name = ""
                self._main_module_manual = False

        # 清理所有父模块里引用到已删除模块的 submodules
        for m in self._modules.values():
            submods = m.get("submodules") or []
            m["submodules"] = [sm for sm in submods if (sm.get("module") or "").strip() not in targets]

        self._refresh_module_tree()
        self._exit_module_delete_mode()
        self._emit_module_library_changed()

    def _on_module_item_hover(self, item: QTreeWidgetItem, column: int):
        # 悬停：显示“模块注释”（实例节点显示实例/父模块/子模块信息）
        payload = item.data(0, Qt.ItemDataRole.UserRole) or {}
        kind = payload.get("_kind", "")
        if kind == "submodule_inst":
            mod = (payload.get("module") or "").strip()
            inst = (payload.get("inst") or "").strip()
            parent = (payload.get("parent") or "").strip()
            tip = self._node_tooltip_for(mod, inst_name=inst, parent_name=parent)
        else:
            mod = self._node_module_name(item)
            tip = self._node_tooltip_for(mod)

        QToolTip.showText(QCursor.pos(), tip, self.global_modules)

