from __future__ import annotations

import inspect
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.conversational_research import (
    extract_explicit_background_research_request,
)
from research.deep_research import (
    filter_unused_research_queries,
    plan_next_deep_research_round,
    research_collection_decision,
    research_quality_snapshot,
)
from research.final_synthesis import (
    generate_grounded_final_synthesis,
    repair_grounded_final_synthesis,
    verify_grounded_final_synthesis,
)
from research.public_factual_research import (
    build_internal_public_factual_packet,
    filter_research_result_for_relevance,
    gather_public_factual_research,
)
from research.research_jobs import (
    claim_next_research_job,
    update_claimed_research_job,
)


_WORKER_LOCK = threading.Lock()
_WORKER_THREAD: Optional[threading.Thread] = None
_WORKER_STOP_EVENT = threading.Event()

_INTERACTIVE_STATE_LOCK = threading.Lock()
_ACTIVE_INTERACTIVE_TURNS = 0
_LAST_INTERACTIVE_ACTIVITY = time.monotonic()


def _normalise_space(
    value: Any,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ).strip(),
    )


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _env_float(
    name: str,
    default: float,
    minimum: float,
) -> float:
    try:
        value = float(
            os.getenv(
                name,
                str(
                    default
                ),
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        value = default

    return max(
        minimum,
        value,
    )


def background_research_enabled() -> bool:
    value = str(
        os.getenv(
            "MAIRON_BACKGROUND_RESEARCH_ENABLED",
            "1",
        )
        or ""
    ).strip().lower()

    return value not in {
        "0",
        "false",
        "no",
        "off",
    }


def note_interactive_activity() -> None:
    """
    Refresh the last interactive-activity timestamp.

    This remains available for narrow callers/tests, but the primary foreground
    boundary is begin_interactive_turn()/end_interactive_turn(). A timestamp by
    itself is not enough because a legitimate foreground request can take longer
    than the idle grace period.
    """

    global _LAST_INTERACTIVE_ACTIVITY

    with _INTERACTIVE_STATE_LOCK:
        _LAST_INTERACTIVE_ACTIVITY = (
            time.monotonic()
        )


def begin_interactive_turn() -> None:
    """
    Mark one foreground Mairon turn as actively in progress.

    Background research must not begin another stage while this count is
    non-zero, even when the foreground turn itself takes longer than the idle
    grace period.
    """

    global _ACTIVE_INTERACTIVE_TURNS
    global _LAST_INTERACTIVE_ACTIVITY

    with _INTERACTIVE_STATE_LOCK:
        _ACTIVE_INTERACTIVE_TURNS += 1
        _LAST_INTERACTIVE_ACTIVITY = (
            time.monotonic()
        )


def end_interactive_turn() -> None:
    """
    Release one foreground turn and restart the post-response idle grace period.
    """

    global _ACTIVE_INTERACTIVE_TURNS
    global _LAST_INTERACTIVE_ACTIVITY

    with _INTERACTIVE_STATE_LOCK:
        _ACTIVE_INTERACTIVE_TURNS = max(
            0,
            _ACTIVE_INTERACTIVE_TURNS - 1,
        )
        _LAST_INTERACTIVE_ACTIVITY = (
            time.monotonic()
        )


def active_interactive_turn_count() -> int:
    with _INTERACTIVE_STATE_LOCK:
        return int(
            _ACTIVE_INTERACTIVE_TURNS
        )


def seconds_since_interactive_activity() -> float:
    with _INTERACTIVE_STATE_LOCK:
        last_activity = (
            _LAST_INTERACTIVE_ACTIVITY
        )

    return max(
        0.0,
        time.monotonic()
        - last_activity,
    )


def background_research_can_run(
    *,
    idle_grace_seconds: Optional[float] = None,
) -> bool:
    grace = (
        _env_float(
            "MAIRON_RESEARCH_IDLE_GRACE_SECONDS",
            8.0,
            0.0,
        )
        if idle_grace_seconds is None
        else max(
            0.0,
            float(
                idle_grace_seconds
            ),
        )
    )

    with _INTERACTIVE_STATE_LOCK:
        foreground_active = (
            _ACTIVE_INTERACTIVE_TURNS > 0
        )

    if foreground_active:
        return False

    return (
        seconds_since_interactive_activity()
        >= grace
    )


def canonical_research_topic(
    job: dict,
) -> str:
    """
    Recover the clean research subject for durable jobs created before the
    execution-suffix cleanup existed.

    The original request remains available, so an old topic such as
    "Garmin smartwatch models in the background" can be rendered/searched as
    "Garmin smartwatch models" without rewriting historical user text.
    """

    original_request = _normalise_space(
        job.get(
            "original_request"
        )
    )

    if original_request:
        parsed = (
            extract_explicit_background_research_request(
                original_request
            )
        )

        if isinstance(
            parsed,
            dict,
        ):
            parsed_topic = _normalise_space(
                parsed.get(
                    "topic"
                )
            )

            if parsed_topic:
                return parsed_topic[
                    :500
                ]

    return _normalise_space(
        job.get(
            "topic"
        )
    )[
        :500
    ]


def build_worker_research_query(
    job: dict,
) -> str:
    metadata = (
        job.get(
            "metadata"
        )
        or {}
    )

    if (
        metadata.get(
            "research_kind"
        )
        == "pairwise_opinion"
    ):
        left = _normalise_space(
            metadata.get(
                "left"
            )
        )

        right = _normalise_space(
            metadata.get(
                "right"
            )
        )

        if left and right:
            return (
                left
                + " vs "
                + right
            )[:500]

    topic = canonical_research_topic(
        job
    )

    if topic:
        return topic[:500]

    goal = _normalise_space(
        job.get(
            "goal"
        )
    )

    return goal[:500]


def _max_reads_for_job(
    job: dict,
) -> int:
    depth = _normalise_space(
        job.get(
            "depth"
        )
    ).lower()

    if depth == "quick":
        return 2

    if depth == "normal":
        return 3

    return 4


def _source_index_from_research_result(
    research_result: dict,
) -> list[dict]:
    """Return only readable sources accepted as evidence by Core relevance gates."""

    sources = []

    for source in (
        research_result.get(
            "sources"
        )
        or []
    ):
        if not isinstance(
            source,
            dict,
        ):
            continue

        if not source.get(
            "read_success"
        ):
            continue

        if source.get(
            "accepted_as_evidence"
        ) is False:
            continue

        if _normalise_space(
            source.get(
                "relevance_status"
            )
        ).lower() == "rejected":
            continue

        sources.append({
            "title": source.get(
                "title"
            ),
            "url": source.get(
                "url"
            ),
            "source_host": source.get(
                "source_host"
            ),
            "source_quality": source.get(
                "source_quality"
            ),
            "authority_tier": source.get(
                "authority_tier"
            ) or "legacy_curated",
            "quality_eligible": (
                source.get(
                    "quality_eligible"
                )
                if source.get(
                    "quality_eligible"
                ) is not None
                else True
            ),
            "authority_reason": source.get(
                "authority_reason"
            ),
            "authority_anchor_matches": list(
                source.get(
                    "authority_anchor_matches"
                )
                or []
            ),
            "published_date": source.get(
                "published_date"
            ),
            "read_success": True,
            "accepted_as_evidence": True,
            "relevance_status": "accepted",
            "identity_anchors": list(
                source.get(
                    "identity_anchors"
                )
                or []
            ),
            "matched_identity_anchors": list(
                source.get(
                    "matched_identity_anchors"
                )
                or []
            ),
        })

    return sources


def _unique_source_index(
    *source_lists: list[dict],
) -> list[dict]:
    merged = []
    seen = set()

    for sources in source_lists:
        for source in (
            sources
            or []
        ):
            if not isinstance(
                source,
                dict,
            ):
                continue

            url = _normalise_space(
                source.get(
                    "url"
                )
            )

            fallback_key = (
                _normalise_space(
                    source.get(
                        "title"
                    )
                ).lower(),
                _normalise_space(
                    source.get(
                        "source_host"
                    )
                ).lower(),
            )

            key = (
                "url",
                url.lower(),
            ) if url else (
                "fallback",
                *fallback_key,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            merged.append(
                dict(
                    source
                )
            )

    return merged


def _unique_rejected_sources(
    *source_lists: list[dict],
) -> list[dict]:
    merged = []
    seen = set()

    for sources in source_lists:
        for source in sources or []:
            if not isinstance(source, dict):
                continue

            url = _normalise_space(
                source.get("url")
            ).lower()
            stage = _normalise_space(
                source.get("stage")
            ).lower()
            reasons = tuple(
                _normalise_space(reason).lower()
                for reason in (source.get("reasons") or [])
                if _normalise_space(reason)
            )
            title = _normalise_space(
                source.get("title")
            ).lower()

            key = (url, stage, reasons, title)

            if key in seen:
                continue

            seen.add(key)
            merged.append(dict(source))

    return merged[-120:]


def _research_function_accepts_identity(
    research_fn: Callable,
) -> bool:
    try:
        signature = inspect.signature(
            research_fn
        )
    except (TypeError, ValueError):
        return False

    if "research_identity" in signature.parameters:
        return True

    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _call_research_function(
    *,
    research_fn: Callable,
    query: str,
    job: dict,
) -> dict:
    kwargs = {
        "max_reads": _max_reads_for_job(
            job
        ),
    }

    if _research_function_accepts_identity(
        research_fn
    ):
        kwargs[
            "research_identity"
        ] = canonical_research_topic(
            job
        )

    return research_fn(
        query,
        **kwargs,
    )


def _normalise_accumulated_result(
    job: dict,
) -> dict:
    """
    Upgrade a Phase 11.5.2 result in memory without throwing its evidence away.

    This lets the Garmin job Oliver already created continue directly into
    iterative research after the 11.5.3 code is installed.
    """

    current = dict(
        job.get(
            "result"
        )
        or {}
    )

    source_index = list(
        current.get(
            "source_index"
        )
        or []
    )

    rounds = list(
        current.get(
            "rounds"
        )
        or []
    )

    evidence_packets = list(
        current.get(
            "evidence_packets"
        )
        or []
    )

    rejected_sources = list(
        current.get(
            "rejected_sources"
        )
        or []
    )

    legacy_query = _normalise_space(
        current.get(
            "query"
        )
        or (
            job.get(
                "checkpoint"
            )
            or {}
        ).get(
            "query"
        )
    )

    if (
        not rounds
        and legacy_query
        and source_index
    ):
        rounds.append({
            "round": 1,
            "stage": "initial_public_evidence",
            "query": legacy_query,
            "started_at": (
                (
                    job.get(
                        "checkpoint"
                    )
                    or {}
                ).get(
                    "stage_started_at"
                )
            ),
            "finished_at": (
                (
                    job.get(
                        "checkpoint"
                    )
                    or {}
                ).get(
                    "stage_finished_at"
                )
            ),
            "readable_source_count": int(
                current.get(
                    "readable_source_count"
                )
                or len(
                    source_index
                )
            ),
            "new_source_count": len(
                source_index
            ),
            "source_urls": [
                source.get(
                    "url"
                )
                for source in source_index
                if isinstance(
                    source,
                    dict,
                )
                and source.get(
                    "url"
                )
            ],
        })

    legacy_packet = str(
        current.get(
            "evidence_packet"
        )
        or ""
    ).strip()

    if (
        legacy_packet
        and not evidence_packets
    ):
        evidence_packets.append({
            "query": legacy_query,
            "packet": legacy_packet,
        })

    return {
        **current,
        "research_phase": "deep_evidence_collection",
        "user_ready": False,
        "source_index": source_index,
        "rounds": rounds,
        "evidence_packets": evidence_packets,
        "rejected_sources": rejected_sources,
        "rejected_source_count": len(
            rejected_sources
        ),
        "planner_history": list(
            current.get(
                "planner_history"
            )
            or []
        ),
    }


def _append_research_pass(
    *,
    job: dict,
    accumulated: dict,
    query: str,
    research_result: dict,
    evidence_packet: str,
    stage: str,
    started_at: str,
) -> dict:
    new_sources = (
        _source_index_from_research_result(
            research_result
        )
    )

    old_sources = list(
        accumulated.get(
            "source_index"
        )
        or []
    )

    merged_sources = (
        _unique_source_index(
            old_sources,
            new_sources,
        )
    )

    new_source_count = (
        len(
            merged_sources
        )
        - len(
            _unique_source_index(
                old_sources
            )
        )
    )

    rejected_sources = _unique_rejected_sources(
        list(
            accumulated.get(
                "rejected_sources"
            )
            or []
        ),
        list(
            research_result.get(
                "rejected_sources"
            )
            or []
        ),
    )

    rounds = list(
        accumulated.get(
            "rounds"
        )
        or []
    )

    rounds.append({
        "round": len(
            rounds
        ) + 1,
        "stage": stage,
        "query": query,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "readable_source_count": int(
            research_result.get(
                "readable_source_count"
            )
            or 0
        ),
        "accepted_source_count": int(
            research_result.get(
                "accepted_source_count"
            )
            or research_result.get(
                "readable_source_count"
            )
            or 0
        ),
        "rejected_source_count": int(
            research_result.get(
                "rejected_source_count"
            )
            or 0
        ),
        "new_source_count": max(
            0,
            new_source_count,
        ),
        "source_urls": [
            source.get(
                "url"
            )
            for source in new_sources
            if isinstance(
                source,
                dict,
            )
            and source.get(
                "url"
            )
        ],
    })

    evidence_packets = list(
        accumulated.get(
            "evidence_packets"
        )
        or []
    )

    if str(
        evidence_packet
        or ""
    ).strip():
        evidence_packets.append({
            "query": query,
            "packet": str(
                evidence_packet
            ),
        })

    return {
        **accumulated,
        "research_phase": "deep_evidence_collection",
        "user_ready": False,
        "query": (
            accumulated.get(
                "query"
            )
            or query
        ),
        "source_index": merged_sources,
        "rounds": rounds,
        "evidence_packets": evidence_packets,
        "rejected_sources": rejected_sources,
        "rejected_source_count": len(
            rejected_sources
        ),
        "readable_source_count": len(
            [
                source
                for source in merged_sources
                if source.get(
                    "read_success"
                )
            ]
        ),
    }


def _run_public_research_pass(
    *,
    query: str,
    job: dict,
    research_fn: Callable,
    packet_builder: Callable,
) -> tuple[dict, str]:
    research_result = _call_research_function(
        research_fn=research_fn,
        query=query,
        job=job,
    )

    if not isinstance(
        research_result,
        dict,
    ):
        raise RuntimeError(
            "research function returned an invalid result"
        )

    research_result = filter_research_result_for_relevance(
        research_result,
        query=query,
        research_identity=canonical_research_topic(
            job
        ),
    )

    if not research_result.get(
        "success"
    ):
        failure_reason = _normalise_space(
            research_result.get(
                "failure_reason"
            )
        ) or (
            "The public research pass returned no readable evidence."
        )

        raise RuntimeError(
            failure_reason
        )

    evidence_packet = packet_builder(
        research_result
    )

    return (
        research_result,
        str(
            evidence_packet
            or ""
        ),
    )


def _pause_for_next_deep_stage(
    *,
    job: dict,
    worker_id: str,
    checkpoint: dict,
    result: dict,
) -> dict:
    return update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="paused",
        checkpoint=checkpoint,
        result=result,
        error=None,
        resume_automatically=True,
    )


def _handle_initial_research_stage(
    *,
    job: dict,
    worker_id: str,
    research_fn: Callable,
    packet_builder: Callable,
    respect_interactive_preemption: bool,
) -> dict:
    query = build_worker_research_query(
        job
    )

    started_at = _now_iso()

    print(
        "[Research] Initial evidence pass started: "
        + query
    )

    started_checkpoint = {
        **(
            job.get(
                "checkpoint"
            )
            or {}
        ),
        "stage": "initial_public_evidence",
        "stage_started_at": started_at,
        "query": query,
        "user_ready": False,
    }

    job = update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="running",
        checkpoint=started_checkpoint,
    )

    if (
        respect_interactive_preemption
        and not background_research_can_run()
    ):
        print(
            "[Research] Interactive activity detected; initial research deferred."
        )

        return _pause_for_next_deep_stage(
            job=job,
            worker_id=worker_id,
            checkpoint={
                **started_checkpoint,
                "stage": "initial_public_evidence_deferred",
                "next_stage": "initial_public_evidence",
                "user_ready": False,
            },
            result=_normalise_accumulated_result(
                job
            ),
        )

    research_result, evidence_packet = (
        _run_public_research_pass(
            query=query,
            job=job,
            research_fn=research_fn,
            packet_builder=packet_builder,
        )
    )

    source_index = (
        _source_index_from_research_result(
            research_result
        )
    )

    depth = _normalise_space(
        job.get(
            "depth"
        )
    ).lower()

    result = {
        "research_phase": (
            "initial_public_evidence"
            if depth == "quick"
            else "deep_evidence_collection"
        ),
        "user_ready": (
            depth == "quick"
        ),
        "query": (
            research_result.get(
                "query"
            )
            or query
        ),
        "readable_source_count": int(
            research_result.get(
                "readable_source_count"
            )
            or 0
        ),
        "accepted_source_count": int(
            research_result.get(
                "accepted_source_count"
            )
            or research_result.get(
                "readable_source_count"
            )
            or 0
        ),
        "rejected_source_count": int(
            research_result.get(
                "rejected_source_count"
            )
            or 0
        ),
        "rejected_sources": list(
            research_result.get(
                "rejected_sources"
            )
            or []
        )[-120:],
        "source_index": source_index,
        "rounds": [{
            "round": 1,
            "stage": "initial_public_evidence",
            "query": query,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "readable_source_count": int(
                research_result.get(
                    "readable_source_count"
                )
                or 0
            ),
            "accepted_source_count": int(
                research_result.get(
                    "accepted_source_count"
                )
                or research_result.get(
                    "readable_source_count"
                )
                or 0
            ),
            "rejected_source_count": int(
                research_result.get(
                    "rejected_source_count"
                )
                or 0
            ),
            "new_source_count": len(
                source_index
            ),
            "source_urls": [
                source.get(
                    "url"
                )
                for source in source_index
                if source.get(
                    "url"
                )
            ],
        }],
        "evidence_packet": evidence_packet,
        "evidence_packets": [{
            "query": query,
            "packet": evidence_packet,
        }],
        "planner_history": [],
    }

    print(
        "[Research] Initial evidence pass collected "
        + str(
            result[
                "readable_source_count"
            ]
        )
        + " relevant readable sources; rejected "
        + str(
            result.get(
                "rejected_source_count"
            )
            or 0
        )
        + " irrelevant/unusable candidates."
    )

    if depth == "quick":
        checkpoint = {
            **started_checkpoint,
            "stage": "initial_public_evidence_complete",
            "stage_finished_at": _now_iso(),
            "next_stage": "delivery",
            "user_ready": True,
            "readable_source_count": result[
                "readable_source_count"
            ],
        }

        print(
            "[Research] Quick research job completed."
        )

        return update_claimed_research_job(
            job[
                "id"
            ],
            worker_id=worker_id,
            status="completed",
            checkpoint=checkpoint,
            result=result,
            error=None,
        )

    checkpoint = {
        **started_checkpoint,
        "stage": "initial_public_evidence_complete",
        "stage_finished_at": _now_iso(),
        "next_stage": "iterative_deep_research",
        "user_ready": False,
        "readable_source_count": result[
            "readable_source_count"
        ],
        "pending_queries": [],
    }

    print(
        "[Research] Initial checkpoint saved; deep research will continue."
    )

    return _pause_for_next_deep_stage(
        job=job,
        worker_id=worker_id,
        checkpoint=checkpoint,
        result=result,
    )


def _handle_iterative_deep_stage(
    *,
    job: dict,
    worker_id: str,
    research_fn: Callable,
    packet_builder: Callable,
    planner_fn: Callable,
    respect_interactive_preemption: bool,
) -> dict:
    checkpoint = dict(
        job.get(
            "checkpoint"
        )
        or {}
    )

    accumulated = _normalise_accumulated_result(
        job
    )

    pending_queries = [
        _normalise_space(
            query
        )
        for query in (
            checkpoint.get(
                "pending_queries"
            )
            or []
        )
        if _normalise_space(
            query
        )
    ]

    if not pending_queries:
        print(
            "[Research] Planning next deep-research gaps for: "
            + _normalise_space(
                job.get(
                    "topic"
                )
            )
        )

        planner_job = dict(
            job
        )

        planner_job[
            "topic"
        ] = canonical_research_topic(
            job
        )

        plan = planner_fn(
            planner_job,
            accumulated,
        )

        if not isinstance(
            plan,
            dict,
        ):
            raise RuntimeError(
                "deep-research planner returned an invalid plan"
            )

        planner_history = list(
            accumulated.get(
                "planner_history"
            )
            or []
        )

        planner_history.append({
            "at": _now_iso(),
            "complete": bool(
                plan.get(
                    "complete"
                )
            ),
            "reason": _normalise_space(
                plan.get(
                    "reason"
                )
            ),
            "knowledge_gaps": list(
                plan.get(
                    "knowledge_gaps"
                )
                or []
            )[
                :8
            ],
            "search_queries": list(
                plan.get(
                    "search_queries"
                )
                or []
            )[
                :5
            ],
            "planner": plan.get(
                "planner"
            ),
        })

        accumulated[
            "planner_history"
        ] = planner_history

        decision = (
            research_collection_decision(
                job,
                accumulated,
                plan,
            )
        )

        if decision[
            "state"
        ] == "evidence_collection_complete":
            complete_checkpoint = {
                **checkpoint,
                "stage": "deep_evidence_collection_complete",
                "stage_finished_at": _now_iso(),
                "next_stage": "final_synthesis",
                "user_ready": False,
                "pending_queries": [],
                "quality": decision[
                    "quality"
                ],
                "completion_reason": decision[
                    "reason"
                ],
            }

            accumulated[
                "quality"
            ] = decision[
                "quality"
            ]

            accumulated[
                "research_phase"
            ] = "deep_evidence_collection_complete"

            print(
                "[Research] Evidence collection quality threshold reached; "
                "awaiting final synthesis."
            )

            return update_claimed_research_job(
                job[
                    "id"
                ],
                worker_id=worker_id,
                status="paused",
                checkpoint=complete_checkpoint,
                result=accumulated,
                error=None,
                resume_automatically=True,
            )

        if decision[
            "state"
        ] == "review_required":
            review_checkpoint = {
                **checkpoint,
                "stage": "deep_research_review_required",
                "stage_finished_at": _now_iso(),
                "next_stage": "research_review_required",
                "user_ready": False,
                "pending_queries": [],
                "quality": decision[
                    "quality"
                ],
                "review_reason": decision[
                    "reason"
                ],
            }

            accumulated[
                "quality"
            ] = decision[
                "quality"
            ]

            accumulated[
                "research_phase"
            ] = "deep_research_review_required"

            print(
                "[Research] Deep-research safety cap reached before confidence; "
                "job paused for review rather than bluffing completion."
            )

            return update_claimed_research_job(
                job[
                    "id"
                ],
                worker_id=worker_id,
                status="paused",
                checkpoint=review_checkpoint,
                result=accumulated,
                error=None,
                resume_automatically=False,
            )

        pending_queries = (
            filter_unused_research_queries(
                accumulated,
                list(
                    plan.get(
                        "search_queries"
                    )
                    or []
                ),
            )
        )

        if not pending_queries:
            no_query_checkpoint = {
                **checkpoint,
                "stage": "deep_research_review_required",
                "stage_finished_at": _now_iso(),
                "next_stage": "research_review_required",
                "user_ready": False,
                "pending_queries": [],
                "quality": research_quality_snapshot(
                    job,
                    accumulated,
                ),
                "review_reason": (
                    "The planner said more research was needed but produced no "
                    "new query that had not already been used."
                ),
            }

            print(
                "[Research] Planner found gaps but no unused query; paused for review."
            )

            return update_claimed_research_job(
                job[
                    "id"
                ],
                worker_id=worker_id,
                status="paused",
                checkpoint=no_query_checkpoint,
                result=accumulated,
                error=None,
                resume_automatically=False,
            )

        gaps = [
            _normalise_space(
                gap
            )
            for gap in (
                plan.get(
                    "knowledge_gaps"
                )
                or []
            )
            if _normalise_space(
                gap
            )
        ]

        if gaps:
            print(
                "[Research] Remaining gap: "
                + gaps[
                    0
                ][
                    :220
                ]
            )

        checkpoint = {
            **checkpoint,
            "stage": "iterative_deep_research",
            "next_stage": "iterative_deep_research",
            "user_ready": False,
            "pending_queries": pending_queries,
            "latest_knowledge_gaps": gaps[
                :8
            ],
            "latest_plan_reason": _normalise_space(
                plan.get(
                    "reason"
                )
            ),
        }

    if (
        respect_interactive_preemption
        and not background_research_can_run()
    ):
        print(
            "[Research] Interactive activity detected; deep research yielded."
        )

        return _pause_for_next_deep_stage(
            job=job,
            worker_id=worker_id,
            checkpoint=checkpoint,
            result=accumulated,
        )

    query = pending_queries[
        0
    ]

    remaining_queries = pending_queries[
        1:
    ]

    started_at = _now_iso()

    print(
        "[Research] Deep research query started: "
        + query
    )

    research_result, evidence_packet = (
        _run_public_research_pass(
            query=query,
            job=job,
            research_fn=research_fn,
            packet_builder=packet_builder,
        )
    )

    updated_result = _append_research_pass(
        job=job,
        accumulated=accumulated,
        query=query,
        research_result=research_result,
        evidence_packet=evidence_packet,
        stage="iterative_deep_research",
        started_at=started_at,
    )

    latest_round = (
        updated_result.get(
            "rounds"
        )
        or []
    )[
        -1
    ]

    quality = research_quality_snapshot(
        job,
        updated_result,
    )

    updated_result[
        "quality"
    ] = quality

    if quality.get(
        "maximum_rounds_reached"
    ):
        # The maximum round count is a hard cap, not merely a signal checked at
        # the next planner boundary. Drop any still-pending queries so the next
        # bounded worker pass resolves the cap immediately instead of overshooting
        # it by executing the rest of a previously planned batch.
        remaining_queries = []

        print(
            "[Research] Deep-research round cap reached; "
            "discarding remaining planned queries before completion review."
        )

    updated_checkpoint = {
        **checkpoint,
        "stage": "iterative_deep_research_checkpoint",
        "stage_finished_at": _now_iso(),
        "next_stage": "iterative_deep_research",
        "user_ready": False,
        "pending_queries": remaining_queries,
        "last_query": query,
        "last_query_new_source_count": int(
            latest_round.get(
                "new_source_count"
            )
            or 0
        ),
        "quality": quality,
    }

    print(
        "[Research] Deep query stored "
        + str(
            latest_round.get(
                "new_source_count"
            )
            or 0
        )
        + " new relevant sources; "
        + str(
            quality.get(
                "source_count"
            )
            or 0
        )
        + " quality-counting sources across "
        + str(
            quality.get(
                "unique_host_count"
            )
            or 0
        )
        + " hosts ("
        + str(
            quality.get(
                "primary_source_count"
            )
            or 0
        )
        + " primary, "
        + str(
            quality.get(
                "independent_source_count"
            )
            or 0
        )
        + " independent)."
    )

    return _pause_for_next_deep_stage(
        job=job,
        worker_id=worker_id,
        checkpoint=updated_checkpoint,
        result=updated_result,
    )


def _handle_final_synthesis_stage(
    *,
    job: dict,
    worker_id: str,
    synthesis_fn: Callable,
    respect_interactive_preemption: bool,
) -> dict:
    checkpoint = dict(
        job.get(
            "checkpoint"
        )
        or {}
    )

    accumulated = dict(
        job.get(
            "result"
        )
        or {}
    )

    if (
        respect_interactive_preemption
        and not background_research_can_run()
    ):
        print(
            "[Research] Interactive activity detected; final synthesis yielded."
        )

        return _pause_for_next_deep_stage(
            job=job,
            worker_id=worker_id,
            checkpoint={
                **checkpoint,
                "stage": "final_synthesis_deferred",
                "next_stage": "final_synthesis",
                "user_ready": False,
            },
            result=accumulated,
        )

    started_at = _now_iso()

    started_checkpoint = {
        **checkpoint,
        "stage": "final_synthesis",
        "stage_started_at": started_at,
        "next_stage": "final_synthesis",
        "user_ready": False,
    }

    job = update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="running",
        checkpoint=started_checkpoint,
        result=accumulated,
    )

    print(
        "[Research] Grounded final synthesis started: "
        + canonical_research_topic(
            job
        )
    )

    synthesis = synthesis_fn(
        job,
        accumulated,
    )

    if isinstance(
        synthesis,
        str,
    ):
        synthesis = {
            "success": bool(
                synthesis.strip()
            ),
            "report_text": synthesis,
            "uncertainties": [],
            "source_urls": [],
        }

    if not isinstance(
        synthesis,
        dict,
    ):
        raise RuntimeError(
            "final synthesis function returned an invalid result"
        )

    if not synthesis.get(
        "success"
    ):
        raise RuntimeError(
            _normalise_space(
                synthesis.get(
                    "failure_reason"
                )
            )
            or "final synthesis failed"
        )

    report_text = str(
        synthesis.get(
            "report_text"
        )
        or ""
    ).strip()

    if not report_text:
        raise RuntimeError(
            "final synthesis returned an empty report"
        )

    synthesis_record = {
        "report_text": report_text,
        "generated_at": _now_iso(),
        "model": synthesis.get(
            "model"
        ),
        "uncertainties": list(
            synthesis.get(
                "uncertainties"
            )
            or []
        )[
            :8
        ],
        "source_urls": list(
            synthesis.get(
                "source_urls"
            )
            or []
        ),
    }

    updated_result = {
        **accumulated,
        "research_phase": "final_synthesis_draft_complete",
        "user_ready": False,
        "final_synthesis": synthesis_record,
        "final_report_verified": False,
    }

    completed_checkpoint = {
        **started_checkpoint,
        "stage": "final_synthesis_draft_complete",
        "stage_finished_at": _now_iso(),
        "next_stage": "final_synthesis_verification",
        "user_ready": False,
    }

    print(
        "[Research] Final synthesis draft checkpoint saved; verification is next."
    )

    return update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="paused",
        checkpoint=completed_checkpoint,
        result=updated_result,
        error=None,
        resume_automatically=True,
    )



