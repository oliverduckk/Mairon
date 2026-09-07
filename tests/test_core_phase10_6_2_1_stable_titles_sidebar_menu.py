import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from continuity.chat_session_store import (
    load_chat_session,
    new_session_id,
    record_chat_turn,
)


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "chat_sessions.db"
        session_id = new_session_id()

        first_state = SimpleNamespace(
            active_intent="calculate_arithmetic",
            active_subject="10 + 5",
            active_entities={},
        )

        record_chat_turn(
            session_id=session_id,
            user_text="add 10 and 5",
            assistant_text="The total is 15.",
            core_state=first_state,
            db_path=db_path,
        )

        first = load_chat_session(
            session_id,
            db_path=db_path,
        )

        assert first is not None
        assert first["title"] == "Arithmetic Calculation"
        assert first["title_origin"] == "auto"

        # A later unrelated message must NOT rename the auto-titled chat.
        second_state = SimpleNamespace(
            active_intent="casual_conversation",
            active_subject="rugby league",
            active_entities={},
        )

        record_chat_turn(
            session_id=session_id,
            user_text="I grew up playing rugby league",
            assistant_text="That explains a few things.",
            core_state=second_state,
            db_path=db_path,
        )

        second = load_chat_session(
            session_id,
            db_path=db_path,
        )

        assert second is not None
        assert second["title"] == "Arithmetic Calculation"
        assert second["title_origin"] == "auto"

    app_path = SRC_DIR / "desktop_app.py"
    app_source = app_path.read_text(
        encoding="utf-8",
    )

    # Menu control is packed before title label, reserving its horizontal slot.
    recent_start = app_source.index(
        "        for session in sessions:"
    )

    recent_end = app_source.index(
        "    def _show_chat_menu(",
        recent_start,
    )

    recent_source = app_source[
        recent_start:
        recent_end
    ]

    assert (
        'text="⋯"'
        in recent_source
    )

    assert (
        "display_title"
        in recent_source
    )

    assert (
        "menu_button.pack("
        in recent_source
    )

    assert (
        "label.pack("
        in recent_source
    )

    assert (
        recent_source.index(
            "menu_button.pack("
        )
        < recent_source.index(
            "label.pack("
        )
    )

    print(
        "Mairon Phase 10.6.2.1 stable-title/sidebar-menu tests: PASS"
    )


if __name__ == "__main__":
    run()
