import inspect
import sys
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


from ai.ollama_provider import (
    build_direct_generation_options,
    build_direct_think_setting,
    handle_direct_conversation,
)


def run():
    # --------------------------------------------------
    # 1. Tiny Core-owned/restricted lanes must disable
    #    Qwen3 hidden thinking.
    # --------------------------------------------------

    for intent in (
        "share_context",
        "acknowledge",
        "casual_conversation",
        "self_correction",
        "conversation_recall",
        "factual_question",
    ):
        assert (
            build_direct_think_setting(
                intent
            )
            is False
        ), intent

    # Heavier reasoning/opinion/action lanes retain provider/model default.
    for intent in (
        "recommendation_request",
        "share_opinion",
        "action_request",
    ):
        assert (
            build_direct_think_setting(
                intent
            )
            is None
        ), intent

    # --------------------------------------------------
    # 2. Bounded visible-output caps remain in place. The
    #    social budget is large enough to finish a short reply
    #    while hidden thinking remains disabled.
    # --------------------------------------------------

    assert (
        build_direct_generation_options(
            "casual_conversation"
        )
        == {
            "temperature": 0.35,
            "num_predict": 160,
        }
    )

    assert (
        build_direct_generation_options(
            "conversation_recall"
        )
        == {
            "temperature": 0.1,
            "num_predict": 128,
        }
    )

    # --------------------------------------------------
    # 3. Runtime wiring must pass think_setting to Ollama
    #    and short-circuit empty drafts before semantic
    #    grounding.
    # --------------------------------------------------

    source = inspect.getsource(
        handle_direct_conversation
    )

    assert (
        'build_direct_think_setting('
        in source
    )

    assert (
        '"think"'
        in source
    )

    empty_guard = source.index(
        "if not draft_text:"
    )

    grounding_call = source.index(
        "verify_core_grounded_draft("
    )

    assert (
        empty_guard
        < grounding_call
    )

    assert (
        "local model produced thinking but no visible response"
        in source
    )

    assert (
        "continue"
        in source[
            empty_guard:
            grounding_call
        ]
    )

    print(
        "Mairon Core Phase 6.7.1 Qwen thinking-budget tests: PASS"
    )


if __name__ == "__main__":
    run()
