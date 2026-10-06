"""One input-transparent cursor window above the application's floating UI.

Used only for the independent pointer. The original system-cursor rendering
path is untouched. Stock hand/resize cursors are rendered, never installed or
moved at the OS level.
"""

import ctypes
import math
from ctypes import wintypes
from functools import lru_cache

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QCursor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget


_u = ctypes.WinDLL('user32', use_last_error=True)
_g = ctypes.WinDLL('gdi32', use_last_error=True)


class _IconInfo(ctypes.Structure):
    _fields_ = [('icon', wintypes.BOOL), ('x', wintypes.DWORD), ('y', wintypes.DWORD),
               ('mask', wintypes.HBITMAP), ('color', wintypes.HBITMAP)]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG),
               ('height', wintypes.LONG), ('planes', wintypes.WORD),
               ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
               ('image_size', wintypes.DWORD), ('xppm', wintypes.LONG),
               ('yppm', wintypes.LONG), ('used', wintypes.DWORD),
               ('important', wintypes.DWORD), ('colors', wintypes.DWORD * 3)]


_u.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
_u.LoadCursorW.restype = wintypes.HANDLE
_u.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_IconInfo)]
_u.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HANDLE,
                        ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
_g.CreateCompatibleDC.argtypes = [wintypes.HDC]
_g.CreateCompatibleDC.restype = wintypes.HDC
_g.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(_BitmapInfo), wintypes.UINT,
                              ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_g.CreateDIBSection.restype = wintypes.HBITMAP
_g.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
_g.SelectObject.restype = wintypes.HANDLE
_g.DeleteObject.argtypes = [wintypes.HANDLE]
_g.DeleteDC.argtypes = [wintypes.HDC]

_STOCK = {
    Qt.CursorShape.PointingHandCursor: 32649,
    Qt.CursorShape.IBeamCursor: 32513,
    Qt.CursorShape.CrossCursor: 32515,
    Qt.CursorShape.SizeVerCursor: 32645,
    Qt.CursorShape.SizeHorCursor: 32644,
    Qt.CursorShape.SizeBDiagCursor: 32643,
    Qt.CursorShape.SizeFDiagCursor: 32642,
    Qt.CursorShape.SizeAllCursor: 32646,
    Qt.CursorShape.ForbiddenCursor: 32648,
    Qt.CursorShape.WaitCursor: 32514,
    Qt.CursorShape.BusyCursor: 32650,
    Qt.CursorShape.OpenHandCursor: 32649,
    Qt.CursorShape.ClosedHandCursor: 32646,
}


@lru_cache(maxsize=24)
def stock_cursor(shape):
    """Render a shared Windows cursor to premultiplied RGBA, retaining hotspot."""
    resource = _STOCK.get(shape)
    if resource is None:
        return None
    handle = _u.LoadCursorW(None, resource)
    info = _IconInfo()
    if not handle or not _u.GetIconInfo(handle, ctypes.byref(info)):
        return None
    dc, bitmap, previous = None, None, None
    try:
        w, h = max(16, _u.GetSystemMetrics(13)), max(16, _u.GetSystemMetrics(14))
        header = _BitmapInfo()
        header.size, header.width, header.height = 40, w, -h
        header.planes, header.bits = 1, 32
        address = ctypes.c_void_p()
        dc = _g.CreateCompatibleDC(None)
        bitmap = _g.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(address), None, 0)
        if not dc or not bitmap or not address.value:
            return None
        previous = _g.SelectObject(dc, bitmap)
        # Black/white renders recover alpha even for monochrome stock cursors.
        renders = []
        for background in (0, 255):
            ctypes.memset(address, background, w * h * 4)
            if not _u.DrawIconEx(dc, 0, 0, handle, w, h, 0, None, 3):
                return None
            _g.GdiFlush()
            renders.append(ctypes.string_at(address, w * h * 4))
        black, white = renders
        pixels = bytearray(black)
        for i in range(0, len(pixels), 4):
            pixels[i + 3] = 255 - max(0, min(255, max(white[i + c] - black[i + c]
                                                      for c in (0, 1, 2))))
        image = QImage(bytes(pixels), w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        return QPixmap.fromImage(image), QPoint(info.x, info.y)
    finally:
        if previous:
            _g.SelectObject(dc, previous)
        if bitmap:
            _g.DeleteObject(bitmap)
        if dc:
            _g.DeleteDC(dc)
        for item in (info.mask, info.color):
            if item:
                _g.DeleteObject(item)


class PointerOverlay(QWidget):
    def __init__(self, owner, cursor_item):
        super().__init__(owner)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowTransparentForInput
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        for attribute in (Qt.WidgetAttribute.WA_TranslucentBackground,
                          Qt.WidgetAttribute.WA_ShowWithoutActivating,
                          Qt.WidgetAttribute.WA_TransparentForMouseEvents):
            self.setAttribute(attribute)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._item = cursor_item
        self._stock = None
        self._draw_scale = 1.0
        self._raise_needed = True

    def invalidate_stack(self):
        self._raise_needed = True

    def present(self, position, cursor=None):
        cursor = cursor or QCursor(Qt.CursorShape.ArrowCursor)
        self._stock = stock_cursor(cursor.shape())
        if cursor.shape() == Qt.CursorShape.BitmapCursor and not cursor.pixmap().isNull():
            self._stock = cursor.pixmap(), cursor.hotSpot()
        if self._stock:
            pixmap, hotspot = self._stock
            self.setGeometry(position.x() - hotspot.x(), position.y() - hotspot.y(),
                             pixmap.width(), pixmap.height())
        else:
            views = self._item.scene().views() if self._item.scene() else []
            self._draw_scale = abs(views[0].transform().m11()) if views else 1.0
            scale = self._draw_scale
            self.setGeometry(round(position.x() + self._item._hx * scale),
                             round(position.y() + self._item._hy * scale),
                             max(1, math.ceil(self._item._w * scale)),
                             max(1, math.ceil(self._item._h * scale)))
        if not self.isVisible():
            self.show()
            self._raise_needed = True
        if self._raise_needed:
            self._raise_needed = False
            self.raise_()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._stock:
            painter.drawPixmap(0, 0, self._stock[0])
        else:
            painter.scale(self._draw_scale, self._draw_scale)
            self._item.paint(painter, None)
