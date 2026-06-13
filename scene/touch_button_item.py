"""
TEGG Touch 蛋挞 (PyQt6) - touch_button_item.py
触控按钮 QGraphicsObject — 封装绘制、编辑交互、运行交互于一体。
"""

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal, pyqtProperty
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QFontDatabase, QFontMetrics

from core.constants import (
    BTN_RADIUS, BTN_MARGIN, BTN_TYPE_CENTER_BAND, BTN_TYPE_GP_BUTTON,
    COLOR_BTN_BG, COLOR_BTN_BORDER, COLOR_TEXT,
    COLOR_GP_BTN_BG, COLOR_GP_BTN_BORDER, COLOR_GP_BTN_TEXT,
    GP_KEY_PREFIX, GP_KEY_TO_LABEL, DEFAULT_GRID_SIZE,
)
from core.i18n import t, get_font
from models.button_model import ButtonData
from engine.hover_state_machine import HoverStateMachine
from scene.tooltip_item import build_edit_tooltip

# 字体缓存 (避免 paint() 每帧创建 QFont)
_font_cache: dict = {}
_FONT_CACHE_MAX = 128  # 缓存上限，超过时清空重建

def _get_cached_font(font_name: str, px: int, bold: bool = True) -> QFont:
    key = (font_name, px, bold)
    f = _font_cache.get(key)
    if f is None:
        if len(_font_cache) >= _FONT_CACHE_MAX:
            _font_cache.clear()
        f = QFont(font_name)
        f.setPixelSize(px)
        if bold:
            f.setWeight(QFont.Weight.Bold)
        _font_cache[key] = f
    return f


# 回中带专用配色
COLOR_CENTER_BAND = "#176F2C"
COLOR_CENTER_BAND_BG = "#0A2E12"
COLOR_CENTER_BAND_TEXT = "#4ADE80"   # 明亮薄荷绿（文字/icon）

# 状态配色表: (fill, border, text_color)
STATE_COLORS = {
    'normal':           (QColor("#111111"), QColor("#555555"), QColor("#FFFFFF")),
    'hover':            (QColor("#0284C7"), QColor("#026AA2"), QColor("#000000")),
    'active_left':      (QColor("#F59E0B"), QColor("#D97706"), QColor("#000000")),
    'active_right':     (QColor("#10B981"), QColor("#059669"), QColor("#000000")),
    'active_middle':    (QColor("#A855F7"), QColor("#9333EA"), QColor("#000000")),
    'active_wheelup':   (QColor("#EC4899"), QColor("#DB2777"), QColor("#000000")),
    'active_wheeldown': (QColor("#F43F5E"), QColor("#E11D48"), QColor("#000000")),
    'active_xbutton1':  (QColor("#06B6D4"), QColor("#0891B2"), QColor("#000000")),
    'active_xbutton2':  (QColor("#8B5CF6"), QColor("#7C3AED"), QColor("#000000")),
}

# 网格尺寸 → (字号px, 按钮圆角, 充能条圆角)
_GRID_STYLE = {
    100: (18, 10, 6),
    90:  (18, 10, 6),
    80:  (16, 8, 5),
    70:  (16, 8, 5),
    60:  (14, 6, 4),
}
_GRID_STYLE_DEFAULT = (18, 10, 6)

# 状态对应的动作键名
STATE_TO_KEY = {
    'hover': 'hover',
    'active_left': 'lclick',
    'active_right': 'rclick',
    'active_middle': 'mclick',
    'active_xbutton1': 'xbutton1',
    'active_xbutton2': 'xbutton2',
    'active_wheelup': 'wheelup',
    'active_wheeldown': 'wheeldown',
}


def _format_btn_name(name):
    """格式化按钮名称：最多2行，过长截断。"""
    limit = 8
    if len(name) > limit * 2:
        return name[:limit * 2 - 1] + "…"
    if len(name) > limit:
        return name[:limit] + "\n" + name[limit:]
    return name


