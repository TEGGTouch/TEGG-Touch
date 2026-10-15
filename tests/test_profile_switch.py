"""Runtime profile switching with physical input, drivers and local data isolated."""

from contextlib import ExitStack
from copy import deepcopy
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QComboBox

from core import config_manager as config
from core import button_theme
from core.i18n import load_locale
from core.profile_switch import normalize_actions, select_destination, TRIGGER_FIELDS
from core.cursor_input import CursorInput
from engine.hover_state_machine import HoverState
from engine.run_controller import RunController, VK_LBUTTON, VK_RBUTTON, VK_MBUTTON, VK_XBUTTON1, VK_XBUTTON2
from engine.ui_pointer import UiPointerController
from models.button_model import ButtonData
from scene.touch_button_item import TouchButtonItem
from views.edit_toolbar import EditToolbar
from views.overlay_window import OverlayWindow
from views.profile_switch_dialog import ProfileSwitchDialog
from views.hotkey_settings_dialog import HotkeySettingsDialog

app = QApplication.instance() or QApplication([])


class DestinationTests(unittest.TestCase):
    def test_fixed_and_cycle_are_independent_and_follow_current_profile(self):
        fixed = {'mode': 'fixed', 'profiles': ['A']}
        cycle = {'mode': 'cycle', 'profiles': ['A', 'B', 'C']}
        for current in ('A', 'B', 'C', 'D'):
            self.assertEqual(select_destination(fixed, current, ['A', 'B', 'C']), 'A')
        self.assertEqual([select_destination(cycle, p, ['A', 'B', 'C']) for p in ('D', 'A', 'B', 'C')], ['A', 'B', 'C', 'A'])
        self.assertEqual(select_destination(cycle, 'A', ['A', 'C']), 'C')
        self.assertIsNone(select_destination(fixed, 'B', ['B']))

    def test_switch_data_roundtrip_and_old_buttons_remain_compatible(self):
        data = ButtonData(btn_type='profile_switch', profile_actions={
            'hover': {'mode': 'cycle', 'profiles': ['A', 'A', 'B']},
            'rclick': {'mode': 'fixed', 'profiles': ['C', 'A']}})
        restored = ButtonData.from_dict(data.to_dict())
        self.assertEqual(restored.switch_id, data.switch_id)
        self.assertEqual(restored.profile_actions['hover']['profiles'], ['A', 'B'])
        self.assertEqual(restored.profile_actions['rclick']['profiles'], ['C'])
        self.assertEqual(restored.rclick, 'profile-switch:rclick')
        self.assertNotIn('switch_id', ButtonData().to_dict())
        self.assertEqual(normalize_actions(None), {})


