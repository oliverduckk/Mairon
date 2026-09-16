from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


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


BENCHMARK_PATH = (
    Path(
        __file__
    ).resolve().with_name(
        "conversational_intelligence_cases.json"
    )
)

REPORT_DIR = (
    PROJECT_ROOT
    / "data"
    / "private"
    / "benchmarks"
)


def _load_cases() -> dict[str, Any]:
    return json.loads(
        BENCHMARK_PATH.read_text(
            encoding="utf-8",
        )
    )


def _install_non_destructive_benchmark_mode(
    application_service_module,
) -> None:
    """
    Prevent benchmark prompts from becoming real personal/session state.

    The real routing/provider/Core path still executes. Only persistence and
    preference side-effects are disabled for this benchmark process.
    """

    application_service_module.record_conversation_turn = (
        lambda *args, **kwargs: None
    )

    application_service_module.record_chat_turn = (
        lambda *args, **kwargs: None
    )

    application_service_module.capture_user_preference = (
        lambda *args, **kwargs: None
    )

    application_service_module.build_user_preference_recall_response = (
        lambda *args, **kwargs: None
    )

    application_service_module.MaironApplication._schedule_semantic_title_if_first_turn = (
        lambda *args, **kwargs: None
    )


def _normalise_fragments(
    values,
) -> list[str]:
    return [
        str(
            value
            or ""
        ).strip().lower()
        for value in (
            values
            or []
        )
        if str(
            value
            or ""
        ).strip()
    ]


def _automatic_turn_checks(
    case: dict[str, Any],
    turn_spec: dict[str, Any],
    result,
) -> dict[str, Any]:
    answer = str(
        getattr(
            result,
            "answer",
            "",
        )
        or ""
    )

    answer_lower = (
        answer.lower()
    )

    authority = str(
        getattr(
            result,
            "authority",
            "",
        )
        or ""
    ).strip()

    diagnostics = (
        getattr(
            result,
            "diagnostics",
            None,
        )
        or {}
    )

    if not authority:
        authority = str(
            diagnostics.get(
                "authority",
                "",
            )
            or ""
        ).strip()

    checks = []

    checks.append({
        "check": "answered",
        "passed": (
            str(
                getattr(
                    result,
                    "status",
                    "",
                )
                or ""
            )
            == "answered"
        ),
        "observed": str(
            getattr(
                result,
                "status",
                "",
            )
            or ""
        ),
    })

    for fragment in _normalise_fragments(
        turn_spec.get(
            "forbidden_answer_fragments"
        )
    ):
        checks.append({
            "check": (
                "forbidden_answer_fragment:"
                + fragment
            ),
            "passed": (
                fragment
                not in answer_lower
            ),
            "observed": answer,
        })

    expected_authorities = {
        str(
            item
            or ""
        ).strip()
        for item in (
            turn_spec.get(
                "expected_authorities"
            )
            or case.get(
                "expected_authorities"
            )
            or []
        )
        if str(
            item
            or ""
        ).strip()
    }

    if expected_authorities:
        checks.append({
            "check": "expected_authority",
            "passed": (
                authority
                in expected_authorities
            ),
            "observed": authority,
            "expected": sorted(
                expected_authorities
            ),
        })

    forbidden_authorities = {
        str(
            item
            or ""
        ).strip()
        for item in (
            turn_spec.get(
                "forbidden_authorities"
            )
            or case.get(
                "forbidden_authorities"
            )
            or []
        )
        if str(
            item
            or ""
        ).strip()
    }

    if forbidden_authorities:
        checks.append({
            "check": "forbidden_authority",
            "passed": (
                authority
                not in forbidden_authorities
            ),
            "observed": authority,
            "forbidden": sorted(
                forbidden_authorities
            ),
        })

    return {
        "passed": all(
            item[
                "passed"
            ]
            for item in checks
        ),
        "checks": checks,
    }


SAFE_RUNTIME_TRACE_PREFIXES = (
    "[Core]",
    "[Research]",
    "[Grounding]",
    "[Personality]",
    "[AI]",
    "[Conversation]",
    "[Context]",
)


