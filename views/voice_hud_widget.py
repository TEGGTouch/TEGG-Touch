"""
TEGG Touch 蛋挞 (PyQt6) - voice_hud_widget.py
运行模式语音指令反馈 HUD — 弹跳动画效果，类似游戏伤害数字。
"""

from PyQt6.QtWidgets import QLabel, QApplication, QGraphicsOpacityEffect
from PyQt6.QtCore import (
    Qt, QPoint, QPropertyAnimation, QSequentialAnimationGroup,
    QEasingCurve, QByteArray,
)
from PyQt6.QtGui import QFont, QPainter, QColor, QPen

from core.i18n import t, get_font


class _PopLabel(QLabel):
    """独立弹跳标签 — 每次指令创建一个，动画结束自动销毁。"""

    def __init__(self, text: str, start_pos: QPoint, end_pos: QPoint):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        fn = get_font()
        font = QFont(fn)
        font.setPixelSize(28)
        font.setWeight(QFont.Weight.Bold)
        self.setFont(font)

        self.setStyleSheet("""
            QLabel {
                background: transparent;
                color: #00D4FF;
            }
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._text = text
        self.setText(text)
        self.adjustSize()
        # 加宽一点防止描边被裁
        self.resize(self.width() + 8, self.height() + 4)

        self.move(start_pos)

        # --- opacity effect ---
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # --- 弹出动画: pos  0~300ms  EaseOutCubic ---
        self._anim_pos = QPropertyAnimation(self, QByteArray(b"pos"))
        self._anim_pos.setDuration(300)
        self._anim_pos.setStartValue(start_pos)
        self._anim_pos.setEndValue(end_pos)
        self._anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        # --- 淡出动画: opacity  300~1500ms → duration 1200ms  EaseInQuad ---
        self._anim_fade = QPropertyAnimation(
            self._opacity_effect, QByteArray(b"opacity")
        )
        self._anim_fade.setDuration(1200)
        self._anim_fade.setStartValue(1.0)
        self._anim_fade.setEndValue(0.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.InQuad)

        # --- 组合: 先弹出 → 再淡出 ---
        self._group = QSequentialAnimationGroup(self)
        self._group.addAnimation(self._anim_pos)
        self._group.addAnimation(self._anim_fade)
        self._group.finished.connect(self.close)

    def start(self):
        self.show()
        self.raise_()
        self._group.start()

    def paintEvent(self, event):
        """绘制文字描边（黑色轮廓）增强可读性。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())

        rect = self.rect()

        # 黑色描边
        pen = QPen(QColor(0, 0, 0, 200))
        pen.setWidth(3)
        painter.setPen(pen)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                painter.drawText(rect.translated(dx, dy), self.alignment(), self._text)

        # 正文
        painter.setPen(QColor("#00D4FF"))
        painter.drawText(rect, self.alignment(), self._text)
        painter.end()


class VoiceHudWidget:
    """语音指令 HUD 管理器 — 每次 show_command 创建独立弹跳标签。"""

    def __init__(self, parent=None):
        # parent 不再使用，保留参数兼容调用方
        pass

    def show_command(self, phrase: str, keys: str, action: str, duration=1500):
        """创建弹跳标签并启动动画。"""
        action_map = {
            "click": t("voice_dialog.action_click"),
            "press": t("voice_dialog.action_press"),
            "release": t("voice_dialog.action_release"),
        }
        action_text = action_map.get(action, action)
        text = f"{phrase}  \u2192  {keys}  [{action_text}]"

        screen = QApplication.primaryScreen().geometry()
        # 用临时 QLabel 测量文字宽度
        tmp = QLabel(text)
        fn = get_font()
        font = QFont(fn)
        font.setPixelSize(28)
        font.setWeight(QFont.Weight.Bold)
        tmp.setFont(font)
        tmp.adjustSize()
        w = tmp.width() + 8

        cx = (screen.width() - w) // 2
        start_y = screen.height() // 2 - 260
        end_y = screen.height() // 2 - 300

        label = _PopLabel(
            text,
            start_pos=QPoint(cx, start_y),
            end_pos=QPoint(cx, end_y),
        )
        label.start()
