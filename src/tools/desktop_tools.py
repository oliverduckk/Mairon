import csv
import ctypes
import glob
import os
import shutil
import subprocess
from urllib.parse import urlencode
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.desktop_catalog import (
    desktop_display_name,
    get_desktop_target,
)


CREATE_NO_WINDOW = getattr(
    subprocess,
    "CREATE_NO_WINDOW",
    0,
)


def _windows_only_error() -> dict:
    return {
        "success": False,
        "message": (
            "Desktop control is only available on the Windows desktop node."
        ),
    }


def _first_existing_path(
    candidates,
) -> Optional[str]:
    for candidate in candidates:
        if not candidate:
            continue

        path = os.path.expandvars(
            os.path.expanduser(
                str(candidate)
            )
        )

        if os.path.isfile(path):
            return path

    return None


def _latest_glob_path(
    pattern: str,
) -> Optional[str]:
    matches = [
        path
        for path in glob.glob(
            os.path.expandvars(pattern)
        )
        if os.path.isfile(path)
    ]

    if not matches:
        return None

    matches.sort(
        reverse=True
    )

    return matches[0]


def _find_chrome() -> Optional[str]:
    path = _first_existing_path([
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ])

    return path or shutil.which(
        "chrome.exe"
    )


def _find_spotify() -> Optional[str]:
    path = _first_existing_path([
        r"%APPDATA%\Spotify\Spotify.exe",
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
    ])

    return path or shutil.which(
        "Spotify.exe"
    )


def _find_discord() -> Optional[str]:
    direct = _latest_glob_path(
        r"%LOCALAPPDATA%\Discord\app-*\Discord.exe"
    )

    if direct:
        return direct

    return _first_existing_path([
        r"%LOCALAPPDATA%\Discord\Discord.exe",
    ])


def _find_discord_update() -> Optional[str]:
    return _first_existing_path([
        r"%LOCALAPPDATA%\Discord\Update.exe",
    ])


def _find_lunar_client() -> Optional[str]:
    """
    Resolve Lunar Client's documented Windows launcher location.

    Lunar's support documentation places the launcher under:
      %LOCALAPPDATA%\\Programs\\lunarclient\\Lunar Client.exe

    A small set of historical/current folder-name variants is accepted, but
    user input never supplies executable paths.
    """

    path = _first_existing_path([
        r"%LOCALAPPDATA%\Programs\lunarclient\Lunar Client.exe",
        r"%LOCALAPPDATA%\Programs\Lunar Client\Lunar Client.exe",
        r"%LOCALAPPDATA%\Programs\launcher\Lunar Client.exe",
    ])

    return path or shutil.which(
        "Lunar Client.exe"
    )


def _find_steam() -> Optional[str]:
    path = _first_existing_path([
        r"%ProgramFiles(x86)%\Steam\steam.exe",
        r"%ProgramFiles%\Steam\steam.exe",
    ])

    return path or shutil.which(
        "steam.exe"
    )


def _find_vscode() -> Optional[str]:
    path = _first_existing_path([
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        r"%ProgramFiles%\Microsoft VS Code\Code.exe",
        r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe",
    ])

    return path or shutil.which(
        "Code.exe"
    )


def _launch_process(
    command: List[str],
) -> dict:
    try:
        subprocess.Popen(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc),
        }

    return {
        "success": True,
    }


def _launch_uri(
    uri: str,
) -> dict:
    try:
        os.startfile(uri)
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc),
        }

    return {
        "success": True,
    }


def _launch_folder(
    path: str,
) -> dict:
    folder = Path(path).expanduser()

    if not folder.is_dir():
        return {
            "success": False,
            "message": f"Folder not found: {folder}",
        }

    try:
        os.startfile(
            str(folder)
        )
    except Exception as exc:
        return {
            "success": False,
            "message": str(exc),
        }

    return {
        "success": True,
    }