def _draft_verification_units(
    draft: str,
) -> list[str]:
    value = re.sub(
        r"[ \t]+",
        " ",
        str(
            draft
            or ""
        ).strip(),
    )

    if not value:
        return []

    return [
        piece.strip()
        for piece in re.split(
            r"(?<=[.!?])\s+|\n+",
            value,
        )
        if piece.strip()
    ]


MIN_REPAIR_ASSESSMENT_COVERAGE = 0.90
MAX_REPAIR_MISSING_ASSESSMENTS = 5


def _normalise_verification_feedback_for_repair(
    report_text: str,
    verification: dict,
) -> Optional[dict]:
    """
    Return repair-safe verifier feedback, or None when the feedback is too incomplete.

    A fully structured verifier map is ideal. Real local-model runs can occasionally
    return valid JSON that omits only the final few sentence assessments. That is not
    safe enough for final acceptance, but it *is* safe enough for one conservative
    repair because Core pessimistically marks every missing sentence unsupported and
    the repaired report must still pass a fresh verifier run before delivery.

    Sparse/transport-style output remains fail-closed.
    """

    if not isinstance(verification, dict):
        return None

    if verification.get("supported") is True:
        return None

    violations = [
        _normalise_space(item).lower()
        for item in (verification.get("violations") or [])
        if _normalise_space(item)
    ]

    if any(
        "could not validate the draft" in item
        for item in violations
    ):
        return None

    units = _draft_verification_units(report_text)
    if not units:
        return None

    assessments = verification.get("sentence_assessments") or []
    if not isinstance(assessments, list):
        return None

    by_index = {}
    has_failure = False

    for assessment in assessments:
        if not isinstance(assessment, dict):
            continue

        try:
            index = int(assessment.get("index"))
        except (TypeError, ValueError):
            continue

        if not (1 <= index <= len(units)):
            continue

        supported = assessment.get("supported") is True
        by_index[index] = {
            "index": index,
            "supported": supported,
        }

        if not supported:
            has_failure = True

    expected = set(range(1, len(units) + 1))
    indexes = set(by_index)
    missing = sorted(expected - indexes)

    if not has_failure and not violations:
        return None

    if missing:
        coverage = len(indexes) / len(expected)

        if (
            coverage < MIN_REPAIR_ASSESSMENT_COVERAGE
            or len(missing) > MAX_REPAIR_MISSING_ASSESSMENTS
        ):
            return None

        for index in missing:
            by_index[index] = {
                "index": index,
                "supported": False,
            }

        normalised = dict(verification)
        normalised["sentence_assessments"] = [
            by_index[index]
            for index in sorted(by_index)
        ]
        normalised["repair_feedback_completed_by_core"] = True
        normalised["repair_feedback_missing_indexes"] = missing
        normalised["repair_feedback_coverage"] = coverage
        return normalised

    normalised = dict(verification)
    normalised["sentence_assessments"] = [
        by_index[index]
        for index in sorted(by_index)
    ]
    return normalised


