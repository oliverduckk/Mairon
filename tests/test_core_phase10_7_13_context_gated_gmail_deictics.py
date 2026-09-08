import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.conversation_state import ConversationState
from core.intent_router import classify_turn


def _state_with_email_messages(count: int) -> ConversationState:
    state = ConversationState()
    state.active_intent = "email_search"
    state.recent_email_referents = [
        {
            "search_text": "Example Sender",
            "time_scope": "rolling_days",
            "days": 30,
            "status": "success",
            "messages": [
                {
                    "message_id": f"msg-{index + 1}",
                    "subject": f"Example message {index + 1}",
                    "sender": "Example Sender",
                    "date": "",
                }
                for index in range(count)
            ],
        }
    ]
    return state


def _assert_not_gmail(turn):
    assert turn.intent != "email_read", (turn.intent, turn.reasons)
    assert turn.preferred_authority != "gmail", (
        turn.preferred_authority,
        turn.reasons,
    )


def run():
    # --------------------------------------------------
    # 1. Bare pronouns must never create a Gmail workflow cold.
    # --------------------------------------------------
    cold = classify_turn("Explain it.")
    _assert_not_gmail(cold)

    reproduced_complaint = classify_turn(
        "YOU HAVE THE INTERNET TO LOOK SHIT UP. "
        "YOU SHOULDN'T NEED ME TO EXPLAIN IT TO YOU"
    )
    _assert_not_gmail(reproduced_complaint)

    # --------------------------------------------------
    # 2. Active Gmail intent alone is not authority.
    # --------------------------------------------------
    no_referent = ConversationState()
    no_referent.active_intent = "email_search"
    _assert_not_gmail(
        classify_turn(
            "Explain it.",
            conversation_state=no_referent,
        )
    )

    zero_matches = _state_with_email_messages(0)
    _assert_not_gmail(
        classify_turn(
            "Read that.",
            conversation_state=zero_matches,
        )
    )

    # A singular pronoun cannot silently choose among multiple verified
    # candidates. Oliver can still say "the second one" via the existing
    # deterministic email-candidate selector path.
    ambiguous = _state_with_email_messages(2)
    _assert_not_gmail(
        classify_turn(
            "Summarise it.",
            conversation_state=ambiguous,
        )
    )

    # --------------------------------------------------
    # 3. One verified message allows deictic Gmail continuation.
    # --------------------------------------------------
    one_message = _state_with_email_messages(1)
    follow_up = classify_turn(
        "Explain it.",
        conversation_state=one_message,
    )

    assert follow_up.intent == "email_read"
    assert follow_up.preferred_authority == "gmail"
    assert follow_up.requested_action == "read_email"
    assert follow_up.is_follow_up is True
    assert follow_up.entities.get("message_id") == "msg-1"
    assert any(
        "verified Gmail referent" in reason
        for reason in follow_up.reasons
    )

    action_follow_up = classify_turn(
        "Do I need to reply about it?",
        conversation_state=one_message,
    )
    assert action_follow_up.intent == "email_read"
    assert action_follow_up.requested_action == "assess_email_action"
    assert action_follow_up.entities.get("message_id") == "msg-1"

    # --------------------------------------------------
    # 4. Explicit email nouns may still enter Gmail without prior context.
    # --------------------------------------------------
    explicit = classify_turn(
        "Explain the email from Example Sender."
    )
    assert explicit.intent == "email_read"
    assert explicit.preferred_authority == "gmail"
    assert explicit.entities.get("search_text") == "Example Sender"

    # Production stays generic: no reproduced complaint or fake sender is
    # hard-coded as a special-case runtime branch.
    source = (SRC_DIR / "core" / "intent_router.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "example sender" not in source
    assert "you have the internet to look shit up" not in source

    print("Mairon Phase 10.7.13 context-gated Gmail deictic tests: PASS")


if __name__ == "__main__":
    run()
