"""
TEGGTouch 蛋挞 — Agent 工具层 (headless 原型 / 调查项 D2)

把散落在 input_engine / gamepad_engine / config_manager 的能力, 收敛成一组
稳定、无 UI 依赖、可被 agent 调用的工具。当前为阶段0原型, 用于验证
"不需要大重构、可程序化操作蛋挞" 这一判断。

两个工具集 (对应 docs/agent-integration-design.md 决策 #4 的 toolset):
- ConfigTools  : 程序化读写 profile 的绑定与参数 (复用 core.config_manager)
- ControlTools : 按现有标签语法 (普通键 / mouse: / gp:) 分派键盘/鼠标/手柄
                 输入 + 鼠标绝对移动; 支持 dry_run 安全空跑

设计约束 (决策 #1 / #2):
- 进程内直调, 但接口按 "可抽成独立进程 + IPC" 设计: 入参/返回都是纯
  dict/list/标量, 不持有任何 Qt 对象, 不依赖运行中的窗口。
- action 协议复用现有标签 + 宏 schema, agent 输出即蛋挞可执行, 零翻译。

已知边界 (这正是 D2 要暴露的真实工作量 / G1):
- macro: / xmacro: / gpmacro: / recenter: / app: 这几类需要 RunController 与
  scene 的运行时上下文, headless 暂不执行, 统一返回 status='deferred',
  让上层清楚看到 "哪些能力还绑在 UI/运行时上"。
"""

from __future__ import annotations

import copy
import inspect
import json
import logging
import time

from core import input_engine
from core import action_service
from core import button_theme
from core.constants import (APP_PREFIX, GP_KEY_PREFIX, GP_LABEL_TO_KEY,
                            DEFAULT_WHEEL_STYLE, DEFAULT_CURSOR_STYLES,
                            DEFAULT_BALL_STYLES, DEFAULT_CURSOR_SHAPE)
from core import config_manager as cfg

logger = logging.getLogger(__name__)

# save_config_to_file 接受的顶层参数白名单 (从签名推导, 去掉 filepath / buttons:
# buttons 改用 set_button_binding)。set_param 写未知 key 会被 save_config_to_file
# 当成非法 kwarg 而崩, 故在此先拦截并给 agent 清晰提示。
_PARAM_FIELDS = frozenset(
    name for name, p in inspect.signature(cfg.save_config_to_file).parameters.items()
    if p.kind == inspect.Parameter.KEYWORD_ONLY and name != "buttons"
)

# 模型经 tool_use 常把数字/布尔当字符串传 (value schema 无类型约束), 会污染
# profile 里的标量参数 (如 transparency 变成 '0.42' 字符串, setWindowOpacity 崩)。
_TRUE_STRS = {"true", "1", "yes", "on", "是", "开"}
_FALSE_STRS = {"false", "0", "no", "off", "否", "关"}


def _coerce_to_type(value, ref):
    """把 value 转成参考值 ref 的类型 (bool/int/float)。转不动就原样返回。

    ref 为已存在的旧值; None (未设置过) 时无从推断类型, 保持原样。
    bool 要在 int 前判 (bool 是 int 子类)。
    """
    if ref is None or type(value) is type(ref):
        return value
    try:
        if isinstance(ref, (dict, list)):
            # 模型常把字典/列表值当 JSON 字符串传 (如 wheel_style='{\"color\":\"#FF8C00\"}')
            if isinstance(value, str):
                parsed = json.loads(value)
                return parsed if isinstance(parsed, type(ref)) else value
            return value
        if isinstance(ref, bool):
            if isinstance(value, str):
                s = value.strip().lower()
                if s in _TRUE_STRS:
                    return True
                if s in _FALSE_STRS:
                    return False
                return value  # 无法判定, 保留原值给上层/模型看到
            return bool(value)
        if isinstance(ref, int):
            return int(value)
        if isinstance(ref, float):
            return float(value)
    except (TypeError, ValueError):
        return value
    return value

# action(agent 用语) → input_engine 动作码
_ACTION_CODE = {"click": "c", "press": "p", "release": "r"}

# 宏标签前缀 → action_service 宏池
_MACRO_PREFIX_POOL = {"xmacro:": "x", "gpmacro:": "gp", "macro:": "kb"}

# 合法的手柄标签 (存储 key)
_GP_LABELS = set(GP_LABEL_TO_KEY.values())

# 鼠标按钮 / 滚轮
_MOUSE_BUTTONS = {"left", "right", "middle", "x1", "x2"}
_MOUSE_WHEELS = {"wheelup", "wheeldown"}


# ════════════════════════════════════════════════════════════════
# ControlTools — 键盘 / 鼠标 / 手柄 / 绝对定位
# ════════════════════════════════════════════════════════════════

