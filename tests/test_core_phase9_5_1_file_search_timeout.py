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


import core.desktop_agent_client as agent_client


def run():
    # --------------------------------------------------
    # 1. File search gets a longer bounded timeout than generic actions.
    # --------------------------------------------------

    original_call = (
        agent_client.call_desktop_agent
    )

    calls = []

    try:
        def fake_call(
            action,
            args=None,
            **kwargs,
        ):
            calls.append({
                "action": action,
                "args": dict(
                    args
                    or {}
                ),
                "kwargs": dict(
                    kwargs
                ),
            })

            return {
                "success": True,
                "status": "search_completed",
                "matches": [],
            }

        agent_client.call_desktop_agent = (
            fake_call
        )

        result = (
            agent_client
            .search_approved_local_files_via_agent(
                "drivers license"
            )
        )

        assert result[
            "success"
        ] is True

        assert calls == [
            {
                "action": "search_approved_local_files",
                "args": {
                    "query": "drivers license",
                },
                "kwargs": {
                    "timeout": 15.0,
                },
            }
        ]

        # Explicit callers may still choose a smaller timeout.
        calls.clear()

        agent_client.search_approved_local_files_via_agent(
            "resume",
            timeout=7.5,
        )

        assert calls[
            0
        ][
            "kwargs"
        ][
            "timeout"
        ] == 7.5

    finally:
        agent_client.call_desktop_agent = (
            original_call
        )

    # --------------------------------------------------
    # 2. Agent response writer handles normal disconnect exceptions.
    # --------------------------------------------------

    agent_path = (
        SRC_DIR
        / "desktop_agent.py"
    )

    tree = ast.parse(
        agent_path.read_text(
            encoding="utf-8",
        ),
        filename=str(
            agent_path
        ),
    )

    handled_names = set()

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.ExceptHandler,
        ):
            continue

        handler_type = node.type

        if isinstance(
            handler_type,
            ast.Tuple,
        ):
            for item in handler_type.elts:
                if isinstance(
                    item,
                    ast.Name,
                ):
                    handled_names.add(
                        item.id
                    )

        elif isinstance(
            handler_type,
            ast.Name,
        ):
            handled_names.add(
                handler_type.id
            )

    assert {
        "BrokenPipeError",
        "ConnectionAbortedError",
        "ConnectionResetError",
    }.issubset(
        handled_names
    )

    print(
        "Mairon Phase 9.5.1 cold-file-search timeout/disconnect tests: PASS"
    )


if __name__ == "__main__":
    run()
