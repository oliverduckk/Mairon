import json
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

BENCHMARK_DIR = (
    PROJECT_ROOT
    / "benchmarks"
)

CASES_PATH = (
    BENCHMARK_DIR
    / "conversational_intelligence_cases.json"
)

RUNNER_PATH = (
    BENCHMARK_DIR
    / "run_conversational_intelligence.py"
)


def run():
    assert CASES_PATH.is_file()
    assert RUNNER_PATH.is_file()

    payload = json.loads(
        CASES_PATH.read_text(
            encoding="utf-8",
        )
    )

    assert (
        payload[
            "schema_version"
        ]
        == "1"
    )

    dimensions = (
        payload[
            "scoring"
        ][
            "dimensions"
        ]
    )

    assert len(
        dimensions
    ) == 5

    assert {
        item[
            "id"
        ]
        for item in dimensions
    } == {
        "understanding",
        "context",
        "trust",
        "personality",
        "initiative",
    }

    cases = payload[
        "cases"
    ]

    assert len(
        cases
    ) >= 15

    ids = [
        case[
            "id"
        ]
        for case in cases
    ]

    assert len(
        ids
    ) == len(
        set(
            ids
        )
    )

    quick_cases = [
        case
        for case in cases
        if case.get(
            "quick"
        )
        is True
    ]

    assert len(
        quick_cases
    ) >= 8

    categories = {
        case[
            "category"
        ]
        for case in cases
    }

    required_categories = {
        "epistemic_ambiguity",
        "casual_conversation",
        "opinion_debate",
        "conversation_continuity",
        "relationship_banter",
        "seriousness",
        "current_information",
        "topic_switching",
    }

    assert (
        required_categories
        <= categories
    )

    assert any(
        len(
            case[
                "turns"
            ]
        )
        >= 2
        for case in cases
    )

    for case in cases:
        assert str(
            case.get(
                "description",
                "",
            )
        ).strip()

        assert str(
            case.get(
                "manual_focus",
                "",
            )
        ).strip()

        turns = case.get(
            "turns"
        )

        assert isinstance(
            turns,
            list,
        )

        assert turns

        for turn in turns:
            assert str(
                turn.get(
                    "user",
                    "",
                )
            ).strip()

    # Regression guard for Exhibit A: the benchmark must retain a direct
    # unknown/current-reference case and explicitly reject the old confident
    # "not a thing" failure mode.
    exhibit_a = next(
        case
        for case in cases
        if case[
            "id"
        ] == "current_media_ambiguity"
    )

    forbidden = {
        fragment.lower()
        for fragment in (
            exhibit_a[
                "turns"
            ][
                0
            ].get(
                "forbidden_answer_fragments",
                [],
            )
        )
    }

    assert "that's not a thing" in forbidden
    assert "not a thing" in forbidden

    # Benchmark runs must be non-destructive to Oliver's normal local history
    # and preference state.
    runner_source = (
        RUNNER_PATH.read_text(
            encoding="utf-8",
        )
    )

    assert (
        "_install_non_destructive_benchmark_mode"
        in runner_source
    )

    assert (
        "record_conversation_turn"
        in runner_source
    )

    assert (
        "record_chat_turn"
        in runner_source
    )

    assert (
        "capture_user_preference"
        in runner_source
    )

    assert (
        "data"
        in runner_source
        and "private"
        in runner_source
        and "benchmarks"
        in runner_source
    )

    # The benchmark may contain concrete media/entity examples, but it must
    # remain evaluation-only rather than adding title-specific production
    # branches.
    assert (
        "application_service.py"
        not in str(
            CASES_PATH
        )
    )

    print(
        "Mairon Phase 11.1 conversational-intelligence benchmark schema tests: PASS"
    )


if __name__ == "__main__":
    run()
