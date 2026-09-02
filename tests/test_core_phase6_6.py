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
)
from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    runtime_from_answer_contract,
)
from core.claim_grounding import (
    build_core_grounding_fallback,
    find_deterministic_grounding_violations,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)
from core.orchestrator import (
    MaironCore,
)
from core.workflows.self_correction import (
    build_self_correction_response,
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
    # --------------------------------------------------
    # 1. Exact acceptance-test self-correction is Core-owned.
    # --------------------------------------------------

    correction = (
        "Actually, scratch that — I cleaned it last night, "
        "not this morning."
    )

    assert (
        build_self_correction_response(
            correction
        )
        == (
            "Got it — you cleaned it last night, "
            "not this morning."
        )
    )

    core = MaironCore()

    decision = core.prepare_turn(
        correction
    )

    assert decision.turn.intent == (
        "self_correction"
    )

    assert decision.direct_response == (
        "Got it — you cleaned it last night, "
        "not this morning."
    )

    assert decision.direct_response is not None

    assert (
        build_self_correction_response(
            "I meant the blue one, not the red one."
        )
        == (
            "Got it — the blue one, not the red one."
        )
    )

    assert (
        build_self_correction_response(
            "Actually, I meant Tuesday."
        )
        == "Got it — Tuesday."
    )

    # --------------------------------------------------
    # 2. Mairon cannot claim physical perception in text chat.
    # --------------------------------------------------

    user_text = (
        "I finally cleaned my desk this morning. "
        "It was getting ridiculous."
    )

    runtime = runtime_for(
        user_text
    )

    bad_observation = (
        "Ah, the desk. I've seen it. Glad you finally cleaned it."
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=bad_observation,
            core_answer_contract=runtime,
            conversation=[],
        )
    )

    assert any(
        "direct physical perception"
        in violation
        for violation in violations
    ), violations

    harmless = (
        "I see what you mean. The desk clearly needed the intervention."
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=harmless,
            core_answer_contract=runtime,
            conversation=[],
        )
    )

    assert not any(
        "direct physical perception"
        in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 3. Generation policy explicitly source-locks concrete details.
    # --------------------------------------------------

    instruction = (
        build_core_micro_act_instruction(
            core_answer_contract=runtime,
            conversation=[],
            retry=False,
        )
    )

    assert instruction is not None

    assert (
        "SOURCE-LOCK concrete details"
        in instruction
    )

    assert (
        "coffee cups"
        in instruction
    )

    assert (
        "caffeine"
        in instruction
    )

    assert (
        "Ordinary text conversation does not grant visual or audio perception."
        in instruction
    )

    retry_instruction = (
        build_core_micro_act_instruction(
            core_answer_contract=runtime,
            conversation=[],
            retry=True,
        )
    )

    assert (
        "Keep concrete nouns/details source-locked on retry too."
        in retry_instruction
    )

    # --------------------------------------------------
    # 4. Fail-closed "At least..." update stays conversational.
    # --------------------------------------------------

    ipad_text = (
        "At least my iPad is fully charged."
    )

    ipad_runtime = runtime_for(
        ipad_text
    )

    fallback = (
        build_core_grounding_fallback(
            ipad_runtime,
            user_input=ipad_text,
        )
    )

    assert fallback == (
        "At least that one's sorted."
    )

    print(
        "Mairon Core Phase 6.6 social quality/embodiment tests: PASS"
    )


if __name__ == "__main__":
    run()
