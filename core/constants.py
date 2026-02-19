"""
TEGG Touch 辅助软件 - 全局常量与默认值
"""

# === 应用信息 ===
APP_TITLE = "TEGG Touch"
APP_VERSION = "0.1"
CONFIG_FILE = "config.json"
PROFILES_DIR = "profiles"
PROFILES_INDEX = "_index.json"
DEFAULT_PROFILE_NAME = "默认配置"

# === 清晰高对比配色表 (High Clarity) ===
COLOR_BG = "#202020"          # 深灰背景，降低干扰
COLOR_BTN_BG = "#000000"      # 按钮常态：黑色
COLOR_BTN_BORDER = "#666666"  # 按钮边框：灰色
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
COLOR_HANDLE = "#666666"      # 灰色，与边框统一

# 透明背景色 (用于 wm_attributes transparentcolor)
COLOR_TRANSPARENT = "#010001"
COLOR_TOOLBAR_TRANSPARENT = "#010002"  # 工具栏窗口镂空用

# === 工具栏尺寸 ===
TOOLBAR_WIDTH = 950
TOOLBAR_HEIGHT = 104
TOOLBAR_RADIUS = 12
TOOLBAR_PADDING = 12
TOOLBAR_BOTTOM_MARGIN = 100  # 距屏幕底部间距

# === 尺寸与间隔 ===
DEFAULT_TRANSPARENCY = 0.3
EDIT_ALPHA = 0.6              # 编辑模式半透明度（让用户能看到底下的画面）
BALL_SIZE = 80
MIN_WINDOW_SIZE = 200
MIN_BTN_SIZE = 100
RESIZE_HANDLE_SIZE = 30       # 调整手柄尺寸 (直角三角形 30x30)
CHAMFER_SIZE = 8
GRID_SIZE = 100               # 网格吸附尺寸 (100px)
BTN_MARGIN = 5                # 按钮边距
BTN_RADIUS = 10               # 按钮圆角半径

# 轮询间隔 (ms) — 约 120fps，兼顾流畅与 CPU 占用
UPDATE_INTERVAL = 8


# === 默认按钮配置 ===
# 坐标系：中心原点（x,y 可为负数，绘制时 screen_x = x + screen_w//2）
DEFAULT_BUTTONS = [
    {
        'x': -100, 'y': -100, 'w': 100, 'h': 100,
        'name': '左上', 'hover': 'w+a', 'hover_delay': 200,
        'lclick': 'j', 'rclick': 'k', 'mclick': '',
        'wheelup': '', 'wheeldown': '',
    },
    {
        'x': 0, 'y': -100, 'w': 100, 'h': 100,
        'name': '右上', 'hover': 'w+d', 'hover_delay': 200,
        'lclick': 'j', 'rclick': 'k', 'mclick': '',
        'wheelup': '', 'wheeldown': '',
    },
    {
        'x': -100, 'y': 0, 'w': 200, 'h': 100,
        'name': '后退', 'hover': 's', 'hover_delay': 200,
        'lclick': 'j', 'rclick': 'k', 'mclick': '',
        'wheelup': '', 'wheeldown': '',
    },
]

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

# 按钮可选字段及默认值 (兼容旧配置)
BUTTON_OPTIONAL_DEFAULTS = {
    'wheelup': '',
    'wheeldown': '',
    'mclick': '',
    'hover_delay': 200,  # 悬停触发延迟(ms)，0=立即触发，默认200ms防误触
    'hover_release_delay': 0,  # 悬停释放延迟(ms)，0=立即释放，默认0ms
}
