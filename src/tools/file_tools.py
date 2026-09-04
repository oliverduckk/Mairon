import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.file_catalog import (
    CODE_OR_TEXT_EXTENSIONS,
    get_approved_file_roots,
    is_path_within_approved_roots,
    is_safe_openable_file,
)


CREATE_NO_WINDOW = getattr(
    subprocess,
    "CREATE_NO_WINDOW",
    0,
)


def _find_vscode() -> Optional[str]:
    candidates = [
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        r"%ProgramFiles%\Microsoft VS Code\Code.exe",
        r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe",
    ]

    for candidate in candidates:
        path = os.path.expandvars(
            candidate
        )

        if os.path.isfile(
            path
        ):
            return path

    return shutil.which(
        "Code.exe"
    )


def _open_with_vscode(
    path: Path,
) -> dict:
    executable = _find_vscode()

    if not executable:
        return {
            "success": False,
            "status": "vscode_not_found",
            "message": (
                "VS Code isn't available to open that text/code file safely."
            ),
        }

    try:
        subprocess.Popen(
            [
                executable,
                str(
                    path
                ),
            ],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )

    except Exception as exc:
        return {
            "success": False,
            "status": "open_failed",
            "message": str(
                exc
            ),
        }

    return {
        "success": True,
        "status": "opened_in_vscode",
    }


def open_approved_local_path(
    path: str,
) -> dict:
    """
    Open one Core-resolved local file/folder.

    The execution layer re-validates that the path is inside an approved root.
    Executable/script-like files are never launched through this function.
    """

    if os.name != "nt":
        return {
            "success": False,
            "status": "windows_only",
            "message": (
                "Local file opening is only available on the Windows desktop node."
            ),
        }

    raw = str(
        path
        or ""
    ).strip()

    if not raw:
        return {
            "success": False,
            "status": "invalid_path",
            "message": (
                "No local path was supplied."
            ),
        }

    try:
        resolved = Path(
            raw
        ).expanduser().resolve()
    except Exception as exc:
        return {
            "success": False,
            "status": "invalid_path",
            "message": str(
                exc
            ),
        }

    roots = get_approved_file_roots()

    if not is_path_within_approved_roots(
        resolved,
        roots,
    ):
        return {
            "success": False,
            "status": "outside_approved_roots",
            "message": (
                "That path is outside Mairon's approved local file roots."
            ),
        }

    if resolved.is_dir():
        try:
            os.startfile(
                str(
                    resolved
                )
            )
        except Exception as exc:
            return {
                "success": False,
                "status": "open_failed",
                "message": str(
                    exc
                ),
            }

        return {
            "success": True,
            "status": "folder_opened",
            "path": str(
                resolved
            ),
        }

    if not is_safe_openable_file(
        resolved,
        roots,
    ):
        return {
            "success": False,
            "status": "unsafe_or_unsupported_file",
            "message": (
                "That file type/path is not approved for local opening."
            ),
        }

    if resolved.suffix.lower() in CODE_OR_TEXT_EXTENSIONS:
        result = _open_with_vscode(
            resolved
        )

        if result.get(
            "success"
        ) is not True:
            return result

        return {
            "success": True,
            "status": "file_opened",
            "path": str(
                resolved
            ),
            "application": "vscode",
        }

    try:
        os.startfile(
            str(
                resolved
            )
        )

    except Exception as exc:
        return {
            "success": False,
            "status": "open_failed",
            "message": str(
                exc
            ),
        }

    return {
        "success": True,
        "status": "file_opened",
        "path": str(
            resolved
        ),
        "application": "default",
    }
