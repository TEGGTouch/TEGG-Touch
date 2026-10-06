"""Cursor capture regression tests. All injected input/OS warps are mocked.

Run: QT_QPA_PLATFORM=offscreen python -m unittest tests.test_adaptive_cursor -v
"""

import ctypes
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from PyQt6.QtCore import QPoint, QRect, QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from core.cursor_input import AdaptivePointer, CursorProbe, CursorInput, RawMouseReader, _Header, _Mouse
from core.constants import PT_ON, PT_OFF, PT_CYCLE, DEFAULT_HOTKEYS
from engine.run_controller import RunController
from engine.passthrough_manager import PassthroughManager, WS_EX_TRANSPARENT
from scene.virtual_cursor_item import VirtualCursorItem

_app = QApplication.instance() or QApplication([])
BOUNDS = QRect(0, 0, 1920, 1080)
CENTRE = (960, 540)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class DetectorTests(unittest.TestCase):
    def model(self):
        return AdaptivePointer(BOUNDS)

    def lock(self, model, visible=False, tiny_clip=False):
        for i in range(35):
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, visible, tiny_clip), [(0, 4, 0)])
        self.assertTrue(model.independent)

    def test_centre_lock_uses_physical_motion(self):
        model = self.model()
        self.lock(model)
        self.assertEqual(model.position, (1100, 540))
        for i in range(35, 70):
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, False), [(0, 0, -4)])
        self.assertEqual(model.position, (1100, 400))

    def test_repeated_small_recentres_do_not_cancel_detection(self):
        model = self.model()
        for i in range(80):
            model.advance(i * .008, CursorProbe((960 + (i % 3) * 3, 540), CENTRE, False), [(0, 4, 0)])
        self.assertTrue(model.independent)

    def test_existing_free_cursor_path_never_switches(self):
        model = self.model()
        for i in range(500):
            x = 600 + (i % 180) * 4
            model.advance(i * .008, CursorProbe((x, 540), CENTRE, False), [(0, 4, 0)])
            self.assertFalse(model.independent)
            self.assertEqual(model.position, (x, 540))

    def test_idle_and_sensor_jitter_do_not_switch(self):
        model = self.model()
        for i in range(500):
            events = [] if i < 200 else [(0, (-1) ** i, 0)]
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE), events)
        self.assertFalse(model.independent)

    def test_screen_edge_is_not_a_game_lock(self):
        for point in ((0, 540), (1919, 540), (960, 0), (960, 1079)):
            model = self.model()
            for i in range(80):
                model.advance(i * .01, CursorProbe(point, point), [(0, 4, 0)])
            self.assertFalse(model.independent, point)

    def test_short_motion_and_idle_do_not_trigger_later(self):
        model = self.model()
        for i in range(80):
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, False),
                          [(0, 10, 0)] if i < 5 else [])
        self.assertFalse(model.independent)

    def test_nearly_long_enough_motion_does_not_trigger_after_stopping(self):
        model = self.model()
        for i in range(80):
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, False),
                          [(0, 10, 0)] if i < 16 else [])
        self.assertFalse(model.independent)

    def test_absolute_reports_are_not_huge_relative_deltas(self):
        model = self.model()
        for i in range(80):
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, False), [(1, 32768, 32768)])
        self.assertFalse(model.independent)

    def test_low_os_sensitivity_near_centre_not_misdetected(self):
        model = self.model()
        for i in range(30):
            model.advance(i * .01, CursorProbe((900 + i * .5, 540), CENTRE), [(0, 10, 0)])
        self.assertAlmostEqual(model.gain, .05)
        for i in range(60):
            model.advance(.3 + i * .01, CursorProbe((950 + i * .5, 540), CENTRE), [(0, 10, 0)])
            self.assertFalse(model.independent)

    def test_windowed_game_centre_supported(self):
        model = self.model()
        for i in range(40):
            model.advance(i * .01, CursorProbe((400, 300), (400, 300), False), [(0, 4, 0)])
        self.assertTrue(model.independent)

    def test_small_clip_can_lock_away_from_centre(self):
        model = self.model()
        for i in range(25):
            model.advance(i * .01, CursorProbe((400, 300), CENTRE, True, True), [(0, 4, 0)])
        self.assertTrue(model.independent)

    def test_showing_native_menu_returns_to_system_automatically(self):
        model = self.model()
        self.lock(model)
        for i in range(35, 60):
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, True), [])
        self.assertFalse(model.independent)
        self.assertEqual(model.position, CENTRE)

    def test_custom_cursor_menu_recognised_by_free_travel(self):
        model = self.model()
        self.lock(model)
        for i in range(35, 80):
            point = (960 + (i - 34) * 4, 540)
            model.advance(i * .01, CursorProbe(point, CENTRE, False), [(0, 4, 0)])
        self.assertFalse(model.independent)
        self.assertEqual(model.position, point)

    def test_locked_idle_does_not_switch_back(self):
        model = self.model()
        self.lock(model, visible=True)
        for i in range(35, 150):
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, True), [])
        self.assertTrue(model.independent)

    def test_focus_change_immediately_releases_capture(self):
        model = self.model()
        self.lock(model)
        changed, focus = model.advance(.4, CursorProbe((300, 300), CENTRE, foreground=2), [])
        self.assertEqual((changed, focus, model.independent), (True, True, False))

    def test_our_own_recenter_cannot_trigger_capture(self):
        model = self.model()
        for i in range(100):
            if i % 10 == 0:
                model.recenter(CENTRE, i * .01)
            model.advance(i * .01, CursorProbe(CENTRE, CENTRE, False), [(0, 8, 0)])
        self.assertFalse(model.independent)

    def test_virtual_recenter_and_edges(self):
        model = self.model()
        self.lock(model)
        model.recenter((300, 400), .4)
        model.advance(.41, CursorProbe(CENTRE, CENTRE, False), [(0, -10000, 10000)])
        self.assertTrue(model.independent)
        self.assertEqual(model.position, (0, 1079))
        model.advance(.42, CursorProbe(CENTRE, CENTRE, False), [(0, 5, -5)])
        self.assertEqual(model.position, (5, 1074))

    def test_negative_screen_origin(self):
        model = AdaptivePointer(QRect(-1920, 0, 1920, 1080))
        for i in range(40):
            model.advance(i * .01, CursorProbe((-960, 540), (-960, 540), False), [(0, -4, 0)])
        self.assertTrue(model.independent)
        self.assertLess(model.position[0], -960)


