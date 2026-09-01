import inspect
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = (
    PROJECT_ROOT
    / "src"
)

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from ai.ollama_provider import (
    handle_direct_conversation,
    split_static_and_turn_instructions,
    strip_ephemeral_core_contracts,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.conversation_state import (
    append_visible_turn_to_model_history,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)
import personality.relationship_state as relationship_state


def run():
    # --------------------------------------------------
    # 1. Per-turn Answer Contract is separated from static personality.
    # --------------------------------------------------

    combined = (
        "STATIC MAIRON INSTRUCTIONS\n"
        "Personality stays here.\n\n"
        "CORE ANSWER CONTRACT:\n"
        "Intent: share_context\n"
        "Recommendations allowed: false"
    )

    static_text, contract_text = (
        split_static_and_turn_instructions(
            combined
        )
    )

    assert (
        static_text
        == (
            "STATIC MAIRON INSTRUCTIONS\n"
            "Personality stays here."
        )
    )

    assert contract_text.startswith(
        "CORE ANSWER CONTRACT:"
    )

    assert (
        "Recommendations allowed: false"
        in contract_text
    )

    # --------------------------------------------------
    # 2. Direct-conversation handler explicitly accepts current contract.
    # --------------------------------------------------

    signature = inspect.signature(
        handle_direct_conversation
    )

    assert (
        "core_answer_contract"
        in signature.parameters
    )

    # --------------------------------------------------
    # 3. Old per-turn contracts are stripped before a future turn.
    # --------------------------------------------------

    conversation = [
        {
            "role": "system",
            "content": "STATIC MAIRON INSTRUCTIONS",
        },
        {
            "role": "system",
            "content": (
                "CORE ANSWER CONTRACT:\n"
                "Intent: old_turn"
            ),
        },
        {
            "role": "user",
            "content": "Old message",
        },
        {
            "role": "assistant",
            "content": "Old answer",
        },
    ]

    cleaned = strip_ephemeral_core_contracts(
        conversation
    )

    assert len(
        cleaned
    ) == 3

    assert all(
        not (
            isinstance(
                message,
                dict,
            )
            and str(
                message.get(
                    "content",
                    "",
                )
            ).startswith(
                "CORE ANSWER CONTRACT:"
            )
        )
        for message in cleaned
    )

    # --------------------------------------------------
    # 4. Core-owned visible turns become live local model history.
    # --------------------------------------------------

    state = (
        append_visible_turn_to_model_history(
            current_state=None,
            user_input=(
                "Hey has my order from Hype DC arrived?"
            ),
            assistant_text=(
                "Yep — your Hype DC order is ready to collect."
            ),
            system_instructions=(
                "STATIC MAIRON INSTRUCTIONS"
            ),
        )
    )

    assert state == [
        {
            "role": "system",
            "content": "STATIC MAIRON INSTRUCTIONS",
        },
        {
            "role": "user",
            "content": (
                "Hey has my order from Hype DC arrived?"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Yep — your Hype DC order is ready to collect."
            ),
        },
    ]

    # --------------------------------------------------
    # 5. XT-6 declarative-share contract is hard-restricted.
    # --------------------------------------------------

    turn = classify_turn(
        (
            "They are a pair of XT6s for my trip to China in 2 months time. "
            "Gotta buy good shoes for walking that much ya know."
        )
    )

    route = route_epistemic_authority(
        turn
    )

    contract = build_answer_contract(
        turn=turn,
        route=route,
    )

    assert contract.allow_recommendations is False
    assert contract.allow_new_factual_claims is False

    contract_text = contract.to_model_instruction()

    assert (
        "Do not turn a declarative share into unsolicited recommendations."
        in contract_text
    )

    # --------------------------------------------------
    # 6. Thanks is not an invitation to offer another service.
    # --------------------------------------------------

    thanks_turn = classify_turn(
        "Thanks Mairon"
    )

    thanks_route = (
        route_epistemic_authority(
            thanks_turn
        )
    )

    thanks_contract = (
        build_answer_contract(
            turn=thanks_turn,
            route=thanks_route,
        )
    )

    assert (
        thanks_contract.allow_follow_up_question
        is False
    )

    assert (
        thanks_contract.allow_recommendations
        is False
    )

    assert (
        thanks_contract.allow_new_factual_claims
        is False
    )

    # --------------------------------------------------
    # 7. Novelty guard no longer rejects one ordinary repeated sentence.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as temp_dir:
        relationship_state.PRIVATE_DATA_DIR = Path(
            temp_dir
        )

        relationship_state.SOCIAL_CONTEXT_PATH = (
            Path(
                temp_dir
            )
            / "social_context.json"
        )

        context = {
            "callback_candidate": None,
        }

        previous = (
            "Fair enough, those XT6s make sense for a month of walking. "
            "You have at least managed to buy the shoes before arriving "
            "at the airport, which clears a remarkably low bar."
        )

        relationship_state.record_accepted_relationship_response(
            response_text=previous,
            relationship_context=context,
        )

        candidate = (
            "Fair enough, those XT6s make sense for a month of walking. "
            "A month in China is exactly the sort of trip where buying "
            "something comfortable beforehand is sensible."
        )

        violations = (
            relationship_state.find_repetition_violations(
                response_text=candidate,
                conversation=[],
            )
        )

        assert (
            "reused a recent sentence/punchline"
            not in violations
        )

        exact = (
            relationship_state.find_repetition_violations(
                response_text=previous,
                conversation=[],
            )
        )

        assert exact

    print(
        "Mairon Core Foundation v1 Phase 4 regression tests: PASS"
    )


if __name__ == "__main__":
    run()
