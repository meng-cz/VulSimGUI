# ui/main_window.py
from __future__ import annotations

import threading
import time
from PyQt6.QtCore import QThread
from service.vulsim_tcp import VulSimControlClient, VulSimLogClient, _json_dumps
from widgets.explorer_dock import ExplorerDock
from widgets.history_dock import HistoryDock
from widgets.bottom_panel import BottomPanel
# from widgets.module_canvas import ModuleCanvas
from widgets.module_canvas_page import ModuleCanvasPage, BaseNodeItem
from widgets.config_relation_page import ConfigRelationPage
from service.vulsim_tcp import Arg

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QEvent
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow, QDockWidget, QTabWidget, QWidget, QToolBar, QStatusBar,
    QToolButton, QMenu, QTabBar, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy, QPushButton,
    QInputDialog, QMessageBox, QLineEdit
)


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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HYPER-IDE")
        self.resize(1400, 900)

        # === 1. 先初始化所有底层通讯实例 ===
        self.control = VulSimControlClient(host="211.87.236.13", port=17995, endian="<")
        self.info_lock = threading.Lock()  # 创建逻辑锁
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

        # 状态栏右侧连接状态标签
        self.conn_status_label = QLabel("正在连接...")
        self._current_project_name: str | None = None
        self._is_connected: bool = False

        # 浮动窗口字典
        self._floating_windows: dict[QWidget, FloatingTabWindow] = {}

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

        self.history = HistoryDock()
        self._add_dock(self.history, Qt.DockWidgetArea.RightDockWidgetArea)

        self.bottom = BottomPanel()
        self._add_dock(self.bottom, Qt.DockWidgetArea.BottomDockWidgetArea)

        # 状态栏
        self.setStatusBar(QStatusBar())
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

        self.monitor = ConnectionMonitor(self.control, self.info_lock)
        self.monitor.status_changed.connect(self._update_conn_ui)
        self.monitor.project_updated.connect(self.update_project_display)
        self.monitor.start()

        # 最后检查初始项目状态
        self.check_initial_project_status()

    def on_update_config_request(self, name: str, value: str):
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

    # 【新增方法】处理添加配置请求
    def on_add_config_request(self, name: str, value: str, comment: str):
        """
        响应 ExplorerDock 的添加配置请求，调用后端 configlib.add 接口
        """
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

    def _on_backend_log(self, log: dict):
        # 注意：这里在子线程回调，严格来说应通过 Qt 信号切回主线程
        # 先“能跑”：用 QMetaObject.invokeMethod 或 pyqtSignal 更规范
        txt = f"[{log.get('level')}] [{log.get('category')}] {log.get('message')}\n"
        self.bottom.logs.append(txt)

    def _on_backend_log_error(self, e: Exception):
        self.bottom.logs.append(f"[LogSocketError] {e}\n")

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

    # 检查是否有已经启动的项目
        # 检查是否有已经启动的项目
    def check_initial_project_status(self):
        """Initial status check using a lock to avoid monitor conflicts."""
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
                        "comment": c
                    })

                # 更新 UI
                self.explorer.update_config_list(config_data_list)
                print(f"[Logic] Refreshed {len(config_data_list)} config items.")
            else:
                msg = resp.get("msg", "Unknown error")
                self.bottom.logs.append(f"同步配置列表失败: {msg}\n")

        except Exception as e:
            err_msg = f"同步配置数据异常: {str(e)}"
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
                ("保存项目", self.on_save_all),
                ("导出", self.on_export_harness),
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
        return page

    def _on_module_updated_from_canvas(self, name: str, data: dict):
        """
        画布页更新模块后：写回全局模块库，并刷新 Explorer 的模块树（如果你实现了刷新函数）。
        """
        # 1) 写回 Explorer 模块库
        if not hasattr(self.explorer, "_modules") or not isinstance(self.explorer._modules, dict):
            self.explorer._modules = {}
        self.explorer._modules[name] = data

        # 2) 刷新树（你需要在 ExplorerDock 里实现/暴露 refresh 方法）
        if hasattr(self.explorer, "_refresh_module_tree"):
            self.explorer._refresh_module_tree()

        # 3) 通知所有打开的 ModuleCanvasPage：某个模块定义更新了，刷新引用它的实例端口
        for i in range(self.center_tabs.count()):
            w = self.center_tabs.widget(i)
            if isinstance(w, ModuleCanvasPage):
                w.refresh_canvas(updated_module_name=name)

    def _open_module_canvas_from_canvas(self, module_name: str):
        # 从画布内部进入子模块：用 explorer 库里的定义兜底
        module_data = self._get_module_data_or_stub(module_name)
        self.open_module_canvas_tab(module_name, module_data)

    def open_config_relation_tab(self, name: str, data: dict):
        # 若已打开同名关联页，则直接切过去，避免重复开一堆 tab
        tab_title = f"{name} (Relations)"
        for i in range(self.center_tabs.count()):
            if self.center_tabs.tabText(i) == tab_title:
                self.center_tabs.setCurrentIndex(i)
                return

        page = ConfigRelationPage(
            name=name,
            comment=data.get("comment", ""),
            expr=data.get("expr", ""),
        )
        # self.center_tabs.addTab(page, tab_title)
        self._add_center_tab(page, tab_title)
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

    def open_harness_detail_tab(self, name: str, data: dict):
        tab_title = f"{name} (Harness)"
        for i in range(self.center_tabs.count()):
            if self.center_tabs.tabText(i) == tab_title:
                self.center_tabs.setCurrentIndex(i)
                return

        page = ConfigRelationPage(name=name, comment=data.get("comment", ""), expr="")  # 临时占位
        # self.center_tabs.addTab(page, tab_title)
        self._add_center_tab(page, tab_title)
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

        # 3. 更新顶部 Label UI
        if name:
            self.project_label.setText(f"\u5f53\u524d\u9879\u76ee: {name}") # "当前项目: name"
            self.project_label.setStyleSheet("margin-right: 15px; color: #0078d4; font-weight: bold;")
            # 【核心修复】：项目状态变为“有”时，立即请求最新配置数据
            print(f"[Logic] Project detected ({name}), auto-refreshing config list...")
            self.refresh_project_data()
        else:
            self.project_label.setText("\u5f53\u524d\u65e0\u5df2\u6253\u5f00\u9879\u76ee") # "当前无已打开项目"
            self.project_label.setStyleSheet("margin-right: 15px; color: #666; font-weight: bold;")

            print(f"[Logic] Project closed, clearing explorer...")
            self.explorer.clear_configs()


    def on_close_opened(self):
        """
        关闭项目流程：
        1. 检查是否有打开的项目
        2. 提示是否保存
        3. 执行关闭(cancel)
        """
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
        ok = self.control.connect()
        if ok:
            self._update_conn_ui(True, "\u5df2\u8fde\u63a5")
            self.check_initial_project_status()
        else:
            self._update_conn_ui(False, "\u8fde\u63a5\u5931\u8d25")

    def on_disconnect(self):
        self.control.close()
        self._update_conn_ui(False, "\u5df2\u65ad\u5f00")
        self.update_project_display(None)
        self.explorer.clear_configs()

    def on_ping(self): print("Ping")

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
        if not self._current_project_name:
            QMessageBox.warning(self, "提示", "当前没有打开的项目，无法保存。")
            return

        self._do_save_project()

    def _do_save_project(self) -> bool:
        """
        内部辅助方法：执行 save 命令
        返回: True(保存成功), False(保存失败)
        """
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

    def on_export_harness(self): print("Export Harness")

    def on_undo(self): print("Undo")

    def on_redo(self): print("Redo")

    def on_cut(self): print("Cut")

    def on_copy(self): print("Copy")

    def on_paste(self): print("Paste")

    def on_run(self): print("Run")

    def on_stop(self): print("Stop")

    def on_build(self): print("Build")

    def on_clean(self): print("Clean")

    def on_preferences(self): print("Preferences")

    def on_theme(self): print("Theme")

    def on_shortcuts(self): print("Shortcuts")

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
