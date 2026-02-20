"""
TEGG Touch - 运行引擎 Mixin

负责核心循环 (update_loop)、运行模式按钮交互、自动回中、穿透判定。
"""

import time
import logging
import ctypes

from core.constants import (
    UPDATE_INTERVAL,
    PT_ON, PT_OFF, PT_BLOCK,
    BTN_TYPE_CENTER_BAND,
    WHEEL_INNER_RADIUS, WHEEL_OUTER_RADIUS,
    WHEEL_RING_INNER, WHEEL_RING_OUTER,
)
from ui.canvas_renderer import (
    set_button_visual_state,
    init_cursor, update_cursor, remove_cursor,
    draw_charge_bar, remove_charge_bar,
    wheel_sector_hit_test, set_wheel_sector_visual,
    draw_wheel_charge_bar, remove_wheel_charge_bar,
    wheel_center_ring_hit_test, set_wheel_center_ring_visual,
    draw_wheel_center_ring_charge_bar, remove_wheel_center_ring_charge_bar,
)
from core.input_engine import (
    trigger, is_key_pressed, poll_wheel_events,
)

user32 = ctypes.windll.user32
logger = logging.getLogger(__name__)


class RunEngineMixin:
    """运行模式核心循环与交互引擎，由 FloatingApp 继承使用。"""

    # ─── 坐标辅助 ────────────────────────────────────────────

    def _btn_screen_rect(self, btn):
        """返回按钮的屏幕矩形 (sx, sy, sw, sh)。"""
        return (btn['x'] + self._offset_x, btn['y'] + self._offset_y, btn['w'], btn['h'])

    def _point_in_btn(self, btn, px, py):
        """判断屏幕坐标 (px,py) 是否在按钮内。"""
        sx = btn['x'] + self._offset_x
        sy = btn['y'] + self._offset_y
        return sx <= px < sx + btn['w'] and sy <= py < sy + btn['h']

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

                # 0e. 自动回中 (F6)
                if is_key_pressed('f6'):
                    self.toggle_auto_center(not self.auto_center)
                    self._show_run_toolbar()
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

                # 3. 智能穿透判定
                if not self.is_hidden:
                    is_on_ui = False
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
                        # 轮盘扇区也参与穿透判定
                        if not is_on_ui and self.wheel_visible and self.wheel_sectors:
                            _wri, _wro = self._get_wheel_radii()
                            if wheel_sector_hit_test(self.wheel_sectors, rel_x, rel_y, ox, oy, r_inner=_wri, r_outer=_wro) >= 0:
                                is_on_ui = True
                            # 中心圆环也参与穿透判定（仅大圆盘模式 + 已启用）
                            if not is_on_ui and self.wheel_enlarged and self.wheel_center_ring_visible and self.wheel_center_ring:
                                if wheel_center_ring_hit_test(self.wheel_center_ring, rel_x, rel_y, ox, oy):
                                    is_on_ui = True

                    if self.current_mode == 'main':
                        if is_on_ui:
                            if not self.is_window_solid:
                                self.set_window_style('normal')
                        else:
                            if self.is_window_solid:
                                self.set_window_style('click_through')

                    elif self.current_mode == 'run':
                        if self.click_through == PT_ON:
                            if self.is_window_solid:
                                self.set_window_style('click_through')
                        elif self.click_through == PT_OFF:
                            if is_on_ui:
                                if not self.is_window_solid:
                                    self.set_window_style('no_focus')
                            else:
                                if self.is_window_solid:
                                    self.set_window_style('click_through')
                        elif self.click_through == PT_BLOCK:
                            if is_on_ui:
                                if self.is_window_solid:
                                    self.set_window_style('click_through')
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
                                    try:
                                        _hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                                        user32.SetForegroundWindow(_hwnd)
                                    except Exception:
                                        pass

                # 4. 更新虚拟光标
                hide_cursor = False
                if self.run_toolbar_win and self.run_toolbar_win.winfo_exists():
                    tb_x = self.run_toolbar_win.winfo_rootx()
                    tb_y = self.run_toolbar_win.winfo_rooty()
                    tb_w = self.run_toolbar_win.winfo_width()
                    tb_h = self.run_toolbar_win.winfo_height()
                    if (tb_x <= abs_x < tb_x + tb_w) and (tb_y <= abs_y < tb_y + tb_h):
                        hide_cursor = True

                if not self.is_hidden and not hide_cursor:
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
                xbutton1_down = (user32.GetAsyncKeyState(0x05) & 0x8000) != 0  # 侧键1(后退)
                xbutton2_down = (user32.GetAsyncKeyState(0x06) & 0x8000) != 0  # 侧键2(前进)

                # 6. 处理点击/悬浮
                if self.is_hidden:
                    self.handle_hidden_interaction(abs_x, abs_y, rel_x, rel_y, left_down)
                else:
                    self.handle_run_interaction(rel_x, rel_y, left_down, right_down, middle_down,
                                               xbutton1_down, xbutton2_down)

                # 6b. 自动回中逻辑 + 倒计时进度条
                self.canvas.delete("_ac_bar")
                if self.auto_center and not self.buttons_hidden and not self.is_hidden:
                    now = time.time()
                    _on_any_btn = False
                    for _b in self.buttons:
                        if _b.get('deleted'):
                            continue
                        if self._point_in_btn(_b, rel_x, rel_y):
                            _on_any_btn = True
                            break
                    # 轮盘扇区也视为"正在操作按钮"
                    if not _on_any_btn and self.wheel_visible and self.wheel_sectors:
                        _wri, _wro = self._get_wheel_radii()
                        _ox, _oy = self._offset_x, self._offset_y
                        if wheel_sector_hit_test(self.wheel_sectors, rel_x, rel_y, _ox, _oy,
                                                 r_inner=_wri, r_outer=_wro) >= 0:
                            _on_any_btn = True
                    # 中心圆环也视为"正在操作按钮"
                    if not _on_any_btn and self.wheel_visible and self.wheel_enlarged \
                       and self.wheel_center_ring_visible and self.wheel_center_ring:
                        _ox, _oy = self._offset_x, self._offset_y
                        if wheel_center_ring_hit_test(self.wheel_center_ring, rel_x, rel_y, _ox, _oy):
                            _on_any_btn = True
                    _center_x = self.screen_w // 2
                    _center_y = self.screen_h // 2
                    _at_center = abs(rel_x - _center_x) <= 50 and abs(rel_y - _center_y) <= 50

                    if _on_any_btn or _at_center:
                        self._last_btn_hover_time = now
                    else:
                        _elapsed = now - self._last_btn_hover_time
                        if _elapsed >= self.AUTO_CENTER_DELAY:
                            user32.SetCursorPos(_center_x, _center_y)
                            self._last_btn_hover_time = now
                        else:
                            _bar_w = 50
                            _bar_h = 6
                            _bar_x = rel_x + 15
                            _bar_y = rel_y
                            _progress = max(0.0, 1.0 - _elapsed / self.AUTO_CENTER_DELAY)
                            _fill_w = int(_bar_w * _progress)
                            self.canvas.create_rectangle(
                                _bar_x, _bar_y, _bar_x + _bar_w, _bar_y + _bar_h,
                                fill="#555555", outline="", tags="_ac_bar")
                            if _fill_w > 0:
                                self.canvas.create_rectangle(
                                    _bar_x, _bar_y, _bar_x + _fill_w, _bar_y + _bar_h,
                                    fill="#176F2C", outline="", tags="_ac_bar")

                # 7. 更新状态
                self.left_was_down = left_down
                self.right_was_down = right_down
                self.middle_was_down = middle_down
                self.xbutton1_was_down = xbutton1_down
                self.xbutton2_was_down = xbutton2_down

        except Exception as e:
            logger.error(f"Loop error: {e}")

        self.root.after(UPDATE_INTERVAL, self.update_loop)

    # ─── 悬浮球交互 ──────────────────────────────────────────

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

    # ─── 运行模式按钮交互 ────────────────────────────────────

    def handle_run_interaction(self, rel_x, rel_y, left_down, right_down, middle_down,
                               xbutton1_down=False, xbutton2_down=False):
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

            # ── 回中带：鼠标进入即刻回中，零延迟 ──
            if btn.get('type') == BTN_TYPE_CENTER_BAND and in_rect:
                user32.SetCursorPos(self.screen_w // 2, self.screen_h // 2)
                continue

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
                elif xbutton1_down and btn.get('xbutton1'):
                    target_state = 'active_xbutton1'
                elif xbutton2_down and btn.get('xbutton2'):
                    target_state = 'active_xbutton2'

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
                if xbutton1_down and not self.xbutton1_was_down and btn.get('xbutton1'):
                    self.holding_btn_xbutton1 = idx
                    trigger(btn['xbutton1'], 'p')
                if xbutton2_down and not self.xbutton2_was_down and btn.get('xbutton2'):
                    self.holding_btn_xbutton2 = idx
                    trigger(btn['xbutton2'], 'p')
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

        if not xbutton1_down and self.xbutton1_was_down and self.holding_btn_xbutton1 is not None:
            btn = self.buttons[self.holding_btn_xbutton1]
            if not btn.get('deleted'):
                trigger(btn['xbutton1'], 'r')
            self.holding_btn_xbutton1 = None

        if not xbutton2_down and self.xbutton2_was_down and self.holding_btn_xbutton2 is not None:
            btn = self.buttons[self.holding_btn_xbutton2]
            if not btn.get('deleted'):
                trigger(btn['xbutton2'], 'r')
            self.holding_btn_xbutton2 = None

        # ── 轮盘扇区交互（与普通按钮逻辑一致） ──
        if self.wheel_visible and self.wheel_sectors:
            ox, oy = self._offset_x, self._offset_y
            _wri, _wro = self._get_wheel_radii()
            hit_idx = wheel_sector_hit_test(self.wheel_sectors, rel_x, rel_y, ox, oy,
                                            r_inner=_wri, r_outer=_wro)

            # 滚轮事件 → 扇区
            for direction, wx, wy in wheel_events:
                w_rx = wx - self.win_x
                w_ry = wy - self.win_y
                w_hit = wheel_sector_hit_test(self.wheel_sectors, w_rx, w_ry, ox, oy,
                                              r_inner=_wri, r_outer=_wro)
                if w_hit >= 0:
                    sec = self.wheel_sectors[w_hit]
                    key = sec.get('wheelup') if direction == 'up' else sec.get('wheeldown')
                    if key:
                        trigger(key, 'c')
                        ws = 'active_wheelup' if direction == 'up' else 'active_wheeldown'
                        set_wheel_sector_visual(self.canvas, sec, ws)
                        sec['last_visual_state'] = ws
                        sec['_wheel_flash_until'] = now + 0.15

            for si, sec in enumerate(self.wheel_sectors):
                in_sec = (si == hit_idx)
                hover_delay = sec.get('hover_delay', 0)

                # 滚轮闪烁期间跳过视觉状态更新
                if now < sec.get('_wheel_flash_until', 0):
                    if in_sec and not sec.get('active_hover') and sec.get('hover'):
                        if hover_delay <= 0:
                            sec['active_hover'] = True
                            trigger(sec['hover'], 'p')
                    elif not in_sec and sec.get('active_hover'):
                        sec['active_hover'] = False
                        trigger(sec['hover'], 'r')
                        remove_wheel_charge_bar(self.canvas, sec)
                    continue

                # 视觉状态
                target = 'normal'
                if in_sec:
                    if sec.get('active_hover'):
                        target = 'hover'
                    if left_down and sec.get('lclick'):
                        target = 'active_left'
                    elif right_down and sec.get('rclick'):
                        target = 'active_right'
                    elif middle_down and sec.get('mclick'):
                        target = 'active_middle'
                    elif xbutton1_down and sec.get('xbutton1'):
                        target = 'active_xbutton1'
                    elif xbutton2_down and sec.get('xbutton2'):
                        target = 'active_xbutton2'

                if sec.get('last_visual_state') != target:
                    set_wheel_sector_visual(self.canvas, sec, target)
                    sec['last_visual_state'] = target

                release_delay = sec.get('hover_release_delay', 0)

                if in_sec:
                    # 重入扇区 → 取消释放倒计时
                    if sec.get('_hover_release_time') is not None:
                        sec['_hover_release_time'] = None
                        remove_wheel_charge_bar(self.canvas, sec)
                        set_wheel_sector_visual(self.canvas, sec, 'hover')
                        sec['last_visual_state'] = 'hover'

                    if not sec.get('active_hover') and sec.get('hover'):
                        if hover_delay <= 0:
                            sec['active_hover'] = True
                            trigger(sec['hover'], 'p')
                        else:
                            if sec.get('_hover_enter_time') is None:
                                sec['_hover_enter_time'] = now
                                sec['_hover_charged'] = False
                            if not sec.get('_hover_charged'):
                                elapsed_ms = (now - sec['_hover_enter_time']) * 1000
                                progress = min(1.0, elapsed_ms / hover_delay)
                                draw_wheel_charge_bar(self.canvas, sec, progress,
                                                      r_inner=_wri, r_outer=_wro)
                                if progress >= 1.0:
                                    sec['_hover_charged'] = True
                                    sec['active_hover'] = True
                                    remove_wheel_charge_bar(self.canvas, sec)
                                    trigger(sec['hover'], 'p')

                    # 点击
                    if left_down and not self.left_was_down and sec.get('lclick'):
                        trigger(sec['lclick'], 'p')
                        sec['_holding_left'] = True
                    if right_down and not self.right_was_down and sec.get('rclick'):
                        trigger(sec['rclick'], 'p')
                        sec['_holding_right'] = True
                    if middle_down and not self.middle_was_down and sec.get('mclick'):
                        trigger(sec['mclick'], 'p')
                        sec['_holding_middle'] = True
                    if xbutton1_down and not self.xbutton1_was_down and sec.get('xbutton1'):
                        trigger(sec['xbutton1'], 'p')
                        sec['_holding_xbutton1'] = True
                    if xbutton2_down and not self.xbutton2_was_down and sec.get('xbutton2'):
                        trigger(sec['xbutton2'], 'p')
                        sec['_holding_xbutton2'] = True
                else:
                    # 离开扇区
                    if sec.get('active_hover'):
                        if release_delay <= 0:
                            sec['active_hover'] = False
                            sec['_hover_release_time'] = None
                            trigger(sec['hover'], 'r')
                        else:
                            if sec.get('_hover_release_time') is None:
                                sec['_hover_release_time'] = now
                            elapsed_ms = (now - sec['_hover_release_time']) * 1000
                            progress = max(0.0, 1.0 - elapsed_ms / release_delay)
                            if progress <= 0:
                                sec['active_hover'] = False
                                sec['_hover_release_time'] = None
                                remove_wheel_charge_bar(self.canvas, sec)
                                trigger(sec['hover'], 'r')
                            else:
                                draw_wheel_charge_bar(self.canvas, sec, progress,
                                                      r_inner=_wri, r_outer=_wro)

                    if sec.get('_hover_enter_time') is not None:
                        sec['_hover_enter_time'] = None
                        sec['_hover_charged'] = False
                        if not sec.get('_hover_release_time'):
                            remove_wheel_charge_bar(self.canvas, sec)

                # 点击释放
                if not left_down and self.left_was_down and sec.get('_holding_left'):
                    trigger(sec['lclick'], 'r')
                    sec['_holding_left'] = False
                if not right_down and self.right_was_down and sec.get('_holding_right'):
                    trigger(sec['rclick'], 'r')
                    sec['_holding_right'] = False
                if not middle_down and self.middle_was_down and sec.get('_holding_middle'):
                    trigger(sec['mclick'], 'r')
                    sec['_holding_middle'] = False
                if not xbutton1_down and self.xbutton1_was_down and sec.get('_holding_xbutton1'):
                    trigger(sec['xbutton1'], 'r')
                    sec['_holding_xbutton1'] = False
                if not xbutton2_down and self.xbutton2_was_down and sec.get('_holding_xbutton2'):
                    trigger(sec['xbutton2'], 'r')
                    sec['_holding_xbutton2'] = False

        # ── 中心圆环交互（仅大圆盘模式 + 已启用） ──
        if self.wheel_visible and self.wheel_enlarged and self.wheel_center_ring_visible and self.wheel_center_ring:
            ring = self.wheel_center_ring
            ox, oy = self._offset_x, self._offset_y
            in_ring = wheel_center_ring_hit_test(ring, rel_x, rel_y, ox, oy)
            hover_delay = ring.get('hover_delay', 0)

            # 滚轮事件 → 圆环
            for direction, wx, wy in wheel_events:
                w_rx = wx - self.win_x
                w_ry = wy - self.win_y
                if wheel_center_ring_hit_test(ring, w_rx, w_ry, ox, oy):
                    key = ring.get('wheelup') if direction == 'up' else ring.get('wheeldown')
                    if key:
                        trigger(key, 'c')
                        ws = 'active_wheelup' if direction == 'up' else 'active_wheeldown'
                        set_wheel_center_ring_visual(self.canvas, ring, ws)
                        ring['last_visual_state'] = ws
                        ring['_wheel_flash_until'] = now + 0.15

            # 滚轮闪烁期间
            if now < ring.get('_wheel_flash_until', 0):
                if in_ring and not ring.get('active_hover') and ring.get('hover'):
                    if hover_delay <= 0:
                        ring['active_hover'] = True
                        trigger(ring['hover'], 'p')
                elif not in_ring and ring.get('active_hover'):
                    ring['active_hover'] = False
                    trigger(ring['hover'], 'r')
                    remove_wheel_center_ring_charge_bar(self.canvas, ring)
            else:
                # 视觉状态
                target = 'normal'
                if in_ring:
                    if ring.get('active_hover'):
                        target = 'hover'
                    if left_down and ring.get('lclick'):
                        target = 'active_left'
                    elif right_down and ring.get('rclick'):
                        target = 'active_right'
                    elif middle_down and ring.get('mclick'):
                        target = 'active_middle'
                    elif xbutton1_down and ring.get('xbutton1'):
                        target = 'active_xbutton1'
                    elif xbutton2_down and ring.get('xbutton2'):
                        target = 'active_xbutton2'

                if ring.get('last_visual_state') != target:
                    set_wheel_center_ring_visual(self.canvas, ring, target)
                    ring['last_visual_state'] = target

                release_delay = ring.get('hover_release_delay', 0)

                if in_ring:
                    if ring.get('_hover_release_time') is not None:
                        ring['_hover_release_time'] = None
                        remove_wheel_center_ring_charge_bar(self.canvas, ring)
                        set_wheel_center_ring_visual(self.canvas, ring, 'hover')
                        ring['last_visual_state'] = 'hover'

                    if not ring.get('active_hover') and ring.get('hover'):
                        if hover_delay <= 0:
                            ring['active_hover'] = True
                            trigger(ring['hover'], 'p')
                        else:
                            if ring.get('_hover_enter_time') is None:
                                ring['_hover_enter_time'] = now
                                ring['_hover_charged'] = False
                            if not ring.get('_hover_charged'):
                                elapsed_ms = (now - ring['_hover_enter_time']) * 1000
                                progress = min(1.0, elapsed_ms / hover_delay)
                                draw_wheel_center_ring_charge_bar(self.canvas, ring, progress)
                                if progress >= 1.0:
                                    ring['_hover_charged'] = True
                                    ring['active_hover'] = True
                                    remove_wheel_center_ring_charge_bar(self.canvas, ring)
                                    trigger(ring['hover'], 'p')

                    # 点击
                    if left_down and not self.left_was_down and ring.get('lclick'):
                        trigger(ring['lclick'], 'p')
                        ring['_holding_left'] = True
                    if right_down and not self.right_was_down and ring.get('rclick'):
                        trigger(ring['rclick'], 'p')
                        ring['_holding_right'] = True
                    if middle_down and not self.middle_was_down and ring.get('mclick'):
                        trigger(ring['mclick'], 'p')
                        ring['_holding_middle'] = True
                    if xbutton1_down and not self.xbutton1_was_down and ring.get('xbutton1'):
                        trigger(ring['xbutton1'], 'p')
                        ring['_holding_xbutton1'] = True
                    if xbutton2_down and not self.xbutton2_was_down and ring.get('xbutton2'):
                        trigger(ring['xbutton2'], 'p')
                        ring['_holding_xbutton2'] = True
                else:
                    if ring.get('active_hover'):
                        if release_delay <= 0:
                            ring['active_hover'] = False
                            ring['_hover_release_time'] = None
                            trigger(ring['hover'], 'r')
                        else:
                            if ring.get('_hover_release_time') is None:
                                ring['_hover_release_time'] = now
                            elapsed_ms = (now - ring['_hover_release_time']) * 1000
                            progress = max(0.0, 1.0 - elapsed_ms / release_delay)
                            if progress <= 0:
                                ring['active_hover'] = False
                                ring['_hover_release_time'] = None
                                remove_wheel_center_ring_charge_bar(self.canvas, ring)
                                trigger(ring['hover'], 'r')
                            else:
                                draw_wheel_center_ring_charge_bar(self.canvas, ring, progress)

                    if ring.get('_hover_enter_time') is not None:
                        ring['_hover_enter_time'] = None
                        ring['_hover_charged'] = False
                        if not ring.get('_hover_release_time'):
                            remove_wheel_center_ring_charge_bar(self.canvas, ring)

                # 点击释放
                if not left_down and self.left_was_down and ring.get('_holding_left'):
                    trigger(ring['lclick'], 'r')
                    ring['_holding_left'] = False
                if not right_down and self.right_was_down and ring.get('_holding_right'):
                    trigger(ring['rclick'], 'r')
                    ring['_holding_right'] = False
                if not middle_down and self.middle_was_down and ring.get('_holding_middle'):
                    trigger(ring['mclick'], 'r')
                    ring['_holding_middle'] = False
                if not xbutton1_down and self.xbutton1_was_down and ring.get('_holding_xbutton1'):
                    trigger(ring['xbutton1'], 'r')
                    ring['_holding_xbutton1'] = False
                if not xbutton2_down and self.xbutton2_was_down and ring.get('_holding_xbutton2'):
                    trigger(ring['xbutton2'], 'r')
                    ring['_holding_xbutton2'] = False
