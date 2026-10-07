"""UI regression: action targets, mode gating, fixed shells and independent scrolling."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QScrollArea

from core.i18n import load_locale, t
from models.button_model import ButtonData
from models.wheel_model import WheelSectorData
from views.button_editor_dialog import ButtonEditorDialog
from views.edit_toolbar import EditToolbar, _DragHandle
from views.hotkey_settings_dialog import HotkeySettingsDialog
from views.key_remap_dialog import KeyRemapDialog
from views.voice_settings_dialog import VoiceSettingsDialog


app = QApplication.instance() or QApplication([])


class RedesignTests(unittest.TestCase):
    def setUp(self):
        load_locale('zh-CN')
        self.windows = []
        self.size_patch = patch('views.ui_components.dialog_size', side_effect=lambda dlg, preferred: preferred)
        self.size_patch.start()

    def tearDown(self):
        for window in self.windows:
            window.close()
        app.processEvents()
        self.size_patch.stop()

    def show(self, window):
        self.windows.append(window)
        window.show()
        app.processEvents()
        return window

    def action(self, window, label):
        return next(button for button in window._ui_actions if button.text() == label)

    def item(self, data=None):
        return SimpleNamespace(data=data or ButtonData(), update=Mock())

    def test_mode_request_waits_for_external_confirmation_and_does_not_move(self):
        toolbar = self.show(EditToolbar())
        toolbar.move(35, 80)
        initial = (toolbar.pos(), toolbar.size(), toolbar._mode_group.size())
        requested = QSignalSpy(toolbar.sim_mode_change_requested)
        thumb = toolbar._mode_switch._thumb.geometry()
        toolbar._mode_buttons['gamepad'].click()
        self.assertEqual(list(requested), [['gamepad']])
        self.assertEqual(toolbar._sim_mode, 'keyboard')
        self.assertEqual(toolbar._mode_stack.currentIndex(), 0)
        self.assertEqual(toolbar._mode_switch._thumb.geometry(), thumb)
        toolbar.set_sim_mode('gamepad')
        QTest.qWait(180)
        self.assertEqual(toolbar._mode_stack.currentIndex(), 1)
        self.assertEqual(toolbar._mode_switch._thumb.x(), 72)
        self.assertEqual((toolbar.pos(), toolbar.size(), toolbar._mode_group.size()), initial)
        toolbar._mode_buttons['gamepad'].click()
        self.assertEqual(len(requested), 1)

    def test_component_entries_have_equal_width_and_singleton_toggle_state(self):
        toolbar = self.show(EditToolbar())
        toolbar.resize(1070, toolbar.height())  # Offscreen's default display is only 800 px wide.
        app.processEvents()
        entries = [toolbar._add_kb_btn, toolbar._cb_btn, toolbar._wheel_btn,
                   toolbar._add_gp_btn, toolbar._add_stick_btn, toolbar._wheel_gp_btn,
                   toolbar._voice_btn, toolbar._keyboard_btn, toolbar._remap_btn]
        self.assertEqual({button.width() for button in entries}, {toolbar._remap_btn.width()})
        self.assertGreater(toolbar._run_btn.width(), toolbar._remap_btn.width())
        wheel = QSignalSpy(toolbar.wheel_clicked)
        toolbar.set_wheel_state(True)
        self.assertTrue(toolbar._wheel_btn.isChecked())
        self.assertTrue(toolbar._wheel_btn._indicator.checked)
        self.assertEqual(len(wheel), 0)
        toolbar._wheel_btn.click()
        self.assertFalse(toolbar._wheel_on)
        self.assertFalse(toolbar._wheel_btn.isChecked())
        self.assertEqual(len(wheel), 1)
        gamepad_wheel = QSignalSpy(toolbar.gp_wheel_toggle_clicked)
        toolbar.set_gp_wheel_state(True)
        self.assertTrue(toolbar._wheel_gp_btn.isChecked())
        self.assertEqual(len(gamepad_wheel), 0)
        toolbar._wheel_gp_btn.click()
        self.assertFalse(toolbar._wheel_gp_on)
        self.assertEqual(len(gamepad_wheel), 1)

    def test_long_profile_name_and_keyboard_status_keep_header_stable(self):
        toolbar = self.show(EditToolbar())
        geometry = toolbar.geometry()
        toolbar.set_profile_name('探索方案 · ' * 40)
        toolbar.set_keyboard_visible(True)
        app.processEvents()
        self.assertEqual(toolbar.geometry(), geometry)
        self.assertIn('探索方案', toolbar._profile_btn.toolTip())
        self.assertEqual(toolbar._keyboard_btn._text_lbl.text(), '隐藏')

    def test_edit_toolbar_drag_propagates_from_its_handle(self):
        toolbar = self.show(EditToolbar())
        toolbar.move(40, 60)
        handle = toolbar.findChild(_DragHandle)
        local = handle.rect().center()
        global_start = handle.mapToGlobal(local)
        moved = QSignalSpy(toolbar.moved)
        before = toolbar.pos()
        events = [
            (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, QPoint()),
            (QEvent.Type.MouseMove, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, QPoint(36, 28)),
            (QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, QPoint(36, 28)),
        ]
        with patch('PyQt6.QtWidgets.QApplication.primaryScreen', return_value=SimpleNamespace(
                geometry=lambda: QRect(0, 0, 3840, 2160))):
            for event_type, button, buttons, delta in events:
                event = QMouseEvent(event_type, QPointF(local), QPointF(global_start + delta),
                                    button, buttons, Qt.KeyboardModifier.NoModifier)
                app.sendEvent(handle, event)
        self.assertEqual(toolbar.pos() - before, QPoint(36, 28))
        self.assertEqual(len(moved), 1)
        self.assertIsNone(toolbar._drag_pos)

    def test_button_footer_save_keeps_all_mouse_actions_and_hover_modes(self):
        item = self.item(ButtonData(name='跳跃', hover='space', lclick='e', hover_toggle='q'))
        dialog = self.show(ButtonEditorDialog(item))
        saved = QSignalSpy(dialog.saved)
        dialog._fields['rclick'].add_tag('r')
        dialog._set_hover_mode('toggle')
        dialog._hover_toggle_delay_entry.setText('350')
        self.action(dialog, t('editor.save')).click()
        self.assertEqual(item.data.hover, 'space')
        self.assertEqual(item.data.hover_toggle, 'q')
        self.assertEqual(item.data.hover_mode, 'toggle')
        self.assertEqual(item.data.hover_toggle_delay, 350)
        self.assertEqual(item.data.lclick, 'e')
        self.assertEqual(item.data.rclick, 'r')
        self.assertEqual(len(saved), 1)
        item.update.assert_called_once()

    def test_footer_copy_and_delete_still_target_the_original_item(self):
        for action, signal_name in [('editor.copy', 'copied'), ('editor.delete', 'deleted')]:
            item = self.item()
            dialog = self.show(ButtonEditorDialog(item))
            signal = QSignalSpy(getattr(dialog, signal_name))
            self.action(dialog, t(action)).click()
            self.assertIs(signal[0][0], item)

    def test_wheel_sector_delete_remains_disabled(self):
        dialog = self.show(ButtonEditorDialog(self.item(WheelSectorData())))
        self.assertFalse(self.action(dialog, t('editor.delete')).isEnabled())

    def test_scrolling_does_not_move_header_footer_or_other_pane(self):
        dialog = self.show(ButtonEditorDialog(self.item()))
        scrolls = dialog.findChildren(QScrollArea)
        self.assertGreaterEqual(len(scrolls), 2)
        header, footer = dialog._ui_header.geometry(), dialog._ui_footer.geometry()
        first = scrolls[0]
        other = scrolls[-1].verticalScrollBar().value()
        first.verticalScrollBar().setValue(first.verticalScrollBar().maximum())
        app.processEvents()
        self.assertEqual(dialog._ui_header.geometry(), header)
        self.assertEqual(dialog._ui_footer.geometry(), footer)
        self.assertEqual(scrolls[-1].verticalScrollBar().value(), other)
        ys = {button.mapTo(dialog, button.rect().topLeft()).y() for button in dialog._ui_actions}
        self.assertEqual(len(ys), 1)
        dialog._fields['lclick'].focusChanged.emit(dialog._fields['lclick'])
        self.assertEqual(dialog._ui_target_hint.text(), '正在填写：左键')
        dialog._fields['hover_toggle'].focusChanged.emit(dialog._fields['hover_toggle'])
        self.assertEqual(dialog._ui_target_hint.text(), '正在填写：' + t('editor.hover_toggle_label'))

    def test_voice_copy_and_save_use_current_unsaved_editor_content(self):
        with patch.object(VoiceSettingsDialog, '_populate_mic_devices'):
            dialog = self.show(VoiceSettingsDialog([{'phrase': '跳跃', 'keys': 'space', 'action': 'click'}]))
        dialog._phrase_edit.setText('起跳')
        self.action(dialog, t('voice_dialog.copy')).click()
        self.assertEqual(len(dialog._commands), 2)
        self.assertEqual(dialog._commands[1]['phrase'], '起跳')
        self.action(dialog, t('voice_dialog.save')).click()
        self.assertEqual([c['phrase'] for c in dialog.get_result()['voice_commands']], ['起跳', '起跳'])

    def test_voice_test_uses_unsaved_phrase_and_keeps_settings_as_parent(self):
        from views.voice_test_dialog import VoiceTestDialog
        with patch.object(VoiceSettingsDialog, '_populate_mic_devices'):
            dialog = self.show(VoiceSettingsDialog([{'phrase': '跳跃', 'keys': 'space', 'action': 'click'}]))
        dialog._phrase_edit.setText('起跳')
        with patch.object(VoiceTestDialog, '_start_test'), \
             patch('views.voice_test_dialog.VoiceTestDialog', wraps=VoiceTestDialog) as test_window:
            dialog._on_test_commands()
            args, kwargs = test_window.call_args
            self.assertEqual(args[0][0]['phrase'], '起跳')
            self.assertIs(kwargs['parent'], dialog)
            self.assertIs(dialog._test_dlg.parent(), dialog)
            dialog._test_dlg.close()

    def test_empty_voice_editor_keeps_add_available_and_item_actions_disabled(self):
        with patch.object(VoiceSettingsDialog, '_populate_mic_devices'):
            dialog = self.show(VoiceSettingsDialog([]))
        self.assertTrue(self.action(dialog, t('voice_dialog.add_command')).isEnabled())
        self.assertFalse(self.action(dialog, t('voice_dialog.delete_command')).isEnabled())
        self.action(dialog, t('voice_dialog.add_command')).click()
        app.processEvents()
        self.assertTrue(self.action(dialog, t('voice_dialog.delete_command')).isEnabled())

    def test_mapping_save_retains_source_target_mode_and_enabled_state(self):
        dialog = self.show(KeyRemapDialog([{'src': 'q', 'dst': 'e', 'mode': 'hold', 'enabled': True}]))
        dialog._dst_input.add_tag('r')
        dialog._on_mode_clicked('toggle')
        self.action(dialog, t('key_remap.save')).click()
        result = dialog.get_result()['key_remaps'][0]
        self.assertEqual(result, {'src': 'q', 'dst': 'e+r', 'mode': 'toggle', 'enabled': True})

    def test_settings_pages_show_only_their_existing_footer_actions(self):
        dialog = self.show(HotkeySettingsDialog())
        initial = dialog.size()
        for page, labels in [(0, ['重置默认', '保存']), (1, ['重置箭头', '重置圆球', '保存']),
                             (2, []), (3, []), (4, []), (5, ['保存'])]:
            dialog._select_page(page)
            app.processEvents()
            self.assertEqual([b.text() for b in dialog._ui_actions if b.isVisible()], labels)
            self.assertEqual(dialog.size(), initial)
            self.assertEqual(dialog._right_wrapper.isVisible(), page == 0)

    def test_compact_settings_pages_have_no_clipped_horizontal_content(self):
        # Wide preview pages must expand their containing pane after navigation.
        # A fixed-width outer scroll wrapper previously cropped these pages.
        with patch('views.ui_components.dialog_size',
                   side_effect=lambda dlg, preferred: (min(preferred[0], 1216), min(preferred[1], 620))):
            dialog = self.show(HotkeySettingsDialog())
        header = dialog._ui_header.geometry()
        footer = dialog._ui_footer.geometry()
        for page in range(6):
            dialog._select_page(page)
            app.processEvents()
            self.assertEqual(dialog._ui_header.geometry(), header)
            self.assertEqual(dialog._ui_footer.geometry(), footer)
            for scroll in dialog.findChildren(QScrollArea):
                if scroll.isVisible():
                    self.assertEqual(scroll.horizontalScrollBar().maximum(), 0, (page, scroll.size()))


if __name__ == '__main__':
    unittest.main()
