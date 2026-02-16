"""
FKB - edit_panel.py
Toolbar: Canvas-drawn (rounded buttons, custom slider, drag handle).
Editor popup: standard Toplevel.
Profile Manager: Canvas-drawn profile switcher.
"""

import tkinter as tk
import tkinter.font as tkfont
import tkinter.messagebox as messagebox
from core.constants import (
    COLOR_BTN_BG, COLOR_BTN_BORDER, COLOR_PANEL,
    COLOR_TOOLBAR_TRANSPARENT,
    TOOLBAR_WIDTH, TOOLBAR_HEIGHT, TOOLBAR_RADIUS,
    TOOLBAR_PADDING, TOOLBAR_BOTTOM_MARGIN,
    DEFAULT_PROFILE_NAME
)
from core.config_manager import (
    list_profiles, get_active_profile_name,
    create_profile, delete_profile, rename_profile
)
from ui.virtual_keyboard import open_virtual_keyboard

# --- Fonts ---
_FF = "Microsoft YaHei UI"
_FI = "Segoe Fluent Icons"
_FI2 = "Segoe MDL2 Assets"

EDIT_FIELDS = [
    ('name', '\u6309\u94ae\u540d\u79f0', False),
    ('lclick', '\u5de6\u952e\u6a21\u62df', True),
    ('mclick', '\u4e2d\u952e\u6a21\u62df', True),
    ('hover', '\u60ac\u6d6e\u6a21\u62df', True),
    ('rclick', '\u53f3\u952e\u6a21\u62df', True),
    ('wheelup', '\u6eda\u8f6e\u4e0a\u6eda\u6a21\u62df', True),
    ('wheeldown', '\u6eda\u8f6e\u4e0b\u6eda\u6a21\u62df', True),
]

# --- Size constants (all px) ---
_TOP = 10;  _BTN_H = 40;  _BTN_R = 10;  _GAP = 8
_FS = -18;  _IS = -20  # font / icon size (px, negative = px in tkinter)
_CLOSE = 40;  _CLOSE_M = 10
_DRAG_W = 28
_SL_LABEL_GAP = 16;  _SL_H = 8;  _SL_TR = 12  # slider track h / thumb radius

# --- Colours ---
_C_CYBER     = "#0C4A6E"   # config selector normal (cyberpunk deep-sea)
_C_CYBER_H   = "#0284C7"   # config selector hover
_C_GRAY      = "#3A3A3A"
_C_GRAY_H    = "#505050"
_C_AMBER     = "#F59E0B"   # amber
_C_AMBER_D   = "#D97706"   # amber dark (run normal)
_C_CLOSE     = "#6E1E1E"
_C_CLOSE_H   = "#8B2020"

# Profile Manager Colors
_C_PM_BG     = "#2D2D2D"   # Profile Manager Background (Matches COLOR_PANEL)
_C_PM_ITEM   = "#3A3A3A"   # Item Background
_C_PM_SEL    = "#F59E0B"   # Selected Item (Amber)
_C_PM_HOVER  = "#474747"   # Hover Item

_FALLBACK = {
    "add": "\uff0b", "run": "\u25b6", "export": "\u2191",
    "import": "\u2193", "quit": "\u2715", "config": "\u25be",
}


def _icon_font():
    try:
        ff = tkfont.families()
        if _FI in ff: return _FI
        if _FI2 in ff: return _FI2
    except Exception:
        pass
    return None


def _rrect(c, x, y, w, h, r, **kw):
    pts = [x+r,y, x+w-r,y, x+w,y, x+w,y+r, x+w,y+h-r, x+w,y+h,
           x+w-r,y+h, x+r,y+h, x,y+h, x,y+h-r, x,y+r, x,y]
    return c.create_polygon(pts, smooth=True, **kw)


# -------------------------------------------------------------
#  Common Styled Dialog Helper
# -------------------------------------------------------------

