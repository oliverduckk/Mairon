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
    # 1. Conversation surface supports actual user scrolling.
    # --------------------------------------------------

    scroll_start = source.index(
        "class ScrollableChat("
    )

    scroll_end = source.index(
        "class DesktopAgentProcessManager:",
        scroll_start,
    )

    scroll_source = source[
        scroll_start:
        scroll_end
    ]

    assert (
        "yscrollcommand"
        in scroll_source
    )

    assert (
        "ThemedScrollbar("
        in scroll_source
    )

    scroll_tree = ast.parse(
        scroll_source,
        filename="ScrollableChat",
    )

    has_mousewheel_bind = False

    for node in ast.walk(
        scroll_tree
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
            and func.attr == "bind_all"
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
            and first_arg.value == "<MouseWheel>"
        ):
            has_mousewheel_bind = True
            break

    assert has_mousewheel_bind is True

    assert (
        "def _pointer_is_over_chat("
        in scroll_source
    )

    assert (
        "def _on_mousewheel("
        in scroll_source
    )

    assert (
        "self.canvas.yview_scroll("
        in scroll_source
    )

    # Scrolling up must be allowed to stop sticky auto-follow.
    assert (
        "_stick_to_bottom"
        in scroll_source
    )

    assert (
        "def _update_stick_to_bottom("
        in scroll_source
    )

    # --------------------------------------------------
    # 2. Composer text is 11pt normal weight.
    # --------------------------------------------------

    composer_font = None

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        if len(
            node.targets
        ) != 1:
            continue

        target = node.targets[
            0
        ]

        if not (
            isinstance(
                target,
                ast.Attribute,
            )
            and isinstance(
                target.value,
                ast.Name,
            )
            and target.value.id == "self"
            and target.attr == "input"
        ):
            continue

        call = node.value

        if not (
            isinstance(
                call,
                ast.Call,
            )
            and isinstance(
                call.func,
                ast.Attribute,
            )
            and isinstance(
                call.func.value,
                ast.Name,
            )
            and call.func.value.id == "tk"
            and call.func.attr == "Text"
        ):
            continue

        for keyword in call.keywords:
            if keyword.arg == "font":
                composer_font = keyword.value
                break

        if composer_font is not None:
            break

    assert isinstance(
        composer_font,
        ast.Tuple,
    )

    font_values = []

    for item in composer_font.elts:
        if isinstance(
            item,
            ast.Constant,
        ):
            font_values.append(
                item.value
            )

        elif (
            isinstance(
                item,
                ast.Attribute,
            )
            and isinstance(
                item.value,
                ast.Name,
            )
            and item.value.id == "self"
            and item.attr == "font_family"
        ):
            font_values.append(
                "self.font_family"
            )

    assert font_values[
        0
    ] == "self.font_family"

    assert 11 in font_values

    assert "bold" not in font_values

    # --------------------------------------------------
    # 3. Mairon is a real native Windows app window with DWM-themed chrome.
    # --------------------------------------------------

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
        "overrideredirect("
        not in source
    )

    assert (
        "def _minimize("
        not in source
    )

    assert (
        "def _start_drag("
        not in source
    )

    # --------------------------------------------------
    # 4. UI boundary remains intact.
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
        "Mairon Phase 10.4.3 native-window/scrolling/composer tests: PASS"
    )


if __name__ == "__main__":
    run()
