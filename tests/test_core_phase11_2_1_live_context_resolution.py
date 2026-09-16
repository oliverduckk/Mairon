import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from core.conversation_state import (
    ConversationState,
    build_live_user_continuity_instruction,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


def _prepare(
    state: ConversationState,
    text: str,
):
    turn = classify_turn(
        text,
        conversation_state=state,
    )

    turn = state.resolve_follow_up(
        turn
    )

    return turn


def _complete(
    state: ConversationState,
    turn,
):
    state.update_from_turn(
        turn
    )


def run():
    # --------------------------------------------------
    # 1. Immediate named-subject continuity:
    #    evaluative pronoun follow-up must not become an unrelated web search.
    # --------------------------------------------------

    state = ConversationState()

    first = _prepare(
        state,
        "Marin's handling of the final vote is already pissing me off",
    )

    _complete(
        state,
        first,
    )

    # The test uses an arbitrary holdout name. Production contains no
    # franchise/title-specific routing.
    assert first.subject == "Marin"

    second = _prepare(
        state,
        "do you think she handled it well though?",
    )

    assert second.is_follow_up is True
    assert second.intent == "share_opinion"
    assert second.factuality == "subjective"
    assert second.should_use_tools is False
    assert second.resolved_referents[
        "she"
    ] == "Marin"

    assert (
        second.entities[
            "_conversation_context_user_text"
        ]
        == (
            "Marin's handling of the final vote "
            "is already pissing me off"
        )
    )

    route = route_epistemic_authority(
        second
    )

    assert route.authority == "conversation"
    assert route.mode == "subjective"

    packet = (
        build_live_user_continuity_instruction(
            second
        )
    )

    assert packet is not None
    assert "CORE LIVE USER CONTINUITY:" in packet
    assert "PREVIOUS OLIVER TURN:" in packet
    assert (
        "Marin's handling of the final vote "
        "is already pissing me off"
        in packet
    )
    assert "she -> Marin" in packet
    assert (
        "prior Mairon prose"
        in packet
    )

    # --------------------------------------------------
    # 2. Recommendation continuity:
    #    "what should I watch then?" must inherit immediate constraints and
    #    must not become public-web factual research.
    # --------------------------------------------------

    state = ConversationState()

    preference_turn = _prepare(
        state,
        (
            "i want something dark and character driven tonight. "
            "definitely not a comedy"
        ),
    )

    _complete(
        state,
        preference_turn,
    )

    recommendation = _prepare(
        state,
        "what should i watch then?",
    )

    assert (
        recommendation.intent
        == "recommendation_request"
    )
    assert recommendation.should_recommend is True
    assert recommendation.is_follow_up is True

    assert (
        recommendation.entities[
            "_conversation_context_user_text"
        ]
        == (
            "i want something dark and character driven tonight. "
            "definitely not a comedy"
        )
    )

    recommendation_route = (
        route_epistemic_authority(
            recommendation
        )
    )

    assert (
        recommendation_route.authority
        != "public_web"
    )

    recommendation_packet = (
        build_live_user_continuity_instruction(
            recommendation
        )
    )

    assert recommendation_packet is not None
    assert (
        "preserve relevant constraints"
        in recommendation_packet
    )
    assert "definitely not a comedy" in recommendation_packet

    # --------------------------------------------------
    # 3. Standalone recommendation shape also stays out of factual lookup.
    # --------------------------------------------------

    standalone = classify_turn(
        "what should i read tonight?",
        conversation_state=None,
    )

    assert (
        standalone.intent
        == "recommendation_request"
    )

    assert (
        route_epistemic_authority(
            standalone
        ).authority
        != "public_web"
    )

    # --------------------------------------------------
    # 4. Do not over-correct genuine factual questions.
    # --------------------------------------------------

    factual = classify_turn(
        "Who is the current CEO of AMD?",
        conversation_state=None,
    )

    assert factual.intent == "factual_question"

    factual_route = (
        route_epistemic_authority(
            factual
        )
    )

    assert factual_route.authority == "public_web"

    # A contextual factual pronoun remains factual. Phase 11.2.1 resolves
    # immediate discourse, but does not falsely convert every pronoun question
    # into an opinion.
    state = ConversationState()

    antecedent = _prepare(
        state,
        "Jensen Huang was the person I meant",
    )

    _complete(
        state,
        antecedent,
    )

    age_follow_up = _prepare(
        state,
        "how old is he?",
    )

    assert age_follow_up.is_follow_up is True
    assert age_follow_up.intent == "factual_question"
    assert (
        age_follow_up.resolved_referents[
            "he"
        ]
        == "Jensen Huang was the person I meant"
    )

    assert (
        route_epistemic_authority(
            age_follow_up
        ).authority
        == "public_web"
    )

    # --------------------------------------------------
    # 5. Tool-domain authority must not be hijacked by generic continuity.
    # --------------------------------------------------

    state = ConversationState()

    casual = _prepare(
        state,
        "im testing something completely unrelated",
    )

    _complete(
        state,
        casual,
    )

    email = _prepare(
        state,
        "Did I get an email from Prosple today?",
    )

    assert email.intent == "email_search"
    assert email.preferred_authority == "gmail"
    assert (
        "_conversation_context_user_text"
        not in email.entities
    )

    desktop = _prepare(
        state,
        "open calculator",
    )

    assert desktop.intent == "launch_application"
    assert desktop.preferred_authority == "desktop"
    assert (
        "_conversation_context_user_text"
        not in desktop.entities
    )

    # --------------------------------------------------
    # 6. Ephemeral context must not leak into active_entities.
    # --------------------------------------------------

    context_state = ConversationState()

    base_turn = _prepare(
        context_state,
        "Kira's choice was ridiculous",
    )

    _complete(
        context_state,
        base_turn,
    )

    follow = _prepare(
        context_state,
        "do you think she was right though?",
    )

    _complete(
        context_state,
        follow,
    )

    assert all(
        not str(
            key
        ).startswith(
            "_"
        )
        for key in (
            context_state
            .active_entities
            .keys()
        )
    )

    assert len(
        context_state.recent_user_turns
    ) == 2

    print(
        "Mairon Phase 11.2.1 live conversational-context resolution tests: PASS"
    )


if __name__ == "__main__":
    run()
