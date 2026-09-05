import sys
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


import core.workflows.application_launch as application_launch

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
    #
    # Phase 9.2 architecture:
    # Core -> application workflow -> Desktop Agent client.
    #
    # This regression deliberately mocks the agent boundary rather
    # than the obsolete in-process tool_registry execution path.
    # --------------------------------------------------

    agent_calls = []

    original_launch_via_agent = (
        application_launch
        .launch_application_via_agent
    )

    def fake_launch_application_via_agent(
        app_name,
    ):
        app_name = str(
            app_name
            or ""
        ).strip().lower()

        agent_calls.append(
            app_name
        )

        if app_name in {
            "calculator",
            "notepad",
        }:
            return {
                "success": True,
                "status": "launch_requested",
                "target_id": app_name,
                "message": (
                    f"{app_name.title()} launch requested."
                ),
            }

        return {
            "success": False,
            "status": "launch_failed",
            "message": (
                "Unexpected Desktop Agent launch request."
            ),
        }

    try:
        application_launch.launch_application_via_agent = (
            fake_launch_application_via_agent
        )

        core = MaironCore()

        decision = core.prepare_turn(
            exact
        )

        assert decision.direct_response == (
            "Calculator's open."
        )

        assert agent_calls == [
            "calculator"
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

    finally:
        application_launch.launch_application_via_agent = (
            original_launch_via_agent
        )

    print(
        "Deterministic application-launch Core regression tests: PASS"
    )


if __name__ == "__main__":
    run()
