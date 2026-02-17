@echo off
echo ==========================================
echo       正在准备打包 TEGG Touch...
echo ==========================================
echo.

echo [1/3] 正在检查打包工具 (PyInstaller)...
pip install pyinstaller keyboard
echo.

echo [2/3] 正在清理旧的打包文件...
rmdir /s /q build
rmdir /s /q dist
del /q *.spec
echo.

echo [3/3] 正在开始打包...
echo -------------------------------------------------------
echo 正在生成独立EXE文件...
echo -------------------------------------------------------

:: 打包命令
pyinstaller --onefile --noconsole --uac-admin --clean --name "TEGG Touch" main.py

echo.
echo ==========================================
echo               ★ 打包完成！★
echo ==========================================
echo.
echo 请打开【dist】文件夹查看成品。
echo.
pause
