"""
FKB - button_editor.py
按钮编辑弹窗：左右两栏布局。
顶部通栏 tip → 左栏4区块 → 右栏按键面板。
"""

import tkinter as tk
import tkinter.font as tkFont

from core.constants import COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS
from ui.widgets import (
    FF, FS, IS, BTN_H, BTN_R, CLOSE_SIZE, CLOSE_M,
    C_GRAY, C_GRAY_H, C_AMBER, C_AMBER_D,
    C_PM_BG, C_CLOSE, C_CLOSE_H,
    icon_font, rrect, create_modal_overlay,
)

# ─── 操作颜色 ──────────────────────────────────────────────────
ACTION_COLORS = {
    'hover':     '#0284C7',   # 天蓝
    'lclick':    '#F59E0B',   # 琥珀
    'rclick':    '#10B981',   # 翠绿
    'mclick':    '#A855F7',   # 紫色
    'wheelup':   '#EC4899',   # 粉红
    'wheeldown': '#F43F5E',   # 玫瑰
}

# ─── 4 区块字段定义 ────────────────────────────────────────────
BLOCK_1 = [('name', '按钮名称', False)]
BLOCK_2 = [('hover', '悬停时', True)]
BLOCK_3 = [
    ('lclick',    '左键', True),
    ('rclick',    '右键', True),
    ('mclick',    '中键', True),
    ('wheelup',   '滚轮向上', True),
    ('wheeldown', '滚轮向下', True),
]
BLOCK_GAP = 40

# ─── 行布局常量 ────────────────────────────────────────────────
ROW_H = 50          # 每行固定高度
DOT_W = 20          # 色块列宽
LABEL_W = 70        # 标签列宽
INPUT_PAD = 10      # 标签和输入框间距
INPUT_H = 40        # TagInput / Entry 固定高度
INPUT_W_SHRINK = 40 # 输入框右侧缩进（右对齐留白）

# ─── 按键分类数据 ──────────────────────────────────────────────
KEY_CATEGORIES = [
    ("字母", [chr(c) for c in range(ord('a'), ord('z') + 1)]),
    ("数字", [str(i) for i in range(10)]),
    ("F键", [f"f{i}" for i in range(1, 13)]),
    ("方向键", ["up", "down", "left", "right"]),
    ("修饰键", ["ctrl", "shift", "alt"]),
    ("功能键", ["space", "enter", "esc", "tab", "backspace"]),
    ("标点符号", [",", ".", "/", ";", "'", "[", "]", "\\", "-", "=", "`"]),
    ("其他", ["home", "end", "pageup", "pagedown", "insert", "delete",
              "print screen", "scroll lock", "pause"]),
    ("小键盘", [f"num {i}" for i in range(10)] + ["num lock",
               "num *", "num /", "num -"]),
]

# ─── 颜色 ──────────────────────────────────────────────────────
_C_TAG_BG = "#404040"
_C_TAG_HOVER = "#555555"
_C_TAG_TEXT = "#E0E0E0"
_C_CAT_LABEL = "#888888"
_C_INPUT_BG = "#3A3A3A"


# ═══════════════════════════════════════════════════════════════
#  TagInput - 固定高度的 Tag 容器控件
# ═══════════════════════════════════════════════════════════════

class TagInput(tk.Frame):
    """Tag 输入控件，固定高度，点击面板添加 tag，Backspace 删除。"""

    def __init__(self, master, initial_value="", accent_color="#F59E0B", **kw):
        super().__init__(master, bg=_C_INPUT_BG, highlightthickness=2,
                         highlightbackground=C_GRAY, highlightcolor=C_GRAY,
                         cursor="xterm", **kw)
        self.tags: list[str] = []
        self._tag_widgets: list[tk.Label] = []
        self._accent = accent_color

        if initial_value:
            for part in initial_value.split("+"):
                part = part.strip()
                if part:
                    self.tags.append(part)

        # 内部容器，居中对齐
        self._inner = tk.Frame(self, bg=_C_INPUT_BG, cursor="xterm")
        self._inner.pack(fill="both", expand=True, padx=4, pady=0)

        self.bind("<Button-1>", self._on_click)
        self._inner.bind("<Button-1>", self._on_click)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Key>", self._on_key)
        self.configure(takefocus=True)
        self._render_tags()

    def _on_click(self, e):
        self.focus_set()

    def _on_focus_in(self, e):
        self.configure(highlightbackground=self._accent,
                       highlightcolor=self._accent)

    def _on_focus_out(self, e):
        self.configure(highlightbackground=C_GRAY, highlightcolor=C_GRAY)

    def _on_key(self, e):
        if e.keysym == "BackSpace" and self.tags:
            self.tags.pop()
            self._render_tags()
        return "break"

    def add_tag(self, key_name: str):
        self.tags.append(key_name)
        self._render_tags()

    def get_value(self) -> str:
        return "+".join(self.tags)

    def _render_tags(self):
        for w in self._tag_widgets:
            w.destroy()
        self._tag_widgets.clear()
        for tag_name in self.tags:
            lbl = tk.Label(self._inner, text=tag_name, bg=self._accent, fg="#FFF",
                           font=(FF, 9, "bold"), padx=6, pady=2, cursor="xterm")
            lbl.pack(side="left", padx=(0, 4), pady=0)
            lbl.bind("<Button-1>", lambda ev: self.focus_set())
            self._tag_widgets.append(lbl)


