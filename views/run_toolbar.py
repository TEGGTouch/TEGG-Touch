"""
TEGG Touch 蛋挞 (PyQt6) - run_toolbar.py
运行模式工具栏 — 匹配原版 Tkinter 布局。

原版布局 (单行, 1070×60):
  DragHandle | Profile(210px,#AAA) | Sep | AutoCenter(150px) | ShowHide(160px)
  | Keyboard(140px) | Passthrough(180px,3-state) | Sep | Stop(130px)
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap

from core.i18n import t, get_font
from core.constants import PT_ON, PT_OFF, PT_BLOCK, TOOLBAR_WIDTH

# 共用组件 & 颜色常量 (从 edit_toolbar 导入)
from views.edit_toolbar import (
    _DragHandle, _VSep, _IconTextBtn, _detect_icon_font, _make_font,
    C_GRAY, C_GRAY_H, C_CLOSE, C_CLOSE_H, C_PANEL,
    C_AMBER, C_AMBER_D,
)
import views.edit_toolbar as _et
from views.toolbar_tip_widget import ToolbarTipWidget

# 运行工具栏专用颜色
C_GREEN = "#176F2C"
C_GREEN_H = "#1E8E38"
C_BLUE = "#1976D2"
C_BLUE_H = "#2196F3"

# 运行工具栏尺寸 (与软键盘宽度保持一致)
RUN_W = 1070
RUN_H = 60
RUN_BOTTOM_MARGIN = 50


class RunToolbar(QWidget):
    """运行模式工具栏 — 匹配原版单行布局"""

    stop_clicked = pyqtSignal()
    voice_toggle_clicked = pyqtSignal()
    auto_center_clicked = pyqtSignal()
    toggle_buttons_clicked = pyqtSignal()
    soft_keyboard_clicked = pyqtSignal()
    pt_clicked = pyqtSignal(str)
    collapse_clicked = pyqtSignal()
    cursor_toggle_clicked = pyqtSignal()  # 切换自绘光标显隐
    moved = pyqtSignal()  # 工具栏被拖拽移动时发出，用于同步软键盘位置
    position_changed = pyqtSignal(int, int)  # 拖拽结束后发出 (x, y)，用于持久化

    def __init__(self, parent=None):
        super().__init__(parent)
        _detect_icon_font()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._auto_center = False
        self._buttons_hidden = False
        self._pt_mode = PT_OFF
        self._drag_pos = None
        self._tip = ToolbarTipWidget()

        self._init_ui()
        self._position_toolbar()

    # ── UI 构建 ──────────────────────────────────────────────

    def _init_ui(self):
        fn = get_font()

        # 读取热键配置
        hotkeys = {}
        try:
            from core.config_manager import load_hotkeys
            hotkeys = load_hotkeys()
        except Exception:
            pass

        _K_CURSOR = hotkeys.get('cursor', 'F3').upper()
        _K_COLLAPSE = hotkeys.get('collapse', 'F4').upper()
        _K_VOICE = hotkeys.get('voice', 'F5').upper()
        _K_AC = hotkeys.get('auto_center', 'F6').upper()
        _K_VIS = hotkeys.get('toggle_buttons', 'F7').upper()
        _K_KB = hotkeys.get('soft_keyboard', 'F8').upper()
        _K_PTON = hotkeys.get('pt_on', 'F9').upper()
        _K_PTOFF = hotkeys.get('pt_off', 'F10').upper()
        _K_PTBLK = hotkeys.get('pt_block', 'F11').upper()
        _K_STOP = hotkeys.get('stop', 'F12').upper()

        # 外层透明
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("rt_container")
        container.setStyleSheet(f"""
            QFrame#rt_container {{
                background: {C_PANEL};
                border-radius: 4px;
                border: 1px solid #444;
            }}
            QToolTip {{
                background: #1A1A1A;
                color: #E0E0E0;
                border: 1px solid #333;
                padding: 4px 8px;
                font-size: 12px;
            }}
        """)
        outer.addWidget(container)

        row = QHBoxLayout(container)
        row.setContentsMargins(0, 10, 10, 10)
        row.setSpacing(10)

        # ── 1. 拖拽把手 ──
        row.addWidget(_DragHandle())

        # ── 2. 方案 icon + 名称 (与编辑工具栏一致) ──
        prof_box = QHBoxLayout()
        prof_box.setSpacing(6)
        prof_box.setContentsMargins(0, 0, 0, 0)

        if _et._ICON_FONT:
            self._prof_icon = QLabel("\uE765")
            self._prof_icon.setFont(_make_font(_et._ICON_FONT, 16))
        else:
            self._prof_icon = QLabel("\U0001F4C4")
            self._prof_icon.setFont(_make_font(fn, 16))
        self._prof_icon.setStyleSheet("color: #AAA; background: transparent;")
        prof_box.addWidget(self._prof_icon)

        self._profile_lbl = QLabel()
        self._profile_lbl.setFont(_make_font(fn, 16, bold=True))
        self._profile_lbl.setStyleSheet("color: #AAA; background: transparent;")
        self._profile_lbl.setMaximumWidth(210)
        prof_box.addWidget(self._profile_lbl)

        row.addLayout(prof_box)

        # 弹簧 → 将所有按钮推到右侧
        row.addStretch()

        # ── 右侧按钮区 (右对齐, 10px间距) ──

        # 分隔线
        row.addWidget(_VSep())

        # 光标 [F3] (眼睛图标; 隐藏时琥珀高亮+闭眼)
        self._cursor_btn = _IconTextBtn(
            "", "\U0001F441",
            t("run.cursor", key=_K_CURSOR),
            C_GRAY, C_GRAY_H)
        self._cursor_btn.setToolTip(t("tooltip.cursor"))
        self._install_tip(self._cursor_btn)
        self._cursor_btn.clicked.connect(self.cursor_toggle_clicked.emit)
        row.addWidget(self._cursor_btn)

        # 悬浮球 [F4] (激活后变琥珀色)
        self._collapse_btn = _IconTextBtn(
            "", "⤓",
            t("run.collapse", key=_K_COLLAPSE),
            C_GRAY, C_GRAY_H)
        self._collapse_btn.setToolTip(t("tooltip.collapse"))
        self._install_tip(self._collapse_btn)
        self._collapse_btn.clicked.connect(self.collapse_clicked.emit)
        row.addWidget(self._collapse_btn)

        # 语音 [F5] (绿/灰 toggle, 默认灰色-关闭)
        self._voice_btn = _IconTextBtn(
            "\uE720", "\U0001F3A4",
            t("run.voice", key=_K_VOICE),
            C_GRAY, C_GRAY_H)
        self._voice_btn.setToolTip(t("tooltip.voice_run"))
        self._install_tip(self._voice_btn)
        self._voice_btn.clicked.connect(self.voice_toggle_clicked.emit)
        row.addWidget(self._voice_btn)

        # 回中 [F6] (绿/灰 toggle, 统一文案)
        self._ac_btn = _IconTextBtn(
            "\uEA3A", "\u21BA",
            t("run.auto_center", key=_K_AC),
            C_GRAY, C_GRAY_H)
        self._ac_btn.setToolTip(t("tooltip.auto_center"))
        self._install_tip(self._ac_btn)
        self._ac_btn.clicked.connect(self.auto_center_clicked.emit)
        row.addWidget(self._ac_btn)

        # 隐藏/显示 [F7] (统一文案)
        self._vis_btn = _IconTextBtn(
            "\uED1A", "\U0001F441",
            t("run.toggle_vis", key=_K_VIS),
            C_GRAY, C_GRAY_H)
        self._vis_btn.setToolTip(t("tooltip.toggle_vis"))
        self._install_tip(self._vis_btn)
        self._vis_btn.clicked.connect(self.toggle_buttons_clicked.emit)
        row.addWidget(self._vis_btn)

        # 软键盘 [F8] (灰色)
        kb_btn = _IconTextBtn(
            "\uE765", "\u2328",
            t("run.soft_keyboard", key=_K_KB),
            C_GRAY, C_GRAY_H)
        kb_btn.setToolTip(t("tooltip.soft_keyboard"))
        self._install_tip(kb_btn)
        kb_btn.clicked.connect(self.soft_keyboard_clicked.emit)
        row.addWidget(kb_btn)

        # 穿透模式 (3-state cycle)
        self._pt_btn = _IconTextBtn(
            "\uE739", "\u26A1",
            t("run.pt_off", key=_K_PTOFF),
            C_BLUE, C_BLUE_H, fg="#FFF")
        self._pt_btn.setToolTip(t("tooltip.passthrough"))
        self._install_tip(self._pt_btn)
        self._pt_btn.clicked.connect(self._cycle_pt)
        row.addWidget(self._pt_btn)

        # 分隔线
        row.addWidget(_VSep())

        # 停止 [F12] (#6E1E1E)
        stop_btn = _IconTextBtn(
            "\uE71A", "\u25A0",
            t("run.stop", key=_K_STOP),
            C_CLOSE, C_CLOSE_H, fg="#FFF")
        stop_btn.setToolTip(t("tooltip.stop"))
        self._install_tip(stop_btn)
        stop_btn.clicked.connect(self.stop_clicked.emit)
        row.addWidget(stop_btn)

    # ── 穿透循环 ──────────────────────────────────────────────

    def _cycle_pt(self):
        from core.constants import PT_CYCLE
        idx = PT_CYCLE.index(self._pt_mode) if self._pt_mode in PT_CYCLE else 0
        new_mode = PT_CYCLE[(idx + 1) % len(PT_CYCLE)]
        self.pt_clicked.emit(new_mode)

    # ── 状态更新 (外部调用) ──────────────────────────────────

    def update_voice_state(self, enabled: bool):
        """语音开关状态变化 → 更新按钮颜色"""
        if enabled:
            self._voice_btn.set_colors(C_GREEN, C_GREEN_H)
            self._voice_btn.set_icon_text("\uE720", "\U0001F3A4")
        else:
            self._voice_btn.set_colors(C_GRAY, C_GRAY_H)
            self._voice_btn.set_icon_text("\uE720", "\U0001F3A4")

    def update_auto_center(self, enabled):
        self._auto_center = enabled
        # 仅切换颜色和icon，文案统一为 "回中 [F6]"
        if enabled:
            self._ac_btn.set_colors(C_GREEN, C_GREEN_H)
            self._ac_btn.set_icon_text("\uE7C9", "\u2714")
        else:
            self._ac_btn.set_colors(C_GRAY, C_GRAY_H)
            self._ac_btn.set_icon_text("\uEA3A", "\u21BA")

    def update_buttons_visibility(self, hidden):
        self._buttons_hidden = hidden
        # 仅切换icon，文案统一为 "隐藏/显示 [F7]"
        if hidden:
            self._vis_btn.set_icon_text("\uE7B3", "\U0001F648")
        else:
            self._vis_btn.set_icon_text("\uED1A", "\U0001F441")

    def update_collapse_state(self, active: bool):
        """悬浮球是否处于激活状态: 激活 → 琥珀色; 否则恢复灰色"""
        if active:
            self._collapse_btn.set_colors(C_AMBER_D, C_AMBER)
        else:
            self._collapse_btn.set_colors(C_GRAY, C_GRAY_H)

    def update_cursor_state(self, visible: bool):
        """自绘光标显隐: 仅切图标 (睁眼/闭眼), 颜色恒为灰 — 与 F7 一致"""
        if visible:
            self._cursor_btn.set_icon_text("", "\U0001F441")
        else:
            self._cursor_btn.set_icon_text("", "\U0001F648")

    def update_pt_mode(self, mode):
        self._pt_mode = mode
        hotkeys = {}
        try:
            from core.config_manager import load_hotkeys
            hotkeys = load_hotkeys()
        except Exception:
            pass

        PT_MAP = {
            PT_ON: {
                "bg": C_GRAY, "bg_h": C_GRAY_H,
                "icon": "\uE73E", "fallback": "\u2714",
                "text": t("run.pt_on", key=hotkeys.get('pt_on', 'F9').upper()),
                "fg": "#E0E0E0",
            },
            PT_OFF: {
                "bg": C_BLUE, "bg_h": C_BLUE_H,
                "icon": "\uE739", "fallback": "\u26A1",
                "text": t("run.pt_off", key=hotkeys.get('pt_off', 'F10').upper()),
                "fg": "#FFF",
            },
            PT_BLOCK: {
                "bg": C_AMBER_D, "bg_h": C_AMBER,
                "icon": "\uE72E", "fallback": "\u26D4",
                "text": t("run.pt_block", key=hotkeys.get('pt_block', 'F11').upper()),
                "fg": "#FFF",
            },
        }
        m = PT_MAP.get(mode, PT_MAP[PT_OFF])
        self._pt_btn.set_colors(m["bg"], m["bg_h"])
        self._pt_btn.set_icon_text(m["icon"], m["fallback"])
        self._pt_btn.set_label(m["text"])
        # 更新文字颜色
        if hasattr(self._pt_btn, '_text_lbl'):
            self._pt_btn._text_lbl.setStyleSheet(
                f"color: {m['fg']}; background: transparent;")
        if hasattr(self._pt_btn, '_icon_lbl') and self._pt_btn._icon_lbl:
            self._pt_btn._icon_lbl.setStyleSheet(
                f"color: {m['fg']}; background: transparent;")

    def set_profile_name(self, name):
        """显示 icon + 方案名称（过长则截断为 ...）"""
        from PyQt6.QtGui import QFontMetrics
        metrics = QFontMetrics(self._profile_lbl.font())
        elided = metrics.elidedText(
            name, Qt.TextElideMode.ElideRight, self._profile_lbl.maximumWidth())
        self._profile_lbl.setText(elided)
        self._profile_lbl.setToolTip(name)  # 完整名称显示在 tooltip

    # ── 定位 ─────────────────────────────────────────────────

    def _position_toolbar(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        self.adjustSize()
        w = min(RUN_W, screen.width() - 40)
        h = self.sizeHint().height()
        x = (screen.width() - w) // 2
        y = screen.height() - h - RUN_BOTTOM_MARGIN
        self.setGeometry(x, y, w, h)

    def set_saved_position(self, x, y):
        """从配置恢复工具栏位置（若坐标有效则使用，否则居中默认）"""
        if x is not None and y is not None:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QRect
            _ps = QApplication.primaryScreen()
            screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
            self.adjustSize()
            w = min(RUN_W, screen.width() - 40)
            h = self.sizeHint().height()
            # 确保在屏幕范围内
            x = max(0, min(x, screen.width() - w))
            y = max(0, min(y, screen.height() - h))
            self.setGeometry(x, y, w, h)

    # ── Tip 事件过滤器 ───────────────────────────────────────

    def _install_tip(self, widget):
        """为按钮安装 hover 事件过滤器，触发下方 tip 浮窗。"""
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.Enter:
            tip_text = obj.toolTip()
            if tip_text:
                self._tip.show_tip(tip_text, self)
        elif event.type() == QEvent.Type.Leave:
            self._tip.hide_tip()
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        self._tip.hide_tip()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._tip.close()
        super().closeEvent(event)

    # ── 拖拽 ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        self.raise_()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            # 屏幕边缘保护：不允许拖出屏幕
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QRect
            _ps = QApplication.primaryScreen()
            screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
            x = max(screen.left(), min(new_pos.x(), screen.right() - self.width() + 1))
            y = max(screen.top(), min(new_pos.y(), screen.bottom() - self.height() + 1))
            self.move(x, y)
            self.moved.emit()  # 同步软键盘位置
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            # 拖拽结束，发射位置变更信号用于持久化
            pos = self.frameGeometry().topLeft()
            self.position_changed.emit(pos.x(), pos.y())
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class CollapsedBubble(QWidget):
    """悬浮球 — 显示"蛋挞"图标，可拖动。
    左键单击 → 切换工具栏显示/隐藏；右键单击 → 切换按键显示/隐藏 (同 F7)。
    """

    toggle_toolbar_requested = pyqtSignal()
    toggle_buttons_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    moved = pyqtSignal(int, int)         # 拖拽结束后发出 (x, y)

    SIZE = 56
    DRAG_THRESHOLD = 4    # 鼠标移动 >4px 才视为拖拽, 否则当点击

    def __init__(self, parent=None):
        super().__init__(parent)
        # WindowDoesNotAcceptFocus: 在 Win32 层设 WS_EX_NOACTIVATE,
        # 让点击/拖动悬浮球时不抢前台焦点 — 否则游戏会失焦暂停,
        # 配合 Special K 禁鼠标时还会切不回游戏。
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self.SIZE, self.SIZE)
        # hover 提示文字 (多行, 列出三键 + 拖动); 用自定义浮窗显示 (原生 tooltip
        # 在 WA_ShowWithoutActivating 的 overlay 窗口上弹不出来)
        self._tip_text = (
            "左键 · 工具栏显隐\n"
            "右键 · 按键显隐 (F7)\n"
            "中键 · 停止运行\n"
            "拖动 · 移动位置"
        )
        self._tip = ToolbarTipWidget()

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        frame = QFrame(self)
        self._frame = frame
        frame.installEventFilter(self)
        frame.setObjectName("bubble")
        # hover 比常态背景加深 ~12%，可感知但不刺眼
        frame.setStyleSheet(f"""
            QFrame#bubble {{
                background: {C_PANEL};
                border-radius: 10px;
                border: 1px solid #444;
            }}
            QFrame#bubble:hover {{
                background: #1F1F1F;
                border: 1px solid #555;
            }}
        """)
        outer.addWidget(frame)

        inner = QHBoxLayout(frame)
        inner.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background: transparent;")
        # 从 assets/icon.ico 加载 (内含多分辨率), 缩放到 40px 居中显示
        import os
        from core.constants import APP_DIR
        _ico_path = os.path.join(APP_DIR, "assets", "icon.ico")
        _pm = QIcon(_ico_path).pixmap(40, 40) if os.path.exists(_ico_path) else QPixmap()
        if not _pm.isNull():
            lbl.setPixmap(_pm)
        else:
            lbl.setText("蛋挞")
            lbl.setFont(_make_font(get_font(), 14, bold=True))
            lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        inner.addWidget(lbl)

        self._drag_pos = None
        self._moved = False
        self._press_button = None
        self._press_global_pos = None

    def show_at(self, x, y):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = max(screen.left(), min(x, screen.right() - self.width() + 1))
        y = max(screen.top(), min(y, screen.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
        self.raise_()

    # ── hover 提示 ──────────────────────────────────────────
    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._frame:
            if event.type() == QEvent.Type.Enter:
                self._tip.show_tip(self._tip_text, self)
            elif event.type() == QEvent.Type.Leave:
                self._tip.hide_tip()
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        self._tip.hide_tip()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._tip.close()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        self.raise_()
        # 仅左键支持拖拽; 三个键按下都记录起点用于点击/拖拽判定
        if event.button() in (Qt.MouseButton.LeftButton,
                              Qt.MouseButton.RightButton,
                              Qt.MouseButton.MiddleButton):
            self._press_button = event.button()
            self._press_global_pos = event.globalPosition().toPoint()
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self._moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_pos and getattr(self, '_press_button', None) == Qt.MouseButton.LeftButton
                and event.buttons() & Qt.MouseButton.LeftButton):
            # 越过阈值后才认为是拖拽
            cur = event.globalPosition().toPoint()
            if not self._moved:
                dx = cur.x() - self._press_global_pos.x()
                dy = cur.y() - self._press_global_pos.y()
                if (dx * dx + dy * dy) < (self.DRAG_THRESHOLD * self.DRAG_THRESHOLD):
                    super().mouseMoveEvent(event)
                    return
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QRect
            new_pos = cur - self._drag_pos
            _ps = QApplication.primaryScreen()
            screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
            x = max(screen.left(), min(new_pos.x(), screen.right() - self.width() + 1))
            y = max(screen.top(), min(new_pos.y(), screen.bottom() - self.height() + 1))
            self.move(x, y)
            self._moved = True
            self._tip.hide_tip()   # 拖动时不显示提示
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        pressed_btn = getattr(self, '_press_button', None)
        moved = self._moved
        self._drag_pos = None
        self._press_button = None
        # 未发生拖拽时按按钮派发: 左键→切工具栏, 右键→切按键, 中键→停止
        if not moved and event.button() == pressed_btn:
            if pressed_btn == Qt.MouseButton.LeftButton:
                self.toggle_toolbar_requested.emit()
            elif pressed_btn == Qt.MouseButton.RightButton:
                self.toggle_buttons_requested.emit()
            elif pressed_btn == Qt.MouseButton.MiddleButton:
                self.stop_requested.emit()
        elif moved:
            self.moved.emit(self.x(), self.y())
        super().mouseReleaseEvent(event)
