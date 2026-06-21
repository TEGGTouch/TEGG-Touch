"""
TEGG Touch 蛋挞 (PyQt6) - profile_manager_dialog.py
方案管理弹窗 — 列表（行内编辑/删除/导出）、新建、复制、导入。
对齐原版 Tkinter 布局。
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QWidget,
    QLineEdit, QFileDialog, QFrame,
    QCheckBox, QRadioButton, QButtonGroup,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent
from PyQt6.QtGui import QFont, QColor

from core.i18n import t, get_font
from core.config_manager import (
    list_profiles, get_active_profile_name,
    create_profile, delete_profile, rename_profile,
    export_profile, import_profile,
    load_profile, save_profile,
)
from views.edit_toolbar import (
    _detect_icon_font, _make_font,
    C_GRAY, C_GRAY_H, C_CLOSE, C_CLOSE_H,
)

# ── 颜色常量 (对齐原版 widgets.py) ──
C_PM_BG = "#2D2D2D"
C_PM_ITEM = "#3A3A3A"
C_PM_SEL = "#F59E0B"
C_PM_HOVER = "#474747"
C_AMBER = "#F59E0B"
C_AMBER_D = "#D97706"

# ── 复用 assets/check.svg + radio_dot.svg (CSS url 需 forward slash) ──
import os
from core.constants import APP_DIR as _APP_DIR
_CHECK_ICON_URL = os.path.join(_APP_DIR, "assets", "check.svg").replace("\\", "/")
_CHECK_AMBER_URL = os.path.join(_APP_DIR, "assets", "check_amber.svg").replace("\\", "/")
_CHECK_DARK_URL = os.path.join(_APP_DIR, "assets", "check_dark.svg").replace("\\", "/")
_RADIO_DOT_URL = os.path.join(_APP_DIR, "assets", "radio_dot_amber.svg").replace("\\", "/")


# ═══════════════════════════════════════════════════════════════
#  通用暗色弹窗 (对齐原版 create_styled_dialog / create_styled_yesno_dialog)
# ═══════════════════════════════════════════════════════════════

class _StyledInputDialog(QDialog):
    """暗色输入弹窗: 标题 + 标签 + 输入框 + 确认按钮。"""

    confirmed = pyqtSignal(str)

    def __init__(self, title, label_text, initial_value="", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 220)
        self._result = None
        self._drag_pos = None

        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        fn = get_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("sid_container")
        container.setStyleSheet(f"""
            QFrame#sid_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题栏
        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # 标签
        lbl = QLabel(label_text)
        lbl.setFont(_make_font(fn, 14))
        lbl.setStyleSheet("color: #CCC; background: transparent;")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        # 输入框
        self._entry = QLineEdit()
        self._entry.setFont(_make_font(fn, 14))
        self._entry.setStyleSheet(f"""
            QLineEdit {{
                background: {C_GRAY}; color: white;
                border: none; border-radius: 6px;
                padding: 8px 12px;
                selection-background-color: {C_AMBER};
                selection-color: black;
            }}
        """)
        if initial_value:
            self._entry.setText(initial_value)
            self._entry.selectAll()
        self._entry.returnPressed.connect(self._on_confirm)
        layout.addWidget(self._entry)

        layout.addStretch()

        # 确认按钮 (琥珀色, 居中)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        confirm_btn = QPushButton(t("dialog.confirm"))
        confirm_btn.setFixedSize(100, 40)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setFont(_make_font(fn, 16))
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_AMBER}; color: black;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_AMBER_D}; }}
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._entry.setFocus()
        self._center_on_screen()

    def _on_confirm(self):
        val = self._entry.text().strip()
        if val:
            self._result = val
            self.confirmed.emit(val)
            self.accept()

    def result_text(self):
        return self._result

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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


