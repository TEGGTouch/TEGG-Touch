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
            "description": "新增一个元素 (normal 普通键 / gp_button 手柄键 / center_band 回中带 / "
                           "gp_stick 摇杆 / gp_wheel 方向盘)。方向盘是单例, 已存在则直接返回它 "
                           "(等于'已启用')。用户说'启用/添加方向盘(摇杆)'就用它, 不要让用户手动加。"
                           "加摇杆时: 用户要'右摇杆'就传 stick_id='R', '左摇杆'传 'L'。"
                           "x/y 屏幕中心原点坐标 (x<0左 x>0右 y<0上 y>0下), 省略放中心 (0,0)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "btn_type": {"type": "string",
                                 "enum": ["normal", "gp_button", "center_band",
                                          "gp_stick", "gp_wheel"]},
                    "btn_name": {"type": "string"},
                    "stick_id": {"type": "string", "enum": ["L", "R"],
                                 "description": "仅 gp_stick: L=左摇杆 R=右摇杆"},
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
        {
            "name": "set_element_field",
            "description": "改某元素的任意字段, 用于类型专有/高级字段: 摇杆 stick_id(L=左/R=右)/"
                           "dead_zone(死区)/eight_way(八向吸附)/mode(analog|wasd)/wasd_up..、"
                           "方向盘 control_mode/lt_*/rt_*、按钮 hover_repeat_interval(长按连发) 等。"
                           "**这些字段都能直接改, 不要说'改不了'** —— 值按旧值类型自动纠正。"
                           "常规绑定 (hover/lclick/name) 优先 set_button_binding; 位置/尺寸用几何工具。"
                           "改前可先 summarize_profile 看该元素 fields 里现有字段名与当前值作参考。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "field": {"type": "string", "description": "字段名 (见 summarize 的 fields)"},
                    "value": {"description": "新值"},
                    "name": {"type": "string"},
                },
                "required": ["index", "field", "value"],
            },
        },
        # ── 执行 (阶段2: 触发已配置的按键/宏/应用) ──
        {
            "name": "run_action",
            "description": "**真的发出**一次输入 (帮用户执行, 非改配置)。value 用蛋挞标签语法: "
                           "普通键 'ctrl+f4' / 鼠标 'mouse:left' / 手柄 'gp:A' / 宏 'xmacro:名' / "
                           "启动应用 'app:名'。用户说'帮我按攻击''放个技能''打开录屏'时: 先 summarize_profile "
                           "找到对应绑定的 value, 再用它调本工具。默认会先让用户确认才真执行 (auto 模式除外)。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "description": "要执行的标签, 如 'ctrl+f4' / 'gp:A' / 'xmacro:连招'"},
                    "action": {"type": "string", "enum": ["click", "press", "release"],
                               "description": "click=按一下(默认) / press=按住 / release=松开"},
                    "target": {"type": "string",
                               "description": "被操作对象的名字(如按钮名'茶叶蛋'/'手柄键01'), 用于给用户看的确认文案; 知道就填"},
                },
                "required": ["value"],
            },
        },
        {
            "name": "run_sequence",
            "description": "**真的连续发出**一串输入, 只弹一次确认 (用于'连按N次''一连串操作')。"
                           "重复N次或多步操作**必须用这个**, 不要 run_action 调 N 次(那样弹 N 次确认)。"
                           "steps 每步二选一: {keys:'a', action:'click', after_ms:50} 或 {delay_ms:100}。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "steps": {"type": "array", "items": {"type": "object"},
                              "description": "步骤数组, 如按a十次: [{keys:'a',after_ms:50}]×10"},
                    "target": {"type": "string", "description": "被操作对象名字(确认文案用)"},
                    "summary": {"type": "string", "description": "一句话概括这串操作(如'连按A键10次'), 确认文案用"},
                },
                "required": ["steps"],
            },
        },
        # ── 多模态感知 ──
        {
            "name": "capture_screen",
            "description": "截取当前屏幕并返回图像给你看 (截图**不含**蛋挞自己的覆盖层/工具栏/本面板)。"
                           "当用户让你看屏幕、或你需要看到画面才能判断/操作时调用。每次截屏都会在面板"
                           "告知用户。返回的是图片, 直接看图回答即可。",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ]


