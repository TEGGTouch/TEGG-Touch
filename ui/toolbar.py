"""
TEGG Touch 蛋挞 - toolbar.py
底部编辑工具栏：方案选择、新建/导入/导出、启动、穿透开关、透明度滑块。
以及运行模式下的独立工具栏。
"""

import tkinter as tk

from core.constants import (
    COLOR_PANEL, COLOR_TOOLBAR_TRANSPARENT,
    TOOLBAR_WIDTH, TOOLBAR_HEIGHT, TOOLBAR_RADIUS,
    TOOLBAR_BOTTOM_MARGIN,
    PT_ON, PT_OFF, PT_BLOCK, PT_CYCLE,
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
from ui.hotkey_settings import open_hotkey_settings
from ui.about_dialog import open_about_dialog
from ui.canvas_renderer import init_cursor, update_cursor, remove_cursor


def create_toolbar_window(parent, screen_w, screen_h, *,
                          on_add, on_add_center_band=None, on_run,
                          on_quit, transparency, on_alpha_change,
                          on_switch_profile, on_edit_passthrough=None,
                          edit_passthrough=False):
    """创建底部编辑工具栏窗口（居中显示）。"""
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
            if top.winfo_exists():
                top.lift()
                # 同步 lift 软键盘 (同层级)
                from ui.virtual_keyboard import get_kb_instance
                kb = get_kb_instance()
                if kb:
                    try:
                        if kb.winfo_exists():
                            kb.lift()
                    except Exception:
                        pass
                top.after(300, _keep)
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
        nx = max(0, min(nx, screen_w - tw))
        ny = max(0, min(ny, screen_h - th))
        top.geometry(f"{tw}x{th}+{nx}+{ny}")
        # 同步移动软键盘
        from ui.virtual_keyboard import get_kb_instance, _position_above_toolbar
        kb = get_kb_instance()
        if kb:
            try:
                if kb.winfo_exists():
                    _position_above_toolbar(kb, top)
            except Exception:
                pass
    for t in ("drag_zone", "toolbar_bg"):
        c.tag_bind(t, "<Button-1>", _ds)
        c.tag_bind(t, "<B1-Motion>", _dm)

    # --- About button (top-right, left of settings) ---
    _SET_SIZE = CLOSE_SIZE
    _SET_GAP = 4
    C_SET_ED = "#4A4A4A"
    C_SET_ED_H = "#5A5A5A"

    ax0 = tw - CLOSE_M - CLOSE_SIZE - _SET_GAP - _SET_SIZE - _SET_GAP - _SET_SIZE
    rrect(c, ax0, CLOSE_M, _SET_SIZE, _SET_SIZE, BTN_R,
          fill=C_SET_ED, outline="", tags=("tabout", "tabout_bg"))
    acx, acy = ax0 + _SET_SIZE // 2, CLOSE_M + _SET_SIZE // 2
    if ifont:
        c.create_text(acx, acy, text="\uE946", font=(ifont, IS), fill="#CCC", tags=("tabout",))
    else:
        c.create_text(acx, acy, text="\u24d8", font=(FF, FS, "bold"), fill="#CCC", tags=("tabout",))
    def _ae(e): i = c.find_withtag("tabout_bg"); i and c.itemconfigure(i[0], fill=C_SET_ED_H)
    def _al(e): i = c.find_withtag("tabout_bg"); i and c.itemconfigure(i[0], fill=C_SET_ED)
    c.tag_bind("tabout", "<Enter>", _ae)
    c.tag_bind("tabout", "<Leave>", _al)
    c.tag_bind("tabout", "<ButtonRelease-1>", lambda e: open_about_dialog(top))

    # --- Settings button (top-right, left of close) ---
    sx0 = tw - CLOSE_M - CLOSE_SIZE - _SET_GAP - _SET_SIZE
    rrect(c, sx0, CLOSE_M, _SET_SIZE, _SET_SIZE, BTN_R,
          fill=C_SET_ED, outline="", tags=("tset", "tset_bg"))
    scx, scy = sx0 + _SET_SIZE // 2, CLOSE_M + _SET_SIZE // 2
    if ifont:
        c.create_text(scx, scy, text="\uE713", font=(ifont, IS), fill="#CCC", tags=("tset",))
    else:
        c.create_text(scx, scy, text="\u2699", font=(FF, FS, "bold"), fill="#CCC", tags=("tset",))
    def _se(e): i = c.find_withtag("tset_bg"); i and c.itemconfigure(i[0], fill=C_SET_ED_H)
    def _sl2(e): i = c.find_withtag("tset_bg"); i and c.itemconfigure(i[0], fill=C_SET_ED)
    c.tag_bind("tset", "<Enter>", _se)
    c.tag_bind("tset", "<Leave>", _sl2)
    c.tag_bind("tset", "<ButtonRelease-1>", lambda e: open_hotkey_settings(top))

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
    c.tag_bind("tq", "<ButtonRelease-1>", lambda e: on_quit())

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
        c.tag_bind(tag, "<ButtonRelease-1>", lambda e: cb())

    # 1) Config selector
    _CFG_W = 180
    cfg_tag = "tcfg"
    rrect(c, bx, by, _CFG_W, BTN_H, BTN_R,
          fill=C_CYBER, outline="", tags=(cfg_tag, cfg_tag + "_bg"))
    cfg_cy = by + BTN_H // 2
    if ifont:
        c.create_text(bx + 14, cfg_cy, text="\uE765", font=(ifont, IS),
                      fill="#E0E0E0", anchor="w", tags=(cfg_tag,))
    active_profile = get_active_profile_name()
    c.create_text(bx + 40, cfg_cy, text=active_profile,
                  font=(FF, FS), fill="#E0E0E0", anchor="w", tags=(cfg_tag, "cfg_name"))
    if ifont:
        c.create_text(bx + _CFG_W - 14, cfg_cy, text="\uE700",
                      font=(ifont, IS - 2), fill="#AAA", anchor="e", tags=(cfg_tag,))
    else:
        c.create_text(bx + _CFG_W - 14, cfg_cy, text="\u2630",
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

    c.tag_bind(cfg_tag, "<ButtonRelease-1>", lambda e: _on_cfg_click())
    bx += _CFG_W + GAP

    # 2) Add
    _txt_btn(bx, by, "\uE710", "\uff0b", "\u65b0\u5efa", "tadd", C_GRAY, C_GRAY_H, on_add)
    bx += _TBTN_W + GAP

    # 2b) Add Center Band (回中带)
    if on_add_center_band:
        _CB_W = 110
        _C_GREEN_TB = "#176F2C"
        _C_GREEN_TB_H = "#1E8E38"
        cb_tag = "tcb"
        rrect(c, bx, by, _CB_W, BTN_H, BTN_R, fill=_C_GREEN_TB, outline="", tags=(cb_tag, cb_tag + "_bg"))
        cb_cy = by + BTN_H // 2
        if ifont:
            c.create_text(bx + 12, cb_cy, text="\uE7C9", font=(ifont, IS),
                          fill="#FFF", anchor="w", tags=(cb_tag,))
            c.create_text(bx + 38, cb_cy, text="\u56de\u4e2d\u5e26", font=(FF, FS),
                          fill="#FFF", anchor="w", tags=(cb_tag,))
        else:
            c.create_text(bx + 12, cb_cy, text="\u229a \u56de\u4e2d\u5e26", font=(FF, FS, "bold"),
                          fill="#FFF", anchor="w", tags=(cb_tag,))
        def _cb_en(e): i = c.find_withtag(cb_tag + "_bg"); i and c.itemconfigure(i[0], fill=_C_GREEN_TB_H)
        def _cb_lv(e): i = c.find_withtag(cb_tag + "_bg"); i and c.itemconfigure(i[0], fill=_C_GREEN_TB)
        c.tag_bind(cb_tag, "<Enter>", _cb_en)
        c.tag_bind(cb_tag, "<Leave>", _cb_lv)
        c.tag_bind(cb_tag, "<ButtonRelease-1>", lambda e: on_add_center_band())
        bx += _CB_W + GAP

    # 3) Separator (between 新建/回中带 and 软键盘)
    sep_x = bx + 4
    c.create_line(sep_x, by + 4, sep_x, by + BTN_H - 4, fill="#555", width=1)
    bx += 12

    # 4) Keyboard button (软键盘) — 宽度加大到 110px 容纳三字
    _KB_W = 110
    def _toggle_kb():
        from ui.virtual_keyboard import toggle_soft_keyboard
        toggle_soft_keyboard(top, mode="input")

    kb_tag = "tkb"
    rrect(c, bx, by, _KB_W, BTN_H, BTN_R, fill=C_GRAY, outline="", tags=(kb_tag, kb_tag + "_bg"))
    kb_cy = by + BTN_H // 2
    if ifont:
        c.create_text(bx + 12, kb_cy, text="\uE765", font=(ifont, IS),
                      fill="#E0E0E0", anchor="w", tags=(kb_tag,))
        c.create_text(bx + 38, kb_cy, text="\u8f6f\u952e\u76d8", font=(FF, FS),
                      fill="#E0E0E0", anchor="w", tags=(kb_tag,))
    else:
        c.create_text(bx + 12, kb_cy, text="\u2328 \u8f6f\u952e\u76d8", font=(FF, FS, "bold"),
                      fill="#E0E0E0", anchor="w", tags=(kb_tag,))
    def _kb_en(e): i = c.find_withtag(kb_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_GRAY_H)
    def _kb_lv(e): i = c.find_withtag(kb_tag + "_bg"); i and c.itemconfigure(i[0], fill=C_GRAY)
    c.tag_bind(kb_tag, "<Enter>", _kb_en)
    c.tag_bind(kb_tag, "<Leave>", _kb_lv)
    c.tag_bind(kb_tag, "<ButtonRelease-1>", lambda e: _toggle_kb())
    bx += _KB_W + GAP

    # 5) Run button
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
    c.tag_bind(run_tag, "<ButtonRelease-1>", lambda e: on_run())
    bx += _RUN_W + 20

    # 7) Passthrough Switch
    # [Modify] 编辑模式暂时屏蔽穿透切换，强制使用智能穿透
    # pt_tag = "tpt"
    # pt_state = {"on": edit_passthrough}
    # pt_label_x = bx
    # pt_cy = by + BTN_H // 2

    # c.create_text(pt_label_x, pt_cy, text="\u7a7f\u900f\u6a21\u5f0f",
    #               font=(FF, -16, "bold"), fill="#AAA", anchor="w", tags=(pt_tag,))

    # _SW_W = 48; _SW_H = 24; _SW_R = _SW_H // 2; _SW_DOT = 18
    # sw_x = pt_label_x + 80
    # sw_y = pt_cy - _SW_H // 2

    # pill_color = C_AMBER if pt_state["on"] else C_GRAY
    # c.create_oval(sw_x, sw_y, sw_x + _SW_H, sw_y + _SW_H,
    #               fill=pill_color, outline="", tags=(pt_tag, "pt_pill_l"))
    # c.create_oval(sw_x + _SW_W - _SW_H, sw_y, sw_x + _SW_W, sw_y + _SW_H,
    #               fill=pill_color, outline="", tags=(pt_tag, "pt_pill_r"))
    # c.create_rectangle(sw_x + _SW_R, sw_y, sw_x + _SW_W - _SW_R, sw_y + _SW_H,
    #                    fill=pill_color, outline="", tags=(pt_tag, "pt_pill_c"))

    # dot_pad = (_SW_H - _SW_DOT) // 2
    # dot_x = (sw_x + _SW_W - dot_pad - _SW_DOT) if pt_state["on"] else (sw_x + dot_pad)
    # dot_y = sw_y + dot_pad
    # c.create_oval(dot_x, dot_y, dot_x + _SW_DOT, dot_y + _SW_DOT,
    #               fill="white", outline="", tags=(pt_tag, "pt_dot"))

    # status_x = sw_x + _SW_W + 8
    # status_text = "\u5f00\u542f" if pt_state["on"] else "\u5173\u95ed"
    # status_color = C_AMBER if pt_state["on"] else "#888"
    # c.create_text(status_x, pt_cy, text=status_text,
    #               font=(FF, -16), fill=status_color, anchor="w", tags=(pt_tag, "pt_status"))

    # def _update_pt_visual():
    #     p_color = C_AMBER if pt_state["on"] else C_GRAY
    #     c.itemconfigure("pt_pill_l", fill=p_color)
    #     c.itemconfigure("pt_pill_r", fill=p_color)
    #     c.itemconfigure("pt_pill_c", fill=p_color)
    #     if pt_state["on"]:
    #         dot_on_x = sw_x + _SW_W - dot_pad - _SW_DOT
    #         c.coords("pt_dot", dot_on_x, dot_y, dot_on_x + _SW_DOT, dot_y + _SW_DOT)
    #         c.itemconfigure("pt_status", text="\u5f00\u542f", fill=C_AMBER)
    #     else:
    #         dot_off_x = sw_x + dot_pad
    #         c.coords("pt_dot", dot_off_x, dot_y, dot_off_x + _SW_DOT, dot_y + _SW_DOT)
    #         c.itemconfigure("pt_status", text="\u5173\u95ed", fill="#888")

    # def _toggle_pt(e=None):
    #     pt_state["on"] = not pt_state["on"]
    #     _update_pt_visual()
    #     if on_edit_passthrough:
    #         on_edit_passthrough(pt_state["on"])

    # c.tag_bind(pt_tag, "<ButtonRelease-1>", _toggle_pt)

    # ========== SECOND ROW: Freeze Hotkey + Slider ==========
    row2_y = TOP + BTN_H + 30

    # --- 模拟模式选择器 ---
    sm_x = DRAG_W + 16
    sm_tag = "tsm"

    c.create_text(sm_x, row2_y, text="模拟模式",
                  font=(FF, 9, "bold"), fill="#AAA", anchor="w")

    _SM_BTN_W = 100
    _SM_BTN_H = 26
    sm_btn_x = sm_x + 66
    sm_btn_y = row2_y - _SM_BTN_H // 2

    rrect(c, sm_btn_x, sm_btn_y, _SM_BTN_W, _SM_BTN_H, 6,
          fill=C_CYBER, outline="", tags=(sm_tag, sm_tag + "_bg"))
    # 按钮文字 "键盘" + 下三角 ▼
    c.create_text(sm_btn_x + _SM_BTN_W // 2 - 6, row2_y, text="键盘",
                  font=(FF, -14, "bold"), fill="#E0E0E0", tags=(sm_tag, "sm_text"))
    c.create_text(sm_btn_x + _SM_BTN_W - 16, row2_y + 1, text="\u25BC",
                  font=(FF, -10), fill="#999", tags=(sm_tag, "sm_arrow"))

    # hover 效果 + tooltip
    _tooltip_id = {"id": None}

    def _sm_en(e):
        i = c.find_withtag(sm_tag + "_bg")
        if i:
            c.itemconfigure(i[0], fill=C_CYBER_H)
        # 显示 tooltip
        tip_x = sm_btn_x + _SM_BTN_W // 2
        tip_y = sm_btn_y - 18
        _tooltip_id["id"] = c.create_text(
            tip_x, tip_y, text="手柄模拟模式开发中",
            font=(FF, -12), fill="#888", tags="sm_tooltip")

    def _sm_lv(e):
        i = c.find_withtag(sm_tag + "_bg")
        if i:
            c.itemconfigure(i[0], fill=C_CYBER)
        # 隐藏 tooltip
        if _tooltip_id["id"]:
            c.delete(_tooltip_id["id"])
            _tooltip_id["id"] = None

    c.tag_bind(sm_tag, "<Enter>", _sm_en)
    c.tag_bind(sm_tag, "<Leave>", _sm_lv)

    # --- Separator ---
    fk_sep_x = sm_btn_x + _SM_BTN_W + 14
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


# ─── 运行模式工具栏 ──────────────────────────────────────────────

def create_run_toolbar(parent, screen_w, screen_h, *,
                       on_edit, on_passthrough, click_through=PT_ON,
                       set_window_style=None,
                       on_toggle_buttons=None, buttons_visible=True,
                       on_toggle_auto_center=None, auto_center=False,
                       on_open_settings=None):
    """创建运行模式独立工具栏（可拖拽、可收缩）。"""
    
    # 尺寸配置
    # 按钮高度 BTN_H=40 (widgets.py)
    # 上下间距 10px -> FULL_H = 10 + 40 + 10 = 60
    # 左右间距 10px
    FULL_H = 60
    MINI_W, MINI_H = 80, 60
    RADIUS = 10
    
    # 确保父窗口几何信息已更新
    parent.update_idletasks()
    
    # 初始位置：跟随父窗口左下角
    # 使用父窗口坐标以支持多显示器或非主屏情况
    try:
        base_x = parent.winfo_rootx()
        base_y = parent.winfo_rooty()
        base_h = parent.winfo_height()
    except:
        base_x, base_y = 0, 0
        base_h = screen_h

    INIT_X = base_x + 30
    INIT_Y = base_y + base_h - FULL_H - 30

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    # 初始宽度设为 800 (之后会根据内容自动调整)
    top.geometry(f"800x{FULL_H}+{INIT_X}+{INIT_Y}")
    top.attributes("-topmost", True)
    top.attributes("-alpha", 1.0)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    # 强制设置为不穿透（普通窗口样式），确保可交互
    if set_window_style:
        set_window_style('normal', top)

    # 隐藏系统光标，使用虚拟光标
    top.config(cursor="none")

    # 状态
    state = {
        "minimized": False,
        "width": 800,
        "height": FULL_H,
        "click_through": click_through,
        "buttons_visible": buttons_visible,
        "auto_center": auto_center,
        "x": INIT_X,
        "y": INIT_Y
    }

    c = tk.Canvas(top, width=800, height=FULL_H,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.pack(fill="both", expand=True)

    # 初始化虚拟光标
    init_cursor(c)
    # 绑定鼠标移动以更新光标位置
    c.bind("<Motion>", lambda e: update_cursor(c, e.x, e.y))
    # 绑定鼠标离开事件以移除光标 (防止残影)
    c.bind("<Leave>", lambda e: remove_cursor(c))

    ifont = icon_font()

    def redraw():
        c.delete("all")
        w, h = state["width"], state["height"]
        
        # 背景
        rrect(c, 0, 0, w, h, RADIUS, fill=COLOR_PANEL, outline="#444", width=1, tags="bg")

        # 拖拽区域绑定
        drag_tags = ("bg", "drag_handle", "title")
        
        # 1. 拖拽把手 (左侧)
        DRAG_ZONE_W = 24
        dcx = DRAG_ZONE_W // 2
        dcy = h // 2
        for dy in [-6, 0, 6]:
            for dx in [-2, 2]:
                c.create_oval(dcx + dx - 1, dcy + dy - 1, dcx + dx + 1, dcy + dy + 1,
                              fill="#666", outline="", tags="drag_handle")
        c.create_line(DRAG_ZONE_W, 10, DRAG_ZONE_W, h - 10, fill="#444", width=1)

        if state["minimized"]:
            # === 收缩状态 ===
            # 显示 LOGO / 图标
            c.create_text(w // 2 + DRAG_ZONE_W // 2, h // 2, text="TEGG", 
                          font=("Microsoft YaHei UI", 10, "bold"), 
                          fill=C_AMBER, tags="mini_logo")
            
            # 点击 Logo 展开
            c.tag_bind("mini_logo", "<ButtonRelease-1>", lambda e: toggle_minimize())
            
        else:
            # === 展开状态 ===
            
            # 2. 功能区起始 X (左间距 10px)
            bx = DRAG_ZONE_W + 10
            
            # 使用与 Edit Toolbar 一致的按钮高度
            BTN_H_RUN = BTN_H  # imported from widgets (40)
            
            # 垂直居中 (上下各 10px)
            by = (h - BTN_H_RUN) // 2
            
            # 按钮样式函数 (icon + text 居中)
            def _run_btn(x, w, text, icon, tag, bg, cb, bg_hover=C_GRAY_H, font_size=9, bold=True, fg="#E0E0E0"):
                rrect(c, x, by, w, BTN_H_RUN, BTN_R, fill=bg, outline="", tags=(tag, tag+"_bg"))
                cy = by + BTN_H_RUN // 2
                cx = x + w // 2  # 按钮水平中心
                
                fw = "bold" if bold else "normal"
                
                if ifont:
                    c.create_text(x + 10, cy, text=icon, font=(ifont, IS),
                                  fill=fg, anchor="w", tags=(tag,))
                    c.create_text(x + 34, cy, text=text, font=("Microsoft YaHei UI", font_size, fw),
                                  fill=fg, anchor="w", tags=(tag,))
                else:
                    c.create_text(x + w//2, cy, text=f"{icon}  {text}", font=("Microsoft YaHei UI", font_size, fw),
                                  fill=fg, tags=(tag,))
                
                def _en(e): c.itemconfigure(tag+"_bg", fill=bg_hover)
                def _lv(e): c.itemconfigure(tag+"_bg", fill=bg)
                c.tag_bind(tag, "<Enter>", _en)
                c.tag_bind(tag, "<Leave>", _lv)
                c.tag_bind(tag, "<ButtonRelease-1>", lambda e: cb())

            # --- 1. 方案文本 (带 icon, 固定宽度 200px) ---
            _PROF_W = 200
            active_profile = get_active_profile_name()
            _prof_cy = h // 2
            if ifont:
                c.create_text(bx, _prof_cy, text="\uE765", font=(ifont, IS),
                              fill="#AAA", anchor="w", tags="run_profile_txt")
                c.create_text(bx + 26, _prof_cy, text=f"\u65b9\u6848\uff1a{active_profile}",
                              font=("Microsoft YaHei UI", 10, "bold"),
                              fill="#AAA", anchor="w", tags="run_profile_txt")
            else:
                c.create_text(bx, _prof_cy, text=f"\U0001F4C4 \u65b9\u6848\uff1a{active_profile}",
                              font=("Microsoft YaHei UI", 10, "bold"),
                              fill="#AAA", anchor="w", tags="run_profile_txt")
            bx += _PROF_W

            # --- 分隔线 ---
            c.create_line(bx, by + 4, bx, by + BTN_H_RUN - 4, fill="#555", width=1)
            bx += 12

            # --- 统一按钮字号 = -18 (与退出/编辑一致) ---
            _RUN_FS = -18

            # --- 1.5 自动回中 [F6] (toggle 按钮, 绿/灰两态) ---
            _AC_W = 150
            ac_tag = "run_ac"
            ac_on = state["auto_center"]
            C_GREEN = "#176F2C"
            C_GREEN_H = "#1E8E38"

            ac_bg = C_GREEN if ac_on else C_GRAY
            ac_bg_h = C_GREEN_H if ac_on else C_GRAY_H
            ac_icon = "\uE7C9" if ac_on else "\uEA3A"
            ac_text = "\u56de\u4e2dON [F6]" if ac_on else "\u56de\u4e2dOFF [F6]"
            ac_fg = "#FFF" if ac_on else "#E0E0E0"

            rrect(c, bx, by, _AC_W, BTN_H_RUN, BTN_R, fill=ac_bg, outline="", tags=(ac_tag, ac_tag+"_bg"))
            ac_cy = by + BTN_H_RUN // 2
            if ifont:
                c.create_text(bx + 10, ac_cy, text=ac_icon, font=(ifont, IS),
                              fill=ac_fg, anchor="w", tags=(ac_tag,))
                c.create_text(bx + 34, ac_cy, text=ac_text,
                              font=("Microsoft YaHei UI", _RUN_FS),
                              fill=ac_fg, anchor="w", tags=(ac_tag,))
            else:
                c.create_text(bx + _AC_W//2, ac_cy, text=ac_text,
                              font=("Microsoft YaHei UI", _RUN_FS),
                              fill=ac_fg, tags=(ac_tag,))

            def _ac_enter(e):
                _bh = C_GREEN_H if state["auto_center"] else C_GRAY_H
                c.itemconfigure(ac_tag+"_bg", fill=_bh)
            def _ac_leave(e):
                _bg = C_GREEN if state["auto_center"] else C_GRAY
                c.itemconfigure(ac_tag+"_bg", fill=_bg)
            c.tag_bind(ac_tag, "<Enter>", _ac_enter)
            c.tag_bind(ac_tag, "<Leave>", _ac_leave)

            def _toggle_ac(e=None):
                state["auto_center"] = not state["auto_center"]
                if on_toggle_auto_center:
                    on_toggle_auto_center(state["auto_center"])
                redraw()

            c.tag_bind(ac_tag, "<ButtonRelease-1>", lambda e: _toggle_ac())
            bx += _AC_W + GAP

            # --- 2. 显示/隐藏按键 [F7] (toggle 按钮, 灰色风格) ---
            _VIS_W = 160
            vis_tag = "run_vis"
            vis_on = state["buttons_visible"]
            vis_icon = "\uED1A" if vis_on else "\uE7B3"
            vis_text = "\u9690\u85cf\u6309\u952e [F7]" if vis_on else "\u663e\u793a\u6309\u952e [F7]"

            rrect(c, bx, by, _VIS_W, BTN_H_RUN, BTN_R, fill=C_GRAY, outline="", tags=(vis_tag, vis_tag+"_bg"))
            vis_cy = by + BTN_H_RUN // 2
            if ifont:
                c.create_text(bx + 10, vis_cy, text=vis_icon, font=(ifont, IS),
                              fill="#E0E0E0", anchor="w", tags=(vis_tag,))
                c.create_text(bx + 34, vis_cy, text=vis_text,
                              font=("Microsoft YaHei UI", _RUN_FS),
                              fill="#E0E0E0", anchor="w", tags=(vis_tag,))
            else:
                c.create_text(bx + _VIS_W//2, vis_cy, text=vis_text,
                              font=("Microsoft YaHei UI", _RUN_FS),
                              fill="#E0E0E0", tags=(vis_tag,))

            def _vis_enter(e): c.itemconfigure(vis_tag+"_bg", fill=C_GRAY_H)
            def _vis_leave(e): c.itemconfigure(vis_tag+"_bg", fill=C_GRAY)
            c.tag_bind(vis_tag, "<Enter>", _vis_enter)
            c.tag_bind(vis_tag, "<Leave>", _vis_leave)

            def _toggle_vis(e=None):
                state["buttons_visible"] = not state["buttons_visible"]
                if on_toggle_buttons:
                    on_toggle_buttons(state["buttons_visible"])
                redraw()

            c.tag_bind(vis_tag, "<ButtonRelease-1>", lambda e: _toggle_vis())
            bx += _VIS_W + GAP

            # --- 3. 软键盘 [F8] ---
            _KB_BTN_W = 130
            def _toggle_kb_run():
                from ui.virtual_keyboard import toggle_soft_keyboard
                toggle_soft_keyboard(top, mode="input")

            _run_btn(bx, _KB_BTN_W, "\u8f6f\u952e\u76d8 [F8]", "\uE765", "btn_kb", C_GRAY, _toggle_kb_run, font_size=_RUN_FS, bold=False)
            bx += _KB_BTN_W + GAP

            # --- 4. 穿透模式 (三态循环按钮: PT_ON→PT_OFF→PT_BLOCK) ---
            _PT_W = 180
            pt_tag = "run_pt"
            _ct = state["click_through"]

            # 三态颜色/文字映射
            C_BLUE = "#1976D2"      # 蓝色 (穿透OFF)
            C_BLUE_H = "#2196F3"

            _PT_MAP = {
                PT_ON:    {"bg": C_GRAY,    "bg_h": C_GRAY_H,  "icon": "\uE73E", "text": "\u7a7f\u900fON [F9]",   "fg": "#E0E0E0"},
                PT_OFF:   {"bg": C_BLUE,    "bg_h": C_BLUE_H,  "icon": "\uE739", "text": "\u7a7f\u900fOFF [F10]", "fg": "#FFF"},
                PT_BLOCK: {"bg": C_AMBER_D, "bg_h": C_AMBER,   "icon": "\uE72E", "text": "\u4e0d\u7a7f\u900f [F11]",  "fg": "#FFF"},
            }
            _pm = _PT_MAP.get(_ct, _PT_MAP[PT_ON])

            rrect(c, bx, by, _PT_W, BTN_H_RUN, BTN_R, fill=_pm["bg"], outline="", tags=(pt_tag, pt_tag+"_bg"))
            pt_cy = by + BTN_H_RUN // 2
            if ifont:
                c.create_text(bx + 10, pt_cy, text=_pm["icon"], font=(ifont, IS),
                              fill=_pm["fg"], anchor="w", tags=(pt_tag,))
                c.create_text(bx + 34, pt_cy, text=_pm["text"],
                              font=("Microsoft YaHei UI", _RUN_FS),
                              fill=_pm["fg"], anchor="w", tags=(pt_tag,))
            else:
                c.create_text(bx + _PT_W//2, pt_cy, text=_pm["text"],
                              font=("Microsoft YaHei UI", _RUN_FS),
                              fill=_pm["fg"], tags=(pt_tag,))

            def _pt_enter(e):
                _m = _PT_MAP.get(state["click_through"], _PT_MAP[PT_ON])
                c.itemconfigure(pt_tag+"_bg", fill=_m["bg_h"])
            def _pt_leave(e):
                _m = _PT_MAP.get(state["click_through"], _PT_MAP[PT_ON])
                c.itemconfigure(pt_tag+"_bg", fill=_m["bg"])
            c.tag_bind(pt_tag, "<Enter>", _pt_enter)
            c.tag_bind(pt_tag, "<Leave>", _pt_leave)

            def _toggle_pt_wrapper(e=None):
                cur = state["click_through"]
                idx = PT_CYCLE.index(cur) if cur in PT_CYCLE else 0
                nxt = PT_CYCLE[(idx + 1) % len(PT_CYCLE)]
                state["click_through"] = nxt
                on_passthrough(nxt)
                redraw()

            c.tag_bind(pt_tag, "<ButtonRelease-1>", lambda e: _toggle_pt_wrapper())
            bx += _PT_W + GAP

            # --- 分隔线 ---
            c.create_line(bx, by + 4, bx, by + BTN_H_RUN - 4, fill="#555", width=1)
            bx += 12

            # --- 6. 停止 [F12] ---
            _EXIT_W = 130
            _run_btn(bx, _EXIT_W, "\u505c\u6b62 [F12]", "\uE71A", "btn_exit", C_CLOSE, on_edit, bg_hover=C_CLOSE_H, font_size=_RUN_FS, bold=False, fg="#FFF")
            bx += _EXIT_W + 10
            
            # 动态更新窗口宽度以适应内容
            if bx != state["width"]:
                state["width"] = bx
                # 使用保存的坐标，强制转为 int 避免浮点数导致格式错误
                top.geometry(f"{int(state['width'])}x{int(state['height'])}+{int(state['x'])}+{int(state['y'])}")
                # 重新绘制背景以适应新宽度
                rrect(c, 0, 0, state["width"], state["height"], RADIUS, fill=COLOR_PANEL, outline="#444", width=1, tags="bg")
                c.tag_lower("bg") # 确保背景在最底层
        
        if state["minimized"]:
            state["width"] = MINI_W
            state["height"] = MINI_H
            # 应用新尺寸和位置 (收缩状态)
            top.geometry(f"{state['width']}x{state['height']}+{state['x']}+{state['y']}")
            c.config(width=state["width"], height=state["height"])
            
            # 由于改变了尺寸，需要重新绘制内容（主要是背景和Logo）
            # 但为了避免无限递归，我们需要小心。
            # 这里 redraw() 内部根据 state["minimized"] 已经绘制了内容。
            # 上面的 c.delete("all") 已经清除了旧内容。
            # 这里的递归调用 redraw() 是有风险的，因为它会再次清除并绘制。
            # 如果 geometry 改变触发了事件可能还好，但直接调用会导致死循环如果逻辑不当。
            # 实际上，上面的代码已经完成了绘制。这里不需要再次 redraw()，
            # 除非是 width/height 变化导致需要重新布局（但在 minimized 状态下内容很简单）。
            
            # 修正：不要递归调用 redraw()。
            # 上面的绘制代码已经处理了 minimized 的情况 (绘制 Logo)。
            # 我们只需要更新窗口大小。
            
        else:
            # 展开状态下，宽度由 bx 动态决定，已经在上面计算并设置了。
            # state["width"] = bx  <-- 已经在上面设置了
            state["height"] = FULL_H
            
            # 应用新尺寸和位置
            top.geometry(f"{state['width']}x{state['height']}+{state['x']}+{state['y']}")
            c.config(width=state["width"], height=state["height"])

    # 拖拽逻辑
    drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}
    def _ds(e):
        drag["sx"], drag["sy"] = e.x_root, e.y_root
        drag["wx"], drag["wy"] = top.winfo_x(), top.winfo_y()
    def _dm(e):
        nx = drag["wx"] + (e.x_root - drag["sx"])
        ny = drag["wy"] + (e.y_root - drag["sy"])
        
        w, h = state["width"], state["height"]
        nx = max(0, min(nx, screen_w - w))
        ny = max(0, min(ny, screen_h - h))
        
        # 更新状态
        state["x"] = nx
        state["y"] = ny
        
        top.geometry(f"{w}x{h}+{nx}+{ny}")
        
        # 同步移动软键盘
        from ui.virtual_keyboard import get_kb_instance, _position_above_toolbar
        kb = get_kb_instance()
        if kb:
            try:
                if kb.winfo_exists():
                    _position_above_toolbar(kb, top)
            except Exception:
                pass

    # Bind drag events to tags
    for t in ("bg", "drag_handle"):
        c.tag_bind(t, "<Button-1>", _ds)
        c.tag_bind(t, "<B1-Motion>", _dm)

    redraw()
    
    def _keep():
        try:
            if top.winfo_exists():
                top.lift()
                # 同步 lift 软键盘 (同层级)
                from ui.virtual_keyboard import get_kb_instance
                kb = get_kb_instance()
                if kb:
                    try:
                        if kb.winfo_exists():
                            kb.lift()
                    except Exception:
                        pass
                top.after(300, _keep)
        except: pass
    top.lift(); top.after(100, _keep)

    return top


def destroy_toolbar_window(toolbar_win):
    """销毁工具栏窗口（同时关闭软键盘）。"""
    from ui.virtual_keyboard import get_kb_instance
    kb = get_kb_instance()
    if kb:
        try:
            if kb.winfo_exists():
                kb.destroy()
        except Exception:
            pass
    if toolbar_win and toolbar_win.winfo_exists():
        toolbar_win.destroy()
