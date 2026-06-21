"""焦点调试辅助 — 查询当前 Windows 前景窗口的 HWND / 标题 / 进程名。

用途: 排查"语音/快捷键识别成功但游戏没响应"这类失焦问题。
SendInput 把按键发给前景窗口, 蛋挞 UI 一旦意外抢焦, 按键就送错地方。
在关键过渡点 (语音开关 / 模式切换 / 语音指令触发) 调用 format_foreground()
拼到日志里, 后续看 logs 就能定位是哪一步把焦点拐走了。

任何调用失败都返回空字符串/0, 不抛异常 — 调试辅助绝不能把主流程搞炸。
"""

import ctypes
import ctypes.wintypes
import os

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
_user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowThreadProcessId.argtypes = [
    ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)
]
_user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_kernel32.OpenProcess.argtypes = [
    ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD
]
_kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
_kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
_kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
    ctypes.c_wchar_p, ctypes.POINTER(ctypes.wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL


def get_foreground_info():
    """返回 (hwnd, title, exe_basename); 失败时单项填 0 / ''."""
    try:
        hwnd = _user32.GetForegroundWindow() or 0
        if not hwnd:
            return 0, '', ''

        title_buf = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, title_buf, 256)
        title = title_buf.value

        pid = ctypes.wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        exe = ''
        if pid.value:
            h = _kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if h:
                try:
                    buf = ctypes.create_unicode_buffer(512)
                    size = ctypes.wintypes.DWORD(512)
                    if _kernel32.QueryFullProcessImageNameW(
                            h, 0, buf, ctypes.byref(size)):
                        exe = os.path.basename(buf.value)
                finally:
                    _kernel32.CloseHandle(h)

        return hwnd, title, exe
    except Exception:
        return 0, '', ''


def format_foreground(label: str = 'fg') -> str:
    """紧凑日志字符串, 直接拼到 logger.info 行尾。

    例: logger.info("Voice ON | %s", format_foreground())
        → Voice ON | fg=[hwnd=0x12345 exe=cs2.exe title='Counter-Strike 2']
    """
    hwnd, title, exe = get_foreground_info()
    return f"{label}=[hwnd=0x{hwnd:X} exe={exe} title={title!r}]"
