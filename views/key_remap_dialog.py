"""
TEGG Touch 蛋挞 (PyQt6) - key_remap_dialog.py
键盘映射设置弹窗 — 三栏: 映射列表 | 编辑区 | 候选动作面板。

一条映射 = 物理键 (src) → 目标动作 (dst) + 触发模式 (mode)。
dst 直接复用 run_controller._smart_trigger 的动作字符串语法, 所以右栏候选
面板与按键编辑器/语音弹窗完全同源 (键盘/手柄/鼠标/宏/应用/回中)。

物理键用「捕获」录入: 点一下按钮, 再按真实键盘, 由 core.keyboard_hook 的
捕获模式吞掉并回读键名 —— 比让用户在面板里翻找准得多。
"""

import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget,
    QScrollArea, QFrame, QApplication, QStackedWidget, QListWidget,
    QListWidgetItem,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer

from core.i18n import t, get_font
from core.constants import GP_LABEL_TO_KEY, GP_KEY_PREFIX, APP_PREFIX
from core import keyboard_hook

from views.button_editor_dialog import (
    TagInput, _FlowWidget, _get_key_categories, _get_mouse_keys,
    populate_gp_palette,
    C_PM_BG, C_GRAY, C_GRAY_H, C_AMBER, C_CLOSE, C_CLOSE_H,
    C_CAT_LABEL,
)

C_ACCENT = "#F59E0B"        # 键盘映射主色 (琥珀, 与工具栏按钮一致)
C_ACCENT_H = "#D97706"
C_MACRO = "#8B5CF6"

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
    from PyQt6.QtGui import QFont
    f = QFont(name)
    screen = QApplication.primaryScreen()
    dpi = screen.logicalDotsPerInch() if screen else 96.0
    f.setPointSizeF(px * 72.0 / dpi)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class _CheckToggle(QWidget):
    """小复选框 (方块 + 文字), 与语音弹窗同款。"""

    def __init__(self, text, fn, checked=True, parent=None, accent=C_ACCENT):
        super().__init__(parent)
        self._checked = checked
        self._accent = accent
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._box = QLabel()
        self._box.setFixedSize(18, 18)
        self._box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._box)
        self._lbl = QLabel(text)
        self._lbl.setFont(_make_font(fn, 14))
        self._lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        lay.addWidget(self._lbl)
        lay.addStretch()
        self._update_style()

    def isChecked(self):
        return self._checked

    def setChecked(self, val):
        self._checked = bool(val)
        self._update_style()

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._update_style()
        self.toggled()

    def toggled(self):
        pass

    def _update_style(self):
        if self._checked:
            self._box.setText("✓")
            self._box.setStyleSheet(
                f"background: {self._accent}; color: #1A1A1A; "
                f"border-radius: 4px; font-weight: bold;")
        else:
            self._box.setText("")
            self._box.setStyleSheet(
                "background: #2A2A2A; border: 2px solid #555; border-radius: 4px;")


