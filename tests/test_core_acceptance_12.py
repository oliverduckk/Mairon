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


from memory import preference_store


def run():
    with tempfile.TemporaryDirectory() as directory:
        original_data_dir = preference_store.DATA_DIR
        original_db_path = preference_store.DB_PATH

        try:
            preference_store.DATA_DIR = Path(
                directory
            )

            preference_store.DB_PATH = (
                Path(directory)
                / "mairon.db"
            )

            preference_store.set_user_preference(
                domain="anime",
                preference_key="top_3",
                value={
                    "items": [
                        "Re: Zero",
                        "Bleach",
                        "maybe One Piece or Naruto",
                    ]
                },
                source_text="existing typed preference",
            )

            # --------------------------------------------------
            # 1. Natural correction after an immediate Core-owned
            #    preference recall can replace the COMPLETE ranking
            #    without restating "my top 3 anime are...".
            # --------------------------------------------------

            revised = (
                preference_store.capture_user_preference(
                    user_text=(
                        "Actually fuck it, Naruto is definitely third. "
                        "So Re:Zero, Bleach and Naruto."
                    ),
                    previous_assistant_text=(
                        "Your top 3 anime are Re: Zero, Bleach, "
                        "and maybe One Piece or Naruto."
                    ),
                    previous_user_text=(
                        "What are my top 3 anime?"
                    ),
                )
            )

            assert revised is not None
            assert revised["changed"] is True
            assert revised["domain"] == "anime"
            assert revised["preference_key"] == "top_3"
            assert revised["value"] == {
                "items": [
                    "Re:Zero",
                    "Bleach",
                    "Naruto",
                ]
            }

            stored = (
                preference_store.get_user_preference(
                    "anime",
                    "top_3",
                )
            )

            assert stored["value"] == {
                "items": [
                    "Re:Zero",
                    "Bleach",
                    "Naruto",
                ]
            }

            assert stored["source_kind"] == (
                "user_preference_revision"
            )

            # --------------------------------------------------
            # 2. A declarative Core recall is NOT a preference
            #    handoff. An unrelated N-item list after recall
            #    must never silently overwrite typed state.
            # --------------------------------------------------

            unrelated = (
                preference_store.capture_user_preference(
                    user_text=(
                        "Milk, eggs and bread"
                    ),
                    previous_assistant_text=(
                        "Your top 3 anime are Re:Zero, "
                        "Bleach, and Naruto."
                    ),
                    previous_user_text=(
                        "What are my top 3 anime?"
                    ),
                )
            )

            assert unrelated is None

            assert (
                preference_store.get_user_preference(
                    "anime",
                    "top_3",
                )["value"]
                == {
                    "items": [
                        "Re:Zero",
                        "Bleach",
                        "Naruto",
                    ]
                }
            )

            # --------------------------------------------------
            # 3. Genuine reciprocal preference handoffs continue
            #    to work exactly as before.
            # --------------------------------------------------

            handoff = (
                preference_store.capture_user_preference(
                    user_text=(
                        "Tokyo Ghoul, "
                        "20th Century Boys and Vinland Saga"
                    ),
                    previous_assistant_text=(
                        "Mine are One Piece, Berserk and Monster. You?"
                    ),
                    previous_user_text=(
                        "What is your top 3 manga?"
                    ),
                )
            )

            assert handoff is not None
            assert handoff["domain"] == "manga"
            assert handoff["preference_key"] == "top_3"
            assert handoff["value"] == {
                "items": [
                    "Tokyo Ghoul",
                    "20th Century Boys",
                    "Vinland Saga",
                ]
            }

            # --------------------------------------------------
            # 4. An incomplete correction must NOT be guessed into
            #    a full ranking. Partial edit operations are a
            #    separate capability/state transition.
            # --------------------------------------------------

            incomplete = (
                preference_store.capture_user_preference(
                    user_text=(
                        "Actually Naruto is definitely third now."
                    ),
                    previous_assistant_text=(
                        "Your top 3 anime are Re:Zero, "
                        "Bleach, and Naruto."
                    ),
                    previous_user_text=(
                        "What are my top 3 anime?"
                    ),
                )
            )

            assert incomplete is None

            # --------------------------------------------------
            # 5. Explicit declarations remain authoritative.
            # --------------------------------------------------

            explicit = (
                preference_store.capture_user_preference(
                    user_text=(
                        "My top 3 games are Elden Ring, "
                        "Minecraft and Cyberpunk 2077"
                    )
                )
            )

            assert explicit is not None
            assert explicit["domain"] == "game"
            assert explicit["value"] == {
                "items": [
                    "Elden Ring",
                    "Minecraft",
                    "Cyberpunk 2077",
                ]
            }

        finally:
            preference_store.DATA_DIR = original_data_dir
            preference_store.DB_PATH = original_db_path

    print(
        "Mairon acceptance cleanup 12 ranked-preference "
        "revision transition tests: PASS"
    )


if __name__ == "__main__":
    run()
