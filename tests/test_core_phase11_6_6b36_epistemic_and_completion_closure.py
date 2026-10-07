from pathlib import Path
import json
import sys
import types

# Lightweight stubs for pure Core helper imports.
_ac = types.ModuleType("core.answer_contract_runtime")

def _coerce_contract(value):
    if value is None:
        return None
    text = str(value or "")
    intent = ""
    mode = ""
    allow_new = False
    metadata = {}
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("intent:"):
            intent = line.split(":", 1)[1].strip()
        elif low.startswith("epistemic mode:"):
            mode = line.split(":", 1)[1].strip()
        elif low.startswith("new unsupported factual claims allowed:"):
            allow_new = line.split(":", 1)[1].strip().lower() == "true"
    return types.SimpleNamespace(
        intent=intent,
        epistemic_mode=mode,
        allow_new_factual_claims=allow_new,
        metadata=metadata,
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
    find_deterministic_grounding_violations,
    find_python_mutable_default_semantics_violations,
    find_unknown_media_opinion_overreach_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.seriousness import find_consequential_tone_violations
from personality.conversation_policy import (
    classify_conversation_policy,
    find_conversation_policy_violations,
)
from research.public_factual_grounding import build_supported_current_lookup_fallback


def _contract(intent="casual_conversation", mode="conversation"):
    return (
        f"Intent: {intent}\n"
        f"Epistemic mode: {mode}\n"
        "New unsupported factual claims allowed: false\n"
    )


def run():
    # 1) Exact media lookup fallback must work with the actual text-envelope
    # packet representation produced by public_factual_research.
    packet = {
        "research_kind": "public_factual",
        "sources": [
            {
                "source_id": "S1",
                "title": (
                    "[September 9] Re:Zero – Starting Life in Another World "
                    "Season 4 Episode 16 ‘Subaru Natsuki’ Preview"
                ),
                "search_snippet": "September 9 preview",
                "content_excerpt": "Preview page.",
            }
        ],
    }
    packet_text = (
        "CORE PUBLIC FACTUAL EVIDENCE PACKET:\n"
        "Internal evidence follows.\n"
        + json.dumps(packet, ensure_ascii=False, indent=2)
    )
    media_answer = build_supported_current_lookup_fallback(
        packet_text,
        "what was that Natsuki Subaru episode from September 9 everyone was talking about?",
    )
    assert media_answer == (
        "The source-supported match for September 9 is Season 4, Episode 16."
    ), media_answer

    # 2) "what do you ACTUALLY think" must activate knowledge honesty, and an
    # unqualified pseudo-deep media take cannot masquerade as familiarity.
    opinion_user = (
        "what do you actually think of The Wandering Inn? dont just agree with me, "
        "i want your take"
    )
    policy = classify_conversation_policy(opinion_user)
    assert policy.get("knowledge_honesty") is True, policy

    fake_deep_take = (
        "The Wandering Inn is competent, but the world-building can drag. The pacing is uneven, "
        "the character development is where it shines, and the author spends three chapters "
        "explaining a kingdom before getting back to the plot."
    )
    opinion_bad = find_unknown_media_opinion_overreach_violations(
        opinion_user,
        fake_deep_take,
        conversation=[],
    )
    assert any("detailed work-specific familiarity" in item for item in opinion_bad), opinion_bad

    honest_take = (
        "I don't know enough about The Wandering Inn to give you a real take without "
        "making details up, and I won't pretend I've read it."
    )
    assert not find_unknown_media_opinion_overreach_violations(
        opinion_user,
        honest_take,
        conversation=[],
    )

    # 3) Punctuation must not let an invented physical observation escape.
    physical_bad = find_deterministic_grounding_violations(
        user_input="im just sitting here bored as fuck",
        draft=(
            "Sitting there staring at nothing? You're basically a human statue "
            "waiting for someone to trip over you."
        ),
        core_answer_contract=_contract("casual_conversation", "conversation"),
        conversation=[],
    )
    assert any("physical-action/state claim involving stare" in item for item in physical_bad), physical_bad

    # 4) Self-evaluation banter cannot invent a long-running relational history.
    dev_conversation = [
        {
            "role": "user",
            "content": "we've finally added developer diagnostics to you so i can see your routing and model metadata",
        }
    ]
    dev_bad = find_deterministic_grounding_violations(
        user_input="reckon you're finally becoming useful?",
        draft=(
            "Useful? I've been useful since the moment you stopped treating me like a toaster "
            "that occasionally recites poetry."
        ),
        core_answer_contract=_contract("share_opinion", "conversation"),
        conversation=dev_conversation,
    )
    assert any("relationship/conversation history" in item for item in dev_bad), dev_bad

    # 5) Mutable-default semantics are not an efficiency optimisation, even if
    # the draft later also mentions the correct once-at-definition rule.
    mutable_conversation = [
        {
            "role": "user",
            "content": "python question: `def f(x=[]): x.append(7); return x` then `print(f()); print(f())` -- what prints?",
        }
    ]
    mutable_bad = find_python_mutable_default_semantics_violations(
        "WHAT why didn't python make a new list every call 😭",
        (
            "Python doesn't create a new list for the default argument because that would be "
            "inefficient and unnecessary. Default arguments are evaluated once at function definition time."
        ),
        conversation=mutable_conversation,
    )
    assert any("efficiency/necessity" in item for item in mutable_bad), mutable_bad

    # 6) The first Wi-Fi diagnostic step must actually isolate the same wireless
    # device near the source rather than merely ask about the wired console's room.
    wifi_user = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_bad = find_user_diagnostic_overclaim_violations(
        wifi_user,
        (
            "Let's check if your phone is actually in the same room as the console or "
            "just hiding upstairs pretending to be part of the network."
        ),
        _contract("factual_question", "stable_model_knowledge"),
        conversation=[],
    )
    assert any("same-device near-source" in item for item in wifi_bad), wifi_bad
    wifi_fallback = build_diagnostic_reasoning_fallback(wifi_user, conversation=[])
    assert "same phone" in wifi_fallback.lower() and "main" in wifi_fallback.lower(), wifi_fallback

    # 7) Consequential advice must not invent severity/savings context as banter.
    serious_bad = find_consequential_tone_violations(
        "Oof, that is not a good start. I hope it's not some massive sum you've been "
        "holding onto for a rainy day. Contact your bank immediately."
    )
    assert serious_bad, serious_bad

    # 8) A visibly truncated social sentence must be retried even if it passes
    # a mechanical minimum-character benchmark.
    incomplete = find_conversation_policy_violations(
        "Yeah, that really sucks. Nothing makes"
    )
    assert any("incomplete/truncated" in item for item in incomplete), incomplete
    assert not any(
        "incomplete/truncated" in item
        for item in find_conversation_policy_violations("Yeah, that really sucks.")
    )

    print("Phase 11.6.6B36 epistemic and completion closure: PASS")


if __name__ == "__main__":
    run()
