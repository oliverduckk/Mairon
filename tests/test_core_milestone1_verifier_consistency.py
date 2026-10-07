"""Core must reject incomplete or contradictory public/media verifier verdicts."""

import copy
import json
import sys
import types
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from research.media_grounding import verify_media_draft
from research.public_factual_grounding import verify_public_factual_draft


DRAFT = "The harbor has a lighthouse. The lighthouse was built in 1890."
SENTENCES = ["The harbor has a lighthouse.", "The lighthouse was built in 1890."]
PACKET = json.dumps({
    "answer_mode": "fact_lookup",
    "sources": [{
        "source_id": "S1",
        "source_quality": "reference",
        "read_success": True,
        "content_excerpt": DRAFT,
    }],
})


class _Client:
    def __init__(self, payload):
        self.payload = payload

    def chat(self, **kwargs):
        return types.SimpleNamespace(
            message=types.SimpleNamespace(content=json.dumps(self.payload))
        )


def _payload(kind):
    value = {
        "supported": True,
        "unsupported_claims": [],
        "sentence_assessments": [
            {"index": 1, "supported": True},
            {"index": 2, "supported": True},
        ],
    }
    if kind == "media":
        value.update(scope_compliant=True, out_of_scope_claims=[])
        for item in value["sentence_assessments"]:
            item["scope_compliant"] = True
    return value


def _verify(kind, payload):
    verifier = verify_media_draft if kind == "media" else verify_public_factual_draft
    return verifier(
        client=_Client(payload),
        model="replaceable-local-model",
        user_input="What does the source say about the harbor?",
        draft=DRAFT,
        research_evidence=PACKET,
    )


class VerifierConsistencyTests(unittest.TestCase):
    def assert_closed(self, kind, payload):
        result = _verify(kind, payload)
        self.assertTrue(result, "invalid verdict approved the whole draft")
        self.assertEqual(result.accepted_sentences, [], "invalid verdict allowed salvage")

    def test_global_success_requires_sentence_assessments(self):
        for kind in ("public", "media"):
            for missing in ("absent", "empty", "null"):
                with self.subTest(kind=kind, missing=missing):
                    payload = _payload(kind)
                    if missing == "absent":
                        del payload["sentence_assessments"]
                    else:
                        payload["sentence_assessments"] = [] if missing == "empty" else None
                    self.assert_closed(kind, payload)

    def test_global_success_requires_complete_sentence_assessments(self):
        for kind in ("public", "media"):
            with self.subTest(kind=kind):
                payload = _payload(kind)
                payload["sentence_assessments"].pop()
                self.assert_closed(kind, payload)

    def test_global_success_cannot_override_negative_sentence_support(self):
        for kind in ("public", "media"):
            with self.subTest(kind=kind):
                payload = _payload(kind)
                payload["sentence_assessments"][1]["supported"] = False
                self.assert_closed(kind, payload)

    def test_global_failure_cannot_contradict_all_positive_sentences(self):
        for kind in ("public", "media"):
            with self.subTest(kind=kind):
                payload = _payload(kind)
                payload["supported"] = False
                self.assert_closed(kind, payload)

    def test_global_success_cannot_contradict_claim_list(self):
        for kind in ("public", "media"):
            with self.subTest(kind=kind):
                payload = _payload(kind)
                payload["unsupported_claims"] = ["unsupported lighthouse date"]
                self.assert_closed(kind, payload)

    def test_media_scope_verdicts_must_agree(self):
        for contradiction in ("negative_unit", "negative_global", "scope_claim"):
            with self.subTest(contradiction=contradiction):
                payload = _payload("media")
                if contradiction == "negative_unit":
                    payload["sentence_assessments"][1]["scope_compliant"] = False
                elif contradiction == "negative_global":
                    payload["scope_compliant"] = False
                else:
                    payload["out_of_scope_claims"] = ["later story detail"]
                self.assert_closed("media", payload)

    def test_sentence_assessments_must_be_unique_and_well_typed(self):
        for kind in ("public", "media"):
            for invalid in ("duplicate", "conflicting_duplicate", "string_index", "float_index",
                            "boolean_index", "out_of_range", "missing_support", "string_support",
                            "non_object"):
                with self.subTest(kind=kind, invalid=invalid):
                    payload = _payload(kind)
                    items = payload["sentence_assessments"]
                    if invalid in ("duplicate", "conflicting_duplicate"):
                        duplicate = copy.deepcopy(items[0])
                        if invalid == "conflicting_duplicate":
                            duplicate["supported"] = False
                        items.append(duplicate)
                    elif invalid == "missing_support":
                        del items[0]["supported"]
                    elif invalid == "non_object":
                        items.append(None)
                    else:
                        key = "supported" if invalid == "string_support" else "index"
                        items[0][key] = {
                            "string_index": "1", "float_index": 1.0, "boolean_index": True,
                            "out_of_range": 3, "string_support": "true",
                        }[invalid]
                    self.assert_closed(kind, payload)

    def test_required_global_fields_must_be_well_typed(self):
        for kind in ("public", "media"):
            for invalid in ("missing_supported", "string_supported", "missing_claims", "invalid_claim"):
                with self.subTest(kind=kind, invalid=invalid):
                    payload = _payload(kind)
                    if invalid == "missing_supported":
                        del payload["supported"]
                    elif invalid == "string_supported":
                        payload["supported"] = "true"
                    elif invalid == "missing_claims":
                        del payload["unsupported_claims"]
                    else:
                        payload["unsupported_claims"] = [None]
                    self.assert_closed(kind, payload)
        for field in ("scope_compliant", "out_of_scope_claims"):
            with self.subTest(kind="media", missing=field):
                payload = _payload("media")
                del payload[field]
                self.assert_closed("media", payload)

    def test_complete_consistent_success_is_accepted(self):
        for kind in ("public", "media"):
            with self.subTest(kind=kind):
                payload = _payload(kind)
                payload["sentence_assessments"].reverse()
                result = _verify(kind, payload)
                self.assertEqual(result, [])
                self.assertEqual(result.accepted_sentences, SENTENCES)

    def test_complete_consistent_rejection_preserves_supported_sentence(self):
        for kind in ("public", "media"):
            with self.subTest(kind=kind):
                payload = _payload(kind)
                payload["supported"] = False
                payload["unsupported_claims"] = ["unsupported lighthouse date"]
                payload["sentence_assessments"][1]["supported"] = False
                payload["sentence_assessments"].reverse()
                result = _verify(kind, payload)
                self.assertTrue(result)
                self.assertEqual(result.accepted_sentences, SENTENCES[:1])

    def test_complete_consistent_media_scope_rejection_preserves_in_scope_sentence(self):
        payload = _payload("media")
        payload["scope_compliant"] = False
        payload["out_of_scope_claims"] = ["later story detail"]
        payload["sentence_assessments"][1]["scope_compliant"] = False
        result = _verify("media", payload)
        self.assertTrue(result)
        self.assertEqual(result.accepted_sentences, SENTENCES[:1])


if __name__ == "__main__":
    unittest.main()
