"""
TEGG Touch 蛋挞 (PyQt6) - edit_toolbar.py
编辑模式工具栏 — 可拖动的三行任务布局。

  Row 1: Profile | Quick switch | Opacity | Scale | Minimize | Settings | Close
  Row 2: Simulation label | Voice label | Soft keyboard label
  Row 3: Mode switch + contextual controls | Voice | Keyboard + Remap | Run
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QFrame, QSlider,
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QFontDatabase

from core.i18n import t, get_font
from core.constants import (
    TOOLBAR_WIDTH, TOOLBAR_HEIGHT, TOOLBAR_RADIUS,
    TOOLBAR_BOTTOM_MARGIN, APP_VERSION,
)
from views.toolbar_tip_widget import ToolbarTipWidget
from views.ui_components import (
    OUTER_RADIUS, INNER_RADIUS, SMALL_RADIUS,
    RECESSED_BG, PANEL_BG, CONTROL_BG, AMBER_TEXT, text_on_surface,
)

# ── 功能色保持原配色；基础灰色按表面距离统一 ──
C_CYBER = "#0C4A6E"
C_CYBER_H = "#0284C7"
C_GRAY = CONTROL_BG
C_GRAY_H = "#505050"
C_AMBER = "#F59E0B"
C_AMBER_D = "#D97706"
C_CLOSE = "#6E1E1E"
C_CLOSE_H = "#8B2020"
C_PANEL = PANEL_BG
C_WH_ON = "#E11D48"       # 玫瑰红 (rose-600)
C_WH_ON_H = "#F43F5E"     # 玫瑰红 hover (rose-500)

# ── 图标字体检测 ──
_ICON_FONT = None


def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""


def _make_font(name, pixel_size, bold=False):
    f = QFont(name)
    f.setPixelSize(pixel_size)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── 拖拽把手 (原版: 4行×2列圆点 + 分隔线) ──
class _DragHandle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(30)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = 14, self.height() // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#666"))
        for dy in [-12, -4, 4, 12]:
            for dx in [-4, 4]:
                p.drawEllipse(cx + dx - 2, cy + dy - 2, 4, 4)
        p.setPen(QPen(QColor("#444"), 1))
        p.drawLine(28, 4, 28, self.height() - 4)


# ── 竖分隔线 (原版: #555, 1px) ──
class _VSep(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(12)

    def paintEvent(self, event):
        p = QPainter(self)
        x = self.width() // 2
        p.setPen(QPen(QColor("#555"), 1))
        p.drawLine(x, 4, x, self.height() - 4)


# ── 图标+文字按钮 (自适应宽度, 深灰圆角) ──
class _IconTextBtn(QPushButton):
    """带图标字体和文字的工具栏按钮 — 宽度自适应内容。"""

    def __init__(self, icon_char, fallback, text, bg, bg_hover,
                 fg="#E0E0E0", width=None, height=40, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(height)
        if width:
            self.setFixedWidth(width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg = bg
        self._bg_h = bg_hover
        self._fg = fg
        self._apply_style()

        fn = get_font()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(4)

        # Icon
        if _ICON_FONT:
            self._icon_lbl = QLabel(icon_char)
            self._icon_lbl.setFont(_make_font(_ICON_FONT, 20))
        elif fallback:
            self._icon_lbl = QLabel(fallback)
            self._icon_lbl.setFont(_make_font(fn, 16, bold=True))
        else:
            self._icon_lbl = None

        if self._icon_lbl:
            self._icon_lbl.setStyleSheet(f"color: {text_on_surface(bg, fg)}; background: transparent;")
            self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(self._icon_lbl)

        # Text
        self._text_lbl = QLabel(text)
        self._text_lbl.setFont(_make_font(fn, 14))
        self._text_lbl.setStyleSheet(f"color: {text_on_surface(bg, fg)}; background: transparent;")
        self._text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._text_lbl)

    def sizeHint(self):
        lay = self.layout()
        if lay:
            m = self.contentsMargins()
            s = lay.sizeHint()
            return QSize(
                s.width() + m.left() + m.right(),
                max(s.height() + m.top() + m.bottom(), self.minimumHeight())
            )
        return super().sizeHint()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._bg}; border: none; border-radius: {INNER_RADIUS}px;
            }}
            QPushButton:hover {{ background: {self._bg_h}; }}
        """)

    def set_colors(self, bg, bg_hover):
        self._bg = bg
        self._bg_h = bg_hover
        self._apply_style()
        for label in (self._icon_lbl, self._text_lbl):
            if label:
                label.setStyleSheet(f"color: {text_on_surface(bg, self._fg)}; background: transparent;")

    def set_icon_text(self, icon_char, fallback=None):
        if self._icon_lbl:
            self._icon_lbl.setText(icon_char if _ICON_FONT else (fallback or ""))

    def set_label(self, text):
        self._text_lbl.setText(text)


