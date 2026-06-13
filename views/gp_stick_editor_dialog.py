"""
TEGG Touch 蛋挞 (PyQt6) - gp_stick_editor_dialog.py
摇杆按钮编辑弹窗 — 左右双栏, 风格对齐 ButtonEditorDialog (940×960)
  左栏 (340px): 摇杆参数 (名称/ID/死区/释放/灵敏度/八向)
                + 鼠标其它按键 (lclick/rclick/mclick/xbutton1/xbutton2/wheelup/wheeldown)
                + 底部 Copy / Delete | Save 按钮
  右栏 (560px): 键位面板 (手柄按键 / 自定义宏 两个 tab)
"""

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QSlider, QPushButton, QFrame, QWidget,
    QApplication, QRadioButton, QButtonGroup, QCheckBox,
    QScrollArea, QStackedWidget, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush, QPolygon

from core.i18n import t, get_font
from core.constants import (
    STICK_ID_LEFT, STICK_ID_RIGHT, APP_DIR,
    GP_BUTTONS, GP_LABEL_TO_KEY, GP_KEY_PREFIX,
    ACTION_COLORS,
    C_PM_BG, C_GRAY, C_GRAY_H, C_CYBER, C_CYBER_H, C_CLOSE, C_CLOSE_H,
    C_INPUT_BG, C_TAG_BG, C_TAG_HOVER, C_TAG_TEXT, C_CAT_LABEL,
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
_C_DEFAULT_TEXT = "#AAAAAA"     # "默认值: X%" 灰白色
_C_MARK = "#CCCCCC"             # ▼ 三角 灰白色
_C_MACRO = "#8B5CF6"

# 默认值 (跟 GamepadStickData 同步)
_DEFAULT_DEAD_ZONE_PCT = 10
_DEFAULT_RELEASE_PCT = 150

# 图标资源
_CHECK_ICON_URL = os.path.join(APP_DIR, "assets", "check.svg").replace("\\", "/")
_RADIO_DOT_URL = os.path.join(APP_DIR, "assets", "radio_dot.svg").replace("\\", "/")


def _font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class _DefaultMarkedSlider(QSlider):
    """横向 slider, 上方画 ▼ 三角 标记默认值位置。
       当前值 == 默认值 → 三角变蓝; 否则灰白。
       CSS 必须配合: groove margin-top = TRACK_MARGIN_TOP, handle 默认 margin -5px 0。"""

    TRI_TOP = 4             # 三角 y 起点 (顶部留 4px)
    TRI_H = 8               # 三角高
    TRACK_MARGIN_TOP = 20   # groove top y (= TRI_TOP+TRI_H+8 buffer)
    # Total height = TRACK_MARGIN_TOP + groove(6) + handle 下溢(5) + 1 = 32
    WIDGET_H = 34

    def __init__(self, min_v: int, max_v: int, init: int, default_v: int, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(min_v, max_v)
        self.setValue(init)
        self._default = default_v
        self.setFixedHeight(self.WIDGET_H)
        # 值变 → 重画三角 (颜色可能切换)
        self.valueChanged.connect(lambda _v: self.update())

    def is_at_default(self) -> bool:
        return self.value() == self._default

    def paintEvent(self, event):
        super().paintEvent(event)
        rng = self.maximum() - self.minimum()
        if rng <= 0:
            return
        margin = 9
        usable_w = max(1, self.width() - 2 * margin)
        pct = (self._default - self.minimum()) / rng
        x = int(margin + pct * usable_w)

        color = _C_BLUE if self.is_at_default() else _C_MARK
        tri = QPolygon([
            QPoint(x - 5, self.TRI_TOP),
            QPoint(x + 5, self.TRI_TOP),
            QPoint(x, self.TRI_TOP + self.TRI_H),
        ])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawPolygon(tri)


class GpStickEditorDialog(QDialog):
    """摇杆编辑弹窗 — 双栏布局, 风格对齐 ButtonEditorDialog"""

    saved = pyqtSignal(object)
    deleted = pyqtSignal(object)
    copied = pyqtSignal(object)

    LEFT_W = 440
    RIGHT_W = 560
    PADDING = 20
    WIN_W = LEFT_W + RIGHT_W + PADDING * 2 + 20  # 1040
    WIN_H = 960

    def __init__(self, item, parent=None, gp_macros=None):
        super().__init__(parent)
        self._item = item
        self.data = item.data
        self._focus_widget = None
        self._tag_inputs: dict[str, TagInput] = {}
        self._macros = list(gp_macros) if gp_macros else []

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
        container.setObjectName("gpstick_container")
        container.setStyleSheet(f"""
            QFrame#gpstick_container {{
                background: {_C_BG}; border-radius: 4px; border: 1px solid {_C_BORDER};
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # 标题栏 + 关闭
        title_row = QHBoxLayout()
        title = QLabel(t("gp_stick_editor.title"))
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
        tip = QLabel(t("gp_stick_editor.tip"))
        tip.setFont(_font(fn, 14))
        tip.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addSpacing(16)

        # 双栏
        cols = QHBoxLayout()
        cols.setSpacing(20)
        cols.addLayout(self._build_left(fn), 0)
        cols.addWidget(self._build_right(fn), 1)
        root.addLayout(cols, 1)

    # ── 左栏 ──

    def _build_left(self, fn):
        outer = QVBoxLayout()
        outer.setSpacing(10)
        outer.setContentsMargins(0, 0, 0, 0)

        # 可滚动区域 (字段)
        scroll = QScrollArea()
        scroll.setFixedWidth(self.LEFT_W)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; border: none; }
            QScrollBar::handle:vertical { background: #404040; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        sc = QVBoxLayout(body)
        sc.setContentsMargins(0, 0, 12, 0)
        sc.setSpacing(0)

        SECTION_SPACING = 14   # 字段块间距

        # ─── 摇杆参数 ───
        sc.addWidget(self._section_label(fn, t("gp_stick_editor.section_params")))
        sc.addSpacing(6)

        # 名称
        sc.addLayout(self._build_name_row(fn))
        sc.addSpacing(SECTION_SPACING)

        # 摇杆 ID
        sc.addLayout(self._build_stick_id_row(fn))
        sc.addSpacing(SECTION_SPACING)

        # 死区
        sc.addLayout(self._build_slider_section(
            fn,
            field_label=t("gp_stick_editor.dead_zone"),
            value_attr='_dead_zone_lbl',
            slider_attr='_dead_zone_slider',
            min_v=5, max_v=30,
            init=int(self.data.dead_zone * 100),
            default_v=_DEFAULT_DEAD_ZONE_PCT,
            suffix='%',
            hint=t("gp_stick_editor.dead_zone_hint"),
            accent=_C_BLUE,
        ))
        sc.addSpacing(SECTION_SPACING)

        # 释放阈值
        sc.addLayout(self._build_slider_section(
            fn,
            field_label=t("gp_stick_editor.release_threshold"),
            value_attr='_release_lbl',
            slider_attr='_release_slider',
            min_v=120, max_v=200,
            init=int(self.data.release_threshold_ratio * 100),
            default_v=_DEFAULT_RELEASE_PCT,
            suffix='%',
            hint=t("gp_stick_editor.release_threshold_hint"),
            accent=_C_BLUE,
        ))
        sc.addSpacing(SECTION_SPACING)

        # 灵敏度
        sc.addLayout(self._build_sensitivity_row(fn))
        sc.addSpacing(SECTION_SPACING)

        # 八方向
        self._eight_chk = self._build_check(fn, t("gp_stick_editor.eight_way"))
        self._eight_chk.setChecked(bool(self.data.eight_way))
        sc.addWidget(self._eight_chk)
        sc.addSpacing(SECTION_SPACING + 6)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #444; border: none;")
        sep.setFixedHeight(1)
        sc.addWidget(sep)
        sc.addSpacing(SECTION_SPACING)

        # ─── 鼠标其它按键 ───
        sc.addWidget(self._section_label(fn, t("gp_stick_editor.section_mouse")))
        sc.addSpacing(4)
        mhint = QLabel(t("gp_stick_editor.mouse_hint"))
        mhint.setFont(_font(fn, 11))
        mhint.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        mhint.setWordWrap(True)
        sc.addWidget(mhint)
        sc.addSpacing(8)

        # 7 个 TagInput 字段 (含色点), 字段之间留间距
        action_fields = [
            ('lclick',    'gp_stick_editor.lclick'),
            ('rclick',    'gp_stick_editor.rclick'),
            ('mclick',    'gp_stick_editor.mclick'),
            ('xbutton1',  'gp_stick_editor.xbutton1'),
            ('xbutton2',  'gp_stick_editor.xbutton2'),
            ('wheelup',   'gp_stick_editor.wheelup'),
            ('wheeldown', 'gp_stick_editor.wheeldown'),
        ]
        for i, (field_name, loc_key) in enumerate(action_fields):
            if i > 0:
                sc.addSpacing(10)
            sc.addLayout(self._build_action_field_row(fn, field_name, t(loc_key)))

        sc.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # 底部按钮 (Copy / Delete | Save) - 跟 button editor 一致
        outer.addLayout(self._build_bottom_buttons(fn))
        return outer

    # ── 右栏: 键位面板 ──

    def _build_right(self, fn):
        wrap = QFrame()
        wrap.setFixedWidth(self.RIGHT_W)
        wrap.setStyleSheet("background: transparent;")
        wlay = QVBoxLayout(wrap)
        wlay.setContentsMargins(0, 0, 0, 0)
        wlay.setSpacing(8)

        # Tab 按钮
        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self._tab_keys_btn = QPushButton(t("gp_stick_editor.tab_keys"))
        self._tab_macros_btn = QPushButton(t("gp_stick_editor.tab_macros"))
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
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)

        cat = QLabel(f"── {t('key_cat.gp_buttons')} ──")
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

        cat = QLabel(f"── {t('gp_stick_editor.tab_macros_hdr')} ──")
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
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        lay.addWidget(self._macro_list, 1)

        hint = QLabel(t("gp_stick_editor.macros_manage_hint"))
        hint.setFont(_font(fn, 11))
        hint.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        hint.setWordWrap(True)
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
            empty = QLabel(t("gp_stick_editor.macros_empty"))
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
            row.setObjectName("gpsmac_row")
            row.setStyleSheet(f"""
                QFrame#gpsmac_row {{ background: {C_GRAY}; border-radius: 6px; }}
                QFrame#gpsmac_row:hover {{ background: {_C_MACRO}; }}
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

    # ── 字段构造 (跟 button editor 同模式: 色点 + 标签 + 输入) ──

    def _build_name_row(self, fn):
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(self._field_label(fn, t("gp_stick_editor.name")))
        self._name_edit = QLineEdit(self.data.name or "")
        self._name_edit.setPlaceholderText(t("gp_stick_editor.name_placeholder"))
        self._name_edit.setFont(_font(fn, 14))
        self._name_edit.setFixedHeight(36)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid #555; border-radius: 6px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border-color: {_C_BLUE}; }}
        """)
        col.addWidget(self._name_edit)
        return col

    def _build_stick_id_row(self, fn):
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(self._field_label(fn, t("gp_stick_editor.stick_id")))
        row = QHBoxLayout()
        self._id_group = QButtonGroup(self)
        self._rb_left = self._build_radio(fn, t("gp_stick_editor.left_stick"))
        self._rb_right = self._build_radio(fn, t("gp_stick_editor.right_stick"))
        self._id_group.addButton(self._rb_left)
        self._id_group.addButton(self._rb_right)
        (self._rb_right if self.data.stick_id == STICK_ID_RIGHT else self._rb_left).setChecked(True)
        row.addWidget(self._rb_left); row.addSpacing(16)
        row.addWidget(self._rb_right); row.addStretch()
        col.addLayout(row)
        return col

    def _build_sensitivity_row(self, fn):
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(self._field_label(fn, t("gp_stick_editor.sensitivity")))
        row = QHBoxLayout()
        self._sens_group = QButtonGroup(self)
        self._rb_linear = self._build_radio(fn, t("gp_stick_editor.sens_linear"))
        self._rb_square = self._build_radio(fn, t("gp_stick_editor.sens_square"))
        self._sens_group.addButton(self._rb_linear)
        self._sens_group.addButton(self._rb_square)
        (self._rb_square if self.data.sensitivity_curve == 'square' else self._rb_linear).setChecked(True)
        row.addWidget(self._rb_linear); row.addSpacing(16)
        row.addWidget(self._rb_square); row.addStretch()
        col.addLayout(row)
        return col

    def _build_slider_section(self, fn, field_label, value_attr, slider_attr,
                              min_v, max_v, init, default_v, suffix, hint, accent):
        """单个 slider 区段:
           Row 1: [Label]   [当前值; 若 == 默认值 则前缀 '默认值']
           Row 2: slider (▼ 三角, 当前 == 默认时三角和数字都变蓝)
           Row 3: 说明 hint
        """
        col = QVBoxLayout()
        col.setSpacing(4)

        head = QHBoxLayout()
        head.addWidget(self._field_label(fn, field_label))
        head.addStretch()
        value_lbl = QLabel()
        value_lbl.setFont(_font(fn, 14, bold=True))
        head.addWidget(value_lbl)
        setattr(self, value_attr, value_lbl)
        col.addLayout(head)

        slider = _DefaultMarkedSlider(min_v, max_v, init, default_v)

        default_prefix = t("gp_stick_editor.default_prefix")

        def _refresh_value_lbl(v):
            at_default = (v == default_v)
            text = f"{default_prefix} {v}{suffix}" if at_default else f"{v}{suffix}"
            value_lbl.setText(text)
            # 在默认值时, 数字也变蓝 (强化视觉关联)
            color = _C_BLUE if at_default else _C_BLUE_H
            value_lbl.setStyleSheet(f"color: {color}; background: transparent;")

        _refresh_value_lbl(init)
        slider.valueChanged.connect(_refresh_value_lbl)
        # CSS: groove 推到下半 (TRACK_MARGIN_TOP), 让上半留给 default 文字 + 三角
        tm = _DefaultMarkedSlider.TRACK_MARGIN_TOP
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: #404040; height: 6px; border-radius: 3px;
                margin: {tm}px 0 0 0;
            }}
            QSlider::sub-page:horizontal {{
                background: {_C_BLUE}; border-radius: 3px;
                margin: {tm}px 0 0 0;
            }}
            QSlider::add-page:horizontal {{
                background: #404040; border-radius: 3px;
                margin: {tm}px 0 0 0;
            }}
            QSlider::handle:horizontal {{
                background: #DDD; border: 1px solid #999;
                width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{ background: {_C_BLUE}; border-color: {_C_BLUE_H}; }}
        """)
        setattr(self, slider_attr, slider)
        col.addWidget(slider)

        hint_lbl = QLabel(hint)
        hint_lbl.setFont(_font(fn, 11))
        hint_lbl.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        hint_lbl.setWordWrap(True)
        col.addWidget(hint_lbl)

        return col

    def _build_action_field_row(self, fn, field_name, label_text):
        """鼠标动作字段行: 色点 + 标签(60px) + TagInput (跟 button editor _build_field_row 同模式)"""
        row = QHBoxLayout()
        row.setSpacing(0)
        accent = ACTION_COLORS.get(field_name, _C_BLUE)
        dot = _ColorDot(accent)
        row.addWidget(dot)
        lbl = QLabel(label_text)
        lbl.setFont(_font(fn, 14))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setFixedWidth(60)
        row.addWidget(lbl)
        row.addSpacing(10)
        ti = TagInput(getattr(self.data, field_name, '') or '', accent_color=accent)
        ti.focusChanged.connect(self._on_focus_changed)
        self._tag_inputs[field_name] = ti
        row.addWidget(ti, 1)
        return row

    # ── 底部按钮 (跟 button editor 一致) ──

    def _build_bottom_buttons(self, fn):
        col = QVBoxLayout()
        col.setSpacing(8)

        # Copy (全宽)
        copy_btn = QPushButton(t("gp_stick_editor.copy"))
        copy_btn.setFixedHeight(40)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(_font(fn, 18))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        copy_btn.clicked.connect(self._on_copy)
        col.addWidget(copy_btn)

        # Delete | Save
        r = QHBoxLayout()
        r.setSpacing(10)
        del_btn = QPushButton(t("gp_stick_editor.delete"))
        del_btn.setFixedHeight(40)
        del_btn.setFont(_font(fn, 18))
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(self._on_delete)
        r.addWidget(del_btn)

        save_btn = QPushButton(t("gp_stick_editor.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_font(fn, 18, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CYBER}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        r.addWidget(save_btn)

        col.addLayout(r)
        return col

    # ── 小控件 ──

    def _section_label(self, fn, text):
        lbl = QLabel(text)
        lbl.setFont(_font(fn, 15, bold=True))
        lbl.setStyleSheet(f"color: {_C_BLUE_H}; background: transparent;")
        return lbl

    def _field_label(self, fn, text):
        lbl = QLabel(text)
        lbl.setFont(_font(fn, 14, bold=True))
        lbl.setStyleSheet(f"color: {_C_TEXT}; background: transparent;")
        return lbl

    def _build_radio(self, fn, text):
        rb = QRadioButton(text)
        rb.setFont(_font(fn, 14))
        rb.setStyleSheet(f"""
            QRadioButton {{ color: {_C_TEXT}; background: transparent; spacing: 8px; }}
            QRadioButton::indicator {{
                width: 16px; height: 16px; border-radius: 9px;
                border: 2px solid #666; background: {_C_BG};
            }}
            QRadioButton::indicator:hover {{ border-color: {_C_BLUE_H}; }}
            QRadioButton::indicator:checked {{
                border: 2px solid {_C_BLUE}; background: {_C_BG};
                image: url({_RADIO_DOT_URL});
            }}
            QRadioButton::indicator:checked:hover {{ border: 2px solid {_C_BLUE_H}; }}
        """)
        return rb

    def _build_check(self, fn, text):
        chk = QCheckBox(text)
        chk.setFont(_font(fn, 14))
        chk.setStyleSheet(f"""
            QCheckBox {{ color: {_C_TEXT}; background: transparent; spacing: 8px; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 3px;
                border: 2px solid #666; background: {_C_BG};
            }}
            QCheckBox::indicator:hover {{ border-color: {_C_BLUE_H}; }}
            QCheckBox::indicator:checked {{
                background: {_C_BLUE}; border: 2px solid {_C_BLUE};
                image: url({_CHECK_ICON_URL});
            }}
            QCheckBox::indicator:checked:hover {{
                background: {_C_BLUE_H}; border-color: {_C_BLUE_H};
                image: url({_CHECK_ICON_URL});
            }}
        """)
        return chk

    # ── 回调 ──

    def _on_copy(self):
        self._apply_to_data()
        self.copied.emit(self._item)
        self.accept()

    def _on_delete(self):
        self.deleted.emit(self._item)
        self.accept()

    def _on_save(self):
        self._apply_to_data()
        self.saved.emit(self._item)
        self.accept()

    def _apply_to_data(self):
        self.data.name = self._name_edit.text().strip()
        self.data.stick_id = (STICK_ID_RIGHT if self._rb_right.isChecked() else STICK_ID_LEFT)
        self.data.dead_zone = self._dead_zone_slider.value() / 100.0
        self.data.release_threshold_ratio = self._release_slider.value() / 100.0
        self.data.sensitivity_curve = ('square' if self._rb_square.isChecked() else 'linear')
        self.data.eight_way = bool(self._eight_chk.isChecked())
        for fname, ti in self._tag_inputs.items():
            setattr(self.data, fname, ti.get_value())

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
