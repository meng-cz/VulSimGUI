# widgets/module_canvas_page.py
from __future__ import annotations

import math
from typing import List, Optional, Callable

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QPushButton,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem,
    QGraphicsSimpleTextItem,
    QMenu, QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QTextEdit, QFormLayout, QLineEdit, QTabWidget,
    QComboBox,
    QTreeWidget, QTreeWidgetItem
)

from .module_dialog import ModuleDialog  # noqa: F401


PRIMARY = QColor("#007180")
BG_DARK = QColor("#12161b")
PANEL = QColor("#232932")
BORDER = QColor("#2d353f")
TEXT = QColor("#e5e7eb")
MUTED = QColor("#94a3b8")

PIPE_ACCENT = QColor("#12a2b4")      # 模块实例（偏青）
PIPELINE_ACCENT = QColor("#a855f7")  # 管道实例（偏紫）
RPC_ACCENT = QColor("#f59e0b")       # RPC（偏橙）
CLOCK_ACCENT = QColor("#22c55e")     # 时钟代码块（偏绿）

SELF_INSTANCE = "__self__"


# ==========================================================
# Utils
# ==========================================================
def _safe_list(x):
    return x if isinstance(x, list) else []


def _strip(x: str) -> str:
    return (x or "").strip()


def _label_with_comment(name: str, comment: str) -> str:
    name = _strip(name)
    comment = _strip(comment)
    return f"{name}({comment})" if comment else name


def _is_self_instance_name(name: str) -> bool:
    return _strip(name) in ("", "self", SELF_INSTANCE, "本模块")


def _normalize_instance_name(name: str) -> str:
    return SELF_INSTANCE if _is_self_instance_name(name) else _strip(name)


def _first_line(text: str) -> str:
    stripped = _strip(text)
    if not stripped:
        return ""
    return stripped.splitlines()[0]


# ==========================================================
# Dialogs
# ==========================================================
class ModuleInstanceDialog(QDialog):
    """创建/编辑 模块实例：inst + module + comment + cfg_overrides(JSON)"""
    def __init__(self, title: str, data: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 320)

        data = data or {}

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.inst_edit = QLineEdit(_strip(data.get("inst", "")))
        self.inst_edit.setPlaceholderText("例如：CPU_Cluster_A")

        self.module_edit = QLineEdit(_strip(data.get("module", "")))
        self.module_edit.setPlaceholderText("例如：Core_Logic 或 某个已存在的模块名")

        self.comment_edit = QLineEdit(_strip(data.get("comment", "")))
        self.comment_edit.setPlaceholderText("可选：注释（用于悬浮提示）")

        self.cfg_overrides_edit = QTextEdit()
        self.cfg_overrides_edit.setPlaceholderText("可选：本地配置覆盖列表(JSON)")
        self.cfg_overrides_edit.setFixedHeight(120)
        self.cfg_overrides_edit.setText(_strip(data.get("cfg_overrides", "")))

        form.addRow("实例名：", self.inst_edit)
        form.addRow("所属模块：", self.module_edit)
        form.addRow("注释：", self.comment_edit)
        form.addRow("配置覆盖(JSON)：", self.cfg_overrides_edit)
        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "inst": self.inst_edit.text().strip(),
            "module": self.module_edit.text().strip(),
            "comment": self.comment_edit.text().strip(),
            "cfg_overrides": self.cfg_overrides_edit.toPlainText().strip(),
        }


class PipeInstanceDialog(QDialog):
    """创建/编辑 管道实例：对应你 ModuleDialog 里 pipes 的字段"""
    def __init__(self, title: str, data: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(720, 420)

        data = data or {}

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.inst_edit = QLineEdit(_strip(data.get("inst", "")))
        self.inst_edit.setPlaceholderText("例如：Pipe_01")

        self.comment_edit = QLineEdit(_strip(data.get("comment", "")))
        self.comment_edit.setPlaceholderText("可选：注释")

        self.dtype_edit = QLineEdit(_strip(data.get("dtype", "")))
        self.dtype_edit.setPlaceholderText("数据类型(线束名)，例如：AXI_Lite_Req")

        self.in_size_edit = QLineEdit(_strip(data.get("in_size", "")))
        self.in_size_edit.setPlaceholderText("表达式，例如：N_IN")

        self.out_size_edit = QLineEdit(_strip(data.get("out_size", "")))
        self.out_size_edit.setPlaceholderText("表达式，例如：N_OUT")

        self.buf_edit = QLineEdit(_strip(data.get("buf", "")))
        self.buf_edit.setPlaceholderText("表达式，例如：4")

        self.latency_edit = QLineEdit(_strip(data.get("latency", "")))
        self.latency_edit.setPlaceholderText("表达式，例如：1")

        self.handshake_edit = QLineEdit(_strip(data.get("handshake", "")))
        self.handshake_edit.setPlaceholderText("true/false")

        self.valid_edit = QLineEdit(_strip(data.get("valid", "")))
        self.valid_edit.setPlaceholderText("true/false")

        form.addRow("实例名：", self.inst_edit)
        form.addRow("注释：", self.comment_edit)
        form.addRow("数据类型(线束名)：", self.dtype_edit)
        form.addRow("输入尺寸(表达式)：", self.in_size_edit)
        form.addRow("输出尺寸(表达式)：", self.out_size_edit)
        form.addRow("缓冲区大小(表达式)：", self.buf_edit)
        form.addRow("延迟(表达式)：", self.latency_edit)
        form.addRow("包含握手(true/false)：", self.handshake_edit)
        form.addRow("包含有效标志(true/false)：", self.valid_edit)
        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "inst": self.inst_edit.text().strip(),
            "comment": self.comment_edit.text().strip(),
            "dtype": self.dtype_edit.text().strip(),
            "in_size": self.in_size_edit.text().strip(),
            "out_size": self.out_size_edit.text().strip(),
            "buf": self.buf_edit.text().strip(),
            "latency": self.latency_edit.text().strip(),
            "handshake": self.handshake_edit.text().strip(),
            "valid": self.valid_edit.text().strip(),
        }


class ClockBlockDialog(QDialog):
    """创建/编辑 时钟代码块：名称 + 注释。代码正文由独立代码页负责。"""
    def __init__(self, title: str, data: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(560, 260)

        data = data or {}

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(_strip(data.get("name", "")))
        self.name_edit.setPlaceholderText("例如：tick_main")

        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("可选：用于画布悬浮预览的注释")
        self.comment_edit.setFixedHeight(120)
        self.comment_edit.setPlainText(_strip(data.get("comment", "")))

        form.addRow("代码块名：", self.name_edit)
        form.addRow("注释：", self.comment_edit)
        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "comment": self.comment_edit.toPlainText().strip(),
        }


class PortEditDialog(QDialog):
    """编辑单个模块边界端口。"""
    def __init__(self, title: str, port_kind: str, data: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 280)

        self._port_kind = "rpc" if _strip(port_kind) == "rpc" else "pipe"
        data = data or {}

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.dir_combo = QComboBox()
        if self._port_kind == "rpc":
            options = [("请求(req)", "req"), ("服务(serv)", "serv")]
        else:
            options = [("输入(in)", "in"), ("输出(out)", "out")]
        for label, value in options:
            self.dir_combo.addItem(label, value)
        current_dir = _strip(data.get("dir", "")) or options[0][1]
        idx = max(0, self.dir_combo.findData(current_dir))
        self.dir_combo.setCurrentIndex(idx)

        self.name_edit = QLineEdit(_strip(data.get("name", "")))
        self.name_edit.setPlaceholderText("例如：req_main / out_data")

        self.comment_edit = QLineEdit(_strip(data.get("comment", "")))
        self.comment_edit.setPlaceholderText("可选：注释")

        self.dtype_edit = QLineEdit(_strip(data.get("dtype", "")))
        if self._port_kind == "rpc":
            self.dtype_edit.setEnabled(False)
            self.dtype_edit.setPlaceholderText("请求/服务端口当前不使用该字段")
        else:
            self.dtype_edit.setPlaceholderText("例如：AXI_Lite_Req")

        form.addRow("方向：", self.dir_combo)
        form.addRow("端口名：", self.name_edit)
        form.addRow("注释：", self.comment_edit)
        form.addRow("数据类型：", self.dtype_edit)
        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "dir": _strip(self.dir_combo.currentData() or ""),
            "name": self.name_edit.text().strip(),
            "comment": self.comment_edit.text().strip(),
            "dtype": self.dtype_edit.text().strip() if self._port_kind == "pipe" else "",
        }


# ==========================================================
# Scene / Items (Ports, Nodes, Edges)
# ==========================================================
class PortDot(QGraphicsItem):
    """
    可连接端口（仅负责“连线点击+绘制+edge更新”）
    - kind: "pipe" / "rpc"
    - direction: "in" / "out" / "req" / "serv"
    - owner_kind: "boundary" / "module_inst" / "pipe_inst"
    """
    def __init__(
        self,
        parent: QGraphicsItem,
        name: str,
        kind: str,
        direction: str,
        owner_kind: str,
        owner_name: str,
        accent: QColor,
        radius: float = 4.0,
    ):
        super().__init__(parent)
        self.port_name = name
        self.port_kind = kind
        self.direction = direction
        self.owner_kind = owner_kind
        self.owner_name = owner_name
        self.accent = accent
        self.radius = radius

        self.edges: List["EdgeItem"] = []

        self._hover = False

        self.setZValue(55)  # 比 handle 更高，确保点击优先命中 dot
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def boundingRect(self) -> QRectF:
        r = self.radius
        pad = 3.0
        return QRectF(-r - pad, -r - pad, (r + pad) * 2, (r + pad) * 2)

    def shape(self) -> QPainterPath:
        r = self.radius
        path = QPainterPath()
        if self.port_kind == "rpc":
            path.moveTo(0, -r)
            path.lineTo(r, 0)
            path.lineTo(0, r)
            path.lineTo(-r, 0)
            path.closeSubpath()
        else:
            path.addEllipse(QPointF(0, 0), r, r)
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self.radius
        stroke = self.accent.lighter(140) if (self._hover or self.isSelected()) else self.accent
        pen_w = 2 if (self._hover or self.isSelected()) else 1.5

        # out/req 实心；in/serv 空心
        if self.direction in ("out", "req"):
            brush = self.accent.lighter(125) if self._hover else self.accent
        else:
            brush = BG_DARK

        painter.setPen(QPen(stroke, pen_w))
        painter.setBrush(QBrush(brush))

        if self.port_kind == "rpc":
            path = QPainterPath()
            path.moveTo(0, -r)
            path.lineTo(r, 0)
            path.lineTo(0, r)
            path.lineTo(-r, 0)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawEllipse(QPointF(0, 0), r, r)

        painter.restore()

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def add_edge(self, edge: "EdgeItem"):
        if edge not in self.edges:
            self.edges.append(edge)

    def remove_edge(self, edge: "EdgeItem"):
        if edge in self.edges:
            self.edges.remove(edge)

    def scene_center(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    def itemChange(self, change, value):
        # 父 handle 移动也会导致 dot scenePos 改变，因此这里能统一更新连线
        if change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
            for e in list(self.edges):
                e.update_path()
        return super().itemChange(change, value)


class LinkAnchorItem(QGraphicsItem):
    """
    轻量连接锚点：
    - 不参与交互，仅用于阻塞传递/更新次序等“非端口级”连线的定位
    - 作为节点/边界的子 item，跟随父 item 移动
    """
    def __init__(self, parent: QGraphicsItem, radius: float = 3.0):
        super().__init__(parent)
        self.radius = radius
        self.edges: List["EdgeItem"] = []

        self.setZValue(3)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)

    def boundingRect(self) -> QRectF:
        r = float(self.radius)
        return QRectF(-r, -r, r * 2.0, r * 2.0)

    def paint(self, painter: QPainter, option, widget=None):
        return

    def scene_center(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    def add_edge(self, edge: "EdgeItem"):
        if edge not in self.edges:
            self.edges.append(edge)

    def remove_edge(self, edge: "EdgeItem"):
        if edge in self.edges:
            self.edges.remove(edge)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
            for e in list(self.edges):
                e.update_path()
        return super().itemChange(change, value)


class EdgeEndpointHandle(QGraphicsItem):
    """连接线选中后显示的端点拖拽手柄。"""
    def __init__(self, edge: "EdgeItem", side: str, radius: float = 5.0):
        super().__init__()
        self.edge = edge
        self.side = side
        self.radius = radius
        self._hover = False

        self.setZValue(70)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)

    def boundingRect(self) -> QRectF:
        r = float(self.radius)
        return QRectF(-r, -r, r * 2.0, r * 2.0)

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        accent = QColor(self.edge._accent)
        fill = accent.lighter(145) if self._hover else accent
        painter.setPen(QPen(TEXT if self._hover else accent.darker(130), 1.4))
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(self.boundingRect())
        painter.restore()

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def sync_pos(self):
        self.setPos(self.edge.endpoint_scene_pos(self.side))


class PortHandle(QGraphicsItem):
    """
    端口的“外围矩形框”：
    - 点击矩形框区域拖动端口位置（handle 可移动）
    - 点击 PortDot 本身由 CanvasView 开始连线
    """
    DOT_OFFSET = QPointF(10.0, 10.0)

    def __init__(
        self,
        parent: QGraphicsItem,
        label: str,
        dot: PortDot,
        accent: QColor,
        key: str,
        on_moved: Optional[Callable[[str, QPointF], None]] = None,
        w: float = 160.0,
        h: float = 22.0,
    ):
        super().__init__(parent)
        self._w = w
        self._h = h
        self._accent = accent
        self._key = key
        self._on_moved = on_moved
        self._hover = False

        self.setZValue(52)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )

        # dot 是 handle 的子 item：点击 dot 命中 dot；点击其它区域命中 handle
        self.dot = dot
        self.dot.setParentItem(self)
        self.dot.setPos(self.DOT_OFFSET)

        # label：不吃鼠标事件，避免挡住拖动
        self.txt = QGraphicsSimpleTextItem(label, self)
        self.txt.setBrush(QBrush(TEXT))
        self.txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.txt.setZValue(53)
        self.txt.setPos(self.DOT_OFFSET.x() + 10, 2)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self.boundingRect(), 4, 4)
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(self._accent.lighter(160) if (self._hover or self.isSelected()) else BORDER, 1.5)
        painter.setPen(pen)

        fill = QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 35 if self._hover else 18)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(self.boundingRect(), 4, 4)

        painter.restore()

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        # 关键：必须 return super，否则会导致拖拽/选择异常
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # handle 移动时，dot 的 scenePos 会变；为了更顺滑，这里也主动更新一下边
            for e in list(self.dot.edges):
                e.update_path()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        # 释放时一次性回写，避免拖动过程触发外部刷新造成卡顿/回弹
        if event.button() == Qt.MouseButton.LeftButton:
            if self._on_moved:
                self._on_moved(self._key, self.dot.scenePos())
        super().mouseReleaseEvent(event)


class GridScene(QGraphicsScene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dot_color = BORDER
        self.dot_spacing = 24
        self.dot_radius = 1.2
        self.setBackgroundBrush(QBrush(BG_DARK))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.dot_color))

        left = int(math.floor(rect.left()))
        right = int(math.ceil(rect.right()))
        top = int(math.floor(rect.top()))
        bottom = int(math.ceil(rect.bottom()))

        x0 = left - (left % self.dot_spacing)
        y0 = top - (top % self.dot_spacing)

        r = self.dot_radius
        for x in range(x0, right, self.dot_spacing):
            for y in range(y0, bottom, self.dot_spacing):
                painter.drawEllipse(QPointF(x, y), r, r)

        painter.restore()


