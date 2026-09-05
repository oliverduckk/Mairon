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
    should_skip_email_read_generation,
)
from core.answer_contract import (
    AnswerContract,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)


def _contract(
    body,
):
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
                f"{body}"
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
    newsletter = _contract(
        "These employers are hiring now!\n"
        "New Graduate Job recommendations\n"
        "Mainfreight Australia\n"
        "Graduate Program - Supply Chain & Logistics\n"
        "AUD 67,400 - AUD 77,700 / Year\n"
        "Applications close 31 December 2026\n"
        "*******************************************************************...\n"
    )

    assert (
        should_skip_email_read_generation(
            newsletter
        )
        is True
    )

    short_human = _contract(
        "Hey Oliver, can you send me the revised document by Friday? Thanks."
    )

    assert (
        should_skip_email_read_generation(
            short_human
        )
        is False
    )

    fallback = build_email_read_verified_fallback(
        newsletter
    )

    assert (
        "Applications close 31 December 2026"
        in fallback
    )

    assert (
        "*******************************************************************..."
        not in fallback
    )

    print(
        "Mairon Phase 8.7.7 adaptive email-read strategy tests: PASS"
    )


if __name__ == "__main__":
    run()
