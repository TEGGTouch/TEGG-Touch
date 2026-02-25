"""
TEGG Touch 蛋挞 (PyQt6) - center_band_item.py
回中带按钮 — 鼠标进入即刻将光标回中。

注意: 回中带实际使用 TouchButtonItem 统一处理（btn_type == center_band），
本文件仅作为独立组件的参考实现，当前不直接使用。
"""

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from core.i18n import t, get_font
from models.button_model import ButtonData


# 回中带专用配色
COLOR_CENTER_BAND = "#176F2C"
COLOR_CENTER_BAND_BG = "#0A2E12"


class CenterBandItem(QGraphicsObject):
    """回中带按钮 — 鼠标进入即刻将光标回中

    绘制: 深绿背景 + 绿色边框 + ⊕ 回中带 文字
    交互: 运行模式下，鼠标进入 → SetCursorPos(center)
    """

    hoverEntered = pyqtSignal(object)
    doubleClicked = pyqtSignal(object)
    data_changed = pyqtSignal()

    def __init__(self, data: ButtonData, offset_x=0, offset_y=0):
        super().__init__()
        self.data = data
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._mode = 'edit'

        self.setPos(data.x + offset_x, data.y + offset_y)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        from scene.resize_handle_item import ResizeHandleItem
        self._resize_handle = ResizeHandleItem(self)
        self._update_handle_pos()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.data.w, self.data.h)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.boundingRect().adjusted(5, 5, -5, -5)
        painter.setPen(QPen(QColor(COLOR_CENTER_BAND), 2))
        painter.setBrush(QBrush(QColor(COLOR_CENTER_BAND_BG)))
        painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(QColor(COLOR_CENTER_BAND))
        painter.setFont(QFont(get_font(), 10, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         t("canvas.center_band_label"))

    def set_mode(self, mode: str):
        self._mode = mode
        movable = (mode == 'edit')
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)
        self._resize_handle.setVisible(movable)
        self.update()

    def _update_handle_pos(self):
        self._resize_handle.setPos(self.data.w - 20, self.data.h - 20)

    def resize_to(self, new_w, new_h):
        from core.constants import DEFAULT_GRID_SIZE
        gs = self.scene().grid_size if self.scene() else DEFAULT_GRID_SIZE
        self.prepareGeometryChange()
        self.data.w = max(gs, new_w)
        self.data.h = max(gs, new_h)
        self._update_handle_pos()
        self.update()
        self.data_changed.emit()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self._mode == 'edit':
                from core.constants import DEFAULT_GRID_SIZE
                gs = self.scene().grid_size if self.scene() else DEFAULT_GRID_SIZE
                from PyQt6.QtCore import QPointF
                new_pos = QPointF(
                    round(value.x() / gs) * gs,
                    round(value.y() / gs) * gs
                )
                self.data.x = new_pos.x() - self._offset_x
                self.data.y = new_pos.y() - self._offset_y
                return new_pos
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        if self._mode == 'edit':
            self.doubleClicked.emit(self)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._mode == 'edit':
            self.data_changed.emit()
