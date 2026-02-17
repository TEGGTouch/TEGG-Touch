"""
TEGG Touch 辅助软件 - 虚拟键盘弹窗

独立的虚拟键盘组件，用于在编辑按钮时选择按键。
"""

import tkinter as tk
from core.constants import COLOR_BTN_BG, COLOR_BTN_BORDER

# 键盘布局
KEYS_LAYOUT = [
    ["Esc", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"],
    ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace"],
    ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["Caps", "a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "Enter"],
    ["Shift", "z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "Up", "Shift"],
    ["Ctrl", "Win", "Alt", "Space", "Alt", "Left", "Down", "Right", "Ctrl"],
    ["Insert", "Home", "PgUp", "Delete", "End", "PgDn"],
]

WIDE_KEYS = {"Space", "Enter", "Shift", "Backspace", "Caps", "Tab"}


def open_virtual_keyboard(parent, entry_widget):
    """打开虚拟键盘弹窗，点击按键会追加到 entry_widget 中。"""
    vk = tk.Toplevel(parent)
    vk.title("选择按键")
    vk.geometry("800x400")
    vk.configure(bg="#222")
    vk.attributes("-topmost", True)

    def on_key_click(key):
        current = entry_widget.get().strip()
        new_text = f"{current}+{key}" if current else key
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, new_text)

    def clear_entry():
        entry_widget.delete(0, tk.END)

    # 键盘主体
    main_frame = tk.Frame(vk, bg="#222")
    main_frame.pack(expand=True, fill="both", padx=10, pady=10)

    for row_keys in KEYS_LAYOUT:
        row_frame = tk.Frame(main_frame, bg="#222")
        row_frame.pack(fill="x", pady=2)
        for key in row_keys:
            width = 8 if key in WIDE_KEYS else 4
            btn = tk.Button(
                row_frame, text=key, width=width, height=2,
                bg=COLOR_BTN_BG, fg="white", activebackground=COLOR_BTN_BORDER,
                command=lambda k=key: on_key_click(k),
            )
            btn.pack(side="left", padx=2, fill="x", expand=(key == "Space"))

    # 底部操作栏
    bottom_frame = tk.Frame(vk, bg="#222")
    bottom_frame.pack(side="bottom", fill="x", pady=10)
    tk.Button(
        bottom_frame, text="清除当前框", command=clear_entry,
        bg="#880000", fg="white", width=15,
    ).pack(side="left", padx=20)
    tk.Button(
        bottom_frame, text="完成关闭", command=vk.destroy,
        bg="#008800", fg="white", width=15,
    ).pack(side="right", padx=20)
