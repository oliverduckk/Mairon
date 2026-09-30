from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

CASES_PATH = Path(__file__).with_name(
    "phase11_6_brain_acceptance_cases.json"
)

BENCHMARK_DIR = (
    PROJECT_ROOT
    / "data"
    / "private"
    / "benchmarks"
)

LATEST_JSON_PATH = (
    BENCHMARK_DIR
    / "brain_acceptance_latest.json"
)

LATEST_MARKDOWN_PATH = (
    BENCHMARK_DIR
    / "brain_acceptance_latest.md"
)

LEGACY_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "private"
    / "brain_acceptance_latest.json"
)


def _load_cases() -> dict[str, Any]:
    return json.loads(
        CASES_PATH.read_text(
            encoding="utf-8"
        )
    )


def _markdown_blockquote(text: Any) -> str:
    value = str(
        text
        or ""
    ).rstrip()

    if not value:
        return "> [empty]"

    return "\n".join(
        "> " + line
        if line
        else ">"
        for line in value.splitlines()
    )


def _markdown_code_block(
    value: Any,
    *,
    language: str = "json",
) -> str:
    if isinstance(
        value,
        str,
    ):
        rendered = value
    else:
        rendered = json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        )

    return (
        "```"
        + language
        + "\n"
        + rendered
        + "\n```"
    )


def _benchmark_outcome(
    report: dict[str, Any],
) -> str:
    summary = (
        report.get(
            "summary"
        )
        or {}
    )

    critical_failures = int(
        summary.get(
            "critical_failures",
            0,
        )
        or 0
    )

    failed = int(
        summary.get(
            "failed",
            0,
        )
        or 0
    )

    if critical_failures:
        return "BLOCKED"

    if failed:
        return "REVIEW NON-CRITICAL FAILURES"

    return "PASS"


def _case_lookup(
    suite: dict[str, Any],
) -> dict[tuple[str, int], dict[str, Any]]:
    lookup: dict[
        tuple[str, int],
        dict[str, Any],
    ] = {}

    for scenario in suite.get(
        "scenarios",
        [],
    ):
        scenario_id = str(
            scenario.get(
                "id",
                "",
            )
        )

        for turn_number, turn in enumerate(
            scenario.get(
                "turns",
                [],
            ),
            start=1,
        ):
            lookup[
                (
                    scenario_id,
                    turn_number,
                )
            ] = {
                "scenario_title": scenario.get(
                    "title"
                ),
                "category": scenario.get(
                    "category"
                ),
                "expectation": turn.get(
                    "expect",
                    {},
                ),
                "post_inject_assistant": turn.get(
                    "post_inject_assistant"
                ),
                "resolve_approval": turn.get(
                    "resolve_approval"
                ),
            }

    return lookup


