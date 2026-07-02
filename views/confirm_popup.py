"""
TEGG Touch 蛋挞 — Agent 执行确认弹窗 (独立小窗, 不塞在聊天框里)

文案: 即将【描述】。语音开启时可通过 执行/取消 操作。
按钮: 执行(橙, 同发送/启动) / 取消(灰)。点击 → confirmed(bool)。
由 OverlayWindow 持有一个实例, 需要时 set_text + show, resolve 后 hide。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
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


class ConfirmPopup(QDialog):
    """执行确认独立弹窗。confirmed(True)=执行 / confirmed(False)=取消。"""

    confirmed = pyqtSignal(bool)

    WIN_W = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._init_ui()

    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        box = QFrame()
        box.setObjectName("confirm_container")
        box.setStyleSheet("""
            QFrame#confirm_container {
                background: #241E12; border: 2px solid #F59E0B; border-radius: 10px;
            }
        """)
        outer.addWidget(box)

        root = QVBoxLayout(box)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setFont(_make_font(fn, 16, bold=True))
        self._msg.setStyleSheet("color: #F5D9A0; background: transparent; border: none;")
        root.addWidget(self._msg)

        self._hint = QLabel("语音开启时可通过 “确认 / 取消” 操作")
        self._hint.setFont(_make_font(fn, 12))
        self._hint.setStyleSheet("color: #9C8A63; background: transparent; border: none;")
        root.addWidget(self._hint)

        # 常态 / 高亮(语音命中时闪一下) 样式
        self._CANCEL_CSS = ("QPushButton{background:#3A3A3A;color:#DDD;border:2px solid #3A3A3A;"
                            "border-radius:8px;} QPushButton:hover{background:#4A4A4A;}")
        self._CANCEL_HL = ("QPushButton{background:#6B6B6B;color:#FFF;border:2px solid #FFF;"
                           "border-radius:8px;}")
        self._RUN_CSS = ("QPushButton{background:#D97706;color:#FFF;border:2px solid #D97706;"
                         "border-radius:8px;} QPushButton:hover{background:#F59E0B;}")
        self._RUN_HL = ("QPushButton{background:#F59E0B;color:#FFF;border:2px solid #FFF;"
                        "border-radius:8px;}")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedHeight(42)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setFont(_make_font(fn, 15))
        self._cancel_btn.setStyleSheet(self._CANCEL_CSS)
        self._cancel_btn.clicked.connect(lambda: self._resolve(False))
        btn_row.addWidget(self._cancel_btn, 1)

        self._run_btn = QPushButton("确认")
        self._run_btn.setFixedHeight(42)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setFont(_make_font(fn, 15, bold=True))
        self._run_btn.setStyleSheet(self._RUN_CSS)
        self._run_btn.clicked.connect(lambda: self._resolve(True))
        btn_row.addWidget(self._run_btn, 1)
        root.addLayout(btn_row)

    def prompt(self, desc: str):
        """设置文案并弹出居中置顶。"""
        self._run_btn.setStyleSheet(self._RUN_CSS)      # 复位上次的高亮
        self._cancel_btn.setStyleSheet(self._CANCEL_CSS)
        self._msg.setText(f"即将{desc}")
        self.setFixedWidth(self.WIN_W)
        self.adjustSize()
        self._center()
        self.show()
        self.raise_()
        self.activateWindow()

    def _resolve(self, ok: bool):
        self.hide()
        self.confirmed.emit(ok)

    def resolve_by_voice(self, ok: bool):
        """语音命中: 先高亮对应按钮闪一下, 再关闭并 resolve (给用户视觉反馈)。"""
        if not self.isVisible():
            self._resolve(ok)
            return
        if ok:
            self._run_btn.setStyleSheet(self._RUN_HL)
        else:
            self._cancel_btn.setStyleSheet(self._CANCEL_HL)
        QTimer.singleShot(280, lambda: self._resolve(ok))

    def _center(self):
        ps = QApplication.primaryScreen()
        scr = ps.availableGeometry() if ps else QRect(0, 0, 1920, 1080)
        self.move(scr.left() + (scr.width() - self.width()) // 2,
                  scr.top() + (scr.height() - self.height()) // 3)

    # 拖拽
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)
