"""Wheel editor controls respect foreground items in drawing and hit testing."""

import unittest
from unittest.mock import Mock

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsView

from core.constants import default_wheel_sectors
from core.i18n import load_locale
from models.button_model import ButtonData
from scene.overlay_scene import OverlayScene


app = QApplication.instance() or QApplication([])


class WheelControlLayerTests(unittest.TestCase):
    def setUp(self):
        load_locale('zh-CN')
        self.scene = OverlayScene()
        self.scene.setSceneRect(0, 0, 1000, 800)
        self.scene._on_wheel_style_clicked = Mock()
        self.scene.save_config = Mock()
        self.scene.load_from_config({'buttons': [], 'wheel_visible': True,
            'wheel_mode': 'large', 'wheel_sectors': default_wheel_sectors()})
        self.view = QGraphicsView(self.scene)
        self.view.resize(1002, 802)
        self.view.show()
        app.processEvents()

    def tearDown(self):
        self.view.close()
        self.scene.clear()
        app.processEvents()

    def image(self):
        image = QImage(1000, 800, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        self.scene.render(painter, QRectF(0, 0, 1000, 800), self.scene.sceneRect())
        painter.end()
        return image

    def test_foreground_button_covers_both_controls_and_receives_the_clicks(self):
        controls = (self.scene._wheel_style_btn, self.scene._wheel_resize_btn)
        points = [control.mapToScene(control.boundingRect().center()) for control in controls]
        before = self.image()
        foreground = self.scene.add_button(ButtonData(name='Foreground', w=140, h=100), _toast=False)
        foreground.setPos(points[0] - QPointF(30, 40))
        app.processEvents()
        after = self.image()
        for point in points:
            self.assertIs(self.scene.itemAt(point, QTransform()), foreground)
            self.assertNotEqual(before.pixelColor(point.toPoint()), after.pixelColor(point.toPoint()))
            QTest.mouseClick(self.view.viewport(), Qt.MouseButton.LeftButton,
                             pos=self.view.mapFromScene(point))
        self.scene._on_wheel_style_clicked.assert_not_called()
        self.assertEqual(self.scene._wheel_offset, 0)
        self.assertFalse(self.scene._wheel_resize_btn._dragging)

        foreground.setPos(0, 0)
        app.processEvents()
        for control, point in zip(controls, points):
            self.assertIs(self.scene.itemAt(point, QTransform()), control)
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.view.mapFromScene(points[0]))
        self.scene._on_wheel_style_clicked.assert_called_once()
        QTest.mousePress(self.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.view.mapFromScene(points[1]))
        self.assertTrue(self.scene._wheel_resize_btn._dragging)
        QTest.mouseRelease(self.view.viewport(), Qt.MouseButton.LeftButton,
                           pos=self.view.mapFromScene(points[1]))
        self.assertFalse(self.scene._wheel_resize_btn._dragging)

    def test_layering_survives_wheel_rebuild_move_and_edit_run_visibility(self):
        controls = (self.scene._wheel_style_btn, self.scene._wheel_resize_btn)
        for mode in ('small', 'large', 'double', 'dual'):
            self.scene._wheel_mode = mode
            self.scene._rebuild_wheel()
            self.scene._update_wheel_controls()
            for control in controls:
                self.assertIs(self.scene.itemAt(control.sceneBoundingRect().center(), QTransform()), control)
            for item in self.scene._all_wheel_items():
                self.assertLess(item.zValue(), controls[0].zValue())
            initial = [control.pos() for control in controls]
            self.scene.begin_wheel_drag(QPointF(0, 0))
            self.scene.update_wheel_drag(QPointF(100, 100))
            self.scene.end_wheel_drag()
            for control, position in zip(controls, initial):
                self.assertEqual(control.pos(), position + QPointF(100, 100))
            self.scene.set_mode('run')
            self.assertTrue(all(not control.isVisible() for control in controls))
            self.scene.set_mode('edit')
            self.assertTrue(all(control.isVisible() for control in controls))

    def test_gear_glyph_is_visually_centered_inside_its_button(self):
        button = self.scene._wheel_style_btn
        image = QImage(120, 120, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        self.scene.render(painter, QRectF(0, 0, 120, 120), button.sceneBoundingRect())
        painter.end()
        pixels = [(x, y) for y in range(120) for x in range(120)
                  if min(image.pixelColor(x, y).red(), image.pixelColor(x, y).green(),
                         image.pixelColor(x, y).blue()) > 235]
        self.assertTrue(pixels)
        xs, ys = zip(*pixels)
        self.assertLessEqual(abs((min(xs) + max(xs)) / 2 - 59.5), 1)
        self.assertLessEqual(abs((min(ys) + max(ys)) / 2 - 59.5), 1)
