"""
TEGG Touch 蛋挞 (PyQt6) - wheel_ring_item.py
中心圆环按钮 — QPainterPath 布尔减法实现真正镂空。
"""

from PyQt6.QtWidgets import QGraphicsObject
from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSignal, pyqtProperty
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QBrush, QColor, QFont

from core.i18n import get_font
from core.constants import WHEEL_VISUAL_INSET
from models.wheel_model import WheelRingData
from engine.hover_state_machine import HoverStateMachine
from scene.tooltip_item import build_edit_tooltip


_RING_COLORS = {
    'normal':           ("#111111", "#555"),
    'hover':            ("#0284C7", "#026AA2"),
    'active_left':      ("#F59E0B", "#D97706"),
    'active_right':     ("#10B981", "#059669"),
    'active_middle':    ("#A855F7", "#9333EA"),
    'active_wheelup':   ("#EC4899", "#DB2777"),
    'active_wheeldown': ("#F43F5E", "#E11D48"),
    'active_xbutton1':  ("#06B6D4", "#0891B2"),
    'active_xbutton2':  ("#8B5CF6", "#7C3AED"),
}


class WheelRingItem(QGraphicsObject):
    """中心圆环按钮 — 真正的镂空圆环

    旧版: 外圆 + 内圆透明覆盖（hack）
    新版: QPainterPath.subtracted() 布尔减法
    """

    # 信号
    doubleClicked = pyqtSignal(object)
    hoverActivated = pyqtSignal(object)
    hoverDeactivated = pyqtSignal(object)
    actionTriggered = pyqtSignal(object, str, str)

    def __init__(self, data: WheelRingData, cx, cy, r_inner, r_outer):
        super().__init__()
        self.data = data
        self._cx = cx
        self._cy = cy
        self._r_inner = r_inner
        self._r_outer = r_outer
        self._visual_state = 'normal'
        self._mode = 'edit'
        self._charge_progress = 0.0

        # 视觉半径（碰撞半径各方向缩进 VISUAL_INSET）
        self._v_inner = r_inner + WHEEL_VISUAL_INSET
        self._v_outer = r_outer - WHEEL_VISUAL_INSET

        # 预计算路径：碰撞路径(hit) + 视觉路径(visual)
        self._hit_path = self._build_ring_path(r_inner, r_outer)
        self._visual_path = self._build_ring_path(self._v_inner, self._v_outer)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton |
            Qt.MouseButton.RightButton |
            Qt.MouseButton.MiddleButton
        )
        self.setZValue(10)  # 圆环在扇面之上

        # 编辑模式持久化光标（不依赖 hover enter/leave）
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 悬停状态机
        self._hover_sm = HoverStateMachine(data.hover_delay, data.hover_release_delay)
        self._hover_sm.activated.connect(self._on_hover_activated)
        self._hover_sm.deactivated.connect(self._on_hover_deactivated)
        self._hover_sm.charge_progress.connect(self._on_charge_progress)
        self._hover_sm.release_progress.connect(self._on_release_progress)

    def _build_ring_path(self, r_inner, r_outer) -> QPainterPath:
        """圆环 = 外圆 - 内圆（布尔减法）"""
        outer = QPainterPath()
        outer.addEllipse(
            self._cx - r_outer, self._cy - r_outer,
            r_outer * 2, r_outer * 2)

        inner = QPainterPath()
        inner.addEllipse(
            self._cx - r_inner, self._cy - r_inner,
            r_inner * 2, r_inner * 2)

        return outer.subtracted(inner)

    def boundingRect(self) -> QRectF:
        return self._hit_path.boundingRect().adjusted(-2, -2, 2, 2)

    def shape(self) -> QPainterPath:
        """精确碰撞检测 — 使用碰撞路径（比视觉区域各方向大 VISUAL_INSET）"""
        return self._hit_path

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fill_str, border_str = _RING_COLORS.get(
            self._visual_state, _RING_COLORS['normal'])

        painter.setPen(QPen(QColor(border_str), 2))
        painter.setBrush(QBrush(QColor(fill_str)))
        painter.drawPath(self._visual_path)

        # 充能进度 — 径向扩展（在视觉区域内从内圆向外圆扩展）
        if self._charge_progress > 0.01:
            charge_r = self._v_inner + (self._v_outer - self._v_inner) * self._charge_progress
            charge_outer = QPainterPath()
            charge_outer.addEllipse(
                self._cx - charge_r, self._cy - charge_r,
                charge_r * 2, charge_r * 2)
            charge_inner = QPainterPath()
            r_in = self._v_inner + 2  # 略微内缩，避免覆盖内圆边框
            charge_inner.addEllipse(
                self._cx - r_in, self._cy - r_in,
                r_in * 2, r_in * 2)
            charge_path = charge_outer.subtracted(charge_inner)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#0284C7")))
            painter.drawPath(charge_path)

        # 中心文字: 不在场景中显示，避免遮挡视线（仍可在编辑弹窗中设定）

    # ── 充能进度属性 ──

    @pyqtProperty(float)
    def chargeProgress(self):
        return self._charge_progress

    @chargeProgress.setter
    def chargeProgress(self, val):
        self._charge_progress = val
        self.update()

    # ── 状态 ──

    def set_visual_state(self, state: str):
        if self._visual_state != state:
            self._visual_state = state
            self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        # 编辑模式持久化手型光标
        if mode == 'edit':
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        self._hover_sm.reset()
        self._visual_state = 'normal'
        self._charge_progress = 0.0
        self.update()

    # ── 鼠标事件 ──

    def mousePressEvent(self, event):
        if self._mode == 'run':
            btn = event.button()
            if btn == Qt.MouseButton.LeftButton and self.data.lclick:
                self.actionTriggered.emit(self.data, self.data.lclick, 'p')
                self.set_visual_state('active_left')
            elif btn == Qt.MouseButton.RightButton and self.data.rclick:
                self.actionTriggered.emit(self.data, self.data.rclick, 'p')
                self.set_visual_state('active_right')
            elif btn == Qt.MouseButton.MiddleButton and self.data.mclick:
                self.actionTriggered.emit(self.data, self.data.mclick, 'p')
                self.set_visual_state('active_middle')
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mode == 'run':
            key_map = {
                Qt.MouseButton.LeftButton: self.data.lclick,
                Qt.MouseButton.RightButton: self.data.rclick,
                Qt.MouseButton.MiddleButton: self.data.mclick,
            }
            key = key_map.get(event.button(), '')
            if key:
                self.actionTriggered.emit(self.data, key, 'r')
            self.set_visual_state('hover' if self._hover_sm.is_active else 'normal')
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击 → 打开编辑弹窗"""
        if self._mode == 'edit':
            self.doubleClicked.emit(self)

    # ── Hover 事件 ──

    def hoverEnterEvent(self, event):
        if self._mode == 'edit':
            scene = self.scene()
            if scene:
                scene.show_tooltip(build_edit_tooltip(self.data), event.scenePos())
        elif self._mode == 'run' and self.data.hover:
            self._hover_sm.enter()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        if self._mode == 'edit':
            scene = self.scene()
            if scene:
                scene.move_tooltip(event.scenePos())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        if self._mode == 'edit':
            scene = self.scene()
            if scene:
                scene.hide_tooltip()
        if self._mode == 'run':
            self._hover_sm.leave()
            if not self._hover_sm.is_active:
                self.set_visual_state('normal')
        super().hoverLeaveEvent(event)

    # ── 滚轮 ──

    def on_wheel(self, direction):
        key = self.data.wheelup if direction == 'up' else self.data.wheeldown
        if key:
            self.actionTriggered.emit(self.data, key, 'c')
            state = 'active_wheelup' if direction == 'up' else 'active_wheeldown'
            self.set_visual_state(state)
            QTimer.singleShot(150, lambda: self.set_visual_state(
                'hover' if self._hover_sm.is_active else 'normal'))

    # ── 状态机回调 ──

    def _on_hover_activated(self):
        self.hoverActivated.emit(self.data)
        self._charge_progress = 0.0  # 充能完成，清除进度条
        self.set_visual_state('hover')

    def _on_hover_deactivated(self):
        self.hoverDeactivated.emit(self.data)
        self._charge_progress = 0.0  # 释放完成，清除进度条
        self.set_visual_state('normal')

    def _on_charge_progress(self, progress):
        """充能进度回调 — 径向从内向外扩展 (0→1)"""
        self._charge_progress = progress
        self.update()

    def _on_release_progress(self, progress):
        """释放倒计时进度回调 — 径向从外向内收缩 (1→0)"""
        self._charge_progress = progress
        self.update()
