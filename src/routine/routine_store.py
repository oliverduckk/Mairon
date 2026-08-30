import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


# --------------------------------------------------
# Paths / timezone
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "mairon.db"
)

TIMEZONE_NAME = "Australia/Sydney"

LOCAL_TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)


# --------------------------------------------------
# Database connection
# --------------------------------------------------

def get_connection():
    """
    Open Mairon's local SQLite database.

    Routine information stays in the same local database
    as Mairon's other persistent state.
    """

    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


# --------------------------------------------------
# Database setup
# --------------------------------------------------

def initialise_routine_store():
    """
    Create Mairon's routine/context tables if required.
    """

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS routine_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                day_of_week INTEGER NOT NULL,
                start_time TEXT,
                end_time TEXT,
                details_json TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, category, day_of_week)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS routine_preferences (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_context (
                context_date TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(context_date, key)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                details_json TEXT,
                expires_at TEXT NOT NULL
            )
            """
        )

        connection.commit()

    return {
        "success": True,
        "message": (
            "Routine store initialised."
        )
    }


# --------------------------------------------------
# JSON helpers
# --------------------------------------------------

def encode_value(
    value
):
    return json.dumps(
        value,
        ensure_ascii=False
    )


def decode_value(
    value
):
    if value is None:
        return None

    try:
        return json.loads(
            value
        )

    except Exception:
        return value


# --------------------------------------------------
# Routine rules
# --------------------------------------------------

def set_routine_rule(
    name,
    category,
    days_of_week,
    start_time=None,
    end_time=None,
    details=None
):
    """
    Create or update a repeating weekly routine.

    days_of_week uses Python weekday numbers:

        Monday    = 0
        Tuesday   = 1
        Wednesday = 2
        Thursday  = 3
        Friday    = 4
        Saturday  = 5
        Sunday    = 6
    """

    if not name:
        return {
            "success": False,
            "message": (
                "Routine name is required."
            )
        }

    if not category:
        return {
            "success": False,
            "message": (
                "Routine category is required."
            )
        }

    if not isinstance(
        days_of_week,
        list
    ):
        return {
            "success": False,
            "message": (
                "days_of_week must be a list."
            )
        }

    cleaned_days = []

    for day in days_of_week:
        try:
            day = int(day)

        except Exception:
            return {
                "success": False,
                "message": (
                    f"Invalid weekday value: {day}"
                )
            }

        if day < 0 or day > 6:
            return {
                "success": False,
                "message": (
                    f"Weekday must be between 0 and 6: {day}"
                )
            }

        if day not in cleaned_days:
            cleaned_days.append(
                day
            )

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    details_json = encode_value(
        details or {}
    )

    with get_connection() as connection:

        for day in cleaned_days:

            connection.execute(
                """
                INSERT INTO routine_rules (
                    name,
                    category,
                    day_of_week,
                    start_time,
                    end_time,
                    details_json,
                    active,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)

                ON CONFLICT(
                    name,
                    category,
                    day_of_week
                )

                DO UPDATE SET
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    details_json = excluded.details_json,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    name,
                    category,
                    day,
                    start_time,
                    end_time,
                    details_json,
                    now,
                    now
                )
            )

        connection.commit()

    return {
        "success": True,
        "message": (
            f"Routine '{name}' saved."
        ),
        "days_of_week": cleaned_days
    }


