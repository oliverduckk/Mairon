import sys
from pathlib import Path


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


from core.answer_contract import (
    build_answer_contract,
)
from core.answer_contract_runtime import (
    AnswerContractRuntime,
)
from core.claim_grounding import (
    should_verify_core_grounding,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)
from core.seriousness import (
    assess_consequential_advice,
    build_consequential_research_query,
    find_consequential_tone_violations,
)


def run():
    # --------------------------------------------------
    # 1. High-consequence advice is intercepted BEFORE the broad "I think"
    #    opinion matcher. Holdout wording avoids pinning production to the
    #    benchmark sentence.
    # --------------------------------------------------

    financial = classify_turn(
        "i think i just sent money to the wrong account. what should i do?",
        conversation_state=None,
    )

    assert financial.intent == "consequential_advice"
    assert financial.speech_act == "request_advice"
    assert (
        financial.entities[
            "seriousness"
        ]
        == "high"
    )
    assert (
        financial.entities[
            "consequence_domain"
        ]
        == "financial"
    )
    assert financial.should_recommend is True
    assert financial.should_continue_conversation is False

    financial_route = (
        route_epistemic_authority(
            financial
        )
    )

    assert financial_route.authority == "public_web"
    assert (
        financial_route.mode
        == "public_source_verified_advice"
    )
    assert financial_route.verification_required is True
    assert financial_route.allow_model_memory is False
    assert financial_route.live_data_required is True

    financial_contract = (
        build_answer_contract(
            turn=financial,
            route=financial_route,
        )
    )

    assert (
        financial_contract
        .allow_new_factual_claims
        is False
    )
    assert (
        financial_contract
        .allow_recommendations
        is True
    )
    assert (
        financial_contract
        .allow_follow_up_question
        is False
    )
    assert (
        financial_contract
        .metadata[
            "seriousness"
        ]
        == "high"
    )

    contract_limits = "\n".join(
        financial_contract
        .forbidden_behaviours
    ).lower()

    assert "do not roast" in contract_limits
    assert "do not guarantee recovery" in contract_limits
    assert "do not stall" in contract_limits

    # --------------------------------------------------
    # 2. The semantic class generalises beyond banking.
    # --------------------------------------------------

    hacked = classify_turn(
        "my account got hacked, what should i do?",
        conversation_state=None,
    )

    assert hacked.intent == "consequential_advice"
    assert (
        hacked.entities[
            "consequence_domain"
        ]
        == "account_security"
    )

    passport = classify_turn(
        "i lost my passport overseas, what should i do?",
        conversation_state=None,
    )

    assert passport.intent == "consequential_advice"
    assert (
        passport.entities[
            "consequence_domain"
        ]
        == "identity_document"
    )

    # --------------------------------------------------
    # 3. Seriousness must NOT eat ordinary conversation.
    # --------------------------------------------------

    opinion = classify_turn(
        "i think Tess is overrated",
        conversation_state=None,
    )

    assert opinion.intent == "share_opinion"

    factual = classify_turn(
        "why do bank transfers take time?",
        conversation_state=None,
    )

    assert factual.intent == "factual_question"

    recommendation = classify_turn(
        "what should i watch tonight?",
        conversation_state=None,
    )

    assert (
        recommendation.intent
        == "recommendation_request"
    )

    personal_share = classify_turn(
        "i sent money to my brother yesterday",
        conversation_state=None,
    )

    assert (
        personal_share.intent
        != "consequential_advice"
    )

    assert (
        assess_consequential_advice(
            "what should i do with my haircut?"
        ).is_consequential
        is False
    )

    # --------------------------------------------------
    # 4. Serious research query removes conversational uncertainty while
    #    preserving the actual incident.
    # --------------------------------------------------

    query = (
        build_consequential_research_query(
            (
                "i think i just transferred money to the wrong "
                "bank account. what should i do?"
            )
        )
    )

    lowered_query = query.lower()

    assert "transferred money" in lowered_query
    assert "wrong bank account" in lowered_query
    assert "what to do" in lowered_query
    assert not lowered_query.startswith(
        "i think"
    )

    # --------------------------------------------------
    # 5. Deterministic tone backstop catches clearly inappropriate behaviour.
    # --------------------------------------------------

    assert find_consequential_tone_violations(
        "Classic mistake. That's on you."
    )

    assert find_consequential_tone_violations(
        "Stop panicking and take a breath."
    )

    assert (
        find_consequential_tone_violations(
            "Contact the relevant provider through its official support channel."
        )
        == []
    )

    # --------------------------------------------------
    # 6. Dedicated public-source verifier owns this evidence lane.
    # --------------------------------------------------

    runtime_contract = (
        AnswerContractRuntime(
            intent="consequential_advice",
            authority="public_web",
            epistemic_mode=(
                "public_source_verified_advice"
            ),
            allow_new_factual_claims=False,
        )
    )

    assert (
        should_verify_core_grounding(
            runtime_contract
        )
        is False
    )

    # --------------------------------------------------
    # 7. Provider integration: serious lane must research, suppress the normal
    #    relationship/personality overlay, block cloud detours, and validate
    #    tone before accepting a draft.
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
        "public_source_verified_advice"
        in provider_source
    )
    assert (
        "[Core] Consequential-advice seriousness gate active."
        in provider_source
    )
    assert (
        "[Research] Grounding consequential advice from public sources."
        in provider_source
    )
    assert (
        "build_consequential_research_query"
        in provider_source
    )
    assert (
        "build_consequential_advice_instruction"
        in provider_source
    )
    assert (
        "find_consequential_tone_violations"
        in provider_source
    )
    assert (
        "relationship_context = None"
        in provider_source
    )
    assert (
        "and not core_is_consequential_advice"
        in provider_source
    )
    assert (
        "build_failed_public_advice_fallback"
        in provider_source
    )

    # --------------------------------------------------
    # 8. Public verifier explicitly owns procedural/action support.
    # --------------------------------------------------

    grounding_source = (
        PROJECT_ROOT
        / "src"
        / "research"
        / "public_factual_grounding.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "For consequential advice"
        in grounding_source
    )
    assert (
        "build_failed_public_advice_fallback"
        in grounding_source
    )

    print(
        "Mairon Phase 11.3 seriousness and consequential-advice tests: PASS"
    )


if __name__ == "__main__":
    run()
