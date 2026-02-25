"""
TEGG Touch 蛋挞 (PyQt6) - button_model.py
按钮配置数据模型 — 纯数据，不含任何运行时/UI 状态。
"""

from dataclasses import dataclass, field, asdict


@dataclass
class ButtonData:
    """按钮配置数据 — 纯数据，不含任何运行时/UI 状态

    旧版: 按钮是一个裸 dict，运行时字段混在其中
    新版: dataclass 明确定义字段，序列化/反序列化有类型保证
    """
    x: float = 0.0
    y: float = 0.0
    w: float = 100.0
    h: float = 100.0
    name: str = "按钮"
    btn_type: str = "normal"       # normal | center_band

    # 按键映射
    hover: str = ""
    lclick: str = ""
    rclick: str = ""
    mclick: str = ""
    wheelup: str = ""
    wheeldown: str = ""
    xbutton1: str = ""
    xbutton2: str = ""

    # 延迟配置
    hover_delay: int = 200         # ms, 0 = 立即触发
    hover_release_delay: int = 0   # ms, 0 = 立即释放

    def to_dict(self) -> dict:
        """序列化为 JSON dict（与旧格式完全兼容）"""
        d = asdict(self)
        # 字段名映射：btn_type → type（与旧格式兼容）
        d['type'] = d.pop('btn_type')
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'ButtonData':
        """从 JSON dict 反序列化（兼容旧格式）"""
        mapped = dict(d)
        if 'type' in mapped:
            mapped['btn_type'] = mapped.pop('type')

        # 只取 dataclass 中定义的字段，忽略旧版的运行时字段
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in mapped.items() if k in valid_fields}
        return cls(**filtered)
