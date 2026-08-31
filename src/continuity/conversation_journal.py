import math
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


# --------------------------------------------------
# Paths / session
# --------------------------------------------------

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

PRIVATE_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "private"
)

JOURNAL_DB_PATH = (
    PRIVATE_DATA_DIR
    / "conversation_journal.db"
)

MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)

CURRENT_SESSION_ID = uuid4().hex


# --------------------------------------------------
# Retrieval configuration
# --------------------------------------------------

MAX_SCAN_TURNS = 2500
DEFAULT_SEARCH_LIMIT = 6
MAX_CONTEXT_TURNS = 8

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been",
    "being", "but", "by", "can", "could", "did", "do",
    "does", "doing", "for", "from", "had", "has", "have",
    "he", "her", "here", "him", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "just", "me", "my",
    "of", "on", "or", "our", "ours", "say", "said", "she",
    "so", "some", "that", "the", "their", "them", "then",
    "there", "these", "they", "this", "those", "to", "too",
    "up", "us", "was", "we", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "would", "you",
    "your", "yours",
}

RECALL_HINTS = [
    "what did you say",
    "what did i say",
    "what were we talking about",
    "what did we talk about",
    "do you remember",
    "remember when",
    "earlier",
    "before",
    "last time",
    "previously",
    "you said",
    "i said",
    "we said",
    "we talked about",
    "we discussed",
]


# --------------------------------------------------
# Database
# --------------------------------------------------

def _now():
    return datetime.now(
        LOCAL_TIMEZONE
    )


