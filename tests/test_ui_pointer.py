"""Offscreen integration tests. All physical input reads/injection are mocked."""

import tempfile
import os
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (QApplication, QDialog, QGraphicsScene, QGraphicsView,
                             QPushButton, QWidget)

from core.cursor_input import AdaptivePointer, CursorInput, CursorProbe, RawMouseReader
from engine.run_controller import RunController
from engine.ui_pointer import UiPointerController
from scene.virtual_cursor_item import VirtualCursorItem

app = QApplication.instance() or QApplication([])


class PointerTests(unittest.TestCase):
    def setUp(self):
        self.buttons = Qt.MouseButton.NoButton
        self.key_patch = patch.object(UiPointerController, 'read_buttons', lambda _: self.buttons)
        self.key_patch.start()
        self.mod_patch = patch.object(UiPointerController, 'modifiers',
                                     return_value=Qt.KeyboardModifier.NoModifier)
        self.mod_patch.start()
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, 1200, 800)
        self.scene.grid_size = 10
        self.scene.show_tooltip = Mock()
        self.scene.move_tooltip = Mock()
        self.scene.hide_tooltip = Mock()
        self.window = QGraphicsView(self.scene)
        self.window._current_mode = 'run'
        self.window.resize(1200, 800)
        self.source = CursorInput()
        self.source._model = AdaptivePointer(QRect(-10000, -10000, 20000, 20000))
        self.source._model.independent = True
        self.source.poll = Mock(return_value=False)
        self.run = RunController(self.scene, self.window, self.source)
        self.cursor = VirtualCursorItem(position_source=self.source.position)
        self.scene.addItem(self.cursor)
        self.router = UiPointerController(self.window, self.source, self.run, self.cursor)
        self.router.set_drawn(True)
        self.window.show()
        self.panel = QWidget(self.window, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.panel.setGeometry(200, 150, 240, 80)
        self.button = QPushButton('Menu', self.panel)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setGeometry(20, 15, 130, 40)
        self.panel.show()
        self.move(self.button.mapToGlobal(self.button.rect().center()))

    def tearDown(self):
        self.router.stop()
        app.removeEventFilter(self.router)
        self.window.close()
        app.processEvents()
        self.key_patch.stop()
        self.mod_patch.stop()

    def move(self, point):
        self.source._model.position = (point.x(), point.y())
        self.router.tick()
        app.processEvents()

    def press(self):
        self.buttons = Qt.MouseButton.LeftButton
        self.router.tick()
        app.processEvents()

    def release(self):
        self.buttons = Qt.MouseButton.NoButton
        self.router.tick()
        app.processEvents()

    def scene_point(self, x, y):
        return self.window.mapToGlobal(self.window.mapFromScene(x, y))

    def test_menu_hand_and_click_uses_virtual_position(self):
        clicked = Mock()
        self.button.clicked.connect(clicked)
        self.assertTrue(self.button.underMouse())
        self.assertEqual(self.router.cursor_for(self.button).shape(), Qt.CursorShape.PointingHandCursor)
        self.assertTrue(self.router.layer.isVisible())
        self.assertFalse(self.cursor.isVisible())
        self.press()
        self.assertTrue(self.button.isDown())
        self.release()
        clicked.assert_called_once()
        self.assertTrue(self.run._pointer_ui_active)

    def test_native_mouse_at_locked_centre_cannot_click_ui(self):
        clicked = Mock()
        self.button.clicked.connect(clicked)
        for kind, button_state in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                                    (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            event = QMouseEvent(kind, QPointF(30, 20), QPointF(960, 540),
                Qt.MouseButton.LeftButton, button_state, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(self.button, event)
        clicked.assert_not_called()

    def test_drag_outside_button_releases_without_clicking_underneath(self):
        clicked = Mock()
        self.button.clicked.connect(clicked)
        self.press()
        self.move(self.scene_point(800, 500))
        self.assertTrue(self.run._pointer_ui_active)
        self.release()
        clicked.assert_not_called()
        self.assertFalse(self.button.isDown())
        self.router.tick()
        self.assertFalse(self.run._pointer_ui_active)

    def test_cancel_discards_queued_press_and_does_not_click(self):
        clicked = Mock()
        self.button.clicked.connect(clicked)
        self.buttons = Qt.MouseButton.LeftButton
        self.router.tick()  # queued but not delivered
        self.router.cancel()
        app.processEvents()
        self.release()
        clicked.assert_not_called()
        self.assertFalse(self.button.isDown())

    def test_menu_hiding_during_press_cancels_capture(self):
        clicked = Mock()
        self.button.clicked.connect(clicked)
        self.press()
        self.panel.hide()
        self.router.tick()
        app.processEvents()
        self.release()
        clicked.assert_not_called()
        self.assertIsNone(self.router._capture)

    def test_editor_drag_uses_qt_scene_events(self):
        from models.button_model import ButtonData
        from scene.touch_button_item import TouchButtonItem
        self.window._current_mode = 'edit'
        item = TouchButtonItem(ButtonData(x=500, y=350, w=100, h=100))
        self.scene.addItem(item)
        item.set_mode('edit')
        self.move(self.scene_point(540, 390))
        before = item.pos()
        self.press()
        self.move(self.scene_point(600, 430))
        self.release()
        self.assertEqual(item.pos() - before, QPointF(60, 40))

    def test_editor_resize_uses_logical_coordinates(self):
        from models.button_model import ButtonData
        from scene.touch_button_item import TouchButtonItem
        self.window._current_mode = 'edit'
        item = TouchButtonItem(ButtonData(x=500, y=350, w=100, h=100))
        self.scene.addItem(item)
        item.set_mode('edit')
        handle = item._resize_handle
        centre = handle.mapToScene(handle.boundingRect().center())
        self.move(self.scene_point(centre.x(), centre.y()))
        self.press()
        self.move(self.scene_point(660, 490))
        self.release()
        self.assertEqual((item.data.w, item.data.h), (160, 140))

    def test_editor_double_click_opens_existing_item_editor_signal(self):
        from models.button_model import ButtonData
        from scene.touch_button_item import TouchButtonItem
        self.window._current_mode = 'edit'
        item = TouchButtonItem(ButtonData(x=500, y=350, w=100, h=100))
        self.scene.addItem(item)
        item.set_mode('edit')
        activated = Mock()
        item.doubleClicked.connect(activated)
        self.move(self.scene_point(540, 390))
        self.press()
        self.release()
        self.press()
        self.release()
        activated.assert_called_once()

    def test_raw_wheel_reaches_widget_without_run_hook(self):
        class WheelWidget(QWidget):
            def wheelEvent(self, event):
                self.delta = event.angleDelta().y()
                event.accept()
        widget = WheelWidget(self.panel)
        widget.setGeometry(160, 5, 70, 60)
        widget.show()
        self.move(widget.mapToGlobal(widget.rect().center()))
        self.source._wheel_delta = -120
        self.router.tick()
        app.processEvents()
        self.assertEqual(widget.delta, -120)
        self.assertEqual(self.source.take_wheel_delta(), 0)

    def test_real_toolbar_drag_propagates_logical_events_from_handle(self):
        from views.run_toolbar import RunToolbar
        from views.edit_toolbar import _DragHandle
        toolbar = RunToolbar(self.window)
        toolbar.move(20, 350)
        toolbar.show()
        handle = toolbar.findChild(_DragHandle)
        point = handle.mapToGlobal(handle.rect().center())
        self.move(point)
        before = toolbar.pos()
        self.press()
        with patch('PyQt6.QtWidgets.QApplication.primaryScreen', return_value=SimpleNamespace(
                geometry=lambda: QRect(0, 0, 3840, 2160))):
            self.move(point + QPoint(40, 30))
        self.release()
        self.assertEqual(toolbar.pos() - before, QPoint(40, 30))
        toolbar.close()

    def test_slider_drag_keeps_capture(self):
        from PyQt6.QtWidgets import QSlider
        slider = QSlider(Qt.Orientation.Horizontal, self.panel)
        slider.setGeometry(10, 60, 210, 18)
        slider.show()
        self.move(slider.mapToGlobal(QPoint(5, 8)))
        self.press()
        self.move(slider.mapToGlobal(QPoint(200, 8)))
        self.release()
        self.assertGreater(slider.value(), 80)

    def test_combo_popup_receives_virtual_click(self):
        from PyQt6.QtWidgets import QComboBox
        combo = QComboBox(self.panel)
        combo.setGeometry(155, 15, 80, 30)
        combo.addItems(['One', 'Two', 'Three'])
        combo.show()
        self.move(combo.mapToGlobal(combo.rect().center()))
        self.press()
        self.release()
        view = combo.view()
        self.assertTrue(view.isVisible())
        rect = view.visualRect(combo.model().index(1, 0))
        self.move(view.viewport().mapToGlobal(rect.center()))
        self.press()
        self.release()
        self.assertEqual(combo.currentIndex(), 1)

    def test_popup_outside_click_dismisses_without_clicking_underneath(self):
        from PyQt6.QtWidgets import QComboBox
        combo = QComboBox(self.panel)
        combo.setGeometry(155, 15, 80, 30)
        combo.addItems(['One', 'Two'])
        combo.show()
        self.move(combo.mapToGlobal(combo.rect().center()))
        self.press()
        self.release()
        clicked = Mock()
        self.button.clicked.connect(clicked)
        self.move(self.button.mapToGlobal(self.button.rect().center()))
        self.press()
        self.release()
        clicked.assert_not_called()
        self.assertFalse(combo.view().isVisible())


    def test_modal_exec_keeps_receiving_pointer_events(self):
        result = []
        def open_dialog():
            dialog = QDialog(self.window)
            dialog.setGeometry(500, 250, 220, 100)
            accept = QPushButton('Accept', dialog)
            accept.setGeometry(30, 30, 130, 40)
            accept.clicked.connect(dialog.accept)
            def aim():
                point = accept.mapToGlobal(accept.rect().center())
                self.source._model.position = (point.x(), point.y())
            QTimer.singleShot(30, aim)
            QTimer.singleShot(70, lambda: setattr(self, 'buttons', Qt.MouseButton.LeftButton))
            QTimer.singleShot(120, lambda: setattr(self, 'buttons', Qt.MouseButton.NoButton))
            QTimer.singleShot(600, dialog.reject)
            result.append(dialog.exec())
            dialog.close()
        self.button.clicked.connect(open_dialog)
        self.router.timer.start()
        self.press()
        self.release()
        self.router.timer.stop()
        self.assertEqual(result, [QDialog.DialogCode.Accepted])

    def test_normal_mode_keeps_native_mouse_and_existing_renderer(self):
        self.source._model.independent = False
        self.router.tick()
        self.assertFalse(self.router.layer.isVisible())
        self.assertTrue(self.cursor.isVisible())
        self.assertIsNone(QApplication.overrideCursor())
        clicked = Mock()
        self.button.clicked.connect(clicked)
        for kind, button_state in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                                    (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            event = QMouseEvent(kind, QPointF(30, 20), QPointF(960, 540),
                Qt.MouseButton.LeftButton, button_state, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(self.button, event)
        clicked.assert_called_once()

    def test_cursor_layer_is_nonactivating_and_input_transparent(self):
        flags = self.router.layer.windowFlags()
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(flags & Qt.WindowType.WindowDoesNotAcceptFocus)

    def test_custom_cursor_keeps_scene_scale_and_ball_hotspot(self):
        self.cursor.set_shape('ball')
        self.window.scale(1.5, 1.5)
        point = self.scene_point(900, 600)
        self.move(point)
        self.assertEqual(self.router.layer.width(), round(self.cursor._w * 1.5))
        self.assertEqual(self.router.layer.x(), round(point.x() + self.cursor._hx * 1.5))

    def test_hidden_window_stops_listener_and_restores_native_cursor(self):
        self.window.hide()
        with patch.object(self.source, 'stop', wraps=self.source.stop) as stop:
            self.router.tick()
            stop.assert_called_once()
        self.assertFalse(self.router.layer.isVisible())
        self.assertFalse(self.source.independent)
        self.assertIsNone(QApplication.overrideCursor())


class LifecycleTests(unittest.TestCase):
    def test_real_overlay_preserves_pointer_through_run_edit_run(self):
        from core import config_manager as config
        from views.overlay_window import OverlayWindow
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch.multiple(config,
                PROFILES_DIR=os.path.join(directory, 'profiles'),
                HOTKEYS_FILE=os.path.join(directory, 'hotkeys.json'),
                CONFIG_FILE=os.path.join(directory, 'config.json')))
            for name in ('views.overlay_window.release_all_keys',
                         'views.overlay_window.install_wheel_hook',
                         'views.overlay_window.uninstall_wheel_hook',
                         'views.overlay_window.QApplication.quit',
                         'engine.run_controller.release_all_keys',
                         'engine.run_controller.keyboard_hook.uninstall_hook',
                         'engine.gamepad_engine.GamepadEngine.shutdown_singleton',
                         'engine.run_controller.RunController._start_key_remap',
                         'engine.run_controller.RunController._start_voice',
                         'engine.run_controller.RunController._stop_voice'):
                stack.enter_context(patch(name))
            stack.enter_context(patch.object(CursorInput, 'start'))
            stack.enter_context(patch.object(CursorInput, 'poll', return_value=False))
            stack.enter_context(patch.object(UiPointerController, 'read_buttons',
                                             return_value=Qt.MouseButton.NoButton))
            window = OverlayWindow()
            try:
                window._scene.get_config()['voice_commands'] = []
                window.show()
                pointer = window._cursor_input
                pointer._model.independent = True
                pointer._model.position = (420, 380)
                window._pointer_controller.tick()
                window.to_run()
                window.to_edit()
                self.assertTrue(window._pointer_controller.timer.isActive())
                self.assertFalse(window._run_controller._timer.isActive())
                self.assertTrue(pointer.independent)
                self.assertEqual(pointer.position(), QPoint(420, 380))
                window.to_run()
                self.assertTrue(pointer.independent)
                self.assertIs(window._run_controller.cursor_input, pointer)
            finally:
                window.close()
                app.removeEventFilter(window._pointer_controller)
                app.processEvents()

    def test_owned_focus_retains_game_anchor_and_pointer(self):
        model = AdaptivePointer(QRect(0, 0, 1920, 1080))
        for i in range(40):
            model.advance(i * .01, CursorProbe((960, 540), (960, 540), False), [(0, 4, 0)])
        before = model.position
        for i in range(40, 70):
            changed, focus = model.advance(i * .01,
                CursorProbe((960, 540), (300, 200), True, foreground=20,
                            external=False, owned=True), [(0, 4, 0)])
            self.assertEqual((changed, focus), (False, False))
        self.assertTrue(model.independent)
        self.assertEqual(model.position, (before[0] + 120, before[1]))
        changed, focus = model.advance(.8, CursorProbe((960, 540), (960, 540), False), [])
        self.assertEqual((changed, focus), (False, False))
        changed, focus = model.advance(.9,
            CursorProbe((960, 540), (960, 540), False, foreground=99), [])
        self.assertEqual((changed, focus), (True, True))

    def test_owned_editor_returns_to_system_when_cursor_really_moves(self):
        model = AdaptivePointer(QRect(0, 0, 1920, 1080))
        for i in range(40):
            model.advance(i * .01, CursorProbe((960, 540), (960, 540), False), [(0, 4, 0)])
        for i in range(40, 80):
            model.advance(i * .01, CursorProbe((960 + (i - 39) * 4, 540), (300, 200),
                True, foreground=20, external=False, owned=True), [(0, 4, 0)])
        self.assertFalse(model.independent)

    def test_stopping_run_does_not_stop_shared_pointer(self):
        source = CursorInput()
        source._model.independent = True
        scene = QGraphicsScene()
        scene.button_items = []
        controller = RunController(scene, None, source)
        with patch.object(source, 'stop') as stop, \
             patch('engine.run_controller.release_all_keys'), \
             patch('engine.run_controller.keyboard_hook.uninstall_hook'):
            controller.stop()
        stop.assert_not_called()
        self.assertTrue(source.independent)

    def test_raw_wheel_is_separate_from_relative_motion(self):
        reader = RawMouseReader()
        reader.feed(0, 0, 0, 120)
        reader.feed(0, 3, -2, -240)
        self.assertEqual(reader.drain(), [(0, 3, -2)])
        self.assertEqual(reader.drain_wheel(), -120)
        self.assertEqual(reader.drain_wheel(), 0)


if __name__ == '__main__':
    unittest.main()
