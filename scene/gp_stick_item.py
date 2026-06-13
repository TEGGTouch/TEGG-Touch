"""
TEGG Touch 蛋挞 (PyQt6) - gp_stick_item.py
摇杆 QGraphicsObject — 圆形区域, 模拟左/右手柄摇杆。

设计:
- 编辑模式: 跟普通按钮一样可拖拽 + 缩放 (强制方形, w == h)
- 运行模式: 由 RunController 通过坐标判定驱动状态机:
    idle → 鼠标入圆 → active (SetCursorPos 圆心, 小球出现)
    active → 鼠标距圆心 > R → sticking (小球钉边缘)
    sticking → 距圆心 > R × release_threshold → idle (小球消失)
- 跨摇杆切换归属 + SetCursorPos 全部在 RunController 层处理
- 本类只负责: 绘制 + 暴露几何 (center/radius) + set_stick_visual(state, x, y)
"""

import math

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontDatabase, QPainterPath

from core.constants import (
    DEFAULT_GRID_SIZE, BTN_MARGIN,
    COLOR_GP_BTN_BG, COLOR_GP_BTN_BORDER, COLOR_GP_BTN_TEXT,
    STICK_ID_LEFT, STICK_ID_RIGHT,
    ACTION_COLORS, GP_KEY_PREFIX, GP_KEY_TO_LABEL,
)

# 小球颜色: 默认 (跟按钮 hover 蓝一致); 鼠标动作触发时按 ACTION_COLORS 切换
_BALL_COLOR_OVERRIDE = "#0284C7"
# sticking 进度 ≥ 90% 时圆环变玫红, 警示快要释放了 (跟轮盘 toggle 玫红一致)
_STICK_WARN_COLOR = "#E11D48"
_STICK_WARN_THRESHOLD = 0.85


def _gp_display(key: str) -> str:
    """gp:LB → 左肩 LB; gpmacro:Foo → Foo; 其它 → 原样"""
    if not key:
        return ''
    if key.startswith(GP_KEY_PREFIX):
        storage = key[len(GP_KEY_PREFIX):]
        return GP_KEY_TO_LABEL.get(storage, storage)
    if key.startswith('gpmacro:'):
        return key[len('gpmacro:'):]
    return key
from core.i18n import get_font
from models.gamepad_model import GamepadStickData
from scene.tooltip_item import build_edit_tooltip

# 状态色
_BORDER_IDLE = QColor(COLOR_GP_BTN_BORDER)        # 蓝, 同手柄键边框
_BORDER_ACTIVE = QColor("#60A5FA")                 # 亮蓝
_BORDER_STICKING = QColor("#F59E0B")               # 琥珀
_FILL = QColor(COLOR_GP_BTN_BG)
_BALL = QColor(_BALL_COLOR_OVERRIDE)               # hover 蓝, 跟按钮一致
_AUX_COLOR = QColor(COLOR_GP_BTN_BORDER)           # 死区圈 + 八向辅助线: 跟边框一致的蓝, 清晰可见
_TEXT = QColor(COLOR_GP_BTN_TEXT)

# 缩放手柄尺寸 (与 ResizeHandleItem 一致)
_RESIZE_INSET = 24


