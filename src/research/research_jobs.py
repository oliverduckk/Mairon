from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
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
                error_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    with _connect() as connection:
        connection.execute(
            """
            UPDATE research_jobs
            SET updated_at = ?,
                status = ?,
                checkpoint_json = ?,
                result_json = ?,
                error_text = ?
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
