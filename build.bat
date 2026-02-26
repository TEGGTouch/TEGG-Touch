@echo off
chcp 65001 >nul
echo ==========================================
echo    TEGG Touch 蛋挞 (PyQt6) - 打包构建
echo ==========================================
echo.

cd /d "%~dp0"

echo [1/5] 安装依赖...
python -m pip install -r requirements.txt pyinstaller >nul 2>&1
echo      √ 依赖已就绪
echo.

echo [2/5] 清理旧的打包文件...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
echo      √ 已清理
echo.

echo [3/5] PyInstaller 打包 (--onedir)...
echo -------------------------------------------------------
python -m PyInstaller teggtouch.spec --clean
echo -------------------------------------------------------
echo.

if not exist "dist\TEGGTouch\TEGGTouch.exe" (
    echo ✗ 打包失败！请检查上方错误信息。
    pause
    exit /b 1
)

echo [4/5] 复制数据文件到发布目录...
set OUT=dist\TEGGTouch

:: 资源文件 (只读)
xcopy /E /I /Y "assets"  "%OUT%\assets"  >nul
xcopy /E /I /Y "locales" "%OUT%\locales" >nul

:: 语音模型 (用户可管理)
xcopy /E /I /Y "models\vosk" "%OUT%\models\vosk" >nul

:: 默认设置
xcopy /E /I /Y "settings" "%OUT%\settings" >nul

:: 默认方案模板
if not exist "%OUT%\core" mkdir "%OUT%\core"
copy /Y "core\default_profile.json" "%OUT%\core\" >nul

:: 预置配置方案 (首次运行的默认方案集)
xcopy /E /I /Y "profiles" "%OUT%\profiles" >nul

echo      √ 数据文件已复制
echo.

echo [5/5] 验证产物...
echo      - TEGGTouch.exe
if exist "%OUT%\locales"        (echo      - locales        √) else (echo      - locales        ✗)
if exist "%OUT%\assets"         (echo      - assets         √) else (echo      - assets         ✗)
if exist "%OUT%\settings"       (echo      - settings       √) else (echo      - settings       ✗)
if exist "%OUT%\models\vosk"    (echo      - models/vosk    √) else (echo      - models/vosk    ✗)
if exist "%OUT%\core\default_profile.json" (echo      - default_profile √) else (echo      - default_profile ✗)
if exist "%OUT%\profiles"       (echo      - profiles       √) else (echo      - profiles       ✗)
echo.

echo ==========================================
echo         ★ 打包完成！★
echo ==========================================
echo.
echo 发布目录: dist\TEGGTouch\
echo 主程序:   dist\TEGGTouch\TEGGTouch.exe
echo.
echo 提示: 运行 pack_release.bat 可生成 ZIP 发布包
echo.
pause
