"""Phase 11.6 B23 — stable security fallback completeness.

Regression for the acceptance invariant:
If Core has a deterministic semantic validator for a stable concept that can
reject every Qwen draft, the stable-knowledge fallback path must still produce
a bounded useful answer rather than exposing generic evidence-limit language.

This test deliberately uses multiple stolen-session phrasings so the fix is
about the semantic class, not one Oliver benchmark sentence.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(
        0,
        str(SRC),
    )


from core.claim_grounding import (  # noqa: E402
    build_stable_model_knowledge_fallback,
    find_session_cookie_security_violations,
)


def _assert_safe_stolen_session_answer(
    answer: str,
):
    assert answer
    lowered = answer.lower()

    assert (
        "server-side" in lowered
        or "server side" in lowered
    )

    assert (
        "revoke" in lowered
        or "invalidate" in lowered
        or "expire" in lowered
    )

    assert "evidence limits" not in lowered

    # The bounded fallback must not reintroduce the misconception the
    # validator exists to prevent.
    assert "clear your cookies and" not in lowered
    assert "log out and" not in lowered


def run():
    # Exact live semantic class: MFA does not retroactively kill a copied
    # authenticated session credential.
    live_style = (
        "bro if someone nicks an already-logged-in session cookie, "
        "will switching on MFA magically stop them using it?"
    )

    live_answer = (
        build_stable_model_knowledge_fallback(
            user_input=live_style,
            conversation=[],
        )
    )

    _assert_safe_stolen_session_answer(
        live_answer
    )

    live_lower = live_answer.lower()

    assert (
        live_lower.startswith("no")
        or "does not" in live_lower
        or "doesn't" in live_lower
    )

    assert (
        "mfa" in live_lower
        or "multi-factor" in live_lower
        or "multifactor" in live_lower
    )

    # Generalised alternate wording: token instead of cookie, copy instead
    # of nick/stolen, 2FA instead of MFA.
    alternate = (
        "If an attacker copied an authenticated session token, "
        "does enabling 2FA invalidate that existing session?"
    )

    alternate_answer = (
        build_stable_model_knowledge_fallback(
            user_input=alternate,
            conversation=[],
        )
    )

    _assert_safe_stolen_session_answer(
        alternate_answer
    )

    # Stable concept fallback should also remain useful when the stolen-session
    # question does not explicitly name MFA.
    generic_session = (
        "Someone stole an authenticated session token. "
        "What actually has to happen to stop that copied session being reused?"
    )

    generic_answer = (
        build_stable_model_knowledge_fallback(
            user_input=generic_session,
            conversation=[],
        )
    )

    _assert_safe_stolen_session_answer(
        generic_answer
    )

    # Do not turn ordinary cookie/session questions into the deterministic
    # stolen-session fallback.
    unrelated = (
        "What does an HTTP session cookie normally do?"
    )

    assert (
        build_stable_model_knowledge_fallback(
            user_input=unrelated,
            conversation=[],
        )
        is None
    )

    # The fallback itself must pass the existing security validator.
    assert (
        find_session_cookie_security_violations(
            user_input=live_style,
            draft=live_answer,
        )
        == []
    )

    # The validator must still reject the misconception B21 was designed to
    # catch.
    unsafe_draft = (
        "You can kick the attacker out by logging out and clearing your "
        "cookies, which invalidates their copied session."
    )

    violations = (
        find_session_cookie_security_violations(
            user_input=live_style,
            draft=unsafe_draft,
        )
    )

    assert violations

    print(
        "B23 stable security fallback completeness passed."
    )


if __name__ == "__main__":
    run()
