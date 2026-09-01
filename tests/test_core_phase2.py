import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = (
    PROJECT_ROOT
    / "src"
)

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


# --------------------------------------------------
# Fake tool_registry before importing the order workflow.
#
# This regression test deliberately does NOT touch real Gmail.
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

    if tool_name == "find_emails":
        search_text = arguments.get(
            "search_text",
            ""
        )

        if (
            search_text.lower()
            == "hype dc"
        ):
            return {
                "success": True,
                "emails": [
                    {
                        "sender": "StarTrack",
                        "subject": (
                            "Your StarTrack parcel from HYPE DC "
                            "SHELLHARBOUR is ready to collect"
                        ),
                        "snippet": (
                            "Your parcel from HYPE DC SHELLHARBOUR "
                            "is ready to collect."
                        ),
                        "date": "2026-08-31",
                        "message_id": "abc123",
                    },
                    {
                        "sender": "Hype DC",
                        "subject": (
                            "Your package from Hype DC is now "
                            "awaiting collection"
                        ),
                        "snippet": (
                            "Your package is awaiting collection."
                        ),
                        "date": "2026-08-31",
                        "message_id": "def456",
                    },
                ],
            }

        return {
            "success": True,
            "emails": [],
        }

    return {
        "success": False,
        "message": (
            "Unexpected tool call in Core regression test."
        ),
    }


fake_registry.execute_tool = (
    fake_execute_tool
)

# Import the real tools package, then replace only the registry module
# for this test process.
import tools

sys.modules[
    "tools.tool_registry"
] = fake_registry


from core.orchestrator import MaironCore


def run():
    core = MaironCore()

    # --------------------------------------------------
    # 1. Exact Hype DC failure from the real conversation.
    # --------------------------------------------------

    tool_calls.clear()

    decision1 = core.prepare_turn(
        "Hey has my order from Hype DC arrived?"
    )

    assert decision1.direct_response == (
        "Yep — your Hype DC order is ready to collect."
    )

    assert decision1.turn.intent == (
        "order_status"
    )

    assert tool_calls == [
        (
            "find_emails",
            {
                "search_text": "Hype DC",
                "days": 60,
                "unread_only": False,
                "max_results": 10,
            },
        )
    ]

    # --------------------------------------------------
    # 2. Exact pronoun follow-up that previously failed.
    # --------------------------------------------------

    tool_calls.clear()

    decision2 = core.prepare_turn(
        "Check my emails to see if it has"
    )

    assert decision2.turn.intent == (
        "order_status"
    )

    assert (
        decision2.turn.entities[
            "merchant"
        ].lower()
        == "hype dc"
    )

    assert (
        decision2.turn.resolved_referents[
            "it"
        ].lower()
        == "hype dc order"
    )

    assert decision2.direct_response == (
        "Yep — your Hype DC order is ready to collect."
    )

    assert [
        call[
            0
        ]
        for call in tool_calls
    ] == [
        "find_emails"
    ]

    # --------------------------------------------------
    # 3. Exact XT-6 declarative-share failure.
    # --------------------------------------------------

    tool_calls.clear()

    decision3 = core.prepare_turn(
        (
            "They are a pair of XT6s for my trip to China in 2 months time. "
            "Gotta buy good shoes for walking that much ya know."
        )
    )

    assert decision3.turn.speech_act == (
        "declarative_share"
    )

    assert decision3.turn.intent == (
        "share_context"
    )

    assert (
        decision3.answer_contract
        .allow_recommendations
        is False
    )

    assert decision3.direct_response is None

    assert tool_calls == []

    assert any(
        "unsolicited recommendations"
        in item
        for item in (
            decision3.answer_contract
            .forbidden_behaviours
        )
    )

    # --------------------------------------------------
    # 4. An actual recommendation request remains valid.
    # --------------------------------------------------

    decision4 = core.prepare_turn(
        "What shoes should I buy for walking all day?"
    )

    assert decision4.turn.intent == (
        "recommendation_request"
    )

    assert (
        decision4.answer_contract
        .allow_recommendations
        is True
    )

    # --------------------------------------------------
    # 5. Thanks is not a request for another offer.
    # --------------------------------------------------

    decision5 = core.prepare_turn(
        "Thanks Mairon"
    )

    assert decision5.turn.speech_act == (
        "thanks"
    )

    assert (
        decision5.answer_contract
        .allow_follow_up_question
        is False
    )

    assert (
        decision5.answer_contract
        .allow_recommendations
        is False
    )

    print(
        "Mairon Core Foundation v1 Phase 2 regression tests: PASS"
    )


if __name__ == "__main__":
    run()
