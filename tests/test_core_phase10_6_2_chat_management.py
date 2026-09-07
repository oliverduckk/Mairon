import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from continuity.chat_session_store import (
    delete_chat_session,
    derive_session_title,
    list_chat_sessions,
    load_chat_session,
    new_session_id,
    record_chat_turn,
    rename_chat_session,
)


def run():
    # --------------------------------------------------
    # 1. Core semantics produce smarter automatic titles.
    # --------------------------------------------------

    arithmetic_state = SimpleNamespace(
        active_intent="calculate_arithmetic",
        active_subject="557 + 528",
        active_entities={},
    )

    assert derive_session_title(
        "add 557, 528, 527, 493, 452 and 1118",
        core_state=arithmetic_state,
    ) == "Arithmetic Calculation"

    application_state = SimpleNamespace(
        active_intent="launch_application",
        active_subject="calculator",
        active_entities={
            "application": "calculator",
        },
    )

    assert derive_session_title(
        "open calculator please",
        core_state=application_state,
    ) == "Open Calculator"

    file_state = SimpleNamespace(
        active_intent="find_local_file",
        active_subject="passport",
        active_entities={
            "file_query": "passport",
        },
    )

    assert derive_session_title(
        "can you find my passport",
        core_state=file_state,
    ) == "Find Passport"

    # --------------------------------------------------
    # 2. Manual rename overrides future automatic titles.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as tmp:
        db_path = (
            Path(
                tmp
            )
            / "chat_sessions.db"
        )

        session_id = new_session_id()

        record_chat_turn(
            session_id=session_id,
            user_text="add 10 and 5",
            assistant_text="The total is 15.",
            core_state=SimpleNamespace(
                active_intent="calculate_arithmetic",
                active_subject="10 + 5",
                active_entities={},
            ),
            db_path=db_path,
        )

        first = load_chat_session(
            session_id,
            db_path=db_path,
        )

        assert first is not None
        assert first[
            "title"
        ] == "Arithmetic Calculation"

        assert first[
            "title_origin"
        ] == "auto"

        renamed = rename_chat_session(
            session_id,
            "Budget Maths",
            db_path=db_path,
        )

        assert renamed is True

        record_chat_turn(
            session_id=session_id,
            user_text="double it",
            assistant_text="The result is 30.",
            core_state=SimpleNamespace(
                active_intent="calculate_arithmetic",
                active_subject="15 * 2",
                active_entities={},
            ),
            db_path=db_path,
        )

        after = load_chat_session(
            session_id,
            db_path=db_path,
        )

        assert after is not None
        assert after[
            "title"
        ] == "Budget Maths"

        assert after[
            "title_origin"
        ] == "manual"

        # --------------------------------------------------
        # 3. Delete removes transcript + session metadata.
        # --------------------------------------------------

        deleted = delete_chat_session(
            session_id,
            db_path=db_path,
        )

        assert deleted is True

        assert load_chat_session(
            session_id,
            db_path=db_path,
        ) is None

        assert list_chat_sessions(
            db_path=db_path,
        ) == []

    print(
        "Mairon Phase 10.6.2 smart-title/rename/delete store tests: PASS"
    )


if __name__ == "__main__":
    run()
