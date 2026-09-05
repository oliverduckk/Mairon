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

    source = app_path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(
            app_path
        ),
    )

    # --------------------------------------------------
    # 1. Chat rendering uses dedicated rounded bubble widgets.
    # --------------------------------------------------

    assert (
        "class RoundedMessageBubble("
        in source
    )

    assert (
        "class ScrollableChat("
        in source
    )

    assert (
        'role="user"'
        in source
    )

    assert (
        'role="mairon"'
        in source
    )

    # --------------------------------------------------
    # 2. Send is a genuinely rounded custom composer control.
    # --------------------------------------------------

    assert (
        "class RoundedIconButton("
        in source
    )

    assert (
        "self.send_button = RoundedIconButton("
        in source
    )

    assert (
        'text="↑"'
        in source
    )

    # --------------------------------------------------
    # 3. Voice moved out of WORKSPACE and into the composer.
    # --------------------------------------------------

    sidebar_start = source.index(
        "    def _build_sidebar("
    )

    sidebar_end = source.index(
        "    def _sidebar_item(",
        sidebar_start,
    )

    sidebar_source = source[
        sidebar_start:
        sidebar_end
    ]

    assert (
        '"◌  Voice"'
        not in sidebar_source
    )

    assert (
        "self.voice_button = RoundedIconButton("
        in source
    )

    # Voice is intentionally still disabled until native GUI recording lands.
    assert (
        'text="🎙"'
        in source
    )

    # --------------------------------------------------
    # 4. Desktop UI still does not reach around the application service.
    # --------------------------------------------------

    imported_modules = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ):
            imported_modules.add(
                str(
                    node.module
                    or ""
                )
            )

    assert (
        "application_service"
        in imported_modules
    )

    assert (
        "core.orchestrator"
        not in imported_modules
    )

    assert (
        "core.router"
        not in imported_modules
    )

    print(
        "Mairon Phase 10.2.1 chat bubbles/composer controls tests: PASS"
    )


if __name__ == "__main__":
    run()
