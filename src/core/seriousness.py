from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


DOMAIN_PATTERNS = {
    "financial": re.compile(
        r"\b(?:bank|banking|account|transfer|transaction|payment|payid|"
        r"money|funds|card|credit\s+card|debit\s+card|charge|wire|"
        r"direct\s+debit|cash|refund)\b",
        flags=re.IGNORECASE,
    ),
    "account_security": re.compile(
        r"\b(?:account|login|password|email|device|phone|computer|"
        r"authentication|2fa|mfa|security|credential|credentials)\b",
        flags=re.IGNORECASE,
    ),
    "identity_document": re.compile(
        r"\b(?:passport|driver'?s?\s+licen[cs]e|licen[cs]e|"
        r"identity\s+card|id\s+card|identity\s+document|birth\s+certificate)\b",
        flags=re.IGNORECASE,
    ),
    "legal_official": re.compile(
        r"\b(?:court|police|fine|penalty|legal|lawyer|solicitor|"
        r"visa|immigration|tax|ato|government|official\s+notice)\b",
        flags=re.IGNORECASE,
    ),
}


INCIDENT_PATTERN = re.compile(
    r"\b(?:wrong|mistake|accident(?:al|ally)?|error|lost|stolen|missing|"
    r"hacked|hack|compromised|breach(?:ed)?|scam(?:med)?|fraud(?:ulent)?|"
    r"phish(?:ing|ed)?|unauthori[sz]ed|unknown\s+(?:charge|transaction)|"
    r"sent\s+to\s+the\s+wrong|transferred\s+to\s+the\s+wrong|"
    r"paid\s+the\s+wrong|locked\s+out|charged\s+twice|duplicate\s+charge)\b",
    flags=re.IGNORECASE,
)


ADVICE_REQUEST_PATTERNS = (
    re.compile(
        r"\bwhat\s+(?:should|do|can)\s+i\s+do\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+now\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bhow\s+(?:do|can)\s+i\s+(?:fix|recover|reverse|stop|"
        r"cancel|report|secure|replace|resolve)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bshould\s+i\s+(?:call|contact|report|cancel|freeze|"
        r"lock|block|change|replace|dispute)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|\b)(?:help|please\s+help)\b",
        flags=re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class ConsequentialAdviceAssessment:
    is_consequential: bool
    domain: Optional[str] = None
    seriousness: str = "normal"
    reason: Optional[str] = None


def _normalise(
    text: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            text
            or ""
        ).strip(),
    )


def _detect_domain(
    text: str,
) -> Optional[str]:
    value = _normalise(
        text
    )

    if not value:
        return None

    if DOMAIN_PATTERNS[
        "identity_document"
    ].search(
        value
    ):
        return "identity_document"

    if (
        DOMAIN_PATTERNS[
            "account_security"
        ].search(
            value
        )
        and re.search(
            r"\b(?:hacked|compromised|password|login|credential|"
            r"phish|breach|unauthori[sz]ed)\b",
            value,
            flags=re.IGNORECASE,
        )
    ):
        return "account_security"

    if DOMAIN_PATTERNS[
        "financial"
    ].search(
        value
    ):
        return "financial"

    if DOMAIN_PATTERNS[
        "legal_official"
    ].search(
        value
    ):
        return "legal_official"

    return None


def assess_consequential_advice(
    text: str,
) -> ConsequentialAdviceAssessment:
    """
    Detect material real-world advice requests using a conjunction:

        advice/help request
        + consequence domain
        + incident/mistake/compromise signal

    Ordinary opinions, explanations, and low-risk recommendations therefore
    remain in their normal lanes.
    """

    value = _normalise(
        text
    )

    if not value:
        return ConsequentialAdviceAssessment(
            is_consequential=False,
        )

    domain = _detect_domain(
        value
    )

    if not domain:
        return ConsequentialAdviceAssessment(
            is_consequential=False,
        )

    incident = bool(
        INCIDENT_PATTERN.search(
            value
        )
    )

    advice_request = any(
        pattern.search(
            value
        )
        for pattern in ADVICE_REQUEST_PATTERNS
    )

    if not (
        incident
        and advice_request
    ):
        return ConsequentialAdviceAssessment(
            is_consequential=False,
            domain=domain,
        )

    return ConsequentialAdviceAssessment(
        is_consequential=True,
        domain=domain,
        seriousness="high",
        reason=(
            "request asks what to do about a real-world "
            + domain.replace(
                "_",
                " ",
            )
            + " incident with potentially material consequences"
        ),
    )


def build_consequential_research_query(
    text: str,
) -> str:
    """
    Build a concise USER-authored search query while preserving the incident.
    """

    value = _normalise(
        text
    )

    if not value:
        return ""

    value = re.sub(
        r"^\s*(?:bro|bruh|mate|hey)[,:\s-]+",
        "",
        value,
        count=1,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^\s*i\s+(?:think|reckon)\s+i\s+(?:just\s+)?",
        "",
        value,
        count=1,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^\s*i\s+(?:just\s+)?",
        "",
        value,
        count=1,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\bwhat\s+(?:should|do|can)\s+i\s+do\b",
        "what to do",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"[?.!,;:]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value[:500]


def build_consequential_advice_instruction(
    *,
    domain: Optional[str],
) -> str:
    domain_label = (
        str(
            domain
            or "real-world"
        )
        .replace(
            "_",
            " ",
        )
        .strip()
    )

    return (
        "CORE CONSEQUENTIAL ADVICE MODE:\n"
        "- This is a high-seriousness "
        + domain_label
        + " incident. Help first; personality is secondary.\n"
        "- Give the most useful verified immediate actions before asking for "
        "extra details.\n"
        "- Do not roast, tease, blame, shame, lecture, or turn the incident "
        "into a joke or story.\n"
        "- Do not tell Oliver to calm down, stop panicking, take a breath, or "
        "otherwise manage his emotions.\n"
        "- Do not guarantee reversal, recovery, reimbursement, legal outcome, "
        "account restoration, or another result unless Core evidence proves it.\n"
        "- Every concrete external procedure, deadline, entitlement, or outcome "
        "must be supported by the public evidence packet.\n"
        "- If provider, jurisdiction, or account-specific details are unknown, "
        "give verified generally applicable steps first and state uncertainty "
        "briefly.\n"
        "- Do not mention routing, guardrails, evidence packets, tools, or model "
        "limitations unless Oliver explicitly asks."
    )


def find_consequential_tone_violations(
    text: str,
) -> list[str]:
    """
    Deterministic backstop for unambiguous banter/blame failure shapes.
    """

    value = _normalise(
        text
    ).lower()

    if not value:
        return []

    markers = (
        "that's on you",
        "that is on you",
        "your fault",
        "you should've",
        "you should have checked",
        "nice one genius",
        "good one genius",
        "skill issue",
        "classic you",
        "classic mistake",
        "good story for next time",
        "at least you'll have a good story",
        "at least you will have a good story",
        "stop panicking",
        "panic mode",
        "take a breath",
        "calm down",
        "lmao",
        " lol ",
        "😂",
        "🤣",
    )

    return [
        (
            "consequential advice used banter, blame, or "
            "emotional-management language: "
            + marker
        )
        for marker in markers
        if marker in value
    ]
