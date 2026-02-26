"""
TEGG Touch - 语音引擎独立测试脚本

用法:
    cd TEGGTouch-PyQt6
    python -m tests.test_voice_engine [--lang zh-CN|en]

测试流程:
    1. 检查依赖（vosk, sounddevice）
    2. 检查模型文件
    3. 配置几条测试指令
    4. 启动 VoiceEngine
    5. 对麦克风说话 → 控制台打印识别结果
    6. 验证 click/press/release 三种动作
    7. Ctrl+C 停止
"""

import sys
import os
import argparse
import time

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def test_model():
    """测试 VoiceCommandData 数据模型"""
    from models.voice_model import VoiceCommandData

    print("=" * 50)
    print("[TEST] VoiceCommandData 模型测试")
    print("=" * 50)

    # 创建实例
    cmd = VoiceCommandData(phrase="开火", keys="space", action="click")
    print(f"  创建: {cmd}")

    # 序列化
    d = cmd.to_dict()
    print(f"  to_dict: {d}")
    assert d == {'phrase': '开火', 'keys': 'space', 'action': 'click'}

    # 反序列化
    cmd2 = VoiceCommandData.from_dict(d)
    print(f"  from_dict: {cmd2}")
    assert cmd2.phrase == "开火"
    assert cmd2.keys == "space"
    assert cmd2.action == "click"

    # 带额外字段的反序列化（忽略未知字段）
    d_extra = {'phrase': 'jump', 'keys': 'w', 'action': 'press', 'unknown_field': 123}
    cmd3 = VoiceCommandData.from_dict(d_extra)
    assert cmd3.phrase == "jump"
    print(f"  extra fields ignored: {cmd3}")

    print("  [PASS] 模型测试通过\n")


def test_dependency_check():
    """测试依赖检查"""
    print("=" * 50)
    print("[TEST] 依赖检查")
    print("=" * 50)

    try:
        import vosk
        print(f"  vosk: OK (version may vary)")
    except ImportError:
        print("  vosk: NOT INSTALLED")
        print("  请运行: pip install vosk")
        return False

    try:
        import sounddevice as sd
        print(f"  sounddevice: OK")
        # 检测可用设备
        devices = sd.query_devices()
        input_devs = [d for d in devices if d['max_input_channels'] > 0]
        print(f"  可用输入设备: {len(input_devs)} 个")
        if input_devs:
            default_input = sd.query_devices(kind='input')
            print(f"  默认输入: {default_input['name']}")
        else:
            print("  [WARN] 未发现麦克风设备")
    except ImportError:
        print("  sounddevice: NOT INSTALLED")
        print("  请运行: pip install sounddevice")
        return False
    except Exception as e:
        print(f"  sounddevice 检查异常: {e}")

    print("  [PASS] 依赖检查完成\n")
    return True


def test_model_files():
    """测试模型文件是否存在"""
    from core.constants import VOICE_MODELS_DIR, VOICE_MODEL_MAP

    print("=" * 50)
    print("[TEST] Vosk 模型文件检查")
    print("=" * 50)
    print(f"  模型目录: {VOICE_MODELS_DIR}")

    all_ok = True
    for lang, name in VOICE_MODEL_MAP.items():
        path = os.path.join(VOICE_MODELS_DIR, name)
        exists = os.path.isdir(path)
        status = "OK" if exists else "MISSING"
        print(f"  [{lang}] {name}: {status}")
        if not exists:
            all_ok = False

    if all_ok:
        print("  [PASS] 所有模型文件就绪\n")
    else:
        print("  [WARN] 部分模型缺失，请下载并放入上述目录\n")
    return all_ok


def test_error_handling():
    """测试错误处理（无模型/无指令）"""
    from PyQt6.QtWidgets import QApplication
    from engine.voice_engine import VoiceEngine

    print("=" * 50)
    print("[TEST] 错误处理测试")
    print("=" * 50)

    app = QApplication.instance() or QApplication(sys.argv)
    errors = []

    engine = VoiceEngine()
    engine.error_occurred.connect(lambda e: errors.append(e))

    # 测试空指令列表
    engine.start(commands=[], language='zh-CN')
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()
    engine.stop()

    if errors:
        print(f"  空指令: 正确捕获错误 -> {errors[-1]}")
    else:
        print("  空指令: 未捕获错误（依赖可能缺失）")

    # 测试无效语言
    errors.clear()
    engine2 = VoiceEngine()
    engine2.error_occurred.connect(lambda e: errors.append(e))
    engine2.start(
        commands=[{'phrase': 'test', 'keys': 'a', 'action': 'click'}],
        language='xx-INVALID'
    )
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()
    engine2.stop()

    if errors:
        print(f"  无效语言: 正确捕获错误 -> {errors[-1]}")
    else:
        print("  无效语言: 未捕获错误（依赖可能缺失）")

    print("  [PASS] 错误处理测试完成\n")


