import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


import core.file_catalog as file_catalog
from core.file_catalog import (
    extract_local_file_action_request,
    get_approved_file_roots,
    search_local_files,
)
import core.workflows.file_actions as file_workflow
from core.orchestrator import (
    MaironCore,
)


def run():
    original_project_root = os.environ.get(
        "MAIRON_PROJECT_ROOT"
    )

    original_file_roots = os.environ.get(
        "MAIRON_FILE_ROOTS"
    )

    original_open = (
        file_workflow.open_approved_local_path
    )

    original_workflow_search = (
        file_workflow.search_local_files
    )

    original_catalog_roots = (
        file_catalog.get_approved_file_roots
    )

    original_workflow_roots = (
        file_workflow.get_approved_file_roots
    )

    try:
        file_workflow.search_local_files = (
            lambda query: file_catalog.search_local_files(
                query
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(
                temp_dir
            )

            project = root / "Mairon"
            docs = root / "Documents"

            project.mkdir()
            docs.mkdir()

            src_dir = project / "src"
            src_dir.mkdir()

            main_py = src_dir / "main.py"
            main_py.write_text(
                "print('hello')\n",
                encoding="utf-8",
            )

            resume = docs / "Oliver_Duck_Resume.pdf"
            resume.write_bytes(
                b"%PDF-test"
            )

            second_resume = docs / "Oliver_Duck_Cyber_Resume.pdf"
            second_resume.write_bytes(
                b"%PDF-test"
            )

            private_dir = project / "data" / "private"
            private_dir.mkdir(
                parents=True
            )

            secret = private_dir / "secret.txt"
            secret.write_text(
                "do not expose\n",
                encoding="utf-8",
            )

            env_file = project / ".env"
            env_file.write_text(
                "SECRET=x\n",
                encoding="utf-8",
            )

            dangerous = docs / "runme.ps1"
            dangerous.write_text(
                "Write-Host nope\n",
                encoding="utf-8",
            )

            os.environ[
                "MAIRON_PROJECT_ROOT"
            ] = str(
                project
            )

            os.environ[
                "MAIRON_FILE_ROOTS"
            ] = str(
                docs
            )

            isolated_roots = [
                project.resolve(),
                docs.resolve(),
            ]

            # Keep this unit test independent from whatever files happen to
            # exist in Oliver's real Documents/Downloads/Desktop/Pictures.
            file_catalog.get_approved_file_roots = (
                lambda: list(
                    isolated_roots
                )
            )

            file_workflow.get_approved_file_roots = (
                lambda: list(
                    isolated_roots
                )
            )

            # --------------------------------------------------
            # 1. Approved roots include configured project/root.
            # --------------------------------------------------

            roots = file_catalog.get_approved_file_roots()

            resolved_roots = {
                str(
                    item.resolve()
                )
                for item in roots
            }

            assert str(
                project.resolve()
            ) in resolved_roots

            assert str(
                docs.resolve()
            ) in resolved_roots

            # --------------------------------------------------
            # 2. Exact code filename resolves, secrets/executables do not.
            # --------------------------------------------------

            matches = search_local_files(
                "main.py"
            )

            assert len(
                matches
            ) == 1

            assert matches[
                0
            ][
                "path"
            ] == str(
                main_py.resolve()
            )

            assert search_local_files(
                ".env"
            ) == []

            assert search_local_files(
                "secret.txt"
            ) == []

            assert search_local_files(
                "runme.ps1"
            ) == []

            # --------------------------------------------------
            # 3. Parser catches file-specific opens and explicit finds,
            #    but not arbitrary app/game-like nouns.
            # --------------------------------------------------

            open_main = (
                extract_local_file_action_request(
                    "open main.py"
                )
            )

            assert open_main[
                "action"
            ] == "open_file"

            find_resume = (
                extract_local_file_action_request(
                    "find my resume"
                )
            )

            assert find_resume[
                "action"
            ] == "find_file"

            assert (
                extract_local_file_action_request(
                    "open Cyberpunk"
                )
                is None
            )

            assert (
                extract_local_file_action_request(
                    "open Spotify"
                )
                is None
            )

            # --------------------------------------------------
            # 4. Unique open goes through Core and stores verified referent.
            # --------------------------------------------------

            open_calls = []

            def fake_open(
                path,
            ):
                open_calls.append(
                    str(
                        Path(
                            path
                        ).resolve()
                    )
                )

                return {
                    "success": True,
                    "status": "file_opened",
                    "path": str(
                        Path(
                            path
                        ).resolve()
                    ),
                    "application": "vscode",
                }

            file_workflow.open_approved_local_path = (
                fake_open
            )

            core = MaironCore()

            opened = core.prepare_turn(
                "open main.py"
            )

            assert (
                opened.turn.intent
                == "open_local_file"
            )

            assert opened.direct_response == (
                "main.py is open."
            )

            assert open_calls == [
                str(
                    main_py.resolve()
                )
            ]

            assert (
                core.conversation_state
                .active_local_file_path
                == str(
                    main_py.resolve()
                )
            )

            # --------------------------------------------------
            # 5. Find with multiple matches does not guess/open.
            # --------------------------------------------------

            before = list(
                open_calls
            )

            found = core.prepare_turn(
                "find my resume"
            )

            assert (
                found.turn.intent
                == "find_local_file"
            )

            assert (
                "I found 2 approved local files"
                in found.direct_response
            )

            assert open_calls == before

            # Multiple-result search invalidates the old singular referent.
            assert (
                core.conversation_state
                .active_local_file_path
                is None
            )

            assert len(
                core.conversation_state
                .active_local_file_candidates
            ) == 2

            # --------------------------------------------------
            # 6. Deictic open only inherits after a unique file is active.
            # --------------------------------------------------

            # Re-establish file-open context.
            core.prepare_turn(
                "open main.py"
            )

            follow = core.prepare_turn(
                "open it"
            )

            assert (
                follow.turn.intent
                == "open_local_file"
            )

            assert (
                follow.turn.is_follow_up
                is True
            )

            assert open_calls[
                -1
            ] == str(
                main_py.resolve()
            )

            # --------------------------------------------------
            # 7. Desktop app/game commands remain outside file lane.
            # --------------------------------------------------

            spotify = core.prepare_turn(
                "open spotify"
            )

            assert spotify.turn.intent == (
                "launch_application"
            )

            # --------------------------------------------------
            # 8. No arbitrary shell execution in local file tool.
            # --------------------------------------------------

            source = (
                SRC_DIR
                / "tools"
                / "file_tools.py"
            ).read_text(
                encoding="utf-8",
            ).lower()

            assert "shell=true" not in source
            assert "powershell" not in source
            assert "taskkill" not in source

    finally:
        file_workflow.search_local_files = (
            original_workflow_search
        )

        file_workflow.open_approved_local_path = (
            original_open
        )

        file_catalog.get_approved_file_roots = (
            original_catalog_roots
        )

        file_workflow.get_approved_file_roots = (
            original_workflow_roots
        )

        if original_project_root is None:
            os.environ.pop(
                "MAIRON_PROJECT_ROOT",
                None,
            )
        else:
            os.environ[
                "MAIRON_PROJECT_ROOT"
            ] = original_project_root

        if original_file_roots is None:
            os.environ.pop(
                "MAIRON_FILE_ROOTS",
                None,
            )
        else:
            os.environ[
                "MAIRON_FILE_ROOTS"
            ] = original_file_roots

    print(
        "Mairon Phase 8.5 approved local file/folder action tests: PASS"
    )


if __name__ == "__main__":
    run()
