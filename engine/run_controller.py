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
import os
import threading
import time as _time

from PyQt6.QtCore import QObject, QTimer, QPoint, QRect, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.input_engine import (
    trigger, is_key_pressed, poll_wheel_events, release_all_keys,
    mouse_press, mouse_release, mouse_wheel,
)
from core.config_manager import load_hotkeys
from core import action_service
from core.constants import (
    UPDATE_INTERVAL, BTN_TYPE_CENTER_BAND, HOTKEY_DEBOUNCE_SEC,
    GP_KEY_PREFIX, APP_PREFIX,
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


# WASD 模式 8 扇区 → 方向集映射 (atan2 屏幕坐标, y 向下为正; 索引 = round(angle/45°)%8)
#   0=右 1=右下 2=下 3=左下 4=左 5=左上 6=上 7=右上
_WASD_SECTOR_DIRS = (
    ('right',), ('down', 'right'), ('down',), ('down', 'left'),
    ('left',), ('up', 'left'), ('up',), ('up', 'right'),
)
_WASD_DIR_FIELD = {
    'up': 'wasd_up', 'down': 'wasd_down', 'left': 'wasd_left', 'right': 'wasd_right',
}


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
    request_toggle_cursor = pyqtSignal()    # F3: 切换自绘光标显隐

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
        # WASD 模式当前按住的方向集 ({'up','down','left','right'} 子集), 用于边沿 press/release
        self._stick_wasd_held: set = set()
        # 应用启动冷却 {path: 上次启动时间}, 防长按/连点重复启动
        self._app_cooldown: dict = {}

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

        # 方向盘「轻松操控」模式状态 (control_mode == 'easy')
        self._easy_last_y: int | None = None       # 上一帧鼠标 Y (用于速度映射)
        self._easy_last_mx: int | None = None      # 上一帧鼠标 X (用于横向位移检测)
        self._easy_smooth_dx: float = 0.0          # EMA 平滑后的 dx (过滤手抖)
        self._easy_rt: float = 0.0                 # 当前累计的 RT (0~1)
        # 转向延迟状态机: fill 0~1 (引擎量), dir 当前方向, key_down 实际按下的键
        self._easy_dir: int = 0                    # -1=左/A, 0=空, +1=右/D
        self._easy_fill: float = 0.0               # 0~1, 触发涨/释放退
        self._easy_key_down: int = 0               # 当前实际按下的键 (-1/0/+1)
        self._easy_steer_tick: float | None = None # 转向状态机 dt 计时
        self._easy_brake_state: bool = False       # 左键 → S 按住状态
        self._easy_visual_steer: float = 0.0       # 视觉转向值 = dir×fill

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
        # 轻松操控模式状态重置
        self._easy_last_y = None
        self._easy_last_mx = None
        self._easy_smooth_dx = 0.0
        self._easy_rt = 0.0
        self._easy_dir = 0
        self._easy_fill = 0.0
        self._easy_key_down = 0
        self._easy_steer_tick = None
        self._easy_brake_state = False
        self._easy_visual_steer = 0.0
        self._timer.start()

        # 启动语音引擎
        self._start_voice(voice_config)

    def _release_all_inputs(self):
        """释放一切对当前 scene item 的引用 + 按住的键/鼠标/手柄, 并重置 hover 状态机。

        供 stop() 与 prepare_hot_reload() 共用。调用时 scene item 引用须仍有效
        (热重载场景下要在清场之前调)。
        """
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
        # 释放轻松操控模式残留的 A/D/S
        self._release_easy_state()
        gp = GamepadEngine.get()
        if gp is not None:
            gp.release_all()

    def prepare_hot_reload(self):
        """配置热重载前调用: 释放所有按住状态与对当前 item 的引用, 但保持运行
        (timer/voice/_active 不动)。调用方随后可安全清场+重建 scene, RunController
        下一帧会自动轮询到新 item。"""
        if not self._active:
            return
        self._release_all_inputs()
        self._prev_lmb = False
        self._prev_rmb = False
        self._prev_mmb = False
        logger.info("RunController 已为热重载释放输入状态")

    def stop(self):
        """退出运行模式"""
        self._active = False
        self._timer.stop()
        self._ac_start_time = None
        self._stop_voice()
        self._active_key_count = 0
        self._release_all_inputs()
        self.auto_center_progress.emit(-1, 0, 0)

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

        # ── 回中带每帧检测 (in_rect → SetCursorPos 到配置的回中目标中心) ──
        if (active_item is not None
                and getattr(active_item.data, 'btn_type', '') == BTN_TYPE_CENTER_BAND):
            target = getattr(active_item.data, 'recenter_target', 'screen') or 'screen'
            pos = self._resolve_recenter_pos(target)
            if pos is None:   # 目标失效 → 回退屏幕中心
                pos = self._resolve_recenter_pos('screen')
            if pos is not None:
                user32.SetCursorPos(pos[0], pos[1])
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
                # 光标接近中心也重置 (50px) — 中心点跟随移动后的中心轮盘
                if scene_pos:
                    wc = (self._scene.wheel_center_scene()
                          if hasattr(self._scene, 'wheel_center_scene') else None)
                    if wc is not None:
                        center_x, center_y = wc.x(), wc.y()
                    else:
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

        # 光标显隐 (默认 F3)
        if _debounced('cursor', hk.get('cursor', 'f3')):
            self.request_toggle_cursor.emit()

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
                # hub 视觉闪一下 ~200ms (跟方向盘对齐: 小球变 ACTION_COLORS 配色 + 显示键文本)
                # _poll_stick_mouse_actions 末尾不会清滚轮类状态, 由这里的 QTimer 自己清
                if hasattr(stick, 'set_pressed_action'):
                    from scene.gp_stick_item import _gp_display
                    field = 'wheelup' if direction == 'up' else 'wheeldown'
                    stick.set_pressed_action(field, _gp_display(key))
                    QTimer.singleShot(200, lambda s=stick, f=field:
                        s.set_pressed_action(None, '') if _is_alive(s) and
                        getattr(s, '_pressed_action', None) == f else None)
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

    def on_hover_repeat(self, data):
        """hover 按住期间按触发间隔补发一次 down (方案A: 模拟长按自动重复)

        键已在 on_hover_activated 时按下并计入 _active_key_count, 这里只是重复发
        down 让"看重复 keydown 流"的目标程序识别为长按, 不改计数、不发 up。
        """
        key = (data.hover_toggle
               if getattr(data, 'hover_mode', 'trigger') == 'toggle'
               else data.hover)
        if key:
            self._smart_trigger(key, 'p')

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
        """解析 key_str, 分离普通键、mouse:xxx / macro:name / gp:LABEL 标签, 分别执行

        action 归一化: touch_button_item / wheel_sector_item / wheel_ring_item 的滚轮
        信号 emit 'c' (跟 input_engine.trigger 一致), 但本函数内部 + 手柄分支用 'click'。
        历史上 'c' 进来后手柄分支三路 (p/r/click) 全 miss → 手柄按键 (含 LT/RT) 静默丢弃。
        """
        if not key_str:
            return
        if action == 'c':
            action = 'click'
        parts = [p.strip() for p in key_str.split('+')]
        normal_keys = []
        macro_names = []
        gp_macro_names = []  # gpmacro:Name (手柄宏池, 兼容旧数据)
        x_macro_names = []   # xmacro:Name (统一混合宏池)
        mouse_buttons = []   # mouse:left, mouse:right, mouse:middle, mouse:x1, mouse:x2
        mouse_wheels = []    # mouse:wheelup, mouse:wheeldown
        gp_labels = []       # gp:A, gp:LB, gp:LT 等
        app_targets = []     # app:<应用名> 启动本地应用
        recenter_targets = []  # recenter:<目标> 光标回中
        for p in parts:
            if p.startswith(APP_PREFIX):
                app_targets.append(p[len(APP_PREFIX):])
            elif p.startswith('recenter:'):
                recenter_targets.append(p[len('recenter:'):])
            elif p.startswith('xmacro:'):
                x_macro_names.append(p[7:])
            elif p.startswith('gpmacro:'):
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

        # 普通键照常触发 — input_engine.trigger 用 'c' 表 click
        if normal_keys:
            trigger('+'.join(normal_keys), 'c' if action == 'click' else action)

        # 鼠标按钮: press → mouse_press, release → mouse_release, click → 按下+延迟释放
        for mb in mouse_buttons:
            if action == 'p':
                mouse_press(mb)
            elif action == 'r':
                mouse_release(mb)
            elif action == 'click':
                mouse_press(mb)
                QTimer.singleShot(40, lambda b=mb: mouse_release(b))

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

        # 手柄宏: 同上, 查 gp_macros 池 (兼容旧数据)
        if gp_macro_names and action in ('p', 'click'):
            for name in gp_macro_names:
                macro_data = self._find_macro(name, pool='gp')
                if macro_data:
                    self._execute_macro(macro_data)
                else:
                    logger.warning("GP Macro not found: '%s'", name)

        # 统一混合宏: 查 xmacros 池
        if x_macro_names and action in ('p', 'click'):
            for name in x_macro_names:
                macro_data = self._find_macro(name, pool='x')
                if macro_data:
                    self._execute_macro(macro_data)
                else:
                    logger.warning("X Macro not found: '%s'", name)

        # 本地应用: 启动程序与"点击/长按/释放"动作无关, 任意动作都启动;
        # 靠 _launch_app 的冷却去重 (一次点击发 p+r 两次 → 只开一次)
        if app_targets:
            for name in app_targets:
                self._launch_app(name)

        # 回中: 光标移到目标中心 (与动作无关; 移到同点是幂等的)
        if recenter_targets:
            for tgt in recenter_targets:
                self._do_recenter(tgt)

    def _resolve_recenter_pos(self, key: str):
        """回中目标 → 屏幕坐标 (x, y); 解析不到返回 None。
        key: 'screen' | 'center_ring' | 'wheel' | 'stick:<名称>'"""
        scene = self._scene

        def _to_screen(scene_pt):
            try:
                view_pt = self._window.mapFromScene(scene_pt)
                sp = self._window.mapToGlobal(view_pt)
                return int(sp.x()), int(sp.y())
            except Exception:
                return None

        if not key or key == 'screen':
            _ps = QApplication.primaryScreen()
            screen = _ps.geometry() if _ps else QRect(0, 0, 1920, 1080)
            return (screen.x() + screen.width() // 2,
                    screen.y() + screen.height() // 2)
        if key == 'center_ring':
            # 回中到中心轮盘几何中心 (任何环模式都成立; 跟随整盘拖动)
            c = scene.wheel_center_scene() if hasattr(scene, 'wheel_center_scene') else None
            return _to_screen(c) if c is not None else None
        if key == 'wheel':
            from scene.gp_wheel_item import GpWheelItem
            for it in scene.button_items:
                if isinstance(it, GpWheelItem) and _is_alive(it):
                    return _to_screen(it.sceneBoundingRect().center())
            return None
        if key.startswith('stick:'):
            name = key[len('stick:'):]
            from scene.gp_stick_item import GpStickItem
            for it in scene.button_items:
                if (isinstance(it, GpStickItem) and _is_alive(it)
                        and (it.data.name or '') == name):
                    return _to_screen(it.circle_center_scene())
            return None
        return None

    def _do_recenter(self, key: str):
        """把光标移到回中目标中心 (目标不存在则静默)。"""
        pos = self._resolve_recenter_pos(key)
        if pos is None:
            logger.warning("回中目标无法解析/不存在: '%s'", key)
            return
        try:
            user32.SetCursorPos(pos[0], pos[1])
        except Exception as e:
            logger.warning("回中 SetCursorPos 失败 '%s': %s", key, e)

    def _find_app(self, name: str):
        """解析 app:<name> → 启动路径 (先 profile apps 池, 再回退全局扫描缓存)。"""
        config = self._scene.get_config() if hasattr(self._scene, 'get_config') else {}
        return action_service.resolve_app_path(name, (config or {}).get('apps', []))

    def _launch_app(self, name: str):
        """启动本地应用 (os.startfile 解析 .lnk/.exe), 带 ~1.5s 冷却防重复。"""
        path = self._find_app(name)
        if not path:
            logger.warning("应用未找到/路径失效: '%s'", name)
            return
        now = _time.time()
        if now - self._app_cooldown.get(path, 0.0) < 1.5:
            return
        self._app_cooldown[path] = now
        action_service.launch_app(path)

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
        self._stick_wasd_held = set()
        stick.set_stick_visual('active', 0.0, 0.0)
        if getattr(stick.data, 'mode', 'analog') == 'wasd':
            return
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
            # WASD 模式: 松开所有按住的方向键, 防卡键
            if getattr(stick.data, 'mode', 'analog') == 'wasd':
                self._apply_wasd_dirs(stick, set())
            stick.set_stick_visual('idle', 0.0, 0.0)
            if getattr(stick.data, 'mode', 'analog') != 'wasd':
                gp = GamepadEngine.get()
                if gp is not None:
                    gp.set_stick(stick.data.stick_id, 0.0, 0.0)
        self._stick_wasd_held = set()
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
            # 只清按钮类 (lclick/rclick/mclick); 滚轮类 (wheelup/wheeldown) 由
            # _dispatch_wheel 的 QTimer 自己清, 否则刚 set 的滚轮闪烁立刻被本帧覆盖。
            cur = getattr(stick, '_pressed_action', None)
            if cur in ('lclick', 'rclick', 'mclick'):
                stick.set_pressed_action(None, '')

    def _update_stick_value(self, stick, scene_pos, sticking: bool):
        """根据 cursor 位置算 stick 值 (含死区/曲线/八向锁) + 更新视觉 + 引擎
        八方向锁定时, 视觉小球位置 AND 引擎值都吸附到 8 个固定方向。
        WASD 模式走独立分支 (按方向键, 不输出摇杆轴)。"""
        import math
        if getattr(stick.data, 'mode', 'analog') == 'wasd':
            self._update_stick_wasd(stick, scene_pos, sticking)
            return
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

    def _update_stick_wasd(self, stick, scene_pos, sticking: bool):
        """WASD 模式: 圆盘 8 扇区 → 方向键。死区内中性 (全松);
        死区外按角度吸附到 8 方向之一, 斜向同时按住相邻两键; sticking 时保持边缘方向。"""
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
        dz = max(0.0, min(0.5, stick.data.dead_zone))

        if mag < dz:
            # 死区内: 中性, 松开所有方向, 小球回中
            dirs: tuple = ()
            stick.set_stick_visual('active', 0.0, 0.0)
        else:
            idx = round(math.atan2(norm_y, norm_x) / (math.pi / 4)) % 8
            dirs = _WASD_SECTOR_DIRS[idx]
            is_stick = sticking or mag >= 1.0
            state = 'sticking' if is_stick else 'active'
            # 小球自由跟随鼠标; sticking 时钉在边缘 (单位向量沿实际角度)
            if is_stick:
                vis_x = norm_x / mag if mag > 0 else 0.0
                vis_y = norm_y / mag if mag > 0 else 0.0
            else:
                vis_x = norm_x
                vis_y = norm_y
            # 八方向锁定 (吸附): 小球吸到 8 方向; 关闭则自由移动 (键触发始终按扇区, 不受影响)
            if stick.data.eight_way:
                sang = idx * (math.pi / 4)
                vm = math.sqrt(vis_x * vis_x + vis_y * vis_y)
                vis_x = math.cos(sang) * vm
                vis_y = math.sin(sang) * vm
            sticking_progress = 0.0
            if state == 'sticking':
                ratio = stick.data.release_threshold_ratio
                if ratio > 1.0:
                    sticking_progress = max(0.0, min(1.0, (mag - 1.0) / (ratio - 1.0)))
            stick.set_stick_visual(state, vis_x, vis_y, sticking_progress=sticking_progress)

        self._apply_wasd_dirs(stick, set(dirs))

    def _apply_wasd_dirs(self, stick, dirs: set):
        """把目标方向集与已按住集做差: 新增的 press, 移除的 release。"""
        held = self._stick_wasd_held
        for d in held - dirs:
            key = getattr(stick.data, _WASD_DIR_FIELD[d], '')
            if key:
                self._smart_trigger(key, 'r')
        for d in dirs - held:
            key = getattr(stick.data, _WASD_DIR_FIELD[d], '')
            if key:
                self._smart_trigger(key, 'p')
        self._stick_wasd_held = set(dirs)

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

        # ── 轻松操控模式分支: 全屏鼠标接管, 不走 in_rect / release zone 逻辑 ──
        if (wheel is not None
                and getattr(wheel.data, 'control_mode', 'advanced') == 'easy'):
            self._poll_gp_wheel_easy(wheel, screen_pt)
            gp = GamepadEngine.get()
            if gp is not None:
                gp.flush()
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

    # ── 轻松操控模式 (mouse-as-car) ──

    def _poll_gp_wheel_easy(self, wheel, screen_pt: QPoint):
        """全屏鼠标接管:
        - X: 增量式 — 鼠标左移(dx<0) → 按 A, 右移(dx>0) → 按 D; 不动则不发。
             防抖靠 EMA 平滑 + _SMOOTH_TH 阈值, 无定点死区 (固定位置时 dx≈0 自然不触发)
        - Y: 上移 → RT 累加 (速度映射); 下移 → RT 减少; 累计值持续输出
        - 鼠标左键: 按下 → 按 S, 松开 → 释放 S
        - A/D 带触发/释放延迟 (fill 状态机); 视觉: 旋转(dir×fill) + 径向填充(fill)
        """
        d = wheel.data
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        sg = screen.geometry()
        sw, sh = sg.width(), sg.height()
        if sw <= 0 or sh <= 0:
            return
        mx = screen_pt.x() - sg.left()
        my = screen_pt.y() - sg.top()

        # ── 1) 横向位移 → A/D, 触发/释放延迟状态机 (fill 0~1, 类按钮) ──
        # EMA 平滑近几帧 dx 过滤手抖; 本帧输入方向驱动 fill 涨/退:
        #   fill 涨满(过触发延迟)→按下 A/D; fill 退到 0(过释放延迟)→松开;
        #   反向立即取消当前键并清 fill; 释放中再触发同向则回填。
        import time as _t1
        _EMA_ALPHA = 0.5
        _SMOOTH_TH = float(getattr(d, 'easy_steer_threshold', 1.0))
        now_t = _t1.perf_counter()
        if self._easy_last_mx is None:
            self._easy_last_mx = mx
            self._easy_smooth_dx = 0.0
        dx_px = mx - self._easy_last_mx
        self._easy_last_mx = mx
        self._easy_smooth_dx = (
            _EMA_ALPHA * self._easy_smooth_dx + (1.0 - _EMA_ALPHA) * dx_px)
        if self._easy_smooth_dx <= -_SMOOTH_TH:
            input_dir = -1
        elif self._easy_smooth_dx >= _SMOOTH_TH:
            input_dir = 1
        else:
            input_dir = 0
        # dt (转向状态机专用)
        if self._easy_steer_tick is None:
            sdt = 0.0
        else:
            sdt = min(0.1, now_t - self._easy_steer_tick)
        self._easy_steer_tick = now_t
        tt = max(0.0, float(getattr(d, 'easy_trigger_delay', 0)) / 1000.0)
        rr = max(0.0, float(getattr(d, 'easy_release_delay', 500)) / 1000.0)

        def _rel(k):
            if k == -1:
                trigger('a', 'r')
            elif k == 1:
                trigger('d', 'r')

        if input_dir != 0:
            if self._easy_dir != 0 and input_dir != self._easy_dir:
                # 反向: 立即取消当前键 + 清 fill (不走释放延迟)
                _rel(self._easy_key_down)
                self._easy_key_down = 0
                self._easy_fill = 0.0
            self._easy_dir = input_dir
            self._easy_fill = 1.0 if tt <= 0 else min(1.0, self._easy_fill + sdt / tt)
        elif self._easy_dir != 0:
            self._easy_fill = 0.0 if rr <= 0 else max(0.0, self._easy_fill - sdt / rr)
            if self._easy_fill <= 0.0:
                self._easy_dir = 0
        # 键实际按下/松开
        if self._easy_fill >= 1.0 and self._easy_dir != 0 and self._easy_key_down != self._easy_dir:
            _rel(self._easy_key_down)
            trigger('a' if self._easy_dir == -1 else 'd', 'p')
            self._easy_key_down = self._easy_dir
        elif self._easy_fill <= 0.0 and self._easy_key_down != 0:
            _rel(self._easy_key_down)
            self._easy_key_down = 0

        # ── 2) 纵向速度 → RT 累加 ──
        sens = float(getattr(d, 'easy_throttle_sensitivity', 0.005))
        if self._easy_last_y is None:
            self._easy_last_y = my
        dy = my - self._easy_last_y      # 屏幕坐标: 向上是负
        self._easy_last_y = my
        # 上移 (dy<0) → RT 增加
        self._easy_rt = max(0.0, min(1.0, self._easy_rt - dy * sens))
        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_trigger("R", self._easy_rt)

        # ── 3) 配置的鼠标键 → S (默认左键, 可在编辑器改成右/中/侧1/侧2) ──
        _BRAKE_VK = {
            'L': VK_LBUTTON, 'R': VK_RBUTTON, 'M': VK_MBUTTON,
            'X1': VK_XBUTTON1, 'X2': VK_XBUTTON2,
        }
        brake_vk = _BRAKE_VK.get(getattr(d, 'easy_brake_button', 'L'), VK_LBUTTON)
        brake_down = bool(user32.GetAsyncKeyState(brake_vk) & 0x8000)
        if brake_down != self._easy_brake_state:
            trigger('s', 'p' if brake_down else 'r')
            self._easy_brake_state = brake_down

        # ── 4) 视觉旋转: 恒定角速模型滑向 key_down 目标 (与 fill 解耦) ──
        # fill 只驱动圆心填充动画 (触发/释放缓冲); 旋转跟「实际按键态」走:
        #   触发 → fill 填满 → key_down 置位 → 方向盘按 ±360°/s 滑向 ±max;
        #   保持触发 (含释放延迟内 key_down 仍在) → 稳在满舵不抖;
        #   fill 归 0 松键 → key_down=0 → 方向盘按 720°/s 滑回中。
        _LOCK_DEG_PER_SEC = 360.0
        _RETURN_DEG_PER_SEC = 720.0
        max_deg = float(getattr(d, 'max_rotation_deg', 180.0)) or 180.0
        lock_norm = _LOCK_DEG_PER_SEC / max_deg
        return_norm = _RETURN_DEG_PER_SEC / max_deg
        target = float(self._easy_key_down)
        cur = self._easy_visual_steer
        speed = lock_norm if target != 0.0 else return_norm
        delta = speed * sdt
        if cur < target:
            cur = min(target, cur + delta)
        elif cur > target:
            cur = max(target, cur - delta)
        self._easy_visual_steer = cur
        if hasattr(wheel, 'set_visual'):
            wheel.set_visual(
                cur,
                1.0 if self._easy_brake_state else 0.0,
                self._easy_rt,
                active=True,
            )
        # fill 圆心填充动画暂时隐藏 (保留状态机逻辑, 仅不推送视觉)
        # if hasattr(wheel, 'set_easy_fill'):
        #     wheel.set_easy_fill(self._easy_fill)

    def _release_easy_state(self):
        """退出 easy 模式或停止运行时调用: 释放 A/D/S, RT 归零, 视觉状态重置"""
        if self._easy_key_down == -1:
            trigger('a', 'r')
        elif self._easy_key_down == 1:
            trigger('d', 'r')
        if self._easy_brake_state:
            trigger('s', 'r')
        self._easy_dir = 0
        self._easy_fill = 0.0
        self._easy_key_down = 0
        self._easy_steer_tick = None
        self._easy_brake_state = False
        self._easy_rt = 0.0
        self._easy_last_y = None
        self._easy_last_mx = None
        self._easy_smooth_dx = 0.0
        self._easy_visual_steer = 0.0
        gp = GamepadEngine.get()
        if gp is not None:
            gp.set_trigger("R", 0.0)

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

        # 鼠标动作叠加: 持有中的任意鼠标键 (含滚轮 pulse) 若映射了 gp:LT / gp:RT,
        # 当前 override 应为 1.0; 跟 wheel 自己的 LT/RT 取 max → 互不影响进度条
        # (wheel 进度条只显示 _wheel_lt/_rt)。
        # 遍历 .values() 而非硬编码字段名 — 让 wheelup/wheeldown 滚轮 pulse 也自动生效。
        override_lt = 0.0
        override_rt = 0.0
        for key in self._wheel_mouse_holding.values():
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
            # 配 gp:LT/RT 时, _smart_trigger 的 50ms 延迟 release 在 _poll_gp_wheel
            # 每帧 set_trigger 覆盖下根本撑不过 1 帧 (~16ms 就被刷成 0)。
            # 把滚轮也加入 _wheel_mouse_holding ~120ms, 让 _update_wheel_triggers 的
            # override_lt/rt 机制持续生效, 游戏端 60Hz polling 至少能采到 6+ 帧 = 100ms
            # 的扳机按下信号。120ms = 看得到但不至于卡很久。
            self._wheel_mouse_holding[field] = key_str
            QTimer.singleShot(120, lambda f=field: self._wheel_mouse_holding.pop(f, None))
            # hub 视觉闪一下 ~200ms (scroll 是瞬时事件没有 hold)
            if hasattr(wheel, 'set_pressed_action'):
                from scene.gp_stick_item import _gp_display
                wheel.set_pressed_action(field, _gp_display(key_str))
                QTimer.singleShot(200, lambda w=wheel:
                                  w.set_pressed_action(None, '') if _is_alive(w) else None)
            return True
        return False

    def _find_macro(self, name: str, pool: str = 'kb'):
        """从当前 config 中查找宏。pool='x' 查 xmacros (统一池), 'gp' 查 gp_macros, 其余查 macros"""
        config = self._scene.get_config() if hasattr(self._scene, 'get_config') else {}
        return action_service.find_macro(config, name, pool)

    def _macro_trigger(self, keys: str, act: str):
        """宏步骤的执行后端 — click 走 p+r (组合键按住语义), 与历史行为一致。"""
        if act == 'click':
            self._smart_trigger(keys, 'p')
            self._smart_trigger(keys, 'r')
        elif act == 'press':
            self._smart_trigger(keys, 'p')
        elif act == 'release':
            self._smart_trigger(keys, 'r')

    def _execute_macro(self, macro_data: dict):
        """在后台线程中顺序执行宏步骤 (避免 delay 阻塞主循环)。

        步骤格式与执行逻辑见 core.action_service.run_macro; 这里只负责
        起线程 + 注入执行后端(_macro_trigger) 与中断条件(self._active)。
        """
        if not macro_data.get('steps'):
            return
        name = macro_data.get('name', '?')

        def _run():
            n = action_service.run_macro(
                macro_data, self._macro_trigger, is_active=lambda: self._active)
            logger.info("Macro '%s' executed (%d steps)", name, n)

        threading.Thread(target=_run, daemon=True).start()

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
        chunk_size = voice_config.get('voice_chunk_size', None)
        if not commands:
            return
        # grammar 里常驻"确认/取消"词 (仅在 agent 待确认时才起作用; 平时被忽略),
        # 避免临时切 grammar 重载 Vosk 模型。已有同名短语的不重复加。
        try:
            from agent import safety
            have = {c.get('phrase') for c in commands}
            commands = list(commands) + [c for c in safety.confirm_voice_commands()
                                         if c['phrase'] not in have]
        except Exception:
            pass

        try:
            from engine.voice_engine import VoiceEngine
            self._voice_engine = VoiceEngine(self)
            self._voice_engine.command_recognized.connect(self._on_voice_command)
            self._voice_engine.error_occurred.connect(
                lambda e: logger.warning(f"语音引擎错误: {e}"))
            self._voice_engine.start(commands, language, mic_device=mic_device, chunk_size=chunk_size)
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
        # agent 待确认时: 语音接管为"只认确认/取消", 其它指令一律忽略; 处理完自动恢复
        from agent import safety
        is_yes = keys == safety.CONFIRM_YES_KEY
        is_no = keys == safety.CONFIRM_NO_KEY
        if safety.confirm_pending():
            if is_yes:
                safety.resolve_pending(True)
                logger.info("语音确认: 确认 ('%s')", phrase)
            elif is_no:
                safety.resolve_pending(False)
                logger.info("语音确认: 取消 ('%s')", phrase)
            # 其它指令在确认期间忽略
            return
        if is_yes or is_no:
            return   # 无待确认时, 确认/取消词不做任何事
        if action == 'click':
            # 统一 click 语义: 键盘=按下+短延迟+释放, 手柄=press+flush+延迟release,
            # 鼠标键=按下+延迟释放。直接 p 紧跟 r 会因无间隔被游戏/驱动丢弃。
            self._smart_trigger(keys, 'click')
        elif action == 'press':
            self._smart_trigger(keys, 'p')
        elif action == 'release':
            self._smart_trigger(keys, 'r')
        self.voice_command_triggered.emit(phrase, keys, action)
        # 把前景窗口一起打到日志: 失焦时 SendInput 会把按键送到错的窗口,
        # 此时 exe 名不是预期的游戏 → 一眼能看出来
        from core.focus_debug import format_foreground
        logger.info("语音指令触发: '%s' → keys='%s', action='%s' | %s",
                    phrase, keys, action, format_foreground())
