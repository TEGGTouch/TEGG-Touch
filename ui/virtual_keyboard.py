"""
TEGG Touch 蛋挞 - virtual_keyboard.py
可复用软键盘组件（统一暗色 UI 风格，108 键标准布局）。

软键盘作为工具栏的向上扩展，紧贴工具栏上方 10px，同层级管理。

三种使用模式:
  mode="input"  — 点击按键模拟真实键盘输入（不抢焦点，支持穿透到 tkinter Entry）
  mode="pick"   — 点击按键后回调 on_pick(key) 并关闭
  mode="append" — 点击按键追加到 entry_widget
"""

import tkinter as tk
import ctypes
import traceback

from core.constants import COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS
from ui.widgets import (
    FF, IS, BTN_R,
    C_PM_BG, C_GRAY, C_GRAY_H, C_AMBER, C_AMBER_D,
    C_CLOSE, C_CLOSE_H, C_CYBER,
    icon_font, rrect,
)

# ─── 尺寸常量 ────────────────────────────────────────────────
KEY_SIZE   = 40   # 最小按键尺寸
KEY_GAP    = 4    # 按键间距
KEY_UNIT   = KEY_SIZE + KEY_GAP  # 44px
PADDING    = 10
SEC_GAP    = 10   # 区块间距
KB_FONT    = ("Consolas", 9, "bold")
KB_FONT_SM = ("Consolas", 7, "bold")

# 键帽颜色
C_KEY      = "#3A3A3A"   # 字母/数字键 — 浅灰（与工具栏灰色按钮一致）
C_KEY_MOD  = "#222222"   # 修饰键 — 深色（比背景 #2D2D2D 更深）
C_KEY_H    = "#505050"   # hover 高亮
C_KEY_ACT  = "#D97706"
C_KEY_FG   = "#E0E0E0"

# ─── 108 键布局定义 ──────────────────────────────────────────
# 每个键: (label, key_name, col, row, col_span, row_span)
# col/row 为浮点数网格坐标; span 默认 1

def _k(label, key, c, r, cw=1, rh=1):
    return (label, key, c, r, cw, rh)

# === 主键区 ===
MAIN_KEYS = [
    # Row 0: Esc + F1~F12
    _k("Esc","esc",       0,0),
    _k("F1","f1",         2,0), _k("F2","f2",3,0), _k("F3","f3",4,0), _k("F4","f4",5,0),
    _k("F5","f5",        6.5,0), _k("F6","f6",7.5,0), _k("F7","f7",8.5,0), _k("F8","f8",9.5,0),
    _k("F9","f9",       11,0), _k("F10","f10",12,0), _k("F11","f11",13,0), _k("F12","f12",14,0),

    # Row 1: Number row
    _k("`","`",          0,1), _k("1","1",1,1), _k("2","2",2,1), _k("3","3",3,1),
    _k("4","4",          4,1), _k("5","5",5,1), _k("6","6",6,1), _k("7","7",7,1),
    _k("8","8",          8,1), _k("9","9",9,1), _k("0","0",10,1),
    _k("-","-",         11,1), _k("=","=",12,1), _k("⌫","backspace",13,1,2),

    # Row 2: QWERTY
    _k("Tab","tab",      0,2,1.5), _k("Q","q",1.5,2), _k("W","w",2.5,2), _k("E","e",3.5,2),
    _k("R","r",          4.5,2), _k("T","t",5.5,2), _k("Y","y",6.5,2), _k("U","u",7.5,2),
    _k("I","i",          8.5,2), _k("O","o",9.5,2), _k("P","p",10.5,2),
    _k("[","[",         11.5,2), _k("]","]",12.5,2), _k("\\","\\",13.5,2,1.5),

    # Row 3: Home row
    _k("Caps","caps",    0,3,1.75), _k("A","a",1.75,3), _k("S","s",2.75,3), _k("D","d",3.75,3),
    _k("F","f",          4.75,3), _k("G","g",5.75,3), _k("H","h",6.75,3), _k("J","j",7.75,3),
    _k("K","k",          8.75,3), _k("L","l",9.75,3), _k(";",";",10.75,3),
    _k("'","'",         11.75,3), _k("Enter","enter",12.75,3,2.25),

    # Row 4: Shift row
    _k("Shift","shift",  0,4,2.25), _k("Z","z",2.25,4), _k("X","x",3.25,4), _k("C","c",4.25,4),
    _k("V","v",          5.25,4), _k("B","b",6.25,4), _k("N","n",7.25,4), _k("M","m",8.25,4),
    _k(",",",",          9.25,4), _k(".",".".strip(),10.25,4), _k("/","/",11.25,4),
    _k("Shift","shift", 12.25,4,2.75),

    # Row 5: Bottom row — Ctrl Win Alt Space Alt Ctrl
    _k("Ctrl","ctrl",    0,5,1.25), _k("Win","win",1.25,5,1.25), _k("Alt","alt",2.5,5,1.25),
    _k("Space","space",  3.75,5,6.25),
    _k("Alt","alt",     10,5,1.25), _k("Ctrl","ctrl",11.25,5,1.25),
]