def _create_styled_dialog(parent, title, width, height, on_confirm=None, initial_value=None, label_text=None):
    """
    Creates a modal dialog with consistent styling (rounded, dark theme).
    Returns (top, entry_widget)
    """
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
    
    # --- MODAL LOGIC START ---
    top.grab_set()
    top.focus_set()
    # --- MODAL LOGIC END ---

    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # Bg
    _rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=_C_PM_BG, outline="#444", width=1, tags="bg")

    # Drag
    drag = {"sx":0,"sy":0,"wx":0,"wy":0}
    def _ds(e): drag["sx"],drag["sy"]=e.x_root,e.y_root; drag["wx"],drag["wy"]=top.winfo_x(),top.winfo_y()
    def _dm(e):
        nx=drag["wx"]+(e.x_root-drag["sx"]); ny=drag["wy"]+(e.y_root-drag["sy"])
        top.geometry(f"{width}x{height}+{max(0,min(nx,sw-width))}+{max(0,min(ny,sh-height))}")
    c.tag_bind("bg", "<Button-1>", _ds)
    c.tag_bind("bg", "<B1-Motion>", _dm)

    # Title
    c.create_text(20, 25, text=title, font=(_FF, 11, "bold"), fill="white", anchor="w", tags="title")
    c.tag_bind("title", "<Button-1>", _ds)
    c.tag_bind("title", "<B1-Motion>", _dm)

    # Close Button
    cx0 = width - _CLOSE_M - _CLOSE
    cy0 = _CLOSE_M
    _rrect(c, cx0, cy0, _CLOSE, _CLOSE, _BTN_R, fill=_C_CLOSE, outline="", tags=("close","close_bg"))
    ifont = _icon_font()
    ccx, ccy = cx0+_CLOSE//2, cy0+_CLOSE//2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, _IS), fill="#FFF", tags=("close",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(_FF, _FS, "bold"), fill="#FFF", tags=("close",))
    
    def _ce(e): i=c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE_H)
    def _cl(e): i=c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE)
    c.tag_bind("close","<Enter>",_ce); c.tag_bind("close","<Leave>",_cl)
    c.tag_bind("close","<Button-1>", lambda e: top.destroy())

    # Content Area
    content_y = 60 # Increased top spacing
    
    if label_text:
        lbl = tk.Label(top, text=label_text, bg=_C_PM_BG, fg="#CCC", font=(_FF, 10))
        lbl.place(x=20, y=content_y)
        content_y += 35 # Increase gap after label

    entry = tk.Entry(top, font=(_FF, 10), bg=_C_GRAY, fg="white", 
                     insertbackground="white", relief="flat", bd=5)
    entry.place(x=20, y=content_y, width=width-40)
    if initial_value:
        entry.insert(0, initial_value)
        entry.select_range(0, tk.END)
    entry.focus_set()

    # Confirm Button
    btn_y = height - 60 # Increased bottom spacing
    btn_w = 100 # Increased width
    btn_h = 36  # Increased height
    bx = (width - btn_w) // 2
    
    # Draw button on canvas
    _rrect(c, bx, btn_y, btn_w, btn_h, 6, fill=_C_AMBER, outline="", tags=("btn", "btn_bg"))
    c.create_text(bx+btn_w//2, btn_y+btn_h//2, text="\u786e\u5b9a", 
                  font=(_FF, _FS), fill="black", tags=("btn",))
    
    def _be(e): c.itemconfigure("btn_bg", fill=_C_AMBER_D)
    def _bl(e): c.itemconfigure("btn_bg", fill=_C_AMBER)
    c.tag_bind("btn", "<Enter>", _be)
    c.tag_bind("btn", "<Leave>", _bl)
    
    def _on_ok(event=None):
        if on_confirm:
            val = entry.get().strip()
            on_confirm(val)
            
    c.tag_bind("btn", "<Button-1>", _on_ok)
    entry.bind("<Return>", _on_ok)

    return top, entry


