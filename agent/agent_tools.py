"""
TEGGTouch 蛋挞 — Agent 工具定义与分派 (阶段1: 配置助手)

把 ConfigTools 暴露成 Anthropic `tools` schema, 并提供 dispatch() 把模型的
tool_use 调用路由到 ConfigTools 真正执行。模型据此程序化读写 profile 绑定/参数,
改完由 AgentThread 发信号让主线程热生效。

设计:
- 工具 schema 与 ConfigTools 一一对应; 字段白名单复用 tool_layer._BUTTON_BINDING_FIELDS。
- dispatch() 纯函数 (文件 IO + 标量), 可在子线程跑 (config_manager 原子写线程安全)。
- system_prompt() 把当前 profile 摘要 + 标签语法塞进上下文, 让模型"知道有哪些可改"。
- 阶段2 的控制 toolset (ControlTools) 预留 build_control_tools(), 暂不在配置助手里启用。
"""

from __future__ import annotations

import logging

from agent.tool_layer import ConfigTools, _BUTTON_WRITABLE_FIELDS
from core.constants import GP_LABEL_TO_KEY

logger = logging.getLogger(__name__)

_FIELD_LIST = sorted(_BUTTON_WRITABLE_FIELDS)


# ════════════════════════════════════════════════════════════════
# 工具 schema (Anthropic tools 格式) — 配置 toolset
# ════════════════════════════════════════════════════════════════

def build_config_tools() -> list:
    """返回配置助手可用的工具定义 (Anthropic tools 格式)。"""
    return [
        {
            "name": "list_profiles",
            "description": "列出所有方案名与当前活跃方案。",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "summarize_profile",
            "description": "查看某方案的精简摘要: 按钮绑定一览、轮盘/语音概况、宏与应用名。"
                           "不传 name 则用当前活跃方案。改任何东西前先用它了解现状。",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "方案名, 省略=当前活跃"}},
                "required": [],
            },
        },
        {
            "name": "read_profile",
            "description": "读取某方案的完整配置 dict (字段较多, 仅在 summarize 不够时用)。",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": [],
            },
        },
        {
            "name": "set_button_binding",
            "description": "修改某个按钮的一个字段并保存。button_index 是 summarize_profile "
                           "返回的按钮 index。field='name' 时改按钮显示名 (value 为任意文字); "
                           "其余字段是按键绑定, value 用蛋挞标签语法 (见系统提示)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "button_index": {"type": "integer", "description": "按钮索引 (从 0 起)"},
                    "field": {"type": "string", "enum": _FIELD_LIST,
                              "description": "要改的字段"},
                    "value": {"type": "string", "description": "新值 (标签语法, 如 'ctrl+f4' / 'mouse:left' / 'gp:A')"},
                    "name": {"type": "string", "description": "方案名, 省略=当前活跃"},
                },
                "required": ["button_index", "field", "value"],
            },
        },
        {
            "name": "set_param",
            "description": "修改方案顶层参数并保存 (如 transparency=0.5 / voice_enabled=true / "
                           "voice_language='zh-CN')。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "参数名"},
                    "value": {"description": "新值 (字符串/数字/布尔)"},
                    "name": {"type": "string", "description": "方案名, 省略=当前活跃"},
                },
                "required": ["key", "value"],
            },
        },
    ]


# 工具名 → ConfigTools 调用 (kwargs 透传)
_DISPATCH = {
    "list_profiles": lambda a: ConfigTools.list_profiles(),
    "summarize_profile": lambda a: ConfigTools.summarize_profile(a.get("name")),
    "read_profile": lambda a: ConfigTools.read_profile(a.get("name")),
    "set_button_binding": lambda a: ConfigTools.set_button_binding(
        int(a["button_index"]), a["field"], a["value"], a.get("name")),
    "set_param": lambda a: ConfigTools.set_param(a["key"], a["value"], a.get("name")),
}

# 会改动配置 → 需要热生效的工具
WRITE_TOOLS = {"set_button_binding", "set_param"}


def dispatch(tool_name: str, tool_input: dict) -> dict:
    """执行一个 tool_use 调用, 返回可序列化结果 dict。永不抛 (异常转 error dict)。"""
    fn = _DISPATCH.get(tool_name)
    if fn is None:
        return {"ok": False, "error": f"未知工具: {tool_name}"}
    try:
        result = fn(tool_input or {})
        return result if isinstance(result, dict) else {"ok": True, "result": result}
    except (KeyError, ValueError, TypeError) as e:
        return {"ok": False, "error": f"参数错误: {e}"}
    except Exception as e:
        logger.exception("工具 %s 执行失败", tool_name)
        return {"ok": False, "error": f"执行失败: {e}"}


# ════════════════════════════════════════════════════════════════
# 系统提示
# ════════════════════════════════════════════════════════════════

def system_prompt() -> str:
    """拼系统提示: 当前 profile 摘要 + 标签语法 + 行为约束。"""
    try:
        summary = ConfigTools.summarize_profile()
    except Exception as e:
        summary = {"error": f"读取摘要失败: {e}"}

    gp_labels = ", ".join(f"gp:{k}" for k in GP_LABEL_TO_KEY.values())

    return f"""你是「蛋挞 TEGGTouch」的配置助手。蛋挞是 Windows 无障碍辅助工具, 把鼠标/触屏操作映射成键盘/鼠标/手柄输入, 帮助手部不便的用户玩需要键鼠/手柄的游戏。

你的职责: 用工具帮用户读取和修改蛋挞的按键配置 (profile)。你**只能改配置**, 不能直接操作鼠标键盘 (那是后续阶段的能力)。

工作流程:
1. 改任何东西前, 先用 summarize_profile 了解当前有哪些按钮和绑定。
2. 用 set_button_binding / set_param 落实修改 (会立即保存并热生效)。
3. 改完用**人话**简短告诉用户你改了什么 (字段、旧值→新值)。

绑定值的「标签语法」(value 字段用):
- 普通键: w / ctrl / f4 / ctrl+f4 (多键用 + 连成组合键)
- 鼠标: mouse:left / mouse:right / mouse:middle / mouse:x1 / mouse:x2 / mouse:wheelup / mouse:wheeldown
- 手柄: {gp_labels}
- 宏: xmacro:<宏名> (统一宏池)
- 启动应用: app:<应用名>
- 光标回中: recenter:screen / recenter:wheel / recenter:center_ring / recenter:stick:<名>

按钮可改字段: {', '.join(_FIELD_LIST)}
(name=按钮显示名, hover=悬停触发键, lclick/rclick/mclick=左/右/中键, wheelup/wheeldown=滚轮, xbutton1/2=鼠标侧键, hover_delay/hover_release_delay=毫秒延迟, hover_mode=trigger|toggle)
改按钮名字就用 set_button_binding field='name'。摘要里每个按钮带 type 字段 (normal/gamepad 等), "第N个手柄键"指按顺序数第N个 type 为手柄类的按钮。

当前活跃方案摘要:
{_json(summary)}

注意: 只有摘要里存在的按钮 index 才能改。不确定就先 summarize_profile。用中文回复用户。"""


def _json(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(obj)
