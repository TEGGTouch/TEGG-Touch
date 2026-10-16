"""
TEGG Touch - update_installer.py
OSS 自动升级器: 下载并校验全量 zip → updater.ps1 → 覆盖 + 重启 + 清理.

UI 走 UpdateInstaller (QThread) 暴露 progress/finished/failed 信号; UpdateDialog 接进度条.
"""

import hashlib
import logging
import os
import sys
import subprocess
import tempfile

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.constants import APP_VERSION
from core.i18n import t
from core.update_manifest import ReleaseInfo, open_update_url, validate_archive

logger = logging.getLogger(__name__)

_DOWNLOAD_CHUNK = 64 * 1024              # 64KB chunks
_DOWNLOAD_TIMEOUT = 30


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
    $splash.Height = 200
    $splash.StartPosition = "CenterScreen"
    $splash.FormBorderStyle = "None"
    $splash.MaximizeBox = $false
    $splash.MinimizeBox = $false
    $splash.TopMost = $true
    $splash.ShowInTaskbar = $false
    $splash.BackColor = [System.Drawing.Color]::FromArgb(45, 45, 45)
    $splash.Padding = New-Object System.Windows.Forms.Padding(1)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "蛋挞 正在升级到新版本"
    $title.Font = New-Object System.Drawing.Font("Microsoft YaHei", 16, [System.Drawing.FontStyle]::Bold)
    $title.ForeColor = [System.Drawing.Color]::FromArgb(245, 158, 11)
    $title.AutoSize = $false
    $title.Location = New-Object System.Drawing.Point(0, 30)
    $title.Width = $splash.ClientSize.Width
    $title.Height = 40
    $title.TextAlign = "MiddleCenter"
    $splash.Controls.Add($title)

    $status = New-Object System.Windows.Forms.Label
    $status.Text = "正在准备..."
    $status.Font = New-Object System.Drawing.Font("Microsoft YaHei", 11)
    $status.ForeColor = [System.Drawing.Color]::FromArgb(204, 204, 204)
    $status.AutoSize = $false
    $status.Location = New-Object System.Drawing.Point(0, 88)
    $status.Width = $splash.ClientSize.Width
    $status.Height = 30
    $status.TextAlign = "MiddleCenter"
    $splash.Controls.Add($status)

    $hint = New-Object System.Windows.Forms.Label
    $hint.Text = "请稍候, 完成后会自动重启"
    $hint.Font = New-Object System.Drawing.Font("Microsoft YaHei", 9)
    $hint.ForeColor = [System.Drawing.Color]::FromArgb(136, 136, 136)
    $hint.AutoSize = $false
    $hint.Location = New-Object System.Drawing.Point(0, 130)
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
    if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) {
        Wait-Process -Id $WaitPid -Timeout 30 -ErrorAction Stop
    }
    Log "main process exited"
} catch {
    Log "wait-process failed or timed out: $_"
    SetStatus "主程序未退出, 升级中止"
    if ($splash) { $splash.Close() }
    exit 3
}
Start-Sleep -Milliseconds 800
[System.Windows.Forms.Application]::DoEvents() 2>$null

