import sys
import ast
import types
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


# --------------------------------------------------
# Fake registry before workflow imports.
# Launch tests must never open real applications.
# --------------------------------------------------

fake_registry = types.ModuleType(
    "tools.tool_registry"
)

launch_calls = []


def fake_execute_tool(
    tool_name,
    arguments=None,
):
    arguments = arguments or {}

    launch_calls.append(
        (
            tool_name,
            dict(arguments),
        )
    )

    if tool_name == "launch_application":
        return {
            "success": True,
            "target_id": arguments.get(
                "app_name"
            ),
            "message": "Launch requested.",
        }

    return {
        "success": False,
        "message": "Unexpected tool call.",
    }


fake_registry.execute_tool = (
    fake_execute_tool
)

import tools

sys.modules[
    "tools.tool_registry"
] = fake_registry


from core.desktop_catalog import (
    extract_desktop_action_request,
)
from core.intent_router import (
    classify_turn,
)
import core.workflows.application_control as control_module
from core.orchestrator import (
    MaironCore,
)


def run():
    # --------------------------------------------------
    # 1. Named targets route deterministically.
    # --------------------------------------------------

    open_cases = (
        ("Open Chrome", "chrome"),
        ("Launch Spotify", "spotify"),
        ("Start Discord", "discord"),
        ("Open Steam", "steam"),
        ("Open VS Code", "vscode"),
        ("Open Downloads", "downloads"),
        (
            "Open my Mairon project in VS Code",
            "mairon_project",
        ),
    )

    for message, target_id in open_cases:
        turn = classify_turn(
            message
        )

        assert (
            turn.intent
            == "launch_application"
        ), (
            message,
            turn.to_dict(),
        )

        assert (
            turn.entities[
                "app_name"
            ]
            == target_id
        ), (
            message,
            turn.to_dict(),
        )

        assert (
            turn.preferred_authority
            == "desktop"
        )

    # --------------------------------------------------
    # 2. Compound action must not silently lose its second half.
    # --------------------------------------------------

    compound = classify_turn(
        "Open Chrome and search for weather in Sydney"
    )

    assert (
        compound.intent
        != "launch_application"
    )

    assert (
        extract_desktop_action_request(
            "Open Chrome and search for weather in Sydney"
        )
        is None
    )

    # --------------------------------------------------
    # 3. Full Core launch path remains model-free.
    # --------------------------------------------------

    launch_calls.clear()

    core = MaironCore()

    opened = core.prepare_turn(
        "Open Spotify"
    )

    assert opened.direct_response == (
        "Spotify's open."
    )

    assert launch_calls == [
        (
            "launch_application",
            {
                "app_name": "spotify",
            },
        )
    ]

    assert (
        core.conversation_state
        .active_desktop_target
        == "spotify"
    )

    # --------------------------------------------------
    # 4. Intervening banter does not erase desktop referent.
    # --------------------------------------------------

    banter = core.prepare_turn(
        "cheers cunt"
    )

    assert (
        banter.turn.intent
        in {
            "acknowledge",
            "casual_conversation",
        }
    )

    assert (
        core.conversation_state
        .active_desktop_target
        == "spotify"
    )

    # --------------------------------------------------
    # 5. Deictic close resolves from Core desktop referent state.
    # --------------------------------------------------

    original_close = (
        control_module.close_application
    )

    original_focus = (
        control_module.focus_application
    )

    close_calls = []
    focus_calls = []

    try:
        def fake_close(
            app_name,
        ):
            close_calls.append(
                app_name
            )

            return {
                "success": True,
                "status": "close_requested",
                "target_id": app_name,
            }

        def fake_focus(
            app_name,
        ):
            focus_calls.append(
                app_name
            )

            return {
                "success": True,
                "status": "focused",
                "target_id": app_name,
            }

        control_module.close_application = (
            fake_close
        )

        control_module.focus_application = (
            fake_focus
        )

        closed = core.prepare_turn(
            "actually close it"
        )

        assert (
            closed.turn.intent
            == "close_application"
        )

        assert (
            closed.turn.entities[
                "app_name"
            ]
            == "spotify"
        )

        assert (
            closed.turn.is_follow_up
            is True
        )

        assert close_calls == [
            "spotify"
        ]

        assert closed.direct_response == (
            "Spotify window's closed."
        )

        # --------------------------------------------------
        # 6. Named focus works and becomes the new desktop referent.
        # --------------------------------------------------

        focused = core.prepare_turn(
            "Bring Discord to the front"
        )

        assert (
            focused.turn.intent
            == "focus_application"
        )

        assert (
            focused.turn.entities[
                "app_name"
            ]
            == "discord"
        )

        assert focus_calls == [
            "discord"
        ]

        assert focused.direct_response == (
            "Discord's in front."
        )

        assert (
            core.conversation_state
            .active_desktop_target
            == "discord"
        )

        # --------------------------------------------------
        # 7. Deictic focus inherits Discord.
        # --------------------------------------------------

        focus_again = core.prepare_turn(
            "focus it"
        )

        assert (
            focus_again.turn.entities[
                "app_name"
            ]
            == "discord"
        )

        assert focus_calls == [
            "discord",
            "discord",
        ]

    finally:
        control_module.close_application = (
            original_close
        )

        control_module.focus_application = (
            original_focus
        )

    # --------------------------------------------------
    # 8. Unknown text never becomes arbitrary execution.
    # --------------------------------------------------

    unknown = classify_turn(
        "Open definitely-not-a-real-app.exe --do-bad-things"
    )

    assert unknown.intent != (
        "launch_application"
    )

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

    # Ignore comments/docstrings and inspect executable string literals only.
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
        "Mairon Phase 8.1 deterministic desktop actions / "
        "referent tests: PASS"
    )


if __name__ == "__main__":
    run()