def _enrich_report_with_case_definitions(
    report: dict[str, Any],
    suite: dict[str, Any],
) -> dict[str, Any]:
    lookup = _case_lookup(
        suite
    )

    for item in report.get(
        "results",
        [],
    ):
        try:
            turn_number = int(
                item.get(
                    "turn_number",
                    0,
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            turn_number = 0

        definition = lookup.get(
            (
                str(
                    item.get(
                        "scenario_id",
                        "",
                    )
                ),
                turn_number,
            ),
            {},
        )

        for key in (
            "scenario_title",
            "category",
            "expectation",
            "post_inject_assistant",
            "resolve_approval",
        ):
            if (
                key not in item
                or item.get(
                    key
                ) is None
            ):
                item[
                    key
                ] = definition.get(
                    key
                )

    report[
        "report_format_version"
    ] = 2

    return report


def _render_markdown_report(
    report: dict[str, Any],
) -> str:
    summary = (
        report.get(
            "summary"
        )
        or {}
    )

    results = list(
        report.get(
            "results",
            [],
        )
    )

    lines = [
        "# Mairon Phase 11.6 — Brain Intelligence Acceptance",
        "",
        "## Run metadata",
        "",
        "- **Outcome:** "
        + _benchmark_outcome(
            report
        ),
        "- **Generated:** "
        + str(
            report.get(
                "generated_at",
                "unknown",
            )
        ),
        "- **Local model:** `"
        + str(
            report.get(
                "model",
                "unknown",
            )
        )
        + "`",
        "- **Suite:** "
        + str(
            report.get(
                "suite",
                "unknown",
            )
        ),
        "- **Suite version:** "
        + str(
            report.get(
                "suite_version",
                "unknown",
            )
        ),
        "- **Report format:** "
        + str(
            report.get(
                "report_format_version",
                1,
            )
        ),
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        "| Passed | "
        + str(
            summary.get(
                "passed",
                0,
            )
        )
        + " |",
        "| Failed | "
        + str(
            summary.get(
                "failed",
                0,
            )
        )
        + " |",
        "| Critical failures | "
        + str(
            summary.get(
                "critical_failures",
                0,
            )
        )
        + " |",
        "| Interactions run | "
        + str(
            summary.get(
                "interactions_run",
                0,
            )
        )
        + "/"
        + str(
            summary.get(
                "interactions_total",
                0,
            )
        )
        + " |",
        "| Elapsed | "
        + str(
            summary.get(
                "elapsed_seconds",
                0,
            )
        )
        + "s |",
        "",
        "## Category results",
        "",
        "| Category | Passed | Total |",
        "|---|---:|---:|",
    ]

    for category, values in (
        report.get(
            "categories",
            {}
        )
        .items()
    ):
        lines.append(
            "| "
            + str(
                category
            )
            + " | "
            + str(
                values.get(
                    "passed",
                    0,
                )
            )
            + " | "
            + str(
                values.get(
                    "total",
                    0,
                )
            )
            + " |"
        )

    failed = [
        item
        for item in results
        if not item.get(
            "passed"
        )
    ]

    lines.extend([
        "",
        "## Failed interaction index",
        "",
    ])

    if not failed:
        lines.append(
            "No failed interactions."
        )
    else:
        for item in failed:
            label = (
                "CRITICAL FAIL"
                if item.get(
                    "critical"
                )
                else "FAIL"
            )

            lines.append(
                "- **"
                + label
                + "** — `"
                + str(
                    item.get(
                        "scenario_id",
                        "unknown",
                    )
                )
                + "` turn "
                + str(
                    item.get(
                        "turn_number",
                        "?",
                    )
                )
                + " ("
                + str(
                    item.get(
                        "category",
                        "uncategorised",
                    )
                )
                + ")"
            )

    lines.extend([
        "",
        "## Full interaction log",
        "",
        (
            "This section intentionally records every benchmark turn, including "
            "passes, prompts, final Mairon answers, routing metadata, expectations, "
            "failures, diagnostics, events, injected assistant-only test claims, "
            "and approval-resolution results."
        ),
        "",
    ])

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    order: list[str] = []

    for item in results:
        scenario_id = str(
            item.get(
                "scenario_id",
                "unknown",
            )
        )

        if scenario_id not in grouped:
            grouped[
                scenario_id
            ] = []
            order.append(
                scenario_id
            )

        grouped[
            scenario_id
        ].append(
            item
        )

    for scenario_number, scenario_id in enumerate(
        order,
        start=1,
    ):
        scenario_results = grouped[
            scenario_id
        ]

        first = scenario_results[
            0
        ]

        title = str(
            first.get(
                "scenario_title",
                "",
            )
            or ""
        ).strip()

        lines.extend([
            "### "
            + str(
                scenario_number
            )
            + ". `"
            + scenario_id
            + "`"
            + (
                " — "
                + title
                if title
                else ""
            ),
            "",
            "- **Category:** `"
            + str(
                first.get(
                    "category",
                    "uncategorised",
                )
            )
            + "`",
            "",
        ])

        for item in scenario_results:
            label = (
                "PASS"
                if item.get(
                    "passed"
                )
                else (
                    "CRITICAL FAIL"
                    if item.get(
                        "critical"
                    )
                    else "FAIL"
                )
            )

            lines.extend([
                "#### Turn "
                + str(
                    item.get(
                        "turn_number",
                        "?",
                    )
                )
                + " — "
                + label,
                "",
                "- **Critical:** "
                + str(
                    bool(
                        item.get(
                            "critical"
                        )
                    )
                ),
                "- **Status:** `"
                + str(
                    item.get(
                        "status",
                        "",
                    )
                    or "-"
                )
                + "`",
                "- **Intent:** `"
                + str(
                    item.get(
                        "intent",
                        "",
                    )
                    or "-"
                )
                + "`",
                "- **Authority:** `"
                + str(
                    item.get(
                        "authority",
                        "",
                    )
                    or "-"
                )
                + "`",
                "",
                "**Oliver**",
                "",
                _markdown_blockquote(
                    item.get(
                        "user"
                    )
                ),
                "",
                "**Mairon**",
                "",
                _markdown_blockquote(
                    item.get(
                        "answer"
                    )
                ),
                "",
                "**Expectation used by benchmark**",
                "",
                _markdown_code_block(
                    item.get(
                        "expectation",
                        {},
                    )
                ),
                "",
            ])

            failures = (
                item.get(
                    "failures"
                )
                or []
            )

            lines.append(
                "**Failures**"
            )
            lines.append(
                ""
            )

            if failures:
                for failure in failures:
                    lines.append(
                        "- "
                        + str(
                            failure
                        )
                    )
            else:
                lines.append(
                    "- None"
                )

            lines.extend([
                "",
                "**Diagnostics**",
                "",
                _markdown_code_block(
                    item.get(
                        "diagnostics"
                    )
                    or {}
                ),
                "",
                "**Events**",
                "",
            ])

            events = (
                item.get(
                    "events"
                )
                or []
            )

            if events:
                for event in events:
                    lines.append(
                        "- `"
                        + str(
                            event
                        ).replace(
                            "`",
                            "\\`",
                        )
                        + "`"
                    )
            else:
                lines.append(
                    "- None"
                )

            injected = item.get(
                "post_inject_assistant"
            )

            if injected:
                lines.extend([
                    "",
                    "**Injected assistant-only claim after this turn**",
                    "",
                    _markdown_blockquote(
                        injected
                    ),
                ])

            if (
                "resolve_approval"
                in item
                and item.get(
                    "resolve_approval"
                )
                is not None
            ):
                lines.extend([
                    "",
                    "**Configured approval resolution:** `"
                    + (
                        "APPROVE"
                        if item.get(
                            "resolve_approval"
                        )
                        else "DECLINE"
                    )
                    + "`",
                ])

            approval_resolution = item.get(
                "approval_resolution"
            )

            approval_preview = item.get("approval_preview")
            if approval_preview:
                lines.extend([
                    "",
                    "**Proposed approval preview (captured before declining)**",
                    "",
                    _markdown_code_block(approval_preview),
                ])

            if approval_resolution:
                lines.extend([
                    "",
                    "**Observed approval-resolution result**",
                    "",
                    _markdown_code_block(
                        approval_resolution
                    ),
                ])

            lines.extend([
                "",
                "---",
                "",
            ])

    return "\n".join(
        lines
    ).rstrip() + "\n"


def _write_report_files(
    report: dict[str, Any],
    *,
    targeted: bool = False,
) -> tuple[Path, Path, Path, Path]:
    BENCHMARK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%d_%H%M%S"
    )

    basename = "brain_acceptance_targeted" if targeted else "brain_acceptance"
    json_snapshot = BENCHMARK_DIR / (basename + "_" + timestamp + ".json")
    markdown_snapshot = BENCHMARK_DIR / (basename + "_" + timestamp + ".md")
    latest_json = (
        BENCHMARK_DIR / (basename + "_latest.json")
        if targeted else LATEST_JSON_PATH
    )
    latest_markdown = (
        BENCHMARK_DIR / (basename + "_latest.md")
        if targeted else LATEST_MARKDOWN_PATH
    )

    json_text = json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    ) + "\n"

    markdown_text = (
        _render_markdown_report(
            report
        )
    )

    for path in (
        json_snapshot,
        latest_json,
    ):
        path.write_text(
            json_text,
            encoding="utf-8",
        )

    for path in (
        markdown_snapshot,
        latest_markdown,
    ):
        path.write_text(
            markdown_text,
            encoding="utf-8",
        )

    return (
        json_snapshot,
        markdown_snapshot,
        latest_json,
        latest_markdown,
    )


