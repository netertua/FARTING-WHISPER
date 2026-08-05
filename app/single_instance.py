"""Single-instance lock — second launch focuses the existing window and exits."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MUTEX_NAME = "Local\\FartingWhisper_SingleInstance_v1"
WINDOW_TITLE = "FARTING-WHISPER"
ERROR_ALREADY_EXISTS = 183

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

SW_RESTORE = 9
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4

_mutex_handle = None


def acquire() -> bool:
    """
    True = this process is primary; continue.
    False = already running; existing instance was activated; caller must exit.
    """
    global _mutex_handle
    kernel32.SetLastError(0)
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not _mutex_handle:
        return True
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        _activate_existing()
        try:
            kernel32.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None
        return False
    return True


def release() -> None:
    global _mutex_handle
    if _mutex_handle:
        try:
            kernel32.ReleaseMutex(_mutex_handle)
            kernel32.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None


def _activate_existing() -> None:
    """Find same-titled window and bring it forward."""
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        # may be hidden in tray — FindWindow still works by title when mapped
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)
    user32.SetForegroundWindow(hwnd)


def ensure_single_or_exit() -> None:
    if not acquire():
        try:
            user32.MessageBoxW(
                0,
                "FARTING-WHISPER is already running.\nCheck the tray icon or hold F11.",
                "FARTING-WHISPER",
                0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            pass
        sys.exit(0)