# ═══════════════════════════════════════════════════════════════
#  主函数
# ═══════════════════════════════════════════════════════════════

def open_button_editor(parent, btn, *, on_save, on_delete, on_copy, set_window_style):
    """打开按钮编辑弹窗。"""
    overlay = create_modal_overlay(parent)

    LEFT_W = 340
    RIGHT_W = 560
    PADDING = 20
    DIVIDER = 1
    width = LEFT_W + DIVIDER + RIGHT_W + PADDING * 2
    height = 780
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
    top.grab_set()
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
    c.tag_bind("close", "<Enter>", lambda e: c.itemconfigure("close_bg", fill=C_CLOSE_H))
    c.tag_bind("close", "<Leave>", lambda e: c.itemconfigure("close_bg", fill=C_CLOSE))
    c.tag_bind("close", "<Button-1>", lambda e: top.destroy())

    # ── 通栏 Tip（标题下方）──
    tip_y = 50
    tip_text = "💡 点击右侧按键添加到输入框 ｜ Backspace 删除 ｜ 支持无限组合"
    tip_lbl = tk.Label(top, text=tip_text, bg=C_PM_BG, fg="#777",
                       font=(FF, 9), anchor="w")
    tip_lbl.place(x=PADDING, y=tip_y, width=width - PADDING * 2)
    tip_lbl.lift()

    # ── 内容区起始 Y（tip 下方 40px）──
    content_y = tip_y + 20 + BLOCK_GAP   # ~110

    # ── 分隔线 ──
    div_x = PADDING + LEFT_W
    c.create_line(div_x, content_y - 10, div_x, height - PADDING, fill="#444", width=1)

    # =================================================================
    #  LEFT COLUMN: 4 Blocks (place-based, fixed row heights)
    # =================================================================
    form_x = PADDING
    form_w = LEFT_W - 10
    input_x = DOT_W + LABEL_W + INPUT_PAD   # 输入框统一起始 X
    input_w = form_w - input_x - INPUT_W_SHRINK  # 输入框宽度（右侧留白）

    focus_state = {"current_widget": None}
    fields = {}

    def _set_focus(widget):
        old = focus_state["current_widget"]
        if old and old != widget and old.winfo_exists():
            if isinstance(old, TagInput):
                old.configure(highlightbackground=C_GRAY, highlightcolor=C_GRAY)
            elif isinstance(old, tk.Entry):
                old.configure(highlightbackground=C_GRAY, highlightcolor=C_GRAY)
        focus_state["current_widget"] = widget
        if isinstance(widget, TagInput):
            widget.configure(highlightbackground=widget._accent,
                             highlightcolor=widget._accent)
        elif isinstance(widget, tk.Entry):
            widget.configure(highlightbackground=C_AMBER,
                             highlightcolor=C_AMBER)
        widget.focus_set()

    def _build_row(parent_frame, local_y, key, label_text, is_tag):
        """在 parent_frame 中用 place 构建一行，返回控件。"""
        if key not in btn:
            btn[key] = ''

        color = ACTION_COLORS.get(key)

        # 色块
        if color:
            dot = tk.Frame(parent_frame, bg=color, width=8, height=8)
            dot.place(x=4, y=local_y + (ROW_H - 8) // 2, width=8, height=8)

        # 标签
        lbl = tk.Label(parent_frame, text=label_text, bg=C_PM_BG, fg="#CCC",
                       font=(FF, 10), anchor="w")
        lbl.place(x=DOT_W, y=local_y, height=ROW_H)

        # 输入控件（固定高度 INPUT_H，垂直居中）
        wy = local_y + (ROW_H - INPUT_H) // 2

        if is_tag:
            ti = TagInput(parent_frame, initial_value=btn[key],
                          accent_color=color or C_AMBER)
            ti.place(x=input_x, y=wy, width=input_w, height=INPUT_H)
            ti.bind("<FocusIn>", lambda ev, w=ti: _set_focus(w))
            fields[key] = ti
        else:
            e = tk.Entry(parent_frame, font=(FF, 10), bg=C_GRAY, fg="white",
                         insertbackground="white", relief="flat", bd=5,
                         highlightthickness=2, highlightbackground=C_GRAY,
                         highlightcolor=C_GRAY)
            e.place(x=input_x, y=wy, width=input_w, height=INPUT_H)
            e.insert(0, btn[key])
            e.bind("<FocusIn>", lambda ev, w=e: _set_focus(w))
            fields[key] = e

    def _create_block(block_fields, abs_y):
        """创建一个区块，返回区块总高度。"""
        frame = tk.Frame(top, bg=C_PM_BG)
        block_h = len(block_fields) * ROW_H
        frame.place(x=form_x, y=abs_y, width=form_w, height=block_h)
        frame.lift()  # 确保在 Canvas 之上
        for i, (key, label_text, is_tag) in enumerate(block_fields):
            _build_row(frame, i * ROW_H, key, label_text, is_tag)
        return block_h

    cur_y = content_y

    # Block 1: 按钮名称
    h1 = _create_block(BLOCK_1, cur_y)
    cur_y += h1 + BLOCK_GAP

    # Block 2: 悬停
    h2 = _create_block(BLOCK_2, cur_y)
    cur_y += h2 + BLOCK_GAP

    # Block 3: 鼠标按键 + 滚轮
    h3 = _create_block(BLOCK_3, cur_y)

    # 默认焦点
    top.after(100, lambda: _set_focus(fields['hover']))

    # =================================================================
    #  Block 4: 底部按钮（复制 / 删除 / 保存）
    # =================================================================
    btn_h = 40
    btn_gap = 10
    total_w = form_w

    row2_y = height - PADDING - btn_h
    half_w = (total_w - btn_gap) // 2

    # 删除
    rrect(c, PADDING, row2_y, half_w, btn_h, BTN_R,
          fill="#6E1E1E", outline="", tags=("del", "del_bg"))
    c.create_text(PADDING + half_w // 2, row2_y + btn_h // 2, text="删除",
                  font=(FF, FS), fill="white", tags=("del",))
    c.tag_bind("del", "<Enter>", lambda e: c.itemconfigure("del_bg", fill="#8B2020"))
    c.tag_bind("del", "<Leave>", lambda e: c.itemconfigure("del_bg", fill="#6E1E1E"))
    c.tag_bind("del", "<Button-1>", lambda e: [on_delete(btn), top.destroy()])

    # 保存
    save_x = PADDING + half_w + btn_gap
    rrect(c, save_x, row2_y, half_w, btn_h, BTN_R,
          fill="#007A7A", outline="", tags=("save", "save_bg"))
    c.create_text(save_x + half_w // 2, row2_y + btn_h // 2, text="保存",
                  font=(FF, FS), fill="white", tags=("save",))
    c.tag_bind("save", "<Enter>", lambda e: c.itemconfigure("save_bg", fill="#009999"))
    c.tag_bind("save", "<Leave>", lambda e: c.itemconfigure("save_bg", fill="#007A7A"))

    def do_save(e=None):
        for k, widget in fields.items():
            if isinstance(widget, TagInput):
                btn[k] = widget.get_value()
            else:
                btn[k] = widget.get()
        on_save(btn)
        top.destroy()
    c.tag_bind("save", "<Button-1>", do_save)

    # 复制
    copy_y = row2_y - btn_gap - btn_h
    rrect(c, PADDING, copy_y, total_w, btn_h, BTN_R,
          fill=C_GRAY, outline="", tags=("copy", "copy_bg"))
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
    c.tag_bind("copy", "<Enter>", lambda e: c.itemconfigure("copy_bg", fill=C_GRAY_H))
    c.tag_bind("copy", "<Leave>", lambda e: c.itemconfigure("copy_bg", fill=C_GRAY))
    c.tag_bind("copy", "<Button-1>", lambda e: [on_copy(btn), top.destroy()])

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
    right_scrollbar = tk.Scrollbar(right_container, orient="vertical", command=right_canvas.yview)
    right_inner = tk.Frame(right_canvas, bg=C_PM_BG)

    right_inner.bind("<Configure>",
                     lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
    cw_id = right_canvas.create_window((0, 0), window=right_inner, anchor="nw")

    def _on_rc_configure(e):
        right_canvas.itemconfig(cw_id, width=e.width)
    right_canvas.bind("<Configure>", _on_rc_configure)
    right_canvas.configure(yscrollcommand=right_scrollbar.set)
    right_canvas.pack(side="left", fill="both", expand=True)
    right_scrollbar.pack(side="right", fill="y")

    def _on_mw(event):
        if right_canvas.yview() != (0.0, 1.0):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    right_container.bind('<Enter>', lambda e: right_canvas.bind_all("<MouseWheel>", _on_mw))
    right_container.bind('<Leave>', lambda e: right_canvas.unbind_all("<MouseWheel>"))

    # ── 追加按键 ──
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
