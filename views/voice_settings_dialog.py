"""
TEGG Touch (PyQt6) - voice_settings_dialog.py
语音指令设置弹窗 — 双栏布局: 左侧指令列表 + 右侧键位面板。
"""

import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QWidget, QScrollArea, QFrame, QApplication, QLineEdit,
    QComboBox, QStackedWidget, QListWidget, QListWidgetItem,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush

from core.i18n import t, get_font, get_lang

# Reuse shared components from existing dialogs
from views.button_editor_dialog import (
    TagInput, _FlowWidget, _get_key_categories, _get_mouse_keys,
    C_PM_BG, C_GRAY, C_GRAY_H, C_AMBER, C_CYBER, C_CYBER_H,
    C_CLOSE, C_CLOSE_H, C_INPUT_BG, C_TAG_BG, C_TAG_HOVER,
    C_TAG_TEXT, C_CAT_LABEL,
)

# ── 颜色常量 ──
C_GREEN = "#10B981"
C_GREEN_H = "#059669"
C_AMBER_D = "#D97706"

# ── 图标字体 ──
_ICON_FONT = None

def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return _ICON_FONT
    from PyQt6.QtGui import QFontDatabase
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""
    return _ICON_FONT

def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── 语言切换按钮 (复用 HotkeySettingsDialog 样式) ──
class _LangBtn(QPushButton):
    def sizeHint(self):
        lay = self.layout()
        if lay:
            m = self.contentsMargins()
            s = lay.sizeHint()
            return QSize(s.width() + m.left() + m.right(),
                         max(s.height() + m.top() + m.bottom(), self.minimumHeight()))
        return super().sizeHint()


