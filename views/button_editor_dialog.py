"""
TEGG Touch 蛋挞 (PyQt6) - button_editor_dialog.py
按钮编辑弹窗 — 双栏布局: 左侧表单 + 右侧键位面板，匹配原版 Tkinter。

原版布局 (920×960):
  左栏 340px: 名称 | Hover | 延迟滑块 × 2 | 鼠标键位 × 7 | Copy/Delete/Save
  右栏 560px: 滚动键位面板 (10分类, flow 布局)
"""

import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QLabel, QSlider, QPushButton, QWidget,
    QScrollArea, QFrame, QSizePolicy, QApplication, QMessageBox,
    QStackedWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush

from core.i18n import t, get_font
from models.button_model import ButtonData

# ── 颜色常量 ──
C_PM_BG = "#2D2D2D"
C_GRAY = "#3A3A3A"
C_GRAY_H = "#505050"
C_AMBER = "#F59E0B"
C_CYBER = "#0C4A6E"
C_CYBER_H = "#0284C7"
C_CLOSE = "#6E1E1E"
C_CLOSE_H = "#8B2020"

C_INPUT_BG = "#3A3A3A"
C_TAG_BG = "#404040"
C_TAG_HOVER = "#555555"
C_TAG_TEXT = "#E0E0E0"
C_CAT_LABEL = "#888888"
C_DELAY = "#0284C7"

# 字段对应的强调色
ACTION_COLORS = {
    'name':      '#F59E0B',
    'hover':     '#0284C7',
    'lclick':    '#F59E0B',
    'rclick':    '#10B981',
    'mclick':    '#A855F7',
    'wheelup':   '#EC4899',
    'wheeldown': '#F43F5E',
    'xbutton1':  '#06B6D4',
    'xbutton2':  '#8B5CF6',
}

# 键位面板分类
KEY_CATEGORIES = [
    (t("key_cat.letters"), [chr(c) for c in range(ord('a'), ord('z') + 1)]),
    (t("key_cat.numbers"), [str(i) for i in range(10)]),
    (t("key_cat.fkeys"), [f"f{i}" for i in range(1, 13)]),
    (t("key_cat.arrows"), ["up", "down", "left", "right"]),
    (t("key_cat.modifiers"), ["ctrl", "shift", "alt", "windows", "caps lock", "menu"]),
    (t("key_cat.functions"), ["space", "enter", "esc", "tab", "backspace"]),
    (t("key_cat.punctuation"), [",", ".", "/", ";", "'", "[", "]", "\\", "-", "=", "`"]),
    (t("key_cat.other"), ["home", "end", "pageup", "pagedown", "insert", "delete",
                           "print screen", "scroll lock", "pause"]),
    (t("key_cat.numpad"), [f"num {i}" for i in range(10)] + ["num lock",
                            "num *", "num +", "num -", "num /", "num .", "num enter"]),
    (t("key_cat.media"), ["play/pause media", "stop media", "next track", "previous track",
                           "volume up", "volume down", "volume mute"]),
]


def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── 图标字体检测 ──
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


# ═══════════════════════════════════════════════════════════════
# TagInput — 标签式输入（替代 QLineEdit 用于键位字段）
# ═══════════════════════════════════════════════════════════════

class TagInput(QWidget):
    """Tag 输入控件: 显示彩色标签，点击面板添加，BackSpace 删除。"""

    focusChanged = pyqtSignal(object)

    def __init__(self, initial_value="", accent_color="#F59E0B", parent=None):
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


# ═══════════════════════════════════════════════════════════════
# FlowLayout — 自适应换行布局 (用于键位面板)
# ═══════════════════════════════════════════════════════════════

class _FlowLayout(QVBoxLayout):
    """Simplified flow layout: builds rows of QHBoxLayouts."""
    pass


# ═══════════════════════════════════════════════════════════════
# ColorDot — 8×8 彩色圆点 (字段左侧标识)
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# FocusLineEdit — 带焦点跟踪和强调色的 QLineEdit
# ═══════════════════════════════════════════════════════════════

