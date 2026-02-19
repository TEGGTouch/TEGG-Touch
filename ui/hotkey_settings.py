"""
TEGG Touch - hotkey_settings.py
快捷键设置弹窗：左右两栏布局（与 button_editor 风格一致）。
左栏：快捷键列表 + 回中延迟滑块
右栏：可选按键面板
底部：重置 / 保存
"""

import tkinter as tk
import tkinter.font as tkFont
import copy

from core.constants import (
    COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS,
    DEFAULT_HOTKEYS, HOTKEY_LABELS,
)
from core.config_manager import load_hotkeys, save_hotkeys
from ui.widgets import (
    FF, FS, IS, BTN_H, BTN_R, CLOSE_SIZE, CLOSE_M,
    C_GRAY, C_GRAY_H, C_AMBER, C_AMBER_D,
    C_CYBER, C_CYBER_H,
    C_PM_BG, C_CLOSE, C_CLOSE_H,
    icon_font, rrect, create_modal_overlay,
)
from ui.button_editor import TagInput, KEY_CATEGORIES

# ─── 颜色 ──────────────────────────────────────────────────────
_C_TAG_BG = "#404040"
_C_TAG_HOVER = "#555555"
_C_TAG_TEXT = "#E0E0E0"
_C_CAT_LABEL = "#888888"

# 每个快捷键的高亮色
_HK_COLORS = {
    "auto_center":    "#176F2C",
    "toggle_buttons": "#6B7280",
    "soft_keyboard":  "#0284C7",
    "pt_on":          "#6B7280",
    "pt_off":         "#1976D2",
    "pt_block":       "#D97706",
    "stop":           "#C42B1C",
}

# 快捷键字段顺序
_HK_KEYS = ["auto_center", "toggle_buttons", "soft_keyboard",
            "pt_on", "pt_off", "pt_block", "stop"]

# ─── 行布局常量 ────────────────────────────────────────────────
ROW_H = 50
DOT_W = 20
LABEL_W = 120
INPUT_PAD = 10
INPUT_H = 42


