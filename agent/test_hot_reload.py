"""
TEGGTouch 蛋挞 — 配置热重载机制验证 (G2)

用 offscreen QApplication 验证热重载的核心: OverlayScene 清场 + 重载能正确
把新 config 反映到 item.data (运行时 RunController 每帧直读 item.data, 故
这一步通过即代表"改完配置可热生效")。

不构造完整 OverlayWindow (太重), 只验证最关键的 scene 机制 + RunController
的 prepare_hot_reload 不崩。

用法: python -m agent.test_hot_reload
"""

import os
import sys
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 必须在 import 任何 Qt widget 之前设 offscreen
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from core import config_manager as cfg


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    from scene.overlay_scene import OverlayScene
    scene = OverlayScene()
    scene.setSceneRect(0, 0, 2560, 1440)

    name = cfg.get_active_profile_name()
    config = cfg.load_profile(name)
    scene.load_from_config(config)
    n0 = len(scene.button_items)
    assert n0 > 0, "活跃方案没有按钮, 换个有按钮的方案再测"
    old_hover = scene.button_items[0].data.hover
    print(f"加载方案 '{name}': {n0} 个按钮, buttons[0].hover = {old_hover!r}")

    # 清场
    scene.clear_all_items()
    assert len(scene.button_items) == 0, "clear_all_items 未清空 button_items"
    assert len(scene.wheel_items) == 0
    print("clear_all_items: 场景已清空 ✓")

    # 改 config 后热重载 (模拟 agent 改了绑定并落盘后, 运行端重读)
    tweaked = copy.deepcopy(config)
    tweaked["buttons"][0]["hover"] = "ctrl+f4"
    scene.load_from_config(tweaked)
    n1 = len(scene.button_items)
    new_hover = scene.button_items[0].data.hover
    assert n1 == n0, f"按钮数变了: {n0} → {n1}"
    assert new_hover == "ctrl+f4", f"热重载未生效: {new_hover!r}"
    print(f"热重载后: {n1} 个按钮, buttons[0].hover = {new_hover!r} ✓")

    # RunController.prepare_hot_reload 不崩 (active=False 时应直接 return)
    from engine.run_controller import RunController
    rc = RunController(scene, None)
    rc.prepare_hot_reload()  # 未运行 → no-op
    print("RunController.prepare_hot_reload (未运行): no-op ✓")

    print("\n✅ G2 热重载机制验证通过")


if __name__ == "__main__":
    main()