# === 导航区 (6键 + 方向键) ===
# 相对于 nav_offset_col
NAV_KEYS_REL = [
    # 6键区 (aligned with rows 1-2)
    _k("Ins","insert",   0,1), _k("Home","home",1,1), _k("PgUp","pgup",2,1),
    _k("Del","delete",   0,2), _k("End","end",  1,2), _k("PgDn","pgdn",2,2),
    # 方向键 (aligned with rows 4-5)
    _k("↑","up",         1,4),
    _k("←","left",       0,5), _k("↓","down",1,5), _k("→","right",2,5),
]

# PrtSc/ScrLk/Pause (aligned with row 0, at nav position)
NAV_TOP_KEYS = [
    _k("PrtSc","printscreen",0,0), _k("ScrLk","scrolllock",1,0), _k("Pause","pause",2,0),
]

# === 数字键盘区 ===
# 相对于 numpad_offset_col
NUMPAD_KEYS_REL = [
    # Row 1
    _k("Num","numlock",  0,1), _k("/","num /",1,1), _k("*","num *",2,1), _k("-","num -",3,1),
    # Row 2
    _k("7","num 7",      0,2), _k("8","num 8",1,2), _k("9","num 9",2,2), _k("+","num +",3,2,1,2),
    # Row 3
    _k("4","num 4",      0,3), _k("5","num 5",1,3), _k("6","num 6",2,3),
    # Row 4
    _k("1","num 1",      0,4), _k("2","num 2",1,4), _k("3","num 3",2,4), _k("Ent","num enter",3,4,1,2),
    # Row 5
    _k("0","num 0",      0,5,2), _k(".","num .",2,5),
]


def _build_all_keys():
    """构建所有按键的绝对坐标列表: (label, key, abs_col, row, cw, rh)"""
    keys = []

    # 主键区
    for label, key, c, r, cw, rh in MAIN_KEYS:
        keys.append((label, key, c, r, cw, rh))

    # 导航区偏移 (主键区最大列 15 + 统一间距 0.935 units)
    nav_off = 15.935
    for label, key, c, r, cw, rh in NAV_TOP_KEYS:
        keys.append((label, key, nav_off + c, r, cw, rh))
    for label, key, c, r, cw, rh in NAV_KEYS_REL:
        keys.append((label, key, nav_off + c, r, cw, rh))

    # 数字键盘偏移 (导航区结束 + 统一间距 0.935 units)
    np_off = nav_off + 3.935
    for label, key, c, r, cw, rh in NUMPAD_KEYS_REL:
        keys.append((label, key, np_off + c, r, cw, rh))

    return keys

ALL_KEYS = _build_all_keys()

# 计算总尺寸
_max_col = max(c + cw for _, _, c, _, cw, _ in ALL_KEYS)
_max_row = max(r + rh for _, _, _, r, _, rh in ALL_KEYS)
KB_WIDTH  = int(_max_col * KEY_UNIT) + PADDING * 2
KB_HEIGHT = int(_max_row * KEY_UNIT) + PADDING * 2

