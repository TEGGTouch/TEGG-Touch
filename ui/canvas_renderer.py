"""
TEGG Touch 辅助软件 - Canvas 绘制工具

纯绘制函数，不持有状态，接收 canvas 实例作为参数。
"""

import math

from core.constants import (
    COLOR_BG, COLOR_TRANSPARENT, COLOR_BTN_BG, COLOR_BTN_BORDER, COLOR_TEXT,
    COLOR_ACTIVE, COLOR_HOVER,
    COLOR_SYS_BG, COLOR_SYS_BORDER, COLOR_SYS_TEXT,
    COLOR_BALL_CORE, COLOR_BALL_RING, COLOR_HANDLE,
    CHAMFER_SIZE, RESIZE_HANDLE_SIZE,
    BTN_MARGIN, BTN_RADIUS,
)

# ─── 字体配置 ────────────────────────────────────────────────
FONT_NAME = ("Microsoft YaHei UI", 10, "bold")
FONT_KEY  = ("Microsoft YaHei UI", 16, "bold")


# ─── 颜色混合工具 ────────────────────────────────────────────

def _hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

def blend_color(color, bg, alpha):
    """Blend `color` toward `bg` by `alpha` (0.0=invisible, 1.0=full)."""
    cr, cg, cb = _hex_to_rgb(color)
    br, bg_, bb = _hex_to_rgb(bg)
    return _rgb_to_hex(
        br + (cr - br) * alpha,
        bg_ + (cg - bg_) * alpha,
        bb + (cb - bb) * alpha,
    )


def preview_button_transparency(canvas, buttons, alpha):
    """Update button colors to simulate transparency preview in edit mode.
    alpha: 0.0~1.0 (the user-set runtime transparency).
    背景已透明，混合目标为 COLOR_TRANSPARENT（穿透色）。
    当 alpha≈0 时直接设为穿透色使按钮完全消失。
    """
    if alpha <= 0.01:
        # 完全透明：按钮变为穿透色（不可见）
        fill = outline = text_color = handle_color = COLOR_TRANSPARENT
    else:
        fill = blend_color(COLOR_BTN_BG, COLOR_TRANSPARENT, alpha)
        outline = blend_color(COLOR_BTN_BORDER, COLOR_TRANSPARENT, alpha)
        text_color = blend_color(COLOR_TEXT, COLOR_TRANSPARENT, alpha)
        handle_color = blend_color(COLOR_HANDLE, COLOR_TRANSPARENT, alpha)

    for idx, btn in enumerate(buttons):
        if btn.get('deleted'):
            continue
        poly_id = btn.get('id_poly')
        text_id = btn.get('id_text')
        resize_id = btn.get('id_resize')
        if poly_id:
            canvas.itemconfigure(poly_id, fill=fill, outline=outline)
        if text_id:
            canvas.itemconfigure(text_id, fill=text_color)
        if resize_id:
            canvas.itemconfigure(resize_id, fill=handle_color)


# ─── 网格绘制 ────────────────────────────────────────────────

COLOR_GRID = "#2A2A2A"  # 网格线颜色（暗灰，不干扰视觉）

def draw_grid(canvas, width, height, grid_size=None):
    """在编辑模式背景上绘制 20% 半透明遮罩 + 100px 网格线。"""
    from core.constants import GRID_SIZE
    gs = grid_size or GRID_SIZE

    # 20% 半透明黑色遮罩（stipple 模拟半透明，未填充像素穿透为透明色）
    canvas.create_rectangle(
        0, 0, width, height,
        fill="#000000", outline="", stipple="gray25", tags="grid",
    )

    # 竖线
    for x in range(0, width + 1, gs):
        canvas.create_line(x, 0, x, height, fill=COLOR_GRID, width=1, tags="grid")

    # 横线
    for y in range(0, height + 1, gs):
        canvas.create_line(0, y, width, y, fill=COLOR_GRID, width=1, tags="grid")


# ─── 几何工具 ────────────────────────────────────────────────

def get_rounded_rect_points(x, y, w, h, r=BTN_RADIUS):
    """生成圆角矩形的顶点坐标列表 (配合 smooth=True 使用)。"""
    return [
        x + r, y,
        x + w - r, y,
        x + w, y,
        x + w, y + r,
        x + w, y + h - r,
        x + w, y + h,
        x + w - r, y + h,
        x + r, y + h,
        x, y + h,
        x, y + h - r,
        x, y + r,
        x, y
    ]


