"""
TEGG Touch 蛋挞 (PyQt6) - virtual_cursor_item.py
屏幕中心十字准星 — 跟踪实际光标或固定在中心。
"""

import os

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import QRectF, QTimer, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QColor, QCursor, QPixmap

from core.constants import APP_DIR


class VirtualCursorItem(QGraphicsItem):
    """屏幕中心的十字准星"""

    SIZE = 30

    def __init__(self, cursor_type='cursor'):
        super().__init__()
        self.setZValue(100)  # 始终在最上层

        self._cursor_type = cursor_type  # 'crosshair' | 'cursor' | 'cursor_off' | 'cursor_block'
        self._pixmap = None

        # 尝试加载自定义光标图片
        self._load_cursor_image()

        # 位置跟踪定时器
        self._tracker = QTimer()
        self._tracker.setInterval(16)  # ~60fps
        self._tracker.timeout.connect(self._update_pos)

    def _load_cursor_image(self):
        """尝试加载光标图片"""
        cursor_map = {
            'cursor': 'cursor.png',
            'cursor_off': 'cursor_off.png',
            'cursor_block': 'cursor_block.png',
        }
        filename = cursor_map.get(self._cursor_type)
        if filename:
            path = os.path.join(APP_DIR, 'assets', filename)
            if os.path.exists(path):
                self._pixmap = QPixmap(path)

    def boundingRect(self) -> QRectF:
        s = self.SIZE
        return QRectF(0, 0, s, s)

    def shape(self):
        """返回空路径 → scene.itemAt() 不会命中虚拟光标，穿透到下方的按钮"""
        return QPainterPath()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._pixmap and not self._pixmap.isNull():
            # 使用自定义光标图片 — 左上角对齐 OS 光标热点
            s = self.SIZE
            painter.drawPixmap(0, 0, s, s, self._pixmap)
        else:
            # 默认十字准星 — 左上角对齐 OS 光标热点
            s = self.SIZE // 2
            pen = QPen(QColor("#FF0000"), 2)
            painter.setPen(pen)
            # 十字
            painter.drawLine(0, s, s * 2, s)
            painter.drawLine(s, 0, s, s * 2)
            # 圆
            painter.drawEllipse(s // 2, s // 2, s, s)

    def set_cursor_type(self, cursor_type: str):
        """切换光标类型"""
        self._cursor_type = cursor_type
        self._load_cursor_image()
        self.update()

    def start_tracking(self):
        """开始跟踪光标位置"""
        self._tracker.start()
        self.setVisible(True)

    def stop_tracking(self):
        """停止跟踪"""
        self._tracker.stop()
        self.setVisible(False)

    def _update_pos(self):
        """更新位置到当前鼠标坐标"""
        pos = QCursor.pos()
        self.setPos(pos.x(), pos.y())
