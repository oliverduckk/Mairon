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


class _NoModelAllowedClient:
    def chat(
        self,
        **kwargs,
    ):
        raise AssertionError(
            "Qwen must not run for deterministic Gmail summary retrieval."
        )


class _BlankThenAnswerClient:
    def __init__(
        self,
    ):
        self.calls = 0

    def chat(
        self,
        **kwargs,
    ):
        self.calls += 1

        if self.calls == 1:
            return _response(
                content=""
            )

        return _response(
            content=(
                "I need Gmail search results before I can answer that."
            )
        )


def run():
    # --------------------------------------------------
    # 1. Generic Gmail summary requests route deterministically.
    # --------------------------------------------------

    positive = (
        "What emails have I received today?",
        "Show me my emails from yesterday.",
        "Do I have any unread emails?",
        "List my recent emails.",
        "What came into my inbox today?",
        "emails today",
    )

    for text in positive:
        assert (
            ollama_provider.is_recent_email_summary_request(
                text
            )
        ), text

    # Nearby requests belong to different Gmail capabilities.
    negative = (
        "What important emails need my attention?",
        "What did the email say?",
        "Did I receive an email from Qantas today?",
        "Do I have an email about my order?",
        "Reply to that email.",
    )

    for text in negative:
        assert not (
            ollama_provider.is_recent_email_summary_request(
                text
            )
        ), text

    # --------------------------------------------------
    # 2. "Today" and "yesterday" are exact Sydney calendar windows.
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

    today_window = (
        ollama_provider.resolve_email_summary_window(
            "What emails arrived today?",
            now=fixed_now,
        )
    )

    assert today_window["mode"] == "exact"
    assert today_window["label"] == "today"

    today_start = datetime.fromtimestamp(
        today_window["after_epoch"],
        tz=ZoneInfo(
            "Australia/Sydney"
        ),
    )

    today_end = datetime.fromtimestamp(
        today_window["before_epoch"],
        tz=ZoneInfo(
            "Australia/Sydney"
        ),
    )

    assert today_start.isoformat() == (
        "2026-09-03T00:00:00+10:00"
    )

    assert today_end.isoformat() == (
        "2026-09-04T00:00:00+10:00"
    )

    yesterday_window = (
        ollama_provider.resolve_email_summary_window(
            "Show my emails from yesterday.",
            now=fixed_now,
        )
    )

    yesterday_start = datetime.fromtimestamp(
        yesterday_window["after_epoch"],
        tz=ZoneInfo(
            "Australia/Sydney"
        ),
    )

    assert yesterday_start.isoformat() == (
        "2026-09-02T00:00:00+10:00"
    )

    # --------------------------------------------------
    # 3. Straightforward listing uses Gmail metadata directly,
    #    with no Qwen generation.
    # --------------------------------------------------

    original_execute_tool = (
        ollama_provider.execute_tool
    )

    try:
        captured = {}

        def fake_execute_tool(
            tool_name,
            arguments,
        ):
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments

            return {
                "success": True,
                "email_count": 2,
                "emails": [
                    {
                        "message_id": "a",
                        "from": "Qantas <news@example.com>",
                        "subject": "Flight update",
                        "internal_date_ms": int(
                            datetime(
                                2026,
                                9,
                                3,
                                14,
                                5,
                                tzinfo=ZoneInfo(
                                    "Australia/Sydney"
                                ),
                            ).timestamp()
                            * 1000
                        ),
                        "unread": True,
                    },
                    {
                        "message_id": "b",
                        "from": "Macquarie University <uni@example.com>",
                        "subject": "Unit announcement",
                        "internal_date_ms": int(
                            datetime(
                                2026,
                                9,
                                3,
                                9,
                                30,
                                tzinfo=ZoneInfo(
                                    "Australia/Sydney"
                                ),
                            ).timestamp()
                            * 1000
                        ),
                        "unread": False,
                    },
                ],
            }

        ollama_provider.execute_tool = (
            fake_execute_tool
        )

        # Freeze the window resolver so the test's exact epoch values are
        # deterministic regardless of the real date on the machine.
        original_resolver = (
            ollama_provider.resolve_email_summary_window
        )

        ollama_provider.resolve_email_summary_window = (
            lambda user_input: dict(
                today_window
            )
        )

        answer, _, _, _ = (
            ollama_provider.get_response(
                client=_NoModelAllowedClient(),
                user_input=(
                    "What emails have I received today?"
                ),
                instructions="You are Mairon.",
                conversation=[],
                allow_cloud_escalation=False,
            )
        )

        assert captured["tool_name"] == "find_emails"
        assert captured["arguments"]["search_text"] == ""
        assert captured["arguments"]["expand_search"] is False
        assert captured["arguments"]["after_epoch"] == (
            today_window["after_epoch"]
        )
        assert captured["arguments"]["before_epoch"] == (
            today_window["before_epoch"]
        )

        assert "Qantas" in answer
        assert "Flight update" in answer
        assert "Macquarie University" in answer
        assert "Unit announcement" in answer
        assert "[unread]" in answer

    finally:
        ollama_provider.execute_tool = (
            original_execute_tool
        )

        if "original_resolver" in locals():
            ollama_provider.resolve_email_summary_window = (
                original_resolver
            )

    # --------------------------------------------------
    # 4. General tool loop may never return a blank answer.
    # --------------------------------------------------

    blank_client = _BlankThenAnswerClient()

    answer, _, _, _ = (
        ollama_provider.get_response(
            client=blank_client,
            user_input=(
                "Did I receive an email from Qantas today?"
            ),
            instructions="You are Mairon.",
            conversation=[],
            allow_cloud_escalation=False,
        )
    )

    assert blank_client.calls == 2
    assert answer.strip()
    assert (
        "Gmail search results"
        in answer
    )

    # Architecture regression: no user/entity benchmark special-casing.
    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8",
    ).lower()

    for forbidden in (
        "qantas today",
        "macquarie university",
        "20.94",
        "blank gmail",
    ):
        assert (
            forbidden
            not in provider_source
        )

    print(
        "Mairon Phase 7 Gmail deterministic-summary / "
        "non-empty-tool-loop tests: PASS"
    )


if __name__ == "__main__":
    run()
