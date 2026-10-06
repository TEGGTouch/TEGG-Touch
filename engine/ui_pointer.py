"""Application-owned adaptive pointer and Qt-only virtual mouse dispatch.

Native input is unchanged in system mode. In independent mode a dedicated
QPointingDevice identifies queued events, so native centre-position events
cannot double-fire controls. Posting (not synchronously sending) mouse events
also lets modal dialog event loops keep receiving pointer updates.
"""

import ctypes
import time

from PyQt6 import sip
from PyQt6.QtCore import QObject, QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import (QCursor, QEnterEvent, QHoverEvent, QInputDevice,
                         QMouseEvent, QPointingDevice, QWheelEvent)
from PyQt6.QtWidgets import QApplication, QAbstractButton, QGraphicsView, QWidget

from core.constants import UPDATE_INTERVAL
from core.input_engine import poll_wheel_events
from views.pointer_overlay import PointerOverlay

_api = ctypes.WinDLL('user32')
_api.GetAsyncKeyState.argtypes = [ctypes.c_int]
_api.GetAsyncKeyState.restype = ctypes.c_short
_BUTTONS = ((Qt.MouseButton.LeftButton, 1), (Qt.MouseButton.RightButton, 2),
            (Qt.MouseButton.MiddleButton, 4), (Qt.MouseButton.BackButton, 5),
            (Qt.MouseButton.ForwardButton, 6))
_MOUSE_EVENTS = {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
                 QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick,
                 QEvent.Type.Wheel, QEvent.Type.Enter, QEvent.Type.Leave,
                 QEvent.Type.HoverEnter, QEvent.Type.HoverLeave, QEvent.Type.HoverMove}


def alive(widget):
    return widget is not None and not sip.isdeleted(widget)


class VirtualMouseEvent(QMouseEvent):
    pass


class VirtualWheelEvent(QWheelEvent):
    pass


