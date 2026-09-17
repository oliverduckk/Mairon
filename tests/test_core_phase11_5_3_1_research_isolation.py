import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from research.deep_research import (
    classify_research_goal_scope,
    ground_planner_search_queries,
    planner_query_grounding_violations,
)
from research.research_worker import (
    active_interactive_turn_count,
    background_research_can_run,
    begin_interactive_turn,
    canonical_research_topic,
    end_interactive_turn,
)


def run():
    # --------------------------------------------------
    # 1. A foreground turn blocks research for its whole lifetime,
    #    even when the nominal idle grace is zero.
    # --------------------------------------------------

    baseline = active_interactive_turn_count()

    begin_interactive_turn()

    try:
        assert (
            active_interactive_turn_count()
            == baseline + 1
        )

        assert (
            background_research_can_run(
                idle_grace_seconds=0,
            )
            is False
        )

        # The old timestamp-only design would eventually have allowed this.
        time.sleep(
            0.02
        )

        assert (
            background_research_can_run(
                idle_grace_seconds=0,
            )
            is False
        )

    finally:
        end_interactive_turn()

    assert (
        active_interactive_turn_count()
        == baseline
    )

    # --------------------------------------------------
    # 2. Old durable jobs recover a clean runtime topic from the original
    #    explicit request rather than preserving execution wording.
    # --------------------------------------------------

    legacy_job = {
        "topic": "the current Garmin smartwatch models in the background",
        "original_request": (
            "Research the current Garmin smartwatch models in the background."
        ),
        "metadata": {},
    }

    assert (
        canonical_research_topic(
            legacy_job
        )
        == "the current Garmin smartwatch models"
    )

    # --------------------------------------------------
    # 3. Planner may target a specific model only after that identity appears
    #    in retrieved evidence.
    # --------------------------------------------------

    job = {
        "topic": "current Acme smartwatches",
        "goal": "Compare the current Acme smartwatch lineup.",
        "original_request": "Research current Acme smartwatches.",
        "metadata": {},
        "depth": "deep",
    }

    result_without_model = {
        "rounds": [
            {
                "query": "current Acme smartwatches",
            }
        ],
        "source_index": [
            {
                "title": "Acme Smartwatch Catalogue",
                "url": "https://example.com/catalogue",
            }
        ],
        "evidence_packets": [
            {
                "query": "current Acme smartwatches",
                "packet": (
                    "Evidence discusses the current Acme smartwatch catalogue "
                    "without naming a numbered Pro model."
                ),
            }
        ],
    }

    invented_query = (
        "Acme Falcon 9 battery life independent review"
    )

    violations = (
        planner_query_grounding_violations(
            job,
            result_without_model,
            invented_query,
        )
    )

    assert violations
    assert any(
        "Acme Falcon 9" in item
        or "Falcon 9" in item
        for item in violations
    )

    plan = {
        "complete": False,
        "reason": "Need battery evidence.",
        "knowledge_gaps": [
            "Independent battery testing."
        ],
        "search_queries": [
            invented_query,
        ],
        "planner": "local_model",
    }

    grounded = ground_planner_search_queries(
        job,
        result_without_model,
        plan,
    )

    assert (
        grounded[
            "planner"
        ]
        == "deterministic_fallback_after_query_grounding_rejection"
    )

    assert grounded[
        "rejected_search_queries"
    ]

    assert all(
        "Falcon 9" not in query
        for query in grounded[
            "search_queries"
        ]
    )

    # Planner-authored durable notes must obey the same grounding boundary.
    # An invented identity may not survive in knowledge_gaps/reason merely
    # because the actual search query was generic and therefore safe.
    note_plan = {
        "complete": False,
        "reason": (
            "Acme Falcon 9 may be a current flagship that needs confirmation."
        ),
        "knowledge_gaps": [
            "Confirm whether Acme Falcon 9 is currently active.",
            "Confirm the breadth of the current official catalogue.",
        ],
        "search_queries": [
            "current Acme smartwatch lineup official catalogue",
        ],
        "planner": "local_model",
    }

    grounded_notes = (
        ground_planner_search_queries(
            job,
            result_without_model,
            note_plan,
        )
    )

    assert grounded_notes[
        "search_queries"
    ] == [
        "current Acme smartwatch lineup official catalogue"
    ]

    assert all(
        "Falcon 9" not in gap
        for gap in grounded_notes[
            "knowledge_gaps"
        ]
    )

    assert (
        "Falcon 9"
        not in grounded_notes[
            "reason"
        ]
    )

    assert (
        "Confirm the breadth of the current official catalogue."
        in grounded_notes[
            "knowledge_gaps"
        ]
    )

    assert set(
        grounded_notes[
            "rejected_planner_note_fields"
        ]
    ) == {
        "knowledge_gaps",
        "reason",
    }

    # Once the exact model identity is actually in retrieved evidence, Core may
    # allow the planner to investigate it further.
    result_with_model = {
        **result_without_model,
        "source_index": [
            {
                "title": "Acme Falcon 9 Smartwatch",
                "url": "https://example.com/falcon-9",
            }
        ],
        "evidence_packets": [
            {
                "query": "current Acme smartwatches",
                "packet": (
                    "The official catalogue identifies the Acme Falcon 9 "
                    "as a current smartwatch model."
                ),
            }
        ],
    }

    assert (
        planner_query_grounding_violations(
            job,
            result_with_model,
            invented_query,
        )
        == []
    )

    grounded_notes_with_evidence = (
        ground_planner_search_queries(
            job,
            result_with_model,
            note_plan,
        )
    )

    assert any(
        "Falcon 9" in gap
        for gap in grounded_notes_with_evidence[
            "knowledge_gaps"
        ]
    )

    assert (
        "Falcon 9"
        in grounded_notes_with_evidence[
            "reason"
        ]
    )

    assert (
        grounded_notes_with_evidence[
            "rejected_planner_note_fields"
        ]
        == []
    )

    # --------------------------------------------------
    # 4. Deep means careful, not unlimited breadth.
    # --------------------------------------------------

    assert (
        classify_research_goal_scope({
            "topic": "current Acme smartwatch models",
            "goal": "Research the current Acme smartwatch models.",
            "original_request": (
                "Research the current Acme smartwatch models in the background."
            ),
            "metadata": {},
        })
        == "catalogue_lookup"
    )

    assert (
        classify_research_goal_scope({
            "topic": "Acme smartwatches",
            "goal": "Work out which Acme smartwatch would be best for me.",
            "original_request": (
                "Research Acme smartwatches and tell me which one is best for me."
            ),
            "metadata": {},
        })
        == "purchase_decision"
    )

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "def _get_response_impl(" in provider_source
    assert "def get_response(" in provider_source
    assert "begin_interactive_turn()" in provider_source
    assert "end_interactive_turn()" in provider_source
    assert "finally:" in provider_source

    print(
        "Mairon Phase 11.5.3.1 foreground-preemption/query-grounding tests: PASS"
    )


if __name__ == "__main__":
    run()
