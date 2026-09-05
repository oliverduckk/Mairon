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


from mairon_theme import (
    FONT_PREFERENCES,
    MAIRON_THEME,
)


def run():
    # --------------------------------------------------
    # 1. Agreed Mairon palette is centralized and exact.
    # --------------------------------------------------

    assert MAIRON_THEME[
        "app_bg"
    ] == "#1A1B2F"

    assert MAIRON_THEME[
        "accent"
    ] == "#D44963"

    assert MAIRON_THEME[
        "surface"
    ] == "#16213E"

    assert MAIRON_THEME[
        "surface_hover"
    ] == "#552C4A"

    assert MAIRON_THEME[
        "border"
    ] == "#343157"

    assert FONT_PREFERENCES[
        :2
    ] == (
        "Plus Jakarta Sans",
        "Inter",
    )

    # --------------------------------------------------
    # 2. Desktop UI still uses the application-service boundary.
    # --------------------------------------------------

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

    # --------------------------------------------------
    # 3. Long-running turns expose a transient thinking state.
    # --------------------------------------------------

    assert (
        "def _show_thinking("
        in source
    )

    assert (
        "def _animate_thinking("
        in source
    )

    assert (
        "def _hide_thinking("
        in source
    )

    assert (
        "def _show_thinking("
        in source
    )

    assert (
        "def _animate_thinking("
        in source
    )

    assert (
        "def _hide_thinking("
        in source
    )

    # --------------------------------------------------
    # 4. Visual shell keeps the agreed Mairon affordances while Windows owns
    #    the real title bar/minimise/dragging behaviour.
    # --------------------------------------------------

    assert (
        "def _build_sidebar("
        in source
    )

    assert (
        "def _apply_windows_titlebar_theme("
        in source
    )

    assert (
        "DWMWA_CAPTION_COLOR"
        in source
    )

    assert (
        "DWMWA_TEXT_COLOR"
        in source
    )

    assert (
        "DWMWA_BORDER_COLOR"
        in source
    )

    # The old fake Tk title bar/minimise layer was intentionally retired.
    assert (
        "def _build_title_bar("
        not in source
    )

    assert (
        "def _minimize("
        not in source
    )

    assert (
        'text="+"'
        in source
    )

    assert (
        'text="↑"'
        in source
    )

    assert (
        "Themes"
        in source
    )

    print(
        "Mairon Phase 10.2 visual shell/thinking-state tests: PASS"
    )


if __name__ == "__main__":
    run()
