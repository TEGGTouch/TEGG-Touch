"""
TEGG Touch 蛋挞 (PyQt6) - gp_wheel_item.py
方向盘 QGraphicsObject — 方形 N×N + 两侧浮挂 LT/RT:
  中央 N×N = 圆角大方块, 也是唯一的鼠标交互区 (steering 输入)
  左侧 1×N = LT 视觉进度条 (无交互, 仅视觉)
  右侧 1×N = RT 视觉进度条 (无交互, 仅视觉)
默认 2×2 grid (200×200), 可缩放 (强制方形, 最小 2 格)。
编辑模式: 显示方形外框 + 缩放手柄;
运行模式: 隐藏外框, 仅方向盘旋转 + LT/RT 视觉跟随。
"""

import math
import os

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF, QByteArray, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from core.constants import (
    DEFAULT_GRID_SIZE, BTN_MARGIN, APP_DIR,
    COLOR_GP_BTN_BG, COLOR_GP_BTN_BORDER, COLOR_GP_BTN_TEXT,
    DEFAULT_WHEEL_STYLE, ACTION_COLORS,
)
from core.i18n import get_font
from models.gamepad_model import GamepadWheelData


# ── 方向盘 SVG 渲染 + 缓存 ──
# 两张 SVG 叠加: wheel_fill 用按钮 bg 色填充, wheel_stroke 用用户色描边
_SVG_PLACEHOLDER_COLOR = "#FFCB31"
_WHEEL_FILL_SVG = "wheel_fill.svg"
_WHEEL_STROKE_SVG = "wheel_stroke.svg"
_WHEEL_RENDER_SIZE = 512    # 高分辨率一次, 运行时按需缩放
# cache key = stroke color (upper hex) → QPixmap
_WHEEL_CACHE: dict = {}


def _render_one_svg_layer(svg_file: str, color: str, painter: QPainter):
    """读 SVG, 把占位色 #FFCB31 换成 color, 渲染到 painter (painter 当前 viewbox 决定大小)"""
    path = os.path.join(APP_DIR, "assets", svg_file)
    if not os.path.exists(path):
        return False
    try:
        with open(path, 'rb') as f:
            svg_text = f.read().decode('utf-8', errors='ignore')
        svg_text = svg_text.replace(_SVG_PLACEHOLDER_COLOR, color)
        svg_text = svg_text.replace(_SVG_PLACEHOLDER_COLOR.lower(), color)
        renderer = QSvgRenderer(QByteArray(svg_text.encode('utf-8')))
        if not renderer.isValid():
            return False
        renderer.render(painter)
        return True
    except Exception:
        return False


