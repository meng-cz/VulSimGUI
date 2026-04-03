from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
)


class ConfigRelationPage(QWidget):
    requestRefresh = pyqtSignal(str)
    requestEdit = pyqtSignal(str)
    requestDelete = pyqtSignal(str)
    requestOpenConfig = pyqtSignal(str)
    requestOpenHarness = pyqtSignal(str)

    def __init__(self, name: str, detail: dict | None = None, parent=None):
        super().__init__(parent)
        self.config_name = name

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")

        self.btn_refresh = QPushButton("刷新")
        self.btn_edit = QPushButton("编辑")
        self.btn_delete = QPushButton("删除")

        top_row.addWidget(self.title_label)
        top_row.addStretch(1)
        top_row.addWidget(self.btn_refresh)
        top_row.addWidget(self.btn_edit)
        top_row.addWidget(self.btn_delete)
        root.addLayout(top_row)

        info_group = QGroupBox("详细信息")
        info_form = QFormLayout(info_group)
        info_form.setContentsMargins(12, 12, 12, 12)
        info_form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setReadOnly(True)

        self.realvalue_edit = QLineEdit()
        self.realvalue_edit.setReadOnly(True)

        self.comment_edit = QTextEdit()
        self.comment_edit.setReadOnly(True)
        self.comment_edit.setFixedHeight(80)

        self.expr_edit = QTextEdit()
        self.expr_edit.setReadOnly(True)
        self.expr_edit.setFixedHeight(90)

        info_form.addRow("配置名：", self.name_edit)
        info_form.addRow("实值：", self.realvalue_edit)
        info_form.addRow("注释：", self.comment_edit)
        info_form.addRow("表达式：", self.expr_edit)
        root.addWidget(info_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        up_group = QGroupBox("向上依赖（递归）")
        up_layout = QVBoxLayout(up_group)
        up_layout.setContentsMargins(10, 10, 10, 10)
        self.required_by_tree = QTreeWidget()
        self.required_by_tree.setHeaderHidden(True)
        up_layout.addWidget(self.required_by_tree)
        left_layout.addWidget(up_group, 1)

        down_group = QGroupBox("向下依赖（递归）")
        down_layout = QVBoxLayout(down_group)
        down_layout.setContentsMargins(10, 10, 10, 10)
        self.depends_on_tree = QTreeWidget()
        self.depends_on_tree.setHeaderHidden(True)
        down_layout.addWidget(self.depends_on_tree)
        left_layout.addWidget(down_group, 1)

        bundle_group = QGroupBox("依赖此配置的全局线组")
        bundle_layout = QVBoxLayout(bundle_group)
        bundle_layout.setContentsMargins(10, 10, 10, 10)
        self.bundle_tree = QTreeWidget()
        self.bundle_tree.setHeaderHidden(True)
        self.bundle_tree.setRootIsDecorated(False)
        bundle_layout.addWidget(self.bundle_tree)
        left_layout.addWidget(bundle_group, 1)

        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        self.preview_title = QLabel("未选择")
        self.preview_kind = QLineEdit()
        self.preview_kind.setReadOnly(True)

        self.preview_summary = QTextEdit()
        self.preview_summary.setReadOnly(True)
        self.preview_summary.setMinimumHeight(220)

        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_kind)
        preview_layout.addWidget(self.preview_summary, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(preview_group)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        for tree in (self.required_by_tree, self.depends_on_tree, self.bundle_tree):
            tree.itemClicked.connect(self._on_relation_item_clicked)
            tree.itemDoubleClicked.connect(self._on_relation_item_double_clicked)

        self.btn_refresh.clicked.connect(lambda: self.requestRefresh.emit(self.config_name))
        self.btn_edit.clicked.connect(lambda: self.requestEdit.emit(self.config_name))
        self.btn_delete.clicked.connect(lambda: self.requestDelete.emit(self.config_name))

        self.reload(detail or {
            "name": name,
            "comment": "",
            "expr": "",
            "realvalue": "",
            "depends_on_tree": [],
            "required_by_tree": [],
            "bundle_refs": [],
        })

    def reload(self, detail: dict):
        self.config_name = detail.get("name", self.config_name) or self.config_name
        self.title_label.setText(f"全局配置：{self.config_name}")
        self.name_edit.setText(self.config_name)
        self.realvalue_edit.setText(detail.get("realvalue", "") or "（未解析）")
        self.comment_edit.setPlainText(detail.get("comment", "") or "")
        self.expr_edit.setPlainText(detail.get("expr", "") or "")

        self._populate_config_tree(self.required_by_tree, detail.get("required_by_tree", []) or [])
        self._populate_config_tree(self.depends_on_tree, detail.get("depends_on_tree", []) or [])
        self._populate_bundle_list(self.bundle_tree, detail.get("bundle_refs", []) or [])

        self._show_preview({
            "kind": "config",
            "name": self.config_name,
            "comment": detail.get("comment", "") or "",
            "expr": detail.get("expr", "") or "",
            "realvalue": detail.get("realvalue", "") or "",
        })

    def _populate_config_tree(self, tree: QTreeWidget, nodes: list[dict]):
        tree.clear()
        if not nodes:
            empty_item = QTreeWidgetItem(["（无）"])
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            tree.addTopLevelItem(empty_item)
            return

        for node in nodes:
            tree.addTopLevelItem(self._build_config_item(node))
        tree.expandAll()

    def _populate_bundle_list(self, tree: QTreeWidget, bundles: list[dict]):
        tree.clear()
        if not bundles:
            empty_item = QTreeWidgetItem(["（无）"])
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            tree.addTopLevelItem(empty_item)
            return

        for bundle in bundles:
            item = QTreeWidgetItem([bundle.get("name", "") or ""])
            item.setData(0, Qt.ItemDataRole.UserRole, bundle)
            item.setToolTip(0, bundle.get("comment", "") or "（无注释）")
            tree.addTopLevelItem(item)

    def _build_config_item(self, node: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.get("name", "") or ""])
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        item.setToolTip(0, node.get("comment", "") or "（无注释）")
        for child in node.get("children", []) or []:
            item.addChild(self._build_config_item(child))
        return item

    def _on_relation_item_clicked(self, item: QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(payload, dict):
            self._show_preview(payload)

    def _on_relation_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return

        kind = payload.get("kind", "")
        name = payload.get("name", "")
        if kind == "config" and name:
            self.requestOpenConfig.emit(name)
        elif kind == "harness" and name:
            self.requestOpenHarness.emit(name)

    def _show_preview(self, payload: dict):
        kind = payload.get("kind", "")
        name = payload.get("name", "") or "未选择"

        if kind == "config":
            self.preview_title.setText(f"配置项：{name}")
            self.preview_kind.setText("全局配置")
            text = [
                f"注释：{payload.get('comment', '') or '（无注释）'}",
                "",
                f"表达式：{payload.get('expr', '') or '（空）'}",
                f"实值：{payload.get('realvalue', '') or '（未解析）'}",
            ]
            self.preview_summary.setPlainText("\n".join(text))
            return

        if kind == "harness":
            self.preview_title.setText(f"线组：{name}")
            self.preview_kind.setText("全局线组")
            text = [
                f"注释：{payload.get('comment', '') or '（无注释）'}",
                "",
                f"摘要：{payload.get('summary', '') or '（无详细摘要）'}",
            ]
            self.preview_summary.setPlainText("\n".join(text))
            return

        self.preview_title.setText(name)
        self.preview_kind.setText("未知")
        self.preview_summary.setPlainText(payload.get("comment", "") or "")
