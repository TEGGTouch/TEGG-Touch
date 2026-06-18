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

# 1) 等主程序退出 (最多 30s, 超时也继续, 让 robocopy 自己处理锁文件)
try {
    Wait-Process -Id $WaitPid -Timeout 30 -ErrorAction SilentlyContinue
    Log "main process exited"
} catch {
    Log "wait-process failed or timed out: $_"
}
Start-Sleep -Seconds 1

# 2) 解压到临时目录
$TmpRoot = Join-Path $env:TEMP ("teggtouch_extract_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TmpRoot | Out-Null
Log "extract to: $TmpRoot"
try {
    Expand-Archive -Path $ZipPath -DestinationPath $TmpRoot -Force
} catch {
    Log "ERROR: Expand-Archive failed: $_"
    exit 1
}

# 3) zip 里顶层是 TEGGTouch_v{V}\ 目录, 取第一个 directory 作为源
$TopDirs = Get-ChildItem -Path $TmpRoot -Directory
if ($TopDirs.Count -eq 0) {
    # 直接解压到根, 没有 TEGGTouch_v{V} 包裹层
    $Src = $TmpRoot
} else {
    $Src = $TopDirs[0].FullName
}
Log "source dir: $Src"

# 4) robocopy 覆盖, 跳过用户数据
#   /E    包含空子目录
#   /XD   排除目录
#   /XF   排除文件
#   /NFL /NDL /NJH /NJS /NP  静默
#   /R:2 /W:2  重试 2 次, 每次等 2s (锁文件场景)
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
# robocopy 退出码 0-7 都是成功 (>= 8 才算失败)
if ($proc.ExitCode -ge 8) {
    Log "ERROR: robocopy reported failure"
    # 不 exit, 继续尝试启动 — 部分文件已替换可能仍能跑
}

# 5) 启动新版
Log "starting: $ExePath"
try {
    Start-Process -FilePath $ExePath -WorkingDirectory $InstallDir
} catch {
    Log "ERROR: failed to start app: $_"
}
Start-Sleep -Seconds 2

# 6) 清理: 删 zip + 删临时解压目录
try {
    if (Test-Path $TmpRoot) {
        Remove-Item -Recurse -Force $TmpRoot
        Log "removed tmp: $TmpRoot"
    }
} catch { Log "cleanup tmp failed: $_" }
try {
    if (Test-Path $ZipPath) {
        Remove-Item -Force $ZipPath
        Log "removed zip: $ZipPath"
    }
} catch { Log "cleanup zip failed: $_" }

Log "=== updater finished ==="
