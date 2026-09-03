import ast
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
    build_direct_generation_options,
    build_recent_assistant_dialogue_context,
    get_local_model_name,
)


def run():
    # --------------------------------------------------
    # 1. Qwen3.5 9B is now the actual source-code default.
    # --------------------------------------------------

    assert (
        DEFAULT_LOCAL_MODEL
        == "qwen3.5:9b"
    )

    old_env = os.environ.pop(
        "MAIRON_LOCAL_MODEL",
        None,
    )

    try:
        assert (
            get_local_model_name()
            == "qwen3.5:9b"
        )

    finally:
        if old_env is not None:
            os.environ[
                "MAIRON_LOCAL_MODEL"
            ] = old_env

    main_text = (
        PROJECT_ROOT
        / "src"
        / "main.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"qwen3.5:9b"'
        in main_text
    )

    # --------------------------------------------------
    # 2. Lightweight opinion turns get a bounded fast profile.
    # --------------------------------------------------

    assert (
        build_direct_generation_options(
            "share_opinion"
        )
        == {
            "temperature": 0.35,
            "num_predict": 112,
        }
    )

    assert (
        build_direct_generation_options(
            "factual_question"
        )
        == {
            "temperature": 0.2,
            "num_predict": 96,
        }
    )

    # --------------------------------------------------
    # 3. Prior assistant text can be used for DIALOGUE continuity
    #    without becoming factual evidence.
    # --------------------------------------------------

    conversation = [
        {
            "role": "system",
            "content": "system",
        },
        {
            "role": "user",
            "content": "What is your top 3 manga?",
        },
        {
            "role": "assistant",
            "content": (
                "Mushishi, Monster, and Vagabond are my current three."
            ),
        },
    ]

    direct_reference = (
        build_recent_assistant_dialogue_context(
            user_input=(
                "I was just asking for your thoughts. "
                "It's good to know what you think the top 3 mangas are."
            ),
            intent="share_context",
            conversation=conversation,
        )
    )

    assert direct_reference is not None
    assert (
        "NOT FACTUAL EVIDENCE"
        in direct_reference
    )
    assert (
        "Mushishi, Monster, and Vagabond"
        in direct_reference
    )

    evaluative_reference = (
        build_recent_assistant_dialogue_context(
            user_input=(
                "That's a banger top 3, I can't even argue with that."
            ),
            intent="casual_conversation",
            conversation=conversation,
        )
    )

    assert evaluative_reference is not None

    correction_reference = (
        build_recent_assistant_dialogue_context(
            user_input="Nah that's wrong.",
            intent="casual_conversation",
            conversation=conversation,
        )
    )

    assert correction_reference is not None

    # Plain backward reference to USER context should not automatically expose
    # assistant prose. The desk benchmark remains isolated from old assistant
    # jokes/claims.
    assert (
        build_recent_assistant_dialogue_context(
            user_input=(
                "Give it two days and it'll probably be fucked again."
            ),
            intent="casual_conversation",
            conversation=conversation,
        )
        is None
    )

    assert (
        build_recent_assistant_dialogue_context(
            user_input=(
                "At least my iPad is fully charged."
            ),
            intent="share_context",
            conversation=conversation,
        )
        is None
    )

    print(
        "Mairon acceptance cleanup 3 default/latency/dialogue-continuity tests: PASS"
    )


if __name__ == "__main__":
    run()
