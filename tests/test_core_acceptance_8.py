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


from core.intent_router import classify_turn
from core.answer_contract_runtime import AnswerContractRuntime
from ai.ollama_provider import (
    _factual_question_requests_explanation,
    build_factual_focus_instruction,
)


def run():
    # --------------------------------------------------
    # 1. Direct social check-ins addressed to Mairon are
    #    conversation/persona, not epistemic factual lookups.
    # --------------------------------------------------

    social_inputs = (
        "Hey Mairon, how is your day going?",
        "How are you?",
        "How have you been?",
        "How's your evening?",
        "How was your weekend?",
        "You good?",
        "What are you up to?",
    )

    for text in social_inputs:
        turn = classify_turn(
            text
        )

        assert (
            turn.intent
            == "casual_conversation"
        ), (
            text,
            turn.intent,
            turn.reasons,
        )

        assert (
            turn.factuality
            == "none"
        )

    # Nearby assistant-directed questions that are genuinely factual/capability
    # questions must remain factual.
    factual_inputs = (
        "What model are you?",
        "What can you do?",
        "How many tokens can you generate?",
        "Are you running locally?",
    )

    for text in factual_inputs:
        turn = classify_turn(
            text
        )

        assert (
            turn.intent
            == "factual_question"
        ), (
            text,
            turn.intent,
            turn.reasons,
        )

    # Abrupt topic switches remain standalone factual questions.
    turn = classify_turn(
        "Anyway, what's the capital of Canada?"
    )

    assert (
        turn.intent
        == "factual_question"
    )

    # --------------------------------------------------
    # 2. Factual scope is based on requested answer shape,
    #    not a subject-specific keyword or hard token limit.
    # --------------------------------------------------

    simple_queries = (
        "What's the capital of Canada?",
        "Who wrote Frankenstein?",
        "How many minutes are in two hours?",
        "How far is the Moon from Earth?",
    )

    for text in simple_queries:
        assert not (
            _factual_question_requests_explanation(
                text
            )
        )

    explanatory_queries = (
        "Why is Ottawa the capital of Canada?",
        "Explain how DNS works.",
        "How does TLS establish a secure connection?",
        "Compare TCP and UDP.",
        "What happened during the Apollo 13 mission?",
        "Tell me about the causes in detail.",
    )

    for text in explanatory_queries:
        assert (
            _factual_question_requests_explanation(
                text
            )
        ), text

    # Provider policy consumes the structured runtime contract. It must not
    # regress to reparsing rendered Answer Contract prose.
    contract = AnswerContractRuntime(
        intent="factual_question",
        speech_act="question",
        task="respond",
        authority="model_knowledge",
        epistemic_mode="factual",
        allow_new_factual_claims=True,
        source="structured",
    )

    # Phase 6 architecture invariant: helpers should not parse arbitrary
    # rendered prose at runtime.
    assert (
        build_factual_focus_instruction(
            "Intent: factual_question",
            user_input="What's the capital of Canada?",
        )
        is None
    )

    simple_instruction = (
        build_factual_focus_instruction(
            contract,
            user_input="What's the capital of Canada?",
        )
    )

    assert (
        "simple factual lookup"
        in simple_instruction.lower()
    )

    assert (
        "stop rather than volunteering additional factual claims"
        in simple_instruction.lower()
    )

    explanatory_instruction = (
        build_factual_focus_instruction(
            contract,
            user_input="Explain why this happened in detail.",
        )
    )

    assert (
        "requested explanation/detail/comparison"
        in explanatory_instruction.lower()
    )

    # Architecture regression: no Ottawa/day benchmark special-casing.
    combined = (
        simple_instruction
        + "\n"
        + explanatory_instruction
    ).lower()

    for forbidden in (
        "ottawa",
        "canada",
        "how is your day",
        "gym routine",
        "top 3",
    ):
        assert (
            forbidden
            not in combined
        )

    print(
        "Mairon acceptance cleanup 8 social-routing / factual-scope tests: PASS"
    )


if __name__ == "__main__":
    run()
