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
    QScrollArea, QFrame, QApplication, QStackedWidget,
    QComboBox, QColorDialog,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPixmap

import os
import webbrowser

from core.i18n import t, get_font, load_locale, get_lang
from core.constants import (
    DEFAULT_HOTKEYS, get_hotkey_labels, APP_VERSION, get_app_title, APP_DIR,
    DEFAULT_CURSOR_STYLES, CURSOR_SCALE_OPTIONS, CURSOR_BASE_SIZE,
)
from core.config_manager import load_hotkeys, save_hotkeys
from scene.virtual_cursor_item import render_cursor_pixmap, clear_cursor_render_cache

_ABOUT_LAST_UPDATE = "2026.06.07"

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
    'collapse':       '#9333EA',
    'voice':          '#10B981',
    'auto_center':    '#176F2C',
    'toggle_buttons': '#6B7280',
    'soft_keyboard':  '#0284C7',
    'pt_on':          '#6B7280',
    'pt_off':         '#1976D2',
    'pt_block':       '#D97706',
    'stop':           '#C42B1C',
}

# 键位面板分类 — 惰性初始化，避免模块加载时 t() 未就绪
_SETTINGS_KEY_CATEGORIES_CACHE = None

def _get_settings_key_categories():
    global _SETTINGS_KEY_CATEGORIES_CACHE
    if _SETTINGS_KEY_CATEGORIES_CACHE is None:
        _SETTINGS_KEY_CATEGORIES_CACHE = [
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
    return _SETTINGS_KEY_CATEGORIES_CACHE


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

    SIDEBAR_W = 130
    CONTENT_W = 400                                # 中间内容区 (快捷键/语言页)
    LEFT_W = SIDEBAR_W + 10 + 1 + 10 + CONTENT_W   # = 551 (sidebar+spacing+divider+spacing+content)
    PADDING = 20
    WIN_W = 1200
    WIN_H = 960
    # 右侧 wrapper = 剩余宽度 (含 divider + spacing + palette)
    RIGHT_PANEL_W = WIN_W - LEFT_W - 20 - PADDING * 2   # = 589
    RIGHT_W = RIGHT_PANEL_W - 1 - 10                    # = 578 (palette 实际宽度)
    # 关于页撑满: left_wrapper 占满 columns 内部 (sidebar 仍贴左, content 撑剩余)
    WIDE_LEFT_W = WIN_W - PADDING * 2                                # = 1160
    WIDE_CONTENT_W = WIDE_LEFT_W - SIDEBAR_W - 10 - 1 - 10           # = 1009

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

        # title 行与下方 columns 之间的间距 (tip 已挪到右栏顶部)
        root.addSpacing(12)

        # ── 左 wrapper(固定) + 右 wrapper(可隐藏) + addStretch ──
        # 左 wrapper 固定宽度, 保证 sidebar 永远在最左; 右 wrapper 在语言页时整体隐藏
        columns = QHBoxLayout()
        columns.setSpacing(0)

        # ════ 左侧 wrapper: sidebar | 分隔线 | stack ════
        # 关于页时会被 _select_page 拉宽到 WIDE_LEFT_W
        self._left_wrapper = QWidget()
        self._left_wrapper.setFixedWidth(self.LEFT_W)
        ll = QHBoxLayout(self._left_wrapper)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        sidebar = self._build_sidebar(fn)
        ll.addWidget(sidebar)
        ll.addSpacing(10)

        sb_divider = QFrame()
        sb_divider.setFixedWidth(1)
        sb_divider.setStyleSheet("background: #444;")
        ll.addWidget(sb_divider)
        ll.addSpacing(10)

        # 中间内容 (Stacked)
        labels = get_hotkey_labels()
        descriptions = {
            'collapse': t("hotkey.desc_collapse"),
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

        self._stack = QStackedWidget()
        self._stack.setFixedWidth(self.CONTENT_W)
        self._stack.setStyleSheet("background: transparent;")

        # 页 0: 快捷键设置
        self._hotkey_page = self._build_hotkey_page(fn, labels, descriptions)
        self._stack.addWidget(self._hotkey_page)

        # 页 1: 光标配色
        self._cursor_page = self._build_cursor_page(fn)
        self._stack.addWidget(self._cursor_page)

        # 页 2: 方向盘样式
        self._wheel_page = self._build_wheel_page(fn)
        self._stack.addWidget(self._wheel_page)

        # 页 3: 语言设置
        self._language_page = self._build_language_page(fn)
        self._stack.addWidget(self._language_page)

        # 页 4: 日志 (诊断报告)
        self._log_page = self._build_log_page(fn)
        self._stack.addWidget(self._log_page)

        # 页 5: 关于蛋挞
        self._about_page = self._build_about_page(fn)
        self._stack.addWidget(self._about_page)

        ll.addWidget(self._stack)

        columns.addWidget(self._left_wrapper)
        columns.addSpacing(20)

        # ════ 右侧 wrapper: 分隔线 | (tip + 细线 + 键位面板) ════
        # 语言/关于页时整体隐藏 → 两列布局
        self._right_wrapper = QWidget()
        self._right_wrapper.setFixedWidth(self.RIGHT_PANEL_W)
        rl = QHBoxLayout(self._right_wrapper)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background: #444;")
        rl.addWidget(divider)
        rl.addSpacing(10)

        # 右栏内部: tip + 细线 + 键位面板 (常驻顶部, 不随键位面板滚动)
        right_inner = QVBoxLayout()
        right_inner.setContentsMargins(0, 0, 0, 0)
        right_inner.setSpacing(0)

        tip = QLabel(t("hotkey.tip"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        tip.setContentsMargins(10, 0, 10, 0)
        right_inner.addWidget(tip)
        right_inner.addSpacing(8)

        tip_sep = QFrame()
        tip_sep.setFixedHeight(1)
        tip_sep.setStyleSheet("background: #444;")
        right_inner.addWidget(tip_sep)
        right_inner.addSpacing(8)

        self._right_palette = self._build_key_palette(fn)
        right_inner.addWidget(self._right_palette, 1)

        rl.addLayout(right_inner, 1)

        columns.addWidget(self._right_wrapper)
        columns.addStretch()   # 关键: right_wrapper 隐藏时余量在末尾, sidebar 不偏移

        root.addLayout(columns, 1)

        # 默认显示快捷键页
        self._select_page(0)

    # ── 侧边菜单 ──

    def _build_sidebar(self, fn):
        sb = QWidget()
        sb.setFixedWidth(self.SIDEBAR_W)
        sb.setStyleSheet("background: transparent;")
        v = QVBoxLayout(sb)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        self._sidebar_btns = []
        items = [
            (t("hotkey.menu_hotkeys"), 0),
            (t("hotkey.menu_cursor"), 1),
            ("方向盘配色", 2),
            (t("hotkey.menu_language"), 3),
            (t("hotkey.menu_log"), 4),
            (t("hotkey.menu_about"), 5),
        ]
        for label_text, idx in items:
            b = QPushButton(label_text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(40)
            b.setFont(_make_font(fn, 15, bold=True))
            b.clicked.connect(lambda _, i=idx: self._select_page(i))
            v.addWidget(b)
            self._sidebar_btns.append(b)

        v.addStretch()
        return sb

    def _select_page(self, idx):
        self._stack.setCurrentIndex(idx)
        # 高亮选中项
        for i, b in enumerate(self._sidebar_btns):
            selected = (i == idx)
            bg = C_CYBER if selected else "transparent"
            bg_h = C_CYBER_H if selected else C_GRAY_H
            fg = "#FFF" if selected else "#CCC"
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: {fg};
                    border: none; border-radius: 6px;
                    text-align: left; padding: 0 12px;
                }}
                QPushButton:hover {{ background: {bg_h}; color: #FFF; }}
            """)
        # 仅快捷键页(0)显示右侧键位面板; 其余页隐藏 right_wrapper → 两列
        if hasattr(self, '_right_wrapper'):
            self._right_wrapper.setVisible(idx == 0)
        # 光标(1) / 方向盘(2) / 日志(4) / 关于(5) 页拉宽 left_wrapper 和 stack
        if hasattr(self, '_left_wrapper'):
            if idx in (1, 2, 4, 5):
                self._stack.setFixedWidth(self.WIDE_CONTENT_W)
                self._left_wrapper.setFixedWidth(self.WIDE_LEFT_W)
            else:
                self._stack.setFixedWidth(self.CONTENT_W)
                self._left_wrapper.setFixedWidth(self.LEFT_W)

    # ── 快捷键页 ──

    def _build_hotkey_page(self, fn, labels, descriptions):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        hotkey_fields = [
            'collapse', 'voice', 'auto_center', 'toggle_buttons', 'soft_keyboard',
            'pt_on', 'pt_off', 'pt_block', 'stop',
        ]

        v.addLayout(self._build_hotkey_row(fn, 'collapse', labels, descriptions))
        v.addSpacing(10)
        v.addLayout(self._build_hotkey_row(fn, 'voice', labels, descriptions))
        v.addSpacing(10)
        v.addLayout(self._build_hotkey_row(fn, 'auto_center', labels, descriptions))
        v.addSpacing(4)
        v.addLayout(self._build_delay_slider(
            fn, t("hotkey.auto_center_delay"), HOTKEY_COLORS['auto_center']))
        v.addSpacing(14)
        for field in hotkey_fields[3:]:
            v.addLayout(self._build_hotkey_row(fn, field, labels, descriptions))
            v.addSpacing(10)

        v.addStretch()

        # 底部按钮: Reset | Save
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

        v.addLayout(btn_row)
        return page

    # ── 光标配色页 ──

    # 当前编辑中的 styles (保存按钮才写盘)
    def _ensure_cursor_buf(self):
        if not hasattr(self, '_cursor_buf'):
            existing = (load_hotkeys() or {}).get('cursor_styles') or {}
            # 默认值兜底
            self._cursor_buf = {}
            for ct in ('cursor', 'cursor_off', 'cursor_block'):
                d = dict(DEFAULT_CURSOR_STYLES[ct])
                d.update(existing.get(ct, {}))
                self._cursor_buf[ct] = d

    def _build_cursor_page(self, fn):
        self._ensure_cursor_buf()
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        tip = QLabel(t("hotkey.cursor_page_tip"))
        tip.setFont(_make_font(fn, 13))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        v.addWidget(tip)
        v.addSpacing(20)

        # 三栏并列
        cols = QHBoxLayout()
        cols.setSpacing(24)

        self._cursor_widgets = {}   # ct → {'preview': QLabel, 'fill_btn': ..., 'stroke_btn': ..., 'scale_combo': ...}

        items = [
            ('cursor',       t("hotkey.cursor_default")),
            ('cursor_off',   t("hotkey.cursor_off_label")),
            ('cursor_block', t("hotkey.cursor_block_label")),
        ]
        for ct, label_text in items:
            cols.addWidget(self._build_cursor_column(fn, ct, label_text), 1)

        v.addLayout(cols)
        v.addStretch()

        # 底部: 重置全部 + 保存
        bottom = QHBoxLayout()
        bottom.addStretch()
        reset_btn = QPushButton(t("hotkey.cursor_reset_all"))
        reset_btn.setFixedHeight(40)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setFont(_make_font(fn, 14, bold=True))
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #FFF;
                border: none; border-radius: 6px; padding: 0 18px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        reset_btn.clicked.connect(self._on_cursor_reset_all)
        bottom.addWidget(reset_btn)
        bottom.addSpacing(10)
        save_btn = QPushButton(t("hotkey.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 14, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        bottom.addWidget(save_btn)
        v.addLayout(bottom)

        return page

    def _build_cursor_column(self, fn, ct: str, label_text: str):
        col = QFrame()
        col.setStyleSheet(
            "QFrame { background: #232323; border: 1px solid #3A3A3A; border-radius: 8px; }")
        cl = QVBoxLayout(col)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(12)

        # 标签
        title = QLabel(label_text)
        title.setFont(_make_font(fn, 15, bold=True))
        title.setStyleSheet("color: #FFF; background: transparent; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        # 预览 (160×160 容器, 居中显示当前 scale 下的实际尺寸)
        preview = QLabel()
        preview.setFixedSize(160, 160)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet(
            "background: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 6px;")
        cl.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)

        # 底色行
        fill_row = self._build_color_row(fn, ct, 'fill', t("hotkey.cursor_fill"))
        cl.addLayout(fill_row)

        # 描边行
        stroke_row = self._build_color_row(fn, ct, 'stroke', t("hotkey.cursor_stroke"))
        cl.addLayout(stroke_row)

        # 大小行: 标签 + 当前值 + 滑块 (参考延迟滑块样式)
        scale_top = QHBoxLayout()
        scale_lbl = QLabel(t("hotkey.cursor_scale"))
        scale_lbl.setFont(_make_font(fn, 14))
        scale_lbl.setStyleSheet("color: #CCC; background: transparent; border: none;")
        scale_top.addWidget(scale_lbl)
        scale_top.addStretch()
        cur_scale = float(self._cursor_buf[ct].get('scale', 1.0))
        scale_value_lbl = QLabel(f"{int(round(cur_scale * 100))}%")
        scale_value_lbl.setFont(_make_font(fn, 13, bold=True))
        scale_value_lbl.setStyleSheet(f"color: {C_CYBER_H}; background: transparent; border: none;")
        scale_value_lbl.setFixedWidth(50)
        scale_value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        scale_top.addWidget(scale_value_lbl)
        cl.addLayout(scale_top)

        scale_slider = QSlider(Qt.Orientation.Horizontal)
        scale_slider.setRange(100, 400)          # 100% - 400%
        scale_slider.setSingleStep(10)
        scale_slider.setPageStep(50)
        scale_slider.setValue(int(round(cur_scale * 100)))
        scale_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: #404040; height: 8px; border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {C_CYBER_H}; border-radius: 4px;
            }}
            QSlider::add-page:horizontal {{
                background: #404040; border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #DDD; border: none;
                width: 16px; height: 16px; margin: -4px 0; border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {C_CYBER_H};
            }}
        """)
        scale_slider.valueChanged.connect(
            lambda v, c=ct: self._on_cursor_scale_changed(c, v))
        cl.addWidget(scale_slider)

        # 存引用 + 初始预览
        self._cursor_widgets[ct] = {
            'preview': preview, 'scale_slider': scale_slider,
            'scale_value_lbl': scale_value_lbl,
        }
        self._refresh_cursor_preview(ct)
        return col

    def _build_color_row(self, fn, ct: str, key: str, label_text: str):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFont(_make_font(fn, 14))
        lbl.setStyleSheet("color: #CCC; background: transparent; border: none;")
        row.addWidget(lbl)
        row.addStretch()

        # 色块按钮
        btn = QPushButton()
        btn.setFixedSize(96, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cur_color = self._cursor_buf[ct].get(key, '#FFFFFF')
        self._apply_color_btn_style(btn, cur_color)
        btn.clicked.connect(lambda _, c=ct, k=key, b=btn: self._on_pick_color(c, k, b))
        row.addWidget(btn)

        # 存按钮引用便于 reset
        if ct not in getattr(self, '_cursor_color_btns', {}):
            if not hasattr(self, '_cursor_color_btns'):
                self._cursor_color_btns = {}
            self._cursor_color_btns[ct] = {}
        self._cursor_color_btns[ct][key] = btn
        return row

    def _apply_color_btn_style(self, btn: QPushButton, color_hex: str):
        btn.setText(color_hex.upper())
        # 选个对比色文字: 暗色背景白字, 亮色背景黑字
        c = QColor(color_hex)
        # luminance
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        fg = "#000" if lum > 140 else "#FFF"
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color_hex}; color: {fg};
                border: 1px solid #555; border-radius: 4px;
                font-family: monospace; font-size: 12px;
            }}
            QPushButton:hover {{ border-color: #888; }}
        """)

    def _on_pick_color(self, ct: str, key: str, btn: QPushButton):
        initial = QColor(self._cursor_buf[ct].get(key, '#FFFFFF'))
        color = QColorDialog.getColor(
            initial, self, t(f"hotkey.cursor_{key}"),
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if not color.isValid():
            return
        hex_val = color.name(QColor.NameFormat.HexRgb).upper()  # #RRGGBB
        self._cursor_buf[ct][key] = hex_val
        self._apply_color_btn_style(btn, hex_val)
        self._refresh_cursor_preview(ct)

    def _on_cursor_scale_changed(self, ct: str, value: int):
        # value 是 100-400 (百分比)
        self._cursor_buf[ct]['scale'] = value / 100.0
        widgets = self._cursor_widgets.get(ct, {})
        lbl = widgets.get('scale_value_lbl')
        if lbl:
            lbl.setText(f"{value}%")
        self._refresh_cursor_preview(ct)

    def _refresh_cursor_preview(self, ct: str):
        # 预览不缓存 (使用临时 base_size, 不污染主缓存)
        from PyQt6.QtGui import QPixmap
        style = self._cursor_buf[ct]
        pm = render_cursor_pixmap(ct, style)
        widgets = self._cursor_widgets.get(ct, {})
        preview = widgets.get('preview')
        if preview:
            if pm and not pm.isNull():
                preview.setPixmap(pm)
            else:
                preview.setText("(SVG 缺失)")
                preview.setStyleSheet(
                    "background: #1A1A1A; color: #888; "
                    "border: 1px solid #2A2A2A; border-radius: 6px;")

    def _on_cursor_reset_all(self):
        self._cursor_buf = {ct: dict(DEFAULT_CURSOR_STYLES[ct])
                            for ct in ('cursor', 'cursor_off', 'cursor_block')}
        for ct, style in self._cursor_buf.items():
            # 同步色块按钮 + 滑块 + 数值标签
            for k in ('fill', 'stroke'):
                btn = self._cursor_color_btns.get(ct, {}).get(k)
                if btn:
                    self._apply_color_btn_style(btn, style[k])
            widgets = self._cursor_widgets.get(ct, {})
            slider = widgets.get('scale_slider')
            if slider:
                slider.setValue(int(round(float(style.get('scale', 1.0)) * 100)))
            self._refresh_cursor_preview(ct)

    # ── 方向盘样式页 ──

    def _ensure_wheel_buf(self):
        if not hasattr(self, '_wheel_buf'):
            from core.constants import DEFAULT_WHEEL_STYLE
            existing = (load_hotkeys() or {}).get('wheel_style') or {}
            buf = dict(DEFAULT_WHEEL_STYLE)
            # 老的 variant 字段静默忽略 (现在只配 color, fill 走按钮 bg)
            c = existing.get('color')
            if isinstance(c, str) and c.startswith('#') and len(c) == 7:
                buf['color'] = c.upper()
            self._wheel_buf = buf

    def _build_wheel_page(self, fn):
        self._ensure_wheel_buf()
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        tip = QLabel("方向盘外观: 描边色可配, 填充用按钮底色 (方向盘永远不透; active 100% / idle 50% 透明度)")
        tip.setFont(_make_font(fn, 13))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        v.addWidget(tip)
        v.addSpacing(20)

        # 单卡片: 预览 + color
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #232323; border: 1px solid #3A3A3A; border-radius: 8px; }")
        card.setFixedWidth(400)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 22, 24, 22)
        cl.setSpacing(16)

        # 预览
        preview = QLabel()
        preview.setFixedSize(240, 240)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet(
            "background: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 6px;")
        cl.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)
        self._wheel_preview_lbl = preview

        # color 行
        color_row = QHBoxLayout()
        color_lbl = QLabel("颜色")
        color_lbl.setFont(_make_font(fn, 14))
        color_lbl.setStyleSheet("color: #CCC; background: transparent; border: none;")
        color_row.addWidget(color_lbl)
        color_row.addStretch()
        self._wheel_color_btn = QPushButton()
        self._wheel_color_btn.setFixedSize(96, 28)
        self._wheel_color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_color_btn_style(self._wheel_color_btn, self._wheel_buf['color'])
        self._wheel_color_btn.clicked.connect(self._on_wheel_color_pick)
        color_row.addWidget(self._wheel_color_btn)
        cl.addLayout(color_row)

        # 卡片居左
        wrap = QHBoxLayout()
        wrap.addWidget(card)
        wrap.addStretch()
        v.addLayout(wrap)
        v.addStretch()

        # 底部: 重置 + 保存
        bottom = QHBoxLayout()
        bottom.addStretch()
        reset_btn = QPushButton("重置默认")
        reset_btn.setFixedHeight(40)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setFont(_make_font(fn, 14, bold=True))
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #FFF;
                border: none; border-radius: 6px; padding: 0 18px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        reset_btn.clicked.connect(self._on_wheel_reset)
        bottom.addWidget(reset_btn)
        bottom.addSpacing(10)
        save_btn = QPushButton(t("hotkey.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 14, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        bottom.addWidget(save_btn)
        v.addLayout(bottom)

        # 初始预览
        self._refresh_wheel_preview()
        return page

    def _refresh_wheel_preview(self):
        from scene.gp_wheel_item import render_wheel_pixmap
        pm = render_wheel_pixmap(self._wheel_buf['color'])
        if pm and not pm.isNull():
            scaled = pm.scaled(
                self._wheel_preview_lbl.width() - 8,
                self._wheel_preview_lbl.height() - 8,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._wheel_preview_lbl.setPixmap(scaled)
        else:
            self._wheel_preview_lbl.setText("(SVG 缺失)")
            self._wheel_preview_lbl.setStyleSheet(
                "background: #1A1A1A; color: #888; "
                "border: 1px solid #2A2A2A; border-radius: 6px;")

    def _on_wheel_color_pick(self):
        initial = QColor(self._wheel_buf.get('color', '#3B82F6'))
        color = QColorDialog.getColor(
            initial, self, "方向盘颜色",
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if not color.isValid():
            return
        hex_val = color.name(QColor.NameFormat.HexRgb).upper()
        self._wheel_buf['color'] = hex_val
        self._apply_color_btn_style(self._wheel_color_btn, hex_val)
        self._refresh_wheel_preview()

    def _on_wheel_reset(self):
        from core.constants import DEFAULT_WHEEL_STYLE
        self._wheel_buf = dict(DEFAULT_WHEEL_STYLE)
        self._apply_color_btn_style(self._wheel_color_btn, self._wheel_buf['color'])
        self._refresh_wheel_preview()

    # ── 语言页 ──

    def _build_language_page(self, fn):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        _detect_icon_font()

        # 标题行
        title_row = QHBoxLayout()
        lang_icon = QLabel("" if _ICON_FONT else "\U0001F310")
        if _ICON_FONT:
            lang_icon.setFont(_make_font(_ICON_FONT, 20))
        else:
            lang_icon.setFont(_make_font(fn, 20))
        lang_icon.setStyleSheet("color: #CCC; background: transparent;")
        title_row.addWidget(lang_icon)
        title_row.addSpacing(8)
        lang_lbl = QLabel("Language / 语言")
        lang_lbl.setFont(_make_font(fn, 17, bold=True))
        lang_lbl.setStyleSheet("color: #FFF; background: transparent;")
        title_row.addWidget(lang_lbl)
        title_row.addStretch()
        v.addLayout(title_row)

        v.addSpacing(20)

        # 切换按钮行
        btn_row = QHBoxLayout()

        self._lang_zh_btn = _LangBtn()
        self._lang_zh_btn.setFixedHeight(40)
        self._lang_zh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_zh_btn.clicked.connect(lambda: self._set_lang("zh-CN"))
        zh_lay = QHBoxLayout(self._lang_zh_btn)
        zh_lay.setContentsMargins(12, 0, 12, 0)
        zh_lay.setSpacing(6)
        self._zh_icon_lbl = QLabel("" if _ICON_FONT else "✓")
        if _ICON_FONT:
            self._zh_icon_lbl.setFont(_make_font(_ICON_FONT, 16))
        else:
            self._zh_icon_lbl.setFont(_make_font(fn, 16, bold=True))
        self._zh_icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        zh_lay.addWidget(self._zh_icon_lbl)
        self._zh_text_lbl = QLabel("中文")
        self._zh_text_lbl.setFont(_make_font(fn, 16, bold=True))
        self._zh_text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        zh_lay.addWidget(self._zh_text_lbl)
        btn_row.addWidget(self._lang_zh_btn)

        btn_row.addSpacing(10)

        self._lang_en_btn = _LangBtn()
        self._lang_en_btn.setFixedHeight(40)
        self._lang_en_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_en_btn.clicked.connect(lambda: self._set_lang("en"))
        en_lay = QHBoxLayout(self._lang_en_btn)
        en_lay.setContentsMargins(12, 0, 12, 0)
        en_lay.setSpacing(6)
        self._en_icon_lbl = QLabel("" if _ICON_FONT else "✓")
        if _ICON_FONT:
            self._en_icon_lbl.setFont(_make_font(_ICON_FONT, 16))
        else:
            self._en_icon_lbl.setFont(_make_font(fn, 16, bold=True))
        self._en_icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        en_lay.addWidget(self._en_icon_lbl)
        self._en_text_lbl = QLabel("English")
        self._en_text_lbl.setFont(_make_font(fn, 16, bold=True))
        self._en_text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        en_lay.addWidget(self._en_text_lbl)
        btn_row.addWidget(self._lang_en_btn)

        btn_row.addStretch()
        v.addLayout(btn_row)

        v.addSpacing(20)
        restart_hint = QLabel(
            "切换语言需要重启应用才能生效\n"
            "Language change requires restart to take effect")
        restart_hint.setFont(_make_font(fn, 13))
        restart_hint.setStyleSheet("color: #888; background: transparent;")
        restart_hint.setWordWrap(True)
        v.addWidget(restart_hint)

        v.addStretch()

        self._selected_lang = get_lang()
        self._update_lang_buttons()
        return page

    # ── 日志 (诊断报告) 页 ──

    def _build_log_page(self, fn):
        """日志 (诊断报告) 页 — 通栏布局: 顶部 标题+说明 跨整行, 下方两列 状态/操作"""
        from core.log_setup import (
            get_session_log_path, list_recent_log_paths,
        )
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ── 顶部: 标题 + 说明 ──
        title = QLabel(t("hotkey.log_page_title"))
        title.setFont(_make_font(fn, 24, bold=True))
        title.setStyleSheet("color: #F59E0B; background: transparent;")
        v.addWidget(title)
        v.addSpacing(8)
        tip = QLabel(t("hotkey.log_page_tip"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #AAA; background: transparent;")
        tip.setWordWrap(True)
        v.addWidget(tip)

        v.addSpacing(20)
        sep1 = QFrame(); sep1.setFixedHeight(1); sep1.setStyleSheet("background: #444;")
        v.addWidget(sep1)
        v.addSpacing(20)

        # ── 下方双栏: 左 状态卡 / 右 操作卡 ──
        two_col = QHBoxLayout()
        two_col.setSpacing(24)

        # === 左栏: 状态卡 ===
        left = QFrame()
        left.setStyleSheet(
            "QFrame { background: #232323; border: 1px solid #3A3A3A; border-radius: 8px; }")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(20, 18, 20, 18)
        ll.setSpacing(10)

        # 当前会话日志
        cur_path = get_session_log_path() or '-'
        cur_lbl = QLabel(t("hotkey.log_session_current"))
        cur_lbl.setFont(_make_font(fn, 13, bold=True))
        cur_lbl.setStyleSheet("color: #FFF; background: transparent; border: none;")
        ll.addWidget(cur_lbl)
        self._log_cur_path_lbl = QLabel(cur_path)
        self._log_cur_path_lbl.setFont(_make_font(fn, 12))
        self._log_cur_path_lbl.setStyleSheet(
            "color: #888; background: transparent; border: none; font-family: monospace;")
        self._log_cur_path_lbl.setWordWrap(True)
        self._log_cur_path_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        ll.addWidget(self._log_cur_path_lbl)

        ll.addSpacing(6)
        sep_in = QFrame(); sep_in.setFixedHeight(1); sep_in.setStyleSheet("background: #3A3A3A;")
        ll.addWidget(sep_in)
        ll.addSpacing(6)

        # 保留数
        kept_n = len(list_recent_log_paths())
        self._log_retained_lbl = QLabel(t("hotkey.log_retained", n=kept_n))
        self._log_retained_lbl.setFont(_make_font(fn, 13))
        self._log_retained_lbl.setStyleSheet(
            "color: #CCC; background: transparent; border: none;")
        ll.addWidget(self._log_retained_lbl)

        ll.addSpacing(12)

        # 启用日志开关
        self._log_enable_cb = QPushButton(t("hotkey.log_enable"))
        self._log_enable_cb.setCheckable(True)
        self._log_enable_cb.setChecked(self._is_logging_enabled())
        self._log_enable_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_enable_cb.setFixedHeight(34)
        self._log_enable_cb.setFont(_make_font(fn, 13, bold=True))
        self._log_enable_cb.clicked.connect(self._on_toggle_logging)
        self._apply_log_enable_btn_style()
        ll.addWidget(self._log_enable_cb)
        en_hint = QLabel(t("hotkey.log_enable_hint"))
        en_hint.setFont(_make_font(fn, 11))
        en_hint.setStyleSheet("color: #777; background: transparent; border: none;")
        en_hint.setWordWrap(True)
        ll.addWidget(en_hint)

        ll.addStretch()
        two_col.addWidget(left, 1)

        # === 右栏: 操作卡 ===
        right = QFrame()
        right.setStyleSheet(
            "QFrame { background: #232323; border: 1px solid #3A3A3A; border-radius: 8px; }")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 18, 20, 18)
        rl.setSpacing(14)

        # 操作标题
        ops_lbl = QLabel(t("hotkey.log_export").rsplit('—', 1)[0].strip() or t("hotkey.menu_log"))
        ops_lbl.setFont(_make_font(fn, 13, bold=True))
        ops_lbl.setStyleSheet("color: #FFF; background: transparent; border: none;")
        # 用更通用的"操作" — 直接取菜单名 + 后缀, 简单点
        ops_lbl.setText(t("hotkey.menu_log"))
        rl.addWidget(ops_lbl)

        # 打开日志文件夹
        open_btn = QPushButton(t("hotkey.log_open_folder"))
        open_btn.setFixedHeight(40)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setFont(_make_font(fn, 14))
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px; padding: 0 14px;
                text-align: left;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        open_btn.clicked.connect(self._on_open_log_folder)
        rl.addWidget(open_btn)

        rl.addSpacing(4)

        # 导出诊断包 (主按钮)
        export_btn = QPushButton(t("hotkey.log_export"))
        export_btn.setFixedHeight(48)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setFont(_make_font(fn, 15, bold=True))
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px; padding: 0 14px;
                text-align: left;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        export_btn.clicked.connect(self._on_export_diag)
        rl.addWidget(export_btn)

        ex_hint = QLabel(t("hotkey.log_export_hint"))
        ex_hint.setFont(_make_font(fn, 12))
        ex_hint.setStyleSheet("color: #999; background: transparent; border: none;")
        ex_hint.setWordWrap(True)
        rl.addWidget(ex_hint)

        rl.addStretch()
        two_col.addWidget(right, 1)

        v.addLayout(two_col)
        v.addStretch()
        return page

    # ── 日志页操作 ──

    def _is_logging_enabled(self) -> bool:
        import logging
        root = logging.getLogger()
        # FileHandler 是否还存在且 level <= CRITICAL
        for h in root.handlers:
            if isinstance(h, logging.FileHandler) and h.level <= logging.CRITICAL:
                return True
        return False

    def _on_toggle_logging(self):
        """开关日志: 关 = file handler.level=CRITICAL+1, 开 = 恢复 INFO"""
        import logging
        enabled = self._log_enable_cb.isChecked()
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.FileHandler):
                h.setLevel(logging.INFO if enabled else logging.CRITICAL + 1)
        self._apply_log_enable_btn_style()

    def _apply_log_enable_btn_style(self):
        if self._log_enable_cb.isChecked():
            bg, bg_h, fg = C_CYBER, C_CYBER_H, "#FFF"
            prefix = "\u2713 "
        else:
            bg, bg_h, fg = "#404040", "#505050", "#AAA"
            prefix = ""
        self._log_enable_cb.setText(prefix + t("hotkey.log_enable"))
        self._log_enable_cb.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {fg};
                border: none; border-radius: 6px; padding: 0 14px;
                text-align: left;
            }}
            QPushButton:hover {{ background: {bg_h}; }}
        """)

    def _on_open_log_folder(self):
        from core.log_setup import _logs_root
        import subprocess
        path = _logs_root()
        try:
            subprocess.Popen(['explorer', path])
        except Exception:
            pass

    def _on_export_diag(self):
        """导出诊断包到桌面 + 进度弹窗"""
        from views.diag_export_dialog import DiagExportDialog
        dlg = DiagExportDialog(self)
        dlg.exec()

    # ── 关于页 ──

    def _build_about_page(self, fn):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ── 应用图标 (居中, 100x100, 用 PNG 源缩放更清晰) ──
        icon_path = os.path.join(APP_DIR, "assets", "icon_source.png")
        if os.path.exists(icon_path):
            icon_lbl = QLabel()
            pm = QPixmap(icon_path)
            icon_lbl.setPixmap(pm.scaled(
                100, 100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent;")
            v.addWidget(icon_lbl)
            v.addSpacing(8)

        # ── 标题 + 版本 (居中) ──
        title = QLabel(get_app_title())
        title.setStyleSheet(
            f"color: #F59E0B; font-size: 28px; font-weight: bold; "
            f"font-family: '{fn}'; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        v.addSpacing(6)

        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(version)

        v.addSpacing(2)

        update = QLabel(t("about.last_update", date=_ABOUT_LAST_UPDATE))
        update.setStyleSheet("color: #666; font-size: 12px; background: transparent;")
        update.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(update)

        v.addSpacing(16)

        sep1 = QFrame()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background: #444;")
        v.addWidget(sep1)

        v.addSpacing(16)

        # ── 产品介绍 ──
        desc = QLabel(t("about.description"))
        desc.setStyleSheet(
            f"color: #CCC; font-size: 16px; font-family: '{fn}'; background: transparent;")
        desc.setWordWrap(True)
        v.addWidget(desc)

        v.addSpacing(16)

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #444;")
        v.addWidget(sep2)

        v.addSpacing(24)

        # ── QR 码 + 右侧文字 ──
        qr_row = QHBoxLayout()
        qr_row.setSpacing(24)

        qr_path = os.path.join(APP_DIR, "assets", "wechat_qr.png")
        qr_label = QLabel()
        qr_size = 180
        if os.path.exists(qr_path):
            pixmap = QPixmap(qr_path)
            qr_label.setPixmap(pixmap.scaled(
                qr_size, qr_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            qr_label.setFixedSize(qr_size, qr_size)
        else:
            qr_label.setText(t("about.qr_missing"))
            qr_label.setStyleSheet(
                "background: #3A3A3A; color: #888; "
                "border: 1px solid #555; border-radius: 8px; font-size: 14px;")
            qr_label.setFixedSize(qr_size, qr_size)
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_row.addWidget(qr_label, 0, Qt.AlignmentFlag.AlignTop)

        # 右侧 hint + email + github
        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        right_col.setContentsMargins(0, 4, 0, 0)

        hint = QLabel(t("about.qr_hint"))
        hint.setStyleSheet(
            f"color: #AAA; font-size: 16px; font-family: '{fn}'; background: transparent;")
        hint.setWordWrap(True)
        right_col.addWidget(hint)

        right_col.addSpacing(16)

        email = QLabel(t("about.email"))
        email.setStyleSheet(
            f"color: #888; font-size: 16px; font-family: '{fn}'; background: transparent;")
        email.setCursor(Qt.CursorShape.PointingHandCursor)
        email.mousePressEvent = lambda e: webbrowser.open(
            "mailto:life.is.like.a.boat@gmail.com")
        right_col.addWidget(email)

        github = QLabel(t("about.github"))
        github.setStyleSheet(
            f"color: #888; font-size: 16px; font-family: '{fn}'; background: transparent;")
        github.setCursor(Qt.CursorShape.PointingHandCursor)
        github.mousePressEvent = lambda e: webbrowser.open(
            "https://github.com/TEGGTouch/TEGG-Touch/releases")
        right_col.addWidget(github)

        right_col.addStretch()
        qr_row.addLayout(right_col, 1)

        v.addLayout(qr_row)

        v.addStretch()
        return page

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

        for i, (cat_name, keys) in enumerate(_get_settings_key_categories()):
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
        if lang == self._selected_lang:
            return
        self._selected_lang = lang
        self._update_lang_buttons()
        # 立即保存到磁盘（合并到现有 hotkeys 配置）
        current = load_hotkeys() or {}
        current['language'] = lang
        save_hotkeys(current)
        load_locale(lang)
        self.language_changed.emit(lang)

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
        # 语言已在切换时即时保存，这里只保留当前值
        data['language'] = self._selected_lang
        # 光标配色 (用户在 cursor 页改动的 buffer)
        if hasattr(self, '_cursor_buf'):
            data['cursor_styles'] = self._cursor_buf
            clear_cursor_render_cache()
        # 方向盘样式
        if hasattr(self, '_wheel_buf'):
            data['wheel_style'] = self._wheel_buf
            from scene.gp_wheel_item import clear_wheel_render_cache
            clear_wheel_render_cache()

        save_hotkeys(data)

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
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
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
