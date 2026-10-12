"""Producer grounding uses real Core provenance, independently of shadow.

The scripted verifier is deliberately over-permissive. Core must still keep
unsupported source properties out of both full drafts and sentence salvage.
"""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import types
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
registry = types.ModuleType("tools.tool_registry")
registry.execute_tool = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Live tool forbidden"))
sys.modules.setdefault("tools.tool_registry", registry)

from research import public_factual_research as research
from research.public_factual_grounding import (
    _split_draft_sentences, build_public_factual_generation_instruction,
    build_public_factual_retry_instruction, verify_public_factual_draft,
)
from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus
from core.acceptance_shadow import acceptance_shadow_events


URL = "https://docs.rivet.example/export"
TEXT = "Rivet supports portable export."


class PermissiveVerifier:
    def __init__(self, supported=True, malformed=None):
        self.supported = supported
        self.malformed = malformed
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        numbered = kwargs["messages"][-1]["content"]
        count = sum(line.startswith("S") and ": " in line for line in numbered.splitlines())
        content = json.dumps(self.malformed if self.malformed is not None else {
            "supported": self.supported, "unsupported_claims": [] if self.supported else ["An unsupported claim"],
            "sentence_assessments": [{"index": index, "supported": self.supported} for index in range(1, count + 1)],
        })
        return SimpleNamespace(message=SimpleNamespace(content=content))


def retained(*, actual=URL, official=True, freshness=False):
    return {
        "success": True, "query": "Rivet export", "freshness_sensitive": freshness,
        "sources": [{
            "title": "Rivet export documentation", "url": URL, "source_host": "docs.rivet.example",
            "read_success": True, "accepted_as_evidence": True, "relevance_status": "accepted",
            "authority_tier": "primary_official" if official else "independent_editorial",
            "quality_eligible": True,
            "read_result": {"success": True, "url": actual, "content": TEXT},
        }],
    }


