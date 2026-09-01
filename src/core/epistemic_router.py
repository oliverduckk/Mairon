from dataclasses import dataclass
from typing import Optional

from core.turn_state import TurnState


@dataclass
class EpistemicRoute:
    """
    Core decision describing where factual authority for a turn belongs.
    """

    authority: str
    mode: str
    verification_required: bool
    allow_model_memory: bool
    live_data_required: bool = False
    private_data_required: bool = False
    reason: Optional[str] = None


def route_epistemic_authority(
    turn: TurnState,
) -> EpistemicRoute:
    """
    Determine HOW Mairon should know the answer.

    This is intentionally deterministic for high-value/private workflows.
    """

    if turn.intent == "order_status":
        return EpistemicRoute(
            authority="gmail",
            mode="tool_verified",
            verification_required=True,
            allow_model_memory=False,
            live_data_required=True,
            private_data_required=True,
            reason=(
                "Order status is private changing information; Gmail is "
                "the current authoritative source."
            ),
        )

    if turn.intent == "email_search":
        return EpistemicRoute(
            authority="gmail",
            mode="tool_verified",
            verification_required=True,
            allow_model_memory=False,
            live_data_required=True,
            private_data_required=True,
            reason=(
                "Email contents/status must come from Gmail, not model memory."
            ),
        )

    if turn.intent == "share_opinion":
        return EpistemicRoute(
            authority="conversation",
            mode="subjective",
            verification_required=False,
            allow_model_memory=True,
            reason=(
                "The user's subjective stance is supplied by the conversation."
            ),
        )

    if turn.intent == "share_context":
        return EpistemicRoute(
            authority="user_turn",
            mode="user_provided",
            verification_required=False,
            allow_model_memory=False,
            reason=(
                "The current user statement itself is authoritative for what "
                "Oliver says about his own context."
            ),
        )

    if turn.intent == "correct_mairon":
        return EpistemicRoute(
            authority="conversation_and_verification",
            mode="reconciliation",
            verification_required=True,
            allow_model_memory=False,
            reason=(
                "A correction requires reconciling Mairon's prior claim with "
                "the best available evidence."
            ),
        )

    if turn.intent == "factual_question":
        return EpistemicRoute(
            authority="epistemic_fallback",
            mode="classify_then_verify",
            verification_required=False,
            allow_model_memory=True,
            reason=(
                "Generic factual questions need a second-stage decision based "
                "on specificity, freshness, and available authoritative sources."
            ),
        )

    if turn.should_use_tools:
        return EpistemicRoute(
            authority=(
                turn.preferred_authority
                or "tool"
            ),
            mode="tool_result",
            verification_required=True,
            allow_model_memory=False,
            live_data_required=turn.requires_live_data,
            private_data_required=turn.requires_private_data,
            reason=(
                "The turn requests an action or authoritative tool-backed result."
            ),
        )

    return EpistemicRoute(
        authority="conversation_model",
        mode="conversation",
        verification_required=False,
        allow_model_memory=True,
        reason=(
            "No stronger authoritative source was identified by Core."
        ),
    )