class EdgeItem(QGraphicsPathItem):
    """连接线：支持 preview（未固定目标前的临时线）"""
    def __init__(
        self,
        out_port: PortDot,
        in_port: Optional[PortDot] = None,
        accent: QColor = PRIMARY,
        line_style: str = "manhattan",
        line_width: float = 2.0,
        tooltip: str = "",
        on_delete: Optional[Callable[["EdgeItem"], None]] = None,
        on_edit: Optional[Callable[["EdgeItem"], None]] = None,
    ):
        super().__init__()
        self.out_port = out_port
        self.in_port = in_port
        self._tmp_end: Optional[QPointF] = None
        self._accent = accent
        self._line_style = line_style
        self._line_width = float(line_width)
        self._tooltip = tooltip
        self._on_delete = on_delete
        self._on_edit = on_edit
        self.conn_group = ""
        self.conn_key = ""
        self.conn_record: dict = {}
        self._hover = False
        self._endpoint_handles: dict[str, EdgeEndpointHandle] = {}

        self.setZValue(2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setToolTip(tooltip)
        self._apply_pen()

        out_port.add_edge(self)
        if in_port:
            in_port.add_edge(self)

        self.update_path()

    def set_tmp_end(self, p: QPointF):
        self._tmp_end = p
        self.update_path()

    def finalize(self, in_port: PortDot):
        self.in_port = in_port
        self._tmp_end = None
        in_port.add_edge(self)
        self.update_path()

    def endpoint_scene_pos(self, side: str) -> QPointF:
        if _strip(side) == "src":
            return self.out_port.scene_center()
        if self.in_port is not None:
            return self.in_port.scene_center()
        return self._tmp_end if self._tmp_end is not None else self.out_port.scene_center()

    def update_path(self):
        a = self.out_port.scene_center()
        if self.in_port is not None:
            b = self.in_port.scene_center()
        else:
            b = self._tmp_end if self._tmp_end is not None else a

        path = QPainterPath(a)
        if self._line_style == "straight":
            path.lineTo(b)
        else:
            mid_x = (a.x() + b.x()) / 2.0
            path.lineTo(QPointF(mid_x, a.y()))
            path.lineTo(QPointF(mid_x, b.y()))
            path.lineTo(b)
        self.setPath(path)
        self.sync_endpoint_handles()

    def apply_meta(self, meta: dict):
        self.conn_group = _strip(meta.get("group", ""))
        self.conn_key = _strip(meta.get("key", ""))
        self.conn_record = dict(meta.get("record") or {})
        self._line_style = _strip(meta.get("line_style", "")) or "manhattan"
        if isinstance(meta.get("line_width"), (int, float)):
            self._line_width = float(meta["line_width"])
        tooltip = _strip(meta.get("tooltip", ""))
        if tooltip:
            self._tooltip = tooltip
            self.setToolTip(tooltip)
        accent = meta.get("accent")
        if isinstance(accent, QColor):
            self._accent = accent
        self._apply_pen()
        self.update_path()

    def _apply_pen(self):
        color = QColor(self._accent)
        width = self._line_width
        if self.isSelected() or self._hover:
            color = color.lighter(145)
            width += 0.8
        self.setPen(QPen(color, width))
        self.sync_endpoint_handles()

    def clear_endpoint_handles(self):
        for handle in list(self._endpoint_handles.values()):
            try:
                sc = handle.scene()
                if sc is not None:
                    sc.removeItem(handle)
            except RuntimeError:
                pass
        self._endpoint_handles.clear()

    def sync_endpoint_handles(self):
        sc = self.scene()
        if (
            sc is None
            or not self.isVisible()
            or not self.isSelected()
            or self.in_port is None
            or not self.conn_group
        ):
            self.clear_endpoint_handles()
            return

        for side in ("src", "dst"):
            handle = self._endpoint_handles.get(side)
            if handle is None:
                handle = EdgeEndpointHandle(self, side)
                self._endpoint_handles[side] = handle
                sc.addItem(handle)
            handle.sync_pos()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._apply_pen()
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            self.sync_endpoint_handles()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._hover = True
        self._apply_pen()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self._apply_pen()
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_edit = menu.addAction("编辑连接")
        act_edit.setEnabled(self._on_edit is not None and bool(self.conn_group) and bool(self.conn_key))
        act_del = menu.addAction("删除连接")
        act = menu.exec(event.screenPos().toPoint())
        if act == act_edit:
            if self._on_edit is not None:
                self._on_edit(self)
            return
        if act == act_del:
            if self._on_delete is not None:
                self._on_delete(self)
            else:
                self.delete_self()

    def mouseDoubleClickEvent(self, event):
        if self._on_edit is not None and self.conn_group and self.conn_key:
            self._on_edit(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def delete_self(self):
        self.clear_endpoint_handles()
        self.out_port.remove_edge(self)
        if self.in_port:
            self.in_port.remove_edge(self)
        sc = self.scene()
        if sc:
            sc.removeItem(self)


class BoundaryItem(QGraphicsItem):
    """
    父模块边界：
      - 左：pipe in
      - 右：pipe out
      - 上：rpc req
      - 下：rpc service
    端口外围用 PortHandle 矩形框包住：点击框拖动；点击 dot 连线
    """
    def __init__(self, rect: QRectF):
        super().__init__()
        self._rect = rect
        self.setZValue(-5)

        self._pipe_ports: list[dict] = []
        self._rpcs: list[dict] = []

        self.port_dots: List[PortDot] = []
        self.handles: List[PortHandle] = []

        self._pos_store: dict = {}

        # 防止重建时 setPos 触发外部刷新造成递归
        self._building: bool = False
        self._on_moved_raw = None
        self._on_moved = None
        self.center_anchor = LinkAnchorItem(self)
        self.center_anchor.setPos(self._rect.center())

    def boundingRect(self) -> QRectF:
        return self._rect

    def _wrapped_on_moved(self, key: str, pos: QPointF):
        if self._building:
            return
        if self._on_moved_raw:
            self._on_moved_raw(key, pos)

    def clear_ports(self):
        sc = self.scene()
        if not sc:
            self.port_dots.clear()
            self.handles.clear()
            return

        # 先删 edges（从 dot 上拿）
        for d in list(self.port_dots):
            for e in list(d.edges):
                e.delete_self()

        # 再删 handles（会带走其子 dot/text）
        for h in list(self.handles):
            try:
                if h.scene() is sc:
                    sc.removeItem(h)
            except RuntimeError:
                pass

        self.port_dots.clear()
        self.handles.clear()

    def set_ports(self, pipe_ports: list[dict], rpcs: list[dict], pos_store: dict | None = None, on_moved=None):
        self._pipe_ports = pipe_ports or []
        self._rpcs = rpcs or []
        self._pos_store = pos_store or {}

        self._on_moved_raw = on_moved
        self._on_moved = self._wrapped_on_moved

        self._rebuild_port_items()

    def _rebuild_port_items(self):
        self._building = True
        try:
            self.clear_ports()
            sc = self.scene()
            if not sc:
                return

            pipe_in = [p for p in self._pipe_ports if _strip(p.get("dir")) == "in" and _strip(p.get("name"))]
            pipe_out = [p for p in self._pipe_ports if _strip(p.get("dir")) == "out" and _strip(p.get("name"))]
            rpc_req = [r for r in self._rpcs if _strip(r.get("kind")) == "req" and _strip(r.get("name"))]
            rpc_svc = [r for r in self._rpcs if _strip(r.get("kind")) == "service" and _strip(r.get("name"))]

            left_x = self._rect.left() + 10
            right_x = self._rect.right() - 10
            top_y = self._rect.top() + 10
            bottom_y = self._rect.bottom() - 10

            self._place_vertical_handles(
                pipe_in, x=left_x, y0=self._rect.top() + 80, y1=self._rect.bottom() - 80,
                kind="pipe", direction="in", owner_kind="boundary", accent=PIPE_ACCENT,
                align="left"
            )
            self._place_vertical_handles(
                pipe_out, x=right_x, y0=self._rect.top() + 80, y1=self._rect.bottom() - 80,
                kind="pipe", direction="out", owner_kind="boundary", accent=PIPE_ACCENT,
                align="right"
            )
            self._place_horizontal_handles(
                rpc_req, y=top_y, x0=self._rect.left() + 120, x1=self._rect.right() - 120,
                kind="rpc", direction="req", owner_kind="boundary", accent=RPC_ACCENT,
                align="top"
            )
            self._place_horizontal_handles(
                rpc_svc, y=bottom_y, x0=self._rect.left() + 120, x1=self._rect.right() - 120,
                kind="rpc", direction="serv", owner_kind="boundary", accent=RPC_ACCENT,
                align="bottom"
            )

            self.update()
        finally:
            self._building = False

    def _place_vertical_handles(self, items: list[dict], x: float, y0: float, y1: float,
                               kind: str, direction: str, owner_kind: str, accent: QColor, align: str):
        sc = self.scene()
        if not sc:
            return
        n = len(items)
        if n <= 0:
            return

        step = (y1 - y0) / max(1, n)
        y = y0 + step * 0.5

        for it in items:
            name = _strip(it.get("name"))
            key = f"{kind}:{direction}:{name}"

            comment = _strip(it.get("comment", ""))
            label = _label_with_comment(name, comment)

            dot = PortDot(
                parent=None,
                name=name,
                kind=kind,
                direction=direction,
                owner_kind=owner_kind,
                owner_name=SELF_INSTANCE,
                accent=accent,
                radius=4.2,
            )

            handle = PortHandle(
                parent=self,
                label=label,
                dot=dot,
                accent=accent,
                key=key,
                on_moved=self._on_moved,
                w=160.0,
                h=22.0,
            )

            # 位置存储的是 dot 的 scene pos：这里要换算成 handle 的 pos
            pos = self._pos_store.get(key)
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                px, py = float(pos["x"]), float(pos["y"])
                handle_pos = QPointF(px, py) - PortHandle.DOT_OFFSET
            else:
                handle_pos = QPointF(x, y) - PortHandle.DOT_OFFSET

            handle.setPos(handle_pos)
            self.port_dots.append(dot)
            self.handles.append(handle)

            y += step

    def _place_horizontal_handles(self, items: list[dict], y: float, x0: float, x1: float,
                                 kind: str, direction: str, owner_kind: str, accent: QColor, align: str):
        sc = self.scene()
        if not sc:
            return
        n = len(items)
        if n <= 0:
            return

        step = (x1 - x0) / max(1, n)
        x = x0 + step * 0.5

        for it in items:
            name = _strip(it.get("name"))
            key = f"{kind}:{direction}:{name}"

            comment = _strip(it.get("comment", ""))
            label = _label_with_comment(name, comment)

            dot = PortDot(
                parent=None,
                name=name,
                kind=kind,
                direction=direction,
                owner_kind=owner_kind,
                owner_name=SELF_INSTANCE,
                accent=accent,
                radius=4.2,
            )

            handle = PortHandle(
                parent=self,
                label=label,
                dot=dot,
                accent=accent,
                key=key,
                on_moved=self._on_moved,
                w=160.0,
                h=22.0,
            )

            pos = self._pos_store.get(key)
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                px, py = float(pos["x"]), float(pos["y"])
                handle_pos = QPointF(px, py) - PortHandle.DOT_OFFSET
            else:
                handle_pos = QPointF(x, y) - PortHandle.DOT_OFFSET

            handle.setPos(handle_pos)
            self.port_dots.append(dot)
            self.handles.append(handle)

            x += step

    def paint(self, painter: QPainter, option, widget=None):
        return  # 你原本就 return 掉了（需要边框再打开）


class BaseNodeItem(QGraphicsItem):
    """
    节点基类：
      - 支持自定义 accent
      - 支持动态 ports（pipe/rpc）
      - 支持边界拉伸改变 w/h（不破坏已有连线）
    """
    MIN_W = 180
    MIN_H = 110
    RESIZE_MARGIN = 8.0  # 靠近边界多少像素算可拉伸

    def __init__(self, title: str, w: int, h: int, accent: QColor, node_kind: str):
        super().__init__()
        self.title = title
        self.w = int(w)
        self.h = int(h)
        self.accent = accent
        self.node_kind = node_kind  # "module_inst" / "pipe_inst"

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.center_anchor = LinkAnchorItem(self)
        self._update_center_anchor()

        self.ports: List[PortDot] = []
        self.labels: List[QGraphicsSimpleTextItem] = []

        self.payload: dict = {}

        # 保存端口定义（resize 时重排）
        self._pipe_ports_src: list[dict] = []
        self._rpcs_src: list[dict] = []

        # key -> (dot, label, align_info)
        # key 规则：(kind, direction, name)
        self._port_map: dict[tuple[str, str, str], PortDot] = {}
        self._label_map: dict[tuple[str, str, str], QGraphicsSimpleTextItem] = {}
        self._label_align: dict[tuple[str, str, str], str] = {}

        # resize 状态
        self._resizing = False
        self._resize_edges: set[str] = set()
        self._press_scene: Optional[QPointF] = None
        self._orig_pos: Optional[QPointF] = None
        self._orig_w: int = self.w
        self._orig_h: int = self.h

        # resize 回调（由外部注入，用于持久化尺寸）
        self.on_resized: Optional[Callable[["BaseNodeItem"], None]] = None

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, float(self.w), float(self.h))

    def set_payload(self, payload: dict):
        self.payload = payload or {}

    def _update_center_anchor(self):
        self.center_anchor.setPos(self.w / 2.0, self.h / 2.0)

    def clear_anchor_edges(self):
        for edge in list(self.center_anchor.edges):
            edge.delete_self()

    # --------------------------
    # Ports: build / sync / layout
    # --------------------------
    def clear_ports(self):
        sc = self.scene()
        if not sc:
            self.ports.clear()
            self.labels.clear()
            self._port_map.clear()
            self._label_map.clear()
            self._label_align.clear()
            return

        # 删除 labels
        for t in list(self.labels):
            try:
                if t.scene() is sc:
                    sc.removeItem(t)
            except RuntimeError:
                pass

        # 删除 dots（会先删连接）
        for p in list(self.ports):
            for e in list(p.edges):
                e.delete_self()
            try:
                if p.scene() is sc:
                    sc.removeItem(p)
            except RuntimeError:
                pass

        self.ports.clear()
        self.labels.clear()
        self._port_map.clear()
        self._label_map.clear()
        self._label_align.clear()

    def set_ports(self, pipe_ports: list[dict], rpcs: list[dict]):
        """
        用于“端口定义变化”的场景（初建/刷新模块定义）。
        注意：会重建端口（因此会删除已有连接）。
        """
        self._pipe_ports_src = pipe_ports or []
        self._rpcs_src = rpcs or []

        self.clear_ports()
        sc = self.scene()
        if not sc:
            return

        self._build_ports(sc)
        self._relayout_ports()  # 初次布局
        self.update()

    def relayout_ports_only(self):
        """
        用于“仅尺寸变化”的场景：不重建端口，不删除已有连接，只重排位置。
        """
        if not self.ports and not self.labels:
            return
        self._relayout_ports()
        self.update()

    def _build_ports(self, sc: QGraphicsScene):
        pipe_ports = self._pipe_ports_src
        rpcs = self._rpcs_src

        pipe_in = [p for p in pipe_ports if _strip(p.get("dir")) == "in" and _strip(p.get("name"))]
        pipe_out = [p for p in pipe_ports if _strip(p.get("dir")) == "out" and _strip(p.get("name"))]
        rpc_req = [r for r in rpcs if _strip(r.get("kind")) == "req" and _strip(r.get("name"))]
        rpc_svc = [r for r in rpcs if _strip(r.get("kind")) == "service" and _strip(r.get("name"))]

        # 创建 dots + labels（位置稍后 relayout）
        def _mk(kind: str, direction: str, name: str, comment: str, accent: QColor, align: str):
            key = (kind, direction, name)
            owner_name = _strip(self.payload.get("inst", ""))

            dot = PortDot(
                self,
                name=name,
                kind=kind,
                direction=direction,
                owner_kind=self.node_kind,
                owner_name=owner_name,
                accent=accent,
                radius=3.5,
            )
            self.ports.append(dot)
            self._port_map[key] = dot

            label = _label_with_comment(name, comment)
            txt = QGraphicsSimpleTextItem(label, self)
            txt.setBrush(QBrush(MUTED))
            txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            txt.setZValue(60)
            self.labels.append(txt)
            self._label_map[key] = txt
            self._label_align[key] = align

        for p in pipe_in:
            _mk("pipe", "in", _strip(p.get("name")), _strip(p.get("comment", "")), PIPE_ACCENT, "left")
        for p in pipe_out:
            _mk("pipe", "out", _strip(p.get("name")), _strip(p.get("comment", "")), PIPE_ACCENT, "right")
        for r in rpc_req:
            _mk("rpc", "req", _strip(r.get("name")), _strip(r.get("comment", "")), RPC_ACCENT, "top")
        for r in rpc_svc:
            _mk("rpc", "serv", _strip(r.get("name")), _strip(r.get("comment", "")), RPC_ACCENT, "bottom")

    def _relayout_ports(self):
        self._update_center_anchor()

        pipe_ports = self._pipe_ports_src
        rpcs = self._rpcs_src

        pipe_in = [p for p in pipe_ports if _strip(p.get("dir")) == "in" and _strip(p.get("name"))]
        pipe_out = [p for p in pipe_ports if _strip(p.get("dir")) == "out" and _strip(p.get("name"))]
        rpc_req = [r for r in rpcs if _strip(r.get("kind")) == "req" and _strip(r.get("name"))]
        rpc_svc = [r for r in rpcs if _strip(r.get("kind")) == "service" and _strip(r.get("name"))]

        left_x = 6
        right_x = self.w - 6
        top_y = 6
        bottom_y = self.h - 6

        # vertical layout (in/out)
        def _layout_vertical(items: list[dict], x: float, y0: float, y1: float, kind: str, direction: str, align: str):
            n = len(items)
            if n <= 0:
                return
            step = (y1 - y0) / max(1, n)
            y = y0 + step * 0.5
            for it in items:
                name = _strip(it.get("name"))
                key = (kind, direction, name)
                dot = self._port_map.get(key)
                txt = self._label_map.get(key)
                if dot is None or txt is None:
                    y += step
                    continue

                dot.setPos(x, y)

                # label
                if align == "left":
                    txt.setPos(x + 6, y - 8)
                else:
                    txt.setPos(x - 6 - txt.boundingRect().width(), y - 8)

                y += step

        # horizontal layout (req/serv)
        def _layout_horizontal(items: list[dict], y: float, x0: float, x1: float, kind: str, direction: str, align: str):
            n = len(items)
            if n <= 0:
                return
            step = (x1 - x0) / max(1, n)
            x = x0 + step * 0.5
            for it in items:
                name = _strip(it.get("name"))
                key = (kind, direction, name)
                dot = self._port_map.get(key)
                txt = self._label_map.get(key)
                if dot is None or txt is None:
                    x += step
                    continue

                dot.setPos(x, y)

                if align == "top":
                    txt.setPos(x - txt.boundingRect().width() / 2, y + 6)
                else:
                    txt.setPos(x - txt.boundingRect().width() / 2, y - 18)

                x += step

        _layout_vertical(pipe_in, x=left_x, y0=44, y1=self.h - 20, kind="pipe", direction="in", align="left")
        _layout_vertical(pipe_out, x=right_x, y0=44, y1=self.h - 20, kind="pipe", direction="out", align="right")
        _layout_horizontal(rpc_req, y=top_y, x0=40, x1=self.w - 40, kind="rpc", direction="req", align="top")
        _layout_horizontal(rpc_svc, y=bottom_y, x0=40, x1=self.w - 40, kind="rpc", direction="serv", align="bottom")

        # 连线更新
        for p in self.ports:
            for e in list(p.edges):
                e.update_path()

    # --------------------------
    # Resize hit test & cursor
    # --------------------------
    def _hit_test_resize(self, p: QPointF) -> set[str]:
        """
        p 是 item-local 坐标。返回命中的边集合：{"left","right","top","bottom"} 或空集合。
        """
        edges: set[str] = set()
        m = float(self.RESIZE_MARGIN)
        r = self.boundingRect()

        if p.x() <= r.left() + m:
            edges.add("left")
        elif p.x() >= r.right() - m:
            edges.add("right")

        if p.y() <= r.top() + m:
            edges.add("top")
        elif p.y() >= r.bottom() - m:
            edges.add("bottom")

        # 确保真的在边界附近，而不是内部
        inside_x = (r.left() + m) < p.x() < (r.right() - m)
        inside_y = (r.top() + m) < p.y() < (r.bottom() - m)
        if inside_x and inside_y:
            return set()

        return edges

    def _cursor_for_edges(self, edges: set[str]) -> Qt.CursorShape:
        if {"left", "top"} <= edges or {"right", "bottom"} <= edges:
            return Qt.CursorShape.SizeFDiagCursor
        if {"right", "top"} <= edges or {"left", "bottom"} <= edges:
            return Qt.CursorShape.SizeBDiagCursor
        if "left" in edges or "right" in edges:
            return Qt.CursorShape.SizeHorCursor
        if "top" in edges or "bottom" in edges:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def hoverMoveEvent(self, event):
        if self._resizing:
            event.accept()
            return
        edges = self._hit_test_resize(event.pos())
        if edges:
            self.setCursor(self._cursor_for_edges(edges))
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        if not self._resizing:
            self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._hit_test_resize(event.pos())
            if edges:
                self._resizing = True
                self._resize_edges = edges
                self._press_scene = event.scenePos()
                self._orig_pos = QPointF(self.pos())
                self._orig_w = int(self.w)
                self._orig_h = int(self.h)
                self.setCursor(self._cursor_for_edges(edges))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._resizing or self._press_scene is None or self._orig_pos is None:
            super().mouseMoveEvent(event)
            return

        delta = event.scenePos() - self._press_scene

        new_w = float(self._orig_w)
        new_h = float(self._orig_h)
        new_pos = QPointF(self._orig_pos)

        # left/right affects width and (left) position
        if "left" in self._resize_edges:
            new_w = float(self._orig_w) - delta.x()
            new_pos.setX(self._orig_pos.x() + delta.x())
        if "right" in self._resize_edges:
            new_w = float(self._orig_w) + delta.x()

        # top/bottom affects height and (top) position
        if "top" in self._resize_edges:
            new_h = float(self._orig_h) - delta.y()
            new_pos.setY(self._orig_pos.y() + delta.y())
        if "bottom" in self._resize_edges:
            new_h = float(self._orig_h) + delta.y()

        # clamp minimum size, adjust pos for left/top if clamped
        min_w = float(self.MIN_W)
        min_h = float(self.MIN_H)

        if new_w < min_w:
            if "left" in self._resize_edges:
                dx = float(self._orig_w) - min_w
                new_pos.setX(self._orig_pos.x() + dx)
            new_w = min_w

        if new_h < min_h:
            if "top" in self._resize_edges:
                dy = float(self._orig_h) - min_h
                new_pos.setY(self._orig_pos.y() + dy)
            new_h = min_h

        # apply geometry
        self.prepareGeometryChange()
        self.setPos(new_pos)
        self.w = int(new_w)
        self.h = int(new_h)

        # relayout ports WITHOUT rebuilding (keep connections)
        self.relayout_ports_only()

        event.accept()

    def mouseReleaseEvent(self, event):
        if self._resizing and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = False
            self._resize_edges = set()
            self._press_scene = None
            self._orig_pos = None

            # 释放后：回调持久化（可选但强烈建议）
            if self.on_resized:
                try:
                    self.on_resized(self)
                except Exception:
                    pass

            # 更新 cursor
            edges = self._hit_test_resize(event.pos())
            if edges:
                self.setCursor(self._cursor_for_edges(edges))
            else:
                self.unsetCursor()

            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bg = QColor(PANEL)
        border_pen = QPen(self.accent if self.isSelected() else BORDER, 2 if self.isSelected() else 1)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(self.boundingRect(), 8, 8)

        title_h = 28
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.accent.red(), self.accent.green(), self.accent.blue(), 55)))
        painter.drawRoundedRect(QRectF(0, 0, self.w, title_h), 8, 8)
        painter.drawRect(QRectF(0, title_h - 8, self.w, 8))

        painter.setPen(QPen(TEXT))
        painter.drawText(QRectF(10, 0, self.w - 20, title_h), Qt.AlignmentFlag.AlignVCenter, self.title)

        painter.setPen(QPen(MUTED))
        badge = "MODULE" if self.node_kind == "module_inst" else "PIPE"
        painter.drawText(QRectF(self.w - 90, 0, 80, title_h),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, badge)

        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for p in self.ports:
                for e in list(p.edges):
                    e.update_path()
        return super().itemChange(change, value)


