"""
TEGG Touch 蛋挞 — 手柄引擎: VX360Gamepad 封装 + 帧聚合

设计:
- 调用方写入按钮 / 摇杆 / 扳机, 内部仅标记 dirty
- 帧末统一 flush() 调一次 _pad.update(), 避免 USB 包风暴
- VX360Gamepad() 实例化在 ViGEmBus 未加载时会抛异常 → get() 捕获返回 None
- 进程单例: 整个 app 只创建 1 个虚拟手柄设备
- LT/RT 在 gp_button 编辑器里可作为「按钮」使用 (press = 1.0, release = 0.0),
  路由到 set_trigger api, 因为 XUSB_BUTTON 枚举中 LT/RT 不是 button 而是 trigger
"""

import logging
import threading

logger = logging.getLogger(__name__)

try:
    import vgamepad as vg
    _VG_AVAILABLE = True
except ImportError:
    vg = None
    _VG_AVAILABLE = False


def _build_button_map() -> dict:
    """标签 → XUSB_BUTTON 枚举 (LT/RT 走 trigger, 不在此 map)"""
    if not _VG_AVAILABLE:
        return {}
    e = vg.XUSB_BUTTON
    return {
        "A": e.XUSB_GAMEPAD_A,
        "B": e.XUSB_GAMEPAD_B,
        "X": e.XUSB_GAMEPAD_X,
        "Y": e.XUSB_GAMEPAD_Y,
        "LB": e.XUSB_GAMEPAD_LEFT_SHOULDER,
        "RB": e.XUSB_GAMEPAD_RIGHT_SHOULDER,
        "Start": e.XUSB_GAMEPAD_START,
        "Back": e.XUSB_GAMEPAD_BACK,
        "Guide": e.XUSB_GAMEPAD_GUIDE,
        "D-Up": e.XUSB_GAMEPAD_DPAD_UP,
        "D-Down": e.XUSB_GAMEPAD_DPAD_DOWN,
        "D-Left": e.XUSB_GAMEPAD_DPAD_LEFT,
        "D-Right": e.XUSB_GAMEPAD_DPAD_RIGHT,
        "L3": e.XUSB_GAMEPAD_LEFT_THUMB,
        "R3": e.XUSB_GAMEPAD_RIGHT_THUMB,
    }


class GamepadEngine:
    """虚拟 Xbox 360 手柄 — 单例 + 帧聚合"""

    _instance = None
    _lock = threading.Lock()
    _init_failed = False   # 初始化失败后不再重试 (避免每帧都触发驱动异常)

    @classmethod
    def get(cls) -> 'GamepadEngine | None':
        """获取单例; 若 vgamepad 缺失或 ViGEmBus 未加载返回 None"""
        if not _VG_AVAILABLE or cls._init_failed:
            return None
        with cls._lock:
            if cls._instance is None:
                try:
                    cls._instance = cls()
                except Exception as e:
                    logger.error(f"GamepadEngine 初始化失败 (ViGEmBus 未加载?): {e}")
                    cls._init_failed = True
                    return None
            return cls._instance

    def __init__(self):
        self._pad = vg.VX360Gamepad()
        self._button_map = _build_button_map()
        self._pressed_buttons: set[str] = set()
        self._lstick = (0.0, 0.0)
        self._rstick = (0.0, 0.0)
        self._ltrigger = 0.0
        self._rtrigger = 0.0
        self._dirty = False
        logger.info("GamepadEngine 已就绪: 虚拟 Xbox 360 手柄已创建")

    # ── 按钮 ──
    def press_button(self, label: str):
        if label == "LT":
            self.set_trigger("L", 1.0); return
        if label == "RT":
            self.set_trigger("R", 1.0); return
        enum = self._button_map.get(label)
        if enum is None:
            logger.warning(f"未知手柄按钮标签: {label}")
            return
        if label not in self._pressed_buttons:
            self._pressed_buttons.add(label)
            self._pad.press_button(enum)
            self._dirty = True

    def release_button(self, label: str):
        if label == "LT":
            self.set_trigger("L", 0.0); return
        if label == "RT":
            self.set_trigger("R", 0.0); return
        enum = self._button_map.get(label)
        if enum is None:
            return
        if label in self._pressed_buttons:
            self._pressed_buttons.discard(label)
            self._pad.release_button(enum)
            self._dirty = True

    # ── 摇杆 (x, y ∈ [-1, 1]) ──
    def set_stick(self, stick_id: str, x: float, y: float):
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        if stick_id == "L":
            if (x, y) != self._lstick:
                self._lstick = (x, y)
                self._pad.left_joystick_float(x, y)
                self._dirty = True
        else:
            if (x, y) != self._rstick:
                self._rstick = (x, y)
                self._pad.right_joystick_float(x, y)
                self._dirty = True

    # ── 扳机 (value ∈ [0, 1]) ──
    def set_trigger(self, trigger_id: str, value: float):
        value = max(0.0, min(1.0, value))
        if trigger_id == "L":
            if value != self._ltrigger:
                self._ltrigger = value
                self._pad.left_trigger_float(value)
                self._dirty = True
        else:
            if value != self._rtrigger:
                self._rtrigger = value
                self._pad.right_trigger_float(value)
                self._dirty = True

    # ── 帧末统一提交 ──
    def flush(self):
        if self._dirty:
            try:
                self._pad.update()
            except Exception as e:
                logger.error(f"vgamepad update 失败: {e}")
            self._dirty = False

    # ── 退出 run 模式时归零 ──
    def release_all(self):
        for label in list(self._pressed_buttons):
            enum = self._button_map.get(label)
            if enum:
                self._pad.release_button(enum)
        self._pressed_buttons.clear()
        self._pad.left_joystick_float(0.0, 0.0)
        self._pad.right_joystick_float(0.0, 0.0)
        self._pad.left_trigger_float(0.0)
        self._pad.right_trigger_float(0.0)
        self._lstick = self._rstick = (0.0, 0.0)
        self._ltrigger = self._rtrigger = 0.0
        try:
            self._pad.update()
        except Exception:
            pass
        self._dirty = False


def is_lib_available() -> bool:
    """vgamepad lib 是否已 import (不代表 ViGEmBus 驱动 OK)"""
    return _VG_AVAILABLE
