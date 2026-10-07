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
    value = str(
        text
        or ""
    ).translate({
        0x2018: ord("'"),
        0x2019: ord("'"),
        0x02BC: ord("'"),
    }).strip()

    return re.sub(
        r"\s+",
        " ",
        value,
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



def infer_consequential_actor_role(
    text: str,
    domain: Optional[str] = None,
) -> Optional[str]:
    """Infer Oliver's role in a bounded consequential incident.

    This is deliberately conservative. It only resolves roles that Oliver
    states directly; otherwise Core leaves the role unknown rather than
    inventing who controls the affected asset/account.
    """

    if str(domain or "").strip().lower() != "financial":
        return None

    value = _normalise(text).lower()

    if re.search(
        r"\b(?:i|we)\b[^.!?]{0,45}\b(?:sent|transferred|wired|paid)\b"
        r"[^.!?]{0,90}\b(?:wrong|incorrect)\b",
        value,
        flags=re.IGNORECASE,
    ):
        return "mistaken_sender"

    if (
        re.search(
            r"\b(?:someone|they|a person|another person)\b[^.!?]{0,60}"
            r"\b(?:sent|transferred|wired|paid)\b[^.!?]{0,45}\b(?:me|us)\b"
            r"[^.!?]{0,60}\b(?:mistake|accident|wrong)\b",
            value,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"\b(?:money|funds|payment|transfer)\b[^.!?]{0,60}"
            r"\b(?:appeared|showed up|landed|arrived|was sent)\b[^.!?]{0,45}"
            r"\b(?:my|our)\s+(?:bank\s+)?account\b",
            value,
            flags=re.IGNORECASE,
        )
    ):
        return "mistaken_recipient"

    return None


def find_consequential_role_violations(
    user_input: str,
    draft: str,
    *,
    domain: Optional[str] = None,
) -> list[str]:
    """Reject advice that flips Oliver's explicitly stated incident role."""

    role = infer_consequential_actor_role(
        user_input,
        domain=domain,
    )

    value = _normalise(draft).lower()

    if not value or role is None:
        return []

    violations = []

    if role == "mistaken_sender":
        # A sender no longer controls funds that reached the unintended
        # recipient. Instructions to avoid spending/touching/moving those
        # funds silently turn Oliver into the recipient.
        sender_control_pattern = (
            r"\b(?:do\s+not|don't|dont|stop|avoid|be\s+careful\s+not\s+to|"
            r"make\s+sure\s+you\s+do\s+not|make\s+sure\s+you\s+don't)\b"
        )
        if re.search(
            sender_control_pattern
            + r"[^.!?]{0,55}\b(?:touch|touching|spend|spending|move|moving|withdraw|"
            r"withdrawing|use|using|freeze)\b[^.!?]{0,70}"
            r"\b(?:money|funds|transfer|it|accounts?|affected\s+accounts?)\b",
            value,
            flags=re.IGNORECASE,
        ) or re.search(
            r"\b(?:money|funds)\b[^.!?]{0,35}\b(?:in|into)\s+your\s+"
            r"(?:bank\s+)?account\b",
            value,
            flags=re.IGNORECASE,
        ) or re.search(
            sender_control_pattern
            + r"[^.!?]{0,55}\b(?:touch|move|withdraw|use|freeze)\b[^.!?]{0,70}"
            r"\b(?:your\s+|the\s+|any\s+)?(?:affected\s+)?(?:bank\s+)?accounts?\b",
            value,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "consequential advice flipped Oliver from mistaken sender to recipient/control-holder"
            )

        # Provider-neutral first action for a mistaken outgoing transfer is to
        # contact the bank/payment provider that sent it. Directly contacting
        # the unintended recipient may be appropriate for some rails/providers,
        # but it must not displace the sender-side provider as the first recovery
        # channel when provider/jurisdiction details are unknown.
        recipient_contact = re.search(
            r"\b(?:contact|call|message|reach\s+out\s+to)\b[^.!?]{0,45}"
            r"\b(?:the\s+)?(?:recipient|person\s+you\s+sent\s+(?:it|money|funds)\s+to)\b",
            value,
            flags=re.IGNORECASE,
        )
        provider_contact = re.search(
            r"\b(?:contact|call|report\s+(?:it\s+)?to|reach\s+out\s+to)\b[^.!?]{0,55}"
            r"\b(?:your\s+)?(?:bank|payment\s+provider|financial\s+institution|provider)\b",
            value,
            flags=re.IGNORECASE,
        )
        if recipient_contact and (
            provider_contact is None
            or recipient_contact.start() < provider_contact.start()
        ):
            violations.append(
                "mistaken-sender advice told Oliver to contact the recipient before the sending bank/payment provider"
            )

    elif role == "mistaken_recipient":
        if re.search(
            r"\b(?:recall|reverse|cancel|stop)\b[^.!?]{0,40}\b(?:the\s+)?transfer\b"
            r"[^.!?]{0,40}\b(?:you|your)\b",
            value,
            flags=re.IGNORECASE,
        ):
            violations.append(
                "consequential advice flipped Oliver from mistaken recipient to sender"
            )

    return violations


def build_consequential_advice_instruction(
    *,
    domain: Optional[str],
    user_input: Optional[str] = None,
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

    actor_role = infer_consequential_actor_role(
        user_input or "",
        domain=domain,
    )

    role_instruction = ""

    if actor_role == "mistaken_sender":
        role_instruction = (
            "- Oliver explicitly described himself as the SENDER of the mistaken "
            "payment/transfer. Preserve that actor direction. Do not tell him not "
            "to spend, touch, withdraw, move, or freeze money/accounts as though the "
            "mistaken funds were sitting in his account. A mistaken outgoing transfer "
            "does not by itself mean his own bank accounts must be frozen or left untouched. "
            "Make the sending bank/payment provider the first recovery contact when provider "
            "or jurisdiction details are unknown; do not lead with contacting the unintended recipient.\n"
        )
    elif actor_role == "mistaken_recipient":
        role_instruction = (
            "- Oliver explicitly described himself as the RECIPIENT of a mistaken "
            "payment/transfer. Preserve that actor direction; do not describe him "
            "as the person who initiated/sent the transfer.\n"
        )

    return (
        "CORE CONSEQUENTIAL ADVICE MODE:\n"
        + role_instruction
        + "- This is a high-seriousness "
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
        "pull your head out",
        "take a breath",
        "calm down",
        "freeze up",
        "stare at a screen",
        "staring at a screen",
        "don't just freeze",
        "dont just freeze",
        "lmao",
        " lol ",
        "😂",
        "🤣",
    )

    violations = [
        (
            "consequential advice used banter, blame, or "
            "emotional-management language: "
            + marker
        )
        for marker in markers
        if marker in value
    ]

    blame_patterns = (
        r"\boh,?\s+great\b",
        r"\byou(?:'re| are)\b[^.!?]{0,80}\bpanic(?:king|ked)?\b",
        r"\bdon['’]?t\s+worry\b",
        r"\bnot\s+a\s+good\s+(?:start|look)\b",
        r"\bi\s+hope\s+it(?:'s| is)\s+not\b[^.!?]{0,90}"
        r"\b(?:massive|huge|large|life[- ]?changing|rainy\s+day|savings)\b",
        r"\b(?:massive|huge|large)\s+(?:sum|amount)\b[^.!?]{0,90}"
        r"\b(?:rainy\s+day|savings)\b",
        r"\bclassic\s+(?:way|move|mistake)\b[^.!?]{0,80}\b(?:lose|lost|send|transfer|money|payment)\b",
        r"\b(?:hit|clicked|pressed|sent|transferred|paid)\b[^.!?]{0,90}\bbefore\b[^.!?]{0,50}\b(?:check|checking|double[- ]?check|verify|verifying)\b",
        r"\byou\b[^.!?]{0,60}\b(?:should(?:'ve| have)|could(?:'ve| have))\b[^.!?]{0,60}\b(?:check|verify|notice|catch)\b",
    )
    for pattern in blame_patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            violations.append(
                "consequential advice used banter, blame, or emotional-management language: "
                + match.group(0)
            )

    return list(dict.fromkeys(violations))
