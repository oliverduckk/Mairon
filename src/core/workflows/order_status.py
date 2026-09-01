import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.evidence import Evidence, EvidenceBundle
from core.workflow_result import WorkflowResult
from tools.tool_registry import execute_tool


STATUS_RULES = [
    (
        "ready_for_collection",
        100,
        [
            r"\bready to collect\b",
            r"\bready for collection\b",
            r"\bawaiting collection\b",
            r"\bready for pickup\b",
            r"\bready for pick[- ]?up\b",
            r"\bcollect your (?:parcel|package|order)\b",
        ],
    ),
    (
        "delivered",
        95,
        [
            r"\bhas been delivered\b",
            r"\bwas delivered\b",
            r"\bdelivered successfully\b",
            r"\bdelivery complete\b",
            r"\bmarked as delivered\b",
        ],
    ),
    (
        "out_for_delivery",
        80,
        [
            r"\bout for delivery\b",
            r"\bonboard for delivery\b",
            r"\bwith (?:the )?(?:driver|courier)\b",
            r"\bdue for delivery today\b",
        ],
    ),
    (
        "in_transit",
        60,
        [
            r"\bin transit\b",
            r"\bon the way\b",
            r"\bin our network\b",
            r"\bbeing processed\b",
            r"\barrived at (?:a |the )?(?:facility|depot)\b",
        ],
    ),
    (
        "shipped",
        40,
        [
            r"\bhas shipped\b",
            r"\bhas been shipped\b",
            r"\bshipped\b",
            r"\bdispatched\b",
            r"\bon its way\b",
        ],
    ),
    (
        "order_confirmed",
        20,
        [
            r"\border confirmed\b",
            r"\border confirmation\b",
            r"\bthanks for your order\b",
            r"\bwe(?:'ve| have) received your order\b",
        ],
    ),
]


EMAIL_FIELD_NAMES = {
    "subject",
    "snippet",
    "sender",
    "from",
    "from_address",
    "date",
    "received_at",
    "message_id",
    "id",
    "body",
    "text",
    "content",
}


def _normalise(
    value: Any,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            value or ""
        ).strip(),
    )


def _first_value(
    mapping: Dict[str, Any],
    *keys: str,
) -> Optional[str]:
    for key in keys:
        value = mapping.get(
            key
        )

        if value is None:
            continue

        text = _normalise(
            value
        )

        if text:
            return text

    return None


def _looks_email_like(
    mapping: Dict[str, Any],
) -> bool:
    keys = {
        str(
            key
        ).lower()
        for key in mapping.keys()
    }

    useful = keys & EMAIL_FIELD_NAMES

    return bool(
        (
            "subject" in keys
            or "snippet" in keys
            or "message_id" in keys
        )
        and len(
            useful
        ) >= 2
    )


def _collect_email_like_dicts(
    value: Any,
    depth: int = 0,
) -> List[Dict[str, Any]]:
    """
    Normalise several plausible Gmail-tool return shapes.

    We deliberately do not require one undocumented wrapper key. The
    workflow cares about the documented email summary fields, not the
    exact container shape used by gmail_tools.py.
    """

    if depth > 8:
        return []

    found = []

    if isinstance(
        value,
        dict,
    ):
        if _looks_email_like(
            value
        ):
            found.append(
                value
            )

        for child in value.values():
            if isinstance(
                child,
                (
                    dict,
                    list,
                    tuple,
                ),
            ):
                found.extend(
                    _collect_email_like_dicts(
                        child,
                        depth=depth + 1,
                    )
                )

    elif isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        for child in value:
            found.extend(
                _collect_email_like_dicts(
                    child,
                    depth=depth + 1,
                )
            )

    # De-duplicate by message ID when available, otherwise by a compact
    # subject/snippet signature.
    unique = []
    seen = set()

    for item in found:
        message_id = _first_value(
            item,
            "message_id",
            "id",
        )

        signature = (
            "id",
            message_id,
        ) if message_id else (
            "text",
            _first_value(
                item,
                "subject",
            ),
            _first_value(
                item,
                "snippet",
            ),
        )

        if signature in seen:
            continue

        seen.add(
            signature
        )
        unique.append(
            item
        )

    return unique


