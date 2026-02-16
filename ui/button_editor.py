"""
FKB - button_editor.py
按钮编辑弹窗：编辑按键绑定、复制/删除按钮。
"""

import tkinter as tk

from core.constants import COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS
from ui.widgets import (
    FF, FS, IS, BTN_R, CLOSE_SIZE, CLOSE_M,
    C_GRAY, C_GRAY_H, C_PM_BG, C_CLOSE, C_CLOSE_H,
    icon_font, rrect, create_modal_overlay,
)
from ui.virtual_keyboard import open_virtual_keyboard

# 编辑字段定义: (key, label, use_virtual_keyboard)
EDIT_FIELDS = [
    ('name', '按钮名称', False),
    ('lclick', '左键模拟', True),
    ('mclick', '中键模拟', True),
    ('hover', '悬浮模拟', True),
    ('rclick', '右键模拟', True),
    ('wheelup', '滚轮上滚模拟', True),
    ('wheeldown', '滚轮下滚模拟', True),
]


def open_button_editor(parent, btn, *, on_save, on_delete, on_copy, set_window_style):
    """打开按钮编辑弹窗。"""
    overlay = create_modal_overlay(parent)

    width, height = 380, 630
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

    # Background
    rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=C_PM_BG, outline="#444", width=1, tags="bg")

    # Drag
    drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}
    def _ds(e):
        drag["sx"], drag["sy"] = e.x_root, e.y_root
        drag["wx"], drag["wy"] = top.winfo_x(), top.winfo_y()
    def _dm(e):
        nx = drag["wx"] + (e.x_root - drag["sx"])
        ny = drag["wy"] + (e.y_root - drag["sy"])
        top.geometry(f"{width}x{height}+{max(0, min(nx, sw - width))}+{max(0, min(ny, sh - height))}")
    c.tag_bind("bg", "<Button-1>", _ds)
    c.tag_bind("bg", "<B1-Motion>", _dm)

    # Title
    c.create_text(20, 25, text="编辑按钮", font=(FF, 11, "bold"), fill="white", anchor="w", tags="title")
    c.tag_bind("title", "<Button-1>", _ds)
    c.tag_bind("title", "<B1-Motion>", _dm)

    # Inner Title
    c.create_text(width // 2, 60, text="按键配置", font=(FF, 14, "bold"), fill="#E0E0E0", tags="inner_title")

    # Close Button
    ifont = icon_font()
    cx0 = width - CLOSE_M - CLOSE_SIZE
    cy0 = CLOSE_M
    rrect(c, cx0, cy0, CLOSE_SIZE, CLOSE_SIZE, BTN_R, fill=C_CLOSE, outline="", tags=("close", "close_bg"))
    ccx, ccy = cx0 + CLOSE_SIZE // 2, cy0 + CLOSE_SIZE // 2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, IS), fill="#FFF", tags=("close",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(FF, FS, "bold"), fill="#FFF", tags=("close",))

    def _ce(e): i = c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE_H)
    def _cl(e): i = c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE)
    c.tag_bind("close", "<Enter>", _ce)
    c.tag_bind("close", "<Leave>", _cl)
    c.tag_bind("close", "<Button-1>", lambda e: top.destroy())

    # Form
    form_y = 90
    form_h = height - form_y - 160
    form_frame = tk.Frame(top, bg=C_PM_BG)
    form_frame.place(x=20, y=form_y, width=width - 40, height=form_h)

    entries = {}

    for idx, (key, label_text, use_vk) in enumerate(EDIT_FIELDS):
        if key not in btn:
            btn[key] = ''

        lbl = tk.Label(form_frame, text=label_text, bg=C_PM_BG, fg="#CCC", font=(FF, 10), anchor="w")
        lbl.grid(row=idx, column=0, sticky="w", pady=5)

        e_frame = tk.Frame(form_frame, bg=C_PM_BG)
        e_frame.grid(row=idx, column=1, sticky="ew", padx=(10, 0), pady=5)

        e = tk.Entry(e_frame, font=(FF, 10), bg=C_GRAY, fg="white",
                     insertbackground="white", relief="flat", bd=5)
        e.pack(side="left", fill="x", expand=True)
        e.insert(0, btn[key])
        entries[key] = e

        if use_vk:
            vk_btn = tk.Label(e_frame, text="\u2328", bg=C_GRAY, fg="#AAA", font=(FF, 12))
            vk_btn.pack(side="right", padx=(5, 0))
            vk_btn.bind("<Button-1>", lambda ev, ent=e: open_virtual_keyboard(top, ent))

    form_frame.columnconfigure(1, weight=1)

    # === Bottom Buttons ===
    padding = 20
    btn_h = 40
    btn_gap = 10

    # Row 2 (bottom): Delete + Save
    row2_y = height - padding - btn_h
    total_w = width - padding * 2
    half_w = (total_w - btn_gap) // 2

    # Delete
    del_x = padding
    rrect(c, del_x, row2_y, half_w, btn_h, BTN_R, fill="#6E1E1E", outline="", tags=("del", "del_bg"))
    c.create_text(del_x + half_w // 2, row2_y + btn_h // 2, text="删除",
                  font=(FF, FS), fill="white", tags=("del",))

    def _del_enter(e): c.itemconfigure("del_bg", fill="#8B2020")
    def _del_leave(e): c.itemconfigure("del_bg", fill="#6E1E1E")
    c.tag_bind("del", "<Enter>", _del_enter)
    c.tag_bind("del", "<Leave>", _del_leave)
    c.tag_bind("del", "<Button-1>", lambda e: [on_delete(btn), top.destroy()])

    # Save
    save_x = padding + half_w + btn_gap
    rrect(c, save_x, row2_y, half_w, btn_h, BTN_R, fill="#007A7A", outline="", tags=("save", "save_bg"))
    c.create_text(save_x + half_w // 2, row2_y + btn_h // 2, text="保存",
                  font=(FF, FS), fill="white", tags=("save",))

    def _save_enter(e): c.itemconfigure("save_bg", fill="#009999")
    def _save_leave(e): c.itemconfigure("save_bg", fill="#007A7A")
    c.tag_bind("save", "<Enter>", _save_enter)
    c.tag_bind("save", "<Leave>", _save_leave)

    def do_save(e=None):
        for k, e_widget in entries.items():
            v = e_widget.get().replace(" ", "").lower() if k != 'name' else e_widget.get()
            btn[k] = v
        on_save(btn)
        top.destroy()
    c.tag_bind("save", "<Button-1>", do_save)

    # Row 1: Copy button (full width)
    copy_y = row2_y - btn_gap - btn_h
    copy_w = total_w
    copy_x = padding
    rrect(c, copy_x, copy_y, copy_w, btn_h, BTN_R, fill=C_GRAY, outline="", tags=("copy", "copy_bg"))

    copy_cy = copy_y + btn_h // 2
    if ifont:
        icon_x = copy_x + copy_w // 2 - 40
        text_x = icon_x + 20 + 12
        c.create_text(icon_x, copy_cy, text="\uE8C8",
                      font=(ifont, IS), fill="#E0E0E0", anchor="center", tags=("copy",))
        c.create_text(text_x, copy_cy, text="复制按钮",
                      font=(FF, FS), fill="#E0E0E0", anchor="w", tags=("copy",))
    else:
        c.create_text(copy_x + copy_w // 2, copy_cy, text="复制按钮",
                      font=(FF, FS, "bold"), fill="#E0E0E0", tags=("copy",))

    def _copy_enter(e): c.itemconfigure("copy_bg", fill=C_GRAY_H)
    def _copy_leave(e): c.itemconfigure("copy_bg", fill=C_GRAY)
    c.tag_bind("copy", "<Enter>", _copy_enter)
    c.tag_bind("copy", "<Leave>", _copy_leave)
    c.tag_bind("copy", "<Button-1>", lambda e: [on_copy(btn), top.destroy()])

    return top
