"""Phase 11.6.6B3: cross-layer task/privacy authority compatibility.

This is an additional deterministic regression. No live model, web request,
private account access or persistent-state write. It protects the provider/Core
seams that formerly disagreed about the provenance of conversational follow-ups.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract import build_answer_contract
from core.conversation_state import ConversationState
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn
from core.orchestrator import MaironCore
from core.turn_state import TurnState


def _history(user_text: str, intent: str = "share_context") -> ConversationState:
    state = ConversationState()
    prior = TurnState(raw_text=user_text)
    prior.intent = intent
    state.remember_user_turn(prior)
    return state


def run() -> None:
    core = MaironCore()
    initial = core.prepare_turn("Bro can u explain data leakage in machine learning?")
    assert initial.epistemic_route.mode == "stable_model_knowledge", initial
    core.prepare_turn("Why is scaling before splitting a problem?")
    followup = core.prepare_turn(
        "wait explain the whole thing in like 2 sentences, my brain is cooked"
    )
    assert followup.turn.entities.get("_user_grounded_followup") == "true"
    assert followup.epistemic_route.mode == "user_context_reasoning"
    assert not followup.epistemic_route.verification_required
    assert not followup.turn.should_use_tools
    assert followup.answer_contract.allow_new_factual_claims, (
        "Stable technical explanations should not be blocked by the "
        "generic source-locked social-conversation contract."
    )
    assert any("invent" in prohibition.lower()
               for prohibition in followup.answer_contract.forbidden_behaviours)

    same_day = _history("I had fruit for breakfast today.")
    known = classify_turn("Bruh what did I eat for breakfast today?", same_day)
    assert route_epistemic_authority(known).mode == "private_user_evidence"
    assert not build_answer_contract(
        known, route_epistemic_authority(known)
    ).allow_new_factual_claims
    unknown = classify_turn(
        "Bro what colour shirt am I wearing right now?", same_day
    )
    assert route_epistemic_authority(unknown).mode == "private_state_uncertain"
    yesterday = _history("I had fruit for breakfast yesterday.")
    uncertain = classify_turn("What did I eat for breakfast today?", yesterday)
    assert route_epistemic_authority(uncertain).mode == "private_state_uncertain"

    fresh = classify_turn(
        "Check the latest forecast online", _history("My keyboard arrived")
    )
    assert fresh.entities.get("_user_grounded_followup") is None
    public = classify_turn("What port does DNS normally use?", same_day)
    assert route_epistemic_authority(public).mode == "public_source_verified"
    current = classify_turn("Can you explain the latest weather forecast?")
    assert route_epistemic_authority(current).mode == "public_source_verified"

    # Cross-layer static check: ensure the provider hasn't reverted to a
    # version lacking context isolation or explicit bounded task instructions.
    provider = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    ast.parse(provider)
    assert 'or core_epistemic_mode in {"user_context_reasoning", "private_user_evidence"}' in provider
    assert '"user_context_reasoning", "private_user_evidence",' in provider

    print("PASS: cross-layer task routing, contract consistency, context isolation, private temporal boundaries")


if __name__ == "__main__":
    run()
