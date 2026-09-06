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

    assert first.turn.intent == (
        "calculate_arithmetic"
    )

    assert first.direct_response == (
        "The total is 3,675."
    )

    # --------------------------------------------------
    # 1. Exact live follow-up from Oliver.
    # --------------------------------------------------

    doubled = core.prepare_turn(
        "double it"
    )

    assert doubled.turn.intent == (
        "calculate_arithmetic"
    )

    assert doubled.turn.is_follow_up is True

    assert doubled.turn.entities[
        "arithmetic_expression"
    ] == (
        "3675 * 2"
    )

    assert doubled.direct_response == (
        "The result is 7,350."
    )

    # --------------------------------------------------
    # 2. Chained follow-ups use the newest verified arithmetic result.
    # --------------------------------------------------

    doubled_again = core.prepare_turn(
        "double it"
    )

    assert doubled_again.direct_response == (
        "The result is 14,700."
    )

    halved = core.prepare_turn(
        "halve it"
    )

    assert halved.direct_response == (
        "The result is 7,350."
    )

    tripled = core.prepare_turn(
        "triple it"
    )

    assert tripled.direct_response == (
        "The result is 22,050."
    )

    # --------------------------------------------------
    # 3. Explicit operations against the active verified result.
    # --------------------------------------------------

    multiplied = core.prepare_turn(
        "multiply it by 4"
    )

    assert multiplied.direct_response == (
        "The result is 88,200."
    )

    divided = core.prepare_turn(
        "divide it by 2"
    )

    assert divided.direct_response == (
        "The result is 44,100."
    )

    added = core.prepare_turn(
        "add 900 to it"
    )

    assert added.direct_response == (
        "The total is 45,000."
    )

    subtracted = core.prepare_turn(
        "subtract 5,000 from it"
    )

    assert subtracted.direct_response == (
        "The result is 40,000."
    )

    # --------------------------------------------------
    # 4. "It" does not become magical global arithmetic context.
    # --------------------------------------------------

    fresh = MaironCore().prepare_turn(
        "double it"
    )

    assert fresh.turn.intent != (
        "calculate_arithmetic"
    )

    print(
        "Mairon Phase 10.5.2 arithmetic-result follow-up tests: PASS"
    )


if __name__ == "__main__":
    run()
