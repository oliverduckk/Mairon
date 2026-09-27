"""Calendar approval-proposal validation (Phase 11.6.4).

A tool call from a language model is an *untrusted suggestion*. Before
showing an actionable Calendar approval, resolve clearly specified dates and
times from the original user message using Core's configured local clock.
Never infer an ambiguous date/time from the model's proposed ISO strings.

Only a conservative subset of normal calendar phrasing is handled here. If
Core cannot interpret an explicit date/time with confidence, ask the user to
clarify rather than approving an unchecked guess. This module NEVER writes to
Calendar and never bypasses the separate approval step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo


_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_DAY_RE = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b", re.I)
_CLOCK = r"\d{1,2}(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)?"
_RANGE_RE = re.compile(
    rf"\b(?:from|between)\s+(?P<start>{_CLOCK})\s*"
    rf"(?:to|until|through|and|[-\u2013\u2014])\s*(?P<end>{_CLOCK})(?=\W|$)",
    re.I,
)
_ALTERNATE_RANGE_RE = re.compile(
    rf"\b(?P<start>{_CLOCK})\s*(?:to|until|[-\u2013\u2014])\s*"
    rf"(?P<end>{_CLOCK})(?=\W|$)", re.I,
)
_AT_TIME_RE = re.compile(rf"\bat\s+(?P<start>{_CLOCK})(?=\W|$)", re.I)
_CLOCK_RE = re.compile(r"^(?P<hour>\d{1,2})(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?$", re.I)
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_LABEL = r"(?:" + "|".join(_MONTHS) + r")"
# Month words disambiguate dates without guessing US/Australian numeric order.
_NATURAL_DATE = re.compile(
    rf"\b(?:(?P<day_first>\d{{1,2}})(?:st|nd|rd|th)?\s+"
    rf"(?P<month_second>{_MONTH_LABEL})|"
    rf"(?P<month_first>{_MONTH_LABEL})\s+"
    rf"(?P<day_second>\d{{1,2}})(?:st|nd|rd|th)?)"
    rf"(?:\s*,?\s+(?P<year>20\d{{2}}))?\b", re.I,
)


class CalendarProposalError(ValueError):
    """The proposed action cannot be safely reconciled with the user text."""


@dataclass(frozen=True)
class ValidatedCalendarProposal:
    action: dict[str, Any]
    corrected: bool
    explanation: str


def _parse_clock(raw: str, *, inherit_meridiem: str | None = None) -> time:
    match = _CLOCK_RE.fullmatch(str(raw).strip())
    if match is None:
        raise CalendarProposalError("I couldn't safely interpret the requested clock time.")
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or "0")
    meridiem = match.group("ampm") or inherit_meridiem
    if meridiem:
        meridiem = meridiem.lower().replace(".", "")
        if not 1 <= hour <= 12:
            raise CalendarProposalError("The requested 12-hour clock time is invalid.")
        hour = (hour % 12) + (12 if meridiem == "pm" else 0)
    else:
        if not 0 <= hour <= 23:
            raise CalendarProposalError("The requested 24-hour clock time is invalid.")
        # "3:00" by itself could mean 3am or 3pm. Genuine 24-hour clock
        # notation (15:00 or 03:00) is unambiguous; otherwise ask.
        if ":" in raw and 1 <= hour <= 12 and not raw.strip().startswith("0"):
            raise CalendarProposalError("Please specify AM/PM for that clock time.")
    return time(hour, minute)


def _explicit_times(user_text: str) -> tuple[time, time] | None:
    # ISO dates contain hyphens and numbers. Mask them before recognising
    # shorthand clock ranges, or "2026-10-02" could look like "10-02".
    clock_text = _ISO_DATE_RE.sub(" ", user_text)
    match = _RANGE_RE.search(clock_text) or _ALTERNATE_RANGE_RE.search(clock_text)
    if match is not None:
        start_raw, end_raw = match.group("start"), match.group("end")
        start_match = _CLOCK_RE.fullmatch(start_raw.strip())
        end_match = _CLOCK_RE.fullmatch(end_raw.strip())
        if start_match is None or end_match is None:
            return None
        start_am_pm = start_match.group("ampm")
        end_am_pm = end_match.group("ampm")
        start_hour, end_hour = int(start_match.group("hour")), int(end_match.group("hour"))
        # Don't invent a missing AM/PM across a possible noon/midnight
        # rollover. "3 to 4pm" is clear, but "11 to 1pm" is not.
        if bool(start_am_pm) != bool(end_am_pm):
            if end_hour <= start_hour or (not end_am_pm and end_hour == 12):
                raise CalendarProposalError(
                    "Please specify AM/PM for both times around noon or midnight."
                )
        start = _parse_clock(start_raw, inherit_meridiem=end_am_pm)
        end = _parse_clock(end_raw, inherit_meridiem=start_am_pm)
        # "3 to 4pm" inherits pm; for an entirely unspecified "3 to 4"
        # there is no justified AM/PM decision, so ask for clarification.
        if not re.search(r"(?:a\.?m\.?|p\.?m\.?|:\d{2})", start_raw + end_raw, re.I):
            raise CalendarProposalError("Please specify AM/PM or 24-hour times.")
        return start, end

    single = _AT_TIME_RE.search(user_text)
    if single is not None:
        raw = single.group("start")
        if not re.search(r"(?:a\.?m\.?|p\.?m\.?|:\d{2})", raw, re.I):
            raise CalendarProposalError("Please specify AM/PM or a 24-hour time.")
        start = _parse_clock(raw)
        duration = timedelta(hours=1)  # Existing explicit tool default.
        duration_match = re.search(
            r"\bfor\s+(\d+(?:\.\d+)?)\s*"
            r"(hours?|hrs?|minutes?|mins?)\b", user_text, re.I,
        )
        if duration_match:
            amount = float(duration_match.group(1))
            unit = duration_match.group(2).lower()
            duration = (timedelta(hours=amount) if unit.startswith(("h",))
                        else timedelta(minutes=amount))
            if not timedelta(0) < duration <= timedelta(days=1):
                raise CalendarProposalError("The requested event duration is invalid or too long.")
        combined = datetime.combine(date(2000, 1, 1), start) + duration
        return start, combined.time()
    return None


def _explicit_date(user_text: str, now_local: datetime, start_clock: time) -> date | None:
    text = str(user_text).lower()
    iso_dates = _ISO_DATE_RE.findall(text)
    if len(set(iso_dates)) > 1:
        raise CalendarProposalError("More than one calendar date was supplied.")
    iso = None
    if iso_dates:
        try:
            iso = date.fromisoformat(iso_dates[0])
        except ValueError as exc:
            raise CalendarProposalError("The requested ISO date is invalid.") from exc

    natural = None
    natural_match = _NATURAL_DATE.search(text)
    if natural_match is not None:
        day_number = int(natural_match.group("day_first") or natural_match.group("day_second"))
        month_number = _MONTHS[(natural_match.group("month_second") or natural_match.group("month_first")).lower()]
        supplied_year = natural_match.group("year")
        initial_year = int(supplied_year) if supplied_year else now_local.year
        try:
            natural = date(initial_year, month_number, day_number)
            # Missing years mean the next future occurrence, checked against
            # the requested event clock, not the machine's UTC date.
            if not supplied_year:
                proposed = datetime.combine(natural, start_clock, tzinfo=now_local.tzinfo)
                if proposed <= now_local:
                    natural = date(initial_year + 1, month_number, day_number)
        except ValueError as exc:
            raise CalendarProposalError("The requested month/day does not form a valid date.") from exc

    relative = None
    if re.search(r"\bday after tomorrow\b", text):
        relative = now_local.date() + timedelta(days=2)
    elif re.search(r"\btomorrow\b", text):
        relative = now_local.date() + timedelta(days=1)
    elif re.search(r"\btoday\b", text):
        relative = now_local.date()

    days = {m.group(1).lower() for m in _DAY_RE.finditer(text)}
    if len(days) > 1:
        raise CalendarProposalError("The requested day of the week is ambiguous.")
    weekday = next(iter(days), None)
    if weekday and re.search(r"\b(?:this|next|coming)\s+" + weekday + r"\b", text):
        # "next Friday" means different dates to different people. A future
        # user-date selector can expand this safely, but never guess here.
        raise CalendarProposalError(
            f"Please provide the exact date you mean by '{weekday}' so I don't schedule the wrong week."
        )

    explicit = iso or natural or relative
    if iso and natural and iso != natural:
        raise CalendarProposalError("Your written dates disagree.")
    if natural and relative and natural != relative:
        raise CalendarProposalError("Your written and relative dates disagree.")
    if iso and relative and iso != relative:
        raise CalendarProposalError("The date and relative day in your request disagree.")
    if weekday and explicit and explicit.weekday() != _WEEKDAYS[weekday]:
        raise CalendarProposalError("The date and weekday in your request disagree.")

    if explicit is not None:
        return explicit
    if weekday:
        # Bare weekday: the next occurrence that is still in the future at
        # the requested time. Uses the user's real local timezone, not UTC.
        delta = (_WEEKDAYS[weekday] - now_local.weekday()) % 7
        target = now_local.date() + timedelta(days=delta)
        candidate = datetime.combine(target, start_clock, now_local.tzinfo)
        if candidate <= now_local:
            target += timedelta(days=7)
        return target
    return None


def _parse_proposed_datetime(value: Any, tz: ZoneInfo) -> datetime:
    try:
        result = datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError) as exc:
        raise CalendarProposalError("The suggested calendar date/time is invalid.") from exc
    return result.replace(tzinfo=tz) if result.tzinfo is None else result.astimezone(tz)


def _validate_local_wall_time(value: datetime) -> None:
    """Reject imaginary or ambiguous wall times during DST changes.

    Attaching ZoneInfo alone does not prove a local wall time exists. For
    example, Australia's clocks jump over 02:30 on spring-forward Sunday.
    """
    local = value.replace(tzinfo=None)
    roundtrip = value.astimezone(timezone.utc).astimezone(value.tzinfo)
    if roundtrip.replace(tzinfo=None) != local:
        raise CalendarProposalError("That local time does not exist due to daylight saving. Please choose another time.")
    alternative = value.replace(fold=1)
    if alternative.utcoffset() != value.utcoffset():
        alt_roundtrip = alternative.astimezone(timezone.utc).astimezone(value.tzinfo)
        if alt_roundtrip.replace(tzinfo=None) == local:
            raise CalendarProposalError("That local time occurs twice during daylight saving. Please provide an unambiguous time.")


def validate_calendar_proposal(
    *,
    user_input: str,
    model_arguments: Mapping[str, Any],
    timezone_name: str = "Australia/Sydney",
    now: datetime | None = None,
) -> ValidatedCalendarProposal:
    """Make a proposed approval agree with unambiguous user date/time evidence.

    The model supplies prose/title/location, but *never* determines a weekday
    or clock time that the user specified explicitly. The canonicalised action
    still requires the normal application approval; no Calendar write occurs.
    """
    tz = ZoneInfo(timezone_name)
    local_now = (now or datetime.now(tz)).astimezone(tz)
    summary = str(model_arguments.get("summary") or "").strip()
    if not summary:
        raise CalendarProposalError("Please provide an event title.")
    original = str(user_input or "").strip()
    times = _explicit_times(original)
    if not times:
        raise CalendarProposalError("Please specify an exact start time and an end time or duration.")
    start_clock, end_clock = times
    target = _explicit_date(original, local_now, start_clock)
    if target is None:
        raise CalendarProposalError("Please specify the calendar date or weekday for this event.")

    start = datetime.combine(target, start_clock, tzinfo=tz)
    end = datetime.combine(target, end_clock, tzinfo=tz)
    if end <= start:
        # The range can cross midnight when the user explicitly supplied it.
        end += timedelta(days=1)
    _validate_local_wall_time(start)
    _validate_local_wall_time(end)
    if start <= local_now:
        raise CalendarProposalError("That requested event time is already in the past. Which date did you mean?")
    if end - start > timedelta(days=1):
        raise CalendarProposalError("The proposed event duration is unclear.")

    try:
        suggested_start = _parse_proposed_datetime(model_arguments.get("start_time"), tz)
        suggested_end = _parse_proposed_datetime(model_arguments.get("end_time"), tz)
        corrected = (suggested_start != start or suggested_end != end)
    except CalendarProposalError:
        corrected = True

    # Omit invented optional fields. A suggested venue/description may be
    # copied only when it appears verbatim in the user-authored request.
    original_flat = " ".join(original.lower().split())
    def grounded_optional(name: str) -> str | None:
        candidate = " ".join(str(model_arguments.get(name) or "").split())
        return candidate if candidate and candidate.lower() in original_flat else None

    action = {
        "type": "create_calendar_event",
        "summary": summary,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "location": grounded_optional("location"),
        "description": grounded_optional("description"),
    }
    return ValidatedCalendarProposal(
        action=action,
        corrected=corrected,
        explanation=(
            "Original model timestamps were replaced with Core-validated user date/time."
            if corrected else "Model timestamps matched Core-validated user date/time."
        ),
    )
