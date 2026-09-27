"""Phase 11.6.6B1: user-grounded follow-up routing and bounded context.

Run: python tests/test_core_phase11_6_6b1_user_task_continuity.py
No model calls, web requests, Calendar writes or private-data reads.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.followup_task import (
    build_bounded_task_instruction,
    bounded_recent_user_turns,
    classify_user_grounded_followup,
)
from core.intent_router import classify_turn
from core.epistemic_router import route_epistemic_authority
from core.conversation_state import ConversationState, build_live_user_continuity_instruction
from core.turn_state import TurnState


def _with_history(*utterances: tuple[str, str]) -> ConversationState:
    state = ConversationState()
    for user_text, intent in utterances:
        entry = TurnState(raw_text=user_text)
        entry.intent = intent
        entry.speech_act = "question" if "?" in user_text else "statement"
        state.remember_user_turn(entry)
    return state


def run() -> None:
    # Keep the user's own history and ensure there's no assistant text in the packet.
    state = _with_history(
        ("bro can u explain data leakage in machine learning?", "factual_question"),
        ("okay but WHY is fitting the scaler before the train/test split a problem?", "factual_question"),
    )
    current = "wait explain the whole thing in like 2 sentences, my brain is cooked"
    turn = classify_turn(current, state)
    assert turn.intent == "factual_question", turn.intent
    assert turn.entities.get("_user_grounded_followup") == "true"
    route = route_epistemic_authority(turn)
    assert route.mode == "user_context_reasoning", route
    assert not route.verification_required and not route.live_data_required
    continuity = build_live_user_continuity_instruction(turn)
    assert continuity and "data leakage" in continuity and "scaler" in continuity
    history_segment = continuity.split("PRIOR USER TURNS (chronological):", 1)[1]
    assert history_segment.find("data leakage") < history_segment.find("scaler")
    assert "Answer his current actual request" in continuity

    # Question after self-correction must perform the requested calculation,
    # rather than turn into a canned acknowledgment of the new number.
    trip = _with_history(
        ("hypothetical travel maths: exactly 180 min, train 55, activity 85, food 50. can it fit?", "factual_question"),
    )
    revised = classify_turn("wait scratch that, food is 30 not 50. does it fit NOW?", trip)
    assert revised.intent == "factual_question", revised.intent
    assert route_epistemic_authority(revised).mode == "user_context_reasoning"
    # This phase fixes CONTEXT and ROUTING; Core deterministic revised-budget
    # arithmetic will be tested separately before relying on exact results.

    python_state = _with_history(
        ("python question: def f(x=[]): x.append(7); return x; why does f() reuse x?", "factual_question"),
    )
    why = classify_turn("WHAT why didn't python make a new list every call 😭", python_state)
    assert why.intent == "factual_question", why.intent
    assert route_epistemic_authority(why).mode == "user_context_reasoning"

    wifi = _with_history(
        ("my wired console gets 600 Mbps but phone upstairs gets 20, what should I test first?", "factual_question"),
    )
    results = classify_turn("tested it: phone hits 580 next to the main mesh node but 20 upstairs. what does that rule out?", wifi)
    assert route_epistemic_authority(results).mode == "user_context_reasoning"

    choices = _with_history(
        ("mac vs windows for dev. gimme trade-offs", "casual_conversation"),
    )
    narrower = classify_turn("okay narrow it to Python, Linux VMs and networking", choices)
    assert route_epistemic_authority(narrower).mode == "user_context_reasoning"

    # Phase 2 compatibility: a recommendation remains a recommendation even
    # after Oliver has just been talking about the same product and purpose.
    # The previous B1 implementation incorrectly intercepted this as factual
    # task reasoning because 'shoes' and 'walking' overlapped.
    shoes = _with_history((
        "They are a pair of XT6s for my trip to China in 2 months time. "
        "Gotta buy good shoes for walking that much ya know.",
        "share_context",
    ))
    for recommendation in (
        "What shoes should I buy for walking all day?",
        "What shoes should I buy instead?",
    ):
        recommendation_turn = classify_turn(recommendation, shoes)
        assert recommendation_turn.intent == "recommendation_request", (
            recommendation, recommendation_turn.intent,
        )
        assert recommendation_turn.should_recommend
        assert recommendation_turn.entities.get("_user_grounded_followup") is None
    # A genuine follow-up calculation/question should still use the new mode.
    assert classify_turn(
        "wait scratch that, food is 30 not 50. does it fit NOW?", trip,
    ).entities.get("_user_grounded_followup") == "true"

    # Non-standard recall wording is never a public-world question, including
    # the version that used to ignore the latest user correction.
    for prompt in (
        "bro what colour cube did i say it's in NOW?",
        "nah mate what did i ACTUALLY tell you about my notebook's location?",
    ):
        recalled = classify_turn(prompt)
        assert recalled.intent == "conversation_recall", (prompt, recalled.intent)
        assert route_epistemic_authority(recalled).authority == "live_conversation"

    # The established private-user authority must remain stronger than a
    # general context follow-up (original acceptance breakfast scenario).
    meal_state = _with_history(("I had toast and yoghurt for breakfast today.", "share_context"))
    private_meal = classify_turn("What did I eat for breakfast today?", meal_state)
    assert private_meal.entities.get("_user_grounded_followup") is None
    assert route_epistemic_authority(private_meal).mode == "private_user_evidence"

    # No accidental web suppression on new topics and genuinely fresh lookups.
    keyboard = _with_history(("my keyboard finally arrived lmao", "share_context"))
    dns = classify_turn("What port does DNS normally use?", keyboard)
    assert dns.entities.get("_user_grounded_followup") is None
    assert route_epistemic_authority(dns).mode == "public_source_verified"
    assert classify_user_grounded_followup(
        "anyway why does my monitor flicker?", bounded_recent_user_turns(keyboard),
    ) is None
    assert classify_user_grounded_followup(
        "can you check the latest price online?", bounded_recent_user_turns(keyboard),
    ) is None

    assert classify_turn("Scratch that, I moved it to the bottom drawer.", keyboard).intent == "self_correction"
    assert classify_turn("actually add an interview block to my calendar on Wednesday", choices).intent == "calendar_event_creation_request"
    assert "user_context_reasoning" in (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")

    print("PASS: bounded user history, natural follow-up routing, recall variants, tool/privacy boundaries")


if __name__ == "__main__":
    run()
