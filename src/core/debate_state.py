from __future__ import annotations

import re
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Pairwise comparison parsing
# ---------------------------------------------------------------------------

# These are intentionally relation-shaped rather than franchise/name-shaped.
# Mairon needs to understand ordinary comparative slang without hard-coding
# Caera/Tess, anime titles, products, sports teams, or any other named subject.
_PAIRWISE_PATTERNS = (
    re.compile(
        r"^(?P<left>.+?)\s+"
        r"(?:(?:absolutely|easily|comfortably|clearly|obviously|still)\s+)?"
        r"(?P<relation>clears|stomps|gaps)\s+"
        r"(?P<right>.+?)"
        r"(?=\s+(?:and|but|because|bc|imo|imho|for\s+me|if\b)|[.!?]|$)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<left>.+?)\s+"
        r"(?P<relation>is\s+(?:way\s+|much\s+|far\s+)?better\s+than)\s+"
        r"(?P<right>.+?)"
        r"(?=\s+(?:and|but|because|bc|imo|imho|for\s+me|if\b)|[.!?]|$)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<left>.+?)\s*(?P<relation>>+)\s*(?P<right>.+?)"
        r"(?=\s+(?:and|but|because|bc|imo|imho|for\s+me|if\b)|[.!?]|$)",
        flags=re.IGNORECASE,
    ),
)

_PREFER_PATTERN = re.compile(
    r"^(?:i\s+)?(?:much\s+|way\s+|definitely\s+)?prefer\s+"
    r"(?P<left>.+?)\s+over\s+(?P<right>.+?)"
    r"(?=\s+(?:and|but|because|bc|imo|imho|for\s+me|if\b)|[.!?]|$)",
    flags=re.IGNORECASE,
)

_VS_HINT_PATTERN = re.compile(
    r"^\s*(?P<left>[^|]{1,120}?)\s+(?:vs\.?|versus)\s+"
    r"(?P<right>[^|]{1,120}?)\s*$",
    flags=re.IGNORECASE,
)

_LEADING_DISCOURSE_PATTERN = re.compile(
    r"^(?:(?:bro|bruh|mate|dude|man|yeah|yep|nah|nope|okay|ok|"
    r"lol|lmao|haha+|honestly|ngl|imo|imho|for\s+me)"
    r"(?:\s*[,!.-]\s*|\s+))+",
    flags=re.IGNORECASE,
)

_LEADING_OPINION_PATTERN = re.compile(
    r"^(?:i\s+(?:think|reckon|feel)\s+|"
    r"in\s+my\s+opinion\s+|"
    r"for\s+me\s+)",
    flags=re.IGNORECASE,
)

_TRAILING_NOISE_PATTERNS = (
    re.compile(
        r"\s+and\s+i(?:'m|\s+am)?\s+not\s+hearing\s+otherwise.*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\s+and\s+that(?:'s|\s+is)\s+final.*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\s+all\s+day.*$",
        flags=re.IGNORECASE,
    ),
)

_GENERIC_SIDE_VALUES = {
    "i",
    "me",
    "my",
    "mine",
    "you",
    "your",
    "yours",
    "he",
    "him",
    "his",
    "she",
    "her",
    "hers",
    "they",
    "them",
    "their",
    "theirs",
    "it",
    "this",
    "that",
    "these",
    "those",
}


# ---------------------------------------------------------------------------
# Debate-continuation detection
# ---------------------------------------------------------------------------

_DEBATE_CONTINUATION_PATTERNS = (
    re.compile(
        r"\bdefend\s+(?:your|that|the)\s+"
        r"(?:take|opinion|pick|choice|stance|ranking)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:back|justify)\s+(?:that|your\s+(?:take|opinion|stance))\s+up\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bmake\s+your\s+case\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:explain|justify)\s+(?:your|that)\s+"
        r"(?:take|opinion|stance|pick)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bwhy\s+(?:do|would)\s+you\s+"
        r"(?:think|reckon|say|pick|prefer)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bconvince\s+me\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bargue\s+(?:it|that|your\s+case)\b",
        flags=re.IGNORECASE,
    ),
)


