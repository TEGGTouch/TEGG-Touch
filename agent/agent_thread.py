"""
TEGGTouch 蛋挞 — Agent 运行时 (阶段1: 配置助手)

后台线程跑云端 agentic tool_use 循环, 信号回主线程驱动 UI 与热生效。
范式照 core/update_checker.py: 阻塞 IO 在 run() 里, 结果用 pyqtSignal 抛回主线程
(自动 QueuedConnection)。

线程规则 (docs/agent-integration-design.md 第5节):
- 本线程内调 ConfigTools (文件 IO, 原子写线程安全) + 云端 HTTP, 都 OK。
- **绝不**在本线程直调 reload_active_profile() (动 scene/UI) —— 改完发 config_changed 信号,
  主线程槽里调。

一轮对话 = 一次 start():
  user_text → [chat → 若 tool_use: 执行工具 + 回填 tool_result → 再 chat] 循环
  → 直到模型给最终文本 (reply_ready) 或达到轮次上限。
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from agent import agent_tools
from agent.ai_client import MiniMaxClient, AIClientError
from core import agent_settings

logger = logging.getLogger(__name__)

# 单轮对话内最多 tool_use 往返次数 (防模型陷入工具循环)
MAX_TOOL_ROUNDS = 8


class AgentThread(QThread):
    """配置助手对话线程。一次 ask() → 一次 start() → 跑完发 reply_ready。

    Signals:
        reply_ready(str)   最终助手文本
        tool_ran(dict)     每执行一个工具发一次 (含 name/input/result, result 带 before/after)
        config_changed()   本轮有写配置, 主线程应 reload_active_profile()
        error(str)         友好错误文案
        busy(bool)         True=开始处理, False=结束 (UI 据此禁/启输入)
    """

    reply_ready = pyqtSignal(str)
    tool_ran = pyqtSignal(dict)
    config_changed = pyqtSignal()
    error = pyqtSignal(str)
    busy = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 多轮对话历史 (Anthropic messages 格式); 跨 ask() 保留, 形成连续会话
        self._history: list = []
        self._pending_text: str = ""

    def reset_history(self):
        """清空会话历史 (新开一段对话)。"""
        self._history = []

    def ask(self, user_text: str):
        """提交一条用户消息并启动处理。线程忙时忽略 (UI 已禁用输入兜底)。"""
        if self.isRunning():
            logger.warning("AgentThread 忙, 忽略新请求")
            return
        self._pending_text = (user_text or "").strip()
        if not self._pending_text:
            return
        self.start()

    def run(self):
        self.busy.emit(True)
        try:
            self._run_conversation()
        except AIClientError as e:
            self.error.emit(str(e))
        except Exception as e:
            logger.exception("AgentThread 未预期异常")
            self.error.emit(f"出错了: {e}")
        finally:
            self.busy.emit(False)

    def _run_conversation(self):
        cfg = agent_settings.load_agent_settings()
        client = MiniMaxClient(
            api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"],
            max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
        )
        tools = agent_tools.build_config_tools()
        system = agent_tools.system_prompt()

        # 追加本轮用户消息
        self._history.append({"role": "user", "content": self._pending_text})

        config_dirty = False
        for _ in range(MAX_TOOL_ROUNDS):
            result = client.chat(self._history, tools=tools, system=system)
            # 回填 assistant 轮 (含 tool_use blocks), 供下一轮上下文连贯
            self._history.append({"role": "assistant", "content": result["content_blocks"]})

            if result["stop_reason"] != "tool_use" or not result["tool_uses"]:
                # 终态: 给最终文本
                text = result["text"] or "(完成)"
                if config_dirty:
                    self.config_changed.emit()
                self.reply_ready.emit(text)
                return

            # 执行所有 tool_use, 回填 tool_result
            tool_results = []
            for tu in result["tool_uses"]:
                out = agent_tools.dispatch(tu["name"], tu["input"])
                self.tool_ran.emit({"name": tu["name"], "input": tu["input"], "result": out})
                if tu["name"] in agent_tools.WRITE_TOOLS and out.get("ok"):
                    config_dirty = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": agent_tools._json(out),
                })
            self._history.append({"role": "user", "content": tool_results})

        # 轮次用尽
        if config_dirty:
            self.config_changed.emit()
        self.error.emit(f"工具调用超过 {MAX_TOOL_ROUNDS} 轮上限, 已停止。")
