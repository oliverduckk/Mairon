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
    original_roots = (
        file_catalog.get_approved_file_roots
    )

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(
                temp_dir
            )

            video = (
                root
                / "Listen To Your Masta.mp4"
            )

            audio = (
                root
                / "Tame Impala.flac"
            )

            executable = (
                root
                / "Definitely Normal Video.exe"
            )

            video.write_bytes(
                b"video"
            )

            audio.write_bytes(
                b"audio"
            )

            executable.write_bytes(
                b"nope"
            )

            file_catalog.get_approved_file_roots = (
                lambda: [
                    root.resolve()
                ]
            )

            file_catalog.clear_file_index_cache()

            video_matches = (
                file_catalog.search_local_files(
                    "listen to your masta.mp4"
                )
            )

            assert len(
                video_matches
            ) == 1

            assert (
                video_matches[
                    0
                ][
                    "path"
                ]
                == str(
                    video.resolve()
                )
            )

            audio_matches = (
                file_catalog.search_local_files(
                    "Tame Impala"
                )
            )

            assert len(
                audio_matches
            ) == 1

            assert (
                audio_matches[
                    0
                ][
                    "path"
                ]
                == str(
                    audio.resolve()
                )
            )

            assert (
                file_catalog.search_local_files(
                    "Definitely Normal Video.exe"
                )
                == []
            )

    finally:
        file_catalog.clear_file_index_cache()

        file_catalog.get_approved_file_roots = (
            original_roots
        )

    print(
        "Mairon Phase 8.5.6 media-file search tests: PASS"
    )


if __name__ == "__main__":
    run()
