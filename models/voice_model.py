"""
TEGG Touch (PyQt6) - voice_model.py
语音指令配置数据模型 — 纯数据，不含运行时状态。
"""

from dataclasses import dataclass, asdict


@dataclass
class VoiceCommandData:
    """语音指令配置数据

    phrase:  触发短语（如 "开火"、"fire"）
    keys:    对应按键字符串（如 "space"、"ctrl+a"），格式同按钮映射
    action:  触发动作类型 — "click" | "press" | "release"
             click   = 按下后立即释放（tap）
             press   = 按下并保持（需要再次语音触发 release 释放）
             release = 释放之前 press 的按键
    """
    phrase: str = ""
    keys: str = ""
    action: str = "click"  # click | press | release

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'VoiceCommandData':
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)