class UiPointerController(QObject):
    def __init__(self, window, source, run_controller, cursor_item):
        super().__init__(window)
        self.window, self.source, self.run = window, source, run_controller
        self.cursor_item = cursor_item
        self.layer = PointerOverlay(window, cursor_item)
        self.device = QPointingDevice('TEGG logical pointer', 0x54454747,
            QInputDevice.DeviceType.Mouse, QPointingDevice.PointerType.Generic,
            QInputDevice.Capability.Position, 1, 5, parent=self)
        self.timer = QTimer(self)
        self.timer.setInterval(UPDATE_INTERVAL)
        self.timer.timeout.connect(self.tick)
        self._started = False
        self._generation = 0
        self._buttons = Qt.MouseButton.NoButton
        self._ignored = Qt.MouseButton.NoButton
        self._capture = None
        self._hover = None
        self._last_position = None
        self._last_click = None
        self._independent = False
        self._drawn = False
        self._hover_dispatch = False
        self._stack = {}
        self._stack_serial = 0
        self._native_dialogs_disabled = False
        QApplication.instance().installEventFilter(self)

    @staticmethod
    def read_buttons():
        result = Qt.MouseButton.NoButton
        for button, vk in _BUTTONS:
            if _api.GetAsyncKeyState(vk) & 0x8000:
                result |= button
        return result

    @staticmethod
    def modifiers():
        result = Qt.KeyboardModifier.NoModifier
        for modifier, vk in ((Qt.KeyboardModifier.ShiftModifier, 0x10),
                             (Qt.KeyboardModifier.ControlModifier, 0x11),
                             (Qt.KeyboardModifier.AltModifier, 0x12),
                             (Qt.KeyboardModifier.MetaModifier, 0x5B)):
            if _api.GetAsyncKeyState(vk) & 0x8000:
                result |= modifier
        return result

    def owns(self, widget):
        if not isinstance(widget, QWidget) or not alive(widget):
            return False
        while widget is not None:
            if widget is self.window:
                return True
            widget = widget.parentWidget()
        return False

    def start(self):
        if self._started:
            return
        self._started = True
        self.source.start(QRect(self.window.mapToGlobal(QPoint()), self.window.size()))
        self._buttons = self.read_buttons()
        self._ignored = self._buttons
        self.timer.start()

    def stop(self):
        self.timer.stop()
        self._started = False
        self.cancel()
        self.source.stop()
        self._set_independent(False)
        self.layer.hide()

    def set_drawn(self, enabled):
        self._drawn = enabled
        self.update_display()

    def _set_independent(self, enabled):
        if enabled == self._independent:
            return
        self._independent = enabled
        if enabled:
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.BlankCursor))
            attr = Qt.ApplicationAttribute.AA_DontUseNativeDialogs
            self._native_dialogs_disabled = not QApplication.testAttribute(attr)
            QApplication.setAttribute(attr, True)
        else:
            QApplication.restoreOverrideCursor()
            if self._native_dialogs_disabled:
                QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, False)
                self._native_dialogs_disabled = False

    def _view_for(self, widget):
        while alive(widget):
            if isinstance(widget, QGraphicsView):
                return widget
            widget = widget.parentWidget()
        return None

    def cancel(self):
        """Cancel a gesture without turning a held button into a click."""
        self._generation += 1
        target = self._capture
        if alive(target):
            current = target
            while current is not None:
                if isinstance(current, QAbstractButton):
                    current.setDown(False)
                if hasattr(current, '_drag_pos'):
                    current._drag_pos = None
                current = current.parentWidget()
            view = self._view_for(target)
            if view and view.scene() and view.scene().mouseGrabberItem():
                view.scene().mouseGrabberItem().ungrabMouse()
            for button, _ in _BUTTONS:
                if self._buttons & button:
                    self._post_mouse(target, QEvent.Type.MouseButtonRelease,
                                     self.source.position(), button, Qt.MouseButton.NoButton)
        self._capture = None
        self._set_hover(None, self.source.position())
        self._buttons = self.read_buttons()
        self._ignored = self._buttons
        self._last_click = None
        self._last_position = None

    def _eligible(self, widget):
        return (self.owns(widget) and widget is not self.layer and widget.isVisible()
                and not widget.isMinimized()
                and not widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                and not widget.windowFlags() & Qt.WindowType.WindowTransparentForInput
                and widget.windowType() != Qt.WindowType.ToolTip)

    def hit_target(self, position):
        """Resolve our frontmost widget using logical coordinates, not widgetAt()."""
        windows = [w for w in QApplication.topLevelWidgets() if self._eligible(w)]
        modal = QApplication.activeModalWidget()
        if modal is not None and self.owns(modal):
            windows = [w for w in windows if w is modal or modal.isAncestorOf(w)]
        else:
            modal = None
        popup = QApplication.activePopupWidget()
        if (popup is not None and self._eligible(popup)
                and not popup.rect().contains(popup.mapFromGlobal(position))):
            # Match native popup semantics: an outside click dismisses the
            # popup, rather than activating a control underneath it.
            return popup, True
        windows.sort(key=lambda w: (w is popup, w is not self.window,
                                    self._stack.get(id(w), 0)), reverse=True)
        for window in windows:
            local = window.mapFromGlobal(position)
            if not window.rect().contains(local):
                continue
            if not window.mask().isEmpty() and not window.mask().contains(local):
                continue
            target = window.childAt(local) or window
            if window is self.window:
                return (self.window.viewport() if self.window._current_mode == 'edit' else None), False
            return target, True
        # A modal UI still owns clicks outside its rectangle.
        return None, modal is not None

    def _post_mouse(self, target, kind, position, button, buttons):
        if not alive(target):
            return
        event = VirtualMouseEvent(kind, QPointF(target.mapFromGlobal(position)),
            QPointF(target.window().mapFromGlobal(position)), QPointF(position),
            button, buttons, self.modifiers(), self.device)
        event.generation = self._generation
        QApplication.postEvent(target, event)

    def _post_wheel(self, target, position, delta):
        event = VirtualWheelEvent(QPointF(target.mapFromGlobal(position)), QPointF(position),
            QPoint(), QPoint(0, delta), self._buttons, self.modifiers(),
            Qt.ScrollPhase.NoScrollPhase, False,
            Qt.MouseEventSource.MouseEventSynthesizedByApplication, self.device)
        event.generation = self._generation
        QApplication.postEvent(target, event)

    def _hover_path(self, target):
        path = []
        while alive(target):
            path.append(target)
            if target.isWindow():
                break
            target = target.parentWidget()
        return path

    def _set_hover(self, target, position):
        if target is self._hover:
            return
        old_path, new_path = self._hover_path(self._hover), self._hover_path(target)
        self._hover = target
        self._hover_dispatch = True
        try:
            for widget in old_path:
                if widget in new_path:
                    continue
                widget.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
                QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))
                if widget.testAttribute(Qt.WidgetAttribute.WA_Hover):
                    local = QPointF(widget.mapFromGlobal(position))
                    QApplication.sendEvent(widget, QHoverEvent(QEvent.Type.HoverLeave,
                        local, QPointF(position), local, self.modifiers(), self.device))
            for widget in reversed(new_path):
                if widget in old_path:
                    continue
                widget.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
                local = QPointF(widget.mapFromGlobal(position))
                QApplication.sendEvent(widget, QEnterEvent(local,
                    QPointF(widget.window().mapFromGlobal(position)), QPointF(position), self.device))
                if widget.testAttribute(Qt.WidgetAttribute.WA_Hover):
                    QApplication.sendEvent(widget, QHoverEvent(QEvent.Type.HoverEnter,
                        local, QPointF(position), local, self.modifiers(), self.device))
        finally:
            self._hover_dispatch = False

    def cursor_for(self, target):
        if alive(target):
            view = self._view_for(target)
            if view and view.scene():
                local = view.mapFromGlobal(self.source.position())
                item = view.scene().itemAt(view.mapToScene(local), view.transform())
                while item is not None:
                    if item.hasCursor():
                        return item.cursor()
                    item = item.parentItem()
            cursor = target.cursor()
            if cursor.shape() != Qt.CursorShape.BlankCursor:
                return cursor
        return QCursor(Qt.CursorShape.ArrowCursor)

    def update_display(self, target=None, on_ui=False):
        if self.source.independent:
            self.cursor_item.stop_tracking()
            if self.window.isVisible() and not self.window.isMinimized() and (self._drawn or on_ui):
                self.layer.present(self.source.position(), self.cursor_for(target))
            else:
                self.layer.hide()
        else:
            self.layer.hide()
            if self._drawn and self.window.isVisible() and not self.window.isMinimized():
                if not self.cursor_item.isVisible():
                    self.cursor_item.start_tracking()
            else:
                self.cursor_item.stop_tracking()

    def tick(self):
        if not self.window.isVisible() or self.window.isMinimized():
            self.stop()
            return
        transition = self.source.poll()
        if transition or self.source.independent != self._independent:
            self.cancel()
            if self.run._active:
                self.run._reset_pointer_actions()
                poll_wheel_events()
        self._set_independent(self.source.independent)
        wheel = self.source.take_wheel_delta()
        if not self.source.independent:
            self.run.set_pointer_ui_active(False)
            self.update_display()
            return
        position = self.source.position()
        if self._capture is not None and (not alive(self._capture) or not self._capture.isVisible()):
            self.cancel()
        target, on_ui = self.hit_target(position)
        captured = alive(self._capture)
        receiver = self._capture if captured else target
        # Include the release frame: queued UI release must not hit the game mapping.
        self.run.set_pointer_ui_active(on_ui or captured)
        self._set_hover(receiver, position)
        buttons = self.read_buttons()
        self._ignored &= buttons
        buttons &= ~self._ignored
        if receiver is not None and receiver.isEnabled() and position != self._last_position:
            self._post_mouse(receiver, QEvent.Type.MouseMove, position,
                             Qt.MouseButton.NoButton, self._buttons)
        for button, _ in _BUTTONS:
            before, after = bool(self._buttons & button), bool(buttons & button)
            if before == after:
                continue
            if after:
                if self._capture is None and alive(target) and target.isEnabled():
                    self._capture = target
                receiver = self._capture
                kind = QEvent.Type.MouseButtonPress
                now = time.monotonic()
                last = self._last_click
                if (last and last[0] is receiver and last[1] == button
                        and (now - last[2]) * 1000 <= QApplication.doubleClickInterval()
                        and (position - last[3]).manhattanLength() <= QApplication.startDragDistance()):
                    kind = QEvent.Type.MouseButtonDblClick
                    self._last_click = None
                else:
                    self._last_click = receiver, button, now, QPoint(position)
                self._post_mouse(receiver, kind, position, button, buttons)
            elif alive(self._capture):
                self._post_mouse(self._capture, QEvent.Type.MouseButtonRelease, position, button, buttons)
        self._buttons = buttons
        if not buttons:
            self._capture = None
        if wheel and alive(receiver) and receiver.isEnabled():
            self._post_wheel(receiver, position, wheel)
        self._last_position = QPoint(position)
        self.update_display(receiver, on_ui or captured)

    def eventFilter(self, obj, event):
        if obj is self.layer or not self.owns(obj):
            return False
        kind = event.type()
        if kind in (QEvent.Type.Show, QEvent.Type.ZOrderChange, QEvent.Type.WindowActivate):
            if obj.isWindow():
                self._stack_serial += 1
                self._stack[id(obj)] = self._stack_serial
                self.layer.invalidate_stack()
        if kind in _MOUSE_EVENTS:
            virtual = hasattr(event, 'pointingDevice') and event.pointingDevice() is self.device
            if virtual:
                return getattr(event, 'generation', self._generation) != self._generation
            if self.source.independent and not self._hover_dispatch:
                return True
        return False
