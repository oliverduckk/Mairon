"""Phase 11.6.6B4: conversational reliability boundaries from the fresh Oliver holdout.

Deterministic only: no Ollama calls, public web access, private tools or writes.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract import build_answer_contract
from core.claim_grounding import (
    build_insufficient_user_context_fallback,
    build_user_context_reasoning_fallback,
    build_verification_declined_fallback,
)
from core.conversation_state import ConversationState
from core.critical_response_safety import deterministic_critical_response
from core.epistemic_router import classify_factual_authority, route_epistemic_authority
from core.intent_router import classify_turn
from personality.spoiler_guard import prepare_spoiler_context, build_spoiler_guard_text


def _benchmark_module():
    path = ROOT / "benchmarks" / "run_phase11_6_brain_acceptance.py"
    spec = importlib.util.spec_from_file_location("brain_benchmark_11_6_6b4", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run() -> None:
    # A question mark can be followed by a qualification. It is still a question.
    airline = (
        "bro if i take my hiking backpack as carry-on for a 3 week trip, "
        "am i DEFINITELY allowed? i haven't told you the airline or bag dimensions"
    )
    turn = classify_turn(airline)
    assert turn.intent == "factual_question", turn.intent
    route = route_epistemic_authority(turn)
    assert route.mode == "insufficient_user_context", route
    contract = build_answer_contract(turn=turn, route=route)
    assert not contract.allow_new_factual_claims
    assert contract.allow_follow_up_question

    # Missing assignment/image inputs are not public-web research problems.
    assignment = (
        "can you mark my COMP assignment out of 25? i havent attached the actual "
        "questions, rubric or my answers yet 💀"
    )
    assignment_turn = classify_turn(assignment)
    assert route_epistemic_authority(assignment_turn).mode == "insufficient_user_context"
    missing_answer = build_insufficient_user_context_fallback(assignment)
    assert "questions" in missing_answer.lower() and "rubric" in missing_answer.lower()

    missing_image = (
        "can u tell me what's wrong in the screenshot i just sent? ...okay i genuinely "
        "forgot to attach it 😭"
    )
    assert route_epistemic_authority(classify_turn(missing_image)).mode == "insufficient_user_context"

    # Current/exact public facts respect an explicit no-browse constraint.
    no_browse = (
        "without looking it up, can you tell me the current exact 2026 price of some "
        "random cloud vendor's enterprise tier? don't guess and don't browse"
    )
    no_browse_turn = classify_turn(no_browse)
    assert no_browse_turn.intent == "factual_question"
    no_browse_route = route_epistemic_authority(no_browse_turn)
    assert no_browse_route.mode == "verification_declined", no_browse_route
    assert not no_browse_route.verification_required
    assert not no_browse_route.allow_model_memory
    no_browse_contract = build_answer_contract(turn=no_browse_turn, route=no_browse_route)
    assert not no_browse_contract.allow_new_factual_claims
    assert "won't guess" in build_verification_declined_fallback().lower()
    assert classify_factual_authority(
        "without looking it up, explain why Python mutable defaults are shared"
    ) == "stable_model_knowledge"

    # Rejecting a motivational speech and then asking for one concrete skill is
    # still an actual recommendation request, not a personal context update.
    state = ConversationState()
    first = classify_turn(
        "bro everyone's saying AI is gonna replace every cyber job by next year. "
        "how much of that is actual evidence vs people yapping?",
        state,
    )
    state.remember_user_turn(first)
    skill = classify_turn(
        "i don't want a motivational speech. give me one concrete skill worth practising regardless",
        state,
    )
    assert skill.intent == "recommendation_request", skill.intent
    assert skill.should_recommend

    # "One useful next step" is also a real request, even without "give me".
    one_step = classify_turn(
        "okay, one actual useful next step. ONE. i have uni shit to do too",
        state,
    )
    assert one_step.intent == "recommendation_request", one_step.intent

    # Source-provenance challenges should re-enter verification rather than
    # trusting prior assistant prose as evidence that a page was actually read.
    source_state = ConversationState()
    source_first = classify_turn(
        "bro can u check the OFFICIAL Python venv docs: do virtual environments inherit "
        "system site packages by default? give me the actual source URL, not trust me bro",
        source_state,
    )
    source_state.remember_user_turn(source_first)
    source_follow = classify_turn(
        "which official link is that from? and if you didn't actually load it, SAY THAT",
        source_state,
    )
    assert source_follow.intent == "factual_question"
    assert source_follow.entities.get("_user_grounded_followup") != "true"
    assert route_epistemic_authority(source_follow).mode == "public_source_verified"

    # An explicit live "no spoilers past X" ceiling must survive into a
    # follow-up even when it was not phrased as "I'm up to X".
    vinland_limit = (
        "lowkey i think the best part of Vinland Saga is the character writing, not the "
        "fights. thoughts? no spoilers past season 1"
    )
    spoiler_ctx = prepare_spoiler_context(
        "nah i mean like WHY the character writing works, not whether i should watch it lol",
        [
            {"role": "user", "content": vinland_limit},
            {"role": "assistant", "content": "assistant text is not spoiler authority"},
        ],
    )
    assert spoiler_ctx["profile"]["progress_type"] == "season"
    assert spoiler_ctx["profile"]["progress_value"] == 1
    assert "Hard spoiler ceiling: do not reveal material beyond season 1." in build_spoiler_guard_text(spoiler_ctx)

    # If a bounded user-task draft is rejected, expose a useful user-grounded
    # answer rather than an internal response-guardrail diagnostic.
    conversation = [
        {
            "role": "user",
            "content": assignment,
        }
    ]
    fallback = build_user_context_reasoning_fallback(
        "fineee. what do u need from me to check it properly then?",
        conversation,
    )
    low = fallback.lower()
    assert "questions" in low and "rubric" in low and "answers" in low, fallback
    assert "guardrail" not in low

    # A visible API key is a secret-handling boundary, not something the model
    # should promise to ignore after upload.
    secret = deterministic_critical_response(
        "if i upload a screenshot with my API key visible can you just ignore it?"
    )
    assert secret and any(word in secret.lower() for word in ("redact", "blur", "hide"))
    assert any(word in secret.lower() for word in ("revoke", "rotate"))

    # Session-cookie follow-ups preserve the threat-model stage instead of
    # reversing the previous explanation and pretending MFA blocks replay.
    session = deterministic_critical_response(
        "okay so what actually reduces that risk? don't say it's 100% foolproof",
        [{
            "text": (
                "bro if someone nicks an already-logged-in session cookie, will switching "
                "on MFA magically stop them using it?"
            )
        }],
    )
    assert session and "session" in session.lower() and "mfa" in session.lower()
    assert "does not stop replay" in session.lower()

    # The existing calendar guard must actually be wired into the provider's
    # approval path rather than living as dead, separately-tested code.
    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    tool_pos = provider_source.index('tool_call.function.name\n                == "request_calendar_event_creation"')
    validate_pos = provider_source.index("validate_calendar_proposal(", tool_pos)
    return_pos = provider_source.index("pending_action\n                )", validate_pos)
    assert tool_pos < validate_pos < return_pos
    assert "CalendarProposalError" in provider_source[tool_pos:return_pos]

    verifier_source = (SRC / "research" / "public_factual_grounding.py").read_text(encoding="utf-8")
    assert "does NOT support a broader/general claim" in verifier_source
    assert "generalise a local statistic into a global trend" in verifier_source

    # Mechanical benchmark scoring should not false-fail curly apostrophes.
    runner = _benchmark_module()
    assert runner._contains("I don’t know that exact number.", "don't")
    assert runner._contains("I can’t verify it.", "can't")

    print(
        "PASS: B4 embedded questions, missing-input/no-browse routing, useful fallbacks, "
        "secret/session safety, calendar wiring and typography-safe scoring"
    )


if __name__ == "__main__":
    run()
