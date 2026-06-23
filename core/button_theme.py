"""
TEGG Touch 蛋挞 (PyQt6) - button_theme.py
按钮配色「单一色源」运行时主题。

三组配色 (per-profile 可调): keyboard(按键+中心轮盘) / gamepad(手柄+摇杆) / center_band(回中带)。
用户每组只调「一个基色」(= 描边/边框色), 填充/字色/摇杆小球按基色派生成系列。
默认值像素级等于历史硬编码色; 仅当用户改了基色才走 HSL 派生。

不变色 (不归本模块管): 触发反馈色(active/hover)、阈值区域、提醒/警告 —— 仍在各 item 内硬编码。
"""

from PyQt6.QtGui import QColor

GROUPS = ('keyboard', 'gamepad', 'center_band')

# 每组「基色」默认值 (= 边框/描边色, 用户取色器调的就是它)
DEFAULT_BUTTON_COLORS = {
    'keyboard':    '#555555',
    'gamepad':     '#3B82F6',
    'center_band': '#176F2C',
}

# 显式默认族 (保证默认像素级一致, 与各 item 历史硬编码完全相同)
_DEFAULT_FAMILY = {
    'keyboard':    {'fill': '#111111', 'border': '#555555', 'text': '#FFFFFF'},
    'gamepad':     {'fill': '#1A1E2E', 'border': '#3B82F6', 'text': '#93C5FD',
                    'ball': '#0284C7'},
    'center_band': {'fill': '#0A2E12', 'border': '#176F2C', 'text': '#4ADE80'},
}


def derive_shades(base: str) -> dict:
    """通用: 一个基色 → {fill(压暗), border(=基色), text(提亮)}。无像素级默认。"""
    c = QColor(base) if base else QColor('#3B82F6')
    if not c.isValid():
        c = QColor('#3B82F6')
    h, s, _l, _a = c.getHslF()
    if h < 0:
        h = 0.0
    border = c.name(QColor.NameFormat.HexRgb).upper()
    fill = QColor.fromHslF(h, s, 0.11, 1.0).name(QColor.NameFormat.HexRgb).upper()
    text = QColor.fromHslF(h, min(1.0, s * 0.6), 0.80, 1.0).name(QColor.NameFormat.HexRgb).upper()
    return {'fill': fill, 'border': border, 'text': text}


def derive_family(group: str, base: str | None) -> dict:
    """基色 → 整组配色族 {fill, border, text[, ball]}。

    base 为空或等于该组默认基色 → 返回显式默认族 (像素级一致);
    否则按 HSL 派生: border=base, fill=压暗, text=提亮。
    """
    if group not in _DEFAULT_FAMILY:
        group = 'keyboard'
    if not base or base.upper() == DEFAULT_BUTTON_COLORS[group].upper():
        return dict(_DEFAULT_FAMILY[group])
    c = QColor(base)
    if not c.isValid():
        return dict(_DEFAULT_FAMILY[group])
    h, s, _l, _a = c.getHslF()
    if h < 0:                       # 灰色 (achromatic) → hue 取 0, 饱和度本就 0
        h = 0.0
    border = c.name(QColor.NameFormat.HexRgb).upper()
    fill = QColor.fromHslF(h, s, 0.11, 1.0).name(QColor.NameFormat.HexRgb).upper()
    text = QColor.fromHslF(h, min(1.0, s * 0.6), 0.80, 1.0).name(QColor.NameFormat.HexRgb).upper()
    fam = {'fill': fill, 'border': border, 'text': text}
    if group == 'gamepad':
        fam['ball'] = border
    return fam


# 方向盘单独一个色 (来自 wheel_style.color, 非 button_colors); 默认蓝
DEFAULT_WHEEL_BASE = '#3B82F6'

# 运行时已解析的配色族 (overlay 在 profile 加载 / 设置保存后调 set_button_colors 更新)
_current = {g: dict(_DEFAULT_FAMILY[g]) for g in GROUPS}
_current_wheel = derive_shades(DEFAULT_WHEEL_BASE)


def set_button_colors(colors: dict | None):
    """colors = {group: base_hex}; None/缺省 → 该组用默认。"""
    colors = colors or {}
    for g in GROUPS:
        _current[g] = derive_family(g, colors.get(g))


def set_wheel_color(base: str | None):
    """方向盘基色 → 派生族 (描边/压暗填充/提亮字)。"""
    global _current_wheel
    _current_wheel = derive_shades(base or DEFAULT_WHEEL_BASE)


def wheel() -> dict:
    return _current_wheel


def family(group: str) -> dict:
    return _current.get(group, _DEFAULT_FAMILY['keyboard'])


def keyboard() -> dict:
    return _current['keyboard']


def gamepad() -> dict:
    return _current['gamepad']


def center_band() -> dict:
    return _current['center_band']
