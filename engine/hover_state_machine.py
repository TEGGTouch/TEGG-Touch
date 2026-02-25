"""
TEGG Touch 蛋挞 (PyQt6) - hover_state_machine.py
统一悬停状态机 — 管理 hover 充能/激活/释放的完整生命周期。

旧版: 每个按钮/扇区各自用 _hover_enter_time / _hover_charged /
      _hover_release_time 等字段手动管理，代码重复 3 遍
新版: 一个状态机类，所有可交互元素各持有一个实例
"""

from enum import Enum
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class HoverState(Enum):
    IDLE = 'idle'
    CHARGING = 'charging'      # hover_delay > 0 时的充能阶段
    ACTIVE = 'active'          # hover 已激活，按键已按下
    RELEASING = 'releasing'    # hover_release_delay > 0 时的释放倒计时


class HoverStateMachine(QObject):
    """悬停状态机 — 管理 hover 充能/激活/释放的完整生命周期

    状态转换:
      IDLE → CHARGING → ACTIVE → RELEASING → IDLE
      (hover_delay == 0 时跳过 CHARGING 直接到 ACTIVE)
      (release_delay == 0 时跳过 RELEASING 直接到 IDLE)
    """

    # 信号
    activated = pyqtSignal()           # hover 充能完成，应触发按键
    deactivated = pyqtSignal()         # hover 释放完成，应释放按键
    charge_progress = pyqtSignal(float)   # 充能进度 0~1
    release_progress = pyqtSignal(float)  # 释放进度 1~0

    _TICK_INTERVAL = 16  # ~60fps

    def __init__(self, hover_delay_ms: int = 200, release_delay_ms: int = 0):
        super().__init__()
        self._state = HoverState.IDLE
        self._hover_delay = hover_delay_ms
        self._release_delay = release_delay_ms

        # 充能定时器
        self._charge_timer = QTimer(self)
        self._charge_timer.setInterval(self._TICK_INTERVAL)
        self._charge_elapsed = 0
        self._charge_timer.timeout.connect(self._on_charge_tick)

        # 释放定时器
        self._release_timer = QTimer(self)
        self._release_timer.setInterval(self._TICK_INTERVAL)
        self._release_elapsed = 0
        self._release_timer.timeout.connect(self._on_release_tick)

    @property
    def state(self) -> HoverState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state == HoverState.ACTIVE

    def enter(self):
        """鼠标进入 hover 区域"""
        if self._state == HoverState.RELEASING:
            # 重入：取消释放倒计时，直接恢复 ACTIVE
            self._release_timer.stop()
            self._state = HoverState.ACTIVE
            self.release_progress.emit(0.0)  # 清除进度条，避免与 hover 填充双层叠加
            return

        if self._state != HoverState.IDLE:
            return

        if self._hover_delay <= 0:
            # 无充能延迟，直接激活
            self._state = HoverState.ACTIVE
            self.activated.emit()
        else:
            # 开始充能
            self._state = HoverState.CHARGING
            self._charge_elapsed = 0
            self._charge_timer.start()

    def leave(self):
        """鼠标离开 hover 区域"""
        if self._state == HoverState.CHARGING:
            # 充能中离开 → 取消充能，回到 IDLE
            self._charge_timer.stop()
            self._state = HoverState.IDLE
            self.charge_progress.emit(0.0)
            return

        if self._state != HoverState.ACTIVE:
            return

        if self._release_delay <= 0:
            # 无释放延迟，直接释放
            self._state = HoverState.IDLE
            self.deactivated.emit()
        else:
            # 开始释放倒计时
            self._state = HoverState.RELEASING
            self._release_elapsed = 0
            self._release_timer.start()

    def reset(self):
        """强制重置到 IDLE（切换模式/隐藏按键时调用）"""
        was_active = self._state in (HoverState.ACTIVE, HoverState.RELEASING)
        self._charge_timer.stop()
        self._release_timer.stop()
        self._state = HoverState.IDLE
        self._charge_elapsed = 0
        self._release_elapsed = 0
        if was_active:
            self.deactivated.emit()

    def update_delays(self, hover_delay_ms: int, release_delay_ms: int):
        """动态更新延迟配置"""
        self._hover_delay = hover_delay_ms
        self._release_delay = release_delay_ms

    # ── 内部定时器回调 ──

    def _on_charge_tick(self):
        self._charge_elapsed += self._TICK_INTERVAL
        progress = min(1.0, self._charge_elapsed / max(1, self._hover_delay))
        self.charge_progress.emit(progress)

        if progress >= 1.0:
            self._charge_timer.stop()
            self._state = HoverState.ACTIVE
            self.activated.emit()
            self.charge_progress.emit(0.0)  # 清除充能条

    def _on_release_tick(self):
        self._release_elapsed += self._TICK_INTERVAL
        progress = max(0.0, 1.0 - self._release_elapsed / max(1, self._release_delay))
        self.release_progress.emit(progress)

        if progress <= 0.0:
            self._release_timer.stop()
            self._state = HoverState.IDLE
            self.deactivated.emit()
