"""Shared presentation for the desktop editor; existing widgets keep their callbacks."""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from core.i18n import get_font, get_lang

OUTER_RADIUS = 12
INNER_RADIUS = 6
CARD_RADIUS = 8


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
        QFrame#{container.objectName()} {{ background: #2D2D2D; border: 1px solid #555; border-radius: {OUTER_RADIUS}px; }}
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
    header.setStyleSheet(f'QFrame#ui_titlebar {{ background: #2D2D2D; border: none; border-bottom: 1px solid #444; border-top-left-radius: {OUTER_RADIUS}px; border-top-right-radius: {OUTER_RADIUS}px; }}')
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
        close.setStyleSheet('QPushButton { background: #3A3A3A; color: #CCC; border: none; border-radius: 6px; } QPushButton:hover { background: #6E1E1E; color: white; }')
    else:
        close = QPushButton('×', header)
        close.setFixedSize(40, 40)
        close.clicked.connect(dialog.close)
        close.setStyleSheet('QPushButton { background: #3A3A3A; color: #CCC; border: none; border-radius: 6px; } QPushButton:hover { background: #6E1E1E; }')
        header_layout.addWidget(close)
    root.addWidget(header)

    body = QWidget(container)
    body.setStyleSheet('background: transparent;')
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(24, 16, 24, 16)
    body_layout.setSpacing(8)
    if guidance:
        body_layout.addWidget(guide_label(*guidance))
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
    footer.setStyleSheet(f'QFrame#ui_actionbar {{ background: #2D2D2D; border: none; border-top: 1px solid #444; border-bottom-left-radius: {OUTER_RADIUS}px; border-bottom-right-radius: {OUTER_RADIUS}px; }}')
    footer_layout = QHBoxLayout(footer)
    footer_layout.setContentsMargins(24, 16, 24, 16)
    footer_layout.setSpacing(10)
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
