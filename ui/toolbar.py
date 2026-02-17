"""
TEGG Touch - toolbar.py
底部编辑工具栏：方案选择、新建/导入/导出、启动、穿透开关、透明度滑块。
"""

import tkinter as tk

from core.constants import (
    COLOR_PANEL, COLOR_TOOLBAR_TRANSPARENT,
    TOOLBAR_WIDTH, TOOLBAR_HEIGHT, TOOLBAR_RADIUS,
    TOOLBAR_BOTTOM_MARGIN,
)
from core.config_manager import get_active_profile_name
from ui.widgets import (
    FF, FS, IS, TOP, BTN_H, BTN_R, GAP,
    CLOSE_SIZE, CLOSE_M, DRAG_W,
    SL_LABEL_GAP, SL_H, SL_TR,
    C_CYBER, C_CYBER_H, C_GRAY, C_GRAY_H,
    C_AMBER, C_AMBER_D, C_CLOSE, C_CLOSE_H,
    icon_font, rrect,
)
from ui.profile_manager import open_profile_manager


def create_toolbar_window(parent, screen_w, screen_h, *,
                          on_add, on_run, on_export, on_import,
                          on_quit, transparency, on_alpha_change,
                          on_switch_profile, on_edit_passthrough=None,
                          edit_passthrough=False,
                          freeze_hotkey='f10', on_freeze_hotkey_change=None):
    """创建底部编辑工具栏窗口。"""
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

    # Background
    rrect(c, 0, 0, tw, th, r, fill=COLOR_PANEL, outline="#444", width=1, tags="toolbar_bg")

    ifont = icon_font()

    # --- Drag handle ---
    dcx, dcy = DRAG_W // 2, th // 2
    for dy in [-12, -4, 4, 12]:
        for dx in [-4, 4]:
            c.create_oval(dcx + dx - 2, dcy + dy - 2, dcx + dx + 2, dcy + dy + 2,
                          fill="#666", outline="", tags="drag_zone")
    c.create_line(DRAG_W + 2, 10, DRAG_W + 2, th - 10, fill="#444", width=1)

    drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}
    def _ds(e):
        drag["sx"], drag["sy"] = e.x_root, e.y_root
        drag["wx"], drag["wy"] = top.winfo_x(), top.winfo_y()
    def _dm(e):
        nx = drag["wx"] + (e.x_root - drag["sx"])
        ny = drag["wy"] + (e.y_root - drag["sy"])
        top.geometry(f"{tw}x{th}+{max(0, min(nx, screen_w - tw))}+{max(0, min(ny, screen_h - th))}")
    for t in ("drag_zone", "toolbar_bg"):
        c.tag_bind(t, "<Button-1>", _ds)
        c.tag_bind(t, "<B1-Motion>", _dm)

    # --- Close button (top-right) ---
    cx0 = tw - CLOSE_M - CLOSE_SIZE
    rrect(c, cx0, CLOSE_M, CLOSE_SIZE, CLOSE_SIZE, BTN_R,
          fill=C_CLOSE, outline="", tags=("tq", "tq_bg"))
    ccx, ccy = cx0 + CLOSE_SIZE // 2, CLOSE_M + CLOSE_SIZE // 2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, IS), fill="#FFF", tags=("tq",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(FF, FS, "bold"), fill="#FFF", tags=("tq",))
    def _ce(e): i = c.find_withtag("tq_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE_H)
    def _cl(e): i = c.find_withtag("tq_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE)
    c.tag_bind("tq", "<Enter>", _ce)
    c.tag_bind("tq", "<Leave>", _cl)
    c.tag_bind("tq", "<Button-1>", lambda e: on_quit())

    # ========== FIRST ROW ==========
    bx = DRAG_W + 16
    by = TOP

    _TBTN_W = 90
    def _txt_btn(x, y, icon_ch, fb, label, tag, bg, bg_h, cb):
        rrect(c, x, y, _TBTN_W, BTN_H, BTN_R, fill=bg, outline="", tags=(tag, tag + "_bg"))
        cy2 = y + BTN_H // 2
        if ifont:
            c.create_text(x + 12, cy2, text=icon_ch, font=(ifont, IS),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
            c.create_text(x + 38, cy2, text=label, font=(FF, FS),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
        else:
            c.create_text(x + 12, cy2, text=f"{fb} {label}", font=(FF, FS, "bold"),
                          fill="#E0E0E0", anchor="w", tags=(tag,))
        def _en(e): i = c.find_withtag(tag + "_bg"); i and c.itemconfigure(i[0], fill=bg_h)
        def _lv(e): i = c.find_withtag(tag + "_bg"); i and c.itemconfigure(i[0], fill=bg)
        c.tag_bind(tag, "<Enter>", _en)
        c.tag_bind(tag, "<Leave>", _lv)
        c.tag_bind(tag, "<Button-1>", lambda e: cb())

    # 1) Config selector
    _CFG_W = 180
    cfg_tag = "tcfg"
    rrect(c, bx, by, _CFG_W, BTN_H, BTN_R,
          fill=C_CYBER, outline="", tags=(cfg_tag, cfg_tag + "_bg"))
    cfg_cy = by + BTN_H // 2
    if ifont:
        c.create_text(bx + 14, cfg_cy, text="\uE7FC", font=(ifont, IS),
                      fill="#E0E0E0", anchor="w", tags=(cfg_tag,))
    active_profile = get_active_profile_name()
    c.create_text(bx + 40, cfg_cy, text=active_profile,
                  font=(FF, FS), fill="#E0E0E0", anchor="w", tags=(cfg_tag, "cfg_name"))
    c.create_text(bx + _CFG_W - 16, cfg_cy, text="\u25be",
                  font=(FF, -14), fill="#AAA", anchor="e", tags=(cfg_tag,))

    def _cfg_en(e): i = c.find_withtag(cfg_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_CYBER_H)
    def _cfg_lv(e): i = c.find_withtag(cfg_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_CYBER)
    c.tag_bind(cfg_tag, "<Enter>", _cfg_en)
    c.tag_bind(cfg_tag, "<Leave>", _cfg_lv)

    def _on_cfg_click():
        def _sw_wrapper(name):
            c.itemconfigure("cfg_name", text=name)
            on_switch_profile(name)
        open_profile_manager(top, _sw_wrapper)

    c.tag_bind(cfg_tag, "<Button-1>", lambda e: _on_cfg_click())
    bx += _CFG_W + GAP

    # 2) Add
    _txt_btn(bx, by, "\uE710", "\uff0b", "\u65b0\u5efa", "tadd", C_GRAY, C_GRAY_H, on_add)
    bx += _TBTN_W + GAP

    # 3) Import
    _txt_btn(bx, by, "\uE896", "\u2193", "\u5bfc\u5165", "timp", C_GRAY, C_GRAY_H, on_import)
    bx += _TBTN_W + GAP

    # 4) Export
    _txt_btn(bx, by, "\uE898", "\u2191", "\u5bfc\u51fa", "texp", C_GRAY, C_GRAY_H, on_export)
    bx += _TBTN_W + GAP

    # 5) Separator
    sep_x = bx + 4
    c.create_line(sep_x, by + 4, sep_x, by + BTN_H - 4, fill="#555", width=1)
    bx += 12

    # 6) Run button
    _RUN_W = 90
    run_tag = "trun"
    rrect(c, bx, by, _RUN_W, BTN_H, BTN_R,
          fill=C_AMBER_D, outline="", tags=(run_tag, run_tag + "_bg"))
    rcy = by + BTN_H // 2
    if ifont:
        c.create_text(bx + 14, rcy, text="\uE768", font=(ifont, IS),
                      fill="#FFF", anchor="w", tags=(run_tag,))
        c.create_text(bx + 40, rcy, text="\u542f\u52a8",
                      font=(FF, FS), fill="#FFF", anchor="w", tags=(run_tag,))
    else:
        c.create_text(bx + 12, rcy, text="\u25b6 \u542f\u52a8",
                      font=(FF, FS, "bold"), fill="#FFF", anchor="w", tags=(run_tag,))
    def _ren(e): i = c.find_withtag(run_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_AMBER)
    def _rlv(e): i = c.find_withtag(run_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_AMBER_D)
    c.tag_bind(run_tag, "<Enter>", _ren)
    c.tag_bind(run_tag, "<Leave>", _rlv)
    c.tag_bind(run_tag, "<Button-1>", lambda e: on_run())
    bx += _RUN_W + 20

    # 7) Passthrough Switch
    pt_tag = "tpt"
    pt_state = {"on": edit_passthrough}
    pt_label_x = bx
    pt_cy = by + BTN_H // 2

    c.create_text(pt_label_x, pt_cy, text="\u7a7f\u900f\u6a21\u5f0f",
                  font=(FF, -16, "bold"), fill="#AAA", anchor="w", tags=(pt_tag,))

    _SW_W = 48; _SW_H = 24; _SW_R = _SW_H // 2; _SW_DOT = 18
    sw_x = pt_label_x + 80
    sw_y = pt_cy - _SW_H // 2

    pill_color = C_AMBER if pt_state["on"] else C_GRAY
    c.create_oval(sw_x, sw_y, sw_x + _SW_H, sw_y + _SW_H,
                  fill=pill_color, outline="", tags=(pt_tag, "pt_pill_l"))
    c.create_oval(sw_x + _SW_W - _SW_H, sw_y, sw_x + _SW_W, sw_y + _SW_H,
                  fill=pill_color, outline="", tags=(pt_tag, "pt_pill_r"))
    c.create_rectangle(sw_x + _SW_R, sw_y, sw_x + _SW_W - _SW_R, sw_y + _SW_H,
                       fill=pill_color, outline="", tags=(pt_tag, "pt_pill_c"))

    dot_pad = (_SW_H - _SW_DOT) // 2
    dot_x = (sw_x + _SW_W - dot_pad - _SW_DOT) if pt_state["on"] else (sw_x + dot_pad)
    dot_y = sw_y + dot_pad
    c.create_oval(dot_x, dot_y, dot_x + _SW_DOT, dot_y + _SW_DOT,
                  fill="white", outline="", tags=(pt_tag, "pt_dot"))

    status_x = sw_x + _SW_W + 8
    status_text = "\u5f00\u542f" if pt_state["on"] else "\u5173\u95ed"
    status_color = C_AMBER if pt_state["on"] else "#888"
    c.create_text(status_x, pt_cy, text=status_text,
                  font=(FF, -16), fill=status_color, anchor="w", tags=(pt_tag, "pt_status"))

    def _update_pt_visual():
        p_color = C_AMBER if pt_state["on"] else C_GRAY
        c.itemconfigure("pt_pill_l", fill=p_color)
        c.itemconfigure("pt_pill_r", fill=p_color)
        c.itemconfigure("pt_pill_c", fill=p_color)
        if pt_state["on"]:
            dot_on_x = sw_x + _SW_W - dot_pad - _SW_DOT
            c.coords("pt_dot", dot_on_x, dot_y, dot_on_x + _SW_DOT, dot_y + _SW_DOT)
            c.itemconfigure("pt_status", text="\u5f00\u542f", fill=C_AMBER)
        else:
            dot_off_x = sw_x + dot_pad
            c.coords("pt_dot", dot_off_x, dot_y, dot_off_x + _SW_DOT, dot_y + _SW_DOT)
            c.itemconfigure("pt_status", text="\u5173\u95ed", fill="#888")

    def _toggle_pt(e=None):
        pt_state["on"] = not pt_state["on"]
        _update_pt_visual()
        if on_edit_passthrough:
            on_edit_passthrough(pt_state["on"])

    c.tag_bind(pt_tag, "<Button-1>", _toggle_pt)

    # ========== SECOND ROW: Freeze Hotkey + Slider ==========
    row2_y = TOP + BTN_H + 30

    # --- 冻结快捷键 ---
    fk_x = DRAG_W + 16
    fk_tag = "tfk"
    fk_state = {"key": freeze_hotkey or ""}

    c.create_text(fk_x, row2_y, text="冻结键",
                  font=(FF, 9, "bold"), fill="#AAA", anchor="w")

    _FK_BTN_W = 90
    _FK_BTN_H = 26
    fk_btn_x = fk_x + 52
    fk_btn_y = row2_y - _FK_BTN_H // 2

    rrect(c, fk_btn_x, fk_btn_y, _FK_BTN_W, _FK_BTN_H, 6,
          fill=C_CYBER, outline="", tags=(fk_tag, fk_tag + "_bg"))
    display_key = fk_state["key"].upper() if fk_state["key"] else "未设置"
    c.create_text(fk_btn_x + _FK_BTN_W // 2, row2_y, text=display_key,
                  font=(FF, -14, "bold"), fill="#E0E0E0", tags=(fk_tag, "fk_text"))

    def _fk_en(e): i = c.find_withtag(fk_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_CYBER_H)
    def _fk_lv(e): i = c.find_withtag(fk_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_CYBER)
    c.tag_bind(fk_tag, "<Enter>", _fk_en)
    c.tag_bind(fk_tag, "<Leave>", _fk_lv)

    def _on_fk_click():
        from ui.virtual_keyboard import open_key_picker
        def _on_pick(new_key):
            fk_state["key"] = new_key
            c.itemconfigure("fk_text", text=new_key.upper() if new_key else "未设置")
            if on_freeze_hotkey_change:
                on_freeze_hotkey_change(new_key)
        open_key_picker(top, _on_pick, current=fk_state["key"])

    c.tag_bind(fk_tag, "<Button-1>", lambda e: _on_fk_click())

    # --- Separator ---
    fk_sep_x = fk_btn_x + _FK_BTN_W + 14
    c.create_line(fk_sep_x, row2_y - 10, fk_sep_x, row2_y + 10, fill="#444", width=1)

    # --- 透明度滑块 ---
    sl_x = fk_sep_x + 14
    sl_y = row2_y
    c.create_text(sl_x, sl_y, text="\u900f\u660e\u5ea6",
                  font=(FF, 9, "bold"), fill="#AAA", anchor="w")

    sl_tx = sl_x + 52 + SL_LABEL_GAP + 12
    sl_tw = tw - sl_tx - 84
    sl_cy = sl_y

    rrect(c, sl_tx, sl_cy - SL_H // 2, sl_tw, SL_H, SL_H // 2,
          fill="#404040", outline="", tags="sl_track_bg")

    ss = {"val": int(transparency * 100)}

    def _v2x(v): return sl_tx + (v - 10) / 80.0 * sl_tw

    fx = _v2x(ss["val"])
    rrect(c, sl_tx, sl_cy - SL_H // 2, max(1, fx - sl_tx), SL_H, SL_H // 2,
          fill=C_AMBER, outline="", tags="sl_fill")

    TR = SL_TR
    c.create_oval(fx - TR, sl_cy - TR, fx + TR, sl_cy + TR,
                  fill="#DDD", outline="#999", width=1, tags="sl_thumb")

    def _te(e): c.itemconfigure("sl_thumb", fill=C_AMBER, outline=C_AMBER_D)
    def _tl(e): c.itemconfigure("sl_thumb", fill="#DDD", outline="#999")
    c.tag_bind("sl_thumb", "<Enter>", _te)
    c.tag_bind("sl_thumb", "<Leave>", _tl)

    c.create_text(tw - 14, sl_cy, text=f"{ss['val']}%",
                  font=(FF, 9, "bold"), fill=C_AMBER, anchor="e", tags="sl_val")

    def _upd(v):
        v = max(10, min(90, v)); ss["val"] = v; fx2 = _v2x(v)
        c.delete("sl_fill")
        rrect(c, sl_tx, sl_cy - SL_H // 2, max(1, fx2 - sl_tx), SL_H, SL_H // 2,
              fill=C_AMBER, outline="", tags="sl_fill")
        c.coords("sl_thumb", fx2 - TR, sl_cy - TR, fx2 + TR, sl_cy + TR)
        c.tag_raise("sl_thumb")
        c.itemconfigure("sl_val", text=f"{v}%")
        on_alpha_change(str(v))

    def _sc(e): _upd(int(10 + (e.x - sl_tx) / sl_tw * 80))
    def _sd(e): _upd(int(10 + (e.x - sl_tx) / sl_tw * 80))
    for t in ("sl_track_bg", "sl_fill", "sl_thumb"):
        c.tag_bind(t, "<Button-1>", _sc)
        c.tag_bind(t, "<B1-Motion>", _sd)

    return top


def destroy_toolbar_window(toolbar_win):
    """销毁工具栏窗口。"""
    if toolbar_win and toolbar_win.winfo_exists():
        toolbar_win.destroy()