MOD_KEYS = {"shift", "ctrl", "alt", "win", "caps", "tab", "enter",
            "backspace", "space", "insert", "delete", "home", "end",
            "pgup", "pgdn", "numlock", "scrolllock", "pause",
            "printscreen", "esc", "num enter", "num +"}

# ─── 键名映射表（我们的 key_name → keyboard 库需要的名称） ────
_KB_KEY_MAP = {
    "caps":        "caps lock",
    "printscreen": "print screen",
    "scrolllock":  "scroll lock",
    "pgup":        "page up",
    "pgdn":        "page down",
    "numlock":     "num lock",
    "num enter":   "enter",
    "num /":       "/",
    "num *":       "*",
    "num -":       "-",
    "num +":       "+",
    "num .":       ".",
    "num 0":       "0",
    "num 1":       "1",
    "num 2":       "2",
    "num 3":       "3",
    "num 4":       "4",
    "num 5":       "5",
    "num 6":       "6",
    "num 7":       "7",
    "num 8":       "8",
    "num 9":       "9",
}

def _map_key(key_name):
    """将内部 key_name 映射为 keyboard 库识别的名称。"""
    return _KB_KEY_MAP.get(key_name.lower(), key_name.lower())

# ─── 粘滞键状态 ──────────────────────────────────────────────
# toggle 键 (caps/numlock/scrolllock): 按一次开，再按一次关（OS 级 toggle）
# hold 键 (ctrl/shift/alt): 按一次激活，按其他键后自动释放；或再次点击手动释放
STICKY_KEYS = {"caps", "shift", "ctrl", "alt", "numlock", "scrolllock"}
STICKY_TOGGLE_KEYS = {"caps", "numlock", "scrolllock"}  # OS 级 toggle 键
_sticky_state = {"caps": False, "shift": False, "ctrl": False, "alt": False,
                 "numlock": False, "scrolllock": False}
# 存储粘滞键对应的 canvas tag，用于更新 UI 高亮
_sticky_tags = {}   # key_name -> [tag1, tag2, ...]  (同一个键可能有多个按钮，如左右 Shift)
_sticky_canvas = None  # 当前软键盘的 Canvas 引用
_key_text_items = {}  # key_name -> (text_item_id, original_label)  用于 Shift 切换键帽

# Shift 键帽映射：普通 label → Shift 状态下的 label
_SHIFT_LABEL_MAP = {
    # 数字行
    "`": "~", "1": "!", "2": "@", "3": "#", "4": "$",
    "5": "%", "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+",
    # 符号键
    "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?",
    # 字母键 → 大写
    "Q": "Q", "W": "W", "E": "E", "R": "R", "T": "T",
    "Y": "Y", "U": "U", "I": "I", "O": "O", "P": "P",
    "A": "A", "S": "S", "D": "D", "F": "F", "G": "G",
    "H": "H", "J": "J", "K": "K", "L": "L",
    "Z": "Z", "X": "X", "C": "C", "V": "V", "B": "B",
    "N": "N", "M": "M",
}


def _set_sticky_highlight(key_name, active):
    """更新粘滞键的 UI 高亮状态。"""
    if _sticky_canvas is None:
        return
    tags = _sticky_tags.get(key_name, [])
    for tag in tags:
        bg_tag = tag + "_bg"
        items = _sticky_canvas.find_withtag(bg_tag)
        if items:
            fill = C_KEY_ACT if active else C_KEY_MOD
            try:
                _sticky_canvas.itemconfigure(items[0], fill=fill)
            except Exception:
                pass


def _update_shift_labels(active):
    """当 Shift 激活/释放时，动态更新键帽文字。
    active=True → 显示 Shift 符号（!@#$ 等）
    active=False → 恢复原始 label
    """
    if _sticky_canvas is None:
        return
    for label, (text_id, orig_label) in _key_text_items.items():
        try:
            if active:
                shifted = _SHIFT_LABEL_MAP.get(orig_label)
                if shifted:
                    _sticky_canvas.itemconfigure(text_id, text=shifted)
            else:
                _sticky_canvas.itemconfigure(text_id, text=orig_label)
        except Exception:
            pass


