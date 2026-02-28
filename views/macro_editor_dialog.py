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
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QDrag

from core.i18n import t, get_font
from views.button_editor_dialog import (
    _get_key_categories, _FlowWidget, _make_font, _detect_icon_font,
    C_PM_BG, C_GRAY, C_GRAY_H, C_CYBER, C_CYBER_H, C_CLOSE, C_CLOSE_H,
    C_INPUT_BG, C_TAG_BG, C_TAG_HOVER, C_TAG_TEXT, C_CAT_LABEL, C_DELAY,
    TagInput,
)

# 宏步骤强调色
C_MACRO_KEY = "#8B5CF6"     # 紫色 — 指令步骤
C_MACRO_DELAY = "#D97706"   # 琥珀黄 — 延迟步骤
C_MACRO_NAME = "#8B5CF6"    # 紫色 — 宏名称 (与 C_MACRO 统一)

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
        self._dragging = False
        self.setFixedHeight(52)
        self._init_ui()

    def _init_ui(self):
        fn = self._fn
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        # 序号 + 拖动手柄 (Segoe icon + 数字双 label)
        _ifont = _detect_icon_font()
        handle_box = QWidget()
        handle_box.setFixedWidth(42)
        handle_box.setCursor(Qt.CursorShape.OpenHandCursor)
        handle_box.setStyleSheet("background: transparent;")
        h_lay = QHBoxLayout(handle_box)
        h_lay.setContentsMargins(0, 0, 0, 0)
        h_lay.setSpacing(2)
        if _ifont:
            h_icon = QLabel("\uE700")
            h_icon.setFont(_make_font(_ifont, 14))
        else:
            h_icon = QLabel("☰")
            h_icon.setFont(_make_font(fn, 14))
        h_icon.setStyleSheet("color: #666; background: transparent;")
        h_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        h_lay.addWidget(h_icon)
        self._handle_num = QLabel(str(self._index + 1))
        self._handle_num.setFont(_make_font(fn, 13))
        self._handle_num.setStyleSheet("color: #666; background: transparent;")
        self._handle_num.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        h_lay.addWidget(self._handle_num)
        self._handle = handle_box
        lay.addWidget(handle_box)

        if self.step_data.get('type') == 'delay':
            self._build_delay_row(lay, fn)
        else:
            self._build_key_row(lay, fn)

        # 移除按钮
        _ifont2 = _detect_icon_font()
        rm_icon = "\uE711" if _ifont2 else "✕"
        rm_btn = QPushButton(rm_icon)
        rm_btn.setFixedSize(32, 32)
        rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ifont2:
            rm_btn.setFont(_make_font(_ifont2, 14))
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
        self._handle_num.setText(str(idx + 1))

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

    # ── 拖拽排序 ──

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and event.position().x() < 42):
            self._dragging = True
            self.grabMouse()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.4)
            self.setGraphicsEffect(eff)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            dlg = self.window()
            if hasattr(dlg, '_on_row_dragging'):
                dlg._on_row_dragging(self, event.globalPosition().y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.releaseMouse()
            self.unsetCursor()
            self.setGraphicsEffect(None)
            dlg = self.window()
            if hasattr(dlg, '_on_row_drop'):
                dlg._on_row_drop(self)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MacroEditorDialog(QDialog):
    """宏编辑弹窗 — 左右双栏: 左侧步骤编辑 + 右侧键位面板"""

    macro_saved = pyqtSignal(dict)  # 发出保存后的完整宏数据

    LEFT_W = 480
    RIGHT_W = 440
    PADDING = 20
    WIN_W = LEFT_W + RIGHT_W + PADDING * 2 + 20
    WIN_H = 800

    def __init__(self, macro_data: dict = None, existing_names: list[str] = None, parent=None):
        super().__init__(parent)
        # macro_data: {"name": "...", "steps": [...]} or None for new
        self._macro = macro_data or {"name": "", "steps": []}
        self._step_rows: list[_StepRow] = []
        self._focus_widget = None
        self._existing_names = set(existing_names or [])
        self._original_name = self._macro.get('name', '')

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

        _ifont = _detect_icon_font()
        close_icon = "\uE711" if _ifont else "\u2715"
        close_btn = QPushButton(close_icon)
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ifont:
            close_btn.setFont(_make_font(_ifont, 20))
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
        self._name_style_normal = f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid #555; border-radius: 6px;
                padding: 4px 8px;
            }}
            QLineEdit:focus {{ border-color: {C_MACRO_NAME}; }}
        """
        self._name_edit.setStyleSheet(self._name_style_normal)
        self._name_edit.textChanged.connect(self._on_name_changed)
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

        # 拖拽指示线 (绝对定位在 _steps_container 上)
        self._drop_indicator = QFrame(self._steps_container)
        self._drop_indicator.setFixedHeight(2)
        self._drop_indicator.setStyleSheet("background: #0078D7;")
        self._drop_indicator.hide()
        self._drag_target_idx = 0

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

        for i, (cat_name, keys) in enumerate(_get_key_categories()):
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

    def _on_name_changed(self):
        """名称输入变化时恢复正常边框样式"""
        self._name_edit.setStyleSheet(self._name_style_normal)
        self._name_edit.setPlaceholderText(t("macro.name_placeholder"))

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            name = f"Macro {len(self._step_rows)}"

        # 校验名称不能与其他宏重复 (编辑时允许保留原名)
        if name != self._original_name and name in self._existing_names:
            self._name_edit.setStyleSheet(f"""
                QLineEdit {{
                    background: {C_INPUT_BG}; color: white;
                    border: 2px solid #F43F5E; border-radius: 6px;
                    padding: 4px 8px;
                }}
            """)
            self._name_edit.setFocus()
            self._name_edit.setPlaceholderText(t("macro.name_duplicate"))
            return

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

    # ── 步骤行拖拽排序 ──

    def _on_row_dragging(self, row, global_y):
        """拖拽中 — 更新指示线位置"""
        rows = self._step_rows
        if len(rows) < 2:
            return

        local_y = self._steps_container.mapFromGlobal(
            QPoint(0, int(global_y))
        ).y()

        # 计算目标插入索引 (基于各行中点)
        target_idx = len(rows)
        for i, r in enumerate(rows):
            row_mid = r.y() + r.height() / 2
            if local_y < row_mid:
                target_idx = i
                break

        self._drag_target_idx = target_idx

        # 定位指示线
        if target_idx < len(rows):
            ind_y = rows[target_idx].y() - 2
        else:
            last = rows[-1]
            ind_y = last.y() + last.height()

        self._drop_indicator.setGeometry(
            0, ind_y, self._steps_container.width(), 2
        )
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    def _on_row_drop(self, row):
        """拖拽释放 — 执行重排"""
        self._drop_indicator.hide()

        if row not in self._step_rows:
            return

        old_idx = self._step_rows.index(row)
        new_idx = self._drag_target_idx

        # 从原位置移除后, 后续索引前移
        if old_idx < new_idx:
            new_idx -= 1

        if old_idx == new_idx:
            return

        # 从列表 & 布局中移除, 再插入新位置
        self._step_rows.pop(old_idx)
        self._steps_layout.removeWidget(row)

        self._step_rows.insert(new_idx, row)
        self._steps_layout.insertWidget(new_idx, row)

        # 重新编号
        for i, r in enumerate(self._step_rows):
            r.set_index(i)

    # ── 定位 + 拖拽 ──

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # 标题栏拖拽区域高度 (PADDING + title_row ~40 + spacing 16)
    _TITLE_BAR_H = 76

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            local_y = event.position().y()
            if local_y <= self._TITLE_BAR_H:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            else:
                self._drag_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
