"""
TEGGTouch 蛋挞 — 自由听写 ASR 客户端 (对 AI 助手说话)

复用 rockeTEGG 的 SiliconFlow(硅基流动) ASR 服务:
  OpenAI 兼容端点 POST {base}/audio/transcriptions, 模型 FunAudioLLM/SenseVoiceSmall
  (极快、中文准、便宜; 对话延迟本就秒级, 完全够用)。

用于唤醒词「蛋挞」后录下的一段自由语音 → 文字 → 灌进 AI 助手对话。
无 Qt 依赖, 可在子线程调。密钥由调用方从 agent_settings 取传入 (不在此写死)。
"""

from __future__ import annotations

import io
import logging
import re
import wave

logger = logging.getLogger(__name__)

# SenseVoice 输出里夹的特殊标签 <|zh|><|EMO_UNKNOWN|> 等, 转写后要清掉
_SENSEVOICE_TAG = re.compile(r"<\|[^|]*\|>")

DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"


class ASRError(Exception):
    """带友好文案的 ASR 异常 (鉴权/网络/服务错误)。"""


def clean_text(text: str) -> str:
    """清掉 SenseVoice 特殊标签, 去首尾空白。"""
    return _SENSEVOICE_TAG.sub("", text or "").strip()


def pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """int16 单声道 PCM → WAV 容器字节 (SiliconFlow 收标准音频文件)。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)      # int16 = 2 字节
        w.setframerate(int(sample_rate))
        w.writeframes(pcm_bytes)
    return buf.getvalue()


def transcribe_wav(wav_bytes: bytes, *, api_key: str,
                   base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL,
                   timeout: float = 30.0) -> str:
    """把一段 WAV 音频转成文字。失败抛 ASRError。返回已清标签的纯文本 (可能为空串)。"""
    if not api_key:
        raise ASRError("未配置 SiliconFlow 密钥 (在 AI 设置里填, 或设环境变量 SILICONFLOW_API_KEY)")
    try:
        import requests
    except ImportError as e:
        raise ASRError("缺少 requests 库") from e

    url = base_url.rstrip("/") + "/audio/transcriptions"
    files = {"file": ("speech.wav", io.BytesIO(wav_bytes), "audio/wav")}
    data = {"model": model, "response_format": "json"}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.post(url, files=files, data=data, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise ASRError(f"语音识别网络失败: {e}") from e

    if resp.status_code == 401:
        raise ASRError("SiliconFlow 密钥无效")
    if resp.status_code != 200:
        raise ASRError(f"语音识别服务错误 ({resp.status_code}): {resp.text[:200]}")
    try:
        text = resp.json().get("text", "")
    except ValueError as e:
        raise ASRError("语音识别返回非 JSON") from e
    return clean_text(text)


def transcribe_pcm16(pcm_bytes: bytes, sample_rate: int = 16000, **kwargs) -> str:
    """int16 PCM → 包 WAV → 转写 (录音直出 PCM 时用这个)。kwargs 透传给 transcribe_wav。"""
    return transcribe_wav(pcm16_to_wav(pcm_bytes, sample_rate), **kwargs)
