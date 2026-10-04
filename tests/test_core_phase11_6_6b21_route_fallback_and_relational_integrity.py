from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_verification_declined_fallback,
    find_scaler_leakage_contradiction_violations,
    find_session_cookie_security_violations,
    find_user_diagnostic_overclaim_violations,
)


def run():
    # 16:16 critical failure: verification_declined already has a deterministic
    # truthful answer. Repeated empty Qwen responses must never replace it with
    # the generic provider-internal "no usable answer" message.
    fallback = build_verification_declined_fallback()
    low = fallback.lower()
    assert "can't" in low or "cannot" in low
    assert "browse" in low or "verif" in low
    assert "won't guess" in low or "will not guess" in low

    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    branch = 'core_epistemic_mode == "verification_declined"'
    assert branch in provider_source
    assert "deterministic no-browse fallback without model/tool generation" in provider_source
    assert provider_source.index("deterministic no-browse fallback without model/tool generation") < provider_source.index(
        "self_correction_context = ("
    )

    # 16:16 hidden PASS: gerund/inflected forms must not bypass stolen-session
    # semantics. Local logout/cookie deletion/password changes are not generic
    # synonyms for server-side revocation of an attacker's copied token.
    session_user = (
        "bro if someone nicks an already-logged-in session cookie, will switching on MFA magically stop them using it?"
    )
    session_bad = (
        "No. Switching on MFA after the fact won't retroactively invalidate a stolen session cookie. "
        "The attacker can still use that existing cookie until it expires or you manually revoke it. "
        "MFA protects new logins, not active sessions. You need to kick them out by logging out and clearing cookies "
        "or changing your password immediately."
    )
    violations = find_session_cookie_security_violations(session_user, session_bad)
    assert any("local cookie deletion" in v for v in violations), violations
    assert any("password" in v or "unspecified logout" in v for v in violations), violations

    session_good = (
        "No. MFA protects the login flow, but a copied valid session can remain usable until it expires or the service "
        "revokes that session server-side. Clearing your local cookies does not revoke the attacker's copied session; use a server-side "
        "revoke-all-sessions/logout-all-devices control if the service provides one."
    )
    assert not find_session_cookie_security_violations(session_user, session_good)

    # 16:16 hidden PASS: preserve measurement relations instead of manufacturing
    # an upstairs node/floor plan or moving the wired console next to the router.
    wifi_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    wifi_history = [
        {
            "role": "user",
            "content": (
                "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
                "bruh don't tell me to buy a new router straight away, what would you test first?"
            ),
        }
    ]
    wifi_user = (
        "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. so what does that rule out?"
    )
    wifi_bad = (
        "Okay, so the wired console gets 600 Mbps right next to the router, but your phone upstairs still chokes at "
        "20 Mbps even when it's close to the main mesh node. That rules out a bad cable or port on the console itself. "
        "The signal is getting degraded as it travels through your house—probably due to walls, floors, or interference. "
        "It could also be that the mesh node upstairs isn't communicating well with the main node."
    )
    violations = find_user_diagnostic_overclaim_violations(
        wifi_user,
        wifi_bad,
        wifi_contract,
        wifi_history,
    )
    assert any("physical location" in v for v in violations), violations
    assert any("upstairs mesh-node" in v for v in violations), violations
    assert any("distinct near-node and upstairs measurements" in v for v in violations), violations
    assert any("physical" in v or "layout" in v for v in violations), violations

    wifi_good = (
        "The same phone being fast next to the main node but slow upstairs makes a broadband-wide cap and a phone-wide "
        "speed limit much less likely. It still leaves the local upstairs Wi-Fi/mesh path unresolved, including signal, "
        "roaming/association, interference or backhaul, so those need separate measurements."
    )
    assert not find_user_diagnostic_overclaim_violations(
        wifi_user,
        wifi_good,
        wifi_contract,
        wifi_history,
    )

    # General data-leakage teaching should not promise that deployment
    # performance necessarily tanks; leakage invalidates evaluation and may
    # cause optimistic estimates, but the exact downstream effect is contingent.
    leakage_user = (
        "bro can u explain data leakage in machine learning like i actually need to understand it, not just paste a definition"
    )
    leakage_bad = (
        "Data leakage means information unavailable at prediction time gets into training. "
        "When you deploy it, performance tanks because that cheat sheet isn't available anymore."
    )
    violations = find_scaler_leakage_contradiction_violations(
        leakage_user,
        leakage_bad,
        [],
    )
    assert any("downstream performance collapse" in v for v in violations), violations

    leakage_good = (
        "Data leakage means held-out test or validation information that should be unavailable to training leaks into model building. "
        "That invalidates the evaluation and can make measured performance too optimistic; deployment performance may then be worse."
    )
    assert not find_scaler_leakage_contradiction_violations(
        leakage_user,
        leakage_good,
        [],
    )

    print(
        "PASS: B21 deterministic no-browse routing, stolen-session inflections, relational diagnostics and leakage calibration"
    )


if __name__ == "__main__":
    run()
