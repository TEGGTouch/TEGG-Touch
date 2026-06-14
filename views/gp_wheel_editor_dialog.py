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
    QScrollArea,
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush, QPolygon

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

_DEFAULT_RELEASE_PCT = 150


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

    mode_changed = pyqtSignal(str)   # 'scroll' | 'vertical' | 'buttons'

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
        lay.setSpacing(6)

        sec_lbl = QLabel(title)
        sec_lbl.setFont(_font(fn, 15, bold=True))
        sec_lbl.setStyleSheet(f"color: {_C_BLUE_H}; background: transparent;")
        lay.addWidget(sec_lbl)
        lay.addSpacing(4)

        # 控制方式 radio
        lay.addWidget(_make_field_label(fn, t("gp_wheel_editor.mode_label")))
        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._rb_scroll = _make_radio(fn, t("gp_wheel_editor.mode_scroll"))
        self._rb_vertical = _make_radio(fn, t("gp_wheel_editor.mode_vertical"))
        self._rb_buttons = _make_radio(fn, t("gp_wheel_editor.mode_buttons"))
        self._mode_group.addButton(self._rb_scroll)
        self._mode_group.addButton(self._rb_vertical)
        self._mode_group.addButton(self._rb_buttons)
        cur_mode = getattr(self._data, f'{self._prefix}_mode', 'scroll')
        {'scroll': self._rb_scroll, 'vertical': self._rb_vertical,
         'buttons': self._rb_buttons}.get(cur_mode, self._rb_scroll).setChecked(True)
        for rb in (self._rb_scroll, self._rb_vertical, self._rb_buttons):
            rb.toggled.connect(self._on_mode_toggle)
        mode_row.addWidget(self._rb_scroll); mode_row.addSpacing(12)
        mode_row.addWidget(self._rb_vertical); mode_row.addSpacing(12)
        mode_row.addWidget(self._rb_buttons); mode_row.addStretch()
        lay.addLayout(mode_row)

        lay.addSpacing(6)

        # 参数 stacked widget
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._build_scroll_params(fn))
        self._stack.addWidget(self._build_vertical_params(fn))
        self._stack.addWidget(self._build_buttons_params(fn))
        lay.addWidget(self._stack)

        idx_map = {'scroll': 0, 'vertical': 1, 'buttons': 2}
        self._stack.setCurrentIndex(idx_map.get(cur_mode, 0))

        # 互斥错误提示 (默认隐藏, 外部 validation 触发)
        self._err_lbl = QLabel("")
        self._err_lbl.setFont(_font(fn, 12, bold=True))
        self._err_lbl.setStyleSheet(f"color: {_C_ERROR}; background: transparent;")
        self._err_lbl.setVisible(False)
        lay.addWidget(self._err_lbl)

    def _build_scroll_params(self, fn):
        page = QWidget(); v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(4)
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
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(4)
        v.addWidget(_make_label(fn, t("gp_wheel_editor.vertical_hint"), _C_HINT, 12))
        head, slider, value_lbl = _make_value_slider(
            fn, t("gp_wheel_editor.vertical_px"),
            init=int(getattr(self._data, f'{self._prefix}_vertical_px')),
            min_v=50, max_v=500, default_v=200, suffix='px',
        )
        self._vertical_px_slider = slider
        v.addLayout(head); v.addWidget(slider)
        return page

    def _build_buttons_params(self, fn):
        page = QWidget(); v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
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

    def _on_mode_toggle(self, checked: bool):
        if not checked:
            return
        if self._rb_scroll.isChecked():
            mode = 'scroll'; self._stack.setCurrentIndex(0)
        elif self._rb_vertical.isChecked():
            mode = 'vertical'; self._stack.setCurrentIndex(1)
        else:
            mode = 'buttons'; self._stack.setCurrentIndex(2)
        self.mode_changed.emit(mode)

    def current_mode(self) -> str:
        if self._rb_scroll.isChecked():
            return 'scroll'
        if self._rb_vertical.isChecked():
            return 'vertical'
        return 'buttons'

    def show_error(self, msg: str):
        self._err_lbl.setText(msg)
        self._err_lbl.setVisible(True)

    def clear_error(self):
        self._err_lbl.setVisible(False)

    def apply_to_data(self):
        setattr(self._data, f'{self._prefix}_mode', self.current_mode())
        setattr(self._data, f'{self._prefix}_scroll_step',
                self._scroll_step_slider.value() / 100.0)
        setattr(self._data, f'{self._prefix}_vertical_px',
                float(self._vertical_px_slider.value()))
        setattr(self._data, f'{self._prefix}_buttons_ms',
                int(self._buttons_ms_slider.value()))
        setattr(self._data, f'{self._prefix}_buttons_step',
                self._buttons_step_slider.value() / 100.0)


