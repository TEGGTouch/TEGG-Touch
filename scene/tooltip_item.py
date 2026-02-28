"""
TEGG Touch 蛋挞 (PyQt6) - tooltip_item.py
场景内自定义 Tooltip — 替代 Qt 原生 setToolTip()，在透明穿透窗口上可靠显示。

原生 setToolTip 在 WA_TranslucentBackground + WA_ShowWithoutActivating + WS_EX_NOACTIVATE
的透明覆盖窗口上无法可靠弹出，改用 QGraphicsObject 直接在场景中绘制。
"""

from PyQt6.QtWidgets import QGraphicsObject
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QBrush, QColor, QFont, QFontMetricsF

from core.i18n import t, get_font


# ── 图标字体检测 (与 edit_toolbar / overlay_scene 共用逻辑) ──
_ICON_FONT = None
_ICON_WARNING = "\uE7BA"   # Segoe Fluent Icons: Warning triangle

def _detect_icon_font():
    global _ICON_FONT
    if _ICON_FONT is not None:
        return _ICON_FONT
    from PyQt6.QtGui import QFontDatabase
    families = QFontDatabase.families()
    if "Segoe Fluent Icons" in families:
        _ICON_FONT = "Segoe Fluent Icons"
    elif "Segoe MDL2 Assets" in families:
        _ICON_FONT = "Segoe MDL2 Assets"
    else:
        _ICON_FONT = ""
    return _ICON_FONT


def build_edit_tooltip(data) -> str:
    """构建编辑模式 tooltip 文本 — 三处复用（TouchButton / WheelSector / WheelRing）

    - center_band: 只显示简化提示
    - 普通按钮/轮盘项: 显示全部字段（含空值）
    - 轮盘项(WheelSectorData/WheelRingData 无 btn_type): 末尾追加轮盘提示
    """
    # 回中带: 只显示简化提示
    if getattr(data, 'btn_type', None) == 'center_band':
        return t("btn_tooltip.center_band_tip")

    # 普通按钮和轮盘项: 显示全部字段（不论是否为空）
    lines = [f"{t('btn_tooltip.name')}: {data.name}"]
    for field, key in [
        ('hover', 'btn_tooltip.hover'),
        ('lclick', 'btn_tooltip.lclick'),
        ('rclick', 'btn_tooltip.rclick'),
        ('mclick', 'btn_tooltip.mclick'),
        ('xbutton1', 'btn_tooltip.xbutton1'),
        ('xbutton2', 'btn_tooltip.xbutton2'),
        ('wheelup', 'btn_tooltip.wheelup'),
        ('wheeldown', 'btn_tooltip.wheeldown'),
    ]:
        val = getattr(data, field, '')
        lines.append(f"{t(key)}: {val}")
    lines.append(f"{t('btn_tooltip.trigger_delay')}: {getattr(data, 'hover_delay', 0)}ms")
    lines.append(f"{t('btn_tooltip.release_delay')}: {getattr(data, 'hover_release_delay', 0)}ms")

    # 轮盘项(WheelSectorData/WheelRingData 没有 btn_type 属性): 追加轮盘提示
    if not hasattr(data, 'btn_type'):
        lines.append("")
        lines.append(t("btn_tooltip.wheel_hint"))

    return "\n".join(lines)


