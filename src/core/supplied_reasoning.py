"""Phase 11.6.2: bounded reasoning from user-authored premises.

Only sufficiently explicit, self-contained structures get deterministic answers.
Other premise-based questions are classified for local reasoning, never
converted into public-world queries merely because they are interrogative.
"""

from __future__ import annotations

import ast
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



def _simple_python_mutable_default_trace_answer(text: str) -> str | None:
    """Safely solve a tiny, explicit mutable-default trace without executing code.

    This intentionally recognises only the canonical shape where a function has
    one list default, appends one literal, returns that same list, and the user
    supplies one or more ``print(f())`` calls. Anything more complex falls back
    to ordinary bounded model reasoning rather than executing arbitrary code.
    """
    value = str(text or "")
    fn_match = re.search(
        r"def\s+(?P<fn>[A-Za-z_]\w*)\s*\(\s*(?P<arg>[A-Za-z_]\w*)\s*=\s*\[\s*\]\s*\)\s*:\s*"
        r"(?P<body>[^`\n]{1,180})",
        value,
    )
    if not fn_match:
        return None

    fn = fn_match.group("fn")
    arg = fn_match.group("arg")
    body = re.sub(r"\s+", " ", fn_match.group("body").strip())

    body_match = re.fullmatch(
        rf"{re.escape(arg)}\.append\((?P<literal>[^()]+)\)\s*;\s*return\s+{re.escape(arg)}\s*",
        body,
    )
    if not body_match:
        return None

    try:
        item = ast.literal_eval(body_match.group("literal").strip())
    except (ValueError, SyntaxError):
        return None

    if not isinstance(item, (str, int, float, bool, type(None))):
        return None

    call_pattern = re.compile(
        rf"print\s*\(\s*{re.escape(fn)}\s*\(\s*\)\s*\)",
        re.IGNORECASE,
    )
    call_count = len(call_pattern.findall(value))
    if not 1 <= call_count <= 6:
        return None

    state = []
    outputs = []
    for _ in range(call_count):
        state.append(item)
        outputs.append(repr(list(state)))

    if call_count == 1:
        return f"It prints {outputs[0]}. The default list is created once and reused when no argument is supplied."

    if call_count == 2:
        return (
            f"It prints {outputs[0]} first, then {outputs[1]}. "
            "The default list is created once at function definition time, so the second call reuses the list mutated by the first."
        )

    rendered = ", ".join(outputs[:-1]) + f", then {outputs[-1]}"
    return (
        f"The calls print, in order: {rendered}. "
        "The same default list object is reused across calls when no argument is supplied."
    )


def _normalise_scalar_unit(unit: str) -> str:
    value = str(unit or "").strip().lower()
    aliases = {
        "kgs": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "grams": "g",
        "gram": "g",
        "lbs": "lb",
        "pound": "lb",
        "pounds": "lb",
    }
    return aliases.get(value, value)


def _format_scalar(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else (
        f"{value:.3f}".rstrip("0").rstrip(".")
    )


def _simple_threshold_comparison_answer(text: str) -> str | None:
    """Solve a bounded same-unit limit comparison from user-supplied numbers.

    This deliberately answers only the mathematical relation. It does not infer
    airline fees, enforcement, security screening, fit, or any other consequence
    the user did not supply.
    """
    value = str(text or "")
    if not re.search(
        r"\b(?:within|under|over|above|below|exceed(?:s|ed)?|limit)\b",
        value,
        re.IGNORECASE,
    ):
        return None

    quantity_pattern = re.compile(
        r"(?P<number>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>kg|kgs|kilograms?|g|grams?|lb|lbs|pounds?)\b",
        re.IGNORECASE,
    )
    quantities = list(quantity_pattern.finditer(value))
    if len(quantities) != 2:
        return None

    first, second = quantities
    first_unit = _normalise_scalar_unit(first.group("unit"))
    second_unit = _normalise_scalar_unit(second.group("unit"))
    if first_unit != second_unit:
        return None

    first_value = float(first.group("number"))
    second_value = float(second.group("number"))

    def before(match, width=40):
        start = max(0, match.start() - width)
        return value[start:match.start()].lower()

    def around(match, before_width=40, after_width=16):
        start = max(0, match.start() - before_width)
        end = min(len(value), match.end() + after_width)
        return value[start:end].lower()

    first_context = around(first)
    second_context = around(second)
    first_before = before(first)
    second_before = before(second)

    limit_words = r"\b(?:limit|max(?:imum)?|allow(?:s|ed)?|cap)\b"
    first_is_limit = bool(re.search(limit_words, first_context, re.IGNORECASE))
    second_is_limit = bool(re.search(limit_words, second_context, re.IGNORECASE))

    object_words = r"\b(?:bag|backpack|pack|item|luggage|case|object)\b|\bweighs?\b"
    first_is_object = bool(re.search(object_words, first_before, re.IGNORECASE))
    second_is_object = bool(re.search(object_words, second_before, re.IGNORECASE))

    if first_is_limit and not second_is_limit:
        limit, actual = first_value, second_value
    elif second_is_limit and not first_is_limit:
        limit, actual = second_value, first_value
    elif second_is_object and not first_is_object:
        # Natural shape: "airline says 7kg, bag is 9kg".
        limit, actual = first_value, second_value
    elif first_is_object and not second_is_object:
        limit, actual = second_value, first_value
    else:
        return None

    unit = first_unit
    difference = actual - limit
    if abs(difference) < 1e-12:
        return (
            f"Yes. {_format_scalar(actual)} {unit} is exactly the "
            f"{_format_scalar(limit)} {unit} limit."
        )
    if difference < 0:
        return (
            f"Yes. {_format_scalar(actual)} {unit} is "
            f"{_format_scalar(abs(difference))} {unit} under the "
            f"{_format_scalar(limit)} {unit} limit."
        )
    return (
        f"No. {_format_scalar(actual)} {unit} is "
        f"{_format_scalar(difference)} {unit} over the "
        f"{_format_scalar(limit)} {unit} limit."
    )

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

    threshold_answer = _simple_threshold_comparison_answer(value)
    if threshold_answer is not None:
        return SuppliedReasoning(
            kind="threshold_comparison",
            direct_answer=threshold_answer,
        )

    # Code-trace questions combine user-supplied program state with stable
    # language semantics, and don't require browsing current public facts.
    if (re.search(r"\b(?:in\s+)?python\b", value, re.I)
            and re.search(
                r"\b(?:if\s+i\s+run|what\s+(?:is|will|would|does|happens|prints?))\b",
                value,
                re.I,
            )
            and ("=" in value or re.search(r"\b(?:code|snippet|print\s*\()\b", value, re.I))
            and "?" in value):
        return SuppliedReasoning(
            kind="code_trace",
            direct_answer=_simple_python_mutable_default_trace_answer(value),
        )
    return None