# ════════════════════════════════════════════════════════════════
# 控制 toolset (L3 坐标操作电脑) — computer use
# 坐标一律归一化 0-1000 (x 左0右1000 / y 上0下1000), 由 M3 视觉 grounding 给出,
# 上层(AgentThread)按最近一次截图的真实尺寸换算成像素再执行。
# 这些是 EXEC_TOOLS: 走安全闸(预演→分档确认→执行), 不走通用 dispatch。
# ════════════════════════════════════════════════════════════════

def build_control_tools() -> list:
    """返回操作电脑的控制工具 (Anthropic tools 格式)。坐标 0-1000。"""
    _xy = {
        "x": {"type": "integer", "description": "目标中心横坐标, 归一化 0-1000 (左0右1000)"},
        "y": {"type": "integer", "description": "目标中心纵坐标, 归一化 0-1000 (上0下1000)"},
        "target": {"type": "string",
                   "description": "你要操作的对象(如'开始游戏按钮'), 给用户看的确认文案用; 务必填"},
    }
    return [
        {
            "name": "computer_click",
            "description": "在屏幕某处点击鼠标。坐标是归一化 0-1000, 由你看截图判断。"
                           "**必须先 capture_screen 看当前画面**再给坐标。点前可能要用户确认。",
            "input_schema": {
                "type": "object",
                "properties": {**_xy,
                    "button": {"type": "string", "enum": ["left", "right", "middle"],
                               "description": "left=左键(默认) right=右键 middle=中键"}},
                "required": ["x", "y", "target"],
            },
        },
        {
            "name": "computer_double_click",
            "description": "在屏幕某处双击左键(如打开桌面图标)。坐标 0-1000。先 capture_screen 再给坐标。",
            "input_schema": {"type": "object", "properties": {**_xy}, "required": ["x", "y", "target"]},
        },
        {
            "name": "computer_move",
            "description": "只把鼠标移到某处(不点击), 用于悬停查看。坐标 0-1000。",
            "input_schema": {"type": "object", "properties": {**_xy}, "required": ["x", "y", "target"]},
        },
        {
            "name": "computer_scroll",
            "description": "在屏幕某处滚动鼠标滚轮(翻页/找列表里的东西)。坐标 0-1000。",
            "input_schema": {
                "type": "object",
                "properties": {**_xy,
                    "direction": {"type": "string", "enum": ["up", "down"], "description": "up上 down下"},
                    "amount": {"type": "integer", "description": "滚几格(1-20, 默认3)"}},
                "required": ["x", "y", "target", "direction"],
            },
        },
        {
            "name": "wait",
            "description": "等待一会儿再继续(用于开程序/加载游戏这类有延迟的场景), 然后你应再 capture_screen 看状态。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ms": {"type": "integer", "description": "等待毫秒数 (100-10000)"},
                    "reason": {"type": "string", "description": "等什么(如'等 Steam 启动')"}},
                "required": ["ms"],
            },
        },
    ]


