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

from PyQt6.QtCore import QObject, QTimer, QPoint, pyqtSignal

from core.input_engine import trigger, is_key_pressed, poll_wheel_events, release_all_keys
from core.config_manager import load_hotkeys
from core.constants import UPDATE_INTERVAL, BTN_TYPE_CENTER_BAND

user32 = ctypes.windll.user32
logger = logging.getLogger(__name__)

# VK 常量
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04


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

    def __init__(self, scene, window):
        super().__init__()
        self._scene = scene
        self._window = window
        self._active = False

        # 硬件按键状态缓存 (用于侧键检测)
        self._prev_xb1 = False
        self._prev_xb2 = False

        # Bug 4 fix: 使用计数器替代布尔值，正确追踪多个同时激活的按键
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

        # 快捷键定时器
        self._timer = QTimer(self)
        self._timer.setInterval(UPDATE_INTERVAL)
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

        # 4. 轮询式 hover/click 检测 (核心! 解决 WS_EX_TRANSPARENT 问题)
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

        # ── 回中带每帧检测 (匹配原版: 每帧 in_rect → SetCursorPos + continue) ──
        if (active_item is not None
                and getattr(active_item.data, 'btn_type', '') == BTN_TYPE_CENTER_BAND):
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
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
                    # RELEASING 时也设 normal — 蓝色充能条在深色背景上递减可见
                    # （原版: 光标离开后 target_state='normal', charge_bar 画在深色背景上）
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
            self.on_action_triggered(h_item.data, h_key, 'r')
            if hasattr(h_item, '_hover_sm') and h_item._hover_sm.is_active:
                h_item.set_visual_state('hover')
            else:
                h_item.set_visual_state('normal')
            self._holding_lclick = None
        if not rmb and self._prev_rmb and self._holding_rclick:
            h_item, h_key = self._holding_rclick
            self.on_action_triggered(h_item.data, h_key, 'r')
            if hasattr(h_item, 'set_visual_state'):
                h_item.set_visual_state('hover' if (hasattr(h_item, '_hover_sm') and h_item._hover_sm.is_active) else 'normal')
            self._holding_rclick = None
        if not mmb and self._prev_mmb and self._holding_mclick:
            h_item, h_key = self._holding_mclick
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
        import time
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
                now = time.time()
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
        import time
        now = time.time()

        def _debounced(name, key_name):
            if is_key_pressed(key_name):
                last = self._debounce.get(name, 0)
                if now - last > 0.3:
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

        # 穿透模式快捷键
        if _debounced('pt_on', hk.get('pt_on', 'f9')):
            self.passthrough_changed.emit('pt_on')
        elif _debounced('pt_off', hk.get('pt_off', 'f10')):
            self.passthrough_changed.emit('pt_off')
        elif _debounced('pt_block', hk.get('pt_block', 'f11')):
            self.passthrough_changed.emit('pt_block')

    def _dispatch_wheel(self, direction, abs_x, abs_y):
        """将滚轮事件分发到场景坐标处的 Item"""
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
        """将侧键事件分发到鼠标下的 Item"""
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
                    from engine.hover_state_machine import HoverState
                    if hasattr(item, '_hover_sm') and item._hover_sm.is_active:
                        item.set_visual_state('hover')
                    else:
                        item.set_visual_state('normal')

    def _do_auto_center(self):
        """执行自动回中 — 使用实际屏幕尺寸（与原版一致）"""
        if not self._active or not self._auto_center:
            return
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        cx = screen.x() + screen.width() // 2
        cy = screen.y() + screen.height() // 2
        user32.SetCursorPos(cx, cy)

    # ── 接收 Item 信号的槽 ──

    def on_hover_activated(self, data):
        """按钮 hover 激活 → 按下按键"""
        self._active_key_count += 1
        self._ac_start_time = None
        if data.hover:
            self._smart_trigger(data.hover, 'p')

    def on_hover_deactivated(self, data):
        """按钮 hover 释放 → 释放按键"""
        self._active_key_count = max(0, self._active_key_count - 1)
        if data.hover:
            self._smart_trigger(data.hover, 'r')

    def on_action_triggered(self, data, key_str, action):
        """按钮点击/滚轮 → 触发按键"""
        if action == 'p':
            self._active_key_count += 1
            self._ac_start_time = None
        elif action == 'r':
            self._active_key_count = max(0, self._active_key_count - 1)
        self._smart_trigger(key_str, action)

    # ── 宏感知的智能触发 ──

    def _smart_trigger(self, key_str: str, action: str):
        """解析 key_str, 分离普通键和 macro:name 标签, 分别执行"""
        if not key_str:
            return
        parts = [p.strip() for p in key_str.split('+')]
        normal_keys = []
        macro_names = []
        for p in parts:
            if p.startswith('macro:'):
                macro_names.append(p[6:])
            else:
                normal_keys.append(p)

        # 普通键照常触发
        if normal_keys:
            trigger('+'.join(normal_keys), action)

        # 宏: 仅在 press / click 时触发 (release 忽略, 避免重复)
        if macro_names and action in ('p', 'click'):
            for name in macro_names:
                macro_data = self._find_macro(name)
                if macro_data:
                    self._execute_macro(macro_data)
                else:
                    logger.warning("Macro not found: '%s'", name)

    def _find_macro(self, name: str):
        """从当前 config 中查找宏"""
        config = getattr(self._scene, '_config', None) or {}
        for m in config.get('macros', []):
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
                        keys = step.get('key', '') or step.get('keys', '')
                        act = step.get('action', 'click')
                        if keys:
                            if act == 'click':
                                trigger(keys, 'p')
                                trigger(keys, 'r')
                            elif act == 'press':
                                trigger(keys, 'p')
                            elif act == 'release':
                                trigger(keys, 'r')
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
                                trigger(keys, 'p')
                                trigger(keys, 'r')
                            elif act == 'press':
                                trigger(keys, 'p')
                            elif act == 'release':
                                trigger(keys, 'r')
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
        if not commands:
            return

        try:
            from engine.voice_engine import VoiceEngine
            self._voice_engine = VoiceEngine(self)
            self._voice_engine.command_recognized.connect(self._on_voice_command)
            self._voice_engine.error_occurred.connect(
                lambda e: logger.warning(f"语音引擎错误: {e}"))
            self._voice_engine.start(commands, language)
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