def open_hotkey_settings(parent, on_save_callback=None):
    """打开快捷键设置弹窗。"""
    overlay = create_modal_overlay(parent)

    LEFT_W = 380
    RIGHT_W = 500
    PADDING = 20
    DIVIDER = 1
    width = LEFT_W + DIVIDER + RIGHT_W + PADDING * 2
    height = 760
    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.geometry(f"{width}x{height}+{x}+{y}")
    top.attributes("-topmost", True)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    def _destroy_all(e):
        try: overlay.destroy()
        except: pass
    top.bind("<Destroy>", _destroy_all, add="+")
    top.focus_set()
    overlay.attributes("-topmost", True)
    top.attributes("-topmost", True)
    top.lift()

    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)
    rrect(c, 0, 0, width, height, TOOLBAR_RADIUS, fill=C_PM_BG, outline="#444", width=1, tags="bg")

    # ── 拖拽 ──
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

    # ── 标题 ──
    c.create_text(PADDING, 25, text="⚙ 快捷键设置", font=(FF, 11, "bold"),
                  fill="white", anchor="w", tags="title")
    c.tag_bind("title", "<Button-1>", _ds)
    c.tag_bind("title", "<B1-Motion>", _dm)

    # ── 关闭按钮 ──
    ifont = icon_font()
    cx0 = width - CLOSE_M - CLOSE_SIZE
    cy0 = CLOSE_M
    rrect(c, cx0, cy0, CLOSE_SIZE, CLOSE_SIZE, BTN_R,
          fill=C_CLOSE, outline="", tags=("close", "close_bg"))
    ccx, ccy = cx0 + CLOSE_SIZE // 2, cy0 + CLOSE_SIZE // 2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, IS), fill="#FFF", tags=("close",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(FF, FS, "bold"), fill="#FFF", tags=("close",))
    c.tag_bind("close", "<Enter>", lambda e: c.itemconfigure("close_bg", fill=C_CLOSE_H))
    c.tag_bind("close", "<Leave>", lambda e: c.itemconfigure("close_bg", fill=C_CLOSE))
    c.tag_bind("close", "<ButtonRelease-1>", lambda e: top.destroy())

    # ── Tip ──
    tip_y = 50
    tip_text = "💡 点击右侧按键添加到输入框 ｜ Backspace 删除 ｜ 支持组合键"
    tip_lbl = tk.Label(top, text=tip_text, bg=C_PM_BG, fg="#777", font=(FF, 9), anchor="w")
    tip_lbl.place(x=PADDING, y=tip_y, width=width - PADDING * 2)
    tip_lbl.lift()

    content_y = tip_y + 40

    # ── 分隔线 ──
    div_x = PADDING + LEFT_W
    c.create_line(div_x, content_y - 10, div_x, height - PADDING, fill="#444", width=1)

    # =================================================================
    #  LEFT COLUMN: Hotkey Fields + Delay Slider
    # =================================================================
    form_x = PADDING
    form_w = LEFT_W - 10
    input_x = DOT_W + LABEL_W + INPUT_PAD
    input_w = form_w - input_x

    hotkeys = load_hotkeys()
    focus_state = {"current_widget": None}
    fields = {}  # key -> TagInput

    def _set_focus(widget):
        old = focus_state["current_widget"]
        if old and old != widget and old.winfo_exists():
            if isinstance(old, TagInput):
                old.configure(highlightbackground=C_GRAY, highlightcolor=C_GRAY)
        focus_state["current_widget"] = widget
        if isinstance(widget, TagInput):
            widget.configure(highlightbackground=widget._accent,
                             highlightcolor=widget._accent)
        widget.focus_set()

    # ── 延迟滑块常量 (提前定义用于计算布局) ──
    _DELAY_COLOR = '#176F2C'
    _DELAY_ROW_H = 36
    _DELAY_SLIDER_H = 28
    _DELAY_ENTRY_W = 80
    _DELAY_MS_W = 26
    _SL_TK_H = 8
    _SL_TR = 10
    delay_total_h = _DELAY_ROW_H + 4 + _DELAY_SLIDER_H

    # ── 第一组: auto_center ──
    hk_frame_1 = tk.Frame(top, bg=C_PM_BG)
    hk1_h = ROW_H
    hk_frame_1.place(x=form_x, y=content_y, width=form_w, height=hk1_h)
    hk_frame_1.lift()

    key = "auto_center"
    color = _HK_COLORS.get(key, C_AMBER)
    label_text = HOTKEY_LABELS.get(key, key)
    current_val = hotkeys.get(key, DEFAULT_HOTKEYS[key])
    dot = tk.Frame(hk_frame_1, bg=color, width=8, height=8)
    dot.place(x=4, y=(ROW_H - 8) // 2, width=8, height=8)
    lbl = tk.Label(hk_frame_1, text=label_text, bg=C_PM_BG, fg="#CCC",
                   font=(FF, 10), anchor="w")
    lbl.place(x=DOT_W, y=0, height=ROW_H)
    wy = (ROW_H - INPUT_H) // 2
    ti = TagInput(hk_frame_1, initial_value=current_val, accent_color=color)
    ti.place(x=input_x, y=wy, width=input_w, height=INPUT_H)
    ti.bind("<FocusIn>", lambda ev, w=ti: _set_focus(w))
    fields[key] = ti

    # ── 回中延迟滑块 (紧跟 auto_center 下方) ──
    delay_y = content_y + hk1_h + 4

    # ── 第二组: 其余快捷键 ──
    _HK_REST = [k for k in _HK_KEYS if k != "auto_center"]
    hk2_y = delay_y + delay_total_h + 10
    hk_frame_2 = tk.Frame(top, bg=C_PM_BG)
    hk2_h = len(_HK_REST) * ROW_H
    hk_frame_2.place(x=form_x, y=hk2_y, width=form_w, height=hk2_h)
    hk_frame_2.lift()

    for i, key in enumerate(_HK_REST):
        local_y = i * ROW_H
        color = _HK_COLORS.get(key, C_AMBER)
        label_text = HOTKEY_LABELS.get(key, key)
        current_val = hotkeys.get(key, DEFAULT_HOTKEYS[key])

        dot = tk.Frame(hk_frame_2, bg=color, width=8, height=8)
        dot.place(x=4, y=local_y + (ROW_H - 8) // 2, width=8, height=8)

        lbl = tk.Label(hk_frame_2, text=label_text, bg=C_PM_BG, fg="#CCC",
                       font=(FF, 10), anchor="w")
        lbl.place(x=DOT_W, y=local_y, height=ROW_H)

        wy = local_y + (ROW_H - INPUT_H) // 2
        ti = TagInput(hk_frame_2, initial_value=current_val, accent_color=color)
        ti.place(x=input_x, y=wy, width=input_w, height=INPUT_H)
        ti.bind("<FocusIn>", lambda ev, w=ti: _set_focus(w))
        fields[key] = ti

    delay_frame = tk.Frame(top, bg=C_PM_BG)
    delay_frame.place(x=form_x, y=delay_y, width=form_w, height=delay_total_h)
    delay_frame.lift()

    # Row 1: label + entry + ms
    dot2 = tk.Frame(delay_frame, bg=_DELAY_COLOR, width=8, height=8)
    dot2.place(x=4, y=(_DELAY_ROW_H - 8) // 2, width=8, height=8)

    lbl2 = tk.Label(delay_frame, text="回中延迟", bg=C_PM_BG, fg="#CCC",
                    font=(FF, 10), anchor="w")
    lbl2.place(x=DOT_W, y=0, height=_DELAY_ROW_H)

    ms_lbl = tk.Label(delay_frame, text="ms", bg=C_PM_BG, fg="#888",
                      font=(FF, 9), anchor="w")
    ms_x = form_w - _DELAY_MS_W
    ms_lbl.place(x=ms_x, y=0, width=_DELAY_MS_W, height=_DELAY_ROW_H)

    entry_x = ms_x - _DELAY_ENTRY_W - 4
    delay_val = int(hotkeys.get("auto_center_delay", 1500))
    delay_entry = tk.Entry(delay_frame, font=(FF, 10), bg="#3A3A3A", fg=_DELAY_COLOR,
                           insertbackground="white", relief="flat", bd=2,
                           justify="center",
                           highlightthickness=1, highlightbackground="#555",
                           highlightcolor=_DELAY_COLOR)
    delay_entry.place(x=entry_x, y=(_DELAY_ROW_H - 28) // 2,
                      width=_DELAY_ENTRY_W, height=28)
    delay_entry.insert(0, str(delay_val))

    # Row 2: Canvas slider (0~5000ms range)
    row2_y = _DELAY_ROW_H + 4
    slider_x = DOT_W
    slider_w = form_w - slider_x
    TR = _SL_TR
    MAX_DELAY = 5000

    sc = tk.Canvas(delay_frame, width=slider_w, height=_DELAY_SLIDER_H,
                   bg=C_PM_BG, highlightthickness=0)
    sc.place(x=slider_x, y=row2_y)

    track_x = TR
    track_w = slider_w - TR * 2
    track_cy = _DELAY_SLIDER_H // 2

    rrect(sc, track_x, track_cy - _SL_TK_H // 2, track_w, _SL_TK_H,
          _SL_TK_H // 2, fill="#404040", outline="", tags="dl_bg")

    _ss = {"val": min(delay_val, MAX_DELAY)}

    def _v2x(v):
        return track_x + (max(0, min(v, MAX_DELAY)) / MAX_DELAY) * track_w

    fx = _v2x(_ss["val"])
    rrect(sc, track_x, track_cy - _SL_TK_H // 2, max(1, fx - track_x), _SL_TK_H,
          _SL_TK_H // 2, fill=_DELAY_COLOR, outline="", tags="dl_fill")
    sc.create_oval(fx - TR, track_cy - TR, fx + TR, track_cy + TR,
                   fill="#DDD", outline="#999", width=1, tags="dl_thumb")

    _syncing = [False]

    def _update_slider(v):
        v = max(0, min(v, MAX_DELAY))
        _ss["val"] = v
        fx2 = _v2x(v)
        sc.delete("dl_fill")
        rrect(sc, track_x, track_cy - _SL_TK_H // 2, max(1, fx2 - track_x), _SL_TK_H,
              _SL_TK_H // 2, fill=_DELAY_COLOR, outline="", tags="dl_fill")
        sc.coords("dl_thumb", fx2 - TR, track_cy - TR, fx2 + TR, track_cy + TR)
        sc.tag_raise("dl_thumb")

    def _on_slider_click(e):
        v = int((e.x - track_x) / track_w * MAX_DELAY)
        v = round(v / 50) * 50
        v = max(0, min(v, MAX_DELAY))
        _update_slider(v)
        if not _syncing[0]:
            _syncing[0] = True
            delay_entry.delete(0, tk.END)
            delay_entry.insert(0, str(v))
            _syncing[0] = False

    for t in ("dl_bg", "dl_fill", "dl_thumb"):
        sc.tag_bind(t, "<Button-1>", _on_slider_click)
        sc.tag_bind(t, "<B1-Motion>", _on_slider_click)

    def _on_entry_change(*_):
        if _syncing[0]:
            return
        _syncing[0] = True
        try:
            val = int(delay_entry.get())
            _update_slider(min(val, MAX_DELAY))
        except ValueError:
            pass
        _syncing[0] = False

    delay_entry.bind("<KeyRelease>", _on_entry_change)

    # 默认焦点
    if _HK_KEYS:
        top.after(100, lambda: _set_focus(fields[_HK_KEYS[0]]))

    # =================================================================
    #  BOTTOM BUTTONS: 重置 / 保存
    # =================================================================
    btn_h = 40
    btn_gap = 10
    total_w = form_w
    row_btn_y = height - PADDING - btn_h
    half_w = (total_w - btn_gap) // 2

    # 重置
    rrect(c, PADDING, row_btn_y, half_w, btn_h, BTN_R,
          fill="#6E1E1E", outline="", tags=("reset", "reset_bg"))
    c.create_text(PADDING + half_w // 2, row_btn_y + btn_h // 2, text="重置默认",
                  font=(FF, FS), fill="white", tags=("reset",))
    c.tag_bind("reset", "<Enter>", lambda e: c.itemconfigure("reset_bg", fill="#8B2020"))
    c.tag_bind("reset", "<Leave>", lambda e: c.itemconfigure("reset_bg", fill="#6E1E1E"))

    def _do_reset(e=None):
        for key in _HK_KEYS:
            ti = fields[key]
            ti.tags.clear()
            default_val = DEFAULT_HOTKEYS[key]
            for part in default_val.split("+"):
                part = part.strip()
                if part:
                    ti.tags.append(part)
            ti._render_tags()
        delay_entry.delete(0, tk.END)
        delay_entry.insert(0, str(DEFAULT_HOTKEYS["auto_center_delay"]))
        _update_slider(min(DEFAULT_HOTKEYS["auto_center_delay"], MAX_DELAY))

    c.tag_bind("reset", "<ButtonRelease-1>", _do_reset)

    # 保存
    save_x = PADDING + half_w + btn_gap
    rrect(c, save_x, row_btn_y, half_w, btn_h, BTN_R,
          fill=C_CYBER, outline="", tags=("save", "save_bg"))
    c.create_text(save_x + half_w // 2, row_btn_y + btn_h // 2, text="保存",
                  font=(FF, FS), fill="white", tags=("save",))
    c.tag_bind("save", "<Enter>", lambda e: c.itemconfigure("save_bg", fill=C_CYBER_H))
    c.tag_bind("save", "<Leave>", lambda e: c.itemconfigure("save_bg", fill=C_CYBER))

    def _do_save(e=None):
        result = {}
        for key in _HK_KEYS:
            result[key] = fields[key].get_value()
        try:
            result["auto_center_delay"] = max(0, int(delay_entry.get()))
        except ValueError:
            result["auto_center_delay"] = DEFAULT_HOTKEYS["auto_center_delay"]
        save_hotkeys(result)
        if on_save_callback:
            on_save_callback(result)
        top.destroy()

    c.tag_bind("save", "<ButtonRelease-1>", _do_save)

    # =================================================================
    #  RIGHT COLUMN: Key Palette (scrollable)
    # =================================================================
    right_x = PADDING + LEFT_W + DIVIDER + 10
    right_y = content_y - 10
    right_w = RIGHT_W - 20
    right_h = height - right_y - PADDING

    right_container = tk.Frame(top, bg=C_PM_BG)
    right_container.place(x=right_x, y=right_y, width=right_w, height=right_h)
    right_container.lift()

    right_canvas = tk.Canvas(right_container, bg=C_PM_BG, highlightthickness=0)
    right_inner = tk.Frame(right_canvas, bg=C_PM_BG)

    right_inner.bind("<Configure>",
                     lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
    cw_id = right_canvas.create_window((0, 0), window=right_inner, anchor="nw")

    def _on_rc_configure(e):
        right_canvas.itemconfig(cw_id, width=e.width)
    right_canvas.bind("<Configure>", _on_rc_configure)
    right_canvas.pack(side="left", fill="both", expand=True)

    def _on_mw(event):
        if right_canvas.yview() != (0.0, 1.0):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    right_container.bind('<Enter>', lambda e: right_canvas.bind_all("<MouseWheel>", _on_mw))
    right_container.bind('<Leave>', lambda e: right_canvas.unbind_all("<MouseWheel>"))

    def _append_key(key_name):
        w = focus_state["current_widget"]
        if w is None or not w.winfo_exists():
            return
        if isinstance(w, TagInput):
            w.add_tag(key_name)
        w.focus_set()

    # ── 按键面板 ──
    TAG_MIN_W = 40
    TAG_H = 40
    TAG_PAD_X = 12
    TAG_FONT = (FF, 10)
    TAG_GAP_X = 8
    TAG_GAP_Y = 10
    CAT_GAP = 40

    measure_font = tkFont.Font(family=FF, size=10)
    avail_w = right_w - 30

    is_first_cat = True
    for cat_name, keys in KEY_CATEGORIES:
        top_pad = 0 if is_first_cat else CAT_GAP
        is_first_cat = False

        cat_lbl = tk.Label(right_inner, text=f"── {cat_name} ──", bg=C_PM_BG,
                           fg=_C_CAT_LABEL, font=(FF, 10, "bold"), anchor="w")
        cat_lbl.pack(fill="x", padx=5, pady=(top_pad, 10))

        flow_frame = tk.Frame(right_inner, bg=C_PM_BG)
        flow_frame.pack(fill="x", padx=5)

        row_idx = 0
        col_x = 0
        for key_name in keys:
            text_w = measure_font.measure(key_name)
            btn_w = max(TAG_MIN_W, text_w + TAG_PAD_X * 2)
            if col_x > 0 and col_x + TAG_GAP_X + btn_w > avail_w:
                row_idx += 1
                col_x = 0
            tag_lbl = tk.Label(flow_frame, text=key_name, bg=_C_TAG_BG, fg=_C_TAG_TEXT,
                               font=TAG_FONT, cursor="hand2", anchor="center", width=0)
            tag_lbl.place(x=col_x, y=row_idx * (TAG_H + TAG_GAP_Y),
                          width=btn_w, height=TAG_H)
            col_x += btn_w + TAG_GAP_X
            tag_lbl.bind("<Enter>", lambda ev, w=tag_lbl: w.configure(bg=_C_TAG_HOVER))
            tag_lbl.bind("<Leave>", lambda ev, w=tag_lbl: w.configure(bg=_C_TAG_BG))
            tag_lbl.bind("<Button-1>", lambda ev, k=key_name: _append_key(k))

        total_rows = row_idx + 1
        frame_h = total_rows * TAG_H + (total_rows - 1) * TAG_GAP_Y
        flow_frame.configure(height=frame_h)
        flow_frame.pack_propagate(False)

    return top