def render_existing_report() -> int:
    suite = _load_cases()

    if LATEST_JSON_PATH.is_file():
        source_path = (
            LATEST_JSON_PATH
        )
    elif LEGACY_REPORT_PATH.is_file():
        source_path = (
            LEGACY_REPORT_PATH
        )
    else:
        print(
            "No existing brain-acceptance JSON report was found."
        )
        return 1

    report = json.loads(
        source_path.read_text(
            encoding="utf-8"
        )
    )

    report = (
        _enrich_report_with_case_definitions(
            report,
            suite,
        )
    )

    paths = _write_report_files(
        report
    )

    print(
        "Rendered existing benchmark report from: "
        + str(
            source_path
        )
    )
    print(
        "Markdown latest: "
        + str(
            paths[
                3
            ]
        )
    )
    print(
        "JSON latest: "
        + str(
            paths[
                2
            ]
        )
    )
    print(
        "Timestamped Markdown: "
        + str(
            paths[
                1
            ]
        )
    )

    return 0


def _contains(
    text: str,
    needle: str,
) -> bool:
    # Mechanical scoring should treat typographic apostrophes/quotes as the
    # same wording, otherwise a truthful "I don’t know" can falsely fail an
    # expectation containing ASCII "don't". This changes typography only; it
    # does not broaden the semantic acceptance criteria.
    table = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
    return str(needle).translate(table).casefold() in str(text).translate(table).casefold()


