import json
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# public_factual_research needs only execute_tool at import time. Keep this
# regression independent from Gmail/Calendar private-service dependencies.
fake_registry = types.ModuleType("tools.tool_registry")

def _unpatched_execute_tool(*args, **kwargs):
    raise AssertionError("public factual research used an unpatched execute_tool")

fake_registry.execute_tool = _unpatched_execute_tool
sys.modules.setdefault("tools.tool_registry", fake_registry)

from core.answer_contract import build_answer_contract
from core.epistemic_router import (
    classify_factual_authority,
    factual_question_requires_live_data,
    route_epistemic_authority,
)
from core.turn_state import TurnState
from research import public_factual_research
from research.public_factual_grounding import (
    PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA,
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
    # 0. Existing stronger Core authorities keep precedence.
    # --------------------------------------------------
    arithmetic_turn = TurnState(
        raw_text="what is 2 + 2?",
        speech_act="question",
        intent="calculate_arithmetic",
        preferred_authority="core_arithmetic",
    )

    arithmetic_route = route_epistemic_authority(
        arithmetic_turn
    )

    assert arithmetic_route.authority == "core_arithmetic"
    assert arithmetic_route.mode == "deterministic_calculation"
    assert arithmetic_route.allow_model_memory is False

    email_read_turn = TurnState(
        raw_text="what does the current email say?",
        speech_act="question",
        intent="email_read",
        preferred_authority="gmail",
        requires_private_data=True,
        requires_live_data=True,
        should_use_tools=True,
    )

    email_read_route = route_epistemic_authority(
        email_read_turn
    )

    assert email_read_route.authority == "gmail"
    assert email_read_route.mode == "tool_verified"
    assert email_read_route.private_data_required is True

    # --------------------------------------------------
    # 1. Durable explanations stay local.
    # --------------------------------------------------
    stable_questions = (
        "Explain how DNS works.",
        "How does TLS establish a secure connection?",
        "What is photosynthesis?",
        "What is Ohm's law?",
        "Compare TCP and UDP.",
    )

    for text in stable_questions:
        assert classify_factual_authority(text) == "stable_model_knowledge", text

        route = route_epistemic_authority(_factual_turn(text))
        assert route.authority == "local_model_knowledge"
        assert route.mode == "stable_model_knowledge"
        assert route.verification_required is False
        assert route.allow_model_memory is True
        assert route.live_data_required is False

        contract = build_answer_contract(
            turn=_factual_turn(text),
            route=route,
        )

        assert contract.allow_new_factual_claims is True

    # --------------------------------------------------
    # 2. Specific/changing/explicitly verified facts require public evidence.
    # --------------------------------------------------
    public_questions = (
        "Who is the chief executive of Example Dynamics?",
        "How much does the ExampleNet home plan cost in Australia?",
        "What happened during the Example Mission accident?",
        "What is the latest ExampleGPU driver version?",
        "Can you look up whether ExampleOS 14 has been released?",
        "Is Example Stadium open?",
    )

    for text in public_questions:
        assert classify_factual_authority(text) == "public_source_verified", text

        route = route_epistemic_authority(_factual_turn(text))
        assert route.authority == "public_web"
        assert route.mode == "public_source_verified"
        assert route.verification_required is True
        assert route.allow_model_memory is False

        contract = build_answer_contract(
            turn=_factual_turn(text),
            route=route,
        )

        assert contract.allow_new_factual_claims is False

    assert factual_question_requires_live_data(
        "What is the latest ExampleGPU driver version?"
    ) is True

    assert factual_question_requires_live_data(
        "What happened during the Example Mission accident?"
    ) is False

    # --------------------------------------------------
    # 3. Public research preserves relevance + independent-source backfill.
    # --------------------------------------------------
    tool_calls = []

    def fake_execute_tool(name, arguments):
        tool_calls.append((name, dict(arguments)))

        if name == "web_search":
            return {
                "success": True,
                "results": [
                    {
                        "title": "Example answer A",
                        "url": "https://alpha.example/fact",
                        "content": "Primary result",
                        "score": 0.99,
                    },
                    {
                        "title": "Example answer A duplicate host",
                        "url": "https://alpha.example/other",
                        "content": "Same host",
                        "score": 0.98,
                    },
                    {
                        "title": "Example answer B",
                        "url": "https://beta.example/reference",
                        "content": "Independent source",
                        "score": 0.94,
                    },
                    {
                        "title": "Example answer C",
                        "url": "https://gamma.example/reference",
                        "content": "Backfill source",
                        "score": 0.90,
                    },
                ],
            }

        if name == "web_read":
            url = arguments["url"]

            if "alpha.example/fact" in url:
                return {
                    "success": True,
                    "url": url,
                    "content": "Example WidgetFlux is a fictional test service.",
                }

            if "beta.example" in url:
                return {
                    "success": False,
                    "message": "temporary extraction failure",
                }

            if "gamma.example" in url:
                return {
                    "success": True,
                    "url": url,
                    "content": "The fictional test service was launched for regression testing.",
                }

        raise AssertionError((name, arguments))

    original_execute_tool = public_factual_research.execute_tool
    public_factual_research.execute_tool = fake_execute_tool

    try:
        result = public_factual_research.gather_public_factual_research(
            "Who operates WidgetFlux?",
            max_reads=2,
        )
    finally:
        public_factual_research.execute_tool = original_execute_tool

    assert result["success"] is True
    assert result["readable_source_count"] == 2
    assert result["read_attempt_count"] == 3

    read_urls = [
        args["url"]
        for name, args in tool_calls
        if name == "web_read"
    ]

    assert read_urls == [
        "https://alpha.example/fact",
        "https://beta.example/reference",
        "https://gamma.example/reference",
    ]

    packet = public_factual_research.build_internal_public_factual_packet(result)
    assert "CORE PUBLIC FACTUAL EVIDENCE PACKET" in packet
    assert "alpha.example" in packet
    assert "gamma.example" in packet
    assert "beta.example" not in packet

    # Current questions use a bounded recent search window rather than an
    # evergreen lookup.
    tool_calls.clear()
    public_factual_research.execute_tool = fake_execute_tool

    try:
        latest_result = public_factual_research.gather_public_factual_research(
            "What is the latest WidgetFlux release?",
            max_reads=1,
        )
    finally:
        public_factual_research.execute_tool = original_execute_tool

    search_call = next(
        args
        for name, args in tool_calls
        if name == "web_search"
    )
    # "latest" requires current-state verification, but Core does not force a
    # narrow publication-date filter that could hide an authoritative static page.
    assert search_call["time_range"] == "none"
    assert latest_result["freshness_sensitive"] is True

    # --------------------------------------------------
    # 4. Generic public verifier is schema-constrained and sentence-aware.
    # --------------------------------------------------
    evidence_packet = json.dumps({
        "research_kind": "public_factual",
        "research_query": "Who operates WidgetFlux?",
        "freshness_window": None,
        "sources": [
            {
                "source_id": "S1",
                "title": "Reference",
                "url": "https://alpha.example/fact",
                "source_quality": "general_web",
                "content_excerpt": "WidgetFlux is operated by Example Dynamics.",
            }
        ],
    })

    client = _VerifierClient({
        "supported": False,
        "unsupported_claims": ["invented launch year"],
        "sentence_assessments": [
            {"index": 1, "supported": True},
            {"index": 2, "supported": False},
        ],
    })

    verification = verify_public_factual_draft(
        client=client,
        model="qwen3.5:9b",
        user_input="Who operates WidgetFlux?",
        draft=(
            "WidgetFlux is operated by Example Dynamics. "
            "It launched in 2019."
        ),
        research_evidence=evidence_packet,
    )

    assert isinstance(verification, PublicFactualVerificationResult)
    assert verification == [
        "unsupported public factual claim: invented launch year"
    ]
    assert verification.accepted_sentences == [
        "WidgetFlux is operated by Example Dynamics."
    ]
    assert client.last_kwargs["format"] == PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA
    assert client.last_kwargs["options"]["temperature"] == 0
    assert client.last_kwargs.get("think") is False

    # --------------------------------------------------
    # 5. Provider integration stays generic; no acceptance entity is hard-coded.
    # --------------------------------------------------
    provider_source = (
        SRC_DIR / "ai" / "ollama_provider.py"
    ).read_text(encoding="utf-8")

    assert "public_source_verified" in provider_source
    assert "gather_public_factual_research" in provider_source
    assert "verify_public_factual_draft" in provider_source
    assert "grounded_research_evidence" in provider_source

    router_source = (
        SRC_DIR / "core" / "epistemic_router.py"
    ).read_text(encoding="utf-8").lower()

    for concrete_name in (
        "widgetflux",
        "example dynamics",
        "examplenet",
        "examplegpu",
    ):
        assert concrete_name not in router_source

    print("Mairon Phase 10.7.10 general factual authority tests: PASS")


if __name__ == "__main__":
    run()
