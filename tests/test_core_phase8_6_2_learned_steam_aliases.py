import json
import os
import sys
import tempfile
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


import core.orchestrator as orchestrator_module
import core.workflows.steam_game_launch as steam_workflow
from core.orchestrator import (
    MaironCore,
)
from core.steam_alias_store import (
    get_steam_game_alias,
)


def run():
    original_alias_path = os.environ.get(
        "MAIRON_STEAM_ALIAS_PATH"
    )

    original_discover = (
        steam_workflow.discover_installed_steam_games
    )

    original_launch = (
        steam_workflow.launch_steam_game_appid
    )

    games = [
        {
            "appid": "359550",
            "name": "Tom Clancy's Rainbow Six Siege",
            "manifest_path": "siege.acf",
        },
        {
            "appid": "1172620",
            "name": "Sea of Thieves",
            "manifest_path": "sot.acf",
        },
        {
            "appid": "674940",
            "name": "Stick Fight: The Game",
            "manifest_path": "stick.acf",
        },
    ]

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            alias_file = (
                Path(
                    temp_dir
                )
                / "steam_game_aliases.json"
            )

            os.environ[
                "MAIRON_STEAM_ALIAS_PATH"
            ] = str(
                alias_file
            )

            steam_workflow.discover_installed_steam_games = (
                lambda: list(
                    games
                )
            )

            launched = []

            def fake_launch(
                appid,
            ):
                launched.append(
                    str(
                        appid
                    )
                )

                return {
                    "success": True,
                    "status": "launch_requested",
                }

            steam_workflow.launch_steam_game_appid = (
                fake_launch
            )

            core = MaironCore()

            # --------------------------------------------------
            # 1. Ambiguous shorthand creates Core candidate state.
            # --------------------------------------------------

            first = core.prepare_turn(
                "open siege"
            )

            assert (
                first.workflow_result.status
                == "ambiguous_game"
            )

            assert (
                core.conversation_state
                .active_steam_game_alias_query
                == "siege"
            )

            assert len(
                core.conversation_state
                .active_steam_game_candidates
            ) == 3

            # --------------------------------------------------
            # 2. Natural confirmation selects one verified candidate.
            # --------------------------------------------------

            confirmed = core.prepare_turn(
                "Rainbow Six Siege"
            )

            assert (
                confirmed.turn.intent
                == "confirm_steam_game_alias"
            )

            assert launched[
                -1
            ] == "359550"

            assert (
                '"siege"'
                in confirmed.direct_response
            )

            learned = get_steam_game_alias(
                "siege"
            )

            assert learned is not None
            assert learned[
                "appid"
            ] == "359550"

            # --------------------------------------------------
            # 3. New Core/session uses persisted learned alias.
            # --------------------------------------------------

            second_core = MaironCore()

            second = second_core.prepare_turn(
                "open siege"
            )

            assert (
                second.workflow_result.success
                is True
            )

            assert launched[
                -1
            ] == "359550"

            assert (
                second.workflow_result.data[
                    "game_name"
                ]
                == "Tom Clancy's Rainbow Six Siege"
            )

            # --------------------------------------------------
            # 4. Ordinal clarification is also deterministic.
            # --------------------------------------------------

            alias_file.unlink(
                missing_ok=True
            )

            third_core = MaironCore()

            third_core.prepare_turn(
                "open siege"
            )

            ordinal = third_core.prepare_turn(
                "the first one"
            )

            assert (
                ordinal.turn.intent
                == "confirm_steam_game_alias"
            )

            assert launched[
                -1
            ] == "359550"

    finally:
        steam_workflow.discover_installed_steam_games = (
            original_discover
        )

        steam_workflow.launch_steam_game_appid = (
            original_launch
        )

        if original_alias_path is None:
            os.environ.pop(
                "MAIRON_STEAM_ALIAS_PATH",
                None,
            )
        else:
            os.environ[
                "MAIRON_STEAM_ALIAS_PATH"
            ] = original_alias_path

    print(
        "Mairon Phase 8.6.2 learned Steam alias tests: PASS"
    )


if __name__ == "__main__":
    run()
