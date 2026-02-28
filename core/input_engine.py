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

# 追踪当前已按下的键 — 用于退出时兜底释放，防止卡键
# 元素: (scan_code, extended: bool)
_pressed_keys: set = set()

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

# ─── 扩展键扫描码集合 ────────────────────────────────────────
# 这些按键与小键盘共享扫描码，必须加 KEYEVENTF_EXTENDEDKEY 标志才能正确识别
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002

# 按键名 → 是否为扩展键（与小键盘共享扫描码，需要 EXTENDEDKEY 标志区分）
_EXTENDED_KEY_NAMES = {
    "up", "down", "left", "right",           # 方向键 (vs Numpad 8/2/4/6)
    "insert", "delete", "home", "end",        # 编辑键 (vs Numpad 0/./7/1)
    "page up", "page down", "pgup", "pgdn",   # 翻页键 (vs Numpad 9/3)
    "right ctrl", "right alt",                 # 右侧修饰键
    "left windows", "right windows",           # Win 键
}

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


def press_key(scan_code: int, extended: bool = False):
    """按下按键（硬件扫描码）。extended=True 为方向键等扩展键。"""
    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    _SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    _pressed_keys.add((scan_code, extended))


def release_key(scan_code: int, extended: bool = False):
    """释放按键（硬件扫描码）。extended=True 为方向键等扩展键。"""
    flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    _SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    _pressed_keys.discard((scan_code, extended))


def release_all_keys():
    """释放所有当前被按下的键 — 退出/停止时兜底调用，防止卡键。"""
    if not _pressed_keys:
        return
    keys_copy = list(_pressed_keys)
    for sc, ext in keys_copy:
        try:
            release_key(sc, ext)
        except Exception as e:
            logger.error(f"释放按键失败: scan={sc}, ext={ext}, error={e}")
    _pressed_keys.clear()
    logger.info(f"兜底释放了 {len(keys_copy)} 个按键")


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
            ext = k.lower() in _EXTENDED_KEY_NAMES
            if action == 'p':
                press_key(sc, ext)
            elif action == 'r':
                release_key(sc, ext)
            elif action == 'c':
                press_key(sc, ext)
                time.sleep(random.uniform(0.03, 0.06))
                release_key(sc, ext)
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


