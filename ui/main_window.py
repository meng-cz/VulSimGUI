# ui/main_window.py
from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from pathlib import Path
from PyQt6.QtCore import QThread
from service.vulsim_tcp import VulSimControlClient, VulSimLogClient, _json_dumps
from service.frontend_store import FrontendStore
from widgets.explorer_dock import ExplorerDock
from widgets.history_dock import HistoryDock
from widgets.bottom_panel import BottomPanel
# from widgets.module_canvas import ModuleCanvas
from widgets.module_canvas_page import ModuleCanvasPage, BaseNodeItem
from widgets.code_block_editor_page import CodeBlockEditorPage
from widgets.config_relation_page import ConfigRelationPage
from widgets.harness_detail_page import HarnessDetailPage
from widgets.settings_dialogs import PreferencesDialog, ThemeDialog, ShortcutsDialog
from service.vulsim_tcp import Arg

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QEvent, QSettings, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QTabWidget, QWidget, QToolBar, QStatusBar,
    QToolButton, QMenu, QTabBar, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy, QPushButton,
    QInputDialog, QMessageBox, QFileDialog, QLineEdit, QTextEdit, QPlainTextEdit
)


def _safe_list(value):
    return value if isinstance(value, list) else []


def _strip_text(value: str) -> str:
    return (value or "").strip()


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# ==========================================================
# 监控线程：修改后 - 只要有返回就算连接成功
# ==========================================================
class ConnectionMonitor(QThread):
    # 定义信号：连接状态(True/False), 提示文字
    status_changed = pyqtSignal(bool, str)
    project_updated = pyqtSignal(object)  # 传递项目名或 None

    def __init__(self, client: VulSimControlClient, lock: threading.Lock):
        super().__init__()
        self.client = client
        self.lock = lock  # 接收共享锁
        self._running = True
        self.fail_count = 0
        self.base_interval = 5  # 基础检查间隔（秒）

    def run(self):
        while self._running:
            # 使用锁防止与主线程初始化冲突
            with self.lock:
                try:
                    resp = self.client.call("info", [])
                    # 【核心修改】：只要 resp 是字典，说明网络通了，不需要 code==0
                    if isinstance(resp, dict):
                        self.fail_count = 0
                        self.status_changed.emit(True, "已连接")

                        # 单独判断项目名称逻辑
                        code = resp.get("code")
                        if code == 0:
                            # 只有 code=0 才有项目名
                            p_name = resp.get("results").get("name")
                            self.project_updated.emit(p_name)
                        else:
                            # 其它 code (如 -11 或错误码) 视为连接正常但无项目/状态异常
                            # 此时传 None 给 UI，让 UI 显示“当前无已打开项目”
                            self.project_updated.emit(None)

                        success = True
                    else:
                        # 如果返回 None 或非字典，视为逻辑上的连接失败
                        raise ConnectionError("Empty response")
                except Exception:
                    success = False

            if success:
                time.sleep(self.base_interval)
            else:
                self.fail_count += 1
                if self.fail_count <= 3:
                    wait_time = self.base_interval
                    msg = f"已断开，正在重试 ({self.fail_count}/3)..."
                else:
                    wait_time = min(self.base_interval * (2 ** (self.fail_count - 3)), 60)
                    msg = f"连接断开，{wait_time}秒后再次尝试..."

                self.status_changed.emit(False, msg)
                self.project_updated.emit(None)
                time.sleep(wait_time)

    def stop(self):
        self._running = False

# -----------------------------
# 1) 可右键的 TabBar
# -----------------------------
class ContextTabBar(QTabBar):
    floatRequested = pyqtSignal(int)   # index
    stickRequested = pyqtSignal(int)   # index
    closeRequested = pyqtSignal(int)   # index

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        # 记录每个 index 对应的关闭按钮，便于移动/删除时维护
        self._close_btns: dict[int, QToolButton] = {}

        # tab 结构变化时重建/刷新按钮位置
        self.tabMoved.connect(lambda _from, _to: self._rebuild_close_buttons())
        self.currentChanged.connect(lambda _i: self._reposition_close_buttons())

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, event):
        idx = self.tabAt(event.pos())
        if idx < 0:
            return

        menu = QMenu(self)
        act_float = QAction("Float（悬浮）", self)
        act_stick = QAction("Stick（贴回）", self)
        act_close = QAction("关闭", self)

        act_float.triggered.connect(lambda: self.floatRequested.emit(idx))
        act_stick.triggered.connect(lambda: self.stickRequested.emit(idx))
        act_close.triggered.connect(lambda: self.closeRequested.emit(idx))

        menu.addAction(act_float)
        menu.addAction(act_stick)
        menu.addSeparator()
        menu.addAction(act_close)
        menu.exec(event.globalPos())

    # ---------- 关闭按钮（最右侧） ----------
    def ensure_close_button(self, index: int):
        """
        给指定 tab index 安装一个最右侧的关闭按钮。
        """
        if index in self._close_btns:
            self._reposition_close_buttons()
            return

        btn = QToolButton(self)
        btn.setText("×")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoRaise(True)
        btn.setToolTip("关闭")
        btn.setFixedSize(18, 18)

        # 注意：index 会变化（tab 移动/关闭），这里不能直接 capture index 常量
        btn.clicked.connect(lambda: self._emit_close_for_button(btn))

        self._close_btns[index] = btn
        btn.show()
        self._reposition_close_buttons()

    def remove_close_button(self, index: int):
        btn = self._close_btns.pop(index, None)
        if btn is not None:
            btn.hide()
            btn.deleteLater()
        self._rebuild_close_buttons()

    def _emit_close_for_button(self, btn: QToolButton):
        # 通过按钮当前位置反查属于哪个 tab
        pos = btn.mapTo(self, btn.rect().center())
        idx = self.tabAt(pos)
        if idx >= 0:
            self.closeRequested.emit(idx)

    # ---------- 维护按钮位置 ----------
    def _rebuild_close_buttons(self):
        """
        tab 的 index 变动后，重新构建 index->button 映射。
        这里采取“全部重算”的方式更稳定。
        """
        # 先拿到现有按钮对象
        existing = list(self._close_btns.values())
        self._close_btns.clear()

        # 按当前 tab 数量重新绑定
        for i in range(self.count()):
            # 复用旧按钮（如果够用），否则新建
            btn = existing.pop(0) if existing else None
            if btn is None:
                btn = QToolButton(self)
                btn.setText("×")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setAutoRaise(True)
                btn.setToolTip("关闭")
                btn.setFixedSize(18, 18)
                btn.clicked.connect(lambda _=False, b=btn: self._emit_close_for_button(b))
            btn.setParent(self)
            btn.show()
            self._close_btns[i] = btn

        # 多余按钮销毁
        for btn in existing:
            btn.hide()
            btn.deleteLater()

        self._reposition_close_buttons()

    def _reposition_close_buttons(self):
        """
        把每个 tab 的关闭按钮放到“页签最右边”。
        """
        for i, btn in self._close_btns.items():
            if i < 0 or i >= self.count():
                continue
            r = self.tabRect(i)
            # 放在 tabRect 右侧稍偏内的位置
            x = r.right() - btn.width() - 6
            y = r.center().y() - btn.height() // 2
            btn.move(x, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_close_buttons()

# -----------------------------
# 2) 浮动窗口的自定义标题栏
#    - 最大化/还原互斥
# -----------------------------
class FloatingTitleBar(QWidget):
    minimizeClicked = pyqtSignal()
    maximizeClicked = pyqtSignal()
    restoreClicked = pyqtSignal()
    closeClicked = pyqtSignal()
    stickClicked = pyqtSignal()

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)

        self._title = QLabel(title)
        self._title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # 贴回按钮（建议提供，否则浮动后无法从主 tab 右键 stick）
        self._btn_stick = QPushButton("Stick")
        self._btn_min = QPushButton("—")
        self._btn_max = QPushButton("□")
        self._btn_restore = QPushButton("❐")
        self._btn_close = QPushButton("×")

        # 互斥：默认显示 Max，不显示 Restore
        self._btn_restore.hide()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)
        lay.addWidget(self._title)
        lay.addWidget(self._btn_stick)
        lay.addWidget(self._btn_min)
        lay.addWidget(self._btn_max)
        lay.addWidget(self._btn_restore)
        lay.addWidget(self._btn_close)

        self._btn_stick.clicked.connect(self.stickClicked.emit)
        self._btn_min.clicked.connect(self.minimizeClicked.emit)
        self._btn_max.clicked.connect(self.maximizeClicked.emit)
        self._btn_restore.clicked.connect(self.restoreClicked.emit)
        self._btn_close.clicked.connect(self.closeClicked.emit)

        # 可拖动窗口（简单实现）
        self._drag_pos: QPoint | None = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_stick = menu.addAction("Stick（贴回）")
        act_close = menu.addAction("关闭")

        act = menu.exec(event.globalPos())
        if act == act_stick:
            self.stickClicked.emit()
        elif act == act_close:
            self.closeClicked.emit()

    def setTitle(self, t: str):
        self._title.setText(t)

    def setMaximizedState(self, maximized: bool):
        # 最大化/还原按钮互斥
        self._btn_max.setVisible(not maximized)
        self._btn_restore.setVisible(maximized)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            w = self.window()
            delta = e.globalPosition().toPoint() - self._drag_pos
            w.move(w.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        e.accept()


# -----------------------------
# 3) 承载“被拆出来 tab 页”的浮动窗口
# -----------------------------
class FloatingTabWindow(QMainWindow):
    """
    用一个独立窗口承载被 float 出来的 tab widget.
    提供：最大化/还原(互斥)、最小化、关闭、Stick(贴回)
    """

    def __init__(self, title: str, content: QWidget, on_stick, on_close, parent=None):
        super().__init__(parent)
        self._content = content
        self._on_stick = on_stick
        self._on_close = on_close

        # 用 Frameless + 自定义标题栏，按钮可控
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
        )

        self._titlebar = FloatingTitleBar(title, self)
        self._titlebar.minimizeClicked.connect(self.showMinimized)
        self._titlebar.maximizeClicked.connect(self._do_maximize)
        self._titlebar.restoreClicked.connect(self._do_restore)
        self._titlebar.closeClicked.connect(self.close)
        self._titlebar.stickClicked.connect(self._stick_back)

        # 把 titlebar 放到一个顶部工具栏区域（简单且稳定）
        tb = QToolBar()
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.addWidget(self._titlebar)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # 用容器 + layout 托住 content，避免浮动后尺寸/布局没接管导致画布空白
        central = QWidget(self)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._content)

        self.setCentralWidget(central)

        # 触发一次布局和重绘（对 GraphicsView/自绘画布很关键）
        self._content.show()
        self._content.update()

        self.setWindowTitle(title)

        self.resize(1000, 700)
        self._sync_buttons()

    def _sync_buttons(self):
        maximized = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        self._titlebar.setMaximizedState(maximized)

    def _do_maximize(self):
        self.showMaximized()
        self._sync_buttons()

    def _do_restore(self):
        self.showNormal()
        self._sync_buttons()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange:
            self._sync_buttons()

    def _stick_back(self):
        # 把 widget 交还给 MainWindow
        self._on_stick(self._content, self.windowTitle())
        # 关闭浮窗（不 delete widget）
        self._content = None
        self.close()

    def closeEvent(self, e):
        # 用户点“关闭”或窗口关闭：等价于关闭 tab（deleteLater）
        if self._content is not None:
            self._on_close(self._content, self.windowTitle())
            self._content = None
        super().closeEvent(e)


