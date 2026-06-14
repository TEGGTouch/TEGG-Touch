"""
TEGG Touch 蛋挞 (PyQt6) - gp_wheel_item.py
方向盘 QGraphicsObject — 4×2 复合 item:
  左 1×2 = LT 视觉进度条
  中 2×2 = 圆形方向盘 (转向指示器)
  右 1×2 = RT 视觉进度条
整体 4×2 矩形是统一输入区, 鼠标位置在哪里都生效。
默认大小固定 (400×200), 不可缩放, 仅可拖动。
"""

import math

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath

from core.constants import (
    DEFAULT_GRID_SIZE, BTN_MARGIN,
    COLOR_GP_BTN_BG, COLOR_GP_BTN_BORDER, COLOR_GP_BTN_TEXT,
)
from core.i18n import get_font
from models.gamepad_model import GamepadWheelData


# 配色 (跟 gp_stick / gp_btn 蓝调一致)
_FILL = QColor(COLOR_GP_BTN_BG)
_BORDER_IDLE = QColor(COLOR_GP_BTN_BORDER)
_BORDER_ACTIVE = QColor("#60A5FA")
_TEXT = QColor(COLOR_GP_BTN_TEXT)
_PROGRESS = QColor("#0284C7")          # LT/RT 进度条填充 (hover 蓝)
_PROGRESS_BG = QColor("#1A1E2E")       # 进度条背景 (跟 item 底色一致)
_INDICATOR = QColor("#0284C7")         # 方向盘指示线 idle
_INDICATOR_ACTIVE = QColor("#FFFFFF")  # 方向盘指示线 active
_AUX = QColor(COLOR_GP_BTN_BORDER)     # 内部分隔线

# 方向盘指示线最大旋转角度 (steering = ±1.0 时左右旋转此角度)
_MAX_WHEEL_ANGLE_DEG = 70.0


