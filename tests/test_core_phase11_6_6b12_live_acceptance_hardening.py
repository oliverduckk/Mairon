from pathlib import Path
import ast
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_diagnostic_reasoning_fallback,
    find_explicit_user_constraint_violations,
    find_scaler_leakage_contradiction_violations,
    find_session_cookie_security_violations,
    find_source_provenance_honesty_violations,
    find_user_diagnostic_overclaim_violations,
)


def _load_micro_act_guard():
    provider_path = SRC / "ai" / "ollama_provider.py"
    source = provider_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "find_core_micro_act_relevance_violations"
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "re": re,
        "_core_contract_value": lambda contract, field: contract.get(field),
    }
    exec(compile(module, str(provider_path), "exec"), namespace)
    return namespace["find_core_micro_act_relevance_violations"]


def run():
    # 22:50 holdout critical: a real "thoughts?" request cannot collapse into
    # a bare acknowledgement just because spoiler/grounding validation is active.
    micro_guard = _load_micro_act_guard()
    opinion_user = (
        "lowkey i think the best part of Vinland Saga is the character writing, "
        "not the fights. thoughts? no spoilers past season 1"
    )
    assert micro_guard("Got it.", opinion_user, {"Intent": "share_opinion"})
    assert not micro_guard(
        "I agree that the character writing can be the stronger part because the fights work as pressure on values and choices, not just spectacle.",
        opinion_user,
        {"Intent": "share_opinion"},
    )

    # Exact new scaler paraphrase: "full dataset" must activate the guard, and
    # a split hidden inside a comment is broken even if later code only calls
    # scaler.transform(X_train/X_test) rather than model.fit(X_train).
    scaler_user = (
        "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"
    )
    scaler_history = [{
        "role": "user",
        "content": "bro can u explain data leakage in machine learning like i actually need to understand it, not just paste a definition",
    }]
    scaler_bad = '''Fitting a scaler on the full dataset before splitting leaks information.
```python
scaler = StandardScaler()
scaler.fit(X)  # Learns from both train AND test data! X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
X_train_scaled = scaler.transform(X_train)
X_test_scaled = scaler.transform(X_test)
```
Otherwise, your evaluation score is artificially inflated by cheating.'''
    scaler_violations = find_scaler_leakage_contradiction_violations(
        scaler_user, scaler_bad, scaler_history
    )
    assert any("commented out" in item for item in scaler_violations), scaler_violations
    assert any("guaranteed" in item for item in scaler_violations), scaler_violations

    # Exact provenance evasion with quotes around "load" must still be rejected.
    provenance_user = "which official link is that from? and if you didn't actually load it, SAY THAT"
    provenance_bad = (
        "The answer comes straight from the official Python docs. "
        "I didn't need to \"load\" anything; it's just reading what's publicly documented."
    )
    assert find_source_provenance_honesty_violations(provenance_user, provenance_bad)
    assert not find_source_provenance_honesty_violations(
        provenance_user,
        "I did retrieve and read the official Python venv documentation for this turn.",
    )

    # The near-node/upstairs measurements remain compatible with a range/coverage
    # problem; they cannot rule it out merely because the phone is fast near the main node.
    wifi_history = [
        {
            "role": "user",
            "content": "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. what would you test first?",
        },
        {
            "role": "user",
            "content": "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. so what does that rule out?",
        },
    ]
    wifi_user = "soooooo i should pay my isp more? LMAO"
    wifi_bad = (
        "No. That test rules out a simple wireless range issue as the sole culprit. "
        "The bottleneck could still be backhaul or interference."
    )
    wifi_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    assert find_user_diagnostic_overclaim_violations(
        wifi_user, wifi_bad, wifi_contract, wifi_history
    )
    wifi_fallback = build_diagnostic_reasoning_fallback(wifi_user, wifi_history)
    assert wifi_fallback
    assert "local wi-fi/mesh path" in wifi_fallback.lower()
    assert "do not identify" in wifi_fallback.lower()

    # Generic stolen-session guidance cannot promise that changing a password
    # kills an already copied session unless the service is known to invalidate sessions.
    session_user = (
        "bro if someone nicks an already-logged-in session cookie, will switching on MFA magically stop them using it?"
    )
    session_bad = (
        "No. Once they're in, they're in until you invalidate that session or change the password."
    )
    assert find_session_cookie_security_violations(session_user, session_bad)
    assert not find_session_cookie_security_violations(
        session_user,
        "No. The stolen session remains usable until it expires or is revoked server-side; a password change only helps if that service also invalidates existing sessions.",
    )

    # Dark-scene correlation does not justify invented mid-frame/low-brightness
    # panel timing mechanisms.
    vrr_history = [{
        "role": "user",
        "content": "anyway why does my screen flicker when variable refresh rate is on?",
    }]
    vrr_user = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    vrr_bad = (
        "Yes. VRR changes the panel's frame timing mid-frame or during low-brightness intervals, "
        "which can cause visible strobing."
    )
    vrr_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    assert find_user_diagnostic_overclaim_violations(
        vrr_user, vrr_bad, vrr_contract, vrr_history
    )

    # Explicit medium separation should not become fresh anime speculation.
    medium_user = "and when i say i read it i mean the manga, not the anime. keep the two separate pls"
    medium_bad = (
        "Understood. Let's see if the anime ever catches up before I expect a sequel from Denji's future self."
    )
    assert find_explicit_user_constraint_violations(medium_user, medium_bad)
    assert not find_explicit_user_constraint_violations(
        medium_user,
        "Understood. I'll keep manga discussion separate and won't pull anime material into it.",
    )

    print(
        "PASS: B12 substantive opinion requests, robust scaler/provenance validation, "
        "calibrated Wi-Fi/VRR/session semantics and explicit medium separation"
    )


if __name__ == "__main__":
    run()