class MainWindow(QMainWindow):
    backendLogArrived = pyqtSignal(dict)
    backendLogErrorArrived = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HYPER-IDE")
        self.resize(1400, 900)

        # === 1. 先初始化所有底层通讯实例 ===
        self.control = VulSimControlClient(host="211.87.236.13", port=17995, endian="<")
        self.info_lock = threading.Lock()  # 创建逻辑锁
        self.frontend_only = os.getenv("VULSIM_FRONTEND_ONLY", "1").strip().lower() not in {"0", "false", "no"}
        self.frontend_store = FrontendStore()
        self._frontend_project_name = self.frontend_store.project_name
        self.settings = QSettings("VulSim", "HyperIDE")
        self.ui_preferences = self._load_ui_preferences()
        self._theme_name = str(self.settings.value("ui/theme_name", "dark") or "dark")
        self._shortcuts: list[QShortcut] = []
        self._shortcut_specs = self._build_shortcut_specs()
        self.log_client = VulSimLogClient(
            host="211.87.236.13",
            port=17996,
            endian="<",
            on_log=self._on_backend_log,
            on_error=self._on_backend_log_error,
        )

        # === 2. 初始化所有 UI 变量（防止 AttributeError） ===
        # 顶部项目标签
        self.project_label = QLabel("当前无已打开项目")
        self.project_label.setStyleSheet("margin-right: 15px; color: #666; font-weight: bold;")
        self.ui_state_label = QLabel("界面状态: 空闲")
        self.ui_state_label.setStyleSheet("margin-right: 12px; color: #64748b;")

        # 状态栏右侧连接状态标签
        self.conn_status_label = QLabel("正在连接...")
        self._current_project_name: str | None = None
        self._is_connected: bool = False
        self._ui_state: str = "idle"
        self._frontend_build_info: dict | None = None
        self._frontend_run_active: bool = False
        self._frontend_run_stream_timer = QTimer(self)
        self._frontend_run_stream_timer.setInterval(320)
        self._frontend_run_stream_timer.timeout.connect(self._flush_frontend_run_stream)
        self._frontend_run_stream_queue: list[str] = []

        # 浮动窗口字典
        self._floating_windows: dict[QWidget, FloatingTabWindow] = {}
        self._history_recording_suspended = True
        self._history_restore_in_progress = False
        self._history_state_cache: dict | None = None
        self._pending_module_history_entry: tuple[str, dict] | None = None
        self.backendLogArrived.connect(self._handle_backend_log)
        self.backendLogErrorArrived.connect(self._handle_backend_log_error)

        # === 3. 执行 UI 布局（现在调用这个方法是安全的） ===
        self._init_top_toolbar()

        # 中央：主标签页
        self.center_tabs = QTabWidget()
        self.center_tabs.setTabsClosable(True)
        self.center_tabs.setMovable(True)
        self.center_tabs.tabCloseRequested.connect(self._close_center_tab)
        self.setCentralWidget(self.center_tabs)

        tabbar = ContextTabBar(self.center_tabs)
        tabbar.floatRequested.connect(self._float_center_tab)
        tabbar.stickRequested.connect(self._stick_center_tab)
        tabbar.closeRequested.connect(self._close_center_tab)
        self.center_tabs.setTabBar(tabbar)

        # Docks
        self.explorer = ExplorerDock()
        self._add_dock(self.explorer, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.explorer.openConfigRequested.connect(self.open_config_relation_tab)
        self.explorer.openHarnessRequested.connect(self.open_harness_detail_tab)
        self.explorer.openModuleRequested.connect(self.open_module_canvas_tab)
        self.explorer.moduleLibraryChanged.connect(self._on_module_library_changed)
        self.explorer.mainModuleChanged.connect(self._on_main_module_changed)
        self.explorer.addDebugRequested.connect(self.on_add_debug_request)
        self.explorer.updateDebugRequested.connect(self.on_update_debug_request)
        self.explorer.removeDebugRequested.connect(self.on_remove_debug_request)

        # 【连接】连接添加配置的请求信号
        self.explorer.addConfigRequested.connect(self.on_add_config_request)
        # 【连接】连接删除配置的请求信号
        self.explorer.removeConfigRequested.connect(self.on_remove_config_request)
        # 【连接】连接update配置的请求信号
        self.explorer.updateConfigRequested.connect(self.on_update_config_request)
        # 【连接】连接注释配置的请求信号
        self.explorer.commentConfigRequested.connect(self.on_comment_config_request)
        # 【连接】连接重命名配置的请求信号
        self.explorer.renameConfigRequested.connect(self.on_rename_config_request)
        # 【连接】回传引用list的配置的请求信号
        self.explorer.listRefRequested.connect(self.on_listref_request)

        # 线束
        ## 【连接】
        self.explorer.addHarnessRequested.connect(self.on_add_harness_request)
        self.explorer.updateHarnessRequested.connect(self.on_update_harness_request)
        self.explorer.removeHarnessRequested.connect(self.on_remove_harness_request)

        self.history = HistoryDock()
        self.history.set_apply_callback(self._restore_frontend_history_state)
        self._add_dock(self.history, Qt.DockWidgetArea.RightDockWidgetArea)

        self.bottom = BottomPanel()
        self.bottom.terminalRunRequested.connect(self.on_run_terminal_script)
        self._add_dock(self.bottom, Qt.DockWidgetArea.BottomDockWidgetArea)
        self._apply_ui_preferences()
        self._install_shortcuts()
        self._apply_theme(self._theme_name, persist=False)

        # 状态栏
        self.setStatusBar(QStatusBar())
        self.statusBar().addPermanentWidget(self.ui_state_label)
        self.statusBar().addPermanentWidget(self.conn_status_label)  # 将预先定义好的标签放入状态栏

        # === 4. 启动后台逻辑与线程 ===
        # default_name = "Core_Logic"
        # default_data = self._get_module_data_or_stub(default_name)
        # page = self._make_module_canvas_page(default_name, default_data)
        # self.center_tabs.addTab(page, f"{default_name} (Canvas)")
        # self.center_tabs.setCurrentWidget(page)
        #
        # self.monitor = ConnectionMonitor(self.control)
        # self.monitor.status_changed.connect(self._update_conn_ui)
        # self.monitor.start()

        if self.frontend_only:
            self._update_conn_ui(True, "前端开发模式")
            self.update_project_display(self._frontend_project_name)
        else:
            self.monitor = ConnectionMonitor(self.control, self.info_lock)
            self.monitor.status_changed.connect(self._update_conn_ui)
            self.monitor.project_updated.connect(self.update_project_display)
            self.monitor.start()

            # 最后检查初始项目状态
            self.check_initial_project_status()

        self._history_recording_suspended = False
        self._reset_frontend_history()

    def on_update_config_request(self, name: str, value: str):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.update_config(name, value)
                self.statusBar().showMessage(f"配置项 '{name}' 更新成功。", 3000)
                self.refresh_project_data()
                self._refresh_open_detail_pages()
                self._record_frontend_history("编辑配置项", {"name": name, "field": "value"}, before_state=before_state)
            except ValueError as e:
                QMessageBox.warning(self, "更新失败", str(e))
            return

        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法更新配置。")
            return
        try:
            args = [
                Arg(index=0, name="name", value=name),
                Arg(index=1, name="value", value=value),
            ]
            resp = self.control.call("configlib.update", args)
            self.bottom.output.append(f"[Request: configlib.update] Name: {name}, Result: {_json_dumps(resp)}\n")

            if resp.get("code") == 0:
                self.statusBar().showMessage(f"配置项 '{name}' 更新成功。", 3000)
                self.refresh_project_data()
            else:
                QMessageBox.warning(self, "更新失败", f"服务器返回错误：\n{resp.get('msg', '未知错误')}")
        except Exception as e:
            self.bottom.logs.append(f"[Critical Error] Failed to execute 'configlib.update': {e}\n")
            QMessageBox.critical(self, "通讯错误", "无法连接到服务器。")

    def on_comment_config_request(self, name: str, comment: str):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.comment_config(name, comment)
                self.statusBar().showMessage(f"配置项 '{name}' 注释更新成功。", 3000)
                self.refresh_project_data()
                self._refresh_open_detail_pages()
                self._record_frontend_history("修改配置注释", {"name": name}, before_state=before_state)
            except ValueError as e:
                QMessageBox.warning(self, "修改注释失败", str(e))
            return

        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法修改注释。")
            return
        try:
            args = [Arg(index=0, name="name", value=name)]
            # comment 允许留空表示清空注释，这里传空字符串即可
            args.append(Arg(index=1, name="comment", value=comment))

            resp = self.control.call("configlib.comment", args)
            self.bottom.output.append(f"[Request: configlib.comment] Name: {name}, Result: {_json_dumps(resp)}\n")

            if resp.get("code") == 0:
                self.statusBar().showMessage(f"配置项 '{name}' 注释更新成功。", 3000)
                self.refresh_project_data()
            else:
                QMessageBox.warning(self, "修改注释失败", f"服务器返回错误：\n{resp.get('msg', '未知错误')}")
        except Exception as e:
            self.bottom.logs.append(f"[Critical Error] Failed to execute 'configlib.comment': {e}\n")
            QMessageBox.critical(self, "通讯错误", "无法连接到服务器。")

    def on_listref_request(self, name: str):
        if self.frontend_only:
            try:
                forward = self.frontend_store.list_config_refs(name, reverse=False)
                reverse = self.frontend_store.list_config_refs(name, reverse=True)
                self.explorer.listRefResult.emit(name, forward, reverse, "")
            except ValueError as e:
                self.explorer.listRefResult.emit(name, {}, {}, str(e))
            return

        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法查看引用。")
            self.explorer.listRefResult.emit(name, {}, {}, "当前未打开项目")
            return

        try:
            # forward
            args_f = [Arg(index=0, name="name", value=name)]
            resp_f = self.control.call("configlib.listref", args_f)
            self.bottom.output.append(f"[Request: configlib.listref] Name: {name}, Result: {_json_dumps(resp_f)}\n")

            if resp_f.get("code") != 0:
                self.explorer.listRefResult.emit(name, {}, {}, resp_f.get("msg", "未知错误"))
                return

            forward = resp_f.get("list_results", {}) or {
                "names": resp_f.get("names", []),
                "childs": resp_f.get("childs", []),
                "values": resp_f.get("values", []),
                "realvalues": resp_f.get("realvalues", []),
            }

            # reverse
            args_r = [
                Arg(index=0, name="name", value=name),
                Arg(index=1, name="reverse", value="true"),
            ]
            resp_r = self.control.call("configlib.listref", args_r)
            self.bottom.output.append(
                f"[Request: configlib.listref reverse] Name: {name}, Result: {_json_dumps(resp_r)}\n")

            if resp_r.get("code") != 0:
                self.explorer.listRefResult.emit(name, forward, {}, resp_r.get("msg", "未知错误"))
                return

            reverse = resp_r.get("list_results", {}) or {
                "names": resp_r.get("names", []),
                "childs": resp_r.get("childs", []),
                "values": resp_r.get("values", []),
                "realvalues": resp_r.get("realvalues", []),
            }

            self.explorer.listRefResult.emit(name, forward, reverse, "")
        except Exception as e:
            self.bottom.logs.append(f"[Critical Error] Failed to execute 'configlib.listref': {e}\n")
            self.explorer.listRefResult.emit(name, {}, {}, "通讯错误")

    def on_rename_config_request(self, old_name: str, new_name: str, old_value: str, old_comment: str):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.rename_config(old_name, new_name, old_value, old_comment)
                self.statusBar().showMessage(f"已重命名：{old_name} → {new_name}", 3000)
                self.refresh_project_data()
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self._refresh_open_detail_pages()
                self._record_frontend_history(
                    "重命名配置项",
                    {"old_name": old_name, "new_name": new_name},
                    before_state=before_state,
                )
            except ValueError as e:
                QMessageBox.warning(self, "重命名失败", str(e))
            return

        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法重命名配置。")
            return

        try:
            # 1) add new
            args_add = [
                Arg(index=0, name="name", value=new_name),
                Arg(index=1, name="value", value=old_value),
                Arg(index=2, name="comment", value=old_comment),
            ]
            resp_add = self.control.call("configlib.add", args_add)
            self.bottom.output.append(
                f"[Request: configlib.add(rename)] New: {new_name}, Result: {_json_dumps(resp_add)}\n")

            if resp_add.get("code") != 0:
                QMessageBox.warning(self, "重命名失败", f"创建新名称失败：\n{resp_add.get('msg', '未知错误')}")
                return

            # 2) remove old
            args_rm = [Arg(index=0, name="name", value=old_name)]
            resp_rm = self.control.call("configlib.remove", args_rm)
            self.bottom.output.append(
                f"[Request: configlib.remove(rename)] Old: {old_name}, Result: {_json_dumps(resp_rm)}\n")

            if resp_rm.get("code") != 0:
                # rollback：删掉 new
                args_rb = [Arg(index=0, name="name", value=new_name)]
                resp_rb = self.control.call("configlib.remove", args_rb)
                self.bottom.output.append(
                    f"[Rollback: configlib.remove] New: {new_name}, Result: {_json_dumps(resp_rb)}\n")
                QMessageBox.warning(self, "重命名失败",
                                    f"删除旧名称失败：\n{resp_rm.get('msg', '未知错误')}\n\n已回滚新名称。")
                return

            self.statusBar().showMessage(f"已重命名：{old_name} → {new_name}", 3000)
            self.refresh_project_data()

        except Exception as e:
            self.bottom.logs.append(f"[Critical Error] Failed to rename config: {e}\n")
            QMessageBox.critical(self, "通讯错误", "无法连接到服务器。")

    def on_remove_config_request(self, names: list[str]):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            success, failed = self.frontend_store.remove_configs(names or [])
            self.explorer.removeConfigResult.emit(success, failed)
            if success:
                self.refresh_project_data()
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self._refresh_open_detail_pages()
                self._record_frontend_history(
                    "删除配置项",
                    {"names": success, "failed": [name for name, _msg in failed]},
                    before_state=before_state,
                )
            if success and not failed:
                self.statusBar().showMessage(f"已删除 {len(success)} 个配置项。", 3000)
            return

        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法删除配置。")
            # 回推空结果，解除 Explorer 锁
            self.explorer.removeConfigResult.emit([], [(n, "当前未打开项目") for n in (names or [])])
            return

        if not names:
            self.explorer.removeConfigResult.emit([], [])
            return

        failed: list[tuple[str, str]] = []
        success: list[str] = []

        try:
            for name in names:
                args = [Arg(index=0, name="name", value=name)]
                resp = self.control.call("configlib.remove", args)

                res_str = _json_dumps(resp)
                self.bottom.output.append(f"[Request: configlib.remove] Name: {name}, Result: {res_str}\n")

                if resp.get("code") == 0:
                    success.append(name)
                else:
                    msg = resp.get("msg", "未知错误")
                    failed.append((name, msg))

            # ✅ 回推给 ExplorerDock，让其移除成功项、保留失败项并提示
            self.explorer.removeConfigResult.emit(success, failed)

            # 可选：如果你更想保证“权威来自后端”，可再 refresh 一次
            # 但注意：refresh 会重建树，可能会让失败项的勾选状态丢失
            # 所以推荐：只在需要时 refresh，比如成功项较多或后端可能隐式改名/联动
            # self.refresh_project_data()
            if success:
                self.refresh_project_data()
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)

            if success and not failed:
                self.statusBar().showMessage(f"已删除 {len(success)} 个配置项。", 3000)

        except Exception as e:
            error_msg = f"[Critical Error] Failed to execute 'configlib.remove': {str(e)}"
            print(error_msg)
            self.bottom.logs.append(error_msg + "\n")
            QMessageBox.critical(self, "通讯错误", "无法连接到服务器。")

            # 回推“全部失败”，解除 Explorer 锁
            self.explorer.removeConfigResult.emit([], [(n, "通讯错误") for n in names])

    def _apply_cfg_remove_result(self, success_names: list[str], failed: list[tuple[str, str]]):
        """
        MainWindow 删除后回调这里：
        - 成功：从树里移除
        - 失败：保留勾选并提示原因（可选高亮）
        - 全部成功：退出删除模式
        - 有失败：保持删除模式，方便继续操作
        """
        # 解除锁定
        self._lock_cfg_delete_ui(False)

        # 1) 先清理“高亮状态”（可选）
        #    用前景色/背景色做失败高亮
        for it in self._iter_cfg_items():
            it.setForeground(0, Qt.GlobalColor.black)
            it.setBackground(0, Qt.GlobalColor.transparent)

        failed_map = {n: m for n, m in (failed or [])}

        # 2) 成功项：从树中移除
        #    注意：删除 topLevelItem 时要倒序删除，避免 index 变化
        to_remove_indices = []
        for i in range(self.global_cfg.topLevelItemCount()):
            it = self.global_cfg.topLevelItem(i)
            if it and it.text(0) in success_names:
                to_remove_indices.append(i)
        for idx in reversed(to_remove_indices):
            self.global_cfg.takeTopLevelItem(idx)

        # 3) 失败项：保留勾选 + 高亮 + tooltip 追加失败原因
        if failed_map:
            for it in self._iter_cfg_items():
                n = it.text(0)
                if n in failed_map:
                    it.setCheckState(0, Qt.CheckState.Checked)  # 保持勾选
                    it.setForeground(0, Qt.GlobalColor.red)
                    it.setBackground(0, Qt.GlobalColor.transparent)
                    old_tip = it.toolTip(0) or ""
                    it.setToolTip(0, f"{old_tip}\n\n[删除失败] {failed_map[n]}".strip())

            # 弹窗汇总失败原因
            fail_text = "\n".join([f"- {n}: {m}" for n, m in failed])
            QMessageBox.warning(
                self,
                "删除失败（部分）",
                f"以下配置项删除失败：\n\n{fail_text}\n\n"
                "常见原因：配置项被引用或来自导入库。"
            )
            # ✅ 有失败：不退出删除模式
            return

        # 4) 全部成功：退出删除模式
        self._exit_cfg_delete_mode()

    # 处理添加配置请求
    def on_add_config_request(self, name: str, value: str, comment: str):
        """
        响应 ExplorerDock 的添加配置请求，调用后端 configlib.add 接口
        """
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.add_config(name, value, comment)
                self.statusBar().showMessage(f"配置项 '{name}' 添加成功。", 3000)
                self.refresh_project_data()
                self._refresh_open_detail_pages()
                self._record_frontend_history("新增配置项", {"name": name}, before_state=before_state)
            except ValueError as e:
                QMessageBox.warning(self, "添加失败", str(e))
            return

        # 1. 检查是否有打开的项目 (可选，依赖后端返回也可以，但前端拦一下更友好)
        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法添加配置。")
            return

        print(f"正在请求添加配置: name={name}, value={value}, comment={comment}")

        try:
            # 2. 构造参数
            # configlib.add(name, value, comment)
            args = [
                Arg(index=0, name="name", value=name),
                Arg(index=1, name="value", value=value),
                Arg(index=2, name="comment", value=comment)
            ]

            # 3. 调用接口
            resp = self.control.call("configlib.add", args)

            # 记录日志
            res_str = _json_dumps(resp)
            self.bottom.output.append(f"[Request: configlib.add] Name: {name}, Result: {res_str}\n")

            # 4. 处理结果
            if resp.get("code") == 0:
                self.statusBar().showMessage(f"配置项 '{name}' 添加成功。", 3000)
                # 成功后，刷新整个配置列表以同步最新状态
                self.refresh_project_data()
            else:
                # 处理错误码
                msg = resp.get("msg", "未知错误")
                # 可以根据具体的 Error Code 做更细致的提示，这里直接显示后端 msg
                QMessageBox.warning(self, "添加失败", f"服务器返回错误：\n{msg}")

        except Exception as e:
            error_msg = f"[Critical Error] Failed to execute 'configlib.add': {str(e)}"
            print(error_msg)
            self.bottom.logs.append(error_msg + "\n")
            QMessageBox.critical(self, "通讯错误", "无法连接到服务器。")

    # 处理添加线束请求
    def on_add_harness_request(self, name: str, comment: str, definition: str, ui_data: dict):
        """
        响应 ExplorerDock 的新增线束(bundle)请求，调用后端 bundlelib.add
        接口参数顺序：
          - name
          - comment (可选)
          - definition (可选, VulBundleItem JSON string)
        """
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.add_bundle(name, comment, definition)
                self.statusBar().showMessage(f"线束 '{name}' 添加成功。", 3000)
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self._refresh_open_detail_pages()
                self._record_frontend_history("新增线组", {"name": name}, before_state=before_state)
            except ValueError as e:
                QMessageBox.warning(self, "添加线束失败", str(e))
            return

        print(f"[线束] [add] ：name is :{name}, comment is :{comment}, definition is :{definition}")
        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法添加线束。")
            return

        try:
            args = [
                Arg(index=-1, name="name", value=name),
                Arg(index=-1, name="comment", value=comment if comment else ""),
                Arg(index=-1, name="definition", value=definition if definition else "")
            ]

            print(f"[线束][add] 发送数据: {[(a.name, a.index, a.value) for a in args]}")

            resp = self.control.call("bundlelib.add", args)
            self.bottom.output.append(f"[Request: bundlelib.add] Name: {name}, Result: {_json_dumps(resp)}\n")

            if resp.get("code") == 0:
                self.statusBar().showMessage(f"线束 '{name}' 添加成功。", 3000)

                try:
                    # self.explorer._add_harness_item(name, ui_data)
                    self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                    # 排序
                    self.explorer.global_harness.sortItems(0, Qt.SortOrder.AscendingOrder)
                except Exception:
                    pass

            else:
                msg = resp.get("msg", "未知错误")
                QMessageBox.warning(self, "添加线束失败", f"服务器返回错误：\n{msg}")

        except Exception as e:
            self.bottom.logs.append(f"[Critical Error] Failed to execute 'bundlelib.add': {e}\n")
            QMessageBox.critical(self, "通讯错误", "无法连接到服务器。")

    def on_update_harness_request(self, old_name: str, new_name: str, comment: str, definition: str, ui_data: dict):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.update_bundle(old_name, new_name, comment, definition)
                self.statusBar().showMessage(f"线束 '{new_name}' 更新成功。", 3000)
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self._refresh_open_detail_pages()
                self._record_frontend_history(
                    "编辑线组",
                    {"old_name": old_name, "new_name": new_name},
                    before_state=before_state,
                )
            except ValueError as e:
                QMessageBox.warning(self, "编辑线束失败", str(e))
            return

        applied = self.explorer.apply_harness_update(old_name, ui_data or {
            "name": new_name,
            "comment": comment,
            "members": [],
            "enums": [],
            "alias": False,
        })
        if not applied:
            QMessageBox.warning(self, "编辑线束失败", f"未找到线束“{old_name}”。")
            return

        self._refresh_open_detail_pages()
        self.statusBar().showMessage(f"线束 '{new_name}' 已更新到当前界面。", 3000)
        QMessageBox.information(self, "尚未对接", "当前版本的线束编辑尚未接入后端接口，已先更新当前界面。")

    def on_remove_harness_request(self, names: list[str]):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            success, failed = self.frontend_store.remove_bundles(names or [])
            self.refresh_project_bundle_data(include_reference=False, include_definition=True)
            if failed:
                detail = "\n".join(f"- {name}: {msg}" for name, msg in failed)
                QMessageBox.warning(self, "删除线束失败", detail)
            elif success:
                self.statusBar().showMessage(f"已删除 {len(success)} 个线束。", 3000)
            if success:
                self._refresh_open_detail_pages()
                self._record_frontend_history(
                    "删除线组",
                    {"names": success, "failed": [name for name, _msg in failed]},
                    before_state=before_state,
                )
            return

        removed = self.explorer.remove_harness_names(names or [])
        if not removed:
            QMessageBox.warning(self, "删除线束失败", "未找到需要删除的线束。")
            return

        self._refresh_open_detail_pages()
        self.statusBar().showMessage(f"已从当前界面删除 {len(removed)} 个线束。", 3000)
        QMessageBox.information(self, "尚未对接", "当前版本的线束删除尚未接入后端接口，已先更新当前界面。")

    def on_add_debug_request(self, data: dict):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.add_debug_point(data or {})
                self.refresh_project_debug_data()
                self.statusBar().showMessage(f"调试检查点 '{data.get('name', '')}' 添加成功。", 3000)
                self._record_frontend_history(
                    "新增调试检查点",
                    {"name": data.get("name", "")},
                    before_state=before_state,
                )
            except ValueError as e:
                QMessageBox.warning(self, "新增调试检查点失败", str(e))
            return

        QMessageBox.information(self, "尚未对接", "真实后端调试信息接口尚未接入。")

    def on_update_debug_request(self, old_name: str, data: dict):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            try:
                self.frontend_store.update_debug_point(old_name, data or {})
                self.refresh_project_debug_data()
                self.statusBar().showMessage(f"调试检查点 '{data.get('name', old_name)}' 更新成功。", 3000)
                self._record_frontend_history(
                    "编辑调试检查点",
                    {"old_name": old_name, "new_name": data.get("name", old_name)},
                    before_state=before_state,
                )
            except ValueError as e:
                QMessageBox.warning(self, "编辑调试检查点失败", str(e))
            return

        QMessageBox.information(self, "尚未对接", "真实后端调试信息接口尚未接入。")

    def on_remove_debug_request(self, names: list[str]):
        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            success, failed = self.frontend_store.remove_debug_points(names or [])
            self.refresh_project_debug_data()
            if failed:
                detail = "\n".join(f"- {name}: {msg}" for name, msg in failed)
                QMessageBox.warning(self, "删除调试检查点失败", detail)
            elif success:
                self.statusBar().showMessage(f"已删除 {len(success)} 个调试检查点。", 3000)
            if success:
                self._record_frontend_history(
                    "删除调试检查点",
                    {"names": success, "failed": [name for name, _msg in failed]},
                    before_state=before_state,
                )
            return

        QMessageBox.information(self, "尚未对接", "真实后端调试信息接口尚未接入。")

    def _on_backend_log(self, log: dict):
        self.backendLogArrived.emit(copy.deepcopy(log or {}))

    def _on_backend_log_error(self, e: Exception):
        self.backendLogErrorArrived.emit(str(e))

    def _handle_backend_log(self, log: dict):
        level = str(log.get("level", "") or "INFO")
        category = str(log.get("category", "") or "")
        message = str(log.get("message", "") or "")
        stream = str(log.get("stream", "") or "").lower()
        category_key = category.strip().lower()

        if stream == "out" or category_key in {"out", "stdout", "simulation", "simout"}:
            self._append_output_line(message.rstrip("\n"))
            self.bottom.set_output_status("接收后端实时输出中。")
            return

        txt = f"[{level}] [{category or 'backend'}] {message}\n"
        self.bottom.logs.append(txt)

    def _handle_backend_log_error(self, message: str):
        self.bottom.logs.append(f"[LogSocketError] {message}\n")

    def _close_center_tab(self, index: int):
        widget = self.center_tabs.widget(index)
        if widget is None:
            return

        # 如果该 widget 正在浮动窗口里，关闭应走浮动窗口逻辑
        # 但正常情况下：浮动后已 removeTab，不会触发这里。
        # 这里仍做防御：若在字典里，优先关闭浮动窗
        if widget in self._floating_windows:
            win = self._floating_windows.get(widget)
            if win is not None:
                win.close()
            return

        tb = self.center_tabs.tabBar()
        if isinstance(tb, ContextTabBar):
            tb.remove_close_button(index)

        self.center_tabs.removeTab(index)
        widget.deleteLater()

    def _add_center_tab(self, widget: QWidget, title: str):
        idx = self.center_tabs.addTab(widget, title)
        self.center_tabs.setCurrentIndex(idx)

        tb = self.center_tabs.tabBar()
        if isinstance(tb, ContextTabBar):
            tb.ensure_close_button(idx)

    def _iter_open_pages(self):
        seen: set[int] = set()
        for i in range(self.center_tabs.count()):
            widget = self.center_tabs.widget(i)
            if widget is None:
                continue
            seen.add(id(widget))
            yield widget

        for widget in list(self._floating_windows.keys()):
            if id(widget) not in seen:
                yield widget

    def _activate_page(self, widget: QWidget):
        if widget in self._floating_windows:
            win = self._floating_windows[widget]
            win.raise_()
            win.activateWindow()
            return

        idx = self.center_tabs.indexOf(widget)
        if idx >= 0:
            self.center_tabs.setCurrentIndex(idx)

    def _set_page_title(self, widget: QWidget, title: str):
        if widget in self._floating_windows:
            win = self._floating_windows.get(widget)
            if win is not None:
                win.setWindowTitle(title)
            return

        idx = self.center_tabs.indexOf(widget)
        if idx >= 0:
            self.center_tabs.setTabText(idx, title)

    def _close_page_widget(self, widget: QWidget):
        if widget in self._floating_windows:
            win = self._floating_windows.get(widget)
            if win is not None:
                win.close()
            return

        idx = self.center_tabs.indexOf(widget)
        if idx >= 0:
            self._close_center_tab(idx)

    def _close_all_project_pages(self):
        for widget in list(self._floating_windows.keys()):
            self._close_page_widget(widget)

        while self.center_tabs.count() > 0:
            self._close_center_tab(self.center_tabs.count() - 1)

    def _build_analysis_store(self) -> FrontendStore:
        if self.frontend_only:
            return self.frontend_store

        store = FrontendStore(project_name=self._current_project_name or "analysis", seed_demo=False)
        store.import_configs(self.explorer.get_config_snapshot())
        store.import_bundles(self.explorer.get_harness_snapshot())
        store.import_modules(self.explorer.export_modules())
        if hasattr(self.explorer, "get_debug_snapshot"):
            store.import_debug_points(self.explorer.get_debug_snapshot())
        return store

    def _capture_frontend_history_state(self) -> dict | None:
        if not self.frontend_only or not self._current_project_name:
            return None

        main_module_name = ""
        if hasattr(self.explorer, "get_main_module_name"):
            main_module_name = self.explorer.get_main_module_name() or ""

        return {
            "project_name": self.frontend_store.project_name,
            "configs": self.frontend_store.list_configs(),
            "bundles": self.frontend_store.list_bundles(),
            "modules": self.frontend_store.list_modules(),
            "debug_points": self.frontend_store.list_debug_points(),
            "main_module_name": main_module_name,
        }

    def _frontend_workspace_root(self) -> Path:
        root = Path(__file__).resolve().parents[1] / ".frontend_workspaces"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _frontend_workspace_safe_stem(self, name: str) -> str:
        safe = "".join(ch if (ch.isalnum() or ch in {"_", "-", "."}) else "_" for ch in (name or "").strip())
        safe = safe.strip("._")
        return safe or "workspace"

    def _frontend_workspace_path(self, name: str) -> Path:
        return self._frontend_workspace_root() / f"{self._frontend_workspace_safe_stem(name)}.json"

    def _list_frontend_workspace_names(self) -> list[str]:
        names: list[str] = []
        for path in sorted(self._frontend_workspace_root().glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                state = payload.get("state", payload)
                project_name = (state.get("project_name") or path.stem).strip()
                if project_name:
                    names.append(project_name)
            except Exception:
                names.append(path.stem)
        deduped = []
        seen = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            deduped.append(name)
        return deduped

    def _build_frontend_workspace_payload(self) -> dict:
        state = self._capture_frontend_history_state()
        if not state:
            state = {
                "project_name": self._frontend_project_name,
                "configs": self.frontend_store.list_configs(),
                "bundles": self.frontend_store.list_bundles(),
                "modules": self.frontend_store.list_modules(),
                "debug_points": self.frontend_store.list_debug_points(),
                "main_module_name": self._current_main_module_name(),
            }
        return {
            "format": "hyper_ide_frontend_workspace",
            "version": 1,
            "saved_at": self._timestamp_text(),
            "state": state,
        }

    def _read_frontend_workspace_payload(self, path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "state" in payload and isinstance(payload.get("state"), dict):
            return payload
        if isinstance(payload, dict):
            return {
                "format": "hyper_ide_frontend_workspace",
                "version": 1,
                "saved_at": self._timestamp_text(),
                "state": payload,
            }
        raise ValueError("工作区文件格式不正确。")

    def _apply_frontend_workspace_payload(self, payload: dict):
        state = copy.deepcopy(payload.get("state", payload))
        project_name = (state.get("project_name") or self._frontend_project_name or "frontend_demo").strip() or "frontend_demo"
        if project_name != self._current_project_name:
            self._close_all_project_pages()
        self._frontend_project_name = project_name
        self._restore_frontend_history_state(state)
        self._reset_frontend_history()
        self._append_log(f"已加载前端工作区：{project_name}。")

    def _save_frontend_workspace(self, name: str | None = None) -> Path | None:
        workspace_name = (name or self._current_project_name or self._frontend_project_name or "").strip()
        if not workspace_name:
            QMessageBox.warning(self, "保存失败", "当前没有可保存的前端工作区名称。")
            return None

        payload = self._build_frontend_workspace_payload()
        payload["state"]["project_name"] = workspace_name
        path = self._frontend_workspace_path(workspace_name)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._frontend_project_name = workspace_name
        self._append_log(f"已保存前端工作区：{workspace_name} -> {path.name}")
        return path

    def _open_frontend_workspace_by_name(self, name: str) -> bool:
        target = (name or "").strip()
        if not target:
            return False

        for path in sorted(self._frontend_workspace_root().glob("*.json")):
            try:
                payload = self._read_frontend_workspace_payload(path)
            except Exception:
                continue
            state = payload.get("state", {})
            if (state.get("project_name") or path.stem).strip() != target:
                continue
            self._apply_frontend_workspace_payload(payload)
            return True
        return False

    def _delete_frontend_workspace_by_name(self, name: str) -> bool:
        target = (name or "").strip()
        if not target:
            return False

        removed = False
        for path in sorted(self._frontend_workspace_root().glob("*.json")):
            try:
                payload = self._read_frontend_workspace_payload(path)
                state = payload.get("state", {})
                candidate = (state.get("project_name") or path.stem).strip()
            except Exception:
                candidate = path.stem
            if candidate != target:
                continue
            path.unlink(missing_ok=True)
            removed = True
        return removed

    def _reset_frontend_history(self):
        self.history.clear_history()
        self._history_state_cache = self._capture_frontend_history_state()

    def _record_frontend_history(self, text: str, params: dict | None = None, before_state: dict | None = None) -> bool:
        if not self.frontend_only:
            return False
        if self._history_recording_suspended or self._history_restore_in_progress:
            self._history_state_cache = self._capture_frontend_history_state()
            return False

        after_state = self._capture_frontend_history_state()
        if after_state is None:
            self._history_state_cache = None
            return False

        if before_state is None:
            before_state = copy.deepcopy(self._history_state_cache) if isinstance(self._history_state_cache, dict) else copy.deepcopy(after_state)
        else:
            before_state = copy.deepcopy(before_state)

        pushed = self.history.push_snapshot_command(text, before_state, after_state, params=params)
        self._history_state_cache = copy.deepcopy(after_state)
        if pushed:
            self._frontend_build_info = None
            self._frontend_run_active = False
            self._stop_frontend_run_stream()
            if self._ui_state in {"built", "running", "stopped"}:
                self._set_ui_state("idle", "数据已变更")
            self.bottom.set_output_status("最近一次 Build / Run 输出可能已过期。")
        return pushed

    def _describe_module_library_change(self, before_state: dict, after_state: dict) -> tuple[str, dict]:
        before_modules = before_state.get("modules", {}) or {}
        after_modules = after_state.get("modules", {}) or {}
        before_names = set(before_modules.keys())
        after_names = set(after_modules.keys())

        before_main = (before_state.get("main_module_name", "") or "").strip()
        after_main = (after_state.get("main_module_name", "") or "").strip()
        if before_modules == after_modules and before_main != after_main:
            if after_main:
                return "设为主模块", {"module": after_main}
            return "取消主模块", {"module": before_main}

        added = sorted(after_names - before_names)
        removed = sorted(before_names - after_names)
        changed = sorted(name for name in (before_names & after_names) if before_modules.get(name) != after_modules.get(name))

        if len(added) == 1 and not removed and not changed:
            return "新增模块", {"module": added[0]}
        if len(removed) == 1 and not added and not changed:
            return "删除模块", {"module": removed[0]}
        if len(added) == 1 and len(removed) == 1 and not changed:
            return "重命名模块", {"from": removed[0], "to": added[0]}
        if len(changed) == 1 and not added and not removed:
            return "编辑模块", {"module": changed[0]}

        return "更新模块库", {
            "added": added,
            "removed": removed,
            "changed": changed,
            "main_module": after_main,
        }

    def _refresh_open_module_pages(self):
        stale_widgets: list[QWidget] = []
        open_module_names = set(self.explorer.export_modules().keys())
        code_modules: set[str] = set()

        for widget in list(self._iter_open_pages()):
            if isinstance(widget, ModuleCanvasPage):
                if widget.module_name not in open_module_names:
                    stale_widgets.append(widget)
                    continue
                widget.refresh_canvas()
            elif isinstance(widget, CodeBlockEditorPage):
                if widget.module_name not in open_module_names:
                    stale_widgets.append(widget)
                    continue
                code_modules.add(widget.module_name)

        for module_name in sorted(code_modules):
            self._refresh_open_code_block_pages(module_name)

        for widget in stale_widgets:
            self._close_page_widget(widget)

    def _restore_frontend_history_state(self, snapshot: dict):
        if not self.frontend_only:
            return

        state = copy.deepcopy(snapshot or {})
        project_name = (state.get("project_name") or self._frontend_project_name or "frontend_demo").strip() or "frontend_demo"

        self._history_restore_in_progress = True
        self._history_recording_suspended = True
        try:
            self.frontend_store.project_name = project_name
            self._frontend_project_name = project_name
            self.frontend_store.import_configs(state.get("configs", []) or [])
            self.frontend_store.import_bundles(state.get("bundles", []) or [])
            self.frontend_store.import_modules(state.get("modules", {}) or {})
            self.frontend_store.import_debug_points(state.get("debug_points", []) or [])

            self._current_project_name = project_name
            self.project_label.setText(f"当前项目: {project_name}")
            self.project_label.setStyleSheet("margin-right: 15px; color: #0078d4; font-weight: bold;")

            self.refresh_project_data()
            self.refresh_project_bundle_data(include_reference=False, include_definition=True)
            self._refresh_project_module_data()
            self.refresh_project_debug_data()
            if hasattr(self.explorer, "set_main_module_name"):
                self.explorer.set_main_module_name(state.get("main_module_name", "") or "", emit_signal=False)
            self._frontend_build_info = None
            self._frontend_run_active = False
            self._stop_frontend_run_stream()
            self.bottom.set_output_status("最近一次 Build / Run 输出可能已过期。")
            self._set_ui_state("idle", "历史恢复")
            self._refresh_open_detail_pages()
            self._refresh_open_module_pages()
            self._history_state_cache = self._capture_frontend_history_state()
            self.statusBar().showMessage("已恢复到所选编辑历史状态。", 2500)
        finally:
            self._history_recording_suspended = False
            self._history_restore_in_progress = False

    def _timestamp_text(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _append_log(self, text: str):
        line = f"[{self._timestamp_text()}] {text}"
        self.bottom.logs.append(line)

    def _theme_label(self, theme_name: str) -> str:
        return {
            "dark": "深色主题",
            "light": "浅色主题",
        }.get(theme_name, theme_name or "深色主题")

    def _theme_qss_path(self, theme_name: str) -> Path:
        theme_file = "theme_light.qss" if theme_name == "light" else "theme.qss"
        return Path(__file__).resolve().parent / theme_file

    def _apply_theme(self, theme_name: str, persist: bool = True):
        theme_name = theme_name if theme_name in {"dark", "light"} else "dark"
        qss_path = self._theme_qss_path(theme_name)
        try:
            stylesheet = qss_path.read_text(encoding="utf-8")
        except Exception:
            theme_name = "dark"
            stylesheet = self._theme_qss_path("dark").read_text(encoding="utf-8")

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)
        self._theme_name = theme_name
        if persist:
            self.settings.setValue("ui/theme_name", theme_name)
        if hasattr(self, "bottom"):
            self.bottom.set_output_status(self.bottom.output_status.text())

    def _load_ui_preferences(self) -> dict:
        return {
            "auto_switch_output_tab": _as_bool(self.settings.value("ui/auto_switch_output_tab", True), True),
            "clear_output_before_build": _as_bool(self.settings.value("ui/clear_output_before_build", True), True),
            "clear_terminal_before_run": _as_bool(self.settings.value("ui/clear_terminal_before_run", False), False),
            "auto_open_logs_on_terminal_error": _as_bool(self.settings.value("ui/auto_open_logs_on_terminal_error", True), True),
            "default_bottom_tab": int(self.settings.value("ui/default_bottom_tab", 0) or 0),
        }

    def _save_ui_preferences(self):
        for key, value in (self.ui_preferences or {}).items():
            self.settings.setValue(f"ui/{key}", value)

    def _apply_ui_preferences(self):
        default_tab = int(self.ui_preferences.get("default_bottom_tab", 0))
        if hasattr(self, "bottom"):
            self.bottom.tabs.setCurrentIndex(max(0, min(default_tab, self.bottom.tabs.count() - 1)))

    def _focus_is_text_input(self) -> bool:
        widget = QApplication.focusWidget()
        return isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit))

    def _focused_text_widget(self):
        widget = QApplication.focusWidget()
        return widget if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)) else None

    def _open_bottom_tab(self, index: int):
        if hasattr(self, "bottom"):
            self.bottom.tabs.setCurrentIndex(index)

    def _maybe_switch_output_tab(self):
        if self.ui_preferences.get("auto_switch_output_tab", True):
            self._open_bottom_tab(2)

    def _build_shortcut_specs(self) -> list[dict]:
        return [
            {"action": "保存项目", "shortcut": "Ctrl+S", "description": "保存当前项目或前端工作区", "handler": self.on_save_all},
            {"action": "构建预览", "shortcut": "Ctrl+B", "description": "执行前端预览 Build", "handler": self.on_build},
            {"action": "运行预览", "shortcut": "F5", "description": "执行前端预览 Run", "handler": self.on_run},
            {"action": "停止运行", "shortcut": "Shift+F5", "description": "停止前端预览运行", "handler": self.on_stop},
            {"action": "清理输出", "shortcut": "Ctrl+Shift+K", "description": "清理最近一次 Build / Run 输出", "handler": self.on_clean},
            {"action": "打开设置", "shortcut": "Ctrl+,", "description": "打开 Preferences", "handler": self.on_preferences},
            {"action": "切换主题", "shortcut": "F6", "description": "打开 Theme 对话框", "handler": self.on_theme},
            {"action": "查看快捷键", "shortcut": "Ctrl+/", "description": "打开 Shortcuts 对话框", "handler": self.on_shortcuts},
            {"action": "聚焦日志", "shortcut": "Alt+1", "description": "切换到底边栏日志页", "handler": lambda: self._open_bottom_tab(0)},
            {"action": "聚焦终端", "shortcut": "Alt+2", "description": "切换到底边栏终端页", "handler": lambda: self._open_bottom_tab(1)},
            {"action": "聚焦输出", "shortcut": "Alt+3", "description": "切换到底边栏输出页", "handler": lambda: self._open_bottom_tab(2)},
        ]

    def _install_shortcuts(self):
        for shortcut in self._shortcuts:
            shortcut.deleteLater()
        self._shortcuts = []

        for spec in self._shortcut_specs:
            shortcut = QShortcut(QKeySequence(spec["shortcut"]), self)
            shortcut.activated.connect(spec["handler"])
            self._shortcuts.append(shortcut)

    def _set_ui_state(self, state: str, detail: str = ""):
        self._ui_state = state
        text_map = {
            "idle": "界面状态: 空闲",
            "building": "界面状态: 正在构建",
            "built": "界面状态: 已构建",
            "running": "界面状态: 运行中",
            "stopped": "界面状态: 已停止",
            "clean": "界面状态: 已清理",
            "terminal": "界面状态: 终端执行中",
        }
        text = text_map.get(state, f"界面状态: {state}")
        if detail:
            text = f"{text} ({detail})"
        color = {
            "idle": "#64748b",
            "building": "#2563eb",
            "built": "#0f766e",
            "running": "#15803d",
            "stopped": "#b45309",
            "clean": "#64748b",
            "terminal": "#7c3aed",
        }.get(state, "#64748b")
        self.ui_state_label.setText(text)
        self.ui_state_label.setStyleSheet(f"margin-right: 12px; color: {color}; font-weight: 600;")

    def _project_stats(self) -> dict:
        configs = self.frontend_store.list_configs() if self.frontend_only else self.explorer.get_config_snapshot()
        bundles = self.frontend_store.list_bundles() if self.frontend_only else self.explorer.get_harness_snapshot()
        modules = self.frontend_store.list_modules() if self.frontend_only else self.explorer.export_modules()
        debug_points = self.frontend_store.list_debug_points() if self.frontend_only else getattr(self.explorer, "get_debug_snapshot", lambda: [])()

        module_dict = modules if isinstance(modules, dict) else {}
        rpc_count = 0
        pipe_port_count = 0
        submodule_count = 0
        pipe_count = 0
        clock_block_count = 0
        code_block_count = 0
        connection_count = 0

        for module_data in module_dict.values():
            rpc_count += len(_safe_list(module_data.get("rpcs", [])))
            pipe_port_count += len(_safe_list(module_data.get("pipe_ports", [])))
            submodule_count += len(_safe_list(module_data.get("submodules", [])))
            pipe_count += len(_safe_list(module_data.get("pipes", [])))
            clock_blocks = _safe_list(module_data.get("clock_blocks", []))
            service_blocks = _safe_list(module_data.get("service_blocks", []))
            subreq_blocks = _safe_list(module_data.get("subreq_blocks", []))
            clock_block_count += len(clock_blocks)
            code_block_count += len(clock_blocks) + len(service_blocks) + len(subreq_blocks)
            helper = module_data.get("helper_code", [])
            if (isinstance(helper, list) and helper) or (isinstance(helper, str) and helper.strip()):
                code_block_count += 1
            connection_count += (
                len(_safe_list(module_data.get("reqsvc_conns", [])))
                + len(_safe_list(module_data.get("instpipe_conns", [])))
                + len(_safe_list(module_data.get("block_conns", [])))
                + len(_safe_list(module_data.get("orders", [])))
            )

        return {
            "configs": len(configs),
            "bundles": len(bundles),
            "modules": len(module_dict),
            "rpcs": rpc_count,
            "pipe_ports": pipe_port_count,
            "submodules": submodule_count,
            "pipes": pipe_count,
            "clock_blocks": clock_block_count,
            "code_blocks": code_block_count,
            "connections": connection_count,
            "debug_points": len(debug_points),
        }

    def _current_main_module_name(self) -> str:
        if hasattr(self.explorer, "get_main_module_name"):
            return (self.explorer.get_main_module_name() or "").strip()
        return ""

    def _show_output_document(self, title: str, lines: list[str], state_text: str = ""):
        self._stop_frontend_run_stream()
        header = [f"[{title}]", f"时间: {self._timestamp_text()}"]
        if self._current_project_name:
            header.append(f"项目: {self._current_project_name}")
        if state_text:
            header.append(f"状态: {state_text}")
        content = "\n".join(header + ["", *lines]).strip()
        self.bottom.output.setPlainText(content)
        if state_text:
            self.bottom.set_output_status(state_text)
        self._maybe_switch_output_tab()

    def _append_output_line(self, text: str):
        self.bottom.output.append(text)
        self._maybe_switch_output_tab()

    def _start_frontend_run_stream(self, lines: list[str]):
        self._stop_frontend_run_stream()
        self._frontend_run_stream_queue = [str(line) for line in lines if str(line).strip()]
        if self._frontend_run_stream_queue:
            self.bottom.set_output_status("前端预览运行中，正在流式输出。")
            self._frontend_run_stream_timer.start()

    def _flush_frontend_run_stream(self):
        if not self._frontend_run_stream_queue:
            self._frontend_run_stream_timer.stop()
            if self._frontend_run_active:
                self.bottom.set_output_status("前端预览运行中，当前批次输出已发送完成。")
            return
        line = self._frontend_run_stream_queue.pop(0)
        self._append_output_line(line)
        if not self._frontend_run_stream_queue:
            self._frontend_run_stream_timer.stop()
            if self._frontend_run_active:
                self.bottom.set_output_status("前端预览运行中，当前批次输出已发送完成。")

    def _stop_frontend_run_stream(self):
        if self._frontend_run_stream_timer.isActive():
            self._frontend_run_stream_timer.stop()
        self._frontend_run_stream_queue.clear()

    def _ensure_frontend_project_open(self, action_name: str) -> bool:
        if self._current_project_name:
            return True
        QMessageBox.warning(self, "操作失败", f"当前没有已打开的前端工作区，无法{action_name}。")
        return False

    def _build_frontend_artifact(self) -> dict:
        modules = self.frontend_store.list_modules()
        stats = self._project_stats()
        main_module = self._current_main_module_name()
        warnings: list[str] = []
        if not modules:
            warnings.append("当前工作区没有模块定义，将生成空构建结果。")
        if modules and not main_module:
            warnings.append("当前未显式设置主模块，将使用前端预览构建模式。")

        return {
            "project_name": self._current_project_name or self.frontend_store.project_name,
            "built_at": self._timestamp_text(),
            "main_module": main_module,
            "stats": stats,
            "warnings": warnings,
        }

    def _terminal_help_text(self) -> str:
        return "\n".join([
            "可用命令：",
            "help",
            "status",
            "build / run / stop / clean",
            "list configs | bundles | modules | debug",
            "show config <name>",
            "show harness <name>",
            "show module <name>",
            "show debug <name>",
            "open config <name>",
            "open harness <name>",
            "open module <name>",
            "open debug <name>",
            "echo <text>",
            "clear logs | output | terminal",
            "repeat <n> <command>",
            "if project_open <command>",
            "if has_module <name> <command>",
        ])

    def _terminal_lines(self, raw_text) -> list[str]:
        return [str(line).rstrip() for line in str(raw_text or "").splitlines()]

    def _terminal_summary_for(self, kind: str, name: str) -> str:
        store = self._build_analysis_store()
        try:
            if kind == "config":
                detail = store.get_config_detail(name)
                return (
                    f"配置项: {detail.get('name', name)}\n"
                    f"表达式: {detail.get('expr', '') or '（空）'}\n"
                    f"实值: {detail.get('realvalue', '') or '（未解析）'}\n"
                    f"注释: {detail.get('comment', '') or '（无注释）'}"
                )
            if kind == "harness":
                detail = store.get_bundle_detail(name)
                member_count = len(detail.get("members", []) or [])
                enum_count = len(detail.get("enums", []) or [])
                return (
                    f"线组: {detail.get('name', name)}\n"
                    f"注释: {detail.get('comment', '') or '（无注释）'}\n"
                    f"成员数: {member_count}\n"
                    f"枚举数: {enum_count}"
                )
        except ValueError:
            pass

        if kind == "debug":
            rows = [row for row in store.list_debug_points() if _strip_text(row.get("name", "")) == name]
            if rows:
                row = rows[0]
                return (
                    f"调试检查点: {row.get('name', name)}\n"
                    f"类型: {row.get('kind', '') or 'wave'}\n"
                    f"表达式: {row.get('expr', '') or '（空）'}\n"
                    f"触发: {row.get('trigger', '') or '（空）'}\n"
                    f"注释: {row.get('comment', '') or '（无注释）'}"
                )

        if kind == "module":
            module_data = self._get_module_data_or_stub(name)
            return (
                f"模块: {module_data.get('name', name)}\n"
                f"注释: {module_data.get('comment', '') or '（无注释）'}\n"
                f"子模块数: {len(_safe_list(module_data.get('submodules', [])))}\n"
                f"管道数: {len(_safe_list(module_data.get('pipes', [])))}\n"
                f"代码块数: {len(_safe_list(module_data.get('clock_blocks', []))) + len(_safe_list(module_data.get('service_blocks', []))) + len(_safe_list(module_data.get('subreq_blocks', [])))}"
            )
        return f"未找到 {kind}: {name}"

    def _execute_terminal_command(self, line: str) -> list[str]:
        text = (line or "").strip()
        if not text or text.startswith("#"):
            return []

        lower = text.lower()
        analysis_store = self._build_analysis_store()
        if lower == "help":
            return [self._terminal_help_text()]
        if lower == "status":
            stats = self._project_stats()
            return [
                f"项目: {self._current_project_name or '（未打开）'}",
                f"主模块: {self._current_main_module_name() or '（未设置）'}",
                f"UI 状态: {self._ui_state}",
                f"配置/线组/模块: {stats['configs']} / {stats['bundles']} / {stats['modules']}",
                f"连接/代码块: {stats['connections']} / {stats['code_blocks']}",
                f"调试检查点: {stats['debug_points']}",
            ]
        if lower == "build":
            self.on_build()
            return ["已触发 Build。"]
        if lower == "run":
            self.on_run()
            return ["已触发 Run。"]
        if lower == "stop":
            self.on_stop()
            return ["已触发 Stop。"]
        if lower == "clean":
            self.on_clean()
            return ["已触发 Clean。"]
        if lower.startswith("echo "):
            return [text[5:]]

        if lower.startswith("repeat "):
            parts = text.split(maxsplit=2)
            if len(parts) < 3 or not parts[1].isdigit():
                raise ValueError("repeat 用法：repeat <次数> <命令>")
            count = int(parts[1])
            nested = parts[2]
            out: list[str] = []
            for idx in range(count):
                out.append(f"[repeat {idx + 1}/{count}] {nested}")
                out.extend(self._execute_terminal_command(nested))
            return out

        if lower.startswith("if project_open "):
            nested = text[len("if project_open "):].strip()
            if not self._current_project_name:
                return ["条件未满足：当前没有打开的项目。"]
            return self._execute_terminal_command(nested)

        if lower.startswith("if has_module "):
            parts = text.split(maxsplit=3)
            if len(parts) < 4:
                raise ValueError("if has_module 用法：if has_module <模块名> <命令>")
            module_name = parts[2]
            if module_name not in analysis_store.list_modules():
                return [f"条件未满足：模块“{module_name}”不存在。"]
            return self._execute_terminal_command(parts[3])

        if lower.startswith("list "):
            target = lower.split(maxsplit=1)[1]
            if target == "configs":
                names = [item.get("name", "") for item in analysis_store.list_configs()]
                return ["配置项列表:", *(names or ["（无）"])]
            if target in {"bundles", "harnesses"}:
                names = [item.get("name", "") for item in analysis_store.list_bundles()]
                return ["线组列表:", *(names or ["（无）"])]
            if target == "modules":
                names = sorted(analysis_store.list_modules().keys())
                return ["模块列表:", *(names or ["（无）"])]
            if target in {"debug", "debugs"}:
                names = [item.get("name", "") for item in analysis_store.list_debug_points()]
                return ["调试检查点列表:", *(names or ["（无）"])]
            raise ValueError("list 仅支持 configs / bundles / modules / debug")

        if lower.startswith("show "):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                raise ValueError("show 用法：show config|harness|module|debug <名称>")
            kind = parts[1].lower()
            name = parts[2].strip()
            kind_map = {"config": "config", "harness": "harness", "bundle": "harness", "module": "module", "debug": "debug"}
            mapped = kind_map.get(kind)
            if not mapped:
                raise ValueError("show 仅支持 config / harness / module / debug")
            return [self._terminal_summary_for(mapped, name)]

        if lower.startswith("open "):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                raise ValueError("open 用法：open config|harness|module|debug <名称>")
            kind = parts[1].lower()
            name = parts[2].strip()
            if kind == "config":
                self.open_config_relation_tab(name, {})
                return [f"已打开配置项标签：{name}"]
            if kind in {"harness", "bundle"}:
                self.open_harness_detail_tab(name, {})
                return [f"已打开线组标签：{name}"]
            if kind == "module":
                self.open_module_canvas_tab(name, {})
                return [f"已打开模块标签：{name}"]
            if kind == "debug":
                rows = [row for row in analysis_store.list_debug_points() if _strip_text(row.get("name", "")) == name]
                if not rows:
                    raise ValueError(f"未找到调试检查点：{name}")
                return [self._terminal_summary_for("debug", name)]
            raise ValueError("open 仅支持 config / harness / module / debug")

        if lower.startswith("clear "):
            target = lower.split(maxsplit=1)[1]
            if target == "logs":
                self.bottom.logs.clear()
                return ["已清空日志面板。"]
            if target == "output":
                self.bottom.output.clear()
                self.bottom.set_output_status("输出已清空。")
                return ["已清空输出面板。"]
            if target == "terminal":
                self.bottom.terminal_output.clear()
                return ["已清空终端结果。"]
            raise ValueError("clear 仅支持 logs / output / terminal")

        raise ValueError(f"未知命令：{text}")

    def on_run_terminal_script(self, script: str):
        prev_ui_state = self._ui_state
        prev_build_active = self._frontend_build_info is not None
        prev_run_active = self._frontend_run_active
        if self.ui_preferences.get("clear_terminal_before_run", False):
            self.bottom.terminal_output.clear()
        self.bottom.tabs.setCurrentIndex(1)
        self.bottom.set_terminal_status("执行中")
        self._set_ui_state("terminal", "脚本执行")

        lines = self._terminal_lines(script)
        executed = 0
        try:
            if not lines:
                self.bottom.append_terminal_line("[终端] 没有可执行的命令。")
                self.bottom.set_terminal_status("待执行")
                if prev_run_active:
                    self._set_ui_state("running", "前端预览")
                elif prev_build_active:
                    self._set_ui_state("built", "前端预览")
                else:
                    self._set_ui_state(prev_ui_state if prev_ui_state != "terminal" else "idle")
                return

            for raw_line in lines:
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                executed += 1
                self.bottom.append_terminal_line(f">>> {stripped}")
                outputs = self._execute_terminal_command(stripped)
                for msg in outputs:
                    self.bottom.append_terminal_line(msg)

            self.bottom.set_terminal_status(f"执行完成，共 {executed} 条命令")
            self._append_log(f"终端脚本执行完成，共 {executed} 条命令。")
        except Exception as e:
            self.bottom.append_terminal_line(f"[错误] {e}")
            self.bottom.set_terminal_status("执行失败")
            self._append_log(f"终端脚本执行失败: {e}")
            if self.ui_preferences.get("auto_open_logs_on_terminal_error", True):
                self._open_bottom_tab(0)
        finally:
            if self._ui_state == "terminal":
                if self._frontend_run_active:
                    self._set_ui_state("running", "前端预览")
                elif self._frontend_build_info:
                    self._set_ui_state("built", "前端预览")
                else:
                    self._set_ui_state("idle")

    def _refresh_open_detail_pages(self):
        widgets = list(self._iter_open_pages())
        if not widgets:
            return

        store = self._build_analysis_store()
        stale_widgets: list[QWidget] = []

        for widget in widgets:
            try:
                if isinstance(widget, ConfigRelationPage):
                    widget.reload(store.get_config_detail(widget.config_name))
                elif isinstance(widget, HarnessDetailPage):
                    widget.reload(store.get_bundle_detail(widget.harness_name))
            except ValueError:
                stale_widgets.append(widget)

        for widget in stale_widgets:
            self._close_page_widget(widget)

    def _refresh_project_module_data(self):
        if self.frontend_only:
            if not self._current_project_name:
                self.explorer.clear_modules()
                return

            self.explorer.update_module_list(self.frontend_store.list_modules())

    def refresh_project_debug_data(self):
        if not hasattr(self.explorer, "update_debug_list"):
            return

        if self.frontend_only:
            if not self._current_project_name:
                self.explorer.clear_debug_points()
                return
            self.explorer.update_debug_list(self.frontend_store.list_debug_points())
            return

        if not self._current_project_name:
            self.explorer.clear_debug_points()
            return

        # 后端调试信息接口尚未定义，先保留当前前端骨架。
        self.explorer.clear_debug_points()

    def _on_module_library_changed(self, modules):
        if self.frontend_only and self._current_project_name:
            before_state = copy.deepcopy(self._history_state_cache) if isinstance(self._history_state_cache, dict) else self._capture_frontend_history_state()
            self.frontend_store.import_modules(modules or {})
            self._refresh_open_module_pages()
            if isinstance(before_state, dict):
                after_state = self._capture_frontend_history_state()
                if isinstance(after_state, dict):
                    text, params = self._describe_module_library_change(before_state, after_state)
                    self._record_frontend_history(text, params, before_state=before_state)

    def _on_main_module_changed(self, module_name: str):
        if not self.frontend_only or not self._current_project_name:
            return

        before_state = copy.deepcopy(self._history_state_cache) if isinstance(self._history_state_cache, dict) else self._capture_frontend_history_state()
        if not isinstance(before_state, dict):
            return

        action = "设为主模块" if module_name else "取消主模块"
        self._record_frontend_history(action, {"module": module_name}, before_state=before_state)

    # 检查是否有已经启动的项目
        # 检查是否有已经启动的项目
    def check_initial_project_status(self):
        """Initial status check using a lock to avoid monitor conflicts."""
        if self.frontend_only:
            self._update_conn_ui(True, "前端开发模式")
            self.update_project_display(self._frontend_project_name)
            return

        # If monitor is busy, this will wait safely.
        with self.info_lock:
            print("[Init] Running startup self-check...")
            try:
                resp = self.control.call("info", [])

                # 【核心修改】：初始化时逻辑同 Monitor，有返回即连接成功
                if isinstance(resp, dict):
                    # 1. 设置连接状态为绿色
                    self._update_conn_ui(True, "已连接")

                    code = resp.get("code")
                    print(f"[TCP] 当前的code为：{code}")
                    if code == 0:
                        # 2. 如果 code=0，更新右上角项目名并刷新数据
                        print(f"[TCP] 当前code为0，更新右上角项目名称，刷新数据")
                        p_name = resp.get("results").get("name")
                        print(f"[TCP] 当前p_name为{p_name}")
                        self.update_project_display(p_name)
                        self.refresh_project_data()
                        self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                    else:
                        print(f"[TCP] ##当前code为{code}")
                        # 3. 如果 code!=0 (如 -11)，清空右上角项目名，清空配置树
                        # 但保持“已连接”状态
                        self.update_project_display(None)
                        self.explorer.clear_configs()
                else:
                    # 返回数据格式不对
                    raise ValueError("Invalid response format")

            except Exception as e:
                # 确实连不上（超时、拒绝连接等）
                print(f"[Init] Connection failed: {e}")
                self.update_project_display(None)
                self._update_conn_ui(False, "未连接")
                self.explorer.clear_configs()

    def refresh_project_data(self):
        """
        调用 configlib.list 获取所有配置并更新 Explorer
        """
        if self.frontend_only:
            if not self._current_project_name:
                self.explorer.clear_configs()
                self._refresh_open_detail_pages()
                return

            self.explorer.update_config_list(self.frontend_store.list_configs())
            self._refresh_open_detail_pages()
            return

        print("[Logic] Refreshing project data (configlib.list)...")
        try:
            # 构造 configlib.list 参数
            # 文档参数：reference="true" (显示引用关系，虽然目前树形列表可能只显示基础信息，但预留着没错)
            args = [Arg(index=0, name="reference", value="true")]

            # 调用接口
            resp = self.control.call("configlib.list", args)

            if resp.get("code") == 0:
                print(f"[configlib.list] 返回结果 :{resp}")
                # 解析返回结果
                # 结果包含: names, values(表达式), comments, realvalues(计算值) 等
                names = resp.get("list_results", {}).get("names", [])
                values = resp.get("list_results", {}).get("values", [])
                comments = resp.get("list_results", {}).get("comments", [])
                realvalues = resp.get("list_results", {}).get("realvalues", [])

                # 组装数据给 Explorer
                config_data_list = []
                count = len(names)

                for i in range(count):
                    # 安全获取，防止数组越界（虽然理论上长度应该一致）
                    n = names[i]
                    v = values[i] if i < len(values) else ""
                    c = comments[i] if i < len(comments) else ""

                    config_data_list.append({
                        "name": n,
                        "value": v,  # 这里对应前端的 Expr/Value
                        "comment": c,
                        "realvalue": realvalues[i] if i < len(realvalues) else "",
                    })

                # 更新 UI
                self.explorer.update_config_list(config_data_list)
                self._refresh_open_detail_pages()
                print(f"[Logic] Refreshed {len(config_data_list)} config items.")
            else:
                msg = resp.get("msg", "Unknown error")
                self.bottom.logs.append(f"同步配置列表失败: {msg}\n")

        except Exception as e:
            err_msg = f"同步配置数据异常: {str(e)}"
            print(err_msg)
            self.bottom.logs.append(err_msg + "\n")

    def refresh_project_bundle_data(self, include_reference: bool = False, include_definition: bool = True):
        """
        调用 bundlelib.list 获取所有 bundle 并更新 Explorer 的线束树
        """
        if self.frontend_only:
            if not self._current_project_name:
                self.explorer.clear_harnesses()
                self._refresh_open_detail_pages()
                return

            self.explorer.update_harness_list(self.frontend_store.list_bundles())
            self._refresh_open_detail_pages()
            return

        print("[Logic] Refreshing project bundle data (bundlelib.list)...")
        if not self._current_project_name:
            self.explorer.clear_harnesses()
            self._refresh_open_detail_pages()
            return

        try:
            args = []

            # reference / definition 是可选参数：按需开关
            if include_reference:
                args.append(Arg(index=len(args), name="reference", value="true"))

            if include_definition:
                args.append(Arg(index=len(args), name="definition", value="true"))

            resp = self.control.call("bundlelib.list", args)
            self.bottom.output.append(f"[Request: bundlelib.list] Result: {_json_dumps(resp)}\n")

            if resp.get("code") != 0:
                msg = resp.get("msg", "Unknown error")
                self.bottom.logs.append(f"同步 bundle 列表失败: {msg}\n")
                return

            list_results = resp.get("list_results", {}) or {}

            names = list_results.get("names", []) or []
            comments = list_results.get("comments", []) or []
            tags = list_results.get("tags", []) or []

            definitions = list_results.get("definitions", []) or []  # 仅 definition=true 才有
            references = list_results.get("references", []) or []  # 仅 reference=true 才有
            config_refs = list_results.get("config_references", []) or []  # 仅 reference=true 才有
            reverse_refs = list_results.get("reverse_references", []) or []  # 仅 reference=true 才有

            n = len(names)
            bundle_data_list: list[dict] = []

            for i in range(n):
                bundle_data_list.append({
                    "name": names[i],
                    "comment": comments[i] if i < len(comments) else "",
                    "tags": tags[i] if i < len(tags) else "",
                    "definition": definitions[i] if (include_definition and i < len(definitions)) else "",
                    "references": references[i] if (include_reference and i < len(references)) else "",
                    "config_references": config_refs[i] if (include_reference and i < len(config_refs)) else "",
                    "reverse_references": reverse_refs[i] if (include_reference and i < len(reverse_refs)) else "",
                })

            self.explorer.update_harness_list(bundle_data_list)
            self._refresh_open_detail_pages()
            print(f"[Logic] Refreshed {len(bundle_data_list)} bundle items.")

        except Exception as e:
            err_msg = f"同步 bundle 数据异常: {str(e)}"
            print(err_msg)
            self.bottom.logs.append(err_msg + "\n")

    def _init_top_toolbar(self):
        tb = QToolBar("Top")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(tb.iconSize())
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # 文档要求：连接/项目/编辑/运行/设置 :contentReference[oaicite:9]{index=9}
        # 这里先加 QAction 占位，后续绑定到具体槽函数
        # for name in ["连接", "项目", "编辑", "运行", "设置"]:
        #     tb.addAction(name)
        # 1) Connection 下拉
        tb.addWidget(self._make_dropdown_button(
            text="连接",
            items=[
                ("Connect", self.on_connect),
                ("Disconnect", self.on_disconnect),
                ("Ping", self.on_ping),
            ],
        ))

        # 2) Project 下拉（对齐你 HTML：New Project/Open File/Save All/Export）
        tb.addWidget(self._make_dropdown_button(
            text="项目",
            items=[
                ("新项目", self.on_new_project),
                ("打开项目", self.on_open_file_list),
                ("导入项目", self.on_import_project),
                ("保存项目", self.on_save_all),
                ("导出", self.on_export_harness),
                ("删除项目", self.on_delete_project),
                ("关闭当前项目", self.on_close_opened)
            ],
        ))

        # 3) Edit 下拉
        tb.addWidget(self._make_dropdown_button(
            text="编辑",
            items=[
                ("Undo", self.on_undo),
                ("Redo", self.on_redo),
                ("Cut", self.on_cut),
                ("Copy", self.on_copy),
                ("Paste", self.on_paste),
            ],
        ))

        # 4) Run 下拉
        tb.addWidget(self._make_dropdown_button(
            text="运行",
            items=[
                ("Run", self.on_run),
                ("Stop", self.on_stop),
                ("Build", self.on_build),
                ("Clean", self.on_clean),
            ],
        ))

        # 5) Settings 下拉
        tb.addWidget(self._make_dropdown_button(
            text="设置",
            items=[
                ("Preferences", self.on_preferences),
                ("Theme", self.on_theme),
                ("Shortcuts", self.on_shortcuts),
            ],
        ))

        # 添加一个弹簧，将后面的内容推向右侧
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        # 添加项目名称显示
        tb.addWidget(self.project_label)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

    def _make_dropdown_button(self, text: str, items: list[tuple[str, callable]]):
        """
        在工具栏创建一个“主按钮 + 下拉菜单”的控件。
        items: [("Menu Text", callback), ...]
        """
        btn = QToolButton()
        btn.setText(text)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # 点击直接弹菜单
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        menu = QMenu(btn)
        for label, cb in items:
            act = QAction(label, self)
            act.triggered.connect(cb)
            menu.addAction(act)

        btn.setMenu(menu)
        return btn

    def _add_dock(self, widget: QWidget, area: Qt.DockWidgetArea):
        dock = QDockWidget(widget.windowTitle(), self)
        dock.setObjectName(widget.windowTitle())
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(area, dock)

    def _get_module_data_or_stub(self, name: str) -> dict:
        """
        从 Explorer 的模块库里取模块定义；如果没有，就返回一个最小骨架，保证画布页能跑。
        你后续接后端/加载工程时，应保证 explorer 有模块库数据。
        """
        # 你的 ExplorerDock 目前示例里没显式维护 _modules 字典的话，你需要在 ExplorerDock 里加
        store = getattr(self.explorer, "_modules", None)
        if isinstance(store, dict) and name in store:
            return store[name]

        return {
            "name": name,
            "comment": "",
            "local_cfgs": [],
            "local_harnesses": [],
            "rpcs": [],
            "pipe_ports": [],
            "submodules": [],
            "pipes": [],
            "storages": [],
            "reqsvc_conns": [],
            "instpipe_conns": [],
            "block_conns": [],
            "orders": [],
            "clock_blocks": [],
            "service_blocks": [],
            "subreq_blocks": [],
            "helper_code": [],
        }

    def _module_resolver(self, name: str) -> dict | None:
        """
        给 ModuleCanvasPage 用的 resolver：根据模块名拿到模块定义（用于生成实例端口）。
        """
        store = getattr(self.explorer, "_modules", None)
        if isinstance(store, dict):
            return store.get(name)
        return None

    def _make_module_canvas_page(self, module_name: str, module_data: dict) -> ModuleCanvasPage:
        """
        统一创建画布页，并绑定回写逻辑
        """
        page = ModuleCanvasPage(
            module_name=module_name,
            module_data=module_data,
            module_resolver=self._module_resolver,
            parent=self,
        )
        page.moduleUpdated.connect(self._on_module_updated_from_canvas)

        # 双击子模块实例 -> 请求打开对应模块画布
        page.requestOpenModuleCanvas.connect(self._open_module_canvas_from_canvas)
        page.requestOpenClockCode.connect(self.open_clock_block_code_tab)
        page.requestOpenServiceCode.connect(self.open_service_block_code_tab)
        page.requestOpenSubreqCode.connect(self.open_subreq_block_code_tab)
        page.requestOpenHelperCode.connect(self.open_helper_code_tab)
        return page

    def _on_module_updated_from_canvas(
        self,
        name: str,
        data: dict,
        history_text: str | None = None,
        history_params: dict | None = None,
        before_state: dict | None = None,
    ):
        """
        画布页更新模块后：写回全局模块库，并刷新 Explorer 的模块树（如果你实现了刷新函数）。
        """
        if self.frontend_only and before_state is None:
            before_state = self._capture_frontend_history_state()

        # 1) 写回 Explorer 模块库
        if not hasattr(self.explorer, "_modules") or not isinstance(self.explorer._modules, dict):
            self.explorer._modules = {}
        self.explorer._modules[name] = data
        if self.frontend_only:
            self.frontend_store.import_modules(self.explorer.export_modules())

        # 2) 刷新树（你需要在 ExplorerDock 里实现/暴露 refresh 方法）
        if hasattr(self.explorer, "_refresh_module_tree"):
            self.explorer._refresh_module_tree()

        # 3) 通知所有打开的 ModuleCanvasPage：某个模块定义更新了，刷新引用它的实例端口
        for i in range(self.center_tabs.count()):
            w = self.center_tabs.widget(i)
            if isinstance(w, ModuleCanvasPage):
                w.refresh_canvas(updated_module_name=name)

        self._refresh_open_code_block_pages(name)

        if self.frontend_only:
            entry = self._pending_module_history_entry
            self._pending_module_history_entry = None
            if history_text is None and isinstance(entry, tuple):
                history_text = entry[0]
                history_params = entry[1]
            self._record_frontend_history(
                history_text or "编辑模块画布",
                history_params or {"module": name},
                before_state=before_state,
            )

    def _refresh_open_code_block_pages(self, module_name: str):
        module_data = self._get_module_data_or_stub(module_name)
        clock_map = {
            _strip_text(row.get("name", "")): row
            for row in _safe_list(module_data.get("clock_blocks", []))
            if _strip_text(row.get("name", ""))
        }
        service_map = {
            _strip_text(row.get("port", "")): row
            for row in _safe_list(module_data.get("service_blocks", []))
            if _strip_text(row.get("port", ""))
        }
        subreq_map = {
            f"{_strip_text(row.get('inst', ''))}.{_strip_text(row.get('port', ''))}": row
            for row in _safe_list(module_data.get("subreq_blocks", []))
            if _strip_text(row.get("inst", "")) and _strip_text(row.get("port", ""))
        }
        helper_row = self._find_code_block_row(module_data, "helper", "helper_code")

        stale_widgets: list[QWidget] = []
        for widget in list(self._iter_open_pages()):
            if not isinstance(widget, CodeBlockEditorPage):
                continue
            if widget.module_name != module_name:
                continue

            if widget.block_kind == "clock":
                row = clock_map.get(widget.block_name)
                if row is None:
                    stale_widgets.append(widget)
                    continue
                widget.reload(
                    module_name,
                    "clock",
                    row,
                    analysis_context=self._build_code_block_analysis_context(module_name, "clock", row),
                )
                self._set_page_title(widget, self._code_block_tab_title(module_name, "clock", widget.block_name))
            elif widget.block_kind == "service":
                row = service_map.get(widget.block_name)
                if row is None:
                    stale_widgets.append(widget)
                    continue
                widget.reload(
                    module_name,
                    "service",
                    row,
                    analysis_context=self._build_code_block_analysis_context(module_name, "service", row),
                )
                self._set_page_title(widget, self._code_block_tab_title(module_name, "service", widget.block_name))
            elif widget.block_kind == "subreq":
                row = subreq_map.get(widget.block_name)
                if row is None:
                    stale_widgets.append(widget)
                    continue
                widget.reload(
                    module_name,
                    "subreq",
                    row,
                    analysis_context=self._build_code_block_analysis_context(module_name, "subreq", row),
                )
                self._set_page_title(widget, self._code_block_tab_title(module_name, "subreq", widget.block_name))
            elif widget.block_kind == "helper":
                if helper_row is None:
                    stale_widgets.append(widget)
                    continue
                widget.reload(
                    module_name,
                    "helper",
                    helper_row,
                    analysis_context=self._build_code_block_analysis_context(module_name, "helper", helper_row),
                )
                self._set_page_title(widget, self._code_block_tab_title(module_name, "helper", widget.block_name))

        for widget in stale_widgets:
            self._close_page_widget(widget)

    def _open_module_canvas_from_canvas(self, module_name: str):
        # 从画布内部进入子模块：用 explorer 库里的定义兜底
        module_data = self._get_module_data_or_stub(module_name)
        self.open_module_canvas_tab(module_name, module_data)

    def _find_existing_page(self, page_type, name: str):
        for widget in self._iter_open_pages():
            if isinstance(widget, page_type):
                current_name = getattr(widget, "config_name", None) or getattr(widget, "harness_name", None)
                if current_name == name:
                    return widget
        return None

    def _edit_config_from_detail(self, name: str):
        if not self.explorer.edit_config_by_name(name):
            QMessageBox.warning(self, "编辑失败", f"未找到配置项“{name}”。")

    def _edit_harness_from_detail(self, name: str):
        if not self.explorer.edit_harness_by_name(name):
            QMessageBox.warning(self, "编辑失败", f"未找到线组“{name}”。")

    def _delete_config_from_detail(self, name: str):
        confirm = QMessageBox.question(
            self,
            "确认删除",
            f"将删除配置项：\n\n{name}\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            success, failed = self.frontend_store.remove_configs([name])
            if failed:
                QMessageBox.warning(self, "删除失败", failed[0][1])
                return
            if success:
                self.refresh_project_data()
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self._refresh_open_detail_pages()
                self._record_frontend_history("删除配置项", {"names": success}, before_state=before_state)
                self.statusBar().showMessage(f"配置项 '{name}' 已删除。", 3000)
            return

        if not self._current_project_name:
            QMessageBox.warning(self, "操作失败", "当前未打开任何项目，无法删除配置。")
            return

        try:
            resp = self.control.call("configlib.remove", [Arg(index=0, name="name", value=name)])
            self.bottom.output.append(f"[Request: configlib.remove] Name: {name}, Result: {_json_dumps(resp)}\n")
            if resp.get("code") == 0:
                self.refresh_project_data()
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self.statusBar().showMessage(f"配置项 '{name}' 已删除。", 3000)
            else:
                QMessageBox.warning(self, "删除失败", f"服务器返回错误：\n{resp.get('msg', '未知错误')}")
        except Exception as e:
            self.bottom.logs.append(f"[Critical Error] Failed to execute 'configlib.remove': {e}\n")
            QMessageBox.critical(self, "通讯错误", "无法连接到服务器。")

    def _delete_harness_from_detail(self, name: str):
        confirm = QMessageBox.question(
            self,
            "确认删除",
            f"将删除线组：\n\n{name}\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if self.frontend_only:
            before_state = self._capture_frontend_history_state()
            success, failed = self.frontend_store.remove_bundles([name])
            if failed:
                QMessageBox.warning(self, "删除失败", failed[0][1])
                return
            if success:
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self._refresh_open_detail_pages()
                self._record_frontend_history("删除线组", {"names": success}, before_state=before_state)
                self.statusBar().showMessage(f"线组 '{name}' 已删除。", 3000)
            return

        removed = self.explorer.remove_harness_names([name])
        if removed:
            self._refresh_open_detail_pages()
            self.statusBar().showMessage(f"线组 '{name}' 已从当前界面移除。", 3000)
            QMessageBox.information(self, "尚未对接", "当前版本的线组删除尚未接入后端接口，已先更新当前界面。")
        else:
            QMessageBox.warning(self, "删除失败", f"未找到线组“{name}”。")

    def open_config_relation_tab(self, name: str, data: dict):
        try:
            detail = self._build_analysis_store().get_config_detail(name)
        except ValueError:
            detail = {
                "name": name,
                "comment": data.get("comment", "") or "",
                "expr": data.get("expr", data.get("value", "")) or "",
                "realvalue": data.get("realvalue", "") or "",
                "depends_on_tree": [],
                "required_by_tree": [],
                "bundle_refs": [],
            }

        page = self._find_existing_page(ConfigRelationPage, name)
        if page is not None:
            page.reload(detail)
            self._activate_page(page)
            return

        page = ConfigRelationPage(name=name, detail=detail, parent=self)
        page.requestRefresh.connect(lambda cfg_name: self.open_config_relation_tab(cfg_name, {}))
        page.requestEdit.connect(self._edit_config_from_detail)
        page.requestDelete.connect(self._delete_config_from_detail)
        page.requestOpenConfig.connect(lambda cfg_name: self.open_config_relation_tab(cfg_name, {}))
        page.requestOpenHarness.connect(lambda harness_name: self.open_harness_detail_tab(harness_name, {}))

        self._add_center_tab(page, f"{name} (Relations)")
        self.center_tabs.setCurrentWidget(page)

    def open_module_canvas_tab(self, name: str, data: dict):
        tab_title = f"{name} (Canvas)"
        for i in range(self.center_tabs.count()):
            if self.center_tabs.tabText(i) == tab_title:
                self.center_tabs.setCurrentIndex(i)
                return

        # data 可能是从 item 里带来的，也可能不完整；这里优先用 explorer 库里的最新定义兜底
        module_data = self._get_module_data_or_stub(name)
        # 如果信号传进来的 data 更完整，可以合并（以 data 为准覆盖）
        if isinstance(data, dict):
            module_data = {**module_data, **data}

        page = self._make_module_canvas_page(name, module_data)
        # self.center_tabs.addTab(page, tab_title)
        self._add_center_tab(page, tab_title)
        self.center_tabs.setCurrentWidget(page)

    def _find_code_block_page(self, module_name: str, block_kind: str, block_name: str):
        for widget in self._iter_open_pages():
            if not isinstance(widget, CodeBlockEditorPage):
                continue
            if widget.module_name != module_name:
                continue
            if widget.block_kind != block_kind:
                continue
            if widget.block_name != block_name:
                continue
            return widget
        return None

    def _append_code_symbol(self, rows: list[dict], category: str, name: str, kind: str, detail: str, insert: str | None = None):
        symbol_name = _strip_text(name)
        if not symbol_name:
            return
        rows.append({
            "category": category,
            "name": symbol_name,
            "kind": kind,
            "detail": detail,
            "insert": insert if insert is not None else symbol_name,
        })

    def _code_identifier_name(self, name: str) -> str:
        safe = re.sub(r"\W+", "_", _strip_text(name))
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe or "user_block"

    def _build_code_block_analysis_context(self, module_name: str, block_kind: str, block_data: dict | None = None) -> dict:
        store = self._build_analysis_store()
        module_dict = store.list_modules()
        module_data = copy.deepcopy(module_dict.get(module_name, self._get_module_data_or_stub(module_name)))
        block = copy.deepcopy(block_data or {})

        symbols: list[dict] = []
        notes: list[str] = []

        for cfg in store.list_configs():
            self._append_code_symbol(
                symbols,
                "全局配置",
                cfg.get("name", ""),
                "常量",
                f"值：{cfg.get('value', '') or '（空）'}",
            )

        for bundle in store.list_bundles():
            self._append_code_symbol(
                symbols,
                "全局线组",
                bundle.get("name", ""),
                "类型",
                bundle.get("comment", "") or "全局线组类型",
            )

        for cfg in _safe_list(module_data.get("local_cfgs", [])):
            self._append_code_symbol(
                symbols,
                "本地配置",
                cfg.get("name", ""),
                "常量",
                f"默认值：{cfg.get('default', '') or '（空）'}",
            )

        for harness in _safe_list(module_data.get("local_harnesses", [])):
            self._append_code_symbol(
                symbols,
                "本地线组",
                harness.get("name", ""),
                "类型",
                harness.get("comment", "") or f"定义模式：{harness.get('mode', '') or 'struct'}",
            )

        for storage in _safe_list(module_data.get("storages", [])):
            type_text = _strip_text(storage.get("type", "")) or _strip_text(storage.get("int_len", "")) or "未定类型"
            self._append_code_symbol(
                symbols,
                "存储对象",
                storage.get("name", ""),
                "存储",
                f"类型：{type_text}",
            )

        for pipe in _safe_list(module_data.get("pipe_ports", [])):
            self._append_code_symbol(
                symbols,
                "管道端口",
                pipe.get("name", ""),
                f"pipe {pipe.get('dir', '') or '?'}",
                f"数据类型：{pipe.get('dtype', '') or '（未填写）'}",
            )

        for rpc in _safe_list(module_data.get("rpcs", [])):
            detail_lines = []
            if _strip_text(rpc.get("params", "")):
                detail_lines.append(f"参数：{rpc.get('params', '')}")
            if _strip_text(rpc.get("returns", "")):
                detail_lines.append(f"返回：{rpc.get('returns', '')}")
            self._append_code_symbol(
                symbols,
                "请求/服务端口",
                rpc.get("name", ""),
                rpc.get("kind", "") or "rpc",
                "；".join(detail_lines) or (rpc.get("comment", "") or "模块对外端口"),
            )

        for submodule in _safe_list(module_data.get("submodules", [])):
            self._append_code_symbol(
                symbols,
                "模块实例",
                submodule.get("inst", ""),
                "实例",
                f"引用模块：{submodule.get('module', '') or '（未填写）'}",
            )

        helper_code = module_data.get("helper_code", [])
        helper_text = helper_code if isinstance(helper_code, str) else "\n".join(str(line) for line in helper_code)
        if helper_text.strip() or block_kind == "helper":
            self._append_code_symbol(
                symbols,
                "帮助函数",
                "helper_code()",
                "函数",
                "帮助函数代码段入口",
                insert="helper_code()",
            )

        block_name = ""
        signature = "void user_block()"
        if block_kind == "clock":
            block_name = _strip_text(block.get("name", ""))
            signature = f"void {self._code_identifier_name(block_name)}()"
            notes.append("时钟代码块的真实触发时序和上下文声明以后端生成结果为准。")
        elif block_kind == "service":
            port_name = _strip_text(block.get("port", ""))
            block_name = port_name
            signature = f"void on_service_{self._code_identifier_name(port_name)}()"
            notes.append("服务代码块的请求/返回值声明以后端分析结果为准。")
        elif block_kind == "subreq":
            inst_name = _strip_text(block.get("inst", ""))
            port_name = _strip_text(block.get("port", ""))
            block_name = f"{inst_name}.{port_name}" if inst_name and port_name else inst_name or port_name
            signature = f"void on_subreq_{self._code_identifier_name(inst_name)}_{self._code_identifier_name(port_name)}()"
            notes.append("子实例请求代码块会绑定到对应实例和请求端口，真实参数声明以后端分析结果为准。")
        elif block_kind == "helper":
            block_name = "helper_code"
            signature = "void helper_code()"
            notes.append("帮助函数代码段可被模块内其他用户代码复用。")

        if not _safe_list(module_data.get("storages", [])):
            notes.append("当前模块没有定义存储对象。")
        if not _safe_list(module_data.get("submodules", [])):
            notes.append("当前模块没有子实例。")

        return {
            "module_name": module_name,
            "block_kind": block_kind,
            "block_name": block_name,
            "prologue": "\n".join([
                "// 前端预览声明（真实代码生成以后端接口文档与分析结果为准）",
                signature,
                "{",
                "    // --- user code begin ---",
            ]),
            "epilogue": "\n".join([
                "    // --- user code end ---",
                "}",
            ]),
            "symbols": symbols,
            "notes": notes,
        }

    def _code_block_tab_title(self, module_name: str, block_kind: str, block_name: str) -> str:
        if block_kind == "clock":
            kind_text = "Clock Code"
        elif block_kind == "service":
            kind_text = "Service Code"
        elif block_kind == "subreq":
            kind_text = "Subreq Code"
        elif block_kind == "helper":
            kind_text = "Helper Code"
        else:
            kind_text = block_kind
        return f"{module_name}::{block_name} ({kind_text})"

    def _code_block_display_name(self, block_kind: str, row: dict) -> str:
        if block_kind == "clock":
            return _strip_text(row.get("name", ""))
        if block_kind == "service":
            return _strip_text(row.get("port", ""))
        if block_kind == "subreq":
            inst = _strip_text(row.get("inst", ""))
            port = _strip_text(row.get("port", ""))
            return f"{inst}.{port}" if inst and port else inst or port
        if block_kind == "helper":
            return "helper_code"
        return _strip_text(row.get("name", ""))

    def _find_code_block_row(self, module_data: dict, block_kind: str, block_name: str):
        if block_kind == "clock":
            rows = _safe_list(module_data.get("clock_blocks", []))
            return next((row for row in rows if _strip_text(row.get("name", "")) == block_name), None)
        if block_kind == "service":
            rows = _safe_list(module_data.get("service_blocks", []))
            return next((row for row in rows if _strip_text(row.get("port", "")) == block_name), None)
        if block_kind == "subreq":
            rows = _safe_list(module_data.get("subreq_blocks", []))
            inst_name = ""
            port_name = block_name
            if "|" in block_name:
                inst_name, port_name = block_name.split("|", 1)
            return next(
                (
                    row for row in rows
                    if _strip_text(row.get("inst", "")) == _strip_text(inst_name)
                    and _strip_text(row.get("port", "")) == _strip_text(port_name)
                ),
                None,
            )
        if block_kind == "helper":
            helper = module_data.get("helper_code", [])
            if isinstance(helper, list):
                code = "\n".join(str(line) for line in helper)
            else:
                code = str(helper or "")
            return {"name": "helper_code", "code": code}
        return None

    def _open_code_block_tab(self, module_name: str, block_kind: str, block_name: str, block_data: dict | None = None):
        module_data = self._get_module_data_or_stub(module_name)
        block = block_data if isinstance(block_data, dict) else self._find_code_block_row(module_data, block_kind, block_name)
        if not isinstance(block, dict):
            QMessageBox.warning(self, "打开失败", f"未找到代码块“{block_name}”。")
            return

        display_name = self._code_block_display_name(block_kind, block)
        analysis_context = self._build_code_block_analysis_context(module_name, block_kind, block)
        page = self._find_code_block_page(module_name, block_kind, display_name)
        if page is not None:
            page.reload(module_name, block_kind, block, analysis_context=analysis_context)
            self._activate_page(page)
            return

        page = CodeBlockEditorPage(
            module_name=module_name,
            block_kind=block_kind,
            block_data=block,
            analysis_context=analysis_context,
            parent=self,
        )
        page.saveRequested.connect(self._save_code_block_from_editor)
        title = self._code_block_tab_title(module_name, block_kind, display_name)
        self._add_center_tab(page, title)
        self.center_tabs.setCurrentWidget(page)

    def open_clock_block_code_tab(self, module_name: str, block_name: str, block_data: dict | None = None):
        self._open_code_block_tab(module_name, "clock", block_name, block_data)

    def open_service_block_code_tab(self, module_name: str, port_name: str, block_data: dict | None = None):
        self._open_code_block_tab(module_name, "service", port_name, block_data)

    def open_subreq_block_code_tab(self, module_name: str, inst_name: str, port_name: str, block_data: dict | None = None):
        self._open_code_block_tab(module_name, "subreq", f"{inst_name}|{port_name}", block_data)

    def open_helper_code_tab(self, module_name: str, block_data: dict | None = None):
        self._open_code_block_tab(module_name, "helper", "helper_code", block_data)

    def _save_code_block_from_editor(self, module_name: str, block_kind: str, original_name: str, payload: dict):
        before_state = self._capture_frontend_history_state() if self.frontend_only else None
        module_data = copy.deepcopy(self._get_module_data_or_stub(module_name))
        updated_row = None

        if block_kind == "clock":
            new_name = _strip_text(payload.get("name", ""))
            if not new_name:
                QMessageBox.warning(self, "保存失败", "代码块名不能为空。")
                return

            rows = _safe_list(module_data.get("clock_blocks", []))
            if any(_strip_text(row.get("name", "")) == new_name and _strip_text(row.get("name", "")) != original_name for row in rows):
                QMessageBox.warning(self, "保存失败", f"时钟代码块“{new_name}”已存在。")
                return

            found = False
            for row in rows:
                if _strip_text(row.get("name", "")) != original_name:
                    continue
                row.update(payload)
                updated_row = dict(row)
                found = True
                break

            if not found or updated_row is None:
                QMessageBox.warning(self, "保存失败", f"时钟代码块“{original_name}”已不存在，请重新从画布打开。")
                return

            if original_name != new_name:
                for row in _safe_list(module_data.get("orders", [])):
                    if _strip_text(row.get("dst_inst", "")) == original_name:
                        row["dst_inst"] = new_name

            module_data["clock_blocks"] = rows

        elif block_kind == "service":
            port_name = _strip_text(payload.get("port", ""))
            if not port_name:
                QMessageBox.warning(self, "保存失败", "服务端口不能为空。")
                return

            rows = _safe_list(module_data.get("service_blocks", []))
            for row in rows:
                if _strip_text(row.get("port", "")) != original_name:
                    continue
                row.update(payload)
                updated_row = dict(row)
                break

            if updated_row is None:
                updated_row = dict(payload)
                rows.append(updated_row)

            module_data["service_blocks"] = rows

        elif block_kind == "subreq":
            inst_name = _strip_text(payload.get("inst", ""))
            port_name = _strip_text(payload.get("port", ""))
            if not inst_name or not port_name:
                QMessageBox.warning(self, "保存失败", "子实例名和请求端口名不能为空。")
                return

            rows = _safe_list(module_data.get("subreq_blocks", []))
            for row in rows:
                row_key = f"{_strip_text(row.get('inst', ''))}|{_strip_text(row.get('port', ''))}"
                if row_key != original_name:
                    continue
                row.update(payload)
                updated_row = dict(row)
                break

            if updated_row is None:
                updated_row = dict(payload)
                rows.append(updated_row)

            module_data["subreq_blocks"] = rows

        elif block_kind == "helper":
            module_data["helper_code"] = (payload.get("code", "") or "").splitlines()
            updated_row = {
                "name": "helper_code",
                "code": payload.get("code", "") or "",
            }

        else:
            QMessageBox.information(self, "尚未实现", f"当前暂不支持 {block_kind}。")
            return

        page = self.sender()
        if isinstance(page, CodeBlockEditorPage):
            page.reload(
                module_name,
                block_kind,
                updated_row,
                analysis_context=self._build_code_block_analysis_context(module_name, block_kind, updated_row),
            )
            self._set_page_title(
                page,
                self._code_block_tab_title(module_name, block_kind, self._code_block_display_name(block_kind, updated_row)),
            )

        kind_text = {
            "clock": "保存时钟代码块",
            "service": "保存服务代码块",
            "subreq": "保存子实例请求代码块",
            "helper": "保存帮助函数代码",
        }.get(block_kind, "保存代码块")
        self._pending_module_history_entry = (
            kind_text,
            {"module": module_name, "kind": block_kind, "name": self._code_block_display_name(block_kind, updated_row)},
        )
        self._on_module_updated_from_canvas(module_name, module_data, before_state=before_state)

    def open_harness_detail_tab(self, name: str, data: dict):
        try:
            detail = self._build_analysis_store().get_bundle_detail(name)
        except ValueError:
            alias_target = ""
            members = data.get("members", []) or []
            if data.get("alias") and members:
                alias_target = members[0].get("type", "") or ""
            detail = {
                "name": name,
                "comment": data.get("comment", "") or "",
                "tags": data.get("tags", "") or "",
                "is_alias": bool(data.get("alias", False)),
                "alias_target": alias_target,
                "members": members,
                "enums": data.get("enums", []) or [],
                "depends_on_tree": [],
                "required_by_tree": [],
                "config_refs": [],
            }

        page = self._find_existing_page(HarnessDetailPage, name)
        if page is not None:
            page.reload(detail)
            self._activate_page(page)
            return

        page = HarnessDetailPage(name=name, detail=detail, parent=self)
        page.requestRefresh.connect(lambda harness_name: self.open_harness_detail_tab(harness_name, {}))
        page.requestEdit.connect(self._edit_harness_from_detail)
        page.requestDelete.connect(self._delete_harness_from_detail)
        page.requestOpenConfig.connect(lambda cfg_name: self.open_config_relation_tab(cfg_name, {}))
        page.requestOpenHarness.connect(lambda harness_name: self.open_harness_detail_tab(harness_name, {}))

        self._add_center_tab(page, f"{name} (Harness)")
        self.center_tabs.setCurrentWidget(page)

    # 初始化业务
    def _update_conn_ui(self, is_connected: bool, message: str):
        """Update the bottom-right connection status label."""
        self._is_connected = is_connected
        self.conn_status_label.setText(message)
        if is_connected:
            self.conn_status_label.setStyleSheet("color: green;")
        else:
            self.conn_status_label.setStyleSheet("color: red;")

    def update_project_display(self, name: str | None):
        """
        如果项目名称发生变化（例如从 None 变为 'proj1'），自动触发数据刷新。
        """
        # 1. 状态比对：只有当项目真的变了，才进行后续操作，避免 Monitor 频繁刷新导致 UI 卡顿
        if name == self._current_project_name:
            return
        print(f"[TCP] Update Project Display: {self._current_project_name} -> {name}")

        # 2. 更新内部状态
        old_name = self._current_project_name
        self._current_project_name = name

        if old_name != name:
            self._close_all_project_pages()
            self._frontend_build_info = None
            self._frontend_run_active = False
            self._stop_frontend_run_stream()
            self.bottom.set_output_status("显示最近一次 Build / Run 的标准输出。")

        # 3. 更新顶部 Label UI
        if name:
            self.project_label.setText(f"\u5f53\u524d\u9879\u76ee: {name}") # "当前项目: name"
            self.project_label.setStyleSheet("margin-right: 15px; color: #0078d4; font-weight: bold;")
            # 【核心修复】：项目状态变为“有”时，立即请求最新配置数据
            print(f"[Logic] Project detected ({name}), auto-refreshing config list...")
            if self.frontend_only:
                old_suspended = self._history_recording_suspended
                self._history_recording_suspended = True
                try:
                    self.refresh_project_data()
                    self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                    self._refresh_project_module_data()
                    self.refresh_project_debug_data()
                finally:
                    self._history_recording_suspended = old_suspended
                self._reset_frontend_history()
                self._set_ui_state("idle")
            else:
                self.refresh_project_data()
                self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                self._refresh_project_module_data()
                self.refresh_project_debug_data()
        else:
            self.project_label.setText("\u5f53\u524d\u65e0\u5df2\u6253\u5f00\u9879\u76ee") # "当前无已打开项目"
            self.project_label.setStyleSheet("margin-right: 15px; color: #666; font-weight: bold;")

            print(f"[Logic] Project closed, clearing explorer...")
            old_suspended = self._history_recording_suspended
            self._history_recording_suspended = True
            try:
                self.explorer.clear_configs()
                self.explorer.clear_harnesses()
                self.explorer.clear_modules()
                self.explorer.clear_debug_points()
            finally:
                self._history_recording_suspended = old_suspended
            if self.frontend_only:
                self._reset_frontend_history()
                self._set_ui_state("idle")


    def on_close_opened(self):
        """
        关闭项目流程：
        1. 检查是否有打开的项目
        2. 提示是否保存
        3. 执行关闭(cancel)
        """
        if self.frontend_only:
            if not self._current_project_name:
                QMessageBox.information(self, "提示", "当前没有已打开的前端工作区。")
                return

            self.update_project_display(None)
            self.explorer.clear_configs()
            self.explorer.clear_harnesses()
            self.statusBar().showMessage("前端工作区已关闭。", 3000)
            return

        # 1. 检查是否有项目
        if not self._current_project_name:
            QMessageBox.information(self, "提示", "当前没有已打开的项目。")
            return

        print("准备关闭当前项目...")

        # 2. 询问是否保存
        reply = QMessageBox.question(
            self,
            "关闭项目",
            f"是否保存对项目 '{self._current_project_name}' 的更改？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Cancel:
            return

        # 3. 如果选择保存
        if reply == QMessageBox.StandardButton.Yes:
            # 调用保存逻辑
            if not self._do_save_project():
                # 如果保存失败（返回 False），询问用户是否强制关闭
                force_close = QMessageBox.warning(
                    self,
                    "保存失败",
                    "项目保存失败。是否强制关闭项目？\n（强制关闭将丢失未保存的更改）",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if force_close == QMessageBox.StandardButton.No:
                    return # 用户取消关闭

        # 4. 执行关闭请求 (cancel)
        try:
            resp = self.control.call("cancel", [])
            res_str = _json_dumps(resp)
            self.bottom.output.append(f"[Request: cancel] Result: {res_str}\n")

            if resp.get("code") == 0:
                self.update_project_display(None)  # 关闭成功，重置显示
                self.explorer.clear_configs()      # 清空侧边栏
                self.explorer.clear_harnesses()  # 清空线束
                self.statusBar().showMessage("项目已关闭。", 3000)
            else:
                self.statusBar().showMessage(f"Error: {resp.get('msg')}", 5000)
                QMessageBox.warning(self, "关闭失败", f"服务器返回错误: {resp.get('msg')}")

        except Exception as e:
            error_msg = f"[Critical Error] Failed to execute 'cancel': {str(e)}"
            print(error_msg)
            self.bottom.logs.append(error_msg + "\n")

    def on_open_file_list(self):
        """
        调用 list 方法获取项目列表，弹出对话框供用户选择并 load
        """
        if self.frontend_only:
            project_names = self._list_frontend_workspace_names()
            current_name = (self._current_project_name or self._frontend_project_name or "").strip()
            unsaved_label = ""
            if current_name and current_name not in project_names:
                unsaved_label = f"{current_name}（当前工作区，未保存）"
                project_names = [unsaved_label] + project_names

            if not project_names:
                QMessageBox.information(self, "提示", "当前没有已保存的前端工作区。你可以先创建或保存一个工作区。")
                return

            dialog = QInputDialog(self)
            dialog.setWindowTitle("选择前端工作区")
            dialog.setLabelText("请从列表中选择要打开的前端工作区:")
            dialog.setOkButtonText("打开")
            dialog.setCancelButtonText("取消")
            dialog.setComboBoxItems(project_names)
            dialog.setComboBoxEditable(False)

            if dialog.exec():
                selected_project = dialog.textValue().strip()
                if not selected_project:
                    return
                if selected_project == unsaved_label:
                    self.update_project_display(current_name)
                    self.statusBar().showMessage(f"已打开当前前端工作区 '{current_name}'。", 3000)
                    return
                if not self._open_frontend_workspace_by_name(selected_project):
                    QMessageBox.warning(self, "打开失败", f"未找到前端工作区“{selected_project}”。")
                    return
                self.statusBar().showMessage(f"已打开前端工作区 '{selected_project}'。", 3000)
            return

        print("正在获取项目列表...")
        try:
            # 1. 调用 list 命令
            resp = self.control.call("list", [])
            # 前端格式化显示返回数据
            self.format_json_bottom(resp)
            if resp.get("code") != 0:
                QMessageBox.warning(self, "获取列表失败", f"服务器返回: {resp.get('msg')}")
                return

            # 2. 解析项目名称列表 (根据文档，结果在 project_names 字段)
            # 注意：某些后端可能直接把列表放在结果根目录，也可能放在特定的键下
            list_results = resp.get("list_results", {})
            project_names = list_results.get("project_names", [])

            if not project_names:
                QMessageBox.information(self, "提示", "项目库中暂无项目。")
                return

            # 3. 弹出选择对话框
            dialog = QInputDialog(self)
            dialog.setWindowTitle("选择项目")
            dialog.setLabelText("请从列表中选择要加载的项目:")
            dialog.setOkButtonText("加载")
            dialog.setCancelButtonText("取消")

            # 设置下拉列表项
            dialog.setComboBoxItems(project_names)
            dialog.setComboBoxEditable(False)

            # 4. 如果用户点击加载
            if dialog.exec():
                selected_project = dialog.textValue()
                if selected_project:
                    self._do_load_project(selected_project)

        except Exception as e:
            error_msg = f"[Critical Error] Failed to list projects: {str(e)}"
            self.bottom.logs.append(error_msg + "\n")
            QMessageBox.critical(self, "列表获取错误", "无法连接到服务器。")

    # 加载load请求
    def _do_load_project(self, name: str):
        """
        内部方法：执行具体的 load 请求
        """
        print(f"正在加载项目: {name}")
        try:
            # 构造参数：name 是必需参数
            load_arg = Arg(index=0, name="name", value=name)

            # 调用 load 命令
            resp = self.control.call("load", [load_arg])

            # 记录日志到 output 面板
            res_str = _json_dumps(resp)

            if resp.get("code") == 0:
                self.update_project_display(name)  # 加载成功，更新顶部显示
                self.refresh_project_data()

            self.bottom.output.append(f"[Request: load] Name: {name}, Result: {res_str}\n")

            if resp.get("code") == 0:
                # 按照文档，load 成功会返回 logs
                logs = resp.get("logs", [])
                for log_line in logs:
                    self.bottom.logs.append(f"[Load Log] {log_line}\n")

                self.statusBar().showMessage(f"项目 '{name}' 已成功加载。", 3000)
                # TODO: 下一步在此处触发 Explorer 刷新或打开主画布
            else:
                msg = resp.get("msg", "加载失败")
                QMessageBox.warning(self, "加载项目失败", f"错误码: {resp.get('code')}\n原因: {msg}")
                self.statusBar().showMessage(f"加载失败: {msg}", 5000)

        except Exception as e:
            error_msg = f"[Critical Error] Failed to execute 'load': {str(e)}"
            self.bottom.logs.append(error_msg + "\n")

    def on_connect(self):
        if self.frontend_only:
            self._update_conn_ui(True, "前端开发模式")
            self.update_project_display(self._frontend_project_name)
            self.statusBar().showMessage("当前为前端开发模式，未连接真实后端。", 3000)
            return

        ok = self.control.connect()
        if ok:
            self._update_conn_ui(True, "\u5df2\u8fde\u63a5")
            self.log_client.start()
            self.check_initial_project_status()
        else:
            self._update_conn_ui(False, "\u8fde\u63a5\u5931\u8d25")

    def on_disconnect(self):
        if self.frontend_only:
            self.statusBar().showMessage("前端开发模式下无需断开后端连接。", 3000)
            return

        self._stop_frontend_run_stream()
        self.log_client.stop()
        self.control.close()
        self._update_conn_ui(False, "\u5df2\u65ad\u5f00")
        self.update_project_display(None)
        self.explorer.clear_configs()
        self.explorer.clear_harnesses()
        self.explorer.clear_debug_points()

    def on_ping(self):
        if self.frontend_only:
            project_name = self._current_project_name or self._frontend_project_name or "frontend_demo"
            stats = {
                "configs": len(self.frontend_store.list_configs()),
                "bundles": len(self.frontend_store.list_bundles()),
                "modules": len(getattr(self.explorer, "_modules", {}) or {}),
                "debug_points": len(self.frontend_store.list_debug_points()),
            }
            line = (
                f"[Ping] frontend_only project={project_name} "
                f"configs={stats['configs']} bundles={stats['bundles']} "
                f"modules={stats['modules']} debug_points={stats['debug_points']}"
            )
            self.bottom.logs.append(line + "\n")
            self.statusBar().showMessage("前端开发模式连接检查通过。", 3000)
            return

        try:
            resp = self.control.call("info", [])
            self.bottom.output.append(f"[Request: info] Result: {_json_dumps(resp)}\n")
            if isinstance(resp, dict):
                code = resp.get("code", -1)
                if code == 0:
                    project_name = _strip_text((resp.get("results") or {}).get("name", ""))
                    label = project_name or "当前无已打开项目"
                    self.statusBar().showMessage(f"连接检查通过，项目：{label}", 3000)
                else:
                    self.statusBar().showMessage("连接检查已返回，但当前没有可用项目信息。", 3000)
            else:
                self.statusBar().showMessage("连接检查返回了非预期结果。", 3000)
        except Exception as e:
            self.bottom.logs.append(f"[Critical Error] Failed to execute 'info': {e}\n")
            QMessageBox.critical(self, "连接检查失败", "无法连接到服务器。")

    def on_new_project(self):
        """
        点击 'New Project' 时触发：弹出中文按钮的对话框获取名称并调用后端 create 接口
        """
        # 1. 创建输入对话框实例
        dialog = QInputDialog(self)
        dialog.setWindowTitle("创建新项目")
        dialog.setLabelText("请输入项目名称:")
        dialog.setOkButtonText("确认")
        dialog.setCancelButtonText("取消")
        dialog.setTextValue("")  # 默认值为空

        # 设置输入框的显示模式（普通文本）
        dialog.setInputMode(QInputDialog.InputMode.TextInput)

        # 2. 显示对话框并获取结果
        if dialog.exec():
            project_name = dialog.textValue().strip()

            if not project_name:
                QMessageBox.warning(self, "验证失败", "项目名称不能为空。")
                return

            if self.frontend_only:
                self.frontend_store.reset(project_name)
                self._frontend_project_name = self.frontend_store.project_name
                if self._current_project_name == self._frontend_project_name:
                    old_suspended = self._history_recording_suspended
                    self._history_recording_suspended = True
                    try:
                        self.refresh_project_data()
                        self.refresh_project_bundle_data(include_reference=False, include_definition=True)
                        self._refresh_project_module_data()
                        self.refresh_project_debug_data()
                    finally:
                        self._history_recording_suspended = old_suspended
                    self._reset_frontend_history()
                else:
                    self.update_project_display(self._frontend_project_name)
                self.statusBar().showMessage(f"前端工作区 '{self._frontend_project_name}' 已创建。", 3000)
                return

            print(f"New Project Request: {project_name}")

            try:
                # 构造参数：必需参数 name, 对应 index 0
                project_name_arg = Arg(index=0, name="name", value=project_name)

                # 调用后端接口
                resp = self.control.call("create", [project_name_arg])

                # 将结果显示在底部面板
                res_str = _json_dumps(resp)
                self.bottom.output.append(f"[Request: create] Name: {project_name}, Result: {res_str}\n")

                # 3. 处理返回码
                code = resp.get("code")
                if code == 0:
                    self.statusBar().showMessage(f"项目 '{project_name}' 创建成功。", 3000)
                else:
                    msg = resp.get("msg", "未知错误")
                    # 将错误消息也尽量友好提示
                    QMessageBox.warning(self, "创建失败", f"服务器返回错误: {msg}")
                    self.statusBar().showMessage(f"错误: {msg}", 5000)

            except Exception as e:
                error_msg = f"[Critical Error] Failed to execute 'create': {str(e)}"
                print(error_msg)
                self.bottom.logs.append(error_msg + "\n")
                QMessageBox.critical(self, "连接错误", "无法与后端通讯，请检查连接状态。")

    def on_open_file(self):
        try:
            # call 现在保证会返回一个包含 'code' 的字典，不会轻易抛出 crash 异常
            resp = self.control.call("list", [])
            # 将结果格式化显示在底部的 output 面板
            self.format_json_bottom(resp)

            if resp.get("code") != 0:
                self.statusBar().showMessage(f"Error: {resp.get('msg')}", 5000)
            else:
                self.statusBar().showMessage("Project list updated.", 3000)

        except Exception as e:
            # 最后的防线：确保 UI 线程捕获所有未预料的错误
            error_msg = f"[Critical Error] Failed to execute 'list': {str(e)}"
            print(error_msg)
            self.bottom.logs.append(error_msg + "\n")

    def on_save_all(self):
        """
        工具栏 - 保存项目按钮响应
        """
        if self.frontend_only:
            path = self._save_frontend_workspace()
            if path is not None:
                self.statusBar().showMessage(f"前端工作区已保存到 {path.name}。", 3000)
            return

        if not self._current_project_name:
            QMessageBox.warning(self, "提示", "当前没有打开的项目，无法保存。")
            return

        self._do_save_project()

    def _do_save_project(self) -> bool:
        """
        内部辅助方法：执行 save 命令
        返回: True(保存成功), False(保存失败)
        """
        if self.frontend_only:
            self.statusBar().showMessage("前端开发模式下无需保存到后端。", 3000)
            return True

        print("正在保存项目...")
        try:
            # 调用 save 命令，无参数
            resp = self.control.call("save", [])
            res_str = _json_dumps(resp)
            self.bottom.output.append(f"[Request: save] Result: {res_str}\n")

            if resp.get("code") == 0:
                self.statusBar().showMessage("项目保存成功。", 3000)
                return True
            else:
                msg = resp.get("msg", "未知错误")
                QMessageBox.warning(self, "保存失败", f"无法保存项目:\n{msg}")
                return False

        except Exception as e:
            error_msg = f"[Critical Error] Failed to execute 'save': {str(e)}"
            print(error_msg)
            self.bottom.logs.append(error_msg + "\n")
            QMessageBox.critical(self, "通讯错误", f"保存请求发送失败: {e}")
            return False

    def on_import_project(self):
        if self.frontend_only:
            path_text, _ = QFileDialog.getOpenFileName(
                self,
                "导入前端工作区",
                str(self._frontend_workspace_root()),
                "JSON Files (*.json);;All Files (*)",
            )
            if not path_text:
                return
            path = Path(path_text)
            try:
                payload = self._read_frontend_workspace_payload(path)
                state = payload.get("state", {})
                project_name = (state.get("project_name") or path.stem).strip() or path.stem
                self._apply_frontend_workspace_payload(payload)
                saved_path = self._save_frontend_workspace(project_name)
                self.statusBar().showMessage(
                    f"已导入前端工作区 '{project_name}'。" if saved_path is None else f"已导入前端工作区 '{project_name}' 并保存到本地库。",
                    3000,
                )
            except Exception as e:
                QMessageBox.warning(self, "导入失败", f"无法导入工作区文件：\n{e}")
            return

        QMessageBox.information(self, "尚未对接", "真实后端 Import 流程尚未接入。")

    def on_export_harness(self):
        if self.frontend_only:
            if not self._ensure_frontend_project_open("导出前端工作区"):
                return
            default_name = f"{self._current_project_name or self._frontend_project_name or 'frontend_workspace'}.json"
            path_text, _ = QFileDialog.getSaveFileName(
                self,
                "导出前端工作区",
                str(self._frontend_workspace_root() / default_name),
                "JSON Files (*.json);;All Files (*)",
            )
            if not path_text:
                return
            path = Path(path_text)
            payload = self._build_frontend_workspace_payload()
            try:
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self._append_log(f"已导出前端工作区到：{path}")
                self.statusBar().showMessage(f"前端工作区已导出到 {path.name}。", 3000)
            except Exception as e:
                QMessageBox.warning(self, "导出失败", f"无法导出工作区：\n{e}")
            return

        QMessageBox.information(self, "尚未对接", "真实后端 Export 流程尚未接入。")

    def on_delete_project(self):
        if self.frontend_only:
            project_names = self._list_frontend_workspace_names()
            if not project_names:
                QMessageBox.information(self, "提示", "当前没有可删除的前端工作区。")
                return

            dialog = QInputDialog(self)
            dialog.setWindowTitle("删除前端工作区")
            dialog.setLabelText("请选择要删除的前端工作区:")
            dialog.setOkButtonText("删除")
            dialog.setCancelButtonText("取消")
            dialog.setComboBoxItems(project_names)
            dialog.setComboBoxEditable(False)
            if not dialog.exec():
                return

            name = dialog.textValue().strip()
            if not name:
                return

            confirm = QMessageBox.question(
                self,
                "确认删除",
                f"将删除前端工作区：\n\n{name}\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

            if not self._delete_frontend_workspace_by_name(name):
                QMessageBox.warning(self, "删除失败", f"未找到前端工作区“{name}”。")
                return

            if name == self._current_project_name:
                self.frontend_store.reset("frontend_demo")
                self._frontend_project_name = self.frontend_store.project_name
                self.update_project_display(None)
            self._append_log(f"已删除前端工作区：{name}")
            self.statusBar().showMessage(f"前端工作区 '{name}' 已删除。", 3000)
            return

        QMessageBox.information(self, "尚未对接", "真实后端 Delete 流程尚未接入。")

    def on_undo(self):
        if self.history.can_undo():
            self.history.undo()
            return
        self.statusBar().showMessage("当前没有可撤销的前端操作。", 2500)

    def on_redo(self):
        if self.history.can_redo():
            self.history.redo()
            return
        self.statusBar().showMessage("当前没有可重做的前端操作。", 2500)

    def on_cut(self):
        widget = self._focused_text_widget()
        if widget is None:
            self.statusBar().showMessage("当前焦点不支持剪切。", 2000)
            return
        if hasattr(widget, "cut"):
            widget.cut()

    def on_copy(self):
        widget = self._focused_text_widget()
        if widget is None:
            self.statusBar().showMessage("当前焦点不支持复制。", 2000)
            return
        if hasattr(widget, "copy"):
            widget.copy()

    def on_paste(self):
        widget = self._focused_text_widget()
        if widget is None:
            self.statusBar().showMessage("当前焦点不支持粘贴。", 2000)
            return
        if hasattr(widget, "paste"):
            widget.paste()

    def on_run(self):
        if self.frontend_only:
            if not self._ensure_frontend_project_open("运行前端预览"):
                return

            if self._frontend_build_info is None:
                self.on_build()
                if self._frontend_build_info is None:
                    return

            stats = self._frontend_build_info.get("stats", {})
            main_module = self._frontend_build_info.get("main_module", "") or self._current_main_module_name() or "frontend_preview_top"
            self._frontend_run_active = True
            self._set_ui_state("running", "前端预览")
            self.bottom.output.clear()
            for line in [
                "[Run Stdout]",
                f"时间: {self._timestamp_text()}",
                f"项目: {self._current_project_name or '（未打开）'}",
                "状态: 前端预览运行中",
                "",
            ]:
                self._append_output_line(line)
            self._start_frontend_run_stream([
                f"[boot] loading project graph for {main_module}",
                f"[boot] modules={stats.get('modules', 0)} submodules={stats.get('submodules', 0)} pipes={stats.get('pipes', 0)}",
                f"[boot] code_blocks={stats.get('code_blocks', 0)} connections={stats.get('connections', 0)}",
                f"[boot] debug_points={stats.get('debug_points', 0)}",
                "[run] frontend preview mode does not execute real backend simulation.",
                "[out] simulation stdout channel connected (frontend preview).",
                "[tick] cycle=0 ready",
                "[tick] cycle=8 request accepted",
                "[tick] cycle=16 response committed",
                "[run] this session stays active until Stop is triggered.",
            ])
            self._append_log(f"已启动前端预览运行，主模块：{main_module or '（未设置）'}。")
            self.statusBar().showMessage("前端预览运行已启动。", 3000)
            return

        QMessageBox.information(self, "尚未对接", "真实后端 Run 流程尚未接入，当前请继续使用前端预览模式。")

    def on_stop(self):
        if self.frontend_only:
            if not self._frontend_run_active:
                self.statusBar().showMessage("当前没有正在运行的前端预览任务。", 2500)
                return

            self._frontend_run_active = False
            self._stop_frontend_run_stream()
            self._append_output_line(f"[stop] simulation stopped at {self._timestamp_text()}")
            self.bottom.set_output_status("最近一次 Run 已停止。")
            self._set_ui_state("stopped", "前端预览")
            self._append_log("已停止前端预览运行。")
            self.statusBar().showMessage("前端预览运行已停止。", 3000)
            return

        QMessageBox.information(self, "尚未对接", "真实后端 Stop 流程尚未接入。")

    def on_build(self):
        if self.frontend_only:
            if not self._ensure_frontend_project_open("构建前端预览"):
                return

            self._stop_frontend_run_stream()
            if self.ui_preferences.get("clear_output_before_build", True):
                self.bottom.output.clear()
            self._set_ui_state("building", "前端预览")
            artifact = self._build_frontend_artifact()
            stats = artifact.get("stats", {})
            main_module = artifact.get("main_module", "") or "（未设置）"
            warnings = artifact.get("warnings", [])

            lines = [
                f"[scan] configs={stats.get('configs', 0)} bundles={stats.get('bundles', 0)} modules={stats.get('modules', 0)}",
                f"[scan] rpc_ports={stats.get('rpcs', 0)} pipe_ports={stats.get('pipe_ports', 0)} connections={stats.get('connections', 0)}",
                f"[scan] debug_points={stats.get('debug_points', 0)}",
                f"[emit] target main module: {main_module}",
                f"[emit] clock blocks: {stats.get('clock_blocks', 0)}",
                "[link] frontend preview build finished successfully.",
            ]
            if warnings:
                lines.extend(["", "[warning]"] + [f"- {msg}" for msg in warnings])

            self._frontend_build_info = artifact
            self._frontend_run_active = False
            self._show_output_document("Build Stdout", lines, state_text="最近一次 Build 已完成")
            self._set_ui_state("built", "前端预览")
            self._append_log(f"已完成前端预览构建，主模块：{main_module}。")
            self.statusBar().showMessage("前端预览构建完成。", 3000)
            return

        QMessageBox.information(self, "尚未对接", "真实后端 Build 流程尚未接入，当前请继续使用前端预览模式。")

    def on_clean(self):
        if self.frontend_only:
            if self._frontend_build_info is None and not self._frontend_run_active and not self.bottom.output.toPlainText().strip():
                self.statusBar().showMessage("当前没有可清理的前端构建结果。", 2500)
                return

            self._frontend_build_info = None
            self._frontend_run_active = False
            self._stop_frontend_run_stream()
            self.bottom.output.clear()
            self.bottom.set_output_status("最近一次 Build / Run 输出已清理。")
            self.bottom.tabs.setCurrentIndex(2)
            self._set_ui_state("clean")
            self._append_log("已清理前端预览构建与运行输出。")
            self.statusBar().showMessage("前端预览输出已清理。", 3000)
            return

        QMessageBox.information(self, "尚未对接", "真实后端 Clean 流程尚未接入。")

    def on_preferences(self):
        dlg = PreferencesDialog(
            preferences=self.ui_preferences,
            current_theme_label=self._theme_label(self._theme_name),
            parent=self,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        self.ui_preferences = dlg.get_preferences()
        self._save_ui_preferences()
        self._apply_ui_preferences()
        self._append_log("已更新界面偏好设置。")
        self.statusBar().showMessage("Preferences 已保存。", 3000)

    def on_theme(self):
        dlg = ThemeDialog(self._theme_name, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        selected = dlg.selected_theme()
        self._apply_theme(selected, persist=True)
        self._append_log(f"已切换界面主题：{self._theme_label(selected)}。")
        self.statusBar().showMessage(f"主题已切换为：{self._theme_label(selected)}", 3000)

    def on_shortcuts(self):
        dlg = ShortcutsDialog(self._shortcut_specs, parent=self)
        dlg.exec()

    def closeEvent(self, e):
        try:
            self._stop_frontend_run_stream()
            self._save_ui_preferences()
            self.settings.setValue("ui/theme_name", self._theme_name)
            if hasattr(self, "monitor"):
                self.monitor.stop()
                self.monitor.wait(1000)
        except Exception:
            pass

        try:
            self.log_client.stop()
        except Exception:
            pass

        try:
            self.control.close()
        except Exception:
            pass

        super().closeEvent(e)

    def _float_center_tab(self, index: int):
        w = self.center_tabs.widget(index)
        if w is None:
            return

        # 已经浮动就不重复
        if w in self._floating_windows:
            self._floating_windows[w].raise_()
            self._floating_windows[w].activateWindow()
            return

        title = self.center_tabs.tabText(index)

        # 从 tab 移除，但不 delete
        self.center_tabs.removeTab(index)
        w.setParent(None)

        win = FloatingTabWindow(
            title=title,
            content=w,
            on_stick=self._dock_back_widget_from_floating,
            on_close=self._close_floating_widget,
            parent=self,
        )
        self._floating_windows[w] = win
        win.show()

        # 关键：显示后再触发一次 geometry/update，避免画布按 0 尺寸初始化
        w.adjustSize()
        w.updateGeometry()
        w.update()

    def _stick_center_tab(self, index: int):
        """
        在 tab 上右键选择 Stick：如果它本来就在 tab 里，这里就是 no-op。
        真正的贴回发生在浮动窗口的 Stick 按钮里。
        """
        # 这里保持行为明确：已经在 tab 内，无需处理
        w = self.center_tabs.widget(index)
        if w is None:
            return
        # 可选：给用户提示（这里不 print，避免污染日志）
        # self.statusBar().showMessage("Tab already docked.", 2000)

    def _dock_back_widget_from_floating(self, w: QWidget, title: str):
        """
        浮动窗口点 Stick：把 widget 重新塞回 QTabWidget
        """
        # 移除记录
        win = self._floating_windows.pop(w, None)
        if win is not None:
            # 不要 delete w
            pass

        w.setParent(None)
        self.center_tabs.addTab(w, title)
        self.center_tabs.setCurrentWidget(w)

    def _close_floating_widget(self, w: QWidget, title: str):
        """
        浮动窗口点 Close：等价于关闭 tab（销毁页面）
        """
        win = self._floating_windows.pop(w, None)
        if win is not None:
            pass

        w.setParent(None)
        w.deleteLater()

    def format_json_bottom(self, resp):
        # 将结果格式化显示在底部的 output 面板
        res_str = _json_dumps(resp)
        self.bottom.output.append(f"[Request: list] Result: {res_str}\n")
