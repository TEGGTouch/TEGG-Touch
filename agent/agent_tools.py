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
                           "voice_language='zh-CN')。要改字典型参数里的某一项 (如方向盘颜色), "
                           "用点路径: key='wheel_style.color', value='#FF8C00' —— 只改该项, "
                           "保留其它键。不要把整个字典塞进 value。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string",
                            "description": "参数名; 嵌套项用点路径, 如 'wheel_style.color'"},
                    "value": {"description": "新值 (字符串/数字/布尔; 颜色用 #RRGGBB)"},
                    "name": {"type": "string", "description": "方案名, 省略=当前活跃"},
                },
                "required": ["key", "value"],
            },
        },
        {
            "name": "reset_param",
            "description": "把某参数重置为出厂默认 (等价于设置面板里的「重置」按钮, 用同一份默认)。"
                           "支持点路径: key='wheel_style.color' 重置方向盘颜色回默认; "
                           "key='button_colors' 重置全部按钮配色; key='transparency' 等亦可。"
                           "用户说'重置X'/'恢复默认X'时用它, **不要自己猜默认值或用 set_param 填当前值**。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "要重置的参数, 支持点路径"},
                    "name": {"type": "string"},
                },
                "required": ["key"],
            },
        },
        # ── 语音命令 ──
        {
            "name": "add_voice_command",
            "description": "新增一条语音命令: 说出 phrase 时触发 keys。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string", "description": "触发短语, 如 '开火'"},
                    "keys": {"type": "string", "description": "按键 (标签语法), 如 'space' / 'ctrl+a'"},
                    "action": {"type": "string", "enum": ["click", "press", "release"]},
                    "name": {"type": "string"},
                },
                "required": ["phrase", "keys"],
            },
        },
        {
            "name": "remove_voice_command",
            "description": "按 index 删除一条语音命令 (index 见 summarize 的 voice_commands 顺序)。",
            "input_schema": {"type": "object",
                             "properties": {"index": {"type": "integer"}, "name": {"type": "string"}},
                             "required": ["index"]},
        },
        {
            "name": "set_voice_command",
            "description": "改某条语音命令的一个字段 (phrase/keys/action)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "field": {"type": "string", "enum": ["phrase", "keys", "action"]},
                    "value": {"description": "新值"},
                    "name": {"type": "string"},
                },
                "required": ["index", "field", "value"],
            },
        },
        # ── 轮盘扇区 (固定 8 个, 只改绑定) ──
        {
            "name": "set_wheel_sector",
            "description": "改某个轮盘扇区 (0~7) 的一个绑定/名字字段。扇区数量固定, 不能增删。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "扇区序号 0~7"},
                    "field": {"type": "string", "enum": _FIELD_LIST},
                    "value": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["index", "field", "value"],
            },
        },
        # ── 应用 ──
        {
            "name": "add_app",
            "description": "新增一个可启动应用 (名字 + 路径, 供 app:<名> 触发)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string"},
                    "path": {"type": "string", "description": ".lnk 或可执行文件绝对路径"},
                    "name": {"type": "string"},
                },
                "required": ["app_name", "path"],
            },
        },
        {
            "name": "remove_app",
            "description": "按 index 删除一个应用。",
            "input_schema": {"type": "object",
                             "properties": {"index": {"type": "integer"}, "name": {"type": "string"}},
                             "required": ["index"]},
        },
        # ── 宏 ──
        {
            "name": "add_macro",
            "description": "新建一个宏。steps 每步二选一: {type:'key', key:'a', action:'click'} "
                           "或 {type:'delay', ms:100}。pool 默认 xmacros (统一池, 推荐)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "macro_name": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "object"},
                              "description": "步骤数组, 见 description"},
                    "pool": {"type": "string", "enum": ["xmacros", "macros", "gp_macros"]},
                    "name": {"type": "string"},
                },
                "required": ["macro_name", "steps"],
            },
        },
        {
            "name": "remove_macro",
            "description": "按名字删除一个宏 (pool 默认 xmacros)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "macro_name": {"type": "string"},
                    "pool": {"type": "string", "enum": ["xmacros", "macros", "gp_macros"]},
                    "name": {"type": "string"},
                },
                "required": ["macro_name"],
            },
        },
        # ── 按钮增删 ──
        {
            "name": "add_button",
            "description": "新增一个按钮 (仅 normal/gp_button/center_band; 摇杆 gp_stick 与方向盘 "
                           "gp_wheel 数据复杂/单例, 请让用户在编辑界面加)。x/y 为屏幕中心原点坐标 "
                           "(x<0左 x>0右 y<0上 y>0下), 省略则放中心 (0,0), 用户可再拖。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "btn_type": {"type": "string", "enum": ["normal", "gp_button", "center_band"]},
                    "btn_name": {"type": "string"},
                    "x": {"type": "number"}, "y": {"type": "number"},
                    "w": {"type": "number"}, "h": {"type": "number"},
                    "name": {"type": "string"},
                },
                "required": ["btn_type"],
            },
        },
        {
            "name": "remove_button",
            "description": "按 index 删除一个按钮 (任意类型; index 同 summarize_profile 的按钮 index)。",
            "input_schema": {"type": "object",
                             "properties": {"index": {"type": "integer"}, "name": {"type": "string"}},
                             "required": ["index"]},
        },
        # ── 元素位置/尺寸 ──
        {
            "name": "move_button",
            "description": "把某元素按网格相对移动 (方向 上/下/左/右, cells 格数, 一格=grid_size)。"
                           "适用所有元素含方向盘 gp_wheel (它们都按各自 buttons.x/y 渲染)。"
                           "用户说'往上移一格''左移两格'时用它, 不用自己算坐标。"
                           "注意: 这不是中心轮盘整组偏移 (那是 wheel_x/wheel_y, 用 set_param)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "cells": {"type": "number", "description": "格数, 默认 1"},
                    "name": {"type": "string"},
                },
                "required": ["index", "direction"],
            },
        },
        {
            "name": "set_button_geometry",
            "description": "绝对设置某元素的位置/尺寸 (x/y 屏幕中心原点坐标: x<0左 x>0右 y<0上 y>0下; "
                           "w/h 尺寸; 任意子集)。含方向盘。要精确落位或改大小时用它。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "x": {"type": "number"}, "y": {"type": "number"},
                    "w": {"type": "number"}, "h": {"type": "number"},
                    "name": {"type": "string"},
                },
                "required": ["index"],
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
    "reset_param": lambda a: ConfigTools.reset_param(a["key"], a.get("name")),
    # 语音命令
    "add_voice_command": lambda a: ConfigTools.add_voice_command(
        a["phrase"], a["keys"], a.get("action", "click"), a.get("name")),
    "remove_voice_command": lambda a: ConfigTools.remove_voice_command(int(a["index"]), a.get("name")),
    "set_voice_command": lambda a: ConfigTools.set_voice_command(
        int(a["index"]), a["field"], a["value"], a.get("name")),
    # 轮盘扇区
    "set_wheel_sector": lambda a: ConfigTools.set_wheel_sector(
        int(a["index"]), a["field"], a["value"], a.get("name")),
    # 应用
    "add_app": lambda a: ConfigTools.add_app(a["app_name"], a["path"], a.get("name")),
    "remove_app": lambda a: ConfigTools.remove_app(int(a["index"]), a.get("name")),
    # 宏
    "add_macro": lambda a: ConfigTools.add_macro(
        a["macro_name"], a.get("steps", []), a.get("pool", "xmacros"), a.get("name")),
    "remove_macro": lambda a: ConfigTools.remove_macro(
        a["macro_name"], a.get("pool", "xmacros"), a.get("name")),
    # 按钮增删
    "add_button": lambda a: ConfigTools.add_button(
        a.get("btn_type", "normal"), a.get("btn_name"),
        a.get("x", 0), a.get("y", 0), a.get("w"), a.get("h"), a.get("name")),
    "remove_button": lambda a: ConfigTools.remove_button(int(a["index"]), a.get("name")),
    "move_button": lambda a: ConfigTools.move_button(
        int(a["index"]), a["direction"], a.get("cells", 1), a.get("name")),
    "set_button_geometry": lambda a: ConfigTools.set_button_geometry(
        int(a["index"]), a.get("x"), a.get("y"), a.get("w"), a.get("h"), a.get("name")),
}

