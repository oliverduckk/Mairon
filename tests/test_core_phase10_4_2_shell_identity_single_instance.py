import ast
import re
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

    installer_path = (
        PROJECT_ROOT
        / "scripts"
        / "install_windows_launcher.ps1"
    )

    for path in (
        app_path,
        identity_path,
        installer_path,
    ):
        assert path.is_file(), path

    app_source = app_path.read_text(
        encoding="utf-8",
    )

    identity_source = identity_path.read_text(
        encoding="utf-8",
    )

    installer_source = installer_path.read_text(
        encoding="utf-8",
    )

    # --------------------------------------------------
    # 1. Process and shortcut use the same stable AppUserModelID.
    # --------------------------------------------------

    match = re.search(
        r'MAIRON_APP_USER_MODEL_ID\s*=\s*\(\s*"([^"]+)"',
        identity_source,
    )

    assert match is not None

    app_id = match.group(
        1
    )

    assert app_id == (
        "OliverDuck.Mairon.Desktop.v1"
    )

    assert app_id in installer_source

    assert (
        "SetCurrentProcessExplicitAppUserModelID"
        in identity_source
    )

    assert (
        "System.AppUserModel.ID"
        in installer_source
        or "PKEY_AppUserModel_ID"
        in installer_source
    )

    assert (
        "SHGetPropertyStoreFromParsingName"
        in installer_source
    )

    assert (
        "SetAppUserModelId"
        in installer_source
    )

    # --------------------------------------------------
    # 2. A second Mairon launch cannot create a second assistant process.
    # --------------------------------------------------

    assert (
        "MAIRON_INSTANCE_MUTEX"
        in identity_source
    )

    assert (
        "CreateMutexW"
        in identity_source
    )

    assert (
        "ERROR_ALREADY_EXISTS"
        in identity_source
    )

    assert (
        "def ensure_single_instance_or_activate("
        in identity_source
    )

    assert (
        "def _activate_existing_mairon_window("
        in identity_source
    )

    assert (
        "SetForegroundWindow"
        in identity_source
    )

    assert (
        "SW_RESTORE"
        in identity_source
    )

    # --------------------------------------------------
    # 3. Single-instance guard runs before Tk creates another window.
    # --------------------------------------------------

    main_start = app_source.index(
        "def main():"
    )

    main_source = app_source[
        main_start:
    ]

    identity_index = main_source.index(
        "set_windows_app_identity()"
    )

    guard_index = main_source.index(
        "ensure_single_instance_or_activate()"
    )

    tk_index = main_source.index(
        "tk.Tk()"
    )

    assert (
        identity_index
        < guard_index
        < tk_index
    )

    # --------------------------------------------------
    # 4. Installer explicitly warns that old pins cache the old identity.
    # --------------------------------------------------

    assert (
        "old taskbar pins"
        in installer_source.lower()
    )

    assert (
        "unpin"
        in installer_source.lower()
    )

    assert (
        "Pin to taskbar"
        in installer_source
    )

    print(
        "Mairon Phase 10.4.2 Windows shell identity/single-instance tests: PASS"
    )


if __name__ == "__main__":
    run()
