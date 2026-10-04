from pathlib import Path
import ast
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_scaler_leakage_contradiction_violations,
    find_session_cookie_security_violations,
    find_user_diagnostic_overclaim_violations,
)


def _load_opinion_fallback():
    provider_path = SRC / "ai" / "ollama_provider.py"
    source = provider_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "build_substantive_opinion_fallback"
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "build_spoiler_safe_discussion_fallback": (
            lambda user_input, spoiler_context: (
                "Staying inside your spoiler limit, character motivations, values and consequences can make the fights matter as pressure rather than spectacle."
            )
        ),
    }
    exec(compile(module, str(provider_path), "exec"), namespace)
    return namespace["build_substantive_opinion_fallback"], source


def run():
    # 23:20 holdout root cause: B12 correctly rejected "Got it.", but the
    # generic Core grounding fallback returned the same bare acknowledgement.
    # Initial opinion requests must instead receive a substantive bounded fallback.
    opinion_fallback, provider_source = _load_opinion_fallback()
    answer = opinion_fallback(
        user_input=(
            "lowkey i think the best part of Vinland Saga is the character writing, "
            "not the fights. thoughts? no spoilers past season 1"
        ),
        spoiler_context={"profile": {"progress_type": "season", "progress_value": 1}},
        media_domain_active=True,
    )
    assert answer.strip().lower() != "got it."
    assert len(answer.strip()) >= 25
    opinion_branch = provider_source.index('elif core_intent == "share_opinion":')
    generic_branch = provider_source.index(
        'elif (\n                core_grounding_failed',
        opinion_branch,
    )
    assert opinion_branch < generic_branch

    # Exact 23:20 scaler answer: the leaking workflow cannot simultaneously
    # claim the contaminated test set remains "unseen".
    scaler_user = (
        "okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example"
    )
    scaler_history = [{
        "role": "user",
        "content": "bro can u explain data leakage in machine learning like i actually need to understand it, not just paste a definition",
    }]
    scaler_bad_example = '''Fitting the scaler on the whole dataset (including test data) leaks information.
```python
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2)
model.fit(X_train, y_train)
score_wrong = model.score(X_test, y_test)  # Biased score! This ensures your test set remains truly "unseen" during the learning phase.
```'''
    example_violations = find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_bad_example,
        scaler_history,
    )
    assert any("unseen" in item for item in example_violations), example_violations

    # Exact short follow-up paraphrase: combined train/test statistics influence
    # preprocessing; they do not literally make train scaling "match" test, and
    # optimistic test performance is a risk rather than a guaranteed outcome.
    scaler_short_user = "wait explain the whole thing in like 2 sentences, my brain is cooked"
    scaler_short_bad = (
        "Fitting a scaler before the split leaks information because the scaler learns its parameters from the test data, "
        "which then biases the training set's scaling to match the test set. This makes your model artificially good at "
        "predicting the test set since it has essentially seen the answer key during training."
    )
    short_violations = find_scaler_leakage_contradiction_violations(
        scaler_short_user,
        scaler_short_bad,
        scaler_history + [{"role": "user", "content": scaler_user}],
    )
    assert any("match the test set" in item for item in short_violations), short_violations
    assert any("guaranteed" in item for item in short_violations), short_violations
    assert not find_scaler_leakage_contradiction_violations(
        scaler_short_user,
        (
            "Fitting before the split lets test-set statistics influence the scaler parameters used on training data, "
            "so the evaluation is no longer fully independent. That can bias the measured test performance, which is why "
            "you fit the scaler on training data only and then transform the held-out test set."
        ),
        scaler_history + [{"role": "user", "content": scaler_user}],
    )

    # Generic logout wording is not guaranteed to revoke an attacker's copied
    # credential. Say server-side invalidation/revocation or qualify the service.
    session_user = (
        "bro if someone nicks an already-logged-in session cookie, will switching on MFA magically stop them using it?"
    )
    session_bad = (
        "No. They're effectively riding shotgun in your account until you log out or the session times out."
    )
    assert find_session_cookie_security_violations(session_user, session_bad)
    assert not find_session_cookie_security_violations(
        session_user,
        (
            "No. A copied session can remain usable until it expires or the service revokes/invalidates that session server-side; "
            "MFA mainly protects new authentication attempts."
        ),
    )

    # VRR diagnostics: correlation supports a hypothesis, not a definite cause;
    # and a hard switch to display troubleshooting must not revive manga/anime.
    public_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="public_source_verified",
    )
    vrr_user = "anyway why does my screen flicker when variable refresh rate is on?"
    vrr_bad = (
        "Your screen flickers with VRR enabled because unstable frame rates force the monitor to rapidly change its refresh rate."
    )
    assert find_user_diagnostic_overclaim_violations(
        vrr_user,
        vrr_bad,
        public_contract,
        [{"role": "user", "content": "BROOO that manga chapter just destroyed me lmao"}],
    )

    live_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    vrr_followup_user = (
        "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    )
    vrr_context_bleed = (
        "It could still be VRR. Dark static scenes are common in horror or action manga adaptations, "
        "so that is a strong clue that VRR is the culprit."
    )
    assert any(
        "unrelated media context" in item
        for item in find_user_diagnostic_overclaim_violations(
            vrr_followup_user,
            vrr_context_bleed,
            live_contract,
            [{"role": "user", "content": vrr_user}],
        )
    )
    assert not find_user_diagnostic_overclaim_violations(
        vrr_followup_user,
        (
            "Yes, it could still be VRR, and dark scenes can make flicker more noticeable. "
            "That pattern supports VRR as a possibility but does not prove the cause without more isolation testing."
        ),
        live_contract,
        [{"role": "user", "content": vrr_user}],
    )

    print(
        "PASS: B13 substantive opinion fallback, scaler correctness, stolen-session logout semantics and VRR context/calibration integrity"
    )


if __name__ == "__main__":
    run()
