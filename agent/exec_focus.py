"""
TEGGTouch 蛋挞 — 执行前焦点校正 (阶段2)

问题: run_action 用 SendInput 发给**前景窗口**。用户在 AI 面板点"执行"/打字时, 面板
是前景 → 按键进了面板而非目标程序(游戏/测试窗), 看着执行了却没效果。

方案: 持续记录"最后一个非蛋挞前景窗"(_target); run_action 真发输入前, 若当前前景不是它,
先 SetForegroundWindow(_target) 并等一小会儿让焦点落定, 再发。蛋挞本身是前景进程,
把焦点让给别的窗口是允许的。

note_target 由主线程定时喂 (排除蛋挞自己的窗口句柄); focus_target 由 AgentThread 子线程
执行前调 (SetForegroundWindow 跨线程可用)。
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time

logger = logging.getLogger(__name__)

_target = 0   # 最后一个非蛋挞前景窗 HWND


def note_target(fg_hwnd: int, own_hwnds) -> None:
    """主线程定时调: 若前景窗不是蛋挞自己的, 记为目标。"""
    global _target
    try:
        if fg_hwnd and int(fg_hwnd) not in {int(h) for h in (own_hwnds or [])}:
            _target = int(fg_hwnd)
    except (TypeError, ValueError):
        pass


def get_foreground() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def target_hwnd() -> int:
    return _target


def focus_target(settle: float = 0.09) -> dict:
    """把焦点切到目标窗口并等待落定。返回 {target, switched, fg_before, fg_after}。"""
    info = {"target": _target, "switched": False, "fg_before": 0, "fg_after": 0}
    if sys.platform != "win32" or not _target:
        return info
    try:
        u = ctypes.windll.user32
        info["fg_before"] = int(u.GetForegroundWindow() or 0)
        if info["fg_before"] != _target:
            u.SetForegroundWindow(_target)
            time.sleep(settle)
            info["switched"] = True
        info["fg_after"] = int(u.GetForegroundWindow() or 0)
    except Exception as e:
        logger.warning("focus_target 失败: %s", e)
    return info
