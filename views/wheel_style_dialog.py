"""
TEGG Touch 蛋挞 (PyQt6) - wheel_style_dialog.py
轮盘样式管理弹窗 — 左侧缩略图选择 + 右侧1:1预览与设置。
"""

import math
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QFrame, QApplication, QCheckBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QSize
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPainterPath,
)

from core.i18n import t, get_font
from core.constants import (
    WHEEL_INNER_RADIUS, WHEEL_OUTER_RADIUS,
    WHEEL_INNER_RADIUS_LARGE, WHEEL_OUTER_RADIUS_LARGE,
    WHEEL_RING_INNER, WHEEL_RING_OUTER,
    WHEEL_TRIPLE_INNER_RING_INNER, WHEEL_TRIPLE_INNER_RING_OUTER,
    WHEEL_TRIPLE_OUTER_RING_INNER, WHEEL_TRIPLE_OUTER_RING_OUTER,
    WHEEL_TRIPLE_SECTOR_INNER, WHEEL_TRIPLE_SECTOR_OUTER,
    WHEEL_DUAL_CENTER_RING_INNER, WHEEL_DUAL_CENTER_RING_OUTER,
    WHEEL_DUAL_INNER_SECTOR_INNER, WHEEL_DUAL_INNER_SECTOR_OUTER,
    WHEEL_DUAL_OUTER_SECTOR_INNER, WHEEL_DUAL_OUTER_SECTOR_OUTER,
    WHEEL_VISUAL_INSET, WHEEL_GAP_PX,
    WHEEL_SECTOR_COUNT, WHEEL_SECTORS_DEF,
)

# ── 颜色 ──
C_BG = "#2D2D2D"
C_CARD_NORMAL = "#3A3A3A"
C_CARD_SELECTED = "#F43F5E"
C_CARD_HOVER = "#505050"
C_CLOSE = "#6E1E1E"
C_CLOSE_H = "#8B2020"
C_SAVE_BG = "#0C4A6E"
C_SAVE_H = "#0284C7"
C_SECTOR_FILL = "#222222"
C_SECTOR_BORDER = "#555555"
C_SECTOR_HIDDEN = "#0D0D0D"
C_RING_FILL = "#222222"
C_RING_BORDER = "#555555"
C_RING_HIDDEN = "#0D0D0D"

# ── 图标字体 ──
_ICON_FONT = None

def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return _ICON_FONT
    from PyQt6.QtGui import QFontDatabase
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""
    return _ICON_FONT

def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── 带勾号 Checkbox (参考 voice_settings_dialog._CheckToggle) ──
C_ACCENT = "#F43F5E"  # 玫瑰红

