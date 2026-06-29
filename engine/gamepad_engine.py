"""
TEGG Touch 蛋挞 — 手柄引擎: VX360Gamepad 封装 + 帧聚合

设计:
- 调用方写入按钮 / 摇杆 / 扳机, 内部仅标记 dirty
- 帧末统一 flush() 调一次 _pad.update(), 避免 USB 包风暴
- VX360Gamepad() 实例化在 ViGEmBus 未加载时会抛异常 → get() 捕获返回 None
- 进程单例: 整个 app 只创建 1 个虚拟手柄设备
- LT/RT 在 gp_button 编辑器里可作为「按钮」使用 (press = 1.0, release = 0.0),
  路由到 set_trigger api, 因为 XUSB_BUTTON 枚举中 LT/RT 不是 button 而是 trigger

vgamepad 惰性导入:
- vgamepad 的 __init__.py 顶层执行 VBus() → vigem_connect, ViGEmBus 驱动
  未装时会抛 VIGEM_ERROR_BUS_NOT_FOUND (普通 Exception, 不是 ImportError)。
- 模块顶层 import 会让整个 app 启动崩溃,所以这里改成惰性 — 只在切到
  手柄模式 / 实际 get() 时才尝试。
- retry_import() 供安装对话框成功后调用,让用户装完驱动不用重启 app。
"""

import atexit
import logging
import sys
import threading

logger = logging.getLogger(__name__)

# 惰性导入状态: _vg 是成功导入的模块缓存; _vg_attempted 是失败缓存避免每帧重试
_vg = None
_vg_attempted = False


def _try_import_vgamepad(force_retry: bool = False):
    """惰性 import vgamepad; 成功返回模块, 失败返回 None。

    首次失败后会缓存(避免每帧重跑 ctypes 调用), 除非 force_retry=True。
    安装对话框装完驱动后应调 retry_import() 强制重试。
    """
    global _vg, _vg_attempted
    if _vg is not None:
        return _vg
    if _vg_attempted and not force_retry:
        return None
    _vg_attempted = True
    # 清掉上次 partial import 残留 (vgamepad/__init__.py 抛异常时
    # submodule 可能已进 sys.modules, 不清会污染重试)
    for k in list(sys.modules.keys()):
        if k == 'vgamepad' or k.startswith('vgamepad.'):
            del sys.modules[k]
    try:
        import vgamepad as vg
        _vg = vg
        logger.info("vgamepad 已加载 (ViGEmBus 驱动可用)")
        return vg
    except Exception as e:
        logger.debug(f"vgamepad import 失败 (ViGEmBus 驱动未装/未加载?): {e}")
        return None


def retry_import():
    """安装对话框装完驱动后调用 — 强制重试 import 并清 GamepadEngine 失败标记。"""
    _try_import_vgamepad(force_retry=True)
    GamepadEngine.reset_init_failed()
    # 驱动状态变了 — 清候选面板就绪缓存, 让下次开编辑器重读 (失败也不影响主流程)
    try:
        from core.gamepad_install import invalidate_status_cache
        invalidate_status_cache()
    except Exception:
        pass


def _build_button_map(vg) -> dict:
    """标签 → XUSB_BUTTON 枚举 (LT/RT 走 trigger, 不在此 map)"""
    e = vg.XUSB_BUTTON
    return {
        "A": e.XUSB_GAMEPAD_A,
        "B": e.XUSB_GAMEPAD_B,
        "X": e.XUSB_GAMEPAD_X,
        "Y": e.XUSB_GAMEPAD_Y,
        "LB": e.XUSB_GAMEPAD_LEFT_SHOULDER,
        "RB": e.XUSB_GAMEPAD_RIGHT_SHOULDER,
        "Start": e.XUSB_GAMEPAD_START,
        "Back": e.XUSB_GAMEPAD_BACK,
        "Guide": e.XUSB_GAMEPAD_GUIDE,
        "D-Up": e.XUSB_GAMEPAD_DPAD_UP,
        "D-Down": e.XUSB_GAMEPAD_DPAD_DOWN,
        "D-Left": e.XUSB_GAMEPAD_DPAD_LEFT,
        "D-Right": e.XUSB_GAMEPAD_DPAD_RIGHT,
        "L3": e.XUSB_GAMEPAD_LEFT_THUMB,
        "R3": e.XUSB_GAMEPAD_RIGHT_THUMB,
    }


