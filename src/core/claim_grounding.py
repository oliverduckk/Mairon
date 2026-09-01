import json
import re
from typing import Any, Dict, List, Optional

from core.answer_contract_runtime import (
    coerce_answer_contract_runtime,
    render_answer_contract,
)


def _extract_json_object(
    text: Any,
) -> Optional[Dict[str, Any]]:
    value = str(
        text or ""
    ).strip()

    if not value:
        return None

    try:
        parsed = json.loads(
            value
        )

        if isinstance(
            parsed,
            dict,
        ):
            return parsed

    except Exception:
        pass

    start = value.find(
        "{"
    )

    end = value.rfind(
        "}"
    )

    if (
        start == -1
        or end == -1
        or end <= start
    ):
        return None

    try:
        parsed = json.loads(
            value[
                start:end + 1
            ]
        )

    except Exception:
        return None

    if not isinstance(
        parsed,
        dict,
    ):
        return None

    return parsed


def contract_forbids_new_factual_claims(
    core_answer_contract,
) -> bool:
    """
    Structured policy check.

    No prose parsing occurs here.
    """

    runtime = (
        coerce_answer_contract_runtime(
            core_answer_contract
        )
    )

    if runtime is None:
        return False

    return not (
        runtime.allow_new_factual_claims
    )


def contract_intent(
    core_answer_contract,
) -> Optional[str]:
    """
    Structured intent lookup.

    No prose parsing occurs here.
    """

    runtime = (
        coerce_answer_contract_runtime(
            core_answer_contract
        )
    )

    if runtime is None:
        return None

    value = str(
        runtime.intent
        or ""
    ).strip().lower()

    return (
        value
        or None
    )


def _message_role_and_content(
    message: Any,
):
    if isinstance(
        message,
        dict,
    ):
        return (
            message.get(
                "role"
            ),
            str(
                message.get(
                    "content"
                )
                or ""
            ),
        )

    return (
        getattr(
            message,
            "role",
            None,
        ),
        str(
            getattr(
                message,
                "content",
                "",
            )
            or ""
        ),
    )


def build_recent_user_grounding_context(
    conversation,
    max_user_messages: int = 4,
) -> Optional[str]:
    """
    Build a compact grounding packet from recent USER messages only.

    Prior assistant messages are deliberately excluded. A previous Mairon
    response proves what Mairon said, not that the factual content was true.
    This prevents an earlier hallucination from becoming evidence for a new
    hallucination.
    """

    collected = []

    for message in reversed(
        list(
            conversation or []
        )
    ):
        role, content = (
            _message_role_and_content(
                message
            )
        )

        if role != "user":
            continue

        content = re.sub(
            r"\s+",
            " ",
            content,
        ).strip()

        if not content:
            continue

        collected.append(
            content
        )

        if len(
            collected
        ) >= max(
            1,
            int(
                max_user_messages
            ),
        ):
            break

    if not collected:
        return None

    collected.reverse()

    lines = [
        "RECENT USER-PROVIDED CONTEXT:",
    ]

    for item in collected:
        lines.append(
            "- "
            + item
        )

    return "\n".join(
        lines
    )


def _combined_allowed_grounding_text(
    user_input: str,
    conversation,
    core_answer_contract: Optional[str],
) -> str:
    pieces = [
        str(
            user_input or ""
        ),
        render_answer_contract(
            core_answer_contract
        ),
    ]

    recent_user_context = (
        build_recent_user_grounding_context(
            conversation
        )
    )

    if recent_user_context:
        pieces.append(
            recent_user_context
        )

    return "\n".join(
        pieces
    )


