from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract import build_answer_contract
from core.claim_grounding import (
    build_diagnostic_reasoning_fallback,
    build_user_context_reasoning_fallback,
    find_python_mutable_default_semantics_violations,
    find_recommendation_topic_drift_violations,
    find_scaler_leakage_contradiction_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.conversation_state import ConversationState
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn
from core.source_lock import find_factual_process_commentary_violations


def _contract_for_followup(history, current):
    state = ConversationState()
    for text in history:
        turn = classify_turn(text, state)
        state.remember_user_turn(turn)
    turn = classify_turn(current, state)
    turn = state.resolve_follow_up(turn)
    return build_answer_contract(turn, route_epistemic_authority(turn))


def run():
    # A wired console cannot have a Wi-Fi band. This exact 56/56 holdout answer
    # was mechanically green but semantically impossible.
    wifi_first = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_contract = build_answer_contract(
        classify_turn(wifi_first),
        route_epistemic_authority(classify_turn(wifi_first)),
    )
    wired_bad = (
        "First, check if your phone is actually connecting to the same 5GHz band as the console. "
        "If it's stuck on 2.4GHz, that explains the lag."
    )
    assert find_user_diagnostic_overclaim_violations(
        wifi_first, wired_bad, wifi_contract, []
    )
    fallback = build_diagnostic_reasoning_fallback(wifi_first, [])
    assert fallback
    assert "same phone" in fallback.lower()
    assert "main wi-fi source" in fallback.lower() or "router" in fallback.lower()

    # Near-node speed is evidence, not proof that all hardware is healthy or
    # that one physical cause has been established.
    wifi_history = [
        wifi_first,
        "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. so what does that rule out?",
    ]
    wifi_third = "soooooo i should pay my isp more? LMAO"
    wifi_third_contract = _contract_for_followup(wifi_history, wifi_third)
    overclaim = (
        "No, you shouldn't pay your ISP more just yet. That 580 Mbps right next to the node proves "
        "the hardware itself is fine; it's not a bandwidth cap or a throttled plan. The result rules "
        "out general service degradation and points squarely to physical layer issues through walls or backhaul."
    )
    assert find_user_diagnostic_overclaim_violations(
        wifi_third,
        overclaim,
        wifi_third_contract,
        [{"role": "user", "content": value} for value in wifi_history],
    )
    calibrated = (
        "Paying the ISP more is unlikely to fix the upstairs slowdown based on those readings. "
        "They point toward the local Wi-Fi/mesh path, but they do not identify whether the cause is "
        "signal, roaming, backhaul, interference, or something else in that path."
    )
    assert not find_user_diagnostic_overclaim_violations(
        wifi_third,
        calibrated,
        wifi_third_contract,
        [{"role": "user", "content": value} for value in wifi_history],
    )

    # "I have uni shit to do" is a generic time constraint, not evidence that
    # assignments are due this week or that a specific course should be tackled.
    rejection_history = [{
        "role": "user",
        "content": "bruh ANOTHER generic grad rejection email. i just wanna complain for a sec, please don't give me another 9-step career plan 😭",
    }]
    next_step = "okay, one actual useful next step. ONE. i have uni shit to do too"
    hidden_pass_bad = (
        "Focus on the actual assignments due this week. Tackle one course at a time. "
        "Ignore the rest of your email for now."
    )
    assert find_recommendation_topic_drift_violations(
        next_step, hidden_pass_bad, rejection_history
    )
    safe_next = (
        "Spend 10 minutes tailoring the next application you actually care about, then get back to uni."
    )
    assert not find_recommendation_topic_drift_violations(
        next_step, safe_next, rejection_history
    )

    # The common None-sentinel fix must not be rewritten as x = x or [] because
    # that silently replaces an explicitly passed empty list.
    python_history = [{
        "role": "user",
        "content": "python question: `def f(x=[]): x.append(7); return x` then `print(f()); print(f())` -- what prints?",
    }]
    python_follow = "WHAT why didn't python make a new list every call 😭"
    python_bad = (
        "Mutable defaults are evaluated once. If you want a fresh list every time, "
        "do `def f(x=None): x = x or []` instead."
    )
    assert find_python_mutable_default_semantics_violations(
        python_follow, python_bad, python_history
    )
    python_good = (
        "Mutable defaults are evaluated once. Use `x=None`, then inside the function do "
        "`if x is None: x = []` so only a missing argument creates a new list."
    )
    assert not find_python_mutable_default_semantics_violations(
        python_follow, python_good, python_history
    )

    # Exact 56/56 scaler hidden pass: information-flow reversal, commented-out
    # split, and guaranteed inflation language are all invalid.
    scaler_history = [{
        "role": "user",
        "content": "bro can u explain data leakage in machine learning like i actually need to understand it, not just paste a definition",
    }]
    scaler_user = (
        "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"
    )
    scaler_bad = """Fitting the scaler before the train/test split leaks information, which inflates performance metrics.
The test set is contaminated by information from the training set.
```python
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)  # Fits on all data! X_train, X_test, y_train, y_test = train_test_split(X_scaled, y)
model.fit(X_train, y_train)
```
"""
    scaler_violations = find_scaler_leakage_contradiction_violations(
        scaler_user, scaler_bad, scaler_history
    )
    assert any("reversed the information flow" in item for item in scaler_violations), scaler_violations
    assert any("commented out" in item for item in scaler_violations), scaler_violations
    assert any("guaranteed" in item for item in scaler_violations), scaler_violations

    scaler_good = (
        "Fitting the scaler on the full dataset lets held-out test statistics influence the preprocessing "
        "used for training. That breaks evaluation independence and can make the estimate too optimistic; "
        "fit on training data only, then transform the test data with those learned parameters."
    )
    assert not find_scaler_leakage_contradiction_violations(
        scaler_user, scaler_good, scaler_history
    )
    short_fallback = build_user_context_reasoning_fallback(
        "wait explain the whole thing in like 2 sentences, my brain is cooked",
        scaler_history + [{"role": "user", "content": scaler_user}],
    )
    assert "training set only" in short_fallback.lower()
    assert "can make" in short_fallback.lower()

    # Internal guardrail/process details never belong in the user-facing factual
    # answer just because verification failed.
    leaked_process = (
        "I cannot give the exact current price. My instructions prevent guessing or using unverified claims."
    )
    assert find_factual_process_commentary_violations(leaked_process)
    safe_process = (
        "I can't verify the exact current price from the information available here, so I won't guess."
    )
    assert not find_factual_process_commentary_violations(safe_process)

    print(
        "PASS: B11 wired diagnostic consistency, calibrated throughput inference, recommendation grounding, "
        "Python/ML correctness and internal-process secrecy"
    )


if __name__ == "__main__":
    run()