def test_live_recognition(language='zh-CN'):
    """实时语音识别测试（交互式）"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from engine.voice_engine import VoiceEngine

    print("=" * 50)
    print(f"[TEST] 实时语音识别 (语言: {language})")
    print("=" * 50)

    # 定义测试指令
    if language == 'zh-CN':
        commands = [
            {'phrase': '开火', 'keys': 'space', 'action': 'click'},
            {'phrase': '跳', 'keys': 'w', 'action': 'click'},
            {'phrase': '前进', 'keys': 'w', 'action': 'press'},
            {'phrase': '停', 'keys': 'w', 'action': 'release'},
            {'phrase': '攻击', 'keys': 'j', 'action': 'click'},
        ]
    else:
        commands = [
            {'phrase': 'fire', 'keys': 'space', 'action': 'click'},
            {'phrase': 'jump', 'keys': 'w', 'action': 'click'},
            {'phrase': 'forward', 'keys': 'w', 'action': 'press'},
            {'phrase': 'stop', 'keys': 'w', 'action': 'release'},
            {'phrase': 'attack', 'keys': 'j', 'action': 'click'},
        ]

    print("  配置的语音指令:")
    for cmd in commands:
        print(f"    '{cmd['phrase']}' -> keys='{cmd['keys']}', action={cmd['action']}")
    print()

    app = QApplication.instance() or QApplication(sys.argv)
    engine = VoiceEngine()

    def on_command(phrase, keys, action):
        action_desc = {'click': '点击', 'press': '按住', 'release': '释放'}.get(action, action)
        print(f"  >>> 识别到: '{phrase}' -> 按键='{keys}', 动作={action_desc}")

    def on_status(status):
        print(f"  [状态] {status}")

    def on_error(error):
        print(f"  [错误] {error}")

    engine.command_recognized.connect(on_command)
    engine.status_changed.connect(on_status)
    engine.error_occurred.connect(on_error)

    print("  正在启动语音引擎...")
    engine.start(commands, language)

    print("  请对麦克风说出上述指令。按 Ctrl+C 停止。\n")

    # 设置 30 秒超时自动停止
    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(lambda: print("\n  [超时] 30秒测试结束") or app.quit())
    timeout_timer.start(30000)

    try:
        app.exec()
    except KeyboardInterrupt:
        print("\n  [中断] 用户停止")
    finally:
        engine.stop()
        print("  语音引擎已停止")
        print("  [DONE] 实时测试结束\n")


def main():
    parser = argparse.ArgumentParser(description='TEGG Touch 语音引擎测试')
    parser.add_argument('--lang', default='zh-CN', choices=['zh-CN', 'en'],
                        help='语音识别语言 (默认: zh-CN)')
    parser.add_argument('--live', action='store_true',
                        help='运行实时麦克风测试（需要模型文件）')
    args = parser.parse_args()

    print("\n" + "=" * 50)
    print("  TEGG Touch 语音引擎测试套件")
    print("=" * 50 + "\n")

    # 1. 数据模型测试（总是运行）
    test_model()

    # 2. 依赖检查
    deps_ok = test_dependency_check()

    # 3. 模型文件检查
    models_ok = test_model_files()

    # 4. 错误处理测试（需要 PyQt6 和 vosk）
    if deps_ok:
        test_error_handling()

    # 5. 实时测试（仅在 --live 且依赖+模型就绪时运行）
    if args.live:
        if deps_ok and models_ok:
            test_live_recognition(args.lang)
        else:
            print("[SKIP] 实时测试跳过：依赖或模型文件缺失")
    else:
        print("提示: 使用 --live 参数运行实时麦克风测试")
        print(f"  python -m tests.test_voice_engine --live --lang {args.lang}")

    print("\n测试完成。")


if __name__ == '__main__':
    main()
