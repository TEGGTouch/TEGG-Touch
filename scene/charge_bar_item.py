"""
TEGG Touch 蛋挞 (PyQt6) - charge_bar_item.py
独立的充能进度条 — 可以附加到任何 Item 上。
"""

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QColor


class ChargeBarItem(QGraphicsItem):
    """独立充能进度条 — 作为子 Item 附加到按钮底部"""

    def __init__(self, parent_item, width=80, height=6):
        super().__init__(parent_item)
        self._width = width
        self._height = height
        self._progress = 0.0
        self._color = QColor("#0284C7")
        self._bg_color = QColor("#333333")

        # 定位在父 Item 底部居中
        parent_rect = parent_item.boundingRect()
        self.setPos(
            (parent_rect.width() - width) / 2,
            parent_rect.height() + 4
        )

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    def set_progress(self, val: float):
        """设置进度 0.0 ~ 1.0"""
        self._progress = max(0.0, min(1.0, val))
        self.update()

    def set_color(self, color_str: str):
        """设置进度条颜色"""
        self._color = QColor(color_str)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(
            QRectF(0, 0, self._width, self._height), 3, 3)

        # 进度
        if self._progress > 0.01:
            painter.setBrush(self._color)
            painter.drawRoundedRect(
                QRectF(0, 0, self._width * self._progress, self._height), 3, 3)
