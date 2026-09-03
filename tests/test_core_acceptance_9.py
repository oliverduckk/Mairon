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


from core.claim_grounding import (
    build_mairon_agency_modality_instruction,
    find_mairon_agency_modality_violations,
)


def run():
    # --------------------------------------------------
    # 1. Concrete activity located outside the active turn is unsupported.
    #    Different verbs/domains should hit the same temporal-agency rule.
    # --------------------------------------------------

    rejected = (
        "I was processing some files before you interrupted me.",
        "I was researching something before you messaged.",
        "I was reading documentation while you were away.",
        "I've been checking logs since your last message.",
        "I've been working on that all morning.",
        "I've been monitoring it for the last two hours.",
        "I'll get back to researching that after this.",
        "I can get back to processing those files now.",
    )

    for draft in rejected:
        violations = (
            find_mairon_agency_modality_violations(
                user_input="Hey Mairon, how's your day going?",
                draft=draft,
                conversation=[],
            )
        )

        assert any(
            "unsupported autonomous off-turn activity"
            in item
            for item in violations
        ), (draft, violations)

    # --------------------------------------------------
    # 2. Ordinary personality, present-response language, and hypothetical
    #    personification remain available. We are not sterilising Mairon.
    # --------------------------------------------------

    allowed = (
        "Fine enough. What about you?",
        "You summoned me again. Tragic.",
        "Apparently my purpose today is judging your decisions.",
        "I'd probably spend the evening reading if I were human.",
        "I'll explain the short version.",
        "That would keep me busy if I actually worked between turns.",
    )

    for draft in allowed:
        violations = (
            find_mairon_agency_modality_violations(
                user_input="Hey Mairon, how's your day going?",
                draft=draft,
                conversation=[],
            )
        )

        assert not any(
            "unsupported autonomous off-turn activity"
            in item
            for item in violations
        ), (draft, violations)

    # Existing future-agency protection still works.
    violations = (
        find_mairon_agency_modality_violations(
            user_input="Fair enough.",
            draft="I'll research that tonight.",
            conversation=[],
        )
    )

    assert any(
        "unsupported autonomous future action"
        in item
        for item in violations
    )

    # --------------------------------------------------
    # 3. Model-facing rule is temporal/agency based, not benchmark-coded.
    # --------------------------------------------------

    instruction = (
        build_mairon_agency_modality_instruction(
            user_input="How are you?",
            conversation=[],
        )
    ).lower()

    assert "before, between, or after" in instruction
    assert "background activity" in instruction
    assert "off-turn" in instruction

    for forbidden in (
        "processing cycle",
        "how is your day going",
        "ottawa",
        "berserk",
        "gym routine",
    ):
        assert forbidden not in instruction

    print(
        "Mairon acceptance cleanup 9 off-turn temporal-agency tests: PASS"
    )


if __name__ == "__main__":
    run()