def _format_btn_name(name):
    """格式化按钮名称：最多2行，过长截断。"""
    # 简单策略：如果超过8个字换行，超过16个字截断
    # 这只是一个粗略的估算，因为没有 font measure
    limit_per_line = 8
    if len(name) > limit_per_line * 2:
        return name[:limit_per_line * 2 - 1] + "…"
    if len(name) > limit_per_line:
        # 尝试在中间空格处换行，或者直接切分
        return name[:limit_per_line] + "\n" + name[limit_per_line:]
    return name


# ─── 用户按钮 ────────────────────────────────────────────────

def draw_button(canvas, btn_data, index, show_resize=True):
    """绘制单个用户按钮。

    返回 (poly_id, text_id, resize_id) 以便后续引用。
    show_resize: 是否显示调整手柄（编辑模式True，运行模式False）。
    """
    tags_poly = f"btn_poly_{index}"
    tags_text = f"btn_text_{index}"
    tags_resize = f"btn_resize_{index}"

    # 计算视觉区域 (应用内边距)
    vx = btn_data['x'] + BTN_MARGIN
    vy = btn_data['y'] + BTN_MARGIN
    vw = btn_data['w'] - 2 * BTN_MARGIN
    vh = btn_data['h'] - 2 * BTN_MARGIN

    points = get_rounded_rect_points(vx, vy, vw, vh, BTN_RADIUS)

    poly = canvas.create_polygon(
        points, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER,
        width=2, smooth=True, tags=tags_poly,
    )
    
    # 默认只显示名称，使用 YaHei 字体
    display_text = _format_btn_name(btn_data.get('name', ''))
    
    text = canvas.create_text(
        btn_data['x'] + btn_data['w'] / 2,
        btn_data['y'] + btn_data['h'] / 2,
        text=display_text,
        font=FONT_NAME, fill=COLOR_TEXT, tags=tags_text,
        justify="center", width=vw  # 辅助换行
    )

    # 调整手柄 (仅编辑模式显示)
    resize_handle = None
    if show_resize:
        rx = vx + vw
        ry = vy + vh
        rs = RESIZE_HANDLE_SIZE
        
        # 直角三角形：右下角为直角
        resize_handle = canvas.create_polygon(
            rx - rs, ry,
            rx, ry - rs,
            rx, ry,
            fill=COLOR_HANDLE, outline="", width=0, tags=tags_resize,
        )

    return poly, text, resize_handle


def update_button_coords(canvas, btn):
    """更新单个按钮的视觉坐标（拖拽/缩放后调用）。"""
    # 计算视觉区域 (应用内边距)
    vx = btn['x'] + BTN_MARGIN
    vy = btn['y'] + BTN_MARGIN
    vw = btn['w'] - 2 * BTN_MARGIN
    vh = btn['h'] - 2 * BTN_MARGIN

    points = get_rounded_rect_points(vx, vy, vw, vh, BTN_RADIUS)
    canvas.coords(btn['id_poly'], *points)
    # 文字保持居中
    canvas.coords(btn['id_text'], btn['x'] + btn['w'] / 2, btn['y'] + btn['h'] / 2)
    # 更新文字换行宽度
    canvas.itemconfigure(btn['id_text'], width=vw)

    if btn.get('id_resize'):
        rs = RESIZE_HANDLE_SIZE
        rx = vx + vw
        ry = vy + vh
        # 更新三角形手柄坐标 (3个顶点: 左下, 右上, 右下)
        canvas.coords(btn['id_resize'], rx - rs, ry, rx, ry - rs, rx, ry)


# ─── 悬停充能条 ──────────────────────────────────────────────

COLOR_CHARGE = '#0284C7'       # 充能条蓝色
COLOR_CHARGE_BORDER = '#0284C7'  # 充能时边框蓝色


