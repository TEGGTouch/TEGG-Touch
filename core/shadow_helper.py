"""
TEGG Touch - shadow_helper.py
全局给所有项目内弹窗 (QDialog 子类 + 内层有 *_container 命名的 QFrame) 装外发光阴影。
通过 QApplication 级 eventFilter 在 Show 事件时一次性注入, 不需要修改每个弹窗源码。

为了让阴影有空间渲染:
1. 把弹窗 outer layout 的边距从 0 → SHADOW_MARGIN
2. 弹窗 setFixedSize 增加 2 * SHADOW_MARGIN
3. 重新居中 (调用 _center_on_screen 或居中算法)
4. QGraphicsDropShadowEffect 应用到 *_container QFrame

每个弹窗只注入一次, 用 _shadow_installed 标记。
"""

from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtWidgets import QApplication, QDialog, QFrame, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor

# 阴影参数
SHADOW_MARGIN = 24      # 边距 (= 阴影最大半径预留)
SHADOW_BLUR = 40
SHADOW_OFFSET_Y = 6     # 向下偏移, 模拟光源在上
SHADOW_COLOR = QColor(0, 0, 0, 200)


class _ShadowInstaller(QObject):
    """QApplication 级 eventFilter, 检测 QDialog Show 事件, 注入阴影"""

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Show:
            return False
        if not isinstance(obj, QDialog):
            return False
        if getattr(obj, '_shadow_installed', False):
            return False

        try:
            self._install(obj)
            obj._shadow_installed = True
        except Exception:
            pass    # 不影响弹窗正常显示
        return False    # 不消费事件

    def _install(self, dlg: QDialog):
        # 1. 找到内层 *_container QFrame (项目约定命名)
        container = None
        for f in dlg.findChildren(QFrame):
            name = f.objectName() or ''
            if name.endswith('_container'):
                container = f
                break
        if container is None:
            return

        # 2. 加大 outer layout 边距给阴影留地方; 同时增大弹窗尺寸保持原内容大小
        lay = dlg.layout()
        if lay is not None:
            cm = lay.contentsMargins()
            extra_w = (SHADOW_MARGIN - cm.left()) + (SHADOW_MARGIN - cm.right())
            extra_h = (SHADOW_MARGIN - cm.top()) + (SHADOW_MARGIN - cm.bottom())
            lay.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN,
                                    SHADOW_MARGIN, SHADOW_MARGIN)
            if extra_w > 0 or extra_h > 0:
                sz = dlg.size()
                dlg.setFixedSize(sz.width() + max(0, extra_w),
                                  sz.height() + max(0, extra_h))
                # 居中: 优先调弹窗自己的 _center_on_screen, 否则手算
                if hasattr(dlg, '_center_on_screen') and callable(dlg._center_on_screen):
                    try:
                        dlg._center_on_screen()
                    except Exception:
                        self._fallback_center(dlg)
                else:
                    self._fallback_center(dlg)

        # 3. 应用阴影 effect
        eff = QGraphicsDropShadowEffect(container)
        eff.setBlurRadius(SHADOW_BLUR)
        eff.setOffset(0.0, float(SHADOW_OFFSET_Y))
        eff.setColor(SHADOW_COLOR)
        container.setGraphicsEffect(eff)

    @staticmethod
    def _fallback_center(dlg: QDialog):
        from PyQt6.QtCore import QRect
        ps = QApplication.primaryScreen()
        screen = ps.geometry() if ps else QRect(0, 0, 1920, 1080)
        dlg.move((screen.width() - dlg.width()) // 2,
                 (screen.height() - dlg.height()) // 2)


# 单例 (parent = QApplication 防止 GC)
_installer_singleton: _ShadowInstaller = None


def install_global_dialog_shadow(app: QApplication):
    """在 main 启动时调一次, 给所有 QDialog 自动加阴影"""
    global _installer_singleton
    if _installer_singleton is not None:
        return
    _installer_singleton = _ShadowInstaller(app)
    app.installEventFilter(_installer_singleton)
