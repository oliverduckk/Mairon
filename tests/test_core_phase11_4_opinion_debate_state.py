import sys
import tempfile
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
from core.conversation_state import (
    ConversationState,
)
from core.debate_state import (
    build_pairwise_opinion_fallback,
    build_pairwise_semantic_instruction,
    extract_pairwise_comparison,
    find_pairwise_opinion_integrity_violations,
    infer_pairwise_position,
    looks_like_debate_continuation,
    pairwise_subject_from_hint,
)
from core.epistemic_router import (
    route_epistemic_authority,
)
from core.intent_router import (
    classify_turn,
)
import personality.opinion_ledger as opinion_ledger


def run():
    # --------------------------------------------------
    # 1. Generic comparative slang is understood semantically.
    # --------------------------------------------------

    comparison = extract_pairwise_comparison(
        "Rhea clears Mina and im not hearing otherwise"
    )

    assert comparison is not None
    assert comparison[
        "kind"
    ] == "pairwise_comparison"
    assert comparison[
        "left"
    ] == "Rhea"
    assert comparison[
        "right"
    ] == "Mina"
    assert comparison[
        "label"
    ] == "Rhea vs Mina"

    instruction = (
        build_pairwise_semantic_instruction(
            comparison
        )
    )

    assert instruction is not None
    assert (
        "evaluative slang"
        in instruction
    )
    assert (
        "does NOT mean"
        in instruction
    )
    assert (
        "not an instruction to agree"
        in instruction
    )

    assert (
        extract_pairwise_comparison(
            "i think i just sent money to the wrong account"
        )
        is None
    )

    assert (
        extract_pairwise_comparison(
            "why does my monitor flicker with vrr?"
        )
        is None
    )

    # --------------------------------------------------
    # 2. First-turn pairwise opinions enter the opinion lane, not generic
    #    casual conversation.
    # --------------------------------------------------

    state = ConversationState()

    first = classify_turn(
        "Rhea clears Mina and im not hearing otherwise",
        conversation_state=state,
    )

    assert first.intent == "share_opinion"
    assert first.subject == "Rhea vs Mina"
    assert (
        first.entities[
            "_pairwise_left"
        ]
        == "Rhea"
    )
    assert (
        first.entities[
            "_pairwise_right"
        ]
        == "Mina"
    )

    first = state.resolve_follow_up(
        first
    )

    state.update_from_turn(
        first
    )

    assert state.active_subject == "Rhea vs Mina"

    # --------------------------------------------------
    # 3. "Defend your take" resolves against the active pairwise debate before
    #    epistemic routing. It must not become a fight about the insult itself.
    # --------------------------------------------------

    second = classify_turn(
        "nah you're chatting shit. defend your take then",
        conversation_state=state,
    )

    assert second.intent == "share_opinion"
    assert second.subject == "Rhea vs Mina"
    assert second.is_follow_up is True
    assert (
        second.entities[
            "_debate_continuation"
        ]
        == "true"
    )

    second = state.resolve_follow_up(
        second
    )

    assert second.intent == "share_opinion"
    assert second.subject == "Rhea vs Mina"
    assert second.is_follow_up is True
    assert (
        second.entities[
            "_debate_continuation"
        ]
        == "true"
    )
    assert (
        "_conversation_context_user_text"
        in second.entities
    )

    route = route_epistemic_authority(
        second
    )

    contract = build_answer_contract(
        turn=second,
        route=route,
    )

    joined_limits = "\n".join(
        contract.forbidden_behaviours
    ).lower()

    assert "active opinion/debate subject" in joined_limits
    assert "bare concession" in joined_limits
    assert "prior mairon wording" in joined_limits

    # --------------------------------------------------
    # 4. A cold "defend your take" must not manufacture an active debate.
    # --------------------------------------------------

    cold = classify_turn(
        "defend your take then",
        conversation_state=ConversationState(),
    )

    assert not (
        cold.intent == "share_opinion"
        and cold.entities.get(
            "_debate_continuation"
        )
        == "true"
    )

    # --------------------------------------------------
    # 5. Explicit topic switches stay clean.
    # --------------------------------------------------

    state.update_from_turn(
        second
    )

    switched = classify_turn(
        "anyway why does my monitor sometimes flicker when VRR is on?",
        conversation_state=state,
    )

    switched = state.resolve_follow_up(
        switched
    )

    assert switched.intent == "factual_question"
    assert (
        switched.entities.get(
            "_debate_continuation"
        )
        is None
    )
    assert switched.subject != "Rhea vs Mina"

    # --------------------------------------------------
    # 6. Opinion Ledger stores Mairon's SIDE as persona state, while explicitly
    #    refusing to promote old factual wording into evidence.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as tmp:
        old_path = (
            opinion_ledger
            .OPINION_LEDGER_PATH
        )

        opinion_ledger.OPINION_LEDGER_PATH = (
            Path(tmp)
            / "mairon_opinions.json"
        )

        try:
            subject = (
                opinion_ledger
                .classify_opinion_subject(
                    user_input=(
                        "Rhea clears Mina and im not hearing otherwise"
                    ),
                    media_title=None,
                )
            )

            assert subject is not None
            assert subject[
                "kind"
            ] == "pairwise_comparison"

            entry = (
                opinion_ledger
                .record_opinion_if_needed(
                    subject=subject,
                    response_text=(
                        "Yeah, Rhea clears Mina for me."
                    ),
                    existing_entry=None,
                    user_input=(
                        "Rhea clears Mina and im not hearing otherwise"
                    ),
                    research_used=False,
                )
            )

            assert entry is not None
            assert entry[
                "position"
            ] == "left"

            context = (
                opinion_ledger
                .build_opinion_context_text(
                    entry
                )
            )

            assert (
                "Rhea over Mina"
                in context
            )
            assert (
                "NOT evidence"
                in context
            )
            assert (
                "factual/canon claims"
                in context
            )

            followup_subject = (
                opinion_ledger
                .classify_opinion_subject(
                    user_input=(
                        "defend your take then"
                    ),
                    media_title=None,
                    subject_hint=(
                        "Rhea vs Mina"
                    ),
                )
            )

            assert followup_subject is not None
            assert (
                followup_subject[
                    "key"
                ]
                == subject[
                    "key"
                ]
            )

        finally:
            opinion_ledger.OPINION_LEDGER_PATH = (
                old_path
            )

    # --------------------------------------------------
    # 7. Stance inference does not hallucinate a side from a misunderstood reply.
    # --------------------------------------------------

    subject = pairwise_subject_from_hint(
        "Rhea vs Mina"
    )

    assert (
        infer_pairwise_position(
            subject,
            user_input="Rhea clears Mina",
            response_text="Yeah, Rhea clears Mina.",
        )
        == "left"
    )

    assert (
        infer_pairwise_position(
            subject,
            user_input="Rhea clears Mina",
            response_text="Nah, Mina clears Rhea.",
        )
        == "right"
    )

    assert (
        infer_pairwise_position(
            subject,
            user_input="Rhea clears Mina",
            response_text=(
                "Glad to hear Rhea is done with Mina."
            ),
        )
        == "unclear"
    )

    # --------------------------------------------------
    # 8. Pairwise replies must establish Mairon's own stance (or explicit
    #    uncertainty) instead of merely mirroring Oliver.
    # --------------------------------------------------

    mirror_violations = (
        find_pairwise_opinion_integrity_violations(
            subject,
            user_input="Rhea clears Mina",
            response_text=(
                "Noted. I suppose you've decided Rhea has the edge over Mina."
            ),
            debate_continuation=False,
            established_position=None,
        )
    )

    assert any(
        "did not establish Mairon's own side"
        in item
        for item in mirror_violations
    )

    # Merely repeating Oliver's explicit relation in second-person framing is
    # still NOT Mairon's own stance.
    assert (
        infer_pairwise_position(
            subject,
            user_input="Rhea clears Mina",
            response_text="I get why you have Rhea over Mina.",
        )
        == "unclear"
    )

    assert (
        infer_pairwise_position(
            subject,
            user_input="Rhea clears Mina",
            response_text=(
                "Rhea over Mina is your call. "
                "I don't have a strong enough side of my own to fake one."
            ),
        )
        == "unclear"
    )

    reflected_relation_violations = (
        find_pairwise_opinion_integrity_violations(
            subject,
            user_input="Rhea clears Mina",
            response_text="I get why you have Rhea over Mina.",
            debate_continuation=False,
            established_position=None,
        )
    )

    assert reflected_relation_violations

    assert (
        find_pairwise_opinion_integrity_violations(
            subject,
            user_input="Rhea clears Mina",
            response_text="Nah, Mina over Rhea for me.",
            debate_continuation=False,
            established_position=None,
        )
        == []
    )

    assert (
        find_pairwise_opinion_integrity_violations(
            subject,
            user_input="defend your take then",
            response_text="Got it.",
            debate_continuation=True,
            established_position="right",
        )
    )

    safe_fallback = build_pairwise_opinion_fallback(
        subject,
        position="right",
        debate_continuation=True,
    )

    assert "Mina over Rhea" in safe_fallback
    assert "canon details" in safe_fallback
    assert safe_fallback != "Got it."

    # --------------------------------------------------
    # 9. An old pairwise ledger entry with an unclear side may be promoted
    #    into a clear accepted side without being mislabelled as a revision.
    # --------------------------------------------------

    with tempfile.TemporaryDirectory() as tmp:
        old_path = (
            opinion_ledger
            .OPINION_LEDGER_PATH
        )

        opinion_ledger.OPINION_LEDGER_PATH = (
            Path(tmp)
            / "mairon_opinions.json"
        )

        try:
            subject_for_upgrade = (
                opinion_ledger
                .classify_opinion_subject(
                    user_input="Rhea clears Mina",
                    media_title=None,
                )
            )

            unclear_entry = (
                opinion_ledger
                .record_opinion_if_needed(
                    subject=subject_for_upgrade,
                    response_text=(
                        "I get why you have Rhea over Mina."
                    ),
                    existing_entry=None,
                    user_input="Rhea clears Mina",
                    research_used=False,
                )
            )

            assert unclear_entry[
                "position"
            ] == "unclear"

            upgraded_entry = (
                opinion_ledger
                .record_opinion_if_needed(
                    subject=subject_for_upgrade,
                    response_text=(
                        "Nah, Mina over Rhea for me."
                    ),
                    existing_entry=unclear_entry,
                    user_input="Rhea clears Mina",
                    research_used=False,
                )
            )

            assert upgraded_entry[
                "position"
            ] == "right"

            uncertainty_entry = (
                opinion_ledger
                .record_opinion_if_needed(
                    subject=subject_for_upgrade,
                    response_text=(
                        "Rhea over Mina is your call. "
                        "I don't have a strong enough side of my own to fake one."
                    ),
                    existing_entry=upgraded_entry,
                    user_input="Rhea clears Mina",
                    research_used=False,
                )
            )

            assert uncertainty_entry[
                "position"
            ] == "unclear"

        finally:
            opinion_ledger.OPINION_LEDGER_PATH = (
                old_path
            )

    # --------------------------------------------------
    # 10. Provider integration carries pairwise semantics + prior stance into
    #    generation, while keeping old assistant wording non-evidentiary.
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
        "build_pairwise_semantic_instruction"
        in provider_source
    )
    assert (
        "core_is_debate_continuation"
        in provider_source
    )
    assert (
        "[Opinion] Active pairwise debate continuation loaded."
        in provider_source
    )
    assert (
        "Give actual reasons for the position."
        in provider_source
    )
    assert (
        "subject_hint="
        in provider_source
    )
    assert (
        "find_pairwise_opinion_integrity_violations"
        in provider_source
    )
    assert (
        "build_pairwise_opinion_fallback"
        in provider_source
    )
    assert (
        "persona-safe debate fallback"
        in provider_source
    )

    print(
        "Mairon Phase 11.4 opinion/debate state tests: PASS"
    )


if __name__ == "__main__":
    run()
