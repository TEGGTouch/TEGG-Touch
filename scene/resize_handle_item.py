"""
TEGG Touch 蛋挞 (PyQt6) - resize_handle_item.py
右下角三角形缩放手柄 — 作为按钮的子 Item，随父 Item 移动。
"""

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QCursor

from core.constants import DEFAULT_GRID_SIZE, BTN_TYPE_CENTER_BAND


# 回中带手柄颜色 — 与回中带边框一致
_COLOR_HANDLE_DEFAULT = "#555555"
_COLOR_HANDLE_CENTER_BAND = "#176F2C"


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
        # 回中带使用绿色手柄，普通按钮使用灰色
        is_band = (hasattr(self._parent_btn, 'data')
                   and getattr(self._parent_btn.data, 'btn_type', '') == BTN_TYPE_CENTER_BAND)
        color = _COLOR_HANDLE_CENTER_BAND if is_band else _COLOR_HANDLE_DEFAULT
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
