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


from core.steam_library import (
    derive_game_title_aliases,
    resolve_installed_steam_game,
)


def run():
    games = [
        {
            "appid": "730",
            "name": "Counter-Strike 2",
        },
        {
            "appid": "550",
            "name": "Left 4 Dead 2",
        },
        {
            "appid": "346900",
            "name": "AdVenture Capitalist",
        },
    ]

    assert (
        derive_game_title_aliases(
            "Counter-Strike 2"
        )
        == [
            "cs2",
            "cs",
        ]
    )

    assert (
        derive_game_title_aliases(
            "Left 4 Dead 2"
        )
        == [
            "l4d2",
            "l4d",
        ]
    )

    cs = resolve_installed_steam_game(
        requested_title="cs",
        games=games,
    )

    assert cs[
        "status"
    ] == "matched"

    assert cs[
        "match"
    ][
        "appid"
    ] == "730"

    l4d = resolve_installed_steam_game(
        requested_title="l4d",
        games=games,
    )

    assert l4d[
        "status"
    ] == "matched"

    assert l4d[
        "match"
    ][
        "appid"
    ] == "550"

    # Ambiguous shortened aliases must never guess.
    ambiguous_games = [
        {
            "appid": "1",
            "name": "Cool Story 2",
        },
        {
            "appid": "2",
            "name": "Counter-Strike 2",
        },
    ]

    ambiguous = resolve_installed_steam_game(
        requested_title="cs",
        games=ambiguous_games,
    )

    assert ambiguous[
        "status"
    ] == "ambiguous"

    print(
        "Mairon Phase 8.6.1 Steam secondary alias tests: PASS"
    )


if __name__ == "__main__":
    run()
