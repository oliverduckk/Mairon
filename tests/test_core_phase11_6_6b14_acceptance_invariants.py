from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_explicit_user_constraint_violations,
    find_scaler_leakage_contradiction_violations,
    find_session_cookie_security_violations,
    find_user_diagnostic_overclaim_violations,
)


def run():
    # Exact 23:55 stolen-session wording: local cookie clearing must not be
    # presented as part of invalidating the attacker's already-copied session.
    session_user = (
        "bro if someone nicks an already-logged-in session cookie, will switching on MFA magically stop them using it?"
    )
    session_bad = (
        "No, switching on MFA won't stop them from using a stolen cookie. The attacker already has the session token; "
        "they're logged in before MFA even kicks in. MFA protects you from new logins, not active sessions. "
        "If someone steals your cookie, you need to invalidate it—logout everywhere, clear cookies, maybe rotate tokens."
    )
    violations = find_session_cookie_security_violations(session_user, session_bad)
    assert any("local cookie deletion" in item for item in violations), violations
    assert not find_session_cookie_security_violations(
        session_user,
        (
            "No. MFA mainly protects new logins. Clearing the cookie in your own browser does not revoke the attacker's "
            "copied session; use server-side session revocation/invalidation and let short expiries limit the remaining window."
        ),
    )

    # Exact 23:55 short scaler answer: preprocessing leakage can bias evaluation,
    # but optimistic/inflated performance is not guaranteed on every dataset.
    scaler_user = "wait explain the whole thing in like 2 sentences, my brain is cooked"
    scaler_history = [{
        "role": "user",
        "content": "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example",
    }]
    scaler_bad = (
        "Fitting a scaler before the split leaks information because the scaler learns its parameters (like mean and std) "
        "from the entire dataset, including the test set, which it shouldn't see yet. When you then apply that scaler to "
        "your test data, you're effectively using knowledge about the test distribution to transform it, which inflates "
        "your model's performance metrics on that test set."
    )
    violations = find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_bad,
        scaler_history,
    )
    assert any("guaranteed" in item or "possible bias" in item for item in violations), violations
    assert not find_scaler_leakage_contradiction_violations(
        scaler_user,
        (
            "Fitting before the split lets test-set statistics influence the scaler parameters used on the training data. "
            "That compromises an independent evaluation and can make the measured test performance too optimistic, so fit "
            "on training data only and then transform the held-out test set."
        ),
        scaler_history,
    )

    # Exact 23:55 Wi-Fi first turn: a large wired/wireless difference is useful
    # evidence, but it is not a 'classic symptom' proving interference/signal loss.
    stable_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="stable_model_knowledge",
    )
    wifi_user = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_bad_first = (
        "That's a classic symptom of wireless interference or poor signal strength, not your router being broken. "
        "First, check if your phone is connecting to the 2.4 GHz band instead of 5 GHz."
    )
    violations = find_user_diagnostic_overclaim_violations(
        wifi_user,
        wifi_bad_first,
        stable_contract,
        [],
    )
    assert any("near-certainty" in item for item in violations), violations

    # Exact 23:55 Wi-Fi final turn: near-main-node throughput does not prove an
    # unmeasured mesh/backhaul path is not the bottleneck.
    live_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    wifi_followup = "soooooo i should pay my isp more? LMAO"
    wifi_history = [
        {"role": "user", "content": wifi_user},
        {
            "role": "user",
            "content": "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. so what does that rule out?",
        },
    ]
    wifi_bad_last = (
        "No, you shouldn't pay your ISP more yet. That test just proves the bottleneck isn't the backhaul from your router "
        "to the wall; it's something specific to that upstairs location or the device itself."
    )
    violations = find_user_diagnostic_overclaim_violations(
        wifi_followup,
        wifi_bad_last,
        live_contract,
        wifi_history,
    )
    assert any("backhaul" in item for item in violations), violations
    assert not find_user_diagnostic_overclaim_violations(
        wifi_followup,
        (
            "Paying the ISP more is unlikely to fix the upstairs slowdown: the same phone is fast next to the main node. "
            "That points to the local Wi-Fi/mesh path, but the readings do not identify signal, roaming, backhaul or interference as the cause."
        ),
        live_contract,
        wifi_history,
    )

    # Exact 23:55 medium-lock wording: acknowledging the manga/anime separation
    # is fine; inventing a different ending/adaptation change is not.
    manga_user = "and when i say i read it i mean the manga, not the anime. keep the two separate pls"
    manga_bad = (
        "Noted. I'll treat the panels as sacred scripture and ignore whatever animated nonsense they turned into. "
        "At least you won't be confused by a different ending or some weird adaptation choice."
    )
    violations = find_explicit_user_constraint_violations(manga_user, manga_bad)
    assert any("anime discussion" in item for item in violations), violations
    assert not find_explicit_user_constraint_violations(
        manga_user,
        "Yep — manga means manga. I'll keep anime details separate unless you explicitly ask about them.",
    )

    # Provider boundary invariant: diagnostic acceptance must run before the
    # narrower factual-focus branch so stable-model-knowledge diagnostics cannot
    # bypass the same deterministic checks used by follow-up routes.
    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    global_marker = provider_source.index(
        "# Diagnostic calibration is a direct-answer acceptance invariant"
    )
    factual_focus_marker = provider_source.index(
        "if factual_focus_fidelity_required:",
        global_marker,
    )
    global_call = provider_source.index(
        "find_user_diagnostic_overclaim_violations(",
        global_marker,
    )
    assert global_marker < global_call < factual_focus_marker

    print(
        "PASS: B14 stolen-session cookie semantics, scaler calibration, global diagnostic acceptance and manga-medium integrity"
    )


if __name__ == "__main__":
    run()