# ---------------------------------------------------------------------------
# Stance interpretation helpers
# ---------------------------------------------------------------------------

_AGREEMENT_PATTERNS = (
    re.compile(
        r"^\s*(?:yeah|yep|yes|agreed|agree|fair|true|valid|absolutely|"
        r"definitely|exactly|correct|right)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i\s+agree|i'm\s+with\s+you|i\s+am\s+with\s+you|"
        r"you(?:'re|\s+are)\s+right)\b",
        flags=re.IGNORECASE,
    ),
)

_DISAGREEMENT_PATTERNS = (
    re.compile(
        r"^\s*(?:nah|no|nope|disagree)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i\s+disagree|i'm\s+not\s+with\s+you|"
        r"i\s+am\s+not\s+with\s+you|you(?:'re|\s+are)\s+wrong)\b",
        flags=re.IGNORECASE,
    ),
)


_EXPLICIT_UNCERTAINTY_PATTERNS = (
    re.compile(
        r"\b(?:i\s+)?(?:do\s+not|don't)\s+(?:really\s+)?"
        r"(?:have|feel)\s+(?:a\s+)?"
        r"(?:(?:strong)(?:\s+enough)?\s+)?"
        r"(?:side|preference|pick)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i'm|i\s+am)\s+(?:split|torn|undecided|not\s+sure)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:no\s+strong\s+preference|too\s+close\s+for\s+me)\b",
        flags=re.IGNORECASE,
    ),
)

_PRIOR_STANCE_REPAIR_PATTERNS = (
    re.compile(
        r"\bi\s+(?:didn't|did\s+not|never)\s+"
        r"(?:actually\s+)?(?:take|pick|choose)\s+(?:a\s+)?side\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bmy\s+(?:last|previous)\s+(?:reply|answer|response)\b.{0,80}"
        r"\b(?:didn't|did\s+not|wasn't|was\s+not)\b.{0,80}"
        r"\b(?:take|state|establish|give)\b.{0,40}\b(?:side|stance|position|pick)\b",
        flags=re.IGNORECASE,
    ),
)

_GENERIC_DEBATE_DODGES = {
    "got it",
    "got it.",
    "fair",
    "fair.",
    "yeah",
    "yeah.",
    "yep",
    "yep.",
    "noted",
    "noted.",
    "right",
    "right.",
}


def _normalise_space(
    value: Any,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ).strip(),
    )


def _normalise_key(
    value: Any,
) -> str:
    text = _normalise_space(
        value
    ).lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        text,
    ).strip(
        "_"
    )

    return text


def _clean_side(
    value: Any,
) -> Optional[str]:
    text = _normalise_space(
        value
    ).strip(
        " \t\r\n\"'`.,!?;:-"
    )

    previous = None

    while (
        text
        and text != previous
    ):
        previous = text

        text = _LEADING_DISCOURSE_PATTERN.sub(
            "",
            text,
            count=1,
        ).strip()

        text = _LEADING_OPINION_PATTERN.sub(
            "",
            text,
            count=1,
        ).strip()

    for pattern in _TRAILING_NOISE_PATTERNS:
        text = pattern.sub(
            "",
            text,
        ).strip()

    words = text.split()

    if (
        not words
        or len(words) > 6
    ):
        return None

    lowered = text.lower()

    if lowered in _GENERIC_SIDE_VALUES:
        return None

    # Avoid promoting request scaffolding into a debate participant.
    if lowered.startswith(
        (
            "what ",
            "why ",
            "how ",
            "do ",
            "does ",
            "did ",
            "can ",
            "could ",
            "would ",
            "should ",
        )
    ):
        return None

    return text[:120]


