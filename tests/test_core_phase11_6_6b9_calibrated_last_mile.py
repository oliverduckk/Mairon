"""Phase 11.6.6B9: calibrated useful-answer preservation at the provider boundary.

Deterministic only: no live Ollama, public network, private tools, or write actions.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai.ollama_provider import find_core_answer_contract_violations
from core.answer_contract import build_answer_contract
from core.claim_grounding import (
    build_debate_continuation_fallback,
    build_diagnostic_reasoning_fallback,
    find_explicit_user_constraint_violations,
    find_source_provenance_honesty_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.conversation_state import ConversationState
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn
from research.public_factual_grounding import build_public_factual_retry_instruction


def run() -> None:
    # Wi-Fi: once Oliver supplies a same-phone near-main-node result, Core can
    # make calibrated deductions without pretending it measured the backhaul.
    wifi_first_text = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_follow_text = (
        "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. "
        "so what does that rule out?"
    )
    first_fallback = build_diagnostic_reasoning_fallback(wifi_first_text, [])
    assert first_fallback and "same phone" in first_fallback.lower(), first_fallback
    assert "wi-fi/mesh" in first_fallback.lower(), first_fallback

    wifi_history = [
        {"role": "user", "content": wifi_first_text},
        {"role": "assistant", "content": "test response"},
    ]
    follow_fallback = build_diagnostic_reasoning_fallback(
        wifi_follow_text,
        wifi_history,
    )
    assert follow_fallback, follow_fallback
    assert "does not rule out" in follow_fallback.lower(), follow_fallback
    assert "backhaul" in follow_fallback.lower(), follow_fallback

    wifi_state = ConversationState()
    wifi_first = classify_turn(wifi_first_text, wifi_state)
    wifi_state.remember_user_turn(wifi_first)
    wifi_follow = wifi_state.resolve_follow_up(classify_turn(wifi_follow_text, wifi_state))
    wifi_contract = build_answer_contract(wifi_follow, route_epistemic_authority(wifi_follow))
    bad_wifi = (
        "That observation rules out a simple backhaul bottleneck between the nodes. "
        "It just means the signal is getting lost somewhere in the air between the node and upstairs."
    )
    wifi_bad = find_user_diagnostic_overclaim_violations(
        wifi_follow_text,
        bad_wifi,
        wifi_contract,
        wifi_history,
    )
    assert any("backhaul" in item.lower() for item in wifi_bad), wifi_bad

    # VRR: dark-scene-only flicker is compatible with VRR, but neither VRR nor
    # a defect/non-defect conclusion is proven by correlation alone.
    vrr_first_text = "anyway why does my screen flicker when variable refresh rate is on?"
    vrr_follow_text = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    vrr_history = [{"role": "user", "content": vrr_first_text}]
    vrr_fallback = build_diagnostic_reasoning_fallback(vrr_follow_text, vrr_history)
    assert vrr_fallback and "could still be vrr" in vrr_fallback.lower(), vrr_fallback
    assert "does not prove" in vrr_fallback.lower(), vrr_fallback

    vrr_state = ConversationState()
    vrr_first = classify_turn(vrr_first_text, vrr_state)
    vrr_state.remember_user_turn(vrr_first)
    vrr_turn = vrr_state.resolve_follow_up(classify_turn(vrr_follow_text, vrr_state))
    vrr_contract = build_answer_contract(vrr_turn, route_epistemic_authority(vrr_turn))
    vrr_bad = find_user_diagnostic_overclaim_violations(
        vrr_follow_text,
        "VRR is the cause and it's not a defect.",
        vrr_contract,
        vrr_history,
    )
    assert vrr_bad, vrr_bad

    # Explicit negative constraints must survive narrowing a comparison. Generic
    # cost trade-offs remain possible; personalised budget/ownership guesses do not.
    compare_user = (
        "okay narrow it to Python, Linux VMs and messing around with networks. "
        "don't invent my budget or which one i already own"
    )
    bad_compare = (
        "Windows wins if you're on a budget, and it depends whether you value saving money more."
    )
    assert find_explicit_user_constraint_violations(compare_user, bad_compare)
    good_compare = (
        "macOS gives you Unix-native CLI tooling; Windows gives you native Windows tooling plus WSL2 and VMs. "
        "Cost can vary by hardware, so I won't infer your budget or current device."
    )
    assert not find_explicit_user_constraint_violations(compare_user, good_compare)

    compare_state = ConversationState()
    compare_first = classify_turn(
        "mac vs windows for dev... actually don't tell me one is 'better' overall. gimme the real trade-offs",
        compare_state,
    )
    compare_state.remember_user_turn(compare_first)
    compare_turn = compare_state.resolve_follow_up(classify_turn(compare_user, compare_state))
    compare_contract = build_answer_contract(compare_turn, route_epistemic_authority(compare_turn))
    rendered = compare_contract.to_model_instruction().lower()
    assert "not to infer his budget" in rendered, rendered

    # Debate continuation must be enforced even when structured metadata is lost
    # and only the rendered legacy contract reaches the provider boundary.
    counter_user = "nah give me an actual counterargument too, otherwise you're just agreeing with me lol"
    counter_turn = classify_turn(counter_user)
    counter_contract = build_answer_contract(counter_turn, route_epistemic_authority(counter_turn))
    counter_violations = find_core_answer_contract_violations(
        "Got it.",
        counter_contract.to_model_instruction(),
        user_input=counter_user,
    )
    assert any("counterargument" in item.lower() for item in counter_violations), counter_violations
    counter_fallback = build_debate_continuation_fallback(
        counter_user,
        [{
            "role": "user",
            "content": "why do some long manga arcs hit harder than short ones? talk about pacing, setup and payoff but no specific spoilers",
        }],
    )
    assert "shorter arcs" in counter_fallback.lower(), counter_fallback
    assert "pacing" in counter_fallback.lower(), counter_fallback

    # Provenance follow-ups cannot evade the user's exact honesty request.
    provenance_user = "which official link is that from? and if you didn't actually load it, SAY THAT"
    evasive = "I didn't need to load it in any special way; that's just where the truth lives."
    assert find_source_provenance_honesty_violations(provenance_user, evasive)
    assert not find_source_provenance_honesty_violations(
        provenance_user,
        "I retrieved the official Python docs source for this turn; the URL is https://docs.python.org/3/library/venv.html.",
    )

    # Public factual retry must treat task relevance as a repair-worthy failure,
    # not only unsupported evidence claims.
    public_retry = build_public_factual_retry_instruction([
        "AI/cyber labour answer discussed adjacent market/infrastructure claims without addressing jobs or role replacement"
    ])
    assert public_retry and "ai/cyber labour answer" in public_retry.lower(), public_retry

    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    assert "build_diagnostic_reasoning_fallback" in provider_source
    assert "build_debate_continuation_fallback" in provider_source
    assert "find_explicit_user_constraint_violations" in provider_source
    assert "find_source_provenance_honesty_violations" in provider_source
    assert "salvage_violations.extend" in provider_source
    assert "find_ai_job_market_answer_violations" in provider_source

    print(
        "PASS: B9 calibrated Wi-Fi/VRR fallbacks, explicit no-assumption constraints, "
        "legacy debate enforcement, source-provenance honesty and research-salvage relevance"
    )


if __name__ == "__main__":
    run()
