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


import core.orchestrator as orchestrator_module
from core.desktop_catalog import (
    extract_steam_game_close_candidate,
)
from core.steam_library import (
    derive_game_title_acronym,
    resolve_installed_steam_game,
)
from core.orchestrator import (
    MaironCore,
)


def run():
    games = [
        {
            "appid": "730",
            "name": "Counter-Strike 2",
            "installdir": "Counter-Strike Global Offensive",
            "install_path": r"E:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive",
        },
        {
            "appid": "346900",
            "name": "AdVenture Capitalist",
            "installdir": "AdVenture Capitalist",
            "install_path": r"E:\SteamLibrary\steamapps\common\AdVenture Capitalist",
        },
    ]

    # --------------------------------------------------
    # 1. Acronym aliases are derived, not hard-coded.
    # --------------------------------------------------

    assert (
        derive_game_title_acronym(
            "Counter-Strike 2"
        )
        == "cs2"
    )

    assert (
        derive_game_title_acronym(
            "AdVenture Capitalist"
        )
        == "ac"
    )

    resolution = (
        resolve_installed_steam_game(
            requested_title="cs2",
            games=games,
        )
    )

    assert resolution[
        "status"
    ] == "matched"

    assert resolution[
        "match"
    ][
        "appid"
    ] == "730"

    assert resolution.get(
        "match_type"
    ) == "derived_acronym"

    # --------------------------------------------------
    # 2. Close syntax is recognised without stealing desktop apps.
    # --------------------------------------------------

    close = (
        extract_steam_game_close_candidate(
            "close counter strike 2"
        )
    )

    assert close == {
        "title": "counter strike 2",
    }

    polite = (
        extract_steam_game_close_candidate(
            "I want you to close counter strike 2"
        )
    )

    assert polite == {
        "title": "counter strike 2",
    }

    # --------------------------------------------------
    # 3. Core owns unsupported game-close capability.
    # --------------------------------------------------

    original_discover = (
        orchestrator_module.discover_installed_steam_games
    )

    try:
        orchestrator_module.discover_installed_steam_games = (
            lambda: list(
                games
            )
        )

        core = MaironCore()

        decision = core.prepare_turn(
            "close counter strike 2"
        )

        assert (
            decision.turn.intent
            == "close_steam_game"
        )

        assert (
            decision.direct_response
            == (
                "I can launch Counter-Strike 2, but I don't have a "
                "safe verified way to close Steam games yet."
            )
        )

        decision2 = core.prepare_turn(
            "I want you to close counter strike 2"
        )

        assert (
            decision2.turn.intent
            == "close_steam_game"
        )

        assert "safe verified way" in (
            decision2.direct_response
        )

    finally:
        orchestrator_module.discover_installed_steam_games = (
            original_discover
        )

    print(
        "Mairon Phase 8.6 Steam command semantics tests: PASS"
    )


if __name__ == "__main__":
    run()