def _make_label(fn, text, color, px):
    lbl = QLabel(text)
    lbl.setFont(_font(fn, px))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    lbl.setWordWrap(True)
    return lbl


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

    WIN_W = 540
    WIN_H = 800
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

        # 标题
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
        root.addSpacing(10)

        # 提示
        tip = QLabel(t("gp_wheel_editor.tip"))
        tip.setFont(_font(fn, 12))
        tip.setStyleSheet(f"color: {_C_HINT}; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addSpacing(14)

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

        SECTION_GAP = 16

        # ─── Section 1 方向盘参数 ───
        sec1 = QLabel(t("gp_wheel_editor.section_wheel"))
        sec1.setFont(_font(fn, 15, bold=True))
        sec1.setStyleSheet(f"color: {_C_BLUE_H}; background: transparent;")
        sc.addWidget(sec1)
        sc.addSpacing(6)

        # 名称
        sc.addWidget(_make_field_label(fn, t("gp_wheel_editor.name")))
        self._name_edit = QLineEdit(self.data.name or "")
        self._name_edit.setPlaceholderText(t("gp_wheel_editor.name_placeholder"))
        self._name_edit.setFont(_font(fn, 14))
        self._name_edit.setFixedHeight(36)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid #555; border-radius: 6px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border-color: {_C_BLUE}; }}
        """)
        sc.addWidget(self._name_edit)
        sc.addSpacing(12)

        # 释放阈值
        head, self._release_slider, _ = _make_value_slider(
            fn, t("gp_wheel_editor.release_threshold"),
            init=int(self.data.release_threshold_ratio * 100),
            min_v=110, max_v=200, default_v=_DEFAULT_RELEASE_PCT, suffix='%',
        )
        sc.addLayout(head)
        sc.addWidget(self._release_slider)
        rel_hint = _make_label(fn, t("gp_wheel_editor.release_threshold_hint"),
                                _C_HINT, 11)
        sc.addWidget(rel_hint)
        sc.addSpacing(12)

        # 灵敏度曲线
        sc.addWidget(_make_field_label(fn, t("gp_wheel_editor.sensitivity")))
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
        sc.addSpacing(SECTION_GAP)

        # 分隔线
        sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background: #444; border: none;"); sep1.setFixedHeight(1)
        sc.addWidget(sep1)
        sc.addSpacing(12)

        # ─── Section 2 LT ───
        self._lt_section = _TriggerSection(t("gp_wheel_editor.lt_title"), self.data, 'lt')
        self._lt_section.mode_changed.connect(self._on_mode_changed)
        sc.addWidget(self._lt_section)
        sc.addSpacing(SECTION_GAP)

        # 分隔线
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background: #444; border: none;"); sep2.setFixedHeight(1)
        sc.addWidget(sep2)
        sc.addSpacing(12)

        # ─── Section 3 RT ───
        self._rt_section = _TriggerSection(t("gp_wheel_editor.rt_title"), self.data, 'rt')
        self._rt_section.mode_changed.connect(self._on_mode_changed)
        sc.addWidget(self._rt_section)

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
            QPushButton {{ background: {C_CLOSE}; color: #FFF; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(del_btn)

        self._save_btn = QPushButton(t("gp_wheel_editor.save"))
        self._save_btn.setFixedHeight(40); self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setFont(_font(fn, 16, bold=True))
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn, 1)
        self._apply_save_button_style(enabled=True)
        root.addLayout(btn_row)

    # ── 互斥校验 ──

    def _on_mode_changed(self, _mode: str):
        self._validate_mutual_exclusion()

    def _validate_mutual_exclusion(self):
        """LT 选 buttons → RT 不能选 buttons (LMB/RMB 已被 LT 全占)"""
        lt_mode = self._lt_section.current_mode()
        rt_mode = self._rt_section.current_mode()
        conflict = (lt_mode == 'buttons' and rt_mode == 'buttons')
        if conflict:
            err = t("gp_wheel_editor.err_mutual_buttons")
            self._lt_section.show_error(err)
            self._rt_section.show_error(err)
            self._apply_save_button_style(enabled=False)
        else:
            self._lt_section.clear_error()
            self._rt_section.clear_error()
            self._apply_save_button_style(enabled=True)

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

    def _on_delete(self):
        self.deleted.emit(self._item)
        self.accept()

    def _on_save(self):
        if not self._save_btn.isEnabled():
            return
        self._apply_to_data()
        self.saved.emit(self._item)
        self.accept()

    def _apply_to_data(self):
        self.data.name = self._name_edit.text().strip()
        self.data.release_threshold_ratio = self._release_slider.value() / 100.0
        self.data.sensitivity_curve = ('square' if self._rb_square.isChecked() else 'linear')
        self._lt_section.apply_to_data()
        self._rt_section.apply_to_data()

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
