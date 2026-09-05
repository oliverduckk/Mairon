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

            front = (
                root
                / "Drivers License.jpeg"
            )
            back = (
                root
                / "Back of Drivers License.jpeg"
            )
            passport = (
                root
                / "Passport photo.PNG"
            )

            front.write_bytes(
                b"front"
            )
            back.write_bytes(
                b"back"
            )
            passport.write_bytes(
                b"passport"
            )

            roots = [
                root.resolve()
            ]

            file_catalog.get_approved_file_roots = (
                lambda: list(
                    roots
                )
            )

            file_workflow.get_approved_file_roots = (
                lambda: list(
                    roots
                )
            )

            file_catalog.clear_file_index_cache()

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

            core = MaironCore()

            # --------------------------------------------------
            # 1. Compound find + open resolves the query, not literal tail.
            # --------------------------------------------------

            compound = core.prepare_turn(
                "find passport and open it"
            )

            assert (
                compound.turn.intent
                == "open_local_file"
            )

            assert (
                compound.direct_response
                == "Passport photo.PNG is open."
            )

            assert open_calls[
                -1
            ] == str(
                passport.resolve()
            )

            # --------------------------------------------------
            # 2. Ambiguous result + open it stays in file lane.
            # --------------------------------------------------

            ambiguous = core.prepare_turn(
                "find drivers license"
            )

            assert (
                ambiguous.workflow_result.status
                == "multiple_matches"
            )

            before = list(
                open_calls
            )

            unresolved = core.prepare_turn(
                "open it"
            )

            assert (
                unresolved.turn.intent
                == "local_file_choice_required"
            )

            assert (
                "Tell me which one you want."
                in unresolved.direct_response
            )

            assert open_calls == before

            # --------------------------------------------------
            # 3. "second one" selects candidate index 1, not word "one".
            # --------------------------------------------------

            second = core.prepare_turn(
                "open the second one"
            )

            assert (
                second.turn.intent
                == "open_local_file"
            )

            assert open_calls[
                -1
            ] == str(
                back.resolve()
            ), open_calls

    finally:
        file_catalog.clear_file_index_cache()

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
        "Mairon Phase 8.5.8 compound/ordinal file tests: PASS"
    )


if __name__ == "__main__":
    run()
