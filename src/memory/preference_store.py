import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from continuity.conversation_journal import (
    load_conversation_turns,
    search_relevant_turns,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "mairon.db"


DOMAIN_ALIASES = {
    "manga": "manga",
    "mangas": "manga",
    "anime": "anime",
    "animes": "anime",
    "book": "book",
    "books": "book",
    "novel": "novel",
    "novels": "novel",
    "game": "game",
    "games": "game",
    "movie": "movie",
    "movies": "movie",
    "film": "movie",
    "films": "movie",
    "show": "show",
    "shows": "show",
    "series": "series",
    "artist": "artist",
    "artists": "artist",
    "album": "album",
    "albums": "album",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

FILLER_PREFIX_RE = re.compile(
    r"^(?:h+m+|h+|umm+|uh+|well+|yeah+|yep+|honestly|probably|definitely|"
    r"for me|mine(?:\s+would\s+be)?|i(?:'d|\s+would)\s+(?:say|go\s+with))\b[\s,:-]*",
    flags=re.IGNORECASE,
)


def _now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


@contextmanager
def _connect():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def initialise_preference_store():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preference_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source_text TEXT,
                source_kind TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(domain, preference_key)
            )
            """
        )


def _normalise_domain(value):
    token = str(
        value
        or ""
    ).strip().lower()

    return DOMAIN_ALIASES.get(
        token,
        token,
    )


def _clean_ranked_domain_phrase(
    value,
):
    domain = re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ).strip().lower(),
    )

    domain = re.sub(
        r"\s+(?:of all time|right now|currently|today|overall)$",
        "",
        domain,
        flags=re.IGNORECASE,
    ).strip()

    # Recall questions may place a copula AFTER the ranked category:
    # "What did I say my top 3 manga were?"
    # The copula belongs to the question grammar, not the preference domain.
    domain = re.sub(
        r"\s+(?:(?:were|are|was|is)(?:\s+again)?|again)$",
        "",
        domain,
        flags=re.IGNORECASE,
    ).strip()

    words = domain.split()

    if not words or len(words) > 8:
        return None

    return _normalise_domain(
        domain
    )


def _parse_count_token(value):
    token = str(
        value
        or ""
    ).strip().lower()

    if token.isdigit():
        return int(
            token
        )

    return NUMBER_WORDS.get(
        token
    )


def set_user_preference(
    domain,
    preference_key,
    value,
    source_text=None,
    source_kind="user_explicit_preference",
):
    initialise_preference_store()

    domain_value = _normalise_domain(
        domain
    )

    key_value = str(
        preference_key
        or ""
    ).strip().lower()

    if not domain_value or not key_value:
        raise ValueError(
            "domain and preference_key are required"
        )

    payload = json.dumps(
        value,
        ensure_ascii=False,
    )

    now = _now_iso()

    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT id, value_json
            FROM user_preference_state
            WHERE domain = ?
              AND preference_key = ?
            """,
            (
                domain_value,
                key_value,
            ),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO user_preference_state (
                    domain,
                    preference_key,
                    value_json,
                    source_text,
                    source_kind,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    domain_value,
                    key_value,
                    payload,
                    str(
                        source_text
                        or ""
                    ).strip(),
                    str(
                        source_kind
                        or "user_explicit_preference"
                    ).strip(),
                    now,
                    now,
                ),
            )

            return {
                "changed": True,
                "created": True,
                "domain": domain_value,
                "preference_key": key_value,
                "value": value,
            }

        changed = (
            str(
                existing["value_json"]
            )
            != payload
        )

        connection.execute(
            """
            UPDATE user_preference_state
            SET value_json = ?,
                source_text = ?,
                source_kind = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                payload,
                str(
                    source_text
                    or ""
                ).strip(),
                str(
                    source_kind
                    or "user_explicit_preference"
                ).strip(),
                now,
                existing["id"],
            ),
        )

    return {
        "changed": changed,
        "created": False,
        "domain": domain_value,
        "preference_key": key_value,
        "value": value,
    }


def get_user_preference(
    domain,
    preference_key,
):
    initialise_preference_store()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT domain,
                   preference_key,
                   value_json,
                   source_text,
                   source_kind,
                   created_at,
                   updated_at
            FROM user_preference_state
            WHERE domain = ?
              AND preference_key = ?
            """,
            (
                _normalise_domain(
                    domain
                ),
                str(
                    preference_key
                    or ""
                ).strip().lower(),
            ),
        ).fetchone()

    if row is None:
        return None

    return {
        "domain": row["domain"],
        "preference_key": row["preference_key"],
        "value": json.loads(
            row["value_json"]
        ),
        "source_text": row["source_text"],
        "source_kind": row["source_kind"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_user_preferences():
    initialise_preference_store()

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT domain,
                   preference_key,
                   value_json,
                   source_text,
                   source_kind,
                   created_at,
                   updated_at
            FROM user_preference_state
            ORDER BY domain, preference_key
            """
        ).fetchall()

    return [
        {
            "domain": row["domain"],
            "preference_key": row["preference_key"],
            "value": json.loads(
                row["value_json"]
            ),
            "source_text": row["source_text"],
            "source_kind": row["source_kind"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def detect_user_ranked_preference_query(text):
    value = str(
        text
        or ""
    ).strip()

    match = re.search(
        r"\bmy\s+top\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?P<domain>[a-zA-Z][a-zA-Z0-9'&\- ]{0,80}?)(?=[?.!,]|$)",
        value,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    count = _parse_count_token(
        match.group(
            "count"
        )
    )

    domain = _clean_ranked_domain_phrase(
        match.group(
            "domain"
        )
    )

    if not count or not domain:
        return None

    return {
        "domain": domain,
        "count": count,
        "preference_key": f"top_{count}",
    }


def _clean_item(value):
    item = str(
        value
        or ""
    ).strip()

    item = re.sub(
        r"^[\-–—:;,.\s]+",
        "",
        item,
    )

    previous = None

    while previous != item:
        previous = item
        item = FILLER_PREFIX_RE.sub(
            "",
            item,
        ).strip()

    return item.strip(
        " \t\n\r.,;:!?-–—*_'\""
    )


def _split_ranked_items(
    text,
    expected_count,
):
    value = str(
        text
        or ""
    ).strip()

    parts = re.split(
        r"\s*,\s*|\s+and\s+|\s*&\s*",
        value,
        flags=re.IGNORECASE,
    )

    cleaned = [
        _clean_item(
            part
        )
        for part in parts
    ]

    cleaned = [
        item
        for item in cleaned
        if item
    ]

    if len(
        cleaned
    ) != expected_count:
        return []

    return cleaned


CONTEXTUAL_PREFERENCE_NEW_REQUEST_PATTERN = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"what|why|who|where|when|how|"
    r"can|could|would|should|will|do|does|did|is|are|"
    r"give|build|make|create|write|draft|design|plan|generate|"
    r"show|tell|find|check|search|recommend|suggest|explain|"
    r"summar(?:y|ise|ize)|compare|calculate|help|open|close|"
    r"turn|set|remind|send|move|copy|download|upload"
    r")\b",
    flags=re.IGNORECASE,
)


def _looks_like_contextual_preference_answer(
    user_text,
):
    """
    A contextual preference write is allowed only when the current turn
    actually looks like an answer to the immediately preceding preference
    question.

    This deliberately rejects NEW questions/commands/requests before any
    comma/"and" splitting occurs. Otherwise a request such as:

        "Give me a routine with exercises, sets and reps"

    can accidentally become three preference items merely because it contains
    two separators.
    """

    text = str(
        user_text
        or ""
    ).strip()

    if not text:
        return False

    if "?" in text:
        return False

    if CONTEXTUAL_PREFERENCE_NEW_REQUEST_PATTERN.search(
        text
    ):
        return False

    return True


def _contextual_preference_request(
    previous_assistant_text,
    previous_user_text=None,
):
    previous_assistant = str(
        previous_assistant_text
        or ""
    ).strip()

    if not previous_assistant:
        return None

    # Mairon must have explicitly bounced the preference question back to
    # Oliver. A random list of three titles is not enough to create memory.
    if not re.search(
        r"(?:\byou\s*\?|\bwhat\s+about\s+you\b|"
        r"\bwhat(?:'s|\s+is|\s+are)\s+your\b|"
        r"\byour\s+top\b[^?\n]{0,120}\?)",
        previous_assistant,
        flags=re.IGNORECASE,
    ):
        return None

    previous_user = str(
        previous_user_text
        or ""
    ).strip()

    prior_query = re.search(
        r"\b(?:your|you)\s+(?:current\s+)?top\s+"
        r"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?P<domain>[a-zA-Z][a-zA-Z0-9'&\- ]{0,80}?)(?=[?.!,]|$)",
        previous_user,
        flags=re.IGNORECASE,
    )

    if prior_query:
        count = _parse_count_token(
            prior_query.group(
                "count"
            )
        )

        domain = _clean_ranked_domain_phrase(
            prior_query.group(
                "domain"
            )
        )

        if count and domain:
            return {
                "domain": domain,
                "count": count,
                "preference_key": f"top_{count}",
            }

    # Fallback: sometimes Mairon's answer repeats the full ranked category.
    assistant_query = re.search(
        r"\btop\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?P<domain>[a-zA-Z][a-zA-Z0-9'&\- ]{0,80}?)(?=[?.!,]|$)",
        previous_assistant,
        flags=re.IGNORECASE,
    )

    if not assistant_query:
        return None

    count = _parse_count_token(
        assistant_query.group(
            "count"
        )
    )

    domain = _clean_ranked_domain_phrase(
        assistant_query.group(
            "domain"
        )
    )

    if not count or not domain:
        return None

    return {
        "domain": domain,
        "count": count,
        "preference_key": f"top_{count}",
    }


def _extract_explicit_ranked_preference(
    user_text,
):
    text = str(
        user_text
        or ""
    ).strip()

    explicit_match = re.search(
        r"\bmy\s+top\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?P<domain>[a-zA-Z][a-zA-Z0-9'&\- ]{0,80}?)(?:\s+however)?\s+"
        r"(?:are|is|would\s+be|have\s+to\s+be|has\s+to\s+be)\b\s*[:\-]?\s*(?P<items>.+)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not explicit_match:
        return None

    count = _parse_count_token(
        explicit_match.group(
            "count"
        )
    )

    domain = _clean_ranked_domain_phrase(
        explicit_match.group(
            "domain"
        )
    )

    items = _split_ranked_items(
        explicit_match.group(
            "items"
        ),
        count,
    )

    if not count or not domain or len(items) != count:
        return None

    return {
        "domain": domain,
        "count": count,
        "preference_key": f"top_{count}",
        "items": items,
        "source_text": text,
    }



PREFERENCE_REVISION_CUE_PATTERN = re.compile(
    r"\b(?:actually|nah|nope|instead|rather|definitely|change|changed|"
    r"correction|correcting|new\s+order|make\s+.+\b(?:first|second|third|"
    r"fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b|so\b)",
    flags=re.IGNORECASE,
)


def _active_ranked_preference_revision_request(
    previous_user_text,
):
    """
    Return the immediately active ranked preference being discussed.

    A natural correction such as:
        "Actually ... So A, B and C."
    does not need to restate "my top 3 anime" if the immediately previous
    Oliver turn already asked for that exact Core-owned preference.

    This is a short-lived dialogue referent, not long-term semantic inference.
    """

    request = detect_user_ranked_preference_query(
        previous_user_text
    )

    if not request:
        return None

    stored = get_user_preference(
        request["domain"],
        request["preference_key"],
    )

    if stored is None:
        return None

    return request


def _extract_complete_ranked_revision_items(
    user_text,
    expected_count,
):
    """
    Extract a COMPLETE replacement ranking from a correction turn.

    We intentionally do not infer partial edits here. The authoritative write
    happens only when Oliver supplies all N items again. Candidate extraction
    works from the newest clause/sentence backwards so surrounding correction
    prose cannot become list items.
    """

    text = str(
        user_text
        or ""
    ).strip()

    if not text or not PREFERENCE_REVISION_CUE_PATTERN.search(
        text
    ):
        return []

    candidates = [
        text,
    ]

    # Newest sentence/clause is the most likely complete replacement list:
    # "Actually X is third. So A, B and X."
    pieces = re.split(
        r"(?<=[.!?;])\s+",
        text,
    )

    candidates.extend(
        reversed(
            pieces
        )
    )

    # Also consider explicit discourse-marker suffixes inside one sentence.
    for match in re.finditer(
        r"\b(?:so|instead|rather|new\s+order(?:\s+is)?|make\s+it)\b\s*[:,-]?\s*",
        text,
        flags=re.IGNORECASE,
    ):
        candidates.append(
            text[
                match.end():
            ]
        )

    seen = set()

    for candidate in candidates:
        value = str(
            candidate
            or ""
        ).strip()

        value = re.sub(
            r"^(?:so|actually|nah|nope|instead|rather|then|"
            r"new\s+order(?:\s+is)?)\b[\s,:-]*",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip()

        if not value or value.lower() in seen:
            continue

        seen.add(
            value.lower()
        )

        items = _split_ranked_items(
            value,
            expected_count,
        )

        if len(
            items
        ) == expected_count:
            return items

    return []


def _recover_ranked_preference_from_turns(
    turns,
    request,
    explicit_source_kind,
    contextual_source_kind,
):
    """
    Inspect supplied journal turns for authoritative ranked-preference evidence.

    Evidence hierarchy:
    1. explicit Oliver declaration;
    2. contextual answer immediately following a same-session ranked-preference
       handoff from Mairon.

    The caller controls HOW the turns were retrieved. This separation is
    important: semantic relevance is useful for speed, but structured migration
    must also be able to inspect deterministic history when relevance ranking is
    polluted by newer recall attempts.
    """

    rows = list(
        turns
        or []
    )

    if not rows:
        return None

    candidates = sorted(
        rows,
        key=lambda turn: int(
            turn.get(
                "id",
                0,
            )
            or 0
        ),
        reverse=True,
    )

    # Highest-confidence: explicit user-authored declarations.
    for turn in candidates:
        extracted = (
            _extract_explicit_ranked_preference(
                turn.get(
                    "user_text",
                    "",
                )
            )
        )

        if not extracted:
            continue

        if (
            extracted["domain"]
            != request["domain"]
            or extracted["preference_key"]
            != request["preference_key"]
        ):
            continue

        return set_user_preference(
            domain=extracted["domain"],
            preference_key=extracted["preference_key"],
            value={
                "items": extracted["items"],
            },
            source_text=extracted["source_text"],
            source_kind=explicit_source_kind,
        )

    # Contextual declarations require adjacency WITHIN THE SAME SESSION.
    # Grouping by session prevents globally sorted IDs from accidentally
    # pairing turns across session boundaries.
    sessions = {}

    for turn in rows:
        session_id = str(
            turn.get(
                "session_id",
                "",
            )
            or ""
        )

        sessions.setdefault(
            session_id,
            [],
        ).append(
            turn
        )

    contextual_candidates = []

    for session_id, session_turns in sessions.items():
        ordered = sorted(
            session_turns,
            key=lambda turn: int(
                turn.get(
                    "id",
                    0,
                )
                or 0
            ),
        )

        for index in range(
            1,
            len(ordered),
        ):
            previous = ordered[
                index - 1
            ]

            current = ordered[
                index
            ]

            current_text = str(
                current.get(
                    "user_text",
                    "",
                )
                or ""
            ).strip()

            if not (
                _looks_like_contextual_preference_answer(
                    current_text
                )
            ):
                continue

            contextual_request = (
                _contextual_preference_request(
                    previous_assistant_text=previous.get(
                        "assistant_text",
                        "",
                    ),
                    previous_user_text=previous.get(
                        "user_text",
                        "",
                    ),
                )
            )

            if not contextual_request:
                continue

            if (
                contextual_request["domain"]
                != request["domain"]
                or contextual_request["preference_key"]
                != request["preference_key"]
            ):
                continue

            items = _split_ranked_items(
                current_text,
                contextual_request["count"],
            )

            if len(
                items
            ) != contextual_request["count"]:
                continue

            contextual_candidates.append(
                (
                    int(
                        current.get(
                            "id",
                            0,
                        )
                        or 0
                    ),
                    contextual_request,
                    current_text,
                    items,
                )
            )

    if not contextual_candidates:
        return None

    # If Oliver gave multiple historical rankings, newest valid evidence wins.
    (
        _turn_id,
        contextual_request,
        current_text,
        items,
    ) = max(
        contextual_candidates,
        key=lambda item: item[0],
    )

    return set_user_preference(
        domain=contextual_request["domain"],
        preference_key=contextual_request["preference_key"],
        value={
            "items": items,
        },
        source_text=current_text,
        source_kind=contextual_source_kind,
    )


def recover_user_preference_from_journal(
    user_text,
    limit=12,
):
    request = detect_user_ranked_preference_query(
        user_text
    )

    if not request:
        return None

    # Fast first pass: normal relevance search. This usually brings the
    # preference exchange plus its neighbourhood into a tiny candidate set.
    relevant_turns = search_relevant_turns(
        user_input=user_text,
        limit=limit,
    )

    recovered = _recover_ranked_preference_from_turns(
        turns=relevant_turns,
        request=request,
        explicit_source_kind="conversation_journal_recovery",
        contextual_source_kind="conversation_journal_context_recovery",
    )

    if recovered is not None:
        return recovered

    # Structured-state migration MUST NOT depend on semantic ranking.
    #
    # Repeated failed recall questions can become newer/more relevant anchors
    # and crowd the original preference exchange out of search results. When the
    # first pass yields no valid evidence, inspect actual recorded dialogue
    # deterministically and validate it with the same strict evidence rules.
    historical_turns = load_conversation_turns(
        include_current_session=True,
        newest_first=False,
        limit=None,
    )

    return _recover_ranked_preference_from_turns(
        turns=historical_turns,
        request=request,
        explicit_source_kind="conversation_journal_full_history_recovery",
        contextual_source_kind="conversation_journal_full_history_context_recovery",
    )


def capture_user_preference(
    user_text,
    previous_assistant_text=None,
    previous_user_text=None,
):
    text = str(
        user_text
        or ""
    ).strip()

    if not text:
        return None

    explicit = _extract_explicit_ranked_preference(
        text
    )

    if explicit:
        request = {
            "domain": explicit["domain"],
            "count": explicit["count"],
            "preference_key": explicit["preference_key"],
        }

        item_source = ", ".join(
            explicit["items"]
        )

    else:
        if not _looks_like_contextual_preference_answer(
            text
        ):
            return None

        request = _contextual_preference_request(
            previous_assistant_text,
            previous_user_text=previous_user_text,
        )

        item_source = text

        # If Mairon did not just bounce a preference question back to Oliver,
        # the turn may still be a natural REVISION of an already active typed
        # ranking immediately recalled in the previous Oliver turn.
        if not request:
            request = _active_ranked_preference_revision_request(
                previous_user_text
            )

            if request:
                revision_items = _extract_complete_ranked_revision_items(
                    text,
                    request["count"],
                )

                if not revision_items:
                    return None

                return set_user_preference(
                    domain=request["domain"],
                    preference_key=request["preference_key"],
                    value={
                        "items": revision_items,
                    },
                    source_text=text,
                    source_kind="user_preference_revision",
                )

    if not request:
        return None

    items = _split_ranked_items(
        item_source,
        request["count"],
    )

    if len(
        items
    ) != request["count"]:
        return None

    return set_user_preference(
        domain=request["domain"],
        preference_key=request["preference_key"],
        value={
            "items": items,
        },
        source_text=text,
        source_kind="user_explicit_preference",
    )


def build_user_preference_recall_response(
    user_text,
    user_name="Oliver",
):
    request = detect_user_ranked_preference_query(
        user_text
    )

    if not request:
        return None

    text = str(
        user_text
        or ""
    ).strip().lower()

    # Declarations contain the same "my top N" shape. Only intercept actual
    # questions/recall requests.
    if not re.search(
        r"\b(?:what|which|remind|remember|did\s+i\s+say|were\s+my|are\s+my)\b",
        text,
    ):
        return None

    stored = get_user_preference(
        request["domain"],
        request["preference_key"],
    )

    readable_key = request[
        "preference_key"
    ].replace(
        "_",
        " ",
    )

    if stored is None:
        recovered = recover_user_preference_from_journal(
            user_text
        )

        if recovered is not None:
            stored = get_user_preference(
                request["domain"],
                request["preference_key"],
            )

    if stored is None:
        return (
            f"I don't have a stored {readable_key} {request['domain']} "
            f"ranking for you yet, {user_name}."
        )

    items = list(
        stored.get(
            "value",
            {}
        ).get(
            "items",
            []
        )
    )

    if not items:
        return (
            f"I don't have a usable stored {readable_key} {request['domain']} "
            f"ranking for you yet, {user_name}."
        )

    if len(
        items
    ) == 1:
        item_text = items[0]

    elif len(
        items
    ) == 2:
        item_text = (
            f"{items[0]} and {items[1]}"
        )

    else:
        item_text = (
            ", ".join(
                items[:-1]
            )
            + f", and {items[-1]}"
        )

    return (
        f"Your {readable_key} {request['domain']} are {item_text}."
    )
