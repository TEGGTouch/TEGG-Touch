"""
TEGG Touch (PyQt6) - core/gamepad_install.py
ViGEmBus 驱动检测 + vgamepad 库管理 + 离线/在线/手动三级安装。

状态枚举:
  READY_OK         — 驱动 + 库都 OK，可直接用
  NEEDS_UPDATE     — 驱动版本低于内置安装包，建议更新
  NOT_INSTALLED    — 驱动未装，准备走离线安装
  DRIVER_BROKEN    — 服务在线但 vgamepad 创建失败 (常见: 安装完没重启)
  ONLINE_FALLBACK  — 离线包缺失，走 winget 在线
  MANUAL_FALLBACK  — 自动安装全部失败，跳官网手动装
  NEEDS_REBOOT     — 安装完成但驱动未加载，需重启电脑

所有阻塞 IO (子进程 / 网络) 在调用方 QThread 里跑，本模块函数本身同步返回。
"""

from __future__ import annotations

import ctypes
import enum
import logging
import os
import subprocess
import sys
import webbrowser

log = logging.getLogger(__name__)


# ── ShellExecuteEx + runas: 正确触发 UAC,等待子进程退出,拿返回码 ────────
# WiX Burn bootstrapper 在 manifest 里声明 requireAdministrator,普通
# subprocess.run 会直接报 740 (ERROR_ELEVATION_REQUIRED)。必须走
# ShellExecuteEx 让 Windows 拉 UAC。

if sys.platform == 'win32':
    class _SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ('cbSize', ctypes.c_ulong),
            ('fMask', ctypes.c_ulong),
            ('hwnd', ctypes.c_void_p),
            ('lpVerb', ctypes.c_wchar_p),
            ('lpFile', ctypes.c_wchar_p),
            ('lpParameters', ctypes.c_wchar_p),
            ('lpDirectory', ctypes.c_wchar_p),
            ('nShow', ctypes.c_int),
            ('hInstApp', ctypes.c_void_p),
            ('lpIDList', ctypes.c_void_p),
            ('lpClass', ctypes.c_wchar_p),
            ('hkeyClass', ctypes.c_void_p),
            ('dwHotKey', ctypes.c_ulong),
            ('hIcon', ctypes.c_void_p),
            ('hProcess', ctypes.c_void_p),
        ]
    _SEE_MASK_NOCLOSEPROCESS = 0x00000040
    _SEE_MASK_NOASYNC = 0x00000100
    _ERROR_CANCELLED = 1223
    _INFINITE = 0xFFFFFFFF


def _run_elevated_wait(path: str, args: str, timeout_ms: int = 180000) -> tuple[int, str]:
    """以管理员身份 (UAC) 启动 path 并等待退出。返回 (returncode, 错误描述)。

    returncode = -1 表示启动本身失败 (UAC 拒绝 / 系统错误)。
    成功的返回码与子进程相同。
    """
    if sys.platform != 'win32':
        return -1, "仅 Windows 支持"
    sei = _SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NOASYNC
    sei.lpVerb = "runas"
    sei.lpFile = path
    sei.lpParameters = args
    sei.nShow = 1  # SW_SHOWNORMAL — bootstrapper 自己决定显示与否
    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = ctypes.c_int
    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.windll.kernel32.GetLastError()
        if err == _ERROR_CANCELLED:
            return -1, "用户取消了 UAC 提权请求"
        return -1, f"ShellExecuteEx 失败, GetLastError={err}"
    if not sei.hProcess:
        return -1, "ShellExecuteEx 未返回进程句柄"
    k32 = ctypes.windll.kernel32
    k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    k32.WaitForSingleObject.restype = ctypes.c_ulong
    k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    k32.GetExitCodeProcess.restype = ctypes.c_int
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    wait_result = k32.WaitForSingleObject(sei.hProcess, timeout_ms)
    if wait_result != 0:  # WAIT_OBJECT_0 = 0
        k32.CloseHandle(sei.hProcess)
        return -1, f"等待安装器超时 (wait_result={wait_result})"
    exit_code = ctypes.c_ulong()
    k32.GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code))
    k32.CloseHandle(sei.hProcess)
    return int(exit_code.value), ""

# 内置离线安装包路径 (相对 APP_DIR)
BUNDLED_INSTALLER_REL = os.path.join("assets", "drivers", "ViGEmBus_Setup.exe")

# 内置安装包的版本号 — 必须与下载到 assets/drivers 的版本对应，发版时同步更新
BUNDLED_VERSION = "1.22.0"

# GitHub Release 永久链接 (失败兜底跳浏览器)
MANUAL_DOWNLOAD_URL = "https://github.com/nefarius/ViGEmBus/releases/latest"


