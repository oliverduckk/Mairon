import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from core.conversation_state import ConversationState
from core.email_intent import is_inbox_attention_request
from core.intent_router import classify_turn
from ai import ollama_provider


def _response(
    content="",
    tool_calls=None,
):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=content,
            tool_calls=tool_calls or [],
        )
    )


class _InboxClient:
    def __init__(
        self,
    ):
        self.calls = 0
        self.tool_args_seen = []

    def chat(
        self,
        **kwargs,
    ):
        self.calls += 1
        self.tool_args_seen.append(
            kwargs.get(
                "tools",
                "__missing__",
            )
        )

        return _response(
            content='{"items":[{"index":1,"category":"IGNORE"}]}'
        )


class _BlankInboxClient:
    def __init__(
        self,
    ):
        self.calls = 0

    def chat(
        self,
        **kwargs,
    ):
        self.calls += 1

        if self.calls < 3:
            return _response(
                content=""
            )

        return _response(
            content="No action needed."
        )


def run():
    # --------------------------------------------------
    # 1. Inbox ATTENTION intent is shared and broad.
    # --------------------------------------------------

    attention_cases = (
        "Which emails from today actually need my attention?",
        "What important emails are in my inbox?",
        "Any urgent emails I should deal with?",
        "Do any emails need action?",
        "Give me an inbox triage.",
    )

    for text in attention_cases:
        assert is_inbox_attention_request(
            text
        ), text

        turn = classify_turn(
            text
        )

        assert (
            turn.intent
            == "inbox_attention"
        ), (
            text,
            turn.intent,
            turn.entities,
            turn.reasons,
        )

        assert (
            turn.preferred_authority
            == "gmail"
        )

    # Nearby targeted lookup must remain targeted Gmail search.
    targeted = classify_turn(
        "Did I receive an email from PayPal today?"
    )

    assert targeted.intent == "email_search"
    assert targeted.entities["search_text"] == "PayPal"

    # --------------------------------------------------
    # 2. Temporal-only followups inherit an ACTIVE Gmail target.
    # --------------------------------------------------

    state = ConversationState()

    first = classify_turn(
        "Did I receive an email from PayPal today?",
        conversation_state=state,
    )

    assert first.intent == "email_search"

    state.update_from_turn(
        first
    )

    for text, expected_scope in (
        ("how about yesterday?", "yesterday"),
        ("what about today?", "today"),
        ("and yesterday?", "yesterday"),
        ("yesterday?", "yesterday"),
    ):
        followup = classify_turn(
            text,
            conversation_state=state,
        )

        assert followup.intent == "email_search", (
            text,
            followup.intent,
            followup.reasons,
        )

        assert followup.is_follow_up is True
        assert followup.entities["search_text"] == "PayPal"
        assert followup.entities["time_scope"] == expected_scope

    # Without an active Gmail target, the same words are NOT hijacked.
    fresh = ConversationState()

    assert (
        classify_turn(
            "how about yesterday?",
            conversation_state=fresh,
        ).intent
        != "email_search"
    )

    # --------------------------------------------------
    # 3. "Today" triage uses an exact local calendar window.
    # --------------------------------------------------

    fixed_now = datetime(
        2026,
        9,
        3,
        16,
        30,
        tzinfo=ZoneInfo(
            "Australia/Sydney"
        ),
    )

    original_resolver = (
        ollama_provider.resolve_email_summary_window
    )

    original_execute_tool = (
        ollama_provider.execute_tool
    )

    try:
        exact_window = (
            original_resolver(
                "Which emails from today need my attention?",
                now=fixed_now,
            )
        )

        ollama_provider.resolve_email_summary_window = (
            lambda user_input: dict(
                exact_window
            )
        )

        captured = {}

        def fake_execute_tool(
            tool_name,
            arguments,
        ):
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments

            return {
                "success": True,
                "emails": [
                    {
                        "message_id": "m1",
                        "from": "Example <example@example.com>",
                        "subject": "Routine newsletter",
                        "snippet": "Weekly roundup",
                        "internal_date_ms": int(
                            datetime(
                                2026,
                                9,
                                3,
                                10,
                                0,
                                tzinfo=ZoneInfo(
                                    "Australia/Sydney"
                                ),
                            ).timestamp()
                            * 1000
                        ),
                        "unread": False,
                    }
                ],
            }

        ollama_provider.execute_tool = fake_execute_tool

        inbox_client = _InboxClient()

        # Test the actual Phase 7.3 invariant at the inbox-handler boundary.
        # Routing to this handler is already covered separately above.
        answer, _, _, _ = (
            ollama_provider.handle_inbox_attention_request(
                client=inbox_client,
                user_input=(
                    "Which emails from today actually need my attention?"
                ),
                conversation=[],
            )
        )

        assert captured["tool_name"] == "find_emails"
        assert captured["arguments"]["search_text"] == ""
        assert captured["arguments"]["expand_search"] is False
        assert captured["arguments"]["after_epoch"] == (
            exact_window["after_epoch"]
        )
        assert captured["arguments"]["before_epoch"] == (
            exact_window["before_epoch"]
        )

        assert (
            "Nothing in your inbox today appears to require action"
            in answer
        )

        assert "Routine newsletter" in answer
        assert "IGNORE:" in answer

        # Phase 7.3: inbox triage is one bounded tool-free judgement pass.
        assert inbox_client.calls == 1
        assert inbox_client.tool_args_seen == [
            "__missing__"
        ]

    finally:
        ollama_provider.resolve_email_summary_window = (
            original_resolver
        )

        ollama_provider.execute_tool = (
            original_execute_tool
        )

    # --------------------------------------------------
    # 4. Specialised inbox workflow also rejects empty finals.
    # --------------------------------------------------

    client = _BlankInboxClient()

    answer, _, _, _ = (
        ollama_provider.finalise_inbox_review(
            client=client,
            working_conversation=[],
        )
    )

    assert client.calls == 3
    assert answer == "No action needed."

    # Architecture guard: production does not benchmark-code the examples.
    combined_source = (
        (SRC_DIR / "core" / "email_intent.py").read_text(
            encoding="utf-8"
        )
        + (SRC_DIR / "core" / "intent_router.py").read_text(
            encoding="utf-8"
        )
    ).lower()

    for forbidden in (
        "paypal today",
        "today actually need my attention",
        "how about yesterday?",
        "1.45s",
    ):
        assert forbidden not in combined_source

    print(
        "Mairon Phase 7.1 Gmail conversational routing / "
        "calendar-window tests: PASS"
    )


if __name__ == "__main__":
    run()
