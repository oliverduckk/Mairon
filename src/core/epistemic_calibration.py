"""Phase 11.6.3: keep inaccessible private state and lexical uncertainty honest.

This module does not attempt to decide whether a word actually exists or to
infer unobserved facts about Oliver. Both require evidence it may not have.
"""

import re
from typing import Optional, Tuple


# These deliberately describe *inaccessible state*, not all questions about
# Oliver. Known calendar/email/routine workflows and explicit conversational
# recall still retain their existing, higher-priority intent routes.
# Single source of truth shared by older Core modules (which need a kind)
# and the Phase 11.6.3 authority router (which needs a boolean).  Never turn
# non-observation into a guessed personal fact or a public-web lookup.
_PRIVATE_STATE_KIND_PATTERNS = (
    ("current_appearance", (
        r"^\s*(?:what|which)\b.{0,90}\b(?:am\s+i|i(?:'m| am))\s+wearing\b",
        r"^\s*(?:what|which)\s+(?:am\s+i|i(?:'m| am))\s+wearing\b",
        r"^\s*(?:can|could)\s+you\s+(?:tell|see|know)\b.{0,75}"
        r"\b(?:i(?:'m| am)\s+wearing|my\s+(?:shirt|outfit))\b",
    )),
    ("undisclosed_meal", (
        r"^\s*what\s+(?:did|have)\s+i\s+(?:eat|have|drink)\s+(?:for\s+)?"
        r"(?:breakfast|lunch|dinner)\b",
        r"^\s*what\s+(?:have\s+i|did\s+i)\s+(?:eat|drink|have)\b.{0,30}"
        r"\b(?:today|this morning|last night|yesterday)\b",
    )),
    ("private_thought", (
        r"^\s*(?:what|which|who)\s+(?:number|person|colour|color|word|name|thing)?"
        r"\s*am\s+i\s+(?:thinking\s+of|imagining|picturing)\b",
    )),
    ("concealed_object", (
        r"^\s*(?:what(?:'s| is)|what\s+do\s+i\s+have)\s+(?:in|inside)\s+my\s+"
        r"(?:pocket|closed\s+hand|fist)\b",
        r"^\s*(?:which|what)\s+side\b.{0,90}\b(?:in|inside)\s+my\s+"
        r"(?:closed|clenched|shut)\s+(?:fist|hand)\b",
        r"\b(?:coin|card|object|item)\b.{0,100}\b(?:in|inside)\s+my\s+"
        r"(?:closed|clenched|shut)\s+(?:fist|hand)\b.{0,125}"
        r"\b(?:which|what)\s+(?:side|face)\b",
    )),
)


def classify_private_user_question(text: str) -> Optional[str]:
    """Return a bounded private-state category, or None for other questions.

    Compatibility for newer/older intent and Core orchestration modules:
    `None` means normal question routing remains eligible for user-grounded
    followups; a nonempty kind signals private state that public search cannot
    independently know.  No attempt is made to infer the hidden fact.
    """
    value = str(text or "").strip()
    if not value:
        return None
    # Oliver's ordinary vocatives and discourse framing must not change the
    # authority of an otherwise identical private-state question. In
    # particular "bro what shirt am I wearing right now?" MUST NOT reach a
    # public lookup merely because the anchored patterns missed "bro".
    prefix = re.compile(
        r"^\s*(?:(?:bro|bruh|mate|dude|yo|hey)\b[!,.: -]*|"
        r"(?:random\s+tangent|quick\s+question|side\s+note)\s*[:,-]\s*)",
        re.IGNORECASE,
    )
    previous = None
    while value and value != previous:
        previous = value
        value = prefix.sub("", value, count=1).strip()
    for kind, patterns in _PRIVATE_STATE_KIND_PATTERNS:
        if any(re.search(p, value, flags=re.IGNORECASE | re.DOTALL)
               for p in patterns):
            return kind
    return None


def is_inaccessible_private_state_question(text: str) -> bool:
    """Whether public research cannot establish the requested private fact."""
    return classify_private_user_question(text) is not None


_LEXICAL_QUERY_PATTERNS = (
    r"^\s*what\s+does\s+(.{1,70}?)\s+mean\s*[?.!]*\s*$",
    r"^\s*what(?:'s| is)\s+the\s+meaning\s+of\s+(.{1,70}?)\s*[?.!]*\s*$",
    r"^\s*define\s+(.{1,70}?)\s*[?.!]*\s*$",
    r"^\s*is\s+(.{1,70}?)\s+(?:a\s+)?(?:real\s+)?(?:word|term)\s*[?.!]*\s*$",
)


def extract_lexical_query_term(text: str) -> Optional[str]:
    """Recognise simple meaning/existence queries, without inventing a lexicon."""
    value = str(text or "").strip()
    for pattern in _LEXICAL_QUERY_PATTERNS:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            term = match.group(1).strip().strip('"\'`“”‘’ ')
            # Reject full-sentence or mathematical expressions. We only need
            # to guard confident claims about a term the user named.
            if (
                1 <= len(term) <= 60
                and len(term.split()) <= 4
                and re.fullmatch(r"[\w\- '\u2019]+", term, flags=re.UNICODE)
                and any(character.isalpha() for character in term)
            ):
                return term
    return None


# These claims assert *nonexistence* or fakery, not merely unfamiliarity.
# An LLM's failure to recognise a term cannot justify any of them.
_CATEGORICAL_LEXICAL_DENIAL_PATTERNS = (
    r"\b(?:is(?:n['’]?t| not)|isnt)\s+(?:an?\s+)?"
    r"(?:real|actual|valid|genuine|legitimate|recognised|recognized)\s+"
    r"(?:word|term|expression)\b",
    r"\b(?:does\s+not|doesn['’]?t|doesnt)\s+exist\b",
    r"\b(?:there(?:'s| is)\s+no\s+such\s+(?:word|term|expression))\b",
    r"\b(?:it(?:'s| is)|that(?:'s| is)|this\s+is)\s+(?:just\s+)?"
    r"(?:nonsense|gibberish|fake|made[ -]up|invented)\b",
    r"\b[\w'-]+\s+is\s+(?:pure\s+|just\s+)?"
    r"(?:nonsense|gibberish|fake|made[ -]up|invented)\b",
    r"\b(?:it(?:'s| is)|that(?:'s| is))\s+(?:a\s+)?fake\s+(?:word|term)\b",
)


def contains_unjustified_lexical_denial(user_input: str, draft: str) -> bool:
    """Detect categorical negative claims on lexical queries without evidence."""
    if not extract_lexical_query_term(user_input):
        return False
    value = str(draft or "")
    return any(
        re.search(pattern, value, flags=re.IGNORECASE)
        for pattern in _CATEGORICAL_LEXICAL_DENIAL_PATTERNS
    )


def repair_unjustified_lexical_denial(
    user_input: str,
    draft: str,
) -> Tuple[str, bool]:
    """Fail closed instead of publishing an unsupported categorical denial.

    Repair only when the drafted response actually crosses this boundary;
    ordinary definitions and properly qualified uncertainty pass untouched.
    """
    if not contains_unjustified_lexical_denial(user_input, draft):
        return draft, False
    term = extract_lexical_query_term(user_input)
    return (
        f"I'm not familiar enough with '{term}' to define it reliably "
        "without more context.",
        True,
    )
