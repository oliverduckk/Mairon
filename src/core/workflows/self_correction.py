"""
Deterministic acknowledgement for Oliver correcting his own prior wording.

Self-correction is user-authoritative state. Mairon does not need an LLM to
decide whether to accept it, and asking the model adds both latency and room
for irrelevant banter.

Examples:
    "Actually, scratch that — I cleaned it last night, not this morning."
        -> "Got it — you cleaned it last night, not this morning."

    "I meant the blue one, not the red one."
        -> "Got it — the blue one, not the red one."
"""

from __future__ import annotations

import re


_PREFIX_PATTERNS = (
    r"^\s*actually\s*[,—\-:]*\s*",
    r"^\s*scratch\s+that\s*[,—\-:]*\s*",
    r"^\s*correction\s*[,—\-:]*\s*",
    r"^\s*actually\s*,?\s*scratch\s+that\s*[,—\-:]*\s*",
)


def _strip_correction_prefix(
    text: str,
) -> str:
    value = str(
        text
        or ""
    ).strip()

    changed = True

    while (
        value
        and changed
    ):
        changed = False

        for pattern in _PREFIX_PATTERNS:
            updated = re.sub(
                pattern,
                "",
                value,
                count=1,
                flags=re.IGNORECASE,
            ).strip()

            if updated != value:
                value = updated
                changed = True
                break

    return value


def _to_second_person_fragment(
    text: str,
) -> str:
    """
    Surface-level pronoun shift only.

    This is intentionally tiny and conservative. It does not attempt general
    grammatical rewriting; it just makes common first-person correction
    clauses natural when echoed back.
    """

    value = str(
        text
        or ""
    ).strip()

    value = re.sub(
        r"^i'm\b",
        "you're",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^i am\b",
        "you are",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^i\b",
        "you",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^my\b",
        "your",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^we're\b",
        "you're",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^we are\b",
        "you are",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^we\b",
        "you",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^our\b",
        "your",
        value,
        flags=re.IGNORECASE,
    )

    return value


def build_self_correction_response(
    user_input: str,
) -> str:
    """
    Return a concise fact-preserving acknowledgement of Oliver's correction.

    Core echoes the correction rather than generating new content. If the
    wording is too awkward to echo safely, fail closed to a neutral
    acknowledgement.
    """

    value = _strip_correction_prefix(
        user_input
    )

    value = re.sub(
        r"[.!?]+\s*$",
        "",
        value,
    ).strip()

    if not value:
        return (
            "Got it — correction noted."
        )

    # "I meant X, not Y." / "I cleaned it last night, not this morning."
    contrast = re.match(
        r"^(?P<new>.+?)\s*,?\s+\bnot\s+(?P<old>.+?)$",
        value,
        flags=re.IGNORECASE,
    )

    if contrast:
        new_value = (
            contrast.group(
                "new"
            )
            or ""
        ).strip(" ,—-")

        old_value = (
            contrast.group(
                "old"
            )
            or ""
        ).strip(" ,—-")

        new_value = re.sub(
            r"^i\s+meant\s+",
            "",
            new_value,
            flags=re.IGNORECASE,
        ).strip()

        new_value = _to_second_person_fragment(
            new_value
        )

        if (
            new_value
            and old_value
            and len(new_value) <= 120
            and len(old_value) <= 80
        ):
            return (
                "Got it — "
                + new_value[0].lower()
                + new_value[1:]
                + ", not "
                + old_value
                + "."
            )

    # "I meant Tuesday." gets a clean deterministic echo.
    meant = re.match(
        r"^i\s+meant\s+(?P<value>.+)$",
        value,
        flags=re.IGNORECASE,
    )

    if meant:
        corrected = (
            meant.group(
                "value"
            )
            or ""
        ).strip()

        if (
            corrected
            and len(corrected) <= 120
        ):
            return (
                "Got it — "
                + corrected
                + "."
            )

    echoed = _to_second_person_fragment(
        value
    )

    if (
        echoed
        and len(echoed) <= 140
    ):
        return (
            "Got it — "
            + echoed[0].lower()
            + echoed[1:]
            + "."
        )

    return (
        "Got it — correction noted."
    )
