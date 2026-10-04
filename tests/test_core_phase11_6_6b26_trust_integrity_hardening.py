import json
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


fake_registry = types.ModuleType("tools.tool_registry")
fake_registry.execute_tool = lambda *args, **kwargs: None
sys.modules["tools.tool_registry"] = fake_registry


from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_deterministic_grounding_violations,
    find_question_echo_violations,
)
from core.seriousness import (
    build_consequential_advice_instruction,
    find_consequential_role_violations,
    find_consequential_tone_violations,
    infer_consequential_actor_role,
)
import research.public_factual_research as public_research
from research.public_factual_grounding import (
    _deterministic_exact_version_support_indexes,
    build_failed_public_advice_fallback,
)


def _result(title, url, snippet=""):
    return {
        "title": title,
        "url": url,
        "content": snippet,
        "score": 1.0,
    }


def _read(content):
    return {
        "success": True,
        "content": content,
    }


def run():
    # --------------------------------------------------
    # 1. Consequential financial advice preserves the actor direction Oliver
    #    explicitly supplied. A mistaken sender must not become the recipient.
    # --------------------------------------------------
    sender_prompt = (
        "i think i just transferred money to the wrong bank account. "
        "what should i do?"
    )

    assert infer_consequential_actor_role(
        sender_prompt,
        domain="financial",
    ) == "mistaken_sender"

    role_violations = find_consequential_role_violations(
        user_input=sender_prompt,
        draft=(
            "If it already landed in the wrong account, don't spend or move "
            "the money while the bank investigates."
        ),
        domain="financial",
    )
    assert role_violations, role_violations

    assert not find_consequential_role_violations(
        user_input=sender_prompt,
        draft=(
            "Contact the bank or payment provider you sent it through and tell "
            "them you sent the transfer to the wrong account."
        ),
        domain="financial",
    )

    instruction = build_consequential_advice_instruction(
        domain="financial",
        user_input=sender_prompt,
    )
    assert "SENDER" in instruction
    assert "Do not tell him not to spend" in instruction

    fallback = build_failed_public_advice_fallback(
        domain="financial",
        user_input=sender_prompt,
    )
    assert "sender" in fallback.lower()
    assert "bank or payment provider you sent it through" in fallback.lower()
    assert "don't spend" not in fallback.lower()

    assert find_consequential_tone_violations(
        "Pull your head out of the panic and let's fix this."
    )

    # --------------------------------------------------
    # 2. Grounded banter may use the supplied physical action (sitting), but
    #    may not invent a second observable action (staring/looking).
    # --------------------------------------------------
    social_contract = AnswerContractRuntime(
        intent="casual_conversation",
        authority="live_conversation",
        epistemic_mode="social_conversation",
        allow_new_factual_claims=False,
    )

    invented_stare = find_deterministic_grounding_violations(
        user_input="im just sitting here bored as fuck",
        draft=(
            "Sitting there staring at nothing, you're basically a human statue."
        ),
        core_answer_contract=social_contract,
        conversation=[],
    )
    assert any(
        "unsupported Oliver physical-action/state claim involving stare" in item
        for item in invented_stare
    ), invented_stare

    supported_sit = find_deterministic_grounding_violations(
        user_input="im just sitting here bored as fuck",
        draft="You're sitting there bored as fuck.",
        core_answer_contract=social_contract,
        conversation=[],
    )
    assert not any(
        "physical-action/state claim involving sit" in item
        for item in supported_sit
    ), supported_sit

    # A factual answer cannot simply repeat the user's question back to them.
    echo = find_question_echo_violations(
        user_input=(
            "my wired console is getting 600 Mbps but my phone upstairs barely "
            "hits 20. bruh don't tell me to buy a new router straight away, "
            "what would you test first?"
        ),
        draft=(
            "Bruh, don't tell me to buy a new router straight away, what would "
            "you test first?"
        ),
    )
    assert echo, echo
    assert not find_question_echo_violations(
        user_input="why does TCP need a handshake?",
        draft="TCP uses the handshake to establish shared connection state before data flows.",
    )

    # --------------------------------------------------
    # 3. Foreground factual/advice/opinion research can require evidence with
    #    real source authority. A readable user-fiction page is not enough.
    # --------------------------------------------------
    original_execute = public_research.execute_tool

    search_result = {
        "success": True,
        "results": [
            _result(
                "COTE fan reaction to the class vote",
                "https://www.wattpad.com/story/example",
                "Horikita COTE class vote fan reaction.",
            ),
            _result(
                "Classroom of the Elite class vote analysis",
                "https://editorial.example/cote-class-vote",
                "Horikita COTE class vote analysis.",
            ),
        ],
    }

    reads = {
        "https://www.wattpad.com/story/example": _read(
            "Horikita and the COTE class vote appear in this fan-written story."
        ),
        "https://editorial.example/cote-class-vote": _read(
            "This editorial discusses Horikita's handling of the COTE class vote."
        ),
    }

    def fake_execute(name, arguments):
        if name == "web_search":
            return search_result
        if name == "web_read":
            return reads[arguments["url"]]
        raise AssertionError(name)

    public_research.execute_tool = fake_execute

    try:
        result = public_research.gather_public_factual_research(
            "Horikita class vote in COTE",
            max_reads=2,
            require_query_resolution=True,
            require_quality_evidence=True,
        )
    finally:
        public_research.execute_tool = original_execute

    assert result["success"] is True, result
    assert result["quality_evidence_required"] is True, result

    accepted = [
        source
        for source in result["sources"]
        if source.get("accepted_as_evidence")
    ]
    assert [item["url"] for item in accepted] == [
        "https://editorial.example/cote-class-vote"
    ], accepted

    rejected = [
        reason
        for item in result["rejected_sources"]
        for reason in item.get("reasons", [])
    ]
    assert any(
        "insufficient_source_authority:weak_community_or_social" in item
        for item in rejected
    ), rejected

    # --------------------------------------------------
    # 4. Exact current-version claims cannot promote a URL/page record ID into
    #    a factual version number when source prose never labels it that way.
    # --------------------------------------------------
    url_id_packet = {
        "sources": [{
            "title": "NVIDIA Drivers Details",
            "url": "https://www.nvidia.com/download/driverResults.aspx/280034/en-us/",
            "search_snippet": "NVIDIA driver download details.",
            "content_excerpt": "Game Ready Driver download information and release notes.",
        }],
    }

    bad_indexes = _deterministic_exact_version_support_indexes(
        url_id_packet,
        ["The latest driver version 280034 is available."],
    )
    assert bad_indexes == {1}, bad_indexes

    supported_version_packet = {
        "sources": [{
            "title": "NVIDIA Driver 581.42",
            "url": "https://example.com/driver/12345",
            "search_snippet": "GeForce Game Ready Driver version 581.42.",
            "content_excerpt": "Driver version 581.42 was released for GeForce products.",
        }],
    }

    assert _deterministic_exact_version_support_indexes(
        supported_version_packet,
        ["The driver version is 581.42."],
    ) == set()

    # --------------------------------------------------
    # 5. Integration guards: no-evidence public lanes fail closed BEFORE model
    #    generation, foreground research requires quality evidence, and both
    #    normal/salvaged consequential drafts receive role validation.
    # --------------------------------------------------
    provider_source = (
        PROJECT_ROOT / "src" / "ai" / "ollama_provider.py"
    ).read_text(encoding="utf-8")

    assert "require_quality_evidence=True" in provider_source
    assert "Required public evidence unavailable" in provider_source
    assert "find_consequential_role_violations" in provider_source
    assert "find_question_echo_violations" in provider_source
    assert provider_source.count("find_consequential_role_violations(") >= 2
    assert "user_input=user_input" in provider_source

    print("PASS: B26 trust integrity hardening")


if __name__ == "__main__":
    run()
