import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.conversation_state import ConversationState
from core.intent_router import classify_turn


def run():
    conversation = ConversationState()

    turn1 = classify_turn(
        "Hey has my order from Hype DC arrived?",
        conversation_state=conversation,
    )

    assert turn1.intent == "order_status"
    assert turn1.preferred_authority == "gmail"
    assert turn1.should_use_tools is True
    assert turn1.entities["merchant"].lower() == "hype dc"
    assert turn1.subject.lower() == "hype dc order"

    conversation.update_from_turn(turn1)

    turn2 = classify_turn(
        "Check my emails to see if it has",
        conversation_state=conversation,
    )

    turn2 = conversation.resolve_follow_up(turn2)

    assert turn2.intent == "order_status"
    assert turn2.resolved_referents["it"].lower() == "hype dc order"
    assert turn2.entities["merchant"].lower() == "hype dc"
    assert turn2.preferred_authority == "gmail"
    assert turn2.should_use_tools is True

    turn3 = classify_turn(
        (
            "They are a pair of XT6s for my trip to China in 2 months time. "
            "Gotta buy good shoes for walking that much ya know."
        )
    )

    assert turn3.speech_act == "declarative_share"
    assert turn3.intent == "share_context"
    assert turn3.should_recommend is False
    assert turn3.should_use_tools is False

    turn4 = classify_turn(
        "What shoes should I buy for walking all day in China?"
    )

    assert turn4.intent == "recommendation_request"
    assert turn4.should_recommend is True

    turn5 = classify_turn(
        "Thanks Mairon"
    )

    assert turn5.speech_act == "thanks"
    assert turn5.should_recommend is False
    assert turn5.should_continue_conversation is False

    print("Core Foundation v1 regression tests: PASS")


if __name__ == "__main__":
    run()
