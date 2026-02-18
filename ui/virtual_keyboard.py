"""
TEGG Touch - virtual_keyboard.py
可复用软键盘组件（统一暗色 UI 风格）。

三种使用模式:
  mode="input"  — 点击按键模拟真实键盘输入 (keyboard.press_and_release)
  mode="pick"   — 点击按键后回调 on_pick(key) 并关闭 (用于冻结键选择等)
  mode="append" — 点击按键追加到 entry_widget (用于按钮编辑器)
"""

import tkinter as tk

from core.constants import COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS
from ui.widgets import (
    FF, IS, BTN_R,
    C_PM_BG, C_GRAY, C_GRAY_H, C_AMBER, C_AMBER_D,
    C_CLOSE, C_CLOSE_H, C_CYBER,
    CLOSE_SIZE, CLOSE_M,
    icon_font, rrect, setup_drag, draw_close_button,
)

# ─── 键盘布局 ────────────────────────────────────────────────
# 每个条目: (label, key_name, width_units)
# width_units=1 → 40px; 1.5→60px; 2→80px 等

_R1 = [("Esc","esc",1), ("F1","f1",1), ("F2","f2",1), ("F3","f3",1),
       ("F4","f4",1), ("F5","f5",1), ("F6","f6",1), ("F7","f7",1),
       ("F8","f8",1), ("F9","f9",1), ("F10","f10",1), ("F11","f11",1), ("F12","f12",1),
       ("PrtSc","printscreen",1), ("Pause","pause",1)]
_R2 = [("`","`",1), ("1","1",1), ("2","2",1), ("3","3",1), ("4","4",1),
       ("5","5",1), ("6","6",1), ("7","7",1), ("8","8",1), ("9","9",1),
       ("0","0",1), ("-","-",1), ("=","=",1), ("⌫","backspace",2)]
_R3 = [("Tab","tab",1.5), ("Q","q",1), ("W","w",1), ("E","e",1), ("R","r",1),
       ("T","t",1), ("Y","y",1), ("U","u",1), ("I","i",1), ("O","o",1),
       ("P","p",1), ("[","[",1), ("]","]",1), ("\\","\\",1.5)]
_R4 = [("Caps","caps",1.8), ("A","a",1), ("S","s",1), ("D","d",1), ("F","f",1),
       ("G","g",1), ("H","h",1), ("J","j",1), ("K","k",1), ("L","l",1),
       (";",";",1), ("'","'",1), ("Enter","enter",2.2)]
_R5 = [("Shift","shift",2.3), ("Z","z",1), ("X","x",1), ("C","c",1), ("V","v",1),
       ("B","b",1), ("N","n",1), ("M","m",1), (",",",",1), (".",".".strip(),1),
       ("/","/",1), ("↑","up",1), ("Shift","shift",1.7)]
_R6 = [("Ctrl","ctrl",1.5), ("Win","win",1.2), ("Alt","alt",1.2),
       ("Space","space",5),
       ("Alt","alt",1.2), ("←","left",1), ("↓","down",1), ("→","right",1), ("Ctrl","ctrl",1.5)]
_R7 = [("Ins","insert",1), ("Home","home",1), ("PgUp","pgup",1),
       ("Del","delete",1), ("End","end",1), ("PgDn","pgdn",1),
       ("","",0.4),  # spacer
       ("Num","numlock",1), ("Np0","num 0",1), ("Np5","num 5",1),
       ("Np.","num .",1), ("ScLk","scrolllock",1)]

KEYBOARD_LAYOUT = [_R1, _R2, _R3, _R4, _R5, _R6, _R7]

# ─── 尺寸常量 ────────────────────────────────────────────────
KEY_SIZE   = 40   # 最小按键尺寸
KEY_GAP    = 4    # 按键间距
KEY_UNIT   = KEY_SIZE + KEY_GAP  # 44px
PADDING    = 14
TITLE_H    = 50
KB_FONT    = ("Consolas", 9, "bold")

# 键帽颜色
C_KEY      = "#3A3A3A"
C_KEY_H    = "#555555"
C_KEY_ACT  = "#D97706"  # 当前选中 / 按下闪烁
C_KEY_FG   = "#E0E0E0"
C_KEY_MOD  = "#2F2F2F"  # 修饰键底色稍深


def _calc_row_width(row):
    """计算一行的像素宽度。"""
    w = 0
    for _, _, wu in row:
        w += int(wu * KEY_UNIT)
    return w


