"""
TEGG Touch 蛋挞 (PyQt6) - gp_wheel_mouse_dialog.py
方向盘 "其他鼠标按键" 配置弹窗 — 双栏布局 (940×720):
  左栏 (440px): 7 个鼠标动作字段 (lclick/rclick/mclick/x1/x2/wheelup/wheeldown)
                每个字段右侧显示「被 LT/RT 占用 不生效」提示 (动态根据扳机 mode 计算)
  右栏 (440px): 键位面板 (手柄按键 / 自定义宏 两 tab) — 跟 gp_stick_editor 同一套
"""

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QWidget,
    QApplication, QScrollArea, QStackedWidget,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from core.i18n import t, get_font
from core.constants import (
    APP_DIR, GP_BUTTONS, GP_LABEL_TO_KEY, GP_KEY_PREFIX,
    ACTION_COLORS,
    C_PM_BG, C_GRAY, C_GRAY_H, C_CYBER, C_CYBER_H, C_CLOSE, C_CLOSE_H,
    C_CAT_LABEL,
)
from views.button_editor_dialog import (
    TagInput, _FlowWidget, _ColorDot, _make_font, _detect_icon_font, _ICON_FONT,
)


_C_BG = C_PM_BG
_C_BORDER = "#444"
_C_BLUE = "#3B82F6"
_C_BLUE_H = "#60A5FA"
_C_TEXT = "#E0E0E0"
_C_HINT = "#888"
_C_MACRO = "#8B5CF6"
_C_WARN = "#F59E0B"   # 「不生效」提示用琥珀色, 不那么刺激


def _font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


def _compute_occupied(data) -> dict:
    """根据 LT/RT 的 mode + marker_button 算出哪些鼠标动作字段会被占用 (不生效)。
    返回 {field_name: reason_str}, 没占的不在 dict 里"""
    occupied: dict = {}
    for prefix, side_name in (('lt', '左扳机'), ('rt', '右扳机')):
        mode = getattr(data, f'{prefix}_mode', '')
        if mode == 'buttons':
            # buttons 模式占左右键
            for f in ('lclick', 'rclick'):
                occupied.setdefault(f, f"{side_name}「左右键」模式占用")
        elif mode == 'marker':
            btn = getattr(data, f'{prefix}_marker_button', 'L')
            f = 'lclick' if btn == 'L' else 'rclick'
            occupied.setdefault(f, f"{side_name}「浮标点击」用了{('左' if btn == 'L' else '右')}键")
        elif mode == 'scroll':
            for f in ('wheelup', 'wheeldown'):
                occupied.setdefault(f, f"{side_name}「滚轮」模式占用")
        # vertical 不占任何鼠标键
    return occupied


