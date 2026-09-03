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
        original_data_dir = (
            preference_store.DATA_DIR
        )

        original_db_path = (
            preference_store.DB_PATH
        )

        original_search = (
            preference_store.search_relevant_turns
        )

        original_load = (
            preference_store.load_conversation_turns
        )

        try:
            preference_store.DATA_DIR = Path(
                directory
            )

            preference_store.DB_PATH = (
                Path(directory)
                / "mairon.db"
            )

            # Simulate exactly the architectural failure:
            # semantic retrieval is polluted by several NEW failed recall
            # attempts and does not surface the old evidence.
            preference_store.search_relevant_turns = (
                lambda user_input, limit=12: [
                    {
                        "id": 500,
                        "session_id": "recent-a",
                        "user_text": (
                            "What did I say my top 3 manga were?"
                        ),
                        "assistant_text": (
                            "I don't have a stored ranking yet."
                        ),
                    },
                    {
                        "id": 510,
                        "session_id": "recent-b",
                        "user_text": (
                            "What are my top 3 manga?"
                        ),
                        "assistant_text": (
                            "I don't have a stored ranking yet."
                        ),
                    },
                ]
            )

            # Deterministic journal history still contains the original
            # authoritative contextual exchange.
            preference_store.load_conversation_turns = (
                lambda include_current_session=True,
                       newest_first=False,
                       limit=None: [
                    {
                        "id": 100,
                        "session_id": "old-session",
                        "user_text": (
                            "What is your top 3 manga?"
                        ),
                        "assistant_text": (
                            "One Piece, Berserk and Monster. You?"
                        ),
                    },
                    {
                        "id": 101,
                        "session_id": "old-session",
                        "user_text": (
                            "hmmmmmm Tokyo Ghoul, "
                            "20th Century Boys and Vinland Saga"
                        ),
                        "assistant_text": (
                            "Those are heavy hitters."
                        ),
                    },
                    # Unrelated later lists must not override the ranking.
                    {
                        "id": 300,
                        "session_id": "other-session",
                        "user_text": (
                            "Milk, eggs and bread"
                        ),
                        "assistant_text": (
                            "Fine."
                        ),
                    },
                    # Failed recalls are present in full history too.
                    {
                        "id": 500,
                        "session_id": "recent-a",
                        "user_text": (
                            "What did I say my top 3 manga were?"
                        ),
                        "assistant_text": (
                            "I don't have a stored ranking yet."
                        ),
                    },
                ]
            )

            recall = (
                preference_store
                .build_user_preference_recall_response(
                    "What did I say my top 3 manga were?",
                    user_name="Oliver",
                )
            )

            assert recall == (
                "Your top 3 manga are Tokyo Ghoul, "
                "20th Century Boys, and Vinland Saga."
            )

            stored = (
                preference_store
                .get_user_preference(
                    "manga",
                    "top_3",
                )
            )

            assert stored is not None

            assert stored["value"] == {
                "items": [
                    "Tokyo Ghoul",
                    "20th Century Boys",
                    "Vinland Saga",
                ]
            }

            assert stored["source_kind"] == (
                "conversation_journal_full_history_context_recovery"
            )

            # Once promoted, later recall is pure typed state and does not
            # need either retrieval path.
            preference_store.search_relevant_turns = (
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError(
                        "semantic search should not run after promotion"
                    )
                )
            )

            preference_store.load_conversation_turns = (
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError(
                        "full-history scan should not run after promotion"
                    )
                )
            )

            second = (
                preference_store
                .build_user_preference_recall_response(
                    "What are my top 3 manga?",
                    user_name="Oliver",
                )
            )

            assert second == recall

        finally:
            preference_store.DATA_DIR = (
                original_data_dir
            )

            preference_store.DB_PATH = (
                original_db_path
            )

            preference_store.search_relevant_turns = (
                original_search
            )

            preference_store.load_conversation_turns = (
                original_load
            )

    print(
        "Mairon acceptance cleanup 11 deterministic preference-migration "
        "fallback tests: PASS"
    )


if __name__ == "__main__":
    run()
