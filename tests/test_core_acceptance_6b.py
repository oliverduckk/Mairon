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


from core.intent_router import classify_turn
from memory import preference_store


def run():
    # --------------------------------------------------
    # 1. Generic content-generation/planning imperatives must
    #    not fall into casual_conversation.
    # --------------------------------------------------

    generation_requests = (
        "Give me a full 5-day Push/Pull/Legs/Upper/Lower gym routine with exercises, sets and reps for every day.",
        "Write me a detailed essay about DNS security.",
        "Create a packing list for a three-week trip.",
        "Build me a PC parts list under $2500.",
        "Put together a study plan for my exam.",
        "Come up with a detailed migration plan.",
    )

    for text in generation_requests:
        state = classify_turn(
            text
        )

        assert (
            state.intent
            == "recommendation_request"
        ), (
            text,
            state.intent,
        )

    # Ordinary conversational statements and idioms that merely begin with
    # an imperative-looking verb must remain outside content generation.
    assert (
        classify_turn(
            "I finally cleaned my desk this morning."
        ).intent
        == "share_context"
    )

    assert (
        classify_turn(
            "Give it two days and it'll probably be fucked again."
        ).intent
        == "casual_conversation"
    )

    assert (
        classify_turn(
            "Give him a minute, he'll figure it out."
        ).intent
        != "recommendation_request"
    )

    assert (
        classify_turn(
            "Make it three days instead."
        ).intent
        != "recommendation_request"
    )

    # --------------------------------------------------
    # 2. Contextual preference capture must accept an actual
    #    answer-shaped list but reject a fresh request that merely
    #    happens to split into the expected number of pieces.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as directory:
        original_path = (
            preference_store.DB_PATH
        )

        try:
            preference_store.DB_PATH = (
                Path(directory)
                / "preferences.db"
            )

            previous_user = (
                "What are your top 3 Hollywood actors?"
            )

            previous_assistant = (
                "Mine are Meryl Streep, Daniel Day-Lewis and Cate Blanchett. You?"
            )

            captured = (
                preference_store.capture_user_preference(
                    user_text=(
                        "Denzel Washington, "
                        "Leonardo DiCaprio and "
                        "Christian Bale"
                    ),
                    previous_assistant_text=(
                        previous_assistant
                    ),
                    previous_user_text=(
                        previous_user
                    ),
                )
            )

            assert (
                captured is not None
            )

            before = (
                preference_store.list_user_preferences()
            )

            # This exact structural class caused the production corruption:
            # a fresh request with commas/"and" must never become a preference.
            rejected_requests = (
                "Give me a routine with exercises, sets and reps for every day.",
                "Create a packing list with clothes, toiletries and electronics.",
                "Write me a plan with goals, milestones and risks.",
                "What are the best movies, books and games?",
            )

            for text in rejected_requests:
                assert (
                    preference_store.capture_user_preference(
                        user_text=text,
                        previous_assistant_text=(
                            previous_assistant
                        ),
                        previous_user_text=(
                            previous_user
                        ),
                    )
                    is None
                ), text

            after = (
                preference_store.list_user_preferences()
            )

            assert (
                before
                == after
            )

            # Explicit preference declarations remain authoritative regardless
            # of the command/question guard used for contextual answers.
            explicit = (
                preference_store.capture_user_preference(
                    user_text=(
                        "My top 3 Hollywood actors are "
                        "Denzel Washington, "
                        "Leonardo DiCaprio and "
                        "Christian Bale"
                    ),
                )
            )

            assert (
                explicit is not None
            )

        finally:
            preference_store.DB_PATH = (
                original_path
            )

    print(
        "Mairon acceptance cleanup 6 request-boundary/preference-state tests: PASS"
    )


if __name__ == "__main__":
    run()
