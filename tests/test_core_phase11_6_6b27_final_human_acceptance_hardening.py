from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    _unsupported_user_physical_object_claims,
    build_recommendation_request_fallback,
    build_stable_model_knowledge_fallback,
    find_recommendation_completion_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.seriousness import (
    build_consequential_advice_instruction,
    find_consequential_role_violations,
)
# Keep this deterministic regression independent of optional Google/calendar
# packages pulled in by the real tool registry. The research module only needs
# the execute_tool symbol at import time for these pure relevance tests.
_tool_registry_stub = types.ModuleType("tools.tool_registry")
_tool_registry_stub.execute_tool = lambda *args, **kwargs: None
sys.modules.setdefault("tools.tool_registry", _tool_registry_stub)

from research.public_factual_research import assess_public_source_relevance


def run():
    # No-browse must be enforced at provider ingress, not only inside the
    # direct-conversation fast path. Otherwise a factual request that bypasses
    # should_use_direct_conversation can still reach Qwen/tools.
    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    ingress_marker = "Verification declined by Oliver at provider ingress"
    pending_marker = "Continue a pending Night Routine v1 clarification"
    assert ingress_marker in provider_source
    assert provider_source.index(ingress_marker) < provider_source.index(pending_marker)

    # A mistaken sender must never be treated as though the transferred funds
    # are sitting in Oliver's own account.
    bank_user = "i think i just transferred money to the wrong bank account. what should i do?"
    bad_bank = (
        "Stop all activity related to that transfer. Don't touch, move, or withdraw "
        "from any affected accounts until clarified. Contact the bank immediately."
    )
    bank_violations = find_consequential_role_violations(
        user_input=bank_user,
        draft=bad_bank,
        domain="financial",
    )
    assert any("mistaken sender" in item for item in bank_violations), bank_violations
    instruction = build_consequential_advice_instruction(
        domain="financial",
        user_input=bank_user,
    ).lower()
    assert "sender" in instruction
    assert "does not by itself mean his own bank accounts must be frozen" in instruction

    # Mistaken-payment research must reject generic bank-transfer articles that
    # do not actually discuss an error/mistake/recovery situation.
    irrelevant = {
        "title": "More Than $1 Billion Was Transferred Into a Prime Minister's Bank Accounts",
        "url": "https://example.com/politics-transfer-story",
        "source_host": "example.com",
        "read_success": True,
        "read_result": {
            "success": True,
            "content": "Large sums of money were transferred into bank accounts during a political controversy.",
        },
    }
    rel = assess_public_source_relevance(
        irrelevant,
        query="transferred money to the wrong bank account what to do",
        research_identity="transferred money to the wrong bank account what to do",
        include_read_content=True,
    )
    assert rel["accepted"] is False, rel
    assert any("unresolved_query_constraint" in reason for reason in rel["reasons"]), rel

    relevant = {
        "title": "What to do after sending money to the wrong recipient",
        "url": "https://example.org/mistaken-payment-help",
        "source_host": "example.org",
        "read_success": True,
        "read_result": {
            "success": True,
            "content": "If you sent a bank transfer to the wrong recipient, contact your bank promptly and ask about its recovery process.",
        },
    }
    rel = assess_public_source_relevance(
        relevant,
        query="transferred money to the wrong bank account what to do",
        research_identity="transferred money to the wrong bank account what to do",
        include_read_content=True,
    )
    assert rel["accepted"] is True, rel

    # Stable first-turn Wi-Fi diagnosis: invented physical layout/environment
    # must be rejected, and Core has a useful bounded fallback if retries fail.
    wifi_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="stable_model_knowledge",
    )
    wifi_user = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    bad_wifi = "Sometimes being near a metal radiator helps more than a router."
    wifi_violations = find_user_diagnostic_overclaim_violations(
        user_input=wifi_user,
        draft=bad_wifi,
        core_answer_contract=wifi_contract,
        conversation=[],
    )
    assert any("physical/layout" in item for item in wifi_violations), wifi_violations
    wifi_fallback = build_stable_model_knowledge_fallback(wifi_user) or ""
    assert "same phone" in wifi_fallback.lower()
    assert "main wi-fi/mesh source" in wifi_fallback.lower()

    # Banter may use supplied physical state ("sitting") but may not invent a
    # chair, room, screen, clothing, food, etc. as if observed.
    physical = _unsupported_user_physical_object_claims(
        draft="At least the chair isn't judging you for wasting its potential.",
        grounding_text="im just sitting here bored as fuck",
    )
    assert physical, physical
    assert "chair" in physical[0]
    assert not _unsupported_user_physical_object_claims(
        draft="That chair sounds uncomfortable.",
        grounding_text="im sitting in this uncomfortable chair",
    )

    # Explicit media recommendation requests need an actual candidate, not just
    # a restatement of the desired vibe.
    rec_contract = AnswerContractRuntime(
        intent="recommendation_request",
        epistemic_mode="conversation",
    )
    vague = "Dark, brooding, lots of moral ambiguity. You need a narrative to lose yourself in."
    rec_violations = find_recommendation_completion_violations(
        user_input="what should i watch then?",
        draft=vague,
        core_answer_contract=rec_contract,
    )
    assert rec_violations, rec_violations
    assert not find_recommendation_completion_violations(
        user_input="what should i watch then?",
        draft="Watch Monster. It's dark and character-driven.",
        core_answer_contract=rec_contract,
    )
    fallback = build_recommendation_request_fallback(
        user_input="what should i watch then?",
        conversation=[
            {"role": "user", "content": "i want something dark and character driven tonight. definitely not a comedy"}
        ],
    )
    assert fallback.startswith("Watch Monster"), fallback

    print("Phase 11.6.6B27 final human acceptance hardening: PASS")


if __name__ == "__main__":
    run()
