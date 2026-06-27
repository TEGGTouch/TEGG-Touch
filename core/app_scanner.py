"""
TEGG Touch 蛋挞 — 本地应用扫描 (app_scanner.py)

扫描 Windows 开始菜单的快捷方式 (.lnk) 作为「可启动应用」候选, 供
语音/按键/摇杆/方向盘/宏 配置 app:<名称> 触发启动。

设计:
- 数据源: 开始菜单 (全局 + 当前用户) 递归找 *.lnk —— 覆盖绝大多数游戏/软件。
- 启动: 直接对 .lnk 走 os.startfile, 由 Windows 解析快捷方式, 无需解析二进制。
- 缓存: settings/apps_cache.json, 避免每次开弹窗重扫; 提供 force 重扫。
- 应用池 (apps): 随 profile 存储 [{name, path}]; 加载/导入/复制时 validate_apps
  丢弃 path 失效的条目 (本机不匹配 → 丢弃)。
- 解析 app:<name>: 先查 profile 池, 再回退全局扫描缓存。
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

_START_MENU_DIRS = [
    os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                 "Microsoft", "Windows", "Start Menu", "Programs"),
    os.path.join(os.environ.get("APPDATA", ""),
                 "Microsoft", "Windows", "Start Menu", "Programs"),
]

_CACHE_FILE = os.path.join("settings", "apps_cache.json")

# 名称含这些关键词的快捷方式跳过 (卸载/帮助/官网等非启动项)
_SKIP_KEYWORDS = (
    "uninstall", "卸载", "readme", "read me", "help", "帮助", "说明",
    "website", "官网", "homepage", "setup", "安装", "update", "更新",
    "documentation", "文档", "license",
)


def scan_apps() -> list[dict]:
    """扫描开始菜单 .lnk → [{name, path}], 去重 + 过滤 + 按名排序。"""
    found: dict[str, dict] = {}
    for base in _START_MENU_DIRS:
        if not base or not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith(".lnk"):
                    continue
                name = os.path.splitext(fn)[0]
                low = name.lower()
                if any(k in low for k in _SKIP_KEYWORDS):
                    continue
                path = os.path.join(root, fn)
                if low not in found:
                    found[low] = {"name": name, "path": path}
    apps = sorted(found.values(), key=lambda a: a["name"].lower())
    logger.info("扫描到本地应用 %d 个", len(apps))
    return apps


def get_apps(force: bool = False) -> list[dict]:
    """取应用列表: 默认读缓存, 无缓存或 force 时重扫并写缓存。"""
    if not force:
        cached = _load_cache()
        if cached:
            return cached
    apps = scan_apps()
    _save_cache(apps)
    return apps


def _load_cache() -> list[dict] | None:
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        apps = data.get("apps")
        return apps if isinstance(apps, list) else None
    except Exception:
        return None


def _save_cache(apps: list[dict]):
    try:
        os.makedirs("settings", exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"apps": apps}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("写应用缓存失败: %s", e)


def validate_apps(apps) -> list[dict]:
    """丢弃 path 不存在的条目 —— 加载/导入/复制 时清理本机不匹配项。"""
    if not isinstance(apps, list):
        return []
    out = []
    for a in apps:
        if isinstance(a, dict):
            p = a.get("path")
            if p and os.path.exists(p):
                out.append({"name": a.get("name", ""), "path": p})
    return out


def find_app_path(name: str, pool=None) -> str | None:
    """解析 app:<name> → 启动路径。先查 profile 池, 再回退全局扫描缓存。"""
    if not name:
        return None
    for a in (pool or []):
        if isinstance(a, dict) and a.get("name") == name:
            p = a.get("path")
            if p and os.path.exists(p):
                return p
    for a in (_load_cache() or []):
        if a.get("name") == name:
            p = a.get("path")
            if p and os.path.exists(p):
                return p
    return None
