import sys
import types
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
# Fake Gmail registry.
#
# This test does NOT touch Oliver's real inbox.
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
            dict(arguments),
        )
    )

    if tool_name == "find_emails":
        search_text = str(
            arguments.get(
                "search_text",
                "",
            )
        ).lower()

        if search_text == "prosple":
            return {
                "success": True,
                "emails": [
                    {
                        "sender": "Richard from Prosple",
                        "subject": (
                            "New Graduate Job recommendations from Prosple"
                        ),
                        "date": "Aug 31, 2026",
                        "snippet": (
                            "New graduate jobs you may be interested in."
                        ),
                        "message_id": "prosple-1",
                    },
                ],
            }

        return {
            "success": True,
            "emails": [],
        }

    return {
        "success": False,
        "message": "Unexpected tool call.",
    }


fake_registry.execute_tool = (
    fake_execute_tool
)

import tools

sys.modules[
    "tools.tool_registry"
] = fake_registry


from core.intent_router import classify_turn
from core.orchestrator import MaironCore


def run():
    # --------------------------------------------------
    # Exact real-world failure.
    # --------------------------------------------------

    text = (
        "Have I received any emails from Prosple "
        "in the last couple days?"
    )

    turn = classify_turn(
        text
    )

    assert turn.intent == "email_search"
    assert turn.preferred_authority == "gmail"
    assert turn.should_use_tools is True
    assert turn.entities["search_text"] == "Prosple"
    assert turn.entities["days"] == 2

    tool_calls.clear()

    core = MaironCore()

    decision = core.prepare_turn(
        text
    )

    assert decision.direct_response is not None
    assert "Prosple" in decision.direct_response
    assert (
        "New Graduate Job recommendations from Prosple"
        in decision.direct_response
    )

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

    assert all(
        tool_name != "get_recent_emails"
        for tool_name, _arguments
        in tool_calls
    )

    # --------------------------------------------------
    # Natural phrasing coverage.
    # --------------------------------------------------

    cases = [
        (
            "Did I get an email from CyberCX yesterday?",
            "CyberCX",
            2,
        ),
        (
            "Has Richard from Prosple emailed me?",
            "Richard from Prosple",
            30,
        ),
        (
            "Check my emails for BDO in the last 7 days",
            "BDO",
            7,
        ),
        (
            "Any emails from Westpac today?",
            "Westpac",
            1,
        ),
    ]

    for (
        message,
        expected_search,
        expected_days,
    ) in cases:
        candidate = classify_turn(
            message
        )

        assert candidate.intent == "email_search"
        assert (
            candidate.entities["search_text"]
            == expected_search
        )
        assert (
            candidate.entities["days"]
            == expected_days
        )

    print(
        "Targeted Gmail Core regression tests: PASS"
    )


if __name__ == "__main__":
    run()