class TooltipItem(QGraphicsObject):
    """场景内 Tooltip — 编辑模式下跟随鼠标位置显示按钮配置信息。

    通过 shape() 返回空路径，使自身对鼠标事件完全透明，
    不影响下层 Item 的 hover/click 检测和智能穿透判定。
    """

    PADDING_X = 10
    PADDING_Y = 8
    OFFSET_X = 16
    OFFSET_Y = 16
    LINE_SPACING = 4
    FONT_SIZE = 9

    def __init__(self):
        super().__init__()
        self._lines = []
        self._rect = QRectF(0, 0, 0, 0)
        self._cached_font = None
        self._cached_fm = None
        self._cached_font_name = None

        self.setZValue(10000)
        self.setVisible(False)
        self.setAcceptHoverEvents(False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    # ── 公开接口 ──

    def _get_font_and_fm(self):
        """获取缓存的 QFont/QFontMetricsF（字体名变化时重建）"""
        fn = get_font()
        if fn != self._cached_font_name:
            self._cached_font_name = fn
            self._cached_font = QFont(fn, self.FONT_SIZE)
            self._cached_fm = QFontMetricsF(self._cached_font)
        return self._cached_font, self._cached_fm

    def show_text(self, text: str, scene_pos):
        """在 scene_pos 附近显示 tooltip 文本"""
        if not text:
            self.hide_text()
            return

        self._lines = text.split('\n')

        # 计算尺寸
        font, fm = self._get_font_and_fm()
        def _line_width(line):
            if line.startswith("\u26A0"):
                ifont = _detect_icon_font()
                if ifont:
                    icon_fm = QFontMetricsF(QFont(ifont, self.FONT_SIZE))
                    rest = line[1:].lstrip()
                    return icon_fm.horizontalAdvance(_ICON_WARNING) + 2 + fm.horizontalAdvance(rest)
            return fm.horizontalAdvance(line)
        max_w = max(_line_width(line) for line in self._lines)
        line_h = fm.height()
        total_h = line_h * len(self._lines) + self.LINE_SPACING * max(0, len(self._lines) - 1)

        self.prepareGeometryChange()
        self._rect = QRectF(
            0, 0,
            max_w + self.PADDING_X * 2,
            total_h + self.PADDING_Y * 2,
        )

        self._position_at(scene_pos)
        self.setVisible(True)
        self.update()

    def move_to(self, scene_pos):
        """仅更新位置，不重算文本/尺寸"""
        if self.isVisible():
            self._position_at(scene_pos)

    def hide_text(self):
        """隐藏 tooltip"""
        self.setVisible(False)

    # ── 内部方法 ──

    def _position_at(self, scene_pos):
        """定位 tooltip（偏移 + 边界修正）"""
        x = scene_pos.x() + self.OFFSET_X
        y = scene_pos.y() + self.OFFSET_Y

        scene = self.scene()
        if scene:
            sr = scene.sceneRect()
            if x + self._rect.width() > sr.right():
                x = scene_pos.x() - self._rect.width() - 5
            if y + self._rect.height() > sr.bottom():
                y = scene_pos.y() - self._rect.height() - 5

        self.setPos(x, y)

    # ── QGraphicsItem 接口 ──

    def boundingRect(self) -> QRectF:
        return self._rect

    def shape(self) -> QPainterPath:
        # 返回空路径 — 对鼠标事件完全透明，不阻挡下层 Item
        return QPainterPath()

    def paint(self, painter: QPainter, option, widget=None):
        if not self._lines:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.setBrush(QBrush(QColor("#1E1E2E")))
        painter.drawRoundedRect(self._rect, 6, 6)

        # 文字
        font, fm = self._get_font_and_fm()
        painter.setFont(font)
        painter.setPen(QColor("#E0E0E0"))
        line_h = fm.height()
        y = self.PADDING_Y + fm.ascent()

        for line in self._lines:
            if line.startswith("\u26A0"):
                # ⚠ 行: 用 Segoe Fluent Icons 渲染警告图标
                ifont = _detect_icon_font()
                if ifont:
                    icon_font = QFont(ifont, self.FONT_SIZE)
                    painter.setFont(icon_font)
                    painter.drawText(int(self.PADDING_X), int(y), _ICON_WARNING)
                    icon_w = QFontMetricsF(icon_font).horizontalAdvance(_ICON_WARNING)
                    painter.setFont(font)
                    rest = line[1:].lstrip()
                    painter.drawText(int(self.PADDING_X + icon_w + 2), int(y), rest)
                else:
                    painter.drawText(int(self.PADDING_X), int(y), line)
            else:
                painter.drawText(int(self.PADDING_X), int(y), line)
            y += line_h + self.LINE_SPACING