def _normalise_for_grounding(
    text: str,
) -> str:
    value = str(
        text or ""
    ).lower()

    value = re.sub(
        r"[’‘]",
        "'",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def _novel_multiword_named_entities(
    draft: str,
    grounding_text: str,
) -> List[str]:
    """
    Catch obvious introduced proper-noun phrases such as "Great Wall"
    when they never appeared anywhere in the allowed grounding packet.

    This is intentionally conservative: only 2-4 word capitalised spans
    are checked, so ordinary sentence-initial words are ignored.
    """

    candidates = re.findall(
        r"\b([A-Z][A-Za-z0-9'-]+"
        r"(?:\s+[A-Z][A-Za-z0-9'-]+){1,3})\b",
        str(
            draft or ""
        ),
    )

    grounding_lower = str(
        grounding_text or ""
    ).lower()

    ignored = {
        "Fair Enough",
        "Good Lord",
        "Jesus Christ",
        "Core Answer Contract",
    }

    leading_determiners = {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "my",
        "your",
        "our",
        "their",
    }

    novel = []

    for candidate in candidates:
        candidate = candidate.strip()

        if (
            not candidate
            or candidate in ignored
        ):
            continue

        candidate_lower = candidate.lower()

        if candidate_lower in grounding_lower:
            continue

        # Sentence-initial determiners can make ordinary grounded entities
        # look like multi-word proper nouns:
        #
        #   "The XT6s arrived."
        #
        # The regex sees "The XT6s". If the informative remainder ("XT6s")
        # is already present in the grounding packet, this is NOT a novel
        # named entity.
        words = candidate.split()

        if (
            len(words) >= 2
            and words[0].lower()
            in leading_determiners
        ):
            remainder = " ".join(
                words[1:]
            ).strip()

            if (
                remainder
                and remainder.lower()
                in grounding_lower
            ):
                continue

        if candidate not in novel:
            novel.append(
                candidate
            )

    return novel


def _unsupported_current_location_claims(
    draft: str,
    grounding_text: str,
) -> List[str]:
    """
    Catch one especially dangerous relation error:
    treating a destination/purpose as a current location.

    Example:
        Oliver: "I bought XT6s for China."
        Draft:  "They're in China."

    Topic overlap is not entailment.
    """

    draft_text = str(
        draft or ""
    )

    grounding_norm = _normalise_for_grounding(
        grounding_text
    )

    patterns = [
        r"\b(?:is|are|am|be|being|currently|now|they're|you're|we're|it's)"
        r"(?:\s+\w+){0,5}\s+in\s+([A-Z][A-Za-z]+"
        r"(?:\s+[A-Z][A-Za-z]+){0,2})\b",
        r"\b(?:sitting|located|based|staying)\s+in\s+"
        r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b",
    ]

    unsupported = []

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            draft_text,
        ):
            location = (
                match.group(
                    1
                )
                or ""
            ).strip()

            if not location:
                continue

            location_norm = (
                location.lower()
            )

            directly_grounded = any(
                phrase
                in grounding_norm
                for phrase in (
                    f"in {location_norm}",
                    f"at {location_norm}",
                    f"currently in {location_norm}",
                    f"currently at {location_norm}",
                )
            )

            if directly_grounded:
                continue

            description = (
                f"current-location claim involving '{location}' "
                "is not directly supported"
            )

            if description not in unsupported:
                unsupported.append(
                    description
                )

    return unsupported


def _unsupported_travel_transport_claims(
    draft: str,
    grounding_text: str,
) -> List[str]:
    """
    Catch high-confidence itinerary/transport inventions.

    Example:
        Oliver: "My XT6s arrived for my China trip."
        Draft:  "Hope you're ready for serious driving adventures."

    "Driving adventures" is not obvious absurd banter. It is a plausible
    claim about how Oliver will travel, so it requires support.

    This check activates only when the grounding packet itself establishes
    a trip/travel context.
    """

    grounding_norm = _normalise_for_grounding(
        grounding_text
    )

    travel_context_terms = (
        " trip",
        "trip ",
        " travel",
        "travel ",
        " holiday",
        "holiday ",
        " vacation",
        "vacation ",
        " itinerary",
        "itinerary ",
    )

    if not any(
        term in f" {grounding_norm} "
        for term in travel_context_terms
    ):
        return []

    draft_text = str(
        draft
        or ""
    )

    transport_categories = {
        "driving": {
            "grounding_terms": (
                "drive",
                "driving",
                "car",
                "road trip",
                "roadtrip",
            ),
            "draft_patterns": (
                r"\bready\s+for\b.{0,35}\bdriving\b",
                r"\bdriving\s+(?:adventure|adventures|trip|trips|around|through|across)\b",
                r"\b(?:you|we)(?:'ll| will| are going to| are gonna| gonna)?\s+(?:be\s+)?driv(?:e|ing)\b",
                r"\b(?:car|road)\s+trip\b",
            ),
        },
        "flying": {
            "grounding_terms": (
                "flight",
                "flights",
                "fly",
                "flying",
                "plane",
            ),
            "draft_patterns": (
                r"\b(?:you|we)(?:'ll| will| are going to| are gonna| gonna)?\s+(?:fly|be flying)\b",
                r"\b(?:take|taking|catch|catching)\b.{0,20}\b(?:a\s+)?flight\b",
            ),
        },
        "rail": {
            "grounding_terms": (
                "train",
                "trains",
                "rail",
                "railway",
            ),
            "draft_patterns": (
                r"\b(?:you|we)(?:'ll| will| are going to| are gonna| gonna)?\s+(?:take|catch|ride)\b.{0,20}\btrain\b",
                r"\btrain\s+(?:trip|journey|ride|rides)\b",
            ),
        },
        "taxi/rideshare": {
            "grounding_terms": (
                "taxi",
                "taxis",
                "didi",
                "uber",
                "rideshare",
            ),
            "draft_patterns": (
                r"\b(?:take|taking|catch|catching|use|using)\b.{0,20}\b(?:taxi|didi|uber|rideshare)\b",
            ),
        },
    }

    unsupported = []

    for category, rules in (
        transport_categories.items()
    ):
        draft_has_claim = any(
            re.search(
                pattern,
                draft_text,
                flags=re.IGNORECASE,
            )
            for pattern in rules[
                "draft_patterns"
            ]
        )

        if not draft_has_claim:
            continue

        grounding_has_transport = any(
            re.search(
                r"\b"
                + re.escape(
                    term
                )
                + r"\b",
                grounding_norm,
                flags=re.IGNORECASE,
            )
            for term in rules[
                "grounding_terms"
            ]
        )

        if grounding_has_transport:
            continue

        unsupported.append(
            (
                f"travel transport claim involving {category} "
                "is not directly supported"
            )
        )

    return unsupported


