@echo off
chcp 65001 >nul
echo ==========================================
echo    TEGG Touch 蛋挞 - 生成发布包
echo ==========================================
echo.

cd /d "%~dp0"

:: ── 从 constants.py 读取版本号 ──
for /f %%v in ('python _version.py') do set VER=%%v
if "%VER%"=="" (
    echo ✗ 无法读取版本号！请检查 core/constants.py
    pause
    exit /b 1
)

set DIST_DIR=dist\TEGGTouch_v%VER%
set RELEASE_NAME=TEGGTouch_v%VER%

:: 检查 dist 是否存在
if not exist "%DIST_DIR%\TEGGTouch.exe" (
    echo ✗ 未找到打包产物！请先运行 build.bat
    echo   期望路径: %DIST_DIR%\TEGGTouch.exe
    pause
    exit /b 1
)

:: 清理旧发布包
if exist "dist\%RELEASE_NAME%.zip" del /q "dist\%RELEASE_NAME%.zip"

echo 版本: v%VER%
echo 正在压缩发布包: dist\%RELEASE_NAME%.zip ...

pwsh -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath 'dist\%RELEASE_NAME%.zip' -Force"

if exist "dist\%RELEASE_NAME%.zip" (
    echo.
    echo ==========================================
    echo    ★ 发布包生成成功！ v%VER% ★
    echo ==========================================
    echo.
    echo 文件: dist\%RELEASE_NAME%.zip
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