class _ModeSwitch(QFrame):
    """Two choices share one recessed track and one sliding selection."""

    requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('simulation_switch')
        self.setFixedSize(144, 40)
        self.setStyleSheet(f'QFrame#simulation_switch {{ background: {RECESSED_BG}; border: none; border-radius: 8px; }}')
        self._thumb = QFrame(self)
        self._thumb.setStyleSheet(f'background: {C_AMBER}; border: none; border-radius: 6px;')
        self._thumb.setGeometry(4, 4, 68, 32)
        self._thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._animation = QPropertyAnimation(self._thumb, b'geometry', self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.buttons = {}
        for index, (mode, label) in enumerate((('keyboard', t('toolbar.sim_keyboard')),
                                               ('gamepad', t('toolbar.sim_gamepad')))):
            button = QPushButton(label, self)
            button.setGeometry(4 + index * 68, 4, 68, 32)
            button.setFont(_make_font(get_font(), 13))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _, picked=mode: self.requested.emit(picked))
            self.buttons[mode] = button

    def set_mode(self, mode):
        target = QRect(72 if mode == 'gamepad' else 4, 4, 68, 32)
        self._animation.stop()
        if self.isVisible() and self._thumb.geometry() != target:
            self._animation.setStartValue(self._thumb.geometry())
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self._thumb.setGeometry(target)
        for key, button in self.buttons.items():
            color = AMBER_TEXT if key == mode else '#AAAAAA'
            button.setStyleSheet(f'QPushButton {{ background: transparent; color: {color}; border: none; border-radius: 6px; }}')