def _unsupported_travel_world_claims(
    draft: str,
    grounding_text: str,
) -> List[str]:
    """
    Catch plausible travel-world embellishments that are not supported by
    Oliver's grounding packet.

    This is deliberately narrower than "ban all novel words". Mairon may
    still make obviously absurd jokes. What this blocks are realistic claims
    about weather/climate, traffic, clothing requirements, venues, activities,
    and other itinerary-like details that a normal reader could mistake for
    actual knowledge.

    Exact live regression:
        Oliver:
            "My XT6s have arrived for my China trip in November!"

        Unsupported:
            "China's infamous traffic"
            "sweating through your jacket in November"
            "your bargaining skills at the market"
    """

    grounding_norm = _normalise_for_grounding(
        grounding_text
    )

    padded_grounding = (
        " "
        + grounding_norm
        + " "
    )

    travel_context_terms = (
        " trip ",
        " travel ",
        " holiday ",
        " vacation ",
        " itinerary ",
    )

    if not any(
        term in padded_grounding
        for term in travel_context_terms
    ):
        return []

    draft_text = str(
        draft
        or ""
    )

    categories = {
        "weather/climate": {
            "grounding_terms": (
                "weather",
                "forecast",
                "rain",
                "raining",
                "rainy",
                "snow",
                "snowing",
                "snowy",
                "hot",
                "heat",
                "warm",
                "warmer",
                "cold",
                "cool",
                "cooler",
                "chilly",
                "freezing",
                "humid",
                "humidity",
                "temperature",
                "temperatures",
                "sweat",
                "sweating",
            ),
            "draft_patterns": (
                r"\b(?:weather|forecast|climate|temperature|temperatures)\b",
                r"\b(?:rain|raining|rainy|drizzle|snow|snowing|snowy)\b",
                r"\b(?:hot|heat|warm|warmer|cold|cool|cooler|chilly|freezing|humid|humidity)\b",
                r"\b(?:sweat|sweating|sweaty)\b",
            ),
        },
        "weather-related clothing": {
            "grounding_terms": (
                "jacket",
                "coat",
                "shell",
                "umbrella",
                "raincoat",
                "poncho",
            ),
            "draft_patterns": (
                r"\b(?:jacket|coat|shell|umbrella|raincoat|poncho)\b",
            ),
        },
        "traffic/road conditions": {
            "grounding_terms": (
                "traffic",
                "congestion",
                "traffic jam",
                "traffic jams",
                "roads",
                "road conditions",
            ),
            "draft_patterns": (
                r"\b(?:traffic|congestion)\b",
                r"\btraffic\s+jams?\b",
                r"\broad\s+conditions?\b",
            ),
        },
        "market/shopping activity": {
            "grounding_terms": (
                "market",
                "markets",
                "shopping",
                "shop",
                "shops",
                "bargain",
                "bargaining",
            ),
            "draft_patterns": (
                r"\b(?:market|markets|shopping|shops?)\b",
                r"\b(?:bargain|bargaining)\b",
            ),
        },
        "tourist activity/venue": {
            "grounding_terms": (
                "museum",
                "museums",
                "temple",
                "temples",
                "attraction",
                "attractions",
                "nightlife",
                "beach",
                "beaches",
                "hike",
                "hiking",
                "mountain",
                "mountains",
                "tour",
                "tours",
                "sightseeing",
            ),
            "draft_patterns": (
                r"\b(?:museum|museums|temple|temples|attraction|attractions)\b",
                r"\b(?:nightlife|beach|beaches|hike|hiking|mountain|mountains)\b",
                r"\b(?:tour|tours|sightseeing)\b",
            ),
        },
    }

    unsupported = []

    for category, rules in (
        categories.items()
    ):
        draft_has_detail = any(
            re.search(
                pattern,
                draft_text,
                flags=re.IGNORECASE,
            )
            for pattern in rules[
                "draft_patterns"
            ]
        )

        if not draft_has_detail:
            continue

        grounding_has_detail = any(
            re.search(
                r"\b"
                + re.escape(
                    term
                )
                + r"\b",
                grounding_norm,
                flags=re.IGNORECASE,
            )
            for term in rules[
                "grounding_terms"
            ]
        )

        if grounding_has_detail:
            continue

        unsupported.append(
            (
                f"travel-world detail involving {category} "
                "is not directly supported"
            )
        )

    return unsupported


