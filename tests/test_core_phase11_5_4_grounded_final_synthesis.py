import json
import os
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


import research.research_jobs as research_jobs
from research.final_synthesis import (
    MAX_FINAL_SYNTHESIS_PACKET_CHARACTERS,
    MAX_FINAL_SYNTHESIS_PACKETS,
    MAX_FINAL_SYNTHESIS_SOURCES,
    build_final_synthesis_evidence,
)
from research.public_factual_grounding import (
    verify_public_factual_draft,
)
from research.research_worker import (
    run_one_research_job,
)


def _source(
    index,
):
    return {
        "title": f"Source {index}",
        "url": f"https://source{index}.example/item",
        "source_host": f"source{index}.example",
        "source_quality": "general_web",
        "published_date": None,
        "read_success": True,
    }


def _packet(
    index,
    size=500,
):
    body = (
        "Grounded evidence sentence "
        + str(
            index
        )
        + ". "
    )

    return {
        "query": (
            "test query "
            + str(
                index
            )
        ),
        "packet": (
            "CORE PUBLIC FACTUAL EVIDENCE PACKET:\n"
            + json.dumps({
                "freshness_required": False,
                "forecast_requested": False,
                "sources": [{
                    "source_id": "S1",
                    "title": f"Source {index}",
                    "url": f"https://source{index}.example/item",
                    "content_excerpt": (
                        body
                        * max(
                            1,
                            int(
                                size
                                / max(
                                    len(
                                        body
                                    ),
                                    1,
                                )
                            ),
                        )
                    ),
                }],
            })
        ),
    }


def _seed_final_synthesis_job(
    *,
    topic,
):
    job = research_jobs.create_research_job(
        topic=topic,
        goal=(
            "Compare the evidence and produce a grounded final recommendation."
        ),
        original_request=(
            "Research the options deeply and tell me which one fits the evidence best."
        ),
        depth="deep",
        priority="background",
    )

    result = {
        "research_phase": "deep_evidence_collection_complete",
        "user_ready": False,
        "query": topic,
        "readable_source_count": 2,
        "source_index": [
            _source(1),
            _source(2),
        ],
        "rounds": [{
            "round": 1,
            "stage": "initial_public_evidence",
            "query": topic,
        }],
        "evidence_packets": [
            _packet(1),
            _packet(2),
        ],
        "planner_history": [{
            "reason": (
                "THIS PLANNER TEXT MUST NEVER BECOME FINAL SYNTHESIS EVIDENCE"
            ),
            "search_queries": [
                "invented planner query"
            ],
        }],
        "quality": {
            "minimum_floor_met": True,
            "source_count": 2,
            "unique_host_count": 2,
        },
    }

    checkpoint = {
        "stage": "deep_evidence_collection_complete",
        "next_stage": "final_synthesis",
        "user_ready": False,
        "quality": result[
            "quality"
        ],
    }

    return research_jobs.update_research_job(
        job[
            "id"
        ],
        status="paused",
        checkpoint=checkpoint,
        result=result,
        resume_automatically=True,
    )


class FakeSynthesis:
    def __init__(
        self,
    ):
        self.calls = 0

    def __call__(
        self,
        job,
        result,
    ):
        self.calls += 1

        assert (
            result[
                "research_phase"
            ]
            == "deep_evidence_collection_complete"
        )

        return {
            "success": True,
            "report_text": (
                "The stored evidence supports Option A for the requested comparison. "
                "The evidence is narrower on long-term durability, so that point remains uncertain."
            ),
            "uncertainties": [
                "Long-term durability is not established by the stored evidence."
            ],
            "source_urls": [
                "https://source1.example/item",
                "https://source2.example/item",
            ],
            "model": "fake-synthesis",
        }


class _FakeMessage:
    def __init__(
        self,
        content,
    ):
        self.content = content


class _FakeChatResponse:
    def __init__(
        self,
        content,
    ):
        self.message = _FakeMessage(
            content
        )


