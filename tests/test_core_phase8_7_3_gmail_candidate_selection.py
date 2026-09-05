import sys
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


from core.conversation_state import (
    ConversationState,
)
from core.intent_router import (
    classify_turn,
)


def run():
    state = ConversationState()

    state.active_intent = "email_read"

    state.recent_email_referents = [
        {
            "search_text": "prosple",
            "time_scope": "rolling_days",
            "days": 30,
            "status": "multiple_matches",
            "messages": [
                {
                    "message_id": "newest-id",
                    "subject": "Newest Prosple email",
                    "sender": "Prosple",
                    "date": "Fri, 04 Sep 2026 23:21:05 +0000",
                },
                {
                    "message_id": "older-id",
                    "subject": "Older Prosple email",
                    "sender": "Prosple",
                    "date": "Thu, 03 Sep 2026 23:21:05 +0000",
                },
            ],
        }
    ]

    # --------------------------------------------------
    # 1. Bare candidate selection remains in Gmail lane.
    # --------------------------------------------------

    latest = classify_turn(
        "the latest one",
        conversation_state=state,
    )

    assert (
        latest.intent
        == "email_read"
    ), latest.intent

    assert (
        latest.entities.get(
            "message_id"
        )
        == "newest-id"
    ), latest.entities

    assert (
        latest.preferred_authority
        == "gmail"
    )

    # --------------------------------------------------
    # 2. Ordinal selection resolves exact verified message ID.
    # --------------------------------------------------

    second = classify_turn(
        "the second one",
        conversation_state=state,
    )

    assert (
        second.intent
        == "email_read"
    ), second.intent

    assert (
        second.entities.get(
            "message_id"
        )
        == "older-id"
    ), second.entities

    # --------------------------------------------------
    # 3. Explicit "latest email from X" carries selector into Core.
    # --------------------------------------------------

    explicit = classify_turn(
        "open the latest email from prosple",
        conversation_state=ConversationState(),
    )

    assert (
        explicit.intent
        == "email_read"
    ), explicit.intent

    assert (
        explicit.entities.get(
            "search_text"
        )
        == "prosple"
    ), explicit.entities

    assert (
        explicit.entities.get(
            "email_selector"
        )
        == "latest"
    ), explicit.entities

    print(
        "Mairon Phase 8.7.3 Gmail candidate selection tests: PASS"
    )


if __name__ == "__main__":
    run()
