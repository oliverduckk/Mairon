import re
from dataclasses import dataclass
from typing import Optional

from core.turn_state import TurnState
from core.conversational_research import (
    contextual_opinion_requires_public_grounding,
)


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


# Phase 10.7.10 — generic factual authority classification.
#
# These patterns describe information classes, not named entities. Existing
# deterministic/private workflow authorities still take precedence below.
FRESHNESS_PATTERNS = [
    r"\btoday\b",
    r"\btonight\b",
    r"\bright now\b",
    r"\bcurrently\b",
    r"\bcurrent(?:ly)?\b",
    r"\blatest\b",
    r"\bnewest\b",
    r"\bmost recent\b",
    r"\brecent(?:ly)?\b",
    r"\bthis (?:week|month|year)\b",
    r"\bas of\b",
    r"\bstill\b",
]

EXPLICIT_PUBLIC_VERIFICATION_PATTERNS = [
    r"\blook (?:it )?up\b",
    r"\bsearch (?:the )?(?:web|internet|online)\b",
    r"\bcheck (?:the )?(?:web|internet|online)\b",
    r"\bverify\b",
    r"\bfact[- ]?check\b",
    r"\bsource(?:s)?\b",
    r"\bcitation(?:s)?\b",
    r"\bofficial source\b",
]

CHANGING_PUBLIC_FACT_PATTERNS = [
    r"\bprice\b",
    r"\bcost\b",
    r"\bhow much (?:is|does|are|do)\b",
    r"\bin stock\b",
    r"\bavailable (?:now|today|in|at|from)\b",
    r"\brelease date\b",
    r"\bwhen (?:does|will) .{0,80}\brelease\b",
    r"\bceo\b",
    r"\bpresident\b",
    r"\bprime minister\b",
    r"\bhead coach\b",
    r"\bschedule\b",
    r"\btimetable\b",
    r"\bscore\b",
    r"\bstandings\b",
    r"\bweather\b",
    r"\bexchange rate\b",
    r"\bstock price\b",
    r"\bshare price\b",
]

SPECIFIC_LOOKUP_PATTERNS = [
    r"^\s*who\b",
    r"^\s*when\b",
    r"^\s*where\b",
    r"\bwhat happened\b",
    r"\bhow many\b",
    r"\bhow far\b",
    r"\bhow old\b",
    r"\bhow tall\b",
    r"\bnet worth\b",
    r"\bfounded by\b",
    r"\bwritten by\b",
    r"\bcreated by\b",
    r"\bdirected by\b",
    r"\bexact(?:ly)?\b",
]

STABLE_EXPLANATION_PATTERNS = [
    r"^\s*what (?:is|are)\b",
    r"^\s*what does\b",
    r"^\s*how (?:does|do)\b",
    r"^\s*why (?:does|do|is|are)\b",
    r"^\s*explain\b",
    r"^\s*describe\b",
    r"^\s*define\b",
    r"^\s*compare\b",
    r"^\s*walk\s+me\s+through\b",
    r"\bdifference between\b",
    r"\bhow .{0,80}\bworks?\b",
]


def _matches_any(text: str, patterns) -> bool:
    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in patterns
    )


def classify_factual_authority(text: str) -> str:
    """Second-stage authority decision for generic factual questions."""
    value = str(text or "").strip()

    if not value:
        return "public_source_verified"

    if _matches_any(value, EXPLICIT_PUBLIC_VERIFICATION_PATTERNS):
        return "public_source_verified"

    if _matches_any(value, FRESHNESS_PATTERNS):
        return "public_source_verified"

    if _matches_any(value, CHANGING_PUBLIC_FACT_PATTERNS):
        return "public_source_verified"

    if _matches_any(value, SPECIFIC_LOOKUP_PATTERNS):
        return "public_source_verified"

    if _matches_any(value, STABLE_EXPLANATION_PATTERNS):
        return "stable_model_knowledge"

    # Accuracy-first default: ambiguous external factual requests verify.
    return "public_source_verified"


