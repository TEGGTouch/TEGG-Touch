"""
TEGGTouch 蛋挞 — grounding 精度探针 (computer use 第一步: 校准, 不真点击)

目的: 单独验证 M3 视觉定位 (0–1000 归一坐标) 落到真实像素**准不准**, 决定
坐标控制层 (L3) 到底靠不靠谱、够不够点小按钮。**不碰主程序、不发点击**。

流程:
  截主屏 → 连同"定位这个目标"发给 M3 → M3 用 report_location 工具回 0–1000 坐标
  → 换算成像素 + 在压缩图上画十字标记 → 存图供肉眼看偏差 (可选把光标移过去, 仍不点)

用法:
  python -m agent.grounding_probe "回收站图标"
  python -m agent.grounding_probe "开始菜单按钮" --move      # 额外把鼠标移过去(不点击)
  python -m agent.grounding_probe "关闭按钮" --think          # 开 M3 思考再定位, 对比精度

需要: settings/agent.json 里的密钥 (或环境变量 MINIMAX_API_KEY) + 网络 + Pillow。
产物: logs/agent/grounding/<时间>_<目标>.png (原图上叠红色十字+目标名)。
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import sys
import time

from agent import coords
from agent.ai_client import MiniMaxClient, AIClientError
from agent.screen_capture import grab_png
from core import agent_settings
from core.constants import APP_DIR


# 单工具: 让模型只报一个中心点坐标 (0–1000)
LOCATE_TOOL = {
    "name": "report_location",
    "description": (
        "报告目标在这张截图中的位置。坐标必须用归一化 0–1000 (与分辨率无关): "
        "x 左=0 右=1000, y 上=0 下=1000。给目标的**中心点**。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "found": {"type": "boolean", "description": "画面里是否找得到这个目标"},
            "x": {"type": "integer", "description": "中心点横坐标 0–1000"},
            "y": {"type": "integer", "description": "中心点纵坐标 0–1000"},
            "note": {"type": "string", "description": "你判定这就是目标的依据(看到的文字/图形)"},
        },
        "required": ["found", "x", "y"],
    },
}

SYSTEM = (
    "你是屏幕视觉定位助手。用户给你一张屏幕截图和一个目标描述, "
    "你要在图中找到该目标, 并调用 report_location 给出它中心点的归一化 0–1000 坐标。"
    "坐标系: x 左0右1000, y 上0下1000。必须调用工具, 不要用文字回答。"
)


def _primary_size() -> tuple[int, int]:
    """主显示器像素尺寸 (SM_CXSCREEN/SM_CYSCREEN)。非 Windows 退化为 1920x1080。"""
    if sys.platform == "win32":
        import ctypes
        u = ctypes.windll.user32
        return int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
    return 1920, 1080


def _draw_marker(png_b64: str, ix: int, iy: int, label: str) -> "Image":
    """在压缩图上画红色十字 + 圆圈 + 目标名, 返回 PIL Image。"""
    from PIL import Image, ImageDraw
    img = Image.open(io.BytesIO(base64.b64decode(png_b64))).convert("RGB")
    d = ImageDraw.Draw(img)
    r = 22
    d.ellipse([ix - r, iy - r, ix + r, iy + r], outline=(255, 40, 40), width=4)
    d.line([ix - r - 12, iy, ix + r + 12, iy], fill=(255, 40, 40), width=3)
    d.line([ix, iy - r - 12, ix, iy + r + 12], fill=(255, 40, 40), width=3)
    d.text((ix + r + 6, iy - r - 6), label, fill=(255, 220, 0))
    return img


def probe(target: str, do_move: bool = False, think: bool = False,
          do_click: bool = False) -> int:
    cfg = agent_settings.load_agent_settings()
    if not cfg.get("api_key"):
        print("✗ 未配置密钥 (settings/agent.json 或环境变量 MINIMAX_API_KEY)")
        return 2

    w, h = _primary_size()
    region = (0, 0, w, h)
    print(f"主屏 {w}x{h}, 抓图中…")
    shot = grab_png(region=region)
    if not shot.get("ok"):
        print(f"✗ 截屏失败: {shot.get('error')}")
        return 2
    src_w, src_h = shot["src_w"], shot["src_h"]

    client = MiniMaxClient(
        api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"],
        max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
    )
    image_block = {"type": "image",
                   "source": {"type": "base64", "media_type": shot["media_type"],
                              "data": shot["data"]}}
    messages = [{"role": "user", "content": [
        image_block,
        {"type": "text", "text": f"定位这个目标: {target}"},
    ]}]

    print(f"问 M3 定位「{target}」{'(开思考)' if think else ''}…")
    t0 = time.time()
    try:
        res = client.chat(messages, tools=[LOCATE_TOOL], system=SYSTEM,
                          thinking={"type": "adaptive"} if think else None)
    except AIClientError as e:
        print(f"✗ 调用失败: {e}")
        return 2
    dt = time.time() - t0

    tus = res.get("tool_uses") or []
    loc = next((t["input"] for t in tus if t["name"] == "report_location"), None)
    if not loc:
        print(f"✗ 模型没调工具, 文字回复: {res.get('text')!r}  (耗时 {dt:.1f}s)")
        return 1

    nx, ny = loc.get("x", 0), loc.get("y", 0)
    found = loc.get("found", False)
    note = loc.get("note", "")
    px, py = coords.norm_to_pixel(nx, ny, src_w, src_h, region)
    ix, iy = coords.norm_to_image_xy(nx, ny, shot["w"], shot["h"])

    print(f"{'✓ 找到' if found else '⚠ 模型说没把握'}  0–1000=({nx},{ny}) "
          f"→ 像素=({px},{py})  耗时 {dt:.1f}s")
    if note:
        print(f"  依据: {note}")

    out_dir = os.path.join(APP_DIR, "logs", "agent", "grounding")
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join(c for c in target if c.isalnum() or c in " _-")[:20].strip() or "target"
    out_path = os.path.join(out_dir, f"{time.strftime('%H%M%S')}_{safe}.png")
    _draw_marker(shot["data"], ix, iy, target).save(out_path)
    print(f"  标记图: {out_path}  (肉眼看红十字是否压在目标上)")

    if (do_move or do_click) and not found:
        print("  (模型没找到目标, 不动鼠标)")
    elif (do_move or do_click) and sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.SetCursorPos(px, py)
        if do_click:
            time.sleep(0.08)
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # 左键按下
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # 左键松开
            print(f"  已在 ({px},{py}) 单击左键")
        else:
            print(f"  已把鼠标移到 ({px},{py}) —— 未点击")

    return 0


def main():
    # Windows 控制台默认 GBK, 直接 print 中文/✓ 会崩; 强制 stdout 走 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="M3 grounding 精度探针 (不真点击)")
    ap.add_argument("target", help="要定位的目标描述, 如 '回收站图标'")
    ap.add_argument("--move", action="store_true", help="额外把鼠标移过去(不点击)")
    ap.add_argument("--click", action="store_true", help="移过去并真的单击左键")
    ap.add_argument("--think", action="store_true", help="开 M3 思考再定位")
    args = ap.parse_args()
    sys.exit(probe(args.target, do_move=args.move, think=args.think,
                   do_click=args.click))


if __name__ == "__main__":
    main()
