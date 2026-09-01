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

    return runtime_from_answer_contract(
        contract
    )


def assert_travel_world_violation(
    user_text,
    draft,
    expected_fragment,
):
    runtime = runtime_for(
        user_text
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=draft,
            core_answer_contract=runtime,
            conversation=[],
        )
    )

    assert any(
        expected_fragment
        in violation
        for violation in violations
    ), violations


def run():
    user_text = (
        "My XT6s have arrived for my China trip "
        "in November! Lets go!"
    )

    # --------------------------------------------------
    # 1. Exact surviving live response must be rejected.
    # --------------------------------------------------

    live_bad_draft = (
        "Finally! The XT6s are here. Time to navigate China's infamous "
        "traffic and pretend you're not sweating through your jacket in "
        "November. May your air conditioning hold up better than your "
        "bargaining skills at the market."
    )

    runtime = runtime_for(
        user_text
    )

    violations = (
        find_deterministic_grounding_violations(
            user_input=user_text,
            draft=live_bad_draft,
            core_answer_contract=runtime,
            conversation=[],
        )
    )

    expected = [
        "travel-world detail involving weather/climate",
        "travel-world detail involving weather-related clothing",
        "travel-world detail involving traffic/road conditions",
        "travel-world detail involving market/shopping activity",
    ]

    for fragment in expected:
        assert any(
            fragment in violation
            for violation in violations
        ), (
            fragment,
            violations,
        )

    # --------------------------------------------------
    # 2. Individual realistic embellishments are blocked.
    # --------------------------------------------------

    assert_travel_world_violation(
        user_text,
        "China's traffic is infamous.",
        "traffic/road conditions",
    )

    assert_travel_world_violation(
        user_text,
        "You'll be sweating in November.",
        "weather/climate",
    )

    assert_travel_world_violation(
        user_text,
        "Better pack a jacket.",
        "weather-related clothing",
    )

    assert_travel_world_violation(
        user_text,
        "Your bargaining skills will get tested at the market.",
        "market/shopping activity",
    )

    assert_travel_world_violation(
        user_text,
        "You'll have plenty of temples to explore.",
        "tourist activity/venue",
    )

    # --------------------------------------------------
    # 3. User-supplied travel details are allowed.
    # --------------------------------------------------

    grounded_examples = [
        (
            "For China we're going to markets.",
            "Those markets are going to be dangerous for your wallet.",
            "market/shopping activity",
        ),
        (
            "I'm bringing a jacket for China.",
            "The jacket is officially coming too.",
            "weather-related clothing",
        ),
        (
            "We're expecting cold weather.",
            "Cold weather has entered the itinerary.",
            "weather/climate",
        ),
        (
            "We're visiting temples.",
            "The temples made the cut.",
            "tourist activity/venue",
        ),
    ]

    for (
        grounded_user,
        draft,
        blocked_fragment,
    ) in grounded_examples:
        grounded_runtime = runtime_for(
            grounded_user
        )

        violations = (
            find_deterministic_grounding_violations(
                user_input=grounded_user,
                draft=draft,
                core_answer_contract=grounded_runtime,
                conversation=[],
            )
        )

        assert not any(
            blocked_fragment
            in violation
            for violation in violations
        ), (
            grounded_user,
            violations,
        )

    # --------------------------------------------------
    # 4. Obviously non-literal banter remains possible.
    #
    # These lines intentionally avoid plausible travel-world premises.
    # --------------------------------------------------

    safe_banter = [
        "Finally. The XT6s have escaped parcel purgatory.",
        "China has been warned.",
        "Those XT6s are about to develop an ego.",
    ]

    for draft in safe_banter:
        violations = (
            find_deterministic_grounding_violations(
                user_input=user_text,
                draft=draft,
                core_answer_contract=runtime,
                conversation=[],
            )
        )

        assert not any(
            "travel-world detail"
            in violation
            for violation in violations
        ), (
            draft,
            violations,
        )

    # --------------------------------------------------
    # 5. Generation prompt explicitly teaches this boundary.
    # --------------------------------------------------

    instruction = (
        build_core_micro_act_instruction(
            core_answer_contract=runtime,
            conversation=[],
            retry=False,
        )
    )

    assert (
        "traffic, clothing, markets/shopping"
        in instruction
    )

    assert (
        "destination/month does NOT"
        in instruction
    )

    print(
        "Mairon Core Phase 6.3 travel-world grounding tests: PASS"
    )


if __name__ == "__main__":
    run()
