import os
import sqlite3
import sys
from contextlib import closing
import tempfile
from datetime import datetime, timedelta, timezone
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


import research.research_jobs as research_jobs
from research.research_worker import (
    background_research_can_run,
    build_worker_research_query,
    note_interactive_activity,
    run_one_research_job,
)


def _fake_research_success(
    query,
    max_reads=2,
):
    return {
        "success": True,
        "query": query,
        "readable_source_count": 2,
        "sources": [
            {
                "title": "Source A",
                "url": "https://example.com/a",
                "source_host": "example.com",
                "source_quality": "general_web",
                "published_date": None,
                "read_success": True,
            },
            {
                "title": "Source B",
                "url": "https://example.org/b",
                "source_host": "example.org",
                "source_quality": "general_web",
                "published_date": None,
                "read_success": True,
            },
        ],
        "failure_reason": None,
    }


def _fake_packet(
    research_result,
):
    return (
        "TEST EVIDENCE PACKET: "
        + str(
            research_result.get(
                "query"
            )
        )
    )


def run():
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

        # --------------------------------------------------
        # 1. Existing Phase 11.5.1 DBs migrate additively.
        # --------------------------------------------------

        db_path = Path(
            os.environ[
                "MAIRON_RESEARCH_JOB_DB"
            ]
        )

        with closing(
            sqlite3.connect(
                db_path
            )
        ) as connection:
            connection.execute(
                """
                CREATE TABLE research_jobs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    original_request TEXT NOT NULL,
                    source TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    depth TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    error_text TEXT
                )
                """
            )
            connection.commit()

        research_jobs.initialise_research_job_store()

        with closing(
            sqlite3.connect(
                db_path
            )
        ) as connection:
            columns = {
                row[
                    1
                ]
                for row in connection.execute(
                    "PRAGMA table_info(research_jobs)"
                ).fetchall()
            }

        assert "lease_owner" in columns
        assert "lease_expires_at" in columns
        assert "attempt_count" in columns

        # --------------------------------------------------
        # 2. Claiming is atomic and a live lease blocks a second worker.
        # --------------------------------------------------

        deep_job = (
            research_jobs.create_research_job(
                topic="Rhea vs Mina",
                goal="Research enough to form an informed opinion.",
                original_request="Rhea clears Mina",
                source="approved_offer",
                depth="deep",
                metadata={
                    "research_kind": "pairwise_opinion",
                    "left": "Rhea",
                    "right": "Mina",
                },
            )
        )

        assert (
            build_worker_research_query(
                deep_job
            )
            == "Rhea vs Mina"
        )

        claimed = (
            research_jobs.claim_next_research_job(
                worker_id="worker-a",
                lease_seconds=300,
            )
        )

        assert claimed is not None
        assert claimed[
            "id"
        ] == deep_job[
            "id"
        ]
        assert claimed[
            "status"
        ] == "running"
        assert claimed[
            "lease_owner"
        ] == "worker-a"
        assert claimed[
            "attempt_count"
        ] == 1

        assert (
            research_jobs.claim_next_research_job(
                worker_id="worker-b",
                lease_seconds=300,
            )
            is None
        )

        # --------------------------------------------------
        # 3. Expired leases are reclaimable after a worker crash.
        # --------------------------------------------------

        expired = (
            datetime.now(
                timezone.utc
            )
            - timedelta(
                minutes=5
            )
        ).isoformat()

        with research_jobs._connect() as connection:
            connection.execute(
                """
                UPDATE research_jobs
                SET lease_expires_at = ?
                WHERE id = ?
                """,
                (
                    expired,
                    deep_job[
                        "id"
                    ],
                ),
            )

        reclaimed = (
            research_jobs.claim_next_research_job(
                worker_id="worker-b",
                lease_seconds=300,
            )
        )

        assert reclaimed is not None
        assert reclaimed[
            "id"
        ] == deep_job[
            "id"
        ]
        assert reclaimed[
            "lease_owner"
        ] == "worker-b"
        assert reclaimed[
            "attempt_count"
        ] == 2

        # Return it to queued so the worker lifecycle test can claim it.
        research_jobs.update_claimed_research_job(
            deep_job[
                "id"
            ],
            worker_id="worker-b",
            status="queued",
            checkpoint={},
            result={},
        )

        # --------------------------------------------------
        # 4. Deep research executes one real stage, persists evidence, then
        #    pauses honestly for the future iterative-deep-research phase.
        # --------------------------------------------------

        processed = run_one_research_job(
            worker_id="worker-c",
            research_fn=_fake_research_success,
            packet_builder=_fake_packet,
        )

        assert processed is not None
        assert processed[
            "id"
        ] == deep_job[
            "id"
        ]
        assert processed[
            "status"
        ] == "paused"
        assert processed[
            "lease_owner"
        ] is None
        assert processed[
            "checkpoint"
        ][
            "stage"
        ] == "initial_public_evidence_complete"
        assert processed[
            "checkpoint"
        ][
            "next_stage"
        ] == "iterative_deep_research"
        assert (
            processed[
                "result"
            ][
                "user_ready"
            ]
            is False
        )
        assert (
            "TEST EVIDENCE PACKET"
            in processed[
                "result"
            ][
                "evidence_packet"
            ]
        )

        # --------------------------------------------------
        # 5. Quick jobs may finish after the bounded pass.
        # --------------------------------------------------

        quick_job = (
            research_jobs.create_research_job(
                topic="Simple public lookup",
                goal="Quickly verify a small public topic.",
                original_request="research this quickly",
                source="explicit_request",
                depth="quick",
            )
        )

        quick_processed = run_one_research_job(
            worker_id="worker-d",
            research_fn=_fake_research_success,
            packet_builder=_fake_packet,
        )

        assert quick_processed is not None
        assert quick_processed[
            "id"
        ] == quick_job[
            "id"
        ]
        assert quick_processed[
            "status"
        ] == "completed"
        assert (
            quick_processed[
                "result"
            ][
                "user_ready"
            ]
            is True
        )

        # --------------------------------------------------
        # 6. Interactive activity preempts the background worker.
        # --------------------------------------------------

        note_interactive_activity()

        assert (
            background_research_can_run(
                idle_grace_seconds=999,
            )
            is False
        )

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
    # 7. Provider integration keeps the background worker available while
    #    foreground turns hold the stronger whole-turn preemption lease.
    #
    # Phase 11.5.2 originally used note_interactive_activity() as a timestamp
    # signal. Phase 11.5.3.1 intentionally superseded that mechanism with
    # begin_interactive_turn()/end_interactive_turn(), so this regression must
    # validate the current contract rather than fossilise the old implementation.
    # --------------------------------------------------

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "ensure_background_research_worker_started"
        in provider_source
    )

    assert (
        "begin_interactive_turn()"
        in provider_source
    )

    assert (
        "end_interactive_turn()"
        in provider_source
    )

    assert (
        "def _get_response_impl("
        in provider_source
    )

    assert (
        "finally:"
        in provider_source
    )

    assert (
        "grounded_opinion_subject = None"
        in provider_source
    )

    print(
        "Mairon Phase 11.5.2 background worker/lease tests: PASS"
    )


if __name__ == "__main__":
    run()