def _gp_display(key: str) -> str:
    """gp: 字段值 → 友好显示 label (例如 'gp:D-Left' → '←', 'gp:LB' → '左肩 LB')。
    非 gp 字段直接返回原样。"""
    if not key.startswith(GP_KEY_PREFIX):
        return key
    storage = key[len(GP_KEY_PREFIX):]
    return GP_KEY_TO_LABEL.get(storage, storage)


# 手柄键固定图标 (Segoe Fluent Icons / MDL2 Assets: \uE7FC = GameConsole)
GP_ICON_CHAR = "\uE7FC"
GP_ICON_FALLBACK = "GP"  # 字体不可用时降级文本

_ICON_FONT = None  # 缓存检测结果: "Segoe Fluent Icons" | "Segoe MDL2 Assets" | ""

def _get_icon_font_name() -> str:
    """惰性检测系统是否有 Segoe 图标字体, 缓存结果。"""
    global _ICON_FONT
    if _ICON_FONT is None:
        fams = QFontDatabase.families()
        if "Segoe Fluent Icons" in fams:
            _ICON_FONT = "Segoe Fluent Icons"
        elif "Segoe MDL2 Assets" in fams:
            _ICON_FONT = "Segoe MDL2 Assets"
        else:
            _ICON_FONT = ""
    return _ICON_FONT


