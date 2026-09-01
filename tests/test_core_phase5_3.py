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
    find_deterministic_grounding_violations,
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

    contract = build_answer_contract(
        turn=turn,
        route=route,
    ).to_model_instruction()

    return contract


def run():
    user_text = (
        "I bought XT6s for China. They arrived today!"
    )

    contract = make_share_contract(
        user_text
    )

    # --------------------------------------------------
    # 1. Exact live false positive:
    #    sentence-initial "The" must not turn a grounded entity
    #    into a novel multi-word proper noun.
    # --------------------------------------------------

    grounded_draft = (
        "The XT6s finally arrived."
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=grounded_draft,
            core_answer_contract=contract,
            conversation=[],
        )
    )

    assert not any(
        "introduced named entity 'The XT6s'"
        in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 2. Other harmless determiners should behave the same way.
    # --------------------------------------------------

    drafts = [
        "Those XT6s finally arrived.",
        "Your XT6s finally arrived.",
        "These XT6s finally arrived.",
    ]

    for draft in drafts:
        violations = (
            find_deterministic_grounding_violations(
                user_input=user_text,
                draft=draft,
                core_answer_contract=contract,
                conversation=[],
            )
        )

        assert not any(
            "XT6s"
            in violation
            and "introduced named entity"
            in violation
            for violation in violations
        ), (
            draft,
            violations,
        )

    # --------------------------------------------------
    # 3. Truly novel named entities must STILL be rejected.
    # --------------------------------------------------

    bad_draft = (
        "You'll wear them at the Great Wall."
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=bad_draft,
            core_answer_contract=contract,
            conversation=[],
        )
    )

    assert any(
        "Great Wall"
        in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 4. Current-location relation error remains rejected.
    # --------------------------------------------------

    bad_location = (
        "The XT6s are finally in China."
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=bad_location,
            core_answer_contract=contract,
            conversation=[],
        )
    )

    assert any(
        "current-location claim"
        in violation
        and "China"
        in violation
        for violation in violations
    ), violations

    assert not any(
        "introduced named entity 'The XT6s'"
        in violation
        for violation in violations
    ), violations

    print(
        "Mairon Core Phase 5.3 named-entity grounding tests: PASS"
    )


if __name__ == "__main__":
    run()
