"""
TEGG Touch 蛋挞 辅助软件 - 键盘输入模拟引擎

使用 Windows SendInput API 发送硬件级扫描码按键事件。
与 UI 完全解耦，可独立测试。
"""

import ctypes
import ctypes.wintypes as wintypes
import time
import random
import logging
import threading
from collections import deque

logger = logging.getLogger(__name__)

# ─── 全局滚轮事件队列 ───────────────────────────────────────

_wheel_queue: deque = deque(maxlen=64)
_hook_handle = None
_hook_func_ref = None  # prevent GC

# ─── ctypes 结构体定义 ───────────────────────────────────────

PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I),
    ]


_SendInput = ctypes.windll.user32.SendInput

# ─── keyboard 库加载 ─────────────────────────────────────────

try:
    import keyboard as _kb
    _keyboard_available = True
except ImportError:
    _kb = None
    _keyboard_available = False
    logger.warning("keyboard 库未安装，按键模拟将不可用")


# ─── 公共 API ────────────────────────────────────────────────

def get_scan_code(key_name: str) -> int:
    """将按键名转换为扫描码。"""
    if not _keyboard_available:
        return 0
    try:
        return _kb.key_to_scan_codes(key_name)[0]
    except Exception:
        logger.debug(f"无法获取按键 '{key_name}' 的扫描码")
        return 0


def press_key(scan_code: int):
    """按下按键（硬件扫描码）。"""
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, 0x0008, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    _SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def release_key(scan_code: int):
    """释放按键（硬件扫描码）。"""
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, 0x0008 | 0x0002, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    _SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def trigger(keys: str, action: str):
    """触发按键操作。

    Args:
        keys:   按键字符串，多键用 '+' 连接，如 "w+a"
        action: 'p' = 按下, 'r' = 释放, 'c' = 点击(按下+短暂延迟+释放)
    """
    if not keys:
        return
    key_list = [k.strip() for k in keys.split('+') if k.strip()]
    if not key_list:
        return
    try:
        for k in key_list:
            sc = get_scan_code(k)
            if sc == 0:
                continue
            if action == 'p':
                press_key(sc)
            elif action == 'r':
                release_key(sc)
            elif action == 'c':
                press_key(sc)
                time.sleep(random.uniform(0.03, 0.06))
                release_key(sc)
    except Exception as e:
        logger.error(f"触发按键失败: keys={keys}, action={action}, error={e}")


def is_key_pressed(key_name: str) -> bool:
    """检查某个键是否被按下（通过 keyboard 库）。"""
    if not _keyboard_available:
        return False
    try:
        return _kb.is_pressed(key_name)
    except Exception:
        return False


# ─── 低级鼠标钩子：全局滚轮捕获 ─────────────────────────────

WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A

class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('pt', wintypes.POINT),
        ('mouseData', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]

_HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(_MSLLHOOKSTRUCT))


# mouse_event 比 SendInput 快得多（无需创建 ctypes 结构体）
_mouse_event = ctypes.windll.user32.mouse_event
MOUSEEVENTF_MOVE = 0x0001


def _mouse_hook_proc(nCode, wParam, lParam):
    """低级鼠标钩子回调。处理全局滚轮捕获。"""
    if nCode >= 0:
        data = lParam.contents

        if wParam == WM_MOUSEWHEEL:
            # mouseData 高16位是滚轮 delta (signed short)
            delta = ctypes.c_short(data.mouseData >> 16).value
            direction = 'up' if delta > 0 else 'down'
            _wheel_queue.append((direction, data.pt.x, data.pt.y))

    return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)


def install_wheel_hook():
    """安装全局鼠标滚轮钩子。在主线程调用。"""
    global _hook_handle, _hook_func_ref
    if _hook_handle is not None:
        return  # 已安装
    _hook_func_ref = _HOOKPROC(_mouse_hook_proc)
    _hook_handle = ctypes.windll.user32.SetWindowsHookExW(
        WH_MOUSE_LL, _hook_func_ref, None, 0
    )
    if _hook_handle == 0:
        logger.error("安装鼠标钩子失败")
        _hook_handle = None


def uninstall_wheel_hook():
    """卸载全局鼠标滚轮钩子。"""
    global _hook_handle, _hook_func_ref
    if _hook_handle:
        ctypes.windll.user32.UnhookWindowsHookEx(_hook_handle)
        _hook_handle = None
        _hook_func_ref = None


def poll_wheel_events():
    """取出所有待处理的滚轮事件。返回 list of (direction, abs_x, abs_y)。"""
    events = []
    while _wheel_queue:
        events.append(_wheel_queue.popleft())
    return events


