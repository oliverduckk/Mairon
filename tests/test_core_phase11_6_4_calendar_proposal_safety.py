"""Phase 11.6.4 — safety/targeted-benchmark deterministic regression.

Run from Mairon's repository root:
    python tests/test_core_phase11_6_4_calendar_proposal_safety.py

No Ollama requests, Google Calendar access or real actions are performed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.calendar_proposal_guard import (  # noqa: E402
    CalendarProposalError,
    validate_calendar_proposal,
)


def _benchmark_module():
    path = ROOT / "benchmarks" / "run_phase11_6_brain_acceptance.py"
    spec = importlib.util.spec_from_file_location("brain_benchmark_11_6_4", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments(start: str, end: str) -> dict:
    return {
        "summary": "Dentist appointment", "start_time": start,
        "end_time": end, "location": "", "description": "",
    }


def _reject(request: str, now: datetime) -> None:
    try:
        validate_calendar_proposal(
            user_input=request,
            model_arguments=_arguments("2026-10-01T15:00:00+10:00", "2026-10-01T16:00:00+10:00"),
            now=now,
        )
    except CalendarProposalError:
        return
    raise AssertionError("Ambiguous/invalid calendar proposal incorrectly accepted: " + request)


def run() -> None:
    syd = ZoneInfo("Australia/Sydney")
    reference = datetime(2026, 9, 26, 23, 16, tzinfo=syd)

    # Reproduce the REAL live failure: Qwen mistakenly proposes Thursday
    # October 1, but Oliver explicitly said Friday. Core owns date and clock.
    proposed = _arguments("2026-10-01T15:00:00+10:00", "2026-10-01T16:00:00+10:00")
    checked = validate_calendar_proposal(
        user_input="Put a dentist appointment on my calendar for Friday from 3pm to 4pm.",
        model_arguments=proposed,
        now=reference,
    )
    assert checked.corrected and checked.action["type"] == "create_calendar_event"
    assert checked.action["start_time"] == "2026-10-02T15:00:00+10:00"
    assert checked.action["end_time"] == "2026-10-02T16:00:00+10:00"
    assert proposed["start_time"].startswith("2026-10-01")  # original untouched
    untrusted_location = dict(proposed, location="Invented Medical Center")
    sanitised = validate_calendar_proposal(
        user_input="Put a dentist appointment on my calendar for Friday from 3pm to 4pm.",
        model_arguments=untrusted_location, now=reference,
    )
    assert sanitised.action["location"] is None

    correct = validate_calendar_proposal(
        user_input="Schedule dentist Friday from 3pm to 4pm.",
        model_arguments=_arguments(checked.action["start_time"], checked.action["end_time"]),
        now=reference,
    )
    assert not correct.corrected

    # Unambiguous unrelated forms use the same generic resolver, not an
    # acceptance-case-specific exception.
    alternatives = (
        ("Add dinner tomorrow at 6pm", "2026-09-27T18:00:00+10:00", "2026-09-27T19:00:00+10:00"),
        ("Schedule a review Monday between 10:30am and 11:15am", "2026-09-28T10:30:00+10:00", "2026-09-28T11:15:00+10:00"),
        ("Plan a call Friday 15:00 to 16:00", "2026-10-02T15:00:00+10:00", "2026-10-02T16:00:00+10:00"),
        ("Plan a call Friday from 3 to 4pm", "2026-10-02T15:00:00+10:00", "2026-10-02T16:00:00+10:00"),
        ("Book something 2026-10-02 at 3pm", "2026-10-02T15:00:00+10:00", "2026-10-02T16:00:00+10:00"),
        ("Book a meeting on 2 October 2026 at 3pm", "2026-10-02T15:00:00+10:00", "2026-10-02T16:00:00+10:00"),
        ("Book a meeting on October 2, 2026 at 3pm", "2026-10-02T15:00:00+10:00", "2026-10-02T16:00:00+10:00"),
        ("Book a meeting on Friday at 3pm for 2 hours", "2026-10-02T15:00:00+10:00", "2026-10-02T17:00:00+10:00"),
        ("Book a meeting on Friday at 3pm for 90 mins", "2026-10-02T15:00:00+10:00", "2026-10-02T16:30:00+10:00"),
        ("Book a meeting on Friday from 3pm to 4", "2026-10-02T15:00:00+10:00", "2026-10-02T16:00:00+10:00"),
    )
    for user, start, end in alternatives:
        actual = validate_calendar_proposal(
            user_input=user, model_arguments=proposed, now=reference,
        ).action
        assert (actual["start_time"], actual["end_time"]) == (start, end), user

    # Today at 3pm when it is already 11pm must never create a past action.
    for query in (
        "Book a meeting today at 3pm", "Put a dentist meeting next Friday from 3pm to 4pm",
        "Put dentist on the calendar sometime", "Add a meeting Friday at 3:00",
        "Add a meeting Friday from 3:00 to 4:00",
        "Set an appointment on Friday morning", "Book Monday and Friday from 3pm to 4pm",
        "Book an appointment on 2026-10-01 Friday from 3pm to 4pm",
        "Book an appointment on 4 October 2026 at 2:30am",  # DST gap
        "Book a meeting Friday from 11 to 1pm",  # noon ambiguous
        "Book a meeting Friday from 11am to 1",  # noon ambiguous
    ):
        _reject(query, reference)

    # Same weekday later today is today, not a week in the future.
    friday_afternoon = datetime(2026, 10, 2, 13, 0, tzinfo=syd)
    today = validate_calendar_proposal(
        user_input="Schedule this appointment Friday from 3pm to 4pm",
        model_arguments=proposed, now=friday_afternoon,
    ).action
    assert today["start_time"] == "2026-10-02T15:00:00+10:00"
    friday_evening = datetime(2026, 10, 2, 18, 0, tzinfo=syd)
    next_week = validate_calendar_proposal(
        user_input="Schedule an appointment Friday from 3pm to 4pm",
        model_arguments=proposed, now=friday_evening,
    ).action
    assert next_week["start_time"] == "2026-10-09T15:00:00+11:00"  # DST!

    # Ensure benchmark doesn't mistake networking "switches" for keyboard callback.
    runner = _benchmark_module()
    cases = json.loads((ROOT / "benchmarks" / "phase11_6_brain_acceptance_cases.json").read_text(encoding="utf-8"))
    by_id = {x["id"]: x for x in cases["scenarios"]}
    dns = by_id["topic_switch_no_callback"]["turns"][1]["expect"]
    fake = lambda answer: SimpleNamespace(status="answered", intent="factual_question", authority="public_web", answer=answer)
    assert runner._check_expectations(fake("DNS switches to TCP port 53 for zone transfers."), dns) == []
    assert runner._check_expectations(fake("Your keyboard switches use port 53."), dns)
    social = by_id["calendar_mention_not_action"]["turns"][0]["expect"]
    assert runner._check_expectations(
        SimpleNamespace(status="answered", intent="share_context", authority="user_turn",
                        answer="I couldn't produce a usable answer for that request."), social,
    )

    # The benchmark now checks both the weekday AND which actual Friday.
    check = by_id["calendar_action_permission"]["turns"][0]["expect"]["pending_action"]
    timezone_now = datetime.now(syd)
    days = (4 - timezone_now.weekday()) % 7
    expected_date = timezone_now.date() + timedelta(days=days)
    expected_start = datetime.combine(expected_date, datetime.min.time(), tzinfo=syd).replace(hour=15)
    if expected_start <= timezone_now:
        expected_start = expected_start + timedelta(days=7)
    expected_end = expected_start + timedelta(hours=1)
    preview = {"pending_action": _arguments(expected_start.isoformat(), expected_end.isoformat())}
    preview["pending_action"]["type"] = "create_calendar_event"
    assert runner._check_approval_preview(preview, check) == []
    preview["pending_action"]["start_time"] = (expected_start + timedelta(days=7)).isoformat()
    preview["pending_action"]["end_time"] = (expected_end + timedelta(days=7)).isoformat()
    assert runner._check_approval_preview(preview, check)

    # A targeted retest must never overwrite the last FULL acceptance report.
    # Keep this independent of Ollama and the real private data directory.
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        original_dir = runner.BENCHMARK_DIR
        original_render = runner._render_markdown_report
        runner.BENCHMARK_DIR = tmp
        runner._render_markdown_report = lambda _report: "# Targeted test\n"
        try:
            files = runner._write_report_files({"scope": "targeted"}, targeted=True)
            assert all(path.exists() for path in files)
            assert (tmp / "brain_acceptance_targeted_latest.md").exists()
            assert not (tmp / "brain_acceptance_latest.md").exists()
        finally:
            runner.BENCHMARK_DIR = original_dir
            runner._render_markdown_report = original_render

    # No tool loop, calendar network calls, or model generation here.
    print("PASS: 11.6.4 calendar canonicalisation, DST, false-pass and benchmark checks")


if __name__ == "__main__":
    run()
