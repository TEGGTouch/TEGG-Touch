"""Shared presentation for the desktop editor; existing widgets keep their callbacks."""

import re

from PyQt6.QtCore import QEvent, QObject, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QPainter, QColor
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget, QRadioButton, QAbstractScrollArea,
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
)

from core.i18n import get_font, get_lang

OUTER_RADIUS = 12
INNER_RADIUS = 6
CARD_RADIUS = 8
SMALL_RADIUS = 3

# Surface depth: recessed wells < panels < raised controls.
RECESSED_BG = '#202020'
PANEL_BG = '#2D2D2D'
CONTROL_BG = '#3A3A3A'
AMBER_BG = '#F59E0B'
AMBER_HOVER = '#D97706'
SCROLL_GAP = 12


class SegmentedControl(QFrame):
    """A shared recessed track; adopt existing buttons without changing their clicks."""

    def __init__(self, buttons, parent=None):
        super().__init__(parent)
        self.buttons = dict(buttons) if isinstance(buttons, dict) else dict(enumerate(buttons))
        self._selected = None
        self.setObjectName('ui_segments')
        self.setStyleSheet(f'QFrame#ui_segments {{ background: {RECESSED_BG}; border: none; border-radius: {CARD_RADIUS}px; }}')
        self._thumb = QFrame(self)
        self._thumb.setStyleSheet(f'background: {AMBER_BG}; border: none; border-radius: {INNER_RADIUS}px;')
        self._thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._thumb.hide()
        self._animation = QPropertyAnimation(self._thumb, b'geometry', self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(0)
        height = max((button.minimumHeight() for button in self.buttons.values()), default=32)
        height = max(24, height)
        self.setFixedHeight(height + 8)
        for key, button in self.buttons.items():
            button.setFixedHeight(height)
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            button.installEventFilter(self)
            row.addWidget(button, 1)
            if isinstance(button, QRadioButton):
                button.toggled.connect(lambda checked, picked=key: self.set_selected(picked) if checked else None)
                if button.isChecked():
                    self._selected = key
        self._style_buttons()

    def _style_buttons(self):
        for key, button in self.buttons.items():
            color = RECESSED_BG if key == self._selected else '#AAAAAA'
            button.setStyleSheet(f'''
                QPushButton, QRadioButton {{ background: transparent; color: {color}; border: none;
                    border-radius: {INNER_RADIUS}px; padding: 0 4px; }}
                QPushButton:hover, QRadioButton:hover {{ color: {RECESSED_BG if key == self._selected else '#FFFFFF'}; }}
                QPushButton:disabled, QRadioButton:disabled {{ color: #666666; background: transparent; }}
                QRadioButton::indicator {{ width: 0; height: 0; }}
            ''')
            for label in button.findChildren(QLabel):
                label.setStyleSheet(f'color: {color}; background: transparent;')

    def set_selected(self, key):
        if key not in self.buttons:
            return
        changed = self._selected != key
        self._selected = key
        self._style_buttons()
        self._place_thumb(animate=changed)

    def clear_selection(self):
        self._selected = None
        self._animation.stop()
        self._thumb.hide()
        self._style_buttons()

    def _place_thumb(self, animate=False):
        if self._selected not in self.buttons:
            return
        button = self.buttons[self._selected]
        target = button.geometry()
        self._animation.stop()
        if animate and self.isVisible() and self._thumb.isVisible():
            self._animation.setStartValue(self._thumb.geometry())
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self._thumb.setGeometry(target)
        self._thumb.setVisible(button.isEnabled())
        self._thumb.lower()

    def eventFilter(self, obj, event):
        if isinstance(obj, QRadioButton):
            if event.type() == QEvent.Type.Paint:
                painter = QPainter(obj)
                painter.setFont(obj.font())
                selected = self.buttons.get(self._selected) is obj
                painter.setPen(QColor('#666' if not obj.isEnabled() else RECESSED_BG if selected else '#AAA'))
                painter.drawText(obj.rect(), Qt.AlignmentFlag.AlignCenter, obj.text())
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                obj.setDown(True)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                pressed = obj.isDown()
                obj.setDown(False)
                if pressed and obj.rect().contains(event.position().toPoint()):
                    obj.click()
                return True
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.EnabledChange):
            self._place_thumb()
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_buttons()
        self._place_thumb()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_buttons()
        self._place_thumb()

    def _fit_buttons(self):
        available = max(0, self.width() - 8)
        required = [button.fontMetrics().horizontalAdvance(button.text()) + 16 +
                    (button.iconSize().width() + 4 if not button.icon().isNull() else 0)
                    for button in self.buttons.values()]
        equal = available // max(1, len(required))
        extra = max(0, available - sum(required)) // max(1, len(required))
        for index, needed in enumerate(required):
            self.layout().setStretch(index, 1 if max(required, default=0) <= equal else needed + extra)


