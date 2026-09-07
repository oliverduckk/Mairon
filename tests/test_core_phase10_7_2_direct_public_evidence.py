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


# media_research only needs execute_tool at import time. Live web calls are not
# part of this regression, so keep the test independent from private services.
fake_registry = types.ModuleType(
    "tools.tool_registry"
)


def _unpatched_execute_tool(*args, **kwargs):
    raise AssertionError(
        "direct-evidence regression unexpectedly called a live tool"
    )


fake_registry.execute_tool = _unpatched_execute_tool
sys.modules.setdefault(
    "tools.tool_registry",
    fake_registry,
)

from research.media_research import (
    build_internal_research_packet,
)
from research.media_grounding import (
    verify_media_draft,
)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeResult:
    def __init__(self, content):
        self.message = _FakeMessage(
            content
        )


class _VerifierClient:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(
            kwargs
        )
        return _FakeResult(
            json.dumps({
                "supported": True,
                "unsupported_claims": [],
            })
        )


def run():
    # --------------------------------------------------
    # 1. Core preserves direct source facts instead of LLM-resummarising them.
    # --------------------------------------------------

    research_result = {
        "success": True,
        "query": "The Beginning After the End synopsis official canon source",
        "topic": "The Beginning After the End",
        "spoiler_profile": "unknown",
        "sources": [
            {
                "title": "Relevant source",
                "url": "https://example.com/tbate",
                "search_snippet": (
                    "The story follows Arthur Leywin in a world of magic."
                ),
                "read_success": True,
                "read_result": {
                    "success": True,
                    "content": (
                        "Arthur Leywin is the protagonist. "
                        "He is the reincarnation of King Grey. "
                        "The story follows his new life in a world where magic exists."
                    ),
                },
            },
        ],
    }

    packet = build_internal_research_packet(
        research_result
    )

    assert packet.startswith(
        "CORE PUBLIC-SOURCE EVIDENCE PACKET:"
    )
    assert '"source_id": "S1"' in packet
    assert "Arthur Leywin is the protagonist" in packet
    assert "reincarnation of King Grey" in packet
    assert "isolated evidence-filter" not in packet

    # --------------------------------------------------
    # 2. Evidence verifier is bounded and disables Qwen thinking.
    # --------------------------------------------------

    client = _VerifierClient()

    violations = verify_media_draft(
        client=client,
        model="qwen3.5:9b",
        user_input="give me a synopsis of The Beginning After the End",
        draft=(
            "The story follows Arthur Leywin, the reincarnation of King Grey, "
            "in a world where magic exists."
        ),
        research_evidence=packet,
    )

    assert violations == []
    assert len(client.calls) == 1

    call = client.calls[0]

    assert call.get(
        "think"
    ) is False
    assert call[
        "options"
    ][
        "temperature"
    ] == 0
    assert call[
        "options"
    ][
        "num_ctx"
    ] == 12288

    # --------------------------------------------------
    # 3. Provider no longer performs an evidence-synthesis model call.
    # --------------------------------------------------

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    start = provider_source.index(
        "def build_spoiler_safe_media_evidence("
    )
    end = provider_source.index(
        "# Ephemeral Core Answer Contracts",
        start,
    )

    evidence_builder = provider_source[
        start:end
    ]

    assert "client.chat(" not in evidence_builder
    assert "return build_internal_research_packet(" in evidence_builder

    # Researched factual turns keep one repair attempt, not the old three-pass loop.
    assert "if research_evidence:\n        # Public-source factual turns" in provider_source
    assert "personality_draft_limit = 2" in provider_source

    # The generic personal-history semantic verifier is skipped when the stricter
    # public-source verifier is already active.
    assert "elif not research_evidence:" in provider_source

    # Grounded explanations receive enough output/context headroom without
    # re-enabling hidden reasoning.
    assert '"num_predict": 240' in provider_source
    assert "12288" in provider_source

    print(
        "Mairon Phase 10.7.2 direct-public-evidence tests: PASS"
    )


if __name__ == "__main__":
    run()
