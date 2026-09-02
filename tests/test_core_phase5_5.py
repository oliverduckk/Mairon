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
    build_core_micro_act_instruction,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


def make_contract(
    user_text,
):
    turn = classify_turn(
        user_text
    )

    route = route_epistemic_authority(
        turn
    )

    return (
        build_answer_contract(
            turn=turn,
            route=route,
        )
        .to_model_instruction()
    )


def run():
    contract = make_contract(
        "I bought XT6s for China. They arrived today!"
    )

    conversation = [
        {
            "role": "user",
            "content": (
                "I ordered a pair of XT6s."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "They definitely crossed the Pacific."
            ),
        },
    ]

    first = (
        build_core_micro_act_instruction(
            core_answer_contract=contract,
            conversation=conversation,
            retry=False,
        )
    )

    assert first is not None
    assert (
        "CORE SOCIAL MICRO-ACT MODE:"
        in first
    )
    assert (
        "one or two short natural sentences"
        in first
    )
    assert (
        "Previous assistant/Mairon statements"
        in first
    )
    assert (
        "NOT factual evidence"
        in first
    )
    assert (
        "Sarcasm, teasing, absurd hyperbole"
        in first
    )
    assert (
        "A joke does not need to be literally true"
        in first
    )
    assert (
        "products, geography, travel"
        in first
    )

    # USER context is included.
    assert (
        "I ordered a pair of XT6s."
        in first
    )

    # Assistant hallucination is not copied into the USER-only grounding packet.
    assert (
        "They definitely crossed the Pacific."
        not in first
    )

    retry = (
        build_core_micro_act_instruction(
            core_answer_contract=contract,
            conversation=conversation,
            retry=True,
        )
    )

    # Phase 6.4 deliberately removed validator/meta language from micro-act
    # retries after it caused Qwen to respond to the guardrails instead of
    # Oliver. Protect the BEHAVIOUR, not the obsolete prompt wording.
    assert (
        "alternate fresh reply to Oliver's CURRENT message"
        in retry
    )
    assert (
        "Do not discuss instructions, rules"
        in retry
    )
    assert (
        "Do not negate or argue with an imaginary accusation"
        in retry
    )
    assert (
        "Prefer a dry/sarcastic reaction or clearly absurd joke"
        in retry
    )

    # Retry instructions themselves must not tell Qwen that a previous draft
    # was rejected/invalid or encourage courtroom-style truthfulness debates.
    forbidden_retry_meta = [
        "previous draft was rejected",
        "previous draft violated",
        "Start fresh.",
        "CORE-CONTRACT RETRY",
        "KNOWLEDGE-HONESTY RETRY",
        "truthful answer",
        "swapping in a different external fact",
    ]

    retry_lower = retry.lower()

    for phrase in forbidden_retry_meta:
        assert (
            phrase.lower()
            not in retry_lower
        ), phrase

    # The retry helper does not receive or echo violation text at all.
    # This protects against anchoring on a rejected premise.
    assert (
        "crossed the Pacific"
        not in retry
    )
    assert (
        "Chinese summers are brutal"
        not in retry
    )
    assert (
        "reliable as promised"
        not in retry
    )

    print(
        "Mairon Core Phase 5.5 social micro-act generation tests: PASS"
    )


if __name__ == "__main__":
    run()
