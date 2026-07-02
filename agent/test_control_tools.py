"""
TEGGTouch 蛋挞 — Computer Use 控制层离线验证 (L3 坐标操作电脑)

不需要密钥/网络/真发输入 (全走 dry_run)。验证:
- 危险词判定 safety.is_dangerous
- 坐标换算 coords (0-1000 ↔ 像素)
- ControlTools.click_xy / scroll_xy 的 dry_run 契约
- build_control_tools schema 合法 + 工具名登记在 COMPUTER_TOOLS

用法: python -m agent.test_control_tools
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from agent import safety, coords, agent_tools
from agent.tool_layer import ControlTools


def main():
    # ── 1. 危险词判定 ──
    for t in ["关闭窗口", "删除存档", "确认支付 100 元", "send message", "卸载 Steam"]:
        assert safety.is_dangerous(t), f"应判危险: {t}"
    for t in ["点击开始游戏", "选择第一个游戏", "move to search box", ""]:
        assert not safety.is_dangerous(t), f"不应判危险: {t}"
    print("safety.is_dangerous ✓ (危险词命中/放行都对)")

    # ── 2. 坐标换算 ──
    assert coords.norm_to_pixel(500, 500, 1920, 1080) == (960, 540)
    assert coords.norm_to_pixel(1000, 1000, 2560, 1440) == (2560, 1440)
    assert coords.norm_to_pixel(500, 500, 1920, 1080, (1920, 0, 3840, 1080)) == (2880, 540)
    assert coords.norm_to_pixel(1200, -50, 1920, 1080) == (1920, 0)  # 越界钳制
    print("coords 0-1000↔像素 ✓ (含多屏偏移+越界钳制)")

    # ── 3. ControlTools 坐标原语 dry_run ──
    r = ControlTools.click_xy(960, 540, "left", dry_run=True)
    assert r["ok"] and r["x"] == 960 and r["button"] == "left" and "[dry-run]" in r["detail"], r
    r = ControlTools.click_xy(10, 20, "middle", double=True, dry_run=True)
    assert r["ok"] and r["double"] and r["button"] == "middle", r
    r = ControlTools.click_xy(0, 0, "bogus", dry_run=True)
    assert not r["ok"], "未知按钮应报错"
    r = ControlTools.scroll_xy(100, 200, "down", 5, dry_run=True)
    assert r["ok"] and r["direction"] == "down" and r["amount"] == 5, r
    r = ControlTools.scroll_xy(100, 200, "sideways", dry_run=True)
    assert not r["ok"], "非法方向应报错"
    print("ControlTools.click_xy / scroll_xy dry_run ✓")

    # ── 4. 控制工具 schema ──
    tools = agent_tools.build_control_tools()
    names = {t["name"] for t in tools}
    assert {"computer_click", "computer_double_click", "computer_move",
            "computer_scroll", "wait"} <= names, names
    for t in tools:
        assert "input_schema" in t and "description" in t, t
    # 坐标类工具都登记在 COMPUTER_TOOLS (供 AgentThread 拦截)
    assert agent_tools.COMPUTER_TOOLS == {
        "computer_click", "computer_double_click", "computer_move", "computer_scroll"}, \
        agent_tools.COMPUTER_TOOLS
    print(f"build_control_tools ✓  {len(tools)} 个工具, COMPUTER_TOOLS 登记正确")

    print("\n✅ Computer Use 控制层离线验证通过")


if __name__ == "__main__":
    main()
