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

# ── 弹一个 splash 窗口, 覆盖主程序退出到新版启动之间的空白期 ──
$splash = $null
$status = $null
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $splash = New-Object System.Windows.Forms.Form
    $splash.Text = "TEGG Touch 升级中"
    $splash.Width = 520
    $splash.Height = 220
    $splash.StartPosition = "CenterScreen"
    $splash.FormBorderStyle = "FixedSingle"
    $splash.MaximizeBox = $false
    $splash.MinimizeBox = $false
    $splash.TopMost = $true
    $splash.ShowInTaskbar = $false
    $splash.BackColor = [System.Drawing.Color]::FromArgb(45, 45, 45)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "蛋挞 正在升级到新版本"
    $title.Font = New-Object System.Drawing.Font("Microsoft YaHei", 16, [System.Drawing.FontStyle]::Bold)
    $title.ForeColor = [System.Drawing.Color]::FromArgb(245, 158, 11)
    $title.AutoSize = $false
    $title.Location = New-Object System.Drawing.Point(0, 36)
    $title.Width = $splash.ClientSize.Width
    $title.Height = 40
    $title.TextAlign = "MiddleCenter"
    $splash.Controls.Add($title)

    $status = New-Object System.Windows.Forms.Label
    $status.Text = "正在准备..."
    $status.Font = New-Object System.Drawing.Font("Microsoft YaHei", 11)
    $status.ForeColor = [System.Drawing.Color]::FromArgb(204, 204, 204)
    $status.AutoSize = $false
    $status.Location = New-Object System.Drawing.Point(0, 100)
    $status.Width = $splash.ClientSize.Width
    $status.Height = 30
    $status.TextAlign = "MiddleCenter"
    $splash.Controls.Add($status)

    $hint = New-Object System.Windows.Forms.Label
    $hint.Text = "请稍候, 完成后会自动重启"
    $hint.Font = New-Object System.Drawing.Font("Microsoft YaHei", 9)
    $hint.ForeColor = [System.Drawing.Color]::FromArgb(136, 136, 136)
    $hint.AutoSize = $false
    $hint.Location = New-Object System.Drawing.Point(0, 140)
    $hint.Width = $splash.ClientSize.Width
    $hint.Height = 20
    $hint.TextAlign = "MiddleCenter"
    $splash.Controls.Add($hint)

    $splash.Show()
    [System.Windows.Forms.Application]::DoEvents()
} catch {
    Log "splash window failed: $_"
}

function SetStatus($msg) {
    Log $msg
    if ($status) {
        try {
            $status.Text = $msg
            [System.Windows.Forms.Application]::DoEvents()
        } catch {}
    }
}

Log "=== updater started ==="
Log "WaitPid=$WaitPid ZipPath=$ZipPath InstallDir=$InstallDir ExePath=$ExePath"

SetStatus "等待主程序退出..."
try {
    Wait-Process -Id $WaitPid -Timeout 30 -ErrorAction SilentlyContinue
    Log "main process exited"
} catch {
    Log "wait-process failed or timed out: $_"
}
Start-Sleep -Milliseconds 800
[System.Windows.Forms.Application]::DoEvents() 2>$null

$TmpRoot = Join-Path $env:TEMP ("teggtouch_extract_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TmpRoot | Out-Null
SetStatus "正在解压新版本 (约 10-15 秒)..."
try {
    Expand-Archive -Path $ZipPath -DestinationPath $TmpRoot -Force
} catch {
    Log "ERROR: Expand-Archive failed: $_"
    SetStatus "解压失败, 升级中止"
    Start-Sleep -Seconds 3
    if ($splash) { $splash.Close() }
    exit 1
}

$Src = $null
if (Test-Path (Join-Path $TmpRoot "TEGGTouch.exe")) {
    $Src = $TmpRoot
} else {
    foreach ($d in Get-ChildItem -Path $TmpRoot -Directory) {
        if (Test-Path (Join-Path $d.FullName "TEGGTouch.exe")) { $Src = $d.FullName; break }
    }
}
if (-not $Src) {
    Log "ERROR: TEGGTouch.exe not found in extracted zip"
    SetStatus "新版本文件结构异常, 升级中止"
    Start-Sleep -Seconds 3
    if ($splash) { $splash.Close() }
    exit 2
}
Log "source dir: $Src"

SetStatus "正在替换文件..."
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

SetStatus "正在启动新版本..."
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
if ($splash) {
    try { $splash.Close(); $splash.Dispose() } catch {}
}
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
    # 必须用 utf-8-sig (带 BOM); Windows PowerShell 5.x 默认读 .ps1 是系统 codepage,
    # 没 BOM 时中文字符会被当 GBK 解析, 整个脚本语法被破坏, splash 看不到 / exe 启动失败.
    with open(ps1_path, "w", encoding="utf-8-sig") as f:
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

    # 给 powershell 一点时间起进程 + 弹 splash 窗口, 然后退出主程序.
    # 用 QTimer.singleShot 延迟 2 秒, 让 UpdateDialog 的「正在重启完成升级…」文字能被用户看到.
    from PyQt6.QtCore import QTimer
    app = QApplication.instance()
    if app is not None:
        QTimer.singleShot(2000, app.quit)
