import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from core.desktop_catalog import (
    get_desktop_target,
)
from tools import desktop_tools


def run():
    steam = get_desktop_target(
        "steam"
    )

    # --------------------------------------------------
    # 1. Lifecycle identity and UI ownership stay separate.
    # --------------------------------------------------

    assert steam[
        "process_names"
    ] == (
        "steam.exe",
    )

    assert steam[
        "window_process_names"
    ] == (
        "steamwebhelper.exe",
    )

    assert steam[
        "window_class_names"
    ] == (
        "SDL_app",
    )

    assert steam[
        "window_titles"
    ] == (
        "Steam",
    )

    original_tasklist = (
        desktop_tools._tasklist_pid_map
    )

    try:
        desktop_tools._tasklist_pid_map = (
            lambda: {
                100: "steam.exe",
                200: "steamwebhelper.exe",
                201: "steamwebhelper.exe",
                300: "spotify.exe",
            }
        )

        assert (
            desktop_tools._target_pids(
                "steam"
            )
            == {
                100,
            }
        )

        assert (
            desktop_tools._target_window_pids(
                "steam"
            )
            == {
                200,
                201,
            }
        )

        # Targets without explicit split metadata preserve old behavior.
        assert (
            desktop_tools._target_pids(
                "spotify"
            )
            == desktop_tools._target_window_pids(
                "spotify"
            )
        )

    finally:
        desktop_tools._tasklist_pid_map = (
            original_tasklist
        )

    # --------------------------------------------------
    # 2. Steam window signature rejects the exact bad helper observed live.
    # --------------------------------------------------

    original_text = (
        desktop_tools._get_window_text
    )

    original_class = (
        desktop_tools._get_window_class_name
    )

    window_data = {
        # Actual bad steam.exe popup from live diagnostic.
        10: (
            "Untitled",
            "vguiPopupWindow",
        ),

        # Actual modern Steam main-window signature.
        20: (
            "Steam",
            "SDL_app",
        ),

        # Helper/menu windows must not become the client.
        30: (
            "Menu",
            "SDL_app",
        ),

        40: (
            "Steam",
            "Chrome_WidgetWin_0",
        ),
    }

    try:
        desktop_tools._get_window_text = (
            lambda hwnd: window_data[
                hwnd
            ][
                0
            ]
        )

        desktop_tools._get_window_class_name = (
            lambda hwnd: window_data[
                hwnd
            ][
                1
            ]
        )

        assert (
            desktop_tools._window_matches_target(
                "steam",
                10,
            )
            is False
        )

        assert (
            desktop_tools._window_matches_target(
                "steam",
                20,
            )
            is True
        )

        assert (
            desktop_tools._window_matches_target(
                "steam",
                30,
            )
            is False
        )

        assert (
            desktop_tools._window_matches_target(
                "steam",
                40,
            )
            is False
        )

    finally:
        desktop_tools._get_window_text = (
            original_text
        )

        desktop_tools._get_window_class_name = (
            original_class
        )

    # --------------------------------------------------
    # 3. Steam launch explicitly requests the main client UI.
    # --------------------------------------------------

    original_os_name = (
        desktop_tools.os.name
    )

    original_target = (
        desktop_tools.get_desktop_target
    )

    original_activate = (
        desktop_tools._activate_existing_application
    )

    original_launch_uri = (
        desktop_tools._launch_uri
    )

    uris = []

    try:
        desktop_tools.os.name = "nt"

        desktop_tools.get_desktop_target = (
            lambda target_id: (
                steam
                if target_id == "steam"
                else None
            )
        )

        desktop_tools._activate_existing_application = (
            lambda target_id: {
                "success": False,
                "status": "no_app_window",
            }
        )

        def fake_launch_uri(
            uri,
        ):
            uris.append(
                uri
            )

            return {
                "success": True,
            }

        desktop_tools._launch_uri = (
            fake_launch_uri
        )

        result = desktop_tools.launch_application(
            "steam"
        )

        assert result[
            "success"
        ] is True

        assert uris == [
            "steam://open/main"
        ]

    finally:
        desktop_tools.os.name = (
            original_os_name
        )

        desktop_tools.get_desktop_target = (
            original_target
        )

        desktop_tools._activate_existing_application = (
            original_activate
        )

        desktop_tools._launch_uri = (
            original_launch_uri
        )

    print(
        "Mairon Phase 9.3.2 Steam UI ownership tests: PASS"
    )


if __name__ == "__main__":
    run()