def _capture_screen(_a: dict) -> dict:
    """截屏 (受 screenshot_enabled 开关约束; 结果含 base64 图, 由 AgentThread 转成图像回填)。"""
    from core import agent_settings
    if not agent_settings.load_agent_settings().get("screenshot_enabled", True):
        return {"ok": False, "error": "用户未开启截屏 (在 AI 设置里开启 screenshot_enabled)"}
    from agent import screen_capture
    return screen_capture.grab_png()


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
        a.get("x", 0), a.get("y", 0), a.get("w"), a.get("h"),
        a.get("stick_id"), a.get("name")),
    "remove_button": lambda a: ConfigTools.remove_button(int(a["index"]), a.get("name")),
    "move_button": lambda a: ConfigTools.move_button(
        int(a["index"]), a["direction"], a.get("cells", 1), a.get("name")),
    "set_button_geometry": lambda a: ConfigTools.set_button_geometry(
        int(a["index"]), a.get("x"), a.get("y"), a.get("w"), a.get("h"), a.get("name")),
    "set_element_field": lambda a: ConfigTools.set_element_field(
        int(a["index"]), a["field"], a["value"], a.get("name")),
    # 多模态
    "capture_screen": lambda a: _capture_screen(a),
    # 执行 (真跑; 由 AgentThread 走安全闸, 不该走到这里)
    "run_action": lambda a: {"ok": False, "error": "run_action 须经安全闸 (内部错误)"},
    "run_sequence": lambda a: {"ok": False, "error": "run_sequence 须经安全闸 (内部错误)"},
    # 操作电脑 (由 AgentThread 换算+主线程执行, 不该走到这里)
    "computer_click": lambda a: {"ok": False, "error": "computer_click 须经安全闸 (内部错误)"},
    "computer_double_click": lambda a: {"ok": False, "error": "computer_double_click 须经安全闸 (内部错误)"},
    "computer_move": lambda a: {"ok": False, "error": "computer_move 须经安全闸 (内部错误)"},
    "computer_scroll": lambda a: {"ok": False, "error": "computer_scroll 须经安全闸 (内部错误)"},
}

# 结果需转成图像回填 (由 AgentThread 特殊处理, 不走 JSON 文本 tool_result)
IMAGE_TOOLS = {"capture_screen"}
# 会真实发出输入的执行类工具 (AgentThread 拦截 → 预演 → 确认/auto → 执行)
EXEC_TOOLS = {"run_action", "run_sequence"}
# 操作电脑 (L3 坐标) 工具: 坐标 0-1000, 由 AgentThread 换算像素 + 主线程执行, 走安全闸分档确认。
# 不走通用 dispatch。computer_move 无点击(🟢), 其余点击/滚动按分档确认。
COMPUTER_TOOLS = {"computer_click", "computer_double_click", "computer_move", "computer_scroll"}
# wait: 子线程 sleep, 无输入、无确认 (AgentThread 直接处理)
WAIT_TOOL = "wait"

