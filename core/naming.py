"""
TEGGTouch 蛋挞 — 元素自动编号命名

新建元素时按"前缀+两位序号"命名 (如 手柄键01 / 按钮01 / 回中带01), 便于用户/agent 指明。
序号取现有同前缀名字的最大值+1; 无编号的旧名 (如"手柄键") 记为 0 → 新的从 01 起。
"""

from __future__ import annotations

import re


def next_numbered_name(existing_names, prefix: str) -> str:
    """existing_names 里找 '<prefix><数字>' 的最大序号, 返回 '<prefix>{max+1:02d}'。"""
    mx = 0
    pat = re.compile(rf"^{re.escape(prefix)}0*(\d+)$")
    for n in existing_names or []:
        m = pat.match((str(n) if n is not None else "").strip())
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{prefix}{mx + 1:02d}"
