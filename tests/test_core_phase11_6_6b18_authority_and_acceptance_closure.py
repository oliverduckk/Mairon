from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.epistemic_router import classify_factual_authority
from core.claim_grounding import (
    find_explicit_user_constraint_violations,
    find_scaler_leakage_contradiction_violations,
    find_user_diagnostic_overclaim_violations,
)


def run():
    # 14:29 critical failure: a durable technical premise check is not a live
    # web fact merely because Oliver says "can u check me".
    tcp_udp = (
        "my mate swears TCP is connectionless and UDP needs a handshake. "
        "that sounds cooked but can u check me"
    )
    assert classify_factual_authority(tcp_udp) == "stable_model_knowledge"
    assert classify_factual_authority(
        "can u check the web for the latest Python release"
    ) == "public_source_verified"
    # 14:29 scaler answers: leakage does not guarantee inflated metrics,
    # overfitting, memorisation, or instant production collapse. A requested
    # code example must actually instantiate train/test separation.
    history = [
        {"role": "user", "content": "bro can u explain data leakage in machine learning like i actually need to understand it"},
    ]
    first_bad = (
        "Data leakage is basically you cheating on the test before the exam starts. "
        "When this happens, your model looks incredibly accurate during training and validation because it's just memorizing the answers instead of learning patterns. "
        "But as soon as you deploy it on real, unseen data, performance tanks instantly."
    )
    violations = find_scaler_leakage_contradiction_violations(
        history[0]["content"], first_bad, []
    )
    assert any("guaranteed memorization" in v for v in violations), violations

    scaler_user = "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"
    scaler_bad = '''Fitting the scaler before the train/test split leaks information from the test set into the training process, which inflates your model's performance metrics and leads to overfitting.

```python
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import numpy as np
X = np.array([[1], [2], [3], [4], [5]])
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
```'''
    violations = find_scaler_leakage_contradiction_violations(
        scaler_user, scaler_bad, history
    )
    assert any("optimistic/inflated" in v for v in violations), violations
    assert any("overfitting" in v for v in violations), violations
    assert any("never instantiated" in v for v in violations), violations

    scaler_good = (
        "Tiny example: suppose the training values are 0 and 10 and the held-out test value is 100. "
        "If you fit the scaler on all three, the test value influences the mean/scale used for training; fit on training only, then apply those learned parameters to test. "
        "That can make evaluation too optimistic, but it does not guarantee a particular score change."
    )
    assert not find_scaler_leakage_contradiction_violations(
        scaler_user, scaler_good, history
    )

    # Explicit manga/anime separation means no back-door comparison to "the
    # show's pacing" after acknowledging the constraint.
    medium_user = "and when i say i read it i mean the manga, not the anime. keep the two separate pls"
    medium_bad = (
        "Noted, I'll keep the anime out of this mess. The manga's art style really does hit different compared to the show's pacing."
    )
    violations = find_explicit_user_constraint_violations(medium_user, medium_bad)
    assert any("locked the conversation to manga" in v for v in violations), violations
    assert not find_explicit_user_constraint_violations(
        medium_user,
        "Yep — manga only. I'll keep the anime separate unless you explicitly bring it up.",
    )

    # Wi-Fi: do not contradict an already-fast wired endpoint, or invent a
    # tower/upstairs AP/between-floor topology that Oliver never supplied.
    diag_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="stable_model_knowledge",
    )
    wifi_user = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_bad = (
        "First test the phone next to the router, then upstairs. If both are slow, it's likely your ISP or plan."
    )
    violations = find_user_diagnostic_overclaim_violations(
        wifi_user, wifi_bad, diag_contract, []
    )
    assert any("known fast wired result" in v for v in violations), violations

    follow_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    wifi_history = [
        {"role": "user", "content": wifi_user},
        {"role": "user", "content": "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. so what does that rule out?"},
    ]
    wifi_follow_user = "soooooo i should pay my isp more? LMAO"
    wifi_follow_bad = (
        "No. The readings rule out a bad signal from the tower. Either the mesh backhaul between floors is weak, "
        "there's interference inside the walls, or the access point upstairs is misconfigured."
    )
    violations = find_user_diagnostic_overclaim_violations(
        wifi_follow_user, wifi_follow_bad, follow_contract, wifi_history
    )
    assert any("network tower" in v for v in violations), violations
    assert any("access-point/topology" in v for v in violations), violations
    assert any("between-floor backhaul" in v for v in violations), violations

    wifi_good = (
        "Paying the ISP more is unlikely to fix this specific upstairs drop. The same phone can do 580 Mbps near the main node, "
        "so the remaining problem is somewhere in the local Wi-Fi/mesh path; the readings do not yet tell us whether that is signal, roaming, interference or backhaul."
    )
    assert not find_user_diagnostic_overclaim_violations(
        wifi_follow_user, wifi_good, follow_contract, wifi_history
    )

    # Dark-only flicker is compatible with VRR, not a strong diagnostic sign by itself.
    vrr_user = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    vrr_bad = (
        "It could absolutely still be VRR. The fact that it only happens in dark scenes is a strong indicator, not a contradiction."
    )
    violations = find_user_diagnostic_overclaim_violations(
        vrr_user,
        vrr_bad,
        follow_contract,
        [{"role": "user", "content": "why does my screen flicker when variable refresh rate is on?"}],
    )
    assert any("strong/definite indicator" in v for v in violations), violations
    assert not find_user_diagnostic_overclaim_violations(
        vrr_user,
        "Yes, it could still be VRR. Dark scenes can make luminance changes easier to notice, but dark-only flicker does not prove VRR is the cause; compare the same scene with VRR on and off.",
        follow_contract,
        [{"role": "user", "content": "why does my screen flicker when variable refresh rate is on?"}],
    )

    print(
        "PASS: B18 stable technical premise authority plus scaler, medium-lock, Wi-Fi and VRR acceptance invariants"
    )


if __name__ == "__main__":
    run()
