"""
TEGG Touch - update_checker.py
后台检查 GitHub Releases 是否有新版本。

使用 urllib (stdlib) 请求 GitHub API，24 小时内不重复检查。
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error

from PyQt6.QtCore import QThread, pyqtSignal

from core.constants import APP_VERSION, APP_DIR

logger = logging.getLogger(__name__)

# GitHub Releases API
_GITHUB_API_URL = "https://api.github.com/repos/TEGGTouch/TEGG-Touch/releases/latest"
_REQUEST_TIMEOUT = 5  # seconds

# 冷却文件: 24 小时内不重复检查
_COOLDOWN_FILE = os.path.join(APP_DIR, "settings", "last_update_check.json")
_COOLDOWN_SECONDS = 24 * 60 * 60


def _parse_version(tag: str) -> tuple:
    """将 'v0.2.1' 或 '0.2.1' 解析为 (0, 2, 1) 元组，解析失败返回 (0,)。"""
    tag = tag.strip().lstrip("vV")
    try:
        return tuple(int(x) for x in tag.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _is_newer(remote_tag: str, local_version: str) -> bool:
    """remote_tag > local_version ?"""
    return _parse_version(remote_tag) > _parse_version(local_version)


def _should_check() -> bool:
    """检查冷却文件，判断是否需要请求 API。"""
    try:
        if os.path.exists(_COOLDOWN_FILE):
            with open(_COOLDOWN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            last_ts = data.get("last_check", 0)
            if time.time() - last_ts < _COOLDOWN_SECONDS:
                return False
    except Exception:
        pass
    return True


def _save_check_timestamp():
    """记录本次检查时间。"""
    try:
        os.makedirs(os.path.dirname(_COOLDOWN_FILE), exist_ok=True)
        with open(_COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_check": time.time()}, f)
    except Exception as e:
        logger.debug(f"Failed to save update check timestamp: {e}")


class UpdateChecker(QThread):
    """后台线程: 检查 GitHub 最新 Release。

    Signals:
        update_available(version, url, body)  — 有新版本时发射
    """

    update_available = pyqtSignal(str, str, str)  # version, html_url, body

    def run(self):
        if not _should_check():
            logger.debug("Update check skipped (cooldown)")
            return

        try:
            req = urllib.request.Request(
                _GITHUB_API_URL,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": f"TEGGTouch/{APP_VERSION}",
                },
            )
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            tag = data.get("tag_name", "")
            html_url = data.get("html_url", "")
            body = data.get("body", "")

            _save_check_timestamp()

            if _is_newer(tag, APP_VERSION):
                version_str = tag.lstrip("vV")
                logger.info(f"New version available: {version_str}")
                self.update_available.emit(version_str, html_url, body)
            else:
                logger.debug(f"Already up to date ({APP_VERSION})")

        except urllib.error.URLError as e:
            logger.debug(f"Update check failed (network): {e}")
        except Exception as e:
            logger.debug(f"Update check failed: {e}")
