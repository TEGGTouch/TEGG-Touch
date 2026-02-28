"""
TEGG Touch 蛋挞 (PyQt6) - virtual_keyboard.py
浮动软键盘 — 完整 108 键布局，匹配原版 Tkinter。

布局: 主键区 + 导航区(6键+方向键) + 数字小键盘
"""

import ctypes

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QFrame,
    QApplication, QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase

from core.i18n import t, get_font
from core.input_engine import trigger

# ── 尺寸常量 ──
# 缩小三栏间距 (0.935 → 0.415)，扩大按键间距 (2 → 4)，总宽不变 1070
KEY_SIZE = 42
KEY_GAP = 4
KEY_UNIT = KEY_SIZE + KEY_GAP  # 46
PADDING = 10

# ── 颜色 ──
C_KEY = "#3A3A3A"
C_KEY_MOD = "#222222"
C_KEY_H = "#505050"
C_KEY_ACT = "#D97706"
C_KEY_FG = "#E0E0E0"
C_PANEL = "#2D2D2D"
C_CLOSE = "#6E1E1E"
C_CLOSE_H = "#8B2020"

# ── 导航区 / 小键盘区列偏移 (缩小三栏间隔) ──
NAV_OFF = 15.415
NP_OFF = 18.83

# ── 图标字体检测 ──
_ICON_FONT = None


def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""

# ── 键名映射 (内部名 → keyboard 库名) ──
_KB_KEY_MAP = {
    "caps": "caps lock",
    "printscreen": "print screen",
    "scrolllock": "scroll lock",
    "pgup": "page up",
    "pgdn": "page down",
    "numlock": "num lock",
    "num enter": "num enter",
    "win": "windows",
}

# Shift 标签映射
# 注意: QPushButton 将 '&' 解释为助记符前缀，需用 '&&' 转义显示字面 '&'
_SHIFT_LABEL_MAP = {
    "`": "~", "1": "!", "2": "@", "3": "#", "4": "$",
    "5": "%", "6": "^", "7": "&&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+",
    "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?",
}

# 粘滞键
STICKY_TOGGLE = {"caps", "numlock", "scrolllock"}
STICKY_HOLD = {"shift", "ctrl", "alt"}

# ── 字符映射 (key_name → 可插入字符) ──
_CHAR_MAP = {
    "space": " ", "`": "`", "-": "-", "=": "=",
    "[": "[", "]": "]", "\\": "\\", ";": ";", "'": "'",
    ",": ",", ".": ".", "/": "/",
    "num /": "/", "num *": "*", "num -": "-", "num +": "+", "num .": ".",
    "num 0": "0", "num 1": "1", "num 2": "2", "num 3": "3",
    "num 4": "4", "num 5": "5", "num 6": "6", "num 7": "7",
    "num 8": "8", "num 9": "9",
}

# Shift 状态下的符号映射 (key_name → 字符)
_SHIFT_CHAR_MAP = {
    "`": "~", "1": "!", "2": "@", "3": "#", "4": "$",
    "5": "%", "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+",
    "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?",
}

