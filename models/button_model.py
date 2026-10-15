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
    # 回中带专用: 回中目标 (screen=屏幕中心 | center_ring | wheel | stick:<名称>)
    recenter_target: str = "screen"

    # 按键映射
    hover: str = ""
    lclick: str = ""
    rclick: str = ""
    mclick: str = ""
    wheelup: str = ""
    wheeldown: str = ""
    xbutton1: str = ""
    xbutton2: str = ""

    # 延迟配置 (悬停触发模式)
    hover_delay: int = 200         # ms, 0 = 立即触发
    hover_release_delay: int = 0   # ms, 0 = 立即释放
    # 触发间隔(ms): 0=激活时只发一次 down; >0=按住期间每隔该毫秒补发一次 down
    # (方案A: 模拟键盘长按自动重复, 键始终按住, 松开时才 up)
    hover_repeat_interval: int = 0

    # 悬停模式: 'trigger' (按住型, 离开即松) | 'toggle' (开关型, 再次 hover 才松)
    hover_mode: str = "trigger"
    # 悬停开关模式独立字段 (与 hover/hover_delay 互不覆盖)
    hover_toggle: str = ""
    hover_toggle_delay: int = 200          # 开启时触发延迟
    hover_toggle_release_delay: int = 0    # 关闭时触发延迟 (第二次 hover 到松开)
    hover_toggle_repeat_interval: int = 0  # 触发间隔(ms), 同上, 用于开关模式

    # 快捷切换按钮: 每种输入独立保存 fixed/cycle 和有序方案列表。
    switch_id: str = ""
    profile_actions: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.btn_type == 'profile_switch':
            from core.profile_switch import normalize_actions, TRIGGER_FIELDS
            from uuid import uuid4
            self.switch_id = self.switch_id or uuid4().hex
            self.profile_actions = normalize_actions(self.profile_actions)
            self.hover_mode = 'trigger'
            self.hover_release_delay = self.hover_repeat_interval = 0
            # 复用现有点击/滚轮/侧键检测。标记只路由动作，不发送键盘输入。
            for key in TRIGGER_FIELDS:
                setattr(self, key, f'profile-switch:{key}' if key in self.profile_actions else '')

    def to_dict(self) -> dict:
        """序列化为 JSON dict（与旧格式完全兼容）"""
        d = asdict(self)
        # 字段名映射：btn_type → type（与旧格式兼容）
        d['type'] = d.pop('btn_type')
        if self.btn_type != 'profile_switch':
            d.pop('switch_id')
            d.pop('profile_actions')
        else:
            from core.profile_switch import TRIGGER_FIELDS
            for key in TRIGGER_FIELDS:
                d[key] = ''
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
