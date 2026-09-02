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

    user_text = (
        "I finally cleaned my desk this morning. "
        "It was getting ridiculous."
    )

    try:
        # --------------------------------------------------
        # 1. The verifier prompt explicitly decomposes a joke
        #    into concrete premise + nonliteral predicate.
        # --------------------------------------------------

        client = FakeClient(
            (
                '{"supported":false,"relevant":true,'
                '"unsupported_claims":["dust/dust bunnies were present"]}'
            )
        )

        violations = (
            grounding.verify_core_grounded_draft(
                client=client,
                model="qwen3.5:9b",
                user_input=user_text,
                draft=(
                    "The dust bunnies must have been plotting a coup."
                ),
                core_answer_contract=None,
                conversation=[],
            )
        )

        assert len(
            client.calls
        ) == 1

        call = client.calls[0]

        prompt_text = "\n".join(
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
            "Decompose each meaningful proposition BEFORE deciding what is banter."
            in prompt_text
        )

        assert (
            "A clearly non-literal predicate/action does NOT exempt the concrete premise"
            in prompt_text
        )

        assert (
            "'the dust bunnies are plotting a coup' is unsupported"
            in prompt_text
        )

        assert (
            "'the desk is plotting revenge' is allowed"
            in prompt_text
        )

        assert (
            "'the XM6s are furious' is allowed"
            in prompt_text
        )

        assert any(
            "dust/dust bunnies were present"
            in violation
            for violation in violations
        ), violations

        assert (
            call["options"]["num_ctx"]
            == 8192
        )

        assert (
            call["think"]
            is False
        )

        # --------------------------------------------------
        # 2. Supplied-entity anthropomorphism remains allowed.
        #    The verifier should not require a literal basis for
        #    the impossible/personified predicate itself.
        # --------------------------------------------------

        allowed_client = FakeClient(
            '{"supported":true,"relevant":true,"unsupported_claims":[]}'
        )

        violations = (
            grounding.verify_core_grounded_draft(
                client=allowed_client,
                model="qwen3.5:9b",
                user_input=user_text,
                draft=(
                    "That desk is already plotting its comeback."
                ),
                core_answer_contract=None,
                conversation=[],
            )
        )

        assert violations == []

    finally:
        grounding.should_verify_core_grounding = (
            original_should_verify
        )

        grounding.find_deterministic_grounding_violations = (
            original_deterministic
        )

    print(
        "Mairon Core Phase 6.8.6 premise-aware banter grounding tests: PASS"
    )


if __name__ == "__main__":
    run()
