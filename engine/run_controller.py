"""
TEGG Touch 蛋挞 (PyQt6) - run_controller.py
运行模式控制器 — 协调输入检测、按键触发、模式切换。

旧版: update_loop() 单函数 400 行，轮询一切
新版:
  - hover/click 由轮询 GetCursorPos + itemAt 驱动（与原版一致）
  - 解决 WS_EX_TRANSPARENT 下 Qt 事件丢失的问题
  - Controller 负责: 快捷键轮询 + hover/click轮询 + 侧键 + 自动回中 + 滚轮
"""

import ctypes
import ctypes.wintypes
import logging
import threading
import time as _time

from PyQt6.QtCore import QObject, QTimer, QPoint, QRect, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.input_engine import (
    trigger, is_key_pressed, poll_wheel_events, release_all_keys,
    mouse_press, mouse_release, mouse_wheel,
)
from core.config_manager import load_hotkeys
from core.constants import (
    UPDATE_INTERVAL, BTN_TYPE_CENTER_BAND, HOTKEY_DEBOUNCE_SEC,
    GP_KEY_PREFIX,
)
from core.system_tuning import input_poll_interval_ms
from engine.gamepad_engine import GamepadEngine

user32 = ctypes.windll.user32
logger = logging.getLogger(__name__)

# ── ctypes 类型声明 ──
user32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
user32.GetCursorPos.restype = ctypes.wintypes.BOOL

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = ctypes.wintypes.BOOL

# VK 常量
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06


def _is_alive(item) -> bool:
    """检查 QGraphicsItem 是否仍然有效（未被 C++ 侧删除）"""
    try:
        from PyQt6 import sip
        return not sip.isdeleted(item)
    except (ImportError, RuntimeError):
        return True


def _wheel_occupied_fields(data) -> set:
    """根据 LT/RT 的 mode + marker_button 算出哪些鼠标动作字段被扳机占用。
    占用 = wheel.data.mouse_* 该字段配了也不生效。"""
    occupied: set = set()
    for prefix in ('lt', 'rt'):
        mode = getattr(data, f'{prefix}_mode', '')
        if mode == 'buttons':
            occupied.update(('lclick', 'rclick'))
        elif mode == 'marker':
            btn = getattr(data, f'{prefix}_marker_button', 'L')
            occupied.add('lclick' if btn == 'L' else 'rclick')
        elif mode == 'scroll':
            occupied.update(('wheelup', 'wheeldown'))
    return occupied