class _StyledConfirmDialog(QDialog):
    """暗色确认弹窗: 标题 + 消息 + 是/否 按钮。accent_color 控制确定按钮颜色。"""

    def __init__(self, title, message, parent=None, accent_color=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 200)
        self._drag_pos = None

        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        fn = get_font()

        # 确定按钮配色
        ac = accent_color or C_AMBER
        ac_hover = C_AMBER_D if ac == C_AMBER else ac
        ac_fg = "black" if ac == C_AMBER else "#FFF"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("scd_container")
        container.setStyleSheet(f"""
            QFrame#scd_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题栏
        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # 消息
        msg_lbl = QLabel(message)
        msg_lbl.setFont(_make_font(fn, 14))
        msg_lbl.setStyleSheet("color: white; background: transparent;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        layout.addStretch()

        # 按钮: 是(强调色) | 否(灰)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        yes_btn = QPushButton(t("dialog.yes"))
        yes_btn.setFixedSize(90, 40)
        yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        yes_btn.setFont(_make_font(fn, 16))
        yes_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ac}; color: {ac_fg};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {ac_hover}; }}
        """)
        yes_btn.clicked.connect(self.accept)
        btn_row.addWidget(yes_btn)

        btn_row.addSpacing(20)

        no_btn = QPushButton(t("dialog.no"))
        no_btn.setFixedSize(90, 40)
        no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        no_btn.setFont(_make_font(fn, 16))
        no_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #EEE;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        no_btn.clicked.connect(self.reject)
        btn_row.addWidget(no_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._center_on_screen()

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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


class _StyledMessageDialog(QDialog):
    """暗色消息弹窗: 标题 + 消息 + 确认按钮。用于替代 QMessageBox.warning/information。"""

    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 200)
        self._drag_pos = None

        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        fn = get_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("smd_container")
        container.setStyleSheet(f"""
            QFrame#smd_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题栏
        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setFont(_make_font(fn, 18, bold=True))
        title_lbl.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # 消息
        msg_lbl = QLabel(message)
        msg_lbl.setFont(_make_font(fn, 14))
        msg_lbl.setStyleSheet("color: white; background: transparent;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        layout.addStretch()

        # 确认按钮 (居中)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton(t("dialog.confirm"))
        ok_btn.setFixedSize(100, 40)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setFont(_make_font(fn, 16))
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_AMBER}; color: black;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_AMBER_D}; }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._center_on_screen()

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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


# ═══════════════════════════════════════════════════════════════
#  详情面板 (右侧) — chip 标签 + 4 tab + 4 stacked 详情页
# ═══════════════════════════════════════════════════════════════

class _Chip(QLabel):
    """小色块标签 — 用于动作类型 (Hover/L/R/...)"""

    def __init__(self, text: str, color: str = "#3B82F6", parent=None):
        super().__init__(text, parent)
        self.setFont(_make_font(get_font(), 11, bold=True))
        self.setStyleSheet(f"""
            QLabel {{
                background: {color}; color: white;
                border-radius: 3px; padding: 1px 6px;
            }}
        """)
        self.setFixedHeight(18)


def _make_section_header(text: str, count: int = -1) -> QWidget:
    """详情段落标题, 可选 count 角标"""
    row = QFrame()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lbl = QLabel(text)
    lbl.setFont(_make_font(get_font(), 14, bold=True))
    lbl.setStyleSheet(f"color: {C_AMBER}; background: transparent;")
    h.addWidget(lbl)
    if count >= 0:
        badge = QLabel(f"({count})")
        badge.setFont(_make_font(get_font(), 12))
        badge.setStyleSheet("color: #888; background: transparent;")
        h.addWidget(badge)
    h.addStretch()
    return row


def _make_kv_label(key: str, value: str, value_color: str = "#E0E0E0") -> QWidget:
    """key: value 一行"""
    row = QFrame()
    h = QHBoxLayout(row)
    h.setContentsMargins(12, 0, 0, 0)
    h.setSpacing(8)
    k = QLabel(key)
    k.setFont(_make_font(get_font(), 13))
    k.setStyleSheet("color: #888; background: transparent;")
    k.setMinimumWidth(80)
    h.addWidget(k)
    v = QLabel(str(value))
    v.setFont(_make_font(get_font(), 13))
    v.setStyleSheet(f"color: {value_color}; background: transparent;")
    h.addWidget(v, 1)
    return row


# 动作 chip 颜色 (按动作种类区分)
_ACTION_COLORS = {
    'Hover': '#0284C7',   # 悬停 蓝
    'L':     '#3B82F6',   # 左键 主蓝
    'R':     '#EF4444',   # 右键 红
    'M':     '#A855F7',   # 中键 紫
    'X1':    '#14B8A6',   # 侧键1 青
    'X2':    '#14B8A6',
    '↑滚':   '#F59E0B',   # 滚轮 橙
    '↓滚':   '#F59E0B',
}


def _summarize_button_actions(btn: dict) -> list:
    """从一个按钮 dict 提取非空动作, 返回 [(label, value)] 列表; 全空返回 []"""
    pairs = [
        ('Hover',  btn.get('hover', '')),
        ('L',      btn.get('lclick', '')),
        ('R',      btn.get('rclick', '')),
        ('M',      btn.get('mclick', '')),
        ('X1',     btn.get('xbutton1', '')),
        ('X2',     btn.get('xbutton2', '')),
        ('↑滚',    btn.get('wheelup', '')),
        ('↓滚',    btn.get('wheeldown', '')),
    ]
    return [(lbl, v) for lbl, v in pairs if v]


def _make_button_row(name: str, actions: list) -> QWidget:
    """按钮一行: 名称 + 动作 chips (chip 显示动作类型, tooltip 显示值)"""
    row = QFrame()
    h = QHBoxLayout(row)
    h.setContentsMargins(12, 4, 8, 4)
    h.setSpacing(8)
    n = QLabel(name or "(未命名)")
    n.setFont(_make_font(get_font(), 13))
    n.setStyleSheet("color: #E0E0E0; background: transparent;")
    n.setMinimumWidth(120)
    h.addWidget(n)
    chip_box = QHBoxLayout()
    chip_box.setSpacing(4)
    for label, value in actions:
        chip = _Chip(label, _ACTION_COLORS.get(label, '#666'))
        chip.setToolTip(f"{label} → {value}")
        chip_box.addWidget(chip)
    chip_box.addStretch()
    h.addLayout(chip_box, 1)
    return row


# ═══════════════════════════════════════════════════════════════
#  方案复制 — 分类选择 + 新建/覆盖到已有
# ═══════════════════════════════════════════════════════════════

_CAT_KB = 'kb'
_CAT_GP = 'gp'
_CAT_VOICE = 'voice'
_CAT_GLOBAL = 'global'
_ALL_CATEGORIES = (_CAT_KB, _CAT_GP, _CAT_VOICE, _CAT_GLOBAL)
_CAT_LABELS = {
    _CAT_KB: '键盘按键',
    _CAT_GP: '手柄按钮',
    _CAT_VOICE: '语音指令',
    _CAT_GLOBAL: '全局参数',
}

# 字段归属表
_KB_BUTTON_TYPES = {'normal', 'center_band', None}
_GP_BUTTON_TYPES = {'gp_button', 'gp_stick', 'gp_wheel'}
_WHEEL_FIELDS = (
    'wheel_visible', 'wheel_enlarged', 'wheel_mode', 'wheel_offset',
    'wheel_sectors', 'wheel_center_ring', 'wheel_inner_ring',
    'wheel_outer_sectors', 'wheel_center_ring_visible', 'wheel_middle_ring_visible',
)
_VOICE_FIELDS = (
    'voice_enabled', 'voice_language', 'voice_commands',
    'voice_mic_device', 'voice_auto_start',
)
_GLOBAL_FIELDS = (
    'geometry', 'transparency', 'click_through', 'grid_size', 'scene_scale',
    'sim_mode', 'run_toolbar_x', 'run_toolbar_y',
    'wheel_style', 'cursor_styles',
)


def _is_kb_button(b: dict) -> bool:
    return b.get('type') not in _GP_BUTTON_TYPES


def _is_gp_button(b: dict) -> bool:
    return b.get('type') in _GP_BUTTON_TYPES


def _append_macros_with_suffix(target: list, src: list) -> list:
    """追加宏到 target, 同名加后缀 _2, _3, ..."""
    used = {m.get('name') for m in target if m.get('name')}
    out = list(target)
    for sm in src:
        name = sm.get('name', '')
        if not name:
            continue
        new_name = name
        i = 2
        while new_name in used:
            new_name = f"{name}_{i}"
            i += 1
        nm = dict(sm)
        nm['name'] = new_name
        out.append(nm)
        used.add(new_name)
    return out


def _merge_profiles(src: dict, dst: dict, categories: set, mode: str) -> dict:
    """合并 src 选中类别到 dst.
    mode: 'append' | 'overwrite'; 'global' 类别强制按 overwrite 处理 (无追加语义);
    'kb' 在 append 模式下中心轮盘 wheel_* 字段跳过 (不动 dst 原样)。"""
    merged = dict(dst)  # 浅拷一份
    buttons = list(merged.get('buttons', []))

    # ── 键盘 ──
    if _CAT_KB in categories:
        src_kb = [dict(b) for b in src.get('buttons', []) if _is_kb_button(b)]
        if mode == 'overwrite':
            buttons = [b for b in buttons if _is_gp_button(b)] + src_kb
            for k in _WHEEL_FIELDS:
                if k in src:
                    merged[k] = src[k]
            merged['macros'] = list(src.get('macros', []))
        else:  # append
            buttons = buttons + src_kb
            # 中心轮盘 wheel_* 跳过 (geometry 固定)
            merged['macros'] = _append_macros_with_suffix(
                merged.get('macros', []) or [], src.get('macros', []) or [])

    # ── 手柄 ──
    if _CAT_GP in categories:
        src_gp = [dict(b) for b in src.get('buttons', []) if _is_gp_button(b)]
        if mode == 'overwrite':
            buttons = [b for b in buttons if not _is_gp_button(b)] + src_gp
            merged['gp_macros'] = list(src.get('gp_macros', []))
        else:  # append
            buttons = buttons + src_gp
            merged['gp_macros'] = _append_macros_with_suffix(
                merged.get('gp_macros', []) or [], src.get('gp_macros', []) or [])

    merged['buttons'] = buttons

    # ── 语音 ──
    if _CAT_VOICE in categories:
        if mode == 'overwrite':
            for k in _VOICE_FIELDS:
                if k in src:
                    merged[k] = src[k]
        else:  # append → 只追加 commands
            cur_cmds = list(merged.get('voice_commands', []) or [])
            src_cmds = list(src.get('voice_commands', []) or [])
            merged['voice_commands'] = cur_cmds + src_cmds

    # ── 全局 (无追加语义, 始终覆盖) ──
    if _CAT_GLOBAL in categories:
        for k in _GLOBAL_FIELDS:
            if k in src:
                merged[k] = src[k]

    return merged


class _ProfileCopyDialog(QDialog):
    """方案复制弹窗 — 左:复制内容 (4 类 checkbox + 全部) / 右:目标 (新建 or 已有 + 模式)"""

    def __init__(self, src_name: str, all_profiles: list, parent=None):
        super().__init__(parent)
        self._src_name = src_name
        self._other_profiles = [p for p in all_profiles if p != src_name]
        self._result = None
        self._drag_pos = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(820, 760)
        self._target_kind = 'new'    # 'new' | 'existing'
        self._init_ui()
        self._center_on_screen()
        # 给两张卡片及其所有子部件装事件过滤器, 这样卡片内部的 QListWidget/QLineEdit
        # 也能触发卡片切换 (而不被它们 eat 掉 click)
        self._install_card_event_filter(self._card_new)
        self._install_card_event_filter(self._card_existing)
        self._select_target_card('new')

    def _install_card_event_filter(self, card_widget):
        card_widget.installEventFilter(self)
        for child in card_widget.findChildren(QWidget):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        """卡片或其子部件被点击 → 若该卡片未选中, 切到它"""
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            # 找到 obj 属于哪张卡片
            w = obj
            while w is not None:
                if w is self._card_new and self._target_kind != 'new':
                    self._select_target_card('new')
                    break
                if w is self._card_existing and self._target_kind != 'existing':
                    self._select_target_card('existing')
                    break
                w = w.parentWidget()
        return super().eventFilter(obj, event)

    def _init_ui(self):
        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        fn = get_font()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("pc_container")
        container.setStyleSheet(f"""
            QFrame#pc_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 标题
        hdr = QHBoxLayout()
        title = QLabel("复制方案")
        title.setFont(_make_font(fn, 18, bold=True))
        title.setStyleSheet("color: white; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(_ICON_FONT, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.reject)
        hdr.addWidget(close_btn)
        root.addLayout(hdr)

        # 源
        src_lbl = QLabel(f"源方案: 「{self._src_name}」")
        src_lbl.setFont(_make_font(fn, 14))
        src_lbl.setStyleSheet("color: #888; background: transparent;")
        root.addWidget(src_lbl)

        # 两列 body
        cols = QHBoxLayout()
        cols.setSpacing(20)

        # ── 左: 复制内容 (固定 240w, 几个 checkbox 够用) ──
        left_frame = QFrame()
        left_frame.setFixedWidth(240)
        left_frame.setObjectName("pc_card")
        left_frame.setStyleSheet(
            "QFrame#pc_card { background: #232323; border: 1px solid #3A3A3A; border-radius: 8px; }")
        left = QVBoxLayout(left_frame)
        left.setContentsMargins(16, 14, 16, 14)
        left.setSpacing(8)
        left_title = QLabel("复制内容")
        left_title.setFont(_make_font(fn, 14, bold=True))
        left_title.setStyleSheet(f"color: {C_AMBER}; background: transparent; border: none;")
        left.addWidget(left_title)
        left.addSpacing(4)

        self._cb_all = self._make_checkbox(fn, "全部 (一键全选)")
        self._cb_all.setChecked(True)
        self._cb_all.stateChanged.connect(self._on_all_toggled)
        left.addWidget(self._cb_all)
        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background: #3A3A3A;")
        left.addWidget(sep)

        self._cb_cats = {}
        for cat in _ALL_CATEGORIES:
            cb = self._make_checkbox(fn, _CAT_LABELS[cat])
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_cat_toggled)
            self._cb_cats[cat] = cb
            left.addWidget(cb)
        left.addStretch()
        # 底对齐的提示 (用 1/2/3/4 序号代替 ⓘ)
        hint = QLabel(
            "1. 全局参数总是覆盖\n\n"
            "2. 追加按钮按源坐标贴入, 可能与已有按钮重叠, 需要时手动拖开\n\n"
            "3. 追加模式下中心轮盘跳过, 不动目标\n\n"
            "4. 追加宏同名时自动加后缀 _2/_3 等"
        )
        hint.setFont(_make_font(fn, 14))
        hint.setStyleSheet("color: #999; background: transparent; border: none;")
        hint.setWordWrap(True)
        left.addWidget(hint)
        cols.addWidget(left_frame)

        # ── 右: 粘贴目标 (撑满剩余) — 上下两张大可点击卡片 ──
        right_wrap = QVBoxLayout()
        right_wrap.setContentsMargins(0, 0, 0, 0)
        right_wrap.setSpacing(12)

        # 粘贴目标标题
        target_title = QLabel("粘贴目标 (点卡片切换)")
        target_title.setFont(_make_font(fn, 14, bold=True))
        target_title.setStyleSheet(f"color: {C_AMBER}; background: transparent;")
        right_wrap.addWidget(target_title)

        # 新建卡片
        self._card_new = self._build_target_card_new(fn)
        right_wrap.addWidget(self._card_new)

        # 已有卡片 (撑满剩余高度)
        self._card_existing = self._build_target_card_existing(fn)
        right_wrap.addWidget(self._card_existing, 1)
        cols.addLayout(right_wrap, 1)
        root.addLayout(cols, 1)

        # 默认选中"新建"卡片
        self._target_kind = 'new'

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(140, 44)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFont(_make_font(fn, 16))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addSpacing(10)
        ok_btn = QPushButton("复制确认")
        ok_btn.setFixedSize(160, 44)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setFont(_make_font(fn, 16, bold=True))
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_AMBER}; color: black;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_AMBER_D}; color: white; }}
        """)
        ok_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    # ── 卡片构造 ──

    def _make_clickable_card(self, on_click) -> QFrame:
        """带 amber 边框 (选中) / 灰边 (未选) 的卡片; 鼠标 pointer 提示可点
        实际切换走 eventFilter (覆盖卡片自身 + 所有子部件), 在 _install_card_event_filter 中安装"""
        card = QFrame()
        card.setObjectName("pc_target_card")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        return card

    def _apply_card_style(self, card: QFrame, selected: bool):
        border = C_AMBER if selected else "#3A3A3A"
        bg = "#262220" if selected else "#222222"
        card.setStyleSheet(
            f"QFrame#pc_target_card {{ background: {bg}; "
            f"border: 2px solid {border}; border-radius: 8px; }}")

    def _build_target_card_new(self, fn) -> QFrame:
        card = self._make_clickable_card(lambda: self._select_target_card('new'))
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        title = QLabel("新建方案")
        title.setFont(_make_font(fn, 15, bold=True))
        title.setStyleSheet(f"color: {C_AMBER}; background: transparent; border: none;")
        v.addWidget(title)
        # 内容容器 (单独 widget, setEnabled 切置灰)
        self._new_content = QWidget()
        self._new_content.setStyleSheet("background: transparent;")
        cv = QHBoxLayout(self._new_content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(8)
        name_lbl = QLabel("名称:")
        name_lbl.setFont(_make_font(fn, 13))
        name_lbl.setStyleSheet("color: #CCC; background: transparent; border: none;")
        cv.addWidget(name_lbl)
        self._new_name_edit = QLineEdit(f"{self._src_name}-copy")
        self._new_name_edit.setFont(_make_font(fn, 13))
        self._new_name_edit.setFixedHeight(32)
        self._new_name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C_GRAY}; color: white;
                border: none; border-radius: 4px; padding: 4px 10px;
            }}
            QLineEdit:disabled {{ background: #2A2A2A; color: #555; }}
        """)
        cv.addWidget(self._new_name_edit, 1)
        v.addWidget(self._new_content)
        return card

    def _build_target_card_existing(self, fn) -> QFrame:
        card = self._make_clickable_card(lambda: self._select_target_card('existing'))
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        title = QLabel("粘贴到已有方案")
        title.setFont(_make_font(fn, 15, bold=True))
        title.setStyleSheet(f"color: {C_AMBER}; background: transparent; border: none;")
        v.addWidget(title)
        # 内容容器
        self._existing_content = QWidget()
        self._existing_content.setStyleSheet("background: transparent;")
        cv = QVBoxLayout(self._existing_content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(10)
        self._target_list = QListWidget()
        self._target_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._target_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._apply_target_list_style(active=True)   # 初始按 active 写一份, _select_target_card 会再覆盖
        for name in self._other_profiles:
            self._target_list.addItem(name)
        if self._target_list.count() > 0:
            self._target_list.setCurrentRow(0)
        cv.addWidget(self._target_list, 1)   # 撑满卡片剩余空间
        # 粘贴方式 radio
        mode_lbl = QLabel("粘贴方式:")
        mode_lbl.setFont(_make_font(fn, 13))
        mode_lbl.setStyleSheet("color: #CCC; background: transparent; border: none;")
        cv.addWidget(mode_lbl)
        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._rb_append = self._make_radio(fn, "追加")
        self._rb_overwrite = self._make_radio(fn, "覆盖")
        self._rb_overwrite.setChecked(True)
        self._mode_group.addButton(self._rb_append)
        self._mode_group.addButton(self._rb_overwrite)
        mode_row.addWidget(self._rb_append)
        mode_row.addSpacing(24)
        mode_row.addWidget(self._rb_overwrite)
        mode_row.addStretch()
        cv.addLayout(mode_row)
        v.addWidget(self._existing_content, 1)
        return card

    def _select_target_card(self, kind: str):
        """切换两张卡片的选中态: kind ∈ {'new', 'existing'}"""
        self._target_kind = kind
        is_new = (kind == 'new')
        self._apply_card_style(self._card_new, is_new)
        self._apply_card_style(self._card_existing, not is_new)
        # 未选中卡片的内容 setEnabled(False) → Qt 自动置灰
        self._new_content.setEnabled(is_new)
        self._existing_content.setEnabled(not is_new)
        # 手动换 list 样式: 已有卡片选中时 selected 高亮 = amber; 否则 = 亮灰
        # (Qt 的 :disabled::item:selected chain selector 不可靠, 手动控制更稳)
        self._apply_target_list_style(active=(not is_new))

    def _apply_target_list_style(self, active: bool):
        """active=True → 选中项 amber; active=False → 选中项亮灰 (卡片未选中态)"""
        sel_bg = C_AMBER if active else "#6A6A6A"
        sel_fg = "black" if active else "#CCC"
        self._target_list.setStyleSheet(f"""
            QListWidget {{
                background: {C_PM_BG}; border: 1px solid #3A3A3A; border-radius: 4px;
                color: #E0E0E0; padding: 4px;
                outline: none;
            }}
            QListWidget::item {{ padding: 6px 8px; border-radius: 3px; }}
            QListWidget::item:hover {{ background: rgba(255,255,255,0.06); }}
            QListWidget::item:selected {{
                background: {sel_bg}; color: {sel_fg};
            }}
            /* 自定义窄滚动条 (跟 profile_manager 主列表一致) */
            QScrollBar:vertical {{
                background: transparent; width: 8px; border: none; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #404040; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #555; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QScrollBar:horizontal {{ height: 0; }}
        """)

    def _make_checkbox(self, fn, text):
        """amber 实底 (checked) + 深灰 ✓ — 跟 cursor 那种 amber 满底视觉一致"""
        cb = QCheckBox(text)
        cb.setFont(_make_font(fn, 14))
        cb.setStyleSheet(f"""
            QCheckBox {{ color: #E0E0E0; background: transparent; border: none; spacing: 8px; }}
            QCheckBox:disabled {{ color: #666; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 3px;
                border: 2px solid #555; background: {C_GRAY};
            }}
            QCheckBox::indicator:hover {{ border-color: {C_AMBER}; }}
            QCheckBox::indicator:checked {{
                background: {C_AMBER}; border: 2px solid {C_AMBER};
                image: url({_CHECK_DARK_URL});
            }}
            QCheckBox::indicator:checked:hover {{
                background: {C_AMBER_D}; border-color: {C_AMBER_D};
            }}
        """)
        return cb

    def _make_radio(self, fn, text):
        """复刻 gp_stick_editor._build_radio 的样式: 选中带圆点 SVG"""
        rb = QRadioButton(text)
        rb.setFont(_make_font(fn, 14))
        rb.setStyleSheet(f"""
            QRadioButton {{ color: #E0E0E0; background: transparent; border: none; spacing: 8px; }}
            QRadioButton::indicator {{
                width: 16px; height: 16px; border-radius: 9px;
                border: 2px solid #666; background: {C_PM_BG};
            }}
            QRadioButton::indicator:hover {{ border-color: {C_AMBER}; }}
            QRadioButton::indicator:checked {{
                border: 2px solid {C_AMBER}; background: {C_PM_BG};
                image: url({_RADIO_DOT_URL});
            }}
            QRadioButton::indicator:checked:hover {{
                border: 2px solid {C_AMBER_D};
            }}
        """)
        return rb

    def _on_all_toggled(self, state):
        if self.sender() is not self._cb_all:
            return
        checked = self._cb_all.isChecked()
        for cb in self._cb_cats.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)

    def _on_cat_toggled(self, state):
        all_checked = all(cb.isChecked() for cb in self._cb_cats.values())
        self._cb_all.blockSignals(True)
        self._cb_all.setChecked(all_checked)
        self._cb_all.blockSignals(False)

    def _on_confirm(self):
        cats = {cat for cat, cb in self._cb_cats.items() if cb.isChecked()}
        if not cats:
            _StyledMessageDialog("无效", "请至少选择一个类别复制", self).exec()
            return
        if self._target_kind == 'new':
            target_name = self._new_name_edit.text().strip()
            if not target_name:
                _StyledMessageDialog("无效", "请填写新方案名称", self).exec()
                return
            mode = 'overwrite'    # 新建对模板覆盖
        else:
            cur_item = self._target_list.currentItem()
            if not cur_item:
                _StyledMessageDialog("无效", "请选一个目标方案", self).exec()
                return
            target_name = cur_item.text()
            mode = 'append' if self._rb_append.isChecked() else 'overwrite'
        self._result = (cats, self._target_kind, target_name, mode)
        self.accept()

    def get_result(self):
        return self._result

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
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