def _build_pairwise_subject(
    left: str,
    right: str,
    relation: str,
) -> Optional[Dict[str, str]]:
    left_value = _clean_side(
        left
    )

    right_value = _clean_side(
        right
    )

    if (
        not left_value
        or not right_value
    ):
        return None

    if left_value.lower() == right_value.lower():
        return None

    left_key = _normalise_key(
        left_value
    )

    right_key = _normalise_key(
        right_value
    )

    if (
        not left_key
        or not right_key
    ):
        return None

    relation_value = _normalise_space(
        relation
    ).lower()

    canonical_sides = sorted([
        left_key,
        right_key,
    ])

    return {
        "key": (
            "comparison::"
            + canonical_sides[0]
            + "::vs::"
            + canonical_sides[1]
        ),
        "label": (
            left_value
            + " vs "
            + right_value
        ),
        "title": (
            left_value
            + " vs "
            + right_value
        ),
        "kind": "pairwise_comparison",
        "left": left_value,
        "right": right_value,
        "asserted_side": "left",
        "relation": relation_value,
    }


def extract_pairwise_comparison(
    text: Any,
) -> Optional[Dict[str, str]]:
    """
    Parse a user-authored pairwise preference/comparison.

    This deliberately recognises generic relation language rather than named
    franchises or entities. Examples:

        "Rhea clears Mina"
        "I prefer Rhea over Mina"
        "Rhea is way better than Mina"
        "Rhea > Mina"

    The output represents conversational stance only. It does not establish
    that either side is a public figure, fictional character, product, or any
    other external-world entity.
    """

    value = _normalise_space(
        text
    )

    if not value:
        return None

    # Remove lightweight discourse/opinion lead-ins before relation parsing.
    previous = None

    while (
        value
        and value != previous
    ):
        previous = value

        value = _LEADING_DISCOURSE_PATTERN.sub(
            "",
            value,
            count=1,
        ).strip()

        value = _LEADING_OPINION_PATTERN.sub(
            "",
            value,
            count=1,
        ).strip()

    prefer_match = _PREFER_PATTERN.search(
        value
    )

    if prefer_match:
        return _build_pairwise_subject(
            left=prefer_match.group(
                "left"
            ),
            right=prefer_match.group(
                "right"
            ),
            relation="prefer_over",
        )

    for pattern in _PAIRWISE_PATTERNS:
        match = pattern.search(
            value
        )

        if not match:
            continue

        return _build_pairwise_subject(
            left=match.group(
                "left"
            ),
            right=match.group(
                "right"
            ),
            relation=match.group(
                "relation"
            ),
        )

    return None


def pairwise_subject_from_hint(
    subject_hint: Any,
) -> Optional[Dict[str, str]]:
    """
    Rehydrate a stable pairwise subject from Core's compact subject label.

    The hint is conversation state ("Rhea vs Mina"), not factual evidence.
    """

    value = _normalise_space(
        subject_hint
    )

    if not value:
        return None

    match = _VS_HINT_PATTERN.match(
        value
    )

    if not match:
        return None

    return _build_pairwise_subject(
        left=match.group(
            "left"
        ),
        right=match.group(
            "right"
        ),
        relation="vs",
    )


def looks_like_debate_continuation(
    text: Any,
) -> bool:
    value = _normalise_space(
        text
    )

    if not value:
        return False

    return any(
        pattern.search(
            value
        )
        for pattern in _DEBATE_CONTINUATION_PATTERNS
    )


