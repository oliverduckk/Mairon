from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo
import os


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

PRIVATE_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "private"
)

CHAT_SESSION_DB_PATH = (
    PRIVATE_DATA_DIR
    / "chat_sessions.db"
)

MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney",
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)

DEFAULT_SESSION_TITLE = "New Chat"
MAX_SESSION_TITLE_LENGTH = 44


def _now_iso() -> str:
    return datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()


def new_session_id() -> str:
    return uuid4().hex


def _normalise_db_path(
    db_path=None,
) -> Path:
    return Path(
        db_path
        or CHAT_SESSION_DB_PATH
    )


def _connect(
    db_path=None,
):
    path = _normalise_db_path(
        db_path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        path
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


@contextmanager
def _connection(
    db_path=None,
):
    connection = _connect(
        db_path
    )

    try:
        with connection:
            yield connection

    finally:
        connection.close()


def initialise_chat_sessions(
    db_path=None,
) -> None:
    with _connection(
        db_path
    ) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                title_origin TEXT NOT NULL DEFAULT 'auto',
                core_state_json TEXT
            )
            """
        )

        columns = {
            str(
                row[
                    "name"
                ]
            )
            for row in connection.execute(
                "PRAGMA table_info(chat_sessions)"
            ).fetchall()
        }

        if "title_origin" not in columns:
            connection.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN title_origin TEXT NOT NULL DEFAULT 'auto'
                """
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                channel TEXT NOT NULL,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL,
                response_ms REAL,
                FOREIGN KEY(session_id)
                    REFERENCES chat_sessions(session_id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_chat_sessions_updated
            ON chat_sessions(updated_at DESC)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_chat_turns_session
            ON chat_turns(session_id, id)
            """
        )


def _clean_title_text(
    value: str,
) -> str:
    text = " ".join(
        str(
            value
            or ""
        ).strip().split()
    )

    text = text.strip(
        " .,!?:;-"
    )

    return text


def _title_case_compact(
    value: str,
) -> str:
    small_words = {
        "a",
        "an",
        "and",
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }

    words = _clean_title_text(
        value
    ).split()

    output = []

    for index, word in enumerate(
        words
    ):
        if (
            index > 0
            and word.lower()
            in small_words
        ):
            output.append(
                word.lower()
            )
        else:
            output.append(
                (
                    word[
                        :1
                    ].upper()
                    + word[
                        1:
                    ]
                )
            )

    return " ".join(
        output
    )


def derive_session_title(
    user_text: str,
    *,
    core_state=None,
) -> str:
    """
    Build a compact UX title from Core-owned turn semantics when available.

    This is intentionally deterministic. Chat naming is presentation metadata,
    but it should still prefer known intent/subject over blindly copying the
    opening characters of the user's first message.
    """

    user_value = _clean_title_text(
        user_text
    )

    active_intent = str(
        getattr(
            core_state,
            "active_intent",
            "",
        )
        or ""
    ).strip()

    active_subject = str(
        getattr(
            core_state,
            "active_subject",
            "",
        )
        or ""
    ).strip()

    active_entities = getattr(
        core_state,
        "active_entities",
        {},
    )

    if not isinstance(
        active_entities,
        dict,
    ):
        active_entities = {}

    title = ""

    if active_intent == "calculate_arithmetic":
        title = "Arithmetic Calculation"

    elif active_intent == "launch_application":
        application = str(
            active_entities.get(
                "application",
                "",
            )
            or active_subject
        ).strip()

        if application:
            title = (
                "Open "
                + _title_case_compact(
                    application
                )
            )

    elif active_intent in {
        "find_local_file",
        "open_local_file",
    }:
        query = str(
            active_entities.get(
                "file_query",
                "",
            )
            or active_subject
        ).strip()

        if query:
            title = (
                "Find "
                + _title_case_compact(
                    query
                )
            )

    elif active_intent in {
        "browser_search",
        "open_browser_site",
    }:
        query = str(
            active_entities.get(
                "query",
                "",
            )
            or active_subject
        ).strip()

        if query:
            title = _title_case_compact(
                query
            )

    elif active_subject:
        title = _title_case_compact(
            active_subject
        )

    if not title:
        title = _title_case_compact(
            user_value
        )

    if not title:
        return DEFAULT_SESSION_TITLE

    if len(
        title
    ) <= MAX_SESSION_TITLE_LENGTH:
        return title

    return (
        title[
            : MAX_SESSION_TITLE_LENGTH - 1
        ].rstrip()
        + "…"
    )


def snapshot_conversation_state(
    state,
) -> dict[str, Any]:
    """
    Serialize only Core-owned ConversationState data.

    This is a state snapshot, not assistant prose and not a replay log.
    """

    if state is None:
        return {}

    if is_dataclass(
        state
    ):
        raw = asdict(
            state
        )

    else:
        raw = dict(
            getattr(
                state,
                "__dict__",
                {},
            )
        )

    # JSON round-trip guarantees the stored snapshot cannot contain arbitrary
    # Python objects. Rare non-JSON leaves degrade to strings rather than code.
    return json.loads(
        json.dumps(
            raw,
            default=str,
        )
    )


def restore_conversation_state(
    state_class,
    snapshot: Optional[
        dict[str, Any]
    ],
):
    snapshot_value = (
        snapshot
        if isinstance(
            snapshot,
            dict,
        )
        else {}
    )

    allowed = {
        item.name
        for item in fields(
            state_class
        )
    }

    kwargs = {
        key: value
        for key, value in (
            snapshot_value.items()
        )
        if key in allowed
    }

    return state_class(
        **kwargs
    )


def ensure_session(
    session_id: str,
    *,
    title: str = DEFAULT_SESSION_TITLE,
    core_state=None,
    db_path=None,
) -> None:
    session_value = str(
        session_id
        or ""
    ).strip()

    if not session_value:
        raise ValueError(
            "session_id is required"
        )

    initialise_chat_sessions(
        db_path
    )

    now = _now_iso()

    core_json = None

    if core_state is not None:
        core_json = json.dumps(
            snapshot_conversation_state(
                core_state
            )
        )

    with _connection(
        db_path
    ) as connection:
        connection.execute(
            """
            INSERT INTO chat_sessions (
                session_id,
                created_at,
                updated_at,
                title,
                title_origin,
                core_state_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO NOTHING
            """,
            (
                session_value,
                now,
                now,
                str(
                    title
                    or DEFAULT_SESSION_TITLE
                ),
                "auto",
                core_json,
            ),
        )


def record_chat_turn(
    *,
    session_id: str,
    user_text: str,
    assistant_text: str,
    channel: str = "text",
    response_seconds=None,
    core_state=None,
    db_path=None,
) -> int:
    user_value = str(
        user_text
        or ""
    ).strip()

    assistant_value = str(
        assistant_text
        or ""
    ).strip()

    if (
        not user_value
        or not assistant_value
    ):
        raise ValueError(
            "completed chat turns require user and assistant text"
        )

    session_value = str(
        session_id
        or ""
    ).strip()

    ensure_session(
        session_value,
        db_path=db_path,
    )

    response_ms = None

    if response_seconds is not None:
        try:
            response_ms = (
                max(
                    0.0,
                    float(
                        response_seconds
                    ),
                )
                * 1000.0
            )

        except (
            TypeError,
            ValueError,
        ):
            response_ms = None

    now = _now_iso()

    core_json = json.dumps(
        snapshot_conversation_state(
            core_state
        )
    )

    with _connection(
        db_path
    ) as connection:
        existing = connection.execute(
            """
            SELECT
                title,
                title_origin
            FROM chat_sessions
            WHERE session_id = ?
            """,
            (
                session_value,
            ),
        ).fetchone()

        current_title = (
            str(
                existing[
                    "title"
                ]
            )
            if existing
            else DEFAULT_SESSION_TITLE
        )

        title_origin = (
            str(
                existing[
                    "title_origin"
                ]
            )
            if existing
            else "auto"
        )

        # Automatic naming happens once, on the first completed turn.
        # Later messages must never continuously rename the conversation.
        # Manual rename remains authoritative forever unless explicitly changed.
        if title_origin == "manual":
            next_title = current_title

        elif current_title == DEFAULT_SESSION_TITLE:
            next_title = derive_session_title(
                user_value,
                core_state=core_state,
            )

        else:
            next_title = current_title

        cursor = connection.execute(
            """
            INSERT INTO chat_turns (
                session_id,
                created_at,
                channel,
                user_text,
                assistant_text,
                response_ms
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_value,
                now,
                str(
                    channel
                    or "text"
                ),
                user_value,
                assistant_value,
                response_ms,
            ),
        )

        connection.execute(
            """
            UPDATE chat_sessions
            SET updated_at = ?,
                title = ?,
                core_state_json = ?
            WHERE session_id = ?
            """,
            (
                now,
                next_title,
                core_json,
                session_value,
            ),
        )

        return int(
            cursor.lastrowid
        )


def apply_semantic_chat_title(
    session_id: str,
    title: str,
    *,
    db_path=None,
) -> bool:
    """
    Replace the one-time automatic fallback title with a semantic model title.

    Manual titles are never overwritten. Once a semantic title is applied, the
    title is frozen exactly like any other automatic first-turn title.
    """

    session_value = str(
        session_id
        or ""
    ).strip()

    title_value = _clean_title_text(
        title
    )

    if not session_value:
        return False

    if not title_value:
        return False

    if len(
        title_value
    ) > MAX_SESSION_TITLE_LENGTH:
        title_value = (
            title_value[
                : MAX_SESSION_TITLE_LENGTH - 1
            ].rstrip()
            + "…"
        )

    initialise_chat_sessions(
        db_path
    )

    with _connection(
        db_path
    ) as connection:
        cursor = connection.execute(
            """
            UPDATE chat_sessions
            SET title = ?,
                title_origin = 'semantic',
                updated_at = ?
            WHERE session_id = ?
              AND title_origin = 'auto'
            """,
            (
                title_value,
                _now_iso(),
                session_value,
            ),
        )

        return (
            cursor.rowcount
            == 1
        )


def rename_chat_session(
    session_id: str,
    title: str,
    *,
    db_path=None,
) -> bool:
    session_value = str(
        session_id
        or ""
    ).strip()

    title_value = _clean_title_text(
        title
    )

    if not session_value:
        return False

    if not title_value:
        raise ValueError(
            "Chat title cannot be empty."
        )

    if len(
        title_value
    ) > MAX_SESSION_TITLE_LENGTH:
        raise ValueError(
            f"Chat title must be {MAX_SESSION_TITLE_LENGTH} characters or fewer."
        )

    initialise_chat_sessions(
        db_path
    )

    with _connection(
        db_path
    ) as connection:
        cursor = connection.execute(
            """
            UPDATE chat_sessions
            SET title = ?,
                title_origin = 'manual',
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                title_value,
                _now_iso(),
                session_value,
            ),
        )

        return (
            cursor.rowcount
            == 1
        )


def delete_chat_session(
    session_id: str,
    *,
    db_path=None,
) -> bool:
    session_value = str(
        session_id
        or ""
    ).strip()

    if not session_value:
        return False

    initialise_chat_sessions(
        db_path
    )

    with _connection(
        db_path
    ) as connection:
        connection.execute(
            """
            DELETE FROM chat_turns
            WHERE session_id = ?
            """,
            (
                session_value,
            ),
        )

        cursor = connection.execute(
            """
            DELETE FROM chat_sessions
            WHERE session_id = ?
            """,
            (
                session_value,
            ),
        )

        return (
            cursor.rowcount
            == 1
        )


def _escape_like_value(
    value: str,
) -> str:
    """
    Escape SQLite LIKE wildcard characters so chat-history search behaves
    like a literal substring search rather than exposing SQL pattern syntax.
    """

    return (
        str(
            value
            or ""
        )
        .replace(
            "\\",
            "\\\\",
        )
        .replace(
            "%",
            "\\%",
        )
        .replace(
            "_",
            "\\_",
        )
    )


def list_chat_sessions(
    *,
    limit: int = 12,
    query: str | None = None,
    db_path=None,
) -> list[dict[str, Any]]:
    """
    Return recent saved chat sessions, optionally filtering by local history.

    Search is entirely local and matches the persisted title plus user and
    assistant transcript text. A query never leaves the machine.
    """

    initialise_chat_sessions(
        db_path
    )

    limit_value = max(
        1,
        min(
            100,
            int(
                limit
            ),
        ),
    )

    query_value = " ".join(
        str(
            query
            or ""
        ).split()
    ).strip()

    where_sql = ""
    parameters: list[Any] = []

    if query_value:
        like_value = (
            "%"
            + _escape_like_value(
                query_value
            )
            + "%"
        )

        where_sql = """
            WHERE (
                s.title LIKE ? ESCAPE '\\' COLLATE NOCASE
                OR EXISTS (
                    SELECT 1
                    FROM chat_turns AS search_turn
                    WHERE search_turn.session_id = s.session_id
                      AND (
                          search_turn.user_text LIKE ? ESCAPE '\\' COLLATE NOCASE
                          OR search_turn.assistant_text LIKE ? ESCAPE '\\' COLLATE NOCASE
                      )
                )
            )
        """

        parameters.extend([
            like_value,
            like_value,
            like_value,
        ])

    parameters.append(
        limit_value
    )

    with _connection(
        db_path
    ) as connection:
        rows = connection.execute(
            f"""
            SELECT
                s.session_id,
                s.created_at,
                s.updated_at,
                s.title,
                s.title_origin,
                COUNT(t.id) AS turn_count
            FROM chat_sessions AS s
            LEFT JOIN chat_turns AS t
                ON t.session_id = s.session_id
            {where_sql}
            GROUP BY s.session_id
            HAVING COUNT(t.id) > 0
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()

    return [
        {
            "session_id": str(
                row[
                    "session_id"
                ]
            ),
            "created_at": str(
                row[
                    "created_at"
                ]
            ),
            "updated_at": str(
                row[
                    "updated_at"
                ]
            ),
            "title": str(
                row[
                    "title"
                ]
            ),
            "title_origin": str(
                row[
                    "title_origin"
                ]
            ),
            "turn_count": int(
                row[
                    "turn_count"
                ]
                or 0
            ),
        }
        for row in rows
    ]


def load_chat_session(
    session_id: str,
    *,
    db_path=None,
) -> Optional[
    dict[str, Any]
]:
    initialise_chat_sessions(
        db_path
    )

    session_value = str(
        session_id
        or ""
    ).strip()

    if not session_value:
        return None

    with _connection(
        db_path
    ) as connection:
        session_row = connection.execute(
            """
            SELECT
                session_id,
                created_at,
                updated_at,
                title,
                title_origin,
                core_state_json
            FROM chat_sessions
            WHERE session_id = ?
            """,
            (
                session_value,
            ),
        ).fetchone()

        if session_row is None:
            return None

        turn_rows = connection.execute(
            """
            SELECT
                id,
                created_at,
                channel,
                user_text,
                assistant_text,
                response_ms
            FROM chat_turns
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (
                session_value,
            ),
        ).fetchall()

    snapshot = {}

    raw_snapshot = session_row[
        "core_state_json"
    ]

    if raw_snapshot:
        try:
            candidate = json.loads(
                raw_snapshot
            )

            if isinstance(
                candidate,
                dict,
            ):
                snapshot = candidate

        except Exception:
            snapshot = {}

    return {
        "session_id": str(
            session_row[
                "session_id"
            ]
        ),
        "created_at": str(
            session_row[
                "created_at"
            ]
        ),
        "updated_at": str(
            session_row[
                "updated_at"
            ]
        ),
        "title": str(
            session_row[
                "title"
            ]
        ),
        "title_origin": str(
            session_row[
                "title_origin"
            ]
        ),
        "core_state": snapshot,
        "turns": [
            {
                "id": int(
                    row[
                        "id"
                    ]
                ),
                "created_at": str(
                    row[
                        "created_at"
                    ]
                ),
                "channel": str(
                    row[
                        "channel"
                    ]
                ),
                "user_text": str(
                    row[
                        "user_text"
                    ]
                ),
                "assistant_text": str(
                    row[
                        "assistant_text"
                    ]
                ),
                "response_ms": (
                    float(
                        row[
                            "response_ms"
                        ]
                    )
                    if row[
                        "response_ms"
                    ]
                    is not None
                    else None
                ),
            }
            for row in turn_rows
        ],
    }