class GpWheelMouseDialog(QDialog):
    """方向盘 其他鼠标按键 配置弹窗 — 双栏布局"""

    saved = pyqtSignal(object)   # 保存时发出 (wheel item), 主编辑器可监听刷新

    LEFT_W = 440
    RIGHT_W = 440
    PADDING = 20
    WIN_W = LEFT_W + RIGHT_W + PADDING * 2 + 20    # 940
    WIN_H = 720

    def __init__(self, item, parent=None, gp_macros=None):
        super().__init__(parent)
        self._item = item
        self.data = item.data
        self._focus_widget = None
        self._tag_inputs: dict[str, TagInput] = {}
        self._macros = list(gp_macros) if gp_macros else []
        self._occupied = _compute_occupied(self.data)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        _detect_icon_font()
        self._init_ui()
        self._center_on_screen()
        self._drag_pos = None

    # ── 主 UI ──

    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("gpwm_container")
        container.setStyleSheet(f"""
            QFrame#gpwm_container {{
                background: {_C_BG}; border-radius: 4px; border: 1px solid {_C_BORDER};
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # 标题 + 关闭
        title_row = QHBoxLayout()
        title = QLabel("方向盘 — 其他鼠标按键配置")
        title.setFont(_font(fn, 18, bold=True))
        title.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title)
        title_row.addStretch()
        close_icon = "\uE711" if _ICON_FONT else "\u2715"
        close_btn = QPushButton(close_icon)
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setFont(_font(_ICON_FONT, 20))
        else:
            close_btn.setFont(_font(fn, 18, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # 提示
        tip = QLabel(
            f'<div style="line-height:170%">'
            f'方向盘 active (鼠标在方块内) 时, 配置的鼠标按键 → 触发对应映射。'
            f'<br>优先级低于 LT/RT: 若扳机模式占用某键, 此处的配置会显示<b style="color:{_C_WARN}">「不生效」</b>。'
            f'</div>')
        tip.setTextFormat(Qt.TextFormat.RichText)
        tip.setFont(_font(fn, 13))
        tip.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addSpacing(14)

        # 双栏 (中间加竖直分隔线)
        cols = QHBoxLayout()
        cols.setSpacing(0)
        cols.addLayout(self._build_left(fn), 0)
        cols.addSpacing(14)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: #444; border: none;")
        cols.addWidget(sep)
        cols.addSpacing(14)
        cols.addWidget(self._build_right(fn), 1)
        root.addLayout(cols, 1)

        # 底部按钮
        root.addSpacing(12)
        root.addLayout(self._build_bottom_buttons(fn))

    # ── 左栏: 7 个鼠标动作字段 ──

    def _build_left(self, fn):
        outer = QVBoxLayout()
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setFixedWidth(self.LEFT_W)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; border: none; }
            QScrollBar::handle:vertical { background: #404040; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 12, 0)
        v.setSpacing(0)

        action_fields = [
            ('lclick',     '左键'),
            ('rclick',     '右键'),
            ('mclick',     '中键'),
            ('xbutton1',   '侧键 X1'),
            ('xbutton2',   '侧键 X2'),
            ('wheelup',    '滚轮 ↑'),
            ('wheeldown',  '滚轮 ↓'),
        ]
        for i, (field, label) in enumerate(action_fields):
            if i > 0:
                v.addSpacing(10)
            v.addLayout(self._build_field_row(fn, field, label))

        v.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        return outer

    def _build_field_row(self, fn, field_name, label_text):
        """鼠标动作字段一行: 色点 + 标签 + TagInput; 若该字段被 LT/RT 占用, 下方加红字「不生效」"""
        accent = ACTION_COLORS.get(field_name, _C_BLUE)
        col = QVBoxLayout()
        col.setSpacing(2)
        # 主行
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addWidget(_ColorDot(accent))
        lbl = QLabel(label_text)
        lbl.setFont(_font(fn, 14))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setFixedWidth(80)
        row.addWidget(lbl)
        row.addSpacing(8)
        # 取 wheel.data.mouse_<field> (注意 prefix 是 mouse_)
        initial = getattr(self.data, f'mouse_{field_name}', '') or ''
        ti = TagInput(initial, accent_color=accent)
        ti.focusChanged.connect(self._on_focus_changed)
        self._tag_inputs[field_name] = ti
        row.addWidget(ti, 1)
        col.addLayout(row)
        # 占用提示 (右对齐)
        if field_name in self._occupied:
            warn = QLabel(f"⚠ 不生效: {self._occupied[field_name]}")
            warn.setFont(_font(fn, 11))
            warn.setStyleSheet(f"color: {_C_WARN}; background: transparent;")
            warn.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            warn.setContentsMargins(0, 0, 6, 0)
            col.addWidget(warn)
        return col

    # ── 右栏: 键位面板 ──

    def _build_right(self, fn):
        wrap = QFrame()
        wrap.setFixedWidth(self.RIGHT_W)
        wrap.setStyleSheet("background: transparent;")
        wlay = QVBoxLayout(wrap)
        wlay.setContentsMargins(0, 0, 0, 0)
        wlay.setSpacing(8)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self._tab_keys_btn = QPushButton("手柄按键")
        self._tab_macros_btn = QPushButton("自定义宏")
        for b in (self._tab_keys_btn, self._tab_macros_btn):
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(_font(fn, 14, bold=True))
        self._tab_keys_btn.clicked.connect(lambda: self._switch_tab(0))
        self._tab_macros_btn.clicked.connect(lambda: self._switch_tab(1))
        tab_row.addWidget(self._tab_keys_btn)
        tab_row.addWidget(self._tab_macros_btn)
        tab_row.addStretch()
        wlay.addLayout(tab_row)

        self._tab_stack = QStackedWidget()
        self._tab_stack.setStyleSheet("background: transparent;")
        self._tab_stack.addWidget(self._build_gp_keys_tab(fn))
        self._tab_stack.addWidget(self._build_gp_macros_tab(fn))
        wlay.addWidget(self._tab_stack, 1)
        self._switch_tab(0)
        return wrap

    def _build_gp_keys_tab(self, fn):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; border: none; }
            QScrollBar::handle:vertical { background: #404040; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)
        cat = QLabel(f"── 手柄按键 ──")
        cat.setFont(_font(fn, 14, bold=True))
        cat.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        lay.addWidget(cat)
        lay.addSpacing(8)
        labels = [label for _, label in GP_BUTTONS]
        flow = _FlowWidget(labels, self._on_gp_key_clicked, fn)
        lay.addWidget(flow)
        lay.addStretch()
        scroll.setWidget(body)
        return scroll

    def _build_gp_macros_tab(self, fn):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cat = QLabel("── 自定义手柄宏 ──")
        cat.setFont(_font(fn, 14, bold=True))
        cat.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        cat.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(cat)

        self._macro_list = QListWidget()
        self._macro_list.setStyleSheet(f"""
            QListWidget {{ background: {_C_BG}; border: none; outline: none; }}
            QListWidget::item {{ background: transparent; padding: 0px; border: none; }}
            QListWidget::item:selected {{ background: transparent; }}
            QListWidget::item:hover {{ background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; border: none; }}
            QScrollBar::handle:vertical {{ background: #404040; border-radius: 4px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        lay.addWidget(self._macro_list, 1)

        hint = QLabel("手柄宏需要在主设置里管理")
        hint.setFont(_font(fn, 11))
        hint.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        hint.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(hint)

        QTimer.singleShot(0, self._rebuild_macro_list)
        return page

    def _rebuild_macro_list(self):
        fn = get_font()
        self._macro_list.clear()
        if not self._macros:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 80))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._macro_list.addItem(item)
            empty = QLabel("(还没有手柄宏)")
            empty.setFont(_font(fn, 13))
            empty.setStyleSheet("color: #666; background: transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self._macro_list.setItemWidget(item, empty)
            return
        for m in self._macros:
            name = m.get('name', '')
            row = QFrame()
            row.setFixedHeight(40)
            row.setObjectName("gpwmmac_row")
            row.setStyleSheet(f"""
                QFrame#gpwmmac_row {{ background: {C_GRAY}; border-radius: 6px; }}
                QFrame#gpwmmac_row:hover {{ background: {_C_MACRO}; }}
            """)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            rl = QHBoxLayout(row); rl.setContentsMargins(15, 0, 10, 0); rl.setSpacing(6)
            lbl = QLabel(name)
            lbl.setFont(_font(fn, 14))
            lbl.setStyleSheet("color: white; background: transparent;")
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            rl.addWidget(lbl, 1)
            row.mousePressEvent = lambda e, n=name: self._insert_macro_tag(n)
            it = QListWidgetItem(); it.setSizeHint(QSize(0, 50))
            self._macro_list.addItem(it)
            self._macro_list.setItemWidget(it, row)

    def _switch_tab(self, idx):
        self._tab_stack.setCurrentIndex(idx)
        sel = f"""QPushButton {{
            background: transparent; color: #FFF; border: none;
            border-bottom: 2px solid {C_CYBER_H};
            border-radius: 0; padding: 0 14px 4px 14px;
        }}"""
        off = f"""QPushButton {{
            background: transparent; color: #AAA; border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0; padding: 0 14px 4px 14px;
        }} QPushButton:hover {{ color: #E0E0E0; }}"""
        self._tab_keys_btn.setStyleSheet(sel if idx == 0 else off)
        self._tab_macros_btn.setStyleSheet(sel if idx == 1 else off)

    # ── 面板点击 / 焦点 ──

    def _on_gp_key_clicked(self, label):
        storage = GP_LABEL_TO_KEY.get(label, label)
        self._insert_to_focused(GP_KEY_PREFIX + storage)

    def _insert_macro_tag(self, macro_name):
        self._insert_to_focused(f"gpmacro:{macro_name}")

    def _insert_to_focused(self, tag: str):
        w = self._focus_widget
        if w and isinstance(w, TagInput):
            w.add_tag(tag)
        else:
            ti = self._tag_inputs.get('lclick')
            if ti is not None:
                ti.add_tag(tag)

    def _on_focus_changed(self, widget):
        self._focus_widget = widget

    # ── 底部按钮 ──

    def _build_bottom_buttons(self, fn):
        r = QHBoxLayout()
        r.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFont(_font(fn, 16))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_GRAY}; color: #E0E0E0; border: none; border-radius: 6px; padding: 0 24px; }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        r.addWidget(cancel_btn)
        r.addSpacing(10)
        save_btn = QPushButton("保存")
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_font(fn, 16, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CYBER}; color: #FFF; border: none; border-radius: 6px; padding: 0 32px; }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        r.addWidget(save_btn)
        return r

    def _on_save(self):
        for field, ti in self._tag_inputs.items():
            value = ti.get_value() if hasattr(ti, 'get_value') else ''
            setattr(self.data, f'mouse_{field}', value)
        self.saved.emit(self._item)
        self.accept()

    # ── 定位 + 拖拽 ──

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

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
