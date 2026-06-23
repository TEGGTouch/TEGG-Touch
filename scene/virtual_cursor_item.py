"""
TEGG Touch 蛋挞 (PyQt6) - virtual_cursor_item.py
屏幕中心十字准星 — 跟踪实际光标或固定在中心。
SVG 实时渲染: 按用户配置的 stroke/fill/scale 替换 SVG 字符串后渲染到 QPixmap。
"""

import os
import re

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import QRectF, QTimer, Qt, QByteArray
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QColor, QCursor, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from core.constants import APP_DIR, DEFAULT_CURSOR_STYLES, CURSOR_BASE_SIZE, BALL_BASE_SIZE
from core.system_tuning import frame_interval_ms

# SVG viewBox 比例 (左上指针, 非正方形)
CURSOR_VIEWBOX_W = 27
CURSOR_VIEWBOX_H = 36


# ── SVG 层 (通用, 3 种状态共用; fill 色用替换占位符) ──
# 各层默认色: base=#FFCB31 (黄, 被 fill 替换), stroke=#FFFFFF (白, 被 stroke 替换),
# gradient 不替换 (永远是 30% 半透明白)
_LAYER_FILES = {
    'base':     ('cursor_base.svg',     '#FFCB31'),  # 底色, fill 替换
    'gradient': ('cursor_gradient.svg', None),       # 渐变蒙版, 不替换
    'stroke':   ('cursor_stroke.svg',   '#FFFFFF'),  # 描边, stroke 替换
}

# 层 SVG 原文缓存
_LAYER_TEXT_CACHE: dict = {}
# 渲染缓存 (key: (fill, stroke, size_px) → QPixmap)
_RENDER_CACHE: dict = {}


def _load_layer_text(layer: str) -> str | None:
    if layer in _LAYER_TEXT_CACHE:
        return _LAYER_TEXT_CACHE[layer]
    filename = _LAYER_FILES[layer][0]
    path = os.path.join(APP_DIR, 'assets', filename)
    if not os.path.exists(path):
        _LAYER_TEXT_CACHE[layer] = None
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception:
        text = None
    _LAYER_TEXT_CACHE[layer] = text
    return text


def _recolor_svg(svg_text: str, old_hex: str, new_hex: str) -> str:
    if not old_hex or old_hex.upper() == new_hex.upper():
        return svg_text
    pattern = re.compile(
        r'(fill\s*=\s*["\'])' + re.escape(old_hex) + r'(["\'])',
        re.IGNORECASE)
    return pattern.sub(r'\g<1>' + new_hex + r'\g<2>', svg_text)


def render_cursor_pixmap(cursor_type: str, style: dict,
                          base_size: int = CURSOR_BASE_SIZE) -> QPixmap | None:
    """按 style 渲染光标三层 SVG (底色 + 渐变 + 描边) → QPixmap。

    cursor_type 不再决定形状 (3 种状态共用同一组层), 仅用于读默认色兜底。
    """
    default = DEFAULT_CURSOR_STYLES.get(cursor_type, {})
    fill = style.get('fill', default.get('fill', '#000000'))
    stroke = style.get('stroke', default.get('stroke', '#FFFFFF'))
    scale = float(style.get('scale', 1.0))
    # base_size 是高度的 1x 参考; 宽度按 viewBox 比例 (27:36)
    h_px = max(1, int(round(base_size * scale)))
    w_px = max(1, int(round(h_px * CURSOR_VIEWBOX_W / CURSOR_VIEWBOX_H)))

    cache_key = (fill.upper(), stroke.upper(), w_px, h_px)
    if cache_key in _RENDER_CACHE:
        return _RENDER_CACHE[cache_key]

    pm = QPixmap(w_px, h_px)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # 按 base → gradient → stroke 顺序叠加
    color_map = {'base': fill, 'gradient': None, 'stroke': stroke}
    for layer in ('base', 'gradient', 'stroke'):
        txt = _load_layer_text(layer)
        if not txt:
            continue
        default_hex = _LAYER_FILES[layer][1]
        new_hex = color_map[layer]
        if default_hex and new_hex:
            txt = _recolor_svg(txt, default_hex, new_hex)
        renderer = QSvgRenderer(QByteArray(txt.encode('utf-8')))
        renderer.render(painter, QRectF(0, 0, w_px, h_px))

    painter.end()
    _RENDER_CACHE[cache_key] = pm
    return pm


def clear_cursor_render_cache():
    """清空渲染缓存 (用户保存新配色时调用)。"""
    _RENDER_CACHE.clear()


