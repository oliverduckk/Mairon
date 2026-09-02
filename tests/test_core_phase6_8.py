import ast
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
    # 1. Default local model remains backward-compatible.
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
            == "qwen3:14b"
        )

        # --------------------------------------------------
        # 2. Runtime model override requires no source edit.
        # --------------------------------------------------

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

        # Straightforward factual Qwen-family turns disable hidden thinking.
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
    #    rejection. Test the AST, not comment placement.
    # --------------------------------------------------

    source = inspect.getsource(
        handle_direct_conversation
    )

    tree = ast.parse(
        source
    )

    guarded_repetition_call_found = False

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.If,
        ):
            continue

        test_dump = ast.dump(
            node.test,
            include_attributes=False,
        )

        if not (
            "core_is_live_recall"
            in test_dump
            and isinstance(
                node.test,
                ast.UnaryOp,
            )
            and isinstance(
                node.test.op,
                ast.Not,
            )
        ):
            continue

        for child in ast.walk(
            node
        ):
            if not isinstance(
                child,
                ast.Call,
            ):
                continue

            func = child.func

            if (
                isinstance(
                    func,
                    ast.Name,
                )
                and func.id
                == "find_repetition_violations"
            ):
                guarded_repetition_call_found = True
                break

        if guarded_repetition_call_found:
            break

    assert guarded_repetition_call_found

    print(
        "Mairon Core Phase 6.8 generator-swap/live-recall tests: PASS"
    )


if __name__ == "__main__":
    run()
