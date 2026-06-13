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
    BTN_TYPE_GP_STICK, BTN_TYPE_GP_TRIGGER,
    STICK_ID_LEFT, TRIGGER_ID_LEFT,
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
class GamepadTriggerData:
    """扳机按钮配置 — 矩形, 横纵两种朝向"""
    x: float = 0.0
    y: float = 0.0
    w: float = 240.0
    h: float = 80.0
    name: str = ""
    btn_type: str = BTN_TYPE_GP_TRIGGER
    trigger_id: str = TRIGGER_ID_LEFT      # 'L' | 'R'
    orientation: str = "h"                 # 'h' (横) | 'v' (纵)
    end_ratio: float = 0.15                # 左右 (或上下) 端 0/1 方形占比

    def to_dict(self) -> dict:
        d = asdict(self)
        d['type'] = d.pop('btn_type')
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'GamepadTriggerData':
        mapped = dict(d)
        if 'type' in mapped:
            mapped['btn_type'] = mapped.pop('type')
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in mapped.items() if k in valid})
