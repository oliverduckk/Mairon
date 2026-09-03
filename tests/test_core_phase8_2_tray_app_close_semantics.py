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


from core.desktop_catalog import (
    DESKTOP_TARGETS,
    extract_desktop_action_request,
)
from tools import desktop_tools
import core.workflows.application_control as control_module


def run():
    # --------------------------------------------------
    # 1. Only known tray-backed apps get full-quit close semantics.
    # --------------------------------------------------

    assert (
        DESKTOP_TARGETS[
            "discord"
        ][
            "close_behavior"
        ]
        == "quit_process"
    )

    assert (
        DESKTOP_TARGETS[
            "lunar_client"
        ][
            "close_behavior"
        ]
        == "quit_process"
    )

    for target_id in (
        "calculator",
        "notepad",
        "chrome",
        "spotify",
        "steam",
        "vscode",
        "mairon_project",
    ):
        assert (
            DESKTOP_TARGETS[
                target_id
            ][
                "close_behavior"
            ]
            == "graceful_window"
        ), target_id

    # --------------------------------------------------
    # 2. Lunar participates in normal deterministic intent extraction.
    # --------------------------------------------------

    lunar_open = (
        extract_desktop_action_request(
            "Open Lunar Client"
        )
    )

    assert lunar_open == {
        "action": "open",
        "target_id": "lunar_client",
        "display_name": "Lunar Client",
        "inherited": False,
    }

    lunar_close = (
        extract_desktop_action_request(
            "close lunar"
        )
    )

    assert lunar_close[
        "action"
    ] == "close"

    assert lunar_close[
        "target_id"
    ] == "lunar_client"

    # --------------------------------------------------
    # 3. Discord close chooses verified process quit, not WM_CLOSE.
    # --------------------------------------------------

    original_os_name = (
        desktop_tools.os.name
    )

    original_terminate = (
        desktop_tools._terminate_target_processes
    )

    original_target_pids = (
        desktop_tools._target_pids
    )

    original_windows = (
        desktop_tools._top_level_windows_for_pids
    )

    terminate_calls = []
    window_calls = []

    try:
        desktop_tools.os.name = "nt"

        def fake_terminate(
            target_id,
            verification_timeout_seconds=1.5,
        ):
            terminate_calls.append(
                target_id
            )

            return {
                "success": True,
                "status": "terminated",
                "target_id": target_id,
                "terminated_pids": [
                    101,
                    102,
                ],
            }

        desktop_tools._terminate_target_processes = (
            fake_terminate
        )

        def fake_target_pids(
            target_id,
        ):
            return {
                101,
                102,
            }

        desktop_tools._target_pids = (
            fake_target_pids
        )

        def fake_windows(
            pids,
            visible_only=True,
        ):
            window_calls.append(
                (
                    set(
                        pids
                    ),
                    visible_only,
                )
            )

            return [
                9999,
            ]

        desktop_tools._top_level_windows_for_pids = (
            fake_windows
        )

        result = (
            desktop_tools.close_application(
                "discord"
            )
        )

        assert result[
            "success"
        ] is True

        assert result[
            "status"
        ] == "terminated"

        assert result[
            "close_behavior"
        ] == "quit_process"

        assert terminate_calls == [
            "discord"
        ]

        # No WM_CLOSE window enumeration should occur for the known exception.
        assert window_calls == []

    finally:
        desktop_tools.os.name = (
            original_os_name
        )

        desktop_tools._terminate_target_processes = (
            original_terminate
        )

        desktop_tools._target_pids = (
            original_target_pids
        )

        desktop_tools._top_level_windows_for_pids = (
            original_windows
        )

    # --------------------------------------------------
    # 4. Normal app still uses graceful close and never process termination.
    # --------------------------------------------------

    original_os_name = (
        desktop_tools.os.name
    )

    original_terminate = (
        desktop_tools._terminate_target_processes
    )

    original_target_pids = (
        desktop_tools._target_pids
    )

    original_windows = (
        desktop_tools._top_level_windows_for_pids
    )

    terminate_calls = []

    class _FakeUser32:
        def PostMessageW(
            self,
            hwnd,
            message,
            wparam,
            lparam,
        ):
            return 1

    class _FakeWindll:
        user32 = _FakeUser32()

    original_windll = (
        desktop_tools.ctypes.windll
    )

    try:
        desktop_tools.os.name = "nt"

        desktop_tools._terminate_target_processes = (
            lambda target_id, verification_timeout_seconds=1.5: (
                terminate_calls.append(
                    target_id
                )
                or {
                    "success": True,
                }
            )
        )

        desktop_tools._target_pids = (
            lambda target_id: {
                303
            }
        )

        desktop_tools._top_level_windows_for_pids = (
            lambda pids, visible_only=True: [
                7001
            ]
        )

        desktop_tools.ctypes.windll = (
            _FakeWindll()
        )

        result = (
            desktop_tools.close_application(
                "spotify"
            )
        )

        assert result[
            "success"
        ] is True

        assert result[
            "close_behavior"
        ] == "graceful_window"

        assert terminate_calls == []

    finally:
        desktop_tools.os.name = (
            original_os_name
        )

        desktop_tools._terminate_target_processes = (
            original_terminate
        )

        desktop_tools._target_pids = (
            original_target_pids
        )

        desktop_tools._top_level_windows_for_pids = (
            original_windows
        )

        desktop_tools.ctypes.windll = (
            original_windll
        )

    # --------------------------------------------------
    # 5. Workflow language reflects full quit vs window close.
    # --------------------------------------------------

    original_close = (
        control_module.close_application
    )

    try:
        control_module.close_application = (
            lambda app_name: {
                "success": True,
                "status": "terminated",
                "target_id": app_name,
                "close_behavior": "quit_process",
            }
        )

        result = (
            control_module
            .control_approved_application(
                app_name="discord",
                action="close",
            )
        )

        assert result.answer_fact == (
            "Discord's closed."
        )

    finally:
        control_module.close_application = (
            original_close
        )

    # --------------------------------------------------
    # 6. Architecture guard: no generic shell/taskkill control.
    # --------------------------------------------------

    desktop_path = (
        SRC_DIR
        / "tools"
        / "desktop_tools.py"
    )

    desktop_source = desktop_path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        desktop_source,
        filename=str(
            desktop_path
        ),
    )

    # No subprocess call may opt into shell execution.
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

    # Comments/docstrings may explain forbidden mechanisms; only executable
    # string literals are relevant to the architecture guard.
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
        "Mairon Phase 8.2 tray-backed app close semantics tests: PASS"
    )


if __name__ == "__main__":
    run()
