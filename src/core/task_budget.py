"""Conservative, user-evidence-only time-budget reasoning.

Handles an explicit total and individually named durations supplied by the user.
Later corrections replace the named quantity; an explicit new delay adds to the
named duration for the current hypothetical. Missing or ambiguous inputs return
None and stay with normal conversation handling. No web calls or persisting
model-generated calculations as evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

NUM = r"\d+(?:\.\d+)?"
UNIT = r"(?:minutes?|mins?|hours?|hrs?)"
BUDGET = re.compile(
    rf"\b(?:have|got|budget(?:\s+of)?|available|exactly|limit(?:\s+of)?)\b"
    rf"[^.?!]{{0,35}}?\b(?P<amount>{NUM})\s*(?P<unit>{UNIT})\b", re.I,
)
TIME_QUESTION = re.compile(
    r"\b(?:can\s+(?:we|i)\s+(?:do|fit|make)|does\s+(?:it|that)\s+fit|"
    r"will\s+(?:it|that)\s+fit|would\s+(?:it|that)\s+fit|"
    r"(?:be|are|is)\s+(?:we|it|that)\s+(?:within|over|under)|"
    r"how\s+much\s+time\s+(?:left|spare)|"
    r"and\s+if\b|what\s+if\b)\b", re.I,
)
STRONG_RESET = re.compile(
    r"^\s*(?:anyway|new\s+topic|different\s+topic|unrelated|random\s+tangent|side\s+note)\b", re.I,
)
EXTERNAL_REQUEST = re.compile(
    r"\b(?:look\s+up|search\s+online|google\s+maps|check\s+(?:live|current)|"
    r"book\s+(?:my|the)|add\s+to\s+(?:my|the)\s+calendar)\b", re.I,
)
CLAUSE = re.compile(r"\s*(?:,|;|\.(?=\s)|\band\s+(?=[A-Za-z][\w -]{0,28}\s+\d))\s*", re.I)
ITEM = re.compile(
    rf"^\s*(?P<label>[A-Za-z][A-Za-z0-9 -]{{0,29}}?)\s+"
    rf"(?:(?:is|takes|=)\s+)?(?P<amount>{NUM})\s*(?P<unit>{UNIT})?\s*$", re.I,
)
CORRECTION = re.compile(
    rf"(?:\b(?:scratch\s+that|correction|actually|wait)\b[^,.:;]{{0,20}}[,.:;]?\s*)?"
    rf"(?P<label>[A-Za-z][A-Za-z0-9 -]{{0,25}}?)\s+(?:is|takes|=)\s+"
    rf"(?P<amount>{NUM})\s*(?P<unit>{UNIT})?\s+(?:not|instead\s+of)\s+(?:{NUM})\b", re.I,
)
DELAY = re.compile(
    rf"\b(?P<label>[A-Za-z][A-Za-z0-9 -]{{0,25}}?)\s+"
    rf"(?:is|gets?|got|was|will\s+be)?\s*delayed\s+by\s+"
    rf"(?P<amount>{NUM})\s*(?P<unit>{UNIT})?\b", re.I,
)


@dataclass(frozen=True)
class TimeBudgetResolution:
    answer: str
    budget_minutes: Decimal
    used_minutes: Decimal
    items: tuple[tuple[str, Decimal], ...]
    delay_minutes: Decimal = Decimal(0)
    delay_target: Optional[str] = None


def _minutes(number: str, unit: str | None) -> Optional[Decimal]:
    try:
        value = Decimal(str(number))
        if not value.is_finite() or value < 0 or value > 100000:
            return None
        if unit and unit.lower().startswith(("hour", "hr")):
            value *= 60
        return value
    except (InvalidOperation, ValueError):
        return None


def _fmt(num: Decimal) -> str:
    return format(num.normalize(), "f")


def _key(label: str) -> str:
    text = " ".join(str(label or "").lower().split())
    return re.sub(r"\b(?:the|an|there|for|our|my|that|and|if)\b", "", text).strip()


def _parse_initial(text: str) -> Optional[tuple[Decimal, dict[str, Decimal]]]:
    match = BUDGET.search(text)
    if not match:
        return None
    budget = _minutes(match["amount"], match["unit"])
    if budget is None:
        return None
    # Only clauses following the explicit total can become task items; no
    # arbitrary numbers from earlier unrelated parts of the user message.
    tail = text[match.end():].strip(" .,:;\n")
    tail = re.split(r"\b(?:can\s+(?:we|i)\s+do|does\s+it\s+fit|will\s+it\s+fit)\b", tail, 1, flags=re.I)[0]
    durations: dict[str, Decimal] = {}
    for raw in CLAUSE.split(tail):
        fragment = raw.strip(" .,:;\n")
        if not fragment:
            continue
        item = ITEM.fullmatch(fragment)
        if not item:
            return None
        label = _key(item["label"])
        value = _minutes(item["amount"], item["unit"])
        if not label or value is None or label in durations:
            return None
        durations[label] = value
    if not 2 <= len(durations) <= 6:
        return None
    return budget, durations


def _name_in_items(candidate: str, names: dict[str, Decimal]) -> Optional[str]:
    clean = _key(candidate)
    if clean in names:
        return clean
    # Do not guess when multiple items share a token (e.g. train there/train back).
    hits = [name for name in names if name == clean or name.endswith(" " + clean)]
    return hits[0] if len(hits) == 1 else None


def resolve_time_budget(
    current_user_text: str,
    recent_user_turns: list[dict[str, Any]] | None = None,
) -> Optional[TimeBudgetResolution]:
    """Compute only when the current question and recent USER facts suffice."""
    current = str(current_user_text or "").strip()
    if not current or STRONG_RESET.search(current) or EXTERNAL_REQUEST.search(current):
        return None
    turns = [str(item.get("text") or "").strip() for item in (recent_user_turns or [])[-5:]
             if isinstance(item, dict) and str(item.get("text") or "").strip()]
    all_turns = turns + [current]
    starts = [(i, parsed) for i, text in enumerate(all_turns)
              if (parsed := _parse_initial(text)) is not None]
    if not starts:
        return None
    start_index, parsed = starts[-1]
    if any(STRONG_RESET.search(t) for t in all_turns[start_index+1:-1]):
        return None
    # Later questions without a clear connection to the established budget
    # should NOT resurrect the stale figures merely because a budget exists.
    has_current_cue = bool(
        TIME_QUESTION.search(current) or
        (start_index == len(all_turns)-1 and "?" in current) or
        (re.search(r"\b(?:delayed|delay)\b", current, re.I) and "?" in current)
    )
    if not has_current_cue:
        return None
    budget, durations = parsed
    new_delay = Decimal(0)
    delay_target: Optional[str] = None
    for index, text in enumerate(all_turns[start_index+1:], start=start_index+1):
        # Apply exactly one unambiguous named correction in each turn.
        correction = CORRECTION.search(text)
        if correction:
            name = _name_in_items(correction["label"], durations)
            value = _minutes(correction["amount"], correction["unit"])
            if name is None or value is None:
                return None
            durations[name] = value
        # A new hypothetical delay applies to the current calculation rather
        # than silently accumulating all earlier hypothetical questions.
        delay = DELAY.search(text)
        if delay:
            name = _name_in_items(delay["label"], durations)
            amount = _minutes(delay["amount"], delay["unit"])
            if name is None or amount is None:
                return None
            if index == len(all_turns)-1:
                new_delay = amount
                delay_target = name
        # A turn with an unrecognised revision should not silently be ignored.
        elif re.search(r"\b(?:scratch\s+that|correction)\b", text, re.I) and not correction:
            return None
    if delay_target:
        durations[delay_target] += new_delay
    used = sum(durations.values(), Decimal(0))
    diff = abs(used-budget)
    expression = " + ".join(_fmt(x) for x in durations.values())
    detail = f"{expression} = {_fmt(used)} minutes against your {_fmt(budget)}-minute limit"
    if used > budget:
        answer = f"No. {detail}, so you're {_fmt(diff)} minutes over."
    elif used < budget:
        answer = f"Yes. {detail}, leaving {_fmt(diff)} minutes spare."
    else:
        answer = f"Yes, exactly. {detail}, with no extra time left."
    if delay_target:
        answer = f"With the {_fmt(new_delay)}-minute delay: {answer}"
    return TimeBudgetResolution(answer, budget, used, tuple(durations.items()), new_delay, delay_target)
