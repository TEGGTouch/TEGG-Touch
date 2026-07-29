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
_wheel_lock = threading.Lock()  # 保护 _wheel_queue 的跨线程访问（钩子线程 vs 主线程）
_hook_handle = None
_hook_func_ref = None  # prevent GC

# 追踪当前已按下的键 — 用于退出时兜底释放，防止卡键
# 元素: (scan_code, extended: bool)
_pressed_keys: set = set()
_pressed_keys_lock = threading.Lock()

# ─── ctypes 结构体定义 ───────────────────────────────────────

PUL = ctypes.POINTER(ctypes.c_ulong)

# ─── 自注入标记 ────────────────────────────────────────────
# 本模块发出的所有键盘/鼠标事件都在 dwExtraInfo 填这个魔数。
# 键盘映射钩子 (core/keyboard_hook.py) 见到它就直接放行, 否则
# 「A→D 同时 D→A」这类互换映射会被自己的注入再次命中 → 无限回环。
# 改动任何 SendInput / mouse_event 调用时务必带上它。
INJECT_MAGIC = 0x7E66  # "TEGG"


class KeyBdInput(ctypes.Structure):
    # dwExtraInfo 是 Win32 ULONG_PTR (指针大小的「整数」, 不是指针) —— 同
    # passthrough_manager 对 mouse_event 的声明。旧版这里写 POINTER(c_ulong)
    # 并传指针, 钩子侧读到的是那个 c_ulong 的「地址」而非魔数本身, 对不上。
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
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
_SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(Input), ctypes.c_int]
_SendInput.restype = ctypes.c_uint

# ─── 扩展键扫描码集合 ────────────────────────────────────────
# 这些按键与小键盘共享扫描码，必须加 KEYEVENTF_EXTENDEDKEY 标志才能正确识别
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002

# 按键名 → 是否为扩展键（与小键盘共享扫描码，需要 EXTENDEDKEY 标志区分）
# 注: 仅用于 keyboard 库返回「低字节扫描码」的键 (如 up=72); 对返回 e0 编码
# (如 windows=0xE05B) 的键, _resolve_scan 会自动识别, 无需列在此。
_EXTENDED_KEY_NAMES = {
    "up", "down", "left", "right",           # 方向键 (vs Numpad 8/2/4/6)
    "insert", "delete", "home", "end",        # 编辑键 (vs Numpad 0/./7/1)
    "page up", "page down", "pgup", "pgdn",   # 翻页键 (vs Numpad 9/3)
    "pageup", "pagedown",                      # 面板用的无空格写法 (键位面板)
    "num enter",                               # 小键盘回车 (0xE01C, 但 keyboard 返回低字节 28)
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


# keyboard 库对个别特殊键返回的 [0] 扫描码不对, 这里硬覆盖为正确的 (scan, extended)
_SCAN_OVERRIDE = {
    "scroll lock": (0x46, False),   # 库返回 0xE046(=Break), 真值 0x46 非扩展
    "print screen": (0x37, True),   # 库返回 0x54(=SysRq), 真值 0xE037
    # pause/break 是多扫描码序列 (0xE11D45), 单次 SendInput scancode 无法正确表达, 不支持
}


def _resolve_scan(key_name: str):
    """按键名 → (扫描码低字节, 是否扩展键)。

    keyboard 库返回的扫描码不一致:
      - 部分键返回「低字节」(如 up=72), 扩展与否查 _EXTENDED_KEY_NAMES;
      - 部分键返回「e0 编码」(如 windows=0xE05B / 媒体键=0xE0xx), 直接据此识别;
      - 个别特殊键 (scroll lock / print screen) 库返回值不对, 用 _SCAN_OVERRIDE 硬覆盖。
    两种都归一到 (低字节, extended), 再由 press_key 加 EXTENDEDKEY 标志, 保证
    Win/菜单/媒体/小键盘除号回车 等扩展键正确发送。
    """
    if not _keyboard_available:
        return 0, False
    ov = _SCAN_OVERRIDE.get(key_name.lower())
    if ov is not None:
        return ov
    try:
        raw = _kb.key_to_scan_codes(key_name)[0]
    except Exception:
        logger.debug(f"无法获取按键 '{key_name}' 的扫描码")
        return 0, False
    if raw >= 0xE000:                    # e0 前缀的扩展键
        return raw & 0xFF, True
    return raw, key_name.lower() in _EXTENDED_KEY_NAMES


def press_key(scan_code: int, extended: bool = False):
    """按下按键（硬件扫描码）。extended=True 为方向键等扩展键。

    先执行 SendInput（可能耗时），再在锁内更新集合，避免锁内阻塞。
    """
    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, INJECT_MAGIC)
    x = Input(ctypes.c_ulong(1), ii_)
    _SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    with _pressed_keys_lock:
        _pressed_keys.add((scan_code, extended))


