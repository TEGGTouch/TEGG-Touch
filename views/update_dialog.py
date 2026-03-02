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
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 300)
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
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(10)

        # ── 标题栏: 标题 + 关闭按钮 ──
        header = QHBoxLayout()
        title = QLabel(t("update.title"))
        title.setStyleSheet(f"""
            color: #FFF; font-size: 18px; font-weight: bold;
            font-family: '{font_name}';
        """)
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 16))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(font_name, 14, bold=True))
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
            color: #F59E0B; font-size: 20px; font-weight: bold;
            font-family: '{font_name}';
        """)
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver_label)

        cur_label = QLabel(t("update.current_version", version=APP_VERSION))
        cur_label.setStyleSheet("color: #888; font-size: 13px;")
        cur_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(cur_label)

        # ── 更新说明 (最多显示 4 行) ──
        if body and body.strip():
            notes = QLabel(body.strip()[:300])
            notes.setStyleSheet(f"""
                color: #AAA; font-size: 13px;
                font-family: '{font_name}';
                padding: 6px;
                background: {C_GRAY};
                border-radius: 4px;
            """)
            notes.setWordWrap(True)
            notes.setMaximumHeight(80)
            layout.addWidget(notes)

        layout.addStretch()

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        skip_btn = QPushButton(t("update.skip"))
        skip_btn.setFixedHeight(36)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #CCC;
                border: none; border-radius: 6px;
                padding: 0 20px; font-size: 14px;
            }}
            QPushButton:hover {{ background: #505050; }}
        """)
        skip_btn.clicked.connect(self.close)
        btn_row.addWidget(skip_btn)

        dl_btn = QPushButton(t("update.download"))
        dl_btn.setFixedHeight(36)
        dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px;
                padding: 0 20px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        dl_btn.clicked.connect(self._open_download)
        btn_row.addWidget(dl_btn)

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