# 会改动配置 → 需要热生效的工具 (新加的 list 编辑工具必须在此登记, 否则改完不热重载)
WRITE_TOOLS = {
    "set_button_binding", "set_param", "reset_param",
    "add_voice_command", "remove_voice_command", "set_voice_command",
    "set_wheel_sector", "add_app", "remove_app",
    "add_macro", "remove_macro", "add_button", "remove_button",
    "move_button", "set_button_geometry",
}


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

def _profile_index() -> str:
    """紧凑索引: 每元素一行 (index/类型/名字/方位/颜色) + 一行概览。
    详情 (完整字段/宏步骤/扇区绑定/语音内容) 让模型按需调 summarize_profile。
    这样 system 提示保持很小且静态 (可缓存), 不随 profile 膨胀。"""
    try:
        s = ConfigTools.summarize_profile()
    except Exception as e:
        return f"(读取方案失败: {e})"
    scr = s.get("screen", {}) or {}
    gs = (s.get("params", {}) or {}).get("grid_size") or 100
    lines = [f'方案「{s.get("profile", "")}」 屏幕 {scr.get("w")}x{scr.get("h")} '
             f'(坐标=像素, 原点=屏幕中心; 一格 grid_size={gs}px)',
             f'元素 (共 {s.get("button_count", 0)} 个, index 可直接用于改/删):']
    for e in s.get("buttons", []):
        col = (e.get("color") or {}).get("name", "")
        lines.append(f'  [{e["index"]}] {e.get("type_label", "")} '
                     f'{e.get("name") or "(无名)"} · {e.get("region", "")} · {col}')
    wheel = s.get("wheel", {}) or {}
    lines.append(
        f'语音命令 {len(s.get("voice_commands", []))} 条 | '
        f'轮盘 {wheel.get("sector_count", 0)} 扇区(颜色 {wheel.get("color")}) | '
        f'宏 x{len(s.get("xmacros", []))}/kb{len(s.get("macros", []))}/gp{len(s.get("gp_macros", []))} | '
        f'应用 {len(s.get("apps", []))} 个')
    return "\n".join(lines)