def _create_styled_yesno_dialog(parent, title, message_text, on_yes):
    """
    Creates a styled Yes/No confirmation dialog.
    """
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
    
    # --- MODAL LOGIC START ---
    top.grab_set()
    top.focus_set()
    # --- MODAL LOGIC END ---

    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # Bg
    _rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=_C_PM_BG, outline="#444", width=1, tags="bg")

    # Drag
    drag = {"sx":0,"sy":0,"wx":0,"wy":0}
    def _ds(e): drag["sx"],drag["sy"]=e.x_root,e.y_root; drag["wx"],drag["wy"]=top.winfo_x(),top.winfo_y()
    def _dm(e):
        nx=drag["wx"]+(e.x_root-drag["sx"]); ny=drag["wy"]+(e.y_root-drag["sy"])
        top.geometry(f"{width}x{height}+{max(0,min(nx,sw-width))}+{max(0,min(ny,sh-height))}")
    c.tag_bind("bg", "<Button-1>", _ds)
    c.tag_bind("bg", "<B1-Motion>", _dm)

    # Title
    c.create_text(20, 25, text=title, font=(_FF, 11, "bold"), fill="white", anchor="w", tags="title")
    c.tag_bind("title", "<Button-1>", _ds)
    c.tag_bind("title", "<B1-Motion>", _dm)

    # Close Button
    cx0 = width - _CLOSE_M - _CLOSE
    cy0 = _CLOSE_M
    _rrect(c, cx0, cy0, _CLOSE, _CLOSE, _BTN_R, fill=_C_CLOSE, outline="", tags=("close","close_bg"))
    ifont = _icon_font()
    ccx, ccy = cx0+_CLOSE//2, cy0+_CLOSE//2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, _IS), fill="#FFF", tags=("close",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(_FF, _FS, "bold"), fill="#FFF", tags=("close",))
    
    def _ce(e): i=c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE_H)
    def _cl(e): i=c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE)
    c.tag_bind("close","<Enter>",_ce); c.tag_bind("close","<Leave>",_cl)
    c.tag_bind("close","<Button-1>", lambda e: top.destroy())

    # Message
    lbl = tk.Label(top, text=message_text, bg=_C_PM_BG, fg="white", font=(_FF, 10), wraplength=width-40)
    lbl.place(x=20, y=70, width=width-40)

    # Buttons
    btn_w, btn_h = 90, 36
    total_btn_w = btn_w * 2 + 20
    start_x = (width - total_btn_w) // 2
    btn_y = height - 50

    # Yes Button
    _rrect(c, start_x, btn_y, btn_w, btn_h, 6, fill=_C_AMBER, outline="", tags=("yes", "yes_bg"))
    c.create_text(start_x+btn_w//2, btn_y+btn_h//2, text="\u786e\u5b9a", 
                  font=(_FF, _FS), fill="black", tags=("yes",))
    
    def _ye(e): c.itemconfigure("yes_bg", fill=_C_AMBER_D)
    def _yl(e): c.itemconfigure("yes_bg", fill=_C_AMBER)
    c.tag_bind("yes", "<Enter>", _ye); c.tag_bind("yes", "<Leave>", _yl)
    c.tag_bind("yes", "<Button-1>", lambda e: [on_yes(), top.destroy()])

    # No Button
    no_x = start_x + btn_w + 20
    _rrect(c, no_x, btn_y, btn_w, btn_h, 6, fill=_C_GRAY, outline="", tags=("no", "no_bg"))
    c.create_text(no_x+btn_w//2, btn_y+btn_h//2, text="\u53d6\u6d88", 
                  font=(_FF, _FS), fill="#EEE", tags=("no",))
    
    def _ne(e): c.itemconfigure("no_bg", fill=_C_GRAY_H)
    def _nl(e): c.itemconfigure("no_bg", fill=_C_GRAY)
    c.tag_bind("no", "<Enter>", _ne); c.tag_bind("no", "<Leave>", _nl)
    c.tag_bind("no", "<Button-1>", lambda e: top.destroy())

    return top


# =============================================================
#  Profile Manager Popup
# =============================================================

