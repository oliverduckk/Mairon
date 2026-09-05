import sys
import ast
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from tools import desktop_tools


def run():
    original_target_pids = (
        desktop_tools._target_pids
    )

    original_target_window_pids = (
        desktop_tools._target_window_pids
    )

    original_windows = (
        desktop_tools
        ._top_level_windows_for_pids
    )

    original_show_focus = (
        desktop_tools
        ._show_and_focus_window
    )

    original_launch = (
        desktop_tools
        ._launch_process
    )

    original_os_name = (
        desktop_tools.os.name
    )

    launch_calls = []
    window_queries = []
    activation_calls = []

    try:
        # Simulate Windows even if this test is inspected elsewhere.
        desktop_tools.os.name = "nt"

        desktop_tools._target_pids = (
            lambda target_id: {
                111,
                222,
            }
            if target_id == "discord"
            else set()
        )

        desktop_tools._target_window_pids = (
            lambda target_id: {
                111,
                222,
            }
            if target_id == "discord"
            else set()
        )

        def fake_windows(
            pids,
            visible_only=True,
            target_id="",
        ):
            window_queries.append(
                (
                    visible_only,
                    target_id,
                )
            )

            if visible_only:
                return []

            # Discord is alive in the tray with one hidden titled main window.
            return [
                9001,
            ]

        desktop_tools._top_level_windows_for_pids = (
            fake_windows
        )

        def fake_show_focus(
            hwnd,
        ):
            activation_calls.append(
                hwnd
            )

            return {
                "visible": True,
                "focused": True,
            }

        desktop_tools._show_and_focus_window = (
            fake_show_focus
        )

        def fake_launch(
            command,
        ):
            launch_calls.append(
                command
            )

            return {
                "success": True,
            }

        desktop_tools._launch_process = (
            fake_launch
        )

        result = (
            desktop_tools
            .launch_application(
                "discord"
            )
        )

        assert result[
            "success"
        ] is True

        assert (
            result[
                "status"
            ]
            == "existing_window_activated"
        )

        assert activation_calls == [
            9001
        ]

        # Critical invariant: do NOT spawn a secondary Discord process when
        # Core can recover the existing hidden tray-backed window.
        assert launch_calls == []

        assert window_queries == [
            (
                True,
                "discord",
            ),
            (
                False,
                "discord",
            ),
        ]

    finally:
        desktop_tools._target_pids = (
            original_target_pids
        )

        desktop_tools._target_window_pids = (
            original_target_window_pids
        )

        desktop_tools._top_level_windows_for_pids = (
            original_windows
        )

        desktop_tools._show_and_focus_window = (
            original_show_focus
        )

        desktop_tools._launch_process = (
            original_launch
        )

        desktop_tools.os.name = (
            original_os_name
        )

    provider_path = (
        SRC_DIR
        / "tools"
        / "desktop_tools.py"
    )

    source = provider_path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(
            provider_path
        ),
    )

    # --------------------------------------------------
    # Architecture guard: no shell=True anywhere.
    # --------------------------------------------------

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        for keyword in node.keywords:
            if (
                keyword.arg == "shell"
                and isinstance(
                    keyword.value,
                    ast.Constant,
                )
                and keyword.value.value is True
            ):
                raise AssertionError(
                    "desktop_tools.py must not execute subprocesses with shell=True"
                )

    # --------------------------------------------------
    # Architecture guard: no executable taskkill/PowerShell command strings.
    #
    # Comments and docstrings are deliberately ignored. Phase 8.2 documents
    # that it does *not* use those mechanisms, which should not fail the test.
    # --------------------------------------------------

    docstring_nodes = set()

    for owner in ast.walk(
        tree
    ):
        if not isinstance(
            owner,
            (
                ast.Module,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            continue

        if not owner.body:
            continue

        first = owner.body[0]

        if (
            isinstance(
                first,
                ast.Expr,
            )
            and isinstance(
                first.value,
                ast.Constant,
            )
            and isinstance(
                first.value.value,
                str,
            )
        ):
            docstring_nodes.add(
                id(
                    first.value
                )
            )

    executable_strings = []

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.Constant,
            )
            and isinstance(
                node.value,
                str,
            )
            and id(
                node
            )
            not in docstring_nodes
        ):
            executable_strings.append(
                node.value.lower()
            )

    executable_text = "\n".join(
        executable_strings
    )

    assert "taskkill" not in executable_text
    assert "powershell" not in executable_text

    print(
        "Mairon Phase 8.1.1 existing hidden-window reopen tests: PASS"
    )


if __name__ == "__main__":
    run()