# ── 完整 108 键定义 ──
# (label, key_name, col, row, col_span, row_span, is_mod)
_ALL_KEYS = [
    # Row 0: Function keys
    ("Esc", "esc", 0, 0, 1, 1, True),
    ("F1", "f1", 2, 0, 1, 1, True), ("F2", "f2", 3, 0, 1, 1, True),
    ("F3", "f3", 4, 0, 1, 1, True), ("F4", "f4", 5, 0, 1, 1, True),
    ("F5", "f5", 6.5, 0, 1, 1, True), ("F6", "f6", 7.5, 0, 1, 1, True),
    ("F7", "f7", 8.5, 0, 1, 1, True), ("F8", "f8", 9.5, 0, 1, 1, True),
    ("F9", "f9", 11, 0, 1, 1, True), ("F10", "f10", 12, 0, 1, 1, True),
    ("F11", "f11", 13, 0, 1, 1, True), ("F12", "f12", 14, 0, 1, 1, True),
    # Nav top
    ("PrtSc", "printscreen", NAV_OFF, 0, 1, 1, True),
    ("ScrLk", "scrolllock", NAV_OFF + 1, 0, 1, 1, True),
    ("Pause", "pause", NAV_OFF + 2, 0, 1, 1, True),

    # Row 1: Number row
    ("`", "`", 0, 1, 1, 1, False),
    ("1", "1", 1, 1, 1, 1, False), ("2", "2", 2, 1, 1, 1, False),
    ("3", "3", 3, 1, 1, 1, False), ("4", "4", 4, 1, 1, 1, False),
    ("5", "5", 5, 1, 1, 1, False), ("6", "6", 6, 1, 1, 1, False),
    ("7", "7", 7, 1, 1, 1, False), ("8", "8", 8, 1, 1, 1, False),
    ("9", "9", 9, 1, 1, 1, False), ("0", "0", 10, 1, 1, 1, False),
    ("-", "-", 11, 1, 1, 1, False), ("=", "=", 12, 1, 1, 1, False),
    ("\u232B", "backspace", 13, 1, 2, 1, True),
    # Nav 6-key top
    ("Ins", "insert", NAV_OFF, 1, 1, 1, True),
    ("Home", "home", NAV_OFF + 1, 1, 1, 1, True),
    ("PgUp", "pgup", NAV_OFF + 2, 1, 1, 1, True),

    # Row 2: QWERTY
    ("Tab", "tab", 0, 2, 1.5, 1, True),
    ("Q", "q", 1.5, 2, 1, 1, False), ("W", "w", 2.5, 2, 1, 1, False),
    ("E", "e", 3.5, 2, 1, 1, False), ("R", "r", 4.5, 2, 1, 1, False),
    ("T", "t", 5.5, 2, 1, 1, False), ("Y", "y", 6.5, 2, 1, 1, False),
    ("U", "u", 7.5, 2, 1, 1, False), ("I", "i", 8.5, 2, 1, 1, False),
    ("O", "o", 9.5, 2, 1, 1, False), ("P", "p", 10.5, 2, 1, 1, False),
    ("[", "[", 11.5, 2, 1, 1, False), ("]", "]", 12.5, 2, 1, 1, False),
    ("\\", "\\", 13.5, 2, 1.5, 1, False),
    # Nav 6-key bottom
    ("Del", "delete", NAV_OFF, 2, 1, 1, True),
    ("End", "end", NAV_OFF + 1, 2, 1, 1, True),
    ("PgDn", "pgdn", NAV_OFF + 2, 2, 1, 1, True),

    # Row 3: Home row
    ("Caps", "caps", 0, 3, 1.75, 1, True),
    ("A", "a", 1.75, 3, 1, 1, False), ("S", "s", 2.75, 3, 1, 1, False),
    ("D", "d", 3.75, 3, 1, 1, False), ("F", "f", 4.75, 3, 1, 1, False),
    ("G", "g", 5.75, 3, 1, 1, False), ("H", "h", 6.75, 3, 1, 1, False),
    ("J", "j", 7.75, 3, 1, 1, False), ("K", "k", 8.75, 3, 1, 1, False),
    ("L", "l", 9.75, 3, 1, 1, False),
    (";", ";", 10.75, 3, 1, 1, False), ("'", "'", 11.75, 3, 1, 1, False),
    ("Enter", "enter", 12.75, 3, 2.25, 1, True),

    # Row 4: Shift row
    ("Shift", "shift", 0, 4, 2.25, 1, True),
    ("Z", "z", 2.25, 4, 1, 1, False), ("X", "x", 3.25, 4, 1, 1, False),
    ("C", "c", 4.25, 4, 1, 1, False), ("V", "v", 5.25, 4, 1, 1, False),
    ("B", "b", 6.25, 4, 1, 1, False), ("N", "n", 7.25, 4, 1, 1, False),
    ("M", "m", 8.25, 4, 1, 1, False),
    (",", ",", 9.25, 4, 1, 1, False), (".", ".", 10.25, 4, 1, 1, False),
    ("/", "/", 11.25, 4, 1, 1, False),
    ("Shift", "shift", 12.25, 4, 2.75, 1, True),
    # Arrow up
    ("\u2191", "up", NAV_OFF + 1, 4, 1, 1, True),

    # Row 5: Bottom row
    ("Ctrl", "ctrl", 0, 5, 1.25, 1, True),
    ("Win", "win", 1.25, 5, 1.25, 1, True),
    ("Alt", "alt", 2.5, 5, 1.25, 1, True),
    ("Space", "space", 3.75, 5, 6.25, 1, True),
    ("Alt", "alt", 10, 5, 1.25, 1, True),
    ("Ctrl", "ctrl", 11.25, 5, 1.25, 1, True),
    # Arrow keys
    ("\u2190", "left", NAV_OFF, 5, 1, 1, True),
    ("\u2193", "down", NAV_OFF + 1, 5, 1, 1, True),
    ("\u2192", "right", NAV_OFF + 2, 5, 1, 1, True),

    # Numpad row 1 (operators)
    ("Num", "numlock", NP_OFF, 1, 1, 1, True),
    ("/", "num /", NP_OFF + 1, 1, 1, 1, False),
    ("*", "num *", NP_OFF + 2, 1, 1, 1, False),
    ("-", "num -", NP_OFF + 3, 1, 1, 1, False),
    # Numpad row 2
    ("7", "num 7", NP_OFF, 2, 1, 1, False),
    ("8", "num 8", NP_OFF + 1, 2, 1, 1, False),
    ("9", "num 9", NP_OFF + 2, 2, 1, 1, False),
    ("+", "num +", NP_OFF + 3, 2, 1, 2, False),  # tall
    # Numpad row 3
    ("4", "num 4", NP_OFF, 3, 1, 1, False),
    ("5", "num 5", NP_OFF + 1, 3, 1, 1, False),
    ("6", "num 6", NP_OFF + 2, 3, 1, 1, False),
    # Numpad row 4
    ("1", "num 1", NP_OFF, 4, 1, 1, False),
    ("2", "num 2", NP_OFF + 1, 4, 1, 1, False),
    ("3", "num 3", NP_OFF + 2, 4, 1, 1, False),
    ("Ent", "num enter", NP_OFF + 3, 4, 1, 2, True),  # tall
    # Numpad row 5
    ("0", "num 0", NP_OFF, 5, 2, 1, False),  # wide
    (".", "num .", NP_OFF + 2, 5, 1, 1, False),
]


