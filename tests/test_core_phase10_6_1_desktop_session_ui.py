import ast
import sys
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


def run():
    app_path = (
        SRC_DIR
        / "desktop_app.py"
    )

    service_path = (
        SRC_DIR
        / "application_service.py"
    )

    store_path = (
        SRC_DIR
        / "continuity"
        / "chat_session_store.py"
    )

    for path in (
        app_path,
        service_path,
        store_path,
    ):
        assert path.is_file(), path

    app_source = app_path.read_text(
        encoding="utf-8",
    )

    service_source = service_path.read_text(
        encoding="utf-8",
    )

    app_tree = ast.parse(
        app_source,
        filename=str(
            app_path
        ),
    )

    # --------------------------------------------------
    # 1. Desktop surface exposes session controls/history.
    # --------------------------------------------------

    for token in (
        "＋  New Chat",
        'text="RECENT"',
        "recent_chats_frame",
        "def _new_chat(",
        "def _open_chat(",
        "def _refresh_recent_chats(",
        "def clear_messages(",
        "chat_title_label",
    ):
        assert token in app_source

    # --------------------------------------------------
    # 2. Session ownership lives in application service, not Tk.
    # --------------------------------------------------

    for token in (
        "def new_chat(",
        "def recent_chats(",
        "def open_chat(",
        "self.session_id",
        "record_chat_turn(",
    ):
        assert token in service_source

    imported_modules = {
        str(
            node.module
            or ""
        )
        for node in ast.walk(
            app_tree
        )
        if isinstance(
            node,
            ast.ImportFrom,
        )
    }

    assert (
        "application_service"
        in imported_modules
    )

    assert (
        "continuity.chat_session_store"
        not in imported_modules
    )

    assert (
        "core.orchestrator"
        not in imported_modules
    )

    # --------------------------------------------------
    # 3. Reopening restores snapshots, never replays prior user actions.
    # --------------------------------------------------

    assert (
        "restore_conversation_state("
        in service_source
    )

    open_start = service_source.index(
        "    def open_chat("
    )

    submit_start = service_source.index(
        "    def submit_text(",
        open_start,
    )

    open_source = service_source[
        open_start:
        submit_start
    ]

    assert (
        ".prepare_turn("
        not in open_source
    )

    assert (
        ".submit_text("
        not in open_source
    )

    print(
        "Mairon Phase 10.6.1 desktop session-boundary tests: PASS"
    )


if __name__ == "__main__":
    run()