class _CheckToggle(QWidget):
    """带勾号的自定义 checkbox — 点击切换选中状态。"""
    toggled = pyqtSignal(bool)

    def __init__(self, text, fn, checked=True, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._box = QLabel()
        self._box.setFixedSize(18, 18)
        self._box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if _ICON_FONT:
            self._box.setFont(_make_font(_ICON_FONT, 13))
        else:
            self._box.setFont(_make_font(fn, 13, bold=True))
        lay.addWidget(self._box)

        lbl = QLabel(text)
        lbl.setFont(_make_font(fn, 14))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(lbl)

        self._update_style()

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self._update_style()
            self.toggled.emit(checked)

    def setVisible(self, visible):
        super().setVisible(visible)

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._update_style()
        self.toggled.emit(self._checked)
        super().mousePressEvent(event)

    def _update_style(self):
        if self._checked:
            icon = "\uE73E" if _ICON_FONT else "\u2713"
            self._box.setText(icon)
            self._box.setStyleSheet(
                f"background: {C_ACCENT}; color: #FFF;"
                " border-radius: 4px;"
            )
        else:
            self._box.setText("")
            self._box.setStyleSheet(
                "background: #333; color: transparent;"
                " border: 1px solid #666; border-radius: 4px;"
            )


# ── 轮盘类型定义 ──
WHEEL_TYPES = [
    {
        'id': 'small',
        'r_inner': WHEEL_INNER_RADIUS,
        'r_outer': WHEEL_OUTER_RADIUS,
        'has_ring': False,
        'has_inner_ring': False,
    },
    {
        'id': 'large',
        'r_inner': WHEEL_INNER_RADIUS_LARGE,
        'r_outer': WHEEL_OUTER_RADIUS_LARGE,
        'has_ring': True,
        'has_inner_ring': False,
    },
    {
        'id': 'double',
        'r_inner': WHEEL_TRIPLE_SECTOR_INNER,
        'r_outer': WHEEL_TRIPLE_SECTOR_OUTER,
        'has_ring': True,
        'has_inner_ring': True,
        'ring_inner': WHEEL_TRIPLE_OUTER_RING_INNER,
        'ring_outer': WHEEL_TRIPLE_OUTER_RING_OUTER,
        'inner_ring_inner': WHEEL_TRIPLE_INNER_RING_INNER,
        'inner_ring_outer': WHEEL_TRIPLE_INNER_RING_OUTER,
    },
    {
        'id': 'dual',
        'r_inner': WHEEL_DUAL_INNER_SECTOR_INNER,
        'r_outer': WHEEL_DUAL_OUTER_SECTOR_OUTER,   # 最外径用于确定预览大小
        'has_ring': True,
        'has_inner_ring': False,
        'has_outer_sectors': True,                    # 标记有外八向
        'ring_inner': WHEEL_DUAL_CENTER_RING_INNER,
        'ring_outer': WHEEL_DUAL_CENTER_RING_OUTER,
        'inner_sector_inner': WHEEL_DUAL_INNER_SECTOR_INNER,
        'inner_sector_outer': WHEEL_DUAL_INNER_SECTOR_OUTER,
        'outer_sector_inner': WHEEL_DUAL_OUTER_SECTOR_INNER,
        'outer_sector_outer': WHEEL_DUAL_OUTER_SECTOR_OUTER,
    },
]

def _wheel_type_name(type_id):
    return t(f"wheel_style.type_{type_id}")


# ═══════════════════════════════════════════════════════
# 路径构建工具函数
# ═══════════════════════════════════════════════════════

def _build_ring_path(cx, cy, r_inner, r_outer):
    outer = QPainterPath()
    outer.addEllipse(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2)
    inner = QPainterPath()
    inner.addEllipse(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2)
    return outer.subtracted(inner)


def _half_gap_angle(radius, gap_px):
    if radius <= 0 or gap_px <= 0:
        return 0
    return math.degrees(math.atan2(gap_px / 2, radius))


def _build_sector_path(cx, cy, r_inner, r_outer, start_angle, span_angle, gap_px=0):
    go = _half_gap_angle(r_outer, gap_px)
    gi = _half_gap_angle(r_inner, gap_px)
    os_ = start_angle + go
    os_span = span_angle - 2 * go
    is_ = start_angle + gi
    is_span = span_angle - 2 * gi

    outer_rect = QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2)
    inner_rect = QRectF(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2)

    path = QPainterPath()
    path.arcMoveTo(outer_rect, os_)
    path.arcTo(outer_rect, os_, os_span)

    ie = math.radians(is_ + is_span)
    ix = cx + r_inner * math.cos(ie)
    iy = cy - r_inner * math.sin(ie)
    path.lineTo(ix, iy)
    path.arcTo(inner_rect, is_ + is_span, -is_span)
    path.closeSubpath()
    return path


# ═══════════════════════════════════════════════════════
# _WheelPreview — 轮盘预览绘制控件 (缩略图 & 1:1)
# ═══════════════════════════════════════════════════════

