from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_insufficient_user_context_fallback,
    build_user_context_reasoning_fallback,
    find_insufficient_context_overreach_violations,
    find_scaler_leakage_contradiction_violations,
)


def run():
    # 15:36 hidden PASS: missing airline policy/dimensions means permission is
    # unknown, not categorically disallowed. Trip length also cannot be used to
    # invent a stricter carrier policy.
    air_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="insufficient_user_context",
    )
    air_bad = (
        "No, you are definitely not allowed without knowing the airline and bag dimensions. "
        "Every carrier has different rules for carry-on size and weight, especially for a 3-week trip where they might be stricter."
    )
    violations = find_insufficient_context_overreach_violations(air_bad, air_contract)
    assert any("unknown policy/permission" in v or "generic world claim" in v for v in violations), violations

    air_good = (
        "I can't tell whether it is allowed yet because you haven't given me the airline's carry-on policy or the bag dimensions."
    )
    assert not find_insufficient_context_overreach_violations(air_good, air_contract)
    fallback = build_insufficient_user_context_fallback(
        "bro if i take my hiking backpack as carry-on for a 3 week trip, am i DEFINITELY allowed? "
        "i haven't told you the airline or bag dimensions"
    )
    assert "can't determine" in fallback.lower()
    assert "airline" in fallback.lower() and "bag dimensions" in fallback.lower()

    # 15:36 hidden PASS: scaler leakage can bias evaluation optimistically, but
    # the direction/magnitude of the score change is not guaranteed.
    scaler_user = (
        "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"
    )
    leakage_history = [
        {
            "role": "user",
            "content": "bro can u explain data leakage in machine learning like i actually need to understand it",
        }
    ]
    scaler_bad = (
        "If you fit StandardScaler on all rows first, the test rows influence the fitted mean and standard deviation. "
        "The test set is no longer independent, so your evaluation is biased upward."
    )
    violations = find_scaler_leakage_contradiction_violations(
        scaler_user, scaler_bad, leakage_history
    )
    assert any("direction of evaluation bias" in v for v in violations), violations

    scaler_good = (
        "If you fit StandardScaler on all rows first, the held-out test rows influence the fitted mean and standard deviation. "
        "That breaks evaluation independence and can make the estimate too optimistic, so fit on train only and transform test with those parameters."
    )
    assert not find_scaler_leakage_contradiction_violations(
        scaler_user, scaler_good, leakage_history
    )

    # 15:36 hidden PASS: a Mac-vs-Windows follow-up with explicit technical
    # criteria does not need Oliver's budget or current-device ownership. If
    # drafts are rejected, Core should still compare the requested pair rather
    # than return the generic missing-user-info fallback.
    comparison_history = [
        {
            "role": "user",
            "content": "mac vs windows for dev... actually don't tell me one is 'better' overall. gimme the real trade-offs",
        }
    ]
    comparison_user = (
        "okay narrow it to Python, Linux VMs and messing around with networks. "
        "don't invent my budget or which one i already own"
    )
    comparison = build_user_context_reasoning_fallback(
        comparison_user,
        comparison_history,
    )
    low = comparison.lower()
    assert "mac" in low and "windows" in low, comparison
    assert "python" in low and ("linux" in low or "vm" in low), comparison
    assert "don't have enough reliable user-supplied information" not in low, comparison
    assert "budget" in low and "own" in low, comparison

    print(
        "PASS: B20 preserves uncertainty, calibrates scaler bias direction, and keeps constrained pairwise technical comparisons useful"
    )


if __name__ == "__main__":
    run()
