"""
TEGG Touch 蛋挞 (PyQt6) - profile_manager_dialog.py
方案管理弹窗 — 列表（行内编辑/删除/导出）、新建、复制、导入。
对齐原版 Tkinter 布局。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QWidget,
    QLineEdit, QFileDialog, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor

from core.i18n import t, get_font
from core.config_manager import (
    list_profiles, get_active_profile_name,
    create_profile, delete_profile, rename_profile,
    export_profile, import_profile,
    load_profile, save_profile,
)
from views.edit_toolbar import (
    _detect_icon_font, _make_font,
    C_GRAY, C_GRAY_H, C_CLOSE, C_CLOSE_H,
)

# ── 颜色常量 (对齐原版 widgets.py) ──
C_PM_BG = "#2D2D2D"
C_PM_ITEM = "#3A3A3A"
C_PM_SEL = "#F59E0B"
C_PM_HOVER = "#474747"
C_AMBER = "#F59E0B"
C_AMBER_D = "#D97706"


# ═══════════════════════════════════════════════════════════════
#  通用暗色弹窗 (对齐原版 create_styled_dialog / create_styled_yesno_dialog)
# ═══════════════════════════════════════════════════════════════

class _StyledInputDialog(QDialog):
    """暗色输入弹窗: 标题 + 标签 + 输入框 + 确认按钮。"""

    confirmed = pyqtSignal(str)

    def __init__(self, title, label_text, initial_value="", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 220)
        self._result = None
        self._drag_pos = None

        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        fn = get_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("sid_container")
        container.setStyleSheet(f"""
            QFrame#sid_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题栏
        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # 标签
        lbl = QLabel(label_text)
        lbl.setFont(_make_font(fn, 14))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        # 输入框
        self._entry = QLineEdit()
        self._entry.setFont(_make_font(fn, 14))
        self._entry.setStyleSheet(f"""
            QLineEdit {{
                background: {C_GRAY}; color: white;
                border: none; border-radius: 6px;
                padding: 8px 12px;
                selection-background-color: {C_AMBER};
                selection-color: black;
            }}
        """)
        if initial_value:
            self._entry.setText(initial_value)
            self._entry.selectAll()
        self._entry.returnPressed.connect(self._on_confirm)
        layout.addWidget(self._entry)

        layout.addStretch()

        # 确认按钮 (琥珀色, 居中)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        confirm_btn = QPushButton(t("dialog.confirm"))
        confirm_btn.setFixedSize(100, 40)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setFont(_make_font(fn, 16))
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_AMBER}; color: black;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_AMBER_D}; }}
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._entry.setFocus()
        self._center_on_screen()

    def _on_confirm(self):
        val = self._entry.text().strip()
        if val:
            self._result = val
            self.confirmed.emit(val)
            self.accept()

    def result_text(self):
        return self._result

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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


