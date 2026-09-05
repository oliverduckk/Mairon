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


from core.intent_router import (
    classify_turn,
)


def run():
    # --------------------------------------------------
    # 1. Gmail-specific open/read syntax beats generic Steam launch.
    # --------------------------------------------------

    turn = classify_turn(
        "open the latest email from prosple"
    )

    assert (
        turn.intent
        == "email_read"
    ), turn.intent

    assert (
        turn.preferred_authority
        == "gmail"
    )

    assert (
        str(
            turn.entities.get(
                "search_text",
                "",
            )
            or ""
        ).lower()
        == "prosple"
    ), turn.entities

    # --------------------------------------------------
    # 2. Generic Steam launch still works after precedence change.
    # --------------------------------------------------

    steam = classify_turn(
        "open counter strike 2"
    )

    assert (
        steam.intent
        == "launch_steam_game"
    ), steam.intent

    assert (
        steam.preferred_authority
        == "desktop"
    )

    # --------------------------------------------------
    # 3. Existing broad Gmail search still wins.
    # --------------------------------------------------

    gmail = classify_turn(
        "find emails from prosple"
    )

    assert (
        gmail.intent
        == "email_search"
    ), gmail.intent

    print(
        "Mairon Phase 8.7 cross-domain action precedence tests: PASS"
    )


if __name__ == "__main__":
    run()
