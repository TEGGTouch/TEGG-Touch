"""Capture real Qt editor windows for the UI review, without running input engines.

Run from the repository: python scripts/capture_ui.py [zh-CN|en]
English captures are saved as docs/ui-client-en-*.png next to the Chinese ones.
The hardware/recognition/diagnostic workers are stopped for this visual inventory.
Sample fields remain in memory; no settings or editor changes are saved.
"""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QScrollArea, QAbstractScrollArea
from views.ui_components import SCROLL_GAP
from core.i18n import load_locale
from core.config_manager import init_profiles, list_profiles
from models.button_model import ButtonData
from models.gamepad_model import GamepadStickData, GamepadWheelData
from views.about_dialog import AboutDialog
from views.button_editor_dialog import ButtonEditorDialog
from views.center_band_dialog import CenterBandDialog
from views.color_picker_dialog import ColorPickerDialog
from views.diag_export_dialog import DiagExportDialog
from views.edit_toolbar import EditToolbar
from views.gamepad_install_dialog import GamepadInstallDialog
from views.gp_stick_editor_dialog import GpStickEditorDialog
from views.gp_wheel_editor_dialog import GpWheelEditorDialog
from views.gp_wheel_mouse_dialog import GpWheelMouseDialog
from views.hotkey_settings_dialog import HotkeySettingsDialog
from views.key_remap_dialog import KeyRemapDialog
from views.macro_editor_dialog import MacroEditorDialog
from views.post_update_dialog import PostUpdateDialog
from views.profile_manager_dialog import (
    ProfileManagerDialog, _ProfileCopyDialog, _StyledConfirmDialog,
    _StyledInputDialog, _StyledMessageDialog,
)
from views.profile_switch_dialog import ProfileSwitchDialog
from views.run_toolbar import RunToolbar, CollapsedBubble
from views.update_dialog import UpdateDialog
from views.voice_settings_dialog import VoiceSettingsDialog, _ChunkSizeDialog
from views.voice_test_dialog import VoiceTestDialog
from views.wheel_style_dialog import WheelStyleDialog
from views.virtual_keyboard import VirtualKeyboard


