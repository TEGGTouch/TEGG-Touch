"""
TEGGTouch 蛋挞 — AI 配置助手对话持久化 (JSONL)

把配置助手的每轮事件追加写到 logs/agent/history.jsonl, 一行一个事件:
两个用途 —
- 方便用户: 重开窗口 / 重启 App 后能在聊天窗看到过往记录 (load_recent 回渲)。
- 方便 debug: 完整记录模型收发的文本、工具调用入参+结果、错误、token 用量。

追加写 + 模块级锁, 任意线程可安全调用 (AgentThread 子线程写, 主线程开窗时读)。
不落密钥 (api_key 在 settings/agent.json, 不进消息)。跨重启不恢复模型上下文 ——
本文件只负责"记录与回看", 不做续聊 (见 docs/agent-integration-design.md 阶段1)。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime

from core.constants import APP_DIR

logger = logging.getLogger(__name__)

# logs/agent/history.jsonl (与 settings/ 同级, 归档在 APP_DIR 下)
LOG_DIR = os.path.join(APP_DIR, "logs", "agent")
LOG_PATH = os.path.join(LOG_DIR, "history.jsonl")

# 回看时最多读取的事件数 (读文件尾, 防历史过大拖慢开窗)
DEFAULT_TAIL = 200

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_event(event: dict) -> None:
    """追加一个事件 (自动补 ts)。永不抛 —— 日志失败不该拖垮对话。"""
    if not isinstance(event, dict):
        return
    ev = {"ts": _now_iso(), **event}
    line = json.dumps(ev, ensure_ascii=False)
    try:
        with _lock:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as e:
        logger.warning("对话日志写入失败: %s", e)


# ── 语义化包装 (调用方读起来清楚) ──────────────────────────────
def log_session_start(model: str | None = None) -> None:
    log_event({"type": "session", "model": model})


def log_user(text: str) -> None:
    log_event({"type": "user", "text": text})


def log_assistant(text: str) -> None:
    log_event({"type": "assistant", "text": text})


def log_tool(name: str, tool_input: dict, result: dict) -> None:
    log_event({"type": "tool", "name": name, "input": tool_input, "result": result})


def log_error(text: str) -> None:
    log_event({"type": "error", "text": text})


def log_meta(model: str | None, stop_reason: str | None, usage: dict | None) -> None:
    """调试用: 单次 chat 的模型/终止原因/token 用量 (不参与 UI 回渲)。"""
    log_event({"type": "meta", "model": model,
               "stop_reason": stop_reason, "usage": usage})


def load_recent(max_events: int = DEFAULT_TAIL) -> list:
    """读日志尾部若干事件, 供开窗回渲。文件不存在 / 损坏行 → 尽力而为跳过。"""
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with _lock:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
    except OSError as e:
        logger.warning("对话日志读取失败: %s", e)
        return []

    events = []
    for line in lines[-max_events:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 半截行 (崩溃时写到一半) 直接跳过
    return events
