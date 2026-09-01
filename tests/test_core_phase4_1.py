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


from ai.ollama_provider import (
    find_core_answer_contract_violations,
    should_retrieve_past_context_for_turn,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


def run():
    # --------------------------------------------------
    # Build real Core contracts from representative turns.
    # --------------------------------------------------

    share_turn = classify_turn(
        (
            "They are a pair of XT6s for my trip to China in 2 months time. "
            "Gotta buy good shoes for walking that much ya know."
        )
    )

    share_route = route_epistemic_authority(
        share_turn
    )

    share_contract = build_answer_contract(
        turn=share_turn,
        route=share_route,
    ).to_model_instruction()

    thanks_turn = classify_turn(
        "Thanks Mairon"
    )

    thanks_route = route_epistemic_authority(
        thanks_turn
    )

    thanks_contract = build_answer_contract(
        turn=thanks_turn,
        route=thanks_route,
    ).to_model_instruction()

    # --------------------------------------------------
    # 1. Trivial acts do not retrieve unrelated long-term history.
    # --------------------------------------------------

    assert (
        should_retrieve_past_context_for_turn(
            user_input="Thanks Mairon",
            core_answer_contract=thanks_contract,
        )
        is False
    )

    assert (
        should_retrieve_past_context_for_turn(
            user_input=(
                "They are a pair of XT6s for my China trip."
            ),
            core_answer_contract=share_contract,
        )
        is False
    )

    # Explicit recall language can still opt a declarative turn into history.
    assert (
        should_retrieve_past_context_for_turn(
            user_input=(
                "Remember when we talked about those XT6s? "
                "They finally arrived."
            ),
            core_answer_contract=share_contract,
        )
        is True
    )

    # --------------------------------------------------
    # 2. The accidental Chinese paragraph is rejected.
    # --------------------------------------------------

    chinese_failure = (
        "You’re not wrong about the walking—China’s got a lot of ground "
        "to cover. Just别让那些XT6s变成踩屎感传奇，好吗？"
        "至于Prosple的邮件，啧，HYPE DC的包裹还没到。"
    )

    chinese_violations = (
        find_core_answer_contract_violations(
            response_text=chinese_failure,
            core_answer_contract=share_contract,
        )
    )

    assert any(
        "out of English"
        in violation
        for violation in chinese_violations
    )

    # --------------------------------------------------
    # 3. A tiny foreign-language joke remains possible.
    # --------------------------------------------------

    tiny_joke = (
        "Fair enough — a month of walking makes the XT6s pretty defensible. "
        "笨蛋. I said pretty defensible, not financially responsible."
    )

    tiny_joke_violations = (
        find_core_answer_contract_violations(
            response_text=tiny_joke,
            core_answer_contract=share_contract,
        )
    )

    assert all(
        "out of English"
        not in violation
        for violation in tiny_joke_violations
    )

    # --------------------------------------------------
    # 4. Unsolicited recommendation mode is rejected.
    # --------------------------------------------------

    recommendation_failure = (
        "You should also buy some Brooks Ghosts for the trip. "
        "Here are three other shoes worth considering."
    )

    recommendation_violations = (
        find_core_answer_contract_violations(
            response_text=recommendation_failure,
            core_answer_contract=share_contract,
        )
    )

    assert any(
        "unsolicited recommendations"
        in violation
        for violation in recommendation_violations
    )

    # --------------------------------------------------
    # 5. The exact Prosple-style 'thanks' derailment is rejected.
    # --------------------------------------------------

    thanks_failure = (
        "The email’s subject line is vague enough to be either a genuine "
        "lead or a phishing attempt. Prosple usually doesn’t send "
        "recommendations unsolicited, so check the sender address and "
        "treat it as suspicious until proven otherwise."
    )

    thanks_violations = (
        find_core_answer_contract_violations(
            response_text=thanks_failure,
            core_answer_contract=thanks_contract,
        )
    )

    assert thanks_violations

    # --------------------------------------------------
    # 6. Short personality acknowledgements remain valid.
    # --------------------------------------------------

    for good_response in (
        "Anytime.",
        "Yeah yeah, don’t get sentimental.",
        "Of course, princess.",
    ):
        violations = (
            find_core_answer_contract_violations(
                response_text=good_response,
                core_answer_contract=thanks_contract,
            )
        )

        assert violations == [], (
            good_response,
            violations,
        )

    # --------------------------------------------------
    # 7. Contract explicitly contains the language policy.
    # --------------------------------------------------

    assert (
        "English is the default response language."
        in share_contract
    )

    assert (
        "Do not revive unrelated older topics"
        in share_contract
    )

    assert (
        "Do not answer or revive an older question or topic."
        in thanks_contract
    )

    print(
        "Mairon Core Phase 4.1 contract enforcement tests: PASS"
    )


if __name__ == "__main__":
    run()