def find_deterministic_grounding_violations(
    user_input: str,
    draft: str,
    core_answer_contract: Optional[str],
    conversation=None,
) -> List[str]:
    """
    Cheap high-confidence checks before the semantic verifier.

    These do not attempt to understand every factual claim. They target
    failure classes where deterministic evidence is stronger than asking
    the same LLM to judge itself.
    """

    grounding_text = (
        _combined_allowed_grounding_text(
            user_input=user_input,
            conversation=conversation,
            core_answer_contract=(
                core_answer_contract
            ),
        )
    )

    violations = []

    for entity in (
        _novel_multiword_named_entities(
            draft=draft,
            grounding_text=grounding_text,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                f"introduced named entity '{entity}' "
                "that is absent from the allowed grounding packet"
            )
        )

    for description in (
        _unsupported_current_location_claims(
            draft=draft,
            grounding_text=grounding_text,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                + description
            )
        )

    for description in (
        _unsupported_travel_transport_claims(
            draft=draft,
            grounding_text=grounding_text,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                + description
            )
        )

    for description in (
        _unsupported_travel_world_claims(
            draft=draft,
            grounding_text=grounding_text,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                + description
            )
        )

    return violations


def should_verify_core_grounding(
    core_answer_contract: Optional[str],
) -> bool:
    """
    Decide whether a generated direct-conversation draft needs semantic
    grounding verification.

    Simple acknowledgements are already constrained by deterministic
    structural rules and do not need an extra model call.

    Declarative shares are the first high-value target because Qwen tends
    to embellish them with product/location/media facts that Oliver did not
    actually supply.
    """

    if not contract_forbids_new_factual_claims(
        core_answer_contract
    ):
        return False

    intent = contract_intent(
        core_answer_contract
    )

    if intent in {
        "acknowledge",
    }:
        return False

    return True


