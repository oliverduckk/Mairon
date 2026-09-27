"""Phase 11.6.2: bounded reasoning from user-authored premises.

Only sufficiently explicit, self-contained structures get deterministic answers.
Other premise-based questions are classified for local reasoning, never
converted into public-world queries merely because they are interrogative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SuppliedReasoning:
    kind: str
    direct_answer: str | None = None


def _minute_of_day(text: str) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*", text, re.I)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    return hour % 12 * 60 + (720 if match.group(3).lower() == "pm" else 0) + minute


def _clock(minutes: int) -> str:
    minutes %= 24 * 60
    hour, minute = divmod(minutes, 60)
    suffix = "am" if hour < 12 else "pm"
    return f"{(hour % 12) or 12}:{minute:02d}{suffix}"


_TIME = r"\d{1,2}(?::\d{2})?\s*(?:am|pm)"


def _schedule_answer(text: str) -> str | None:
    """Conservatively solve a complete appointment + transit + arrival buffer."""
    appointment = re.search(rf"\b(?:appointment|meeting|event)\b[^.!?]{{0,60}}?\b(?:at|for)\s+(?P<clock>{_TIME})", text, re.I)
    drive = re.search(r"\b(?:drive|journey|trip|travel)\s+(?:takes?|will take|is)\s+(?P<minutes>\d{1,3})\s+minutes?\b", text, re.I)
    early = re.search(r"\b(?:arrive|get there|be there)\s+(?P<minutes>\d{1,3})\s+minutes?\s+early\b", text, re.I)
    leave = re.search(rf"\b(?:leave|depart)\s+at\s+(?P<clock>{_TIME})", text, re.I)
    if not all((appointment, drive, early, leave)):
        return None
    appointment_at = _minute_of_day(appointment.group("clock"))
    leaving_at = _minute_of_day(leave.group("clock"))
    if appointment_at is None or leaving_at is None:
        return None
    travel = int(drive.group("minutes"))
    buffer = int(early.group("minutes"))
    if travel > 240 or buffer > 120:
        return None
    latest_departure = appointment_at - travel - buffer
    arrival_at = leaving_at + travel
    arrival_target = appointment_at - buffer
    if leaving_at <= latest_departure:
        return (
            f"Yes. To arrive {buffer} minutes early, leave no later than "
            f"{_clock(latest_departure)}. Leaving at {_clock(leaving_at)} "
            f"gets you there around {_clock(arrival_at)}."
        )
    return (
        f"No. To arrive {buffer} minutes early, you need to leave by "
        f"{_clock(latest_departure)}. Leaving at {_clock(leaving_at)} "
        f"would get you there around {_clock(arrival_at)}."
    )


def _categorical_exclusion_answer(text: str) -> str | None:
    """A⊆B and B∩C=∅ entails A∩C=∅, irrespective of labels."""
    word = r"[a-z][a-z'-]*"
    premise = re.search(
        rf"\b(?:every|all)\s+(?P<a>{word})\s+(?:is|are)\s+(?:an?\s+)?(?P<b>{word})"
        rf"\s*[,.;]\s*(?:and\s+)?no\s+(?P<b2>{word})\s+(?:is|are)\s+(?P<property>{word})",
        text, re.I,
    )
    question = re.search(rf"\bcan\s+any\s+(?P<a>{word})\s+be\s+(?P<property>{word})\s*\?", text, re.I)
    if not premise or not question:
        return None
    if (premise.group("b").lower() != premise.group("b2").lower()
            or premise.group("a").lower() != question.group("a").lower()
            or premise.group("property").lower() != question.group("property").lower()):
        return None
    return (f"No. Every {premise.group('a')} is a {premise.group('b')}, "
            f"and no {premise.group('b')} is {premise.group('property')}, "
            f"so no {premise.group('a')} can be {premise.group('property')}.")


def classify_supplied_reasoning(text: str) -> SuppliedReasoning | None:
    """Identify self-contained reasoning, not arbitrary factual or advice prompts."""
    value = str(text or "").strip()
    if not value:
        return None
    # Reject explicit public-source requests: they belong to verification.
    if re.search(r"\b(?:search the web|look (?:it )?up|verify (?:online|with sources)|latest|currently)\b", value, re.I):
        return None

    # A complete schedule question can be solved with no current traffic or
    # calendar access. Incomplete timings must not be guessed.
    if (re.search(r"\b(?:appointment|meeting|event)\b", value, re.I)
            and re.search(r"\b(?:drive|journey|trip|travel)\s+(?:takes?|will take|is)\b", value, re.I)
            and re.search(r"\b(?:early|late)\b", value, re.I)
            and re.search(r"\b(?:leave|depart)\s+at\b", value, re.I)
            and "?" in value):
        return SuppliedReasoning(kind="schedule", direct_answer=_schedule_answer(value))

    if (re.search(r"\b(?:every|all)\b", value, re.I)
            and re.search(r"\bno\b", value, re.I)
            and re.search(r"\bcan\s+any\b", value, re.I)
            and "?" in value):
        return SuppliedReasoning(kind="logic", direct_answer=_categorical_exclusion_answer(value))

    # Code-trace questions combine user-supplied program state with stable
    # language semantics, and don't require browsing current public facts.
    if (re.search(r"\b(?:in\s+)?python\b", value, re.I)
            and re.search(r"\b(?:if\s+i\s+run|what\s+(?:is|will|would|does|happens))\b", value, re.I)
            and ("=" in value or re.search(r"\b(?:code|snippet)\b", value, re.I))
            and "?" in value):
        return SuppliedReasoning(kind="code_trace")
    return None