class Status(enum.Enum):
    READY_OK = "ready_ok"
    NEEDS_UPDATE = "needs_update"
    NOT_INSTALLED = "not_installed"   # 驱动未装 (顺带库也可能没装)
    LIB_MISSING = "lib_missing"       # 驱动 OK, 仅 Python 端 vgamepad 库缺
    DRIVER_BROKEN = "driver_broken"   # 库装了, 但创建虚拟手柄失败 (装完未重启等)
    NEEDS_REBOOT = "needs_reboot"


def _bundled_installer_path() -> str:
    """绝对路径，可能不存在 (用 has_bundled_installer() 判断)。"""
    from core.constants import APP_DIR
    return os.path.join(APP_DIR, BUNDLED_INSTALLER_REL)


def has_bundled_installer() -> bool:
    p = _bundled_installer_path()
    return os.path.isfile(p) and os.path.getsize(p) > 0


# ─── 检测 ────────────────────────────────────────────────────────────────

def _service_running() -> bool:
    """sc query ViGEmBus 看服务是否 RUNNING。"""
    if sys.platform != 'win32':
        return False
    try:
        out = subprocess.run(
            ['sc', 'query', 'ViGEmBus'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        return 'RUNNING' in out.stdout
    except Exception as e:
        log.debug(f"sc query 失败: {e}")
        return False


def _installed_version() -> str | None:
    """读取已安装 ViGEmBus 驱动的版本号。

    优先注册表 Uninstall 键，失败回退到 pnputil。
    返回 None 表示未装或读取失败。
    """
    if sys.platform != 'win32':
        return None
    # 注册表路径：HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{...}
    try:
        import winreg
        for hive_root in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ):
            try:
                with winreg.OpenKey(hive_root[0], hive_root[1]) as root:
                    idx = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(root, idx)
                            idx += 1
                        except OSError:
                            break
                        try:
                            with winreg.OpenKey(root, sub) as k:
                                try:
                                    name, _ = winreg.QueryValueEx(k, "DisplayName")
                                except FileNotFoundError:
                                    continue
                                if 'ViGEm' in str(name) and 'Bus' in str(name):
                                    try:
                                        ver, _ = winreg.QueryValueEx(k, "DisplayVersion")
                                        return str(ver).strip()
                                    except FileNotFoundError:
                                        return ""  # 装了但没记版本
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception as e:
        log.debug(f"读取注册表版本失败: {e}")
    return None


def _vgamepad_lib_available() -> bool:
    """vgamepad 库是否真的安装在 site-packages / 打包 bundle 里。

    历史上这里直接 `import vgamepad`, 但 vgamepad 的 __init__.py 顶层会执行
    VBus() → vigem_connect(), 驱动一旦没就绪 import 就抛异常 → lib_ok=False。
    结果"驱动有问题"被误判成"Python 库缺", 弹窗让用户去 pip install,
    pip 装了也没用 (真因是驱动), 用户被坑。

    现在改用 importlib.util.find_spec, 只检测包文件存在, 不触发 init。
    真的有 "驱动没准备好" → 后续 _vgamepad_smoke_test() 会捕获 → DRIVER_BROKEN
    (友好提示"重新安装一下"), 而不是误导到 LIB_MISSING。

    打包用户 (sys.frozen): vgamepad 永远嵌在 _internal/vgamepad/, 没有缺失场景;
    且 pip 安装路径在 .exe 进程里跑不起来, 必须从源头避开 LIB_MISSING 分支。
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式: vgamepad 跟程序文件一起发布, 必然存在;
        # 兜底强制 True, 让流程永远不会进 LIB_MISSING (即使 find_spec 出意外)
        return True
    try:
        import importlib.util
        return importlib.util.find_spec('vgamepad') is not None
    except Exception:
        return False


def _vgamepad_smoke_test() -> tuple[bool, str]:
    """尝试 import vgamepad + 创建 VX360Gamepad。返回 (ok, 错误信息)。"""
    try:
        import vgamepad as vg  # type: ignore
    except ImportError as e:
        return False, f"vgamepad 库未安装: {e}"
    except Exception as e:
        return False, f"vgamepad 导入异常: {e}"
    try:
        pad = vg.VX360Gamepad()
        pad.update()
        del pad
        return True, ""
    except Exception as e:
        return False, f"VX360Gamepad 创建失败: {e}"


def _cmp_version(a: str, b: str) -> int:
    """语义化版本比较，a<b 返回 -1，a==b 返回 0，a>b 返回 1。容错非数字段。"""
    def parts(v: str) -> list[int]:
        out = []
        for seg in v.replace('-', '.').split('.'):
            try:
                out.append(int(seg))
            except ValueError:
                break
        return out
    pa, pb = parts(a), parts(b)
    # 补齐长度
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    for x, y in zip(pa, pb):
        if x < y:
            return -1
        if x > y:
            return 1
    return 0


def detect_status() -> tuple[Status, dict]:
    """主检测入口，返回 (状态, 额外信息字典)。

    info 字典字段:
      installed_version: str | None
      bundled_version:   str
      driver_ok:         bool (服务在 OR 注册表有版本)
      lib_ok:            bool
      smoke_err:         str  (DRIVER_BROKEN 时有意义)
    """
    info = {
        "installed_version": _installed_version(),
        "bundled_version": BUNDLED_VERSION,
        "driver_ok": False,
        "lib_ok": _vgamepad_lib_available(),
        "smoke_err": "",
    }
    # 注册表是权威信号:MSI 卸载后注册表立刻清,即使内核服务还在内存里
    # 运行到下次重启 (sc query 仍报 RUNNING),也应视为未装。
    info["driver_ok"] = info["installed_version"] is not None

    # 驱动没装 — 不管库在不在,主流程都是装驱动 (装驱动顺便引导装库)
    if not info["driver_ok"]:
        return Status.NOT_INSTALLED, info

    # 驱动在,库没在 — 简单情况,只缺 pip 包
    if not info["lib_ok"]:
        return Status.LIB_MISSING, info

    # 两者都在,做端到端 smoke test
    ok, err = _vgamepad_smoke_test()
    if not ok:
        info["smoke_err"] = err
        return Status.DRIVER_BROKEN, info

    # 全部 OK,看版本
    iv = info["installed_version"]
    if iv and _cmp_version(iv, BUNDLED_VERSION) < 0:
        return Status.NEEDS_UPDATE, info
    return Status.READY_OK, info


# ─── 候选面板就绪门控 (轻量, 不创建真实设备) ──────────────────────────────
#
# 历史坑: 候选面板 (按钮/宏/语音/方向盘/摇杆 编辑器) 过去用 detect_status() 门控,
# 而 detect_status() 会跑 _vgamepad_smoke_test() —— 真的 VX360Gamepad() 插一个虚拟
# 手柄再 del 拔掉。结果每开一次编辑器 Windows 就响一声"设备插拔音", 用户连续删按键
# = 高频插拔 ViGEmBus → 驱动卡 / UI 线程堆积 → 死机。
#
# 修复 (A+B):
#   B — 门控改用 palette_ready(): 只查"注册表有驱动版本 + vgamepad 库存在", 绝不创建
#       真实设备, 零插拔音。
#   A — 结果缓存, 安装/重试后 invalidate_status_cache() 清; 平时开编辑器零开销。
#
# 真正的端到端设备校验仍保留给"切到手柄运行模式"和"安装弹窗"(它们本就要建设备)。
# DRIVER_BROKEN (装了没重启) 这种边角态门控会放行, 但进手柄运行模式时仍会被
# detect_status() 拦下, 且 GamepadEngine.get() 失败也会优雅返回 None, 不影响安全。

_palette_ready_cache: bool | None = None


def palette_ready() -> bool:
    """候选面板「手柄就绪」轻量判断 — 驱动已装(注册表有版本) + vgamepad 库存在。

    不创建真实虚拟手柄设备, 因此不会触发 Windows 设备插拔提示音。结果缓存,
    安装驱动 / retry_import 后须 invalidate_status_cache() 清。
    """
    global _palette_ready_cache
    if _palette_ready_cache is None:
        _palette_ready_cache = (_installed_version() is not None) and _vgamepad_lib_available()
    return _palette_ready_cache


def invalidate_status_cache() -> None:
    """清就绪缓存 — 装完驱动 / retry_import / 做过真实检测后调, 让下次 palette_ready() 重读。"""
    global _palette_ready_cache
    _palette_ready_cache = None


def install_vgamepad_lib(progress_cb=None) -> tuple[bool, str]:
    """pip install vgamepad - 仅 Python 端。返回 (ok, info)。

    关键策略: 优先 --only-binary :all: 拉 wheel,跳过 setup.py 里的
    ViGEmBus 安装器(避免重复弹出"修改/修复"向导)。
    wheel 缺失时回退到普通 sdist 安装。
    """
    if progress_cb:
        progress_cb("正在通过 pip 安装 (优先 wheel)…", 10)
    try:
        # 第一次尝试: wheel-only - 不会执行 setup.py 的 post-install
        proc = subprocess.run(
            [sys.executable, '-m', 'pip', 'install',
             '--only-binary', ':all:', '--upgrade', 'vgamepad'],
            capture_output=True, text=True, timeout=180,
        )
        used_sdist = False
        if proc.returncode != 0:
            # 没有匹配的 wheel → 回退 sdist
            log.warning(
                f"wheel 安装失败 ({proc.returncode}),回退 sdist: "
                f"{proc.stderr[-200:]}"
            )
            if progress_cb:
                progress_cb("wheel 不可用,回退源码安装…", 40)
            proc = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', 'vgamepad'],
                capture_output=True, text=True, timeout=180,
            )
            used_sdist = True
            if proc.returncode != 0:
                return False, f"pip 退出码 {proc.returncode}: {proc.stderr[-200:]}"

        if progress_cb:
            progress_cb("验证虚拟手柄创建…", 90)
        ok, err = _vgamepad_smoke_test()
        if ok:
            return True, ""
        # 装完了但 smoke 失败 — 提示需重启
        hint = " (走了 sdist,setup.py 可能触发了驱动安装,需重启电脑加载驱动)" if used_sdist else ""
        return False, f"NEEDS_REBOOT::{err}{hint}"
    except subprocess.TimeoutExpired:
        return False, "pip 安装超时"
    except Exception as e:
        return False, f"pip 安装异常: {e}"


# ─── 安装 ────────────────────────────────────────────────────────────────

def install_offline(progress_cb=None) -> tuple[bool, str]:
    """运行内置 EXE bootstrapper 安装,通过 ShellExecuteEx 触发 UAC。

    WiX Burn bootstrapper 在 manifest 里要求管理员权限,普通 subprocess.run
    会直接报 740 (ERROR_ELEVATION_REQUIRED),所以必须走 runas verb 让
    Windows 拉 UAC 弹窗。

    策略: 先 -passive (进度条,无需点击),失败回退到完整交互模式。
    成功 = 返回码 0 或 3010,且 smoke test 通过 (或 NEEDS_REBOOT)。
    """
    if not has_bundled_installer():
        return False, "内置安装包不存在"
    path = _bundled_installer_path()
    if progress_cb:
        progress_cb("UAC 弹窗请点「是」,然后在安装向导里按提示完成…", 10)
    log.info(f"开始离线安装 (交互模式): {path}")

    # 直接走交互模式 — ViGEm v1.22 的 bootstrapper 实测拒绝 -passive/-quiet
    # 等 flag,反而会卡死。交互模式用户点 Install→Finish 两下就完了。
    rc, ex_err = _run_elevated_wait(path, "", timeout_ms=600000)
    log.info(f"安装器 returncode={rc}, err={ex_err!r}")
    if rc not in (0, 3010):
        if "取消" in ex_err or "CANCELLED" in ex_err.upper():
            return False, ex_err
        return False, f"安装器退出码 {rc}; {ex_err}"

    if progress_cb:
        progress_cb("验证驱动…", 90)
    try:
        subprocess.run(['sc', 'start', 'ViGEmBus'],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    ok, smoke_err = _vgamepad_smoke_test()
    if ok:
        return True, ""
    return False, f"NEEDS_REBOOT::{smoke_err}"


def install_online(progress_cb=None) -> tuple[bool, str]:
    """winget 在线安装作为离线 fallback。winget 装机器范围的包也需要管理员。"""
    if progress_cb:
        progress_cb("通过 winget 下载,UAC 弹出时点「是」…", 10)
    try:
        # 用普通 subprocess 调 winget — 包内部的 msiexec 才需要 UAC,
        # 但 winget 自带提权处理,失败时 stdout 会有清晰提示
        proc = subprocess.run(
            ['winget', 'install', '--id=ViGEm.ViGEmBus', '-e', '--silent',
             '--accept-package-agreements', '--accept-source-agreements'],
            capture_output=True, text=True, timeout=180,
        )
        log.info(f"winget install returncode={proc.returncode}")
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr)[-300:]
            return False, f"winget 退出码 {proc.returncode}: {tail}"
        if progress_cb:
            progress_cb("等待服务启动…", 80)
        try:
            subprocess.run(['sc', 'start', 'ViGEmBus'],
                           capture_output=True, timeout=10)
        except Exception:
            pass
        ok, err = _vgamepad_smoke_test()
        if ok:
            return True, ""
        return False, f"NEEDS_REBOOT::{err}"
    except FileNotFoundError:
        return False, "winget 不可用 (老版本 Windows)"
    except subprocess.TimeoutExpired:
        return False, "在线安装超时"
    except Exception as e:
        return False, f"在线安装异常: {e}"


def open_manual_install_page() -> None:
    """打开浏览器跳到 GitHub Release 页让用户手动下载。"""
    try:
        webbrowser.open(MANUAL_DOWNLOAD_URL)
    except Exception as e:
        log.warning(f"打开浏览器失败: {e}")
