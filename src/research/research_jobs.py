from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


ACTIVE_RESEARCH_JOB_STATUSES = {
    "queued",
    "running",
    "paused",
}

TERMINAL_RESEARCH_JOB_STATUSES = {
    "completed",
    "cancelled",
    "failed",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def research_job_database_path() -> Path:
    configured = str(
        os.getenv(
            "MAIRON_RESEARCH_JOB_DB",
            "",
        )
        or ""
    ).strip()

    if configured:
        return Path(configured)

    return (
        _project_root()
        / "data"
        / "private"
        / "research_jobs.sqlite3"
    )


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _normalise_space(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ).strip(),
    )


def canonical_research_topic_key(
    topic: Any,
) -> str:
    value = _normalise_space(
        topic
    ).lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()[:240]


def _encode_json(
    value: Any,
) -> str:
    return json.dumps(
        value
        if value is not None
        else {},
        ensure_ascii=False,
        sort_keys=True,
    )


def _decode_json(
    value: Any,
) -> Any:
    if not value:
        return {}

    try:
        return json.loads(
            str(
                value
            )
        )
    except Exception:
        return {}


@contextmanager
def _connect():
    """
    Open one research-job SQLite transaction and ALWAYS close its file handle.

    sqlite3.Connection's built-in context manager commits or rolls back, but
    does not close the connection on exit. On Windows that leaves the SQLite
    file locked and breaks TemporaryDirectory cleanup with WinError 32.
    """

    path = research_job_database_path()

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        path,
        timeout=30,
    )

    try:
        connection.row_factory = (
            sqlite3.Row
        )

        connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        connection.execute(
            "PRAGMA foreign_keys=ON"
        )

        yield connection

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    rows = connection.execute(
        "PRAGMA table_info("
        + str(
            table_name
        )
        + ")"
    ).fetchall()

    return {
        str(
            row[
                "name"
            ]
        )
        for row in rows
    }


