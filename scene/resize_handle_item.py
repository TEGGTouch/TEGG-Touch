"""
TEGG Touch 蛋挞 (PyQt6) - resize_handle_item.py
右下角三角形缩放手柄 — 作为按钮的子 Item，随父 Item 移动。
"""

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QCursor

from core.constants import (
    DEFAULT_GRID_SIZE, BTN_TYPE_CENTER_BAND,
    BTN_TYPE_GP_BUTTON, BTN_TYPE_GP_STICK, BTN_TYPE_GP_WHEEL,
    COLOR_GP_BTN_BORDER,
)


# 缩放手柄颜色: 跟随按钮类型, 视觉一致
_COLOR_HANDLE_DEFAULT = "#555555"
_COLOR_HANDLE_CENTER_BAND = "#176F2C"        # 与回中带边框一致
_COLOR_HANDLE_GP = COLOR_GP_BTN_BORDER       # 与手柄键/摇杆边框一致 (蓝)


class ResizeHandleItem(QGraphicsItem):
    """右下角三角形缩放手柄 — 作为按钮的子 Item，随父 Item 移动

    旧版: canvas.create_polygon(三角形) + tag_bind + 手动计算坐标
    新版: 子 Item，自动跟随父 Item，事件独立处理
    """
    SIZE = 20

    def __init__(self, parent_button):
        super().__init__(parent_button)
        self._parent_btn = parent_button
        self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        s = self.SIZE
        path.moveTo(s, 0)
        path.lineTo(s, s)
        path.lineTo(0, s)
        path.closeSubpath()
        # 手柄颜色跟随按钮类型: 回中带绿 / 手柄键 + 摇杆蓝 / 其他灰
        btn_type = (getattr(self._parent_btn.data, 'btn_type', '')
                    if hasattr(self._parent_btn, 'data') else '')
        if btn_type == BTN_TYPE_CENTER_BAND:
            color = _COLOR_HANDLE_CENTER_BAND
        elif btn_type in (BTN_TYPE_GP_BUTTON, BTN_TYPE_GP_STICK, BTN_TYPE_GP_WHEEL):
            color = _COLOR_HANDLE_GP
        else:
            color = _COLOR_HANDLE_DEFAULT
        painter.fillPath(path, QColor(color))

    def mousePressEvent(self, event):
        event.accept()  # 拦截，不传给父 Item

    def mouseMoveEvent(self, event):
        """拖拽缩放，网格吸附"""
        gs = self._parent_btn.scene().grid_size if self._parent_btn.scene() else DEFAULT_GRID_SIZE
        scene_pos = event.scenePos()
        parent_pos = self._parent_btn.scenePos()

        new_w = max(gs, round((scene_pos.x() - parent_pos.x()) / gs) * gs)
        new_h = max(gs, round((scene_pos.y() - parent_pos.y()) / gs) * gs)

        self._parent_btn.resize_to(new_w, new_h)

    def mouseReleaseEvent(self, event):
        event.accept()
