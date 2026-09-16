import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from core.answer_contract_runtime import (
    AnswerContractRuntime,
)
from core.claim_grounding import (
    should_verify_core_grounding,
)
from core.conversation_state import (
    ConversationState,
)
from core.conversational_research import (
    build_contextual_opinion_research_query,
    contextual_opinion_requires_public_grounding,
    looks_like_public_external_context,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)


def _prepare(
    state: ConversationState,
    text: str,
):
    turn = classify_turn(
        text,
        conversation_state=state,
    )

    return state.resolve_follow_up(
        turn
    )


def _complete(
    state: ConversationState,
    turn,
):
    state.update_from_turn(
        turn
    )


def run():
    # --------------------------------------------------
    # 1. Clear public/external context gets a grounded-opinion route.
    #    The entity/title is deliberately arbitrary: no franchise hard-coding.
    # --------------------------------------------------

    state = ConversationState()

    first = _prepare(
        state,
        (
            "Marin's handling of the final vote in ABCD "
            "is already pissing me off"
        ),
    )

    _complete(
        state,
        first,
    )

    second = _prepare(
        state,
        "do you think she handled it well though?",
    )

    assert second.intent == "share_opinion"
    assert second.is_follow_up is True
    assert second.resolved_referents[
        "she"
    ] == "Marin"

    assert (
        second.entities.get(
            "_conversation_public_grounding_required"
        )
        == "true"
    )

    assert (
        contextual_opinion_requires_public_grounding(
            second
        )
        is True
    )

    route = route_epistemic_authority(
        second
    )

    assert route.authority == "public_web"
    assert (
        route.mode
        == "public_source_verified_opinion"
    )
    assert route.verification_required is True
    assert route.allow_model_memory is False

    # --------------------------------------------------
    # 2. Public-context detector is generic and privacy-aware.
    # --------------------------------------------------

    assert (
        looks_like_public_external_context(
            "The latest episode of a series handled that reveal badly"
        )
        is True
    )

    assert (
        looks_like_public_external_context(
            "The CEO's handling of the company launch was strange"
        )
        is True
    )

    assert (
        looks_like_public_external_context(
            "Marin's decision in WXYZ was strange"
        )
        is True
    )

    # Explicit personal-relation language blocks automatic public lookup even
    # when the rest of the sentence looks opinion-shaped.
    assert (
        looks_like_public_external_context(
            "my mate Sarah handled the group vote badly"
        )
        is False
    )

    assert (
        looks_like_public_external_context(
            "my brother hated that episode"
        )
        is False
    )

    # --------------------------------------------------
    # 3. Personal contextual opinions remain private/conversational.
    # --------------------------------------------------

    private_turn = SimpleNamespace(
        intent="share_opinion",
        entities={
            "_conversation_context_user_text": (
                "my mate Sarah handled the group vote badly"
            ),
        },
        raw_text="do you think she was right?",
    )

    private_route = (
        route_epistemic_authority(
            private_turn
        )
    )

    assert (
        private_route.authority
        == "conversation"
    )
    assert (
        private_route.mode
        == "subjective"
    )

    # --------------------------------------------------
    # 4. Research query comes from Oliver-authored context, not assistant prose.
    # --------------------------------------------------

    query = (
        build_contextual_opinion_research_query(
            user_input=(
                "do you think she handled it well though?"
            ),
            previous_user_text=(
                "Marin's handling of the final vote in ABCD "
                "is already pissing me off"
            ),
            subject="Marin",
        )
    )

    # Phase 11.2.4 may compact conversational wording before public search.
    # This 11.2.3 regression therefore checks that the USER-authored semantic
    # identity survives, rather than pinning the exact search-string phrasing.
    lowered_query = query.lower()

    assert "marin" in lowered_query
    assert "final vote" in lowered_query
    assert "abcd" in lowered_query

    # Oliver's reaction may be stripped as search noise; assistant prose must
    # never become part of the research query.
    assert "assistant" not in lowered_query
    assert "mairon" not in lowered_query

    # If no prior context exists, current USER wording remains a safe non-empty
    # fallback. Later query-normalisation phases may remove punctuation.
    fallback_query = (
        build_contextual_opinion_research_query(
            user_input="what do you think of this?",
            previous_user_text=None,
            subject=None,
        )
    )

    assert fallback_query
    assert "what do you think of this" in fallback_query.lower()

    # --------------------------------------------------
    # 5. The generic Core-grounding verifier must not police public evidence
    #    it cannot see. Dedicated public-source verification owns this lane.
    # --------------------------------------------------

    grounded_opinion_contract = (
        AnswerContractRuntime(
            intent="share_opinion",
            authority="public_web",
            epistemic_mode=(
                "public_source_verified_opinion"
            ),
            allow_new_factual_claims=False,
        )
    )

    assert (
        should_verify_core_grounding(
            grounded_opinion_contract
        )
        is False
    )

    # Ordinary source-locked opinion still uses the generic Core verifier.
    ordinary_opinion_contract = (
        AnswerContractRuntime(
            intent="share_opinion",
            authority="conversation",
            epistemic_mode="subjective",
            allow_new_factual_claims=False,
        )
    )

    assert (
        should_verify_core_grounding(
            ordinary_opinion_contract
        )
        is True
    )

    # --------------------------------------------------
    # 6. Static integration guards: provider must reuse the public-evidence
    #    pipeline and opinion-specific fail-closed behaviour.
    # --------------------------------------------------

    provider_source = (
        PROJECT_ROOT
        / "src"
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "public_source_verified_opinion"
        in provider_source
    )
    assert (
        "Grounding conversational opinion from public sources."
        in provider_source
    )
    assert (
        "build_contextual_opinion_research_query"
        in provider_source
    )
    assert (
        "build_failed_public_opinion_fallback"
        in provider_source
    )
    assert (
        "CORE GROUNDED CONVERSATIONAL OPINION MODE:"
        in provider_source
    )

    # Regression for the first live 11.2.3 failure:
    #
    # A Core conversational referent is a plain string, while the Opinion
    # Ledger expects a structured subject dictionary. The provider must keep
    # those types separate rather than assigning the raw referent into
    # opinion_subject.
    assert (
        "grounded_opinion_subject = None"
        in provider_source
    )
    assert (
        "subject=grounded_opinion_subject"
        in provider_source
    )
    assert (
        "opinion_subject = (\n                resolved_contract_subject"
        not in provider_source
    )
    assert (
        "opinion_subject = (\n                grounded_opinion_subject"
        not in provider_source
    )

    grounding_source = (
        PROJECT_ROOT
        / "src"
        / "research"
        / "public_factual_grounding.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "clearly subjective judgement"
        in grounding_source
    )
    assert (
        "proper take without bullshitting it"
        in grounding_source
    )

    print(
        "Mairon Phase 11.2.3 knowledge-aware conversational opinion tests: PASS"
    )


if __name__ == "__main__":
    run()