class ControlTools:
    """把意图(标签语法)翻译成真实输入。所有方法返回可序列化 dict, 便于日后 IPC。"""

    @staticmethod
    def run_keys(key_str: str, action: str = "click", dry_run: bool = False,
                 profile: str | None = None) -> dict:
        """执行一个绑定值 (可含 '+' 组合 / 多标签)。

        复刻 run_controller._smart_trigger 的分类逻辑, 但完全 headless:
        '+' 拆分后, 普通键合并成组合键一次触发(保证 ctrl+f4 这类成立),
        mouse:/gp:/macro:/app:/recenter: 各自执行 (宏/应用从 profile 配置查)。

        返回 {key_str, action, steps:[{part, kind, status, detail}...]}。
        """
        if action not in _ACTION_CODE:
            return {"key_str": key_str, "action": action, "ok": False,
                    "error": f"未知 action: {action} (应为 click/press/release)"}

        parts = [p.strip() for p in (key_str or "").split("+") if p.strip()]
        normal_keys: list[str] = []
        steps: list[dict] = []

        for p in parts:
            macro_pref = next((x for x in _MACRO_PREFIX_POOL if p.startswith(x)), None)
            if macro_pref:
                steps.append(ControlTools._do_macro(
                    p[len(macro_pref):], _MACRO_PREFIX_POOL[macro_pref], action, dry_run, profile))
            elif p.startswith("recenter:"):
                steps.append(ControlTools._do_recenter(p[len("recenter:"):], dry_run))
            elif p.startswith(APP_PREFIX):
                steps.append(ControlTools._do_app(p[len(APP_PREFIX):], dry_run, profile))
            elif p.startswith("mouse:"):
                steps.append(ControlTools._do_mouse(p[6:], action, dry_run))
            elif p.startswith(GP_KEY_PREFIX):
                steps.append(ControlTools._do_gamepad(p[len(GP_KEY_PREFIX):], action, dry_run))
            else:
                normal_keys.append(p)

        if normal_keys:
            steps.insert(0, ControlTools._do_keys(normal_keys, action, dry_run))

        ok = all(s.get("status") in ("ok", "deferred", "skip") for s in steps)
        return {"key_str": key_str, "action": action, "ok": ok, "steps": steps}

    # ── 键盘 ──
    @staticmethod
    def _do_keys(keys: list[str], action: str, dry_run: bool) -> dict:
        combo = "+".join(keys)
        # 解析扫描码 — 即便 dry_run 也跑, 用来证明 headless 下按键解析可用
        resolved = []
        for k in keys:
            sc, ext = input_engine._resolve_scan(k)
            resolved.append({"key": k, "scan": sc, "ext": ext,
                             "ok": sc != 0})
        unresolved = [r["key"] for r in resolved if not r["ok"]]
        if unresolved:
            return {"part": combo, "kind": "key", "status": "error",
                    "detail": f"无法解析按键: {unresolved}", "resolved": resolved}
        if dry_run:
            return {"part": combo, "kind": "key", "status": "ok",
                    "detail": f"[dry-run] trigger('{combo}', '{_ACTION_CODE[action]}')",
                    "resolved": resolved}
        input_engine.trigger(combo, _ACTION_CODE[action])
        return {"part": combo, "kind": "key", "status": "ok",
                "detail": f"trigger('{combo}', '{_ACTION_CODE[action]}')",
                "resolved": resolved}

    # ── 鼠标 ──
    @staticmethod
    def _do_mouse(val: str, action: str, dry_run: bool) -> dict:
        val = val.lower()
        token = f"mouse:{val}"
        if val in _MOUSE_WHEELS:
            if action == "release":
                return {"part": token, "kind": "mouse_wheel", "status": "skip",
                        "detail": "滚轮 release 忽略"}
            direction = "up" if val == "wheelup" else "down"
            if not dry_run:
                input_engine.mouse_wheel(direction)
            return {"part": token, "kind": "mouse_wheel", "status": "ok",
                    "detail": f"{'[dry-run] ' if dry_run else ''}mouse_wheel('{direction}')"}
        if val in _MOUSE_BUTTONS:
            if dry_run:
                return {"part": token, "kind": "mouse_btn", "status": "ok",
                        "detail": f"[dry-run] mouse {val} {action}"}
            if action == "press":
                input_engine.mouse_press(val)
            elif action == "release":
                input_engine.mouse_release(val)
            else:  # click
                input_engine.mouse_press(val)
                time.sleep(0.04)
                input_engine.mouse_release(val)
            return {"part": token, "kind": "mouse_btn", "status": "ok",
                    "detail": f"mouse {val} {action}"}
        return {"part": token, "kind": "mouse", "status": "error",
                "detail": f"未知鼠标目标: {val}"}

    # ── 手柄 ──
    @staticmethod
    def _do_gamepad(label: str, action: str, dry_run: bool) -> dict:
        token = f"gp:{label}"
        if label not in _GP_LABELS:
            return {"part": token, "kind": "gamepad", "status": "error",
                    "detail": f"未知手柄标签: {label}"}
        if dry_run:
            return {"part": token, "kind": "gamepad", "status": "ok",
                    "detail": f"[dry-run] gamepad {label} {action}"}
        from engine.gamepad_engine import GamepadEngine
        gp = GamepadEngine.get()
        if gp is None:
            return {"part": token, "kind": "gamepad", "status": "error",
                    "detail": "GamepadEngine 不可用 (ViGEmBus 未装/未加载)"}
        if action == "press":
            gp.press_button(label); gp.flush()
        elif action == "release":
            gp.release_button(label); gp.flush()
        else:  # click
            gp.press_button(label); gp.flush()
            time.sleep(0.05)
            gp.release_button(label); gp.flush()
        return {"part": token, "kind": "gamepad", "status": "ok",
                "detail": f"gamepad {label} {action}"}

    # ── 宏 (复用 core.action_service, 与运行时同一份实现) ──
    @staticmethod
    def _do_macro(name: str, pool: str, action: str, dry_run: bool,
                  profile: str | None) -> dict:
        token = {"x": "xmacro:", "gp": "gpmacro:", "kb": "macro:"}[pool] + name
        if action == "release":  # 宏只在 press/click 触发, 与 _smart_trigger 一致
            return {"part": token, "kind": "macro", "status": "skip", "detail": "release 忽略"}
        config = cfg.load_profile(profile or cfg.get_active_profile_name())
        macro = action_service.find_macro(config, name, pool)
        if macro is None:
            return {"part": token, "kind": "macro", "status": "error",
                    "detail": f"宏未找到: {name} (pool={pool})"}
        n_steps = len(macro.get("steps", []))
        if dry_run:
            return {"part": token, "kind": "macro", "status": "ok",
                    "detail": f"[dry-run] 宏 '{name}' ({n_steps} 步 ×{macro.get('repeat', 1)})"}
        trig = lambda keys, act: ControlTools.run_keys(keys, act, dry_run=False, profile=profile)
        done = action_service.run_macro(macro, trig)
        return {"part": token, "kind": "macro", "status": "ok",
                "detail": f"宏 '{name}' 执行 {done} 步"}

    # ── 启动应用 ──
    @staticmethod
    def _do_app(name: str, dry_run: bool, profile: str | None) -> dict:
        token = f"{APP_PREFIX}{name}"
        config = cfg.load_profile(profile or cfg.get_active_profile_name())
        path = action_service.resolve_app_path(name, config.get("apps", []))
        if not path:
            return {"part": token, "kind": "app", "status": "error",
                    "detail": f"应用未找到/路径失效: {name}"}
        if dry_run:
            return {"part": token, "kind": "app", "status": "ok",
                    "detail": f"[dry-run] launch {path}"}
        ok = action_service.launch_app(path)
        return {"part": token, "kind": "app", "status": "ok" if ok else "error",
                "detail": f"launch {path}"}

    # ── 回中 (仅 screen 可 headless; wheel/stick/center_ring 需运行时窗口几何) ──
    @staticmethod
    def _do_recenter(target: str, dry_run: bool) -> dict:
        token = f"recenter:{target}"
        if target in ("", "screen"):
            cx, cy = action_service.screen_center()
            if not dry_run:
                input_engine.mouse_move(cx, cy)
            return {"part": token, "kind": "recenter", "status": "ok",
                    "detail": f"{'[dry-run] ' if dry_run else ''}回中到主屏中心 ({cx}, {cy})"}
        return {"part": token, "kind": "recenter", "status": "deferred",
                "detail": f"'{target}' 需运行中的窗口/控件几何, headless 无法解析"}

    # ── 鼠标绝对定位 (G5) ──
    @staticmethod
    def move_mouse(x: int, y: int, dry_run: bool = False) -> dict:
        if not dry_run:
            input_engine.mouse_move(x, y)
        return {"kind": "mouse_move", "status": "ok", "x": int(x), "y": int(y),
                "detail": f"{'[dry-run] ' if dry_run else ''}mouse_move({x}, {y})"}

    # ── computer use L3: 绝对像素点击/滚动 (0-1000 → 像素的换算在上层做) ──
    @staticmethod
    def click_xy(x: int, y: int, button: str = "left", double: bool = False,
                 dry_run: bool = False) -> dict:
        """移动到绝对像素 (x,y) 并点击。button: left/right/middle; double=双击。"""
        x, y = int(x), int(y)
        if button not in _MOUSE_BUTTONS:
            return {"kind": "click_xy", "status": "error",
                    "detail": f"未知鼠标按钮: {button}", "ok": False}
        detail = f"click_xy({x},{y},{button}{',double' if double else ''})"
        if dry_run:
            return {"kind": "click_xy", "status": "ok", "ok": True, "x": x, "y": y,
                    "button": button, "double": double, "detail": f"[dry-run] {detail}"}
        input_engine.mouse_move(x, y)
        time.sleep(0.04)
        for i in range(2 if double else 1):
            input_engine.mouse_press(button)
            time.sleep(0.03)
            input_engine.mouse_release(button)
            if double and i == 0:
                time.sleep(0.06)
        return {"kind": "click_xy", "status": "ok", "ok": True, "x": x, "y": y,
                "button": button, "double": double, "detail": detail}

    @staticmethod
    def scroll_xy(x: int, y: int, direction: str = "down", amount: int = 3,
                  dry_run: bool = False) -> dict:
        """移到绝对像素 (x,y) 处滚动 amount 格。direction: up/down。"""
        x, y = int(x), int(y)
        direction = (direction or "down").lower()
        if direction not in ("up", "down"):
            return {"kind": "scroll_xy", "status": "error",
                    "detail": f"方向应为 up/down: {direction}", "ok": False}
        amount = max(1, min(20, int(amount)))
        detail = f"scroll_xy({x},{y},{direction},x{amount})"
        if dry_run:
            return {"kind": "scroll_xy", "status": "ok", "ok": True, "x": x, "y": y,
                    "direction": direction, "amount": amount, "detail": f"[dry-run] {detail}"}
        input_engine.mouse_move(x, y)
        time.sleep(0.04)
        for _ in range(amount):
            input_engine.mouse_wheel(direction)
            time.sleep(0.02)
        return {"kind": "scroll_xy", "status": "ok", "ok": True, "x": x, "y": y,
                "direction": direction, "amount": amount, "detail": detail}

    # ── 动作序列 ──
    @staticmethod
    def run_sequence(steps: list[dict], dry_run: bool = False,
                     profile: str | None = None) -> dict:
        """执行一串动作。每步是下列之一:
            {"keys": "ctrl+c", "action": "click", "after_ms": 100}
            {"delay_ms": 200}
            {"move": [x, y]}
        返回 {ok, results:[...]}。
        """
        results = []
        for i, step in enumerate(steps):
            if "delay_ms" in step:
                ms = int(step["delay_ms"])
                if not dry_run:
                    time.sleep(ms / 1000.0)
                results.append({"i": i, "kind": "delay", "status": "ok", "ms": ms})
                continue
            if "move" in step:
                x, y = step["move"]
                results.append({"i": i, **ControlTools.move_mouse(x, y, dry_run)})
                continue
            if "keys" in step:
                r = ControlTools.run_keys(step["keys"], step.get("action", "click"),
                                          dry_run, profile)
                results.append({"i": i, **r})
                after = int(step.get("after_ms", 0))
                if after and not dry_run:
                    time.sleep(after / 1000.0)
                continue
            results.append({"i": i, "status": "error", "detail": f"未知步骤: {step}"})
        ok = all(r.get("ok", r.get("status") in ("ok", "deferred", "skip")) for r in results)
        return {"ok": ok, "results": results}