class _StyledConfirmDialog(QDialog):
    """暗色确认弹窗: 标题 + 消息 + 是/否 按钮。accent_color 控制确定按钮颜色。"""

    def __init__(self, title, message, parent=None, accent_color=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 200)
        self._drag_pos = None

        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        fn = get_font()

        # 确定按钮配色
        ac = accent_color or C_AMBER
        ac_hover = C_AMBER_D if ac == C_AMBER else ac
        ac_fg = "black" if ac == C_AMBER else "#FFF"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("scd_container")
        container.setStyleSheet(f"""
            QFrame#scd_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题栏
        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # 消息
        msg_lbl = QLabel(message)
        msg_lbl.setFont(_make_font(fn, 14))
        msg_lbl.setStyleSheet("color: white; background: transparent;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        layout.addStretch()

        # 按钮: 是(强调色) | 否(灰)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        yes_btn = QPushButton(t("dialog.yes"))
        yes_btn.setFixedSize(90, 40)
        yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        yes_btn.setFont(_make_font(fn, 16))
        yes_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ac}; color: {ac_fg};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {ac_hover}; }}
        """)
        yes_btn.clicked.connect(self.accept)
        btn_row.addWidget(yes_btn)

        btn_row.addSpacing(20)

        no_btn = QPushButton(t("dialog.no"))
        no_btn.setFixedSize(90, 40)
        no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        no_btn.setFont(_make_font(fn, 16))
        no_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #EEE;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        no_btn.clicked.connect(self.reject)
        btn_row.addWidget(no_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._center_on_screen()

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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


class _StyledMessageDialog(QDialog):
    """暗色消息弹窗: 标题 + 消息 + 确认按钮。用于替代 QMessageBox.warning/information。"""

    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 200)
        self._drag_pos = None

        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        fn = get_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("smd_container")
        container.setStyleSheet(f"""
            QFrame#smd_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题栏
        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # 消息
        msg_lbl = QLabel(message)
        msg_lbl.setFont(_make_font(fn, 14))
        msg_lbl.setStyleSheet("color: white; background: transparent;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        layout.addStretch()

        # 确认按钮 (居中)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton(t("dialog.confirm"))
        ok_btn.setFixedSize(100, 40)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setFont(_make_font(fn, 16))
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_AMBER}; color: black;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_AMBER_D}; }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._center_on_screen()

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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


class _ProfileRowWidget(QFrame):
    """方案列表行 — 名称 + 行内操作按钮 (编辑/删除/导出)，对齐原版。"""

    rename_clicked = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)
    export_clicked = pyqtSignal(str)
    switch_clicked = pyqtSignal(str)

    ROW_H = 40

    def __init__(self, name, is_active, icon_font_name, font_name, parent=None):
        super().__init__(parent)
        self._name = name
        self._is_active = is_active
        self.setFixedHeight(self.ROW_H)

        bg = C_PM_SEL if is_active else C_PM_ITEM
        fg = "black" if is_active else "white"
        fg_dim = "rgba(0,0,0,0.35)" if is_active else "white"
        hover_bg = "#D97706" if is_active else "rgba(255,255,255,0.15)"

        self.setObjectName("profile_row")
        self.setStyleSheet(f"""
            QFrame#profile_row {{
                background: {bg}; border-radius: 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(6)

        # ✓ 图标 (仅活跃方案)
        if is_active:
            check = QLabel()
            if icon_font_name:
                check.setText("\uE73E")
                check.setFont(_make_font(icon_font_name, 16))
            else:
                check.setText("\u2713")
                check.setFont(_make_font(font_name, 14, bold=True))
            check.setStyleSheet(f"color: {fg}; background: transparent;")
            layout.addWidget(check)

        # 方案名
        name_lbl = QLabel(name)
        name_lbl.setFont(_make_font(font_name, 16))
        name_lbl.setStyleSheet(f"color: {fg}; background: transparent;")
        name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        name_lbl.mousePressEvent = lambda e: self.switch_clicked.emit(self._name)
        layout.addWidget(name_lbl, 1)

        # 行内按钮: 编辑(重命名) | 删除 | 导出
        btn_size = 30

        # 编辑
        edit_btn = QPushButton()
        edit_btn.setFixedSize(btn_size, btn_size)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_font_name:
            edit_btn.setText("\uE70F")
            edit_btn.setFont(_make_font(icon_font_name, 14))
        else:
            edit_btn.setText("\u270E")
            edit_btn.setFont(_make_font(font_name, 14))
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                color: {fg}; background: transparent; border: none;
            }}
            QPushButton:hover {{ background: {hover_bg}; border-radius: 6px; }}
        """)
        edit_btn.clicked.connect(lambda: self.rename_clicked.emit(self._name))
        layout.addWidget(edit_btn)

        # 删除
        del_btn = QPushButton()
        del_btn.setFixedSize(btn_size, btn_size)
        if icon_font_name:
            del_btn.setText("\uE74D")
            del_btn.setFont(_make_font(icon_font_name, 14))
        else:
            del_btn.setText("\u2715")
            del_btn.setFont(_make_font(font_name, 12))
        if is_active:
            del_btn.setEnabled(False)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {fg_dim}; background: transparent; border: none;
                }}
            """)
        else:
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {fg}; background: transparent; border: none;
                }}
                QPushButton:hover {{ background: {hover_bg}; border-radius: 6px; }}
            """)
            del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._name))
        layout.addWidget(del_btn)

        # 导出
        exp_btn = QPushButton()
        exp_btn.setFixedSize(btn_size, btn_size)
        exp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_font_name:
            exp_btn.setText("\uE896")
            exp_btn.setFont(_make_font(icon_font_name, 14))
        else:
            exp_btn.setText("\u2193")
            exp_btn.setFont(_make_font(font_name, 14))
        exp_btn.setStyleSheet(f"""
            QPushButton {{
                color: {fg}; background: transparent; border: none;
            }}
            QPushButton:hover {{ background: {hover_bg}; border-radius: 6px; }}
        """)
        exp_btn.clicked.connect(lambda: self.export_clicked.emit(self._name))
        layout.addWidget(exp_btn)

    def mousePressEvent(self, event):
        """点击行空白区域也触发切换"""
        if not self._is_active:
            self.switch_clicked.emit(self._name)
        super().mousePressEvent(event)


class ProfileManagerDialog(QDialog):
    """方案管理弹窗 — 对齐原版 Tkinter 布局"""

    profile_switched = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 540)
        self._init_ui()
        self._refresh()
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self):
        self._font_name = get_font()
        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        self._icon_font = _ICON_FONT

        # ── 外层透明, 内层 QFrame 容器 ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("pm_container")
        container.setStyleSheet(f"""
            QFrame#pm_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self._layout = layout

        # ── 标题栏 ──
        header = QHBoxLayout()
        title = QLabel(t("profile.manager_title"))
        title.setFont(_make_font(self._font_name, 18, bold=True))
        title.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._icon_font:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(self._icon_font, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(self._font_name, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # ── 方案列表 ──
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: {C_PM_BG};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                padding: 0px;
                border: none;
                margin-right: 0px;
            }}
            QListWidget::item:selected {{
                background: transparent;
            }}
            QListWidget::item:hover {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 18px; border: none;
                padding-left: 10px;
            }}
            QScrollBar::handle:vertical {{
                background: #404040; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._list, 1)

        # ── 底部按钮: 新建 | 复制 | 导入 (对齐原版 3 按钮等宽) ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_style = f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
                padding: 8px 0px; font-size: 16px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """

        new_btn = self._build_bottom_btn("\uE710", "\uff0b", t("profile.new"))
        new_btn.setStyleSheet(btn_style)
        new_btn.clicked.connect(self._on_new)
        btn_row.addWidget(new_btn, 1)

        copy_btn = self._build_bottom_btn("\uE8C8", "\u2398", t("profile.copy"))
        copy_btn.setStyleSheet(btn_style)
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn, 1)

        import_btn = self._build_bottom_btn("\uE898", "\u2193", t("profile.import_btn"))
        import_btn.setStyleSheet(btn_style)
        import_btn.clicked.connect(self._on_import)
        btn_row.addWidget(import_btn, 1)

        layout.addLayout(btn_row)

    def _build_bottom_btn(self, icon_char, fallback, label):
        """底部按钮: icon font 图标 + 文字 (与工具栏同方案)"""
        btn = QPushButton()
        btn.setFixedHeight(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(btn)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        if self._icon_font:
            icon_lbl.setText(icon_char)
            icon_lbl.setFont(_make_font(self._icon_font, 20))
        else:
            icon_lbl.setText(fallback)
            icon_lbl.setFont(_make_font(self._font_name, 16, bold=True))
        icon_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(icon_lbl)

        text_lbl = QLabel(label)
        text_lbl.setFont(_make_font(self._font_name, 16))
        text_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(text_lbl)

        return btn

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _refresh(self):
        self._list.clear()
        profiles = list_profiles()
        active = get_active_profile_name()
        for name in profiles:
            row = _ProfileRowWidget(
                name, name == active,
                self._icon_font, self._font_name)
            row.switch_clicked.connect(self._on_switch)
            row.rename_clicked.connect(self._on_rename)
            row.delete_clicked.connect(self._on_delete)
            row.export_clicked.connect(self._on_export)

            item = QListWidgetItem()
            item.setSizeHint(QSize(0, _ProfileRowWidget.ROW_H + 10))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)

    # ── 操作回调 ──

    def _on_switch(self, name):
        self.profile_switched.emit(name)
        self._refresh()

    def _on_new(self):
        dlg = _StyledInputDialog(
            t("profile.new_title"), t("profile.new_name_label"), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.result_text()
            if name:
                if create_profile(name, from_template=True):
                    self.profile_switched.emit(name)
                    self._refresh()
                else:
                    _StyledMessageDialog(t("dialog.error"), t("profile.error_exists"), self).exec()

    def _on_copy(self):
        base = get_active_profile_name()
        dlg = _StyledInputDialog(
            t("profile.copy_title"),
            t("profile.copy_label", name=base),
            initial_value=f"{base}_copy", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.result_text()
            if name:
                if create_profile(name, from_template=True):
                    src_cfg = load_profile(base)
                    save_profile(name, src_cfg)
                    self.profile_switched.emit(name)
                    self._refresh()
                else:
                    _StyledMessageDialog(t("dialog.error"), t("profile.error_exists"), self).exec()

    def _on_rename(self, old_name):
        dlg = _StyledInputDialog(
            t("profile.rename_title"),
            t("profile.rename_label", name=old_name),
            initial_value=old_name, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name = dlg.result_text()
            if new_name and new_name != old_name:
                if rename_profile(old_name, new_name):
                    self._refresh()
                else:
                    _StyledMessageDialog(t("dialog.error"), t("profile.error_rename_exists"), self).exec()

    def _on_delete(self, name):
        dlg = _StyledConfirmDialog(
            t("dialog.confirm"), t("profile.confirm_delete", name=name), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if not delete_profile(name):
                _StyledMessageDialog(t("dialog.error"), t("profile.error_delete_active"), self).exec()
            self._refresh()

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("profile.import_title"), "",
            "JSON (*.json);;All (*.*)")
        if not path:
            return
        new_name = import_profile(path)
        if new_name:
            self.profile_switched.emit(new_name)
            self._refresh()
        else:
            _StyledMessageDialog(t("dialog.error"), t("profile.error_import_invalid"), self).exec()

    def _on_export(self, name):
        path, _ = QFileDialog.getSaveFileName(
            self, t("profile.export_title", name=name),
            f"{name}.json", "JSON (*.json);;All (*.*)")
        if not path:
            return
        if export_profile(name, path):
            _StyledMessageDialog(t("dialog.success"), t("profile.export_success", name=name), self).exec()
        else:
            _StyledMessageDialog(t("dialog.error"), t("profile.error_export"), self).exec()

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