def render_wheel_pixmap(color: str) -> QPixmap:
    """SVG 双层叠加 → QPixmap, 缓存。fill 用按钮 bg, stroke 用用户色。"""
    color = (color or DEFAULT_WHEEL_STYLE["color"]).upper()
    if color in _WHEEL_CACHE:
        return _WHEEL_CACHE[color]
    pm = QPixmap(_WHEEL_RENDER_SIZE, _WHEEL_RENDER_SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    # 1) fill 层: 用户色的同色系深暗版 (而非固定深蓝), 让方向盘永远不透且随色变
    from core import button_theme
    fill_hex = button_theme.derive_shades(color)['fill']
    fill_ok = _render_one_svg_layer(_WHEEL_FILL_SVG, fill_hex, p)
    # 2) stroke 层 (用户色) — 描边压在 fill 上面
    stroke_ok = _render_one_svg_layer(_WHEEL_STROKE_SVG, color, p)
    p.end()
    if not (fill_ok or stroke_ok):
        _WHEEL_CACHE[color] = None
        return None
    _WHEEL_CACHE[color] = pm
    return pm


def clear_wheel_render_cache():
    """设置改动后清缓存, 下次 paint 重新渲染"""
    _WHEEL_CACHE.clear()


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

# 方向盘视觉旋转角度上限 (老常量, 现已迁移到 data.max_rotation_deg, 仅作 fallback)
_MAX_WHEEL_ANGLE_DEG_FALLBACK = 180.0

# 缩放手柄距右下角内缩 (跟 gp_stick 一致)
_RESIZE_INSET = 24


class GpWheelItem(QGraphicsObject):
    """方向盘 item — 4×2 矩形, 单例 (每个 profile 最多一个)"""

    doubleClicked = pyqtSignal(object)

    def __init__(self, data: GamepadWheelData, offset_x: float = 0, offset_y: float = 0):
        super().__init__()
        self.data = data
        # 老 profile 兼容: 老版本是 4×2 (400×200) 矩形, 现在改方形 → 取 min 收缩到 2×2
        if self.data.w != self.data.h:
            side = max(2 * DEFAULT_GRID_SIZE, min(self.data.w, self.data.h))
            self.data.w = side
            self.data.h = side
        # 老 profile 默认值迁移: LT 默认从 'scroll' 改成 'buttons'; 仅在 LT 全套老默认未动时迁移,
        # 避免覆盖用户主动选 scroll 的配置
        if (self.data.lt_mode == 'scroll'
                and self.data.lt_scroll_step == 0.05
                and self.data.lt_buttons_ms == 100
                and self.data.lt_buttons_step == 0.05):
            self.data.lt_mode = 'buttons'
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._mode = 'edit'  # 'edit' | 'run'
        # run 状态: steering ∈ [-1, 1], lt/rt ∈ [0, 1], active bool
        self._steering = 0.0
        self._lt = 0.0
        self._rt = 0.0
        self._active = False
        # 方向盘样式 (variant + color); overlay_window 在加载完成后会调 apply_style 覆盖
        self._style = dict(DEFAULT_WHEEL_STYLE)
        # 设置弹窗预览专用: 实例级颜色覆盖, 不读全局 button_theme, 不污染实时场景
        self._preview_color: str | None = None
        # 轻松模式触发/释放引擎量 (0~1) → 圆心发散填充视觉
        self._easy_fill: float = 0.0
        # 编辑器预览态: 显示鼠标有效区域 (释放阈值边界) — 30% 透明蓝方块
        # _preview_release_ratio = None 时用 data.release_threshold_ratio, 不为 None 时用预览值
        self._show_release_zone: bool = False
        self._preview_release_ratio: float = None
        # marker 模式浮标位置 (0~1), None 表示该侧不画浮标
        self._lt_marker: float = None
        self._rt_marker: float = None
        # 鼠标动作按下视觉: 中心 hub 变色 + 显示键文本 (跟 gp_stick 同套语义)
        self._pressed_action: str = None       # 'lclick' | 'rclick' | ...
        self._pressed_key_display: str = ''
        # 死区预览 (玫红色, 编辑器勾选才显示)
        self._show_dead_zone: bool = False
        self._preview_dead_zone: float = None

        # Z 序: 跟摇杆同 20 (方向盘单例, 不会与其他 gp_wheel 叠)
        self.setZValue(20)
        # 编辑模式下 hover → 显示 scene tooltip (run 模式靠 polling, 不影响)
        self.setAcceptHoverEvents(True)

        # 初始位置 (像素 → scene 坐标 + 中心 offset)
        self.setPos(self._offset_x + data.x, self._offset_y + data.y)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # 缩放手柄 (强制方形, 跟 gp_stick 一致)
        from scene.resize_handle_item import ResizeHandleItem
        self._resize_handle = ResizeHandleItem(self)
        self._update_resize_handle_pos()

        # 编辑模式光标
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        # tooltip 改用 scene.show_tooltip (hoverEnterEvent 触发), 不用 Qt 默认 setToolTip

    # ── 几何 ──

    def _bar_width(self) -> float:
        """LT/RT 条宽 = 1 格 (跟随场景 grid_size)"""
        if self.scene() is not None and hasattr(self.scene(), 'grid_size'):
            return float(self.scene().grid_size)
        return float(DEFAULT_GRID_SIZE)

    def boundingRect(self) -> QRectF:
        """bounds = 左 LT (1 格) + 中央方形 (N 格) + 右 RT (1 格) + 释放区外扩
        编辑器预览态可能用更大的 ratio (slider 实时拖到 500%), 取 max 确保 zone 不被裁"""
        w = self.data.w
        bar_w = self._bar_width()
        ratio = max(1.0, self.data.release_threshold_ratio)
        if self._show_release_zone and self._preview_release_ratio is not None:
            ratio = max(ratio, self._preview_release_ratio)
        ext = (w / 2) * (ratio - 1.0) + 4
        return QRectF(-bar_w - ext, -ext,
                      w + 2 * bar_w + 2 * ext,
                      w + 2 * ext)

    def shape(self) -> QPainterPath:
        """hit-test 只在中央方形 — LT/RT 是纯视觉, 不参与鼠标交互 / 拖拽"""
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.data.w, self.data.w))
        return path

    def rect_center_local(self) -> QPointF:
        return QPointF(self.data.w / 2, self.data.w / 2)

    def rect_center_scene(self) -> QPointF:
        return self.mapToScene(self.rect_center_local())

    def half_width_scene(self) -> float:
        # scene 无缩放, 直接返回本地一半宽 (square: w == h)
        return self.data.w / 2

    def is_cursor_in_rect(self, scene_pos: QPointF) -> bool:
        """是否在中央方形内 (LT/RT 不算)"""
        local = self.mapFromScene(scene_pos)
        return (0 <= local.x() <= self.data.w
                and 0 <= local.y() <= self.data.w)

    def cursor_distance_ratio(self, scene_pos: QPointF) -> float:
        """鼠标距方形中心的切比雪夫距离 / (w/2) — 大于 release_threshold_ratio 时释放。
        用 max(|dx|, |dy|) 而非纯 X, 这样垂直方向走出方形也会触发释放
        (方形的几何切比雪夫距离 = 跟方形边的同向距离)。"""
        c = self.rect_center_scene()
        dx = abs(scene_pos.x() - c.x())
        dy = abs(scene_pos.y() - c.y())
        half = max(1.0, self.half_width_scene())
        return max(dx, dy) / half

    # ── 绘制 ──

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.data.w
        bar_w = self._bar_width()
        is_edit = (self._mode == 'edit')
        # 方向盘整体配色: 单一基色派生 (描边/填充压暗/字), 编辑态与扳机都跟它走
        from core import button_theme
        self._fam = (button_theme.derive_shades(self._preview_color)
                     if self._preview_color else button_theme.wheel())
        c_border = QColor(self._fam['border'])
        c_fill = QColor(self._fam['fill'])
        c_text = QColor(self._fam['text'])
        border_color = _BORDER_ACTIVE if self._active else c_border

        # ── LT 视觉条 (左, 浮挂在方形外, 1 格宽); marker 玫瑰红 ──
        lt_rect = QRectF(-bar_w + 6, 6, bar_w - 12, w - 12)
        self._paint_trigger_bar(painter, lt_rect, self._lt, "LT",
                                marker=self._lt_marker, marker_color="#F43F5E")

        # ── RT 视觉条 (右, 浮挂在方形外, 1 格宽); marker 琥珀黄 ──
        rt_rect = QRectF(w + 6, 6, bar_w - 12, w - 12)
        self._paint_trigger_bar(painter, rt_rect, self._rt, "RT",
                                marker=self._rt_marker, marker_color="#F59E0B")

        # ── 中央方形 (编辑模式才描边/填底; 运行模式只有方向盘图) ──
        # 右下角为直角 (匹配缩放手柄三角形); 其他三角圆角
        if is_edit:
            x = BTN_MARGIN
            y = BTN_MARGIN
            ow = w - 2 * BTN_MARGIN
            oh = ow
            r = 12
            outline_path = QPainterPath()
            outline_path.moveTo(x + r, y)
            outline_path.lineTo(x + ow - r, y)
            outline_path.arcTo(x + ow - 2 * r, y, 2 * r, 2 * r, 90, -90)
            outline_path.lineTo(x + ow, y + oh)             # 右下: 直角
            outline_path.lineTo(x + r, y + oh)
            outline_path.arcTo(x, y + oh - 2 * r, 2 * r, 2 * r, -90, -90)
            outline_path.lineTo(x, y + r)
            outline_path.arcTo(x, y, 2 * r, 2 * r, 180, -90)
            outline_path.closeSubpath()
            border_w_v = 3 if self._active else 2
            painter.setPen(QPen(border_color, border_w_v))
            painter.setBrush(QBrush(c_fill))
            painter.drawPath(outline_path)

            # 中心死区: 编辑器勾选「显示死区」后才画 — 玫红色双竖线 + 50% 半透明填充
            if self._show_dead_zone:
                dz = (self._preview_dead_zone
                      if self._preview_dead_zone is not None
                      else getattr(self.data, 'dead_zone', 0.0))
                dz = max(0.0, min(0.95, float(dz)))
                if dz > 0:
                    cx_l = w / 2
                    dz_x = (w / 2) * dz
                    top_y = BTN_MARGIN + 4
                    bot_y = w - BTN_MARGIN - 4
                    rose_fill = QColor("#F43F5E")
                    rose_fill.setAlphaF(0.5)
                    rose_line = QColor("#F43F5E")
                    # 内部 50% 半透明填充
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(rose_fill))
                    painter.drawRect(QRectF(cx_l - dz_x, top_y,
                                            2 * dz_x, bot_y - top_y))
                    # 两侧虚线 (玫红 2px)
                    painter.setPen(QPen(rose_line, 2, Qt.PenStyle.DashLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawLine(QPointF(cx_l - dz_x, top_y),
                                     QPointF(cx_l - dz_x, bot_y))
                    painter.drawLine(QPointF(cx_l + dz_x, top_y),
                                     QPointF(cx_l + dz_x, bot_y))

        # ── 鼠标有效区域预览 (编辑器勾选时) — 蓝色 30% 透明方块, 边长 = w × ratio ──
        # 放在方向盘之前画, 让方向盘 + 外框压在上面, 不挡视觉重心
        if self._show_release_zone:
            ratio = (self._preview_release_ratio
                     if self._preview_release_ratio is not None
                     else self.data.release_threshold_ratio)
            ratio = max(1.0, float(ratio))
            cx_l = w / 2
            half = (w / 2) * ratio
            zone = QRectF(cx_l - half, cx_l - half, 2 * half, 2 * half)
            zone_color = QColor("#3B82F6")
            zone_color.setAlphaF(0.30)
            painter.setPen(QPen(QColor("#3B82F6"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(zone_color))
            painter.drawRect(zone)

        # ── 方向盘 (SVG 渲染, variant + color 由设置控制, 跟随 steering 旋转) ──
        cx = w / 2
        cy = w / 2
        r = w / 2 - BTN_MARGIN
        max_deg = getattr(self.data, 'max_rotation_deg', _MAX_WHEEL_ANGLE_DEG_FALLBACK) or _MAX_WHEEL_ANGLE_DEG_FALLBACK
        angle_deg = self._steering * max_deg

        if r > 0:
            color = self._preview_color or self._style.get("color", DEFAULT_WHEEL_STYLE["color"])
            pixmap = render_wheel_pixmap(color)

            if pixmap is not None:
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(angle_deg)
                # active 100%, idle 50% (同色, 透明度区分)
                painter.setOpacity(1.0 if self._active else 0.5)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawPixmap(
                    QRectF(-r, -r, 2 * r, 2 * r),
                    pixmap,
                    QRectF(pixmap.rect()),
                )
                painter.restore()
            else:
                # 回退: SVG 加载失败, 画一个简化的圆 (idle/active 同色, 透明度区分)
                fallback = QColor(color if isinstance(color, str) else "#3B82F6")
                fallback.setAlphaF(1.0 if self._active else 0.5)
                painter.setPen(QPen(fallback, max(3.0, r * 0.08)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), r - 4, r - 4)

        # ── 轻松模式: 引擎量 fill → 从圆心发散的半透明实心圆 (随方向盘配色) ──
        if self._easy_fill > 0.001 and r > 0:
            fc = QColor(self._fam['border'])
            fc.setAlphaF(0.38)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fc))
            fr = r * max(0.0, min(1.0, self._easy_fill))
            painter.drawEllipse(QPointF(cx, cy), fr, fr)

        # ── 鼠标动作按下视觉: 方向盘中心 hub 实底着色 + 键文本 ──
        if self._pressed_action and r > 0:
            hub_r = r * 0.22
            hub_color = QColor(ACTION_COLORS.get(self._pressed_action, "#F59E0B"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(hub_color))
            painter.drawEllipse(QPointF(cx, cy), hub_r, hub_r)
            if self._pressed_key_display:
                # 键文本 — 居中显示在 hub 内, 文本太长则上方溢出
                fn = get_font()
                f = QFont(fn)
                f.setPixelSize(max(11, int(hub_r * 0.45)))
                f.setWeight(QFont.Weight.Bold)
                painter.setFont(f)
                # 白字, 黑色 luminance 用 ACTION_COLORS 决定 (大多是深色 → 用白字)
                painter.setPen(QColor("#FFFFFF"))
                tw = max(hub_r * 2, 80.0)
                text_rect = QRectF(cx - tw / 2, cy - 10, tw, 20)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter,
                                 self._pressed_key_display)

        # ── 名称 (编辑模式) ──
        if is_edit and self.data.name:
            fn = get_font()
            f = QFont(fn)
            f.setPixelSize(12)
            painter.setFont(f)
            painter.setPen(c_text)
            painter.drawText(
                QRectF(0, 4, w, 16),
                Qt.AlignmentFlag.AlignCenter, self.data.name)

    def _paint_trigger_bar(self, painter: QPainter, rect: QRectF,
                           value: float, label: str,
                           marker: float = None, marker_color: str = None):
        """绘制单个 LT / RT 进度条 (底部往上填充) — 边框/底色/填充/字 全跟方向盘基色派生。
        marker: 浮标位置 0~1, None 不画; marker_color: 浮标线颜色 (hex)"""
        fam = getattr(self, '_fam', None) or {'fill': '#1A1E2E', 'border': '#3B82F6', 'text': '#93C5FD'}
        c_border = QColor(fam['border'])
        c_bg = QColor(fam['fill'])
        c_text = QColor(fam['text'])
        # 背景
        painter.setPen(QPen(c_border, 1))
        painter.setBrush(QBrush(c_bg))
        painter.drawRoundedRect(rect, 6, 6)

        # 填充 (从底往上) — 用基色(描边色)
        v = max(0.0, min(1.0, value))
        if v > 0.01:
            fill_h = rect.height() * v
            fill_rect = QRectF(rect.x(), rect.bottom() - fill_h,
                                rect.width(), fill_h)
            color = QColor(c_border)
            color.setAlphaF(0.85)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(fill_rect, 6, 6)

        # 浮标线 (marker 模式专用): 4px 横线, 位置 = 0(底) ~ 1(顶)
        if marker is not None and marker_color:
            m = max(0.0, min(1.0, float(marker)))
            m_y = rect.bottom() - m * rect.height()
            painter.setPen(QPen(QColor(marker_color), 4, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.FlatCap))
            painter.drawLine(QPointF(rect.x() + 2, m_y),
                             QPointF(rect.right() - 2, m_y))

        # 标签 (顶部) + 当前值 (底部)
        fn = get_font()
        f = QFont(fn)
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.Bold)
        painter.setFont(f)
        painter.setPen(c_text)
        painter.drawText(
            QRectF(rect.x(), rect.y() + 4, rect.width(), 20),
            Qt.AlignmentFlag.AlignCenter, label)
        # 当前 % 值
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Normal)
        painter.setFont(f)
        painter.setPen(c_text)
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

    def set_easy_fill(self, fill: float):
        """轻松模式: 触发/释放引擎量 (0~1), 圆心发散填充视觉。"""
        fill = max(0.0, min(1.0, float(fill)))
        if abs(fill - self._easy_fill) < 0.001:
            return
        self._easy_fill = fill
        self.update()

    def set_pressed_action(self, action: str, key_display: str = ''):
        """RunController: 鼠标动作触发时调; action ∈ {lclick/rclick/...} | None;
        None = 清除按下视觉 (中心 hub 恢复); 否则按 ACTION_COLORS 着色 + 显示键文本"""
        if action == self._pressed_action and key_display == self._pressed_key_display:
            return
        self._pressed_action = action
        self._pressed_key_display = key_display or ''
        self.update()

    def set_markers(self, lt: float, rt: float):
        """run controller 推: marker 浮标位置 (0~1, None 隐藏)
        LT 浮标 = 玫瑰红, RT 浮标 = 琥珀黄"""
        if lt == self._lt_marker and rt == self._rt_marker:
            return
        self._lt_marker = lt
        self._rt_marker = rt
        self.update()

    def set_show_release_zone(self, flag: bool):
        """编辑器: 是否在方向盘上叠加显示鼠标释放区域 (蓝色 30% 透明方块)"""
        self._show_release_zone = bool(flag)
        self.prepareGeometryChange()  # zone 可能超过当前 bounds, 通知 Qt 重算
        self.update()

    def set_preview_release_ratio(self, ratio):
        """编辑器拖滑块时实时预览; None 表示用 data.release_threshold_ratio"""
        self._preview_release_ratio = ratio
        self.prepareGeometryChange()
        self.update()

    def set_show_dead_zone(self, flag: bool):
        """编辑器: 是否在方向盘上叠加显示死区 (玫红线 + 50% 半透明填充)"""
        self._show_dead_zone = bool(flag)
        self.update()

    def set_preview_dead_zone(self, pct):
        """编辑器拖滑块时实时预览死区宽度; None 表示用 data.dead_zone"""
        self._preview_dead_zone = pct
        self.update()

    def apply_style(self, style: dict):
        """从设置弹窗收到新样式 (只剩 color, 老 variant 字段静默忽略); 调用方负责清模块缓存"""
        if not isinstance(style, dict):
            return
        merged = dict(DEFAULT_WHEEL_STYLE)
        v = style.get("color")
        if isinstance(v, str) and v.startswith("#") and len(v) == 7:
            merged["color"] = v.upper()
        self._style = merged
        self.update()

    def set_preview_color(self, color: str | None):
        """设置弹窗预览专用: 用实例级颜色覆盖渲染 (描边/填充/扳机/字 全派生), 不读全局。"""
        self._preview_color = color.upper() if isinstance(color, str) else None
        self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        movable = (mode == 'edit')
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)
        # 缩放手柄只在编辑模式可见
        if self._resize_handle is not None:
            self._resize_handle.setVisible(movable)
        if mode == 'edit':
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        # 模式切换重置视觉
        self._steering = 0.0
        self._lt = 0.0
        self._rt = 0.0
        self._active = False
        self._lt_marker = None
        self._rt_marker = None
        self._pressed_action = None
        self._pressed_key_display = ''
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

    def resize_to(self, w: float, h: float):
        """缩放回调 — 强制方形 (鼠标区是方块, w == h)"""
        gs = self.scene().grid_size if self.scene() else DEFAULT_GRID_SIZE
        size = max(2 * gs, min(w, h))   # 至少 2 网格
        self.prepareGeometryChange()
        self.data.w = size
        self.data.h = size
        self._update_resize_handle_pos()
        self.update()

    def _update_resize_handle_pos(self):
        self._resize_handle.setPos(self.data.w - _RESIZE_INSET,
                                   self.data.w - _RESIZE_INSET)

    def _build_tooltip(self) -> str:
        mode_label = {'scroll': '滚轮', 'vertical': '垂直位移', 'buttons': '左右键'}
        lines = ["方向盘"]
        lines.append(f"释放阈值: {int(self.data.release_threshold_ratio * 100)}% 半宽")
        lines.append(f"中心死区: {int(getattr(self.data, 'dead_zone', 0.10) * 100)}%")
        lines.append(f"灵敏度: {'平方' if self.data.sensitivity_curve == 'square' else '线性'}")
        lines.append(f"视觉旋转: ±{int(getattr(self.data, 'max_rotation_deg', 180))}°")
        lines.append("")
        lt_m = mode_label.get(self.data.lt_mode, self.data.lt_mode)
        rt_m = mode_label.get(self.data.rt_mode, self.data.rt_mode)
        # vertical 模式额外显示 pct
        if self.data.lt_mode == 'vertical':
            lt_m = f"{lt_m} ({int(self.data.lt_vertical_pct * 100)}%)"
        if self.data.rt_mode == 'vertical':
            rt_m = f"{rt_m} ({int(self.data.rt_vertical_pct * 100)}%)"
        lines.append(f"LT: {lt_m}")
        lines.append(f"RT: {rt_m}")
        lines.append("")
        lines.append("双击编辑｜可拖动｜右下角缩放")
        return "\n".join(lines)

    # ── Hover (编辑模式 scene tooltip) ──

    def hoverEnterEvent(self, event):
        if self._mode == 'edit':
            scene = self.scene()
            if scene and hasattr(scene, 'show_tooltip'):
                scene.show_tooltip(self._build_tooltip(), event.scenePos())
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        if self._mode == 'edit':
            scene = self.scene()
            if scene and hasattr(scene, 'move_tooltip'):
                scene.move_tooltip(event.scenePos())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        scene = self.scene()
        if scene and hasattr(scene, 'hide_tooltip'):
            scene.hide_tooltip()
        super().hoverLeaveEvent(event)
