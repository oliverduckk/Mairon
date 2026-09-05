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


from tools import desktop_tools


def run():
    original_os_name = (
        desktop_tools.os.name
    )

    original_get_target = (
        desktop_tools.get_desktop_target
    )

    original_activate = (
        desktop_tools._activate_existing_application
    )

    calls = []

    try:
        desktop_tools.os.name = "nt"

        desktop_tools.get_desktop_target = (
            lambda target_id: {
                "supports_focus": True,
            }
        )

        # --------------------------------------------------
        # 1. Explicit focus must request strict foreground verification.
        # --------------------------------------------------

        def fake_focused(
            target_id,
            require_focus=False,
        ):
            calls.append(
                (
                    target_id,
                    require_focus,
                )
            )

            return {
                "success": True,
                "status": "focused",
                "focused": True,
                "window_handle": 1234,
            }

        desktop_tools._activate_existing_application = (
            fake_focused
        )

        success = desktop_tools.focus_application(
            "spotify"
        )

        assert success[
            "success"
        ] is True

        assert success[
            "status"
        ] == "focused"

        assert success[
            "focused"
        ] is True

        assert calls == [
            (
                "spotify",
                True,
            )
        ]

        # --------------------------------------------------
        # 2. A merely visible/shown window is NOT focus success.
        # --------------------------------------------------

        def fake_denied(
            target_id,
            require_focus=False,
        ):
            assert require_focus is True

            return {
                "success": False,
                "status": "foreground_denied",
                "focused": False,
            }

        desktop_tools._activate_existing_application = (
            fake_denied
        )

        denied = desktop_tools.focus_application(
            "spotify"
        )

        assert denied[
            "success"
        ] is False

        assert denied[
            "status"
        ] == "foreground_denied"

        assert (
            "didn't allow it to become the foreground window"
            in denied[
                "message"
            ]
        )

    finally:
        desktop_tools.os.name = (
            original_os_name
        )

        desktop_tools.get_desktop_target = (
            original_get_target
        )

        desktop_tools._activate_existing_application = (
            original_activate
        )

    print(
        "Mairon Phase 9.3.1 verified foreground focus tests: PASS"
    )


if __name__ == "__main__":
    run()
