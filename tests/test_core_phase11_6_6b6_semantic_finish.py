"""Phase 11.6.6B6: semantic holdout closures after B5.

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
from core.claim_grounding import find_user_diagnostic_overclaim_violations
from core.conversation_state import ConversationState
from core.epistemic_router import route_epistemic_authority
from core.intent_router import (
    classify_turn,
    is_source_provenance_followup,
    reconstruct_bounded_factual_followup,
    source_provenance_research_query,
)
from personality.spoiler_guard import (
    find_spoiler_guard_violations,
    prepare_spoiler_context,
)


def run() -> None:
    # Concrete code traces are self-contained reasoning problems. The full
    # benchmark wording must no longer fall through to generic stable-fact
    # generation, which previously collapsed two print calls into one output.
    code_prompt = (
        "python question: `def f(x=[]): x.append(7); return x` then "
        "`print(f()); print(f())` -- what prints?"
    )
    code_turn = classify_turn(code_prompt)
    assert code_turn.intent == "reason_from_supplied_premises", code_turn.intent
    assert code_turn.entities.get("reasoning_kind") == "code_trace"
    code_route = route_epistemic_authority(code_turn)
    assert code_route.mode == "user_premise_reasoning"

    orchestrator = (SRC / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert "report each observed output separately and in order" in orchestrator
    assert "do not claim a default argument is stored in a closure" in orchestrator.lower()

    # A request for a counterargument is debate/opinion continuation, not a
    # generic recommendation task with an unrelated reversible-action fallback.
    counter = classify_turn(
        "nah give me an actual counterargument too, otherwise you're just agreeing with me lol"
    )
    assert counter.intent == "share_opinion", counter.intent
    assert counter.entities.get("_debate_continuation") == "true"
    assert counter.should_recommend is False

    # "Give me the trade-offs" is an informational comparison request even
    # without a trailing question mark. A narrowing follow-up must preserve the
    # original pair rather than silently substituting a third platform.
    first = classify_turn(
        "mac vs windows for dev... actually don't tell me one is 'better' overall. "
        "gimme the real trade-offs"
    )
    assert first.intent == "factual_question", first.intent
    assert route_epistemic_authority(first).mode == "stable_model_knowledge"

    state = ConversationState()
    state.remember_user_turn(first)
    narrowed = classify_turn(
        "okay narrow it to Python, Linux VMs and messing around with networks. "
        "don't invent my budget or which one i already own",
        state,
    )
    narrowed = state.resolve_follow_up(narrowed)
    narrowed_route = route_epistemic_authority(narrowed)
    narrowed_contract = build_answer_contract(narrowed, narrowed_route)
    rendered = narrowed_contract.to_model_instruction().lower()
    assert narrowed_contract.metadata.get("comparison_frame") == "mac vs windows"
    assert "preserve the requested comparison between mac and windows" in rendered
    assert "do not silently replace either side with a third option" in rendered

    # Source-provenance follow-ups re-run the exact previous USER question.
    # Synthetic instructions/current deictic wording must not pollute the web query.
    previous = (
        "bro can u check the OFFICIAL Python venv docs: do virtual environments inherit "
        "system site packages by default? give me the actual source URL, not trust me bro"
    )
    provenance_turn = (
        "which official link is that from? and if you didn't actually load it, SAY THAT"
    )
    assert is_source_provenance_followup(provenance_turn)
    reconstructed = reconstruct_bounded_factual_followup(provenance_turn, previous)
    assert reconstructed is not None
    assert "official/primary source" in reconstructed.lower()  # preserve B5 API contract
    exact_research_query = source_provenance_research_query(provenance_turn, previous)
    assert exact_research_query == previous
    assert "verify this again" not in exact_research_query.lower()

    provider = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    assert "CORE SOURCE-PROVENANCE FOLLOW-UP" in provider
    assert "CURRENT provenance question, not the old question" in provider
    assert "Do not trust or repeat a URL merely because a prior" in provider

    # Diagnostic reasoning can explain hypotheses but cannot manufacture
    # Oliver-specific configuration/topology from nearby speed readings.
    diag_state = ConversationState()
    diag_first = classify_turn(
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "what would you test first?",
        diag_state,
    )
    diag_state.remember_user_turn(diag_first)
    diag_follow = classify_turn(
        "tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. "
        "so what does that rule out?",
        diag_state,
    )
    diag_follow = diag_state.resolve_follow_up(diag_follow)
    diag_route = route_epistemic_authority(diag_follow)
    assert diag_route.mode == "user_context_reasoning"
    diag_contract = build_answer_contract(diag_follow, diag_route).to_model_instruction()
    diag_conversation = [{"role": "user", "content": diag_first.raw_text}]

    bad_drafts = (
        "Your wired console is on 160 MHz while the phone is on 40 MHz.",
        "The backhaul path is fine, so that is ruled out.",
        "The specific access point serving your upper floor is the bottleneck.",
    )
    for bad in bad_drafts:
        assert find_user_diagnostic_overclaim_violations(
            diag_follow.raw_text,
            bad,
            diag_contract,
            diag_conversation,
        ), bad

    conservative = (
        "The 580 Mbps result near the main node makes the ISP connection itself less likely "
        "to be the limiting factor there, but it does not identify whether the upstairs loss "
        "is signal, interference, or an unmeasured mesh path."
    )
    assert not find_user_diagnostic_overclaim_violations(
        diag_follow.raw_text,
        conservative,
        diag_contract,
        diag_conversation,
    )

    # Explicit conversation-scoped spoiler ceilings must reject ungrounded
    # character end-state/transformation summaries while retaining safe craft analysis.
    spoiler_conversation = [{
        "role": "user",
        "content": (
            "lowkey i think the best part of Vinland Saga is the character writing, "
            "not the fights. thoughts? no spoilers past season 1"
        ),
    }]
    spoiler_context = prepare_spoiler_context(
        "nah i mean like WHY the character writing works, not whether i should watch it lol",
        spoiler_conversation,
    )
    risky = "The protagonist's journey from vengeance to peace is what makes the writing work."
    assert find_spoiler_guard_violations(risky, spoiler_context)
    safe = (
        "The writing works because motivations are clear, choices have consequences, and "
        "conflicting values create tension without needing a future character outcome."
    )
    assert not find_spoiler_guard_violations(safe, spoiler_context)

    # An explicit social share should not be allowed to collapse into a sterile
    # one-line acknowledgement after model retries fail.
    assert "collapsed an explicit sharing moment into a generic acknowledgement" in provider

    # Recommendation lanes may still use stable judgement, but should not turn
    # uncertainty about AI/job change into an unsupported replacement forecast.
    recommendation = classify_turn(
        "i don't want a motivational speech. give me one concrete skill worth practising regardless"
    )
    recommendation_route = route_epistemic_authority(recommendation)
    recommendation_contract = build_answer_contract(recommendation, recommendation_route)
    rec_text = recommendation_contract.to_model_instruction().lower()
    assert "do not justify a recommendation with a confident prediction" in rec_text

    print(
        "PASS: B6 code-trace sequencing, debate/tradeoff continuity, provenance, diagnostic "
        "discipline, spoiler ceilings, social-share relevance and forecast-safe recommendations"
    )


if __name__ == "__main__":
    run()