def release_key(scan_code: int, extended: bool = False):
    """释放按键（硬件扫描码）。extended=True 为方向键等扩展键。

    先执行 SendInput（可能耗时），再在锁内更新集合，避免锁内阻塞。
    """
    flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, INJECT_MAGIC)
    x = Input(ctypes.c_ulong(1), ii_)
    _SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    with _pressed_keys_lock:
        _pressed_keys.discard((scan_code, extended))


def release_all_keys():
    """释放所有当前被按下的键 — 退出/停止时兜底调用，防止卡键。"""
    with _pressed_keys_lock:
        if not _pressed_keys:
            return
        keys_copy = list(_pressed_keys)
        _pressed_keys.clear()
    # 在锁外执行 Win32 API 调用，避免锁内阻塞
    for sc, ext in keys_copy:
        try:
            flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
            if ext:
                flags |= KEYEVENTF_EXTENDEDKEY
            ii_ = Input_I()
            ii_.ki = KeyBdInput(0, sc, flags, 0, INJECT_MAGIC)
            x = Input(ctypes.c_ulong(1), ii_)
            _SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        except Exception as e:
            logger.error(f"释放按键失败: scan={sc}, ext={ext}, error={e}")
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
        if action == 'c':
            # 组合键 click: 必须「全部按下 → 延迟 → 逆序全部释放」, 否则像
            # ctrl+f4 会被逐键拆成 ctrl 单击 + f4 单击, 修饰键提前松开, 组合键不成立。
            scans = []
            for k in key_list:
                sc, ext = _resolve_scan(k)
                if sc == 0:
                    continue
                scans.append((sc, ext))
            for sc, ext in scans:
                press_key(sc, ext)
            time.sleep(random.uniform(0.03, 0.06))
            for sc, ext in reversed(scans):
                release_key(sc, ext)
        else:
            for k in key_list:
                sc, ext = _resolve_scan(k)
                if sc == 0:
                    continue
                if action == 'p':
                    press_key(sc, ext)
                elif action == 'r':
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

_HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.POINTER(_MSLLHOOKSTRUCT))


# mouse_event 比 SendInput 快得多（无需创建 ctypes 结构体）
_mouse_event = ctypes.windll.user32.mouse_event
# dwExtraInfo 是 Win32 ULONG_PTR (指针大小的整数, 非指针)。必须与 passthrough_manager
# 对同一个 user32.mouse_event 的声明一致 (c_size_t) —— 二者共享同一个缓存函数对象,
# argtypes 互相覆盖; 若这里用 POINTER(c_ulong)+传指针, 运行态被 passthrough 的 c_size_t
# 覆盖后会抛 "argument 5: LP_c_ulong cannot be interpreted as an integer", 滚轮全失效。
_mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
_mouse_event.restype = None

_CallNextHookEx = ctypes.windll.user32.CallNextHookEx
_CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, ctypes.c_size_t, ctypes.POINTER(_MSLLHOOKSTRUCT)]
_CallNextHookEx.restype = ctypes.c_ssize_t

_SetWindowsHookExW = ctypes.windll.user32.SetWindowsHookExW
_SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_SetWindowsHookExW.restype = wintypes.HHOOK