class SourceTests(unittest.TestCase):
    def test_reader_coalesces_high_rate_motion(self):
        reader = RawMouseReader()
        for _ in range(8000):
            reader.feed(0, 1, -1)
        self.assertEqual(reader.drain(), [(0, 8000, -8000)])
        self.assertEqual(reader.drain(), [])
        self.assertEqual(ctypes.sizeof(_Mouse), 24)
        self.assertEqual(ctypes.sizeof(_Header), 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16)

    def test_reader_preserves_absolute_marker(self):
        reader = RawMouseReader()
        reader.feed(0, 10, 0)
        reader.feed(3, 32768, 32768)
        reader.feed(0, 2, 3)
        self.assertEqual(reader.drain(), [(3, 32768, 32768), (0, 2, 3)])

    def test_system_path_and_virtual_path_recenter(self):
        source = CursorInput()
        with patch('core.cursor_input.QCursor.pos', return_value=QPoint(230, 400)), \
             patch('core.cursor_input._user32') as api:
            self.assertEqual(source.position(), QPoint(230, 400))
            source.set_position(350, 450)
            api.SetCursorPos.assert_called_once_with(350, 450)
            api.reset_mock()
            source._model.independent = True
            source.set_position(700, 350)
            self.assertEqual(source.position(), QPoint(700, 350))
            api.SetCursorPos.assert_not_called()

    def test_start_failure_preserves_original_path(self):
        reader = Mock()
        reader.start.return_value = False
        source = CursorInput(reader_factory=lambda: reader)
        with patch('core.cursor_input.QCursor.pos', return_value=QPoint(300, 200)):
            source.start(BOUNDS)
            self.assertFalse(source.independent)
            self.assertEqual(source.position(), QPoint(300, 200))

    def test_position_reads_do_not_reconsume_raw_motion(self):
        reader = Mock(alive=True)
        reader.drain.return_value = [(0, 4, 0)]
        source = CursorInput()
        source._reader = reader
        source._model.independent = True
        source._model.position = CENTRE
        source._model._last = CursorProbe(CENTRE, CENTRE, False)
        with patch.object(source, '_probe', return_value=source._model._last):
            source.poll()
            for _ in range(20):
                self.assertEqual(source.position(), QPoint(964, 540))
        reader.drain.assert_called_once()


