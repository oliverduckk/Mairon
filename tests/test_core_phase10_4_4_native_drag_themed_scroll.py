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


def _method_source(
    source: str,
    name: str,
    next_name: str,
) -> str:
    start = source.index(
        f"    def {name}("
    )

    end = source.index(
        f"    def {next_name}(",
        start,
    )

    return source[
        start:
        end
    ]


def run():
    app_path = (
        SRC_DIR
        / "desktop_app.py"
    )

    assert app_path.is_file()

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
    # 1. Scrollbar is Mairon-owned, not the native white Tk scrollbar.
    # --------------------------------------------------

    assert (
        "class ThemedScrollbar("
        in source
    )

    assert (
        "tk.Scrollbar("
        not in source
    )

    assert (
        'self.theme[\\n                "border"'
        in source
        or '"border"' in source
    )

    assert (
        'self.theme[\\n                "surface_hover"'
        in source
        or '"surface_hover"' in source
    )

    # --------------------------------------------------
    # 2. Wheel-up disables sticky following before the canvas moves.
    # --------------------------------------------------

    wheel_source = _method_source(
        source,
        "_on_mousewheel",
        "_update_stick_to_bottom",
    )

    sticky_index = wheel_source.index(
        "self._stick_to_bottom = False"
    )

    scroll_index = wheel_source.index(
        "self.canvas.yview_scroll("
    )

    assert (
        sticky_index
        < scroll_index
    )

    # Inner-frame geometry updates must never auto-jump to the bottom.
    inner_source = _method_source(
        source,
        "_on_inner_configure",
        "_on_canvas_configure",
    )

    assert (
        "scroll_to_bottom"
        not in inner_source
    )

    # --------------------------------------------------
    # 3. Title-bar dragging is owned entirely by the native Windows title bar.
    # --------------------------------------------------

    assert (
        "def _start_drag("
        not in source
    )

    assert (
        "def _drag_window("
        not in source
    )

    assert (
        "SC_MOVE"
        not in source
    )

    assert (
        "WM_NCLBUTTONDOWN"
        not in source
    )

    # --------------------------------------------------
    # 4. Native Windows title bar/frame is themed through DWM.
    # --------------------------------------------------

    assert (
        "DWMWA_BORDER_COLOR"
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
        "DwmSetWindowAttribute"
        in source
    )

    assert (
        "def _minimize("
        not in source
    )

    assert (
        "SC_MINIMIZE"
        not in source
    )

    # --------------------------------------------------
    # 5. Core remains behind application-service boundary.
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
        "Mairon Phase 10.4.4 native drag/themed scrolling tests: PASS"
    )


if __name__ == "__main__":
    run()
