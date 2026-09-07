import sys
import tempfile
from pathlib import Path


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


import application_service as app_module

from application_service import (
    MaironApplication,
)
from continuity import chat_session_store
from core.orchestrator import (
    MaironCore,
)


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = (
            Path(
                tmp
            )
            / "chat_sessions.db"
        )

        # Route application-service persistence into the isolated test DB.
        app_module.record_chat_turn = (
            lambda **kwargs: (
                chat_session_store
                .record_chat_turn(
                    db_path=db_path,
                    **kwargs,
                )
            )
        )

        app_module.list_chat_sessions = (
            lambda **kwargs: (
                chat_session_store
                .list_chat_sessions(
                    db_path=db_path,
                    **kwargs,
                )
            )
        )

        app_module.load_chat_session = (
            lambda session_id: (
                chat_session_store
                .load_chat_session(
                    session_id,
                    db_path=db_path,
                )
            )
        )

        # The continuity journal has its own tests; don't touch the real local DB.
        app_module.record_conversation_turn = (
            lambda **kwargs: None
        )

        app = MaironApplication(
            user_name="Oliver",
            core=MaironCore(),
            create_providers=False,
        )

        first_session_id = (
            app.session_id
        )

        first = app.submit_text(
            "add 10 and 5"
        )

        assert first.answer == (
            "The total is 15."
        )

        recent = app.recent_chats()

        assert len(
            recent
        ) == 1

        assert recent[
            0
        ][
            "session_id"
        ] == first_session_id

        assert recent[
            0
        ][
            "title"
        ] == "Arithmetic Calculation"

        # --------------------------------------------------
        # New Chat is a genuine short-term state boundary.
        # --------------------------------------------------

        new_session = app.new_chat()

        assert new_session[
            "session_id"
        ] != first_session_id

        assert app.core.conversation_state.active_intent is None
        assert app.local_state is None
        assert app.last_user_input is None
        assert app.last_assistant_answer is None

        # "double it" must NOT inherit arithmetic from the old chat.
        fresh_turn = app.core.prepare_turn(
            "double it"
        )

        assert fresh_turn.turn.intent != (
            "calculate_arithmetic"
        )

        # --------------------------------------------------
        # Reopen does not replay actions; it restores stored Core state.
        # --------------------------------------------------

        restored = app.open_chat(
            first_session_id
        )

        assert restored[
            "session_id"
        ] == first_session_id

        assert len(
            restored[
                "turns"
            ]
        ) == 1

        assert restored[
            "turns"
        ][
            0
        ][
            "user_text"
        ] == "add 10 and 5"

        assert app.core.conversation_state.active_intent == (
            "calculate_arithmetic"
        )

        # Restored authoritative arithmetic state supports referent continuity.
        follow_up = app.submit_text(
            "double it"
        )

        assert follow_up.answer == (
            "The result is 30."
        )

        # The original session now has two persisted turns.
        loaded = chat_session_store.load_chat_session(
            first_session_id,
            db_path=db_path,
        )

        assert loaded is not None
        assert len(
            loaded[
                "turns"
            ]
        ) == 2

        print(
            "Mairon Phase 10.6.1 persistent chat-session tests: PASS"
        )


if __name__ == "__main__":
    run()
