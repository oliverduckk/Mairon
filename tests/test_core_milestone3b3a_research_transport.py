"""Public research/verifier transport preserves provenance without new decisions."""

import copy
import hashlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

registry = types.ModuleType("tools.tool_registry")


def _no_live_tool(*args, **kwargs):
    raise AssertionError("Transport regression must not call a live service")


registry.execute_tool = _no_live_tool
sys.modules.setdefault("tools.tool_registry", registry)

from research import public_factual_research as research
from research import public_factual_grounding as grounding
from research.public_factual_grounding import (
    PublicFactualVerificationResult,
    verify_public_factual_draft,
)


DRAFT = "The harbor has eight berths. The east berth has a shelter."
PACKET = json.dumps({
    "research_kind": "public_factual",
    "research_query": "Describe the harbor berths",
    "freshness_required": False,
    "sources": [{
        "source_id": "S1",
        "title": "Harbor guide",
        "url": "https://docs.vendor.example/harbor/guide",
        "content_excerpt": DRAFT,
    }],
})


class _VerifierClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return types.SimpleNamespace(message=types.SimpleNamespace(content=content))


def _payload():
    return {
        "supported": True,
        "unsupported_claims": [],
        "sentence_assessments": [
            {"index": 1, "supported": True},
            {"index": 2, "supported": True},
        ],
    }


def _verify(payload, draft=DRAFT, packet=PACKET, question="Describe the harbor berths"):
    return verify_public_factual_draft(
        client=_VerifierClient(payload), model="replaceable-local-model",
        user_input=question, draft=draft, research_evidence=packet,
    )


class PublicResearchTransportTests(unittest.TestCase):
    def gather(self, read_failure=False):
        discovered = [
            {"title": "Harbor guide", "url": "https://docs.vendor.example/harbor/guide",
             "content": "Harbor berths", "score": 0.9, "published_date": "2025-04-12"},
            {"title": "Navigation index", "url": "https://support.example/navigation",
             "content": "Search-only navigation snippet", "score": 0.8},
            {"title": "Port survey", "url": "https://research.example/port",
             "content": "Search-only survey snippet", "score": 0.7},
        ]
        calls = []

        def tool(name, arguments):
            calls.append((name, copy.deepcopy(arguments)))
            if name == "web_search":
                return {"success": True, "results": copy.deepcopy(discovered)}
            if read_failure and arguments["url"] == discovered[0]["url"]:
                return {"success": False, "message": "Unreadable"}
            return {
                "success": True,
                "url": arguments["url"] + "?read=canonical",
                "content": "The harbor has eight berths.",
            }

        with patch.object(research, "execute_tool", tool):
            result = research.gather_public_factual_research(
                "Describe the harbor berths", max_reads=1,
            )
        return result, calls

    def test_search_only_sources_are_retained_without_read_authority(self):
        result, calls = self.gather()
        self.assertTrue(result["success"])
        self.assertEqual(len(result["discovered_sources"]), 3)
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["read_attempt_count"], 1)
        self.assertEqual([name for name, _ in calls], ["web_search", "web_read"])
        for item in result["discovered_sources"]:
            self.assertNotIn("read_success", item)
            self.assertNotIn("accepted_as_evidence", item)
            self.assertNotIn("read_result", item)

    def test_discovery_retains_actual_source_metadata_and_optional_date(self):
        result, _ = self.gather()
        first, second, _ = result["discovered_sources"]
        self.assertEqual(first["title"], "Harbor guide")
        self.assertEqual(first["url"], "https://docs.vendor.example/harbor/guide")
        self.assertEqual(first["published_date"], "2025-04-12")
        self.assertEqual(first["source_host"], "docs.vendor.example")
        self.assertEqual(second["snippet"], "Search-only navigation snippet")
        self.assertIsNone(second["published_date"])

    def test_read_result_keeps_returned_identity_independent_of_discovery(self):
        result, _ = self.gather()
        source = result["sources"][0]
        self.assertTrue(source["read_success"])
        self.assertTrue(source["accepted_as_evidence"])
        self.assertEqual(source["read_result"]["url"], source["url"] + "?read=canonical")
        self.assertNotEqual(source["read_result"]["url"], result["discovered_sources"][0]["url"])

    def test_unreadable_source_and_search_only_source_remain_distinct(self):
        result, _ = self.gather(read_failure=True)
        failed = result["sources"][0]
        self.assertFalse(failed["read_success"])
        self.assertFalse(failed["accepted_as_evidence"])
        self.assertEqual(failed["relevance_status"], "rejected")
        self.assertIn("unreadable_source", failed["relevance_reasons"])
        self.assertEqual(result["rejected_sources"][0]["url"], failed["url"])
        self.assertEqual(len(result["discovered_sources"]), 3)
        self.assertEqual(len(result["sources"]), 2)
        self.assertTrue(result["sources"][1]["read_success"])

    def test_discovery_metadata_does_not_change_the_model_packet(self):
        result, _ = self.gather()
        legacy = {key: value for key, value in result.items() if key != "discovered_sources"}
        packet = research.build_internal_public_factual_packet(result)
        self.assertEqual(packet, research.build_internal_public_factual_packet(legacy))
        self.assertNotIn("Search-only", packet)
        self.assertNotIn("read=canonical", packet)
        self.assertIn('"source_id": "S1"', packet)

    def test_discovery_and_read_records_do_not_share_mutable_dictionary(self):
        result, _ = self.gather()
        original = result["discovered_sources"][0]["title"]
        result["sources"][0]["title"] = "Mutated read record"
        self.assertEqual(result["discovered_sources"][0]["title"], original)

    def test_failed_search_retains_empty_discovery_without_new_reads(self):
        with patch.object(research, "execute_tool", return_value={"success": False}):
            result = research.gather_public_factual_research("Describe the harbor")
        self.assertFalse(result["success"])
        self.assertEqual(result["discovered_sources"], [])
        self.assertEqual(result["sources"], [])