def _connect():
    PRIVATE_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        JOURNAL_DB_PATH
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def initialise_journal():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                channel TEXT NOT NULL,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_conversation_turns_created_at
            ON conversation_turns(created_at)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_conversation_turns_session_id
            ON conversation_turns(session_id)
            """
        )


def record_conversation_turn(
    user_text,
    assistant_text,
    channel="text",
):
    """
    Persist one completed user<->Mairon turn locally.

    This journal is continuity/history, not explicit durable fact memory.
    It records what was actually said so future sessions can retrieve
    relevant dialogue without loading the full transcript.
    """

    user_value = str(
        user_text or ""
    ).strip()

    assistant_value = str(
        assistant_text or ""
    ).strip()

    if (
        not user_value
        or not assistant_value
    ):
        return None

    initialise_journal()

    created_at = _now().isoformat()

    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO conversation_turns (
                session_id,
                created_at,
                channel,
                user_text,
                assistant_text
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                CURRENT_SESSION_ID,
                created_at,
                str(channel or "text"),
                user_value,
                assistant_value,
            )
        )

        return cursor.lastrowid


# --------------------------------------------------
# Text processing
# --------------------------------------------------

def _normalise_text(text):
    value = str(
        text or ""
    ).lower()

    value = re.sub(
        r"https?://\S+",
        " ",
        value,
    )

    value = re.sub(
        r"[^a-z0-9'\s]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def _tokens(text):
    return [
        token
        for token in _normalise_text(
            text
        ).split()
        if (
            len(token) >= 2
            and token not in STOPWORDS
        )
    ]


def _query_terms(text):
    tokens = _tokens(
        text
    )

    # Preserve order while removing duplicates.
    return list(
        dict.fromkeys(
            tokens
        )
    )


def _looks_like_recall_request(
    user_input
):
    text = _normalise_text(
        user_input
    )

    return any(
        hint in text
        for hint in RECALL_HINTS
    )


# --------------------------------------------------
# Retrieval
# --------------------------------------------------

def _load_candidate_rows(
    max_scan=MAX_SCAN_TURNS,
    exclude_current_session=True,
):
    initialise_journal()

    query = """
        SELECT
            id,
            session_id,
            created_at,
            channel,
            user_text,
            assistant_text
        FROM conversation_turns
    """

    parameters = []

    if exclude_current_session:
        query += """
            WHERE session_id != ?
        """

        parameters.append(
            CURRENT_SESSION_ID
        )

    query += """
        ORDER BY id DESC
        LIMIT ?
    """

    parameters.append(
        int(max_scan)
    )

    with _connect() as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def _document_frequency(
    rows,
):
    counts = Counter()

    for row in rows:
        unique_terms = set(
            _tokens(
                row["user_text"]
                + " "
                + row["assistant_text"]
            )
        )

        counts.update(
            unique_terms
        )

    return counts


def _score_row(
    row,
    query_terms,
    document_frequency,
    corpus_size,
    newest_id,
    recall_request,
):
    if not query_terms:
        return 0.0

    user_tokens = set(
        _tokens(
            row["user_text"]
        )
    )

    assistant_tokens = set(
        _tokens(
            row["assistant_text"]
        )
    )

    score = 0.0
    matched = 0

    for term in query_terms:
        in_user = (
            term in user_tokens
        )

        in_assistant = (
            term in assistant_tokens
        )

        if not (
            in_user
            or in_assistant
        ):
            continue

        matched += 1

        df = document_frequency.get(
            term,
            0,
        )

        # Rare terms such as "bleach", "yoruichi", "minecraft",
        # etc. matter more than generic recurring vocabulary.
        idf = math.log(
            (
                corpus_size
                + 1
            )
            / (
                df
                + 1
            )
        ) + 1.0

        if in_user:
            score += (
                1.35
                * idf
            )

        if in_assistant:
            score += (
                1.00
                * idf
            )

    if matched == 0:
        return 0.0

    coverage = (
        matched
        / max(
            len(query_terms),
            1,
        )
    )

    score += (
        coverage
        * 2.0
    )

    # Small recency preference, never enough to defeat a much more
    # relevant older turn.
    id_gap = max(
        newest_id
        - row["id"],
        0,
    )

    recency_bonus = (
        1.0
        / (
            1.0
            + (
                id_gap
                / 80.0
            )
        )
    )

    score += (
        0.65
        * recency_bonus
    )

    if recall_request:
        score *= 1.12

    return score


def _fetch_session_neighbourhood(
    session_id,
    anchor_id,
    radius_before=2,
    radius_after=2,
):
    initialise_journal()

    with _connect() as connection:
        anchor = connection.execute(
            """
            SELECT id
            FROM conversation_turns
            WHERE id = ?
              AND session_id = ?
            """,
            (
                anchor_id,
                session_id,
            )
        ).fetchone()

        if anchor is None:
            return []

        before = connection.execute(
            """
            SELECT
                id,
                session_id,
                created_at,
                channel,
                user_text,
                assistant_text
            FROM conversation_turns
            WHERE session_id = ?
              AND id < ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                session_id,
                anchor_id,
                radius_before,
            )
        ).fetchall()

        current = connection.execute(
            """
            SELECT
                id,
                session_id,
                created_at,
                channel,
                user_text,
                assistant_text
            FROM conversation_turns
            WHERE session_id = ?
              AND id = ?
            """,
            (
                session_id,
                anchor_id,
            )
        ).fetchall()

        after = connection.execute(
            """
            SELECT
                id,
                session_id,
                created_at,
                channel,
                user_text,
                assistant_text
            FROM conversation_turns
            WHERE session_id = ?
              AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (
                session_id,
                anchor_id,
                radius_after,
            )
        ).fetchall()

    result = (
        list(reversed(before))
        + list(current)
        + list(after)
    )

    return [
        dict(row)
        for row in result
    ]


def search_relevant_turns(
    user_input,
    limit=DEFAULT_SEARCH_LIMIT,
):
    """
    Retrieve a small relevant slice of PREVIOUS PROCESS SESSIONS.

    Current-process history is intentionally excluded because Qwen
    already receives that conversation normally.
    """

    query_terms = _query_terms(
        user_input
    )

    if not query_terms:
        return []

    rows = _load_candidate_rows(
        exclude_current_session=True
    )

    if not rows:
        return []

    newest_id = max(
        row["id"]
        for row in rows
    )

    document_frequency = (
        _document_frequency(
            rows
        )
    )

    corpus_size = len(
        rows
    )

    recall_request = (
        _looks_like_recall_request(
            user_input
        )
    )

    scored = []

    for row in rows:
        score = _score_row(
            row=row,
            query_terms=query_terms,
            document_frequency=document_frequency,
            corpus_size=corpus_size,
            newest_id=newest_id,
            recall_request=recall_request,
        )

        if score > 0:
            scored.append(
                (
                    score,
                    row,
                )
            )

    scored.sort(
        key=lambda item: (
            item[0],
            item[1]["id"],
        ),
        reverse=True,
    )

    # A low-information match is more likely to confuse Qwen than help.
    threshold = (
        1.35
        if recall_request
        else 1.80
    )

    anchors = [
        row
        for score, row in scored
        if score >= threshold
    ][
        :max(
            1,
            min(
                int(limit),
                3,
            )
        )
    ]

    if not anchors:
        return []

    expanded = {}

    for anchor in anchors:
        neighbourhood = (
            _fetch_session_neighbourhood(
                session_id=anchor[
                    "session_id"
                ],
                anchor_id=anchor[
                    "id"
                ],
            )
        )

        for row in neighbourhood:
            expanded[
                row["id"]
            ] = row

    ordered = sorted(
        expanded.values(),
        key=lambda row: row[
            "id"
        ],
    )

    # Keep the context bounded even if several anchor neighbourhoods
    # overlap across different sessions.
    if len(ordered) > MAX_CONTEXT_TURNS:
        # Prefer turns closest to one of the anchors.
        anchor_ids = {
            row["id"]
            for row in anchors
        }

        ordered.sort(
            key=lambda row: min(
                abs(
                    row["id"]
                    - anchor_id
                )
                for anchor_id in anchor_ids
            )
        )

        ordered = ordered[
            :MAX_CONTEXT_TURNS
        ]

        ordered.sort(
            key=lambda row: row[
                "id"
            ]
        )

    return ordered


# --------------------------------------------------
# Diagnostics
# --------------------------------------------------

def get_journal_path():
    return str(
        JOURNAL_DB_PATH
    )


def get_current_session_id():
    return CURRENT_SESSION_ID


def get_turn_count():
    initialise_journal()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM conversation_turns
            """
        ).fetchone()

    return int(
        row["count"]
    )
