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


from core.answer_contract import (
    build_answer_contract,
)
from core.claim_grounding import (
    contract_forbids_new_factual_claims,
    should_verify_core_grounding,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


def run():
    user_text = (
        "I bought XT6s for China. They arrived today!"
    )

    turn = classify_turn(
        user_text
    )

    route = route_epistemic_authority(
        turn
    )

    contract = build_answer_contract(
        turn=turn,
        route=route,
    ).to_model_instruction()

    assert (
        contract_forbids_new_factual_claims(
            contract
        )
        is True
    )

    assert (
        should_verify_core_grounding(
            contract
        )
        is True
    )

    # The verifier prompt itself is generated inside verify_core_grounded_draft,
    # so this regression protects the policy wording in source rather than
    # pretending a fake model can prove semantic judgement quality.
    source_path = (
        SRC_DIR
        / "core"
        / "claim_grounding.py"
    )

    source = source_path.read_text(
        encoding="utf-8"
    )

    required_phrases = [
        "Clearly absurd, impossible, anthropomorphic, sarcastic, teasing, or",
        "The shoes will need their own passport",
        "Hope they're not plotting a mutiny",
        "CLEARLY_NON_LITERAL_BANTER",
        "XT6s are waterproof",
        "they are currently in China",
        "you will visit the Great Wall",
    ]

    for phrase in required_phrases:
        assert phrase in source, phrase

    print(
        "Mairon Core Phase 5.4 non-literal banter policy tests: PASS"
    )


if __name__ == "__main__":
    run()