class PublicVerifierTransportTests(unittest.TestCase):
    def test_complete_support_retains_global_and_sentence_state(self):
        result = _verify(_payload())
        self.assertEqual(result, [])
        state = result.verification_state
        self.assertEqual(state["version"], 1)
        self.assertIs(state["global_supported"], True)
        self.assertIs(state["effective_supported"], True)
        self.assertIs(state["assessment_complete"], True)
        self.assertEqual(state["unsupported_claim_count"], 0)
        self.assertEqual(state["assessed_sentences"], tuple(result.accepted_sentences))
        self.assertEqual(state["sentence_assessments"], state["effective_sentence_assessments"])

    def test_consistent_negative_support_remains_negative(self):
        payload = _payload()
        payload["supported"] = False
        payload["unsupported_claims"] = ["Unverified shelter detail"]
        payload["sentence_assessments"][1]["supported"] = False
        result = _verify(payload)
        self.assertTrue(result)
        self.assertIs(result.verification_state["global_supported"], False)
        self.assertIs(result.verification_state["effective_supported"], False)
        self.assertIs(result.verification_state["assessment_complete"], True)
        self.assertEqual(result.verification_state["unsupported_claim_count"], 1)
        self.assertEqual(result.accepted_sentences, ["The harbor has eight berths."])

    def test_core_exclusion_does_not_overwrite_raw_positive_global_verdict(self):
        draft = "The harbor will probably remain unchanged next year."
        payload = {"supported": True, "unsupported_claims": [],
                   "sentence_assessments": [{"index": 1, "supported": True}]}
        result = _verify(payload, draft=draft)
        self.assertTrue(result)
        self.assertIs(result.verification_state["global_supported"], True)
        self.assertIs(result.verification_state["effective_supported"], False)
        self.assertIs(result.verification_state["sentence_assessments"][0]["supported"], True)
        self.assertIs(result.verification_state["effective_sentence_assessments"][0]["supported"], False)

    def test_digests_bind_exact_supplied_draft_and_packet_strings(self):
        draft = "  The harbor has eight berths.\nThe east berth has a shelter.  "
        packet = PACKET + "\n"
        result = _verify(_payload(), draft=draft, packet=packet)
        self.assertEqual(result, [])
        self.assertEqual(result.verification_state["assessed_draft_digest"],
                         hashlib.sha256(draft.encode("utf-8")).hexdigest())
        self.assertEqual(result.verification_state["packet_digest"],
                         hashlib.sha256(packet.encode("utf-8")).hexdigest())
        self.assertNotEqual(result.verification_state["assessed_draft_digest"],
                            hashlib.sha256(DRAFT.encode("utf-8")).hexdigest())

    def test_verifier_metadata_is_deeply_immutable_and_legacy_lists_stay_usable(self):
        result = _verify(_payload())
        state = result.verification_state
        with self.assertRaises(TypeError):
            state["global_supported"] = False
        with self.assertRaises(TypeError):
            state["sentence_assessments"][0]["supported"] = False
        with self.assertRaises(AttributeError):
            result.verification_state = {}
        result.sentence_assessments[0]["supported"] = False
        result.accepted_sentences.clear()
        self.assertIs(state["effective_sentence_assessments"][0]["supported"], True)
        self.assertEqual(len(state["assessed_sentences"]), 2)

    def test_constructor_snapshots_ingress_and_preserves_positional_interface(self):
        metadata = {"assessment_complete": True,
                    "sentence_assessments": [{"index": 1, "supported": True}]}
        result = PublicFactualVerificationResult(["unsupported"], ["approved"],
                                                [{"index": 1, "supported": True}], metadata)
        metadata["sentence_assessments"][0]["supported"] = False
        self.assertEqual(result, ["unsupported"])
        self.assertEqual(result.accepted_sentences, ["approved"])
        self.assertIs(result.verification_state["sentence_assessments"][0]["supported"], True)
        self.assertEqual(PublicFactualVerificationResult().verification_state, {})

    def test_incomplete_or_contradictory_state_cannot_claim_complete_support(self):
        variants = []
        incomplete = _payload()
        incomplete["sentence_assessments"].pop()
        variants.append(incomplete)
        contradictory = _payload()
        contradictory["sentence_assessments"][1]["supported"] = False
        variants.append(contradictory)
        invalid = _payload()
        invalid["supported"] = "true"
        variants.extend((invalid, "not a structured object"))
        for value in variants:
            with self.subTest(value=value):
                result = _verify(value)
                self.assertTrue(result)
                self.assertEqual(result.accepted_sentences, [])
                self.assertIsNot(result.verification_state.get("assessment_complete"), True)
                self.assertIsNot(result.verification_state.get("effective_supported"), True)

    def test_missing_evidence_does_not_fabricate_verifier_state(self):
        result = _verify(_payload(), packet="")
        self.assertEqual(result.verification_state, {})
        self.assertEqual(result.accepted_sentences, [])

    def test_metadata_freeze_failure_does_not_change_the_legacy_verdict(self):
        with patch.object(grounding, "freeze_metadata", side_effect=RuntimeError("not logged")):
            result = _verify(_payload())
        self.assertEqual(result, [])
        self.assertEqual(result.accepted_sentences, [
            "The harbor has eight berths.", "The east berth has a shelter.",
        ])
        self.assertEqual(result.verification_state, {})
        with self.assertRaises(TypeError):
            result.verification_state["assessment_complete"] = True

    def test_digest_failure_does_not_change_the_legacy_verdict(self):
        with patch.object(grounding.hashlib, "sha256", side_effect=RuntimeError("not logged")):
            result = _verify(_payload())
        self.assertEqual(result, [])
        self.assertEqual(len(result.accepted_sentences), 2)
        self.assertEqual(result.verification_state, {})

    def test_unencodable_unicode_metadata_does_not_change_the_legacy_verdict(self):
        draft = DRAFT + "\ud800"
        result = _verify(_payload(), draft=draft)
        self.assertEqual(result, [])
        self.assertEqual(result.accepted_sentences[-1], "The east berth has a shelter.\ud800")
        self.assertEqual(result.verification_state, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
