"""
TEGG Touch (PyQt6) - post_update_dialog.py
更新完成提示弹窗 — 新版首次启动时弹出, 明确告知"已更新到 vX + 程序所在位置"。

设计取舍: 就地更新不改用户安装目录名 (改名会让快捷方式/任务栏固定失效),
所以更新后用户常找不到新版装在哪。这里用一个可读路径 + 「打开所在文件夹」按钮
把位置直接告诉用户, 解决困惑而不动用户的目录结构。
与 AboutDialog / UpdateDialog 同风格的深色无边框窗口。
"""

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt

from core.i18n import t, get_font
from core.constants import APP_VERSION, C_PM_BG, C_GRAY, C_AMBER, C_CYBER, C_CYBER_H
from views.edit_toolbar import (
    _detect_icon_font, _make_font, C_AMBER_D, C_CLOSE, C_CLOSE_H,
)


class PostUpdateDialog(QDialog):
    """更新完成提示: 已更新到 vX + 程序位置 + 打开文件夹。"""

    def __init__(self, install_dir: str, parent=None):
        super().__init__(parent)
        self._install_dir = install_dir
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 300)
        self._drag_pos = None
        self._init_ui()
        self._center_on_screen()

    def _init_ui(self):
        fn = get_font()
        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("post_update_container")
        container.setStyleSheet(f"""
            QFrame#post_update_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
            QLabel {{ color: #CCC; background: transparent; }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        # ── 标题栏 ──
        header = QHBoxLayout()
        title = QLabel(t("update.applied_title", version=APP_VERSION))
        title.setStyleSheet(f"color: #F59E0B; font-size: 20px; font-weight: bold; font-family: '{fn}';")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("")
            close_btn.setFont(_make_font(_ICON_FONT, 16))
        else:
            close_btn.setText("✕")
            close_btn.setFont(_make_font(fn, 15, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        layout.addLayout(header)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        layout.addWidget(sep)

        # ── 说明 ──
        body = QLabel(t("update.applied_body"))
        body.setStyleSheet(f"color: #BBB; font-size: 14px; font-family: '{fn}';")
        body.setWordWrap(True)
        layout.addWidget(body)

        # ── 程序位置 (可选中复制) ──
        loc_label = QLabel(t("update.applied_location"))
        loc_label.setStyleSheet(f"color: #888; font-size: 13px; font-family: '{fn}';")
        layout.addWidget(loc_label)

        path_box = QLabel(self._install_dir)
        path_box.setStyleSheet(f"""
            color: #E5E5E5; font-size: 13px; font-family: '{fn}';
            padding: 10px; background: {C_GRAY}; border-radius: 6px;
        """)
        path_box.setWordWrap(True)
        path_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_box)

        layout.addStretch()

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        open_btn = QPushButton(t("update.open_folder"))
        open_btn.setFixedHeight(42)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF; border: none; border-radius: 6px;
                padding: 0 22px; font-size: 15px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        open_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(open_btn, 1)

        ok_btn = QPushButton(t("update.got_it"))
        ok_btn.setFixedHeight(42)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_AMBER}; color: #000; border: none; border-radius: 6px;
                padding: 0 22px; font-size: 15px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C_AMBER_D}; }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn, 1)

        layout.addLayout(btn_row)

    def _open_folder(self):
        """在资源管理器中打开程序所在文件夹。"""
        try:
            if os.path.isdir(self._install_dir):
                os.startfile(self._install_dir)  # type: ignore[attr-defined]  # Windows only
        except Exception:
            pass

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
