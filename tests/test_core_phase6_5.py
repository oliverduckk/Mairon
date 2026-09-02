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
    build_live_conversation_recall_context,
    should_retrieve_past_context_for_turn,
)
from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    runtime_from_answer_contract,
)
from core.claim_grounding import (
    build_recent_user_grounding_context,
    contract_forbids_new_factual_claims,
    should_verify_core_grounding,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)
from personality.spoiler_guard import (
    is_media_like_turn,
    prepare_spoiler_context,
    should_activate_media_domain,
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
        route,
        contract,
        runtime,
    )


def run():
    # --------------------------------------------------
    # 1. Personal updates from the acceptance test belong
    #    to the restricted user-context lane.
    # --------------------------------------------------

    personal_updates = [
        (
            "I finally cleaned my desk this morning. "
            "It was getting ridiculous."
        ),
        (
            "Anyway, my XM6s are at 40% and I forgot "
            "to charge them before work. Classic."
        ),
        "At least my iPad is fully charged.",
    ]

    for text in personal_updates:
        (
            turn,
            route,
            contract,
            runtime,
        ) = runtime_for(
            text
        )

        assert turn.intent == (
            "share_context"
        ), (
            text,
            turn.intent,
            turn.reasons,
        )

        assert route.authority == (
            "user_turn"
        )

        assert (
            should_retrieve_past_context_for_turn(
                text,
                runtime,
            )
            is False
        )

        assert (
            contract.allow_new_factual_claims
            is False
        )

        assert (
            contract.allow_follow_up_question
            is False
        )

        assert (
            should_verify_core_grounding(
                runtime
            )
            is True
        )

        assert (
            build_core_micro_act_instruction(
                core_answer_contract=runtime,
                conversation=[],
                retry=False,
            )
            is not None
        )

    # --------------------------------------------------
    # 2. Ordinary banter/follow-up is still conversation,
    #    but it is now live-conversation grounded rather
    #    than an excuse to retrieve historical journal data.
    # --------------------------------------------------

    casual_turns = [
        "Give it two days and it'll probably be fucked again.",
        (
            "Don't get smug. You're still the assistant "
            "I have to debug every night."
        ),
    ]

    for text in casual_turns:
        (
            turn,
            route,
            contract,
            runtime,
        ) = runtime_for(
            text
        )

        assert turn.intent == (
            "casual_conversation"
        ), (
            text,
            turn.intent,
            turn.reasons,
        )

        assert route.authority == (
            "live_conversation"
        )

        assert route.mode == (
            "social_conversation"
        )

        assert route.allow_model_memory is False

        assert (
            contract.allow_new_factual_claims
            is False
        )

        assert (
            should_verify_core_grounding(
                runtime
            )
            is True
        )

        assert (
            should_retrieve_past_context_for_turn(
                text,
                runtime,
            )
            is False
        )

        assert (
            build_core_micro_act_instruction(
                core_answer_contract=runtime,
                conversation=[],
                retry=False,
            )
            is not None
        )

    # --------------------------------------------------
    # 3. Oliver correcting HIMSELF is not Mairon correction.
    # --------------------------------------------------

    self_correction_text = (
        "Actually, scratch that — I cleaned it last night, "
        "not this morning."
    )

    (
        turn,
        route,
        contract,
        runtime,
    ) = runtime_for(
        self_correction_text
    )

    assert turn.intent == (
        "self_correction"
    ), (
        turn.intent,
        turn.reasons,
    )

    assert turn.speech_act == (
        "self_correction"
    )

    assert route.authority == (
        "user_turn_and_live_conversation"
    )

    assert route.mode == (
        "self_correction"
    )

    assert route.allow_model_memory is False

    assert (
        contract.allow_new_factual_claims
        is False
    )

    assert (
        contract.allow_follow_up_question
        is False
    )

    assert (
        should_retrieve_past_context_for_turn(
            self_correction_text,
            runtime,
        )
        is False
    )

    # Existing Mairon-correction lane must still work.
    mairon_correction = (
        "I never even asked for the weather idiot"
    )

    (
        turn,
        route,
        _,
        runtime,
    ) = runtime_for(
        mairon_correction
    )

    assert turn.intent == (
        "correct_mairon"
    )

    assert route.authority == (
        "conversation_and_verification"
    )

    assert (
        should_retrieve_past_context_for_turn(
            mairon_correction,
            runtime,
        )
        is False
    )

    # --------------------------------------------------
    # 4. Exact live recall regression gets its own lane.
    # --------------------------------------------------

    recall_text = (
        "Back to the desk — what did I say I changed "
        "about when I cleaned it?"
    )

    (
        turn,
        route,
        contract,
        runtime,
    ) = runtime_for(
        recall_text
    )

    assert turn.intent == (
        "conversation_recall"
    ), (
        turn.intent,
        turn.reasons,
    )

    assert route.authority == (
        "live_conversation"
    )

    assert route.mode == (
        "conversation_recall"
    )

    assert route.allow_model_memory is False

    assert contract.allow_recommendations is False
    assert contract.allow_new_factual_claims is False
    assert contract.allow_follow_up_question is False

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

    assert (
        should_retrieve_past_context_for_turn(
            recall_text,
            runtime,
        )
        is False
    )

    # --------------------------------------------------
    # 5. Media machinery must not even activate for the
    #    desk-recall sentence.
    # --------------------------------------------------

    assert (
        is_media_like_turn(
            recall_text
        )
        is False
    )

    assert (
        should_activate_media_domain(
            recall_text,
            conversation=[],
        )
        is False
    )

    spoiler_context = (
        prepare_spoiler_context(
            user_input=recall_text,
            conversation=[],
        )
    )

    assert spoiler_context[
        "domain_active"
    ] is False

    assert spoiler_context[
        "title"
    ] is None

    # Real explicit media language still activates.
    real_media = (
        "I'm up to chapter 100 of One Piece."
    )

    assert (
        is_media_like_turn(
            real_media
        )
        is True
    )

    assert (
        should_activate_media_domain(
            real_media,
            conversation=[],
        )
        is True
    )

    # Lexical-boundary regression: generic words containing a
    # media token as a substring do not count.
    assert (
        is_media_like_turn(
            "The endgame plan is still unfinished."
        )
        is False
    )

    # --------------------------------------------------
    # 6. Live recall packet is USER ONLY and preserves the
    #    corrected detail even after several later turns.
    # --------------------------------------------------

    conversation = [
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
                "Your desk contained expired coupons and "
                "a drawer labelled Important Documents."
            ),
        },
        {
            "role": "user",
            "content": (
                "Give it two days and it'll probably be fucked again."
            ),
        },
        {
            "role": "assistant",
            "content": "Some reply.",
        },
        {
            "role": "user",
            "content": self_correction_text,
        },
        {
            "role": "assistant",
            "content": "Correction acknowledged.",
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
            "content": "Some reply.",
        },
        {
            "role": "user",
            "content": "At least my iPad is fully charged.",
        },
        {
            "role": "assistant",
            "content": "Some reply.",
        },
        {
            "role": "user",
            "content": (
                "Don't get smug. You're still the assistant "
                "I have to debug every night."
            ),
        },
        {
            "role": "assistant",
            "content": "Some reply.",
        },
        {
            "role": "user",
            "content": "Anyway, what's the capital of Canada?",
        },
        {
            "role": "assistant",
            "content": "Ottawa.",
        },
    ]

    recall_packet = (
        build_live_conversation_recall_context(
            conversation=conversation,
            max_user_messages=12,
        )
    )

    assert (
        "cleaned it last night"
        in recall_packet
    )

    assert (
        "not this morning"
        in recall_packet
    )

    assert (
        "expired coupons"
        not in recall_packet
    )

    assert (
        "Important Documents"
        not in recall_packet
    )

    # Grounding's larger recall window must also preserve that correction.
    grounding_packet = (
        build_recent_user_grounding_context(
            conversation,
            max_user_messages=12,
        )
    )

    assert (
        "cleaned it last night"
        in grounding_packet
    )

    assert (
        "expired coupons"
        not in grounding_packet
    )

    # --------------------------------------------------
    # 7. Long-term journal retrieval remains available,
    #    but only when Oliver actually asks for older history.
    # --------------------------------------------------

    long_term_recall = (
        "Do you remember when we talked about that last month?"
    )

    (
        _,
        _,
        _,
        runtime,
    ) = runtime_for(
        long_term_recall
    )

    assert (
        should_retrieve_past_context_for_turn(
            long_term_recall,
            runtime,
        )
        is True
    )

    # Ordinary factual questions no longer drag journal snippets in.
    factual = (
        "Anyway, what's the capital of Canada?"
    )

    (
        turn,
        _,
        _,
        runtime,
    ) = runtime_for(
        factual
    )

    assert turn.intent == (
        "factual_question"
    )

    assert (
        should_retrieve_past_context_for_turn(
            factual,
            runtime,
        )
        is False
    )

    # A mere historical time phrase is not permission to search old chats.
    ordinary_old_statement = (
        "I bought this last month."
    )

    (
        _,
        _,
        _,
        runtime,
    ) = runtime_for(
        ordinary_old_statement
    )

    assert (
        should_retrieve_past_context_for_turn(
            ordinary_old_statement,
            runtime,
        )
        is False
    )

    print(
        "Mairon Core Phase 6.5 conversational domain/recall tests: PASS"
    )


if __name__ == "__main__":
    run()
