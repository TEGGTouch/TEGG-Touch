"""English UI regression: no Chinese chrome and no clipped single-line labels."""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton

from core.i18n import load_locale
from models.button_model import ButtonData
from models.gamepad_model import GamepadStickData, GamepadWheelData


app = QApplication.instance() or QApplication([])
CJK = re.compile(r'[一-鿿]')
# 诊断包文件名在代码中固定为中文, 英文提示需照实写出
REAL_FILE_NAMES = ('蛋挞debug日志.zip',)


class EnglishUiTests(unittest.TestCase):
    def setUp(self):
        load_locale('en')
        self.windows = []
        self.size_patch = patch('views.ui_components.dialog_size', side_effect=lambda dlg, preferred: preferred)
        self.size_patch.start()

    def tearDown(self):
        for window in self.windows:
            window.close()
        app.processEvents()
        self.size_patch.stop()
        load_locale('zh-CN')

    def show(self, window):
        self.windows.append(window)
        window.show()
        app.processEvents()
        return window

    def item(self, data):
        return SimpleNamespace(data=data, update=Mock())

    def assert_english(self, window, name):
        for widget in window.findChildren(QLabel) + window.findChildren(QPushButton) + \
                window.findChildren(QCheckBox):
            if not widget.isVisible():
                continue
            text = widget.text()
            visible = text
            for file_name in REAL_FILE_NAMES:
                visible = visible.replace(file_name, '')
            self.assertIsNone(CJK.search(visible), (name, type(widget).__name__, text))
            if isinstance(widget, QLabel) and text and not widget.wordWrap() and \
                    not text.lstrip().startswith('<') and widget.pixmap().isNull():
                line = max(text.split('\n'), key=widget.fontMetrics().horizontalAdvance)
                self.assertLessEqual(widget.fontMetrics().horizontalAdvance(line),
                                     widget.contentsRect().width() + 1, (name, text))

    def test_editors_and_settings_show_english_text_that_fits(self):
        from views.button_editor_dialog import ButtonEditorDialog
        from views.center_band_dialog import CenterBandDialog
        from views.edit_toolbar import EditToolbar
        from views.gp_stick_editor_dialog import GpStickEditorDialog
        from views.gp_wheel_editor_dialog import GpWheelEditorDialog
        from views.gp_wheel_mouse_dialog import GpWheelMouseDialog
        from views.hotkey_settings_dialog import HotkeySettingsDialog
        from views.profile_manager_dialog import _ProfileCopyDialog
        from views.profile_switch_dialog import ProfileSwitchDialog
        toolbar = self.show(EditToolbar())
        self.assert_english(toolbar, 'EditToolbar')
        self.assert_english(self.show(ButtonEditorDialog(self.item(ButtonData(name='Jump')))), 'ButtonEditor')
        self.assert_english(self.show(CenterBandDialog(self.item(ButtonData(name='Band', btn_type='center_band')),
                                                       recenter_targets=[])), 'CenterBand')
        self.assert_english(self.show(GpStickEditorDialog(self.item(GamepadStickData(name='Stick')))), 'Stick')
        wheel = self.show(GpWheelEditorDialog(self.item(GamepadWheelData(name='Wheel'))))
        self.assert_english(wheel, 'Wheel easy')
        wheel._select_mode_tab(1)
        app.processEvents()
        self.assert_english(wheel, 'Wheel advanced')
        self.assert_english(self.show(GpWheelMouseDialog(self.item(GamepadWheelData(name='Wheel')))), 'WheelMouse')
        settings = self.show(HotkeySettingsDialog())
        for index in (0, 1, 3, 4, 5):  # 2 = language page, bilingual by design
            settings._select_page(index)
            app.processEvents()
            self.assert_english(settings, 'Settings page %d' % index)
        self.assert_english(self.show(_ProfileCopyDialog('Racing', ['Racing', 'Building'])), 'ProfileCopy')
        switch = ButtonData(name='Quick Switch', btn_type='profile_switch',
                            profile_actions={'hover': {'mode': 'cycle', 'profiles': ['Racing', 'Building']}})
        self.assert_english(self.show(ProfileSwitchDialog(self.item(switch), profiles=['Racing', 'Building'])),
                            'ProfileSwitch')

    def test_quick_switch_entry_and_names_are_not_cut(self):
        from scene.touch_button_item import _format_btn_name
        from views.edit_toolbar import EditToolbar
        toolbar = self.show(EditToolbar())
        label = toolbar._switch_btn._text_lbl
        self.assertLessEqual(label.fontMetrics().horizontalAdvance(label.text()), label.width())
        self.assertEqual(_format_btn_name('Quick Switch'), 'Quick\nSwitch')
        self.assertEqual(_format_btn_name('方案切换方案切换方案'), '方案切换方案切换\n方案')

    def test_language_switch_offers_restart_and_ok_requests_it(self):
        import views.profile_manager_dialog as profile_dialogs
        from views.hotkey_settings_dialog import HotkeySettingsDialog
        prompts, answers, restarts = [], [True, False], []

        def answer(dialog):
            prompts.append([label.text() for label in dialog.findChildren(QLabel)])
            return answers.pop(0)

        with patch('views.hotkey_settings_dialog.save_hotkeys'),                 patch.object(profile_dialogs._StyledConfirmDialog, 'exec', answer):
            settings = self.show(HotkeySettingsDialog())
            settings.restart_requested.connect(lambda: restarts.append(True))
            settings._set_lang('en')  # already English: no prompt
            settings._set_lang('zh-CN')  # OK -> restart
            settings._set_lang('en')  # Cancel -> keep running
        self.assertEqual(len(prompts), 2)
        self.assertIn('需要重启', prompts[0])
        self.assertIn('Restart Required', prompts[1])
        self.assertEqual(restarts, [True])

    def test_gamepad_labels_follow_language_and_keep_reverse_lookup(self):
        from core.constants import GP_KEY_TO_LABEL, GP_LABEL_TO_KEY
        self.assertEqual(GP_KEY_TO_LABEL['LB'], 'LB')
        self.assertEqual(GP_LABEL_TO_KEY['LB'], 'LB')
        self.assertEqual(GP_LABEL_TO_KEY['左肩 LB'], 'LB')
        load_locale('zh-CN')
        self.assertEqual(GP_KEY_TO_LABEL['LB'], '左肩 LB')
        self.assertEqual(GP_LABEL_TO_KEY['左肩 LB'], 'LB')


if __name__ == '__main__':
    unittest.main()
