"""
TEGG Touch 辅助软件 - 主应用类

负责窗口管理、模式切换、事件分发。
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
)
# Update import to include profile functions
from core.config_manager import (
    load_config, save_config,
    init_profiles, load_profile, save_profile, set_active_profile
)
from ui.canvas_renderer import (
    draw_button, update_button_coords, set_button_visual_state,
    draw_control_ui, draw_floating_ball,
    init_cursor, update_cursor, remove_cursor,
    preview_button_transparency, draw_grid,
    draw_charge_bar, remove_charge_bar,
)
from ui.edit_panel import create_toolbar_window, destroy_toolbar_window, open_button_editor
from core.input_engine import trigger, is_key_pressed, install_wheel_hook, uninstall_wheel_hook, poll_wheel_events

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

        # 独立工具栏窗口（编辑模式时创建）
        self.toolbar_win = None

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
        """创建独立工具栏窗口。"""
        destroy_toolbar_window(self.toolbar_win)
        self.toolbar_win = create_toolbar_window(
            self.root, self.screen_w, self.screen_h,
            on_add=self.add_btn,
            on_run=self.to_run,
            on_export=self.export_config,
            on_import=self.import_config,
            on_quit=self.quit,
            transparency=self.transparency,
            on_alpha_change=self.set_alpha,
            on_switch_profile=self.switch_profile,
            on_edit_passthrough=self.toggle_edit_passthrough,
            edit_passthrough=self.edit_passthrough,
        )
        # 确保工具栏在主窗口之上
        if self.toolbar_win:
            self.toolbar_win.lift()
            self.toolbar_win.after(100, self.toolbar_win.lift)

    def _hide_toolbar(self):
        """销毁独立工具栏窗口。"""
        destroy_toolbar_window(self.toolbar_win)
        self.toolbar_win = None

    def setup_ui_mode(self):
        """根据 current_mode 设置界面。"""
        if self.current_mode == 'main':
            # === 编辑模式：全屏透明背景（只显示按钮+网格） ===
            self._hide_toolbar()  # 先清理
            self.root.overrideredirect(True)
            self.root.geometry(self.fullscreen_geo)
            self.root.attributes("-alpha", self.transparency)
            self.root.configure(bg=COLOR_TRANSPARENT)
            self.canvas.configure(bg=COLOR_TRANSPARENT)
            self.root.wm_attributes("-transparentcolor", COLOR_TRANSPARENT)
            self.set_window_style('normal')

            # 恢复系统光标 + 创建独立不透明工具栏
            self.root.config(cursor="")
            self._show_toolbar()
            remove_cursor(self.canvas)

            # 更新缓存
            self.win_x = 0
            self.win_y = 0
            self.win_w = self.screen_w
            self.win_h = self.screen_h

        elif self.current_mode == 'run':
            # === 运行模式：全屏透明穿透 ===
            self.save_config()  # 自动保存
            self._hide_toolbar()

            self.root.overrideredirect(True)
            self.root.geometry(self.fullscreen_geo)
            self.root.attributes("-alpha", self.transparency)
            self.root.configure(bg=COLOR_TRANSPARENT)
            self.canvas.configure(bg=COLOR_TRANSPARENT)
            self.root.wm_attributes("-transparentcolor", COLOR_TRANSPARENT)

            # 根据配置决定初始穿透状态
            if self.click_through:
                self.set_window_style('click_through')
            else:
                self.set_window_style('no_focus')

            # 隐藏系统光标（避免与虚拟光标重叠）
            self.root.config(cursor="none")
            init_cursor(self.canvas)

            # 更新缓存
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
        self.edit_passthrough = False  # 重置穿透开关
        # 恢复全屏
        self.root.geometry(self.fullscreen_geo)
        self.redraw_all()
        self.setup_ui_mode()

    def to_hide(self):
        """切换到隐藏(悬浮球)模式。"""
        self.is_hidden = True

        # 计算悬浮球位置
        tx = self.screen_w // 2 - 40
        ty = self.screen_h // 2 - 40
        if self.ball_x is not None and self.ball_y is not None:
            tx, ty = self.ball_x, self.ball_y

        self.root.geometry(f"80x80+{tx}+{ty}")
        self.redraw_all()
        self.set_window_style('no_focus')  # 悬浮球必须能点

    def to_show(self):
        """从悬浮球展开。"""
        # 记录球的位置
        self.ball_x = self.root.winfo_x()
        self.ball_y = self.root.winfo_y()

        self.is_hidden = False
        self.root.geometry(self.fullscreen_geo)
        self.redraw_all()
        self.setup_ui_mode()  # 恢复原来的模式(通常是run)

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

        # 绘制用户按钮
        show_resize = (self.current_mode == 'main')
        for idx, btn in enumerate(self.buttons):
            if btn.get('deleted'):
                continue
            poly, text, resize = draw_button(self.canvas, btn, idx, show_resize=show_resize)
            btn['id_poly'] = poly
            btn['id_text'] = text
            btn['id_resize'] = resize

            if self.current_mode == 'main':
                self.bind_edit_events(idx)

        # 绘制系统UI
        if self.current_mode == 'run':
            draw_control_ui(self.canvas, self.click_through)
            self.canvas.tag_bind("exit_btn_ui", "<Button-1>", lambda e: self.to_edit())
            self.canvas.tag_bind("hide_btn_ui", "<Button-1>", lambda e: self.to_hide())
            self.canvas.tag_bind("ct_btn_ui", "<Button-1>", lambda e: self.toggle_click_through())

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
            # 边界检查
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
        # 原始计算坐标
        raw_x = max(0, min(self.win_w - btn['w'], e.x - btn['w'] / 2))
        raw_y = max(0, min(self.win_h - btn['h'], e.y - btn['h'] / 2))

        # 网格吸附
        btn['x'] = round(raw_x / GRID_SIZE) * GRID_SIZE
        btn['y'] = round(raw_y / GRID_SIZE) * GRID_SIZE

        update_button_coords(self.canvas, btn)

    def on_btn_resize(self, e, idx):
        btn = self.buttons[idx]
        # 原始计算宽高
        raw_w = max(GRID_SIZE, e.x - btn['x'])
        raw_h = max(GRID_SIZE, e.y - btn['y'])

        # 网格吸附
        btn['w'] = round(raw_w / GRID_SIZE) * GRID_SIZE
        btn['h'] = round(raw_h / GRID_SIZE) * GRID_SIZE

        update_button_coords(self.canvas, btn)

    # ─── 核心循环 (Core Loop) ────────────────────────────────

    def update_loop(self):
        try:
            # 运行模式下的硬件检测
            if self.current_mode == 'run':
                # 0. 全局快捷键检测 (F12)
                if is_key_pressed('f12'):
                    self.to_edit()
                    # 避免按键重复触发，稍微延迟
                    time.sleep(0.3)
                    self.root.after(1, self.update_loop)
                    return

                # 1. 窗口置顶保活
                self.root.lift()

                # 2. 获取鼠标绝对/相对位置 (全屏下 rel = abs)
                abs_x, abs_y = self.root.winfo_pointerxy()
                rel_x = abs_x - self.win_x
                rel_y = abs_y - self.win_y

                # 3. 智能穿透判定 (仅当开启穿透模式时)
                if self.click_through and not self.is_hidden:
                    is_on_ui = False

                    # 检查系统按钮区域
                    if 10 <= rel_x <= 280 and 10 <= rel_y <= 50:
                        is_on_ui = True
                    else:
                        # 检查用户按钮
                        for btn in self.buttons:
                            if btn.get('deleted'):
                                continue
                            if (btn['x'] <= rel_x < btn['x'] + btn['w'] and
                                    btn['y'] <= rel_y < btn['y'] + btn['h']):
                                is_on_ui = True
                                break

                    # 状态切换
                    if is_on_ui and not self.is_window_solid:
                        self.set_window_style('no_focus')
                    elif not is_on_ui and self.is_window_solid:
                        self.set_window_style('click_through')

                # 4. 更新虚拟光标
                if not self.is_hidden and 0 <= rel_x <= self.win_w and 0 <= rel_y <= self.win_h:
                    update_cursor(self.canvas, rel_x, rel_y)
                else:
                    remove_cursor(self.canvas)

                # 5. 硬件按键状态检测
                left_down = (user32.GetAsyncKeyState(0x01) & 0x8000) != 0
                right_down = (user32.GetAsyncKeyState(0x02) & 0x8000) != 0
                middle_down = (user32.GetAsyncKeyState(0x04) & 0x8000) != 0

                # 6. 处理点击/悬浮逻辑
                if self.is_hidden:
                    self.handle_hidden_interaction(abs_x, abs_y, rel_x, rel_y, left_down)
                else:
                    self.handle_run_interaction(rel_x, rel_y, left_down, right_down, middle_down)

                # 7. 更新历史状态
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

    def handle_run_interaction(self, rel_x, rel_y, left_down, right_down, middle_down):
        """处理运行模式下的交互。"""
        now = time.time()

        # 系统按钮检测 (左键点击)
        if left_down and not self.left_was_down:
            if 10 <= rel_x <= 90 and 10 <= rel_y <= 45:
                self.to_edit()
                return
            if 100 <= rel_x <= 180 and 10 <= rel_y <= 45:
                self.to_hide()
                return
            if 190 <= rel_x <= 270 and 10 <= rel_y <= 45:
                self.toggle_click_through()
                return

        # ── 滚轮事件处理（硬件级钩子） ──
        wheel_events = poll_wheel_events()
        for direction, wx, wy in wheel_events:
            w_rel_x = wx - self.win_x
            w_rel_y = wy - self.win_y
            for btn in self.buttons:
                if btn.get('deleted'):
                    continue
                if (btn['x'] <= w_rel_x < btn['x'] + btn['w'] and
                        btn['y'] <= w_rel_y < btn['y'] + btn['h']):
                    key = btn.get('wheelup') if direction == 'up' else btn.get('wheeldown')
                    if key:
                        trigger(key, 'c')
                        # 视觉反馈 + 闪烁保护时间戳
                        wheel_state = 'active_wheelup' if direction == 'up' else 'active_wheeldown'
                        set_button_visual_state(self.canvas, btn, wheel_state)
                        btn['last_visual_state'] = wheel_state
                        btn['_wheel_flash_until'] = now + 0.15

        # 用户按钮检测
        for idx, btn in enumerate(self.buttons):
            if btn.get('deleted'):
                continue

            in_rect = (btn['x'] <= rel_x < btn['x'] + btn['w'] and
                       btn['y'] <= rel_y < btn['y'] + btn['h'])

            # 获取悬停延迟配置 (ms)
            hover_delay = btn.get('hover_delay', 0)

            # 滚轮闪烁保护：在闪烁期内跳过视觉状态更新
            if now < btn.get('_wheel_flash_until', 0):
                # 仍然处理 hover/click 触发逻辑，只是不覆盖颜色
                if in_rect:
                    # 悬停延迟逻辑（滚轮闪烁期间也需要）
                    if not btn.get('active_hover'):
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
                    if left_down and not self.left_was_down:
                        self.holding_btn_left = idx
                        trigger(btn['lclick'], 'p')
                    if right_down and not self.right_was_down:
                        self.holding_btn_right = idx
                        trigger(btn['rclick'], 'p')
                    if middle_down and not self.middle_was_down:
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
                    # 清除充能状态
                    if btn.get('_hover_enter_time') is not None:
                        btn['_hover_enter_time'] = None
                        btn['_hover_charged'] = False
                        if not btn.get('_hover_release_time'):
                            remove_charge_bar(self.canvas, btn)
                continue

            # 状态判定：hover 仅在 active_hover 为 True 时显示
            # 充能期间保持 normal，由 charge bar 提供视觉反馈
            target_state = 'normal'
            if in_rect:
                if btn.get('active_hover'):
                    target_state = 'hover'
                if left_down:
                    target_state = 'active_left'
                elif right_down:
                    target_state = 'active_right'
                elif middle_down:
                    target_state = 'active_middle'

            # 视觉更新 (仅当状态改变时)
            if btn.get('last_visual_state') != target_state:
                set_button_visual_state(self.canvas, btn, target_state)
                btn['last_visual_state'] = target_state

            # 触发逻辑
            release_delay = btn.get('hover_release_delay', 0)

            if in_rect:
                # ── 如果正在释放倒计时，鼠标重新进入：取消释放 ──
                if btn.get('_hover_release_time') is not None:
                    btn['_hover_release_time'] = None
                    remove_charge_bar(self.canvas, btn)
                    # active_hover 仍然为 True，恢复 hover 视觉
                    set_button_visual_state(self.canvas, btn, 'hover')
                    btn['last_visual_state'] = 'hover'

                # ── 悬停延迟触发 ──
                if not btn.get('active_hover'):
                    if hover_delay <= 0:
                        # 无延迟：立即触发
                        btn['active_hover'] = True
                        trigger(btn['hover'], 'p')
                    else:
                        # 有延迟：充能模式
                        if btn.get('_hover_enter_time') is None:
                            btn['_hover_enter_time'] = now
                            btn['_hover_charged'] = False

                        if not btn.get('_hover_charged'):
                            elapsed_ms = (now - btn['_hover_enter_time']) * 1000
                            progress = min(1.0, elapsed_ms / hover_delay)
                            draw_charge_bar(self.canvas, btn, progress)

                            if progress >= 1.0:
                                # 充能完成！触发 press
                                btn['_hover_charged'] = True
                                btn['active_hover'] = True
                                remove_charge_bar(self.canvas, btn)
                                trigger(btn['hover'], 'p')
                                # 立刻更新为 hover 视觉
                                set_button_visual_state(self.canvas, btn, 'hover')
                                btn['last_visual_state'] = 'hover'

                # ── 鼠标按键触发 ──
                if left_down and not self.left_was_down:
                    self.holding_btn_left = idx
                    trigger(btn['lclick'], 'p')
                if right_down and not self.right_was_down:
                    self.holding_btn_right = idx
                    trigger(btn['rclick'], 'p')
                if middle_down and not self.middle_was_down:
                    self.holding_btn_middle = idx
                    trigger(btn['mclick'], 'p')
            else:
                # 鼠标离开按钮
                if btn.get('active_hover'):
                    if release_delay <= 0:
                        # 无释放延迟：立即释放
                        btn['active_hover'] = False
                        btn['_hover_release_time'] = None
                        trigger(btn['hover'], 'r')
                    else:
                        # 有释放延迟：开始/继续释放倒计时
                        if btn.get('_hover_release_time') is None:
                            btn['_hover_release_time'] = now

                        elapsed_ms = (now - btn['_hover_release_time']) * 1000
                        progress = max(0.0, 1.0 - elapsed_ms / release_delay)

                        if progress <= 0:
                            # 释放倒计时完成
                            btn['active_hover'] = False
                            btn['_hover_release_time'] = None
                            remove_charge_bar(self.canvas, btn)
                            trigger(btn['hover'], 'r')
                            set_button_visual_state(self.canvas, btn, 'normal')
                            btn['last_visual_state'] = 'normal'
                        else:
                            # 仍在释放中：绘制反向充能条（100%→0%）
                            draw_charge_bar(self.canvas, btn, progress)

                # 清除触发充能状态（不清除释放状态）
                if btn.get('_hover_enter_time') is not None:
                    btn['_hover_enter_time'] = None
                    btn['_hover_charged'] = False
                    if not btn.get('_hover_release_time'):
                        remove_charge_bar(self.canvas, btn)

        # 释放逻辑
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

    def _find_empty_slot(self, w, h, start_x=0, start_y=0, scan='lr_tb'):
        """在网格上查找不与现有按钮重叠的空位。
        scan: 'lr_tb' = 左→右 再 上→下 (新建用)
              'tb_lr' = 上→下 再 左→右 (复制用, 从源位置开始)
        返回 (x, y) 或 None。
        """
        gs = GRID_SIZE
        max_x = self.screen_w - w
        max_y = self.screen_h - h
        occupied = [(b['x'], b['y'], b['w'], b['h'])
                    for b in self.buttons if not b.get('deleted')]

        def overlaps(nx, ny):
            for bx, by, bw, bh in occupied:
                if not (nx + w <= bx or nx >= bx + bw or ny + h <= by or ny >= by + bh):
                    return True
            return False

        if scan == 'lr_tb':
            for y in range(0, max_y + 1, gs):
                for x in range(0, max_x + 1, gs):
                    if not overlaps(x, y):
                        return (x, y)
        else:  # copy — 先右侧再下侧
            # 1. 同行右侧：y=start_y, x 从 start_x+w 向右
            for x in range(start_x + w, max_x + 1, gs):
                if not overlaps(x, start_y):
                    return (x, start_y)
            # 2. 同列下侧：x=start_x, y 从 start_y+h 向下
            for y in range(start_y + h, max_y + 1, gs):
                if not overlaps(start_x, y):
                    return (start_x, y)
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
        pos = self._find_empty_slot(w, h, scan='lr_tb')
        if pos:
            cx, cy = pos
        else:
            cx, cy = 0, 0  # 没有空位，在原点覆盖
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
            pos = self._find_empty_slot(w, h, start_x=src_btn['x'], start_y=src_btn['y'], scan='tb_lr')
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

    def toggle_click_through(self):
        self.click_through = not self.click_through
        self.redraw_all()
        if self.click_through:
            self.set_window_style('click_through')
        else:
            self.set_window_style('no_focus')

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
        self.root.destroy()
        sys.exit()
