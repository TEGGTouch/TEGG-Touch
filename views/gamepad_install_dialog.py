"""
TEGG Touch (PyQt6) - views/gamepad_install_dialog.py
ViGEmBus 驱动检测/安装弹窗 — 5 状态机:
  READY_OK / NEEDS_UPDATE / NOT_INSTALLED / DRIVER_BROKEN / NEEDS_REBOOT
安装走 QThread (先离线 → 在线 → 手动 fallback)，期间显示进度条。
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QApplication, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.i18n import t, get_font
from core.gamepad_install import (
    Status, detect_status, install_offline, install_online,
    install_vgamepad_lib, open_manual_install_page, has_bundled_installer,
)

# 复用其他弹窗的色板
from views.button_editor_dialog import (
    _make_font, C_PM_BG, C_GRAY, C_GRAY_H, C_CYBER, C_CYBER_H,
    C_CLOSE, C_CLOSE_H,
)

logger = logging.getLogger(__name__)

# 安装方式 (内部状态)
_INSTALL_OFFLINE = "offline"
_INSTALL_ONLINE = "online"
_INSTALL_LIB = "lib"           # 仅 pip install vgamepad


class _InstallThread(QThread):
    progress = pyqtSignal(str, int)        # 文案, 百分比 (0-100)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)               # 错误信息; "NEEDS_REBOOT::xxx" 表示需重启
    need_fallback = pyqtSignal(str)        # 当前方式 (offline/online) 完蛋，让对话框降级

    def __init__(self, method: str, parent=None):
        super().__init__(parent)
        self._method = method

    def run(self):
        cb = lambda text, pct: self.progress.emit(text, pct)
        try:
            if self._method == _INSTALL_OFFLINE:
                ok, err = install_offline(progress_cb=cb)
            elif self._method == _INSTALL_ONLINE:
                ok, err = install_online(progress_cb=cb)
            elif self._method == _INSTALL_LIB:
                ok, err = install_vgamepad_lib(progress_cb=cb)
            else:
                ok, err = False, f"unknown method: {self._method}"
        except Exception as e:
            logger.exception("install thread crashed")
            self.failed.emit(f"未预期异常: {e}")
            return

        if ok:
            self.finished_ok.emit()
        elif err.startswith("NEEDS_REBOOT::"):
            # 装了但起不来 - 走特殊路径
            self.failed.emit(err)
        elif self._method == _INSTALL_LIB:
            # 仅 pip 失败,没有降级路径,直接报错给用户
            self.failed.emit(err)
        else:
            # 驱动安装这一档失败,请求降级
            self.need_fallback.emit(self._method)


class GamepadInstallDialog(QDialog):
    """ViGEmBus 安装/检测弹窗。

    accepted / rejected 信号语义:
      accepted = 驱动就绪 (READY_OK 或安装成功)，调用方可切换到手柄模式
      rejected = 用户取消 / 需重启 / 手动安装中，调用方应退回键盘模式
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 不加 WindowStaysOnTopHint:安装阶段需要让 ViGEm bootstrapper
        # 的安装向导窗口能浮到前台,否则用户看不到、点不到。
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 260)
        self._status_info: dict = {}
        self._thread: _InstallThread | None = None
        self._build_ui()
        self._center_on_screen()
        # 自动检测
        self._enter_detecting()

    # ── UI 框架 ──────────────────────────────────────────────────

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
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(12)

        # 主标题
        self._title_lbl = QLabel("")
        self._title_lbl.setFont(_make_font(fn, 16, bold=True))
        self._title_lbl.setStyleSheet(
            "color: #FFF; background: transparent; border: none;")
        self._title_lbl.setWordWrap(True)
        v.addWidget(self._title_lbl)

        # 主文案
        self._body_lbl = QLabel("")
        self._body_lbl.setFont(_make_font(fn, 13))
        self._body_lbl.setStyleSheet(
            "color: #CCC; background: transparent; border: none;")
        self._body_lbl.setWordWrap(True)
        v.addWidget(self._body_lbl)

        # 进度条 (默认隐藏)
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
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
        self._bar.setVisible(False)
        v.addWidget(self._bar)

        v.addStretch()

        # 按钮行
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(10)
        self._btn_row.addStretch()
        self._btn_secondary = self._make_btn("", C_GRAY, C_GRAY_H, "#E0E0E0")
        self._btn_secondary.setVisible(False)
        self._btn_row.addWidget(self._btn_secondary)
        self._btn_primary = self._make_btn("", C_CYBER, C_CYBER_H, "#FFF", bold=True)
        self._btn_primary.setVisible(False)
        self._btn_row.addWidget(self._btn_primary)
        v.addLayout(self._btn_row)

    def _make_btn(self, text: str, bg: str, bg_h: str, fg: str, bold: bool = False) -> QPushButton:
        fn = get_font()
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setMinimumWidth(110)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(_make_font(fn, 13, bold=bold))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {fg};
                border: none; border-radius: 6px; padding: 0 18px;
            }}
            QPushButton:hover {{ background: {bg_h}; }}
            QPushButton:disabled {{ background: #333; color: #666; }}
        """)
        return btn

    def _set_buttons(self, primary_text: str = "", primary_cb=None,
                     secondary_text: str = "", secondary_cb=None,
                     primary_color: tuple[str, str] = (C_CYBER, C_CYBER_H)):
        # primary
        try:
            self._btn_primary.clicked.disconnect()
        except TypeError:
            pass
        if primary_text:
            self._btn_primary.setText(primary_text)
            self._btn_primary.setVisible(True)
            self._btn_primary.setEnabled(True)
            self._btn_primary.setStyleSheet(f"""
                QPushButton {{
                    background: {primary_color[0]}; color: #FFF;
                    border: none; border-radius: 6px; padding: 0 18px;
                }}
                QPushButton:hover {{ background: {primary_color[1]}; }}
                QPushButton:disabled {{ background: #333; color: #666; }}
            """)
            if primary_cb:
                self._btn_primary.clicked.connect(primary_cb)
        else:
            self._btn_primary.setVisible(False)

        # secondary
        try:
            self._btn_secondary.clicked.disconnect()
        except TypeError:
            pass
        if secondary_text:
            self._btn_secondary.setText(secondary_text)
            self._btn_secondary.setVisible(True)
            self._btn_secondary.setEnabled(True)
            if secondary_cb:
                self._btn_secondary.clicked.connect(secondary_cb)
        else:
            self._btn_secondary.setVisible(False)

    # ── 状态机入口 ────────────────────────────────────────────────

    def _enter_detecting(self):
        self._title_lbl.setText(t("gp_install.detecting_title"))
        self._body_lbl.setText(t("gp_install.detecting_body"))
        self._bar.setVisible(True)
        self._bar.setRange(0, 0)  # indeterminate
        self._set_buttons()
        # 检测本身是快操作 (毫秒级)，主线程跑足够
        QApplication.processEvents()
        st, info = detect_status()
        self._status_info = info
        self._bar.setVisible(False)
        if st == Status.READY_OK:
            self._enter_ready_ok()
        elif st == Status.NEEDS_UPDATE:
            self._enter_needs_update()
        elif st == Status.NOT_INSTALLED:
            self._enter_not_installed()
        elif st == Status.LIB_MISSING:
            self._enter_lib_missing()
        elif st == Status.DRIVER_BROKEN:
            self._enter_driver_broken()
        else:
            # 不可能到这里 (NEEDS_REBOOT 只在安装后)，保险起见走 not_installed
            self._enter_not_installed()

    def _enter_ready_ok(self):
        ver = self._status_info.get("installed_version") or t("gp_install.unknown_version")
        self._title_lbl.setText(t("gp_install.ready_title"))
        self._body_lbl.setText(t("gp_install.ready_body", version=ver))
        self._set_buttons(
            primary_text=t("gp_install.btn_start_use"),
            primary_cb=self.accept,
        )

    def _enter_needs_update(self):
        iv = self._status_info.get("installed_version") or "?"
        bv = self._status_info.get("bundled_version") or "?"
        self._title_lbl.setText(t("gp_install.update_title"))
        self._body_lbl.setText(t("gp_install.update_body", installed=iv, bundled=bv))
        self._set_buttons(
            primary_text=t("gp_install.btn_update_now"),
            primary_cb=self._start_install_offline,
            secondary_text=t("gp_install.btn_keep_current"),
            secondary_cb=self.accept,
        )

    def _enter_not_installed(self):
        if has_bundled_installer():
            self._title_lbl.setText(t("gp_install.install_title"))
            self._body_lbl.setText(t(
                "gp_install.install_body_offline",
                bundled=self._status_info.get("bundled_version") or "?",
            ))
            self._set_buttons(
                primary_text=t("gp_install.btn_install_now"),
                primary_cb=self._start_install_offline,
                secondary_text=t("gp_install.btn_cancel"),
                secondary_cb=self.reject,
            )
        else:
            # 没内置包 → 直接走在线
            self._enter_online_fallback("no_bundled")

    def _enter_lib_missing(self):
        """驱动已就绪,只缺 vgamepad Python 库 — 简单走 pip,无需 UAC。"""
        iv = self._status_info.get("installed_version") or t("gp_install.unknown_version")
        self._title_lbl.setText(t("gp_install.lib_missing_title"))
        self._body_lbl.setText(t("gp_install.lib_missing_body", version=iv))
        self._set_buttons(
            primary_text=t("gp_install.btn_install_lib"),
            primary_cb=self._start_install_lib,
            secondary_text=t("gp_install.btn_cancel"),
            secondary_cb=self.reject,
        )

    def _enter_driver_broken(self):
        err = self._status_info.get("smoke_err", "")
        self._title_lbl.setText(t("gp_install.broken_title"))
        self._body_lbl.setText(t("gp_install.broken_body", err=err[:120]))
        self._set_buttons(
            primary_text=t("gp_install.btn_reinstall"),
            primary_cb=self._start_install_offline,
            secondary_text=t("gp_install.btn_cancel"),
            secondary_cb=self.reject,
        )

    def _enter_online_fallback(self, reason: str = ""):
        msg_key = (
            "gp_install.online_body_offline_failed"
            if reason == "offline_failed"
            else "gp_install.online_body_no_bundled"
        )
        self._title_lbl.setText(t("gp_install.online_title"))
        self._body_lbl.setText(t(msg_key))
        self._set_buttons(
            primary_text=t("gp_install.btn_install_online"),
            primary_cb=self._start_install_online,
            secondary_text=t("gp_install.btn_manual_page"),
            secondary_cb=self._open_manual,
        )

    def _enter_manual_fallback(self, err: str = ""):
        self._title_lbl.setText(t("gp_install.manual_title"))
        self._body_lbl.setText(t("gp_install.manual_body", err=err[:160]))
        self._set_buttons(
            primary_text=t("gp_install.btn_manual_page"),
            primary_cb=self._open_manual,
            secondary_text=t("gp_install.btn_close"),
            secondary_cb=self.reject,
            primary_color=(C_CYBER, C_CYBER_H),
        )

    def _enter_needs_reboot(self, err: str = ""):
        self._title_lbl.setText(t("gp_install.reboot_title"))
        self._body_lbl.setText(t("gp_install.reboot_body"))
        self._set_buttons(
            primary_text=t("gp_install.btn_got_it"),
            primary_cb=self.reject,  # 暂时切回键盘
        )

    def _enter_done(self):
        self._title_lbl.setText(t("gp_install.done_title"))
        self._body_lbl.setText(t("gp_install.done_body"))
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._set_buttons(
            primary_text=t("gp_install.btn_start_use"),
            primary_cb=self.accept,
        )

    # ── 安装动作 ──────────────────────────────────────────────────

    def _start_install_offline(self):
        self._begin_installing(_INSTALL_OFFLINE)

    def _start_install_online(self):
        self._begin_installing(_INSTALL_ONLINE)

    def _start_install_lib(self):
        self._begin_installing(_INSTALL_LIB)

    def _begin_installing(self, method: str):
        if method == _INSTALL_OFFLINE:
            title_key = "gp_install.installing_offline_title"
        elif method == _INSTALL_ONLINE:
            title_key = "gp_install.installing_online_title"
        else:
            title_key = "gp_install.installing_lib_title"
        self._title_lbl.setText(t(title_key))
        self._body_lbl.setText(t("gp_install.installing_body_init"))
        self._bar.setVisible(True)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._set_buttons()  # 隐藏所有按钮
        self._thread = _InstallThread(method, self)
        self._thread.progress.connect(self._on_install_progress)
        self._thread.finished_ok.connect(self._on_install_done)
        self._thread.failed.connect(self._on_install_failed)
        self._thread.need_fallback.connect(self._on_install_need_fallback)
        self._thread.start()

    def _on_install_progress(self, text: str, pct: int):
        self._body_lbl.setText(text)
        self._bar.setValue(max(0, min(100, pct)))

    def _on_install_done(self):
        self._bar.setVisible(False)
        self._enter_done()

    def _on_install_failed(self, err: str):
        self._bar.setVisible(False)
        if err.startswith("NEEDS_REBOOT::"):
            self._enter_needs_reboot(err[len("NEEDS_REBOOT::"):])
        else:
            # 不应该走这里 (失败时该发 need_fallback)，兜底走手动
            self._enter_manual_fallback(err)

    def _on_install_need_fallback(self, current_method: str):
        if current_method == _INSTALL_OFFLINE:
            # 离线失败 → 在线
            self._enter_online_fallback("offline_failed")
        else:
            # 在线也失败 → 手动
            self._enter_manual_fallback(t("gp_install.online_install_failed"))

    def _open_manual(self):
        open_manual_install_page()
        # 不立即关，等用户手动装完再来切换

    # ── 杂项 ──────────────────────────────────────────────────────

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def closeEvent(self, event):
        # 关闭时若有线程在跑，等其完成 (用户也无法干预安装器)
        if self._thread and self._thread.isRunning():
            self._thread.wait(500)
        super().closeEvent(event)
