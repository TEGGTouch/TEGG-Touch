"""
TEGGTouch 蛋挞 — AI Agent 全局设置 (密钥 / 模型 / 行为)

存于 settings/agent.json (与 hotkeys.json 同目录), 用 config_manager._atomic_write_json
原子写, 避免崩溃留 0 字节。**不写入 profile** —— 密钥是账号级、与具体方案无关,
且 profile 会被导出/分享, 密钥不应随之外泄。

读取优先级 (api_key): 环境变量 MINIMAX_API_KEY > settings/agent.json。
这样 CI / 高级用户可用环境变量, 普通用户在设置里填一次即可。

字段 (见 DEFAULT_AGENT_SETTINGS):
- api_key             : MiniMax 密钥 (国内站 platform.minimaxi.com 申请; 密钥不跨区)
- base_url            : Anthropic 兼容端点; 默认国内站
- model               : 默认 MiniMax-M3 (唯一支持图片输入的型号)
- use_openai_fallback : /anthropic tool_use 垫片抖动时, 预留切 OpenAI 兼容 /v1 (阶段标记)
- auto_execute        : 控制类动作是否免确认直接执行 (阶段2 用; 默认 False = 先确认)
- screenshot_enabled  : 是否允许截屏喂给多模态 (阶段2 用; 默认 False, 决策#5 知情透明)
- asr_backend         : 自由语音转写后端 (功能②; 默认 'whisper', 可插拔)
- max_tokens          : 单次回复上限
- temperature         : 采样温度 (MiniMax 合法区间 [0, 2])
"""

from __future__ import annotations

import copy
import json
import logging
import os

from core.constants import APP_DIR
from core.config_manager import _atomic_write_json

logger = logging.getLogger(__name__)

# settings/agent.json (与 HOTKEYS_FILE 同目录)
AGENT_SETTINGS_FILE = os.path.join(APP_DIR, "settings", "agent.json")

# api_key 环境变量覆盖名 (与 MiniMax 文档/SDK 习惯一致)
ENV_API_KEY = "MINIMAX_API_KEY"
# 自由听写 ASR 密钥环境变量 (SiliconFlow 硅基流动)
ENV_ASR_KEY = "SILICONFLOW_API_KEY"

# 国内站 Anthropic 兼容端点 (密钥不跨区; 海外站为 https://api.minimax.io/anthropic)
DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic"
DEFAULT_MODEL = "MiniMax-M3"

DEFAULT_AGENT_SETTINGS = {
    "api_key": "",
    "base_url": DEFAULT_BASE_URL,
    "model": DEFAULT_MODEL,
    "use_openai_fallback": False,
    "auto_execute": False,
    "screenshot_enabled": True,   # 允许 agent 截屏看画面 (每次都会在面板告知; 可关)
    "asr_backend": "siliconflow",
    # 自由听写 (对 AI 助手说话): SiliconFlow SenseVoice, 唤醒词「蛋挞」→ 录音 → 转文字 → 发 agent
    "asr_api_key": "",                                   # SiliconFlow 密钥 (环境变量 SILICONFLOW_API_KEY 优先)
    "asr_base_url": "https://api.siliconflow.cn/v1",
    "asr_model": "FunAudioLLM/SenseVoiceSmall",
    "voice_wake_enabled": True,                          # 是否常驻监听唤醒词 (类似 Hey Siri, 可关)
    "wake_word": "蛋挞",
    "max_tokens": 1024,
    "temperature": 1.0,
    # AI 助手对话框的用户拖动位置/尺寸 (None=首次居中); 全局, 与 profile 无关
    "dialog_x": None,
    "dialog_y": None,
    "dialog_w": None,
    "dialog_h": None,
    "dialog_open": False,    # 上次退出时面板是否处于打开状态 → 启动时恢复
}


def load_agent_settings() -> dict:
    """加载 AI 设置; 不存在/损坏则返回默认值的拷贝。

    返回的 api_key 已应用环境变量覆盖 (环境变量优先)。
    """
    result = copy.deepcopy(DEFAULT_AGENT_SETTINGS)
    if os.path.exists(AGENT_SETTINGS_FILE):
        try:
            with open(AGENT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in result:
                    if k in data and data[k] is not None:
                        result[k] = data[k]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("读取 agent.json 失败, 用默认值: %s", e)

    # 环境变量覆盖 api_key (优先级最高)
    env_key = os.environ.get(ENV_API_KEY)
    if env_key:
        result["api_key"] = env_key.strip()
    # 同理 ASR 密钥 (SiliconFlow)
    env_asr = os.environ.get(ENV_ASR_KEY)
    if env_asr:
        result["asr_api_key"] = env_asr.strip()

    # temperature 夹到 MiniMax 合法区间 [0, 2]
    try:
        result["temperature"] = max(0.0, min(2.0, float(result["temperature"])))
    except (TypeError, ValueError):
        result["temperature"] = DEFAULT_AGENT_SETTINGS["temperature"]

    return result


def save_agent_settings(settings: dict) -> bool:
    """保存 AI 设置 (合并写, 保留未知字段)。环境变量提供的 api_key 不会被写回文件。"""
    try:
        existing = {}
        if os.path.exists(AGENT_SETTINGS_FILE):
            try:
                with open(AGENT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, dict):
                    existing = {}
            except (json.JSONDecodeError, OSError):
                existing = {}

        merged = {**existing, **(settings or {})}
        # 若 api_key 来自环境变量, 不要把它落盘 (避免明文写入文件)
        if os.environ.get(ENV_API_KEY) and "api_key" in (settings or {}):
            # 仅当调用方显式传了与环境变量相同的值时才剔除; 用户真改了就尊重
            if settings.get("api_key") == os.environ.get(ENV_API_KEY, "").strip():
                merged.pop("api_key", None)

        _atomic_write_json(AGENT_SETTINGS_FILE, merged)
        return True
    except Exception as e:
        logger.error("保存 agent.json 失败: %s", e)
        return False


def is_configured() -> bool:
    """是否已配置可用密钥 (环境变量或文件)。"""
    return bool(load_agent_settings().get("api_key"))


def load_ui_geometry() -> dict:
    """AI 助手对话框上次的位置/尺寸 (值可能为 None = 未保存过)。"""
    s = load_agent_settings()
    return {k: s.get(k) for k in ("dialog_x", "dialog_y", "dialog_w", "dialog_h")}


def save_ui_geometry(x: int, y: int, w: int, h: int) -> bool:
    """保存 AI 助手对话框几何 (合并写, 不动密钥等其它字段)。"""
    return save_agent_settings({
        "dialog_x": int(x), "dialog_y": int(y),
        "dialog_w": int(w), "dialog_h": int(h),
    })


def save_ui_open(is_open: bool) -> bool:
    """记住面板开/关状态 (启动时据此恢复)。"""
    return save_agent_settings({"dialog_open": bool(is_open)})