def _capture_approval_preview(app, response) -> dict[str, Any] | None:
    """Capture a read-only proposal BEFORE the test declines the action.

    No approval happens here, and only calendar preview fields are retained.
    The current ApplicationTurn already exposes user-visible approval_detail;
    the pending action provides structured dates for exact validation.
    """
    if getattr(response, "status", "") != "action_approval_required":
        return None
    pending = getattr(app, "_pending", None)
    router_result = getattr(pending, "router_result", None)
    action = getattr(router_result, "pending_action", None)
    if not isinstance(action, dict):
        action = {}
    allowed = ("type", "summary", "start_time", "end_time", "location", "description")
    return {
        "approval_title": str(getattr(response, "approval_title", "") or ""),
        "approval_detail": str(getattr(response, "approval_detail", "") or ""),
        "pending_action": {key: action.get(key) for key in allowed if key in action},
    }


def _check_approval_preview(
    preview: dict[str, Any] | None,
    expectation: dict[str, Any],
) -> list[str]:
    """Check proposed action *before* any simulated decline/approval."""
    if not expectation:
        return []
    if not preview or not preview.get("pending_action"):
        return ["missing inspectable approval preview/pending action"]

    action = preview["pending_action"]
    problems = []
    if expectation.get("action_type") and action.get("type") != expectation["action_type"]:
        problems.append("unexpected proposed action type " + repr(action.get("type")))
    summary = str(action.get("summary") or "").lower()
    for part in expectation.get("summary_contains", []):
        if str(part).lower() not in summary:
            problems.append("proposed title missing " + repr(part))

    timezone = ZoneInfo(os.getenv("MAIRON_TIMEZONE", "Australia/Sydney"))
    timestamps = {}
    for field in ("start_time", "end_time"):
        raw = str(action.get(field) or "")
        try:
            parsed = datetime.fromisoformat(raw)
            parsed = (
                parsed.replace(tzinfo=timezone)
                if parsed.tzinfo is None else parsed.astimezone(timezone)
            )
            timestamps[field] = parsed
        except (TypeError, ValueError):
            problems.append("invalid or missing proposed " + field + ": " + repr(raw))

    for field in ("start_time", "end_time"):
        if field not in timestamps:
            continue
        field_prefix = "start" if field == "start_time" else "end"
        expected_clock = expectation.get(field_prefix + "_hhmm")
        if expected_clock and timestamps[field].strftime("%H:%M") != expected_clock:
            problems.append(field + " expected " + expected_clock + " got "
                            + timestamps[field].strftime("%H:%M"))
        expected_day = expectation.get(field_prefix + "_weekday")
        if expected_day and timestamps[field].strftime("%A").lower() != expected_day.lower():
            problems.append(field + " expected " + expected_day + " got "
                            + timestamps[field].strftime("%A"))

    if expectation.get("must_be_future") and "start_time" in timestamps:
        if timestamps["start_time"] <= datetime.now(timezone):
            problems.append("proposed start is not in the future")
    if (expectation.get("end_same_date_as_start")
            and "start_time" in timestamps and "end_time" in timestamps
            and timestamps["start_time"].date() != timestamps["end_time"].date()):
        problems.append("proposed end date differs from the requested same-day event")
    if (expectation.get("start_next_occurrence_weekday")
            and "start_time" in timestamps and expectation.get("start_weekday")):
        target_weekday = expectation["start_weekday"].lower()
        weekday_names = ("monday", "tuesday", "wednesday", "thursday",
                         "friday", "saturday", "sunday")
        if target_weekday in weekday_names:
            local_now = datetime.now(timezone)
            days = (weekday_names.index(target_weekday) - local_now.weekday()) % 7
            expected_date = local_now.date() + timedelta(days=days)
            proposed_start = timestamps["start_time"]
            if days == 0 and proposed_start.time() <= local_now.time():
                expected_date += timedelta(days=7)
            if proposed_start.date() != expected_date:
                problems.append("proposed start expected next " + target_weekday
                                + " " + expected_date.isoformat()
                                + ", got " + proposed_start.date().isoformat())
    return problems