def draw_charge_bar(canvas, btn, progress):
    """绘制/更新悬停充能进度条。

    progress: 0.0 ~ 1.0，从左到右填充蓝色。
    充能条绘制在按钮 polygon 之上、文字之下。
    同时将边框设为蓝色。
    """
    progress = max(0.0, min(1.0, progress))

    vx = btn['x'] + BTN_MARGIN
    vy = btn['y'] + BTN_MARGIN
    vw = btn['w'] - 2 * BTN_MARGIN
    vh = btn['h'] - 2 * BTN_MARGIN

    # 充能条矩形：从左边缘到 progress 位置
    bar_w = int(vw * progress)
    if bar_w < 1:
        bar_w = 1

    charge_tag = f"charge_{id(btn)}"

    # 删除旧的充能条
    canvas.delete(charge_tag)

    if bar_w > 0:
        # 绘制充能条矩形（在 polygon 之上）
        bar_id = canvas.create_rectangle(
            vx + 2, vy + 2, vx + bar_w - 2, vy + vh - 2,
            fill=COLOR_CHARGE, outline="", tags=charge_tag,
        )
        btn['id_charge'] = bar_id

        # 确保充能条在 polygon 之上，文字之下
        poly_id = btn.get('id_poly')
        text_id = btn.get('id_text')
        if poly_id:
            canvas.tag_raise(charge_tag, poly_id)
        if text_id:
            canvas.tag_raise(text_id, charge_tag)
    
    # 充能时：显示 Hover 键值（居中，大字体）
    hover_key = btn.get('hover', '')
    if hover_key and text_id:
        # 截断过长的键值显示
        disp = hover_key if len(hover_key) <= 3 else hover_key[:2] + '..'
        canvas.itemconfigure(text_id, text=disp, font=FONT_KEY, fill=COLOR_TEXT)

    # 边框变蓝
    poly_id = btn.get('id_poly')
    if poly_id:
        canvas.itemconfigure(poly_id, outline=COLOR_CHARGE_BORDER, width=3)


def remove_charge_bar(canvas, btn):
    """移除充能条并恢复默认边框。"""
    charge_tag = f"charge_{id(btn)}"
    canvas.delete(charge_tag)
    btn['id_charge'] = None

    # 恢复默认外观
    poly_id = btn.get('id_poly')
    if poly_id:
        canvas.itemconfigure(poly_id, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER, width=2)
    
    # 恢复显示名称
    text_id = btn.get('id_text')
    if text_id:
        display_text = _format_btn_name(btn.get('name', ''))
        canvas.itemconfigure(text_id, text=display_text, font=FONT_NAME, fill=COLOR_TEXT)


# ─── 运行时操作配色 ──────────────────────────────────────────

ACTION_STATE_COLORS = {
    # state           → (fill,      outline,    text)
    'hover':           ('#0284C7', '#026AA2', '#000000'),   # 天蓝
    'active_left':     ('#F59E0B', '#D97706', '#000000'),   # 琥珀
    'active_right':    ('#10B981', '#059669', '#000000'),   # 翠绿
    'active_middle':   ('#A855F7', '#9333EA', '#000000'),   # 紫色
    'active_wheelup':  ('#EC4899', '#DB2777', '#000000'),   # 粉红
    'active_wheeldown':('#F43F5E', '#E11D48', '#000000'),   # 玫瑰
}

# 状态对应的动作键名
STATE_TO_KEY = {
    'hover': 'hover',
    'active_left': 'lclick',
    'active_right': 'rclick',
    'active_middle': 'mclick',
    'active_wheelup': 'wheelup',
    'active_wheeldown': 'wheeldown',
}

def set_button_visual_state(canvas, btn, state):
    """设置按钮的视觉状态。

    state: 'normal' | 'hover' | 'active_left' ...
    """
    text_id = btn.get('id_text')
    poly_id = btn.get('id_poly')

    if state == 'normal':
        # 恢复默认
        canvas.itemconfigure(poly_id, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER, width=2)
        display_text = _format_btn_name(btn.get('name', ''))
        canvas.itemconfigure(text_id, text=display_text, font=FONT_NAME, fill=COLOR_TEXT)
        return

    # 检查该状态是否有配置键值
    key_field = STATE_TO_KEY.get(state)
    key_val = btn.get(key_field, '')

    if not key_val:
        # 如果没有配置键值，保持原样（即 normal 样式，不变色不显字）
        # 这里直接返回，不做任何视觉变更
        # 但为了保证一致性，可能需要强制设回 normal？
        # 用户需求：没有配置 -> 不会变色 也不会出键值字符
        # 如果上一个状态是 active，现在变成了另一种 active 但没键值，应该回退到 normal
        # 但 app.py 逻辑通常是 normal -> active -> normal
        # 这里简单起见，如果无键值，则执行 normal 逻辑覆盖回去
        set_button_visual_state(canvas, btn, 'normal')
        return

    if state in ACTION_STATE_COLORS:
        fill, outline, text_fill = ACTION_STATE_COLORS[state]
        canvas.itemconfigure(poly_id, fill=fill, outline=outline, width=3)
        
        # 显示键值 (大字体，居中)
        disp = key_val if len(key_val) <= 3 else key_val[:2] + '..'
        canvas.itemconfigure(text_id, text=disp, font=FONT_KEY, fill=text_fill)


