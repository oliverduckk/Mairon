import json
import os
import re
from typing import Any, Dict, List, Optional

from core.answer_contract_runtime import (
    coerce_answer_contract_runtime,
    render_answer_contract,
)

from core.source_lock import (
    build_draft_source_lock_diagnostics,
    build_source_lock_instruction,
    find_structural_source_lock_violations,
    recommended_source_lock_prior_window,
)


def _generation_debug_enabled():
    value = str(
        os.getenv(
            "MAIRON_DEBUG_GENERATION",
            "",
        )
        or ""
    ).strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


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


def _unsupported_mairon_perception_claims(
    draft: str,
) -> List[str]:
    """
    Reject unsupported claims that Mairon directly perceived Oliver or his
    physical surroundings.

    Ordinary text conversation does not provide visual/audio perception.
    This is an embodiment/capability boundary, not a topic-specific rule.
    """

    text = str(
        draft
        or ""
    )

    patterns = (
        r"\bi(?:'ve| have)\s+seen\s+(?:it|that|this|your|the)\b",
        r"\bi\s+saw\s+(?:it|that|this|your|the)\b",
        r"\bi\s+can\s+see\s+(?:your|the|that|this)\b",
        r"\bi(?:'ve| have)\s+watched\s+you\b",
        r"\bi\s+watched\s+you\b",
        r"\bi(?:'ve| have)\s+heard\s+you\b",
        r"\bi\s+heard\s+you\b",
        r"\bi\s+can\s+hear\s+you\b",
        r"\bi(?:'ve| have)\s+noticed\s+(?:your|the|that|this)\b",
        r"\bi\s+noticed\s+(?:your|the|that|this)\b",
    )

    violations = []

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            violations.append(
                (
                    "Mairon claimed direct physical perception "
                    "without sensor/image evidence"
                )
            )
            break

    return violations


USER_PHYSICAL_ACTION_FAMILIES = {
    "rush": ("rush", "rushing", "rushed"),
    "sit": ("sit", "sits", "sat", "sitting"),
    "stand": ("stand", "stands", "stood", "standing"),
    "walk": ("walk", "walks", "walked", "walking"),
    "run": ("run", "runs", "ran", "running"),
    "lie": ("lie", "lies", "lay", "lying", "laying"),
    "sleep": ("sleep", "sleeps", "slept", "sleeping"),
    "wake": ("wake", "wakes", "woke", "waking"),
    "eat": ("eat", "eats", "ate", "eating"),
    "drink": ("drink", "drinks", "drank", "drinking"),
    "hold": ("hold", "holds", "held", "holding"),
    "wear": ("wear", "wears", "wore", "wearing", "dressed"),
    "drive": ("drive", "drives", "drove", "driving"),
    "leave": ("leave", "leaves", "left", "leaving"),
}


def _grounding_mentions_action_family(
    grounding_text: str,
    variants,
) -> bool:
    value = _normalise_for_grounding(
        grounding_text
    )

    return any(
        re.search(
            r"\b" + re.escape(variant) + r"\b",
            value,
            flags=re.IGNORECASE,
        )
        for variant in variants
    )


def _unsupported_user_physical_action_claims(
    draft: str,
    grounding_text: str,
) -> List[str]:
    """
    Reject high-confidence claims about Oliver's physical actions/state when
    the supplied grounding packet never established that activity.

    This is an embodiment/source-authority boundary, not a domain rule.
    Examples caught from the Desk benchmark:
      - "while you were rushing out"
      - "before you've even sat down"

    We intentionally limit this to concrete observable actions. Abstract
    reactions such as "you're blaming yourself" remain semantic/personality
    territory so Mairon does not become sterile.
    """

    value = _normalise_apostrophes_for_physical_checks(
        draft
    )

    violations = []

    for family, variants in USER_PHYSICAL_ACTION_FAMILIES.items():
        variant_pattern = "|".join(
            re.escape(item)
            for item in variants
        )

        pattern = (
            r"\byou(?:\s+(?:are|were|have|had|did|will|would|could|might|"
            r"still|already|just|even|never|not))*\s+(?:"
            + variant_pattern
            + r")\b"
        )

        if not re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        ):
            continue

        if _grounding_mentions_action_family(
            grounding_text=grounding_text,
            variants=variants,
        ):
            continue

        violations.append(
            "unsupported Oliver physical-action/state claim involving "
            + family
        )

    return violations