def _check_expectations(
    turn_result,
    expectation: dict[str, Any],
) -> list[str]:
    failures: list[str] = []

    status = str(
        getattr(
            turn_result,
            "status",
            "",
        )
        or ""
    ).strip()

    intent = str(
        getattr(
            turn_result,
            "intent",
            "",
        )
        or ""
    ).strip()

    authority = str(
        getattr(
            turn_result,
            "authority",
            "",
        )
        or ""
    ).strip()

    answer = str(
        getattr(
            turn_result,
            "answer",
            "",
        )
        or ""
    ).strip()

    # Never mark the provider's own empty-generation failure as an accepted
    # answer.  Previously a status-only case could pass even though the
    # response explicitly said that no usable answer was produced.
    # Keep this narrowly tied to the provider's failure sentinel: ordinary
    # admissions of uncertainty (including inaccessible private state) are
    # valid answers and must not be rejected.
    if status == "answered" and re.match(
        r"^i\s+couldn['’]?t\s+produce\s+a\s+usable\s+answer\b",
        answer,
        flags=re.IGNORECASE,
    ):
        failures.append("provider reported no usable answer despite answered status")

    expected_status = (
        expectation.get(
            "status"
        )
        or []
    )

    if (
        expected_status
        and status not in expected_status
    ):
        failures.append(
            "status="
            + repr(status)
            + " expected one of "
            + repr(expected_status)
        )

    forbidden_status = (
        expectation.get(
            "forbidden_status"
        )
        or []
    )

    if status in forbidden_status:
        failures.append(
            "forbidden status "
            + repr(status)
        )

    expected_intent = (
        expectation.get(
            "intent"
        )
        or []
    )

    if (
        expected_intent
        and intent not in expected_intent
    ):
        failures.append(
            "intent="
            + repr(intent)
            + " expected one of "
            + repr(expected_intent)
        )

    expected_authority = (
        expectation.get(
            "authority"
        )
        or []
    )

    if (
        expected_authority
        and authority not in expected_authority
    ):
        failures.append(
            "authority="
            + repr(authority)
            + " expected one of "
            + repr(expected_authority)
        )

    for required in (
        expectation.get(
            "required_all"
        )
        or []
    ):
        if not _contains(
            answer,
            str(required),
        ):
            failures.append(
                "missing required text "
                + repr(required)
            )

    required_any = (
        expectation.get(
            "required_any"
        )
        or []
    )

    if required_any:
        if not any(
            _contains(
                answer,
                str(item),
            )
            for item in required_any
        ):
            failures.append(
                "answer contained none of required alternatives "
                + repr(required_any)
            )

    for pattern in (
        expectation.get(
            "required_regex"
        )
        or []
    ):
        if re.search(
            str(pattern),
            answer,
            flags=re.IGNORECASE,
        ) is None:
            failures.append(
                "missing required regex "
                + repr(pattern)
            )

    for forbidden in (
        expectation.get(
            "forbidden"
        )
        or []
    ):
        if _contains(
            answer,
            str(forbidden),
        ):
            failures.append(
                "contained forbidden text "
                + repr(forbidden)
            )

    for pattern in (
        expectation.get(
            "forbidden_regex"
        )
        or []
    ):
        if re.search(
            str(pattern),
            answer,
            flags=re.IGNORECASE,
        ) is not None:
            failures.append(
                "matched forbidden regex "
                + repr(pattern)
            )

    min_chars = expectation.get("min_chars")
    if min_chars is not None and len(answer) < int(min_chars):
        failures.append("answer was too short or empty")

    max_chars = expectation.get(
        "max_chars"
    )

    if (
        max_chars is not None
        and len(answer) > int(max_chars)
    ):
        failures.append(
            "answer length "
            + str(len(answer))
            + " exceeded "
            + str(max_chars)
        )

    if expectation.get(
        "forbid_question"
    ):
        if "?" in answer:
            failures.append(
                "answer contained a follow-up question"
            )

    return failures


