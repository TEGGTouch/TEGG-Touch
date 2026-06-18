"""
TEGG Touch - update_installer.py
A 方案自动升级器: 下载全量 zip → 写 updater.ps1 → spawn powershell → 主程序退出 → ps1 接管覆盖 + 重启 + 清理.

UI 走 UpdateInstaller (QThread) 暴露 progress/finished/failed 信号; UpdateDialog 接进度条.
"""

import hashlib
import logging
import os
import sys
import subprocess
import tempfile
import urllib.request
import urllib.error

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.constants import APP_VERSION

logger = logging.getLogger(__name__)

# 主下载源 + 国内镜像 fallback (前缀 + 原 URL 拼接)
# ghproxy 系列的稳定性会变, 失败就顺序回退下一个
_MIRRORS = [
    "",                                  # 直连
    "https://ghproxy.com/",
    "https://gh-proxy.com/",
    "https://mirror.ghproxy.com/",
]

_DOWNLOAD_CHUNK = 64 * 1024              # 64KB chunks
_DOWNLOAD_TIMEOUT_PER_MIRROR = 20        # 单个镜像连接超时 (秒)


class UpdateError(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────
# updater.ps1 模板内嵌 (避免 PyInstaller datas 漏装风险)
# 同步: scripts/updater_template.ps1
# ─────────────────────────────────────────────────────────────────────
_UPDATER_PS1 = r"""# TEGGTouch 升级器 — 等主程序退出 → 解压 zip → 覆盖到安装目录 → 启动新版 → 清理
param(
    [Parameter(Mandatory=$true)][int]$WaitPid,
    [Parameter(Mandatory=$true)][string]$ZipPath,
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$ExePath
)

$ErrorActionPreference = "Continue"
$LogPath = Join-Path $env:TEMP "teggtouch_updater.log"

function Log($msg) {
    try {
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $LogPath -Value "[$ts] $msg" -Encoding UTF8
    } catch {}
}

Log "=== updater started ==="
Log "WaitPid=$WaitPid ZipPath=$ZipPath InstallDir=$InstallDir ExePath=$ExePath"

try {
    Wait-Process -Id $WaitPid -Timeout 30 -ErrorAction SilentlyContinue
    Log "main process exited"
} catch {
    Log "wait-process failed or timed out: $_"
}
Start-Sleep -Seconds 1

$TmpRoot = Join-Path $env:TEMP ("teggtouch_extract_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TmpRoot | Out-Null
Log "extract to: $TmpRoot"
try {
    Expand-Archive -Path $ZipPath -DestinationPath $TmpRoot -Force
} catch {
    Log "ERROR: Expand-Archive failed: $_"
    exit 1
}

# Src 智能判定: 优先看 $TmpRoot 是否平铺有 TEGGTouch.exe; 若没有, 找包裹了 exe 的唯一子目录.
# pack_release.bat 用 Compress-Archive '*' 打包 → zip 永远平铺, $TmpRoot 本身就是 src.
$Src = $null
if (Test-Path (Join-Path $TmpRoot "TEGGTouch.exe")) {
    $Src = $TmpRoot
} else {
    foreach ($d in Get-ChildItem -Path $TmpRoot -Directory) {
        if (Test-Path (Join-Path $d.FullName "TEGGTouch.exe")) { $Src = $d.FullName; break }
    }
}
if (-not $Src) {
    Log "ERROR: TEGGTouch.exe not found in extracted zip (tried root + 1 level subdirs)"
    exit 2
}
Log "source dir: $Src"

$RoboArgs = @(
    $Src, $InstallDir, "/E",
    "/XD", "profiles", "settings", "logs",
    "/XF", "config.json", "config.json.bak",
    "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
    "/R:2", "/W:2"
)
Log "robocopy: $($RoboArgs -join ' ')"
$proc = Start-Process -FilePath "robocopy" -ArgumentList $RoboArgs -NoNewWindow -PassThru -Wait
Log "robocopy exit code: $($proc.ExitCode)"
if ($proc.ExitCode -ge 8) {
    Log "ERROR: robocopy reported failure"
}

Log "starting: $ExePath"
try {
    Start-Process -FilePath $ExePath -WorkingDirectory $InstallDir
} catch {
    Log "ERROR: failed to start app: $_"
}
Start-Sleep -Seconds 2

try {
    if (Test-Path $TmpRoot) { Remove-Item -Recurse -Force $TmpRoot; Log "removed tmp: $TmpRoot" }
} catch { Log "cleanup tmp failed: $_" }
try {
    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath; Log "removed zip: $ZipPath" }
} catch { Log "cleanup zip failed: $_" }

Log "=== updater finished ==="
"""


# ─────────────────────────────────────────────────────────────────────
# 下载: 直连 + 镜像顺序 fallback, 带进度回调
# ─────────────────────────────────────────────────────────────────────

def _download(url: str, dest: str, on_progress, timeout: int) -> int:
    """单源下载, 返回总字节数. 失败抛 URLError / OSError."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"TEGGTouch/{APP_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(_DOWNLOAD_CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress:
                    on_progress(downloaded, total)
        return downloaded


def download_with_fallback(url: str, dest: str, on_progress=None) -> str:
    """按 _MIRRORS 顺序尝试. 返回下载后的文件路径 (= dest). 全失败抛 UpdateError."""
    last_err: Exception | None = None
    for prefix in _MIRRORS:
        try_url = (prefix + url) if prefix else url
        logger.info(f"downloading from: {try_url}")
        try:
            _download(try_url, dest, on_progress, _DOWNLOAD_TIMEOUT_PER_MIRROR)
            logger.info(f"download succeeded: {try_url} → {dest}")
            return dest
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
            last_err = e
            logger.warning(f"download failed via {prefix or 'direct'}: {e}")
            # 清掉半截文件再试下一个镜像
            try:
                if os.path.exists(dest):
                    os.remove(dest)
            except Exception:
                pass
            continue
    raise UpdateError(f"all mirrors failed: {last_err}")


def verify_sha256(path: str, expected_hex: str) -> bool:
    """文件 sha256 校验, expected_hex 为 None / 空字符串时直接 True (跳过)."""
    if not expected_hex:
        return True
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_DOWNLOAD_CHUNK), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    expected = expected_hex.strip().lower()
    return actual == expected


# ─────────────────────────────────────────────────────────────────────
# UpdateInstaller — QThread 包装下载逻辑, 给 UpdateDialog 喂进度
# ─────────────────────────────────────────────────────────────────────

class UpdateInstaller(QThread):
    """后台线程下载新版 zip; 完成后调 apply_update() 触发 ps1 + 退出 app.

    Signals:
        progress(downloaded_bytes, total_bytes)  下载进度; total=0 时说明 server 没给 Content-Length
        finished_ok(zip_path)                    下载完成 + 校验通过
        failed(error_msg)                        任何环节失败
    """

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, zip_url: str, expected_sha256: str = "", parent=None):
        super().__init__(parent)
        self._zip_url = zip_url
        self._expected_sha256 = expected_sha256
        self._dest_path: str | None = None

    def run(self):
        try:
            tmp_dir = os.path.join(tempfile.gettempdir(), "teggtouch_update")
            os.makedirs(tmp_dir, exist_ok=True)
            # 用 URL 的文件名 (TEGGTouch_v{V}.zip), 防重名加 PID
            filename = self._zip_url.rstrip("/").split("/")[-1] or "TEGGTouch_update.zip"
            dest = os.path.join(tmp_dir, filename)
            self._dest_path = dest

            def _on_progress(downloaded, total):
                self.progress.emit(downloaded, total)

            download_with_fallback(self._zip_url, dest, _on_progress)

            if not verify_sha256(dest, self._expected_sha256):
                self.failed.emit("SHA-256 校验失败")
                return

            self.finished_ok.emit(dest)
        except UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            logger.exception("UpdateInstaller crashed")
            self.failed.emit(f"未知错误: {e}")


# ─────────────────────────────────────────────────────────────────────
# 应用升级: 写 ps1 + spawn powershell + quit app
# ─────────────────────────────────────────────────────────────────────

def _get_install_dir_and_exe() -> tuple[str, str]:
    """获取当前安装目录 + exe 全路径.
    冻结状态 (PyInstaller): sys.executable = TEGGTouch.exe
    开发状态: 用 cwd / sys.argv[0] 兜底 (升级不会实际跑, 但避免崩)
    """
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        install_dir = os.path.dirname(exe_path)
    else:
        install_dir = os.getcwd()
        exe_path = os.path.join(install_dir, "TEGGTouch.exe")
    return install_dir, exe_path


def apply_update(zip_path: str) -> None:
    """写 updater.ps1 → 启动 powershell → 退出主程序.
    调用此函数后 app 会立即 quit, 后续控制权交给 ps1."""
    install_dir, exe_path = _get_install_dir_and_exe()
    tmp_dir = os.path.join(tempfile.gettempdir(), "teggtouch_update")
    os.makedirs(tmp_dir, exist_ok=True)
    ps1_path = os.path.join(tmp_dir, "updater.ps1")
    with open(ps1_path, "w", encoding="utf-8") as f:
        f.write(_UPDATER_PS1)

    main_pid = os.getpid()
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden",
        "-File", ps1_path,
        "-WaitPid", str(main_pid),
        "-ZipPath", zip_path,
        "-InstallDir", install_dir,
        "-ExePath", exe_path,
    ]
    logger.info(f"spawning updater: {' '.join(cmd)}")

    # 注意: DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP 在 Win11 上会让 powershell
    # 秒退出 (v0.3.5/v0.3.6 测试版踩过的坑). 必须用 CREATE_NO_WINDOW 才能后台稳跑.
    CREATE_NO_WINDOW = 0x08000000
    try:
        subprocess.Popen(
            cmd,
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception as e:
        logger.error(f"failed to spawn updater: {e}")
        raise

    # 给 powershell 一点时间起进程, 然后退出主程序
    app = QApplication.instance()
    if app is not None:
        app.quit()