class PublicProducerTrustTests(unittest.TestCase):
    def verify(self, text, *, data=None, current="Explain Rivet export.", client=None):
        data = data if data is not None else retained()
        context = research.build_public_factual_authority_context(data, current)
        packet = research.build_internal_public_factual_packet(data, include_read_provenance=True)
        return verify_public_factual_draft(client or PermissiveVerifier(), "replaceable-model", current,
                                           text, packet, authority_context=context)

    def test_actual_successful_gather_constructs_source_state(self):
        calls = []
        def tool(name, arguments):
            calls.append((name, dict(arguments)))
            if name == "web_search":
                return {"success": True, "results": [{"url": URL, "title": "Rivet export documentation", "content": TEXT}]}
            return {"success": True, "url": URL, "content": TEXT}
        with patch.object(research, "execute_tool", tool):
            data = research.gather_public_factual_research("Check the official Rivet export documentation.",
                                                           require_query_resolution=True, require_quality_evidence=True)
        context = research.build_public_factual_authority_context(data, "Check the official source and its exact URL.")
        self.assertEqual([name for name, _ in calls], ["web_search", "web_read"])
        self.assertEqual(context["sources"][0]["read_url"], URL)
        self.assertEqual(context["sources"][0]["authority_tier"], "primary_official")
        self.assertTrue(context["requirements"]["official_source_required"])

    def test_context_is_detached_and_immutable(self):
        data = retained()
        context = research.build_public_factual_authority_context(data, "Which source URL did you use?")
        data["sources"][0]["read_result"]["url"] = "https://other.example/changed"
        self.assertEqual(context["sources"][0]["read_url"], URL)
        with self.assertRaises(TypeError):
            context["sources"][0]["read_url"] = "https://other.example/changed"

    def test_actual_read_url_differs_from_discovery_without_guessed_equivalence(self):
        actual = "https://docs.rivet.example/export.html"
        data = retained(actual=actual)
        self.assertEqual(research.actual_read_url(data["sources"][0]), actual)
        context = research.build_public_factual_authority_context(data, "Which source did you read?")
        self.assertEqual(context["sources"][0]["discovered_url"], URL)
        self.assertEqual(context["sources"][0]["read_url"], actual)

    def test_packet_retains_read_identity_and_admission(self):
        data = retained(actual="https://docs.rivet.example/export.html")
        packet = research.build_internal_public_factual_packet(data, include_read_provenance=True)
        parsed = json.loads(packet[packet.index("{"):])
        source = parsed["sources"][0]
        self.assertEqual(source["url"], URL)
        self.assertEqual(source["read_url"], data["sources"][0]["read_result"]["url"])
        self.assertIs(source["read_success"], True)
        self.assertIs(source["accepted_as_evidence"], True)

    def test_missing_actual_url_is_not_fabricated_from_search(self):
        data = retained()
        del data["sources"][0]["read_result"]["url"]
        self.assertIsNone(research.actual_read_url(data["sources"][0]))
        self.assertTrue(self.verify("I actually loaded " + URL + ".", data=data))

    def test_rejected_source_never_becomes_actual_read_authority(self):
        data = retained()
        data["sources"][0]["accepted_as_evidence"] = False
        self.assertIsNone(research.actual_read_url(data["sources"][0]))
        self.assertFalse(research.build_public_factual_authority_context(data, "Read the page.")["sources"])

    def test_unreadable_source_never_becomes_read_authority(self):
        data = retained()
        data["sources"][0]["read_result"]["success"] = False
        self.assertIsNone(research.actual_read_url(data["sources"][0]))
        self.assertTrue(self.verify("I loaded the page.", data=data))

    def test_valid_loaded_source_caption_is_accepted(self):
        result = self.verify(TEXT + " Here is the official source: " + URL + ".")
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [TEXT, "Here is the official source: " + URL + "."])

    def test_fabricated_source_url_rejects_even_positive_verifier(self):
        result = self.verify("The source is https://docs.rivet.example/other.")
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_scheme_and_path_changes_are_not_guessed_equivalent(self):
        for wrong in (URL.replace("https:", "http:"), URL + ".html", URL + "?format=full", URL + "#details"):
            with self.subTest(wrong=wrong):
                self.assertTrue(self.verify("Here is the source: " + wrong + "."))

    def test_source_property_failure_is_removed_from_salvage(self):
        invalid = "Here is the source: https://other.example/substituted."
        result = self.verify(TEXT + " " + invalid)
        self.assertTrue(result)
        self.assertEqual(result.accepted_sentences, [TEXT])
        self.assertEqual(result.sentence_assessments, [{"index": 1, "supported": True}, {"index": 2, "supported": False}])
        self.assertIs(result.verification_state["global_supported"], True)
        self.assertIs(result.verification_state["effective_supported"], False)

    def test_false_official_caption_does_not_acquire_authority_from_wording(self):
        self.assertTrue(self.verify("Here is the official source: " + URL + ".", data=retained(official=False)))

    def test_explicit_official_request_requires_actual_source_metadata(self):
        self.assertTrue(self.verify(TEXT, data=retained(official=False), current="Check the official documentation."))

    def test_explicit_read_request_uses_current_user_not_reconstructed_query(self):
        data = retained()
        data["query"] = "Rivet export"
        context = research.build_public_factual_authority_context(data, "If you didn't read it, say so. Which official link is that from?")
        self.assertTrue(context["requirements"]["source_read_required"])
        self.assertTrue(context["requirements"]["exact_source_required"])
        self.assertTrue(context["requirements"]["official_source_required"])

    def test_requested_exact_url_must_be_actual_read_url(self):
        self.assertTrue(self.verify(TEXT, current="Read https://docs.rivet.example/other."))

    def test_valid_actual_read_statement_is_allowed(self):
        self.assertFalse(self.verify("I loaded the page. Here is the source: " + URL + "."))

    def test_named_unread_source_cannot_be_claimed_loaded(self):
        self.assertTrue(self.verify("I read the Cyclone technical reference."))

    def test_bounded_reporting_does_not_authorize_an_invented_source(self):
        self.assertTrue(self.verify("According to the Cyclone technical reference, portable export is supported."))

    def test_retrieval_claim_needs_actual_provenance(self):
        data = retained()
        data["sources"][0]["read_result"].pop("url")
        self.assertTrue(self.verify("I pulled the text from the live site.", data=data))

    def test_current_exact_result_requires_more_than_retrieval_date(self):
        data = retained(freshness=True)
        data["sources"][0]["published_date"] = "2026-09-23"
        data["sources"][0]["read_result"]["content"] = "Rivet version 6.8 was released for the laboratory edition."
        result = self.verify("The latest version is 6.8.", data=data, current="What is the latest Rivet version?")
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_unqualified_exact_answer_cannot_evade_current_context(self):
        data = retained(freshness=True)
        data["sources"][0]["read_result"]["content"] = "Rivet version 6.8 was released."
        self.assertTrue(self.verify("It is version 6.8.", data=data, current="Which version is current?"))

    def test_bounded_dated_source_report_remains_possible(self):
        data = retained(freshness=True)
        data["sources"][0]["read_result"]["content"] = "Rivet version 6.8 was released."
        draft = "The source reports version 6.8. I cannot confirm the current release."
        self.assertFalse(self.verify(draft, data=data, current="Which version is current?"))

    def test_explicit_trusted_currentness_can_support_current_answer(self):
        data = retained(freshness=True)
        data["sources"][0]["currentness_established"] = True
        data["sources"][0]["read_result"]["content"] = "Rivet version 6.8 is current."
        self.assertFalse(self.verify("The current version is 6.8.", data=data))

    def test_evergreen_fact_is_not_rejected_for_absent_dates(self):
        self.assertFalse(self.verify(TEXT))

    def test_source_scope_must_remain_in_the_answer(self):
        data = retained()
        data["sources"][0]["source_scope"] = "laboratory edition"
        self.assertTrue(self.verify(TEXT, data=data))
        self.assertFalse(self.verify("The laboratory edition supports portable export.", data=data))

    def test_required_scope_cannot_be_substituted(self):
        data = retained()
        data["required_source_scope"] = "field edition"
        data["sources"][0]["source_scope"] = "laboratory edition"
        self.assertTrue(self.verify("The laboratory edition supports portable export.", data=data))

    def test_independent_multi_source_scopes_are_not_all_required_in_every_sentence(self):
        data = retained()
        data["sources"][0]["source_scope"] = "laboratory edition"
        alternate = copy.deepcopy(data["sources"][0])
        alternate["source_scope"] = "field edition"
        alternate["url"] = alternate["read_result"]["url"] = "https://docs.rivet.example/field-export"
        data["sources"].append(alternate)
        self.assertFalse(self.verify("The laboratory edition supports portable export.", data=data))

    def test_multiple_actual_source_properties_fail_independently(self):
        data = retained(official=False, freshness=True)
        result = self.verify("The latest version is 6.8. Here is the official source: https://other.example/page.",
                             data=data, current="Check the official source for the latest version.")
        reasons = " ".join(result)
        for phrase in ("source identity", "source authority", "official source", "current state"):
            self.assertIn(phrase, reasons)

    def test_invalid_context_fails_closed_in_legacy_pipeline(self):
        for malformed in ({"version": 8}, "untrusted context", False):
            with self.subTest(context=malformed):
                result = verify_public_factual_draft(PermissiveVerifier(), "replaceable-model", "Explain export.",
                    TEXT, research.build_internal_public_factual_packet(retained()), authority_context=malformed)
                self.assertTrue(result)
                self.assertFalse(result.accepted_sentences)

    def test_legacy_calls_remain_compatible_without_new_context(self):
        result = verify_public_factual_draft(PermissiveVerifier(), "replaceable-model", "Explain export.",
            TEXT, research.build_internal_public_factual_packet(retained()))
        self.assertFalse(result)

    def test_verifier_global_unit_consistency_remains_strict(self):
        bad = {"supported": True, "unsupported_claims": [], "sentence_assessments": [{"index": 1, "supported": False}]}
        result = self.verify(TEXT, client=PermissiveVerifier(malformed=bad))
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_new_producer_instruction_exposes_actual_authority_bounds(self):
        context = research.build_public_factual_authority_context(retained(), "Which source URL did you use?")
        instruction = build_public_factual_generation_instruction(context)
        self.assertIn('"read_url": "' + URL + '"', instruction)
        self.assertIn("does not prove the latest/current state", instruction)
        self.assertIn("not facts supplied by your prose", instruction)
        self.assertIsNone(build_public_factual_generation_instruction(None))

    def test_retry_instruction_handles_core_source_property_failures(self):
        result = self.verify("Here is the source: https://other.example/substituted.")
        self.assertIn("source property unsupported", build_public_factual_retry_instruction(result))


