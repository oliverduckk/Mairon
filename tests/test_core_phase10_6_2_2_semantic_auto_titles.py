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
    apply_semantic_chat_title,
    load_chat_session,
    new_session_id,
    record_chat_turn,
    rename_chat_session,
)
from continuity.chat_title_generator import (
    generate_semantic_chat_title,
)


class _FakeMessage:
    def __init__(
        self,
        content,
    ):
        self.content = content


class _FakeResponse:
    def __init__(
        self,
        content,
    ):
        self.message = _FakeMessage(
            content
        )


class _FakeClient:
    def __init__(
        self,
        content,
    ):
        self.content = content
        self.calls = []

    def chat(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return _FakeResponse(
            self.content
        )


def run():
    # --------------------------------------------------
    # 1. Local title generation is isolated and produces broad short metadata.
    # --------------------------------------------------

    client = _FakeClient(
        "Starlink Cost and Gaming"
    )

    local_ai = {
        "name": "ollama",
        "client": client,
    }

    title = generate_semantic_chat_title(
        local_ai=local_ai,
        model_name="qwen3.5:9b",
        user_text=(
            "can you explain Starlink to me and tell me if "
            "it is worth the price"
        ),
        assistant_text=(
            "Starlink is a satellite internet service. "
            "Its value depends on your location and alternatives."
        ),
    )

    assert title == (
        "Starlink Cost and Gaming"
    )

    assert len(
        client.calls
    ) == 1

    call = client.calls[
        0
    ]

    assert call[
        "model"
    ] == "qwen3.5:9b"

    messages = call[
        "messages"
    ]

    assert len(
        messages
    ) == 2

    assert messages[
        0
    ][
        "role"
    ] == "system"

    assert messages[
        1
    ][
        "role"
    ] == "user"

    # No conversation history, tools, Answer Contract or Mairon state is passed.
    assert "tools" not in call

    # --------------------------------------------------
    # 2. Semantic title upgrades an automatic fallback exactly once.
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
            user_text=(
                "can you explain Starlink to me and tell me "
                "if it is worth the price"
            ),
            assistant_text=(
                "Starlink is satellite internet."
            ),
            core_state=SimpleNamespace(
                active_intent="casual_conversation",
                active_subject="",
                active_entities={},
            ),
            db_path=db_path,
        )

        before = load_chat_session(
            session_id,
            db_path=db_path,
        )

        assert before is not None
        assert before[
            "title_origin"
        ] == "auto"

        changed = apply_semantic_chat_title(
            session_id,
            "Starlink Overview",
            db_path=db_path,
        )

        assert changed is True

        after = load_chat_session(
            session_id,
            db_path=db_path,
        )

        assert after is not None
        assert after[
            "title"
        ] == "Starlink Overview"
        assert after[
            "title_origin"
        ] == "semantic"

        # A later semantic attempt cannot continuously rename the chat.
        changed_again = apply_semantic_chat_title(
            session_id,
            "Different Title",
            db_path=db_path,
        )

        assert changed_again is False

        # --------------------------------------------------
        # 3. Manual rename always outranks semantic generation.
        # --------------------------------------------------

        assert rename_chat_session(
            session_id,
            "My Starlink Chat",
            db_path=db_path,
        ) is True

        semantic_after_manual = (
            apply_semantic_chat_title(
                session_id,
                "Should Never Win",
                db_path=db_path,
            )
        )

        assert semantic_after_manual is False

        manual = load_chat_session(
            session_id,
            db_path=db_path,
        )

        assert manual is not None
        assert manual[
            "title"
        ] == "My Starlink Chat"
        assert manual[
            "title_origin"
        ] == "manual"

    # --------------------------------------------------
    # 4. Application service schedules generation off the response path.
    # --------------------------------------------------

    service_source = (
        SRC_DIR
        / "application_service.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "threading.Thread("
        in service_source
    )

    assert (
        'daemon=True'
        in service_source
    )

    assert (
        "_schedule_semantic_title_if_first_turn("
        in service_source
    )

    # --------------------------------------------------
    # 5. Desktop refreshes after the async metadata update.
    # --------------------------------------------------

    desktop_source = (
        SRC_DIR
        / "desktop_app.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "def _refresh_current_chat_title("
        in desktop_source
    )

    assert (
        "self.root.after("
        in desktop_source
    )

    print(
        "Mairon Phase 10.6.2.2 semantic auto-title tests: PASS"
    )


if __name__ == "__main__":
    run()