def _release_all_sticky_modifiers():
    """释放所有粘滞的 Ctrl/Shift/Alt（不包括 Caps，Caps 是 toggle）。"""
    had_shift = _sticky_state.get("shift", False)
    import keyboard as _kb
    for mod in ("shift", "ctrl", "alt"):
        if _sticky_state[mod]:
            _sticky_state[mod] = False
            try:
                _kb.release(_map_key(mod))
            except Exception:
                pass
            _set_sticky_highlight(mod, False)
    # Shift 释放后恢复键帽
    if had_shift:
        _update_shift_labels(False)


# ─── 软键盘窗口管理 ──────────────────────────────────────────

_soft_kb_instance = None    # Toplevel 引用
_attached_toolbar = None    # 绑定的工具栏窗口
_last_focused_entry = None  # 最后一个获得焦点的 Entry（软键盘点击时回退用）
_focus_bind_id = None       # bind_all 的 ID，用于解绑


def get_kb_instance():
    """获取当前软键盘实例（供 toolbar lift 循环使用）。"""
    return _soft_kb_instance


def toggle_soft_keyboard(toolbar_win, **kwargs):
    """切换软键盘，紧贴 toolbar_win 上方。"""
    global _soft_kb_instance, _attached_toolbar
    if _soft_kb_instance is not None:
        try:
            if _soft_kb_instance.winfo_exists():
                _soft_kb_instance.destroy()
                _soft_kb_instance = None
                _attached_toolbar = None
                return
        except Exception:
            pass
        _soft_kb_instance = None
        _attached_toolbar = None

    _attached_toolbar = toolbar_win
    _soft_kb_instance = open_soft_keyboard(toolbar_win, **kwargs)


def _position_above_toolbar(top, toolbar_win):
    """将软键盘窗口放置在工具栏上方（两种模式统一逻辑）。
    
    定位策略（编辑/运行模式统一）：
    - 水平：与工具栏居中对齐
    - 垂直：紧贴工具栏上方 10px
    - 边缘处理：上方放不下 → 翻到工具栏下方；左右超出 → 夹紧屏幕边缘
    """
    try:
        toolbar_win.update_idletasks()
        tx = toolbar_win.winfo_x()
        ty = toolbar_win.winfo_y()
        tw = toolbar_win.winfo_width()
        th = toolbar_win.winfo_height()
    except Exception:
        return

    kw = KB_WIDTH
    sh = toolbar_win.winfo_screenheight()
    sw = toolbar_win.winfo_screenwidth()

    # 水平：与工具栏居中对齐
    kx = tx + (tw - kw) // 2

    # 垂直：紧贴工具栏上方 10px
    ky = ty - KB_HEIGHT - 10

    # 上方空间不够 → 翻到工具栏下方
    if ky < 0:
        ky = ty + th + 10

    # 确保不超出屏幕（左右、上下夹紧）
    kx = max(0, min(kx, sw - kw))
    ky = max(0, min(ky, sh - KB_HEIGHT))

    top.geometry(f"{kw}x{KB_HEIGHT}+{kx}+{ky}")


