@echo off
chcp 65001 >nul
echo ==========================================
echo    TEGG Touch 蛋挞 - 生成发布包
echo ==========================================
echo.

cd /d "%~dp0"

:: 检查 dist 是否存在
if not exist "dist\TEGGTouch\TEGGTouch.exe" (
    echo ✗ 未找到打包产物！请先运行 build.bat
    pause
    exit /b 1
)

:: 读取版本号
set VERSION=0.1

:: 清理旧发布包
set RELEASE_NAME=TEGGTouch_v%VERSION%
if exist "%RELEASE_NAME%.zip" del /q "%RELEASE_NAME%.zip"

echo 正在压缩发布包: %RELEASE_NAME%.zip ...

:: 使用 PowerShell 压缩
powershell -Command "Compress-Archive -Path 'dist\TEGGTouch\*' -DestinationPath '%RELEASE_NAME%.zip' -Force"

if exist "%RELEASE_NAME%.zip" (
    echo.
    echo ==========================================
    echo      ★ 发布包生成成功！★
    echo ==========================================
    echo.
    echo 文件: %RELEASE_NAME%.zip
    echo.
    echo 用户使用方式:
    echo   1. 解压 ZIP 到任意目录
    echo   2. 双击 TEGGTouch.exe 即可运行
    echo   3. 无需安装 Python
    echo.
) else (
    echo ✗ 压缩失败！
)

pause