class _CheckToggle(QWidget):
    """带勾号的自定义 checkbox — 点击切换选中状态。"""

    def __init__(self, text, fn, checked=True, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # 方框 + 勾
        self._box = QLabel()
        self._box.setFixedSize(18, 18)
        self._box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if _ICON_FONT:
            self._box.setFont(_make_font(_ICON_FONT, 13))
        else:
            self._box.setFont(_make_font(fn, 13, bold=True))
        lay.addWidget(self._box)

        lbl = QLabel(text)
        lbl.setFont(_make_font(fn, 14))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(lbl)

        self._update_style()

    def isChecked(self):
        return self._checked

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._update_style()
        super().mousePressEvent(event)

    def _update_style(self):
        if self._checked:
            icon = "\uE73E" if _ICON_FONT else "\u2713"
            self._box.setText(icon)
            self._box.setStyleSheet(
                f"background: {C_CYBER}; color: #FFF;"
                " border-radius: 4px;"
            )
        else:
            self._box.setText("")
            self._box.setStyleSheet(
                "background: #333; color: transparent;"
                " border: 1px solid #666; border-radius: 4px;"
            )


# ── 单条指令行 ──
class _CommandRow(QFrame):
    """单条语音指令行: 短语输入 + 按键TagInput + 动作选择 + 删除"""
    delete_clicked = pyqtSignal(object)
    focus_changed = pyqtSignal(object)

    def __init__(self, phrase="", keys="", action="click", fn="", parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; }")
        self._action = action
        self._build_ui(phrase, keys, action, fn)

    # Column fixed widths
    COL_PHRASE = 160
    COL_KEYS = 220
    COL_ACT = 180
    COL_DEL = 36

    def _build_ui(self, phrase, keys, action, fn):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        _detect_icon_font()

        # ── Row 1: labels (fixed widths) ──
        r1 = QHBoxLayout()
        r1.setSpacing(8)

        phrase_lbl = QLabel(t("voice_dialog.phrase"))
        phrase_lbl.setFont(_make_font(fn, 14))
        phrase_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        phrase_lbl.setFixedWidth(self.COL_PHRASE)
        r1.addWidget(phrase_lbl)

        keys_lbl = QLabel(t("voice_dialog.keys"))
        keys_lbl.setFont(_make_font(fn, 14))
        keys_lbl.setStyleSheet("color: #666; background: transparent;")
        keys_lbl.setFixedWidth(self.COL_KEYS)
        r1.addWidget(keys_lbl)

        act_lbl = QLabel(t("voice_dialog.action"))
        act_lbl.setFont(_make_font(fn, 14))
        act_lbl.setStyleSheet("color: #666; background: transparent;")
        act_lbl.setFixedWidth(self.COL_ACT)
        r1.addWidget(act_lbl)

        r1.addStretch()
        lay.addLayout(r1)

        # ── Row 2: inputs + delete btn (same fixed widths) ──
        r2 = QHBoxLayout()
        r2.setSpacing(8)

        self._phrase_edit = QLineEdit(phrase)
        self._phrase_edit.setFont(_make_font(fn, 14))
        self._phrase_edit.setPlaceholderText(t("voice_dialog.phrase_placeholder"))
        self._phrase_edit.setFixedSize(self.COL_PHRASE, 36)
        self._phrase_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid {C_GRAY}; border-radius: 6px;
                padding: 2px 8px;
            }}
            QLineEdit:focus {{ border-color: {C_GREEN}; }}
        """)
        r2.addWidget(self._phrase_edit)

        self._keys_input = TagInput(initial_value=keys, accent_color=C_AMBER)
        self._keys_input.setFixedWidth(self.COL_KEYS)
        self._keys_input.setMinimumHeight(36)
        self._keys_input.focusChanged.connect(
            lambda w: self.focus_changed.emit(w))
        r2.addWidget(self._keys_input)

        # Action buttons container
        act_box = QHBoxLayout()
        act_box.setSpacing(4)
        act_box.setContentsMargins(0, 0, 0, 0)
        self._action_btns = {}
        for act_key, act_text in [
            ("click", t("voice_dialog.action_click")),
            ("press", t("voice_dialog.action_press")),
            ("release", t("voice_dialog.action_release")),
        ]:
            btn = QPushButton(act_text)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(_make_font(fn, 13))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, k=act_key: self._set_action(k))
            self._action_btns[act_key] = btn
            act_box.addWidget(btn)

        act_wrapper = QWidget()
        act_wrapper.setStyleSheet("background: transparent;")
        act_wrapper.setLayout(act_box)
        act_wrapper.setFixedSize(self.COL_ACT, 36)
        r2.addWidget(act_wrapper)

        # Delete button (same row, same height)
        del_btn = QPushButton()
        del_btn.setFixedSize(self.COL_DEL, 36)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            del_btn.setText("\uE74D")
            del_btn.setFont(_make_font(_ICON_FONT, 14))
        else:
            del_btn.setText("\u2715")
            del_btn.setFont(_make_font(fn, 13, bold=True))
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self))
        r2.addWidget(del_btn)

        r2.addStretch()
        lay.addLayout(r2)
        self._update_action_styles()

        lay.addSpacing(6)

        # Separator line
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        lay.addWidget(sep)

    def _set_action(self, action):
        self._action = action
        self._update_action_styles()

    def _update_action_styles(self):
        for k, btn in self._action_btns.items():
            if k == self._action:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_CYBER}; color: #FFF;
                        border: none; border-radius: 6px; padding: 0 12px;
                    }}
                    QPushButton:hover {{ background: {C_CYBER_H}; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #404040; color: #AAA;
                        border: none; border-radius: 6px; padding: 0 12px;
                    }}
                    QPushButton:hover {{ background: #505050; }}
                """)

    def get_data(self):
        return {
            'phrase': self._phrase_edit.text().strip(),
            'keys': self._keys_input.get_value(),
            'action': self._action,
        }


