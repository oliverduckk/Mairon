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
    infer_recent_media_consumption_action,
)


def run():
    # --------------------------------------------------
    # 1. Core infers media modality from semantic category,
    #    not from title-specific knowledge.
    # --------------------------------------------------

    assert (
        infer_recent_media_consumption_action(
            "Give me some manga recommendations."
        )
        == "read"
    )

    assert (
        infer_recent_media_consumption_action(
            "What movies should I check out?"
        )
        == "watch"
    )

    assert (
        infer_recent_media_consumption_action(
            "Recommend me a few podcasts."
        )
        == "listen"
    )

    assert (
        infer_recent_media_consumption_action(
            "What games would you recommend?"
        )
        == "play"
    )

    # Mixed media is intentionally ambiguous rather than guessed.
    assert (
        infer_recent_media_consumption_action(
            "Do you prefer manga or anime?"
        )
        is None
    )

    # --------------------------------------------------
    # 2. The exact production-shaped failure is handled using
    #    conversational modality, with zero knowledge of the titles.
    # --------------------------------------------------

    conversation = [
        {
            "role": "user",
            "content": "What manga would you want me to recommend?",
        },
        {
            "role": "assistant",
            "content": "Throw me a few picks.",
        },
    ]

    current_user = (
        "Berserk, Vinland Saga, Tokyo Ghoul, Bleach, "
        "One Piece, Chainsaw Man, 20th Century Boys, Vagabond"
    )

    bad = (
        "Nice list. I'm going to watch Berserk next."
    )

    violations = (
        find_mairon_agency_modality_violations(
            user_input=current_user,
            draft=bad,
            conversation=conversation,
        )
    )

    assert any(
        "unsupported autonomous future action"
        in item
        for item in violations
    )

    assert any(
        "media modality drift"
        in item
        for item in violations
    )

    # Same titles, correct modality, but still fake future agency:
    # agency is independent from modality correctness.
    read_later = (
        "I'm going to read Berserk next."
    )

    violations = (
        find_mairon_agency_modality_violations(
            user_input=current_user,
            draft=read_later,
            conversation=conversation,
        )
    )

    assert any(
        "unsupported autonomous future action"
        in item
        for item in violations
    )

    assert not any(
        "media modality drift"
        in item
        for item in violations
    )

    # Hypothetical preference is allowed because it does not claim an
    # autonomous future action.
    hypothetical = (
        "Berserk would probably be my next pick from that list."
    )

    assert (
        find_mairon_agency_modality_violations(
            user_input=current_user,
            draft=hypothetical,
            conversation=conversation,
        )
        == []
    )

    # --------------------------------------------------
    # 3. Explicit medium switches are allowed.
    # --------------------------------------------------

    explicit_switch = (
        "If you mean the anime adaptation, I'd watch that; "
        "for the manga itself, I'd read it."
    )

    assert (
        find_mairon_agency_modality_violations(
            user_input="We're talking about manga here.",
            draft=explicit_switch,
            conversation=[],
        )
        == []
    )

    # --------------------------------------------------
    # 4. Future-agency protection is broad beyond media.
    # --------------------------------------------------

    for draft in (
        "I'll research that later.",
        "I'll check that tomorrow.",
        "I'm going to look up the details tonight.",
        "I plan to buy one next week.",
        "I'll email them later.",
    ):
        violations = (
            find_mairon_agency_modality_violations(
                user_input="Fair enough.",
                draft=draft,
                conversation=[],
            )
        )

        assert any(
            "unsupported autonomous future action"
            in item
            for item in violations
        ), draft

    # Current-response communicative language is not confused with off-turn
    # autonomous action.
    for draft in (
        "I'll explain why.",
        "I'll give you the short version.",
        "I'd probably pick Berserk.",
        "That would be my next pick.",
    ):
        assert (
            find_mairon_agency_modality_violations(
                user_input="What do you reckon?",
                draft=draft,
                conversation=[],
            )
            == []
        ), draft

    # --------------------------------------------------
    # 5. The model-facing instruction is general, not title/scenario-coded.
    # --------------------------------------------------

    instruction = (
        build_mairon_agency_modality_instruction(
            user_input="Recommend some manga.",
            conversation=[],
        )
    )

    lower = instruction.lower()

    assert "independently act between turns" in lower
    assert "preserve the medium" in lower
    assert "currently infers" in lower
    assert "'read'" in lower

    for forbidden_benchmark_word in (
        "berserk",
        "vinland",
        "tokyo ghoul",
        "top 3",
        "gym",
    ):
        assert (
            forbidden_benchmark_word
            not in lower
        )

    print(
        "Mairon acceptance cleanup 7 agency/modality integrity tests: PASS"
    )


if __name__ == "__main__":
    run()
