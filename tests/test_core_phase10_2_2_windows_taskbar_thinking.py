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
    # 1. Mairon keeps genuine native Windows chrome and themes it through DWM.
    # --------------------------------------------------

    assert (
        "native_windows_chrome"
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

    assert (
        "DWMWA_USE_IMMERSIVE_DARK_MODE"
        in source
    )

    assert (
        "DwmSetWindowAttribute"
        in source
    )

    for forbidden in (
        "overrideredirect(",
        "def _start_drag(",
        "def _minimize(",
        "def _apply_windows_window_style(",
    ):
        assert forbidden not in source

    map_start = source.index(
        "    def _on_window_map("
    )

    map_end = source.index(
        "    # --------------------------------------------------\n"
        "    # Shutdown",
        map_start,
    )

    map_source = source[
        map_start:
        map_end
    ]

    assert (
        "_apply_windows_titlebar_theme"
        in map_source
    )

    # --------------------------------------------------
    # 2. Thinking state is now a compact animated ellipsis.
    # --------------------------------------------------

    animate_start = source.index(
        "    def _animate_thinking("
    )

    animate_end = source.index(
        "    def _hide_thinking(",
        animate_start,
    )

    animate_source = source[
        animate_start:
        animate_end
    ]

    assert (
        'frames = ('
        in animate_source
    )

    assert (
        '"."'
        in animate_source
    )

    assert (
        '".."'
        in animate_source
    )

    assert (
        '"..."'
        in animate_source
    )

    # --------------------------------------------------
    # 3. UI still sits above the application-service boundary.
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
        "Mairon Phase 10.2.2 Windows taskbar/minimal thinking tests: PASS"
    )


if __name__ == "__main__":
    run()
