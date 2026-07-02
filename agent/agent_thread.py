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
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from agent import agent_tools
from agent import conversation_log as clog
from agent import safety
from agent.ai_client import MiniMaxClient, AIClientError
from agent.tool_layer import ControlTools
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
    confirm_requested = pyqtSignal(str)     # 预演文本 → 主线程弹确认条 (执行/取消)
    execute_requested = pyqtSignal(str, str)  # (value, action) → 主线程用 RunController 真执行

    def __init__(self, parent=None):
        super().__init__(parent)
        # 多轮对话历史 (Anthropic messages 格式); 跨 ask() 保留, 形成连续会话
        self._history: list = []
        self._pending_text: str = ""
        self._session_logged = False   # 首条消息才打会话分隔 (避免空会话刷屏)
        # 执行确认: 子线程 emit confirm_requested 后阻塞等主线程 resolve_confirm
        self._confirm_event = threading.Event()
        self._confirm_result = False
        # 真执行: 子线程 emit execute_requested 后阻塞等主线程 resolve_execute
        self._exec_event = threading.Event()
        self._exec_res = {}

    # ── 执行确认 (主线程点击"执行/取消"时调) ──
    def resolve_confirm(self, ok: bool):
        self._confirm_result = bool(ok)
        self._confirm_event.set()

    # ── 真执行回填 (主线程 RunController 执行完调) ──
    def resolve_execute(self, res: dict):
        self._exec_res = res or {}
        self._exec_event.set()

    def _trigger_on_main(self, value: str, action: str) -> dict:
        """子线程: 请求主线程用 RunController._smart_trigger 执行一个标签, 阻塞等结果。"""
        self._exec_res = {}
        self._exec_event.clear()
        self.execute_requested.emit(value, action)
        if not self._exec_event.wait(timeout=15):
            return {"ok": False, "error": "执行超时"}
        return self._exec_res

    def _await_confirm(self, preview: str) -> bool:
        """子线程: 请求确认并阻塞, 直到 resolve 或超时(视为取消)。
        确认 UI/语音登记/切模式/关弹窗 由主窗口(OverlayWindow)在 confirm_requested 槽里统一收口。"""
        self._confirm_result = False
        self._confirm_event.clear()
        self.confirm_requested.emit(preview)
        if not self._confirm_event.wait(timeout=120):
            return False
        return self._confirm_result

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
        if not self._session_logged:      # 真正开聊才打会话分隔
            clog.log_session_start()
            self._session_logged = True
        self.start()

    def _exec_action(self, name: str, inp: dict) -> dict:
        """执行类工具的安全闸: 预演 → (确认/auto) → 真执行; 全程可急停。
        name = run_action(单个标签) | run_sequence(一串步骤, 只弹一次确认)。"""
        inp = inp or {}
        target = (inp.get("target") or "").strip()

        # 组装"预演回调 + 真跑回调 + 确认文案", 两种工具共用后面的闸门逻辑
        if name == "run_sequence":
            steps = inp.get("steps") or []
            if not steps:
                return {"ok": False, "error": "steps 为空"}
            summary = (inp.get("summary") or "").strip() or f"{len(steps)} 步操作"
            desc = f"对【{target}】{summary}" if target else summary
            preview = lambda: ControlTools.run_sequence(steps, dry_run=True)
            realrun = lambda: ControlTools.run_sequence(steps, dry_run=False)
            label = summary
        else:  # run_action
            value = (inp.get("value") or "").strip()
            action = inp.get("action", "click")
            if not value:
                return {"ok": False, "error": "value 为空"}
            desc = f"对【{target}】执行 {value}" if target else f"执行 {value}"
            preview = lambda: ControlTools.run_keys(value, action, dry_run=True)
            realrun = lambda: ControlTools.run_keys(value, action, dry_run=False)
            label = value

        if safety.is_aborted():
            return {"ok": False, "error": "已急停, 未执行"}
        preview()   # 预演 (校验 + 不发输入)
        if agent_settings.load_agent_settings().get("auto_execute"):
            decided = True
        else:
            decided = self._await_confirm(desc)
        if not decided:
            return {"ok": False, "cancelled": True, "value": label, "note": "用户取消, 未执行"}
        if safety.is_aborted():
            return {"ok": False, "error": "已急停, 未执行"}

        # 真执行: 走主线程 RunController._smart_trigger (权威执行器: 进运行态 + 焦点校正 +
        # recenter 用真实几何)。延迟在本子线程 sleep, 每个触发 marshal 到主线程。
        import time
        results = []
        if name == "run_sequence":
            for st in (inp.get("steps") or []):
                if safety.is_aborted():
                    break
                if "delay_ms" in st:
                    time.sleep(min(5.0, max(0, int(st.get("delay_ms", 0))) / 1000.0))
                    continue
                v = (st.get("keys") or st.get("value") or "").strip()
                if not v:
                    continue
                results.append(self._trigger_on_main(v, st.get("action", "click")))
                if st.get("after_ms"):
                    time.sleep(min(5.0, max(0, int(st.get("after_ms", 0))) / 1000.0))
        else:
            results.append(self._trigger_on_main(value, action))

        ok = bool(results) and all(r.get("ok", False) for r in results)
        note = None
        if any(r.get("no_target") for r in results):
            note = "⚠ 没有目标窗口(先点一下游戏/目标程序), 输入可能发到别处"
        return {"ok": ok, "executed": True, "value": label,
                "steps": results, "error": (None if ok else "部分步骤失败"), "note": note}

    def run(self):
        self.busy.emit(True)
        safety.clear_abort()   # 每轮开始清急停标志
        try:
            self._run_conversation()
        except AIClientError as e:
            clog.log_error(str(e))
            self.error.emit(str(e))
        except Exception as e:
            logger.exception("AgentThread 未预期异常")
            clog.log_error(f"出错了: {e}")
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
        clog.log_user(self._pending_text)

        config_dirty = False
        for _ in range(MAX_TOOL_ROUNDS):
            result = client.chat(self._history, tools=tools, system=system)
            clog.log_meta(cfg["model"], result.get("stop_reason"), result.get("usage"))
            # 回填 assistant 轮 (含 tool_use blocks), 供下一轮上下文连贯
            self._history.append({"role": "assistant", "content": result["content_blocks"]})

            if result["stop_reason"] != "tool_use" or not result["tool_uses"]:
                # 终态: 给最终文本
                text = result["text"] or "(完成)"
                if config_dirty:
                    self.config_changed.emit()
                clog.log_assistant(text)
                self.reply_ready.emit(text)
                return

            # 执行所有 tool_use, 回填 tool_result
            tool_results = []
            for tu in result["tool_uses"]:
                # 执行类 (run_action): 走安全闸 (预演/确认/急停), 不走通用 dispatch
                if tu["name"] in agent_tools.EXEC_TOOLS:
                    out = self._exec_action(tu["name"], tu["input"])
                    clog.log_tool(tu["name"], tu["input"], out)
                    self.tool_ran.emit({"name": tu["name"], "input": tu["input"], "result": out})
                    tool_results.append({"type": "tool_result", "tool_use_id": tu["id"],
                                         "content": agent_tools._json(out)})
                    continue

                out = agent_tools.dispatch(tu["name"], tu["input"])
                is_image = tu["name"] in agent_tools.IMAGE_TOOLS and out.get("ok")

                # 图像类结果里的 base64 太大: 日志/信号只留摘要, 不带 data
                slim = out
                if is_image:
                    slim = {"ok": True, "w": out.get("w"), "h": out.get("h"),
                            "bytes": out.get("bytes"), "screenshot": True}
                clog.log_tool(tu["name"], tu["input"], slim)
                self.tool_ran.emit({"name": tu["name"], "input": tu["input"], "result": slim})
                if tu["name"] in agent_tools.WRITE_TOOLS and out.get("ok"):
                    config_dirty = True

                if is_image:
                    # 截图: tool_result 内容为图像 block (MiniMax-M3 可读)
                    content = [
                        {"type": "image",
                         "source": {"type": "base64",
                                    "media_type": out.get("media_type", "image/jpeg"),
                                    "data": out["data"]}},
                        {"type": "text",
                         "text": f"屏幕截图 {out.get('w')}x{out.get('h')} (已排除蛋挞覆盖层)"},
                    ]
                else:
                    content = agent_tools._json(out)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": content,
                })
            self._history.append({"role": "user", "content": tool_results})

        # 轮次用尽
        if config_dirty:
            self.config_changed.emit()
        msg = f"工具调用超过 {MAX_TOOL_ROUNDS} 轮上限, 已停止。"
        clog.log_error(msg)
        self.error.emit(msg)
