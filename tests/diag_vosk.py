"""
Vosk 打包环境诊断脚本 — 直接在 dist 目录下双击运行或 python diag_vosk.py

把这个文件复制到 dist/TEGGTouch/ 目录下运行即可。
"""
import sys
import os
import traceback

print("=" * 60)
print("  Vosk 打包诊断")
print("=" * 60)

frozen = getattr(sys, 'frozen', False)
print(f"frozen: {frozen}")
print(f"sys.executable: {sys.executable}")
print(f"cwd: {os.getcwd()}")
print(f"__file__: {__file__}")
print(f"Python: {sys.version}")
print()

# 1. 检查 vosk 包目录
if frozen:
    internal = os.path.join(os.path.dirname(sys.executable), '_internal')
else:
    internal = os.path.dirname(os.path.abspath(__file__))

vosk_pkg = os.path.join(internal, 'vosk') if frozen else None
print(f"[1] vosk package dir: {vosk_pkg}")
if vosk_pkg and os.path.isdir(vosk_pkg):
    print(f"    contents: {os.listdir(vosk_pkg)}")
else:
    print(f"    NOT FOUND (non-frozen or missing)")
print()

# 2. 尝试 import vosk
print("[2] import vosk...")
try:
    # 手动注入 DLL 搜索路径
    if frozen and sys.platform == 'win32' and vosk_pkg and os.path.isdir(vosk_pkg):
        os.environ['PATH'] = vosk_pkg + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(vosk_pkg)
        print(f"    DLL dir added: {vosk_pkg}")

    import vosk
    print(f"    OK! vosk.__file__: {vosk.__file__}")
    print(f"    vosk version attrs: {[a for a in dir(vosk) if 'version' in a.lower()]}")
except Exception as e:
    print(f"    FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    input("\n按回车退出...")
    sys.exit(1)
print()

# 3. 检查模型路径
if frozen:
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

models_dir = os.path.join(app_dir, 'models', 'vosk')
model_name = 'vosk-model-small-cn-0.22'
model_path = os.path.join(models_dir, model_name)

print(f"[3] model path: {model_path}")
print(f"    exists: {os.path.isdir(model_path)}")
if os.path.isdir(model_path):
    for root, dirs, files in os.walk(model_path):
        for f in files:
            fp = os.path.join(root, f)
            sz = os.path.getsize(fp)
            rel = os.path.relpath(fp, model_path)
            print(f"    {rel} ({sz:,} bytes)")
else:
    print(f"    MODEL DIR MISSING!")
    input("\n按回车退出...")
    sys.exit(1)
print()

# 4. 检查路径编码
print(f"[4] path encoding check:")
encoded = model_path.encode('utf-8')
print(f"    UTF-8 bytes: {encoded}")
print(f"    has non-ASCII: {any(b > 127 for b in encoded)}")
print(f"    path repr: {repr(model_path)}")
print()

# 5. 尝试加载模型 (带日志)
print("[5] vosk.Model() test...")
vosk.SetLogLevel(0)  # 开启 vosk 日志看错误细节
try:
    model = vosk.Model(model_path)
    print(f"    SUCCESS! model loaded")
except Exception as e:
    print(f"    FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()

    # 5b. 试试用短路径 (8.3 格式) 绕过中文路径问题
    print()
    print("[5b] 尝试短路径...")
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetShortPathNameW(model_path, buf, 512)
        short_path = buf.value
        if short_path and short_path != model_path:
            print(f"    short path: {short_path}")
            model = vosk.Model(short_path)
            print(f"    SUCCESS with short path!")
        else:
            print(f"    no short path available (same as original)")
    except Exception as e2:
        print(f"    short path also FAILED: {e2}")

    # 5c. 试试复制到纯 ASCII 路径
    print()
    print("[5c] 尝试纯 ASCII 临时路径...")
    try:
        import shutil, tempfile
        tmp = os.path.join(tempfile.gettempdir(), 'vosk_test_model')
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        shutil.copytree(model_path, tmp)
        print(f"    temp path: {tmp}")
        model = vosk.Model(tmp)
        print(f"    SUCCESS with ASCII path! <-- 中文路径是问题根因")
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e3:
        print(f"    ASCII path also FAILED: {e3}")
        print(f"    问题不是路径编码，可能是模型文件损坏或 DLL 问题")

print()
print("=" * 60)
print("  诊断完成")
print("=" * 60)
input("\n按回车退出...")
