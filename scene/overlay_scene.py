"""
TEGG Touch 蛋挞 (PyQt6) - overlay_scene.py
主场景 — 管理所有 QGraphicsItem。
"""

from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtGui import QPen, QColor, QPainter
from PyQt6.QtCore import QRectF, pyqtSignal

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem
from PyQt6.QtCore import QRectF, Qt as _Qt
from PyQt6.QtGui import QPainter as _QPainter, QColor as _QColor, QFont as _QFont, QPen as _QPen

from core.constants import (
    DEFAULT_GRID_SIZE, BTN_TYPE_WHEEL_SECTOR, BTN_TYPE_WHEEL_RING,
    BTN_TYPE_WHEEL_INNER_RING, BTN_TYPE_CENTER_BAND,
    WHEEL_INNER_RADIUS, WHEEL_OUTER_RADIUS,
    WHEEL_INNER_RADIUS_LARGE, WHEEL_OUTER_RADIUS_LARGE,
    WHEEL_RING_INNER, WHEEL_RING_OUTER,
    WHEEL_TRIPLE_INNER_RING_INNER, WHEEL_TRIPLE_INNER_RING_OUTER,
    WHEEL_TRIPLE_OUTER_RING_INNER, WHEEL_TRIPLE_OUTER_RING_OUTER,
    WHEEL_TRIPLE_SECTOR_INNER, WHEEL_TRIPLE_SECTOR_OUTER,
    WHEEL_SECTOR_COUNT, WHEEL_MAX_OFFSET, WHEEL_RESIZE_BTN_SIZE,
)
from core.i18n import t


# ── 图标字体检测 (与 edit_toolbar 共用逻辑) ──
_ICON_FONT_NAME = None

def _detect_icon_font():
    global _ICON_FONT_NAME
    if _ICON_FONT_NAME is not None:
        return _ICON_FONT_NAME
    from PyQt6.QtGui import QFontDatabase
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT_NAME = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT_NAME = "Segoe MDL2 Assets"
    else:
        _ICON_FONT_NAME = ""
    return _ICON_FONT_NAME

# 轮盘样式按钮
_ICON_SETTINGS = "\uE713"   # Settings 齿轮
_STYLE_BTN_SIZE = 30
_STYLE_BTN_COLOR = "#F43F5E"      # 玫瑰红
_STYLE_BTN_HOVER = "#FB7185"      # 玫瑰红 lighter


