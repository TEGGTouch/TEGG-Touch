"""
TEGG Touch 蛋挞 (PyQt6) - hotkey_settings_dialog.py
快捷键设置弹窗 — 双栏布局匹配原版: 左侧表单 + 右侧键位面板。

原版布局 (~900×880):
  左栏 380px: 热键字段(带色点+描述) + 延迟滑块 + 语言切换 + Reset/Save
  右栏 500px: 滚动键位面板 (分类, flow 布局)
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QSlider, QPushButton, QWidget,
    QScrollArea, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush

from core.i18n import t, get_font, load_locale, get_lang
from core.constants import DEFAULT_HOTKEYS, get_hotkey_labels
from core.config_manager import load_hotkeys, save_hotkeys

# ── 颜色 ──
C_PM_BG = "#2D2D2D"
C_GRAY = "#3A3A3A"
C_GRAY_H = "#505050"
C_INPUT_BG = "#3A3A3A"
C_CLOSE = "#6E1E1E"
C_CLOSE_H = "#8B2020"
C_CYBER = "#0C4A6E"
C_CYBER_H = "#0284C7"
C_TAG_BG = "#404040"
C_TAG_HOVER = "#555555"
C_TAG_TEXT = "#E0E0E0"
C_CAT_LABEL = "#888888"

# 各热键字段的强调色
HOTKEY_COLORS = {
    'voice':          '#10B981',
    'auto_center':    '#176F2C',
    'toggle_buttons': '#6B7280',
    'soft_keyboard':  '#0284C7',
    'pt_on':          '#6B7280',
    'pt_off':         '#1976D2',
    'pt_block':       '#D97706',
    'stop':           '#C42B1C',
}

# 键位面板分类 (与 button_editor 一致的部分 + 设置专用键)
SETTINGS_KEY_CATEGORIES = [
    (t("key_cat.modifiers"), ["ctrl", "shift", "alt", "windows"]),
    (t("key_cat.fkeys"), [f"f{i}" for i in range(1, 13)]),
    (t("key_cat.letters"), [chr(c) for c in range(ord('a'), ord('z') + 1)]),
    (t("key_cat.numbers"), [str(i) for i in range(10)]),
    (t("key_cat.punctuation"), [",", ".", "/", ";", "'", "[", "]", "\\", "-", "=", "`"]),
    (t("key_cat.other"), ["home", "end", "pageup", "pagedown", "insert", "delete",
                           "print screen", "scroll lock", "pause",
                           "up", "down", "left", "right"]),
    (t("key_cat.numpad"), [f"num {i}" for i in range(10)] + ["num lock",
                            "num *", "num +", "num -", "num /", "num .", "num enter"]),
]


def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


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


# ── 自适应宽度语言按钮（参照 edit_toolbar._IconTextBtn 的 sizeHint）──
class _LangBtn(QPushButton):
    def sizeHint(self):
        lay = self.layout()
        if lay:
            m = self.contentsMargins()
            s = lay.sizeHint()
            return QSize(
                s.width() + m.left() + m.right(),
                max(s.height() + m.top() + m.bottom(), self.minimumHeight()))
        return super().sizeHint()


# ── 色点 ──
class _ColorDot(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(20, 42)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._color))
        p.drawEllipse(6, 17, 8, 8)


# ── Tag 输入控件 ──
class TagInput(QWidget):
    """Tag 输入控件: 显示彩色标签，点击面板添加，BackSpace 删除。"""

    focusChanged = pyqtSignal(object)

    def __init__(self, initial_value="", accent_color="#0284C7", parent=None):
        super().__init__(parent)
        self.tags: list[str] = []
        self._accent = accent_color
        self._focused = False

        self.setFixedHeight(42)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)

        # 解析初始值
        if initial_value:
            for part in initial_value.split("+"):
                part = part.strip()
                if part:
                    self.tags.append(part)

        self._build_tags()

    def _build_tags(self):
        lay = self.layout()
        if lay is None:
            lay = QHBoxLayout()
            lay.setContentsMargins(5, 5, 5, 5)
            lay.setSpacing(4)
            self.setLayout(lay)

        # 清理旧项
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        fn = get_font()
        for tag_name in self.tags:
            lbl = QLabel(tag_name)
            lbl.setFont(_make_font(fn, 12, bold=True))
            lbl.setStyleSheet(f"""
                QLabel {{
                    background: {self._accent}; color: #FFF;
                    padding: 2px 6px; border-radius: 4px;
                }}
            """)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(lbl)

        lay.addStretch()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        border_color = QColor(self._accent) if self._focused else QColor(C_GRAY)
        p.setPen(QPen(border_color, 2))
        p.setBrush(QBrush(QColor(C_INPUT_BG)))
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 6, 6)

    def focusInEvent(self, event):
        self._focused = True
        self.update()
        self.focusChanged.emit(self)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._focused = False
        self.update()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Backspace and self.tags:
            self.tags.pop()
            self._build_tags()
        event.accept()

    def add_tag(self, key_name: str):
        self.tags.append(key_name)
        self._build_tags()

    def get_value(self) -> str:
        return "+".join(self.tags)


# ── Flow 键位按钮容器 ──
class _FlowKeys(QWidget):
    TAG_H = 40
    TAG_GAP_X = 8
    TAG_GAP_Y = 8
    TAG_PAD_X = 12
    TAG_MIN_W = 40

    def __init__(self, keys, on_click, fn, parent=None):
        super().__init__(parent)
        self._buttons = []
        self.setStyleSheet("background: transparent;")

        for key in keys:
            btn = QPushButton(key, self)
            btn.setFont(_make_font(fn, 14))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C_TAG_BG}; color: {C_TAG_TEXT};
                    border: none; border-radius: 6px;
                    padding: 0 {self.TAG_PAD_X}px;
                }}
                QPushButton:hover {{ background: {C_TAG_HOVER}; }}
            """)
            btn.setFixedHeight(self.TAG_H)
            fm = btn.fontMetrics()
            tw = fm.horizontalAdvance(key)
            btn.setFixedWidth(max(self.TAG_MIN_W, tw + self.TAG_PAD_X * 2))
            btn.clicked.connect(lambda checked, k=key: on_click(k))
            self._buttons.append(btn)

        if parent:
            parent.resizeEvent = self._do_layout_event

    def _do_layout_event(self, event):
        self._do_layout()

    def _do_layout(self):
        if not self._buttons:
            return
        avail_w = self.parent().width() - 20 if self.parent() else 460
        x, y = 0, 0
        row_h = self.TAG_H + self.TAG_GAP_Y
        for btn in self._buttons:
            bw = btn.width()
            if x + bw > avail_w and x > 0:
                x = 0
                y += row_h
            btn.move(x, y)
            btn.show()
            x += bw + self.TAG_GAP_X
        self.setFixedHeight(y + self.TAG_H + 4)

    def resizeEvent(self, event):
        self._do_layout()
        super().resizeEvent(event)


