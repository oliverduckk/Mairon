from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.calendar_proposal_guard import (
    CalendarProposalError,
    build_calendar_approval_from_user_request,
    extract_user_calendar_summary,
)


def run():
    syd = ZoneInfo("Australia/Sydney")
    now = datetime(2026, 10, 1, 16, 54, tzinfo=syd)

    # Exact 16:54 live critical failure. A clear explicit write request must
    # not depend on Qwen remembering to call the permission-request tool.
    request = (
        "actually add a mock interview practice block to my calendar "
        "for Wednesday from 7pm to 7:30pm"
    )
    assert extract_user_calendar_summary(request) == "mock interview practice block"
    proposal = build_calendar_approval_from_user_request(
        user_input=request,
        now=now,
    )
    assert proposal is not None
    action = proposal.action
    assert action["type"] == "create_calendar_event"
    assert action["summary"] == "mock interview practice block"
    assert action["start_time"] == "2026-10-07T19:00:00+11:00", action
    assert action["end_time"] == "2026-10-07T19:30:00+11:00", action
    assert action["location"] is None
    assert action["description"] is None

    # Existing ambiguity safety must remain stronger than convenience.
    ambiguous = (
        "put a mock test block on my calendar NEXT Friday from 5pm to 5:30pm "
        "-- yeah i know next Friday is ambiguous lol"
    )
    try:
        build_calendar_approval_from_user_request(
            user_input=ambiguous,
            now=now,
        )
    except CalendarProposalError as exc:
        assert "exact date" in str(exc).lower() and "friday" in str(exc).lower(), exc
    else:
        raise AssertionError("B22 guessed an ambiguous NEXT Friday")

    # Other ordinary explicit title shapes are extracted from user text rather
    # than invented by Core.
    examples = {
        "Schedule dentist Friday from 3pm to 4pm.": "dentist",
        "Add dinner tomorrow at 6pm": "dinner",
        "Plan a call Monday between 10:30am and 11:15am": "call",
        "Book something 2026-10-02 at 3pm": "something",
    }
    for text, expected in examples.items():
        assert extract_user_calendar_summary(text) == expected, text

    # Provider must attempt deterministic Core proposal construction before
    # asking the model to emit any calendar tool call. Execution remains
    # approval-gated elsewhere; this path returns only pending_action.
    provider = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    marker = "Core prepared a deterministic approval proposal from explicit user-authored details."
    assert marker in provider
    assert "build_calendar_approval_from_user_request(" in provider
    branch = provider.index('if core_intent == "calendar_event_creation_request":')
    build_pos = provider.index("build_calendar_approval_from_user_request(", branch)
    chat_pos = provider.index("response = client.chat(", branch)
    assert build_pos < chat_pos

    print(
        "PASS: B22 deterministic calendar approval preparation preserves next-occurrence and ambiguity safety"
    )


if __name__ == "__main__":
    run()