class KeyRemapDialog(QDialog):
    """键盘映射设置弹窗。"""

    settings_saved = pyqtSignal()
    xmacros_changed = pyqtSignal(list)
    apps_changed = pyqtSignal(list)

    COL1_W = 260
    COL2_W = 320
    PADDING = 20
    GUTTER = 20
    WIN_W = 1160
    WIN_H = 860

    CAPTURE_TIMEOUT_MS = 8000

    def __init__(self, key_remaps=None, enabled=True, parent=None,
                 xmacros=None, apps=None, recenter_targets=None):
        super().__init__(parent)
        self._remaps = [dict(r) for r in (key_remaps or [])]
        self._enabled = bool(enabled)
        self._macros = list(xmacros or [])
        self._apps = [dict(a) for a in (apps or [])]
        self._recenter_targets = [dict(x) for x in (recenter_targets or [])]
        self._current_idx = -1
        self._focus_widget = None
        self._drag_pos = None
        self._capturing = False
        self._capture_timer = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        _detect_icon_font()
        self._init_ui()
        self._rebuild_list()
        if self._remaps:
            self._list.setCurrentRow(0)
        else:
            self._update_editor_visibility()
        self._center_on_screen()

    # ── UI ──

    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("kr_container")
        container.setStyleSheet(f"""
            QFrame#kr_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING,
                                self.PADDING, self.PADDING)
        root.setSpacing(0)

        # ── 标题栏 ──
        title_row = QHBoxLayout()
        icon = QLabel("" if _ICON_FONT else "⌨")
        icon.setFont(_make_font(_ICON_FONT or fn, 20))
        icon.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(icon)
        title_row.addSpacing(6)
        title_lbl = QLabel(t("key_remap.title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        close_btn = QPushButton("" if _ICON_FONT else "✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFont(_make_font(_ICON_FONT or fn, 20 if _ICON_FONT else 18,
                                     bold=not _ICON_FONT))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF;
                           border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        tip = QLabel(t("key_remap.tip"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addSpacing(14)

        # ── 三列 ──
        columns = QHBoxLayout()
        columns.setSpacing(0)

        col1 = self._build_col1_list(fn)
        col1.setFixedWidth(self.COL1_W)
        columns.addWidget(col1)
        columns.addSpacing(self.GUTTER)
        d1 = QFrame(); d1.setFixedWidth(1); d1.setStyleSheet("background: #444;")
        columns.addWidget(d1)

        col2 = self._build_col2_editor(fn)
        col2.setFixedWidth(self.COL2_W)
        columns.addSpacing(self.GUTTER - 10)
        columns.addWidget(col2)
        columns.addSpacing(self.GUTTER)
        d2 = QFrame(); d2.setFixedWidth(1); d2.setStyleSheet("background: #444;")
        columns.addWidget(d2)
        columns.addSpacing(10)

        columns.addWidget(self._build_right_panel(fn), 1)
        root.addLayout(columns, 1)

    # ── Col1: 列表 + 总开关 ──

    def _build_col1_list(self, fn):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # 总开关
        self._enable_cb = _CheckToggle(t("key_remap.enable"), fn, self._enabled)
        self._enable_cb.toggled = self._on_enable_toggled
        v.addWidget(self._enable_cb)
        v.addSpacing(4)

        self._list = QListWidget()
        self._list.setFont(_make_font(fn, 14))
        self._list.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none;
                           color: #E0E0E0; outline: none; }}
            QListWidget::item {{ background: {C_GRAY}; border-radius: 6px;
                                 padding: 8px 10px; margin-bottom: 6px; }}
            QListWidget::item:selected {{ background: {C_ACCENT}; color: #1A1A1A; }}
            QListWidget::item:hover {{ background: {C_GRAY_H}; color: #FFF; }}
            /* 选中行被 hover 时不能被上面那条 hover 规则改成白字 —— 琥珀底必须配黑字 */
            QListWidget::item:selected:hover {{ background: {C_ACCENT}; color: #1A1A1A; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; border: none; }}
            QScrollBar::handle:vertical {{ background: #404040; border-radius: 4px;
                                           min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        self._list.currentRowChanged.connect(self._on_row_changed)
        v.addWidget(self._list, 1)

        add_btn = QPushButton(t("key_remap.add"))
        add_btn.setFixedHeight(36)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFont(_make_font(fn, 14))
        add_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_ACCENT}; color: #1A1A1A;
                           border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_ACCENT_H}; }}
        """)
        add_btn.clicked.connect(self._on_add)
        v.addWidget(add_btn)
        return wrap

    def _on_enable_toggled(self):
        self._enabled = self._enable_cb.isChecked()

    # ── Col2: 编辑区 ──

    def _build_col2_editor(self, fn):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._editor_hint = QLabel(t("key_remap.select_hint"))
        self._editor_hint.setFont(_make_font(fn, 14))
        self._editor_hint.setStyleSheet("color: #666; background: transparent;")
        self._editor_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_hint.setWordWrap(True)
        v.addWidget(self._editor_hint, 1)

        self._editor_form = QWidget()
        self._editor_form.setStyleSheet("background: transparent;")
        form = QVBoxLayout(self._editor_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)

        # 物理键 (捕获)
        src_lbl = QLabel(t("key_remap.src"))
        src_lbl.setFont(_make_font(fn, 14))
        src_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        form.addWidget(src_lbl)

        self._src_btn = QPushButton()
        self._src_btn.setFixedHeight(44)
        self._src_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._src_btn.setFont(_make_font(fn, 16, bold=True))
        self._src_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._src_btn.clicked.connect(self._on_capture_clicked)
        form.addWidget(self._src_btn)
        self._update_src_btn()

        # 目标动作
        dst_lbl = QLabel(t("key_remap.dst"))
        dst_lbl.setFont(_make_font(fn, 14))
        dst_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        form.addWidget(dst_lbl)
        self._dst_input = TagInput(initial_value="", accent_color=C_AMBER,
                                   tag_text_color="#1A1A1A")
        self._dst_input.setMinimumHeight(42)
        self._dst_input.focusChanged.connect(self._on_focus_changed)
        form.addWidget(self._dst_input)

        # 模式
        mode_lbl = QLabel(t("key_remap.mode"))
        mode_lbl.setFont(_make_font(fn, 14))
        mode_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        form.addWidget(mode_lbl)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        self._mode_btns = {}
        self._current_mode = 'hold'
        for k, label in (('hold', t("key_remap.mode_hold")),
                         ('click', t("key_remap.mode_click")),
                         ('toggle', t("key_remap.mode_toggle"))):
            b = QPushButton(label)
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(_make_font(fn, 13))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _, kk=k: self._on_mode_clicked(kk))
            mode_row.addWidget(b)
            self._mode_btns[k] = b
        form.addLayout(mode_row)
        self._mode_hint = QLabel(t("key_remap.mode_hold_hint"))
        self._mode_hint.setFont(_make_font(fn, 12))
        self._mode_hint.setStyleSheet("color: #777; background: transparent;")
        self._mode_hint.setWordWrap(True)
        form.addWidget(self._mode_hint)
        self._update_mode_styles()

        # 单条启用
        self._row_enable_cb = _CheckToggle(t("key_remap.row_enable"), fn, True)
        self._row_enable_cb.toggled = self._on_row_enable_toggled
        form.addWidget(self._row_enable_cb)

        form.addStretch()

        del_save_row = QHBoxLayout()
        del_save_row.setSpacing(8)
        del_btn = QPushButton(t("key_remap.delete"))
        del_btn.setFixedHeight(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFont(_make_font(fn, 14))
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF;
                           border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(self._on_delete)
        del_save_row.addWidget(del_btn, 1)

        save_btn = QPushButton(t("key_remap.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 16, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_ACCENT}; color: #1A1A1A;
                           border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_ACCENT_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        del_save_row.addWidget(save_btn, 1)
        form.addLayout(del_save_row)

        v.addWidget(self._editor_form)
        self._editor_form.setVisible(False)
        return wrap

    def _update_editor_visibility(self):
        has = 0 <= self._current_idx < len(self._remaps)
        self._editor_form.setVisible(has)
        self._editor_hint.setVisible(not has)

    # ── 物理键捕获 ──

    def _update_src_btn(self):
        if self._capturing:
            self._src_btn.setText(t("key_remap.capturing"))
            self._src_btn.setStyleSheet(f"""
                QPushButton {{ background: #2A2A2A; color: {C_ACCENT};
                               border: 2px dashed {C_ACCENT}; border-radius: 6px; }}
            """)
            return
        src = ''
        if 0 <= self._current_idx < len(self._remaps):
            src = self._remaps[self._current_idx].get('src', '')
        self._src_btn.setText(src.upper() if src else t("key_remap.src_empty"))
        color = "#FFF" if src else "#888"
        self._src_btn.setStyleSheet(f"""
            QPushButton {{ background: #2A2A2A; color: {color};
                           border: 2px solid {C_GRAY_H}; border-radius: 6px; }}
            QPushButton:hover {{ border-color: {C_ACCENT}; }}
        """)

    def _on_capture_clicked(self):
        if self._capturing:
            self._stop_capture()
            return
        if not (0 <= self._current_idx < len(self._remaps)):
            return
        self._capturing = True
        self._update_src_btn()
        keyboard_hook.start_capture()
        self._capture_timer = QTimer(self)
        self._capture_timer.setInterval(40)
        self._capture_timer.timeout.connect(self._poll_capture)
        self._capture_timer.start()
        self._capture_elapsed = 0
        QTimer.singleShot(self.CAPTURE_TIMEOUT_MS, self._capture_timeout)

    def _poll_capture(self):
        if not self._capturing:
            return
        name = keyboard_hook.poll_captured()
        if not name:
            return
        if 0 <= self._current_idx < len(self._remaps):
            self._remaps[self._current_idx]['src'] = name
            self._refresh_current_item()
        self._stop_capture()

    def _capture_timeout(self):
        if self._capturing:
            self._stop_capture()

    def _stop_capture(self):
        self._capturing = False
        if self._capture_timer is not None:
            self._capture_timer.stop()
            self._capture_timer = None
        keyboard_hook.stop_capture()
        self._update_src_btn()

    # ── 模式 ──

    def _on_mode_clicked(self, mode):
        self._current_mode = mode
        if 0 <= self._current_idx < len(self._remaps):
            self._remaps[self._current_idx]['mode'] = mode
        self._update_mode_styles()

    def _update_mode_styles(self):
        for k, b in self._mode_btns.items():
            if k == self._current_mode:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C_ACCENT}; color: #1A1A1A;
                                   border: none; border-radius: 6px; padding: 0 10px; }}
                    QPushButton:hover {{ background: {C_ACCENT_H}; }}
                """)
            else:
                b.setStyleSheet("""
                    QPushButton { background: #404040; color: #AAA;
                                  border: none; border-radius: 6px; padding: 0 10px; }
                    QPushButton:hover { background: #505050; }
                """)
        if hasattr(self, '_mode_hint'):
            self._mode_hint.setText(t(f"key_remap.mode_{self._current_mode}_hint"))

    def _on_row_enable_toggled(self):
        if 0 <= self._current_idx < len(self._remaps):
            self._remaps[self._current_idx]['enabled'] = self._row_enable_cb.isChecked()
            self._refresh_current_item()

    # ── 右栏候选面板 ──

    def _build_right_panel(self, fn):
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        titles = [t("macro.tab_keys"), t("macro.tab_gp"), t("macro.tab_mouse"),
                  t("macro.tab_macros"), t("app.tab"), t("recenter.tab")]
        self._tab_btns = []
        for i, title in enumerate(titles):
            b = QPushButton(title)
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(_make_font(fn, 14, bold=True))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _, ix=i: self._switch_tab(ix))
            tab_row.addWidget(b)
            self._tab_btns.append(b)
        tab_row.addStretch()
        lay.addLayout(tab_row)
        lay.addSpacing(10)

        from views.recenter_palette import RecenterPaletteWidget
        self._recenter_palette = RecenterPaletteWidget(
            self._recenter_targets, current_key=None, fn=fn)
        self._recenter_palette.target_selected.connect(self._on_recenter_clicked)

        self._tab_stack = QStackedWidget()
        self._tab_stack.setStyleSheet("background: transparent;")
        self._tab_stack.addWidget(self._build_key_palette(fn))     # 0 键盘
        self._tab_stack.addWidget(self._build_gp_palette(fn))      # 1 手柄
        self._tab_stack.addWidget(self._build_mouse_palette(fn))   # 2 鼠标
        self._tab_stack.addWidget(self._build_macro_tab(fn))       # 3 宏
        self._tab_stack.addWidget(self._build_app_tab(fn))         # 4 应用
        self._tab_stack.addWidget(self._recenter_palette)          # 5 回中
        lay.addWidget(self._tab_stack, 1)
        self._switch_tab(0)
        return panel

    def _switch_tab(self, idx):
        self._tab_stack.setCurrentIndex(idx)
        sel = (f"QPushButton {{ background: transparent; color: #FFF; border: none; "
               f"border-bottom: 2px solid {C_ACCENT}; border-radius: 0; "
               f"padding: 0 12px 4px 12px; }}")
        off = ("QPushButton { background: transparent; color: #AAA; border: none; "
               "border-bottom: 2px solid transparent; border-radius: 0; "
               "padding: 0 12px 4px 12px; } "
               "QPushButton:hover { color: #E0E0E0; }")
        for ix, b in enumerate(self._tab_btns):
            b.setStyleSheet(sel if idx == ix else off)

    def _scroll_area(self):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; border: none; }
            QScrollBar::handle:vertical { background: #404040; border-radius: 4px;
                                          min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        return sc

    def _build_key_palette(self, fn):
        sc = self._scroll_area()
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)
        for i, (cat_name, keys) in enumerate(_get_key_categories()):
            if i > 0:
                lay.addSpacing(18)
            cat = QLabel(f"── {cat_name} ──")
            cat.setFont(_make_font(fn, 14, bold=True))
            cat.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
            lay.addWidget(cat)
            lay.addSpacing(8)
            box = QWidget()
            box.setStyleSheet("background: transparent;")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(0)
            bl.addWidget(_FlowWidget(keys, self._on_key_clicked, fn, box))
            lay.addWidget(box)
        lay.addStretch()
        sc.setWidget(content)
        return sc

    def _build_gp_palette(self, fn):
        sc = self._scroll_area()
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)
        populate_gp_palette(lay, fn, self._on_gp_clicked, self)
        sc.setWidget(body)
        return sc

    def _on_gp_clicked(self, label):
        storage = GP_LABEL_TO_KEY.get(label, label)
        self._on_key_clicked(GP_KEY_PREFIX + storage)

    def _build_mouse_palette(self, fn):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)
        cat = QLabel(f"── {t('key_cat.mouse_buttons')} ──")
        cat.setFont(_make_font(fn, 14, bold=True))
        cat.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        lay.addWidget(cat)
        lay.addSpacing(8)
        mouse_keys = _get_mouse_keys()
        names = [label for label, _ in mouse_keys]
        self._mouse_name_to_tag = dict(zip(names, [tag for _, tag in mouse_keys]))
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(_FlowWidget(names, self._on_mouse_clicked, fn, box))
        lay.addWidget(box)
        lay.addStretch()
        return page

    def _on_mouse_clicked(self, display_name):
        self._on_key_clicked(self._mouse_name_to_tag.get(display_name, display_name))

    def _build_app_tab(self, fn):
        from views.app_palette import AppPaletteWidget
        w = AppPaletteWidget(fn)
        w.app_clicked.connect(self._on_app_clicked)
        return w

    def _on_app_clicked(self, app: dict):
        name = app.get('name', '')
        path = app.get('path', '')
        if not name:
            return
        for a in self._apps:
            if a.get('name') == name:
                a['path'] = path
                break
        else:
            self._apps.append({'name': name, 'path': path})
        self.apps_changed.emit(self._apps)
        self._on_key_clicked(APP_PREFIX + name)

    def _on_recenter_clicked(self, key):
        self._on_key_clicked('recenter:' + (key or 'screen'))

    # ── 宏 Tab (浏览 + 新建/编辑/删除, 与语音弹窗同款) ──

    def _build_macro_tab(self, fn):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        cat = QLabel(f"── {t('macro.macro_list_label')} ──")
        cat.setFont(_make_font(fn, 14, bold=True))
        cat.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        cat.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(cat)

        self._macro_list = QListWidget()
        self._macro_list.setStyleSheet(f"""
            QListWidget {{ background: {C_PM_BG}; border: none; outline: none; }}
            QListWidget::item {{ background: transparent; padding: 0px; border: none; }}
            QListWidget::item:selected {{ background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; border: none; }}
            QScrollBar::handle:vertical {{ background: #404040; border-radius: 4px;
                                           min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        self._macro_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self._macro_list, 1)

        new_btn = QPushButton(t("macro.new"))
        new_btn.setFixedHeight(40)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setFont(_make_font(fn, 15))
        new_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_MACRO}; color: #FFF;
                           border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: #7C3AED; }}
        """)
        new_btn.clicked.connect(self._new_macro)
        lay.addWidget(new_btn)

        QTimer.singleShot(0, self._rebuild_macro_list)
        return page

    def _rebuild_macro_list(self):
        fn = get_font()
        self._macro_list.clear()
        ROW_H = 40
        if not self._macros:
            it = QListWidgetItem()
            it.setSizeHint(QSize(0, 60))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self._macro_list.addItem(it)
            hint = QLabel(t("macro.no_macros_hint"))
            hint.setFont(_make_font(fn, 14))
            hint.setStyleSheet("color: #666; background: transparent;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            self._macro_list.setItemWidget(it, hint)
            return
        for i, macro in enumerate(self._macros):
            name = macro.get('name', f'Macro {i+1}')
            row = QFrame()
            row.setFixedHeight(ROW_H)
            row.setObjectName("macro_row")
            row.setStyleSheet(f"""
                QFrame#macro_row {{ background: {C_GRAY}; border-radius: 6px; }}
                QFrame#macro_row:hover {{ background: {C_MACRO}; }}
            """)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(15, 0, 10, 0)
            rl.setSpacing(6)
            nl = QLabel(name)
            nl.setFont(_make_font(fn, 14))
            nl.setStyleSheet("color: white; background: transparent;")
            nl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            rl.addWidget(nl, 1)
            for icon, fallback, slot in (
                    ("", "✎", lambda _, ix=i: self._edit_macro(ix)),
                    ("", "✕", lambda _, ix=i: self._delete_macro(ix))):
                b = QPushButton(icon if _ICON_FONT else fallback)
                b.setFixedSize(30, 30)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setFont(_make_font(_ICON_FONT or fn, 14))
                b.setStyleSheet("""
                    QPushButton { color: white; background: transparent; border: none; }
                    QPushButton:hover { background: rgba(255,255,255,0.15);
                                        border-radius: 6px; }
                """)
                b.clicked.connect(slot)
                rl.addWidget(b)
            row.mousePressEvent = lambda e, n=name: self._on_key_clicked(f"xmacro:{n}")
            it = QListWidgetItem()
            it.setSizeHint(QSize(0, ROW_H + 10))
            self._macro_list.addItem(it)
            self._macro_list.setItemWidget(it, row)

    def _new_macro(self):
        from views.macro_editor_dialog import MacroEditorDialog
        names = [m.get('name', '') for m in self._macros]
        dlg = MacroEditorDialog(existing_names=names, parent=self,
                                mode='mix', apps=self._apps)
        dlg.macro_saved.connect(lambda d: self._on_macro_saved(d, -1))
        dlg.apps_changed.connect(self._on_nested_apps_changed)
        dlg.exec()

    def _edit_macro(self, idx):
        from views.macro_editor_dialog import MacroEditorDialog
        data = copy.deepcopy(self._macros[idx])
        names = [m.get('name', '') for m in self._macros]
        dlg = MacroEditorDialog(macro_data=data, existing_names=names, parent=self,
                                mode='mix', apps=self._apps)
        dlg.macro_saved.connect(lambda d: self._on_macro_saved(d, idx))
        dlg.apps_changed.connect(self._on_nested_apps_changed)
        dlg.exec()

    def _delete_macro(self, idx):
        from views.profile_manager_dialog import _StyledConfirmDialog
        name = self._macros[idx].get('name', '')
        msg = t("macro.confirm_delete").replace("{name}", name)
        dlg = _StyledConfirmDialog(t("macro.confirm_delete_title"), msg,
                                   parent=self, accent_color=C_MACRO)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._macros.pop(idx)
            self._rebuild_macro_list()
            self.xmacros_changed.emit(self._macros)

    def _on_macro_saved(self, data, idx):
        if 0 <= idx < len(self._macros):
            self._macros[idx] = data
        else:
            self._macros.append(data)
        self._rebuild_macro_list()
        self.xmacros_changed.emit(self._macros)

    def _on_nested_apps_changed(self, apps_list):
        self._apps = [dict(a) for a in apps_list]
        self.apps_changed.emit(self._apps)

    # ── 候选 → 目标动作 ──

    def _on_key_clicked(self, key_name):
        if 0 <= self._current_idx < len(self._remaps):
            self._dst_input.add_tag(key_name)
            self._remaps[self._current_idx]['dst'] = self._dst_input.get_value()
            self._refresh_current_item()

    def _on_focus_changed(self, widget):
        self._focus_widget = widget

    # ── 列表 ↔ 编辑同步 ──

    def _display_name(self, r: dict) -> str:
        src = (r.get('src') or '').strip()
        dst = (r.get('dst') or '').strip()
        left = src.upper() if src else t("key_remap.src_empty")
        right = dst if dst else t("key_remap.dst_empty")
        text = f"{left}  →  {right}"
        if not r.get('enabled', True):
            text += f"  ({t('key_remap.disabled')})"
        return text

    def _rebuild_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for r in self._remaps:
            self._list.addItem(self._display_name(r))
        self._list.blockSignals(False)

    def _refresh_current_item(self):
        if 0 <= self._current_idx < self._list.count():
            self._list.item(self._current_idx).setText(
                self._display_name(self._remaps[self._current_idx]))
        self._update_src_btn()

    def _on_row_changed(self, row: int):
        if self._capturing:
            self._stop_capture()
        self._pull_editor()
        self._current_idx = row
        if 0 <= row < len(self._remaps):
            self._load_to_editor(self._remaps[row])
        else:
            self._current_idx = -1
        self._update_editor_visibility()
        self._update_src_btn()

    def _load_to_editor(self, r: dict):
        dst = str(r.get('dst', '') or '')
        self._dst_input.tags = [p.strip() for p in dst.split('+') if p.strip()]
        self._dst_input._build_tags()
        self._current_mode = r.get('mode', 'hold')
        if self._current_mode not in self._mode_btns:
            self._current_mode = 'hold'
        self._update_mode_styles()
        self._row_enable_cb.setChecked(r.get('enabled', True))

    def _pull_editor(self):
        if not (0 <= self._current_idx < len(self._remaps)):
            return
        r = self._remaps[self._current_idx]
        r['dst'] = self._dst_input.get_value()
        r['mode'] = self._current_mode
        r['enabled'] = self._row_enable_cb.isChecked()

    def _on_add(self):
        new = {'src': '', 'dst': '', 'mode': 'hold', 'enabled': True}
        self._remaps.append(new)
        self._list.addItem(self._display_name(new))
        self._list.setCurrentRow(len(self._remaps) - 1)
        # 新建即进入捕获, 少点一次
        self._on_capture_clicked()

    def _on_delete(self):
        if not (0 <= self._current_idx < len(self._remaps)):
            return
        if self._capturing:
            self._stop_capture()
        idx = self._current_idx
        self._list.blockSignals(True)
        self._remaps.pop(idx)
        self._list.takeItem(idx)
        self._list.blockSignals(False)
        if self._remaps:
            self._list.setCurrentRow(min(idx, len(self._remaps) - 1))
        else:
            self._current_idx = -1
            self._update_editor_visibility()

    # ── Save ──

    def _on_save(self):
        if self._capturing:
            self._stop_capture()
        self._pull_editor()
        # 丢弃没配全的空行 (src 或 dst 缺一不可)
        self._result = [dict(r) for r in self._remaps
                        if (r.get('src') or '').strip() and (r.get('dst') or '').strip()]
        self.settings_saved.emit()
        self.accept()

    def get_result(self):
        return {
            'key_remaps': getattr(self, '_result', []),
            'key_remap_enabled': self._enabled,
        }

    def reject(self):
        if self._capturing:
            self._stop_capture()
        super().reject()

    def closeEvent(self, event):
        if self._capturing:
            self._stop_capture()
        super().closeEvent(event)

    # ── 位置 / 拖拽 ──

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        ps = QApplication.primaryScreen()
        screen = ps.geometry() if ps else QRect(0, 0, 1920, 1080)
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
