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
    should_retrieve_past_context_for_turn,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    runtime_from_answer_contract,
)
from core.claim_grounding import (
    contract_forbids_new_factual_claims,
    should_verify_core_grounding,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
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

    runtime = runtime_from_answer_contract(
        contract
    )

    return (
        turn,
        runtime,
    )


def run():
    # --------------------------------------------------
    # 1. Exact live Prosple-resurrection regression.
    # --------------------------------------------------

    live_text = (
        "My XT6s have arrived for my China trip "
        "in November! Lets go!"
    )

    (
        turn,
        runtime,
    ) = runtime_for(
        live_text
    )

    assert turn.intent == (
        "share_context"
    ), (
        turn.intent,
        turn.reasons,
    )

    assert turn.speech_act == (
        "declarative_share"
    )

    assert (
        should_retrieve_past_context_for_turn(
            live_text,
            runtime,
        )
        is False
    )

    assert (
        contract_forbids_new_factual_claims(
            runtime
        )
        is True
    )

    assert (
        should_verify_core_grounding(
            runtime
        )
        is True
    )

    # --------------------------------------------------
    # 2. General possessive personal updates.
    # --------------------------------------------------

    examples = [
        "My new monitor is here.",
        "My exam got moved to Friday.",
        "My package has arrived.",
        "Our flight has changed.",
        "Our hotel is booked.",
    ]

    for text in examples:
        turn = classify_turn(
            text
        )

        # Existing specialised intents may legitimately beat the generic
        # share rule. What must never happen is a plain personal status
        # update silently falling through to casual_conversation.
        if turn.intent in {
            "order_status",
            "email_search",
        }:
            continue

        assert turn.intent == (
            "share_context"
        ), (
            text,
            turn.intent,
            turn.reasons,
        )

    # --------------------------------------------------
    # 3. Questions remain questions.
    # --------------------------------------------------

    question_examples = [
        "My XT6s have arrived?",
        "My exam got moved?",
        "Our flight has changed?",
    ]

    for text in question_examples:
        turn = classify_turn(
            text
        )

        assert turn.intent != (
            "share_context"
        ), (
            text,
            turn.intent,
        )

    # --------------------------------------------------
    # 4. Existing action routing still wins.
    # --------------------------------------------------

    action = classify_turn(
        "Bro can you please open the calculator?"
    )

    assert action.intent == (
        "launch_application"
    )

    print(
        "Mairon Core Phase 6.1 personal-update routing tests: PASS"
    )


if __name__ == "__main__":
    run()