class RuntimeSwitchTests(unittest.TestCase):
    def setUp(self):
        load_locale('zh-CN')
        self.stack = ExitStack()
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.switch_file = os.path.join(self.directory, 'settings', 'profile_switches.json')
        self.stack.enter_context(patch.multiple(config,
            PROFILES_DIR=os.path.join(self.directory, 'profiles'),
            HOTKEYS_FILE=os.path.join(self.directory, 'hotkeys.json'),
            CONFIG_FILE=os.path.join(self.directory, 'config.json')))
        self.stack.enter_context(patch('core.profile_switch.SWITCHES_FILE', self.switch_file))
        for name in ('views.overlay_window.release_all_keys',
                     'views.overlay_window.install_wheel_hook',
                     'views.overlay_window.uninstall_wheel_hook',
                     'views.overlay_window.QApplication.quit',
                     'engine.run_controller.keyboard_hook.uninstall_hook',
                     'engine.run_controller.keyboard_hook.poll_events',
                     'engine.run_controller.poll_wheel_events',
                     'engine.gamepad_engine.GamepadEngine.shutdown_singleton',
                     'engine.run_controller.RunController._start_key_remap',
                     'engine.run_controller.RunController._start_voice',
                     'engine.run_controller.RunController._stop_voice'):
            mocked = self.stack.enter_context(patch(name))
            if name.endswith(('poll_events', 'poll_wheel_events')):
                mocked.return_value = []
        self.release = self.stack.enter_context(patch('engine.run_controller.release_all_keys'))
        self.smart = self.stack.enter_context(patch.object(RunController, '_smart_trigger'))
        self.stack.enter_context(patch.object(CursorInput, 'start'))
        self.stack.enter_context(patch.object(CursorInput, 'poll', return_value=False))
        self.stack.enter_context(patch.object(UiPointerController, 'read_buttons',
                                             return_value=Qt.MouseButton.NoButton))
        self.buttons_down = set()
        self.stack.enter_context(patch('engine.run_controller.user32.GetAsyncKeyState',
                                       side_effect=lambda key: 0x8000 if key in self.buttons_down else 0))
        config.init_profiles()
        for name, key in [('A', 'a'), ('B', 'b'), ('C', 'c')]:
            config.create_profile(name, from_template=False)
            config.save_profile(name, geometry='1200x800+0+0', transparency=.75,
                                buttons=[ButtonData(x=300, y=200, name=name, hover=key,
                                                    hover_delay=0).to_dict()],
                                key_remaps=[{'src': 'q', 'dst': key, 'mode': 'hold'}])
        config.set_active_profile('A')
        self.window = OverlayWindow()
        self.window._pointer_controller.timer.stop()
        self.window.show()
        app.processEvents()
        self.window._on_add_profile_switch()
        self.switch = next(it for it in self.window._scene.button_items if it.data.btn_type == 'profile_switch')
        self.switch.data.profile_actions = {key: {'mode': 'cycle', 'profiles': ['A', 'B', 'C']} for key in TRIGGER_FIELDS}
        self.switch.data.hover_delay = 0
        self.switch.data.__post_init__()
        self.switch._hover_sm.update_config('trigger', 0, 0)
        self.window._scene.save_config()
        self.window.to_run()
        self.controller = self.window._run_controller
        self.controller._timer.stop()
        self.cursor = self.stack.enter_context(patch.object(self.controller, '_get_cursor_item'))
        self.hover_on(self.switch)

    def tearDown(self):
        self.window.close()
        app.removeEventFilter(self.window._pointer_controller)
        app.processEvents()
        self.stack.close()

    def hover_on(self, item):
        if item is None:
            self.cursor.return_value = (None, None, -10000, -10000)
        else:
            point = item.sceneBoundingRect().center()
            screen = self.window.mapToGlobal(self.window.mapFromScene(point))
            self.cursor.return_value = (item, point, screen.x(), screen.y())

    def refresh_switch(self):
        self.switch = next(it for it in self.window._scene.button_items if it.data.btn_type == 'profile_switch')
        self.hover_on(self.switch)

    def test_hover_cycles_once_and_rearms_only_after_leaving_new_layout(self):
        self.controller._timer.start()
        timer_id = self.controller._timer.timerId()
        self.controller._poll_hover_and_click()
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'B')
        self.assertEqual(self.window._current_mode, 'run')
        self.assertEqual(self.controller._timer.timerId(), timer_id)
        self.assertTrue(self.controller._active)
        self.refresh_switch()
        for _ in range(8):
            self.controller._poll_hover_and_click()
            app.processEvents()
        self.assertEqual(self.window._profile_name, 'B')
        self.assertEqual(self.switch._hover_sm.state, HoverState.IDLE)
        self.hover_on(None)
        self.controller._poll_hover_and_click()
        self.hover_on(self.switch)
        self.controller._poll_hover_and_click()
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'C')
        self.release.assert_called()

    def test_each_click_wheel_and_side_key_switches_once_and_never_injects_a_marker(self):
        self.switch.data.profile_actions.pop('hover')
        self.switch.data.__post_init__()
        self.window._scene.save_config()
        self.buttons_down.add(VK_RBUTTON)
        self.controller._poll_hover_and_click()
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'B')
        self.refresh_switch()
        for _ in range(5):
            self.controller._poll_hover_and_click()
            app.processEvents()
        self.assertEqual(self.window._profile_name, 'B')
        self.buttons_down.clear()
        self.controller._poll_hover_and_click()
        self.switch.on_wheel('up')
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'C')
        self.refresh_switch()
        self.stack.enter_context(patch.object(self.window._scene, 'itemAt', return_value=self.switch))
        self.buttons_down.add(VK_XBUTTON1)
        self.controller._poll_hardware_buttons()
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'A')
        self.refresh_switch()
        self.buttons_down.clear()
        self.controller._poll_hardware_buttons()
        self.assertEqual(self.window._profile_name, 'A')
        self.assertFalse(any(str(call.args[0]).startswith('profile-switch:') for call in self.smart.call_args_list))

    def test_pending_request_is_cancelled_when_stopped(self):
        self.controller._queue_profile_switch(self.switch.data, 'hover')
        self.controller.stop()
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'A')

    def test_empty_hover_has_no_charge_or_visual_feedback_and_click_still_switches(self):
        self.switch.data.profile_actions.pop('hover')
        self.switch.data.__post_init__()
        self.switch._hover_sm.update_config('trigger', 100, 0, 0)
        self.window._scene.save_config()
        activated = QSignalSpy(self.switch.hoverActivated)
        for _ in range(3):
            self.hover_on(None)
            self.controller._poll_hover_and_click()
            self.hover_on(self.switch)
            self.controller._poll_hover_and_click()
            QTest.qWait(120)
            self.controller._poll_hover_and_click()
            self.assertEqual(self.switch._hover_sm.state, HoverState.IDLE)
            self.assertEqual(self.switch._visual_state, 'normal')
            self.assertEqual(self.switch._charge_progress, 0)
        self.assertEqual(len(activated), 0)
        self.buttons_down.add(VK_LBUTTON)
        self.controller._poll_hover_and_click()
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'B')
        self.refresh_switch()
        self.controller._poll_hover_and_click()
        self.assertEqual(self.switch._visual_state, 'normal')

    def test_switch_color_uses_current_profile_appearance_and_survives_save(self):
        self.window._button_colors = {'profile_switch': '#EAB308'}
        self.window._persist_appearance_to_profile()
        self.window._apply_appearance_to_items()
        self.assertEqual(button_theme.family('profile_switch')['border'], '#EAB308')
        self.assertEqual(config.load_profile('A')['button_colors']['profile_switch'], '#EAB308')
        destination = config.load_profile('B')
        destination['button_colors'] = {'profile_switch': '#06B6D4'}
        config.save_profile('B', destination)
        self.window._on_quick_profile_switch(self.switch.data, 'hover')
        self.assertEqual(button_theme.family('profile_switch')['border'], '#06B6D4')

    def test_all_mouse_trigger_paths_switch_the_running_profile(self):
        self.switch.data.profile_actions.pop('hover')
        self.switch.data.__post_init__()
        self.window._scene.save_config()
        for field, vk in [('lclick', VK_LBUTTON), ('mclick', VK_MBUTTON),
                           ('rclick', VK_RBUTTON), ('xbutton1', VK_XBUTTON1),
                           ('xbutton2', VK_XBUTTON2), ('wheelup', None), ('wheeldown', None)]:
            with self.subTest(trigger=field):
                before = self.window._profile_name
                expected = {'A': 'B', 'B': 'C', 'C': 'A'}[before]
                if vk:
                    self.buttons_down.add(vk)
                if field in ('wheelup', 'wheeldown'):
                    self.switch.on_wheel('up' if field == 'wheelup' else 'down')
                elif field.startswith('xbutton'):
                    with patch.object(self.window._scene, 'itemAt', return_value=self.switch):
                        self.controller._poll_hardware_buttons()
                else:
                    self.controller._poll_hover_and_click()
                app.processEvents()
                self.assertEqual(self.window._profile_name, expected)
                self.refresh_switch()
                self.buttons_down.clear()
                self.controller._poll_hover_and_click()
                self.controller._poll_hardware_buttons()

    def test_gamepad_configuration_refreshes_while_running_controls_stay_active(self):
        destination = config.load_profile('B')
        destination['buttons'][0]['hover'] = 'gp:A'
        config.save_profile('B', destination)
        gamepad = Mock()
        self.controller._auto_center = True
        with patch('engine.run_controller.GamepadEngine.get', return_value=gamepad):
            self.window._on_quick_profile_switch(self.switch.data, 'hover')
        self.assertTrue(self.controller._gp_enabled)
        self.assertTrue(self.controller._auto_center)
        self.assertTrue(self.controller._active)
        self.refresh_switch()
        with patch('engine.run_controller.GamepadEngine.get', return_value=gamepad):
            self.window._on_quick_profile_switch(self.switch.data, 'hover')
        self.assertFalse(self.controller._gp_enabled)
        gamepad.release_all.assert_called()

    def test_shared_buttons_persist_separately_and_copy_gets_a_new_id(self):
        with open(self.switch_file, encoding='utf-8') as source:
            saved = json.load(source)
        self.assertEqual(saved[0]['switch_id'], self.switch.data.switch_id)
        with open(config._profile_path('A'), encoding='utf-8') as source:
            profile = json.load(source)
        self.assertTrue(all(b['type'] != 'profile_switch' for b in profile['buttons']))
        copied = self.window._scene.copy_button(self.switch)
        self.assertNotEqual(copied.data.switch_id, self.switch.data.switch_id)

    def test_old_hover_and_click_are_released_and_destination_uses_new_bindings(self):
        normal = next(it for it in self.window._scene.button_items if it.data.btn_type == 'normal')
        normal._hover_sm.enter()
        self.controller._holding_lclick = (normal, 'space')
        self.smart.reset_mock()
        self.window._on_quick_profile_switch(self.switch.data, 'hover')
        self.assertEqual(self.window._profile_name, 'B')
        calls = [call.args for call in self.smart.call_args_list]
        self.assertIn(('a', 'r'), calls)
        self.assertIn(('space', 'r'), calls)
        self.assertIsNone(self.controller._holding_lclick)
        self.assertEqual(self.window._scene.get_config()['key_remaps'][0]['dst'], 'b')

    def test_invalid_destination_preserves_current_layout(self):
        with open(config._profile_path('B'), 'w', encoding='utf-8') as destination:
            destination.write('{broken')
        with self.assertLogs('views.overlay_window', level='ERROR'):
            self.window._on_quick_profile_switch(self.switch.data, 'hover')
        self.assertEqual(self.window._profile_name, 'A')
        self.assertTrue(self.controller._active)
        self.assertFalse(self.controller._profile_transition)

    def test_build_failure_rolls_back_and_can_switch_again(self):
        original = self.window._scene.load_from_config
        def load(cfg):
            if cfg['buttons'][0]['name'] == 'B':
                raise ValueError('simulate bad scene geometry')
            return original(cfg)
        with patch.object(self.window._scene, 'load_from_config', side_effect=load), \
                self.assertLogs('views.overlay_window', level='ERROR'):
            self.window._on_quick_profile_switch(self.switch.data, 'hover')
        self.assertEqual(self.window._profile_name, 'A')
        self.assertEqual(config.get_active_profile_name(), 'A')
        self.assertTrue(self.controller._active)
        self.assertFalse(self.controller._profile_transition)
        self.refresh_switch()
        self.window._on_quick_profile_switch(self.switch.data, 'hover')
        self.assertEqual(self.window._profile_name, 'B')

    def test_hover_delay_can_be_cancelled_and_fixed_self_does_not_cycle(self):
        self.switch.data.profile_actions['hover'] = {'mode': 'fixed', 'profiles': ['A']}
        self.switch._hover_sm.update_config('trigger', 100, 0, 0)
        self.controller._poll_hover_and_click()
        QTest.qWait(40)
        self.hover_on(None)
        self.controller._poll_hover_and_click()
        QTest.qWait(120)
        self.assertEqual(self.window._profile_name, 'A')
        self.hover_on(self.switch)
        self.controller._poll_hover_and_click()
        QTest.qWait(150)
        app.processEvents()
        self.assertEqual(self.window._profile_name, 'A')

    def test_delayed_old_macro_does_not_resume_in_destination_profile(self):
        entered = threading.Event()
        resume = threading.Event()
        def pause(_):
            entered.set()
            resume.wait(2)
        with patch('engine.run_controller._time.sleep', side_effect=pause):
            self.controller._execute_macro({'steps': [
                {'type': 'delay', 'ms': 100}, {'type': 'key', 'key': 'w', 'action': 'press'}]})
            self.assertTrue(entered.wait(1))
            self.window._on_quick_profile_switch(self.switch.data, 'hover')
            resume.set()
            QTest.qWait(50)
        self.assertEqual(self.window._profile_name, 'B')
        self.assertNotIn(('w', 'p'), [call.args for call in self.smart.call_args_list])

    def test_editor_keeps_independent_fixed_and_cycle_settings(self):
        dialog = ProfileSwitchDialog(self.switch, profiles=['A', 'B', 'C'])
        try:
            dialog._mode_buttons['lclick']['fixed'].click()
            dialog._profile_buttons['C'].click()
            dialog._mode_buttons['rclick']['cycle'].click()
            dialog._fields['rclick'].set_profiles([])
            dialog._profile_buttons['B'].click()
            dialog._profile_buttons['A'].click()
            dialog._activate_field('hover')
            dialog._delay.setValue(350)
            saved = QSignalSpy(dialog.saved)
            dialog._save_btn.click()
            self.assertEqual(len(saved), 1)
            self.assertEqual(self.switch.data.profile_actions['lclick'], {'mode': 'fixed', 'profiles': ['C']})
            self.assertEqual(self.switch.data.profile_actions['rclick'], {'mode': 'cycle', 'profiles': ['B', 'A']})
            self.assertEqual(self.switch.data.hover_delay, 350)
        finally:
            dialog.close()

    def test_toolbar_entry_matches_add_button_width_and_sliders_use_two_rows(self):
        toolbar = self.window._edit_toolbar
        self.assertEqual(toolbar._switch_btn.width(), toolbar._add_kb_btn.width())
        self.assertGreater(toolbar._switch_btn.x(), toolbar._profile_btn.x())
        self.assertLess(toolbar._val_lbl.mapTo(toolbar, QPoint()).y(), toolbar._slider.mapTo(toolbar, QPoint()).y())