class GpStickItem(QGraphicsObject):
    """摇杆 item — 圆形, 由 RunController 驱动状态"""

    doubleClicked = pyqtSignal(object)   # 双击 → 打开编辑器
    data_changed = pyqtSignal()

    def __init__(self, data: GamepadStickData, offset_x: float = 0, offset_y: float = 0):
        super().__init__()
        self.data = data
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._mode = 'edit'  # 'edit' | 'run'
        self._state = 'idle'  # 'idle' | 'active' | 'sticking'
        self._value = (0.0, 0.0)  # 当前 stick 值, 用于绘制小球
        # sticking 进度 0~1: 0=刚出圆, 1=已到释放阈值 (用于画进度条)
        self._sticking_progress = 0.0
        # 鼠标动作触发显示: 例如用户按下 LMB → ball 变 'lclick' 色 + 显示 stick.lclick 的键文本
        self._pressed_action: str | None = None
        self._pressed_key_display: str = ''

        # Z 序: 摇杆 (20) > 普通按钮 (15), 多个摇杆叠放时按添加顺序 (Qt 自动)
        self.setZValue(20)
        self.setAcceptHoverEvents(False)  # 不依赖 hover, 用 polling

        # 初始位置 (像素 → 场景坐标 = 像素 + offset)
        self.setPos(self._offset_x + data.x, self._offset_y + data.y)

        # 编辑模式 flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # 缩放手柄 (强制方形)
        from scene.resize_handle_item import ResizeHandleItem
        self._resize_handle = ResizeHandleItem(self)
        self._resize_handle.setPos(self.data.w - _RESIZE_INSET, self.data.h - _RESIZE_INSET)
        self._update_resize_handle_pos()

        # 编辑模式光标
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)

        # 编辑模式 tooltip
        self.setToolTip(self._build_tooltip())

    # ── 几何 ──

    def boundingRect(self) -> QRectF:
        """扩展 boundingRect 容纳: 边缘小球外延 + sticking 进度条最大长度 (= R × (ratio - 1))"""
        r = min(self.data.w, self.data.h) / 2 - BTN_MARGIN
        if r <= 0:
            return QRectF(0, 0, self.data.w, self.data.h)
        ball_r = max(6, r * 0.15)
        max_bar = r * max(0.0, self.data.release_threshold_ratio - 1.0)
        overflow = ball_r + max_bar + 4  # 4px 安全边距 (抗锯齿 + line cap)
        return QRectF(-overflow, -overflow,
                      self.data.w + 2 * overflow,
                      self.data.h + 2 * overflow)

    def shape(self) -> QPainterPath:
        """hit-test 区域 = 视觉圆 (boundingRect 扩大用于绘制, 但点击/hover 只在圆内)"""
        cx, cy, r = self.circle_geom()
        path = QPainterPath()
        if r > 0:
            path.addEllipse(QPointF(cx, cy), r, r)
        return path

    def circle_geom(self) -> tuple[float, float, float]:
        """返回圆 (cx, cy, r) — 本地坐标, 取 min(w,h) 内切圆并留 margin"""
        cx = self.data.w / 2
        cy = self.data.h / 2
        r = min(self.data.w, self.data.h) / 2 - BTN_MARGIN
        return cx, cy, r

    def circle_center_scene(self) -> QPointF:
        cx, cy, _ = self.circle_geom()
        return self.mapToScene(QPointF(cx, cy))

    def circle_radius_scene(self) -> float:
        _, _, r = self.circle_geom()
        # scene 没有缩放, 半径直接等于本地半径
        return r

    def is_cursor_in_circle(self, scene_pos: QPointF) -> bool:
        c = self.circle_center_scene()
        dx = scene_pos.x() - c.x()
        dy = scene_pos.y() - c.y()
        r = self.circle_radius_scene()
        return (dx * dx + dy * dy) <= (r * r)

    def cursor_distance_ratio(self, scene_pos: QPointF) -> float:
        """鼠标距圆心 / R; > 1.0 表示在圆外, > release_threshold 应释放"""
        c = self.circle_center_scene()
        dx = scene_pos.x() - c.x()
        dy = scene_pos.y() - c.y()
        r = self.circle_radius_scene()
        if r <= 0:
            return 99.0
        return math.sqrt(dx * dx + dy * dy) / r

    # ── 绘制 ──

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = self.circle_geom()

        # 选边框色 (sticking 时不再变黄, 改用进度条表达; 边框保持 active 蓝)
        if self._state in ('active', 'sticking'):
            border_color = _BORDER_ACTIVE
            border_width = 3
        else:
            border_color = _BORDER_IDLE
            border_width = 2

        # 填充圆
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(_FILL))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # 死区圈 (仅编辑模式可见, 虚线辅助; 加粗 + 蓝色, 醒目)
        if self._mode == 'edit' and self.data.dead_zone > 0:
            painter.setPen(QPen(_AUX_COLOR, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            dz_r = r * self.data.dead_zone
            painter.drawEllipse(QPointF(cx, cy), dz_r, dz_r)

        # 中心标签 (L / R), 始终显示
        label = "L" if self.data.stick_id == STICK_ID_LEFT else "R"
        fn = get_font()
        font = QFont(fn)
        font.setPixelSize(max(14, int(r * 0.35)))
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(_TEXT)
        # 标签放圆心稍上方 (active 时小球会盖到圆心区域, 标签留在上半)
        text_rect = QRectF(0, cy - r * 0.55, self.data.w, r * 0.5)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

        # 八方向锁定时的 8 个指示扇区分隔线 (仅编辑模式; 死区内不画, 起点 = 死区圈外缘)
        if self._mode == 'edit' and self.data.eight_way:
            painter.setPen(QPen(_AUX_COLOR, 1, Qt.PenStyle.DashLine))
            inner = r * max(0.0, self.data.dead_zone)
            for i in range(8):
                ang = i * math.pi / 4
                x1 = cx + math.cos(ang) * inner
                y1 = cy + math.sin(ang) * inner
                x2 = cx + math.cos(ang) * r
                y2 = cy + math.sin(ang) * r
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 小球 (active / sticking 时显示); 鼠标动作触发时切色 + 显示键文本
        if self._state in ('active', 'sticking'):
            vx, vy = self._value
            bx = cx + vx * r
            by = cy + vy * r
            ball_r = max(6, r * 0.15)
            # 颜色: 默认 hover 蓝, 鼠标动作触发时用 ACTION_COLORS
            if self._pressed_action:
                ball_color = QColor(ACTION_COLORS.get(self._pressed_action, _BALL_COLOR_OVERRIDE))
            else:
                ball_color = _BALL

            # sticking: 在圆外画一个完整 360° 蓝色圆环, 向外径向扩展 (类似中心环 hover 充能效果)
            # 内半径 = R (紧贴圆边缘), 外半径 = R + progress × max_extension
            if self._state == 'sticking':
                max_bar = r * max(0.0, self.data.release_threshold_ratio - 1.0)
                bar_len = self._sticking_progress * max_bar
                if bar_len > 1.0:
                    outer_r = r + bar_len
                    ring_outer = QPainterPath()
                    ring_outer.addEllipse(QPointF(cx, cy), outer_r, outer_r)
                    ring_inner = QPainterPath()
                    ring_inner.addEllipse(QPointF(cx, cy), r, r)
                    ring_path = ring_outer.subtracted(ring_inner)
                    # 进度 ≥ 90% 变玫红警示, 否则蓝
                    if self._sticking_progress >= _STICK_WARN_THRESHOLD:
                        ring_color = QColor(_STICK_WARN_COLOR)
                    else:
                        ring_color = QColor(_BALL_COLOR_OVERRIDE)
                    ring_color.setAlphaF(0.5)   # 50% 透明
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(ring_color))
                    painter.drawPath(ring_path)

            # ball
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ball_color)
            painter.drawEllipse(QPointF(bx, by), ball_r, ball_r)

            # 触发键文本: 水平居中对齐 ball 的 bx (不再固定在圆心轴线)
            if self._pressed_action and self._pressed_key_display:
                fn = get_font()
                f = QFont(fn)
                f.setPixelSize(max(14, int(r * 0.22)))
                f.setWeight(QFont.Weight.Bold)
                painter.setFont(f)
                painter.setPen(ball_color)
                # 文本框 80×24, 居中对齐 ball 上方
                tw = max(80.0, r * 1.0)
                text_rect = QRectF(bx - tw / 2, by - ball_r - 28, tw, 24)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter,
                                 self._pressed_key_display)

    # ── 状态控制 (由 RunController 调用) ──

    def set_stick_visual(self, state: str, x: float = 0.0, y: float = 0.0,
                         sticking_progress: float = 0.0):
        """RunController 每帧调; state ∈ idle/active/sticking
        - x/y ∈ [-1,1] 屏幕坐标系 (sticking 状态下是单位向量, 表示边缘方向)
        - sticking_progress ∈ [0,1] 仅在 sticking 状态有意义: 0=刚出圆边缘, 1=即将释放"""
        if state not in ('idle', 'active', 'sticking'):
            state = 'idle'
        sticking_progress = max(0.0, min(1.0, sticking_progress))
        if (state == self._state and (x, y) == self._value
                and sticking_progress == self._sticking_progress):
            return
        self._state = state
        self._value = (x, y)
        self._sticking_progress = sticking_progress
        self.update()

    def set_pressed_action(self, action: str | None, key_display: str = ''):
        """RunController: 鼠标按键触发时调; action ∈ {lclick/rclick/mclick/...} | None
        - action=None: 清除按下状态, ball 回默认色, 不显示键文本
        - 否则: ball 用 ACTION_COLORS[action], 在 ball 上方显示 key_display"""
        if action == self._pressed_action and key_display == self._pressed_key_display:
            return
        self._pressed_action = action
        self._pressed_key_display = key_display or ''
        self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        movable = (mode == 'edit')
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)
        self._resize_handle.setVisible(movable)
        if mode == 'edit':
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        # 切到 run 时重置状态; 切回 edit 时也清掉小球
        self._state = 'idle'
        self._value = (0.0, 0.0)
        self._sticking_progress = 0.0
        self._pressed_action = None
        self._pressed_key_display = ''
        self.update()

    # ── 编辑交互 ──

    def itemChange(self, change, value):
        """拖拽时网格吸附 — 与 TouchButtonItem 同样的中心原点对齐"""
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
        """双击 → 打开编辑器"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resize_to(self, w: float, h: float):
        """缩放回调 — 强制方形 (摇杆是圆, w == h)"""
        gs = self.scene().grid_size if self.scene() else DEFAULT_GRID_SIZE
        size = max(gs * 2, min(w, h))   # 至少 2 网格
        self.prepareGeometryChange()
        self.data.w = size
        self.data.h = size
        self._update_resize_handle_pos()
        self.update()
        self.data_changed.emit()

    def _update_resize_handle_pos(self):
        self._resize_handle.setPos(self.data.w - _RESIZE_INSET, self.data.h - _RESIZE_INSET)

    def _build_tooltip(self) -> str:
        sid = "左摇杆" if self.data.stick_id == STICK_ID_LEFT else "右摇杆"
        return f"{sid}\n双击编辑"
