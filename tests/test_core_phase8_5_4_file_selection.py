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

            main_py = (
                project
                / "src"
                / "main.py"
            )
            main_py.write_text(
                "print('mairon')\n",
                encoding="utf-8",
            )

            # Dependency copy must be pruned.
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

            feasibility = (
                docs
                / "Feasibility Report.pdf"
            )
            feasibility.write_bytes(
                b"%PDF"
            )

            fent = (
                docs
                / "The Last Fent Bender.txt"
            )
            fent.write_text(
                "test\n",
                encoding="utf-8",
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

            open_calls = []

            def fake_open(
                path,
            ):
                resolved = str(
                    Path(
                        path
                    ).resolve()
                )

                open_calls.append(
                    resolved
                )

                return {
                    "success": True,
                    "status": "file_opened",
                    "path": resolved,
                    "application": "default",
                }

            file_workflow.open_approved_local_path = (
                fake_open
            )

            # --------------------------------------------------
            # 1. Huge/dependency trees cannot hide the actual project file.
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
                    main_py.resolve()
                )
            )

            # --------------------------------------------------
            # 2. Conversational filename wrappers are removed.
            # --------------------------------------------------

            request = (
                file_catalog.extract_local_file_action_request(
                    "find my file named The Last Fent Bender"
                )
            )

            assert request is not None
            assert request[
                "action"
            ] == "find_file"
            assert request[
                "query"
            ] == "The Last Fent Bender"

            fent_matches = (
                file_catalog.search_local_files(
                    request[
                        "query"
                    ]
                )
            )

            assert len(
                fent_matches
            ) == 1
            assert fent_matches[
                0
            ][
                "path"
            ] == str(
                fent.resolve()
            )

            # --------------------------------------------------
            # 3. Conservative typo tolerance handles one-word misspelling.
            # --------------------------------------------------

            typo_matches = (
                file_catalog.search_local_files(
                    "feasability report"
                )
            )

            assert typo_matches
            assert typo_matches[
                0
            ][
                "path"
            ] == str(
                feasibility.resolve()
            )

            # --------------------------------------------------
            # 4. Candidate-aware extension selection.
            # --------------------------------------------------

            core = MaironCore()

            found = core.prepare_turn(
                "find my resume"
            )

            assert (
                found.workflow_result.status
                == "multiple_matches"
            )
            assert (
                core.conversation_state
                .active_local_file_pending_action
                == "find"
            )

            before = len(
                open_calls
            )

            opened_pdf = core.prepare_turn(
                "open the pdf"
            )

            assert (
                opened_pdf.turn.intent
                == "open_local_file"
            )

            assert open_calls[
                -1
            ] == str(
                resume_pdf.resolve()
            )

            assert len(
                open_calls
            ) == before + 1

            # --------------------------------------------------
            # 5. Pending OPEN + bare filename completes that action.
            # --------------------------------------------------

            pending = core.prepare_turn(
                "open my resume"
            )

            assert (
                pending.workflow_result.status
                == "multiple_matches"
            )
            assert (
                core.conversation_state
                .active_local_file_pending_action
                == "open"
            )

            opened_by_name = core.prepare_turn(
                "Oliver Duck Resume.pdf"
            )

            assert (
                opened_by_name.turn.intent
                == "open_local_file"
            )

            assert open_calls[
                -1
            ] == str(
                resume_pdf.resolve()
            )

            # --------------------------------------------------
            # 6. FIND + bare descriptive candidate selects, but doesn't open.
            # --------------------------------------------------

            core.prepare_turn(
                "find my resume"
            )

            before = list(
                open_calls
            )

            selected = core.prepare_turn(
                "my resume pdf"
            )

            assert (
                selected.turn.intent
                == "select_local_file"
            )

            assert (
                selected.direct_response
                == "Selected Oliver Duck Resume.pdf."
            )

            assert open_calls == before

            assert (
                core.conversation_state
                .active_local_file_path
                == str(
                    resume_pdf.resolve()
                )
            )

            # --------------------------------------------------
            # 7. Explicit "open both files" opens the active candidate set.
            # --------------------------------------------------

            core.prepare_turn(
                "find my resume"
            )

            before_count = len(
                open_calls
            )

            both = core.prepare_turn(
                "open both files"
            )

            assert (
                both.turn.intent
                == "open_local_files"
            )

            assert len(
                open_calls
            ) == before_count + 2

            assert set(
                open_calls[
                    -2:
                ]
            ) == {
                str(
                    resume_docx.resolve()
                ),
                str(
                    resume_pdf.resolve()
                ),
            }

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
        "Mairon Phase 8.5.4 file search/selection tests: PASS"
    )


if __name__ == "__main__":
    run()
