"""Background OSS update check. GitHub is not needed by the client."""

import json
import logging
import os
import time

from PyQt6.QtCore import QThread, pyqtSignal

from core.constants import APP_VERSION, APP_DIR
from core.update_manifest import (LATEST_URL, MAX_MANIFEST_BYTES, is_newer as _is_newer,
                                  open_update_url, parse_manifest)

logger = logging.getLogger(__name__)
_COOLDOWN_FILE = os.path.join(APP_DIR, "settings", "last_update_check.json")
_COOLDOWN_SECONDS = 24 * 60 * 60


def _should_check() -> bool:
    try:
        with open(_COOLDOWN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # A GitHub timestamp must not delay the first OSS check after migration.
        age = time.time() - data.get("last_check", 0)
        return data.get("source") != LATEST_URL or not 0 <= age < _COOLDOWN_SECONDS
    except (OSError, ValueError, TypeError, AttributeError):
        return True


def _save_check_timestamp():
    try:
        os.makedirs(os.path.dirname(_COOLDOWN_FILE), exist_ok=True)
        with open(_COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_check": time.time(), "source": LATEST_URL}, f)
    except OSError as e:
        logger.debug("Failed to save update check timestamp: %s", e)


def fetch_latest():
    with open_update_url(LATEST_URL) as response:
        raw = response.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("更新清单过大")
    return parse_manifest(json.loads(raw.decode("utf-8")))


class UpdateChecker(QThread):
    """force=True bypasses the daily cooldown for manual checks."""

    update_available = pyqtSignal(object)  # ReleaseInfo, including size + digest
    no_update_available = pyqtSignal()
    check_failed = pyqtSignal(str)

    def __init__(self, parent=None, force: bool = False):
        super().__init__(parent)
        self._force = force

    def run(self):
        if not self._force and not _should_check():
            return
        try:
            release = fetch_latest()
            _save_check_timestamp()
            if _is_newer(release.version, APP_VERSION):
                logger.info("New OSS release available: %s", release.version)
                self.update_available.emit(release)
            else:
                self.no_update_available.emit()
        except Exception as e:
            logger.info("OSS update check failed: %s", e)
            self.check_failed.emit(str(e))
