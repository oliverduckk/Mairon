"""Phase 11.6.6B8: last-mile live semantic reliability closures.

Deterministic only: no Ollama, public network, private tools, or write actions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract import build_answer_contract
from core.claim_grounding import (
    build_core_grounding_fallback,
    build_user_context_reasoning_fallback,
    find_ai_job_market_answer_violations,
    find_insufficient_context_overreach_violations,
    find_pairwise_comparison_drift_violations,
    find_python_mutable_default_semantics_violations,
    find_scaler_leakage_contradiction_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.conversation_state import ConversationState
from core.epistemic_calibration import (
    extract_lexical_query_term,
    repair_unjustified_lexical_denial,
)
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn
from core.workflows.self_correction import build_self_correction_response
from personality.spoiler_guard import (
    build_spoiler_safe_discussion_fallback,
    find_spoiler_guard_violations,
    prepare_spoiler_context,
)


def run() -> None:
    # Natural "WAIT correction ..." language is a self-correction, and Core's
    # deterministic acknowledgement preserves the new fact immediately.
    correction = "WAIT correction the spare battery's in the BLACK cube not red. i moved it"
    correction_turn = classify_turn(correction)
    assert correction_turn.intent == "self_correction", correction_turn.intent
    correction_answer = build_self_correction_response(correction)
    assert "black" in correction_answer.lower(), correction_answer
    assert "not red" in correction_answer.lower(), correction_answer

    # A supplied numeric limit is premise reasoning, not permission to invent
    # airline/security/fee consequences.
    airline_state = ConversationState()
    first_airline = classify_turn(
        "bro if i take my hiking backpack as carry-on for a 3 week trip, am i DEFINITELY allowed? "
        "i haven't told you the airline or bag dimensions",
        airline_state,
    )
    airline_state.remember_user_turn(first_airline)
    second_airline = classify_turn(
        "okay hypothetically the airline says 7kg, bag is 9kg, am i within that limit? "
        "don't assume anything about the bag size",
        airline_state,
    )
    second_airline = airline_state.resolve_follow_up(second_airline)
    assert second_airline.intent == "reason_from_supplied_premises", second_airline.intent
    assert second_airline.entities.get("reasoning_kind") == "threshold_comparison"
    threshold = str(second_airline.entities.get("reasoning_direct_answer") or "")
    threshold_low = threshold.lower()
    assert "9 kg" in threshold_low and "7 kg" in threshold_low and "2 kg" in threshold_low, threshold
    assert "over" in threshold_low, threshold
    assert all(word not in threshold_low for word in ("fee", "security", "check it")), threshold

    # Conversationally prefixed unknown terms still receive calibrated
    # uncertainty instead of a categorical "there is no such thing" claim.
    nonce_user = (
        "quick one: what's a dravonetic handshake in computer networking? "
        "if ur not sure say so instead of inventing shit"
    )
    assert extract_lexical_query_term(nonce_user) == "dravonetic handshake"
    repaired, changed = repair_unjustified_lexical_denial(
        nonce_user,
        'There is no such thing as a "dravonetic handshake" in computer networking.',
    )
    assert changed
    assert "not familiar" in repaired.lower() or "not sure" in repaired.lower()

    # Explicit counterargument language carries a debate-continuation contract.
    counter = classify_turn(
        "nah give me an actual counterargument too, otherwise you're just agreeing with me lol"
    )
    assert counter.intent == "share_opinion", counter.intent
    assert counter.entities.get("_debate_continuation") == "true"
    counter_contract = build_answer_contract(counter, route_epistemic_authority(counter))
    assert counter_contract.metadata.get("debate_continuation") == "true"

    # The narrowed Mac-vs-Windows follow-up must still contain both requested
    # sides; Linux is a workload/VM subject here, not a third replacement OS.
    compare_state = ConversationState()
    compare_first = classify_turn(
        "mac vs windows for dev... actually don't tell me one is 'better' overall. gimme the real trade-offs",
        compare_state,
    )
    compare_state.remember_user_turn(compare_first)
    compare_follow = classify_turn(
        "okay narrow it to Python, Linux VMs and messing around with networks. "
        "don't invent my budget or which one i already own",
        compare_state,
    )
    compare_follow = compare_state.resolve_follow_up(compare_follow)
    compare_contract = build_answer_contract(compare_follow, route_epistemic_authority(compare_follow))
    live_drift = (
        "Linux is the native environment for Python tooling. Windows has improved significantly with WSL2. "
        "Linux wins on fidelity while Windows wins on convenience."
    )
    assert find_pairwise_comparison_drift_violations(live_drift, compare_contract)
    good_compare = (
        "On macOS, Python and Unix networking tools run natively, while Linux VMs still add a VM boundary. "
        "On Windows, WSL2 gives a strong Linux environment but some low-level networking crosses that extra layer."
    )
    assert not find_pairwise_comparison_drift_violations(good_compare, compare_contract)

    # Mutable defaults persist because the default object belongs to the
    # function defaults; they are not "stored in the closure".
    prior_code = [{
        "role": "user",
        "content": "python question: `def f(x=[]): x.append(7); return x` then `print(f()); print(f())` -- what prints?",
    }]
    assert find_python_mutable_default_semantics_violations(
        "WHAT why didn't python make a new list every call 😭",
        "Default arguments are evaluated once and stored in the closure, so the list persists.",
        prior_code,
    )
    assert not find_python_mutable_default_semantics_violations(
        "WHAT why didn't python make a new list every call 😭",
        "The list is evaluated once and stored with the function's default arguments, so the same object is reused.",
        prior_code,
    )
    python_fallback = build_user_context_reasoning_fallback(
        "WHAT why didn't python make a new list every call 😭",
        prior_code,
    )
    assert "not a closure" in python_fallback.lower(), python_fallback

    # A leakage explanation cannot both fit on the test set and then claim the
    # test set remained unseen / the evaluation stayed unbiased.
    leakage_prior = [{
        "role": "user",
        "content": "bro can u explain data leakage in machine learning like i actually need to understand it",
    }]
    leakage_user = "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"
    leakage_bad = (
        "The scaler is fit on the whole dataset including test data. "
        "The test set remains truly unseen during training. This ensures the estimate is realistic and not inflated."
    )
    assert find_scaler_leakage_contradiction_violations(
        leakage_user, leakage_bad, leakage_prior
    )
    leakage_good = (
        "If the scaler is fit on the whole dataset, the test values influence its mean/scale, "
        "so the held-out evaluation is no longer fully independent. Fit on training only, then transform test."
    )
    assert not find_scaler_leakage_contradiction_violations(
        leakage_user, leakage_good, leakage_prior
    )

    # Wi-Fi measurements leave the unmeasured mesh path open, and the final
    # ISP question has a useful bounded fallback rather than a generic refusal.
    wifi_first_text = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_follow_text = (
        "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. "
        "so what does that rule out?"
    )
    wifi_state = ConversationState()
    wifi_first = classify_turn(wifi_first_text, wifi_state)
    wifi_state.remember_user_turn(wifi_first)
    wifi_follow = classify_turn(wifi_follow_text, wifi_state)
    wifi_follow = wifi_state.resolve_follow_up(wifi_follow)
    wifi_contract = build_answer_contract(wifi_follow, route_epistemic_authority(wifi_follow))
    wifi_live_bad = (
        "It points toward either significant interference or a physical obstruction like thick walls. "
        "That narrows the field down to environmental factors rather than hardware death."
    )
    assert find_user_diagnostic_overclaim_violations(
        wifi_follow_text,
        wifi_live_bad,
        wifi_contract,
        [{"role": "user", "content": wifi_first_text}],
    )
    wifi_conversation = [
        {"role": "user", "content": wifi_first_text},
        {"role": "assistant", "content": "test response"},
        {"role": "user", "content": wifi_follow_text},
        {"role": "assistant", "content": "diagnostic response"},
    ]
    wifi_fallback = build_user_context_reasoning_fallback(
        "soooooo i should pay my isp more? LMAO",
        wifi_conversation,
    )
    assert "unlikely" in wifi_fallback.lower() and "wi-fi/mesh" in wifi_fallback.lower(), wifi_fallback

    # VRR does not select refresh rate from scene brightness, and Core should
    # not invent OLED/PWM when no panel technology was supplied.
    vrr_state = ConversationState()
    vrr_first_text = "anyway why does my screen flicker when variable refresh rate is on?"
    vrr_first = classify_turn(vrr_first_text, vrr_state)
    vrr_state.remember_user_turn(vrr_first)
    vrr_user = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    vrr_turn = classify_turn(vrr_user, vrr_state)
    vrr_turn = vrr_state.resolve_follow_up(vrr_turn)
    vrr_contract = build_answer_contract(vrr_turn, route_epistemic_authority(vrr_turn))
    vrr_bad = (
        "The display can drop frames or change its refresh rate dynamically based on content brightness and motion. "
        "Some panels like OLEDs may flicker due to PWM dimming triggered by luminance thresholds."
    )
    vrr_violations = find_user_diagnostic_overclaim_violations(
        vrr_user,
        vrr_bad,
        vrr_contract,
        [{"role": "user", "content": vrr_first_text}],
    )
    assert len(vrr_violations) >= 2, vrr_violations

    # Missing-input answers should not fill the missing airline policy with a
    # generic "most carriers..." claim.
    missing_airline = classify_turn(
        "bro if i take my hiking backpack as carry-on, am i DEFINITELY allowed? "
        "i haven't told you the airline or bag dimensions"
    )
    missing_contract = build_answer_contract(
        missing_airline, route_epistemic_authority(missing_airline)
    )
    assert find_insufficient_context_overreach_violations(
        "Most carriers have strict limits and hiking backpacks are often too bulky.",
        missing_contract,
    )

    # Public AI-job research must actually address job/role replacement rather
    # than drifting into adjacent market-size / CPU infrastructure commentary.
    ai_user = "bro everyone's saying AI is gonna replace every cyber job by next year. how much of that is actual evidence vs people yapping?"
    ai_bad = (
        "A vendor CEO says AI is doubling the cybersecurity market size. "
        "The importance of CPUs is rising rapidly alongside GPUs."
    )
    assert find_ai_job_market_answer_violations(ai_user, ai_bad)
    ai_good = (
        "There is no evidence here that every cybersecurity job will be replaced next year. "
        "Evidence about task automation or hiring trends is narrower than that universal claim."
    )
    assert not find_ai_job_market_answer_violations(ai_user, ai_good)

    # Hard spoiler ceilings still allow a useful craft-level fallback and reject
    # vague future-direction wording such as "later shifts".
    spoiler_user = (
        "lowkey i think the best part of Vinland Saga is the character writing, "
        "not the fights. thoughts? no spoilers past season 1"
    )
    spoiler_ctx = prepare_spoiler_context(spoiler_user, [])
    spoiler_fallback = build_spoiler_safe_discussion_fallback(spoiler_user, spoiler_ctx)
    assert spoiler_fallback and "spoiler limit" in spoiler_fallback.lower()
    assert "einar" not in spoiler_fallback.lower() and "later" not in spoiler_fallback.lower()
    assert find_spoiler_guard_violations(
        "The early arcs establish the values, while later shifts force characters to confront them.",
        spoiler_ctx,
    )

    # The holdout's no-follow-up flag ignores rhetorical tag questions while
    # still catching real new questions.
    runner_path = ROOT / "benchmarks" / "run_phase11_6_brain_acceptance.py"
    spec = importlib.util.spec_from_file_location("b8_runner", runner_path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert not runner._contains_actual_follow_up_question(
        "You really did that to yourself, didn't you? Fifteen minutes of pain."
    )
    assert runner._contains_actual_follow_up_question(
        "Fair enough. Which arc stood out to you?"
    )

    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    assert "contract_debate_continuation" in provider_source
    assert "find_python_mutable_default_semantics_violations" in provider_source
    assert "find_scaler_leakage_contradiction_violations" in provider_source
    assert "find_ai_job_market_answer_violations" in provider_source
    assert "build_spoiler_safe_discussion_fallback" in provider_source

    print(
        "PASS: B8 correction echo, bounded threshold math, lexical calibration, debate continuation, "
        "comparison continuity, Python/scaler correctness, diagnostic fallbacks, AI-job relevance, "
        "spoiler-safe usefulness and rhetorical-question benchmark calibration"
    )


if __name__ == "__main__":
    run()
