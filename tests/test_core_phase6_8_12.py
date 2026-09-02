import ast
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from core.claim_grounding import (
    find_deterministic_grounding_violations,
)
from core.source_lock import (
    build_source_lock_packet,
    find_structural_source_lock_violations,
)


def _load_provider_generation_options():
    provider_path = PROJECT_ROOT / "src" / "ai" / "ollama_provider.py"
    provider_text = provider_path.read_text()
    tree = ast.parse(provider_text)

    wanted = {"build_direct_generation_options"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]

    namespace = {}
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(provider_path), "exec"), namespace)
    return namespace["build_direct_generation_options"], provider_text


build_direct_generation_options, provider_text = (
    _load_provider_generation_options()
)


def run():
    # --------------------------------------------------
    # 1. Possession extraction must not cross time/punctuation boundaries.
    # --------------------------------------------------
    desk_user = (
        "I finally cleaned my desk this morning. It was getting ridiculous."
    )

    packet = build_source_lock_packet(
        user_input=desk_user,
        conversation=[],
        max_prior_user_messages=0,
    )

    oliver_entities = [
        item.key
        for item in packet.possessions
        if item.owner == "Oliver"
    ]

    assert oliver_entities == ["desk"], oliver_entities

    # The exact Desk benchmark false positives must no longer be treated as
    # concrete entity substitutions simply because they contain "your X".
    desk_banter = (
        "Glad to see that pile of digital dust has been exorcised from your "
        "desk, Oliver. Now you can stop pretending the clutter is art."
    )

    violations = find_structural_source_lock_violations(
        user_input=desk_user,
        draft=desk_banter,
        conversation=[],
        max_prior_user_messages=0,
    )

    assert not any(
        "desk Oliver Now you" in violation
        or "entity substitution/invention" in violation
        for violation in violations
    ), violations

    # --------------------------------------------------
    # 2. Entity substitution remains blocked when a bound value/property moves.
    # --------------------------------------------------
    xm6_user = (
        "Anyway, my XM6s are at 40% and I forgot to charge them before work. Classic."
    )

    percent_swap = (
        "Forty percent is the polite way of saying your phone has already given up."
    )

    percent_violations = find_structural_source_lock_violations(
        user_input=xm6_user,
        draft=percent_swap,
        conversation=[],
        max_prior_user_messages=0,
    )

    assert any(
        "source-lock entity substitution/invention" in violation
        and "phone" in violation
        for violation in percent_violations
    ), percent_violations

    ipad_user = "At least my iPad is fully charged."
    prior = [{"role": "user", "content": xm6_user}]

    predicate_swap = "At least your phone is fully charged."

    predicate_violations = find_structural_source_lock_violations(
        user_input=ipad_user,
        draft=predicate_swap,
        conversation=prior,
        max_prior_user_messages=1,
    )

    assert any(
        "source-lock entity substitution/invention" in violation
        and "fully charged" in violation
        and "phone" in violation
        for violation in predicate_violations
    ), predicate_violations

    # --------------------------------------------------
    # 3. Concrete Oliver physical-action claims require user grounding.
    # --------------------------------------------------
    rushing_draft = (
        "At least the battery didn't die while you were rushing out; that "
        "would have been a tragedy."
    )

    rushing_violations = find_deterministic_grounding_violations(
        user_input=xm6_user,
        draft=rushing_draft,
        core_answer_contract=None,
        conversation=[],
    )

    assert any(
        "physical-action/state claim involving rush" in violation
        for violation in rushing_violations
    ), rushing_violations

    desk_followup = "Give it two days and it'll probably be fucked again."
    prior_desk = [{"role": "user", "content": desk_user}]

    sitting_draft = (
        "Two days? You're already expecting the desk to rebel before you've "
        "even sat down."
    )

    sitting_violations = find_deterministic_grounding_violations(
        user_input=desk_followup,
        draft=sitting_draft,
        core_answer_contract=None,
        conversation=prior_desk,
    )

    assert any(
        "physical-action/state claim involving sit" in violation
        for violation in sitting_violations
    ), sitting_violations

    # If Oliver actually supplies the activity, it is allowed.
    grounded_rush_user = "I was rushing out before work and forgot to charge my XM6s."
    grounded_rush_draft = "You were rushing out and forgot to charge the XM6s."

    grounded_violations = find_deterministic_grounding_violations(
        user_input=grounded_rush_user,
        draft=grounded_rush_draft,
        core_answer_contract=None,
        conversation=[],
    )

    assert not any(
        "physical-action/state claim involving rush" in violation
        for violation in grounded_violations
    ), grounded_violations

    # --------------------------------------------------
    # 4. Mairon cannot invent its own record-keeping history.
    # --------------------------------------------------
    recall_user = (
        "Back to the desk — what did I say I changed about when I cleaned it?"
    )

    ledger_draft = (
        "You corrected yourself from this morning to last night. Don't worry, "
        "I didn't write that down in a ledger somewhere."
    )

    ledger_violations = find_deterministic_grounding_violations(
        user_input=recall_user,
        draft=ledger_draft,
        core_answer_contract=None,
        conversation=[],
    )

    assert any(
        "record-keeping/history" in violation
        for violation in ledger_violations
    ), ledger_violations

    # --------------------------------------------------
    # 5. Straight factual questions use a lower-variance concise generation lane.
    # --------------------------------------------------
    factual_options = build_direct_generation_options("factual_question")

    assert factual_options == {
        "temperature": 0.2,
        "num_predict": 96,
    }, factual_options

    assert "Do not discuss internal answer-generation process" in provider_text
    assert "whether a fact is hard-coded" in provider_text

    print("Mairon Core Phase 6.8.12 structural grounding cleanup tests: PASS")


if __name__ == "__main__":
    run()
