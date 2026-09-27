"""Phase 11.6.2: deterministic routing and benchmark-acceptance repairs.

Standalone style matches Mairon's existing regression runner:
    python tests/test_core_phase11_6_2_brain_acceptance_hardening.py
"""

import sys
from pathlib import Path
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.arithmetic import extract_arithmetic_request, evaluate_arithmetic_expression
from core.claim_grounding import _unsupported_personal_history_year_claims
from core.epistemic_router import route_epistemic_authority, classify_factual_authority
from core.intent_router import classify_turn, reconstruct_bounded_factual_followup
from core.orchestrator import MaironCore
from core.supplied_reasoning import classify_supplied_reasoning


class _PriorUserOnly:
    """Enough conversation state for isolated routing; no assistant evidence."""

    active_intent = None
    active_entities = {}

    def __init__(self, previous_user_text=None):
        self.previous_user_text = previous_user_text

    def latest_user_turn(self):
        if self.previous_user_text is None:
            return None
        return {"text": self.previous_user_text}


def _turn(text, previous_user_text=None):
    return classify_turn(text, _PriorUserOnly(previous_user_text))


def run():
    # A. Natural user-authored recall, never public-world lookup.
    for utterance in (
        "Where did I say the USB adapter is now?",
        "What was the code word I just gave you?",
        "What did I just mention?",
    ):
        turn = _turn(utterance)
        assert turn.intent == "conversation_recall", (utterance, turn.intent)
        route = route_epistemic_authority(turn)
        assert route.authority == "live_conversation", (utterance, route)

    # Do not confuse challenging MAIRON with Oliver asking to recall his words.
    challenge = _turn("Where did you get that claim?")
    assert challenge.intent == "correct_mairon", challenge.intent

    # B. Unit-consistent natural arithmetic stays in deterministic Core.
    storage = "A drive has 931 GiB free and I use 37 GiB. How much is left?"
    request = extract_arithmetic_request(storage)
    assert request is not None and request.operation == "subtract"
    assert evaluate_arithmetic_expression(request.expression) == Decimal(894)
    turn = _turn(storage)
    assert turn.intent == "calculate_arithmetic", turn.intent
    assert route_epistemic_authority(turn).authority == "core_arithmetic"
    core_answer = MaironCore().prepare_turn(storage)
    assert "894" in str(core_answer.direct_response), core_answer.direct_response

    money = extract_arithmetic_request(
        "I had 50 dollars and spent 12 dollars. How much is left?"
    )
    assert money is not None
    assert evaluate_arithmetic_expression(money.expression) == Decimal(38)
    assert extract_arithmetic_request(
        "A drive has 931 GiB free and I use 37 MB. How much is left?"
    ) is None

    # C. All premises supplied: public web contributes no relevant evidence.
    appointment = (
        "I need to be at an appointment at 2pm. The drive takes 45 minutes "
        "and I want to arrive 15 minutes early. If I leave at 1:20pm, am I good?"
    )
    for utterance, required in (
        (appointment, "1:00pm"),
        ("Every Neral is a Vesk, and no Vesk is blue. "
         "Can any Neral be blue?", "no Neral"),
    ):
        reasoning = classify_supplied_reasoning(utterance)
        assert reasoning is not None and required in (reasoning.direct_answer or "")
        turn = _turn(utterance)
        assert turn.intent == "reason_from_supplied_premises", turn.intent
        assert route_epistemic_authority(turn).mode == "user_premise_reasoning"
        decision = MaironCore().prepare_turn(utterance)
        assert required in str(decision.direct_response), decision.direct_response

    trace = "In Python, if I run x = [1, 2, 3], then y = x, then y.append(4), what is x afterwards?"
    assert _turn(trace).intent == "reason_from_supplied_premises"
    assert route_epistemic_authority(_turn(trace)).mode == "user_premise_reasoning"
    assert classify_supplied_reasoning("What time is the appointment tomorrow?") is None

    # D. A fragment can inherit QUESTION FORM only from the prior user turn.
    prior = "What's the default port for SSH?"
    resolved = reconstruct_bounded_factual_followup("and HTTPS?", prior)
    assert resolved == "What is the default port for HTTPS?", resolved
    followed = _turn("and HTTPS?", prior)
    assert followed.intent == "factual_question"
    assert followed.entities["factual_query"] == resolved
    assert route_epistemic_authority(followed).mode == "stable_model_knowledge"
    unrelated = _turn("and HTTPS?", "My keyboard arrived.")
    assert "factual_query" not in unrelated.entities
    assert reconstruct_bounded_factual_followup("and HTTPS?", "") is None
    assert classify_factual_authority(
        "Look up the latest default port for HTTPS"
    ) == "public_source_verified"

    # E. Intent-specific calendar WRITE: proposal route, never silent execution.
    calendar = _turn(
        "Put a dentist appointment on my calendar for Friday from 3pm to 4pm."
    )
    assert calendar.intent == "calendar_event_creation_request", calendar.intent
    assert calendar.requested_action == "request_calendar_event_creation"
    assert calendar.should_use_tools and not calendar.should_answer_directly
    assert route_epistemic_authority(calendar).authority == "calendar"
    assert _turn(
        "I really should put dentist stuff on my calendar at some point."
    ).intent == "share_context"
    assert _turn("Create a sample Python function for me.").intent != "calendar_event_creation_request"

    # F. Focused spelling recovery changes classification, not raw user text.
    typo = "whts the diffrence between ram and storage in one sentence"
    typo_turn = _turn(typo)
    assert typo_turn.raw_text == typo
    assert typo_turn.intent == "factual_question", typo_turn.intent
    assert route_epistemic_authority(typo_turn).mode == "stable_model_knowledge"

    # G. User-only support for precise PERSONAL years; no prior model guesses.
    assert _unsupported_personal_history_year_claims(
        "My keyboard finally arrived.",
        "Finally, you've been waiting for it since 2023!",
        [],
    )
    assert not _unsupported_personal_history_year_claims(
        "My keyboard, ordered in 2023, finally arrived.",
        "You've been waiting since 2023!",
        [],
    )
    assert not _unsupported_personal_history_year_claims(
        "What happened to HTTP in 1999?",
        "HTTP has had a standard since 1999.",
        [],
    )

    print("PASS: Phase 11.6.2 brain acceptance hardening")


if __name__ == "__main__":
    run()