$TmpRoot = Join-Path $env:TEMP ("teggtouch_extract_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TmpRoot | Out-Null
SetStatus "正在解压新版本 (约 10-15 秒)..."
try {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $TmpRoot -Force -ErrorAction Stop
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
    ('"' + $Src + '"'), ('"' + $InstallDir + '"'), "/E",
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
    SetStatus "替换文件失败, 请保留更新包并重试"
    if ($splash) { $splash.Close() }
    exit 4
}

# 写更新完成标记 — 新版首启据此弹"已更新 + 程序位置"提示 (仅覆盖成功时写)
if ($proc.ExitCode -lt 8) {
    try {
        $marker = Join-Path $InstallDir ".update_applied"
        Set-Content -Path $marker -Value $InstallDir -Encoding UTF8
        Log "wrote update marker: $marker"
    } catch { Log "write marker failed: $_" }
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
# 下载: 官方直链、大小 + SHA256 + ZIP 校验，通过后才原子改名
# ─────────────────────────────────────────────────────────────────────

def download_release(release: ReleaseInfo, dest: str, on_progress=None, cancelled=None) -> str:
    release.validate()
    part = dest + ".part"
    digest, downloaded = hashlib.sha256(), 0
    try:
        with open_update_url(release.url, timeout=_DOWNLOAD_TIMEOUT) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != release.size:
                raise UpdateError(t("update_msg.size_mismatch"))
            with open(part, "wb") as output:
                while True:
                    if cancelled and cancelled():
                        raise UpdateError(t("update_msg.cancelled"))
                    chunk = response.read(_DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > release.size:
                        raise UpdateError(t("update_msg.size_exceeded"))
                    output.write(chunk)
                    digest.update(chunk)
                    if on_progress:
                        on_progress(downloaded, release.size)
        if downloaded != release.size:
            raise UpdateError(t("update_msg.incomplete"))
        if digest.hexdigest() != release.sha256.lower():
            raise UpdateError(t("update_msg.sha_failed"))
        validate_archive(part)
        if cancelled and cancelled():
            raise UpdateError(t("update_msg.cancelled"))
        os.replace(part, dest)
        return dest
    except Exception as e:
        try:
            if os.path.isfile(part):
                os.remove(part)
        except OSError:
            logger.warning("Failed to clean partial download: %s", part)
        raise UpdateError(str(e)) from e


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

    def __init__(self, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self._release = release
        self._dest_path: str | None = None

    def run(self):
        tmp_dir = None
        try:
            self._release.validate()
            tmp_dir = tempfile.mkdtemp(prefix="teggtouch-update-")
            filename = f"TEGGTouch_v{self._release.version}.zip"
            dest = os.path.join(tmp_dir, filename)
            self._dest_path = dest

            def _on_progress(downloaded, total):
                self.progress.emit(downloaded, total)

            download_release(self._release, dest, _on_progress, self.isInterruptionRequested)
            self.finished_ok.emit(dest)
        except UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            logger.exception("UpdateInstaller crashed")
            self.failed.emit(t("update_msg.unknown", error=e))
        finally:
            if tmp_dir:
                try:
                    os.rmdir(tmp_dir)  # failure only; never deletes a verified ZIP
                except OSError:
                    pass


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
    if not getattr(sys, "frozen", False):
        raise UpdateError(t("update_msg.source_run"))
    install_dir, exe_path = _get_install_dir_and_exe()
    tmp_dir = os.path.dirname(os.path.abspath(zip_path))
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


# ─────────────────────────────────────────────────────────────────────
# 更新完成标记 — 新版首启时读取一次, 告知用户"已更新 + 程序位置"
# (不改用户安装目录名, 仅提示其位置, 解决"找不到新版装哪了")
# ─────────────────────────────────────────────────────────────────────

_UPDATE_MARKER_NAME = ".update_applied"


def consume_post_update_marker() -> str | None:
    """新版启动时调用一次: 存在更新完成标记则删除并返回安装目录, 否则 None。

    标记由 updater.ps1 在 robocopy 覆盖成功后写入 InstallDir。
    返回本程序所在目录 (APP_DIR) 供 UI 提示"程序位置"; 以标记是否存在为信号,
    不依赖文件内容 (避免编码/空文件干扰)。
    """
    from core.constants import APP_DIR
    marker = os.path.join(APP_DIR, _UPDATE_MARKER_NAME)
    try:
        if not os.path.isfile(marker):
            return None
        try:
            os.remove(marker)
        except OSError as e:
            logger.debug(f"remove update marker failed: {e}")
        logger.info(f"检测到更新完成标记, 程序位置: {APP_DIR}")
        return APP_DIR
    except Exception as e:
        logger.debug(f"consume_post_update_marker error: {e}")
        return None
