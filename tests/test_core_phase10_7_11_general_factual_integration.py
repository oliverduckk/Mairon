import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.answer_contract import build_answer_contract
from core.answer_contract_runtime import runtime_from_answer_contract
from core.claim_grounding import (
    should_verify_core_grounding,
    should_verify_factual_focus_fidelity,
)
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn


def _runtime_for(text):
    turn = classify_turn(text)
    route = route_epistemic_authority(turn)
    contract = build_answer_contract(turn=turn, route=route)
    return turn, route, runtime_from_answer_contract(contract)


def run():
    # --------------------------------------------------
    # 1. Imperative explanation requests are factual speech acts.
    # --------------------------------------------------
    stable_examples = (
        "Explain how DNS works.",
        "Describe how a TCP handshake works.",
        "Define asymmetric encryption.",
        "Compare TCP and UDP.",
        "Walk me through how DHCP works.",
    )

    for text in stable_examples:
        turn, route, runtime = _runtime_for(text)

        assert turn.intent == "factual_question", (
            text, turn.intent, turn.reasons
        )
        assert turn.speech_act == "question"
        assert route.authority == "local_model_knowledge", (
            text, route
        )
        assert route.mode == "stable_model_knowledge"
        assert route.verification_required is False
        assert route.allow_model_memory is True

        # Factual questions must not be policed by the generic conversation
        # grounding verifier. Their personal/history fidelity is checked by
        # the factual-focus verifier instead.
        assert should_verify_core_grounding(runtime) is False
        assert should_verify_factual_focus_fidelity(runtime) is True

    # --------------------------------------------------
    # 2. Public-source factual lookups use the same verifier separation.
    # --------------------------------------------------
    turn, route, runtime = _runtime_for(
        "Who is the current CEO of Example Semiconductor?"
    )

    assert turn.intent == "factual_question"
    assert route.authority == "public_web"
    assert route.mode == "public_source_verified"
    assert route.verification_required is True
    assert route.allow_model_memory is False

    # This is the regression for the AMD/Lisa Su acceptance failure: the
    # generic Core verifier does not know the retrieved web packet and must
    # not reject evidence-backed names before the dedicated public verifier
    # evaluates them.
    assert should_verify_core_grounding(runtime) is False
    assert should_verify_factual_focus_fidelity(runtime) is True

    # --------------------------------------------------
    # 3. Existing source-locked conversation lanes still use Core grounding.
    # --------------------------------------------------
    turn, route, runtime = _runtime_for(
        "My new keyboard arrived today."
    )

    assert turn.intent == "share_context"
    assert should_verify_core_grounding(runtime) is True

    # Production stays generic: no live acceptance-test entity is hard-coded.
    router_source = (SRC_DIR / "core" / "intent_router.py").read_text(
        encoding="utf-8"
    ).lower()
    grounding_source = (SRC_DIR / "core" / "claim_grounding.py").read_text(
        encoding="utf-8"
    ).lower()

    for concrete_name in (
        "amd",
        "lisa su",
        "example semiconductor",
    ):
        assert concrete_name not in router_source
        assert concrete_name not in grounding_source

    print("Mairon Phase 10.7.11 general factual integration tests: PASS")


if __name__ == "__main__":
    run()
