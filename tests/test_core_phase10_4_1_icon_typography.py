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

    icon_path = (
        PROJECT_ROOT
        / "assets"
        / "mairon.ico"
    )

    assert app_path.is_file()
    assert icon_path.is_file()

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
    # 1. The running Tk window uses the dedicated Mairon icon when present.
    # --------------------------------------------------

    assert (
        "APP_ICON_PATH"
        in source
    )

    assert (
        ' / "assets"'
        in source
    )

    assert (
        ' / "mairon.ico"'
        in source
    )

    assert (
        "root.iconbitmap("
        in source
    )

    assert (
        "set_windows_app_identity()"
        in source
    )

    # --------------------------------------------------
    # 2. Chat/composer text keeps the larger size without blanket bold.
    # --------------------------------------------------

    bubble_start = source.index(
        "class RoundedMessageBubble("
    )

    bubble_end = source.index(
        "class ScrollableChat(",
        bubble_start,
    )

    bubble_source = source[
        bubble_start:
        bubble_end
    ]

    assert (
        "size=11"
        in bubble_source
    )

    assert (
        'weight="normal"'
        in bubble_source
    )

    # Speaker labels may remain bold; body text may not.
    message_font_start = bubble_source.index(
        "self._message_font = tkfont.Font("
    )

    message_font_end = bubble_source.index(
        ")",
        message_font_start,
    )

    message_font_source = bubble_source[
        message_font_start:
        message_font_end
        + 1
    ]

    assert (
        'weight="bold"'
        not in message_font_source
    )

    # --------------------------------------------------
    # 3. Sidebar section/item typography is larger than the original shell.
    # --------------------------------------------------

    sidebar_start = source.index(
        "    def _build_sidebar("
    )

    sidebar_end = source.index(
        "    def _build_main_area(",
        sidebar_start,
    )

    sidebar_source = source[
        sidebar_start:
        sidebar_end
    ]

    assert (
        'text="WORKSPACE"'
        in sidebar_source
    )

    assert (
        'text="SYSTEM"'
        in sidebar_source
    )

    item_start = source.index(
        "    def _sidebar_item("
    )

    item_end = source.index(
        "    def _build_main_area(",
        item_start,
    )

    item_source = source[
        item_start:
        item_end
    ]

    assert (
        "self.font_family,\n                10,"
        in item_source
    )

    # --------------------------------------------------
    # 4. Desktop UI remains above the application-service boundary.
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
        "Mairon Phase 10.4.1 icon/typography polish tests: PASS"
    )


if __name__ == "__main__":
    run()
