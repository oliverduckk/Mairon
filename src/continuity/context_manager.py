from continuity.conversation_journal import (
    search_relevant_turns,
)


MAX_CONTEXT_CHARACTERS = 7000


def _format_timestamp(
    timestamp,
):
    if not timestamp:
        return "unknown time"

    value = str(
        timestamp
    )

    if "T" in value:
        date_part, time_part = value.split(
            "T",
            1,
        )

        time_part = time_part[
            :5
        ]

        return (
            f"{date_part} {time_part}"
        )

    return value


def build_relevant_past_context(
    user_input,
):
    """
    Build a compact, grounded prior-conversation excerpt.

    This is NOT the entire transcript and NOT explicit permanent memory.
    It is a relevance-selected slice of earlier local conversation used
    to preserve continuity across Mairon process restarts.
    """

    turns = search_relevant_turns(
        user_input=user_input,
    )

    if not turns:
        return None

    lines = [
        "MAIRON RELEVANT PRIOR CONVERSATION:",
        (
            "The excerpts below are retrieved from Mairon's private "
            "local conversation journal."
        ),
        (
            "They are authoritative about what Oliver and Mairon "
            "previously SAID, but a past Mairon statement is not "
            "automatically authoritative factual evidence."
        ),
        (
            "Use these excerpts only when genuinely relevant to the "
            "current turn. They may support continuity, earned callbacks, "
            "and accurate recall."
        ),
        (
            "Do not invent additional history around them. Do not claim "
            "to remember anything not supported by current conversation, "
            "this retrieved context, or explicit persistent memory."
        ),
        "",
    ]

    for turn in turns:
        timestamp = _format_timestamp(
            turn.get(
                "created_at"
            )
        )

        lines.extend([
            f"[{timestamp}]",
            (
                "Oliver: "
                + turn.get(
                    "user_text",
                    "",
                )
            ),
            (
                "Mairon: "
                + turn.get(
                    "assistant_text",
                    "",
                )
            ),
            "",
        ])

    value = "\n".join(
        lines
    ).strip()

    if len(value) <= MAX_CONTEXT_CHARACTERS:
        return value

    return (
        value[
            :MAX_CONTEXT_CHARACTERS
        ].rstrip()
        + "\n[Older retrieved context truncated by Core.]"
    )
