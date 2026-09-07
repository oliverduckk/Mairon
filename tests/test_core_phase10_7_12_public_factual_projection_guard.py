import json
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Keep this regression independent from private Google connector imports.
fake_registry = types.ModuleType("tools.tool_registry")


def _unpatched_execute_tool(*args, **kwargs):
    raise AssertionError("public factual research used an unpatched execute_tool")


fake_registry.execute_tool = _unpatched_execute_tool
sys.modules.setdefault("tools.tool_registry", fake_registry)

from core.answer_contract import build_answer_contract
from core.epistemic_router import route_epistemic_authority
from core.turn_state import TurnState
from research import public_factual_research
from research.public_factual_grounding import (
    PublicFactualVerificationResult,
    verify_public_factual_draft,
)


class _Message:
    def __init__(self, content):
        self.content = content


class _Result:
    def __init__(self, content):
        self.message = _Message(content)


class _VerifierClient:
    def __init__(self, payload):
        self.payload = payload
        self.last_kwargs = None

    def chat(self, **kwargs):
        self.last_kwargs = kwargs
        return _Result(json.dumps(self.payload))


def _factual_turn(text):
    return TurnState(
        raw_text=text,
        speech_act="question",
        intent="factual_question",
        factuality="requires_epistemic_routing",
        should_continue_conversation=True,
    )


def run():
    # --------------------------------------------------
    # 1. Public research records whether Oliver actually asked for a forecast.
    # --------------------------------------------------
    tool_calls = []

    def fake_execute_tool(name, arguments):
        tool_calls.append((name, dict(arguments)))

        if name == "web_search":
            return {
                "success": True,
                "results": [
                    {
                        "title": "Example leadership",
                        "url": "https://example.org/leadership",
                        "content": "Example leadership page",
                        "score": 0.99,
                    }
                ],
            }

        if name == "web_read":
            return {
                "success": True,
                "url": arguments["url"],
                "content": "Jordan Example is the current chief executive.",
            }

        raise AssertionError((name, arguments))

    original_execute_tool = public_factual_research.execute_tool
    public_factual_research.execute_tool = fake_execute_tool

    try:
        current_result = public_factual_research.gather_public_factual_research(
            "Who is the current chief executive of Example Systems?",
            max_reads=1,
        )
        forecast_result = public_factual_research.gather_public_factual_research(
            "Will the chief executive of Example Systems remain in the role next year?",
            max_reads=1,
        )
    finally:
        public_factual_research.execute_tool = original_execute_tool

    assert current_result["forecast_requested"] is False
    assert forecast_result["forecast_requested"] is True

    current_packet = public_factual_research.build_internal_public_factual_packet(
        current_result
    )
    forecast_packet = public_factual_research.build_internal_public_factual_packet(
        forecast_result
    )

    assert '"forecast_requested": false' in current_packet
    assert '"forecast_requested": true' in forecast_packet
    assert "Do not extrapolate" in current_packet

    # --------------------------------------------------
    # 2. Answer Contract explicitly forbids unsolicited future extrapolation.
    # --------------------------------------------------
    turn = _factual_turn(
        "Who is the current chief executive of Example Systems?"
    )
    route = route_epistemic_authority(turn)
    contract = build_answer_contract(turn=turn, route=route)

    assert route.mode == "public_source_verified"
    assert any(
        "Do not extrapolate a verified current fact into a prediction" in item
        for item in contract.forbidden_behaviours
    )
    assert any(
        "future outcomes into personality filler" in item
        for item in contract.forbidden_behaviours
    )

    # --------------------------------------------------
    # 3. Deterministic projection guard overrides an over-permissive LLM verifier.
    # --------------------------------------------------
    evidence_packet = (
        "CORE PUBLIC FACTUAL EVIDENCE PACKET:\n"
        + json.dumps({
            "research_kind": "public_factual",
            "research_query": "Who is the current chief executive of Example Systems?",
            "freshness_required": True,
            "forecast_requested": False,
            "sources": [
                {
                    "source_id": "S1",
                    "title": "Leadership",
                    "url": "https://example.org/leadership",
                    "source_quality": "general_web",
                    "content_excerpt": "Jordan Example is the current chief executive.",
                }
            ],
        })
    )

    # Simulate Qwen incorrectly claiming BOTH sentences are supported. Core's
    # deterministic future-projection guard must still reject the second one.
    client = _VerifierClient({
        "supported": True,
        "unsupported_claims": [],
        "sentence_assessments": [
            {"index": 1, "supported": True},
            {"index": 2, "supported": True},
        ],
    })

    verification = verify_public_factual_draft(
        client=client,
        model="qwen3.5:9b",
        user_input="Who is the current chief executive of Example Systems?",
        draft=(
            "It's Jordan Example. "
            "They're not going anywhere anytime soon."
        ),
        research_evidence=evidence_packet,
    )

    assert isinstance(verification, PublicFactualVerificationResult)
    assert verification == [
        "unsolicited public factual future projection: "
        "They're not going anywhere anytime soon."
    ]
    assert verification.accepted_sentences == [
        "It's Jordan Example."
    ]

    # --------------------------------------------------
    # 4. If Oliver explicitly asks for a forecast, this deterministic guard
    #    does not pre-empt the evidence verifier.
    # --------------------------------------------------
    forecast_evidence_packet = (
        "CORE PUBLIC FACTUAL EVIDENCE PACKET:\n"
        + json.dumps({
            "research_kind": "public_factual",
            "research_query": "Will Jordan Example remain next year?",
            "freshness_required": True,
            "forecast_requested": True,
            "sources": [
                {
                    "source_id": "S1",
                    "title": "Leadership announcement",
                    "url": "https://example.org/announcement",
                    "source_quality": "general_web",
                    "content_excerpt": "Jordan Example is contracted to remain chief executive through next year.",
                }
            ],
        })
    )

    forecast_client = _VerifierClient({
        "supported": True,
        "unsupported_claims": [],
        "sentence_assessments": [
            {"index": 1, "supported": True},
        ],
    })

    forecast_verification = verify_public_factual_draft(
        client=forecast_client,
        model="qwen3.5:9b",
        user_input="Will Jordan Example remain chief executive next year?",
        draft="Jordan Example is expected to remain chief executive next year.",
        research_evidence=forecast_evidence_packet,
    )

    assert forecast_verification == []
    assert forecast_verification.accepted_sentences == [
        "Jordan Example is expected to remain chief executive next year."
    ]

    # The semantic verifier prompt itself also states the future-inference rule.
    system_prompt = client.last_kwargs["messages"][0]["content"]
    assert "future continuity" in system_prompt
    assert "not going anywhere" in system_prompt

    # Production remains entity-generic.
    production_text = "\n".join([
        (SRC_DIR / "research" / "public_factual_research.py").read_text(encoding="utf-8"),
        (SRC_DIR / "research" / "public_factual_grounding.py").read_text(encoding="utf-8"),
        (SRC_DIR / "core" / "answer_contract.py").read_text(encoding="utf-8"),
    ]).lower()

    for concrete_name in (
        "jordan example",
        "example systems",
    ):
        assert concrete_name not in production_text

    print("Mairon Phase 10.7.12 public factual projection guard tests: PASS")


if __name__ == "__main__":
    run()
