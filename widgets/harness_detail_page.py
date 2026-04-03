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
    QTabWidget,
)


class HarnessDetailPage(QWidget):
    requestRefresh = pyqtSignal(str)
    requestEdit = pyqtSignal(str)
    requestDelete = pyqtSignal(str)
    requestOpenConfig = pyqtSignal(str)
    requestOpenHarness = pyqtSignal(str)

    def __init__(self, name: str, detail: dict | None = None, parent=None):
        super().__init__(parent)
        self.harness_name = name

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

        self.kind_edit = QLineEdit()
        self.kind_edit.setReadOnly(True)

        self.tags_edit = QLineEdit()
        self.tags_edit.setReadOnly(True)

        self.comment_edit = QTextEdit()
        self.comment_edit.setReadOnly(True)
        self.comment_edit.setFixedHeight(80)

        info_form.addRow("线组名：", self.name_edit)
        info_form.addRow("定义类型：", self.kind_edit)
        info_form.addRow("标签：", self.tags_edit)
        info_form.addRow("注释：", self.comment_edit)
        root.addWidget(info_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left_panel = QTabWidget()
        splitter.addWidget(left_panel)

        structure_page = QWidget()
        structure_layout = QVBoxLayout(structure_page)
        structure_layout.setContentsMargins(0, 0, 0, 0)
        self.structure_tree = QTreeWidget()
        self.structure_tree.setColumnCount(5)
        self.structure_tree.setHeaderLabels(["名称", "类型/位宽", "默认值", "维度", "注释"])
        structure_layout.addWidget(self.structure_tree)
        left_panel.addTab(structure_page, "详细内容")

        depends_page = QWidget()
        depends_layout = QVBoxLayout(depends_page)
        depends_layout.setContentsMargins(0, 0, 0, 0)
        self.depends_tree = QTreeWidget()
        self.depends_tree.setHeaderHidden(True)
        depends_layout.addWidget(self.depends_tree)
        left_panel.addTab(depends_page, "依赖项")

        reverse_page = QWidget()
        reverse_layout = QVBoxLayout(reverse_page)
        reverse_layout.setContentsMargins(0, 0, 0, 0)
        self.required_by_tree = QTreeWidget()
        self.required_by_tree.setHeaderHidden(True)
        reverse_layout.addWidget(self.required_by_tree)
        left_panel.addTab(reverse_page, "反向依赖")

        config_page = QWidget()
        config_layout = QVBoxLayout(config_page)
        config_layout.setContentsMargins(0, 0, 0, 0)
        self.config_tree = QTreeWidget()
        self.config_tree.setHeaderHidden(True)
        self.config_tree.setRootIsDecorated(False)
        config_layout.addWidget(self.config_tree)
        left_panel.addTab(config_page, "配置引用")

        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        self.preview_title = QLabel("未选择")
        self.preview_kind = QLineEdit()
        self.preview_kind.setReadOnly(True)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(260)

        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_kind)
        preview_layout.addWidget(self.preview_text, 1)
        splitter.addWidget(preview_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        for tree in (self.structure_tree, self.depends_tree, self.required_by_tree, self.config_tree):
            tree.itemClicked.connect(self._on_tree_item_clicked)
            tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)

        self.btn_refresh.clicked.connect(lambda: self.requestRefresh.emit(self.harness_name))
        self.btn_edit.clicked.connect(lambda: self.requestEdit.emit(self.harness_name))
        self.btn_delete.clicked.connect(lambda: self.requestDelete.emit(self.harness_name))

        self.reload(detail or {
            "name": name,
            "comment": "",
            "tags": "",
            "is_alias": False,
            "alias_target": "",
            "members": [],
            "enums": [],
            "depends_on_tree": [],
            "required_by_tree": [],
            "config_refs": [],
        })

    def reload(self, detail: dict):
        self.harness_name = detail.get("name", self.harness_name) or self.harness_name
        self.title_label.setText(f"全局线组：{self.harness_name}")
        self.name_edit.setText(self.harness_name)
        self.kind_edit.setText(self._kind_text(detail))
        self.tags_edit.setText(detail.get("tags", "") or "（无）")
        self.comment_edit.setPlainText(detail.get("comment", "") or "")

        self._populate_structure_tree(detail)
        self._populate_ref_tree(self.depends_tree, detail.get("depends_on_tree", []) or [])
        self._populate_ref_tree(self.required_by_tree, detail.get("required_by_tree", []) or [])
        self._populate_config_tree(detail.get("config_refs", []) or [])

        self._show_preview({
            "kind": "harness",
            "name": self.harness_name,
            "comment": detail.get("comment", "") or "",
            "summary": self._kind_text(detail),
        })

    def _kind_text(self, detail: dict) -> str:
        if detail.get("is_alias"):
            target = detail.get("alias_target", "") or "（未指定）"
            return f"别名 -> {target}"
        enums = detail.get("enums", []) or []
        if enums:
            return f"枚举，共 {len(enums)} 项"
        members = detail.get("members", []) or []
        return f"结构体，共 {len(members)} 项"

    def _populate_structure_tree(self, detail: dict):
        self.structure_tree.clear()

        if detail.get("is_alias"):
            root = QTreeWidgetItem(["别名目标", detail.get("alias_target", "") or "", "", "", detail.get("comment", "") or ""])
            root.setData(0, Qt.ItemDataRole.UserRole, {
                "kind": "harness",
                "name": detail.get("alias_target", "") or "",
                "comment": "",
                "summary": "别名目标",
            })
            self.structure_tree.addTopLevelItem(root)
        else:
            members_root = QTreeWidgetItem(["成员列表", "", "", "", ""])
            members_root.setFlags(members_root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.structure_tree.addTopLevelItem(members_root)

            members = detail.get("members", []) or []
            if members:
                for member in members:
                    dims = member.get("dims", []) or []
                    type_text = member.get("type", "") or member.get("uint_length", "") or ""
                    row = QTreeWidgetItem([
                        member.get("name", "") or "",
                        type_text,
                        member.get("value", "") or "",
                        ", ".join(str(x) for x in dims) if dims else "",
                        member.get("comment", "") or "",
                    ])
                    payload = {
                        "kind": "member",
                        "name": member.get("name", "") or "",
                        "comment": member.get("comment", "") or "",
                        "type": member.get("type", "") or "",
                        "uint_length": member.get("uint_length", "") or "",
                        "value": member.get("value", "") or "",
                        "dims": dims,
                    }
                    row.setData(0, Qt.ItemDataRole.UserRole, payload)
                    members_root.addChild(row)
            else:
                members_root.addChild(QTreeWidgetItem(["（无成员）", "", "", "", ""]))

            enums_root = QTreeWidgetItem(["枚举成员", "", "", "", ""])
            enums_root.setFlags(enums_root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.structure_tree.addTopLevelItem(enums_root)

            enums = detail.get("enums", []) or []
            if enums:
                for enum_member in enums:
                    row = QTreeWidgetItem([
                        enum_member.get("name", "") or "",
                        "枚举值",
                        enum_member.get("value", "") or "",
                        "",
                        enum_member.get("comment", "") or "",
                    ])
                    row.setData(0, Qt.ItemDataRole.UserRole, {
                        "kind": "enum",
                        "name": enum_member.get("name", "") or "",
                        "comment": enum_member.get("comment", "") or "",
                        "value": enum_member.get("value", "") or "",
                    })
                    enums_root.addChild(row)
            else:
                enums_root.addChild(QTreeWidgetItem(["（无枚举成员）", "", "", "", ""]))

        self.structure_tree.expandAll()
        for i in range(self.structure_tree.columnCount()):
            self.structure_tree.resizeColumnToContents(i)

    def _populate_ref_tree(self, tree: QTreeWidget, nodes: list[dict]):
        tree.clear()
        if not nodes:
            empty_item = QTreeWidgetItem(["（无）"])
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            tree.addTopLevelItem(empty_item)
            return

        for node in nodes:
            tree.addTopLevelItem(self._build_harness_ref_item(node))
        tree.expandAll()

    def _populate_config_tree(self, configs: list[dict]):
        self.config_tree.clear()
        if not configs:
            empty_item = QTreeWidgetItem(["（无）"])
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.config_tree.addTopLevelItem(empty_item)
            return

        for cfg in configs:
            item = QTreeWidgetItem([cfg.get("name", "") or ""])
            item.setData(0, Qt.ItemDataRole.UserRole, cfg)
            item.setToolTip(0, cfg.get("comment", "") or "（无注释）")
            self.config_tree.addTopLevelItem(item)

    def _build_harness_ref_item(self, node: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.get("name", "") or ""])
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        item.setToolTip(0, node.get("comment", "") or "（无注释）")
        for child in node.get("children", []) or []:
            item.addChild(self._build_harness_ref_item(child))
        return item

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(payload, dict):
            self._show_preview(payload)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return

        kind = payload.get("kind", "")
        if kind == "config":
            name = payload.get("name", "")
            if name:
                self.requestOpenConfig.emit(name)
            return

        if kind == "harness":
            name = payload.get("name", "")
            if name:
                self.requestOpenHarness.emit(name)
            return

        if kind == "member":
            target_type = payload.get("type", "")
            if target_type:
                self.requestOpenHarness.emit(target_type)

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
            self.preview_text.setPlainText("\n".join(text))
            return

        if kind == "harness":
            self.preview_title.setText(f"线组：{name}")
            self.preview_kind.setText("全局线组")
            text = [
                f"注释：{payload.get('comment', '') or '（无注释）'}",
                "",
                f"摘要：{payload.get('summary', '') or '（无详细摘要）'}",
            ]
            self.preview_text.setPlainText("\n".join(text))
            return

        if kind == "member":
            dims = payload.get("dims", []) or []
            type_text = payload.get("type", "") or payload.get("uint_length", "") or "（未指定）"
            text = [
                f"注释：{payload.get('comment', '') or '（无注释）'}",
                "",
                f"类型/位宽：{type_text}",
                f"默认值：{payload.get('value', '') or '（空）'}",
                f"维度：{', '.join(str(x) for x in dims) if dims else '（无）'}",
            ]
            self.preview_title.setText(f"成员：{name}")
            self.preview_kind.setText("线组成员")
            self.preview_text.setPlainText("\n".join(text))
            return

        if kind == "enum":
            self.preview_title.setText(f"枚举成员：{name}")
            self.preview_kind.setText("枚举")
            text = [
                f"注释：{payload.get('comment', '') or '（无注释）'}",
                "",
                f"取值：{payload.get('value', '') or '（空）'}",
            ]
            self.preview_text.setPlainText("\n".join(text))
            return

        self.preview_title.setText(name)
        self.preview_kind.setText("未知")
        self.preview_text.setPlainText(payload.get("comment", "") or "")