# ════════════════════════════════════════════════════════════════
# ConfigTools — 程序化读写 profile 绑定 / 参数
# ════════════════════════════════════════════════════════════════

# 按钮上允许 agent 改写的绑定字段 (白名单)
_BUTTON_BINDING_FIELDS = {
    "hover", "lclick", "rclick", "mclick", "wheelup", "wheeldown",
    "xbutton1", "xbutton2", "hover_delay", "hover_release_delay",
    "hover_mode", "hover_toggle", "recenter_target",
}

# 按钮上允许 agent 改写的全部字段 = 绑定字段 + 元信息 (如按钮显示名)。
# name 不是"绑定"但用户常要改, 复用 set_button_binding 通道 (省一个工具)。
_BUTTON_WRITABLE_FIELDS = _BUTTON_BINDING_FIELDS | {"name"}

# 元素类型 → 人类可读标签 (用户常按类型描述: "摇杆" "回中带")
_TYPE_LABELS = {
    "normal": "普通键", "center_band": "回中带", "gp_button": "手柄键",
    "gp_stick": "摇杆", "gp_wheel": "手柄方向盘",
    "wheel_sector": "轮盘扇区", "wheel_center_ring": "轮盘中心环",
    "wheel_inner_ring": "轮盘内环",
}

# 颜色不存在按钮数据里 (每个按钮 color/bg_color 常为 null), 而是按类型走 button_theme
# 这个"单一色源": keyboard 组=普通键/中心轮盘, gamepad 组=手柄键+摇杆, center_band 组=回中带,
# 方向盘(gp_wheel)单列, 取 wheel_style.color。这里直接复用 button_theme, 不再自造映射,
# 否则会像先前那样把蓝色方向盘误判成 gamepad 色。


