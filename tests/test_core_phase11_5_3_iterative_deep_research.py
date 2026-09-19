import os
import sqlite3
import sys
import tempfile
from contextlib import closing
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
    extract_explicit_background_research_request,
)
import research.research_jobs as research_jobs
from research.deep_research import (
    research_collection_decision,
)
from research.research_worker import (
    run_one_research_job,
)


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


class FakeResearch:
    def __init__(self):
        self.calls = []

    def __call__(
        self,
        query,
        max_reads=2,
    ):
        self.calls.append(
            (
                query,
                max_reads,
            )
        )

        call_number = len(
            self.calls
        )

        sources = []

        for index in range(
            max_reads
        ):
            ordinal = (
                (
                    call_number - 1
                )
                * max_reads
                + index
                + 1
            )

            sources.append({
                "title": (
                    "Source "
                    + str(
                        ordinal
                    )
                ),
                "url": (
                    "https://source"
                    + str(
                        ordinal
                    )
                    + ".example/item"
                ),
                "source_host": (
                    "source"
                    + str(
                        ordinal
                    )
                    + ".example"
                ),
                "source_quality": "general_web",
                "published_date": None,
                "read_success": True,
            })

        return {
            "success": True,
            "query": query,
            "readable_source_count": len(
                sources
            ),
            "sources": sources,
            "failure_reason": None,
        }


class FakePlanner:
    def __init__(self):
        self.calls = 0

    def __call__(
        self,
        job,
        result,
    ):
        self.calls += 1

        source_count = len(
            result.get(
                "source_index"
            )
            or []
        )

        if source_count >= 12:
            return {
                "complete": True,
                "reason": (
                    "The important comparison gaps are resolved by the accumulated evidence."
                ),
                "knowledge_gaps": [],
                "search_queries": [],
                "planner": "test_planner",
            }

        return {
            "complete": False,
            "reason": (
                "More independent comparison and drawback evidence is needed."
            ),
            "knowledge_gaps": [
                "Independent comparison evidence",
                "Material drawbacks",
            ],
            "search_queries": [
                "Garmin smartwatch independent comparison",
                "Garmin smartwatch drawbacks limitations",
            ],
            "planner": "test_planner",
        }


