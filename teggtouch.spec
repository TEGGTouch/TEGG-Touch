# -*- mode: python ; coding: utf-8 -*-
"""
TEGG Touch (PyQt6) - PyInstaller spec file
Usage: pyinstaller teggtouch.spec --clean
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files

# ── collect_all: 收集包的 全部内容 (Python代码+DLL+数据文件+隐藏import) ──
vosk_datas, vosk_binaries, vosk_hidden = collect_all('vosk')
sd_datas, sd_binaries, sd_hidden = collect_all('sounddevice')

sd_data_datas = []
sd_data_binaries = []
sd_data_hidden = []
try:
    sd_data_datas, sd_data_binaries, sd_data_hidden = collect_all('_sounddevice_data')
except Exception:
    pass

all_datas = vosk_datas + sd_datas + sd_data_datas
all_binaries = vosk_binaries + sd_binaries + sd_data_binaries
all_hidden = vosk_hidden + sd_hidden + sd_data_hidden

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden + [
        # vosk 顶层无条件 import，但延迟导入导致 PyInstaller 追踪不到
        'srt', 'requests', 'tqdm', 'urllib3', 'idna',
        'charset_normalizer', 'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
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