def factual_question_requires_live_data(text: str) -> bool:
    """Whether verification concerns changing/current public state."""
    value = str(text or "").strip()
    return bool(
        _matches_any(value, FRESHNESS_PATTERNS)
        or _matches_any(value, CHANGING_PUBLIC_FACT_PATTERNS)
    )


def route_epistemic_authority(
    turn: TurnState,
) -> EpistemicRoute:
    """
    Determine HOW Mairon should know the answer.

    This is intentionally deterministic for high-value/private workflows.
    """

    if turn.intent == "calculate_arithmetic":
        return EpistemicRoute(
            authority="core_arithmetic",
            mode="deterministic_calculation",
            verification_required=False,
            allow_model_memory=False,
            live_data_required=False,
            private_data_required=False,
            reason=(
                "Unambiguous arithmetic is owned by deterministic Core "
                "evaluation, not language-model interpretation or memory."
            ),
        )

    if turn.intent == "consequential_advice":
        return EpistemicRoute(
            authority="public_web",
            mode="public_source_verified_advice",
            verification_required=True,
            allow_model_memory=False,
            live_data_required=True,
            private_data_required=False,
            reason=(
                "Consequential real-world guidance requires current public "
                "evidence; model memory and casual conversation are not "
                "authoritative enough."
            ),
        )

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

    if turn.intent in {
        "email_search",
        "email_read",
    }:
        return EpistemicRoute(
            authority="gmail",
            mode="tool_verified",
            verification_required=True,
            allow_model_memory=False,
            live_data_required=True,
            private_data_required=True,
            reason=(
                "Email existence and contents must come from verified Gmail "
                "data, not model memory or prior assistant prose."
            ),
        )

    if (
        turn.intent == "share_opinion"
        and contextual_opinion_requires_public_grounding(
            turn
        )
    ):
        return EpistemicRoute(
            authority="public_web",
            mode="public_source_verified_opinion",
            verification_required=True,
            allow_model_memory=False,
            live_data_required=False,
            private_data_required=False,
            reason=(
                "Oliver asked for Mairon's judgement about a clearly public or "
                "external subject, but the live conversation does not establish "
                "enough factual substrate for a detailed opinion. Core requires "
                "bounded public evidence before the personality layer answers."
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

    if turn.intent == "self_correction":
        return EpistemicRoute(
            authority="user_turn_and_live_conversation",
            mode="self_correction",
            verification_required=False,
            allow_model_memory=False,
            reason=(
                "Oliver's latest explicit self-correction is authoritative for "
                "what he meant; older conflicting user wording is superseded."
            ),
        )

    if turn.intent == "conversation_recall":
        return EpistemicRoute(
            authority="live_conversation",
            mode="conversation_recall",
            verification_required=True,
            allow_model_memory=False,
            reason=(
                "A question about what was said in this conversation must be "
                "answered from the live user-authored conversation, not model "
                "memory, web research, or unrelated journal retrieval."
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

    if turn.intent == "casual_conversation":
        return EpistemicRoute(
            authority="live_conversation",
            mode="social_conversation",
            verification_required=False,
            allow_model_memory=False,
            reason=(
                "Ordinary banter should stay anchored to the live conversation "
                "instead of importing unrelated world facts or old journal material."
            ),
        )

    if turn.intent == "factual_question":
        factual_mode = classify_factual_authority(
            turn.raw_text
        )

        if factual_mode == "stable_model_knowledge":
            return EpistemicRoute(
                authority="local_model_knowledge",
                mode="stable_model_knowledge",
                verification_required=False,
                allow_model_memory=True,
                live_data_required=False,
                reason=(
                    "The question asks for a durable general explanation; local "
                    "model knowledge is permitted, but changing/specific public "
                    "facts must not be invented."
                ),
            )

        live_data_required = factual_question_requires_live_data(
            turn.raw_text
        )

        return EpistemicRoute(
            authority="public_web",
            mode="public_source_verified",
            verification_required=True,
            allow_model_memory=False,
            live_data_required=live_data_required,
            reason=(
                "The factual question depends on specific or changing public-world "
                "information, so Core requires public-source evidence rather than "
                "model memory."
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
