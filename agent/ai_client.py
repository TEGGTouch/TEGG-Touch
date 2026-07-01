"""
TEGGTouch 蛋挞 — MiniMax AI 客户端 (Anthropic 兼容)

封装 `anthropic` SDK, 指向 MiniMax 国内站的 Anthropic 兼容端点。
MiniMax-M3 是唯一支持图片输入的型号, 故默认用它 (多模态阶段直接复用)。

关键事实 (见 docs/agent-integration-design.md / 研究):
- 端点 POST {base_url}/v1/messages, 头 x-api-key (SDK 自动) + anthropic-version。
- 忽略参数: top_k / stop_sequences / mcp_servers 等; temperature ∈ [0,2]。
- tool_use 支持 (含并行), 但 /anthropic 垫片对 stringified 参数偶有解析抖动,
  故 extract_tool_calls() 对 input 做 JSON 兜底。
- 图片 block: {"type":"image","source":{"type":"base64","media_type":...,"data":<裸base64>}}
  (阶段2 截屏用; 这里先提供静态构造器)。

本模块无 Qt 依赖, 可被 AgentThread 子线程直接使用。
"""

from __future__ import annotations

import base64
import json
import logging

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """带用户友好 msg 的客户端异常 (鉴权/网络/缺依赖)。"""


class MiniMaxClient:
    """MiniMax-M3 客户端 (Anthropic 兼容)。线程内构造, 不跨线程共享。"""

    def __init__(self, api_key: str, base_url: str, model: str,
                 max_tokens: int = 1024, temperature: float = 1.0):
        if not api_key:
            raise AIClientError("未配置 API 密钥 (在 AI 助手设置里填写, 或设置环境变量 MINIMAX_API_KEY)")
        try:
            import anthropic  # 延迟导入: 缺依赖时给清晰提示而非启动崩溃
        except ImportError as e:
            raise AIClientError("缺少 anthropic 库, 请运行: pip install anthropic") from e

        self._anthropic = anthropic
        self._model = model
        self._max_tokens = int(max_tokens)
        self._temperature = max(0.0, min(2.0, float(temperature)))
        try:
            self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        except Exception as e:
            raise AIClientError(f"初始化 AI 客户端失败: {e}") from e

    # ── 对话 ────────────────────────────────────────────────────
    def chat(self, messages: list, tools: list | None = None,
             system: str | None = None) -> dict:
        """调一次 messages.create, 返回归一化结果。

        Args:
            messages: Anthropic 格式消息列表 (role + content)
            tools:    工具定义列表 (None = 不带工具)
            system:   系统提示

        Returns:
            {
              "stop_reason": str,
              "content_blocks": [<原始 block, 用于回填 assistant 轮>],
              "tool_uses": [{"id","name","input"}...],   # input 已健壮解析为 dict
              "text": str,                                # 合并所有 text block
            }

        Raises:
            AIClientError: 鉴权 / 网络 / 限流 / 其他, msg 已本地化为友好文案。
        """
        kwargs = dict(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=messages,
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            resp = self._client.messages.create(**kwargs)
        except self._anthropic.AuthenticationError as e:
            raise AIClientError("密钥无效或无权限 (检查密钥是否为国内站 minimaxi.com 申请)") from e
        except self._anthropic.RateLimitError as e:
            raise AIClientError("触发限流, 请稍后再试") from e
        except self._anthropic.APIConnectionError as e:
            raise AIClientError("网络连接失败, 请检查网络") from e
        except self._anthropic.APIStatusError as e:
            raise AIClientError(f"服务返回错误 ({getattr(e, 'status_code', '?')}): {e}") from e
        except Exception as e:
            raise AIClientError(f"调用失败: {e}") from e

        return self._normalize(resp)

    def _normalize(self, resp) -> dict:
        """把 SDK 响应对象归一化为纯 dict + 健壮解析 tool_use。"""
        blocks = getattr(resp, "content", []) or []
        tool_uses = []
        texts = []
        for b in blocks:
            btype = getattr(b, "type", None)
            if btype == "text":
                texts.append(getattr(b, "text", "") or "")
            elif btype == "tool_use":
                tool_uses.append({
                    "id": getattr(b, "id", ""),
                    "name": getattr(b, "name", ""),
                    "input": self._coerce_tool_input(getattr(b, "input", {})),
                })
        return {
            "stop_reason": getattr(resp, "stop_reason", None),
            "content_blocks": blocks,
            "tool_uses": tool_uses,
            "text": "\n".join(t for t in texts if t).strip(),
        }

    @staticmethod
    def _coerce_tool_input(raw) -> dict:
        """tool_use.input 健壮解析: 垫片偶尔回 stringified JSON, 这里兜底成 dict。"""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {"_raw": raw}
            except json.JSONDecodeError:
                logger.warning("tool_use.input 非合法 JSON, 原样保留: %r", raw[:200])
                return {"_raw": raw}
        return {}

    # ── 多模态 (阶段2 截屏) ──────────────────────────────────────
    @staticmethod
    def image_block(image_bytes: bytes, media_type: str = "image/png") -> dict:
        """构造 Anthropic 图片 content block (裸 base64, 无 data: 前缀)。

        M3 限制: 单图 ≤10MB。调用方负责压缩到限制内。
        """
        data = base64.b64encode(image_bytes).decode("ascii")
        return {"type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data}}

    # ── 语音转写 (功能②, 可插拔 ASR) ─────────────────────────────
    def transcribe(self, audio_bytes: bytes, **kwargs) -> str:
        """自由语音转写。MiniMax 无可信官方 ASR, 故转调可插拔 ASR 后端 (待实现)。"""
        raise AIClientError("ASR 后端尚未接入 (计划用可插拔 Whisper, 见路线图功能②)")