def open_soft_keyboard(toolbar_win, *, mode="input", on_pick=None,
                       entry_widget=None, current=""):
    """打开软键盘浮动窗口，紧贴工具栏上方。"""
    global _soft_kb_instance

    parent = toolbar_win.master if toolbar_win.master else toolbar_win

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    top.attributes("-alpha", 0.95)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    # 定位在工具栏上方
    _position_above_toolbar(top, toolbar_win)

    # ─── 焦点追踪：记录最后一个获得焦点的 Entry ──────────
    # 软键盘点击时 tkinter 焦点会转移到 Canvas，用此回退找到目标 Entry
    global _last_focused_entry, _focus_bind_id
    _last_focused_entry = None

    def _on_any_focus_in(event):
        global _last_focused_entry
        w = event.widget
        if isinstance(w, tk.Entry):
            _last_focused_entry = w

    try:
        root = tk._default_root
        if root:
            _focus_bind_id = root.bind_all("<FocusIn>", _on_any_focus_in)
    except Exception:
        _focus_bind_id = None

    # ─── 设置 WS_EX_NOACTIVATE：点击软键盘不抢焦点 ──────────
    try:
        top.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(top.winfo_id())
        if hwnd == 0:
            hwnd = top.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_LAYERED = 0x00080000
        old_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              old_style | WS_EX_NOACTIVATE | WS_EX_LAYERED)
    except Exception:
        pass

    def _on_destroy(e):
        global _soft_kb_instance, _attached_toolbar, _sticky_canvas
        global _last_focused_entry, _focus_bind_id
        if e.widget is top:
            # 解绑焦点追踪
            try:
                root = tk._default_root
                if root and _focus_bind_id:
                    root.unbind_all("<FocusIn>")
                    _focus_bind_id = None
            except Exception:
                pass
            _last_focused_entry = None
            # 关闭键盘时释放所有粘滞修饰键
            try:
                import keyboard as _kb
                for mod in ("shift", "ctrl", "alt"):
                    if _sticky_state[mod]:
                        _sticky_state[mod] = False
                        try:
                            _kb.release(_map_key(mod))
                        except Exception:
                            pass
                # toggle 键状态只重置 UI 标记（它们是 OS 级 toggle，不需要 release）
                for tk_key in STICKY_TOGGLE_KEYS:
                    _sticky_state[tk_key] = False
            except ImportError:
                pass
            _sticky_tags.clear()
            _key_text_items.clear()
            _sticky_canvas = None
            _soft_kb_instance = None
            _attached_toolbar = None
    top.bind("<Destroy>", _on_destroy)

    c = tk.Canvas(top, width=KB_WIDTH, height=KB_HEIGHT,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # 设置粘滞键 canvas 引用
    global _sticky_canvas
    _sticky_canvas = c
    _sticky_tags.clear()
    _key_text_items.clear()

    # 背景 (只圆上面两角，下面贴合工具栏)
    rrect(c, 0, 0, KB_WIDTH, KB_HEIGHT, TOOLBAR_RADIUS,
          fill=C_PM_BG, outline="#444", width=1, tags="kb_bg")

    # ─── 按键点击处理 ────────────────────────────────────────
    current_lower = current.lower() if current else ""

    def _on_key(key_name, tag):
        if not key_name:
            return
        if mode == "input":
            kn_lower = key_name.lower()
            # ── 粘滞键特殊处理 ──
            if kn_lower in STICKY_KEYS:
                _handle_sticky_click(kn_lower)
                return
            # ── 普通键：先模拟，再自动释放粘滞修饰键 ──
            _simulate_key(key_name)
            _flash_key(c, tag)
            return
        elif mode == "pick":
            if on_pick:
                on_pick(key_name.lower())
            top.destroy()
        elif mode == "append":
            if entry_widget:
                cur = entry_widget.get().strip()
                new_text = f"{cur}+{key_name}" if cur else key_name
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, new_text)
            _flash_key(c, tag)

    def _flash_key(canvas, tag):
        bg_tag = tag + "_bg"
        items = canvas.find_withtag(bg_tag)
        if items:
            old_fill = canvas.itemcget(items[0], "fill")
            canvas.itemconfigure(items[0], fill=C_KEY_ACT)
            canvas.after(120, lambda: _safe_restore(canvas, items[0], old_fill))

    def _safe_restore(canvas, item, fill):
        try:
            canvas.itemconfigure(item, fill=fill)
        except Exception:
            pass

    # ─── 绘制所有按键 ────────────────────────────────────────
    for ki, (label, key_name, col, row, cw, rh) in enumerate(ALL_KEYS):
        kx = PADDING + int(col * KEY_UNIT)
        ky = PADDING + int(row * KEY_UNIT)
        kw = int(cw * KEY_UNIT) - KEY_GAP
        kh = int(rh * KEY_UNIT) - KEY_GAP

        if kw < 4 or not label:
            continue

        tag = f"k{ki}"
        tag_bg = tag + "_bg"

        is_current = (mode == "pick" and key_name.lower() == current_lower)
        is_mod = key_name.lower() in MOD_KEYS
        is_sticky = key_name.lower() in STICKY_KEYS

        bg = C_KEY_ACT if is_current else (C_KEY_MOD if is_mod else C_KEY)
        fg = "#000" if is_current else C_KEY_FG
        font = KB_FONT_SM if len(label) > 3 else KB_FONT

        rrect(c, kx, ky, kw, kh, 6,
              fill=bg, outline="", tags=(tag, tag_bg))
        text_id = c.create_text(kx + kw // 2, ky + kh // 2, text=label,
                                font=font, fill=fg, tags=(tag,))

        # 记录 text item ID，供 Shift 切换键帽使用（只记录有 Shift 映射的键）
        if label in _SHIFT_LABEL_MAP:
            _key_text_items[tag] = (text_id, label)

        # 注册粘滞键 tag（同一 key_name 可能有多个按钮，如左右 Shift/Ctrl/Alt）
        if is_sticky:
            kn_low = key_name.lower()
            if kn_low not in _sticky_tags:
                _sticky_tags[kn_low] = []
            _sticky_tags[kn_low].append(tag)

        # hover（粘滞键激活时不被 Leave 覆盖回 normal）
        _bg_normal = bg

        def _mk_enter(t, bh):
            def _en(e):
                items = c.find_withtag(t + "_bg")
                if items:
                    c.itemconfigure(items[0], fill=bh)
            return _en

        def _mk_leave(t, bn, kn=key_name):
            def _lv(e):
                kn_low = kn.lower()
                # 粘滞键激活中 → Leave 时恢复为高亮色而非 normal
                if kn_low in STICKY_KEYS and _sticky_state.get(kn_low, False):
                    items = c.find_withtag(t + "_bg")
                    if items:
                        c.itemconfigure(items[0], fill=C_KEY_ACT)
                    return
                items = c.find_withtag(t + "_bg")
                if items:
                    c.itemconfigure(items[0], fill=bn)
            return _lv

        c.tag_bind(tag, "<Enter>", _mk_enter(tag, C_KEY_H))
        c.tag_bind(tag, "<Leave>", _mk_leave(tag, _bg_normal))
        c.tag_bind(tag, "<Button-1>",
                   lambda e, kn=key_name, t=tag: _on_key(kn, t))

    # pick 模式底部操作栏 (覆盖在最后一行上)
    if mode == "pick":
        bar_y = KB_HEIGHT - 44
        clr_tag = "kb_clear"
        clr_w, clr_h = 160, 34
        # 背景遮挡
        rrect(c, PADDING, bar_y, clr_w, clr_h, 6,
              fill=C_CLOSE, outline="", tags=(clr_tag, clr_tag + "_bg"))
        c.create_text(PADDING + clr_w // 2, bar_y + clr_h // 2,
                      text="清除（不设快捷键）", font=(FF, -14), fill="#FFF", tags=(clr_tag,))
        def _clr_en(e): c.itemconfigure(clr_tag + "_bg", fill=C_CLOSE_H)
        def _clr_lv(e): c.itemconfigure(clr_tag + "_bg", fill=C_CLOSE)
        c.tag_bind(clr_tag, "<Enter>", _clr_en)
        c.tag_bind(clr_tag, "<Leave>", _clr_lv)
        c.tag_bind(clr_tag, "<Button-1>", lambda e: [on_pick("") if on_pick else None, top.destroy()])

        can_tag = "kb_cancel"
        can_w = 80
        can_x = KB_WIDTH - PADDING - can_w
        rrect(c, can_x, bar_y, can_w, clr_h, 6,
              fill=C_GRAY, outline="", tags=(can_tag, can_tag + "_bg"))
        c.create_text(can_x + can_w // 2, bar_y + clr_h // 2,
                      text="取消", font=(FF, -14), fill="#EEE", tags=(can_tag,))
        def _can_en(e): c.itemconfigure(can_tag + "_bg", fill=C_GRAY_H)
        def _can_lv(e): c.itemconfigure(can_tag + "_bg", fill=C_GRAY)
        c.tag_bind(can_tag, "<Enter>", _can_en)
        c.tag_bind(can_tag, "<Leave>", _can_lv)
        c.tag_bind(can_tag, "<Button-1>", lambda e: top.destroy())

    _soft_kb_instance = top
    return top


