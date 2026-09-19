"""
TEGG Touch - 悬停状态机「自愈重入」回归测试

用法:
    cd TEGGTouch-PyQt6
    python -m tests.test_hover_rearm

复现的线上问题:
    运行模式下悬浮概率不触发 (点击正常, 鼠标移出再移回就好)。
    根因是 hover 状态机曾有两个驱动源 —— RunController 的坐标轮询, 和 Qt 自己的
    hoverEnter/LeaveEvent。智能穿透每帧切 WS_EX_TRANSPARENT, Windows 随之补发
    WM_MOUSELEAVE; 这条消息可能晚几帧才被派发, 于是「轮询刚 enter() 起了充能,
    一条过期的 hoverLeaveEvent 立刻把它打回 IDLE」。轮询是边沿触发的
    (active_item != prev_item 才 enter), 之后再也不补 enter → 悬浮就哑了。

本测试只验证轮询侧的兜底 (_rearm_stale_hover): 不管谁把状态机清空,
光标还在按钮上就应该在下一帧重新开始充能。
"""

import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication              # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer           # noqa: E402

from engine.hover_state_machine import HoverStateMachine, HoverState  # noqa: E402
from engine.run_controller import RunController       # noqa: E402


class _FakeData:
    name = '防御'


class _FakeItem:
    """只带 _hover_sm + data 的假 item, 够 _rearm_stale_hover 用"""

    def __init__(self, sm):
        self._hover_sm = sm
        self.data = _FakeData()
        self.visual_state = 'normal'

    def set_visual_state(self, state):
        self.visual_state = state


def _wait(ms: int):
    """跑 Qt 事件循环 ms 毫秒 (让状态机的充能定时器真的 tick)"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _make_controller():
    """RunController 只在轮询里用 scene/window, 这里测的方法用不到, 传 None 即可"""
    return RunController(None, None)


def test_rearm_after_stale_leave() -> bool:
    """trigger 模式: 充能中被外部 leave() 打断 → 下一帧应自愈重入并最终激活"""
    ctrl = _make_controller()
    sm = HoverStateMachine(hover_delay_ms=150, release_delay_ms=0, mode='trigger')
    fired = []
    sm.activated.connect(lambda: fired.append('activated'))
    item = _FakeItem(sm)

    sm.enter()
    assert sm.state == HoverState.CHARGING, f'enter 后应在充能: {sm.state}'

    # 模拟迟到的 Qt hoverLeaveEvent —— 光标其实还压在按钮上
    sm.leave()
    assert sm.state == HoverState.IDLE, f'外部 leave 后应回 IDLE: {sm.state}'

    # 轮询下一帧: active_item 没变 → 走自愈分支
    ctrl._rearm_stale_hover(item)
    if sm.state != HoverState.CHARGING:
        print(f'  [FAIL] 自愈未生效, 状态={sm.state}')
        return False

    _wait(400)
    if not fired:
        print('  [FAIL] 自愈后充能未完成, activated 没触发')
        return False
    if ctrl._hover_rearm_count != 1:
        print(f'  [FAIL] 自愈计数不对: {ctrl._hover_rearm_count}')
        return False
    print('  [OK] 充能被外部打断后自愈重入, activated 正常触发')
    return True


def test_no_rearm_when_charging_or_active() -> bool:
    """正常充能/激活中不该被重复 enter (否则进度条会一直从 0 重来)"""
    ctrl = _make_controller()
    sm = HoverStateMachine(hover_delay_ms=150, release_delay_ms=0, mode='trigger')
    item = _FakeItem(sm)

    sm.enter()
    _wait(60)                      # 充到一半
    ctrl._rearm_stale_hover(item)  # 不应该打断
    _wait(200)
    if not sm.is_active:
        print('  [FAIL] 充能中被自愈分支干扰, 没能激活')
        return False
    ctrl._rearm_stale_hover(item)  # ACTIVE 状态也不该动
    if not sm.is_active or ctrl._hover_rearm_count != 0:
        print(f'  [FAIL] ACTIVE 状态被误重入, count={ctrl._hover_rearm_count}')
        return False
    print('  [OK] CHARGING / ACTIVE 状态不会被误重入')
    return True


def test_toggle_mode_not_rearmed() -> bool:
    """toggle 模式: 关掉之后光标还停在按钮上, 绝不能被自愈成无限自动开关"""
    ctrl = _make_controller()
    sm = HoverStateMachine(hover_delay_ms=0, release_delay_ms=0, mode='toggle')
    item = _FakeItem(sm)

    sm.enter()                      # 开
    assert sm.is_active
    sm.leave()                      # 光标移出 (标记 has_left)
    sm.enter()                      # 再进来 → 关
    assert sm.state == HoverState.IDLE, f'toggle 第二次 enter 应关闭: {sm.state}'

    for _ in range(5):              # 光标继续压在按钮上, 轮询每帧都会走到这
        ctrl._rearm_stale_hover(item)
    if sm.state != HoverState.IDLE or ctrl._hover_rearm_count != 0:
        print(f'  [FAIL] toggle 被自愈重新打开: state={sm.state}, '
              f'count={ctrl._hover_rearm_count}')
        return False
    print('  [OK] toggle 模式的 IDLE 不会被自愈重入')
    return True


def test_rearm_cancels_stale_release() -> bool:
    """配了释放延迟时: 外部 leave 让它进 RELEASING, 自愈应把它拉回 ACTIVE 且不重发按键"""
    ctrl = _make_controller()
    sm = HoverStateMachine(hover_delay_ms=0, release_delay_ms=300, mode='trigger')
    fired = []
    sm.activated.connect(lambda: fired.append('p'))
    sm.deactivated.connect(lambda: fired.append('r'))
    item = _FakeItem(sm)

    sm.enter()
    assert sm.is_active and fired == ['p']

    sm.leave()                       # 迟到的 hoverLeaveEvent → 开始释放倒计时
    assert sm.state == HoverState.RELEASING

    ctrl._rearm_stale_hover(item)
    if not sm.is_active:
        print(f'  [FAIL] RELEASING 未被自愈拉回 ACTIVE: {sm.state}')
        return False
    _wait(400)
    if fired != ['p']:
        print(f'  [FAIL] 按键被误松开/重发: {fired}')
        return False
    print('  [OK] 释放倒计时被自愈取消, 按键保持按住不抖动')
    return True


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    print('悬停自愈回归测试')
    print('=' * 40)
    cases = [
        ('充能被外部清空 → 自愈', test_rearm_after_stale_leave),
        ('正常充能/激活不被打扰', test_no_rearm_when_charging_or_active),
        ('toggle 关闭态不被自愈', test_toggle_mode_not_rearmed),
        ('释放倒计时被自愈取消', test_rearm_cancels_stale_release),
    ]
    failed = 0
    for name, fn in cases:
        print(f'\n[{name}]')
        try:
            if not fn():
                failed += 1
        except Exception as e:
            print(f'  [FAIL] 异常: {e}')
            failed += 1
    print('\n' + '=' * 40)
    print('全部通过' if failed == 0 else f'{failed} 项失败')
    del app
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
