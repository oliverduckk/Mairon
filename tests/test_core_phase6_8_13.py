import ast
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from core.source_lock import (
    find_factual_process_commentary_violations,
    find_structural_source_lock_violations,
)


def _load_provider_helpers():
    provider_path = PROJECT_ROOT / "src" / "ai" / "ollama_provider.py"
    provider_text = provider_path.read_text()
    tree = ast.parse(provider_text)

    wanted = {
        "repair_factual_process_tail",
        "repair_live_recall_tail",
    }

    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]

    namespace = {
        "re": re,
        "find_factual_process_commentary_violations": (
            find_factual_process_commentary_violations
        ),
    }

    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(provider_path), "exec"), namespace)

    return (
        namespace["repair_factual_process_tail"],
        namespace["repair_live_recall_tail"],
        provider_text,
    )


(
    repair_factual_process_tail,
    repair_live_recall_tail,
    provider_text,
) = _load_provider_helpers()


def run():
    # --------------------------------------------------
    # 1. Actor/target locks are relation-scoped, not globally directional.
    # --------------------------------------------------
    debug_user = (
        "Don't get smug. You're still the assistant I have to debug every night."
    )

    real_reversal = (
        "I'll keep my mouth shut. Just don't expect me to fix your code."
    )

    real_violations = find_structural_source_lock_violations(
        user_input=debug_user,
        draft=real_reversal,
        conversation=[],
        max_prior_user_messages=0,
    )

    assert any(
        "source-lock relation reversal" in violation
        for violation in real_violations
    ), real_violations

    # These are opposite-direction relations between the same speakers, but
    # they are NOT the inverse of Oliver's maintenance/debug relation.
    for unrelated_draft in (
        "Don't worry, I can mock you later.",
        "I can remember your desk schedule without becoming your debugger.",
        "You're as unreliable with your own schedule as anyone else.",
    ):
        violations = find_structural_source_lock_violations(
            user_input=debug_user,
            draft=unrelated_draft,
            conversation=[],
            max_prior_user_messages=0,
        )

        assert not any(
            "source-lock relation reversal" in violation
            for violation in violations
        ), (unrelated_draft, violations)

    # --------------------------------------------------
    # 2. New concrete temporal relations on locked entities are rejected.
    # --------------------------------------------------
    xm6_user = (
        "Anyway, my XM6s are at 40% and I forgot to charge them before work. Classic."
    )
    ipad_user = "At least my iPad is fully charged."
    prior = [{"role": "user", "content": xm6_user}]

    overnight_draft = (
        "Well, at least your iPad didn't have to survive the night on fumes "
        "like the XM6s did."
    )

    temporal_violations = find_structural_source_lock_violations(
        user_input=ipad_user,
        draft=overnight_draft,
        conversation=prior,
        max_prior_user_messages=1,
    )

    assert any(
        "source-lock temporal relation invention" in violation
        for violation in temporal_violations
    ), temporal_violations

    # --------------------------------------------------
    # 3. Live recall preserves the correct answer prefix instead of retrying it.
    # --------------------------------------------------
    recall_draft = (
        "You corrected yourself from this morning to last night. "
        "Don't worry, I didn't write that down in a ledger just to mock you later."
    )

    repaired, removed = repair_live_recall_tail(recall_draft)

    assert repaired == (
        "You corrected yourself from this morning to last night."
    ), repaired
    assert removed == [
        "Don't worry, I didn't write that down in a ledger just to mock you later."
    ], removed

    # A short lead-in may precede the substantive answer.
    repaired, removed = repair_live_recall_tail(
        "Yep. You corrected yourself from this morning to last night. "
        "No need for a victory lap."
    )

    assert repaired == (
        "Yep. You corrected yourself from this morning to last night."
    ), repaired
    assert removed == ["No need for a victory lap."], removed

    # --------------------------------------------------
    # 4. Factual answer-generation/process commentary is removed or rejected.
    # --------------------------------------------------
    factual_draft = (
        "The capital of Canada is Ottawa. "
        "I know this one well enough to answer without needing to check a map or anything."
    )

    repaired, removed = repair_factual_process_tail(factual_draft)

    assert repaired == "The capital of Canada is Ottawa.", repaired
    assert removed == [
        "I know this one well enough to answer without needing to check a map or anything."
    ], removed

    assert find_factual_process_commentary_violations(
        "Ottawa, which I know without checking a map."
    )

    assert find_factual_process_commentary_violations(
        "Ottawa. Vancouver can stop auditioning."
    ) == []

    # --------------------------------------------------
    # 5. Production provider applies both answer-preserving repairs.
    # --------------------------------------------------
    assert "repair_live_recall_tail" in provider_text
    assert "repair_factual_process_tail" in provider_text
    assert (
        "Preserved live-recall answer prefix; removed trailing decoration."
        in provider_text
    )
    assert "Removed factual answer-generation/process tail." in provider_text

    # --------------------------------------------------
    # 6. Router diagnostic no longer hard-codes the retired Qwen3 14B label.
    # --------------------------------------------------
    router_text = (
        PROJECT_ROOT / "src" / "core" / "router.py"
    ).read_text()

    assert "[AI] Using local: Qwen3 14B" not in router_text
    assert "_local_model_label" in router_text
    assert "get_local_model_name" in router_text

    print(
        "Mairon Core Phase 6.8.13 scoped-relation/answer-prefix tests: PASS"
    )


if __name__ == "__main__":
    run()