# ─── 粘滞键点击处理 ──────────────────────────────────────────

def _handle_sticky_click(key_name):
    """处理粘滞键的点击。
    - toggle 键 (caps/numlock/scrolllock): 按一次开，再按一次关（press_and_release）
    - hold 键 (ctrl/shift/alt): 按一次 press（按住），再按一次或按其他键后 release
    """
    try:
        import keyboard as _kb
    except ImportError:
        print(f"[VK] keyboard 库未安装，无法处理粘滞键: {key_name}")
        return

    kn = key_name.lower()
    mapped = _map_key(kn)

    if kn in STICKY_TOGGLE_KEYS:
        # OS 级 toggle 键（Caps Lock / Num Lock / Scroll Lock）
        # 每次点击都 press_and_release 一次切换
        new_state = not _sticky_state[kn]
        _sticky_state[kn] = new_state
        try:
            _kb.press_and_release(mapped)
        except Exception as ex:
            print(f"[VK] {kn} 切换失败: {ex}")
        _set_sticky_highlight(kn, new_state)
    else:
        # Ctrl / Shift / Alt：按一次 press，再按一次 release
        if _sticky_state[kn]:
            # 当前已激活 → 释放
            _sticky_state[kn] = False
            try:
                _kb.release(mapped)
            except Exception as ex:
                print(f"[VK] 释放 {kn} 失败: {ex}")
            _set_sticky_highlight(kn, False)
            # Shift 释放后恢复键帽
            if kn == "shift":
                _update_shift_labels(False)
        else:
            # 当前未激活 → 按下（按住不放）
            _sticky_state[kn] = True
            try:
                _kb.press(mapped)
            except Exception as ex:
                print(f"[VK] 按下 {kn} 失败: {ex}")
            _set_sticky_highlight(kn, True)
            # Shift 激活后切换键帽
            if kn == "shift":
                _update_shift_labels(True)