class GpWheelItem(QGraphicsObject):
    """方向盘 item — 4×2 矩形, 单例 (每个 profile 最多一个)"""

    doubleClicked = pyqtSignal(object)

    def __init__(self, data: GamepadWheelData, offset_x: float = 0, offset_y: float = 0):
        super().__init__()
        self.data = data
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._mode = 'edit'  # 'edit' | 'run'
        # run 状态: steering ∈ [-1, 1], lt/rt ∈ [0, 1], active bool
        self._steering = 0.0
        self._lt = 0.0
        self._rt = 0.0
        self._active = False

        # Z 序: 跟摇杆同 20 (方向盘单例, 不会与其他 gp_wheel 叠)
        self.setZValue(20)
        self.setAcceptHoverEvents(False)

        # 初始位置 (像素 → scene 坐标 + 中心 offset)
        self.setPos(self._offset_x + data.x, self._offset_y + data.y)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # 编辑模式光标
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)

        self.setToolTip(self._build_tooltip())

    # ── 几何 ──

    def boundingRect(self) -> QRectF:
        """扩展 boundingRect 容纳 release zone (= w/2 × ratio 半径范围) — 留出未来视觉反馈空间"""
        ratio = max(1.0, self.data.release_threshold_ratio)
        ext_x = (self.data.w / 2) * (ratio - 1.0) + 4
        ext_y = (self.data.h / 2) * (ratio - 1.0) + 4
        return QRectF(-ext_x, -ext_y,
                      self.data.w + 2 * ext_x,
                      self.data.h + 2 * ext_y)

    def shape(self) -> QPainterPath:
        """hit-test 只在内部矩形 (避免 release zone 触发误判)"""
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.data.w, self.data.h))
        return path

    def rect_center_local(self) -> QPointF:
        return QPointF(self.data.w / 2, self.data.h / 2)

    def rect_center_scene(self) -> QPointF:
        return self.mapToScene(self.rect_center_local())

    def half_width_scene(self) -> float:
        # scene 无缩放, 直接返回本地一半宽
        return self.data.w / 2

    def is_cursor_in_rect(self, scene_pos: QPointF) -> bool:
        local = self.mapFromScene(scene_pos)
        return (0 <= local.x() <= self.data.w
                and 0 <= local.y() <= self.data.h)

    def cursor_distance_ratio(self, scene_pos: QPointF) -> float:
        """鼠标距矩形中心 / (w/2) — 大于 release_threshold_ratio 时应释放
        用 X 距离衡量 (steering 主要在 X 方向, Y 方向不影响 steering 但仍计算合距更安全)"""
        c = self.rect_center_scene()
        dx = abs(scene_pos.x() - c.x())
        half = max(1.0, self.half_width_scene())
        return dx / half

    # ── 绘制 ──

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_color = _BORDER_ACTIVE if self._active else _BORDER_IDLE
        border_w = 3 if self._active else 2

        # 整体矩形外框
        rect = QRectF(BTN_MARGIN, BTN_MARGIN,
                      self.data.w - 2 * BTN_MARGIN,
                      self.data.h - 2 * BTN_MARGIN)
        painter.setPen(QPen(border_color, border_w))
        painter.setBrush(QBrush(_FILL))
        painter.drawRoundedRect(rect, 8, 8)

        # 3 列等分: w/4 = LT 条 / 2w/4 = 中央方向盘 / w/4 = RT 条
        col_w = self.data.w / 4.0
        h = self.data.h

        # 左 LT 条
        lt_rect = QRectF(0, 0, col_w, h).adjusted(8, 8, -4, -8)
        self._paint_trigger_bar(painter, lt_rect, self._lt, "LT")

        # 右 RT 条
        rt_rect = QRectF(3 * col_w, 0, col_w, h).adjusted(4, 8, -8, -8)
        self._paint_trigger_bar(painter, rt_rect, self._rt, "RT")

        # 中央方向盘 (2 列宽 = 2 × col_w, 圆形内切于 2×2 子区域)
        center_box = QRectF(col_w, 0, 2 * col_w, h).adjusted(8, 8, -8, -8)
        cx = center_box.x() + center_box.width() / 2
        cy = center_box.y() + center_box.height() / 2
        r = min(center_box.width(), center_box.height()) / 2

        # 圆盘 (盘面)
        painter.setPen(QPen(border_color, 2))
        painter.setBrush(QBrush(_FILL.darker(110)))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # 中心横十字 (作为方向盘视觉)
        painter.setPen(QPen(_AUX, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(cx - r * 0.8, cy), QPointF(cx + r * 0.8, cy))

        # 方向指示线 (steering = ±1.0 → ±_MAX_WHEEL_ANGLE_DEG)
        angle_deg = self._steering * _MAX_WHEEL_ANGLE_DEG
        angle_rad = math.radians(angle_deg - 90)  # -90 让 0° 指向上
        ind_color = _INDICATOR_ACTIVE if self._active else _INDICATOR
        painter.setPen(QPen(ind_color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        ind_len = r * 0.85
        painter.drawLine(
            QPointF(cx, cy),
            QPointF(cx + math.cos(angle_rad) * ind_len,
                    cy + math.sin(angle_rad) * ind_len),
        )
        # 中心实心圆点
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ind_color)
        painter.drawEllipse(QPointF(cx, cy), 5, 5)

        # 名称 (编辑模式右上角小字)
        if self._mode == 'edit' and self.data.name:
            fn = get_font()
            f = QFont(fn)
            f.setPixelSize(12)
            painter.setFont(f)
            painter.setPen(_TEXT)
            painter.drawText(
                QRectF(0, 4, self.data.w, 16),
                Qt.AlignmentFlag.AlignCenter, self.data.name)

    def _paint_trigger_bar(self, painter: QPainter, rect: QRectF,
                           value: float, label: str):
        """绘制单个 LT / RT 进度条 (底部往上填充)"""
        # 背景
        painter.setPen(QPen(_BORDER_IDLE, 1))
        painter.setBrush(QBrush(_PROGRESS_BG))
        painter.drawRoundedRect(rect, 6, 6)

        # 填充 (从底往上)
        v = max(0.0, min(1.0, value))
        if v > 0.01:
            fill_h = rect.height() * v
            fill_rect = QRectF(rect.x(), rect.bottom() - fill_h,
                                rect.width(), fill_h)
            color = QColor(_PROGRESS)
            color.setAlphaF(0.85)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(fill_rect, 6, 6)

        # 标签 (顶部) + 当前值 (底部)
        fn = get_font()
        f = QFont(fn)
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.Bold)
        painter.setFont(f)
        painter.setPen(_TEXT)
        painter.drawText(
            QRectF(rect.x(), rect.y() + 4, rect.width(), 20),
            Qt.AlignmentFlag.AlignCenter, label)
        # 当前 % 值
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Normal)
        painter.setFont(f)
        painter.setPen(_TEXT)
        painter.drawText(
            QRectF(rect.x(), rect.bottom() - 18, rect.width(), 14),
            Qt.AlignmentFlag.AlignCenter, f"{int(v * 100)}%")

    # ── 状态控制 (run_controller 调) ──

    def set_visual(self, steering: float, lt: float, rt: float, active: bool = True):
        steering = max(-1.0, min(1.0, steering))
        lt = max(0.0, min(1.0, lt))
        rt = max(0.0, min(1.0, rt))
        if (steering == self._steering and lt == self._lt
                and rt == self._rt and active == self._active):
            return
        self._steering = steering
        self._lt = lt
        self._rt = rt
        self._active = active
        self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        movable = (mode == 'edit')
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)
        if mode == 'edit':
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        # 模式切换重置视觉
        self._steering = 0.0
        self._lt = 0.0
        self._rt = 0.0
        self._active = False
        self.update()

    # ── 编辑交互 ──

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self._mode == 'edit' and self.scene() is not None:
                gs = self.scene().grid_size
                new_pos = QPointF(
                    round((value.x() - self._offset_x) / gs) * gs + self._offset_x,
                    round((value.y() - self._offset_y) / gs) * gs + self._offset_y,
                )
                self.data.x = new_pos.x() - self._offset_x
                self.data.y = new_pos.y() - self._offset_y
                return new_pos
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _build_tooltip(self) -> str:
        return "方向盘\nLT + 转向 + RT\n双击编辑 ｜ 可拖动 ｜ 不可缩放"
