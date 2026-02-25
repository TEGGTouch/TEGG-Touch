"""
TEGG Touch 蛋挞 (PyQt6) - wheel_model.py
轮盘扇区 & 中心圆环 配置数据模型。
"""

from dataclasses import dataclass, asdict


@dataclass
class WheelSectorData:
    """轮盘扇区配置数据"""
    name: str = ""
    angle: float = 0.0
    hover: str = ""
    hover_delay: int = 200
    hover_release_delay: int = 0
    lclick: str = ""
    rclick: str = ""
    mclick: str = ""
    wheelup: str = ""
    wheeldown: str = ""
    xbutton1: str = ""
    xbutton2: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'WheelSectorData':
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class WheelRingData:
    """中心圆环按钮配置数据"""
    name: str = ""
    hover: str = ""
    hover_delay: int = 200
    hover_release_delay: int = 0
    lclick: str = ""
    rclick: str = ""
    mclick: str = ""
    wheelup: str = ""
    wheeldown: str = ""
    xbutton1: str = ""
    xbutton2: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'WheelRingData':
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})
