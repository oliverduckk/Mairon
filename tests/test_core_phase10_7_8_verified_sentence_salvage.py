import json
import sys
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

from research.media_grounding import (
    MediaVerificationResult,
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
    packet = json.dumps({
        "answer_mode": "spoiler_light_overview",
        "recommendation_requested": False,
        "requested_medium": "screen",
        "answer_scope": {
            "scope": "opening_premise_only",
            "max_sentences": 3,
            "stop_after_synopsis": True,
        },
        "sources": [
            {
                "source_id": "S1",
                "title": "Example Work - Reference",
                "url": "https://example.com/reference",
                "source_quality": "reference",
                "read_success": True,
                "content_excerpt": (
                    "A teacher faces a life-changing diagnosis and makes a "
                    "dangerous decision with a former student."
                ),
            },
        ],
    })

    client = _VerifierClient({
        "supported": False,
        "scope_compliant": False,
        "unsupported_claims": [
            "specific later adversary detail",
        ],
        "out_of_scope_claims": [
            "closing recommendation tail",
        ],
        "sentence_assessments": [
            {
                "index": 1,
                "supported": True,
                "scope_compliant": True,
            },
            {
                "index": 2,
                "supported": True,
                "scope_compliant": True,
            },
            {
                "index": 3,
                "supported": False,
                "scope_compliant": False,
            },
        ],
    })

    result = verify_media_draft(
        client=client,
        model="qwen3.5:9b",
        user_input=(
            "can you give me a synopsis of Example Work? "
            "I'm thinking about watching it"
        ),
        draft=(
            "The story follows a teacher facing a life-changing diagnosis. "
            "He makes a dangerous decision with a former student. "
            "You should definitely watch it because things get wild later."
        ),
        research_evidence=packet,
    )

    assert isinstance(
        result,
        MediaVerificationResult,
    )

    assert len(result) == 2

    assert result.accepted_sentences == [
        "The story follows a teacher facing a life-changing diagnosis.",
        "He makes a dangerous decision with a former student.",
    ]

    verifier_text = "\n".join(
        message.get(
            "content",
            "",
        )
        for message in client.last_kwargs[
            "messages"
        ]
    )

    assert "S1:" in verifier_text
    assert "S2:" in verifier_text
    assert "S3:" in verifier_text
    assert "Assess EVERY numbered sentence independently" in verifier_text
    assert "mark the WHOLE sentence false" in verifier_text

    # Incomplete sentence accounting must fail closed for salvage.
    incomplete_client = _VerifierClient({
        "supported": False,
        "scope_compliant": False,
        "unsupported_claims": [
            "bad third sentence",
        ],
        "out_of_scope_claims": [],
        "sentence_assessments": [
            {
                "index": 1,
                "supported": True,
                "scope_compliant": True,
            },
        ],
    })

    incomplete = verify_media_draft(
        client=incomplete_client,
        model="qwen3.5:9b",
        user_input="what is Example Work about?",
        draft="Good first sentence. Bad second sentence.",
        research_evidence=packet,
    )

    assert incomplete.accepted_sentences == []

    provider_source = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "accepted_sentences" in provider_source
    assert "_validate_salvaged_research_draft" in provider_source
    assert "no creative rewrite required" in provider_source

    grounding_source = (
        SRC_DIR
        / "research"
        / "media_grounding.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    # No acceptance title may leak into generic production logic.
    assert "breaking bad" not in grounding_source
    assert "tokyo ghoul" not in grounding_source

    print(
        "Mairon Phase 10.7.8 verified sentence salvage tests: PASS"
    )


if __name__ == "__main__":
    run()
