"""
TEGG Touch 蛋挞 (PyQt6) - center_band_dialog.py
回中带编辑弹窗 —— 尺寸/结构对齐 ButtonEditorDialog (同款容器/标题栏/名称字段/底部按钮),
内容为: 名称(可编辑) + 回中目标选择。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QApplication, QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase

from core.i18n import t, get_font
from core.constants import (
    C_PM_BG, C_GRAY, C_GRAY_H, C_CLOSE, C_CLOSE_H, C_CYBER, C_CYBER_H,
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
    """回中带编辑弹窗 — 尺寸/结构对齐 ButtonEditorDialog"""

    deleted = pyqtSignal(object)
    copied = pyqtSignal(object)
    saved = pyqtSignal(object)

    # 与 ButtonEditorDialog 同尺寸
    WIN_W = 940
    WIN_H = 960
    PADDING = 20

    def __init__(self, item, parent=None, recenter_targets=None):
        super().__init__(parent)
        self._item = item
        self._recenter_targets = list(recenter_targets or [{'key': 'screen', 'label': t('recenter.screen')}])

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        self._drag_pos = None
        self._init_ui()
        self._center_on_screen()

    def _init_ui(self):
        fn = get_font()
        _detect_icon_font()

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

        # ── 标题栏 (标题 + 关闭) ──
        title_row = QHBoxLayout()
        title_lbl = QLabel(t("editor.center_band_title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        close_icon = "" if _ICON_FONT else "✕"
        close_btn = QPushButton(close_icon)
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFont(_make_font(_ICON_FONT or fn, 20 if _ICON_FONT else 18,
                                     bold=not _ICON_FONT))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # ── 提示文字 ──
        tip = QLabel(t("editor.center_band_desc"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)

        root.addSpacing(20)

        # ── 名称 ──
        name_lbl = QLabel(t("editor.name"))
        name_lbl.setFont(_make_font(fn, 15))
        name_lbl.setStyleSheet("color: #BBB; background: transparent;")
        root.addWidget(name_lbl)
        root.addSpacing(6)
        self._name_edit = QLineEdit(getattr(self._item.data, 'name', '') or '')
        self._name_edit.setFont(_make_font(fn, 16))
        self._name_edit.setFixedHeight(40)
        self._name_edit.setStyleSheet(
            "QLineEdit { background: #1E1E1E; color: #EEE; border: 1px solid #444;"
            " border-radius: 6px; padding: 4px 12px; }"
            "QLineEdit:focus { border: 1px solid #0EA5E9; }")
        root.addWidget(self._name_edit)

        root.addSpacing(18)

        # ── 回中目标 ──
        rc_lbl = QLabel(t("editor.center_band_sub"))
        rc_lbl.setFont(_make_font(fn, 15))
        rc_lbl.setStyleSheet("color: #BBB; background: transparent;")
        root.addWidget(rc_lbl)
        root.addSpacing(8)

        from views.recenter_palette import RecenterPaletteWidget
        cur = getattr(self._item.data, 'recenter_target', 'screen') or 'screen'
        self._picker = RecenterPaletteWidget(self._recenter_targets, current_key=cur, fn=fn)
        self._picker.target_selected.connect(self._on_target_selected)
        root.addWidget(self._picker, 1)   # 占满剩余空间

        root.addSpacing(14)

        # ── 底部按钮 (对齐 ButtonEditorDialog: Copy 全宽 + [Delete | Save]) ──
        copy_btn = QPushButton(t("editor.copy"))
        copy_btn.setFixedHeight(40)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(_make_font(fn, 18))
        copy_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_GRAY}; color: #E0E0E0; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        copy_btn.clicked.connect(self._on_copy)
        root.addWidget(copy_btn)

        root.addSpacing(8)

        r2 = QHBoxLayout()
        r2.setSpacing(10)
        del_btn = QPushButton(t("editor.delete"))
        del_btn.setFixedHeight(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFont(_make_font(fn, 18))
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(self._on_delete)
        r2.addWidget(del_btn)

        save_btn = QPushButton(t("editor.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 18, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CYBER}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        r2.addWidget(save_btn)
        root.addLayout(r2)

    # ── 回调 ──
    def _on_target_selected(self, key):
        self._item.data.recenter_target = key

    def _on_save(self):
        self._item.data.recenter_target = self._picker.current_key()
        new_name = self._name_edit.text().strip()
        if new_name:
            self._item.data.name = new_name
        self.saved.emit(self._item)
        self.accept()

    def _on_copy(self):
        self.copied.emit(self._item)
        self.accept()

    def _on_delete(self):
        self.deleted.emit(self._item)
        self.accept()

    # ── 定位 + 拖拽 ──
    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

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
