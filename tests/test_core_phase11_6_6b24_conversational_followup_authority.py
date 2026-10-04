"""Phase 11.6 B24 — conversational follow-up authority.

Protect the distinction between:
- explicit requests for Mairon's own subjective judgement;
- contextual agreement/opinion follow-ups; and
- standalone factual questions that still require factual authority.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from core.conversation_state import ConversationState  # noqa: E402
from core.epistemic_router import route_epistemic_authority  # noqa: E402
from core.intent_router import classify_turn  # noqa: E402


def _direct(text: str):
    turn = classify_turn(text)
    return turn, route_epistemic_authority(turn)


def _prepare(state: ConversationState, text: str):
    turn = classify_turn(
        text,
        conversation_state=state,
    )
    return state.resolve_follow_up(turn)


def _complete(state: ConversationState, turn) -> None:
    state.update_from_turn(turn)


def run() -> None:
    # Existing Mairon preference/ranking behavior must survive B24.
    for text in (
        "What is your top 3 mangas?",
        "what's your favourite manga?",
        "who are your top 5 characters?",
    ):
        turn, route = _direct(text)
        assert turn.intent == "share_opinion", (text, turn.intent, turn.reasons)
        assert route.authority == "conversation", (text, route)
        assert route.mode == "subjective", (text, route)

    # New direct opinion-request shapes found during Gate-B human review.
    for text in (
        "what do you actually think of The Wandering Inn? dont just agree with me, i want your take",
        "what's your take on slower stories versus faster ones?",
        "what is your opinion on stories that take ages to get moving?",
        "reckon you're finally becoming useful?",
    ):
        turn, route = _direct(text)
        assert turn.intent == "share_opinion", (text, turn.intent, turn.reasons)
        assert turn.factuality == "subjective", (text, turn.factuality)
        assert route.authority == "conversation", (text, route)
        assert route.mode == "subjective", (text, route)
        assert route.verification_required is False, (text, route)

    # Agreement is contextual. In the live debate it should remain in the
    # conversation instead of launching a literal public search for "or nah".
    debate = ConversationState()

    first = _prepare(
        debate,
        "i think a slower story can be better than a fast one if the character work is actually doing something",
    )
    _complete(debate, first)

    second = _prepare(
        debate,
        "but if five chapters pass and nothing about the characters or plot changes, thats not slow burn, thats just bad pacing",
    )
    _complete(debate, second)

    third = _prepare(
        debate,
        "you agree with that distinction or nah?",
    )

    assert third.intent == "share_opinion", (third.intent, third.reasons)
    assert third.is_follow_up is True
    assert third.entities.get("_conversation_context_user_text") == (
        "but if five chapters pass and nothing about the characters or plot changes, thats not slow burn, thats just bad pacing"
    )

    third_route = route_epistemic_authority(third)
    assert third_route.authority == "conversation", third_route
    assert third_route.mode == "subjective", third_route

    # Existing public-context opinion grounding must remain intact. B24 must
    # not short-circuit the Phase 11.2.3 referent/grounding mechanism.
    public = ConversationState()

    setup = _prepare(
        public,
        "Horikita's handling of the class vote in COTE is already pissing me off",
    )
    _complete(public, setup)

    opinion = _prepare(
        public,
        "do you think she handled it well though?",
    )

    assert opinion.intent == "share_opinion", (opinion.intent, opinion.reasons)
    assert opinion.is_follow_up is True
    assert opinion.entities.get("_conversation_public_grounding_required") == "true"

    public_route = route_epistemic_authority(opinion)
    assert public_route.authority == "public_web", public_route
    assert public_route.mode == "public_source_verified_opinion", public_route

    # Negative controls: factual agreement/current-state questions remain
    # factual when there is no conversational opinion context to inherit.
    for text in (
        "do you agree TCP uses a three-way handshake?",
        "what do you think the current NVIDIA driver version is?",
        "is there a new NVIDIA driver out right now?",
        "what are the top 3 manga by lifetime sales?",
    ):
        turn, route = _direct(text)
        assert turn.intent == "factual_question", (text, turn.intent, turn.reasons)
        assert route.mode in {
            "stable_model_knowledge",
            "public_source_verified",
        }, (text, route)

    print("PASS: B24 conversational opinion/follow-up authority")


if __name__ == "__main__":
    run()
