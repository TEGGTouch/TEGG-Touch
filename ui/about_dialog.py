"""
TEGG Touch 蛋挞 - about_dialog.py
关于/产品介绍弹窗。
"""

import tkinter as tk
import os

from PIL import Image, ImageTk

from core.constants import (
    APP_TITLE, APP_VERSION,
    COLOR_TOOLBAR_TRANSPARENT, TOOLBAR_RADIUS,
)
from ui.widgets import (
    FF, FS, IS, BTN_R, CLOSE_SIZE, CLOSE_M,
    C_PM_BG, C_CLOSE, C_CLOSE_H, C_AMBER,
    icon_font, rrect, create_modal_overlay,
)

# 最后更新日期
_LAST_UPDATE = "2026.02.19"

# 产品介绍文本
_DESC_TEXT = (
    "TEGG Touch 蛋挞 是一款永久免费、完全开源的无障碍辅助软件。\n\n"
    "想要做到用仅仅用鼠标的简单的点击行为，替代大部分的游戏操作。"
    "希望能给有需求的用户提供帮助，让大家都能体会到游戏的乐趣。"
)

_QR_HINT = "扫码加我微信好友（茶叶蛋TEGG）\n问题 / 建议 / 反馈，看到一定会解答 :)"


def open_about_dialog(parent):
    """打开关于弹窗。"""
    overlay = create_modal_overlay(parent)

    PADDING = 30
    width = 440
    height = 580
    sw = parent.winfo_screenwidth()
    sh = parent.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.geometry(f"{width}x{height}+{x}+{y}")
    top.attributes("-topmost", True)
    top.configure(bg=COLOR_TOOLBAR_TRANSPARENT)
    top.wm_attributes("-transparentcolor", COLOR_TOOLBAR_TRANSPARENT)

    def _destroy_all(e):
        try:
            overlay.destroy()
        except Exception:
            pass
    top.bind("<Destroy>", _destroy_all, add="+")
    top.focus_set()
    overlay.attributes("-topmost", True)
    top.attributes("-topmost", True)
    top.lift()

    c = tk.Canvas(top, width=width, height=height,
                  bg=COLOR_TOOLBAR_TRANSPARENT, highlightthickness=0)
    c.place(x=0, y=0)
    rrect(c, 0, 0, width, height, TOOLBAR_RADIUS,
          fill=C_PM_BG, outline="#444", width=1, tags="bg")

    # ── 拖拽 ──
    drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}
    def _ds(e):
        drag["sx"], drag["sy"] = e.x_root, e.y_root
        drag["wx"], drag["wy"] = top.winfo_x(), top.winfo_y()
    def _dm(e):
        nx = drag["wx"] + (e.x_root - drag["sx"])
        ny = drag["wy"] + (e.y_root - drag["sy"])
        top.geometry(f"{width}x{height}+{max(0, min(nx, sw - width))}+{max(0, min(ny, sh - height))}")
    c.tag_bind("bg", "<Button-1>", _ds)
    c.tag_bind("bg", "<B1-Motion>", _dm)

    # ── 关闭按钮 ──
    ifont = icon_font()
    cx0 = width - CLOSE_M - CLOSE_SIZE
    cy0 = CLOSE_M
    rrect(c, cx0, cy0, CLOSE_SIZE, CLOSE_SIZE, BTN_R,
          fill=C_CLOSE, outline="", tags=("close", "close_bg"))
    ccx, ccy = cx0 + CLOSE_SIZE // 2, cy0 + CLOSE_SIZE // 2
    if ifont:
        c.create_text(ccx, ccy, text="\uE711", font=(ifont, IS), fill="#FFF", tags=("close",))
    else:
        c.create_text(ccx, ccy, text="\u2715", font=(FF, FS, "bold"), fill="#FFF", tags=("close",))
    c.tag_bind("close", "<Enter>", lambda e: c.itemconfigure("close_bg", fill=C_CLOSE_H))
    c.tag_bind("close", "<Leave>", lambda e: c.itemconfigure("close_bg", fill=C_CLOSE))
    c.tag_bind("close", "<ButtonRelease-1>", lambda e: top.destroy())

    # ── 内容区 ──
    cy = 40
    mid_x = width // 2

    # 标题: 🎮 TEGG Touch 蛋挞
    c.create_text(mid_x, cy, text=f"🎮  {APP_TITLE}",
                  font=(FF, 18, "bold"), fill=C_AMBER, tags="bg")
    cy += 34

    # 版本号
    c.create_text(mid_x, cy, text=f"v{APP_VERSION}",
                  font=(FF, 11), fill="#888", tags="bg")
    cy += 22

    # 最后更新
    c.create_text(mid_x, cy, text=f"最后更新：{_LAST_UPDATE}",
                  font=(FF, 9), fill="#666", tags="bg")
    cy += 30

    # 分隔线
    c.create_line(PADDING, cy, width - PADDING, cy, fill="#444", width=1)
    cy += 20

    # 产品介绍 (使用 tk.Label 支持 wraplength)
    desc_w = width - PADDING * 2
    desc_lbl = tk.Label(top, text=_DESC_TEXT, bg=C_PM_BG, fg="#CCC",
                        font=(FF, 10), anchor="nw", justify="left",
                        wraplength=desc_w)
    desc_lbl.place(x=PADDING, y=cy, width=desc_w)
    desc_lbl.lift()
    cy += 110

    # 分隔线
    c.create_line(PADDING, cy, width - PADDING, cy, fill="#444", width=1)
    cy += 60

    # ── QR 码区域 (左图右文) ──
    QR_SIZE = 160
    qr_x = PADDING
    qr_y = cy

    # 尝试加载二维码图片
    _qr_photo = None
    qr_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "wechat_qr.png")
    try:
        img = Image.open(qr_path)
        img = img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
        _qr_photo = ImageTk.PhotoImage(img)
    except Exception:
        _qr_photo = None

    if _qr_photo:
        qr_label = tk.Label(top, image=_qr_photo, bg=C_PM_BG, bd=0)
        qr_label.image = _qr_photo  # 防止 GC
        qr_label.place(x=qr_x, y=qr_y, width=QR_SIZE, height=QR_SIZE)
        qr_label.lift()
    else:
        # 占位文字
        rrect(c, qr_x, qr_y, QR_SIZE, QR_SIZE, 8,
              fill="#3A3A3A", outline="#555", width=1, tags="bg")
        c.create_text(qr_x + QR_SIZE // 2, qr_y + QR_SIZE // 2,
                      text="微信二维码\n(图片缺失)", font=(FF, 10), fill="#888", tags="bg")

    # 右侧说明文字 (垂直居中于二维码区域)
    txt_x = qr_x + QR_SIZE + 14
    txt_w = width - txt_x - PADDING
    txt_y = qr_y

    hint_lbl = tk.Label(top, text=_QR_HINT, bg=C_PM_BG, fg="#AAA",
                        font=(FF, 10), anchor="nw", justify="left",
                        wraplength=txt_w)
    hint_lbl.place(x=txt_x, y=txt_y, width=txt_w)
    hint_lbl.lift()

    return top