def open_chrome_search(
    query: str,
) -> dict:
    """
    Open an explicit Google search in Chrome.

    Query text is URL-encoded as data and never becomes shell text.
    """

    if os.name != "nt":
        return _windows_only_error()

    value = str(
        query
        or ""
    ).strip()

    if (
        not value
        or len(
            value
        ) > 500
    ):
        return {
            "success": False,
            "message": "That search query is empty or too long.",
        }

    chrome = _find_chrome()

    if not chrome:
        return {
            "success": False,
            "message": (
                "I couldn't find Chrome on the Windows desktop node."
            ),
        }

    url = (
        "https://www.google.com/search?"
        + urlencode({
            "q": value,
        })
    )

    result = _launch_process([
        chrome,
        url,
    ])

    if result.get(
        "success"
    ) is not True:
        return {
            "success": False,
            "message": (
                result.get(
                    "message"
                )
                or "I couldn't open that Chrome search."
            ),
        }

    return {
        "success": True,
        "status": "search_opened",
        "browser": "chrome",
        "query": value,
        "url": url,
        "message": "Chrome search opened.",
    }


def launch_steam_game_appid(
    appid: str,
) -> dict:
    """
    Launch one locally resolved Steam AppID through Steam's URL protocol.

    The AppID must already have been selected by Core from local Steam
    manifests. Arbitrary URI text is never accepted here.
    """

    if os.name != "nt":
        return _windows_only_error()

    value = str(
        appid
        or ""
    ).strip()

    if not value.isdigit():
        return {
            "success": False,
            "message": "Steam AppID must be numeric.",
        }

    result = _launch_uri(
        f"steam://run/{value}"
    )

    if result.get(
        "success"
    ) is not True:
        return {
            "success": False,
            "message": (
                result.get(
                    "message"
                )
                or "Steam rejected the game launch request."
            ),
        }

    return {
        "success": True,
        "status": "steam_launch_requested",
        "appid": value,
        "message": "Steam game launch requested.",
    }


def launch_application(
    app_name: str,
) -> dict:
    """
    Launch one allowlisted desktop target.

    The historical function name is retained because the existing tool
    registry already calls launch_application(app_name).
    """

    if os.name != "nt":
        return _windows_only_error()

    target_id = str(
        app_name
        or ""
    ).strip().lower()

    target = get_desktop_target(
        target_id
    )

    if target is None:
        return {
            "success": False,
            "message": "That desktop target is not approved.",
        }

    display_name = desktop_display_name(
        target_id
    )

    # "Open" means make the app usable, not blindly spawn another process.
    # Tray-backed apps may already be running with their main window hidden.
    if (
        target.get(
            "supports_focus",
            False,
        )
        and target_id != "mairon_project"
    ):
        activation = (
            _activate_existing_application(
                target_id
            )
        )

        if activation.get(
            "success"
        ):
            return {
                "success": True,
                "status": "existing_window_activated",
                "target_id": target_id,
                "message": (
                    f"{display_name} existing window activated."
                ),
                "activation": activation,
            }

    result = None

    if target_id == "calculator":
        result = _launch_process(
            ["calc.exe"]
        )

    elif target_id == "notepad":
        result = _launch_process(
            ["notepad.exe"]
        )

    elif target_id == "chrome":
        executable = _find_chrome()
        if executable:
            result = _launch_process(
                [executable]
            )

    elif target_id == "spotify":
        executable = _find_spotify()
        if executable:
            result = _launch_process(
                [executable]
            )
        else:
            result = _launch_uri(
                "spotify:"
            )

    elif target_id == "discord":
        updater = _find_discord_update()

        if updater:
            result = _launch_process([
                updater,
                "--processStart",
                "Discord.exe",
            ])

        else:
            executable = _find_discord()

            if executable:
                result = _launch_process(
                    [executable]
                )

    elif target_id == "lunar_client":
        executable = _find_lunar_client()

        if executable:
            result = _launch_process(
                [executable]
            )

    elif target_id == "steam":
        executable = _find_steam()
        if executable:
            result = _launch_process(
                [executable]
            )
        else:
            result = _launch_uri(
                "steam://open/main"
            )

    elif target_id == "vscode":
        executable = _find_vscode()
        if executable:
            result = _launch_process(
                [executable]
            )

    elif target_id == "downloads":
        downloads = os.path.join(
            os.path.expanduser("~"),
            "Downloads",
        )
        result = _launch_folder(
            downloads
        )

    elif target_id == "mairon_project":
        executable = _find_vscode()

        project_root = os.environ.get(
            "MAIRON_PROJECT_ROOT",
            r"C:\Projects\Mairon",
        )

        if executable:
            project_path = Path(
                project_root
            ).expanduser()

            if not project_path.is_dir():
                return {
                    "success": False,
                    "message": (
                        "The configured Mairon project folder does not exist: "
                        f"{project_path}"
                    ),
                }

            result = _launch_process([
                executable,
                str(project_path),
            ])

    if result is None:
        return {
            "success": False,
            "message": (
                f"I couldn't find an installed launcher for {display_name}."
            ),
        }

    if result.get("success") is not True:
        return {
            "success": False,
            "message": (
                result.get("message")
                or f"I couldn't open {display_name}."
            ),
        }

    return {
        "success": True,
        "status": "launch_requested",
        "target_id": target_id,
        "message": f"{display_name} launch requested.",
    }


