"""Start the actual client and open an existing button editor for UI review.

Run: python scripts/review_ui.py [--color]
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
