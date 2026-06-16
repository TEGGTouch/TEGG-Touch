"""
TEGG Touch 蛋挞 (PyQt6) - gp_wheel_editor_dialog.py
方向盘编辑弹窗 — 单栏布局 (~520×760):
  Section 1 方向盘参数: 名称 / 释放阈值 / 灵敏度曲线
  Section 2 LT 控制方式: 滚轮 / 垂直位移 / 左右键 (+ 参数)
  Section 3 RT 控制方式: 同 LT (+ 互斥校验)
"""

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QSlider, QPushButton, QFrame, QWidget,
    QApplication, QRadioButton, QButtonGroup, QStackedWidget,
    QScrollArea, QCheckBox,
)
from PyQt6.QtCore import Qt, QPoint, QSize, QByteArray, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush, QPolygon, QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from core.i18n import t, get_font
from core.constants import (
    APP_DIR,
    C_PM_BG, C_GRAY, C_GRAY_H, C_CYBER, C_CYBER_H, C_CLOSE, C_CLOSE_H,
    C_INPUT_BG,
)


_C_BG = C_PM_BG
_C_BORDER = "#444"
_C_BLUE = "#3B82F6"
_C_BLUE_H = "#60A5FA"
_C_TEXT = "#E0E0E0"
_C_HINT = "#888"
_C_DEFAULT_TEXT = "#AAAAAA"
_C_MARK = "#CCCCCC"
_C_ERROR = "#E11D48"

_CHECK_ICON_URL = os.path.join(APP_DIR, "assets", "check.svg").replace("\\", "/")
_RADIO_DOT_URL = os.path.join(APP_DIR, "assets", "radio_dot.svg").replace("\\", "/")
_RADIO_DOT_ROSE_URL = os.path.join(APP_DIR, "assets", "radio_dot_rose.svg").replace("\\", "/")
_RADIO_DOT_AMBER_URL = os.path.join(APP_DIR, "assets", "radio_dot_amber.svg").replace("\\", "/")
# marker 模式: LT = 玫瑰红, RT = 琥珀黄 (跟方向盘上的浮标横线同色)
_MARKER_COLOR_LT = "#F43F5E"
_MARKER_COLOR_RT = "#F59E0B"

# check.svg 是固定白色; 这里按颜色生成对应 QIcon 并缓存 (color hex → QIcon)
_CHECK_ICON_CACHE: dict = {}


def _check_icon(color: str) -> QIcon:
    color = color.upper()
    if color in _CHECK_ICON_CACHE:
        return _CHECK_ICON_CACHE[color]
    try:
        with open(_CHECK_ICON_URL, 'rb') as f:
            svg = f.read().decode('utf-8')
        svg = svg.replace('#FFFFFF', color).replace('#ffffff', color)
        renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(p)
        p.end()
        icon = QIcon(pm)
    except Exception:
        icon = QIcon(_CHECK_ICON_URL)
    _CHECK_ICON_CACHE[color] = icon
    return icon

_DEFAULT_RELEASE_PCT = 200


