import sys
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
# Fake tool registry.
#
# This test does not open real applications.
# --------------------------------------------------

fake_registry = types.ModuleType(
    "tools.tool_registry"
)

tool_calls = []


def fake_execute_tool(
    tool_name,
    arguments=None,
):
    arguments = arguments or {}

    tool_calls.append(
        (
            tool_name,
            dict(
                arguments
            ),
        )
    )

    if (
        tool_name
        == "launch_application"
        and arguments.get(
            "app_name"
        )
        in {
            "calculator",
            "notepad",
        }
    ):
        return {
            "success": True,
            "message": (
                "Application launched."
            ),
        }

    return {
        "success": False,
        "message": (
            "Unexpected tool call."
        ),
    }


fake_registry.execute_tool = (
    fake_execute_tool
)

import tools

sys.modules[
    "tools.tool_registry"
] = fake_registry


from core.intent_router import (
    classify_turn,
)
from core.orchestrator import (
    MaironCore,
)


def run():
    # --------------------------------------------------
    # Exact STT transcript that failed live.
    # --------------------------------------------------

    exact = (
        "Can you please open the calculator?"
    )

    turn = classify_turn(
        exact
    )

    assert turn.intent == (
        "launch_application"
    )

    assert turn.entities[
        "app_name"
    ] == "calculator"

    assert turn.preferred_authority == (
        "desktop"
    )

    assert turn.should_use_tools is True

    # --------------------------------------------------
    # Full Core path must launch without Qwen.
    # --------------------------------------------------

    tool_calls.clear()

    core = MaironCore()

    decision = core.prepare_turn(
        exact
    )

    assert decision.direct_response == (
        "Calculator's open."
    )

    assert tool_calls == [
        (
            "launch_application",
            {
                "app_name": "calculator",
            },
        )
    ]

    # --------------------------------------------------
    # Natural phrasing coverage.
    # --------------------------------------------------

    cases = [
        (
            "Open calculator",
            "calculator",
        ),
        (
            "Open the calculator",
            "calculator",
        ),
        (
            "Could you open the calculator?",
            "calculator",
        ),
        (
            "Can you please open up the calculator?",
            "calculator",
        ),
        (
            "Launch calculator",
            "calculator",
        ),
        (
            "Please start the calculator",
            "calculator",
        ),
        (
            "Can you open Notepad?",
            "notepad",
        ),
        (
            "Please launch the notepad",
            "notepad",
        ),
        (
            "Open up Notepad",
            "notepad",
        ),
    ]

    for message, expected_app in cases:
        candidate = classify_turn(
            message
        )

        assert (
            candidate.intent
            == "launch_application"
        ), (
            message,
            candidate.to_dict(),
        )

        assert (
            candidate.entities[
                "app_name"
            ]
            == expected_app
        ), (
            message,
            candidate.to_dict(),
        )

    # --------------------------------------------------
    # Random "open" wording must not be hijacked.
    # --------------------------------------------------

    unrelated = classify_turn(
        "Can you explain open source software?"
    )

    assert unrelated.intent != (
        "launch_application"
    )

    print(
        "Deterministic application-launch Core regression tests: PASS"
    )


if __name__ == "__main__":
    run()