class _WheelStyleBtn(QGraphicsObject):
    """轮盘样式管理按钮 — 玫瑰红圆角矩形 + 齿轮 icon"""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setCursor(_Qt.CursorShape.PointingHandCursor)
        self.setZValue(50)

    def boundingRect(self):
        return QRectF(0, 0, _STYLE_BTN_SIZE, _STYLE_BTN_SIZE)

    def paint(self, painter: _QPainter, option, widget=None):
        painter.setRenderHint(_QPainter.RenderHint.Antialiasing)
        bg = _QColor(_STYLE_BTN_HOVER) if self._hover else _QColor(_STYLE_BTN_COLOR)
        painter.setPen(_Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(self.boundingRect(), 6, 6)

        ifont = _detect_icon_font()
        if ifont:
            painter.setPen(_QColor("#FFFFFF"))
            painter.setFont(_QFont(ifont, 10))
            painter.drawText(self.boundingRect(), _Qt.AlignmentFlag.AlignCenter, _ICON_SETTINGS)
        else:
            from core.i18n import get_font as _gf
            painter.setPen(_QColor("#FFFFFF"))
            painter.setFont(_QFont(_gf(), 10, _QFont.Weight.Bold))
            painter.drawText(self.boundingRect(), _Qt.AlignmentFlag.AlignCenter, "\u2699")

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        scene = self.scene()
        if scene and hasattr(scene, 'show_tooltip'):
            tip = getattr(self, '_tooltip_text', '')
            if tip:
                scene.show_tooltip(tip, event.scenePos())

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        scene = self.scene()
        if scene and hasattr(scene, 'hide_tooltip'):
            scene.hide_tooltip()

    def mousePressEvent(self, event):
        if event.button() == _Qt.MouseButton.LeftButton:
            self._callback()
            event.accept()


# 轮盘缩放按钮
_RESIZE_BTN_COLOR = "#555555"     # 灰色（与普通按钮拖动手柄一致）
_RESIZE_BTN_HOVER = "#777777"
_ICON_RESIZE = "\uE740"          # ResizeMouseSmall 对角双箭头


class _WheelResizeBtn(QGraphicsObject):
    """轮盘缩放拖拽按钮 — 灰色圆角矩形 + 缩放 icon，拖拽改变轮盘半径"""

    def __init__(self, scene_ref, parent=None):
        super().__init__(parent)
        self._scene_ref = scene_ref
        self._hover = False
        self._dragging = False
        self._drag_start_y = 0
        self._drag_start_offset = 0
        self.setAcceptHoverEvents(True)
        self.setCursor(_Qt.CursorShape.SizeFDiagCursor)
        self.setZValue(50)

    def boundingRect(self):
        s = WHEEL_RESIZE_BTN_SIZE
        return QRectF(0, 0, s, s)

    def paint(self, painter: _QPainter, option, widget=None):
        painter.setRenderHint(_QPainter.RenderHint.Antialiasing)
        bg = _QColor(_RESIZE_BTN_HOVER) if self._hover else _QColor(_RESIZE_BTN_COLOR)
        painter.setPen(_Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        s = WHEEL_RESIZE_BTN_SIZE
        painter.drawRoundedRect(QRectF(0, 0, s, s), 6, 6)

        ifont = _detect_icon_font()
        if ifont:
            painter.save()
            painter.translate(s, 0)
            painter.scale(-1, 1)  # 水平镜像翻转
            painter.setPen(_QColor("#FFFFFF"))
            painter.setFont(_QFont(ifont, 10))
            painter.drawText(QRectF(0, 0, s, s), _Qt.AlignmentFlag.AlignCenter, _ICON_RESIZE)
            painter.restore()
        else:
            from core.i18n import get_font as _gf
            painter.setPen(_QColor("#FFFFFF"))
            painter.setFont(_QFont(_gf(), 10, _QFont.Weight.Bold))
            painter.drawText(self.boundingRect(), _Qt.AlignmentFlag.AlignCenter, "\u2922")

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == _Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_y = event.scenePos().y()
            self._drag_start_offset = self._scene_ref._wheel_offset
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        scene = self._scene_ref
        cx = scene.sceneRect().width() / 2
        cy = scene.sceneRect().height() / 2
        mouse = event.scenePos()
        # 用鼠标到中心的最大单轴距离来决定新的 effective_r
        dx = mouse.x() - cx
        dy = mouse.y() - cy
        # 取 max(dx, dy) 因为按钮在右下角
        desired_r = max(dx, dy)
        base_r = scene._get_base_r_outer()
        new_offset = int(max(0, min(WHEEL_MAX_OFFSET, desired_r - base_r)))
        if new_offset != scene._wheel_offset:
            scene.set_wheel_offset(new_offset)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()


class _AutoCenterBar(QGraphicsObject):
    """自动回中倒计时进度条 — 跟随光标位置 (匹配原版 50×6px 绿色条)"""

    BAR_W = 50
    BAR_H = 6

    def __init__(self):
        super().__init__()
        self._progress = 0.0
        self.setVisible(False)
        self.setZValue(100)

    def boundingRect(self):
        return QRectF(0, 0, self.BAR_W, self.BAR_H)

    def shape(self):
        from PyQt6.QtGui import QPainterPath
        return QPainterPath()  # 鼠标透明

    def paint(self, painter: _QPainter, option, widget=None):
        painter.setRenderHint(_QPainter.RenderHint.Antialiasing)
        # 灰色底
        painter.setPen(_Qt.PenStyle.NoPen)
        painter.setBrush(_QColor("#1A1A1A"))
        painter.drawRect(0, 0, self.BAR_W, self.BAR_H)
        # 绿色填充
        fill_w = int(self.BAR_W * self._progress)
        if fill_w > 0:
            painter.setBrush(_QColor("#176F2C"))
            painter.drawRect(0, 0, fill_w, self.BAR_H)

    def update_progress(self, progress, x, y):
        if progress < 0:
            self.setVisible(False)
            return
        self._progress = progress
        self.setPos(x, y)
        self.setVisible(True)
        self.update()


class OverlayScene(QGraphicsScene):
    """主场景 — 管理所有 QGraphicsItem"""

    # 信号
    button_double_clicked = pyqtSignal(object)  # TouchButtonItem
    toast_requested = pyqtSignal(str)           # toast 文字
    wheel_rebuilt = pyqtSignal()                # 轮盘重建完成（需要重新设置透明度等）

    def __init__(self):
        super().__init__()
        self.mode = 'edit'  # 'edit' | 'run'
        self.grid_size = DEFAULT_GRID_SIZE
        self.button_items = []
        self.wheel_items = []
        self.ring_item = None
        self.inner_ring_item = None
        self._config = {}           # 保存完整配置引用
        self._wheel_visible = False
        self._wheel_mode = 'small'  # 'small' | 'large' | 'double'
        self._wheel_enlarged = False  # 向后兼容
        self._wheel_center_ring_visible = True
        self._wheel_middle_ring_visible = True
        self._wheel_offset = 0          # 轮盘缩放偏移 (px)
        self._wheel_style_btn = None
        self._wheel_resize_btn = None

        # 场景内自定义 Tooltip（替代 Qt 原生 setToolTip）
        from scene.tooltip_item import TooltipItem
        self._tooltip = TooltipItem()
        self.addItem(self._tooltip)

        # 自动回中倒计时进度条
        self._ac_bar = _AutoCenterBar()
        self.addItem(self._ac_bar)

    # ── 背景绘制 ──

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """编辑模式下绘制网格背景 — 自动调用，无需手动管理"""
        super().drawBackground(painter, rect)

        if self.mode != 'edit':
            return

        # 20% 黑色遮罩
        painter.fillRect(rect, QColor(0, 0, 0, 50))

        scene_rect = self.sceneRect()
        cx = scene_rect.width() / 2
        cy = scene_rect.height() / 2
        gs = self.grid_size

        # 普通网格线
        pen = QPen(QColor("#2A2A2A"), 1)
        painter.setPen(pen)

        x = cx % gs
        while x <= scene_rect.width():
            painter.drawLine(int(x), 0, int(x), int(scene_rect.height()))
            x += gs

        y = cy % gs
        while y <= scene_rect.height():
            painter.drawLine(0, int(y), int(scene_rect.width()), int(y))
            y += gs

        # 中心十字线（稍亮）
        center_pen = QPen(QColor("#444444"), 2)
        painter.setPen(center_pen)
        painter.drawLine(int(cx), 0, int(cx), int(scene_rect.height()))
        painter.drawLine(0, int(cy), int(scene_rect.width()), int(cy))

    # ── 配置加载/保存 ──

    def load_from_config(self, config: dict):
        """从配置数据创建所有 Item — 替代旧版 redraw_all()

        x/y/w/h 存储的是像素坐标（以屏幕中心为原点）。
        grid_size 由 overlay_window 在调用本方法之前通过
        self.grid_size = saved_grid 直接赋值恢复。
        """
        from models.button_model import ButtonData
        from scene.touch_button_item import TouchButtonItem

        self._config = config
        buttons = config.get('buttons', [])
        offset_x = self.sceneRect().width() / 2
        offset_y = self.sceneRect().height() / 2

        for btn_dict in buttons:
            if btn_dict.get('deleted'):
                continue
            # 跳过轮盘扇区和中心圆环（由 load_wheel 处理）
            btn_type = btn_dict.get('type', 'normal')
            if btn_type in (BTN_TYPE_WHEEL_SECTOR, BTN_TYPE_WHEEL_RING, BTN_TYPE_WHEEL_INNER_RING):
                continue

            data = ButtonData.from_dict(btn_dict)
            item = TouchButtonItem(data, offset_x, offset_y)
            item.doubleClicked.connect(self._on_button_double_clicked)
            self.addItem(item)
            self.button_items.append(item)

        # 加载轮盘
        self._wheel_visible = config.get('wheel_visible', False)
        # wheel_mode: 优先读取新字段，向后兼容旧 wheel_enlarged
        self._wheel_mode = config.get('wheel_mode', None)
        if self._wheel_mode is None:
            self._wheel_mode = 'large' if config.get('wheel_enlarged', False) else 'small'
        # 兼容旧 'triple' → 'double'
        if self._wheel_mode == 'triple':
            self._wheel_mode = 'double'
        self._wheel_enlarged = (self._wheel_mode in ('large', 'double'))
        self._wheel_center_ring_visible = config.get('wheel_center_ring_visible', True)
        self._wheel_middle_ring_visible = config.get('wheel_middle_ring_visible', True)
        self._wheel_offset = int(config.get('wheel_offset', 0))
        self._load_wheel(config)
        self._update_wheel_controls()

    def _load_wheel(self, config: dict):
        """从配置加载轮盘扇面和中心圆环"""
        from models.wheel_model import WheelSectorData, WheelRingData
        from scene.wheel_sector_item import WheelSectorItem
        from scene.wheel_ring_item import WheelRingItem

        sectors = config.get('wheel_sectors', [])
        if not sectors:
            return

        cx = self.sceneRect().width() / 2
        cy = self.sceneRect().height() / 2

        # 根据模式选择半径 + 应用缩放偏移
        ofs = self._wheel_offset
        if self._wheel_mode == 'double':
            r_inner = WHEEL_TRIPLE_SECTOR_INNER + ofs
            r_outer = WHEEL_TRIPLE_SECTOR_OUTER + ofs
        elif self._wheel_mode == 'large':
            r_inner = WHEEL_INNER_RADIUS_LARGE + ofs
            r_outer = WHEEL_OUTER_RADIUS_LARGE + ofs
        else:
            r_inner = WHEEL_INNER_RADIUS + ofs
            r_outer = WHEEL_OUTER_RADIUS + ofs

        # 扇面角度：360° / 扇面数
        sector_count = len(sectors)
        span = 360.0 / sector_count

        for sec_dict in sectors:
            data = WheelSectorData.from_dict(sec_dict)
            # 从配置的 center_angle 计算 start_angle
            # Qt 角度: 0°=右, 逆时针; config angle 也是同样的约定
            center_angle = data.angle
            start_angle = center_angle - span / 2

            item = WheelSectorItem(data, cx, cy, r_inner, r_outer,
                                   start_angle, span)
            item.doubleClicked.connect(self._on_button_double_clicked)
            item.setZValue(5)
            item.setVisible(self._wheel_visible)
            self.addItem(item)
            self.wheel_items.append(item)

        # 中心圆环
        # large 模式: ring_item = 中心环 ← wheel_center_ring
        # double 模式: ring_item = 中二环位置 ← wheel_inner_ring 数据
        #              inner_ring_item = 中心环位置 ← wheel_center_ring 数据
        if self._wheel_mode == 'double':
            # ── 双环: 中二环 (ring_item) ──
            from core.constants import default_wheel_inner_ring
            mid_dict = config.get('wheel_inner_ring', None)
            if not mid_dict:
                mid_dict = default_wheel_inner_ring()
                config['wheel_inner_ring'] = mid_dict
            mid_data = WheelRingData.from_dict(mid_dict)
            self.ring_item = WheelRingItem(
                mid_data, cx, cy,
                WHEEL_TRIPLE_OUTER_RING_INNER + ofs,
                WHEEL_TRIPLE_OUTER_RING_OUTER + ofs)
            self.ring_item.doubleClicked.connect(self._on_button_double_clicked)
            self.ring_item.setVisible(
                self._wheel_visible and self._wheel_middle_ring_visible)
            self.addItem(self.ring_item)

            # ── 双环: 中心环 (inner_ring_item) ──
            center_dict = config.get('wheel_center_ring', {})
            if center_dict:
                center_data = WheelRingData.from_dict(center_dict)
                self.inner_ring_item = WheelRingItem(
                    center_data, cx, cy,
                    WHEEL_TRIPLE_INNER_RING_INNER + ofs,
                    WHEEL_TRIPLE_INNER_RING_OUTER + ofs)
                self.inner_ring_item.doubleClicked.connect(self._on_button_double_clicked)
                self.inner_ring_item.setVisible(
                    self._wheel_visible and self._wheel_center_ring_visible)
                self.addItem(self.inner_ring_item)

        elif self._wheel_mode == 'large':
            # ── 单环: ring_item = 中心环 ← wheel_center_ring ──
            ring_dict = config.get('wheel_center_ring', {})
            if ring_dict:
                ring_data = WheelRingData.from_dict(ring_dict)
                self.ring_item = WheelRingItem(
                    ring_data, cx, cy,
                    WHEEL_RING_INNER + ofs, WHEEL_RING_OUTER + ofs)
                self.ring_item.doubleClicked.connect(self._on_button_double_clicked)
                self.ring_item.setVisible(
                    self._wheel_visible and self._wheel_center_ring_visible)
                self.addItem(self.ring_item)

    def save_config(self):
        """将当前场景中的按钮状态保存回配置

        x/y/w/h 以像素存储，grid_size 一起保存。
        加载时先恢复 grid_size 再加载像素坐标，保证一致。
        """
        from core.config_manager import get_active_profile_name, save_profile

        if not self._config:
            return

        # 从按钮 Item 收集最新数据（原始像素坐标）
        new_buttons = []
        for item in self.button_items:
            new_buttons.append(item.data.to_dict())

        self._config['buttons'] = new_buttons
        # 清除旧的 coord_format 标记（如果残留）
        self._config.pop('coord_format', None)

        # 轮盘扇面数据（从 Item 回写）
        if self.wheel_items:
            wheel_sectors = []
            for item in self.wheel_items:
                wheel_sectors.append(item.data.to_dict())
            self._config['wheel_sectors'] = wheel_sectors

        # 圆环数据 — 双环模式下 ring_item=中二环, inner_ring_item=中心环
        if self._wheel_mode == 'double':
            if self.ring_item:
                self._config['wheel_inner_ring'] = self.ring_item.data.to_dict()
            if self.inner_ring_item:
                self._config['wheel_center_ring'] = self.inner_ring_item.data.to_dict()
        else:
            if self.ring_item:
                self._config['wheel_center_ring'] = self.ring_item.data.to_dict()

        # 轮盘显示状态
        self._config['wheel_visible'] = self._wheel_visible
        self._config['wheel_mode'] = self._wheel_mode
        self._config['wheel_enlarged'] = self._wheel_enlarged
        self._config['wheel_center_ring_visible'] = self._wheel_center_ring_visible
        self._config['wheel_middle_ring_visible'] = self._wheel_middle_ring_visible
        self._config['wheel_offset'] = self._wheel_offset
        # 网格大小
        self._config['grid_size'] = self.grid_size
        # 语音配置透传（voice_commands 等字段已在 _config 中，无需额外处理）

        profile_name = get_active_profile_name()
        save_profile(profile_name, self._config)

    # ── 按钮 CRUD ──

    def add_button(self, data=None, _toast=True):
        """新增按钮，自动找空位"""
        from models.button_model import ButtonData
        from scene.touch_button_item import TouchButtonItem

        gs = self.grid_size
        if data is None:
            data = ButtonData(name=t("button_defaults.name"), w=gs, h=gs)

        # 空位查找
        pos = self._find_empty_slot(data.w, data.h, start_x=data.x, start_y=data.y)
        if pos:
            data.x, data.y = pos

        offset_x = self.sceneRect().width() / 2
        offset_y = self.sceneRect().height() / 2
        item = TouchButtonItem(data, offset_x, offset_y)
        item.doubleClicked.connect(self._on_button_double_clicked)
        self.addItem(item)
        self.button_items.append(item)
        if _toast:
            self.toast_requested.emit(t("toast.created"))
        return item

    def add_center_band(self):
        """新增回中带按钮"""
        from models.button_model import ButtonData
        data = ButtonData(
            name=t("button_defaults.center_band"),
            btn_type=BTN_TYPE_CENTER_BAND,
            hover_delay=0,
            hover_release_delay=0,
        )
        pos = self._find_empty_slot(data.w, data.h)
        if pos:
            data.x, data.y = pos
        item = self.add_button(data, _toast=False)
        self.toast_requested.emit(t("toast.center_band_created"))
        return item

    def delete_button(self, item):
        """删除按钮"""
        if item in self.button_items:
            self.button_items.remove(item)
        self.removeItem(item)

    def copy_button(self, source):
        """复制按钮"""
        from models.button_model import ButtonData
        new_data = ButtonData.from_dict(source.data.to_dict())
        pos = self._find_empty_slot(new_data.w, new_data.h,
                                     start_x=new_data.x, start_y=new_data.y)
        if pos:
            new_data.x, new_data.y = pos
        item = self.add_button(new_data, _toast=False)
        self.toast_requested.emit(t("toast.copy_success"))
        return item

    def get_all_button_data(self):
        """导出所有按钮数据（用于保存配置）"""
        return [item.data.to_dict() for item in self.button_items]

    # ── 轮盘操作 ──

    def _update_wheel_controls(self):
        """更新轮盘样式管理按钮的位置和可见性"""
        show = self._wheel_visible and self.mode == 'edit' and len(self.wheel_items) > 0
        cx = self.sceneRect().width() / 2
        cy = self.sceneRect().height() / 2

        if self._wheel_style_btn is None:
            self._wheel_style_btn = _WheelStyleBtn(self._on_wheel_style_clicked)
            self._wheel_style_btn._tooltip_text = t("btn_tooltip.style_tooltip")
            self.addItem(self._wheel_style_btn)

        # 缩放按钮 — 懒创建
        if self._wheel_resize_btn is None:
            self._wheel_resize_btn = _WheelResizeBtn(self)
            self.addItem(self._wheel_resize_btn)

        # 按钮位置 — 基于外接正方形右下角
        eff_r = self._get_base_r_outer() + self._wheel_offset
        s = WHEEL_RESIZE_BTN_SIZE
        resize_x = cx + eff_r - s
        resize_y = cy + eff_r - s
        style_x = resize_x - 10 - s   # 设置按钮在缩放按钮左侧，间距10px
        style_y = resize_y            # 垂直对齐

        self._wheel_resize_btn.setPos(resize_x, resize_y)
        self._wheel_resize_btn.setVisible(show)
        self._wheel_style_btn.setPos(style_x, style_y)
        self._wheel_style_btn.setVisible(show)

    def _on_wheel_style_clicked(self):
        """打开轮盘样式管理弹窗"""
        from views.wheel_style_dialog import WheelStyleDialog

        # 临时降低 overlay 的置顶，避免与弹窗的 z-order 争夺
        overlay = None
        saved_flags = None
        views = self.views()
        if views:
            overlay = views[0].window()
            if overlay:
                saved_flags = overlay.windowFlags()
                overlay.setWindowFlags(saved_flags & ~_Qt.WindowType.WindowStaysOnTopHint)
                overlay.show()

        dlg = WheelStyleDialog(self._wheel_mode, self._wheel_center_ring_visible,
                               self._wheel_middle_ring_visible)
        if dlg.exec():
            result = dlg.get_result()
            if result:
                self.apply_wheel_style(result)

        # 恢复 overlay 置顶
        if overlay and saved_flags is not None:
            overlay.setWindowFlags(saved_flags)
            overlay.show()

    def apply_wheel_style(self, settings: dict):
        """应用轮盘样式设置（从弹窗返回的结果）"""
        new_mode = settings.get('wheel_mode', self._wheel_mode)
        new_ring_vis = settings.get('wheel_center_ring_visible', self._wheel_center_ring_visible)
        new_mid_vis = settings.get('wheel_middle_ring_visible', self._wheel_middle_ring_visible)

        # 重置八方向扇区键值
        reset_sectors = settings.get('reset_sectors', None)
        if reset_sectors and isinstance(reset_sectors, list):
            self._config['wheel_sectors'] = reset_sectors

        need_rebuild = (new_mode != self._wheel_mode) or (reset_sectors is not None)
        self._wheel_mode = new_mode
        self._wheel_enlarged = (new_mode in ('large', 'double'))
        self._wheel_center_ring_visible = new_ring_vis
        self._wheel_middle_ring_visible = new_mid_vis

        if need_rebuild:
            self._rebuild_wheel()

        # 更新中心环可见性
        self._update_ring_visibility()
        self._update_wheel_controls()

    def _update_ring_visibility(self):
        """更新中心环/内环的可见性"""
        if self.ring_item:
            if self._wheel_mode == 'double':
                # 双环: ring_item = 中二环
                visible = (self._wheel_visible and self._wheel_middle_ring_visible)
            else:
                # 单环: ring_item = 中心环
                visible = (self._wheel_visible and self._wheel_center_ring_visible)
            self.ring_item.setVisible(visible)
        if self.inner_ring_item:
            # 双环: inner_ring_item = 中心环（最内）
            visible = (self._wheel_visible and self._wheel_mode == 'double'
                       and self._wheel_center_ring_visible)
            self.inner_ring_item.setVisible(visible)

    def toggle_wheel(self):
        """切换轮盘显示/隐藏"""
        self._wheel_visible = not self._wheel_visible
        for item in self.wheel_items:
            item.setVisible(self._wheel_visible)
        self._update_ring_visibility()
        self._update_wheel_controls()
        return self._wheel_visible

    def toggle_wheel_size(self):
        """切换轮盘大小模式 — 需要重建轮盘 Item"""
        self._wheel_enlarged = not self._wheel_enlarged
        self._rebuild_wheel()
        self._update_wheel_controls()
        return self._wheel_enlarged

    def toggle_wheel_center_ring(self):
        """切换中心圆环显示"""
        self._wheel_center_ring_visible = not self._wheel_center_ring_visible
        if self.ring_item:
            visible = (self._wheel_visible and self._wheel_enlarged
                       and self._wheel_center_ring_visible)
            self.ring_item.setVisible(visible)
        self._update_wheel_controls()
        return self._wheel_center_ring_visible

    def _rebuild_wheel(self):
        """清除并重建轮盘 Item（切换模式时调用）"""
        # 移除旧 Item
        for item in self.wheel_items:
            self.removeItem(item)
        self.wheel_items.clear()
        if self.ring_item:
            self.removeItem(self.ring_item)
            self.ring_item = None
        if self.inner_ring_item:
            self.removeItem(self.inner_ring_item)
            self.inner_ring_item = None
        # 重新加载
        self._load_wheel(self._config)
        # 通知外部重新应用透明度等属性
        self.wheel_rebuilt.emit()

    @property
    def wheel_visible(self):
        return self._wheel_visible

    # ── 模式切换 ──

    def set_mode(self, mode: str):
        """切换编辑/运行模式"""
        self.hide_tooltip()
        self.mode = mode
        for item in self.button_items:
            item.set_mode(mode)
        for item in self.wheel_items:
            item.set_mode(mode)
        if self.ring_item:
            self.ring_item.set_mode(mode)
        if self.inner_ring_item:
            self.inner_ring_item.set_mode(mode)
        self._update_wheel_controls()
        self.invalidate()  # 触发重绘（更新网格背景）

    # ── Tooltip ──

    def show_tooltip(self, text: str, scene_pos):
        """显示场景内 Tooltip"""
        self._tooltip.show_text(text, scene_pos)

    def move_tooltip(self, scene_pos):
        """更新场景内 Tooltip 位置"""
        self._tooltip.move_to(scene_pos)

    def hide_tooltip(self):
        """隐藏场景内 Tooltip"""
        self._tooltip.hide_text()

    def update_auto_center_bar(self, progress, x, y):
        """更新自动回中倒计时进度条"""
        self._ac_bar.update_progress(progress, x, y)

    # ── 内部方法 ──

    def _get_base_r_outer(self):
        """获取当前轮盘模式的基础最大外径（不含 offset）"""
        if self._wheel_mode == 'double':
            return WHEEL_TRIPLE_SECTOR_OUTER
        elif self._wheel_mode == 'large':
            return WHEEL_OUTER_RADIUS_LARGE
        else:
            return WHEEL_OUTER_RADIUS

    def set_wheel_offset(self, new_offset):
        """设置轮盘缩放偏移并重建轮盘"""
        new_offset = max(0, min(WHEEL_MAX_OFFSET, int(new_offset)))
        if new_offset == self._wheel_offset:
            return
        self._wheel_offset = new_offset
        self._rebuild_wheel()
        self._update_wheel_controls()

    def _on_button_double_clicked(self, item):
        """按钮双击 → 转发信号"""
        self.button_double_clicked.emit(item)

    def set_grid_size(self, new_gs: int):
        """动态修改网格大小 — 先算格子数，再乘新 grid（以屏幕中心为原点）"""
        old_gs = self.grid_size
        if new_gs == old_gs:
            return
        self.grid_size = new_gs

        # 格子数不变，只是每格像素变了
        for item in self.button_items:
            cell_x = round(item.data.x / old_gs)
            cell_y = round(item.data.y / old_gs)
            cell_w = max(1, round(item.data.w / old_gs))
            cell_h = max(1, round(item.data.h / old_gs))
            item.data.x = cell_x * new_gs
            item.data.y = cell_y * new_gs
            item.data.w = cell_w * new_gs
            item.data.h = cell_h * new_gs
            item.setPos(item.data.x + item._offset_x, item.data.y + item._offset_y)
            item.prepareGeometryChange()
            item._update_handle_pos()
            item.update()

        # 重绘网格
        self.invalidate()

    def _find_empty_slot(self, w, h, start_x=0, start_y=0):
        """在网格上查找不与现有按钮重叠的空位（逻辑坐标，中心原点）。"""
        gs = self.grid_size
        scene_rect = self.sceneRect()
        ox = scene_rect.width() / 2
        oy = scene_rect.height() / 2
        screen_w = scene_rect.width()
        screen_h = scene_rect.height()

        min_lx = -ox
        min_ly = -oy
        max_lx = screen_w - w - ox
        max_ly = screen_h - h - oy

        occupied = [(item.data.x, item.data.y, item.data.w, item.data.h)
                    for item in self.button_items]

        def overlaps(nx, ny):
            for bx, by, bw, bh in occupied:
                if not (nx + w <= bx or nx >= bx + bw or ny + h <= by or ny >= by + bh):
                    return True
            return False

        def in_bounds(nx, ny):
            return min_lx <= nx <= max_lx and min_ly <= ny <= max_ly

        cx = round(start_x / gs) * gs
        cy = round(start_y / gs) * gs

        if in_bounds(cx, cy) and not overlaps(cx, cy):
            return (cx, cy)

        max_radius = max(int(screen_w), int(screen_h)) // gs
        for ring in range(1, max_radius + 1):
            for dx in range(-ring, ring + 1):
                for dy in [-ring, ring]:
                    nx, ny = cx + dx * gs, cy + dy * gs
                    if in_bounds(nx, ny) and not overlaps(nx, ny):
                        return (nx, ny)
            for dy in range(-ring + 1, ring):
                for dx in [-ring, ring]:
                    nx, ny = cx + dx * gs, cy + dy * gs
                    if in_bounds(nx, ny) and not overlaps(nx, ny):
                        return (nx, ny)

        return None
