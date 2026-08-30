import json
import os
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

TIMEZONE_NAME = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)


# --------------------------------------------------
# Database connection
# --------------------------------------------------

def get_connection():
    """
    Open Mairon's local SQLite database.
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

def initialise_alarm_store():
    """
    Create Mairon's alarm table if required.

    Alarm records represent intended alarms only.
    Actual sound playback will be attached later when
    Mairon has persistent Pi/audio hardware.
    """

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_date TEXT NOT NULL,
                alarm_time TEXT NOT NULL,
                alarm_type TEXT NOT NULL,
                label TEXT,
                source TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # Only one active conceptual wake alarm is needed
        # for a particular date.
        #
        # Other alarm types can eventually support multiple
        # reminders on the same day.
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                unique_wake_alarm_per_date
            ON alarms(alarm_date)
            WHERE alarm_type = 'wake'
            """
        )

        connection.commit()

    return {
        "success": True,
        "message": (
            "Alarm store initialised."
        )
    }


# --------------------------------------------------
# Validation helpers
# --------------------------------------------------

def validate_date(
    date_string
):
    """
    Validate YYYY-MM-DD.
    """

    try:
        datetime.strptime(
            date_string,
            "%Y-%m-%d"
        )

        return True

    except (TypeError, ValueError):
        return False


def validate_time(
    time_string
):
    """
    Validate HH:MM using 24-hour time.
    """

    try:
        datetime.strptime(
            time_string,
            "%H:%M"
        )

        return True

    except (TypeError, ValueError):
        return False


def encode_value(
    value
):
    return json.dumps(
        value or {},
        ensure_ascii=False
    )


def decode_value(
    value
):
    if not value:
        return {}

    try:
        return json.loads(
            value
        )

    except Exception:
        return {}


