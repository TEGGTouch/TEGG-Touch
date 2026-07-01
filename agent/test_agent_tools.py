"""
TEGGTouch 蛋挞 — Agent 工具分派验证 (阶段1 配置助手)

离线验证 agent_tools.dispatch 正确走 ConfigTools 读写 profile: 不需要 API 密钥
和网络。会临时改当前活跃方案再还原 (跑前自动快照整份 config, 跑后写回)。

也顺带验证 system_prompt 能拼出来、build_config_tools schema 合法。

用法: python -m agent.test_agent_tools
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import config_manager as cfg
from agent import agent_tools


def main():
    name = cfg.get_active_profile_name()
    original = cfg.load_profile(name)
    snapshot = copy.deepcopy(original)
    print(f"活跃方案: '{name}'")

    try:
        # ── 1. 读类工具 ──
        profs = agent_tools.dispatch("list_profiles", {})
        assert "active" in profs and "profiles" in profs, profs
        print(f"list_profiles ✓  active={profs['active']}, {len(profs['profiles'])} 个方案")

        summary = agent_tools.dispatch("summarize_profile", {})
        assert summary.get("profile") == name, summary
        assert "buttons" in summary, summary
        print(f"summarize_profile ✓  {summary['button_count']} 个按钮")

        # ── 2. set_param 往返 (before/after + 落盘) ──
        #    用真实白名单参数 transparency (合成 key 会被 set_param 白名单拒绝)
        param_key = "transparency"
        r = agent_tools.dispatch("set_param", {"key": param_key, "value": 0.66})
        assert r.get("ok") and r.get("after") == 0.66, r
        reloaded = cfg.load_profile(name)
        assert reloaded.get(param_key) == 0.66, "set_param 未落盘"
        print(f"set_param ✓  {param_key}: {r['before']!r} → {r['after']!r} (已落盘)")

        # 白名单拒绝未知参数
        r = agent_tools.dispatch("set_param", {"key": "_no_such_param", "value": 1})
        assert not r.get("ok"), "未知参数应被拒绝"
        print("set_param 白名单拒绝未知参数 ✓")

        # ── 3. set_button_binding 往返 (需有按钮) ──
        if summary["button_count"] > 0:
            before = summary["buttons"][0]["bindings"].get("hover", "")
            r = agent_tools.dispatch("set_button_binding",
                                     {"button_index": 0, "field": "hover", "value": "ctrl+f4"})
            assert r.get("ok") and r.get("after") == "ctrl+f4", r
            reloaded = cfg.load_profile(name)
            assert reloaded["buttons"][0]["hover"] == "ctrl+f4", "set_button_binding 未落盘"
            print(f"set_button_binding ✓  按钮0 hover: {before!r} → 'ctrl+f4' (已落盘)")

            # 白名单拒绝非法字段
            r = agent_tools.dispatch("set_button_binding",
                                     {"button_index": 0, "field": "x", "value": "y"})
            assert not r.get("ok"), "非法字段应被拒绝"
            print("set_button_binding 白名单拒绝非法字段 ✓")
        else:
            print("(当前方案无按钮, 跳过 set_button_binding 测试)")

        # ── 4. 未知工具 / 缺参 ──
        assert not agent_tools.dispatch("nope", {}).get("ok"), "未知工具应报错"
        assert not agent_tools.dispatch("set_param", {}).get("ok"), "缺参应报错"
        print("未知工具 / 缺参 均返回 error ✓")

        # ── 5. schema + system_prompt 可构造 ──
        tools = agent_tools.build_config_tools()
        assert len(tools) >= 5 and all("input_schema" in t for t in tools), tools
        sp = agent_tools.system_prompt()
        assert "标签语法" in sp and name in sp, "system_prompt 内容异常"
        print(f"build_config_tools ✓  {len(tools)} 个工具; system_prompt ✓  {len(sp)} 字")

        print("\n✅ Agent 工具分派验证通过")
    finally:
        # 还原 (无论成败) — 把快照写回, 顺便去掉 marker
        snapshot.pop("_agent_test_marker", None)
        cfg.save_profile(name, snapshot)
        print("已还原方案到测试前状态。")


if __name__ == "__main__":
    main()
