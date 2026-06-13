"""
TEGG Touch (PyQt6) - views/diag_export_dialog.py
诊断包导出弹窗 — 后台 QThread 打包最近 5 条日志 + 当前 settings + 当前激活方案
到桌面 zip; 显示进度 + 完成后的操作 (打开所在文件夹 / 关闭)
"""

import os
import sys
import zipfile
import datetime
import subprocess
import logging

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QApplication, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.i18n import t, get_font
from views.button_editor_dialog import (
    _make_font, C_PM_BG, C_GRAY, C_GRAY_H, C_CYBER, C_CYBER_H,
    C_CLOSE, C_CLOSE_H,
)


logger = logging.getLogger(__name__)


def _desktop_path() -> str:
    """优先 OneDrive\\桌面, 否则 ~\\Desktop"""
    home = os.path.expanduser('~')
    onedrive_desktop = os.path.join(home, 'OneDrive', '桌面')
    if os.path.isdir(onedrive_desktop):
        return onedrive_desktop
    onedrive_desktop_en = os.path.join(home, 'OneDrive', 'Desktop')
    if os.path.isdir(onedrive_desktop_en):
        return onedrive_desktop_en
    classic = os.path.join(home, 'Desktop')
    if os.path.isdir(classic):
        return classic
    return home


def _collect_diag_files() -> list[tuple[str, str]]:
    """收集要打入诊断包的 (源路径, zip 内相对路径) 列表"""
    from core.log_setup import list_recent_log_paths

    items: list[tuple[str, str]] = []

    # 最近 5 条日志
    for p in list_recent_log_paths(5):
        items.append((p, f'logs/{os.path.basename(p)}'))

    # settings/hotkeys.json
    hk = os.path.join(os.getcwd(), 'settings', 'hotkeys.json')
    if os.path.isfile(hk):
        items.append((hk, 'settings/hotkeys.json'))

    # 当前激活方案
    try:
        from core.config_manager import (
            get_active_profile_name, _profiles_dir, _profile_path,
        )
        name = get_active_profile_name()
        pf = _profile_path(name)
        if os.path.isfile(pf):
            items.append((pf, f'profile/{os.path.basename(pf)}'))
        # 方案索引也带上
        idx_path = os.path.join(_profiles_dir(), '_index.json')
        if os.path.isfile(idx_path):
            items.append((idx_path, 'profile/_index.json'))
    except Exception:
        pass

    return items


class _PackerThread(QThread):
    progress = pyqtSignal(int, int, str)   # done, total, current
    finished_ok = pyqtSignal(str)          # zip 路径
    failed = pyqtSignal(str)               # 错误消息

    def __init__(self, dst_zip: str, parent=None):
        super().__init__(parent)
        self._dst = dst_zip

    def run(self):
        try:
            items = _collect_diag_files()
            total = max(1, len(items))
            with zipfile.ZipFile(self._dst, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, (src, arcname) in enumerate(items, start=1):
                    self.progress.emit(i - 1, total, arcname)
                    try:
                        zf.write(src, arcname)
                    except OSError as e:
                        logger.warning('skip %s: %s', src, e)
                self.progress.emit(total, total, '')
            self.finished_ok.emit(self._dst)
        except Exception as e:
            logger.exception('diag export failed')
            self.failed.emit(str(e))


class DiagExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(440, 220)
        self._result_path: str | None = None
        self._build_ui()
        self._center_on_screen()
        # 自动开始
        self._start()

    def _build_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background: {C_PM_BG};
                border-radius: 6px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)
        v = QVBoxLayout(container)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)

        self._title_lbl = QLabel(t("hotkey.log_export_progress_title"))
        self._title_lbl.setFont(_make_font(fn, 15, bold=True))
        self._title_lbl.setStyleSheet("color: #FFF; background: transparent; border: none;")
        v.addWidget(self._title_lbl)

        self._status_lbl = QLabel(t("hotkey.log_export_packing"))
        self._status_lbl.setFont(_make_font(fn, 13))
        self._status_lbl.setStyleSheet("color: #CCC; background: transparent; border: none;")
        self._status_lbl.setWordWrap(True)
        v.addWidget(self._status_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # indeterminate during packing
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: #2A2A2A; border: none; border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {C_CYBER_H}; border-radius: 4px;
            }}
        """)
        v.addWidget(self._bar)

        v.addStretch()

        # 操作按钮 (完成后显示)
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(10)
        self._btn_row.addStretch()
        self._open_btn = QPushButton(t("hotkey.log_export_open_folder"))
        self._open_btn.setFixedHeight(34)
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.setFont(_make_font(fn, 13))
        self._open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        self._open_btn.clicked.connect(self._on_open_folder)
        self._open_btn.setVisible(False)
        self._btn_row.addWidget(self._open_btn)

        self._close_btn = QPushButton(t("hotkey.log_export_close"))
        self._close_btn.setFixedHeight(34)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFont(_make_font(fn, 13, bold=True))
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        self._close_btn.clicked.connect(self.accept)
        self._close_btn.setVisible(False)
        self._btn_row.addWidget(self._close_btn)
        v.addLayout(self._btn_row)

    def _start(self):
        ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        fname = f'TEGG-Touch-诊断报告-{ts}.zip'
        dst = os.path.join(_desktop_path(), fname)
        self._dst_path = dst

        self._thread = _PackerThread(dst, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_ok.connect(self._on_finished_ok)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_progress(self, done: int, total: int, current: str):
        if total > 1:
            self._bar.setRange(0, total)
            self._bar.setValue(done)
        if current:
            self._status_lbl.setText(f'{done}/{total} — {current}')

    def _on_finished_ok(self, path: str):
        self._result_path = path
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._title_lbl.setText(t("hotkey.log_export_done"))
        # 显示路径 (太长时省略)
        disp = path
        if len(disp) > 60:
            disp = '...' + path[-57:]
        self._status_lbl.setText(disp)
        self._open_btn.setVisible(True)
        self._close_btn.setVisible(True)

    def _on_failed(self, err: str):
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._title_lbl.setText(t("hotkey.log_export_failed", err=err))
        self._close_btn.setVisible(True)

    def _on_open_folder(self):
        if not self._result_path:
            return
        try:
            # 选中 zip 文件
            subprocess.Popen(['explorer', '/select,', self._result_path])
        except Exception:
            pass

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
