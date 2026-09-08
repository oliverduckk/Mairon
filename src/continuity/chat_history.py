from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional


HISTORY_GROUP_ORDER = (
    "TODAY",
    "YESTERDAY",
    "PREVIOUS 7 DAYS",
    "OLDER",
)


def _parse_timestamp(
    value,
) -> Optional[datetime]:
    text = str(
        value
        or ""
    ).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text
        )
    except Exception:
        return None


def history_group_label(
    updated_at,
    *,
    now: Optional[datetime] = None,
) -> str:
    """
    Return the ChatGPT-style local-history bucket for one session timestamp.

    Session timestamps are already stored with Mairon's configured timezone.
    When no explicit reference time is provided, compare against "now" in the
    timestamp's own timezone so day boundaries do not silently drift.
    """

    updated = _parse_timestamp(
        updated_at
    )

    if updated is None:
        return "OLDER"

    reference = now

    if reference is None:
        if updated.tzinfo is not None:
            reference = datetime.now(
                updated.tzinfo
            )
        else:
            reference = datetime.now()

    elif (
        updated.tzinfo is not None
        and reference.tzinfo is None
    ):
        reference = reference.replace(
            tzinfo=updated.tzinfo
        )

    elif (
        updated.tzinfo is not None
        and reference.tzinfo is not None
    ):
        reference = reference.astimezone(
            updated.tzinfo
        )

    age_days = (
        reference.date()
        - updated.date()
    ).days

    if age_days <= 0:
        return "TODAY"

    if age_days == 1:
        return "YESTERDAY"

    if age_days <= 7:
        return "PREVIOUS 7 DAYS"

    return "OLDER"


def group_chat_sessions(
    sessions: Iterable[dict],
    *,
    now: Optional[datetime] = None,
) -> list[tuple[str, list[dict]]]:
    """
    Group already-recency-sorted chat session summaries without reordering
    sessions inside each bucket.
    """

    grouped = {
        name: []
        for name in HISTORY_GROUP_ORDER
    }

    for session in list(
        sessions
        or []
    ):
        label = history_group_label(
            session.get(
                "updated_at",
                "",
            ),
            now=now,
        )

        grouped[
            label
        ].append(
            session
        )

    return [
        (
            name,
            grouped[name],
        )
        for name in HISTORY_GROUP_ORDER
        if grouped[name]
    ]
