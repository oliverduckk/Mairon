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

    # The verifier prompt itself is generated inside verify_core_grounded_draft.
    # This historical regression protects the semantic policy invariants:
    # obvious impossible/personified banter remains allowed, while plausible
    # concrete premises and ordinary factual claims still require grounding.
    # Internal classification labels are not part of the contract.
    source_path = (
        SRC_DIR
        / "core"
        / "claim_grounding.py"
    )

    source = source_path.read_text(
        encoding="utf-8"
    )

    required_phrases = [
        # Obvious impossible/personified banter remains allowed.
        "Clearly absurd, impossible, anthropomorphic, sarcastic, teasing, or",
        "The shoes will need their own passport",
        "Hope they're not plotting a mutiny",

        # Plausible literal claims remain evidence-gated.
        "XT6s are waterproof",
        "they are currently in China",
        "you will visit the Great Wall",

        # Phase 6.8.6 strengthens the old binary banter label into
        # premise-aware decomposition: the joke predicate can be
        # non-literal while its concrete scene premise still requires
        # support.
        "Decompose each meaningful proposition BEFORE deciding what is banter.",
        "A clearly non-literal predicate/action does NOT exempt the concrete premise",
        "Only the obviously impossible/non-literal predicate itself is exempt",
        "the dust bunnies are plotting a coup",
        "the desk is plotting revenge",
        "the XM6s are furious",
    ]

    for phrase in required_phrases:
        assert phrase in source, phrase

    print(
        "Mairon Core Phase 5.4 non-literal banter policy tests: PASS"
    )


if __name__ == "__main__":
    run()
