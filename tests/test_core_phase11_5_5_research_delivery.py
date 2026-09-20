import os
import sqlite3
import sys
import tempfile
from pathlib import Path


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


from research import research_jobs
from research.research_delivery import (
    build_research_delivery_text,
    research_delivery_turn_marker,
)


def _verified_result(
    report="Verified research report.",
):
    # Match the real Phase 11.5.4 persistence shape. final_report is structured
    # metadata; final_report_text is the exact verified user-facing report.
    return {
        "research_phase": "final_synthesis_complete",
        "user_ready": True,
        "final_report_verified": True,
        "final_report": {
            "text": report,
            "verified": True,
            "verified_at": "2026-09-20T00:00:00+00:00",
            "source_urls": [
                "https://example.test/source"
            ],
            "source_index": [{
                "title": "Example source",
                "url": "https://example.test/source",
            }],
            "uncertainties": [],
        },
        "final_report_text": report,
        "final_synthesis": {
            "report_text": report,
            "verification": {
                "supported": True,
                "violations": [],
            },
        },
    }


def _delivery_checkpoint():
    return {
        "stage": "final_synthesis_complete",
        "next_stage": "delivery",
        "user_ready": True,
    }


def run():
    old_db = os.environ.get(
        "MAIRON_RESEARCH_JOB_DB"
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = (
            Path(tmp)
            / "research_jobs.sqlite3"
        )

        os.environ[
            "MAIRON_RESEARCH_JOB_DB"
        ] = str(
            db_path
        )

        # --------------------------------------------------
        # 1. Session/client provenance flows into newly-created jobs.
        # --------------------------------------------------

        with research_jobs.research_request_context(
            session_id="session-123",
            channel="text",
            client="application",
        ):
            context_job = (
                research_jobs.create_research_job(
                    topic="delivery provenance test",
                    goal="test provenance",
                    original_request="research delivery provenance",
                    depth="deep",
                )
            )

        assert (
            context_job[
                "metadata"
            ][
                "origin_session_id"
            ]
            == "session-123"
        )
        assert (
            context_job[
                "metadata"
            ][
                "origin_channel"
            ]
            == "text"
        )
        assert (
            context_job[
                "metadata"
            ][
                "origin_client"
            ]
            == "application"
        )

        research_jobs.update_research_job(
            context_job[
                "id"
            ],
            status="cancelled",
        )

        # --------------------------------------------------
        # 2. Completing a verified report automatically queues delivery.
        # --------------------------------------------------

        job = research_jobs.create_research_job(
            topic="Garmin delivery test",
            goal="deliver verified Garmin research",
            original_request="research Garmin in the background",
            depth="deep",
        )

        job = research_jobs.update_research_job(
            job[
                "id"
            ],
            status="completed",
            checkpoint=_delivery_checkpoint(),
            result=_verified_result(),
            resume_automatically=False,
        )

        assert (
            job[
                "delivery_status"
            ]
            == "pending"
        )

        text = build_research_delivery_text(
            job
        )

        assert text is not None
        assert (
            "Garmin delivery test"
            in text
        )
        assert (
            "Verified research report."
            in text
        )
        assert "source_index" not in text
        assert "source_urls" not in text
        assert "{'text':" not in text

        # Backward-compatible string-shaped final_report still delivers cleanly.
        legacy_shape = dict(
            _verified_result(
                "Legacy string report."
            )
        )
        legacy_shape.pop(
            "final_report_text",
            None,
        )
        legacy_shape[
            "final_report"
        ] = "Legacy string report."

        legacy_shape_job = {
            **job,
            "result": legacy_shape,
        }

        legacy_shape_text = build_research_delivery_text(
            legacy_shape_job
        )

        assert legacy_shape_text is not None
        assert "Legacy string report." in legacy_shape_text

        marker = research_delivery_turn_marker(
            job[
                "id"
            ]
        )

        assert marker.startswith(
            "__MAIRON_RESEARCH_DELIVERY__:"
        )

        # --------------------------------------------------
        # 3. Delivery uses an atomic short lease and can be safely released.
        # --------------------------------------------------

        claimed = (
            research_jobs
            .claim_next_research_delivery(
                consumer_id="desktop-a",
                lease_seconds=120,
            )
        )

        assert claimed is not None
        assert (
            claimed[
                "id"
            ]
            == job[
                "id"
            ]
        )
        assert (
            claimed[
                "delivery_status"
            ]
            == "claimed"
        )
        assert (
            claimed[
                "delivery_claim_owner"
            ]
            == "desktop-a"
        )
        assert (
            claimed[
                "delivery_attempt_count"
            ]
            == 1
        )

        assert (
            research_jobs
            .claim_next_research_delivery(
                consumer_id="desktop-b",
                lease_seconds=120,
            )
            is None
        )

        released = (
            research_jobs
            .release_research_delivery(
                job[
                    "id"
                ],
                consumer_id="desktop-a",
            )
        )

        assert (
            released[
                "delivery_status"
            ]
            == "pending"
        )

        reclaimed = (
            research_jobs
            .claim_next_research_delivery(
                consumer_id="desktop-b",
                lease_seconds=120,
            )
        )

        assert reclaimed is not None
        assert (
            reclaimed[
                "delivery_attempt_count"
            ]
            == 2
        )

        # --------------------------------------------------
        # 4. Successful delivery is terminal and survives store reinitialisation.
        # --------------------------------------------------

        delivered = (
            research_jobs
            .complete_research_delivery(
                job[
                    "id"
                ],
                consumer_id="desktop-b",
                delivered_session_id="session-xyz",
            )
        )

        assert (
            delivered[
                "delivery_status"
            ]
            == "delivered"
        )
        assert (
            delivered[
                "delivered_at"
            ]
            is not None
        )
        assert (
            delivered[
                "delivered_session_id"
            ]
            == "session-xyz"
        )

        research_jobs.initialise_research_job_store()

        assert (
            research_jobs
            .claim_next_research_delivery(
                consumer_id="desktop-c",
                lease_seconds=120,
            )
            is None
        )

        # --------------------------------------------------
        # 5. Legacy verified completion migrates to pending delivery.
        # --------------------------------------------------

        legacy = research_jobs.create_research_job(
            topic="legacy verified report",
            goal="test upgrade delivery migration",
            original_request="research this",
            depth="deep",
        )

        legacy = research_jobs.update_research_job(
            legacy[
                "id"
            ],
            status="completed",
            checkpoint=_delivery_checkpoint(),
            result=_verified_result(
                "Legacy verified report."
            ),
            resume_automatically=False,
        )

        # Recreate the exact pre-11.5.5 state after the public update helper has
        # correctly queued it. initialise_research_job_store() must restore it.
        with research_jobs._connect() as connection:
            connection.execute(
                """
                UPDATE research_jobs
                SET delivery_status = 'not_ready',
                    delivery_claim_owner = NULL,
                    delivery_claim_expires_at = NULL
                WHERE id = ?
                """,
                (
                    legacy[
                        "id"
                    ],
                ),
            )

        research_jobs.initialise_research_job_store()

        legacy_after = (
            research_jobs.get_research_job(
                legacy[
                    "id"
                ]
            )
        )

        assert legacy_after is not None
        assert (
            legacy_after[
                "delivery_status"
            ]
            == "pending"
        )

        # --------------------------------------------------
        # 6. Unverified or non-final results never enter the delivery queue.
        # --------------------------------------------------

        unsafe = research_jobs.create_research_job(
            topic="unsafe delivery test",
            goal="must not deliver",
            original_request="research this",
            depth="deep",
        )

        unsafe = research_jobs.update_research_job(
            unsafe[
                "id"
            ],
            status="completed",
            checkpoint=_delivery_checkpoint(),
            result={
                "research_phase": "final_synthesis_review_required",
                "user_ready": True,
                "final_report_verified": False,
                "final_report": "This must never be delivered.",
            },
            resume_automatically=False,
        )

        assert (
            unsafe[
                "delivery_status"
            ]
            == "not_ready"
        )

        # Consume the legacy safe job so static checks below run with no pending
        # delivery ambiguity.
        legacy_claim = (
            research_jobs
            .claim_next_research_delivery(
                consumer_id="cleanup",
            )
        )

        assert legacy_claim is not None
        assert (
            legacy_claim[
                "id"
            ]
            == legacy[
                "id"
            ]
        )

        research_jobs.complete_research_delivery(
            legacy[
                "id"
            ],
            consumer_id="cleanup",
            delivered_session_id="cleanup-session",
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
    # 7. UI/application integration keeps delivery Core-owned and proactive.
    # --------------------------------------------------

    application_source = (
        SRC_DIR
        / "application_service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def poll_research_delivery("
        in application_source
    )
    assert (
        "research_request_context("
        in application_source
    )
    assert (
        "research_delivery_turn_marker("
        in application_source
    )
    assert (
        "append_research_delivery_to_model_history("
        in application_source
    )

    desktop_source = (
        SRC_DIR
        / "desktop_app.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def _poll_research_deliveries("
        in desktop_source
    )
    assert (
        "is_research_delivery_turn("
        in desktop_source
    )
    assert (
        "self.root.after("
        in desktop_source
    )

    terminal_source = (
        SRC_DIR
        / "main.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def deliver_pending_research_results("
        in terminal_source
    )
    assert (
        "claim_next_research_delivery("
        in terminal_source
    )
    assert (
        "research_request_context("
        in terminal_source
    )

    print(
        "Mairon Phase 11.5.5 research delivery tests: PASS"
    )


if __name__ == "__main__":
    run()
