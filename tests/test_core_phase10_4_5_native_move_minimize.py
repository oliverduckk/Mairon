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


def _method_node(
    tree: ast.AST,
    name: str,
):
    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name == name
        ):
            return node

    raise AssertionError(
        f"Missing method: {name}"
    )


def _called_attributes(
    node: ast.AST,
) -> set[str]:
    names = set()

    for item in ast.walk(
        node
    ):
        if not isinstance(
            item,
            ast.Call,
        ):
            continue

        func = item.func

        if isinstance(
            func,
            ast.Attribute,
        ):
            names.add(
                func.attr
            )

    return names


def _loaded_names(
    node: ast.AST,
) -> set[str]:
    return {
        item.id
        for item in ast.walk(
            node
        )
        if isinstance(
            item,
            ast.Name,
        )
        and isinstance(
            item.ctx,
            ast.Load,
        )
    }


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
    # 1. Windows owns title-bar movement and minimise directly.
    # --------------------------------------------------

    assert (
        "def _start_drag("
        not in source
    )

    assert (
        "def _minimize("
        not in source
    )

    assert (
        "SC_MOVE"
        not in source
    )

    assert (
        "SC_MINIMIZE"
        not in source
    )

    assert (
        "WM_NCLBUTTONDOWN"
        not in source
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

    # --------------------------------------------------
    # 3. Scrolling/themed scrollbar from 10.4.4 stays intact.
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
    # 4. UI still sits above the application-service boundary.
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
        "Mairon Phase 10.4.5 stable native move/minimize tests: PASS"
    )


if __name__ == "__main__":
    run()
