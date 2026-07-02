"""
TEGGTouch 蛋挞 — 屏幕截取 (阶段2 多模态感知)

给 agent "看屏幕"的能力: 抓蛋挞所在显示器 → 压缩到模型可接收大小 → base64。

**临时排除蛋挞覆盖层**: 只在 agent 截屏那一瞬间, 用 Windows
SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) 把蛋挞所有顶层窗标记为"对捕获不可见",
抓完立即恢复 —— 覆盖层对用户始终可见, 也照常出现在用户自己的录屏/OBS 里, 只有 agent
这次截图拍不到它。设标记后需等 DWM 重新合成 ~1 帧再抓。

主线程 (OverlayWindow) 通过 set_capture_context() 提供: 要排除的窗口句柄列表 +
蛋挞所在显示器的区域。grab_png() 在 AgentThread 子线程调 (排除/等待/抓屏/恢复 全在此完成;
sleep 在子线程不卡界面)。需 Win10 2004+; 老系统排除失败则退化为普通抓屏。
"""

from __future__ import annotations

import base64
import io
import logging
import sys
import time

logger = logging.getLogger(__name__)

# MiniMax-M3 单图 ≤10MB; 另按多模态惯例把长边压到 ~1600 省 token 与带宽
MAX_EDGE = 1600
JPEG_QUALITY = 80
FRAME_WAIT = 0.10   # 设排除标记后等 DWM 重新合成 (>1 帧@60Hz)

WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11

# 由主线程 (OverlayWindow) 填: 要临时排除的窗口句柄 + 蛋挞所在显示器区域
_ctx = {"hwnds": [], "region": None}


def set_capture_context(hwnds, region) -> None:
    """主线程调: 提供蛋挞所有顶层窗句柄 + 蛋挞所在显示器区域 (l,t,r,b, 虚拟桌面坐标)。"""
    try:
        _ctx["hwnds"] = [int(h) for h in (hwnds or [])]
    except (TypeError, ValueError):
        _ctx["hwnds"] = []
    _ctx["region"] = tuple(region) if region else None


def exclude_hwnd_from_capture(hwnd: int, exclude: bool = True) -> bool:
    """对一个窗口句柄设置/取消"从捕获中排除"。返回是否成功 (老系统/失败 → False)。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(hwnd), affinity))
    except Exception as e:
        logger.warning("SetWindowDisplayAffinity 失败 (hwnd=%s): %s", hwnd, e)
        return False


def grab_png(region: tuple | None = None) -> dict:
    """抓屏(蛋挞所在显示器) + 临时排除覆盖层 + 压缩。

    返回 {ok, media_type, data(base64 str), w, h, src_w, src_h, bytes} 或 {ok:False, error}。
    region 省略则用 set_capture_context 提供的蛋挞显示器区域。
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"ok": False, "error": "缺少 Pillow, 请 pip install pillow"}

    reg = region or _ctx["region"]
    excluded = []
    try:
        # 1) 临时把覆盖层各顶层窗排除出捕获
        for h in _ctx["hwnds"]:
            if exclude_hwnd_from_capture(h, True):
                excluded.append(h)
        if excluded:
            time.sleep(FRAME_WAIT)   # 等 DWM 重新合成, 否则仍拍得到
        # 2) 抓蛋挞所在显示器 (all_screens 支持非主屏; bbox 在虚拟桌面坐标里裁剪)
        img = ImageGrab.grab(bbox=reg, all_screens=True)
    except Exception as e:
        return {"ok": False, "error": f"截屏失败: {e}"}
    finally:
        # 3) 无论成败, 立即恢复覆盖层可见于捕获
        for h in excluded:
            exclude_hwnd_from_capture(h, False)

    src_w, src_h = img.size
    longest = max(src_w, src_h) or 1
    if longest > MAX_EDGE:
        scale = MAX_EDGE / longest
        img = img.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=JPEG_QUALITY)
    data = buf.getvalue()
    return {
        "ok": True,
        "media_type": "image/jpeg",
        "data": base64.b64encode(data).decode("ascii"),
        "w": img.width, "h": img.height,
        "src_w": src_w, "src_h": src_h,
        "bytes": len(data),
    }
