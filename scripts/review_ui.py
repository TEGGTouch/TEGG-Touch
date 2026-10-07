"""Start the actual client and open an existing button editor for UI review.

Run: python scripts/review_ui.py [--color | --wheel | --controls | --themes]
Uses main.main(), the current branch's normal profile and existing editor route.
Captures only application widgets, never the desktop behind the overlay.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main as client
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication


def open_review():
    app = QApplication.instance()
    window = next((w for w in app.topLevelWidgets() if isinstance(w, client.OverlayWindow)), None)
    if window is None:
        return
    window._edit_toolbar.grab().save(str(ROOT / 'docs' / 'ui-running-toolbar.png'))
    if '--controls' in sys.argv:
        return  # Leave the normal canvas available for overlap / drag review.
    if '--themes' in sys.argv:
        open_theme_review(window)
        return
    items = window._scene.button_items
    item = next((it for it in items if getattr(it.data, 'name', '') == '全配置示范'), None)
    if item is None:
        item = next((it for it in items if getattr(it.data, 'btn_type', '') == 'button'), None)
    if item is None:
        return
    window._open_button_editor(item)
    editor = getattr(item, '_editor_dialog', None)
    if editor:
        editor.raise_()
        editor.activateWindow()
        QTimer.singleShot(500, lambda: editor.grab().save(str(ROOT / 'docs' / 'ui-running-editor.png')))
    if '--color' in sys.argv:
        QTimer.singleShot(800, lambda: open_color_review(window, editor))
    elif '--wheel' in sys.argv:
        QTimer.singleShot(800, lambda: open_wheel_review(window, editor))


def open_wheel_review(window, editor):
    if editor:
        editor.close()
    keyboard = window._virtual_keyboard
    keyboard.position_above_toolbar(window._edit_toolbar)
    keyboard.show()

    def open_style():
        keyboard.grab().save(str(ROOT / 'docs' / 'ui-running-keyboard.png'))
        keyboard.hide()

        def capture_style():
            from views.wheel_style_dialog import WheelStyleDialog
            dialog = next((w for w in QApplication.instance().topLevelWidgets()
                           if isinstance(w, WheelStyleDialog) and w.isVisible()), None)
            if dialog:
                # Review the widest reset label; this remains an unsaved selection.
                dialog._select_type('dual')
                QTimer.singleShot(200, lambda: dialog.grab().save(
                    str(ROOT / 'docs' / 'ui-running-wheel.png')))

        QTimer.singleShot(400, capture_style)
        window._scene._on_wheel_style_clicked()

    QTimer.singleShot(300, open_style)


def open_theme_review(window):
    # Capture the client's existing run widgets without starting input listeners.
    window._run_toolbar.grab().save(str(ROOT / 'docs' / 'ui-running-run-toolbar.png'))
    window._collapsed_bubble.grab().save(str(ROOT / 'docs' / 'ui-running-bubble.png'))

    def capture_wheel():
        from views.wheel_style_dialog import WheelStyleDialog
        dialog = next((w for w in QApplication.instance().topLevelWidgets()
                       if isinstance(w, WheelStyleDialog) and w.isVisible()), None)
        if dialog:
            dialog._select_type('dual')  # Review only; discard this selection below.
            def finish_wheel():
                dialog.grab().save(str(ROOT / 'docs' / 'ui-running-wheel.png'))
                dialog.reject()
            QTimer.singleShot(200, finish_wheel)

    QTimer.singleShot(400, capture_wheel)
    window._scene._on_wheel_style_clicked()
    window._open_voice_settings()
    voice = window._dlg_voice
    voice.raise_()
    voice.activateWindow()
    QTimer.singleShot(500, lambda: voice.grab().save(
        str(ROOT / 'docs' / 'ui-running-voice.png')))


def open_color_review(window, editor):
    if editor:
        editor.close()
    window._open_hotkey_settings()
    settings = window._dlg_hotkey
    settings._select_page(1)
    settings.raise_()
    settings.activateWindow()

    def capture_picker():
        from views.color_picker_dialog import ColorPickerDialog
        picker = next((w for w in QApplication.instance().topLevelWidgets()
                       if isinstance(w, ColorPickerDialog) and w.isVisible()), None)
        if picker:
            picker.grab().save(str(ROOT / 'docs' / 'ui-running-color.png'))

    def open_picker():
        cursor_type, buttons = next(iter(settings._cursor_color_btns.items()))
        key, button = next(iter(buttons.items()))
        QTimer.singleShot(400, capture_picker)
        settings._on_pick_color(cursor_type, key, button)

    QTimer.singleShot(300, open_picker)


if __name__ == '__main__':
    # Schedule review after the normal entry point has built its QApplication.
    application_class = client.QApplication

    def review_application(arguments):
        app = application_class(arguments)
        QTimer.singleShot(1400, open_review)
        return app

    client.QApplication = review_application
    client.main()
