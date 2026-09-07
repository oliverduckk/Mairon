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

    app_source = app_path.read_text(
        encoding="utf-8",
    )

    service_source = service_path.read_text(
        encoding="utf-8",
    )

    store_source = store_path.read_text(
        encoding="utf-8",
    )

    app_tree = ast.parse(
        app_source,
        filename=str(
            app_path
        ),
    )

    # --------------------------------------------------
    # 1. Recent chat rows expose rename/delete management.
    # --------------------------------------------------

    for token in (
        'text="⋯"',
        'label="Rename"',
        'label="Delete"',
        "def _show_chat_menu(",
        "def _rename_chat(",
        "def _delete_chat(",
        "simpledialog.askstring(",
        "messagebox.askyesno(",
    ):
        assert token in app_source

    # --------------------------------------------------
    # 2. Application service owns session mutations.
    # --------------------------------------------------

    for token in (
        "def rename_chat(",
        "def delete_chat(",
        "rename_chat_session(",
        "delete_chat_session(",
    ):
        assert token in service_source

    # Deleting the currently open chat creates a clean replacement session.
    delete_start = service_source.index(
        "    def delete_chat("
    )

    delete_end = service_source.index(
        "    def open_chat(",
        delete_start,
    )

    delete_source = service_source[
        delete_start:
        delete_end
    ]

    assert (
        "self.new_chat()"
        in delete_source
    )

    # --------------------------------------------------
    # 3. Manual title provenance is persisted in the store.
    # --------------------------------------------------

    assert (
        "title_origin"
        in store_source
    )

    assert (
        "title_origin = 'manual'"
        in store_source
    )

    assert (
        "derive_session_title("
        in store_source
    )

    # UI remains above the application-service boundary.
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

    print(
        "Mairon Phase 10.6.2 desktop chat-management tests: PASS"
    )


if __name__ == "__main__":
    run()
