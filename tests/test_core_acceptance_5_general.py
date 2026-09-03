import ast
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def _load_selected(path, function_names=(), constant_names=()):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in function_names:
                body.append(node)
                continue

        if isinstance(node, ast.Assign):
            names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }

            if names.intersection(constant_names):
                body.append(node)

    namespace = {
        "re": re,
    }

    exec(
        compile(
            ast.Module(
                body=body,
                type_ignores=[],
            ),
            str(path),
            "exec",
        ),
        namespace,
    )

    return namespace


def run():
    provider_path = SRC_DIR / "ai" / "ollama_provider.py"
    relationship_path = SRC_DIR / "personality" / "relationship_state.py"
    spoiler_path = SRC_DIR / "personality" / "spoiler_guard.py"
    media_research_path = SRC_DIR / "research" / "media_research.py"
    opinion_ledger_path = SRC_DIR / "personality" / "opinion_ledger.py"
    preference_store_path = SRC_DIR / "memory" / "preference_store.py"

    provider_text = provider_path.read_text(encoding="utf-8")

    # --------------------------------------------------
    # 1. Output-length handling is universal, not scenario-shaped.
    # --------------------------------------------------

    provider_ns = _load_selected(
        provider_path,
        function_names=(
            "generation_stopped_for_length",
            "build_runtime_output_budget",
            "build_runtime_context_window",
        ),
        constant_names=(
            "MIN_DIRECT_OUTPUT_BUDGET",
            "MAX_DIRECT_OUTPUT_BUDGET",
            "GENERATION_TRUNCATION_VIOLATION",
        ),
    )

    stopped_for_length = provider_ns[
        "generation_stopped_for_length"
    ]

    build_budget = provider_ns[
        "build_runtime_output_budget"
    ]

    truncation_violation = provider_ns[
        "GENERATION_TRUNCATION_VIOLATION"
    ]

    assert stopped_for_length("length") is True
    assert stopped_for_length("LENGTH") is True
    assert stopped_for_length("stop") is False
    assert stopped_for_length(None) is False

    # Tiny historical lane caps are now only soft configuration inputs.
    # Runtime gives every topic enough generic headroom to finish naturally.
    assert build_budget(
        {"num_predict": 96},
        0,
    ) == 1024

    assert build_budget(
        {"num_predict": 112},
        0,
    ) == 1024

    assert build_budget(
        {},
        0,
    ) == 1024

    assert build_budget(
        {"num_predict": 700},
        0,
    ) == 1024

    # Only a real length stop expands the next attempt.
    assert build_budget(
        {"num_predict": 96},
        1,
    ) == 2048

    assert build_budget(
        {"num_predict": 96},
        2,
    ) == 4096

    # Hard ceiling remains a runaway safety boundary, not a normal target.
    assert build_budget(
        {"num_predict": 9000},
        0,
    ) == 4096

    build_context = provider_ns[
        "build_runtime_context_window"
    ]

    assert build_context(
        8192,
        1024,
    ) == 8192

    assert build_context(
        8192,
        2048,
    ) == 8192

    assert build_context(
        8192,
        4096,
    ) == 16384

    assert "COMPLETION RETRY" in provider_text
    assert "original request" in provider_text.lower()
    assert "requested sections, items, steps, explanations" in provider_text

    # Regression against benchmark-specific architecture.
    assert "OPINION-RANKING RETRY" not in provider_text
    assert "opinion ranking hit the generation limit" not in provider_text
    assert "find_opinion_ranking_completion_violations" not in provider_text
    assert "build_opinion_ranking_instruction" not in provider_text

    # A known-incomplete draft must be rejected before expensive validators.
    length_guard_index = provider_text.index(
        "if generation_stopped_for_length("
    )

    personality_validation_index = provider_text.index(
        "find_personality_violations(",
        length_guard_index,
    )

    assert length_guard_index < personality_validation_index

    # --------------------------------------------------
    # 2. Stable Core-owned Mairon opinions may repeat.
    # --------------------------------------------------

    relationship_text = relationship_path.read_text(
        encoding="utf-8"
    )

    assert "allow_stable_repeat=False" in relationship_text
    assert "if allow_stable_repeat:" in relationship_text
    assert "allow_stable_repeat=bool(" in provider_text
    assert "opinion_entry" in provider_text

    # --------------------------------------------------
    # 3. New questions do not inherit stale media context merely
    #    because they start with an interrogative word.
    # --------------------------------------------------

    spoiler_ns = _load_selected(
        spoiler_path,
        function_names=(
            "_normalise_text",
            "_looks_like_media_follow_up",
        ),
    )

    looks_like_follow_up = spoiler_ns[
        "_looks_like_media_follow_up"
    ]

    assert looks_like_follow_up(
        "what are your favourite actors?"
    ) is False

    assert looks_like_follow_up(
        "what gym routine would you build for me?"
    ) is False

    assert looks_like_follow_up(
        "what happened to him?"
    ) is True

    assert looks_like_follow_up(
        "and what about that?"
    ) is True

    assert looks_like_follow_up(
        "why did they do that?"
    ) is True

    # --------------------------------------------------
    # 4. Subjective opinion alone does not launch heavyweight
    #    media research; factual/current media questions still can.
    # --------------------------------------------------

    media_ns = _load_selected(
        media_research_path,
        function_names=(
            "_normalise",
            "_matches_any",
            "should_research_media_turn",
        ),
        constant_names=(
            "FACT_CHECK_PATTERNS",
            "SPECIFIC_FACT_PATTERNS",
            "CURRENT_PATTERNS",
        ),
    )

    should_research = media_ns[
        "should_research_media_turn"
    ]

    base_spoiler = {
        "title": "One Piece",
        "must_ask_progress": False,
        "must_complete_progress": False,
        "must_confirm_latest": False,
        "progress_updated": False,
        "pending_question": None,
    }

    assert should_research(
        user_input="What do you think of One Piece?",
        conversation_policy={
            "opinion_turn": True,
            "challenge_turn": False,
        },
        spoiler_context=base_spoiler,
    ) is False

    assert should_research(
        user_input="What happened to Ace?",
        conversation_policy={
            "opinion_turn": False,
            "challenge_turn": False,
        },
        spoiler_context=base_spoiler,
    ) is True

    assert should_research(
        user_input="What is the latest One Piece chapter?",
        conversation_policy={
            "opinion_turn": False,
            "challenge_turn": False,
        },
        spoiler_context=base_spoiler,
    ) is True

    # --------------------------------------------------
    # 5. Ranked Mairon persona subjects are generic noun phrases,
    #    not a hard-coded manga/anime/actor vocabulary.
    # --------------------------------------------------

    opinion_ns = _load_selected(
        opinion_ledger_path,
        function_names=(
            "_normalise",
            "_normalise_key",
            "_parse_rank_count",
            "_normalise_ranking_subject_phrase",
            "_classify_generic_category_ranking",
        ),
        constant_names=(
            "RANK_COUNT_WORDS",
            "GENERIC_RANKING_PATTERN",
            "RANKING_SUBJECT_TRAILING_QUALIFIERS",
            "RANKING_SUBJECT_ALIASES",
        ),
    )

    classify_ranking = opinion_ns[
        "_classify_generic_category_ranking"
    ]

    normalise = opinion_ns[
        "_normalise"
    ]

    examples = (
        (
            "what are your top 3 hollywood actors?",
            "general::hollywood_actors::top_3",
            "hollywood actors",
            3,
        ),
        (
            "what are your top five exercises for chest?",
            "general::exercises_for_chest::top_5",
            "exercises for chest",
            5,
        ),
        (
            "what are your top 4 holiday destinations of all time?",
            "general::holiday_destinations::top_4",
            "holiday destinations",
            4,
        ),
    )

    for text, key, domain, count in examples:
        subject = classify_ranking(
            normalise(text)
        )

        assert subject is not None
        assert subject["key"] == key
        assert subject["domain"] == domain
        assert subject["count"] == count

    ledger_text = opinion_ledger_path.read_text(
        encoding="utf-8"
    )

    assert "GENERIC_RANKING_DOMAINS" not in ledger_text

    # --------------------------------------------------
    # 6. Oliver's explicit ranked preferences support generic
    #    multi-word subjects too.
    # --------------------------------------------------

    preference_ns = _load_selected(
        preference_store_path,
        function_names=(
            "_normalise_domain",
            "_clean_ranked_domain_phrase",
            "_parse_count_token",
            "detect_user_ranked_preference_query",
            "_clean_item",
            "_split_ranked_items",
            "_extract_explicit_ranked_preference",
        ),
        constant_names=(
            "DOMAIN_ALIASES",
            "NUMBER_WORDS",
            "FILLER_PREFIX_RE",
        ),
    )

    detect_user_query = preference_ns[
        "detect_user_ranked_preference_query"
    ]

    extract_user_preference = preference_ns[
        "_extract_explicit_ranked_preference"
    ]

    exercise_query = detect_user_query(
        "what were my top five exercises for chest?"
    )

    assert exercise_query == {
        "domain": "exercises for chest",
        "count": 5,
        "preference_key": "top_5",
    }

    exercise_preference = extract_user_preference(
        "my top 5 exercises for chest are incline press, cable fly, dips, "
        "push ups and machine press"
    )

    assert exercise_preference is not None
    assert exercise_preference["domain"] == "exercises for chest"
    assert exercise_preference["items"] == [
        "incline press",
        "cable fly",
        "dips",
        "push ups",
        "machine press",
    ]

    print(
        "Mairon acceptance cleanup 5 broad generation/context/state tests: PASS"
    )


if __name__ == "__main__":
    run()
