"""
TEGG Touch (PyQt6) - core/system_tuning.py
系统层调优：进程优先级 + 显示器刷新率自适应。

仅 Windows 生效，其他平台所有函数返回安全默认值并打日志，不抛异常。
所有探测结果有内部缓存，可被反复调用。
"""

import sys
import ctypes
import logging

log = logging.getLogger(__name__)

_cached_refresh_rate: int | None = None
_cached_frame_interval: int | None = None


def boost_process_priority() -> bool:
    """提升当前进程优先级。优先 HIGH，权限不足时降级到 ABOVE_NORMAL。

    返回 True 表示已设置 (任意一档成功)；失败/非 Windows 返回 False。
    游戏满载时确保 UI/输入响应不被普通进程抢占。
    """
    if sys.platform != 'win32':
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        # 关键：64 位系统上 HANDLE 是 64-bit，ctypes 默认 c_int 会截断伪句柄 (-1)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.SetPriorityClass.restype = ctypes.c_int
        handle = kernel32.GetCurrentProcess()
        # 普通用户能设的最高一档是 ABOVE_NORMAL；HIGH 需要 SE_INC_BASE_PRIORITY (通常管理员)
        for name, value in (("HIGH", 0x00000080), ("ABOVE_NORMAL", 0x00008000)):
            if kernel32.SetPriorityClass(handle, value):
                log.info(f"进程优先级已提升至 {name}_PRIORITY_CLASS")
                return True
            err = ctypes.windll.kernel32.GetLastError()
            log.debug(f"SetPriorityClass({name}) 失败, GetLastError={err}")
        log.warning("SetPriorityClass 全部失败 (HIGH + ABOVE_NORMAL)")
        return False
    except Exception as e:
        log.warning(f"提升进程优先级异常: {e}")
        return False


def detect_refresh_rate(default: int = 60) -> int:
    """探测主显示器刷新率 (Hz)。失败/非 Windows → default。结果缓存。"""
    global _cached_refresh_rate
    if _cached_refresh_rate is not None:
        return _cached_refresh_rate
    hz = default
    if sys.platform == 'win32':
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hdc = user32.GetDC(None)
            VREFRESH = 116
            value = gdi32.GetDeviceCaps(hdc, VREFRESH)
            user32.ReleaseDC(None, hdc)
            if value and value > 0:
                hz = int(value)
        except Exception as e:
            log.warning(f"GetDeviceCaps VREFRESH 失败: {e}")
    _cached_refresh_rate = hz
    return hz


def frame_interval_ms(min_interval: int = 4) -> int:
    """根据显示器刷新率推导帧间隔 (ms)。结果缓存。

    60Hz → 17ms, 120Hz → 8ms, 144Hz → 7ms, 240Hz → 4ms。
    用于渲染/位置跟踪类定时器。
    """
    global _cached_frame_interval
    if _cached_frame_interval is not None:
        return _cached_frame_interval
    hz = detect_refresh_rate()
    interval = max(min_interval, int(round(1000.0 / hz)))
    _cached_frame_interval = interval
    log.info(f"显示器 {hz}Hz → 帧间隔 {interval}ms")
    return interval


def input_poll_interval_ms(target_max: int = 8, min_interval: int = 4) -> int:
    """输入轮询间隔：取 min(target_max, frame_interval)，保证不慢于显示。

    60Hz → 8ms (保持原值), 144Hz → 7ms, 240Hz → 4ms。
    用于按键/悬停检测类高频定时器。
    """
    return max(min_interval, min(target_max, frame_interval_ms(min_interval)))
