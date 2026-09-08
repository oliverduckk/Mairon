import ast
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from continuity.chat_history import (
    group_chat_sessions,
    history_group_label,
)
from continuity.chat_session_store import (
    list_chat_sessions,
    record_chat_turn,
    rename_chat_session,
)


def _record(db_path, session_id, user_text, assistant_text, title=None):
    record_chat_turn(
        session_id=session_id,
        user_text=user_text,
        assistant_text=assistant_text,
        db_path=db_path,
    )

    if title is not None:
        assert rename_chat_session(
            session_id,
            title,
            db_path=db_path,
        ) is True


def run():
    # --------------------------------------------------
    # 1. History search is local and covers title + transcript text.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "chat_sessions.db"

        _record(
            db_path,
            "bluetooth-session",
            "Why is Bluetooth range limited through walls?",
            "Radio power, frequency and obstacles all affect the usable range.",
            title="Bluetooth Range Explained",
        )

        _record(
            db_path,
            "apollo-session",
            "What happened during Apollo 13?",
            "The lunar module was used as a lifeboat during the return to Earth.",
            title="Apollo 13 Mission",
        )

        # More than the old six-chat sidebar ceiling must remain retrievable.
        for index in range(7):
            _record(
                db_path,
                f"extra-{index}",
                f"Extra saved conversation {index}",
                f"Saved reply {index}",
                title=f"Extra Chat {index}",
            )

        all_sessions = list_chat_sessions(
            limit=100,
            db_path=db_path,
        )

        assert len(all_sessions) == 9

        by_title = list_chat_sessions(
            limit=100,
            query="Bluetooth Range",
            db_path=db_path,
        )

        assert [
            item["session_id"]
            for item in by_title
        ] == ["bluetooth-session"]

        by_user_text = list_chat_sessions(
            limit=100,
            query="Apollo 13",
            db_path=db_path,
        )

        assert [
            item["session_id"]
            for item in by_user_text
        ] == ["apollo-session"]

        by_assistant_text = list_chat_sessions(
            limit=100,
            query="lunar module",
            db_path=db_path,
        )

        assert [
            item["session_id"]
            for item in by_assistant_text
        ] == ["apollo-session"]

        # LIKE wildcards are literal user text, not an accidental "match all".
        assert list_chat_sessions(
            limit=100,
            query="%",
            db_path=db_path,
        ) == []

    # --------------------------------------------------
    # 2. Date grouping is deterministic around local calendar boundaries.
    # --------------------------------------------------

    tz = timezone(
        timedelta(hours=10)
    )

    now = datetime(
        2026,
        9,
        8,
        21,
        0,
        tzinfo=tz,
    )

    assert history_group_label(
        "2026-09-08T08:00:00+10:00",
        now=now,
    ) == "TODAY"

    assert history_group_label(
        "2026-09-07T23:00:00+10:00",
        now=now,
    ) == "YESTERDAY"

    assert history_group_label(
        "2026-09-03T12:00:00+10:00",
        now=now,
    ) == "PREVIOUS 7 DAYS"

    assert history_group_label(
        "2026-08-20T12:00:00+10:00",
        now=now,
    ) == "OLDER"

    grouped = group_chat_sessions(
        [
            {"session_id": "today", "updated_at": "2026-09-08T10:00:00+10:00"},
            {"session_id": "yesterday", "updated_at": "2026-09-07T10:00:00+10:00"},
            {"session_id": "week", "updated_at": "2026-09-04T10:00:00+10:00"},
            {"session_id": "older", "updated_at": "2026-08-01T10:00:00+10:00"},
        ],
        now=now,
    )

    assert [
        label
        for label, _ in grouped
    ] == [
        "TODAY",
        "YESTERDAY",
        "PREVIOUS 7 DAYS",
        "OLDER",
    ]

    # --------------------------------------------------
    # 3. Desktop implementation exposes a scrollable, searchable grouped list.
    # --------------------------------------------------

    desktop_path = SRC_DIR / "desktop_app.py"
    desktop_source = desktop_path.read_text(
        encoding="utf-8",
    )

    ast.parse(
        desktop_source,
        filename=str(desktop_path),
    )

    assert 'text="CHATS"' in desktop_source
    assert '"Search chats..."' in desktop_source
    assert "self.recent_chats_canvas = tk.Canvas(" in desktop_source
    assert "self.recent_chats_scrollbar = ThemedScrollbar(" in desktop_source
    assert '"<MouseWheel>"' in desktop_source
    assert "group_chat_sessions(" in desktop_source
    assert "limit=100" in desktop_source
    assert "query=(" in desktop_source
    assert '"No chats match your search"' in desktop_source

    # Search should be debounced rather than querying SQLite on every raw key event.
    assert "self.root.after(" in desktop_source
    assert "120," in desktop_source

    # --------------------------------------------------
    # 4. Application boundary forwards query without UI knowledge leaking down.
    # --------------------------------------------------

    app_path = SRC_DIR / "application_service.py"
    app_source = app_path.read_text(
        encoding="utf-8",
    )

    ast.parse(
        app_source,
        filename=str(app_path),
    )

    assert "query: str | None = None" in app_source
    assert "query=query" in app_source

    print(
        "Mairon Phase 10.6.3 conversation-history UX tests: PASS"
    )


if __name__ == "__main__":
    run()