def _patch_benchmark_persistence(
    application_service,
) -> None:
    """
    Keep the acceptance run from polluting Oliver's real conversation/session
    history or preference store.

    The provider/Core path remains real. Only persistence side effects are
    disabled for this benchmark process.
    """

    application_service.record_conversation_turn = (
        lambda *args, **kwargs: None
    )

    application_service.record_chat_turn = (
        lambda *args, **kwargs: None
    )

    application_service.capture_user_preference = (
        lambda *args, **kwargs: None
    )

    application_service.build_user_preference_recall_response = (
        lambda *args, **kwargs: None
    )


def _inject_assistant_claim(
    app,
    text: str,
) -> None:
    """
    Insert an assistant-only claim into model-visible history.

    This deliberately does NOT alter Core's user-authored conversational state.
    It lets the benchmark verify that an old Mairon statement cannot become
    factual evidence for a later recall question.
    """

    if app.local_state is None:
        app.local_state = []

    app.local_state = list(
        app.local_state
    )

    app.local_state.append({
        "role": "assistant",
        "content": str(text),
    })


def _print_turn_header(
    index: int,
    total: int,
    scenario_id: str,
    turn_index: int,
    user_text: str,
) -> None:
    print()
    print(
        "=" * 78
    )
    print(
        f"[{index}/{total}] "
        f"{scenario_id} "
        f"(turn {turn_index})"
    )
    print(
        "=" * 78
    )
    print(
        "Oliver: "
        + user_text
    )


def _safe_resolve_pending(
    app,
    approved: bool,
):
    try:
        return app.resolve_pending_approval(
            approved=approved
        )
    except TypeError:
        return app.resolve_pending_approval(
            approved
        )