class _CheckIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.checked = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(C_AMBER if self.checked else '#AAAAAA'), 1.5))
        painter.setBrush(QColor(C_AMBER) if self.checked else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(2, 2, 16, 16, SMALL_RADIUS, SMALL_RADIUS)
        if self.checked:
            painter.setPen(QPen(QColor(AMBER_TEXT), 2.0, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(6, 10, 9, 13)
            painter.drawLine(9, 13, 14, 7)


class _ComponentToggle(_IconTextBtn):
    """Singleton entry: gray button, an empty / checked indicator, original signal."""

    def __init__(self, text, width, parent=None):
        super().__init__('', '', text, C_GRAY, C_GRAY_H, width=width, parent=parent)
        if self._icon_lbl:
            self.layout().removeWidget(self._icon_lbl)
            self._icon_lbl.deleteLater()
            self._icon_lbl = None
        self._indicator = _CheckIndicator(self)
        # 与图标标签一样参与分配余宽, 文字位置与其他组件按钮一致
        slot = QWidget(self)
        slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        slot_lay = QHBoxLayout(slot)
        slot_lay.setContentsMargins(0, 0, 0, 0)
        slot_lay.addWidget(self._indicator, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.layout().insertWidget(0, slot)
        self.setCheckable(True)

    def set_colors(self, background, hover):
        super().set_colors(C_GRAY, C_GRAY_H)

    def set_icon_text(self, icon, fallback=None):
        checked = icon == '\uE73E'
        self.setChecked(checked)
        self._indicator.checked = checked
        self._indicator.update()


# ═══════════════════════════════════════════════════════════════
class EditToolbar(QWidget):
    """编辑模式工具栏 — 浮动在场景底部"""

    # 信号
    add_button_clicked = pyqtSignal()
    add_profile_switch_clicked = pyqtSignal()
    add_center_band_clicked = pyqtSignal()
    voice_clicked = pyqtSignal()
    keyboard_clicked = pyqtSignal()
    key_remap_clicked = pyqtSignal()
    run_clicked = pyqtSignal()
    wheel_clicked = pyqtSignal()
    opacity_changed = pyqtSignal(float)
    scene_scale_changed = pyqtSignal(int)   # 百分比 50-200
    profile_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    quit_clicked = pyqtSignal()
    moved = pyqtSignal()  # 工具栏被拖拽移动时发出，用于同步软键盘位置
    sim_mode_change_requested = pyqtSignal(str)  # 'keyboard' | 'gamepad'
    # 手柄模式按钮添加 (+手柄键 / +摇杆) + 方向盘 toggle
    add_gp_button_clicked = pyqtSignal()
    add_gp_stick_clicked = pyqtSignal()
    gp_wheel_toggle_clicked = pyqtSignal()   # 方向盘 toggle (单例: 显/隐)

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

        self._wheel_on = False
        self._drag_pos = None
        self._sim_mode = 'keyboard'  # 'keyboard' | 'gamepad'
        self._tip = ToolbarTipWidget()
        self._init_ui()
        self._position_toolbar()

    # ── UI 构建 ──────────────────────────────────────────────

    def _init_ui(self):
        from PyQt6.QtWidgets import QStackedWidget, QSizePolicy
        from views.ui_components import ui_text
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setObjectName("et_container")
        container.setStyleSheet(f"QFrame#et_container {{ background: {C_PANEL}; border: none; border-radius: {OUTER_RADIUS}px; }}")
        outer.addWidget(container)
        main = QVBoxLayout(container)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(10)
        grip = _DragHandle()
        grip.setFixedWidth(24)
        grip.setCursor(Qt.CursorShape.SizeAllCursor)
        header.addWidget(grip)
        self._profile_btn = self._build_profile_btn(fn)
        self._profile_btn.setFixedWidth(240)
        self._prof_name_lbl.setMinimumWidth(0)
        self._prof_name_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._profile_full_name = "Default"
        self._profile_btn.setToolTip(t("tooltip.profiles"))
        self._install_tip(self._profile_btn)
        header.addWidget(self._profile_btn)

        self._switch_btn = _IconTextBtn('\uE710', '+', t('profile_switch.entry'), C_GRAY, C_GRAY_H)
        if self._switch_btn._icon_lbl:
            self._switch_btn._icon_lbl.setFont(_make_font(_ICON_FONT or fn, 24))
        self._switch_btn.clicked.connect(self.add_profile_switch_clicked.emit)
        self._switch_btn.setToolTip(t('profile_switch.entry_tip'))
        self._install_tip(self._switch_btn)
        header.addWidget(self._switch_btn)

        def slider_group(label, color, low, high, value, callback):
            widget = QWidget()
            widget.setMinimumWidth(125)
            column = QVBoxLayout(widget)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            column.addLayout(row)
            text = QLabel(label)
            text.setFont(_make_font(fn, 12))
            text.setStyleSheet("color: #AAA; background: transparent;")
            row.addWidget(text)
            row.addStretch()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            slider.setValue(value)
            slider.setFixedHeight(24)
            slider.setMinimumWidth(54)
            slider.setStyleSheet(f"QSlider::groove:horizontal {{ background: {RECESSED_BG}; height: 6px; border-radius: 3px; }} QSlider::sub-page:horizontal {{ background: {color}; border-radius: 3px; }} QSlider::add-page:horizontal {{ background: {RECESSED_BG}; border-radius: 3px; }} QSlider::handle:horizontal {{ background: #DDD; border: none; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }}")
            slider.valueChanged.connect(callback)
            column.addWidget(slider)
            number = QLabel(f"{value}%")
            number.setFixedWidth(40)
            number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            number.setFont(_make_font(fn, 13))
            number.setStyleSheet(f"color: {color}; background: transparent;")
            row.addWidget(number)
            header.addWidget(widget, 1)
            return slider, number

        self._slider, self._val_lbl = slider_group(t("toolbar.opacity"), C_AMBER, 10, 90, 75, self._on_opacity)
        self._scale_slider, self._scale_val_lbl = slider_group(t("toolbar.scale"), C_AMBER, 50, 200, 100, self._on_scale_changed)
        self._scale_slider.setSingleStep(10)
        self._scale_slider.setPageStep(10)
        header.addWidget(_VSep())
        for icon, fallback, signal, tip in [
            ("\uE921", "_", self.minimize_clicked, "tooltip.minimize"),
            ("\uE713", "⚙", self.settings_clicked, "tooltip.settings"),
            ("\uE711", "×", self.quit_clicked, "tooltip.quit")]:
            button = self._build_sq_btn(icon, fallback, C_CLOSE if tip == "tooltip.quit" else C_GRAY,
                                        C_CLOSE_H if tip == "tooltip.quit" else C_GRAY_H, "#CCC", signal)
            button.setToolTip(t(tip))
            self._install_tip(button)
            header.addWidget(button)
        main.addLayout(header)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #444;")
        main.addWidget(line)
        groups = QHBoxLayout()
        groups.setSpacing(8)

        remap = _IconTextBtn("\uE8AB", "⇄", t("toolbar.key_remap"), C_GRAY, C_GRAY_H)
        self._component_width = max(108, remap.sizeHint().width() + 8)
        self._switch_btn.setFixedWidth(max(self._component_width, self._switch_btn.sizeHint().width()))
        remap.setFixedWidth(self._component_width)
        self._remap_btn = remap

        def group(title, width=None):
            widget = QWidget()
            if width:
                widget.setFixedWidth(width)
            col = QVBoxLayout(widget)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(8)
            text = QLabel(title)
            text.setFixedHeight(18)
            text.setFont(_make_font(fn, 12))
            text.setStyleSheet("color: #AAA; background: transparent;")
            col.addWidget(text)
            row = QHBoxLayout()
            row.setSpacing(8)
            col.addLayout(row)
            return widget, row

        self._mode_group, mode = group(ui_text("添加模拟组件", "Add input components"), 144 + 3 * self._component_width + 24)
        self._mode_switch = _ModeSwitch()
        self._mode_switch.requested.connect(self._on_sim_mode_picked)
        self._mode_buttons = self._mode_switch.buttons
        mode.addWidget(self._mode_switch)
        self._mode_stack = QStackedWidget()
        self._mode_stack.setFixedHeight(40)
        mode.addWidget(self._mode_stack, 1)
        for specs in [
            [("_add_kb_btn", "toolbar.add_button", self.add_button_clicked.emit, "＋"),
             ("_cb_btn", "toolbar.add_center_band", self.add_center_band_clicked.emit, "＋"),
             ("_wheel_btn", "toolbar.center_wheel", self._on_wheel_toggle, "▣")],
            [("_add_gp_btn", "toolbar.add_gp_button", self.add_gp_button_clicked.emit, "＋"),
             ("_add_stick_btn", "toolbar.add_gp_stick", self.add_gp_stick_clicked.emit, "＋"),
             ("_wheel_gp_btn", "toolbar.toggle_gp_wheel", self._on_gp_wheel_toggle, "▣")]]:
            page = QWidget()
            row = QHBoxLayout(page)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            for attr, label, callback, icon in specs:
                if attr in ('_wheel_btn', '_wheel_gp_btn'):
                    button = _ComponentToggle(t(label), self._component_width)
                else:
                    button = _IconTextBtn('\uE710', '+', t(label), C_GRAY, C_GRAY_H, width=self._component_width)
                    if button._icon_lbl:
                        button._icon_lbl.setFont(_make_font(_ICON_FONT or fn, 24))
                button.clicked.connect(callback)
                button.setToolTip(t(label))
                self._install_tip(button)
                button.set_colors(C_GRAY, C_GRAY_H)
                setattr(self, attr, button)
                row.addWidget(button)
            self._mode_stack.addWidget(page)
        self._wheel_gp_on = False
        groups.addWidget(self._mode_group)
        groups.addWidget(_VSep())
        voice_widget, voice = group(ui_text("语音控制", "Voice control"), self._component_width)
        voice_button = _IconTextBtn("\uE720", "♪", t("toolbar.voice"), C_GRAY, C_GRAY_H, width=self._component_width)
        self._voice_btn = voice_button
        voice_button.clicked.connect(self.voice_clicked.emit)
        voice_button.setToolTip(ui_text("设置语音指令、识别设备，并测试当前指令", "Edit voice commands, recognition settings and test commands."))
        self._install_tip(voice_button)
        voice.addWidget(voice_button)
        groups.addWidget(voice_widget)
        groups.addWidget(_VSep())
        keys_widget, keys = group(t("toolbar.keyboard"), self._component_width * 2 + 8)
        self._keyboard_btn = _IconTextBtn("\uE765", "⌨", ui_text("打开", "Show"), C_GRAY, C_GRAY_H, width=self._component_width)
        self._keyboard_btn.clicked.connect(self.keyboard_clicked.emit)
        self._keyboard_btn.setToolTip(t("tooltip.keyboard"))
        self._install_tip(self._keyboard_btn)
        keys.addWidget(self._keyboard_btn)
        remap.clicked.connect(self.key_remap_clicked.emit)
        remap.setToolTip(t("tooltip.key_remap"))
        self._install_tip(remap)
        keys.addWidget(remap)
        groups.addWidget(keys_widget)
        self._launch_separator = _VSep()
        groups.addWidget(self._launch_separator)
        launch_widget, launch = group(f"{ui_text('蛋挞', 'TEGG Touch')} v{APP_VERSION}")
        self._brand_label = launch_widget.layout().itemAt(0).widget()
        self._brand_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        run = _IconTextBtn("\uE768", "▶", t("toolbar.start"), C_AMBER_D, C_AMBER, fg="#FFF")
        run.setMinimumWidth(96)
        self._run_btn = run
        run.clicked.connect(self.run_clicked.emit)
        run.setToolTip(t("tooltip.start"))
        self._install_tip(run)
        launch.addWidget(run)
        groups.addWidget(launch_widget, 1)
        main.addLayout(groups)
        self._refresh_mode_visual()

    def _refresh_mode_visual(self):
        self._mode_switch.set_mode(self._sim_mode)
        self._mode_stack.setCurrentIndex(1 if self._sim_mode == 'gamepad' else 0)

    def set_keyboard_visible(self, visible):
        from views.ui_components import ui_text
        self._keyboard_btn.set_label(ui_text("隐藏", "Hide") if visible else ui_text("打开", "Show"))

    def _elide_profile_name(self):
        metrics = self._prof_name_lbl.fontMetrics()
        self._prof_name_lbl.setText(metrics.elidedText(self._profile_full_name, Qt.TextElideMode.ElideRight, self._prof_name_lbl.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_profile_full_name'):
            self._elide_profile_name()

    # ── 组件构建辅助 ─────────────────────────────────────────

    def _build_profile_btn(self, fn):
        """Compact profile selector with a document icon for both input modes."""
        btn = QPushButton()
        btn.setFixedHeight(40)
        btn.setMinimumWidth(220)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; border: none; border-radius: {INNER_RADIUS}px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        btn.clicked.connect(self.profile_clicked.emit)

        lay = QHBoxLayout(btn)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(6)

        # 图标
        if _ICON_FONT:
            ic = QLabel("\uE8A5")
            ic.setFont(_make_font(_ICON_FONT, 20))
        else:
            ic = QLabel("\U0001F4C4")
        ic.setStyleSheet("color: #E0E0E0; background: transparent;")
        ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(ic)

        # 名称
        self._prof_name_lbl = QLabel("Default")
        self._prof_name_lbl.setFont(_make_font(fn, 16))
        self._prof_name_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        self._prof_name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._prof_name_lbl, 1)

        # 下拉箭头
        if _ICON_FONT:
            ar = QLabel("\uE700")
            ar.setFont(_make_font(_ICON_FONT, 14))
        else:
            ar = QLabel("\u2630")
        ar.setStyleSheet("color: #AAA; background: transparent;")
        ar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(ar)

        return btn

    def _build_sq_btn(self, icon_char, fallback, bg, bg_h, fg, signal):
        """36×36 方形图标按钮 (关于/设置/关闭)"""
        btn = QPushButton()
        btn.setFixedSize(40, 40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            btn.setText(icon_char)
            btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            btn.setText(fallback)
            btn.setFont(_make_font(get_font(), 16, bold=True))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {fg}; border: none; border-radius: {INNER_RADIUS}px;
            }}
            QPushButton:hover {{ background: {bg_h}; }}
        """)
        btn.clicked.connect(signal.emit)
        return btn

    # ── 回调 ─────────────────────────────────────────────────

    def _on_wheel_toggle(self):
        self._wheel_on = not self._wheel_on
        if self._wheel_on:
            self._wheel_btn.set_colors(C_WH_ON, C_WH_ON_H)
            self._wheel_btn.set_icon_text("\uE73E", "\u2611")
        else:
            self._wheel_btn.set_colors(C_GRAY, C_GRAY_H)
            self._wheel_btn.set_icon_text("\uE739", "\u25a3")
        self.wheel_clicked.emit()

    def _on_gp_wheel_toggle(self):
        """方向盘 toggle: 翻转视觉 (玫红/灰) + emit 信号"""
        self._wheel_gp_on = not self._wheel_gp_on
        self._apply_gp_wheel_visual()
        self.gp_wheel_toggle_clicked.emit()

    def _apply_gp_wheel_visual(self):
        if self._wheel_gp_on:
            self._wheel_gp_btn.set_colors(C_WH_ON, C_WH_ON_H)
            self._wheel_gp_btn.set_icon_text("\uE73E", "\u2611")
        else:
            self._wheel_gp_btn.set_colors(C_GRAY, C_GRAY_H)
            self._wheel_gp_btn.set_icon_text("\uE739", "\u25a3")

    def set_gp_wheel_state(self, visible: bool):
        """外部同步 (启动 / 编辑器内删除等场景): 直接设状态, 不 emit 信号"""
        self._wheel_gp_on = bool(visible)
        self._apply_gp_wheel_visual()

    def _on_opacity(self, value):
        self._val_lbl.setText(f"{value}%")
        self.opacity_changed.emit(value / 100.0)

    def _on_scale_changed(self, value):
        """场景缩放滑块回调 — 吸附到 10% 步进"""
        snapped = round(value / 10) * 10
        snapped = max(50, min(200, snapped))
        if snapped != value:
            self._scale_slider.blockSignals(True)
            self._scale_slider.setValue(snapped)
            self._scale_slider.blockSignals(False)
        self._scale_val_lbl.setText(f"{snapped}%")
        self.scene_scale_changed.emit(snapped)

    def set_opacity(self, value: float):
        """外部设置透明度 (0.1~0.9)，同步滑块和标签"""
        int_val = max(10, min(90, int(value * 100)))
        self._slider.blockSignals(True)
        self._slider.setValue(int_val)
        self._slider.blockSignals(False)
        self._val_lbl.setText(f"{int_val}%")

    def set_scene_scale(self, percent: int):
        """外部设置场景缩放百分比 (50-200)，同步滑块和标签"""
        percent = max(50, min(200, round(percent / 10) * 10))
        self._scale_slider.blockSignals(True)
        self._scale_slider.setValue(percent)
        self._scale_slider.blockSignals(False)
        self._scale_val_lbl.setText(f"{percent}%")

    # ── 定位 ─────────────────────────────────────────────────

    def _position_toolbar(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        # 宽度取内容自适应与原版 TOOLBAR_WIDTH 的较大值，但不超出屏幕
        self.adjustSize()
        w = min(max(TOOLBAR_WIDTH, self.sizeHint().width()), screen.width() - 40)
        h = self.sizeHint().height()
        x = (screen.width() - w) // 2
        y = screen.height() - h - TOOLBAR_BOTTOM_MARGIN
        self.setGeometry(x, y, w, h)

    # ── 外部接口 ─────────────────────────────────────────────

    def set_profile_name(self, name: str):
        self._profile_full_name = name
        self._profile_btn.setToolTip(name + "\n" + t("tooltip.profiles"))
        self._elide_profile_name()

    def set_wheel_state(self, visible: bool):
        """同步轮盘按钮外观 — 配置加载/切换时调用"""
        self._wheel_on = visible
        if visible:
            self._wheel_btn.set_colors(C_WH_ON, C_WH_ON_H)
            self._wheel_btn.set_icon_text("\uE73E", "\u2611")
        else:
            self._wheel_btn.set_colors(C_GRAY, C_GRAY_H)
            self._wheel_btn.set_icon_text("\uE739", "\u25a3")

    # ── 模拟模式 (键盘 / 手柄) ───────────────────────────────────

    def _on_sim_mode_picked(self, mode: str):
        """模式选择 — 转发给外部决定能否切换 (手柄要先检测驱动)。"""
        if mode == self._sim_mode:
            return
        self.sim_mode_change_requested.emit(mode)

    def set_sim_mode(self, mode: str):
        """Only reflect the mode confirmed by the overlay / driver check."""
        self._sim_mode = mode if mode in ('keyboard', 'gamepad') else 'keyboard'
        self._refresh_mode_visual()

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
        self._drag_pos = None
        super().mouseReleaseEvent(event)
