from pathlib import Path
import sys
import types

# Lightweight stubs so the pure Core helpers can be tested without app/runtime deps.
_ac = types.ModuleType("core.answer_contract_runtime")
def _coerce_contract(value):
    if value is None:
        return None
    text = str(value or "")
    intent = ""
    mode = ""
    for line in text.splitlines():
        if line.lower().startswith("intent:"):
            intent = line.split(":", 1)[1].strip()
        elif line.lower().startswith("epistemic mode:"):
            mode = line.split(":", 1)[1].strip()
    return types.SimpleNamespace(
        intent=intent,
        epistemic_mode=mode,
        allow_new_factual_claims=True,
        metadata={},
    )
_ac.coerce_answer_contract_runtime = _coerce_contract
_ac.render_answer_contract = lambda value: str(value or "")
sys.modules.setdefault("core.answer_contract_runtime", _ac)

_sl = types.ModuleType("core.source_lock")
_sl.build_draft_source_lock_diagnostics = lambda *args, **kwargs: {}
_sl.build_source_lock_instruction = lambda *args, **kwargs: ""
_sl.find_structural_source_lock_violations = lambda *args, **kwargs: []
_sl.recommended_source_lock_prior_window = lambda *args, **kwargs: 4
sys.modules.setdefault("core.source_lock", _sl)