def _verification_feedback_supports_repair(
    report_text: str,
    verification: dict,
) -> bool:
    return (
        _normalise_verification_feedback_for_repair(
            report_text,
            verification,
        )
        is not None
    )


def _pause_for_synthesis_review(
    *,
    job: dict,
    worker_id: str,
    checkpoint: dict,
    accumulated: dict,
    synthesis_record: dict,
    verified_at: str,
    review_reason: str,
) -> dict:
    review_result = {
        **accumulated,
        "research_phase": "final_synthesis_review_required",
        "user_ready": False,
        "final_synthesis": synthesis_record,
        "final_report_verified": False,
    }

    review_checkpoint = {
        **checkpoint,
        "stage": "final_synthesis_review_required",
        "stage_finished_at": verified_at,
        "next_stage": "synthesis_review_required",
        "user_ready": False,
        "review_reason": review_reason,
    }

    print(
        "[Research] Final synthesis was not fully grounded; paused for review."
    )

    return update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="paused",
        checkpoint=review_checkpoint,
        result=review_result,
        error=None,
        resume_automatically=False,
    )


def _handle_final_synthesis_verification_stage(
    *,
    job: dict,
    worker_id: str,
    synthesis_verifier_fn: Callable,
    respect_interactive_preemption: bool,
) -> dict:
    checkpoint = dict(
        job.get(
            "checkpoint"
        )
        or {}
    )

    accumulated = dict(
        job.get(
            "result"
        )
        or {}
    )

    synthesis_record = accumulated.get(
        "final_synthesis"
    )

    if not isinstance(
        synthesis_record,
        dict,
    ):
        raise RuntimeError(
            "final synthesis verification has no persisted draft"
        )

    report_text = str(
        synthesis_record.get(
            "report_text"
        )
        or ""
    ).strip()

    if not report_text:
        raise RuntimeError(
            "final synthesis verification has an empty persisted draft"
        )

    if (
        respect_interactive_preemption
        and not background_research_can_run()
    ):
        print(
            "[Research] Interactive activity detected; synthesis verification yielded."
        )

        return _pause_for_next_deep_stage(
            job=job,
            worker_id=worker_id,
            checkpoint={
                **checkpoint,
                "stage": "final_synthesis_verification_deferred",
                "next_stage": "final_synthesis_verification",
                "user_ready": False,
            },
            result=accumulated,
        )

    started_checkpoint = {
        **checkpoint,
        "stage": "final_synthesis_verification",
        "stage_started_at": _now_iso(),
        "next_stage": "final_synthesis_verification",
        "user_ready": False,
    }

    job = update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="running",
        checkpoint=started_checkpoint,
        result=accumulated,
    )

    print(
        "[Research] Verifying final synthesis against stored evidence."
    )

    verification = synthesis_verifier_fn(
        job,
        accumulated,
        report_text,
    )

    if isinstance(
        verification,
        list,
    ):
        verification = {
            "supported": len(
                verification
            ) == 0,
            "violations": list(
                verification
            ),
        }

    if not isinstance(
        verification,
        dict,
    ):
        raise RuntimeError(
            "final synthesis verifier returned an invalid result"
        )

    supported = (
        verification.get(
            "supported"
        )
        is True
    )

    violations = [
        _normalise_space(
            item
        )
        for item in (
            verification.get(
                "violations"
            )
            or []
        )
        if _normalise_space(
            item
        )
    ][
        :8
    ]

    verified_at = _now_iso()

    verification_record = {
        "supported": supported,
        "violations": violations,
        "verified_at": verified_at,
        "model": verification.get(
            "model"
        ),
        "accepted_sentences": list(
            verification.get(
                "accepted_sentences"
            )
            or []
        ),
        "sentence_assessments": list(
            verification.get(
                "sentence_assessments"
            )
            or []
        ),
    }

    repair_feedback = (
        _normalise_verification_feedback_for_repair(
            report_text,
            verification_record,
        )
        if not supported
        else None
    )

    if repair_feedback is not None:
        verification_record = repair_feedback

    synthesis_record = {
        **synthesis_record,
        "verification": verification_record,
    }

    if not supported:
        repair_attempt_count = int(
            synthesis_record.get(
                "repair_attempt_count"
            )
            or 0
        )

        repairable = bool(
            repair_attempt_count < 1
            and repair_feedback is not None
        )

        if repairable:
            queued_result = {
                **accumulated,
                "research_phase": "final_synthesis_repair_pending",
                "user_ready": False,
                "final_synthesis": synthesis_record,
                "final_report_verified": False,
            }

            queued_checkpoint = {
                **started_checkpoint,
                "stage": "final_synthesis_repair_pending",
                "stage_finished_at": verified_at,
                "next_stage": "final_synthesis_repair",
                "user_ready": False,
                "repair_attempt_count": repair_attempt_count,
                "repair_reason": (
                    violations[
                        0
                    ]
                    if violations
                    else (
                        "The verifier returned complete unsupported-sentence feedback."
                    )
                ),
            }

            print(
                "[Research] Verification rejected the draft; one grounded repair is queued."
            )

            return update_claimed_research_job(
                job[
                    "id"
                ],
                worker_id=worker_id,
                status="paused",
                checkpoint=queued_checkpoint,
                result=queued_result,
                error=None,
                resume_automatically=True,
            )

        review_reason = (
            violations[
                0
            ]
            if violations
            else (
                "The final synthesis could not be verified against the stored evidence."
            )
        )

        return _pause_for_synthesis_review(
            job=job,
            worker_id=worker_id,
            checkpoint=started_checkpoint,
            accumulated=accumulated,
            synthesis_record=synthesis_record,
            verified_at=verified_at,
            review_reason=review_reason,
        )

    source_index = list(
        accumulated.get(
            "source_index"
        )
        or []
    )

    source_urls = []
    seen_urls = set()

    for source in source_index:
        if not isinstance(
            source,
            dict,
        ):
            continue

        url = _normalise_space(
            source.get(
                "url"
            )
        )

        if (
            not url
            or url in seen_urls
        ):
            continue

        seen_urls.add(
            url
        )
        source_urls.append(
            url
        )

    final_report = {
        "text": report_text,
        "verified": True,
        "verified_at": verified_at,
        "source_urls": source_urls,
        "source_index": source_index,
        "uncertainties": list(
            synthesis_record.get(
                "uncertainties"
            )
            or []
        )[
            :8
        ],
    }

    completed_result = {
        **accumulated,
        "research_phase": "final_synthesis_complete",
        "user_ready": True,
        "final_synthesis": synthesis_record,
        "final_report": final_report,
        "final_report_text": report_text,
        "final_report_verified": True,
    }

    completed_checkpoint = {
        **started_checkpoint,
        "stage": "final_synthesis_complete",
        "stage_finished_at": verified_at,
        "next_stage": "delivery",
        "user_ready": True,
        "final_report_verified": True,
    }

    print(
        "[Research] Grounded final report verified and ready for delivery."
    )

    return update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="completed",
        checkpoint=completed_checkpoint,
        result=completed_result,
        error=None,
        resume_automatically=False,
    )


