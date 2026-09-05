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
    # 1. Native Windows title bar is the only window-chrome authority.
    # --------------------------------------------------

    has_mairon_native_title = False

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if not (
            isinstance(
                func,
                ast.Attribute,
            )
            and func.attr == "title"
            and isinstance(
                func.value,
                ast.Attribute,
            )
            and isinstance(
                func.value.value,
                ast.Name,
            )
            and func.value.value.id == "self"
            and func.value.attr == "root"
        ):
            continue

        if not node.args:
            continue

        first_arg = node.args[
            0
        ]

        if (
            isinstance(
                first_arg,
                ast.Constant,
            )
            and first_arg.value == "MAIRON"
        ):
            has_mairon_native_title = True
            break

    assert has_mairon_native_title is True

    assert (
        "native_windows_chrome"
        in source
    )

    assert (
        "def _apply_windows_titlebar_theme("
        in source
    )

    for forbidden in (
        "overrideredirect(",
        "def _build_title_bar(",
        "def _start_drag(",
        "def _drag_window(",
        "def _minimize(",
        "SC_MOVE",
        "SC_MINIMIZE",
        "WM_NCLBUTTONDOWN",
    ):
        assert forbidden not in source

    # --------------------------------------------------
    # 2. DWM themes the native title bar to Mairon's palette.
    # --------------------------------------------------

    for token in (
        "DWMWA_USE_IMMERSIVE_DARK_MODE",
        "DWMWA_WINDOW_CORNER_PREFERENCE",
        "DWMWA_BORDER_COLOR",
        "DWMWA_CAPTION_COLOR",
        "DWMWA_TEXT_COLOR",
        "MAIRON_DWM_CAPTION_COLOR",
        "MAIRON_DWM_TEXT_COLOR",
        "MAIRON_DWM_BORDER_COLOR",
        "DwmSetWindowAttribute",
    ):
        assert token in source

    # --------------------------------------------------
    # 3. Body is now the top-level application surface.
    # --------------------------------------------------

    build_start = source.index(
        "    def _build_ui("
    )

    build_end = source.index(
        "    def _build_body(",
        build_start,
    )

    build_source = source[
        build_start:
        build_end
    ]

    assert (
        "self._build_body()"
        in build_source
    )

    assert (
        "_build_title_bar"
        not in build_source
    )

    # --------------------------------------------------
    # 4. Existing themed scrolling stays intact.
    # --------------------------------------------------

    assert (
        "class ThemedScrollbar("
        in source
    )

    assert (
        "class ScrollableChat("
        in source
    )

    assert (
        "def _on_mousewheel("
        in source
    )

    # --------------------------------------------------
    # 5. Core still stays behind the application-service boundary.
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
        "Mairon Phase 10.4.6 native Windows titlebar tests: PASS"
    )


if __name__ == "__main__":
    run()