def _font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class _DefaultMarkedSlider(QSlider):
    """slider 上方画 ▼ 三角; 当前值 == 默认值 → 蓝, 否则灰白 (复用 gp_stick_editor 模式)"""
    TRI_TOP = 4
    TRI_H = 8
    TRACK_MARGIN_TOP = 20
    WIDGET_H = 34

    def __init__(self, min_v, max_v, init, default_v, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(min_v, max_v)
        self.setValue(init)
        self._default = default_v
        self.setFixedHeight(self.WIDGET_H)
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


class _TriggerSection(QWidget):
    """LT 或 RT 一个完整 section: mode radio + 3 个 mode 的参数 (QStackedWidget)"""

    mode_changed = pyqtSignal(str)              # 'scroll' | 'vertical' | 'buttons' | 'marker'
    marker_button_changed = pyqtSignal(str)     # 'L' | 'R' — 用户改了 marker 模式的 click 键

    def __init__(self, title: str, data, prefix: str, parent=None):
        """prefix: 'lt' or 'rt' — 用于读 data 的 lt_scroll_step / rt_vertical_px 等字段"""
        super().__init__(parent)
        self._data = data
        self._prefix = prefix
        self._fn = get_font()
        self._init_ui(title)

    def _init_ui(self, title):
        fn = self._fn
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        sec_lbl = QLabel(title)
        sec_lbl.setFont(_font(fn, 16, bold=True))
        sec_lbl.setStyleSheet(f"color: {_C_BLUE_H}; background: transparent;")
        lay.addWidget(sec_lbl)

        # 控制方式 — tab 按钮 (三选一, 互斥由 Dialog 协调)
        lay.addWidget(_make_field_label(fn, t("gp_wheel_editor.mode_label")))
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self._mode_btns: dict = {}
        self._disabled_reasons: dict = {}
        mode_info = [
            ('marker', '浮标点击'),                        # 默认模式, 放最左
            ('scroll', t("gp_wheel_editor.mode_scroll")),
            ('vertical', t("gp_wheel_editor.mode_vertical")),
            ('buttons', t("gp_wheel_editor.mode_buttons")),
        ]
        cur_mode = getattr(self._data, f'{self._prefix}_mode', 'scroll')
        if cur_mode not in ('scroll', 'vertical', 'buttons', 'marker'):
            cur_mode = 'scroll'
        self._current_mode = cur_mode
        for key, label in mode_info:
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(_font(fn, 14, bold=True))
            b.setFixedHeight(36)
            b.clicked.connect(lambda _, k=key: self._on_tab_clicked(k))
            mode_row.addWidget(b, 1)
            self._mode_btns[key] = b
        lay.addLayout(mode_row)
        self._refresh_tab_styles()

        # 参数 stacked widget
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._build_scroll_params(fn))
        self._stack.addWidget(self._build_vertical_params(fn))
        self._stack.addWidget(self._build_buttons_params(fn))
        self._stack.addWidget(self._build_marker_params(fn))
        lay.addWidget(self._stack)

        idx_map = {'scroll': 0, 'vertical': 1, 'buttons': 2, 'marker': 3}
        self._stack.setCurrentIndex(idx_map.get(cur_mode, 0))

        # ── 逆向 checkbox (作用于当前 mode, 说明文本跟 mode 联动) ──
        from PyQt6.QtWidgets import QCheckBox
        lay.addSpacing(6)
        self._reverse_cb = QCheckBox("逆向")
        self._reverse_cb.setFont(_font(fn, 14, bold=True))
        self._reverse_cb.setStyleSheet(f"""
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
        """)
        self._reverse_cb.setChecked(bool(getattr(self._data, f'{self._prefix}_reverse', False)))
        lay.addWidget(self._reverse_cb)
        # 解释文本 (跟 mode 联动)
        self._reverse_hint = _make_label(fn, self._reverse_hint_text(cur_mode), _C_HINT, 12)
        lay.addWidget(self._reverse_hint)

    def _build_scroll_params(self, fn):
        page = QWidget(); v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(10)
        v.addWidget(_make_label(fn, t("gp_wheel_editor.scroll_hint"), _C_HINT, 12))
        head, slider, value_lbl = _make_value_slider(
            fn, t("gp_wheel_editor.scroll_step"),
            init=int(getattr(self._data, f'{self._prefix}_scroll_step') * 100),
            min_v=1, max_v=20, default_v=5, suffix='%',
        )
        self._scroll_step_slider = slider
        v.addLayout(head); v.addWidget(slider)
        return page

    def _build_vertical_params(self, fn):
        page = QWidget(); v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(10)
        v.addWidget(_make_label(
            fn,
            "上下移动鼠标改变扳机值; 位移单位是方向盘高度的百分比 (跟着方向盘缩放, 不会被像素绑死)。",
            _C_HINT, 12))
        head, slider, value_lbl = _make_value_slider(
            fn, "0→100% 所需位移",
            init=int(round(getattr(self._data, f'{self._prefix}_vertical_pct') * 100)),
            min_v=10, max_v=80, default_v=50, suffix='%',
        )
        self._vertical_pct_slider = slider
        v.addLayout(head); v.addWidget(slider)
        return page

    def _build_buttons_params(self, fn):
        page = QWidget(); v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(14)
        v.addWidget(_make_label(fn, t("gp_wheel_editor.buttons_hint"), _C_HINT, 12))
        # interval (ms)
        head_ms, slider_ms, _ = _make_value_slider(
            fn, t("gp_wheel_editor.buttons_ms"),
            init=int(getattr(self._data, f'{self._prefix}_buttons_ms')),
            min_v=10, max_v=500, default_v=100, suffix='ms',
        )
        self._buttons_ms_slider = slider_ms
        v.addLayout(head_ms); v.addWidget(slider_ms)
        # step value per interval (in % unit, e.g. 5 = +0.05)
        head_step, slider_step, _ = _make_value_slider(
            fn, t("gp_wheel_editor.buttons_step"),
            init=int(getattr(self._data, f'{self._prefix}_buttons_step') * 100),
            min_v=1, max_v=20, default_v=5, suffix='%',
        )
        self._buttons_step_slider = slider_step
        v.addLayout(head_step); v.addWidget(slider_step)
        return page

    def _build_marker_params(self, fn):
        page = QWidget(); v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(10)
        marker_color = "玫瑰红" if self._prefix == 'lt' else "琥珀黄"
        v.addWidget(_make_label(
            fn,
            f"鼠标上下移动 {marker_color} 浮标 (不直接改扳机值), 按下下方所选鼠标键 → 扳机值锁定到浮标当前位置。位移单位是方向盘高度的百分比。",
            _C_HINT, 12))
        # 同 vertical 的 pct slider
        head, slider, _ = _make_value_slider(
            fn, "0→100% 所需位移",
            init=int(round(getattr(self._data, f'{self._prefix}_marker_pct', 0.5) * 100)),
            min_v=10, max_v=80, default_v=50, suffix='%',
        )
        self._marker_pct_slider = slider
        v.addLayout(head); v.addWidget(slider)
        # click 键 radio (L / R) — 选中态用 marker 色 (LT 玫红 / RT 琥珀黄)
        v.addSpacing(4)
        v.addWidget(_make_field_label(fn, "锁定按键"))
        btn_row = QHBoxLayout()
        self._marker_btn_group = QButtonGroup(self)
        self._rb_marker_l = self._make_marker_radio(fn, "左键")
        self._rb_marker_r = self._make_marker_radio(fn, "右键")
        self._marker_btn_group.addButton(self._rb_marker_l)
        self._marker_btn_group.addButton(self._rb_marker_r)
        cur_btn = getattr(self._data, f'{self._prefix}_marker_button', 'L')
        (self._rb_marker_r if cur_btn == 'R' else self._rb_marker_l).setChecked(True)
        # 用户主动改 radio 时 emit (会触发 Dialog 联动另一侧自动翻转)
        self._rb_marker_l.toggled.connect(self._on_marker_btn_toggled)
        self._rb_marker_r.toggled.connect(self._on_marker_btn_toggled)
        btn_row.addWidget(self._rb_marker_l); btn_row.addSpacing(20)
        btn_row.addWidget(self._rb_marker_r); btn_row.addStretch()
        v.addLayout(btn_row)
        return page

    def _make_marker_radio(self, fn, text):
        """marker 模式专用 radio: 选中态用 LT 玫红 / RT 琥珀黄 (跟方向盘浮标线同色)"""
        color = _MARKER_COLOR_LT if self._prefix == 'lt' else _MARKER_COLOR_RT
        dot_url = _RADIO_DOT_ROSE_URL if self._prefix == 'lt' else _RADIO_DOT_AMBER_URL
        rb = QRadioButton(text)
        rb.setFont(_font(fn, 14))
        rb.setStyleSheet(f"""
            QRadioButton {{ color: {_C_TEXT}; background: transparent; spacing: 8px; }}
            QRadioButton:checked {{ color: {color}; font-weight: bold; }}
            QRadioButton::indicator {{
                width: 16px; height: 16px; border-radius: 9px;
                border: 2px solid #666; background: {_C_BG};
            }}
            QRadioButton::indicator:hover {{ border-color: {color}; }}
            QRadioButton::indicator:checked {{
                border: 2px solid {color}; background: {_C_BG};
                image: url({dot_url});
            }}
            QRadioButton::indicator:checked:hover {{ border: 2px solid {color}; }}
        """)
        return rb

    def _on_marker_btn_toggled(self, checked: bool):
        if not checked:
            return     # 只在 toggled-ON 时发, 避免重复
        if getattr(self, '_silencing_marker_btn', False):
            return     # 外部联动设置时不要回传
        self.marker_button_changed.emit(self.current_marker_button())

    def current_marker_button(self) -> str:
        return 'R' if self._rb_marker_r.isChecked() else 'L'

    def set_marker_button(self, btn: str):
        """外部 (Dialog) 联动: 静默改 radio, 不触发 marker_button_changed"""
        self._silencing_marker_btn = True
        try:
            (self._rb_marker_r if btn == 'R' else self._rb_marker_l).setChecked(True)
        finally:
            self._silencing_marker_btn = False

    def _on_tab_clicked(self, mode: str):
        if mode in self._disabled_reasons:
            return
        if mode == self._current_mode:
            return
        self._current_mode = mode
        idx_map = {'scroll': 0, 'vertical': 1, 'buttons': 2, 'marker': 3}
        self._stack.setCurrentIndex(idx_map.get(mode, 0))
        self._refresh_tab_styles()
        # 同步「逆向」说明文本
        if hasattr(self, '_reverse_hint'):
            self._reverse_hint.setText(
                f'<div style="line-height: 180%;">{self._reverse_hint_text(mode)}</div>')
        self.mode_changed.emit(mode)

    def _reverse_hint_text(self, mode: str) -> str:
        if mode == 'scroll':
            return "勾选后: 向上滚动 → 扳机值减少, 向下滚动 → 扳机值增加"
        if mode == 'vertical':
            return "勾选后: 鼠标向上移 → 扳机值减少, 向下移 → 扳机值增加"
        if mode == 'buttons':
            return "勾选后: 左键 → 扳机值减少, 右键 → 扳机值增加"
        if mode == 'marker':
            return "勾选后: 鼠标向上移 → 浮标向下走, 向下移 → 浮标向上走"
        return ""

    def current_mode(self) -> str:
        return self._current_mode

    def set_disabled_modes(self, disabled_modes, reason: str, other_selected: str = None):
        """Dialog 协调互斥:
        disabled_modes = 不能选的 mode 集合
        other_selected = 对面正在用的 mode (用于显示灰色 ☑ 提示)
        ☑ 标记规则: 这一侧选中 (白勾) / 对面也选了同一 mode (灰勾) / 其他原因禁用 (不显示勾)"""
        self._disabled_reasons = {m: reason for m in (disabled_modes or set())
                                  if m in ('scroll', 'vertical', 'buttons', 'marker')}
        self._other_selected_mode = other_selected if other_selected in (
            'scroll', 'vertical', 'buttons', 'marker') else None
        self._refresh_tab_styles()

    def _refresh_tab_styles(self):
        """tab 三态: 选中=C_CYBER/C_CYBER_H; 空闲=C_GRAY/C_GRAY_H; 禁用=透明无填充 + 细边框 + 灰字 + tooltip
        ☑ 图标规则:
          - 这一侧选中 → 白勾
          - 对面正在用同一 mode (灰勾, 提示"被对方采用了")
          - 因其他原因禁用 (例如 marker+buttons 冲突) 但没人选这个 → 不画勾"""
        empty_icon = QIcon()
        other_mode = getattr(self, '_other_selected_mode', None)
        for key, b in self._mode_btns.items():
            is_selected = (key == self._current_mode)
            is_disabled = (key in self._disabled_reasons)
            is_other_using = (key == other_mode) and not is_selected
            # ☑: 选中 (白) 或 对方采用 (灰); 仅"被禁但没人选"时无勾
            if is_selected:
                b.setIcon(_check_icon("#FFFFFF"))
            elif is_other_using:
                b.setIcon(_check_icon("#555555"))
            else:
                b.setIcon(empty_icon)
            b.setIconSize(QSize(16, 16))
            if is_disabled:
                b.setEnabled(False)
                b.setCursor(Qt.CursorShape.ArrowCursor)
                b.setToolTip(self._disabled_reasons[key])
                # 不填充 (transparent), 用细边框维持高度/形状; QSS 用 :disabled 防被默认灰板覆盖
                b.setStyleSheet("""
                    QPushButton, QPushButton:disabled {
                        background: transparent; color: #555;
                        border: 1px solid #3A3A3A; border-radius: 6px;
                    }
                """)
            else:
                b.setEnabled(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setToolTip("")
                if is_selected:
                    b.setStyleSheet(f"""
                        QPushButton {{
                            background: {C_CYBER}; color: #FFF;
                            border: none; border-radius: 6px;
                        }}
                        QPushButton:hover {{ background: {C_CYBER_H}; }}
                    """)
                else:
                    b.setStyleSheet(f"""
                        QPushButton {{
                            background: {C_GRAY}; color: #CCC;
                            border: none; border-radius: 6px;
                        }}
                        QPushButton:hover {{ background: {C_GRAY_H}; color: #FFF; }}
                    """)

    def refresh_from_data(self):
        """从 self._data 重新读所有字段并刷新 UI (供「恢复默认」用)"""
        cur_mode = getattr(self._data, f'{self._prefix}_mode', 'scroll')
        if cur_mode not in ('scroll', 'vertical', 'buttons', 'marker'):
            cur_mode = 'scroll'
        self._current_mode = cur_mode
        idx_map = {'scroll': 0, 'vertical': 1, 'buttons': 2, 'marker': 3}
        self._stack.setCurrentIndex(idx_map[cur_mode])
        self._scroll_step_slider.setValue(
            int(getattr(self._data, f'{self._prefix}_scroll_step') * 100))
        self._vertical_pct_slider.setValue(
            int(round(getattr(self._data, f'{self._prefix}_vertical_pct') * 100)))
        self._buttons_ms_slider.setValue(
            int(getattr(self._data, f'{self._prefix}_buttons_ms')))
        self._buttons_step_slider.setValue(
            int(getattr(self._data, f'{self._prefix}_buttons_step') * 100))
        self._marker_pct_slider.setValue(
            int(round(getattr(self._data, f'{self._prefix}_marker_pct', 0.5) * 100)))
        cur_btn = getattr(self._data, f'{self._prefix}_marker_button', 'L')
        self.set_marker_button(cur_btn)
        self._reverse_cb.setChecked(bool(getattr(self._data, f'{self._prefix}_reverse', False)))
        if hasattr(self, '_reverse_hint'):
            self._reverse_hint.setText(
                f'<div style="line-height: 180%;">{self._reverse_hint_text(cur_mode)}</div>')
        self._refresh_tab_styles()

    def apply_to_data(self):
        setattr(self._data, f'{self._prefix}_mode', self.current_mode())
        setattr(self._data, f'{self._prefix}_scroll_step',
                self._scroll_step_slider.value() / 100.0)
        setattr(self._data, f'{self._prefix}_vertical_pct',
                self._vertical_pct_slider.value() / 100.0)
        setattr(self._data, f'{self._prefix}_buttons_ms',
                int(self._buttons_ms_slider.value()))
        setattr(self._data, f'{self._prefix}_buttons_step',
                self._buttons_step_slider.value() / 100.0)
        setattr(self._data, f'{self._prefix}_marker_pct',
                self._marker_pct_slider.value() / 100.0)
        setattr(self._data, f'{self._prefix}_marker_button', self.current_marker_button())
        setattr(self._data, f'{self._prefix}_reverse', self._reverse_cb.isChecked())


def _make_label(fn, text, color, px):
    """提示/说明文字 — HTML 包一层 line-height 让多行不挤"""
    lbl = QLabel(f'<div style="line-height: 180%;">{text}</div>')
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setFont(_font(fn, px))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    lbl.setWordWrap(True)
    return lbl


def _wrap_in_card(inner_widget) -> QFrame:
    """把 LT/RT section 包成一张卡片 (圆角 + 边框 + 内边距; 用 objectName 选择器避免污染子 QFrame)"""
    card = QFrame()
    card.setObjectName("gpwheel_trigger_card")
    card.setStyleSheet(
        "QFrame#gpwheel_trigger_card { background: #232323; "
        "border: 1px solid #3A3A3A; border-radius: 8px; }")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(22, 20, 22, 20)
    cl.setSpacing(0)
    cl.addWidget(inner_widget)
    return card


def _make_field_label(fn, text):
    lbl = QLabel(text)
    lbl.setFont(_font(fn, 13, bold=True))
    lbl.setStyleSheet(f"color: {_C_TEXT}; background: transparent;")
    return lbl


def _make_radio(fn, text):
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


def _make_value_slider(fn, label_text, init, min_v, max_v, default_v, suffix):
    """返回 (head_hbox, slider, value_lbl); 接入 valueChanged 自动刷新值文本 + 默认值前缀"""
    head = QHBoxLayout()
    head.addWidget(_make_field_label(fn, label_text))
    head.addStretch()
    value_lbl = QLabel()
    value_lbl.setFont(_font(fn, 14, bold=True))
    head.addWidget(value_lbl)

    slider = _DefaultMarkedSlider(min_v, max_v, init, default_v)
    slider.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            background: #404040; height: 6px; border-radius: 3px;
            margin: {_DefaultMarkedSlider.TRACK_MARGIN_TOP}px 0 0 0;
        }}
        QSlider::sub-page:horizontal {{
            background: {_C_BLUE}; border-radius: 3px;
            margin: {_DefaultMarkedSlider.TRACK_MARGIN_TOP}px 0 0 0;
        }}
        QSlider::add-page:horizontal {{
            background: #404040; border-radius: 3px;
            margin: {_DefaultMarkedSlider.TRACK_MARGIN_TOP}px 0 0 0;
        }}
        QSlider::handle:horizontal {{
            background: #DDD; border: 1px solid #999;
            width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{ background: {_C_BLUE}; border-color: {_C_BLUE_H}; }}
    """)

    default_prefix = t("gp_stick_editor.default_prefix")

    def _refresh(v):
        at_default = (v == default_v)
        text = f"{default_prefix} {v}{suffix}" if at_default else f"{v}{suffix}"
        value_lbl.setText(text)
        color = _C_BLUE if at_default else _C_BLUE_H
        value_lbl.setStyleSheet(f"color: {color}; background: transparent;")

    _refresh(init)
    slider.valueChanged.connect(_refresh)

    return head, slider, value_lbl


class GpWheelEditorDialog(QDialog):
    """方向盘编辑弹窗 — 单栏布局"""

    saved = pyqtSignal(object)
    deleted = pyqtSignal(object)

    WIN_W = 960
    WIN_H = 960
    PADDING = 20

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self._item = item
        self.data = item.data

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        self._init_ui()
        self._validate_mutual_exclusion()
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self):
        fn = get_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setObjectName("gpwheel_container")
        container.setStyleSheet(f"""
            QFrame#gpwheel_container {{
                background: {_C_BG}; border-radius: 4px; border: 1px solid {_C_BORDER};
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # 顶部: 标题 + 关闭按钮
        hdr = QHBoxLayout()
        title = QLabel(t("gp_wheel_editor.title"))
        title.setFont(_font(fn, 18, bold=True))
        title.setStyleSheet("color: white; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFont(_font(fn, 14, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        hdr.addWidget(close_btn)
        root.addLayout(hdr)
        root.addSpacing(12)

        # 提示 (HTML line-height 拉宽)
        tip = QLabel(f'<div style="line-height:180%">{t("gp_wheel_editor.tip")}</div>')
        tip.setTextFormat(Qt.TextFormat.RichText)
        tip.setFont(_font(fn, 13))
        tip.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addSpacing(20)

        # 可滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; border: none; }
            QScrollBar::handle:vertical { background: #404040; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        body = QWidget(); body.setStyleSheet("background: transparent;")
        sc = QVBoxLayout(body)
        sc.setContentsMargins(0, 0, 12, 0)
        sc.setSpacing(0)

        SECTION_GAP = 22

        # ─── Section 1 方向盘参数 ───
        sec1 = QLabel(t("gp_wheel_editor.section_wheel"))
        sec1.setFont(_font(fn, 16, bold=True))
        sec1.setStyleSheet(f"color: {_C_BLUE_H}; background: transparent;")
        sc.addWidget(sec1)
        sc.addSpacing(10)

        # ── 释放阈值 (1/2 左) + 死区 (1/2 右) 同一行 ──
        two_col_rd = QHBoxLayout()
        two_col_rd.setSpacing(20)

        # 左: 释放阈值
        rel_col = QVBoxLayout()
        rel_col.setSpacing(0)
        head, self._release_slider, _ = _make_value_slider(
            fn, t("gp_wheel_editor.release_threshold"),
            init=int(self.data.release_threshold_ratio * 100),
            min_v=110, max_v=500, default_v=_DEFAULT_RELEASE_PCT, suffix='%',
        )
        self._show_zone_cb = QCheckBox("显示鼠标有效区域")
        self._show_zone_cb.setFont(_font(fn, 12))
        self._show_zone_cb.setStyleSheet(f"""
            QCheckBox {{ color: {_C_TEXT}; background: transparent; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border-radius: 3px;
                border: 2px solid #666; background: {_C_BG};
            }}
            QCheckBox::indicator:hover {{ border-color: {_C_BLUE_H}; }}
            QCheckBox::indicator:checked {{
                background: {_C_BLUE}; border: 2px solid {_C_BLUE};
                image: url({_CHECK_ICON_URL});
            }}
        """)
        self._show_zone_cb.setChecked(False)
        self._show_zone_cb.toggled.connect(self._on_show_zone_toggled)
        head.insertSpacing(1, 10)
        head.insertWidget(2, self._show_zone_cb)
        self._release_slider.valueChanged.connect(self._on_release_slider_changed)
        rel_col.addLayout(head)
        rel_col.addWidget(self._release_slider)
        rel_col.addSpacing(6)
        rel_hint = _make_label(fn, t("gp_wheel_editor.release_threshold_hint"),
                                _C_HINT, 12)
        rel_col.addWidget(rel_hint)
        rel_col.addStretch()
        two_col_rd.addLayout(rel_col, 1)

        # 右: 中心死区 (玫红色可视化)
        _MARKER_ROSE = "#F43F5E"
        dz_col = QVBoxLayout()
        dz_col.setSpacing(0)
        head_dz, self._dead_zone_slider, _ = _make_value_slider(
            fn, "中心死区",
            init=int(round(getattr(self.data, 'dead_zone', 0.10) * 100)),
            min_v=0, max_v=30, default_v=10, suffix='%',
        )
        self._show_dz_cb = QCheckBox("显示死区")
        self._show_dz_cb.setFont(_font(fn, 12))
        self._show_dz_cb.setStyleSheet(f"""
            QCheckBox {{ color: {_C_TEXT}; background: transparent; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border-radius: 3px;
                border: 2px solid #666; background: {_C_BG};
            }}
            QCheckBox::indicator:hover {{ border-color: {_MARKER_ROSE}; }}
            QCheckBox::indicator:checked {{
                background: {_MARKER_ROSE}; border: 2px solid {_MARKER_ROSE};
                image: url({_CHECK_ICON_URL});
            }}
        """)
        self._show_dz_cb.setChecked(False)
        self._show_dz_cb.toggled.connect(self._on_show_dz_toggled)
        head_dz.insertSpacing(1, 10)
        head_dz.insertWidget(2, self._show_dz_cb)
        self._dead_zone_slider.valueChanged.connect(self._on_dz_slider_changed)
        dz_col.addLayout(head_dz)
        dz_col.addWidget(self._dead_zone_slider)
        dz_col.addSpacing(6)
        dz_hint = _make_label(
            fn, "鼠标在方向盘中心 ±死区% 范围内, 不输出转向 — 减少小幅抖动误触发",
            _C_HINT, 12)
        dz_col.addWidget(dz_hint)
        dz_col.addStretch()
        two_col_rd.addLayout(dz_col, 1)

        sc.addLayout(two_col_rd)
        sc.addSpacing(18)

        # 灵敏度曲线 (独立一行)
        sc.addWidget(_make_field_label(fn, t("gp_wheel_editor.sensitivity")))
        sc.addSpacing(8)
        sens_row = QHBoxLayout()
        self._sens_group = QButtonGroup(self)
        self._rb_linear = _make_radio(fn, t("gp_wheel_editor.sens_linear"))
        self._rb_square = _make_radio(fn, t("gp_wheel_editor.sens_square"))
        self._sens_group.addButton(self._rb_linear)
        self._sens_group.addButton(self._rb_square)
        (self._rb_square if self.data.sensitivity_curve == 'square' else self._rb_linear).setChecked(True)
        sens_row.addWidget(self._rb_linear); sens_row.addSpacing(16)
        sens_row.addWidget(self._rb_square); sens_row.addStretch()
        sc.addLayout(sens_row)
        sc.addSpacing(18)

        # 视觉旋转角度 (独立一行)
        sc.addWidget(_make_field_label(fn, "视觉旋转角度 (单边)"))
        sc.addSpacing(8)
        rot_row = QHBoxLayout()
        rot_row.setSpacing(8)
        self._rot_btns: dict = {}
        cur_rot = int(round(getattr(self.data, 'max_rotation_deg', 180.0)))
        if cur_rot not in (90, 180, 270, 360, 720):
            cur_rot = 180
        self._current_max_rotation = cur_rot
        for deg in (90, 180, 270, 360, 720):
            b = QPushButton(f"{deg}°")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(_font(fn, 14, bold=True))
            b.setFixedHeight(36)
            b.clicked.connect(lambda _, d=deg: self._on_rot_clicked(d))
            rot_row.addWidget(b, 1)
            self._rot_btns[deg] = b
        sc.addLayout(rot_row)
        sc.addSpacing(6)
        rot_hint = _make_label(
            fn, "真车 90~180° 紧凑赛车手感; 360~540° 接近真车; 720° 模拟器整圈感",
            _C_HINT, 12)
        sc.addWidget(rot_hint)
        self._refresh_rot_btns()
        sc.addSpacing(SECTION_GAP)

        # 分隔线
        sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background: #444; border: none;"); sep1.setFixedHeight(1)
        sc.addWidget(sep1)
        sc.addSpacing(16)

        # ─── Section 2/3: LT / RT 卡片左右并排 ───
        self._lt_section = _TriggerSection(t("gp_wheel_editor.lt_title"), self.data, 'lt')
        self._lt_section.mode_changed.connect(lambda m: self._on_mode_changed_from('lt', m))
        self._lt_section.marker_button_changed.connect(
            lambda btn: self._on_marker_button_changed_from('lt', btn))
        lt_card = _wrap_in_card(self._lt_section)

        self._rt_section = _TriggerSection(t("gp_wheel_editor.rt_title"), self.data, 'rt')
        self._rt_section.mode_changed.connect(lambda m: self._on_mode_changed_from('rt', m))
        self._rt_section.marker_button_changed.connect(
            lambda btn: self._on_marker_button_changed_from('rt', btn))
        rt_card = _wrap_in_card(self._rt_section)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        cards_row.addWidget(lt_card, 1)
        cards_row.addWidget(rt_card, 1)
        sc.addLayout(cards_row)

        sc.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # 底部按钮: Delete | Save (跟 gp_stick 一致, 但去掉 Copy — 单例不允许复制)
        root.addSpacing(12)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        del_btn = QPushButton(t("gp_wheel_editor.delete"))
        del_btn.setFixedHeight(40); del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFont(_font(fn, 16))
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; padding: 0 32px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(del_btn, 1)

        reset_btn = QPushButton("恢复默认")
        reset_btn.setFixedHeight(40); reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setFont(_font(fn, 16))
        reset_btn.setStyleSheet(f"""
            QPushButton {{ background: {C_GRAY}; color: #FFF; border: none; border-radius: 6px; padding: 0 32px; }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        reset_btn.clicked.connect(self._on_reset_defaults)
        btn_row.addWidget(reset_btn, 1)

        # 其他鼠标按键配置 (琥珀色, 在「保存」左边)
        self._mouse_cfg_btn = QPushButton("其他鼠标按键配置")
        self._mouse_cfg_btn.setFixedHeight(40)
        self._mouse_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mouse_cfg_btn.setFont(_font(fn, 15, bold=True))
        self._mouse_cfg_btn.setStyleSheet(f"""
            QPushButton {{ background: #F59E0B; color: #000; border: none; border-radius: 6px; padding: 0 24px; }}
            QPushButton:hover {{ background: #D97706; color: #FFF; }}
        """)
        self._mouse_cfg_btn.clicked.connect(self._on_open_mouse_cfg)
        btn_row.addWidget(self._mouse_cfg_btn, 2)

        self._save_btn = QPushButton(t("gp_wheel_editor.save"))
        self._save_btn.setFixedHeight(40); self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setFont(_font(fn, 16, bold=True))
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn, 3)
        self._apply_save_button_style(enabled=True)
        root.addLayout(btn_row)

    # ── 互斥校验 (三选一: LT/RT 不能用同一种控制方式) ──

    def _on_mode_changed_from(self, from_prefix: str, new_mode: str):
        """from_prefix = 'lt' | 'rt', 哪边刚改了 mode; new_mode = 它的新 mode"""
        # 若刚切到 marker, 而对面也是 marker → 这一侧 (新切的) 取对面的相反键
        if new_mode == 'marker':
            other = self._rt_section if from_prefix == 'lt' else self._lt_section
            if other.current_mode() == 'marker':
                this = self._lt_section if from_prefix == 'lt' else self._rt_section
                other_btn = other.current_marker_button()
                opposite = 'R' if other_btn == 'L' else 'L'
                if this.current_marker_button() != opposite:
                    this.set_marker_button(opposite)
        self._validate_mutual_exclusion()

    def _validate_mutual_exclusion(self):
        """LT/RT 模式互斥规则:
        (a) 同模式互斥 — 但 marker 例外 (双方都可用 marker, 通过按键互斥)
        (b) marker + buttons 互斥 (buttons 占左右键, marker 占其中一个 → 必然抢键)
        (c) marker + marker 允许, 但锁定按键自动翻反 (在 _on_marker_button_changed_from 处理)"""
        lt_mode = self._lt_section.current_mode()
        rt_mode = self._rt_section.current_mode()
        name_map = {
            'scroll':   t("gp_wheel_editor.mode_scroll"),
            'vertical': t("gp_wheel_editor.mode_vertical"),
            'buttons':  t("gp_wheel_editor.mode_buttons"),
            'marker':   '浮标点击',
        }
        rt_label = name_map.get(rt_mode, rt_mode)
        lt_label = name_map.get(lt_mode, lt_mode)

        # (a) 同模式互斥, marker 例外
        lt_disabled = set()
        rt_disabled = set()
        if rt_mode != 'marker':
            lt_disabled.add(rt_mode)
        if lt_mode != 'marker':
            rt_disabled.add(lt_mode)
        # (b) marker ↔ buttons 互斥
        if rt_mode == 'marker':
            lt_disabled.add('buttons')
        if rt_mode == 'buttons':
            lt_disabled.add('marker')
        if lt_mode == 'marker':
            rt_disabled.add('buttons')
        if lt_mode == 'buttons':
            rt_disabled.add('marker')

        self._lt_section.set_disabled_modes(
            lt_disabled, f"右扳机已使用「{rt_label}」, 跟当前模式互斥",
            other_selected=rt_mode)
        self._rt_section.set_disabled_modes(
            rt_disabled, f"左扳机已使用「{lt_label}」, 跟当前模式互斥",
            other_selected=lt_mode)

        # marker + marker 启动时双方相同按键 → 把 RT 翻反 (启动加载老数据兜底; UI 联动走信号路径)
        if lt_mode == 'marker' and rt_mode == 'marker':
            if self._lt_section.current_marker_button() == self._rt_section.current_marker_button():
                lt_btn = self._lt_section.current_marker_button()
                self._rt_section.set_marker_button('R' if lt_btn == 'L' else 'L')

        # 保存禁用条件: 同 mode 但非 marker (marker 双开是合法的)
        ok = (lt_mode != rt_mode) or (lt_mode == 'marker' and rt_mode == 'marker')
        self._apply_save_button_style(enabled=ok)

    def _on_marker_button_changed_from(self, from_prefix: str, btn: str):
        """marker + marker 双方选了同一个键 → 自动翻反对面"""
        if (self._lt_section.current_mode() != 'marker'
                or self._rt_section.current_mode() != 'marker'):
            return
        other = self._rt_section if from_prefix == 'lt' else self._lt_section
        opposite = 'R' if btn == 'L' else 'L'
        if other.current_marker_button() != opposite:
            other.set_marker_button(opposite)

    def _apply_save_button_style(self, enabled: bool):
        self._save_btn.setEnabled(enabled)
        if enabled:
            self._save_btn.setStyleSheet(f"""
                QPushButton {{ background: {C_CYBER}; color: #FFF; border: none; border-radius: 6px; }}
                QPushButton:hover {{ background: {C_CYBER_H}; }}
            """)
        else:
            self._save_btn.setStyleSheet("""
                QPushButton { background: #3A3A3A; color: #666; border: none; border-radius: 6px; }
            """)

    # ── 回调 ──

    def _on_reset_defaults(self):
        """把所有参数恢复成 GamepadWheelData() 默认值; 保留位置/尺寸/名称"""
        from models.gamepad_model import GamepadWheelData
        defaults = GamepadWheelData()
        keep = {'x', 'y', 'w', 'h', 'name', 'btn_type'}
        for field in self.data.__dataclass_fields__:
            if field not in keep:
                setattr(self.data, field, getattr(defaults, field))
        # 刷新 UI: section 1
        self._release_slider.setValue(int(self.data.release_threshold_ratio * 100))
        self._dead_zone_slider.setValue(int(round(self.data.dead_zone * 100)))
        (self._rb_square if self.data.sensitivity_curve == 'square'
         else self._rb_linear).setChecked(True)
        cur_rot = int(round(self.data.max_rotation_deg))
        if cur_rot not in (90, 180, 270, 360, 720):
            cur_rot = 180
        self._current_max_rotation = cur_rot
        self._refresh_rot_btns()
        # section 2/3
        self._lt_section.refresh_from_data()
        self._rt_section.refresh_from_data()
        # 重新计算互斥 (mode 可能变了)
        self._validate_mutual_exclusion()

    def _on_delete(self):
        self.deleted.emit(self._item)
        self.accept()

    def _on_save(self):
        if not self._save_btn.isEnabled():
            return
        self._apply_to_data()
        self.saved.emit(self._item)
        self.accept()

    # ── 其他鼠标按键配置 ──

    def _on_open_mouse_cfg(self):
        """打开 GpWheelMouseDialog — 配置 wheel active 时其他鼠标按键映射"""
        from views.gp_wheel_mouse_dialog import GpWheelMouseDialog
        # 拿当前方向盘 gp_macros (跟 gp_stick 编辑器一致, 从 scene 当前 profile 拿)
        gp_macros = []
        try:
            sc = self._item.scene()
            if sc is not None and hasattr(sc, 'get_config'):
                cfg = sc.get_config() or {}
                gp_macros = list(cfg.get('gp_macros', []) or [])
        except Exception:
            pass
        dlg = GpWheelMouseDialog(self._item, parent=self, gp_macros=gp_macros)
        dlg.exec()      # 模态; 弹窗 _on_save 内部已写回 self._item.data

    # ── 释放阈值预览 (鼠标有效区域显示) ──

    def _on_show_zone_toggled(self, checked: bool):
        if hasattr(self._item, 'set_show_release_zone'):
            self._item.set_show_release_zone(checked)
            if checked and hasattr(self._item, 'set_preview_release_ratio'):
                self._item.set_preview_release_ratio(self._release_slider.value() / 100.0)
            elif hasattr(self._item, 'set_preview_release_ratio'):
                self._item.set_preview_release_ratio(None)

    def _on_release_slider_changed(self, value: int):
        # checkbox 勾上时才需要实时刷预览; 否则只更新值标签 (_make_value_slider 已处理)
        if (self._show_zone_cb.isChecked()
                and hasattr(self._item, 'set_preview_release_ratio')):
            self._item.set_preview_release_ratio(value / 100.0)

    # ── 死区预览 (玫红色可视化) ──

    def _on_show_dz_toggled(self, checked: bool):
        if hasattr(self._item, 'set_show_dead_zone'):
            self._item.set_show_dead_zone(checked)
            if checked and hasattr(self._item, 'set_preview_dead_zone'):
                self._item.set_preview_dead_zone(self._dead_zone_slider.value() / 100.0)
            elif hasattr(self._item, 'set_preview_dead_zone'):
                self._item.set_preview_dead_zone(None)

    def _on_dz_slider_changed(self, value: int):
        if (self._show_dz_cb.isChecked()
                and hasattr(self._item, 'set_preview_dead_zone')):
            self._item.set_preview_dead_zone(value / 100.0)

    def _cleanup_preview(self):
        if hasattr(self._item, 'set_show_release_zone'):
            self._item.set_show_release_zone(False)
        if hasattr(self._item, 'set_preview_release_ratio'):
            self._item.set_preview_release_ratio(None)
        if hasattr(self._item, 'set_show_dead_zone'):
            self._item.set_show_dead_zone(False)
        if hasattr(self._item, 'set_preview_dead_zone'):
            self._item.set_preview_dead_zone(None)

    def accept(self):
        self._cleanup_preview()
        super().accept()

    def reject(self):
        self._cleanup_preview()
        super().reject()

    def _apply_to_data(self):
        self.data.release_threshold_ratio = self._release_slider.value() / 100.0
        self.data.dead_zone = self._dead_zone_slider.value() / 100.0
        self.data.sensitivity_curve = ('square' if self._rb_square.isChecked() else 'linear')
        self.data.max_rotation_deg = float(self._current_max_rotation)
        self._lt_section.apply_to_data()
        self._rt_section.apply_to_data()

    # ── 视觉旋转角度 tab ──

    def _on_rot_clicked(self, deg: int):
        if deg == self._current_max_rotation:
            return
        self._current_max_rotation = deg
        self._refresh_rot_btns()

    def _refresh_rot_btns(self):
        for deg, b in self._rot_btns.items():
            selected = (deg == self._current_max_rotation)
            if selected:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_CYBER}; color: #FFF;
                        border: none; border-radius: 6px;
                    }}
                    QPushButton:hover {{ background: {C_CYBER_H}; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_GRAY}; color: #CCC;
                        border: none; border-radius: 6px;
                    }}
                    QPushButton:hover {{ background: {C_GRAY_H}; color: #FFF; }}
                """)

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
