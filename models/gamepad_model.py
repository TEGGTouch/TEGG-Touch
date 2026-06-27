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
    stick_id: str = STICK_ID_LEFT          # 'L' | 'R' (mode='analog' 时有效)
    mode: str = "analog"                   # 'analog'=线性摇杆 | 'wasd'=圆盘模拟方向键
    dead_zone: float = 0.10                # 死区半径占圆半径比例 (0~1)
    release_threshold_ratio: float = 1.5   # 鼠标距圆心 > R×ratio 释放
    sensitivity_curve: str = "linear"      # 'linear' | 'square' (仅 analog)
    eight_way: bool = False                # 八方向锁定 (老 RPG 用; 仅 analog)

    # WASD 模式: 圆盘 8 扇区 → 方向键, 斜向同时触发相邻两键 (可填任意键/组合键)
    wasd_up: str = "w"
    wasd_down: str = "s"
    wasd_left: str = "a"
    wasd_right: str = "d"

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
    release_threshold_ratio: float = 2.0   # 鼠标距矩形中心 > w/2×ratio → 全部释放 (默认 200%, UI 110%~300%)
    sensitivity_curve: str = "linear"      # 'linear' | 'square'
    max_rotation_deg: float = 180.0        # steering = ±1.0 时方向盘视觉旋转角度 (单边); UI 离散 90/180/270/360/720
    dead_zone: float = 0.10                # 中心死区 (X 轴): |val| < dz → steering=0; dz~1 重映射成 0~1

    # LT 控制方式 — 默认浮标点击 (左键锁定)
    lt_mode: str = "marker"                # 'scroll' | 'vertical' | 'buttons' | 'marker'
    lt_scroll_step: float = 0.05
    lt_vertical_pct: float = 0.5           # 0→1 所需 Y 位移 = 方向盘高度 × pct (默认 50%, 上限 80%)
    lt_buttons_ms: int = 100
    lt_buttons_step: float = 0.05
    lt_marker_pct: float = 0.5             # marker 模式: 同 vertical 含义
    lt_marker_button: str = "L"            # marker 模式: 用哪个鼠标键锁定 ('L' | 'R')
    lt_reverse: bool = False               # 逆向 (含义跟 mode 联动)

    # RT 控制方式 — 默认浮标点击 (右键锁定)
    rt_mode: str = "marker"
    rt_scroll_step: float = 0.05
    rt_vertical_pct: float = 0.5
    rt_buttons_ms: int = 100
    rt_buttons_step: float = 0.05
    rt_marker_pct: float = 0.5
    rt_marker_button: str = "R"
    rt_reverse: bool = False

    # 其他鼠标按键: wheel active 时, 未被 LT/RT 占用的鼠标键触发对应映射
    # 优先级低于 LT/RT (buttons 模式占左右键; marker 占其中一个; scroll 占滚轮)
    mouse_lclick: str = ""
    mouse_rclick: str = ""
    mouse_mclick: str = ""
    mouse_xbutton1: str = ""
    mouse_xbutton2: str = ""
    mouse_wheelup: str = ""
    mouse_wheeldown: str = ""

    # ── 操控模式 ──
    # 'easy' (默认) = mouse-as-car: 鼠标 X→A/D 键盘, Y 速度→RT 累加, 配置鼠标键→S 键盘
    # 'advanced' = 全套方向盘行为 (摇杆 LX + LT/RT 多模式)
    control_mode: str = "easy"
    # 注: 轻松模式转向是「增量」式 (dx=mx-last_mx → A/D), 无定点死区。
    # easy_steer_threshold = 「增量死区」: 平滑后移动量(px)超过此值才触发 A/D。
    easy_steer_threshold: float = 1.0       # easy: 触发 A/D 的最小移动量 (px, 越大越抗抖)
    easy_throttle_sensitivity: float = 0.005  # easy: 鼠标上移每 1px 累加多少 RT (0~1)
    # 触发/释放延迟 (ms): 类按钮 — fill 从 0 涨到 1(触发)按下 A/D, 退回 0(释放)松开;
    # 反向立即取消, 释放中再触发回填。让左右更平滑。
    easy_trigger_delay: int = 0             # easy: 触发延迟 (ms, 默认无)
    easy_release_delay: int = 500           # easy: 释放延迟 (ms, 默认 500)
    easy_brake_button: str = "L"            # easy: 哪个鼠标键触发 S 刹车; 'L'/'R'/'M'/'X1'/'X2'

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