def _ensure_research_job_schema_columns(
    connection: sqlite3.Connection,
) -> None:
    """
    Forward-only additive migration for the persistent research queue.

    Phase 11.5.1 databases already exist in user installs. CREATE TABLE IF NOT
    EXISTS does not add new columns, so lease fields must be migrated explicitly
    without deleting or recreating the queue.
    """

    columns = _table_columns(
        connection,
        "research_jobs",
    )

    additions = {
        "lease_owner": "TEXT",
        "lease_expires_at": "TEXT",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "resume_automatically": "INTEGER NOT NULL DEFAULT 0",
    }

    for column_name, declaration in additions.items():
        if column_name in columns:
            continue

        connection.execute(
            "ALTER TABLE research_jobs ADD COLUMN "
            + column_name
            + " "
            + declaration
        )

    # Older phases intentionally paused resumable research work between bounded
    # stages. When a newer worker first opens that database, make known automatic
    # stages resumable without requiring Oliver to recreate the job.
    paused_rows = connection.execute(
        """
        SELECT id, checkpoint_json, result_json
        FROM research_jobs
        WHERE status = 'paused'
          AND COALESCE(resume_automatically, 0) = 0
        """
    ).fetchall()

    for row in paused_rows:
        checkpoint = _decode_json(
            row[
                "checkpoint_json"
            ]
        )

        result = _decode_json(
            row[
                "result_json"
            ]
        )

        if not isinstance(
            checkpoint,
            dict,
        ):
            continue

        next_stage = checkpoint.get(
            "next_stage"
        )

        if next_stage in {
            "iterative_deep_research",
            "final_synthesis",
            "final_synthesis_verification",
        }:
            connection.execute(
                """
                UPDATE research_jobs
                SET resume_automatically = 1
                WHERE id = ?
                """,
                (
                    row[
                        "id"
                    ],
                ),
            )
            continue

        # Phase 11.5.3 treated a max-round planner disagreement as requiring
        # human review even when the deterministic evidence floor had already
        # been satisfied. Phase 11.5.4 can safely hand that accumulated evidence
        # to grounded synthesis instead. Only migrate the exact old safety-cap
        # state; unrelated review-required jobs remain deliberately paused.
        quality = (
            checkpoint.get(
                "quality"
            )
            or {}
        )

        old_cap_review = bool(
            next_stage == "research_review_required"
            and checkpoint.get(
                "stage"
            )
            == "deep_research_review_required"
            and isinstance(
                quality,
                dict,
            )
            and quality.get(
                "minimum_floor_met"
            )
            is True
            and quality.get(
                "maximum_rounds_reached"
            )
            is True
            and "safety cap was reached"
            in str(
                checkpoint.get(
                    "review_reason"
                )
                or ""
            ).lower()
        )

        # Phase 11.5.4 initially reused the conversational factual verifier's
        # fixed 320-token response budget. Long final reports require one JSON
        # sentence assessment per verification unit, so an otherwise valid
        # verifier response could be truncated before the JSON object closed.
        # Retry only that exact protocol/transport-style failure once after the
        # verifier implementation is upgraded. Genuine unsupported-claim review
        # states remain paused for human inspection.
        synthesis_record = (
            result.get(
                "final_synthesis"
            )
            if isinstance(
                result,
                dict,
            )
            else None
        )

        verifier_protocol_retry_count = int(
            checkpoint.get(
                "verifier_protocol_retry_count"
            )
            or 0
        )

        old_verifier_protocol_failure = bool(
            next_stage == "synthesis_review_required"
            and checkpoint.get(
                "stage"
            )
            == "final_synthesis_review_required"
            and verifier_protocol_retry_count < 1
            and "public factual-support verifier could not validate the draft"
            in str(
                checkpoint.get(
                    "review_reason"
                )
                or ""
            ).lower()
            and isinstance(
                synthesis_record,
                dict,
            )
            and str(
                synthesis_record.get(
                    "report_text"
                )
                or ""
            ).strip()
        )

        if old_verifier_protocol_failure:
            migrated_checkpoint = {
                **checkpoint,
                "stage": "final_synthesis_draft_complete",
                "next_stage": "final_synthesis_verification",
                "user_ready": False,
                "verifier_protocol_retry_count": (
                    verifier_protocol_retry_count
                    + 1
                ),
            }
            migrated_checkpoint.pop(
                "review_reason",
                None,
            )

            migrated_result = dict(
                result
            )
            migrated_result[
                "research_phase"
            ] = "final_synthesis_draft_complete"
            migrated_result[
                "user_ready"
            ] = False
            migrated_result[
                "final_report_verified"
            ] = False

            connection.execute(
                """
                UPDATE research_jobs
                SET checkpoint_json = ?,
                    result_json = ?,
                    resume_automatically = 1
                WHERE id = ?
                """,
                (
                    _encode_json(
                        migrated_checkpoint
                    ),
                    _encode_json(
                        migrated_result
                    ),
                    row[
                        "id"
                    ],
                ),
            )
            continue

        if not old_cap_review:
            continue

        migrated_checkpoint = {
            **checkpoint,
            "stage": "deep_evidence_collection_complete",
            "next_stage": "final_synthesis",
            "user_ready": False,
            "pending_queries": [],
            "completion_reason": (
                "Migrated from the older max-round review policy: the deterministic "
                "evidence floor was already satisfied, so grounded final synthesis "
                "may now proceed."
            ),
        }
        migrated_checkpoint.pop(
            "review_reason",
            None,
        )

        migrated_result = (
            dict(
                result
            )
            if isinstance(
                result,
                dict,
            )
            else {}
        )
        migrated_result[
            "research_phase"
        ] = "deep_evidence_collection_complete"
        migrated_result[
            "user_ready"
        ] = False
        migrated_result[
            "quality"
        ] = dict(
            quality
        )

        connection.execute(
            """
            UPDATE research_jobs
            SET checkpoint_json = ?,
                result_json = ?,
                resume_automatically = 1
            WHERE id = ?
            """,
            (
                _encode_json(
                    migrated_checkpoint
                ),
                _encode_json(
                    migrated_result
                ),
                row[
                    "id"
                ],
            ),
        )


