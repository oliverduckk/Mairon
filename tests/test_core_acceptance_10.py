import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


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
from core.temporal_context import (
    build_relative_date_context,
    find_relative_date_weekday_violations,
    resolve_relative_date_references,
)


def run():
    # --------------------------------------------------
    # 1. Ranked-preference recall grammar must separate
    #    the category from trailing question grammar.
    # --------------------------------------------------

    cases = (
        (
            "What did I say my top 3 manga were?",
            "manga",
            "top_3",
        ),
        (
            "What are my top 3 manga?",
            "manga",
            "top_3",
        ),
        (
            "Remind me what my top 5 chest exercises were again?",
            "chest exercises",
            "top_5",
        ),
    )

    for text, expected_domain, expected_key in cases:
        parsed = (
            preference_store
            .detect_user_ranked_preference_query(
                text
            )
        )

        assert parsed is not None
        assert parsed["domain"] == expected_domain
        assert parsed["preference_key"] == expected_key

    # --------------------------------------------------
    # 2. Historical contextual preference answers can be
    #    promoted from journal dialogue into typed state.
    # --------------------------------------------------

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

            preference_store.search_relevant_turns = (
                lambda user_input, limit=12: [
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
                "conversation_journal_context_recovery"
            )

            # No contextual recovery without a real same-dialogue preference
            # handoff. A nearby arbitrary list is not enough.
            preference_store.DB_PATH = (
                Path(directory)
                / "second.db"
            )

            unrelated_history = [
                {
                    "id": 200,
                    "session_id": "old-session",
                    "user_text": (
                        "Is it raining tomorrow?"
                    ),
                    "assistant_text": (
                        "Looks dry. You?"
                    ),
                },
                {
                    "id": 201,
                    "session_id": "old-session",
                    "user_text": (
                        "Tokyo Ghoul, "
                        "20th Century Boys and Vinland Saga"
                    ),
                    "assistant_text": (
                        "Fair enough."
                    ),
                },
            ]

            preference_store.search_relevant_turns = (
                lambda user_input, limit=12: list(
                    unrelated_history
                )
            )

            # Acceptance 11 added deterministic full-history fallback.
            # This negative test must therefore prove that NO valid evidence
            # exists in either retrieval path, rather than accidentally
            # falling through into the developer's real conversation journal.
            preference_store.load_conversation_turns = (
                lambda include_current_session=True,
                       newest_first=False,
                       limit=None: list(
                    unrelated_history
                )
            )

            missing = (
                preference_store
                .build_user_preference_recall_response(
                    "What were my top 3 manga?",
                    user_name="Oliver",
                )
            )

            assert (
                "don't have a stored"
                in missing.lower()
            )

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

    # --------------------------------------------------
    # 3. Relative calendar language is resolved by Core,
    #    not calculated/guessed by Qwen.
    # --------------------------------------------------

    fixed_now = datetime(
        2026,
        9,
        3,
        15,
        24,
        tzinfo=ZoneInfo(
            "Australia/Sydney"
        ),
    )

    expected = {
        "last night": (
            "2026-09-02",
            "Wednesday",
        ),
        "yesterday": (
            "2026-09-02",
            "Wednesday",
        ),
        "today": (
            "2026-09-03",
            "Thursday",
        ),
        "tonight": (
            "2026-09-03",
            "Thursday",
        ),
        "tomorrow": (
            "2026-09-04",
            "Friday",
        ),
        "day after tomorrow": (
            "2026-09-05",
            "Saturday",
        ),
    }

    for phrase, (date_value, weekday) in expected.items():
        resolved = (
            resolve_relative_date_references(
                f"I mean {phrase}.",
                now=fixed_now,
            )
        )

        assert len(resolved) == 1
        assert resolved[0]["date"] == date_value
        assert resolved[0]["weekday"] == weekday

    context = (
        build_relative_date_context(
            "I watched it last night.",
            now=fixed_now,
        )
    )

    assert "2026-09-02" in context
    assert "Wednesday" in context
    assert "Core" in context

    violations = (
        find_relative_date_weekday_violations(
            user_input="I watched it last night.",
            draft="That's a bold choice for a Tuesday.",
            now=fixed_now,
        )
    )

    assert any(
        "relative-date weekday mismatch"
        in item
        for item in violations
    )

    assert (
        find_relative_date_weekday_violations(
            user_input="I watched it last night.",
            draft="That's a bold choice for a Wednesday.",
            now=fixed_now,
        )
        == []
    )

    assert (
        find_relative_date_weekday_violations(
            user_input="I watched it.",
            draft="Tuesday was busy.",
            now=fixed_now,
        )
        == []
    )

    # --------------------------------------------------
    # 4. Provider integration must use Core temporal state
    #    on direct conversation turns.
    # --------------------------------------------------

    provider_text = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "build_relative_date_context" in provider_text
    assert "find_relative_date_weekday_violations" in provider_text
    assert "CORE-RESOLVED" not in provider_text

    print(
        "Mairon acceptance cleanup 10 preference migration / "
        "relative-calendar grounding tests: PASS"
    )


if __name__ == "__main__":
    run()
