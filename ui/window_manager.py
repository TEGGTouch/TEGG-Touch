"""
TEGG Touch - 窗口样式管理 Mixin

负责 Windows API 穿透样式控制、焦点管理。
"""

import ctypes

user32 = ctypes.windll.user32


class WindowStyleMixin:
    """管理窗口穿透样式的 Mixin，由 FloatingApp 继承使用。"""

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
