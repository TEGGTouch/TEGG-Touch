"""
TEGG Touch 蛋挞 (PyQt6) - macro_editor_dialog.py
宏编辑弹窗 — 左右双栏布局: 左侧宏步骤编辑 + 右侧键位面板。
覆盖在按钮编辑弹窗之上。
"""

import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QSlider, QPushButton, QWidget,
    QScrollArea, QFrame, QApplication, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QDrag

from core.i18n import t, get_font
from views.button_editor_dialog import (
    KEY_CATEGORIES, _FlowWidget, _make_font, _detect_icon_font, _ICON_FONT,
    C_PM_BG, C_GRAY, C_GRAY_H, C_CYBER, C_CYBER_H, C_CLOSE, C_CLOSE_H,
    C_INPUT_BG, C_TAG_BG, C_TAG_HOVER, C_TAG_TEXT, C_CAT_LABEL, C_DELAY,
    TagInput,
)

# 宏步骤强调色
C_MACRO_KEY = "#8B5CF6"     # 紫色 — 指令步骤
C_MACRO_DELAY = "#D97706"   # 琥珀色 — 延迟步骤
C_MACRO_NAME = "#10B981"    # 绿色 — 宏名称

MAX_STEPS = 32
MIN_DELAY = 10
MAX_DELAY = 5000
DELAY_STEP = 10


