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


from core.arithmetic import (
    ArithmeticEvaluationError,
    evaluate_arithmetic_expression,
    extract_arithmetic_request,
)
from core.intent_router import (
    classify_turn,
)
from core.orchestrator import (
    MaironCore,
)


def run():
    # --------------------------------------------------
    # 1. The exact live failure now routes to deterministic Core arithmetic.
    # --------------------------------------------------

    request_text = (
        "add 557, 528, 527, 493, 452 and 1118"
    )

    turn = classify_turn(
        request_text
    )

    assert turn.intent == (
        "calculate_arithmetic"
    )

    assert turn.preferred_authority == (
        "core_arithmetic"
    )

    assert turn.should_answer_directly is True
    assert turn.should_use_tools is False

    assert turn.entities[
        "arithmetic_expression"
    ] == (
        "557 + 528 + 527 + 493 + 452 + 1118"
    )

    core = MaironCore()

    first = core.prepare_turn(
        request_text
    )

    assert first.epistemic_route.authority == (
        "core_arithmetic"
    )

    assert first.epistemic_route.mode == (
        "deterministic_calculation"
    )

    assert first.direct_response == (
        "The total is 3,675."
    )

    assert first.workflow_result is not None
    assert first.workflow_result.success is True

    # --------------------------------------------------
    # 2. Oliver's exact clarification reuses Core-owned previous operands.
    # --------------------------------------------------

    correction = (
        "no dumbass i meant addition. add those numbers together "
        "and provide me with the total"
    )

    second = core.prepare_turn(
        correction
    )

    assert second.turn.intent == (
        "calculate_arithmetic"
    )

    assert second.turn.is_follow_up is True

    assert second.turn.entities[
        "arithmetic_operands"
    ] == (
        "557|528|527|493|452|1118"
    )

    assert second.direct_response == (
        "The total is 3,675."
    )

    # --------------------------------------------------
    # 3. Everyday deterministic arithmetic variants.
    # --------------------------------------------------

    cases = [
        (
            "subtract 3 from 10",
            "The result is 7.",
        ),
        (
            "multiply 5 by 6",
            "The result is 30.",
        ),
        (
            "divide 20 by 4",
            "The result is 5.",
        ),
        (
            "what is 15% of 200?",
            "15% of 200 is 30.",
        ),
        (
            "what is 5 + 7 * 2?",
            "The result is 19.",
        ),
        (
            "what is 2^3?",
            "The result is 8.",
        ),
        (
            "add 1,000 and 2,000",
            "The total is 3,000.",
        ),
    ]

    for user_text, expected in cases:
        result = MaironCore().prepare_turn(
            user_text
        )

        assert result.turn.intent == (
            "calculate_arithmetic"
        ), user_text

        assert result.direct_response == (
            expected
        ), user_text

    # --------------------------------------------------
    # 4. Division by zero fails deterministically and truthfully.
    # --------------------------------------------------

    zero = MaironCore().prepare_turn(
        "divide 5 by 0"
    )

    assert zero.turn.intent == (
        "calculate_arithmetic"
    )

    assert zero.workflow_result is not None
    assert zero.workflow_result.success is False

    assert zero.direct_response == (
        "I can't divide by zero."
    )

    # --------------------------------------------------
    # 5. Arithmetic evaluator is not Python eval.
    # --------------------------------------------------

    try:
        evaluate_arithmetic_expression(
            "__import__('os').system('echo nope')"
        )

    except ArithmeticEvaluationError:
        pass

    else:
        raise AssertionError(
            "unsafe Python-like arithmetic input was not rejected"
        )

    # --------------------------------------------------
    # 6. "Open Calculator" remains a desktop action, not maths.
    # --------------------------------------------------

    calculator_turn = classify_turn(
        "open calculator"
    )

    assert calculator_turn.intent == (
        "launch_application"
    )

    # --------------------------------------------------
    # 7. A vague phrase with only one number is not guessed as arithmetic.
    # --------------------------------------------------

    vague = extract_arithmetic_request(
        "add 5 to my list"
    )

    assert vague is None

    print(
        "Mairon Phase 10.5 deterministic arithmetic authority tests: PASS"
    )


if __name__ == "__main__":
    run()
