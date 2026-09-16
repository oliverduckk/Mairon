import os
import sqlite3
import sys
import tempfile
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


from core.conversational_research import (
    build_background_research_offer_text,
    build_pairwise_background_research_opportunity,
    classify_research_permission_reply,
    extract_explicit_background_research_request,
)
import research.research_jobs as research_jobs


def run():
    # --------------------------------------------------
    # 1. Explicit background research requests become durable job specs.
    # --------------------------------------------------

    request = (
        extract_explicit_background_research_request(
            "while im asleep, research running shoes for me"
        )
    )

    assert request is not None
    assert request[
        "topic"
    ] == "running shoes for me"
    assert request[
        "priority"
    ] == "background"
    assert request[
        "depth"
    ] == "deep"

    request = (
        extract_explicit_background_research_request(
            "do some research on smart watch models"
        )
    )

    assert request is not None
    assert request[
        "topic"
    ] == "smart watch models"

    assert (
        extract_explicit_background_research_request(
            "what are the best smart watches?"
        )
        is None
    )

    # --------------------------------------------------
    # 2. Research permission replies are deliberately narrow.
    # --------------------------------------------------

    assert (
        classify_research_permission_reply(
            "go for it"
        )
        == "approve"
    )

    assert (
        classify_research_permission_reply(
            "yeah"
        )
        == "approve"
    )

    assert (
        classify_research_permission_reply(
            "nah"
        )
        == "decline"
    )

    assert (
        classify_research_permission_reply(
            "what's the weather tomorrow?"
        )
        is None
    )

    # --------------------------------------------------
    # 3. Pairwise debate can create a permission-gated research opportunity.
    # --------------------------------------------------

    subject = {
        "kind": "pairwise_comparison",
        "left": "Rhea",
        "right": "Mina",
    }

    opportunity = (
        build_pairwise_background_research_opportunity(
            opinion_subject=subject,
            opinion_entry=None,
            user_input="Rhea clears Mina",
            intent="share_opinion",
        )
    )

    assert opportunity is not None
    assert opportunity[
        "topic"
    ] == "Rhea vs Mina"
    assert opportunity[
        "source"
    ] == "research_offer"

    offer = (
        build_background_research_offer_text(
            opportunity
        )
    )

    assert "Rhea vs Mina" in offer
    assert "Want me to research" in offer

    established_opinion = {
        "position": "left",
    }

    assert (
        build_pairwise_background_research_opportunity(
            opinion_subject=subject,
            opinion_entry=established_opinion,
            user_input="Rhea clears Mina",
            intent="share_opinion",
        )
        is None
    )

    # --------------------------------------------------
    # 4. Approved jobs are persistent, background-priority, and deduplicated.
    # --------------------------------------------------

    old_db = os.environ.get(
        "MAIRON_RESEARCH_JOB_DB"
    )

    with tempfile.TemporaryDirectory() as tmp:
        os.environ[
            "MAIRON_RESEARCH_JOB_DB"
        ] = str(
            Path(tmp)
            / "research_jobs.sqlite3"
        )

        # Windows regression: leaving Core's database context must close the
        # underlying sqlite3 handle, not merely commit it. Otherwise cleanup
        # fails with WinError 32 because research_jobs.sqlite3 remains locked.
        with research_jobs._connect() as probe_connection:
            probe_connection.execute(
                "SELECT 1"
            ).fetchone()

        connection_was_closed = False

        try:
            probe_connection.execute(
                "SELECT 1"
            )
        except sqlite3.ProgrammingError:
            connection_was_closed = True

        assert connection_was_closed

        first = (
            research_jobs.create_research_job(
                topic="Rhea vs Mina",
                goal="Learn enough to form an informed opinion.",
                original_request="Rhea clears Mina",
                source="approved_offer",
            )
        )

        assert first[
            "status"
        ] == "queued"
        assert first[
            "priority"
        ] == "background"
        assert first[
            "depth"
        ] == "deep"
        assert (
            first[
                "metadata"
            ][
                "interactive_work_preempts_job"
            ]
            is True
        )

        second = (
            research_jobs.create_research_job(
                topic="Rhea vs Mina",
                goal="Duplicate request should not create another active job.",
                original_request="research that",
                source="explicit_request",
            )
        )

        assert second[
            "id"
        ] == first[
            "id"
        ]
        assert second[
            "deduplicated"
        ] is True

        queued = (
            research_jobs.list_research_jobs(
                statuses=[
                    "queued"
                ]
            )
        )

        assert len(
            queued
        ) == 1

    if old_db is None:
        os.environ.pop(
            "MAIRON_RESEARCH_JOB_DB",
            None,
        )
    else:
        os.environ[
            "MAIRON_RESEARCH_JOB_DB"
        ] = old_db

    # --------------------------------------------------
    # 5. Provider integration preserves conversation-scoped permission.
    # --------------------------------------------------

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "MAIRON_PENDING_RESEARCH_PROPOSAL:"
        in provider_source
    )
    assert (
        "MAIRON_RESOLVED_RESEARCH_PROPOSAL:"
        in provider_source
    )
    assert (
        "handle_pending_research_permission_reply"
        in provider_source
    )
    assert (
        "handle_explicit_background_research_request"
        in provider_source
    )
    assert (
        "requesting permission for background research"
        in provider_source
    )
    assert (
        "grounded_opinion_subject = None"
        in provider_source
    )
    assert (
        "find_pairwise_opinion_integrity_violations"
        in provider_source
    )

    print(
        "Mairon Phase 11.5.1 research permission/queue tests: PASS"
    )


if __name__ == "__main__":
    run()