def item(data):
    return SimpleNamespace(data=data, update=lambda: None)


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else 'zh-CN'
    load_locale(lang)
    prefix = 'ui-client-' if lang.startswith('zh') else 'ui-client-en-'
    app = QApplication(sys.argv)
    profile_name, _ = init_profiles()
    targets = [{'key': 'stick:L', 'label': '左摇杆'}]
    commands = [
        {'phrase': '起跳', 'keys': 'space', 'action': 'click'},
        {'phrase': '打开地图', 'keys': 'm', 'action': 'click'},
        {'phrase': '向前走', 'keys': 'w', 'action': 'press'},
    ]
    factories = [
        lambda: EditToolbar(),
        lambda: RunToolbar(),
        lambda: ButtonEditorDialog(item(ButtonData(name='跳跃', hover='space', lclick='e', rclick='r'))),
        lambda: CenterBandDialog(item(ButtonData(name='回中带', btn_type='center_band')), recenter_targets=targets),
        lambda: GpStickEditorDialog(item(GamepadStickData(name='左摇杆'))),
        lambda: GpWheelEditorDialog(item(GamepadWheelData(name='方向盘'))),
        lambda: GpWheelMouseDialog(item(GamepadWheelData(name='方向盘'))),
        lambda: KeyRemapDialog([{'src': 'caps lock', 'dst': 'escape', 'mode': 'click', 'enabled': True}]),
        lambda: VoiceSettingsDialog(commands),
        lambda: VoiceTestDialog(commands, 'zh-CN'),
        lambda: MacroEditorDialog({'name': '交互后切换', 'steps': [
            {'type': 'key', 'key': 'e', 'action': 'click'},
            {'type': 'delay', 'ms': 200},
            {'type': 'key', 'key': '1', 'action': 'click'},
        ]}, mode='mix'),
        lambda: HotkeySettingsDialog(),
        lambda: WheelStyleDialog(),
        lambda: ProfileManagerDialog(),
        lambda: _ProfileCopyDialog(profile_name, list_profiles()),
        lambda: _StyledInputDialog('方案名称', '请输入名称', '探索与建造 · 键盘方案'),
        lambda: _StyledConfirmDialog('删除方案', '确定删除这个方案吗？'),
        lambda: _StyledMessageDialog('方案提示', '请选择需要查看或应用的方案。'),
        lambda: _ChunkSizeDialog(4000),
        lambda: AboutDialog(),
        lambda: UpdateDialog('0.2.2', '', '版本更新说明\n\n改进体验与稳定性。'),
        lambda: PostUpdateDialog(str(ROOT)),
        lambda: GamepadInstallDialog(),
        lambda: DiagExportDialog(),
        lambda: ColorPickerDialog(QColor('#F59E0B'), title='选择颜色'),
        lambda: VirtualKeyboard(),
        lambda: CollapsedBubble(),
        lambda: ProfileSwitchDialog(item(ButtonData(name='方案切换', btn_type='profile_switch', profile_actions={
            'hover': {'mode': 'cycle', 'profiles': list_profiles()[:2]}})), profiles=list_profiles()),
    ]
    output = ROOT / 'docs'
    report = []

    def capture(window, name):
        window.show()
        app.processEvents()
        window.grab().save(str(output / (name + '.png')))
        entry = {'window': type(window).__name__, 'image': name + '.png',
                 'size': [window.width(), window.height()]}
        if hasattr(window, '_ui_header'):
            entry.update(header=window._ui_header.height(), footer=window._ui_footer.height())
            # Original state gates may hide actions; visible actions share one baseline.
            ys = {button.mapTo(window, QPoint()).y() for button in window._ui_actions if button.isVisible()}
            assert len(ys) <= 1, (name, ys)
            if window._ui_guidance:
                hint = window._ui_guidance
                assert window._ui_footer.isAncestorOf(hint)
                assert hint.heightForWidth(hint.width()) <= hint.height(), (name, 'footer guidance')
            for area in window.findChildren(QAbstractScrollArea):
                if area.isVisible():
                    assert area.viewportMargins().right() == SCROLL_GAP, (name, 'scrollbar gap')
        report.append(entry)

    with patch.object(VoiceTestDialog, '_start_test'), \
         patch.object(GamepadInstallDialog, '_enter_detecting'), \
         patch.object(DiagExportDialog, '_start'):
        for factory in factories:
            window = factory()
            name = type(window).__name__
            if isinstance(window, GamepadInstallDialog):
                window._status_info = {'installed_version': '1.22'}
                window._enter_ready_ok()
            capture(window, prefix + name)
            if isinstance(window, EditToolbar):
                window.set_sim_mode('gamepad')
                QTest.qWait(180)
                capture(window, prefix + 'EditToolbar-gamepad')
            if isinstance(window, RunToolbar):
                window.set_profile_name('探索、建造与竞速 · 常用游戏方案 · 手柄')
                capture(window, prefix + 'RunToolbar-long-name')
            if isinstance(window, VoiceSettingsDialog):
                nested = MacroEditorDialog({'name': '语音交互', 'steps': [
                    {'type': 'key', 'key': 'e', 'action': 'click'},
                    {'type': 'delay', 'ms': 200},
                ]}, parent=window, mode='mix')
                capture(nested, prefix + 'voice-macro')
                nested.close()
                nested.deleteLater()
                app.processEvents()
            if isinstance(window, HotkeySettingsDialog):
                for index in range(window._stack.count()):
                    window._select_page(index)
                    capture(window, prefix + 'settings-' + str(index))
            if isinstance(window, GpWheelEditorDialog):
                window._select_mode_tab(1)
                capture(window, prefix + 'direction-advanced')
            if isinstance(window, WheelStyleDialog):
                for wheel_type in ('large', 'double', 'dual'):
                    window._select_type(wheel_type)
                    capture(window, prefix + 'wheel-' + wheel_type)
            window.close()
            window.deleteLater()
            app.processEvents()

        # Simulate the available logical area of a smaller / highly scaled screen.
        with patch('views.ui_components.dialog_size',
                   side_effect=lambda dlg, preferred: (min(preferred[0], 1216), min(preferred[1], 620))):
            for index in (2, 5, 7, 8, 11, 12):
                window = factories[index]()
                if isinstance(window, WheelStyleDialog):
                    window._select_type('dual')
                capture(window, prefix.replace('client', 'compact') + type(window).__name__)
                for sc in window.findChildren(QScrollArea):
                    if sc.isVisible():
                        assert sc.horizontalScrollBar().maximum() == 0, type(window).__name__
                window.close()
                window.deleteLater()
                app.processEvents()
    screen = app.primaryScreen()
    result = {'screen': [screen.size().width(), screen.size().height()],
              'available': [screen.availableGeometry().width(), screen.availableGeometry().height()],
              'device_pixel_ratio': screen.devicePixelRatio(), 'windows': report}
    (output / ('ui-capture-report.json' if lang.startswith('zh') else 'ui-capture-report-en.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Captured', len(report), 'actual Qt views. Screen:', result['screen'])


if __name__ == '__main__':
    main()