def _tasklist_pid_map() -> Dict[int, str]:
    result = subprocess.run(
        [
            "tasklist",
            "/FO",
            "CSV",
            "/NH",
        ],
        capture_output=True,
        text=True,
        shell=False,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )

    if result.returncode != 0:
        return {}

    rows = csv.reader(
        result.stdout.splitlines()
    )

    process_map = {}

    for row in rows:
        if len(row) < 2:
            continue

        image_name = str(
            row[0]
            or ""
        ).strip().lower()

        pid_text = str(
            row[1]
            or ""
        ).replace(
            ",",
            "",
        ).strip()

        try:
            pid = int(pid_text)
        except ValueError:
            continue

        process_map[pid] = image_name

    return process_map


def _target_pids(
    target_id: str,
) -> Set[int]:
    target = get_desktop_target(
        target_id
    )

    if target is None:
        return set()

    names = {
        str(value).strip().lower()
        for value in target.get(
            "process_names",
            (),
        )
        if str(value).strip()
    }

    if not names:
        return set()

    process_map = _tasklist_pid_map()

    return {
        pid
        for pid, image_name in process_map.items()
        if image_name in names
    }


def _top_level_windows_for_pids(
    pids: Set[int],
    visible_only: bool = True,
) -> List[int]:
    """
    Find titled top-level windows owned by the allowlisted process set.

    Some tray applications (notably Discord) keep their primary top-level
    window alive but hidden after WM_CLOSE. `visible_only=False` lets Core
    recover that existing window instead of spawning a doomed second instance.
    """

    if (
        os.name != "nt"
        or not pids
    ):
        return []

    user32 = ctypes.windll.user32
    windows = []

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )

    @callback_type
    def enum_callback(
        hwnd,
        _lparam,
    ):
        if (
            visible_only
            and not user32.IsWindowVisible(
                hwnd
            )
        ):
            return True

        pid = ctypes.c_ulong()

        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(
                pid
            ),
        )

        if int(
            pid.value
        ) not in pids:
            return True

        # Avoid Electron helper/message windows. The actual app window retains
        # a human-facing title even when hidden in the tray.
        length = user32.GetWindowTextLengthW(
            hwnd
        )

        if length <= 0:
            return True

        windows.append(
            int(
                hwnd
            )
        )

        return True

    user32.EnumWindows(
        enum_callback,
        0,
    )

    return windows


def _show_and_focus_window(
    hwnd: int,
) -> dict:
    """
    Make an existing top-level window visible and attempt to foreground it.

    SetForegroundWindow can legally be refused by Windows focus-stealing rules.
    Visibility is therefore the hard success condition for `open`; foreground
    status is reported separately.
    """

    user32 = ctypes.windll.user32

    SW_SHOW = 5
    SW_RESTORE = 9

    if not user32.IsWindowVisible(
        hwnd
    ):
        user32.ShowWindow(
            hwnd,
            SW_SHOW,
        )

    user32.ShowWindow(
        hwnd,
        SW_RESTORE,
    )

    try:
        user32.BringWindowToTop(
            hwnd
        )
    except Exception:
        pass

    focused = bool(
        user32.SetForegroundWindow(
            hwnd
        )
    )

    visible = bool(
        user32.IsWindowVisible(
            hwnd
        )
    )

    return {
        "visible": visible,
        "focused": focused,
    }


