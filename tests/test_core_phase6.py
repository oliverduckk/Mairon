import inspect
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
    _core_contract_value,
    build_core_micro_act_instruction,
    should_retrieve_past_context_for_turn,
    split_static_and_turn_instructions,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    AnswerContractRuntime,
    coerce_answer_contract_runtime,
    contract_field_value,
    render_answer_contract,
    runtime_from_answer_contract,
    runtime_from_legacy_text,
)
from core.claim_grounding import (
    contract_forbids_new_factual_claims,
    contract_intent,
    should_verify_core_grounding,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


def make_contract(
    user_text,
):
    turn = classify_turn(
        user_text
    )

    route = route_epistemic_authority(
        turn
    )

    return build_answer_contract(
        turn=turn,
        route=route,
    )


def run():
    # --------------------------------------------------
    # 1. Real AnswerContract -> structured runtime directly.
    # --------------------------------------------------

    contract = make_contract(
        (
            "I bought XT6s for China. "
            "They arrived today!"
        )
    )

    runtime = (
        runtime_from_answer_contract(
            contract
        )
    )

    assert isinstance(
        runtime,
        AnswerContractRuntime,
    )

    assert runtime.source == (
        "structured"
    )

    assert runtime.intent == (
        "share_context"
    )

    assert (
        runtime.allow_new_factual_claims
        is False
    )

    assert (
        runtime.allow_follow_up_question
        is False
    )

    assert (
        runtime.allow_recommendations
        is False
    )

    assert (
        render_answer_contract(
            runtime
        )
        == contract.to_model_instruction()
    )

    # --------------------------------------------------
    # 2. Current router transport can still be reconstructed ONCE.
    #    Bullet formatting must never break booleans again.
    # --------------------------------------------------

    rendered = (
        contract.to_model_instruction()
    )

    legacy_runtime = (
        runtime_from_legacy_text(
            rendered
        )
    )

    assert isinstance(
        legacy_runtime,
        AnswerContractRuntime,
    )

    assert legacy_runtime.source == (
        "legacy_text"
    )

    assert legacy_runtime.intent == (
        "share_context"
    )

    assert (
        legacy_runtime.allow_new_factual_claims
        is False
    )

    assert (
        legacy_runtime.allow_follow_up_question
        is False
    )

    assert (
        legacy_runtime.allow_recommendations
        is False
    )

    # --------------------------------------------------
    # 3. Provider helper consumes STRUCTURED state.
    # --------------------------------------------------

    assert (
        _core_contract_value(
            runtime,
            "Intent",
        )
        == "share_context"
    )

    assert (
        _core_contract_value(
            runtime,
            "Follow-up question allowed",
        )
        == "false"
    )

    assert (
        _core_contract_value(
            runtime,
            (
                "New unsupported factual "
                "claims allowed"
            ),
        )
        == "false"
    )

    assert (
        contract_field_value(
            runtime,
            "Recommendations allowed",
        )
        == "false"
    )

    # --------------------------------------------------
    # 4. Grounding consumes the runtime object directly.
    # --------------------------------------------------

    assert (
        contract_forbids_new_factual_claims(
            runtime
        )
        is True
    )

    assert (
        contract_intent(
            runtime
        )
        == "share_context"
    )

    assert (
        should_verify_core_grounding(
            runtime
        )
        is True
    )

    # --------------------------------------------------
    # 5. Social micro-act routing accepts the structured contract.
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
        "CORE SOCIAL MICRO-ACT MODE:"
        in instruction
    )

    assert (
        should_retrieve_past_context_for_turn(
            (
                "I bought XT6s for China. "
                "They arrived today!"
            ),
            runtime,
        )
        is False
    )

    # --------------------------------------------------
    # 6. Provider transport compatibility:
    #    static text + legacy contract are separated once,
    #    then immediately coerced into structured runtime.
    # --------------------------------------------------

    combined = (
        "STATIC MAIRON INSTRUCTIONS"
        + "\n\n"
        + rendered
    )

    (
        static_text,
        legacy_contract_text,
    ) = split_static_and_turn_instructions(
        combined
    )

    assert static_text == (
        "STATIC MAIRON INSTRUCTIONS"
    )

    ingress_runtime = (
        coerce_answer_contract_runtime(
            legacy_contract_text
        )
    )

    assert isinstance(
        ingress_runtime,
        AnswerContractRuntime,
    )

    assert ingress_runtime.intent == (
        "share_context"
    )

    # --------------------------------------------------
    # 7. Regression guard:
    #    duplicated contract prose parser is gone from provider/grounding.
    # --------------------------------------------------

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    grounding_source = (
        SRC_DIR
        / "core"
        / "claim_grounding.py"
    ).read_text(
        encoding="utf-8"
    )

    runtime_source = (
        SRC_DIR
        / "core"
        / "answer_contract_runtime.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def _contract_value("
        not in grounding_source
    )

    # Provider compatibility accessor must delegate, not parse.
    #
    # Inspect the function directly instead of assuming which unrelated
    # helper happens to appear after it in ollama_provider.py. Phase 6.5
    # legitimately renamed/reorganised the recall helpers.
    provider_accessor = (
        inspect.getsource(
            _core_contract_value
        )
    )

    assert (
        ".splitlines()"
        not in provider_accessor
    )

    assert (
        "contract_field_value("
        in provider_accessor
    )

    # There should be one explicit legacy parser home.
    assert (
        "def _parse_field_lines("
        in runtime_source
    )

    print(
        "Mairon Core Phase 6 structured Answer Contract tests: PASS"
    )


if __name__ == "__main__":
    run()
