"""
FKB - button_editor.py
按钮编辑弹窗：左右两栏布局。
左栏：按键绑定表单 + 使用说明 + 复制/删除/保存。
右栏：分类按键面板，点击追加到当前焦点输入框。
"""

import tkinter as tk

from core.constants import COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS
from ui.widgets import (
    FF, FS, IS, BTN_H, BTN_R, CLOSE_SIZE, CLOSE_M,
    C_GRAY, C_GRAY_H, C_AMBER, C_AMBER_D,
    C_PM_BG, C_CLOSE, C_CLOSE_H,
    icon_font, rrect, create_modal_overlay,
)

# ─── 编辑字段 ──────────────────────────────────────────────────
EDIT_FIELDS = [
    ('name',      '按钮名称', False),
    ('lclick',    '左键模拟', True),
    ('mclick',    '中键模拟', True),
    ('hover',     '悬浮模拟', True),
    ('rclick',    '右键模拟', True),
    ('wheelup',   '滚轮上滚', True),
    ('wheeldown', '滚轮下滚', True),
]

# ─── 按键分类数据 ──────────────────────────────────────────────
KEY_CATEGORIES = [
    ("字母", [chr(c) for c in range(ord('a'), ord('z') + 1)]),
    ("数字", [str(i) for i in range(10)]),
    ("F键", [f"f{i}" for i in range(1, 13)]),
    ("方向键", ["up", "down", "left", "right"]),
    ("修饰键", ["ctrl", "shift", "alt"]),
    ("功能键", ["space", "enter", "esc", "tab", "backspace"]),
    ("其他", ["home", "end", "pageup", "pagedown", "insert", "delete"]),
    ("小键盘", [f"num {i}" for i in range(10)] + ["num lock"]),
]

# ─── 颜色 ──────────────────────────────────────────────────────
_C_TAG_BG = "#404040"
_C_TAG_HOVER = "#555555"
_C_TAG_TEXT = "#E0E0E0"
_C_CAT_LABEL = "#888888"
_C_FOCUS_BORDER = C_AMBER