class _WheelPreview(QWidget):
    """绘制轮盘预览，支持缩放和点击交互。

    simplified=True: 缩略图模式 — 无描边、无文字、纯形状
    accent=True: 选中态 — 形状变玫瑰红
    """

    area_clicked = pyqtSignal(str)  # 'ring' 或 'sector_0'..'sector_7'

    def __init__(self, wtype, scale=1.0, interactive=False,
                 simplified=False, parent=None):
        super().__init__(parent)
        self._wtype = wtype
        self._scale = scale
        self._interactive = interactive
        self._simplified = simplified
        self._accent = False
        self._center_ring_visible = True
        self._middle_ring_visible = True
        self._hover_area = None

        ri = wtype['r_inner']
        ro = wtype['r_outer']
        pad = 4 if simplified else 20
        diameter = int(ro * 2 * scale) + pad
        self.setFixedSize(diameter, diameter)

        if interactive:
            self.setMouseTracking(True)

    def set_center_ring_visible(self, visible):
        self._center_ring_visible = visible
        self.update()

    def set_middle_ring_visible(self, visible):
        self._middle_ring_visible = visible
        self.update()

    def set_accent(self, on: bool):
        self._accent = on
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._scale
        cx = self.width() / 2
        cy = self.height() / 2

        wt = self._wtype
        ri = wt['r_inner'] * s
        ro = wt['r_outer'] * s
        vi = ri + WHEEL_VISUAL_INSET * s
        vo = ro - WHEEL_VISUAL_INSET * s
        gap = WHEEL_GAP_PX * s

        # 简化模式的填充色 — 始终深灰
        if self._simplified:
            fill_color = QColor("#252525")

        # dual 模式: 内八向用 inner_sector 半径，外八向用 outer_sector 半径
        is_dual = wt.get('has_outer_sectors', False)
        if is_dual:
            inner_vi = wt['inner_sector_inner'] * s + WHEEL_VISUAL_INSET * s
            inner_vo = wt['inner_sector_outer'] * s - WHEEL_VISUAL_INSET * s
            outer_vi = wt['outer_sector_inner'] * s + WHEEL_VISUAL_INSET * s
            outer_vo = wt['outer_sector_outer'] * s - WHEEL_VISUAL_INSET * s
        else:
            inner_vi, inner_vo = vi, vo
            outer_vi, outer_vo = None, None

        # 绘制8个扇面 (内八向)
        span = 360.0 / WHEEL_SECTOR_COUNT
        for i, sd in enumerate(WHEEL_SECTORS_DEF):
            start = sd['angle'] - span / 2
            path = _build_sector_path(cx, cy, inner_vi, inner_vo, start, span, gap)

            if self._simplified:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(fill_color))
            else:
                area_id = f'sector_{i}'
                if self._hover_area == area_id:
                    p.setBrush(QBrush(QColor("#0284C7")))
                    p.setPen(QPen(QColor("#026AA2"), max(1, 2 * s)))
                else:
                    p.setBrush(QBrush(QColor(C_SECTOR_FILL)))
                    p.setPen(QPen(QColor(C_SECTOR_BORDER), max(1, 2 * s)))
            p.drawPath(path)

            # 扇面文字 (简化模式不画)
            if not self._simplified:
                mid_deg = sd['angle']
                mid_r = (inner_vi + inner_vo) / 2
                tx = cx + mid_r * math.cos(math.radians(mid_deg))
                ty = cy - mid_r * math.sin(math.radians(mid_deg))
                fn = get_font()
                p.setFont(_make_font(fn, max(6, int(10 * s)), bold=True))
                p.setPen(QColor("#FFFFFF"))
                ts = max(10, int(24 * s))
                p.drawText(QRectF(tx - ts, ty - ts / 2, ts * 2, ts),
                           Qt.AlignmentFlag.AlignCenter, sd['name'])

        # 绘制外八向扇面 (仅 dual 模式)
        if is_dual and outer_vi is not None:
            for i, sd in enumerate(WHEEL_SECTORS_DEF):
                start = sd['angle'] - span / 2
                path = _build_sector_path(cx, cy, outer_vi, outer_vo, start, span, gap)

                if self._simplified:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(fill_color))
                else:
                    area_id = f'outer_{i}'
                    if self._hover_area == area_id:
                        p.setBrush(QBrush(QColor("#0284C7")))
                        p.setPen(QPen(QColor("#026AA2"), max(1, 2 * s)))
                    else:
                        p.setBrush(QBrush(QColor(C_SECTOR_FILL)))
                        p.setPen(QPen(QColor(C_SECTOR_BORDER), max(1, 2 * s)))
                p.drawPath(path)

                if not self._simplified:
                    mid_deg = sd['angle']
                    mid_r = (outer_vi + outer_vo) / 2
                    tx = cx + mid_r * math.cos(math.radians(mid_deg))
                    ty = cy - mid_r * math.sin(math.radians(mid_deg))
                    p.setFont(_make_font(fn, max(6, int(9 * s)), bold=True))
                    p.setPen(QColor("#FFFFFF"))
                    ts = max(10, int(24 * s))
                    p.drawText(QRectF(tx - ts, ty - ts / 2, ts * 2, ts),
                               Qt.AlignmentFlag.AlignCenter, sd['name'])

        # 绘制中心环 (单环/三环)
        if wt['has_ring']:
            # 外环(中环): 从 wtype 取半径，large 用默认常量
            r_ring_i = wt.get('ring_inner', WHEEL_RING_INNER)
            r_ring_o = wt.get('ring_outer', WHEEL_RING_OUTER)
            rri = r_ring_i * s + WHEEL_VISUAL_INSET * s
            rro = r_ring_o * s - WHEEL_VISUAL_INSET * s
            ring_path = _build_ring_path(cx, cy, rri, rro)

            if self._simplified:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(fill_color))
                p.drawPath(ring_path)
            else:
                # 双环: ring 位置 = 中二环 → _middle_ring_visible
                # 单环: ring 位置 = 中心环 → _center_ring_visible
                is_double = wt.get('has_inner_ring', False)
                ring_vis = self._middle_ring_visible if is_double else self._center_ring_visible
                if ring_vis:
                    if self._hover_area == 'ring':
                        p.setBrush(QBrush(QColor("#0284C7")))
                        p.setPen(QPen(QColor("#026AA2"), max(1, 2 * s)))
                    else:
                        p.setBrush(QBrush(QColor(C_RING_FILL)))
                        p.setPen(QPen(QColor(C_RING_BORDER), max(1, 2 * s)))
                    p.drawPath(ring_path)

        # 绘制内环 (仅双环模式) — 最内位置 = 中心环
        if wt.get('has_inner_ring'):
            ir_i = wt['inner_ring_inner'] * s + WHEEL_VISUAL_INSET * s
            ir_o = wt['inner_ring_outer'] * s - WHEEL_VISUAL_INSET * s
            inner_path = _build_ring_path(cx, cy, ir_i, ir_o)

            if self._simplified:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(fill_color))
                p.drawPath(inner_path)
            elif self._center_ring_visible:
                if self._hover_area == 'inner_ring':
                    p.setBrush(QBrush(QColor("#0284C7")))
                    p.setPen(QPen(QColor("#026AA2"), max(1, 2 * s)))
                else:
                    p.setBrush(QBrush(QColor(C_RING_FILL)))
                    p.setPen(QPen(QColor(C_RING_BORDER), max(1, 2 * s)))
                p.drawPath(inner_path)

        p.end()

    def mouseMoveEvent(self, event):
        if not self._interactive:
            return
        area = self._hit_test(event.position())
        if area != self._hover_area:
            self._hover_area = area
            self.setCursor(Qt.CursorShape.PointingHandCursor if area else Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, event):
        if not self._interactive or event.button() != Qt.MouseButton.LeftButton:
            return
        area = self._hit_test(event.position())
        if area:
            self.area_clicked.emit(area)

    def leaveEvent(self, event):
        if self._hover_area:
            self._hover_area = None
            self.update()

    def _hit_test(self, pos):
        """检测鼠标点击了哪个区域"""
        s = self._scale
        cx = self.width() / 2
        cy = self.height() / 2
        wt = self._wtype
        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = math.sqrt(dx * dx + dy * dy)

        # 内环 (三环模式)
        if wt.get('has_inner_ring'):
            ir_i = wt['inner_ring_inner'] * s
            ir_o = wt['inner_ring_outer'] * s
            if ir_i <= dist <= ir_o:
                return 'inner_ring'

        # 中心环
        if wt['has_ring']:
            rri = wt.get('ring_inner', WHEEL_RING_INNER) * s
            rro = wt.get('ring_outer', WHEEL_RING_OUTER) * s
            if rri <= dist <= rro:
                return 'ring'

        # 外八向扇面 (dual 模式 — 先检测外层再检测内层)
        if wt.get('has_outer_sectors', False):
            oi = wt['outer_sector_inner'] * s
            oo = wt['outer_sector_outer'] * s
            if oi <= dist <= oo:
                angle = math.degrees(math.atan2(-dy, dx)) % 360
                span = 360.0 / WHEEL_SECTOR_COUNT
                for i, sd in enumerate(WHEEL_SECTORS_DEF):
                    center = sd['angle']
                    start = (center - span / 2) % 360
                    end = (center + span / 2) % 360
                    if start < end:
                        if start <= angle < end:
                            return f'outer_{i}'
                    else:
                        if angle >= start or angle < end:
                            return f'outer_{i}'
            # 内八向 (dual 模式用 inner_sector 半径)
            ii = wt['inner_sector_inner'] * s
            io = wt['inner_sector_outer'] * s
            if ii <= dist <= io:
                angle = math.degrees(math.atan2(-dy, dx)) % 360
                span = 360.0 / WHEEL_SECTOR_COUNT
                for i, sd in enumerate(WHEEL_SECTORS_DEF):
                    center = sd['angle']
                    start = (center - span / 2) % 360
                    end = (center + span / 2) % 360
                    if start < end:
                        if start <= angle < end:
                            return f'sector_{i}'
                    else:
                        if angle >= start or angle < end:
                            return f'sector_{i}'
        else:
            # 普通扇面
            ri = wt['r_inner'] * s
            ro = wt['r_outer'] * s
            if ri <= dist <= ro:
                angle = math.degrees(math.atan2(-dy, dx)) % 360
                span = 360.0 / WHEEL_SECTOR_COUNT
                for i, sd in enumerate(WHEEL_SECTORS_DEF):
                    center = sd['angle']
                    start = (center - span / 2) % 360
                    end = (center + span / 2) % 360
                    if start < end:
                        if start <= angle < end:
                            return f'sector_{i}'
                    else:
                        if angle >= start or angle < end:
                            return f'sector_{i}'
        return None