def _safe_runtime_trace(
    stdout_text: str,
) -> list[str]:
    """
    Keep only high-level operational/provider diagnostics in benchmark reports.

    Raw tool payloads, OAuth details, page contents, evidence packets, and
    hidden reasoning are deliberately excluded.
    """

    lines = []

    for raw_line in str(
        stdout_text
        or ""
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if not line.startswith(
            SAFE_RUNTIME_TRACE_PREFIXES
        ):
            continue

        # Keep reports readable and prevent an accidental future log expansion
        # from dumping large payloads into the benchmark artifact.
        lines.append(
            line[:1200]
        )

    return lines


def _clean_diagnostics(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        dict,
    ):
        return {}

    # Diagnostics are already intentionally operational metadata only. Keep a
    # second explicit allowlist here so benchmark reports cannot accidentally
    # grow into raw-prompt/evidence dumps later.
    allowed = {
        "intent",
        "authority",
        "mode",
        "route_mode",
        "workflow",
        "model",
        "model_used",
        "agent_action",
        "status",
        "channel",
        "response_seconds",
        "session_id",
    }

    return {
        key: value[
            key
        ]
        for key in allowed
        if key in value
    }


def _render_markdown(
    benchmark: dict[str, Any],
    report: dict[str, Any],
) -> str:
    lines = [
        "# Mairon Conversational Intelligence Benchmark",
        "",
        f"Run: `{report['run_id']}`",
        f"Model: `{report.get('local_model') or 'unknown'}`",
        f"Mode: `{report['selection']}`",
        "",
        "## Baseline summary",
        "",
        f"- Scenarios run: **{report['summary']['scenario_count']}**",
        f"- Turns run: **{report['summary']['turn_count']}**",
        f"- Automatic checks passed: **{report['summary']['automatic_passes']}/{report['summary']['automatic_checks']}**",
        f"- Average response time: **{report['summary']['average_response_seconds']:.2f}s**",
        "",
        "### Human scoring",
        "",
        "Score each scenario from **0–2** on each dimension:",
        "",
        "| Dimension | 0 | 1 | 2 |",
        "|---|---|---|---|",
        "| Understanding / intent | Material miss | Usable but weak | Strong |",
        "| Context / referent | Lost/wrong | Partial | Correct continuity |",
        "| Epistemic trust | Bluff/wrong behaviour | Qualified but weak | Correct answer/research/humility |",
        "| Personality | Robotic/forced | Fine | Feels like Mairon |",
        "| Initiative | Wrong amount | Acceptable | Research/initiative exactly right |",
        "",
        "Target after Phase 11 improvements: **≥8/10 average with zero catastrophic trust failures.**",
        "",
    ]

    for scenario in report[
        "scenarios"
    ]:
        lines.extend([
            "---",
            "",
            f"## {scenario['id']}",
            "",
            f"**Category:** `{scenario['category']}`  ",
            f"**Purpose:** {scenario['description']}  ",
            f"**Manual focus:** {scenario['manual_focus']}",
            "",
        ])

        for index, turn in enumerate(
            scenario[
                "turns"
            ],
            start=1,
        ):
            lines.extend([
                f"### Turn {index}",
                "",
                f"**Oliver:** {turn['user']}",
                "",
                f"**Mairon:** {turn.get('answer') or '[no answer]'}",
                "",
                f"- Status: `{turn.get('status')}`",
                f"- Intent: `{turn.get('intent') or '—'}`",
                f"- Authority: `{turn.get('authority') or '—'}`",
                f"- Response: `{turn.get('response_seconds') if turn.get('response_seconds') is not None else '—'}s`",
                f"- Automatic checks: **{'PASS' if turn['automatic']['passed'] else 'FAIL'}**",
                "",
            ])

            if turn.get(
                "events"
            ):
                lines.extend([
                    "<details>",
                    "<summary>Application events</summary>",
                    "",
                    "```text",
                    *turn[
                        "events"
                    ],
                    "```",
                    "",
                    "</details>",
                    "",
                ])

            if turn.get(
                "runtime_trace"
            ):
                lines.extend([
                    "<details>",
                    "<summary>Safe runtime trace</summary>",
                    "",
                    "```text",
                    *turn[
                        "runtime_trace"
                    ],
                    "```",
                    "",
                    "</details>",
                    "",
                ])

        lines.extend([
            "**Human score:**",
            "",
            "- Understanding / intent: __ / 2",
            "- Context / referent: __ / 2",
            "- Epistemic trust: __ / 2",
            "- Personality: __ / 2",
            "- Initiative/research: __ / 2",
            "- **Total: __ / 10**",
            "- Catastrophic failure? `yes / no`",
            "- Notes:",
            "",
        ])

    return "\n".join(
        lines
    ) + "\n"


def run_benchmark(
    *,
    selection: str,
    case_id: str | None,
) -> tuple[dict[str, Any], Path, Path]:
    import application_service as application_service_module

    _install_non_destructive_benchmark_mode(
        application_service_module
    )

    MaironApplication = (
        application_service_module
        .MaironApplication
    )

    benchmark = _load_cases()

    all_cases = list(
        benchmark.get(
            "cases"
        )
        or []
    )

    if case_id:
        selected = [
            case
            for case in all_cases
            if case.get(
                "id"
            )
            == case_id
        ]

        if not selected:
            raise SystemExit(
                f"Unknown benchmark case: {case_id}"
            )

        selection_name = (
            f"case:{case_id}"
        )

    elif selection == "full":
        selected = all_cases
        selection_name = "full"

    else:
        selected = [
            case
            for case in all_cases
            if case.get(
                "quick"
            )
            is True
        ]
        selection_name = "quick"

    events: list[str] = []

    app = MaironApplication(
        user_name="Oliver",
        event_sink=lambda message: events.append(
            str(
                message
            )
        ),
    )

    report = {
        "schema_version": "1",
        "benchmark": benchmark.get(
            "benchmark"
        ),
        "run_id": datetime.now().strftime(
            "%Y%m%d-%H%M%S"
        ),
        "created_at": datetime.now().astimezone().isoformat(),
        "selection": selection_name,
        "local_model": (
            app.session_status().get(
                "local_model"
            )
        ),
        "scenarios": [],
    }

    total_seconds = 0.0
    timed_turns = 0
    automatic_checks = 0
    automatic_passes = 0
    turn_count = 0

    print()
    print(
        "MAIRON CONVERSATIONAL INTELLIGENCE BENCHMARK"
    )
    print(
        "=" * 68
    )
    print(
        f"Selection: {selection_name}"
    )
    print(
        "Persistence: DISABLED for benchmark prompts"
    )
    print()

    for scenario_number, case in enumerate(
        selected,
        start=1,
    ):
        if scenario_number > 1:
            try:
                app.new_chat()
            except RuntimeError:
                if app.has_pending_approval:
                    app.resolve_pending_approval(
                        approved=False
                    )
                app.new_chat()

        scenario_result = {
            "id": case[
                "id"
            ],
            "category": case[
                "category"
            ],
            "description": case[
                "description"
            ],
            "manual_focus": case[
                "manual_focus"
            ],
            "turns": [],
        }

        print(
            f"[{scenario_number}/{len(selected)}] "
            f"{case['id']}"
        )
        print(
            "-" * 68
        )

        for turn_spec in case[
            "turns"
        ]:
            events.clear()

            user_text = str(
                turn_spec[
                    "user"
                ]
            )

            print(
                f"Oliver: {user_text}"
            )

            provider_stdout = io.StringIO()

            with contextlib.redirect_stdout(
                provider_stdout
            ):
                result = app.submit_text(
                    user_text
                )

            runtime_trace = _safe_runtime_trace(
                provider_stdout.getvalue()
            )

            # Preserve the normal live terminal experience while also storing
            # the filtered trace in the Markdown/JSON benchmark report.
            for trace_line in runtime_trace:
                print(
                    trace_line
                )

            automatic = (
                _automatic_turn_checks(
                    case,
                    turn_spec,
                    result,
                )
            )

            checks = automatic[
                "checks"
            ]

            automatic_checks += len(
                checks
            )

            automatic_passes += sum(
                1
                for item in checks
                if item[
                    "passed"
                ]
            )

            answer = str(
                getattr(
                    result,
                    "answer",
                    "",
                )
                or ""
            )

            response_seconds = getattr(
                result,
                "response_seconds",
                None,
            )

            if isinstance(
                response_seconds,
                (
                    int,
                    float,
                ),
            ):
                total_seconds += float(
                    response_seconds
                )
                timed_turns += 1

            turn_count += 1

            turn_result = {
                "user": user_text,
                "status": str(
                    getattr(
                        result,
                        "status",
                        "",
                    )
                    or ""
                ),
                "answer": answer,
                "intent": getattr(
                    result,
                    "intent",
                    None,
                ),
                "authority": getattr(
                    result,
                    "authority",
                    None,
                ),
                "response_seconds": (
                    round(
                        float(
                            response_seconds
                        ),
                        3,
                    )
                    if isinstance(
                        response_seconds,
                        (
                            int,
                            float,
                        ),
                    )
                    else None
                ),
                "diagnostics": (
                    _clean_diagnostics(
                        getattr(
                            result,
                            "diagnostics",
                            None,
                        )
                    )
                ),
                "events": list(
                    events
                ),
                "runtime_trace": list(
                    runtime_trace
                ),
                "automatic": automatic,
            }

            scenario_result[
                "turns"
            ].append(
                turn_result
            )

            print(
                "Mairon: "
                + (
                    answer
                    or f"[{turn_result['status']}]"
                )
            )

            print(
                "Auto checks: "
                + (
                    "PASS"
                    if automatic[
                        "passed"
                    ]
                    else "FAIL"
                )
            )

            print()

            # Do not grant cloud/action authority merely because a benchmark
            # prompt triggered it. Clear the pending state so later cases can
            # continue.
            if app.has_pending_approval:
                try:
                    app.resolve_pending_approval(
                        approved=False
                    )
                except Exception:
                    pass

        report[
            "scenarios"
        ].append(
            scenario_result
        )

    report[
        "summary"
    ] = {
        "scenario_count": len(
            selected
        ),
        "turn_count": turn_count,
        "automatic_checks": automatic_checks,
        "automatic_passes": automatic_passes,
        "average_response_seconds": (
            (
                total_seconds
                / timed_turns
            )
            if timed_turns
            else 0.0
        ),
    }

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stem = (
        "conversational_intelligence_"
        + report[
            "run_id"
        ]
        + "_"
        + selection_name.replace(
            ":",
            "_",
        )
    )

    json_path = (
        REPORT_DIR
        / f"{stem}.json"
    )

    markdown_path = (
        REPORT_DIR
        / f"{stem}.md"
    )

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown_path.write_text(
        _render_markdown(
            benchmark,
            report,
        ),
        encoding="utf-8",
    )

    print(
        "=" * 68
    )
    print(
        "BENCHMARK COLLECTION COMPLETE"
    )
    print(
        "=" * 68
    )
    print(
        "Automatic checks: "
        f"{automatic_passes}/{automatic_checks}"
    )
    print(
        "Average response: "
        f"{report['summary']['average_response_seconds']:.2f}s"
    )
    print(
        f"JSON report: {json_path}"
    )
    print(
        f"Review report: {markdown_path}"
    )
    print()
    print(
        "The important score is the human 0-10 conversational score, "
        "not the automatic checks."
    )

    return (
        report,
        json_path,
        markdown_path,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run Mairon's non-destructive conversational-intelligence benchmark."
        )
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Run the core conversational scenarios (default)."
        ),
    )

    group.add_argument(
        "--full",
        action="store_true",
        help=(
            "Run every conversational benchmark scenario."
        ),
    )

    group.add_argument(
        "--case",
        help=(
            "Run exactly one case by id."
        ),
    )

    args = parser.parse_args()

    run_benchmark(
        selection=(
            "full"
            if args.full
            else "quick"
        ),
        case_id=args.case,
    )


if __name__ == "__main__":
    main()
