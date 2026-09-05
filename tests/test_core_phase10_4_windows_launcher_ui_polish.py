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

    identity_path = (
        SRC_DIR
        / "windows_app_identity.py"
    )

    launcher_path = (
        PROJECT_ROOT
        / "Mairon.pyw"
    )

    installer_path = (
        PROJECT_ROOT
        / "scripts"
        / "install_windows_launcher.ps1"
    )

    for path in (
        app_path,
        identity_path,
        launcher_path,
        installer_path,
    ):
        assert path.is_file(), path

    app_source = app_path.read_text(
        encoding="utf-8",
    )

    identity_source = identity_path.read_text(
        encoding="utf-8",
    )

    launcher_source = launcher_path.read_text(
        encoding="utf-8",
    )

    installer_source = installer_path.read_text(
        encoding="utf-8",
    )

    # --------------------------------------------------
    # 1. Mairon owns a stable Windows app identity.
    # --------------------------------------------------

    assert (
        "MAIRON_APP_USER_MODEL_ID"
        in identity_source
    )

    assert (
        "SetCurrentProcessExplicitAppUserModelID"
        in identity_source
    )

    assert (
        "set_windows_app_identity()"
        in app_source
    )

    # Identity must be established before Tk creates the top-level HWND.
    main_start = app_source.index(
        "def main():"
    )

    main_source = app_source[
        main_start:
    ]

    identity_index = main_source.index(
        "set_windows_app_identity()"
    )

    tk_index = main_source.index(
        "tk.Tk()"
    )

    assert (
        identity_index
        < tk_index
    )

    # --------------------------------------------------
    # 2. Bubble width is responsive and typography is more legible.
    # --------------------------------------------------

    assert (
        "def fit_to_width("
        in app_source
    )

    assert (
        "item.fit_to_width("
        in app_source
    )

    bubble_start = app_source.index(
        "class RoundedMessageBubble("
    )

    bubble_end = app_source.index(
        "class ScrollableChat(",
        bubble_start,
    )

    bubble_source = app_source[
        bubble_start:
        bubble_end
    ]

    assert (
        "size=11"
        in bubble_source
    )

    assert (
        'weight="bold"'
        in bubble_source
    )

    # --------------------------------------------------
    # 3. Standalone .pyw entrypoint launches the existing desktop client.
    # --------------------------------------------------

    launcher_tree = ast.parse(
        launcher_source,
        filename=str(
            launcher_path
        ),
    )

    launcher_imports = {
        str(
            node.module
            or ""
        )
        for node in ast.walk(
            launcher_tree
        )
        if isinstance(
            node,
            ast.ImportFrom,
        )
    }

    assert (
        "desktop_app"
        in launcher_imports
    )

    assert (
        "core.orchestrator"
        not in launcher_imports
    )

    # --------------------------------------------------
    # 4. Windows shortcut installer uses pythonw + the Mairon launcher.
    # --------------------------------------------------

    assert (
        ".venv\\Scripts\\pythonw.exe"
        in installer_source
    )

    assert (
        "Mairon.pyw"
        in installer_source
    )

    assert (
        "Start Menu\\Programs"
        in installer_source
    )

    assert (
        "Pin to taskbar"
        in installer_source
    )

    assert (
        "assets\\mairon.ico"
        in installer_source
    )

    print(
        "Mairon Phase 10.4 Windows launcher/UI polish tests: PASS"
    )


if __name__ == "__main__":
    run()
