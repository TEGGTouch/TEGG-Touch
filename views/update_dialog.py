"""
TEGG Touch (PyQt6) - update_dialog.py
新版本提示弹窗 — 与 AboutDialog 同风格的深色无边框窗口.
点「立即更新」会发 install_requested(zip_url) 信号, 由 main.py 接到, 启动后台 UpdateInstaller.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QApplication, QProgressBar,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.i18n import t, get_font
from core.constants import APP_VERSION

from views.edit_toolbar import (
    _detect_icon_font, _make_font,
    C_CLOSE, C_CLOSE_H,
)
from core.constants import C_PM_BG, C_CYBER, C_CYBER_H, C_GRAY


class UpdateDialog(QDialog):
    """新版本提示弹窗 + 内嵌升级流程 UI."""

    # 用户点「立即更新」时发出, payload = zip 直链 URL
    install_requested = pyqtSignal(str)

    def __init__(self, version: str, url: str, body: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._version = version
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(560, 460)
        self._init_ui(version, body)
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self, version: str, body: str):
        font_name = get_font()
        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT

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

        # ── 标题栏 ──
        header = QHBoxLayout()
        title = QLabel(t("update.title"))
        title.setStyleSheet(f"""
            color: #FFF; font-size: 22px; font-weight: bold;
            font-family: '{font_name}';
        """)
        header.addWidget(title)
        header.addStretch()

        self._close_btn = QPushButton()
        self._close_btn.setFixedSize(40, 40)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            self._close_btn.setText("\uE711")
            self._close_btn.setFont(_make_font(_ICON_FONT, 18))
        else:
            self._close_btn.setText("\u2715")
            self._close_btn.setFont(_make_font(font_name, 16, bold=True))
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        self._close_btn.clicked.connect(self.close)
        header.addWidget(self._close_btn)
        layout.addLayout(header)

        # 分隔线
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

        # ── 更新说明 ──
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

        # ── 进度区 (默认隐藏, 下载中显示) ──
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: #BBB; font-size: 13px; font-family: '{font_name}';")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setVisible(False)
        layout.addWidget(self._status_lbl)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #1F1F1F; border: none; border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {C_CYBER}; border-radius: 4px;
            }}
        """)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        self._skip_btn = QPushButton(t("update.skip"))
        self._skip_btn.setFixedHeight(44)
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #CCC;
                border: none; border-radius: 6px;
                padding: 0 28px; font-size: 16px;
            }}
            QPushButton:hover {{ background: #505050; }}
        """)
        self._skip_btn.clicked.connect(self.close)
        btn_row.addWidget(self._skip_btn)

        self._install_btn = QPushButton(t("update.install_now"))
        self._install_btn.setFixedHeight(44)
        self._install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._install_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px;
                padding: 0 28px; font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
            QPushButton:disabled {{
                background: #2A4A5E; color: #888;
            }}
        """)
        self._install_btn.clicked.connect(self._on_install_clicked)
        btn_row.addWidget(self._install_btn, 1)

        layout.addLayout(btn_row)

    def _on_install_clicked(self):
        if not self._url:
            return
        self._install_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._status_lbl.setText(t("update.downloading"))
        self._status_lbl.setVisible(True)
        self._progress_bar.setRange(0, 0)   # indeterminate 直到拿到 Content-Length
        self._progress_bar.setVisible(True)
        self.install_requested.emit(self._url)

    # ── 由 main.py 在下载进度变化时回调 ──

    def on_progress(self, downloaded: int, total: int):
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(downloaded)
            mb_d = downloaded / 1024 / 1024
            mb_t = total / 1024 / 1024
            self._status_lbl.setText(
                t("update.downloading_progress", done=f"{mb_d:.1f}", total=f"{mb_t:.1f}")
            )
        else:
            # 未知总大小, 用 indeterminate 模式
            mb_d = downloaded / 1024 / 1024
            self._status_lbl.setText(
                t("update.downloading_unknown", done=f"{mb_d:.1f}")
            )

    def on_applying(self):
        """下载完, 准备 spawn updater + quit 主程序."""
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100)
        self._status_lbl.setText(t("update.applying"))

    def on_failed(self, msg: str):
        self._install_btn.setEnabled(True)
        self._skip_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_lbl.setText(t("update.failed", error=msg))
        self._status_lbl.setStyleSheet(
            f"color: #F87171; font-size: 13px; font-family: '{get_font()}';"
        )

    # ── 定位 + 拖拽 ──

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

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