class _StepRow(QWidget):
    """单个宏步骤行 — 指令或延迟"""

    removed = pyqtSignal(object)
    focus_changed = pyqtSignal(object)  # TagInput 聚焦时发出

    def __init__(self, step_data: dict, index: int, fn: str, parent=None):
        super().__init__(parent)
        self.step_data = step_data
        self._index = index
        self._fn = fn
        self.setFixedHeight(52)
        self._init_ui()

    def _init_ui(self):
        fn = self._fn
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        # 序号 + 拖动手柄
        handle = QLabel(f"☰ {self._index + 1}")
        handle.setFont(_make_font(fn, 14))
        handle.setStyleSheet("color: #666; background: transparent;")
        handle.setFixedWidth(36)
        handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self._handle = handle
        lay.addWidget(handle)

        if self.step_data.get('type') == 'delay':
            self._build_delay_row(lay, fn)
        else:
            self._build_key_row(lay, fn)

        # 移除按钮
        _detect_icon_font()
        rm_icon = "\uE711" if _ICON_FONT else "✕"
        rm_btn = QPushButton(rm_icon)
        rm_btn.setFixedSize(32, 32)
        rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            rm_btn.setFont(_make_font(_ICON_FONT, 14))
        else:
            rm_btn.setFont(_make_font(fn, 14, bold=True))
        rm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        rm_btn.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(rm_btn)

    def _build_key_row(self, lay, fn):
        """构建指令步骤行: 键值输入框 + 操作下拉"""
        # 键值 TagInput
        key_val = self.step_data.get('key', '')
        self._key_input = TagInput(initial_value=key_val, accent_color=C_MACRO_KEY)
        self._key_input.setFixedHeight(38)
        self._key_input.focusChanged.connect(lambda w: self.focus_changed.emit(w))
        lay.addWidget(self._key_input, 1)

        # 操作下拉
        self._action_combo = QComboBox()
        self._action_combo.setFixedSize(80, 38)
        self._action_combo.setFont(_make_font(fn, 13))
        actions = [
            (t("macro.action_click"), "click"),
            (t("macro.action_press"), "press"),
            (t("macro.action_release"), "release"),
        ]
        for label, value in actions:
            self._action_combo.addItem(label, value)
        # 恢复保存的值
        saved_action = self.step_data.get('action', 'click')
        for i in range(self._action_combo.count()):
            if self._action_combo.itemData(i) == saved_action:
                self._action_combo.setCurrentIndex(i)
                break
        self._action_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C_INPUT_BG}; color: #E0E0E0;
                border: 1px solid #555; border-radius: 4px;
                padding: 2px 6px;
            }}
            QComboBox:hover {{ border-color: {C_MACRO_KEY}; }}
            QComboBox::drop-down {{
                border: none; width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {C_PM_BG}; color: #E0E0E0;
                border: 1px solid #555; selection-background-color: {C_MACRO_KEY};
            }}
        """)
        lay.addWidget(self._action_combo)

    def _build_delay_row(self, lay, fn):
        """构建延迟步骤行: 文本 + 滑块 + 输入框"""
        # "延迟" 标签
        delay_lbl = QLabel(t("macro.delay_label"))
        delay_lbl.setFont(_make_font(fn, 14))
        delay_lbl.setStyleSheet(f"color: {C_MACRO_DELAY}; background: transparent;")
        delay_lbl.setFixedWidth(40)
        lay.addWidget(delay_lbl)

        # 滑块
        val = self.step_data.get('ms', 100)
        self._delay_slider = QSlider(Qt.Orientation.Horizontal)
        self._delay_slider.setRange(MIN_DELAY, MAX_DELAY)
        self._delay_slider.setValue(val)
        self._delay_slider.setSingleStep(DELAY_STEP)
        self._delay_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: #404040; height: 6px; border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {C_MACRO_DELAY}; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #DDD; border: none;
                width: 14px; height: 14px; margin: -4px 0; border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{ background: {C_MACRO_DELAY}; }}
        """)
        lay.addWidget(self._delay_slider, 1)

        # 输入框
        self._delay_entry = QLineEdit(str(val))
        self._delay_entry.setFixedSize(70, 32)
        self._delay_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._delay_entry.setFont(_make_font(fn, 13))
        self._delay_entry.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: {C_MACRO_DELAY};
                border: 1px solid #555; border-radius: 4px;
            }}
            QLineEdit:focus {{ border-color: {C_MACRO_DELAY}; }}
        """)
        lay.addWidget(self._delay_entry)

        ms_lbl = QLabel("ms")
        ms_lbl.setFont(_make_font(fn, 13))
        ms_lbl.setStyleSheet("color: #888; background: transparent;")
        ms_lbl.setFixedWidth(22)
        lay.addWidget(ms_lbl)

        # 双向同步
        def _s2e(v):
            v = round(v / DELAY_STEP) * DELAY_STEP
            self._delay_entry.setText(str(v))

        def _e2s():
            try:
                v = max(MIN_DELAY, min(MAX_DELAY, int(self._delay_entry.text())))
                v = round(v / DELAY_STEP) * DELAY_STEP
                self._delay_slider.setValue(v)
                self._delay_entry.setText(str(v))
            except ValueError:
                pass

        self._delay_slider.valueChanged.connect(_s2e)
        self._delay_entry.editingFinished.connect(_e2s)

    def set_index(self, idx: int):
        self._index = idx
        self._handle.setText(f"☰ {idx + 1}")

    def get_step_data(self) -> dict:
        """读取当前步骤数据"""
        if self.step_data.get('type') == 'delay':
            try:
                ms = max(MIN_DELAY, min(MAX_DELAY, int(self._delay_entry.text())))
                ms = round(ms / DELAY_STEP) * DELAY_STEP
            except ValueError:
                ms = self._delay_slider.value()
            return {'type': 'delay', 'ms': ms}
        else:
            return {
                'type': 'key',
                'key': self._key_input.get_value(),
                'action': self._action_combo.currentData(),
            }


class MacroEditorDialog(QDialog):
    """宏编辑弹窗 — 左右双栏: 左侧步骤编辑 + 右侧键位面板"""

    macro_saved = pyqtSignal(dict)  # 发出保存后的完整宏数据

    LEFT_W = 480
    RIGHT_W = 440
    PADDING = 20
    WIN_W = LEFT_W + RIGHT_W + PADDING * 2 + 20
    WIN_H = 800

    def __init__(self, macro_data: dict = None, parent=None):
        super().__init__(parent)
        # macro_data: {"name": "...", "steps": [...]} or None for new
        self._macro = macro_data or {"name": "", "steps": []}
        self._step_rows: list[_StepRow] = []
        self._focus_widget = None

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

    def _init_ui(self):
        fn = get_font()
        _detect_icon_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("me_container")
        container.setStyleSheet(f"""
            QFrame#me_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #555;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # ── 标题栏 ──
        title_row = QHBoxLayout()
        title_lbl = QLabel(t("macro.editor_title"))
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
        root.addSpacing(16)

        # ── 双栏 ──
        columns = QHBoxLayout()
        columns.setSpacing(0)

        # ════ 左栏: 宏步骤 ════
        left = QVBoxLayout()
        left.setSpacing(0)
        left.setContentsMargins(0, 0, 0, 0)

        # 宏名称
        name_row = QHBoxLayout()
        name_lbl = QLabel(t("macro.name_label"))
        name_lbl.setFont(_make_font(fn, 16))
        name_lbl.setStyleSheet(f"color: {C_MACRO_NAME}; background: transparent;")
        name_row.addWidget(name_lbl)
        name_row.addSpacing(10)

        self._name_edit = QLineEdit(self._macro.get('name', ''))
        self._name_edit.setPlaceholderText(t("macro.name_placeholder"))
        self._name_edit.setFont(_make_font(fn, 14))
        self._name_edit.setFixedHeight(38)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid #555; border-radius: 6px;
                padding: 4px 8px;
            }}
            QLineEdit:focus {{ border-color: {C_MACRO_NAME}; }}
        """)
        name_row.addWidget(self._name_edit, 1)
        left.addLayout(name_row)
        left.addSpacing(12)

        # 步骤限制提示
        self._limit_lbl = QLabel(f"0 / {MAX_STEPS}")
        self._limit_lbl.setFont(_make_font(fn, 12))
        self._limit_lbl.setStyleSheet("color: #666; background: transparent;")
        self._limit_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        left.addWidget(self._limit_lbl)
        left.addSpacing(4)

        # 分隔线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        left.addWidget(sep)
        left.addSpacing(8)

        # 步骤列表 (滚动区域)
        self._steps_scroll = QScrollArea()
        self._steps_scroll.setWidgetResizable(True)
        self._steps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._steps_scroll.setStyleSheet("""
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

        self._steps_container = QWidget()
        self._steps_container.setStyleSheet("background: transparent;")
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(4)
        self._steps_layout.addStretch()

        self._steps_scroll.setWidget(self._steps_container)
        left.addWidget(self._steps_scroll, 1)

        left.addSpacing(12)

        # 底部按钮
        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)

        add_key_btn = QPushButton(t("macro.add_key_step"))
        add_key_btn.setFixedHeight(36)
        add_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_key_btn.setFont(_make_font(fn, 14))
        add_key_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_MACRO_KEY}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: #7C3AED; }}
        """)
        add_key_btn.clicked.connect(self._add_key_step)
        btn_row1.addWidget(add_key_btn)

        add_delay_btn = QPushButton(t("macro.add_delay_step"))
        add_delay_btn.setFixedHeight(36)
        add_delay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_delay_btn.setFont(_make_font(fn, 14))
        add_delay_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_MACRO_DELAY}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: #B45309; }}
        """)
        add_delay_btn.clicked.connect(self._add_delay_step)
        btn_row1.addWidget(add_delay_btn)

        left.addLayout(btn_row1)
        left.addSpacing(8)

        save_btn = QPushButton(t("macro.save"))
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
        left.addWidget(save_btn)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(self.LEFT_W)
        left_widget.setStyleSheet("background: transparent;")
        columns.addWidget(left_widget)
        columns.addSpacing(12)

        # 分隔线
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background: #444;")
        columns.addWidget(divider)
        columns.addSpacing(8)

        # ════ 右栏: 键位面板 ════
        right = self._build_key_palette(fn)
        columns.addWidget(right, 1)

        root.addLayout(columns, 1)

        # 加载已有步骤
        for step in self._macro.get('steps', []):
            self._add_step_row(step)
        self._update_limit_label()

    def _build_key_palette(self, fn):
        """复用 KEY_CATEGORIES 构建键位面板"""
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

        for i, (cat_name, keys) in enumerate(KEY_CATEGORIES):
            if i > 0:
                layout.addSpacing(16)
            cat_lbl = QLabel(f"── {cat_name} ──")
            cat_lbl.setFont(_make_font(fn, 13, bold=True))
            cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
            layout.addWidget(cat_lbl)
            layout.addSpacing(6)

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

    def _on_key_clicked(self, key_name):
        """键位面板点击 → 填入当前聚焦的 TagInput"""
        if self._focus_widget and isinstance(self._focus_widget, TagInput):
            self._focus_widget.add_tag(key_name)

    def _add_step_row(self, step_data: dict):
        """添加一个步骤行到列表"""
        fn = get_font()
        idx = len(self._step_rows)
        row = _StepRow(step_data, idx, fn)
        row.removed.connect(self._on_step_removed)
        row.focus_changed.connect(self._on_step_focus)
        self._step_rows.append(row)
        # 插入到 stretch 之前
        self._steps_layout.insertWidget(self._steps_layout.count() - 1, row)
        self._update_limit_label()

    def _add_key_step(self):
        if len(self._step_rows) >= MAX_STEPS:
            return
        self._add_step_row({'type': 'key', 'key': '', 'action': 'click'})

    def _add_delay_step(self):
        if len(self._step_rows) >= MAX_STEPS:
            return
        self._add_step_row({'type': 'delay', 'ms': 100})

    def _on_step_removed(self, row):
        """移除步骤"""
        if row in self._step_rows:
            self._step_rows.remove(row)
            self._steps_layout.removeWidget(row)
            row.deleteLater()
            # 重新编号
            for i, r in enumerate(self._step_rows):
                r.set_index(i)
            self._update_limit_label()

    def _on_step_focus(self, widget):
        self._focus_widget = widget

    def _update_limit_label(self):
        n = len(self._step_rows)
        color = "#F43F5E" if n >= MAX_STEPS else "#666"
        self._limit_lbl.setText(f"{n} / {MAX_STEPS}")
        self._limit_lbl.setStyleSheet(f"color: {color}; background: transparent;")

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            name = f"Macro {len(self._step_rows)}"
        steps = [row.get_step_data() for row in self._step_rows]
        result = {'name': name, 'steps': steps}
        self.macro_saved.emit(result)
        self.accept()

    def get_result(self) -> dict:
        name = self._name_edit.text().strip()
        if not name:
            name = f"Macro {len(self._step_rows)}"
        steps = [row.get_step_data() for row in self._step_rows]
        return {'name': name, 'steps': steps}

    # ── 定位 + 拖拽 ──

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

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