class ModuleInstNode(BaseNodeItem):
    def __init__(self, title: str):
        super().__init__(title=title, w=280, h=170, accent=PIPE_ACCENT, node_kind="module_inst")


class PipeInstNode(BaseNodeItem):
    def __init__(self, title: str):
        super().__init__(title=title, w=240, h=130, accent=PIPELINE_ACCENT, node_kind="pipe_inst")


class ClockBlockNode(BaseNodeItem):
    MIN_W = 200
    MIN_H = 90

    def __init__(self, title: str):
        super().__init__(title=title, w=240, h=110, accent=CLOCK_ACCENT, node_kind="clock_block")

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        border_pen = QPen(self.accent if self.isSelected() else BORDER, 2 if self.isSelected() else 1)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(QColor(PANEL)))
        painter.drawRoundedRect(self.boundingRect(), 8, 8)

        title_h = 28
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.accent.red(), self.accent.green(), self.accent.blue(), 55)))
        painter.drawRoundedRect(QRectF(0, 0, self.w, title_h), 8, 8)
        painter.drawRect(QRectF(0, title_h - 8, self.w, 8))

        painter.setPen(QPen(TEXT))
        painter.drawText(QRectF(10, 0, self.w - 100, title_h), Qt.AlignmentFlag.AlignVCenter, self.title)

        painter.setPen(QPen(MUTED))
        painter.drawText(
            QRectF(self.w - 90, 0, 80, title_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            "CLOCK",
        )

        preview = _strip((self.payload or {}).get("comment", "")) or "双击打开代码编辑页"
        painter.setPen(QPen(MUTED))
        painter.drawText(
            QRectF(12, 40, self.w - 24, self.h - 52),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            preview,
        )

        painter.restore()


# ==========================================================
# View: Pan/Zoom + Connection interaction + Context menu
# ==========================================================
class CanvasView(QGraphicsView):
    # 缩放极值：可按需调整
    MIN_SCALE = 0.20   # 最小只能缩到 20%
    MAX_SCALE = 4.00   # 最大只能放到 400%

    def __init__(self, scene: QGraphicsScene, host: "ModuleCanvas"):
        super().__init__(scene)
        self._host = host
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self._panning = False
        self._pan_start = None
        self._space_down = False

        self._connecting = False
        self._start_port: Optional[PortDot] = None
        self._preview_edge: Optional[EdgeItem] = None
        self._retargeting_edge: Optional[EdgeItem] = None
        self._retarget_side: str = ""
        self._retarget_preview: Optional[EdgeItem] = None

        # =========================
        # 右下角缩放提示（悬浮）
        # =========================
        self._zoom_badge = QLabel(self.viewport())
        self._zoom_badge.setText("")
        self._zoom_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._zoom_badge.setStyleSheet(
            """
            QLabel{
                color: #e5e7eb;
                background: rgba(35, 41, 50, 170);
                border: 1px solid rgba(45, 53, 63, 180);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
            }
            """
        )
        self._zoom_badge.show()
        self._update_zoom_badge()

    def _node_at_view_pos(self, view_pos) -> Optional["BaseNodeItem"]:
        for it in self.items(view_pos):
            if isinstance(it, BaseNodeItem):
                return it
            p = it.parentItem()
            while p is not None:
                if isinstance(p, BaseNodeItem):
                    return p
                p = p.parentItem()
        return None

    def _port_at_pos_strict(self, view_pos) -> Optional[PortDot]:
        for it in self.items(view_pos):
            if isinstance(it, PortDot):
                return it
        return None

    def _port_target_at_view_pos(self, view_pos) -> Optional[PortDot]:
        for it in self.items(view_pos):
            if isinstance(it, PortDot):
                return it
            if isinstance(it, PortHandle):
                return it.dot
        return None

    def _edge_handle_at_view_pos(self, view_pos) -> Optional[EdgeEndpointHandle]:
        for it in self.items(view_pos):
            if isinstance(it, EdgeEndpointHandle):
                return it
        return None

    def _object_target_at_view_pos(self, view_pos, scene_pos: QPointF):
        for it in self.items(view_pos):
            if isinstance(it, BaseNodeItem):
                return it
            parent = it.parentItem() if isinstance(it, QGraphicsItem) else None
            while parent is not None:
                if isinstance(parent, BaseNodeItem):
                    return parent
                parent = parent.parentItem()
        if self._host.boundary_rect.contains(scene_pos):
            return self._host.boundary
        return None

    def _current_scale(self) -> float:
        # 假设等比缩放（x/y 一样），m11 即当前 scale
        t = self.transform()
        s = float(t.m11())
        if s <= 0:
            return 1.0
        return s

    def _update_zoom_badge(self):
        # 1) 文本
        pct = int(round(self._current_scale() * 100.0))
        self._zoom_badge.setText(f"{pct}%")

        # 2) 右下角定位
        self._zoom_badge.adjustSize()
        margin = 10
        x = self.viewport().width() - self._zoom_badge.width() - margin
        y = self.viewport().height() - self._zoom_badge.height() - margin
        if x < margin:
            x = margin
        if y < margin:
            y = margin
        self._zoom_badge.move(x, y)

        # 3) 保底：避免极端情况下被隐藏
        self._zoom_badge.raise_()

    def _apply_zoom(self, factor: float):
        """
        统一在这里做 clamp，避免无限缩放导致崩溃。
        """
        cur = self._current_scale()
        if factor <= 0:
            return

        target = cur * factor
        if target < self.MIN_SCALE:
            factor = self.MIN_SCALE / cur
        elif target > self.MAX_SCALE:
            factor = self.MAX_SCALE / cur

        # 如果已经到极值，factor 可能会非常接近 1
        if abs(factor - 1.0) < 1e-6:
            # 仍然刷新一下 badge（比如用户想确认当前已到极限）
            self._update_zoom_badge()
            return

        self.scale(factor, factor)
        self._update_zoom_badge()

    def wheelEvent(self, event):
        # Ctrl + 滚轮缩放
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                event.accept()
                return

            factor = 1.15 if delta > 0 else 1 / 1.15
            self._apply_zoom(factor)

            event.accept()
            return

        super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 视口尺寸变化要重摆右下角 badge
        self._update_zoom_badge()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_down = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_edge_retarget()
            self._cancel_connection()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_down = False
            if not self._panning:
                self.unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        # panning
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_down
        ):
            self._cancel_edge_retarget()
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            edge_handle = self._edge_handle_at_view_pos(event.pos())
            if edge_handle is not None:
                self._begin_edge_retarget(edge_handle, self.mapToScene(event.pos()))
                event.accept()
                return
            port = self._port_at_pos_strict(event.pos())
            if port:
                if self._connecting and port is self._start_port:
                    event.accept()
                    return
                self._on_port_clicked(port, self.mapToScene(event.pos()))
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._connecting and self._preview_edge is not None:
            self._preview_edge.set_tmp_end(self.mapToScene(event.pos()))
            event.accept()
            return

        if self._retargeting_edge is not None and self._retarget_preview is not None:
            self._retarget_preview.set_tmp_end(self.mapToScene(event.pos()))
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and (event.button() == Qt.MouseButton.MiddleButton or event.button() == Qt.MouseButton.LeftButton):
            self._panning = False
            self._pan_start = None
            if self._space_down:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._connecting:
            port = self._port_at_pos_strict(event.pos())
            if port:
                self._on_port_clicked(port, self.mapToScene(event.pos()))
                event.accept()
                return

        if event.button() == Qt.MouseButton.LeftButton and self._retargeting_edge is not None:
            edge = self._retargeting_edge
            scene_pos = self.mapToScene(event.pos())
            target = None
            if edge.conn_group in ("reqsvc_conns", "instpipe_conns"):
                target = self._port_target_at_view_pos(event.pos())
            else:
                target = self._object_target_at_view_pos(event.pos(), scene_pos)
            if target is not None and self._host.retarget_connection is not None:
                try:
                    self._host.retarget_connection(edge, self._retarget_side, target)
                except Exception:
                    pass
            self._cancel_edge_retarget()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        port = self._port_at_pos_strict(event.pos())
        if port is not None:
            self._cancel_connection()
            if self._host.on_port_double_clicked is not None:
                try:
                    self._host.on_port_double_clicked(port)
                except Exception:
                    pass
            event.accept()
            return

        item = self.itemAt(event.pos())
        node = item if isinstance(item, BaseNodeItem) else (item.parentItem() if isinstance(item, PortDot) else None)
        if isinstance(node, BaseNodeItem):
            self._host.on_node_double_clicked(node, event.modifiers())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self._retargeting_edge is not None:
            self._cancel_edge_retarget()
            event.accept()
            return
        if self._connecting:
            self._cancel_connection()
            event.accept()
            return

        port = self._port_target_at_view_pos(event.pos())
        if port is not None and self._host.show_port_menu(event.globalPos(), port):
            event.accept()
            return

        node = self._node_at_view_pos(event.pos())
        scene_pos = self.mapToScene(event.pos())

        if isinstance(node, BaseNodeItem):
            self._host.show_node_menu(event.globalPos(), node)
            event.accept()
            return

        self._host.show_blank_menu(event.globalPos(), scene_pos)
        event.accept()

    def _on_port_clicked(self, port: PortDot, scene_pos: QPointF):
        if not self._connecting:
            self._connecting = True
            self._start_port = port
            self._preview_edge = EdgeItem(out_port=port, in_port=None, accent=port.accent)
            self.scene().addItem(self._preview_edge)
            self._preview_edge.set_tmp_end(scene_pos)
            return

        if self._start_port is None or self._preview_edge is None:
            self._cancel_connection()
            return

        if port.port_kind != self._start_port.port_kind:
            QMessageBox.information(None, "类型不匹配", "RPC 端口只能连接 RPC；PIPE 端口只能连接 PIPE。")
            return

        if self._host.resolve_connection is not None:
            meta = self._host.resolve_connection(self._start_port, port)
            if not isinstance(meta, dict):
                return
            self._preview_edge.finalize(port)
            self._preview_edge._on_delete = self._host.on_edge_deleted
            self._preview_edge.apply_meta(meta)
        else:
            self._preview_edge.finalize(port)
        self._connecting = False
        self._start_port = None
        self._preview_edge = None

    def _cancel_connection(self):
        if self._preview_edge is not None:
            self._preview_edge.delete_self()
        self._connecting = False
        self._start_port = None
        self._preview_edge = None

    def _begin_edge_retarget(self, handle: EdgeEndpointHandle, scene_pos: QPointF):
        edge = handle.edge
        if edge.in_port is None or not edge.conn_group:
            return

        self._cancel_connection()
        self._cancel_edge_retarget()

        self._retargeting_edge = edge
        self._retarget_side = handle.side
        fixed_anchor = edge.in_port if handle.side == "src" else edge.out_port
        edge.clear_endpoint_handles()
        edge.setVisible(False)

        self._retarget_preview = EdgeItem(
            out_port=fixed_anchor,
            in_port=None,
            accent=edge._accent,
            line_style=edge._line_style,
            line_width=edge._line_width,
            tooltip=edge.toolTip(),
        )
        self.scene().addItem(self._retarget_preview)
        self._retarget_preview.set_tmp_end(scene_pos)

    def _cancel_edge_retarget(self):
        if self._retarget_preview is not None:
            self._retarget_preview.delete_self()
        if self._retargeting_edge is not None:
            try:
                self._retargeting_edge.setVisible(True)
                self._retargeting_edge.sync_endpoint_handles()
            except RuntimeError:
                pass
        self._retargeting_edge = None
        self._retarget_side = ""
        self._retarget_preview = None


# ==========================================================
# ModuleCanvas
# ==========================================================
class ModuleCanvas(QWidget):
    # 类信号
    requestCreateModuleInst = pyqtSignal(QPointF)
    requestCreatePipeInst = pyqtSignal(QPointF)
    requestCreateClockBlock = pyqtSignal(QPointF)
    requestEditNode = pyqtSignal(object)  # BaseNodeItem
    requestEnterSubmodule = pyqtSignal(str, str)  # inst, module
    requestOpenNode = pyqtSignal(object)  # BaseNodeItem
    requestDeleteNode = pyqtSignal(object)  # BaseNodeItem
    requestNodeResized = pyqtSignal(object)  # BaseNodeItem（用于 ModuleCanvasPage 持久化尺寸）
    requestPreviewSelection = pyqtSignal(object)
    requestEditBoundaryPort = pyqtSignal(object)  # PortDot
    requestDeleteBoundaryPort = pyqtSignal(object)  # PortDot

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scene = GridScene()
        self.scene.setSceneRect(-2500, -2000, 5000, 4000)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

        self.view = CanvasView(self.scene, host=self)
        layout.addWidget(self.view)

        self.boundary_rect = QRectF(-1500, -950, 3000, 1900)
        self.boundary = BoundaryItem(self.boundary_rect)
        self.scene.addItem(self.boundary)

        self.on_parent_port_moved: Optional[Callable[[str, QPointF], None]] = None
        self.resolve_connection: Optional[Callable[[PortDot, PortDot], Optional[dict]]] = None
        self.on_edge_deleted: Optional[Callable[[EdgeItem], None]] = None
        self.on_port_double_clicked: Optional[Callable[[PortDot], bool]] = None
        self.retarget_connection: Optional[Callable[[EdgeItem, str, object], bool]] = None
        self.parent_port_pos: dict = {}

    def set_parent_ports(self, pipe_ports: list[dict], rpcs: list[dict], pos_store: dict | None = None):
        self.parent_port_pos = pos_store or {}
        self.boundary.set_ports(
            pipe_ports or [], rpcs or [],
            pos_store=self.parent_port_pos,
            on_moved=self.on_parent_port_moved
        )

    def show_blank_menu(self, global_pos, scene_pos: QPointF):
        menu = QMenu()
        act_mod = menu.addAction("创建模块实例")
        act_pipe = menu.addAction("创建管道实例")
        act_clock = menu.addAction("创建时钟代码块")
        act = menu.exec(global_pos)
        if act == act_mod:
            self.requestCreateModuleInst.emit(scene_pos)
        elif act == act_pipe:
            self.requestCreatePipeInst.emit(scene_pos)
        elif act == act_clock:
            self.requestCreateClockBlock.emit(scene_pos)

    def show_node_menu(self, global_pos, node: BaseNodeItem):
        payload = node.payload or {}
        kind = payload.get("_kind")

        menu = QMenu()

        # 子模块实例：打开/编辑/删除
        if kind == "module_inst":
            act_open = menu.addAction("打开")
            act_edit = menu.addAction("编辑")
            act_del = menu.addAction("删除")
            act = menu.exec(global_pos)
            if act == act_open:
                self.requestOpenNode.emit(node)
            elif act == act_edit:
                self.requestEditNode.emit(node)
            elif act == act_del:
                self.requestDeleteNode.emit(node)
            return

        # 子管道实例：编辑/删除
        if kind == "pipe_inst":
            act_edit = menu.addAction("编辑")
            act_del = menu.addAction("删除")
            act = menu.exec(global_pos)
            if act == act_edit:
                self.requestEditNode.emit(node)
            elif act == act_del:
                self.requestDeleteNode.emit(node)
            return

        if kind == "clock_block":
            act_open = menu.addAction("打开代码")
            act_edit = menu.addAction("编辑")
            act_del = menu.addAction("删除")
            act = menu.exec(global_pos)
            if act == act_open:
                self.requestOpenNode.emit(node)
            elif act == act_edit:
                self.requestEditNode.emit(node)
            elif act == act_del:
                self.requestDeleteNode.emit(node)
            return

        menu.addAction("（无可用操作）")
        menu.exec(global_pos)

    def show_port_menu(self, global_pos, port: PortDot) -> bool:
        if not isinstance(port, PortDot):
            return False

        menu = QMenu()
        act_edit = None
        act_del = None
        act_open = None

        if port.owner_kind == "boundary":
            act_edit = menu.addAction("编辑端口")
            act_del = menu.addAction("删除端口")
            if port.port_kind == "rpc" and port.direction == "serv":
                menu.addSeparator()
                act_open = menu.addAction("打开服务代码")
        elif port.owner_kind == "module_inst" and port.port_kind == "rpc" and port.direction == "req":
            act_open = menu.addAction("打开请求代码")
        else:
            return False

        act = menu.exec(global_pos)
        if act == act_edit:
            self.requestEditBoundaryPort.emit(port)
            return True
        if act == act_del:
            self.requestDeleteBoundaryPort.emit(port)
            return True
        if act == act_open and self.on_port_double_clicked is not None:
            self.on_port_double_clicked(port)
            return True
        return True

    def request_edit_node(self, node: BaseNodeItem):
        self.requestEditNode.emit(node)

    def on_node_double_clicked(self, node: BaseNodeItem, modifiers: Qt.KeyboardModifier):
        payload = node.payload or {}
        kind = payload.get("_kind")

        # 规则：双击 module_inst => 进入子模块画布
        #      Alt + 双击 => 编辑（保留编辑入口）
        if kind == "module_inst" and not (modifiers & Qt.KeyboardModifier.AltModifier):
            inst = _strip(payload.get("inst", ""))
            mod = _strip(payload.get("module", ""))
            if not mod:
                QMessageBox.warning(self, "无法进入子模块", "该实例未设置所属模块名（module 为空）。")
                return
            self.requestEnterSubmodule.emit(inst, mod)
            return

        if kind == "clock_block":
            self.requestOpenNode.emit(node)
            return

        # 其它情况：仍然走编辑（pipe_inst、或 Alt+双击 module_inst）
        self.requestEditNode.emit(node)

    def _wire_resize_callback(self, node: BaseNodeItem):
        # 让 node 在 resize 结束时通知 canvas，再由 page 做持久化
        def _cb(n: BaseNodeItem):
            self.requestNodeResized.emit(n)
        node.on_resized = _cb

    def add_module_inst_node(self, title: str, pos: QPointF) -> ModuleInstNode:
        node = ModuleInstNode(title)
        node.setPos(pos)
        self.scene.addItem(node)
        self._wire_resize_callback(node)
        return node

    def add_pipe_inst_node(self, title: str, pos: QPointF) -> PipeInstNode:
        node = PipeInstNode(title)
        node.setPos(pos)
        self.scene.addItem(node)
        self._wire_resize_callback(node)
        return node

    def add_clock_block_node(self, title: str, pos: QPointF) -> ClockBlockNode:
        node = ClockBlockNode(title)
        node.setPos(pos)
        self.scene.addItem(node)
        self._wire_resize_callback(node)
        return node

    def _normalize_selected_item(self, item):
        if isinstance(item, (BaseNodeItem, EdgeItem, PortDot, PortHandle)):
            return item
        parent = item.parentItem() if isinstance(item, QGraphicsItem) else None
        while parent is not None:
            if isinstance(parent, (BaseNodeItem, EdgeItem, PortDot, PortHandle)):
                return parent
            parent = parent.parentItem()
        return None

    def _on_scene_selection_changed(self):
        selected = list(self.scene.selectedItems())
        for item in reversed(selected):
            normalized = self._normalize_selected_item(item)
            if normalized is not None:
                self.requestPreviewSelection.emit(normalized)
                return
        self.requestPreviewSelection.emit(None)


