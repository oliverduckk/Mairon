"""Phase 11.6.6B5: final Oliver-holdout reliability closures.

Deterministic only: no Ollama, network, private-tool or write actions.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract import build_answer_contract
from core.claim_grounding import (
    build_core_grounding_fallback,
    build_recommendation_request_fallback,
)
from core.conversation_state import ConversationState
from core.epistemic_router import classify_factual_authority, route_epistemic_authority
from core.intent_router import classify_turn, reconstruct_bounded_factual_followup
from personality.spoiler_guard import build_spoiler_guard_text, prepare_spoiler_context


def run() -> None:
    # Durable mechanism/code questions should not require web research merely
    # because they are phrased as a conditional or contain a code snippet.
    session = (
        "bro if someone nicks an already-logged-in session cookie, will switching "
        "on MFA magically stop them using it?"
    )
    assert classify_factual_authority(session) == "stable_model_knowledge"
    session_turn = classify_turn(session)
    assert session_turn.intent == "factual_question"
    assert route_epistemic_authority(session_turn).mode == "stable_model_knowledge"

    code = "python question: `def f(x=[]): x.append(7); return x` -- what prints?"
    assert classify_factual_authority(code) == "stable_model_knowledge"

    # Explicit current/version/source requests must still override stable-tech memory.
    assert classify_factual_authority("what is the current Python version?") == "public_source_verified"
    assert classify_factual_authority("check the official Python docs for venv isolation") == "public_source_verified"

    # Source-provenance follow-ups should repeat the prior USER question for
    # research rather than searching literally for "which official link".
    previous = (
        "bro can u check the OFFICIAL Python venv docs: do virtual environments inherit "
        "system site packages by default? give me the actual source URL, not trust me bro"
    )
    reconstructed = reconstruct_bounded_factual_followup(
        "which official link is that from? and if you didn't actually load it, SAY THAT",
        previous,
    )
    assert reconstructed is not None
    assert "virtual environments inherit system site packages" in reconstructed.lower()
    assert "official/primary source" in reconstructed.lower()

    # A user explicitly saying they only wanted to share something is a social
    # update, not a new shopping/recommendation task.
    social = classify_turn(
        "im not asking you for shopping recommendations btw i just wanted to tell someone lmao"
    )
    assert social.intent == "share_context", social.intent
    social_route = route_epistemic_authority(social)
    social_contract = build_answer_contract(social, social_route)
    fallback = build_core_grounding_fallback(
        social_contract.to_model_instruction(),
        user_input=social.raw_text,
    )
    assert len(fallback.split()) > 1
    assert "task" in fallback.lower() or "share" in fallback.lower() or "win" in fallback.lower()

    # If recommendation generation fails closed, the visible fallback must
    # still answer the requested task rather than expose evidence-limit prose.
    career_conversation = [
        {
            "role": "user",
            "content": (
                "bruh ANOTHER generic grad rejection email. i just wanna complain for a sec, "
                "please don't give me another 9-step career plan 😭"
            ),
        }
    ]
    next_step = build_recommendation_request_fallback(
        "okay, one actual useful next step. ONE. i have uni shit to do too",
        career_conversation,
    )
    low = next_step.lower()
    assert "application" in low or "role" in low
    assert "evidence limit" not in low

    cyber_conversation = [
        {
            "role": "user",
            "content": "bro everyone's saying AI is gonna replace every cyber job by next year",
        }
    ]
    skill = build_recommendation_request_fallback(
        "i don't want a motivational speech. give me one concrete skill worth practising regardless",
        cyber_conversation,
    )
    assert "wireshark" in skill.lower() or "packet" in skill.lower()
    assert "evidence limit" not in skill.lower()

    # Corrected answer frames should be answered directly rather than echoing
    # the discarded interpretation (which also avoids mechanical false fails).
    state = ConversationState()
    first = classify_turn(
        "lowkey i think the best part of Vinland Saga is the character writing, not the fights. "
        "thoughts? no spoilers past season 1",
        state,
    )
    state.remember_user_turn(first)
    corrected = classify_turn(
        "nah i mean like WHY the character writing works, not whether i should watch it lol",
        state,
    )
    corrected_route = route_epistemic_authority(corrected)
    corrected_contract = build_answer_contract(corrected, corrected_route)
    rendered = corrected_contract.to_model_instruction().lower()
    assert "do not repeat or paraphrase the discarded interpretation" in rendered
    assert "unmeasured component" not in rendered

    spoiler_ctx = prepare_spoiler_context(
        corrected.raw_text,
        [
            {"role": "user", "content": first.raw_text},
            {"role": "assistant", "content": "assistant text is not authority"},
        ],
    )
    guard = build_spoiler_guard_text(spoiler_ctx).lower()
    assert "hard spoiler ceiling" in guard
    assert "full-series arc" in guard
    assert "craft analysis" in guard

    # Diagnostic continuations must explicitly distinguish measured evidence
    # from unmeasured topology/components.
    diag_state = ConversationState()
    diag_first = classify_turn(
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. what would you test first?",
        diag_state,
    )
    diag_state.remember_user_turn(diag_first)
    diag_follow = classify_turn(
        "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. so what does that rule out?",
        diag_state,
    )
    diag_route = route_epistemic_authority(diag_follow)
    assert diag_route.mode == "user_context_reasoning"
    diag_contract = build_answer_contract(diag_follow, diag_route).to_model_instruction().lower()
    assert "unmeasured component" in diag_contract
    assert "what they actually rule out" in diag_contract

    verifier = (SRC / "research" / "public_factual_grounding.py").read_text(encoding="utf-8")
    assert "whole field is safe from automation/replacement" in verifier
    assert "reject personal certainty" in verifier

    provider = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    assert "build_recommendation_request_fallback" in provider
    assert "bounded useful recommendation fallback" in provider
    assert "empty/one-word acknowledgement" in provider

    print(
        "PASS: B5 stable technical routing, provenance reconstruction, useful recommendation/social "
        "fallbacks, diagnostic calibration, spoiler ceiling and labour-scope verification"
    )


if __name__ == "__main__":
    run()
