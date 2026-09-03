import math
import sqlite3
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from core.response_timer import ResponseTimer
from continuity import conversation_journal


class FakeClock:
    def __init__(
        self,
    ):
        self.value = 100.0

    def __call__(
        self,
    ):
        return self.value

    def advance(
        self,
        seconds,
    ):
        self.value += float(
            seconds
        )


def run_timer_unit_checks():
    clock = FakeClock()

    timer = ResponseTimer(
        clock=clock
    )

    clock.advance(
        1.25
    )

    assert math.isclose(
        timer.elapsed(),
        1.25,
        abs_tol=1e-9,
    )

    timer.pause()

    clock.advance(
        30.0
    )

    assert math.isclose(
        timer.elapsed(),
        1.25,
        abs_tol=1e-9,
    )

    timer.resume()

    clock.advance(
        0.75
    )

    measured = timer.stop()

    assert math.isclose(
        measured,
        2.0,
        abs_tol=1e-9,
    )

    # stop() is idempotent.
    clock.advance(
        5.0
    )

    assert math.isclose(
        timer.stop(),
        2.0,
        abs_tol=1e-9,
    )


def run_journal_checks():
    with tempfile.TemporaryDirectory() as directory:
        temp_db = (
            Path(
                directory
            )
            / "conversation_journal.db"
        )

        original_path = (
            conversation_journal.JOURNAL_DB_PATH
        )

        original_session = (
            conversation_journal.CURRENT_SESSION_ID
        )

        try:
            conversation_journal.JOURNAL_DB_PATH = (
                temp_db
            )

            conversation_journal.CURRENT_SESSION_ID = (
                "timing-test-session"
            )

            # Simulate a PRE-TIMING journal to prove migration is safe.
            temp_db.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            connection = sqlite3.connect(
                temp_db
            )

            try:
                connection.execute(
                    """
                    CREATE TABLE conversation_turns (
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
                        "old-session",
                        "2026-09-01T10:00:00+10:00",
                        "text",
                        "old prompt",
                        "old answer",
                    ),
                )

                connection.commit()

            finally:
                connection.close()

            conversation_journal.initialise_journal()

            connection = sqlite3.connect(
                temp_db
            )

            try:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(conversation_turns)"
                    ).fetchall()
                }

            finally:
                connection.close()

            assert (
                "response_ms"
                in columns
            )

            conversation_journal.record_conversation_turn(
                user_text="one",
                assistant_text="answer one",
                response_seconds=4.0,
            )

            conversation_journal.record_conversation_turn(
                user_text="two",
                assistant_text="answer two",
                response_seconds=2.0,
            )

            conversation_journal.record_conversation_turn(
                user_text="three",
                assistant_text="answer three",
                response_seconds=3.0,
            )

            stats = (
                conversation_journal
                .get_response_timing_stats()
            )

            # Old unmeasured turn is not included.
            assert (
                stats["count"]
                == 3
            )

            assert math.isclose(
                stats["average_seconds"],
                3.0,
                abs_tol=1e-9,
            )

            assert math.isclose(
                stats["median_seconds"],
                3.0,
                abs_tol=1e-9,
            )

            assert math.isclose(
                stats["p95_seconds"],
                4.0,
                abs_tol=1e-9,
            )

            assert math.isclose(
                stats["fastest_seconds"],
                2.0,
                abs_tol=1e-9,
            )

            assert math.isclose(
                stats["slowest_seconds"],
                4.0,
                abs_tol=1e-9,
            )

            session_stats = (
                conversation_journal
                .get_response_timing_stats(
                    session_id=(
                        "timing-test-session"
                    )
                )
            )

            assert (
                session_stats["count"]
                == 3
            )

            recent_stats = (
                conversation_journal
                .get_response_timing_stats(
                    limit=2
                )
            )

            assert (
                recent_stats["count"]
                == 2
            )

        finally:
            conversation_journal.JOURNAL_DB_PATH = (
                original_path
            )

            conversation_journal.CURRENT_SESSION_ID = (
                original_session
            )


def run():
    run_timer_unit_checks()
    run_journal_checks()

    print(
        "Response timing regression passed."
    )


if __name__ == "__main__":
    run()