def open_profile_manager(parent, on_switch):
    """
    打开方案管理弹窗
    """
    width, height = 360, 420
    # Center relative to screen
    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2

    top = tk.Toplevel(parent)
    top.overrideredirect(True) # Remove system title bar
    top.geometry(f"{width}x{height}+{x}+{y}")
    top.attributes("-topmost", True)
    top.attributes("-alpha", 1.0)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)
    
    # --- MODAL LOGIC START ---
    # Make it modal to prevent underlying clicks
    top.grab_set()
    top.focus_set()
    # --- MODAL LOGIC END ---

    # Main canvas for rounded background
    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # Draw rounded background
    _rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=_C_PM_BG, outline="#444", width=1, tags="pm_bg")

    # Drag functionality
    drag = {"sx":0,"sy":0,"wx":0,"wy":0}
    def _ds(e): drag["sx"],drag["sy"]=e.x_root,e.y_root; drag["wx"],drag["wy"]=top.winfo_x(),top.winfo_y()
    def _dm(e):
        nx=drag["wx"]+(e.x_root-drag["sx"]); ny=drag["wy"]+(e.y_root-drag["sy"])
        top.geometry(f"{width}x{height}+{max(0,min(nx,sw-width))}+{max(0,min(ny,sh-height))}")
    
    # Bind drag to background
    c.tag_bind("pm_bg", "<Button-1>", _ds)
    c.tag_bind("pm_bg", "<B1-Motion>", _dm)

    # --- Header (Title + Close) ---
    header_h = 60 # Increased header height to accommodate padding
    padding = 20  # Global padding
    
    # Title
    c.create_text(padding, 30, text="\u65b9\u6848\u7ba1\u7406", 
                  font=(_FF, 12, "bold"), fill="white", anchor="w", tags="pm_title")
    c.tag_bind("pm_title", "<Button-1>", _ds)
    c.tag_bind("pm_title", "<B1-Motion>", _dm)

    # Close Button (Top Right)
    # Reusing toolbar close button style: 40x40, red, rounded
    cx0 = width - _CLOSE_M - _CLOSE  # 10px margin from right edge
    cy0 = _CLOSE_M                   # 10px margin from top edge
    
    _rrect(c, cx0, cy0, _CLOSE, _CLOSE, _BTN_R,
           fill=_C_CLOSE, outline="", tags=("pm_close","pm_close_bg"))
    
    ifont = _icon_font()
    ccx, ccy = cx0+_CLOSE//2, cy0+_CLOSE//2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, _IS), fill="#FFF", tags=("pm_close",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(_FF, _FS, "bold"), fill="#FFF", tags=("pm_close",))

    def _ce(e): i=c.find_withtag("pm_close_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE_H)
    def _cl(e): i=c.find_withtag("pm_close_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE)
    c.tag_bind("pm_close","<Enter>",_ce); c.tag_bind("pm_close","<Leave>",_cl)
    c.tag_bind("pm_close","<Button-1>", lambda e: top.destroy())

    # --- List Area (Frame on top of Canvas) ---
    # Top padding: header_h (60)
    # Side padding: 20
    # Bottom padding: 20 (gap) + 40 (btn height) + 20 (bottom margin) = 80
    list_y = header_h
    list_h = height - list_y - 80
    list_w = width - (padding * 2)
    
    list_frame_container = tk.Frame(top, bg=_C_PM_BG)
    list_frame_container.place(x=padding, y=list_y, width=list_w, height=list_h)

    list_canvas = tk.Canvas(list_frame_container, bg=_C_PM_BG, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_frame_container, orient="vertical", command=list_canvas.yview)
    scrollable_frame = tk.Frame(list_canvas, bg=_C_PM_BG)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all"))
    )

    # Force scrollable_frame width to match list_w
    canvas_window = list_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    
    def _on_canvas_configure(event):
        list_canvas.itemconfig(canvas_window, width=event.width)
    
    list_canvas.bind("<Configure>", _on_canvas_configure)
    list_canvas.configure(yscrollcommand=scrollbar.set)

    list_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # --- Refresh Logic ---
    def refresh_list():
        try:
            if not scrollable_frame.winfo_exists(): return
        except Exception: return

        for widget in scrollable_frame.winfo_children():
            widget.destroy()

        profiles = list_profiles()
        active = get_active_profile_name()

        for name in profiles:
            _draw_profile_row(scrollable_frame, name, name == active, refresh_list, on_switch)

    # --- Bottom Buttons (Canvas Drawn) ---
    btn_h = 40
    btn_y = height - padding - btn_h
    
    # Calculate button width (half width with gap)
    btn_w = (list_w - 10) // 2
    
    # New Profile Button
    bx_new = padding
    by_new = btn_y
    
    # Copy Profile Button
    bx_copy = padding + btn_w + 10
    by_copy = btn_y

    def _draw_pm_btn(x, y, w, h, icon_ch, label, tag, cb):
        _rrect(c, x, y, w, h, _BTN_R, fill=_C_GRAY, outline="", tags=(tag, tag+"_bg"))
        
        cy2 = y + h // 2
        # Icon + Text centered calculation
        if ifont:
            text_w = len(label) * 14
            gap = 12 
            total_w = 20 + gap + text_w 
            
            # Center X
            start_x = x + (w - total_w) / 2
            
            # Draw icon (center anchored)
            c.create_text(start_x + 10, cy2, text=icon_ch, font=(ifont, _IS),
                          fill="#E0E0E0", anchor="center", tags=(tag,))
            
            # Draw text (left anchored relative to icon end)
            c.create_text(start_x + 20 + gap, cy2, text=label, font=(_FF, _FS),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
        else:
            c.create_text(x + w//2, cy2, text=f"{icon_ch} {label}", font=(_FF, 10, "bold"),
                          fill="#E0E0E0", tags=(tag,))
        
        def _en(e): c.itemconfigure(tag+"_bg", fill=_C_GRAY_H)
        def _lv(e): c.itemconfigure(tag+"_bg", fill=_C_GRAY)
        
        c.tag_bind(tag, "<Enter>", _en)
        c.tag_bind(tag, "<Leave>", _lv)
        c.tag_bind(tag, "<Button-1>", lambda e: cb())

    # Handlers
    def _new_profile():
        _show_new_profile_dialog(top, refresh_list, on_switch)
    
    def _copy_profile():
        _show_copy_profile_dialog(top, refresh_list, on_switch)

    # Draw Buttons
    _draw_pm_btn(bx_new, by_new, btn_w, btn_h, "\uE710", "\u65b0\u5efa", "pm_btn_new", _new_profile)
    _draw_pm_btn(bx_copy, by_copy, btn_w, btn_h, "\uE8C8", "\u590d\u5236", "pm_btn_copy", _copy_profile)

    refresh_list()
    
    # Mouse wheel
    def _on_mousewheel(event):
        # Only scroll if content height > visible height
        if list_canvas.yview() != (0.0, 1.0):
            list_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _bind_mousewheel(event):
        list_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_mousewheel(event):
        list_canvas.unbind_all("<MouseWheel>")

    list_frame_container.bind('<Enter>', _bind_mousewheel)
    list_frame_container.bind('<Leave>', _unbind_mousewheel)


def _draw_profile_row(parent, name, is_active, refresh_cb, switch_cb):
    # Using Canvas for rounded row background
    h = 40 # Row height
    
    # Let's use a Frame that holds a Canvas.
    row_frame = tk.Frame(parent, bg=_C_PM_BG, height=h+10) # +10 for gap
    row_frame.pack(fill="x", pady=0) # We handle gap inside
    
    c = tk.Canvas(row_frame, bg=_C_PM_BG, height=h, highlightthickness=0)
    c.pack(fill="x", padx=0, pady=5) # 5px top/bottom padding = 10px gap between items
    
    bg_color = _C_PM_SEL if is_active else _C_PM_ITEM
    fg_color = "black" if is_active else "white"
    
    # We need to draw the rounded rect when size is known
    def _draw_bg(e):
        w = c.winfo_width()
        c.delete("bg")
        # Draw rounded rect
        _rrect(c, 0, 0, w, h, 10, fill=bg_color, outline="", tags="bg")
        c.tag_lower("bg")
        
    c.bind("<Configure>", _draw_bg)
    
    # Click handler
    def _switch(e=None):
        if not is_active:
            switch_cb(name)
            refresh_cb()
    
    c.bind("<Button-1>", _switch)
    
    # Checkmark & Name
    ifont = _icon_font()
    
    cy = h // 2
    left_x = 15
    
    if is_active:
        if ifont:
            c.create_text(left_x, cy, text="\uE73E", font=(ifont, 12), fill=fg_color, anchor="w", tags="content")
        else:
            c.create_text(left_x, cy, text="\u2713", font=("Arial", 10, "bold"), fill=fg_color, anchor="w", tags="content")
        left_x += 25
        
    c.create_text(left_x, cy, text=name, font=(_FF, 10), fill=fg_color, anchor="w", tags="content")
    
    # Buttons (Right aligned)
    # Edit
    def _rename():
        _show_rename_dialog(parent, name, refresh_cb)
        
    btn_edit = tk.Label(row_frame, text="\uE70F" if ifont else "\u270e", 
                        bg=bg_color, fg=fg_color, font=(ifont, 12) if ifont else ("Arial", 11))
    c.create_window(300, cy, window=btn_edit, anchor="e", tags="btn_edit") 
    
    btn_edit.bind("<Button-1>", lambda e: _rename())
    
    # Delete
    def _delete():
        def do_del():
            if delete_profile(name):
                refresh_cb()
            else:
                messagebox.showerror("\u9519\u8bef", "\u5220\u9664\u5931\u8d25\uff0c\u53ef\u80fd\u662f\u5f53\u524d\u6d3b\u8dc3\u65b9\u6848")
        
        _create_styled_yesno_dialog(parent, "\u786e\u8ba4", f"\u786e\u5b9a\u5220\u9664\u65b9\u6848 '{name}' \u5417?", do_del)
                
    btn_del = tk.Label(row_frame, text="\uE74D" if ifont else "✕", 
                       bg=bg_color, fg="#888" if is_active else fg_color, 
                       font=(ifont, 12) if ifont else ("Arial", 10))
    if is_active:
        btn_del.configure(state="disabled")
    else:
        btn_del.bind("<Button-1>", lambda e: _delete())
        
    c.create_window(330, cy, window=btn_del, anchor="e", tags="btn_del")
    
    # Update button positions on resize
    def _update_pos(e):
        w = c.winfo_width()
        c.coords("btn_del", w - 10, cy)
        c.coords("btn_edit", w - 40, cy)
        _draw_bg(e) # Re-draw bg as well
        
    c.bind("<Configure>", _update_pos)
    
    # Propagate click to text
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

    top, entry = _create_styled_dialog(parent, "\u65b0\u5efa\u65b9\u6848", 360, 220, 
                                       on_confirm=lambda val: top.destroy() if on_ok(val) else None,
                                       label_text="\u65b0\u65b9\u6848\u540d\u79f0:")


def _show_copy_profile_dialog(parent, refresh_cb, switch_cb):
    base_name = get_active_profile_name()
    
    def on_ok(new_name):
        if not new_name: return
        if create_profile(new_name, from_template=True): 
            # 2. Overwrite with current profile data
            from core.config_manager import save_profile, load_profile
            src_cfg = load_profile(base_name)
            save_profile(new_name, src_cfg)
            switch_cb(new_name)
            refresh_cb()
            return True
        else:
            messagebox.showerror("\u9519\u8bef", "\u65b9\u6848\u5df2\u5b58\u5728", parent=parent)
            return False

    top, entry = _create_styled_dialog(parent, "\u590d\u5236\u65b9\u6848", 360, 220,
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

    top, entry = _create_styled_dialog(parent, "\u91cd\u547d\u540d", 360, 220,
                                       on_confirm=lambda val: top.destroy() if on_ok(val) else None,
                                       initial_value=old_name,
                                       label_text=f"\u5c06 '{old_name}' \u91cd\u547d\u540d\u4e3a:")


# =============================================================
#  Toolbar window
# =============================================================

def create_toolbar_window(parent, screen_w, screen_h, *,
                          on_add, on_run, on_export, on_import,
                          on_quit, transparency, on_alpha_change,
                          on_switch_profile):
    tw, th = TOOLBAR_WIDTH, TOOLBAR_HEIGHT
    tx = (screen_w - tw) // 2
    ty = screen_h - th - TOOLBAR_BOTTOM_MARGIN
    r = TOOLBAR_RADIUS

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.geometry(f"{tw}x{th}+{tx}+{ty}")
    top.attributes("-topmost", True)
    top.attributes("-alpha", 1.0)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    def _keep():
        try:
            if top.winfo_exists(): top.lift(); top.after(300, _keep)
        except: pass
    top.lift(); top.after(100, _keep)

    c = tk.Canvas(top, width=tw, height=th,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)

    # bg
    _rrect(c, 0, 0, tw, th, r, fill=COLOR_PANEL, outline="#444", width=1, tags="toolbar_bg")

    ifont = _icon_font()

    # --- drag handle ---
    dcx, dcy = _DRAG_W//2, th//2
    for dy in [-12,-4,4,12]:
        for dx in [-4,4]:
            c.create_oval(dcx+dx-2, dcy+dy-2, dcx+dx+2, dcy+dy+2,
                          fill="#666", outline="", tags="drag_zone")
    c.create_line(_DRAG_W+2, 10, _DRAG_W+2, th-10, fill="#444", width=1)

    drag = {"sx":0,"sy":0,"wx":0,"wy":0}
    def _ds(e): drag["sx"],drag["sy"]=e.x_root,e.y_root; drag["wx"],drag["wy"]=top.winfo_x(),top.winfo_y()
    def _dm(e):
        nx=drag["wx"]+(e.x_root-drag["sx"]); ny=drag["wy"]+(e.y_root-drag["sy"])
        top.geometry(f"{tw}x{th}+{max(0,min(nx,screen_w-tw))}+{max(0,min(ny,screen_h-th))}")
    for t in ("drag_zone","toolbar_bg"):
        c.tag_bind(t,"<Button-1>",_ds); c.tag_bind(t,"<B1-Motion>",_dm)

    # --- CLOSE (top-right 40x40) ---
    cx0 = tw - _CLOSE_M - _CLOSE
    _rrect(c, cx0, _CLOSE_M, _CLOSE, _CLOSE, _BTN_R,
           fill=_C_CLOSE, outline="", tags=("tq","tq_bg"))
    ccx, ccy = cx0+_CLOSE//2, _CLOSE_M+_CLOSE//2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, _IS), fill="#FFF", tags=("tq",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(_FF, _FS, "bold"), fill="#FFF", tags=("tq",))
    def _ce(e): i=c.find_withtag("tq_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE_H)
    def _cl(e): i=c.find_withtag("tq_bg"); i and c.itemconfigure(i[0], fill=_C_CLOSE)
    c.tag_bind("tq","<Enter>",_ce); c.tag_bind("tq","<Leave>",_cl)
    c.tag_bind("tq","<Button-1>", lambda e: on_quit())

    # ========== FIRST ROW ==========
    bx = _DRAG_W + 16
    by = _TOP

    # helper: draw icon+text button (w=90px)
    _TBTN_W = 90
    def _txt_btn(x, y, icon_ch, fb, label, tag, bg, bg_h, cb):
        _rrect(c, x, y, _TBTN_W, _BTN_H, _BTN_R, fill=bg, outline="", tags=(tag, tag+"_bg"))
        cy2 = y + _BTN_H // 2
        if ifont:
            c.create_text(x+12, cy2, text=icon_ch, font=(ifont, _IS),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
            c.create_text(x+38, cy2, text=label, font=(_FF, _FS),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
        else:
            c.create_text(x+12, cy2, text=f"{fb} {label}", font=(_FF, _FS,"bold"),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
        def _en(e): i=c.find_withtag(tag+"_bg"); i and c.itemconfigure(i[0], fill=bg_h)
        def _lv(e): i=c.find_withtag(tag+"_bg"); i and c.itemconfigure(i[0], fill=bg)
        c.tag_bind(tag,"<Enter>",_en); c.tag_bind(tag,"<Leave>",_lv)
        c.tag_bind(tag,"<Button-1>", lambda e: cb())

    # --- 1) Config selector (cyberpunk blue, 180px wide) ---
    _CFG_W = 180
    cfg_tag = "tcfg"
    _rrect(c, bx, by, _CFG_W, _BTN_H, _BTN_R,
           fill=_C_CYBER, outline="", tags=(cfg_tag, cfg_tag+"_bg"))

    cfg_cy = by + _BTN_H // 2
    # icon: gamepad \uE7FC or controller \uE7FC
    if ifont:
        c.create_text(bx+14, cfg_cy, text="\uE7FC", font=(ifont, _IS),
                      fill="#E0E0E0", anchor="w", tags=(cfg_tag,))
    
    # Text: Active Profile Name
    active_profile = get_active_profile_name()
    c.create_text(bx+40, cfg_cy, text=active_profile,
                  font=(_FF, _FS), fill="#E0E0E0", anchor="w", tags=(cfg_tag, "cfg_name"))
    
    # dropdown arrow
    c.create_text(bx+_CFG_W-16, cfg_cy, text="\u25be",
                  font=(_FF, -14), fill="#AAA", anchor="e", tags=(cfg_tag,))

    # hover
    def _cfg_en(e): i=c.find_withtag(cfg_tag+"_bg"); i and c.itemconfigure(i[0], fill=_C_CYBER_H)
    def _cfg_lv(e): i=c.find_withtag(cfg_tag+"_bg"); i and c.itemconfigure(i[0], fill=_C_CYBER)
    c.tag_bind(cfg_tag, "<Enter>", _cfg_en)
    c.tag_bind(cfg_tag, "<Leave>", _cfg_lv)

    # Click to open profile manager
    def _on_cfg_click():
        # Update name text when switching
        def _sw_wrapper(name):
            c.itemconfigure("cfg_name", text=name)
            on_switch_profile(name)
        
        open_profile_manager(top, _sw_wrapper)

    c.tag_bind(cfg_tag, "<Button-1>", lambda e: _on_cfg_click())

    bx += _CFG_W + _GAP

    # --- 2) + Add (90px icon+text) ---
    _txt_btn(bx, by, "\uE710", "\uff0b", "\u65b0\u5efa", "tadd", _C_GRAY, _C_GRAY_H, on_add)
    bx += _TBTN_W + _GAP

    # --- 3) Import (90px icon+text) ---
    _txt_btn(bx, by, "\uE896", "\u2193", "\u5bfc\u5165", "timp", _C_GRAY, _C_GRAY_H, on_import)
    bx += _TBTN_W + _GAP

    # --- 4) Export (90px icon+text) ---
    _txt_btn(bx, by, "\uE898", "\u2191", "\u5bfc\u51fa", "texp", _C_GRAY, _C_GRAY_H, on_export)
    bx += _TBTN_W + _GAP

    # --- 5) Vertical separator ---
    sep_x = bx + 4
    c.create_line(sep_x, by+4, sep_x, by+_BTN_H-4, fill="#555", width=1)
    bx += 12

    # --- 6) Run / Launch button (90px, amber) ---
    _RUN_W = 90
    run_tag = "trun"
    _rrect(c, bx, by, _RUN_W, _BTN_H, _BTN_R,
           fill=_C_AMBER_D, outline="", tags=(run_tag, run_tag+"_bg"))
    rcx, rcy = bx + _RUN_W//2, by + _BTN_H//2
    if ifont:
        c.create_text(bx+14, rcy, text="\uE768", font=(ifont, _IS),
                      fill="#FFF", anchor="w", tags=(run_tag,))
        c.create_text(bx+40, rcy, text="\u542f\u52a8",
                      font=(_FF, _FS), fill="#FFF", anchor="w", tags=(run_tag,))
    else:
        c.create_text(bx+12, rcy, text="\u25b6 \u542f\u52a8",
                      font=(_FF, _FS, "bold"), fill="#FFF", anchor="w", tags=(run_tag,))
    def _ren(e): i=c.find_withtag(run_tag+"_bg"); i and c.itemconfigure(i[0], fill=_C_AMBER)
    def _rlv(e): i=c.find_withtag(run_tag+"_bg"); i and c.itemconfigure(i[0], fill=_C_AMBER_D)
    c.tag_bind(run_tag,"<Enter>",_ren); c.tag_bind(run_tag,"<Leave>",_rlv)
    c.tag_bind(run_tag,"<Button-1>", lambda e: on_run())

    # ========== SECOND ROW: Slider ==========
    sl_x = _DRAG_W + 16
    sl_y = _TOP + _BTN_H + 30

    c.create_text(sl_x, sl_y, text="\u900f\u660e\u5ea6",
                  font=(_FF, 9, "bold"), fill="#AAA", anchor="w")

    sl_tx = sl_x + 52 + _SL_LABEL_GAP + 12
    sl_tw = tw - sl_tx - 84
    sl_cy = sl_y

    _rrect(c, sl_tx, sl_cy - _SL_H//2, sl_tw, _SL_H, _SL_H//2,
           fill="#404040", outline="", tags="sl_track_bg")

    ss = {"val": int(transparency * 100)}

    def _v2x(v): return sl_tx + (v-10)/80.0 * sl_tw

    fx = _v2x(ss["val"])
    _rrect(c, sl_tx, sl_cy-_SL_H//2, max(1, fx-sl_tx), _SL_H, _SL_H//2,
           fill=_C_AMBER, outline="", tags="sl_fill")

    TR = _SL_TR
    c.create_oval(fx-TR, sl_cy-TR, fx+TR, sl_cy+TR,
                  fill="#DDD", outline="#999", width=1, tags="sl_thumb")

    def _te(e): c.itemconfigure("sl_thumb", fill=_C_AMBER, outline=_C_AMBER_D)
    def _tl(e): c.itemconfigure("sl_thumb", fill="#DDD", outline="#999")
    c.tag_bind("sl_thumb","<Enter>",_te); c.tag_bind("sl_thumb","<Leave>",_tl)

    # percentage label (amber, right-aligned)
    c.create_text(tw-14, sl_cy, text=f"{ss['val']}%",
                  font=(_FF, 9, "bold"), fill=_C_AMBER, anchor="e", tags="sl_val")

    def _upd(v):
        v = max(10, min(90, v)); ss["val"] = v; fx2 = _v2x(v)
        c.delete("sl_fill")
        _rrect(c, sl_tx, sl_cy-_SL_H//2, max(1, fx2-sl_tx), _SL_H, _SL_H//2,
               fill=_C_AMBER, outline="", tags="sl_fill")
        c.coords("sl_thumb", fx2-TR, sl_cy-TR, fx2+TR, sl_cy+TR)
        c.tag_raise("sl_thumb")
        c.itemconfigure("sl_val", text=f"{v}%")
        on_alpha_change(str(v))

    def _sc(e): _upd(int(10+(e.x-sl_tx)/sl_tw*80))
    def _sd(e): _upd(int(10+(e.x-sl_tx)/sl_tw*80))
    for t in ("sl_track_bg","sl_fill","sl_thumb"):
        c.tag_bind(t,"<Button-1>",_sc); c.tag_bind(t,"<B1-Motion>",_sd)

    return top


def destroy_toolbar_window(toolbar_win):
    if toolbar_win and toolbar_win.winfo_exists():
        toolbar_win.destroy()


def setup_edit_toolbar(frame, **kwargs):
    pass


# =============================================================
#  Button editor popup
# =============================================================

def open_button_editor(parent, btn, *, on_save, on_delete, set_window_style):
    top = tk.Toplevel(parent)
    top.geometry("380x660")
    top.attributes("-topmost", True)
    top.title("\u7f16\u8f91\u6309\u94ae")
    top.configure(bg="#222")
    set_window_style('normal', target_window=top)
    
    # --- MODAL LOGIC START ---
    top.grab_set()
    top.focus_set()
    # --- MODAL LOGIC END ---

    def _keep():
        try:
            if top.winfo_exists(): top.lift(); top.after(500, _keep)
        except: pass
    top.lift(); top.after(200, _keep)

    entries = {}
    tk.Label(top, text="\u56fe\u5f62\u5316\u914d\u7f6e", fg=COLOR_BTN_BORDER, bg="#222",
             font=(_FF, 13, "bold")).pack(pady=(16, 8))

    for key, label_text, use_vk in EDIT_FIELDS:
        if key not in btn: btn[key] = ''
        frame = tk.Frame(top, bg="#222"); frame.pack(fill="x", padx=24, pady=4)
        tk.Label(frame, text=label_text, fg="#CCC", bg="#222",
                 width=10, anchor="w", font=(_FF, 9)).pack(side="left")
        e = tk.Entry(frame, font=(_FF, 10), bg="#3A3A3A", fg="white",
                     insertbackground="white", relief="flat", bd=4)
        e.insert(0, btn[key]); e.pack(side="left", fill="x", expand=True)
        entries[key] = e
        if use_vk:
            tk.Button(frame, text="+", width=3, bg="#404040", fg="#CCC", relief="flat",
                      font=(_FF, 9),
                      command=lambda ent=e: open_virtual_keyboard(top, ent)
                      ).pack(side="right", padx=(6, 0))

    def do_save():
        for k, e in entries.items():
            v = e.get().replace(" ", "").lower() if k != 'name' else e.get()
            btn[k] = v
        on_save(btn); top.destroy()

    def do_delete():
        on_delete(btn); top.destroy()

    tk.Button(top, text="\u4fdd  \u5b58", command=do_save,
              bg="#007A7A", fg="white", relief="flat", width=20,
              font=(_FF, 10, "bold"), activebackground="#009999").pack(pady=(20, 8))
    tk.Button(top, text="\u5220  \u9664", command=do_delete,
              bg="#6E1E1E", fg="white", relief="flat", width=20,
              font=(_FF, 10), activebackground="#8B2020").pack(pady=4)