def open_button_editor(parent, btn, *, on_save, on_delete, on_copy, set_window_style):
    """打开按钮编辑弹窗（左右两栏布局）。"""
    overlay = create_modal_overlay(parent)

    # ── 尺寸 ──
    LEFT_W = 340
    RIGHT_W = 560
    PADDING = 20
    DIVIDER = 1
    width = LEFT_W + DIVIDER + RIGHT_W + PADDING * 2  # ~941
    height = 680
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

    # ── 背景 ──
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
    c.create_text(PADDING, 25, text="编辑按钮", font=(FF, 11, "bold"),
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
    def _ce(e): i = c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE_H)
    def _cl(e): i = c.find_withtag("close_bg"); i and c.itemconfigure(i[0], fill=C_CLOSE)
    c.tag_bind("close", "<Enter>", _ce)
    c.tag_bind("close", "<Leave>", _cl)
    c.tag_bind("close", "<Button-1>", lambda e: top.destroy())

    # ── 分隔线 ──
    div_x = PADDING + LEFT_W
    header_y = 55
    c.create_line(div_x, header_y, div_x, height - PADDING, fill="#444", width=1)

    # =================================================================
    #  LEFT COLUMN: Form + Help + Buttons
    # =================================================================
    form_x = PADDING
    form_y = header_y + 10
    form_w = LEFT_W - 10  # slight right margin before divider

    # ── 焦点追踪 ──
    focus_state = {"current_entry": None}
    entries = {}

    def _set_focus(entry_widget):
        """设置焦点输入框，高亮边框。"""
        # 恢复旧焦点
        old = focus_state["current_entry"]
        if old and old.winfo_exists():
            old.configure(highlightbackground=C_GRAY, highlightcolor=C_GRAY)
        # 设置新焦点
        focus_state["current_entry"] = entry_widget
        entry_widget.configure(highlightbackground=_C_FOCUS_BORDER, highlightcolor=_C_FOCUS_BORDER)
        entry_widget.focus_set()

    # ── 表单 ──
    form_frame = tk.Frame(top, bg=C_PM_BG)
    form_frame.place(x=form_x, y=form_y, width=form_w)

    for idx, (key, label_text, _use_vk) in enumerate(EDIT_FIELDS):
        if key not in btn:
            btn[key] = ''

        lbl = tk.Label(form_frame, text=label_text, bg=C_PM_BG, fg="#CCC",
                       font=(FF, 10), anchor="w")
        lbl.grid(row=idx, column=0, sticky="w", pady=4)

        e = tk.Entry(form_frame, font=(FF, 10), bg=C_GRAY, fg="white",
                     insertbackground="white", relief="flat", bd=5,
                     highlightthickness=2, highlightbackground=C_GRAY, highlightcolor=C_GRAY)
        e.grid(row=idx, column=1, sticky="ew", padx=(10, 0), pady=4)
        e.insert(0, btn[key])
        entries[key] = e

        # 点击输入框时设置焦点
        e.bind("<FocusIn>", lambda ev, ent=e: _set_focus(ent))

    form_frame.columnconfigure(1, weight=1)

    # 默认焦点到第一个可编辑字段
    first_key = EDIT_FIELDS[1][0] if len(EDIT_FIELDS) > 1 else EDIT_FIELDS[0][0]
    top.after(100, lambda: _set_focus(entries[first_key]))

    # ── 使用说明 ──
    help_y_base = form_y + len(EDIT_FIELDS) * 40 + 40
    help_text = (
        "💡 点击右侧按键添加到当前输入框\n"
        "多键用 + 连接，如 ctrl+a\n"
        "支持无限组合"
    )
    help_lbl = tk.Label(top, text=help_text, bg=C_PM_BG, fg="#999",
                        font=(FF, 9), anchor="w", justify="left")
    help_lbl.place(x=form_x, y=help_y_base, width=form_w)

    # ── 底部按钮 ──
    btn_h = 40
    btn_gap = 10
    total_w = form_w

    # Row 2 (bottom): Delete + Save
    row2_y = height - PADDING - btn_h
    half_w = (total_w - btn_gap) // 2

    # Delete
    del_x = PADDING
    rrect(c, del_x, row2_y, half_w, btn_h, BTN_R, fill="#6E1E1E", outline="", tags=("del", "del_bg"))
    c.create_text(del_x + half_w // 2, row2_y + btn_h // 2, text="删除",
                  font=(FF, FS), fill="white", tags=("del",))
    def _del_enter(e): c.itemconfigure("del_bg", fill="#8B2020")
    def _del_leave(e): c.itemconfigure("del_bg", fill="#6E1E1E")
    c.tag_bind("del", "<Enter>", _del_enter)
    c.tag_bind("del", "<Leave>", _del_leave)
    c.tag_bind("del", "<Button-1>", lambda e: [on_delete(btn), top.destroy()])

    # Save
    save_x = PADDING + half_w + btn_gap
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
    rrect(c, PADDING, copy_y, total_w, btn_h, BTN_R, fill=C_GRAY, outline="", tags=("copy", "copy_bg"))
    copy_cy = copy_y + btn_h // 2
    if ifont:
        icon_x = PADDING + total_w // 2 - 40
        text_x = icon_x + 20 + 12
        c.create_text(icon_x, copy_cy, text="\uE8C8",
                      font=(ifont, IS), fill="#E0E0E0", anchor="center", tags=("copy",))
        c.create_text(text_x, copy_cy, text="复制按钮",
                      font=(FF, FS), fill="#E0E0E0", anchor="w", tags=("copy",))
    else:
        c.create_text(PADDING + total_w // 2, copy_cy, text="复制按钮",
                      font=(FF, FS, "bold"), fill="#E0E0E0", tags=("copy",))
    def _copy_enter(e): c.itemconfigure("copy_bg", fill=C_GRAY_H)
    def _copy_leave(e): c.itemconfigure("copy_bg", fill=C_GRAY)
    c.tag_bind("copy", "<Enter>", _copy_enter)
    c.tag_bind("copy", "<Leave>", _copy_leave)
    c.tag_bind("copy", "<Button-1>", lambda e: [on_copy(btn), top.destroy()])

    # =================================================================
    #  RIGHT COLUMN: Key Palette (scrollable)
    # =================================================================
    right_x = PADDING + LEFT_W + DIVIDER + 10
    right_y = header_y + 5
    right_w = RIGHT_W - 20
    right_h = height - right_y - PADDING

    # Container frame
    right_container = tk.Frame(top, bg=C_PM_BG)
    right_container.place(x=right_x, y=right_y, width=right_w, height=right_h)

    # Scrollable canvas
    right_canvas = tk.Canvas(right_container, bg=C_PM_BG, highlightthickness=0)
    right_scrollbar = tk.Scrollbar(right_container, orient="vertical", command=right_canvas.yview)
    right_inner = tk.Frame(right_canvas, bg=C_PM_BG)

    right_inner.bind("<Configure>",
                     lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
    cw = right_canvas.create_window((0, 0), window=right_inner, anchor="nw")

    def _on_rc_configure(e):
        right_canvas.itemconfig(cw, width=e.width)
    right_canvas.bind("<Configure>", _on_rc_configure)
    right_canvas.configure(yscrollcommand=right_scrollbar.set)

    right_canvas.pack(side="left", fill="both", expand=True)
    right_scrollbar.pack(side="right", fill="y")

    # Mouse wheel for right panel
    def _on_mw(event):
        if right_canvas.yview() != (0.0, 1.0):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    def _bind_mw(event): right_canvas.bind_all("<MouseWheel>", _on_mw)
    def _unbind_mw(event): right_canvas.unbind_all("<MouseWheel>")
    right_container.bind('<Enter>', _bind_mw)
    right_container.bind('<Leave>', _unbind_mw)

    # ── 追加按键到焦点输入框 ──
    def _append_key(key_name):
        ent = focus_state["current_entry"]
        if ent is None or not ent.winfo_exists():
            return
        current = ent.get()
        if current:
            ent.insert(tk.END, f"+{key_name}")
        else:
            ent.insert(0, key_name)
        # 保持焦点
        ent.focus_set()

    # ── 绘制按键面板 ──
    TAG_MIN_W = 40   # 最低宽度 40px
    TAG_H = 40       # 高度 40px
    TAG_PAD_X = 10
    TAG_PAD_Y = 8
    TAG_FONT = (FF, 10)
    TAG_GAP = 6      # 同行按钮间距
    ROW_GAP = 20     # 同类按键行间距
    CAT_GAP = 40     # 不同类型间距

    is_first_cat = True
    for cat_name, keys in KEY_CATEGORIES:
        # 分类标题（首个无额外上间距，后续 40px）
        top_pad = 0 if is_first_cat else CAT_GAP
        is_first_cat = False

        cat_lbl = tk.Label(right_inner, text=f"── {cat_name} ──", bg=C_PM_BG,
                           fg=_C_CAT_LABEL, font=(FF, 10, "bold"), anchor="w")
        cat_lbl.pack(fill="x", padx=5, pady=(top_pad, 10))

        # 使用 Text widget 实现自动换行的 flow 布局
        flow_text = tk.Text(right_inner, bg=C_PM_BG, relief="flat", bd=0,
                            highlightthickness=0, cursor="arrow",
                            wrap="char", state="normal")
        flow_text.pack(fill="x", padx=5, pady=(0, 0))

        # 禁用文字输入（只做按钮容器）
        flow_text.configure(state="normal")

        for key_name in keys:
            tag_btn = tk.Frame(flow_text, bg=_C_TAG_BG, cursor="hand2",
                               height=TAG_H, padx=0, pady=0)
            tag_btn.pack_propagate(False)

            inner_lbl = tk.Label(tag_btn, text=key_name, bg=_C_TAG_BG, fg=_C_TAG_TEXT,
                                 font=TAG_FONT, cursor="hand2")
            inner_lbl.pack(expand=True, fill="both", padx=TAG_PAD_X, pady=0)

            # 计算宽度：至少 TAG_MIN_W，长文本自适应
            inner_lbl.update_idletasks()
            text_w = inner_lbl.winfo_reqwidth() + TAG_PAD_X * 2
            btn_w = max(TAG_MIN_W, text_w)
            tag_btn.configure(width=btn_w, height=TAG_H)

            flow_text.window_create("end", window=tag_btn,
                                    padx=TAG_GAP // 2, pady=ROW_GAP // 2)

            # Hover
            def _enter(ev, f=tag_btn, l=inner_lbl):
                f.configure(bg=_C_TAG_HOVER)
                l.configure(bg=_C_TAG_HOVER)
            def _leave(ev, f=tag_btn, l=inner_lbl):
                f.configure(bg=_C_TAG_BG)
                l.configure(bg=_C_TAG_BG)

            tag_btn.bind("<Enter>", _enter)
            tag_btn.bind("<Leave>", _leave)
            inner_lbl.bind("<Enter>", _enter)
            inner_lbl.bind("<Leave>", _leave)

            # Click
            tag_btn.bind("<Button-1>", lambda ev, k=key_name: _append_key(k))
            inner_lbl.bind("<Button-1>", lambda ev, k=key_name: _append_key(k))

        # 设置 Text 高度自适应内容
        flow_text.configure(state="disabled")
        flow_text.update_idletasks()
        # 计算需要的行数来设置高度
        flow_text.configure(height=1)  # 先设最小
        flow_text.update_idletasks()
        bbox = flow_text.bbox("end-1c")
        if bbox:
            needed_h = bbox[1] + bbox[3] + ROW_GAP
            flow_text.configure(height=1)
            # Use pixel height via place/config
            flow_text.pack_forget()
            flow_text.pack(fill="x", padx=5, pady=(0, 0))
            flow_text.configure(height=max(1, needed_h // 20))

    return top
