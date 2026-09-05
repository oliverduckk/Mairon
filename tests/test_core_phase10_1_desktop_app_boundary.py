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

    identity_path = (
        SRC_DIR
        / "mairon_identity.py"
    )

    for path in (
        app_path,
        service_path,
        identity_path,
    ):
        assert path.is_file(), path

    # --------------------------------------------------
    # 1. Desktop UI uses the application service rather than importing Core.
    # --------------------------------------------------

    tree = ast.parse(
        app_path.read_text(
            encoding="utf-8",
        ),
        filename=str(
            app_path
        ),
    )

    imports = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ):
            imports.add(
                str(
                    node.module
                    or ""
                )
            )

    assert (
        "application_service"
        in imports
    )

    assert (
        "core.orchestrator"
        not in imports
    )

    assert (
        "core.router"
        not in imports
    )

    # --------------------------------------------------
    # 2. Importing desktop_app must not immediately create a Tk root/run loop.
    # --------------------------------------------------

    source = app_path.read_text(
        encoding="utf-8",
    )

    assert (
        'if __name__ == "__main__":'
        in source
    )

    # --------------------------------------------------
    # 3. The UI bootstraps the Desktop Agent automatically.
    # --------------------------------------------------

    assert (
        "DesktopAgentProcessManager"
        in source
    )

    assert (
        "ensure_running"
        in source
    )

    assert (
        "ping_desktop_agent"
        in source
    )

    # --------------------------------------------------
    # 4. Stable Mairon identity lives in one shared module.
    # --------------------------------------------------

    service_source = (
        service_path.read_text(
            encoding="utf-8",
        )
    )

    assert (
        "build_mairon_instructions"
        in service_source
    )

    assert (
        "You are Mairon, a personal AI assistant"
        not in service_source
    )

    print(
        "Mairon Phase 10.1 desktop-app boundary tests: PASS"
    )


if __name__ == "__main__":
    run()
