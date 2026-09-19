import sys
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
    runtime_research_year,
)


def run():
    # --------------------------------------------------
    # 1. "Current" research cannot silently fall back to a stale training year.
    # --------------------------------------------------

    current_year = runtime_research_year()

    job = {
        "topic": "current Acme smartwatch models",
        "goal": "Research the current Acme smartwatch models.",
        "original_request": (
            "Research the current Acme smartwatch models in the background."
        ),
        "metadata": {},
        "depth": "deep",
    }

    assert (
        classify_research_goal_scope(
            job
        )
        == "catalogue_lookup"
    )

    stale_year = (
        current_year
        - 1
    )

    stale_query = (
        "Acme smartwatch official lineup "
        + str(
            stale_year
        )
    )

    result = {
        "rounds": [],
        "source_index": [],
        "evidence_packets": [],
    }

    violations = (
        planner_query_grounding_violations(
            job,
            result,
            stale_query,
        )
    )

    assert any(
        "runtime year" in item
        for item in violations
    )

    grounded = ground_planner_search_queries(
        job,
        result,
        {
            "complete": False,
            "reason": "Need current lineup verification.",
            "knowledge_gaps": [
                "Current official lineup."
            ],
            "search_queries": [
                stale_query,
            ],
            "planner": "local_model",
        },
    )

    assert all(
        str(
            stale_year
        ) not in query
        for query in grounded[
            "search_queries"
        ]
    )

    # The real current year remains legal.
    assert (
        planner_query_grounding_violations(
            job,
            result,
            "Acme smartwatch lineup "
            + str(
                current_year
            ),
        )
        == []
    )

    # A historical year becomes legal only after retrieved evidence actually
    # establishes that it matters to the current-lineup question.
    evidence_result = {
        "rounds": [],
        "source_index": [
            {
                "title": (
                    "Acme "
                    + str(
                        stale_year
                    )
                    + " models now discontinued"
                ),
                "url": "https://example.com/history",
            }
        ],
        "evidence_packets": [],
    }

    assert (
        planner_query_grounding_violations(
            job,
            evidence_result,
            stale_query,
        )
        == []
    )

    # --------------------------------------------------
    # 2. Day-overview workflow must have a deterministic nonblank fallback.
    # --------------------------------------------------

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def build_safe_day_overview_fallback("
        in provider_source
    )

    assert (
        "Day overview model returned blank"
        in provider_source
    )

    assert (
        "think=False"
        in provider_source
    )

    assert (
        "content = build_safe_day_overview_fallback("
        in provider_source
    )

    print(
        "Mairon Phase 11.5.3.2 date-grounding/day-overview fallback tests: PASS"
    )


if __name__ == "__main__":
    run()