def run():
    old_db = os.environ.get(
        "MAIRON_RESEARCH_JOB_DB"
    )

    old_idle = os.environ.get(
        "MAIRON_RESEARCH_IDLE_GRACE_SECONDS"
    )

    try:
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

            os.environ[
                "MAIRON_RESEARCH_IDLE_GRACE_SECONDS"
            ] = "0"

            # --------------------------------------------------
            # 1. Execution timing language must not pollute topic identity.
            # --------------------------------------------------

            cases = {
                (
                    "Research the current Garmin smartwatch models "
                    "in the background."
                ): "the current Garmin smartwatch models",
                (
                    "research running shoes while im asleep"
                ): "running shoes",
                (
                    "research smartwatches overnight."
                ): "smartwatches",
                (
                    "while im asleep, research Re:Zero theories"
                ): "Re:Zero theories",
            }

            for text, expected_topic in cases.items():
                parsed = (
                    extract_explicit_background_research_request(
                        text
                    )
                )

                assert parsed is not None
                assert (
                    parsed[
                        "topic"
                    ]
                    == expected_topic
                )

            # --------------------------------------------------
            # 2. Phase 11.5.2 paused jobs migrate into resumable 11.5.3 work.
            # --------------------------------------------------

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
                        error_text TEXT,
                        lease_owner TEXT,
                        lease_expires_at TEXT,
                        attempt_count INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )

                connection.execute(
                    """
                    INSERT INTO research_jobs (
                        id,
                        created_at,
                        updated_at,
                        status,
                        topic,
                        topic_key,
                        goal,
                        original_request,
                        source,
                        priority,
                        depth,
                        checkpoint_json,
                        result_json,
                        metadata_json,
                        error_text,
                        lease_owner,
                        lease_expires_at,
                        attempt_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "legacy-paused",
                        "2026-09-16T00:00:00+00:00",
                        "2026-09-16T00:01:00+00:00",
                        "paused",
                        "Legacy Garmin research",
                        "legacy garmin research",
                        "Research the topic deeply.",
                        "Research Garmin.",
                        "explicit_request",
                        "background",
                        "deep",
                        (
                            '{"next_stage": "iterative_deep_research", '
                            '"stage": "initial_public_evidence_complete"}'
                        ),
                        (
                            '{"query": "Garmin", '
                            '"readable_source_count": 4, '
                            '"source_index": ['
                            '{"title":"A","url":"https://a.example","source_host":"a.example","read_success":true},'
                            '{"title":"B","url":"https://b.example","source_host":"b.example","read_success":true},'
                            '{"title":"C","url":"https://c.example","source_host":"c.example","read_success":true},'
                            '{"title":"D","url":"https://d.example","source_host":"d.example","read_success":true}'
                            '], '
                            '"evidence_packet":"legacy packet"}'
                        ),
                        "{}",
                        None,
                        None,
                        None,
                        1,
                    ),
                )

                connection.commit()

            research_jobs.initialise_research_job_store()

            migrated = (
                research_jobs.get_research_job(
                    "legacy-paused"
                )
            )

            assert migrated is not None
            assert (
                migrated[
                    "resume_automatically"
                ]
                is True
            )

            claimed_legacy = (
                research_jobs.claim_next_research_job(
                    worker_id="migration-test",
                    lease_seconds=300,
                )
            )

            assert claimed_legacy is not None
            assert (
                claimed_legacy[
                    "id"
                ]
                == "legacy-paused"
            )

            # Remove the synthetic legacy job so the lifecycle test below starts
            # with a clean oldest-job ordering.
            research_jobs.update_claimed_research_job(
                "legacy-paused",
                worker_id="migration-test",
                status="cancelled",
                resume_automatically=False,
            )

            # --------------------------------------------------
            # 3. Deep work continues in one-query checkpoints and reaches a
            #    quality-gated final-synthesis boundary.
            # --------------------------------------------------

            job = research_jobs.create_research_job(
                topic="current Garmin smartwatch models",
                goal=(
                    "Research the current Garmin smartwatch market deeply."
                ),
                original_request=(
                    "Research current Garmin smartwatch models in the background."
                ),
                depth="deep",
                priority="background",
            )

            fake_research = FakeResearch()
            fake_planner = FakePlanner()

            # Initial pass: 4 sources, then auto-resumable pause.
            stage1 = run_one_research_job(
                worker_id="worker-1",
                research_fn=fake_research,
                packet_builder=_fake_packet,
                planner_fn=fake_planner,
            )

            assert stage1 is not None
            assert stage1[
                "id"
            ] == job[
                "id"
            ]
            assert stage1[
                "status"
            ] == "paused"
            assert (
                stage1[
                    "resume_automatically"
                ]
                is True
            )
            assert stage1[
                "checkpoint"
            ][
                "next_stage"
            ] == "iterative_deep_research"
            assert len(
                stage1[
                    "result"
                ][
                    "source_index"
                ]
            ) == 4

            # Planner creates two targeted queries; one bounded query is executed.
            stage2 = run_one_research_job(
                worker_id="worker-2",
                research_fn=fake_research,
                packet_builder=_fake_packet,
                planner_fn=fake_planner,
            )

            assert stage2 is not None
            assert stage2[
                "status"
            ] == "paused"
            assert stage2[
                "resume_automatically"
            ] is True
            assert len(
                stage2[
                    "checkpoint"
                ][
                    "pending_queries"
                ]
            ) == 1
            assert len(
                stage2[
                    "result"
                ][
                    "source_index"
                ]
            ) == 8

            # The second pending query runs without asking the planner again.
            planner_calls_before = (
                fake_planner.calls
            )

            stage3 = run_one_research_job(
                worker_id="worker-3",
                research_fn=fake_research,
                packet_builder=_fake_packet,
                planner_fn=fake_planner,
            )

            assert stage3 is not None
            assert fake_planner.calls == planner_calls_before
            assert len(
                stage3[
                    "result"
                ][
                    "source_index"
                ]
            ) == 12
            assert len(
                stage3[
                    "result"
                ][
                    "rounds"
                ]
            ) == 3

            # With floors met, the next planner pass may declare evidence
            # collection complete. Phase 11.5.4 can now resume final synthesis
            # automatically from that durable boundary.
            stage4 = run_one_research_job(
                worker_id="worker-4",
                research_fn=fake_research,
                packet_builder=_fake_packet,
                planner_fn=fake_planner,
            )

            assert stage4 is not None
            assert stage4[
                "status"
            ] == "paused"
            assert (
                stage4[
                    "resume_automatically"
                ]
                is True
            )
            assert stage4[
                "checkpoint"
            ][
                "next_stage"
            ] == "final_synthesis"
            assert (
                stage4[
                    "result"
                ][
                    "research_phase"
                ]
                == "deep_evidence_collection_complete"
            )
            assert (
                stage4[
                    "checkpoint"
                ][
                    "quality"
                ][
                    "minimum_floor_met"
                ]
                is True
            )

            # --------------------------------------------------
            # 4. SQLite handles remain Windows-safe after the entire lifecycle.
            # --------------------------------------------------

            db_path.unlink()

    finally:
        if old_db is None:
            os.environ.pop(
                "MAIRON_RESEARCH_JOB_DB",
                None,
            )
        else:
            os.environ[
                "MAIRON_RESEARCH_JOB_DB"
            ] = old_db

        if old_idle is None:
            os.environ.pop(
                "MAIRON_RESEARCH_IDLE_GRACE_SECONDS",
                None,
            )
        else:
            os.environ[
                "MAIRON_RESEARCH_IDLE_GRACE_SECONDS"
            ] = old_idle

    # --------------------------------------------------
    # 5. Safety-cap convergence: once the deterministic deep-research floor is
    #    met, an indefinitely cautious planner may no longer veto synthesis.
    #    If the floor is still missing at the cap, fail closed for review.
    # --------------------------------------------------

    cap_job = {
        "depth": "deep",
    }

    cap_result = {
        "rounds": [
            {"query": "q" + str(index)}
            for index in range(
                10
            )
        ],
        "source_index": [
            {
                "source_host": (
                    "source"
                    + str(index)
                    + ".example"
                )
            }
            for index in range(
                12
            )
        ],
    }

    cautious_plan = {
        "complete": False,
        "reason": "The planner would prefer still more evidence.",
        "knowledge_gaps": [
            "Potentially unresolved catalogue edge cases"
        ],
        "search_queries": [
            "another broad lookup"
        ],
    }

    cap_decision = research_collection_decision(
        cap_job,
        cap_result,
        cautious_plan,
    )

    assert (
        cap_decision[
            "state"
        ]
        == "evidence_collection_complete"
    )
    assert (
        cap_decision.get(
            "completion_mode"
        )
        == "safety_cap_floor_met"
    )

    weak_cap_result = {
        **cap_result,
        "source_index": [
            {
                "source_host": (
                    "weak"
                    + str(index)
                    + ".example"
                )
            }
            for index in range(
                4
            )
        ],
    }

    weak_cap_decision = research_collection_decision(
        cap_job,
        weak_cap_result,
        cautious_plan,
    )

    assert (
        weak_cap_decision[
            "state"
        ]
        == "review_required"
    )

    # --------------------------------------------------
    # 6. Provider starts the worker on every live turn so old paused work can
    #    resume after an app restart, while the foreground turn is protected
    #    by the whole-turn interaction lease introduced in Phase 11.5.3.1.
    # --------------------------------------------------

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
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
        "ensure_background_research_worker_started()"
        in provider_source
    )

    worker_source = (
        SRC_DIR
        / "research"
        / "research_worker.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "[Research] Claimed background job:"
        in worker_source
    )

    assert (
        "[Research] Deep research query started:"
        in worker_source
    )

    assert (
        "[Research] Deep-research round cap reached;"
        in worker_source
    )

    assert (
        "remaining_queries = []"
        in worker_source
    )

    print(
        "Mairon Phase 11.5.3 iterative deep research tests: PASS"
    )


if __name__ == "__main__":
    run()