import ast
import re
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


from core.source_lock import (
    find_structural_source_lock_violations,
)


def _load_provider_helpers():
    provider_path = (
        PROJECT_ROOT
        / "src"
        / "ai"
        / "ollama_provider.py"
    )

    provider_text = provider_path.read_text()
    tree = ast.parse(
        provider_text
    )

    wanted = {
        "_current_turn_needs_recent_user_context",
        "should_use_restricted_generation_context",
        "repair_factual_follow_up_tail",
    }

    nodes = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name in wanted
    ]

    namespace = {
        "re": re,
    }

    module = ast.Module(
        body=nodes,
        type_ignores=[],
    )

    exec(
        compile(
            module,
            str(provider_path),
            "exec",
        ),
        namespace,
    )

    return (
        namespace[
            "repair_factual_follow_up_tail"
        ],
        namespace[
            "should_use_restricted_generation_context"
        ],
    )


(
    repair_factual_follow_up_tail,
    should_use_restricted_generation_context,
) = _load_provider_helpers()


def run():
    # --------------------------------------------------
    # 1. Source-lock must be conservative around clause boundaries.
    # --------------------------------------------------

    debug_user = (
        "Don't get smug. You're still the assistant I have to debug every night."
    )

    false_positive_one = (
        "I'll keep my code clean enough for you to sleep through, won't I?"
    )

    false_positive_two = (
        "Fine, fine. I'll stop acting like a god while you're busy trying "
        "to debug me into submission."
    )

    assert (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=false_positive_one,
            conversation=[],
            max_prior_user_messages=0,
        )
        == []
    )

    assert (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=false_positive_two,
            conversation=[],
            max_prior_user_messages=0,
        )
        == []
    )

    # The live true reversal from Phase 6.8.9 must still be caught.
    true_reversal = (
        "I'll keep my mouth shut, Oliver. Just don't expect me to fix your "
        "code while you sleep; that's a job for tomorrow."
    )

    reversal_violations = (
        find_structural_source_lock_violations(
            user_input=debug_user,
            draft=true_reversal,
            conversation=[],
            max_prior_user_messages=0,
        )
    )

    assert any(
        "source-lock relation reversal"
        in violation
        for violation in reversal_violations
    ), reversal_violations

    # --------------------------------------------------
    # 2. Abstract possessives are not concrete entity substitutions.
    # --------------------------------------------------

    ipad_user = (
        "At least my iPad is fully charged."
    )

    prior = [
        {
            "role": "user",
            "content": (
                "Anyway, my XM6s are at 40% and I forgot to charge them "
                "before work. Classic."
            ),
        }
    ]

    abstract_banter = (
        "At least your iPad is charged. Maybe it's jealous of your attention span."
    )

    assert (
        find_structural_source_lock_violations(
            user_input=ipad_user,
            draft=abstract_banter,
            conversation=prior,
            max_prior_user_messages=1,
        )
        == []
    )

    # Concrete substitution remains blocked.
    concrete_substitution = (
        "At least your phone is fully charged."
    )

    concrete_violations = (
        find_structural_source_lock_violations(
            user_input=ipad_user,
            draft=concrete_substitution,
            conversation=prior,
            max_prior_user_messages=1,
        )
    )

    assert any(
        "source-lock entity substitution/invention"
        in violation
        for violation in concrete_violations
    ), concrete_violations

    # --------------------------------------------------
    # 3. Standalone factual questions do not receive stale live history.
    # --------------------------------------------------

    assert (
        should_use_restricted_generation_context(
            "factual_question",
            user_input="Anyway, what's the capital of Canada?",
        )
        is True
    )

    # A genuine backward-pointing factual follow-up keeps live context.
    assert (
        should_use_restricted_generation_context(
            "factual_question",
            user_input="And what about its population?",
        )
        is False
    )

    # Existing social isolation remains unchanged.
    assert (
        should_use_restricted_generation_context(
            "share_context",
            user_input="My iPad is fully charged.",
        )
        is True
    )

    # --------------------------------------------------
    # 4. Once a factual answer exists, unsolicited question tails are cut.
    # --------------------------------------------------

    live_ottawa_draft = (
        "It's Ottawa. Toronto might be louder, but it doesn't make it the capital.\n\n"
        "So, did you manage to plug in those XM6s before your day got away from you?"
    )

    repaired, removed = (
        repair_factual_follow_up_tail(
            live_ottawa_draft
        )
    )

    assert repaired == (
        "It's Ottawa. Toronto might be louder, but it doesn't make it the capital."
    ), repaired

    assert removed == [
        "So, did you manage to plug in those XM6s before your day got away from you?"
    ], removed

    # A clarification-only response is still allowed to remain a question.
    clarification = (
        "Which Canada-related statistic did you mean?"
    )

    repaired, removed = (
        repair_factual_follow_up_tail(
            clarification
        )
    )

    assert repaired == clarification
    assert removed == []

    print(
        "Mairon Core Phase 6.8.11 factual isolation/conservative source-lock tests: PASS"
    )


if __name__ == "__main__":
    run()
