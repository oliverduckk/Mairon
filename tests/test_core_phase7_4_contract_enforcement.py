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


from core.answer_contract_runtime import (
    AnswerContractRuntime,
)
from ai import ollama_provider


def _contract(
    allow_recommendations,
):
    return AnswerContractRuntime(
        task="respond",
        speech_act="question",
        intent="email_read",
        subject="selected Gmail message",
        authority="gmail",
        epistemic_mode="tool_verified",
        allow_recommendations=allow_recommendations,
        allow_new_factual_claims=False,
        allow_follow_up_question=False,
        source="structured",
    )


def run():
    forbidden = _contract(
        allow_recommendations=False
    )

    allowed = _contract(
        allow_recommendations=True
    )

    # --------------------------------------------------
    # 1. Direct Mairon advice is rejected when Core forbids it.
    # --------------------------------------------------

    bad_drafts = (
        (
            "The email is a legal-agreement update. "
            "You should probably click the link and review it."
        ),
        (
            "It says no action is required. "
            "It's not urgent, but you should check the changes anyway."
        ),
        (
            "The message is informational. "
            "I'd recommend reading the full policy update."
        ),
        (
            "Nothing is required right now. "
            "Consider checking it later."
        ),
    )

    for draft in bad_drafts:
        violations = (
            ollama_provider
            .find_forbidden_recommendation_violations(
                response_text=draft,
                core_answer_contract=forbidden,
            )
        )

        assert violations, draft
        assert (
            "forbids unsolicited recommendations"
            in violations[0]
        )

    # --------------------------------------------------
    # 2. Reporting source-authored instructions is NOT Mairon advice.
    # --------------------------------------------------

    reported_source = (
        "The email says you should verify your billing address "
        "before the deadline."
    )

    assert not (
        ollama_provider
        .find_forbidden_recommendation_violations(
            response_text=reported_source,
            core_answer_contract=forbidden,
        )
    )

    reported_source_2 = (
        "PayPal says you should review the updated agreement."
    )

    assert not (
        ollama_provider
        .find_forbidden_recommendation_violations(
            response_text=reported_source_2,
            core_answer_contract=forbidden,
        )
    )

    # --------------------------------------------------
    # 3. If Core explicitly allows recommendation, the same draft is valid.
    # --------------------------------------------------

    advice = (
        "You should probably review the agreement."
    )

    assert not (
        ollama_provider
        .find_forbidden_recommendation_violations(
            response_text=advice,
            core_answer_contract=allowed,
        )
    )

    # --------------------------------------------------
    # 4. No hard-coded Gmail sender/company benchmark logic.
    # --------------------------------------------------

    source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8",
    ).lower()

    for forbidden_literal in (
        "some companies sneakily",
        "paypal legal agreements",
        "paypal yesterday",
        "13.01s",
        "espn fantasy basketball draft results",
    ):
        assert (
            forbidden_literal
            not in source
        )

    print(
        "Mairon Phase 7.4 structured recommendation-permission "
        "enforcement tests: PASS"
    )


if __name__ == "__main__":
    run()
