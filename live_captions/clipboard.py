from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PySide6.QtWidgets import QApplication

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040


def set_clipboard_text(text: str, owner_hwnd: int = 0) -> None:
    """Copy text without relying on the Windows OLE/COM clipboard."""
    if sys.platform != "win32":
        QApplication.clipboard().setText(text)
        return

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = ()
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = ()
    user32.CloseClipboard.restype = wintypes.BOOL

    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    payload = text.encode("utf-16-le") + b"\x00\x00"
    memory = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(payload))
    if not memory:
        raise _windows_error("Could not allocate memory for the copied text")

    clipboard_open = False
    owns_memory = True
    try:
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            raise _windows_error("Could not prepare the text for copying")
        try:
            ctypes.memmove(pointer, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(memory)

        for _ in range(10):
            if user32.OpenClipboard(owner_hwnd):
                clipboard_open = True
                break
            time.sleep(0.02)
        if not clipboard_open:
            raise _windows_error("The clipboard is busy")

        if not user32.EmptyClipboard():
            raise _windows_error("Could not clear the clipboard")
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            raise _windows_error("Could not copy the text")

        # Windows owns the memory block after SetClipboardData succeeds.
        owns_memory = False
    finally:
        if clipboard_open:
            user32.CloseClipboard()
        if owns_memory:
            kernel32.GlobalFree(memory)


def _windows_error(message: str) -> RuntimeError:
    code = ctypes.get_last_error()
    detail = ctypes.FormatError(code).strip() if code else "unknown error"
    return RuntimeError(f"{message}: {detail} (Windows {code})")
