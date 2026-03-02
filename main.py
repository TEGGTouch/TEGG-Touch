"""
TEGG Touch 蛋挞 (PyQt6) - Entry Point
"""

import sys
import os
import json
import logging

# 确保工作目录为脚本/EXE 所在目录（无论从哪里启动）
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='teggtouch.log',
    filemode='w'
)
logger = logging.getLogger(__name__)

# ═══ i18n 初始化（必须在所有 UI 模块导入之前） ═══
from core.i18n import load_locale, t


def _detect_language():
    """从 settings/hotkeys.json 读取 language 字段，默认 zh-CN。"""
    try:
        hk_path = os.path.join(os.getcwd(), "settings", "hotkeys.json")
        if os.path.exists(hk_path):
            with open(hk_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("language", "zh-CN")
    except Exception:
        pass
    return "zh-CN"


load_locale(_detect_language())

# 依赖检查
try:
    import keyboard
except ImportError:
    msg = t("app.dep_missing_msg")
    print(msg)
    sys.exit(1)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from views.overlay_window import OverlayWindow


def _check_for_updates(parent):
    """启动后台更新检查，有新版本时弹窗提示。"""
    from core.update_checker import UpdateChecker
    from views.update_dialog import UpdateDialog

    checker = UpdateChecker(parent)

    def _on_update(version, url, body):
        dlg = UpdateDialog(version, url, body, parent)
        dlg.show()

    checker.update_available.connect(_on_update)
    checker.start()
    # 保持引用防止被 GC
    parent._update_checker = checker


def main():
    try:
        # Disable Qt6 high-DPI scaling to get 1:1 physical pixel mapping,
        # matching the original Tkinter app's coordinate system.
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

        app = QApplication(sys.argv)
        app.setApplicationName("TEGG Touch")
        app.setApplicationVersion("0.2.0")

        window = OverlayWindow()
        window.show()

        # 启动 3 秒后检查更新（避免阻塞启动流程）
        QTimer.singleShot(3000, lambda: _check_for_updates(window))

        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        print(t("app.error_msg", error=str(e)))


if __name__ == "__main__":
    main()