def verify_core_grounded_draft(
    client,
    model: str,
    user_input: str,
    draft: str,
    core_answer_contract: Optional[str],
    conversation=None,
) -> List[str]:
    """
    Isolated semantic verifier for Core-restricted conversational turns.

    Allowed factual grounding:
    - Oliver's CURRENT message;
    - recent prior USER messages;
    - the current Core Answer Contract, including resolved referents,
      required claims, and verified evidence.

    Explicitly NOT authoritative:
    - model training memory;
    - prior assistant/Mairon claims;
    - plausibility;
    - stereotypical assumptions.

    Subjective banter is allowed when it is clearly non-literal and does not
    smuggle in a factual premise.
    """

    if not should_verify_core_grounding(
        core_answer_contract
    ):
        return []

    deterministic_violations = (
        find_deterministic_grounding_violations(
            user_input=user_input,
            draft=draft,
            core_answer_contract=(
                core_answer_contract
            ),
            conversation=conversation,
        )
    )

    if deterministic_violations:
        return deterministic_violations

    recent_user_context = (
        build_recent_user_grounding_context(
            conversation
        )
    )

    system_text = (
        "You are Mairon Core's INTERNAL claim-grounding verifier. "
        "You are not speaking to Oliver.\n\n"
        "Your only job is to decide whether factual assertions in a proposed "
        "Mairon draft are supported by the allowed grounding packet.\n\n"
        "ALLOWED FACTUAL GROUNDING:\n"
        "1. Oliver's current message.\n"
        "2. Recent PRIOR USER messages supplied below.\n"
        "3. The current CORE ANSWER CONTRACT, including resolved references, "
        "required claims, and verified evidence.\n\n"
        "NOT ALLOWED AS FACTUAL GROUNDING:\n"
        "- your own training memory;\n"
        "- common knowledge that is absent from the packet;\n"
        "- prior Mairon/assistant statements;\n"
        "- likely assumptions;\n"
        "- stereotypes;\n"
        "- facts that merely sound plausible.\n\n"
        "IMPORTANT — FACTS VS BANTER:\n"
        "- Grounding applies to statements a reasonable reader could interpret as "
        "literal claims about reality.\n"
        "- Clearly absurd, impossible, anthropomorphic, sarcastic, teasing, or "
        "hyperbolic jokes are NOT factual claims and do NOT require evidence.\n"
        "- Do NOT reject a joke merely because its literal wording is false. The "
        "whole point of obvious non-literal humour is that it is not asserting the "
        "literal proposition.\n"
        "- Examples that are NON-LITERAL and should be ALLOWED: "
        "'The shoes will need their own passport', "
        "'Hope they're not plotting a mutiny', "
        "'You'll end up living in those things', "
        "'They've claimed permanent residency on your feet', "
        "'Your socks should start drafting their obituary'.\n"
        "- A joke is NOT automatically exempt merely because it is phrased casually. "
        "If it smuggles in a plausible real-world premise, that premise still needs "
        "grounding.\n"
        "- Examples that remain FACTUAL and must be grounded: "
        "'XT6s are waterproof', "
        "'XT6s last 500 km', "
        "'they are currently in China', "
        "'you will visit the Great Wall', "
        "'they were made in China', "
        "'China has infamous traffic', "
        "'you will be sweating in a jacket in November', "
        "'your bargaining skills at the market'. "
        "A sentence can be sarcastic while still smuggling in a plausible "
        "factual premise; those premises still require grounding.\n"
        "- When uncertain, ask: would a normal reader reasonably believe Mairon is "
        "telling Oliver something true about the product, location, itinerary, "
        "history, media canon, technical behaviour, or an external event? If yes, "
        "treat it as factual. If it is obviously impossible or ridiculous on its "
        "face, treat it as non-literal banter.\n"
        "- A product property, location assumption, itinerary assumption, "
        "technical specification, historical claim, media/canon claim, or "
        "claim about what happened outside the supplied packet IS factual.\n"
        "- Paraphrasing or logically trivial restatement of Oliver's supplied "
        "facts is allowed.\n"
        "- ENTAILMENT matters. Mere topic/word overlap is NOT support.\n"
        "- 'for China' does NOT support 'currently in China'.\n"
        "- 'arrived today' does NOT identify the place it arrived unless Oliver says where.\n"
        "- 'for a China trip' does NOT support a specific attraction or itinerary such as "
        "the Great Wall.\n"
        "- A product name does NOT support durability, cushioning, waterproofing, materials, "
        "performance, or other product properties unless those properties appear in the packet.\n"
        "- If a claim is true in the real world but absent from the allowed "
        "packet, it is STILL unsupported for this turn.\n"
        "- Never rescue a claim using your own knowledge.\n\n"
        "First classify each meaningful proposition as either LITERAL_FACT or "
        "CLEARLY_NON_LITERAL_BANTER. Do not perform factual grounding on "
        "CLEARLY_NON_LITERAL_BANTER. For EACH LITERAL_FACT, require a directly "
        "supporting quote or a trivial logical restatement of a supplied quote. "
        "Relation changes such as for->in, planned->completed, may->did, or "
        "future->current are unsupported.\n\n"
        "Return JSON ONLY:\n"
        "{\n"
        '  "supported": true,\n'
        '  "unsupported_claims": [],\n'
        '  "claim_checks": [\n'
        '    {"claim": "...", "supported": true, "evidence_quote": "...", "reason": "..."}\n'
        "  ]\n"
        "}\n\n"
        "If any factual assertion is unsupported, set supported=false and "
        "list short descriptions of those claims."
    )

    messages = [
        {
            "role": "system",
            "content": system_text,
        },
        {
            "role": "system",
            "content": (
                "CORE ANSWER CONTRACT:\n"
                + render_answer_contract(
                    core_answer_contract
                )
            ),
        },
    ]

    if recent_user_context:
        messages.append({
            "role": "system",
            "content": recent_user_context,
        })

    messages.extend([
        {
            "role": "user",
            "content": (
                "OLIVER'S CURRENT MESSAGE:\n"
                + str(
                    user_input
                )
            ),
        },
        {
            "role": "user",
            "content": (
                "PROPOSED MAIRON DRAFT:\n"
                + str(
                    draft
                )
            ),
        },
    ])

    result = client.chat(
        model=model,
        messages=messages,
        options={
            "temperature": 0,
        },
    )

    parsed = _extract_json_object(
        result.message.content
    )

    if not parsed:
        return [
            "Core claim-grounding verifier could not validate the draft"
        ]

    if parsed.get(
        "supported"
    ) is True:
        return []

    claims = parsed.get(
        "unsupported_claims"
    )

    if not isinstance(
        claims,
        list,
    ):
        claims = []

    cleaned = []

    for claim in claims[
        :8
    ]:
        value = re.sub(
            r"\s+",
            " ",
            str(
                claim
            ).strip(),
        )

        if value:
            cleaned.append(
                value
            )

    if cleaned:
        return [
            (
                "unsupported Core-grounded claim: "
                + claim
            )
            for claim in cleaned
        ]

    return [
        "Core-restricted response contained unsupported factual claims"
    ]