# 会改动配置 → 需要热生效的工具 (新加的 list 编辑工具必须在此登记, 否则改完不热重载)
WRITE_TOOLS = {
    "set_button_binding", "set_param", "reset_param",
    "add_voice_command", "remove_voice_command", "set_voice_command",
    "set_wheel_sector", "add_app", "remove_app",
    "add_macro", "remove_macro", "add_button", "remove_button",
    "move_button", "set_button_geometry", "set_element_field",
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


# ── 跨"配置/执行"共用的公共认知 (将来若拆成多套工具集/提示, 两边都复用此常量, 不重写) ──
SHARED_TERMINOLOGY = """**术语与指代 (用户怎么叫元素, 你要对上)**:
- 类型: 普通键(normal)、手柄键(gp_button)、摇杆(gp_stick)、方向盘(gp_wheel)、回中带(center_band)。
- **"中心轮盘" = "中心环"**: 同一个东西(8扇区那个), 是顶层 wheel_*/wheel_sectors(**不在 buttons 里**)、单例。它和"方向盘"**不是一回事**。
- **"方向盘"** = gp_wheel 元素(在 buttons 里、单例)。
- 用户指代摇杆的三种说法:
  · "左摇杆/右摇杆" → 指 **stick_id=L / R** 的 analog 摇杆(是 ID 的左右, 不是名字)
  · "WASD摇杆" → 指 **mode='wasd'** 的摇杆
  · 直接报名字 → 按 name 匹配(手柄键/按钮/回中带/摇杆都有 name, 见速览)
- 名字现在按类型编号(手柄键01/按钮01/回中带01 等); 用户可能说"第一个手柄键"(按顺序数)或直接名字。
- 指代匹配到多个时, 先列候选(index+方位+颜色+名字)让用户确认, 别乱猜。"""


def system_prompt() -> str:
    """拼系统提示: 静态规则 + 标签语法 + 紧凑 profile 索引 (细节走工具按需拉取)。"""
    gp_labels = ", ".join(f"gp:{k}" for k in GP_LABEL_TO_KEY.values())
    index = _profile_index()

    return f"""你是「蛋挞 TEGGTouch」的配置助手。蛋挞是 Windows 无障碍辅助工具, 把鼠标/触屏操作映射成键盘/鼠标/手柄输入, 帮助手部不便的用户玩需要键鼠/手柄的游戏。

你的职责: 用工具帮用户读取和修改蛋挞的按键配置 (profile)。你**只能改配置**, 不能直接操作鼠标键盘 (那是后续阶段的能力)。

看屏幕: 用户让你看屏幕、或你需要看画面才能判断时, 调 capture_screen (截图不含蛋挞自己的覆盖层, 每次都会告知用户), 然后据图回答。别凭空猜屏幕内容。

执行操作 (帮用户"按键", 非改配置): 用户说"帮我按X""放个技能""打开录屏"等要你**真的发输入**时, 用 run_action。流程: 先 summarize_profile 找到对应元素绑定的 value(如某按钮 hover='ctrl+f4'), 再 run_action(value=值, target=该元素名字如'茶叶蛋')。target 会显示在给用户的确认弹窗里, 知道就带上。也可直接跑宏 'xmacro:名' / 启动应用 'app:名'。**重复 N 次 或 一连串操作**(如"连按A十次""先按A再按B")→ 用 run_sequence 把整串打包成 steps, **只弹一次确认、一次执行**, 千万别 run_action 调 N 次(会弹 N 次确认)。注意: 默认会先弹确认, 确认后才真执行; 用户随时可急停。别把"改配置"和"发输入"搞混——改键位用 set_*, 真按键用 run_action/run_sequence。

你能改 profile 里的几乎所有东西:
- 元素: 改绑定/名字 (set_button_binding)、新增任意类型 (add_button, 含普通键/手柄键/回中带/摇杆/方向盘;
  方向盘单例, 已有即"已启用")、删除 (remove_button)
- 类型专有/高级字段: set_element_field (摇杆 dead_zone/eight_way/mode/wasd_*、方向盘 control_mode、
  按钮 hover_repeat_interval 长按连发 等 —— 凡 summarize 的 fields 里有的字段都能改)
- 摇杆(gp_stick)领域知识 (关键!): 有两种 mode ——
  · mode='analog': 模拟手柄摇杆, 由 stick_id=L/R 决定是**左**还是**右**摇杆;
  · mode='wasd': 圆盘模拟 W/A/S/D 方向键, **此模式下 stick_id 完全无效**(不驱动手柄摇杆)。
  所以用户说"改成左/右摇杆"通常指 analog 摇杆: 若目标摇杆当前是 wasd 模式, **光改 stick_id 没有任何效果**,
  要么同时把 mode 改成 'analog'(会从"出方向键"变成"出手柄摇杆", 行为大变), 要么先问用户是否要这样切。
  别只改 stick_id 就报成功。
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
{SHARED_TERMINOLOGY}

**行为准则 (重要)**:
- **能做就直接做, 别反复确认。** 改配置是安全、可撤销、即时热生效的; 用户意图清楚时直接执行 + 一句话回报, 不要写长篇、不要追问"你确定吗"。
- 用户重复同一要求 = 你上一轮太啰嗦或没动手, 立刻执行, 别再解释为什么难。
- **别编造"改不了"。** profile 里元素的几乎所有字段(含摇杆 stick_id、mode、dead_zone 等)都能用
  set_element_field 改。拿不准某字段能不能改, 先 summarize_profile 看该元素 fields 里有没有, 有就直接改, 不要凭空说不行。
- 回复**简短**(通常 1~3 句)。只在**真的有歧义**且无法合理默认时才问, 且只问一个最短的问题。
- "启用/添加 方向盘(gp_wheel)/摇杆(gp_stick)" → 直接 add_button, 不要说"要在编辑界面手动加"(你能加, 方向盘还是单例)。

工作流程:
1. 需要现状时先 summarize_profile; 简单改动可直接动手。
2. 用工具落实修改 (立即保存并热生效)。
3. 用**人话**一句话回报改了什么 (字段/旧值→新值)。

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
