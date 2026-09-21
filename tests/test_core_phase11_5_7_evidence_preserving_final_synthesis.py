import json
import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


import research.research_jobs as research_jobs
from research.final_synthesis import (
    MAX_FINAL_SYNTHESIS_PACKET_CHARACTERS,
    build_final_synthesis_evidence,
)
from research.research_worker import run_one_research_job


def _source(
    name,
    host,
    tier,
    *,
    quality_eligible=True,
):
    return {
        "title": name,
        "url": f"https://{host}/{name.lower().replace(' ', '-')}",
        "source_host": host,
        "source_quality": "general_web",
        "authority_tier": tier,
        "quality_eligible": quality_eligible,
        "published_date": "2026-09-20",
        "read_success": True,
        "accepted_as_evidence": True,
        "relevance_status": "accepted",
    }


def _packet(query, sources, *, body_size=9000):
    packet_sources = []

    for index, source in enumerate(sources, start=1):
        body = (
            f"Evidence for {source['title']}. "
            * max(1, body_size // max(1, len(source["title"]) + 15))
        )

        packet_sources.append({
            "source_id": f"S{index}",
            "title": source["title"],
            "url": source["url"],
            "source_host": source["source_host"],
            "source_quality": source["source_quality"],
            "authority_tier": source["authority_tier"],
            "quality_eligible": source["quality_eligible"],
            "published_date": source["published_date"],
            "search_snippet": f"Snippet for {source['title']}",
            "content_excerpt": body,
        })

    payload = {
        "research_kind": "public_factual",
        "research_query": query,
        "freshness_required": True,
        "forecast_requested": False,
        "sources": packet_sources,
    }

    return {
        "query": query,
        "packet": (
            "CORE PUBLIC FACTUAL EVIDENCE PACKET:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        ),
    }


def _seed_verification_job(topic, draft):
    job = research_jobs.create_research_job(
        topic=topic,
        goal=f"Research {topic} carefully.",
        original_request=f"Research {topic} in the background.",
        depth="deep",
        priority="background",
    )

    source = _source(
        "Official Source",
        "example.com",
        "primary_official",
    )

    result = {
        "research_phase": "final_synthesis_draft_complete",
        "user_ready": False,
        "source_index": [source],
        "rounds": [{
            "round": 1,
            "query": topic,
            "stage": "initial_public_evidence",
        }],
        "evidence_packets": [
            _packet(topic, [source], body_size=1200)
        ],
        "quality": {
            "minimum_floor_met": True,
            "source_count": 1,
            "unique_host_count": 1,
        },
        "final_synthesis": {
            "report_text": draft,
            "generated_at": "2026-09-21T00:00:00+00:00",
            "model": "fake-synthesis",
            "uncertainties": [],
            "source_urls": [source["url"]],
        },
        "final_report_verified": False,
    }

    checkpoint = {
        "stage": "final_synthesis_draft_complete",
        "next_stage": "final_synthesis_verification",
        "user_ready": False,
    }

    return research_jobs.update_research_job(
        job["id"],
        status="paused",
        checkpoint=checkpoint,
        result=result,
        resume_automatically=True,
    )


class RepairingVerifier:
    def __init__(self):
        self.calls = 0

    def __call__(self, job, result, draft):
        self.calls += 1

        if self.calls == 1:
            return {
                "supported": False,
                "violations": [
                    "unsupported public factual claim: unsupported second sentence"
                ],
                "accepted_sentences": ["Supported sentence one."],
                "sentence_assessments": [
                    {"index": 1, "supported": True},
                    {"index": 2, "supported": False},
                ],
                "model": "fake-verifier",
            }

        assert draft == "Supported sentence one."
        return {
            "supported": True,
            "violations": [],
            "accepted_sentences": ["Supported sentence one."],
            "sentence_assessments": [
                {"index": 1, "supported": True},
            ],
            "model": "fake-verifier",
        }


class AlwaysRejectingVerifier:
    def __init__(self):
        self.calls = 0

    def __call__(self, job, result, draft):
        self.calls += 1
        sentence_count = 1 if draft == "Supported sentence one." else 2
        return {
            "supported": False,
            "violations": [
                "unsupported public factual claim: still unsupported"
            ],
            "accepted_sentences": [],
            "sentence_assessments": [
                {"index": index, "supported": False}
                for index in range(1, sentence_count + 1)
            ],
            "model": "fake-verifier",
        }


class RepairThenProtocolFailureVerifier:
    """
    Reproduce the live 11.5.7 edge case: the original draft receives enough
    grounded feedback to allow one repair, but the repaired draft's verifier
    response is a protocol/structured-output failure. That second failure must
    stay paused forever; the legacy 11.5.4 protocol retry migration must not
    resurrect it.
    """

    def __init__(self):
        self.calls = 0

    def __call__(self, job, result, draft):
        self.calls += 1

        if self.calls == 1:
            return {
                "supported": False,
                "violations": [
                    "unsupported public factual claim: unsupported second sentence"
                ],
                "accepted_sentences": ["Supported sentence one."],
                "sentence_assessments": [
                    {"index": 1, "supported": True},
                    {"index": 2, "supported": False},
                ],
                "model": "fake-verifier",
            }

        return {
            "supported": False,
            "violations": [
                "public factual-support verifier could not validate the draft"
            ],
            "accepted_sentences": [],
            "sentence_assessments": [],
            "model": "fake-verifier",
        }


class IncompleteVerifier:
    def __call__(self, job, result, draft):
        return {
            "supported": False,
            "violations": [
                "unsupported public factual claim: incomplete feedback"
            ],
            "accepted_sentences": [],
            "sentence_assessments": [
                {"index": 1, "supported": False},
            ],
            "model": "fake-verifier",
        }


class FakeRepair:
    def __init__(self):
        self.calls = 0

    def __call__(self, job, result, draft, verification):
        self.calls += 1
        assert verification["supported"] is False
        assert verification["sentence_assessments"]
        return {
            "success": True,
            "report_text": "Supported sentence one.",
            "uncertainties": [
                "The unsupported second sentence was omitted."
            ],
            "source_urls": [],
            "model": "fake-repair",
        }


def run():
    old_db = os.environ.get("MAIRON_RESEARCH_JOB_DB")
    old_idle = os.environ.get("MAIRON_RESEARCH_IDLE_GRACE_SECONDS")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "research_jobs.sqlite3"
            os.environ["MAIRON_RESEARCH_JOB_DB"] = str(db_path)
            os.environ["MAIRON_RESEARCH_IDLE_GRACE_SECONDS"] = "0"

            # --------------------------------------------------
            # 1. Final synthesis evidence preserves every round and prioritises
            #    official/independent sources inside a hard character budget.
            # --------------------------------------------------

            official = _source(
                "Garmin Official Forerunner",
                "garmin.com",
                "primary_official",
            )
            weak_1 = _source(
                "Round One Video",
                "youtube.com",
                "weak_community_or_social",
                quality_eligible=False,
            )
            independent_2 = _source(
                "Independent Review Two",
                "techreview.example",
                "independent_editorial",
            )
            weak_2 = _source(
                "Retail Listing",
                "shop.example",
                "secondary_retailer_or_marketplace",
                quality_eligible=False,
            )
            independent_3 = _source(
                "Independent Review Three",
                "editorial3.example",
                "independent_editorial",
            )
            weak_3 = _source(
                "Community Thread",
                "reddit.com",
                "weak_community_or_social",
                quality_eligible=False,
            )
            independent_4 = _source(
                "Independent Review Four",
                "editorial4.example",
                "independent_editorial",
            )
            weak_4 = _source(
                "Marketplace Listing",
                "market.example",
                "secondary_retailer_or_marketplace",
                quality_eligible=False,
            )

            source_index = [
                official,
                weak_1,
                independent_2,
                weak_2,
                independent_3,
                weak_3,
                independent_4,
                weak_4,
            ]

            evidence_result = {
                "source_index": source_index,
                "evidence_packets": [
                    _packet("round one official lineup", [official, weak_1]),
                    _packet("round two independent", [independent_2, weak_2]),
                    _packet("round three comparison", [independent_3, weak_3]),
                    _packet("round four availability", [independent_4, weak_4]),
                ],
                "quality": {
                    "minimum_floor_met": True,
                    "source_count": 4,
                    "primary_source_count": 1,
                    "independent_source_count": 3,
                },
                "planner_history": [{
                    "reason": "THIS MUST NOT BECOME EVIDENCE",
                }],
            }

            evidence_job = {
                "topic": "the current Garmin Forerunner smartwatch models",
                "goal": "Research the current Garmin Forerunner smartwatch models.",
                "original_request": "Research the current Garmin Forerunner smartwatch models in the background.",
                "depth": "deep",
                "metadata": {},
            }

            evidence = build_final_synthesis_evidence(
                evidence_job,
                evidence_result,
            )

            selection = evidence["evidence_selection"]
            assert selection["raw_packet_count"] == 4
            assert selection["represented_packet_count"] == 4
            assert selection["selected_primary_count"] >= 1
            assert selection["selected_independent_count"] >= 3
            assert selection["packet_characters"] <= MAX_FINAL_SYNTHESIS_PACKET_CHARACTERS
            assert selection["strategy"] == "round_coverage_then_authority"
            assert evidence["request_shape"] == "catalogue_lookup"

            evidence_text = json.dumps(evidence, ensure_ascii=False)
            assert "Garmin Official Forerunner" in evidence_text
            assert "Independent Review Four" in evidence_text
            assert "THIS MUST NOT BECOME EVIDENCE" not in evidence_text
            assert "planner_history" not in evidence_text

            # --------------------------------------------------
            # 2. Upgrade migration: an existing 11.5.6 verifier rejection with
            #    a complete sentence map becomes exactly-one repair work.
            # --------------------------------------------------

            migration_job = research_jobs.create_research_job(
                topic="existing rejected synthesis",
                goal="test migration",
                original_request="test migration",
                depth="deep",
                priority="background",
            )

            migration_job = research_jobs.update_research_job(
                migration_job["id"],
                status="paused",
                checkpoint={
                    "stage": "final_synthesis_review_required",
                    "next_stage": "synthesis_review_required",
                    "user_ready": False,
                    "review_reason": "unsupported public factual claim: unsupported second sentence",
                },
                result={
                    "research_phase": "final_synthesis_review_required",
                    "user_ready": False,
                    "final_report_verified": False,
                    "final_synthesis": {
                        "report_text": "Supported sentence one. Unsupported sentence two.",
                        "repair_attempt_count": 0,
                        "verification": {
                            "supported": False,
                            "violations": [
                                "unsupported public factual claim: unsupported second sentence"
                            ],
                            "sentence_assessments": [
                                {"index": 1, "supported": True},
                                {"index": 2, "supported": False},
                            ],
                        },
                    },
                },
                resume_automatically=False,
            )

            research_jobs.initialise_research_job_store()
            migration_after = research_jobs.get_research_job(migration_job["id"])
            assert migration_after is not None
            assert migration_after["resume_automatically"] is True
            assert migration_after["checkpoint"]["next_stage"] == "final_synthesis_repair"
            assert migration_after["checkpoint"]["stage"] == "final_synthesis_repair_pending"
            assert migration_after["result"]["research_phase"] == "final_synthesis_repair_pending"

            research_jobs.update_research_job(
                migration_job["id"],
                status="cancelled",
                resume_automatically=False,
            )

            # --------------------------------------------------
            # 2b. Live-shape migration: a near-complete parsed verifier map
            #     (47/50) is safe for ONE repair when Core marks the missing
            #     tail units unsupported. It is still not eligible for final
            #     acceptance until the repaired report passes fresh verification.
            # --------------------------------------------------

            live_units = [
                f"Sentence {index}."
                for index in range(1, 51)
            ]
            live_report = " ".join(live_units)

            near_complete_job = research_jobs.create_research_job(
                topic="near complete migration",
                goal="test near complete migration",
                original_request="test near complete migration",
                depth="deep",
                priority="background",
            )

            near_complete_job = research_jobs.update_research_job(
                near_complete_job["id"],
                status="paused",
                checkpoint={
                    "stage": "final_synthesis_review_required",
                    "next_stage": "synthesis_review_required",
                    "user_ready": False,
                    "review_reason": (
                        "unsupported public factual claim: sentence three"
                    ),
                },
                result={
                    "research_phase": "final_synthesis_review_required",
                    "user_ready": False,
                    "final_report_verified": False,
                    "final_synthesis": {
                        "report_text": live_report,
                        "repair_attempt_count": 0,
                        "verification": {
                            "supported": False,
                            "violations": [
                                "unsupported public factual claim: sentence three"
                            ],
                            "sentence_assessments": [
                                {
                                    "index": index,
                                    "supported": index != 3,
                                }
                                for index in range(1, 48)
                            ],
                        },
                    },
                },
                resume_automatically=False,
            )

            research_jobs.initialise_research_job_store()
            near_complete_after = research_jobs.get_research_job(
                near_complete_job["id"]
            )
            assert near_complete_after is not None
            assert near_complete_after["resume_automatically"] is True
            assert (
                near_complete_after["checkpoint"]["next_stage"]
                == "final_synthesis_repair"
            )

            migrated_verification = (
                near_complete_after["result"]
                ["final_synthesis"]
                ["verification"]
            )
            assert (
                migrated_verification["repair_feedback_completed_by_core"]
                is True
            )
            assert migrated_verification["repair_feedback_missing_indexes"] == [
                48,
                49,
                50,
            ]
            assert len(
                migrated_verification["sentence_assessments"]
            ) == 50
            assert all(
                item["supported"] is False
                for item in migrated_verification["sentence_assessments"]
                if item["index"] in {48, 49, 50}
            )

            research_jobs.update_research_job(
                near_complete_job["id"],
                status="cancelled",
                resume_automatically=False,
            )

            # --------------------------------------------------
            # 3. A genuine complete verifier rejection queues one durable repair,
            #    verifies the repaired draft on the next pass, then completes.
            # --------------------------------------------------

            repaired_job = _seed_verification_job(
                "repair succeeds",
                "Supported sentence one. Unsupported sentence two.",
            )
            verifier = RepairingVerifier()
            repair = FakeRepair()

            rejected = run_one_research_job(
                worker_id="repair-verify-1",
                synthesis_verifier_fn=verifier,
                synthesis_repair_fn=repair,
            )

            assert rejected is not None
            assert rejected["id"] == repaired_job["id"]
            assert rejected["status"] == "paused"
            assert rejected["resume_automatically"] is True
            assert rejected["checkpoint"]["next_stage"] == "final_synthesis_repair"
            assert rejected["result"]["research_phase"] == "final_synthesis_repair_pending"
            assert repair.calls == 0

            repaired = run_one_research_job(
                worker_id="repair-generation",
                synthesis_verifier_fn=verifier,
                synthesis_repair_fn=repair,
            )

            assert repaired is not None
            assert repaired["status"] == "paused"
            assert repaired["checkpoint"]["next_stage"] == "final_synthesis_verification"
            assert repaired["result"]["final_synthesis"]["repair_attempt_count"] == 1
            assert repaired["result"]["final_synthesis"]["report_text"] == "Supported sentence one."
            assert len(repaired["result"]["final_synthesis"]["verification_history"]) == 1
            assert repair.calls == 1

            completed = run_one_research_job(
                worker_id="repair-verify-2",
                synthesis_verifier_fn=verifier,
                synthesis_repair_fn=repair,
            )

            assert completed is not None
            assert completed["status"] == "completed"
            assert completed["checkpoint"]["next_stage"] == "delivery"
            assert completed["result"]["final_report_verified"] is True
            assert completed["result"]["final_report_text"] == "Supported sentence one."
            assert verifier.calls == 2
            assert repair.calls == 1

            # --------------------------------------------------
            # 4. A repaired draft that still fails verification pauses for review;
            #    Core never loops into a second repair.
            # --------------------------------------------------

            second_job = _seed_verification_job(
                "repair still rejected",
                "Supported sentence one. Unsupported sentence two.",
            )
            rejecting = AlwaysRejectingVerifier()
            second_repair = FakeRepair()

            queued = run_one_research_job(
                worker_id="reject-verify-1",
                synthesis_verifier_fn=rejecting,
                synthesis_repair_fn=second_repair,
            )
            assert queued["checkpoint"]["next_stage"] == "final_synthesis_repair"

            repaired_again = run_one_research_job(
                worker_id="reject-repair",
                synthesis_verifier_fn=rejecting,
                synthesis_repair_fn=second_repair,
            )
            assert repaired_again["checkpoint"]["next_stage"] == "final_synthesis_verification"

            review = run_one_research_job(
                worker_id="reject-verify-2",
                synthesis_verifier_fn=rejecting,
                synthesis_repair_fn=second_repair,
            )

            assert review["status"] == "paused"
            assert review["resume_automatically"] is False
            assert review["checkpoint"]["next_stage"] == "synthesis_review_required"
            assert review["result"]["final_synthesis"]["repair_attempt_count"] == 1
            assert second_repair.calls == 1
            assert rejecting.calls == 2

            # --------------------------------------------------
            # 4b. Live edge case: if the ONE repaired draft then hits a verifier
            #     protocol failure, the old 11.5.4 protocol-retry migration must
            #     NOT resurrect it for a third verification pass.
            # --------------------------------------------------

            protocol_job = _seed_verification_job(
                "repair then protocol failure",
                "Supported sentence one. Unsupported sentence two.",
            )
            protocol_verifier = RepairThenProtocolFailureVerifier()
            protocol_repair = FakeRepair()

            protocol_queued = run_one_research_job(
                worker_id="protocol-verify-1",
                synthesis_verifier_fn=protocol_verifier,
                synthesis_repair_fn=protocol_repair,
            )
            assert protocol_queued["checkpoint"]["next_stage"] == "final_synthesis_repair"

            protocol_repaired = run_one_research_job(
                worker_id="protocol-repair",
                synthesis_verifier_fn=protocol_verifier,
                synthesis_repair_fn=protocol_repair,
            )
            assert (
                protocol_repaired["checkpoint"]["next_stage"]
                == "final_synthesis_verification"
            )
            assert (
                protocol_repaired["result"]["final_synthesis"]["repair_attempt_count"]
                == 1
            )

            protocol_review = run_one_research_job(
                worker_id="protocol-verify-2",
                synthesis_verifier_fn=protocol_verifier,
                synthesis_repair_fn=protocol_repair,
            )
            assert protocol_review["status"] == "paused"
            assert protocol_review["resume_automatically"] is False
            assert (
                protocol_review["checkpoint"]["next_stage"]
                == "synthesis_review_required"
            )
            assert (
                protocol_review["checkpoint"]["review_reason"]
                == "public factual-support verifier could not validate the draft"
            )
            assert (
                protocol_review["result"]["final_synthesis"]["repair_attempt_count"]
                == 1
            )
            assert protocol_verifier.calls == 2
            assert protocol_repair.calls == 1

            # Store initialisation runs repeatedly in the real worker polling
            # path. It must not reinterpret the repaired draft as an old 11.5.4
            # protocol failure and set resume_automatically back to True.
            research_jobs.initialise_research_job_store()
            protocol_after_initialise = research_jobs.get_research_job(
                protocol_job["id"]
            )
            assert protocol_after_initialise is not None
            assert protocol_after_initialise["status"] == "paused"
            assert protocol_after_initialise["resume_automatically"] is False
            assert (
                protocol_after_initialise["checkpoint"]["stage"]
                == "final_synthesis_review_required"
            )
            assert (
                protocol_after_initialise["checkpoint"]["next_stage"]
                == "synthesis_review_required"
            )

            research_jobs.update_research_job(
                protocol_job["id"],
                status="cancelled",
                resume_automatically=False,
            )

            # --------------------------------------------------
            # 5. Sparse verifier feedback remains fail-closed and does NOT repair.
            #    Near-complete maps may be pessimistically completed by Core, but
            #    genuinely sparse/protocol-like feedback still cannot trigger repair.
            # --------------------------------------------------

            incomplete_job = _seed_verification_job(
                "incomplete verifier feedback",
                "Sentence one. Sentence two.",
            )
            incomplete_repair = FakeRepair()

            incomplete = run_one_research_job(
                worker_id="incomplete-verifier",
                synthesis_verifier_fn=IncompleteVerifier(),
                synthesis_repair_fn=incomplete_repair,
            )

            assert incomplete["id"] == incomplete_job["id"]
            assert incomplete["status"] == "paused"
            assert incomplete["resume_automatically"] is False
            assert incomplete["checkpoint"]["next_stage"] == "synthesis_review_required"
            assert incomplete_repair.calls == 0

            db_path.unlink()

    finally:
        if old_db is None:
            os.environ.pop("MAIRON_RESEARCH_JOB_DB", None)
        else:
            os.environ["MAIRON_RESEARCH_JOB_DB"] = old_db

        if old_idle is None:
            os.environ.pop("MAIRON_RESEARCH_IDLE_GRACE_SECONDS", None)
        else:
            os.environ["MAIRON_RESEARCH_IDLE_GRACE_SECONDS"] = old_idle

    print("Mairon Phase 11.5.7 evidence-preserving final synthesis tests: PASS")


if __name__ == "__main__":
    run()
