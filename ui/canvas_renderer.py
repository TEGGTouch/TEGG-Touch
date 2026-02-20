"""
TEGG Touch 蛋挞 辅助软件 - Canvas 绘制工具

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
    BTN_TYPE_CENTER_BAND, BTN_TYPE_WHEEL_SECTOR,
    WHEEL_INNER_RADIUS, WHEEL_OUTER_RADIUS,
    WHEEL_INNER_RADIUS_LARGE, WHEEL_OUTER_RADIUS_LARGE,
    WHEEL_GAP_PX,
    WHEEL_RING_INNER, WHEEL_RING_OUTER,
)

# 回中带专用配色
COLOR_CENTER_BAND = "#176F2C"        # 绿色边框/文字
COLOR_CENTER_BAND_BG = "#0A2E12"     # 深绿背景

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

COLOR_GRID_CENTER = "#444444"  # 中心十字线颜色（稍亮）

def draw_grid(canvas, width, height, grid_size=None):
    """在编辑模式背景上绘制 20% 半透明遮罩 + 从中心向外的网格线。"""
    from core.constants import GRID_SIZE
    gs = grid_size or GRID_SIZE

    cx = width // 2
    cy = height // 2

    # 20% 半透明黑色遮罩（stipple 模拟半透明，未填充像素穿透为透明色）
    canvas.create_rectangle(
        0, 0, width, height,
        fill="#000000", outline="", stipple="gray25", tags="grid",
    )

    # 网格线对齐中心：线在 cx ± n*gs 处
    # 竖线
    first_x = cx % gs
    for x in range(first_x, width + 1, gs):
        color = COLOR_GRID_CENTER if x == cx else COLOR_GRID
        w = 2 if x == cx else 1
        canvas.create_line(x, 0, x, height, fill=color, width=w, tags="grid")

    # 横线
    first_y = cy % gs
    for y in range(first_y, height + 1, gs):
        color = COLOR_GRID_CENTER if y == cy else COLOR_GRID
        w = 2 if y == cy else 1
        canvas.create_line(0, y, width, y, fill=color, width=w, tags="grid")


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

def draw_button(canvas, btn_data, index, show_resize=True, offset_x=0, offset_y=0):
    """绘制单个用户按钮。

    返回 (poly_id, text_id, resize_id) 以便后续引用。
    show_resize: 是否显示调整手柄（编辑模式True，运行模式False）。
    offset_x/offset_y: 逻辑坐标→屏幕坐标偏移 (screen_w//2, screen_h//2)。
    """
    tags_poly = f"btn_poly_{index}"
    tags_text = f"btn_text_{index}"
    tags_resize = f"btn_resize_{index}"

    # 逻辑坐标→屏幕坐标，并缓存到 btn 供 charge_bar 等使用
    sx = btn_data['x'] + offset_x
    sy = btn_data['y'] + offset_y
    btn_data['_sx'] = sx
    btn_data['_sy'] = sy

    # 计算视觉区域 (应用内边距)
    vx = sx + BTN_MARGIN
    vy = sy + BTN_MARGIN
    vw = btn_data['w'] - 2 * BTN_MARGIN
    vh = btn_data['h'] - 2 * BTN_MARGIN

    points = get_rounded_rect_points(vx, vy, vw, vh, BTN_RADIUS)

    # 判断是否为回中带按钮
    is_center_band = btn_data.get('type') == BTN_TYPE_CENTER_BAND

    if is_center_band:
        # 回中带：深绿背景 + 绿色边框
        poly = canvas.create_polygon(
            points, fill=COLOR_CENTER_BAND_BG, outline=COLOR_CENTER_BAND,
            width=2, smooth=True, tags=tags_poly,
        )
        # 两行文字：第一行 ⊕ 图标，第二行 "回中带"
        display_text = "\u2295\n\u56de\u4e2d\u5e26"
        text = canvas.create_text(
            sx + btn_data['w'] / 2,
            sy + btn_data['h'] / 2,
            text=display_text,
            font=FONT_NAME, fill=COLOR_CENTER_BAND, tags=tags_text,
            justify="center", width=vw,
        )
    else:
        poly = canvas.create_polygon(
            points, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER,
            width=2, smooth=True, tags=tags_poly,
        )
        # 默认只显示名称，使用 YaHei 字体
        display_text = _format_btn_name(btn_data.get('name', ''))
        text = canvas.create_text(
            sx + btn_data['w'] / 2,
            sy + btn_data['h'] / 2,
            text=display_text,
            font=FONT_NAME, fill=COLOR_TEXT, tags=tags_text,
            justify="center", width=vw,
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


def update_button_coords(canvas, btn, offset_x=0, offset_y=0):
    """更新单个按钮的视觉坐标（拖拽/缩放后调用）。
    offset_x/offset_y: 逻辑坐标→屏幕坐标偏移。
    """
    sx = btn['x'] + offset_x
    sy = btn['y'] + offset_y
    btn['_sx'] = sx
    btn['_sy'] = sy
    # 计算视觉区域 (应用内边距)
    vx = sx + BTN_MARGIN
    vy = sy + BTN_MARGIN
    vw = btn['w'] - 2 * BTN_MARGIN
    vh = btn['h'] - 2 * BTN_MARGIN

    points = get_rounded_rect_points(vx, vy, vw, vh, BTN_RADIUS)
    canvas.coords(btn['id_poly'], *points)
    # 文字保持居中
    canvas.coords(btn['id_text'], sx + btn['w'] / 2, sy + btn['h'] / 2)
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

    # 使用缓存的屏幕坐标 (_sx/_sy 在 draw_button 时设置)
    sx = btn.get('_sx', btn['x'])
    sy = btn.get('_sy', btn['y'])
    vx = sx + BTN_MARGIN
    vy = sy + BTN_MARGIN
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
    'active_xbutton1': ('#06B6D4', '#0891B2', '#000000'),   # 青色(侧键1)
    'active_xbutton2': ('#8B5CF6', '#7C3AED', '#000000'),   # 靛紫(侧键2)
}

# 状态对应的动作键名
STATE_TO_KEY = {
    'hover': 'hover',
    'active_left': 'lclick',
    'active_right': 'rclick',
    'active_middle': 'mclick',
    'active_xbutton1': 'xbutton1',
    'active_xbutton2': 'xbutton2',
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


# ─── 中心轮盘绘制 ────────────────────────────────────────────

# 轮盘扇面字体：与普通按钮统一，使用 FONT_NAME / FONT_KEY


def _gap_half_angle(radius, gap_px):
    """将像素间隙转换为该半径上对应的半角偏移（度）。
    gap_px 是两扇区边缘之间的总间隙宽度，half = gap_px/2。
    """
    half = gap_px / 2.0
    if radius <= half:
        return 0.0
    return math.degrees(math.asin(half / radius))


def _annular_sector_points(cx, cy, r_inner, r_outer,
                           center_angle_deg, sector_span_deg=45.0,
                           gap_px=WHEEL_GAP_PX, steps=20):
    """生成等宽间隙环形扇区的 polygon 顶点列表。

    通过在每个半径上独立计算角度偏移，实现内外圈间隙等宽 (gap_px 像素)。
    """
    half_span = sector_span_deg / 2.0
    # 外弧角度范围（外圈间隙小角度）
    outer_half_gap = _gap_half_angle(r_outer, gap_px)
    outer_start = center_angle_deg - half_span + outer_half_gap
    outer_end = center_angle_deg + half_span - outer_half_gap
    # 内弧角度范围（内圈间隙大角度）
    inner_half_gap = _gap_half_angle(r_inner, gap_px)
    inner_start = center_angle_deg - half_span + inner_half_gap
    inner_end = center_angle_deg + half_span - inner_half_gap

    points = []
    # 外弧：从 start 到 end
    for i in range(steps + 1):
        a = math.radians(outer_start + (outer_end - outer_start) * i / steps)
        points.append(cx + r_outer * math.cos(a))
        points.append(cy - r_outer * math.sin(a))  # y 轴翻转（屏幕坐标）
    # 内弧：从 end 到 start（反向闭合）
    for i in range(steps + 1):
        a = math.radians(inner_end - (inner_end - inner_start) * i / steps)
        points.append(cx + r_inner * math.cos(a))
        points.append(cy - r_inner * math.sin(a))
    return points


def draw_wheel_sectors(canvas, sectors, offset_x, offset_y,
                       r_inner=None, r_outer=None):
    """绘制中心轮盘的8个扇面。

    sectors: 8个扇区配置 list（每个含 angle, name, hover 等）
    offset_x/offset_y: 屏幕中心坐标 (screen_w//2, screen_h//2)
    r_inner/r_outer: 可选，覆盖默认内外圆半径（用于大/小版切换）
    
    为每个扇区存储 id_poly 和 id_text 到 sector dict 中。
    """
    cx, cy = offset_x, offset_y
    r_in = r_inner if r_inner is not None else WHEEL_INNER_RADIUS
    r_out = r_outer if r_outer is not None else WHEEL_OUTER_RADIUS

    for idx, sec in enumerate(sectors):
        center_angle = sec['angle']

        tag_poly = f"wheel_poly_{idx}"
        tag_text = f"wheel_text_{idx}"
        tag_all = f"wheel_sector_{idx}"

        points = _annular_sector_points(cx, cy, r_in, r_out, center_angle)

        poly_id = canvas.create_polygon(
            points, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER,
            width=2, tags=(tag_poly, tag_all, "wheel_all"),
        )

        # 文字位置：在内外圆中间半径、扇区中心角
        mid_r = (r_in + r_out) / 2
        mid_a = math.radians(center_angle)
        tx = cx + mid_r * math.cos(mid_a)
        ty = cy - mid_r * math.sin(mid_a)  # y 翻转

        # 只显示名称（与普通按钮一致）
        disp_name = sec.get('name', '')

        text_id = canvas.create_text(
            tx, ty, text=disp_name,
            font=FONT_NAME, fill=COLOR_TEXT,
            justify="center", tags=(tag_text, tag_all, "wheel_all"),
        )

        sec['id_poly'] = poly_id
        sec['id_text'] = text_id
        # 缓存屏幕坐标用于 hit test
        sec['_cx'] = cx
        sec['_cy'] = cy


def wheel_sector_hit_test(sectors, mx, my, offset_x, offset_y,
                          r_inner=None, r_outer=None):
    """判断鼠标 (mx, my) 在哪个轮盘扇区内。
    
    返回扇区索引 (0~7)，不在任何扇区内返回 -1。
    r_inner/r_outer: 可选，覆盖默认内外圆半径。
    """
    cx, cy = offset_x, offset_y
    dx = mx - cx
    dy = -(my - cy)  # 翻转 y 轴为数学坐标
    dist = math.sqrt(dx * dx + dy * dy)

    r_in = r_inner if r_inner is not None else WHEEL_INNER_RADIUS
    r_out = r_outer if r_outer is not None else WHEEL_OUTER_RADIUS

    if dist < r_in or dist > r_out:
        return -1

    # 计算角度 (0~360, 逆时针, 0=右)
    angle = math.degrees(math.atan2(dy, dx))
    if angle < 0:
        angle += 360

    # 在当前距离处计算像素间隙对应的半角偏移
    half_gap_deg = _gap_half_angle(dist, WHEEL_GAP_PX)

    for idx, sec in enumerate(sectors):
        center = sec['angle']
        a_start = center - 22.5 + half_gap_deg  # 45/2 = 22.5
        a_end = center + 22.5 - half_gap_deg

        # 规范化角度范围到 [0, 360)
        a_start_n = a_start % 360
        a_end_n = a_end % 360

        if a_start_n <= a_end_n:
            if a_start_n <= angle <= a_end_n:
                return idx
        else:
            # 跨越 0° 的情况 (例如 右: -22.5 ~ 22.5)
            if angle >= a_start_n or angle <= a_end_n:
                return idx

    return -1


def set_wheel_sector_visual(canvas, sector, state):
    """设置轮盘扇区的视觉状态（与普通按钮统一配色）。
    state: 'normal' | 'hover' | 'active_left' | ...
    """
    poly_id = sector.get('id_poly')
    text_id = sector.get('id_text')
    if not poly_id:
        return

    if state == 'normal':
        canvas.itemconfigure(poly_id, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER, width=2)
        disp_name = sector.get('name', '')
        if text_id:
            canvas.itemconfigure(text_id, text=disp_name, font=FONT_NAME, fill=COLOR_TEXT)
        return

    key_field = STATE_TO_KEY.get(state)
    key_val = sector.get(key_field, '')
    if not key_val:
        set_wheel_sector_visual(canvas, sector, 'normal')
        return

    if state in ACTION_STATE_COLORS:
        fill, outline, text_fill = ACTION_STATE_COLORS[state]
        canvas.itemconfigure(poly_id, fill=fill, outline=outline, width=3)
        disp = key_val if len(key_val) <= 3 else key_val[:2] + '..'
        if text_id:
            canvas.itemconfigure(text_id, text=disp, font=FONT_KEY, fill=text_fill)


# ─── 轮盘放射充能条 ──────────────────────────────────────────

def draw_wheel_charge_bar(canvas, sector, progress,
                          r_inner=None, r_outer=None):
    """绘制轮盘扇区的放射充能条：从内圆向外圆扩展。

    progress: 0.0~1.0  (触发充能=从圆心到外缘, 释放=反向)
    r_inner/r_outer: 可选，覆盖默认内外圆半径。
    用一个中间半径的环形扇面作为充能覆盖层。
    """
    progress = max(0.0, min(1.0, progress))
    charge_tag = f"wheel_charge_{id(sector)}"
    canvas.delete(charge_tag)

    if progress <= 0.01:
        return

    cx = sector.get('_cx', 0)
    cy = sector.get('_cy', 0)
    r_in = r_inner if r_inner is not None else WHEEL_INNER_RADIUS
    r_out = r_outer if r_outer is not None else WHEEL_OUTER_RADIUS

    center_angle = sector['angle']

    # 充能半径：从内圆到 inner + (outer-inner)*progress
    charge_r = r_in + (r_out - r_in) * progress

    points = _annular_sector_points(cx, cy, r_in + 2, max(r_in + 3, charge_r - 2),
                                    center_angle, gap_px=WHEEL_GAP_PX, steps=16)
    bar_id = canvas.create_polygon(
        points, fill=COLOR_CHARGE, outline="", tags=(charge_tag, "wheel_all"),
    )

    # 确保在 polygon 之上, text 之下
    poly_id = sector.get('id_poly')
    text_id = sector.get('id_text')
    if poly_id:
        canvas.tag_raise(charge_tag, poly_id)
    if text_id:
        canvas.tag_raise(text_id, charge_tag)

    # 充能时显示 hover 键值
    hover_key = sector.get('hover', '')
    if hover_key and text_id:
        disp = hover_key if len(hover_key) <= 3 else hover_key[:2] + '..'
        canvas.itemconfigure(text_id, text=disp, font=FONT_KEY, fill=COLOR_TEXT)

    # 边框变蓝
    if poly_id:
        canvas.itemconfigure(poly_id, outline=COLOR_CHARGE_BORDER, width=3)


def remove_wheel_charge_bar(canvas, sector):
    """移除轮盘扇区充能条，恢复默认外观。"""
    charge_tag = f"wheel_charge_{id(sector)}"
    canvas.delete(charge_tag)

    poly_id = sector.get('id_poly')
    if poly_id:
        canvas.itemconfigure(poly_id, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER, width=2)

    text_id = sector.get('id_text')
    if text_id:
        disp_name = sector.get('name', '')
        canvas.itemconfigure(text_id, text=disp_name, font=FONT_NAME, fill=COLOR_TEXT)


# ─── 中心圆环按钮（仅大圆盘模式） ────────────────────────────

def _ring_points(cx, cy, r, steps=48):
    """生成圆形多边形顶点。"""
    pts = []
    for i in range(steps):
        a = math.radians(360.0 * i / steps)
        pts.append(cx + r * math.cos(a))
        pts.append(cy - r * math.sin(a))
    return pts


def draw_wheel_center_ring(canvas, ring_data, offset_x, offset_y):
    """绘制中心圆环按钮（完整 360° 环形，无文字）。

    ring_data: dict（含 hover/lclick 等，和普通按钮一致）
    tag: "wheel_ring"
    """
    cx, cy = offset_x, offset_y
    r_in = WHEEL_RING_INNER
    r_out = WHEEL_RING_OUTER

    # 外圆 + 内圆组成环形 polygon（外顺时针 + 内逆时针 = 镂空环）
    outer = _ring_points(cx, cy, r_out, 48)
    inner = _ring_points(cx, cy, r_in, 48)
    inner.reverse()  # 逆向打孔

    # tkinter polygon 不支持孔洞, 用两个 oval 模拟
    # 外圆（填充 + 边框）
    poly_outer = canvas.create_oval(
        cx - r_out, cy - r_out, cx + r_out, cy + r_out,
        fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER,
        width=2, tags=("wheel_ring", "wheel_ring_outer", "wheel_all"),
    )
    # 内圆（用透明色挖洞）
    poly_inner = canvas.create_oval(
        cx - r_in, cy - r_in, cx + r_in, cy + r_in,
        fill=COLOR_TRANSPARENT, outline=COLOR_BTN_BORDER,
        width=2, tags=("wheel_ring", "wheel_ring_inner", "wheel_all"),
    )

    ring_data['id_poly'] = poly_outer
    ring_data['_id_inner'] = poly_inner
    ring_data['id_text'] = None  # 圆环无文字
    ring_data['_cx'] = cx
    ring_data['_cy'] = cy


def wheel_center_ring_hit_test(ring, mx, my, offset_x, offset_y):
    """判断鼠标 (mx, my) 是否在中心圆环区域内。

    ring: 圆环配置 dict（保留参数，与调用端一致）
    返回 True/False。
    """
    dx = mx - offset_x
    dy = my - offset_y
    dist = math.sqrt(dx * dx + dy * dy)
    return WHEEL_RING_INNER <= dist <= WHEEL_RING_OUTER


def set_wheel_center_ring_visual(canvas, ring, state):
    """设置圆环按钮视觉状态（不显示文字，仅变色）。

    state: 'normal' | 'hover' | 'active_left' | ...
    """
    poly_id = ring.get('id_poly')
    inner_id = ring.get('_id_inner')
    if not poly_id:
        return

    if state == 'normal':
        canvas.itemconfigure(poly_id, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER, width=2)
        if inner_id:
            canvas.itemconfigure(inner_id, outline=COLOR_BTN_BORDER, width=2)
        return

    key_field = STATE_TO_KEY.get(state)
    key_val = ring.get(key_field, '')
    if not key_val:
        set_wheel_center_ring_visual(canvas, ring, 'normal')
        return

    if state in ACTION_STATE_COLORS:
        fill, outline, _ = ACTION_STATE_COLORS[state]
        canvas.itemconfigure(poly_id, fill=fill, outline=outline, width=3)
        if inner_id:
            canvas.itemconfigure(inner_id, outline=outline, width=3)


def draw_wheel_center_ring_charge_bar(canvas, ring, progress):
    """绘制圆环充能条：从内圆向外圆扩展的环形充能。

    progress: 0.0~1.0
    """
    progress = max(0.0, min(1.0, progress))
    charge_tag = "wheel_ring_charge"
    canvas.delete(charge_tag)

    if progress <= 0.01:
        return

    cx = ring.get('_cx', 0)
    cy = ring.get('_cy', 0)

    # 充能圆环：从 RING_INNER 扩展到 RING_INNER + (OUTER-INNER)*progress
    charge_r = WHEEL_RING_INNER + (WHEEL_RING_OUTER - WHEEL_RING_INNER) * progress

    # 用 oval 画充能层 (比内圆略大, 比充能半径略小)
    r_in = WHEEL_RING_INNER + 2
    r_ch = max(r_in + 1, charge_r - 2)

    canvas.create_oval(
        cx - r_ch, cy - r_ch, cx + r_ch, cy + r_ch,
        fill=COLOR_CHARGE, outline="",
        tags=(charge_tag, "wheel_all"),
    )
    # 用透明色再挖出内圆
    canvas.create_oval(
        cx - r_in, cy - r_in, cx + r_in, cy + r_in,
        fill=COLOR_TRANSPARENT, outline="",
        tags=(charge_tag, "wheel_all"),
    )

    # 层级：充能在 poly 之上
    poly_id = ring.get('id_poly')
    inner_id = ring.get('_id_inner')
    if poly_id:
        canvas.tag_raise(charge_tag, poly_id)
    if inner_id:
        canvas.tag_raise(inner_id)

    # 边框变蓝
    if poly_id:
        canvas.itemconfigure(poly_id, outline=COLOR_CHARGE_BORDER, width=3)
    if inner_id:
        canvas.itemconfigure(inner_id, outline=COLOR_CHARGE_BORDER, width=3)


def remove_wheel_center_ring_charge_bar(canvas, ring):
    """移除圆环充能条，恢复默认。"""
    canvas.delete("wheel_ring_charge")

    poly_id = ring.get('id_poly')
    inner_id = ring.get('_id_inner')
    if poly_id:
        canvas.itemconfigure(poly_id, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER, width=2)
    if inner_id:
        canvas.itemconfigure(inner_id, outline=COLOR_BTN_BORDER, width=2)


# ─── 轮盘缩放切换按钮 ────────────────────────────────────────

# 图标码点 (Segoe Fluent Icons / Segoe MDL2 Assets)
_ICON_ZOOM_IN  = "\uE8A3"   # ZoomIn  放大镜+
_ICON_ZOOM_OUT = "\uE71F"   # ZoomOut 放大镜−
_ZOOM_BTN_SIZE = 30
_ZOOM_ICON_SIZE = 14

# 中心环开关按钮颜色
_RING_TOGGLE_COLOR_ON = "#005A9E"    # 蓝色（启用）— 与工具栏轮盘启用一致
_RING_TOGGLE_COLOR_OFF = "#666666"   # 灰色（禁用）

def draw_wheel_ring_toggle_button(canvas, offset_x, offset_y, is_visible=False):
    """在编辑模式下绘制中心环开关按钮（⭕ 图标）。

    位置：缩放按钮左侧 (cx+130, cy+165)，30×30px
    is_visible: True=中心环启用(蓝色), False=中心环禁用(灰色)
    tag: "wheel_ring_toggle_btn"
    """
    cx, cy = offset_x, offset_y
    x1 = cx + 130
    y1 = cy + 165
    s = _ZOOM_BTN_SIZE  # 30

    color = _RING_TOGGLE_COLOR_ON if is_visible else _RING_TOGGLE_COLOR_OFF

    # 圆角矩形背景
    pts = get_rounded_rect_points(x1, y1, s, s, BTN_RADIUS)
    canvas.create_polygon(
        pts, fill=color, outline="",
        smooth=True, tags="wheel_ring_toggle_btn",
    )

    # ⭕ 图标 (用简单圆形绘制)
    icon_r = 7
    icon_cx = x1 + s / 2
    icon_cy = y1 + s / 2
    canvas.create_oval(
        icon_cx - icon_r, icon_cy - icon_r,
        icon_cx + icon_r, icon_cy + icon_r,
        fill="", outline="#E0E0E0", width=2,
        tags="wheel_ring_toggle_btn",
    )


def draw_wheel_zoom_button(canvas, offset_x, offset_y, is_enlarged=False):
    """在编辑模式下绘制轮盘缩放切换按钮。

    按钮位置：中心偏移 (+165, +165) → (+195, +195)，30×30px
    纯灰色圆角矩形底 (COLOR_HANDLE)，无描边。
    图标使用 Segoe Fluent Icons / MDL2 Assets 字体 (与工具栏统一)。
    is_enlarged: True=当前为大版(显示缩小镜)，False=当前为小版(显示放大镜)
    tag: "wheel_zoom_btn"
    """
    from ui.widgets import icon_font

    cx, cy = offset_x, offset_y
    x1 = cx + 165
    y1 = cy + 165
    s = _ZOOM_BTN_SIZE

    # 圆角矩形背景 (纯灰色, 无描边, 与按钮体系统一圆角)
    pts = get_rounded_rect_points(x1, y1, s, s, BTN_RADIUS)
    canvas.create_polygon(
        pts, fill=COLOR_HANDLE, outline="",
        smooth=True, tags="wheel_zoom_btn",
    )

    # 图标 (Segoe Fluent Icons / MDL2 Assets，与工具栏一致)
    ifont = icon_font()
    icon_ch = _ICON_ZOOM_OUT if is_enlarged else _ICON_ZOOM_IN
    if ifont:
        canvas.create_text(
            x1 + s / 2, y1 + s / 2,
            text=icon_ch, font=(ifont, _ZOOM_ICON_SIZE),
            fill="#E0E0E0", tags="wheel_zoom_btn",
        )
    else:
        # fallback: 无图标字体时用简单文字
        canvas.create_text(
            x1 + s / 2, y1 + s / 2,
            text="−" if is_enlarged else "+",
            font=("Microsoft YaHei UI", 14, "bold"),
            fill="#E0E0E0", tags="wheel_zoom_btn",
        )


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
from core.constants import PT_ON, PT_OFF, PT_BLOCK

# 全局引用，防止 GC 回收
_cursor_photos = {}       # {mode: ImageTk.PhotoImage}
_current_cursor_mode = PT_ON  # 当前光标模式

_CURSOR_FILES = {
    PT_ON:    "cursor.png",
    PT_OFF:   "cursor_off.png",
    PT_BLOCK: "cursor_block.png",
}

def _get_cursor_image(mode=None):
    """加载指定模式的光标 PNG 图片，返回 ImageTk.PhotoImage。"""
    if mode is None:
        mode = _current_cursor_mode
    if mode not in _cursor_photos:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filename = _CURSOR_FILES.get(mode, "cursor.png")
        path = os.path.join(base, "assets", filename)
        try:
            img = Image.open(path).convert("RGBA")
            _cursor_photos[mode] = ImageTk.PhotoImage(img)
        except Exception:
            # 找不到对应光标文件，fallback 到默认
            if mode != PT_ON:
                return _get_cursor_image(PT_ON)
            pass
    return _cursor_photos.get(mode)


def set_cursor_mode(mode):
    """切换光标模式（PT_ON / PT_OFF / PT_BLOCK），下次绘制时生效。"""
    global _current_cursor_mode
    _current_cursor_mode = mode


def init_cursor(canvas):
    """初始化虚拟光标（使用自定义 PNG 图片）。"""
    photo = _get_cursor_image()
    if photo:
        # state='disabled' 确保光标图片不拦截鼠标事件，允许点击穿透到下方的按钮
        canvas.create_image(
            -100, -100, image=photo, anchor="nw", tags="v_cursor", state="disabled"
        )
        canvas.tag_raise("v_cursor")


def update_cursor(canvas, x, y):
    """更新虚拟光标位置（图片左上角对齐鼠标尖端）。
    同时检查光标模式是否需要切换图片。
    """
    items = canvas.find_withtag("v_cursor")
    if not items:
        init_cursor(canvas)
        items = canvas.find_withtag("v_cursor")
    
    # 检查是否需要切换光标图片
    if items:
        new_photo = _get_cursor_image()
        if new_photo:
            try:
                canvas.itemconfigure(items[0], image=new_photo)
            except Exception:
                pass
    
    canvas.coords("v_cursor", x, y)
    canvas.tag_raise("v_cursor")


def remove_cursor(canvas):
    """移除虚拟光标。"""
    canvas.delete("v_cursor")