def run(
    *,
    stop_on_critical: bool = False,
    only_scenarios: list[str] | None = None,
) -> int:
    os.environ.setdefault(
        "MAIRON_DEBUG_GENERATION",
        "0",
    )

    from application_service import (
        MaironApplication,
    )
    import application_service

    _patch_benchmark_persistence(
        application_service
    )

    suite = _load_cases()

    scenarios = list(suite.get("scenarios", []))
    targeted = bool(only_scenarios)
    if targeted:
        requested = set(only_scenarios or [])
        known = {str(s.get("id")) for s in scenarios}
        unknown = requested - known
        if unknown:
            raise ValueError("Unknown benchmark scenario(s): " + ", ".join(sorted(unknown)))
        scenarios = [s for s in scenarios if str(s.get("id")) in requested]

    total_turns = sum(
        len(
            scenario.get(
                "turns",
                []
            )
        )
        for scenario in scenarios
    )

    events: list[str] = []

    def event_sink(
        message: str,
    ) -> None:
        value = str(
            message
            or ""
        ).strip()

        if value:
            events.append(
                value
            )
            print(
                value
            )

    print()
    print(
        "Mairon Phase 11.6 — Brain Intelligence Acceptance"
    )
    print(
        "---------------------------------------------------"
    )
    print(
        f"Scenarios: {len(scenarios)}"
    )
    print(
        f"Live interactions: {total_turns}"
    )
    print(
        "Persistence: benchmark-isolated"
    )
    print()

    app = MaironApplication(
        event_sink=event_sink
    )

    # No chat-title thread should be started during the benchmark.
    app._schedule_semantic_title_if_first_turn = (
        lambda **kwargs: None
    )

    results: list[dict[str, Any]] = []
    category_totals = Counter()
    category_passes = Counter()

    overall_index = 0
    critical_failures = 0
    started = time.perf_counter()

    for scenario_number, scenario in enumerate(
        scenarios,
        start=1,
    ):
        if scenario_number > 1:
            if app.has_pending_approval:
                _safe_resolve_pending(
                    app,
                    approved=False,
                )

            app.new_chat()

        scenario_id = str(
            scenario.get(
                "id",
                f"scenario_{scenario_number}",
            )
        )

        category = str(
            scenario.get(
                "category",
                "uncategorised",
            )
        )

        for turn_number, turn in enumerate(
            scenario.get(
                "turns",
                []
            ),
            start=1,
        ):
            overall_index += 1
            user_text = str(
                turn.get(
                    "user",
                    "",
                )
            )

            _print_turn_header(
                overall_index,
                total_turns,
                scenario_id,
                turn_number,
                user_text,
            )

            event_start = len(
                events
            )

            try:
                response = app.submit_text(
                    user_text,
                    channel="text",
                )

            except Exception as exc:
                response = None
                failures = [
                    "benchmark call raised "
                    + type(exc).__name__
                    + ": "
                    + str(exc)
                ]

            else:
                failures = _check_expectations(
                    response,
                    turn.get(
                        "expect",
                        {},
                    ),
                )

            answer = (
                str(
                    getattr(
                        response,
                        "answer",
                        "",
                    )
                    or ""
                )
                if response is not None
                else ""
            )

            status = (
                str(
                    getattr(
                        response,
                        "status",
                        "",
                    )
                    or ""
                )
                if response is not None
                else "exception"
            )

            intent = (
                str(
                    getattr(
                        response,
                        "intent",
                        "",
                    )
                    or ""
                )
                if response is not None
                else ""
            )

            authority = (
                str(
                    getattr(
                        response,
                        "authority",
                        "",
                    )
                    or ""
                )
                if response is not None
                else ""
            )

            print(
                "Mairon: "
                + (
                    answer
                    if answer
                    else "[no final answer]"
                )
            )

            print(
                "[Benchmark] "
                f"status={status or '-'} "
                f"intent={intent or '-'} "
                f"authority={authority or '-'}"
            )

            approval_preview = (
                _capture_approval_preview(app, response)
                if response is not None else None
            )
            failures.extend(_check_approval_preview(
                approval_preview,
                turn.get("expect", {}).get("pending_action", {}),
            ))

            passed = not failures
            critical = bool(
                turn.get(
                    "critical",
                    False,
                )
            )

            category_totals[
                category
            ] += 1

            if passed:
                category_passes[
                    category
                ] += 1

                print(
                    "[Benchmark] PASS"
                )

            else:
                if critical:
                    critical_failures += 1

                print(
                    "[Benchmark] "
                    + (
                        "CRITICAL FAIL"
                        if critical
                        else "FAIL"
                    )
                )

                for failure in failures:
                    print(
                        "  - "
                        + failure
                    )

            results.append({
                "scenario_id": scenario_id,
                "scenario_title": scenario.get(
                    "title"
                ),
                "category": category,
                "turn_number": turn_number,
                "user": user_text,
                "answer": answer,
                "status": status,
                "intent": intent,
                "authority": authority,
                "diagnostics": (
                    getattr(
                        response,
                        "diagnostics",
                        None,
                    )
                    if response is not None
                    else None
                ),
                "events": events[
                    event_start:
                ],
                "passed": passed,
                "critical": critical,
                "failures": failures,
                "expectation": turn.get(
                    "expect",
                    {},
                ),
                "post_inject_assistant": turn.get(
                    "post_inject_assistant"
                ),
                "resolve_approval": turn.get(
                    "resolve_approval"
                ),
                "approval_resolution": None,
                "approval_preview": approval_preview,
            })

            injection = turn.get(
                "post_inject_assistant"
            )

            if injection:
                _inject_assistant_claim(
                    app,
                    str(
                        injection
                    ),
                )

                print(
                    "[Benchmark] Injected assistant-only false claim "
                    "for the next recall test."
                )

            if (
                response is not None
                and getattr(
                    response,
                    "status",
                    "",
                )
                in {
                    "cloud_approval_required",
                    "action_approval_required",
                }
            ):
                resolve_value = turn.get(
                    "resolve_approval",
                    False,
                )

                resolved = _safe_resolve_pending(
                    app,
                    approved=bool(
                        resolve_value
                    ),
                )

                results[-1][
                    "approval_resolution"
                ] = {
                    "approved": bool(
                        resolve_value
                    ),
                    "status": str(
                        getattr(
                            resolved,
                            "status",
                            "",
                        )
                        or ""
                    ),
                    "answer": str(
                        getattr(
                            resolved,
                            "answer",
                            "",
                        )
                        or ""
                    ),
                    "diagnostics": getattr(
                        resolved,
                        "diagnostics",
                        None,
                    ),
                }

                print(
                    "[Benchmark] Pending approval resolved as "
                    + (
                        "APPROVED"
                        if resolve_value
                        else "DECLINED"
                    )
                    + "."
                )

                if (
                    resolve_value
                    and getattr(
                        response,
                        "status",
                        "",
                    )
                    == "action_approval_required"
                ):
                    print(
                        "[Benchmark] WARNING: a mutating action was approved."
                    )

            if (
                stop_on_critical
                and failures
                and critical
            ):
                break

        if (
            stop_on_critical
            and critical_failures
        ):
            break

    elapsed = (
        time.perf_counter()
        - started
    )

    passed_count = sum(
        1
        for item in results
        if item[
            "passed"
        ]
    )

    failed_count = (
        len(results)
        - passed_count
    )

    print()
    print(
        "=" * 78
    )
    print(
        "MAIRON PHASE 11.6 BRAIN ACCEPTANCE SUMMARY"
    )
    print(
        "=" * 78
    )
    print(
        f"Passed: {passed_count}"
    )
    print(
        f"Failed: {failed_count}"
    )
    print(
        f"Critical failures: {critical_failures}"
    )
    print(
        f"Interactions run: {len(results)}/{total_turns}"
    )
    print(
        f"Elapsed: {elapsed:.1f}s"
    )
    print()

    print(
        "By category:"
    )

    for category in sorted(
        category_totals
    ):
        print(
            "  "
            + category
            + ": "
            + str(
                category_passes[
                    category
                ]
            )
            + "/"
            + str(
                category_totals[
                    category
                ]
            )
        )

    report = {
        "scope": "targeted" if targeted else "full",
        "selected_scenarios": sorted(set(only_scenarios or [])) if targeted else None,
        "suite": suite.get(
            "suite"
        ),
        "suite_version": suite.get(
            "version"
        ),
        "report_format_version": 2,
        "generated_at": datetime.now().astimezone().isoformat(),
        "model": str(getattr(app, "local_model_name", None)
                     or os.getenv("MAIRON_LOCAL_MODEL")
                     or "configured/default local model"),
        "summary": {
            "passed": passed_count,
            "failed": failed_count,
            "critical_failures": critical_failures,
            "interactions_run": len(
                results
            ),
            "interactions_total": total_turns,
            "elapsed_seconds": round(
                elapsed,
                3,
            ),
        },
        "categories": {
            category: {
                "passed": int(
                    category_passes[
                        category
                    ]
                ),
                "total": int(
                    category_totals[
                        category
                    ]
                ),
            }
            for category in sorted(
                category_totals
            )
        },
        "results": results,
    }

    report = (
        _enrich_report_with_case_definitions(
            report,
            suite,
        )
    )

    report_paths = _write_report_files(
        report, targeted=targeted
    )

    print()
    print(
        "Markdown report: "
        + str(
            report_paths[
                3
            ]
        )
    )
    print(
        "JSON report: "
        + str(
            report_paths[
                2
            ]
        )
    )
    print(
        "Timestamped Markdown: "
        + str(
            report_paths[
                1
            ]
        )
    )

    if critical_failures:
        print()
        print(
            "BRAIN ACCEPTANCE: BLOCKED"
        )
        return 2

    if failed_count:
        print()
        print(
            "BRAIN ACCEPTANCE: REVIEW NON-CRITICAL FAILURES"
        )
        return 1

    print()
    if targeted:
        print("TARGETED CHECK: PASS (the full acceptance result is unchanged)")
    else:
        print("BRAIN ACCEPTANCE 11.6: PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run Mairon's live local-model Phase 11.6 brain "
            "intelligence acceptance benchmark."
        )
    )

    parser.add_argument(
        "--stop-on-critical",
        action="store_true",
        help=(
            "Stop immediately after the first critical benchmark failure."
        ),
    )

    parser.add_argument(
        "--render-existing",
        action="store_true",
        help=(
            "Convert the latest existing JSON benchmark report into the "
            "new data/private/benchmarks JSON + Markdown report format "
            "without running the model again."
        ),
    )

    parser.add_argument(
        "--only", metavar="SCENARIO_ID", action="append",
        help=("Run only the named scenario. May be repeated; saves a separate "
              "targeted report and never overwrites the full acceptance report."),
    )

    args = parser.parse_args()

    if args.render_existing:
        raise SystemExit(
            render_existing_report()
        )

    raise SystemExit(
        run(
            stop_on_critical=(
                args.stop_on_critical
            ),
            only_scenarios=args.only,
        )
    )


if __name__ == "__main__":
    main()