# ─── 按键模拟（智能输入） ────────────────────────────────────

# 可直接插入到 Entry 的单字符键 (key_name → 实际字符)
_CHAR_MAP = {
    "space": " ",
    "`": "`", "-": "-", "=": "=",
    "[": "[", "]": "]", "\\": "\\",
    ";": ";", "'": "'", ",": ",", ".": ".", "/": "/",
}
# 单字母/单数字直接用 key_name 本身
# 特殊操作键
_ENTRY_ACTION_KEYS = {"backspace", "delete", "enter", "tab"}

def _simulate_key(key_name):
    """智能按键模拟：
    1. 如果 tkinter 应用内有 Entry/Text 控件获得焦点 → 直接插入字符
    2. 否则 → 使用 keyboard 库模拟系统级按键（穿透到游戏/外部窗口）

    按键发送后，自动释放所有粘滞的 Ctrl/Shift/Alt 修饰键。
    """
    if not key_name:
        return

    # 尝试找到 tkinter 应用中获得焦点的 Entry 控件
    focused = _find_focused_entry()
    if focused is not None:
        _insert_to_entry(focused, key_name)
        # Entry 模式下也自动释放粘滞修饰键
        try:
            _release_all_sticky_modifiers()
        except Exception:
            pass
        return

    # 无 tkinter Entry 获焦 → 系统级模拟（使用映射后的键名）
    mapped = _map_key(key_name)
    try:
        import keyboard as _kb
        _kb.press_and_release(mapped)
    except ImportError:
        print(f"[VK] keyboard 库未安装，无法模拟按键: {key_name}")
    except Exception as ex:
        print(f"[VK] 按键模拟失败 '{key_name}' (mapped='{mapped}'): {ex}")

    # 按完普通键后，自动释放所有粘滞的 Ctrl/Shift/Alt
    try:
        _release_all_sticky_modifiers()
    except Exception as ex:
        print(f"[VK] 自动释放粘滞键失败: {ex}")


