import sys
from pathlib import Path
from types import SimpleNamespace


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


from core.conversation_claim_boundary import (
    apply_conversational_claim_boundary,
    build_conversational_claim_boundary_instruction,
)
from core.conversation_state import (
    ConversationState,
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

    return state.resolve_follow_up(
        turn
    )


def _complete(
    state: ConversationState,
    turn,
):
    state.update_from_turn(
        turn
    )


def _contract(
    *,
    allow_new_factual_claims=True,
):
    return SimpleNamespace(
        allow_new_factual_claims=(
            allow_new_factual_claims
        ),
        forbidden_behaviours=[],
    )


def run():
    # --------------------------------------------------
    # 1. "Anyway" is a topical boundary, not automatic continuity.
    # --------------------------------------------------

    state = ConversationState()

    first = _prepare(
        state,
        "The final tournament arc is still one of my favourites",
    )

    _complete(
        state,
        first,
    )

    switched = _prepare(
        state,
        (
            "anyway why does my monitor sometimes flicker "
            "when VRR is on?"
        ),
    )

    assert (
        "_conversation_context_user_text"
        not in switched.entities
    )

    assert switched.is_follow_up is False

    # An actual deictic/pronoun still wins even after "anyway".
    state = ConversationState()

    antecedent = _prepare(
        state,
        "Marin's decision was ridiculous",
    )

    _complete(
        state,
        antecedent,
    )

    deictic = _prepare(
        state,
        "anyway do you think she was right?",
    )

    assert deictic.is_follow_up is True
    assert (
        deictic.resolved_referents[
            "she"
        ]
        == "Marin"
    )

    # --------------------------------------------------
    # 2. Social/opinion turns lose permission to invent external facts.
    # --------------------------------------------------

    opinion_turn = SimpleNamespace(
        intent="share_opinion",
        raw_text=(
            "do you think she handled it well though?"
        ),
        entities={
            "_conversation_context_user_text": (
                "Marin's handling of the vote annoyed me"
            ),
        },
        resolved_referents={
            "she": "Marin",
        },
    )

    opinion_route = SimpleNamespace(
        authority="conversation",
        mode="subjective",
    )

    opinion_contract = _contract(
        allow_new_factual_claims=True,
    )

    mode = apply_conversational_claim_boundary(
        turn=opinion_turn,
        route=opinion_route,
        contract=opinion_contract,
    )

    assert mode == "social_claim_ceiling"
    assert (
        opinion_contract
        .allow_new_factual_claims
        is False
    )

    rendered_limits = "\n".join(
        opinion_contract
        .forbidden_behaviours
    )

    assert (
        "Do not invent literal actions"
        in rendered_limits
    )

    assert (
        "reaction only"
        in rendered_limits
    )

    assert (
        "Preserve the direction and meaning"
        in rendered_limits
    )

    instruction = (
        build_conversational_claim_boundary_instruction(
            turn=opinion_turn,
            route=opinion_route,
            mode=mode,
        )
    )

    assert instruction is not None
    assert (
        "CORE CONVERSATIONAL CLAIM BOUNDARY:"
        in instruction
    )
    assert (
        "Marin's handling of the vote annoyed me"
        in instruction
    )
    assert "she -> Marin" in instruction
    assert (
        "Prior Mairon/assistant prose is not factual authority."
        in instruction
    )

    # --------------------------------------------------
    # 3. Casual reaction gets the same literal-claim ceiling.
    # --------------------------------------------------

    casual_turn = SimpleNamespace(
        intent="casual_conversation",
        raw_text=(
            "Marin's handling of the vote is pissing me off"
        ),
        entities={},
        resolved_referents={},
    )

    casual_route = SimpleNamespace(
        authority="live_conversation",
        mode="social_conversation",
    )

    casual_contract = _contract(
        allow_new_factual_claims=False,
    )

    casual_mode = (
        apply_conversational_claim_boundary(
            turn=casual_turn,
            route=casual_route,
            contract=casual_contract,
        )
    )

    assert casual_mode == "social_claim_ceiling"
    assert (
        casual_contract
        .allow_new_factual_claims
        is False
    )

    # --------------------------------------------------
    # 4. Recommendation mode keeps title-level freedom but limits fake detail.
    # --------------------------------------------------

    recommendation_turn = SimpleNamespace(
        intent="recommendation_request",
        raw_text="what should i watch then?",
        entities={
            "_conversation_context_user_text": (
                "i want something dark and character driven. "
                "definitely not a comedy"
            ),
        },
        resolved_referents={},
    )

    recommendation_route = SimpleNamespace(
        authority="conversation_model",
        mode="conversation",
    )

    recommendation_contract = _contract(
        allow_new_factual_claims=True,
    )

    recommendation_mode = (
        apply_conversational_claim_boundary(
            turn=recommendation_turn,
            route=recommendation_route,
            contract=recommendation_contract,
        )
    )

    assert (
        recommendation_mode
        == "recommendation_detail_ceiling"
    )

    # Naming a recommendation still requires model-memory freedom.
    assert (
        recommendation_contract
        .allow_new_factual_claims
        is True
    )

    recommendation_limits = "\n".join(
        recommendation_contract
        .forbidden_behaviours
    )

    assert (
        "cast/creator names"
        in recommendation_limits
    )

    assert (
        "Do not ask Oliver to repeat constraints"
        in recommendation_limits
    )

    recommendation_instruction = (
        build_conversational_claim_boundary_instruction(
            turn=recommendation_turn,
            route=recommendation_route,
            mode=recommendation_mode,
        )
    )

    assert (
        "definitely not a comedy"
        in recommendation_instruction
    )

    # --------------------------------------------------
    # 5. Public factual questions and tool routes are untouched.
    # --------------------------------------------------

    factual_turn = SimpleNamespace(
        intent="factual_question",
        raw_text="Who is the current CEO of AMD?",
        entities={},
        resolved_referents={},
    )

    factual_route = SimpleNamespace(
        authority="public_web",
        mode="public_source_verified",
    )

    factual_contract = _contract(
        allow_new_factual_claims=False,
    )

    assert (
        apply_conversational_claim_boundary(
            turn=factual_turn,
            route=factual_route,
            contract=factual_contract,
        )
        is None
    )

    desktop_turn = SimpleNamespace(
        intent="launch_application",
        raw_text="open calculator",
        entities={},
        resolved_referents={},
    )

    desktop_route = SimpleNamespace(
        authority="desktop",
        mode="tool_result",
    )

    desktop_contract = _contract(
        allow_new_factual_claims=False,
    )

    assert (
        apply_conversational_claim_boundary(
            turn=desktop_turn,
            route=desktop_route,
            contract=desktop_contract,
        )
        is None
    )

    # --------------------------------------------------
    # 6. Production application boundary must install the policy before
    #    rendering the Answer Contract.
    # --------------------------------------------------

    application_source = (
        PROJECT_ROOT
        / "src"
        / "application_service.py"
    ).read_text(
        encoding="utf-8",
    )

    apply_position = (
        application_source.find(
            "apply_conversational_claim_boundary("
        )
    )

    contract_render_position = (
        application_source.find(
            ".answer_contract\n"
            "                    .to_model_instruction()"
        )
    )

    assert apply_position >= 0
    assert contract_render_position >= 0
    assert (
        apply_position
        < contract_render_position
    )

    assert (
        "[Grounding] Conversational "
        in application_source
    )

    print(
        "Mairon Phase 11.2.2 conversational claim-authority tests: PASS"
    )


if __name__ == "__main__":
    run()
