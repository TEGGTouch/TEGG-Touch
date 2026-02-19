"""
TEGG Touch 辅助软件 - 启动入口

"""

import sys
import tkinter as tk
import traceback
from tkinter import messagebox
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='teggtouch.log',
    filemode='w'
)
logger = logging.getLogger(__name__)

# 依赖检查
try:
    import keyboard
except ImportError:
    msg = "错误: 找不到 keyboard 库\n请运行: pip install keyboard"
    print(msg)
    try:
        import tkinter
        tkinter.messagebox.showerror("依赖缺失", msg)
    except:
        pass
    sys.exit(1)

from ui.app import FloatingApp

def main():
    try:
        root = tk.Tk()
        app = FloatingApp(root)
        root.mainloop()
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        messagebox.showerror("严重错误", f"程序发生未捕获异常:\n{e}\n请查看 teggtouch.log")

if __name__ == "__main__":
    main()
