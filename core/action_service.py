"""
TEGGTouch 蛋挞 — Headless 动作服务 (G1)

从 RunController 抽出的纯逻辑: 宏执行 / 应用启动 / 屏幕回中。无 Qt 依赖,
供「运行时(RunController)」与「agent 工具层」共用同一份实现, 消除重复。

设计:
- run_macro 不自带线程, 调用方决定是否放进后台线程; 通过注入的
  trigger_fn / is_active 与具体执行后端解耦 (运行时用 _smart_trigger,
  agent 用 ControlTools.run_keys)。
- 回中只处理 headless 可解析的 'screen' (主屏中心); wheel/stick/center_ring
  依赖运行中的窗口几何, 不在此处 (由 RunController 自己解析)。
"""

from __future__ import annotations

import ctypes
import logging
import os
import time

from core.app_scanner import find_app_path

logger = logging.getLogger(__name__)


# ── 宏 ──────────────────────────────────────────────────────────

def find_macro(config: dict, name: str, pool: str = "kb") -> dict | None:
    """从 config 查找宏。pool='x' 查 xmacros(统一池), 'gp' 查 gp_macros, 余查 macros。"""
    field = {"x": "xmacros", "gp": "gp_macros"}.get(pool, "macros")
    for m in (config or {}).get(field, []):
        if m.get("name") == name:
            return m
    return None


def run_macro(macro_data: dict, trigger_fn, is_active=None) -> int:
    """同步执行宏步骤。返回已执行的步骤数。

    Args:
        macro_data: {"name", "repeat", "steps":[...]}, 步骤支持:
            {"type":"key","key":"a+b","action":"click"} /
            {"type":"delay","ms":100} / 旧格式 {"keys","action","delay"}
        trigger_fn: 回调 (keys: str, action: str) — action ∈ click/press/release
        is_active:  可选回调, 返回 False 时中断 (运行时退出 run 模式用)

    调用方若不想阻塞, 自行把本函数放进后台线程。
    """
    steps = macro_data.get("steps", [])
    repeat = max(1, macro_data.get("repeat", 1))
    if not steps:
        return 0
    done = 0
    for _ in range(repeat):
        for step in steps:
            if is_active is not None and not is_active():
                return done
            stype = step.get("type", "key")
            if stype == "delay":
                ms = step.get("ms", 50)
                if ms > 0:
                    time.sleep(ms / 1000.0)
            else:
                keys = step.get("key", "") or step.get("keys", "")
                act = step.get("action", "click")
                if keys:
                    trigger_fn(keys, act)
                delay = step.get("delay", 0)
                if delay > 0:
                    time.sleep(delay / 1000.0)
            done += 1
    return done


# ── 应用启动 ────────────────────────────────────────────────────

def resolve_app_path(name: str, apps: list | None) -> str | None:
    """app:<name> → 启动路径 (先 profile apps 池, 再回退全局扫描缓存)。"""
    return find_app_path(name, apps or [])


def launch_app(path: str) -> bool:
    """启动本地应用 (os.startfile 解析 .lnk/.exe)。成功返回 True。"""
    if not path:
        return False
    try:
        os.startfile(path)
        logger.info("启动应用: %s", path)
        return True
    except Exception as e:
        logger.warning("启动应用失败 (%s): %s", path, e)
        return False


# ── 回中 (仅 headless 可解析的主屏中心) ─────────────────────────

def screen_center() -> tuple[int, int]:
    """主屏几何中心 (屏幕像素)。"""
    u = ctypes.windll.user32
    return (u.GetSystemMetrics(0) // 2, u.GetSystemMetrics(1) // 2)