def _max_row_width():
    return max(_calc_row_width(r) for r in KEYBOARD_LAYOUT)


# ─── 软键盘窗口管理 ──────────────────────────────────────────

_soft_kb_instance = None  # 全局单例引用


def toggle_soft_keyboard(parent, **kwargs):
    """切换软键盘显示/隐藏。若已打开则关闭，否则打开。"""
    global _soft_kb_instance
    if _soft_kb_instance is not None:
        try:
            if _soft_kb_instance.winfo_exists():
                _soft_kb_instance.destroy()
                _soft_kb_instance = None
                return
        except Exception:
            pass
        _soft_kb_instance = None

    _soft_kb_instance = open_soft_keyboard(parent, **kwargs)


def open_soft_keyboard(parent, *, mode="input", on_pick=None,
                       entry_widget=None, current=""):
    """打开软键盘浮动窗口。

    Args:
        parent: 父窗口
        mode: "input" | "pick" | "append"
        on_pick: mode="pick" 时的回调 on_pick(key_name)
        entry_widget: mode="append" 时的目标 Entry
        current: mode="pick" 时高亮显示的当前键
    Returns:
        Toplevel 窗口对象
    """
    global _soft_kb_instance

    max_rw = _max_row_width()
    width = max_rw + PADDING * 2
    n_rows = len(KEYBOARD_LAYOUT)
    height = TITLE_H + n_rows * KEY_UNIT + PADDING + (40 if mode in ("pick", "append") else 0)

    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - width) // 2
    y = sh - height - 80

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.geometry(f"{width}x{height}+{x}+{y}")
    top.attributes("-topmost", True)
    top.attributes("-alpha", 0.95)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    def _on_destroy(e):
        global _soft_kb_instance
        if e.widget is top:
            _soft_kb_instance = None
    top.bind("<Destroy>", _on_destroy)

    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # 背景
    rrect(c, 0, 0, width, height, TOOLBAR_RADIUS,
          fill=C_PM_BG, outline="#444", width=1, tags="kb_bg")

    ifont = icon_font()

    # 拖拽
    setup_drag(c, top, width, height, sw, sh, bind_tags=("kb_bg", "kb_title"))

    # 标题
    title_map = {"input": "软键盘", "pick": "选择快捷键", "append": "虚拟键盘"}
    c.create_text(PADDING, TITLE_H // 2, text=title_map.get(mode, "软键盘"),
                  font=(FF, 11, "bold"), fill="white", anchor="w", tags="kb_title")

    # 关闭按钮
    close_tag = draw_close_button(c, width)
    c.tag_bind(close_tag, "<Button-1>", lambda e: top.destroy())

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
        """按键按下时闪烁效果。"""
        bg_tag = tag + "_bg"
        items = canvas.find_withtag(bg_tag)
        if items:
            canvas.itemconfigure(items[0], fill=C_KEY_ACT)
            canvas.after(120, lambda: _safe_restore(canvas, items[0], tag))

    def _safe_restore(canvas, item, tag):
        try:
            canvas.itemconfigure(item, fill=C_KEY)
        except Exception:
            pass

    # ─── 绘制按键 ────────────────────────────────────────────
    MOD_KEYS = {"shift", "ctrl", "alt", "win", "caps", "tab", "enter",
                "backspace", "space", "insert", "delete", "home", "end",
                "pgup", "pgdn", "numlock", "scrolllock", "pause", "printscreen", "esc"}

    for ri, row in enumerate(KEYBOARD_LAYOUT):
        kx = PADDING
        ky = TITLE_H + ri * KEY_UNIT
        for ki, (label, key_name, wu) in enumerate(row):
            kw = int(wu * KEY_UNIT) - KEY_GAP
            kh = KEY_SIZE
            if kw < 4 or not label:
                kx += int(wu * KEY_UNIT)
                continue

            tag = f"k_{ri}_{ki}"
            tag_bg = tag + "_bg"

            is_current = (mode == "pick" and key_name.lower() == current_lower)
            is_mod = key_name.lower() in MOD_KEYS

            bg = C_KEY_ACT if is_current else (C_KEY_MOD if is_mod else C_KEY)
            fg = "#000" if is_current else C_KEY_FG

            rrect(c, kx, ky, kw, kh, 6,
                  fill=bg, outline="", tags=(tag, tag_bg))
            c.create_text(kx + kw // 2, ky + kh // 2, text=label,
                          font=KB_FONT, fill=fg, tags=(tag,))

            # hover
            _bg_normal = bg

            def _make_enter(t, bg_h):
                def _en(e):
                    items = c.find_withtag(t + "_bg")
                    if items:
                        c.itemconfigure(items[0], fill=bg_h)
                return _en

            def _make_leave(t, bg_n):
                def _lv(e):
                    items = c.find_withtag(t + "_bg")
                    if items:
                        c.itemconfigure(items[0], fill=bg_n)
                return _lv

            c.tag_bind(tag, "<Enter>", _make_enter(tag, C_KEY_H))
            c.tag_bind(tag, "<Leave>", _make_leave(tag, _bg_normal))
            c.tag_bind(tag, "<Button-1>",
                       lambda e, kn=key_name, t=tag: _on_key(kn, t))

            kx += int(wu * KEY_UNIT)

    # ─── 底部操作栏 (pick / append 模式) ─────────────────────
    if mode == "pick":
        bar_y = height - 44
        # 清除按钮
        clr_tag = "kb_clear"
        clr_w, clr_h = 160, 34
        clr_x = PADDING
        rrect(c, clr_x, bar_y, clr_w, clr_h, 6,
              fill=C_CLOSE, outline="", tags=(clr_tag, clr_tag + "_bg"))
        c.create_text(clr_x + clr_w // 2, bar_y + clr_h // 2,
                      text="清除（不设快捷键）", font=(FF, -14), fill="#FFF", tags=(clr_tag,))

        def _clr_en(e): c.itemconfigure(clr_tag + "_bg", fill=C_CLOSE_H)
        def _clr_lv(e): c.itemconfigure(clr_tag + "_bg", fill=C_CLOSE)
        c.tag_bind(clr_tag, "<Enter>", _clr_en)
        c.tag_bind(clr_tag, "<Leave>", _clr_lv)
        c.tag_bind(clr_tag, "<Button-1>", lambda e: [on_pick("") if on_pick else None, top.destroy()])

        # 取消按钮
        can_tag = "kb_cancel"
        can_w = 80
        can_x = width - PADDING - can_w
        rrect(c, can_x, bar_y, can_w, clr_h, 6,
              fill=C_GRAY, outline="", tags=(can_tag, can_tag + "_bg"))
        c.create_text(can_x + can_w // 2, bar_y + clr_h // 2,
                      text="取消", font=(FF, -14), fill="#EEE", tags=(can_tag,))

        def _can_en(e): c.itemconfigure(can_tag + "_bg", fill=C_GRAY_H)
        def _can_lv(e): c.itemconfigure(can_tag + "_bg", fill=C_GRAY)
        c.tag_bind(can_tag, "<Enter>", _can_en)
        c.tag_bind(can_tag, "<Leave>", _can_lv)
        c.tag_bind(can_tag, "<Button-1>", lambda e: top.destroy())

    elif mode == "append":
        bar_y = height - 44
        # 清除按钮
        clr_tag = "kb_clear"
        clr_w, clr_h = 120, 34
        clr_x = PADDING
        rrect(c, clr_x, bar_y, clr_w, clr_h, 6,
              fill=C_CLOSE, outline="", tags=(clr_tag, clr_tag + "_bg"))
        c.create_text(clr_x + clr_w // 2, bar_y + clr_h // 2,
                      text="清除输入框", font=(FF, -14), fill="#FFF", tags=(clr_tag,))

        def _clr_en2(e): c.itemconfigure(clr_tag + "_bg", fill=C_CLOSE_H)
        def _clr_lv2(e): c.itemconfigure(clr_tag + "_bg", fill=C_CLOSE)
        c.tag_bind(clr_tag, "<Enter>", _clr_en2)
        c.tag_bind(clr_tag, "<Leave>", _clr_lv2)

        def _clear_entry():
            if entry_widget:
                entry_widget.delete(0, tk.END)
        c.tag_bind(clr_tag, "<Button-1>", lambda e: _clear_entry())

    # 保持顶层
    def _keep():
        try:
            if top.winfo_exists():
                top.lift()
                top.after(500, _keep)
        except Exception:
            pass
    top.lift()
    top.after(200, _keep)

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
    """打开虚拟键盘（追加模式）—— 兼容旧代码。"""
    return open_soft_keyboard(parent, mode="append", entry_widget=entry_widget)


def open_key_picker(parent, on_pick, current=""):
    """打开单键选择弹窗 —— 兼容旧代码。"""
    return open_soft_keyboard(parent, mode="pick", on_pick=on_pick, current=current)