class _ProfileDetailPanel(QFrame):
    """右侧方案详情面板 — 顶部方案名 + 4 个 tab + 4 stacked 详情页"""

    apply_clicked = pyqtSignal(str)   # 点「应用此方案」时发出 (传方案名)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cur_name: str = ""
        self._cur_cfg: dict = {}
        self._cur_is_active: bool = False
        self._init_ui()

    def _init_ui(self):
        fn = get_font()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        # 顶部: 方案名 + 应用按钮
        hdr = QHBoxLayout()
        self._name_lbl = QLabel("—")
        self._name_lbl.setFont(_make_font(fn, 18, bold=True))
        self._name_lbl.setStyleSheet("color: white; background: transparent;")
        hdr.addWidget(self._name_lbl, 1)
        self._apply_btn = QPushButton(t("profile.apply_btn") if False else "应用此方案")
        self._apply_btn.setFixedHeight(36)
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.setFont(_make_font(fn, 13, bold=True))
        self._apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_AMBER}; color: black;
                border: none; border-radius: 6px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {C_AMBER_D}; color: white; }}
            QPushButton:disabled {{ background: #404040; color: #888; }}
        """)
        self._apply_btn.clicked.connect(lambda: self.apply_clicked.emit(self._cur_name))
        hdr.addWidget(self._apply_btn)
        v.addLayout(hdr)

        # tab 按钮行 (4 个等宽)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(6)
        self._tab_btns: dict = {}
        self._tab_count_lbls: dict = {}
        self._cur_tab = 'kb'
        for key, label in (('kb', '键盘按键'), ('gp', '手柄按钮'),
                           ('voice', '语音指令'), ('global', '全局参数')):
            b = QPushButton(label)
            b.setFixedHeight(36)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(_make_font(fn, 13, bold=True))
            b.clicked.connect(lambda _, k=key: self._on_tab_clicked(k))
            tab_row.addWidget(b, 1)
            self._tab_btns[key] = b
        v.addLayout(tab_row)

        # stacked 详情 (4 页, 每页一个 QScrollArea)
        from PyQt6.QtWidgets import QStackedWidget, QScrollArea
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._pages: dict = {}
        for key in ('kb', 'gp', 'voice', 'global'):
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
            QVBoxLayout(body)   # 占位 layout, set_profile 时清空重建
            scroll.setWidget(body)
            self._stack.addWidget(scroll)
            self._pages[key] = body
        v.addWidget(self._stack, 1)
        self._refresh_tab_styles()

    def _on_tab_clicked(self, key: str):
        if key == self._cur_tab:
            return
        self._cur_tab = key
        idx_map = {'kb': 0, 'gp': 1, 'voice': 2, 'global': 3}
        self._stack.setCurrentIndex(idx_map[key])
        self._refresh_tab_styles()

    def _refresh_tab_styles(self):
        for key, b in self._tab_btns.items():
            is_selected = (key == self._cur_tab)
            if is_selected:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_CYBER if False else "#0C4A6E"}; color: white;
                        border: none; border-radius: 6px;
                    }}
                    QPushButton:hover {{ background: #0284C7; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: {C_GRAY}; color: #CCC;
                        border: none; border-radius: 6px;
                    }}
                    QPushButton:hover {{ background: {C_GRAY_H}; color: white; }}
                """)

    def set_profile(self, name: str, cfg: dict, is_active: bool):
        """从外部刷新: 改方案名 + 重渲染 4 页 + 切回 kb tab + 更新 apply 按钮状态"""
        self._cur_name = name
        self._cur_cfg = cfg or {}
        self._cur_is_active = is_active
        self._name_lbl.setText(name or "—")
        self._apply_btn.setEnabled(bool(name) and not is_active)
        self._apply_btn.setText("当前已是激活方案" if is_active else "应用此方案")
        # 重渲染所有页
        self._render_kb_page()
        self._render_gp_page()
        self._render_voice_page()
        self._render_global_page()
        # 回到 kb tab
        self._cur_tab = 'kb'
        self._stack.setCurrentIndex(0)
        self._refresh_tab_styles()

    # ── 4 个页面渲染 ──

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                self._clear_layout(item.layout())

    def _page_layout(self, key: str) -> QVBoxLayout:
        body = self._pages[key]
        lay = body.layout()
        self._clear_layout(lay)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)
        return lay

    def _render_kb_page(self):
        lay = self._page_layout('kb')
        cfg = self._cur_cfg
        # 1. 普通按钮 (含 center_band)
        buttons = cfg.get('buttons', []) or []
        kb_btns = [b for b in buttons
                   if b.get('type') in ('normal', 'center_band', None)
                   and b.get('type') not in ('gp_button', 'gp_stick', 'gp_wheel')]
        kb_btns_with_actions = []
        for b in kb_btns:
            actions = _summarize_button_actions(b)
            if actions or b.get('type') == 'center_band':
                kb_btns_with_actions.append((b, actions))
        lay.addWidget(_make_section_header("普通按钮", len(kb_btns_with_actions)))
        if kb_btns_with_actions:
            for b, actions in kb_btns_with_actions[:30]:
                lay.addWidget(_make_button_row(b.get('name', ''), actions))
            if len(kb_btns_with_actions) > 30:
                more = QLabel(f"  ...还有 {len(kb_btns_with_actions) - 30} 个")
                more.setStyleSheet("color: #888; background: transparent;")
                more.setFont(_make_font(get_font(), 12))
                lay.addWidget(more)
        else:
            empty = QLabel("  (无)")
            empty.setStyleSheet("color: #666; background: transparent;")
            lay.addWidget(empty)
        # 2. 中心轮盘
        if cfg.get('wheel_visible'):
            sectors = cfg.get('wheel_sectors', []) or []
            sectors_with = [s for s in sectors if _summarize_button_actions(s)]
            lay.addSpacing(8)
            lay.addWidget(_make_section_header("中心轮盘", len(sectors_with)))
            lay.addWidget(_make_kv_label("模式", cfg.get('wheel_mode') or "默认"))
            lay.addWidget(_make_kv_label("放大", "是" if cfg.get('wheel_enlarged') else "否"))
            lay.addWidget(_make_kv_label("偏移", str(cfg.get('wheel_offset', 0))))
            for s in sectors_with[:8]:
                actions = _summarize_button_actions(s)
                lay.addWidget(_make_button_row(s.get('name', '扇区'), actions))
        # 3. kb 宏
        macros = cfg.get('macros', []) or []
        if macros:
            lay.addSpacing(8)
            lay.addWidget(_make_section_header("键盘宏", len(macros)))
            for m in macros[:10]:
                name = m.get('name', '(未命名)')
                steps = len(m.get('steps', []))
                lay.addWidget(_make_kv_label(name, f"{steps} 步"))
            if len(macros) > 10:
                more = QLabel(f"  ...还有 {len(macros) - 10} 个宏")
                more.setStyleSheet("color: #888; background: transparent;")
                lay.addWidget(more)
        lay.addStretch()

    def _render_gp_page(self):
        lay = self._page_layout('gp')
        cfg = self._cur_cfg
        buttons = cfg.get('buttons', []) or []
        gp_btns = [b for b in buttons if b.get('type') == 'gp_button']
        gp_sticks = [b for b in buttons if b.get('type') == 'gp_stick']
        gp_wheels = [b for b in buttons if b.get('type') == 'gp_wheel']
        # 手柄键
        gp_btns_with = []
        for b in gp_btns:
            actions = _summarize_button_actions(b)
            if actions:
                gp_btns_with.append((b, actions))
        lay.addWidget(_make_section_header("手柄键", len(gp_btns_with)))
        if gp_btns_with:
            for b, actions in gp_btns_with[:30]:
                lay.addWidget(_make_button_row(b.get('name', ''), actions))
        else:
            empty = QLabel("  (无)")
            empty.setStyleSheet("color: #666; background: transparent;")
            lay.addWidget(empty)
        # 摇杆
        if gp_sticks:
            lay.addSpacing(8)
            lay.addWidget(_make_section_header("摇杆", len(gp_sticks)))
            for s in gp_sticks:
                sid = "左摇杆 (L)" if s.get('stick_id') == 'L' else "右摇杆 (R)"
                summary = (f"死区 {int((s.get('dead_zone', 0.1)) * 100)}% / "
                           f"{'平方' if s.get('sensitivity_curve') == 'square' else '线性'}")
                if s.get('eight_way'):
                    summary += " / 八方向"
                lay.addWidget(_make_kv_label(sid, summary))
        # 方向盘
        if gp_wheels:
            lay.addSpacing(8)
            lay.addWidget(_make_section_header("方向盘", len(gp_wheels)))
            for w in gp_wheels:
                mode_label = {'scroll': '滚轮', 'vertical': '垂直位移', 'buttons': '左右键'}
                lay.addWidget(_make_kv_label(
                    "释放阈值", f"{int(w.get('release_threshold_ratio', 1.5) * 100)}%"))
                lay.addWidget(_make_kv_label(
                    "视觉旋转", f"±{int(w.get('max_rotation_deg', 180))}°"))
                lay.addWidget(_make_kv_label(
                    "灵敏度", '平方' if w.get('sensitivity_curve') == 'square' else '线性'))
                lt = mode_label.get(w.get('lt_mode', ''), w.get('lt_mode', ''))
                rt = mode_label.get(w.get('rt_mode', ''), w.get('rt_mode', ''))
                lay.addWidget(_make_kv_label("LT", lt))
                lay.addWidget(_make_kv_label("RT", rt))
        # gp 宏
        gp_macros = cfg.get('gp_macros', []) or []
        if gp_macros:
            lay.addSpacing(8)
            lay.addWidget(_make_section_header("手柄宏", len(gp_macros)))
            for m in gp_macros[:10]:
                name = m.get('name', '(未命名)')
                steps = len(m.get('steps', []))
                lay.addWidget(_make_kv_label(name, f"{steps} 步"))
        lay.addStretch()

    def _render_voice_page(self):
        lay = self._page_layout('voice')
        cfg = self._cur_cfg
        cmds = cfg.get('voice_commands', []) or []
        lay.addWidget(_make_section_header("配置", -1))
        lay.addWidget(_make_kv_label("启用", "开" if cfg.get('voice_enabled') else "关"))
        lay.addWidget(_make_kv_label("语言", cfg.get('voice_language') or "zh-CN"))
        lay.addWidget(_make_kv_label(
            "自动启动", "是" if cfg.get('voice_auto_start', True) else "否"))
        lay.addWidget(_make_kv_label("麦克风", cfg.get('voice_mic_device') or "默认"))
        lay.addSpacing(8)
        lay.addWidget(_make_section_header("语音指令", len(cmds)))
        if cmds:
            for c in cmds[:50]:
                phrase = c.get('phrase', '')
                keys = c.get('keys', '')
                act = c.get('action', 'click')
                lay.addWidget(_make_kv_label(f'"{phrase}"', f"→ {keys}  [{act}]"))
            if len(cmds) > 50:
                more = QLabel(f"  ...还有 {len(cmds) - 50} 条")
                more.setStyleSheet("color: #888; background: transparent;")
                lay.addWidget(more)
        else:
            empty = QLabel("  (未配置)")
            empty.setStyleSheet("color: #666; background: transparent;")
            lay.addWidget(empty)
        lay.addStretch()

    def _render_global_page(self):
        lay = self._page_layout('global')
        cfg = self._cur_cfg
        lay.addWidget(_make_section_header("窗口", -1))
        geo = cfg.get('geometry', '')
        if geo:
            try:
                wh = geo.split('+')[0]
                lay.addWidget(_make_kv_label("分辨率", wh))
            except Exception:
                lay.addWidget(_make_kv_label("Geometry", geo))
        lay.addWidget(_make_kv_label(
            "透明度", f"{int((cfg.get('transparency', 0.5)) * 100)}%"))
        ct_map = {'pt_on': '开启', 'pt_off': '关闭', 'pt_block': '阻挡'}
        lay.addWidget(_make_kv_label(
            "穿透模式", ct_map.get(cfg.get('click_through', ''), str(cfg.get('click_through', '')))))
        lay.addWidget(_make_kv_label("网格", f"{cfg.get('grid_size') or '默认'}px"))
        sc = cfg.get('scene_scale', 1.0)
        try:
            sc_pct = int(round(float(sc) * 100))
        except (TypeError, ValueError):
            sc_pct = 100
        lay.addWidget(_make_kv_label("缩放", f"{sc_pct}%"))
        lay.addSpacing(8)
        lay.addWidget(_make_section_header("模拟", -1))
        sm = cfg.get('sim_mode')
        sm_label = '手柄' if sm == 'gamepad' else ('键盘' if sm == 'keyboard' else '未设置 (按全局默认)')
        lay.addWidget(_make_kv_label("模式", sm_label))
        # 运行工具栏位置
        rtx = cfg.get('run_toolbar_x')
        rty = cfg.get('run_toolbar_y')
        if rtx is not None and rty is not None:
            lay.addSpacing(8)
            lay.addWidget(_make_section_header("布局记忆", -1))
            lay.addWidget(_make_kv_label("运行工具栏", f"({rtx}, {rty})"))
        # 外观 (wheel_style + cursor_styles)
        ws = cfg.get('wheel_style')
        cs = cfg.get('cursor_styles')
        if ws or cs:
            lay.addSpacing(8)
            lay.addWidget(_make_section_header("外观", -1))
            if isinstance(ws, dict):
                color = ws.get('color', '?')
                lay.addWidget(_make_kv_label("方向盘描边", color, value_color=color))
            if isinstance(cs, dict):
                for ct, label in (('cursor', '光标-默认'),
                                  ('cursor_off', '光标-关闭'),
                                  ('cursor_block', '光标-阻挡')):
                    sty = cs.get(ct, {}) or {}
                    fill = sty.get('fill', '?')
                    scale = sty.get('scale', 1.0)
                    lay.addWidget(_make_kv_label(
                        label, f"底色 {fill} / {int(round(float(scale) * 100))}%",
                        value_color=fill if fill.startswith('#') else "#E0E0E0"))
        lay.addStretch()