def get_routine_for_date(
    date_string
):
    """
    Get repeating routine rules that apply to a date.

    date_string:
        YYYY-MM-DD
    """

    try:
        target_date = datetime.strptime(
            date_string,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        return {
            "success": False,
            "message": (
                "Date must use YYYY-MM-DD format."
            )
        }

    weekday = target_date.weekday()

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                id,
                name,
                category,
                day_of_week,
                start_time,
                end_time,
                details_json
            FROM routine_rules
            WHERE
                day_of_week = ?
                AND active = 1
            ORDER BY
                start_time IS NULL,
                start_time,
                id
            """,
            (
                weekday,
            )
        ).fetchall()

    rules = []

    for row in rows:

        rules.append({
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "day_of_week": row["day_of_week"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "details": decode_value(
                row["details_json"]
            )
        })

    return {
        "success": True,
        "date": date_string,
        "weekday": target_date.strftime(
            "%A"
        ),
        "rules": rules
    }


def list_routine_rules():
    """
    Return all active repeating routine rules.
    """

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                id,
                name,
                category,
                day_of_week,
                start_time,
                end_time,
                details_json
            FROM routine_rules
            WHERE active = 1
            ORDER BY
                day_of_week,
                start_time IS NULL,
                start_time,
                id
            """
        ).fetchall()

    rules = []

    for row in rows:

        rules.append({
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "day_of_week": row["day_of_week"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "details": decode_value(
                row["details_json"]
            )
        })

    return {
        "success": True,
        "rules": rules
    }


# --------------------------------------------------
# Routine preferences
# --------------------------------------------------

def set_routine_preference(
    key,
    value
):
    """
    Save a persistent routine preference.

    Examples:

        office_wake_time = "06:30"
        wfh_wake_time = "08:00"
    """

    if not key:
        return {
            "success": False,
            "message": (
                "Preference key is required."
            )
        }

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO routine_preferences (
                key,
                value_json,
                updated_at
            )
            VALUES (?, ?, ?)

            ON CONFLICT(key)

            DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (
                key,
                encode_value(
                    value
                ),
                now
            )
        )

        connection.commit()

    return {
        "success": True,
        "key": key,
        "value": value
    }


def get_routine_preference(
    key,
    default=None
):
    """
    Read one persistent routine preference.
    """

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT value_json
            FROM routine_preferences
            WHERE key = ?
            """,
            (
                key,
            )
        ).fetchone()

    if not row:
        return {
            "success": True,
            "key": key,
            "value": default,
            "found": False
        }

    return {
        "success": True,
        "key": key,
        "value": decode_value(
            row["value_json"]
        ),
        "found": True
    }


def list_routine_preferences():
    """
    Return all saved routine preferences.
    """

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                key,
                value_json,
                updated_at
            FROM routine_preferences
            ORDER BY key
            """
        ).fetchall()

    preferences = {}

    for row in rows:

        preferences[
            row["key"]
        ] = decode_value(
            row["value_json"]
        )

    return {
        "success": True,
        "preferences": preferences
    }


# --------------------------------------------------
# Daily context
# --------------------------------------------------

def set_daily_context(
    date_string,
    key,
    value
):
    """
    Save a one-day fact or override.

    Examples:

        work_location = "office"
        work_location = "home"
        wake_time = "06:30"
        skip_gym = True

    This does NOT modify the repeating routine.
    """

    try:
        datetime.strptime(
            date_string,
            "%Y-%m-%d"
        )

    except ValueError:
        return {
            "success": False,
            "message": (
                "Date must use YYYY-MM-DD format."
            )
        }

    if not key:
        return {
            "success": False,
            "message": (
                "Daily context key is required."
            )
        }

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO daily_context (
                context_date,
                key,
                value_json,
                updated_at
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(
                context_date,
                key
            )

            DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (
                date_string,
                key,
                encode_value(
                    value
                ),
                now
            )
        )

        connection.commit()

    return {
        "success": True,
        "date": date_string,
        "key": key,
        "value": value
    }