def _element_color_hex(btype: str | None, button_colors: dict | None,
                       wheel_style: dict | None) -> str:
    """按元素类型解析其"代表色"(=用户眼里的描边/边框色), 与渲染完全一致。"""
    if btype == "gp_wheel":
        base = (wheel_style or {}).get("color") or button_theme.DEFAULT_WHEEL_BASE
        return button_theme.derive_shades(base)["border"]
    if btype and btype.startswith("gp"):      # gp_button / gp_stick
        group = "gamepad"
    elif btype == "center_band":
        group = "center_band"
    else:                                     # normal / 其它
        group = "keyboard"
    return button_theme.derive_family(group, (button_colors or {}).get(group))["border"]


def _color_name_from_hex(h) -> str | None:
    """#RRGGBB → 中文粗略色名 (走 HSL, 兼容用户自定义 button_colors)。"""
    if not isinstance(h, str):
        return None
    s = h.lstrip("#")
    if len(s) != 6:
        return None
    try:
        r, g, b = (int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    lightness = (mx + mn) / 2
    if lightness < 0.12:
        return "黑"
    if d < 0.08:
        return "白" if lightness > 0.9 else "灰"
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    hue *= 60
    for lim, name in ((12, "红"), (40, "橙"), (70, "黄"), (160, "绿"),
                      (195, "青"), (255, "蓝"), (300, "紫"), (345, "玫红")):
        if hue < lim:
            return name
    return "红"


def _screen_wh(geometry, default=(1920, 1080)) -> tuple[int, int]:
    """从 'WxH+X+Y' 解析屏幕宽高 (方位判断的参考系)。"""
    try:
        wh = str(geometry).split("+")[0].split("x")
        return int(wh[0]), int(wh[1])
    except (ValueError, AttributeError, IndexError):
        return default


def _region_label(cx: float, cy: float, sw: int, sh: int) -> str:
    """元素中心坐标 → 九宫格方位标签。坐标系原点=屏幕中心, y 越大越靠下。

    校准基准 (用户实测): 玫红手柄键中心约 (-1700,-750) 在屏幕左上 → 本函数返回"左上"。
    阈值用屏幕三分之一; 超出屏幕边缘的坐标仍归到最靠近的边 (不裁剪)。
    """
    hx = cx / (sw / 2) if sw else 0
    hy = cy / (sh / 2) if sh else 0
    col = "左" if hx < -1 / 3 else ("右" if hx > 1 / 3 else "中")
    row = "上" if hy < -1 / 3 else ("下" if hy > 1 / 3 else "中")
    table = {
        ("左", "上"): "左上", ("中", "上"): "正上", ("右", "上"): "右上",
        ("左", "中"): "正左", ("中", "中"): "居中", ("右", "中"): "正右",
        ("左", "下"): "左下", ("中", "下"): "正下", ("右", "下"): "右下",
    }
    return table[(col, row)]


# ── list 型配置的元素级编辑约束 ──
_VOICE_FIELDS = {"phrase", "keys", "action"}           # 语音命令可改字段
_ACTIONS = {"click", "press", "release"}               # action 合法取值
_MACRO_POOLS = {"xmacros", "macros", "gp_macros"}      # 三个宏池 (推荐 xmacros 统一池)
_WHEEL_SECTOR_COUNT = 8                                 # 轮盘扇区固定 8 个 (只改不增删)
# 可由 agent 新增的按钮类型 (共用 ButtonData schema); gp_stick/gp_wheel 数据模型特殊/单例,
# 新增交给 UI, 这里只允许删除。
_ADDABLE_BTN_TYPES = {"normal", "gp_button", "center_band"}
_BTN_TYPE_DEFAULT_NAME = {"normal": "按钮", "gp_button": "手柄键", "center_band": "回中带"}

# 移动方向 → (dx, dy) 单位向量; 坐标系 y<0 为上 (与屏幕一致)
_MOVE_DIRS = {
    "up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0),
    "上": (0, -1), "下": (0, 1), "左": (-1, 0), "右": (1, 0),
}

# 元素的结构字段: 有专用工具(几何)或不可改, set_element_field 不碰
_ELEMENT_STRUCTURAL = {"x", "y", "w", "h", "type"}


# "重置为默认"的默认源 —— 与 UI 各重置按钮用的是**同一份权威常量**, 不另算默认:
#   _on_wheel_reset→DEFAULT_WHEEL_STYLE, _on_bc_reset→DEFAULT_BUTTON_COLORS,
#   _on_arrow_reset→DEFAULT_CURSOR_STYLES, _on_ball_reset→DEFAULT_BALL_STYLES。
# 其余普通参数的默认取自 default_profile 模板。
_RESET_DEFAULTS = {
    "wheel_style": lambda: dict(DEFAULT_WHEEL_STYLE),
    "button_colors": lambda: dict(button_theme.DEFAULT_BUTTON_COLORS),
    "cursor_styles": lambda: {k: dict(v) for k, v in DEFAULT_CURSOR_STYLES.items()},
    "ball_styles": lambda: {k: dict(v) for k, v in DEFAULT_BALL_STYLES.items()},
    "cursor_shape": lambda: DEFAULT_CURSOR_SHAPE,
}


def _default_for_top(top: str):
    """取顶层键的出厂默认: 优先专用常量源, 否则查默认 profile 模板。返回 (found, value)。"""
    if top in _RESET_DEFAULTS:
        return True, _RESET_DEFAULTS[top]()
    try:
        tmpl = cfg._load_default_template()
    except Exception:
        tmpl = {}
    if isinstance(tmpl, dict) and top in tmpl:
        return True, copy.deepcopy(tmpl[top])
    return False, None


def _norm_macro_step(step: dict) -> dict:
    """规范化一个宏步骤: {type:'delay', ms} 或 {type:'key', key, action}。"""
    if not isinstance(step, dict):
        raise ValueError(f"步骤须为对象: {step!r}")
    if step.get("type") == "delay":
        return {"type": "delay", "ms": int(step.get("ms", 100))}
    key = step.get("key") or step.get("keys") or ""
    if not key:
        raise ValueError(f"指令步骤缺 key: {step!r}")
    action = step.get("action", "click")
    if action not in _ACTIONS:
        raise ValueError(f"非法 action: {action}")
    return {"type": step.get("type", "key"), "key": key, "action": action}


class ConfigTools:
    """程序化读写蛋挞配置。全部走 config_manager 公开 API, 原子写有保证。"""

    @staticmethod
    def list_profiles() -> dict:
        return {"active": cfg.get_active_profile_name(),
                "profiles": cfg.list_profiles()}

    @staticmethod
    def _resolve_name(name: str | None) -> str:
        return name or cfg.get_active_profile_name()

    @staticmethod
    def read_profile(name: str | None = None) -> dict:
        """读取完整 profile dict (含默认值填充)。"""
        return cfg.load_profile(ConfigTools._resolve_name(name))

    @staticmethod
    def summarize_profile(name: str | None = None) -> dict:
        """给 agent 看的全量摘要: 每个元素的 类型/名字/方位/颜色/坐标/所有非空字段,
        加全部顶层参数、语音、轮盘、宏、应用。目标是让配置助手感知 profile 里的全部数据
        (需要更原始的完整 dict 时用 read_profile)。
        """
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        sw, sh = _screen_wh(c.get("geometry"))
        bcolors = c.get("button_colors") or {}
        wstyle = c.get("wheel_style") or {}

        promoted = {"x", "y", "w", "h", "type", "name"}
        elements = []
        for i, b in enumerate(c.get("buttons", [])):
            x, y = b.get("x") or 0, b.get("y") or 0
            w, h = b.get("w") or 0, b.get("h") or 0
            btype = b.get("type", "normal")
            hexc = _element_color_hex(btype, bcolors, wstyle)
            # 其余所有非空字段全暴露 (绑定 + 各类型专有参数), 不再挑挑拣拣
            fields = {k: v for k, v in b.items()
                      if k not in promoted and v not in (None, "")}
            elements.append({
                "index": i,
                "type": btype,
                "type_label": _TYPE_LABELS.get(btype, btype),
                "name": b.get("name", ""),
                "region": _region_label(x + w / 2, y + h / 2, sw, sh),
                "color": {"name": _color_name_from_hex(hexc), "hex": hexc},
                "pos": {"x": x, "y": y, "w": w, "h": h},
                "fields": fields,
            })

        # 全部顶层标量参数 (transparency / voice_* / wheel_* / sim_mode ...); geometry
        # 已拆进 screen, 列表/字典类另行结构化, 故这里只收标量。
        params = {k: v for k, v in c.items()
                  if not isinstance(v, (list, dict)) and k != "geometry"}
        voice = [{"phrase": v.get("phrase"), "keys": v.get("keys"),
                  "action": v.get("action")} for v in c.get("voice_commands", [])]
        return {
            "profile": name,
            "screen": {"w": sw, "h": sh,
                       "note": "坐标系原点=屏幕中心; x<0 左 / x>0 右; y<0 上 / y>0 下 (y 越大越靠下)"},
            "button_count": len(elements),
            "buttons": elements,
            "params": params,
            "button_colors": bcolors,
            "voice_enabled": c.get("voice_enabled"),
            "voice_commands": voice,
            "wheel": {
                "visible": c.get("wheel_visible"), "mode": c.get("wheel_mode"),
                "enlarged": c.get("wheel_enlarged"),
                "sector_count": len(c.get("wheel_sectors") or []),
                "sectors": [
                    {"index": i, "name": s.get("name", ""), "angle": s.get("angle"),
                     "bindings": {k: v for k, v in s.items()
                                  if k not in ("name", "angle") and v not in (None, "", 0, "trigger")}}
                    for i, s in enumerate(c.get("wheel_sectors") or [])
                ],
                "center_ring": c.get("wheel_center_ring"),
                "color": wstyle.get("color"),   # 方向盘颜色 (独立于 button_colors)
            },
            # 宏: 展开 name + steps (三个池; xmacros 为统一池)
            "xmacros": c.get("xmacros", []),
            "macros": c.get("macros", []),
            "gp_macros": c.get("gp_macros", []),
            "apps": [{"name": a.get("name"), "path": a.get("path")}
                     for a in c.get("apps", [])],
        }

    @staticmethod
    def set_button_binding(button_index: int, field: str, value: str,
                           name: str | None = None) -> dict:
        """改写某个按钮的一个字段 (绑定 / 名字) 并保存。返回 before/after。"""
        if field not in _BUTTON_WRITABLE_FIELDS:
            return {"ok": False, "error": f"不允许的字段: {field}",
                    "allowed": sorted(_BUTTON_WRITABLE_FIELDS)}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = c.get("buttons", [])
        if not (0 <= button_index < len(buttons)):
            return {"ok": False, "error": f"button_index 越界: {button_index} (共 {len(buttons)} 个)"}
        before = buttons[button_index].get(field)
        value = _coerce_to_type(value, before)  # hover_delay(int)/hover_toggle(bool) 防字符串污染
        buttons[button_index][field] = value
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "button_index": button_index,
                "field": field, "before": before, "after": value}

    @staticmethod
    def set_param(key: str, value, name: str | None = None) -> dict:
        """改写 profile 顶层参数并保存。

        - 标量参数: key='transparency', value=0.5
        - 嵌套标量 (dict 里的一项, 推荐用点路径): key='wheel_style.color', value='#FF8C00'
          → 只改该项, 保留 dict 其它键。
        - 整个 dict 参数: key='wheel_style', value={...} 会与旧 dict **合并** (不覆盖其它键)。
        值的类型按旧值自动纠正 (数字/布尔/字典 JSON 字符串都会被还原成正确类型)。
        """
        top = key.split(".", 1)[0]
        if top not in _PARAM_FIELDS:
            return {"ok": False, "error": f"不允许的参数: {top}",
                    "allowed": sorted(_PARAM_FIELDS)}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)

        # ── 点路径: 改 dict 里的一个嵌套项 (如 wheel_style.color) ──
        if "." in key:
            parts = key.split(".")
            container = c
            for p in parts[:-1]:
                nxt = container.get(p)
                if not isinstance(nxt, dict):
                    nxt = {}
                    container[p] = nxt
                container = nxt
            leaf = parts[-1]
            before = container.get(leaf)
            value = _coerce_to_type(value, before)
            container[leaf] = value
            cfg.save_profile(name, c)
            return {"ok": True, "profile": name, "key": key,
                    "before": before, "after": value}

        # ── 顶层参数 ──
        before = c.get(key)
        value = _coerce_to_type(value, before)  # 数字/布尔/JSON字符串 → 正确类型
        # dict 参数 (wheel_style / button_colors ...) 合并而非整体覆盖, 避免丢兄弟键
        if isinstance(before, dict) and isinstance(value, dict):
            value = {**before, **value}
        c[key] = value
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "key": key,
                "before": before, "after": value}

    @staticmethod
    def reset_param(key: str, name: str | None = None) -> dict:
        """把某参数重置为出厂默认 (等价于面板里的"重置"按钮, 用同一份默认常量)。
        支持点路径: key='wheel_style.color' 重置方向盘颜色回默认蓝; key='button_colors'
        重置全部配色组; key='transparency' 回默认。用户说"重置/恢复默认"时用它。
        """
        top = key.split(".", 1)[0]
        found, default_top = _default_for_top(top)
        if not found:
            return {"ok": False, "error": f"该参数无已知默认值, 无法重置: {top}"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)

        if "." in key:
            parts = key.split(".")
            d = default_top                       # 在默认值里定位 leaf
            for p in parts[1:]:
                if not isinstance(d, dict) or p not in d:
                    return {"ok": False, "error": f"默认值里没有此项: {key}"}
                d = d[p]
            container = c                          # 在 profile 里定位并写入
            for p in parts[:-1]:
                nxt = container.get(p)
                if not isinstance(nxt, dict):
                    nxt = {}
                    container[p] = nxt
                container = nxt
            leaf = parts[-1]
            before, after = container.get(leaf), d
            container[leaf] = d
        else:
            before, after = c.get(top), default_top   # 整项替换回默认 (不合并)
            c[top] = default_top

        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "key": key,
                "before": before, "after": after, "reset_to_default": True}

    # ════════════════════════════════════════════════════════════
    # list 型配置的元素级编辑 (语音命令 / 轮盘扇区 / 宏 / 应用 / 按钮)
    # ════════════════════════════════════════════════════════════

    # ── 语音命令 ──
    @staticmethod
    def add_voice_command(phrase: str, keys: str, action: str = "click",
                          name: str | None = None) -> dict:
        """新增一条语音命令 (短语→按键)。"""
        if action not in _ACTIONS:
            return {"ok": False, "error": f"action 须为 {sorted(_ACTIONS)}"}
        if not (phrase or "").strip():
            return {"ok": False, "error": "phrase 不能为空"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        cmds = c.setdefault("voice_commands", [])
        item = {"phrase": phrase, "keys": keys or "", "action": action}
        cmds.append(item)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": len(cmds) - 1, "added": item}

    @staticmethod
    def remove_voice_command(index: int, name: str | None = None) -> dict:
        """按 index 删除一条语音命令。"""
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        cmds = c.get("voice_commands", [])
        if not (0 <= index < len(cmds)):
            return {"ok": False, "error": f"index 越界: {index} (共 {len(cmds)} 条)"}
        removed = cmds.pop(index)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "removed": removed}

    @staticmethod
    def set_voice_command(index: int, field: str, value, name: str | None = None) -> dict:
        """改某条语音命令的一个字段 (phrase/keys/action)。"""
        if field not in _VOICE_FIELDS:
            return {"ok": False, "error": f"不允许的字段: {field}",
                    "allowed": sorted(_VOICE_FIELDS)}
        if field == "action" and value not in _ACTIONS:
            return {"ok": False, "error": f"action 须为 {sorted(_ACTIONS)}"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        cmds = c.get("voice_commands", [])
        if not (0 <= index < len(cmds)):
            return {"ok": False, "error": f"index 越界: {index} (共 {len(cmds)} 条)"}
        before = cmds[index].get(field)
        cmds[index][field] = value
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": index,
                "field": field, "before": before, "after": value}

    # ── 轮盘扇区 (固定 8 个, 只改绑定) ──
    @staticmethod
    def set_wheel_sector(index: int, field: str, value, name: str | None = None) -> dict:
        """改某个轮盘扇区的一个绑定/名字字段 (扇区数量固定, 不可增删)。"""
        if field not in _BUTTON_WRITABLE_FIELDS:
            return {"ok": False, "error": f"不允许的字段: {field}",
                    "allowed": sorted(_BUTTON_WRITABLE_FIELDS)}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        secs = c.get("wheel_sectors", [])
        if not (0 <= index < len(secs)):
            return {"ok": False, "error": f"扇区 index 越界: {index} (共 {len(secs)} 个)"}
        before = secs[index].get(field)
        value = _coerce_to_type(value, before)
        secs[index][field] = value
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": index,
                "field": field, "before": before, "after": value}

    # ── 应用 ──
    @staticmethod
    def add_app(app_name: str, path: str, name: str | None = None) -> dict:
        """新增一个可启动应用 (name + .lnk/可执行路径)。"""
        if not (app_name or "").strip() or not (path or "").strip():
            return {"ok": False, "error": "app_name 与 path 都不能为空"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        apps = c.setdefault("apps", [])
        item = {"name": app_name, "path": path}
        apps.append(item)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": len(apps) - 1, "added": item}

    @staticmethod
    def remove_app(index: int, name: str | None = None) -> dict:
        """按 index 删除一个应用。"""
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        apps = c.get("apps", [])
        if not (0 <= index < len(apps)):
            return {"ok": False, "error": f"index 越界: {index} (共 {len(apps)} 个)"}
        removed = apps.pop(index)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "removed": removed}

    # ── 宏 ──
    @staticmethod
    def add_macro(macro_name: str, steps: list, pool: str = "xmacros",
                  name: str | None = None) -> dict:
        """新建一个宏 (name + steps)。steps 每步: {type:'delay',ms} 或 {type:'key',key,action}。"""
        if pool not in _MACRO_POOLS:
            return {"ok": False, "error": f"pool 须为 {sorted(_MACRO_POOLS)}"}
        if not (macro_name or "").strip():
            return {"ok": False, "error": "宏名不能为空"}
        try:
            norm = [_norm_macro_step(s) for s in (steps or [])]
        except (ValueError, TypeError) as e:
            return {"ok": False, "error": f"步骤非法: {e}"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        pool_list = c.setdefault(pool, [])
        if any(m.get("name") == macro_name for m in pool_list):
            return {"ok": False, "error": f"宏名已存在: {macro_name}"}
        item = {"name": macro_name, "steps": norm}
        pool_list.append(item)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "pool": pool, "added": item}

    @staticmethod
    def remove_macro(macro_name: str, pool: str = "xmacros",
                     name: str | None = None) -> dict:
        """按名字删除一个宏。"""
        if pool not in _MACRO_POOLS:
            return {"ok": False, "error": f"pool 须为 {sorted(_MACRO_POOLS)}"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        pool_list = c.get(pool, [])
        idx = next((i for i, m in enumerate(pool_list)
                    if m.get("name") == macro_name), None)
        if idx is None:
            return {"ok": False, "error": f"未找到宏: {macro_name}"}
        removed = pool_list.pop(idx)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "pool": pool, "removed": removed}

    # ── 按钮增删 ──
    @staticmethod
    def add_button(btn_type: str = "normal", btn_name: str | None = None,
                   x: float = 0, y: float = 0,
                   w: float | None = None, h: float | None = None,
                   stick_id: str | None = None, name: str | None = None) -> dict:
        """新增一个元素 (normal/gp_button/center_band/gp_stick/gp_wheel)。
        方向盘 gp_wheel 是单例: 已存在则直接返回它 (视为"已启用")。
        摇杆 gp_stick 可传 stick_id ('L'=左 / 'R'=右; 省略默认 L)。
        x/y 为屏幕中心原点坐标 (x<0左 x>0右 y<0上 y>0下); 省略 w/h 用类型默认。
        """
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = c.setdefault("buttons", [])

        # 摇杆 / 方向盘: 用各自数据模型的默认值构造 (与 UI add_gp_stick/add_gp_wheel 一致)
        if btn_type in ("gp_stick", "gp_wheel"):
            from models.gamepad_model import GamepadStickData, GamepadWheelData
            if btn_type == "gp_wheel":
                exist = next((i for i, b in enumerate(buttons)
                              if b.get("type") == "gp_wheel"), None)
                if exist is not None:                 # 单例: 已有即"已启用"
                    return {"ok": True, "profile": name, "index": exist,
                            "already_exists": True, "note": "方向盘已存在 (单例), 无需重复添加"}
                data = GamepadWheelData(x=float(x), y=float(y))
            else:
                sid = str(stick_id).upper() if stick_id else None
                data = (GamepadStickData(x=float(x), y=float(y), stick_id=sid)
                        if sid in ("L", "R") else GamepadStickData(x=float(x), y=float(y)))
            btn = data.to_dict()
            if w:
                btn["w"] = float(w)
            if h:
                btn["h"] = float(h)
            if btn_name:
                btn["name"] = btn_name
            buttons.append(btn)
            cfg.save_profile(name, c)
            return {"ok": True, "profile": name, "index": len(buttons) - 1,
                    "added": {"type": btn_type, "name": btn.get("name", "")}}

        if btn_type not in _ADDABLE_BTN_TYPES:
            return {"ok": False, "error": f"未知类型: {btn_type}"}
        gs = c.get("grid_size") or 100
        # 未指定名字 → 按类型编号命名 (手柄键01/按钮01/回中带01), 便于用户指明
        if btn_name:
            auto_name = btn_name
        else:
            from core.naming import next_numbered_name
            prefix = _BTN_TYPE_DEFAULT_NAME[btn_type]
            existing = [b.get("name") for b in buttons if b.get("type") == btn_type]
            auto_name = next_numbered_name(existing, prefix)
        btn = {
            "type": btn_type,
            "name": auto_name,
            "x": float(x), "y": float(y),
            "w": float(w) if w else gs, "h": float(h) if h else gs,
        }
        if btn_type == "center_band":            # 回中带默认零延迟 (与 UI 新建一致)
            btn["hover_delay"] = 0
            btn["hover_release_delay"] = 0
        buttons.append(btn)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": len(buttons) - 1, "added": btn}

    @staticmethod
    def remove_button(index: int, name: str | None = None) -> dict:
        """按 index 删除一个按钮 (任意类型, index 同 summarize_profile)。"""
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = c.get("buttons", [])
        if not (0 <= index < len(buttons)):
            return {"ok": False, "error": f"index 越界: {index} (共 {len(buttons)} 个)"}
        removed = buttons.pop(index)
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name,
                "removed": {"type": removed.get("type"), "name": removed.get("name")}}

    # ── 元素位置 / 尺寸 (所有元素含方向盘 gp_wheel 都按各自 buttons.x/y 渲染) ──
    @staticmethod
    def move_button(index: int, direction: str, cells: float = 1,
                    name: str | None = None) -> dict:
        """按网格相对移动某元素 (方向 上/下/左/右, cells 格数)。坐标系 y<0 上, 一格=grid_size。
        注意: 这移动的是 buttons 里的元素 (含方向盘 gp_wheel); 中心轮盘整组偏移是另一回事
        (wheel_x/wheel_y, 用 set_param)。"""
        d = _MOVE_DIRS.get(str(direction).strip().lower())
        if d is None:
            return {"ok": False, "error": "direction 须为 上/下/左/右 (up/down/left/right)"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = c.get("buttons", [])
        if not (0 <= index < len(buttons)):
            return {"ok": False, "error": f"index 越界: {index} (共 {len(buttons)} 个)"}
        try:
            step = float(cells) * (c.get("grid_size") or 100)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"cells 非法: {cells}"}
        b = buttons[index]
        bx, by = float(b.get("x") or 0), float(b.get("y") or 0)
        nx, ny = bx + d[0] * step, by + d[1] * step
        b["x"], b["y"] = nx, ny
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": index, "direction": direction,
                "cells": cells, "before": {"x": bx, "y": by}, "after": {"x": nx, "y": ny}}

    @staticmethod
    def set_button_geometry(index: int, x: float | None = None, y: float | None = None,
                            w: float | None = None, h: float | None = None,
                            name: str | None = None) -> dict:
        """绝对设置某元素的位置/尺寸 (x/y 屏幕中心原点坐标, 任意子集)。含方向盘 gp_wheel。"""
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = c.get("buttons", [])
        if not (0 <= index < len(buttons)):
            return {"ok": False, "error": f"index 越界: {index} (共 {len(buttons)} 个)"}
        b = buttons[index]
        before = {k: b.get(k) for k in ("x", "y", "w", "h")}
        changed = {}
        try:
            for k, v in (("x", x), ("y", y), ("w", w), ("h", h)):
                if v is not None:
                    b[k] = float(v)
                    changed[k] = b[k]
        except (TypeError, ValueError):
            return {"ok": False, "error": "x/y/w/h 须为数字"}
        if not changed:
            return {"ok": False, "error": "至少提供 x/y/w/h 之一"}
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": index,
                "before": before, "after": changed}

    @staticmethod
    def set_element_field(index: int, field: str, value, name: str | None = None) -> dict:
        """改某元素的任意字段 (含类型专有/高级字段: 摇杆 dead_zone/eight_way/mode/wasd_*、
        方向盘 control_mode/lt_*、按钮 hover_repeat_interval 等)。值按旧值类型自动纠正。
        结构字段 x/y/w/h 请用 set_button_geometry/move_button; type 不可改。
        常规绑定 (hover/lclick/name…) 用 set_button_binding 更稳。"""
        if field in _ELEMENT_STRUCTURAL:
            return {"ok": False, "error": f"{field} 是结构字段: x/y/w/h 用 set_button_geometry/"
                    "move_button, type 不可改"}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = c.get("buttons", [])
        if not (0 <= index < len(buttons)):
            return {"ok": False, "error": f"index 越界: {index} (共 {len(buttons)} 个)"}
        b = buttons[index]
        before = b.get(field)
        value = _coerce_to_type(value, before)  # 按旧值类型纠正 (bool/int/float/dict)
        b[field] = value
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "index": index,
                "field": field, "before": before, "after": value}
