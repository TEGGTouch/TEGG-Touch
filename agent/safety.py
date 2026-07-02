"""
TEGGTouch 蛋挞 — Agent 执行安全 (阶段2 骨架)

真实输入不可逆, 故执行类动作要过安全闸:
- **急停 (abort)**: 全局标志, 任何线程可置位 (急停热键 / STOP 按钮)。执行前检查,
  置位则拒绝执行; 并唤醒任何等待中的确认。
- **确认 (confirm)**: 默认先确认再执行 (auto_execute=False); auto 模式直接放行。
  确认的阻塞/UI 交互由 AgentThread + 对话框实现 (需 Qt 主线程), 本模块只管急停标志。

本模块无 Qt 依赖, 纯 threading, 供任意线程共享。
"""

from __future__ import annotations

import threading

_abort = threading.Event()


def request_abort() -> None:
    """置位急停 (急停热键 / STOP 按钮调用)。"""
    _abort.set()


def clear_abort() -> None:
    """清除急停 (开始新一轮执行前调用)。"""
    _abort.clear()


def is_aborted() -> bool:
    return _abort.is_set()


# ── 待确认 broker: 让语音(RunController)与按钮(对话框)都能 resolve 同一次确认 ──
_pending_confirm = None   # callable(bool) | None
_pending_lock = threading.Lock()


def set_pending_confirm(resolver) -> None:
    """AgentThread 等待确认时挂上 resolver(bool)。"""
    global _pending_confirm
    with _pending_lock:
        _pending_confirm = resolver


def clear_pending_confirm() -> None:
    global _pending_confirm
    with _pending_lock:
        _pending_confirm = None


def confirm_pending() -> bool:
    return _pending_confirm is not None


def resolve_pending(ok: bool) -> bool:
    """有待确认则 resolve 并返回 True; 否则 False。"""
    global _pending_confirm
    with _pending_lock:
        fn = _pending_confirm
        _pending_confirm = None
    if fn:
        try:
            fn(bool(ok))
        except Exception:
            pass
        return True
    return False


# ── 语音确认词 (grammar 常驻 + 路由用; 仅"语音已开"时生效) ──
CONFIRM_YES_KEY = "__confirm_yes__"
CONFIRM_NO_KEY = "__confirm_no__"
# 与确认弹窗按钮文本一致: "确认" / "取消" ("确认"比"执行"更好识别)
_CONFIRM_PHRASES = [
    ("确认", True),
    ("取消", False),
]


def confirm_voice_commands() -> list:
    """返回确认/取消的语音命令 (合进 grammar; keys 为哨兵, 由 _on_voice_command 特判)。"""
    return [{"phrase": p, "keys": (CONFIRM_YES_KEY if yes else CONFIRM_NO_KEY),
             "action": "click"} for p, yes in _CONFIRM_PHRASES]