class GamepadEngine:
    """虚拟 Xbox 360 手柄 — 单例 + 帧聚合"""

    _instance = None
    _lock = threading.Lock()
    _init_failed = False   # 初始化失败后不再重试 (避免每帧都触发驱动异常)

    @classmethod
    def get(cls) -> 'GamepadEngine | None':
        """获取单例; 若 vgamepad 缺失或 ViGEmBus 未加载返回 None"""
        if cls._init_failed:
            return None
        vg = _try_import_vgamepad()
        if vg is None:
            return None
        with cls._lock:
            if cls._instance is None:
                try:
                    cls._instance = cls(vg)
                except Exception as e:
                    logger.error(f"GamepadEngine 初始化失败 (ViGEmBus 未加载?): {e}")
                    cls._init_failed = True
                    return None
            return cls._instance

    @classmethod
    def reset_init_failed(cls):
        """清掉「初始化失败」缓存 — 安装驱动后调用, 让下次 get() 重试。"""
        with cls._lock:
            if cls._init_failed:
                logger.info("GamepadEngine 失败缓存已清, 下次 get() 将重试")
            cls._init_failed = False

    def __init__(self, vg):
        self._pad = vg.VX360Gamepad()
        self._button_map = _build_button_map(vg)
        self._pressed_buttons: set[str] = set()
        self._lstick = (0.0, 0.0)
        self._rstick = (0.0, 0.0)
        self._ltrigger = 0.0
        self._rtrigger = 0.0
        self._dirty = False
        logger.info("GamepadEngine 已就绪: 虚拟 Xbox 360 手柄已创建")

    # ── 按钮 ──
    def press_button(self, label: str):
        if label == "LT":
            self.set_trigger("L", 1.0); return
        if label == "RT":
            self.set_trigger("R", 1.0); return
        enum = self._button_map.get(label)
        if enum is None:
            logger.warning(f"未知手柄按钮标签: {label}")
            return
        if label not in self._pressed_buttons:
            self._pressed_buttons.add(label)
            self._pad.press_button(enum)
            self._dirty = True

    def release_button(self, label: str):
        if label == "LT":
            self.set_trigger("L", 0.0); return
        if label == "RT":
            self.set_trigger("R", 0.0); return
        enum = self._button_map.get(label)
        if enum is None:
            return
        if label in self._pressed_buttons:
            self._pressed_buttons.discard(label)
            self._pad.release_button(enum)
            self._dirty = True

    # ── 摇杆 (x, y ∈ [-1, 1]) ──
    def set_stick(self, stick_id: str, x: float, y: float):
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        if stick_id == "L":
            if (x, y) != self._lstick:
                self._lstick = (x, y)
                self._pad.left_joystick_float(x, y)
                self._dirty = True
        else:
            if (x, y) != self._rstick:
                self._rstick = (x, y)
                self._pad.right_joystick_float(x, y)
                self._dirty = True

    # ── 扳机 (value ∈ [0, 1]) ──
    def set_trigger(self, trigger_id: str, value: float):
        value = max(0.0, min(1.0, value))
        if trigger_id == "L":
            if value != self._ltrigger:
                self._ltrigger = value
                self._pad.left_trigger_float(value)
                self._dirty = True
        else:
            if value != self._rtrigger:
                self._rtrigger = value
                self._pad.right_trigger_float(value)
                self._dirty = True

    # ── 帧末统一提交 ──
    def flush(self):
        if self._dirty:
            try:
                self._pad.update()
            except Exception as e:
                logger.error(f"vgamepad update 失败: {e}")
            self._dirty = False

    # ── 退出 run 模式时归零 ──
    def release_all(self):
        for label in list(self._pressed_buttons):
            enum = self._button_map.get(label)
            if enum:
                self._pad.release_button(enum)
        self._pressed_buttons.clear()
        self._pad.left_joystick_float(0.0, 0.0)
        self._pad.right_joystick_float(0.0, 0.0)
        self._pad.left_trigger_float(0.0)
        self._pad.right_trigger_float(0.0)
        self._lstick = self._rstick = (0.0, 0.0)
        self._ltrigger = self._rtrigger = 0.0
        try:
            self._pad.update()
        except Exception:
            pass
        self._dirty = False


    @classmethod
    def shutdown_singleton(cls):
        """显式销毁虚拟手柄设备 — 触发 vgamepad __del__ 拔出 ViGEm 端
        atexit 注册; 也可在 app closeEvent 主动调, 防 force-kill 时设备残留 ViGEmBus bus"""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.release_all()
                except Exception:
                    pass
                try:
                    cls._instance._pad = None   # 抹掉引用 → __del__ → unplug
                except Exception:
                    pass
                cls._instance = None
                logger.info("GamepadEngine 已 shutdown (虚拟手柄拔出)")


def is_lib_available() -> bool:
    """vgamepad lib + 驱动是否可用 (惰性 import, 失败有缓存)"""
    return _try_import_vgamepad() is not None


# 进程正常退出时自动清理虚拟手柄设备 (防止 ViGEmBus bus 累积 ghost 设备)
atexit.register(GamepadEngine.shutdown_singleton)
