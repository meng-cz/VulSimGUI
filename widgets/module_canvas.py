# widgets/module_canvas.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, List, Tuple

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsPathItem, QGraphicsEllipseItem, QMenu
)


PRIMARY = QColor("#007180")
BG_DARK = QColor("#12161b")
PANEL = QColor("#232932")
BORDER = QColor("#2d353f")
TEXT = QColor("#e5e7eb")
MUTED = QColor("#94a3b8")


class GridScene(QGraphicsScene):
    """点阵背景（schematic-grid 观感）：在 drawBackground 里画。"""
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

        # 对齐到 spacing 网格
        x0 = left - (left % self.dot_spacing)
        y0 = top - (top % self.dot_spacing)

        r = self.dot_radius
        for x in range(x0, right, self.dot_spacing):
            for y in range(y0, bottom, self.dot_spacing):
                painter.drawEllipse(QPointF(x, y), r, r)

        painter.restore()


class CanvasView(QGraphicsView):
    """支持缩放 + 平移（中键/空格左键）。"""
    def __init__(self, scene: QGraphicsScene):
        super().__init__(scene)
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

    def wheelEvent(self, event):
        # Ctrl+滚轮缩放（也可以无 Ctrl，按你喜好）
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_down = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
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
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_down
        ):
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
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
        super().mouseReleaseEvent(event)


class PortItem(QGraphicsEllipseItem):
    """端口点：维护与连线的绑定关系。"""
    def __init__(self, parent: QGraphicsItem, radius=3.0, is_output=False):
        super().__init__(-radius, -radius, radius * 2, radius * 2, parent)
        self.setBrush(QBrush(PRIMARY))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setZValue(10)
        self.is_output = is_output
        self.edges: List["EdgeItem"] = []

        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor("#12a2b4")))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(PRIMARY))
        super().hoverLeaveEvent(event)

    def add_edge(self, edge: "EdgeItem"):
        if edge not in self.edges:
            self.edges.append(edge)

    def remove_edge(self, edge: "EdgeItem"):
        if edge in self.edges:
            self.edges.remove(edge)

    def scene_center(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))


class NodeItem(QGraphicsItem):
    """模块节点（卡片样式 + 标题栏 + 输入/输出端口）。"""
    def __init__(self, title: str, w=260, h=160):
        super().__init__()
        self.title = title
        self.w = w
        self.h = h

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        # 端口：示例（你后续可以动态生成）
        self.in_ports: List[PortItem] = []
        self.out_ports: List[PortItem] = []

        # 左侧两个输入
        for i in range(2):
            p = PortItem(self, radius=3.0, is_output=False)
            p.setPos(10, 52 + i * 18)
            self.in_ports.append(p)

        # 右侧一个输出
        p_out = PortItem(self, radius=3.0, is_output=True)
        p_out.setPos(self.w - 10, 52)
        self.out_ports.append(p_out)

        self._hover = False

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.w, self.h)

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 背板
        bg = QColor(PANEL)
        pen = QPen(QColor(PRIMARY) if self.isSelected() else BORDER, 2 if self.isSelected() else 1)
        painter.setPen(pen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(self.boundingRect(), 8, 8)

        # 标题栏
        title_h = 28
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 113, 128, 55)))  # primary/20
        painter.drawRoundedRect(QRectF(0, 0, self.w, title_h), 8, 8)
        painter.drawRect(QRectF(0, title_h - 8, self.w, 8))  # 覆盖下圆角的“台阶”观感

        # 标题文字
        painter.setPen(QPen(TEXT))
        painter.setFont(painter.font())
        painter.drawText(QRectF(10, 0, self.w - 20, title_h), Qt.AlignmentFlag.AlignVCenter, self.title)

        # 端口标签（demo）
        painter.setPen(QPen(MUTED))
        painter.setFont(painter.font())
        painter.drawText(QRectF(20, 44, 120, 20), "DATA_0")
        painter.drawText(QRectF(20, 62, 120, 20), "DATA_1")
        painter.drawText(QRectF(self.w - 110, 44, 90, 20), Qt.AlignmentFlag.AlignRight, "PIPE_OUT")

        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # 节点移动时更新所有连线
            for p in self.in_ports + self.out_ports:
                for e in list(p.edges):
                    e.update_path()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    """直角（Manhattan）连线：从 out_port 到 in_port。"""
    def __init__(self, out_port: PortItem, in_port: PortItem):
        super().__init__()
        self.out_port = out_port
        self.in_port = in_port

        self.setZValue(1)
        self.setPen(QPen(PRIMARY, 2))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self.out_port.add_edge(self)
        self.in_port.add_edge(self)

        self.update_path()

    def update_path(self):
        a = self.out_port.scene_center()
        b = self.in_port.scene_center()

        # 简单的直角路径：先水平再垂直（可按需要升级为避障路由）
        mid_x = (a.x() + b.x()) / 2.0
        path = QPainterPath(a)
        path.lineTo(QPointF(mid_x, a.y()))
        path.lineTo(QPointF(mid_x, b.y()))
        path.lineTo(b)
        self.setPath(path)

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            self.setPen(QPen(QColor("#12a2b4"), 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.isSelected():
            self.setPen(QPen(QColor("#12a2b4"), 3))
        else:
            self.setPen(QPen(PRIMARY, 2))
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_del = menu.addAction("Delete Connection")
        act = menu.exec(event.screenPos().toPoint())
        if act == act_del:
            self.delete_self()

    def delete_self(self):
        self.out_port.remove_edge(self)
        self.in_port.remove_edge(self)
        scene = self.scene()
        if scene is not None:
            scene.removeItem(self)


class ModuleCanvas(QWidget):
    """
    模块画布：QGraphicsView + QGraphicsScene
    - 点阵背景
    - 节点拖拽
    - 端口
    - 直角连线
    - Ctrl+滚轮缩放；中键/空格拖拽平移
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Module Canvas")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scene = GridScene()
        self.scene.setSceneRect(-2000, -2000, 4000, 4000)

        self.view = CanvasView(self.scene)
        layout.addWidget(self.view)

        # Demo：放几个节点 + 一条连线，运行即可看到效果
        self._build_demo()

    def _build_demo(self):
        n1 = NodeItem("Instance_A", w=260, h=160)
        n1.setPos(-600, -350)
        self.scene.addItem(n1)

        n2 = NodeItem("Pipe_01", w=200, h=120)
        n2.setPos(0, -120)
        self.scene.addItem(n2)

        # 用 n1 输出端口连 n2 输入端口
        e = EdgeItem(n1.out_ports[0], n2.in_ports[0])
        self.scene.addItem(e)

        # 再放一个 Clock Block（简单矩形节点，先用 NodeItem 模拟）
        clk = NodeItem("CLK_GEN_MAIN", w=160, h=90)
        clk.setPos(-350, 250)
        self.scene.addItem(clk)

    # 你后续接后端数据时，会用到下面这些 API
    def add_node(self, title: str, pos: QPointF, w=260, h=160) -> NodeItem:
        node = NodeItem(title, w=w, h=h)
        node.setPos(pos)
        self.scene.addItem(node)
        return node

    def connect_ports(self, out_port: PortItem, in_port: PortItem) -> EdgeItem:
        edge = EdgeItem(out_port, in_port)
        self.scene.addItem(edge)
        return edge
