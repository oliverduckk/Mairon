"""Phase 11.6.6B2: user-only numeric state, extractive recall and conversational questions.

Run individually before the full regression suite:
    python tests/test_core_phase11_6_6b2_task_answers.py
No real web search, calendar changes, model calls or external state writes.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.task_budget import resolve_time_budget
from core.user_statement_recall import extract_latest_stated_colour
from core.followup_task import classify_user_grounded_followup, build_bounded_task_instruction
from core.intent_router import classify_turn
from core.epistemic_router import classify_factual_authority, route_epistemic_authority
from core.conversation_state import ConversationState
from core.turn_state import TurnState
from core.orchestrator import MaironCore


def _user(text, intent="factual_question"):
    return {"text": text, "intent": intent}


def run():
    first = (
        "hypothetical travel maths: we have exactly 180 min. "
        "train there 55, thing A 85, food 50. can we do it all? only use MY numbers"
    )
    second = "wait scratch that, food is 30 minutes not 50. does it fit NOW?"
    third = "and if the train is delayed by 20 min now?"

    # Pure parsing: exact arithmetic, latest correction, no web or model.
    a = resolve_time_budget(first)
    b = resolve_time_budget(second, [_user(first)])
    c = resolve_time_budget(third, [_user(first), _user(second)])
    assert a is not None and a.used_minutes == Decimal(190) and "10 minutes over" in a.answer
    assert b is not None and b.used_minutes == Decimal(170) and "10 minutes spare" in b.answer
    assert c is not None and c.used_minutes == Decimal(190) and "10 minutes over" in c.answer

    # Not a shortcut for unrelated historical numbers or live traffic research.
    assert resolve_time_budget("What port does DNS use?", [_user(first)]) is None
    assert resolve_time_budget("anyway how much time is left?", [_user(first)]) is None
    assert resolve_time_budget("check live train times, will it fit?", [_user(first)]) is None
    assert resolve_time_budget(
        "we have 90 min. travel 20, tour 40, lunch 15. does it fit?"
    ).used_minutes == Decimal(75)
    assert resolve_time_budget(
        "we have 90 min. travel 20, tour ??, lunch 15. does it fit?"
    ) is None

    red = "for this convo the spare camera battery is inside the RED packing cube"
    black = "WAIT correction the spare battery's in the BLACK cube not red. i moved it"
    question = "bro what colour cube did i say it's in NOW?"
    extract = extract_latest_stated_colour(question, [_user(red), _user(black)])
    assert extract is not None and "black" in extract.lower() and "red" not in extract.lower()
    assert extract_latest_stated_colour("what colour cube did i say it's in now?", []) is None
    assert extract_latest_stated_colour("what colour shirt am i wearing?", [_user(red)]) is None
    assert extract_latest_stated_colour(
        "what colour cube did i say it's in now?", [_user("not the black cube, it's somewhere else")]
    ) is None

    # The new scope isn't hardcoded to travel, cameras or the benchmark words.
    other = resolve_time_budget("we've got 120 minutes. commute 25, museum 45, lunch 40. can we do it?" )
    assert other is not None and other.used_minutes == Decimal(110)

    state = ConversationState()
    earlier = TurnState(raw_text="my wired console is getting 600 Mbps but phone upstairs is 20 Mbps")
    earlier.intent = "factual_question"
    state.remember_user_turn(earlier)
    follow = TurnState(raw_text="phone hits 580 next to main mesh node but 20 upstairs. what does that rule out?")
    follow.intent = "factual_question"
    state.remember_user_turn(follow)
    conclusion = "soooooo i should pay my isp more? LMAO"
    grounded = classify_user_grounded_followup(conclusion, state.recent_user_turns)
    assert grounded is not None and len(grounded) == 2
    classified = classify_turn(conclusion, state)
    assert classified.intent == "factual_question", classified.intent
    assert route_epistemic_authority(classified).mode == "user_context_reasoning"
    instruction = build_bounded_task_instruction(classified)
    assert instruction and "A joke must not replace a yes/no answer" in instruction

    # Real question inside informal preface must not collapse into "Fair."
    mirrorless = classify_turn("random tangent: why do mirrorless cameras eat batteries so fast lol")
    assert mirrorless.intent == "factual_question", mirrorless.intent
    assert classify_factual_authority(mirrorless.raw_text) == "stable_model_knowledge"
    assert classify_turn("What shoes should I buy for walking all day?").intent == "recommendation_request"

    # Core integration without any external tool/model calls, preserving
    # the real session state between turns.
    core = MaironCore()
    decisions = [core.prepare_turn(x) for x in (first, second, third)]
    for decision, expected in zip(decisions, ("10 minutes over", "10 minutes spare", "10 minutes over")):
        assert decision.direct_response and expected in decision.direct_response, decision
        assert decision.epistemic_route.mode == "user_premise_reasoning"

    recall_core = MaironCore()
    for user_text in (red, "random tangent: why do mirrorless cameras eat batteries so fast lol", black):
        recall_core.prepare_turn(user_text)
    recall_decision = recall_core.prepare_turn(question)
    assert recall_decision.turn.intent == "conversation_recall"
    assert recall_decision.direct_response and "black" in recall_decision.direct_response.lower()
    assert recall_decision.epistemic_route.mode == "conversation_recall"

    print("PASS: task arithmetic 190/170/190, user-only corrected recall, informal questions, and routing boundaries")


if __name__ == "__main__":
    run()