def _make_font(name, px, bold=False):
    f = QFont(name)
    f.setPixelSize(px)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


class VirtualKeyboard(QWidget):
    """浮动软键盘 — 完整 108 键布局"""

    key_pressed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._drag_pos = None
        self._attached_toolbar = None  # 吸附的工具栏引用
        self._sticky_state = {k: False for k in
                              STICKY_TOGGLE | STICKY_HOLD}
        self._key_buttons = {}  # key_name -> [btn, ...]
        self._label_map = {}    # btn -> original_label
        self._last_focused_input = None  # 焦点追踪
        self._focus_connected = False    # focusChanged 信号连接状态

        self._init_ui()

    def _init_ui(self):
        _detect_icon_font()
        fn = get_font()

        # 计算总宽度/高度 (无标题栏，节约垂直空间)
        max_col = NP_OFF + 4  # 22.83
        max_row = 6
        total_w = int(max_col * KEY_UNIT) + PADDING * 2  # 1050 + 20 = 1070
        total_h = int(max_row * KEY_UNIT) + PADDING * 2  # 276 + 20 = 296

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("kb_container")
        container.setStyleSheet(f"""
            QFrame#kb_container {{
                background: {C_PANEL};
                border-radius: 4px;
                border: 1px solid #444;
            }}
        """)
        outer.addWidget(container)

        # 键盘区域 (absolute positioning, 无标题栏)
        self._keys_area = QWidget(container)
        self._keys_area.setStyleSheet("background: transparent;")

        # 放置所有按键
        for label, key_name, col, row, cw, rh, is_mod in _ALL_KEYS:
            kx = PADDING + int(col * KEY_UNIT)
            ky = PADDING + int(row * KEY_UNIT)
            kw = int(cw * KEY_UNIT) - KEY_GAP
            kh = int(rh * KEY_UNIT) - KEY_GAP

            btn = QPushButton(label, self._keys_area)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            bg = C_KEY_MOD if is_mod else C_KEY

            # 字体: 长标签用小字
            if len(label) > 3:
                btn.setFont(_make_font("Consolas", 12, bold=True))
            else:
                btn.setFont(_make_font("Consolas", 15, bold=True))

            btn.setGeometry(kx, ky, kw, kh)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._key_style(bg))
            btn.clicked.connect(lambda checked, kn=key_name: self._on_key(kn))

            # 存储引用
            if key_name not in self._key_buttons:
                self._key_buttons[key_name] = []
            self._key_buttons[key_name].append(btn)
            self._label_map[btn] = label

        # ── 收起按钮 (数字键盘-号上方, NP_OFF+3 row 0) ──
        cx = PADDING + int((NP_OFF + 3) * KEY_UNIT)
        cy = PADDING + int(0 * KEY_UNIT)
        cw_btn = int(1 * KEY_UNIT) - KEY_GAP
        ch_btn = int(1 * KEY_UNIT) - KEY_GAP

        close_btn = QPushButton(self._keys_area)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setGeometry(cx, cy, cw_btn, ch_btn)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if _ICON_FONT:
            close_btn.setText("\uE70D")  # ChevronUp — 收起
            close_btn.setFont(_make_font(_ICON_FONT, 18))
        else:
            close_btn.setText("\u25B2")  # ▲ fallback
            close_btn.setFont(_make_font(fn, 16, bold=True))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C_CLOSE}; color: #FFF;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_CLOSE_H}; }}
            QPushButton:pressed {{ background: {C_KEY_ACT}; }}
        """)
        close_btn.clicked.connect(self.hide)

        # 布局
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        self._keys_area.setFixedSize(total_w, total_h)
        vbox.addWidget(self._keys_area)

        self.setFixedSize(total_w, total_h)

    def _key_style(self, bg):
        return f"""
            QPushButton {{
                background: {bg}; color: {C_KEY_FG};
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background: {C_KEY_H}; }}
            QPushButton:pressed {{ background: {C_KEY_ACT}; }}
        """

    def _on_key(self, key_name):
        """按键点击处理 — 智能路由: QLineEdit 直接插入, 否则走系统模拟"""
        # 粘滞键处理
        if key_name in STICKY_TOGGLE:
            self._toggle_sticky(key_name)
            return
        if key_name in STICKY_HOLD:
            self._toggle_sticky(key_name)
            return

        # 智能路由: 有焦点输入框 → 直接插入; 否则 → keyboard 模拟
        target = self._find_focused_input()
        if target is not None:
            self._insert_to_line_edit(target, key_name)
        else:
            mapped = _KB_KEY_MAP.get(key_name, key_name)
            try:
                import keyboard as _kb
                _kb.press_and_release(mapped)
            except ImportError:
                pass
            except Exception:
                pass

        # 发出信号 (供外部监听)
        mapped = _KB_KEY_MAP.get(key_name, key_name)
        self.key_pressed.emit(mapped)

        # 闪烁反馈
        self._flash_key(key_name)

        # 自动释放 Hold 粘滞键 (匹配原版 _release_all_sticky_modifiers)
        had_shift = self._sticky_state.get("shift", False)
        for sk in list(STICKY_HOLD):
            if self._sticky_state.get(sk, False):
                self._sticky_state[sk] = False
                self._update_sticky_visual(sk)
                if target is None:
                    try:
                        import keyboard as _kb
                        sk_mapped = _KB_KEY_MAP.get(sk, sk)
                        _kb.release(sk_mapped)
                    except Exception:
                        pass
        # 更新 Shift 标签
        if had_shift:
            self._update_shift_labels(False)

    def _toggle_sticky(self, key_name):
        """切换粘滞键状态 — 匹配原版 _handle_sticky_click
        - toggle 键 (caps/numlock/scrolllock): press_and_release 切换 OS 状态
        - hold 键 (ctrl/shift/alt): press 按住 / release 释放
        """
        current = self._sticky_state.get(key_name, False)
        self._sticky_state[key_name] = not current
        self._update_sticky_visual(key_name)

        mapped = _KB_KEY_MAP.get(key_name, key_name)
        try:
            import keyboard as _kb
            if key_name in STICKY_TOGGLE:
                # OS 级 toggle 键: 每次点击 press_and_release
                _kb.press_and_release(mapped)
            else:
                # Hold 键: 按一次 press, 再按一次 release
                if self._sticky_state[key_name]:
                    _kb.press(mapped)
                else:
                    _kb.release(mapped)
        except ImportError:
            pass
        except Exception:
            pass

        # Shift 切换时更新标签
        if key_name == "shift":
            self._update_shift_labels(self._sticky_state["shift"])

    def _update_sticky_visual(self, key_name):
        """更新粘滞键视觉状态"""
        active = self._sticky_state.get(key_name, False)
        is_mod = True
        bg = C_KEY_ACT if active else (C_KEY_MOD if is_mod else C_KEY)
        for btn in self._key_buttons.get(key_name, []):
            btn.setStyleSheet(self._key_style(bg))

    def _flash_key(self, key_name):
        """按键闪烁反馈"""
        for btn in self._key_buttons.get(key_name, []):
            btn.setStyleSheet(self._key_style(C_KEY_ACT))
            QTimer.singleShot(120, lambda b=btn, kn=key_name:
                              b.setStyleSheet(self._key_style(
                                  C_KEY_MOD if kn in STICKY_HOLD | STICKY_TOGGLE else C_KEY)))

    def _update_shift_labels(self, active):
        """更新 Shift 激活时的按键标签"""
        for btn, orig_label in self._label_map.items():
            if active:
                new_label = _SHIFT_LABEL_MAP.get(orig_label)
                if new_label:
                    btn.setText(new_label)
                elif len(orig_label) == 1 and orig_label.isalpha():
                    btn.setText(orig_label.upper())
            else:
                btn.setText(orig_label)

    # ── Win32 NoActivate ──

    def _apply_noactivate(self):
        """设置 WS_EX_NOACTIVATE 防止键盘窗口抢夺焦点"""
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            old = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if not (old & WS_EX_NOACTIVATE):
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, old | WS_EX_NOACTIVATE)
        except Exception:
            pass

    # ── 焦点追踪 ──

    def _on_app_focus_changed(self, old, new):
        """焦点变化追踪: 记录 QLineEdit"""
        if isinstance(new, QLineEdit) and not self.isAncestorOf(new):
            self._last_focused_input = new

    def _find_focused_input(self):
        """查找当前应接收输入的 QLineEdit"""
        # 优先: 当前焦点控件
        w = QApplication.focusWidget()
        if isinstance(w, QLineEdit) and not self.isAncestorOf(w):
            return w
        # 回退: 上次记录的焦点输入框，但仅当有 Qt 窗口处于激活态时才使用
        # (若无激活窗口，说明用户在外部游戏窗口，应走系统模拟)
        target = self._last_focused_input
        if target is not None:
            try:
                active_win = QApplication.activeWindow()
                if (active_win is not None
                        and active_win is not self
                        and target.isVisible()
                        and not target.isReadOnly()):
                    return target
            except RuntimeError:
                self._last_focused_input = None
        return None

    def _insert_to_line_edit(self, widget, key_name):
        """将按键直接插入到 QLineEdit (移植自原版 _insert_to_entry)"""
        shift_on = self._sticky_state.get("shift", False)

        # Backspace
        if key_name == "backspace":
            widget.backspace()
            return

        # Delete
        if key_name == "delete":
            widget.del_()
            return

        # 光标移动
        if key_name == "left":
            pos = widget.cursorPosition()
            if pos > 0:
                widget.setCursorPosition(pos - 1)
            return
        if key_name == "right":
            pos = widget.cursorPosition()
            if pos < len(widget.text()):
                widget.setCursorPosition(pos + 1)
            return
        if key_name == "home":
            widget.setCursorPosition(0)
            return
        if key_name == "end":
            widget.setCursorPosition(len(widget.text()))
            return

        # Enter → 忽略 (QLineEdit 单行)
        if key_name in ("enter", "num enter"):
            return

        # Tab → 忽略
        if key_name == "tab":
            return

        # 修饰键 / 功能键 / 方向上下 → 忽略
        if key_name in ("ctrl", "alt", "win", "shift", "caps",
                         "numlock", "scrolllock", "esc",
                         "up", "down", "insert", "pause",
                         "printscreen", "pgup", "pgdn") or key_name.startswith("f"):
            return

        # Shift + 符号映射
        if shift_on and key_name in _SHIFT_CHAR_MAP:
            widget.insert(_SHIFT_CHAR_MAP[key_name])
            return

        # 字符映射表中的键
        if key_name in _CHAR_MAP:
            ch = _CHAR_MAP[key_name]
            if shift_on and ch.isalpha():
                ch = ch.upper()
            widget.insert(ch)
            return

        # 单字母/数字键
        if len(key_name) == 1:
            ch = key_name.upper() if shift_on else key_name
            widget.insert(ch)
            return

        # Numpad 键 (已在 _CHAR_MAP 中处理, 这里作为兜底)
        if key_name.startswith("num ") and len(key_name) > 4:
            ch = key_name[4:]
            widget.insert(ch)
            return

    def hideEvent(self, event):
        """关闭键盘时释放所有粘滞修饰键 + 断开焦点追踪"""
        # 断开 focusChanged 信号
        if self._focus_connected:
            try:
                app = QApplication.instance()
                if app is not None:
                    app.focusChanged.disconnect(self._on_app_focus_changed)
            except (TypeError, RuntimeError):
                pass
            self._focus_connected = False
        self._last_focused_input = None

        try:
            import keyboard as _kb
            for mod in ("shift", "ctrl", "alt"):
                if self._sticky_state.get(mod, False):
                    self._sticky_state[mod] = False
                    mapped = _KB_KEY_MAP.get(mod, mod)
                    try:
                        _kb.release(mapped)
                    except Exception:
                        pass
                    self._update_sticky_visual(mod)
            # toggle 键只重置 UI 标记
            for tk_key in STICKY_TOGGLE:
                self._sticky_state[tk_key] = False
                self._update_sticky_visual(tk_key)
        except ImportError:
            pass
        # 恢复 shift 键帽
        self._update_shift_labels(False)
        super().hideEvent(event)

    # ── 定位 (吸附工具栏 — 匹配原版 _position_above_toolbar) ──

    def position_above_toolbar(self, toolbar=None):
        """将软键盘放置在工具栏上方（匹配原版 Tkinter _position_above_toolbar）。

        定位策略：
        - 水平：与工具栏居中对齐
        - 垂直：紧贴工具栏上方 10px
        - 上方放不下 → 翻到工具栏下方
        - 左右超出 → 夹紧屏幕边缘
        """
        if toolbar is not None:
            self._attached_toolbar = toolbar

        tb = self._attached_toolbar
        if tb is None:
            # 无工具栏引用时 fallback 到屏幕居中偏下
            from PyQt6.QtCore import QRect
            _ps = QApplication.primaryScreen()
            screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
            x = (screen.width() - self.width()) // 2
            y = screen.height() - self.height() - 160
            self.move(x, y)
            return

        from PyQt6.QtCore import QRect
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        sw, sh = screen.width(), screen.height()

        # 获取工具栏的全局坐标和尺寸
        tb_geo = tb.frameGeometry()
        tx, ty = tb_geo.x(), tb_geo.y()
        tw, th = tb_geo.width(), tb_geo.height()

        kw, kh = self.width(), self.height()

        # 水平: 与工具栏居中对齐
        kx = tx + (tw - kw) // 2

        # 垂直: 紧贴工具栏上方 10px
        ky = ty - kh - 10

        # Fallback: 上方放不下 → 翻到下方
        if ky < 0:
            ky = ty + th + 10

        # 边缘夹紧: 确保不超出屏幕
        kx = max(0, min(kx, sw - kw))
        ky = max(0, min(ky, sh - kh))

        self.move(kx, ky)

    def showEvent(self, event):
        """显示时重新定位、设置 NoActivate、连接焦点追踪"""
        super().showEvent(event)
        self.position_above_toolbar()
        self._apply_noactivate()
        # 连接焦点追踪
        if not self._focus_connected:
            app = QApplication.instance()
            if app is not None:
                app.focusChanged.connect(self._on_app_focus_changed)
                self._focus_connected = True

    # ── 拖拽 ──

    def mousePressEvent(self, event):
        self.raise_()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
