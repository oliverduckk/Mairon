import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from research.media_grounding import (
    MEDIA_VERIFIER_RESPONSE_SCHEMA,
    MediaVerificationResult,
    verify_media_draft,
)


class _Message:
    def __init__(self, content):
        self.content = content


class _Result:
    def __init__(self, content):
        self.message = _Message(content)


class _VerifierClient:
    def __init__(self, content):
        self.content = content
        self.last_kwargs = None

    def chat(self, **kwargs):
        self.last_kwargs = kwargs
        return _Result(self.content)


def _packet():
    return json.dumps({
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
                    "A teacher receives a serious diagnosis and makes a "
                    "dangerous decision with a former student."
                ),
            }
        ],
    })


def run():
    payload = {
        "supported": True,
        "scope_compliant": True,
        "unsupported_claims": [],
        "out_of_scope_claims": [],
        "sentence_assessments": [
            {
                "index": 1,
                "supported": True,
                "scope_compliant": True,
            }
        ],
    }

    client = _VerifierClient(json.dumps(payload))

    result = verify_media_draft(
        client=client,
        model="qwen3.5:9b",
        user_input="what is Example Work about?",
        draft="A teacher makes a dangerous decision after a serious diagnosis.",
        research_evidence=_packet(),
    )

    assert isinstance(result, MediaVerificationResult)
    assert result == []

    # Phase 10.7.9: the verifier must use Ollama's schema-constrained
    # structured-output path rather than relying on prompt compliance alone.
    assert client.last_kwargs["format"] == MEDIA_VERIFIER_RESPONSE_SCHEMA
    assert MEDIA_VERIFIER_RESPONSE_SCHEMA["type"] == "object"
    assert set(MEDIA_VERIFIER_RESPONSE_SCHEMA["required"]) == {
        "supported",
        "scope_compliant",
        "unsupported_claims",
        "out_of_scope_claims",
        "sentence_assessments",
    }

    assessment_schema = (
        MEDIA_VERIFIER_RESPONSE_SCHEMA[
            "properties"
        ]["sentence_assessments"]["items"]
    )

    assert assessment_schema["additionalProperties"] is False
    assert set(assessment_schema["required"]) == {
        "index",
        "supported",
        "scope_compliant",
    }

    # Sentence assessment JSON must have enough completion headroom. The old
    # 240-token ceiling intermittently truncated live verifier output.
    assert client.last_kwargs["options"]["num_predict"] >= 384
    assert client.last_kwargs["options"]["temperature"] == 0
    assert client.last_kwargs.get("think") is False

    # Even with structured-output mode, Core still independently validates the
    # returned payload and fails closed if the server/model response is malformed.
    malformed_client = _VerifierClient(
        'not-json-at-all'
    )

    malformed = verify_media_draft(
        client=malformed_client,
        model="qwen3.5:9b",
        user_input="what is Example Work about?",
        draft="A teacher makes a dangerous decision.",
        research_evidence=_packet(),
    )

    assert malformed == [
        "media factual-support verifier could not validate the draft"
    ]
    assert malformed.accepted_sentences == []

    grounding_source = (
        SRC_DIR / "research" / "media_grounding.py"
    ).read_text(encoding="utf-8").lower()

    # Regression remains semantic rather than franchise-specific.
    assert "breaking bad" not in grounding_source
    assert "tokyo ghoul" not in grounding_source

    print(
        "Mairon Phase 10.7.9 structured verifier output tests: PASS"
    )


if __name__ == "__main__":
    run()