class IntegrationTests(unittest.TestCase):
    def test_captured_pointer_walks_with_real_round_wheel_sector(self):
        from models.wheel_model import WheelSectorData
        from scene.wheel_sector_item import WheelSectorItem
        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, 1920, 1080)
        view = QGraphicsView(scene)
        view.resize(1920, 1080)
        sector = WheelSectorItem(WheelSectorData(name='Forward', hover='w', hover_delay=20),
                                 960, 540, 40, 160, 67.5, 45)
        sector.set_mode('run')
        scene.addItem(sector)
        scene.wheel_items = [sector]
        ctrl = RunController(scene, view)
        origin = view.mapToGlobal(view.mapFromScene(960, 540))
        centre = (origin.x(), origin.y())
        ctrl.cursor_input._model = AdaptivePointer(QRect(-10000, -10000, 20000, 20000))
        sector.hoverActivated.connect(ctrl.on_hover_activated)
        sector.hoverDeactivated.connect(ctrl.on_hover_deactivated)
        for i in range(35):
            ctrl.cursor_input._model.advance(i * .01, CursorProbe(centre, centre, False), [(0, 0, -4)])
        self.assertTrue(ctrl.cursor_input.independent)
        with patch.object(ctrl, '_smart_trigger') as trigger, \
             patch('engine.run_controller.user32') as api:
            api.GetAsyncKeyState.return_value = 0
            ctrl._poll_hover_and_click()
            wait(70)
            trigger.assert_any_call('w', 'p')
            ctrl._reset_pointer_actions()
            trigger.assert_any_call('w', 'r')
        scene.clear()

    def test_captured_pointer_drives_real_hover_button(self):
        from models.button_model import ButtonData
        from scene.touch_button_item import TouchButtonItem
        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, 1920, 1080)
        view = QGraphicsView(scene)
        view.resize(1920, 1080)
        item = TouchButtonItem(ButtonData(x=1100, y=490, w=100, h=100,
                                          name='W', hover='w', hover_delay=30))
        item.set_mode('run')
        scene.addItem(item)
        ctrl = RunController(scene, view)
        anchor = view.mapToGlobal(view.mapFromScene(960, 540))
        centre = (anchor.x(), anchor.y())
        ctrl.cursor_input._model = AdaptivePointer(QRect(-10000, -10000, 20000, 20000))
        for i in range(48):
            ctrl.cursor_input._model.advance(i * .01, CursorProbe(centre, centre, False), [(0, 4, 0)])
        self.assertTrue(ctrl.cursor_input.independent)
        item.hoverActivated.connect(ctrl.on_hover_activated)
        item.hoverDeactivated.connect(ctrl.on_hover_deactivated)
        with patch.object(ctrl, '_smart_trigger') as trigger, \
             patch('engine.run_controller.user32') as api:
            api.GetAsyncKeyState.return_value = 0
            ctrl._poll_hover_and_click()
            wait(100)
            trigger.assert_any_call('w', 'p')
            ctrl._reset_pointer_actions()
            trigger.assert_any_call('w', 'r')
        scene.clear()

    def test_wasd_stick_uses_virtual_recenter_and_motion(self):
        from models.gamepad_model import GamepadStickData
        from scene.gp_stick_item import GpStickItem
        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, 1920, 1080)
        view = QGraphicsView(scene)
        view.resize(1920, 1080)
        stick = GpStickItem(GamepadStickData(x=400, y=300, mode='wasd'))
        scene.addItem(stick)
        scene.button_items = [stick]
        ctrl = RunController(scene, view)
        centre = stick.circle_center_scene()
        point = view.mapToGlobal(view.mapFromScene(centre))
        ctrl.cursor_input._model = AdaptivePointer(QRect(-10000, -10000, 20000, 20000))
        ctrl.cursor_input._model.independent = True
        ctrl.cursor_input._model.position = (point.x(), point.y())
        with patch('core.cursor_input._user32') as api, \
             patch('engine.run_controller.user32') as key_api, \
             patch.object(ctrl, '_smart_trigger') as trigger:
            key_api.GetAsyncKeyState.return_value = 0
            ctrl._poll_gp_sticks()
            self.assertIs(ctrl._active_gp_stick, stick)
            ctrl.cursor_input._model.position = (point.x() + 60, point.y())
            ctrl._poll_gp_sticks()
            trigger.assert_any_call('d', 'p')
            ctrl._reset_pointer_actions()
            trigger.assert_any_call('d', 'r')
            api.SetCursorPos.assert_not_called()
        scene.clear()

    def test_visual_cursor_and_hit_testing_share_position(self):
        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, 1920, 1080)
        view = QGraphicsView(scene)
        view.resize(1920, 1080)
        target = scene.addRect(400, 300, 100, 100)
        ctrl = RunController(scene, view)
        global_pos = view.mapToGlobal(view.mapFromScene(450, 350))
        ctrl.cursor_input._model.independent = True
        ctrl.cursor_input._model.position = (global_pos.x(), global_pos.y())
        cursor = VirtualCursorItem(position_source=ctrl.cursor_input.position)
        scene.addItem(cursor)
        with patch('core.cursor_input.QCursor.pos', return_value=QPoint(960, 540)):
            cursor._update_pos()
            item, position, _, _ = ctrl._get_cursor_item()
        self.assertIs(item, target)
        self.assertEqual(cursor.pos(), position)
        scene.clear()

    def test_wheel_side_button_and_recenter_use_logical_position(self):
        item = SimpleNamespace(data=SimpleNamespace(xbutton1='x'), on_wheel=Mock(),
                               set_visual_state=Mock())
        scene = SimpleNamespace(itemAt=Mock(return_value=item))
        window = SimpleNamespace(mapFromGlobal=lambda p: p, mapToScene=lambda p: p,
                                 transform=lambda: None)
        ctrl = RunController(scene, window)
        ctrl.cursor_input._model.independent = True
        ctrl.cursor_input._model.position = (450, 350)
        ctrl._dispatch_wheel('up', 960, 540)
        self.assertEqual(scene.itemAt.call_args.args[0], QPoint(450, 350))
        item.on_wheel.assert_called_once_with('up')
        with patch('engine.run_controller.trigger') as trigger:
            ctrl._dispatch_xbutton('xbutton1', 'p')
            trigger.assert_called_once_with('x', 'p')
        with patch.object(ctrl, '_resolve_recenter_pos', return_value=(500, 400)), \
             patch('core.cursor_input._user32') as api:
            ctrl._do_recenter('screen')
            self.assertEqual(ctrl.cursor_input.position(), QPoint(500, 400))
            api.SetCursorPos.assert_not_called()

    def test_transition_releases_pointer_actions(self):
        sm = Mock()
        item = SimpleNamespace(_hover_sm=sm, set_visual_state=Mock())
        ctrl = RunController(SimpleNamespace(button_items=[item]), None)
        ctrl._poll_hover_item = item
        ctrl._holding_lclick = (item, 'w')
        ctrl._active_key_count = 2
        with patch('engine.run_controller._is_alive', return_value=True), \
             patch.object(ctrl, '_smart_trigger') as trigger:
            ctrl._reset_pointer_actions()
        sm.reset.assert_called_once()
        trigger.assert_called_once_with('w', 'r')
        self.assertIsNone(ctrl._holding_lclick)
        self.assertIsNone(ctrl._poll_hover_item)
        self.assertEqual(ctrl._active_key_count, 0)

    def test_side_button_release_keeps_original_mapping_across_transition(self):
        ctrl = RunController(None, None)
        ctrl._holding_xbuttons['xbutton1'] = (None, 'w', False)
        with patch('engine.run_controller.trigger') as trigger:
            ctrl._reset_pointer_actions()
            trigger.assert_called_once_with('w', 'r')
            # Physical release after the transition must not release a new item.
            ctrl._dispatch_xbutton('xbutton1', 'r')
            trigger.assert_called_once_with('w', 'r')
        self.assertEqual(ctrl._holding_xbuttons, {})

    def test_transition_does_not_reset_unrelated_gamepad_trigger(self):
        ctrl = RunController(None, None)
        ctrl._gp_enabled = True
        with patch('engine.run_controller.GamepadEngine.get') as get:
            ctrl._reset_pointer_actions()
            get.return_value.set_trigger.assert_not_called()

    def test_preview_does_not_offer_downgrade_to_current_stable(self):
        from core.update_checker import _is_newer
        self.assertFalse(_is_newer('v0.5.1', '0.5.2-preview.1'))
        self.assertTrue(_is_newer('v0.5.2', '0.5.2-preview.1'))
        self.assertTrue(_is_newer('v0.5.3', '0.5.2'))
        self.assertFalse(_is_newer('v0.5.2', '0.5.2'))


