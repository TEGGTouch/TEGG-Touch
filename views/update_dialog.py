"""
TEGG Touch (PyQt6) - update_dialog.py
新版本提示弹窗 — 与 AboutDialog 同风格的深色无边框窗口。
"""

import webbrowser

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.i18n import t, get_font
from core.constants import APP_VERSION


# 复用编辑工具栏的图标字体检测 + 字体工厂 + 颜色常量
from views.edit_toolbar import (
    _detect_icon_font, _make_font,
    C_CLOSE, C_CLOSE_H,
)
from core.constants import C_PM_BG, C_CYBER, C_CYBER_H, C_GRAY


class UpdateDialog(QDialog):
    """新版本提示弹窗"""

    def __init__(self, version: str, url: str, body: str, parent=None):
        super().__init__(parent)
        self._url = url
        # 故意不用 Qt.WindowType.Tool — 它在 Windows 上会阻止窗口被 activate, 导致顶不上去
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(560, 440)
        self._init_ui(version, body)
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self, version: str, body: str):
        font_name = get_font()
        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT

        # 外层透明, 内层 QFrame 容器
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("update_container")
        container.setStyleSheet(f"""
            QFrame#update_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
            QLabel {{ color: #CCC; }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        # ── 标题栏: 标题 + 关闭按钮 ──
        header = QHBoxLayout()
        title = QLabel(t("update.title"))
        title.setStyleSheet(f"""
            color: #FFF; font-size: 22px; font-weight: bold;
            font-family: '{font_name}';
        """)
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 18))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(font_name, 16, bold=True))
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

        # ── 分隔线 ──
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        layout.addWidget(sep)

        # ── 版本信息 ──
        ver_text = t("update.new_version", version=version)
        ver_label = QLabel(ver_text)
        ver_label.setStyleSheet(f"""
            color: #F59E0B; font-size: 26px; font-weight: bold;
            font-family: '{font_name}';
        """)
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver_label)

        cur_label = QLabel(t("update.current_version", version=APP_VERSION))
        cur_label.setStyleSheet("color: #888; font-size: 14px;")
        cur_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(cur_label)

        # ── 更新说明 (放大显示区, 容纳更多内容) ──
        if body and body.strip():
            notes = QLabel(body.strip()[:1200])
            notes.setStyleSheet(f"""
                color: #BBB; font-size: 14px;
                font-family: '{font_name}';
                padding: 12px;
                background: {C_GRAY};
                border-radius: 6px;
            """)
            notes.setWordWrap(True)
            notes.setMaximumHeight(220)
            notes.setAlignment(Qt.AlignmentFlag.AlignTop)
            layout.addWidget(notes, 1)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        skip_btn = QPushButton(t("update.skip"))
        skip_btn.setFixedHeight(44)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #CCC;
                border: none; border-radius: 6px;
                padding: 0 28px; font-size: 16px;
            }}
            QPushButton:hover {{ background: #505050; }}
        """)
        skip_btn.clicked.connect(self.close)
        btn_row.addWidget(skip_btn)

        dl_btn = QPushButton(t("update.download"))
        dl_btn.setFixedHeight(44)
        dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px;
                padding: 0 28px; font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        dl_btn.clicked.connect(self._open_download)
        btn_row.addWidget(dl_btn, 1)

        layout.addLayout(btn_row)

    def _open_download(self):
        if self._url:
            webbrowser.open(self._url)
        self.close()

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
