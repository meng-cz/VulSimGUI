# widgets/module_canvas_page.py
from __future__ import annotations

import math
from typing import List, Optional, Callable

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QPushButton,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem,
    QGraphicsSimpleTextItem,
    QMenu, QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QTextEdit, QFormLayout, QLineEdit
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
        accent: QColor,
        radius: float = 4.0,
    ):
        super().__init__(parent)
        self.port_name = name
        self.port_kind = kind
        self.direction = direction
        self.owner_kind = owner_kind
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
    """Manhattan 连接线：支持 preview（未固定目标前的临时线）"""
    def __init__(self, out_port: PortDot, in_port: Optional[PortDot] = None, accent: QColor = PRIMARY):
        super().__init__()
        self.out_port = out_port
        self.in_port = in_port
        self._tmp_end: Optional[QPointF] = None
        self._accent = accent

        self.setZValue(2)
        self.setPen(QPen(accent, 2))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

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

    def update_path(self):
        a = self.out_port.scene_center()
        if self.in_port is not None:
            b = self.in_port.scene_center()
        else:
            b = self._tmp_end if self._tmp_end is not None else a

        mid_x = (a.x() + b.x()) / 2.0
        path = QPainterPath(a)
        path.lineTo(QPointF(mid_x, a.y()))
        path.lineTo(QPointF(mid_x, b.y()))
        path.lineTo(b)
        self.setPath(path)

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            self.setPen(QPen(self._accent.lighter(140), 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.isSelected():
            self.setPen(QPen(self._accent.lighter(140), 3))
        else:
            self.setPen(QPen(self._accent, 2))
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_del = menu.addAction("Delete Connection")
        act = menu.exec(event.screenPos().toPoint())
        if act == act_del:
            self.delete_self()

    def delete_self(self):
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

            dot = PortDot(parent=None, name=name, kind=kind, direction=direction, owner_kind=owner_kind, accent=accent, radius=4.2)

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
            sc.addItem(handle)

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

            dot = PortDot(parent=None, name=name, kind=kind, direction=direction, owner_kind=owner_kind, accent=accent, radius=4.2)

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
            sc.addItem(handle)

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
                t.setParentItem(None)
                sc.removeItem(t)
            except RuntimeError:
                pass

        # 删除 dots（会先删连接）
        for p in list(self.ports):
            for e in list(p.edges):
                e.delete_self()
            try:
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

            dot = PortDot(self, name=name, kind=kind, direction=direction, owner_kind=self.node_kind, accent=accent, radius=3.5)
            sc.addItem(dot)
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

    def _is_output_dir(self, d: str) -> bool:
        return d in ("out", "req")

    def _is_input_dir(self, d: str) -> bool:
        return d in ("in", "serv")

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
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            port = self._port_at_pos_strict(event.pos())
            if port:
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
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        node = item if isinstance(item, BaseNodeItem) else (item.parentItem() if isinstance(item, PortDot) else None)
        if isinstance(node, BaseNodeItem):
            self._host.on_node_double_clicked(node, event.modifiers())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self._connecting:
            self._cancel_connection()
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
            if not self._is_output_dir(port.direction):
                QMessageBox.information(None, "无法开始连接", "请从输出端口（out/req）开始拖拽/点击连接。")
                return
            self._connecting = True
            self._start_port = port
            self._preview_edge = EdgeItem(out_port=port, in_port=None, accent=port.accent)
            self.scene().addItem(self._preview_edge)
            self._preview_edge.set_tmp_end(scene_pos)
            return

        if not self._is_input_dir(port.direction):
            QMessageBox.information(None, "无法连接", "请连接到输入端口（in/serv）。按 Esc 取消。")
            return

        if self._start_port is None or self._preview_edge is None:
            self._cancel_connection()
            return

        if port.port_kind != self._start_port.port_kind:
            QMessageBox.information(None, "类型不匹配", "RPC 端口只能连接 RPC；PIPE 端口只能连接 PIPE。")
            return

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


# ==========================================================
# ModuleCanvas
# ==========================================================
class ModuleCanvas(QWidget):
    # 类信号
    requestCreateModuleInst = pyqtSignal(QPointF)
    requestCreatePipeInst = pyqtSignal(QPointF)
    requestEditNode = pyqtSignal(object)  # BaseNodeItem
    requestEnterSubmodule = pyqtSignal(str, str)  # inst, module
    requestOpenNode = pyqtSignal(object)  # BaseNodeItem
    requestDeleteNode = pyqtSignal(object)  # BaseNodeItem
    requestNodeResized = pyqtSignal(object)  # BaseNodeItem（用于 ModuleCanvasPage 持久化尺寸）

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scene = GridScene()
        self.scene.setSceneRect(-2500, -2000, 5000, 4000)

        self.view = CanvasView(self.scene, host=self)
        layout.addWidget(self.view)

        self.boundary_rect = QRectF(-1500, -950, 3000, 1900)
        self.boundary = BoundaryItem(self.boundary_rect)
        self.scene.addItem(self.boundary)

        self.on_parent_port_moved: Optional[Callable[[str, QPointF], None]] = None
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
        act = menu.exec(global_pos)
        if act == act_mod:
            self.requestCreateModuleInst.emit(scene_pos)
        elif act == act_pipe:
            self.requestCreatePipeInst.emit(scene_pos)

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

        menu.addAction("（无可用操作）")
        menu.exec(global_pos)

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

        self.btn_local_cfg = QPushButton("本地配置列表")
        self.btn_local_harness = QPushButton("本地线束列表")
        self.btn_ports = QPushButton("端口列表")
        self.btn_submodules = QPushButton("子模块列表")
        self.btn_storages = QPushButton("存储对象列表")
        self.btn_code_blocks = QPushButton("代码块列表")

        for b in [self.btn_local_cfg, self.btn_local_harness, self.btn_ports,
                  self.btn_submodules, self.btn_storages, self.btn_code_blocks]:
            b.setMinimumHeight(34)
            side.addWidget(b)

        side.addStretch(1)
        root.addWidget(self.sidebar)

        # ---- Canvas
        self.canvas = ModuleCanvas()

        if "parent_port_pos" not in self.data or not isinstance(self.data["parent_port_pos"], dict):
            self.data["parent_port_pos"] = {}

        self.canvas.on_parent_port_moved = self._on_parent_port_moved

        root.addWidget(self.canvas, 1)

        self._refresh_parent_ports()

        self.btn_collapse.clicked.connect(self._toggle_sidebar)
        self.btn_local_cfg.clicked.connect(self._edit_local_cfg)
        self.btn_local_harness.clicked.connect(self._edit_local_harness)
        self.btn_ports.clicked.connect(self._edit_pipe_ports)
        self.btn_submodules.clicked.connect(self._edit_submodules_list)
        self.btn_storages.clicked.connect(self._edit_storages)
        self.btn_code_blocks.clicked.connect(self._edit_code_blocks)

        self.canvas.requestCreateModuleInst.connect(self._create_module_inst_at)
        self.canvas.requestCreatePipeInst.connect(self._create_pipe_inst_at)
        self.canvas.requestEditNode.connect(self._edit_node)
        self.canvas.requestEnterSubmodule.connect(self._enter_submodule)
        self.canvas.requestOpenNode.connect(self._open_node)
        self.canvas.requestDeleteNode.connect(self._delete_node)
        self.canvas.requestNodeResized.connect(self._on_node_resized)  # 强烈建议：尺寸持久化

        # module_inst 索引（用于 refresh_canvas）
        self._inst_nodes: dict[str, BaseNodeItem] = {}

        self._render_all_instances()

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

    # --------------------------
    # Open / Delete
    # --------------------------
    def _open_node(self, node: BaseNodeItem):
        payload = node.payload or {}
        if payload.get("_kind") != "module_inst":
            return
        mod = _strip(payload.get("module", ""))
        if not mod:
            QMessageBox.warning(self, "无法打开", "该模块实例未设置所属模块名（module 为空）。")
            return

        defn = self.module_resolver(mod)
        if defn is None:
            QMessageBox.warning(self, "模块不存在", f"未找到模块定义“{mod}”，无法打开其画布。")
            return

        self.requestOpenModuleCanvas.emit(mod)

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

            try:
                node.clear_ports()
            except Exception:
                pass
            sc = self.canvas.scene
            if sc:
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

            try:
                node.clear_ports()
            except Exception:
                pass
            sc = self.canvas.scene
            if sc:
                sc.removeItem(node)

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
    def _toggle_sidebar(self):
        if self.sidebar.width() > 60:
            self.sidebar.setFixedWidth(52)
            self.btn_collapse.setText("⟩")
            self.btn_collapse.setToolTip("展开侧边栏")
            self.lbl_title.setVisible(False)
            self.btn_local_cfg.setText("配")
            self.btn_local_harness.setText("束")
            self.btn_ports.setText("端")
            self.btn_submodules.setText("子")
            self.btn_storages.setText("存")
            self.btn_code_blocks.setText("码")
        else:
            self.sidebar.setFixedWidth(220)
            self.btn_collapse.setText("⟨")
            self.btn_collapse.setToolTip("收起侧边栏")
            self.lbl_title.setVisible(True)
            self.btn_local_cfg.setText("本地配置列表")
            self.btn_local_harness.setText("本地线束列表")
            self.btn_ports.setText("端口列表")
            self.btn_submodules.setText("子模块列表")
            self.btn_storages.setText("存储对象列表")
            self.btn_code_blocks.setText("代码块列表")

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
            self._refresh_parent_ports()

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

    def _render_all_instances(self):
        self._inst_nodes.clear()
        sc = self.canvas.scene

        for it in list(sc.items()):
            if it is self.canvas.boundary:
                continue
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
            col += 1
            if col >= 4:
                col = 0
                row += 1

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
            if inst_old and inst_old in self._inst_nodes:
                self._inst_nodes.pop(inst_old, None)
            self._inst_nodes[inst_new] = node

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
        self._notify_updated()

    def _edit_local_harness(self):
        dlg = LocalHarnessDialog(parent=self)
        dlg.load(_safe_list(self.data.get("local_harnesses", [])))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.data["local_harnesses"] = dlg.dump()
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

    def _edit_code_blocks(self):
        dlg = CodeBlocksDialog(parent=self)
        dlg.load(self.data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.data.update(dlg.dump())
        self._notify_updated()
