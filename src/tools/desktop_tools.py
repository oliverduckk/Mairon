import csv
import ctypes
import glob
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.desktop_catalog import (
    desktop_display_name,
    get_desktop_target,
)
from core.web_catalog import (
    build_trusted_site_url,
    get_trusted_site,
    trusted_site_display_name,
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



def open_chrome_trusted_site(
    site_id: str,
    query: Optional[str] = None,
) -> dict:
    """
    Open one Core-approved trusted site in Chrome.

    site_id must exist in core.web_catalog. Query text is URL-encoded by the
    Core-owned catalogue and can never replace the selected scheme/host/path.
    """

    if os.name != "nt":
        return _windows_only_error()

    site_id = str(
        site_id
        or ""
    ).strip().lower()

    site = get_trusted_site(
        site_id
    )

    if site is None:
        return {
            "success": False,
            "status": "untrusted_site",
            "message": (
                "That website is not in Mairon's trusted browser catalogue."
            ),
        }

    url = build_trusted_site_url(
        site_id=site_id,
        query=query,
    )

    if not url:
        return {
            "success": False,
            "status": "unsupported_site_action",
            "message": (
                f"{trusted_site_display_name(site_id)} does not support "
                "that browser action."
            ),
        }

    chrome = _find_chrome()

    if not chrome:
        return {
            "success": False,
            "status": "chrome_not_found",
            "message": (
                "I couldn't find Chrome on the Windows desktop node."
            ),
        }

    result = _launch_process([
        chrome,
        url,
    ])

    if result.get(
        "success"
    ) is not True:
        return {
            "success": False,
            "status": "browser_open_failed",
            "message": (
                result.get(
                    "message"
                )
                or (
                    f"I couldn't open {trusted_site_display_name(site_id)} "
                    "in Chrome."
                )
            ),
        }

    return {
        "success": True,
        "status": (
            "search_opened"
            if query is not None
            else "site_opened"
        ),
        "browser": "chrome",
        "site_id": site_id,
        "query": (
            str(
                query
            )
            if query is not None
            else None
        ),
        "url": url,
        "message": (
            f"{trusted_site_display_name(site_id)} opened in Chrome."
        ),
    }


def open_chrome_search(
    query: str,
) -> dict:
    """
    Backward-compatible Phase 8.3 Google-search wrapper.
    """

    return open_chrome_trusted_site(
        site_id="google",
        query=query,
    )



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
        # Fixed Core-owned URI: explicitly request the modern main Steam
        # client UI. This avoids surfacing steam.exe's tiny VGUI bootstrap
        # window when the client is already resident.
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


def _pids_for_process_names(
    process_names,
) -> Set[int]:
    names = {
        str(
            value
        ).strip().lower()
        for value in (
            process_names
            or ()
        )
        if str(
            value
        ).strip()
    }

    if not names:
        return set()

    process_map = _tasklist_pid_map()

    return {
        pid
        for pid, image_name in process_map.items()
        if image_name in names
    }


def _target_pids(
    target_id: str,
) -> Set[int]:
    """
    Return lifecycle/process identity PIDs for one allowlisted target.

    These remain intentionally separate from UI-window ownership. Steam is
    the motivating example: steam.exe is the client identity while the modern
    main client window is owned by steamwebhelper.exe.
    """

    target = get_desktop_target(
        target_id
    )

    if target is None:
        return set()

    return _pids_for_process_names(
        target.get(
            "process_names",
            (),
        )
    )


def _target_window_pids(
    target_id: str,
) -> Set[int]:
    """
    Return only processes approved to own user-facing windows for a target.

    Targets without an explicit window_process_names field preserve the
    historical process_names behavior.
    """

    target = get_desktop_target(
        target_id
    )

    if target is None:
        return set()

    names = target.get(
        "window_process_names",
        target.get(
            "process_names",
            (),
        ),
    )

    return _pids_for_process_names(
        names
    )


def _get_window_text(
    hwnd: int,
) -> str:
    if os.name != "nt":
        return ""

    user32 = ctypes.windll.user32

    length = int(
        user32.GetWindowTextLengthW(
            hwnd
        )
        or 0
    )

    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(
        length + 1
    )

    user32.GetWindowTextW(
        hwnd,
        buffer,
        length + 1,
    )

    return str(
        buffer.value
        or ""
    )


def _get_window_class_name(
    hwnd: int,
) -> str:
    if os.name != "nt":
        return ""

    user32 = ctypes.windll.user32

    buffer = ctypes.create_unicode_buffer(
        256
    )

    result = user32.GetClassNameW(
        hwnd,
        buffer,
        256,
    )

    if not result:
        return ""

    return str(
        buffer.value
        or ""
    )


def _window_matches_target(
    target_id: str,
    hwnd: int,
) -> bool:
    """
    Apply optional Core-owned UI signatures to an already allowlisted HWND.

    This is intentionally exact/conservative. A target without extra window
    metadata keeps the historical "human-facing title required" rule.
    """

    title = _get_window_text(
        hwnd
    ).strip()

    if not title:
        return False

    target = get_desktop_target(
        target_id
    )

    if target is None:
        return False

    allowed_titles = {
        str(
            value
        ).strip().lower()
        for value in target.get(
            "window_titles",
            (),
        )
        if str(
            value
        ).strip()
    }

    if (
        allowed_titles
        and title.lower() not in allowed_titles
    ):
        return False

    allowed_classes = {
        str(
            value
        ).strip().lower()
        for value in target.get(
            "window_class_names",
            (),
        )
        if str(
            value
        ).strip()
    }

    if allowed_classes:
        class_name = (
            _get_window_class_name(
                hwnd
            ).strip().lower()
        )

        if class_name not in allowed_classes:
            return False

    return True


def _top_level_windows_for_pids(
    pids: Set[int],
    visible_only: bool = True,
    target_id: str = "",
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

        hwnd_value = int(
            hwnd
        )

        if target_id:
            if not _window_matches_target(
                target_id,
                hwnd_value,
            ):
                return True

        else:
            # Historical fallback for callers without target-specific window
            # metadata: only human-facing titled windows are candidates.
            if not _get_window_text(
                hwnd_value
            ).strip():
                return True

        windows.append(
            hwnd_value
        )

        return True

    user32.EnumWindows(
        enum_callback,
        0,
    )

    return windows


def _foreground_window_handle() -> int:
    """
    Return the current foreground HWND using pointer-sized ctypes handling.
    """

    if os.name != "nt":
        return 0

    user32 = ctypes.windll.user32

    get_foreground_window = (
        user32.GetForegroundWindow
    )

    get_foreground_window.restype = (
        ctypes.c_void_p
    )

    return int(
        get_foreground_window()
        or 0
    )


def _window_thread_id(
    hwnd: int,
) -> int:
    if (
        os.name != "nt"
        or not hwnd
    ):
        return 0

    user32 = ctypes.windll.user32

    return int(
        user32.GetWindowThreadProcessId(
            ctypes.c_void_p(
                int(
                    hwnd
                )
            ),
            None,
        )
        or 0
    )


def _is_foreground_window(
    hwnd: int,
) -> bool:
    return (
        bool(
            hwnd
        )
        and _foreground_window_handle()
        == int(
            hwnd
        )
    )


def _try_attached_thread_foreground(
    hwnd: int,
) -> bool:
    """
    Make one bounded foreground attempt using Windows thread-input attachment.

    Windows deliberately restricts focus stealing. When a direct
    SetForegroundWindow call is refused, temporarily attaching this agent
    thread to the foreground/target GUI threads gives Windows a legitimate
    shared input context for a second activation attempt.

    No user input is synthesized and no arbitrary process/thread identifiers
    come from user text. The HWND was already discovered from an allowlisted
    application's verified process set.
    """

    if os.name != "nt":
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    foreground_hwnd = (
        _foreground_window_handle()
    )

    current_thread_id = int(
        kernel32.GetCurrentThreadId()
        or 0
    )

    foreground_thread_id = (
        _window_thread_id(
            foreground_hwnd
        )
    )

    target_thread_id = (
        _window_thread_id(
            hwnd
        )
    )

    attached_pairs = []

    def attach(
        first: int,
        second: int,
    ) -> None:
        if (
            not first
            or not second
            or first == second
        ):
            return

        if user32.AttachThreadInput(
            first,
            second,
            True,
        ):
            attached_pairs.append(
                (
                    first,
                    second,
                )
            )

    try:
        attach(
            current_thread_id,
            foreground_thread_id,
        )

        attach(
            current_thread_id,
            target_thread_id,
        )

        try:
            user32.BringWindowToTop(
                hwnd
            )
        except Exception:
            pass

        try:
            user32.SetActiveWindow(
                hwnd
            )
        except Exception:
            pass

        try:
            user32.SetFocus(
                hwnd
            )
        except Exception:
            pass

        user32.SetForegroundWindow(
            hwnd
        )

        # Foreground state may settle immediately after the Win32 call rather
        # than before it returns. Keep verification short so desktop actions
        # remain effectively instant.
        for _ in range(
            5
        ):
            if _is_foreground_window(
                hwnd
            ):
                return True

            time.sleep(
                0.02
            )

        return False

    finally:
        for first, second in reversed(
            attached_pairs
        ):
            try:
                user32.AttachThreadInput(
                    first,
                    second,
                    False,
                )
            except Exception:
                pass


def _show_and_focus_window(
    hwnd: int,
) -> dict:
    """
    Make an existing top-level window visible and attempt verified foreground
    activation.

    Visibility remains sufficient for generic `open`, because restoring an
    already-running app is useful even when Windows refuses focus stealing.
    Explicit `focus_application`, however, requires the separate verified
    `focused` result.
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

    user32.SetForegroundWindow(
        hwnd
    )

    focused = _is_foreground_window(
        hwnd
    )

    if not focused:
        focused = (
            _try_attached_thread_foreground(
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
    require_focus: bool = False,
) -> dict:
    """
    Ensure an already-running allowlisted app has a usable window.

    Generic `open` accepts a restored visible window even if Windows refuses
    foreground focus. Explicit focus operations set require_focus=True and
    succeed only after verified foreground activation.
    """

    lifecycle_pids = _target_pids(
        target_id
    )

    if not lifecycle_pids:
        return {
            "success": False,
            "status": "not_running",
        }

    window_pids = _target_window_pids(
        target_id
    )

    if not window_pids:
        return {
            "success": False,
            "status": "no_app_window",
        }

    visible_windows = (
        _top_level_windows_for_pids(
            window_pids,
            visible_only=True,
            target_id=target_id,
        )
    )

    all_windows = (
        _top_level_windows_for_pids(
            window_pids,
            visible_only=False,
            target_id=target_id,
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

    saw_visible_window = False

    for hwnd in candidates:
        result = _show_and_focus_window(
            hwnd
        )

        visible = bool(
            result.get(
                "visible"
            )
        )

        focused = bool(
            result.get(
                "focused"
            )
        )

        if visible:
            saw_visible_window = True

        if focused:
            return {
                "success": True,
                "status": "focused",
                "window_handle": hwnd,
                "focused": True,
            }

        if (
            visible
            and not require_focus
        ):
            return {
                "success": True,
                "status": "shown",
                "window_handle": hwnd,
                "focused": False,
            }

    if (
        require_focus
        and saw_visible_window
    ):
        return {
            "success": False,
            "status": "foreground_denied",
            "focused": False,
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

    lifecycle_pids = _target_pids(
        target_id
    )

    if not lifecycle_pids:
        return {
            "success": False,
            "status": "not_running",
            "close_behavior": "graceful_window",
            "message": (
                f"{desktop_display_name(target_id)} doesn't appear to be running."
            ),
        }

    window_pids = _target_window_pids(
        target_id
    )

    windows = _top_level_windows_for_pids(
        window_pids,
        target_id=target_id,
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
            target_id,
            require_focus=True,
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

    elif status == "foreground_denied":
        message = (
            f"I found {desktop_display_name(target_id)} and restored its "
            "window, but Windows didn't allow it to become the foreground "
            "window."
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
