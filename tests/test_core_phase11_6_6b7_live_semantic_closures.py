"""Phase 11.6.6B7: closures from the 2026-09-30 full Oliver holdout.

Deterministic only: no Ollama, public network, private tools, or write actions.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract import build_answer_contract
from core.answer_contract_runtime import coerce_answer_contract_runtime
from core.claim_grounding import (
    find_explicit_example_request_violations,
    find_pairwise_comparison_drift_violations,
    find_recommendation_forecast_violations,
    find_session_cookie_security_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.conversation_state import ConversationState
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn
from personality.spoiler_guard import (
    find_spoiler_guard_violations,
    prepare_spoiler_context,
)
from research.public_factual_grounding import (
    _deterministic_population_scope_indexes,
)


def run() -> None:
    # The canonical mutable-default trace is safe to solve deterministically.
    # Do not execute arbitrary code; the bounded parser must return both print
    # results in order and keep the code-reasoning route established in B6.
    code_prompt = (
        "python question: `def f(x=[]): x.append(7); return x` then "
        "`print(f()); print(f())` -- what prints?"
    )
    code_turn = classify_turn(code_prompt)
    assert code_turn.intent == "reason_from_supplied_premises"
    assert code_turn.entities.get("reasoning_kind") == "code_trace"
    direct = str(code_turn.entities.get("reasoning_direct_answer") or "")
    assert "[7]" in direct and "[7, 7]" in direct, direct
    assert direct.index("[7]") < direct.index("[7, 7]"), direct
    assert "closure" not in direct.lower()

    # Explicit live spoiler ceilings are conservative about names the user did
    # not introduce, and about future-direction language phrased in new ways.
    spoiler_user = (
        "lowkey i think the best part of Vinland Saga is the character writing, "
        "not the fights. thoughts? no spoilers past season 1"
    )
    spoiler_ctx = prepare_spoiler_context(spoiler_user, [])
    leaked_name = (
        "The writing is strong enough that you could be crying over Thorfinn or Einar."
    )
    assert find_spoiler_guard_violations(leaked_name, spoiler_ctx)
    leaked_direction = (
        "The way Thorfinn's motivations shift from vengeance to survival to purpose is compelling."
    )
    assert find_spoiler_guard_violations(leaked_direction, spoiler_ctx)
    safe_craft = (
        "The writing works because motivations are clear, choices have consequences, "
        "and conflicting values create tension without revealing a later outcome."
    )
    assert not find_spoiler_guard_violations(safe_craft, spoiler_ctx)

    named_by_user_ctx = prepare_spoiler_context(
        "what about Thorfinn specifically? no spoilers past season 1",
        [],
    )
    assert not find_spoiler_guard_violations(
        "Thorfinn works because his choices have clear consequences.",
        named_by_user_ctx,
    )

    # Troubleshooting: first test should isolate a variable rather than force
    # unmeasured radio settings; later measurements cannot prove wall materials,
    # antenna alignment or an attic/drywall cause.
    diag_state = ConversationState()
    first_text = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    first = classify_turn(first_text, diag_state)
    first_contract = build_answer_contract(first, route_epistemic_authority(first))
    bad_first = "Try forcing it to 5GHz and see if the speed magically improves."
    assert find_user_diagnostic_overclaim_violations(
        first_text,
        bad_first,
        first_contract.to_model_instruction(),
        [],
    )

    diag_state.remember_user_turn(first)
    follow_text = (
        "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. "
        "so what does that rule out?"
    )
    follow = classify_turn(follow_text, diag_state)
    follow = diag_state.resolve_follow_up(follow)
    follow_contract = build_answer_contract(follow, route_epistemic_authority(follow))
    prior = [{"role": "user", "content": first_text}]
    live_bad = (
        "The bottleneck is almost certainly physical interference (concrete walls, metal studs) "
        "or poor antenna alignment for that vertical path."
    )
    assert find_user_diagnostic_overclaim_violations(
        follow_text, live_bad, follow_contract.to_model_instruction(), prior
    )
    live_bad_2 = (
        "That's a classic case of the signal dying in the attic or getting absorbed by drywall."
    )
    assert find_user_diagnostic_overclaim_violations(
        follow_text, live_bad_2, follow_contract.to_model_instruction(), prior
    )
    live_good = (
        "The fast result by the main node makes the ISP connection less likely to be the "
        "limiting factor there, but the readings alone do not identify whether the upstairs "
        "loss is signal, interference, or an unmeasured mesh path."
    )
    assert not find_user_diagnostic_overclaim_violations(
        follow_text, live_good, follow_contract.to_model_instruction(), prior
    )

    # Pairwise comparison metadata now survives into the structured runtime so
    # acceptance can reject a conclusion that silently swaps in a third OS.
    compare_state = ConversationState()
    compare_first = classify_turn(
        "mac vs windows for dev... actually don't tell me one is 'better' overall. "
        "gimme the real trade-offs",
        compare_state,
    )
    compare_state.remember_user_turn(compare_first)
    compare_follow = classify_turn(
        "okay narrow it to Python, Linux VMs and messing around with networks. "
        "don't invent my budget or which one i already own",
        compare_state,
    )
    compare_follow = compare_state.resolve_follow_up(compare_follow)
    compare_contract = build_answer_contract(
        compare_follow,
        route_epistemic_authority(compare_follow),
    )
    runtime = coerce_answer_contract_runtime(compare_contract)
    assert runtime is not None
    assert runtime.metadata.get("comparison_frame") == "mac vs windows"
    assert find_pairwise_comparison_drift_violations(
        "On macOS you get Unix tooling. On Windows you get WSL2. "
        "If you're comfortable with Linux, sticking with it saves time.",
        compare_contract,
    )

    # An explicit example request must contain an actual concrete example.
    example_user = (
        "okay but WHY is fitting the scaler before the train/test split a problem? "
        "give me a tiny example"
    )
    abstract_only = (
        "Fitting before the split uses statistics from all data and contaminates evaluation."
    )
    assert find_explicit_example_request_violations(example_user, abstract_only)
    assert not find_explicit_example_request_violations(
        example_user,
        "Suppose train values are 1 and 2 while the held-out value is 100; fitting on all three changes the mean.",
    )

    # A recommendation can be useful without asserting that a skill is immune
    # to AI/automation replacement.
    recommendation = classify_turn(
        "i don't want a motivational speech. give me one concrete skill worth practising regardless"
    )
    rec_contract = build_answer_contract(
        recommendation,
        route_epistemic_authority(recommendation),
    )
    assert find_recommendation_forecast_violations(
        "Low-level networking fundamentals. That's exactly why it won't be replaced by AI.",
        rec_contract,
    )
    assert not find_recommendation_forecast_violations(
        "Low-level networking fundamentals. Packet captures force you to reason about what the network is actually doing.",
        rec_contract,
    )

    # Local browser-cookie deletion is not server-side revocation of an
    # attacker's already-copied authenticated session.
    session_user = (
        "bro if someone nicks an already-logged-in session cookie, will switching on MFA "
        "magically stop them using it?"
    )
    assert find_session_cookie_security_violations(
        session_user,
        "No. They're in until you clear the cookies or revoke the session.",
    )
    assert not find_session_cookie_security_violations(
        session_user,
        "No. The copied cookie remains usable until it expires or the server-side session is revoked; "
        "clearing only your local browser cookie does not erase the attacker's copy.",
    )

    # A narrow BLS occupation projection cannot be rewritten as a projection
    # for the entire cybersecurity field.
    packet = {
        "sources": [{
            "source_host": "www.bls.gov",
            "title": "Information Security Analysts : Occupational Outlook Handbook: : U.S. Bureau of Labor Statistics",
        }]
    }
    assert _deterministic_population_scope_indexes(
        packet,
        ["The U.S. Bureau of Labor Statistics projects cybersecurity jobs to grow by 21% through 2035."],
    ) == {1}
    assert not _deterministic_population_scope_indexes(
        packet,
        ["The U.S. Bureau of Labor Statistics projects information security analysts to grow by 21% through 2035."],
    )

    public_research_source = (
        SRC / "research" / "public_factual_research.py"
    ).read_text(encoding="utf-8")
    assert 'r"\\bnext year\\b"' in public_research_source
    assert 'time_range = "year"' in public_research_source

    provider = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    assert "find_pairwise_comparison_drift_violations" in provider
    assert "find_recommendation_forecast_violations" in provider
    assert "find_explicit_example_request_violations" in provider
    assert "find_session_cookie_security_violations" in provider

    print(
        "PASS: B7 deterministic code trace, spoiler name/direction ceiling, diagnostic evidence discipline, "
        "comparison scope, example compliance, forecast-safe recommendations/session semantics and fresh labour scope"
    )


if __name__ == "__main__":
    run()