def initialise_research_job_store() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_jobs (
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

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                research_jobs_status_updated
            ON research_jobs (
                status,
                updated_at
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                research_jobs_topic_key
            ON research_jobs (
                topic_key,
                updated_at
            )
            """
        )

        _ensure_research_job_schema_columns(
            connection
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                research_jobs_lease
            ON research_jobs (
                status,
                lease_expires_at
            )
            """
        )


def _row_to_job(
    row: sqlite3.Row,
) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "status": row["status"],
        "topic": row["topic"],
        "topic_key": row["topic_key"],
        "goal": row["goal"],
        "original_request": row["original_request"],
        "source": row["source"],
        "priority": row["priority"],
        "depth": row["depth"],
        "checkpoint": _decode_json(
            row["checkpoint_json"]
        ),
        "result": _decode_json(
            row["result_json"]
        ),
        "metadata": _decode_json(
            row["metadata_json"]
        ),
        "error": row["error_text"],
        "lease_owner": row["lease_owner"],
        "lease_expires_at": row["lease_expires_at"],
        "attempt_count": int(
            row["attempt_count"]
            or 0
        ),
        "resume_automatically": bool(
            row["resume_automatically"]
        ),
    }


def get_research_job(
    job_id: Any,
) -> Optional[dict]:
    value = _normalise_space(
        job_id
    )

    if not value:
        return None

    initialise_research_job_store()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM research_jobs
            WHERE id = ?
            """,
            (
                value,
            ),
        ).fetchone()

    if row is None:
        return None

    return _row_to_job(
        row
    )


def find_active_research_job(
    topic: Any,
) -> Optional[dict]:
    topic_key = canonical_research_topic_key(
        topic
    )

    if not topic_key:
        return None

    initialise_research_job_store()

    placeholders = ",".join(
        "?"
        for _ in ACTIVE_RESEARCH_JOB_STATUSES
    )

    parameters = [
        topic_key,
        *sorted(
            ACTIVE_RESEARCH_JOB_STATUSES
        ),
    ]

    with _connect() as connection:
        row = connection.execute(
            f"""
            SELECT *
            FROM research_jobs
            WHERE topic_key = ?
              AND status IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT 1
            """,
            parameters,
        ).fetchone()

    if row is None:
        return None

    return _row_to_job(
        row
    )


def create_research_job(
    *,
    topic: Any,
    goal: Any,
    original_request: Any,
    source: str = "explicit_request",
    priority: str = "background",
    depth: str = "deep",
    metadata: Optional[dict] = None,
) -> dict:
    topic_value = _normalise_space(
        topic
    )

    goal_value = _normalise_space(
        goal
    )

    original_request_value = _normalise_space(
        original_request
    )

    if not topic_value:
        raise ValueError(
            "research job topic is required"
        )

    if not goal_value:
        goal_value = (
            "Research the topic thoroughly and produce a trustworthy "
            "answer or recommendation."
        )

    if not original_request_value:
        original_request_value = (
            goal_value
        )

    existing = find_active_research_job(
        topic_value
    )

    if existing is not None:
        return {
            **existing,
            "deduplicated": True,
        }

    now = _now_iso()
    job_id = str(
        uuid.uuid4()
    )

    job_metadata = dict(
        metadata
        or {}
    )

    job_metadata.setdefault(
        "execution_policy",
        "background_only",
    )

    job_metadata.setdefault(
        "interactive_work_preempts_job",
        True,
    )

    with _connect() as connection:
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
                attempt_count,
                resume_automatically
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                now,
                now,
                "queued",
                topic_value,
                canonical_research_topic_key(
                    topic_value
                ),
                goal_value,
                original_request_value,
                _normalise_space(
                    source
                )
                or "explicit_request",
                _normalise_space(
                    priority
                )
                or "background",
                _normalise_space(
                    depth
                )
                or "deep",
                _encode_json({}),
                _encode_json({}),
                _encode_json(
                    job_metadata
                ),
                None,
                None,
                None,
                0,
                0,
            ),
        )

    created = get_research_job(
        job_id
    )

    if created is None:
        raise RuntimeError(
            "research job was created but could not be read back"
        )

    return {
        **created,
        "deduplicated": False,
    }


def list_research_jobs(
    *,
    statuses: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict]:
    initialise_research_job_store()

    safe_limit = max(
        1,
        min(
            int(
                limit
                or 50
            ),
            500,
        ),
    )

    parameters = []
    where = ""

    if statuses:
        cleaned = [
            _normalise_space(
                value
            ).lower()
            for value in statuses
            if _normalise_space(
                value
            )
        ]

        if cleaned:
            placeholders = ",".join(
                "?"
                for _ in cleaned
            )

            where = (
                f"WHERE status IN ({placeholders})"
            )

            parameters.extend(
                cleaned
            )

    parameters.append(
        safe_limit
    )

    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM research_jobs
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()

    return [
        _row_to_job(
            row
        )
        for row in rows
    ]


def update_research_job(
    job_id: Any,
    *,
    status: Optional[str] = None,
    checkpoint: Optional[dict] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    resume_automatically: Optional[bool] = None,
) -> dict:
    current = get_research_job(
        job_id
    )

    if current is None:
        raise KeyError(
            "research job not found"
        )

    next_status = (
        _normalise_space(
            status
        ).lower()
        if status is not None
        else current["status"]
    )

    allowed_statuses = (
        ACTIVE_RESEARCH_JOB_STATUSES
        | TERMINAL_RESEARCH_JOB_STATUSES
    )

    if next_status not in allowed_statuses:
        raise ValueError(
            "unsupported research job status: "
            + next_status
        )

    next_checkpoint = (
        checkpoint
        if checkpoint is not None
        else current["checkpoint"]
    )

    next_result = (
        result
        if result is not None
        else current["result"]
    )

    if resume_automatically is None:
        next_resume_automatically = bool(
            current.get(
                "resume_automatically"
            )
        )
    else:
        next_resume_automatically = bool(
            resume_automatically
        )

    if next_status != "paused":
        next_resume_automatically = False

    with _connect() as connection:
        connection.execute(
            """
            UPDATE research_jobs
            SET updated_at = ?,
                status = ?,
                checkpoint_json = ?,
                result_json = ?,
                error_text = ?,
                lease_owner = CASE
                    WHEN ? = 'running' THEN lease_owner
                    ELSE NULL
                END,
                lease_expires_at = CASE
                    WHEN ? = 'running' THEN lease_expires_at
                    ELSE NULL
                END,
                resume_automatically = ?
            WHERE id = ?
            """,
            (
                _now_iso(),
                next_status,
                _encode_json(
                    next_checkpoint
                ),
                _encode_json(
                    next_result
                ),
                (
                    str(
                        error
                    )
                    if error is not None
                    else current["error"]
                ),
                next_status,
                next_status,
                1
                if next_resume_automatically
                else 0,
                str(
                    current["id"]
                ),
            ),
        )

    updated = get_research_job(
        current["id"]
    )

    if updated is None:
        raise RuntimeError(
            "research job update could not be read back"
        )

    return updated


def _lease_expiry_iso(
    lease_seconds: int,
) -> str:
    try:
        seconds = max(
            30,
            int(
                lease_seconds
                or 0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        seconds = 300

    return (
        datetime.now(
            timezone.utc
        )
        + timedelta(
            seconds=seconds
        )
    ).isoformat()


def claim_next_research_job(
    *,
    worker_id: Any,
    lease_seconds: int = 300,
) -> Optional[dict]:
    """
    Atomically claim the oldest available background job.

    A queued job is eligible immediately. A previously-running job becomes
    eligible again only after its lease expires, which lets a new worker recover
    work after a crash/restart without two live workers owning it at once.
    """

    worker = _normalise_space(
        worker_id
    )

    if not worker:
        raise ValueError(
            "worker_id is required"
        )

    initialise_research_job_store()

    now = _now_iso()
    lease_expires_at = _lease_expiry_iso(
        lease_seconds
    )

    with _connect() as connection:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        row = connection.execute(
            """
            SELECT *
            FROM research_jobs
            WHERE priority = 'background'
              AND (
                    status = 'queued'
                    OR (
                        status = 'paused'
                        AND COALESCE(resume_automatically, 0) = 1
                    )
                    OR (
                        status = 'running'
                        AND (
                            lease_expires_at IS NULL
                            OR lease_expires_at <= ?
                        )
                    )
                  )
            ORDER BY
                CASE status
                    WHEN 'queued' THEN 0
                    WHEN 'paused' THEN 1
                    ELSE 2
                END,
                updated_at ASC,
                created_at ASC
            LIMIT 1
            """,
            (
                now,
            ),
        ).fetchone()

        if row is None:
            return None

        job_id = str(
            row[
                "id"
            ]
        )

        connection.execute(
            """
            UPDATE research_jobs
            SET updated_at = ?,
                status = 'running',
                lease_owner = ?,
                lease_expires_at = ?,
                attempt_count = COALESCE(attempt_count, 0) + 1,
                error_text = NULL,
                resume_automatically = 0
            WHERE id = ?
            """,
            (
                now,
                worker,
                lease_expires_at,
                job_id,
            ),
        )

        claimed_row = connection.execute(
            """
            SELECT *
            FROM research_jobs
            WHERE id = ?
            """,
            (
                job_id,
            ),
        ).fetchone()

    if claimed_row is None:
        return None

    return _row_to_job(
        claimed_row
    )


def renew_research_job_lease(
    job_id: Any,
    *,
    worker_id: Any,
    lease_seconds: int = 300,
) -> bool:
    job_value = _normalise_space(
        job_id
    )

    worker = _normalise_space(
        worker_id
    )

    if not job_value or not worker:
        return False

    initialise_research_job_store()

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE research_jobs
            SET updated_at = ?,
                lease_expires_at = ?
            WHERE id = ?
              AND status = 'running'
              AND lease_owner = ?
            """,
            (
                _now_iso(),
                _lease_expiry_iso(
                    lease_seconds
                ),
                job_value,
                worker,
            ),
        )

        return cursor.rowcount == 1