def _email_text(
    email: Dict[str, Any],
) -> str:
    pieces = [
        _first_value(
            email,
            "sender",
            "from",
            "from_address",
        ),
        _first_value(
            email,
            "subject",
        ),
        _first_value(
            email,
            "snippet",
        ),
        _first_value(
            email,
            "body",
            "text",
            "content",
        ),
    ]

    return " ".join(
        piece
        for piece in pieces
        if piece
    )


def _classify_status(
    text: str,
) -> Tuple[str, int, Optional[str]]:
    normalised = _normalise(
        text
    ).lower()

    for status, priority, patterns in STATUS_RULES:
        for pattern in patterns:
            match = re.search(
                pattern,
                normalised,
                flags=re.IGNORECASE,
            )

            if match:
                return (
                    status,
                    priority,
                    match.group(
                        0
                    ),
                )

    return (
        "unknown",
        0,
        None,
    )


def _merchant_matches(
    email: Dict[str, Any],
    merchant: str,
) -> bool:
    merchant_tokens = [
        token
        for token in re.findall(
            r"[a-z0-9]+",
            merchant.lower(),
        )
        if len(
            token
        ) >= 2
    ]

    if not merchant_tokens:
        return True

    text = _email_text(
        email
    ).lower()

    # Require all merchant tokens for short merchant names such as
    # "Hype DC". This avoids mistaking unrelated delivery mail as the
    # relevant order.
    return all(
        token in text
        for token in merchant_tokens
    )


def _status_answer(
    merchant: str,
    status: str,
) -> str:
    merchant_text = (
        merchant.strip()
        if merchant
        else "your order"
    )

    if status == "ready_for_collection":
        return (
            f"Yep — your {merchant_text} order is ready to collect."
        )

    if status == "delivered":
        return (
            f"Yep — your {merchant_text} order is marked as delivered."
        )

    if status == "out_for_delivery":
        return (
            f"Not yet — your {merchant_text} order is out for delivery."
        )

    if status == "in_transit":
        return (
            f"Not yet — your {merchant_text} order is still in transit."
        )

    if status == "shipped":
        return (
            f"Not yet — your {merchant_text} order has shipped but isn't marked as arrived."
        )

    if status == "order_confirmed":
        return (
            f"I found the {merchant_text} order confirmation, but nothing saying it has arrived yet."
        )

    return (
        f"I found email about your {merchant_text} order, but the messages I can see don't give me a clear arrival status."
    )


