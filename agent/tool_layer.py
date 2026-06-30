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

import logging
import time

from core import input_engine
from core import action_service
from core.constants import APP_PREFIX, GP_KEY_PREFIX, GP_LABEL_TO_KEY
from core import config_manager as cfg

logger = logging.getLogger(__name__)

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
        """给 agent 看的精简摘要: 按钮绑定一览 + 轮盘/语音/参数概况。"""
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = []
        for i, b in enumerate(c.get("buttons", [])):
            bind = {k: b.get(k) for k in ("hover", "lclick", "rclick", "mclick",
                                          "wheelup", "wheeldown", "xbutton1", "xbutton2")
                    if b.get(k)}
            buttons.append({"index": i, "name": b.get("name", ""),
                            "type": b.get("type", "normal"), "bindings": bind})
        voice = [{"phrase": v.get("phrase"), "keys": v.get("keys"),
                  "action": v.get("action")} for v in c.get("voice_commands", [])]
        return {
            "profile": name,
            "button_count": len(buttons),
            "buttons": buttons,
            "wheel_visible": c.get("wheel_visible"),
            "wheel_mode": c.get("wheel_mode"),
            "voice_enabled": c.get("voice_enabled"),
            "voice_commands": voice,
            "xmacros": [m.get("name") for m in c.get("xmacros", [])],
            "apps": [a.get("name") for a in c.get("apps", [])],
        }

    @staticmethod
    def set_button_binding(button_index: int, field: str, value: str,
                           name: str | None = None) -> dict:
        """改写某个按钮的一个绑定字段并保存。返回 before/after。"""
        if field not in _BUTTON_BINDING_FIELDS:
            return {"ok": False, "error": f"不允许的字段: {field}",
                    "allowed": sorted(_BUTTON_BINDING_FIELDS)}
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        buttons = c.get("buttons", [])
        if not (0 <= button_index < len(buttons)):
            return {"ok": False, "error": f"button_index 越界: {button_index} (共 {len(buttons)} 个)"}
        before = buttons[button_index].get(field)
        buttons[button_index][field] = value
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "button_index": button_index,
                "field": field, "before": before, "after": value}

    @staticmethod
    def set_param(key: str, value, name: str | None = None) -> dict:
        """改写 profile 顶层参数 (如 transparency / voice_enabled) 并保存。"""
        name = ConfigTools._resolve_name(name)
        c = cfg.load_profile(name)
        before = c.get(key)
        c[key] = value
        cfg.save_profile(name, c)
        return {"ok": True, "profile": name, "key": key,
                "before": before, "after": value}
