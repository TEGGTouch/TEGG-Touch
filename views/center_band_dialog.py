"""
TEGG Touch 蛋挞 (PyQt6) - center_band_dialog.py
回中带专用简化编辑弹窗 — 400×280, 无属性编辑字段。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.i18n import t, get_font


def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class CenterBandDialog(QDialog):
    """回中带专用简化编辑弹窗 — 匹配原版 400×280 布局"""

    deleted = pyqtSignal(object)
    copied = pyqtSignal(object)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self._item = item

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(400, 280)

        self._init_ui()
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self):
        fn = get_font()

        # 外层透明
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("cb_container")
        container.setStyleSheet("""
            QFrame#cb_container {
                background: #2D2D2D;
                border-radius: 4px;
                border: 1px solid #444;
            }
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # ── 标题栏: 弹簧 + 关闭按钮 ──
        header = QHBoxLayout()
        header.addStretch()
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFont(_make_font(fn, 14, bold=True))
        close_btn.setStyleSheet("""
            QPushButton {
                background: #6E1E1E; color: #FFF;
                border: none; border-radius: 6px;
            }
            QPushButton:hover { background: #8B2020; }
        """)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        root.addLayout(header)

        # ── 绿色标题 ──
        title = QLabel(t("editor.center_band_title"))
        title.setFont(_make_font(fn, 14, bold=True))
        title.setStyleSheet("color: #176F2C; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        # ── 说明文字 ──
        desc = QLabel(t("editor.center_band_desc"))
        desc.setFont(_make_font(fn, 13))
        desc.setStyleSheet("color: #CCC; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        root.addWidget(desc)

        # ── 副标题 ──
        sub = QLabel(t("editor.center_band_sub"))
        sub.setFont(_make_font(fn, 11))
        sub.setStyleSheet("color: #888; background: transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)

        root.addStretch()

        # ── 复制按钮 ──
        copy_btn = QPushButton(t("editor.copy"))
        copy_btn.setFixedHeight(40)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(_make_font(fn, 13))
        copy_btn.setStyleSheet("""
            QPushButton {
                background: #3A3A3A; color: #E0E0E0;
                border: none; border-radius: 6px;
            }
            QPushButton:hover { background: #505050; }
        """)
        copy_btn.clicked.connect(self._on_copy)
        root.addWidget(copy_btn)

        # ── 删除按钮 ──
        del_btn = QPushButton(t("editor.delete"))
        del_btn.setFixedHeight(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFont(_make_font(fn, 13))
        del_btn.setStyleSheet("""
            QPushButton {
                background: #6E1E1E; color: #FFF;
                border: none; border-radius: 6px;
            }
            QPushButton:hover { background: #8B2020; }
        """)
        del_btn.clicked.connect(self._on_delete)
        root.addWidget(del_btn)

    # ── 回调 ──

    def _on_copy(self):
        self.copied.emit(self._item)
        self.accept()

    def _on_delete(self):
        self.deleted.emit(self._item)
        self.accept()

    # ── 定位 ──

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # ── 拖拽 ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
