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


from core.orchestrator import (
    MaironCore,
)


def run():
    core = MaironCore()

    first = core.prepare_turn(
        "add 557, 528, 527, 493, 452 and 1118"
    )

    assert first.direct_response == (
        "The total is 3,675."
    )

    tripled = core.prepare_turn(
        "triple it"
    )

    assert tripled.direct_response == (
        "The result is 11,025."
    )

    # --------------------------------------------------
    # 1. Exact live failure: square the active verified result.
    # --------------------------------------------------

    squared = core.prepare_turn(
        "square it"
    )

    assert squared.turn.intent == (
        "calculate_arithmetic"
    )

    assert squared.turn.is_follow_up is True

    assert squared.turn.entities[
        "arithmetic_expression"
    ] == (
        "11025 ** 2"
    )

    assert squared.direct_response == (
        "The result is 121,550,625."
    )

    # --------------------------------------------------
    # 2. Cube operates on the newest verified result.
    # --------------------------------------------------

    cubed = core.prepare_turn(
        "cube it"
    )

    assert cubed.turn.intent == (
        "calculate_arithmetic"
    )

    assert cubed.turn.is_follow_up is True

    assert cubed.turn.entities[
        "arithmetic_expression"
    ] == (
        "121550625 ** 3"
    )

    assert cubed.direct_response == (
        "The result is 1,795,856,326,022,129,150,390,625."
    )

    # --------------------------------------------------
    # 3. Explicit integer power syntax is deterministic too.
    # --------------------------------------------------

    fresh = MaironCore()

    base = fresh.prepare_turn(
        "what is 5 + 5?"
    )

    assert base.direct_response == (
        "The total is 10."
    )

    fourth = fresh.prepare_turn(
        "raise it to the 4th power"
    )

    assert fourth.turn.intent == (
        "calculate_arithmetic"
    )

    assert fourth.direct_response == (
        "The result is 10,000."
    )

    second = fresh.prepare_turn(
        "it to the 2nd power"
    )

    assert second.direct_response == (
        "The result is 100,000,000."
    )

    # --------------------------------------------------
    # 4. Power referents are not inferred without active arithmetic state.
    # --------------------------------------------------

    no_context = MaironCore().prepare_turn(
        "square it"
    )

    assert no_context.turn.intent != (
        "calculate_arithmetic"
    )

    print(
        "Mairon Phase 10.5.4 arithmetic power follow-up tests: PASS"
    )


if __name__ == "__main__":
    run()
