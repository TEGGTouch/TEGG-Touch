"""
TEGG Touch i18n 翻译引擎

用法:
    from core.i18n import t, load_locale, get_lang
    load_locale("en")           # 启动时调用一次
    t("toolbar.add_button")     # → "+ Button"
    t("run.auto_center_on", key="F6")  # → "Center ON [F6]"
"""

import json
import os
import sys
import logging

logger = logging.getLogger(__name__)

_strings = {}       # 扁平化的翻译字典 {"run.stop": "Stop [{key}]", ...}
_current_lang = "en"

# APP_DIR: 与 constants.py 保持一致
if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _flatten(d, prefix=""):
    """将嵌套 dict 扁平化为 "a.b.c" 格式。"""
    items = {}
    for k, v in d.items():
        new_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten(v, new_key))
        else:
            items[new_key] = v
    return items


def load_locale(lang="en"):
    """加载语言包 JSON。

    Args:
        lang: 语言代码，如 "en" 或 "zh-CN"
    """
    global _strings, _current_lang
    _current_lang = lang
    locale_path = os.path.join(_APP_DIR, "locales", f"{lang}.json")

    if not os.path.exists(locale_path):
        logger.warning(f"Locale file not found: {locale_path}, falling back to en")
        locale_path = os.path.join(_APP_DIR, "locales", "en.json")

    try:
        with open(locale_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _strings = _flatten(raw)
        logger.info(f"Locale loaded: {lang} ({len(_strings)} keys)")
    except Exception as e:
        logger.error(f"Failed to load locale {lang}: {e}")
        _strings = {}


def t(msg_id, **kwargs):
    """翻译函数。

    用法:
        t("run.auto_center_on", key="F6") → "Center ON [F6]"
        缺失 key 返回 key 本身（不会崩溃）
    """
    text = _strings.get(msg_id, msg_id)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def get_lang():
    """返回当前语言代码。"""
    return _current_lang


def get_font():
    """根据当前语言返回合适的 UI 字体名。"""
    if _current_lang.startswith("zh"):
        return "Microsoft YaHei UI"
    return "Segoe UI"
