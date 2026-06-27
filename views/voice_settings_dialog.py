"""
TEGG Touch (PyQt6) - voice_settings_dialog.py
语音指令设置弹窗 — 双栏布局: 左侧指令列表 + 右侧键位面板。
"""

import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QWidget, QScrollArea, QFrame, QApplication, QLineEdit,
    QComboBox, QStackedWidget, QListWidget, QListWidgetItem,
    QMessageBox, QSlider,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush

from core.i18n import t, get_font, get_lang
from core.constants import (
    VOICE_SAMPLE_RATE, GP_LABEL_TO_KEY, GP_KEY_PREFIX,
)

# Reuse shared components from existing dialogs
from views.button_editor_dialog import (
    TagInput, _FlowWidget, _get_key_categories, _get_mouse_keys, populate_gp_palette,
    C_PM_BG, C_GRAY, C_GRAY_H, C_AMBER, C_CYBER, C_CYBER_H,
    C_CLOSE, C_CLOSE_H, C_INPUT_BG, C_TAG_BG, C_TAG_HOVER,
    C_TAG_TEXT, C_CAT_LABEL,
)

# ── 颜色常量 ──
C_GREEN = "#10B981"
C_GREEN_H = "#059669"
C_AMBER_D = "#D97706"

# ── 图标字体 ──
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
    f = QFont(name)
    # 使用 pointSizeF 替代 pixelSize，避免 Qt 内部组件（如 QComboBox）
    # 复制字体时调用 setPointSize(font.pointSize()) 产生 -1 警告
    screen = QApplication.primaryScreen()
    dpi = screen.logicalDotsPerInch() if screen else 96.0
    f.setPointSizeF(px * 72.0 / dpi)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── 语言切换按钮 (复用 HotkeySettingsDialog 样式) ──
class _LangBtn(QPushButton):
    def sizeHint(self):
        lay = self.layout()
        if lay:
            m = self.contentsMargins()
            s = lay.sizeHint()
            return QSize(s.width() + m.left() + m.right(),
                         max(s.height() + m.top() + m.bottom(), self.minimumHeight()))
        return super().sizeHint()


class _CheckToggle(QWidget):
    """带勾号的自定义 checkbox — 点击切换选中状态。"""

    def __init__(self, text, fn, checked=True, parent=None, label_px=14, accent=None):
        super().__init__(parent)
        self._checked = checked
        self._accent = accent or C_CYBER
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # 方框 + 勾 (随字号缩放)
        bs = label_px + 5
        self._box = QLabel()
        self._box.setFixedSize(bs, bs)
        self._box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if _ICON_FONT:
            self._box.setFont(_make_font(_ICON_FONT, label_px))
        else:
            self._box.setFont(_make_font(fn, label_px - 1, bold=True))
        lay.addWidget(self._box)

        lbl = QLabel(text)
        lbl.setFont(_make_font(fn, label_px))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(lbl)

        self._update_style()

    def isChecked(self):
        return self._checked

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._update_style()
        super().mousePressEvent(event)

    def _update_style(self):
        if self._checked:
            icon = "\uE73E" if _ICON_FONT else "\u2713"
            self._box.setText(icon)
            self._box.setStyleSheet(
                f"background: {self._accent}; color: #FFF;"
                " border-radius: 4px;"
            )
        else:
            self._box.setText("")
            self._box.setStyleSheet(
                "background: #333; color: transparent;"
                " border: 1px solid #666; border-radius: 4px;"
            )


# ── 单条指令行 ──
class _CommandRow(QFrame):
    """单条语音指令行: 短语输入 + 按键TagInput + 动作选择 + 删除"""
    delete_clicked = pyqtSignal(object)
    focus_changed = pyqtSignal(object)

    def __init__(self, phrase="", keys="", action="click", fn="", parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; }")
        self._action = action
        self._build_ui(phrase, keys, action, fn)

    # Column fixed widths
    COL_PHRASE = 160
    COL_KEYS = 220
    COL_ACT = 180
    COL_DEL = 36

    def _build_ui(self, phrase, keys, action, fn):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        _detect_icon_font()

        # ── Row 1: labels (fixed widths) ──
        r1 = QHBoxLayout()
        r1.setSpacing(8)

        phrase_lbl = QLabel(t("voice_dialog.phrase"))
        phrase_lbl.setFont(_make_font(fn, 14))
        phrase_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        phrase_lbl.setFixedWidth(self.COL_PHRASE)
        r1.addWidget(phrase_lbl)

        keys_lbl = QLabel(t("voice_dialog.keys"))
        keys_lbl.setFont(_make_font(fn, 14))
        keys_lbl.setStyleSheet("color: #666; background: transparent;")
        keys_lbl.setFixedWidth(self.COL_KEYS)
        r1.addWidget(keys_lbl)

        act_lbl = QLabel(t("voice_dialog.action"))
        act_lbl.setFont(_make_font(fn, 14))
        act_lbl.setStyleSheet("color: #666; background: transparent;")
        act_lbl.setFixedWidth(self.COL_ACT)
        r1.addWidget(act_lbl)

        r1.addStretch()
        lay.addLayout(r1)

        # ── Row 2: inputs + delete btn (same fixed widths) ──
        r2 = QHBoxLayout()
        r2.setSpacing(8)

        self._phrase_edit = QLineEdit(phrase)
        self._phrase_edit.setFont(_make_font(fn, 14))
        self._phrase_edit.setPlaceholderText(t("voice_dialog.phrase_placeholder"))
        self._phrase_edit.setFixedSize(self.COL_PHRASE, 36)
        self._phrase_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid {C_GRAY}; border-radius: 6px;
                padding: 2px 8px;
            }}
            QLineEdit:focus {{ border-color: {C_GREEN}; }}
        """)
        r2.addWidget(self._phrase_edit)

        self._keys_input = TagInput(initial_value=keys, accent_color=C_AMBER)
        self._keys_input.setFixedWidth(self.COL_KEYS)
        self._keys_input.setMinimumHeight(36)
        self._keys_input.focusChanged.connect(
            lambda w: self.focus_changed.emit(w))
        r2.addWidget(self._keys_input)

        # Action buttons container
        act_box = QHBoxLayout()
        act_box.setSpacing(4)
        act_box.setContentsMargins(0, 0, 0, 0)
        self._action_btns = {}
        for act_key, act_text in [
            ("click", t("voice_dialog.action_click")),
            ("press", t("voice_dialog.action_press")),
            ("release", t("voice_dialog.action_release")),
        ]:
            btn = QPushButton(act_text)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(_make_font(fn, 13))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, k=act_key: self._set_action(k))
            self._action_btns[act_key] = btn
            act_box.addWidget(btn)

        act_wrapper = QWidget()
        act_wrapper.setStyleSheet("background: transparent;")
        act_wrapper.setLayout(act_box)
        act_wrapper.setFixedSize(self.COL_ACT, 36)
        r2.addWidget(act_wrapper)

        # Delete button (same row, same height)
        del_btn = QPushButton()
        del_btn.setFixedSize(self.COL_DEL, 36)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            del_btn.setText("\uE74D")
            del_btn.setFont(_make_font(_ICON_FONT, 14))
        else:
            del_btn.setText("\u2715")
            del_btn.setFont(_make_font(fn, 13, bold=True))
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self))
        r2.addWidget(del_btn)

        r2.addStretch()
        lay.addLayout(r2)
        self._update_action_styles()

        lay.addSpacing(6)

        # Separator line
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        lay.addWidget(sep)

    def _set_action(self, action):
        self._action = action
        self._update_action_styles()

    def _update_action_styles(self):
        for k, btn in self._action_btns.items():
            if k == self._action:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_CYBER}; color: #FFF;
                        border: none; border-radius: 6px; padding: 0 12px;
                    }}
                    QPushButton:hover {{ background: {C_CYBER_H}; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #404040; color: #AAA;
                        border: none; border-radius: 6px; padding: 0 12px;
                    }}
                    QPushButton:hover {{ background: #505050; }}
                """)

    def get_data(self):
        return {
            'phrase': self._phrase_edit.text().strip(),
            'keys': self._keys_input.get_value(),
            'action': self._action,
        }


