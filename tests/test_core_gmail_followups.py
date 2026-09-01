import sys
import types
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


# --------------------------------------------------
# Fake tool registry before importing Core workflows.
#
# No real Gmail calls are made by this test.
# --------------------------------------------------

fake_registry = types.ModuleType(
    "tools.tool_registry"
)

tool_calls = []


def fake_execute_tool(
    tool_name,
    arguments=None,
):
    arguments = arguments or {}

    tool_calls.append(
        (
            tool_name,
            dict(
                arguments
            ),
        )
    )

    if tool_name != "find_emails":
        return {
            "success": False,
            "message": (
                f"Unexpected tool call: {tool_name}"
            ),
        }

    search_text = str(
        arguments.get(
            "search_text",
            "",
        )
    )

    if search_text.lower() == "prosple":
        return {
            "success": True,
            "email_count": 1,
            "emails": [
                {
                    "sender": "Richard from Prosple",
                    "subject": (
                        "New Graduate Job recommendations from Prosple"
                    ),
                    "date": "Mon, 31 Aug 2026 23:21:03 +0000",
                    "snippet": "Graduate role recommendations.",
                    "message_id": "prosple-1",
                },
            ],
        }

    return {
        "success": True,
        "email_count": 0,
        "emails": [],
    }


fake_registry.execute_tool = (
    fake_execute_tool
)

import tools

sys.modules[
    "tools.tool_registry"
] = fake_registry


from core.intent_router import (
    classify_turn,
)
from core.orchestrator import (
    MaironCore,
)


def assert_exact_day_arguments(
    arguments,
):
    assert arguments[
        "search_text"
    ] == "Prosple"

    assert arguments[
        "expand_search"
    ] is False

    after_epoch = arguments.get(
        "after_epoch"
    )

    before_epoch = arguments.get(
        "before_epoch"
    )

    assert isinstance(
        after_epoch,
        int,
    )

    assert isinstance(
        before_epoch,
        int,
    )

    # A local calendar day is normally 24h, but DST transition days can
    # legitimately be 23h or 25h. Accept the real-world range.
    duration = (
        before_epoch
        - after_epoch
    )

    assert duration in {
        23 * 60 * 60,
        24 * 60 * 60,
        25 * 60 * 60,
    }


def run():
    core = MaironCore()

    # --------------------------------------------------
    # 1. Initial explicit Gmail lookup remains rolling.
    # --------------------------------------------------

    tool_calls.clear()

    first = core.prepare_turn(
        (
            "Have I received any emails from Prosple "
            "in the last couple days?"
        )
    )

    assert first.turn.intent == (
        "email_search"
    )

    assert first.turn.entities[
        "search_text"
    ] == "Prosple"

    assert first.turn.entities[
        "time_scope"
    ] == "rolling_days"

    assert first.direct_response is not None

    assert tool_calls == [
        (
            "find_emails",
            {
                "search_text": "Prosple",
                "days": 2,
                "unread_only": False,
                "max_results": 10,
            },
        )
    ]

    # --------------------------------------------------
    # 2. Exact real failure:
    #    no repeated word "email", but active Gmail context exists.
    # --------------------------------------------------

    tool_calls.clear()

    second = core.prepare_turn(
        "Did I get anything from Prosple yesterday?"
    )

    assert second.turn.intent == (
        "email_search"
    )

    assert second.turn.is_follow_up is True

    assert second.turn.entities[
        "search_text"
    ] == "Prosple"

    assert second.turn.entities[
        "time_scope"
    ] == "yesterday"

    assert second.direct_response is not None

    assert len(
        tool_calls
    ) == 1

    assert tool_calls[
        0
    ][
        0
    ] == "find_emails"

    assert_exact_day_arguments(
        tool_calls[
            0
        ][
            1
        ]
    )

    # --------------------------------------------------
    # 3. Pronoun follow-up inherits Prosple too.
    # --------------------------------------------------

    tool_calls.clear()

    third = core.prepare_turn(
        "Did I get anything from them yesterday?"
    )

    assert third.turn.intent == (
        "email_search"
    )

    assert third.turn.entities[
        "search_text"
    ] == "Prosple"

    assert third.turn.entities[
        "time_scope"
    ] == "yesterday"

    assert third.direct_response is not None

    assert len(
        tool_calls
    ) == 1

    assert_exact_day_arguments(
        tool_calls[
            0
        ][
            1
        ]
    )

    # --------------------------------------------------
    # 4. No generic inbox summary anywhere.
    # --------------------------------------------------

    assert all(
        tool_name != "get_recent_emails"
        for tool_name, _arguments
        in tool_calls
    )

    # --------------------------------------------------
    # 5. Without active Gmail context, "anything from X" remains
    #    ambiguous instead of being globally hijacked as email.
    # --------------------------------------------------

    fresh = MaironCore()

    ambiguous = classify_turn(
        "Did I get anything from Prosple yesterday?",
        conversation_state=(
            fresh.conversation_state
        ),
    )

    assert ambiguous.intent != (
        "email_search"
    )

    print(
        "Contextual Gmail follow-up regression tests: PASS"
    )


if __name__ == "__main__":
    run()
