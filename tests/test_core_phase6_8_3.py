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
    find_core_micro_act_relevance_violations,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    runtime_from_answer_contract,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
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


def runtime_for(
    text,
):
    turn = classify_turn(
        text
    )

    route = route_epistemic_authority(
        turn
    )

    contract = build_answer_contract(
        turn=turn,
        route=route,
    )

    return runtime_from_answer_contract(
        contract
    )


def run():
    user_text = (
        "I finally cleaned my desk this morning. "
        "It was getting ridiculous."
    )

    runtime = runtime_for(
        user_text
    )

    # --------------------------------------------------
    # 1. Social generation gets enough visible-output room
    #    to finish one or two short sentences.
    # --------------------------------------------------

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
    # 2. Cheap relevance no longer rejects valid semantic
    #    paraphrases merely because exact tokens differ.
    # --------------------------------------------------

    paraphrase = (
        "Glad you got that disaster zone under control, Oliver."
    )

    cheap_violations = (
        find_core_micro_act_relevance_violations(
            response_text=paraphrase,
            user_input=user_text,
            core_answer_contract=runtime,
        )
    )

    assert cheap_violations == []

    # But deterministic validator/meta leakage still fails.
    meta_draft = (
        "My previous response was rejected by validation."
    )

    cheap_violations = (
        find_core_micro_act_relevance_violations(
            response_text=meta_draft,
            user_input=user_text,
            core_answer_contract=runtime,
        )
    )

    assert any(
        "imaginary accusation/validator"
        in violation
        for violation in cheap_violations
    )

    # --------------------------------------------------
    # 3. Semantic verifier now judges grounding AND
    #    relevance in the SAME compact model call.
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
        supported_client = FakeClient(
            '{"supported":true,"relevant":true,"unsupported_claims":[]}'
        )

        violations = (
            grounding.verify_core_grounded_draft(
                client=supported_client,
                model="qwen3.5:9b",
                user_input=user_text,
                draft=paraphrase,
                core_answer_contract=runtime,
                conversation=[],
            )
        )

        assert violations == []
        assert len(
            supported_client.calls
        ) == 1

        call = supported_client.calls[0]

        assert (
            call["options"]["temperature"]
            == 0
        )

        assert (
            call["options"]["num_predict"]
            == 160
        )

        assert (
            call["think"]
            is False
        )

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
            '"relevant":true'
            in prompt_text
        )

        assert (
            "claim_checks"
            not in prompt_text
        )

        # --------------------------------------------------
        # 4. A grounded but generic/unrelated draft fails
        #    SEMANTIC relevance rather than lexical overlap.
        # --------------------------------------------------

        irrelevant_client = FakeClient(
            '{"supported":true,"relevant":false,"unsupported_claims":[]}'
        )

        violations = (
            grounding.verify_core_grounded_draft(
                client=irrelevant_client,
                model="qwen3.5:9b",
                user_input=user_text,
                draft=(
                    "I'm just sitting here processing your latest input."
                ),
                core_answer_contract=runtime,
                conversation=[],
            )
        )

        assert any(
            "not semantically relevant"
            in violation
            for violation in violations
        )

        # --------------------------------------------------
        # 5. Grounding and relevance failures can coexist.
        # --------------------------------------------------

        both_client = FakeClient(
            (
                '{"supported":false,"relevant":false,'
                '"unsupported_claims":["invented coffee machine"]}'
            )
        )

        violations = (
            grounding.verify_core_grounded_draft(
                client=both_client,
                model="qwen3.5:9b",
                user_input=user_text,
                draft=(
                    "The coffee machine agrees with me."
                ),
                core_answer_contract=runtime,
                conversation=[],
            )
        )

        assert any(
            "not semantically relevant"
            in violation
            for violation in violations
        )

        assert any(
            "invented coffee machine"
            in violation
            for violation in violations
        )

    finally:
        grounding.should_verify_core_grounding = (
            original_should_verify
        )

        grounding.find_deterministic_grounding_violations = (
            original_deterministic
        )

    print(
        "Mairon Core Phase 6.8.3 semantic relevance/compact verifier tests: PASS"
    )


if __name__ == "__main__":
    run()
