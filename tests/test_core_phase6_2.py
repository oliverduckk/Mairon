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
    is_direct_weather_request,
    should_retrieve_past_context_for_turn,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    runtime_from_answer_contract,
)
from core.claim_grounding import (
    find_deterministic_grounding_violations,
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

    return (
        turn,
        runtime_from_answer_contract(
            contract
        ),
    )


def run():
    # --------------------------------------------------
    # 1. Exact live weather hijack:
    #    "trains" must NOT match the substring "rain".
    # --------------------------------------------------

    trains_turn = (
        "We arent driving anywhere. We are taking 1 domestic flight "
        "and the rest are trains. Only driving we are doing is with "
        "Didi's around cities. And walking! Lots of walking. "
        "Perfect for my XT6s!"
    )

    assert (
        is_direct_weather_request(
            trains_turn
        )
        is False
    )

    # --------------------------------------------------
    # 2. Weather meta/correction turns are not forecast requests.
    # --------------------------------------------------

    meta_turns = [
        (
            "bruh where are you getting the weather for? "
            "im going in November....."
        ),
        "I never even asked for the weather idiot",
        "Why are you giving me the weather?",
        "Stop with the weather.",
        "I'm not asking about the forecast.",
    ]

    for text in meta_turns:
        assert (
            is_direct_weather_request(
                text
            )
            is False
        ), text

    # --------------------------------------------------
    # 3. Real weather requests still work.
    # --------------------------------------------------

    real_weather_turns = [
        "What's the weather tomorrow?",
        "Will it rain tomorrow?",
        "Forecast for Sydney",
        "Weather Sydney",
        "Is it windy today?",
        "What's the temperature in Sydney?",
    ]

    for text in real_weather_turns:
        assert (
            is_direct_weather_request(
                text
            )
            is True
        ), text

    # --------------------------------------------------
    # 4. First-person plural status updates are share_context.
    # --------------------------------------------------

    (
        turn,
        runtime,
    ) = runtime_for(
        trains_turn
    )

    assert turn.intent == (
        "share_context"
    ), (
        turn.intent,
        turn.reasons,
    )

    assert (
        should_retrieve_past_context_for_turn(
            trains_turn,
            runtime,
        )
        is False
    )

    # --------------------------------------------------
    # 5. Source challenges / "I never asked" are corrections.
    # --------------------------------------------------

    correction_turns = [
        (
            "bruh where are you getting the weather for? "
            "im going in November....."
        ),
        "I never even asked for the weather idiot",
    ]

    for text in correction_turns:
        (
            turn,
            runtime,
        ) = runtime_for(
            text
        )

        assert turn.intent == (
            "correct_mairon"
        ), (
            text,
            turn.intent,
            turn.reasons,
        )

        assert (
            should_retrieve_past_context_for_turn(
                text,
                runtime,
            )
            is False
        )

    # --------------------------------------------------
    # 6. Exact first-turn hallucination:
    #    trip context does not imply a driving itinerary.
    # --------------------------------------------------

    user_text = (
        "My XT6s have arrived for my China trip "
        "in November! Lets go!"
    )

    (
        _,
        runtime,
    ) = runtime_for(
        user_text
    )

    bad_draft = (
        "Finally! The XT6s are here. November in China – "
        "hope you're ready for some serious driving adventures."
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=bad_draft,
            core_answer_contract=runtime,
            conversation=[],
        )
    )

    assert any(
        "travel transport claim involving driving"
        in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 7. A transport claim is allowed when Oliver supplied it.
    # --------------------------------------------------

    grounded_user_text = (
        "For the trip we're taking trains between cities."
    )

    (
        _,
        grounded_runtime,
    ) = runtime_for(
        grounded_user_text
    )

    grounded_draft = (
        "You'll be taking trains between cities."
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=grounded_user_text,
            draft=grounded_draft,
            core_answer_contract=grounded_runtime,
            conversation=[],
        )
    )

    assert not any(
        "travel transport claim"
        in violation
        for violation in violations
    ), violations

    print(
        "Mairon Core Phase 6.2 weather/transport routing tests: PASS"
    )


if __name__ == "__main__":
    run()
