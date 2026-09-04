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


def run():
    original_personal = (
        file_catalog.get_windows_personal_folder_paths
    )
    original_project_root = os.environ.get(
        "MAIRON_PROJECT_ROOT"
    )
    original_extra_roots = os.environ.get(
        "MAIRON_FILE_ROOTS"
    )

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(
                temp_dir
            )

            desktop = root / "Desktop"
            documents = root / "Documents"
            downloads = root / "Downloads"
            pictures = root / "PicturesRedirected"
            project = root / "Mairon"

            for path in (
                desktop,
                documents,
                downloads,
                pictures,
                project,
            ):
                path.mkdir(
                    parents=True
                )

            image = (
                pictures
                / "china-trip-photo.jpg"
            )
            image.write_bytes(
                b"jpg"
            )

            video_archive = (
                root
                / "Videos"
            )
            video_archive.mkdir()

            clip = (
                video_archive
                / "unnamed-game-clip.mp4"
            )
            clip.write_bytes(
                b"video"
            )

            file_catalog.get_windows_personal_folder_paths = (
                lambda: {
                    "desktop": desktop.resolve(),
                    "documents": documents.resolve(),
                    "downloads": downloads.resolve(),
                    "pictures": pictures.resolve(),
                }
            )

            os.environ[
                "MAIRON_PROJECT_ROOT"
            ] = str(
                project
            )

            os.environ.pop(
                "MAIRON_FILE_ROOTS",
                None,
            )

            roots = (
                file_catalog.get_approved_file_roots()
            )

            root_values = {
                str(
                    path.resolve()
                )
                for path in roots
            }

            assert str(
                pictures.resolve()
            ) in root_values

            assert str(
                video_archive.resolve()
            ) not in root_values

            file_catalog.clear_file_index_cache()

            matches = (
                file_catalog.search_local_files(
                    "china-trip-photo"
                )
            )

            assert len(
                matches
            ) == 1

            assert (
                matches[
                    0
                ][
                    "path"
                ]
                == str(
                    image.resolve()
                )
            )

            assert (
                file_catalog.search_local_files(
                    "unnamed-game-clip"
                )
                == []
            )

    finally:
        file_catalog.clear_file_index_cache()

        file_catalog.get_windows_personal_folder_paths = (
            original_personal
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

        if original_extra_roots is None:
            os.environ.pop(
                "MAIRON_FILE_ROOTS",
                None,
            )
        else:
            os.environ[
                "MAIRON_FILE_ROOTS"
            ] = original_extra_roots

    print(
        "Mairon Phase 8.5.7 Windows Known Folder tests: PASS"
    )


if __name__ == "__main__":
    run()