class PassthroughTests(unittest.TestCase):
    def setUp(self):
        self.style = 0
        self.calls = []
        self.api = SimpleNamespace(GetWindowLongW=lambda *a: self.style,
            SetWindowLongW=self.set_style, mouse_event=lambda *a: self.calls.append(a))
        self.patch = patch('engine.passthrough_manager.user32', self.api)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.manager = PassthroughManager(None)
        self.manager._hwnd = 1

    def set_style(self, hwnd, index, style):
        self.style = style

    def test_two_modes_and_legacy_fallback(self):
        self.assertEqual(PT_CYCLE, [PT_ON, PT_OFF])
        self.assertNotIn('pt_block', DEFAULT_HOTKEYS)
        for mode, on_ui, transparent in ((PT_ON, True, True), (PT_ON, False, True),
                                          (PT_OFF, True, False), (PT_OFF, False, True)):
            self.manager.set_mode(mode)
            self.manager.update_smart_passthrough(on_ui)
            self.assertEqual(bool(self.style & WS_EX_TRANSPARENT), transparent)
        self.manager.set_mode('pt_block')
        self.assertEqual(self.manager.mode, PT_ON)

    def test_pending_forward_cannot_overwrite_new_mode(self):
        self.manager.set_mode(PT_OFF)
        self.manager.update_smart_passthrough(True)
        self.manager.forward_click_to_game(None)
        self.manager.set_mode(PT_ON)
        wait(90)
        self.assertTrue(self.style & WS_EX_TRANSPARENT)
        self.assertEqual(self.manager.mode, PT_ON)

    def test_pending_forward_restores_latest_hover_not_old_hover(self):
        self.manager.set_mode(PT_OFF)
        self.manager.forward_click_to_game(None)
        self.manager.update_smart_passthrough(True)
        wait(90)
        self.assertFalse(self.style & WS_EX_TRANSPARENT)

    def test_old_profile_load_save_preserves_layout_and_maps_removed_mode(self):
        from core.config_manager import load_config_from_file, save_config_to_file
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'profile.json')
            self.assertTrue(save_config_to_file(path, geometry='1920x1080+0+0', transparency=.6,
                click_through='pt_block', buttons=[dict(name='W', x=25, y=50, w=100, h=100)]))
            config = load_config_from_file(path)
            self.assertEqual(config['click_through'], PT_ON)
            self.assertEqual(config['buttons'][0]['x'], 25)
            self.assertEqual(config['buttons'][0]['name'], 'W')


if __name__ == '__main__':
    unittest.main()