class RunController(QObject):
    """运行模式控制器"""
    # 信号
    request_edit_mode = pyqtSignal()
    request_toggle_voice = pyqtSignal()
    request_toggle_buttons = pyqtSignal()
    request_toggle_auto_center = pyqtSignal()
    request_soft_keyboard = pyqtSignal()
    passthrough_changed = pyqtSignal(str)   # 'pt_on' | 'pt_off' | 'pt_block'
    cursor_on_ui = pyqtSignal(bool)         # 每帧: 光标是否在 UI 元素上
    auto_center_progress = pyqtSignal(float, float, float)  # progress, x, y
    voice_command_triggered = pyqtSignal(str, str, str)  # phrase, keys, action
    request_toggle_collapse = pyqtSignal()  # F10: 折叠/展开运行工具栏

    def __init__(self, scene, window):
        super().__init__()
        self._scene = scene
        self._window = window
        self._active = False

        # 硬件按键状态缓存 (用于侧键检测)
        self._prev_xb1 = False
        self._prev_xb2 = False

        # Bug 4 fix: 使用计数器替代布尔值，正确追踪多个同时激活的按键
        # 线程安全说明: 所有修改 _active_key_count 的 slot 均在主线程中
        # 通过 DirectConnection 或同线程 QueuedConnection 调用，不存在跨线程竞态。
        self._active_key_count = 0

        # 轮询式 hover 检测状态 (解决 WS_EX_TRANSPARENT 下 Qt 事件丢失)
        self._poll_hover_item = None  # 当前 hover 的 item
        self._prev_lmb = False  # 左键上一帧状态
        self._prev_rmb = False  # 右键
        self._prev_mmb = False  # 中键

        # 原版 holding_btn 模式: 按下时记住按钮，释放时用存储的按钮（光标可能已移走）
        self._holding_lclick = None   # (item, key_str) or None
        self._holding_rclick = None
        self._holding_mclick = None

        # 防抖标志
        self._debounce = {}

        # 摇杆状态机 — 任一帧只允许一个 active 摇杆 (跨摇杆切换会让旧的释放 + SetCursorPos 跳到新圆心)
        self._active_gp_stick = None  # GpStickItem | None

        # 方向盘单例状态 + LT/RT 持久值
        self._active_gp_wheel = None  # GpWheelItem | None
        self._wheel_lt = 0.0          # 0~1, 持久化
        self._wheel_rt = 0.0
        self._wheel_last_screen_y = 0  # vertical 模式的 reference Y (screen 坐标)
        # marker 模式: 浮标位置 (0~1, 不写入扳机值, 直到用户点击对应键才锁定到扳机)
        # 上次按键状态用于边沿检测 (按下→ click 一次, 持续按住不重复)
        self._wheel_lt_marker_pos = 0.0
        self._wheel_rt_marker_pos = 0.0
        self._wheel_lmb_was_down = False
        self._wheel_rmb_was_down = False
        # 方向盘 active 时其他鼠标按键触发的动作 (优先级低于 LT/RT)
        # 持有状态: {field_name → key_str}, 用于按下时记 + 释放时触发 'r'
        self._wheel_mouse_holding: dict = {}
        # 上次鼠标键状态 (用于 x1/x2 边沿检测; lmb/rmb 复用 _wheel_lmb_was_down)
        self._wheel_mmb_was_down = False
        self._wheel_x1_was_down = False
        self._wheel_x2_was_down = False

        # 快捷键定时器
        self._timer = QTimer(self)
        self._timer.setInterval(input_poll_interval_ms(UPDATE_INTERVAL))
        self._timer.timeout.connect(self._tick)

        # 自动回中
        self._auto_center = False
        self._auto_center_delay = 1500
        self._ac_start_time = None  # 倒计时开始时间

        self._hotkeys = load_hotkeys()

        # 语音引擎（延迟创建，仅在配置启用时）
        self._voice_engine = None

    def reload_hotkeys(self):
        """重新加载快捷键配置"""
        self._hotkeys = load_hotkeys()
        self._auto_center_delay = self._hotkeys.get('auto_center_delay', 1500)

    @property
    def auto_center(self):
        return self._auto_center

    @auto_center.setter
    def auto_center(self, val):
        self._auto_center = val
        if not val:
            self._ac_start_time = None

    def start(self, voice_config: dict = None):
        """进入运行模式

        Args:
            voice_config: 语音配置 dict，包含 voice_enabled, voice_language, voice_commands。
                          为 None 时不启动语音。
        """
        self._active = True
        self._hotkeys = load_hotkeys()
        self._auto_center_delay = self._hotkeys.get('auto_center_delay', 1500)
        self._debounce.clear()
        self._poll_hover_item = None
        self._prev_lmb = False
        self._prev_rmb = False
        self._prev_mmb = False
        self._holding_lclick = None
        self._holding_rclick = None
        self._holding_mclick = None
        self._timer.start()

        # 启动语音引擎
        self._start_voice(voice_config)

    def stop(self):
        """退出运行模式"""
        self._active = False
        self._timer.stop()
        self._ac_start_time = None
        self._stop_voice()
        self._active_key_count = 0
        # 释放当前 hover
        if self._poll_hover_item is not None:
            item = self._poll_hover_item
            self._poll_hover_item = None
            if hasattr(item, '_hover_sm'):
                item._hover_sm.leave()
            if hasattr(item, 'set_visual_state'):
                item.set_visual_state('normal')
        # 释放所有 holding 的点击键
        for holding in (self._holding_lclick, self._holding_rclick, self._holding_mclick):
            if holding:
                _item, _key = holding
                if _is_alive(_item):
                    self.on_action_triggered(_item.data, _key, 'r')
        self._holding_lclick = None
        self._holding_rclick = None
        self._holding_mclick = None
        self.auto_center_progress.emit(-1, 0, 0)
        # 重置所有按钮的 hover 状态机
        for item in self._scene.button_items:
            if hasattr(item, '_hover_sm'):
                item._hover_sm.reset()
        # 兜底释放所有残留按键，防止卡键
        release_all_keys()
        # 手柄: 释放当前 active 摇杆/方向盘 + 引擎全部归零
        if self._active_gp_stick is not None:
            self._release_active_stick()
        if self._active_gp_wheel is not None:
            self._release_gp_wheel()
        gp = GamepadEngine.get()
        if gp is not None:
            gp.release_all()

    # ── 获取光标下的 item ──

    def _get_cursor_item(self):
        """获取光标位置和光标下的 item（使用 Win32 GetCursorPos，不依赖 Qt 事件）"""
        try:
            pt = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            cursor_pos = QPoint(pt.x, pt.y)
            view_pos = self._window.mapFromGlobal(cursor_pos)
            scene_pos = self._window.mapToScene(view_pos)
            item = self._scene.itemAt(scene_pos, self._window.transform())
            return item, scene_pos, pt.x, pt.y
        except Exception:
            return None, None, 0, 0

    # ── 主循环 ──

    def _tick(self):
        """轮询循环 — 快捷键 + hover/click + 侧键 + 滚轮 + 自动回中"""
        if not self._active:
            return

        hk = self._hotkeys

        # 1. 快捷键检测
        self._check_hotkeys(hk)
        if not self._active:  # stop 可能在 _check_hotkeys 中被调用
            return

        # 2. 处理滚轮事件
        wheel_events = poll_wheel_events()
        for direction, wx, wy in wheel_events:
            self._dispatch_wheel(direction, wx, wy)

        # 3. 侧键轮询
        self._poll_hardware_buttons()

        # 4a. 摇杆轮询 (在 hover/click 之前; 摇杆 item 不走 hover_sm, 自有状态机)
        self._poll_gp_sticks()

        # 4b. 方向盘轮询 (单例; 同样自有状态机)
        self._poll_gp_wheel()

        # 4c. 轮询式 hover/click 检测 (核心! 解决 WS_EX_TRANSPARENT 问题)
        self._poll_hover_and_click()

        # 5. 自动回中管理
        self._poll_auto_center()

    # ── 轮询式 hover/click 检测 ──

    def _poll_hover_and_click(self):
        """轮询光标位置，驱动 hover 状态机和 click 检测
        
        与原版 Tkinter 一致：使用 GetCursorPos + 坐标碰撞检测，
        不依赖 Qt 的 hoverEnterEvent/mousePressEvent（WS_EX_TRANSPARENT 下不触发）。
        """
        item, scene_pos, abs_x, abs_y = self._get_cursor_item()

        # 只关注有 data 属性的交互 item（按钮/扇区/圆环）
        active_item = item if (item and hasattr(item, 'data') and item.isVisible()) else None

        # ── 方向盘 / 摇杆: 不走 hover_sm + click 逻辑 (各自有状态机), 但仍发 cursor_on_ui ──
        from scene.gp_stick_item import GpStickItem
        from scene.gp_wheel_item import GpWheelItem
        if isinstance(active_item, (GpStickItem, GpWheelItem)):
            # 离开上一次的非 gp_stick item (若有)
            prev_item = self._poll_hover_item
            if prev_item is not None and prev_item is not active_item:
                if hasattr(prev_item, '_hover_sm'):
                    prev_item._hover_sm.leave()
                if hasattr(prev_item, 'set_visual_state'):
                    prev_item.set_visual_state('normal')
            self._poll_hover_item = None
            self.cursor_on_ui.emit(True)
            return  # 摇杆不响应键鼠点击

        # ── 回中带每帧检测 (匹配原版: 每帧 in_rect → SetCursorPos + continue) ──
        if (active_item is not None
                and getattr(active_item.data, 'btn_type', '') == BTN_TYPE_CENTER_BAND):
            _ps = QApplication.primaryScreen()
            screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
            cx = screen.x() + screen.width() // 2
            cy = screen.y() + screen.height() // 2
            user32.SetCursorPos(cx, cy)
            if hasattr(active_item, 'set_visual_state'):
                active_item.set_visual_state('hover')
            self.cursor_on_ui.emit(True)
            return  # 跳过后续 hover/click 逻辑 (原版 continue)

        prev_item = self._poll_hover_item

        # ── hover 状态变化 ──
        if active_item != prev_item:
            # 离开旧 item
            if prev_item is not None:
                if hasattr(prev_item, '_hover_sm'):
                    prev_item._hover_sm.leave()
                if hasattr(prev_item, 'set_visual_state'):
                    # toggle 模式下 ACTIVE 状态: 按键持续按住, 视觉保持 hover 蓝
                    # 其他情况(trigger 模式 leave 后立即/延迟松开): 设 normal
                    if (hasattr(prev_item, '_hover_sm')
                            and prev_item._hover_sm.is_active):
                        prev_item.set_visual_state('hover')
                    else:
                        prev_item.set_visual_state('normal')

            # 进入新 item
            if active_item is not None:
                if hasattr(active_item, '_hover_sm'):
                    active_item._hover_sm.enter()
                    # 原版行为: 充能期间保持 normal（充能条在 normal 背景上可见）
                    # 只有 delay=0 直接激活时才立刻设 hover
                    if active_item._hover_sm.is_active:
                        if hasattr(active_item, 'set_visual_state'):
                            active_item.set_visual_state('hover')
                    # CHARGING 状态: 不设 hover，保持 normal，充能条可见
                else:
                    # 无状态机的 item，直接设 hover
                    if hasattr(active_item, 'set_visual_state'):
                        active_item.set_visual_state('hover')

            self._poll_hover_item = active_item

        # ── 通知穿透管理器当前是否在 UI 上（驱动 PT_OFF/PT_BLOCK 动态切换）──
        self.cursor_on_ui.emit(active_item is not None)

        # ── 硬件按键状态 ──
        lmb = (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0
        rmb = (user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000) != 0
        mmb = (user32.GetAsyncKeyState(VK_MBUTTON) & 0x8000) != 0

        # ── 按下检测: 光标在按钮上 + 按键刚按下 → 记录 holding + trigger 'p' ──
        if active_item and hasattr(active_item, 'data'):
            if lmb and not self._prev_lmb:
                click_key = getattr(active_item.data, 'lclick', '')
                if click_key:
                    self._holding_lclick = (active_item, click_key)
                    self.on_action_triggered(active_item.data, click_key, 'p')
                    active_item.set_visual_state('active_left')
            if rmb and not self._prev_rmb:
                rclick_key = getattr(active_item.data, 'rclick', '')
                if rclick_key:
                    self._holding_rclick = (active_item, rclick_key)
                    self.on_action_triggered(active_item.data, rclick_key, 'p')
                    active_item.set_visual_state('active_right')
            if mmb and not self._prev_mmb:
                mclick_key = getattr(active_item.data, 'mclick', '')
                if mclick_key:
                    self._holding_mclick = (active_item, mclick_key)
                    self.on_action_triggered(active_item.data, mclick_key, 'p')
                    active_item.set_visual_state('active_middle')

        # ── 释放检测: 用存储的 holding 按钮（光标可能已移走）→ trigger 'r' ──
        if not lmb and self._prev_lmb and self._holding_lclick:
            h_item, h_key = self._holding_lclick
            if _is_alive(h_item):
                self.on_action_triggered(h_item.data, h_key, 'r')
                if hasattr(h_item, '_hover_sm') and h_item._hover_sm.is_active:
                    h_item.set_visual_state('hover')
                else:
                    h_item.set_visual_state('normal')
            self._holding_lclick = None
        if not rmb and self._prev_rmb and self._holding_rclick:
            h_item, h_key = self._holding_rclick
            if _is_alive(h_item):
                self.on_action_triggered(h_item.data, h_key, 'r')
                if hasattr(h_item, 'set_visual_state'):
                    h_item.set_visual_state('hover' if (hasattr(h_item, '_hover_sm') and h_item._hover_sm.is_active) else 'normal')
            self._holding_rclick = None
        if not mmb and self._prev_mmb and self._holding_mclick:
            h_item, h_key = self._holding_mclick
            if _is_alive(h_item):
                self.on_action_triggered(h_item.data, h_key, 'r')
                if hasattr(h_item, 'set_visual_state'):
                    h_item.set_visual_state('hover' if (hasattr(h_item, '_hover_sm') and h_item._hover_sm.is_active) else 'normal')
            self._holding_mclick = None

        self._prev_lmb = lmb
        self._prev_rmb = rmb
        self._prev_mmb = mmb

    # ── 自动回中 ──

    def _poll_auto_center(self):
        """自动回中管理 (匹配原版 elapsed-time 模型 + 倒计时进度条)"""
        if self._auto_center and self._active_key_count <= 0:
            _on_btn = False
            try:
                item, scene_pos, _, _ = self._get_cursor_item()
                if item and hasattr(item, 'data'):
                    _on_btn = True
                # 光标接近中心也重置 (50px)
                if scene_pos:
                    center_x = self._scene.sceneRect().width() / 2
                    center_y = self._scene.sceneRect().height() / 2
                    if abs(scene_pos.x() - center_x) <= 50 and abs(scene_pos.y() - center_y) <= 50:
                        _on_btn = True
            except Exception:
                pass

            if _on_btn:
                self._ac_start_time = None
                self.auto_center_progress.emit(-1, 0, 0)
            else:
                now = _time.time()
                if self._ac_start_time is None:
                    self._ac_start_time = now
                elapsed_ms = (now - self._ac_start_time) * 1000
                if elapsed_ms >= self._auto_center_delay:
                    self._do_auto_center()
                    self._ac_start_time = now
                    self.auto_center_progress.emit(-1, 0, 0)
                else:
                    progress = max(0.0, 1.0 - elapsed_ms / self._auto_center_delay)
                    try:
                        if scene_pos:
                            self.auto_center_progress.emit(
                                progress, scene_pos.x() + 15, scene_pos.y())
                    except Exception:
                        pass
        else:
            self._ac_start_time = None
            self.auto_center_progress.emit(-1, 0, 0)

    def _check_hotkeys(self, hk):
        """检测快捷键，带防抖"""
        now = _time.time()

        def _debounced(name, key_name):
            if is_key_pressed(key_name):
                last = self._debounce.get(name, 0)
                if now - last > HOTKEY_DEBOUNCE_SEC:
                    self._debounce[name] = now
                    return True
            return False

        if _debounced('stop', hk.get('stop', 'f12')):
            self.stop()
            self.request_edit_mode.emit()
            return

        if _debounced('voice', hk.get('voice', 'f5')):
            self.request_toggle_voice.emit()

        if _debounced('toggle_buttons', hk.get('toggle_buttons', 'f7')):
            self.request_toggle_buttons.emit()

        if _debounced('soft_keyboard', hk.get('soft_keyboard', 'f8')):
            self.request_soft_keyboard.emit()

        if _debounced('auto_center', hk.get('auto_center', 'f6')):
            self.request_toggle_auto_center.emit()

        # 收起/展开 (默认 F4)
        if _debounced('collapse', hk.get('collapse', 'f4')):
            self.request_toggle_collapse.emit()

        # 穿透模式快捷键
        if _debounced('pt_on', hk.get('pt_on', 'f9')):
            self.passthrough_changed.emit('pt_on')
        elif _debounced('pt_off', hk.get('pt_off', 'f10')):
            self.passthrough_changed.emit('pt_off')
        elif _debounced('pt_block', hk.get('pt_block', 'f11')):
            self.passthrough_changed.emit('pt_block')

    def _dispatch_wheel(self, direction, abs_x, abs_y):
        """将滚轮事件分发到场景坐标处的 Item;
        优先级: 方向盘 active 且 LT/RT 用 scroll 模式 > 摇杆 active > 普通 item.on_wheel"""
        # 1) 方向盘 active 时, scroll 模式的 LT/RT 接收滚轮
        if self._dispatch_wheel_to_active_wheel(direction):
            return
        # 2) 摇杆 active 时, 滚轮路由到 stick.wheelup/wheeldown
        if self._active_gp_stick is not None and _is_alive(self._active_gp_stick):
            stick = self._active_gp_stick
            key = stick.data.wheelup if direction == 'up' else stick.data.wheeldown
            if key:
                self._smart_trigger(key, 'click')
            return
        try:
            global_pos = QPoint(abs_x, abs_y)
            view_pos = self._window.mapFromGlobal(global_pos)
            scene_pos = self._window.mapToScene(view_pos)
            item = self._scene.itemAt(scene_pos, self._window.transform())
            if item and hasattr(item, 'on_wheel'):
                item.on_wheel(direction)
        except Exception:
            pass

    def _poll_hardware_buttons(self):
        """轮询侧键状态（XButton1/2，Scene 事件无法捕获）"""
        xb1 = (user32.GetAsyncKeyState(0x05) & 0x8000) != 0
        xb2 = (user32.GetAsyncKeyState(0x06) & 0x8000) != 0

        if xb1 != self._prev_xb1:
            self._prev_xb1 = xb1
            self._dispatch_xbutton('xbutton1', 'p' if xb1 else 'r')

        if xb2 != self._prev_xb2:
            self._prev_xb2 = xb2
            self._dispatch_xbutton('xbutton2', 'p' if xb2 else 'r')

    def _dispatch_xbutton(self, btn_name, action):
        """侧键事件分发: 摇杆 active 时优先到 stick.xbutton1/2; 否则到鼠标下的 Item"""
        # 摇杆 active 时, 侧键路由到 stick (走 _smart_trigger 支持 gp:/gpmacro: 前缀)
        if self._active_gp_stick is not None and _is_alive(self._active_gp_stick):
            stick = self._active_gp_stick
            key = getattr(stick.data, btn_name, '')
            if key:
                self._smart_trigger(key, action)
            return

        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        cursor_pos = QPoint(pt.x, pt.y)

        view_pos = self._window.mapFromGlobal(cursor_pos)
        scene_pos = self._window.mapToScene(view_pos)
        item = self._scene.itemAt(scene_pos, self._window.transform())

        if item and hasattr(item, 'data'):
            key_val = getattr(item.data, btn_name, '')
            if key_val:
                trigger(key_val, action)
                state_name = f'active_{btn_name}'
                if action == 'p':
                    item.set_visual_state(state_name)
                else:
                    if hasattr(item, '_hover_sm') and item._hover_sm.is_active:
                        item.set_visual_state('hover')
                    else:
                        item.set_visual_state('normal')

    def _do_auto_center(self):
        """执行自动回中 — 使用实际屏幕尺寸（与原版一致）"""
        if not self._active or not self._auto_center:
            return
        _ps = QApplication.primaryScreen()
        screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
        cx = screen.x() + screen.width() // 2
        cy = screen.y() + screen.height() // 2
        user32.SetCursorPos(cx, cy)

    # ── 接收 Item 信号的槽 ──

    def on_hover_activated(self, data):
        """按钮 hover 激活 → 按下按键"""
        self._active_key_count += 1
        self._ac_start_time = None
        key = (data.hover_toggle
               if getattr(data, 'hover_mode', 'trigger') == 'toggle'
               else data.hover)
        if key:
            self._smart_trigger(key, 'p')

    def on_hover_deactivated(self, data):
        """按钮 hover 释放 → 释放按键"""
        self._active_key_count = max(0, self._active_key_count - 1)
        key = (data.hover_toggle
               if getattr(data, 'hover_mode', 'trigger') == 'toggle'
               else data.hover)
        if key:
            self._smart_trigger(key, 'r')

    def on_action_triggered(self, data, key_str, action):
        """按钮点击/滚轮 → 触发按键"""
        if action == 'p':
            self._active_key_count += 1
            self._ac_start_time = None
        elif action == 'r':
            self._active_key_count = max(0, self._active_key_count - 1)
        self._smart_trigger(key_str, action)

    def _gp_delayed_release(self, label: str):
        """vgamepad 状态机延迟释放 — 给 'click' 动作用, 确保 press 帧能被驱动看到"""
        gp = GamepadEngine.get()
        if gp is not None:
            gp.release_button(label)
            gp.flush()

    # ── 宏感知的智能触发 ──

    def _smart_trigger(self, key_str: str, action: str):
        """解析 key_str, 分离普通键、mouse:xxx / macro:name / gp:LABEL 标签, 分别执行"""
        if not key_str:
            return
        parts = [p.strip() for p in key_str.split('+')]
        normal_keys = []
        macro_names = []
        gp_macro_names = []  # gpmacro:Name (手柄宏池)
        mouse_buttons = []   # mouse:left, mouse:right, mouse:middle, mouse:x1, mouse:x2
        mouse_wheels = []    # mouse:wheelup, mouse:wheeldown
        gp_labels = []       # gp:A, gp:LB, gp:LT 等
        for p in parts:
            if p.startswith('gpmacro:'):
                gp_macro_names.append(p[8:])
            elif p.startswith('macro:'):
                macro_names.append(p[6:])
            elif p.startswith('mouse:'):
                mouse_val = p[6:]  # "left", "right", "middle", "x1", "x2", "wheelup", "wheeldown"
                if mouse_val in ('wheelup', 'wheeldown'):
                    mouse_wheels.append(mouse_val)
                else:
                    mouse_buttons.append(mouse_val)
            elif p.startswith(GP_KEY_PREFIX):
                gp_labels.append(p[len(GP_KEY_PREFIX):])
            else:
                normal_keys.append(p)

        # 普通键照常触发
        if normal_keys:
            trigger('+'.join(normal_keys), action)

        # 鼠标按钮: press → mouse_press, release → mouse_release
        for mb in mouse_buttons:
            if action == 'p':
                mouse_press(mb)
            elif action == 'r':
                mouse_release(mb)

        # 鼠标滚轮: 仅在 press/click 时触发一次 (release 忽略)
        if mouse_wheels and action in ('p', 'click'):
            for mw in mouse_wheels:
                direction = 'up' if mw == 'wheelup' else 'down'
                mouse_wheel(direction)

        # 手柄按钮: 走 gamepad_engine
        # 注意: vgamepad 是状态机不是事件队列 — press 后立即 release 净变化为 0,
        # 驱动收不到 button down 事件。'click' 必须 press → flush → 延迟 → release → flush
        if gp_labels:
            gp = GamepadEngine.get()
            if gp is not None:
                for label in gp_labels:
                    if action == 'p':
                        gp.press_button(label)
                    elif action == 'r':
                        gp.release_button(label)
                    elif action == 'click':
                        gp.press_button(label)
                        gp.flush()      # 让 press 立即可见
                        QTimer.singleShot(
                            50, lambda l=label: self._gp_delayed_release(l))
                if action != 'click':
                    gp.flush()
            else:
                logger.warning("GamepadEngine 不可用 (ViGEmBus 未加载?), 忽略手柄按键: %s", gp_labels)

        # 宏: 仅在 press / click 时触发 (release 忽略, 避免重复)
        if macro_names and action in ('p', 'click'):
            for name in macro_names:
                macro_data = self._find_macro(name, pool='kb')
                if macro_data:
                    self._execute_macro(macro_data)
                else:
                    logger.warning("Macro not found: '%s'", name)

        # 手柄宏: 同上, 查 gp_macros 池
        if gp_macro_names and action in ('p', 'click'):
            for name in gp_macro_names:
                macro_data = self._find_macro(name, pool='gp')
                if macro_data:
                    self._execute_macro(macro_data)
                else:
                    logger.warning("GP Macro not found: '%s'", name)

    # ── 摇杆轮询: 状态机 + 跨摇杆切换 + SetCursorPos 圆心 + gp engine ──

    def _poll_gp_sticks(self):
        """每帧处理所有 gp_stick item: 计算 cursor 位置 → 状态迁移 → 引擎赋值 + flush"""
        import math
        from scene.gp_stick_item import GpStickItem

        sticks = [it for it in self._scene.button_items
                  if isinstance(it, GpStickItem) and it.isVisible()]
        if not sticks and self._active_gp_stick is None:
            return

        # cursor → scene 坐标
        try:
            pt = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            view_pos = self._window.mapFromGlobal(QPoint(pt.x, pt.y))
            scene_pos = self._window.mapToScene(view_pos)
        except Exception:
            return

        # 找鼠标下最上层摇杆 (按 z 降序; 平局取后加的 = 索引大的)
        cursor_stick = None
        # 列表后加的 z 序更高 (实际 z 相同时 Qt 按添加顺序)
        for s in reversed(sticks):
            if not _is_alive(s):
                continue
            if s.is_cursor_in_circle(scene_pos):
                cursor_stick = s
                break

        active = self._active_gp_stick
        if active is not None and not _is_alive(active):
            active = None
            self._active_gp_stick = None

        # ── 状态迁移 ──
        if cursor_stick is None and active is not None:
            # 当前无入圆但有 active: 检查吸附/释放
            dist_ratio = active.cursor_distance_ratio(scene_pos)
            if dist_ratio > active.data.release_threshold_ratio:
                self._release_active_stick()
            else:
                self._update_stick_value(active, scene_pos, sticking=True)
        elif cursor_stick is not None and cursor_stick is active:
            # 仍在同一 active 摇杆: 正常更新
            self._update_stick_value(active, scene_pos, sticking=False)
        elif cursor_stick is not None and cursor_stick is not active:
            # 跨摇杆切换 或 首次激活: 释放老的 + 激活新的
            if active is not None:
                self._release_active_stick()
            self._activate_stick(cursor_stick)

        # active stick 下: 检测鼠标键边沿 → 触发 stick 鼠标动作字段
        if self._active_gp_stick is not None and _is_alive(self._active_gp_stick):
            self._poll_stick_mouse_actions(self._active_gp_stick)

        # 帧末 flush
        gp = GamepadEngine.get()
        if gp is not None:
            gp.flush()

    def _activate_stick(self, stick):
        """激活摇杆: SetCursorPos 到圆心 (屏幕坐标), 状态 → active, 引擎 (0,0)"""
        try:
            center_scene = stick.circle_center_scene()
            view_pt = self._window.mapFromScene(center_scene)
            screen_pt = self._window.mapToGlobal(view_pt)
            user32.SetCursorPos(int(screen_pt.x()), int(screen_pt.y()))
        except Exception as e:
            logger.warning("SetCursorPos to stick center failed: %s", e)
        self._active_gp_stick = stick
        stick.set_stick_visual('active', 0.0, 0.0)
        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_stick(stick.data.stick_id, 0.0, 0.0)

    def _release_active_stick(self):
        """释放 active 摇杆: 状态 → idle, 引擎 (0,0); 顺便释放本 stick 的鼠标动作 held 键"""
        stick = self._active_gp_stick
        if stick is None:
            return
        if _is_alive(stick):
            # 释放鼠标动作 held 键 (lclick/rclick/mclick), 防卡键
            for prev_attr, key_field in (
                ('_prev_lmb', 'lclick'),
                ('_prev_rmb', 'rclick'),
                ('_prev_mmb', 'mclick'),
            ):
                if getattr(self, prev_attr):
                    key = getattr(stick.data, key_field, '')
                    if key:
                        self._smart_trigger(key, 'r')
            stick.set_stick_visual('idle', 0.0, 0.0)
            gp = GamepadEngine.get()
            if gp is not None:
                gp.set_stick(stick.data.stick_id, 0.0, 0.0)
        self._active_gp_stick = None

    def _poll_stick_mouse_actions(self, stick):
        """active stick 下的鼠标键边沿检测 → 触发 stick.lclick/rclick/mclick
        共享 self._prev_lmb 等状态; _poll_hover_and_click 在 stick 模式下不再处理边沿。
        同时根据当前按下的鼠标键, 设置 stick 小球的颜色 + 显示触发键文本。"""
        from scene.gp_stick_item import _gp_display

        lmb = (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0
        rmb = (user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000) != 0
        mmb = (user32.GetAsyncKeyState(VK_MBUTTON) & 0x8000) != 0
        for new_state, prev_attr, key_field in (
            (lmb, '_prev_lmb', 'lclick'),
            (rmb, '_prev_rmb', 'rclick'),
            (mmb, '_prev_mmb', 'mclick'),
        ):
            if new_state != getattr(self, prev_attr):
                key = getattr(stick.data, key_field, '')
                if key:
                    self._smart_trigger(key, 'p' if new_state else 'r')
                setattr(self, prev_attr, new_state)

        # 选当前 hold 的优先级最高的鼠标键, 设小球颜色 + 显示键文本 (优先 LMB > RMB > MMB)
        if self._prev_lmb and stick.data.lclick:
            stick.set_pressed_action('lclick', _gp_display(stick.data.lclick))
        elif self._prev_rmb and stick.data.rclick:
            stick.set_pressed_action('rclick', _gp_display(stick.data.rclick))
        elif self._prev_mmb and stick.data.mclick:
            stick.set_pressed_action('mclick', _gp_display(stick.data.mclick))
        else:
            stick.set_pressed_action(None, '')

    def _update_stick_value(self, stick, scene_pos, sticking: bool):
        """根据 cursor 位置算 stick 值 (含死区/曲线/八向锁) + 更新视觉 + 引擎
        八方向锁定时, 视觉小球位置 AND 引擎值都吸附到 8 个固定方向。"""
        import math
        center = stick.circle_center_scene()
        dx = scene_pos.x() - center.x()
        dy = scene_pos.y() - center.y()
        r = stick.circle_radius_scene()
        if r <= 0:
            return
        norm_x = dx / r
        norm_y = dy / r
        mag = math.sqrt(norm_x * norm_x + norm_y * norm_y)

        # 1) 计算视觉位置 (vis_x, vis_y) + 状态
        if sticking or mag >= 1.0:
            state = 'sticking'
            if mag > 0:
                vis_x = norm_x / mag
                vis_y = norm_y / mag
            else:
                vis_x = vis_y = 0.0
        else:
            state = 'active'
            vis_x = norm_x
            vis_y = norm_y

        # 2) 计算引擎值 (含死区缩放)
        if state == 'sticking':
            out_x, out_y = vis_x, vis_y
        else:
            dz = max(0.0, min(0.5, stick.data.dead_zone))
            if mag < dz:
                out_x = out_y = 0.0
            else:
                scale = (mag - dz) / (1.0 - dz) if (1.0 - dz) > 0 else 1.0
                out_x = (norm_x / mag) * scale if mag > 0 else 0.0
                out_y = (norm_y / mag) * scale if mag > 0 else 0.0

        # 3) 灵敏度曲线 (square: 微调精度提升)
        if stick.data.sensitivity_curve == 'square':
            out_x = math.copysign(out_x * out_x, out_x)
            out_y = math.copysign(out_y * out_y, out_y)

        # 4) 八方向锁定: 视觉 + 引擎 同步吸附到最近的 45° 方向
        if stick.data.eight_way:
            if abs(vis_x) > 1e-4 or abs(vis_y) > 1e-4:
                vang = math.atan2(vis_y, vis_x)
                vsnap = round(vang / (math.pi / 4)) * (math.pi / 4)
                vm = min(1.0, math.sqrt(vis_x * vis_x + vis_y * vis_y))
                vis_x = math.cos(vsnap) * vm
                vis_y = math.sin(vsnap) * vm
            if abs(out_x) > 1e-4 or abs(out_y) > 1e-4:
                ang = math.atan2(out_y, out_x)
                snap = round(ang / (math.pi / 4)) * (math.pi / 4)
                m = min(1.0, math.sqrt(out_x * out_x + out_y * out_y))
                out_x = math.cos(snap) * m
                out_y = math.sin(snap) * m

        # 5) sticking 进度: 0=刚出圆, 1=即将释放; 用于绘制圆外蓝色进度条
        sticking_progress = 0.0
        if state == 'sticking':
            ratio = stick.data.release_threshold_ratio
            if ratio > 1.0:
                sticking_progress = max(0.0, min(1.0, (mag - 1.0) / (ratio - 1.0)))

        # 6) 视觉 + 引擎赋值 (引擎 Y 翻转: 屏幕 down 正 → 手柄 up 正)
        stick.set_stick_visual(state, vis_x, vis_y, sticking_progress=sticking_progress)
        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_stick(stick.data.stick_id,
                         max(-1.0, min(1.0, out_x)),
                         max(-1.0, min(1.0, -out_y)))

    # ── 方向盘 (gp_wheel) 单例状态机 ──

    def _poll_gp_wheel(self):
        """单例方向盘: 入区 SetCursorPos 中心 + steering 归零;
           运行中 steering 跟随鼠标 X (距中心 / 半宽), LT/RT 按各自 mode 更新;
           出 release zone (距中心 > 半宽 × ratio) → steering + LT + RT 全归零"""
        import math
        from scene.gp_wheel_item import GpWheelItem

        wheel = next((it for it in self._scene.button_items
                      if isinstance(it, GpWheelItem) and it.isVisible()), None)
        if wheel is None and self._active_gp_wheel is None:
            return

        try:
            pt = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            screen_pt = QPoint(pt.x, pt.y)
            view_pos = self._window.mapFromGlobal(screen_pt)
            scene_pos = self._window.mapToScene(view_pos)
        except Exception:
            return

        active = self._active_gp_wheel
        if active is not None and not _is_alive(active):
            active = None
            self._active_gp_wheel = None

        if wheel is None:
            # wheel 被删 但 active 还残留: 释放
            if active is not None:
                self._release_gp_wheel()
            return

        in_rect = wheel.is_cursor_in_rect(scene_pos)

        if not in_rect and active is not None:
            dist_ratio = active.cursor_distance_ratio(scene_pos)
            if dist_ratio > active.data.release_threshold_ratio:
                self._release_gp_wheel()
            else:
                # 在 release zone 内: steering 钉边缘 (sticky); 但 vertical 扳机仍跟随 Y
                # (用户期望: 阈值范围内 vertical 一直有效, 不会因为离开方块就停)
                self._update_wheel_steering(active, scene_pos, force_edge=True)
                self._update_wheel_triggers(active, screen_pt)
                self._sync_wheel_visual(active)
        elif in_rect and wheel is active:
            self._update_wheel_steering(active, scene_pos, force_edge=False)
            self._update_wheel_triggers(active, screen_pt)
            self._sync_wheel_visual(active)
        elif in_rect and wheel is not active:
            if active is not None:
                self._release_gp_wheel()
            self._activate_gp_wheel(wheel)

        gp = GamepadEngine.get()
        if gp is not None:
            gp.flush()

    def _activate_gp_wheel(self, wheel):
        """入区瞬移光标到矩形中心 + steering = 0; LT/RT 值保持上次"""
        try:
            center = wheel.rect_center_scene()
            view_pt = self._window.mapFromScene(center)
            screen_pt = self._window.mapToGlobal(view_pt)
            user32.SetCursorPos(int(screen_pt.x()), int(screen_pt.y()))
            self._wheel_last_screen_y = int(screen_pt.y())
        except Exception as e:
            logger.warning("SetCursorPos to wheel center failed: %s", e)
        self._active_gp_wheel = wheel
        # marker 模式: 初始浮标 = 当前扳机值 (保持视觉连贯)
        self._wheel_lt_marker_pos = self._wheel_lt
        self._wheel_rt_marker_pos = self._wheel_rt
        self._wheel_lmb_was_down = False
        self._wheel_rmb_was_down = False
        wheel.set_visual(0.0, self._wheel_lt, self._wheel_rt, active=True)
        self._sync_wheel_visual(wheel)
        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_stick("L", 0.0, 0.0)
            gp.set_trigger("L", self._wheel_lt)
            gp.set_trigger("R", self._wheel_rt)

    def _release_gp_wheel(self):
        """steering + LT + RT 全归零, 方向盘 idle"""
        wheel = self._active_gp_wheel
        if wheel is None:
            return
        if _is_alive(wheel):
            wheel.set_visual(0.0, 0.0, 0.0, active=False)
            if hasattr(wheel, 'set_markers'):
                wheel.set_markers(None, None)
            if hasattr(wheel, 'set_pressed_action'):
                wheel.set_pressed_action(None, '')
        self._wheel_lt = 0.0
        self._wheel_rt = 0.0
        self._wheel_lt_marker_pos = 0.0
        self._wheel_rt_marker_pos = 0.0
        self._wheel_lmb_was_down = False
        self._wheel_rmb_was_down = False
        self._wheel_mmb_was_down = False
        self._wheel_x1_was_down = False
        self._wheel_x2_was_down = False
        # 释放所有 holding 的鼠标动作 (触发 'r' 防止键卡住)
        for field, key_str in list(self._wheel_mouse_holding.items()):
            try:
                self.on_action_triggered(wheel.data if _is_alive(wheel) else None,
                                          key_str, 'r')
            except Exception:
                pass
        self._wheel_mouse_holding.clear()
        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_stick("L", 0.0, 0.0)
            gp.set_trigger("L", 0.0)
            gp.set_trigger("R", 0.0)
        self._active_gp_wheel = None

    def _update_wheel_steering(self, wheel, scene_pos, force_edge: bool):
        """计算 steering 并写入引擎 (仅左摇杆 X 轴, Y 始终 0); 含中心死区"""
        import math
        cx = wheel.rect_center_scene().x()
        half_w = max(1.0, wheel.half_width_scene())
        dx = scene_pos.x() - cx
        val = max(-1.0, min(1.0, dx / half_w))
        if force_edge:
            val = max(-1.0, min(1.0, val))
        # 死区: |val| < dz → 0; dz~1 重新映射成 0~1 (平滑过渡)
        dz = max(0.0, min(0.95, getattr(wheel.data, 'dead_zone', 0.0)))
        abs_v = abs(val)
        if abs_v < dz:
            val = 0.0
        elif dz > 0:
            val = math.copysign((abs_v - dz) / (1.0 - dz), val)
        # 灵敏度曲线 (死区之后再施加, 让 dz~1 区段保持平方曲线特性)
        if wheel.data.sensitivity_curve == 'square':
            val = math.copysign(val * val, val)
        self._wheel_steering_last = val
        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_stick("L", val, 0.0)

    def _update_wheel_triggers(self, wheel, screen_pt: QPoint):
        """根据 LT/RT 各自 mode 更新值; scroll 由 _dispatch_wheel 异步处理 (不在此 tick)"""
        # vertical mode: 用 screen Y delta (上 = 屏幕 Y 减小, value +)
        cur_y = int(screen_pt.y())
        dy = cur_y - self._wheel_last_screen_y
        self._wheel_last_screen_y = cur_y

        lmb = (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0
        rmb = (user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000) != 0
        dt_ms = max(1, self._timer.interval())

        # marker 模式: 边沿检测 (按下→ click 一次, 持续按住不重复)
        lmb_edge_down = lmb and not self._wheel_lmb_was_down
        rmb_edge_down = rmb and not self._wheel_rmb_was_down

        for prefix, val_attr, marker_attr in (
                ('lt', '_wheel_lt', '_wheel_lt_marker_pos'),
                ('rt', '_wheel_rt', '_wheel_rt_marker_pos')):
            mode = getattr(wheel.data, f'{prefix}_mode')
            reverse = bool(getattr(wheel.data, f'{prefix}_reverse', False))
            cur = getattr(self, val_attr)
            if mode == 'vertical':
                # 0→1 所需 Y 位移 = 方向盘高度 × pct (方向盘是方形, w == h)
                # reverse: 上→减, 下→加 (默认是 上→加, 下→减)
                pct = max(0.05, min(0.95, getattr(wheel.data, f'{prefix}_vertical_pct')))
                px_per = max(1.0, wheel.data.w * pct)
                sign = 1.0 if reverse else -1.0
                cur = max(0.0, min(1.0, cur + sign * dy / px_per))
            elif mode == 'buttons':
                # reverse: 互换 LMB / RMB 含义
                ms = max(1, getattr(wheel.data, f'{prefix}_buttons_ms'))
                step = getattr(wheel.data, f'{prefix}_buttons_step')
                rate = step / ms  # value per ms
                add_btn, sub_btn = (rmb, lmb) if reverse else (lmb, rmb)
                if add_btn:
                    cur = min(1.0, cur + rate * dt_ms)
                if sub_btn:
                    cur = max(0.0, cur - rate * dt_ms)
            elif mode == 'marker':
                # marker: 移动鼠标 → 浮标位置变 (不写扳机); 按对应键 → 扳机值 = 浮标位置
                pct = max(0.05, min(0.95, getattr(wheel.data, f'{prefix}_marker_pct')))
                px_per = max(1.0, wheel.data.w * pct)
                sign = 1.0 if reverse else -1.0
                m_pos = getattr(self, marker_attr)
                m_pos = max(0.0, min(1.0, m_pos + sign * dy / px_per))
                setattr(self, marker_attr, m_pos)
                # 检查 click 锁定 (扳机配的键边沿按下时)
                btn = getattr(wheel.data, f'{prefix}_marker_button', 'L')
                clicked = (btn == 'L' and lmb_edge_down) or (btn == 'R' and rmb_edge_down)
                if clicked:
                    cur = m_pos    # 锁定扳机值到当前浮标位置
            # scroll 模式: 由 _dispatch_wheel 处理, 此处不动
            setattr(self, val_attr, cur)

        # ── 其他鼠标按键 (优先级低于 LT/RT) ──
        # 读 mmb/x1/x2 (lmb/rmb 已在上面读); 算占用集; 边沿触发对应动作
        from scene.gp_stick_item import _gp_display
        mmb = (user32.GetAsyncKeyState(VK_MBUTTON) & 0x8000) != 0
        x1 = (user32.GetAsyncKeyState(VK_XBUTTON1) & 0x8000) != 0
        x2 = (user32.GetAsyncKeyState(VK_XBUTTON2) & 0x8000) != 0
        occupied = _wheel_occupied_fields(wheel.data)
        # 对每个鼠标按键: (字段名, 当前按下, 上次按下)
        mouse_btn_events = (
            ('lclick',   lmb, self._wheel_lmb_was_down),
            ('rclick',   rmb, self._wheel_rmb_was_down),
            ('mclick',   mmb, self._wheel_mmb_was_down),
            ('xbutton1', x1,  self._wheel_x1_was_down),
            ('xbutton2', x2,  self._wheel_x2_was_down),
        )
        for field, now_down, was_down in mouse_btn_events:
            key_str = getattr(wheel.data, f'mouse_{field}', '') or ''
            # 边沿按下: 字段未被占用 + 有映射 → 触发 'p' + 记 holding
            if now_down and not was_down:
                if field not in occupied and key_str:
                    self._wheel_mouse_holding[field] = key_str
                    self.on_action_triggered(wheel.data, key_str, 'p')
            # 边沿松开: 若 holding 中有该字段 → 触发 'r'
            elif (not now_down) and was_down and field in self._wheel_mouse_holding:
                hk = self._wheel_mouse_holding.pop(field)
                self.on_action_triggered(wheel.data, hk, 'r')

        # 推 hub 视觉: 优先级 lclick > rclick > mclick > x1 > x2
        # 持有中的第一个 → 中心 hub 着色 + 显示键文本; 都没持有 → 只清「按钮类」hub
        # (滚轮类 wheelup/wheeldown 由 _dispatch_wheel_to_active_wheel 的 QTimer 自己清,
        #  此处不能动, 否则下一 tick 立即覆盖掉滚轮闪烁)
        if hasattr(wheel, 'set_pressed_action'):
            shown = None
            for f in ('lclick', 'rclick', 'mclick', 'xbutton1', 'xbutton2'):
                if f in self._wheel_mouse_holding:
                    shown = (f, _gp_display(self._wheel_mouse_holding[f]))
                    break
            if shown:
                wheel.set_pressed_action(shown[0], shown[1])
            else:
                cur = getattr(wheel, '_pressed_action', None)
                if cur in ('lclick', 'rclick', 'mclick', 'xbutton1', 'xbutton2'):
                    wheel.set_pressed_action(None, '')

        # 诊断日志: 任意鼠标键边沿事件都打一行, 帮排查"hub 不显示"问题
        for field, now_down, was_down in mouse_btn_events:
            if now_down != was_down:
                key_str = getattr(wheel.data, f'mouse_{field}', '') or ''
                blocked = field in occupied
                fired = field in self._wheel_mouse_holding and now_down
                logger.info(f"[wheel mouse] {field} {'↓' if now_down else '↑'} "
                            f"key={key_str!r} blocked={blocked} fired_p={fired}")

        # 记录本帧鼠标键状态供下帧边沿检测
        self._wheel_lmb_was_down = lmb
        self._wheel_rmb_was_down = rmb
        self._wheel_mmb_was_down = mmb
        self._wheel_x1_was_down = x1
        self._wheel_x2_was_down = x2

        # 鼠标动作叠加: 持有中的鼠标键如果映射了 gp:LT / gp:RT, 当前应为 1.0
        # 跟 wheel 自己的 LT/RT 取 max → 互不影响进度条 (wheel 进度条只显示 _wheel_lt/_rt)
        override_lt = 0.0
        override_rt = 0.0
        for field in ('lclick', 'rclick', 'mclick', 'xbutton1', 'xbutton2'):
            if field in self._wheel_mouse_holding:
                key = self._wheel_mouse_holding[field]
                for p in key.split('+'):
                    p = p.strip()
                    if p == f'{GP_KEY_PREFIX}LT':
                        override_lt = 1.0
                    elif p == f'{GP_KEY_PREFIX}RT':
                        override_rt = 1.0
        final_lt = max(self._wheel_lt, override_lt)
        final_rt = max(self._wheel_rt, override_rt)

        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_trigger("L", final_lt)
            gp.set_trigger("R", final_rt)

    def _sync_wheel_visual(self, wheel):
        """把 active 状态最新的 steering + LT + RT + marker 同步到 item"""
        steering = getattr(self, '_wheel_steering_last', 0.0)
        wheel.set_visual(steering, self._wheel_lt, self._wheel_rt, active=True)
        if hasattr(wheel, 'set_markers'):
            lt_m = self._wheel_lt_marker_pos if wheel.data.lt_mode == 'marker' else None
            rt_m = self._wheel_rt_marker_pos if wheel.data.rt_mode == 'marker' else None
            wheel.set_markers(lt_m, rt_m)

    def _dispatch_wheel_to_active_wheel(self, direction: str) -> bool:
        """方向盘 active 时, scroll 事件交给配 scroll 模式的 trigger; 返回 True 表示已消费"""
        wheel = self._active_gp_wheel
        if wheel is None or not _is_alive(wheel):
            return False
        handled = False
        for prefix, val_attr in (('lt', '_wheel_lt'), ('rt', '_wheel_rt')):
            if getattr(wheel.data, f'{prefix}_mode') != 'scroll':
                continue
            step = getattr(wheel.data, f'{prefix}_scroll_step')
            reverse = bool(getattr(wheel.data, f'{prefix}_reverse', False))
            cur = getattr(self, val_attr)
            # 默认: 上→加, 下→减; reverse: 上→减, 下→加
            effective_up = (direction == 'up')
            if reverse:
                effective_up = not effective_up
            if effective_up:
                cur = min(1.0, cur + step)
            else:
                cur = max(0.0, cur - step)
            setattr(self, val_attr, cur)
            handled = True
        if handled:
            gp = GamepadEngine.get()
            if gp is not None:
                gp.set_trigger("L", self._wheel_lt)
                gp.set_trigger("R", self._wheel_rt)
                gp.flush()
            self._sync_wheel_visual(wheel)
            return True

        # 没被 scroll 模式扳机消费 → 尝试触发 wheel.data.mouse_wheelup / mouse_wheeldown
        # (优先级低于 LT/RT 的 scroll 模式; 若 LT/RT 任一 scroll, 占用所以这里已 return)
        field = 'wheelup' if direction == 'up' else 'wheeldown'
        key_str = getattr(wheel.data, f'mouse_{field}', '') or ''
        if key_str:
            # 滚轮事件 = 一次性 click; _smart_trigger 内 click 对 gp 走延迟 release
            self._smart_trigger(key_str, 'click')
            # hub 视觉闪一下 ~200ms (scroll 是瞬时事件没有 hold)
            if hasattr(wheel, 'set_pressed_action'):
                from scene.gp_stick_item import _gp_display
                wheel.set_pressed_action(field, _gp_display(key_str))
                QTimer.singleShot(200, lambda w=wheel:
                                  w.set_pressed_action(None, '') if _is_alive(w) else None)
            return True
        return False

    def _find_macro(self, name: str, pool: str = 'kb'):
        """从当前 config 中查找宏。pool='kb' 查 macros, pool='gp' 查 gp_macros"""
        config = self._scene.get_config() if hasattr(self._scene, 'get_config') else {}
        field = 'gp_macros' if pool == 'gp' else 'macros'
        for m in config.get(field, []):
            if m.get('name') == name:
                return m
        return None

    def _execute_macro(self, macro_data: dict):
        """在后台线程中顺序执行宏步骤 (避免 delay 阻塞主循环)

        支持两种步骤格式:
          - type='key':  {"type":"key", "key":"a+b", "action":"click"}
          - type='delay': {"type":"delay", "ms":100}
          - 旧格式(兼容): {"keys":"a+b", "action":"click", "delay":50}
        """
        steps = macro_data.get('steps', [])
        repeat = max(1, macro_data.get('repeat', 1))
        name = macro_data.get('name', '?')
        if not steps:
            return

        def _run():
            for r in range(repeat):
                for step in steps:
                    if not self._active:
                        return
                    step_type = step.get('type', 'key')

                    if step_type == 'delay':
                        # 延迟步骤: {"type":"delay", "ms":100}
                        ms = step.get('ms', 50)
                        if ms > 0:
                            _time.sleep(ms / 1000.0)

                    elif step_type == 'key':
                        # 按键步骤: {"type":"key", "key":"a+b", "action":"click"}
                        # 兼容旧格式 "keys" 字段
                        # 使用 _smart_trigger 以支持 mouse: 和 macro: 前缀
                        keys = step.get('key', '') or step.get('keys', '')
                        act = step.get('action', 'click')
                        if keys:
                            if act == 'click':
                                self._smart_trigger(keys, 'p')
                                self._smart_trigger(keys, 'r')
                            elif act == 'press':
                                self._smart_trigger(keys, 'p')
                            elif act == 'release':
                                self._smart_trigger(keys, 'r')
                        # 旧格式可能有内嵌 delay
                        delay = step.get('delay', 0)
                        if delay > 0:
                            _time.sleep(delay / 1000.0)

                    else:
                        # 未知类型，尝试旧格式兼容
                        keys = step.get('keys', '') or step.get('key', '')
                        act = step.get('action', 'click')
                        delay = step.get('delay', 50)
                        if keys:
                            if act == 'click':
                                self._smart_trigger(keys, 'p')
                                self._smart_trigger(keys, 'r')
                            elif act == 'press':
                                self._smart_trigger(keys, 'p')
                            elif act == 'release':
                                self._smart_trigger(keys, 'r')
                        if delay > 0:
                            _time.sleep(delay / 1000.0)

            logger.info("Macro '%s' executed (repeat=%d, steps=%d)", name, repeat, len(steps))

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    # ── 语音引擎集成 ──

    def _start_voice(self, voice_config: dict = None):
        """根据配置启动语音引擎"""
        if not voice_config:
            return
        if not voice_config.get('voice_enabled', False):
            return
        commands = voice_config.get('voice_commands', [])
        language = voice_config.get('voice_language', 'zh-CN')
        mic_device = voice_config.get('voice_mic_device', None)
        if not commands:
            return

        try:
            from engine.voice_engine import VoiceEngine
            self._voice_engine = VoiceEngine(self)
            self._voice_engine.command_recognized.connect(self._on_voice_command)
            self._voice_engine.error_occurred.connect(
                lambda e: logger.warning(f"语音引擎错误: {e}"))
            self._voice_engine.start(commands, language, mic_device=mic_device)
        except Exception as e:
            logger.warning(f"语音引擎启动失败: {e}")
            self._voice_engine = None

    def _stop_voice(self):
        """停止语音引擎"""
        if self._voice_engine:
            try:
                self._voice_engine.stop()
            except Exception as e:
                logger.warning(f"语音引擎停止异常: {e}")
            self._voice_engine = None

    def _on_voice_command(self, phrase: str, keys: str, action: str, latency_ms: int = 0):
        """语音指令识别回调 → 触发按键 (支持宏)"""
        if not self._active or not keys:
            return
        if action == 'click':
            self._smart_trigger(keys, 'p')
            self._smart_trigger(keys, 'r')
        elif action == 'press':
            self._smart_trigger(keys, 'p')
        elif action == 'release':
            self._smart_trigger(keys, 'r')
        self.voice_command_triggered.emit(phrase, keys, action)
        logger.info(f"语音指令触发: '{phrase}' → keys='{keys}', action='{action}'")
