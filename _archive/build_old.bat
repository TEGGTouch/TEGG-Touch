@echo off
chcp 65001
echo ==========================================
echo       正在准备打包 FKB 悬浮触控助手...
echo ==========================================
echo.

echo [1/3] 正在检查打包工具 (PyInstaller)...
pip install pyinstaller
echo.

echo [2/3] 正在清理旧的打包文件...
rmdir /s /q build
rmdir /s /q dist
del /q *.spec
echo.

echo [3/3] 正在开始打包 (这可能需要几分钟，请勿关闭窗口)...
echo -------------------------------------------------------
echo 正在生成独立EXE文件，集成管理员权限和无控制台模式...
echo -------------------------------------------------------

:: 核心打包命令解释：
:: --onefile: 打包成单个exe文件 (朋友最方便)
:: --noconsole: 运行时不显示黑框
:: --uac-admin: 强制要求管理员权限 (控制游戏必须)
:: --clean: 清理缓存
:: --name: 软件名字 (这里修改为 FKB)

pyinstaller --onefile --noconsole --uac-admin --clean --name "FKB" main.py

echo.
echo ==========================================
echo               ★ 打包完成！★
echo ==========================================
echo.
echo 请打开新出现的【dist】文件夹。
echo 里面的【FKB.exe】就是最终成品！
echo.
echo 您可以直接把那个 .exe 发给朋友，不需要发其他文件。
echo.
pause