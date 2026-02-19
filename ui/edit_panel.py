"""
TEGG Touch 蛋挞 - edit_panel.py
向后兼容的重导出层。实际实现已拆分到：
  - ui/widgets.py         通用 UI 组件
  - ui/profile_manager.py 方案管理弹窗
  - ui/toolbar.py         底部工具栏
  - ui/button_editor.py   按钮编辑弹窗
"""

# Re-export for backward compatibility
from ui.toolbar import create_toolbar_window, destroy_toolbar_window  # noqa: F401
from ui.button_editor import open_button_editor  # noqa: F401


def setup_edit_toolbar(frame, **kwargs):
    """已弃用，保留兼容。"""
    pass
