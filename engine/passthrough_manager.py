"""
TEGG Touch 蛋挞 (PyQt6) - passthrough_manager.py
穿透模式管理器 — 三态穿透模型 (pt_on / pt_off / pt_block)。

旧版: window_manager.py 每帧调用 SetWindowLongW() 切换 WS_EX 样式
新版: Qt 原生 flag + 仅在模式切换时更新（非每帧）
"""

import ctypes
import ctypes.wintypes
import logging

from PyQt6.QtCore import QObject, Qt, pyqtSignal

from core.constants import PT_ON, PT_OFF, PT_BLOCK

user32 = ctypes.windll.user32
logger = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_NOACTIVATE = 0x08000000

# mouse_event flags
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040


class PassthroughManager(QObject):
    """穿透模式管理器

    三态模型:
      pt_on:    全穿透 — UI 上的点击穿透到下方游戏
      pt_off:   智能穿透 — 按钮拦截，空白穿透
      pt_block: 不穿透 — 所有鼠标事件被拦截（视角锁定）
    """

    mode_changed = pyqtSignal(str)

    def __init__(self, window):
        super().__init__()
        self._window = window
        self._mode = PT_OFF
        self._hwnd = None
        # 使用 Win32 方式避免 setWindowFlag 闪烁
        self._use_win32 = True

    def init_hwnd(self):
        """获取窗口句柄（窗口 show 之后调用）"""
        try:
            self._hwnd = int(self._window.winId())
        except Exception:
            self._hwnd = None

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        """切换穿透模式"""
        if mode == self._mode:
            return
        old_mode = self._mode
        self._mode = mode

        if mode == PT_ON:
            self._enable_full_passthrough()
        elif mode == PT_OFF:
            self._enable_smart_passthrough()
        elif mode == PT_BLOCK:
            self._disable_passthrough()

        self.mode_changed.emit(mode)
        logger.info(f"Passthrough: {old_mode} -> {mode}")

    def _enable_full_passthrough(self):
        """全穿透: 所有鼠标事件穿过窗口"""
        if self._use_win32 and self._hwnd:
            old = user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE,
                                   old | WS_EX_TRANSPARENT)
        else:
            self._window.setWindowFlag(
                Qt.WindowType.WindowTransparentForInput, True)
            self._window.show()

    def _disable_passthrough(self):
        """不穿透: 窗口拦截所有鼠标事件"""
        if self._use_win32 and self._hwnd:
            old = user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE,
                                   old & ~WS_EX_TRANSPARENT)
        else:
            self._window.setWindowFlag(
                Qt.WindowType.WindowTransparentForInput, False)
            self._window.show()

    def _enable_smart_passthrough(self):
        """智能穿透: 默认穿透，由轮询定时器动态切换

        空白区域远多于按钮区域，默认穿透更安全 —
        16ms 内轮询定时器会精确设置正确的 WS_EX 状态。
        """
        self._enable_full_passthrough()

    def update_smart_passthrough(self, is_on_ui: bool):
        """根据鼠标是否在 UI 上动态切换穿透状态（每帧调用）

        PT_OFF:  on_ui → no_focus（拦截）, off_ui → click_through（穿透）
        PT_BLOCK: on_ui → click_through（穿透）, off_ui → no_focus（拦截/锁视角）
        PT_ON:   始终穿透，不需要动态切换
        """
        if self._mode == PT_ON:
            return
        if not self._hwnd:
            return

        old = user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)

        if self._mode == PT_OFF:
            if is_on_ui:
                # 在按钮上 → 不穿透，使用 no_focus 模式
                new_style = (old & ~WS_EX_TRANSPARENT) | WS_EX_NOACTIVATE
            else:
                # 在空白区 → 穿透
                new_style = old | WS_EX_TRANSPARENT
        elif self._mode == PT_BLOCK:
            if is_on_ui:
                # 在按钮上 → 穿透（双层触发：按钮 + 游戏）
                new_style = old | WS_EX_TRANSPARENT
            else:
                # 在空白区 → 不穿透（锁定视角）
                new_style = (old & ~WS_EX_TRANSPARENT) | WS_EX_NOACTIVATE
        else:
            return

        if old != new_style:
            user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE, new_style)

    def should_forward_to_game(self, scene_pos) -> bool:
        """智能穿透模式下，判断是否应将事件转发到下层窗口"""
        if self._mode != PT_BLOCK:
            return False
        scene = self._window.scene()
        if scene is None:
            return True
        item = scene.itemAt(scene_pos, self._window.transform())
        return item is None

    def forward_click_to_game(self, global_pos, button=None):
        """将鼠标点击转发到下方窗口

        通过临时设置 WS_EX_TRANSPARENT 并模拟鼠标按键实现穿透。
        """
        if not self._hwnd:
            return

        from PyQt6.QtCore import Qt, QTimer

        # 确定鼠标按键的 down/up 事件标志
        if button == Qt.MouseButton.RightButton:
            down_flag = MOUSEEVENTF_RIGHTDOWN
            up_flag = MOUSEEVENTF_RIGHTUP
        elif button == Qt.MouseButton.MiddleButton:
            down_flag = MOUSEEVENTF_MIDDLEDOWN
            up_flag = MOUSEEVENTF_MIDDLEUP
        else:
            down_flag = MOUSEEVENTF_LEFTDOWN
            up_flag = MOUSEEVENTF_LEFTUP

        # 1. 临时穿透
        old_style = user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE,
                               old_style | WS_EX_TRANSPARENT)

        # 2. 模拟鼠标点击 (down + up)
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        user32.mouse_event(up_flag, 0, 0, 0, 0)

        # 3. 延迟恢复窗口样式 (让点击有时间被下层窗口接收)
        def _restore():
            user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE, old_style)

        QTimer.singleShot(50, _restore)

    def ensure_game_focus(self):
        """确保游戏窗口保持焦点（防止误抢焦）"""
        if not self._hwnd:
            return
        fg = user32.GetForegroundWindow()
        if fg == self._hwnd:
            # 我们的窗口意外获得了焦点
            pt = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))

            old_style = user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE,
                                   old_style | WS_EX_TRANSPARENT)
            game_hwnd = user32.WindowFromPoint(pt)
            user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE, old_style)

            if game_hwnd and game_hwnd != self._hwnd:
                user32.SetForegroundWindow(game_hwnd)