# ─── 系统按钮 ────────────────────────────────────────────────
# (系统按钮逻辑已移至 ui/toolbar.py 的独立工具栏中)


# ─── 悬浮球 ──────────────────────────────────────────────────

def draw_floating_ball(canvas):
    """绘制悬浮球（隐藏模式）。"""
    cx, cy = 40, 40
    r = 25
    points = []
    for i in range(6):
        angle_rad = math.radians(60 * i - 30)
        points.append(cx + r * math.cos(angle_rad))
        points.append(cy + r * math.sin(angle_rad))

    canvas.create_polygon(
        points, fill=COLOR_BG, outline=COLOR_BALL_RING,
        width=3, tags="float_ball",
    )
    canvas.create_oval(
        cx - 10, cy - 10, cx + 10, cy + 10,
        fill=COLOR_BALL_CORE, outline="white", width=2, tags="float_ball",
    )
    canvas.create_text(
        cx, cy + 32, text="展开", fill=COLOR_TEXT,
        font=("Microsoft YaHei UI", 8, "bold"), tags="float_ball",
    )


# ─── 虚拟光标 ────────────────────────────────────────────────

import os
from PIL import Image, ImageTk

# 全局引用，防止 GC 回收
_cursor_photo = None
_cursor_freeze_photo = None
_current_cursor_mode = 'normal'  # 'normal' | 'freeze'

def _get_cursor_image():
    """加载普通光标 PNG 图片，返回 ImageTk.PhotoImage。"""
    global _cursor_photo
    if _cursor_photo is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "assets", "cursor.png")
        try:
            img = Image.open(path).convert("RGBA")
            _cursor_photo = ImageTk.PhotoImage(img)
        except Exception:
            pass # ignore missing cursor
    return _cursor_photo

def _get_freeze_cursor_image():
    """加载冻结模式光标 PNG 图片，返回 ImageTk.PhotoImage。"""
    global _cursor_freeze_photo
    if _cursor_freeze_photo is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "assets", "cursor_freeze.png")
        img = Image.open(path).convert("RGBA")
        _cursor_freeze_photo = ImageTk.PhotoImage(img)
    return _cursor_freeze_photo

def init_cursor(canvas):
    """初始化虚拟光标（使用自定义 PNG 图片）。"""
    global _current_cursor_mode
    _current_cursor_mode = 'normal'
    photo = _get_cursor_image()
    if photo:
        # state='disabled' 确保光标图片不拦截鼠标事件，允许点击穿透到下方的按钮
        canvas.create_image(
            -100, -100, image=photo, anchor="nw", tags="v_cursor", state="disabled"
        )
        canvas.tag_raise("v_cursor")


def switch_cursor_mode(canvas, freeze: bool):
    """切换虚拟光标图片：freeze=True 用冻结图标，False 用普通图标。"""
    global _current_cursor_mode
    new_mode = 'freeze' if freeze else 'normal'
    if new_mode == _current_cursor_mode:
        return
    _current_cursor_mode = new_mode
    photo = _get_freeze_cursor_image() if freeze else _get_cursor_image()
    canvas.itemconfigure("v_cursor", image=photo)
    canvas.tag_raise("v_cursor")


def update_cursor(canvas, x, y):
    """更新虚拟光标位置（图片左上角对齐鼠标尖端）。"""
    if not canvas.find_withtag("v_cursor"):
        init_cursor(canvas)
    canvas.coords("v_cursor", x, y)
    canvas.tag_raise("v_cursor")


def remove_cursor(canvas):
    """移除虚拟光标。"""
    global _current_cursor_mode
    _current_cursor_mode = 'normal'
    canvas.delete("v_cursor")
