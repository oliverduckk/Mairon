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


from core.source_lock import (
    build_source_lock_retry_instruction,
    find_factual_answer_integrity_violations,
    find_factual_personal_history_violations,
    find_structural_source_lock_violations,
)


def run():
    # --------------------------------------------------
    # 1. Embedded "me to VERB your X" keeps Mairon as actor.
    # --------------------------------------------------

    debug_user = (
        "Don't get smug. You're still the assistant I have to debug every night."
    )

    live_bad_draft = (
        "I'll keep my mouth shut, Oliver. Just don't expect me to fix your code "
        "while you sleep; that's a job for tomorrow."
    )

    relation_violations = (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=live_bad_draft,
            conversation=[],
            max_prior_user_messages=0,
        )
    )

    assert any(
        "source-lock relation reversal"
        in violation
        for violation in relation_violations
    ), relation_violations

    # Phase 6.8.13 scopes direction locks to the relation/action family.
    # "Oliver debugs Mairon" must not globally forbid Mairon from performing
    # unrelated actions involving Oliver. The live maintenance-role reversal
    # above remains blocked; unrelated content editing is not a reversal.
    unrelated_draft = (
        "Don't expect me to rewrite your notes for you."
    )

    unrelated_violations = (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=unrelated_draft,
            conversation=[],
            max_prior_user_messages=0,
        )
    )

    assert not any(
        "source-lock relation reversal"
        in violation
        for violation in unrelated_violations
    ), unrelated_violations

    faithful_draft = (
        "Fine. I'm still the thing you have to debug every night."
    )

    faithful_violations = (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=faithful_draft,
            conversation=[],
            max_prior_user_messages=0,
        )
    )

    assert faithful_violations == [], (
        faithful_violations
    )

    # --------------------------------------------------
    # 2. Source-lock failures generate explicit retry guidance.
    # --------------------------------------------------

    xm6_user = (
        "Anyway, my XM6s are at 40% and I forgot to charge them before work. Classic."
    )

    source_lock_violation = (
        "unsupported Core-grounded claim: source-lock entity substitution/invention: "
        "draft introduced Oliver-owned entity 'phone' while the user-authored "
        "locked entities are ['xm6s']"
    )

    retry_text = build_source_lock_retry_instruction(
        user_input=xm6_user,
        violations=[source_lock_violation],
        conversation=[],
        intent="share_context",
        max_prior_user_messages=0,
    )

    assert retry_text is not None
    assert "Oliver -> 'XM6s'" in retry_text
    assert "source-lock entity substitution/invention" in retry_text
    assert "react without telling Oliver what he should do" in retry_text

    # --------------------------------------------------
    # 3. Factual answers are truth-first: no fake answer -> retraction.
    # --------------------------------------------------

    fakeout = (
        "Vancouver.\n\n(Just kidding. Ottawa.)"
    )

    integrity_violations = (
        find_factual_answer_integrity_violations(
            draft=fakeout
        )
    )

    assert any(
        "answer-integrity violation"
        in violation
        for violation in integrity_violations
    ), integrity_violations

    # Personality is still allowed after a truth-first answer when it does not
    # retract the answer or invent Oliver/Mairon history.
    truth_first_banter = (
        "Ottawa. Vancouver can stop auditioning."
    )

    assert (
        find_factual_answer_integrity_violations(
            draft=truth_first_banter
        )
        == []
    )

    assert (
        find_factual_personal_history_violations(
            user_input="Anyway, what's the capital of Canada?",
            draft=truth_first_banter,
            conversation=[],
        )
        == []
    )

    # --------------------------------------------------
    # 4. Provider carries rejected structural facts into later retries.
    # --------------------------------------------------

    provider_text = (
        PROJECT_ROOT
        / "src"
        / "ai"
        / "ollama_provider.py"
    ).read_text()

    assert "retry_violations = []" in provider_text
    assert "effective_retry_violations" in provider_text
    assert "build_source_lock_retry_instruction" in provider_text
    assert "find_factual_answer_integrity_violations" in provider_text
    assert "Core-grounding repair must also reach social micro-act retries" in provider_text

    answer_contract_text = (
        PROJECT_ROOT
        / "src"
        / "core"
        / "answer_contract.py"
    ).read_text()

    assert (
        "Do not intentionally give a fake/joke factual answer first"
        in answer_contract_text
    )

    assert (
        "A very short personality line may follow the answer"
        in answer_contract_text
    )

    print(
        "Mairon Core Phase 6.8.10 truth-first relation retry tests: PASS"
    )


if __name__ == "__main__":
    run()
