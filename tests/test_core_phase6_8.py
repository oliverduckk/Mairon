import inspect
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
    DEFAULT_LOCAL_MODEL,
    build_direct_think_setting,
    get_local_model_name,
    handle_direct_conversation,
)


def run():
    # --------------------------------------------------
    # 1. Qwen3.5 9B is now Mairon's source-code default.
    #
    # Phase 6.8 originally kept qwen3:14b as the fallback
    # while qwen3.5:9b was evaluated through an environment
    # override. Conversational acceptance later promoted
    # qwen3.5:9b to the actual default.
    # --------------------------------------------------

    original = os.environ.get(
        "MAIRON_LOCAL_MODEL"
    )

    try:
        os.environ.pop(
            "MAIRON_LOCAL_MODEL",
            None,
        )

        assert (
            get_local_model_name()
            == DEFAULT_LOCAL_MODEL
            == "qwen3.5:9b"
        )

        # --------------------------------------------------
        # 2. Runtime model override still requires no source edit.
        # --------------------------------------------------

        os.environ[
            "MAIRON_LOCAL_MODEL"
        ] = "qwen3:14b"

        assert (
            get_local_model_name()
            == "qwen3:14b"
        )

        os.environ[
            "MAIRON_LOCAL_MODEL"
        ] = "qwen3.5:9b"

        assert (
            get_local_model_name()
            == "qwen3.5:9b"
        )

        # Qwen-family restricted turns disable hidden thinking.
        assert (
            build_direct_think_setting(
                "casual_conversation",
                model_name="qwen3.5:9b",
            )
            is False
        )

        # GPT-OSS cannot fully disable thinking; low effort is valid.
        assert (
            build_direct_think_setting(
                "casual_conversation",
                model_name="gpt-oss:20b",
            )
            == "low"
        )

        # Unknown/non-thinking model: do not force a think parameter.
        assert (
            build_direct_think_setting(
                "casual_conversation",
                model_name="gemma3:12b",
            )
            is None
        )

        # Later Phase 6.8 work established that straightforward
        # factual Qwen turns should also disable hidden thinking.
        assert (
            build_direct_think_setting(
                "factual_question",
                model_name="qwen3.5:9b",
            )
            is False
        )

    finally:
        if original is None:
            os.environ.pop(
                "MAIRON_LOCAL_MODEL",
                None,
            )
        else:
            os.environ[
                "MAIRON_LOCAL_MODEL"
            ] = original

    # --------------------------------------------------
    # 3. Explicit live recall bypasses style-repetition
    #    rejection. Accuracy outranks novelty.
    # --------------------------------------------------

    source = inspect.getsource(
        handle_direct_conversation
    )

    # Assert the behaviour structurally rather than depending on a
    # particular explanatory comment. Explicit live recall must bypass
    # repetition rejection so accuracy is not sacrificed for novelty.
    import re

    repetition_guard = re.search(
        r"if\s+not\s+core_is_live_recall\s*:\s*"
        r"violations\.extend\(\s*"
        r"find_repetition_violations\(",
        source,
    )

    assert (
        repetition_guard
        is not None
    )

    print(
        "Mairon Core Phase 6.8 generator-swap/live-recall tests: PASS"
    )


if __name__ == "__main__":
    run()
