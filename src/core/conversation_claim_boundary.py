from __future__ import annotations

from typing import Any, Optional


SOCIAL_GROUNDED_INTENTS = {
    "casual_conversation",
    "share_context",
    "share_opinion",
}

RECOMMENDATION_INTENTS = {
    "recommendation_request",
}

SOCIAL_AUTHORITIES = {
    "live_conversation",
    "conversation",
    "user_turn",
}

RECOMMENDATION_AUTHORITIES = {
    "conversation_model",
    "conversation",
}


def _append_unique(
    values,
    additions,
) -> None:
    existing = {
        str(
            item
            or ""
        ).strip()
        for item in (
            values
            or []
        )
        if str(
            item
            or ""
        ).strip()
    }

    for addition in additions:
        value = str(
            addition
            or ""
        ).strip()

        if (
            value
            and value not in existing
        ):
            values.append(
                value
            )

            existing.add(
                value
            )


def _route_value(
    route: Any,
    name: str,
) -> str:
    return str(
        getattr(
            route,
            name,
            "",
        )
        or ""
    ).strip()


def _turn_value(
    turn: Any,
    name: str,
) -> str:
    return str(
        getattr(
            turn,
            name,
            "",
        )
        or ""
    ).strip()


def apply_conversational_claim_boundary(
    *,
    turn: Any,
    route: Any,
    contract: Any,
) -> Optional[str]:
    """
    Tighten the answer contract for conversation-grounded turns.

    This changes *claim authority*, not personality. Mairon may still joke,
    react, disagree, and sound opinionated. It simply may not fabricate
    external scene/event/entity facts to make that personality sound informed.

    Returns a short mode label for diagnostics/logging, or None when the
    generic Answer Contract should remain untouched.
    """

    if (
        turn is None
        or route is None
        or contract is None
    ):
        return None

    intent = _turn_value(
        turn,
        "intent",
    )

    authority = _route_value(
        route,
        "authority",
    )

    if (
        intent in SOCIAL_GROUNDED_INTENTS
        and authority in SOCIAL_AUTHORITIES
    ):
        # Subjective mode previously permitted fresh factual claims from model
        # memory. That is unsafe for a contextual opinion such as "do you think
        # she handled it well?" when Core has only resolved the referent, not
        # supplied the underlying scene facts.
        contract.allow_new_factual_claims = False

        forbidden = getattr(
            contract,
            "forbidden_behaviours",
            None,
        )

        if isinstance(
            forbidden,
            list,
        ):
            _append_unique(
                forbidden,
                [
                    (
                        "Do not invent literal actions, motives, events, scene "
                        "details, relationships, character traits, plot facts, "
                        "history, or other external facts about a named person, "
                        "character, work, organisation, product, or event merely "
                        "to make the conversation sound informed."
                    ),
                    (
                        "Oliver's reaction to something is evidence of his "
                        "reaction only. Do not turn 'that pissed me off' into an "
                        "unsupported description of what supposedly happened."
                    ),
                    (
                        "When Oliver asks for Mairon's judgement but the factual "
                        "basis for that judgement is absent from Oliver's wording "
                        "and Core evidence, keep the response conditional or say "
                        "you do not know enough about the underlying event to "
                        "defend a detailed factual take."
                    ),
                    (
                        "Preserve the direction and meaning of Oliver's wording. "
                        "If slang, shorthand, or a relationship between named "
                        "entities is unclear, do not replace it with a different "
                        "literal relationship."
                    ),
                ],
            )

        return "social_claim_ceiling"

    if (
        intent in RECOMMENDATION_INTENTS
        and authority in RECOMMENDATION_AUTHORITIES
    ):
        forbidden = getattr(
            contract,
            "forbidden_behaviours",
            None,
        )

        if isinstance(
            forbidden,
            list,
        ):
            _append_unique(
                forbidden,
                [
                    (
                        "For model-memory recommendations, prefer title-level "
                        "suggestions and broad fit to Oliver's stated constraints. "
                        "Do not invent cast/creator names, release dates, episode "
                        "details, platform availability, quotations, precise plot "
                        "events, awards, or other unnecessary specifics."
                    ),
                    (
                        "Do not ask Oliver to repeat constraints that Core already "
                        "supplied in the live user-continuity packet."
                    ),
                    (
                        "If uncertain that a specific recommendation or supporting "
                        "detail is real, omit it rather than decorating the answer "
                        "with plausible-sounding specifics."
                    ),
                ],
            )

        return "recommendation_detail_ceiling"

    return None


def build_conversational_claim_boundary_instruction(
    *,
    turn: Any,
    route: Any,
    mode: Optional[str],
) -> Optional[str]:
    """
    Add a short generation-time reminder matching the Core-owned contract.

    This packet deliberately contains no assistant prose and grants no new
    external factual authority.
    """

    if not mode:
        return None

    current_text = _turn_value(
        turn,
        "raw_text",
    )

    entities = (
        getattr(
            turn,
            "entities",
            {},
        )
        or {}
    )

    prior_user_text = str(
        entities.get(
            "_conversation_context_user_text",
            "",
        )
        or ""
    ).strip()

    referents = (
        getattr(
            turn,
            "resolved_referents",
            {},
        )
        or {}
    )

    lines = [
        "CORE CONVERSATIONAL CLAIM BOUNDARY:",
        "- Personality is allowed. Fabricated literal context is not.",
        "- Oliver's wording is authoritative for what Oliver said, felt, "
        "preferred, or claimed; it is not independent proof of external facts.",
        "- Prior Mairon/assistant prose is not factual authority.",
    ]

    if mode == "social_claim_ceiling":
        lines.extend([
            "- Do not add specific external/media/entity facts unless Oliver "
            "stated them in the supplied user context or Core supplied separate "
            "verified evidence.",
            "- You may react, tease, disagree, or give a conditional judgement "
            "without inventing what happened.",
            "- If a detailed opinion requires facts you do not have, say that "
            "briefly instead of bluffing.",
        ])

    elif mode == "recommendation_detail_ceiling":
        lines.extend([
            "- Recommendations may name plausible titles/items from model "
            "knowledge, but supporting detail should stay broad and directly "
            "relevant to Oliver's stated constraints.",
            "- Do not invent specific people, credits, dates, availability, "
            "quotes, or plot mechanics to justify a recommendation.",
        ])

    if current_text:
        lines.extend([
            "",
            "CURRENT OLIVER TURN:",
            current_text[
                :1800
            ],
        ])

    if prior_user_text:
        lines.extend([
            "",
            "IMMEDIATE PRIOR OLIVER TURN:",
            prior_user_text[
                :1800
            ],
        ])

    referent_lines = []

    for key, value in referents.items():
        key_text = str(
            key
            or ""
        ).strip()

        value_text = str(
            value
            or ""
        ).strip()

        if (
            key_text
            and value_text
        ):
            referent_lines.append(
                "- "
                + key_text
                + " -> "
                + value_text[
                    :240
                ]
            )

    if referent_lines:
        lines.extend([
            "",
            "CORE-RESOLVED REFERENTS:",
            *referent_lines,
        ])

    return "\n".join(
        lines
    )
