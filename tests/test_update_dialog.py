"""
更新弹窗样式预览 — 不联网，纯本地模拟。

用法:
    cd TEGGTouch-PyQt6
    python -m tests.test_update_dialog
"""
import sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

from core.i18n import load_locale
load_locale("en")  # 改成 "zh-CN" 可测中文

from PyQt6.QtWidgets import QApplication
from views.update_dialog import UpdateDialog

app = QApplication(sys.argv)

dlg = UpdateDialog(
    version="0.3.0",
    url="https://github.com/TEGGTouch/TEGG-Touch/releases/tag/v0.3.0",
    body="- 新增语音识别引擎切换\n- 修复回中带偶现闪退\n- 优化按钮编辑器响应速度",
)
dlg.show()

sys.exit(app.exec())