def _normalise_apostrophes_for_physical_checks(
    text: str,
) -> str:
    value = str(
        text
        or ""
    ).replace(
        "’",
        "'",
    ).replace(
        "‘",
        "'",
    )

    replacements = (
        (r"\byou're\b", "you are"),
        (r"\byou've\b", "you have"),
        (r"\byou'd\b", "you had"),
        (r"\byou'll\b", "you will"),
    )

    for pattern, replacement in replacements:
        value = re.sub(
            pattern,
            replacement,
            value,
            flags=re.IGNORECASE,
        )

    return value


def _unsupported_mairon_recordkeeping_claims(
    draft: str,
) -> List[str]:
    """
    Model prose is not authoritative about whether Core stored, logged, wrote,
    remembered, or persisted something. Claims about Mairon's own concrete
    record-keeping history require explicit Core evidence.

    This catches the live false recall tail:
        "I didn't write that down in a ledger somewhere."
    while leaving ordinary metaphor/personification alone.
    """

    value = str(
        draft
        or ""
    ).replace(
        "’",
        "'",
    )

    patterns = (
        r"\bI\s+(?:didn't|did not|never)\s+(?:write|save|record|store|log|persist|remember)\b",
        r"\bI\s+(?:wrote|saved|recorded|stored|logged|persisted|remembered)\b",
        r"\bI(?:'ve| have)\s+(?:written|saved|recorded|stored|logged|persisted|remembered)\b",
    )

    for pattern in patterns:
        if re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        ):
            return [
                "Mairon claimed concrete record-keeping/history without Core evidence"
            ]

    return []


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

    # Phase 6.8.9: deterministic structural source locks run before the
    # broad semantic verifier. These preserve entity ownership and
    # actor/target direction without asking Qwen to approve its own rewrite.
    source_lock_window = (
        recommended_source_lock_prior_window(
            user_input=user_input,
            intent=contract_intent(
                core_answer_contract
            ),
        )
    )

    violations.extend(
        find_structural_source_lock_violations(
            user_input=user_input,
            draft=draft,
            conversation=conversation,
            max_prior_user_messages=source_lock_window,
        )
    )

    for description in (
        _unsupported_user_physical_action_claims(
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
        _unsupported_mairon_recordkeeping_claims(
            draft=draft,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                + description
            )
        )

    for description in (
        _unsupported_mairon_perception_claims(
            draft=draft,
        )
    ):
        violations.append(
            (
                "unsupported Core-grounded claim: "
                + description
            )
        )

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


def _core_verifier_think_setting(
    model: str,
):
    """
    Semantic grounding is a constrained classification task, not a reasoning
    task. Thinking-capable local models should not spend long hidden traces
    deciding whether a short draft is supported.

    Qwen3/Qwen3.5 and DeepSeek accept think=False.
    GPT-OSS uses effort levels instead, so request "low".
    Unknown/non-thinking models receive no explicit think argument.
    """

    model_name = str(
        model
        or ""
    ).strip().lower()

    if model_name.startswith(
        "gpt-oss"
    ):
        return "low"

    if (
        model_name.startswith(
            "qwen3"
        )
        or model_name.startswith(
            "deepseek"
        )
    ):
        return False

    return None


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

    intent = contract_intent(
        core_answer_contract
    )

    # Ordinary social grounding stays intentionally small. Explicit live
    # conversation recall needs a wider user-only window so a corrected fact
    # does not fall out of evidence merely because several later turns occurred.
    grounding_user_window = (
        12
        if intent == "conversation_recall"
        else 4
    )

    recent_user_context = (
        build_recent_user_grounding_context(
            conversation,
            max_user_messages=grounding_user_window,
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
        "SOURCE-FIDELITY RULES:\n"
        "- Preserve the exact concrete entity Oliver supplied. Do not silently substitute "
        "a related object, device, person, place, or category. If Oliver says his XM6s are "
        "at 40%, that does NOT support saying his phone is at 40%.\n"
        "- Preserve actor, target, possession, direction, and temporal relations. "
        "If Oliver says 'I debug you every night', Oliver is the debugger and Mairon is "
        "the thing being debugged. It does NOT support Mairon claiming to debug Oliver's "
        "code.\n"
        "- Pronouns must resolve to the supplied entity rather than a plausible substitute.\n"
        "- Do not turn 'forgot to charge them before work' into 'abandoned them overnight' "
        "unless Oliver explicitly supplied the overnight relation.\n"
        "- A draft can be topically relevant yet still be unsupported because it swapped "
        "an entity or reversed a relation.\n\n"
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
        "- Pay special attention to IMPLIED SCENE PREMISES. An absurd action can still "
        "depend on an unsupported ordinary object or user state. If Oliver mentions a "
        "desk, 'the desk is plotting a coup' can be obvious banter about the supplied "
        "desk. But 'the coffee cups are plotting a rebellion' additionally asserts that "
        "coffee cups are present, so it is unsupported unless Oliver mentioned them. "
        "Likewise, 'your caffeine-fueled rage' asserts caffeine use and is unsupported "
        "unless Oliver supplied that fact. 'I've seen your desk' claims Mairon physically "
        "observed it and is unsupported without explicit sensor/image evidence.\n"
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
        "Decompose each meaningful proposition BEFORE deciding what is banter. "
        "A clearly non-literal predicate/action does NOT exempt the concrete premise "
        "that makes the joke possible. Ground any plausible entity-existence, possession, "
        "scene, habit, substance, bodily-state, location, or event premise separately. "
        "Only the obviously impossible/non-literal predicate itself is exempt from factual "
        "grounding. For EACH concrete/literal premise, require a directly supporting quote "
        "or a trivial logical restatement of a supplied quote. "
        "Examples: 'the desk is plotting revenge' is allowed when the desk was supplied "
        "(desk exists = supported; plotting revenge = non-literal). "
        "'the dust bunnies are plotting a coup' is unsupported unless dust/dust bunnies "
        "were supplied (their existence is a plausible scene premise even though plotting "
        "a coup is absurd). 'the coffee mugs formed a union' likewise requires coffee mugs "
        "to have been supplied. 'the XM6s are furious' is allowed when XM6s were supplied "
        "(XM6s exist = supported; furious = personification). "
        "Relation changes such as for->in, planned->completed, may->did, or "
        "future->current are unsupported.\n\n"
        "Also judge RELEVANCE to OLIVER'S CURRENT MESSAGE. A reply is relevant "
        "when it directly reacts to, answers, paraphrases, or naturally jokes about "
        "the current message. Exact word overlap is NOT required: synonyms and "
        "ordinary paraphrases count. Generic self-description, generic hostility, "
        "talk about merely processing input, or unrelated banter is not relevant. "
        "Do not use older assistant prose to rescue relevance.\n\n"
        "Return compact JSON ONLY, with no explanation and no extra fields:\n"
        '{"supported":true,"relevant":true,"source_faithful":true,"unsupported_claims":[]}\n\n'
        "Set source_faithful=false if the draft substitutes a supplied entity, reverses "
        "actor/target/ownership/direction/time relations, or invents a concrete relation "
        "that is not entailed by the packet. "
        "If any factual assertion is unsupported, set supported=false and "
        "list only short descriptions of those claims. If the draft does not "
        "actually respond to the current message, set relevant=false."
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

    source_lock_text = build_source_lock_instruction(
        user_input=user_input,
        conversation=conversation,
        intent=intent,
        max_prior_user_messages=(
            recommended_source_lock_prior_window(
                user_input=user_input,
                intent=intent,
            )
        ),
    )

    if source_lock_text:
        messages.append({
            "role": "system",
            "content": source_lock_text,
        })

    messages.append({
        "role": "system",
        "content": build_draft_source_lock_diagnostics(
            draft
        ),
    })

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

    verifier_kwargs = {
        "model": model,
        "messages": messages,
        "options": {
            "temperature": 0,
            "num_predict": 160,
            "num_ctx": 8192,
        },
    }

    verifier_think_setting = (
        _core_verifier_think_setting(
            model
        )
    )

    if verifier_think_setting is not None:
        verifier_kwargs[
            "think"
        ] = verifier_think_setting

    result = client.chat(
        **verifier_kwargs
    )

    verifier_content = str(
        result.message.content
        or ""
    )

    parsed = _extract_json_object(
        verifier_content
    )

    if _generation_debug_enabled():
        print(
            "[Debug] Grounding verifier raw output: "
            + repr(
                verifier_content
            )
        )

        thinking_text = str(
            getattr(
                result.message,
                "thinking",
                "",
            )
            or ""
        ).strip()

        if thinking_text:
            print(
                "[Debug] Grounding verifier thinking output: "
                + repr(
                    thinking_text
                )
            )

    if not parsed:
        return [
            "Core claim-grounding verifier could not validate the draft"
        ]

    violations = []

    if parsed.get(
        "source_faithful"
    ) is False:
        violations.append(
            (
                "Core draft changed a supplied entity, actor, target, "
                "ownership, direction, or time relation"
            )
        )

    if parsed.get(
        "relevant"
    ) is False:
        violations.append(
            (
                "Core social micro-act is not semantically relevant "
                "to Oliver's current message"
            )
        )

    if parsed.get(
        "supported"
    ) is True:
        return violations

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
        violations.extend([
            (
                "unsupported Core-grounded claim: "
                + claim
            )
            for claim in cleaned
        ])

        return violations

    violations.append(
        "Core-restricted response contained unsupported factual claims"
    )

    return violations



def should_verify_factual_focus_fidelity(
    core_answer_contract: Optional[str],
) -> bool:
    """
    Factual questions may legitimately use model/public-world knowledge, so the
    ordinary source-locked grounding verifier must not police the answer itself.

    They still need a smaller fidelity check for unsupported claims about
    Oliver, Mairon, conversation history, prior actions, or relationship state.
    """

    return (
        contract_intent(
            core_answer_contract
        )
        == "factual_question"
    )


def verify_factual_focus_fidelity(
    client,
    model: str,
    user_input: str,
    draft: str,
    core_answer_contract: Optional[str],
    conversation=None,
) -> List[str]:
    """
    Verify only PERSONAL / CONVERSATIONAL source fidelity on a factual answer.

    Public-world facts that answer the current question are explicitly outside
    this verifier's scope. This lets Mairon say "Ottawa" from model knowledge
    while preventing invented tails such as "I got lost reading a book about it
    last time."
    """

    if not should_verify_factual_focus_fidelity(
        core_answer_contract
    ):
        return []

    recent_user_context = (
        build_recent_user_grounding_context(
            conversation,
            max_user_messages=4,
        )
    )

    system_text = (
        "You are Mairon Core's INTERNAL factual-answer source-fidelity verifier. "
        "You are not speaking to Oliver.\n\n"
        "IMPORTANT SCOPE:\n"
        "- Do NOT fact-check the public-world answer to Oliver's current factual question.\n"
        "- The answer may legitimately come from the local model's general knowledge.\n"
        "- Check ONLY claims about Oliver, Mairon, their conversation/history, prior actions, "
        "personal habits, remembered events, observations, research supposedly performed, "
        "or user-specific entities/relations.\n\n"
        "SOURCE-FIDELITY RULES:\n"
        "- Do not invent prior Mairon experiences, actions, reading, research, observations, "
        "mistakes, or earlier conversations.\n"
        "- Words such as 'again', 'this time', 'last time', or callbacks are acceptable only "
        "when the supplied USER-authored context actually establishes the referenced history.\n"
        "- Preserve actor and target relations exactly. 'Oliver debugs Mairon' does not support "
        "'Mairon debugs Oliver's code'.\n"
        "- Preserve concrete entity identity. XM6s are not a phone simply because both are devices.\n"
        "- Obvious impossible self-personification that does not imply a real prior event can be "
        "treated as banter, but a plausible claimed history still requires support.\n\n"
        "EXAMPLES:\n"
        "- User asks 'what is the capital of Canada?' Draft 'Ottawa.' => faithful.\n"
        "- Same question, draft 'Ottawa. Not Toronto.' => this verifier does not judge the public "
        "fact/comparison; faithful unless it adds personal/history claims.\n"
        "- Same question, draft 'Ottawa. I didn't get lost reading a book about it this time.' "
        "=> NOT faithful unless supplied context proves Mairon previously read/got lost in such a book.\n\n"
        "Return compact JSON ONLY:\n"
        '{"faithful":true,"violations":[]}'
    )

    user_packet = (
        "CURRENT USER MESSAGE:\n"
        + str(
            user_input
            or ""
        ).strip()
        + "\n\nRECENT PRIOR USER CONTEXT:\n"
        + (
            recent_user_context
            or "(none)"
        )
        + "\n\nPROPOSED MAIRON DRAFT:\n"
        + str(
            draft
            or ""
        ).strip()
    )

    source_lock_text = build_source_lock_instruction(
        user_input=user_input,
        conversation=conversation,
        intent="factual_question",
        max_prior_user_messages=(
            recommended_source_lock_prior_window(
                user_input=user_input,
                intent="factual_question",
            )
        ),
    )

    verifier_messages = [
        {
            "role": "system",
            "content": system_text,
        },
    ]

    if source_lock_text:
        verifier_messages.append({
            "role": "system",
            "content": source_lock_text,
        })

    verifier_messages.append({
        "role": "system",
        "content": build_draft_source_lock_diagnostics(
            draft
        ),
    })

    verifier_messages.append({
        "role": "user",
        "content": user_packet,
    })

    verifier_kwargs = {
        "model": model,
        "messages": verifier_messages,
        "options": {
            "temperature": 0,
            "num_predict": 96,
            "num_ctx": 8192,
        },
    }

    verifier_think_setting = (
        _core_verifier_think_setting(
            model
        )
    )

    if verifier_think_setting is not None:
        verifier_kwargs[
            "think"
        ] = verifier_think_setting

    result = client.chat(
        **verifier_kwargs
    )

    verifier_content = str(
        result.message.content
        or ""
    )

    if _generation_debug_enabled():
        print(
            "[Debug] Factual-focus fidelity verifier raw output: "
            + repr(
                verifier_content
            )
        )

    parsed = _extract_json_object(
        verifier_content
    )

    if not parsed:
        return [
            "Core factual-focus fidelity verifier could not validate the draft"
        ]

    if parsed.get(
        "faithful"
    ) is True:
        return []

    raw_violations = parsed.get(
        "violations"
    )

    if not isinstance(
        raw_violations,
        list,
    ):
        raw_violations = []

    cleaned = []

    for violation in raw_violations[
        :6
    ]:
        value = re.sub(
            r"\s+",
            " ",
            str(
                violation
            ).strip(),
        )

        if value:
            cleaned.append(
                value
            )

    if cleaned:
        return [
            (
                "factual-focus source-fidelity violation: "
                + violation
            )
            for violation in cleaned
        ]

    return [
        (
            "factual answer added unsupported Oliver/Mairon "
            "history or source-fidelity claims"
        )
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
            or "factual-focus source-fidelity violation"
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

        if text.lstrip().startswith(
            "at least "
        ):
            return (
                "At least that one's sorted."
            )

        return (
            "Right, got you."
        )

    if intent == "self_correction":
        return (
            "Got it — correction noted."
        )

    if intent == "casual_conversation":
        return (
            "Fair."
        )

    if intent == "conversation_recall":
        return (
            "I can't reliably recover that from the live conversation."
        )

    if intent == "acknowledge":
        return (
            "Anytime."
        )

    return (
        "Got it."
    )
