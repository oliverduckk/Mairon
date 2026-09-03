import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney",
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)


RELATIVE_DATE_REFERENCES = (
    (
        "day after tomorrow",
        re.compile(
            r"\bday\s+after\s+tomorrow\b",
            flags=re.IGNORECASE,
        ),
        2,
    ),
    (
        "tomorrow",
        re.compile(
            r"\btomorrow\b",
            flags=re.IGNORECASE,
        ),
        1,
    ),
    (
        "yesterday",
        re.compile(
            r"\byesterday\b",
            flags=re.IGNORECASE,
        ),
        -1,
    ),
    (
        "last night",
        re.compile(
            r"\blast\s+night\b",
            flags=re.IGNORECASE,
        ),
        -1,
    ),
    (
        "today",
        re.compile(
            r"\btoday\b",
            flags=re.IGNORECASE,
        ),
        0,
    ),
    (
        "tonight",
        re.compile(
            r"\btonight\b",
            flags=re.IGNORECASE,
        ),
        0,
    ),
    (
        "this morning",
        re.compile(
            r"\bthis\s+morning\b",
            flags=re.IGNORECASE,
        ),
        0,
    ),
    (
        "this afternoon",
        re.compile(
            r"\bthis\s+afternoon\b",
            flags=re.IGNORECASE,
        ),
        0,
    ),
    (
        "this evening",
        re.compile(
            r"\bthis\s+evening\b",
            flags=re.IGNORECASE,
        ),
        0,
    ),
)


WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

WEEKDAY_PATTERN = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
    flags=re.IGNORECASE,
)

TEMPORAL_WEEKDAY_ASSERTION_PATTERN = re.compile(
    r"(?:\b(?:on|for)\s+(?:a\s+)?"
    r"(?P<weekday1>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b)"
    r"|(?:\b(?P<weekday2>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(?:morning|afternoon|evening|night)\b)"
    r"|(?:\b(?:was|is|falls?\s+on)\s+(?:a\s+)?"
    r"(?P<weekday3>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b)",
    flags=re.IGNORECASE,
)


CURRENT_DAY_EXPLICIT_PATTERN = re.compile(
    r"\b(?:today|right\s+now|currently|now)\b",
    flags=re.IGNORECASE,
)


def _coerce_now(now=None):
    if now is None:
        return datetime.now(
            LOCAL_TIMEZONE
        )

    if now.tzinfo is None:
        return now.replace(
            tzinfo=LOCAL_TIMEZONE
        )

    return now.astimezone(
        LOCAL_TIMEZONE
    )


def resolve_relative_date_references(
    user_input,
    now=None,
):
    """
    Resolve high-confidence relative calendar references in Core.

    This is deliberately about calendar semantics, not subject matter. It gives
    the language model exact dates/weekdays so it never needs to calculate or
    guess that "last night" was Tuesday/Wednesday/etc.
    """

    text = str(
        user_input
        or ""
    )

    local_now = _coerce_now(
        now
    )

    today = local_now.date()
    resolved = []
    occupied = []

    # Longer/more-specific references are declared first. Track spans so
    # "day after tomorrow" does not also emit a second "tomorrow" entry.
    for label, pattern, offset in RELATIVE_DATE_REFERENCES:
        for match in pattern.finditer(
            text
        ):
            start, end = match.span()

            if any(
                not (
                    end <= prior_start
                    or start >= prior_end
                )
                for prior_start, prior_end in occupied
            ):
                continue

            target = (
                today
                + timedelta(
                    days=offset
                )
            )

            resolved.append({
                "reference": label,
                "source_text": match.group(0),
                "date": target.isoformat(),
                "weekday": target.strftime(
                    "%A"
                ),
                "offset_days": offset,
            })

            occupied.append(
                (
                    start,
                    end,
                )
            )

    resolved.sort(
        key=lambda item: text.lower().find(
            str(
                item["source_text"]
            ).lower()
        )
    )

    return resolved


def build_relative_date_context(
    user_input,
    now=None,
):
    references = (
        resolve_relative_date_references(
            user_input=user_input,
            now=now,
        )
    )

    if not references:
        return None

    local_now = _coerce_now(
        now
    )

    lines = [
        "CORE-RESOLVED RELATIVE DATE CONTEXT:",
        (
            "Core, not the language model, is authoritative for calendar "
            "relations in this turn."
        ),
        (
            "Current local date: "
            + local_now.date().isoformat()
            + " ("
            + local_now.strftime(
                "%A"
            )
            + f") in timezone {MAIRON_TIMEZONE}."
        ),
    ]

    for reference in references:
        lines.append(
            "- '"
            + str(
                reference["source_text"]
            )
            + "' resolves to "
            + str(
                reference["date"]
            )
            + " ("
            + str(
                reference["weekday"]
            )
            + ")."
        )

    lines.extend([
        (
            "If you mention a date or weekday for one of these relative "
            "references, it MUST match Core's resolved value."
        ),
        (
            "Do not invent a weekday merely for personality or banter when "
            "the user did not ask for one."
        ),
    ])

    return "\n".join(
        lines
    )


def find_relative_date_weekday_violations(
    user_input,
    draft,
    now=None,
):
    """
    Reject high-confidence weekday contradictions for a relative date.

    The validator intentionally avoids policing every weekday occurrence. It
    checks only when Oliver supplied one unambiguous relative date reference
    and Mairon's sentence grammatically asserts a weekday about an event/time
    ("for a Tuesday", "Wednesday night", "was Monday").
    """

    references = (
        resolve_relative_date_references(
            user_input=user_input,
            now=now,
        )
    )

    if len(
        references
    ) != 1:
        return []

    expected = str(
        references[0]["weekday"]
    ).lower()

    text = str(
        draft
        or ""
    )

    violations = []

    for match in TEMPORAL_WEEKDAY_ASSERTION_PATTERN.finditer(
        text
    ):
        weekday = next(
            (
                value
                for value in match.groups()
                if value
            ),
            None,
        )

        if not weekday:
            continue

        if weekday.lower() == expected:
            continue

        violations.append(
            "relative-date weekday mismatch: Oliver's '"
            + str(
                references[0]["source_text"]
            )
            + "' resolves to "
            + str(
                references[0]["weekday"]
            )
            + ", but Mairon asserted "
            + weekday
        )

    return list(
        dict.fromkeys(
            violations
        )
    )
