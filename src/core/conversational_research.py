from __future__ import annotations

import re
from typing import Any, Optional


PRIVATE_RELATION_PATTERN = re.compile(
    r"\bmy\s+(?:"
    r"friend|mate|mum|mom|dad|mother|father|brother|sister|"
    r"partner|girlfriend|boyfriend|wife|husband|"
    r"boss|manager|coworker|co-worker|colleague|"
    r"classmate|teacher|lecturer|doctor|neighbour|neighbor|"
    r"cousin|aunt|uncle|grandma|grandmother|grandpa|grandfather"
    r")\b",
    flags=re.IGNORECASE,
)


PUBLIC_CONTEXT_PATTERN = re.compile(
    r"\b(?:"
    r"anime|manga|manhwa|manhua|light\s+novel|web\s+novel|novel|book|"
    r"film|movie|show|series|episode|season|chapter|volume|arc|character|"
    r"game|match|team|league|tournament|player|coach|"
    r"company|ceo|executive|stock|shareholder|product|launch|release|"
    r"president|prime\s+minister|government|election|policy|parliament|"
    r"album|song|artist|actor|author|director|creator"
    r")\b",
    flags=re.IGNORECASE,
)


PUBLIC_ACRONYM_PATTERN = re.compile(
    r"\b[A-Z][A-Z0-9]{1,7}\b"
)


CONVERSATIONAL_SEARCH_PREFIX_PATTERNS = (
    # Explicit discourse/topic reset wrappers are conversational state, not
    # public-search identity.
    r"^\s*(?:anyway|anyways|moving\s+on|different\s+topic|"
    r"unrelated(?:ly)?|side\s+note)[,:\s-]+",

    r"^\s*(?:bro|bruh|mate)[,:\s-]+",
    r"^\s*(?:hey[,:\s-]+)?(?:are|were)\s+we\s+"
    r"(?:keen|ready|hyped|excited)\s+(?:for\s+|about\s+)?",
    r"^\s*(?:can|could|would)\s+you\s+(?:please\s+)?"
    r"(?:tell\s+me|check|look\s+up|find\s+out|search\s+for)\s+",
    r"^\s*do\s+you\s+know\s+(?:if|whether\s+)?",
    r"^\s*any\s+idea\s+(?:if|whether\s+)?",

    # Recent/past media shorthand often arrives as a natural-language
    # referential question. Remove the question wrapper without touching the
    # identity/date phrase itself.
    r"^\s*what\s+(?:was|is)\s+(?:that|the)\s+",
)


PERSONAL_REACTION_SUFFIX_PATTERNS = (
    r"\s+(?:is|was|has\s+been|had\s+been)\s+"
    r"(?:already\s+|really\s+|seriously\s+|so\s+)?"
    r"(?:pissing\s+me\s+off|annoying\s+me|frustrating\s+me|"
    r"doing\s+my\s+head\s+in|driving\s+me\s+mad)\b.*$",

    r"\s+(?:has|had)\s+me\s+"
    r"(?:annoyed|frustrated|pissed\s+off|mad)\b.*$",

    r"\s+(?:that\s+)?(?:everyone|people)\s+(?:was|were)\s+"
    r"(?:talking|posting|hyping)\s+about\b.*$",
)


