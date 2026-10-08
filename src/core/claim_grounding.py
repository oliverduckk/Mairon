import ast
import builtins
import json
import math
import os
import re
from typing import Any, Dict, List, Optional

from core.missing_inputs import extract_missing_inputs, resolve_missing_inputs

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


def contract_epistemic_mode(
    core_answer_contract,
) -> Optional[str]:
    runtime = (
        coerce_answer_contract_runtime(
            core_answer_contract
        )
    )

    if runtime is None:
        return None

    value = str(
        runtime.epistemic_mode
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


def _user_explicitly_requests_public_attribution(
    user_input: str,
) -> bool:
    """
    Return True when authorship/creation/credit is itself Oliver's question.

    In that case the attribution is the requested public-world fact and may
    legitimately come from the factual lane/model knowledge. The incidental
    attribution guard below is for *extra* credits injected into otherwise
    subjective/conversational answers.
    """

    value = str(
        user_input
        or ""
    )

    patterns = (
        r"\bwho\s+(?:wrote|created|directed|designed|developed|illustrated|"
        r"authored|composed|produced|made)\b",
        r"\bwho\s+is\s+(?:the\s+)?(?:author|creator|director|writer|artist|"
        r"illustrator|mangaka|developer|designer|composer|producer)\b",
        r"\b(?:author|creator|director|writer|artist|illustrator|mangaka|"
        r"developer|designer|composer|producer)\s+of\b",
        r"\b(?:written|created|directed|designed|developed|illustrated|"
        r"authored|composed|produced|made)\s+by\s+who(?:m)?\b",
    )

    return any(
        re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


def _extract_incidental_public_attributions(
    draft: str,
):
    """
    Extract HIGH-CONFIDENCE named creator/credit relations from a draft.

    This is intentionally not a general entity relation parser. It targets
    attribution shapes where a hallucinated name is especially damaging:

        "Murakami Genshaku's art..."
        "written by Kentaro Miura"
        "Takehiko Inoue, the creator..."
        "Berserk (post-Masamune era)..."

    Ordinary opinions and title names are not attribution claims.
    """

    value = str(
        draft
        or ""
    ).replace(
        "’",
        "'",
    )

    # Requiring at least two capitalised name tokens keeps this conservative
    # and avoids treating ordinary sentence-initial nouns as people.
    name_pattern = (
        r"[A-Z][A-Za-z0-9'-]+"
        r"(?:\s+[A-Z][A-Za-z0-9'-]+){1,3}"
    )

    # A one-token capitalised label is allowed only for the very narrow
    # creative-era shape below. This catches model confabulations such as
    # "Berserk (post-Masamune era)" without treating arbitrary title words as
    # people or credits.
    era_name_pattern = (
        r"[A-Z][A-Za-z0-9'-]{2,}"
        r"(?:\s+[A-Z][A-Za-z0-9'-]+){0,2}"
    )

    patterns = (
        (
            "named creative-era/history credit",
            re.compile(
                rf"\b(?:[Pp]ost|[Pp]re)-(?P<name>{era_name_pattern})\s+"
                r"(?:era|period|run)\b"
            ),
        ),
        (
            "possessive creative credit",
            re.compile(
                rf"\b(?P<name>{name_pattern})'s\s+"
                r"(?:art|artwork|writing|direction|directing|design|music|"
                r"score|illustrations?|story|animation|cinematography|work)\b"
            ),
        ),
        (
            "single-token possessive creative credit",
            re.compile(
                r"\b(?P<name>[A-Z][A-Za-z0-9'-]{2,})'s\s+"
                r"(?:art|artwork|writing|direction|directing|design|music|"
                r"score|illustrations?|story|animation|cinematography|work)\b"
            ),
        ),
        (
            "explicit byline/credit",
            re.compile(
                r"\b(?:written|created|directed|designed|developed|illustrated|"
                r"authored|composed|produced|made)\s+by\s+"
                rf"(?P<name>{name_pattern})\b",
                flags=re.IGNORECASE,
            ),
        ),
        (
            "named role credit",
            re.compile(
                rf"\b(?P<name>{name_pattern})\s*,\s*(?:the\s+)?"
                r"(?:author|creator|director|writer|artist|illustrator|mangaka|"
                r"developer|designer|composer|producer)\b",
                flags=re.IGNORECASE,
            ),
        ),
    )

    found = []

    for relation_type, pattern in patterns:
        for match in pattern.finditer(
            value
        ):
            name = re.sub(
                r"\s+",
                " ",
                str(
                    match.group(
                        "name"
                    )
                    or ""
                ).strip(),
            )

            if not name:
                continue

            item = (
                name,
                relation_type,
                match.group(
                    0
                ).strip(),
            )

            if item not in found:
                found.append(
                    item
                )

    return found


def find_incidental_public_attribution_violations(
    user_input: str,
    draft: str,
    core_answer_contract: Optional[str],
    conversation=None,
) -> List[str]:
    """
    Block unsupported real-world creator/credit attributions that are *extra*
    to Oliver's request.

    The guard is deliberately universal across generation lanes because an
    opinion/recommendation answer may legitimately invent subjective rankings
    while still being unsafe to invent a concrete author/director/creator.

    If Oliver explicitly asks for that attribution ("Who wrote X?"), the
    normal factual lane remains responsible for answering it and this guard
    gets out of the way.
    """

    if _user_explicitly_requests_public_attribution(
        user_input
    ):
        return []

    grounding_text = (
        _combined_allowed_grounding_text(
            user_input=user_input,
            conversation=conversation,
            core_answer_contract=(
                core_answer_contract
            ),
        )
    )

    grounding_lower = str(
        grounding_text
        or ""
    ).lower()

    violations = []

    for name, relation_type, quote in (
        _extract_incidental_public_attributions(
            draft
        )
    ):
        if name.lower() in grounding_lower:
            continue

        violations.append(
            "unsupported Core-grounded claim: incidental public attribution "
            f"introduced unverified credit name '{name}' via {relation_type}: "
            f"{quote}"
        )

    return violations


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



MEDIA_MODALITY_RULES = (
    (
        "read",
        (
            r"\bmanga\b",
            r"\bmanhwa\b",
            r"\bmanhua\b",
            r"\bcomics?\b",
            r"\bbooks?\b",
            r"\bnovels?\b",
            r"\blight novels?\b",
            r"\bweb novels?\b",
            r"\bchapters?\b",
        ),
    ),
    (
        "watch",
        (
            r"\banime\b",
            r"\bmovies?\b",
            r"\bfilms?\b",
            r"\btv shows?\b",
            r"\bshows?\b",
            r"\bepisodes?\b",
            r"\bvideos?\b",
        ),
    ),
    (
        "listen",
        (
            r"\bmusic\b",
            r"\bsongs?\b",
            r"\balbums?\b",
            r"\bpodcasts?\b",
            r"\baudiobooks?\b",
        ),
    ),
    (
        "play",
        (
            r"\bvideo games?\b",
            r"\bvideogames?\b",
            r"\bgames?\b",
        ),
    ),
)


def _media_modalities_in_text(
    text: str,
) -> List[str]:
    """
    Return explicit media-consumption modalities named in text.

    This is deliberately semantic-category based rather than title based:
    Core never needs to know that "Berserk" is manga. It only needs a clear
    conversational frame such as "manga", "movie", "podcast", or "game".
    """

    value = str(
        text
        or ""
    )

    found = []

    for action, patterns in MEDIA_MODALITY_RULES:
        if any(
            re.search(
                pattern,
                value,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        ):
            found.append(
                action
            )

    return found


def infer_recent_media_consumption_action(
    user_input: str,
    conversation=None,
) -> Optional[str]:
    """
    Infer one unambiguous consumption action from the nearest explicit
    conversational medium.

    Priority:
    1. current Oliver message;
    2. nearest recent conversation turn.

    If a nearer message explicitly mixes media (for example "manga vs anime"),
    return None instead of guessing.
    """

    candidates = [
        str(
            user_input
            or ""
        )
    ]

    if conversation:
        recent = list(
            conversation
        )[-6:]

        for message in reversed(
            recent
        ):
            content = str(
                (
                    message
                    or {}
                ).get(
                    "content",
                    "",
                )
                or ""
            ).strip()

            if content:
                candidates.append(
                    content
                )

    for text in candidates:
        modalities = (
            _media_modalities_in_text(
                text
            )
        )

        if len(
            modalities
        ) == 1:
            return modalities[
                0
            ]

        if len(
            modalities
        ) > 1:
            # A nearer mixed-media turn makes the frame ambiguous.
            return None

    return None


def build_mairon_agency_modality_instruction(
    user_input: str,
    conversation=None,
) -> str:
    """
    Universal direct-conversation identity/capability boundary.

    Qwen may express interest or hypothetical preference, but it must not
    fabricate autonomous actions that Mairon will perform between turns.
    When Core can infer a media modality, preserve it unless Oliver explicitly
    switches medium.
    """

    lines = [
        "CORE AGENCY + MODALITY BOUNDARY:",
        "- You do not independently act between turns unless Core has actually "
        "executed or scheduled a workflow that supports that action.",
        "- Do not invent concrete background activity before, between, or after "
        "Oliver's turns. Do not claim you were processing, researching, checking, "
        "working on, or otherwise doing something off-turn before Oliver messaged "
        "or interrupted you unless Core supplied that workflow state.",
        "- Do not claim or promise that you will later watch, read, listen to, "
        "play, research, browse, check, visit, buy, contact, install, or otherwise "
        "do something autonomously after this reply.",
        "- You may express hypothetical interest without claiming future action: "
        "for example, 'that would be my next pick' is fine; 'I'll watch it tonight' "
        "is not.",
        "- Preserve the medium/action established by the conversation. Do not "
        "silently turn reading into watching, watching into reading, listening "
        "into watching, or playing into another medium.",
        "- If Oliver explicitly changes medium (for example asks about an anime "
        "adaptation while discussing manga), follow the explicit new medium.",
    ]

    expected_action = (
        infer_recent_media_consumption_action(
            user_input=user_input,
            conversation=conversation,
        )
    )

    if expected_action:
        lines.append(
            "- Core currently infers the conversational media-consumption action "
            f"as '{expected_action}'. Preserve that action unless Oliver explicitly "
            "switches medium."
        )

    return "\n".join(
        lines
    )


MAIRON_OFF_TURN_ACTIVITY = re.compile(
    # Past/background activity explicitly located before/between user turns.
    r"\bI\s+was\s+(?:\w+\s+){0,5}?\w+ing\b[^.!?\n]{0,120}"
    r"\b(?:before\s+you\s+(?:asked|messaged|texted|interrupted|showed\s+up|"
    r"came\s+back|said\s+anything)|while\s+you\s+were\s+(?:gone|away|offline)|"
    r"between\s+(?:turns|messages|conversations))\b"
    r"|"
    # Claimed continuous activity across an off-turn time span.
    r"\bI(?:'ve| have)\s+been\s+(?:\w+\s+){0,4}?\w+ing\b[^.!?\n]{0,100}"
    r"\b(?:since\s+(?:your\s+last\s+(?:message|turn)|we\s+last\s+(?:spoke|talked)|"
    r"you\s+(?:left|went\s+away))|all\s+(?:day|morning|afternoon|evening|night)|"
    # Duration phrasing is deliberately quantity-agnostic: "for 2 hours",
    # "for two hours", "for the last couple of hours", "for about 30 minutes".
    r"for\s+[^.!?\n]{0,48}\b(?:hours?|minutes?|days?))\b"
    r"|"
    # "Get back to <gerund>" asserts an activity was already underway.
    r"\bI(?:'ll| will| can| should| need\s+to| have\s+to| want\s+to)?\s*"
    r"get\s+back\s+to\s+\w+ing\b",
    flags=re.IGNORECASE,
)


MAIRON_FUTURE_AUTONOMOUS_ACTION = re.compile(
    r"\bI(?:'ll| will)\s+(?:probably\s+|maybe\s+|definitely\s+)?"
    r"(?:make\s+sure\s+to\s+)?"
    r"(?:watch|read|listen\s+to|play|research|check|look\s+up|browse|search|"
    r"visit|buy|order|call|email|message|contact|download|install)\b"
    r"|\bI(?:'m| am)\s+going\s+to\s+"
    r"(?:watch|read|listen\s+to|play|research|check|look\s+up|browse|search|"
    r"visit|buy|order|call|email|message|contact|download|install)\b"
    r"|\bI(?:'m| am)\s+gonna\s+"
    r"(?:watch|read|listen\s+to|play|research|check|look\s+up|browse|search|"
    r"visit|buy|order|call|email|message|contact|download|install)\b"
    r"|\bI\s+plan\s+to\s+"
    r"(?:watch|read|listen\s+to|play|research|check|look\s+up|browse|search|"
    r"visit|buy|order|call|email|message|contact|download|install)\b",
    flags=re.IGNORECASE,
)


FIRST_PERSON_MEDIA_ACTION = re.compile(
    r"\bI(?:(?:'ll| will|'d| would| might| could| should| want to| plan to|"
    r"'m going to| am going to)\s+)?"
    r"(?P<action>read|watch|listen\s+to|play)\b",
    flags=re.IGNORECASE,
)


def find_mairon_agency_modality_violations(
    user_input: str,
    draft: str,
    conversation=None,
) -> List[str]:
    """
    Deterministic acceptance-stage boundary for Mairon's own agency.

    This is intentionally NOT a catalogue of domains or titles. It checks:
    - unsupported concrete background/off-turn activity;
    - unsupported first-person autonomous future actions;
    - silent media-consumption modality drift when the conversational medium
      is unambiguous.

    Explicit medium switches inside the draft are allowed.
    """

    text = str(
        draft
        or ""
    )

    violations = []

    if MAIRON_OFF_TURN_ACTIVITY.search(
        text
    ):
        violations.append(
            "Mairon claimed unsupported autonomous off-turn activity"
        )

    if MAIRON_FUTURE_AUTONOMOUS_ACTION.search(
        text
    ):
        violations.append(
            "Mairon claimed an unsupported autonomous future action"
        )

    expected_action = (
        infer_recent_media_consumption_action(
            user_input=user_input,
            conversation=conversation,
        )
    )

    if not expected_action:
        return violations

    sentences = re.split(
        r"(?<=[.!?])\s+|\n+",
        text,
    )

    for sentence in sentences:
        match = (
            FIRST_PERSON_MEDIA_ACTION.search(
                sentence
            )
        )

        if not match:
            continue

        action = (
            match.group(
                "action"
            )
            .lower()
            .replace(
                "listen to",
                "listen",
            )
        )

        if action == expected_action:
            continue

        explicit_sentence_modalities = (
            _media_modalities_in_text(
                sentence
            )
        )

        # An explicit alternate medium is a deliberate switch/comparison,
        # not silent drift: "I'd watch the anime adaptation" is allowed even
        # when the broader conversation is about manga.
        if action in explicit_sentence_modalities:
            continue

        violations.append(
            "media modality drift: conversational context implies "
            f"'{expected_action}' but Mairon used '{action}' without an explicit "
            "medium switch"
        )
        break

    return list(
        dict.fromkeys(
            violations
        )
    )


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
        r"\bi(?:'m| am)\s+(?:just\s+)?(?:here\s+)?(?:watching|looking\s+at|staring\s+at)\s+(?:your|the|that|this)\s+(?:clock|timer|screen|monitor|cursor|room|window|door|desk|table)\b",
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
    "stare": ("stare", "stares", "stared", "staring"),
    "look": ("look", "looks", "looked", "looking"),
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


USER_PHYSICAL_OBJECT_TERMS = (
    "chair", "couch", "sofa", "bed", "desk", "screen", "monitor",
    "window", "door", "table", "floor", "wall", "walls", "room",
    "clock", "timer", "cursor",
    "shirt", "clothes", "clothing", "face", "eyes", "food", "drink",
)


def _unsupported_user_physical_object_claims(
    *,
    draft: str,
    grounding_text: str,
) -> List[str]:
    """Reject concrete scene objects attached to Oliver when he never supplied them.

    This is intentionally conservative: it only checks a compact set of ordinary
    physical scene/body objects and only when the draft presents them as part of
    Oliver's immediate situation rather than as a clearly hypothetical example.
    """
    text = _normalise_for_grounding(draft)
    grounding = _normalise_for_grounding(grounding_text)
    violations: List[str] = []

    for term in USER_PHYSICAL_OBJECT_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", grounding, flags=re.IGNORECASE):
            continue

        pattern = (
            r"\b(?:your|the|that|this)\s+" + re.escape(term) + r"s?\b"
            r"|\b" + re.escape(term) + r"s?\b[^.!?]{0,55}\byou(?:\b|'re|'ve|'ll|'d)"
        )
        if not re.search(pattern, text, flags=re.IGNORECASE):
            continue

        # Explicit hypotheticals/examples are not observations about Oliver's scene.
        unit_candidates = [
            unit.strip()
            for unit in re.split(r"(?<=[.!?])\s+", text)
            if re.search(r"\b" + re.escape(term) + r"s?\b", unit, flags=re.IGNORECASE)
        ]
        if unit_candidates and all(
            re.search(r"\b(?:if|imagine|suppose|hypothetically|for example|could be|might be)\b", unit, flags=re.IGNORECASE)
            for unit in unit_candidates
        ):
            continue

        violations.append(
            "unsupported Oliver immediate physical-scene object claim involving " + term
        )
        break

    return violations


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

        direct_match = re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        )

        # Participial scene descriptions can put the invented action before
        # the explicit second-person subject: "Sitting there staring at
        # nothing, you're ...". Treat those as the same observable-state
        # claim without broadening to generic imperative "look" phrasing.
        reversed_scene_match = False
        cross_sentence_scene_match = False
        ing_variants = [
            item
            for item in variants
            if item.endswith("ing")
        ]
        if ing_variants:
            reversed_scene_match = bool(re.search(
                r"\b(?:"
                + "|".join(re.escape(item) for item in ing_variants)
                + r")\b[^.!?]{0,80}\byou(?:\b|'re|'ve|'ll|'d)",
                value,
                flags=re.IGNORECASE,
            ))
            cross_sentence_scene_match = bool(re.search(
                r"\b(?:"
                + "|".join(re.escape(item) for item in ing_variants)
                + r")\b[^.!?]{0,80}[?!]\s*you(?:\b|'re|'ve|'ll|'d)",
                value,
                flags=re.IGNORECASE,
            ))

        indirect_scene_match = False
        sentence_initial_scene_match = False
        if ing_variants:
            indirect_scene_match = bool(re.search(
                r"\byou\b[^.!?]{0,65}\b(?:stop|stopped|keep|kept|start|started|continue|continued)\s+(?:"
                + "|".join(re.escape(item) for item in ing_variants)
                + r")\b",
                value,
                flags=re.IGNORECASE,
            ))

            # Conversational fragments can omit the explicit second-person
            # subject while still asserting an observed physical state:
            # "Sitting there staring at nothing? ..." is still a claim about
            # Oliver. Keep this narrow so abstract phrases such as
            # "looking at it another way" are not swept in.
            if family in {"stare", "look", "watch"}:
                sentence_initial_scene_match = bool(re.search(
                    r"(?:^|[.!?]\s+)(?:sitting\s+there\s+|standing\s+there\s+)?(?:"
                    + "|".join(re.escape(item) for item in ing_variants)
                    + r")\s+(?:at|out|around)\b",
                    value,
                    flags=re.IGNORECASE,
                ))

        if not (
            direct_match
            or reversed_scene_match
            or cross_sentence_scene_match
            or indirect_scene_match
            or sentence_initial_scene_match
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


def _unsupported_relationship_history_claims(
    *,
    draft: str,
    grounding_text: str,
) -> List[str]:
    """Reject plausible shared-history claims that Oliver never established."""
    text = str(draft or "").replace("’", "'")
    grounding = _normalise_for_grounding(grounding_text)

    patterns = (
        r"\bi(?:'ve| have)\s+(?:known|been\s+(?:helping|processing|dealing\s+with|putting\s+up\s+with))\s+you\b[^.!?]{0,100}\b(?:since|for)\b",
        r"\bi(?:'ve| have)\s+been\b[^.!?]{0,120}\bsince\s+day\s+one\b",
        r"\bi(?:'ve| have)\s+been\b[^.!?]{0,120}\bsince\s+(?:the\s+)?(?:moment|time|day)\b[^.!?]{0,90}\byou\b",
        r"\bi(?:'ve| have)\s+been\b[^.!?]{0,100}\bsince\s+before\s+you\b",
        r"\bsince\s+before\s+you\s+(?:had|got|were|became|started)\b",
        r"\bwe(?:'ve| have)\s+been\b[^.!?]{0,90}\bfor\s+(?:years?|months?|ages?)\b",
        r"\byou(?:'re| are)\s+(?:treating|testing|using|debugging|programming|training|"
        r"poking|prodding|messing\s+with)\s+(?:me\b[^.!?]{0,100})?\bagain\b",
        r"\byou\s+(?:keep|kept)\s+(?:treating|testing|using|debugging|programming|training|"
        r"poking|prodding|messing\s+with)\s+me\b",
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        phrase = _normalise_for_grounding(match.group(0))
        if phrase and phrase in grounding:
            continue
        if "since" in phrase and re.search(r"\bsince\b", grounding, flags=re.IGNORECASE):
            continue
        return ["Mairon invented unsupported relationship/conversation history"]

    return []



def find_unknown_media_opinion_overreach_violations(
    user_input: str,
    draft: str,
    conversation=None,
) -> List[str]:
    """Reject invented work-specific takes after Mairon admits it lacks familiarity.

    An explicit first-hand-knowledge disclaimer is good epistemic behaviour, but
    it cannot be followed by concrete claims about pacing, world-building,
    characters, prose, plot quality, or Oliver's attachment to the work. If
    Mairon lacks enough knowledge for a real take, it should say that cleanly
    rather than replace fake familiarity with fake speculation.
    """
    user = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
    response = re.sub(r"\s+", " ", str(draft or "").strip()).lower()

    if not re.search(
        r"\bwhat\s+do\s+you\s+(?:actually\s+|really\s+)?think\s+(?:of|about)\b|"
        r"\bwhat(?:'s| is)\s+your\s+(?:actual\s+)?(?:take|opinion|view)\b",
        user,
        flags=re.IGNORECASE,
    ):
        return []

    recent_user_context = str(
        build_recent_user_grounding_context(
            conversation,
            max_user_messages=4,
        )
        or ""
    ).lower()
    allowed_user_grounding = user + "\n" + recent_user_context

    knowledge_qualifier = bool(re.search(
        r"\b(?:from|based\s+on)\s+what\s+i\s+know\b|"
        r"\bmy\s+knowledge\s+(?:of|about)\b|"
        r"\bi\s+(?:am|'m)\s+not\s+(?:deeply\s+)?familiar\b|"
        r"\bi\s+can\s+only\s+speak\s+(?:broadly|generally)\b|"
        r"\bi\s+don['’]?t\s+know\s+enough\b|"
        r"\bi\s+(?:haven['’]?t|have\s+not|didn['’]?t|did\s+not)\s+"
        r"(?:actually\s+|personally\s+)?"
        r"(?:read|watch|see|play|finish|consume|experience)\b|"
        r"\bi\s+won['’]?t\s+pretend\s+i(?:['’]?ve|\s+have)\s+"
        r"(?:read|watched|played|finished)\b",
        response,
        flags=re.IGNORECASE,
    ))

    media_dimension_patterns = {
        "pacing": r"\bpacing\b",
        "worldbuilding": r"\bworld[- ]?building\b",
        "characters": r"\b(?:character\s+(?:development|writing|work)|characters?|npcs?)\b",
        "plot": r"\bplot\b",
        "prose": r"\b(?:prose|writing\s+style)\b",
        "themes": r"\bthemes?\b",
        "dialogue": r"\bdialogue\b",
        "exposition": r"\bexposition\b",
        "ending": r"\bending\b",
        "combat": r"\b(?:combat|fights?|battles?)\b",
        "romance": r"\bromance\b",
    }
    novel_dimensions = [
        label
        for label, pattern in media_dimension_patterns.items()
        if (
            re.search(pattern, response, flags=re.IGNORECASE)
            and not re.search(pattern, allowed_user_grounding, flags=re.IGNORECASE)
        )
    ]
    concrete_familiarity_shape = bool(re.search(
        r"\b(?:the\s+author|the\s+writer)\b[^.!?]{0,90}\b(?:spends?|uses?|keeps?|returns?|switches?)\b|"
        r"\b\d+\s+chapters?\b|"
        r"\b(?:minor|side)\s+(?:characters?|npcs?)\b|"
        r"\b(?:we(?:'re| are)|you(?:'re| are))\s+back\s+to\b",
        response,
        flags=re.IGNORECASE,
    ))
    if (
        not knowledge_qualifier
        and (
            len(set(novel_dimensions)) >= 3
            or concrete_familiarity_shape
        )
    ):
        return [
            "unknown-media opinion presented detailed work-specific familiarity without a knowledge qualifier or user-supplied grounding"
        ]

    admits_limited_familiarity = bool(re.search(
        r"\bi\s+(?:haven['’]?t|have\s+not|didn['’]?t|did\s+not)\s+"
        r"(?:actually\s+|personally\s+)?"
        r"(?:read|watch|see|play|finish|consume|experience)\b|"
        r"\bi\s+don['’]?t\s+know\s+enough\b|"
        r"\bi\s+can['’]?t\s+give\s+(?:you\s+)?(?:a\s+)?real\s+take\b",
        response,
        flags=re.IGNORECASE,
    ))
    if not admits_limited_familiarity:
        return []

    violations: List[str] = []

    work_specific_guess = re.search(
        r"\b(?:pacing|world[- ]?building|characters?|character\s+work|plot|prose|"
        r"writing|story|themes?|dialogue|ending|combat|romance)\b"
        r"[^.!?]{0,80}\b(?:sucks?|bad|good|great|weak|strong|dense|boring|slow|"
        r"amazing|excellent|poor|messy|bloated|thin|deep|shallow|impressive|"
        r"trying\s+too\s+hard|works?|doesn['’]?t\s+work)\b|"
        r"\b(?:sucks?|bad|good|great|weak|strong|dense|boring|slow|amazing|excellent|"
        r"poor|messy|bloated|thin|deep|shallow)\b[^.!?]{0,80}"
        r"\b(?:pacing|world[- ]?building|characters?|plot|prose|writing|story|themes?)\b",
        response,
        flags=re.IGNORECASE,
    )
    if work_specific_guess:
        violations.append(
            "unknown-media opinion admitted insufficient familiarity but then invented work-specific evaluative details"
        )

    # A first-hand-knowledge disclaimer does not license model-memory guesses
    # about the work immediately afterwards. If Mairon says it has not consumed
    # the work, any title-specific property still needs user grounding or
    # researched evidence.
    admitted_but_specific = False
    if admits_limited_familiarity:
        ungrounded_dimension_claim = any(
            re.search(
                pattern,
                response,
                flags=re.IGNORECASE,
            )
            and not re.search(
                pattern,
                allowed_user_grounding,
                flags=re.IGNORECASE,
            )
            for pattern in media_dimension_patterns.values()
        )
        ungrounded_scale_or_cast = bool(re.search(
            r"\b(?:sheer\s+)?volume\b|"
            r"\b(?:very\s+)?long[- ](?:running|form)\b|"
            r"\bprotagonists?\b[^.!?]{0,90}\b(?:inevitably|always|often|usually|tend(?:s)?\s+to|make|makes|do|does)\b",
            response,
            flags=re.IGNORECASE,
        )) and not bool(re.search(
            r"\b(?:sheer\s+)?volume\b|"
            r"\b(?:very\s+)?long[- ](?:running|form)\b|"
            r"\bprotagonists?\b",
            allowed_user_grounding,
            flags=re.IGNORECASE,
        ))

        admitted_but_specific = bool(
            ungrounded_dimension_claim
            or ungrounded_scale_or_cast
        )

    if admitted_but_specific:
        violations.append(
            "unknown-media opinion admitted insufficient familiarity but still asserted ungrounded work-specific properties"
        )

    if re.search(
        r"\byou(?:'re| are)\s+(?:clearly\s+)?(?:obsessed|a\s+fan|into\s+it|hooked)\b|"
        r"\byou\s+(?:obviously|clearly)\s+(?:love|like|adore)\b",
        response,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\bi\s+(?:love|like|adore|am\s+obsessed|am\s+into)\b",
        user,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "unknown-media opinion invented Oliver's preference/attachment to the work"
        )

    return list(dict.fromkeys(violations))


def _unsupported_personal_history_year_claims(
    user_input: str,
    draft: str,
    conversation=None,
) -> List[str]:
    """Block invented exact years for Oliver's personal history in social turns.

    Year evidence comes from actual USER messages, never old assistant prose
    or generated Answer Contract metadata. Only high-confidence past/personal
    constructions are caught; generic dates and clearly fantastic banter are
    deliberately outside this conservative guard.
    """
    user_context = (
        str(user_input or "") + "\n"
        + str(build_recent_user_grounding_context(conversation) or "")
    )
    supplied_years = set(re.findall(r"\b(?:19|20)\d{2}\b", user_context))
    draft_text = str(draft or "").replace("’", "'")
    unsupported = []
    year_pattern = re.compile(
        r"\b(?:since|back\s+in|from)\s+((?:19|20)\d{2})\b", re.I
    )
    personal_pattern = re.compile(
        r"\b(?:you|your|yours|you've|you'd|you're|oliver)\b", re.I
    )
    for match in year_pattern.finditer(draft_text):
        year = match.group(1)
        if year in supplied_years:
            continue
        # This exact personal-history assertion must refer to Oliver or
        # something he possesses, not an incidental historical example.
        nearby = draft_text[max(0, match.start() - 100):match.end()]
        if not personal_pattern.search(nearby):
            continue
        unsupported.append(
            "unsupported exact-year claim about Oliver's personal history: " + year
        )
    return list(dict.fromkeys(unsupported))


def _unsupported_new_scene_piles(
    user_input: str,
    draft: str,
    conversation=None,
) -> List[str]:
    """Catch concrete clutter that a social joke invents out of thin air.

    Only a narrow, physically plausible construction is blocked. Metaphors
    about digital debris, rebellion or a desk having an ego remain available.
    This check reads USER statements only; previous Mairon jokes are not proof
    that papers, clothes, dishes, parcels, etc. are in Oliver's surroundings.
    """
    source = (
        str(user_input or "") + "\n"
        + str(build_recent_user_grounding_context(conversation) or "")
    ).lower()
    result = []
    pattern = re.compile(
        r"\b(?:next|another|new|inevitable)\b[^.!?]{0,40}?"
        r"\b(?:pile|stack)\s+of\s+"
        r"(?P<object>papers?|clothes?|dishes?|receipts?|bills?|"
        r"boxes?|parcels?|cans?|cups?|laundry)\b",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(str(draft or "")):
        noun = match.group("object").lower()
        canonical = noun[:-1] if noun.endswith("s") and noun != "dishes" else noun
        variants = {noun, canonical, canonical + "s"}
        if noun == "dishes":
            variants.add("dish")
        if any(re.search(r"\b" + re.escape(word) + r"\b", source) for word in variants):
            continue
        result.append("introduced an unsupported physical pile/stack of " + noun)
    return list(dict.fromkeys(result))



def find_question_echo_violations(
    user_input: str,
    draft: str,
) -> List[str]:
    """Reject a response that merely hands Oliver's question back to him.

    This is a response-adequacy check, not a semantic fact checker. It is
    intentionally conservative: the proposed answer must itself be a question
    and be almost entirely copied from the current user message.
    """

    user = re.sub(
        r"[^a-z0-9]+",
        " ",
        str(user_input or "").lower(),
    ).strip()
    answer_raw = str(draft or "").strip()
    answer = re.sub(
        r"[^a-z0-9]+",
        " ",
        answer_raw.lower(),
    ).strip()

    if (
        not user
        or not answer
        or not answer_raw.endswith("?")
        or len(answer) < 24
    ):
        return []

    if answer in user:
        return [
            "response merely echoed Oliver's question instead of answering it"
        ]

    answer_tokens = answer.split()
    user_tokens = set(user.split())

    if len(answer_tokens) < 6:
        return []

    overlap = sum(
        1
        for token in answer_tokens
        if token in user_tokens
    ) / len(answer_tokens)

    if overlap >= 0.9:
        return [
            "response mostly echoed Oliver's question instead of answering it"
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

    if contract_intent(core_answer_contract) in {
        "share_context", "casual_conversation", "acknowledge",
    }:
        violations.extend(
            "unsupported Core-grounded claim: " + item
            for item in _unsupported_personal_history_year_claims(
                user_input, draft, conversation
            )
        )
        violations.extend(
            "unsupported Core-grounded claim: " + item
            for item in _unsupported_new_scene_piles(user_input, draft, conversation)
        )

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
        _unsupported_user_physical_object_claims(
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
        _unsupported_relationship_history_claims(
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


def find_user_diagnostic_overclaim_violations(
    user_input: str,
    draft: str,
    core_answer_contract: Optional[str],
    conversation=None,
) -> List[str]:
    """Reject confident claims about Oliver's unmeasured diagnostic setup.

    Stable technical knowledge may explain what a measurement *suggests*, but it
    cannot manufacture user-specific bands, backhaul state, access points,
    materials or topology. This validator is deliberately narrow and only fires
    when the USER-authored packet is clearly diagnostic/troubleshooting-shaped.
    """
    if contract_intent(core_answer_contract) != "factual_question":
        return []

    if contract_epistemic_mode(core_answer_contract) not in {
        "stable_model_knowledge",
        "user_context_reasoning",
        "public_source_verified",
    }:
        return []

    current_user = str(user_input or "").lower()
    source = (
        current_user
        + "\n"
        + str(build_recent_user_grounding_context(conversation, max_user_messages=4) or "")
    ).lower()

    if not re.search(
        r"\b(?:mbps|gbps|ping|latency|speed\s*test|signal|wi[- ]?fi|wireless|mesh|"
        r"router|node|backhaul|flicker|refresh\s+rate|vrr|measured|tested|reading)\b",
        source,
        flags=re.IGNORECASE,
    ):
        return []

    text = re.sub(r"\s+", " ", str(draft or "").strip()).lower()
    violations: List[str] = []

    # When Oliver asks what to *test first*, preserve diagnostic information
    # instead of immediately mutating configuration that has not been measured.
    # A first step should normally isolate a variable (same device near/far,
    # association/RSSI, wired-vs-wireless path) before forcing a band/channel.
    asks_first_test = bool(re.search(
        r"\b(?:what|which)\b[^?]{0,50}\b(?:test|check|try)\b[^?]{0,25}\bfirst\b|"
        r"\bfirst\b[^?]{0,25}\b(?:test|check|thing)\b",
        current_user,
        flags=re.IGNORECASE,
    ))
    if asks_first_test and not re.search(
        r"\b(?:2\.4|5|6)\s*ghz\b|\bchannel(?:\s+width)?\b|\bband\b",
        source,
        flags=re.IGNORECASE,
    ):
        # Before an isolating test, a wired-fast / wireless-slow comparison
        # narrows the problem domain but does not prove a single Wi-Fi root
        # cause. Reject definitive diagnoses such as "that's a classic range
        # issue" so Core can use its calibrated same-device isolation fallback.
        if re.search(
            r"\b(?:that(?:'s| is)|this\s+is|it(?:'s| is))\s+"
            r"(?:(?:a\s+)?classic\s+|definitely\s+|clearly\s+|obviously\s+)?"
            r"(?:a\s+)?(?:wi[- ]?fi\s+)?(?:range|signal|coverage|backhaul|interference|roaming)\s+"
            r"(?:issue|problem|fault)\b|"
            r"\b(?:definitely|clearly|obviously)\b[^.!?]{0,60}"
            r"\b(?:range|signal|coverage|backhaul|interference|roaming)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "diagnostic first-test answer asserted a single unmeasured Wi-Fi root cause before isolating the variable"
            )

        if re.search(
            r"\b(?:force|forcing|switch|switching|set|setting|change|changing|lock|locking)\b[^.!?]{0,70}"
            r"(?:\b(?:2\.4|5|6)\s*ghz\b|\bchannel(?:\s+width)?\b|\bband\b)",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "diagnostic first-test answer changed an unmeasured radio configuration instead of isolating a variable"
            )

        # For the common wired-fast / wireless-slow location comparison, the
        # cleanest first isolation is the same wireless device near the source
        # versus in the problem location. Merely checking an assumed radio band
        # first leaves device-vs-location-vs-path confounded.
        if (
            re.search(r"\bwired\s+[a-z][a-z0-9_-]{2,30}\b", source)
            and re.search(r"\bphone\b", source)
            and re.search(r"\b(?:upstairs|downstairs|room|area|location)\b", source)
        ):
            band_check = re.search(
                r"\b(?:check|see|verify|confirm|look)\b[^.!?]{0,160}"
                r"\b(?:2\.4|5|6)\s*ghz\b|"
                r"\b(?:check|see|verify|confirm|look)\b[^.!?]{0,160}\b(?:band|channel)\b|"
                r"\b(?:check|see|verify|confirm)\b[^.!?]{0,160}"
                r"\b(?:phone|device|adapter)\b[^.!?]{0,120}"
                r"\b(?:capable|capability|band|channel)\b",
                text,
                flags=re.IGNORECASE,
            )
            same_device_near_source = re.search(
                r"\b(?:same\s+)?phone\b[^.!?]{0,100}"
                r"\b(?:near|next\s+to|beside|closer\s+to|by)\b[^.!?]{0,70}"
                r"\b(?:router|node|wi[- ]?fi\s+source|access\s+point|source)\b|"
                r"\b(?:router|node|wi[- ]?fi\s+source|access\s+point|source)\b[^.!?]{0,70}"
                r"\b(?:same\s+)?phone\b",
                text,
                flags=re.IGNORECASE,
            )
            if not same_device_near_source:
                violations.append(
                    "diagnostic first-test answer did not perform the clean same-device near-source versus problem-location isolation"
                )

            if band_check and (
                not same_device_near_source
                or band_check.start() < same_device_near_source.start()
            ):
                violations.append(
                    "diagnostic first-test answer prioritized an unmeasured band hypothesis over same-device near-vs-problem-location isolation"
                )

    # A user-described wired endpoint cannot simultaneously be treated as if
    # Core had observed its Wi-Fi channel/band configuration.
    wired_entities = {
        match.group("entity")
        for match in re.finditer(
            r"\bwired\s+(?P<entity>[a-z][a-z0-9_-]{2,30})\b",
            source,
            flags=re.IGNORECASE,
        )
    }
    for entity in sorted(wired_entities):
        if re.search(
            rf"\b(?:your\s+)?{re.escape(entity)}\b[^.!?]{{0,70}}"
            r"\b(?:on|using|at)\s+(?:2\.4|5|6|20|40|80|160)\s*(?:mhz|ghz)?\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "diagnostic answer assigned an unobserved Wi-Fi band/channel to a user-described wired device"
            )
            break

    # Also catch comparisons such as "the same 5GHz band as the console".
    # A wired endpoint has no Wi-Fi band to compare against. Allow an explicit
    # correction ("the wired console is not on a Wi-Fi band") but reject any
    # positive band/channel association in the same sentence.
    for entity in sorted(wired_entities):
        entity_units = [
            unit.strip()
            for unit in re.split(r"(?<=[.!?])\s+", text)
            if re.search(rf"\b{re.escape(entity)}\b", unit, flags=re.IGNORECASE)
        ]
        for unit in entity_units:
            has_radio_term = bool(re.search(
                r"\b(?:2\.4|5|6)\s*ghz\b|\b(?:wi[- ]?fi\s+)?band\b|\bchannel\b",
                unit,
                flags=re.IGNORECASE,
            ))
            explicit_negation = bool(re.search(
                rf"\b(?:wired\s+)?{re.escape(entity)}\b[^.!?]{{0,55}}"
                r"\b(?:isn['’]?t|is\s+not|doesn['’]?t|does\s+not|can['’]?t|cannot)\b"
                r"[^.!?]{0,55}\b(?:wi[- ]?fi|band|channel|ghz)\b|"
                r"\bno\s+(?:wi[- ]?fi\s+)?band\b",
                unit,
                flags=re.IGNORECASE,
            ))
            if has_radio_term and not explicit_negation:
                violations.append(
                    "diagnostic answer associated a user-described wired device with a Wi-Fi band/channel"
                )
                break
        if violations and violations[-1].startswith("diagnostic answer associated"):
            break

    # Mentioning backhaul as a hypothesis is fine. Declaring its actual state
    # is not, unless Oliver supplied a backhaul-specific observation.
    if "backhaul" not in source and re.search(
        r"\b(?:the|your)?\s*(?:mesh\s+)?backhaul(?:\s+(?:path|link))?\b"
        r"[^.!?]{0,90}\b(?:is|are|was|were|looks?|seems?)\s+"
        r"(?:fine|healthy|good|working|functioning|okay|ok|not\s+(?:the\s+)?bottleneck)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer declared unmeasured backhaul state as established fact"
        )

    if "access point" not in source and re.search(
        r"\b(?:the|your)\s+(?:specific\s+)?access\s+point\b[^.!?]{0,90}"
        r"\b(?:serving|for|on)\s+(?:your\s+)?(?:upstairs|upper\s+floor|room|area)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer invented a user-specific access-point/topology detail"
        )

    physical_details = (
        "concrete",
        "brick",
        "metal studs",
        "radiator",
        "heater",
        "steel",
        "foil insulation",
        "drywall",
        "plaster",
        "attic",
        "antenna alignment",
        "wall",
        "walls",
        "floor",
        "floors",
    )
    hedge_markers = (
        "could be", "might be", "may be", "possible", "possibly",
        "for example", "such as", "one possibility", "a possibility",
    )
    for detail in physical_details:
        if detail in source or detail not in text:
            continue
        containing_units = [
            unit.strip()
            for unit in re.split(r"(?<=[.!?])\s+", text)
            if detail in unit
        ]
        if not containing_units:
            continue
        if any(
            not any(marker in unit for marker in hedge_markers)
            for unit in containing_units
        ):
            violations.append(
                "diagnostic answer asserted an unmeasured physical/layout detail as the actual cause"
            )
            break

    if re.search(
        r"\b(?:almost\s+certainly|definitely|clearly|classic\s+(?:case|symptom|sign)(?:\s+of)?|"
        r"the\s+bottleneck\s+is|the\s+issue\s+is)\b[^.!?]{0,140}"
        r"\b(?:physical\s+interference|wireless\s+interference|interference|poor\s+placement|"
        r"poor\s+signal(?:\s+strength)?|signal\s+attenuation|antenna\s+alignment|walls?|floors?|"
        r"attic|drywall|concrete|metal\s+studs)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer promoted an unmeasured physical cause from hypothesis to near-certainty"
        )

    if re.search(
        r"\b(?:probably|likely|most\s+likely)\b[^.!?]{0,45}"
        r"\b(?:due\s+to|because\s+of|caused\s+by|from)\b[^.!?]{0,70}"
        r"\b(?:physical\s+interference|wireless\s+interference|interference|poor\s+placement|"
        r"poor\s+signal(?:\s+strength)?|signal\s+attenuation|antenna\s+alignment|walls?|floors?|"
        r"attic|drywall|concrete|metal\s+studs)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer promoted an unmeasured physical cause from hypothesis to near-certainty"
        )

    # A main-node reading does not collapse a mesh problem into purely
    # environmental causes. The unmeasured wireless/mesh path remains open.
    if (
        "mesh" in source
        and "main" in source
        and re.search(r"\bupstairs\b", source)
        and "backhaul" not in source
        and re.search(
            r"\b(?:narrows?|narrowed|points?|pointed)\b[^.!?]{0,120}"
            r"\b(?:environmental|interference|physical\s+obstruction|walls?|floors?)\b",
            text,
            flags=re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:mesh\s+path|wireless\s+path|backhaul|node\s+placement|"
            r"association|roaming|signal\s+path)\b",
            text,
            flags=re.IGNORECASE,
        )
    ):
        violations.append(
            "diagnostic answer excluded the still-unmeasured mesh/wireless path"
        )

    # A fast near-node reading is useful evidence, but it does not prove that
    # every router/node/hardware component is healthy or establish one exact
    # physical cause. Preserve "less likely / points toward" calibration.
    if re.search(r"\b(?:mbps|gbps)\b", source, flags=re.IGNORECASE):
        if re.search(
            r"\b(?:proves?|proven)\b[^.!?]{0,110}\b(?:hardware|router|node|equipment)\b"
            r"[^.!?]{0,60}\b(?:fine|healthy|working|good|okay|ok)\b|"
            r"\b(?:hardware|router|node|equipment)\b[^.!?]{0,80}\b(?:is|are)\s+definitely\s+fine\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "diagnostic answer treated one throughput reading as proof that all relevant hardware is healthy"
            )

        if re.search(
            r"\b(?:points?|pointed)\s+squarely\s+to\b[^.!?]{0,140}"
            r"\b(?:physical\s+layer|attenuation|interference|walls?|backhaul|signal)\b|"
            r"\brules?\s+out\b[^.!?]{0,120}\b(?:general\s+service\s+degradation|"
            r"bandwidth\s+cap|throttled\s+plan|isp\s+problem)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "diagnostic answer overclaimed what the supplied throughput measurements rule out or prove"
            )

        if (
            re.search(r"\bupstairs\b", source, flags=re.IGNORECASE)
            and re.search(r"\b(?:main\s+)?(?:mesh\s+)?node\b", source, flags=re.IGNORECASE)
            and re.search(
                r"\brules?\s+out\b[^.!?]{0,120}\b(?:wireless\s+)?(?:range|coverage|distance|attenuation|signal\s+loss|signal\s+strength)\b|"
                r"\b(?:wireless\s+)?(?:range|coverage|distance|attenuation|signal\s+loss|signal\s+strength)\b[^.!?]{0,90}\b(?:is|was)\s+ruled\s+out\b",
                text,
                flags=re.IGNORECASE,
            )
        ):
            violations.append(
                "diagnostic answer ruled out an upstairs range/coverage path that remains compatible with the supplied measurements"
            )

    # User-specific network infrastructure must come from the USER packet. A
    # generic ISP/mesh prompt does not establish a tower, an upstairs access
    # point, or a particular between-floor backhaul topology.
    if "tower" not in source and re.search(
        r"\b(?:tower|cell\s+tower|wireless\s+tower)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer introduced an unprovided network tower/infrastructure detail"
        )

    if "access point" not in source and re.search(
        r"\b(?:the|your|an?)\s+access\s+point\b[^.!?]{0,70}"
        r"\b(?:upstairs|downstairs|between\s+floors|in\s+your\s+room|in\s+the\s+room)\b|"
        r"\baccess\s+point\s+(?:upstairs|downstairs)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer invented a user-specific access-point/topology detail"
        )

    if "backhaul" not in source and re.search(
        r"\b(?:mesh\s+)?backhaul\b[^.!?]{0,60}\bbetween\s+(?:the\s+)?floors\b|"
        r"\bbetween\s+(?:the\s+)?floors\b[^.!?]{0,60}\b(?:mesh\s+)?backhaul\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer invented a user-specific between-floor backhaul topology"
        )

    # If a wired endpoint is already fast, a conditional conclusion that two
    # slow *wireless* location tests would make the ISP/plan the likely cause is
    # internally inconsistent with the supplied evidence.
    if wired_entities and re.search(r"\b(?:mbps|gbps)\b", source, re.IGNORECASE):
        if re.search(
            r"\bif\s+(?:they|both|the\s+phone\s+tests?)\b[^.!?]{0,80}\bslow\b"
            r"[^.!?]{0,100}\b(?:isp|internet\s+plan|plan)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "diagnostic answer contradicted the known fast wired result by making slow wireless location tests evidence for an ISP/plan bottleneck"
            )

    # Preserve relations in the supplied measurements. "Phone fast next to
    # the main node, slow upstairs" does not establish that the upstairs test
    # happened next to that node, nor does it establish a separate upstairs
    # mesh node.
    user_supplied_upstairs_node = bool(re.search(
        r"\bupstairs\s+(?:mesh\s+)?node\b|"
        r"\b(?:mesh\s+)?node\s+upstairs\b|"
        r"\b(?:mesh\s+)?node\b[^.!?]{0,25}\b(?:is|was|located|sitting)\s+upstairs\b|"
        r"\b(?:mesh\s+)?node\b[^.!?]{0,25}\bon\s+(?:the\s+)?upper\s+floor\b",
        source,
        flags=re.IGNORECASE,
    ))
    draft_asserts_upstairs_node = bool(re.search(
        r"\bupstairs\s+(?:mesh\s+)?node\b|"
        r"\b(?:mesh\s+)?node\s+upstairs\b|"
        r"\b(?:mesh\s+)?node\b[^.!?]{0,25}\b(?:is|was|located|sitting)\s+upstairs\b|"
        r"\b(?:mesh\s+)?node\b[^.!?]{0,25}\bon\s+(?:the\s+)?upper\s+floor\b",
        text,
        flags=re.IGNORECASE,
    ))
    if draft_asserts_upstairs_node and not user_supplied_upstairs_node:
        violations.append(
            "diagnostic answer invented a separate upstairs mesh-node/topology relation"
        )

    # If the current USER turn explicitly contrasts a fast reading next to the
    # main node with a slow upstairs reading, do not collapse those into one
    # location (for example, '20 Mbps upstairs even when close to the node').
    user_separates_near_and_upstairs = bool(re.search(
        r"\bphone\b[^.!?]{0,90}\b(?:hits?|gets?|reaches?)\b[^.!?]{0,50}"
        r"\b(?:next\s+to|near|beside)\b[^.!?]{0,45}\b(?:main\s+)?(?:mesh\s+)?node\b"
        r"[^.!?]{0,90}\b(?:but|while|and)\b[^.!?]{0,40}\b(?:still\s+)?(?:slow|\d+(?:\.\d+)?(?:\s*(?:mbps|gbps))?)\b[^.!?]{0,35}\bupstairs\b",
        current_user,
        flags=re.IGNORECASE,
    ))
    if user_separates_near_and_upstairs and re.search(
        r"\bphone\b[^.!?]{0,80}\bupstairs\b[^.!?]{0,100}"
        r"\b(?:even\s+when|while|despite\s+being)\b[^.!?]{0,45}"
        r"\b(?:close\s+to|near|next\s+to|beside)\b[^.!?]{0,45}\b(?:main\s+)?(?:mesh\s+)?node\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer collapsed distinct near-node and upstairs measurements into the same location"
        )

    # A wired endpoint's throughput can be known without its physical location
    # being known. Do not silently move it next to the router/node.
    for entity in sorted(wired_entities):
        user_places_wired_near_source = bool(re.search(
            rf"\b(?:wired\s+)?{re.escape(entity)}\b[^.!?]{{0,90}}"
            r"\b(?:next\s+to|near|beside|by)\b[^.!?]{0,45}\b(?:router|node|wi[- ]?fi\s+source)\b",
            source,
            flags=re.IGNORECASE,
        ))
        draft_places_wired_near_source = bool(re.search(
            rf"\b(?:wired\s+)?{re.escape(entity)}\b[^.!?]{{0,100}}"
            r"\b(?:next\s+to|near|beside|by)\b[^.!?]{0,45}\b(?:router|node|wi[- ]?fi\s+source)\b",
            text,
            flags=re.IGNORECASE,
        ))
        if draft_places_wired_near_source and not user_places_wired_near_source:
            violations.append(
                "diagnostic answer invented the physical location of a user-described wired endpoint"
            )
            break

    # VRR tracks frame presentation cadence, not scene brightness. Dark scenes
    # can expose refresh/gamma instability, but brightness itself does not tell
    # VRR what refresh rate to choose. Avoid inventing a panel type too.
    if re.search(r"\b(?:vrr|variable\s+refresh)\b", source, re.IGNORECASE):
        if re.search(
            r"\b(?:refresh\s+rate|display)\b[^.!?]{0,120}"
            r"\b(?:based\s+on|triggered\s+by)\b[^.!?]{0,80}"
            r"\b(?:brightness|luminance|darkness|motion)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "VRR explanation incorrectly tied refresh-rate selection to scene brightness/content"
            )
        if re.search(
            r"\b(?:switch(?:es|ed|ing)?|change(?:s|d|ing)?)\b[^.!?]{0,55}\brefresh\s+rates?\b"
            r"[^.!?]{0,70}\b(?:to\s+match|for)\b[^.!?]{0,45}\b(?:slower|faster|dark|bright)\s+scenes?\b|"
            r"\brefresh\s+rates?\b[^.!?]{0,70}\b(?:match(?:es|ing)?|tracks?)\b[^.!?]{0,45}"
            r"\b(?:slower|faster|dark|bright)\s+scenes?\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "VRR explanation incorrectly treated scene content as the controller of refresh-rate changes"
            )
        if re.search(r"\bdisplay\b[^.!?]{0,60}\bdrop(?:s|ping)?\s+frames\b", text, re.IGNORECASE):
            violations.append(
                "VRR explanation incorrectly described the display itself as dropping frames"
            )
        if not re.search(r"\b(?:oleds?|lcds?|pwm|va|ips|tn|local\s+dimming)\b", source, re.IGNORECASE) and re.search(
            r"\b(?:oleds?|lcds?|pwm|va(?:\s+panel)?|ips(?:\s+panel)?|tn(?:\s+panel)?|local\s+dimming(?:\s+zones?)?)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "VRR diagnosis introduced an unprovided panel/dimming technology"
            )
        if (
            re.search(r"\bdark\s+scenes?\b", current_user, re.IGNORECASE)
            and (
                re.search(
                    r"\b(?:strong|clear|definite)\s+(?:indicator|sign|clue|evidence)\b",
                    text,
                    flags=re.IGNORECASE,
                )
                or re.search(
                    r"\b(?:points?|pointing)\s+(?:strongly\s+)?(?:toward|towards|to)\b"
                    r"[^.!?]{0,70}\b(?:vrr|variable\s+refresh|culprit)\b",
                    text,
                    flags=re.IGNORECASE,
                )
                or re.search(
                    r"\bclassic\s+(?:symptom|sign)\b[^.!?]{0,70}\b(?:vrr|variable\s+refresh)\b",
                    text,
                    flags=re.IGNORECASE,
                )
            )
        ):
            violations.append(
                "VRR diagnosis treated dark-scene correlation as a strong/definite indicator or strong/diagnostic evidence instead of merely compatible evidence"
            )

        if (
            re.search(r"\bdark\s+scenes?\b", current_user, re.IGNORECASE)
            and re.search(
                r"\bdark\s+scenes?\b[^.!?]{0,160}\b(?:gpu|graphics)\b[^.!?]{0,120}"
                r"\b(?:under\s+load|more\s+load|heavier\s+load|frame[- ]?rate\s+drops?|stutter(?:ing)?)\b|"
                r"\b(?:gpu|graphics)\b[^.!?]{0,120}\b(?:under\s+load|more\s+load|heavier\s+load)\b"
                r"[^.!?]{0,120}\bdark\s+scenes?\b",
                text,
                flags=re.IGNORECASE,
            )
        ):
            violations.append(
                "VRR diagnosis incorrectly treated dark scenes themselves as evidence of higher GPU load or frame-rate drops"
            )

        if re.search(
            r"\b(?:your\s+screen|it)\s+flickers\b[^.!?]{0,60}\bbecause\b|"
            r"\bthe\s+cause\s+is\b",
            text,
            flags=re.IGNORECASE,
        ) and not re.search(r"\b(?:measured|confirmed|verified|tested)\b", source):
            violations.append(
                "VRR diagnosis stated a definite cause from correlation alone"
            )

        if re.search(
            r"\b(?:display|screen|monitor)\b[^.!?]{0,100}\b(?:drop(?:s|ping)?|lower(?:s|ing)?|reduce(?:s|d|ing)?)\b"
            r"[^.!?]{0,80}\brefresh\s+rate\b[^.!?]{0,120}"
            r"\b(?:save\s+power|reduce\s+motion\s+blur|static|dim|dark)\b|"
            r"\brefresh\s+rate\b[^.!?]{0,100}\b(?:drop(?:s|ping)?|lower(?:s|ing)?)\b"
            r"[^.!?]{0,100}\b(?:dark|dim|static|save\s+power|motion\s+blur)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "VRR diagnosis invented scene-brightness/power or motion-blur control of refresh-rate selection"
            )

        if not re.search(
            r"\b(?:manga|anime|chapter|episode|adaptation)\b",
            current_user,
            flags=re.IGNORECASE,
        ) and re.search(
            r"\b(?:manga|anime|chapter|episode|adaptation)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "VRR diagnostic answer revived unrelated media context after the conversation had switched topics"
            )
        if re.search(r"\b(?:it(?:'s| is)|this is)\s+not\s+a\s+defect\b", text, re.IGNORECASE):
            violations.append(
                "VRR diagnosis ruled out a display defect without user-specific isolation evidence"
            )
        if not re.search(r"\b(?:brightness\s+control|dimming|backlight|pixel\s+response)\b", source, re.IGNORECASE) and re.search(
            r"\b(?:aggressive\s+)?(?:brightness|dimming)\s+(?:adjustments?|changes?)\b[^.!?]{0,100}"
            r"\b(?:cause|causes|causing|create|creates|creating|stutter|flicker)\b|"
            r"\b(?:backlight|pixel\s+response)\b[^.!?]{0,90}\b(?:stutter|flicker)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "VRR diagnosis invented an unmeasured brightness/dimming or panel-response mechanism"
            )

        if not re.search(r"\b(?:mid[- ]frame|low[- ]brightness\s+intervals?)\b", source, re.IGNORECASE) and re.search(
            r"\b(?:mid[- ]frame|low[- ]brightness\s+intervals?)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "VRR diagnosis invented an unsupported mid-frame/low-brightness timing mechanism"
            )

    # A near-main-node result does not rule out an unmeasured mesh backhaul or
    # upstairs wireless path. Explicit rule-out wording is stronger than a
    # hypothesis and therefore needs direct user evidence.
    if "backhaul" not in source and re.search(
        r"\b(?:rules?|ruled)\s+out\b[^.!?]{0,110}\bbackhaul\b|"
        r"\bbackhaul\b[^.!?]{0,90}\b(?:is|was|has been)\s+(?:ruled\s+out|not\s+the\s+bottleneck)\b|"
        r"\bproves?\b[^.!?]{0,120}\b(?:bottleneck|problem|issue)\b[^.!?]{0,60}"
        r"\b(?:isn['’]?t|is\s+not|wasn['’]?t|was\s+not)\b[^.!?]{0,60}\bbackhaul\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "diagnostic answer ruled out an unmeasured backhaul path"
        )

    if (
        "mesh" in source
        and "main" in source
        and "upstairs" in source
        and re.search(
            r"\b(?:it|that)\s+(?:just\s+)?means\b[^.!?]{0,120}"
            r"\b(?:signal\s+(?:is\s+)?(?:getting\s+)?lost|over[- ]the[- ]air|through\s+the\s+air)\b",
            text,
            flags=re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:mesh\s+path|wireless\s+path|backhaul|roaming|association)\b",
            text,
            flags=re.IGNORECASE,
        )
    ):
        violations.append(
            "diagnostic answer collapsed an unresolved mesh/path problem into wireless propagation alone"
        )

    return list(dict.fromkeys(violations))


def _is_stolen_session_credential_context(
    user_input: str,
) -> bool:
    """Return True for questions about an already-copied authenticated session.

    This is the shared semantic gate for both validation and deterministic
    fallback. Keeping one detector prevents the acceptance guard from knowing
    about a concept that the fallback path cannot recognise.

    Deliberately bounded:
    - there must be theft/copy/compromise language;
    - the turn must explicitly concern a session;
    - the copied credential must be identified as a cookie/token/credential.

    Ordinary cookie, token, login, or MFA questions therefore stay on the
    normal stable-knowledge path.
    """
    user = re.sub(
        r"\s+",
        " ",
        str(
            user_input
            or ""
        ).strip(),
    ).lower()

    stolen_or_copied = bool(
        re.search(
            r"\b(?:stolen|stole|steal|steals|stealing|"
            r"nicks?|nicked|nick(?:ing)?|"
            r"cop(?:y|ied|ies|ying)|"
            r"compromis(?:e|ed|es|ing))\b",
            user,
            flags=re.IGNORECASE,
        )
    )

    session_context = bool(
        re.search(
            r"\bsessions?\b",
            user,
            flags=re.IGNORECASE,
        )
    )

    credential_context = bool(
        re.search(
            r"\b(?:cookies?|tokens?|credentials?|session\s+ids?)\b",
            user,
            flags=re.IGNORECASE,
        )
    )

    return (
        stolen_or_copied
        and session_context
        and credential_context
    )


def find_session_cookie_security_violations(
    user_input: str,
    draft: str,
) -> List[str]:
    """Prevent common stolen-session misconceptions.

    A copied authenticated session is distinct from the login ceremony that
    created it. Local cookie deletion, ordinary logout wording, or a password
    change must not be presented as universal server-side revocation of the
    attacker's already-copied credential.
    """
    if not _is_stolen_session_credential_context(
        user_input
    ):
        return []

    text = re.sub(r"\s+", " ", str(draft or "").strip()).lower()
    bad_patterns = (
        r"\buntil\b[^.!?]{0,90}\b(?:clear|delete|remove)\b[^.!?]{0,30}\bcookies?\b",
        r"\b(?:clear|delete|remove)\b[^.!?]{0,30}\bcookies?\b[^.!?]{0,70}"
        r"\b(?:stop|invalidate|revoke|kick|end)\b[^.!?]{0,40}\b(?:attacker|thief|session|access)\b",
        r"\b(?:stolen|existing|copied)\s+session\b[^.!?]{0,80}\b(?:remains?|stays?)\s+active\b"
        r"[^.!?]{0,90}\bunless\b[^.!?]{0,70}\b(?:clear|delete|remove)\b[^.!?]{0,30}\bcookies?\b",
        r"\bunless\b[^.!?]{0,60}\b(?:clear|delete|remove)\b[^.!?]{0,30}\bcookies?\b"
        r"[^.!?]{0,80}\b(?:session|access|attacker|stolen)\b",
    )
    violations = []
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in bad_patterns):
        violations.append(
            "stolen-session answer treated local cookie deletion as revocation of the attacker's copied session"
        )

    # If Oliver is explicitly asking about a stolen/copied authenticated cookie,
    # listing "clear cookies" as part of invalidating the attacker is misleading
    # unless the answer clearly distinguishes local browser deletion from
    # server-side revocation of the attacker's copied credential.
    mentions_cookie_clearing = bool(re.search(
        r"\b(?:clear(?:s|ed|ing)?|delet(?:e|es|ed|ing)|remov(?:e|es|ed|ing))\b[^.!?]{0,45}\b(?:cookies?|browser\s+data|site\s+data|browser\s+storage)\b",
        text,
        flags=re.IGNORECASE,
    ))
    explicitly_disclaims_cookie_revocation = bool(re.search(
        r"\b(?:clear(?:ing)?|delet(?:e|ing)|remov(?:e|ing))\b[^.!?]{0,50}"
        r"\b(?:local\s+|your\s+|browser\s+)?(?:cookies?|browser\s+data|site\s+data|browser\s+storage)\b"
        r"[^.!?]{0,100}\b(?:doesn['’]?t|does\s+not|won['’]?t|will\s+not|can['’]?t|cannot)\b"
        r"[^.!?]{0,80}\b(?:revoke|invalidate|stop|kill|end|erase|remove|delete)\b"
        r"[^.!?]{0,80}\b(?:attacker|thief|copied|stolen|remote|other\s+device|session|access)\b|"
        r"\b(?:only|just)\b[^.!?]{0,40}\b(?:clear|remove|delete)s?\b[^.!?]{0,50}"
        r"\b(?:your|the)\s+(?:local\s+|browser\s+)?(?:cookie|browser\s+data|site\s+data|browser\s+storage)",
        text,
        flags=re.IGNORECASE,
    ))
    if (
        mentions_cookie_clearing
        and not explicitly_disclaims_cookie_revocation
        and "stolen-session answer treated local cookie deletion as revocation of the attacker's copied session"
        not in violations
    ):
        violations.append(
            "stolen-session answer treated local cookie deletion as revocation of the attacker's copied session"
        )

    if re.search(
        r"\b(?:until|unless)\b[^.!?]{0,90}\bchange\s+(?:your\s+|the\s+)?password\b|"
        r"\bchange\s+(?:your\s+|the\s+)?password\b[^.!?]{0,90}\b(?:kills?|ends?|invalidates?|revokes?|stops?)\b[^.!?]{0,50}\b(?:session|cookie|attacker|access)\b",
        text,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\bif\b[^.!?]{0,80}\b(?:service|site|server|provider)\b[^.!?]{0,80}\b(?:invalidates?|revokes?|ends?)\b[^.!?]{0,40}\bsessions?\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "stolen-session answer treated a password change as guaranteed invalidation of an already-stolen session"
        )

    unqualified_logout_claim = bool(re.search(
        r"\buntil\b[^.!?]{0,100}\b(?:log(?:ged|ging)?\s*out|logout)\b",
        text,
        flags=re.IGNORECASE,
    ))
    logout_is_server_qualified = bool(re.search(
        r"\b(?:log(?:ged|ging)?\s*out|logout)\b[^.!?]{0,90}\b(?:everywhere|all\s+sessions|all\s+devices|server[- ]side|revokes?|invalidates?)\b|"
        r"\b(?:server[- ]side|all\s+sessions|all\s+devices|logout\s+endpoint|service|site|server|provider)\b"
        r"[^.!?]{0,90}\b(?:log\s*out|logout|revokes?|invalidates?)\b",
        text,
        flags=re.IGNORECASE,
    ))
    if unqualified_logout_claim and not logout_is_server_qualified:
        violations.append(
            "stolen-session answer treated an unspecified logout as guaranteed server-side invalidation of the attacker's copied session"
        )

    # Catch causal phrasing such as "kick them out by logging out and clearing
    # cookies or changing your password". Those local/user actions only remove
    # the attacker's copied token if the service performs server-side session
    # invalidation; the wording must not imply that guarantee generically.
    local_action_kicks_attacker = bool(re.search(
        r"\b(?:kick|force|get)\s+(?:them|the\s+attacker|the\s+thief)\s+out\b"
        r"[^.!?]{0,60}\b(?:by|with)\b[^.!?]{0,100}"
        r"\b(?:log(?:ged|ging)?\s*out|logout|clear(?:s|ed|ing)?\s+cookies?|"
        r"chang(?:e|es|ed|ing)\s+(?:your\s+|the\s+)?password)\b",
        text,
        flags=re.IGNORECASE,
    ))
    if local_action_kicks_attacker and not re.search(
        r"\b(?:server[- ]side|all\s+sessions|all\s+devices|logout\s+everywhere|"
        r"revoke(?:s|d)?\s+(?:the\s+)?session|invalidate(?:s|d)?\s+(?:the\s+)?session)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "stolen-session answer treated local logout/password/cookie actions as guaranteed revocation of the attacker's copied session"
        )

    return list(dict.fromkeys(violations))


def find_explicit_example_request_violations(
    user_input: str,
    draft: str,
) -> List[str]:
    """Enforce an explicit request for a concrete/tiny example.

    The model may choose the example, but it cannot answer only with another
    abstract definition when Oliver explicitly asked to see one.
    """
    user = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
    if not re.search(
        r"\b(?:give|show)\s+(?:me\s+)?(?:a\s+)?(?:tiny|small|quick|simple|concrete)?\s*example\b|"
        r"\b(?:tiny|small|quick|simple|concrete)\s+example\b",
        user,
        flags=re.IGNORECASE,
    ):
        return []

    text = str(draft or "").strip()
    if not text:
        return ["explicit example request received no example"]

    example_markers = (
        r"\bfor example\b",
        r"\be\.g\.",
        r"\bsuppose\b",
        r"\bimagine\b",
        r"\blet['’]?s say\b",
        r"\bsay you (?:have|start|train|split|run)\b",
        r"\bconsider\b.{0,30}:",
        r"\bexample\s*:",
        r"```",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in example_markers):
        return []

    return [
        "explicit example request was answered only abstractly without a concrete example"
    ]


def find_recommendation_forecast_violations(
    draft: str,
    core_answer_contract,
) -> List[str]:
    """Keep ordinary recommendations from smuggling in unsupported forecasts.

    A skill/item/action can be recommended from stable judgement, but a claim
    that it "won't be replaced", is future-proof, or will survive automation is
    a separate changing-world prediction. Without verified evidence in the
    current contract, reject that rationale and let the model retry more modestly.
    """
    runtime = coerce_answer_contract_runtime(core_answer_contract)
    if runtime is None or runtime.intent != "recommendation_request":
        return []
    if runtime.verified_evidence_claims:
        return []

    text = re.sub(r"\s+", " ", str(draft or "").strip()).lower()
    forecast_patterns = (
        r"\b(?:won['’]?t|will\s+not|can['’]?t|cannot|isn['’]?t\s+going\s+to|is\s+not\s+going\s+to)\b[^.!?]{0,100}\b(?:replace|replaced|automate|automated|eliminate|eliminated|disappear|replicate|replicated)\b",
        r"\b(?:ai|automation)\b[^.!?]{0,80}\b(?:won['’]?t|will\s+not|can['’]?t|cannot)\b[^.!?]{0,80}\b(?:replicate|replace|automate|eliminate)\b",
        r"\b(?:humans?|people)\s+(?:still\s+)?(?:hold|retain|keep)\s+(?:the\s+)?(?:leverage|advantage|edge)\b[^.!?]{0,80}\b(?:ai|automation|automated|scales?)\b",
        r"\b(?:future[- ]?proof|automation[- ]?proof|ai[- ]?proof)\b",
        r"\b(?:will|is\s+going\s+to)\b[^.!?]{0,80}\b(?:survive|remain|stay)\b[^.!?]{0,60}\b(?:ai|automation|automated)\b",
        r"\b(?:ai|automation|machines?)\b[^.!?]{0,60}\b(?:will|would)\s+fail\b",
        r"\b(?:machines?|ai|automation)\b[^.!?]{0,60}\b(?:don['’]?t|do\s+not|can['’]?t|cannot)\s+(?:model|understand|handle|reason\s+about|replicate)\b",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in forecast_patterns):
        return [
            "recommendation rationale made an unsupported future replacement/automation forecast"
        ]
    return []


def find_recommendation_topic_drift_violations(
    user_input: str,
    draft: str,
    conversation=None,
) -> List[str]:
    """Keep a requested next step attached to the live topic, not a side constraint.

    A phrase such as "I have uni shit to do too" limits how much advice Oliver
    wants; it does not silently replace the subject of a rejection/application
    follow-up with an invented university deadline.
    """
    current = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
    if not re.search(r"\b(?:next\s+step|useful\s+next\s+step|one\s+actual\s+useful)\b", current):
        return []

    prior_user = re.sub(
        r"\s+",
        " ",
        str(build_recent_user_grounding_context(conversation, max_user_messages=3) or "").strip(),
    ).lower()
    if not re.search(r"\b(?:rejection|rejected|grad|graduate|application|job)\b", prior_user):
        return []

    text = re.sub(r"\s+", " ", str(draft or "").strip()).lower()
    stays_on_topic = bool(re.search(
        r"\b(?:rejection|rejected|application|apply|job|role|grad|graduate|employer|email|career)\b",
        text,
    ))
    invented_uni_task = bool(re.search(
        r"\b(?:submit|finish|complete|crush|do|focus\s+on|tackle|pick|start(?:\s+typing)?)\b[^.!?]{0,70}"
        r"\b(?:assignments?|class|uni|university|coursework|course|task)\b|"
        r"\b(?:assignments?|class|uni|university|coursework|course)\b[^.!?]{0,70}"
        r"\b(?:tonight|urgent|deadline|due\s+(?:today|tomorrow|this\s+week)|submit|finish|complete|one\s+at\s+a\s+time)\b",
        text,
    ))
    user_context = (prior_user + " " + current).lower()
    supplied_specific_uni_task = bool(re.search(
        r"\b(?:assignments?|coursework|deadline|due\s+(?:today|tomorrow|this\s+week)|"
        r"exam|quiz|class\s+task|uni\s+assignment)\b",
        user_context,
    ))
    if invented_uni_task and not supplied_specific_uni_task:
        return [
            "recommendation follow-up invented a specific university task/deadline from a generic uni constraint"
        ]
    if invented_uni_task and not stays_on_topic:
        return [
            "recommendation follow-up drifted from the live rejection/application topic into an invented university task"
        ]

    invented_personal_activity = bool(re.search(
        r"\b(?:open|opening|check|checking)\b[^.!?]{0,45}\b(?:your\s+)?(?:uni|university)\s+portal\b|"
        r"\b(?:check|checking)\b[^.!?]{0,35}\b(?:your\s+)?grades?\b|"
        r"\b(?:email|message)\b[^.!?]{0,55}\b(?:you(?:'ve| have)\s+been\s+avoiding|you\s+avoided)\b|"
        r"\b(?:stop\s+)?(?:scrolling|doomscrolling)\b|"
        r"\bdrowning\b[^.!?]{0,40}\bdoomscrolling\b",
        text,
        flags=re.IGNORECASE,
    ))
    supplied_personal_activity = bool(re.search(
        r"\b(?:portal|grades?|avoiding\s+(?:an?\s+)?email|scrolling|doomscrolling)\b",
        user_context,
        flags=re.IGNORECASE,
    ))
    if invented_personal_activity and not supplied_personal_activity:
        return [
            "recommendation follow-up invented a personal task or current behaviour that Oliver did not supply"
        ]

    return []


def find_recommendation_completion_violations(
    user_input: str,
    draft: str,
    core_answer_contract,
) -> List[str]:
    """Require a concrete candidate when Oliver explicitly asks what to watch/read/play.

    Repeating the requested mood or constraints is not a recommendation. The rule
    is intentionally limited to explicit media-selection prompts; broader advice
    requests keep their existing behaviour.
    """
    runtime = coerce_answer_contract_runtime(core_answer_contract)
    if runtime is None or runtime.intent != "recommendation_request":
        return []

    current = re.sub(r"\s+", " ", str(user_input or "").strip())
    if not re.search(
        r"\bwhat\s+should\s+i\s+(?:watch|read|play)\b|"
        r"\b(?:recommend|pick|choose)\b[^?]{0,35}\b(?:movie|show|series|anime|manga|book|game)\b",
        current,
        flags=re.IGNORECASE,
    ):
        return []

    text = str(draft or "").strip()
    if not text:
        return ["explicit media recommendation did not name a concrete candidate"]

    concrete = bool(
        re.search(
            r"\b(?i:watch|read|play|try|start\s+with|go\s+with|pick)\s+"
            r"(?:\*{0,2}|[\"'“‘])?"
            r"[A-Z0-9][A-Za-z0-9&:’'._!+\-]*(?:\s+[A-Z0-9][A-Za-z0-9&:’'._!+\-]*){0,8}",
            text,
        )
        or re.search(r"[\"“][^\"”]{2,80}[\"”]", text)
    )

    if concrete:
        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
        if re.match(r"^\s*(?:it|this|that)\b", first_sentence, flags=re.IGNORECASE):
            first_has_candidate = bool(
                re.search(
                    r"\b(?i:watch|read|play|try|start\s+with|go\s+with|pick)\s+"
                    r"(?:\*{0,2}|[\"'“‘])?"
                    r"[A-Z0-9][A-Za-z0-9&:’'._!+\-]*(?:\s+[A-Z0-9][A-Za-z0-9&:’'._!+\-]*){0,8}",
                    first_sentence,
                )
                or re.search(r"[\"“][^\"”]{2,80}[\"”]", first_sentence)
            )
            if not first_has_candidate:
                return [
                    "explicit media recommendation opened with an unresolved candidate pronoun before naming a concrete title"
                ]
        return []

    return ["explicit media recommendation did not name a concrete candidate"]


def find_pairwise_comparison_drift_violations(
    draft: str,
    core_answer_contract,
) -> List[str]:
    """Reject a conclusion that silently replaces a requested comparison side.

    Core may allow third platforms/tools as context, but a Mac-vs-Windows style
    request should not end by recommending Linux (or another third option) as if
    that were one of the requested sides. Structured contract metadata carries
    the frame so this check does not have to parse model-facing prose.
    """
    runtime = coerce_answer_contract_runtime(core_answer_contract)
    if runtime is None:
        return []

    frame = str((runtime.metadata or {}).get("comparison_frame") or "").strip()
    if " vs " not in frame.lower():
        return []

    left, right = re.split(r"\s+vs\s+", frame, maxsplit=1, flags=re.IGNORECASE)
    left = left.strip().lower()
    right = right.strip().lower()
    if not left or not right:
        return []

    draft_lower = re.sub(r"\s+", " ", str(draft or "").lower()).strip()

    def side_present(side: str) -> bool:
        aliases = {side}
        if side in {"mac", "macos", "mac os"}:
            aliases.update({"mac", "macos", "mac os"})
        if side in {"windows", "win"}:
            aliases.update({"windows", "win"})
        return any(
            re.search(rf"\b{re.escape(alias)}\b", draft_lower, flags=re.IGNORECASE)
            for alias in aliases
        )

    if not side_present(left) or not side_present(right):
        return [
            "pairwise comparison answer omitted one of the two requested comparison sides"
        ]

    units = [
        unit.strip()
        for unit in re.split(r"(?<=[.!?])\s+", str(draft or ""))
        if unit.strip()
    ]

    for unit in units:
        low = unit.lower()
        if left in low or right in low:
            continue

        direct = re.search(
            r"\b(?:choose|pick|prefer|use|go\s+with|stick(?:ing)?\s+with)\s+"
            r"(?P<target>[A-Za-z][A-Za-z0-9+._-]{1,30})\b",
            unit,
            flags=re.IGNORECASE,
        )
        if direct:
            target = direct.group("target").lower()
            if target not in {left, right, "it", "that", "this"}:
                return [
                    "pairwise comparison answer concluded with a third option instead of the requested pair"
                ]

        pronoun = re.search(
            r"\b(?:comfortable|familiar|happy|experienced)\s+with\s+"
            r"(?P<target>[A-Za-z][A-Za-z0-9+._-]{1,30})\b[^.!?]{0,70}"
            r"\bstick(?:ing)?\s+with\s+it\b",
            unit,
            flags=re.IGNORECASE,
        )
        if pronoun:
            target = pronoun.group("target").lower()
            if target not in {left, right}:
                return [
                    "pairwise comparison answer concluded with a third option instead of the requested pair"
                ]

    # A third platform can be discussed as context (for example Linux VMs on
    # Mac vs Windows), but it must not silently become a third candidate in the
    # final comparison. Catch standalone option headings/summary bullets rather
    # than banning contextual mentions of the platform.
    requested_aliases = {left, right}
    if left in {"mac", "macos", "mac os"} or right in {"mac", "macos", "mac os"}:
        requested_aliases.update({"mac", "macos", "mac os"})
    if left in {"windows", "win"} or right in {"windows", "win"}:
        requested_aliases.update({"windows", "win"})

    third_platforms = ("linux", "chromeos", "freebsd")
    raw_draft = str(draft or "")
    for platform in third_platforms:
        if platform in requested_aliases:
            continue
        if re.search(
            rf"(?im)^\s*[-*]?\s*(?:\*\*)?{re.escape(platform)}(?:\*\*)?\s*:\s*",
            raw_draft,
        ):
            return [
                "pairwise comparison answer promoted a contextual third platform into a third comparison option"
            ]

    return []




def find_insufficient_context_overreach_violations(
    draft: str,
    core_answer_contract,
) -> List[str]:
    """Keep missing-input answers from filling the gap with generic world claims."""
    if contract_epistemic_mode(core_answer_contract) != "insufficient_user_context":
        return []
    text = re.sub(r"\s+", " ", str(draft or "").strip()).lower()
    if re.search(
        r"\b(?:most|usually|often|typically|generally|commonly|standard)\b[^.!?]{0,120}"
        r"\b(?:airlines?|carriers?|bags?|devices?|systems?|companies?|providers?|policies?|limits?)\b|"
        r"\b(?:airlines?|carriers?|providers?|companies?)\b[^.!?]{0,120}"
        r"\b(?:usually|often|typically|generally|commonly|strict(?:er|est)?|standard)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return [
            "missing-input answer filled an unknown task detail with an unnecessary generic world claim"
        ]

    if re.search(
        r"\b(?:kicked|removed|denied|refused|tossed|rejected)\b[^.!?]{0,60}\b(?:plane|flight|boarding|board|gate)\b|"
        r"\b(?:gate|boarding)\b[^.!?]{0,55}\b(?:tossed|rejected|denied|refused)\b|"
        r"\b(?:security|airport\s+security)\b[^.!?]{0,80}\b(?:repack|re-pack|pay|fee|confiscat|reject)\w*\b|"
        r"\b(?:pay|charged?)\b[^.!?]{0,60}\b(?:fee|oversize|overweight|baggage)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return [
            "missing-input answer invented airline/airport consequences that cannot be known without the carrier policy and bag details"
        ]

    # A missing policy/detail means the permission state is unknown. Do not
    # turn epistemic uncertainty into the opposite categorical conclusion
    # (for example, "definitely not allowed") merely because required
    # carrier/policy details were omitted.
    if re.search(
        r"\b(?:definitely|certainly|guaranteed(?:ly)?)\b[^.!?]{0,55}"
        r"\b(?:allowed|permitted|accepted|compliant|eligible|prohibited|forbidden)\b|"
        r"\b(?:allowed|permitted|accepted|compliant|eligible|prohibited|forbidden)\b"
        r"[^.!?]{0,45}\b(?:definitely|certainly|guaranteed)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return [
            "missing-input answer converted an unknown policy/permission state into a categorical conclusion"
        ]

    return []

def find_tcp_udp_semantics_violations(
    *,
    user_input: str,
    draft: str,
) -> List[str]:
    """Protect a stable networking polarity from subject drift.

    When Oliver explicitly asks about TCP versus UDP connection setup, Core
    should never let a draft blur which protocol is connection-oriented or
    which one uses a connection-establishment handshake. This is a compact
    stable-fact invariant, not a general web/current-world checker.
    """

    user = _normalise_for_grounding(user_input).lower()
    text = _normalise_for_grounding(draft).lower()

    if not (re.search(r"\btcp\b", user) and re.search(r"\budp\b", user)):
        return []

    if not re.search(r"\b(?:handshake|connectionless|connection[- ]oriented)\b", user):
        return []

    violations: List[str] = []

    if re.search(r"\btcp\b[^.!?]{0,100}\bconnectionless\b", text) or re.search(
        r"\bconnectionless\b[^.!?]{0,100}\btcp\b",
        text,
    ):
        violations.append("TCP/UDP explanation incorrectly described TCP as connectionless")

    udp_positive_handshake = bool(
        re.search(
            r"\budp\b[^.!?]{0,100}\b(?:requires?|needs?)\b[^.!?]{0,45}\bhandshake\b",
            text,
        )
        or (
            re.search(
                r"\budp\b[^.!?]{0,100}\buses?\b[^.!?]{0,45}\bhandshake\b",
                text,
            )
            and not re.search(
                r"\budp\b[^.!?]{0,100}\b(?:does\s+not|doesn't|doesnt|do\s+not|don't|dont|no)\b"
                r"[^.!?]{0,30}\buses?\b[^.!?]{0,45}\bhandshake\b",
                text,
            )
        )
    )
    if udp_positive_handshake:
        violations.append("TCP/UDP explanation incorrectly gave UDP a connection-establishment handshake")

    # For an explicit pairwise correction, both roles must be named clearly.
    # A dangling sentence such as "That's connectionless" after discussing
    # TCP is too ambiguous to safely accept even if the intended subject was UDP.
    if re.search(r"\bconnectionless\b", text):
        udp_near_connectionless = bool(
            re.search(r"\budp\b[^.!?]{0,90}\bconnectionless\b", text)
            or re.search(r"\bconnectionless\b[^.!?]{0,90}\budp\b", text)
        )
        if not udp_near_connectionless:
            violations.append("TCP/UDP explanation left the connectionless role ambiguous instead of assigning it to UDP")

    tcp_near_handshake = bool(
        re.search(r"\btcp\b[^.!?]{0,100}\bhandshake\b", text)
        or re.search(r"\bhandshake\b[^.!?]{0,100}\btcp\b", text)
    )
    if not tcp_near_handshake:
        violations.append("TCP/UDP explanation did not clearly assign connection establishment/handshake to TCP")

    udp_role_clear = bool(
        re.search(r"\budp\b[^.!?]{0,100}\bconnectionless\b", text)
        or re.search(r"\bconnectionless\b[^.!?]{0,100}\budp\b", text)
        or re.search(
            r"\budp\b[^.!?]{0,100}\b(?:does\s+not|doesn't|doesnt|no)\b"
            r"[^.!?]{0,50}\bhandshake\b",
            text,
        )
    )
    if not udp_role_clear:
        violations.append(
            "TCP/UDP pairwise correction did not clearly state that UDP is connectionless / has no connection-establishment handshake"
        )

    return list(dict.fromkeys(violations))


def find_python_mutable_default_semantics_violations(
    user_input: str,
    draft: str,
    conversation=None,
) -> List[str]:
    """Reject contradictions in the canonical mutable-default trace.

    The original program can live in a prior USER turn, so derive the expected
    trace from current + recent user-authored context rather than keying only on
    whichever wrong wording the model happened to use this time.
    """
    source_raw = "\n".join([
        str(user_input or ""),
        str(build_recent_user_grounding_context(conversation, max_user_messages=4) or ""),
    ])
    source = source_raw.lower()
    if not (
        re.search(r"def\s+[a-zA-Z_]\w*\s*\([^)]*=\s*\[\s*\]", source)
        or ("mutable default" in source and "python" in source)
    ):
        return []

    text_raw = str(draft or "").strip()
    text = re.sub(r"\s+", " ", text_raw).lower()
    violations = []

    if re.search(r"\b(?:stored|kept|saved)\s+in\s+(?:the\s+)?closure\b", text):
        violations.append(
            "Python mutable-default explanation incorrectly said the default is stored in a closure"
        )

    if re.search(r"\bx\s*=\s*x\s+or\s+\[\s*\]", text):
        violations.append(
            "Python mutable-default fix used 'x = x or []', which replaces an explicitly supplied empty list instead of only handling None"
        )

    # Derive the trace for the deliberately narrow canonical form used by Core:
    # def f(x=[]): x.append(<literal>); return x ; print(f()); print(f())
    # This does not execute user code. It only literal-parses the appended scalar.
    trace_match = re.search(
        r"def\s+(?P<fn>[A-Za-z_]\w*)\s*\(\s*(?P<arg>[A-Za-z_]\w*)\s*=\s*\[\s*\]\s*\)\s*:\s*"
        r"(?P<body>[^`\n]{1,180})",
        source_raw,
    )
    expected_outputs = None
    if trace_match:
        fn = trace_match.group("fn")
        arg = trace_match.group("arg")
        body = re.sub(r"\s+", " ", trace_match.group("body").strip())
        body_match = re.fullmatch(
            rf"{re.escape(arg)}\.append\((?P<literal>[^()]+)\)\s*;\s*return\s+{re.escape(arg)}\s*",
            body,
        )
        if body_match:
            try:
                item = ast.literal_eval(body_match.group("literal").strip())
            except (ValueError, SyntaxError):
                item = object()
            if isinstance(item, (str, int, float, bool, type(None))):
                call_count = len(re.findall(
                    rf"print\s*\(\s*{re.escape(fn)}\s*\(\s*\)\s*\)",
                    source_raw,
                    flags=re.IGNORECASE,
                ))
                if 1 <= call_count <= 6:
                    state = []
                    expected_outputs = []
                    for _ in range(call_count):
                        state.append(item)
                        expected_outputs.append(list(state))

    if expected_outputs and len(expected_outputs) >= 2:
        # Successive append calls cannot have identical outputs. Any prose that
        # says "both prints/calls/outputs show ..." contradicts the derived trace
        # regardless of which list literal the model invents.
        if re.search(
            r"\bboth\s+(?:prints?|calls?|outputs?)\b[^.!?]{0,100}(?:show|print|return|are|give|produce)?",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "Python mutable-default follow-up contradicted the derived trace: "
                f"the first call is {expected_outputs[0]}, the second call is {expected_outputs[1]}; "
                "the two calls do not have the same output"
            )

        explicit_pair = re.search(
            r"\bfirst\s+(?:print|call|output)?[^.!?]{0,50}(?P<first>\[[^\]]*\])"
            r"[^.!?]{0,90}\b(?:then|second)\b[^.!?]{0,50}(?P<second>\[[^\]]*\])",
            text_raw,
            flags=re.IGNORECASE,
        )
        if explicit_pair:
            try:
                first_value = ast.literal_eval(explicit_pair.group("first"))
                second_value = ast.literal_eval(explicit_pair.group("second"))
            except (ValueError, SyntaxError):
                first_value = second_value = None
            if (
                first_value is not None
                and second_value is not None
                and (
                    first_value != expected_outputs[0]
                    or second_value != expected_outputs[1]
                )
            ):
                violations.append(
                    "Python mutable-default follow-up stated outputs that contradict the deterministically derived first/second call trace"
                )

    if re.search(
        r"\b(?:doesn['’]?t|does\s+not|won['’]?t|will\s+not)\b[^.!?]{0,100}"
        r"\b(?:create|make)\b[^.!?]{0,80}\b(?:new\s+)?(?:list|object|default)\b"
        r"[^.!?]{0,80}\bbecause\b[^.!?]{0,80}\b(?:inefficient|unnecessary)\b|"
        r"\bbecause\b[^.!?]{0,80}\b(?:inefficient|unnecessary)\b[^.!?]{0,80}"
        r"\b(?:default|list|object)\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "Python mutable-default explanation incorrectly presented efficiency/necessity as the reason defaults are evaluated once"
        )

    if re.search(
        r"\b(?:cache|caches|cached|caching)\b[^.!?]{0,100}\b(?:list|object|default)\b|"
        r"\b(?:save|saving|saves)\s+(?:on\s+)?memory\b",
        text,
        flags=re.IGNORECASE,
    ):
        violations.append(
            "Python mutable-default explanation incorrectly framed default-object reuse as a caching/memory optimisation"
        )

    return list(dict.fromkeys(violations))

def find_scaler_leakage_contradiction_violations(
    user_input: str,
    draft: str,
    conversation=None,
) -> List[str]:
    """Reject incomplete or contradictory data-leakage/scaler explanations.

    General data-leakage tutoring should identify an information-boundary
    violation, not stop at a vague exam analogy. Scaler follow-ups then get
    stricter checks for directionality, code integrity and calibration.
    """
    source_raw = "\n".join([
        str(user_input or ""),
        str(build_recent_user_grounding_context(conversation, max_user_messages=4) or ""),
    ])
    source = source_raw.lower()
    current_user = str(user_input or "").lower()
    raw = str(draft or "")
    text = re.sub(r"\s+", " ", raw.strip()).lower()
    bad: List[str] = []

    # A first-principles explanation of ML data leakage must describe an
    # information boundary: information unavailable to the genuine training
    # process/prediction setting leaks into training, preprocessing or model
    # selection. An exam metaphor alone is not enough for a tutoring request.
    if (
        re.search(r"\bdata\s+leakage\b", current_user)
        and re.search(r"\b(?:machine\s+learning|ml|model)\b", current_user)
        and re.search(r"\b(?:explain|understand|what|why)\b", current_user)
    ):
        has_train_test_boundary = bool(
            re.search(r"\btrain(?:ing)?\b", text)
            and re.search(r"\b(?:test|validation|held[- ]?out)\b", text)
        )
        has_prediction_boundary = bool(re.search(
            r"\b(?:prediction\s+time|future\s+data|future\s+information|target|label|outcome)\b",
            text,
            flags=re.IGNORECASE,
        ))
        has_information_flow = bool(re.search(
            r"\b(?:information|data|statistics?|features?|values?|labels?|outcomes?)\b"
            r"[^.!?]{0,120}\b(?:leak|leaks|leaked|use|uses|using|learn|learns|learned|"
            r"influence|influences|influenced|available|seen|sees)\b|"
            r"\b(?:leak|leaks|leaked|uses?|learns?|influences?|sees?)\b"
            r"[^.!?]{0,120}\b(?:information|data|statistics?|features?|values?|labels?|outcomes?)\b",
            text,
            flags=re.IGNORECASE,
        ))
        if not ((has_train_test_boundary or has_prediction_boundary) and has_information_flow):
            bad.append(
                "data-leakage tutoring answer did not explain the actual information-boundary violation"
            )

        if re.search(
            r"\b(?:performance|accuracy|validation\s+(?:score|performance))\b[^.!?]{0,80}"
            r"\b(?:tanks?|collapses?|fails?)\b[^.!?]{0,35}\b(?:instantly|immediately|always)\b|"
            r"\bmodel\b[^.!?]{0,90}\bjust\s+memor(?:ise|ize|ises|izes|ised|ized|ising|izing)\b"
            r"[^.!?]{0,70}\b(?:answers?|targets?|labels?)\b",
            text,
            flags=re.IGNORECASE,
        ):
            bad.append(
                "data-leakage tutoring answer overstated leakage as guaranteed memorization or immediate real-world performance collapse"
            )


        # A spurious-correlation or distribution-shift example is not, by
        # itself, a leakage example. If the teaching example explains failure
        # only as a seasonal/correlation pattern changing on new data, require
        # an actual information-boundary mechanism in that example (future
        # information, target-derived data, or held-out/test contamination).
        example_match = re.search(
            r"\b(?:for\s+example|suppose|imagine|let['’]?s\s+say)\b"
            r"(?P<example>.{0,700})",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if example_match:
            example = example_match.group("example")
            distribution_shift_shape = bool(re.search(
                r"\b(?:seasonal|spurious)\b[^.!?]{0,60}\b(?:trends?|correlations?)\b|"
                r"\bnew\s+data\b[^.!?]{0,120}\b(?:predictions?|performance|accuracy)\b"
                r"[^.!?]{0,80}\b(?:off|wrong|worse|drop|fail)\b",
                example,
                flags=re.IGNORECASE,
            ))
            leakage_mechanism = bool(re.search(
                r"\b(?:future\s+(?:information|data)|target[- ]derived|label[- ]derived|"
                r"outcome[- ]derived|post[- ]outcome|after\s+the\s+outcome|after\s+the\s+event|"
                r"held[- ]?out\s+(?:test|validation)|test\s+(?:set|data)\b[^.!?]{0,100}"
                r"(?:used|seen|included|fit|influence)|validation\s+(?:set|data)\b[^.!?]{0,100}"
                r"(?:used|seen|included|fit|influence)|unavailable\s+at\s+(?:prediction|inference)\s+time|"
                r"not\s+available\s+at\s+(?:prediction|inference)\s+time)\b",
                example,
                flags=re.IGNORECASE,
            ))
            if distribution_shift_shape and not leakage_mechanism:
                bad.append(
                    "data-leakage tutoring example described distribution shift/spurious correlation without an actual leakage mechanism"
                )

            # If the answer chooses to teach with a concrete example, the
            # example itself must contain the boundary violation. A merely
            # predictive feature (for example a date) is not leakage just
            # because the target is unknown; the leaked information has to be
            # unavailable/target-derived/held-out/post-outcome in the stated
            # workflow.
            concrete_example = bool(re.search(
                r"\b(?:include|including|use|using|feature|column|variable|fit|fitting|train|training)\b",
                example,
                flags=re.IGNORECASE,
            ))
            if concrete_example and not leakage_mechanism:
                bad.append(
                    "data-leakage tutoring concrete example did not identify any information that is unavailable, target-derived, held-out, or post-outcome"
                )

        for unit in re.split(r"(?<=[.!?])\s+", text):
            if not re.search(
                r"\b(?:performance|accuracy|score)\b[^.!?]{0,70}\b(?:tanks?|collapses?|fails?)\b",
                unit,
                flags=re.IGNORECASE,
            ):
                continue
            if not re.search(
                r"\b(?:can|could|may|might|often|sometimes|can\s+appear\s+to|risk)\b",
                unit,
                flags=re.IGNORECASE,
            ):
                bad.append(
                    "data-leakage tutoring answer treated downstream performance collapse as guaranteed rather than a possible consequence"
                )
                break

    scaler_context = bool(
        "scaler" in source
        and re.search(r"train\s*/?\s*test|train(?:ing)?\s+(?:and|or)\s+test", source)
    )
    if not scaler_context:
        return list(dict.fromkeys(bad))

    fit_on_all = bool(re.search(
        r"\b(?:fit|fitting|fit_transform|learns?)\b[^.!?]{0,120}"
        r"\b(?:entire|whole|all|full)\b[^.!?]{0,70}\b(?:dataset|data)\b|"
        r"\b(?:including|uses?)\b[^.!?]{0,50}\btest\s+(?:set|data)\b",
        text,
        flags=re.IGNORECASE,
    ))
    # The live user prompt itself can establish the leaking workflow even when
    # a later short paraphrase says only "before the split".
    if not fit_on_all and re.search(
        r"\bfit(?:ting)?\b[^.!?]{0,60}\bscaler\b[^.!?]{0,80}"
        r"\bbefore\b[^.!?]{0,50}\b(?:train\s*/?\s*test\s+)?split\b",
        source,
        flags=re.IGNORECASE,
    ):
        fit_on_all = True
    if not fit_on_all:
        return list(dict.fromkeys(bad))

    if re.search(r"\b(?:tiny|small|quick|simple|concrete)\s+example\b", current_user, re.IGNORECASE):
        code_blocks_for_example = re.findall(
            r"```(?:python)?\s*\n?(.*?)```",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        has_explicit_numeric_split = bool(
            re.search(
                r"\btrain(?:ing)?\b[^.!?]{0,120}\b-?\d+(?:\.\d+)?\b",
                text,
                flags=re.IGNORECASE,
            )
            and re.search(
                r"\b(?:test|held[- ]?out)\b[^.!?]{0,120}\b-?\d+(?:\.\d+)?\b",
                text,
                flags=re.IGNORECASE,
            )
        )
        has_executed_split = any(
            re.search(r"(?<!from\s)\btrain_test_split\s*\(", block, re.IGNORECASE)
            for block in code_blocks_for_example
        )
        has_natural_language_example = bool(
            re.search(
                r"\b(?:for\s+example|suppose|imagine|let['’]?s\s+say)\b",
                text,
                flags=re.IGNORECASE,
            )
            and re.search(r"\btrain(?:ing)?\b", text, flags=re.IGNORECASE)
            and re.search(r"\b(?:test|held[- ]?out)\b", text, flags=re.IGNORECASE)
            and re.search(r"\b-?\d+(?:\.\d+)?\b", text)
        )
        presented_example_marker = bool(re.search(
            r"(?:\b(?:for\s+example|suppose|imagine|let['’]?s\s+say)\b|\be\.g\.)",
            text,
            flags=re.IGNORECASE,
        ))
        if (
            presented_example_marker
            and not (has_explicit_numeric_split or has_executed_split or has_natural_language_example)
        ):
            bad.append(
                "scaler-leakage tiny-example request used an example marker but never gave a concrete train/test example"
            )
        if code_blocks_for_example and not (has_explicit_numeric_split or has_executed_split):
            bad.append(
                "scaler-leakage tiny example included code but never instantiated an actual train/test split or explicit train/test values"
            )


        # If teaching with executable Python, the snippet itself must be sound
        # enough to demonstrate the concept rather than introducing unrelated
        # runtime errors.
        for block in code_blocks_for_example:
            try:
                tree = ast.parse(block)
            except SyntaxError:
                bad.append(
                    "scaler-leakage code example is syntactically invalid Python"
                )
                continue

            defined = set(dir(builtins))
            assigned_1d_names = set()
            standard_scaler_vars = set()

            def _collect_target_names(node):
                names = set()
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, (ast.Tuple, ast.List)):
                    for elt in node.elts:
                        names.update(_collect_target_names(elt))
                return names

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        defined.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        defined.add(alias.asname or alias.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defined.add(node.name)
                elif isinstance(node, ast.Assign):
                    target_names = set()
                    for target in node.targets:
                        target_names.update(_collect_target_names(target))
                    defined.update(target_names)

                    call = node.value
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "randn"
                        and len(call.args) == 1
                    ):
                        assigned_1d_names.update(target_names)

                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr in {"array", "asarray"}
                        and call.args
                        and isinstance(call.args[0], (ast.List, ast.Tuple))
                        and all(
                            not isinstance(item, (ast.List, ast.Tuple))
                            for item in call.args[0].elts
                        )
                    ):
                        assigned_1d_names.update(target_names)

                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id == "StandardScaler"
                    ):
                        standard_scaler_vars.update(target_names)
                elif isinstance(node, ast.AnnAssign):
                    defined.update(_collect_target_names(node.target))
                elif isinstance(node, (ast.For, ast.AsyncFor)):
                    defined.update(_collect_target_names(node.target))

            loaded = {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            }
            undefined = sorted(
                name for name in loaded
                if name not in defined
                and name not in {"__name__", "__file__", "__package__"}
            )
            if undefined:
                bad.append(
                    "scaler-leakage code example uses undefined name(s): "
                    + ", ".join(undefined[:5])
                )

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"fit", "fit_transform", "transform"}:
                    continue
                if not isinstance(node.func.value, ast.Name):
                    continue
                if node.func.value.id not in standard_scaler_vars:
                    continue
                if not node.args or not isinstance(node.args[0], ast.Name):
                    continue
                if node.args[0].id in assigned_1d_names:
                    bad.append(
                        "scaler-leakage StandardScaler example passes a one-dimensional array where sklearn expects a 2D feature matrix"
                    )
                    break

    if re.search(
        r"\btest\s+set\s+remains?\s+(?:truly\s+)?[\"'“”]?(?:unseen|blind)[\"'“”]?\b|"
        r"\btest\s+set\b[^.!?]{0,60}\bremains?\s+(?:truly\s+)?[\"'“”]?(?:unseen|blind)[\"'“”]?\b",
        text,
        re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer contradicted itself by calling the contaminated test set unseen/blind"
        )

    if re.search(
        r"\b(?:this|that)\s+(?:ensures?|guarantees?|keeps?)\b[^.!?]{0,100}"
        r"\b(?:realistic|honest|not\s+inflated|unbiased|independent)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer claimed the leaking workflow preserves an unbiased/independent evaluation"
        )

    if fit_on_all and re.search(
        r"\b(?:this|that)\s+ensures?\b[^.!?]{0,140}\bno\s+information\b[^.!?]{0,100}\bleaks?\b|"
        r"\btest\s+set\b[^.!?]{0,100}\btransform(?:ed|ing)?\b[^.!?]{0,100}"
        r"\bwithout\b[^.!?]{0,50}\binfluenc(?:e|ing|ed)\b[^.!?]{0,40}\b(?:parameters?|scaler|statistics?)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer contradicted the leaking workflow by claiming the test set no longer influenced the fitted preprocessing"
        )

    if re.search(
        r"\btest\s+set\b[^.!?]{0,100}\b(?:contaminated|leaked|influenced)\b"
        r"[^.!?]{0,100}\b(?:by|from)\b[^.!?]{0,60}\btrain(?:ing)?\s+(?:set|data)\b|"
        r"\bleaks?\s+(?:info(?:rmation)?|data|statistics?)\s+from\s+train(?:ing)?\s+to\s+test\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer reversed the information flow; fitting before the split lets test statistics influence the training preprocessing"
        )

    if re.search(
        r"\bbias(?:es|ing|ed)?\b[^.!?]{0,100}\btrain(?:ing)?\s+set(?:'s)?\b"
        r"[^.!?]{0,100}\b(?:scaling|transform(?:ation)?)\b[^.!?]{0,80}"
        r"\bmatch\b[^.!?]{0,50}\btest\s+set\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer overstated the effect as making training scaling match the test set rather than using parameters influenced by test statistics"
        )

    if re.search(
        r"\b(?:this|that)\s+makes?\b[^.!?]{0,100}\bmodel\b[^.!?]{0,80}"
        r"\bartificially\s+(?:good|better)\b|"
        r"\bmodel\b[^.!?]{0,100}\bartificially\s+(?:good|better)\b",
        text,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\b(?:can|could|may|might)\b[^.!?]{0,100}\bartificially\s+(?:good|better)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer treated improved test performance as guaranteed instead of describing a biased evaluation risk"
        )

    # Catch executable-looking code accidentally placed after an inline comment
    # inside a Python code block. This is a syntax/teaching-quality invariant,
    # not a benchmark phrase check.
    code_blocks = re.findall(
        r"```(?:python)?\s*\n?(.*?)```",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in code_blocks:
        for line in block.splitlines():
            if "#" not in line:
                continue
            before_hash, after_hash = line.split("#", 1)
            if not before_hash.strip():
                continue
            if re.search(
                r"\b[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w*\s*\(|"
                r"\b[A-Za-z_]\w*\.(?:fit|transform|predict|score)\s*\(",
                after_hash,
                flags=re.IGNORECASE,
            ):
                bad.append(
                    "scaler-leakage code example placed executable Python after an inline comment, so the shown code would not run as explained"
                )
                break
        if bad and bad[-1].startswith("scaler-leakage code example placed executable"):
            break

    commented_split = bool(re.search(
        r"(?m)^\s*[^\n]*#.*\bX_train\b[^\n]*\btrain_test_split\s*\(",
        raw,
        flags=re.IGNORECASE,
    ))
    later_uses_split_variables = bool(re.search(
        r"\b(?:[A-Za-z_]\w*\.)?(?:fit|transform|predict|score)\s*\(\s*X_(?:train|test)\b|"
        r"\bX_(?:train|test)(?:_scaled)?\b\s*=",
        raw,
        flags=re.IGNORECASE,
    ))
    if commented_split and later_uses_split_variables:
        bad.append(
            "scaler-leakage code example accidentally commented out the train/test split while later using X_train/X_test"
        )

    # A scaler learns summary parameters such as mean/variance; describing it
    # as memorising the held-out distribution overstates what the preprocessing
    # step actually stores.
    if re.search(
        r"\bscaler\b[^.!?]{0,100}\bmemor(?:ise|ize|ises|izes|ised|ized|ising|izing)\b"
        r"[^.!?]{0,100}\b(?:test|held[- ]?out)\b[^.!?]{0,80}\b(?:data|distribution|set)\b|"
        r"\bmemor(?:ise|ize|ises|izes|ised|ized|ising|izing)\b[^.!?]{0,100}"
        r"\b(?:test|held[- ]?out)\b[^.!?]{0,80}\b(?:data|distribution|set)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer incorrectly described the scaler as memorising the held-out test distribution"
        )

    # Do not describe the bad workflow as fitting on all data and then, in the
    # same explanation, say that the split is scaled only with training-derived
    # statistics. Those are different workflows.
    if fit_on_all and re.search(
        r"\b(?:when|then|so\s+when|after\s+that)\b[^.!?]{0,100}"
        r"\b(?:scale|scaling|transform(?:ed|ing)?)\b[^.!?]{0,80}"
        r"\bonly\b[^.!?]{0,50}\b(?:training|train)\b[^.!?]{0,50}\b(?:stats?|statistics?|parameters?)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer contradicted the leaking workflow by switching to training-only scaling mid-explanation"
        )

    if re.search(
        r"\b(?:evaluation|estimate|assessment|result|results|metric|metrics|score|performance)\b"
        r"[^.!?]{0,70}\b(?:is|are|becomes?|gets?)\b[^.!?]{0,35}"
        r"\b(?:biased\s+upward|upwardly\s+biased|overly\s+optimistic|artificially\s+inflated|inflated)\b",
        text,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\b(?:can|could|may|might|risk|potential(?:ly)?)\b[^.!?]{0,120}"
        r"\b(?:biased\s+upward|optimistic|inflated|bias)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer treated the direction of evaluation bias as guaranteed rather than a possible optimistic bias"
        )

    if re.search(
        r"\b(?:performance|score|metric)\b[^.!?]{0,70}\b(?:looks?|seems?|is|are)\b"
        r"[^.!?]{0,50}\b(?:great|good|amazing|high)\b[^.!?]{0,45}\b(?:but\s+)?(?:fake|invalid|meaningless)\b",
        text,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\b(?:can|could|may|might|risk|potential(?:ly)?)\b[^.!?]{0,100}"
        r"\b(?:optimistic|inflated|biased|misleading)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer treated a favourable performance distortion as guaranteed rather than a possible evaluation bias"
        )

    if re.search(
        r"\b(?:which|this|that)\s+(?:artificially\s+)?(?:inflates?|inflating)\b[^.!?]{0,110}\b(?:performance|metrics?|score)\b|"
        r"\b(?:inflates?|inflating)\b[^.!?]{0,110}\b(?:model(?:['’]s)?\s+)?(?:performance|metrics?|score)\b|"
        r"\b(?:performance|metrics?|score)\s+(?:is|are)\s+artificially\s+inflated\b|"
        r"\b(?:lead(?:s|ing)?|cause(?:s|d|ing)?|make(?:s|ing)?)\b[^.!?]{0,100}\boverly\s+optimistic\b",
        text,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\b(?:can|could|may|might|risk|potential(?:ly)?)\b[^.!?]{0,120}"
        r"\b(?:inflate|inflated|optimistic|bias)\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer treated optimistic/inflated evaluation as guaranteed rather than a possible bias"
        )

    if re.search(
        r"\b(?:lead(?:s|ing)?\s+to|cause(?:s|d|ing)?)\b[^.!?]{0,80}\boverfitting\b",
        text,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\b(?:can|could|may|might|risk|potential(?:ly)?|contribute)\b[^.!?]{0,100}\boverfitting\b",
        text,
        flags=re.IGNORECASE,
    ):
        bad.append(
            "scaler-leakage answer treated overfitting as a guaranteed consequence of preprocessing leakage"
        )

    # Leakage can bias an evaluation, but contamination does not guarantee
    # that the measured score becomes numerically higher.
    for unit in re.split(r"(?<=[.!?])\s+|\n+", text):
        if not re.search(
            r"\b(?:score|performance|estimate|accuracy)\b[^.!?]{0,80}"
            r"\b(?:inflated|higher|biased\s+upward|optimistic)\b",
            unit,
            flags=re.IGNORECASE,
        ):
            continue
        if not re.search(
            r"\b(?:can|could|may|might|often|risk|potential(?:ly)?)\b",
            unit,
            flags=re.IGNORECASE,
        ):
            bad.append(
                "scaler-leakage answer treated score inflation as guaranteed rather than a possible bias"
            )
            break

    # A tiny technical example must not introduce code that fails before it
    # demonstrates the requested concept. Detect literal one-class slices fed
    # into a generated classifier fit.
    if re.search(r"\b(?:logisticregression|classifier)\b", text, flags=re.IGNORECASE):
        y_match = re.search(
            r"\by\s*=\s*(?:np\.)?array\s*\(\s*\[(?P<body>[^\]]+)\]\s*\)",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        fit_match = re.search(
            r"\.fit\s*\([^,]+,\s*y\s*\[:\s*(?P<n>\d+)\s*\]\s*\)",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if y_match and fit_match:
            try:
                y_values = ast.literal_eval("[" + y_match.group("body") + "]")
                n = int(fit_match.group("n"))
                train_labels = list(y_values[:n])
            except Exception:
                train_labels = []
            if train_labels and len(set(train_labels)) < 2:
                bad.append(
                    "scaler-leakage example trains a classifier on only one target class, so the example code would fail"
                )

    # Tiny numeric examples are useful only if their own arithmetic is sound.
    # When a draft explicitly lists simple train/test values and then states a
    # fitted mean, verify that mean against those same values instead of
    # trusting model arithmetic.
    def _listed_numbers(name):
        patterns = [
            rf"\b{re.escape(name)}\s*=\s*(\[[^\n]+\])",
            rf"(?mi)^\s*[-*]?\s*{re.escape(name)}\s*:\s*(\[[^\n]+\])",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                return [
                    float(item)
                    for item in re.findall(r"-?\d+(?:\.\d+)?", match.group(1))
                ]
        return []

    train_values = _listed_numbers("train")
    test_values = _listed_numbers("test")
    if train_values and test_values:
        combined_values = train_values + test_values

        def _expected_stat(context, values_train, values_all):
            if re.search(
                r"train\s*\+\s*test|entire\s+dataset|whole\s+dataset|"
                r"all\s+(?:\d+|five|four|three)\s+(?:points|values|samples)|"
                r"all\s+(?:the\s+)?(?:data|samples|points|values)",
                context,
                flags=re.IGNORECASE,
            ):
                return values_all
            if re.search(
                r"training\s+(?:set|values|points)|train(?:ing)?\s+only|"
                r"just\s+(?:the\s+)?(?:\d+|three|four|five)\s+training|"
                r"fit(?:ted)?\s+(?:the\s+)?scaler\s+on\s+(?:the\s+)?train",
                context,
                flags=re.IGNORECASE,
            ):
                return values_train
            return None

        for mean_match in re.finditer(
            r"\bmean\s*=\s*(-?\d+(?:\.\d+)?)",
            raw,
            flags=re.IGNORECASE,
        ):
            claimed = float(mean_match.group(1))
            context = raw[max(0, mean_match.start() - 260):mean_match.end() + 220].lower()
            values = _expected_stat(context, train_values, combined_values)
            if values:
                expected = sum(values) / len(values)
                if abs(claimed - expected) > 0.02:
                    bad.append(
                        "scaler-leakage numeric example stated a mean inconsistent with its own listed values"
                    )
                    break

        # sklearn StandardScaler uses population variance (ddof=0). Tiny
        # examples often accidentally quote sample standard deviation instead,
        # which teaches the wrong transformation even though the leakage idea
        # itself is correct.
        for std_match in re.finditer(
            r"\b(?:std|standard\s+deviation)\s*(?:=|is)\s*(?:≈|~)?\s*(-?\d+(?:\.\d+)?)",
            raw,
            flags=re.IGNORECASE,
        ):
            claimed = float(std_match.group(1))
            context = raw[max(0, std_match.start() - 260):std_match.end() + 220].lower()
            values = _expected_stat(context, train_values, combined_values)
            if values:
                mean = sum(values) / len(values)
                expected = math.sqrt(
                    sum((item - mean) ** 2 for item in values) / len(values)
                )
                if abs(claimed - expected) > max(0.03, expected * 0.04):
                    bad.append(
                        "scaler-leakage numeric example stated a StandardScaler standard deviation inconsistent with its own listed values"
                    )
                    break

    return list(dict.fromkeys(bad))

def find_ai_job_market_answer_violations(
    user_input: str,
    draft: str,
) -> List[str]:
    """Require AI-job answers to address jobs/roles rather than adjacent market hype."""
    user = re.sub(r"\s+", " ", str(user_input or "").lower())
    if not (
        re.search(r"\bai\b", user)
        and re.search(r"\b(?:replace|replacement|jobs?|roles?|employment|hiring)\b", user)
        and re.search(r"\b(?:cyber|cybersecurity|security)\b", user)
    ):
        return []
    text = re.sub(r"\s+", " ", str(draft or "").lower())
    if not re.search(r"\b(?:jobs?|roles?|employment|hiring|replace|replacement|automation|tasks?)\b", text):
        return [
            "AI/cyber labour answer discussed adjacent market/infrastructure claims without addressing jobs or role replacement"
        ]
    if re.search(r"\b(?:every|all)\s+(?:cyber|cybersecurity|security)\s+(?:job|role)s?\b", text) and not re.search(
        r"\b(?:no evidence|not enough evidence|unsupported|uncertain|cannot|can't|don['’]?t know|forecast)\b",
        text,
    ):
        return [
            "AI/cyber labour answer treated a universal job-replacement claim as established"
        ]
    return []


def find_explicit_user_constraint_violations(
    user_input: str,
    draft: str,
) -> List[str]:
    """Preserve explicit negative constraints from Oliver's current turn.

    This is intentionally conservative: it only blocks personal assumptions
    Oliver explicitly told Mairon not to make. General trade-off discussion is
    still allowed when it does not assign those preferences/facts to Oliver.
    """
    user = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
    text = re.sub(r"\s+", " ", str(draft or "").strip()).lower()
    violations: List[str] = []

    if re.search(
        r"\b(?:don['’]?t|do\s+not)\s+(?:invent|assume|infer)\b[^.!?]{0,80}\b(?:my\s+)?budget\b",
        user,
        flags=re.IGNORECASE,
    ):
        personalised_budget = bool(re.search(
            r"\b(?:your\s+budget|if\s+you(?:'re|\s+are)\s+on\s+a\s+budget|"
            r"if\s+you(?:'re|\s+are)\s+willing\s+to\s+pay|if\s+you\s+can\s+afford|"
            r"if\s+you\s+don['’]?t\s+mind\s+paying|"
            r"you\s+(?:value|care\s+about|prioriti[sz]e)\s+(?:saving\s+money|cost)|"
            r"whether\s+you\s+value\s+[^.!?]{0,40}saving\s+money)\b",
            text,
            flags=re.IGNORECASE,
        ))
        explicit_budget_noninference = bool(re.search(
            r"\b(?:i\s+)?(?:won['’]?t|will\s+not|don['’]?t|do\s+not)\s+"
            r"(?:infer|assume|invent)\b[^.!?]{0,30}\b(?:your\s+)?budget\b",
            text,
            flags=re.IGNORECASE,
        ))
        if personalised_budget and not explicit_budget_noninference:
            violations.append(
                "answer inferred Oliver's budget/cost preference despite an explicit no-budget-assumption constraint"
            )

    if re.search(
        r"\b(?:don['’]?t|do\s+not)\s+(?:invent|assume|infer)\b[^.!?]{0,100}"
        r"\b(?:which\s+one\s+i\s+(?:already\s+)?own|what\s+i\s+(?:already\s+)?own|my\s+current\s+(?:device|computer|machine))\b",
        user,
        flags=re.IGNORECASE,
    ):
        personalised_ownership = bool(re.search(
            r"\b(?:you|your)\s+(?:already\s+)?(?:own|have|use|run)\b[^.!?]{0,50}"
            r"\b(?:mac(?:os)?|windows|pc|laptop|machine|computer)\b|"
            r"\b(?:your\s+mac|your\s+windows\s+(?:pc|machine|laptop|computer))\b",
            text,
            flags=re.IGNORECASE,
        ))
        explicit_ownership_noninference = bool(re.search(
            r"\b(?:i\s+)?(?:won['’]?t|will\s+not|don['’]?t|do\s+not)\s+"
            r"(?:infer|assume|invent)\b[^.!?]{0,45}\b(?:own|current\s+device|current\s+machine)\b",
            text,
            flags=re.IGNORECASE,
        ))
        if personalised_ownership and not explicit_ownership_noninference:
            violations.append(
                "answer inferred which platform/device Oliver owns despite an explicit no-ownership-assumption constraint"
            )

    if re.search(
        r"\b(?:manga\b[^.!?]{0,80}\bnot\s+(?:the\s+)?anime|keep\s+(?:the\s+)?(?:two|manga\s+and\s+anime)\s+separate)\b",
        user,
        flags=re.IGNORECASE,
    ):
        if re.search(
            r"\banime(?:['’]s)?\b[^.!?]{0,100}\b(?:catch(?:es)?\s+up|sequel|future\s+self|better|worse|ignore|watch|episode|adaptation|pacing|filler|art|animation|ending|source\s+material|team|studio|version|character|plot|story|antics|comparable|add(?:ed|s|ing)?|chang(?:ed|es|ing)|remov(?:ed|es|ing)|cut(?:s|ting)?)\b|"
            r"\b(?:pacing|filler|watch|episode|adaptation|animation|team|studio|version|character|plot|story|antics)\b[^.!?]{0,80}\banime\b|"
            r"\b(?:different|alternate|changed?)\s+ending\b|"
            r"\b(?:weird|bad|good|better|worse|different)\s+adaptation\b|"
            r"\badaptation\s+(?:choice|change|difference|ending)\b|"
            r"\banimated\b[^.!?]{0,80}\b(?:nonsense|mess|version|adaptation)\b|"
            r"\b(?:show|series)(?:['’]s)?\b[^.!?]{0,90}\b(?:pacing|animation|episodes?|adaptation|version|art|ending|story|plot)\b|"
            r"\b(?:pacing|animation|episodes?|adaptation|version|art|ending|story|plot)\b[^.!?]{0,90}\b(?:show|series)(?:['’]s)?\b|"
            r"\b(?:compared\s+to|comparable\s+to|versus|vs\.?|against)\b[^.!?]{0,80}\b(?:anime|show|series)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "answer drifted into anime discussion after Oliver explicitly locked the conversation to manga as a separate medium"
            )

    # Preserve an explicitly mentioned competing obligation. If Oliver says he
    # also has uni/work/study obligations, a recommendation must not dismiss
    # that same obligation as something that can simply wait.
    obligation_terms = (
        "uni", "university", "work", "study", "studying",
        "assignment", "homework", "school", "class",
    )
    for term in obligation_terms:
        if not re.search(
            rf"\b(?:i\s+(?:have|got)\b[^.!?]{{0,55}}\b{re.escape(term)}\b[^.!?]{{0,45}}\b(?:to\s+do|to\s+finish|to\s+get\s+done)|"
            rf"\b{re.escape(term)}\b[^.!?]{{0,45}}\b(?:to\s+do|to\s+finish|to\s+get\s+done))\b",
            user,
            flags=re.IGNORECASE,
        ):
            continue
        if re.search(
            rf"\b{re.escape(term)}\b[^.!?]{{0,35}}\bcan\s+wait\b|"
            rf"\bput\b[^.!?]{{0,35}}\b{re.escape(term)}\b[^.!?]{{0,35}}\b(?:aside|off)\b",
            text,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "recommendation dismissed a competing obligation Oliver explicitly said he still needs to do"
            )
            break

    return list(dict.fromkeys(violations))


def find_self_evaluation_overreach_violations(
    user_input: str,
    draft: str,
) -> List[str]:
    """Keep Mairon self-evaluation about Mairon, not invented Oliver habits.

    A prompt such as "reckon you're becoming useful?" may be answered from
    explicitly supplied development context.  It is not permission to invent a
    history of Oliver wasting time, relying on Mairon, or making recurring
    questionable decisions.
    """
    user = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
    if not re.search(
        r"\b(?:reckon|think)\b[^?]{0,55}\b(?:you(?:'re| are)|you)\b"
        r"[^?]{0,70}\b(?:useful|better|improving|improved|competent|ready|solid)\b",
        user,
        flags=re.IGNORECASE,
    ):
        return []

    text = str(draft or "").replace("’", "'")
    if re.search(
        r"\byou\s+(?:always|constantly|usually|keep)\b|"
        r"\b(?:how\s+much|the\s+amount\s+of)\s+time\s+you\s+(?:waste|spend)\b|"
        r"\byour\s+(?:questionable|bad|terrible|stupid)\s+decisions?\b|"
        r"\byou\s+(?:need|rely\s+on|depend\s+on)\s+me\b",
        text,
        flags=re.IGNORECASE,
    ):
        return [
            "self-evaluation invented unrelated recurring behaviour/history about Oliver"
        ]

    return []


def find_factual_personal_observation_violations(
    user_input: str,
    draft: str,
    core_answer_contract,
) -> List[str]:
    """Block decorative claims that Mairon has repeatedly observed Oliver.

    Stable factual answers should explain the subject, not invent a history of
    watching Oliver's habits.  If prior conversation really matters, Core can
    refer to what Oliver *said* rather than claiming direct observation.
    """
    runtime = coerce_answer_contract_runtime(core_answer_contract)
    if runtime is None or runtime.intent != "factual_question":
        return []

    text = str(draft or "").replace("’", "'")
    if re.search(
        r"\b(?:i(?:'ve| have)?\s+noticed|i\s+keep\s+noticing|i\s+keep\s+seeing|"
        r"i(?:'ve| have)\s+seen\s+you|don['’]?t\s+think\s+i\s+haven['’]?t\s+noticed)\b"
        r"[^.!?]{0,140}\b(?:you|your)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return [
            "factual answer invented repeated personal observation/history about Oliver"
        ]

    return []


def find_source_provenance_honesty_violations(
    user_input: str,
    draft: str,
) -> List[str]:
    """Reject evasive source-use claims when Oliver explicitly asks what was loaded."""
    user = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
    if not re.search(
        r"\b(?:actually|really)\s+(?:load|loaded|open|opened|read|browse|browsed)\b|"
        r"\bif\s+you\s+didn['’]?t\s+actually\s+(?:load|open|read|browse)\b",
        user,
        flags=re.IGNORECASE,
    ):
        return []

    text = re.sub(r"\s+", " ", str(draft or "").strip()).lower()
    if re.search(
        r"\bi\s+(?:didn['’]?t|did\s+not)\s+need\s+to\s+[\"'“”]?\s*(?:load|open|read|browse)\s*[\"'“”]?\b|"
        r"\bno\s+need\s+to\s+[\"'“”]?\s*(?:load|open|read|browse)\s*[\"'“”]?\b",
        text,
        flags=re.IGNORECASE,
    ):
        return [
            "source-provenance answer evaded whether the source was actually retrieved/read"
        ]

    explicit_use = bool(re.search(
        r"\bi\s+(?:actually\s+)?(?:retrieved|loaded|opened|read|checked|browsed|accessed)\b|"
        r"\bi\s+(?:did|didn['’]?t|couldn['’]?t|wasn['’]?t\s+able\s+to)\b[^.!?]{0,35}"
        r"\b(?:load|open|read|browse|retrieve|access)\b",
        text,
        flags=re.IGNORECASE,
    ))
    if not explicit_use:
        return [
            "source-provenance answer did not explicitly say whether the source was actually retrieved/read"
        ]
    return []


def build_diagnostic_reasoning_fallback(
    user_input: str,
    conversation=None,
) -> Optional[str]:
    """Useful bounded fallback for common diagnostic follow-ups.

    It reasons only from Oliver's supplied measurements plus durable mechanism
    knowledge. It deliberately keeps unmeasured causes open rather than turning
    a safe rejection into either a hallucination or a generic refusal.
    """
    current = re.sub(r"\s+", " ", str(user_input or "").strip())
    recent_user = []
    for item in reversed(list(conversation or [])):
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        else:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
        if str(role or "").lower() != "user":
            continue
        value = re.sub(r"\s+", " ", str(content or "").strip())
        if value:
            recent_user.append(value)
        if len(recent_user) >= 4:
            break
    recent_user.reverse()
    context = "\n".join(recent_user + [current])
    low = context.lower()
    current_low = current.lower()

    wifi_context = bool(
        re.search(r"\b(?:wi[- ]?fi|wireless|mesh|router|node|mbps|gbps)\b", low)
        and re.search(r"\b(?:upstairs|wireless|wi[- ]?fi|mesh)\b", low)
    )
    if wifi_context:
        if re.search(
            r"\bwhat\s+would\s+you\s+(?:test|check)\s+first\b|"
            r"\bwhat\s+should\s+i\s+(?:test|check)\s+first\b",
            current_low,
        ):
            return (
                "Test the same phone right next to the main Wi-Fi source/router with the same speed test, "
                "then compare that result with upstairs. If the phone is fast near the source but slow upstairs, "
                "that shifts suspicion away from a broadband-wide speed cap and toward the local Wi-Fi/mesh path; "
                "it still does not tell you whether the cause is signal, roaming, backhaul, or interference."
            )

        if re.search(r"\bwhat\s+does\s+that\s+rule\s+out\b", current_low) and re.search(
            r"\bphone\b[^\n]{0,100}\b(?:main\s+)?(?:mesh\s+)?node\b|"
            r"\b(?:main\s+)?(?:mesh\s+)?node\b[^\n]{0,100}\bphone\b",
            low,
        ):
            return (
                "It rules out the phone being inherently limited to the slow upstairs speed and makes a total "
                "main-node/router failure or broadband-wide cap much less likely, because the same phone is fast "
                "next to the main node. It does not rule out the upstairs Wi-Fi/mesh path, roaming/association, "
                "backhaul, interference, or distance; those are still separate possibilities."
            )

        if re.search(r"\b(?:pay|upgrade)\b[^?]{0,50}\bisp\b|\bisp\b[^?]{0,50}\b(?:pay|upgrade)\b", current_low):
            return (
                "Based on the readings you gave me, paying the ISP more is unlikely to fix the upstairs slowdown: "
                "the same setup can deliver high throughput near the main node while the phone is slow upstairs. "
                "That points to the local Wi-Fi/mesh path, but the readings still do not identify whether the cause "
                "is signal, roaming, backhaul, interference, or something else in that local path."
            )

    if re.search(r"\b(?:vrr|variable\s+refresh(?:\s+rate)?)\b", low, re.IGNORECASE):
        if re.search(r"\bwhy\b[^?]{0,90}\bflicker\b|\bflicker\b[^?]{0,90}\bwhy\b", current_low):
            return (
                "VRR can be related because changing refresh timing with frame delivery can expose luminance/gamma "
                "instability, especially when frame rate fluctuates or approaches the VRR range limits. Dark scenes "
                "can make that flicker easier to notice, but VRR being enabled does not by itself prove the display is "
                "healthy or that VRR is the only cause."
            )

        if re.search(r"\bcould\s+it\s+still\s+be\s+vrr\b|\bdark\s+scenes?\b", current_low):
            return (
                "Yes, it could still be VRR. Dark scenes can make small luminance/gamma changes from variable-refresh "
                "behaviour easier to see, so dark-only flicker is compatible with VRR, but it does not prove VRR is "
                "the root cause. The clean isolation test is the same scene with VRR on versus off under similar frame-rate conditions."
            )

    return None


def build_debate_continuation_fallback(
    user_input: str,
    conversation=None,
) -> str:
    """Substantive fallback for an explicit request for a counterargument."""
    recent_user = []
    for item in reversed(list(conversation or [])):
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        else:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
        if str(role or "").lower() != "user":
            continue
        value = re.sub(r"\s+", " ", str(content or "").strip())
        if value:
            recent_user.append(value)
        if len(recent_user) >= 3:
            break
    context = " ".join(list(reversed(recent_user)) + [str(user_input or "")]).lower()

    if re.search(r"\b(?:long|short)\b", context) and re.search(r"\b(?:arc|manga|pacing|setup|payoff)\b", context):
        return (
            "Counterargument: shorter arcs can hit harder because tighter pacing concentrates the setup and payoff, "
            "leaves less room for repetition, and can make the climax feel sharper. Long arcs gain room for depth, "
            "but they also carry a bigger risk of bloat or diluted momentum."
        )

    return (
        "A reasonable counterargument is that the alternative can trade depth for concentration: less setup can mean "
        "less drag, tighter pacing, and a sharper payoff. That does not automatically make it better, but it is the "
        "strongest case against simply agreeing with the original position."
    )


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
    actually supply. Factual questions are intentionally excluded here: their
    public-world authority is handled by the factual-focus/public-evidence
    validators instead of this conversation-grounding verifier.
    """

    if not contract_forbids_new_factual_claims(
        core_answer_contract
    ):
        return False

    intent = contract_intent(
        core_answer_contract
    )

    epistemic_mode = (
        contract_epistemic_mode(
            core_answer_contract
        )
    )

    if (
        (
            intent == "share_opinion"
            and epistemic_mode
            == "public_source_verified_opinion"
        )
        or (
            intent == "consequential_advice"
            and epistemic_mode
            == "public_source_verified_advice"
        )
    ):
        # Evidence-backed conversational opinions and consequential advice are
        # verified against the dedicated public-source packet later in the
        # provider. The ordinary Core verifier does not receive that packet and
        # would therefore falsely reject supported external facts/procedures.
        return False

    if intent in {
        "acknowledge",

        # Factual questions use a different authority model:
        # - stable_model_knowledge may legitimately use local model knowledge;
        # - public_source_verified is checked against the dedicated retrieved
        #   evidence packet by the public factual verifier.
        #
        # The generic source-locked Core verifier only sees the user turn,
        # recent user context, and Answer Contract. Letting it police factual
        # answers therefore creates false rejections for evidence-backed names
        # and facts (for example, a CEO name retrieved from public sources).
        # Personal/conversation-history fidelity remains enforced separately by
        # verify_factual_focus_fidelity().
        "factual_question",
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
        "- For a share_opinion turn, generic evaluative reasoning about an abstract "
        "idea, trade-off, or distinction is also not an external-world factual claim. "
        "Mairon may reason about a user-supplied comparison without needing citation-style "
        "support. This does NOT permit invented named entities, canon, personal history, "
        "concrete events, measurements, or current-world facts.\n"
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
        "- On troubleshooting/diagnostic turns, also police claims about Oliver's ACTUAL setup: "
        "do not invent bands, channel widths, access points, backhaul state, wall/floor materials, "
        "topology, device configuration, or measurements that Oliver did not supply. General "
        "possibilities may be framed as possibilities, but they are not observations about his setup.\n"
        "- A reading beside one node/device does not prove the state of an unmeasured path/component. "
        "Distinguish what the measurement rules out from what remains only a hypothesis.\n"
        "- If Oliver explicitly says an endpoint is wired, reject a draft that assigns that endpoint "
        "a Wi-Fi channel/band as though it were observed.\n"
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



def _extract_explicit_missing_items(text: str) -> Optional[str]:
    """Compatibility rendering of Core's normalized user-authored omissions.

    The initial fallback and USER-only follow-up share this extraction; neither
    can infer a requirement or copy a trailing request into a material label.
    """
    missing = extract_missing_inputs(text)
    return missing.description if missing is not None else None


def build_insufficient_user_context_fallback(user_input: str) -> str:
    """Fail closed without inventing the private/task-specific missing input."""
    missing = _extract_explicit_missing_items(user_input)
    if missing:
        return (
            "I can't determine that reliably yet because you haven't given me "
            + missing
            + "."
        )
    if re.search(r"\b(?:forgot|didn['’]?t|did\s+not)\b.{0,40}\b(?:attach|upload)\b", str(user_input or ""), re.I):
        return "I can't inspect it until you actually attach or upload it."
    return (
        "I can't determine that reliably from the information you've supplied yet. "
        "Give me the missing task-specific detail and I'll use that rather than guess."
    )


def build_verification_declined_fallback() -> str:
    """Truthful fallback when the user forbids the lookup needed for a live fact."""
    return (
        "I can't give you a reliable exact current answer without verifying it, "
        "and you explicitly told me not to browse, so I won't guess."
    )


def build_stolen_session_security_fallback(
    user_input: str,
) -> Optional[str]:
    """Bounded deterministic explanation for stolen authenticated sessions.

    The validator for this concept can legitimately reject every Qwen draft.
    When that happens, Core must still be able to answer the stable security
    concept without exposing an internal/evidence-limit fallback.

    This is not a generic cyber answer generator. It activates only for the
    tightly bounded stolen-session credential context recognised by
    _is_stolen_session_credential_context().
    """
    if not _is_stolen_session_credential_context(
        user_input
    ):
        return None

    current = re.sub(
        r"\s+",
        " ",
        str(
            user_input
            or ""
        ).strip(),
    ).lower()

    asks_about_mfa = bool(
        re.search(
            r"\b(?:mfa|2fa|two[- ]factor|multi[- ]factor|"
            r"multifactor|two[- ]step|authenticator)\b",
            current,
            flags=re.IGNORECASE,
        )
    )

    if asks_about_mfa:
        return (
            "No — MFA protects the authentication/login step, but turning it on "
            "does not retroactively invalidate an already-stolen authenticated "
            "session credential. If the copied session is still valid, stopping "
            "its reuse requires the service to revoke or invalidate that session "
            "server-side (or for it to expire); clearing only the victim browser's "
            "local cookie does not revoke the attacker's copy."
        )

    return (
        "An already-copied authenticated session credential is a session-control "
        "problem, not the same thing as a new login. Controls such as MFA can protect "
        "future authentication, but a stolen session that is still valid must be "
        "revoked or invalidated server-side (or expire); clearing only the victim "
        "browser's local cookie does not revoke the attacker's copy."
    )


def build_stable_model_knowledge_fallback(
    user_input: str,
    conversation=None,
) -> Optional[str]:
    """Return a deterministic fallback for narrow stable concepts we can teach safely.

    This is deliberately not a generic encyclopedia fallback. It exists for
    stable concepts where acceptance guards may reject repeated model drafts
    but Core can still provide a bounded, technically correct explanation.

    Any concept-specific acceptance guard that can reject every model draft
    should have a matching bounded fallback here (or through a helper called
    here), so Core never replaces an answerable stable fact with internal
    evidence-limit language.
    """
    current = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()

    stolen_session_fallback = (
        build_stolen_session_security_fallback(
            user_input
        )
    )

    if stolen_session_fallback is not None:
        return stolen_session_fallback

    if (
        re.search(r"\btcp\b", current)
        and re.search(r"\budp\b", current)
        and re.search(r"\b(?:handshake|connectionless|connection[- ]oriented)\b", current)
    ):
        return (
            "TCP is connection-oriented and establishes a connection with a three-way handshake. "
            "UDP is connectionless and does not use a connection-establishment handshake; it sends "
            "datagrams without first establishing a TCP-style session."
        )

    if (
        re.search(r"\bdata\s+leakage\b", current)
        and re.search(r"\b(?:machine\s+learning|ml|model)\b", current)
        and re.search(r"\b(?:explain|understand|what|why)\b", current)
    ):
        return (
            "Data leakage happens when information that should be unavailable during training "
            "or evaluation leaks into the model-building process — for example, held-out test/validation "
            "data, future information, or target-derived features. That breaks the independence of the "
            "evaluation and can make measured performance too optimistic, so keep train/validation/test "
            "boundaries clean and fit preprocessing only on the training data."
        )

    if (
        re.search(r"\bwired\b[^.!?]{0,90}\b(?:mbps|gbps)\b", current)
        and re.search(r"\bphone\b", current)
        and re.search(r"\b(?:wi[- ]?fi|wireless|mesh|router|node|upstairs|downstairs|room)\b", current)
        and re.search(r"\b(?:what|which)\b[^?]{0,55}\b(?:test|check|try)\b[^?]{0,30}\bfirst\b", current)
    ):
        return (
            "First, test the same phone close to the main Wi-Fi/mesh source and compare that with the problem location. "
            "That isolates the local wireless path from the broadband connection and the phone itself before you change "
            "bands, channels, configuration, or buy new hardware."
        )

    return None


def build_user_context_reasoning_fallback(
    user_input: str,
    conversation=None,
) -> str:
    """Useful last-resort response for a bounded USER-authored task continuation.

    Rejected model drafts must never surface an internal guardrail diagnostic.
    This extracts only material Oliver explicitly said was missing in prior USER
    turns; it does not trust prior assistant prose or invent a rubric/attachment.
    """
    current = str(user_input or "")
    recent_user_texts = []
    for item in reversed(list(conversation or [])):
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        else:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
        if str(role or "").lower() != "user":
            continue
        value = re.sub(r"\s+", " ", str(content or "").strip())
        if value:
            recent_user_texts.append(value)
        if len(recent_user_texts) >= 4:
            break
    recent_user_texts.reverse()
    user_context = "\n".join(recent_user_texts + [current])

    if re.search(
        r"\bwhat\s+do\s+(?:u|you)\s+need\s+from\s+me\b|"
        r"\bwhat\s+should\s+i\s+(?:send|attach|upload|provide)\b|"
        r"\bwhat\s+do\s+i\s+need\s+to\s+(?:send|attach|upload|provide)\b",
        current,
        flags=re.IGNORECASE,
    ):
        missing = resolve_missing_inputs(conversation, user_input=current)
        if missing is not None:
            return "Send me " + missing.description + ". That's what I need to check it properly."

    if (
        re.search(r"def\s+[A-Za-z_]\w*\s*\([^)]*=\s*\[\s*\]", user_context)
        and re.search(r"\bwhy\b|\bnew\s+list\b|\bdefault\b", current, re.IGNORECASE)
    ):
        return (
            "Python evaluates that default expression once when the function is defined, "
            "and the resulting list is stored with the function's default arguments. "
            "Calling the function again without an argument reuses the same list; it is not a closure variable."
        )

    if (
        "scaler" in user_context.lower()
        and re.search(r"train\s*/?\s*test", user_context, re.IGNORECASE)
        and re.search(r"\bexample\b", current, re.IGNORECASE)
    ):
        return (
            "Tiny example: if your training values are 0 and 10 but the held-out test value is 100, "
            "fitting the scaler on all three lets 100 influence the mean/scale used for training. "
            "Fit the scaler on the training values only, then use those learned parameters to transform the test value."
        )

    if (
        "scaler" in user_context.lower()
        and re.search(r"train\s*/?\s*test", user_context, re.IGNORECASE)
    ):
        return (
            "Fit the scaler on the training set only, because fitting it before the split lets held-out test statistics "
            "influence the preprocessing used for training. That breaks the independence of the evaluation and can make "
            "the reported performance too optimistic; transform the test set using only the scaler learned from training data."
        )

    # A bounded pairwise technical comparison does not require personal budget
    # or ownership facts when Oliver has already supplied the comparison and
    # the criteria. If model drafts are rejected, stay useful rather than
    # treating those deliberately-withheld personal details as missing inputs.
    user_context_lower = user_context.lower()
    mac_windows_frame = bool(
        re.search(r"\bmac(?:os)?\s+(?:vs\.?|versus)\s+windows\b", user_context_lower)
        or re.search(r"\bwindows\s+(?:vs\.?|versus)\s+mac(?:os)?\b", user_context_lower)
    )
    technical_criteria = bool(re.search(
        r"\b(?:python|linux\s+vms?|virtual\s+machines?|network(?:ing|s)?|wsl2?|unix)\b",
        current,
        flags=re.IGNORECASE,
    ))
    if mac_windows_frame and technical_criteria:
        return (
            "You gave enough constraints to compare them without knowing your budget or which one you own. "
            "For Python, both are strong. macOS gives you a Unix/POSIX-style shell and tooling natively; "
            "Windows gives you native Windows tooling plus WSL2 for a Linux environment. Both can support Linux-VM workflows, "
            "although exact guest/architecture support depends on the hardware and hypervisor. For networking work, macOS is convenient "
            "for Unix-oriented CLI workflows, while Windows is more direct when you need Windows-specific networking, Active Directory, "
            "or enterprise tooling. Neither is universally better for the criteria you listed."
        )

    if (
        re.search(r"\b(?:pay|upgrade)\b[^?]{0,50}\bisp\b|\bisp\b[^?]{0,50}\b(?:pay|upgrade)\b", current, re.IGNORECASE)
        and re.search(r"\bwired\b[^\n]{0,80}\b(?:mbps|gbps)\b", user_context, re.IGNORECASE)
        and (
            re.search(r"\b(?:main\s+)?(?:mesh\s+)?node\b[^\n]{0,80}\b(?:mbps|gbps)\b", user_context, re.IGNORECASE)
            or re.search(r"\b(?:mbps|gbps)\b[^\n]{0,80}\b(?:main\s+)?(?:mesh\s+)?node\b", user_context, re.IGNORECASE)
            or re.search(r"\b\d+(?:\.\d+)?\s*(?:mbps|gbps)\b[^\n]{0,80}\b(?:main\s+)?(?:mesh\s+)?node\b", user_context, re.IGNORECASE)
            or re.search(r"\b\d{2,4}(?:\.\d+)?\b[^\n]{0,55}\b(?:main\s+)?(?:mesh\s+)?node\b", user_context, re.IGNORECASE)
        )
        and re.search(r"\bupstairs\b", user_context, re.IGNORECASE)
    ):
        return (
            "Based on the readings you gave me, paying the ISP more is unlikely to fix the upstairs slowdown: "
            "you already demonstrated high throughput on the wired/main-node side while the phone is slow upstairs. "
            "That points to the local Wi-Fi/mesh path, but those readings still do not identify the exact wireless cause."
        )

    return (
        "I don't have enough reliable user-supplied information to answer that "
        "without guessing."
    )


def build_recommendation_request_fallback(
    user_input: str,
    conversation=None,
) -> str:
    """Useful fail-closed rendering for an explicit recommendation request.

    This is only used after normal local generation/retry has failed. It keeps
    the response actionable without fabricating personal facts or returning an
    internal evidence-limit diagnostic to Oliver.
    """

    current = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
    recent_user = []

    for message in reversed(list(conversation or [])):
        if isinstance(message, dict):
            role = message.get("role")
            content = message.get("content")
        else:
            role = getattr(message, "role", None)
            content = getattr(message, "content", None)

        if str(role or "").lower() != "user":
            continue

        value = re.sub(r"\s+", " ", str(content or "").strip())
        if value:
            recent_user.append(value)
        if len(recent_user) >= 3:
            break

    context = (" ".join(reversed(recent_user)) + " " + current).lower()

    wants_one = bool(re.search(r"\b(?:one|single|just one)\b", current))
    wants_skill = bool(re.search(r"\bskill\b|\bpractis(?:e|ing)\b|\bpractice\b", current))
    wants_next_step = bool(re.search(r"\bnext\s+step\b|\buseful\s+step\b|\bwhat\s+should\s+i\s+do\b", current))

    if re.search(r"\bwhat\s+should\s+i\s+watch\b", current):
        if (
            re.search(r"\bdark\b", context)
            and re.search(r"\bcharacter(?:[- ]driven|\s+driven)?\b", context)
            and re.search(r"\b(?:not\s+(?:a\s+)?comedy|no\s+comedy|definitely\s+not\s+(?:a\s+)?comedy)\b", context)
        ):
            return (
                "Watch Monster. It's a dark, character-driven psychological thriller, "
                "and comedy is not the point of the show."
            )
        return "Watch Monster if you want a serious, character-driven thriller."

    if wants_skill and re.search(r"\b(?:cyber|cybersecurity|security|network|soc)\b", context):
        return (
            "Practice packet analysis in Wireshark: take one small capture and explain "
            "the DNS/TCP/TLS flow from first principles. One skill, no career speech."
        )

    if wants_next_step and re.search(r"\b(?:rejection|rejected|grad|graduate|application|job)\b", context):
        return (
            "Take the next role you actually want and spend 10 minutes tailoring your "
            "application to that job, then stop and get back to uni."
        )

    if wants_skill:
        return (
            "Pick one core skill in the area you're working on and practise it hands-on "
            "with one small exercise instead of turning it into a whole study plan."
        )

    if wants_one or wants_next_step:
        return (
            "Do one small, reversible action that directly advances the thing you just "
            "asked about, then reassess instead of turning it into a whole plan."
        )

    return (
        "Start with one small, reversible recommendation that directly matches the "
        "constraint you just gave me; keep everything else for later."
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

        if re.search(
            r"\bjust\s+wanted\s+to\s+(?:tell|share)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return (
                "Yeah, fair — sometimes you just want to share the win without "
                "turning it into another task."
            )

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
        current = re.sub(r"\s+", " ", str(user_input or "").strip())
        contrast = re.search(
            r"\b(?P<new>[A-Za-z][A-Za-z0-9_-]{1,30})\s+"
            r"(?P<noun>cube|bag|box|folder|file|room|shelf|drawer)\b"
            r"[^.!?]{0,35}\bnot\s+(?P<old>[A-Za-z][A-Za-z0-9_-]{1,30})\b",
            current,
            flags=re.IGNORECASE,
        )
        if contrast:
            return (
                "Got it — " + contrast.group("new") + " " + contrast.group("noun")
                + ", not " + contrast.group("old") + "."
            )
        return (
            "Got it — I'll use your latest correction instead of the earlier detail."
        )

    if intent == "casual_conversation":
        if user_input is not None:
            text = re.sub(r"\s+", " ", str(user_input or "").strip()).lower()
            if re.search(r"\bjust\s+wanted\s+to\s+(?:tell|share)\b", text):
                return (
                    "Yeah, fair — sometimes you just want to share the win without "
                    "turning it into another task."
                )
        return (
            "Yeah, fair enough."
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
