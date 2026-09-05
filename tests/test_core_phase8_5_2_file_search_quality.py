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
import core.workflows.file_actions as file_workflow
from core.orchestrator import (
    MaironCore,
)


def run():
    original_catalog_roots = (
        file_catalog.get_approved_file_roots
    )
    original_workflow_roots = (
        file_workflow.get_approved_file_roots
    )
    original_open = (
        file_workflow.open_approved_local_path
    )

    original_workflow_search = (
        file_workflow.search_local_files
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

            (project / "src").mkdir(
                parents=True
            )
            docs.mkdir()

            real_main = (
                project
                / "src"
                / "main.py"
            )
            real_main.write_text(
                "print('mairon')\n",
                encoding="utf-8",
            )

            dependency_main = (
                docs
                / "old-project"
                / "env"
                / "Lib"
                / "site-packages"
                / "package"
                / "main.py"
            )

            dependency_main.parent.mkdir(
                parents=True
            )

            dependency_main.write_text(
                "print('dependency')\n",
                encoding="utf-8",
            )

            (
                docs
                / "old-project"
                / "env"
                / "pyvenv.cfg"
            ).write_text(
                "home = test\n",
                encoding="utf-8",
            )

            resume_docx = (
                docs
                / "Oliver Duck Resume.docx"
            )
            resume_pdf = (
                docs
                / "Oliver Duck Resume.pdf"
            )

            resume_docx.write_bytes(
                b"docx"
            )

            resume_pdf.write_bytes(
                b"%PDF"
            )

            isolated_roots = [
                project.resolve(),
                docs.resolve(),
            ]

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
            # 1. Python virtual environments/dependency trees are pruned.
            # --------------------------------------------------

            matches = file_catalog.search_local_files(
                "main.py"
            )

            assert len(
                matches
            ) == 1, matches

            assert (
                matches[0][
                    "path"
                ]
                == str(
                    real_main.resolve()
                )
            )

            # --------------------------------------------------
            # 2. Ambiguous results invalidate any older singular referent.
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

            assert opened.direct_response == (
                "main.py is open."
            )

            assert (
                core.conversation_state
                .active_local_file_path
                == str(
                    real_main.resolve()
                )
            )

            ambiguous = core.prepare_turn(
                "find my resume"
            )

            assert (
                ambiguous.workflow_result.status
                == "multiple_matches"
            )

            assert (
                core.conversation_state
                .active_local_file_path
                is None
            )

            assert len(
                core.conversation_state
                .active_local_file_candidates
            ) == 2

            before = list(
                open_calls
            )

            follow = core.prepare_turn(
                "open it"
            )

            assert (
                follow.turn.intent
                != "open_local_file"
            )

            assert open_calls == before

    finally:
        file_catalog.get_approved_file_roots = (
            original_catalog_roots
        )

        file_workflow.get_approved_file_roots = (
            original_workflow_roots
        )

        file_workflow.search_local_files = (
            original_workflow_search
        )

        file_workflow.open_approved_local_path = (
            original_open
        )

    print(
        "Mairon Phase 8.5.2 file search pruning / "
        "ambiguity-state tests: PASS"
    )


if __name__ == "__main__":
    run()