# ── 主弹窗类 ──
class VoiceSettingsDialog(QDialog):
    """语音指令设置弹窗 — 双栏布局"""
    settings_saved = pyqtSignal()
    macros_changed = pyqtSignal(list)

    LEFT_W = 640
    RIGHT_W = 520
    PADDING = 20
    WIN_W = LEFT_W + RIGHT_W + PADDING * 2 + 20
    WIN_H = 880

    def __init__(self, voice_commands=None, voice_language=None, voice_mic_device=None, parent=None, macros=None, voice_auto_start=True):
        super().__init__(parent)
        self._macros = list(macros) if macros else []
        self._commands = voice_commands or []
        self._language = voice_language or get_lang()
        self._saved_mic_device = voice_mic_device  # 之前保存的麦克风设备名
        self._auto_start = voice_auto_start
        self._focus_widget = None
        self._command_rows = []
        self._drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        _detect_icon_font()
        self._init_ui()
        self._load_commands()
        self._center_on_screen()

    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("vs_container")
        container.setStyleSheet(f"""
            QFrame#vs_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # ── Title bar ──
        title_row = QHBoxLayout()
        mic_icon = QLabel("\uE720" if _ICON_FONT else "\U0001F3A4")
        if _ICON_FONT:
            mic_icon.setFont(_make_font(_ICON_FONT, 20))
        else:
            mic_icon.setFont(_make_font(fn, 20))
        mic_icon.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(mic_icon)
        title_row.addSpacing(6)

        title_lbl = QLabel(t("voice_dialog.title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        close_btn = QPushButton("\uE711" if _ICON_FONT else "\u2715")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setFont(_make_font(fn, 18, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # Tip
        tip = QLabel(t("voice_dialog.tip"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addSpacing(16)

        # ── Two columns ──
        columns = QHBoxLayout()
        columns.setSpacing(0)

        # === Left column ===
        left = QVBoxLayout()
        left.setSpacing(0)
        left.setContentsMargins(0, 0, 0, 0)

        # Language selector
        left.addLayout(self._build_lang_selector(fn))
        left.addSpacing(20)

        # Divider
        d1 = QFrame()
        d1.setFixedHeight(1)
        d1.setStyleSheet("background: #444;")
        left.addWidget(d1)
        left.addSpacing(10)

        # Command list (scrollable)
        self._cmd_scroll = QScrollArea()
        self._cmd_scroll.setWidgetResizable(True)
        self._cmd_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cmd_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 8px; border: none;
            }
            QScrollBar::handle:vertical {
                background: #404040; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        self._cmd_content = QWidget()
        self._cmd_content.setStyleSheet("background: transparent;")
        self._cmd_layout = QVBoxLayout(self._cmd_content)
        self._cmd_layout.setContentsMargins(0, 0, 10, 0)
        self._cmd_layout.setSpacing(10)
        self._cmd_layout.addStretch()
        self._cmd_scroll.setWidget(self._cmd_content)
        left.addWidget(self._cmd_scroll, 1)

        left.addSpacing(18)

        # Mic status
        left.addLayout(self._build_mic_status(fn))

        left.addSpacing(12)

        # Bottom row: Add command (left) + Save (right)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        add_btn = QPushButton(t("voice_dialog.add_command"))
        add_btn.setFixedHeight(40)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFont(_make_font(fn, 16))
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        add_btn.clicked.connect(self._on_add_command)
        bottom_row.addWidget(add_btn, 1)

        save_btn = QPushButton(t("voice_dialog.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 18, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        bottom_row.addWidget(save_btn, 1)

        left.addLayout(bottom_row)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(self.LEFT_W)
        left_widget.setStyleSheet("background: transparent;")
        columns.addWidget(left_widget)
        columns.addSpacing(20)

        # Divider
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background: #444;")
        columns.addWidget(divider)
        columns.addSpacing(10)

        # === Right column: tabbed (keys + macros) ===
        right = self._build_right_tabbed_panel(fn)
        columns.addWidget(right, 1)

        root.addLayout(columns, 1)

    def _build_lang_selector(self, fn):
        row = QHBoxLayout()
        row.setSpacing(8)

        lang_lbl = QLabel(t("voice_dialog.language"))
        lang_lbl.setFont(_make_font(fn, 16, bold=True))
        lang_lbl.setStyleSheet("color: #CCC; background: transparent;")
        row.addWidget(lang_lbl)
        row.addSpacing(12)

        is_zh = self._language.startswith("zh")

        self._lang_zh_btn = _LangBtn()
        self._lang_zh_btn.setFixedHeight(36)
        self._lang_zh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_zh_btn.clicked.connect(lambda: self._set_lang("zh-CN"))
        zh_lay = QHBoxLayout(self._lang_zh_btn)
        zh_lay.setContentsMargins(10, 0, 10, 0)
        zh_lay.setSpacing(4)
        self._zh_icon_lbl = QLabel("\uE73E" if _ICON_FONT else "\u2713")
        if _ICON_FONT:
            self._zh_icon_lbl.setFont(_make_font(_ICON_FONT, 16))
        else:
            self._zh_icon_lbl.setFont(_make_font(fn, 16, bold=True))
        self._zh_icon_lbl.setStyleSheet("color: #FFF; background: transparent;")
        self._zh_icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        zh_lay.addWidget(self._zh_icon_lbl)
        self._zh_text = QLabel("中文")
        self._zh_text.setFont(_make_font(fn, 16, bold=True))
        self._zh_text.setStyleSheet("color: #FFF; background: transparent;")
        self._zh_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        zh_lay.addWidget(self._zh_text)
        row.addWidget(self._lang_zh_btn)

        row.addSpacing(8)

        self._lang_en_btn = _LangBtn()
        self._lang_en_btn.setFixedHeight(36)
        self._lang_en_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_en_btn.clicked.connect(lambda: self._set_lang("en"))
        en_lay = QHBoxLayout(self._lang_en_btn)
        en_lay.setContentsMargins(10, 0, 10, 0)
        en_lay.setSpacing(4)
        self._en_icon_lbl = QLabel("\uE73E" if _ICON_FONT else "\u2713")
        if _ICON_FONT:
            self._en_icon_lbl.setFont(_make_font(_ICON_FONT, 16))
        else:
            self._en_icon_lbl.setFont(_make_font(fn, 16, bold=True))
        self._en_icon_lbl.setStyleSheet("color: #FFF; background: transparent;")
        self._en_icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        en_lay.addWidget(self._en_icon_lbl)
        self._en_text = QLabel("English")
        self._en_text.setFont(_make_font(fn, 16, bold=True))
        self._en_text.setStyleSheet("color: #FFF; background: transparent;")
        self._en_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        en_lay.addWidget(self._en_text)
        row.addWidget(self._lang_en_btn)

        row.addStretch()

        self._auto_start_cb = _CheckToggle(
            t("voice_dialog.auto_start"), fn, checked=self._auto_start
        )
        row.addWidget(self._auto_start_cb)
        self._update_lang_buttons()
        return row

    def _set_lang(self, lang):
        self._language = lang
        self._update_lang_buttons()

    def _update_lang_buttons(self):
        is_zh = self._language.startswith("zh")

        # 中文按钮: 选中时显示勾 icon
        self._zh_icon_lbl.setVisible(is_zh)
        zh_fg = "#FFF" if is_zh else "#E0E0E0"
        self._zh_text.setStyleSheet(f"color: {zh_fg}; background: transparent;")
        self._zh_icon_lbl.setStyleSheet(f"color: {zh_fg}; background: transparent;")
        self._lang_zh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER if is_zh else '#404040'};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H if is_zh else '#505050'}; }}
        """)

        # English 按钮: 选中时显示勾 icon
        self._en_icon_lbl.setVisible(not is_zh)
        en_fg = "#FFF" if not is_zh else "#E0E0E0"
        self._en_text.setStyleSheet(f"color: {en_fg}; background: transparent;")
        self._en_icon_lbl.setStyleSheet(f"color: {en_fg}; background: transparent;")
        self._lang_en_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER if not is_zh else '#404040'};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H if not is_zh else '#505050'}; }}
        """)

    def _build_mic_status(self, fn):
        """构建麦克风状态区: 状态圆点 + 标签 + 设备下拉 + 测试按钮 (单行)"""
        row = QHBoxLayout()
        row.setSpacing(8)

        self._mic_dot = QLabel("\u25CF")
        self._mic_dot.setFont(_make_font(fn, 14))
        self._mic_dot.setStyleSheet("color: #666; background: transparent;")
        row.addWidget(self._mic_dot)

        self._mic_lbl = QLabel(t("voice_dialog.mic_status"))
        self._mic_lbl.setFont(_make_font(fn, 13))
        self._mic_lbl.setStyleSheet("color: #AAA; background: transparent;")
        row.addWidget(self._mic_lbl)

        row.addSpacing(4)

        self._mic_combo = QComboBox()
        self._mic_combo.setFixedHeight(32)
        self._mic_combo.setFont(_make_font(fn, 13))
        self._mic_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C_INPUT_BG}; color: #E0E0E0;
                border: 2px solid {C_GRAY}; border-radius: 6px;
                padding: 2px 28px 2px 8px;
            }}
            QComboBox:hover {{ border-color: #666; }}
            QComboBox::drop-down {{
                border: none; width: 28px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox QAbstractItemView {{
                background: #2A2A2A; color: #E0E0E0;
                selection-background-color: {C_CYBER};
                border: 1px solid #444; border-radius: 4px;
            }}
        """)
        row.addWidget(self._mic_combo, 1)

        self._test_btn = QPushButton(t("voice_test.btn"))
        self._test_btn.setFixedSize(100, 32)
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setFont(_make_font(fn, 13))
        self._test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        self._test_btn.clicked.connect(self._on_test_commands)
        row.addWidget(self._test_btn)

        # Populate devices
        self._mic_devices = []
        self._populate_mic_devices()
        return row

    # 「系统默认」的内部标记值 (不会与任何真实设备名冲突)
    _MIC_DEFAULT_TAG = "__system_default__"

    def _populate_mic_devices(self):
        """枚举麦克风设备 — 仅保留 WASAPI 后端 + 首项「系统默认」"""
        self._mic_combo.clear()
        self._mic_devices = []  # list of (sd_index | None, display_name)
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            host_apis = sd.query_hostapis()

            # 找到 WASAPI 的 hostapi index (Windows 推荐 API)
            wasapi_idx = None
            for hi, ha in enumerate(host_apis):
                if 'WASAPI' in ha.get('name', ''):
                    wasapi_idx = hi
                    break

            # ── 第 1 项: 系统默认 ──
            default_label = t("voice_dialog.mic_system_default")
            self._mic_combo.addItem(default_label, self._MIC_DEFAULT_TAG)
            self._mic_devices.append((None, default_label))

            # ── 遍历设备，只取 WASAPI (或全部取 + 去重) ──
            seen = set()
            for i, d in enumerate(devs):
                if d.get('max_input_channels', 0) <= 0:
                    continue
                # 优先只保留 WASAPI 后端的设备
                if wasapi_idx is not None and d.get('hostapi') != wasapi_idx:
                    continue
                raw_name = d.get('name', f'Device {i}')
                # 清洗: 去掉尾部可能的 host api 标注
                clean = raw_name.strip()
                if clean in seen:
                    continue
                seen.add(clean)
                self._mic_devices.append((i, clean))
                self._mic_combo.addItem(clean, i)

            # 如果 WASAPI 没找到任何设备，回退: 取全部后端去重
            if len(self._mic_devices) <= 1 and wasapi_idx is not None:
                seen.clear()
                for i, d in enumerate(devs):
                    if d.get('max_input_channels', 0) <= 0:
                        continue
                    raw_name = d.get('name', f'Device {i}')
                    clean = raw_name.strip()
                    if clean in seen:
                        continue
                    seen.add(clean)
                    self._mic_devices.append((i, clean))
                    self._mic_combo.addItem(clean, i)

            if len(self._mic_devices) > 1:
                # 至少有 1 个真实设备 (除去「系统默认」)
                self._mic_dot.setStyleSheet("color: #10B981; background: transparent;")
                self._mic_lbl.setText(t("voice_dialog.mic_ready"))
                self._test_btn.setEnabled(True)
                # 恢复之前保存的设备
                if self._saved_mic_device and self._saved_mic_device != self._MIC_DEFAULT_TAG:
                    idx = self._mic_combo.findText(self._saved_mic_device)
                    if idx >= 0:
                        self._mic_combo.setCurrentIndex(idx)
                    # else: 设备已拔出，回落到「系统默认」(index 0)
                # 否则保持「系统默认」(index 0)
            elif len(self._mic_devices) == 1:
                # 只有「系统默认」，没有真实设备
                self._mic_dot.setStyleSheet("color: #EF4444; background: transparent;")
                self._mic_lbl.setText(t("voice_dialog.mic_not_found"))
                self._test_btn.setEnabled(False)
            else:
                self._mic_dot.setStyleSheet("color: #EF4444; background: transparent;")
                self._mic_lbl.setText(t("voice_dialog.mic_not_found"))
                self._test_btn.setEnabled(False)
        except ImportError:
            self._mic_dot.setStyleSheet("color: #EF4444; background: transparent;")
            self._mic_lbl.setText(t("voice_dialog.mic_dep_missing"))
            self._test_btn.setEnabled(False)
        except Exception:
            self._mic_dot.setStyleSheet("color: #F59E0B; background: transparent;")
            self._mic_lbl.setText(t("voice_dialog.mic_check_failed"))
            self._test_btn.setEnabled(False)

    def _on_test_commands(self):
        """收集当前指令列表，打开语音指令测试弹窗"""
        commands = []
        for row in self._command_rows:
            data = row.get_data()
            if data['phrase']:
                commands.append(data)
        from views.voice_test_dialog import VoiceTestDialog
        self._test_dlg = VoiceTestDialog(commands, self._language, parent=None)
        self._test_dlg.show()

    def get_selected_mic(self):
        """返回当前选中的麦克风设备名; 「系统默认」返回 None"""
        if not self._mic_devices:
            return None
        data = self._mic_combo.currentData()
        if data == self._MIC_DEFAULT_TAG:
            return None  # 系统默认 → voice_engine 不指定 device
        return self._mic_combo.currentText()

    def _build_key_palette(self, fn):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 8px; border: none;
            }
            QScrollBar::handle:vertical {
                background: #404040; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(0)

        for i, (cat_name, keys) in enumerate(_get_key_categories()):
            if i > 0:
                layout.addSpacing(20)
            cat_lbl = QLabel(f"── {cat_name} ──")
            cat_lbl.setFont(_make_font(fn, 14, bold=True))
            cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
            layout.addWidget(cat_lbl)
            layout.addSpacing(8)
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            flow = _FlowWidget(keys, self._on_key_clicked, fn, container)
            c_lay = QVBoxLayout(container)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.setSpacing(0)
            c_lay.addWidget(flow)
            layout.addWidget(container)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ── 右栏 Tab 面板 (浏览模式，无管理) ──

    def _build_right_tabbed_panel(self, fn):
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(8)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self._tab_keys_btn = QPushButton(t("macro.tab_keys"))
        self._tab_keys_btn.setFixedHeight(34)
        self._tab_keys_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_keys_btn.setFont(_make_font(fn, 14, bold=True))
        self._tab_keys_btn.clicked.connect(lambda: self._switch_tab(0))
        tab_row.addWidget(self._tab_keys_btn)

        self._tab_mouse_btn = QPushButton(t("macro.tab_mouse"))
        self._tab_mouse_btn.setFixedHeight(34)
        self._tab_mouse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_mouse_btn.setFont(_make_font(fn, 14, bold=True))
        self._tab_mouse_btn.clicked.connect(lambda: self._switch_tab(1))
        tab_row.addWidget(self._tab_mouse_btn)

        self._tab_macros_btn = QPushButton(t("macro.tab_macros"))
        self._tab_macros_btn.setFixedHeight(34)
        self._tab_macros_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_macros_btn.setFont(_make_font(fn, 14, bold=True))
        self._tab_macros_btn.clicked.connect(lambda: self._switch_tab(2))
        tab_row.addWidget(self._tab_macros_btn)
        tab_row.addStretch()
        panel_lay.addLayout(tab_row)
        panel_lay.addSpacing(10)

        self._tab_stack = QStackedWidget()
        self._tab_stack.setStyleSheet("background: transparent;")
        self._tab_stack.addWidget(self._build_key_palette(fn))
        self._tab_stack.addWidget(self._build_mouse_palette(fn))
        self._tab_stack.addWidget(self._build_macro_browse(fn))
        panel_lay.addWidget(self._tab_stack, 1)
        self._switch_tab(0)
        return panel

    def _switch_tab(self, idx):
        self._tab_stack.setCurrentIndex(idx)
        sel = f"QPushButton {{ background: transparent; color: #FFF; border: none; border-bottom: 2px solid {C_CYBER_H}; border-radius: 0; padding: 0 14px 4px 14px; }} QPushButton:hover {{ color: #FFF; }}"
        off = f"QPushButton {{ background: transparent; color: #AAA; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 0 14px 4px 14px; }} QPushButton:hover {{ color: #E0E0E0; }}"
        self._tab_keys_btn.setStyleSheet(sel if idx == 0 else off)
        self._tab_mouse_btn.setStyleSheet(sel if idx == 1 else off)
        self._tab_macros_btn.setStyleSheet(sel if idx == 2 else off)

    def _build_mouse_palette(self, fn):
        """构建鼠标操作 Tab: 分类标签 + 5 个鼠标按键 flow"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)

        cat_lbl = QLabel(f"── {t('key_cat.mouse_buttons')} ──")
        cat_lbl.setFont(_make_font(fn, 14, bold=True))
        cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        lay.addWidget(cat_lbl)
        lay.addSpacing(8)

        mouse_keys = _get_mouse_keys()
        mouse_display_names = [label for label, _ in mouse_keys]
        mouse_tag_values = [tag for _, tag in mouse_keys]
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        flow = _FlowWidget(
            mouse_display_names,
            lambda name: self._on_mouse_key_clicked(name),
            fn, container
        )
        c_lay = QVBoxLayout(container)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(0)
        c_lay.addWidget(flow)
        lay.addWidget(container)

        self._mouse_name_to_tag = dict(zip(mouse_display_names, mouse_tag_values))

        lay.addStretch()
        return page

    def _on_mouse_key_clicked(self, display_name):
        tag = self._mouse_name_to_tag.get(display_name, display_name)
        self._on_key_clicked(tag)

    C_MACRO = "#8B5CF6"
    MAX_MACROS = 20

    def _build_macro_browse(self, fn):
        """构建宏 Tab: 横条列表 + 底部「新建」按钮 (完整管理模式)"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # 分类标题 (与常规按键分类标签风格一致)
        cat_lbl = QLabel(f"── {t('macro.macro_list_label')} ──")
        cat_lbl.setFont(_make_font(fn, 14, bold=True))
        cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        cat_lbl.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(cat_lbl)

        # 宏列表 (QListWidget)
        self._macro_list = QListWidget()
        self._macro_list.setStyleSheet(f"""
            QListWidget {{
                background: {C_PM_BG};
                border: none; outline: none;
            }}
            QListWidget::item {{
                background: transparent; padding: 0px;
                border: none; margin-right: 0px;
            }}
            QListWidget::item:selected {{ background: transparent; }}
            QListWidget::item:hover {{ background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #404040; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        self._macro_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._macro_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self._macro_list, 1)

        # 底部「新建」按钮 (紫色, icon + 文字双 label)
        _detect_icon_font()
        new_btn = QPushButton()
        new_btn.setFixedHeight(40)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.C_MACRO}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: #7C3AED; }}
        """)
        nb_lay = QHBoxLayout(new_btn)
        nb_lay.setContentsMargins(0, 0, 0, 0)
        nb_lay.setSpacing(4)
        nb_lay.addStretch()
        if _ICON_FONT:
            nb_icon = QLabel("\uE710")
            nb_icon.setFont(_make_font(_ICON_FONT, 16))
        else:
            nb_icon = QLabel("+")
            nb_icon.setFont(_make_font(fn, 16, bold=True))
        nb_icon.setStyleSheet("color: #FFF; background: transparent;")
        nb_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        nb_lay.addWidget(nb_icon)
        nb_text = QLabel(t("macro.new"))
        nb_text.setFont(_make_font(fn, 16))
        nb_text.setStyleSheet("color: #FFF; background: transparent;")
        nb_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        nb_lay.addWidget(nb_text)
        nb_lay.addStretch()
        new_btn.clicked.connect(self._new_macro)
        lay.addWidget(new_btn)

        # 延迟到下一帧事件循环再填充列表，确保 QListWidget 已完成布局
        QTimer.singleShot(0, self._rebuild_macro_list)
        return page

    def _rebuild_macro_list(self):
        """重建宏列表 (横条风格, 参考 _ProfileRowWidget)"""
        fn = get_font()
        _detect_icon_font()
        self._macro_list.clear()

        ROW_H = 40

        if not self._macros:
            hint_item = QListWidgetItem()
            hint_item.setSizeHint(QSize(0, 60))
            hint_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._macro_list.addItem(hint_item)
            hint = QLabel(t("macro.no_macros_hint"))
            hint.setFont(_make_font(fn, 14))
            hint.setStyleSheet("color: #666; background: transparent;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            self._macro_list.setItemWidget(hint_item, hint)
            return

        for i, macro in enumerate(self._macros):
            name = macro.get('name', f'Macro {i+1}')

            row = QFrame()
            row.setFixedHeight(ROW_H)
            row.setObjectName("macro_row")
            row.setStyleSheet(f"""
                QFrame#macro_row {{
                    background: {C_GRAY}; border-radius: 6px;
                }}
                QFrame#macro_row:hover {{
                    background: {self.C_MACRO};
                }}
            """)
            row.setCursor(Qt.CursorShape.PointingHandCursor)

            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(15, 0, 10, 0)
            row_lay.setSpacing(6)

            name_lbl = QLabel(name)
            name_lbl.setFont(_make_font(fn, 14))
            name_lbl.setStyleSheet("color: white; background: transparent;")
            name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_lay.addWidget(name_lbl, 1)

            btn_size = 30
            edit_btn = QPushButton()
            edit_btn.setFixedSize(btn_size, btn_size)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if _ICON_FONT:
                edit_btn.setText("\uE70F")
                edit_btn.setFont(_make_font(_ICON_FONT, 14))
            else:
                edit_btn.setText("\u270E")
                edit_btn.setFont(_make_font(fn, 14))
            edit_btn.setStyleSheet("""
                QPushButton { color: white; background: transparent; border: none; }
                QPushButton:hover { background: rgba(255,255,255,0.15); border-radius: 6px; }
            """)
            edit_btn.clicked.connect(lambda _, idx=i: self._edit_macro(idx))
            row_lay.addWidget(edit_btn)

            del_btn = QPushButton()
            del_btn.setFixedSize(btn_size, btn_size)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if _ICON_FONT:
                del_btn.setText("\uE74D")
                del_btn.setFont(_make_font(_ICON_FONT, 14))
            else:
                del_btn.setText("\u2715")
                del_btn.setFont(_make_font(fn, 12))
            del_btn.setStyleSheet("""
                QPushButton { color: white; background: transparent; border: none; }
                QPushButton:hover { background: rgba(255,255,255,0.15); border-radius: 6px; }
            """)
            del_btn.clicked.connect(lambda _, idx=i: self._delete_macro(idx))
            row_lay.addWidget(del_btn)

            row.mousePressEvent = lambda e, n=name: self._insert_macro_tag(n)

            item = QListWidgetItem()
            item.setSizeHint(QSize(0, ROW_H + 10))
            self._macro_list.addItem(item)
            self._macro_list.setItemWidget(item, row)

    def _insert_macro_tag(self, macro_name):
        if self._focus_widget and isinstance(self._focus_widget, TagInput):
            self._focus_widget.add_tag(f"macro:{macro_name}")

    def _new_macro(self):
        from views.macro_editor_dialog import MacroEditorDialog
        names = [m.get('name', '') for m in self._macros]
        dlg = MacroEditorDialog(existing_names=names, parent=self)
        dlg.macro_saved.connect(lambda data: self._on_macro_editor_saved(data, -1))
        dlg.exec()

    def _edit_macro(self, idx):
        from views.macro_editor_dialog import MacroEditorDialog
        data = copy.deepcopy(self._macros[idx])
        names = [m.get('name', '') for m in self._macros]
        dlg = MacroEditorDialog(macro_data=data, existing_names=names, parent=self)
        dlg.macro_saved.connect(lambda d: self._on_macro_editor_saved(d, idx))
        dlg.exec()

    def _delete_macro(self, idx):
        from views.profile_manager_dialog import _StyledConfirmDialog
        name = self._macros[idx].get('name', '')
        msg = t("macro.confirm_delete").replace("{name}", name)
        dlg = _StyledConfirmDialog(
            t("macro.confirm_delete_title"), msg,
            parent=self, accent_color="#8B5CF6")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._macros.pop(idx)
            self._rebuild_macro_list()
            self.macros_changed.emit(self._macros)

    def _on_macro_editor_saved(self, data, idx):
        if 0 <= idx < len(self._macros):
            self._macros[idx] = data
        else:
            self._macros.append(data)
        self._rebuild_macro_list()
        self.macros_changed.emit(self._macros)

    def _on_key_clicked(self, key_name):
        if self._focus_widget and isinstance(self._focus_widget, TagInput):
            self._focus_widget.add_tag(key_name)

    # ── Command list management ──

    def _load_commands(self):
        for cmd in self._commands:
            self._add_command_row(
                cmd.get('phrase', ''),
                cmd.get('keys', ''),
                cmd.get('action', 'click'))

    def _add_command_row(self, phrase="", keys="", action="click"):
        fn = get_font()
        row = _CommandRow(phrase, keys, action, fn)
        row.delete_clicked.connect(self._on_delete_command)
        row.focus_changed.connect(self._on_focus_changed)
        self._command_rows.append(row)
        # Insert before the stretch
        idx = self._cmd_layout.count() - 1
        self._cmd_layout.insertWidget(idx, row)

    def _on_add_command(self):
        self._add_command_row()

    def _on_delete_command(self, row):
        if row in self._command_rows:
            self._command_rows.remove(row)
            self._cmd_layout.removeWidget(row)
            row.deleteLater()

    def _on_focus_changed(self, widget):
        self._focus_widget = widget

    # ── Save ──

    def _on_save(self):
        self._result_commands = []
        for row in self._command_rows:
            data = row.get_data()
            if data['phrase']:  # skip empty phrases
                self._result_commands.append(data)
        self._result_language = self._language
        self.settings_saved.emit()
        self.accept()

    def get_result(self):
        return {
            'voice_commands': getattr(self, '_result_commands', []),
            'voice_language': getattr(self, '_result_language', self._language),
            'voice_enabled': len(getattr(self, '_result_commands', [])) > 0,
            'voice_mic_device': self.get_selected_mic(),
            'voice_auto_start': self._auto_start_cb.isChecked(),
        }

    # ── Positioning ──

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # ── Drag ──

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