def _find_focused_entry():
    """查找当前 tkinter 应用中获得焦点的 Entry 控件。
    优先使用 focus_get()，若焦点已被软键盘抢走则回退到 _last_focused_entry。
    返回 tk.Entry 实例或 None（None 时走 keyboard 库穿透到游戏/桌面）。
    """
    try:
        root = tk._default_root
        if root is None:
            return None
        focused = root.focus_get()
        if focused is not None and isinstance(focused, tk.Entry):
            return focused
    except Exception:
        pass

    # 回退：焦点被软键盘 Canvas 抢走时，使用之前记录的最后一个 Entry
    if _last_focused_entry is not None:
        try:
            if _last_focused_entry.winfo_exists():
                return _last_focused_entry
        except Exception:
            pass
    return None


def _insert_to_entry(entry, key_name):
    """将按键内容直接插入到 tkinter Entry 控件中。"""
    kn = key_name.lower()
    try:
        if kn == "backspace":
            # 如果有选中文本，删除选中；否则删除光标前一个字符
            try:
                sel_start = entry.index(tk.SEL_FIRST)
                sel_end = entry.index(tk.SEL_LAST)
                entry.delete(sel_start, sel_end)
            except tk.TclError:
                pos = entry.index(tk.INSERT)
                if pos > 0:
                    entry.delete(pos - 1, pos)
        elif kn == "delete":
            try:
                sel_start = entry.index(tk.SEL_FIRST)
                sel_end = entry.index(tk.SEL_LAST)
                entry.delete(sel_start, sel_end)
            except tk.TclError:
                pos = entry.index(tk.INSERT)
                entry.delete(pos)
        elif kn == "enter":
            # Entry 不支持换行，忽略
            pass
        elif kn == "tab":
            # Entry 中 tab 通常无意义，忽略
            pass
        elif kn in ("shift", "ctrl", "alt", "win", "caps",
                     "insert", "home", "end", "pgup", "pgdn",
                     "numlock", "scrolllock", "pause", "printscreen",
                     "esc"):
            # 修饰键/功能键在 Entry 中无意义，忽略
            pass
        elif kn in ("up", "down", "left", "right"):
            # 方向键：移动光标
            pos = entry.index(tk.INSERT)
            if kn == "left" and pos > 0:
                entry.icursor(pos - 1)
            elif kn == "right":
                entry.icursor(pos + 1)
            # up/down 对单行 Entry 无意义
        elif kn.startswith("f") and kn[1:].isdigit():
            # F1~F12 功能键，忽略
            pass
        elif kn.startswith("num "):
            # 小键盘键：提取实际字符
            num_part = kn[4:]  # "num 7" → "7", "num ." → "."
            if num_part == "enter":
                pass
            elif num_part in ("+", "-", "*", "/", "."):
                entry.insert(tk.INSERT, num_part)
            elif num_part.isdigit():
                entry.insert(tk.INSERT, num_part)
        else:
            # 普通字符键
            char = _CHAR_MAP.get(kn, None)
            if char is not None:
                entry.insert(tk.INSERT, char)
            elif len(kn) == 1:
                # 单字符：字母或数字
                entry.insert(tk.INSERT, kn)
    except Exception as ex:
        print(f"[VK] Entry 插入失败 '{key_name}': {ex}")


# ─── 兼容旧接口 ──────────────────────────────────────────────

def open_virtual_keyboard(parent, entry_widget):
    """打开虚拟键盘（追加模式）。"""
    return open_soft_keyboard(parent, mode="append", entry_widget=entry_widget)


def open_key_picker(parent, on_pick, current=""):
    """打开单键选择弹窗。"""
    return open_soft_keyboard(parent, mode="pick", on_pick=on_pick, current=current)