def build_pairwise_semantic_instruction(
    subject: Optional[Dict[str, Any]],
    *,
    debate_continuation: bool = False,
    position: Optional[str] = None,
) -> Optional[str]:
    """
    Render compact semantic state for the language model.

    This is interpretation/persona state only. It grants no factual authority
    about the compared entities.
    """

    if (
        not subject
        or subject.get(
            "kind"
        )
        != "pairwise_comparison"
    ):
        return None

    left = _normalise_space(
        subject.get(
            "left"
        )
    )

    right = _normalise_space(
        subject.get(
            "right"
        )
    )

    if (
        not left
        or not right
    ):
        return None

    relation = _normalise_space(
        subject.get(
            "relation"
        )
    ).lower()

    lines = [
        "CORE PAIRWISE OPINION FRAME:",
        (
            "- Active comparison: "
            + left
            + " vs "
            + right
            + "."
        ),
        (
            "- Oliver's comparison places "
            + left
            + " above "
            + right
            + "."
        ),
        "- This is conversational stance, not evidence about either subject.",
        "- Oliver stating a preference is not an instruction to agree. Mairon may "
        "agree, disagree, or qualify the comparison based on its own judgement.",
        "- Do not invent specific canon/events/credits merely to sound decisive. If "
        "you do not confidently know the basis for a detailed argument, say so.",
    ]

    if relation == "clears":
        lines.append(
            "- In this comparison, '"
            + left
            + " clears "
            + right
            + "' is evaluative slang meaning "
            + left
            + " is rated above "
            + right
            + "; it does NOT mean "
            + left
            + " is literally finished/done with "
            + right
            + "."
        )

    if debate_continuation:
        lines.extend([
            "- Oliver is explicitly continuing the debate and asking Mairon to "
            "defend/explain its own take.",
            "- Address the comparison itself. Do not redirect the argument into "
            "Oliver's tone, the insult, or generic banter about being challenged.",
            "- If Mairon's earlier stance was weak or mistaken, revise it explicitly "
            "instead of pretending a coherent stance existed.",
            "- Prefer preference-level or interpretive reasons when no verified factual "
            "packet is available. Do not manufacture canon events, relationships, powers, "
            "roles, creator credits, or plot details merely to make the defence sound deeper.",
        ])
    else:
        lines.extend([
            "- Mairon's reply must establish its OWN stance: side with the left option, "
            "side with the right option, or explicitly say it is genuinely undecided.",
            "- Merely paraphrasing Oliver's preference is not enough to establish Mairon's "
            "own opinion.",
            "- A pure preference is persona state, not an external factual claim. Mairon "
            "may state which side it prefers without inventing canon facts to justify it.",
        ])

    if position == "left":
        lines.append(
            "- Structured persona state: Mairon previously sided with "
            + left
            + " over "
            + right
            + "."
        )

    elif position == "right":
        lines.append(
            "- Structured persona state: Mairon previously sided with "
            + right
            + " over "
            + left
            + "."
        )

    elif position == "unclear":
        lines.append(
            "- Structured persona state: Mairon's previous reply did not establish "
            "a clear side. Do not fabricate a prior stance; clarify or explicitly "
            "take/revise a position now."
        )

    return "\n".join(
        lines
    )



def _relation_match_is_user_attributed(
    response_text: Any,
    match_start: int,
    match_end: Optional[int] = None,
) -> bool:
    """
    Distinguish Mairon's own pairwise stance from a paraphrase of Oliver's.

    Examples that belong to Oliver:
        "I get why you have Rhea over Mina."
        "Rhea over Mina is your call."
        "Rhea over Mina — that's your preference."

    Examples that belong to Mairon:
        "Rhea over Mina, easy."
        "For me, Rhea over Mina."
        "I know you have Rhea over Mina, but Mina over Rhea for me."

    This is intentionally speaker-role based rather than topic/name based.
    """

    response = _normalise_space(
        response_text
    )

    if not response:
        return False

    start = max(
        0,
        int(
            match_start
            or 0
        ),
    )

    end = (
        max(
            start,
            int(
                match_end
                if match_end is not None
                else start
            ),
        )
    )

    # Inspect only the nearby clause around the relation. A separate stance
    # after "but"/punctuation should be allowed to belong to Mairon.
    prefix = response[
        max(
            0,
            start - 140,
        )
        :start
    ]

    prefix_clause = re.split(
        r"[.!?;]|(?:\bbut\b)|(?:\bhowever\b)",
        prefix,
        flags=re.IGNORECASE,
    )[-1]

    suffix = response[
        end:
        min(
            len(response),
            end + 140,
        )
    ]

    suffix_clause = re.split(
        r"[.!?;]|(?:\bbut\b)|(?:\bhowever\b)",
        suffix,
        flags=re.IGNORECASE,
    )[0]

    attributed_before = bool(
        re.search(
            r"\b(?:"
            r"you|your|yours|"
            r"you(?:'ve|'d|'re)|"
            r"you\s+(?:have|had|would|rate|rank|put|pick|picked|"
            r"choose|chose|prefer|preferred|decide|decided|think|reckon|say|said)|"
            r"your\s+(?:take|pick|ranking|preference|opinion|call|choice)"
            r")\b",
            prefix_clause,
            flags=re.IGNORECASE,
        )
    )

    attributed_after = bool(
        re.search(
            r"^\s*(?:[-—,:]\s*)?(?:"
            r"is\s+your\s+(?:call|take|pick|ranking|preference|opinion|choice)|"
            r"(?:is|that's|that\s+is)\s+what\s+you\s+(?:think|reckon|said|picked|chose)|"
            r"(?:that's|that\s+is)\s+your\s+(?:call|take|pick|ranking|preference|opinion|choice)"
            r")\b",
            suffix_clause,
            flags=re.IGNORECASE,
        )
    )

    return (
        attributed_before
        or attributed_after
    )