# ═══════════════════════════════════════════════════════
# _TypeCard — 左侧轮盘类型选择卡片
# ═══════════════════════════════════════════════════════

class _TypeCard(QFrame):
    """轮盘类型选择卡片 — 方形 icon + 下方文字标签"""
    clicked = pyqtSignal(str)  # type_id

    ICON_SIZE = 96       # 方形图标区
    CARD_W = 110         # 总宽
    CARD_H = 126         # 总高（icon + label）

    def __init__(self, wtype, parent=None):
        super().__init__(parent)
        self._type_id = wtype['id']
        self._selected = False
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 5, 0, 3)
        lay.setSpacing(4)

        # 方形 icon 容器
        icon_frame = QFrame()
        icon_frame.setObjectName("tc_icon")
        icon_frame.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        icon_lay = QVBoxLayout(icon_frame)
        icon_lay.setContentsMargins(0, 0, 0, 0)
        icon_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 简化缩略图（居中在 icon 方框内）
        self._preview = _WheelPreview(wtype, scale=0.18, interactive=False,
                                       simplified=True)
        self._preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        icon_lay.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignCenter)

        self._icon_frame = icon_frame
        icon_frame.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(icon_frame, 0, Qt.AlignmentFlag.AlignCenter)

        # 文字标签
        self._label = QLabel(_wheel_type_name(wtype['id']))
        fn = get_font()
        self._label.setFont(_make_font(fn, 16))
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._label)

        self._apply_style()

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        sel = self._selected
        # 外框 — 选中仅边框变色，底色不变
        border = C_CARD_SELECTED if sel else "transparent"
        self.setStyleSheet(f"""
            _TypeCard {{
                background: {C_CARD_NORMAL};
                border: 2px solid {border};
                border-radius: 8px;
            }}
            _TypeCard:hover {{
                background: {C_CARD_HOVER};
            }}
        """)
        # icon 方框背景 — 透明简洁
        self._icon_frame.setStyleSheet("""
            QFrame#tc_icon {
                background: transparent;
                border: none;
            }
        """)
        # 标签颜色
        lbl_color = "#F43F5E" if sel else "#AAA"
        self._label.setStyleSheet(f"color: {lbl_color}; background: transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._type_id)


# ═══════════════════════════════════════════════════════
# WheelStyleDialog — 主弹窗
# ═══════════════════════════════════════════════════════

class WheelStyleDialog(QDialog):
    """轮盘样式管理弹窗"""

    settings_changed = pyqtSignal(dict)

    WIN_W = 920
    WIN_H = 650
    PAD = 20
    INFO_W = 220

    def __init__(self, wheel_mode='small', center_ring_visible=True,
                 middle_ring_visible=True, parent=None):
        super().__init__(parent)
        # 兼容旧调用: 如果传入 bool 则转换
        if isinstance(wheel_mode, bool):
            wheel_mode = 'large' if wheel_mode else 'small'
        # 兼容旧 'triple' → 'double'
        if wheel_mode == 'triple':
            wheel_mode = 'double'
        self._selected_type = wheel_mode
        self._center_ring_visible = center_ring_visible
        self._middle_ring_visible = middle_ring_visible
        self._result = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        self._init_ui()
        self._select_type(self._selected_type)
        self._center_on_screen()
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _init_ui(self):
        fn = get_font()
        _detect_icon_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("ws_container")
        container.setStyleSheet(f"""
            QFrame#ws_container {{
                background: {C_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        root.setSpacing(10)

        # ── 标题栏 ──
        title_row = QHBoxLayout()
        title_lbl = QLabel(t("wheel_style.title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        close_icon = "\uE711" if _ICON_FONT else "\u2715"
        close_btn = QPushButton(close_icon)
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setFont(_make_font(fn, 18, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # ── 主体: 选择区 | 分割线 | 预览区 | 信息操作区 ──
        body = QHBoxLayout()
        body.setSpacing(0)

        # ── 左侧: 轮盘选择区 ──
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        self._type_cards = {}
        for wtype in WHEEL_TYPES:
            card = _TypeCard(wtype)
            card.clicked.connect(self._select_type)
            left.addWidget(card)
            self._type_cards[wtype['id']] = card
        left.addStretch()

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(130)
        left_widget.setContentsMargins(0, 0, 0, 0)
        left_widget.setStyleSheet("background: transparent;")
        body.addWidget(left_widget)

        # 分隔线 1
        div1 = QFrame()
        div1.setFixedWidth(1)
        div1.setStyleSheet("background: #444;")
        body.addWidget(div1)
        body.addSpacing(10)

        # ── 中间: 1:1 样式预览区 ──
        mid = QVBoxLayout()
        mid.setSpacing(0)
        self._preview_container = QVBoxLayout()
        self._preview_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._current_preview = None
        mid.addLayout(self._preview_container, 1)

        mid_widget = QWidget()
        mid_widget.setLayout(mid)
        mid_widget.setStyleSheet("background: transparent;")
        body.addWidget(mid_widget, 1)

        body.addSpacing(10)

        # ── 右侧: 信息操作区 (固定宽度) ──
        info_panel = QVBoxLayout()
        info_panel.setSpacing(12)

        # 类型名称 (大标题)
        self._info_title = QLabel("")
        self._info_title.setFont(_make_font(fn, 18, bold=True))
        self._info_title.setStyleSheet("color: #F43F5E; background: transparent;")
        self._info_title.setWordWrap(True)
        info_panel.addWidget(self._info_title)

        # 类型描述
        self._info_desc = QLabel("")
        self._info_desc.setFont(_make_font(fn, 13))
        self._info_desc.setStyleSheet("color: #999; background: transparent;")
        self._info_desc.setWordWrap(True)
        info_panel.addWidget(self._info_desc)

        # 分割线
        info_sep = QFrame()
        info_sep.setFixedHeight(1)
        info_sep.setStyleSheet("background: #444;")
        info_panel.addWidget(info_sep)

        # 设置区域 — 带勾号 checkbox
        self._ring_cb = _CheckToggle(
            t("wheel_style.show_center_ring"), fn,
            checked=self._center_ring_visible)
        self._ring_cb.toggled.connect(self._on_ring_toggled)
        info_panel.addWidget(self._ring_cb)

        # 中二环复选框 (仅双环模式)
        self._middle_ring_cb = _CheckToggle(
            t("wheel_style.show_middle_ring"), fn,
            checked=self._middle_ring_visible)
        self._middle_ring_cb.toggled.connect(self._on_middle_ring_toggled)
        info_panel.addWidget(self._middle_ring_cb)

        info_panel.addStretch()

        # 底部按钮 (从上到下: 重置八方向键 → 取消 → 确定)
        self._reset_btn = QPushButton(t("wheel_style.reset_sectors"))
        self._reset_btn.setFixedHeight(40)
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setFont(_make_font(fn, 14))
        self._reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CARD_NORMAL}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CARD_HOVER}; }}
        """)
        self._reset_btn.clicked.connect(self._on_reset_sectors)
        info_panel.addWidget(self._reset_btn)

        cancel_btn = QPushButton(t("wheel_style.cancel"))
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFont(_make_font(fn, 16))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CARD_NORMAL}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CARD_HOVER}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        info_panel.addWidget(cancel_btn)

        save_btn = QPushButton(t("wheel_style.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 16, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_ACCENT}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: #E11D48; }}
        """)
        save_btn.clicked.connect(self._on_save)
        info_panel.addWidget(save_btn)

        info_widget = QWidget()
        info_widget.setLayout(info_panel)
        info_widget.setFixedWidth(self.INFO_W)
        info_widget.setStyleSheet("background: transparent;")
        body.addWidget(info_widget)

        root.addLayout(body, 1)

    def _select_type(self, type_id):
        self._selected_type = type_id
        for tid, card in self._type_cards.items():
            card.set_selected(tid == type_id)

        # 更新 1:1 预览
        if self._current_preview:
            self._preview_container.removeWidget(self._current_preview)
            self._current_preview.deleteLater()

        wtype = next(wt for wt in WHEEL_TYPES if wt['id'] == type_id)
        preview = _WheelPreview(wtype, scale=1.0, interactive=True)
        preview.set_center_ring_visible(self._center_ring_visible)
        preview.set_middle_ring_visible(self._middle_ring_visible)
        preview.area_clicked.connect(self._on_area_clicked)
        self._preview_container.addWidget(preview, 0, Qt.AlignmentFlag.AlignCenter)
        self._current_preview = preview

        # 更新右侧信息面板
        self._info_title.setText(_wheel_type_name(type_id))
        self._info_desc.setText(t(f"wheel_style.desc_{type_id}"))

        # 复选框可见性:
        # small: 无环，两个 checkbox 都隐藏
        # large (单环): 仅显示「显示中心环」
        # double (双环): 显示「显示中心环」+「显示中二环」
        if type_id == 'double':
            self._ring_cb.setVisible(True)
            self._ring_cb.setChecked(self._center_ring_visible)
            self._middle_ring_cb.setVisible(True)
            self._middle_ring_cb.setChecked(self._middle_ring_visible)
            self._reset_btn.setText(t("wheel_style.reset_sectors"))
        elif type_id == 'large':
            self._ring_cb.setVisible(True)
            self._ring_cb.setChecked(self._center_ring_visible)
            self._middle_ring_cb.setVisible(False)
            self._reset_btn.setText(t("wheel_style.reset_sectors"))
        elif type_id == 'dual':
            self._ring_cb.setVisible(True)
            self._ring_cb.setChecked(self._center_ring_visible)
            self._middle_ring_cb.setVisible(False)
            self._reset_btn.setText(t("wheel_style.reset_sectors_dual"))
        else:
            self._ring_cb.setVisible(False)
            self._middle_ring_cb.setVisible(False)
            self._reset_btn.setText(t("wheel_style.reset_sectors"))

        # 防止 widget 重建导致弹窗掉到 overlay 后面
        self.raise_()
        self.activateWindow()

    def _on_ring_toggled(self, checked):
        self._center_ring_visible = checked
        if self._current_preview:
            self._current_preview.set_center_ring_visible(checked)

    def _on_middle_ring_toggled(self, checked):
        self._middle_ring_visible = checked
        if self._current_preview:
            self._current_preview.set_middle_ring_visible(checked)

    def _on_area_clicked(self, area):
        if area == 'ring':
            # 双环模式: ring = 中二环; 单环模式: ring = 中心环
            if self._selected_type == 'double':
                self._middle_ring_cb.setChecked(not self._middle_ring_cb.isChecked())
            else:
                self._ring_cb.setChecked(not self._ring_cb.isChecked())
        elif area == 'inner_ring':
            # 双环模式: inner_ring = 中心环
            self._ring_cb.setChecked(not self._ring_cb.isChecked())

    def _on_reset_sectors(self):
        """重置八方向扇区为默认键值，立即保存并关闭。"""
        from core.constants import default_wheel_sectors
        self._result = {
            'wheel_mode': self._selected_type,
            'wheel_enlarged': self._selected_type in ('large', 'double'),
            'wheel_center_ring_visible': self._center_ring_visible,
            'wheel_middle_ring_visible': self._middle_ring_visible,
            'reset_sectors': default_wheel_sectors(),
        }
        # dual 模式同时重置外八向
        if self._selected_type == 'dual':
            from core.constants import default_wheel_outer_sectors
            self._result['reset_outer_sectors'] = default_wheel_outer_sectors()
        self.settings_changed.emit(self._result)
        self.accept()

    def _on_save(self):
        self._result = {
            'wheel_mode': self._selected_type,
            'wheel_enlarged': self._selected_type in ('large', 'double'),  # 向后兼容
            'wheel_center_ring_visible': self._center_ring_visible,
            'wheel_middle_ring_visible': self._middle_ring_visible,
        }
        self.settings_changed.emit(self._result)
        self.accept()

    def get_result(self):
        return self._result

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