class RecordingLongVerifierClient:
    def __init__(
        self,
        sentence_count,
    ):
        self.sentence_count = int(
            sentence_count
        )
        self.calls = []

    def chat(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return _FakeChatResponse(
            json.dumps({
                "supported": True,
                "unsupported_claims": [],
                "sentence_assessments": [
                    {
                        "index": index,
                        "supported": True,
                    }
                    for index in range(
                        1,
                        self.sentence_count + 1,
                    )
                ],
            })
        )


class FakeVerifier:
    def __init__(
        self,
        supported=True,
    ):
        self.supported = bool(
            supported
        )
        self.calls = 0

    def __call__(
        self,
        job,
        result,
        draft,
    ):
        self.calls += 1

        assert draft
        assert (
            result.get(
                "final_synthesis"
            )
            is not None
        )

        if self.supported:
            return {
                "supported": True,
                "violations": [],
                "sentence_assessments": [
                    {
                        "index": 1,
                        "supported": True,
                    },
                    {
                        "index": 2,
                        "supported": True,
                    },
                ],
                "model": "fake-verifier",
            }

        return {
            "supported": False,
            "violations": [
                "unsupported public factual claim: invented specification"
            ],
            "sentence_assessments": [
                {
                    "index": 1,
                    "supported": False,
                },
            ],
            "model": "fake-verifier",
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
            # 1. Final synthesis evidence is bounded and planner-free.
            # --------------------------------------------------

            evidence_job = {
                "topic": "bounded evidence test",
                "goal": "Produce a grounded answer.",
                "original_request": "Research this deeply.",
                "depth": "deep",
                "metadata": {},
            }

            evidence_result = {
                "quality": {
                    "minimum_floor_met": True,
                },
                "source_index": [
                    _source(
                        index
                    )
                    for index in range(
                        45
                    )
                ],
                "evidence_packets": [
                    _packet(
                        index,
                        size=1800,
                    )
                    for index in range(
                        16
                    )
                ],
                "planner_history": [{
                    "reason": "UNTRUSTED PLANNER ASSERTION",
                }],
            }

            evidence = build_final_synthesis_evidence(
                evidence_job,
                evidence_result,
            )

            assert len(
                evidence[
                    "source_index"
                ]
            ) <= MAX_FINAL_SYNTHESIS_SOURCES

            assert len(
                evidence[
                    "evidence_packets"
                ]
            ) <= MAX_FINAL_SYNTHESIS_PACKETS

            packet_characters = sum(
                len(
                    packet[
                        "packet"
                    ]
                )
                for packet in evidence[
                    "evidence_packets"
                ]
            )

            assert (
                packet_characters
                <= MAX_FINAL_SYNTHESIS_PACKET_CHARACTERS
            )

            evidence_text = json.dumps(
                evidence,
                ensure_ascii=False,
            )

            assert (
                "UNTRUSTED PLANNER ASSERTION"
                not in evidence_text
            )

            assert (
                "planner_history"
                not in evidence_text
            )

            # --------------------------------------------------
            # 2. Upgrade recovery: an old 11.5.3 final-synthesis pause becomes
            #    automatically resumable when the 11.5.4 store opens it.
            # --------------------------------------------------

            migration_job = (
                research_jobs.create_research_job(
                    topic="migration final synthesis",
                    goal="test migration",
                    original_request="test migration",
                    depth="deep",
                    priority="background",
                )
            )

            migration_job = (
                research_jobs.update_research_job(
                    migration_job[
                        "id"
                    ],
                    status="paused",
                    checkpoint={
                        "stage": "deep_evidence_collection_complete",
                        "next_stage": "final_synthesis",
                        "user_ready": False,
                    },
                    resume_automatically=False,
                )
            )

            # Seed the exact stale 11.5.3 condition directly. Public reads call
            # initialise_research_job_store(), so observing the stale flag through
            # get_research_job() would itself trigger the migration first.
            with research_jobs._connect() as connection:
                connection.execute(
                    """
                    UPDATE research_jobs
                    SET resume_automatically = 0
                    WHERE id = ?
                    """,
                    (
                        migration_job[
                            "id"
                        ],
                    ),
                )

            research_jobs.initialise_research_job_store()

            migrated = research_jobs.get_research_job(
                migration_job[
                    "id"
                ]
            )

            assert migrated is not None
            assert (
                migrated[
                    "resume_automatically"
                ]
                is True
            )

            research_jobs.update_research_job(
                migration_job[
                    "id"
                ],
                status="cancelled",
                resume_automatically=False,
            )

            # --------------------------------------------------
            # 3. Upgrade recovery: the old max-round review state is no longer a
            #    dead end when its deterministic evidence floor was already met.
            #    It migrates to final_synthesis, while unrelated review states do
            #    not get auto-resumed.
            # --------------------------------------------------

            cap_quality = {
                "minimum_rounds": 3,
                "minimum_sources": 12,
                "minimum_unique_hosts": 5,
                "maximum_rounds": 10,
                "round_count": 12,
                "source_count": 34,
                "unique_host_count": 18,
                "minimum_floor_met": True,
                "maximum_rounds_reached": True,
            }

            old_cap_job = research_jobs.create_research_job(
                topic="legacy safety-cap review",
                goal="test legacy cap migration",
                original_request="research this deeply",
                depth="deep",
                priority="background",
            )

            old_cap_job = research_jobs.update_research_job(
                old_cap_job[
                    "id"
                ],
                status="paused",
                checkpoint={
                    "stage": "deep_research_review_required",
                    "next_stage": "research_review_required",
                    "user_ready": False,
                    "pending_queries": [],
                    "quality": cap_quality,
                    "review_reason": (
                        "The deep-research safety cap was reached before both the "
                        "planner and deterministic evidence floors agreed that the "
                        "important knowledge gaps were resolved."
                    ),
                },
                result={
                    "research_phase": "deep_research_review_required",
                    "user_ready": False,
                    "quality": cap_quality,
                    "source_index": [
                        _source(
                            index
                        )
                        for index in range(
                            34
                        )
                    ],
                    "evidence_packets": [
                        _packet(
                            1
                        ),
                        _packet(
                            2
                        ),
                    ],
                },
                resume_automatically=False,
            )

            with research_jobs._connect() as connection:
                connection.execute(
                    """
                    UPDATE research_jobs
                    SET resume_automatically = 0
                    WHERE id = ?
                    """,
                    (
                        old_cap_job[
                            "id"
                        ],
                    ),
                )

            research_jobs.initialise_research_job_store()

            migrated_cap = research_jobs.get_research_job(
                old_cap_job[
                    "id"
                ]
            )

            assert migrated_cap is not None
            assert (
                migrated_cap[
                    "resume_automatically"
                ]
                is True
            )
            assert (
                migrated_cap[
                    "checkpoint"
                ][
                    "stage"
                ]
                == "deep_evidence_collection_complete"
            )
            assert (
                migrated_cap[
                    "checkpoint"
                ][
                    "next_stage"
                ]
                == "final_synthesis"
            )
            assert (
                migrated_cap[
                    "result"
                ][
                    "research_phase"
                ]
                == "deep_evidence_collection_complete"
            )

            research_jobs.update_research_job(
                old_cap_job[
                    "id"
                ],
                status="cancelled",
                resume_automatically=False,
            )

            unrelated_review = research_jobs.create_research_job(
                topic="unrelated review pause",
                goal="stay paused",
                original_request="research this",
                depth="deep",
                priority="background",
            )

            unrelated_review = research_jobs.update_research_job(
                unrelated_review[
                    "id"
                ],
                status="paused",
                checkpoint={
                    "stage": "deep_research_review_required",
                    "next_stage": "research_review_required",
                    "user_ready": False,
                    "quality": cap_quality,
                    "review_reason": (
                        "The planner said more research was needed but produced no "
                        "new query that had not already been used."
                    ),
                },
                result={
                    "research_phase": "deep_research_review_required",
                    "user_ready": False,
                    "quality": cap_quality,
                },
                resume_automatically=False,
            )

            research_jobs.initialise_research_job_store()

            unrelated_after = research_jobs.get_research_job(
                unrelated_review[
                    "id"
                ]
            )

            assert unrelated_after is not None
            assert (
                unrelated_after[
                    "resume_automatically"
                ]
                is False
            )
            assert (
                unrelated_after[
                    "checkpoint"
                ][
                    "next_stage"
                ]
                == "research_review_required"
            )

            research_jobs.update_research_job(
                unrelated_review[
                    "id"
                ],
                status="cancelled",
                resume_automatically=False,
            )

            # --------------------------------------------------
            # 4. Long final reports receive enough structured-output budget for
            #    one sentence assessment per verification unit. This prevents the
            #    verifier JSON from being truncated at the old fixed 320 tokens.
            # --------------------------------------------------

            long_sentence_count = 40
            long_draft = "\n".join(
                "Grounded statement "
                + str(index)
                + "."
                for index in range(
                    1,
                    long_sentence_count + 1,
                )
            )

            long_client = RecordingLongVerifierClient(
                long_sentence_count
            )

            long_verification = verify_public_factual_draft(
                long_client,
                "qwen3.5:9b",
                "Research the test topic.",
                long_draft,
                json.dumps({
                    "freshness_required": False,
                    "sources": [],
                }),
            )

            assert list(
                long_verification
            ) == []
            assert len(
                long_verification.sentence_assessments
            ) == long_sentence_count
            assert len(
                long_client.calls
            ) == 1
            assert (
                long_client.calls[
                    0
                ][
                    "options"
                ][
                    "num_predict"
                ]
                > 320
            )

            # --------------------------------------------------
            # 5. A legacy synthesis-review pause caused only by invalid/truncated
            #    verifier structured output is retried once. Genuine content
            #    rejections remain review-required.
            # --------------------------------------------------

            verifier_retry_job = research_jobs.create_research_job(
                topic="legacy verifier protocol failure",
                goal="retry verifier protocol failure",
                original_request="research this deeply",
                depth="deep",
                priority="background",
            )

            verifier_retry_result = {
                "research_phase": "final_synthesis_review_required",
                "user_ready": False,
                "final_report_verified": False,
                "final_synthesis": {
                    "report_text": "Persisted grounded report draft.",
                    "uncertainties": [],
                    "verification": {
                        "supported": False,
                        "violations": [
                            "public factual-support verifier could not validate the draft"
                        ],
                    },
                },
            }

            verifier_retry_job = research_jobs.update_research_job(
                verifier_retry_job[
                    "id"
                ],
                status="paused",
                checkpoint={
                    "stage": "final_synthesis_review_required",
                    "next_stage": "synthesis_review_required",
                    "user_ready": False,
                    "review_reason": (
                        "public factual-support verifier could not validate the draft"
                    ),
                },
                result=verifier_retry_result,
                resume_automatically=False,
            )

            research_jobs.initialise_research_job_store()

            verifier_retry_after = research_jobs.get_research_job(
                verifier_retry_job[
                    "id"
                ]
            )

            assert verifier_retry_after is not None
            assert (
                verifier_retry_after[
                    "resume_automatically"
                ]
                is True
            )
            assert (
                verifier_retry_after[
                    "checkpoint"
                ][
                    "next_stage"
                ]
                == "final_synthesis_verification"
            )
            assert (
                verifier_retry_after[
                    "checkpoint"
                ][
                    "verifier_protocol_retry_count"
                ]
                == 1
            )
            assert (
                verifier_retry_after[
                    "result"
                ][
                    "final_synthesis"
                ][
                    "report_text"
                ]
                == "Persisted grounded report draft."
            )

            research_jobs.update_research_job(
                verifier_retry_job[
                    "id"
                ],
                status="cancelled",
                resume_automatically=False,
            )

            # --------------------------------------------------
            # 6. Supported synthesis: draft checkpoint -> verification -> durable
            #    completed report with user_ready=True.
            # --------------------------------------------------

            supported_job = _seed_final_synthesis_job(
                topic="supported final synthesis"
            )

            fake_synthesis = FakeSynthesis()
            supported_verifier = FakeVerifier(
                supported=True
            )

            draft_stage = run_one_research_job(
                worker_id="synthesis-worker",
                synthesis_fn=fake_synthesis,
                synthesis_verifier_fn=(
                    supported_verifier
                ),
            )

            assert draft_stage is not None
            assert (
                draft_stage[
                    "id"
                ]
                == supported_job[
                    "id"
                ]
            )
            assert (
                draft_stage[
                    "status"
                ]
                == "paused"
            )
            assert (
                draft_stage[
                    "resume_automatically"
                ]
                is True
            )
            assert (
                draft_stage[
                    "checkpoint"
                ][
                    "stage"
                ]
                == "final_synthesis_draft_complete"
            )
            assert (
                draft_stage[
                    "checkpoint"
                ][
                    "next_stage"
                ]
                == "final_synthesis_verification"
            )
            assert (
                draft_stage[
                    "result"
                ][
                    "user_ready"
                ]
                is False
            )
            assert (
                draft_stage[
                    "result"
                ][
                    "final_synthesis"
                ][
                    "report_text"
                ]
            )
            assert (
                "final_report_text"
                not in draft_stage[
                    "result"
                ]
            )
            assert fake_synthesis.calls == 1
            assert supported_verifier.calls == 0

            verified_stage = run_one_research_job(
                worker_id="verification-worker",
                synthesis_fn=fake_synthesis,
                synthesis_verifier_fn=(
                    supported_verifier
                ),
            )

            assert verified_stage is not None
            assert (
                verified_stage[
                    "id"
                ]
                == supported_job[
                    "id"
                ]
            )
            assert (
                verified_stage[
                    "status"
                ]
                == "completed"
            )
            assert (
                verified_stage[
                    "checkpoint"
                ][
                    "stage"
                ]
                == "final_synthesis_complete"
            )
            assert (
                verified_stage[
                    "checkpoint"
                ][
                    "next_stage"
                ]
                == "delivery"
            )
            assert (
                verified_stage[
                    "result"
                ][
                    "user_ready"
                ]
                is True
            )
            assert (
                verified_stage[
                    "result"
                ][
                    "final_report_verified"
                ]
                is True
            )
            assert (
                verified_stage[
                    "result"
                ][
                    "final_report"
                ][
                    "verified"
                ]
                is True
            )
            assert (
                verified_stage[
                    "result"
                ][
                    "final_report_text"
                ]
                == verified_stage[
                    "result"
                ][
                    "final_synthesis"
                ][
                    "report_text"
                ]
            )
            assert fake_synthesis.calls == 1
            assert supported_verifier.calls == 1

            # --------------------------------------------------
            # 7. Unsupported synthesis fails closed: the draft remains durable,
            #    but the job pauses for review and never becomes user-ready.
            # --------------------------------------------------

            review_job = _seed_final_synthesis_job(
                topic="unsupported final synthesis"
            )

            review_synthesis = FakeSynthesis()
            rejecting_verifier = FakeVerifier(
                supported=False
            )

            review_draft = run_one_research_job(
                worker_id="review-draft-worker",
                synthesis_fn=review_synthesis,
                synthesis_verifier_fn=(
                    rejecting_verifier
                ),
            )

            assert review_draft is not None
            assert (
                review_draft[
                    "checkpoint"
                ][
                    "next_stage"
                ]
                == "final_synthesis_verification"
            )

            review_stage = run_one_research_job(
                worker_id="review-verifier-worker",
                synthesis_fn=review_synthesis,
                synthesis_verifier_fn=(
                    rejecting_verifier
                ),
            )

            assert review_stage is not None
            assert (
                review_stage[
                    "id"
                ]
                == review_job[
                    "id"
                ]
            )
            assert (
                review_stage[
                    "status"
                ]
                == "paused"
            )
            assert (
                review_stage[
                    "resume_automatically"
                ]
                is False
            )
            assert (
                review_stage[
                    "checkpoint"
                ][
                    "stage"
                ]
                == "final_synthesis_review_required"
            )
            assert (
                review_stage[
                    "checkpoint"
                ][
                    "next_stage"
                ]
                == "synthesis_review_required"
            )
            assert (
                review_stage[
                    "result"
                ][
                    "user_ready"
                ]
                is False
            )
            assert (
                review_stage[
                    "result"
                ][
                    "final_report_verified"
                ]
                is False
            )
            assert (
                "final_report_text"
                not in review_stage[
                    "result"
                ]
            )

            # Windows-safe SQLite lifecycle remains intact.
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

    print(
        "Mairon Phase 11.5.4 grounded final synthesis tests: PASS"
    )


if __name__ == "__main__":
    run()
