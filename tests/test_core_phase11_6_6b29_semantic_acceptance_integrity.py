from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.claim_grounding import (
    _unsupported_mairon_perception_claims,
    build_stable_model_knowledge_fallback,
    find_tcp_udp_semantics_violations,
)
from core.seriousness import find_consequential_role_violations

# Keep deterministic relevance tests independent of optional connector deps.
_tool_registry_stub = types.ModuleType("tools.tool_registry")
_tool_registry_stub.execute_tool = lambda *args, **kwargs: None
sys.modules.setdefault("tools.tool_registry", _tool_registry_stub)

from research.public_factual_research import assess_public_source_relevance


def run():
    # Consequential actor-role checks must survive curly apostrophes produced by
    # natural model text. This exact punctuation previously bypassed B27.
    bank_user = "i think i just transferred money to the wrong bank account. what should i do?"
    curly_bad = (
        "Check the transaction and call your bank. Don’t touch or move any money "
        "in your accounts while you sort it out."
    )
    violations = find_consequential_role_violations(
        user_input=bank_user,
        draft=curly_bad,
        domain="financial",
    )
    assert any("mistaken sender" in item for item in violations), violations

    # Salvaged grounded-opinion text must be rechecked for answer adequacy. The
    # provider's salvage validator must call the public-opinion completion guard.
    provider_source = (SRC / "ai" / "ollama_provider.py").read_text(encoding="utf-8")
    salvage_start = provider_source.index("def _validate_salvaged_research_draft")
    salvage_end = provider_source.index("if grounded_research_evidence:", salvage_start)
    salvage_block = provider_source[salvage_start:salvage_end]
    assert "find_grounded_opinion_response_violations" in salvage_block

    # If public search fails for a stable concept, the provider may use Core's
    # bounded stable fallback. It must not use this as a substitute for live/current facts.
    failure_marker = "Required public-source lanes may not fall back to model memory"
    failure_start = provider_source.index(failure_marker)
    failure_end = provider_source.index("grounded_research_evidence =", failure_start)
    failure_block = provider_source[failure_start:failure_end]
    assert "build_stable_model_knowledge_fallback" in failure_block

    # VRR acronym collisions must not accept unrelated organisations/cookie pages.
    bad_vrr = {
        "title": "VRR Life Sciences Management Team | Org Chart",
        "url": "https://rocketreach.co/vrr-life-sciences-management_b5",
        "source_host": "rocketreach.co",
        "read_success": True,
        "read_result": {
            "success": True,
            "content": "Privacy policy, cookies, people search and company contact information.",
        },
    }
    rel = assess_public_source_relevance(
        bad_vrr,
        query="why does my monitor sometimes flicker when VRR is on",
        research_identity="why does my monitor sometimes flicker when VRR is on",
        include_read_content=True,
    )
    assert rel["accepted"] is False, rel
    assert any("display/variable-refresh context" in reason for reason in rel["reasons"]), rel

    good_vrr = {
        "title": "Variable Refresh Rate (VRR) flicker on displays",
        "url": "https://example.org/display-vrr-flicker",
        "source_host": "example.org",
        "read_success": True,
        "read_result": {
            "success": True,
            "content": "VRR variable refresh rate can expose display luminance or gamma flicker when frame rate changes.",
        },
    }
    rel = assess_public_source_relevance(
        good_vrr,
        query="why does my monitor sometimes flicker when VRR is on",
        research_identity="why does my monitor sometimes flicker when VRR is on",
        include_read_content=True,
    )
    assert rel["accepted"] is True, rel

    # Current driver questions require actual release/version evidence rather
    # than a nearby vendor story about some unrelated feature rollout.
    bad_driver = {
        "title": "NVIDIA RTX Gets Shader Delivery After AMD Performance Cut",
        "url": "https://example.com/nvidia-shader-delivery",
        "source_host": "example.com",
        "read_success": True,
        "read_result": {
            "success": True,
            "content": "NVIDIA is rolling out advanced shader delivery for RTX systems. Users may need compatible software.",
        },
    }
    rel = assess_public_source_relevance(
        bad_driver,
        query="is there a new NVIDIA driver out right now",
        research_identity="is there a new NVIDIA driver out right now",
        include_read_content=True,
    )
    assert rel["accepted"] is False, rel
    assert any("current driver release" in reason for reason in rel["reasons"]), rel

    good_driver = {
        "title": "NVIDIA releases GeForce Game Ready Driver 590.12 WHQL",
        "url": "https://example.org/nvidia-driver-590-12",
        "source_host": "example.org",
        "read_success": True,
        "read_result": {
            "success": True,
            "content": "NVIDIA released GeForce Game Ready Driver 590.12 WHQL today and it is available now.",
        },
    }
    rel = assess_public_source_relevance(
        good_driver,
        query="is there a new NVIDIA driver out right now",
        research_identity="is there a new NVIDIA driver out right now",
        include_read_content=True,
    )
    assert rel["accepted"] is True, rel

    # Text-only Mairon cannot claim it is literally watching an invented cursor.
    perception = _unsupported_mairon_perception_claims(
        "I'm just watching the cursor blink in solidarity with your soul."
    )
    assert perception, perception

    # Stable TCP/UDP role polarity must be explicit and correct.
    network_user = "my mate swears TCP is connectionless and UDP needs a handshake. can u check me"
    bad_network = (
        "TCP absolutely requires a handshake; it's the whole point of the protocol. "
        "That's connectionless. It just sends packets and hopes for the best."
    )
    violations = find_tcp_udp_semantics_violations(
        user_input=network_user,
        draft=bad_network,
    )
    assert violations, violations

    good_network = (
        "TCP is connection-oriented and uses a three-way handshake. "
        "UDP is connectionless and does not use a connection-establishment handshake."
    )
    assert not find_tcp_udp_semantics_violations(
        user_input=network_user,
        draft=good_network,
    )
    fallback = build_stable_model_knowledge_fallback(network_user) or ""
    assert "TCP is connection-oriented" in fallback
    assert "UDP is connectionless" in fallback

    print("Phase 11.6.6B29 semantic acceptance integrity: PASS")


if __name__ == "__main__":
    run()
