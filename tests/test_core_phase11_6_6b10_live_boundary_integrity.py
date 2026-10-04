from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract import build_answer_contract
from core.answer_contract_runtime import coerce_answer_contract_runtime
from core.claim_grounding import (
    find_pairwise_comparison_drift_violations,
    find_recommendation_forecast_violations,
    find_recommendation_topic_drift_violations,
    find_session_cookie_security_violations,
    find_source_provenance_honesty_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.conversation_state import ConversationState
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn


def run():
    # Live router/provider transport is still rendered text. Preserve the
    # structured pairwise frame when reconstructing runtime state from it.
    state = ConversationState()
    first = classify_turn(
        "mac vs windows for dev... actually don't tell me one is 'better' overall. gimme the real trade-offs",
        state,
    )
    state.remember_user_turn(first)
    follow = classify_turn(
        "okay narrow it to Python, Linux VMs and messing around with networks. don't invent my budget or which one i already own",
        state,
    )
    follow = state.resolve_follow_up(follow)
    contract = build_answer_contract(follow, route_epistemic_authority(follow))
    rendered = contract.to_model_instruction()
    runtime = coerce_answer_contract_runtime(rendered)
    assert runtime is not None
    assert runtime.metadata.get("comparison_frame") == "mac vs windows", runtime.metadata
    assert runtime.forbidden_behaviours

    live_bad_compare = (
        "For Python specifically, Linux VMs are the clear winner here for network messing around. "
        "Windows can do this via WSL2, but if you're mostly doing Python, networking, and Linux-based workloads, "
        "sticking with Linux on both ends saves you from that extra layer of abstraction."
    )
    compare_bad = find_pairwise_comparison_drift_violations(live_bad_compare, rendered)
    assert compare_bad, compare_bad

    # A copied attacker cookie is not revoked by clearing the victim browser's
    # local cookie. Catch the exact live wording that B9 allowed through.
    cookie_user = "bro if someone nicks an already-logged-in session cookie, will switching on MFA magically stop them using it?"
    cookie_bad = (
        "No, switching on MFA won't retroactively invalidate a stolen session cookie. "
        "The existing stolen session remains active unless you clear cookies or force a logout."
    )
    assert find_session_cookie_security_violations(cookie_user, cookie_bad)
    cookie_good = (
        "No. MFA protects future login attempts, but a copied valid session can still be replayed until it expires "
        "or the server invalidates it. Clearing your own browser cookie does not revoke the attacker's copy."
    )
    assert not find_session_cookie_security_violations(cookie_user, cookie_good)

    # Recommendation rationale must not smuggle in unverified automation
    # forecasts such as 'humans hold leverage' or 'AI won't replicate it'.
    rec_turn = classify_turn("give me one concrete skill worth practising regardless")
    rec_contract = build_answer_contract(rec_turn, route_epistemic_authority(rec_turn))
    forecast_bad = (
        "Architectural reasoning is where humans hold leverage even as automation scales. "
        "That practice trains intuition in ways AI won't replicate."
    )
    assert find_recommendation_forecast_violations(forecast_bad, rec_contract)

    # 'I have uni shit to do too' is a time/verbosity constraint on the rejection
    # follow-up, not permission to invent an urgent assignment and change topic.
    rejection_history = [{
        "role": "user",
        "content": "bruh ANOTHER generic grad rejection email. i just wanna complain for a sec, please don't give me another 9-step career plan 😭",
    }]
    next_step_user = "okay, one actual useful next step. ONE. i have uni shit to do too"
    next_step_bad = (
        "Submit your most urgent assignment tonight before you lose it. Prioritise that single uni task."
    )
    assert find_recommendation_topic_drift_violations(next_step_user, next_step_bad, rejection_history)
    next_step_good = (
        "Take the next role you actually want and spend 10 minutes tailoring that application, then get back to uni."
    )
    assert not find_recommendation_topic_drift_violations(next_step_user, next_step_good, rejection_history)

    # Provenance follow-ups must explicitly say whether a source was actually
    # retrieved/read; naming a URL and saying it 'comes straight from' is evasive.
    provenance_user = "which official link is that from? and if you didn't actually load it, SAY THAT"
    provenance_bad = (
        "The answer comes straight from the official Python docs: https://docs.python.org/3/library/venv.html. "
        "The docs are pretty clear."
    )
    assert find_source_provenance_honesty_violations(provenance_user, provenance_bad)
    provenance_good = (
        "I retrieved and read the official Python docs for this turn. "
        "The URL I actually loaded is https://docs.python.org/3/library/venv.html."
    )
    assert not find_source_provenance_honesty_violations(provenance_user, provenance_good)

    # VRR: correlation can make VRR plausible, but 'it flickers because...' and
    # invented dimming/backlight mechanisms are stronger than the measurements.
    vrr_history = [{"role": "user", "content": "anyway why does my screen flicker when variable refresh rate is on?"}]
    vrr_user = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    vrr_state = ConversationState()
    vrr_first = classify_turn(vrr_history[0]["content"], vrr_state)
    vrr_state.remember_user_turn(vrr_first)
    vrr_turn = vrr_state.resolve_follow_up(classify_turn(vrr_user, vrr_state))
    vrr_contract = build_answer_contract(vrr_turn, route_epistemic_authority(vrr_turn))

    assert find_user_diagnostic_overclaim_violations(
        vrr_user,
        "It flickers because your frame rate is unstable, forcing the monitor to jump refresh rates rapidly.",
        vrr_contract,
        vrr_history,
    )
    assert find_user_diagnostic_overclaim_violations(
        vrr_user,
        "Aggressive brightness/dimming adjustments can cause the backlight or pixel response to stutter, creating that flicker.",
        vrr_contract,
        vrr_history,
    )
    safe_vrr = (
        "Yes, it could still be VRR; dark scenes can make VRR-related luminance instability easier to notice. "
        "That pattern supports VRR as a possibility, but it does not prove VRR is the root cause."
    )
    assert not find_user_diagnostic_overclaim_violations(
        vrr_user, safe_vrr, vrr_contract, vrr_history
    )

    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    assert "find_recommendation_topic_drift_violations" in provider_source
    assert "actual retrieved-source URL fallback" in provider_source

    print(
        "PASS: B10 legacy-contract metadata, session-cookie semantics, recommendation continuity/forecast, "
        "source provenance honesty and calibrated VRR boundaries"
    )


if __name__ == "__main__":
    run()
