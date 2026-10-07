"""The existing Qt color picker inside the editor's shared dialog shell."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLayout,
    QPushButton, QVBoxLayout,
)

from core.i18n import t
from views.ui_components import CONTROL_BG, INNER_RADIUS, finish_dialog


class ColorPickerDialog(QColorDialog):
    def __init__(self, initial, parent=None, title='', options=None):
        super().__init__(initial, parent)
        if options is not None:
            self.setOptions(options)
        self.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        self.setWindowTitle(title or self.windowTitle())
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None

        native_root = self.layout()
        # Qt's picker normally fixes its size to its content hint. The shared
        # shell needs its own screen-aware dimensions, including the footer.
        native_root.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        button_box = self.findChild(QDialogButtonBox)
        self._ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        # Removing from the box disconnects its role dispatch. Reconnect the same
        # QColorDialog accept/reject methods, including selectedColor semantics.
        for button in (self._ok_button, self._cancel_button):
            button_box.removeButton(button)
        self._ok_button.clicked.connect(self.accept)
        self._cancel_button.clicked.connect(self.reject)
        self._ok_button.setText(t('dialog.confirm'))
        self._cancel_button.setText(t('dialog.cancel'))
        self._ok_button.setDefault(True)

        native_items = []
        while native_root.count():
            item = native_root.takeAt(0)
            if item.widget() is not button_box:
                native_items.append(item)
        button_box.hide()
        native_root.setContentsMargins(0, 0, 0, 0)
        native_root.setSpacing(0)

        container = QFrame(self)
        container.setObjectName('color_picker_container')
        root = QVBoxLayout(container)
        header = QHBoxLayout()
        header.addWidget(QLabel(self.windowTitle()), 1)
        close = QPushButton('×')
        close.clicked.connect(self.reject)
        header.addWidget(close)
        root.addLayout(header)
        for item in native_items:
            if item.layout():
                root.addLayout(item.layout())
            else:
                root.addItem(item)
        actions = QHBoxLayout()
        for button in (self._cancel_button, self._ok_button):
            button.setStyleSheet(f'''
                QPushButton {{ background: {CONTROL_BG}; color: #EEE;
                    border: none; border-radius: {INNER_RADIUS}px; padding: 0 16px; }}
                QPushButton:hover {{ background: #505050; }}
            ''')
            actions.addWidget(button)
        root.addLayout(actions)
        native_root.addWidget(container)
        finish_dialog(self, (760, 620), actions=(self._cancel_button, self._ok_button))

    @staticmethod
    def getColor(initial=QColor(Qt.GlobalColor.white), parent=None, title='', options=None):
        dialog = ColorPickerDialog(initial, parent, title, options)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                return dialog.selectedColor()
            return QColor()
        finally:
            dialog.deleteLater()

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self._ui_header.geometry().contains(event.position().toPoint())):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
