import base64
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


from tools import gmail_tools
from ai import ollama_provider


def _encode(
    value,
):
    return (
        base64.urlsafe_b64encode(
            value.encode(
                "utf-8"
            )
        )
        .decode(
            "ascii"
        )
        .rstrip(
            "="
        )
    )


def _response(
    content="",
):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=content,
            tool_calls=[],
        )
    )


class _OnePassInboxClient:
    def __init__(
        self,
        answer,
    ):
        self.answer = answer
        self.calls = []

    def chat(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        assert "tools" not in kwargs
        assert kwargs.get(
            "think"
        ) is False

        return _response(
            self.answer
        )


def run():
    # --------------------------------------------------
    # 1. Genuine text/plain remains preferred.
    # --------------------------------------------------

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": _encode(
                        "Plain authoritative body."
                    ),
                },
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": _encode(
                        "<p>Different HTML body.</p>"
                    ),
                },
            },
        ],
    }

    text, body_format = (
        gmail_tools.extract_message_text(
            payload
        )
    )

    assert text == (
        "Plain authoritative body."
    )
    assert body_format == "text/plain"

    # --------------------------------------------------
    # 2. HTML-only Gmail messages become clean visible text.
    # --------------------------------------------------

    html_payload = {
        "mimeType": "text/html",
        "body": {
            "data": _encode(
                """
                <html>
                  <head>
                    <style>.hidden { display:none; }</style>
                    <script>alert('nope')</script>
                  </head>
                  <body>
                    <h1>Account update</h1>
                    <p>We are changing our legal agreements.</p>
                    <p>No action is required &amp; your account stays active.</p>
                    <a href="https://example.invalid">Review the changes</a>
                  </body>
                </html>
                """
            ),
        },
    }

    text, body_format = (
        gmail_tools.extract_message_text(
            html_payload
        )
    )

    assert body_format == "text/html"
    assert "Account update" in text
    assert (
        "We are changing our legal agreements."
        in text
    )
    assert (
        "No action is required & your account stays active."
        in text
    )
    assert "Review the changes" in text

    assert "<p>" not in text
    assert "alert(" not in text
    assert "display:none" not in text

    # --------------------------------------------------
    # 3. normalise_full_message reports which body source won.
    # --------------------------------------------------

    message = {
        "id": "m1",
        "internalDate": "1788400000000",
        "labelIds": [],
        "snippet": "Account update...",
        "payload": {
            "mimeType": "text/html",
            "headers": [
                {
                    "name": "From",
                    "value": "Example <mail@example.com>",
                },
                {
                    "name": "To",
                    "value": "Oliver <oliver@example.com>",
                },
                {
                    "name": "Subject",
                    "value": "Account update",
                },
                {
                    "name": "Date",
                    "value": "Thu, 03 Sep 2026 10:00:00 +1000",
                },
            ],
            "body": {
                "data": _encode(
                    "<p>No action is required.</p>"
                ),
            },
        },
    }

    normalised = (
        gmail_tools.normalise_full_message(
            message
        )
    )

    assert normalised[
        "body"
    ] == "No action is required."

    assert normalised[
        "body_format"
    ] == "text/html"

    # --------------------------------------------------
    # 4. Inbox triage performs exactly one tool-free model pass.
    # --------------------------------------------------

    original_execute = (
        ollama_provider.execute_tool
    )

    original_resolver = (
        ollama_provider.resolve_email_summary_window
    )

    try:
        fixed_window = {
            "mode": "exact",
            "label": "today",
            "after_epoch": int(
                datetime(
                    2026,
                    9,
                    3,
                    0,
                    0,
                    tzinfo=ZoneInfo(
                        "Australia/Sydney"
                    ),
                ).timestamp()
            ),
            "before_epoch": int(
                datetime(
                    2026,
                    9,
                    4,
                    0,
                    0,
                    tzinfo=ZoneInfo(
                        "Australia/Sydney"
                    ),
                ).timestamp()
            ),
            "unread_only": False,
        }

        ollama_provider.resolve_email_summary_window = (
            lambda user_input: dict(
                fixed_window
            )
        )

        tool_calls = []

        def fake_execute_tool(
            tool_name,
            arguments,
        ):
            tool_calls.append(
                (
                    tool_name,
                    dict(
                        arguments
                    ),
                )
            )

            assert tool_name == "find_emails"

            return {
                "success": True,
                "emails": [
                    {
                        "message_id": "a",
                        "from": "Sender A",
                        "subject": "Routine newsletter",
                        "date": "Thu, 03 Sep 2026 09:00:00 +1000",
                        "snippet": "Weekly recommendations",
                        "unread": True,
                    },
                    {
                        "message_id": "b",
                        "from": "Sender B",
                        "subject": "Security alert",
                        "date": "Thu, 03 Sep 2026 10:00:00 +1000",
                        "snippet": "New sign-in detected",
                        "unread": False,
                    },
                ],
            }

        ollama_provider.execute_tool = (
            fake_execute_tool
        )

        client = _OnePassInboxClient(
            '{"items":['
            '{"index":1,"category":"IGNORE"},'
            '{"index":2,"category":"ACTION"}'
            ']}'
        )

        answer, _, _, _ = (
            ollama_provider.handle_inbox_attention_request(
                client=client,
                user_input=(
                    "Which emails from today need my attention?"
                ),
                conversation=[],
            )
        )

        assert "1 email looks actionable" in answer
        assert "Security alert — Sender B" in answer
        assert "Routine newsletter — Sender A" in answer
        assert "ACTION NEEDED:" in answer
        assert "IGNORE:" in answer

        # Deterministic rendering cannot invent arrival-time claims.
        lowered_answer = answer.lower()
        assert "morning" not in lowered_answer
        assert "last night" not in lowered_answer

        assert len(
            client.calls
        ) == 1

        assert len(
            tool_calls
        ) == 1

        # The ONLY tool is Core's initial Gmail summary fetch.
        assert tool_calls[
            0
        ][0] == "find_emails"

    finally:
        ollama_provider.execute_tool = (
            original_execute
        )

        ollama_provider.resolve_email_summary_window = (
            original_resolver
        )

    print(
        "Mairon Phase 7.3 Gmail HTML-body fallback / "
        "one-pass inbox triage tests: PASS"
    )


if __name__ == "__main__":
    run()
