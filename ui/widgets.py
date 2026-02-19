"""
TEGG Touch 蛋挞 - widgets.py
通用 UI 组件：圆角矩形、图标字体检测、模态遮罩、样式化弹窗。
所有弹窗/面板共享的基础设施。
"""

import tkinter as tk
import tkinter.font as tkfont
from core.constants import (
    COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS,
)

# ─── 字体常量 ─────────────────────────────────────────────────
FF = "Microsoft YaHei UI"
FI = "Segoe Fluent Icons"
FI2 = "Segoe MDL2 Assets"

# ─── 尺寸常量 ─────────────────────────────────────────────────
TOP = 10;  BTN_H = 40;  BTN_R = 10;  GAP = 8
FS = -18;  IS = -20  # font / icon size (px, negative = px in tkinter)
CLOSE_SIZE = 40;  CLOSE_M = 10
DRAG_W = 28
SL_LABEL_GAP = 16;  SL_H = 8;  SL_TR = 12

# ─── 颜色常量 ─────────────────────────────────────────────────
C_CYBER     = "#0C4A6E"
C_CYBER_H   = "#0284C7"
C_GRAY      = "#3A3A3A"
C_GRAY_H    = "#505050"
C_AMBER     = "#F59E0B"
C_AMBER_D   = "#D97706"
C_CLOSE     = "#6E1E1E"
C_CLOSE_H   = "#8B2020"
C_PM_BG     = "#2D2D2D"
C_PM_ITEM   = "#3A3A3A"
C_PM_SEL    = "#F59E0B"
C_PM_HOVER  = "#474747"


# ─── 工具函数 ─────────────────────────────────────────────────

def icon_font():
    """检测可用的图标字体，返回字体名或 None。"""
    try:
        ff = tkfont.families()
        if FI in ff: return FI
        if FI2 in ff: return FI2
    except Exception:
        pass
    return None


def rrect(c, x, y, w, h, r, **kw):
    """在 Canvas 上绘制圆角矩形。"""
    pts = [x+r,y, x+w-r,y, x+w,y, x+w,y+r, x+w,y+h-r, x+w,y+h,
           x+w-r,y+h, x+r,y+h, x,y+h, x,y+h-r, x,y+r, x,y]
    return c.create_polygon(pts, smooth=True, **kw)


def create_modal_overlay(parent):
    """创建全屏 50% 黑色遮罩层（穿透点击）。"""
    overlay = tk.Toplevel(parent)
    overlay.attributes('-alpha', 0.5)
    overlay.configure(bg='black')
    overlay.overrideredirect(True)
    w = parent.winfo_screenwidth()
    h = parent.winfo_screenheight()
    overlay.geometry(f"{w}x{h}+0+0")
    overlay.attributes('-topmost', True)

    try:
        import ctypes
        overlay.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(overlay.winfo_id())
        if hwnd == 0:
            hwnd = overlay.winfo_id()
        GWL_EXSTYLE = -20
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= 0x00080000 | 0x00000020  # WS_EX_LAYERED | WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass

    return overlay


def draw_close_button(c, width, tags_prefix="close"):
    """在弹窗右上角绘制关闭按钮，返回 (tag_group, destroy_callback)。"""
    cx0 = width - CLOSE_M - CLOSE_SIZE
    cy0 = CLOSE_M
    tag = tags_prefix
    tag_bg = f"{tags_prefix}_bg"
    
    rrect(c, cx0, cy0, CLOSE_SIZE, CLOSE_SIZE, BTN_R,
          fill=C_CLOSE, outline="", tags=(tag, tag_bg))
    
    ifont = icon_font()
    ccx, ccy = cx0 + CLOSE_SIZE // 2, cy0 + CLOSE_SIZE // 2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, IS), fill="#FFF", tags=(tag,))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(FF, FS, "bold"), fill="#FFF", tags=(tag,))
    
    def _ce(e): i = c.find_withtag(tag_bg); i and c.itemconfigure(i[0], fill=C_CLOSE_H)
    def _cl(e): i = c.find_withtag(tag_bg); i and c.itemconfigure(i[0], fill=C_CLOSE)
    c.tag_bind(tag, "<Enter>", _ce)
    c.tag_bind(tag, "<Leave>", _cl)
    
    return tag


def setup_drag(c, top, width, height, sw, sh, bind_tags=("bg",)):
    """为弹窗设置拖拽功能。"""
    drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}

    def _ds(e):
        drag["sx"], drag["sy"] = e.x_root, e.y_root
        drag["wx"], drag["wy"] = top.winfo_x(), top.winfo_y()

    def _dm(e):
        nx = drag["wx"] + (e.x_root - drag["sx"])
        ny = drag["wy"] + (e.y_root - drag["sy"])
        top.geometry(f"{width}x{height}+{max(0, min(nx, sw - width))}+{max(0, min(ny, sh - height))}")

    for t in bind_tags:
        c.tag_bind(t, "<Button-1>", _ds)
        c.tag_bind(t, "<B1-Motion>", _dm)

    return _ds, _dm