ROOT = Path(__file__).resolve().parents[0]
repo_src = Path(__file__).resolve().parents[1] / "src"
SRC = repo_src if repo_src.exists() else ROOT
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.claim_grounding import (
    build_diagnostic_reasoning_fallback,
    build_stable_model_knowledge_fallback,
    find_recommendation_completion_violations,
    find_scaler_leakage_contradiction_violations,
    find_tcp_udp_semantics_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.seriousness import (
    build_consequential_advice_instruction,
    find_consequential_role_violations,
)
from research.public_factual_grounding import (
    build_failed_public_advice_fallback,
    find_grounded_opinion_response_violations,
)


def _contract(intent="factual_question", mode="stable_model_knowledge"):
    return (
        f"Intent: {intent}\n"
        f"Epistemic mode: {mode}\n"
        "Authority: local_model_knowledge\n"
    )


def run():
    # 1) Consequential financial advice must preserve mistaken-sender direction
    # and make the sending bank/provider the first recovery contact.
    bank_user = "i think i just transferred money to the wrong bank account. what should i do?"
    bad_bank = (
        "Contact the recipient immediately and try to get them to send it back. "
        "If they won't, contact your bank. Be careful not to move any of the funds yourself."
    )
    bank_bad = find_consequential_role_violations(
        bank_user,
        bad_bank,
        domain="financial",
    )
    assert any("sender to recipient" in item or "contact the recipient before" in item for item in bank_bad), bank_bad

    good_bank = (
        "Contact your bank or payment provider immediately, tell them you sent a transfer "
        "to the wrong account, and ask for its documented mistaken-payment/recovery process. "
        "I can't promise it can be reversed."
    )
    assert not find_consequential_role_violations(
        bank_user,
        good_bank,
        domain="financial",
    )
    instruction = build_consequential_advice_instruction(
        domain="financial",
        user_input=bank_user,
    )
    assert "sending bank/payment provider the first recovery contact" in instruction
    fallback = build_failed_public_advice_fallback(
        domain="financial",
        user_input=bank_user,
    )
    assert "contact the bank or payment provider" in fallback.lower(), fallback

    # 2) Explicit TCP-vs-UDP correction must name BOTH protocol roles clearly.
    tcp_user = "my mate swears TCP is connectionless and UDP needs a handshake. that sounds cooked but can u check me"
    ambiguous_tcp = (
        "TCP absolutely requires a handshake; it's the whole point of being reliable. "
        "That's the one skipping the pleasantries and just sending data."
    )
    tcp_bad = find_tcp_udp_semantics_violations(
        user_input=tcp_user,
        draft=ambiguous_tcp,
    )
    assert any("UDP" in item for item in tcp_bad), tcp_bad

    good_tcp = (
        "TCP is connection-oriented and establishes a connection with a three-way handshake. "
        "UDP is connectionless and does not use a connection-establishment handshake."
    )
    assert not find_tcp_udp_semantics_violations(
        user_input=tcp_user,
        draft=good_tcp,
    )
    assert "UDP is connectionless" in build_stable_model_knowledge_fallback(tcp_user)

    # 3) A concrete data-leakage example must itself contain a leakage mechanism.
    leak_user = (
        "bro can u explain data leakage in machine learning like i actually need "
        "to understand it, not just paste a definition"
    )
    bad_leak = (
        "Data leakage happens when the model learns information unavailable at prediction time. "
        "For example, if you're predicting house prices and include sale date as a feature, "
        "the model might memorize the price for each date. That's leakage because you don't "
        "know the future sale price when evaluating a house."
    )
    leak_bad = find_scaler_leakage_contradiction_violations(
        leak_user,
        bad_leak,
        conversation=[],
    )
    assert any("concrete example" in item for item in leak_bad), leak_bad

    good_leak = (
        "Data leakage is when information that should be unavailable during training or evaluation "
        "gets into model building. For example, fitting preprocessing on held-out test data lets "
        "test-set statistics influence training, making evaluation too optimistic."
    )
    assert not find_scaler_leakage_contradiction_violations(
        leak_user,
        good_leak,
        conversation=[],
    ), find_scaler_leakage_contradiction_violations(leak_user, good_leak, conversation=[])
    assert "held-out test/validation" in build_stable_model_knowledge_fallback(leak_user)

    # 4) Dark-scene correlation is compatible with VRR but is not strong proof.
    vrr_user = "could it still be VRR if the flicker only happens in dark scenes? or am i guessing"
    bad_vrr = (
        "It could absolutely still be VRR. Dark scenes are a strong clue pointing toward "
        "variable refresh rate being the culprit. It's a classic symptom of VRR issues."
    )
    vrr_bad = find_user_diagnostic_overclaim_violations(
        vrr_user,
        bad_vrr,
        _contract(),
        conversation=[],
    )
    assert any("strong/diagnostic evidence" in item for item in vrr_bad), vrr_bad
    vrr_fallback = build_diagnostic_reasoning_fallback(vrr_user, conversation=[])
    assert "does not prove VRR is the root cause" in vrr_fallback, vrr_fallback

    # 5) Evidence-backed opinion answers must actually make the requested judgement.
    opinion_user = "do you think she handled it well though?"
    recap_only = "She announced Yamauchi was out before anyone could argue the point."
    opinion_bad = find_grounded_opinion_response_violations(opinion_user, recap_only)
    assert any("evaluative judgement" in item for item in opinion_bad), opinion_bad
    judgement = (
        "No, I don't think she handled it well. The source supports that she announced "
        "the decision publicly before the class had much room to respond."
    )
    assert not find_grounded_opinion_response_violations(opinion_user, judgement)

    # 6) A recommendation cannot refer to an unnamed candidate before naming another title.
    rec_user = "what should i watch then?"
    rec_contract = _contract("recommendation_request", "conversation")
    unresolved = (
        'It got brutal in its second season but has real heft to it. '
        'Or if you want old-school gritty, "Chinatown" is strong.'
    )
    rec_bad = find_recommendation_completion_violations(
        rec_user,
        unresolved,
        rec_contract,
    )
    assert any("unresolved candidate pronoun" in item for item in rec_bad), rec_bad

    good_rec = 'Watch "Monster" if you want something dark and character-driven without comedy.'
    assert not find_recommendation_completion_violations(
        rec_user,
        good_rec,
        rec_contract,
    )

    print("Phase 11.6.6B35 human semantic acceptance closure: PASS")


if __name__ == "__main__":
    run()
