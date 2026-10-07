"""UI regression: action targets, mode gating, fixed shells and independent scrolling."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QMouseEvent, QColor
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QScrollArea, QColorDialog, QStyle, QStyleOptionSlider

from core.i18n import load_locale, t
from models.button_model import ButtonData
from models.wheel_model import WheelSectorData
from models.gamepad_model import GamepadWheelData
from views.button_editor_dialog import ButtonEditorDialog
from views.color_picker_dialog import ColorPickerDialog
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
        animation_finished = QSignalSpy(toolbar._mode_switch._animation.finished)
        toolbar.set_sim_mode('gamepad')
        self.assertTrue(animation_finished.wait(1000))
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

    def test_candidate_segments_keep_pages_and_insert_into_the_focused_field(self):
        dialog = self.show(ButtonEditorDialog(self.item()))
        for index, button in dialog._segments.buttons.items():
            button.click()
            app.processEvents()
            self.assertEqual(dialog._tab_stack.currentIndex(), index)
        dialog._fields['lclick'].focusChanged.emit(dialog._fields['lclick'])
        dialog._segments.buttons[0].click()
        dialog._on_key_clicked('e')
        self.assertEqual(dialog._fields['lclick'].get_value(), 'e')
        dialog._hover_segments.buttons['toggle'].click()
        self.assertEqual(dialog._hover_mode, 'toggle')
        self.assertEqual(dialog._hover_stack.currentIndex(), 1)

    def test_profile_segments_keep_the_original_content_page_selection(self):
        from views.profile_manager_dialog import ProfileManagerDialog
        dialog = self.show(ProfileManagerDialog())
        panel = dialog._detail_panel
        for index, (key, button) in enumerate(panel._tab_btns.items()):
            button.click()
            app.processEvents()
            self.assertEqual(panel._cur_tab, key)
            self.assertEqual(panel._stack.currentIndex(), index)
        self.assertTrue(dialog._ui_footer.isAncestorOf(dialog._ui_guidance))
        self.assertFalse(dialog._ui_body.isAncestorOf(dialog._ui_guidance))

    def test_direction_segments_keep_disabled_modes_and_native_radio_exclusion(self):
        from views.gp_wheel_editor_dialog import GpWheelEditorDialog
        dialog = self.show(GpWheelEditorDialog(self.item(GamepadWheelData())))
        dialog._select_mode_tab(1)
        section = dialog._lt_section
        section.set_disabled_modes({'buttons'}, '被另一个扳机采用')
        disabled = section._mode_btns['buttons']
        before = section.current_mode()
        disabled.click()
        self.assertEqual(section.current_mode(), before)
        self.assertFalse(disabled.isEnabled())
        self.assertEqual(disabled.toolTip(), '被另一个扳机采用')
        dialog._rb_square.setFocus()
        QTest.keyClick(dialog._rb_square, Qt.Key.Key_Space)
        self.assertTrue(dialog._rb_square.isChecked())
        dialog._rb_square.click()
        self.assertTrue(dialog._rb_square.isChecked())
        self.assertFalse(dialog._rb_linear.isChecked())
        dialog._rb_linear.click()
        self.assertTrue(dialog._rb_linear.isChecked())
        self.assertFalse(dialog._rb_square.isChecked())
        QTest.mouseClick(dialog._rb_square, Qt.MouseButton.LeftButton,
                         pos=dialog._rb_square.rect().center())
        self.assertTrue(dialog._rb_square.isChecked())
        self.assertFalse(dialog._rb_linear.isChecked())

    def test_color_samples_and_dynamically_added_macro_steps_keep_real_values(self):
        from views.macro_editor_dialog import MacroEditorDialog
        from PyQt6.QtWidgets import QPushButton
        settings = self.show(HotkeySettingsDialog())
        sample = QPushButton(settings)
        settings._apply_color_btn_style(sample, '#0284C7')
        app.processEvents()
        self.assertEqual(sample.text(), '#0284C7')
        self.assertIn('background: #0284C7', sample.styleSheet())
        macro = self.show(MacroEditorDialog({'name': '示范', 'steps': []}, mode='mix'))
        self.action(macro, t('macro.add_key_step')).click()
        app.processEvents()
        self.assertEqual(len(macro._step_rows), 1)
        row = macro._step_rows[0]
        row._key_input.add_tag('space')
        self.assertEqual(row.get_step_data()['key'], 'space')

    def test_color_picker_footer_confirm_returns_selected_color_and_alpha(self):
        chosen = QColor(16, 185, 129, 128)

        def confirm():
            picker = next(w for w in app.topLevelWidgets()
                          if isinstance(w, ColorPickerDialog) and w.isVisible())
            picker.setCurrentColor(chosen)
            picker._ok_button.click()

        QTimer.singleShot(0, confirm)
        result = ColorPickerDialog.getColor(QColor('#F59E0B'),
                 options=QColorDialog.ColorDialogOption.ShowAlphaChannel)
        self.assertEqual(result.rgba(), chosen.rgba())

    def test_wheel_style_scrolls_only_the_type_list_and_keeps_content_visible(self):
        from views.wheel_style_dialog import WheelStyleDialog
        for lang in ('zh-CN', 'en'):
            load_locale(lang)
            with patch('views.ui_components.dialog_size', side_effect=lambda dlg, preferred: (1216, 620)):
                dialog = self.show(WheelStyleDialog(wheel_mode='double'))
            scrolls = dialog.findChildren(QScrollArea)
            self.assertEqual(scrolls, [dialog._type_scroll])
            self.assertGreater(dialog._type_scroll.verticalScrollBar().maximum(), 0)
            positions = [panel.geometry() for panel in (dialog._preview_panel, dialog._info_panel)]
            for wheel_type in ('small', 'large', 'double', 'dual'):
                dialog._select_type(wheel_type)
                app.processEvents()
                for panel in (dialog._preview_panel, dialog._info_panel):
                    self.assertTrue(dialog._ui_body.rect().contains(panel.geometry()))
                preview = dialog._current_preview
                self.assertTrue(dialog._preview_panel.rect().contains(preview.geometry()))
                self.assertGreaterEqual(dialog._reset_btn.width(),
                    dialog._reset_btn.fontMetrics().horizontalAdvance(dialog._reset_btn.text()) + 64)
                for track in (dialog._center_mode_wrap, dialog._middle_mode_wrap):
                    if track.isVisible():
                        self.assertTrue(dialog._info_panel.rect().contains(
                            QRect(track.mapTo(dialog._info_panel, QPoint()), track.size())))
            dialog._type_scroll.verticalScrollBar().setValue(dialog._type_scroll.verticalScrollBar().maximum())
            app.processEvents()
            self.assertEqual([panel.geometry() for panel in (dialog._preview_panel, dialog._info_panel)], positions)

    def test_wheel_vertical_choices_keep_ring_modes_visibility_and_save(self):
        from views.wheel_style_dialog import WheelStyleDialog
        from core.constants import RING_MODES
        dialog = self.show(WheelStyleDialog(wheel_mode='double'))
        for mode in RING_MODES:
            dialog._center_mode_btns[mode].click()
            self.assertEqual(dialog._center_ring_mode, mode)
            self.assertEqual(dialog._current_preview._center_ring_mode, mode)
        dialog._middle_mode_btns['half_h'].click()
        dialog._ring_cb.setChecked(False)
        dialog._center_mode_btns['whole'].click()
        self.assertEqual(dialog._center_ring_mode, 'octa')
        self.assertFalse(dialog._current_preview._center_ring_visible)
        self.action(dialog, t('wheel_style.save')).click()
        result = dialog.get_result()
        self.assertEqual(result['wheel_center_ring_mode'], 'octa')
        self.assertEqual(result['wheel_inner_ring_mode'], 'half_h')
        self.assertFalse(result['wheel_center_ring_visible'])

    def test_wider_wheel_reset_keeps_inner_and_outer_default_keys(self):
        from views.wheel_style_dialog import WheelStyleDialog
        from core.constants import default_wheel_sectors, default_wheel_outer_sectors
        dialog = self.show(WheelStyleDialog(wheel_mode='large'))
        dialog._select_type('dual')
        signal = QSignalSpy(dialog.settings_changed)
        dialog._reset_btn.click()
        result = dialog.get_result()
        self.assertEqual(result['reset_sectors'], default_wheel_sectors())
        self.assertEqual(result['reset_outer_sectors'], default_wheel_outer_sectors())
        self.assertEqual(signal[0][0], result)
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_run_profile_name_keeps_full_tooltip_and_all_actions_visible(self):
        from views.run_toolbar import RunToolbar
        from views.edit_toolbar import _IconTextBtn
        for language in ('zh-CN', 'en'):
            load_locale(language)
            toolbar = self.show(RunToolbar())
            full_name = '探索、建造与竞速 · 常用游戏方案 · 手柄' * 3
            toolbar.set_profile_name(full_name)
            app.processEvents()
            self.assertEqual(toolbar._profile_lbl.toolTip(), full_name)
            self.assertLessEqual(toolbar._profile_lbl.fontMetrics().horizontalAdvance(
                toolbar._profile_lbl.text()), toolbar._profile_lbl.width())
            for button in toolbar.findChildren(_IconTextBtn):
                self.assertTrue(toolbar.rect().contains(button.mapTo(toolbar, QPoint())))
                self.assertTrue(toolbar.rect().contains(button.mapTo(toolbar,
                    button.rect().bottomRight())))
            screen = QRect(0, 0, 1920, 1080)
            with patch('PyQt6.QtWidgets.QApplication.primaryScreen',
                       return_value=Mock(geometry=lambda: screen)):
                toolbar._position_toolbar()
                self.assertLessEqual(abs(toolbar.frameGeometry().center().x()
                                         - screen.center().x()), 1)
                toolbar.set_saved_position(1910, 1070)
                self.assertTrue(screen.contains(toolbar.frameGeometry()))

    def test_voice_nested_macro_editor_keeps_steps_and_emits_existing_save_signal(self):
        from views.macro_editor_dialog import MacroEditorDialog
        steps = [{'type': 'key', 'key': 'space', 'action': 'click'},
                 {'type': 'delay', 'ms': 200}]
        with patch.object(VoiceSettingsDialog, '_populate_mic_devices'):
            voice = self.show(VoiceSettingsDialog([], xmacros=[{'name': '起跳', 'steps': steps}]))
        saved = QSignalSpy(voice.xmacros_changed)
        def edit_macro():
            macro = app.activeModalWidget()
            self.assertIsInstance(macro, MacroEditorDialog)
            macro._add_delay_step()
            self.action(macro, t('macro.save')).click()
        QTimer.singleShot(0, edit_macro)
        voice._edit_macro(0)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][0], [{'name': '起跳', 'steps': steps + [{'type': 'delay', 'ms': 100}]}])

    def test_larger_bubble_preserves_three_click_actions_and_drag_threshold(self):
        from views.run_toolbar import CollapsedBubble
        bubble = self.show(CollapsedBubble())
        clicks = [(Qt.MouseButton.LeftButton, bubble.toggle_toolbar_requested),
                  (Qt.MouseButton.RightButton, bubble.toggle_buttons_requested),
                  (Qt.MouseButton.MiddleButton, bubble.stop_requested)]
        spies = [QSignalSpy(signal) for _, signal in clicks]
        for button, _ in clicks:
            QTest.mouseClick(bubble, button, pos=bubble.rect().center())
        self.assertEqual([len(spy) for spy in spies], [1, 1, 1])
        bubble.move(100, 100)
        start = bubble.rect().center()
        global_start = bubble.mapToGlobal(start)
        moved = QSignalSpy(bubble.moved)
        QTest.mousePress(bubble, Qt.MouseButton.LeftButton, pos=start)
        move = QMouseEvent(QEvent.Type.MouseMove, QPointF(start + QPoint(20, 20)),
            QPointF(global_start + QPoint(20, 20)), Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(bubble, move)
        QTest.mouseRelease(bubble, Qt.MouseButton.LeftButton, pos=start)
        self.assertEqual(bubble.pos(), QPoint(120, 120))
        self.assertEqual(len(moved), 1)
        self.assertEqual([len(spy) for spy in spies], [1, 1, 1])

    def test_color_picker_native_layout_does_not_shrink_or_crop_the_shared_shell(self):
        picker = self.show(ColorPickerDialog(QColor('#F59E0B'), title='选择颜色'))
        self.assertEqual((picker.width(), picker.height()), (760, 620))
        header, footer = picker._ui_header.geometry(), picker._ui_footer.geometry()
        for scroll in picker.findChildren(QScrollArea):
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        self.assertEqual(picker._ui_header.geometry(), header)
        self.assertEqual(picker._ui_footer.geometry(), footer)
        for button in picker._ui_actions:
            self.assertTrue(picker._ui_footer.isAncestorOf(button))

    def test_color_picker_cancel_close_and_escape_discard_preview_color(self):
        for action in ('cancel', 'close', 'escape'):
            with self.subTest(action=action):
                def cancel():
                    picker = next(w for w in app.topLevelWidgets()
                                  if isinstance(w, ColorPickerDialog) and w.isVisible())
                    picker.setCurrentColor(QColor('#10B981'))
                    if action == 'cancel':
                        picker._cancel_button.click()
                    elif action == 'close':
                        picker._ui_header.findChild(type(picker._ok_button)).click()
                    else:
                        QTest.keyClick(picker, Qt.Key.Key_Escape)

                QTimer.singleShot(0, cancel)
                self.assertFalse(ColorPickerDialog.getColor(QColor('#F59E0B')).isValid())

    def test_direction_slider_handles_fit_inside_controls_at_all_positions(self):
        from views.gp_wheel_editor_dialog import GpWheelEditorDialog, _DefaultMarkedSlider
        dialog = self.show(GpWheelEditorDialog(self.item(GamepadWheelData())))
        for mode in (0, 1):
            dialog._select_mode_tab(mode)
            app.processEvents()
            for slider in dialog.findChildren(_DefaultMarkedSlider):
                for value in (slider.minimum(), slider._default, slider.maximum()):
                    slider.setValue(value)
                    option = QStyleOptionSlider()
                    slider.initStyleOption(option)
                    handle = slider.style().subControlRect(QStyle.ComplexControl.CC_Slider,
                             option, QStyle.SubControl.SC_SliderHandle, slider)
                    self.assertTrue(slider.rect().contains(handle), (mode, value, handle))
                    self.assertGreaterEqual(slider.height() - 1 - handle.bottom(), 2)

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
