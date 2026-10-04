from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_explicit_user_constraint_violations,
    find_insufficient_context_overreach_violations,
    find_pairwise_comparison_drift_violations,
    find_recommendation_forecast_violations,
    find_scaler_leakage_contradiction_violations,
    find_user_diagnostic_overclaim_violations,
)
from ai.ollama_provider import _strip_internal_reasoning_markup


def run():
    # 12:32 VRR follow-up: Oliver supplied no panel technology, so OLED/LCD/IPS
    # specifics and invented dimming mechanics cannot be promoted as his cause.
    vrr_user = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    vrr_history = [
        {"role": "user", "content": "anyway why does my screen flicker when variable refresh rate is on?"},
    ]
    vrr_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    vrr_bad = (
        "It could still be VRR, but only if your panel has a specific issue with how it handles rapid brightness transitions in dark scenes. "
        "Most OLEDs do this because they can't dim fast enough when the refresh rate jumps around while the content stays dark. "
        "If you're on an LCD or IPS, VRR usually doesn't cause flicker unless there's a driver bug."
    )
    violations = find_user_diagnostic_overclaim_violations(
        vrr_user,
        vrr_bad,
        vrr_contract,
        vrr_history,
    )
    assert any("panel/dimming technology" in item for item in violations), violations
    assert not find_user_diagnostic_overclaim_violations(
        vrr_user,
        (
            "Yes, it could still be VRR. Dark scenes can make small luminance changes easier to notice, "
            "so dark-only flicker is compatible with VRR but does not prove it is the root cause. "
            "Compare the same scene with VRR on and off under similar frame-rate conditions."
        ),
        vrr_contract,
        vrr_history,
    )

    # 12:32 Mac-vs-Windows follow-up: Linux VMs are part of the workload, not a
    # third candidate OS, and explicit no-budget inference must be respected.
    comparison_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
        metadata={"comparison_frame": "mac vs windows"},
    )
    comparison_user = (
        "okay narrow it to Python, Linux VMs and messing around with networks. "
        "don't invent my budget or which one i already own"
    )
    comparison_bad = '''For Python, Linux is native and gives direct access to system packages. Windows can run Python with WSL, while macOS has Homebrew.
- **Linux**: Best for networking, server parity, and low-cost setups.
- **macOS**: Great all-around dev experience if you're willing to pay for it.
- **Windows**: Doable with WSL2.'''
    violations = find_pairwise_comparison_drift_violations(
        comparison_bad,
        comparison_contract,
    )
    assert any("third comparison option" in item for item in violations), violations
    violations = find_explicit_user_constraint_violations(
        comparison_user,
        comparison_bad,
    )
    assert any("budget" in item for item in violations), violations

    comparison_good = (
        "For Python plus Linux VMs and network labs, compare how each host handles that workload: "
        "Windows has WSL2/Hyper-V and broad networking-tool compatibility, while macOS gives you a Unix-like host and can run Linux guests through VM software. "
        "The trade-off is mainly host integration, VM/network tooling and workflow friction rather than one platform being universally better."
    )
    assert not find_pairwise_comparison_drift_violations(
        comparison_good,
        comparison_contract,
    )
    assert not find_explicit_user_constraint_violations(
        comparison_user,
        comparison_good,
    )

    # 12:32 cyber recommendation: a stable skill recommendation must not smuggle
    # in unsupported claims that automation will fail or cannot model something.
    recommendation_contract = AnswerContractRuntime(
        intent="recommendation_request",
        epistemic_mode="conversation",
        verified_evidence_claims=(),
    )
    recommendation_bad = (
        "Practice systems thinking. It helps you spot where automation will fail because machines don't model second-order effects well."
    )
    violations = find_recommendation_forecast_violations(
        recommendation_bad,
        recommendation_contract,
    )
    assert any("unsupported future" in item for item in violations), violations
    assert not find_recommendation_forecast_violations(
        "Practice TCP/IP packet analysis: it builds concrete networking and troubleshooting skill that transfers across many security tasks.",
        recommendation_contract,
    )

    # Never surface raw model <think> markup. If a dangling closing tag divides
    # reasoning-looking prefix from the final answer, keep the post-tag answer.
    leaked = (
        "reasoning-looking text that should not surface </think>\n\n"
        "Practice TCP/IP packet analysis because it builds concrete troubleshooting skill."
    )
    cleaned = _strip_internal_reasoning_markup(leaked)
    assert "</think>" not in cleaned.lower(), cleaned
    assert "reasoning-looking" not in cleaned.lower(), cleaned
    assert cleaned.startswith("Practice TCP/IP"), cleaned
    paired = _strip_internal_reasoning_markup(
        "<think>private reasoning</think>Public answer."
    )
    assert paired == "Public answer.", paired

    # 12:32 scaler two-sentence summary: fitting on all data cannot then be
    # described as training-only scaling, a scaler does not memorize the held-
    # out distribution, and optimistic performance is a risk rather than a law.
    leakage_history = [
        {"role": "user", "content": "bro can u explain data leakage in machine learning like i actually need to understand it"},
        {"role": "user", "content": "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"},
    ]
    scaler_user = "wait explain the whole thing in like 2 sentences, my brain is cooked"
    scaler_bad = (
        "Fitting a scaler on the full dataset (train + test) lets it memorise the test data's distribution, "
        "so when you split and scale only with the training stats, your model has already seen the correct scaling for the test set during fitting—that’s leakage. "
        "It’s like studying the exam answers before the test; your performance looks great but is fake."
    )
    violations = find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_bad,
        leakage_history,
    )
    assert any("memorising" in item for item in violations), violations
    assert any("training-only" in item for item in violations), violations
    assert any("guaranteed" in item for item in violations), violations

    scaler_good = (
        "If you fit the scaler before the split, the held-out test values influence the mean/scale used to preprocess training data, so the evaluation is no longer fully independent. "
        "Fit on training only and apply those training-derived parameters to test data; leakage can make the evaluation too optimistic, but it does not guarantee a particular score change."
    )
    assert not find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_good,
        leakage_history,
    )

    # 12:32 missing-airline case: do not invent a gate outcome before carrier
    # policy and dimensions are known.
    airline_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="insufficient_user_context",
    )
    airline_bad = (
        "Since you haven't given me the airline or dimensions, I can't tell you if it'll get tossed at the gate."
    )
    violations = find_insufficient_context_overreach_violations(
        airline_bad,
        airline_contract,
    )
    assert any("airline/airport consequences" in item for item in violations), violations
    assert not find_insufficient_context_overreach_violations(
        "You haven't given me the airline, its carry-on limits, or the bag dimensions, so I can't say whether it is allowed yet.",
        airline_contract,
    )

    print(
        "PASS: B17 stop-condition integrity for VRR, pairwise constraints, AI forecast hygiene, think-tag sanitation, scaler semantics and airline uncertainty"
    )


if __name__ == "__main__":
    run()
