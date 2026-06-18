"""
TEGG Touch 蛋挞 (PyQt6) - center_band_dialog.py
回中带专用简化编辑弹窗 — 复制 / 删除两个操作 + 说明文本，无属性编辑字段。
视觉规范对齐 ButtonEditorDialog（标题 18 / 提示 14 / 关闭图标按钮 / C_PM_BG）。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase

from core.i18n import t, get_font
from core.constants import (
    C_PM_BG, C_GRAY, C_GRAY_H, C_CLOSE, C_CLOSE_H,
)


def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


_ICON_FONT = None

def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return _ICON_FONT
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""
    return _ICON_FONT


class CenterBandDialog(QDialog):
    """回中带专用简化编辑弹窗 — 视觉对齐 ButtonEditorDialog"""

    deleted = pyqtSignal(object)
    copied = pyqtSignal(object)

    WIN_W = 420
    WIN_H = 340
    PADDING = 20

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self._item = item

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        self._init_ui()
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self):
        fn = get_font()
        _detect_icon_font()

        # 外层透明
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("cb_container")
        container.setStyleSheet(f"""
            QFrame#cb_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # ── 标题栏: 左标题 + 右关闭按钮 ──
        title_row = QHBoxLayout()
        title_lbl = QLabel(t("editor.center_band_title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        close_icon = "\uE711" if _ICON_FONT else "\u2715"
        close_btn = QPushButton(close_icon)
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setFont(_make_font(fn, 18, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        root.addSpacing(16)

        # ── 提示文字 (直接显示，主/副两行) ──
        desc = QLabel(t("editor.center_band_desc"))
        desc.setFont(_make_font(fn, 16))
        desc.setStyleSheet("color: #E0E0E0; background: transparent;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        root.addSpacing(6)

        sub = QLabel(t("editor.center_band_sub"))
        sub.setFont(_make_font(fn, 14))
        sub.setStyleSheet("color: #888; background: transparent;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        root.addStretch()

        # ── 复制按钮 ──
        copy_btn = QPushButton(t("editor.copy"))
        copy_btn.setFixedHeight(40)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(_make_font(fn, 18))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        copy_btn.clicked.connect(self._on_copy)
        root.addWidget(copy_btn)

        root.addSpacing(8)

        # ── 删除按钮 ──
        del_btn = QPushButton(t("editor.delete"))
        del_btn.setFixedHeight(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFont(_make_font(fn, 18, bold=True))
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
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
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
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