def normalise_alarm_row(
    row
):
    """
    Convert one SQLite row into a normal dictionary.
    """

    if not row:
        return None

    return {
        "id": row["id"],
        "alarm_date": row["alarm_date"],
        "alarm_time": row["alarm_time"],
        "alarm_type": row["alarm_type"],
        "label": row["label"],
        "source": row["source"],
        "enabled": bool(
            row["enabled"]
        ),
        "metadata": decode_value(
            row["metadata_json"]
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }


# --------------------------------------------------
# Wake alarms
# --------------------------------------------------

def set_wake_alarm(
    date,
    time,
    label="Wake up",
    source="manual",
    metadata=None
):
    """
    Create or update the wake alarm for one date.

    There can only be one wake alarm per date.

    Examples:

        office routine:
            date = 2026-08-31
            time = 06:30
            source = routine

        explicit override:
            date = 2026-08-31
            time = 07:00
            source = manual
    """

    if not validate_date(
        date
    ):
        return {
            "success": False,
            "message": (
                "Alarm date must use YYYY-MM-DD format."
            )
        }

    if not validate_time(
        time
    ):
        return {
            "success": False,
            "message": (
                "Alarm time must use HH:MM 24-hour format."
            )
        }

    label = (
        label
        or "Wake up"
    ).strip()

    source = (
        source
        or "manual"
    ).strip().lower()

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    metadata_json = encode_value(
        metadata
    )

    with get_connection() as connection:

        existing = connection.execute(
            """
            SELECT id
            FROM alarms
            WHERE
                alarm_date = ?
                AND alarm_type = 'wake'
            """,
            (
                date,
            )
        ).fetchone()

        if existing:

            connection.execute(
                """
                UPDATE alarms
                SET
                    alarm_time = ?,
                    label = ?,
                    source = ?,
                    enabled = 1,
                    metadata_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    time,
                    label,
                    source,
                    metadata_json,
                    now,
                    existing["id"]
                )
            )

            alarm_id = existing[
                "id"
            ]

            operation = "updated"

        else:

            cursor = connection.execute(
                """
                INSERT INTO alarms (
                    alarm_date,
                    alarm_time,
                    alarm_type,
                    label,
                    source,
                    enabled,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, 'wake', ?, ?, 1, ?, ?, ?)
                """,
                (
                    date,
                    time,
                    label,
                    source,
                    metadata_json,
                    now,
                    now
                )
            )

            alarm_id = cursor.lastrowid

            operation = "created"

        connection.commit()

        row = connection.execute(
            """
            SELECT *
            FROM alarms
            WHERE id = ?
            """,
            (
                alarm_id,
            )
        ).fetchone()

    return {
        "success": True,
        "operation": operation,
        "alarm": normalise_alarm_row(
            row
        )
    }


def get_wake_alarm(
    date
):
    """
    Get the wake alarm for one date.

    Disabled alarms are still returned so Mairon can
    distinguish "no alarm exists" from "alarm disabled".
    """

    if not validate_date(
        date
    ):
        return {
            "success": False,
            "message": (
                "Alarm date must use YYYY-MM-DD format."
            )
        }

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT *
            FROM alarms
            WHERE
                alarm_date = ?
                AND alarm_type = 'wake'
            """,
            (
                date,
            )
        ).fetchone()

    if not row:
        return {
            "success": True,
            "date": date,
            "found": False,
            "alarm": None
        }

    return {
        "success": True,
        "date": date,
        "found": True,
        "alarm": normalise_alarm_row(
            row
        )
    }


def disable_wake_alarm(
    date
):
    """
    Disable the wake alarm for one date without deleting
    the record.

    Useful for:

        "Don't wake me tomorrow."
    """

    if not validate_date(
        date
    ):
        return {
            "success": False,
            "message": (
                "Alarm date must use YYYY-MM-DD format."
            )
        }

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    with get_connection() as connection:

        cursor = connection.execute(
            """
            UPDATE alarms
            SET
                enabled = 0,
                updated_at = ?
            WHERE
                alarm_date = ?
                AND alarm_type = 'wake'
            """,
            (
                now,
                date
            )
        )

        connection.commit()

    if cursor.rowcount == 0:
        return {
            "success": True,
            "date": date,
            "found": False,
            "message": (
                "No wake alarm existed for that date."
            )
        }

    return {
        "success": True,
        "date": date,
        "found": True,
        "message": (
            "Wake alarm disabled."
        )
    }


def delete_wake_alarm(
    date
):
    """
    Permanently remove one date's wake alarm.
    """

    if not validate_date(
        date
    ):
        return {
            "success": False,
            "message": (
                "Alarm date must use YYYY-MM-DD format."
            )
        }

    with get_connection() as connection:

        cursor = connection.execute(
            """
            DELETE FROM alarms
            WHERE
                alarm_date = ?
                AND alarm_type = 'wake'
            """,
            (
                date,
            )
        )

        connection.commit()

    return {
        "success": True,
        "date": date,
        "deleted": cursor.rowcount
    }


# --------------------------------------------------
# Upcoming alarms
# --------------------------------------------------

def list_upcoming_alarms(
    days=7,
    enabled_only=True
):
    """
    List alarms from today through the requested number
    of days ahead.
    """

    days = max(
        1,
        min(
            int(days),
            90
        )
    )

    today = datetime.now(
        LOCAL_TIMEZONE
    ).date()

    end_date = (
        today
        + timedelta(
            days=days
        )
    )

    query = """
        SELECT *
        FROM alarms
        WHERE
            alarm_date >= ?
            AND alarm_date <= ?
    """

    parameters = [
        today.isoformat(),
        end_date.isoformat()
    ]

    if enabled_only:
        query += """
            AND enabled = 1
        """

    query += """
        ORDER BY
            alarm_date,
            alarm_time,
            id
    """

    with get_connection() as connection:

        rows = connection.execute(
            query,
            parameters
        ).fetchall()

    alarms = [
        normalise_alarm_row(
            row
        )
        for row in rows
    ]

    return {
        "success": True,
        "start_date": today.isoformat(),
        "end_date": end_date.isoformat(),
        "alarms": alarms
    }


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":

    # Disposable future workday.
    test_date = "2026-09-03"

    print(
        "--- Initialise ---"
    )

    print(
        json.dumps(
            initialise_alarm_store(),
            indent=2
        )
    )

    print()

    print(
        "--- Before ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Set office wake alarm ---"
    )

    print(
        json.dumps(
            set_wake_alarm(
                date=test_date,
                time="06:30",
                label="Work - Office",
                source="routine",
                metadata={
                    "work_location": "office"
                }
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Read alarm ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Override to 07:00 ---"
    )

    print(
        json.dumps(
            set_wake_alarm(
                date=test_date,
                time="07:00",
                label="Wake up",
                source="manual",
                metadata={
                    "reason": (
                        "Explicit test override."
                    )
                }
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Read overridden alarm ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Disable ---"
    )

    print(
        json.dumps(
            disable_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Disabled alarm state ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- Cleanup ---"
    )

    print(
        json.dumps(
            delete_wake_alarm(
                test_date
            ),
            indent=2
        )
    )

    print()

    print(
        "--- After cleanup ---"
    )

    print(
        json.dumps(
            get_wake_alarm(
                test_date
            ),
            indent=2
        )
    )