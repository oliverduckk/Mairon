import re


EMAIL_ATTENTION_PATTERNS = (
    # Email/inbox subject + action/importance predicate in either order.
    r"\b(?:emails?|messages?|inbox|gmail)\b[^.!?\n]{0,100}"
    r"\b(?:need|needs|require|requires|deserve|deserves)\b[^.!?\n]{0,50}"
    r"\b(?:my\s+)?(?:attention|action|reply|response)\b",

    r"\b(?:important|urgent|actionable|priority)\b[^.!?\n]{0,80}"
    r"\b(?:emails?|messages?|inbox)\b",

    r"\b(?:emails?|messages?|inbox)\b[^.!?\n]{0,80}"
    r"\b(?:important|urgent|actionable|priority|matter|matters)\b",

    # Natural "what do I need to do/respond to?" inbox phrasing.
    r"\bwhat\b[^.!?\n]{0,50}\b(?:emails?|messages?)\b[^.!?\n]{0,80}"
    r"\b(?:should|need\s+to|have\s+to)\b[^.!?\n]{0,40}"
    r"\b(?:reply|respond|act|do)\b",

    r"\bwhat\s+(?:should|do)\s+i\s+(?:reply|respond)\b",

    # Explicit workflow nouns.
    r"\binbox\s+(?:brief|review|triage)\b",
)


def is_inbox_attention_request(
    user_input,
):
    """
    True when Oliver wants judgement/triage over inbox messages rather than
    a literal sender/topic existence search.

    This helper is shared by Core intent routing and the provider's constrained
    Gmail workflow so one layer cannot reinterpret an attention request as a
    targeted search before the other layer sees it.
    """

    text = re.sub(
        r"\s+",
        " ",
        str(
            user_input
            or ""
        ).strip().lower(),
    )

    if not text:
        return False

    # Common compact forms that are easier to express semantically than with
    # the broader relation patterns above.
    compact_phrases = (
        "need my attention",
        "needs my attention",
        "need attention",
        "needs attention",
        "important emails",
        "important email",
        "need to act",
        "needs action",
        "need action",
        "action required",
        "actionable emails",
        "actionable email",
        "what should i respond",
        "what do i need to respond",
        "inbox brief",
        "inbox review",
        "inbox triage",
    )

    if any(
        phrase in text
        for phrase in compact_phrases
    ):
        return True

    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        is not None
        for pattern in EMAIL_ATTENTION_PATTERNS
    )
