"""
TEGG Touch 蛋挞 (PyQt6) - toolbar_tip_widget.py
工具栏下方固定位置 Tip 浮窗 — 复刻原版 Tkinter _show_tip/_hide_tip。

原版行为: 鼠标 hover 工具栏按钮时，在工具栏正下方居中显示描述文字。
"""

from PyQt6.QtWidgets import QLabel, QApplication
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QPainterPath

from core.i18n import get_font

# tip 与工具栏的间距
_GAP = 6
# 内边距
_PAD_H = 14
_PAD_V = 6
# 圆角
_RADIUS = 4


class ToolbarTipWidget(QLabel):
    """工具栏正上方固定位置 tip 浮窗 — 复刻原版 _show_tip/_hide_tip。

    用法:
        tip = ToolbarTipWidget()
        tip.show_tip("描述文字", toolbar_widget)
        tip.hide_tip()
    """

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
        font.setPixelSize(13)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 不用 stylesheet 的 background (WA_TranslucentBackground 下不可靠)
        # 改为 paintEvent 手绘背景
        self.setStyleSheet("background: transparent; color: transparent;")

    # ── 手绘背景 + 文字 ─────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)

        # 背景
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(),
                            _RADIUS, _RADIUS)
        p.fillPath(path, QColor("#1A1A1A"))

        # 边框
        p.setPen(QPen(QColor("#444"), 1))
        p.drawPath(path)

        # 文字
        p.setPen(QColor("#E0E0E0"))
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()

    # ── 显示 / 隐藏 ─────────────────────────────────────────

    def show_tip(self, text: str, toolbar):
        """在 toolbar 正上方居中显示 tip 文字。"""
        if not text:
            self.hide_tip()
            return

        self.setText(text)

        # 计算尺寸
        fm = self.fontMetrics()
        tw = fm.horizontalAdvance(text) + _PAD_H * 2 + 4
        th = fm.height() + _PAD_V * 2 + 4
        self.setFixedSize(tw, th)

        # 获取工具栏的全局坐标
        tb_geo = toolbar.frameGeometry()
        tb_x = tb_geo.x()
        tb_y = tb_geo.y()
        tb_w = tb_geo.width()

        # 居中于工具栏正上方, 间距 _GAP
        tip_x = tb_x + (tb_w - tw) // 2
        tip_y = tb_y - th - _GAP

        # 如果上方空间不够 (极端情况)，放到下方
        if tip_y < 0:
            tip_y = tb_geo.y() + tb_geo.height() + _GAP

        self.move(tip_x, tip_y)
        self.show()
        self.raise_()

    def hide_tip(self):
        """隐藏 tip。"""
        self.hide()
