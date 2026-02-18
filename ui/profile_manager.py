"""
TEGG Touch - profile_manager.py
方案管理弹窗：列表、新建、复制、重命名、删除、导入、导出。
"""

import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.filedialog as filedialog

from core.constants import COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS
from core.config_manager import (
    list_profiles, get_active_profile_name,
    create_profile, delete_profile, rename_profile,
    export_profile, import_profile,
    load_profile, save_profile,
)
from ui.widgets import (
    FF, FS, IS, BTN_H, BTN_R, CLOSE_SIZE, CLOSE_M,
    C_GRAY, C_GRAY_H, C_CLOSE, C_CLOSE_H,
    C_PM_BG, C_PM_ITEM, C_PM_SEL,
    icon_font, rrect,
    create_modal_overlay, create_styled_dialog, create_styled_yesno_dialog,
)


def open_profile_manager(parent, on_switch):
    """打开方案管理弹窗。"""
    overlay = create_modal_overlay(parent)

    width, height = 480, 540
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

    rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=C_PM_BG, outline="#444", width=1, tags="pm_bg")

    # Drag
    drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}
    def _ds(e):
        drag["sx"], drag["sy"] = e.x_root, e.y_root
        drag["wx"], drag["wy"] = top.winfo_x(), top.winfo_y()
    def _dm(e):
        nx = drag["wx"] + (e.x_root - drag["sx"])
        ny = drag["wy"] + (e.y_root - drag["sy"])
        top.geometry(f"{width}x{height}+{max(0, min(nx, sw - width))}+{max(0, min(ny, sh - height))}")

    c.tag_bind("pm_bg", "<Button-1>", _ds)
    c.tag_bind("pm_bg", "<B1-Motion>", _dm)

    # Header
    padding = 20
    c.create_text(padding, 30, text="\u65b9\u6848\u7ba1\u7406",
                  font=(FF, 12, "bold"), fill="white", anchor="w", tags="pm_title")
    c.tag_bind("pm_title", "<Button-1>", _ds)
    c.tag_bind("pm_title", "<B1-Motion>", _dm)

    # Close
    ifont = icon_font()
    cx0 = width - CLOSE_M - CLOSE_SIZE
    cy0 = CLOSE_M
    rrect(c, cx0, cy0, CLOSE_SIZE, CLOSE_SIZE, BTN_R,
          fill=C_CLOSE, outline="", tags=("pm_close", "pm_close_bg"))
    ccx, ccy = cx0 + CLOSE_SIZE // 2, cy0 + CLOSE_SIZE // 2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, IS), fill="#FFF", tags=("pm_close",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(FF, FS, "bold"), fill="#FFF", tags=("pm_close",))

    def _ce(e): i = c.find_withtag("pm_close_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE_H)
    def _cl(e): i = c.find_withtag("pm_close_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE)
    c.tag_bind("pm_close", "<Enter>", _ce)
    c.tag_bind("pm_close", "<Leave>", _cl)
    c.tag_bind("pm_close", "<Button-1>", lambda e: top.destroy())

    # List area
    header_h = 60
    list_y = header_h
    list_h = height - list_y - 80
    list_w = width - padding * 2

    list_frame_container = tk.Frame(top, bg=C_PM_BG)
    list_frame_container.place(x=padding, y=list_y, width=list_w, height=list_h)

    list_canvas = tk.Canvas(list_frame_container, bg=C_PM_BG, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_frame_container, orient="vertical", command=list_canvas.yview)
    scrollable_frame = tk.Frame(list_canvas, bg=C_PM_BG)

    scrollable_frame.bind("<Configure>",
                          lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))

    canvas_window = list_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

    def _on_canvas_configure(event):
        list_canvas.itemconfig(canvas_window, width=event.width)
    list_canvas.bind("<Configure>", _on_canvas_configure)
    list_canvas.configure(yscrollcommand=scrollbar.set)

    list_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def refresh_list():
        try:
            if not scrollable_frame.winfo_exists(): return
        except Exception: return
        for widget in scrollable_frame.winfo_children():
            widget.destroy()
        profiles = list_profiles()
        active = get_active_profile_name()
        for name in profiles:
            _draw_profile_row(scrollable_frame, name, name == active, refresh_list, on_switch, top)

    # Bottom buttons: 新建 | 复制 | 导入
    btn_h = 40
    btn_y = height - padding - btn_h
    btn_gap = 10
    btn_w = (list_w - btn_gap * 2) // 3

    def _draw_pm_btn(x, y, w, h, icon_ch, label, tag, cb):
        rrect(c, x, y, w, h, BTN_R, fill=C_GRAY, outline="", tags=(tag, tag + "_bg"))
        cy2 = y + h // 2
        if ifont:
            text_w = len(label) * 14
            gap = 12
            total_w = 20 + gap + text_w
            start_x = x + (w - total_w) / 2
            c.create_text(start_x + 10, cy2, text=icon_ch, font=(ifont, IS),
                          fill="#E0E0E0", anchor="center", tags=(tag,))
            c.create_text(start_x + 20 + gap, cy2, text=label, font=(FF, FS),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
        else:
            c.create_text(x + w // 2, cy2, text=f"{icon_ch} {label}", font=(FF, 10, "bold"),
                          fill="#E0E0E0", tags=(tag,))
        def _en(e): c.itemconfigure(tag + "_bg", fill=C_GRAY_H)
        def _lv(e): c.itemconfigure(tag + "_bg", fill=C_GRAY)
        c.tag_bind(tag, "<Enter>", _en)
        c.tag_bind(tag, "<Leave>", _lv)
        c.tag_bind(tag, "<Button-1>", lambda e: cb())

    def _new_profile():
        _show_new_profile_dialog(top, refresh_list, on_switch)

    def _copy_profile():
        _show_copy_profile_dialog(top, refresh_list, on_switch)

    def _import_profile():
        path = filedialog.askopenfilename(
            title="导入方案",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            parent=top,
        )
        if not path:
            return
        new_name = import_profile(path)
        if new_name:
            on_switch(new_name)
            refresh_list()
        else:
            messagebox.showerror("错误", "导入失败，JSON 格式无效", parent=top)

    bx = padding
    _draw_pm_btn(bx, btn_y, btn_w, btn_h, "\uE710", "\u65b0\u5efa", "pm_btn_new", _new_profile)
    bx += btn_w + btn_gap
    _draw_pm_btn(bx, btn_y, btn_w, btn_h, "\uE8C8", "\u590d\u5236", "pm_btn_copy", _copy_profile)
    bx += btn_w + btn_gap
    _draw_pm_btn(bx, btn_y, btn_w, btn_h, "\uE896", "\u5bfc\u5165", "pm_btn_imp", _import_profile)

    refresh_list()

    # Mouse wheel
    def _on_mousewheel(event):
        if list_canvas.yview() != (0.0, 1.0):
            list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_mousewheel(event):
        list_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_mousewheel(event):
        list_canvas.unbind_all("<MouseWheel>")

    list_frame_container.bind('<Enter>', _bind_mousewheel)
    list_frame_container.bind('<Leave>', _unbind_mousewheel)


def _draw_profile_row(parent, name, is_active, refresh_cb, switch_cb, top_win):
    """绘制方案列表中的一行。包含 编辑、删除、导出 三个按钮。"""
    h = 40
    row_frame = tk.Frame(parent, bg=C_PM_BG, height=h + 10)
    row_frame.pack(fill="x", pady=0)

    c = tk.Canvas(row_frame, bg=C_PM_BG, height=h, highlightthickness=0)
    c.pack(fill="x", padx=0, pady=5)

    bg_color = C_PM_SEL if is_active else C_PM_ITEM
    fg_color = "black" if is_active else "white"

    def _draw_bg(e):
        w = c.winfo_width()
        c.delete("bg")
        rrect(c, 0, 0, w, h, 10, fill=bg_color, outline="", tags="bg")
        c.tag_lower("bg")

    c.bind("<Configure>", _draw_bg)

    def _switch(e=None):
        if not is_active:
            switch_cb(name)
            refresh_cb()

    c.bind("<Button-1>", _switch)

    ifont = icon_font()
    cy = h // 2
    left_x = 15

    if is_active:
        if ifont:
            c.create_text(left_x, cy, text="\uE73E", font=(ifont, 12), fill=fg_color, anchor="w", tags="content")
        else:
            c.create_text(left_x, cy, text="\u2713", font=("Arial", 10, "bold"), fill=fg_color, anchor="w", tags="content")
        left_x += 25

    c.create_text(left_x, cy, text=name, font=(FF, 10), fill=fg_color, anchor="w", tags="content")

    # --- 3 action buttons: Edit, Delete, Export ---

    # Edit (rename)
    def _rename():
        _show_rename_dialog(parent, name, refresh_cb)

    btn_edit = tk.Label(row_frame, text="\uE70F" if ifont else "\u270e",
                        bg=bg_color, fg=fg_color, font=(ifont, 12) if ifont else ("Arial", 11),
                        cursor="hand2")
    c.create_window(0, cy, window=btn_edit, anchor="e", tags="btn_edit")
    btn_edit.bind("<Button-1>", lambda e: _rename())

    # Delete
    def _delete():
        def do_del():
            if delete_profile(name):
                refresh_cb()
            else:
                messagebox.showerror("\u9519\u8bef", "\u5220\u9664\u5931\u8d25\uff0c\u53ef\u80fd\u662f\u5f53\u524d\u6d3b\u8dc3\u65b9\u6848")

        create_styled_yesno_dialog(parent, "\u786e\u8ba4", f"\u786e\u5b9a\u5220\u9664\u65b9\u6848 '{name}' \u5417?", do_del)

    btn_del = tk.Label(row_frame, text="\uE74D" if ifont else "✕",
                       bg=bg_color, fg="#888" if is_active else fg_color,
                       font=(ifont, 12) if ifont else ("Arial", 10),
                       cursor="hand2")
    if is_active:
        btn_del.configure(state="disabled", cursor="arrow")
    else:
        btn_del.bind("<Button-1>", lambda e: _delete())
    c.create_window(0, cy, window=btn_del, anchor="e", tags="btn_del")

    # Export
    def _export():
        path = filedialog.asksaveasfilename(
            title=f"导出方案 '{name}'",
            initialfile=f"{name}.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            parent=top_win,
        )
        if not path:
            return
        if export_profile(name, path):
            messagebox.showinfo("成功", f"方案 '{name}' 已导出", parent=top_win)
        else:
            messagebox.showerror("错误", "导出失败", parent=top_win)

    btn_exp = tk.Label(row_frame, text="\uE898" if ifont else "↑",
                       bg=bg_color, fg=fg_color,
                       font=(ifont, 12) if ifont else ("Arial", 10),
                       cursor="hand2")
    btn_exp.bind("<Button-1>", lambda e: _export())
    c.create_window(0, cy, window=btn_exp, anchor="e", tags="btn_exp")

    def _update_pos(e):
        w = c.winfo_width()
        c.coords("btn_exp", w - 10, cy)
        c.coords("btn_del", w - 40, cy)
        c.coords("btn_edit", w - 70, cy)
        _draw_bg(e)

    c.bind("<Configure>", _update_pos)
    c.tag_bind("content", "<Button-1>", _switch)


def _show_new_profile_dialog(parent, refresh_cb, switch_cb):
    def on_ok(name):
        if not name: return
        if create_profile(name, from_template=False):
            switch_cb(name)
            refresh_cb()
            return True
        else:
            messagebox.showerror("\u9519\u8bef", "\u65b9\u6848\u5df2\u5b58\u5728", parent=parent)
            return False

    top, entry = create_styled_dialog(parent, "\u65b0\u5efa\u65b9\u6848", 360, 220,
                                      on_confirm=lambda val: top.destroy() if on_ok(val) else None,
                                      label_text="\u65b0\u65b9\u6848\u540d\u79f0:")


def _show_copy_profile_dialog(parent, refresh_cb, switch_cb):
    base_name = get_active_profile_name()

    def on_ok(new_name):
        if not new_name: return
        if create_profile(new_name, from_template=True):
            from core.config_manager import save_profile, load_profile
            src_cfg = load_profile(base_name)
            save_profile(new_name, src_cfg)
            switch_cb(new_name)
            refresh_cb()
            return True
        else:
            messagebox.showerror("\u9519\u8bef", "\u65b9\u6848\u5df2\u5b58\u5728", parent=parent)
            return False

    top, entry = create_styled_dialog(parent, "\u590d\u5236\u65b9\u6848", 360, 220,
                                      on_confirm=lambda val: top.destroy() if on_ok(val) else None,
                                      initial_value=f"{base_name}_copy",
                                      label_text=f"\u590d\u5236 '{base_name}' \u4e3a:")


def _show_rename_dialog(parent, old_name, refresh_cb):
    def on_ok(new_name):
        if not new_name or new_name == old_name: return True
        if rename_profile(old_name, new_name):
            refresh_cb()
            return True
        else:
            messagebox.showerror("\u9519\u8bef", "\u91cd\u547d\u540d\u5931\u8d25\uff0c\u540d\u79f0\u53ef\u80fd\u5df2\u5b58\u5728", parent=parent)
            return False

    top, entry = create_styled_dialog(parent, "\u91cd\u547d\u540d", 360, 220,
                                      on_confirm=lambda val: top.destroy() if on_ok(val) else None,
                                      initial_value=old_name,
                                      label_text=f"\u5c06 '{old_name}' \u91cd\u547d\u540d\u4e3a:")
