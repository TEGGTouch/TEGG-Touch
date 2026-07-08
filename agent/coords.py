"""
TEGGTouch 蛋挞 — 坐标映射 (computer use L3 坐标层的永久基建)

M3 视觉 grounding 的输出约定是**归一化 0–1000**, 与分辨率无关:
  x: 左 0 → 右 1000    y: 上 0 → 下 1000
本模块把这套约定和真实屏幕像素双向换算, 供:
  - 探针脚本 (grounding_probe) 校准精度
  - 以后的坐标控制工具 (computer_click 等) 把模型给的 0–1000 落到真实像素

无 Qt / 无网络依赖, 纯函数, 可在任意线程调。
"""

from __future__ import annotations


def _frac(v: float) -> float:
    """把 0–1000 的一维坐标夹到 [0,1] 比例 (越界钳制, 防模型偶发越界)。"""
    return max(0.0, min(1.0, float(v) / 1000.0))


def norm_to_pixel(nx: float, ny: float, src_w: int, src_h: int,
                  region: tuple | None = None) -> tuple[int, int]:
    """0–1000 归一坐标 → 屏幕绝对像素 (虚拟桌面坐标, 可直接喂 SetCursorPos/SendInput)。

    Args:
        nx, ny:   模型给的 0–1000 坐标 (中心点)
        src_w/h:  截图**压缩前**的真实像素尺寸 (grab_png 返回的 src_w/src_h)
        region:   截图区域 (l, t, r, b), 用其左上角做偏移; None 视为 (0,0) (主屏原点)

    Returns:
        (x, y) 整数像素, 已按区域偏移。
    """
    left = region[0] if region else 0
    top = region[1] if region else 0
    return (int(round(left + _frac(nx) * src_w)),
            int(round(top + _frac(ny) * src_h)))


def norm_to_image_xy(nx: float, ny: float, img_w: int, img_h: int) -> tuple[int, int]:
    """0–1000 归一坐标 → **压缩图内**像素 (在返回给模型的那张图上画标记用)。"""
    return (int(round(_frac(nx) * img_w)),
            int(round(_frac(ny) * img_h)))


def norm_to_center_origin(nx: float, ny: float, src_w: int, src_h: int,
                          region: tuple | None = None) -> tuple[int, int]:
    """0-1000 grounding 坐标 → TEGGTouch 中心原点像素 (直接用于 add_button / set_button_geometry 的 x/y)。

    原点 = 蛋挞所在屏的中心; x 右正 y 下正, 单位像素。
    """
    abs_x, abs_y = norm_to_pixel(nx, ny, src_w, src_h, region)
    if region:
        cx = (region[0] + region[2]) / 2.0
        cy = (region[1] + region[3]) / 2.0
    else:
        cx = src_w / 2.0
        cy = src_h / 2.0
    return (int(round(abs_x - cx)), int(round(abs_y - cy)))


def pixel_to_norm(px: float, py: float, src_w: int, src_h: int,
                  region: tuple | None = None) -> tuple[int, int]:
    """屏幕绝对像素 → 0–1000 归一坐标 (反向; 校准/回填时用)。"""
    left = region[0] if region else 0
    top = region[1] if region else 0
    w = src_w or 1
    h = src_h or 1
    nx = (px - left) / w * 1000.0
    ny = (py - top) / h * 1000.0
    return (int(round(max(0.0, min(1000.0, nx)))),
            int(round(max(0.0, min(1000.0, ny)))))
