"""
TEGG Touch - virtual_keyboard.py
可复用软键盘组件（统一暗色 UI 风格，108 键标准布局）。

软键盘作为工具栏的向上扩展，紧贴工具栏上方 10px，同层级管理。

三种使用模式:
  mode="input"  — 点击按键模拟真实键盘输入
  mode="pick"   — 点击按键后回调 on_pick(key) 并关闭
  mode="append" — 点击按键追加到 entry_widget
"""

import tkinter as tk

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
C_KEY      = "#3A3A3A"
C_KEY_H    = "#555555"
C_KEY_ACT  = "#D97706"
C_KEY_FG   = "#E0E0E0"
C_KEY_MOD  = "#2F2F2F"

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

    # 导航区偏移 (主键区最大列 ~15 + gap)
    nav_off = 15.75
    for label, key, c, r, cw, rh in NAV_TOP_KEYS:
        keys.append((label, key, nav_off + c, r, cw, rh))
    for label, key, c, r, cw, rh in NAV_KEYS_REL:
        keys.append((label, key, nav_off + c, r, cw, rh))

    # 数字键盘偏移 (导航区结束 ~15.75+3 + gap)
    np_off = nav_off + 3.5
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

# ─── 软键盘窗口管理 ──────────────────────────────────────────

_soft_kb_instance = None    # Toplevel 引用
_attached_toolbar = None    # 绑定的工具栏窗口


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
    """将软键盘窗口放置在工具栏正上方 10px。"""
    try:
        toolbar_win.update_idletasks()
        tx = toolbar_win.winfo_x()
        ty = toolbar_win.winfo_y()
        tw = toolbar_win.winfo_width()
    except Exception:
        return

    kw = KB_WIDTH
    # 水平居中对齐工具栏
    kx = tx + (tw - kw) // 2
    ky = ty - KB_HEIGHT - 10

    # 确保不超出屏幕
    sw = toolbar_win.winfo_screenwidth()
    kx = max(0, min(kx, sw - kw))
    ky = max(0, ky)

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

    def _on_destroy(e):
        global _soft_kb_instance, _attached_toolbar
        if e.widget is top:
            _soft_kb_instance = None
            _attached_toolbar = None
    top.bind("<Destroy>", _on_destroy)

    c = tk.Canvas(top, width=KB_WIDTH, height=KB_HEIGHT,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # 背景 (只圆上面两角，下面贴合工具栏)
    rrect(c, 0, 0, KB_WIDTH, KB_HEIGHT, TOOLBAR_RADIUS,
          fill=C_PM_BG, outline="#444", width=1, tags="kb_bg")

    # ─── 按键点击处理 ────────────────────────────────────────
    current_lower = current.lower() if current else ""

    def _on_key(key_name, tag):
        if not key_name:
            return
        if mode == "input":
            _simulate_key(key_name)
            _flash_key(c, tag)
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

        bg = C_KEY_ACT if is_current else (C_KEY_MOD if is_mod else C_KEY)
        fg = "#000" if is_current else C_KEY_FG
        font = KB_FONT_SM if len(label) > 3 else KB_FONT

        rrect(c, kx, ky, kw, kh, 6,
              fill=bg, outline="", tags=(tag, tag_bg))
        c.create_text(kx + kw // 2, ky + kh // 2, text=label,
                      font=font, fill=fg, tags=(tag,))

        # hover
        _bg_normal = bg

        def _mk_enter(t, bh):
            def _en(e):
                items = c.find_withtag(t + "_bg")
                if items:
                    c.itemconfigure(items[0], fill=bh)
            return _en

        def _mk_leave(t, bn):
            def _lv(e):
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


# ─── 按键模拟 ────────────────────────────────────────────────

def _simulate_key(key_name):
    """使用 keyboard 库模拟按键。"""
    if not key_name:
        return
    try:
        import keyboard as _kb
        _kb.press_and_release(key_name)
    except ImportError:
        print(f"[VK] keyboard 库未安装，无法模拟按键: {key_name}")
    except Exception as ex:
        print(f"[VK] 按键模拟失败 '{key_name}': {ex}")


# ─── 兼容旧接口 ──────────────────────────────────────────────

def open_virtual_keyboard(parent, entry_widget):
    """打开虚拟键盘（追加模式）。"""
    return open_soft_keyboard(parent, mode="append", entry_widget=entry_widget)


def open_key_picker(parent, on_pick, current=""):
    """打开单键选择弹窗。"""
    return open_soft_keyboard(parent, mode="pick", on_pick=on_pick, current=current)