def pairwise_response_is_explicitly_uncertain(
    response_text: Any,
) -> bool:
    """
    Public helper for Opinion Ledger revision logic.

    A clear statement that Mairon has no side is valid persona state and may
    revise an older stored pairwise stance.
    """

    return _explicit_pairwise_uncertainty(
        response_text
    )


def infer_pairwise_position(
    subject: Optional[Dict[str, Any]],
    *,
    user_input: Any,
    response_text: Any,
) -> str:
    """
    Infer only Mairon's expressed preference relation.

    The result is persona state, never external factual evidence.
    """

    if (
        not subject
        or subject.get(
            "kind"
        )
        != "pairwise_comparison"
    ):
        return "unclear"

    left = _normalise_space(
        subject.get(
            "left"
        )
    )

    right = _normalise_space(
        subject.get(
            "right"
        )
    )

    if (
        not left
        or not right
    ):
        return "unclear"

    response = _normalise_space(
        response_text
    )

    if not response:
        return "unclear"

    response_comparison = (
        extract_pairwise_comparison(
            response
        )
    )

    if response_comparison:
        resp_left = _normalise_space(
            response_comparison.get(
                "left"
            )
        ).lower()

        resp_right = _normalise_space(
            response_comparison.get(
                "right"
            )
        ).lower()

        if (
            resp_left == left.lower()
            and resp_right == right.lower()
        ):
            return "left"

        if (
            resp_left == right.lower()
            and resp_right == left.lower()
        ):
            return "right"

    # Direct "X over Y" phrasing is common in a defence even without "prefer".
    left_over_right = re.search(
        re.escape(
            left
        )
        + r"\s+over\s+"
        + re.escape(
            right
        ),
        response,
        flags=re.IGNORECASE,
    )

    if (
        left_over_right
        and not _relation_match_is_user_attributed(
            response,
            left_over_right.start(),
            left_over_right.end(),
        )
    ):
        return "left"

    right_over_left = re.search(
        re.escape(
            right
        )
        + r"\s+over\s+"
        + re.escape(
            left
        ),
        response,
        flags=re.IGNORECASE,
    )

    if (
        right_over_left
        and not _relation_match_is_user_attributed(
            response,
            right_over_left.start(),
            right_over_left.end(),
        )
    ):
        return "right"

    user_comparison = (
        extract_pairwise_comparison(
            user_input
        )
    )

    if user_comparison:
        if any(
            pattern.search(
                response
            )
            for pattern in _AGREEMENT_PATTERNS
        ):
            return "left"

        if any(
            pattern.search(
                response
            )
            for pattern in _DISAGREEMENT_PATTERNS
        ):
            return "right"

    return "unclear"