class TouchButtonItem(QGraphicsObject):
    """触摸按钮 — 封装绘制、编辑交互、运行交互于一体

    旧版: 按钮是 canvas.create_polygon() 返回的 id + dict
          绘制/交互/状态分散在 canvas_renderer/button_manager/run_engine 三个文件
    新版: 一个 Item 类封装所有职责，信号/槽对外通信
    """

    # ── 信号 ──
    doubleClicked = pyqtSignal(object)           # 双击 → 打开编辑器
    hoverActivated = pyqtSignal(object)          # hover 激活 → 触发按键
    hoverDeactivated = pyqtSignal(object)        # hover 释放 → 释放按键
    actionTriggered = pyqtSignal(object, str, str)  # (data, key_str, 'p'|'r'|'c')
    data_changed = pyqtSignal()                  # 数据变更

    MARGIN = BTN_MARGIN
    RADIUS = BTN_RADIUS

    def __init__(self, data: ButtonData, offset_x: float = 0, offset_y: float = 0):
        super().__init__()
        self.data = data
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._visual_state = 'normal'
        self._mode = 'edit'  # 'edit' | 'run'
        self._charge_progress = 0.0  # 充能进度 0~1

        # 层级: 按钮(15) > 中心环(10) > 轮盘扇区(5)
        self.setZValue(15)

        # 启用 hover 事件
        self.setAcceptHoverEvents(True)

        # 编辑模式标志
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # 初始位置（逻辑坐标 + 中心偏移 = 屏幕坐标）
        self.setPos(data.x + offset_x, data.y + offset_y)

        # 缩放手柄（子 Item）
        from scene.resize_handle_item import ResizeHandleItem
        self._resize_handle = ResizeHandleItem(self)
        self._update_handle_pos()

        # 悬停状态机 — 按 hover_mode 选 delay 字段
        _is_toggle = getattr(data, 'hover_mode', 'trigger') == 'toggle'
        _hd = data.hover_toggle_delay if _is_toggle else data.hover_delay
        _rd = (getattr(data, 'hover_toggle_release_delay', 0) if _is_toggle
               else data.hover_release_delay)
        self._hover_sm = HoverStateMachine(
            _hd, _rd, mode=getattr(data, 'hover_mode', 'trigger'))
        self._hover_sm.activated.connect(self._on_hover_activated)
        self._hover_sm.deactivated.connect(self._on_hover_deactivated)
        self._hover_sm.charge_progress.connect(self._on_charge_progress)
        self._hover_sm.release_progress.connect(self._on_release_progress)

        # 编辑模式持久化光标（不依赖 hover enter/leave）
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 接受所有鼠标按键
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton |
            Qt.MouseButton.RightButton |
            Qt.MouseButton.MiddleButton
        )

    # ── 几何 ──

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.data.w, self.data.h)

    # ── 绘制 ──

    def paint(self, painter: QPainter, option, widget=None):
        """绘制按钮 — 圆角矩形 + 名称文字"""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.boundingRect().adjusted(
            self.MARGIN, self.MARGIN, -self.MARGIN, -self.MARGIN)

        is_band = self.data.btn_type == BTN_TYPE_CENTER_BAND
        is_gp = self.data.btn_type == BTN_TYPE_GP_BUTTON

        if is_band:
            # 回中带：深绿背景 + 绿色边框 + 明亮绿文字
            fill = QColor(COLOR_CENTER_BAND_BG)
            border = QColor(COLOR_CENTER_BAND)
            text_color = QColor(COLOR_CENTER_BAND_TEXT)
        elif is_gp and self._visual_state == 'normal':
            # 手柄键 normal: 蓝紫调; active 状态仍走 STATE_COLORS 反馈
            fill = QColor(COLOR_GP_BTN_BG)
            border = QColor(COLOR_GP_BTN_BORDER)
            text_color = QColor(COLOR_GP_BTN_TEXT)
        elif self._visual_state == 'normal':
            fill, border, text_color = STATE_COLORS['normal']
        else:
            fill, border, text_color = STATE_COLORS.get(
                self._visual_state, STATE_COLORS['normal'])

        border_width = 3 if self._visual_state != 'normal' else 2

        # 从网格尺寸查表获取动态样式参数
        gs = self.scene().grid_size if self.scene() else DEFAULT_GRID_SIZE
        font_px, btn_r, charge_r = _GRID_STYLE.get(gs, _GRID_STYLE_DEFAULT)

        # 按钮路径：编辑模式右下直角（与缩放手柄贴合），运行模式全圆角
        painter.setPen(QPen(border, border_width))
        painter.setBrush(QBrush(fill))
        btn_path = self._build_btn_path(rect, btn_r,
                                         sharp_br=(self._mode == 'edit'))
        painter.drawPath(btn_path)

        # 充能进度条
        if self._charge_progress > 0.01:
            charge_rect = rect.adjusted(2, 2, -2, -2)
            charge_rect.setWidth(charge_rect.width() * self._charge_progress)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#0284C7"))
            charge_path = self._build_btn_path(charge_rect, charge_r,
                                                sharp_br=(self._mode == 'edit'))
            painter.drawPath(charge_path)

        # 确定显示文字 — 字体大小随网格动态缩放 (px)
        font_name = get_font()

        def _make_px_font(px, bold=True):
            return _get_cached_font(font_name, px, bold)

        # ── 手柄键: 跟回中带一样的 icon+name 布局 ──
        # icon 永远是固定 Segoe gamepad 字形, name/key 都用 font_px 同尺寸, 居中堆叠
        # 跟按钮形状无关 (font_px 只跟 grid_size 走)
        if is_gp:
            # 底部文字: normal=name, active=去前缀的友好 label (例如 'gp:LB' → '左肩 LB')
            if self._visual_state != 'normal':
                key_field = STATE_TO_KEY.get(self._visual_state)
                if key_field == 'hover' and getattr(self.data, 'hover_mode', 'trigger') == 'toggle':
                    key_field = 'hover_toggle'
                key_val = getattr(self.data, key_field, '') if key_field else ''
                if key_val:
                    s = '+'.join(_gp_display(k) for k in key_val.split('+'))
                    # 长 label (例如 '左肩 LB') 不截断, 让 Qt elide; 超 8 字符再截
                    bottom_text = s if len(s) <= 8 else s[:7] + '…'
                else:
                    bottom_text = _format_btn_name(self.data.name) if self.data.name else ''
            else:
                bottom_text = _format_btn_name(self.data.name) if self.data.name else ''

            # icon 用 Segoe 字体, 文字用常规字体, 两者都是 font_px
            icon_font_name = _get_icon_font_name()
            if icon_font_name:
                icon_font = _get_cached_font(icon_font_name, font_px, bold=False)
                icon_char = GP_ICON_CHAR
            else:
                icon_font = _make_px_font(font_px, bold=True)
                icon_char = GP_ICON_FALLBACK
            name_font = _make_px_font(font_px)

            # 用 QFontMetrics 算两行高度, 整体居中 (无额外 gap, 模拟 '\n')
            icon_h = QFontMetrics(icon_font).height()
            name_h = QFontMetrics(name_font).height()
            total_h = icon_h + name_h
            y0 = rect.y() + (rect.height() - total_h) / 2

            painter.setPen(text_color)
            painter.setFont(icon_font)
            painter.drawText(QRectF(rect.x(), y0, rect.width(), icon_h),
                             Qt.AlignmentFlag.AlignCenter, icon_char)
            painter.setFont(name_font)
            painter.drawText(QRectF(rect.x(), y0 + icon_h, rect.width(), name_h),
                             Qt.AlignmentFlag.AlignCenter, bottom_text)
            return

        if is_band:
            display_text = t("canvas.center_band_label")
            painter.setFont(_make_px_font(font_px))
        elif self._visual_state != 'normal':
            # 运行时有状态：显示键值
            key_field = STATE_TO_KEY.get(self._visual_state)
            # hover 状态: 按 hover_mode 选 hover / hover_toggle 字段
            if key_field == 'hover' and getattr(self.data, 'hover_mode', 'trigger') == 'toggle':
                key_field = 'hover_toggle'
            key_val = getattr(self.data, key_field, '') if key_field else ''
            if key_val:
                display_text = key_val if len(key_val) <= 3 else key_val[:2] + '..'
                painter.setFont(_make_px_font(font_px + 6))
            else:
                display_text = _format_btn_name(self.data.name)
                painter.setFont(_make_px_font(font_px))
        else:
            display_text = _format_btn_name(self.data.name)
            painter.setFont(_make_px_font(font_px))

        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, display_text)


    # ── 充能进度属性（用于 QPropertyAnimation）──

    @pyqtProperty(float)
    def chargeProgress(self):
        return self._charge_progress

    @chargeProgress.setter
    def chargeProgress(self, val):
        self._charge_progress = val
        self.update()

    # ── 状态设置 ──

    def set_visual_state(self, state: str):
        if self._visual_state != state:
            self._visual_state = state
            self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        movable = (mode == 'edit')
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)
        self._resize_handle.setVisible(movable)
        # 编辑模式持久化手型光标
        if mode == 'edit':
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        # 切换模式时重置状态
        self._hover_sm.reset()
        self._visual_state = 'normal'
        self._charge_progress = 0.0
        self.update()

    # ── 编辑交互 ──

    def itemChange(self, change, value):
        """拖拽时网格吸附 — 相对于屏幕中心(网格原点)对齐

        注意: 仅在 item 已加入 scene 后才执行吸附。
        __init__ 中 setPos() 触发本方法时 self.scene() 为 None，
        此时必须跳过吸附，否则会用 DEFAULT_GRID_SIZE 重新对齐坐标，
        导致非 100px 网格保存的坐标在加载时错位。
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self._mode == 'edit' and self.scene() is not None:
                gs = self.scene().grid_size
                # 以屏幕中心为基准吸附，确保与 drawBackground 网格对齐
                new_pos = QPointF(
                    round((value.x() - self._offset_x) / gs) * gs + self._offset_x,
                    round((value.y() - self._offset_y) / gs) * gs + self._offset_y,
                )
                self.data.x = new_pos.x() - self._offset_x
                self.data.y = new_pos.y() - self._offset_y
                return new_pos
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        """双击 → 打开编辑弹窗"""
        if self._mode == 'edit':
            self.doubleClicked.emit(self)

    def _update_handle_pos(self):
        """更新缩放手柄位置"""
        self._resize_handle.setPos(self.data.w - 24, self.data.h - 24)

    def resize_to(self, new_w, new_h):
        """缩放按钮"""
        gs = self.scene().grid_size if self.scene() else DEFAULT_GRID_SIZE
        self.prepareGeometryChange()
        self.data.w = max(gs, new_w)
        self.data.h = max(gs, new_h)
        self._update_handle_pos()
        self.update()
        self.data_changed.emit()

    # ── 鼠标事件（编辑 + 运行共用）──

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
                Qt.MouseButton.LeftButton: ('lclick', self.data.lclick),
                Qt.MouseButton.RightButton: ('rclick', self.data.rclick),
                Qt.MouseButton.MiddleButton: ('mclick', self.data.mclick),
            }
            field, key = key_map.get(event.button(), (None, ''))
            if key:
                self.actionTriggered.emit(self.data, key, 'r')
            # 恢复 hover 或 normal 状态
            self.set_visual_state('hover' if self._hover_sm.is_active else 'normal')
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            if self._mode == 'edit':
                self.data_changed.emit()

    # ── Hover 事件 ──

    def hoverEnterEvent(self, event):
        if self._mode == 'edit':
            scene = self.scene()
            if scene:
                scene.show_tooltip(build_edit_tooltip(self.data), event.scenePos())
        elif self._mode == 'run':
            # 回中带：立即回中 (匹配原版 handle_run_interaction: center_band → SetCursorPos)
            if self.data.btn_type == BTN_TYPE_CENTER_BAND:
                import ctypes
                from PyQt6.QtWidgets import QApplication
                from PyQt6.QtCore import QRect
                _ps = QApplication.primaryScreen()
                screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
                cx = screen.x() + screen.width() // 2
                cy = screen.y() + screen.height() // 2
                ctypes.windll.user32.SetCursorPos(cx, cy)
            else:
                _key = (self.data.hover_toggle
                        if getattr(self.data, 'hover_mode', 'trigger') == 'toggle'
                        else self.data.hover)
                if _key:
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

    # ── 滚轮事件（由 RunController 分发）──

    def on_wheel(self, direction):
        """滚轮事件"""
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
        """充能进度回调 — 进度条从 0→1"""
        self._charge_progress = progress
        self.update()

    def _on_release_progress(self, progress):
        """释放倒计时进度回调 — 进度条从 1→0"""
        self._charge_progress = progress
        self.update()

    # ── 路径构建辅助 ──

    @staticmethod
    def _build_btn_path(rect: QRectF, r: float, sharp_br: bool = False) -> QPainterPath:
        """构建按钮轮廓路径。

        三个角圆角(左上/右上/左下)，右下角根据 sharp_br 决定:
        - True  → 直角（编辑模式，与缩放手柄贴合）
        - False → 圆角（运行模式，手柄隐藏）
        """
        path = QPainterPath()
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        d = r * 2

        # 左上圆角
        path.moveTo(x + r, y)
        # 顶边
        path.lineTo(x + w - r, y)
        # 右上圆角
        path.arcTo(x + w - d, y, d, d, 90, -90)
        # 右边
        if sharp_br:
            path.lineTo(x + w, y + h)
            # 底边 → 到左下圆角起点(x+r, y+h)，避免多余连接线
            path.lineTo(x + r, y + h)
        else:
            path.lineTo(x + w, y + h - r)
            # 右下圆角
            path.arcTo(x + w - d, y + h - d, d, d, 0, -90)
            # 底边
            path.lineTo(x + r, y + h)
        # 左下圆角
        path.arcTo(x, y + h - d, d, d, 270, -90)
        # 左边
        path.lineTo(x, y + r)
        # 左上圆角
        path.arcTo(x, y, d, d, 180, -90)
        path.closeSubpath()
        return path
