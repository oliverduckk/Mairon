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
    build_direct_generation_options,
)

import core.claim_grounding as grounding


class FakeMessage:
    def __init__(
        self,
        content,
    ):
        self.content = content
        self.thinking = ""


class FakeResponse:
    def __init__(
        self,
        content,
    ):
        self.message = FakeMessage(
            content
        )


class FakeClient:
    def __init__(self):
        self.calls = []

    def chat(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return FakeResponse(
            '{"supported":true,"relevant":true,"unsupported_claims":[]}'
        )


def run():
    # --------------------------------------------------
    # 1. Restricted social/recall lanes explicitly request
    #    enough runtime context for Mairon's system prompt.
    # --------------------------------------------------

    for intent in (
        "share_context",
        "acknowledge",
        "casual_conversation",
        "self_correction",
        "conversation_recall",
    ):
        assert (
            build_direct_context_window(
                intent
            )
            == 8192
        ), intent

    for intent in (
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

    # Existing visible-output budget remains independently bounded.
    assert (
        build_direct_generation_options(
            "share_context"
        )
        == {
            "temperature": 0.35,
            "num_predict": 160,
        }
    )

    # --------------------------------------------------
    # 2. The semantic verifier receives the same 8192
    #    runtime context headroom.
    # --------------------------------------------------

    original_should_verify = (
        grounding.should_verify_core_grounding
    )

    original_deterministic = (
        grounding.find_deterministic_grounding_violations
    )

    grounding.should_verify_core_grounding = (
        lambda contract: True
    )

    grounding.find_deterministic_grounding_violations = (
        lambda **kwargs: []
    )

    try:
        client = FakeClient()

        violations = (
            grounding.verify_core_grounded_draft(
                client=client,
                model="qwen3.5:9b",
                user_input=(
                    "I finally cleaned my desk this morning. "
                    "It was getting ridiculous."
                ),
                draft=(
                    "About time you got that disaster zone under control."
                ),
                core_answer_contract=None,
                conversation=[],
            )
        )

    finally:
        grounding.should_verify_core_grounding = (
            original_should_verify
        )

        grounding.find_deterministic_grounding_violations = (
            original_deterministic
        )

    assert violations == []
    assert len(client.calls) == 1

    call = client.calls[0]

    assert (
        call["options"]["num_ctx"]
        == 8192
    )

    assert (
        call["options"]["num_predict"]
        == 160
    )

    assert (
        call["options"]["temperature"]
        == 0
    )

    assert (
        call["think"]
        is False
    )

    print(
        "Mairon Core Phase 6.8.5 runtime-context headroom tests: PASS"
    )


if __name__ == "__main__":
    run()
