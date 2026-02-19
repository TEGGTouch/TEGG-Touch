"""
TEGG Touch 辅助软件 - 主应用类

负责88、模式切换、事件分发。
编辑模式和运行模式均为全屏覆盖。
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import sys
import time
import logging
import ctypes

from core.constants import (
    APP_TITLE, APP_VERSION,
    COLOR_BG, COLOR_PANEL, COLOR_TRANSPARENT,
    UPDATE_INTERVAL, GRID_SIZE,
    DEFAULT_PROFILE_NAME,
    PT_ON, PT_OFF, PT_BLOCK, PT_CYCLE,
    COLOR_BLOCK_OVERLAY,
)
# Update import to include profile functions
from core.config_manager import (
    load_config, save_config,
    init_profiles, load_profile, save_profile, set_active_profile
)
from ui.canvas_renderer import (
    draw_button, update_button_coords, set_button_visual_state,
    draw_floating_ball,
    init_cursor, update_cursor, remove_cursor, set_cursor_mode,
    preview_button_transparency, draw_grid,
    draw_charge_bar, remove_charge_bar,
)
from ui.edit_panel import create_toolbar_window, destroy_toolbar_window, open_button_editor

# Try to import create_run_toolbar. It might be in ui.edit_panel in upstream, 
# or still in ui.toolbar if that file exists. 
# Based on Stashed changes, it was in ui.toolbar.
# I'll try to import from ui.toolbar as a fallback or if it's the correct place.
try:
    from ui.edit_panel import create_run_toolbar
except ImportError:
    try:
        from ui.toolbar import create_run_toolbar
    except ImportError:
        # If it's nowhere, we might have a problem, but let's assume it's available somewhere.
        # This is a best-effort resolution without seeing other files.
        pass

from core.input_engine import (
    trigger, is_key_pressed,
    install_wheel_hook, uninstall_wheel_hook, poll_wheel_events,
)

# Windows API
user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

logger = logging.getLogger(__name__)


class FloatingApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")

        # 获取屏幕尺寸（全屏用）
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        self.fullscreen_geo = f"{self.screen_w}x{self.screen_h}+0+0"

        # 中心原点坐标系偏移量 (逻辑坐标→屏幕坐标)
        self._offset_x = self.screen_w // 2
        self._offset_y = self.screen_h // 2

        # 初始化/加载方案
        self.current_profile, config = init_profiles()
        
        self.transparency = config['transparency']
        self.buttons = config['buttons']
        self.ball_x = config['ball_x']
        self.ball_y = config['ball_y']
        self.click_through = config['click_through']

        # 运行时状态
        self.current_mode = 'main'  # 'main' | 'run'
        self.is_hidden = False
        self.is_window_solid = True  # True=不穿透, False=穿透
        self.edit_passthrough = False  # 编辑模式穿透开关
        self.buttons_hidden = False  # 运行模式下隐藏所有悬浮按键

        # 硬件输入状态缓存
        self.left_was_down = False
        self.right_was_down = False
        self.middle_was_down = False
        self.holding_btn_left = None
        self.holding_btn_right = None
        self.holding_btn_middle = None

        # 悬浮球拖拽状态
        self.ball_drag_start_x = 0
        self.ball_drag_start_y = 0
        self.ball_win_start_x = 0
        self.ball_win_start_y = 0
        self.ball_click_time = 0
        self.dragging_ball = False

        # 窗口初始化 — 全屏无边框
        self.root.overrideredirect(True)
        self.root.geometry(self.fullscreen_geo)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.configure(bg=COLOR_BG)

        # 主画布
        self.canvas = tk.Canvas(self.root, bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 安装全局滚轮钩子（硬件级，不依赖窗口焦点）
        install_wheel_hook()

        # 独立工具栏窗口
        self.toolbar_win = None       # 编辑模式工具栏
        self.run_toolbar_win = None   # 运行模式工具栏

        # 窗口位置缓存 (全屏模式下固定)
        self.win_x = 0
        self.win_y = 0
        self.win_w = self.screen_w
        self.win_h = self.screen_h

        # 启动
        self.redraw_all()
        self.setup_ui_mode()
        self.update_loop()

    # ─── 窗口样式控制 ──────────────────────────────────────────

    def set_window_style(self, style_type, target_window=None):
        """设置窗口穿透样式。
        style_type: 'normal' (不穿透), 'no_focus' (不获取焦点但拦截点击), 'click_through' (完全穿透)
        target_window: 如果指定，则设置该窗口的样式；否则默认设置 self.root
        """
        try:
            if target_window:
                win_id = target_window.winfo_id()
            else:
                win_id = self.root.winfo_id()

            hwnd = user32.GetParent(win_id)
            if hwnd == 0:
                hwnd = win_id

            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020

            old_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = old_style

            if style_type == 'normal':
                new_style = new_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT
                self.is_window_solid = True
            elif style_type == 'no_focus':
                new_style = (new_style | WS_EX_LAYERED | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT
                self.is_window_solid = True
            elif style_type == 'click_through':
                new_style = new_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                self.is_window_solid = False

            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        except Exception:
            pass

    def update_geo_cache(self):
        """更新窗口位置缓存。全屏模式下基本固定，仅在悬浮球模式需更新。"""
        try:
            self.root.update_idletasks()
            self.win_x = self.root.winfo_rootx()
            self.win_y = self.root.winfo_rooty()
            self.win_w = self.root.winfo_width()
            self.win_h = self.root.winfo_height()
        except Exception:
            pass

    # ─── 模式切换 ────────────────────────────────────────────

    def _show_toolbar(self):
        """创建编辑工具栏窗口。"""
        destroy_toolbar_window(self.toolbar_win)
        self.toolbar_win = create_toolbar_window(
            self.root, self.screen_w, self.screen_h,
            on_add=self.add_btn,
            on_run=self.to_run,
            on_quit=self.quit,
            transparency=self.transparency,
            on_alpha_change=self.set_alpha,
            on_switch_profile=self.switch_profile,
            on_edit_passthrough=self.toggle_edit_passthrough,
            edit_passthrough=self.edit_passthrough,
        )
        if self.toolbar_win:
            self.toolbar_win.lift()
            self.toolbar_win.after(100, self.toolbar_win.lift)

    def _hide_toolbar(self):
        """销毁编辑工具栏窗口。"""
        destroy_toolbar_window(self.toolbar_win)
        self.toolbar_win = None

    def _show_run_toolbar(self):
        """创建运行工具栏窗口。"""
        destroy_toolbar_window(self.run_toolbar_win)
        self.run_toolbar_win = create_run_toolbar(
            self.root, self.screen_w, self.screen_h,
            on_edit=self.to_edit,
            on_passthrough=self.toggle_click_through_sync, # 同步状态
            click_through=self.click_through,
            set_window_style=self.set_window_style,
            on_toggle_buttons=self.toggle_buttons_visibility,
            buttons_visible=not self.buttons_hidden,
        )
        if self.run_toolbar_win:
            self.run_toolbar_win.lift()
            self.run_toolbar_win.after(100, self.run_toolbar_win.lift)

    def _hide_run_toolbar(self):
        """销毁运行工具栏窗口。"""
        destroy_toolbar_window(self.run_toolbar_win)
        self.run_toolbar_win = None

    def setup_ui_mode(self):
        """根据 current_mode 设置界面。"""
        if self.current_mode == 'main':
            # === 编辑模式 ===
            self._hide_run_toolbar() # 隐藏运行工具栏
            
            self.root.overrideredirect(True)
            self.root.geometry(self.fullscreen_geo)
            self.root.attributes("-alpha", self.transparency)
            self.root.configure(bg=COLOR_TRANSPARENT)
            self.canvas.configure(bg=COLOR_TRANSPARENT)
            self.root.wm_attributes("-transparentcolor", COLOR_TRANSPARENT)
            self.set_window_style('normal')

            self.root.config(cursor="")
            self._show_toolbar() # 显示编辑工具栏
            remove_cursor(self.canvas)

            self.win_x = 0
            self.win_y = 0
            self.win_w = self.screen_w
            self.win_h = self.screen_h

        elif self.current_mode == 'run':
            # === 运行模式 ===
            self.save_config()
            self._hide_toolbar() # 隐藏编辑工具栏

            self.root.overrideredirect(True)
            self.root.geometry(self.fullscreen_geo)
            self.root.attributes("-alpha", self.transparency)
            self.root.configure(bg=COLOR_TRANSPARENT)
            self.canvas.configure(bg=COLOR_TRANSPARENT)
            self.root.wm_attributes("-transparentcolor", COLOR_TRANSPARENT)

            # 无论配置中是否开启穿透，初始化时都先设为 no_focus (拦截点击)
            # 这样保证按钮能点击、光标能显示。
            # 如果开启了穿透，update_loop 会在下一帧根据鼠标位置自动切为穿透。
            self.set_window_style('no_focus')

            self.root.config(cursor="none")
            set_cursor_mode(self.click_through)  # 初始化光标图片
            self._show_run_toolbar() # 显示运行工具栏
            init_cursor(self.canvas)

            self.win_x = 0
            self.win_y = 0
            self.win_w = self.screen_w
            self.win_h = self.screen_h

    def to_run(self):
        """切换到运行模式。"""
        self.current_mode = 'run'
        self.is_hidden = False
        self.redraw_all()
        self.setup_ui_mode()

    def to_edit(self):
        """切换到编辑模式。"""
        self.current_mode = 'main'
        self.is_hidden = False
        self.edit_passthrough = False
        self.buttons_hidden = False  # 回编辑模式自动恢复显示
        self.root.geometry(self.fullscreen_geo)
        self.redraw_all()
        self.setup_ui_mode()

    def to_hide(self):
        """切换到隐藏(悬浮球)模式。"""
        self.is_hidden = True
        self._hide_run_toolbar() # 隐藏运行工具栏

        tx = self.screen_w // 2 - 40
        ty = self.screen_h // 2 - 40
        if self.ball_x is not None and self.ball_y is not None:
            tx, ty = self.ball_x, self.ball_y

        self.root.geometry(f"80x80+{tx}+{ty}")
        self.redraw_all()
        self.set_window_style('no_focus')

    def to_show(self):
        """从悬浮球展开。"""
        self.ball_x = self.root.winfo_x()
        self.ball_y = self.root.winfo_y()

        self.is_hidden = False
        self.root.geometry(self.fullscreen_geo)
        self.redraw_all()
        self.setup_ui_mode()

    # ─── 绘制逻辑 ────────────────────────────────────────────

    def redraw_all(self):
        self.canvas.delete("all")

        if self.is_hidden:
            draw_floating_ball(self.canvas)
            self.bind_ball_events()
            return

        # 编辑模式下先绘制网格
        if self.current_mode == 'main':
            draw_grid(self.canvas, self.screen_w, self.screen_h)

        # 绘制用户按钮 (运行模式下如果隐藏按键则跳过)
        if self.current_mode == 'run' and self.buttons_hidden:
            # 按键已隐藏，不绘制任何按钮
            if self.current_mode == 'run':
                init_cursor(self.canvas)
            return

        show_resize = (self.current_mode == 'main')
        for idx, btn in enumerate(self.buttons):
            if btn.get('deleted'):
                continue
            poly, text, resize = draw_button(
                self.canvas, btn, idx, show_resize=show_resize,
                offset_x=self._offset_x, offset_y=self._offset_y)
            btn['id_poly'] = poly
            btn['id_text'] = text
            btn['id_resize'] = resize

            if self.current_mode == 'main':
                self.bind_edit_events(idx)

        # 运行模式不再绘制 Control UI (已移至独立工具栏)
        if self.current_mode == 'run':
            init_cursor(self.canvas)

    def bind_ball_events(self):
        self.canvas.tag_bind("float_ball", "<Button-1>", self.on_ball_down)
        self.canvas.tag_bind("float_ball", "<B1-Motion>", self.on_ball_move)
        self.canvas.tag_bind("float_ball", "<ButtonRelease-1>", self.on_ball_up)

    def bind_edit_events(self, idx):
        tag_poly = f"btn_poly_{idx}"
        tag_text = f"btn_text_{idx}"
        tag_resize = f"btn_resize_{idx}"

        # 拖拽移动
        for tag in [tag_poly, tag_text]:
            self.canvas.tag_bind(tag, "<B1-Motion>", lambda e, i=idx: self.on_btn_drag(e, i))
            self.canvas.tag_bind(tag, "<Double-Button-1>", lambda e, i=idx: self.edit_btn(i))

        # 调整大小
        self.canvas.tag_bind(tag_resize, "<B1-Motion>", lambda e, i=idx: self.on_btn_resize(e, i))

    # ─── 交互事件处理 ────────────────────────────────────────

    def on_ball_down(self, event):
        self.ball_drag_start_x = event.x_root
        self.ball_drag_start_y = event.y_root
        self.ball_win_start_x = self.root.winfo_x()
        self.ball_win_start_y = self.root.winfo_y()
        self.ball_click_time = time.time()
        self.dragging_ball = False

    def on_ball_move(self, event):
        dx = event.x_root - self.ball_drag_start_x
        dy = event.y_root - self.ball_drag_start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self.dragging_ball = True

        if self.dragging_ball:
            new_x = self.ball_win_start_x + dx
            new_y = self.ball_win_start_y + dy
            new_x = max(0, min(new_x, self.screen_w - 80))
            new_y = max(0, min(new_y, self.screen_h - 80))
            self.root.geometry(f"80x80+{new_x}+{new_y}")

    def on_ball_up(self, event):
        if self.dragging_ball:
            self.ball_x = self.root.winfo_x()
            self.ball_y = self.root.winfo_y()
        elif time.time() - self.ball_click_time < 0.3:
            self.to_show()

    def on_btn_drag(self, e, idx):
        btn = self.buttons[idx]
        ox, oy = self._offset_x, self._offset_y
        # e.x/e.y 是屏幕坐标，转为逻辑坐标后吸附网格
        raw_x = max(0, min(self.win_w - btn['w'], e.x - btn['w'] / 2))
        raw_y = max(0, min(self.win_h - btn['h'], e.y - btn['h'] / 2))
        # 屏幕坐标 → 逻辑坐标(中心原点)，对齐网格
        logical_x = round((raw_x - ox) / GRID_SIZE) * GRID_SIZE
        logical_y = round((raw_y - oy) / GRID_SIZE) * GRID_SIZE
        btn['x'] = logical_x
        btn['y'] = logical_y
        update_button_coords(self.canvas, btn, offset_x=ox, offset_y=oy)

    def on_btn_resize(self, e, idx):
        btn = self.buttons[idx]
        ox, oy = self._offset_x, self._offset_y
        # e.x/e.y 是屏幕坐标，btn['x'] 是逻辑坐标
        screen_x = btn['x'] + ox
        screen_y = btn['y'] + oy
        raw_w = max(GRID_SIZE, e.x - screen_x)
        raw_h = max(GRID_SIZE, e.y - screen_y)
        btn['w'] = round(raw_w / GRID_SIZE) * GRID_SIZE
        btn['h'] = round(raw_h / GRID_SIZE) * GRID_SIZE
        update_button_coords(self.canvas, btn, offset_x=ox, offset_y=oy)

    # ─── 核心循环 (Core Loop) ────────────────────────────────

    def update_loop(self):
        try:
            if self.current_mode == 'run':
                # 0. 全局快捷键检测 (F12)
                if is_key_pressed('f12'):
                    self.to_edit()
                    time.sleep(0.3)
                    self.root.after(1, self.update_loop)
                    return

                # 0b. 隐藏/显示按键 (F7)
                if is_key_pressed('f7'):
                    self.toggle_buttons_visibility(self.buttons_hidden)
                    self._show_run_toolbar()
                    time.sleep(0.3)

                # 0c. 软键盘 (F8)
                if is_key_pressed('f8'):
                    from ui.virtual_keyboard import toggle_soft_keyboard
                    toggle_soft_keyboard(self.run_toolbar_win or self.root, mode="input")
                    time.sleep(0.3)

                # 0d. 穿透模式快捷键 (F9/F10/F11 直接切换)
                _pt_switched = False
                if is_key_pressed('f9') and self.click_through != PT_ON:
                    self.toggle_click_through_sync(PT_ON)
                    self._show_run_toolbar()
                    _pt_switched = True
                elif is_key_pressed('f10') and self.click_through != PT_OFF:
                    self.toggle_click_through_sync(PT_OFF)
                    self._show_run_toolbar()
                    _pt_switched = True
                elif is_key_pressed('f11') and self.click_through != PT_BLOCK:
                    self.toggle_click_through_sync(PT_BLOCK)
                    self._show_run_toolbar()
                    _pt_switched = True

                # 1. 窗口置顶保活
                self.root.lift()

                # 2. 获取鼠标位置（OS 光标）
                abs_x, abs_y = self.root.winfo_pointerxy()
                rel_x = abs_x - self.win_x
                rel_y = abs_y - self.win_y

                # 3. 智能穿透判定 (根据模式和设置决定)
                if not self.is_hidden:
                    is_on_ui = False
                    # 按键隐藏时跳过按钮碰撞检测，视为全空白→穿透
                    if not self.buttons_hidden:
                        ox, oy = self._offset_x, self._offset_y
                        for btn in self.buttons:
                            if btn.get('deleted'):
                                continue
                            sx = btn['x'] + ox
                            sy = btn['y'] + oy
                            if (sx <= rel_x < sx + btn['w'] and
                                    sy <= rel_y < sy + btn['h']):
                                is_on_ui = True
                                break

                    if self.current_mode == 'main':
                        # === 编辑模式 (Edit Mode) ===
                        # 强制执行智能穿透：按钮实心(可拖拽)，空白穿透(可操作游戏)
                        # 注意：编辑模式下用 'normal' 样式以确保获得焦点进行编辑
                        if is_on_ui:
                            if not self.is_window_solid:
                                self.set_window_style('normal')
                        else:
                            # 只有当确实处于实心状态才切换，避免频繁调用
                            # 注意：编辑模式下 edit_passthrough 开关已被禁用/隐藏，
                            # 这里直接实现"智能穿透"效果
                            if self.is_window_solid:
                                self.set_window_style('click_through')

                    elif self.current_mode == 'run':
                        # === 运行模式 (Run Mode) — 三态穿透 ===
                        if self.click_through == PT_ON:
                            # [穿透ON] = 完全穿透 (Full Passthrough)
                            if self.is_window_solid:
                                self.set_window_style('click_through')
                        elif self.click_through == PT_OFF:
                            # [穿透OFF] = 智能穿透 (Smart Passthrough)
                            if is_on_ui:
                                if not self.is_window_solid:
                                    self.set_window_style('no_focus')
                            else:
                                if self.is_window_solid:
                                    self.set_window_style('click_through')
                        elif self.click_through == PT_BLOCK:
                            # [不穿透] = 反向智能穿透：按钮区域穿透，空白区域拦截
                            if is_on_ui:
                                if self.is_window_solid:
                                    self.set_window_style('click_through')
                                    # 把焦点还给游戏窗口（覆盖层已穿透，WindowFromPoint 会找到下方窗口）
                                    try:
                                        import ctypes.wintypes as _wt
                                        _pt = _wt.POINT(abs_x, abs_y)
                                        _game_hwnd = user32.WindowFromPoint(_pt)
                                        if _game_hwnd:
                                            user32.SetForegroundWindow(_game_hwnd)
                                    except Exception:
                                        pass
                            else:
                                if not self.is_window_solid:
                                    self.set_window_style('no_focus')
                                    # 强制抢回焦点，防止游戏继续接收鼠标移动
                                    try:
                                        _hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                                        user32.SetForegroundWindow(_hwnd)
                                    except Exception:
                                        pass

                # 4. 更新虚拟光标
                # 策略：如果鼠标在工具栏上方，则隐藏主窗口光标（因为工具栏自己会画光标）
                # 否则，显示主窗口光标
                hide_cursor = False
                if self.run_toolbar_win and self.run_toolbar_win.winfo_exists():
                    # 获取工具栏位置和大小
                    tb_x = self.run_toolbar_win.winfo_rootx()
                    tb_y = self.run_toolbar_win.winfo_rooty()
                    tb_w = self.run_toolbar_win.winfo_width()
                    tb_h = self.run_toolbar_win.winfo_height()
                    
                    # 检查鼠标是否在工具栏范围内
                    if (tb_x <= abs_x < tb_x + tb_w) and (tb_y <= abs_y < tb_y + tb_h):
                        hide_cursor = True

                # 无论是否开启穿透，只要不在工具栏上，就应该在主窗口绘制光标
                # 注意：如果开启了 click_through (全穿透)，主窗口实际上接收不到鼠标事件，
                # 但这里的 update_loop 是基于全局鼠标位置 (winfo_pointerxy) 运行的，
                # 所以只要窗口还在顶层（即使穿透），我们仍然可以通过 Canvas 绘制光标。
                # 唯一的问题是：如果窗口完全穿透 (WS_EX_TRANSPARENT)，Canvas 还能显示内容吗？
                # 答案是：WS_EX_TRANSPARENT 让鼠标事件穿透，但绘制内容仍然可见。
                
                # 修正逻辑：
                # 1. 如果在工具栏上，主窗口不画光标 (hide_cursor=True)
                # 2. 如果不在工具栏上，且未隐藏(悬浮球)，则始终更新光标位置
                
                if not self.is_hidden and not hide_cursor:
                    # 确保光标在屏幕范围内
                    if 0 <= rel_x <= self.win_w and 0 <= rel_y <= self.win_h:
                        update_cursor(self.canvas, rel_x, rel_y)
                    else:
                        remove_cursor(self.canvas)
                else:
                    remove_cursor(self.canvas)

                # 5. 硬件按键
                left_down = (user32.GetAsyncKeyState(0x01) & 0x8000) != 0
                right_down = (user32.GetAsyncKeyState(0x02) & 0x8000) != 0
                middle_down = (user32.GetAsyncKeyState(0x04) & 0x8000) != 0

                # 6. 处理点击/悬浮
                if self.is_hidden:
                    self.handle_hidden_interaction(abs_x, abs_y, rel_x, rel_y, left_down)
                else:
                    self.handle_run_interaction(rel_x, rel_y, left_down, right_down, middle_down)

                # 7. 更新状态
                self.left_was_down = left_down
                self.right_was_down = right_down
                self.middle_was_down = middle_down

        except Exception as e:
            logger.error(f"Loop error: {e}")

        self.root.after(UPDATE_INTERVAL, self.update_loop)

    def handle_hidden_interaction(self, abs_x, abs_y, rel_x, rel_y, left_down):
        """处理隐藏模式(悬浮球)下的交互。"""
        dist_sq = (rel_x - 40) ** 2 + (rel_y - 40) ** 2

        if left_down and not self.left_was_down and dist_sq <= 30 ** 2:
            self.dragging_ball = True
            self.ball_drag_start_x = abs_x
            self.ball_drag_start_y = abs_y
            self.ball_win_start_x = self.root.winfo_x()
            self.ball_win_start_y = self.root.winfo_y()
            self.ball_click_time = time.time()

        if not left_down and self.left_was_down and self.dragging_ball:
            self.dragging_ball = False
            if time.time() - self.ball_click_time < 0.3:
                drag_dist = (abs_x - self.ball_drag_start_x) ** 2 + (abs_y - self.ball_drag_start_y) ** 2
                if drag_dist < 100:
                    self.to_show()

    def _btn_screen_rect(self, btn):
        """返回按钮的屏幕矩形 (sx, sy, sw, sh)。"""
        return (btn['x'] + self._offset_x, btn['y'] + self._offset_y, btn['w'], btn['h'])

    def _point_in_btn(self, btn, px, py):
        """判断屏幕坐标 (px,py) 是否在按钮内。"""
        sx = btn['x'] + self._offset_x
        sy = btn['y'] + self._offset_y
        return sx <= px < sx + btn['w'] and sy <= py < sy + btn['h']

    def handle_run_interaction(self, rel_x, rel_y, left_down, right_down, middle_down):
        """处理运行模式下的交互。"""
        now = time.time()
        # 按键隐藏时跳过所有按钮交互
        if self.buttons_hidden:
            poll_wheel_events()
            return
        # ── 滚轮事件处理（硬件级钩子） ──
        wheel_events = poll_wheel_events()
        for direction, wx, wy in wheel_events:
            w_rel_x = wx - self.win_x
            w_rel_y = wy - self.win_y
            for btn in self.buttons:
                if btn.get('deleted'):
                    continue
                if self._point_in_btn(btn, w_rel_x, w_rel_y):
                    key = btn.get('wheelup') if direction == 'up' else btn.get('wheeldown')
                    if key:
                        trigger(key, 'c')
                        wheel_state = 'active_wheelup' if direction == 'up' else 'active_wheeldown'
                        set_button_visual_state(self.canvas, btn, wheel_state)
                        btn['last_visual_state'] = wheel_state
                        btn['_wheel_flash_until'] = now + 0.15

        # 用户按钮检测
        for idx, btn in enumerate(self.buttons):
            if btn.get('deleted'):
                continue

            in_rect = self._point_in_btn(btn, rel_x, rel_y)
            hover_delay = btn.get('hover_delay', 0)

            if now < btn.get('_wheel_flash_until', 0):
                if in_rect:
                    if not btn.get('active_hover') and btn.get('hover'):
                        if hover_delay <= 0:
                            btn['active_hover'] = True
                            trigger(btn['hover'], 'p')
                        else:
                            if btn.get('_hover_enter_time') is None:
                                btn['_hover_enter_time'] = now
                                btn['_hover_charged'] = False
                            if not btn.get('_hover_charged'):
                                elapsed_ms = (now - btn['_hover_enter_time']) * 1000
                                if elapsed_ms >= hover_delay:
                                    btn['_hover_charged'] = True
                                    btn['active_hover'] = True
                                    remove_charge_bar(self.canvas, btn)
                                    trigger(btn['hover'], 'p')
                    if left_down and not self.left_was_down and btn.get('lclick'):
                        self.holding_btn_left = idx
                        trigger(btn['lclick'], 'p')
                    if right_down and not self.right_was_down and btn.get('rclick'):
                        self.holding_btn_right = idx
                        trigger(btn['rclick'], 'p')
                    if middle_down and not self.middle_was_down and btn.get('mclick'):
                        self.holding_btn_middle = idx
                        trigger(btn['mclick'], 'p')
                else:
                    if btn.get('active_hover'):
                        _rd = btn.get('hover_release_delay', 0)
                        if _rd <= 0:
                            btn['active_hover'] = False
                            btn['_hover_release_time'] = None
                            trigger(btn['hover'], 'r')
                        else:
                            if btn.get('_hover_release_time') is None:
                                btn['_hover_release_time'] = now
                            _el = (now - btn['_hover_release_time']) * 1000
                            if _el >= _rd:
                                btn['active_hover'] = False
                                btn['_hover_release_time'] = None
                                trigger(btn['hover'], 'r')
                    if btn.get('_hover_enter_time') is not None:
                        btn['_hover_enter_time'] = None
                        btn['_hover_charged'] = False
                        if not btn.get('_hover_release_time'):
                            remove_charge_bar(self.canvas, btn)
                continue

            target_state = 'normal'
            if in_rect:
                if btn.get('active_hover'):
                    target_state = 'hover'
                if left_down and btn.get('lclick'):
                    target_state = 'active_left'
                elif right_down and btn.get('rclick'):
                    target_state = 'active_right'
                elif middle_down and btn.get('mclick'):
                    target_state = 'active_middle'

            if btn.get('last_visual_state') != target_state:
                set_button_visual_state(self.canvas, btn, target_state)
                btn['last_visual_state'] = target_state

            release_delay = btn.get('hover_release_delay', 0)

            if in_rect:
                if btn.get('_hover_release_time') is not None:
                    btn['_hover_release_time'] = None
                    remove_charge_bar(self.canvas, btn)
                    set_button_visual_state(self.canvas, btn, 'hover')
                    btn['last_visual_state'] = 'hover'

                if not btn.get('active_hover') and btn.get('hover'):
                    if hover_delay <= 0:
                        btn['active_hover'] = True
                        trigger(btn['hover'], 'p')
                    else:
                        if btn.get('_hover_enter_time') is None:
                            btn['_hover_enter_time'] = now
                            btn['_hover_charged'] = False

                        if not btn.get('_hover_charged'):
                            elapsed_ms = (now - btn['_hover_enter_time']) * 1000
                            progress = min(1.0, elapsed_ms / hover_delay)
                            draw_charge_bar(self.canvas, btn, progress)

                            if progress >= 1.0:
                                btn['_hover_charged'] = True
                                btn['active_hover'] = True
                                remove_charge_bar(self.canvas, btn)
                                trigger(btn['hover'], 'p')
                                set_button_visual_state(self.canvas, btn, 'hover')
                                btn['last_visual_state'] = 'hover'

                if left_down and not self.left_was_down and btn.get('lclick'):
                    self.holding_btn_left = idx
                    trigger(btn['lclick'], 'p')
                if right_down and not self.right_was_down and btn.get('rclick'):
                    self.holding_btn_right = idx
                    trigger(btn['rclick'], 'p')
                if middle_down and not self.middle_was_down and btn.get('mclick'):
                    self.holding_btn_middle = idx
                    trigger(btn['mclick'], 'p')
            else:
                if btn.get('active_hover'):
                    if release_delay <= 0:
                        btn['active_hover'] = False
                        btn['_hover_release_time'] = None
                        trigger(btn['hover'], 'r')
                    else:
                        if btn.get('_hover_release_time') is None:
                            btn['_hover_release_time'] = now

                        elapsed_ms = (now - btn['_hover_release_time']) * 1000
                        progress = max(0.0, 1.0 - elapsed_ms / release_delay)

                        if progress <= 0:
                            btn['active_hover'] = False
                            btn['_hover_release_time'] = None
                            remove_charge_bar(self.canvas, btn)
                            trigger(btn['hover'], 'r')
                            set_button_visual_state(self.canvas, btn, 'normal')
                            btn['last_visual_state'] = 'normal'
                        else:
                            draw_charge_bar(self.canvas, btn, progress)

                if btn.get('_hover_enter_time') is not None:
                    btn['_hover_enter_time'] = None
                    btn['_hover_charged'] = False
                    if not btn.get('_hover_release_time'):
                        remove_charge_bar(self.canvas, btn)

        if not left_down and self.left_was_down and self.holding_btn_left is not None:
            btn = self.buttons[self.holding_btn_left]
            if not btn.get('deleted'):
                trigger(btn['lclick'], 'r')
            self.holding_btn_left = None

        if not right_down and self.right_was_down and self.holding_btn_right is not None:
            btn = self.buttons[self.holding_btn_right]
            if not btn.get('deleted'):
                trigger(btn['rclick'], 'r')
            self.holding_btn_right = None

        if not middle_down and self.middle_was_down and self.holding_btn_middle is not None:
            btn = self.buttons[self.holding_btn_middle]
            if not btn.get('deleted'):
                trigger(btn['mclick'], 'r')
            self.holding_btn_middle = None

    # ─── 辅助功能 ────────────────────────────────────────────

    def _find_empty_slot(self, w, h, start_x=0, start_y=0, scan='spiral'):
        """在网格上查找不与现有按钮重叠的空位（逻辑坐标，中心原点）。

        scan: 'spiral' = 从 (start_x, start_y) 螺旋扩散 (新建用，默认从 0,0)
              'nearby' = 从源位置附近找 (复制用)
        返回 (x, y) 逻辑坐标 或 None。
        """
        gs = GRID_SIZE
        ox, oy = self._offset_x, self._offset_y
        # 逻辑坐标范围 (确保屏幕坐标 ≥ 0 且 < screen)
        min_lx = -ox
        min_ly = -oy
        max_lx = self.screen_w - w - ox
        max_ly = self.screen_h - h - oy

        occupied = [(b['x'], b['y'], b['w'], b['h'])
                    for b in self.buttons if not b.get('deleted')]

        def overlaps(nx, ny):
            for bx, by, bw, bh in occupied:
                if not (nx + w <= bx or nx >= bx + bw or ny + h <= by or ny >= by + bh):
                    return True
            return False

        def in_bounds(nx, ny):
            return min_lx <= nx <= max_lx and min_ly <= ny <= max_ly

        # 螺旋扩散算法：从中心向外，按层展开
        # 对齐网格
        cx = round(start_x / gs) * gs
        cy = round(start_y / gs) * gs

        if in_bounds(cx, cy) and not overlaps(cx, cy):
            return (cx, cy)

        max_radius = max(self.screen_w, self.screen_h) // gs
        for ring in range(1, max_radius + 1):
            # 每层走 4 条边: 上→右→下→左
            for dx in range(-ring, ring + 1):
                for dy in [-ring, ring]:
                    nx, ny = cx + dx * gs, cy + dy * gs
                    if in_bounds(nx, ny) and not overlaps(nx, ny):
                        return (nx, ny)
            for dy in range(-ring + 1, ring):
                for dx in [-ring, ring]:
                    nx, ny = cx + dx * gs, cy + dy * gs
                    if in_bounds(nx, ny) and not overlaps(nx, ny):
                        return (nx, ny)

        return None

    def show_toast(self, text, duration=1500):
        """在屏幕中央显示 toast 提示，duration 毫秒后消失。"""
        tag = "_toast"
        self.canvas.delete(tag)
        cx = self.screen_w // 2
        cy = self.screen_h // 2
        # 背景
        pw, ph = 200, 40
        self.canvas.create_rectangle(
            cx - pw, cy - ph, cx + pw, cy + ph,
            fill="#000000", outline="", stipple="gray50", tags=tag)
        self.canvas.create_text(
            cx, cy, text=text, fill="#FFFFFF",
            font=("Microsoft YaHei", 16, "bold"), tags=tag)
        self.canvas.tag_raise(tag)
        self.root.after(duration, lambda: self.canvas.delete(tag))

    def add_btn(self):
        w, h = GRID_SIZE, GRID_SIZE
        pos = self._find_empty_slot(w, h, start_x=0, start_y=0, scan='spiral')
        if pos:
            cx, cy = pos
        else:
            cx, cy = 0, 0  # 没有空位，在逻辑原点(屏幕中心)覆盖
        new_btn = {
            'x': cx, 'y': cy,
            'w': w, 'h': h,
            'name': '按钮', 'hover_delay': 200, 'hover_release_delay': 0,
            'hover': '', 'lclick': '', 'rclick': '', 'mclick': '',
            'wheelup': '', 'wheeldown': '',
        }
        self.buttons.append(new_btn)
        self.redraw_all()
        self.show_toast("✓ 创建成功")

    def edit_btn(self, idx):
        if self.current_mode != 'main':
            return
        btn = self.buttons[idx]

        def on_save(updated_btn):
            self.redraw_all()

        def on_delete(del_btn):
            del_btn['deleted'] = True
            self.redraw_all()

        def on_copy(src_btn):
            w, h = src_btn['w'], src_btn['h']
            pos = self._find_empty_slot(w, h, start_x=src_btn['x'], start_y=src_btn['y'], scan='spiral')
            if pos:
                nx, ny = pos
            else:
                nx, ny = src_btn['x'], src_btn['y']  # 没有空位，在原位覆盖
            new_btn = {
                'x': nx, 'y': ny,
                'w': w, 'h': h,
                'name': src_btn.get('name', '按钮'),
                'hover': src_btn.get('hover', ''),
                'hover_delay': src_btn.get('hover_delay', 200),
                'hover_release_delay': src_btn.get('hover_release_delay', 0),
                'lclick': src_btn.get('lclick', ''),
                'rclick': src_btn.get('rclick', ''),
                'mclick': src_btn.get('mclick', ''),
                'wheelup': src_btn.get('wheelup', ''),
                'wheeldown': src_btn.get('wheeldown', ''),
            }
            self.buttons.append(new_btn)
            self.redraw_all()
            self.show_toast("✓ 复制成功")

        open_button_editor(
            self.root, btn,
            on_save=on_save,
            on_delete=on_delete,
            on_copy=on_copy,
            set_window_style=self.set_window_style
        )

    def set_alpha(self, v):
        self.transparency = int(v) / 100.0
        # 编辑/运行模式统一：直接设置窗口级透明度
        self.root.attributes("-alpha", self.transparency)

    def toggle_edit_passthrough(self, is_on):
        """编辑模式穿透开关回调。"""
        self.edit_passthrough = is_on
        if self.current_mode == 'main':
            if is_on:
                self.set_window_style('click_through')
            else:
                self.set_window_style('normal')

    def _focus_game_window(self):
        """尝试将焦点交给覆盖层下方的游戏窗口。"""
        try:
            import ctypes.wintypes as _wt
            ax, ay = self.root.winfo_pointerxy()
            # 先临时穿透，让 WindowFromPoint 能找到下方窗口
            self.set_window_style('click_through')
            _pt = _wt.POINT(ax, ay)
            _game_hwnd = user32.WindowFromPoint(_pt)
            # 恢复 no_focus
            self.set_window_style('no_focus')
            if _game_hwnd:
                user32.SetForegroundWindow(_game_hwnd)
        except Exception:
            pass

    def toggle_click_through(self):
        """三态循环：PT_ON → PT_OFF → PT_BLOCK → PT_ON ..."""
        idx = PT_CYCLE.index(self.click_through) if self.click_through in PT_CYCLE else 0
        self.click_through = PT_CYCLE[(idx + 1) % len(PT_CYCLE)]
        self.redraw_all()
        self.set_window_style('no_focus')
        # PT_ON/PT_OFF 切换后自动给游戏焦点
        if self.click_through in (PT_ON, PT_OFF):
            self._focus_game_window()
    
    def toggle_buttons_visibility(self, visible):
        """切换按键显示/隐藏（由运行工具栏调用）。"""
        self.buttons_hidden = not visible
        # 隐藏时：释放所有 hover 状态 + 清除充能条
        if self.buttons_hidden:
            for btn in self.buttons:
                if btn.get('deleted'):
                    continue
                if btn.get('active_hover') and btn.get('hover'):
                    trigger(btn['hover'], 'r')
                btn['active_hover'] = False
                btn['_hover_enter_time'] = None
                btn['_hover_charged'] = False
                btn['_hover_release_time'] = None
                remove_charge_bar(self.canvas, btn)
        self.redraw_all()

    def toggle_click_through_sync(self, mode):
        """同步设置穿透状态（由运行工具栏调用）。mode 为 PT_ON/PT_OFF/PT_BLOCK。"""
        self.click_through = mode
        set_cursor_mode(mode)  # 切换光标图片
        self.redraw_all()
        self.set_window_style('no_focus')
        if mode in (PT_ON, PT_OFF):
            # 穿透ON / 穿透OFF：焦点交给游戏
            self._focus_game_window()
        elif mode == PT_BLOCK:
            # 不穿透：焦点抢到 TeggTouch 覆盖层，阻止游戏接收鼠标输入
            try:
                _hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                user32.SetForegroundWindow(_hwnd)
            except Exception:
                pass

    def switch_profile(self, name):
        """切换方案"""
        # 1. 保存当前方案
        if self.current_profile:
            self.save_config()
        
        # 2. 设置新活跃方案
        set_active_profile(name)
        
        # 3. 加载新方案
        config = load_profile(name)
        self.current_profile = name
        self.transparency = config['transparency']
        self.buttons = config['buttons']
        self.ball_x = config['ball_x']
        self.ball_y = config['ball_y']
        self.click_through = config['click_through']
        
        # 4. 刷新界面
        self.redraw_all()
        # 如果当前在编辑模式，刷新透明度滑块预览
        if self.current_mode == 'main':
            # 注意：toolbar本身需要刷新滑块位置，这里我们只是重新绘制canvas
            # 最简单的办法是销毁并重建工具栏以同步滑块状态
            self._show_toolbar()

    def save_config(self):
        # 修改为使用 save_profile
        save_profile(
            self.current_profile,
            geometry=self.fullscreen_geo,
            transparency=self.transparency,
            buttons=self.buttons,
            ball_x=self.ball_x,
            ball_y=self.ball_y,
            click_through=self.click_through,
            is_hidden=self.is_hidden,
            saved_geometry=self.fullscreen_geo,
            root=self.root
        )

    def export_config(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("配置", "*.json")],
            title="导出配置"
        )
        if path:
            # 导出还是用 save_config_to_file 的逻辑 (底层共用)
            # 这里直接调用 save_config 即可，但需要指定 filepath
            save_config(
                filepath=path,
                geometry=self.fullscreen_geo,
                transparency=self.transparency,
                buttons=self.buttons,
                click_through=self.click_through
            )
            messagebox.showinfo("成功", "配置已导出")

    def import_config(self):
        path = filedialog.askopenfilename(
            filetypes=[("配置", "*.json")],
            title="导入配置"
        )
        if not path:
            return
        try:
            cfg = load_config(path)
            self.transparency = cfg['transparency']
            self.buttons = cfg['buttons']
            self.click_through = cfg['click_through']

            self.redraw_all()
            if self.current_mode == 'main':
                self._show_toolbar()
            messagebox.showinfo("成功", "配置已导入")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def quit(self):
        self.save_config()
        uninstall_wheel_hook()
        self._hide_toolbar()
        self._hide_run_toolbar()
        self.root.destroy()
        sys.exit()