def normalise_public_research_query(
    text: str,
) -> str:
    """
    Convert conversational wording into a compact public-search query.

    This is deliberately semantic-preserving rather than an LLM rewrite:
    - strip conversational wrappers;
    - strip Oliver's trailing reaction when it adds no search identity;
    - simplify "<subject>'s handling of <event>";
    - preserve names, titles, acronyms, temporal words, and content nouns.

    Examples:
        "are we keen for the Natsuki Subaru episode tonight?"
            -> "Natsuki Subaru episode tonight"

        "Marin's handling of the final vote in ABCD is pissing me off"
            -> "Marin final vote in ABCD"
    """

    value = re.sub(
        r"\s+",
        " ",
        str(
            text
            or ""
        ).strip(),
    )

    if not value:
        return ""

    for pattern in CONVERSATIONAL_SEARCH_PREFIX_PATTERNS:
        value = re.sub(
            pattern,
            "",
            value,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

    for pattern in PERSONAL_REACTION_SUFFIX_PATTERNS:
        value = re.sub(
            pattern,
            "",
            value,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

    # "Rina's handling of the final vote" carries the same search identity as
    # "Rina final vote" and ranks substantially better on ordinary web search.
    possessive_handling = re.match(
        r"^\s*(.{1,140}?)[’']s\s+handling\s+of\s+(?:the\s+)?(.+)$",
        value,
        flags=re.IGNORECASE,
    )

    if possessive_handling:
        value = (
            possessive_handling.group(1).strip()
            + " "
            + possessive_handling.group(2).strip()
        )

    value = re.sub(
        r"^\s*the\s+",
        "",
        value,
        count=1,
        flags=re.IGNORECASE,
    )

    value = value.strip(
        " \t\r\n?!.,;:"
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value[:500]


def looks_like_public_external_context(
    text: str,
) -> bool:
    """
    Conservative privacy-aware classifier for contextual opinion research.

    This is intentionally NOT named-entity recognition. It asks only whether
    Oliver's previous wording contains a clear public/external-domain signal
    strong enough to justify a web lookup.

    Personal relationship language wins and blocks automatic public research.
    """

    value = str(
        text
        or ""
    ).strip()

    if not value:
        return False

    if PRIVATE_RELATION_PATTERN.search(
        value
    ):
        return False

    if PUBLIC_CONTEXT_PATTERN.search(
        value
    ):
        return True

    # Short all-caps title/company/league abbreviations are a useful public
    # context signal without hard-coding any franchise or organisation.
    if PUBLIC_ACRONYM_PATTERN.search(
        value
    ):
        return True

    return False


def contextual_opinion_requires_public_grounding(
    turn: Any,
) -> bool:
    if turn is None:
        return False

    if str(
        getattr(
            turn,
            "intent",
            "",
        )
        or ""
    ).strip() != "share_opinion":
        return False

    entities = (
        getattr(
            turn,
            "entities",
            {},
        )
        or {}
    )

    return str(
        entities.get(
            "_conversation_public_grounding_required",
            "",
        )
        or ""
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "public",
    }


def build_contextual_opinion_research_query(
    *,
    user_input: str,
    previous_user_text: Optional[str],
    subject: Optional[str] = None,
) -> str:
    """
    Build a bounded search query from USER-authored discourse only.

    The previous Oliver turn normally carries more useful factual context than
    a pronoun-heavy current question such as "do you think she handled it well?"
    """

    current = normalise_public_research_query(
        user_input
    )

    previous = normalise_public_research_query(
        previous_user_text
    )

    subject_value = re.sub(
        r"\s+",
        " ",
        str(
            subject
            or ""
        ).strip(),
    )

    pieces = []

    if previous:
        pieces.append(
            previous[
                :420
            ]
        )

    if (
        subject_value
        and subject_value.lower()
        not in previous.lower()
    ):
        pieces.insert(
            0,
            subject_value[
                :120
            ],
        )

    # The current question can contain useful judgement terms, but avoid
    # duplicating it when the prior context already gives the search enough
    # specificity.
    if (
        current
        and not previous
    ):
        pieces.append(
            current[
                :280
            ]
        )

    query = " ".join(
        piece
        for piece in pieces
        if piece
    ).strip()

    return (
        query
        or current[
            :500
        ]
    )


# ------------------------------------------------------------------
# Phase 11.5.1 — background research opportunity + permission
# ------------------------------------------------------------------

_BACKGROUND_RESEARCH_DIRECT_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:while|when)\s+(?:i(?:'m|m| am)?\s+)?"
    r"(?:sleep(?:ing)?|asleep|out|away|at\s+work|busy)\s*[,;:-]?\s*)?"
    r"(?:(?:can|could|would)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:"
    r"research|"
    r"do\s+(?:some\s+|a\s+bit\s+of\s+)?research(?:\s+(?:on|into|about))?|"
    r"look\s+into"
    r")\s+"
    r"(?P<topic>.+?)"
    r"\s*$",
    flags=re.IGNORECASE,
)

_BACKGROUND_RESEARCH_SUFFIX_PATTERN = re.compile(
    r"\s+(?:"
    r"in\s+the\s+background|"
    r"overnight|"
    r"(?:while|when)\s+i(?:'m|m| am)?\s+"
    r"(?:sleep(?:ing)?|asleep|out|away|busy|at\s+work)|"
    r"(?:while|when)\s+i\s+(?:sleep|go\s+to\s+sleep)|"
    r"before\s+i\s+(?:wake\s+up|get\s+back|come\s+back|get\s+home)"
    r")\s*$",
    flags=re.IGNORECASE,
)

_RESEARCH_APPROVAL_PATTERNS = (
    r"^\s*(?:yeah|yep|yes|sure|okay|ok)[,.!]?\s*(?:go\s+for\s+it|do\s+it|research\s+it|look\s+into\s+it)?[.!]?\s*$",
    r"^\s*(?:go\s+for\s+it|do\s+it|research\s+it|look\s+into\s+it|go\s+ahead)[.!]?\s*$",
    r"^\s*(?:yeah|yes|yep|sure)[, ]+(?:research|look\s+into)\s+(?:it|that)[.!]?\s*$",
)

_RESEARCH_DECLINE_PATTERNS = (
    r"^\s*(?:nah|no|nope)[.!]?\s*$",
    r"^\s*(?:don't|do\s+not)\s+(?:research|look\s+into)\s+(?:it|that)[.!]?\s*$",
    r"^\s*(?:leave|forget)\s+(?:it|that)[.!]?\s*$",
)


def classify_research_permission_reply(
    text: str,
) -> Optional[str]:
    """
    Resolve a short reply to Mairon's explicit research-permission question.

    Returns:
        "approve", "decline", or None.

    This is intentionally narrow so an unrelated conversational turn cannot
    accidentally launch background research.
    """

    value = re.sub(
        r"\s+",
        " ",
        str(
            text
            or ""
        ).strip(),
    )

    if not value:
        return None

    if len(
        value.split()
    ) > 12:
        return None

    if any(
        re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        )
        for pattern in _RESEARCH_APPROVAL_PATTERNS
    ):
        return "approve"

    if any(
        re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        )
        for pattern in _RESEARCH_DECLINE_PATTERNS
    ):
        return "decline"

    return None


def extract_explicit_background_research_request(
    text: str,
) -> Optional[dict]:
    """
    Recognise an explicit request to create background research.

    No web access happens here. This only turns Oliver's direct instruction
    into a durable job description that the background worker can process
    later. The original request remains the authoritative goal/context.
    """

    value = re.sub(
        r"\s+",
        " ",
        str(
            text
            or ""
        ).strip(),
    )

    if not value:
        return None

    match = _BACKGROUND_RESEARCH_DIRECT_PATTERN.match(
        value
    )

    if not match:
        return None

    topic = str(
        match.group(
            "topic"
        )
        or ""
    ).strip()

    # Execution timing belongs to job policy, not topic identity. Strip terminal
    # punctuation first so phrases such as "in the background." still match.
    topic = topic.strip(
        " \t\r\n?!.,;:"
    )

    previous = None

    while topic and topic != previous:
        previous = topic

        topic = re.sub(
            _BACKGROUND_RESEARCH_SUFFIX_PATTERN,
            "",
            topic,
        ).strip(
            " \t\r\n?!.,;:"
        )

    if not topic:
        return None

    return {
        "topic": topic[:500],
        "goal": value[:1200],
        "original_request": value[:1200],
        "depth": "deep",
        "priority": "background",
        "source": "explicit_request",
    }


def build_pairwise_background_research_opportunity(
    *,
    opinion_subject: Any,
    opinion_entry: Any,
    user_input: str,
    intent: Optional[str],
) -> Optional[dict]:
    """
    Offer research when Oliver opens a pairwise debate but Mairon has no
    established side of its own.

    This does NOT assume the names are public and does NOT access the web.
    Oliver's approval is the boundary before a background research job exists.
    """

    if str(
        intent
        or ""
    ).strip() != "share_opinion":
        return None

    if not isinstance(
        opinion_subject,
        dict,
    ):
        return None

    if opinion_subject.get(
        "kind"
    ) != "pairwise_comparison":
        return None

    existing_position = ""

    if isinstance(
        opinion_entry,
        dict,
    ):
        existing_position = str(
            opinion_entry.get(
                "position"
            )
            or ""
        ).strip().lower()

    if existing_position in {
        "left",
        "right",
    }:
        return None

    left = re.sub(
        r"\s+",
        " ",
        str(
            opinion_subject.get(
                "left"
            )
            or ""
        ).strip(),
    )

    right = re.sub(
        r"\s+",
        " ",
        str(
            opinion_subject.get(
                "right"
            )
            or ""
        ).strip(),
    )

    if not left or not right:
        return None

    topic = (
        left
        + " vs "
        + right
    )

    return {
        "topic": topic[:500],
        "goal": (
            "Research enough trustworthy public context about "
            + topic
            + " for Mairon to form and defend an informed independent opinion. "
            "Keep verified external facts separate from Mairon's eventual subjective stance."
        )[:1200],
        "original_request": str(
            user_input
            or ""
        ).strip()[:1200],
        "depth": "deep",
        "priority": "background",
        "source": "research_offer",
        "metadata": {
            "research_kind": "pairwise_opinion",
            "left": left,
            "right": right,
        },
    }


def build_background_research_offer_text(
    opportunity: dict,
) -> str:
    topic = re.sub(
        r"\s+",
        " ",
        str(
            (
                opportunity
                or {}
            ).get(
                "topic"
            )
            or "that topic"
        ).strip(),
    )

    return (
        "I don't know enough about "
        + topic
        + " to argue it properly yet. Want me to research it properly in "
        "the background and come back with an informed take?"
    )


def build_background_research_queued_text(
    job: dict,
) -> str:
    topic = re.sub(
        r"\s+",
        " ",
        str(
            (
                job
                or {}
            ).get(
                "topic"
            )
            or "that"
        ).strip(),
    )

    if (
        job
        and job.get(
            "deduplicated"
        )
    ):
        return (
            "Already on it — "
            + topic
            + " is already sitting in my background research queue."
        )

    return (
        "Yep. I've queued "
        + topic
        + " for proper background research. Normal conversations and other "
        "interactive stuff still take priority."
    )
