"""
TEGG Touch - 全局常量与默认值
"""

import os
import sys
from core.i18n import t, get_font

# === 应用根目录（frozen 兼容） ===
# 开发时: TEGGTouch/ (项目根)
# 打包后: dist/TEGGTouch/ (EXE 所在目录，__file__ 在 _internal/ 内)
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# === 应用信息 ===
APP_VERSION = "0.2.0"
CONFIG_FILE = "config.json"
PROFILES_DIR = "profiles"
PROFILES_INDEX = "_index.json"
DEFAULT_PROFILE_NAME = "Default"  # 固定英文作为文件名 key，显示名用 t("profile.default_name")
HOTKEYS_FILE = "settings/hotkeys.json"

def get_app_title():
    """返回本地化的应用标题。"""
    return t("app.title")

# === 默认快捷键映射 ===
DEFAULT_HOTKEYS = {
    "voice":          "f5",
    "auto_center":    "f6",
    "toggle_buttons": "f7",
    "soft_keyboard":  "f8",
    "pt_on":          "f9",
    "pt_off":         "f10",
    "pt_block":       "f11",
    "stop":           "f12",
    "auto_center_delay": 1500,
}

def get_hotkey_labels():
    """返回本地化的快捷键显示名称（运行时求值）。"""
    return {
        "voice":          t("hotkey.voice"),
        "auto_center":    t("hotkey.auto_center"),
        "toggle_buttons": t("hotkey.toggle_buttons"),
        "soft_keyboard":  t("hotkey.soft_keyboard"),
        "pt_on":          t("hotkey.pt_on"),
        "pt_off":         t("hotkey.pt_off"),
        "pt_block":       t("hotkey.pt_block"),
        "stop":           t("hotkey.stop"),
    }

# === 清晰高对比配色表 (High Clarity) ===
COLOR_BG = "#202020"          # 深灰背景，降低干扰
COLOR_BTN_BG = "#111111"      # 按钮常态：深灰
COLOR_BTN_BORDER = "#555555"  # 按钮边框：灰色
COLOR_TEXT = "#FFFFFF"        # 文字：纯白
COLOR_ACTIVE = "#005A9E"      # 激活/按下：深蓝
COLOR_HOVER = "#0078D7"       # 悬停：亮蓝
COLOR_PANEL = "#2D2D2D"       # 底部面板：稍浅的深灰

# 系统功能按钮配色
COLOR_SYS_BG = "#C42B1C"      # 退出/隐藏：醒目的红
COLOR_SYS_BORDER = "#FFFFFF"
COLOR_SYS_TEXT = "#FFFFFF"

# 悬浮球配色
COLOR_BALL_CORE = "#0078D7"   # 核心：亮蓝
COLOR_BALL_RING = "#FFFFFF"   # 环：亮白

# 调整手柄配色
COLOR_HANDLE = "#555555"      # 灰色，与边框统一

# 透明背景色 (用于 wm_attributes transparentcolor)
COLOR_TRANSPARENT = "#010001"
COLOR_TOOLBAR_TRANSPARENT = "#010002"  # 工具栏窗口镂空用

# === 按钮类型 ===
BTN_TYPE_NORMAL = "normal"
BTN_TYPE_CENTER_BAND = "center_band"
BTN_TYPE_WHEEL_SECTOR = "wheel_sector"
BTN_TYPE_WHEEL_RING = "wheel_center_ring"
BTN_TYPE_WHEEL_INNER_RING = "wheel_inner_ring"

# === 中心轮盘配置 ===
# 碰撞区域（hit test）— 相邻组件碰撞半径无缝衔接，无死区
WHEEL_INNER_RADIUS = 60    # 碰撞内径 (px) — 小版
WHEEL_OUTER_RADIUS = 150   # 碰撞外径 (px) — 小版
WHEEL_INNER_RADIUS_LARGE = 110   # 碰撞内径 (px) — 大版
WHEEL_OUTER_RADIUS_LARGE = 200   # 碰撞外径 (px) — 大版
WHEEL_GAP_PX = 10           # 扇面视觉间距 (像素)
WHEEL_SECTOR_COUNT = 8
WHEEL_MAX_OFFSET = 300       # 轮盘缩放最大偏移 (px)
WHEEL_RESIZE_BTN_SIZE = 30   # 缩放按钮尺寸

# 视觉偏移 — 视觉区域比碰撞区域各方向缩进，产生视觉间隔但交互无死区
WHEEL_VISUAL_INSET = 5      # 视觉区域比碰撞区域各方向缩进 (px)

# 中心圆环按钮 (单环/三环模式可见)
WHEEL_RING_INNER = 70       # 碰撞内径 (px) — 单环模式
WHEEL_RING_OUTER = 110      # 碰撞外径 (px) — 与大版扇面碰撞内径无缝衔接

# 三环模式尺寸 (inner_ring + outer_ring + 8-sector)
WHEEL_TRIPLE_INNER_RING_INNER = 80    # 内环碰撞内径 (px)
WHEEL_TRIPLE_INNER_RING_OUTER = 120   # 内环碰撞外径 (px)
WHEEL_TRIPLE_OUTER_RING_INNER = 120   # 中环碰撞内径 (px) — 与内环无缝衔接
WHEEL_TRIPLE_OUTER_RING_OUTER = 160   # 中环碰撞外径 (px)
WHEEL_TRIPLE_SECTOR_INNER = 160       # 八向环碰撞内径 (px) — 与中环无缝衔接
WHEEL_TRIPLE_SECTOR_OUTER = 240       # 八向环碰撞外径 (px)