class ProductionClient:
    def __init__(self, drafts):
        self.drafts = tuple(drafts)
        self.generations = 0
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if "format" in kwargs:
            numbered = kwargs["messages"][-1]["content"]
            count = sum(line.startswith("S") and ": " in line for line in numbered.splitlines())
            content = json.dumps({"supported": True, "unsupported_claims": [],
                "sentence_assessments": [{"index": index, "supported": True} for index in range(1, count + 1)]})
        else:
            content = self.drafts[min(self.generations, len(self.drafts) - 1)]
            self.generations += 1
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")


class PublicProducerIntegrationTests(unittest.TestCase):
    def run_production(self, drafts, *, current="Explain Rivet export.", query=None,
                       read_url=URL, content=TEXT, observer_status=None, followup=False):
        from test_core_milestone3b3a_public_shadow_integration import provider, contract
        from core.evidence import EvidenceKind
        calls = []

        def tool(name, arguments):
            calls.append((name, dict(arguments)))
            if name == "web_search":
                return {"success": True, "results": [{"url": URL, "title": "Rivet export documentation", "content": content}]}
            return {"success": True, "url": read_url, "content": content}

        run, namespace = provider()
        namespace.update({
            "gather_public_factual_research": research.gather_public_factual_research,
            "build_public_factual_authority_context": research.build_public_factual_authority_context,
            "build_public_factual_generation_instruction": build_public_factual_generation_instruction,
            "actual_read_url": research.actual_read_url,
        })
        if followup:
            namespace.update({
                "_latest_user_authored_message": lambda *args, **kwargs: "Explain Rivet export.",
                "reconstruct_bounded_factual_followup": lambda *args, **kwargs: query or "Explain Rivet export.",
                "source_provenance_research_query": lambda *args, **kwargs: query or "Explain Rivet export.",
                "is_source_provenance_followup": lambda *args, **kwargs: True,
            })
        client = ProductionClient(drafts)
        candidates = []
        evaluate = CoreAcceptanceEvaluator.evaluate

        def capture(evaluator, candidate):
            candidates.append(candidate)
            if observer_status is not None:
                return AcceptanceDecision(observer_status, candidate.text, violated_invariants=("source_identity",))
            return evaluate(evaluator, candidate)

        with redirect_stdout(io.StringIO()), patch.object(research, "execute_tool", tool), \
                patch.object(CoreAcceptanceEvaluator, "evaluate", capture), acceptance_shadow_events(lambda event: None):
            result = run(client, current, [{"role": "assistant", "content": "An unverified source claim."}], core_answer_contract=contract())
        return result, client, candidates, calls

    def test_real_gather_packet_and_legacy_guard_replace_guessed_source_with_correct_retry(self):
        wrong = "Here is the source: " + URL.replace("https:", "http:") + "."
        valid = TEXT + " Here is the source: " + URL + "."
        result, client, candidates, calls = self.run_production([wrong, valid])
        self.assertEqual(result[0], valid)
        self.assertEqual(result[1][-1]["content"], valid)
        self.assertEqual(client.generations, 2)
        self.assertEqual(len(candidates), 1)
        self.assertEqual([name for name, _ in calls], ["web_search", "web_read"])
        self.assertTrue(any("CORE PUBLIC SOURCE AUTHORITY BOUNDS" in message.get("content", "")
                            for call in client.calls for message in call["messages"]))

    def test_real_current_lookup_uses_bounded_source_report_after_unproven_latest(self):
        content = "Rivet version 6.8 was released."
        invalid = "The latest version is 6.8."
        valid = "The source reports version 6.8. I cannot confirm the current release."
        result, client, candidates, calls = self.run_production([invalid, valid], current="What is the latest Rivet version?", content=content)
        self.assertEqual(result[0], valid)
        self.assertEqual(client.generations, 2)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(calls), 2)

    def test_rejected_shadow_cannot_change_producer_valid_answer(self):
        result, client, candidates, _ = self.run_production([TEXT], observer_status=AcceptanceStatus.REJECTED)
        self.assertEqual(result[0], TEXT)
        self.assertEqual(result[1][-1]["content"], TEXT)
        self.assertEqual(client.generations, 1)
        self.assertEqual(len(candidates), 1)

    def test_replacement_shadow_cannot_change_producer_valid_answer(self):
        result, client, candidates, _ = self.run_production([TEXT], observer_status=AcceptanceStatus.REPLACEMENT_REQUIRED)
        self.assertEqual(result[0], TEXT)
        self.assertEqual(result[1][-1]["content"], TEXT)
        self.assertEqual(client.generations, 1)

    def test_provenance_fallback_names_actual_extracted_identity(self):
        actual = "https://docs.rivet.example/export.html"
        result, client, candidates, _ = self.run_production(["I loaded https://other.example/unseen."],
            current="Which source URL did you actually load?", read_url=actual, followup=True)
        self.assertIn("URL I actually loaded is " + actual, result[0])
        self.assertTrue(result[0].endswith(actual + "."))
        self.assertGreaterEqual(client.generations, 1)
        self.assertFalse(candidates)

    def test_missing_actual_identity_fallback_does_not_claim_search_url_was_loaded(self):
        result, _, candidates, _ = self.run_production(["I loaded https://other.example/unseen."],
            current="Which source URL did you actually load?", read_url=None, followup=True)
        self.assertIn("did not retain a usable URL", result[0])
        self.assertNotIn(URL, result[0])
        self.assertFalse(candidates)


if __name__ == "__main__":
    unittest.main(verbosity=2)
