import ast
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


import core.orchestrator as orchestrator_module
import core.workflows.file_actions as file_workflow
import core.workflows.steam_game_launch as steam_workflow

from core.desktop_agent_protocol import (
    build_request,
    validate_request,
)
from core.file_catalog import (
    extract_local_file_action_request,
    resolve_trusted_folder_alias,
)
from core.intent_router import (
    classify_turn,
)
from core.orchestrator import (
    MaironCore,
)


def run():
    # --------------------------------------------------
    # 1. Trusted folder parsing is semantic only: no Windows path in Core.
    # --------------------------------------------------

    folder = resolve_trusted_folder_alias(
        "pictures"
    )

    assert folder == {
        "folder_id": "pictures",
        "display_name": "Pictures",
    }

    parsed = extract_local_file_action_request(
        "open pictures"
    )

    assert parsed[
        "action"
    ] == "open_folder"

    assert parsed[
        "folder_id"
    ] == "pictures"

    assert "path" not in parsed

    turn = classify_turn(
        "open pictures"
    )

    assert turn.intent == "open_local_folder"

    assert turn.entities[
        "local_folder_id"
    ] == "pictures"

    assert "local_file_path" not in turn.entities

    # --------------------------------------------------
    # 2. Trusted-folder protocol accepts only approved semantic IDs.
    # --------------------------------------------------

    request = validate_request(
        build_request(
            request_id="phase9-7-folder",
            action="open_trusted_folder",
            args={
                "folder_id": "pictures",
            },
        )
    )

    assert request[
        "args"
    ] == {
        "folder_id": "pictures",
    }

    for bad_args in (
        {
            "folder_id": r"C:\Users\Oliver\Pictures",
        },
        {
            "folder_id": "pictures",
            "path": r"C:\Windows",
        },
    ):
        try:
            validate_request({
                "version": "1",
                "request_id": "phase9-7-bad-folder",
                "action": "open_trusted_folder",
                "args": bad_args,
            })

        except ValueError:
            pass

        else:
            raise AssertionError(
                "Trusted-folder protocol accepted path-like authority."
            )

    # --------------------------------------------------
    # 3. Core folder workflow crosses Agent with folder_id only.
    # --------------------------------------------------

    original_folder_call = (
        file_workflow.open_trusted_folder_via_agent
    )

    folder_calls = []

    try:
        def fake_folder_call(
            folder_id,
        ):
            folder_calls.append(
                folder_id
            )

            return {
                "success": True,
                "status": "folder_opened",
                "folder_id": folder_id,
                "path": r"D:\Pictures",
            }

        file_workflow.open_trusted_folder_via_agent = (
            fake_folder_call
        )

        core = MaironCore()

        decision = core.prepare_turn(
            "open pictures"
        )

        assert decision.direct_response == (
            "Pictures is open."
        )

        assert folder_calls == [
            "pictures"
        ]

        # The Agent may internally report the concrete Windows path, but Core
        # does not promote it into a local-file referent.
        assert (
            core.conversation_state
            .active_local_file_path
            is None
        )

    finally:
        file_workflow.open_trusted_folder_via_agent = (
            original_folder_call
        )

    # --------------------------------------------------
    # 4. Steam close semantics use Agent-backed discovery, not local Windows.
    # --------------------------------------------------

    original_discover = (
        orchestrator_module.discover_installed_steam_games
    )

    steam_calls = []

    try:
        def fake_discover():
            steam_calls.append(
                "list"
            )

            return [
                {
                    "appid": "346900",
                    "name": "AdVenture Capitalist",
                }
            ]

        orchestrator_module.discover_installed_steam_games = (
            fake_discover
        )

        core = MaironCore()

        closed = core.prepare_turn(
            "close adventure capitalist"
        )

        assert steam_calls == [
            "list"
        ]

        assert (
            "safe verified way to close Steam games yet"
            in closed.direct_response
        )

    finally:
        orchestrator_module.discover_installed_steam_games = (
            original_discover
        )

    # The orchestrator must source discovery from the Agent-backed workflow,
    # not directly from core.steam_library.
    orch_path = (
        SRC_DIR
        / "core"
        / "orchestrator.py"
    )

    orch_tree = ast.parse(
        orch_path.read_text(
            encoding="utf-8",
        ),
        filename=str(
            orch_path
        ),
    )

    forbidden_import = False

    for node in ast.walk(
        orch_tree
    ):
        if not isinstance(
            node,
            ast.ImportFrom,
        ):
            continue

        if node.module != "core.steam_library":
            continue

        imported_names = {
            alias.name
            for alias in node.names
        }

        if "discover_installed_steam_games" in imported_names:
            forbidden_import = True

    assert forbidden_import is False

    # --------------------------------------------------
    # 5. Desktop-facing workflows do not directly import Windows tools.
    # --------------------------------------------------

    workflow_names = (
        "application_launch.py",
        "application_control.py",
        "browser_search.py",
        "file_actions.py",
        "steam_game_launch.py",
    )

    forbidden_modules = {
        "tools.desktop_tools",
        "tools.file_tools",
    }

    for filename in workflow_names:
        path = (
            SRC_DIR
            / "core"
            / "workflows"
            / filename
        )

        tree = ast.parse(
            path.read_text(
                encoding="utf-8",
            ),
            filename=str(
                path
            ),
        )

        direct_tool_imports = []

        for node in ast.walk(
            tree
        ):
            if isinstance(
                node,
                ast.ImportFrom,
            ) and node.module in forbidden_modules:
                direct_tool_imports.append(
                    node.module
                )

        assert direct_tool_imports == [], (
            filename,
            direct_tool_imports,
        )

    print(
        "Mairon Phase 9.7 Windows execution boundary audit tests: PASS"
    )


if __name__ == "__main__":
    run()
