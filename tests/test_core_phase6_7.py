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
    build_factual_focus_instruction,
    build_micro_act_prior_user_context,
    build_restricted_generation_context,
    should_use_restricted_generation_context,
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
        contract,
        runtime_from_answer_contract(
            contract
        ),
    )


def run():
    # --------------------------------------------------
    # 1. Restricted generation context excludes all old
    #    user/assistant dialogue and preserves only system seed.
    # --------------------------------------------------

    conversation = [
        {
            "role": "system",
            "content": "MAIRON STATIC PERSONALITY",
        },
        {
            "role": "user",
            "content": (
                "Anyway, my XM6s are at 40% and I forgot "
                "to charge them before work. Classic."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "The XM6s are plotting your demise in a dark room."
            ),
        },
        {
            "role": "user",
            "content": "At least my iPad is fully charged.",
        },
        {
            "role": "assistant",
            "content": (
                "The iPad is sneaking around charging itself."
            ),
        },
    ]

    isolated = (
        build_restricted_generation_context(
            conversation
        )
    )

    assert len(isolated) == 1
    assert isolated[0]["role"] == "system"
    assert (
        isolated[0]["content"]
        == "MAIRON STATIC PERSONALITY"
    )

    rendered = str(
        isolated
    )

    assert "XM6" not in rendered
    assert "iPad" not in rendered
    assert "dark room" not in rendered
    assert "charging itself" not in rendered

    # --------------------------------------------------
    # 2. Restricted-context policy:
    #    - social/live-recall lanes remain isolated;
    #    - standalone factual questions are now isolated too;
    #    - backward-pointing factual follow-ups keep live context;
    #    - recommendation/opinion/action lanes remain unrestricted.
    #
    # Phase 6.8.11 deliberately refined the original Phase 6.7
    # boundary. Test the stable behaviour rather than freezing the
    # older blanket "all factual questions are unrestricted" rule.
    # --------------------------------------------------

    for intent in (
        "share_context",
        "acknowledge",
        "casual_conversation",
        "self_correction",
        "conversation_recall",
    ):
        assert (
            should_use_restricted_generation_context(
                intent
            )
            is True
        ), intent

    assert (
        should_use_restricted_generation_context(
            "factual_question",
            user_input=(
                "Anyway, what's the capital of Canada?"
            ),
        )
        is True
    )

    assert (
        should_use_restricted_generation_context(
            "factual_question",
            user_input=(
                "And what about its population?"
            ),
        )
        is False
    )

    for intent in (
        "recommendation_request",
        "share_opinion",
        "action_request",
    ):
        assert (
            should_use_restricted_generation_context(
                intent
            )
            is False
        ), intent

    # --------------------------------------------------
    # 3. Minimal prior-user context:
    #    - "it" genuinely needs one prior USER turn;
    #    - the debug insult stands alone and gets NONE;
    #    - "At least..." receives only one prior USER turn.
    # --------------------------------------------------

    desk_conversation = [
        {
            "role": "system",
            "content": "system",
        },
        {
            "role": "user",
            "content": (
                "I finally cleaned my desk this morning. "
                "It was getting ridiculous."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Invented coffee mugs should never be grounding."
            ),
        },
    ]

    desk_context = (
        build_micro_act_prior_user_context(
            user_input=(
                "Give it two days and it'll probably "
                "be fucked again."
            ),
            intent="casual_conversation",
            conversation=desk_conversation,
        )
    )

    assert desk_context is not None
    assert "cleaned my desk" in desk_context
    assert "coffee mugs" not in desk_context

    debug_context = (
        build_micro_act_prior_user_context(
            user_input=(
                "Don't get smug. You're still the assistant "
                "I have to debug every night."
            ),
            intent="casual_conversation",
            conversation=conversation,
        )
    )

    assert debug_context is None

    ipad_context = (
        build_micro_act_prior_user_context(
            user_input=(
                "At least my iPad is fully charged."
            ),
            intent="share_context",
            conversation=[
                {
                    "role": "system",
                    "content": "system",
                },
                {
                    "role": "user",
                    "content": (
                        "Anyway, my XM6s are at 40% and "
                        "I forgot to charge them."
                    ),
                },
                {
                    "role": "assistant",
                    "content": (
                        "Assistant hallucination."
                    ),
                },
            ],
        )
    )

    assert ipad_context is not None
    assert "XM6s" in ipad_context
    assert "Assistant hallucination" not in ipad_context

    # --------------------------------------------------
    # 4. Restricted micro-acts use lower-variance, capped output.
    # --------------------------------------------------

    social_options = (
        build_direct_generation_options(
            "casual_conversation"
        )
    )

    assert social_options == {
        "temperature": 0.35,
        "num_predict": 160,
    }

    recall_options = (
        build_direct_generation_options(
            "conversation_recall"
        )
    )

    assert recall_options == {
        "temperature": 0.1,
        "num_predict": 128,
    }

    # Phase 6.8.12 introduced its own lower-variance generation policy for
    # straightforward factual questions. Phase 6.7 owns the social/recall
    # isolation behaviour above; the exact factual generation tuning is tested
    # by the newer dedicated regression and should not be frozen here.
    factual_options = (
        build_direct_generation_options(
            "factual_question"
        )
    )

    assert (
        factual_options is None
        or isinstance(
            factual_options,
            dict,
        )
    )

    # --------------------------------------------------
    # 5. Factual questions receive a no-stale-callback contract.
    # --------------------------------------------------

    factual_text = (
        "Anyway, what's the capital of Canada?"
    )

    (
        turn,
        contract,
        runtime,
    ) = runtime_for(
        factual_text
    )

    assert turn.intent == (
        "factual_question"
    )

    assert any(
        "Do not append callbacks to unrelated prior topics"
        in item
        for item in contract.forbidden_behaviours
    )

    factual_focus = (
        build_factual_focus_instruction(
            runtime
        )
    )

    assert factual_focus is not None
    # Assert the stable Phase 6.7 behaviour rather than freezing later
    # factual-focus wording. Newer phases may strengthen the instruction
    # (for example, by requiring truth-first personality) while preserving
    # the same core requirement.
    assert (
        "Answer Oliver's CURRENT factual question directly"
        in factual_focus
    )
    assert (
        "Do not append a callback, joke, or comment about an unrelated prior topic."
        in factual_focus
    )

    # Non-factual turns do not receive this instruction.
    (
        _,
        _,
        share_runtime,
    ) = runtime_for(
        "My iPad is fully charged."
    )

    assert (
        build_factual_focus_instruction(
            share_runtime
        )
        is None
    )

    print(
        "Mairon Core Phase 6.7 restricted-context isolation tests: PASS"
    )


if __name__ == "__main__":
    run()