def update_claimed_research_job(
    job_id: Any,
    *,
    worker_id: Any,
    status: Optional[str] = None,
    checkpoint: Optional[dict] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    lease_seconds: int = 300,
    resume_automatically: bool = False,
) -> dict:
    """
    Update a job only when the caller still owns its active lease.

    This is the worker-safe counterpart to update_research_job(). Terminal,
    queued, and paused transitions release the lease automatically.
    """

    job_value = _normalise_space(
        job_id
    )

    worker = _normalise_space(
        worker_id
    )

    if not job_value or not worker:
        raise ValueError(
            "job_id and worker_id are required"
        )

    initialise_research_job_store()

    current = get_research_job(
        job_value
    )

    if current is None:
        raise KeyError(
            "research job not found""research job not found"
        )

    if (
        current.get(
            "status"
        )
        != "running"
        or current.get(
            "lease_owner"
        )
        != worker
    ):
        raise RuntimeError(
            "research job lease is not owned by this worker"
        )

    next_status = (
        _normalise_space(
            status
        ).lower()
        if status is not None
        else "running"
    )

    allowed_statuses = (
        ACTIVE_RESEARCH_JOB_STATUSES
        | TERMINAL_RESEARCH_JOB_STATUSES
    )

    if next_status not in allowed_statuses:
        raise ValueError(
            "unsupported research job status: "
            + next_status
        )

    next_checkpoint = (
        checkpoint
        if checkpoint is not None
        else current.get(
            "checkpoint"
        )
        or {}
    )

    next_result = (
        result
        if result is not None
        else current.get(
            "result"
        )
        or {}
    )

    lease_owner = (
        worker
        if next_status == "running"
        else None
    )

    lease_expires_at = (
        _lease_expiry_iso(
            lease_seconds
        )
        if next_status == "running"
        else None
    )

    next_resume_automatically = bool(
        resume_automatically
    ) and next_status == "paused"

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE research_jobs
            SET updated_at = ?,
                status = ?,
                checkpoint_json = ?,
                result_json = ?,
                error_text = ?,
                lease_owner = ?,
                lease_expires_at = ?,
                resume_automatically = ?
            WHERE id = ?
              AND status = 'running'
              AND lease_owner = ?
            """,
            (
                _now_iso(),
                next_status,
                _encode_json(
                    next_checkpoint
                ),
                _encode_json(
                    next_result
                ),
                (
                    str(
                        error
                    )
                    if error is not None
                    else current.get(
                        "error"
                    )
                ),
                lease_owner,
                lease_expires_at,
                1
                if next_resume_automatically
                else 0,
                job_value,
                worker,
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "research job lease changed before the update completed"
            )

    updated = get_research_job(
        job_value
    )

    if updated is None:
        raise RuntimeError(
            "research job update could not be read back"
        )

    return updated