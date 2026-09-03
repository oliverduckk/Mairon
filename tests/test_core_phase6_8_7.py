import os
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
    build_direct_context_window,
    build_direct_think_setting,
)


def run():
    # --------------------------------------------------
    # 1. Every direct-conversation lane gets enough active
    #    Ollama context for Mairon's >4K prompt.
    # --------------------------------------------------

    for intent in (
        "share_context",
        "acknowledge",
        "casual_conversation",
        "self_correction",
        "conversation_recall",
        "factual_question",
        "recommendation_request",
        "share_opinion",
        "action_request",
    ):
        assert (
            build_direct_context_window(
                intent
            )
            == 8192
        ), intent

    # --------------------------------------------------
    # 2. Straight factual Qwen/DeepSeek turns do not burn
    #    seconds/tokens on hidden reasoning for one-line facts.
    # --------------------------------------------------

    assert (
        build_direct_think_setting(
            "factual_question",
            model_name="qwen3.5:9b",
        )
        is False
    )

    assert (
        build_direct_think_setting(
            "factual_question",
            model_name="qwen3:14b",
        )
        is False
    )

    assert (
        build_direct_think_setting(
            "factual_question",
            model_name="deepseek-r1:14b",
        )
        is False
    )

    assert (
        build_direct_think_setting(
            "factual_question",
            model_name="gpt-oss:20b",
        )
        == "low"
    )

    assert (
        build_direct_think_setting(
            "factual_question",
            model_name="gemma3:12b",
        )
        is None
    )

    # --------------------------------------------------
    # 3. Acceptance cleanup 2 extends the no-thinking fast
    #    path to lightweight share_opinion turns on Qwen3.5.
    #    Recommendation/action lanes remain untouched.
    # --------------------------------------------------

    assert (
        build_direct_think_setting(
            "share_opinion",
            model_name="qwen3.5:9b",
        )
        is False
    )

    for intent in (
        "recommendation_request",
        "action_request",
    ):
        assert (
            build_direct_think_setting(
                intent,
                model_name="qwen3.5:9b",
            )
            is None
        ), intent

    print(
        "Mairon Core Phase 6.8.7 direct context/factual thinking tests: PASS"
    )


if __name__ == "__main__":
    run()
