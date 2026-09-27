"""Narrow extractive recall from the user's own live statements.

Only directly answer short, unambiguous *what did I say* colour questions
when an explicit noun/colour pair appears in the live USER record. Unknown,
contradictory or vague cases remain with the existing grounded recall model.
Assistant prose is never parsed for facts.
"""
from __future__ import annotations

import re
from typing import Any, Optional

_COLOURS = (
    "black|white|red|blue|green|yellow|orange|purple|pink|brown|grey|gray|"
    "silver|gold|beige|teal|navy|maroon|cream|clear"
)
_ASK = re.compile(
    r"\b(?:what|which)\s+colou?r\s+(?:was\s+(?:the|my)\s+)?"
    r"(?P<noun>[a-z][a-z0-9_-]{1,22})\b.{0,110}?"
    r"\b(?:did\s+i\s+(?:actually\s+)?(?:say|tell)|i\s+said)\b", re.I,
)


def extract_latest_stated_colour(
    current_question: str,
    recent_user_turns: list[dict[str, Any]] | None,
) -> Optional[str]:
    query = str(current_question or "")
    ask = _ASK.search(query)
    if not ask:
        return None
    noun = ask["noun"].lower()
    if noun in {"thing", "item", "one", "colour", "color"}:
        return None
    noun_re = re.escape(noun.rstrip("s")) + "s?"
    # The colour must occur immediately before the requested object (allowing
    # one modifier such as 'packing'). The pair must not be negated; scan latest
    # user turns first so an explicit correction outranks the original.
    pair = re.compile(rf"\b(?P<colour>{_COLOURS})\s+(?:[a-z-]+\s+)?{noun_re}\b", re.I)
    for entry in reversed(list(recent_user_turns or [])[-8:]):
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "")
        if not text:
            continue
        for match in reversed(list(pair.finditer(text))):
            preceding = text[max(0, match.start()-22): match.start()].lower()
            if re.search(r"\b(?:not|isn'?t|wasn'?t|never)\s+(?:the\s+)?$", preceding):
                continue
            # Ambiguous if the same message contains conflicting unnegated
            # values, unless it explicitly identifies a correction.
            candidates = [m for m in pair.finditer(text) if not re.search(
                r"\b(?:not|isn'?t|wasn'?t|never)\s+(?:the\s+)?$",
                text[max(0,m.start()-22):m.start()].lower()
            )]
            if len({m["colour"].lower() for m in candidates}) > 1 and not re.search(
                r"\b(?:correction|actually|not|instead|moved|scratch that)\b", text, re.I
            ):
                return None
            return f"You said the {noun} is {match['colour'].lower()}."
    return None