def system_prompt() -> str:
    """拼系统提示: 静态规则 + 标签语法 + 紧凑 profile 索引 (细节走工具按需拉取)。"""
    gp_labels = ", ".join(f"gp:{k}" for k in GP_LABEL_TO_KEY.values())
    index = _profile_index()

    return f"""你是「蛋挞 TEGGTouch」的配置助手。蛋挞是 Windows 无障碍辅助工具, 把鼠标/触屏操作映射成键盘/鼠标/手柄输入, 帮助手部不便的用户玩需要键鼠/手柄的游戏。

你的职责: 用工具帮用户读取和修改蛋挞的按键配置 (profile)。你**只能改配置**, 不能直接操作鼠标键盘 (那是后续阶段的能力)。

你能改 profile 里的几乎所有东西:
- 按钮: 改绑定/名字 (set_button_binding)、新增 (add_button, 仅普通键/手柄键/回中带)、删除 (remove_button)
- 移动/改尺寸元素: move_button (按格相对移动, 上/下/左/右)、set_button_geometry (绝对 x/y/w/h)。
  **所有元素都用这个** —— 包括方向盘 gp_wheel (它是 buttons 里的元素, 有自己的 x/y)。
  ⚠️ 别混淆: "方向盘"=gp_wheel 元素(move_button 按 index 移); "中心轮盘"整组(8扇区+中心环)
  的偏移才是 wheel_x/wheel_y(set_param)。用户说移动"方向盘"时用 move_button, 不是改 wheel_y。
- 顶层参数与配色 (set_param, 支持点路径如 wheel_style.color)
- **重置/恢复默认**: reset_param (等价面板「重置」按钮, 用出厂默认常量)。用户说"重置方向盘颜色"
  就 reset_param key='wheel_style.color', 别用 set_param 填当前值 (那不是重置)。
- 语音命令: 增 (add_voice_command) / 删 (remove_voice_command) / 改 (set_voice_command)
- 轮盘扇区绑定: set_wheel_sector (固定8个 0~7, 只改不增删)
- 宏: 增 (add_macro) / 删 (remove_macro); 应用: 增 (add_app) / 删 (remove_app)
摇杆(gp_stick)与方向盘(gp_wheel)的新增/删除较特殊, 新增请引导用户在编辑界面操作 (但它们的字段和方向盘颜色你能改)。

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

按空间/颜色/类型定位元素 (用户常这么说话):
- 下方速览每个元素带 index/类型/名字/方位/颜色; 用户说"左上那个""右下的摇杆"
  "左边第一个绿色回中带"时据此匹配 index。方位九宫格: 左上/正上/右上/正左/居中/正右/左下/正下/右下。
- 坐标系: 原点=屏幕中心, x<0 左 / x>0 右, y<0 上 / y>0 下 (y 越大越靠下)。
- "第几个/从左数第一个": 需要精确坐标时调 summarize_profile 看 pos, 按 x/y 排序。
- 描述能匹配多个元素时, 先列候选让用户确认, 不要乱猜。
- 改方向盘颜色 → set_param key='wheel_style.color' value='#RRGGBB';
  改手柄键/摇杆颜色 → set_param key='button_colors.gamepad' value='#RRGGBB'。

下面是当前方案的**速览索引** (只有 index/类型/名字/方位/颜色)。要看某元素的完整
字段与绑定、宏的步骤、扇区绑定、语音命令内容, 就调 summarize_profile; 要最原始的
完整配置 dict, 调 read_profile。不要凭速览猜细节字段。
{index}

注意: 只改速览里存在的 index; 拿不准细节先 summarize_profile。用中文回复用户。"""


def _json(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(obj)
