"""Automatic independent pointer for games that warp or confine the OS cursor.

Normally the system cursor remains authoritative. A read-only Raw Input stream
detects sustained motion against a cursor locked at the game's centre. Only
then do we integrate motion ourselves, returning to the OS on release/focus
change. No per-packet Qt signals or game input suppression are used.
"""

import ctypes
from ctypes import wintypes
import logging
import math
import os
import threading
from dataclasses import dataclass
from collections import deque
import statistics
import time

from PyQt6.QtCore import QObject, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QCursor, QGuiApplication

log = logging.getLogger(__name__)
_user32 = ctypes.WinDLL('user32', use_last_error=True)
_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)
WM_INPUT, WM_QUIT = 0x00FF, 0x0012
RID_INPUT, RIDEV_INPUTSINK, RIDEV_REMOVE = 0x10000003, 0x100, 1
MOUSE_MOVE_ABSOLUTE, MOUSE_VIRTUAL_DESKTOP = 1, 2


class _WindowClass(ctypes.Structure):
    _fields_ = [('style', wintypes.UINT),
                ('proc', _WNDPROC), ('class_extra', ctypes.c_int),
                ('window_extra', ctypes.c_int), ('instance', wintypes.HINSTANCE),
                ('icon', wintypes.HICON), ('cursor', wintypes.HANDLE),
                ('background', wintypes.HBRUSH), ('menu', wintypes.LPCWSTR),
                ('name', wintypes.LPCWSTR)]


class _Device(ctypes.Structure):
    _fields_ = [('page', wintypes.USHORT), ('usage', wintypes.USHORT),
                ('flags', wintypes.DWORD), ('target', wintypes.HWND)]


class _Header(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('size', wintypes.DWORD),
                ('device', wintypes.HANDLE), ('param', wintypes.WPARAM)]


class _Mouse(ctypes.Structure):
    # buttons is the aligned ULONG union containing usButtonFlags/usButtonData.
    _fields_ = [('flags', wintypes.USHORT), ('buttons', wintypes.ULONG),
                ('raw_buttons', wintypes.ULONG), ('x', wintypes.LONG),
                ('y', wintypes.LONG), ('extra', wintypes.ULONG)]


_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WindowClass)]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
_user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(_Device), wintypes.UINT, wintypes.UINT]
_user32.RegisterRawInputDevices.restype = wintypes.BOOL
_user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT]
_user32.GetRawInputData.restype = wintypes.UINT
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
_user32.SetCursorPos.restype = wintypes.BOOL
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.GetClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class _CursorInfo(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('cursor', wintypes.HANDLE), ('position', wintypes.POINT)]


_user32.GetCursorInfo.argtypes = [ctypes.POINTER(_CursorInfo)]


