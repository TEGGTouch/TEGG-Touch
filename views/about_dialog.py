"""
TEGG Touch 蛋挞 (PyQt6) - about_dialog.py
关于/产品介绍弹窗。
"""

import os
import webbrowser

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont

from core.i18n import t, get_font
from core.constants import APP_VERSION, get_app_title, APP_DIR
from views.edit_toolbar import _detect_icon_font, _make_font, C_CLOSE, C_CLOSE_H


_LAST_UPDATE = "2026.02.22"


class AboutDialog(QDialog):
    """关于弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(620, 620)
        self._init_ui()
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self):
        font_name = get_font()
        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT

        # ── 外层透明, 内层 QFrame 容器 (与其他弹窗一致) ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("about_container")
        container.setStyleSheet("""
            QFrame#about_container {
                background: #2D2D2D;
                border-radius: 4px;
                border: 1px solid #444;
            }
            QLabel { color: #CCC; }
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 关闭按钮 (右上角, 与工具栏关闭按钮同规格)
        header = QHBoxLayout()
        header.addStretch()
        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
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

        # 标题
        title = QLabel(f"🎮  {get_app_title()}")
        title.setStyleSheet(f"""
            color: #F59E0B; font-size: 28px; font-weight: bold;
            font-family: '{font_name}';
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 版本号
        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet("color: #888; font-size: 14px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        # 最后更新
        update = QLabel(t("about.last_update", date=_LAST_UPDATE))
        update.setStyleSheet("color: #666; font-size: 12px;")
        update.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(update)

        # 分隔线
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        layout.addWidget(sep)

        # 产品介绍
        desc = QLabel(t("about.description"))
        desc.setStyleSheet(f"color: #CCC; font-size: 16px; font-family: '{font_name}';")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 分隔线
        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #444;")
        layout.addWidget(sep2)

        # QR 码区域
        qr_layout = QHBoxLayout()
        qr_layout.setSpacing(14)

        # 尝试加载二维码
        qr_path = os.path.join(APP_DIR, "assets", "wechat_qr.png")
        qr_label = QLabel()
        if os.path.exists(qr_path):
            pixmap = QPixmap(qr_path)
            qr_label.setPixmap(pixmap.scaled(
                160, 160, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            qr_label.setText(t("about.qr_missing"))
            qr_label.setStyleSheet("""
                background: #3A3A3A; color: #888;
                border: 1px solid #555; border-radius: 8px;
                font-size: 14px;
            """)
            qr_label.setFixedSize(160, 160)
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr_layout.addWidget(qr_label)

        # 右侧文字
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        hint = QLabel(t("about.qr_hint"))
        hint.setStyleSheet(f"color: #AAA; font-size: 16px; font-family: '{font_name}';")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        right_layout.addSpacing(20)

        # 邮箱
        email_label = QLabel(t("about.email"))
        email_label.setStyleSheet(f"color: #888; font-size: 16px; font-family: '{font_name}';")
        email_label.setCursor(Qt.CursorShape.PointingHandCursor)
        email_label.mousePressEvent = lambda e: webbrowser.open(
            "mailto:life.is.like.a.boat@gmail.com")
        right_layout.addWidget(email_label)

        # GitHub
        github_label = QLabel(t("about.github"))
        github_label.setStyleSheet(f"color: #888; font-size: 16px; font-family: '{font_name}';")
        github_label.setCursor(Qt.CursorShape.PointingHandCursor)
        github_label.mousePressEvent = lambda e: webbrowser.open(
            "https://github.com/TEGGTouch/TEGG-Touch/releases")
        right_layout.addWidget(github_label)

        right_layout.addStretch()
        qr_layout.addLayout(right_layout)
        layout.addLayout(qr_layout)

        layout.addStretch()

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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
