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
    build_email_read_verified_fallback,
    find_email_read_contract_violations,
)
from core.answer_contract import (
    AnswerContract,
)
from core.answer_contract_runtime import (
    runtime_from_answer_contract,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)


def _contract():
    evidence = EvidenceBundle(
        authority="gmail",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                "Verified Gmail message contents:\n"
                "From: Richard from Prosple <richard@example.com>\n"
                "Subject: Graduate Job recommendations\n"
                "Date: Fri, 04 Sep 2026 23:21:05 +0000\n"
                "Body:\n"
                "Mainfreight Graduate Program. Applications close December 31."
            ),
            provenance="gmail",
            confidence="verified",
        )
    )

    return AnswerContract(
        task="read_email",
        speech_act="request_action",
        intent="email_read",
        subject="latest email",
        authority="gmail",
        epistemic_mode="tool_verified",
        allow_recommendations=False,
        allow_new_factual_claims=False,
        allow_follow_up_question=False,
        evidence=evidence,
    )


def run():
    contract = _contract()

    # --------------------------------------------------
    # 1. Verified evidence survives as structured runtime data.
    # --------------------------------------------------

    runtime = runtime_from_answer_contract(
        contract
    )

    assert runtime is not None
    assert len(
        runtime.verified_evidence_claims
    ) == 1

    assert (
        "Mainfreight Graduate Program"
        in runtime.verified_evidence_claims[
            0
        ]
    )

    # --------------------------------------------------
    # 2. Mairon-authored advice is rejected.
    # --------------------------------------------------

    bad = (
        "Look, if you want to apply for that program, go ahead, "
        "but don't forget the deadline. You could wait instead."
    )

    violations = (
        find_email_read_contract_violations(
            response_text=bad,
            core_answer_contract=contract,
        )
    )

    assert violations, violations

    # --------------------------------------------------
    # 3. Unsupported editorialising is rejected.
    # --------------------------------------------------

    editorial = (
        "Richard's already been spamming you with Prosple job alerts again."
    )

    violations = (
        find_email_read_contract_violations(
            response_text=editorial,
            core_answer_contract=contract,
        )
    )

    assert violations, violations

    # --------------------------------------------------
    # 4. Source-attributed requirements remain allowed.
    # --------------------------------------------------

    good = (
        "The email says applications close December 31."
    )

    violations = (
        find_email_read_contract_violations(
            response_text=good,
            core_answer_contract=contract,
        )
    )

    assert violations == [], violations

    # --------------------------------------------------
    # 5. Exhausted-generation fallback is source-extractive.
    # --------------------------------------------------

    fallback = build_email_read_verified_fallback(
        contract
    )

    assert (
        "From: Richard from Prosple"
        in fallback
    )

    assert (
        "Subject: Graduate Job recommendations"
        in fallback
    )

    assert (
        "Mainfreight Graduate Program"
        in fallback
    )

    assert (
        "go ahead"
        not in fallback.lower()
    )

    assert (
        "guardrails"
        not in fallback.lower()
    )

    print(
        "Mairon Phase 8.7.4 email-read contract enforcement tests: PASS"
    )


if __name__ == "__main__":
    run()