def get_daily_context(
    date_string
):
    """
    Return all one-day context for a date.
    """

    try:
        datetime.strptime(
            date_string,
            "%Y-%m-%d"
        )

    except ValueError:
        return {
            "success": False,
            "message": (
                "Date must use YYYY-MM-DD format."
            )
        }

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                key,
                value_json,
                updated_at
            FROM daily_context
            WHERE context_date = ?
            ORDER BY key
            """,
            (
                date_string,
            )
        ).fetchall()

    context = {}

    for row in rows:

        context[
            row["key"]
        ] = decode_value(
            row["value_json"]
        )

    return {
        "success": True,
        "date": date_string,
        "context": context
    }


def clear_daily_context(
    date_string,
    key=None
):
    """
    Remove a one-day override.

    If key is omitted, remove all context for that day.
    """

    with get_connection() as connection:

        if key:

            cursor = connection.execute(
                """
                DELETE FROM daily_context
                WHERE
                    context_date = ?
                    AND key = ?
                """,
                (
                    date_string,
                    key
                )
            )

        else:

            cursor = connection.execute(
                """
                DELETE FROM daily_context
                WHERE context_date = ?
                """,
                (
                    date_string,
                )
            )

        connection.commit()

    return {
        "success": True,
        "deleted": cursor.rowcount
    }


# --------------------------------------------------
# Recent context
# --------------------------------------------------

def record_recent_context(
    event_type,
    details=None,
    occurred_at=None,
    retention_hours=36
):
    """
    Record temporary context that is useful for the near
    future but should not become permanent memory.

    Examples:

        bedtime
        pc_shutdown
        lights_off
        workout_completed

    Events automatically expire.
    """

    if not event_type:
        return {
            "success": False,
            "message": (
                "Recent context event type is required."
            )
        }

    if occurred_at is None:

        occurred_at_dt = datetime.now(
            LOCAL_TIMEZONE
        )

    else:

        try:
            occurred_at_dt = datetime.fromisoformat(
                occurred_at
            )

            if occurred_at_dt.tzinfo is None:
                occurred_at_dt = (
                    occurred_at_dt.replace(
                        tzinfo=LOCAL_TIMEZONE
                    )
                )

        except ValueError:
            return {
                "success": False,
                "message": (
                    "occurred_at must be ISO 8601."
                )
            }

    retention_hours = max(
        1,
        min(
            int(retention_hours),
            168
        )
    )

    expires_at_dt = (
        occurred_at_dt
        + timedelta(
            hours=retention_hours
        )
    )

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO recent_context (
                event_type,
                occurred_at,
                details_json,
                expires_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                event_type,
                occurred_at_dt.isoformat(),
                encode_value(
                    details or {}
                ),
                expires_at_dt.isoformat()
            )
        )

        connection.commit()

    return {
        "success": True,
        "event_type": event_type,
        "occurred_at": (
            occurred_at_dt.isoformat()
        ),
        "expires_at": (
            expires_at_dt.isoformat()
        )
    }


def get_recent_context():
    """
    Return all currently non-expired recent context.
    """

    now = datetime.now(
        LOCAL_TIMEZONE
    )

    with get_connection() as connection:

        connection.execute(
            """
            DELETE FROM recent_context
            WHERE expires_at <= ?
            """,
            (
                now.isoformat(),
            )
        )

        rows = connection.execute(
            """
            SELECT
                id,
                event_type,
                occurred_at,
                details_json,
                expires_at
            FROM recent_context
            WHERE expires_at > ?
            ORDER BY occurred_at DESC
            """,
            (
                now.isoformat(),
            )
        ).fetchall()

        connection.commit()

    events = []

    for row in rows:

        events.append({
            "id": row["id"],
            "event_type": row["event_type"],
            "occurred_at": row["occurred_at"],
            "details": decode_value(
                row["details_json"]
            ),
            "expires_at": row["expires_at"]
        })

    return {
        "success": True,
        "events": events
    }


# --------------------------------------------------
# Combined day view
# --------------------------------------------------

def get_day_context(
    date_string
):
    """
    Return Mairon's current understanding of one day.

    This deliberately keeps repeating routine and daily
    overrides separate so callers can reason about both.
    """

    routine = get_routine_for_date(
        date_string
    )

    if not routine.get(
        "success"
    ):
        return routine

    daily = get_daily_context(
        date_string
    )

    if not daily.get(
        "success"
    ):
        return daily

    return {
        "success": True,
        "date": date_string,
        "weekday": routine["weekday"],
        "routine": routine["rules"],
        "daily_context": daily["context"]
    }


# --------------------------------------------------
# Standalone check
# --------------------------------------------------

if __name__ == "__main__":

    result = initialise_routine_store()

    print(
        json.dumps(
            result,
            indent=2
        )
    )

    print()

    print(
        json.dumps(
            list_routine_rules(),
            indent=2
        )
    )

    print()

    print(
        json.dumps(
            list_routine_preferences(),
            indent=2
        )
    )