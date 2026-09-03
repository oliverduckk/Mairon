import tempfile
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

import sys

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


from memory import preference_store
from personality import opinion_ledger


def run():
    # --------------------------------------------------
    # 1. Mairon's existing Opinion Ledger now recognises
    #    generic category rankings without a media title.
    # --------------------------------------------------

    subject = (
        opinion_ledger
        .classify_opinion_subject(
            "What is your top 3 manga?"
        )
    )

    assert subject == {
        "key": "general::manga::top_3",
        "title": "Manga",
        "domain": "manga",
        "kind": "category_ranking",
        "count": 3,
        "label": "Mairon top 3 manga",
    }

    anime_subject = (
        opinion_ledger
        .classify_opinion_subject(
            "what are you top three animes?"
        )
    )

    assert anime_subject is not None
    assert anime_subject["domain"] == "anime"
    assert anime_subject["count"] == 3

    # Oliver stating his own preference must NOT be interpreted as
    # Mairon opinion state.
    assert (
        opinion_ledger
        .classify_opinion_subject(
            "My top 3 manga are Tokyo Ghoul, "
            "20th Century Boys and Vinland Saga"
        )
        is None
    )

    # --------------------------------------------------
    # 2. Mairon's first accepted category ranking becomes
    #    stable persona state; later stochastic rerolls are
    #    ignored unless revision is explicit.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as directory:
        private_dir = Path(
            directory
        )

        original_private_dir = (
            opinion_ledger.PRIVATE_DATA_DIR
        )

        original_ledger_path = (
            opinion_ledger.OPINION_LEDGER_PATH
        )

        try:
            opinion_ledger.PRIVATE_DATA_DIR = (
                private_dir
            )

            opinion_ledger.OPINION_LEDGER_PATH = (
                private_dir
                / "mairon_opinions.json"
            )

            first = (
                opinion_ledger
                .record_opinion_if_needed(
                    subject=subject,
                    response_text=(
                        "My top three are One Piece, Berserk, and Monster."
                    ),
                    existing_entry=None,
                    user_input=(
                        "What is your top 3 manga?"
                    ),
                    research_used=False,
                )
            )

            assert first is not None
            assert first["stance_text"] == (
                "My top three are One Piece, Berserk, and Monster."
            )

            loaded = (
                opinion_ledger
                .get_opinion_entry(
                    subject
                )
            )

            assert loaded is not None

            reroll = (
                opinion_ledger
                .record_opinion_if_needed(
                    subject=subject,
                    response_text=(
                        "Mushishi, Vagabond, and Chainsaw Man."
                    ),
                    existing_entry=loaded,
                    user_input=(
                        "What is your top 3 manga?"
                    ),
                    research_used=False,
                )
            )

            assert reroll["stance_text"] == (
                "My top three are One Piece, Berserk, and Monster."
            )

            context = (
                opinion_ledger
                .build_opinion_context_text(
                    loaded
                )
            )

            assert "Mairon top 3 manga" in context
            assert "One Piece, Berserk, and Monster" in context
            assert "Do not silently swap" in context

            revised = (
                opinion_ledger
                .record_opinion_if_needed(
                    subject=subject,
                    response_text=(
                        "You convinced me. My revised top three are "
                        "Berserk, Monster, and One Piece."
                    ),
                    existing_entry=loaded,
                    user_input=(
                        "Update your ranking after our discussion."
                    ),
                    research_used=False,
                )
            )

            assert revised["stance_text"].startswith(
                "You convinced me."
            )

            # --------------------------------------------------
            # 3. If no ledger entry exists yet, generic ranking
            #    can recover the latest real prior Mairon stance
            #    from the conversation journal.
            # --------------------------------------------------

            fresh_subject = (
                opinion_ledger
                .classify_opinion_subject(
                    "What is your top 3 anime?"
                )
            )

            original_search = (
                opinion_ledger.search_relevant_turns
            )

            try:
                opinion_ledger.search_relevant_turns = (
                    lambda user_input, limit=6: [
                        {
                            "id": 100,
                            "user_text": (
                                "What is your top 3 anime?"
                            ),
                            "assistant_text": (
                                "Bleach, Re Zero, and Hunter x Hunter."
                            ),
                        }
                    ]
                )

                recovered = (
                    opinion_ledger
                    .get_or_recover_opinion_entry(
                        user_input=(
                            "What is your top 3 anime?"
                        ),
                        subject=fresh_subject,
                    )
                )

            finally:
                opinion_ledger.search_relevant_turns = (
                    original_search
                )

            assert recovered is not None
            assert recovered["source"] == (
                "conversation_journal_recovery"
            )
            assert recovered["stance_text"] == (
                "Bleach, Re Zero, and Hunter x Hunter."
            )

        finally:
            opinion_ledger.PRIVATE_DATA_DIR = (
                original_private_dir
            )

            opinion_ledger.OPINION_LEDGER_PATH = (
                original_ledger_path
            )

    # --------------------------------------------------
    # 4. Oliver's explicit ranked preferences use separate
    #    typed user state, not the Mairon Opinion Ledger.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(
            directory
        )

        original_data_dir = (
            preference_store.DATA_DIR
        )

        original_db_path = (
            preference_store.DB_PATH
        )

        try:
            preference_store.DATA_DIR = (
                data_dir
            )

            preference_store.DB_PATH = (
                data_dir
                / "mairon.db"
            )

            explicit = (
                preference_store
                .capture_user_preference(
                    "My top 3 manga however would be "
                    "Tokyo Ghoul, 20th Century Boys and Vinland Saga"
                )
            )

            assert explicit is not None
            assert explicit["changed"] is True

            stored = (
                preference_store
                .get_user_preference(
                    "manga",
                    "top_3",
                )
            )

            assert stored["value"] == {
                "items": [
                    "Tokyo Ghoul",
                    "20th Century Boys",
                    "Vinland Saga",
                ]
            }

            # Explicit restatement updates the same typed preference.
            changed = (
                preference_store
                .capture_user_preference(
                    "My top 3 manga are Tokyo Ghoul, "
                    "Vinland Saga and 20th Century Boys"
                )
            )

            assert changed is not None
            assert changed["changed"] is True

            # Restore Oliver's current ranking for deterministic recall.
            preference_store.capture_user_preference(
                "My top 3 manga are Tokyo Ghoul, "
                "20th Century Boys and Vinland Saga"
            )

            recall = (
                preference_store
                .build_user_preference_recall_response(
                    "What were my top 3 manga?",
                    user_name="Oliver",
                )
            )

            assert recall == (
                "Your top 3 manga are Tokyo Ghoul, "
                "20th Century Boys, and Vinland Saga."
            )

            # --------------------------------------------------
            # 5. Terse contextual answers are only captured when
            #    the previous exchange clearly asked for Oliver's
            #    corresponding ranked preference.
            # --------------------------------------------------

            contextual = (
                preference_store
                .capture_user_preference(
                    "hmmmmmm Tokyo Ghoul, 20th Century Boys and Vinland Saga",
                    previous_assistant_text=(
                        "My top three? Fine. You?"
                    ),
                    previous_user_text=(
                        "What is your top 3 manga?"
                    ),
                )
            )

            assert contextual is not None

            unrelated = (
                preference_store
                .capture_user_preference(
                    "Berserk, Monster and Vagabond",
                    previous_assistant_text=(
                        "That weather sounds rough."
                    ),
                    previous_user_text=(
                        "Is it raining tomorrow?"
                    ),
                )
            )

            assert unrelated is None

            weak = (
                preference_store
                .capture_user_preference(
                    "Tokyo Ghoul is really good."
                )
            )

            assert weak is None

            # --------------------------------------------------
            # 6. If typed state is absent, explicit Oliver preference
            #    can be recovered from real user-authored journal text.
            # --------------------------------------------------

            # Use a different domain so the typed table is intentionally empty.
            original_search = (
                preference_store.search_relevant_turns
            )

            try:
                preference_store.search_relevant_turns = (
                    lambda user_input, limit=12: [
                        {
                            "id": 200,
                            "user_text": (
                                "My top 3 anime would be Bleach, "
                                "Re Zero and Hunter x Hunter"
                            ),
                            "assistant_text": (
                                "Fair list."
                            ),
                        }
                    ]
                )

                recovered_recall = (
                    preference_store
                    .build_user_preference_recall_response(
                        "What were my top 3 anime?",
                        user_name="Oliver",
                    )
                )

            finally:
                preference_store.search_relevant_turns = (
                    original_search
                )

            assert recovered_recall == (
                "Your top 3 anime are Bleach, Re Zero, and Hunter x Hunter."
            )

            recovered_user = (
                preference_store
                .get_user_preference(
                    "anime",
                    "top_3",
                )
            )

            assert recovered_user is not None
            assert recovered_user["source_kind"] == (
                "conversation_journal_recovery"
            )

        finally:
            preference_store.DATA_DIR = (
                original_data_dir
            )

            preference_store.DB_PATH = (
                original_db_path
            )

    # --------------------------------------------------
    # 6. Runtime main wiring persists explicit Oliver state
    #    and serves exact preference recall from Core.
    # --------------------------------------------------

    main_text = (
        SRC_DIR
        / "main.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "capture_user_preference(" in main_text
    assert "build_user_preference_recall_response(" in main_text
    assert "Core-owned preference recall" in main_text
    assert "last_user_input" in main_text
    assert "last_assistant_answer" in main_text

    print(
        "Mairon acceptance cleanup 4 persistent user/self-preference tests: PASS"
    )


if __name__ == "__main__":
    run()
