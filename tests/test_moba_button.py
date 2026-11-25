"""MOBA cast buttons: hover taps the cast key, other buttons lock until a click/Esc/timeout."""

from contextlib import ExitStack
import os
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core import config_manager as config
from core import button_theme
from core.i18n import load_locale, t
from core.cursor_input import CursorInput
from engine.hover_state_machine import HoverState
from engine.run_controller import RunController, VK_LBUTTON, VK_RBUTTON, VK_ESCAPE
from engine.ui_pointer import UiPointerController
from models.button_model import ButtonData
from models.wheel_model import WheelSectorData
from scene.touch_button_item import TouchButtonItem
from scene.tooltip_item import build_edit_tooltip
from views.button_editor_dialog import ButtonEditorDialog
from views.overlay_window import OverlayWindow

app = QApplication.instance() or QApplication([])


class MobaDataTests(unittest.TestCase):
    def test_roundtrip_clamps_and_frees_mouse_buttons(self):
        data = ButtonData(btn_type='moba', hover='q', lclick='e', rclick='r', wheelup='1',
                          hover_mode='toggle', hover_release_delay=300,
                          moba_timeout=99999, moba_dim=-5)
        self.assertEqual((data.lclick, data.rclick, data.wheelup), ('', '', ''))
        self.assertEqual((data.hover_mode, data.hover_release_delay), ('trigger', 0))
        self.assertEqual((data.moba_timeout, data.moba_dim), (30000, 0))
        restored = ButtonData.from_dict(data.to_dict())
        self.assertEqual((restored.btn_type, restored.hover, restored.moba_timeout),
                         ('moba', 'q', 30000))

    def test_regular_buttons_do_not_store_moba_fields(self):
        stored = ButtonData(hover='w').to_dict()
        self.assertNotIn('moba_timeout', stored)
        self.assertNotIn('moba_dim', stored)

    def test_theme_tooltip_and_paint(self):
        load_locale('zh-CN')
        self.assertEqual(button_theme.family('moba')['border'], '#14B8A6')
        data = ButtonData(btn_type='moba', name='Q技能', hover='q')
        self.assertIn('q', build_edit_tooltip(data))
        self.assertIn(t('moba.tooltip_hint'), build_edit_tooltip(data))
        from PyQt6.QtGui import QImage, QPainter
        image = QImage(100, 100, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        TouchButtonItem(data).paint(painter, None)
        painter.end()


class MobaRuntimeTests(unittest.TestCase):
    def setUp(self):
        load_locale('zh-CN')
        self.stack = ExitStack()
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.multiple(config,
            PROFILES_DIR=os.path.join(self.directory, 'profiles'),
            HOTKEYS_FILE=os.path.join(self.directory, 'hotkeys.json'),
            CONFIG_FILE=os.path.join(self.directory, 'config.json')))
        self.stack.enter_context(patch('core.profile_switch.SWITCHES_FILE',
                                       os.path.join(self.directory, 'switches.json')))
        for name in ('views.overlay_window.release_all_keys',
                     'views.overlay_window.install_wheel_hook',
                     'views.overlay_window.uninstall_wheel_hook',
                     'views.overlay_window.QApplication.quit',
                     'engine.run_controller.keyboard_hook.uninstall_hook',
                     'engine.run_controller.keyboard_hook.poll_events',
                     'engine.run_controller.poll_wheel_events',
                     'engine.run_controller.release_all_keys',
                     'engine.run_controller.RunController._check_hotkeys',
                     'engine.run_controller.RunController._start_key_remap',
                     'engine.run_controller.RunController._start_voice',
                     'engine.run_controller.RunController._stop_voice'):
            mocked = self.stack.enter_context(patch(name))
            if name.endswith(('poll_events', 'poll_wheel_events')):
                mocked.return_value = []
        self.smart = self.stack.enter_context(patch.object(RunController, '_smart_trigger'))
        self.stack.enter_context(patch.object(CursorInput, 'start'))
        self.stack.enter_context(patch.object(CursorInput, 'poll', return_value=False))
        self.stack.enter_context(patch.object(UiPointerController, 'read_buttons',
                                             return_value=Qt.MouseButton.NoButton))
        self.down = set()
        self.stack.enter_context(patch('engine.run_controller.user32.GetAsyncKeyState',
                                       side_effect=lambda key: 0x8000 if key in self.down else 0))
        self.now = [1000.0]
        self.stack.enter_context(patch('engine.run_controller._time.monotonic',
                                       side_effect=lambda: self.now[0]))
        config.init_profiles()
        config.create_profile('A', from_template=False)
        config.save_profile('A', geometry='1200x800+0+0', transparency=.8, buttons=[
            ButtonData(x=-300, y=0, name='Q', btn_type='moba', hover='q', hover_delay=0,
                       moba_timeout=5000, moba_dim=25).to_dict(),
            ButtonData(x=200, y=0, name='W', hover='w', hover_delay=0).to_dict()])
        config.set_active_profile('A')
        self.window = OverlayWindow()
        self.window._pointer_controller.timer.stop()
        self.window.show()
        app.processEvents()
        self.window.to_run()
        self.controller = self.window._run_controller
        self.controller._timer.stop()
        self.cursor = self.stack.enter_context(patch.object(self.controller, '_get_cursor_item'))
        items = {it.data.name: it for it in self.window._scene.button_items}
        self.moba, self.other = items['Q'], items['W']
        self.on_ui = []
        self.controller.cursor_on_ui.connect(self.on_ui.append)

    def tearDown(self):
        self.window.close()
        app.removeEventFilter(self.window._pointer_controller)
        app.processEvents()
        self.stack.close()

    def hover(self, item):
        if item is None:
            self.cursor.return_value = (None, None, -10000, -10000)
        else:
            point = item.sceneBoundingRect().center()
            screen = self.window.mapToGlobal(self.window.mapFromScene(point))
            self.cursor.return_value = (item, point, screen.x(), screen.y())
        self.controller._tick()
        app.processEvents()

    def keys_sent(self):
        return [call.args for call in self.smart.call_args_list]

    def start_aiming(self):
        self.hover(self.moba)
        self.assertEqual(self.keys_sent(), [('q', 'click')])
        self.assertIs(self.window._moba_lock_item, self.moba)
        self.smart.reset_mock()

    def test_hover_taps_key_dims_others_and_left_click_releases(self):
        self.start_aiming()
        base = self.window._current_opacity
        self.assertAlmostEqual(self.other.opacity(), base * 0.25)
        self.assertAlmostEqual(self.moba.opacity(), base)
        # Aiming across another button never triggers it and keeps clicks with the game.
        for _ in range(3):
            self.hover(self.other)
        self.assertEqual(self.keys_sent(), [])
        self.assertEqual(self.other._hover_sm.state, HoverState.IDLE)
        self.assertFalse(self.on_ui[-1])
        self.down.add(VK_LBUTTON)
        self.hover(self.other)
        self.assertIsNone(self.controller._moba_lock)
        self.assertIsNone(self.window._moba_lock_item)
        self.assertAlmostEqual(self.other.opacity(), base)
        # The button under the cursor after casting waits for a fresh entry.
        self.down.clear()
        for _ in range(3):
            self.hover(self.other)
        self.assertEqual(self.keys_sent(), [])
        self.hover(None)
        self.hover(self.other)
        self.assertEqual(self.keys_sent(), [('w', 'p')])

    def test_right_click_escape_and_timeout_end_aiming(self):
        for end in ('right', 'esc', 'timeout'):
            self.hover(None)
            self.down.clear()
            self.start_aiming()
            if end == 'right':
                self.down.add(VK_RBUTTON)
            elif end == 'esc':
                self.down.add(VK_ESCAPE)
            else:
                self.now[0] += 4.9
                self.hover(None)
                self.assertIsNotNone(self.controller._moba_lock)
                self.now[0] += 0.2
            self.hover(None)
            self.assertIsNone(self.controller._moba_lock, end)
            self.assertEqual(self.keys_sent(), [], end)

    def test_held_button_at_lock_does_not_end_aiming(self):
        self.down.add(VK_LBUTTON)
        self.start_aiming()
        self.hover(None)
        self.assertIsNotNone(self.controller._moba_lock)
        self.down.clear()
        self.hover(None)
        self.down.add(VK_LBUTTON)
        self.hover(None)
        self.assertIsNone(self.controller._moba_lock)

    def test_cast_on_the_button_itself_needs_leaving_before_next_cast(self):
        self.start_aiming()
        self.down.add(VK_LBUTTON)
        self.hover(self.moba)
        self.down.clear()
        for _ in range(3):
            self.hover(self.moba)
        self.assertEqual(self.keys_sent(), [])
        self.hover(None)
        self.hover(self.moba)
        self.assertEqual(self.keys_sent(), [('q', 'click')])

    def test_zero_brightness_hides_others_and_leaving_run_mode_restores(self):
        self.moba.data.moba_dim = 0
        self.start_aiming()
        self.assertEqual(self.other.opacity(), 0)
        self.window.to_edit()
        self.assertIsNone(self.controller._moba_lock)
        self.assertAlmostEqual(self.other.opacity(), self.window._current_opacity)


