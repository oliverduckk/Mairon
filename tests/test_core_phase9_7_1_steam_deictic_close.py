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

from core.conversation_state import (
    ConversationState,
)
from core.intent_router import (
    classify_turn,
)
from core.orchestrator import (
    MaironCore,
)


def run():
    # --------------------------------------------------
    # 1. Deictic Steam close resolves against Core-owned game referent.
    # --------------------------------------------------

    state = ConversationState()

    state.active_steam_game_title = (
        "AdVenture Capitalist"
    )

    state.active_desktop_target = None

    turn = classify_turn(
        "close it",
        conversation_state=state,
    )

    assert turn.intent == (
        "close_steam_game"
    )

    assert turn.is_follow_up is True

    assert turn.entities[
        "steam_game_title"
    ] == (
        "AdVenture Capitalist"
    )

    assert turn.resolved_referents[
        "it"
    ] == (
        "AdVenture Capitalist"
    )

    # --------------------------------------------------
    # 2. End-to-end: launch referent -> "close it" uses same game title.
    # --------------------------------------------------

    original_launch = (
        orchestrator_module
        .launch_installed_steam_game
    )

    original_discover = (
        orchestrator_module
        .discover_installed_steam_games
    )

    try:
        def fake_launch(
            requested_title,
        ):
            from core.workflow_result import (
                WorkflowResult,
            )

            return WorkflowResult(
                success=True,
                status="steam_game_launch_requested",
                answer_fact=(
                    "Launching AdVenture Capitalist through Steam."
                ),
                data={
                    "requested_title": requested_title,
                    "game_name": "AdVenture Capitalist",
                    "appid": "346900",
                },
            )

        orchestrator_module.launch_installed_steam_game = (
            fake_launch
        )

        orchestrator_module.discover_installed_steam_games = (
            lambda: [
                {
                    "appid": "346900",
                    "name": "AdVenture Capitalist",
                }
            ]
        )

        core = MaironCore()

        opened = core.prepare_turn(
            "open adventure capitalist"
        )

        assert opened.turn.intent == (
            "launch_steam_game"
        )

        assert (
            core.conversation_state
            .active_steam_game_title
            == "adventure capitalist"
        )

        closed = core.prepare_turn(
            "close it"
        )

        assert closed.turn.intent == (
            "close_steam_game"
        )

        assert closed.turn.is_follow_up is True

        assert closed.turn.entities[
            "steam_game_title"
        ] == (
            "adventure capitalist"
        )

        assert closed.direct_response == (
            "I can launch AdVenture Capitalist, but I don't have a "
            "safe verified way to close Steam games yet."
        )

    finally:
        orchestrator_module.launch_installed_steam_game = (
            original_launch
        )

        orchestrator_module.discover_installed_steam_games = (
            original_discover
        )

    print(
        "Mairon Phase 9.7.1 Steam deictic close referent tests: PASS"
    )


if __name__ == "__main__":
    run()
