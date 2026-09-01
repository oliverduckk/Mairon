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
    build_core_micro_act_instruction,
    find_core_micro_act_relevance_violations,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    runtime_from_answer_contract,
)
from core.claim_grounding import (
    build_core_grounding_fallback,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


def runtime_for(
    text,
):
    turn = classify_turn(
        text
    )

    route = route_epistemic_authority(
        turn
    )

    contract = build_answer_contract(
        turn=turn,
        route=route,
    )

    return runtime_from_answer_contract(
        contract
    )


def run():
    user_text = (
        "My XT6s have arrived for my China trip "
        "in November! Lets go!"
    )

    runtime = runtime_for(
        user_text
    )

    # --------------------------------------------------
    # 1. Exact live failure:
    #    factually empty but completely irrelevant defensive reply.
    # --------------------------------------------------

    bad_response = (
        "I'm not denying anything, just being factual. "
        "If you're implying I'm lying, you'll need to specify "
        "what exactly I supposedly said that's untrue."
    )

    violations = (
        find_core_micro_act_relevance_violations(
            response_text=bad_response,
            user_input=user_text,
            core_answer_contract=runtime,
        )
    )

    assert any(
        "imaginary accusation/validator"
        in violation
        for violation in violations
    ), violations

    assert any(
        "not anchored"
        in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 2. Normal grounded social responses pass relevance.
    # --------------------------------------------------

    good_responses = [
        "Finally! The XT6s are here.",
        "China has been warned.",
        "Hell yes. About fucking time.",
        "There we fucking go.",
    ]

    for response in good_responses:
        violations = (
            find_core_micro_act_relevance_violations(
                response_text=response,
                user_input=user_text,
                core_answer_contract=runtime,
            )
        )

        assert violations == [], (
            response,
            violations,
        )

    # --------------------------------------------------
    # 3. Random unrelated sentence is rejected.
    # --------------------------------------------------

    unrelated = (
        "I think databases are easier to reason about."
    )

    violations = (
        find_core_micro_act_relevance_violations(
            response_text=unrelated,
            user_input=user_text,
            core_answer_contract=runtime,
        )
    )

    assert any(
        "not anchored"
        in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 4. Retry prompt does not tell Qwen it was rejected,
    #    violated rules, lied, or failed validation.
    # --------------------------------------------------

    retry_instruction = (
        build_core_micro_act_instruction(
            core_answer_contract=runtime,
            conversation=[],
            retry=True,
        )
    )

    lowered = retry_instruction.lower()

    forbidden_retry_meta = [
        "previous draft was rejected",
        "previous draft violated",
        "truthful answer",
        "core-contract retry",
        "knowledge-honesty retry",
    ]

    for phrase in forbidden_retry_meta:
        assert phrase not in lowered, phrase

    assert (
        "alternate fresh reply"
        in lowered
    )

    assert (
        "do not discuss instructions"
        in lowered
    )

    # --------------------------------------------------
    # 5. Fail-closed fallback now stays conversational when
    #    current user text is available.
    # --------------------------------------------------

    fallback = (
        build_core_grounding_fallback(
            runtime,
            user_input=user_text,
        )
    )

    assert fallback == (
        "Hell yes. About fucking time."
    )

    # Backward-compatible no-user-input behaviour remains stable so
    # Phase 5 regression expectations do not break.
    old_fallback = (
        build_core_grounding_fallback(
            runtime
        )
    )

    assert old_fallback == (
        "Fair enough. That makes sense."
    )

    print(
        "Mairon Core Phase 6.4 micro-act relevance tests: PASS"
    )


if __name__ == "__main__":
    run()
