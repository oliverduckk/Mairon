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


import core.claim_grounding as grounding
from core.source_lock import (
    build_source_lock_instruction,
    build_source_lock_packet,
    find_factual_personal_history_violations,
    find_structural_source_lock_violations,
    repair_factual_personal_history_tail,
    recommended_source_lock_prior_window,
)


class MustNotCallClient:
    def chat(
        self,
        **kwargs,
    ):
        raise AssertionError(
            "Phase 6.8.9 deterministic source lock should reject/repair before verifier call"
        )


def run():
    # --------------------------------------------------
    # 1. Source locks preserve explicit entity identity.
    # --------------------------------------------------

    xm6_user = (
        "Anyway, my XM6s are at 40% and I forgot to charge them before work. Classic."
    )

    packet = build_source_lock_packet(
        user_input=xm6_user,
        conversation=[],
        max_prior_user_messages=1,
    )

    assert any(
        item.owner == "Oliver"
        and item.key == "xm6s"
        for item in packet.possessions
    ), packet

    entity_violations = (
        find_structural_source_lock_violations(
            user_input=xm6_user,
            draft=(
                "Forty percent is the perfect amount of battery to let you panic "
                "about your phone dying during a meeting."
            ),
            conversation=[],
        )
    )

    assert any(
        "source-lock entity substitution/invention"
        in violation
        and "phone"
        in violation
        for violation in entity_violations
    ), entity_violations

    scalar_substitution_violations = (
        find_structural_source_lock_violations(
            user_input=xm6_user,
            draft=(
                "Forty percent is the perfect amount of battery to let you feel "
                "the anxiety of a dying phone while pretending you're in control. "
                "At least your XM6s are honest about their impending doom."
            ),
            conversation=[],
        )
    )

    assert any(
        "source-lock quantitative binding"
        in violation
        and "dying phone"
        in violation
        for violation in scalar_substitution_violations
    ), scalar_substitution_violations

    faithful_entity_violations = (
        find_structural_source_lock_violations(
            user_input=xm6_user,
            draft=(
                "Your XM6s are still alive at 40%, so naturally they're acting smug about it."
            ),
            conversation=[],
        )
    )

    assert faithful_entity_violations == [], (
        faithful_entity_violations
    )

    # --------------------------------------------------
    # 2. Source locks preserve actor -> target direction.
    # --------------------------------------------------

    debug_user = (
        "Don't get smug. You're still the assistant I have to debug every night."
    )

    debug_packet = build_source_lock_packet(
        user_input=debug_user,
        conversation=[],
    )

    assert any(
        relation.actor == "Oliver"
        and relation.action == "debug"
        and relation.target == "Mairon"
        for relation in debug_packet.relations
    ), debug_packet.relations

    relation_violations = (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=(
                "I'll keep my mouth shut and focus on your code, then."
            ),
            conversation=[],
        )
    )

    assert any(
        "source-lock relation reversal"
        in violation
        for violation in relation_violations
    ), relation_violations

    faithful_relation_violations = (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=(
                "Fine. I'm still the thing you have to debug every night."
            ),
            conversation=[],
        )
    )

    assert faithful_relation_violations == [], (
        faithful_relation_violations
    )

    # --------------------------------------------------
    # 3. Generation receives explicit source-lock anchors.
    # --------------------------------------------------

    standalone_window = (
        recommended_source_lock_prior_window(
            user_input=debug_user,
            intent="casual_conversation",
        )
    )

    assert standalone_window == 0

    source_lock_text = build_source_lock_instruction(
        user_input=debug_user,
        conversation=[
            {
                "role": "user",
                "content": xm6_user,
            }
        ],
        intent="casual_conversation",
        max_prior_user_messages=standalone_window,
    )

    assert source_lock_text is not None
    assert "Oliver -> 'XM6s'" not in source_lock_text
    assert "Oliver --debug--> Mairon" in source_lock_text
    assert "Never reverse actor/target direction" in source_lock_text

    followup_user = (
        "At least my iPad is fully charged."
    )

    followup_window = (
        recommended_source_lock_prior_window(
            user_input=followup_user,
            intent="share_context",
        )
    )

    assert followup_window == 1

    followup_lock_text = build_source_lock_instruction(
        user_input=followup_user,
        conversation=[
            {
                "role": "user",
                "content": xm6_user,
            }
        ],
        intent="share_context",
        max_prior_user_messages=followup_window,
    )

    assert "Oliver -> 'XM6s'" in followup_lock_text
    assert "Oliver -> 'iPad'" in followup_lock_text

    # --------------------------------------------------
    # 4. Factual answer tails cannot invent Oliver/Mairon history.
    # --------------------------------------------------

    factual_user = (
        "Anyway, what's the capital of Canada?"
    )

    factual_bad_drafts = [
        (
            "Ottawa. I didn't get lost reading a book about it this time."
        ),
        (
            "Ottawa. Stop trying to trick me into thinking it’s Toronto, Vancouver, "
            "or some other city you’ve probably visited at least once."
        ),
    ]

    for bad_draft in factual_bad_drafts:
        history_violations = (
            find_factual_personal_history_violations(
                user_input=factual_user,
                draft=bad_draft,
                conversation=[],
            )
        )

        assert history_violations, bad_draft

        repaired, removed = (
            repair_factual_personal_history_tail(
                user_input=factual_user,
                draft=bad_draft,
                conversation=[],
            )
        )

        assert repaired == "Ottawa.", (
            bad_draft,
            repaired,
        )

        assert removed, bad_draft

    clean_repaired, clean_removed = (
        repair_factual_personal_history_tail(
            user_input=factual_user,
            draft="Ottawa.",
            conversation=[],
        )
    )

    assert clean_repaired == "Ottawa."
    assert clean_removed == []

    # --------------------------------------------------
    # 5. Deterministic checks happen BEFORE Qwen self-verification.
    # --------------------------------------------------

    original_should_ground = (
        grounding.should_verify_core_grounding
    )

    original_should_factual = (
        grounding.should_verify_factual_focus_fidelity
    )

    grounding.should_verify_core_grounding = (
        lambda contract: True
    )

    grounding.should_verify_factual_focus_fidelity = (
        lambda contract: True
    )

    try:
        violations = (
            grounding.verify_core_grounded_draft(
                client=MustNotCallClient(),
                model="qwen3.5:9b",
                user_input=xm6_user,
                draft=(
                    "Forty percent should be enough for your phone to limp through the morning."
                ),
                core_answer_contract=None,
                conversation=[],
            )
        )

        assert any(
            "source-lock entity substitution/invention"
            in violation
            for violation in violations
        ), violations

        # Factual personal-history checks are wired one layer above the
        # semantic fallback so Phase 6.8.8 can still exercise that verifier
        # independently. Test the deterministic helper directly here.
        violations = (
            find_factual_personal_history_violations(
                user_input=factual_user,
                draft=(
                    "Ottawa. You've probably visited another Canadian city before."
                ),
                conversation=[],
            )
        )

        assert any(
            "unsupported personal/history tail"
            in violation
            for violation in violations
        ), violations

    finally:
        grounding.should_verify_core_grounding = (
            original_should_ground
        )

        grounding.should_verify_factual_focus_fidelity = (
            original_should_factual
        )

    # --------------------------------------------------
    # 6. Provider is wired to generation-time locks and tail repair.
    # --------------------------------------------------

    provider_text = (
        PROJECT_ROOT
        / "src"
        / "ai"
        / "ollama_provider.py"
    ).read_text()

    assert (
        "build_source_lock_instruction"
        in provider_text
    )

    assert (
        "[Grounding] Source-lock anchors active."
        in provider_text
    )

    assert (
        "repair_factual_personal_history_tail"
        in provider_text
    )

    assert (
        "[Grounding] Removed unsupported factual personality/history tail."
        in provider_text
    )

    print(
        "Mairon Core Phase 6.8.9 source-lock relation tests: PASS"
    )


if __name__ == "__main__":
    run()
