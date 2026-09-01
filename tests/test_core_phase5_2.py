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
    repair_core_restricted_draft,
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


def make_share_contract(
    user_text,
):
    turn = classify_turn(
        user_text
    )

    route = route_epistemic_authority(
        turn
    )

    return (
        build_answer_contract(
            turn=turn,
            route=route,
        )
        .to_model_instruction()
    )


def run():
    contract = make_share_contract(
        "Mate they are currently on my feet"
    )

    # --------------------------------------------------
    # 1. Keep the useful declarative part, remove question tail.
    # --------------------------------------------------

    draft = (
        "Of course they're already on your feet. "
        "How are they feeling?"
    )

    repaired = (
        repair_core_restricted_draft(
            response_text=draft,
            core_answer_contract=contract,
        )
    )

    assert repaired == (
        "Of course they're already on your feet."
    ), repaired

    assert (
        find_core_answer_contract_violations(
            response_text=repaired,
            core_answer_contract=contract,
        )
        == []
    )

    # --------------------------------------------------
    # 2. Remove generic service tail even without a question mark.
    # --------------------------------------------------

    draft = (
        "Fair enough. That makes sense. "
        "Let me know if they're worth the wait."
    )

    repaired = (
        repair_core_restricted_draft(
            response_text=draft,
            core_answer_contract=contract,
        )
    )

    assert repaired == (
        "Fair enough. That makes sense."
    ), repaired

    # --------------------------------------------------
    # 3. Validator independently rejects service language if it survives.
    # --------------------------------------------------

    violations = (
        find_core_answer_contract_violations(
            response_text=(
                "Fair enough. Let me know if they're worth it."
            ),
            core_answer_contract=contract,
        )
    )

    assert any(
        "generic follow-up/service language"
        in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 4. A pure question is removed entirely, forcing regeneration.
    # --------------------------------------------------

    repaired = (
        repair_core_restricted_draft(
            response_text=(
                "How's the break-in going? Blisters yet?"
            ),
            core_answer_contract=contract,
        )
    )

    assert repaired == ""

    # --------------------------------------------------
    # 5. Normal declarative banter is untouched.
    # --------------------------------------------------

    clean = (
        "There it is. Purchase justification complete."
    )

    repaired = (
        repair_core_restricted_draft(
            response_text=clean,
            core_answer_contract=contract,
        )
    )

    assert repaired == clean

    print(
        "Mairon Core Phase 5.2 restricted-response repair tests: PASS"
    )


if __name__ == "__main__":
    run()