class _ProfileRowWidget(QFrame):
    """方案列表行 — 名称 + 行内操作按钮 (编辑/删除/导出)。
    视觉解耦: is_active (金色底, 当前激活方案) vs is_viewed (蓝色描边, 右侧详情正在查看)
    点击行 = 只查看 (view_clicked); 应用切换走右侧详情面板的按钮。"""

    rename_clicked = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)
    export_clicked = pyqtSignal(str)
    view_clicked = pyqtSignal(str)     # 单击行 → 只切换右侧查看, 不切换 active

    ROW_H = 40
    VIEW_OUTLINE_COLOR = "#F59E0B"     # 查看选中态黄描边 (跟项目主色 amber 一致)

    def __init__(self, name, is_active, is_viewed,
                 icon_font_name, font_name, parent=None):
        super().__init__(parent)
        self._name = name
        self._is_active = is_active
        self._is_viewed = is_viewed
        self.setFixedHeight(self.ROW_H)

        bg = C_PM_SEL if is_active else C_PM_ITEM
        fg = "black" if is_active else "white"
        fg_dim = "rgba(0,0,0,0.35)" if is_active else "white"
        hover_bg = "#D97706" if is_active else "rgba(255,255,255,0.15)"
        # 蓝色描边只在 viewed 时显示, 跟金底/灰底叠加
        border = (f"2px solid {self.VIEW_OUTLINE_COLOR}" if is_viewed else "2px solid transparent")

        self.setObjectName("profile_row")
        self.setStyleSheet(f"""
            QFrame#profile_row {{
                background: {bg}; border-radius: 6px; border: {border};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(6)

        # ✓ 图标 (仅活跃方案)
        if is_active:
            check = QLabel()
            if icon_font_name:
                check.setText("\uE73E")
                check.setFont(_make_font(icon_font_name, 16))
            else:
                check.setText("\u2713")
                check.setFont(_make_font(font_name, 14, bold=True))
            check.setStyleSheet(f"color: {fg}; background: transparent;")
            layout.addWidget(check)

        # 方案名 (点击 = 查看, 不再触发 switch)
        name_lbl = QLabel(name)
        name_lbl.setFont(_make_font(font_name, 16))
        name_lbl.setStyleSheet(f"color: {fg}; background: transparent;")
        name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        name_lbl.mousePressEvent = lambda e: self.view_clicked.emit(self._name)
        layout.addWidget(name_lbl, 1)

        # 行内按钮: 编辑(重命名) | 删除 | 导出
        btn_size = 30

        # 编辑
        edit_btn = QPushButton()
        edit_btn.setFixedSize(btn_size, btn_size)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_font_name:
            edit_btn.setText("\uE70F")
            edit_btn.setFont(_make_font(icon_font_name, 14))
        else:
            edit_btn.setText("\u270E")
            edit_btn.setFont(_make_font(font_name, 14))
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                color: {fg}; background: transparent; border: none;
            }}
            QPushButton:hover {{ background: {hover_bg}; border-radius: 6px; }}
        """)
        edit_btn.clicked.connect(lambda: self.rename_clicked.emit(self._name))
        layout.addWidget(edit_btn)

        # 删除
        del_btn = QPushButton()
        del_btn.setFixedSize(btn_size, btn_size)
        if icon_font_name:
            del_btn.setText("\uE74D")
            del_btn.setFont(_make_font(icon_font_name, 14))
        else:
            del_btn.setText("\u2715")
            del_btn.setFont(_make_font(font_name, 12))
        if is_active:
            del_btn.setEnabled(False)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {fg_dim}; background: transparent; border: none;
                }}
            """)
        else:
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {fg}; background: transparent; border: none;
                }}
                QPushButton:hover {{ background: {hover_bg}; border-radius: 6px; }}
            """)
            del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._name))
        layout.addWidget(del_btn)

        # 导出
        exp_btn = QPushButton()
        exp_btn.setFixedSize(btn_size, btn_size)
        exp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_font_name:
            exp_btn.setText("\uE896")
            exp_btn.setFont(_make_font(icon_font_name, 14))
        else:
            exp_btn.setText("\u2193")
            exp_btn.setFont(_make_font(font_name, 14))
        exp_btn.setStyleSheet(f"""
            QPushButton {{
                color: {fg}; background: transparent; border: none;
            }}
            QPushButton:hover {{ background: {hover_bg}; border-radius: 6px; }}
        """)
        exp_btn.clicked.connect(lambda: self.export_clicked.emit(self._name))
        layout.addWidget(exp_btn)

    def mousePressEvent(self, event):
        """点击行空白区域 = 查看 (不再切换 active)"""
        self.view_clicked.emit(self._name)
        super().mousePressEvent(event)