def _handle_final_synthesis_repair_stage(
    *,
    job: dict,
    worker_id: str,
    synthesis_repair_fn: Callable,
    respect_interactive_preemption: bool,
) -> dict:
    checkpoint = dict(
        job.get(
            "checkpoint"
        )
        or {}
    )

    accumulated = dict(
        job.get(
            "result"
        )
        or {}
    )

    synthesis_record = accumulated.get(
        "final_synthesis"
    )

    if not isinstance(
        synthesis_record,
        dict,
    ):
        raise RuntimeError(
            "final synthesis repair has no persisted synthesis record"
        )

    report_text = str(
        synthesis_record.get(
            "report_text"
        )
        or ""
    ).strip()

    if not report_text:
        raise RuntimeError(
            "final synthesis repair has no persisted draft"
        )

    repair_attempt_count = int(
        synthesis_record.get(
            "repair_attempt_count"
        )
        or 0
    )

    verification_record = synthesis_record.get(
        "verification"
    )

    if repair_attempt_count >= 1:
        return _pause_for_synthesis_review(
            job=job,
            worker_id=worker_id,
            checkpoint=checkpoint,
            accumulated=accumulated,
            synthesis_record=synthesis_record,
            verified_at=_now_iso(),
            review_reason=(
                "The one permitted grounded synthesis repair was already used."
            ),
        )

    if not isinstance(
        verification_record,
        dict,
    ):
        return _pause_for_synthesis_review(
            job=job,
            worker_id=worker_id,
            checkpoint=checkpoint,
            accumulated=accumulated,
            synthesis_record=synthesis_record,
            verified_at=_now_iso(),
            review_reason=(
                "The synthesis repair stage has no complete verifier feedback."
            ),
        )

    if not _verification_feedback_supports_repair(
        report_text,
        verification_record,
    ):
        return _pause_for_synthesis_review(
            job=job,
            worker_id=worker_id,
            checkpoint=checkpoint,
            accumulated=accumulated,
            synthesis_record=synthesis_record,
            verified_at=_now_iso(),
            review_reason=(
                "The verifier feedback is not complete enough for a safe grounded repair."
            ),
        )

    if (
        respect_interactive_preemption
        and not background_research_can_run()
    ):
        print(
            "[Research] Interactive activity detected; synthesis repair yielded."
        )

        return _pause_for_next_deep_stage(
            job=job,
            worker_id=worker_id,
            checkpoint={
                **checkpoint,
                "stage": "final_synthesis_repair_deferred",
                "next_stage": "final_synthesis_repair",
                "user_ready": False,
            },
            result=accumulated,
        )

    started_at = _now_iso()

    started_checkpoint = {
        **checkpoint,
        "stage": "final_synthesis_repair",
        "stage_started_at": started_at,
        "next_stage": "final_synthesis_repair",
        "user_ready": False,
    }

    job = update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="running",
        checkpoint=started_checkpoint,
        result=accumulated,
    )

    print(
        "[Research] Grounded final synthesis repair started."
    )

    repair = synthesis_repair_fn(
        job,
        accumulated,
        report_text,
        verification_record,
    )

    if isinstance(
        repair,
        str,
    ):
        repair = {
            "success": bool(
                repair.strip()
            ),
            "report_text": repair,
            "uncertainties": [],
            "source_urls": [],
        }

    if not isinstance(
        repair,
        dict,
    ):
        raise RuntimeError(
            "final synthesis repair function returned an invalid result"
        )

    repaired_text = str(
        repair.get(
            "report_text"
        )
        or ""
    ).strip()

    if (
        repair.get(
            "success"
        ) is not True
        or not repaired_text
    ):
        reason = _normalise_space(
            repair.get(
                "failure_reason"
            )
        ) or (
            "The one permitted grounded synthesis repair did not produce a usable draft."
        )

        return _pause_for_synthesis_review(
            job=job,
            worker_id=worker_id,
            checkpoint=started_checkpoint,
            accumulated=accumulated,
            synthesis_record=synthesis_record,
            verified_at=_now_iso(),
            review_reason=reason,
        )

    if repaired_text == report_text:
        return _pause_for_synthesis_review(
            job=job,
            worker_id=worker_id,
            checkpoint=started_checkpoint,
            accumulated=accumulated,
            synthesis_record=synthesis_record,
            verified_at=_now_iso(),
            review_reason=(
                "The grounded synthesis repair returned the same rejected draft."
            ),
        )

    failed_indexes = [
        int(
            item.get(
                "index"
            )
        )
        for item in (
            verification_record.get(
                "sentence_assessments"
            )
            or []
        )
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "supported"
        ) is not True
        and str(
            item.get(
                "index"
            )
            or ""
        ).isdigit()
    ]

    verification_history = list(
        synthesis_record.get(
            "verification_history"
        )
        or []
    )
    verification_history.append(
        dict(
            verification_record
        )
    )

    repair_history = list(
        synthesis_record.get(
            "repair_history"
        )
        or []
    )
    repair_history.append({
        "attempt": 1,
        "generated_at": _now_iso(),
        "model": repair.get(
            "model"
        ),
        "violations": list(
            verification_record.get(
                "violations"
            )
            or []
        )[
            :8
        ],
        "failed_sentence_indexes": failed_indexes,
    })

    repaired_record = {
        **synthesis_record,
        "report_text": repaired_text,
        "uncertainties": list(
            repair.get(
                "uncertainties"
            )
            or []
        )[
            :8
        ],
        "source_urls": list(
            repair.get(
                "source_urls"
            )
            or synthesis_record.get(
                "source_urls"
            )
            or []
        ),
        "repair_attempt_count": 1,
        "repair_history": repair_history,
        "verification_history": verification_history,
        "verification": None,
        "repaired_at": _now_iso(),
        "repair_model": repair.get(
            "model"
        ),
    }

    repaired_result = {
        **accumulated,
        "research_phase": "final_synthesis_repair_complete",
        "user_ready": False,
        "final_synthesis": repaired_record,
        "final_report_verified": False,
    }

    repaired_checkpoint = {
        **started_checkpoint,
        "stage": "final_synthesis_repair_complete",
        "stage_finished_at": _now_iso(),
        "next_stage": "final_synthesis_verification",
        "user_ready": False,
        "repair_attempt_count": 1,
    }

    print(
        "[Research] Grounded repair checkpoint saved; verification will run once more."
    )

    return update_claimed_research_job(
        job[
            "id"
        ],
        worker_id=worker_id,
        status="paused",
        checkpoint=repaired_checkpoint,
        result=repaired_result,
        error=None,
        resume_automatically=True,
    )