class VirtualCursorItem(QGraphicsItem):
    """屏幕中心的十字准星 / 自定义光标。"""

    def __init__(self, cursor_type='cursor', style: dict | None = None):
        super().__init__()
        self.setZValue(100)  # 始终在最上层

        self._cursor_type = cursor_type  # 'cursor' | 'cursor_off' | 'cursor_block'
        self._shape = 'arrow'            # 'arrow' | 'ball'
        self._style = dict(style) if style else dict(
            DEFAULT_CURSOR_STYLES.get(cursor_type, {}))
        self._pixmap: QPixmap | None = None
        self._w = int(CURSOR_BASE_SIZE * CURSOR_VIEWBOX_W / CURSOR_VIEWBOX_H)
        self._h = CURSOR_BASE_SIZE
        self._hx = 0.0   # 热点偏移 (arrow: 左上角=0; ball: 圆心 → -w/2,-h/2)
        self._hy = 0.0

        self._refresh_pixmap()

        # 位置跟踪定时器 (跟随显示器刷新率)
        self._tracker = QTimer()
        self._tracker.setInterval(frame_interval_ms())
        self._tracker.timeout.connect(self._update_pos)

    def _refresh_pixmap(self):
        """按当前 shape + style 重新渲染 pixmap, 更新 bounding box 尺寸与热点。"""
        scale = float(self._style.get('scale', 1.0))
        if self._shape == 'ball':
            pm, d = self._render_ball()
            self._pixmap = pm
            self.prepareGeometryChange()
            self._w = self._h = d
            # 圆心对齐光标 → 整体左上偏移半径
            self._hx = -d / 2.0
            self._hy = -d / 2.0
        else:
            pm = render_cursor_pixmap(self._cursor_type, self._style)
            self._pixmap = pm if pm and not pm.isNull() else None
            self.prepareGeometryChange()
            self._h = max(1, int(round(CURSOR_BASE_SIZE * scale)))
            self._w = max(1, int(round(self._h * CURSOR_VIEWBOX_W / CURSOR_VIEWBOX_H)))
            self._hx = 0.0   # 箭头尖即左上角, 无偏移
            self._hy = 0.0
        self.update()

    def _render_ball(self):
        """渲染半透明实心圆 → (QPixmap, 直径px)。颜色取 style.color + style.alpha。"""
        color = self._style.get('color', '#000000')
        alpha = max(0.0, min(1.0, float(self._style.get('alpha', 0.6))))
        scale = float(self._style.get('scale', 1.0))
        d = max(2, int(round(BALL_BASE_SIZE * scale)))
        pm = QPixmap(d, d)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(color)
        c.setAlphaF(alpha)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, d, d)
        p.end()
        return pm, d

    def set_shape(self, shape: str):
        """切换光标形状 ('arrow' | 'ball')。"""
        new_shape = 'ball' if shape == 'ball' else 'arrow'
        if new_shape != self._shape:
            self._shape = new_shape
            self._refresh_pixmap()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def shape(self):
        """返回空路径 → scene.itemAt() 不会命中虚拟光标，穿透到下方的按钮"""
        return QPainterPath()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._pixmap and not self._pixmap.isNull():
            painter.drawPixmap(0, 0, self._w, self._h, self._pixmap)
        else:
            # SVG 缺失时的兜底十字准星
            s = self._h // 2
            painter.setPen(QPen(QColor("#FF0000"), 2))
            painter.drawLine(0, s, s * 2, s)
            painter.drawLine(s, 0, s, s * 2)
            painter.drawEllipse(s // 2, s // 2, s, s)

    def set_cursor_type(self, cursor_type: str):
        """切换光标类型 (穿透模式切换时)。"""
        self._cursor_type = cursor_type
        self._refresh_pixmap()

    def set_style(self, style: dict):
        """应用新 style (用户保存配色后调用)。"""
        self._style = dict(style) if style else {}
        self._refresh_pixmap()

    def apply_styles_map(self, styles_map: dict, current_type: str | None = None):
        """从 cursor_styles 字典中提取当前类型的 style 并应用。"""
        if current_type:
            self._cursor_type = current_type
        self._style = dict(styles_map.get(self._cursor_type, {}))
        self._refresh_pixmap()

    def apply_shape_and_style(self, shape: str, styles_map: dict,
                              current_type: str | None = None):
        """一次性设置形状(arrow/ball) + 当前穿透类型的样式, 只刷新一次。"""
        self._shape = 'ball' if shape == 'ball' else 'arrow'
        if current_type:
            self._cursor_type = current_type
        self._style = dict(styles_map.get(self._cursor_type, {}))
        self._refresh_pixmap()

    def start_tracking(self):
        """开始跟踪光标位置"""
        self._tracker.start()
        self.setVisible(True)

    def stop_tracking(self):
        """停止跟踪"""
        self._tracker.stop()
        self.setVisible(False)

    def _update_pos(self):
        """更新位置到当前鼠标坐标（通过 view 做 global→scene 坐标变换）"""
        scene = self.scene()
        if scene is None:
            return
        views = scene.views()
        if not views:
            return
        view = views[0]
        global_pos = QCursor.pos()
        view_pos = view.mapFromGlobal(global_pos)
        scene_pos = view.mapToScene(view_pos)
        # 加热点偏移: 箭头(0,0) 左上对齐; 圆球(-r,-r) 圆心对齐光标顶点
        self.setPos(scene_pos.x() + self._hx, scene_pos.y() + self._hy)
