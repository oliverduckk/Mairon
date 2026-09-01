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
# Fake Gmail registry.
#
# This test does not touch Oliver's real inbox.
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
            ],
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


from core.orchestrator import MaironCore


def run():
    core = MaironCore()

    # --------------------------------------------------
    # Core-owned factual workflow.
    # --------------------------------------------------

    first = core.prepare_turn(
        "Hey has my order from Hype DC arrived?"
    )

    assert first.direct_response == (
        "Yep — your Hype DC order is ready to collect."
    )

    assert first.answer_contract.allow_new_factual_claims is False
    assert first.answer_contract.allow_recommendations is False

    assert [
        name
        for name, _arguments
        in tool_calls
    ] == [
        "find_emails"
    ]

    # --------------------------------------------------
    # Declarative follow-up inherits the Core referent.
    # --------------------------------------------------

    tool_calls.clear()

    second = core.prepare_turn(
        (
            "They are a pair of XT6s for my trip to China in 2 months time. "
            "Gotta buy good shoes for walking that much ya know."
        )
    )

    assert second.direct_response is None
    assert second.turn.intent == "share_context"
    assert second.turn.resolved_referents["they"].lower() == "hype dc order"

    contract_text = (
        second.answer_contract
        .to_model_instruction()
    )

    assert (
        "'they' refers to: Hype DC order"
        in contract_text
    )

    assert (
        "Recommendations allowed: false"
        in contract_text
    )

    assert (
        "New unsupported factual claims allowed: false"
        in contract_text
    )

    assert (
        "Do not turn a declarative share into unsolicited recommendations."
        in contract_text
    )

    # --------------------------------------------------
    # Thanks remains a terminal acknowledgement.
    # --------------------------------------------------

    third = core.prepare_turn(
        "Thanks Mairon"
    )

    third_contract = (
        third.answer_contract
        .to_model_instruction()
    )

    assert third.answer_contract.allow_recommendations is False
    assert third.answer_contract.allow_follow_up_question is False
    assert (
        "Do not turn thanks into another offer of help."
        in third_contract
    )

    print(
        "Mairon Core Foundation v1 runtime-wiring regression: PASS"
    )


if __name__ == "__main__":
    run()