def segmented_row(row, buttons=None):
    """Replace a horizontal button row with one track, preserving each button object."""
    adopted = []
    while row.count():
        item = row.takeAt(0)
        if isinstance(item.widget(), (QPushButton, QRadioButton)):
            adopted.append(item.widget())
    control = SegmentedControl(buttons if buttons is not None else adopted)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addWidget(control)
    return control


_SCROLL_STYLE = f'''
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; border: none; }}
    QScrollBar::handle:vertical {{ background: #626262; min-height: 28px; border-radius: 4px; }}
    QScrollBar::handle:vertical:hover {{ background: #888888; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; border: none; }}
    QScrollBar::handle:horizontal {{ background: #626262; min-width: 28px; border-radius: 4px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
'''


class _DialogPresentation(QObject):
    """Keep dynamic styles consistent with the shell without altering widget behavior."""

    def __init__(self, dialog):
        super().__init__(dialog)
        self._styling = False
        dialog.installEventFilter(self)
        for widget in dialog.findChildren(QWidget):
            self.watch(widget)

    def watch(self, widget):
        if not isinstance(widget, QWidget) or widget.property('ui_presentation_watched'):
            return
        widget.setProperty('ui_presentation_watched', True)
        widget.installEventFilter(self)
        self.apply(widget)

    def apply(self, widget):
        if self._styling:
            return
        self._styling = True
        try:
            if isinstance(widget, QAbstractScrollArea):
                if isinstance(widget, QScrollArea) and widget.widget() and widget.widget().layout():
                    layout = widget.widget().layout()
                    margins = layout.contentsMargins()
                    if margins.right():
                        layout.setContentsMargins(margins.left(), margins.top(), 0, margins.bottom())
                if widget.viewportMargins().right() != SCROLL_GAP:
                    widget.setViewportMargins(0, 0, SCROLL_GAP, 0)
                for bar in (widget.verticalScrollBar(), widget.horizontalScrollBar()):
                    if bar.styleSheet() != _SCROLL_STYLE:
                        bar.setStyleSheet(_SCROLL_STYLE)
            style = widget.styleSheet()
            updated = style
            if isinstance(widget, QPushButton) and not widget.property('ui_color_sample'):
                # Recolor blue button surfaces, leaving action fields, previews and values alone.
                pattern = r'(QPushButton[^{}]*\{)([^{}]*)(\})'
                def amber_block(match):
                    body = match[2]
                    replaced = re.sub(r'(background(?:-color)?\s*:\s*)#(?:0C4A6E|0284C7|1976D2|2196F3|0078D7)\b',
                                      lambda color: color[1] + (AMBER_HOVER if ':hover' in match[1] else AMBER_BG), body,
                                      flags=re.IGNORECASE)
                    if replaced != body:
                        replaced = re.sub(r'(?<![-\w])(color\s*:\s*)(?:#FFF(?:FFF)?|white)\b',
                                          r'\1#202020', replaced, flags=re.IGNORECASE)
                    return match[1] + replaced + match[3]
                updated = re.sub(pattern, amber_block, style)
                if widget.property('ui_primary') and '/* ui_primary */' not in updated:
                    updated += f'\nQPushButton {{ background: {AMBER_BG}; color: {RECESSED_BG}; }} QPushButton:hover {{ background: {AMBER_HOVER}; color: {RECESSED_BG}; }} QPushButton:disabled {{ background: {CONTROL_BG}; color: #888; }}\n/* ui_primary */'
            if isinstance(widget, (QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
                selector = type(widget).__name__
                if '/* ui_input */' not in updated:
                    updated += f'\n{selector}, {selector}:disabled {{ background: {RECESSED_BG}; }}\n/* ui_input */'
            if widget.property('ui_input_surface') and '/* ui_input_surface */' not in updated:
                updated += f'\nQPushButton {{ background: {RECESSED_BG}; }}\n/* ui_input_surface */'
            if updated != style:
                widget.setStyleSheet(updated)
        finally:
            self._styling = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ChildPolished:
            self.watch(event.child())
        if event.type() == QEvent.Type.DynamicPropertyChange and bytes(event.propertyName()) in (
                b'ui_primary', b'ui_input_surface', b'ui_color_sample'):
            self.apply(obj)
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.Show, QEvent.Type.Resize):
            self.apply(obj)
        return False


def ui_text(chinese, english):
    return chinese if get_lang().startswith('zh') else english


def section_heading(chinese, english, parent=None):
    label = QLabel(ui_text(chinese, english), parent)
    label.setStyleSheet('color: #E0E0E0; background: transparent; font-size: 14px; font-weight: 600;')
    label.setContentsMargins(0, 0, 0, 10)
    return label


def guide_label(chinese, english):
    label = QLabel(ui_text(chinese, english))
    label.setWordWrap(True)
    label.setStyleSheet('color: #AAAAAA; background: transparent; font-size: 13px;')
    return label


def scroll_widget(widget):
    scroll = QScrollArea()
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(widget)
    scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
    return scroll


def dialog_size(dialog, preferred):
    screen = dialog.parentWidget().screen() if dialog.parentWidget() else QApplication.primaryScreen()
    available = screen.availableGeometry()
    return min(preferred[0], available.width() - 64), min(preferred[1], available.height() - 64)


def _remove_widget(layout, widget):
    """Remove an action from its original layout without destroying it or its signals."""
    for index in range(layout.count() - 1, -1, -1):
        item = layout.itemAt(index)
        if item.widget() is widget:
            layout.takeAt(index)
            return True
        if item.layout() and _remove_widget(item.layout(), widget):
            return True
        child = item.widget()
        if child and child.layout() and _remove_widget(child.layout(), widget):
            return True
    return False


class _ActionVisibility(QObject):
    """Keep relocated actions tied to their original page / selected-item scope."""

    def __init__(self, scope, buttons, disable=False):
        super().__init__(scope)
        self.scope, self.buttons, self.disable = scope, buttons, disable
        scope.installEventFilter(self)

    def sync(self):
        visible = self.scope.isVisible()
        for button in self.buttons:
            if self.disable:
                button.setEnabled(visible)
            else:
                button.setVisible(visible)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            self.sync()
        return False


def finish_dialog(dialog, size, actions=(), guidance=None, columns=False,
                  scope=None, scope_actions=(), page_actions=None):
    """Adopt an existing root into fixed header / scrolling body / one-row footer.

    `actions` are existing button texts or button objects, in their intended order.
    Multi-column editors retain their individual scroll areas; only columns that
    do not yet scroll get a wrapper. No business callbacks are added here.
    """
    container = next((f for f in dialog.findChildren(QFrame)
                      if f.objectName().endswith('_container')), None)
    if container is None:
        return
    root = container.layout()
    if root is None or not root.count():
        return
    dialog._shadow_installed = True  # This shell owns its border and screen budget.
    dialog._ui_shell = True
    container.setStyleSheet(container.styleSheet() + f'''
        QFrame#{container.objectName()} {{ background: {PANEL_BG}; border: 1px solid #555; border-radius: {OUTER_RADIUS}px; }}
        QScrollBar:vertical {{ background: #2D2D2D; width: 8px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: #626262; min-height: 28px; border-radius: 4px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    ''')
    dialog.setFixedSize(*dialog_size(dialog, size))

    action_buttons = []
    action_hidden = {}
    for action in actions:
        candidates = ([action] if isinstance(action, QPushButton) else
                      [b for b in dialog.findChildren(QPushButton) if b.text() == action])
        for button in candidates:
            if button not in action_buttons:
                action_hidden[button] = button.isHidden()
                _remove_widget(root, button)
                action_buttons.append(button)

    # Empty action layouts left by relocation must not consume body height.
    def compact(layout):
        for index in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(index)
            child = item.layout()
            if child:
                compact(child)
                if not child.count() or all(child.itemAt(i).spacerItem() for i in range(child.count())):
                    layout.takeAt(index)
            elif item.widget() and item.widget().layout():
                compact(item.widget().layout())
    compact(root)

    items = []
    while root.count():
        items.append(root.takeAt(0))
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    header = QFrame(container)
    header.setObjectName('ui_titlebar')
    header.setFixedHeight(64)
    header.setStyleSheet(f'QFrame#ui_titlebar {{ background: {PANEL_BG}; border: none; border-bottom: 1px solid #444; border-top-left-radius: {OUTER_RADIUS}px; border-top-right-radius: {OUTER_RADIUS}px; }}')
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(24, 0, 24, 0)
    marker = QLabel('▏', header)
    marker.setStyleSheet('color: #F59E0B; font-size: 24px; background: transparent;')
    header_layout.addWidget(marker)
    first = items.pop(0)
    if first.layout():
        header_layout.addLayout(first.layout(), 1)
    elif first.widget():
        header_layout.addWidget(first.widget(), 1)
    close = next((b for b in header.findChildren(QPushButton)), None)
    if close:
        close.setFixedSize(40, 40)
        close.setToolTip(ui_text('关闭', 'Close'))
        close.setStyleSheet(f'QPushButton {{ background: {CONTROL_BG}; color: #CCC; border: none; border-radius: {INNER_RADIUS}px; }} QPushButton:hover {{ background: #6E1E1E; color: white; }}')
    else:
        close = QPushButton('×', header)
        close.setFixedSize(40, 40)
        close.clicked.connect(dialog.close)
        close.setStyleSheet(f'QPushButton {{ background: {CONTROL_BG}; color: #CCC; border: none; border-radius: {INNER_RADIUS}px; }} QPushButton:hover {{ background: #6E1E1E; }}')
        header_layout.addWidget(close)
    root.addWidget(header)

    body = QWidget(container)
    body.setStyleSheet('background: transparent;')
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(24, 16, 24, 16)
    body_layout.setSpacing(8)
    expanding_layout = next((item.layout() for item in reversed(items) if item.layout()), None)
    for item in items:
        if item.layout():
            body_layout.addLayout(item.layout(), 1 if columns and item.layout() is expanding_layout else 0)
        elif item.widget():
            body_layout.addWidget(item.widget(), 1 if isinstance(item.widget(), QScrollArea) else 0)
        else:
            body_layout.addItem(item)
    if columns:
        # Keep each pane independent, including page forms that used to be fixed.
        for item in items:
            if item.layout() is not expanding_layout:
                continue
            lay = item.layout()
            for index in range(lay.count()):
                child = lay.itemAt(index).widget()
                if child and child.layout() and not isinstance(child, QScrollArea):
                    if child.findChild(QScrollArea) is None:
                        lay.takeAt(index)
                        pane_width = child.minimumWidth() if child.minimumWidth() == child.maximumWidth() else None
                        if pane_width:
                            child.setMinimumWidth(0)
                            child.setMaximumWidth(16777215)
                        sc = scroll_widget(child)
                        if pane_width:
                            sc.setFixedWidth(pane_width)
                        lay.insertWidget(index, sc, 0 if pane_width else 1)
        root.addWidget(body, 1)
    else:
        # Logs keep their own scroll area so the waveform/status remain stationary.
        root.addWidget(body if body.findChild(QScrollArea) else scroll_widget(body), 1)

    footer = QFrame(container)
    footer.setObjectName('ui_actionbar')
    footer.setFixedHeight(72)
    footer.setStyleSheet(f'QFrame#ui_actionbar {{ background: {PANEL_BG}; border: none; border-top: 1px solid #444; border-bottom-left-radius: {OUTER_RADIUS}px; border-bottom-right-radius: {OUTER_RADIUS}px; }}')
    footer_layout = QHBoxLayout(footer)
    footer_layout.setContentsMargins(24, 16, 24, 16)
    footer_layout.setSpacing(10)
    dialog._ui_guidance = None
    if guidance:
        hint = guide_label(*guidance)
        hint.setStyleSheet('color: #CCCCCC; background: transparent; font-size: 15px;')
        hint.setMinimumWidth(0)
        hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        footer_layout.addWidget(hint, 1)
        dialog._ui_guidance = hint
    else:
        footer_layout.addStretch()
    for button in action_buttons:
        button.setFixedHeight(40)
        button.setMinimumWidth(max(96, button.fontMetrics().horizontalAdvance(button.text()) + 32))
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        footer_layout.addWidget(button)
        # Keep original state-driven visibility (update/install dialogs).
        if not action_hidden[button]:
            button.show()
    root.addWidget(footer)
    dialog._ui_header, dialog._ui_body, dialog._ui_footer = header, body, footer
    dialog._ui_actions = action_buttons
    for button in action_buttons:
        font = QFont(get_font())
        font.setPixelSize(14)
        font.setBold(button is action_buttons[-1])
        button.setFont(font)
        if not button.text() and button.layout():
            for label in button.findChildren(QLabel):
                if label.text() and not any(0xE000 <= ord(c) <= 0xF8FF for c in label.text()):
                    label.setFont(font)
    for label in header.findChildren(QLabel):
        if label is not marker and not any(0xE000 <= ord(c) <= 0xF8FF for c in label.text()):
            font = QFont(get_font())
            font.setPixelSize(20)
            font.setBold(True)
            label.setFont(font)
    dialog._ui_action_filters = []
    if scope:
        scoped = [b for b in action_buttons if b.text() in scope_actions]
        binding = _ActionVisibility(scope, scoped, disable=True)
        dialog._ui_action_filters.append(binding)
        binding.sync()
    for page, buttons in (page_actions or []):
        binding = _ActionVisibility(page, buttons)
        dialog._ui_action_filters.append(binding)
        binding.sync()

    # Confirmation uses the brand accent; secondary, delete and cancel stay distinct.
    from core.i18n import t
    confirmation_labels = {'保存', '确定', '确认', '复制确认', '应用此方案'}
    confirmation_labels.update(t(key) for key in (
        'dialog.confirm', 'dialog.yes', 'editor.save', 'macro.save', 'voice_dialog.save',
        'key_remap.save', 'wheel_style.save', 'gp_stick_editor.save', 'gp_wheel_editor.save',
    ))
    for button in action_buttons:
        if button.text() in confirmation_labels or button is getattr(dialog, '_save_btn', None):
            button.setProperty('ui_primary', True)
    dialog._ui_presentation = _DialogPresentation(dialog)

    return close


def target_hint(dialog, palette_layout, fields):
    """Explain the existing focused field without adding a new selection step."""
    hint = QLabel(ui_text('先点击左侧字段，再选择这里的动作',
                         'Select a field on the left, then choose an action here.'))
    hint.setWordWrap(True)
    hint.setStyleSheet('color: #AAA; font-size: 13px; background: transparent;')
    palette_layout.insertWidget(0, hint)
    for key, widget in fields.items():
        if not hasattr(widget, 'focusChanged'):
            continue
        def update(focused, field=key):
            if focused:
                from core.constants import ACTION_COLORS
                from core.i18n import t
                label = t('editor.' + ('hover_toggle_label' if field == 'hover_toggle' else field))
                if label.startswith('editor.'):
                    label = field
                color = ACTION_COLORS.get(field, '#F59E0B')
                hint.setText(ui_text('正在填写：', 'Editing: ') + label)
                hint.setStyleSheet(f'color: {color}; font-size: 13px; background: transparent;')
        widget.focusChanged.connect(update)
    dialog._ui_target_hint = hint