class HotkeySettingsDialog(QDialog):
    """快捷键设置弹窗 — 双栏布局"""

    settings_saved = pyqtSignal()
    defaults_reset = pyqtSignal()   # 重置默认时发出，通知主窗口重置透明度和工具栏位置
    language_changed = pyqtSignal(str)

    LEFT_W = 380
    RIGHT_W = 500
    PADDING = 20
    WIN_W = LEFT_W + RIGHT_W + PADDING * 2 + 20
    WIN_H = 980

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        self._hotkeys = load_hotkeys()
        self._focus_widget = None
        self._init_ui()
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self):
        fn = get_font()

        # ── 容器 ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("hs_container")
        container.setStyleSheet(f"""
            QFrame#hs_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # ── 标题栏 ──
        title_row = QHBoxLayout()

        _detect_icon_font()
        gear_icon = QLabel("\uE713" if _ICON_FONT else "\u2699")
        if _ICON_FONT:
            gear_icon.setFont(_make_font(_ICON_FONT, 20))
        else:
            gear_icon.setFont(_make_font(fn, 20))
        gear_icon.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(gear_icon)
        title_row.addSpacing(6)

        title_lbl = QLabel(t("hotkey.title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        close_icon = "\uE711" if _ICON_FONT else "\u2715"
        close_btn = QPushButton(close_icon)
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

        # 提示
        tip = QLabel(t("hotkey.tip"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)

        root.addSpacing(20)

        # ── 双栏 ──
        columns = QHBoxLayout()
        columns.setSpacing(0)

        # ════ 左栏 ════
        left = QVBoxLayout()
        left.setSpacing(0)
        left.setContentsMargins(0, 0, 0, 0)

        labels = get_hotkey_labels()
        descriptions = {
            'voice': t("hotkey.desc_voice"),
            'auto_center': t("hotkey.desc_auto_center"),
            'toggle_buttons': t("hotkey.desc_toggle_buttons"),
            'soft_keyboard': t("hotkey.desc_soft_keyboard"),
            'pt_on': t("hotkey.desc_pt_on"),
            'pt_off': t("hotkey.desc_pt_off"),
            'pt_block': t("hotkey.desc_pt_block"),
            'stop': t("hotkey.desc_stop"),
        }

        self._key_edits = {}

        hotkey_fields = [
            'voice', 'auto_center', 'toggle_buttons', 'soft_keyboard',
            'pt_on', 'pt_off', 'pt_block', 'stop',
        ]

        # 语音识别字段
        left.addLayout(self._build_hotkey_row(
            fn, 'voice', labels, descriptions))
        left.addSpacing(10)

        # 自动回中字段 + 延迟滑块
        left.addLayout(self._build_hotkey_row(
            fn, 'auto_center', labels, descriptions))
        left.addSpacing(4)
        left.addLayout(self._build_delay_slider(
            fn, t("hotkey.auto_center_delay"), HOTKEY_COLORS['auto_center']))
        left.addSpacing(14)

        # 其余热键字段 (skip voice + auto_center already added above)
        for field in hotkey_fields[2:]:
            left.addLayout(self._build_hotkey_row(fn, field, labels, descriptions))
            left.addSpacing(10)

        left.addSpacing(20)

        # ── 分隔线 ──
        lang_divider = QFrame()
        lang_divider.setFixedHeight(1)
        lang_divider.setStyleSheet("background: #444;")
        left.addWidget(lang_divider)

        left.addSpacing(20)

        # ── 语言切换 ──
        lang_row = QHBoxLayout()

        _detect_icon_font()
        lang_icon = QLabel("\uE774" if _ICON_FONT else "\U0001F310")
        if _ICON_FONT:
            lang_icon.setFont(_make_font(_ICON_FONT, 18))
        else:
            lang_icon.setFont(_make_font(fn, 18))
        lang_icon.setStyleSheet("color: #CCC; background: transparent;")
        lang_row.addWidget(lang_icon)
        lang_row.addSpacing(6)

        lang_lbl = QLabel("Language / 语言:")
        lang_lbl.setFont(_make_font(fn, 16))
        lang_lbl.setStyleSheet("color: #CCC; background: transparent;")
        lang_row.addWidget(lang_lbl)
        lang_row.addSpacing(12)

        current_lang = get_lang()

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
        self._zh_text_lbl = QLabel("中文")
        self._zh_text_lbl.setFont(_make_font(fn, 16, bold=True))
        self._zh_text_lbl.setStyleSheet("color: #FFF; background: transparent;")
        self._zh_text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        zh_lay.addWidget(self._zh_text_lbl)
        lang_row.addWidget(self._lang_zh_btn)

        lang_row.addSpacing(10)

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
        self._en_text_lbl = QLabel("English")
        self._en_text_lbl.setFont(_make_font(fn, 16, bold=True))
        self._en_text_lbl.setStyleSheet("color: #FFF; background: transparent;")
        self._en_text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        en_lay.addWidget(self._en_text_lbl)
        lang_row.addWidget(self._lang_en_btn)

        self._selected_lang = current_lang
        self._update_lang_buttons()

        lang_row.addStretch()
        left.addLayout(lang_row)

        # ── 重启提示（中英双语，硬编码，不走 i18n）──
        left.addSpacing(8)
        restart_hint = QLabel(
            "切换语言需要重启应用才能生效\n"
            "Language change requires restart to take effect")
        restart_hint.setFont(_make_font(fn, 13))
        restart_hint.setStyleSheet("color: #888; background: transparent;")
        restart_hint.setWordWrap(True)
        restart_hint.setContentsMargins(26, 0, 0, 0)
        left.addWidget(restart_hint)

        left.addStretch()

        # ── 底部按钮: Reset | Save ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        reset_btn = QPushButton(t("hotkey.reset"))
        reset_btn.setFixedHeight(40)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setFont(_make_font(fn, 18))
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)

        save_btn = QPushButton(t("hotkey.save"))
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
        btn_row.addWidget(save_btn)

        left.addLayout(btn_row)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(self.LEFT_W)
        left_widget.setStyleSheet("background: transparent;")
        columns.addWidget(left_widget)
        columns.addSpacing(20)

        # ── 分隔线 ──
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background: #444;")
        columns.addWidget(divider)

        columns.addSpacing(10)

        # ════ 右栏: 键位面板 ════
        right = self._build_key_palette(fn)
        columns.addWidget(right, 1)

        root.addLayout(columns, 1)

    # ── 热键行 ──

    def _build_hotkey_row(self, fn, field, labels, descriptions):
        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        # Row 1: dot + label + input
        r1 = QHBoxLayout()
        r1.setSpacing(0)

        accent = HOTKEY_COLORS.get(field, '#888')
        dot = _ColorDot(accent)
        r1.addWidget(dot)

        lbl = QLabel(labels.get(field, field))
        lbl.setFont(_make_font(fn, 16))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setFixedWidth(110)
        r1.addWidget(lbl)

        r1.addSpacing(10)

        edit = TagInput(
            initial_value=self._hotkeys.get(field, DEFAULT_HOTKEYS.get(field, '')),
            accent_color=accent)
        edit.focusChanged.connect(self._on_focus_changed)
        self._key_edits[field] = edit
        r1.addWidget(edit, 1)

        col.addLayout(r1)

        # Row 2: description
        desc_text = descriptions.get(field, '')
        if desc_text:
            col.addSpacing(5)
            desc = QLabel(desc_text)
            desc.setFont(_make_font(fn, 13))
            desc.setStyleSheet("color: #666; background: transparent;")
            desc.setContentsMargins(20, 0, 0, 0)
            col.addWidget(desc)

        return col

    def _build_delay_slider(self, fn, label_text, accent):
        col = QVBoxLayout()
        col.setSpacing(4)
        col.setContentsMargins(0, 0, 0, 0)

        r1 = QHBoxLayout()
        r1.setSpacing(0)

        dot = _ColorDot(accent)
        r1.addWidget(dot)

        lbl = QLabel(label_text)
        lbl.setFont(_make_font(fn, 16))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        r1.addWidget(lbl)

        r1.addStretch()

        self._ac_delay_entry = QLineEdit(
            str(self._hotkeys.get('auto_center_delay', 1500)))
        self._ac_delay_entry.setFixedSize(80, 28)
        self._ac_delay_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ac_delay_entry.setFont(_make_font(fn, 13))
        self._ac_delay_entry.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: {accent};
                border: 1px solid #555; border-radius: 4px;
            }}
            QLineEdit:focus {{ border-color: {accent}; }}
        """)
        r1.addWidget(self._ac_delay_entry)

        r1.addSpacing(10)

        ms_lbl = QLabel("ms")
        ms_lbl.setFont(_make_font(fn, 16))
        ms_lbl.setStyleSheet("color: #888; background: transparent;")
        ms_lbl.setFixedWidth(26)
        r1.addWidget(ms_lbl)

        col.addLayout(r1)

        self._ac_delay_slider = QSlider(Qt.Orientation.Horizontal)
        self._ac_delay_slider.setRange(200, 5000)
        self._ac_delay_slider.setValue(self._hotkeys.get('auto_center_delay', 1500))
        self._ac_delay_slider.setSingleStep(100)
        self._ac_delay_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: #404040; height: 8px; border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent}; border-radius: 4px;
            }}
            QSlider::add-page:horizontal {{
                background: #404040; border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #DDD; border: none;
                width: 16px; height: 16px; margin: -4px 0; border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {accent};
            }}
        """)

        def _s2e(v):
            self._ac_delay_entry.setText(str(v))

        def _e2s():
            try:
                v = max(200, min(5000, int(self._ac_delay_entry.text())))
                self._ac_delay_slider.setValue(v)
            except ValueError:
                pass

        self._ac_delay_slider.valueChanged.connect(_s2e)
        self._ac_delay_entry.editingFinished.connect(_e2s)

        col.addWidget(self._ac_delay_slider)
        return col

    # ── 键位面板 ──

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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(0)

        for i, (cat_name, keys) in enumerate(SETTINGS_KEY_CATEGORIES):
            if i > 0:
                layout.addSpacing(20)
            cat_lbl = QLabel(f"── {cat_name} ──")
            cat_lbl.setFont(_make_font(fn, 14, bold=True))
            cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
            layout.addWidget(cat_lbl)
            layout.addSpacing(8)

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            flow = _FlowKeys(keys, self._on_key_clicked, fn, container)
            c_lay = QVBoxLayout(container)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.setSpacing(0)
            c_lay.addWidget(flow)
            layout.addWidget(container)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _on_key_clicked(self, key_name):
        w = self._focus_widget
        if w and isinstance(w, TagInput):
            w.add_tag(key_name)

    def _on_focus_changed(self, widget):
        self._focus_widget = widget

    # ── 语言切换 ──

    def _set_lang(self, lang):
        self._selected_lang = lang
        self._update_lang_buttons()

    def _update_lang_buttons(self):
        is_zh = self._selected_lang.startswith("zh")

        # 中文按钮: 选中时显示勾 icon
        self._zh_icon_lbl.setVisible(is_zh)
        zh_fg = "#FFF" if is_zh else "#E0E0E0"
        self._zh_text_lbl.setStyleSheet(f"color: {zh_fg}; background: transparent;")
        self._zh_icon_lbl.setStyleSheet(f"color: {zh_fg}; background: transparent;")
        self._lang_zh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER if is_zh else "#404040"};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {C_CYBER_H if is_zh else "#505050"};
            }}
        """)

        # English 按钮: 选中时显示勾 icon
        self._en_icon_lbl.setVisible(not is_zh)
        en_fg = "#FFF" if not is_zh else "#E0E0E0"
        self._en_text_lbl.setStyleSheet(f"color: {en_fg}; background: transparent;")
        self._en_icon_lbl.setStyleSheet(f"color: {en_fg}; background: transparent;")
        self._lang_en_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER if not is_zh else "#404040"};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {C_CYBER_H if not is_zh else "#505050"};
            }}
        """)

    # ── 保存/重置 ──

    def _on_save(self):
        data = {}
        for field, edit in self._key_edits.items():
            data[field] = edit.get_value()
        data['auto_center_delay'] = self._ac_delay_slider.value()
        data['language'] = self._selected_lang

        save_hotkeys(data)

        if self._selected_lang != get_lang():
            load_locale(self._selected_lang)
            self.language_changed.emit(self._selected_lang)

        self.settings_saved.emit()
        self.accept()

    def _on_reset(self):
        for field, default in DEFAULT_HOTKEYS.items():
            if field in self._key_edits:
                widget = self._key_edits[field]
                widget.tags = [p.strip() for p in str(default).split("+") if p.strip()]
                widget._build_tags()
        self._ac_delay_slider.setValue(DEFAULT_HOTKEYS.get('auto_center_delay', 1500))
        # 通知主窗口重置透明度和运行工具栏位置
        self.defaults_reset.emit()

    # ── 定位 ──

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # ── 拖拽 ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