class MobaEditorTests(unittest.TestCase):
    def setUp(self):
        load_locale('zh-CN')

    def editor(self, data):
        from types import SimpleNamespace
        item = TouchButtonItem(data) if isinstance(data, ButtonData) else SimpleNamespace(data=data)
        dialog = ButtonEditorDialog(item)
        saved = []
        dialog.saved.connect(saved.append)
        return item, dialog, saved

    def test_convert_to_moba_saves_only_on_save(self):
        item, dialog, saved = self.editor(ButtonData(name='Q', hover='q', hover_delay=150,
                                                     lclick='e'))
        button = dialog._moba_btn
        self.assertTrue(dialog._ui_footer.isAncestorOf(button))
        self.assertEqual(dialog._ui_actions[0], button)
        self.assertEqual(button.text(), t('moba.convert'))
        button.click()
        self.assertTrue(dialog._moba_box.isVisibleTo(dialog))
        self.assertFalse(dialog._regular_box.isVisibleTo(dialog))
        self.assertEqual(button.text(), t('moba.revert'))
        self.assertEqual(dialog._ui_guidance.text(), t('moba.guidance'))
        self.assertEqual(dialog._fields['moba_key'].get_value(), 'q')
        self.assertEqual(dialog._moba_hover_delay_entry.text(), '150')
        self.assertEqual(item.data.btn_type, 'normal')  # not applied before saving
        dialog._moba_timeout_entry.setText('8')
        dialog._moba_dim_entry.setText('40')
        dialog._on_save()
        self.assertEqual(saved, [item.data])
        self.assertEqual((item.data.btn_type, item.data.hover, item.data.hover_delay),
                         ('moba', 'q', 150))
        self.assertEqual((item.data.moba_timeout, item.data.moba_dim, item.data.lclick),
                         (8000, 40, ''))

    def test_closing_without_saving_keeps_regular_button(self):
        item, dialog, saved = self.editor(ButtonData(hover='q'))
        dialog._moba_btn.click()
        dialog.reject()
        self.assertEqual((item.data.btn_type, saved), ('normal', []))

    def test_convert_back_keeps_cast_key(self):
        item, dialog, _ = self.editor(ButtonData(btn_type='moba', hover='q', hover_delay=80))
        self.assertTrue(dialog._moba_box.isVisibleTo(dialog))
        dialog._fields['moba_key'].set_value('e')
        dialog._moba_btn.click()
        self.assertEqual(dialog._fields['hover'].get_value(), 'e')
        dialog._on_save()
        self.assertEqual((item.data.btn_type, item.data.hover, item.data.hover_delay),
                         ('normal', 'e', 80))

    def test_only_keyboard_buttons_offer_conversion(self):
        from core.constants import BTN_TYPE_GP_BUTTON
        for data in (ButtonData(btn_type=BTN_TYPE_GP_BUTTON), WheelSectorData()):
            _, dialog, _ = self.editor(data)
            self.assertFalse(dialog._moba_btn.isVisibleTo(dialog))

    def test_english_buttons_fit(self):
        load_locale('en')
        try:
            _, dialog, _ = self.editor(ButtonData(hover='q'))
            button = dialog._moba_btn
            for key in ('moba.convert', 'moba.revert'):
                self.assertLessEqual(button.fontMetrics().horizontalAdvance(t(key)) + 16,
                                     button.minimumWidth())
        finally:
            load_locale('zh-CN')


if __name__ == '__main__':
    unittest.main()
