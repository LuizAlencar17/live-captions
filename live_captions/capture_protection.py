from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011


@dataclass(frozen=True, slots=True)
class ProtectionResult:
    protected: bool
    fully_excluded: bool
    message: str


def exclude_window_from_capture(widget: QWidget) -> ProtectionResult:
    """Protect a top-level window with the official Windows API."""
    if sys.platform != "win32":
        return ProtectionResult(False, False, "Capture protection is available only on Windows")

    hwnd = int(widget.winId())
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    set_affinity = user32.SetWindowDisplayAffinity
    set_affinity.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    set_affinity.restype = ctypes.c_bool

    ctypes.set_last_error(0)
    if set_affinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        return ProtectionResult(True, True, "Hidden from capture")

    full_error = ctypes.get_last_error()
    ctypes.set_last_error(0)
    if set_affinity(hwnd, WDA_MONITOR):
        return ProtectionResult(
            True,
            False,
            "Compatibility protection (may appear as a blank area)",
        )

    fallback_error = ctypes.get_last_error()
    error_code = fallback_error or full_error
    return ProtectionResult(
        False,
        False,
        f"Failed to enable capture protection (Windows {error_code})",
    )
