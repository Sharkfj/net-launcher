"""Blur behind the window: KDE (KWindowEffects) on Linux, Acrylic/Mica on Windows."""

from __future__ import annotations

import ctypes as C
import sys

from PySide6.QtGui import QGuiApplication, QRegion

_kde_fn = None


def _kde(widget, region: QRegion | None, on: bool = True) -> bool:
    global _kde_fn
    try:
        import shiboken6
        if _kde_fn is None:
            lib = C.CDLL("libKF6WindowSystem.so.6")
            _kde_fn = getattr(lib, "_ZN14KWindowEffects16enableBlurBehindEP7QWindowbRK7QRegion")
            _kde_fn.argtypes = [C.c_void_p, C.c_bool, C.c_void_p]
            _kde_fn.restype = None
        handle = widget.windowHandle()
        if handle is None:
            return False
        reg = region if region is not None else QRegion()
        _kde_fn(shiboken6.getCppPointer(handle)[0], on, shiboken6.getCppPointer(reg)[0])
        return True
    except (OSError, AttributeError, ImportError):
        return False


class _ACCENT(C.Structure):
    _fields_ = [("AccentState", C.c_int), ("AccentFlags", C.c_int), ("GradientColor", C.c_uint),
                ("AnimationId", C.c_int)]


class _WCA(C.Structure):
    _fields_ = [("Attribute", C.c_int), ("Data", C.c_void_p), ("SizeOfData", C.c_size_t)]


def _windows(widget, on: bool = True) -> bool:
    try:
        hwnd = int(widget.winId())
        dwm = C.windll.dwmapi
        dark = C.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, C.byref(dark), C.sizeof(dark))
        backdrop = C.c_int(3 if on else 1)  # DWMSBT_TRANSIENTWINDOW (acrylic) / DWMSBT_NONE
        if dwm.DwmSetWindowAttribute(hwnd, 38, C.byref(backdrop), C.sizeof(backdrop)) == 0:
            return True
        if not on:
            return False
        accent = _ACCENT(4, 2, 0x99201208, 0)  # ACCENT_ENABLE_ACRYLICBLURBEHIND, ABGR tint
        data = _WCA(19, C.cast(C.pointer(accent), C.c_void_p), C.sizeof(accent))
        return bool(C.windll.user32.SetWindowCompositionAttribute(hwnd, C.byref(data)))
    except (AttributeError, OSError):
        return False


def enable(widget, region: QRegion | None = None, on: bool = True) -> bool:
    """Turn blur behind the window on (returns True when it worked) or off (always returns False)."""
    platform = QGuiApplication.platformName()
    if platform in ("offscreen", "minimal", "vnc"):
        return False
    if sys.platform == "win32":
        return _windows(widget, on) and on
    if sys.platform.startswith("linux"):
        return _kde(widget, region, on) and on
    return False