def _activate_existing_application(
    target_id: str,
) -> dict:
    """
    Ensure an already-running allowlisted app has a visible usable window.

    Visible windows are preferred. If the app is tray-backed, hidden titled
    windows are considered next.
    """

    pids = _target_pids(
        target_id
    )

    if not pids:
        return {
            "success": False,
            "status": "not_running",
        }

    visible_windows = (
        _top_level_windows_for_pids(
            pids,
            visible_only=True,
        )
    )

    all_windows = (
        _top_level_windows_for_pids(
            pids,
            visible_only=False,
        )
    )

    candidates = list(
        visible_windows
    )

    candidates.extend(
        hwnd
        for hwnd in all_windows
        if hwnd not in visible_windows
    )

    if not candidates:
        return {
            "success": False,
            "status": "no_app_window",
        }

    for hwnd in candidates:
        result = _show_and_focus_window(
            hwnd
        )

        if result.get(
            "visible"
        ):
            return {
                "success": True,
                "status": (
                    "focused"
                    if result.get(
                        "focused"
                    )
                    else "shown"
                ),
                "window_handle": hwnd,
                "focused": bool(
                    result.get(
                        "focused"
                    )
                ),
            }

    return {
        "success": False,
        "status": "activation_failed",
    }


def _terminate_target_processes(
    target_id: str,
    verification_timeout_seconds: float = 1.5,
) -> dict:
    """
    Terminate only the exact allowlisted process image(s) for one target.

    This is deliberately narrower than a generic "kill process" tool:
    - target_id must already exist in Core's desktop allowlist;
    - PIDs come from exact fixed process_names in that allowlist;
    - user text never supplies a PID, image name, executable, or command;
    - no shell / PowerShell / taskkill command is constructed.

    Used only for targets whose catalogue close_behavior is `quit_process`.
    """

    target = get_desktop_target(
        target_id
    )

    if target is None:
        return {
            "success": False,
            "status": "unsupported_application",
            "message": "That desktop target is not approved.",
        }

    pids = _target_pids(
        target_id
    )

    if not pids:
        return {
            "success": True,
            "status": "already_closed",
            "target_id": target_id,
            "terminated_pids": [],
            "message": (
                f"{desktop_display_name(target_id)} is already closed."
            ),
        }

    kernel32 = ctypes.windll.kernel32

    PROCESS_TERMINATE = 0x0001

    kernel32.OpenProcess.argtypes = [
        ctypes.c_ulong,
        ctypes.c_bool,
        ctypes.c_ulong,
    ]

    kernel32.OpenProcess.restype = (
        ctypes.c_void_p
    )

    kernel32.TerminateProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
    ]

    kernel32.TerminateProcess.restype = (
        ctypes.c_bool
    )

    kernel32.CloseHandle.argtypes = [
        ctypes.c_void_p,
    ]

    kernel32.CloseHandle.restype = (
        ctypes.c_bool
    )

    attempted = []
    failed = []

    for pid in sorted(
        pids
    ):
        handle = kernel32.OpenProcess(
            PROCESS_TERMINATE,
            False,
            int(
                pid
            ),
        )

        if not handle:
            failed.append(
                pid
            )
            continue

        try:
            terminated = bool(
                kernel32.TerminateProcess(
                    handle,
                    0,
                )
            )

            if terminated:
                attempted.append(
                    pid
                )
            else:
                failed.append(
                    pid
                )

        finally:
            kernel32.CloseHandle(
                handle
            )

    deadline = (
        time.monotonic()
        + max(
            0.0,
            float(
                verification_timeout_seconds
            ),
        )
    )

    remaining = _target_pids(
        target_id
    )

    while (
        remaining
        and time.monotonic() < deadline
    ):
        time.sleep(
            0.05
        )

        remaining = _target_pids(
            target_id
        )

    if remaining:
        return {
            "success": False,
            "status": "termination_incomplete",
            "target_id": target_id,
            "attempted_pids": attempted,
            "failed_pids": failed,
            "remaining_pids": sorted(
                remaining
            ),
            "message": (
                f"I tried to fully close {desktop_display_name(target_id)}, "
                "but some approved app processes are still running."
            ),
        }

    return {
        "success": True,
        "status": "terminated",
        "target_id": target_id,
        "terminated_pids": attempted,
        "failed_pids": failed,
        "message": (
            f"{desktop_display_name(target_id)} fully exited."
        ),
    }