def pairwise_position_label(
    subject: Optional[Dict[str, Any]],
    position: Any,
) -> Optional[str]:
    if (
        not subject
        or subject.get(
            "kind"
        )
        != "pairwise_comparison"
    ):
        return None

    left = _normalise_space(
        subject.get(
            "left"
        )
    )

    right = _normalise_space(
        subject.get(
            "right"
        )
    )

    position_value = _normalise_space(
        position
    ).lower()

    if position_value == "left":
        return (
            left
            + " over "
            + right
        )

    if position_value == "right":
        return (
            right
            + " over "
            + left
        )

    return "unclear"


def _explicit_pairwise_uncertainty(
    response_text: Any,
) -> bool:
    value = _normalise_space(
        response_text
    )

    if not value:
        return False

    return any(
        pattern.search(
            value
        )
        for pattern in _EXPLICIT_UNCERTAINTY_PATTERNS
    )


def _explicit_prior_stance_repair(
    response_text: Any,
) -> bool:
    value = _normalise_space(
        response_text
    )

    if not value:
        return False

    return any(
        pattern.search(
            value
        )
        for pattern in _PRIOR_STANCE_REPAIR_PATTERNS
    )


def find_pairwise_opinion_integrity_violations(
    subject: Optional[Dict[str, Any]],
    *,
    user_input: Any,
    response_text: Any,
    debate_continuation: bool = False,
    established_position: Optional[str] = None,
) -> list[str]:
    """
    Enforce only the conversational/persona side of a pairwise opinion.
    Existing grounding remains responsible for factual/canon support.
    """

    if (
        not subject
        or subject.get(
            "kind"
        )
        != "pairwise_comparison"
    ):
        return []

    response = _normalise_space(
        response_text
    )

    if not response:
        return []

    violations = []

    if (
        debate_continuation
        and response.lower()
        in _GENERIC_DEBATE_DODGES
    ):
        violations.append(
            "explicit debate continuation was answered with a generic acknowledgement"
        )

    current_position = infer_pairwise_position(
        subject,
        user_input=user_input,
        response_text=response,
    )

    explicit_uncertainty = (
        _explicit_pairwise_uncertainty(
            response
        )
    )

    if not debate_continuation:
        if (
            current_position
            == "unclear"
            and not explicit_uncertainty
        ):
            violations.append(
                "pairwise opinion reply did not establish Mairon's own side "
                "or explicit uncertainty"
            )

        return violations

    previous_position = _normalise_space(
        established_position
    ).lower()

    if previous_position not in {
        "left",
        "right",
    }:
        if (
            current_position
            == "unclear"
            and not explicit_uncertainty
            and not _explicit_prior_stance_repair(
                response
            )
        ):
            violations.append(
                "debate continuation had no established prior side and did not "
                "explicitly repair, choose, or decline a stance"
            )

    return violations


def build_pairwise_opinion_fallback(
    subject: Optional[Dict[str, Any]],
    *,
    position: Optional[str] = None,
    debate_continuation: bool = False,
) -> str:
    """
    Persona-safe fallback after repeated pairwise-opinion grounding failures.
    No external/canon claims are introduced here.
    """

    if (
        not subject
        or subject.get(
            "kind"
        )
        != "pairwise_comparison"
    ):
        return "I don't have a clean enough take to force one."

    left = _normalise_space(
        subject.get(
            "left"
        )
    )

    right = _normalise_space(
        subject.get(
            "right"
        )
    )

    position_value = _normalise_space(
        position
    ).lower()

    if debate_continuation:
        if position_value == "left":
            return (
                "I had "
                + left
                + " over "
                + right
                + ". That's the preference I'm defending; I'm just not going to "
                "invent canon details to pad the argument."
            )

        if position_value == "right":
            return (
                "I had "
                + right
                + " over "
                + left
                + ". That's the preference I'm defending; I'm just not going to "
                "invent canon details to pad the argument."
            )

        return (
            "I didn't actually establish my own side in that last reply — I only "
            "reflected yours. So pretending I had a take to defend would be bullshit."
        )

    return (
        "I get the comparison — "
        + left
        + " over "
        + right
        + " is your call. I don't have a strong enough side of my own to fake one."
    )