def build_core_grounding_retry_instruction(
    violations: List[str],
) -> Optional[str]:
    relevant = [
        violation
        for violation in violations
        if (
            "unsupported Core-grounded claim"
            in violation
            or "claim-grounding verifier"
            in violation
            or "Core-restricted response contained unsupported"
            in violation
        )
    ]

    if not relevant:
        return None

    details = "\n".join(
        "- "
        + item
        for item in relevant
    )

    return (
        "CORE CLAIM-GROUNDING REPAIR:\n"
        "The previous draft introduced factual statements that were not "
        "grounded in Oliver's current message, recent USER-provided context, "
        "or Core's verified evidence.\n"
        f"{details}\n\n"
        "Rewrite the response with those factual claims REMOVED. Do not "
        "replace them with different external facts. Keep the response "
        "natural; subjective reaction and clearly non-literal banter are fine "
        "when they do not rely on an unsupported factual premise. A short "
        "response is better than invented detail."
    )


def build_core_grounding_fallback(
    core_answer_contract: Optional[str],
    user_input: Optional[str] = None,
) -> str:
    """
    Fail closed after repeated semantic-grounding failures.

    Phase 6.4:
    Keep factual content near-zero, but avoid sounding like a broken
    customer-service bot when the user's turn is obviously social.

    Existing callers that do not provide user_input retain the old fallback
    for backward compatibility with the regression suite.
    """

    intent = contract_intent(
        core_answer_contract
    )

    if intent == "share_context":
        if user_input is None:
            return (
                "Fair enough. That makes sense."
            )

        text = str(
            user_input
            or ""
        ).lower()

        arrival_markers = (
            "arrived",
            "has arrived",
            "have arrived",
            "is here",
            "are here",
            "turned up",
            "showed up",
            "came today",
            "came in",
        )

        excitement_markers = (
            "let's go",
            "lets go",
            "fuck yeah",
            "hell yeah",
            "finally",
            "!!!",
        )

        has_arrival = any(
            marker in text
            for marker in arrival_markers
        )

        has_excitement = (
            any(
                marker in text
                for marker in excitement_markers
            )
            or "!" in text
        )

        if (
            has_arrival
            and has_excitement
        ):
            return (
                "Hell yes. About fucking time."
            )

        if has_arrival:
            return (
                "Nice. About time."
            )

        if has_excitement:
            return (
                "There we fucking go."
            )

        return (
            "Right, got you."
        )

    if intent == "acknowledge":
        return (
            "Anytime."
        )

    return (
        "Got it."
    )
