"""
TEGG Touch — 打包产物 smoke test
build.bat / pack_release.bat 自动调用; 退出码非 0 = 打包缺关键依赖, 阻止发版。

加新依赖时往 REQUIRED_PATHS 加一行, 不要单纯依赖手工测启动 (Windows UAC + 静默崩溃组合很容易漏)。
"""
import sys
import os
# Windows 控制台默认 GBK, 强制 stdout/stderr UTF-8 避免 ✓ ✗ 这类符号 raise UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

if len(sys.argv) > 1:
    dist_dir = sys.argv[1]
else:
    from core.constants import APP_VERSION
    dist_dir = os.path.join(os.path.dirname(__file__), 'dist', f'TEGGTouch_v{APP_VERSION}')

if not os.path.isdir(dist_dir):
    print(f"FAIL: dist 目录不存在: {dist_dir}")
    sys.exit(2)

INTERNAL = os.path.join(dist_dir, '_internal')

# 关键文件/目录清单 — 加新依赖后必须补这里
# (root, relpath, desc) — root = 'dist' 表 dist_dir 根目录, 'internal' 表 _internal/ 下
REQUIRED_PATHS = [
    # PyInstaller 本体产物 (dist 根)
    ('dist', 'TEGGTouch.exe', 'exe'),
    # 第三方 native 依赖 (PyInstaller 收到 _internal/)
    ('internal', 'vosk/libvosk.dll', 'vosk DLL'),
    ('internal', '_sounddevice_data/portaudio-binaries/libportaudio64bit.dll',
     'sounddevice portaudio DLL'),
    # vgamepad — v0.3.0 漏过一次, 之后必须保留这条
    ('internal', 'vgamepad/win/vigem/client/x64/ViGEmClient.dll',
     'vgamepad ViGEmClient DLL (x64)'),
    ('internal', 'vgamepad/win/vigem/install/x64/ViGEmBusSetup_x64.msi',
     'vgamepad ViGEmBus 安装包 (x64)'),
    # 项目自带资源 (build.bat copy 到 dist 根, 不在 _internal/)
    ('dist', 'assets/icon.ico', 'app 图标'),
    ('dist', 'assets/wheel_stroke.svg', '方向盘 SVG (stroke)'),
    ('dist', 'assets/wheel_fill.svg', '方向盘 SVG (fill)'),
    ('dist', 'locales/zh-CN.json', '中文本地化'),
    ('dist', 'core/default_profile.json', '默认 profile 模板'),
    ('dist', 'models/vosk', 'Vosk 模型目录'),
]

errors = []
for root, rel, desc in REQUIRED_PATHS:
    base = dist_dir if root == 'dist' else INTERNAL
    full = os.path.join(base, rel)
    if not os.path.exists(full):
        errors.append(f"  ✗ 缺失: {desc}\n     期望路径: {full}")

if errors:
    print("==========================================")
    print("    ✗ Smoke test 失败 — 打包不完整")
    print("==========================================")
    for e in errors:
        print(e)
    print()
    print("通常原因: spec 文件 (teggtouch.spec) 没收对应包")
    print("修复: 在 spec 顶部加 collect_all('<包名>') 然后重新 build")
    sys.exit(1)

print("==========================================")
print("    ✓ Smoke test 通过")
print("==========================================")
print(f"  目录: {dist_dir}")
print(f"  检查项: {len(REQUIRED_PATHS)} 全部命中")
sys.exit(0)
