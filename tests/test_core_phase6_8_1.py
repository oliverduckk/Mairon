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


import core.claim_grounding as grounding


class FakeMessage:
    def __init__(
        self,
        content,
    ):
        self.content = content


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
            '{"supported": true, "unsupported_claims": [], "claim_checks": []}'
        )


def run():
    # --------------------------------------------------
    # 1. Model-aware verifier thinking policy.
    # --------------------------------------------------

    assert (
        grounding._core_verifier_think_setting(
            "qwen3:14b"
        )
        is False
    )

    assert (
        grounding._core_verifier_think_setting(
            "qwen3.5:9b"
        )
        is False
    )

    assert (
        grounding._core_verifier_think_setting(
            "deepseek-r1:14b"
        )
        is False
    )

    assert (
        grounding._core_verifier_think_setting(
            "gpt-oss:20b"
        )
        == "low"
    )

    assert (
        grounding._core_verifier_think_setting(
            "gemma3:12b"
        )
        is None
    )

    # --------------------------------------------------
    # 2. Isolate the verifier call itself. We are testing
    #    runtime kwargs here, not routing/deterministic
    #    grounding behaviour already covered elsewhere.
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
                    "There we fucking go."
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
        call["model"]
        == "qwen3.5:9b"
    )

    assert (
        call["think"]
        is False
    )

    assert (
        call["options"]["temperature"]
        == 0
    )

    assert (
        call["options"]["num_predict"]
        == 160
    )

    print(
        "Mairon Core Phase 6.8.1 verifier thinking-budget tests: PASS"
    )


if __name__ == "__main__":
    run()
