"""
TEGGTouch 蛋挞 — Agent 工具层 headless 验证脚本 (调查项 D2)

不启动 UI, 直接验证:
  1. ConfigTools  — 程序化读 / 改 / 存 profile 绑定与参数 (读写往返)
  2. ControlTools — 按标签语法分派键盘/鼠标/手柄 + 鼠标绝对移动

配置部分用临时方案 (__agent_d2_demo__) 做真实读写往返, 跑完即删, 不动
用户真实方案。控制部分默认 dry-run (只打印将要发的输入, 不真的发);
加 --live 才真实发送 (会真的动你的鼠标/键盘, 慎用)。

用法:
    python -m agent.headless_demo            # 安全: 配置真改往返 + 控制 dry-run
    python -m agent.headless_demo --live     # 控制也真实发送 (3 秒后开始)
"""

import os
import sys
import json
import logging

# 允许 `python agent/headless_demo.py` 直接跑 (把仓库根加进 sys.path)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 控制台默认 GBK, 打 ✓/── 等字符会崩 — 强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import config_manager as cfg
from agent.tool_layer import ConfigTools, ControlTools

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

TMP_PROFILE = "__agent_d2_demo__"


def _dump(title, obj):
    print(f"\n── {title} ──")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def demo_config():
    print("\n" + "=" * 60)
    print(" ConfigTools — 程序化读写 profile (真实读写往返)")
    print("=" * 60)

    _dump("现有方案", ConfigTools.list_profiles())

    # 用临时方案做往返, 不碰用户真实方案
    if TMP_PROFILE in cfg.list_profiles():
        cfg.delete_profile(TMP_PROFILE)
    created = cfg.create_profile(TMP_PROFILE, from_template=True)
    print(f"\n创建临时方案 {TMP_PROFILE}: {created}")

    try:
        before = ConfigTools.summarize_profile(TMP_PROFILE)
        _dump(f"摘要 (前 3 个按钮)", {**before, "buttons": before["buttons"][:3]})

        if before["button_count"] == 0:
            print("⚠ 模板无按钮, 跳过绑定改写")
        else:
            # 1) 改按钮 0 的 hover 绑定 → 验证读写往返
            r = ConfigTools.set_button_binding(0, "hover", "ctrl+f4", name=TMP_PROFILE)
            _dump("set_button_binding(0, hover='ctrl+f4')", r)
            # 重新读盘, 断言确实落盘
            reread = cfg.load_profile(TMP_PROFILE)["buttons"][0]["hover"]
            assert reread == "ctrl+f4", f"落盘校验失败: {reread!r}"
            print(f"✓ 重新读盘校验通过: buttons[0].hover = {reread!r}")

            # 2) 非法字段被拦
            bad = ConfigTools.set_button_binding(0, "x", "999", name=TMP_PROFILE)
            _dump("set_button_binding(0, x=...) — 应被拒", bad)
            assert bad["ok"] is False

        # 3) 改顶层参数
        rp = ConfigTools.set_param("transparency", 0.5, name=TMP_PROFILE)
        _dump("set_param(transparency=0.5)", rp)
        assert cfg.load_profile(TMP_PROFILE)["transparency"] == 0.5
        print("✓ 顶层参数读写往返通过")
    finally:
        cfg.delete_profile(TMP_PROFILE)
        print(f"\n已清理临时方案 {TMP_PROFILE}")


def demo_control(live: bool):
    print("\n" + "=" * 60)
    print(f" ControlTools — 输入分派  ({'LIVE 真实发送' if live else 'dry-run 空跑'})")
    print("=" * 60)

    dry = not live

    # 单组合键 (核心: 证明 ctrl+f4 这类组合在 headless 下能正确解析/合并)
    _dump("run_keys('ctrl+f4', click)", ControlTools.run_keys("ctrl+f4", "click", dry_run=dry))

    # 混合标签: 普通键 + 鼠标 + 手柄 + deferred(宏)
    _dump("run_keys('shift+mouse:left', click)",
          ControlTools.run_keys("shift+mouse:left", "click", dry_run=dry))
    _dump("run_keys('gp:A', click)", ControlTools.run_keys("gp:A", "click", dry_run=dry))
    _dump("run_keys('xmacro:连招', click) — 应 deferred",
          ControlTools.run_keys("xmacro:连招", "click", dry_run=dry))

    # 鼠标绝对定位 (G5)
    _dump("move_mouse(960, 540)", ControlTools.move_mouse(960, 540, dry_run=dry))

    # 动作序列
    seq = [
        {"keys": "ctrl+c", "action": "click", "after_ms": 50},
        {"delay_ms": 100},
        {"move": [200, 200]},
        {"keys": "mouse:wheelup", "action": "click"},
    ]
    _dump("run_sequence([...])", ControlTools.run_sequence(seq, dry_run=dry))


def main():
    live = "--live" in sys.argv
    demo_config()
    if live:
        import time
        print("\n⚠ --live: 3 秒后将真实发送鼠标/键盘输入, 切到安全窗口...")
        time.sleep(3)
    demo_control(live)
    print("\n✅ D2 headless 验证完成")


if __name__ == "__main__":
    main()