def run_one_research_job(
    *,
    worker_id: Optional[str] = None,
    research_fn: Callable = gather_public_factual_research,
    packet_builder: Callable = build_internal_public_factual_packet,
    planner_fn: Callable = plan_next_deep_research_round,
    synthesis_fn: Callable = generate_grounded_final_synthesis,
    synthesis_verifier_fn: Callable = verify_grounded_final_synthesis,
    synthesis_repair_fn: Callable = repair_grounded_final_synthesis,
    lease_seconds: int = 900,
    respect_interactive_preemption: bool = False,
) -> Optional[dict]:
    """
    Claim and execute ONE resumable background-research stage.

    Each web query or planning transition ends in a durable checkpoint. That
    gives interactive work a chance to preempt before the next stage and means
    a process/PC restart never needs to throw the entire research job away.
    """

    owner = (
        _normalise_space(
            worker_id
        )
        or (
            "research-worker-"
            + str(
                uuid.uuid4()
            )
        )
    )

    job = claim_next_research_job(
        worker_id=owner,
        lease_seconds=lease_seconds,
    )

    if job is None:
        return None

    print(
        "[Research] Claimed background job: "
        + canonical_research_topic(
            job
        )
        + " (attempt "
        + str(
            job.get(
                "attempt_count"
            )
            or 0
        )
        + ")."
    )

    checkpoint = (
        job.get(
            "checkpoint"
        )
        or {}
    )

    next_stage = _normalise_space(
        checkpoint.get(
            "next_stage"
        )
    ).lower()

    try:
        if next_stage == "final_synthesis":
            return _handle_final_synthesis_stage(
                job=job,
                worker_id=owner,
                synthesis_fn=synthesis_fn,
                respect_interactive_preemption=(
                    respect_interactive_preemption
                ),
            )

        if next_stage == "final_synthesis_verification":
            return _handle_final_synthesis_verification_stage(
                job=job,
                worker_id=owner,
                synthesis_verifier_fn=synthesis_verifier_fn,
                respect_interactive_preemption=(
                    respect_interactive_preemption
                ),
            )

        if next_stage == "final_synthesis_repair":
            return _handle_final_synthesis_repair_stage(
                job=job,
                worker_id=owner,
                synthesis_repair_fn=synthesis_repair_fn,
                respect_interactive_preemption=(
                    respect_interactive_preemption
                ),
            )

        if next_stage in {
            "iterative_deep_research",
        }:
            return _handle_iterative_deep_stage(
                job=job,
                worker_id=owner,
                research_fn=research_fn,
                packet_builder=packet_builder,
                planner_fn=planner_fn,
                respect_interactive_preemption=(
                    respect_interactive_preemption
                ),
            )

        return _handle_initial_research_stage(
            job=job,
            worker_id=owner,
            research_fn=research_fn,
            packet_builder=packet_builder,
            respect_interactive_preemption=(
                respect_interactive_preemption
            ),
        )

    except Exception as error:
        failed_checkpoint = {
            **checkpoint,
            "stage": "background_research_failed",
            "stage_finished_at": _now_iso(),
            "failure_reason": str(
                error
            ),
            "user_ready": False,
        }

        print(
            "[Research] Background stage failed: "
            + str(
                error
            )
        )

        return update_claimed_research_job(
            job[
                "id"
            ],
            worker_id=owner,
            status="failed",
            checkpoint=failed_checkpoint,
            error=str(
                error
            ),
            resume_automatically=False,
        )


