from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.workflow_result import (
    WorkflowResult,
)
from tools.tool_registry import (
    execute_tool,
)


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
    "internal_date_ms",
}


def _normalise(
    value: Any,
) -> str:
    return " ".join(
        str(
            value or ""
        ).strip().split()
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
            or "id" in keys
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
    Accept several plausible gmail_tools.py return shapes instead of
    coupling Core to one wrapper key.
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

    unique = []
    seen = set()

    for item in found:
        message_id = _first_value(
            item,
            "message_id",
            "id",
        )

        signature = (
            ("id", message_id)
            if message_id
            else (
                "text",
                _first_value(
                    item,
                    "sender",
                    "from",
                    "from_address",
                ),
                _first_value(
                    item,
                    "subject",
                ),
                _first_value(
                    item,
                    "date",
                    "received_at",
                ),
            )
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


def _window_phrase(
    days: int,
    time_scope: str,
) -> str:
    if time_scope == "today":
        return "today"

    if time_scope == "yesterday":
        return "yesterday"

    if days == 1:
        return "the last day"

    if days == 2:
        return "the last 2 days"

    return (
        f"the last {days} days"
    )


def _window_clause(
    days: int,
    time_scope: str,
) -> str:
    phrase = _window_phrase(
        days,
        time_scope,
    )

    if time_scope in {
        "today",
        "yesterday",
    }:
        return phrase

    return (
        "in "
        + phrase
    )


def _exact_local_day_bounds(
    time_scope: str,
    now: Optional[datetime] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """
    Return epoch-second boundaries for an exact local calendar day.

    datetime.now().astimezone() uses the machine's configured local
    timezone. On Oliver's PC/Pi deployment this is the intended Mairon
    local timezone.

    Epoch boundaries are sent to Gmail's after:/before: operators so
    "yesterday" means the previous local calendar day rather than a vague
    rolling 48-hour window.
    """

    if time_scope not in {
        "today",
        "yesterday",
    }:
        return (
            None,
            None,
        )

    current = (
        now.astimezone()
        if now is not None
        else datetime.now().astimezone()
    )

    today_start = current.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    if time_scope == "today":
        start = today_start
        end = (
            today_start
            + timedelta(
                days=1
            )
        )

    else:
        end = today_start
        start = (
            today_start
            - timedelta(
                days=1
            )
        )

    return (
        int(
            start.timestamp()
        ),
        int(
            end.timestamp()
        ),
    )


def _filter_exact_window(
    emails: List[Dict[str, Any]],
    after_epoch: Optional[int],
    before_epoch: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Verify Gmail results against message.internalDate when available.

    Gmail's server-side after:/before: query is already authoritative, but
    checking internalDate gives Core an additional deterministic guard
    against timezone/header weirdness. Messages without internalDate are
    retained because older/fake tool outputs may not expose it.
    """

    if (
        after_epoch is None
        and before_epoch is None
    ):
        return emails

    filtered = []

    for email in emails:
        raw_internal = email.get(
            "internal_date_ms"
        )

        if raw_internal in {
            None,
            "",
        }:
            filtered.append(
                email
            )
            continue

        try:
            internal_epoch = (
                int(
                    raw_internal
                )
                // 1000
            )

        except (
            TypeError,
            ValueError,
        ):
            filtered.append(
                email
            )
            continue

        if (
            after_epoch is not None
            and internal_epoch < after_epoch
        ):
            continue

        if (
            before_epoch is not None
            and internal_epoch >= before_epoch
        ):
            continue

        filtered.append(
            email
        )

    return filtered


def _email_description(
    email: Dict[str, Any],
) -> str:
    sender = _first_value(
        email,
        "sender",
        "from",
        "from_address",
    )

    subject = _first_value(
        email,
        "subject",
    )

    date = _first_value(
        email,
        "date",
        "received_at",
    )

    pieces = []

    if subject:
        pieces.append(
            f'"{subject}"'
        )

    if sender:
        pieces.append(
            f"from {sender}"
        )

    if date:
        pieces.append(
            f"({date})"
        )

    return " ".join(
        pieces
    ).strip()


def search_email(
    search_text: str,
    days: int = 30,
    max_results: int = 10,
    time_scope: str = "rolling_days",
    now: Optional[datetime] = None,
) -> WorkflowResult:
    """
    Deterministic targeted Gmail lookup.

    This handles questions such as:
    - "Have I received any emails from Prosple in the last couple days?"
    - "Did Richard from Prosple email me?"
    - "Check my emails for CyberCX."

    Core chooses find_emails directly. Qwen does not get to replace a
    targeted lookup with a generic recent-inbox summary.
    """

    search_text = _normalise(
        search_text
    )

    days = max(
        1,
        min(
            int(
                days
            ),
            365,
        ),
    )

    max_results = max(
        1,
        min(
            int(
                max_results
            ),
            20,
        ),
    )

    time_scope = str(
        time_scope
        or "rolling_days"
    ).strip().lower()

    if time_scope not in {
        "rolling_days",
        "today",
        "yesterday",
    }:
        time_scope = "rolling_days"

    (
        after_epoch,
        before_epoch,
    ) = _exact_local_day_bounds(
        time_scope=time_scope,
        now=now,
    )

    if not search_text:
        return WorkflowResult(
            success=False,
            status="missing_search_text",
            error=(
                "Email search needs a person, company, topic, or keyword."
            ),
        )

    tool_arguments = {
        "search_text": search_text,
        "days": days,
        "unread_only": False,
        "max_results": max_results,
    }

    if (
        after_epoch is not None
        or before_epoch is not None
    ):
        tool_arguments[
            "after_epoch"
        ] = after_epoch

        tool_arguments[
            "before_epoch"
        ] = before_epoch

        tool_arguments[
            "expand_search"
        ] = False

    result = execute_tool(
        "find_emails",
        tool_arguments,
    )

    if (
        isinstance(
            result,
            dict,
        )
        and result.get(
            "success"
        ) is False
    ):
        return WorkflowResult(
            success=False,
            status="gmail_search_failed",
            error=(
                result.get(
                    "message"
                )
                or "Gmail search failed."
            ),
            data={
                "search_text": search_text,
                "days": days,
                "time_scope": time_scope,
                "after_epoch": after_epoch,
                "before_epoch": before_epoch,
            },
        )

    emails = _collect_email_like_dicts(
        result
    )

    emails = _filter_exact_window(
        emails=emails,
        after_epoch=after_epoch,
        before_epoch=before_epoch,
    )

    evidence = EvidenceBundle(
        authority="gmail",
        success=True,
    )

    if not emails:
        evidence.uncertainty = (
            "No Gmail summaries matched the requested search text in the "
            "configured time window."
        )

        return WorkflowResult(
            success=True,
            status="no_match",
            answer_fact=(
                f"I couldn't find any emails matching {search_text} "
                f"{_window_clause(days, time_scope)}."
            ),
            evidence=evidence,
            data={
                "search_text": search_text,
                "days": days,
                "time_scope": time_scope,
                "after_epoch": after_epoch,
                "before_epoch": before_epoch,
                "matched_messages": 0,
            },
        )

    for email in emails:
        evidence.add(
            Evidence(
                claim=(
                    "Gmail returned a matching email summary: "
                    + (
                        _email_description(
                            email
                        )
                        or "matching message"
                    )
                ),
                provenance="gmail",
                confidence="verified",
                source_name=(
                    _first_value(
                        email,
                        "subject",
                    )
                    or _first_value(
                        email,
                        "sender",
                        "from",
                        "from_address",
                    )
                    or "Gmail"
                ),
                source_id=_first_value(
                    email,
                    "message_id",
                    "id",
                ),
                observed_at=_first_value(
                    email,
                    "date",
                    "received_at",
                ),
                data={
                    "search_text": search_text,
                    "time_scope": time_scope,
                    "after_epoch": after_epoch,
                    "before_epoch": before_epoch,
                    "subject": _first_value(
                        email,
                        "subject",
                    ),
                    "sender": _first_value(
                        email,
                        "sender",
                        "from",
                        "from_address",
                    ),
                },
            )
        )

    most_recent = emails[
        0
    ]

    description = _email_description(
        most_recent
    )

    if len(
        emails
    ) == 1:
        answer = (
            f"Yep — I found an email matching {search_text} "
            f"{_window_clause(days, time_scope)}"
        )

        if description:
            answer += (
                f": {description}"
            )

        answer += "."

    else:
        answer = (
            f"Yep — I found {len(emails)} emails matching {search_text} "
            f"{_window_clause(days, time_scope)}."
        )

        if description:
            answer += (
                f" The most recent is {description}."
            )

    return WorkflowResult(
        success=True,
        status="match_found",
        answer_fact=answer,
        evidence=evidence,
        data={
            "search_text": search_text,
            "days": days,
            "time_scope": time_scope,
            "after_epoch": after_epoch,
            "before_epoch": before_epoch,
            "matched_messages": len(
                emails
            ),
            "most_recent_subject": _first_value(
                most_recent,
                "subject",
            ),
            "most_recent_sender": _first_value(
                most_recent,
                "sender",
                "from",
                "from_address",
            ),
            "most_recent_date": _first_value(
                most_recent,
                "date",
                "received_at",
            ),
        },
    )
