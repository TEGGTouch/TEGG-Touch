# -*- mode: python ; coding: utf-8 -*-
"""
TEGG Touch (PyQt6) - PyInstaller spec file
Usage: pyinstaller teggtouch.spec --clean

数据文件(locales/assets/models等)由 build.bat 手动复制到 EXE 同级目录,
不走 datas, 以匹配 APP_DIR = os.path.dirname(sys.executable) 的路径逻辑,
同时让用户可以直接管理 profiles/ 和 models/ 目录。
"""

from PyInstaller.utils.hooks import collect_dynamic_libs

# ── 收集原生 DLL ──
# vosk 包内含 kaldi 等原生库，
# hiddenimports 只嵌入 Python 代码到 PYZ，不会自动收集这些原生库。
# 缺少时 import vosk 会抛出 OSError 导致闪退。
vosk_binaries = collect_dynamic_libs('vosk')

# sounddevice 依赖 _sounddevice_data 包中的 libportaudio*.dll (PortAudio)。
# hiddenimports 只引入 Python 代码，不会收集 PortAudio 原生 DLL。
# 缺少时 import sounddevice 会抛 OSError，导致语音功能在打包版无法使用。
sounddevice_binaries = collect_dynamic_libs('sounddevice')
try:
    sounddevice_binaries += collect_dynamic_libs('_sounddevice_data')
except Exception:
    pass  # _sounddevice_data 不一定存在（取决于 sounddevice 版本）

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=vosk_binaries + sounddevice_binaries,
    datas=[],
    hiddenimports=[
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'keyboard',
        'vosk',
        'sounddevice',
        '_sounddevice_data',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除系统 Python 环境中与本项目无关的大型库
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'tensorboard',
        'transformers', 'tokenizers',
        'pandas', 'scipy', 'sklearn', 'scikit-learn',
        'PIL', 'Pillow',
        'matplotlib', 'plotly', 'seaborn',
        'lxml', 'bs4', 'beautifulsoup4',
        'jinja2', 'flask', 'django', 'fastapi',
        'sympy', 'psutil',
        'cryptography', 'pydantic',
        'fsspec', 'lz4', 'regex',
        'anyio', 'httpx', 'httpcore',
        'setuptools', 'pkg_resources', 'pip',
        'pytest', 'unittest',
        # sherpa 全家桶（已移除，显式排除防止被间接引入）
        'sherpa_onnx', 'sentencepiece', 'pypinyin', 'numpy',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TEGGTouch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TEGGTouch',
)
