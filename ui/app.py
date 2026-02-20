"""
TEGG Touch 蛋挞 辅助软件 - 主应用类

负责窗口管理、模式切换、事件分发。
编辑模式和运行模式均为全屏覆盖。

架构说明：
  FloatingApp 通过 Mixin 组合三个职责模块：
    - WindowStyleMixin  → ui/window_manager.py  (穿透样式 / 焦点控制)
    - RunEngineMixin    → ui/run_engine.py       (核心循环 / 按钮交互)
    - ButtonManagerMixin→ ui/button_manager.py   (按钮增删改 / 拖拽缩放)
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import sys
import time
import logging
import ctypes

from core.constants import (
    APP_TITLE, APP_VERSION,
    COLOR_BG, COLOR_TRANSPARENT,
    GRID_SIZE,
    PT_ON, PT_OFF, PT_BLOCK, PT_CYCLE,
    BTN_TYPE_CENTER_BAND, BTN_TYPE_WHEEL_SECTOR,
    default_wheel_sectors,
)
from core.config_manager import (
    load_config, save_config,
    init_profiles, load_profile, save_profile, set_active_profile
)
from ui.canvas_renderer import (
    draw_button, draw_floating_ball,
    init_cursor, remove_cursor, set_cursor_mode,
    draw_grid,
    remove_charge_bar,
    draw_wheel_sectors,
)
from ui.edit_panel import create_toolbar_window, destroy_toolbar_window

try:
    from ui.edit_panel import create_run_toolbar
except ImportError:
    try:
        from ui.toolbar import create_run_toolbar
    except ImportError:
        pass

from core.input_engine import (
    trigger,
    install_wheel_hook, uninstall_wheel_hook,
)

# Mixin 模块
from ui.window_manager import WindowStyleMixin
from ui.run_engine import RunEngineMixin
from ui.button_manager import ButtonManagerMixin

# Windows API
user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

logger = logging.getLogger(__name__)


class FloatingApp(WindowStyleMixin, RunEngineMixin, ButtonManagerMixin):
    """TEGG Touch 主应用类。

    继承顺序决定 MRO：同名方法以 WindowStyleMixin → RunEngineMixin → ButtonManagerMixin 优先。
    """

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
        self.is_window_solid = True
        self.edit_passthrough = False
        self.buttons_hidden = False
        self.auto_center = False
        self._last_btn_hover_time = 0
        self.AUTO_CENTER_DELAY = 2.0

        # 硬件输入状态缓存
        self.left_was_down = False
        self.right_was_down = False
        self.middle_was_down = False
        self.holding_btn_left = None
        self.holding_btn_right = None
        self.holding_btn_middle = None
        self.xbutton1_was_down = False
        self.xbutton2_was_down = False
        self.holding_btn_xbutton1 = None
        self.holding_btn_xbutton2 = None

        # 中心轮盘状态（从 profile 加载）
        self.wheel_visible = config.get('wheel_visible', False)
        self.wheel_sectors = config.get('wheel_sectors', default_wheel_sectors())

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

        # 安装全局滚轮钩子
        install_wheel_hook()

        # 独立工具栏窗口
        self.toolbar_win = None
        self.run_toolbar_win = None

        # 窗口位置缓存
        self.win_x = 0
        self.win_y = 0
        self.win_w = self.screen_w
        self.win_h = self.screen_h

        # 启动
        self.redraw_all()
        self.setup_ui_mode()
        self.update_loop()

    # ─── 工具栏管理 ──────────────────────────────────────────

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
            on_add_center_band=self.add_center_band_btn,
            on_edit_passthrough=self.toggle_edit_passthrough,
            edit_passthrough=self.edit_passthrough,
            on_toggle_wheel=self.toggle_wheel,
            wheel_visible=self.wheel_visible,
        )
        if self.toolbar_win:
            self.toolbar_win.lift()
            self.toolbar_win.after(100, self.toolbar_win.lift)

    def _hide_toolbar(self):
        destroy_toolbar_window(self.toolbar_win)
        self.toolbar_win = None

    def _show_run_toolbar(self):
        """创建运行工具栏窗口。"""
        destroy_toolbar_window(self.run_toolbar_win)
        self.run_toolbar_win = create_run_toolbar(
            self.root, self.screen_w, self.screen_h,
            on_edit=self.to_edit,
            on_passthrough=self.toggle_click_through_sync,
            click_through=self.click_through,
            set_window_style=self.set_window_style,
            on_toggle_buttons=self.toggle_buttons_visibility,
            buttons_visible=not self.buttons_hidden,
            on_toggle_auto_center=self.toggle_auto_center,
            auto_center=self.auto_center,
        )
        if self.run_toolbar_win:
            self.run_toolbar_win.lift()
            self.run_toolbar_win.after(100, self.run_toolbar_win.lift)

    def _hide_run_toolbar(self):
        destroy_toolbar_window(self.run_toolbar_win)
        self.run_toolbar_win = None

    # ─── 模式切换 ────────────────────────────────────────────

    def setup_ui_mode(self):
        """根据 current_mode 设置界面。"""
        if self.current_mode == 'main':
            self._hide_run_toolbar()
            self.root.overrideredirect(True)
            self.root.geometry(self.fullscreen_geo)
            self.root.attributes("-alpha", self.transparency)
            self.root.configure(bg=COLOR_TRANSPARENT)
            self.canvas.configure(bg=COLOR_TRANSPARENT)
            self.root.wm_attributes("-transparentcolor", COLOR_TRANSPARENT)
            self.set_window_style('normal')
            self.root.config(cursor="")
            self._show_toolbar()
            remove_cursor(self.canvas)
            self.win_x = 0
            self.win_y = 0
            self.win_w = self.screen_w
            self.win_h = self.screen_h

        elif self.current_mode == 'run':
            self.save_config()
            self._hide_toolbar()
            self.root.overrideredirect(True)
            self.root.geometry(self.fullscreen_geo)
            self.root.attributes("-alpha", self.transparency)
            self.root.configure(bg=COLOR_TRANSPARENT)
            self.canvas.configure(bg=COLOR_TRANSPARENT)
            self.root.wm_attributes("-transparentcolor", COLOR_TRANSPARENT)
            self.set_window_style('no_focus')
            self.root.config(cursor="none")
            set_cursor_mode(self.click_through)
            self._show_run_toolbar()
            init_cursor(self.canvas)
            self.win_x = 0
            self.win_y = 0
            self.win_w = self.screen_w
            self.win_h = self.screen_h

    def to_run(self):
        self.current_mode = 'run'
        self.is_hidden = False
        self.redraw_all()
        self.setup_ui_mode()

    def to_edit(self):
        self.current_mode = 'main'
        self.is_hidden = False
        self.edit_passthrough = False
        self.buttons_hidden = False
        self.root.geometry(self.fullscreen_geo)
        self.redraw_all()
        self.setup_ui_mode()

    def to_hide(self):
        self.is_hidden = True
        self._hide_run_toolbar()
        tx = self.screen_w // 2 - 40
        ty = self.screen_h // 2 - 40
        if self.ball_x is not None and self.ball_y is not None:
            tx, ty = self.ball_x, self.ball_y
        self.root.geometry(f"80x80+{tx}+{ty}")
        self.redraw_all()
        self.set_window_style('no_focus')

    def to_show(self):
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

        if self.current_mode == 'main':
            draw_grid(self.canvas, self.screen_w, self.screen_h)

        if self.current_mode == 'run' and self.buttons_hidden:
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

        # 中心轮盘（编辑模式和运行模式都绘制，如果可见）
        if self.wheel_visible and self.wheel_sectors:
            draw_wheel_sectors(self.canvas, self.wheel_sectors,
                               self._offset_x, self._offset_y)
            # 编辑模式下绑定双击编辑 + hover tooltip 事件
            if self.current_mode == 'main':
                for wi in range(len(self.wheel_sectors)):
                    wtag = f"wheel_sector_{wi}"
                    self.canvas.tag_bind(wtag, "<Double-Button-1>",
                                         lambda e, i=wi: self._edit_wheel_sector(i))
                    self.canvas.tag_bind(wtag, "<Enter>",
                                         lambda e, i=wi: self._show_edit_tooltip(e, self.wheel_sectors[i], is_wheel=True))
                    self.canvas.tag_bind(wtag, "<Leave>",
                                         lambda e: self._hide_edit_tooltip())

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
        for tag in [tag_poly, tag_text]:
            self.canvas.tag_bind(tag, "<B1-Motion>", lambda e, i=idx: self.on_btn_drag(e, i))
            self.canvas.tag_bind(tag, "<Double-Button-1>", lambda e, i=idx: self.edit_btn(i))
            self.canvas.tag_bind(tag, "<Enter>", lambda e, i=idx: self._show_edit_tooltip(e, self.buttons[i]))
            self.canvas.tag_bind(tag, "<Leave>", lambda e: self._hide_edit_tooltip())
        self.canvas.tag_bind(tag_resize, "<B1-Motion>", lambda e, i=idx: self.on_btn_resize(e, i))

    # ─── 编辑模式 Tooltip ────────────────────────────────────

    def _build_tooltip_text(self, btn_data, is_wheel=False):
        """根据按钮类型构建 tooltip 文本。"""
        btn_type = btn_data.get('type', '')

        if btn_type == BTN_TYPE_CENTER_BAND:
            return "鼠标到这里就会回中"

        # 普通按钮 / 轮盘扇区：显示所有配置参数
        fields = [
            ('名称', 'name'),
            ('悬停', 'hover'),
            ('触发延迟', 'hover_delay'),
            ('释放延迟', 'hover_release_delay'),
            ('左键', 'lclick'),
            ('右键', 'rclick'),
            ('中键', 'mclick'),
            ('滚上', 'wheelup'),
            ('滚下', 'wheeldown'),
            ('侧键1', 'xbutton1'),
            ('侧键2', 'xbutton2'),
        ]
        lines = []
        for label, key in fields:
            val = btn_data.get(key, '')
            # 延迟字段带 ms 后缀
            if key in ('hover_delay', 'hover_release_delay') and val != '':
                lines.append(f"{label}: {val}ms")
            else:
                lines.append(f"{label}: {val}")

        if is_wheel:
            lines.append("⚠ 中心轮盘不可移动和放大")

        return "\n".join(lines)

    def _show_edit_tooltip(self, event, btn_data, is_wheel=False):
        """在鼠标附近显示配置参数 tooltip。"""
        self._hide_edit_tooltip()
        text = self._build_tooltip_text(btn_data, is_wheel=is_wheel)

        # tooltip 位置：鼠标右下方偏移
        tx = event.x + 16
        ty = event.y + 16

        # 先绘制文字以获取 bbox
        tid = self.canvas.create_text(
            tx + 8, ty + 6, text=text, anchor="nw",
            font=("Microsoft YaHei UI", 9), fill="#E0E0E0",
            tags="edit_tooltip",
        )
        bbox = self.canvas.bbox(tid)
        if bbox:
            pad = 6
            x1, y1, x2, y2 = bbox
            # 如果超出屏幕右侧，移到鼠标左侧
            if x2 + pad > self.screen_w:
                offset = (x2 - x1) + 32
                self.canvas.move(tid, -offset, 0)
                x1 -= offset
                x2 -= offset
            # 如果超出屏幕底部，移到鼠标上方
            if y2 + pad > self.screen_h:
                offset = (y2 - y1) + 32
                self.canvas.move(tid, 0, -offset)
                y1 -= offset
                y2 -= offset
            # 背景矩形
            bg = self.canvas.create_rectangle(
                x1 - pad, y1 - pad, x2 + pad, y2 + pad,
                fill="#005A9E", outline="#005A9E", width=1,
                tags="edit_tooltip",
            )
            self.canvas.tag_lower(bg, tid)

    def _hide_edit_tooltip(self):
        """移除 tooltip。"""
        self.canvas.delete("edit_tooltip")

    # ─── 悬浮球 UI 事件 ─────────────────────────────────────

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

    # ─── 设置与开关 ──────────────────────────────────────────

    def set_alpha(self, v):
        self.transparency = int(v) / 100.0
        self.root.attributes("-alpha", self.transparency)

    def toggle_edit_passthrough(self, is_on):
        self.edit_passthrough = is_on
        if self.current_mode == 'main':
            self.set_window_style('click_through' if is_on else 'normal')

    def toggle_click_through(self):
        """三态循环：PT_ON → PT_OFF → PT_BLOCK → PT_ON ..."""
        idx = PT_CYCLE.index(self.click_through) if self.click_through in PT_CYCLE else 0
        self.click_through = PT_CYCLE[(idx + 1) % len(PT_CYCLE)]
        self.redraw_all()
        self.set_window_style('no_focus')
        if self.click_through in (PT_ON, PT_OFF):
            self._focus_game_window()

    def toggle_wheel(self, visible):
        """切换中心轮盘显示/隐藏。"""
        self.wheel_visible = visible
        self.redraw_all()

    def _edit_wheel_sector(self, index):
        """双击编辑轮盘扇区 — 复用普通按钮编辑弹窗。"""
        from ui.button_editor import open_button_editor
        sector = self.wheel_sectors[index]
        logger.info(f"编辑轮盘扇区 #{index}: {sector.get('name')}")

        def on_save(updated):
            # 保留 angle/type 等结构字段，合并编辑结果
            for k, v in updated.items():
                sector[k] = v
            self.redraw_all()

        open_button_editor(
            self.root, sector,
            on_save=on_save,
            on_delete=None,
            on_copy=None,
            set_window_style=None,
        )

    def toggle_auto_center(self, on):
        self.auto_center = on
        self._last_btn_hover_time = time.time()

    def toggle_buttons_visibility(self, visible):
        self.buttons_hidden = not visible
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
        self.click_through = mode
        set_cursor_mode(mode)
        self.redraw_all()
        self.set_window_style('no_focus')
        if mode in (PT_ON, PT_OFF):
            self._focus_game_window()
        elif mode == PT_BLOCK:
            try:
                _hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                user32.SetForegroundWindow(_hwnd)
            except Exception:
                pass

    # ─── 配置管理 ────────────────────────────────────────────

    def switch_profile(self, name):
        if self.current_profile:
            self.save_config()
        set_active_profile(name)
        config = load_profile(name)
        self.current_profile = name
        self.transparency = config['transparency']
        self.buttons = config['buttons']
        self.ball_x = config['ball_x']
        self.ball_y = config['ball_y']
        self.click_through = config['click_through']
        self.wheel_visible = config.get('wheel_visible', False)
        self.wheel_sectors = config.get('wheel_sectors', default_wheel_sectors())
        self.redraw_all()
        if self.current_mode == 'main':
            self._show_toolbar()

    def save_config(self):
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
            root=self.root,
            wheel_visible=self.wheel_visible,
            wheel_sectors=self.wheel_sectors,
        )

    def export_config(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("配置", "*.json")],
            title="导出配置"
        )
        if path:
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
