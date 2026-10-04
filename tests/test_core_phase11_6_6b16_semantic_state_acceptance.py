from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_explicit_user_constraint_violations,
    find_python_mutable_default_semantics_violations,
    find_scaler_leakage_contradiction_violations,
    find_source_provenance_honesty_violations,
    find_user_diagnostic_overclaim_violations,
)


def run():
    # 12:05 Python follow-up: the validator must derive the trace from the
    # prior USER-authored program, not memorize one previously seen bad list.
    python_history = [{
        "role": "user",
        "content": "python question: `def f(x=[]): x.append(7); return x` then `print(f()); print(f())` -- what prints?",
    }]
    python_user = "WHAT why didn't python make a new list every call 😭"
    for bad in (
        "Python evaluates defaults once. That's why both prints show [7].",
        "Python evaluates defaults once. That's why both prints show [7, 7].",
        "The first print is [7, 7], then the second is [7, 7].",
    ):
        violations = find_python_mutable_default_semantics_violations(
            python_user,
            bad,
            python_history,
        )
        assert any("derived" in item or "same output" in item for item in violations), (bad, violations)

    assert not find_python_mutable_default_semantics_violations(
        python_user,
        (
            "Python evaluates the default list once when the function is defined and reuses it when x is omitted. "
            "So the first call returns [7], then the second call reuses that list and returns [7, 7]."
        ),
        python_history,
    )

    # 12:05 general data-leakage explanation: an exam analogy alone is not a
    # sufficient tutoring answer if it never explains the information boundary.
    leakage_user = "bro can u explain data leakage in machine learning like i actually need to understand it, not just paste a definition"
    leakage_bad = (
        "Data leakage is basically you cheating on the test by peeking at the answer key before the exam starts. "
        "The model just memorizes the math, not the relationship between size and value."
    )
    violations = find_scaler_leakage_contradiction_violations(leakage_user, leakage_bad)
    assert any("information-boundary" in item for item in violations), violations
    assert not find_scaler_leakage_contradiction_violations(
        leakage_user,
        (
            "Data leakage is when information that should be unavailable to the training process sneaks into training, preprocessing, or model selection. "
            "For example, if held-out test statistics influence preprocessing, the evaluation is no longer independent of the data used to build the model."
        ),
    )

    # 12:05 scaler example: catch semantic direction reversal, self-contradictory
    # 'blind' language, guaranteed optimism, and executable code after a comment.
    scaler_history = [{"role": "user", "content": leakage_user}]
    scaler_user = "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"
    scaler_bad = '''Fitting the scaler before the train/test split leaks information because the scaler learns statistics from the entire dataset, including the test set. Here's a tiny example:
```python
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
import numpy as np
X = np.random.randn(100, 1)
y = X.flatten()
scaler = StandardScaler().fit(X)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
X_train_scaled = scaler.transform(X_train)
X_test_scaled = scaler.transform(X_test)  # This leaks info from training to test! model = LinearRegression()
model.fit(X_train_scaled, y_train)
```
This leads to overly optimistic performance estimates. The test set remains truly blind to training.'''
    violations = find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_bad,
        scaler_history,
    )
    assert any("reversed the information flow" in item for item in violations), violations
    assert any("unseen/blind" in item for item in violations), violations
    assert any("executable Python after an inline comment" in item for item in violations), violations
    assert any("guaranteed" in item for item in violations), violations

    scaler_good = (
        "Tiny example: suppose training values are 0 and 10 while the held-out test value is 100. "
        "If you fit the scaler before the split, that 100 influences the mean and scale used on the training data; fit on training only, then transform the test set with those training-derived parameters. "
        "That contamination can make the evaluation too optimistic, but it does not guarantee a particular score change."
    )
    assert not find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_good,
        scaler_history,
    )

    # 12:05 Wi-Fi turn 1: do not promote an unmeasured cause to a 'classic'
    # diagnosis or make a band hypothesis the first isolation step.
    wifi_user = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_bad = (
        "That's a classic symptom of interference or poor placement. First, I'd check if your phone is actually connecting to the 5 GHz band. "
        "Then try moving closer to the router."
    )
    contract = AnswerContractRuntime(intent="factual_question", epistemic_mode="stable_model_knowledge")
    violations = find_user_diagnostic_overclaim_violations(wifi_user, wifi_bad, contract)
    assert any("near-certainty" in item for item in violations), violations
    assert any("near-vs-problem-location" in item for item in violations), violations
    assert not find_user_diagnostic_overclaim_violations(
        wifi_user,
        (
            "Test the same phone next to the main Wi-Fi source/router with the same speed test, then compare it with upstairs. "
            "If it is fast near the source but slow upstairs, that shifts suspicion toward the local wireless/mesh path without yet telling you whether the cause is signal, roaming, backhaul, or interference."
        ),
        contract,
    )

    # 12:05 explicit medium lock: acknowledgement is allowed, anime-specific
    # story/adaptation material is not.
    manga_user = "and when i say i read it i mean the manga, not the anime. keep the two separate pls"
    manga_bad = (
        "Understood. I'll keep the manga and anime in their own lanes, even if the anime team tries to steal your attention "
        "with its own version of Denji's antics."
    )
    violations = find_explicit_user_constraint_violations(manga_user, manga_bad)
    assert any("anime discussion" in item for item in violations), violations
    assert not find_explicit_user_constraint_violations(
        manga_user,
        "Yep — when you say you read it, I'll treat that as the manga and keep anime discussion separate unless you ask for it.",
    )

    # 12:05 source provenance: "did not need to load" is still evasive when
    # Oliver explicitly asks whether retrieval actually happened.
    provenance_user = "which official link is that from? and if you didn't actually load it, SAY THAT"
    provenance_bad = (
        'The answer comes straight from https://docs.python.org/3/library/venv.html. '
        'I did not need to "load" anything in the traditional sense; I checked the official docs as requested.'
    )
    violations = find_source_provenance_honesty_violations(provenance_user, provenance_bad)
    assert any("evaded" in item for item in violations), violations
    assert not find_source_provenance_honesty_violations(
        provenance_user,
        "I did retrieve the official page for this turn: https://docs.python.org/3/library/venv.html.",
    )

    print(
        "PASS: B16 deterministic trace continuity, leakage semantics/code integrity, diagnostic isolation, medium lock and provenance honesty"
    )


if __name__ == "__main__":
    run()
