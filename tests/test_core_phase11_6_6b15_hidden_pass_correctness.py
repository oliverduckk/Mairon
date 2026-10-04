from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Keep this regression independent of optional Gmail/Calendar packages pulled in
# by the real tool registry. public_factual_research only needs execute_tool,
# which this test replaces with a deterministic fake below.
if "tools.tool_registry" not in sys.modules:
    registry_stub = types.ModuleType("tools.tool_registry")
    registry_stub.execute_tool = lambda *args, **kwargs: None
    sys.modules["tools.tool_registry"] = registry_stub

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_explicit_user_constraint_violations,
    find_incidental_public_attribution_violations,
    find_insufficient_context_overreach_violations,
    find_python_mutable_default_semantics_violations,
    find_recommendation_topic_drift_violations,
    find_session_cookie_security_violations,
    find_user_diagnostic_overclaim_violations,
)
import research.public_factual_research as public_research


def run():
    # Exact 11:25 stolen-session wording: clearing the victim browser's data
    # does not revoke the attacker's already-copied credential.
    session_user = (
        "bro if someone nicks an already-logged-in session cookie, will switching on MFA magically stop them using it?"
    )
    session_bad = (
        "No, switching on MFA won't magically revoke a stolen session cookie. The attacker already has a valid session token; "
        "enabling MFA just stops them from creating new sessions. They can keep using that specific cookie until it expires "
        "or you clear your browser data."
    )
    violations = find_session_cookie_security_violations(session_user, session_bad)
    assert any("local cookie deletion" in item for item in violations), violations
    assert not find_session_cookie_security_violations(
        session_user,
        (
            "No. MFA protects new logins, but a copied session can remain usable until expiry or server-side revocation. "
            "Clearing your own browser data only removes your local copy; it does not revoke the attacker's copied token."
        ),
    )

    # Exact 11:25 mutable-default follow-up: preserve first [7], second [7, 7].
    python_history = [{
        "role": "user",
        "content": "python question: `def f(x=[]): x.append(7); return x` then `print(f()); print(f())` -- what prints?",
    }]
    python_user = "WHAT why didn't python make a new list every call 😭"
    python_bad = (
        "The default value is evaluated only once, at function definition time, not on each call. "
        "So x=[] creates one shared list object that persists across calls. That's why both prints show [7, 7]."
    )
    violations = find_python_mutable_default_semantics_violations(
        python_user,
        python_bad,
        python_history,
    )
    assert any("first call is [7]" in item for item in violations), violations
    assert not find_python_mutable_default_semantics_violations(
        python_user,
        (
            "The default list is created once when the function is defined and reused on later calls that omit x. "
            "So the first call mutates it to [7], and the second reuses that same list and returns [7, 7]."
        ),
        python_history,
    )

    # Exact 11:25 manga/anime lock: no adaptation detail and no ungrounded
    # single-token creator attribution such as "Sato's art".
    manga_user = "and when i say i read it i mean the manga, not the anime. keep the two separate pls"
    manga_bad = (
        "Good, I'll respect that boundary. The anime's pacing and filler can be a real letdown compared to Sato's art, "
        "so it makes sense to treat them as different experiences."
    )
    violations = find_explicit_user_constraint_violations(manga_user, manga_bad)
    assert any("anime discussion" in item for item in violations), violations
    attribution = find_incidental_public_attribution_violations(
        manga_user,
        manga_bad,
        AnswerContractRuntime(intent="casual_conversation", epistemic_mode="social_conversation"),
        conversation=[{"role": "user", "content": "finally got back into reading Chainsaw Man"}],
    )
    assert any("Sato" in item for item in attribution), attribution
    assert not find_explicit_user_constraint_violations(
        manga_user,
        "Yep — when you say you read it, I'll treat that as the manga and keep anime discussion separate unless you ask for it.",
    )

    # Exact 11:25 rejection follow-up: generic "uni shit" is a time/attention
    # constraint, not evidence of grades, a portal, avoided email, or doomscrolling.
    rec_user = "okay, one actual useful next step. ONE. i have uni shit to do too"
    rec_history = [{
        "role": "user",
        "content": "bruh ANOTHER generic grad rejection email. i just wanna complain for a sec, please don't give me another 9-step career plan 😭",
    }]
    rec_bad = (
        "One step: stop scrolling through emails for 10 minutes and do something useful. "
        "Open your uni portal and check grades, or write the one email you've been avoiding instead of doomscrolling."
    )
    violations = find_recommendation_topic_drift_violations(rec_user, rec_bad, rec_history)
    assert any("personal task" in item or "university task" in item for item in violations), violations
    assert not find_recommendation_topic_drift_violations(
        rec_user,
        "Take the next role you actually want and spend 10 minutes tailoring that application, then stop and get back to uni.",
        rec_history,
    )

    # Exact 11:25 VRR follow-up: dark scenes do not mean the display lowers
    # refresh rate to save power/reduce motion blur.
    vrr_user = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    vrr_history = [{
        "role": "user",
        "content": "anyway why does my screen flicker when variable refresh rate is on?",
    }]
    vrr_bad = (
        "Yes, it could still be VRR. Flicker in dark scenes often happens because the display drops its refresh rate "
        "to save power or reduce motion blur when the image is static and dim."
    )
    violations = find_user_diagnostic_overclaim_violations(
        vrr_user,
        vrr_bad,
        AnswerContractRuntime(intent="factual_question", epistemic_mode="user_context_reasoning"),
        vrr_history,
    )
    assert any("scene-brightness/power" in item for item in violations), violations
    assert not find_user_diagnostic_overclaim_violations(
        vrr_user,
        (
            "Yes, it could still be related to VRR. Dark scenes can make luminance/gamma instability easier to notice, "
            "but that pattern alone does not prove VRR is the cause or identify a specific panel mechanism."
        ),
        AnswerContractRuntime(intent="factual_question", epistemic_mode="user_context_reasoning"),
        vrr_history,
    )

    # Exact 11:25 unknown-airline response: missing carrier policy/bag dimensions
    # cannot justify invented boarding/security consequences.
    air_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="insufficient_user_context",
    )
    air_bad = (
        "No, you are not definitely allowed. Without the airline and bag dimensions I can't give you a yes. "
        "That sounds like a recipe for getting kicked off the plane or spending an hour at security re-packing."
    )
    violations = find_insufficient_context_overreach_violations(air_bad, air_contract)
    assert any("airline/airport consequences" in item for item in violations), violations
    assert not find_insufficient_context_overreach_violations(
        "No. Without the airline's policy and your bag dimensions, I can't tell you whether that backpack is allowed as carry-on.",
        air_contract,
    )

    # Explicit official-documentation requests may use only a deterministic
    # primary-official source. A relevant third-party/legacy guide cannot
    # satisfy "official Python docs" when docs.python.org is available.
    calls = []
    original_execute = public_research.execute_tool

    def fake_execute(tool_name, args):
        calls.append((tool_name, dict(args)))
        if tool_name == "web_search":
            return {
                "success": True,
                "results": [
                    {
                        "title": "virtualenv legacy user guide",
                        "url": "https://virtualenv.pypa.io/en/legacy/userguide.html",
                        "snippet": "legacy virtualenv documentation",
                    },
                    {
                        "title": "venv — Creation of virtual environments",
                        "url": "https://docs.python.org/3/library/venv.html",
                        "snippet": "Python documentation for venv",
                    },
                ],
            }
        if tool_name == "web_read":
            url = args["url"]
            return {
                "success": True,
                "url": url,
                "content": "system_site_packages defaults to false; --system-site-packages enables access.",
            }
        raise AssertionError(tool_name)

    public_research.execute_tool = fake_execute
    try:
        result = public_research.gather_public_factual_research(
            "check the OFFICIAL Python venv docs and give me the actual source URL",
            max_reads=2,
        )
    finally:
        public_research.execute_tool = original_execute

    assert result["success"], result
    accepted = [
        s for s in result["sources"]
        if s.get("read_success") and s.get("accepted_as_evidence") is not False
    ]
    assert accepted, result
    assert accepted[0]["url"].startswith("https://docs.python.org/"), accepted
    assert all("virtualenv.pypa.io" not in s["url"] for s in accepted), accepted
    read_urls = [args["url"] for tool, args in calls if tool == "web_read"]
    assert read_urls[0].startswith("https://docs.python.org/"), read_urls

    print(
        "PASS: B15 exact-output continuity, session revocation, manga-medium grounding, recommendation grounding, VRR calibration, airline uncertainty and official-doc authority"
    )


if __name__ == "__main__":
    run()