class ProfileEditorTests(unittest.TestCase):
    def setUp(self):
        load_locale('zh-CN')
        self.size_patch = patch('views.ui_components.dialog_size', side_effect=lambda dialog, preferred: preferred)
        self.size_patch.start()
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
        app.processEvents()
        self.size_patch.stop()

    def show_editor(self, actions=None, profiles=None):
        item = TouchButtonItem(ButtonData(btn_type='profile_switch', profile_actions=actions or {}))
        dialog = ProfileSwitchDialog(item, profiles=profiles or ['A', 'B', 'C'])
        self.dialogs.append(dialog)
        dialog.show()
        app.processEvents()
        return item, dialog

    def pick_field(self, dialog, key):
        field = dialog._fields[key]
        dialog._left_scroll.ensureWidgetVisible(field)
        app.processEvents()
        QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=QPoint(field.width() - 4, field.height() // 2))
        self.assertEqual(dialog._current_trigger, key)

    def pick_profile(self, dialog, name):
        button = dialog._profile_buttons[name]
        dialog._right_scroll.ensureWidgetVisible(button)
        app.processEvents()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    def test_all_rows_keep_independent_click_wheel_and_cycle_mappings_after_reopen(self):
        item, dialog = self.show_editor()
        self.assertEqual(set(dialog._fields), set(TRIGGER_FIELDS))
        self.assertFalse(dialog.findChildren(QComboBox))
        self.pick_field(dialog, 'lclick')
        self.pick_profile(dialog, 'A')
        self.pick_field(dialog, 'wheelup')
        self.pick_profile(dialog, 'B')
        dialog._mode_buttons['rclick']['cycle'].click()
        self.pick_profile(dialog, 'C')
        self.pick_profile(dialog, 'A')
        self.pick_profile(dialog, 'C')  # Duplicate candidates do not duplicate cycle entries.
        self.assertEqual(dialog._fields['lclick'].profiles, ['A'])
        self.assertEqual(dialog._fields['wheelup'].profiles, ['B'])
        saved = QSignalSpy(dialog.saved)
        dialog._save_btn.click()
        self.assertEqual(len(saved), 1)
        expected = {'lclick': {'mode': 'fixed', 'profiles': ['A']},
                    'wheelup': {'mode': 'fixed', 'profiles': ['B']},
                    'rclick': {'mode': 'cycle', 'profiles': ['C', 'A']}}
        self.assertEqual(item.data.profile_actions, expected)
        _, reopened = self.show_editor(actions=ButtonData.from_dict(item.data.to_dict()).profile_actions)
        for key, action in expected.items():
            self.assertEqual(reopened._fields[key].profiles, action['profiles'])
            self.assertEqual(reopened._mode_controls[key]._selected, action['mode'])

    def test_fixed_choice_replaces_one_target_without_changing_other_rows(self):
        _, dialog = self.show_editor(actions={'hover': {'mode': 'cycle', 'profiles': ['C', 'A']}})
        self.pick_field(dialog, 'lclick')
        self.pick_profile(dialog, 'A')
        self.pick_profile(dialog, 'B')
        self.assertEqual(dialog._fields['lclick'].profiles, ['B'])
        self.assertEqual(dialog._fields['hover'].profiles, ['C', 'A'])
        self.assertEqual([name for name, button in dialog._profile_buttons.items() if button._selected], ['B'])

    def test_hover_delay_is_enabled_only_when_hover_mapping_is_set(self):
        _, dialog = self.show_editor()
        self.assertFalse(dialog._delay.isEnabled())
        self.pick_profile(dialog, 'A')
        self.assertTrue(dialog._delay.isEnabled())
        dialog._delay.setValue(450)
        self.pick_field(dialog, 'hover')
        QTest.keyClick(dialog._fields['hover'], Qt.Key.Key_Backspace)
        self.assertFalse(dialog._delay.isEnabled())
        self.pick_profile(dialog, 'B')
        self.assertTrue(dialog._delay.isEnabled())
        self.assertEqual(dialog._delay.value(), 450)

    def test_cycle_order_buttons_and_chip_removal_update_only_selected_field(self):
        item, dialog = self.show_editor(actions={
            'rclick': {'mode': 'cycle', 'profiles': ['A', 'B', 'C']},
            'wheelup': {'mode': 'fixed', 'profiles': ['B']}})
        self.pick_field(dialog, 'rclick')
        self.assertFalse(dialog._cycle_rows[0]['up'].isEnabled())
        self.assertFalse(dialog._cycle_rows[-1]['down'].isEnabled())
        dialog._cycle_rows[1]['up'].click()
        self.assertEqual(dialog._fields['rclick'].profiles, ['B', 'A', 'C'])
        dialog._cycle_rows[1]['down'].click()
        self.assertEqual(dialog._fields['rclick'].profiles, ['B', 'C', 'A'])
        dialog._cycle_rows[1]['remove'].click()
        app.processEvents()
        field = dialog._fields['rclick']
        close = field._layout_chips()[0][0][3]
        QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=close.center())
        self.assertEqual(field.profiles, ['A'])
        QTest.keyClick(field, Qt.Key.Key_Backspace)
        dialog._save_btn.click()
        self.assertEqual(item.data.profile_actions, {'wheelup': {'mode': 'fixed', 'profiles': ['B']}})

    def test_cancel_keeps_original_button_and_hover_configuration(self):
        item, dialog = self.show_editor(actions={'hover': {'mode': 'cycle', 'profiles': ['A', 'B']}})
        before = deepcopy(item.data.to_dict())
        self.pick_profile(dialog, 'C')
        dialog._name.setText('Unsaved')
        dialog._delay.setValue(700)
        dialog.reject()
        self.assertEqual(item.data.to_dict(), before)

    def test_missing_profile_can_be_removed_before_saving(self):
        item, dialog = self.show_editor(actions={'rclick': {'mode': 'fixed', 'profiles': ['Deleted']}})
        saved = QSignalSpy(dialog.saved)
        dialog._save_btn.click()
        self.assertEqual(len(saved), 0)
        self.assertEqual(dialog._current_trigger, 'rclick')
        self.assertTrue(dialog._error.isVisible())
        self.pick_field(dialog, 'rclick')
        QTest.keyClick(dialog._fields['rclick'], Qt.Key.Key_Delete)
        dialog._save_btn.click()
        self.assertEqual(len(saved), 1)
        self.assertEqual(item.data.profile_actions, {})

    def test_full_profile_names_wrap_without_changing_shell_or_other_scroll(self):
        names = ['Work+Game', 'A very long profile name ' * 5, 'B', 'C']
        profiles = names + [f'Profile {index}' for index in range(30)]
        item, dialog = self.show_editor(actions={'rclick': {'mode': 'cycle', 'profiles': names}}, profiles=profiles)
        self.pick_field(dialog, 'rclick')
        field = dialog._fields['rclick']
        self.assertGreater(field.height(), 42)
        chips, _ = field._layout_chips()
        self.assertTrue(all(rect.right() <= field.width() - 6 for _, _, rect, _ in chips))
        self.assertEqual(dialog._profile_buttons[names[1]].toolTip(), names[1])
        header, footer, right_width = dialog._ui_header.geometry(), dialog._ui_footer.geometry(), dialog._right_pane.width()
        other = dialog._right_scroll.verticalScrollBar().value()
        dialog._left_scroll.verticalScrollBar().setValue(dialog._left_scroll.verticalScrollBar().maximum())
        app.processEvents()
        self.assertEqual(dialog._right_scroll.verticalScrollBar().value(), other)
        self.assertEqual(dialog._ui_header.geometry(), header)
        self.assertEqual(dialog._ui_footer.geometry(), footer)
        self.assertEqual(dialog._right_pane.width(), right_width)
        self.assertEqual(dialog._left_scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(dialog._right_scroll.horizontalScrollBar().maximum(), 0)
        dialog._save_btn.click()
        self.assertEqual(item.data.profile_actions['rclick']['profiles'], names)


class SwitchColorTests(unittest.TestCase):
    def setUp(self):
        load_locale('zh-CN')
        self.theme_patch = patch.dict(button_theme._current)
        self.theme_patch.start()

    def tearDown(self):
        self.theme_patch.stop()

    def fill_pixel(self, item):
        canvas = QImage(100, 100, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        item.paint(painter, None)
        painter.end()
        return canvas.pixelColor(20, 20).name().upper()

    def test_switch_button_renders_default_and_custom_family_with_existing_feedback(self):
        item = TouchButtonItem(ButtonData(btn_type='profile_switch'))
        button_theme.set_button_colors(None)
        self.assertEqual(self.fill_pixel(item), '#4C1D95')
        button_theme.set_button_colors({'profile_switch': '#EAB308'})
        self.assertEqual(self.fill_pixel(item), button_theme.derive_family('profile_switch', '#EAB308')['fill'])
        self.assertEqual(button_theme.keyboard()['border'], '#555555')
        item.set_visual_state('active_left')
        self.assertEqual(self.fill_pixel(item), '#7C3AED')
        button_theme.set_button_colors({'profile_switch': 'invalid'})
        self.assertEqual(button_theme.family('profile_switch')['border'], '#A78BFA')

    def test_settings_color_picker_reset_and_save_preserve_other_groups(self):
        existing = {'button_colors': {'keyboard': '#ABCDEF', 'profile_switch': '#06B6D4'}}
        with patch('views.hotkey_settings_dialog.load_hotkeys', side_effect=lambda: deepcopy(existing)), \
             patch('views.hotkey_settings_dialog.save_hotkeys') as save, \
             patch('views.ui_components.dialog_size', side_effect=lambda dialog, preferred: preferred):
            dialog = HotkeySettingsDialog()
            try:
                self.assertIn('profile_switch', dialog._bc_widgets)
                self.assertEqual(dialog._button_colors_buf['profile_switch'], '#06B6D4')
                button = dialog._bc_widgets['profile_switch']['btn']
                with patch('views.hotkey_settings_dialog.ColorPickerDialog.getColor', return_value=QColor('#EAB308')):
                    button.click()
                self.assertEqual(dialog._button_colors_buf['profile_switch'], '#EAB308')
                dialog._on_bc_reset('profile_switch')
                self.assertEqual(dialog._button_colors_buf['profile_switch'], '#A78BFA')
                with patch('views.hotkey_settings_dialog.ColorPickerDialog.getColor', return_value=QColor('#F97316')):
                    button.click()
                dialog._on_save()
                colors = save.call_args.args[0]['button_colors']
                self.assertEqual(colors['profile_switch'], '#F97316')
                self.assertEqual(colors['keyboard'], '#ABCDEF')
                self.assertEqual(colors['gamepad'], button_theme.DEFAULT_BUTTON_COLORS['gamepad'])
            finally:
                dialog.close()
                app.processEvents()


if __name__ == '__main__':
    unittest.main()
