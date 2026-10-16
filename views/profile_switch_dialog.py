"""All input mappings on the left; profile candidates and cycle order on the right."""

from copy import deepcopy

from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from core.constants import ACTION_COLORS
from core.i18n import t, get_font
from core.profile_switch import TRIGGER_FIELDS
from views.ui_components import (CONTROL_BG, RECESSED_BG, SegmentedControl,
                                  finish_dialog, scroll_widget, section_heading)

PURPLE = '#7C3AED'
PURPLE_HOVER = '#6D28D9'


class _ProfileTags(QWidget):
    """Wrapping profile chips, preserving full names including '+' characters."""

    activated = pyqtSignal()
    profilesChanged = pyqtSignal(object)

    def __init__(self, profiles, cycle=False, available=(), parent=None):
        super().__init__(parent)
        self.profiles = list(profiles)
        self._cycle = cycle
        self._available = set(available)
        self._selected = False
        self._tag_font = QFont(get_font())
        self._tag_font.setPixelSize(12)
        self._tag_font.setBold(True)
        self.setMinimumWidth(100)
        self.setFixedHeight(42)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_profiles(self, profiles):
        names = list(dict.fromkeys(profiles))
        if self.profiles != names:
            self.profiles = names
            self._refresh_geometry()
            self.profilesChanged.emit(list(names))

    def set_cycle(self, cycle):
        self._cycle = cycle
        self._refresh_geometry()

    def set_selected(self, selected):
        self._selected = selected
        self.update()

    def _layout_chips(self):
        metrics = QFontMetrics(self._tag_font)
        limit = max(40, self.width() - 12)
        x, y = 6, 7
        chips = []
        for index, name in enumerate(self.profiles):
            label = f'{index + 1} {name}' if self._cycle else name
            label = metrics.elidedText(label, Qt.TextElideMode.ElideRight, max(10, limit - 32))
            width = min(limit, metrics.horizontalAdvance(label) + 32)
            if x > 6 and x + width > self.width() - 6:
                x, y = 6, y + 32
            rect = QRect(x, y, width, 28)
            chips.append((name, label, rect, QRect(rect.right() - 21, y, 22, 28)))
            x += width + 4
        return chips, max(42, y + 35)

    def _refresh_geometry(self):
        _, height = self._layout_chips()
        if self.height() != height:
            self.setFixedHeight(height)
        self.setToolTip(' → '.join(self.profiles) if self.profiles else t('profile_switch.field_hint'))
        self.update()

    def resizeEvent(self, event):
        self._refresh_geometry()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(RECESSED_BG))
        painter.setPen(QPen(QColor(PURPLE if self._selected else '#555555'), 2 if self._selected else 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        painter.setFont(self._tag_font)
        chips, _ = self._layout_chips()
        if not chips:
            painter.setPen(QColor('#888888'))
            painter.drawText(self.rect().adjusted(10, 0, -8, 0),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             t('profile_switch.unset'))
        for name, label, rect, close in chips:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(PURPLE if name in self._available else '#8B2020'))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor('#FFFFFF'))
            painter.drawText(rect.adjusted(6, 0, -24, 0),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            painter.drawText(close, Qt.AlignmentFlag.AlignCenter, '×')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.activated.emit()
            for name, _, _, close in self._layout_chips()[0]:
                if close.contains(event.position().toPoint()):
                    self.set_profiles([p for p in self.profiles if p != name])
                    break
        event.accept()

    def focusInEvent(self, event):
        self.activated.emit()
        super().focusInEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and self.profiles:
            self.set_profiles(self.profiles[:-1])
            event.accept()
        else:
            super().keyPressEvent(event)


class _ProfileCandidate(QPushButton):
    """Neutral profile choice with an elided label and full-name tooltip."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.profile_name = name
        self.setFixedHeight(40)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.set_selected(False)

    def set_selected(self, selected):
        self._selected = selected
        self.setStyleSheet(f'QPushButton {{ background: {CONTROL_BG}; color: #E0E0E0; '
                          f'border: 1px solid {PURPLE if selected else CONTROL_BG}; '
                          'border-radius: 6px; text-align: left; padding: 0 12px; } '
                          'QPushButton:hover { background: #505050; border-color: #A78BFA; }')
        self._elide()

    def _elide(self):
        label = ('✓  ' if self._selected else '') + self.profile_name
        # Escape '&' so profile names are not shown as mnemonic shortcuts.
        self.setText(self.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight,
                                                  max(0, self.width() - 26)).replace('&', '&&'))

    def resizeEvent(self, event):
        self._elide()
        super().resizeEvent(event)


class ProfileSwitchDialog(QDialog):
    saved = pyqtSignal(object)
    deleted = pyqtSignal(object)
    copied = pyqtSignal(object)

    def __init__(self, item, parent=None, profiles=None):
        super().__init__(parent)
        self._item = item
        self._profiles = list(dict.fromkeys(profiles or []))
        self._actions = {key: deepcopy(item.data.profile_actions.get(key,
                         {'mode': 'fixed', 'profiles': []})) for key in TRIGGER_FIELDS}
        self._current_trigger = 'hover'
        self._fields, self._mode_buttons, self._mode_controls = {}, {}, {}
        self._cycle_rows = []
        self._drag_pos = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet('QLabel { color: #DDDDDD; background: transparent; } '
                          'QLineEdit { background: #202020; color: white; border: 1px solid #555; '
                          'border-radius: 6px; padding: 4px 8px; } '
                          'QLineEdit:focus { border: 1px solid #7C3AED; } '
                          'QPushButton { background: #3A3A3A; color: white; border: none; '
                          'border-radius: 6px; padding: 0 8px; } '
                          'QPushButton:hover { background: #505050; }')
        font = QFont(get_font())
        font.setPixelSize(14)
        self.setFont(font)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setObjectName('switch_container')
        outer.addWidget(container)
        root = QVBoxLayout(container)
        header = QHBoxLayout()
        header.addWidget(QLabel(t('profile_switch.title')))
        header.addStretch()
        from views import edit_toolbar
        edit_toolbar._detect_icon_font()
        icon_font = edit_toolbar._ICON_FONT
        close = QPushButton('\uE711' if icon_font else '\u2715')
        close_font = QFont(icon_font or get_font())
        close_font.setPixelSize(20 if icon_font else 18)
        close_font.setBold(not bool(icon_font))
        close.setFont(close_font)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(40, 40)
        close.clicked.connect(self.reject)
        header.addWidget(close)
        root.addLayout(header)
        columns = QHBoxLayout()
        columns.setSpacing(16)
        self._left_scroll = self._build_left()
        columns.addWidget(self._left_scroll)
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet('background: #444444;')
        columns.addWidget(divider)
        self._right_pane = self._build_right()
        columns.addWidget(self._right_pane, 1)
        root.addLayout(columns, 1)
        footer = QHBoxLayout()
        actions = []
        for key, callback in [('copy', self._copy), ('delete', self._delete), ('save', self._save)]:
            button = QPushButton(t('editor.' + key))
            button.clicked.connect(callback)
            footer.addWidget(button)
            actions.append(button)
            if key == 'save':
                self._save_btn = button
        root.addLayout(footer)
        finish_dialog(self, (960, 700), actions=actions, columns=True,
                      guidance=(t('profile_switch.guidance'), t('profile_switch.guidance')),
                      accent=(PURPLE, PURPLE_HOVER, '#FFFFFF'))
        self._left_scroll.setFixedWidth(min(500, max(340, int((self.width() - 81) * .56))))
        self._update_hover_controls()
        self._activate_field('hover')
        screen = self.screen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def _build_left(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(QLabel(t('editor.name')))
        self._name = QLineEdit(self._item.data.name)
        self._name.setFixedHeight(38)
        name_row.addWidget(self._name, 1)
        layout.addLayout(name_row)
        layout.addSpacing(6)
        shared = QLabel(t('profile_switch.shared_hint'))
        shared.setWordWrap(True)
        shared.setStyleSheet('color: #AAAAAA; font-size: 13px;')
        layout.addWidget(shared)
        layout.addSpacing(12)
        layout.addWidget(section_heading(t('profile_switch.mappings'), t('profile_switch.mappings')))
        layout.addWidget(self._build_mapping('hover'))
        layout.addSpacing(4)
        delay_row = QHBoxLayout()
        delay_row.setSpacing(8)
        self._delay_label = QLabel(t('profile_switch.delay_short'))
        delay_row.addWidget(self._delay_label)
        self._delay_value = QLabel()
        self._delay_value.setStyleSheet(f'color: {PURPLE};')
        self._delay = QSlider(Qt.Orientation.Horizontal)
        self._delay.setRange(0, max(2000, self._item.data.hover_delay))
        self._delay.setSingleStep(50)
        self._delay.setFixedHeight(24)
        self._delay.setStyleSheet('QSlider::groove:horizontal { background: #202020; height: 6px; '
                                 'border-radius: 3px; } QSlider::sub-page:horizontal { background: #7C3AED; '
                                 'border-radius: 3px; } QSlider::handle:horizontal { background: #DDDDDD; '
                                 'border: none; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; } '
                                 'QSlider::sub-page:horizontal:disabled { background: #555555; } '
                                 'QSlider::handle:horizontal:disabled { background: #777777; }')
        self._delay.valueChanged.connect(lambda v: self._delay_value.setText(f'{v} ms'))
        self._delay.setValue(self._item.data.hover_delay)
        self._delay_value.setText(f'{self._item.data.hover_delay} ms')
        delay_row.addWidget(self._delay, 1)
        self._delay_value.setFixedWidth(66)
        self._delay_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        delay_row.addWidget(self._delay_value)
        layout.addLayout(delay_row)
        layout.addSpacing(10)
        for index, key in enumerate(('lclick', 'rclick', 'mclick', 'xbutton1', 'xbutton2', 'wheelup', 'wheeldown')):
            if index:
                layout.addSpacing(6)
            layout.addWidget(self._build_mapping(key))
        layout.addStretch()
        return scroll_widget(content)

    def _update_hover_controls(self):
        enabled = bool(self._actions['hover']['profiles'])
        hint = t('profile_switch.hover_hint' if enabled else 'profile_switch.hover_unset_hint')
        for widget in (self._delay, self._delay_label, self._delay_value):
            widget.setEnabled(enabled)
            widget.setToolTip(hint)
        self._delay_value.setStyleSheet(f'color: {PURPLE if enabled else "#777777"};')

    def _build_mapping(self, key):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        dot = QLabel('●')
        dot.setFixedSize(12, 42)
        dot.setStyleSheet(f'color: {ACTION_COLORS.get(key, PURPLE)}; font-size: 10px;')
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(t('editor.' + key))
        label_width = max(64, min(100, max(self.fontMetrics().horizontalAdvance(t('editor.' + field))
                                          for field in TRIGGER_FIELDS) + 1))
        label.setFixedSize(label_width, 42)
        label.setToolTip(label.text())
        row.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)
        buttons = {}
        for mode in ('fixed', 'cycle'):
            button = QPushButton(t('profile_switch.' + mode + '_short'))
            button.setToolTip(t('profile_switch.' + mode))
            button.setFixedHeight(32)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            font = QFont(self.font())
            font.setPixelSize(12)
            button.setFont(font)
            button.clicked.connect(lambda _, field=key, picked=mode: self._set_mode(field, picked))
            buttons[mode] = button
        control = SegmentedControl(buttons)
        control.setFixedWidth(116)
        control.set_accent(PURPLE, '#FFFFFF')
        control.set_selected(self._actions[key]['mode'])
        self._mode_controls[key], self._mode_buttons[key] = control, buttons
        row.addWidget(control, 0, Qt.AlignmentFlag.AlignTop)
        field = _ProfileTags(self._actions[key]['profiles'],
                             cycle=self._actions[key]['mode'] == 'cycle', available=self._profiles)
        field.activated.connect(lambda field=key: self._activate_field(field))
        field.profilesChanged.connect(lambda profiles, field=key: self._on_profiles_changed(field, profiles))
        self._fields[key] = field
        row.addWidget(field, 1)
        return widget

    def _build_right(self):
        pane = QWidget()
        pane.setMinimumWidth(0)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(section_heading('用户方案', 'User profiles'))
        self._target_hint = QLabel()
        self._target_hint.setWordWrap(True)
        self._target_hint.setStyleSheet('color: #A78BFA; font-size: 14px;')
        layout.addWidget(self._target_hint)
        self._mode_hint = QLabel()
        self._mode_hint.setWordWrap(True)
        self._mode_hint.setStyleSheet('color: #AAAAAA; font-size: 13px;')
        layout.addWidget(self._mode_hint)
        content = QWidget()
        choices = QVBoxLayout(content)
        choices.setContentsMargins(0, 0, 0, 0)
        choices.setSpacing(8)
        self._profile_buttons = {}
        profile_grid = QGridLayout()
        profile_grid.setSpacing(8)
        profile_grid.setColumnStretch(0, 1)
        profile_grid.setColumnStretch(1, 1)
        for index, profile in enumerate(self._profiles):
            button = _ProfileCandidate(profile)
            button.clicked.connect(lambda _, name=profile: self._add_profile(name))
            self._profile_buttons[profile] = button
            profile_grid.addWidget(button, index // 2, index % 2)
        choices.addLayout(profile_grid)
        if not self._profiles:
            empty = QLabel(t('profile_switch.no_profiles'))
            empty.setWordWrap(True)
            choices.addWidget(empty)
        self._cycle_panel = QWidget()
        cycle = QVBoxLayout(self._cycle_panel)
        cycle.setContentsMargins(0, 12, 0, 0)
        cycle.setSpacing(8)
        cycle.addWidget(section_heading(t('profile_switch.order'), t('profile_switch.order')))
        self._cycle_layout = QVBoxLayout()
        self._cycle_layout.setSpacing(8)
        cycle.addLayout(self._cycle_layout)
        choices.addWidget(self._cycle_panel)
        choices.addStretch()
        self._right_scroll = scroll_widget(content)
        layout.addWidget(self._right_scroll, 1)
        self._error = QLabel()
        self._error.setWordWrap(True)
        self._error.setStyleSheet('color: #FCA5A5; font-size: 13px;')
        self._error.hide()
        layout.addWidget(self._error)
        return pane

    def _activate_field(self, key):
        self._current_trigger = key
        for name, field in self._fields.items():
            field.set_selected(name == key)
        self._error.hide()
        self._refresh_palette()

    def _set_mode(self, key, mode):
        self._actions[key]['mode'] = mode
        self._mode_controls[key].set_selected(mode)
        self._fields[key].set_cycle(mode == 'cycle')
        if mode == 'fixed':
            self._fields[key].set_profiles(self._fields[key].profiles[:1])
        self._activate_field(key)

    def _on_profiles_changed(self, key, profiles):
        self._actions[key]['profiles'] = list(profiles)
        if key == 'hover':
            self._update_hover_controls()
        if key == self._current_trigger:
            self._refresh_palette()

    def _add_profile(self, name):
        if name not in self._profiles:
            return
        key = self._current_trigger
        profiles = self._fields[key].profiles
        if self._actions[key]['mode'] == 'fixed':
            self._fields[key].set_profiles([name])
        elif name not in profiles:
            self._fields[key].set_profiles(profiles + [name])

    def _remove_profile(self, name):
        field = self._fields[self._current_trigger]
        field.set_profiles([p for p in field.profiles if p != name])

    def _move_profile(self, index, delta):
        field = self._fields[self._current_trigger]
        profiles = list(field.profiles)
        target = index + delta
        if 0 <= index < len(profiles) and 0 <= target < len(profiles):
            profiles.insert(target, profiles.pop(index))
            field.set_profiles(profiles)

    def _refresh_palette(self):
        key = self._current_trigger
        action = self._actions[key]
        self._target_hint.setText(t('profile_switch.editing',
                                   trigger=t('editor.' + key), mode=t('profile_switch.' + action['mode'])))
        self._mode_hint.setText(t('profile_switch.' + action['mode'] + '_hint'))
        for name, button in self._profile_buttons.items():
            button.set_selected(name in action['profiles'])
        self._cycle_panel.setVisible(action['mode'] == 'cycle')
        while self._cycle_layout.count():
            widget = self._cycle_layout.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._cycle_rows = []
        for index, name in enumerate(action['profiles']):
            widget = QWidget()
            row = QHBoxLayout(widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            number = QLabel(str(index + 1))
            number.setFixedWidth(20)
            number.setStyleSheet('color: #A78BFA;')
            row.addWidget(number)
            label = QLabel(name)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setToolTip(name)
            row.addWidget(label, 1)
            buttons = {}
            for symbol, text, callback, enabled in (
                    ('↑', 'up', lambda _, i=index: self._move_profile(i, -1), index > 0),
                    ('↓', 'down', lambda _, i=index: self._move_profile(i, 1), index < len(action['profiles']) - 1),
                    ('×', 'remove', lambda _, profile=name: self._remove_profile(profile), True)):
                button = QPushButton(symbol)
                button.setToolTip(t('profile_switch.' + text))
                button.setFixedSize(32, 32)
                button.setStyleSheet('QPushButton { background: #3A3A3A; color: #DDDDDD; '
                                    'border: none; border-radius: 6px; } '
                                    'QPushButton:hover { background: #505050; } '
                                    'QPushButton:disabled { color: #666666; background: #333333; }')
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setEnabled(enabled)
                button.clicked.connect(callback)
                row.addWidget(button)
                buttons[text] = button
            self._cycle_layout.addWidget(widget)
            self._cycle_rows.append(buttons)
        if not action['profiles']:
            empty = QLabel(t('profile_switch.cycle_empty'))
            empty.setWordWrap(True)
            empty.setStyleSheet('color: #888888; font-size: 13px;')
            self._cycle_layout.addWidget(empty)

    def _save(self):
        actions = {key: deepcopy(action) for key, action in self._actions.items() if action['profiles']}
        for key, action in actions.items():
            if any(profile not in self._profiles for profile in action['profiles']):
                self._activate_field(key)
                self._left_scroll.ensureWidgetVisible(self._fields[key])
                self._error.setText(t('profile_switch.missing'))
                self._error.show()
                return
        self._item.data.name = self._name.text().strip() or t('profile_switch.name')
        self._item.data.profile_actions = actions
        self._item.data.hover_delay = self._delay.value()
        self._item.data.__post_init__()
        self._item._hover_sm.update_config('trigger', self._delay.value(), 0, 0)
        self.saved.emit(self._item)
        self.accept()

    def _copy(self):
        self.copied.emit(self._item)
        self.accept()

    def _delete(self):
        self.deleted.emit(self._item)
        self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
