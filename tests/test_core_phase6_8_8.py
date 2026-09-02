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
    def __init__(
        self,
        content,
    ):
        self.content = content
        self.calls = []

    def chat(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return FakeResponse(
            self.content
        )


def run():
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
        # --------------------------------------------------
        # 1. Ordinary grounded-turn verifier has explicit
        #    entity / actor / relation fidelity semantics.
        # --------------------------------------------------

        client = FakeClient(
            (
                '{"supported":true,"relevant":true,'
                '"source_faithful":false,"unsupported_claims":[]}'
            )
        )

        violations = (
            grounding.verify_core_grounded_draft(
                client=client,
                model="qwen3.5:9b",
                user_input=(
                    "My XM6s are at 40% and I forgot to charge them before work."
                ),
                draft=(
                    "Your phone's battery life is becoming a philosophical statement."
                ),
                core_answer_contract=None,
                conversation=[],
            )
        )

        assert any(
            "changed a supplied entity"
            in violation
            for violation in violations
        ), violations

        prompt_text = "\n".join(
            str(
                message.get(
                    "content",
                    "",
                )
            )
            for message in client.calls[
                0
            ][
                "messages"
            ]
            if isinstance(
                message,
                dict,
            )
        )

        assert (
            "XM6s are at 40%, that does NOT support saying his phone is at 40%"
            in prompt_text
        )

        assert (
            "I debug you every night"
            in prompt_text
        )

        assert (
            '"source_faithful":true'
            in prompt_text
        )

        # --------------------------------------------------
        # 2. Factual-focus verifier does NOT fact-check the
        #    public answer; it checks only personal/history
        #    fidelity.
        # --------------------------------------------------

        faithful_client = FakeClient(
            '{"faithful":true,"violations":[]}'
        )

        violations = (
            grounding.verify_factual_focus_fidelity(
                client=faithful_client,
                model="qwen3.5:9b",
                user_input=(
                    "What's the capital of Canada?"
                ),
                draft=(
                    "Ottawa."
                ),
                core_answer_contract=None,
                conversation=[],
            )
        )

        # None contract means helper correctly decides this is not a factual
        # contract, so test the policy helper independently below.
        assert violations == []

        # Force the factual verifier path to exercise its runtime semantics.
        original_should_factual = (
            grounding.should_verify_factual_focus_fidelity
        )

        grounding.should_verify_factual_focus_fidelity = (
            lambda contract: True
        )

        try:
            bad_client = FakeClient(
                (
                    '{"faithful":false,"violations":['
                    '"invented prior Mairon reading/history"]}'
                )
            )

            violations = (
                grounding.verify_factual_focus_fidelity(
                    client=bad_client,
                    model="qwen3.5:9b",
                    user_input=(
                        "What's the capital of Canada?"
                    ),
                    draft=(
                        "Ottawa. I didn't get lost reading a book about it this time."
                    ),
                    core_answer_contract=None,
                    conversation=[],
                )
            )

            assert any(
                "invented prior Mairon reading/history"
                in violation
                for violation in violations
            ), violations

            call = bad_client.calls[
                0
            ]

            assert (
                call["options"]["num_ctx"]
                == 8192
            )

            assert (
                call["options"]["num_predict"]
                == 96
            )

            assert (
                call["think"]
                is False
            )

            factual_prompt = "\n".join(
                str(
                    message.get(
                        "content",
                        "",
                    )
                )
                for message in call[
                    "messages"
                ]
                if isinstance(
                    message,
                    dict,
                )
            )

            assert (
                "Do NOT fact-check the public-world answer"
                in factual_prompt
            )

            assert (
                "I didn't get lost reading a book about it this time."
                in factual_prompt
            )

            assert (
                "Oliver debugs Mairon"
                in factual_prompt
            )

        finally:
            grounding.should_verify_factual_focus_fidelity = (
                original_should_factual
            )

    finally:
        grounding.should_verify_core_grounding = (
            original_should_verify
        )

        grounding.find_deterministic_grounding_violations = (
            original_deterministic
        )

    print(
        "Mairon Core Phase 6.8.8 source-fidelity tests: PASS"
    )


if __name__ == "__main__":
    run()