_UnhookWindowsHookEx = ctypes.windll.user32.UnhookWindowsHookEx
_UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_UnhookWindowsHookEx.restype = wintypes.BOOL
MOUSEEVENTF_MOVE = 0x0001

# ─── 鼠标按钮模拟常量 ─────────────────────────────────────────
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP   = 0x0040
MOUSEEVENTF_XDOWN      = 0x0080
MOUSEEVENTF_XUP        = 0x0100
MOUSEEVENTF_WHEEL      = 0x0800
XBUTTON1               = 0x0001
XBUTTON2               = 0x0002
WHEEL_DELTA            = 120

# 按钮名 → (down_flag, up_flag, mouseData)
_MOUSE_BUTTON_MAP = {
    'left':   (MOUSEEVENTF_LEFTDOWN,   MOUSEEVENTF_LEFTUP,   0),
    'right':  (MOUSEEVENTF_RIGHTDOWN,  MOUSEEVENTF_RIGHTUP,  0),
    'middle': (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, 0),
    'x1':     (MOUSEEVENTF_XDOWN,      MOUSEEVENTF_XUP,      XBUTTON1),
    'x2':     (MOUSEEVENTF_XDOWN,      MOUSEEVENTF_XUP,      XBUTTON2),
}


def mouse_press(button: str):
    """按下鼠标按钮。button: 'left', 'right', 'middle', 'x1', 'x2'"""
    entry = _MOUSE_BUTTON_MAP.get(button.lower())
    if not entry:
        logger.debug(f"未知鼠标按钮: '{button}'")
        return
    down_flag, _, mouse_data = entry
    _mouse_event(down_flag, 0, 0, mouse_data, INJECT_MAGIC)


def mouse_release(button: str):
    """释放鼠标按钮。button: 'left', 'right', 'middle', 'x1', 'x2'"""
    entry = _MOUSE_BUTTON_MAP.get(button.lower())
    if not entry:
        logger.debug(f"未知鼠标按钮: '{button}'")
        return
    _, up_flag, mouse_data = entry
    _mouse_event(up_flag, 0, 0, mouse_data, INJECT_MAGIC)


def mouse_wheel(direction: str):
    """模拟鼠标滚轮。direction: 'up' 或 'down'"""
    delta = WHEEL_DELTA if direction.lower() == 'up' else -WHEEL_DELTA
    _mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta & 0xFFFFFFFF, INJECT_MAGIC)


def _mouse_hook_proc(nCode, wParam, lParam):
    """低级鼠标钩子回调。处理全局滚轮捕获。"""
    if nCode >= 0:
        data = lParam.contents

        if wParam == WM_MOUSEWHEEL:
            # mouseData 高16位是滚轮 delta (signed short)
            delta = ctypes.c_short(data.mouseData >> 16).value
            direction = 'up' if delta > 0 else 'down'
            with _wheel_lock:
                _wheel_queue.append((direction, data.pt.x, data.pt.y))

    return _CallNextHookEx(None, nCode, wParam, lParam)


def install_wheel_hook():
    """安装全局鼠标滚轮钩子。在主线程调用。"""
    global _hook_handle, _hook_func_ref
    if _hook_handle is not None:
        return  # 已安装
    _hook_func_ref = _HOOKPROC(_mouse_hook_proc)
    _hook_handle = _SetWindowsHookExW(
        WH_MOUSE_LL, _hook_func_ref, None, 0
    )
    if _hook_handle == 0:
        logger.error("安装鼠标钩子失败")
        _hook_handle = None


def uninstall_wheel_hook():
    """卸载全局鼠标滚轮钩子。"""
    global _hook_handle, _hook_func_ref
    if _hook_handle:
        _UnhookWindowsHookEx(_hook_handle)
        _hook_handle = None
        _hook_func_ref = None


def poll_wheel_events():
    """取出所有待处理的滚轮事件。返回 list of (direction, abs_x, abs_y)。"""
    with _wheel_lock:
        events = list(_wheel_queue)
        _wheel_queue.clear()
    return events


