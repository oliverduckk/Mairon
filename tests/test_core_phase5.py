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


from core.answer_contract import (
    build_answer_contract,
)
from core.claim_grounding import (
    build_core_grounding_fallback,
    build_recent_user_grounding_context,
    should_verify_core_grounding,
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


class FakeClient:
    """
    Deterministic fake semantic verifier.

    This test checks our Core plumbing and source boundaries without
    requiring Ollama to be running.
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

        combined = "\n".join(
            str(
                message.get(
                    "content",
                    "",
                )
            )
            for message in messages
            if isinstance(
                message,
                dict,
            )
        )

        proposed_marker = (
            "PROPOSED MAIRON DRAFT:\n"
        )

        proposed = (
            combined.split(
                proposed_marker,
                1,
            )[
                1
            ]
            if proposed_marker
            in combined
            else ""
        )

        unsupported = []

        if (
            "outlast a marathon"
            in proposed
        ):
            unsupported.append(
                "XT6s are built to outlast a marathon"
            )

        if (
            "Great Wall"
            in proposed
        ):
            unsupported.append(
                "Oliver will visit the Great Wall"
            )

        if unsupported:
            return FakeResult(
                json.dumps({
                    "supported": False,
                    "unsupported_claims": unsupported,
                })
            )

        return FakeResult(
            json.dumps({
                "supported": True,
                "unsupported_claims": [],
            })
        )


def run():
    # --------------------------------------------------
    # 1. Share-context contract requires semantic grounding.
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
    ).to_model_instruction()

    assert (
        should_verify_core_grounding(
            contract
        )
        is True
    )

    assert (
        "FACTUAL GROUNDING POLICY:"
        in contract
    )

    assert (
        "Plausible is not the same as grounded."
        in contract
    )

    # --------------------------------------------------
    # 2. Recent grounding context includes USER messages only.
    #    Prior Mairon hallucinations never become evidence.
    # --------------------------------------------------

    conversation = [
        {
            "role": "system",
            "content": "Static instructions.",
        },
        {
            "role": "user",
            "content": (
                "Hey has my Hype DC order arrived?"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Yep — and XT6s are waterproof forever."
            ),
        },
        {
            "role": "user",
            "content": (
                "They're the shoes for my China trip."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "You're definitely visiting the Great Wall."
            ),
        },
    ]

    grounding_context = (
        build_recent_user_grounding_context(
            conversation
        )
    )

    assert (
        "Hey has my Hype DC order arrived?"
        in grounding_context
    )

    assert (
        "They're the shoes for my China trip."
        in grounding_context
    )

    assert (
        "waterproof forever"
        not in grounding_context
    )

    assert (
        "Great Wall"
        not in grounding_context
    )

    # --------------------------------------------------
    # 3. The exact XT-6 embellishment is rejected.
    # --------------------------------------------------

    client = FakeClient()

    # Test the semantic verifier independently with a product-property
    # hallucination that the deterministic named-entity gate does not
    # short-circuit first.
    bad_product_draft = (
        "XT6s for China — smart choice. Those things are built to "
        "outlast a marathon, let alone a trip."
    )

    violations = (
        verify_core_grounded_draft(
            client=client,
            model="fake-model",
            user_input=turn.raw_text,
            draft=bad_product_draft,
            core_answer_contract=contract,
            conversation=conversation,
        )
    )

    assert any(
        "outlast a marathon"
        in violation
        for violation in violations
    )

    # Phase 5.1 added a cheaper deterministic gate for novel named facts.
    # Great Wall should therefore be rejected before the semantic verifier
    # needs to reason about the rest of the draft.
    bad_itinerary_draft = (
        "You'll be lacing them up before you even touch the Great Wall."
    )

    violations = (
        verify_core_grounded_draft(
            client=client,
            model="fake-model",
            user_input=turn.raw_text,
            draft=bad_itinerary_draft,
            core_answer_contract=contract,
            conversation=conversation,
        )
    )

    assert any(
        "Great Wall"
        in violation
        for violation in violations
    )

    # --------------------------------------------------
    # 4. A grounded conversational reaction is accepted.
    # --------------------------------------------------

    good_draft = (
        "Fair enough — if you're expecting that much walking, "
        "buying the XT6s before the trip makes sense."
    )

    violations = (
        verify_core_grounded_draft(
            client=client,
            model="fake-model",
            user_input=turn.raw_text,
            draft=good_draft,
            core_answer_contract=contract,
            conversation=conversation,
        )
    )

    assert violations == []

    # --------------------------------------------------
    # 5. Verifier runs cold/deterministically.
    # --------------------------------------------------

    assert client.calls

    assert all(
        call[
            "options"
        ][
            "temperature"
        ] == 0
        for call in client.calls
    )

    assert all(
        call[
            "options"
        ][
            "num_predict"
        ] == 160
        for call in client.calls
    )

    # --------------------------------------------------
    # 6. Acknowledgements do not incur semantic-verifier overhead.
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
        .to_model_instruction()
    )

    assert (
        should_verify_core_grounding(
            thanks_contract
        )
        is False
    )

    # --------------------------------------------------
    # 7. Repeated grounding failure has a safe deterministic fallback.
    # --------------------------------------------------

    assert (
        build_core_grounding_fallback(
            contract
        )
        == "Fair enough. That makes sense."
    )

    print(
        "Mairon Core Phase 5 claim-grounding regression tests: PASS"
    )


if __name__ == "__main__":
    run()
