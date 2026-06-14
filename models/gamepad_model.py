"""
TEGG Touch 蛋挞 — 手柄模式按钮配置数据模型

设计:
- 手柄键 (gp_button) 复用 ButtonData (hover/lclick/... 字段值带 "gp:" 前缀)
  → 不需要新 dataclass
- 摇杆 / 扳机 字段差异较大, 各自独立 dataclass

序列化兼容:
- to_dict() 把 btn_type → 'type', 与旧 profile 格式对齐
- from_dict() 反向, 并丢弃运行时字段
"""

from dataclasses import dataclass, asdict

from core.constants import (
    BTN_TYPE_GP_STICK, BTN_TYPE_GP_WHEEL,
    STICK_ID_LEFT,
    GP_WHEEL_DEFAULT_W, GP_WHEEL_DEFAULT_H,
)


@dataclass
class GamepadStickData:
    """摇杆按钮配置 — 圆形 ≥ 2x2 网格 + 鼠标其它按键作为额外触发源 (无 hover)"""
    x: float = 0.0
    y: float = 0.0
    w: float = 200.0
    h: float = 200.0
    name: str = ""
    btn_type: str = BTN_TYPE_GP_STICK
    stick_id: str = STICK_ID_LEFT          # 'L' | 'R'
    dead_zone: float = 0.10                # 死区半径占圆半径比例 (0~1)
    release_threshold_ratio: float = 1.5   # 鼠标距圆心 > R×ratio 释放
    sensitivity_curve: str = "linear"      # 'linear' | 'square'
    eight_way: bool = False                # 八方向锁定 (老 RPG 用)

    # 鼠标其它按键: 摇杆 active 时按下/抬起对应键, 触发该字段内容 (gp:X / gpmacro:X 等)
    # 跟 ButtonData 字段同名同语义, 但 stick 不需要 hover (鼠标始终在 stick 上)
    lclick: str = ""
    rclick: str = ""
    mclick: str = ""
    xbutton1: str = ""
    xbutton2: str = ""
    wheelup: str = ""
    wheeldown: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d['type'] = d.pop('btn_type')
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'GamepadStickData':
        mapped = dict(d)
        if 'type' in mapped:
            mapped['btn_type'] = mapped.pop('type')
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in mapped.items() if k in valid})


@dataclass
class GamepadWheelData:
    """方向盘配置 — 4×2 复合 item (LT 视觉条 + 中央圆盘 + RT 视觉条)
    一个 profile 最多一个 (toolbar toggle 控制)。
    Steering 走左摇杆 X 轴; LT/RT 三种控制方式 (互斥)。"""
    x: float = 0.0
    y: float = 0.0
    w: float = float(GP_WHEEL_DEFAULT_W)
    h: float = float(GP_WHEEL_DEFAULT_H)
    name: str = ""
    btn_type: str = BTN_TYPE_GP_WHEEL

    # Steering (左摇杆 X 轴)
    release_threshold_ratio: float = 1.5   # 鼠标距矩形中心 > w/2×ratio → 全部释放
    sensitivity_curve: str = "linear"      # 'linear' | 'square'

    # LT 控制方式 — 默认左右键 (LMB 加 / RMB 减)
    lt_mode: str = "buttons"               # 'scroll' | 'vertical' | 'buttons'
    lt_scroll_step: float = 0.05
    lt_vertical_pct: float = 0.5           # 0→1 所需 Y 位移 = 方向盘高度 × pct (默认 50%, 上限 80%)
    lt_buttons_ms: int = 100
    lt_buttons_step: float = 0.05

    # RT 控制方式 — 默认垂直位移
    rt_mode: str = "vertical"
    rt_scroll_step: float = 0.05
    rt_vertical_pct: float = 0.5
    rt_buttons_ms: int = 100
    rt_buttons_step: float = 0.05

    def to_dict(self) -> dict:
        d = asdict(self)
        d['type'] = d.pop('btn_type')
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'GamepadWheelData':
        mapped = dict(d)
        if 'type' in mapped:
            mapped['btn_type'] = mapped.pop('type')
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in mapped.items() if k in valid})


