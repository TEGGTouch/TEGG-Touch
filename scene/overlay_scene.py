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
    BTN_TYPE_CENTER_BAND,
    WHEEL_INNER_RADIUS, WHEEL_OUTER_RADIUS,
    WHEEL_INNER_RADIUS_LARGE, WHEEL_OUTER_RADIUS_LARGE,
    WHEEL_RING_INNER, WHEEL_RING_OUTER,
    WHEEL_SECTOR_COUNT,
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

# 原版图标码点
_ICON_ZOOM_IN  = "\uE8A3"   # ZoomIn  放大镜+  (当前为小版 → 点击放大)
_ICON_ZOOM_OUT = "\uE71F"   # ZoomOut 放大镜−  (当前为大版 → 点击缩小)
_ZOOM_ICON_SIZE = 14
_BTN_SIZE = 30


class _WheelZoomBtn(QGraphicsObject):
    """轮盘缩放切换按钮 — 匹配原版 draw_wheel_zoom_button
    灰色圆角矩形底, Segoe Fluent Icons 放大镜图标, fallback +/−
    """

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._enlarged = False
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setCursor(_Qt.CursorShape.PointingHandCursor)
        self.setZValue(50)

    def set_enlarged(self, enlarged):
        self._enlarged = enlarged
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, _BTN_SIZE, _BTN_SIZE)

    def paint(self, painter: _QPainter, option, widget=None):
        painter.setRenderHint(_QPainter.RenderHint.Antialiasing)
        bg = _QColor("#777777") if self._hover else _QColor("#666666")
        painter.setPen(_Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(self.boundingRect(), 6, 6)

        ifont = _detect_icon_font()
        if ifont:
            icon_ch = _ICON_ZOOM_OUT if self._enlarged else _ICON_ZOOM_IN
            painter.setPen(_QColor("#E0E0E0"))
            painter.setFont(_QFont(ifont, _ZOOM_ICON_SIZE))
            painter.drawText(self.boundingRect(), _Qt.AlignmentFlag.AlignCenter, icon_ch)
        else:
            # fallback: +/−
            text = "\u2212" if self._enlarged else "+"
            painter.setPen(_QColor("#E0E0E0"))
            from core.i18n import get_font as _gf
            painter.setFont(_QFont(_gf(), 14, _QFont.Weight.Bold))
            painter.drawText(self.boundingRect(), _Qt.AlignmentFlag.AlignCenter, text)

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


class _WheelRingToggleBtn(QGraphicsObject):
    """中心环开关按钮 — 匹配原版 draw_wheel_ring_toggle_button
    圆角矩形底 (蓝/灰切换), 圆形 ⭕ 图标 (canvas.create_oval)
    """

    _COLOR_ON  = "#005A9E"
    _COLOR_OFF = "#666666"

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._ring_visible = False
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setCursor(_Qt.CursorShape.PointingHandCursor)
        self.setZValue(50)

    def set_ring_visible(self, visible):
        self._ring_visible = visible
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, _BTN_SIZE, _BTN_SIZE)

    def paint(self, painter: _QPainter, option, widget=None):
        painter.setRenderHint(_QPainter.RenderHint.Antialiasing)
        base = self._COLOR_ON if self._ring_visible else self._COLOR_OFF
        bg = _QColor(base).lighter(120) if self._hover else _QColor(base)
        painter.setPen(_Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(self.boundingRect(), 6, 6)

        # ⭕ 图标: 空心圆, 半径 7, 描边 #E0E0E0 宽 2
        icon_r = 7
        cx = _BTN_SIZE / 2
        cy = _BTN_SIZE / 2
        painter.setPen(_QPen(_QColor("#E0E0E0"), 2))
        painter.setBrush(_Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(cx - icon_r), int(cy - icon_r),
                            icon_r * 2, icon_r * 2)

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

    def __init__(self):
        super().__init__()
        self.mode = 'edit'  # 'edit' | 'run'
        self.grid_size = DEFAULT_GRID_SIZE
        self.button_items = []
        self.wheel_items = []
        self.ring_item = None
        self._config = {}           # 保存完整配置引用
        self._wheel_visible = False
        self._wheel_enlarged = False
        self._wheel_center_ring_visible = False
        self._wheel_zoom_btn = None
        self._wheel_ring_btn = None

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
            if btn_type in (BTN_TYPE_WHEEL_SECTOR, BTN_TYPE_WHEEL_RING):
                continue

            data = ButtonData.from_dict(btn_dict)
            item = TouchButtonItem(data, offset_x, offset_y)
            item.doubleClicked.connect(self._on_button_double_clicked)
            self.addItem(item)
            self.button_items.append(item)

        # 加载轮盘
        self._wheel_visible = config.get('wheel_visible', False)
        self._wheel_enlarged = config.get('wheel_enlarged', False)
        self._wheel_center_ring_visible = config.get('wheel_center_ring_visible', False)
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

        # 根据大小模式选择半径
        if self._wheel_enlarged:
            r_inner = WHEEL_INNER_RADIUS_LARGE
            r_outer = WHEEL_OUTER_RADIUS_LARGE
        else:
            r_inner = WHEEL_INNER_RADIUS
            r_outer = WHEEL_OUTER_RADIUS

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

        # 中心圆环（仅大轮盘模式）
        ring_dict = config.get('wheel_center_ring', {})
        if ring_dict:
            ring_data = WheelRingData.from_dict(ring_dict)
            ring_r_inner = WHEEL_RING_INNER
            ring_r_outer = WHEEL_RING_OUTER
            self.ring_item = WheelRingItem(ring_data, cx, cy,
                                           ring_r_inner, ring_r_outer)
            self.ring_item.doubleClicked.connect(self._on_button_double_clicked)
            visible = (self._wheel_visible and self._wheel_enlarged
                       and self._wheel_center_ring_visible)
            self.ring_item.setVisible(visible)
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

        # 中心圆环数据
        if self.ring_item:
            self._config['wheel_center_ring'] = self.ring_item.data.to_dict()

        # 轮盘显示状态
        self._config['wheel_visible'] = self._wheel_visible
        self._config['wheel_enlarged'] = self._wheel_enlarged
        self._config['wheel_center_ring_visible'] = self._wheel_center_ring_visible
        # 网格大小
        self._config['grid_size'] = self.grid_size

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
        """更新轮盘控制按钮的位置和可见性 (匹配原版 draw_wheel_zoom_button / ring_toggle_button)"""
        show = self._wheel_visible and self.mode == 'edit' and len(self.wheel_items) > 0
        cx = self.sceneRect().width() / 2
        cy = self.sceneRect().height() / 2

        if self._wheel_zoom_btn is None:
            self._wheel_zoom_btn = _WheelZoomBtn(self._on_wheel_zoom_clicked)
            self._wheel_zoom_btn._tooltip_text = t("btn_tooltip.zoom_tooltip")
            self.addItem(self._wheel_zoom_btn)

        if self._wheel_ring_btn is None:
            self._wheel_ring_btn = _WheelRingToggleBtn(self._on_wheel_ring_clicked)
            self._wheel_ring_btn._tooltip_text = t("btn_tooltip.ring_tooltip")
            self.addItem(self._wheel_ring_btn)

        # 同步状态
        self._wheel_zoom_btn.set_enlarged(self._wheel_enlarged)
        self._wheel_ring_btn.set_ring_visible(self._wheel_center_ring_visible)

        # 位置: 原版 cx+165, cy+165 (zoom) 和 cx+130, cy+165 (ring)
        self._wheel_zoom_btn.setPos(cx + 165, cy + 165)
        self._wheel_ring_btn.setPos(cx + 130, cy + 165)

        self._wheel_zoom_btn.setVisible(show)
        # 圆环按钮仅在大轮盘模式下显示
        self._wheel_ring_btn.setVisible(show and self._wheel_enlarged)

    def _on_wheel_zoom_clicked(self):
        self.toggle_wheel_size()
        self._update_wheel_controls()

    def _on_wheel_ring_clicked(self):
        self.toggle_wheel_center_ring()
        self._update_wheel_controls()

    def toggle_wheel(self):
        """切换轮盘显示/隐藏"""
        self._wheel_visible = not self._wheel_visible
        for item in self.wheel_items:
            item.setVisible(self._wheel_visible)
        if self.ring_item:
            visible = (self._wheel_visible and self._wheel_enlarged
                       and self._wheel_center_ring_visible)
            self.ring_item.setVisible(visible)
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
        """清除并重建轮盘 Item（切换大小时调用）"""
        # 移除旧 Item
        for item in self.wheel_items:
            self.removeItem(item)
        self.wheel_items.clear()
        if self.ring_item:
            self.removeItem(self.ring_item)
            self.ring_item = None
        # 重新加载
        self._load_wheel(self._config)

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