def create_styled_dialog(parent, title, width, height, on_confirm=None, initial_value=None, label_text=None):
    """创建模态输入弹窗（暗色主题、圆角）。返回 (top, entry_widget)。"""
    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2

    overlay = create_modal_overlay(parent)

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.geometry(f"{width}x{height}+{x}+{y}")
    top.attributes("-topmost", True)
    top.attributes("-alpha", 1.0)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    def _destroy_all(e):
        try: overlay.destroy()
        except: pass
    top.bind("<Destroy>", _destroy_all, add="+")

    top.grab_set()
    top.focus_set()
    overlay.attributes("-topmost", True)
    top.attributes("-topmost", True)
    top.lift()

    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # Background
    rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=C_PM_BG, outline="#444", width=1, tags="bg")

    # Drag
    _ds, _dm = setup_drag(c, top, width, height, sw, sh, bind_tags=("bg",))

    # Title
    c.create_text(20, 25, text=title, font=(FF, 11, "bold"), fill="white", anchor="w", tags="title")
    c.tag_bind("title", "<Button-1>", _ds)
    c.tag_bind("title", "<B1-Motion>", _dm)

    # Close Button
    close_tag = draw_close_button(c, width)
    c.tag_bind(close_tag, "<Button-1>", lambda e: top.destroy())

    # Content Area
    content_y = 60
    if label_text:
        lbl = tk.Label(top, text=label_text, bg=C_PM_BG, fg="#CCC", font=(FF, 10))
        lbl.place(x=20, y=content_y)
        content_y += 35

    entry = tk.Entry(top, font=(FF, 10), bg=C_GRAY, fg="white",
                     insertbackground="white", relief="flat", bd=5)
    entry.place(x=20, y=content_y, width=width - 40)
    if initial_value:
        entry.insert(0, initial_value)
        entry.select_range(0, tk.END)
    entry.focus_set()

    # Confirm Button
    btn_y = height - 60
    btn_w = 100
    btn_h = 40
    bx = (width - btn_w) // 2

    rrect(c, bx, btn_y, btn_w, btn_h, 6, fill=C_AMBER, outline="", tags=("btn", "btn_bg"))
    c.create_text(bx + btn_w // 2, btn_y + btn_h // 2, text="\u786e\u5b9a",
                  font=(FF, FS), fill="black", tags=("btn",))

    def _be(e): c.itemconfigure("btn_bg", fill=C_AMBER_D)
    def _bl(e): c.itemconfigure("btn_bg", fill=C_AMBER)
    c.tag_bind("btn", "<Enter>", _be)
    c.tag_bind("btn", "<Leave>", _bl)

    def _on_ok(event=None):
        if on_confirm:
            val = entry.get().strip()
            on_confirm(val)

    c.tag_bind("btn", "<Button-1>", _on_ok)
    entry.bind("<Return>", _on_ok)

    return top, entry


def create_styled_yesno_dialog(parent, title, message_text, on_yes):
    """创建样式化确认弹窗（是/否）。"""
    overlay = create_modal_overlay(parent)

    width, height = 360, 200
    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.geometry(f"{width}x{height}+{x}+{y}")
    top.attributes("-topmost", True)
    top.attributes("-alpha", 1.0)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    def _destroy_all(e):
        try: overlay.destroy()
        except: pass
    top.bind("<Destroy>", _destroy_all, add="+")

    top.grab_set()
    top.focus_set()
    overlay.attributes("-topmost", True)
    top.attributes("-topmost", True)
    top.lift()

    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=C_PM_BG, outline="#444", width=1, tags="bg")

    _ds, _dm = setup_drag(c, top, width, height, sw, sh, bind_tags=("bg",))

    c.create_text(20, 25, text=title, font=(FF, 11, "bold"), fill="white", anchor="w", tags="title")
    c.tag_bind("title", "<Button-1>", _ds)
    c.tag_bind("title", "<B1-Motion>", _dm)

    close_tag = draw_close_button(c, width)
    c.tag_bind(close_tag, "<Button-1>", lambda e: top.destroy())

    # Message
    lbl = tk.Label(top, text=message_text, bg=C_PM_BG, fg="white", font=(FF, 10), wraplength=width - 40)
    lbl.place(x=20, y=70, width=width - 40)

    # Buttons
    btn_w, btn_h = 90, 40
    total_btn_w = btn_w * 2 + 20
    start_x = (width - total_btn_w) // 2
    btn_y = height - 60

    # Yes
    rrect(c, start_x, btn_y, btn_w, btn_h, 6, fill=C_AMBER, outline="", tags=("yes", "yes_bg"))
    c.create_text(start_x + btn_w // 2, btn_y + btn_h // 2, text="\u786e\u5b9a",
                  font=(FF, FS), fill="black", tags=("yes",))

    def _ye(e): c.itemconfigure("yes_bg", fill=C_AMBER_D)
    def _yl(e): c.itemconfigure("yes_bg", fill=C_AMBER)
    c.tag_bind("yes", "<Enter>", _ye)
    c.tag_bind("yes", "<Leave>", _yl)
    c.tag_bind("yes", "<Button-1>", lambda e: [on_yes(), top.destroy()])

    # No
    no_x = start_x + btn_w + 20
    rrect(c, no_x, btn_y, btn_w, btn_h, 6, fill=C_GRAY, outline="", tags=("no", "no_bg"))
    c.create_text(no_x + btn_w // 2, btn_y + btn_h // 2, text="\u53d6\u6d88",
                  font=(FF, FS), fill="#EEE", tags=("no",))

    def _ne(e): c.itemconfigure("no_bg", fill=C_GRAY_H)
    def _nl(e): c.itemconfigure("no_bg", fill=C_GRAY)
    c.tag_bind("no", "<Enter>", _ne)
    c.tag_bind("no", "<Leave>", _nl)
    c.tag_bind("no", "<Button-1>", lambda e: top.destroy())

    return top
