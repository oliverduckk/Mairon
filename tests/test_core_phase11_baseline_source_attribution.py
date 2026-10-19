"""Reporting predicates do not turn mechanisms into unretained source titles.

The shared syntax projection is exercised directly and through the existing
legacy public verifier. All sources are frozen invented public fixtures. No
tool/model service, retry, publication policy or old fixture is changed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from core.acceptance_public import _source_attribution_issue
from research.public_factual_grounding import (
    _public_source_property_indexes, verify_public_factual_draft,
)


URL = "https://docs.vendor.example/meridian"
TITLE = "Meridian field guide"
FACT = "A staged exchange ensures both endpoints agree on initial counters and confirms that the path is bidirectional before ordinary transfer."
SIMPLE = "The registration packet confirms shared state."


def sources(title=TITLE):
    return (SimpleNamespace(source_name=title, source_id="S1", source_url=URL,
                            data={"read_url": URL}),)


def context(title=TITLE):
    return {"version": 1, "freshness_required": False, "requirements": {},
            "sources": [{"source_id": "S1", "title": title, "read_url": URL,
                         "read_success": True, "accepted_as_evidence": True,
                         "authority_tier": "primary_official", "quality_eligible": True}]}


class Verifier:
    def __init__(self, supported=True):
        self.supported = supported
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        last = kwargs["messages"][-1]["content"]
        count = sum(line.startswith("S") and ": " in line for line in last.splitlines())
        result = {"supported": self.supported,
                  "unsupported_claims": [] if self.supported else ["Unsupported proposition"],
                  "sentence_assessments": [{"index": index, "supported": self.supported}
                                           for index in range(1, count + 1)]}
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))


def verify(text, *, title=TITLE, authority=None, supported=True, body=None):
    client = Verifier(supported)
    evidence = {"research_kind": "public_factual", "sources": [{
        "source_id": "S1", "title": title, "url": URL, "read_url": URL,
        "read_success": True, "accepted_as_evidence": True,
        "content_excerpt": text if body is None else body}]}
    result = verify_public_factual_draft(
        client, "scripted", "Describe the staged exchange.", text,
        json.dumps(evidence), authority_context=context(title) if authority is None else authority,
    )
    return result, client


class SourceAttributionProjectionTests(unittest.TestCase):
    def test_compound_mechanism_confirm_is_not_a_source_name(self):
        self.assertFalse(_source_attribution_issue(FACT, sources()))

    def test_simple_lowercase_mechanism_confirm_is_not_a_source_name(self):
        self.assertFalse(_source_attribution_issue(SIMPLE, sources()))

    def test_instrument_reports_an_observation_without_source_attribution(self):
        self.assertFalse(_source_attribution_issue("The pressure sensor reports a falling value.", sources()))

    def test_signal_indicates_state_without_claiming_page_read(self):
        self.assertFalse(_source_attribution_issue("The status flag indicates shared state.", sources()))

    def test_coordinated_causal_clause_is_not_a_long_source_title(self):
        text = "The exchange aligns the counters and indicates that transfer can proceed."
        self.assertFalse(_source_attribution_issue(text, sources()))

    def test_parenthetical_mechanism_does_not_become_a_source_title(self):
        text = "A staged exchange (OPEN, REPLY, READY) aligns counters and confirms that transfer can proceed."
        self.assertFalse(_source_attribution_issue(text, sources()))

    def test_unknown_named_handbook_still_requires_identity(self):
        self.assertTrue(_source_attribution_issue("Unretained handbook confirms shared state.", sources()))

    def test_unknown_report_still_requires_identity(self):
        self.assertTrue(_source_attribution_issue("The unretained pressure report indicates a falling value.", sources()))

    def test_unknown_proper_title_without_document_noun_still_requires_identity(self):
        self.assertTrue(_source_attribution_issue("Silent Meridian confirms shared state.", sources()))

    def test_unknown_title_with_connector_still_requires_identity(self):
        self.assertTrue(_source_attribution_issue("Signals and States reports shared state.", sources()))

    def test_unknown_quoted_lowercase_title_still_requires_identity(self):
        self.assertTrue(_source_attribution_issue('"ordinary transfer" confirms shared state.', sources()))

    def test_retained_lowercase_title_still_has_actual_identity(self):
        self.assertFalse(_source_attribution_issue("meridian field guide confirms shared state.", sources("meridian field guide")))

    def test_retained_proper_title_without_source_noun_passes(self):
        self.assertFalse(_source_attribution_issue("Silent Meridian indicates shared state.", sources("Silent Meridian")))

    def test_retained_complex_title_passes_only_its_identity(self):
        title = "Why staged exchanges align counters"
        self.assertFalse(_source_attribution_issue(title + " confirms shared state.", sources(title)))

    def test_named_source_says_remains_strict(self):
        self.assertTrue(_source_attribution_issue("unretained survey says shared state exists.", sources()))

    def test_named_source_states_remains_strict(self):
        self.assertTrue(_source_attribution_issue("Unretained compilation states shared state exists.", sources()))

    def test_named_source_documents_remains_strict(self):
        self.assertTrue(_source_attribution_issue("Unretained compilation documents shared state.", sources()))

    def test_according_to_unknown_source_remains_strict(self):
        self.assertTrue(_source_attribution_issue("According to Silent Meridian, shared state exists.", sources()))

    def test_explicit_unretained_read_remains_strict(self):
        self.assertTrue(_source_attribution_issue("I read the Unretained handbook.", sources()))

    def test_explicit_retained_read_passes_identity(self):
        self.assertFalse(_source_attribution_issue("I read the Meridian field guide.", sources()))

    def test_unknown_source_in_later_sentence_is_not_hidden_by_mechanism(self):
        self.assertTrue(_source_attribution_issue(SIMPLE + " Silent Meridian confirms shared state.", sources()))

    def test_candidate_title_does_not_create_retained_identity(self):
        self.assertTrue(_source_attribution_issue("Silent Meridian confirms shared state.", sources("Other Atlas")))

    def test_unretained_handbook_with_origin_qualifier_requires_identity(self):
        self.assertTrue(_source_attribution_issue(
            "The unretained handbook from Elysia confirms shared state.", sources()))

    def test_fabricated_report_with_origin_qualifier_requires_identity(self):
        self.assertTrue(_source_attribution_issue(
            "The fabricated report from Mars confirms shared state.", sources()))

    def test_document_qualifier_families_remain_source_attributions(self):
        for qualifier in ("from", "by", "of", "in", "on", "for", "about", "with", "under", "at"):
            with self.subTest(qualifier=qualifier):
                self.assertTrue(_source_attribution_issue(
                    f"The unretained handbook {qualifier} Orven confirms shared state.", sources()))

    def test_multiple_nominal_qualifiers_do_not_hide_source_head(self):
        self.assertTrue(_source_attribution_issue(
            "The unretained handbook from the archive in Elysia confirms shared state.", sources()))

    def test_coordinated_nominal_qualifier_does_not_hide_source_head(self):
        self.assertTrue(_source_attribution_issue(
            "The unretained handbook from Elysia and Belan confirms shared state.", sources()))

    def test_actually_retained_qualified_title_keeps_its_identity(self):
        title = "Meridian field guide from Elysia"
        self.assertFalse(_source_attribution_issue(title + " confirms shared state.", sources(title)))

    def test_qualified_sensor_is_still_ordinary_factual_content(self):
        self.assertFalse(_source_attribution_issue(
            "The pressure sensor from Elysia reports a falling value.", sources()))

    def test_qualified_exchange_is_still_ordinary_factual_content(self):
        self.assertFalse(_source_attribution_issue(
            "A staged exchange from Elysia confirms shared state.", sources()))

    def test_coordinated_mechanism_cannot_become_qualified_source(self):
        self.assertFalse(_source_attribution_issue(
            "A staged exchange checks the guide from Elysia and confirms shared state.", sources()))

    def test_mechanism_clause_with_prepositional_context_remains_factual(self):
        self.assertFalse(_source_attribution_issue(
            "The exchange aligns the counters in sequence and confirms shared state.", sources()))


class LegacyProducerSourceGuardTests(unittest.TestCase):
    def test_positive_verifier_keeps_supported_compound_mechanism(self):
        result, client = verify(FACT)
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, [FACT])
        self.assertEqual(len(client.calls), 1)

    def test_positive_verifier_keeps_supported_simple_mechanism(self):
        result, client = verify(SIMPLE)
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, [SIMPLE])
        self.assertEqual(len(client.calls), 1)

    def test_mechanism_without_source_read_identity_is_not_mislabelled_provenance(self):
        state = context()
        state["sources"] = []
        self.assertEqual(_public_source_property_indexes(state, [SIMPLE]), {})

    def test_source_guard_has_no_mutation_or_model_side_effect(self):
        state = context()
        before = copy.deepcopy(state)
        self.assertEqual(_public_source_property_indexes(state, [FACT]), {})
        self.assertEqual(state, before)

    def test_global_positive_does_not_authorize_unknown_source(self):
        text = "Unretained handbook confirms shared state."
        result, client = verify(text)
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertEqual(result.accepted_sentences, [])
        self.assertEqual(len(client.calls), 1)

    def test_global_positive_does_not_authorize_unknown_title(self):
        result, client = verify("Silent Meridian indicates shared state.")
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertFalse(result.accepted_sentences)
        self.assertEqual(len(client.calls), 1)

    def test_global_positive_does_not_authorize_unread_url(self):
        result, client = verify("Here is the source: https://docs.vendor.example/other.")
        self.assertTrue(any("source identity absent" in failure for failure in result))
        self.assertEqual(len(client.calls), 1)

    def test_global_positive_does_not_authorize_explicit_read_without_ingress(self):
        state = context()
        state["sources"] = []
        result, client = verify("I read the public page.", authority=state)
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertEqual(len(client.calls), 1)

    def test_true_loaded_named_title_stays_available(self):
        result, client = verify("Silent Meridian confirms shared state.", title="Silent Meridian")
        self.assertFalse(result, list(result))
        self.assertEqual(len(client.calls), 1)

    def test_source_admission_remains_required(self):
        state = context()
        state["sources"][0]["accepted_as_evidence"] = False
        result, client = verify("I read the Meridian field guide.", authority=state)
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertEqual(len(client.calls), 1)

    def test_model_negative_still_rejects_ordinary_factual_proposition(self):
        result, client = verify(SIMPLE, supported=False, body="The packet contains a timestamp.")
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)
        self.assertEqual(len(client.calls), 1)

    def test_source_scope_and_currentness_are_not_relaxed(self):
        state = context()
        state["freshness_required"] = True
        state["required_source_scope"] = "specialized subsystem"
        reasons = _public_source_property_indexes(state, [SIMPLE])
        self.assertIn("current state not established by retained evidence", reasons)
        self.assertIn("requested source scope not established", reasons)

    def test_both_retries_are_checked_without_inventing_an_extra_call(self):
        for text in ("Silent Meridian confirms shared state.", SIMPLE):
            result, client = verify(text)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(bool(result), text != SIMPLE)

    def test_positive_verifier_cannot_authorize_qualified_unretained_handbook(self):
        text = "The unretained handbook from Elysia confirms shared state."
        self.assertIn("source read claim absent from actual admitted provenance",
                      _public_source_property_indexes(context(), [text]))
        result, client = verify(text)
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertEqual(result.accepted_sentences, [])
        self.assertEqual(len(client.calls), 1)

    def test_positive_verifier_cannot_authorize_qualified_fabricated_report(self):
        text = "The fabricated report from Mars confirms shared state."
        self.assertIn("source read claim absent from actual admitted provenance",
                      _public_source_property_indexes(context(), [text]))
        result, client = verify(text)
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertEqual(result.accepted_sentences, [])
        self.assertEqual(len(client.calls), 1)

    def test_positive_verifier_cannot_authorize_other_document_qualifiers(self):
        for text in ("The unretained handbook by Orven indicates shared state.",
                     "The fabricated report about counters reports shared state."):
            with self.subTest(text=text):
                result, client = verify(text)
                self.assertTrue(any("source read claim absent" in failure for failure in result))
                self.assertEqual(result.accepted_sentences, [])
                self.assertEqual(len(client.calls), 1)

    def test_positive_verifier_keeps_supported_qualified_mechanisms(self):
        for text in ("A staged exchange confirms shared state.",
                     "The pressure sensor reports a falling value.",
                     "The pressure sensor from Elysia reports a falling value.",
                     "A staged exchange from Elysia confirms shared state.",
                     "A staged exchange checks the guide from Elysia and confirms shared state."):
            with self.subTest(text=text):
                self.assertEqual(_public_source_property_indexes(context(), [text]), {})
                result, client = verify(text)
                self.assertFalse(result, list(result))
                self.assertEqual(result.accepted_sentences, [text])
                self.assertEqual(len(client.calls), 1)

    def test_loaded_qualified_document_title_remains_available(self):
        title = "Meridian field guide from Elysia"
        text = title + " confirms shared state."
        result, client = verify(text, title=title)
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, [text])
        self.assertEqual(len(client.calls), 1)

    def test_qualified_document_still_requires_actual_read(self):
        title = "Meridian field guide from Elysia"
        state = context(title)
        state["sources"][0]["read_success"] = False
        result, client = verify(title + " confirms shared state.", title=title, authority=state)
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertEqual(result.accepted_sentences, [])
        self.assertEqual(len(client.calls), 1)

    def test_qualified_document_still_requires_admission(self):
        title = "Meridian field guide from Elysia"
        state = context(title)
        state["sources"][0]["accepted_as_evidence"] = False
        result, client = verify(title + " confirms shared state.", title=title, authority=state)
        self.assertTrue(any("source read claim absent" in failure for failure in result))
        self.assertEqual(result.accepted_sentences, [])
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