class _FocusLineEdit(QLineEdit):
    focusChanged = pyqtSignal(object)

    def __init__(self, text="", accent="#F59E0B", parent=None):
        super().__init__(text, parent)
        self._accent = accent
        self._update_border(False)

    def _update_border(self, focused):
        bc = self._accent if focused else "#555"
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid {bc}; border-radius: 6px;
                padding: 4px 8px; font-size: 13px;
            }}
        """)

    def focusInEvent(self, event):
        self._update_border(True)
        self.focusChanged.emit(self)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._update_border(False)
        super().focusOutEvent(event)


# ═══════════════════════════════════════════════════════════════
# ButtonEditorDialog — 主弹窗
# ═══════════════════════════════════════════════════════════════

class ButtonEditorDialog(QDialog):
    """按钮编辑弹窗 — 双栏布局匹配原版"""

    saved = pyqtSignal(object)
    deleted = pyqtSignal(object)
    copied = pyqtSignal(object)
    macros_changed = pyqtSignal(list)  # 宏列表变更时发出

    LEFT_W = 340
    RIGHT_W = 560
    PADDING = 20
    WIN_W = LEFT_W + RIGHT_W + PADDING * 2 + 20  # 940
    WIN_H = 960

    MAX_MACROS = 20
    C_MACRO = "#8B5CF6"  # 宏 tag 紫色

    def __init__(self, item, parent=None, macros=None):
        super().__init__(parent)
        self._item = item
        self.data = item.data
        self._focus_widget = None  # 当前聚焦的输入控件
        self._is_wheel = not hasattr(self.data, 'btn_type')
        self._macros = list(macros) if macros else []
        self._macro_manage_mode = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        self._init_ui()
        self._center_on_screen()
        self._drag_pos = None

    # ── 拖拽 ──────────────────────────────────────────────────

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

    def _init_ui(self):
        fn = get_font()

        # ── 容器 (带背景) ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("be_container")
        container.setStyleSheet(f"""
            QFrame#be_container {{
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
        title_lbl = QLabel(t("editor.title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        _detect_icon_font()
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

        # ── 提示文字 ──
        tip = QLabel(t("editor.tip"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)

        root.addSpacing(20)

        # ── 双栏 ──
        columns = QHBoxLayout()
        columns.setSpacing(0)

        # ════ 左栏: 表单 ════
        left = QVBoxLayout()
        left.setSpacing(0)
        left.setContentsMargins(0, 0, 0, 0)

        self._fields = {}

        # -- Block 1: 名称 (Entry, 无色点) --
        left.addLayout(self._build_field_row(
            fn, 'name', t("editor.name"), self.data.name, is_tag=False, show_dot=False))

        # ── 分割线: 名称 / 悬停 ──
        left.addSpacing(20)
        sep1 = QFrame()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background: #444;")
        left.addWidget(sep1)
        left.addSpacing(20)

        # -- Block 2: Hover (TagInput) --
        left.addLayout(self._build_field_row(
            fn, 'hover', t("editor.hover"), self.data.hover, is_tag=True))
        left.addSpacing(14)

        # -- 延迟滑块: hover_delay --
        left.addLayout(self._build_delay_slider(
            fn, t("editor.hover_delay"), self.data.hover_delay, 'hover_delay'))
        left.addSpacing(14)

        # -- 延迟滑块: hover_release_delay --
        left.addLayout(self._build_delay_slider(
            fn, t("editor.hover_release_delay"), self.data.hover_release_delay, 'release_delay'))

        # ── 分割线: 延迟 / 鼠标键位 ──
        left.addSpacing(20)
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #444;")
        left.addWidget(sep2)
        left.addSpacing(20)

        # -- Block 3: 鼠标键位 (7 fields, all TagInput) --
        mouse_fields = [
            ('lclick', t("editor.lclick")),
            ('rclick', t("editor.rclick")),
            ('mclick', t("editor.mclick")),
            ('xbutton1', t("editor.xbutton1")),
            ('xbutton2', t("editor.xbutton2")),
            ('wheelup', t("editor.wheelup")),
            ('wheeldown', t("editor.wheeldown")),
        ]
        for i, (field, label) in enumerate(mouse_fields):
            left.addLayout(self._build_field_row(
                fn, field, label, getattr(self.data, field, ''), is_tag=True))
            if i < len(mouse_fields) - 1:
                left.addSpacing(8)

        left.addStretch()

        # -- 底部按钮 --
        left.addLayout(self._build_bottom_buttons(fn))

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

        # ════ 右栏: Tab 切换 (常规按键 / 自定义宏) ════
        right = self._build_right_tabbed_panel(fn)
        columns.addWidget(right, 1)

        root.addLayout(columns, 1)

    # ── 表单行构建 ────────────────────────────────────────────

    def _build_field_row(self, fn, field_name, label_text, value, is_tag=True, show_dot=True):
        """构建一行: 色点 + 标签 + 输入框"""
        row = QHBoxLayout()
        row.setSpacing(0)

        accent = ACTION_COLORS.get(field_name, C_AMBER)

        # 色点
        if show_dot:
            dot = _ColorDot(accent)
            row.addWidget(dot)

        # 标签
        lbl = QLabel(label_text)
        lbl.setFont(_make_font(fn, 16))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setFixedWidth(80)
        row.addWidget(lbl)

        row.addSpacing(10)

        # 输入控件
        if is_tag:
            widget = TagInput(initial_value=value, accent_color=accent)
            widget.focusChanged.connect(self._on_focus_changed)
        else:
            widget = _FocusLineEdit(text=value, accent=accent)
            widget.setFont(_make_font(fn, 13))
            widget.setFixedHeight(42)
            widget.focusChanged.connect(self._on_focus_changed)

        self._fields[field_name] = widget
        row.addWidget(widget, 1)

        return row

    def _build_delay_slider(self, fn, label_text, value, key):
        """构建延迟滑块: 色点 + 标签 + Entry + ms + Slider"""
        col = QVBoxLayout()
        col.setSpacing(4)

        # Row 1: dot + label + entry + ms
        r1 = QHBoxLayout()
        r1.setSpacing(0)

        dot = _ColorDot(C_DELAY)
        r1.addWidget(dot)

        lbl = QLabel(label_text)
        lbl.setFont(_make_font(fn, 16))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        r1.addWidget(lbl)

        r1.addStretch()

        entry = QLineEdit(str(value))
        entry.setFixedSize(80, 28)
        entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        entry.setFont(_make_font(fn, 13))
        entry.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: {C_DELAY};
                border: 1px solid #555; border-radius: 4px;
            }}
            QLineEdit:focus {{ border-color: {C_DELAY}; }}
        """)
        r1.addWidget(entry)

        r1.addSpacing(10)

        ms_lbl = QLabel("ms")
        ms_lbl.setFont(_make_font(fn, 16))
        ms_lbl.setStyleSheet("color: #888; background: transparent;")
        r1.addWidget(ms_lbl)

        col.addLayout(r1)

        # Row 2: slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 1000)
        slider.setValue(value)
        slider.setSingleStep(10)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: #404040; height: 8px; border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {C_DELAY}; border-radius: 4px;
            }}
            QSlider::add-page:horizontal {{
                background: #404040; border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #DDD; border: none;
                width: 16px; height: 16px; margin: -4px 0; border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {C_DELAY};
            }}
        """)

        # 双向同步
        def _slider_to_entry(v):
            v = round(v / 10) * 10
            entry.setText(str(v))

        def _entry_to_slider():
            try:
                v = max(0, int(entry.text()))
                slider.setValue(min(1000, v))
            except ValueError:
                pass

        slider.valueChanged.connect(_slider_to_entry)
        entry.editingFinished.connect(_entry_to_slider)

        col.addWidget(slider)

        # 存储引用
        if key == 'hover_delay':
            self._hover_delay_slider = slider
            self._hover_delay_entry = entry
        else:
            self._release_delay_slider = slider
            self._release_delay_entry = entry

        return col

    # ── 键位面板 ──────────────────────────────────────────────

    def _build_key_palette(self, fn):
        """构建右侧可滚动键位面板"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent; border: none;
            }
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

        for i, (cat_name, keys) in enumerate(KEY_CATEGORIES):
            # 分类标签
            if i > 0:
                layout.addSpacing(20)
            cat_lbl = QLabel(f"── {cat_name} ──")
            cat_lbl.setFont(_make_font(fn, 14, bold=True))
            cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
            layout.addWidget(cat_lbl)
            layout.addSpacing(8)

            # 键位按钮 (flow layout via wrapping rows)
            flow = self._build_flow_keys(fn, keys)
            layout.addWidget(flow)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_flow_keys(self, fn, keys):
        """构建 flow 布局的键位按钮"""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        flow = _FlowWidget(keys, self._on_key_clicked, fn, container)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(flow)
        return container

    def _on_key_clicked(self, key_name):
        """键位面板点击 → 插入到聚焦的输入控件"""
        w = self._focus_widget
        if w is None:
            return
        if isinstance(w, TagInput):
            w.add_tag(key_name)
        elif isinstance(w, (_FocusLineEdit, QLineEdit)):
            w.insert(key_name)

    def _on_focus_changed(self, widget):
        self._focus_widget = widget

    # ── 底部按钮 ──────────────────────────────────────────────

    def _build_bottom_buttons(self, fn):
        col = QVBoxLayout()
        col.setSpacing(8)

        # Row 1: Copy (全宽) — 始终显示
        copy_btn = QPushButton(t("editor.copy"))
        copy_btn.setFixedHeight(40)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(_make_font(fn, 18))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        copy_btn.clicked.connect(self._on_copy)
        col.addWidget(copy_btn)

        # Row 2: Delete | Save
        r2 = QHBoxLayout()
        r2.setSpacing(10)

        del_btn = QPushButton(t("editor.delete"))
        del_btn.setFixedHeight(40)
        del_btn.setFont(_make_font(fn, 18))
        if self._is_wheel:
            # 轮盘项: 删除按钮显示但禁用（灰色）
            del_btn.setEnabled(False)
            del_btn.setStyleSheet("""
                QPushButton {
                    background: #3A3A3A; color: #666666;
                    border: none; border-radius: 6px;
                }
            """)
        else:
            # 普通按钮: 正常红色删除按钮
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C_CLOSE}; color: #FFF;
                    border: none; border-radius: 6px;
                }}
                QPushButton:hover {{ background: {C_CLOSE_H}; }}
            """)
            del_btn.clicked.connect(self._on_delete)
        r2.addWidget(del_btn)

        save_btn = QPushButton(t("editor.save"))
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
        r2.addWidget(save_btn)

        col.addLayout(r2)
        return col

    # ── 回调 ──────────────────────────────────────────────────

    def _on_save(self):
        # 名称
        name_w = self._fields.get('name')
        if isinstance(name_w, _FocusLineEdit):
            self.data.name = name_w.text()

        # 键位字段
        for field in ('hover', 'lclick', 'rclick', 'mclick',
                      'xbutton1', 'xbutton2', 'wheelup', 'wheeldown'):
            w = self._fields.get(field)
            if isinstance(w, TagInput):
                setattr(self.data, field, w.get_value())

        # 延迟 — 从 entry 读取，允许超过 slider 上限 1000
        try:
            self.data.hover_delay = max(0, int(self._hover_delay_entry.text()))
        except ValueError:
            self.data.hover_delay = self._hover_delay_slider.value()
        try:
            self.data.hover_release_delay = max(0, int(self._release_delay_entry.text()))
        except ValueError:
            self.data.hover_release_delay = self._release_delay_slider.value()

        # 更新状态机
        if hasattr(self._item, '_hover_sm'):
            self._item._hover_sm.update_delays(
                self.data.hover_delay, self.data.hover_release_delay)

        self._item.update()
        self.saved.emit(self.data)
        self.accept()

    def _on_delete(self):
        self.deleted.emit(self._item)
        self.accept()

    def _on_copy(self):
        self.copied.emit(self._item)
        self.accept()

    # ── 右栏 Tab 面板 ────────────────────────────────────────

    def _build_right_tabbed_panel(self, fn):
        """构建右栏: Tab 切换 [常规按键] [自定义宏]"""
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(8)

        # Tab 按钮行
        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)

        self._tab_keys_btn = QPushButton(t("macro.tab_keys"))
        self._tab_keys_btn.setFixedHeight(34)
        self._tab_keys_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_keys_btn.setFont(_make_font(fn, 14, bold=True))
        self._tab_keys_btn.clicked.connect(lambda: self._switch_tab(0))
        tab_row.addWidget(self._tab_keys_btn)

        self._tab_macros_btn = QPushButton(t("macro.tab_macros"))
        self._tab_macros_btn.setFixedHeight(34)
        self._tab_macros_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_macros_btn.setFont(_make_font(fn, 14, bold=True))
        self._tab_macros_btn.clicked.connect(lambda: self._switch_tab(1))
        tab_row.addWidget(self._tab_macros_btn)

        tab_row.addStretch()
        panel_lay.addLayout(tab_row)

        # Stacked widget
        self._tab_stack = QStackedWidget()
        self._tab_stack.setStyleSheet("background: transparent;")

        # Page 0: 常规按键
        self._tab_stack.addWidget(self._build_key_palette(fn))

        # Page 1: 自定义宏
        self._tab_stack.addWidget(self._build_macro_tab(fn))

        panel_lay.addWidget(self._tab_stack, 1)

        self._switch_tab(0)
        return panel

    def _switch_tab(self, idx):
        self._tab_stack.setCurrentIndex(idx)
        sel_style = f"""QPushButton {{
            background: {C_CYBER}; color: #FFF;
            border: none; border-radius: 6px; padding: 0 14px;
        }} QPushButton:hover {{ background: {C_CYBER_H}; }}"""
        off_style = f"""QPushButton {{
            background: #404040; color: #E0E0E0;
            border: none; border-radius: 6px; padding: 0 14px;
        }} QPushButton:hover {{ background: #505050; }}"""
        self._tab_keys_btn.setStyleSheet(sel_style if idx == 0 else off_style)
        self._tab_macros_btn.setStyleSheet(sel_style if idx == 1 else off_style)

    # ── 宏 Tab ────────────────────────────────────────────────

    def _build_macro_tab(self, fn):
        """构建自定义宏 Tab: 宏 tag 列表 + 管理/退出按钮"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)

        # 宏 tag 滚动区域
        self._macro_scroll = QScrollArea()
        self._macro_scroll.setWidgetResizable(True)
        self._macro_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._macro_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; border: none;
            }
            QScrollBar::handle:vertical {
                background: #404040; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        self._macro_tag_container = QWidget()
        self._macro_tag_container.setStyleSheet("background: transparent;")
        self._macro_tag_layout = QVBoxLayout(self._macro_tag_container)
        self._macro_tag_layout.setContentsMargins(0, 0, 0, 0)
        self._macro_tag_layout.setSpacing(0)

        # flow 容器 (会被 _rebuild_macro_tags 填充)
        self._macro_flow_host = QWidget()
        self._macro_flow_host.setStyleSheet("background: transparent;")
        self._macro_tag_layout.addWidget(self._macro_flow_host)
        self._macro_tag_layout.addStretch()

        self._macro_scroll.setWidget(self._macro_tag_container)
        lay.addWidget(self._macro_scroll, 1)

        lay.addSpacing(8)

        # 管理 / 退出管理 按钮
        self._macro_manage_btn = QPushButton(t("macro.manage"))
        self._macro_manage_btn.setFixedHeight(36)
        self._macro_manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._macro_manage_btn.setFont(_make_font(fn, 14, bold=True))
        self._macro_manage_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        self._macro_manage_btn.clicked.connect(self._toggle_macro_manage)
        lay.addWidget(self._macro_manage_btn)

        self._rebuild_macro_tags()
        return page

    def _toggle_macro_manage(self):
        fn = get_font()
        self._macro_manage_mode = not self._macro_manage_mode
        if self._macro_manage_mode:
            self._macro_manage_btn.setText(t("macro.exit_manage"))
            self._macro_manage_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C_CYBER}; color: #FFF;
                    border: none; border-radius: 6px;
                }}
                QPushButton:hover {{ background: {C_CYBER_H}; }}
            """)
        else:
            self._macro_manage_btn.setText(t("macro.manage"))
            self._macro_manage_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C_GRAY}; color: #E0E0E0;
                    border: none; border-radius: 6px;
                }}
                QPushButton:hover {{ background: {C_GRAY_H}; }}
            """)
        self._rebuild_macro_tags()

    def _rebuild_macro_tags(self):
        """重建宏 tag 列表"""
        fn = get_font()
        # 清除旧内容
        old_lay = self._macro_flow_host.layout()
        if old_lay:
            while old_lay.count():
                item = old_lay.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
        else:
            old_lay = QVBoxLayout(self._macro_flow_host)
            old_lay.setContentsMargins(0, 0, 0, 0)
            old_lay.setSpacing(8)

        # 空状态
        if not self._macros and not self._macro_manage_mode:
            hint = QLabel(t("macro.no_macros_hint"))
            hint.setFont(_make_font(fn, 14))
            hint.setStyleSheet("color: #666; background: transparent;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            old_lay.addWidget(hint)
            return

        # flow 行
        flow_widget = QWidget()
        flow_widget.setStyleSheet("background: transparent;")
        flow_lay = QHBoxLayout(flow_widget)
        flow_lay.setContentsMargins(0, 0, 0, 0)
        flow_lay.setSpacing(8)

        for i, macro in enumerate(self._macros):
            name = macro.get('name', f'Macro {i+1}')
            if self._macro_manage_mode:
                # 管理模式: 编辑 + 名称 + 删除
                grp = QWidget()
                grp.setStyleSheet("background: transparent;")
                grp_lay = QHBoxLayout(grp)
                grp_lay.setContentsMargins(0, 0, 0, 0)
                grp_lay.setSpacing(2)

                edit_btn = QPushButton("✏")
                edit_btn.setFixedSize(28, 36)
                edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                edit_btn.setFont(_make_font(fn, 14))
                edit_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {self.C_MACRO}; color: #FFF;
                        border: none; border-radius: 4px 0 0 4px;
                    }}
                    QPushButton:hover {{ background: #7C3AED; }}
                """)
                edit_btn.clicked.connect(lambda _, idx=i: self._edit_macro(idx))
                grp_lay.addWidget(edit_btn)

                name_btn = QPushButton(name)
                name_btn.setFixedHeight(36)
                name_btn.setFont(_make_font(fn, 13, bold=True))
                name_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {self.C_MACRO}; color: #FFF;
                        border: none; padding: 0 8px;
                    }}
                """)
                name_btn.setEnabled(False)
                grp_lay.addWidget(name_btn)

                del_btn = QPushButton("✕")
                del_btn.setFixedSize(28, 36)
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                del_btn.setFont(_make_font(fn, 14, bold=True))
                del_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_CLOSE}; color: #FFF;
                        border: none; border-radius: 0 4px 4px 0;
                    }}
                    QPushButton:hover {{ background: {C_CLOSE_H}; }}
                """)
                del_btn.clicked.connect(lambda _, idx=i: self._delete_macro(idx))
                grp_lay.addWidget(del_btn)

                old_lay.addWidget(grp)
            else:
                # 浏览模式: 点击添加到 TagInput
                tag_btn = QPushButton(name)
                tag_btn.setFixedHeight(36)
                tag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                tag_btn.setFont(_make_font(fn, 13, bold=True))
                tag_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {self.C_MACRO}; color: #FFF;
                        border: none; border-radius: 6px;
                        padding: 0 12px;
                    }}
                    QPushButton:hover {{ background: #7C3AED; }}
                """)
                tag_btn.clicked.connect(lambda _, n=name: self._insert_macro_tag(n))
                old_lay.addWidget(tag_btn)

        # 管理模式: 新增按钮
        if self._macro_manage_mode and len(self._macros) < self.MAX_MACROS:
            new_btn = QPushButton(f"➕ {t('macro.new')}")
            new_btn.setFixedHeight(36)
            new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            new_btn.setFont(_make_font(fn, 13, bold=True))
            new_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #404040; color: #10B981;
                    border: 2px dashed #10B981; border-radius: 6px;
                    padding: 0 12px;
                }}
                QPushButton:hover {{ background: #505050; }}
            """)
            new_btn.clicked.connect(self._new_macro)
            old_lay.addWidget(new_btn)

    def _insert_macro_tag(self, macro_name):
        """浏览模式: 点击宏 → 添加 macro:name 到当前 TagInput"""
        w = self._focus_widget
        if w and isinstance(w, TagInput):
            w.add_tag(f"macro:{macro_name}")

    def _new_macro(self):
        from views.macro_editor_dialog import MacroEditorDialog
        dlg = MacroEditorDialog(parent=self)
        dlg.macro_saved.connect(lambda data: self._on_macro_editor_saved(data, -1))
        dlg.exec()

    def _edit_macro(self, idx):
        from views.macro_editor_dialog import MacroEditorDialog
        data = copy.deepcopy(self._macros[idx])
        dlg = MacroEditorDialog(macro_data=data, parent=self)
        dlg.macro_saved.connect(lambda d: self._on_macro_editor_saved(d, idx))
        dlg.exec()

    def _delete_macro(self, idx):
        name = self._macros[idx].get('name', '')
        msg = t("macro.confirm_delete").replace("{name}", name)
        reply = QMessageBox.question(
            self, t("macro.confirm_delete_title"), msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._macros.pop(idx)
            self._rebuild_macro_tags()
            self.macros_changed.emit(self._macros)

    def _on_macro_editor_saved(self, data, idx):
        if idx >= 0 and idx < len(self._macros):
            self._macros[idx] = data
        else:
            self._macros.append(data)
        self._rebuild_macro_tags()
        self.macros_changed.emit(self._macros)

    # ── 定位 ──────────────────────────────────────────────────

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)


# ═══════════════════════════════════════════════════════════════
# _FlowWidget — 自适应换行的键位按钮容器
# ═══════════════════════════════════════════════════════════════

class _FlowWidget(QWidget):
    """Flow layout: 根据容器宽度自动换行排列按钮。"""

    TAG_H = 40
    TAG_GAP_X = 8
    TAG_GAP_Y = 8
    TAG_PAD_X = 12
    TAG_MIN_W = 40

    def __init__(self, keys, on_click, fn, parent=None):
        super().__init__(parent)
        self._keys = keys
        self._on_click = on_click
        self._fn = fn
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
            # 根据文字宽度设置按钮宽度
            fm = btn.fontMetrics()
            text_w = fm.horizontalAdvance(key)
            btn.setFixedWidth(max(self.TAG_MIN_W, text_w + self.TAG_PAD_X * 2))
            btn.clicked.connect(lambda checked, k=key: self._on_click(k))
            self._buttons.append(btn)

        # 初始布局延迟到 resizeEvent（构造时宽度为 0）

    def _do_layout(self):
        if not self._buttons:
            return
        w = self.width()
        avail_w = w if w > 0 else 520
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

        total_h = y + self.TAG_H + 4
        self.setFixedHeight(total_h)

    def resizeEvent(self, event):
        self._do_layout()
        super().resizeEvent(event)
