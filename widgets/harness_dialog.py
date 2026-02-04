from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTreeWidget, QTreeWidgetItem,
    QPushButton, QDialog, QFormLayout, QLineEdit, QTextEdit,
    QDialogButtonBox, QMessageBox, QToolTip, QLabel, QMenu,
    QCheckBox, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView
)

# =========================
# Harness Dialog (per spec)
# =========================
class HarnessDialog(QDialog):
    """
    新增/编辑线束（Tab 模式）：
    - 第一行：线束名（唯一索引）+ 注释（单行，可选）
    - 下方 Tab：
      1) 成员列表：成员表格
      2) 枚举成员：枚举表格
      3) 别名：只填写一个别名目标（通常引用其他线束名）
    保存规则：
      - 以当前选中 Tab 为准，三者互斥
      - 别名 Tab：alias=True, enums=[], members 仅一个元素表示别名目标
    """

    MEMBER_COLS = ["成员名", "成员类型(可引用线束名)", "整数长度(表达式)", "注释", "默认值(表达式)", "维度(表达式数组)"]
    ENUM_COLS = ["成员名", "注释", "值(表达式)"]

    TAB_MEMBERS = 0
    TAB_ENUMS = 1
    TAB_ALIAS = 2

    def __init__(self, title: str, harness_data: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(900, 600)

        harness_data = harness_data or {}

        layout = QVBoxLayout(self)

        # ---- Top: name + comment（保持不变）
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：AXI_Lite_Req 或 sys_v1.harness")
        self.name_edit.setText(harness_data.get("name", ""))

        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("可选：线束注释（用于悬浮提示）")
        self.comment_edit.setText(harness_data.get("comment", ""))

        form.addRow("线束名：", self.name_edit)
        form.addRow("注释：", self.comment_edit)
        layout.addLayout(form)

        # ---- Tabs: members / enums / alias
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # ========== Tab 1: Members ==========
        members_page = QWidget()
        members_layout = QVBoxLayout(members_page)
        members_layout.setContentsMargins(0, 0, 0, 0)
        members_layout.setSpacing(8)

        mem_btn_row = QHBoxLayout()
        self.btn_add_member = QPushButton("新增成员")
        self.btn_del_member = QPushButton("删除选中成员")
        mem_btn_row.addStretch(1)
        mem_btn_row.addWidget(self.btn_add_member)
        mem_btn_row.addWidget(self.btn_del_member)
        members_layout.addLayout(mem_btn_row)

        self.members_tbl = QTableWidget(0, len(self.MEMBER_COLS))
        self.members_tbl.setHorizontalHeaderLabels(self.MEMBER_COLS)
        self.members_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.members_tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.members_tbl.horizontalHeader().setStretchLastSection(True)
        members_layout.addWidget(self.members_tbl, 1)

        self.tabs.addTab(members_page, "成员列表")

        # ========== Tab 2: Enums ==========
        enums_page = QWidget()
        enums_layout = QVBoxLayout(enums_page)
        enums_layout.setContentsMargins(0, 0, 0, 0)
        enums_layout.setSpacing(8)

        enum_btn_row = QHBoxLayout()
        self.btn_add_enum = QPushButton("新增枚举成员")
        self.btn_del_enum = QPushButton("删除选中枚举成员")
        enum_btn_row.addStretch(1)
        enum_btn_row.addWidget(self.btn_add_enum)
        enum_btn_row.addWidget(self.btn_del_enum)
        enums_layout.addLayout(enum_btn_row)

        self.enums_tbl = QTableWidget(0, len(self.ENUM_COLS))
        self.enums_tbl.setHorizontalHeaderLabels(self.ENUM_COLS)
        self.enums_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.enums_tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.enums_tbl.horizontalHeader().setStretchLastSection(True)
        enums_layout.addWidget(self.enums_tbl, 1)

        self.tabs.addTab(enums_page, "枚举成员")

        # ========== Tab 3: Alias ==========
        alias_page = QWidget()
        alias_layout = QFormLayout(alias_page)

        self.alias_target_edit = QLineEdit()
        self.alias_target_edit.setPlaceholderText("填写别名目标（例如：OtherHarnessName）")
        alias_layout.addRow("别名目标：", self.alias_target_edit)

        hint = QLabel("说明：别名模式下，只需要填写一个别名目标。保存时将自动生成 1 个成员用于表示别名目标。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #94a3b8;")  # 可选：如果你更想统一，用 QSS 控制更好
        alias_layout.addRow("", hint)

        self.tabs.addTab(alias_page, "别名")

        # ---- Dialog buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # ---- Wire buttons
        self.btn_add_member.clicked.connect(self._add_member_row)
        self.btn_del_member.clicked.connect(self._del_selected_row_members)
        self.btn_add_enum.clicked.connect(self._add_enum_row)
        self.btn_del_enum.clicked.connect(self._del_selected_row_enums)

        # ---- Fill initial data + set initial tab
        self._load_from_data(harness_data)

    # =========================
    # Load initial data -> decide which tab
    # =========================
    def _load_from_data(self, data: dict):
        alias = bool(data.get("alias", False))
        members = data.get("members", []) or []
        enums = data.get("enums", []) or []

        # 先填表
        self.members_tbl.setRowCount(0)
        for m in members:
            self._add_member_row(m)

        self.enums_tbl.setRowCount(0)
        for e in enums:
            self._add_enum_row(e)

        # Alias 目标：若 alias=True，则尝试从 members[0].type 或 members[0].name 推断
        if alias:
            target = ""
            if members:
                # 约定：别名目标优先放 type 字段
                target = (members[0].get("type") or members[0].get("name") or "")
            self.alias_target_edit.setText(str(target))
            self.tabs.setCurrentIndex(self.TAB_ALIAS)
            return

        # 非 alias：有 enums 则枚举 tab，否则成员 tab
        if enums:
            self.tabs.setCurrentIndex(self.TAB_ENUMS)
        else:
            self.tabs.setCurrentIndex(self.TAB_MEMBERS)

    # =========================
    # Table helpers
    # =========================
    def _add_member_row(self, m: dict | None = None):
        m = m or {}
        r = self.members_tbl.rowCount()
        self.members_tbl.insertRow(r)
        vals = [
            m.get("name", ""),
            m.get("type", ""),
            m.get("int_len", ""),
            m.get("comment", ""),
            m.get("default", ""),
            m.get("dims", ""),
        ]
        for c, v in enumerate(vals):
            self.members_tbl.setItem(r, c, QTableWidgetItem(str(v)))

    def _add_enum_row(self, e: dict | None = None):
        e = e or {}
        r = self.enums_tbl.rowCount()
        self.enums_tbl.insertRow(r)
        vals = [
            e.get("name", ""),
            e.get("comment", ""),
            e.get("value", ""),
        ]
        for c, v in enumerate(vals):
            self.enums_tbl.setItem(r, c, QTableWidgetItem(str(v)))

    def _del_selected_row_members(self):
        r = self.members_tbl.currentRow()
        if r >= 0:
            self.members_tbl.removeRow(r)

    def _del_selected_row_enums(self):
        r = self.enums_tbl.currentRow()
        if r >= 0:
            self.enums_tbl.removeRow(r)

    def _collect_members(self) -> list[dict]:
        out = []
        for r in range(self.members_tbl.rowCount()):
            name = (self.members_tbl.item(r, 0).text().strip() if self.members_tbl.item(r, 0) else "")
            mtype = (self.members_tbl.item(r, 1).text().strip() if self.members_tbl.item(r, 1) else "")
            ilen = (self.members_tbl.item(r, 2).text().strip() if self.members_tbl.item(r, 2) else "")
            comment = (self.members_tbl.item(r, 3).text().strip() if self.members_tbl.item(r, 3) else "")
            default = (self.members_tbl.item(r, 4).text().strip() if self.members_tbl.item(r, 4) else "")
            dims = (self.members_tbl.item(r, 5).text().strip() if self.members_tbl.item(r, 5) else "")
            if not name and not mtype and not ilen and not comment and not default and not dims:
                continue
            out.append({
                "name": name,
                "type": mtype,
                "int_len": ilen,
                "comment": comment,
                "default": default,
                "dims": dims,
            })
        return out

    def _collect_enums(self) -> list[dict]:
        out = []
        for r in range(self.enums_tbl.rowCount()):
            name = (self.enums_tbl.item(r, 0).text().strip() if self.enums_tbl.item(r, 0) else "")
            comment = (self.enums_tbl.item(r, 1).text().strip() if self.enums_tbl.item(r, 1) else "")
            value = (self.enums_tbl.item(r, 2).text().strip() if self.enums_tbl.item(r, 2) else "")
            if not name and not comment and not value:
                continue
            out.append({
                "name": name,
                "comment": comment,
                "value": value,
            })
        return out

    # =========================
    # OK validation per current tab
    # =========================
    def _on_ok(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入无效", "线束名不能为空。")
            return

        tab = self.tabs.currentIndex()

        if tab == self.TAB_ALIAS:
            target = self.alias_target_edit.text().strip()
            if not target:
                QMessageBox.warning(self, "输入无效", "别名目标不能为空。")
                return

            # 别名模式：强制 members 只有一个元素表示目标
            # 这里用 type 字段保存目标，name 给一个固定值也可以（后续你若要更语义化可改）
            self._result = {
                "name": name,
                "comment": self.comment_edit.text().strip(),
                "alias": True,
                "members": [{
                    "name": "alias_target",
                    "type": target,
                    "int_len": "",
                    "comment": "",
                    "default": "",
                    "dims": "",
                }],
                "enums": [],
            }
            self.accept()
            return

        if tab == self.TAB_ENUMS:
            enums = self._collect_enums()
            if not enums:
                QMessageBox.warning(self, "输入无效", "枚举成员列表不能为空（至少填写一个枚举成员）。")
                return

            self._result = {
                "name": name,
                "comment": self.comment_edit.text().strip(),
                "alias": False,
                "members": [],
                "enums": enums,
            }
            self.accept()
            return

        # 默认：成员列表
        members = self._collect_members()
        if not members:
            QMessageBox.warning(self, "输入无效", "成员列表不能为空（至少填写一个成员）。")
            return

        # 成员类型 vs 整数长度互斥（逐行校验）
        for m in members:
            if m.get("type") and m.get("int_len"):
                QMessageBox.warning(self, "输入无效",
                                    f"成员“{m.get('name','') or '(未命名)'}”：成员类型 与 整数长度 互斥，请只填写其中一个。")
                return

        self._result = {
            "name": name,
            "comment": self.comment_edit.text().strip(),
            "alias": False,
            "members": members,
            "enums": [],
        }
        self.accept()

    def get_data(self) -> dict:
        # 只在 accept 后调用
        return getattr(self, "_result", {
            "name": self.name_edit.text().strip(),
            "comment": self.comment_edit.text().strip(),
            "alias": False,
            "members": [],
            "enums": [],
        })