"""
TEGGTouch 蛋挞 — 语音输入提示小窗 (唤醒词「蛋挞」后弹出)

无操作按钮, 纯状态展示: 在听 → 识别中 → (听到的文字一闪) → 关闭。
由 OverlayWindow 持有一个实例, 据 VoiceWakeEngine 的状态 show/update/hide。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont

from core.i18n import get_font


def _make_font(name, px, bold=False):
    f = QFont(name)
    screen = QApplication.primaryScreen()
    dpi = screen.logicalDotsPerInch() if screen else 96.0
    f.setPointSizeF(px * 72.0 / dpi)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class VoiceInputPopup(QDialog):
    """语音输入状态小窗 (无按钮, 只展示状态)。"""

    WIN_W = 380

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._init_ui()

    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        box = QFrame()
        box.setObjectName("voice_box")
        box.setStyleSheet("""
            QFrame#voice_box {
                background: #241E12; border: 2px solid #F59E0B; border-radius: 10px;
            }
        """)
        outer.addWidget(box)

        root = QVBoxLayout(box)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(8)

        self._title = QLabel("🎤 在听…")
        self._title.setFont(_make_font(fn, 17, bold=True))
        self._title.setStyleSheet("color:#F5D9A0; background:transparent; border:none;")
        root.addWidget(self._title)

        self._hint = QLabel("说完停一下会自动结束")
        self._hint.setWordWrap(True)
        self._hint.setFont(_make_font(fn, 12))
        self._hint.setStyleSheet("color:#9C8A63; background:transparent; border:none;")
        root.addWidget(self._hint)

    # ── 状态更新 ──
    def show_listening(self):
        self._title.setText("🎤 在听…")
        self._hint.setText("说完停一下会自动结束")
        self._pop()

    def show_recognizing(self):
        self._title.setText("✍ 识别中…")
        self._hint.setText("正在把语音转成文字")

    def show_text(self, text: str):
        """短暂显示听到的文字 (发送前的反馈)。"""
        self._title.setText("✓ 听到")
        self._hint.setText(text or "(没听清)")

    def _pop(self):
        self.setFixedWidth(self.WIN_W)
        self.adjustSize()
        ps = QApplication.primaryScreen()
        scr = ps.availableGeometry() if ps else QRect(0, 0, 1920, 1080)
        self.move(scr.left() + (scr.width() - self.width()) // 2,
                  scr.top() + (scr.height() - self.height()) // 3)
        self.show()
        self.raise_()
