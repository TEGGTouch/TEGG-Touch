"""
TEGG Touch 蛋挞 (PyQt6) - toast_widget.py
屏幕中央 Toast 通知 — 添加/复制按钮时短暂显示。
"""

from PyQt6.QtWidgets import QLabel, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from core.i18n import get_font


class ToastWidget(QLabel):
    """屏幕中央 Toast 通知"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        fn = get_font()
        font = QFont(fn)
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.Bold)
        self.setFont(font)

        self.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 128);
                color: #FFF;
                padding: 16px 40px;
                border-radius: 8px;
            }
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_toast(self, text, duration=1500):
        """显示 toast 文本，duration ms 后自动隐藏"""
        self.setText(text)
        self.adjustSize()

        # 居中屏幕
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

        self.show()
        self.raise_()
        self._timer.start(duration)
