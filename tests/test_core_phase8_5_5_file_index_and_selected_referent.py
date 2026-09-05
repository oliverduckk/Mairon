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
    original_walk = file_catalog.os.walk

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

            file_catalog.clear_file_index_cache()

            walk_calls = []

            def counting_walk(*args, **kwargs):
                walk_calls.append(
                    str(args[0])
                )
                return original_walk(
                    *args,
                    **kwargs,
                )

            file_catalog.os.walk = (
                counting_walk
            )

            # --------------------------------------------------
            # 1. First search builds the index.
            # --------------------------------------------------

            first = file_catalog.search_local_files(
                "main.py"
            )

            assert len(first) == 1, first
            assert first[0]["path"] == str(
                main_py.resolve()
            )

            first_walk_count = len(
                walk_calls
            )

            assert first_walk_count == len(
                isolated_roots
            )

            # --------------------------------------------------
            # 2. Second search reuses the session index.
            # --------------------------------------------------

            second = file_catalog.search_local_files(
                "resume"
            )

            assert len(second) == 2, second
            assert len(walk_calls) == first_walk_count

            # --------------------------------------------------
            # 3. A miss on the current cache refreshes once.
            # --------------------------------------------------

            missing = file_catalog.search_local_files(
                "definitely nonexistent report"
            )

            assert missing == []
            assert len(walk_calls) == (
                first_walk_count
                + len(isolated_roots)
            )

            # --------------------------------------------------
            # 4. Selecting a candidate creates a valid singular referent.
            #    "open it" must stay in the local-file lane.
            # --------------------------------------------------

            open_calls = []

            def fake_open(path):
                resolved = str(
                    Path(path).resolve()
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

            core = MaironCore()

            found = core.prepare_turn(
                "find my resume"
            )

            assert (
                found.workflow_result.status
                == "multiple_matches"
            )

            selected = core.prepare_turn(
                "my resume pdf"
            )

            assert (
                selected.turn.intent
                == "select_local_file"
            )
            assert (
                core.conversation_state
                .active_local_file_path
                == str(
                    resume_pdf.resolve()
                )
            )

            opened = core.prepare_turn(
                "open it"
            )

            assert (
                opened.turn.intent
                == "open_local_file"
            ), opened.turn.to_dict()

            assert open_calls[-1] == str(
                resume_pdf.resolve()
            )

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
        file_catalog.os.walk = original_walk
        file_catalog.clear_file_index_cache()

    print(
        "Mairon Phase 8.5.5 file index / selected referent tests: PASS"
    )


if __name__ == "__main__":
    run()
