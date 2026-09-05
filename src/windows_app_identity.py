from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


MAIRON_APP_USER_MODEL_ID = (
    "OliverDuck.Mairon.Desktop.v1"
)

MAIRON_INSTANCE_MUTEX = (
    r"Local\OliverDuck.Mairon.Desktop.v1.Instance"
)

MAIRON_WINDOW_TITLE = (
    "Mairon"
)

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9

_instance_mutex_handle = None


def set_windows_app_identity() -> bool:
    """
    Give the current process an explicit Windows application identity.

    The Start Menu/taskbar shortcut must carry this exact same AppUserModelID
    so Windows groups the pinned shortcut and running Mairon window together.
    """

    if os.name != "nt":
        return False

    try:
        shell32 = (
            ctypes.windll.shell32
        )

        result = (
            shell32
            .SetCurrentProcessExplicitAppUserModelID(
                MAIRON_APP_USER_MODEL_ID
            )
        )

        return (
            int(
                result
            )
            == 0
        )

    except Exception:
        return False


def _activate_existing_mairon_window() -> bool:
    """
    Restore and foreground an existing top-level Mairon window.

    A second user-launched process is normally permitted by Windows foreground
    rules to activate the existing window because the launch originated from
    explicit user interaction.
    """

    if os.name != "nt":
        return False

    try:
        user32 = ctypes.WinDLL(
            "user32",
            use_last_error=True,
        )

        enum_windows = (
            user32.EnumWindows
        )

        get_window_text_length = (
            user32.GetWindowTextLengthW
        )

        get_window_text = (
            user32.GetWindowTextW
        )

        show_window = (
            user32.ShowWindow
        )

        bring_to_top = (
            user32.BringWindowToTop
        )

        set_foreground = (
            user32.SetForegroundWindow
        )

        found = {
            "hwnd": None,
        }

        CALLBACK = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def callback(
            hwnd,
            lparam,
        ):
            length = int(
                get_window_text_length(
                    hwnd
                )
                or 0
            )

            if length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(
                length
                + 1
            )

            get_window_text(
                hwnd,
                buffer,
                len(
                    buffer
                ),
            )

            title = str(
                buffer.value
                or ""
            ).strip()

            if title == MAIRON_WINDOW_TITLE:
                found[
                    "hwnd"
                ] = hwnd

                return False

            return True

        callback_ref = CALLBACK(
            callback
        )

        enum_windows(
            callback_ref,
            0,
        )

        hwnd = found[
            "hwnd"
        ]

        if not hwnd:
            return False

        show_window(
            hwnd,
            SW_RESTORE,
        )

        bring_to_top(
            hwnd
        )

        set_foreground(
            hwnd
        )

        return True

    except Exception:
        return False


def ensure_single_instance_or_activate() -> bool:
    """
    Return True when this process should continue starting Mairon.

    When another Mairon process already owns the named mutex, restore/foreground
    that existing window and return False so the new process exits cleanly.

    The OS automatically releases the retained mutex when the owning process
    terminates.
    """

    global _instance_mutex_handle

    if os.name != "nt":
        return True

    if _instance_mutex_handle:
        return True

    try:
        kernel32 = ctypes.WinDLL(
            "kernel32",
            use_last_error=True,
        )

        create_mutex = (
            kernel32.CreateMutexW
        )

        create_mutex.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]

        create_mutex.restype = (
            wintypes.HANDLE
        )

        close_handle = (
            kernel32.CloseHandle
        )

        close_handle.argtypes = [
            wintypes.HANDLE,
        ]

        close_handle.restype = (
            wintypes.BOOL
        )

        ctypes.set_last_error(
            0
        )

        handle = create_mutex(
            None,
            True,
            MAIRON_INSTANCE_MUTEX,
        )

        if not handle:
            # Failing to create the guard should not stop Mairon from starting.
            return True

        last_error = (
            ctypes.get_last_error()
        )

        if last_error == ERROR_ALREADY_EXISTS:
            close_handle(
                handle
            )

            _activate_existing_mairon_window()

            return False

        _instance_mutex_handle = (
            handle
        )

        return True

    except Exception:
        # Single-instance handling is shell hygiene, not an authority boundary.
        return True
