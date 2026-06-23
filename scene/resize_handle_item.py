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
)
from core import button_theme


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
        # 手柄颜色跟随各组「描边色」(用户可调): 回中带 / 手柄(键+摇杆) / 方向盘 / 其他(按键)
        btn_type = (getattr(self._parent_btn.data, 'btn_type', '')
                    if hasattr(self._parent_btn, 'data') else '')
        if btn_type == BTN_TYPE_CENTER_BAND:
            color = button_theme.center_band()['border']
        elif btn_type in (BTN_TYPE_GP_BUTTON, BTN_TYPE_GP_STICK):
            color = button_theme.gamepad()['border']
        elif btn_type == BTN_TYPE_GP_WHEEL:
            color = button_theme.wheel()['border']
        else:
            color = button_theme.keyboard()['border']
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