# ── 识别延迟 (chunk size) 调整子弹窗 ──
class _ChunkSizeDialog(QDialog):
    """调整 VOICE_CHUNK_SIZE — 滑块(按 10ms 步进) + 说明 + 重置 + 保存/取消。

    返回值 (get_value): int 采样数; 若等于引擎默认则返回 None (表示「用默认」,
    这样不会把默认值写进 profile 文件, reset 后文件保持干净)。
    """

    def __init__(self, current_chunk, parent=None):
        super().__init__(parent)
        from core.constants import (
            VOICE_CHUNK_SIZE, VOICE_CHUNK_MIN, VOICE_CHUNK_MAX, VOICE_CHUNK_STEP)
        self._DEFAULT = VOICE_CHUNK_SIZE
        self._MIN = VOICE_CHUNK_MIN
        self._MAX = VOICE_CHUNK_MAX
        self._STEP = VOICE_CHUNK_STEP
        self._result = None
        self._drag_pos = None

        # None / 非法 → 默认; 夹到范围内
        cur = current_chunk if isinstance(current_chunk, int) and current_chunk > 0 else self._DEFAULT
        cur = max(self._MIN, min(self._MAX, cur))

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(440)
        _detect_icon_font()
        self._build_ui(cur)
        self._center_on_parent()

    def _build_ui(self, cur):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("cs_container")
        container.setStyleSheet(f"""
            QFrame#cs_container {{
                background: {C_PM_BG};
                border-radius: 8px; border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # 标题
        title = QLabel(t("voice_dialog.chunk_title"))
        title.setFont(_make_font(fn, 17, bold=True))
        title.setStyleSheet("color: #FFF; background: transparent;")
        root.addWidget(title)

        # 说明
        desc = QLabel(t("voice_dialog.chunk_desc"))
        desc.setFont(_make_font(fn, 13))
        desc.setStyleSheet("color: #999; background: transparent;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # 当前值 (大字)
        self._value_lbl = QLabel("")
        self._value_lbl.setFont(_make_font(fn, 22, bold=True))
        self._value_lbl.setStyleSheet(f"color: {C_GREEN}; background: transparent;")
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._value_lbl)

        self._samples_lbl = QLabel("")
        self._samples_lbl.setFont(_make_font(fn, 12))
        self._samples_lbl.setStyleSheet("color: #777; background: transparent;")
        self._samples_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._samples_lbl)

        # 滑块 (单位 = STEP 采样 = 10ms) — 尺寸样式与工具栏滑块一致, 填充用亮绿
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setFixedHeight(24)
        self._slider.setMinimum(self._MIN // self._STEP)
        self._slider.setMaximum(self._MAX // self._STEP)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(1)
        self._slider.setValue(cur // self._STEP)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: #404040; height: 8px; border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {C_GREEN}; border-radius: 4px;
            }}
            QSlider::add-page:horizontal {{
                background: #404040; border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #DDD; border: 1px solid #999;
                width: 18px; height: 18px; margin: -5px 0; border-radius: 9px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {C_GREEN}; border-color: {C_GREEN_H};
            }}
        """)
        self._slider.valueChanged.connect(self._on_slider_changed)
        root.addWidget(self._slider)

        # 两端标签: 更快 / 更稳
        ends = QHBoxLayout()
        faster = QLabel(t("voice_dialog.chunk_faster"))
        faster.setFont(_make_font(fn, 11))
        faster.setStyleSheet("color: #777; background: transparent;")
        ends.addWidget(faster)
        ends.addStretch()
        slower = QLabel(t("voice_dialog.chunk_slower"))
        slower.setFont(_make_font(fn, 11))
        slower.setStyleSheet("color: #777; background: transparent;")
        ends.addWidget(slower)
        root.addLayout(ends)

        root.addSpacing(4)

        # 底部按钮: 重置 | 取消 · 保存
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        reset_btn = QPushButton(t("voice_dialog.chunk_reset"))
        reset_btn.setFixedHeight(36)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setFont(_make_font(fn, 13))
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        reset_btn.clicked.connect(
            lambda: self._slider.setValue(self._DEFAULT // self._STEP))
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton(t("voice_dialog.chunk_cancel"))
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFont(_make_font(fn, 13))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px; padding: 0 18px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton(t("voice_dialog.save"))
        save_btn.setFixedHeight(36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 14, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER}; color: #FFF;
                border: none; border-radius: 6px; padding: 0 22px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        self._on_slider_changed(self._slider.value())  # 初始化显示

    def _on_slider_changed(self, val):
        chunk = val * self._STEP
        ms = chunk * 1000 // VOICE_SAMPLE_RATE
        self._value_lbl.setText(t("voice_dialog.chunk_unit", ms=ms))
        self._samples_lbl.setText(t("voice_dialog.chunk_samples", n=chunk))

    def _on_save(self):
        chunk = self._slider.value() * self._STEP
        # 等于默认值 → 存 None (不写进 profile, 保持「用默认」语义)
        self._result = None if chunk == self._DEFAULT else chunk
        self.accept()

    def get_value(self):
        return self._result

    def _center_on_parent(self):
        p = self.parent()
        if p is not None:
            geo = p.frameGeometry()
            self.adjustSize()
            x = geo.center().x() - self.width() // 2
            y = geo.center().y() - self.height() // 2
            self.move(x, y)

    # 允许拖动 (无边框)
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


# ── 主弹窗类 ──
class VoiceSettingsDialog(QDialog):
    """语音指令设置弹窗 — 双栏布局"""
    settings_saved = pyqtSignal()
    xmacros_changed = pyqtSignal(list)   # 统一混合宏池变更

    # 三列布局: 列表 / 编辑 / 候选按键面板
    COL1_W = 280     # 指令列表 + 底部 mic/test/language
    COL2_W = 320     # 当前选中指令编辑区
    PADDING = 20
    GUTTER = 20      # 列间距
    WIN_W = 1200
    WIN_H = 960
    COL3_W = WIN_W - PADDING * 2 - COL1_W - COL2_W - GUTTER * 2 - 2  # = 538

    def __init__(self, voice_commands=None, voice_language=None, voice_mic_device=None, parent=None, xmacros=None, voice_auto_start=True, voice_chunk_size=None):
        super().__init__(parent)
        # 统一混合宏池 (xmacros) — 兼容旧 macros (已在 config 加载时迁入)
        self._macros = list(xmacros) if xmacros else []
        # 深拷贝防止编辑过程影响外部数据 (失败时还能 cancel)
        self._commands = [dict(c) for c in (voice_commands or [])]
        self._language = voice_language or get_lang()
        self._saved_mic_device = voice_mic_device  # 之前保存的麦克风设备名
        self._auto_start = voice_auto_start
        self._chunk_size = voice_chunk_size  # None = 用引擎默认 (VOICE_CHUNK_SIZE)
        self._focus_widget = None
        self._current_idx = -1   # 当前选中指令在 _commands 中的索引; -1 表示未选中
        self._drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        _detect_icon_font()
        self._init_ui()
        self._load_commands()
        self._center_on_screen()

    def _init_ui(self):
        fn = get_font()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("vs_container")
        container.setStyleSheet(f"""
            QFrame#vs_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        root.setSpacing(0)

        # ── Title bar ──
        title_row = QHBoxLayout()
        mic_icon = QLabel("\uE720" if _ICON_FONT else "\U0001F3A4")
        if _ICON_FONT:
            mic_icon.setFont(_make_font(_ICON_FONT, 20))
        else:
            mic_icon.setFont(_make_font(fn, 20))
        mic_icon.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(mic_icon)
        title_row.addSpacing(6)

        title_lbl = QLabel(t("voice_dialog.title"))
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        close_btn = QPushButton("\uE711" if _ICON_FONT else "\u2715")
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

        # Tip
        tip = QLabel(t("voice_dialog.tip"))
        tip.setFont(_make_font(fn, 14))
        tip.setStyleSheet("color: #888; background: transparent;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addSpacing(16)

        # ── 三列布局: 指令列表 | 编辑区 | 候选按键面板 ──
        columns = QHBoxLayout()
        columns.setSpacing(0)

        # Col1
        col1 = self._build_col1_list(fn)
        col1.setFixedWidth(self.COL1_W)
        columns.addWidget(col1)
        columns.addSpacing(self.GUTTER)
        d1 = QFrame(); d1.setFixedWidth(1); d1.setStyleSheet("background: #444;")
        columns.addWidget(d1)

        # Col2
        col2 = self._build_col2_editor(fn)
        col2.setFixedWidth(self.COL2_W)
        columns.addSpacing(self.GUTTER - 10)
        columns.addWidget(col2)
        columns.addSpacing(self.GUTTER)
        d2 = QFrame(); d2.setFixedWidth(1); d2.setStyleSheet("background: #444;")
        columns.addWidget(d2)
        columns.addSpacing(10)

        # Col3
        col3 = self._build_right_tabbed_panel(fn)
        columns.addWidget(col3, 1)

        root.addLayout(columns, 1)

        # 数据载入到列表 + 默认选中
        self._rebuild_command_list()
        if self._commands:
            self._cmd_list.setCurrentRow(0)
        else:
            self._update_editor_visibility()

    # ── Col1: 指令列表 + 底部 mic/test/lang ──

    def _build_col1_list(self, fn):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # 指令列表
        self._cmd_list = QListWidget()
        # 列表本身无底色/无边框; 每个条目=灰底小圆角矩形, 条目间距 5px
        self._cmd_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent; border: none;
                color: #E0E0E0; outline: none;
            }}
            QListWidget::item {{
                background: {C_GRAY}; border-radius: 6px;
                padding: 8px 10px; margin-bottom: 5px;
            }}
            QListWidget::item:selected {{
                background: {C_GREEN}; color: #1A1A1A;
            }}
            QListWidget::item:hover {{ background: {C_GRAY_H}; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #404040; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        self._cmd_list.setFont(_make_font(fn, 14))
        self._cmd_list.currentRowChanged.connect(self._on_list_row_changed)
        v.addWidget(self._cmd_list, 1)

        # 新建按钮
        add_btn = QPushButton(t("voice_dialog.add_command"))
        add_btn.setFixedHeight(36)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFont(_make_font(fn, 14))
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GREEN}; color: #1A1A1A;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GREEN_H}; }}
        """)
        add_btn.clicked.connect(self._on_add_command)
        v.addWidget(add_btn)

        v.addSpacing(8)
        sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet("background: #444;")
        v.addWidget(sep)
        v.addSpacing(8)

        # 底部固定区: 麦克风 / 测试 / 语言
        v.addLayout(self._build_bottom_status(fn))
        return wrap

    def _build_bottom_status(self, fn):
        col = QVBoxLayout()
        col.setSpacing(8)

        # 麦克风状态点 + 设备下拉
        mic_row = QHBoxLayout()
        mic_row.setSpacing(6)
        self._mic_dot = QLabel("\u25CF")
        self._mic_dot.setFont(_make_font(fn, 12))
        self._mic_dot.setStyleSheet("color: #666; background: transparent;")
        mic_row.addWidget(self._mic_dot)
        self._mic_lbl = QLabel(t("voice_dialog.mic_status"))
        self._mic_lbl.setFont(_make_font(fn, 11))
        self._mic_lbl.setStyleSheet("color: #AAA; background: transparent;")
        mic_row.addWidget(self._mic_lbl)
        mic_row.addStretch()
        # 运行时启用语音 — 右对齐到麦克风状态行, 字号与左侧一致 (省一行)
        self._auto_start_cb = _CheckToggle(
            t("voice_dialog.auto_start"), fn, checked=self._auto_start,
            label_px=11, accent=C_GREEN)
        mic_row.addWidget(self._auto_start_cb)
        col.addLayout(mic_row)

        self._mic_combo = QComboBox()
        self._mic_combo.setFixedHeight(30)
        self._mic_combo.setFont(_make_font(fn, 12))
        self._mic_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C_INPUT_BG}; color: #E0E0E0;
                border: 1px solid {C_GRAY}; border-radius: 6px;
                padding: 2px 28px 2px 8px;
            }}
            QComboBox:hover {{ border-color: #666; }}
            QComboBox::drop-down {{
                border: none; width: 22px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox QAbstractItemView {{
                background: #2A2A2A; color: #E0E0E0;
                selection-background-color: {C_CYBER};
                border: 1px solid #444; border-radius: 4px;
            }}
        """)
        col.addWidget(self._mic_combo)

        # 测试指令按钮 + 左侧「识别延迟」齿轮小按钮
        test_row = QHBoxLayout()
        test_row.setSpacing(6)

        # 设置 (识别延迟) — Segoe Fluent 齿轮 icon + 「设置」文本 (内嵌两 label 混排字体)
        # 用 _LangBtn (按内部 layout 算 sizeHint), 否则普通 QPushButton 不撑开宽度
        self._chunk_btn = _LangBtn()
        self._chunk_btn.setFixedHeight(32)
        self._chunk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chunk_btn.setToolTip(t("voice_dialog.chunk_tooltip"))
        self._chunk_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        _cb_lay = QHBoxLayout(self._chunk_btn)
        _cb_lay.setContentsMargins(14, 0, 14, 0)
        _cb_lay.setSpacing(6)
        _cb_gear = QLabel("" if _ICON_FONT else "⚙")
        _cb_gear.setFont(_make_font(_ICON_FONT, 15) if _ICON_FONT else _make_font(fn, 15))
        _cb_gear.setStyleSheet("color: #E0E0E0; background: transparent;")
        _cb_gear.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        _cb_lay.addWidget(_cb_gear)
        _cb_txt = QLabel(t("voice_dialog.settings_btn"))
        _cb_txt.setFont(_make_font(fn, 13))
        _cb_txt.setStyleSheet("color: #E0E0E0; background: transparent;")
        _cb_txt.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        _cb_lay.addWidget(_cb_txt)
        self._chunk_btn.clicked.connect(self._on_open_chunk_dialog)
        test_row.addWidget(self._chunk_btn)

        # 测试指令按钮
        self._test_btn = QPushButton(t("voice_dialog.test_cmd"))
        self._test_btn.setFixedHeight(32)
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setFont(_make_font(fn, 13))
        self._test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GREEN}; color: #333333;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: #34D399; }}
        """)
        self._test_btn.clicked.connect(self._on_test_commands)
        test_row.addWidget(self._test_btn, 1)
        col.addLayout(test_row)

        # 语言下拉 (识别语言)
        lang_row = QHBoxLayout()
        lang_row.setSpacing(6)
        lang_lbl = QLabel(t("voice_dialog.language"))
        lang_lbl.setFont(_make_font(fn, 12))
        lang_lbl.setStyleSheet("color: #AAA; background: transparent;")
        lang_row.addWidget(lang_lbl)
        self._lang_combo = QComboBox()
        self._lang_combo.setFixedHeight(30)
        self._lang_combo.setFont(_make_font(fn, 12))
        self._lang_combo.setStyleSheet(self._mic_combo.styleSheet())
        self._lang_combo.addItem(t("voice_dialog.language_zh"), "zh-CN")
        self._lang_combo.addItem(t("voice_dialog.language_en"), "en")
        # 选中当前
        idx = 0 if self._language.startswith("zh") else 1
        self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_combo_changed)
        lang_row.addWidget(self._lang_combo, 1)
        col.addLayout(lang_row)

        # 枚举设备 (与原版相同逻辑)
        self._mic_devices = []
        self._populate_mic_devices()
        return col

    def _on_lang_combo_changed(self, idx):
        self._language = self._lang_combo.itemData(idx)

    # ── Col2: 当前选中指令编辑 ──

    def _build_col2_editor(self, fn):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 未选中时显示的占位标签
        self._editor_hint = QLabel(t("voice_dialog.select_hint"))
        self._editor_hint.setFont(_make_font(fn, 14))
        self._editor_hint.setStyleSheet("color: #666; background: transparent;")
        self._editor_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_hint.setWordWrap(True)
        v.addWidget(self._editor_hint, 1)

        # 编辑表单容器
        self._editor_form = QWidget()
        self._editor_form.setStyleSheet("background: transparent;")
        form = QVBoxLayout(self._editor_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(14)

        # 名称
        name_lbl = QLabel(t("voice_dialog.phrase"))
        name_lbl.setFont(_make_font(fn, 14))
        name_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        form.addWidget(name_lbl)
        self._phrase_edit = QLineEdit()
        self._phrase_edit.setPlaceholderText(t("voice_dialog.phrase_placeholder"))
        self._phrase_edit.setFixedHeight(36)
        self._phrase_edit.setFont(_make_font(fn, 14))
        self._phrase_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C_INPUT_BG}; color: white;
                border: 2px solid {C_GRAY}; border-radius: 6px;
                padding: 2px 8px;
            }}
            QLineEdit:focus {{ border-color: {C_GREEN}; }}
        """)
        self._phrase_edit.textChanged.connect(self._on_phrase_changed)
        form.addWidget(self._phrase_edit)

        # 触发按键 (TagInput)
        keys_lbl = QLabel(t("voice_dialog.keys"))
        keys_lbl.setFont(_make_font(fn, 14))
        keys_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        form.addWidget(keys_lbl)
        self._keys_input = TagInput(initial_value="", accent_color=C_AMBER)
        self._keys_input.setMinimumHeight(36)
        self._keys_input.focusChanged.connect(self._on_focus_changed)
        # TagInput 没有 textChanged 信号; 编辑(add/remove tag)后用一个 timer 同步
        form.addWidget(self._keys_input)

        # 动作
        act_lbl = QLabel(t("voice_dialog.action"))
        act_lbl.setFont(_make_font(fn, 14))
        act_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        form.addWidget(act_lbl)
        act_row = QHBoxLayout()
        act_row.setSpacing(6)
        self._action_btns = {}
        self._current_action = 'click'
        for k, label in (('click', t("voice_dialog.action_click")),
                          ('press', t("voice_dialog.action_press")),
                          ('release', t("voice_dialog.action_release"))):
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(_make_font(fn, 13))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, kk=k: self._on_action_clicked(kk))
            act_row.addWidget(btn)
            self._action_btns[k] = btn
        form.addLayout(act_row)
        self._update_action_btn_styles()

        form.addStretch()

        # 底部操作: 复制 / 删除‖保存
        copy_btn = QPushButton(t("voice_dialog.copy"))
        copy_btn.setFixedHeight(36)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(_make_font(fn, 14))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        copy_btn.clicked.connect(self._on_copy_command)
        form.addWidget(copy_btn)

        del_save_row = QHBoxLayout()
        del_save_row.setSpacing(8)
        del_btn = QPushButton(t("voice_dialog.delete_command"))
        del_btn.setFixedHeight(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFont(_make_font(fn, 14))
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        del_btn.clicked.connect(self._on_delete_current)
        del_save_row.addWidget(del_btn, 1)

        save_btn = QPushButton(t("voice_dialog.save"))
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(_make_font(fn, 16, bold=True))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GREEN}; color: #1A1A1A;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GREEN_H}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        del_save_row.addWidget(save_btn, 1)
        form.addLayout(del_save_row)

        v.addWidget(self._editor_form)
        self._editor_form.setVisible(False)
        return wrap

    def _update_editor_visibility(self):
        has = (self._current_idx >= 0 and self._current_idx < len(self._commands))
        self._editor_form.setVisible(has)
        self._editor_hint.setVisible(not has)

    # ── (legacy 原文未删, 下面是 _build_lang_selector 旧代码, 已不再被调用) ──

    def _build_lang_selector_legacy(self, fn):
        row = QHBoxLayout()
        row.setSpacing(8)

        lang_lbl = QLabel(t("voice_dialog.language"))
        lang_lbl.setFont(_make_font(fn, 16, bold=True))
        lang_lbl.setStyleSheet("color: #CCC; background: transparent;")
        row.addWidget(lang_lbl)
        row.addSpacing(12)

        is_zh = self._language.startswith("zh")

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
        self._zh_text = QLabel("中文")
        self._zh_text.setFont(_make_font(fn, 16, bold=True))
        self._zh_text.setStyleSheet("color: #FFF; background: transparent;")
        self._zh_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        zh_lay.addWidget(self._zh_text)
        row.addWidget(self._lang_zh_btn)

        row.addSpacing(8)

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
        self._en_text = QLabel("English")
        self._en_text.setFont(_make_font(fn, 16, bold=True))
        self._en_text.setStyleSheet("color: #FFF; background: transparent;")
        self._en_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        en_lay.addWidget(self._en_text)
        row.addWidget(self._lang_en_btn)

        row.addStretch()

        self._auto_start_cb = _CheckToggle(
            t("voice_dialog.auto_start"), fn, checked=self._auto_start
        )
        row.addWidget(self._auto_start_cb)
        self._update_lang_buttons()
        return row

    def _set_lang(self, lang):
        self._language = lang
        self._update_lang_buttons()

    def _update_lang_buttons(self):
        is_zh = self._language.startswith("zh")

        # 中文按钮: 选中时显示勾 icon
        self._zh_icon_lbl.setVisible(is_zh)
        zh_fg = "#FFF" if is_zh else "#E0E0E0"
        self._zh_text.setStyleSheet(f"color: {zh_fg}; background: transparent;")
        self._zh_icon_lbl.setStyleSheet(f"color: {zh_fg}; background: transparent;")
        self._lang_zh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER if is_zh else '#404040'};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H if is_zh else '#505050'}; }}
        """)

        # English 按钮: 选中时显示勾 icon
        self._en_icon_lbl.setVisible(not is_zh)
        en_fg = "#FFF" if not is_zh else "#E0E0E0"
        self._en_text.setStyleSheet(f"color: {en_fg}; background: transparent;")
        self._en_icon_lbl.setStyleSheet(f"color: {en_fg}; background: transparent;")
        self._lang_en_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CYBER if not is_zh else '#404040'};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CYBER_H if not is_zh else '#505050'}; }}
        """)

    def _build_mic_status(self, fn):
        """构建麦克风状态区: 状态圆点 + 标签 + 设备下拉 + 测试按钮 (单行)"""
        row = QHBoxLayout()
        row.setSpacing(8)

        self._mic_dot = QLabel("\u25CF")
        self._mic_dot.setFont(_make_font(fn, 14))
        self._mic_dot.setStyleSheet("color: #666; background: transparent;")
        row.addWidget(self._mic_dot)

        self._mic_lbl = QLabel(t("voice_dialog.mic_status"))
        self._mic_lbl.setFont(_make_font(fn, 13))
        self._mic_lbl.setStyleSheet("color: #AAA; background: transparent;")
        row.addWidget(self._mic_lbl)

        row.addSpacing(4)

        self._mic_combo = QComboBox()
        self._mic_combo.setFixedHeight(32)
        self._mic_combo.setFont(_make_font(fn, 13))
        self._mic_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C_INPUT_BG}; color: #E0E0E0;
                border: 2px solid {C_GRAY}; border-radius: 6px;
                padding: 2px 28px 2px 8px;
            }}
            QComboBox:hover {{ border-color: #666; }}
            QComboBox::drop-down {{
                border: none; width: 28px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox QAbstractItemView {{
                background: #2A2A2A; color: #E0E0E0;
                selection-background-color: {C_CYBER};
                border: 1px solid #444; border-radius: 4px;
            }}
        """)
        row.addWidget(self._mic_combo, 1)

        self._test_btn = QPushButton(t("voice_test.btn"))
        self._test_btn.setFixedSize(100, 32)
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setFont(_make_font(fn, 13))
        self._test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        self._test_btn.clicked.connect(self._on_test_commands)
        row.addWidget(self._test_btn)

        # Populate devices
        self._mic_devices = []
        self._populate_mic_devices()
        return row

    # 「系统默认」的内部标记值 (不会与任何真实设备名冲突)
    _MIC_DEFAULT_TAG = "__system_default__"

    def _populate_mic_devices(self):
        """枚举麦克风设备 — 仅保留 WASAPI 后端 + 首项「系统默认」"""
        self._mic_combo.clear()
        self._mic_devices = []  # list of (sd_index | None, display_name)
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            host_apis = sd.query_hostapis()

            # 找到 WASAPI 的 hostapi index (Windows 推荐 API)
            wasapi_idx = None
            for hi, ha in enumerate(host_apis):
                if 'WASAPI' in ha.get('name', ''):
                    wasapi_idx = hi
                    break

            # ── 第 1 项: 系统默认 ──
            default_label = t("voice_dialog.mic_system_default")
            self._mic_combo.addItem(default_label, self._MIC_DEFAULT_TAG)
            self._mic_devices.append((None, default_label))

            # ── 遍历设备，只取 WASAPI (或全部取 + 去重) ──
            seen = set()
            for i, d in enumerate(devs):
                if d.get('max_input_channels', 0) <= 0:
                    continue
                # 优先只保留 WASAPI 后端的设备
                if wasapi_idx is not None and d.get('hostapi') != wasapi_idx:
                    continue
                raw_name = d.get('name', f'Device {i}')
                # 清洗: 去掉尾部可能的 host api 标注
                clean = raw_name.strip()
                if clean in seen:
                    continue
                seen.add(clean)
                self._mic_devices.append((i, clean))
                self._mic_combo.addItem(clean, i)

            # 如果 WASAPI 没找到任何设备，回退: 取全部后端去重
            if len(self._mic_devices) <= 1 and wasapi_idx is not None:
                seen.clear()
                for i, d in enumerate(devs):
                    if d.get('max_input_channels', 0) <= 0:
                        continue
                    raw_name = d.get('name', f'Device {i}')
                    clean = raw_name.strip()
                    if clean in seen:
                        continue
                    seen.add(clean)
                    self._mic_devices.append((i, clean))
                    self._mic_combo.addItem(clean, i)

            if len(self._mic_devices) > 1:
                # 至少有 1 个真实设备 (除去「系统默认」)
                self._mic_dot.setStyleSheet("color: #10B981; background: transparent;")
                self._mic_lbl.setText(t("voice_dialog.mic_ready"))
                self._test_btn.setEnabled(True)
                # 恢复之前保存的设备
                if self._saved_mic_device and self._saved_mic_device != self._MIC_DEFAULT_TAG:
                    idx = self._mic_combo.findText(self._saved_mic_device)
                    if idx >= 0:
                        self._mic_combo.setCurrentIndex(idx)
                    # else: 设备已拔出，回落到「系统默认」(index 0)
                # 否则保持「系统默认」(index 0)
            elif len(self._mic_devices) == 1:
                # 只有「系统默认」，没有真实设备
                self._mic_dot.setStyleSheet("color: #EF4444; background: transparent;")
                self._mic_lbl.setText(t("voice_dialog.mic_not_found"))
                self._test_btn.setEnabled(False)
            else:
                self._mic_dot.setStyleSheet("color: #EF4444; background: transparent;")
                self._mic_lbl.setText(t("voice_dialog.mic_not_found"))
                self._test_btn.setEnabled(False)
        except (ImportError, OSError):
            self._mic_dot.setStyleSheet("color: #EF4444; background: transparent;")
            self._mic_lbl.setText(t("voice_dialog.mic_dep_missing"))
            self._test_btn.setEnabled(False)
        except Exception:
            self._mic_dot.setStyleSheet("color: #F59E0B; background: transparent;")
            self._mic_lbl.setText(t("voice_dialog.mic_check_failed"))
            self._test_btn.setEnabled(False)

    def _on_test_commands(self):
        """收集当前指令列表，打开语音指令测试弹窗。

        测试弹窗以 self 为 parent，确保:
        - 设置弹窗关闭时，测试弹窗也会被正确清理
        - 不会出现孤立的测试弹窗持有已销毁引擎的引用
        """
        # 关闭已有的测试弹窗
        if hasattr(self, '_test_dlg') and self._test_dlg is not None:
            try:
                self._test_dlg.close()
            except RuntimeError:
                pass
            self._test_dlg = None

        # 先把编辑器当前值回写, 再收集
        self._pull_editor_to_command()
        commands = [dict(c) for c in self._commands
                    if (c.get('phrase') or '').strip()]
        if not commands:
            return

        from views.voice_test_dialog import VoiceTestDialog
        mic = self.get_selected_mic()
        self._test_dlg = VoiceTestDialog(commands, self._language, parent=self, mic_device=mic)
        self._test_dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._test_dlg.destroyed.connect(lambda: setattr(self, '_test_dlg', None))
        self._test_dlg.show()

    def _on_open_chunk_dialog(self):
        """打开「识别延迟」调整子弹窗。"""
        dlg = _ChunkSizeDialog(self._chunk_size, parent=self)
        if dlg.exec():
            self._chunk_size = dlg.get_value()  # int 或 None(=默认)

    def get_selected_mic(self):
        """返回当前选中的麦克风设备名; 「系统默认」返回 None"""
        if not self._mic_devices:
            return None
        data = self._mic_combo.currentData()
        if data == self._MIC_DEFAULT_TAG:
            return None  # 系统默认 → 不指定 device
        return self._mic_combo.currentText()

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
                layout.addSpacing(20)
            cat_lbl = QLabel(f"── {cat_name} ──")
            cat_lbl.setFont(_make_font(fn, 14, bold=True))
            cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
            layout.addWidget(cat_lbl)
            layout.addSpacing(8)
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

    # ── 右栏 Tab 面板 (浏览模式，无管理) ──

    def _build_right_tabbed_panel(self, fn):
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(8)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self._tab_keys_btn = QPushButton(t("macro.tab_keys"))
        self._tab_mouse_btn = QPushButton(t("macro.tab_mouse"))
        self._tab_gp_btn = QPushButton(t("macro.tab_gp"))
        self._tab_macros_btn = QPushButton(t("macro.tab_macros"))
        self._tab_btns = (self._tab_keys_btn, self._tab_gp_btn,
                          self._tab_mouse_btn, self._tab_macros_btn)
        for i, b in enumerate(self._tab_btns):
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(_make_font(fn, 14, bold=True))
            b.clicked.connect(lambda _, ix=i: self._switch_tab(ix))
            tab_row.addWidget(b)
        tab_row.addStretch()
        panel_lay.addLayout(tab_row)
        panel_lay.addSpacing(10)

        self._tab_stack = QStackedWidget()
        self._tab_stack.setStyleSheet("background: transparent;")
        self._tab_stack.addWidget(self._build_key_palette(fn))      # 0 键盘
        self._tab_stack.addWidget(self._build_gp_palette(fn))       # 1 手柄
        self._tab_stack.addWidget(self._build_mouse_palette(fn))    # 2 鼠标
        self._tab_stack.addWidget(self._build_macro_browse(fn))     # 3 宏
        panel_lay.addWidget(self._tab_stack, 1)
        self._switch_tab(0)
        return panel

    def _build_gp_palette(self, fn):
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
        self._gp_palette_layout = lay
        populate_gp_palette(lay, fn, self._on_gp_key_clicked, self)
        scroll.setWidget(body)
        return scroll

    def _on_gp_key_clicked(self, label):
        storage = GP_LABEL_TO_KEY.get(label, label)
        self._on_key_clicked(GP_KEY_PREFIX + storage)

    def _switch_tab(self, idx):
        self._tab_stack.setCurrentIndex(idx)
        sel = f"QPushButton {{ background: transparent; color: #FFF; border: none; border-bottom: 2px solid {C_GREEN}; border-radius: 0; padding: 0 14px 4px 14px; }} QPushButton:hover {{ color: #FFF; }}"
        off = f"QPushButton {{ background: transparent; color: #AAA; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 0 14px 4px 14px; }} QPushButton:hover {{ color: #E0E0E0; }}"
        for ix, b in enumerate(self._tab_btns):
            b.setStyleSheet(sel if idx == ix else off)

    def _build_mouse_palette(self, fn):
        """构建鼠标操作 Tab: 分类标签 + 5 个鼠标按键 flow"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)

        cat_lbl = QLabel(f"── {t('key_cat.mouse_buttons')} ──")
        cat_lbl.setFont(_make_font(fn, 14, bold=True))
        cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        lay.addWidget(cat_lbl)
        lay.addSpacing(8)

        mouse_keys = _get_mouse_keys()
        mouse_display_names = [label for label, _ in mouse_keys]
        mouse_tag_values = [tag for _, tag in mouse_keys]
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        flow = _FlowWidget(
            mouse_display_names,
            lambda name: self._on_mouse_key_clicked(name),
            fn, container
        )
        c_lay = QVBoxLayout(container)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(0)
        c_lay.addWidget(flow)
        lay.addWidget(container)

        self._mouse_name_to_tag = dict(zip(mouse_display_names, mouse_tag_values))

        lay.addStretch()
        return page

    def _on_mouse_key_clicked(self, display_name):
        tag = self._mouse_name_to_tag.get(display_name, display_name)
        self._on_key_clicked(tag)

    C_MACRO = "#8B5CF6"
    MAX_MACROS = 20

    def _build_macro_browse(self, fn):
        """构建宏 Tab: 横条列表 + 底部「新建」按钮 (完整管理模式)"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # 分类标题 (与常规按键分类标签风格一致)
        cat_lbl = QLabel(f"── {t('macro.macro_list_label')} ──")
        cat_lbl.setFont(_make_font(fn, 14, bold=True))
        cat_lbl.setStyleSheet(f"color: {C_CAT_LABEL}; background: transparent;")
        cat_lbl.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(cat_lbl)

        # 宏列表 (QListWidget)
        self._macro_list = QListWidget()
        self._macro_list.setStyleSheet(f"""
            QListWidget {{
                background: {C_PM_BG};
                border: none; outline: none;
            }}
            QListWidget::item {{
                background: transparent; padding: 0px;
                border: none; margin-right: 0px;
            }}
            QListWidget::item:selected {{ background: transparent; }}
            QListWidget::item:hover {{ background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #404040; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        self._macro_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._macro_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self._macro_list, 1)

        # 底部「新建」按钮 (紫色, icon + 文字双 label)
        _detect_icon_font()
        new_btn = QPushButton()
        new_btn.setFixedHeight(40)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.C_MACRO}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: #7C3AED; }}
        """)
        nb_lay = QHBoxLayout(new_btn)
        nb_lay.setContentsMargins(0, 0, 0, 0)
        nb_lay.setSpacing(4)
        nb_lay.addStretch()
        if _ICON_FONT:
            nb_icon = QLabel("\uE710")
            nb_icon.setFont(_make_font(_ICON_FONT, 16))
        else:
            nb_icon = QLabel("+")
            nb_icon.setFont(_make_font(fn, 16, bold=True))
        nb_icon.setStyleSheet("color: #FFF; background: transparent;")
        nb_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        nb_lay.addWidget(nb_icon)
        nb_text = QLabel(t("macro.new"))
        nb_text.setFont(_make_font(fn, 16))
        nb_text.setStyleSheet("color: #FFF; background: transparent;")
        nb_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        nb_lay.addWidget(nb_text)
        nb_lay.addStretch()
        new_btn.clicked.connect(self._new_macro)
        lay.addWidget(new_btn)

        # 延迟到下一帧事件循环再填充列表，确保 QListWidget 已完成布局
        QTimer.singleShot(0, self._rebuild_macro_list)
        return page

    def _rebuild_macro_list(self):
        """重建宏列表 (横条风格, 参考 _ProfileRowWidget)"""
        fn = get_font()
        _detect_icon_font()
        self._macro_list.clear()

        ROW_H = 40

        if not self._macros:
            hint_item = QListWidgetItem()
            hint_item.setSizeHint(QSize(0, 60))
            hint_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._macro_list.addItem(hint_item)
            hint = QLabel(t("macro.no_macros_hint"))
            hint.setFont(_make_font(fn, 14))
            hint.setStyleSheet("color: #666; background: transparent;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            self._macro_list.setItemWidget(hint_item, hint)
            return

        for i, macro in enumerate(self._macros):
            name = macro.get('name', f'Macro {i+1}')

            row = QFrame()
            row.setFixedHeight(ROW_H)
            row.setObjectName("macro_row")
            row.setStyleSheet(f"""
                QFrame#macro_row {{
                    background: {C_GRAY}; border-radius: 6px;
                }}
                QFrame#macro_row:hover {{
                    background: {self.C_MACRO};
                }}
            """)
            row.setCursor(Qt.CursorShape.PointingHandCursor)

            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(15, 0, 10, 0)
            row_lay.setSpacing(6)

            name_lbl = QLabel(name)
            name_lbl.setFont(_make_font(fn, 14))
            name_lbl.setStyleSheet("color: white; background: transparent;")
            name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_lay.addWidget(name_lbl, 1)

            btn_size = 30
            edit_btn = QPushButton()
            edit_btn.setFixedSize(btn_size, btn_size)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if _ICON_FONT:
                edit_btn.setText("\uE70F")
                edit_btn.setFont(_make_font(_ICON_FONT, 14))
            else:
                edit_btn.setText("\u270E")
                edit_btn.setFont(_make_font(fn, 14))
            edit_btn.setStyleSheet("""
                QPushButton { color: white; background: transparent; border: none; }
                QPushButton:hover { background: rgba(255,255,255,0.15); border-radius: 6px; }
            """)
            edit_btn.clicked.connect(lambda _, idx=i: self._edit_macro(idx))
            row_lay.addWidget(edit_btn)

            del_btn = QPushButton()
            del_btn.setFixedSize(btn_size, btn_size)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if _ICON_FONT:
                del_btn.setText("\uE74D")
                del_btn.setFont(_make_font(_ICON_FONT, 14))
            else:
                del_btn.setText("\u2715")
                del_btn.setFont(_make_font(fn, 12))
            del_btn.setStyleSheet("""
                QPushButton { color: white; background: transparent; border: none; }
                QPushButton:hover { background: rgba(255,255,255,0.15); border-radius: 6px; }
            """)
            del_btn.clicked.connect(lambda _, idx=i: self._delete_macro(idx))
            row_lay.addWidget(del_btn)

            row.mousePressEvent = lambda e, n=name: self._insert_macro_tag(n)

            item = QListWidgetItem()
            item.setSizeHint(QSize(0, ROW_H + 10))
            self._macro_list.addItem(item)
            self._macro_list.setItemWidget(item, row)

    def _insert_macro_tag(self, macro_name):
        if self._focus_widget and isinstance(self._focus_widget, TagInput):
            self._focus_widget.add_tag(f"xmacro:{macro_name}")

    def _new_macro(self):
        from views.macro_editor_dialog import MacroEditorDialog
        names = [m.get('name', '') for m in self._macros]
        dlg = MacroEditorDialog(existing_names=names, parent=self, mode='mix')
        dlg.macro_saved.connect(lambda data: self._on_macro_editor_saved(data, -1))
        dlg.exec()

    def _edit_macro(self, idx):
        from views.macro_editor_dialog import MacroEditorDialog
        data = copy.deepcopy(self._macros[idx])
        names = [m.get('name', '') for m in self._macros]
        dlg = MacroEditorDialog(macro_data=data, existing_names=names, parent=self, mode='mix')
        dlg.macro_saved.connect(lambda d: self._on_macro_editor_saved(d, idx))
        dlg.exec()

    def _delete_macro(self, idx):
        from views.profile_manager_dialog import _StyledConfirmDialog
        name = self._macros[idx].get('name', '')
        msg = t("macro.confirm_delete").replace("{name}", name)
        dlg = _StyledConfirmDialog(
            t("macro.confirm_delete_title"), msg,
            parent=self, accent_color="#8B5CF6")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._macros.pop(idx)
            self._rebuild_macro_list()
            self.xmacros_changed.emit(self._macros)

    def _on_macro_editor_saved(self, data, idx):
        if 0 <= idx < len(self._macros):
            self._macros[idx] = data
        else:
            self._macros.append(data)
        self._rebuild_macro_list()
        self.xmacros_changed.emit(self._macros)

    def _on_key_clicked(self, key_name):
        if self._focus_widget and isinstance(self._focus_widget, TagInput):
            self._focus_widget.add_tag(key_name)

    # ── 列表 ↔ 编辑同步 ──

    def _load_commands(self):
        # 入口保留 (旧逻辑无 op, 真正载入由 _rebuild_command_list 完成)
        pass

    def _rebuild_command_list(self):
        """从 self._commands 重建左侧列表。"""
        self._cmd_list.blockSignals(True)
        self._cmd_list.clear()
        for cmd in self._commands:
            self._cmd_list.addItem(self._display_name(cmd))
        self._cmd_list.blockSignals(False)

    def _display_name(self, cmd: dict) -> str:
        phrase = (cmd.get('phrase') or '').strip()
        return phrase if phrase else t("voice_dialog.unnamed")

    def _refresh_current_list_item(self):
        """当前指令的 phrase 变化时, 同步刷新列表显示。"""
        if 0 <= self._current_idx < self._cmd_list.count():
            item = self._cmd_list.item(self._current_idx)
            item.setText(self._display_name(self._commands[self._current_idx]))

    def _on_list_row_changed(self, row: int):
        # 切换前先把编辑器当前 TagInput 内容回写
        self._pull_editor_to_command()
        self._current_idx = row
        if 0 <= row < len(self._commands):
            self._load_command_to_editor(self._commands[row])
        else:
            self._current_idx = -1
        self._update_editor_visibility()

    def _load_command_to_editor(self, cmd: dict):
        """把 cmd 内容载入编辑器 widgets。"""
        self._phrase_edit.blockSignals(True)
        self._phrase_edit.setText(cmd.get('phrase', ''))
        self._phrase_edit.blockSignals(False)
        # TagInput 没有 setValue 方法, 重置 tags 列表后重建
        self._keys_input.tags = [p.strip() for p in cmd.get('keys', '').split('+') if p.strip()]
        self._keys_input._build_tags()
        self._current_action = cmd.get('action', 'click')
        self._update_action_btn_styles()

    def _pull_editor_to_command(self):
        """把编辑器当前值回写到 _commands[_current_idx] (主要为 TagInput 同步)。"""
        if not (0 <= self._current_idx < len(self._commands)):
            return
        self._commands[self._current_idx]['phrase'] = self._phrase_edit.text().strip()
        self._commands[self._current_idx]['keys'] = self._keys_input.get_value()
        self._commands[self._current_idx]['action'] = self._current_action

    def _on_phrase_changed(self, text):
        if 0 <= self._current_idx < len(self._commands):
            self._commands[self._current_idx]['phrase'] = text.strip()
            self._refresh_current_list_item()

    def _on_action_clicked(self, action):
        self._current_action = action
        self._update_action_btn_styles()
        if 0 <= self._current_idx < len(self._commands):
            self._commands[self._current_idx]['action'] = action

    def _update_action_btn_styles(self):
        for k, btn in self._action_btns.items():
            if k == self._current_action:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_GREEN}; color: #1A1A1A;
                        border: none; border-radius: 6px; padding: 0 12px;
                    }}
                    QPushButton:hover {{ background: {C_GREEN_H}; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #404040; color: #AAA;
                        border: none; border-radius: 6px; padding: 0 12px;
                    }}
                    QPushButton:hover {{ background: #505050; }}
                """)

    def _on_add_command(self):
        new_cmd = {'phrase': '', 'keys': '', 'action': 'click'}
        self._commands.append(new_cmd)
        self._cmd_list.addItem(self._display_name(new_cmd))
        self._cmd_list.setCurrentRow(len(self._commands) - 1)

    def _on_copy_command(self):
        if not (0 <= self._current_idx < len(self._commands)):
            return
        self._pull_editor_to_command()
        src = self._commands[self._current_idx]
        new_cmd = dict(src)
        self._commands.insert(self._current_idx + 1, new_cmd)
        self._rebuild_command_list()
        self._cmd_list.setCurrentRow(self._current_idx + 1)

    def _on_delete_current(self):
        if not (0 <= self._current_idx < len(self._commands)):
            return
        idx = self._current_idx
        # 先脱离选中, 避免 currentRowChanged 把空 commands 又载入
        self._cmd_list.blockSignals(True)
        self._commands.pop(idx)
        self._cmd_list.takeItem(idx)
        self._cmd_list.blockSignals(False)
        if self._commands:
            new_idx = min(idx, len(self._commands) - 1)
            self._cmd_list.setCurrentRow(new_idx)
        else:
            self._current_idx = -1
            self._update_editor_visibility()

    def _on_focus_changed(self, widget):
        self._focus_widget = widget

    # ── Save ──

    def _on_save(self):
        # 先把编辑器当前值回写
        self._pull_editor_to_command()
        # 过滤空 phrase
        self._result_commands = [dict(c) for c in self._commands
                                  if (c.get('phrase') or '').strip()]
        self._result_language = self._language
        self.settings_saved.emit()
        self.accept()

    def get_result(self):
        return {
            'voice_commands': getattr(self, '_result_commands', []),
            'voice_language': getattr(self, '_result_language', self._language),
            'voice_enabled': len(getattr(self, '_result_commands', [])) > 0,
            'voice_mic_device': self.get_selected_mic(),
            'voice_auto_start': self._auto_start_cb.isChecked(),
            'voice_chunk_size': self._chunk_size,
        }

    # ── Positioning ──

    def _center_on_screen(self):
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # ── Drag ──

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
