@echo off
chcp 65001 >nul
echo ==========================================
echo    TEGG Touch 蛋挞 - 打包构建
echo ==========================================
echo.

cd /d "%~dp0"

echo [1/4] 检查打包工具...
python -m pip install pyinstaller keyboard pillow >nul 2>&1
echo      √ PyInstaller 已就绪
echo.

echo [2/4] 清理旧的打包文件...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul
echo      √ 已清理
echo.

echo [3/4] PyInstaller 打包 (--onedir)...
echo -------------------------------------------------------
python -m PyInstaller --onedir --noconsole --uac-admin --clean ^
  --name "TEGGTouch" ^
  --icon "assets\cursor.png" ^
  main.py
echo -------------------------------------------------------
echo.

if not exist "dist\TEGGTouch\TEGGTouch.exe" (
    echo ✗ 打包失败！请检查上方错误信息。
    pause
    exit /b 1
)

echo [4/4] 复制数据文件到发布目录...
:: 复制 assets（图片资源）
xcopy /E /I /Y "assets" "dist\TEGGTouch\assets" >nul
:: 复制 settings（默认快捷键）
xcopy /E /I /Y "settings" "dist\TEGGTouch\settings" >nul
:: 复制默认方案模板
if not exist "dist\TEGGTouch\core" mkdir "dist\TEGGTouch\core"
if exist "core\default_profile.json" copy /Y "core\default_profile.json" "dist\TEGGTouch\core\" >nul
:: 创建空的 profiles 目录
if not exist "dist\TEGGTouch\profiles" mkdir "dist\TEGGTouch\profiles"
echo      √ 数据文件已复制
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
