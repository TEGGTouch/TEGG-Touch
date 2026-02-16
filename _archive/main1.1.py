import sys
import time
import traceback
import tkinter as tk
from tkinter import messagebox, filedialog
import ctypes
import json
import os
import random 
import math

# === 依赖检查 ===
try:
    import keyboard
except ImportError:
    print("错误: 找不到 keyboard 库")
    sys.exit()

# === 基础配置 ===
APP_TITLE = "FKB"
CONFIG_FILE = "config.json"

# 赛博配色表
COLOR_BG = "#121212"
COLOR_BTN_BG = "#2A2A2A"
COLOR_BTN_BORDER = "#00FFFF"
COLOR_TEXT = "#FFFFFF"
COLOR_ACTIVE = "#FF0055"
COLOR_HOVER = "#00FF00"
COLOR_PANEL = "#1E1E1E"

# 功能按钮统一配色
COLOR_SYS_BG = "#880000"     # 深红底
COLOR_SYS_BORDER = "#FF0000" # 亮红框
COLOR_SYS_TEXT = "#FFFFFF"

COLOR_BALL_CORE = "#00FFFF"
COLOR_BALL_RING = "#008888"

user32 = ctypes.windll.user32

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

class FloatingApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.buttons_config = []
        self.current_mode = 'main'
        self.transparency = 0.3
        
        # 窗口状态缓存
        self.win_x = 0
        self.win_y = 0
        self.win_w = 640
        self.win_h = 480
        
        # 记录隐藏前的窗口位置大小 (默认保底)
        self.saved_geometry = "640x480+100+100"
        
        # 记录悬浮球的位置
        self.ball_x = None
        self.ball_y = None
        
        # 鼠标硬件状态
        self.left_was_down = False
        self.right_was_down = False
        self.holding_btn_left = None
        self.holding_btn_right = None
        
        # 悬浮球交互状态
        self.is_hidden = False 
        self.ball_drag_start_x = 0
        self.ball_drag_start_y = 0
        self.ball_win_start_x = 0
        self.ball_win_start_y = 0
        self.ball_click_time = 0
        self.dragging_ball = False
        
        # 光标渲染优化标记
        self.cursor_initialized = False

        self.load_config()

        self.root.attributes("-topmost", True) 
        self.root.protocol("WM_DELETE_WINDOW", self.quit) 
        self.root.configure(bg=COLOR_BG)

        self.canvas = tk.Canvas(self.root, bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.root.bind_all("<MouseWheel>", self.on_mouse_wheel)

        self.redraw_all_buttons()

        self.ui_frame = tk.Frame(self.root, bg=COLOR_PANEL, bd=0)
        self.ui_frame.place(relx=0.5, rely=0.92, anchor=tk.CENTER)

        self.setup_ui()
        self.update_loop()

    def load_config(self):
        default_geo = "640x640+100+100"
        default_btns = [
            {'x': 50, 'y': 100, 'w': 100, 'h': 80, 'name': '左上', 'hover': 'w+a', 'lclick': 'j', 'rclick': 'k', 'wheelup': '', 'wheeldown': ''},
            {'x': 200, 'y': 100, 'w': 100, 'h': 80, 'name': '右上', 'hover': 'w+d', 'lclick': 'j', 'rclick': 'k', 'wheelup': '', 'wheeldown': ''},
            {'x': 125, 'y': 200, 'w': 100, 'h': 80, 'name': '后退', 'hover': 's', 'lclick': 'j', 'rclick': 'k', 'wheelup': '', 'wheeldown': ''},
        ]
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    geo = data.get('geometry', default_geo)
                    
                    # 【核心修复】加载时检查尺寸，如果是小球尺寸，强制恢复默认大尺寸
                    # 防止因为上次关闭时是隐藏状态，导致永久变小
                    try:
                        wh = geo.split('+')[0].split('x')
                        w, h = int(wh[0]), int(wh[1])
                        if w < 200 or h < 200: 
                            geo = default_geo
                    except: 
                        geo = default_geo
                        
                    self.root.geometry(geo)
                    self.saved_geometry = geo # 同步保存一份
                    
                    self.transparency = data.get('transparency', 0.3)
                    self.buttons_config = data.get('buttons', default_btns)
                    self.ball_x = data.get('ball_x', None)
                    self.ball_y = data.get('ball_y', None)
            except:
                self.root.geometry(default_geo)
                self.buttons_config = default_btns
        else:
            self.root.geometry(default_geo)
            self.buttons_config = default_btns
        
        self.root.update()
        self.update_geo_cache()

    def update_geo_cache(self):
        # 只有在非隐藏模式下才更新缓存，防止把隐藏后的小窗口尺寸存进去了
        if not self.is_hidden:
            try:
                w = self.root.winfo_width()
                h = self.root.winfo_height()
                # 只有当宽高看起来正常（大于小球尺寸）时才更新
                if w > 100 and h > 100:
                    self.win_w = w
                    self.win_h = h
                    self.win_x = self.root.winfo_rootx()
                    self.win_y = self.root.winfo_rooty()
            except: pass

    def _save_to_file(self, filepath):
        # 保存逻辑安全锁：绝不保存 80x80 这种尺寸作为主窗口尺寸
        current_geo = self.root.geometry()
        try:
            wh = current_geo.split('+')[0].split('x')
            w, h = int(wh[0]), int(wh[1])
            if w < 200 or h < 200:
                # 如果当前是小球，保存 saved_geometry (之前的大窗口记录)
                geo_to_save = self.saved_geometry
            else:
                geo_to_save = current_geo
        except:
            geo_to_save = self.saved_geometry
        
        # 更新悬浮球位置记录
        ball_x_to_save = self.ball_x
        ball_y_to_save = self.ball_y
        if self.is_hidden:
            ball_x_to_save = self.root.winfo_x()
            ball_y_to_save = self.root.winfo_y()

        clean_btns = []
        for b in self.buttons_config:
            clean_btn = {k:v for k,v in b.items() if k not in ['id_rect', 'id_text', 'id_resize', 'active_hover', 'id_poly', 'last_visual_state']}
            if not b.get('deleted'):
                clean_btns.append(clean_btn)
                
        data = {
            'geometry': geo_to_save,
            'transparency': self.transparency,
            'buttons': clean_btns,
            'ball_x': ball_x_to_save,
            'ball_y': ball_y_to_save
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except: return False

    def save_config(self):
        self._save_to_file(CONFIG_FILE)

    def export_config(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("配置", "*.json")], title="导出配置")
        if filepath and self._save_to_file(filepath): messagebox.showinfo("成功", f"配置已导出！")

    def import_config(self):
        filepath = filedialog.askopenfilename(filetypes=[("配置", "*.json")], title="导入配置")
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if 'geometry' in data: self.root.geometry(data['geometry'])
            if 'transparency' in data: self.transparency = data['transparency']
            if 'buttons' in data: self.buttons_config = data['buttons']
            self.redraw_all_buttons()
            if self.current_mode == 'main': self.setup_ui()
            self.save_config()
            messagebox.showinfo("成功", "配置已装载！")
        except Exception as e: messagebox.showerror("错误", f"导入失败:\n{e}")

    def set_window_style(self, window, style_type):
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            if hwnd == 0: hwnd = window.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = old_style
            if style_type == 'normal':
                new_style = new_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT
            elif style_type == 'no_focus':
                new_style = (new_style | WS_EX_LAYERED | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT
            elif style_type == 'click_through':
                new_style = new_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        except: pass

    def redraw_all_buttons(self):
        self.canvas.delete("all")
        self.cursor_initialized = False 
        
        # 隐藏模式：只画球
        if self.is_hidden:
            self.draw_floating_ball()
            return

        # 正常模式：画用户按钮
        valid_buttons = []
        for idx, btn in enumerate(self.buttons_config):
            if btn.get('deleted'): continue
            if 'wheelup' not in btn: btn['wheelup'] = ''
            if 'wheeldown' not in btn: btn['wheeldown'] = ''
            self.create_button_visual(btn, len(valid_buttons))
            valid_buttons.append(btn)
        self.buttons_config = valid_buttons
        
        # 正常模式：画系统按钮
        if self.current_mode == 'run':
            self.draw_control_ui()
            # 强制置顶功能按钮
            self.canvas.tag_raise("exit_btn_ui")
            self.canvas.tag_raise("hide_btn_ui")

    def draw_system_btn(self, x, y, text, tag_name):
        """统一绘制系统功能按钮 (退出/隐藏)"""
        w, h = 80, 35
        # 切角矩形
        points = [x+5, y, x+w, y, x+w, y+h-5, x+w-5, y+h, x, y+h, x, y+5]
        
        self.canvas.create_polygon(points, fill=COLOR_SYS_BG, outline=COLOR_SYS_BORDER, width=2, tags=tag_name)
        self.canvas.create_text(x+w/2, y+h/2, text=text, fill=COLOR_SYS_TEXT, font=("Arial", 9, "bold"), tags=tag_name)

    def draw_control_ui(self):
        # 1. 退出按钮 (10,10)
        self.draw_system_btn(10, 10, "退出(F12)", "exit_btn_ui")
        
        # 2. 隐藏按钮 (100,10) - 样式完全一致，只有位置不同
        self.draw_system_btn(100, 10, "隐藏[-]", "hide_btn_ui")

        if self.current_mode == 'main':
            self.canvas.tag_bind("exit_btn_ui", "<Button-1>", lambda e: self.to_edit())
            
    def draw_floating_ball(self):
        cx, cy = 40, 40 
        r = 25
        points = []
        for i in range(6):
            angle_deg = 60 * i - 30
            angle_rad = math.radians(angle_deg)
            px = cx + r * math.cos(angle_rad)
            py = cy + r * math.sin(angle_rad)
            points.append(px)
            points.append(py)
        
        # 悬浮球主体
        self.canvas.create_polygon(points, fill=COLOR_BG, outline=COLOR_BALL_RING, width=3, tags="float_ball")
        self.canvas.create_oval(cx-10, cy-10, cx+10, cy+10, fill=COLOR_BALL_CORE, outline="white", width=2, tags="float_ball")
        self.canvas.create_text(cx, cy+32, text="展开", fill=COLOR_TEXT, font=("Arial", 8, "bold"), tags="float_ball")

        # 【双重保险】同时绑定 Tkinter 事件，确保至少有一个生效
        self.canvas.tag_bind("float_ball", "<Button-1>", self.on_ball_down)
        self.canvas.tag_bind("float_ball", "<B1-Motion>", self.on_ball_move)
        self.canvas.tag_bind("float_ball", "<ButtonRelease-1>", self.on_ball_up)

    def on_ball_down(self, event):
        self.ball_drag_start_x = event.x_root
        self.ball_drag_start_y = event.y_root
        self.ball_win_start_x = self.root.winfo_x()
        self.ball_win_start_y = self.root.winfo_y()
        self.ball_click_time = time.time()
        self.dragging_ball = False 

    def on_ball_move(self, event):
        dx = event.x_root - self.ball_drag_start_x
        dy = event.y_root - self.ball_drag_start_y
        
        if abs(dx) > 3 or abs(dy) > 3:
            self.dragging_ball = True
            
        if self.dragging_ball:
            new_x = self.ball_win_start_x + dx
            new_y = self.ball_win_start_y + dy
            
            # 边缘保护
            s_w = self.root.winfo_screenwidth()
            s_h = self.root.winfo_screenheight()
            if new_x < 0: new_x = 0
            if new_y < 0: new_y = 0
            if new_x > s_w - 80: new_x = s_w - 80
            if new_y > s_h - 80: ty = s_h - 80
            
            self.root.geometry(f"80x80+{new_x}+{new_y}")

    def on_ball_up(self, event):
        if not self.dragging_ball and (time.time() - self.ball_click_time < 0.3):
            self.to_show()

    def get_chamfered_points(self, x, y, w, h, cut=10):
        return [x+cut, y, x+w-cut, y, x+w, y+cut, x+w, y+h-cut, x+w-cut, y+h, x+cut, y+h, x, y+h-cut, x, y+cut]

    def create_button_visual(self, btn_data, index):
        tags_poly = f"btn_poly_{index}"
        tags_text = f"btn_text_{index}"
        tags_resize = f"btn_resize_{index}"
        
        if 'active_hover' not in btn_data: btn_data['active_hover'] = False
        btn_data['last_visual_state'] = 'init' 
        
        points = self.get_chamfered_points(btn_data['x'], btn_data['y'], btn_data['w'], btn_data['h'], 8)
        poly = self.canvas.create_polygon(points, fill=COLOR_BTN_BG, outline=COLOR_BTN_BORDER, width=2, tags=tags_poly)
        text = self.canvas.create_text(btn_data['x']+btn_data['w']/2, btn_data['y']+btn_data['h']/2, text=f"{btn_data['name']}\n[{btn_data['hover']}]", font=("Consolas", 10, "bold"), fill=COLOR_TEXT, tags=tags_text)
        resize_size = 12
        rx, ry = btn_data['x'] + btn_data['w'], btn_data['y'] + btn_data['h']
        resize_tri = self.canvas.create_polygon(rx, ry, rx - resize_size, ry, rx, ry - resize_size, fill=COLOR_BTN_BORDER, tags=tags_resize)
        btn_data['id_poly'] = poly; btn_data['id_rect'] = poly; btn_data['id_text'] = text; btn_data['id_resize'] = resize_tri
        
        for tag in [tags_poly, tags_text]:
            if self.current_mode == 'main':
                self.canvas.tag_bind(tag, "<B1-Motion>", lambda e, idx=index: self.on_drag(e, idx))
                self.canvas.tag_bind(tag, "<Double-Button-1>", lambda e, idx=index: self.edit_btn(idx))
        if self.current_mode == 'main':
            self.canvas.tag_bind(tags_resize, "<B1-Motion>", lambda e, idx=index: self.on_resize(e, idx))
            self.canvas.tag_bind(tags_resize, "<Button-1>", lambda e: "break")

    def update_cursor_visuals(self, x, y):
        if not self.cursor_initialized:
            self.canvas.create_polygon(0,0,0,0, fill=COLOR_BG, outline=COLOR_BTN_BORDER, width=3, tags=("v_cursor", "v_cursor_body"), smooth=False)
            self.canvas.create_oval(0,0,0,0, fill=COLOR_ACTIVE, outline=COLOR_TEXT, width=1, tags=("v_cursor", "v_cursor_core"))
            self.cursor_initialized = True
            self.canvas.tag_raise("v_cursor")

        arrow_points = [x, y, x+16, y+16, x+12, y+28, x, y+20, x-12, y+28, x-16, y+16]
        self.canvas.coords("v_cursor_body", *arrow_points)
        core_y = y + 18
        self.canvas.coords("v_cursor_core", x-3, core_y-3, x+3, core_y+3)
        self.canvas.tag_raise("v_cursor")

    def setup_ui(self):
        for w in self.ui_frame.winfo_children(): w.destroy()
        btn_style = {"bg": "#333", "fg": "white", "activebackground": "#555", "activeforeground": "white", "bd": 1, "relief": "flat", "font": ("Arial", 9)}
        btn_action_style = {"bg": "#008888", "fg": "white", "activebackground": "#00AAAA", "activeforeground": "white", "bd": 1, "relief": "flat", "font": ("Arial", 9, "bold")}

        if self.current_mode == 'main':
            self.root.overrideredirect(False) 
            self.root.attributes("-alpha", 1.0)
            self.root.configure(bg=COLOR_BG, cursor="arrow")
            self.canvas.configure(bg=COLOR_BG)
            self.root.wm_attributes("-transparentcolor", "")
            self.set_window_style(self.root, 'normal')
            self.canvas.delete("v_cursor")
            self.canvas.delete("exit_btn_ui")
            self.canvas.delete("hide_btn_ui")
            self.canvas.delete("float_ball")
            
            row1 = tk.Frame(self.ui_frame, bg=COLOR_PANEL)
            row1.pack(side=tk.TOP, pady=5, fill=tk.X)
            tk.Button(row1, text="✚ 新建", command=self.add_btn, **btn_style).pack(side=tk.LEFT, padx=5)
            tk.Button(row1, text="▶ 运行", command=self.to_run, **btn_action_style).pack(side=tk.LEFT, padx=5)
            tk.Button(row1, text="⬆ 导出", command=self.export_config, **btn_style).pack(side=tk.LEFT, padx=5)
            tk.Button(row1, text="⬇ 导入", command=self.import_config, **btn_style).pack(side=tk.LEFT, padx=5)

            row2 = tk.Frame(self.ui_frame, bg=COLOR_PANEL)
            row2.pack(side=tk.TOP, pady=5, fill=tk.X)
            tk.Label(row2, text="透明度:", bg=COLOR_PANEL, fg=COLOR_BTN_BORDER, font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
            s = tk.Scale(row2, from_=10, to=90, orient=tk.HORIZONTAL, command=self.set_alpha, bg=COLOR_PANEL, fg=COLOR_BTN_BORDER, highlightthickness=0, troughcolor="#404040", activebackground=COLOR_BTN_BORDER, length=120)
            s.set(int(self.transparency*100))
            s.pack(side=tk.LEFT)

        elif self.current_mode == 'run':
            self.ui_frame.place_forget()
            self.save_config()
            self.root.overrideredirect(True) 
            self.root.attributes("-alpha", self.transparency)
            self.root.configure(bg='#010001', cursor="none") 
            self.canvas.configure(bg='#010001')
            self.root.wm_attributes("-transparentcolor", "#010001")
            self.set_window_style(self.root, 'no_focus')

    def set_alpha(self, v): self.transparency = int(v)/100.0
    
    def to_edit(self): 
        self.current_mode = 'main'
        self.is_hidden = False
        self.ui_frame.place(relx=0.5, rely=0.92, anchor=tk.CENTER)
        self.setup_ui()
        self.redraw_all_buttons()
        
    def to_run(self): 
        self.update_geo_cache()
        self.current_mode = 'run'
        self.is_hidden = False
        self.setup_ui()
        self.redraw_all_buttons()
        self.root.update()
        self.last_cursor_x = -9999
        self.last_cursor_y = -9999

    def to_hide(self):
        # 1. 记录大窗口尺寸 (如果当前尺寸合法)
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w > 100 and h > 100:
                self.saved_geometry = self.root.geometry()
        except: pass
        
        self.is_hidden = True
        
        # 2. 确定悬浮球位置
        target_x = 0
        target_y = 0
        if self.ball_x is not None and self.ball_y is not None:
            target_x = self.ball_x
            target_y = self.ball_y
        else:
            target_x = self.root.winfo_x() + 50
            target_y = self.root.winfo_y() + 50
            
        self.root.geometry(f"80x80+{target_x}+{target_y}")
        self.redraw_all_buttons() 

    def to_show(self):
        self.ball_x = self.root.winfo_x()
        self.ball_y = self.root.winfo_y()
        self.is_hidden = False
        
        # 3. 恢复尺寸 (带安全校验)
        geo = self.saved_geometry
        if "80x80" in geo: geo = "640x480+100+100" # 终极保底
        
        self.root.geometry(geo)
        self.redraw_all_buttons()
        self.root.update()
        self.update_geo_cache()

    def quit(self): 
        self.save_config()
        self.root.destroy()
        sys.exit()
    
    def add_btn(self):
        cw = self.root.winfo_width()
        ch = self.root.winfo_height()
        new_btn = {'x': cw//2-40, 'y': ch//2-40, 'w': 80, 'h': 80, 'name': '按钮', 'hover': '', 'lclick': '', 'rclick': '', 'wheelup': '', 'wheeldown': ''}
        self.buttons_config.append(new_btn)
        self.redraw_all_buttons()

    def on_drag(self, e, idx):
        if self.current_mode != 'main': return
        btn = self.buttons_config[idx]
        btn['x'] = max(0, min(self.root.winfo_width()-btn['w'], e.x - btn['w']/2))
        btn['y'] = max(0, min(self.root.winfo_height()-btn['h'], e.y - btn['h']/2))
        self.update_btn_coords(idx)

    def on_resize(self, e, idx):
        if self.current_mode != 'main': return
        btn = self.buttons_config[idx]
        new_w = e.x - btn['x']
        new_h = e.y - btn['y']
        btn['w'] = max(40, new_w)
        btn['h'] = max(40, new_h)
        self.update_btn_coords(idx)

    def update_btn_coords(self, idx):
        btn = self.buttons_config[idx]
        points = self.get_chamfered_points(btn['x'], btn['y'], btn['w'], btn['h'], 8)
        self.canvas.coords(btn['id_poly'], *points)
        self.canvas.coords(btn['id_text'], btn['x']+btn['w']/2, btn['y']+btn['h']/2)
        resize_size = 12
        rx, ry = btn['x'] + btn['w'], btn['y'] + btn['h']
        self.canvas.coords(btn['id_resize'], rx, ry, rx - resize_size, ry, rx, ry - resize_size)

    def open_virtual_keyboard(self, entry_widget):
        vk = tk.Toplevel(self.root)
        vk.title("选择按键")
        vk.geometry("800x400")
        vk.configure(bg="#222")
        vk.attributes("-topmost", True)
        
        keys_layout = [
            ["Esc", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"],
            ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace"],
            ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
            ["Caps", "a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "Enter"],
            ["Shift", "z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "Up", "Shift"],
            ["Ctrl", "Win", "Alt", "Space", "Alt", "Left", "Down", "Right", "Ctrl"],
            ["Insert", "Home", "PgUp", "Delete", "End", "PgDn"]
        ]

        def on_key_click(key):
            current_text = entry_widget.get().strip()
            if current_text: new_text = f"{current_text}+{key}"
            else: new_text = key
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, new_text)
            
        def clear_entry():
            entry_widget.delete(0, tk.END)

        main_frame = tk.Frame(vk, bg="#222")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        for r, row_keys in enumerate(keys_layout):
            row_frame = tk.Frame(main_frame, bg="#222")
            row_frame.pack(fill="x", pady=2)
            for key in row_keys:
                width = 4
                if key in ["Space", "Enter", "Shift", "Backspace", "Caps", "Tab"]: width = 8
                btn = tk.Button(row_frame, text=key, width=width, height=2, 
                                bg=COLOR_BTN_BG, fg="white", activebackground=COLOR_BTN_BORDER,
                                command=lambda k=key: on_key_click(k))
                btn.pack(side="left", padx=2, fill="x", expand=True if key=="Space" else False)

        bottom_frame = tk.Frame(vk, bg="#222")
        bottom_frame.pack(side="bottom", fill="x", pady=10)
        tk.Button(bottom_frame, text="清除当前框", command=clear_entry, bg="#880000", fg="white", width=15).pack(side="left", padx=20)
        tk.Button(bottom_frame, text="完成关闭", command=vk.destroy, bg="#008800", fg="white", width=15).pack(side="right", padx=20)

    def edit_btn(self, idx):
        if self.current_mode != 'main': return
        btn = self.buttons_config[idx]
        top = tk.Toplevel(self.root)
        top.geometry("360x600")
        top.attributes("-topmost", True)
        top.title("编辑")
        top.configure(bg="#222") 
        self.set_window_style(top, 'normal')
        
        entries = {}
        tk.Label(top, text="[ 图形化配置 ]", fg=COLOR_BTN_BORDER, bg="#222", font=("Arial", 12, "bold")).pack(pady=10)
        
        fields = [
            ('name', '按钮名称', False),
            ('lclick', '左键模拟', True),
            ('hover', '悬浮模拟', True),
            ('rclick', '右键模拟', True),
            ('wheelup', '滚轮上滚模拟', True),
            ('wheeldown', '滚轮下滚模拟', True)
        ]
        
        for k, txt, use_vk in fields:
            if k not in btn: btn[k] = ''
            frame = tk.Frame(top, bg="#222")
            frame.pack(fill="x", padx=20, pady=5)
            tk.Label(frame, text=txt, fg="white", bg="#222", width=12, anchor="w").pack(side="left")
            e = tk.Entry(frame, font=("Arial", 10), bg="#444", fg="white", insertbackground="white")
            e.insert(0, btn[k])
            e.pack(side="left", fill="x", expand=True)
            entries[k] = e
            if use_vk:
                vk_btn = tk.Button(frame, text="+", width=3, bg=COLOR_BTN_BG, fg=COLOR_BTN_BORDER,
                                   command=lambda ent=e: self.open_virtual_keyboard(ent))
                vk_btn.pack(side="right", padx=(5, 0))
            
        def save():
            for k in entries: 
                val = entries[k].get().replace(" ", "").lower()
                if k == 'name': val = entries[k].get() 
                btn[k] = val
            self.canvas.itemconfigure(btn['id_text'], text=f"{btn['name']}\n[{btn['hover']}]")
            top.destroy()
        
        def delete():
            btn['deleted'] = True
            self.redraw_all_buttons()
            top.destroy()

        tk.Button(top, text="保存", command=save, bg="#008888", fg="white", relief="flat", width=20).pack(pady=15)
        tk.Button(top, text="删除", command=delete, bg="#880000", fg="white", relief="flat", width=20).pack(pady=5)

    def trigger(self, keys, action):
        if not keys: return
        key_list = [k.strip() for k in keys.split('+') if k.strip()]
        if not key_list: return
        try:
            for k in key_list:
                scan_code = get_scan_code(k)
                if scan_code == 0: continue
                if action == 'p': PressKey(scan_code)
                elif action == 'r': ReleaseKey(scan_code)
                elif action == 'c':
                    PressKey(scan_code)
                    time.sleep(random.uniform(0.03, 0.06))
                    ReleaseKey(scan_code)
        except: pass

    def on_mouse_wheel(self, event):
        if self.current_mode != 'run' or self.is_hidden: return
        abs_x = event.x_root
        abs_y = event.y_root
        rel_x = abs_x - self.win_x
        rel_y = abs_y - self.win_y
        direction = 'up' if event.delta > 0 else 'down'
        for btn in self.buttons_config:
            if btn.get('deleted'): continue
            if btn['x'] <= rel_x < btn['x'] + btn['w'] and btn['y'] <= rel_y < btn['y'] + btn['h']:
                key_to_press = btn.get('wheelup') if direction == 'up' else btn.get('wheeldown')
                if key_to_press:
                    self.trigger(key_to_press, 'c')
                    self.canvas.itemconfigure(btn['id_poly'], fill=COLOR_ACTIVE)
                    self.root.after(100, lambda b=btn: self.restore_btn_color(b))
    
    def restore_btn_color(self, btn):
        if not btn.get('deleted'):
            self.canvas.itemconfigure(btn['id_poly'], fill=COLOR_BTN_BG)

    def update_loop(self):
        try:
            if self.current_mode == 'run':
                if keyboard.is_pressed('F12'):
                    self.to_edit()
                    time.sleep(0.3)
                    self.root.after(1, self.update_loop)
                    return

                self.root.lift() 
                
                abs_x, abs_y = self.root.winfo_pointerxy()
                win_x = self.root.winfo_rootx()
                win_y = self.root.winfo_rooty()
                rel_x = abs_x - win_x
                rel_y = abs_y - win_y
                
                if not self.is_hidden:
                    if 0 <= rel_x <= self.win_w and 0 <= rel_y <= self.win_h:
                        self.update_cursor_visuals(rel_x, rel_y)
                    else:
                        self.canvas.delete("v_cursor")
                        self.cursor_initialized = False
                else:
                    self.canvas.delete("v_cursor")

                left_is_down = (user32.GetAsyncKeyState(0x01) & 0x8000) != 0
                right_is_down = (user32.GetAsyncKeyState(0x02) & 0x8000) != 0

                # === 悬浮球检测 (硬件级) ===
                if self.is_hidden:
                    dist_sq = (rel_x - 40)**2 + (rel_y - 40)**2
                    
                    if left_is_down and not self.left_was_down:
                        if dist_sq <= 25**2: 
                            self.ball_dragging = True
                            self.ball_drag_start_x = abs_x
                            self.ball_drag_start_y = abs_y
                            self.ball_win_start_x = self.root.winfo_x()
                            self.ball_win_start_y = self.root.winfo_y()
                            self.ball_click_time = time.time()
                    
                    if self.ball_dragging:
                        if left_is_down:
                            dx = abs_x - self.ball_drag_start_x
                            dy = abs_y - self.ball_drag_start_y
                            new_x = self.ball_win_start_x + dx
                            new_y = self.ball_win_start_y + dy
                            s_w = self.root.winfo_screenwidth()
                            s_h = self.root.winfo_screenheight()
                            w = 80
                            h = 80
                            if new_x < 0: new_x = 0
                            if new_y < 0: new_y = 0
                            if new_x > s_w - w: new_x = s_w - w
                            if new_y > s_h - h: new_y = s_h - h
                            self.root.geometry(f"80x80+{new_x}+{new_y}")
                        else:
                            self.ball_dragging = False
                            click_dur = time.time() - self.ball_click_time
                            drag_dist = (abs_x - self.ball_drag_start_x)**2 + (abs_y - self.ball_drag_start_y)**2
                            if click_dur < 0.3 and drag_dist < 100:
                                self.to_show()

                    self.left_was_down = left_is_down
                    self.root.after(1, self.update_loop)
                    return

                # === 退出/隐藏检测 (硬件级) ===
                if left_is_down and not self.left_was_down:
                    if 10 <= rel_x <= 90 and 10 <= rel_y <= 45:
                        self.to_edit()
                        self.left_was_down = True
                        self.root.after(1, self.update_loop)
                        return
                    if 100 <= rel_x <= 180 and 10 <= rel_y <= 45:
                        self.to_hide()
                        self.left_was_down = True
                        self.root.after(1, self.update_loop)
                        return

                for idx, btn in enumerate(self.buttons_config):
                    if btn.get('deleted'): continue
                    in_x = btn['x'] <= rel_x < btn['x'] + btn['w']
                    in_y = btn['y'] <= rel_y < btn['y'] + btn['h']
                    
                    target_state = 'normal'
                    if in_x and in_y:
                        target_state = 'hover'
                        if left_is_down: target_state = 'active_left'
                        if right_is_down: target_state = 'active_right'
                    
                    if btn.get('last_visual_state') != target_state:
                        outline = COLOR_BTN_BORDER
                        width = 2
                        fill = COLOR_BTN_BG
                        text_fill = COLOR_TEXT
                        
                        if target_state != 'normal': 
                            outline = COLOR_HOVER
                            width = 3
                            text_fill = COLOR_HOVER
                            if target_state == 'active_left' or target_state == 'active_right':
                                outline = COLOR_ACTIVE
                                text_fill = COLOR_ACTIVE
                        
                        self.canvas.itemconfigure(btn['id_poly'], outline=outline, width=width, fill=fill)
                        self.canvas.itemconfigure(btn['id_text'], fill=text_fill)
                        btn['last_visual_state'] = target_state

                    if in_x and in_y:
                        if not btn['active_hover']:
                            btn['active_hover'] = True
                            self.trigger(btn['hover'], 'p')
                        
                        if left_is_down and not self.left_was_down:
                            self.holding_btn_left = idx
                            self.trigger(btn['lclick'], 'p')
                        if right_is_down and not self.right_was_down:
                            self.holding_btn_right = idx
                            self.trigger(btn['rclick'], 'p')
                    else:
                        if btn['active_hover']:
                            btn['active_hover'] = False
                            self.trigger(btn['hover'], 'r')

                if not left_is_down and self.left_was_down:
                    if self.holding_btn_left is not None:
                        btn = self.buttons_config[self.holding_btn_left]
                        if not btn.get('deleted'): self.trigger(btn['lclick'], 'r')
                        self.holding_btn_left = None
                
                if not right_is_down and self.right_was_down:
                    if self.holding_btn_right is not None:
                        btn = self.buttons_config[self.holding_btn_right]
                        if not btn.get('deleted'): self.trigger(btn['rclick'], 'r')
                        self.holding_btn_right = None

                self.left_was_down = left_is_down
                self.right_was_down = right_is_down
        except: pass
        self.root.after(1, self.update_loop)

# === 辅助函数 (保持不变) ===
PUL = ctypes.POINTER(ctypes.c_ulong)
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),("wScan", ctypes.c_ushort),("dwFlags", ctypes.c_ulong),("time", ctypes.c_ulong),("dwExtraInfo", PUL)]
class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),("wParamL", ctypes.c_short),("wParamH", ctypes.c_ushort)]
class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),("dy", ctypes.c_long),("mouseData", ctypes.c_ulong),("dwFlags", ctypes.c_ulong),("time", ctypes.c_ulong),("dwExtraInfo", PUL)]
class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),("mi", MouseInput),("hi", HardwareInput)]
class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),("ii", Input_I)]
SendInput = ctypes.windll.user32.SendInput
def PressKey(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hexKeyCode, 0x0008, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
def ReleaseKey(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hexKeyCode, 0x0008 | 0x0002, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
def get_scan_code(key_name):
    try: return keyboard.key_to_scan_codes(key_name)[0]
    except: return 0

if __name__ == "__main__":
    root = tk.Tk()
    app = FloatingApp(root)
    root.mainloop()