# TEGGTouch 升级器 — 等主程序退出 → 解压 zip → 覆盖到安装目录 → 启动新版 → 清理
#
# 参数:
#   -WaitPid <int>     主程序 PID, 等它退出再动手
#   -ZipPath <string>  下载好的全量 zip 路径 (TEGGTouch_v{V}.zip)
#   -InstallDir <string>  安装目录 (覆盖目标, TEGGTouch.exe 所在的目录)
#   -ExePath <string>  升级完后启动的 exe 全路径
#
# 跳过的用户数据 (robocopy /XD / /XF):
#   profiles\, settings\, logs\, config.json, config.json.bak
#
# 升级完成后, zip 和临时解压目录都会被删
#
# !! 该文件必须跟 core/update_installer.py 里的 _UPDATER_PS1 字符串同步 !!

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
