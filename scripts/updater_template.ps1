# TEGGTouch 升级器 — 等主程序退出 → 解压 zip → 覆盖到安装目录 → 启动新版 → 清理
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
    # 无边框, 整窗一色深灰; 不要 Windows 默认的浅色标题栏
    $splash.FormBorderStyle = "None"
    $splash.MaximizeBox = $false
    $splash.MinimizeBox = $false
    $splash.TopMost = $true
    $splash.ShowInTaskbar = $false
    $splash.BackColor = [System.Drawing.Color]::FromArgb(45, 45, 45)
    # 微调: 用 1px 深色边框区隔背景
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

# Src 智能判定: 优先看 $TmpRoot 是否平铺有 TEGGTouch.exe; 若没有, 找包裹了 exe 的唯一子目录.
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