def _read_for_status(
    email: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    message_id = _first_value(
        email,
        "message_id",
        "id",
    )

    if not message_id:
        return None

    result = execute_tool(
        "read_email",
        {
            "message_id": message_id,
        },
    )

    if not isinstance(
        result,
        dict,
    ):
        return None

    return result


def check_order_status(
    merchant: str,
    days: int = 60,
) -> WorkflowResult:
    """
    Deterministic Gmail-backed order-status workflow.

    Qwen does not choose the Gmail tool and does not infer delivery state.
    Core searches the merchant, classifies the returned delivery language,
    and only reads a full email if the summaries are insufficient.
    """

    merchant = _normalise(
        merchant
    )

    if not merchant:
        return WorkflowResult(
            success=False,
            status="missing_merchant",
            error=(
                "Order-status workflow needs a merchant or other order identifier."
            ),
        )

    search_result = execute_tool(
        "find_emails",
        {
            "search_text": merchant,
            "days": int(
                days
            ),
            "unread_only": False,
            "max_results": 10,
        },
    )

    if isinstance(
        search_result,
        dict,
    ) and search_result.get(
        "success"
    ) is False:
        return WorkflowResult(
            success=False,
            status="gmail_search_failed",
            error=(
                search_result.get(
                    "message"
                )
                or "Gmail search failed."
            ),
            data={
                "merchant": merchant,
            },
        )

    emails = [
        email
        for email in _collect_email_like_dicts(
            search_result
        )
        if _merchant_matches(
            email,
            merchant,
        )
    ]

    if not emails:
        return WorkflowResult(
            success=True,
            status="no_matching_email",
            answer_fact=(
                f"I couldn't find recent Gmail messages matching {merchant}."
            ),
            evidence=EvidenceBundle(
                authority="gmail",
                success=True,
                uncertainty=(
                    "No matching Gmail summary was found in the configured search window."
                ),
            ),
            data={
                "merchant": merchant,
                "matched_messages": 0,
            },
        )

    classified = []

    for email in emails:
        status, priority, trigger = _classify_status(
            _email_text(
                email
            )
        )

        classified.append(
            (
                priority,
                status,
                trigger,
                email,
                None,
            )
        )

    classified.sort(
        key=lambda item: item[
            0
        ],
        reverse=True,
    )

    best = classified[
        0
    ]

    # If summaries do not answer the question, inspect at most two full
    # matching emails. We still fail closed if the body is ambiguous.
    if best[
        1
    ] == "unknown":
        expanded = []

        for item in classified[
            :2
        ]:
            email = item[
                3
            ]

            body_result = _read_for_status(
                email
            )

            if not body_result:
                continue

            body_text = (
                _email_text(
                    email
                )
                + " "
                + _normalise(
                    body_result
                )
            )

            (
                body_status,
                body_priority,
                body_trigger,
            ) = _classify_status(
                body_text
            )

            expanded.append(
                (
                    body_priority,
                    body_status,
                    body_trigger,
                    email,
                    body_result,
                )
            )

        if expanded:
            expanded.sort(
                key=lambda item: item[
                    0
                ],
                reverse=True,
            )

            if expanded[
                0
            ][
                0
            ] > best[
                0
            ]:
                best = expanded[
                    0
                ]

    (
        priority,
        status,
        trigger,
        email,
        body_result,
    ) = best

    subject = _first_value(
        email,
        "subject",
    )

    sender = _first_value(
        email,
        "sender",
        "from",
        "from_address",
    )

    message_id = _first_value(
        email,
        "message_id",
        "id",
    )

    date = _first_value(
        email,
        "date",
        "received_at",
    )

    evidence = EvidenceBundle(
        authority="gmail",
        success=True,
    )

    if status == "unknown":
        evidence.uncertainty = (
            "Matching Gmail messages were found, but Core could not identify "
            "a supported delivery-status phrase."
        )

    evidence.add(
        Evidence(
            claim=(
                (
                    f"Gmail indicates status '{status}' for the {merchant} order."
                )
                if status != "unknown"
                else (
                    f"Gmail contains recent messages about the {merchant} order, "
                    "but no unambiguous delivery status was extracted."
                )
            ),
            provenance="gmail",
            confidence=(
                "verified"
                if status != "unknown"
                else "uncertain"
            ),
            source_name=(
                subject
                or sender
                or "Gmail"
            ),
            source_id=message_id,
            observed_at=date,
            data={
                "merchant": merchant,
                "status": status,
                "matched_phrase": trigger,
                "subject": subject,
                "sender": sender,
                "used_full_body": body_result is not None,
            },
        )
    )

    return WorkflowResult(
        success=True,
        status=status,
        answer_fact=_status_answer(
            merchant=merchant,
            status=status,
        ),
        evidence=evidence,
        data={
            "merchant": merchant,
            "matched_messages": len(
                emails
            ),
            "subject": subject,
            "sender": sender,
            "message_id": message_id,
            "matched_phrase": trigger,
        },
    )