class ProfileManagerDialog(QDialog):
    """方案管理弹窗 — 对齐原版 Tkinter 布局"""

    profile_switched = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(960, 960)
        self._viewed_name: str = ""   # 右侧详情正在查看的方案 (跟 active 解耦)
        self._init_ui()
        self._refresh()
        self._center_on_screen()
        self._drag_pos = None

    def _init_ui(self):
        self._font_name = get_font()
        _detect_icon_font()
        from views.edit_toolbar import _ICON_FONT
        self._icon_font = _ICON_FONT

        # ── 外层透明, 内层 QFrame 容器 ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("pm_container")
        container.setStyleSheet(f"""
            QFrame#pm_container {{
                background: {C_PM_BG};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self._layout = layout

        # ── 标题栏 (跨两列) ──
        header = QHBoxLayout()
        title = QLabel(t("profile.manager_title"))
        title.setFont(_make_font(self._font_name, 18, bold=True))
        title.setStyleSheet("color: white; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._icon_font:
            close_btn.setText("\uE711")
            close_btn.setFont(_make_font(self._icon_font, 20))
        else:
            close_btn.setText("\u2715")
            close_btn.setFont(_make_font(self._font_name, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
        """)
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # ── 两列 (左 380w 列表+按钮, 右 540w 详情) ──
        columns = QHBoxLayout()
        columns.setSpacing(20)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        left_wrap = QFrame()
        left_wrap.setFixedWidth(380)
        left_wrap.setLayout(left)
        columns.addWidget(left_wrap)

        # 中间分隔线
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: #444;")
        columns.addWidget(sep)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right_wrap = QFrame()
        right_wrap.setLayout(right)
        columns.addWidget(right_wrap, 1)

        layout.addLayout(columns, 1)

        # ── 左列: 方案列表 ──
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: {C_PM_BG};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                padding: 0px;
                border: none;
                margin-right: 0px;
            }}
            QListWidget::item:selected {{
                background: transparent;
            }}
            QListWidget::item:hover {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 18px; border: none;
                padding-left: 10px;
            }}
            QScrollBar::handle:vertical {{
                background: #404040; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left.addWidget(self._list, 1)

        # ── 左列底部按钮: 新建 | 复制 | 导入 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_style = f"""
            QPushButton {{
                background: {C_GRAY}; color: #E0E0E0;
                border: none; border-radius: 6px;
                padding: 8px 0px; font-size: 16px;
            }}
            QPushButton:hover {{ background: {C_GRAY_H}; }}
        """

        new_btn = self._build_bottom_btn("\uE710", "\uff0b", t("profile.new"))
        new_btn.setStyleSheet(btn_style)
        new_btn.clicked.connect(self._on_new)
        btn_row.addWidget(new_btn, 1)

        copy_btn = self._build_bottom_btn("\uE8C8", "\u2398", t("profile.copy"))
        copy_btn.setStyleSheet(btn_style)
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn, 1)

        import_btn = self._build_bottom_btn("\uE898", "\u2193", t("profile.import_btn"))
        import_btn.setStyleSheet(btn_style)
        import_btn.clicked.connect(self._on_import)
        btn_row.addWidget(import_btn, 1)

        left.addLayout(btn_row)

        # ── 右列: 方案详情面板 ──
        self._detail_panel = _ProfileDetailPanel()
        self._detail_panel.apply_clicked.connect(self._on_apply_viewed)
        right.addWidget(self._detail_panel)

    def _build_bottom_btn(self, icon_char, fallback, label):
        """底部按钮: icon font 图标 + 文字 (与工具栏同方案)"""
        btn = QPushButton()
        btn.setFixedHeight(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(btn)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        if self._icon_font:
            icon_lbl.setText(icon_char)
            icon_lbl.setFont(_make_font(self._icon_font, 20))
        else:
            icon_lbl.setText(fallback)
            icon_lbl.setFont(_make_font(self._font_name, 16, bold=True))
        icon_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(icon_lbl)

        text_lbl = QLabel(label)
        text_lbl.setFont(_make_font(self._font_name, 16))
        text_lbl.setStyleSheet("color: #E0E0E0; background: transparent;")
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(text_lbl)

        return btn

    def _center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _refresh(self):
        self._list.clear()
        profiles = list_profiles()
        active = get_active_profile_name()
        # 默认 viewed = active (首次或 viewed 被删时回退)
        if not self._viewed_name or self._viewed_name not in profiles:
            self._viewed_name = active
        for name in profiles:
            row = _ProfileRowWidget(
                name, name == active, name == self._viewed_name,
                self._icon_font, self._font_name)
            row.view_clicked.connect(self._on_view_clicked)
            row.rename_clicked.connect(self._on_rename)
            row.delete_clicked.connect(self._on_delete)
            row.export_clicked.connect(self._on_export)

            item = QListWidgetItem()
            item.setSizeHint(QSize(0, _ProfileRowWidget.ROW_H + 10))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        # 同步右侧详情
        self._refresh_detail()

    def _refresh_detail(self):
        """刷新右侧详情面板, 根据 _viewed_name 拉 config"""
        name = self._viewed_name
        if not name:
            self._detail_panel.set_profile("", {}, False)
            return
        try:
            cfg = load_profile(name) or {}
        except Exception:
            cfg = {}
        is_active = (name == get_active_profile_name())
        self._detail_panel.set_profile(name, cfg, is_active)

    def _on_view_clicked(self, name: str):
        """用户单击行 → 只更新 viewed (不切换 active), 刷新右侧详情和列表高亮"""
        if name == self._viewed_name:
            return
        self._viewed_name = name
        self._refresh()   # 重建行让 viewed 蓝边框更新

    def _on_apply_viewed(self, name: str):
        """右侧详情「应用此方案」→ 切换 active"""
        if not name:
            return
        self.profile_switched.emit(name)
        self._refresh()

    # ── 操作回调 ──

    def _on_new(self):
        dlg = _StyledInputDialog(
            t("profile.new_title"), t("profile.new_name_label"), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.result_text()
            if name:
                if create_profile(name, from_template=True):
                    self._viewed_name = name
                    self.profile_switched.emit(name)
                    self._refresh()
                else:
                    _StyledMessageDialog(t("dialog.error"), t("profile.error_exists"), self).exec()

    def _on_copy(self):
        """复制方案 — 弹出 _ProfileCopyDialog (分类选择 + 新建/已有 + 追加/覆盖)"""
        src = self._viewed_name or get_active_profile_name()
        if not src:
            return
        dlg = _ProfileCopyDialog(src, list_profiles(), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cats, target_kind, target_name, mode = dlg.get_result()
        src_cfg = load_profile(src) or {}
        if target_kind == 'new':
            # 1) 创建新 profile (用模板填充默认字段)
            if not create_profile(target_name, from_template=True):
                _StyledMessageDialog(t("dialog.error"), t("profile.error_exists"), self).exec()
                return
            template_cfg = load_profile(target_name) or {}
            # 2) 选中类别 overwrite 到模板, 其他保留模板默认
            merged = _merge_profiles(src_cfg, template_cfg, cats, mode='overwrite')
            save_profile(target_name, merged)
            self._viewed_name = target_name
            self.profile_switched.emit(target_name)
        else:
            # 粘贴到已有
            dst_cfg = load_profile(target_name) or {}
            merged = _merge_profiles(src_cfg, dst_cfg, cats, mode)
            save_profile(target_name, merged)
            self._viewed_name = target_name
            # 若目标 == active, 通知 overlay 重载
            if target_name == get_active_profile_name():
                self.profile_switched.emit(target_name)
        self._refresh()

    def _on_rename(self, old_name):
        dlg = _StyledInputDialog(
            t("profile.rename_title"),
            t("profile.rename_label", name=old_name),
            initial_value=old_name, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name = dlg.result_text()
            if new_name and new_name != old_name:
                if rename_profile(old_name, new_name):
                    self._refresh()
                else:
                    _StyledMessageDialog(t("dialog.error"), t("profile.error_rename_exists"), self).exec()

    def _on_delete(self, name):
        dlg = _StyledConfirmDialog(
            t("dialog.confirm"), t("profile.confirm_delete", name=name), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if not delete_profile(name):
                _StyledMessageDialog(t("dialog.error"), t("profile.error_delete_active"), self).exec()
            else:
                # 删了 viewed → 回退到 active
                if name == self._viewed_name:
                    self._viewed_name = get_active_profile_name()
            self._refresh()

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("profile.import_title"), "",
            "JSON (*.json);;All (*.*)")
        if not path:
            return
        new_name = import_profile(path)
        if new_name:
            self._viewed_name = new_name
            self.profile_switched.emit(new_name)
            self._refresh()
        else:
            _StyledMessageDialog(t("dialog.error"), t("profile.error_import_invalid"), self).exec()

    def _on_export(self, name):
        path, _ = QFileDialog.getSaveFileName(
            self, t("profile.export_title", name=name),
            f"{name}.json", "JSON (*.json);;All (*.*)")
        if not path:
            return
        if export_profile(name, path):
            _StyledMessageDialog(t("dialog.success"), t("profile.export_success", name=name), self).exec()
        else:
            _StyledMessageDialog(t("dialog.error"), t("profile.error_export"), self).exec()

    # ── 拖拽 ──
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