class RawMouseReader:
    """Thread-owned message window; coalesces relative motion between UI ticks."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = []
        self._wheel = 0
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._thread = None
        self._thread_id = 0
        self._registered = False
        self._error_reported = False
        self._buffer = ctypes.create_string_buffer(512)
        self._proc = _WNDPROC(self._message)

    @property
    def alive(self):
        return bool(self._registered and self._thread and self._thread.is_alive())

    def start(self):
        if self._thread is not None:
            return self.alive
        self._thread = threading.Thread(target=self._run, name='tegg-raw-mouse', daemon=True)
        self._thread.start()
        if not self._ready.wait(2) or not self.alive:
            self.stop()
            return False
        return True

    def stop(self):
        self._stopping.set()
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(2)
        self.drain()

    def drain(self):
        with self._lock:
            events, self._pending = self._pending, []
        return events

    def drain_wheel(self):
        with self._lock:
            delta, self._wheel = self._wheel, 0
        return delta

    def _run(self):
        hwnd = None
        atom = 0
        name = f'TEGGCursorInput-{os.getpid()}-{id(self)}'
        instance = _kernel32.GetModuleHandleW(None)
        self._thread_id = _kernel32.GetCurrentThreadId()
        try:
            wc = _WindowClass()
            wc.proc, wc.instance, wc.name = self._proc, instance, name
            atom = _user32.RegisterClassW(ctypes.byref(wc))
            if not atom:
                raise ctypes.WinError(ctypes.get_last_error())
            hwnd = _user32.CreateWindowExW(0, name, '', 0, 0, 0, 0, 0,
                                           wintypes.HWND(-3), None, instance, None)
            if not hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            device = _Device(1, 2, RIDEV_INPUTSINK, hwnd)
            if not _user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._registered = True
            self._ready.set()
            msg = wintypes.MSG()
            while not self._stopping.is_set():
                result = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    break
                _user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            log.exception('独立光标 Raw Input 启动/监听失败')
        finally:
            if self._registered:
                device = _Device(1, 2, RIDEV_REMOVE, None)
                _user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device))
            self._registered = False
            if hwnd:
                _user32.DestroyWindow(hwnd)
            if atom:
                _user32.UnregisterClassW(name, instance)
            self._ready.set()

    def _message(self, hwnd, message, wp, lp):
        if message == WM_INPUT:
            try:
                size = wintypes.UINT(len(self._buffer))
                count = _user32.GetRawInputData(lp, RID_INPUT, self._buffer,
                                                ctypes.byref(size), ctypes.sizeof(_Header))
                if count != 0xFFFFFFFF and count >= ctypes.sizeof(_Header) + ctypes.sizeof(_Mouse):
                    header = _Header.from_buffer(self._buffer)
                    if header.type == 0:
                        mouse = _Mouse.from_buffer(self._buffer, ctypes.sizeof(_Header))
                        wheel = (ctypes.c_short(mouse.buttons >> 16).value
                                 if mouse.buttons & 0x0400 else 0)
                        self.feed(mouse.flags, mouse.x, mouse.y, wheel)
            except Exception:
                if not self._error_reported:
                    log.exception('独立光标 Raw Input 数据读取失败')
                    self._error_reported = True
        return _user32.DefWindowProcW(hwnd, message, wp, lp)

    def feed(self, flags, x, y, wheel=0):
        absolute = bool(flags & MOUSE_MOVE_ABSOLUTE)
        with self._lock:
            self._wheel += wheel
            if not absolute and not (x or y):
                return
            if not absolute and self._pending and not (self._pending[-1][0] & MOUSE_MOVE_ABSOLUTE):
                _, old_x, old_y = self._pending[-1]
                self._pending[-1] = (0, old_x + x, old_y + y)
            else:
                # Absolute reports supersede earlier positions, so no unbounded queue.
                if absolute:
                    self._pending.clear()
                self._pending.append((flags, x, y))


@dataclass(frozen=True)
class CursorProbe:
    position: tuple[float, float]
    centre: tuple[float, float]
    visible: bool = True
    tiny_clip: bool = False
    foreground: int = 1
    external: bool = True
    owned: bool = False


class AdaptivePointer:
    """Deterministic detector, independent of timers, Win32 and Qt event delivery.

    Require sustained directional physical motion with <= 12 px OS travel near
    the client centre (or an explicit tiny ClipCursor rectangle). A still mouse,
    screen edge, ordinary cursor movement or absolute input is not a lock.
    """

    def __init__(self, bounds):
        self.bounds = QRect(bounds)
        self.independent = False
        self.position = (float(bounds.center().x()), float(bounds.center().y()))
        self.gain = 1.0
        self._ratios = deque(maxlen=16)
        self._last = None
        self._samples = deque()
        self._release_at = None
        self._hidden_at_lock = False
        self._ignore_until = 0.0
        self._game_foreground = None
        self._game_centre = None

    def reset(self, position, now=0.0):
        self.independent = False
        self.position = tuple(position)
        self._samples.clear()
        self._release_at = None
        self._last = None
        self._ignore_until = now

    def recenter(self, position, now):
        self.position = self._clamp(position)
        self._samples.clear()
        self._last = None
        # Our own system warp is not evidence of a game capture.
        self._ignore_until = now + 0.25

    def _clamp(self, p):
        return (max(self.bounds.left(), min(self.bounds.right(), p[0])),
                max(self.bounds.top(), min(self.bounds.bottom(), p[1])))

    def advance(self, now, probe, events):
        old_mode = self.independent
        previous = self._last
        # Our toolbar/dialog is part of the same pointer session. Keep the
        # game's anchor while it owns focus; its client centre is not a new lock.
        internal = probe.owned or (previous is not None and previous.owned
                                   and probe.foreground == self._game_foreground)
        focus_changed = (previous is not None and previous.foreground != probe.foreground
                         and not internal)
        if probe.external:
            self._game_foreground, self._game_centre = probe.foreground, probe.centre
        if focus_changed or not (probe.external or probe.owned):
            self.reset(probe.position, now + 0.15)
            self._last = probe
            return old_mode != self.independent, focus_changed
        self._last = probe
        # An absolute tablet/touch report must never be interpreted as a delta.
        if any(flags & MOUSE_MOVE_ABSOLUTE for flags, _, _ in events):
            self.reset(probe.position, now + 0.25)
            self._last = probe
            return old_mode != self.independent, False
        dx = sum(x for _, x, _ in events)
        dy = sum(y for _, _, y in events)
        raw_length = math.hypot(dx, dy)
        centre = self._game_centre if probe.owned and self._game_centre else probe.centre
        near_centre = math.dist(probe.position, centre) <= 16
        near_edge = (probe.position[0] <= self.bounds.left() + 3 or
                     probe.position[0] >= self.bounds.right() - 3 or
                     probe.position[1] <= self.bounds.top() + 3 or
                     probe.position[1] >= self.bounds.bottom() - 3)
        # Learn OS pointer scale only from real, aligned travel, away from warps.
        if previous and raw_length >= 2 and not self.independent and not near_centre:
            sx, sy = (probe.position[i] - previous.position[i] for i in (0, 1))
            distance = math.hypot(sx, sy)
            if distance and (sx * dx + sy * dy) / (distance * raw_length) > 0.95:
                ratio = distance / raw_length
                if 0.05 <= ratio <= 8:
                    self._ratios.append(ratio)
                    self.gain = statistics.median(self._ratios)

        if self.independent:
            self.position = self._clamp((self.position[0] + dx * self.gain,
                                         self.position[1] + dy * self.gain))
            # Native menus usually reveal the OS cursor. Custom-cursor menus
            # can also be recognised by sustained travel away from the anchor.
            released = not probe.tiny_clip and (
                (self._hidden_at_lock and probe.visible and not probe.owned) or not near_centre)
            if released:
                if self._release_at is None:
                    self._release_at = now
                if now - self._release_at >= 0.12:
                    self.reset(probe.position, now + 0.25)
                    self._last = probe
            else:
                self._release_at = None
            return old_mode != self.independent, False

        self.position = probe.position
        if (now < self._ignore_until or near_edge or not (near_centre or probe.tiny_clip)
                or (probe.owned and self._game_centre is None)):
            self._samples.clear()
            return False, False
        if self._samples and now - self._samples[-1][0] > 0.08:
            self._samples.clear()
        if raw_length:
            self._samples.append((now, dx, dy, probe.position))
        while self._samples and now - self._samples[0][0] > 0.45:
            self._samples.popleft()
        if len(self._samples) < 4:
            return False, False
        elapsed = self._samples[-1][0] - self._samples[0][0]
        rx, ry = (sum(s[i] for s in self._samples) for i in (1, 2))
        positions = [s[3] for s in self._samples]
        span = math.hypot(max(p[0] for p in positions) - min(p[0] for p in positions),
                          max(p[1] for p in positions) - min(p[1] for p in positions))
        duration = 0.08 if probe.tiny_clip else 0.18
        if elapsed >= duration and span <= 12 and math.hypot(rx, ry) * self.gain >= 40:
            self.independent = True
            self._hidden_at_lock = not probe.visible
            self.position = self._clamp((probe.position[0] + rx * self.gain,
                                         probe.position[1] + ry * self.gain))
            self._samples.clear()
            return True, False
        return False, False


class CursorInput(QObject):
    """Shared source; poll once per input tick, render the same logical position."""

    mode_changed = pyqtSignal(bool)

    def __init__(self, parent=None, reader_factory=RawMouseReader):
        super().__init__(parent)
        self._reader_factory = reader_factory
        self._reader = None
        self._model = AdaptivePointer(QRect(0, 0, 1920, 1080))
        self._diag_at = 0.0
        self._diag_raw = [0, 0]
        self._diag_motion = False
        self._wheel_delta = 0

    @property
    def independent(self):
        return self._model.independent

    def start(self, bounds):
        self.stop()
        self._model = AdaptivePointer(bounds)
        self._diag_at = time.monotonic()
        self._diag_raw = [0, 0]
        self._diag_motion = False
        reader = self._reader_factory()
        if reader.start():
            self._reader = reader
            log.info('自动光标监听已启动: bounds=%s', bounds.getRect())
        else:
            log.warning('自动光标监听不可用，继续使用系统光标')

    def stop(self):
        was_independent = self.independent
        if self._reader:
            self._reader.stop()
            self._reader = None
        self._model.reset((QCursor.pos().x(), QCursor.pos().y()))
        self._wheel_delta = 0
        if was_independent:
            self.mode_changed.emit(False)

    @staticmethod
    def _probe():
        point = QCursor.pos()
        hwnd = _user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wintypes.RECT()
        centre = wintypes.POINT()
        if _user32.GetClientRect(hwnd, ctypes.byref(rect)):
            centre.x = (rect.left + rect.right) // 2
            centre.y = (rect.top + rect.bottom) // 2
            _user32.ClientToScreen(hwnd, ctypes.byref(centre))
        else:
            centre.x, centre.y = -100000, -100000
        # Relate Win32 physical points to Qt's logical pixels on the current
        # screen. The native/Qt cursor pair anchors the conversion (incl. DPI).
        native = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(native))
        screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        centre_qt = (point.x() + (centre.x - native.x) / dpr,
                     point.y() + (centre.y - native.y) / dpr)
        clip = wintypes.RECT()
        clipped = bool(_user32.GetClipCursor(ctypes.byref(clip)))
        tiny = clipped and clip.right - clip.left <= 4 and clip.bottom - clip.top <= 4
        info = _CursorInfo()
        info.size = ctypes.sizeof(info)
        visible = bool(info.flags & 1) if _user32.GetCursorInfo(ctypes.byref(info)) else True
        # A BlankCursor supplied by our overlay is not the game's menu cursor.
        hit_pid = wintypes.DWORD()
        hit = _user32.WindowFromPoint(native)
        _user32.GetWindowThreadProcessId(hit, ctypes.byref(hit_pid))
        if hit_pid.value == os.getpid():
            visible = False
        return CursorProbe((point.x(), point.y()), centre_qt, visible, tiny,
                           int(hwnd or 0), bool(pid.value and pid.value != os.getpid()),
                           pid.value == os.getpid())

    def poll(self):
        """Return True on a transition so held pointer actions can be released."""
        if self._reader is None:
            return False
        if not self._reader.alive:
            log.warning('自动光标监听中断，恢复系统光标')
            was_independent = self.independent
            self.stop()
            return was_independent
        probe = self._probe()
        now = time.monotonic()
        events = self._reader.drain()
        changed, focus_changed = self._model.advance(now, probe, events)
        wheel = self._reader.drain_wheel()
        self._wheel_delta += wheel if self.independent else 0
        for flags, x, y in events:
            if not (flags & MOUSE_MOVE_ABSOLUTE):
                self._diag_raw[0] += x
                self._diag_raw[1] += y
                self._diag_motion |= bool(x or y)
        if self._diag_motion and now - self._diag_at >= 2:
            log.info('光标诊断: mode=%s hwnd=%s raw_delta=%s system=%s centre=%s logical=%s visible=%s tiny_clip=%s gain=%.2f',
                     'independent' if self.independent else 'system', probe.foreground,
                     tuple(self._diag_raw), probe.position, probe.centre, self._model.position,
                     probe.visible, probe.tiny_clip, self._model.gain)
            self._diag_at = now
            self._diag_raw = [0, 0]
            self._diag_motion = False
        if changed:
            log.info('自动光标切换: %s | hwnd=%s system=%s logical=%s visible=%s tiny_clip=%s gain=%.2f',
                     '独立' if self.independent else '系统', probe.foreground,
                     probe.position, self._model.position, probe.visible, probe.tiny_clip,
                     self._model.gain)
            self.mode_changed.emit(self.independent)
        return changed or focus_changed

    def take_wheel_delta(self):
        delta, self._wheel_delta = self._wheel_delta, 0
        return delta

    def position(self):
        if not self.independent:
            return QCursor.pos()
        return QPoint(round(self._model.position[0]), round(self._model.position[1]))

    def set_position(self, x, y):
        if self._reader:
            self._reader.drain()
        self._model.recenter((x, y), time.monotonic())
        if not self.independent:
            return bool(_user32.SetCursorPos(int(x), int(y)))
        return True