def _background_worker_loop(
    worker_id: str,
) -> None:
    poll_seconds = _env_float(
        "MAIRON_RESEARCH_WORKER_POLL_SECONDS",
        2.0,
        0.25,
    )

    while not _WORKER_STOP_EVENT.is_set():
        if not background_research_enabled():
            _WORKER_STOP_EVENT.wait(
                poll_seconds
            )
            continue

        if not background_research_can_run():
            _WORKER_STOP_EVENT.wait(
                min(
                    poll_seconds,
                    1.0,
                )
            )
            continue

        processed = run_one_research_job(
            worker_id=worker_id,
            respect_interactive_preemption=True,
        )

        if processed is None:
            _WORKER_STOP_EVENT.wait(
                poll_seconds
            )
            continue

        # One bounded stage at a time. The next loop re-checks Oliver's activity
        # before claiming another stage of the same durable job.
        _WORKER_STOP_EVENT.wait(
            0.15
        )


def ensure_background_research_worker_started() -> bool:
    """
    Lazily start one daemon worker for this Mairon process.

    The worker is safe to start even when the queue is empty. This matters for
    restart recovery: an old paused/leased research job can continue after the
    first interactive Mairon turn in a new process.
    """

    global _WORKER_THREAD

    if not background_research_enabled():
        return False

    with _WORKER_LOCK:
        if (
            _WORKER_THREAD is not None
            and _WORKER_THREAD.is_alive()
        ):
            return True

        _WORKER_STOP_EVENT.clear()

        worker_id = (
            "research-worker-"
            + str(
                uuid.uuid4()
            )
        )

        _WORKER_THREAD = threading.Thread(
            target=_background_worker_loop,
            args=(
                worker_id,
            ),
            name="MaironBackgroundResearch",
            daemon=True,
        )

        _WORKER_THREAD.start()

        print(
            "[Research] Background worker started."
        )

        return True


def stop_background_research_worker(
    *,
    timeout: float = 3.0,
) -> None:
    global _WORKER_THREAD

    _WORKER_STOP_EVENT.set()

    thread = _WORKER_THREAD

    if (
        thread is not None
        and thread.is_alive()
    ):
        thread.join(
            timeout=max(
                0.0,
                float(
                    timeout
                ),
            )
        )

    with _WORKER_LOCK:
        _WORKER_THREAD = None