# ==========================================================
# Sidebar dialogs
# ==========================================================
class _TableDialog(QDialog):
    def __init__(self, title: str, headers: list[str], keys: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(860, 520)

        self._keys = keys

        root = QVBoxLayout(self)

        self.tbl = QTableWidget(0, len(headers))
        self.tbl.setHorizontalHeaderLabels(headers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        bar = QHBoxLayout()
        bar.addStretch(1)
        btn_add = QPushButton("新增")
        btn_del = QPushButton("删除选中")
        bar.addWidget(btn_add)
        bar.addWidget(btn_del)

        btn_add.clicked.connect(lambda: self.tbl.insertRow(self.tbl.rowCount()))
        btn_del.clicked.connect(lambda: self.tbl.removeRow(self.tbl.currentRow()) if self.tbl.currentRow() >= 0 else None)

        root.addLayout(bar)
        root.addWidget(self.tbl, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def load(self, rows: list[dict]):
        self.tbl.setRowCount(0)
        for row in rows or []:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            for c, k in enumerate(self._keys):
                self.tbl.setItem(r, c, QTableWidgetItem(str(row.get(k, ""))))

    def dump(self) -> list[dict]:
        out = []
        for r in range(self.tbl.rowCount()):
            d = {}
            empty = True
            for c, k in enumerate(self._keys):
                it = self.tbl.item(r, c)
                v = it.text().strip() if it else ""
                if v:
                    empty = False
                d[k] = v
            if not empty:
                out.append(d)
        return out


class LocalCfgDialog(_TableDialog):
    def __init__(self, parent=None):
        super().__init__("编辑：本地配置列表", ["本地配置名", "默认值(表达式)", "注释"], ["name", "default", "comment"], parent=parent)


class LocalHarnessDialog(_TableDialog):
    def __init__(self, parent=None):
        super().__init__(
            "编辑：本地线束列表",
            ["本地线束名", "注释", "定义模式(alias/members/enums)", "定义内容(JSON)"],
            ["name", "comment", "mode", "body"],
            parent=parent
        )


class PortsDialog(_TableDialog):
    def __init__(self, parent=None):
        super().__init__(
            "编辑：Pipe 端口列表",
            ["方向(in/out/req/serv)", "端口名", "注释", "数据类型(线束名)"],
            ["dir", "name", "comment", "dtype"],
            parent=parent
        )


class StoragesDialog(_TableDialog):
    def __init__(self, parent=None):
        super().__init__(
            "编辑：存储对象列表",
            ["类别(storage/cycle_delay/cycle_tmp)", "成员名", "成员类型(线束名)", "整数长度(表达式)", "注释", "默认值(表达式)", "维度(表达式数组)"],
            ["kind", "name", "type", "int_len", "comment", "default", "dims"],
            parent=parent
        )


class ConnectionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑：连接列表")
        self.setModal(True)
        self.resize(1180, 760)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"说明：本模块使用 {SELF_INSTANCE} 表示“本模块边界”。"))

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.reqsvc_page = self._make_page(
            "请求/服务连接",
            ["源实例名", "源端口名", "目标实例名", "目标端口名"],
            ["src_inst", "src_port", "dst_inst", "dst_port"],
            "规则：子实例请求 -> 子实例服务；子实例请求 -> 本模块请求；本模块服务 -> 子实例服务",
        )
        self.instpipe_page = self._make_page(
            "实例/管道连接",
            ["源实例名", "源端口名", "目标实例名", "目标端口名(管道实例可留空)"],
            ["src_inst", "src_port", "dst_inst", "dst_port"],
            "规则：子实例/本模块管道端口可连接到管道实例；子实例端口也可映射到本模块同向端口",
        )
        self.block_page = self._make_page(
            "阻塞传递连接",
            ["源实例名", "目标实例名"],
            ["src_inst", "dst_inst"],
            "规则：仅用于模块子实例 + 本模块边界",
        )
        self.order_page = self._make_page(
            "更新次序连接",
            ["源对象名", "目标对象名"],
            ["src_inst", "dst_inst"],
            "规则：用于模块子实例 + 时钟代码块的更新次序约束",
        )

        self.tabs.addTab(self.reqsvc_page["widget"], "请求/服务")
        self.tabs.addTab(self.instpipe_page["widget"], "实例/管道")
        self.tabs.addTab(self.block_page["widget"], "阻塞传递")
        self.tabs.addTab(self.order_page["widget"], "更新次序")

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _make_page(self, title: str, headers: list[str], keys: list[str], hint: str) -> dict:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(hint)
        label.setWordWrap(True)
        layout.addWidget(label)

        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        bar = QHBoxLayout()
        bar.addStretch(1)
        btn_add = QPushButton("新增")
        btn_del = QPushButton("删除选中")
        bar.addWidget(btn_add)
        bar.addWidget(btn_del)

        btn_add.clicked.connect(lambda: table.insertRow(table.rowCount()))
        btn_del.clicked.connect(lambda: table.removeRow(table.currentRow()) if table.currentRow() >= 0 else None)

        layout.addLayout(bar)
        layout.addWidget(table, 1)

        return {
            "widget": widget,
            "title": title,
            "keys": keys,
            "table": table,
        }

    def _load_table(self, page: dict, rows: list[dict]):
        table = page["table"]
        table.setRowCount(0)
        keys = page["keys"]
        for row in rows or []:
            r = table.rowCount()
            table.insertRow(r)
            for c, key in enumerate(keys):
                table.setItem(r, c, QTableWidgetItem(str(row.get(key, ""))))

    def _dump_table(self, page: dict) -> list[dict]:
        out = []
        table = page["table"]
        keys = page["keys"]
        for r in range(table.rowCount()):
            row = {}
            empty = True
            for c, key in enumerate(keys):
                item = table.item(r, c)
                value = item.text().strip() if item else ""
                if value:
                    empty = False
                row[key] = value
            if not empty:
                out.append(row)
        return out

    def load(self, data: dict):
        self._load_table(self.reqsvc_page, _safe_list(data.get("reqsvc_conns", [])))
        self._load_table(self.instpipe_page, _safe_list(data.get("instpipe_conns", [])))
        self._load_table(self.block_page, _safe_list(data.get("block_conns", [])))
        self._load_table(self.order_page, _safe_list(data.get("orders", [])))

    def dump(self) -> dict:
        return {
            "reqsvc_conns": self._dump_table(self.reqsvc_page),
            "instpipe_conns": self._dump_table(self.instpipe_page),
            "block_conns": self._dump_table(self.block_page),
            "orders": self._dump_table(self.order_page),
        }


class CodeBlocksDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑：代码块列表")
        self.setModal(True)
        self.resize(980, 680)

        root = QVBoxLayout(self)

        root.addWidget(QLabel("时钟代码块列表"))
        self.clock = _TableDialog("clock", ["代码块名", "注释", "代码段(C++多行文本)"], ["name", "comment", "code"], parent=self)
        root.addWidget(self.clock.tbl, 1)

        root.addWidget(QLabel("服务代码块列表"))
        self.service = _TableDialog("service", ["服务端口名", "代码段(C++多行文本)"], ["port", "code"], parent=self)
        root.addWidget(self.service.tbl, 1)

        root.addWidget(QLabel("子实例请求代码块列表"))
        self.subreq = _TableDialog("subreq", ["子实例名", "子实例请求端口名", "代码段(C++多行文本)"], ["inst", "port", "code"], parent=self)
        root.addWidget(self.subreq.tbl, 1)

        root.addWidget(QLabel("帮助函数代码段"))
        self.helper_edit = QTextEdit()
        self.helper_edit.setPlaceholderText("帮助函数代码段（C++ 多行文本）")
        root.addWidget(self.helper_edit, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def load(self, data: dict):
        self.clock.load(_safe_list(data.get("clock_blocks", [])))
        self.service.load(_safe_list(data.get("service_blocks", [])))
        self.subreq.load(_safe_list(data.get("subreq_blocks", [])))
        helper = data.get("helper_code", [])
        self.helper_edit.setPlainText("\n".join(helper) if isinstance(helper, list) else str(helper or ""))

    def dump(self) -> dict:
        return {
            "clock_blocks": self.clock.dump(),
            "service_blocks": self.service.dump(),
            "subreq_blocks": self.subreq.dump(),
            "helper_code": self.helper_edit.toPlainText().splitlines(),
        }


# ==========================================================
# Page: ModuleCanvasPage
# ==========================================================
class ModuleCanvasPage(QWidget):
    moduleCreated = pyqtSignal(str, dict)
    moduleUpdated = pyqtSignal(str, dict)
    requestRefreshExplorer = pyqtSignal()
    requestOpenModuleCanvas = pyqtSignal(str)  # module_name
    requestOpenClockCode = pyqtSignal(str, str, dict)  # module_name, block_name, row
    requestOpenServiceCode = pyqtSignal(str, str, dict)  # module_name, port_name, row
    requestOpenSubreqCode = pyqtSignal(str, str, str, dict)  # module_name, inst, port, row
    requestOpenHelperCode = pyqtSignal(str, dict)  # module_name, row

    def __init__(self, module_name: str, module_data: dict,
                 module_resolver: Optional[Callable[[str], Optional[dict]]] = None,
                 parent=None):
        super().__init__(parent)
        self.module_name = module_name
        self.data = dict(module_data or {})
        self.data["name"] = module_name

        self.module_resolver = module_resolver or (lambda _name: None)

        self._pending_emit = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar
        self.sidebar = QWidget()
        self.sidebar.setObjectName("canvasSidebar")
        self.sidebar.setFixedWidth(220)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(10, 10, 10, 10)
        side.setSpacing(8)

        topbar = QHBoxLayout()
        self.btn_collapse = QToolButton()
        self.btn_collapse.setText("⟨")
        self.btn_collapse.setToolTip("收起侧边栏")
        self.lbl_title = QLabel(self.module_name)
        self.lbl_title.setStyleSheet("font-weight:700;")
        topbar.addWidget(self.btn_collapse, 0)
        topbar.addWidget(self.lbl_title, 1)
        side.addLayout(topbar)

        self.btn_helper_code = QPushButton("帮助函数代码")
        self.btn_local_cfg = QPushButton("本地配置列表")
        self.btn_local_harness = QPushButton("本地线束列表")
        self.btn_ports = QPushButton("端口列表")
        self.btn_submodules = QPushButton("子模块列表")
        self.btn_storages = QPushButton("存储对象列表")
        self.btn_connections = QPushButton("连接列表")
        self.btn_code_blocks = QPushButton("代码块列表")

        for b in [self.btn_helper_code, self.btn_local_cfg, self.btn_local_harness, self.btn_ports,
                  self.btn_submodules, self.btn_storages, self.btn_connections, self.btn_code_blocks]:
            b.setMinimumHeight(34)
            side.addWidget(b)

        self.cfg_section_btn, self.cfg_section_body = self._make_sidebar_section("本地配置")
        self.local_cfg_tree = self._make_sidebar_tree()
        cfg_body_layout = QVBoxLayout(self.cfg_section_body)
        cfg_body_layout.setContentsMargins(0, 0, 0, 0)
        cfg_body_layout.setSpacing(6)
        cfg_body_layout.addWidget(self.local_cfg_tree)
        side.addWidget(self.cfg_section_btn)
        side.addWidget(self.cfg_section_body)

        self.harness_section_btn, self.harness_section_body = self._make_sidebar_section("本地线组")
        self.local_harness_tree = self._make_sidebar_tree()
        harness_body_layout = QVBoxLayout(self.harness_section_body)
        harness_body_layout.setContentsMargins(0, 0, 0, 0)
        harness_body_layout.setSpacing(6)
        harness_body_layout.addWidget(self.local_harness_tree)
        side.addWidget(self.harness_section_btn)
        side.addWidget(self.harness_section_body)

        self.preview_section_btn, self.preview_section_body = self._make_sidebar_section("预览", expanded=True)
        self.preview_title = QLabel("未选择")
        self.preview_title.setStyleSheet("font-weight:600;")
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(120)
        preview_layout = QVBoxLayout(self.preview_section_body)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)
        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_text)
        side.addWidget(self.preview_section_btn)
        side.addWidget(self.preview_section_body)

        side.addStretch(1)
        root.addWidget(self.sidebar)

        # ---- Canvas + top action bar
        self.canvas = ModuleCanvas()
        self.canvas_panel = QWidget()
        self.canvas_panel.setObjectName("moduleCanvasPanel")
        canvas_panel_layout = QVBoxLayout(self.canvas_panel)
        canvas_panel_layout.setContentsMargins(0, 0, 0, 0)
        canvas_panel_layout.setSpacing(0)

        self.canvas_topbar = QWidget()
        self.canvas_topbar.setObjectName("moduleCanvasTopbar")
        top_actions = QHBoxLayout(self.canvas_topbar)
        top_actions.setContentsMargins(12, 10, 12, 10)
        top_actions.setSpacing(8)

        self.btn_top_add_module = QPushButton("新增模块实例")
        self.btn_top_add_pipe = QPushButton("新增管道实例")
        self.btn_top_add_clock = QPushButton("新增时钟代码块")
        self.btn_top_edit_selected = QPushButton("编辑选中")
        self.btn_top_delete_selected = QPushButton("删除选中")
        self.btn_top_connections = QPushButton("编辑连接")
        self.btn_top_code_blocks = QPushButton("代码块管理")
        self.btn_top_helper_code = QPushButton("帮助函数")
        self.lbl_canvas_hint = QLabel("双击本模块服务端口或子模块请求端口，可直接打开对应代码页")
        self.lbl_canvas_hint.setStyleSheet("color:#94a3b8;")

        for btn in (
            self.btn_top_add_module,
            self.btn_top_add_pipe,
            self.btn_top_add_clock,
            self.btn_top_edit_selected,
            self.btn_top_delete_selected,
            self.btn_top_connections,
            self.btn_top_code_blocks,
            self.btn_top_helper_code,
        ):
            btn.setMinimumHeight(30)
            top_actions.addWidget(btn, 0)
        top_actions.addStretch(1)
        top_actions.addWidget(self.lbl_canvas_hint, 0)

        canvas_panel_layout.addWidget(self.canvas_topbar, 0)
        canvas_panel_layout.addWidget(self.canvas, 1)

        if "parent_port_pos" not in self.data or not isinstance(self.data["parent_port_pos"], dict):
            self.data["parent_port_pos"] = {}
        for key in ("reqsvc_conns", "instpipe_conns", "block_conns", "orders"):
            if key not in self.data or not isinstance(self.data[key], list):
                self.data[key] = []

        self.canvas.on_parent_port_moved = self._on_parent_port_moved
        self.canvas.resolve_connection = self._resolve_connection_from_ports
        self.canvas.on_edge_deleted = self._delete_connection_edge
        self.canvas.on_port_double_clicked = self._open_code_from_port
        self.canvas.retarget_connection = self._retarget_connection_edge

        root.addWidget(self.canvas_panel, 1)

        self._current_canvas_selection = None
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self._backspace_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self._edit_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)

        self._refresh_parent_ports()

        self.btn_collapse.clicked.connect(self._toggle_sidebar)
        self.btn_helper_code.clicked.connect(self._open_helper_code)
        self.btn_local_cfg.clicked.connect(self._edit_local_cfg)
        self.btn_local_harness.clicked.connect(self._edit_local_harness)
        self.btn_ports.clicked.connect(self._edit_pipe_ports)
        self.btn_submodules.clicked.connect(self._edit_submodules_list)
        self.btn_storages.clicked.connect(self._edit_storages)
        self.btn_connections.clicked.connect(self._edit_connections)
        self.btn_code_blocks.clicked.connect(self._edit_code_blocks)
        self.btn_top_add_module.clicked.connect(self._create_module_inst_from_toolbar)
        self.btn_top_add_pipe.clicked.connect(self._create_pipe_inst_from_toolbar)
        self.btn_top_add_clock.clicked.connect(self._create_clock_block_from_toolbar)
        self.btn_top_edit_selected.clicked.connect(self._edit_selected_canvas_item)
        self.btn_top_delete_selected.clicked.connect(self._delete_selected_canvas_item)
        self.btn_top_connections.clicked.connect(self._edit_connections)
        self.btn_top_code_blocks.clicked.connect(self._edit_code_blocks)
        self.btn_top_helper_code.clicked.connect(self._open_helper_code)
        self.local_cfg_tree.itemClicked.connect(self._on_sidebar_item_clicked)
        self.local_harness_tree.itemClicked.connect(self._on_sidebar_item_clicked)
        self.local_cfg_tree.itemDoubleClicked.connect(lambda _item, _col: self._edit_local_cfg())
        self.local_harness_tree.itemDoubleClicked.connect(lambda _item, _col: self._edit_local_harness())
        self.local_cfg_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.local_harness_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.local_cfg_tree.customContextMenuRequested.connect(lambda pos: self._show_sidebar_item_menu(self.local_cfg_tree, pos, "cfg"))
        self.local_harness_tree.customContextMenuRequested.connect(lambda pos: self._show_sidebar_item_menu(self.local_harness_tree, pos, "harness"))

        self.canvas.requestCreateModuleInst.connect(self._create_module_inst_at)
        self.canvas.requestCreatePipeInst.connect(self._create_pipe_inst_at)
        self.canvas.requestCreateClockBlock.connect(self._create_clock_block_at)
        self.canvas.requestEditNode.connect(self._edit_node)
        self.canvas.requestEnterSubmodule.connect(self._enter_submodule)
        self.canvas.requestOpenNode.connect(self._open_node)
        self.canvas.requestDeleteNode.connect(self._delete_node)
        self.canvas.requestNodeResized.connect(self._on_node_resized)  # 强烈建议：尺寸持久化
        self.canvas.requestPreviewSelection.connect(self._on_canvas_item_selected)
        self.canvas.requestEditBoundaryPort.connect(self._edit_boundary_port)
        self.canvas.requestDeleteBoundaryPort.connect(self._delete_boundary_port)
        self._delete_shortcut.activated.connect(self._delete_selected_canvas_item)
        self._backspace_shortcut.activated.connect(self._delete_selected_canvas_item)
        self._edit_shortcut.activated.connect(self._edit_selected_canvas_item)

        # module_inst 索引（用于 refresh_canvas）
        self._inst_nodes: dict[str, BaseNodeItem] = {}
        self._pipe_nodes: dict[str, BaseNodeItem] = {}
        self._clock_nodes: dict[str, BaseNodeItem] = {}

        self._refresh_sidebar_local_views()
        self._render_all_instances()
        self._update_canvas_selection_actions()

    # --------------------------
    # Resize persistence (强烈建议)
    # --------------------------
    def _on_node_resized(self, node: BaseNodeItem):
        payload = node.payload or {}
        kind = payload.get("_kind")

        if kind == "module_inst":
            inst = _strip(payload.get("inst", ""))
            if not inst:
                return
            subs = _safe_list(self.data.get("submodules", []))
            for sm in subs:
                if _strip(sm.get("inst")) == inst:
                    sm["w"] = int(node.w)
                    sm["h"] = int(node.h)
                    break
            self.data["submodules"] = subs
            self._notify_updated()
            return

        if kind == "pipe_inst":
            inst = _strip(payload.get("inst", ""))
            if not inst:
                return
            pipes = _safe_list(self.data.get("pipes", []))
            for p in pipes:
                if _strip(p.get("inst")) == inst:
                    p["w"] = int(node.w)
                    p["h"] = int(node.h)
                    break
            self.data["pipes"] = pipes
            self._notify_updated()
            return

        if kind == "clock_block":
            name = _strip(payload.get("name", ""))
            if not name:
                return
            clocks = _safe_list(self.data.get("clock_blocks", []))
            for block in clocks:
                if _strip(block.get("name")) == name:
                    block["w"] = int(node.w)
                    block["h"] = int(node.h)
                    break
            self.data["clock_blocks"] = clocks
            self._notify_updated()
            return

    # --------------------------
    # Open / Delete
    # --------------------------
    def _open_node(self, node: BaseNodeItem):
        payload = node.payload or {}
        kind = payload.get("_kind")
        if kind == "module_inst":
            mod = _strip(payload.get("module", ""))
            if not mod:
                QMessageBox.warning(self, "无法打开", "该模块实例未设置所属模块名（module 为空）。")
                return

            defn = self.module_resolver(mod)
            if defn is None:
                QMessageBox.warning(self, "模块不存在", f"未找到模块定义“{mod}”，无法打开其画布。")
                return

            self.requestOpenModuleCanvas.emit(mod)
            return

        if kind == "clock_block":
            block_name = _strip(payload.get("name", ""))
            if not block_name:
                QMessageBox.warning(self, "无法打开", "该时钟代码块缺少名称。")
                return
            self.requestOpenClockCode.emit(self.module_name, block_name, dict(payload))
            return

    def _delete_node(self, node: BaseNodeItem):
        payload = node.payload or {}
        kind = payload.get("_kind")

        if kind == "module_inst":
            inst = _strip(payload.get("inst", ""))
            if not inst:
                return
            ok = QMessageBox.question(
                self, "确认删除",
                f"确定删除模块实例“{inst}”吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ok != QMessageBox.StandardButton.Yes:
                return

            subs = _safe_list(self.data.get("submodules", []))
            self.data["submodules"] = [x for x in subs if _strip(x.get("inst")) != inst]
            self._remove_connections_for_instance(inst)
            self._remove_subreq_code_rows_for_instance(inst)

            try:
                node.clear_anchor_edges()
                node.clear_ports()
            except Exception:
                pass
            sc = self.canvas.scene
            if sc and node.scene() is sc:
                sc.removeItem(node)

            if inst in self._inst_nodes:
                self._inst_nodes.pop(inst, None)

            self._notify_updated()
            return

        if kind == "pipe_inst":
            inst = _strip(payload.get("inst", ""))
            if not inst:
                return
            ok = QMessageBox.question(
                self, "确认删除",
                f"确定删除管道实例“{inst}”吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ok != QMessageBox.StandardButton.Yes:
                return

            pipes = _safe_list(self.data.get("pipes", []))
            self.data["pipes"] = [x for x in pipes if _strip(x.get("inst")) != inst]
            self._remove_connections_for_instance(inst)

            try:
                node.clear_anchor_edges()
                node.clear_ports()
            except Exception:
                pass
            sc = self.canvas.scene
            if sc and node.scene() is sc:
                sc.removeItem(node)

            if inst in self._pipe_nodes:
                self._pipe_nodes.pop(inst, None)

            self._notify_updated()
            return

        if kind == "clock_block":
            name = _strip(payload.get("name", ""))
            if not name:
                return
            ok = QMessageBox.question(
                self, "确认删除",
                f"确定删除时钟代码块“{name}”吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ok != QMessageBox.StandardButton.Yes:
                return

            clocks = _safe_list(self.data.get("clock_blocks", []))
            self.data["clock_blocks"] = [x for x in clocks if _strip(x.get("name")) != name]
            self.data["orders"] = [
                row for row in _safe_list(self.data.get("orders", []))
                if _strip(row.get("dst_inst", "")) != name
            ]

            try:
                node.clear_anchor_edges()
                node.clear_ports()
            except Exception:
                pass
            sc = self.canvas.scene
            if sc and node.scene() is sc:
                sc.removeItem(node)

            self._clock_nodes.pop(name, None)
            self._render_connections()
            self._notify_updated()
            return

    # --------------------------
    # Parent ports movement persistence
    # --------------------------
    def _on_parent_port_moved(self, key: str, pos: QPointF):
        store = self.data.setdefault("parent_port_pos", {})
        store[key] = {"x": float(pos.x()), "y": float(pos.y())}
        self._notify_updated()

    # --------------------------
    # Sidebar
    # --------------------------
    def _make_sidebar_section(self, title: str, expanded: bool = False) -> tuple[QToolButton, QWidget]:
        btn = QToolButton()
        btn.setText(title)
        btn.setCheckable(True)
        btn.setChecked(expanded)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        btn.setMinimumHeight(28)

        body = QWidget()
        body.setVisible(expanded)

        btn.clicked.connect(lambda checked, b=btn, w=body: self._set_sidebar_section_expanded(b, w, checked))
        return btn, body

    def _set_sidebar_section_expanded(self, button: QToolButton, body: QWidget, expanded: bool):
        button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        body.setVisible(expanded)

    def _make_sidebar_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(False)
        tree.setIndentation(10)
        tree.setMinimumHeight(90)
        tree.setMaximumHeight(140)
        return tree

    def _set_sidebar_preview(self, title: str, lines: list[str]):
        self.preview_title.setText(title or "未选择")
        self.preview_text.setPlainText("\n".join(lines).strip())

    def _selection_action_state(self, item) -> tuple[bool, bool, str]:
        if isinstance(item, BaseNodeItem):
            payload = item.payload or {}
            kind = payload.get("_kind", "")
            label = {
                "module_inst": "模块实例",
                "pipe_inst": "管道实例",
                "clock_block": "时钟代码块",
            }.get(kind, "节点")
            return True, True, label

        if isinstance(item, EdgeItem):
            return True, True, "连接"

        if isinstance(item, PortHandle):
            item = item.dot

        if isinstance(item, PortDot):
            if item.owner_kind == "boundary":
                return True, True, "边界端口"
            return False, False, "端口"

        return False, False, ""

    def _update_canvas_selection_actions(self):
        can_edit, can_delete, label = self._selection_action_state(self._current_canvas_selection)
        self.btn_top_edit_selected.setEnabled(can_edit)
        self.btn_top_delete_selected.setEnabled(can_delete)
        if label:
            self.btn_top_edit_selected.setToolTip(f"编辑当前选中的{label}（Ctrl+E）")
            self.btn_top_delete_selected.setToolTip(f"删除当前选中的{label}（Delete / Backspace）")
        else:
            self.btn_top_edit_selected.setToolTip("先在画布中选中一个可编辑对象")
            self.btn_top_delete_selected.setToolTip("先在画布中选中一个可删除对象")

    def _port_definition_for(self, port: PortDot) -> dict:
        if port.owner_kind == "boundary":
            if port.port_kind == "pipe":
                for row in _safe_list(self.data.get("pipe_ports", [])):
                    if _strip(row.get("name", "")) == _strip(port.port_name) and _strip(row.get("dir", "")) == _strip(port.direction):
                        return dict(row)
            else:
                target_kind = "req" if port.direction == "req" else "service"
                for row in _safe_list(self.data.get("rpcs", [])):
                    if _strip(row.get("name", "")) == _strip(port.port_name) and _strip(row.get("kind", "")) == target_kind:
                        return dict(row)
            return {}

        if port.owner_kind == "module_inst":
            inst_name = _strip(port.owner_name)
            sub = next((row for row in _safe_list(self.data.get("submodules", [])) if _strip(row.get("inst", "")) == inst_name), None)
            mod_name = _strip(sub.get("module", "")) if isinstance(sub, dict) else ""
            defn = self.module_resolver(mod_name) if mod_name else None
            if isinstance(defn, dict):
                if port.port_kind == "pipe":
                    for row in _safe_list(defn.get("pipe_ports", [])):
                        if _strip(row.get("name", "")) == _strip(port.port_name) and _strip(row.get("dir", "")) == _strip(port.direction):
                            return dict(row)
                else:
                    target_kind = "req" if port.direction == "req" else "service"
                    for row in _safe_list(defn.get("rpcs", [])):
                        if _strip(row.get("name", "")) == _strip(port.port_name) and _strip(row.get("kind", "")) == target_kind:
                            return dict(row)
            return {}

        if port.owner_kind == "pipe_inst":
            inst_name = _strip(port.owner_name)
            pipe_row = next((row for row in _safe_list(self.data.get("pipes", [])) if _strip(row.get("inst", "")) == inst_name), None)
            if isinstance(pipe_row, dict):
                return {
                    "name": port.port_name,
                    "dir": port.direction,
                    "comment": pipe_row.get("comment", ""),
                    "dtype": pipe_row.get("dtype", ""),
                }
        return {}

    def _module_summary_preview(self):
        self._set_sidebar_preview(
            f"模块：{self.module_name}",
            [
                f"子模块实例：{len(_safe_list(self.data.get('submodules', [])))}",
                f"管道实例：{len(_safe_list(self.data.get('pipes', [])))}",
                f"时钟代码块：{len(_safe_list(self.data.get('clock_blocks', [])))}",
                f"连接数：{len(_safe_list(self.data.get('reqsvc_conns', []))) + len(_safe_list(self.data.get('instpipe_conns', []))) + len(_safe_list(self.data.get('block_conns', []))) + len(_safe_list(self.data.get('orders', [])))}",
            ],
        )

    def _preview_for_node(self, node: BaseNodeItem):
        payload = node.payload or {}
        kind = payload.get("_kind", "")
        if kind == "module_inst":
            inst_name = _strip(payload.get("inst", ""))
            module_name = _strip(payload.get("module", ""))
            defn = self.module_resolver(module_name) if module_name else None
            self._set_sidebar_preview(
                f"模块实例：{inst_name or '（未命名）'}",
                [
                    f"所属模块：{module_name or '（未填写）'}",
                    f"注释：{payload.get('comment', '') or '（无注释）'}",
                    "",
                    f"对外 RPC 端口：{len(_safe_list(defn.get('rpcs', [])) if isinstance(defn, dict) else [])}",
                    f"对外 Pipe 端口：{len(_safe_list(defn.get('pipe_ports', [])) if isinstance(defn, dict) else [])}",
                ],
            )
            return

        if kind == "pipe_inst":
            self._set_sidebar_preview(
                f"管道实例：{_strip(payload.get('inst', '')) or '（未命名）'}",
                [
                    f"数据类型：{payload.get('dtype', '') or '（未填写）'}",
                    f"注释：{payload.get('comment', '') or '（无注释）'}",
                    "",
                    f"输入尺寸：{payload.get('in_size', '') or '（未填写）'}",
                    f"输出尺寸：{payload.get('out_size', '') or '（未填写）'}",
                    f"缓冲区大小：{payload.get('buf', '') or '（未填写）'}",
                    f"延迟：{payload.get('latency', '') or '（未填写）'}",
                    f"握手：{payload.get('handshake', '') or '（未填写）'}",
                    f"有效标志：{payload.get('valid', '') or '（未填写）'}",
                ],
            )
            return

        if kind == "clock_block":
            self._set_sidebar_preview(
                f"时钟代码块：{_strip(payload.get('name', '')) or '（未命名）'}",
                [
                    f"注释：{payload.get('comment', '') or '（无注释）'}",
                    "",
                    "双击可打开对应代码页。",
                ],
            )
            return

        self._module_summary_preview()

    def _preview_for_port(self, port):
        if isinstance(port, PortHandle):
            port = port.dot
        if not isinstance(port, PortDot):
            self._module_summary_preview()
            return

        definition = self._port_definition_for(port)
        owner_text = "本模块边界" if port.owner_kind == "boundary" else _strip(port.owner_name) or "（未命名）"
        title = f"端口：{owner_text}.{_strip(port.port_name)}"
        lines = [
            f"类别：{'请求/服务' if port.port_kind == 'rpc' else '管道'}",
            f"方向：{port.direction}",
            f"所属对象：{owner_text}",
        ]
        if definition:
            if _strip(definition.get("dtype", "")):
                lines.append(f"数据类型：{definition.get('dtype', '')}")
            if _strip(definition.get("params", "")):
                lines.append(f"参数：{definition.get('params', '')}")
            if _strip(definition.get("returns", "")):
                lines.append(f"返回：{definition.get('returns', '')}")
            lines.append(f"注释：{definition.get('comment', '') or '（无注释）'}")
        else:
            lines.append("注释：（无详细信息）")
        if port.owner_kind == "boundary":
            lines.append("")
            lines.append("右键可直接编辑或删除该边界端口。")
        if port.owner_kind == "pipe_inst":
            lines.append("")
            lines.append("说明：该端口来自管道实例的固定 IN/OUT 端口。")
        self._set_sidebar_preview(title, lines)

    def _preview_for_edge(self, edge: EdgeItem):
        group = _strip(edge.conn_group)
        title_map = {
            "reqsvc_conns": "连接预览：请求/服务",
            "instpipe_conns": "连接预览：实例/管道",
            "block_conns": "连接预览：阻塞传递",
            "orders": "连接预览：更新次序",
        }
        lines = [edge.toolTip() or "（无描述）", ""]
        if edge.conn_key:
            lines.append(f"连接键：{edge.conn_key}")
        lines.append("右键或双击可编辑该连接。")
        lines.append("选中后可拖拽端点修改连接位置。")
        self._set_sidebar_preview(title_map.get(group, "连接预览"), lines)

    def _on_canvas_item_selected(self, item):
        self._current_canvas_selection = item
        self._update_canvas_selection_actions()
        if item is None:
            self._module_summary_preview()
            return
        if isinstance(item, EdgeItem):
            self._preview_for_edge(item)
            return
        if isinstance(item, (PortDot, PortHandle)):
            self._preview_for_port(item)
            return
        if isinstance(item, BaseNodeItem):
            self._preview_for_node(item)
            return
        self._module_summary_preview()

    def _edit_selected_canvas_item(self):
        item = self._current_canvas_selection
        if isinstance(item, PortHandle):
            item = item.dot

        if isinstance(item, BaseNodeItem):
            self._edit_node(item)
            return
        if isinstance(item, EdgeItem):
            self._edit_connection_edge(item)
            return
        if isinstance(item, PortDot) and item.owner_kind == "boundary":
            self._edit_boundary_port(item)
            return

    def _delete_selected_canvas_item(self):
        item = self._current_canvas_selection
        if isinstance(item, PortHandle):
            item = item.dot

        if isinstance(item, BaseNodeItem):
            self._delete_node(item)
            return
        if isinstance(item, EdgeItem):
            self._delete_connection_edge(item)
            return
        if isinstance(item, PortDot) and item.owner_kind == "boundary":
            self._delete_boundary_port(item)
            return

    def _populate_local_cfg_tree(self):
        self.local_cfg_tree.clear()
        rows = _safe_list(self.data.get("local_cfgs", []))
        if not rows:
            item = QTreeWidgetItem(["（无本地配置）"])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.local_cfg_tree.addTopLevelItem(item)
            return

        for row in rows:
            name = _strip(row.get("name", "")) or "（未命名）"
            default = _strip(row.get("default", ""))
            comment = _strip(row.get("comment", ""))
            label = name if not default else f"{name} = {default}"
            item = QTreeWidgetItem([label])
            payload = {
                "kind": "local_cfg",
                "name": name,
                "default": default,
                "comment": comment,
            }
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            item.setToolTip(0, comment or default or "（无详细信息）")
            self.local_cfg_tree.addTopLevelItem(item)

    def _populate_local_harness_tree(self):
        self.local_harness_tree.clear()
        rows = _safe_list(self.data.get("local_harnesses", []))
        if not rows:
            item = QTreeWidgetItem(["（无本地线组）"])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.local_harness_tree.addTopLevelItem(item)
            return

        for row in rows:
            name = _strip(row.get("name", "")) or "（未命名）"
            mode = _strip(row.get("mode", "")) or "members"
            comment = _strip(row.get("comment", ""))
            body = _strip(row.get("body", ""))
            label = f"{name} [{mode}]"
            item = QTreeWidgetItem([label])
            payload = {
                "kind": "local_harness",
                "name": name,
                "mode": mode,
                "comment": comment,
                "body": body,
            }
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            item.setToolTip(0, comment or _first_line(body) or "（无详细信息）")
            self.local_harness_tree.addTopLevelItem(item)

    def _refresh_sidebar_local_views(self):
        self._populate_local_cfg_tree()
        self._populate_local_harness_tree()

        if self.local_cfg_tree.topLevelItemCount() > 0:
            item = self.local_cfg_tree.topLevelItem(0)
            if item and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self.local_cfg_tree.setCurrentItem(item)
                self._on_sidebar_item_clicked(item, 0)
                return

        if self.local_harness_tree.topLevelItemCount() > 0:
            item = self.local_harness_tree.topLevelItem(0)
            if item and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self.local_harness_tree.setCurrentItem(item)
                self._on_sidebar_item_clicked(item, 0)
                return

        self._set_sidebar_preview("未选择", ["请选择本地配置或本地线组以查看详细信息。"])

    def _on_sidebar_item_clicked(self, item: QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            self._set_sidebar_preview("未选择", ["请选择本地配置或本地线组以查看详细信息。"])
            return

        kind = payload.get("kind", "")
        if kind == "local_cfg":
            self._set_sidebar_preview(
                f"本地配置：{payload.get('name', '')}",
                [
                    f"默认值：{payload.get('default', '') or '（空）'}",
                    "",
                    f"注释：{payload.get('comment', '') or '（无注释）'}",
                ],
            )
            return

        if kind == "local_harness":
            self._set_sidebar_preview(
                f"本地线组：{payload.get('name', '')}",
                [
                    f"定义模式：{payload.get('mode', '') or 'members'}",
                    "",
                    f"注释：{payload.get('comment', '') or '（无注释）'}",
                    "",
                    f"定义预览：{_first_line(payload.get('body', '')) or '（空）'}",
                ],
            )
            return

        self._set_sidebar_preview("未选择", ["请选择本地配置或本地线组以查看详细信息。"])

    def _show_sidebar_item_menu(self, tree: QTreeWidget, pos, kind: str):
        item = tree.itemAt(pos)
        if item is None:
            return
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return

        menu = QMenu(self)
        act_edit = menu.addAction("编辑")
        act = menu.exec(tree.viewport().mapToGlobal(pos))
        if act == act_edit:
            if kind == "cfg":
                self._edit_local_cfg()
            elif kind == "harness":
                self._edit_local_harness()

    def _toggle_sidebar(self):
        if self.sidebar.width() > 60:
            self.sidebar.setFixedWidth(52)
            self.btn_collapse.setText("⟩")
            self.btn_collapse.setToolTip("展开侧边栏")
            self.lbl_title.setVisible(False)
            self.btn_helper_code.setText("辅")
            self.btn_local_cfg.setText("配")
            self.btn_local_harness.setText("束")
            self.btn_ports.setText("端")
            self.btn_submodules.setText("子")
            self.btn_storages.setText("存")
            self.btn_connections.setText("连")
            self.btn_code_blocks.setText("码")
            self.cfg_section_btn.setText("地配")
            self.harness_section_btn.setText("地束")
            self.preview_section_btn.setText("预")
        else:
            self.sidebar.setFixedWidth(220)
            self.btn_collapse.setText("⟨")
            self.btn_collapse.setToolTip("收起侧边栏")
            self.lbl_title.setVisible(True)
            self.btn_helper_code.setText("帮助函数代码")
            self.btn_local_cfg.setText("本地配置列表")
            self.btn_local_harness.setText("本地线束列表")
            self.btn_ports.setText("端口列表")
            self.btn_submodules.setText("子模块列表")
            self.btn_storages.setText("存储对象列表")
            self.btn_connections.setText("连接列表")
            self.btn_code_blocks.setText("代码块列表")
            self.cfg_section_btn.setText("本地配置")
            self.harness_section_btn.setText("本地线组")
            self.preview_section_btn.setText("预览")

    # --------------------------
    # Update emit
    # --------------------------
    def _notify_updated(self):
        if self._pending_emit:
            return
        self._pending_emit = True

        def _emit():
            self._pending_emit = False
            self.moduleUpdated.emit(self.module_name, self.data)

        QTimer.singleShot(0, _emit)

    def _emit_updated_now(self):
        self._pending_emit = False
        self.moduleUpdated.emit(self.module_name, self.data)

    def _helper_code_row(self) -> dict:
        helper = self.data.get("helper_code", [])
        if isinstance(helper, list):
            code = "\n".join(str(line) for line in helper)
        else:
            code = str(helper or "")
        return {
            "name": "helper_code",
            "code": code,
        }

    def _open_helper_code(self):
        self.requestOpenHelperCode.emit(self.module_name, self._helper_code_row())

    def _visible_scene_center(self) -> QPointF:
        rect = self.canvas.view.viewport().rect()
        return self.canvas.view.mapToScene(rect.center())

    def _create_module_inst_from_toolbar(self):
        self._create_module_inst_at(self._visible_scene_center())

    def _create_pipe_inst_from_toolbar(self):
        self._create_pipe_inst_at(self._visible_scene_center())

    def _create_clock_block_from_toolbar(self):
        self._create_clock_block_at(self._visible_scene_center())

    def _service_code_row(self, port_name: str) -> Optional[dict]:
        target = _strip(port_name)
        for row in _safe_list(self.data.get("service_blocks", [])):
            if _strip(row.get("port", "")) == target:
                return row
        return None

    def _subreq_code_row(self, inst_name: str, port_name: str) -> Optional[dict]:
        inst = _strip(inst_name)
        port = _strip(port_name)
        for row in _safe_list(self.data.get("subreq_blocks", [])):
            if _strip(row.get("inst", "")) == inst and _strip(row.get("port", "")) == port:
                return row
        return None

    def _prune_service_code_rows(self):
        allowed = {
            _strip(row.get("name", ""))
            for row in _safe_list(self.data.get("rpcs", []))
            if _strip(row.get("kind", "")) == "service" and _strip(row.get("name", ""))
        }
        rows = [
            row for row in _safe_list(self.data.get("service_blocks", []))
            if _strip(row.get("port", "")) in allowed
        ]
        self.data["service_blocks"] = rows

    def _prune_subreq_code_rows_for_instance(self, inst_name: str, module_name: str):
        inst = _strip(inst_name)
        if not inst:
            return

        defn = self.module_resolver(module_name) if module_name else None
        rpc_rows = _safe_list(defn.get("rpcs", [])) if isinstance(defn, dict) else []
        allowed_ports = {
            _strip(row.get("name", ""))
            for row in rpc_rows
            if _strip(row.get("kind", "")) == "req" and _strip(row.get("name", ""))
        }
        rows = []
        for row in _safe_list(self.data.get("subreq_blocks", [])):
            if _strip(row.get("inst", "")) != inst:
                rows.append(row)
                continue
            if _strip(row.get("port", "")) in allowed_ports:
                rows.append(row)
        self.data["subreq_blocks"] = rows

    def _remove_subreq_code_rows_for_instance(self, inst_name: str):
        inst = _strip(inst_name)
        self.data["subreq_blocks"] = [
            row for row in _safe_list(self.data.get("subreq_blocks", []))
            if _strip(row.get("inst", "")) != inst
        ]

    def _replace_subreq_inst_name(self, old_name: str, new_name: str):
        old_inst = _strip(old_name)
        new_inst = _strip(new_name)
        rows = []
        for row in _safe_list(self.data.get("subreq_blocks", [])):
            item = dict(row)
            if _strip(item.get("inst", "")) == old_inst:
                item["inst"] = new_inst
            rows.append(item)
        self.data["subreq_blocks"] = rows

    def _ensure_service_code_row(self, port_name: str) -> tuple[dict, bool]:
        row = self._service_code_row(port_name)
        if isinstance(row, dict):
            return row, False
        rows = _safe_list(self.data.get("service_blocks", []))
        row = {"port": _strip(port_name), "code": ""}
        rows.append(row)
        self.data["service_blocks"] = rows
        return row, True

    def _ensure_subreq_code_row(self, inst_name: str, port_name: str) -> tuple[dict, bool]:
        row = self._subreq_code_row(inst_name, port_name)
        if isinstance(row, dict):
            return row, False
        rows = _safe_list(self.data.get("subreq_blocks", []))
        row = {"inst": _strip(inst_name), "port": _strip(port_name), "code": ""}
        rows.append(row)
        self.data["subreq_blocks"] = rows
        return row, True

    def _open_code_from_port(self, port: PortDot) -> bool:
        if port.port_kind != "rpc":
            return False

        if port.owner_kind == "boundary" and port.direction == "serv":
            row, created = self._ensure_service_code_row(port.port_name)
            if created:
                self._emit_updated_now()
            self.requestOpenServiceCode.emit(self.module_name, port.port_name, dict(row))
            return True

        if port.owner_kind == "module_inst" and port.direction == "req":
            row, created = self._ensure_subreq_code_row(port.owner_name, port.port_name)
            if created:
                self._emit_updated_now()
            self.requestOpenSubreqCode.emit(self.module_name, port.owner_name, port.port_name, dict(row))
            return True

        return False

    def _boundary_port_record(self, port: PortDot) -> tuple[str, int, dict] | None:
        if not isinstance(port, PortDot) or port.owner_kind != "boundary":
            return None

        if port.port_kind == "pipe":
            rows = _safe_list(self.data.get("pipe_ports", []))
            for idx, row in enumerate(rows):
                if _strip(row.get("name", "")) == _strip(port.port_name) and _strip(row.get("dir", "")) == _strip(port.direction):
                    return "pipe", idx, dict(row)
            return None

        target_kind = "req" if port.direction == "req" else "service"
        rows = _safe_list(self.data.get("rpcs", []))
        for idx, row in enumerate(rows):
            if _strip(row.get("name", "")) == _strip(port.port_name) and _strip(row.get("kind", "")) == target_kind:
                return "rpc", idx, dict(row)
        return None

    def _boundary_port_duplicate_exists(self, port_kind: str, direction: str, name: str, exclude_index: int) -> bool:
        name = _strip(name)
        direction = _strip(direction)
        if _strip(port_kind) == "pipe":
            for idx, row in enumerate(_safe_list(self.data.get("pipe_ports", []))):
                if idx == exclude_index:
                    continue
                if _strip(row.get("name", "")) == name and _strip(row.get("dir", "")) == direction:
                    return True
            return False

        target_kind = "req" if direction == "req" else "service"
        for idx, row in enumerate(_safe_list(self.data.get("rpcs", []))):
            if idx == exclude_index:
                continue
            if _strip(row.get("name", "")) == name and _strip(row.get("kind", "")) == target_kind:
                return True
        return False

    def _rename_service_code_port(self, old_name: str, new_name: str):
        old_port = _strip(old_name)
        new_port = _strip(new_name)
        rows = []
        for row in _safe_list(self.data.get("service_blocks", [])):
            item = dict(row)
            if _strip(item.get("port", "")) == old_port:
                item["port"] = new_port
            rows.append(item)
        self.data["service_blocks"] = rows

    def _retarget_boundary_pipe_connections(self, old_name: str, old_dir: str, new_name: str, new_dir: str):
        rows = []
        old_port = _strip(old_name)
        same_dir = _strip(old_dir) == _strip(new_dir)
        for row in _safe_list(self.data.get("instpipe_conns", [])):
            item = dict(row)
            if _normalize_instance_name(item.get("dst_inst", "")) == SELF_INSTANCE and _strip(item.get("dst_port", "")) == old_port:
                if not same_dir:
                    continue
                item["dst_port"] = _strip(new_name)
            rows.append(item)
        self.data["instpipe_conns"] = rows

    def _remove_boundary_pipe_connections(self, port_name: str):
        target = _strip(port_name)
        self.data["instpipe_conns"] = [
            row for row in _safe_list(self.data.get("instpipe_conns", []))
            if not (
                _normalize_instance_name(row.get("dst_inst", "")) == SELF_INSTANCE
                and _strip(row.get("dst_port", "")) == target
            )
        ]

    def _retarget_boundary_rpc_connections(self, old_name: str, old_dir: str, new_name: str, new_dir: str):
        rows = []
        old_port = _strip(old_name)
        old_dir = _strip(old_dir)
        new_dir = _strip(new_dir)
        for row in _safe_list(self.data.get("reqsvc_conns", [])):
            item = dict(row)
            if (
                old_dir == "req"
                and _normalize_instance_name(item.get("dst_inst", "")) == SELF_INSTANCE
                and _strip(item.get("dst_port", "")) == old_port
            ):
                if new_dir != "req":
                    continue
                item["dst_port"] = _strip(new_name)
            elif (
                old_dir == "serv"
                and _normalize_instance_name(item.get("src_inst", "")) == SELF_INSTANCE
                and _strip(item.get("src_port", "")) == old_port
            ):
                if new_dir != "serv":
                    continue
                item["src_port"] = _strip(new_name)
            rows.append(item)
        self.data["reqsvc_conns"] = rows

    def _remove_boundary_rpc_connections(self, port_name: str, direction: str):
        target = _strip(port_name)
        direction = _strip(direction)
        rows = []
        for row in _safe_list(self.data.get("reqsvc_conns", [])):
            if (
                direction == "req"
                and _normalize_instance_name(row.get("dst_inst", "")) == SELF_INSTANCE
                and _strip(row.get("dst_port", "")) == target
            ):
                continue
            if (
                direction == "serv"
                and _normalize_instance_name(row.get("src_inst", "")) == SELF_INSTANCE
                and _strip(row.get("src_port", "")) == target
            ):
                continue
            rows.append(row)
        self.data["reqsvc_conns"] = rows

    def _after_boundary_ports_changed(self):
        self._refresh_parent_ports()
        self._render_connections()
        self._module_summary_preview()
        self._notify_updated()

    def _edit_boundary_port(self, port: PortDot):
        record = self._boundary_port_record(port)
        if record is None:
            QMessageBox.warning(self, "无法编辑", "未找到该边界端口对应的数据定义。")
            return

        port_kind, row_idx, row = record
        dlg = PortEditDialog(
            "编辑边界端口",
            port_kind=port_kind,
            data={
                "dir": port.direction,
                "name": row.get("name", ""),
                "comment": row.get("comment", ""),
                "dtype": row.get("dtype", ""),
            },
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        updated = dlg.get_data()
        new_name = _strip(updated.get("name", ""))
        new_dir = _strip(updated.get("dir", ""))
        old_name = _strip(row.get("name", ""))
        old_dir = _strip(port.direction)
        if not new_name or not new_dir:
            QMessageBox.warning(self, "输入无效", "端口方向和端口名不能为空。")
            return

        if self._boundary_port_duplicate_exists(port_kind, new_dir, new_name, row_idx):
            QMessageBox.warning(self, "重复端口", "已存在同方向、同名称的边界端口。")
            return

        if port_kind == "pipe":
            rows = _safe_list(self.data.get("pipe_ports", []))
            rows[row_idx] = {
                "dir": new_dir,
                "name": new_name,
                "comment": updated.get("comment", ""),
                "dtype": updated.get("dtype", ""),
            }
            self.data["pipe_ports"] = rows
            self._retarget_boundary_pipe_connections(old_name, old_dir, new_name, new_dir)
        else:
            rows = _safe_list(self.data.get("rpcs", []))
            item = dict(row)
            item["kind"] = "req" if new_dir == "req" else "service"
            item["name"] = new_name
            item["comment"] = updated.get("comment", "")
            rows[row_idx] = item
            self.data["rpcs"] = rows
            self._retarget_boundary_rpc_connections(old_name, old_dir, new_name, new_dir)
            if old_dir == "serv" and new_dir == "serv" and old_name != new_name:
                self._rename_service_code_port(old_name, new_name)
            else:
                self._prune_service_code_rows()

        self._after_boundary_ports_changed()

    def _delete_boundary_port(self, port: PortDot):
        record = self._boundary_port_record(port)
        if record is None:
            QMessageBox.warning(self, "无法删除", "未找到该边界端口对应的数据定义。")
            return

        port_kind, row_idx, row = record
        port_name = _strip(row.get("name", ""))
        port_dir = _strip(port.direction)
        ok = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除边界端口“{port_name}”吗？\n相关连接会一起清理。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return

        if port_kind == "pipe":
            rows = _safe_list(self.data.get("pipe_ports", []))
            self.data["pipe_ports"] = [item for idx, item in enumerate(rows) if idx != row_idx]
            self._remove_boundary_pipe_connections(port_name)
        else:
            rows = _safe_list(self.data.get("rpcs", []))
            self.data["rpcs"] = [item for idx, item in enumerate(rows) if idx != row_idx]
            self._remove_boundary_rpc_connections(port_name, port_dir)
            self._prune_service_code_rows()

        self._set_sidebar_preview("端口已删除", [f"已删除边界端口：{port_name}"])
        self._after_boundary_ports_changed()

    # --------------------------
    # Connections
    # --------------------------
    def _display_inst_name(self, name: str) -> str:
        return "本模块" if _is_self_instance_name(name) else _strip(name)

    def _connection_key(self, group: str, row: dict) -> str:
        if group in ("reqsvc_conns", "instpipe_conns"):
            return "|".join([
                group,
                _normalize_instance_name(row.get("src_inst", "")),
                _strip(row.get("src_port", "")),
                _normalize_instance_name(row.get("dst_inst", "")),
                _strip(row.get("dst_port", "")),
            ])
        return "|".join([
            group,
            _normalize_instance_name(row.get("src_inst", "")),
            _normalize_instance_name(row.get("dst_inst", "")),
        ])

    def _connection_exists(self, group: str, row: dict) -> bool:
        target_key = self._connection_key(group, row)
        for item in _safe_list(self.data.get(group, [])):
            if self._connection_key(group, item) == target_key:
                return True
        return False

    def _append_connection(self, group: str, row: dict) -> bool:
        if self._connection_exists(group, row):
            return False
        rows = _safe_list(self.data.get(group, []))
        rows.append(dict(row))
        self.data[group] = rows
        return True

    def _remove_connection_by_key(self, group: str, key: str) -> bool:
        rows = _safe_list(self.data.get(group, []))
        kept = [row for row in rows if self._connection_key(group, row) != key]
        changed = len(kept) != len(rows)
        if changed:
            self.data[group] = kept
        return changed

    def _validator_for_group(self, group: str):
        return {
            "reqsvc_conns": self._validate_reqsvc_rows,
            "instpipe_conns": self._validate_instpipe_rows,
            "block_conns": self._validate_block_rows,
            "orders": self._validate_order_rows,
        }.get(group)

    def _replace_connection_row(self, group: str, old_key: str, new_row: dict) -> bool:
        current = _safe_list(self.data.get(group, []))
        new_key = self._connection_key(group, new_row)
        if new_key == old_key:
            return True

        for row in current:
            if self._connection_key(group, row) == new_key:
                QMessageBox.information(self, "重复连接", "目标连接已经存在。")
                return False

        replaced = False
        updated = []
        for row in current:
            if not replaced and self._connection_key(group, row) == old_key:
                updated.append(dict(new_row))
                replaced = True
            else:
                updated.append(dict(row))
        if not replaced:
            return False

        validator = self._validator_for_group(group)
        if validator is not None:
            validated = validator(updated)
            if validated is None:
                return False
            self.data[group] = validated
        else:
            self.data[group] = updated

        self._render_connections()
        self._notify_updated()
        return True

    def _remove_connections_for_instance(self, inst_name: str):
        target = _normalize_instance_name(inst_name)
        for group in ("reqsvc_conns", "instpipe_conns", "block_conns", "orders"):
            rows = []
            for row in _safe_list(self.data.get(group, [])):
                src = _normalize_instance_name(row.get("src_inst", ""))
                dst = _normalize_instance_name(row.get("dst_inst", ""))
                if src == target or dst == target:
                    continue
                rows.append(row)
            self.data[group] = rows

    def _replace_instance_name_in_connections(self, old_name: str, new_name: str):
        old_norm = _normalize_instance_name(old_name)
        new_norm = _normalize_instance_name(new_name)
        for group in ("reqsvc_conns", "instpipe_conns", "block_conns", "orders"):
            updated = []
            for row in _safe_list(self.data.get(group, [])):
                item = dict(row)
                if _normalize_instance_name(item.get("src_inst", "")) == old_norm:
                    item["src_inst"] = new_norm
                if _normalize_instance_name(item.get("dst_inst", "")) == old_norm:
                    item["dst_inst"] = new_norm
                updated.append(item)
            self.data[group] = updated

    def _find_port(self, owner_name: str, owner_kind: str, kind: str, direction: str, port_name: str) -> Optional[PortDot]:
        owner_norm = _normalize_instance_name(owner_name)
        for port in self._iter_all_ports():
            if port.owner_kind != owner_kind:
                continue
            if _normalize_instance_name(port.owner_name) != owner_norm:
                continue
            if port.port_kind != kind or port.direction != direction:
                continue
            if _strip(port.port_name) != _strip(port_name):
                continue
            return port
        return None

    def _iter_all_ports(self):
        for port in self.canvas.boundary.port_dots:
            yield port
        for node in self._inst_nodes.values():
            for port in node.ports:
                yield port
        for node in self._pipe_nodes.values():
            for port in node.ports:
                yield port

    def _anchor_for_object(self, name: str) -> Optional[LinkAnchorItem]:
        norm = _normalize_instance_name(name)
        if norm == SELF_INSTANCE:
            return self.canvas.boundary.center_anchor
        node = self._inst_nodes.get(norm)
        if isinstance(node, BaseNodeItem):
            return node.center_anchor
        clock_node = self._clock_nodes.get(_strip(name))
        if isinstance(clock_node, BaseNodeItem):
            return clock_node.center_anchor
        return None

    def _reqsvc_ports_for_record(self, row: dict) -> tuple[Optional[PortDot], Optional[PortDot]]:
        src_inst = _normalize_instance_name(row.get("src_inst", ""))
        dst_inst = _normalize_instance_name(row.get("dst_inst", ""))
        src_port = _strip(row.get("src_port", ""))
        dst_port = _strip(row.get("dst_port", ""))

        if not src_port or not dst_port:
            return None, None

        if src_inst == SELF_INSTANCE and dst_inst != SELF_INSTANCE:
            src = self._find_port(SELF_INSTANCE, "boundary", "rpc", "serv", src_port)
            dst = self._find_port(dst_inst, "module_inst", "rpc", "serv", dst_port)
            return src, dst

        if dst_inst == SELF_INSTANCE and src_inst != SELF_INSTANCE:
            src = self._find_port(src_inst, "module_inst", "rpc", "req", src_port)
            dst = self._find_port(SELF_INSTANCE, "boundary", "rpc", "req", dst_port)
            return src, dst

        if src_inst != SELF_INSTANCE and dst_inst != SELF_INSTANCE:
            src = self._find_port(src_inst, "module_inst", "rpc", "req", src_port)
            dst = self._find_port(dst_inst, "module_inst", "rpc", "serv", dst_port)
            return src, dst

        return None, None

    def _instpipe_ports_for_record(self, row: dict) -> tuple[Optional[PortDot], Optional[PortDot]]:
        src_inst = _normalize_instance_name(row.get("src_inst", ""))
        dst_inst = _normalize_instance_name(row.get("dst_inst", ""))
        src_port = _strip(row.get("src_port", ""))
        dst_port = _strip(row.get("dst_port", ""))

        if not src_port:
            return None, None

        if src_inst == SELF_INSTANCE:
            src_owner_kind = "boundary"
        else:
            src_owner_kind = "module_inst"

        src_candidates = [
            self._find_port(src_inst, src_owner_kind, "pipe", "in", src_port),
            self._find_port(src_inst, src_owner_kind, "pipe", "out", src_port),
        ]
        src = next((port for port in src_candidates if port is not None), None)
        if src is None:
            return None, None

        if dst_inst == SELF_INSTANCE:
            if src.direction not in ("in", "out") or not dst_port:
                return None, None
            dst = self._find_port(SELF_INSTANCE, "boundary", "pipe", src.direction, dst_port)
            return src, dst

        if not dst_port:
            if src.direction == "out":
                dst = self._find_port(dst_inst, "pipe_inst", "pipe", "in", "IN")
            elif src.direction == "in":
                dst = self._find_port(dst_inst, "pipe_inst", "pipe", "out", "OUT")
            else:
                dst = None
            return src, dst

        return None, None

    def _block_anchors_for_record(self, row: dict) -> tuple[Optional[LinkAnchorItem], Optional[LinkAnchorItem]]:
        src = self._anchor_for_object(row.get("src_inst", ""))
        dst = self._anchor_for_object(row.get("dst_inst", ""))
        return src, dst

    def _order_anchors_for_record(self, row: dict) -> tuple[Optional[LinkAnchorItem], Optional[LinkAnchorItem]]:
        src_name = _strip(row.get("src_inst", ""))
        dst_name = _strip(row.get("dst_inst", ""))
        if not src_name or not dst_name:
            return None, None
        src = self._anchor_for_object(src_name)
        dst = self._anchor_for_object(dst_name)
        return src, dst

    def _make_edge_meta(self, group: str, row: dict) -> dict:
        tooltip = self._connection_tooltip(group, row)
        if group == "reqsvc_conns":
            accent = RPC_ACCENT
            line_style = "manhattan"
            line_width = 2.0
        elif group == "instpipe_conns":
            accent = PIPE_ACCENT
            line_style = "manhattan"
            line_width = 2.0
        elif group == "block_conns":
            accent = QColor("#6b7280")
            accent.setAlpha(180)
            line_style = "straight"
            line_width = 1.6
        else:
            accent = QColor(CLOCK_ACCENT)
            accent.setAlpha(170)
            line_style = "straight"
            line_width = 1.6
        return {
            "group": group,
            "key": self._connection_key(group, row),
            "record": dict(row),
            "accent": accent,
            "line_style": line_style,
            "line_width": line_width,
            "tooltip": tooltip,
        }

    def _connection_tooltip(self, group: str, row: dict) -> str:
        if group == "reqsvc_conns":
            return (
                f"请求/服务连接\n"
                f"{self._display_inst_name(row.get('src_inst', ''))}.{_strip(row.get('src_port', ''))}"
                f" -> "
                f"{self._display_inst_name(row.get('dst_inst', ''))}.{_strip(row.get('dst_port', ''))}"
            )
        if group == "instpipe_conns":
            dst_port = _strip(row.get("dst_port", ""))
            if dst_port:
                dst_desc = f"{self._display_inst_name(row.get('dst_inst', ''))}.{dst_port}"
            else:
                dst_desc = self._display_inst_name(row.get("dst_inst", ""))
            return (
                f"实例/管道连接\n"
                f"{self._display_inst_name(row.get('src_inst', ''))}.{_strip(row.get('src_port', ''))}"
                f" -> {dst_desc}"
            )
        if group == "block_conns":
            return (
                f"阻塞传递连接\n"
                f"{self._display_inst_name(row.get('src_inst', ''))}"
                f" -> "
                f"{self._display_inst_name(row.get('dst_inst', ''))}"
            )
        if group == "orders":
            return (
                f"更新次序连接\n"
                f"{self._display_inst_name(row.get('src_inst', ''))}"
                f" -> "
                f"{_strip(row.get('dst_inst', ''))}"
            )
        return ""

    def _render_connections(self):
        scene = self.canvas.scene
        for item in list(scene.items()):
            if isinstance(item, EdgeItem):
                item.delete_self()

        for row in _safe_list(self.data.get("reqsvc_conns", [])):
            src, dst = self._reqsvc_ports_for_record(row)
            if src is None or dst is None:
                continue
            edge = EdgeItem(src, dst, accent=RPC_ACCENT, on_delete=self._delete_connection_edge, on_edit=self._edit_connection_edge)
            edge.apply_meta(self._make_edge_meta("reqsvc_conns", row))
            scene.addItem(edge)

        for row in _safe_list(self.data.get("instpipe_conns", [])):
            src, dst = self._instpipe_ports_for_record(row)
            if src is None or dst is None:
                continue
            edge = EdgeItem(src, dst, accent=PIPE_ACCENT, on_delete=self._delete_connection_edge, on_edit=self._edit_connection_edge)
            edge.apply_meta(self._make_edge_meta("instpipe_conns", row))
            scene.addItem(edge)

        for row in _safe_list(self.data.get("block_conns", [])):
            src, dst = self._block_anchors_for_record(row)
            if src is None or dst is None:
                continue
            edge = EdgeItem(src, dst, accent=QColor("#6b7280"), on_delete=self._delete_connection_edge, on_edit=self._edit_connection_edge)
            edge.apply_meta(self._make_edge_meta("block_conns", row))
            scene.addItem(edge)

        for row in _safe_list(self.data.get("orders", [])):
            src, dst = self._order_anchors_for_record(row)
            if src is None or dst is None:
                continue
            edge = EdgeItem(src, dst, accent=CLOCK_ACCENT, on_delete=self._delete_connection_edge, on_edit=self._edit_connection_edge)
            edge.apply_meta(self._make_edge_meta("orders", row))
            scene.addItem(edge)

    def _resolve_reqsvc_connection(self, port_a: PortDot, port_b: PortDot) -> Optional[dict]:
        if "pipe_inst" in (port_a.owner_kind, port_b.owner_kind):
            QMessageBox.information(self, "无法连接", "请求/服务连接不能直接连到管道实例。")
            return None

        if port_a.owner_kind == "boundary" and port_b.owner_kind == "boundary":
            QMessageBox.information(self, "无法连接", "本模块边界端口之间不能直接建立请求/服务连接。")
            return None

        if port_a.owner_kind == "module_inst" and port_b.owner_kind == "module_inst":
            req_port = port_a if port_a.direction == "req" else port_b if port_b.direction == "req" else None
            svc_port = port_a if port_a.direction == "serv" else port_b if port_b.direction == "serv" else None
            if req_port is None or svc_port is None:
                QMessageBox.information(self, "无法连接", "子模块之间的请求/服务连接要求：请求端口 -> 服务端口。")
                return None
            return {
                "src_inst": req_port.owner_name,
                "src_port": req_port.port_name,
                "dst_inst": svc_port.owner_name,
                "dst_port": svc_port.port_name,
            }

        boundary = port_a if port_a.owner_kind == "boundary" else port_b if port_b.owner_kind == "boundary" else None
        module_port = port_b if boundary is port_a else port_a if boundary is not None else None
        if boundary is None or module_port is None or module_port.owner_kind != "module_inst":
            QMessageBox.information(self, "无法连接", "当前请求/服务连接只支持：子模块 <-> 子模块 或 子模块 <-> 本模块。")
            return None

        if boundary.direction == "req" and module_port.direction == "req":
            return {
                "src_inst": module_port.owner_name,
                "src_port": module_port.port_name,
                "dst_inst": SELF_INSTANCE,
                "dst_port": boundary.port_name,
            }

        if boundary.direction == "serv" and module_port.direction == "serv":
            return {
                "src_inst": SELF_INSTANCE,
                "src_port": boundary.port_name,
                "dst_inst": module_port.owner_name,
                "dst_port": module_port.port_name,
            }

        QMessageBox.information(self, "无法连接", "本模块与子模块之间的请求/服务连接要求同类端口相连：req -> req 或 service -> service。")
        return None

    def _resolve_instpipe_connection(self, port_a: PortDot, port_b: PortDot) -> Optional[dict]:
        if port_a.owner_kind == "pipe_inst" and port_b.owner_kind == "pipe_inst":
            QMessageBox.information(self, "无法连接", "两个管道实例之间不能直接建立实例/管道连接。")
            return None

        if port_a.owner_kind == "boundary" and port_b.owner_kind == "boundary":
            QMessageBox.information(self, "无法连接", "本模块边界端口之间不能直接建立实例/管道连接。")
            return None

        if "pipe_inst" in (port_a.owner_kind, port_b.owner_kind):
            pipe_port = port_a if port_a.owner_kind == "pipe_inst" else port_b
            module_port = port_b if pipe_port is port_a else port_a
            if module_port.owner_kind != "module_inst":
                QMessageBox.information(self, "无法连接", "当前版本仅支持“子模块管道端口 -> 管道实例”的实例/管道连接。")
                return None

            if module_port.direction == "out" and pipe_port.direction == "in":
                return {
                    "src_inst": module_port.owner_name,
                    "src_port": module_port.port_name,
                    "dst_inst": pipe_port.owner_name,
                    "dst_port": "",
                }
            if module_port.direction == "in" and pipe_port.direction == "out":
                return {
                    "src_inst": module_port.owner_name,
                    "src_port": module_port.port_name,
                    "dst_inst": pipe_port.owner_name,
                    "dst_port": "",
                }

            QMessageBox.information(self, "无法连接", "子模块管道输出只能连到管道实例 IN；子模块管道输入只能连到管道实例 OUT。")
            return None

        boundary = port_a if port_a.owner_kind == "boundary" else port_b if port_b.owner_kind == "boundary" else None
        module_port = port_b if boundary is port_a else port_a if boundary is not None else None
        if boundary is None or module_port is None or module_port.owner_kind != "module_inst":
            QMessageBox.information(self, "无法连接", "当前实例/管道连接只支持：子模块 <-> 本模块，或 子模块 <-> 管道实例。")
            return None

        if boundary.direction != module_port.direction:
            QMessageBox.information(self, "无法连接", "子模块端口映射到本模块边界时，方向必须保持一致（in -> in / out -> out）。")
            return None

        return {
            "src_inst": module_port.owner_name,
            "src_port": module_port.port_name,
            "dst_inst": SELF_INSTANCE,
            "dst_port": boundary.port_name,
        }

    def _resolve_connection_from_ports(self, start_port: PortDot, end_port: PortDot) -> Optional[dict]:
        if start_port is end_port:
            QMessageBox.information(self, "无法连接", "同一个端口不能连接到自身。")
            return None

        if start_port.port_kind != end_port.port_kind:
            QMessageBox.information(self, "无法连接", "只能连接相同类别的端口。")
            return None

        if start_port.port_kind == "rpc":
            group = "reqsvc_conns"
            row = self._resolve_reqsvc_connection(start_port, end_port)
        else:
            group = "instpipe_conns"
            row = self._resolve_instpipe_connection(start_port, end_port)

        if row is None:
            return None

        if not self._append_connection(group, row):
            QMessageBox.information(self, "重复连接", "该连接已经存在，无需重复创建。")
            return None

        self._notify_updated()
        return self._make_edge_meta(group, row)

    def _delete_connection_edge(self, edge: EdgeItem):
        group = _strip(edge.conn_group)
        key = _strip(edge.conn_key)
        if not group or not key:
            edge.delete_self()
            return

        if self._remove_connection_by_key(group, key):
            self._notify_updated()
        edge.delete_self()

    def _dialog_page_for_connection_group(self, dlg: ConnectionsDialog, group: str) -> Optional[dict]:
        return {
            "reqsvc_conns": dlg.reqsvc_page,
            "instpipe_conns": dlg.instpipe_page,
            "block_conns": dlg.block_page,
            "orders": dlg.order_page,
        }.get(group)

    def _focus_connection_in_dialog(self, dlg: ConnectionsDialog, group: str, key: str):
        page = self._dialog_page_for_connection_group(dlg, group)
        if page is None:
            return

        idx = dlg.tabs.indexOf(page["widget"])
        if idx >= 0:
            dlg.tabs.setCurrentIndex(idx)

        table = page["table"]
        rows = []
        if group == "reqsvc_conns":
            rows = _safe_list(self.data.get("reqsvc_conns", []))
        elif group == "instpipe_conns":
            rows = _safe_list(self.data.get("instpipe_conns", []))
        elif group == "block_conns":
            rows = _safe_list(self.data.get("block_conns", []))
        elif group == "orders":
            rows = _safe_list(self.data.get("orders", []))

        for row_idx, row in enumerate(rows):
            if self._connection_key(group, row) == key:
                table.setCurrentCell(row_idx, 0)
                table.selectRow(row_idx)
                break

    def _edit_connection_edge(self, edge: EdgeItem):
        group = _strip(edge.conn_group)
        key = _strip(edge.conn_key)
        if not group or not key:
            self._edit_connections()
            return
        self._edit_connections(focus_group=group, focus_key=key)

    def _connection_object_name_from_target(self, target) -> str:
        if target is self.canvas.boundary:
            return SELF_INSTANCE
        if isinstance(target, BaseNodeItem):
            payload = target.payload or {}
            kind = payload.get("_kind", "")
            if kind == "module_inst":
                return _strip(payload.get("inst", ""))
            if kind == "clock_block":
                return _strip(payload.get("name", ""))
        return ""

    def _retarget_connection_edge(self, edge: EdgeItem, side: str, target) -> bool:
        group = _strip(edge.conn_group)
        key = _strip(edge.conn_key)
        side = _strip(side)
        if not group or not key or side not in ("src", "dst"):
            return False

        if group in ("reqsvc_conns", "instpipe_conns"):
            if not isinstance(target, PortDot):
                return False
            fixed_port = edge.in_port if side == "src" else edge.out_port
            if not isinstance(fixed_port, PortDot):
                return False
            if group == "reqsvc_conns":
                new_row = self._resolve_reqsvc_connection(fixed_port, target)
            else:
                new_row = self._resolve_instpipe_connection(fixed_port, target)
            if new_row is None:
                return False
            return self._replace_connection_row(group, key, new_row)

        if group in ("block_conns", "orders"):
            target_name = self._connection_object_name_from_target(target)
            if not target_name:
                return False
            new_row = dict(edge.conn_record or {})
            if side == "src":
                new_row["src_inst"] = target_name
            else:
                new_row["dst_inst"] = target_name
            return self._replace_connection_row(group, key, new_row)

        return False

    def _validate_reqsvc_rows(self, rows: list[dict]) -> Optional[list[dict]]:
        validated: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            item = {
                "src_inst": _normalize_instance_name(row.get("src_inst", "")),
                "src_port": _strip(row.get("src_port", "")),
                "dst_inst": _normalize_instance_name(row.get("dst_inst", "")),
                "dst_port": _strip(row.get("dst_port", "")),
            }
            if not all(item.values()):
                QMessageBox.warning(self, "输入无效", "请求/服务连接的四个字段都不能为空。")
                return None
            src, dst = self._reqsvc_ports_for_record(item)
            if src is None or dst is None:
                QMessageBox.warning(
                    self,
                    "连接无效",
                    f"无法解析请求/服务连接：\n{self._display_inst_name(item['src_inst'])}.{item['src_port']} -> "
                    f"{self._display_inst_name(item['dst_inst'])}.{item['dst_port']}",
                )
                return None
            key = self._connection_key("reqsvc_conns", item)
            if key in seen:
                continue
            seen.add(key)
            validated.append(item)
        return validated

    def _validate_instpipe_rows(self, rows: list[dict]) -> Optional[list[dict]]:
        validated: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            item = {
                "src_inst": _normalize_instance_name(row.get("src_inst", "")),
                "src_port": _strip(row.get("src_port", "")),
                "dst_inst": _normalize_instance_name(row.get("dst_inst", "")),
                "dst_port": _strip(row.get("dst_port", "")),
            }
            if not item["src_inst"] or not item["src_port"] or not item["dst_inst"]:
                QMessageBox.warning(self, "输入无效", "实例/管道连接至少需要填写源实例名、源端口名、目标实例名。")
                return None
            src, dst = self._instpipe_ports_for_record(item)
            if src is None or dst is None:
                dst_desc = self._display_inst_name(item["dst_inst"])
                if item["dst_port"]:
                    dst_desc += f".{item['dst_port']}"
                QMessageBox.warning(
                    self,
                    "连接无效",
                    f"无法解析实例/管道连接：\n{self._display_inst_name(item['src_inst'])}.{item['src_port']} -> {dst_desc}",
                )
                return None
            key = self._connection_key("instpipe_conns", item)
            if key in seen:
                continue
            seen.add(key)
            validated.append(item)
        return validated

    def _validate_block_rows(self, rows: list[dict]) -> Optional[list[dict]]:
        validated: list[dict] = []
        seen: set[str] = set()
        allowed = {SELF_INSTANCE}
        allowed.update(_strip(row.get("inst", "")) for row in _safe_list(self.data.get("submodules", [])) if _strip(row.get("inst", "")))
        for row in rows:
            item = {
                "src_inst": _normalize_instance_name(row.get("src_inst", "")),
                "dst_inst": _normalize_instance_name(row.get("dst_inst", "")),
            }
            if not item["src_inst"] or not item["dst_inst"]:
                QMessageBox.warning(self, "输入无效", "阻塞传递连接的源对象名和目标对象名不能为空。")
                return None
            if item["src_inst"] not in allowed or item["dst_inst"] not in allowed:
                QMessageBox.warning(self, "输入无效", "阻塞传递连接仅允许使用“本模块”或现有子模块实例名。")
                return None
            key = self._connection_key("name_pair", item)
            if key in seen:
                continue
            seen.add(key)
            validated.append(item)
        return validated

    def _validate_order_rows(self, rows: list[dict]) -> Optional[list[dict]]:
        validated: list[dict] = []
        seen: set[str] = set()
        allowed_sources = {_strip(row.get("inst", "")) for row in _safe_list(self.data.get("submodules", [])) if _strip(row.get("inst", ""))}
        allowed_targets = {_strip(row.get("name", "")) for row in _safe_list(self.data.get("clock_blocks", [])) if _strip(row.get("name", ""))}
        for row in rows:
            item = {
                "src_inst": _strip(row.get("src_inst", "")),
                "dst_inst": _strip(row.get("dst_inst", "")),
            }
            if not item["src_inst"] or not item["dst_inst"]:
                QMessageBox.warning(self, "输入无效", "更新次序连接的源对象名和目标对象名不能为空。")
                return None
            if item["src_inst"] not in allowed_sources:
                QMessageBox.warning(self, "输入无效", "更新次序连接的源对象必须是现有子模块实例名。")
                return None
            if item["dst_inst"] not in allowed_targets:
                QMessageBox.warning(self, "输入无效", "更新次序连接的目标对象必须是现有时钟代码块名。")
                return None
            key = self._connection_key("name_pair", item)
            if key in seen:
                continue
            seen.add(key)
            validated.append(item)
        return validated

    # --------------------------
    # Canvas refresh & render
    # --------------------------
    def _refresh_parent_ports(self):
        self.canvas.set_parent_ports(
            pipe_ports=_safe_list(self.data.get("pipe_ports", [])),
            rpcs=_safe_list(self.data.get("rpcs", [])),
            pos_store=self.data.get("parent_port_pos", {}),
        )

    def refresh_canvas(self, updated_module_name: str | None = None):
        if updated_module_name is None or updated_module_name == self.module_name:
            latest = self.module_resolver(self.module_name)
            if isinstance(latest, dict):
                synced = dict(latest)
                synced["name"] = self.module_name
                if "parent_port_pos" not in synced or not isinstance(synced.get("parent_port_pos"), dict):
                    synced["parent_port_pos"] = {}
                for key in (
                    "reqsvc_conns", "instpipe_conns", "block_conns", "orders",
                    "clock_blocks", "service_blocks", "subreq_blocks",
                ):
                    if key not in synced or not isinstance(synced.get(key), list):
                        synced[key] = []
                self.data = synced
            self._refresh_sidebar_local_views()
            self._refresh_parent_ports()
            self._render_clock_blocks()

        for inst, node in list(self._inst_nodes.items()):
            payload = node.payload or {}
            if payload.get("_kind") != "module_inst":
                continue
            mod = _strip(payload.get("module", ""))
            if not mod:
                continue
            if updated_module_name is not None and mod != updated_module_name:
                continue

            defn = self.module_resolver(mod)
            if not isinstance(defn, dict):
                continue

            # 注意：这里是“端口定义变化”刷新，会重建端口并清掉连接
            node.set_ports(
                pipe_ports=_safe_list(defn.get("pipe_ports", [])),
                rpcs=_safe_list(defn.get("rpcs", [])),
            )
            node.update()

        self.canvas.scene.update()
        self.canvas.view.viewport().update()
        self._render_connections()

    def _clock_block_tooltip(self, row: dict) -> str:
        name = _strip(row.get("name", "")) or "未命名时钟代码块"
        comment = _strip(row.get("comment", "")) or "（无注释）"
        code = _strip(row.get("code", ""))
        code_lines = len(code.splitlines()) if code else 0
        return (
            f"时钟代码块：{name}\n"
            f"注释：{comment}\n"
            f"代码行数：{code_lines}"
        )

    def _render_clock_blocks(self):
        sc = self.canvas.scene
        for node in list(self._clock_nodes.values()):
            try:
                node.clear_anchor_edges()
                node.clear_ports()
            except Exception:
                pass
            if node.scene() is sc:
                sc.removeItem(node)
        self._clock_nodes.clear()

        clocks = _safe_list(self.data.get("clock_blocks", []))
        x0, y0 = 650, -720
        dx, dy = 280, 150
        col, row = 0, 0
        for block in clocks:
            name = _strip(block.get("name", ""))
            if not name:
                continue

            node = self.canvas.add_clock_block_node(name, QPointF(x0 + col * dx, y0 + row * dy))
            node.set_payload({"_kind": "clock_block", **block})
            node.setToolTip(self._clock_block_tooltip(block))

            w = block.get("w")
            h = block.get("h")
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                node.prepareGeometryChange()
                node.w = int(w)
                node.h = int(h)
                node._update_center_anchor()

            self._clock_nodes[name] = node

            col += 1
            if col >= 2:
                col = 0
                row += 1

    def _render_all_instances(self):
        sc = self.canvas.scene
        old_inst_nodes = list(self._inst_nodes.values())
        old_pipe_nodes = list(self._pipe_nodes.values())
        old_clock_nodes = list(self._clock_nodes.values())

        for node in old_inst_nodes + old_pipe_nodes + old_clock_nodes:
            try:
                node.clear_anchor_edges()
                node.clear_ports()
            except Exception:
                pass
            if node.scene() is sc:
                sc.removeItem(node)

        self._inst_nodes.clear()
        self._pipe_nodes.clear()
        self._clock_nodes.clear()

        for it in list(sc.items()):
            if it is self.canvas.boundary or it.parentItem() is not None:
                continue
            if isinstance(it, EdgeItem):
                it.delete_self()
                continue
            if it.scene() is sc:
                sc.removeItem(it)

        self._refresh_parent_ports()

        # --- submodules (module instances)
        subs = _safe_list(self.data.get("submodules", []))
        x0, y0 = -1200, -700
        dx, dy = 340, 240
        col, row = 0, 0
        for sm in subs:
            inst = _strip(sm.get("inst"))
            mod = _strip(sm.get("module"))
            if not inst:
                continue

            node = self.canvas.add_module_inst_node(f"{inst}\n[{mod}]", QPointF(x0 + col * dx, y0 + row * dy))
            node.set_payload({"_kind": "module_inst", **sm})

            defn = self.module_resolver(mod) if mod else None
            pipe_ports = _safe_list(defn.get("pipe_ports", [])) if isinstance(defn, dict) else []
            rpcs = _safe_list(defn.get("rpcs", [])) if isinstance(defn, dict) else []

            # 尺寸持久化（强烈建议）
            w = sm.get("w")
            h = sm.get("h")
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                node.prepareGeometryChange()
                node.w = int(w)
                node.h = int(h)

            node.set_ports(pipe_ports=pipe_ports, rpcs=rpcs)
            self._inst_nodes[inst] = node

            col += 1
            if col >= 3:
                col = 0
                row += 1

        # --- pipes (pipe instances)
        pipes = _safe_list(self.data.get("pipes", []))
        x1, y1 = -1100, 350
        dx2, dy2 = 300, 180
        col, row = 0, 0
        for p in pipes:
            inst = _strip(p.get("inst"))
            dtype = _strip(p.get("dtype"))
            if not inst:
                continue

            node = self.canvas.add_pipe_inst_node(f"{inst}\n<{dtype}>", QPointF(x1 + col * dx2, y1 + row * dy2))
            node.set_payload({"_kind": "pipe_inst", **p})

            # 管道节点的端口定义
            pipe_ports = [
                {"dir": "in", "name": "IN", "comment": "", "dtype": dtype},
                {"dir": "out", "name": "OUT", "comment": "", "dtype": dtype},
            ]

            # 尺寸持久化（强烈建议）
            w = p.get("w")
            h = p.get("h")
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                node.prepareGeometryChange()
                node.w = int(w)
                node.h = int(h)

            node.set_ports(pipe_ports=pipe_ports, rpcs=[])
            self._pipe_nodes[inst] = node
            col += 1
            if col >= 4:
                col = 0
                row += 1

        self._render_clock_blocks()
        self._render_connections()

    # --------------------------
    # Create instances
    # --------------------------
    def _create_module_inst_at(self, scene_pos: QPointF):
        dlg = ModuleInstanceDialog("创建模块实例", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sm = dlg.get_data()
        inst = _strip(sm.get("inst"))
        mod = _strip(sm.get("module"))
        if not inst:
            QMessageBox.warning(self, "输入无效", "实例名不能为空。")
            return
        if not mod:
            QMessageBox.warning(self, "输入无效", "所属模块不能为空（需要用于生成实例端口）。")
            return

        defn = self.module_resolver(mod)
        if defn is None:
            QMessageBox.warning(self, "模块不存在", f"未找到模块定义“{mod}”。请先在全局模块库中创建它。")
            return

        subs = _safe_list(self.data.get("submodules", []))
        if any(_strip(x.get("inst")) == inst for x in subs):
            QMessageBox.warning(self, "重复实例", f"实例名“{inst}”已存在。")
            return

        # 先创建 node（拿到默认尺寸写回数据）
        node = self.canvas.add_module_inst_node(f"{inst}\n[{mod}]", scene_pos)

        # 尺寸持久化（强烈建议）
        sm["w"] = int(node.w)
        sm["h"] = int(node.h)

        subs.append(sm)
        self.data["submodules"] = subs

        node.set_payload({"_kind": "module_inst", **sm})
        node.set_ports(pipe_ports=_safe_list(defn.get("pipe_ports", [])), rpcs=_safe_list(defn.get("rpcs", [])))

        self._inst_nodes[inst] = node
        self._notify_updated()

    def _create_pipe_inst_at(self, scene_pos: QPointF):
        dlg = PipeInstanceDialog("创建管道实例", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = dlg.get_data()
        inst = _strip(p.get("inst"))
        dtype = _strip(p.get("dtype"))
        if not inst:
            QMessageBox.warning(self, "输入无效", "管道实例名不能为空。")
            return
        if not dtype:
            QMessageBox.warning(self, "输入无效", "数据类型(线束名)不能为空。")
            return

        pipes = _safe_list(self.data.get("pipes", []))
        if any(_strip(x.get("inst")) == inst for x in pipes):
            QMessageBox.warning(self, "重复实例", f"管道实例名“{inst}”已存在。")
            return

        node = self.canvas.add_pipe_inst_node(f"{inst}\n<{dtype}>", scene_pos)

        # 尺寸持久化（强烈建议）
        p["w"] = int(node.w)
        p["h"] = int(node.h)

        pipes.append(p)
        self.data["pipes"] = pipes

        node.set_payload({"_kind": "pipe_inst", **p})
        pipe_ports = [
            {"dir": "in", "name": "IN", "comment": "", "dtype": dtype},
            {"dir": "out", "name": "OUT", "comment": "", "dtype": dtype},
        ]
        node.set_ports(pipe_ports=pipe_ports, rpcs=[])
        self._pipe_nodes[inst] = node

        self._notify_updated()

    def _create_clock_block_at(self, scene_pos: QPointF):
        dlg = ClockBlockDialog("创建时钟代码块", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        block = dlg.get_data()
        name = _strip(block.get("name", ""))
        if not name:
            QMessageBox.warning(self, "输入无效", "时钟代码块名不能为空。")
            return

        clocks = _safe_list(self.data.get("clock_blocks", []))
        if any(_strip(x.get("name")) == name for x in clocks):
            QMessageBox.warning(self, "重复名称", f"时钟代码块“{name}”已存在。")
            return

        node = self.canvas.add_clock_block_node(name, scene_pos)
        block["code"] = ""
        block["w"] = int(node.w)
        block["h"] = int(node.h)

        clocks.append(block)
        self.data["clock_blocks"] = clocks

        node.set_payload({"_kind": "clock_block", **block})
        node.setToolTip(self._clock_block_tooltip(block))
        self._clock_nodes[name] = node
        self._notify_updated()

    # --------------------------
    # Edit nodes
    # --------------------------
    def _edit_node(self, node: BaseNodeItem):
        payload = node.payload or {}
        kind = payload.get("_kind")

        if kind == "module_inst":
            dlg = ModuleInstanceDialog("编辑模块实例", data=payload, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_sm = dlg.get_data()
            inst_old = _strip(payload.get("inst"))
            inst_new = _strip(new_sm.get("inst"))
            mod_new = _strip(new_sm.get("module"))

            if not inst_new or not mod_new:
                QMessageBox.warning(self, "输入无效", "实例名/所属模块不能为空。")
                return

            defn = self.module_resolver(mod_new)
            if defn is None:
                QMessageBox.warning(self, "模块不存在", f"未找到模块定义“{mod_new}”。")
                return

            subs = _safe_list(self.data.get("submodules", []))
            for sm in subs:
                if _strip(sm.get("inst")) == inst_old:
                    # 保留尺寸字段（强烈建议）
                    w = sm.get("w")
                    h = sm.get("h")
                    sm.update(new_sm)
                    if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                        sm["w"] = int(w)
                        sm["h"] = int(h)
                    else:
                        sm["w"] = int(node.w)
                        sm["h"] = int(node.h)
                    break
            self.data["submodules"] = subs

            node.title = f"{inst_new}\n[{mod_new}]"
            # 保持尺寸字段在 payload 内（可选）
            new_sm["w"] = int(node.w)
            new_sm["h"] = int(node.h)

            node.set_payload({"_kind": "module_inst", **new_sm})

            # 端口刷新会重建并清掉连接（符合你目前的数据模型）
            node.set_ports(pipe_ports=_safe_list(defn.get("pipe_ports", [])), rpcs=_safe_list(defn.get("rpcs", [])))
            node.update()

            # 修复：实例名变更时，更新索引
            if inst_old and inst_new and inst_old != inst_new:
                self._replace_instance_name_in_connections(inst_old, inst_new)
                self._replace_subreq_inst_name(inst_old, inst_new)
            self._prune_subreq_code_rows_for_instance(inst_new, mod_new)
            if inst_old and inst_old in self._inst_nodes:
                self._inst_nodes.pop(inst_old, None)
            self._inst_nodes[inst_new] = node

            self._render_connections()
            self._notify_updated()
            return

        if kind == "pipe_inst":
            dlg = PipeInstanceDialog("编辑管道实例", data=payload, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_p = dlg.get_data()
            inst_old = _strip(payload.get("inst"))
            inst_new = _strip(new_p.get("inst"))
            dtype = _strip(new_p.get("dtype"))

            if not inst_new or not dtype:
                QMessageBox.warning(self, "输入无效", "实例名/数据类型不能为空。")
                return

            pipes = _safe_list(self.data.get("pipes", []))
            for pp in pipes:
                if _strip(pp.get("inst")) == inst_old:
                    w = pp.get("w")
                    h = pp.get("h")
                    pp.update(new_p)
                    if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                        pp["w"] = int(w)
                        pp["h"] = int(h)
                    else:
                        pp["w"] = int(node.w)
                        pp["h"] = int(node.h)
                    break
            self.data["pipes"] = pipes

            node.title = f"{inst_new}\n<{dtype}>"

            # 保持尺寸字段在 payload 内（可选）
            new_p["w"] = int(node.w)
            new_p["h"] = int(node.h)

            node.set_payload({"_kind": "pipe_inst", **new_p})

            pipe_ports = [
                {"dir": "in", "name": "IN", "comment": "", "dtype": dtype},
                {"dir": "out", "name": "OUT", "comment": "", "dtype": dtype},
            ]
            # 这里重建端口（会清掉连接）
            node.set_ports(pipe_ports=pipe_ports, rpcs=[])
            node.update()

            if inst_old and inst_new and inst_old != inst_new:
                self._replace_instance_name_in_connections(inst_old, inst_new)
            if inst_old and inst_old in self._pipe_nodes:
                self._pipe_nodes.pop(inst_old, None)
            self._pipe_nodes[inst_new] = node

            self._render_connections()
            self._notify_updated()
            return

        if kind == "clock_block":
            dlg = ClockBlockDialog("编辑时钟代码块", data=payload, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            old_name = _strip(payload.get("name", ""))
            new_data = dlg.get_data()
            new_name = _strip(new_data.get("name", ""))
            if not new_name:
                QMessageBox.warning(self, "输入无效", "时钟代码块名不能为空。")
                return

            clocks = _safe_list(self.data.get("clock_blocks", []))
            if old_name != new_name and any(_strip(x.get("name")) == new_name for x in clocks):
                QMessageBox.warning(self, "重复名称", f"时钟代码块“{new_name}”已存在。")
                return

            for block in clocks:
                if _strip(block.get("name")) == old_name:
                    code = block.get("code", "")
                    w = block.get("w")
                    h = block.get("h")
                    block.update(new_data)
                    block["code"] = code
                    if isinstance(w, (int, float)):
                        block["w"] = int(w)
                    if isinstance(h, (int, float)):
                        block["h"] = int(h)
                    new_data["code"] = code
                    if isinstance(w, (int, float)):
                        new_data["w"] = int(w)
                    if isinstance(h, (int, float)):
                        new_data["h"] = int(h)
                    break
            self.data["clock_blocks"] = clocks

            if old_name and new_name and old_name != new_name:
                for row in _safe_list(self.data.get("orders", [])):
                    if _strip(row.get("dst_inst", "")) == old_name:
                        row["dst_inst"] = new_name

            node.title = new_name
            node.set_payload({"_kind": "clock_block", **new_data})
            node.setToolTip(self._clock_block_tooltip(new_data))
            node.update()

            if old_name and old_name in self._clock_nodes:
                self._clock_nodes.pop(old_name, None)
            self._clock_nodes[new_name] = node

            self._render_connections()
            self._notify_updated()
            return

    # --------------------------
    # Enter submodule
    # --------------------------
    def _enter_submodule(self, inst: str, module_name: str):
        module_name = _strip(module_name)
        if not module_name:
            QMessageBox.warning(self, "无法进入子模块", "所属模块名为空。")
            return

        defn = self.module_resolver(module_name)
        if defn is None:
            QMessageBox.warning(self, "模块不存在", f"未找到模块定义“{module_name}”，无法进入其画布。")
            return

        self.requestOpenModuleCanvas.emit(module_name)

    # --------------------------
    # Sidebar edit dialogs
    # --------------------------
    def _edit_local_cfg(self):
        dlg = LocalCfgDialog(parent=self)
        dlg.load(_safe_list(self.data.get("local_cfgs", [])))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.data["local_cfgs"] = dlg.dump()
        self._refresh_sidebar_local_views()
        self._notify_updated()

    def _edit_local_harness(self):
        dlg = LocalHarnessDialog(parent=self)
        dlg.load(_safe_list(self.data.get("local_harnesses", [])))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.data["local_harnesses"] = dlg.dump()
        self._refresh_sidebar_local_views()
        self._notify_updated()

    def _edit_pipe_ports(self):
        dlg = PortsDialog(parent=self)

        merged = []
        for p in _safe_list(self.data.get("pipe_ports", [])):
            merged.append(p)

        for r in _safe_list(self.data.get("rpcs", [])):
            merged.append({
                "dir": "req" if _strip(r.get("kind")) == "req" else "serv",
                "name": _strip(r.get("name", "")),
                "comment": _strip(r.get("comment", "")),
                "dtype": "",
            })

        dlg.load(merged)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        rows = dlg.dump()

        pipe_ports = []
        rpcs = []

        for row in rows:
            d = _strip(row.get("dir"))
            name = _strip(row.get("name"))
            if not name:
                continue

            if d in ("in", "out"):
                pipe_ports.append(row)
            elif d in ("req", "serv"):
                rpcs.append({
                    "kind": "req" if d == "req" else "service",
                    "name": name,
                    "comment": row.get("comment", ""),
                    "params": "",
                    "returns": "",
                    "handshake": "",
                })
            else:
                QMessageBox.warning(self, "方向无效", f"端口 {name} 的方向必须是 in/out/req/serv")
                return

        self.data["pipe_ports"] = pipe_ports
        self.data["rpcs"] = rpcs
        self._prune_service_code_rows()
        self._notify_updated()
        self.refresh_canvas(updated_module_name=self.module_name)

    def _edit_submodules_list(self):
        dlg = _TableDialog(
            "编辑：子模块列表（模块实例）",
            ["实例名", "所属模块", "注释", "本地配置覆盖列表(JSON)"],
            ["inst", "module", "comment", "cfg_overrides"],
            parent=self
        )
        dlg.load(_safe_list(self.data.get("submodules", [])))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # 保留 w/h（强烈建议）：用户在表格里没字段可编辑，但我们别丢
        old = { _strip(x.get("inst")): x for x in _safe_list(self.data.get("submodules", [])) }
        new_list = dlg.dump()
        for sm in new_list:
            inst = _strip(sm.get("inst"))
            if inst in old:
                if "w" in old[inst]:
                    sm["w"] = old[inst].get("w")
                if "h" in old[inst]:
                    sm["h"] = old[inst].get("h")

        self.data["submodules"] = new_list
        self._render_all_instances()
        self._notify_updated()

    def _edit_storages(self):
        dlg = StoragesDialog(parent=self)
        dlg.load(_safe_list(self.data.get("storages", [])))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rows = dlg.dump()
        for s in rows:
            if _strip(s.get("type")) and _strip(s.get("int_len")):
                QMessageBox.warning(self, "输入无效", f"存储成员“{s.get('name','(未命名)')}”：成员类型 与 整数长度 互斥，请只填一个。")
                return
        self.data["storages"] = rows
        self._notify_updated()

    def _edit_connections(self, focus_group: str | None = None, focus_key: str | None = None):
        dlg = ConnectionsDialog(parent=self)
        dlg.load(self.data)
        if focus_group and focus_key:
            self._focus_connection_in_dialog(dlg, focus_group, focus_key)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        dumped = dlg.dump()
        reqsvc_rows = self._validate_reqsvc_rows(_safe_list(dumped.get("reqsvc_conns", [])))
        if reqsvc_rows is None:
            return

        instpipe_rows = self._validate_instpipe_rows(_safe_list(dumped.get("instpipe_conns", [])))
        if instpipe_rows is None:
            return

        block_rows = self._validate_block_rows(_safe_list(dumped.get("block_conns", [])))
        if block_rows is None:
            return

        order_rows = self._validate_order_rows(_safe_list(dumped.get("orders", [])))
        if order_rows is None:
            return

        self.data["reqsvc_conns"] = reqsvc_rows
        self.data["instpipe_conns"] = instpipe_rows
        self.data["block_conns"] = block_rows
        self.data["orders"] = order_rows
        self._render_connections()
        self._notify_updated()

    def _edit_code_blocks(self):
        dlg = CodeBlocksDialog(parent=self)
        dlg.load(self.data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        dumped = dlg.dump()

        old_clocks = {
            _strip(row.get("name", "")): row
            for row in _safe_list(self.data.get("clock_blocks", []))
            if _strip(row.get("name", ""))
        }
        normalized_clocks = []
        seen_names: set[str] = set()
        for row in _safe_list(dumped.get("clock_blocks", [])):
            name = _strip(row.get("name", ""))
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            item = dict(row)
            old = old_clocks.get(name)
            if isinstance(old, dict):
                for hidden_key in ("w", "h"):
                    if hidden_key in old:
                        item[hidden_key] = old[hidden_key]
            normalized_clocks.append(item)

        dumped["clock_blocks"] = normalized_clocks
        self.data.update(dumped)

        allowed_clock_names = {row.get("name", "") for row in normalized_clocks}
        self.data["orders"] = [
            row for row in _safe_list(self.data.get("orders", []))
            if _strip(row.get("dst_inst", "")) in allowed_clock_names
        ]
        self._render_clock_blocks()
        self._render_connections()
        self._notify_updated()