def close_application(
    app_name: str,
) -> dict:
    """
    Close one allowlisted app using its Core-owned close semantics.

    Most apps receive a normal WM_CLOSE so they can save/exit naturally.

    Known tray-backed exceptions use `quit_process`: Core terminates only the
    fixed allowlisted process image(s) for that target and verifies they are
    gone before claiming success.
    """

    if os.name != "nt":
        return _windows_only_error()

    target_id = str(
        app_name
        or ""
    ).strip().lower()

    target = get_desktop_target(
        target_id
    )

    if (
        target is None
        or not target.get(
            "supports_close",
            False,
        )
    ):
        return {
            "success": False,
            "message": (
                "That target does not support closing."
            ),
        }

    close_behavior = str(
        target.get(
            "close_behavior",
            "graceful_window",
        )
        or "graceful_window"
    ).strip().lower()

    if close_behavior == "quit_process":
        result = _terminate_target_processes(
            target_id
        )

        result[
            "close_behavior"
        ] = "quit_process"

        return result

    if close_behavior != "graceful_window":
        return {
            "success": False,
            "status": "unsupported_close_behavior",
            "message": (
                "That target has an unsupported close behavior."
            ),
        }

    pids = _target_pids(
        target_id
    )

    if not pids:
        return {
            "success": False,
            "status": "not_running",
            "close_behavior": "graceful_window",
            "message": (
                f"{desktop_display_name(target_id)} doesn't appear to be running."
            ),
        }

    windows = _top_level_windows_for_pids(
        pids
    )

    if not windows:
        return {
            "success": False,
            "status": "no_closable_window",
            "close_behavior": "graceful_window",
            "message": (
                f"I found {desktop_display_name(target_id)} running, "
                "but not a visible window I can close gracefully."
            ),
        }

    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    sent = 0

    for hwnd in windows:
        if user32.PostMessageW(
            hwnd,
            WM_CLOSE,
            0,
            0,
        ):
            sent += 1

    if sent == 0:
        return {
            "success": False,
            "status": "close_failed",
            "close_behavior": "graceful_window",
            "message": (
                f"I couldn't close the {desktop_display_name(target_id)} window."
            ),
        }

    return {
        "success": True,
        "status": "close_requested",
        "target_id": target_id,
        "close_behavior": "graceful_window",
        "window_count": sent,
        "message": (
            f"Graceful close sent to {desktop_display_name(target_id)}."
        ),
    }


def focus_application(
    app_name: str,
) -> dict:
    """
    Restore/show and foreground one allowlisted app window.

    Hidden tray-backed windows are valid focus targets.
    """

    if os.name != "nt":
        return _windows_only_error()

    target_id = str(
        app_name
        or ""
    ).strip().lower()

    target = get_desktop_target(
        target_id
    )

    if (
        target is None
        or not target.get(
            "supports_focus",
            False,
        )
    ):
        return {
            "success": False,
            "message": (
                "That target does not support window focus."
            ),
        }

    activation = (
        _activate_existing_application(
            target_id
        )
    )

    if activation.get(
        "success"
    ):
        return {
            "success": True,
            "status": (
                activation.get(
                    "status"
                )
                or "shown"
            ),
            "target_id": target_id,
            "focused": bool(
                activation.get(
                    "focused"
                )
            ),
            "message": (
                f"{desktop_display_name(target_id)} "
                "is visible and foreground activation was requested."
            ),
        }

    status = str(
        activation.get(
            "status"
        )
        or "focus_failed"
    )

    if status == "not_running":
        message = (
            f"{desktop_display_name(target_id)} "
            "doesn't appear to be running."
        )

    elif status == "no_app_window":
        message = (
            f"I found {desktop_display_name(target_id)} running, "
            "but not a usable app window to bring forward."
        )

    else:
        message = (
            f"I couldn't restore the "
            f"{desktop_display_name(target_id)} window."
        )

    return {
        "success": False,
        "status": status,
        "message": message,
    }
