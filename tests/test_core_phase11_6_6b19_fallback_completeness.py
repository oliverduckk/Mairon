from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.claim_grounding import (
    build_stable_model_knowledge_fallback,
    find_explicit_user_constraint_violations,
    find_recommendation_topic_drift_violations,
    find_scaler_leakage_contradiction_violations,
    find_session_cookie_security_violations,
)


def run():
    # 15:06 critical failure: a stable textbook concept can be rejected by
    # strict acceptance without dropping all the way to a generic evidence-limit
    # refusal. Core has a narrow deterministic fallback for this concept.
    leakage_user = (
        "bro can u explain data leakage in machine learning like i actually "
        "need to understand it, not just paste a definition"
    )
    fallback = build_stable_model_knowledge_fallback(leakage_user)
    assert fallback is not None
    lower = fallback.lower()
    assert "train" in lower
    assert "test" in lower or "validation" in lower
    assert "can make" in lower or "can" in lower
    assert build_stable_model_knowledge_fallback("what does a Python tuple do?") is None

    # Exact 15:06 scaler follow-up: it is not a tiny example, and it
    # contradicts the leaking workflow by later claiming the test set did not
    # influence the fitted parameters.
    scaler_user = (
        "okay but WHY is fitting the scaler before the train/test split a problem? "
        "give me a tiny example"
    )
    scaler_bad = (
        "Fitting the scaler before the split leaks information from the test set into your training process. "
        "You want to predict Y using X. If you fit the scaler (e.g., StandardScaler) on the entire dataset before splitting, "
        "it calculates the mean and standard deviation using both training and test data. Then, when you transform your test set, "
        "you're essentially using information from the test set to scale it. This means your model indirectly sees the test data "
        "during preprocessing, which violates the assumption that the test set is unseen. The test set is transformed using these "
        "parameters without influencing them. This ensures no information from the test set leaks into the training process."
    )
    violations = find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_bad,
        [{"role": "user", "content": leakage_user}],
    )
    assert any("tiny-example request" in v for v in violations), violations
    assert any("no longer influenced" in v for v in violations), violations

    short_user = "wait explain the whole thing in like 2 sentences, my brain is cooked"
    short_bad = (
        "Fitting a scaler on the full dataset lets it peek at the test data's distribution, so its parameters are biased toward that unseen set. "
        "When you then scale the test set with those same parameters, you've effectively given the model a cheat sheet about how to normalize "
        "future data, inflating your performance metrics."
    )
    violations = find_scaler_leakage_contradiction_violations(
        short_user,
        short_bad,
        [
            {"role": "user", "content": leakage_user},
            {"role": "user", "content": scaler_user},
        ],
    )
    assert any("optimistic/inflated" in v for v in violations), violations

    scaler_good = (
        "Tiny example: suppose the training values are 0 and 10 and the held-out test value is 100. "
        "If you fit the scaler on all three, 100 influences the mean/scale used for training. "
        "Fit on the training values only, then apply those learned parameters to the test value; leakage can make evaluation too optimistic."
    )
    assert not find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_good,
        [{"role": "user", "content": leakage_user}],
    )

    # Exact 15:06 session-cookie paraphrase: generic local logout is not
    # necessarily server-side revocation of an attacker's copied token.
    session_user = (
        "bro if someone nicks an already-logged-in session cookie, will switching on MFA magically stop them using it?"
    )
    session_bad = (
        "No, switching on MFA won't magically revoke a stolen cookie. The attacker already has a valid session token; "
        "they'll keep using that old cookie until it expires or you log out."
    )
    violations = find_session_cookie_security_violations(session_user, session_bad)
    assert any("unspecified logout" in v for v in violations), violations
    assert not find_session_cookie_security_violations(
        session_user,
        "No. MFA does not revoke the copied token; it remains usable until it expires or the service invalidates/revokes that session server-side.",
    )

    # Exact 15:06 medium-lock paraphrase: saying the anime is not comparable to
    # the manga is still a comparison after Oliver asked to keep them separate.
    medium_user = (
        "and when i say i read it i mean the manga, not the anime. keep the two separate pls"
    )
    medium_bad = (
        "Noted, I'll keep the anime in its own little box of misery so you don't have to pretend it's comparable to the manga."
    )
    violations = find_explicit_user_constraint_violations(medium_user, medium_bad)
    assert any("locked the conversation to manga" in v for v in violations), violations
    assert not find_explicit_user_constraint_violations(
        medium_user,
        "Yep — manga only. I'll keep the anime separate unless you explicitly bring it up.",
    )

    # Hidden PASS from 15:06: the live topic is the grad rejection/application;
    # generic 'uni shit' is a time constraint, not permission to invent an assignment.
    recommendation_user = "okay, one actual useful next step. ONE. i have uni shit to do too"
    recommendation_bad = (
        "One thing that usually moves the ball forward: pick the smallest unreadable assignment "
        "and start typing the bare minimum required to get it out of the way."
    )
    conversation = [
        {
            "role": "user",
            "content": "bruh ANOTHER generic grad rejection email. i just wanna complain for a sec",
        }
    ]
    violations = find_recommendation_topic_drift_violations(
        recommendation_user,
        recommendation_bad,
        conversation,
    )
    assert any("invented a specific university task" in v for v in violations), violations
    assert not find_recommendation_topic_drift_violations(
        recommendation_user,
        "Spend 10 minutes tailoring the next application you actually want, then stop and get back to uni.",
        conversation,
    )

    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    assert "build_stable_model_knowledge_fallback" in provider_source
    assert 'core_epistemic_mode == "stable_model_knowledge"' in provider_source

    print(
        "PASS: B19 stable-knowledge fallback completeness plus scaler, session, medium-lock and recommendation continuity"
    )


if __name__ == "__main__":
    run()
