import json
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


fake_registry = types.ModuleType(
    "tools.tool_registry"
)


def _unpatched_execute_tool(*args, **kwargs):
    raise AssertionError(
        "answer-scope regression unexpectedly called a live tool"
    )


fake_registry.execute_tool = _unpatched_execute_tool
sys.modules.setdefault(
    "tools.tool_registry",
    fake_registry,
)

from research import media_research
from research.media_grounding import (
    build_grounding_retry_instruction,
    verify_media_draft,
)


class _Message:
    def __init__(self, content):
        self.content = content


class _Result:
    def __init__(self, content):
        self.message = _Message(
            content
        )


class _VerifierClient:
    def __init__(self, payload):
        self.payload = payload
        self.last_kwargs = None

    def chat(self, **kwargs):
        self.last_kwargs = kwargs
        return _Result(
            json.dumps(
                self.payload
            )
        )


def run():
    # --------------------------------------------------
    # 1. Core must carry a structured answer-scope ceiling into the evidence
    #    packet. This is semantic policy, not title/franchise hard-coding.
    # --------------------------------------------------

    packet = media_research.build_internal_research_packet({
        "success": True,
        "query": "Glass Harbour synopsis premise overview official",
        "topic": "Glass Harbour",
        "research_mode": "spoiler_light_overview",
        "recommendation_requested": False,
        "requested_medium": "screen",
        "spoiler_profile": "unknown",
        "sources": [
            {
                "title": "Glass Harbour - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Glass_Harbour",
                "source_quality": "reference",
                "source_medium": "tv",
                "search_snippet": "Opening premise.",
                "read_success": True,
                "read_result": {
                    "success": True,
                    "content": "Opening premise plus additional later details.",
                },
            },
        ],
    })

    assert '"scope": "opening_premise_only"' in packet
    assert '"max_sentences": 3' in packet
    assert '"stop_after_synopsis": true' in packet
    assert '"closing_joke_or_commentary"' in packet
    assert '"specific_pursuer_or_family_relationship_detail"' in packet

    # --------------------------------------------------
    # 2. A claim can be fully supported yet still be rejected for exceeding
    #    the requested synopsis scope. The verifier must expose those as a
    #    separate violation class rather than pretending they are unsupported.
    # --------------------------------------------------

    client = _VerifierClient({
        "supported": True,
        "scope_compliant": False,
        "unsupported_claims": [],
        "out_of_scope_claims": [
            "later alias and pursuer relationship detail",
            "separate closing joke after the synopsis",
        ],
    })

    violations = verify_media_draft(
        client=client,
        model="qwen3.5:9b",
        user_input=(
            "can you give me a synopsis of Glass Harbour? "
            "I'm thinking about watching it"
        ),
        draft=(
            "Opening premise. Later identity detail. Funny closing aside."
        ),
        research_evidence=packet,
    )

    assert any(
        violation.startswith(
            "out-of-scope media detail:"
        )
        for violation in violations
    )

    verifier_system = "\n".join(
        message.get(
            "content",
            "",
        )
        for message in client.last_kwargs[
            "messages"
        ]
        if message.get(
            "role"
        ) == "system"
    )

    assert "FACTUAL SUPPORT and SCOPE COMPLIANCE are separate decisions" in verifier_system
    assert '"scope_compliant": true' in verifier_system
    assert "closing joke" in verifier_system

    # --------------------------------------------------
    # 3. Fully supported + in-scope still passes normally.
    # --------------------------------------------------

    clean_client = _VerifierClient({
        "supported": True,
        "scope_compliant": True,
        "unsupported_claims": [],
        "out_of_scope_claims": [],
    })

    clean = verify_media_draft(
        client=clean_client,
        model="qwen3.5:9b",
        user_input="what is Glass Harbour about?",
        draft="Opening premise and broad central conflict.",
        research_evidence=packet,
    )

    assert clean == []

    # --------------------------------------------------
    # 4. Repair must remove scope violations rather than swap in fresh fluff.
    # --------------------------------------------------

    retry = build_grounding_retry_instruction([
        "out-of-scope media detail: later secondary-character relationship",
        "out-of-scope media detail: closing joke",
    ])

    assert retry is not None
    assert "requested scope" in retry
    assert "End immediately after the synopsis" in retry
    assert "becoming SHORTER" in retry

    # No acceptance-fixture franchise may leak into production routing.
    research_source = (
        SRC_DIR
        / "research"
        / "media_research.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    grounding_source = (
        SRC_DIR
        / "research"
        / "media_grounding.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "glass harbour" not in research_source
    assert "glass harbour" not in grounding_source
    assert "breaking bad" not in research_source
    assert "breaking bad" not in grounding_source

    print(
        "Mairon Phase 10.7.7 answer-scope authority tests: PASS"
    )


if __name__ == "__main__":
    run()
