import json
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
    find_core_answer_contract_violations,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.claim_grounding import (
    find_deterministic_grounding_violations,
    verify_core_grounded_draft,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


class FakeMessage:
    def __init__(
        self,
        content,
    ):
        self.content = content


class FakeResult:
    def __init__(
        self,
        content,
    ):
        self.message = FakeMessage(
            content
        )


class AlwaysSupportClient:
    """
    If deterministic Core checks miss something, this fake verifier would
    approve it. That lets this regression prove the deterministic layer
    catches the exact failures before the model can wave them through.
    """

    def __init__(
        self,
    ):
        self.calls = []

    def chat(
        self,
        model,
        messages,
        options=None,
        **kwargs,
    ):
        self.calls.append({
            "model": model,
            "messages": messages,
            "options": options,
        })

        return FakeResult(
            json.dumps({
                "supported": True,
                "unsupported_claims": [],
                "claim_checks": [],
            })
        )


def make_share_contract(
    user_text,
):
    turn = classify_turn(
        user_text
    )

    route = route_epistemic_authority(
        turn
    )

    contract = build_answer_contract(
        turn=turn,
        route=route,
    ).to_model_instruction()

    return (
        turn,
        contract,
    )


def run():
    # --------------------------------------------------
    # 1. Exact live failure:
    #    "for China" must NOT become "currently in China".
    # --------------------------------------------------

    first_user = (
        "I bought XT6s for China. They arrived today!"
    )

    turn, contract = make_share_contract(
        first_user
    )

    assert turn.intent == (
        "share_context"
    )

    bad_location_draft = (
        "Ah, the XT6s have finally made landfall. "
        "I hope they’re as thrilled to be in China as you are to have them."
    )

    deterministic = (
        find_deterministic_grounding_violations(
            user_input=first_user,
            draft=bad_location_draft,
            core_answer_contract=contract,
            conversation=[],
        )
    )

    assert any(
        "current-location claim"
        in violation
        and "China"
        in violation
        for violation in deterministic
    ), deterministic

    client = AlwaysSupportClient()

    violations = (
        verify_core_grounded_draft(
            client=client,
            model="fake-model",
            user_input=first_user,
            draft=bad_location_draft,
            core_answer_contract=contract,
            conversation=[],
        )
    )

    assert any(
        "current-location claim"
        in violation
        for violation in violations
    )

    # Deterministic Core should reject this BEFORE asking the semantic
    # verifier that would otherwise approve everything.
    assert client.calls == []

    # --------------------------------------------------
    # 2. Another live failure class:
    #    specific itinerary facts may not appear from nowhere.
    # --------------------------------------------------

    great_wall_draft = (
        "You’ll be lacing them up before you even touch the Great Wall."
    )

    deterministic = (
        find_deterministic_grounding_violations(
            user_input=first_user,
            draft=great_wall_draft,
            core_answer_contract=contract,
            conversation=[],
        )
    )

    assert any(
        "Great Wall"
        in violation
        for violation in deterministic
    ), deterministic

    # --------------------------------------------------
    # 3. Casual discourse markers must not break intent routing.
    # --------------------------------------------------

    cases = [
        "Mate they are currently on my feet",
        "Bro they are currently on my feet",
        "Bruh they are currently on my feet",
        "Yeah they are currently on my feet",
        "Lmao they are currently on my feet",
    ]

    for message in cases:
        candidate = classify_turn(
            message
        )

        assert (
            candidate.intent
            == "share_context"
        ), (
            message,
            candidate.to_dict(),
        )

        assert (
            candidate.speech_act
            == "declarative_share"
        ), (
            message,
            candidate.to_dict(),
        )

    # --------------------------------------------------
    # 4. A share-context contract that forbids follow-up questions is
    #    actually enforced, not merely written into the prompt.
    # --------------------------------------------------

    question_draft = (
        "So they’re on your feet right now—how’s the break-in going? "
        "Blisters yet?"
    )

    contract_violations = (
        find_core_answer_contract_violations(
            response_text=question_draft,
            core_answer_contract=contract,
        )
    )

    assert any(
        "forbids a follow-up question"
        in violation
        for violation in contract_violations
    ), contract_violations

    # --------------------------------------------------
    # 5. Lead-ins also should not break real action routing.
    # --------------------------------------------------

    app_turn = classify_turn(
        "Bro can you please open the calculator?"
    )

    assert app_turn.intent == (
        "launch_application"
    )

    assert app_turn.entities[
        "app_name"
    ] == "calculator"

    # --------------------------------------------------
    # 6. Grounded conversational response remains allowed.
    # --------------------------------------------------

    good_draft = (
        "Finally. At least the China shoes actually arrived before the trip."
    )

    client = AlwaysSupportClient()

    violations = (
        verify_core_grounded_draft(
            client=client,
            model="fake-model",
            user_input=first_user,
            draft=good_draft,
            core_answer_contract=contract,
            conversation=[],
        )
    )

    assert violations == []

    assert len(
        client.calls
    ) == 1

    print(
        "Mairon Core Phase 5.1 relation-grounding regression tests: PASS"
    )


if __name__ == "__main__":
    run()