# 8个扇面方向定义 (名称, 中心角度-tkinter角度, 默认hover键)
# tkinter arc: 0°=右, 逆时针增加, 90°=上
WHEEL_SECTORS_DEF = [
    {"name": "↑",  "angle": 90,  "hover": "w"},
    {"name": "↖",  "angle": 135, "hover": "w+a"},
    {"name": "←",  "angle": 180, "hover": "a"},
    {"name": "↙",  "angle": 225, "hover": "a+s"},
    {"name": "↓",  "angle": 270, "hover": "s"},
    {"name": "↘",  "angle": 315, "hover": "s+d"},
    {"name": "→",  "angle": 0,   "hover": "d"},
    {"name": "↗",  "angle": 45,  "hover": "d+w"},
]

def default_wheel_sectors():
    """生成默认的8个轮盘扇区配置。"""
    sectors = []
    for s in WHEEL_SECTORS_DEF:
        sectors.append({
            'name': s['name'],
            'type': BTN_TYPE_WHEEL_SECTOR,
            'angle': s['angle'],
            'hover': s['hover'],
            'hover_delay': 200,
            'hover_release_delay': 0,
            'lclick': '', 'rclick': '', 'mclick': '',
            'wheelup': '', 'wheeldown': '',
        })
    return sectors

def default_wheel_center_ring():
    """生成默认的中心圆环按钮配置（单环/三环模式可见）。"""
    return {
        'name': t("button_defaults.center_ring"),
        'type': BTN_TYPE_WHEEL_RING,
        'hover': '', 'hover_delay': 200,
        'hover_release_delay': 0,
        'lclick': '', 'rclick': '', 'mclick': '',
        'wheelup': '', 'wheeldown': '',
        'xbutton1': '', 'xbutton2': '',
    }

def default_wheel_inner_ring():
    """生成默认的中二环按钮配置（双环模式的中间环）。"""
    return {
        'name': t("button_defaults.inner_ring"),
        'type': BTN_TYPE_WHEEL_INNER_RING,
        'hover': '', 'hover_delay': 200,
        'hover_release_delay': 0,
        'lclick': '', 'rclick': '', 'mclick': '',
        'wheelup': '', 'wheeldown': '',
        'xbutton1': '', 'xbutton2': '',
    }

# === 工具栏尺寸 ===
TOOLBAR_WIDTH = 1070
TOOLBAR_HEIGHT = 104
TOOLBAR_RADIUS = 12
TOOLBAR_PADDING = 12
TOOLBAR_BOTTOM_MARGIN = 100  # 距屏幕底部间距

# === 尺寸与间隔 ===
DEFAULT_TRANSPARENCY = 0.75
EDIT_ALPHA = 0.6              # 编辑模式半透明度（让用户能看到底下的画面）
BALL_SIZE = 80
MIN_WINDOW_SIZE = 200
MIN_BTN_SIZE = 100
RESIZE_HANDLE_SIZE = 30       # 调整手柄尺寸 (直角三角形 30x30)
CHAMFER_SIZE = 8
GRID_SIZE = 100               # 网格吸附尺寸 (100px) — 旧版兼容，新代码用 DEFAULT_GRID_SIZE
DEFAULT_GRID_SIZE = 100       # 默认网格大小
MIN_GRID_SIZE = 60            # 最小网格
MAX_GRID_SIZE = 100           # 最大网格
GRID_STEP = 10                # 网格步进
BTN_MARGIN = 5                # 按钮边距
BTN_RADIUS = 10               # 按钮圆角半径

# 轮询间隔 (ms) — 约 120fps，兼顾流畅与 CPU 占用
UPDATE_INTERVAL = 8



# 按钮运行时字段 (保存时需要剔除)
RUNTIME_FIELDS = frozenset({
    'id_rect', 'id_text', 'id_resize', 'id_poly',
    'active_hover', 'last_visual_state',
    '_wheel_flash_until',
    '_hover_enter_time', '_hover_charged', 'id_charge',
    '_hover_release_time',
    '_sx', '_sy',  # 缓存的屏幕坐标（逻辑坐标+偏移）
})

# === 穿透模式三态常量 ===
PT_ON = "pt_on"        # 完全穿透：点击穿透到下层游戏/桌面
PT_OFF = "pt_off"      # 智能穿透：按钮拦截，空白穿透
PT_BLOCK = "pt_block"  # 不穿透：所有输入都被拦截
PT_CYCLE = [PT_ON, PT_OFF, PT_BLOCK]  # 循环顺序

# 不穿透模式覆盖色（半透明黑，提示用户当前处于拦截状态）
COLOR_BLOCK_OVERLAY = "#1A1A1A"

# === 语音识别配置 ===
VOICE_MODELS_DIR = os.path.join(APP_DIR, "models", "vosk")
VOICE_SAMPLE_RATE = 16000       # Vosk 推荐采样率
VOICE_CHUNK_SIZE = 4000         # 每次读取的采样数 (~250ms @16kHz)
VOICE_MODEL_MAP = {
    "zh-CN": "vosk-model-small-cn-0.22",
    "en":    "vosk-model-small-en-us-0.15",
}

# 按钮可选字段及默认值 (兼容旧配置)
BUTTON_OPTIONAL_DEFAULTS = {
    'type': BTN_TYPE_NORMAL,  # 按钮类型：normal=普通按钮, center_band=回中带
    'wheelup': '',
    'wheeldown': '',
    'mclick': '',
    'xbutton1': '',  # 鼠标侧键1（后退键）
    'xbutton2': '',  # 鼠标侧键2（前进键）
    'hover_delay': 200,  # 悬停触发延迟(ms)，0=立即触发，默认200ms防误触
    'hover_release_delay': 0,  # 悬停释放延迟(ms)，0=立即释放，默认0ms
}
