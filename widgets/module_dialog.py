from __future__ import annotations

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QSize

from PyQt6.QtWidgets import (
    QDialog, QWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit,
    QListWidget, QListWidgetItem,
    QStackedWidget,
    QTableWidget, QTableWidgetItem,
    QPushButton, QLabel,
    QDialogButtonBox, QMessageBox,
    QHeaderView,
)


class ModuleDialog(QDialog):
    """
    左右结构模块编辑器：
    - 左侧：功能侧边栏（基本配置/本地配置/本地线束/请求服务/管道端口/...）
    - 右侧：对应功能的编辑页面（自上而下，一行一组字段）
    """

    # side menu indices（只保留你要显示的模块）
    PAGE_BASIC = 0
    PAGE_LOCAL_CFG = 1
    PAGE_LOCAL_HARNESS = 2
    PAGE_RPC = 3
    PAGE_PIPE_PORTS = 4
    PAGE_SUBMODULES = 5
    PAGE_PIPES = 6
    PAGE_STORAGES = 7

    def __init__(self, title: str, module_data: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(1100, 720)

        module_data = module_data or {}

        root = QVBoxLayout(self)

        # =========================
        # Main: left sidebar + right pages
        # =========================
        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(10)
        root.addLayout(main, 1)

        # ---- Left: sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # ✅ 只添加要显示的 8 个模块
        self._add_sidebar_item("基本配置", self.PAGE_BASIC, ":/resources/icons/basic.svg")
        self._add_sidebar_item("本地配置", self.PAGE_LOCAL_CFG, ":/resources/icons/local_cfg.svg")
        self._add_sidebar_item("本地线束", self.PAGE_LOCAL_HARNESS, ":/resources/icons/local_harness.svg")
        self._add_sidebar_item("请求/服务", self.PAGE_RPC, ":/resources/icons/rpc.svg")
        self._add_sidebar_item("管道端口", self.PAGE_PIPE_PORTS, ":/resources/icons/pipe_ports.svg")
        self._add_sidebar_item("模块实例", self.PAGE_SUBMODULES, ":/resources/icons/submodules.svg")
        self._add_sidebar_item("管道实例", self.PAGE_PIPES, ":/resources/icons/pipes.svg")
        self._add_sidebar_item("存储", self.PAGE_STORAGES, ":/resources/icons/storages.svg")

        main.addWidget(self.sidebar)

        # ---- Right: stacked pages
        self.pages = QStackedWidget()
        main.addWidget(self.pages, 1)

        # =========================
        # Pages（✅ 只构建要显示的页面）
        # =========================
        self._build_page_basic()
        self._build_page_local_cfg()
        self._build_page_local_harness()
        self._build_page_rpc()
        self._build_page_pipe_ports()
        self._build_page_submodules()
        self._build_page_pipes()
        self._build_page_storages()

        # =========================
        # Buttons
        # =========================
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # sidebar behavior
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(self.PAGE_BASIC)

        self.sidebar.setObjectName("ideSidebar")

        # load existing
        self._load(module_data)

    # -------------------------
    # Sidebar helpers
    # -------------------------
    def _add_sidebar_item(self, text: str, page_index: int, icon_path: str):
        it = QListWidgetItem(QIcon(icon_path), text)
        it.setData(Qt.ItemDataRole.UserRole, page_index)
        it.setSizeHint(it.sizeHint().expandedTo(QSize(it.sizeHint().width(), 34)))
        self.sidebar.addItem(it)

    # -------------------------
    # UI helpers: table + add/del wrapper
    # -------------------------
    def _mk_table(self, headers: list[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        return tbl

    def _wrap_table_with_add_del(self, tbl: QTableWidget, add_text: str, del_text: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        btn_add = QPushButton(add_text)
        btn_del = QPushButton(del_text)
        row.addWidget(btn_add)
        row.addWidget(btn_del)

        lay.addLayout(row)
        lay.addWidget(tbl, 1)

        btn_add.clicked.connect(lambda: self._add_row(tbl))
        btn_del.clicked.connect(lambda: self._del_selected_row(tbl))
        return w

    def _add_row(self, tbl: QTableWidget):
        tbl.insertRow(tbl.rowCount())

    def _del_selected_row(self, tbl: QTableWidget):
        r = tbl.currentRow()
        if r >= 0:
            tbl.removeRow(r)

    # -------------------------
    # Data helpers
    # -------------------------
    def _table_to_rows(self, tbl: QTableWidget, keys: list[str]) -> list[dict]:
        out: list[dict] = []
        for r in range(tbl.rowCount()):
            row = {}
            empty = True
            for c, k in enumerate(keys):
                it = tbl.item(r, c)
                val = it.text().strip() if it else ""
                if val:
                    empty = False
                row[k] = val
            if not empty:
                out.append(row)
        return out

    def _rows_to_table(self, tbl: QTableWidget, keys: list[str], rows: list[dict]):
        tbl.setRowCount(0)
        for row in rows or []:
            r = tbl.rowCount()
            tbl.insertRow(r)
            for c, k in enumerate(keys):
                tbl.setItem(r, c, QTableWidgetItem(str(row.get(k, ""))))

    # =========================
    # Build pages
    # =========================
    def _build_page_basic(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        title = QLabel("基本配置")
        title.setStyleSheet("font-weight: 700;")
        lay.addWidget(title)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：Core_Logic 或 CPU_Cluster_A")

        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("可选：模块注释（用于悬浮提示）")

        form.addRow("模块名：", self.name_edit)
        form.addRow("注释：", self.comment_edit)
        lay.addLayout(form)

        lay.addStretch(1)
        self.pages.addWidget(page)

    def _build_page_local_cfg(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("本地配置列表（仅模块内部常量）"))
        self.local_cfg_tbl = self._mk_table(["本地配置名", "默认值(表达式)", "注释"])
        lay.addWidget(self._wrap_table_with_add_del(self.local_cfg_tbl, "新增本地配置", "删除选中"), 1)

        self.pages.addWidget(page)

    def _build_page_local_harness(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("本地线束列表（可引用本地配置/本地线束；定义内容暂以 JSON 文本承载）"))
        self.local_harness_tbl = self._mk_table(["本地线束名", "注释", "定义模式(alias/members/enums)", "定义内容(JSON)"])
        lay.addWidget(self._wrap_table_with_add_del(self.local_harness_tbl, "新增本地线束", "删除选中"), 1)

        self.pages.addWidget(page)

    def _build_page_rpc(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("请求/服务列表（请求端口/服务端口）"))
        self.rpc_tbl = self._mk_table(["类型(req/service)", "名称", "注释", "参数列表(JSON)", "返回值列表(JSON)", "包含握手(true/false)"])
        lay.addWidget(self._wrap_table_with_add_del(self.rpc_tbl, "新增请求/服务", "删除选中"), 1)

        self.pages.addWidget(page)

    def _build_page_pipe_ports(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("管道输入/输出端口列表"))
        self.pipe_ports_tbl = self._mk_table(["方向(in/out)", "端口名", "注释", "数据类型(线束名)"])
        lay.addWidget(self._wrap_table_with_add_del(self.pipe_ports_tbl, "新增端口", "删除选中"), 1)

        self.pages.addWidget(page)

    def _build_page_submodules(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("模块子实例列表"))
        self.submod_tbl = self._mk_table(["实例名", "所属模块", "注释", "本地配置覆盖列表(JSON)"])
        lay.addWidget(self._wrap_table_with_add_del(self.submod_tbl, "新增模块实例", "删除选中"), 1)

        self.pages.addWidget(page)

    def _build_page_pipes(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("管道子实例列表"))
        self.pipe_inst_tbl = self._mk_table([
            "实例名", "注释", "数据类型(线束名)",
            "输入尺寸(表达式)", "输出尺寸(表达式)", "缓冲区大小(表达式)", "延迟(表达式)",
            "包含握手(true/false)", "包含有效标志(true/false)"
        ])
        lay.addWidget(self._wrap_table_with_add_del(self.pipe_inst_tbl, "新增管道实例", "删除选中"), 1)

        self.pages.addWidget(page)

    def _build_page_storages(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel("存储/周期延迟存储/周期临时存储列表"))
        self.storage_tbl = self._mk_table([
            "类别(storage/cycle_delay/cycle_tmp)",
            "成员名", "成员类型(线束名)", "整数长度(表达式)", "注释", "默认值(表达式)", "维度(表达式数组)"
        ])
        lay.addWidget(self._wrap_table_with_add_del(self.storage_tbl, "新增存储成员", "删除选中"), 1)

        self.pages.addWidget(page)

    # =========================
    # Load / Save（✅ 去掉隐藏模块对应字段）
    # =========================
    def _load(self, data: dict):
        # basic
        self.name_edit.setText(data.get("name", ""))
        self.comment_edit.setText(data.get("comment", ""))

        # local_cfg
        self._rows_to_table(self.local_cfg_tbl, ["name", "default", "comment"], data.get("local_cfgs", []))
        # local_harness
        self._rows_to_table(self.local_harness_tbl, ["name", "comment", "mode", "body"], data.get("local_harnesses", []))
        # rpc
        self._rows_to_table(self.rpc_tbl, ["kind", "name", "comment", "params", "returns", "handshake"], data.get("rpcs", []))
        # pipe ports
        self._rows_to_table(self.pipe_ports_tbl, ["dir", "name", "comment", "dtype"], data.get("pipe_ports", []))
        # sub modules
        self._rows_to_table(self.submod_tbl, ["inst", "module", "comment", "cfg_overrides"], data.get("submodules", []))
        # pipes
        self._rows_to_table(
            self.pipe_inst_tbl,
            ["inst", "comment", "dtype", "in_size", "out_size", "buf", "latency", "handshake", "valid"],
            data.get("pipes", [])
        )
        # storage
        self._rows_to_table(
            self.storage_tbl,
            ["kind", "name", "type", "int_len", "comment", "default", "dims"],
            data.get("storages", [])
        )

    def _on_ok(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入无效", "模块名不能为空。")
            self.sidebar.setCurrentRow(self.PAGE_BASIC)
            return

        # 存储成员：type vs int_len 互斥（基本校验）
        storages = self._table_to_rows(self.storage_tbl, ["kind", "name", "type", "int_len", "comment", "default", "dims"])
        for s in storages:
            if s.get("type") and s.get("int_len"):
                QMessageBox.warning(self, "输入无效", f"存储成员“{s.get('name','(未命名)')}”：成员类型 与 整数长度 互斥，请只填一个。")
                self.sidebar.setCurrentRow(self.PAGE_STORAGES)
                return

        # ✅ 输出也去掉隐藏模块相关数据字段
        self._result = {
            "name": name,
            "comment": self.comment_edit.text().strip(),

            "local_cfgs": self._table_to_rows(self.local_cfg_tbl, ["name", "default", "comment"]),
            "local_harnesses": self._table_to_rows(self.local_harness_tbl, ["name", "comment", "mode", "body"]),
            "rpcs": self._table_to_rows(self.rpc_tbl, ["kind", "name", "comment", "params", "returns", "handshake"]),
            "pipe_ports": self._table_to_rows(self.pipe_ports_tbl, ["dir", "name", "comment", "dtype"]),

            "submodules": self._table_to_rows(self.submod_tbl, ["inst", "module", "comment", "cfg_overrides"]),
            "pipes": self._table_to_rows(self.pipe_inst_tbl, ["inst", "comment", "dtype", "in_size", "out_size", "buf", "latency", "handshake", "valid"]),
            "storages": storages,
        }
        self.accept()

    def get_data(self) -> dict:
        return getattr(self, "_result", {})
