"""
TEGG Touch 蛋挞 (PyQt6) - keyboard_hook.py
键盘映射 (remap) — WH_KEYBOARD_LL 低级键盘钩子。

职责: 截获物理按键 → 查当前 profile 的映射表 → 吞掉原键 + 触发目标动作。
目标动作字符串复用 run_controller._smart_trigger 的语法 (普通键 / mouse: /
gp: / xmacro: / app: / recenter:), 所以这里只负责「截获 + 路由」, 不负责执行。

两条分发路径 (按耗时分流, 这不是优化而是硬要求):
  - 快路径: mode=hold 且目标是纯键盘键 → 在钩子回调里直接 SendInput, 零延迟;
  - 慢路径: 其余 (宏/手柄/鼠标/应用/回中/click/toggle) → 入队, 由 run_controller
            的 tick (4~8ms) 取出走 _smart_trigger。
低级钩子跑在主线程消息循环上, 单次回调超过 LowLevelHooksTimeout (默认 300ms)
系统会直接把钩子摘掉 —— 带 sleep 的宏绝不能在回调里跑。

防回环: input_engine 发出的所有事件 dwExtraInfo 都填 INJECT_MAGIC, 这里见到就
放行。否则「A→D 同时 D→A」会被自己的注入再次命中, 无限回环。
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading
from collections import deque

from core.input_engine import (
    INJECT_MAGIC, _resolve_scan, press_key, release_key,
)

logger = logging.getLogger(__name__)

# ─── Win32 常量 ──────────────────────────────────────────────

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_EXTENDED = 0x01

HC_ACTION = 0


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        # ULONG_PTR: 指针大小的整数 (不是指针) —— 与 input_engine.KeyBdInput 一致
        ('dwExtraInfo', ctypes.c_size_t),
    ]


_KB_HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t,
    ctypes.POINTER(_KBDLLHOOKSTRUCT))

# 必须用「私有」的 user32 实例, 不能用 ctypes.windll.user32 ——
# ctypes.windll 是全局缓存: 同一个 DLL 里同名函数返回的是同一个函数对象,
# argtypes 会被后设置的一方覆盖。input_engine 也给 SetWindowsHookExW /
# CallNextHookEx 设过 argtypes (鼠标钩子那套 HOOKPROC + MSLLHOOKSTRUCT),
# 共用的话两边互相踩, 表现为 install_wheel_hook() 抛
# "expected CFunctionType instead of CFunctionType" —— 滚轮钩子装不上,
# 连带整个运行模式起不来。WinDLL() 每次构造都是独立实例, 各管各的。
_user32 = ctypes.WinDLL("user32", use_last_error=True)

_SetWindowsHookExW = _user32.SetWindowsHookExW
_SetWindowsHookExW.argtypes = [ctypes.c_int, _KB_HOOKPROC,
                               wintypes.HINSTANCE, wintypes.DWORD]
_SetWindowsHookExW.restype = wintypes.HHOOK

_UnhookWindowsHookEx = _user32.UnhookWindowsHookEx
_UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_UnhookWindowsHookEx.restype = wintypes.BOOL

_CallNextHookEx = _user32.CallNextHookEx
_CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, ctypes.c_size_t,
                            ctypes.POINTER(_KBDLLHOOKSTRUCT)]
_CallNextHookEx.restype = ctypes.c_ssize_t

# ─── 模块状态 ────────────────────────────────────────────────

_hook_handle = None
_hook_func_ref = None          # 防 GC: 回调对象被回收会导致进程崩溃

# (scan, extended) → {'dst': str, 'mode': str}
_table: dict = {}
_enabled = False               # 总开关 (F2 / 弹窗勾选)

# 按下中的键: (scan, extended) → {'dst', 'mode', 'fast': [(sc, ext), ...]}
# 记录「按下那一刻解析出的目标」, 抬起时释放同一个 —— 中途改表/切 profile 不卡键
_down: dict = {}

# 慢路径事件队列: (dst, action)  action ∈ 'p' | 'r' | 'click'
_queue: deque = deque(maxlen=128)
_queue_lock = threading.Lock()

# toggle 模式已锁定的键: (scan, extended) → dst
_toggled: dict = {}

# 捕获模式 (弹窗录入物理键时打开): 吞掉一切按键, 只把键名塞进 _captured
_capture_active = False
_captured: deque = deque(maxlen=8)


# ─── 键名 ⇄ 扫描码 ───────────────────────────────────────────
# 与候选键位面板 (button_editor_dialog._get_key_categories) 同一套名字, 保证
# 捕获出来的名字 input_engine._resolve_scan 一定认得。
_CAPTURE_NAME_POOL = (
    [chr(c) for c in range(ord('a'), ord('z') + 1)]
    + [str(i) for i in range(10)]
    + [f"f{i}" for i in range(1, 13)]
    + ["up", "down", "left", "right"]
    + ["ctrl", "shift", "alt", "windows", "caps lock", "menu",
       "right ctrl", "right shift", "right alt", "right windows"]
    + ["space", "enter", "esc", "tab", "backspace"]
    + [",", ".", "/", ";", "'", "[", "]", "\\", "-", "=", "`"]
    + ["home", "end", "pageup", "pagedown", "insert", "delete",
       "print screen", "scroll lock"]
    + [f"num {i}" for i in range(10)]
    + ["num lock", "num *", "num +", "num -", "num /", "num .", "num enter"]
)

_scan_to_name: dict = {}


def _ensure_reverse_map():
    """(scan, extended) → 键名。首个占位优先, 后面的同码名字不覆盖
    (如 'ctrl' 先于 'right ctrl' 各占各的 extended 位, 不冲突)。"""
    global _scan_to_name
    if _scan_to_name:
        return
    m = {}
    for name in _CAPTURE_NAME_POOL:
        sc, ext = _resolve_scan(name)
        if sc == 0:
            continue
        m.setdefault((sc, ext), name)
    _scan_to_name = m


def scan_to_name(scan: int, extended: bool):
    """扫描码 → 键名; 认不出返回 None。"""
    _ensure_reverse_map()
    return _scan_to_name.get((scan, extended))


# ─── 映射表 ──────────────────────────────────────────────────

def _is_pure_keys(dst: str) -> bool:
    """目标是否为「纯键盘键」(可走钩子内快路径)。"""
    for p in dst.split('+'):
        p = p.strip()
        if not p:
            return False
        if ':' in p:        # mouse: / gp: / xmacro: / app: / recenter: ...
            return False
    return True


def set_remaps(remaps, enabled: bool = True):
    """载入映射表。remaps: [{src, dst, mode, enabled}]

    重建表前先把当前按下的目标全部释放, 避免换表后残留卡键。
    """
    release_all()
    table = {}
    for r in (remaps or []):
        if not isinstance(r, dict) or not r.get('enabled', True):
            continue
        src = (r.get('src') or '').strip()
        dst = (r.get('dst') or '').strip()
        if not src or not dst:
            continue
        sc, ext = _resolve_scan(src)
        if sc == 0:
            logger.warning("键盘映射: 无法解析物理键 '%s', 已跳过", src)
            continue
        mode = r.get('mode') or 'hold'
        if mode not in ('hold', 'click', 'toggle'):
            mode = 'hold'
        # 宏/应用/回中这类「一次性动作」按住不放没有意义, 强制成 click
        if mode == 'hold' and not _is_pure_keys(dst) and _oneshot_only(dst):
            mode = 'click'
        table[(sc, ext)] = {'dst': dst, 'mode': mode,
                            'fast': _is_pure_keys(dst)}
    global _table, _enabled
    _table = table
    _enabled = bool(enabled)
    logger.info("键盘映射已载入: %d 条, 启用=%s", len(table), _enabled)


def _oneshot_only(dst: str) -> bool:
    """目标是否只由「一次性动作」构成 (宏 / 启动应用 / 回中)。
    这些动作没有 press/release 语义, hold 模式对它们等同于 click。"""
    parts = [p.strip() for p in dst.split('+') if p.strip()]
    if not parts:
        return False
    return all(p.startswith(('xmacro:', 'macro:', 'gpmacro:', 'app:', 'recenter:'))
               for p in parts)


def set_enabled(on: bool):
    """总开关。关闭时立刻释放已按下的目标, 防卡键。"""
    global _enabled
    if not on:
        release_all()
    _enabled = bool(on)


def is_enabled() -> bool:
    return _enabled


def has_remaps() -> bool:
    return bool(_table)


# ─── 事件分发 ────────────────────────────────────────────────

def _enqueue(dst: str, action: str):
    with _queue_lock:
        _queue.append((dst, action))


def poll_events():
    """取出待处理的慢路径事件。返回 [(dst, action), ...]"""
    with _queue_lock:
        if not _queue:
            return []
        events = list(_queue)
        _queue.clear()
    return events


def _on_key_down(key) -> bool:
    """返回 True 表示吞掉此键。"""
    if key in _down:
        return True             # 系统自动重复: 吞掉但不重复触发
    entry = _table.get(key)
    if entry is None:
        return False
    dst, mode, fast = entry['dst'], entry['mode'], entry['fast']

    if mode == 'toggle':
        if key in _toggled:
            _release_target(dst, fast)
            _toggled.pop(key, None)
        else:
            _press_target(dst, fast)
            _toggled[key] = dst
        # toggle 不记 _down (按下即完成一次切换), 但要挡住自动重复
        _down[key] = {'dst': dst, 'fast': fast, 'mode': mode}
        return True

    if mode == 'click':
        _enqueue(dst, 'click')
        _down[key] = {'dst': dst, 'fast': fast, 'mode': mode}
        return True

    # hold
    _press_target(dst, fast)
    _down[key] = {'dst': dst, 'fast': fast, 'mode': mode}
    return True


def _on_key_up(key) -> bool:
    held = _down.pop(key, None)
    if held is None:
        # 没记录过按下 (映射是按住期间才加的 / 按下时没命中) → 抬起放行,
        # 否则原键会只按下不抬起, 在目标程序里卡住
        return False
    if held['mode'] == 'hold':
        _release_target(held['dst'], held['fast'])
    return True


def _press_target(dst: str, fast: bool):
    if fast:
        for p in dst.split('+'):
            sc, ext = _resolve_scan(p.strip())
            if sc:
                press_key(sc, ext)
    else:
        _enqueue(dst, 'p')


def _release_target(dst: str, fast: bool):
    if fast:
        # 逆序释放, 与 input_engine.trigger 的组合键语义一致
        for p in reversed([x.strip() for x in dst.split('+')]):
            sc, ext = _resolve_scan(p)
            if sc:
                release_key(sc, ext)
    else:
        _enqueue(dst, 'r')


def release_all():
    """释放所有按下中的目标 —— 停止运行 / 卸载钩子 / 切 profile 时必须调用。"""
    for key, held in list(_down.items()):
        if held.get('mode') == 'hold':
            try:
                _release_target(held['dst'], held['fast'])
            except Exception:
                logger.exception("释放映射目标失败: %s", held.get('dst'))
    _down.clear()
    for key, dst in list(_toggled.items()):
        try:
            _release_target(dst, _is_pure_keys(dst))
        except Exception:
            logger.exception("释放 toggle 目标失败: %s", dst)
    _toggled.clear()


# ─── 捕获模式 (弹窗录入物理键) ───────────────────────────────

def start_capture():
    """进入捕获模式: 吞掉一切按键, 只把键名记进队列。会自动装钩子。"""
    global _capture_active
    _capture_active = True
    install_hook()


def stop_capture():
    global _capture_active
    _capture_active = False
    _captured.clear()
    # 捕获是编辑模式下的临时行为, 没有映射表就顺手把钩子卸掉
    if not _table:
        uninstall_hook()


def poll_captured():
    """取出捕获到的键名 (最新一个); 无则 None。"""
    if not _captured:
        return None
    name = _captured[-1]
    _captured.clear()
    return name


# ─── 钩子 ────────────────────────────────────────────────────

def _hook_proc(nCode, wParam, lParam):
    try:
        if nCode == HC_ACTION:
            kb = lParam.contents
            # 自注入事件直接放行 —— 少了这一步 A↔D 互换会无限回环
            if kb.dwExtraInfo != INJECT_MAGIC:
                scan = kb.scanCode & 0xFF
                ext = bool(kb.flags & LLKHF_EXTENDED)
                key = (scan, ext)
                is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)

                if _capture_active:
                    if is_down:
                        name = scan_to_name(scan, ext)
                        if name:
                            _captured.append(name)
                    return 1        # 捕获期间吞掉一切, 免得录键时误触发

                if _enabled and _table:
                    if is_down and _on_key_down(key):
                        return 1
                    if is_up and _on_key_up(key):
                        return 1
    except Exception:
        # 钩子回调里抛异常会被 ctypes 吞掉且可能导致钩子被摘, 这里兜住并记录
        logger.exception("键盘钩子回调异常")
    return _CallNextHookEx(None, nCode, wParam, lParam)


def install_hook():
    """安装低级键盘钩子。必须在主线程 (有消息循环) 调用。"""
    global _hook_handle, _hook_func_ref
    if _hook_handle is not None:
        return True
    _hook_func_ref = _KB_HOOKPROC(_hook_proc)
    _hook_handle = _SetWindowsHookExW(WH_KEYBOARD_LL, _hook_func_ref, None, 0)
    if not _hook_handle:
        err = ctypes.get_last_error() if hasattr(ctypes, 'get_last_error') else 0
        logger.error("安装键盘钩子失败 (err=%s)", err)
        _hook_handle = None
        _hook_func_ref = None
        return False
    logger.info("键盘钩子已安装")
    return True


def uninstall_hook():
    """卸载钩子 + 释放残留按键 + 清空映射表。

    清表是刻意的: 「表非空」⇔「正处于运行模式」这个不变量, 让捕获模式
    (编辑态临时装钩子) 能据此判断退出时该不该把钩子一起摘掉。
    """
    global _hook_handle, _hook_func_ref, _table
    release_all()
    _table = {}
    if _hook_handle:
        _UnhookWindowsHookEx(_hook_handle)
        _hook_handle = None
        _hook_func_ref = None
        logger.info("键盘钩子已卸载")
    with _queue_lock:
        _queue.clear()


def is_installed() -> bool:
    return _hook_handle is not None
