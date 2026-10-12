"""Neutral Core-owned relation/reason witness regressions (offline)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from research.public_claim_obligations import (
    admitted_body_sources, build_public_claim_obligations, public_claim_failures,
    public_claim_assessment_schema, public_request_requires_relational_completion,
)
from research.public_factual_grounding import (
    PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA, requires_public_factual_salvage_completion,
    verify_public_factual_draft, verify_public_factual_salvage_completion,
)


def packet(body="A preview called Avery Morgan exists.", title="Avery Morgan Preview", **source_state):
    source = {"source_id": "S1", "title": title, "url": "https://research.example/preview",
              "content_excerpt": body, "search_snippet": "A preview is listed.",
              "read_success": True, "accepted_as_evidence": True, "relevance_status": "accepted"}
    source.update(source_state)
    return {"research_kind": "public_factual", "freshness_required": False, "sources": [source]}


def verdict(sentences=1, claims=None, supported=True):
    value = {"supported": supported, "unsupported_claims": [] if supported else ["Unsupported detail"],
             "sentence_assessments": [{"index": index, "supported": supported} for index in range(1, sentences + 1)]}
    if claims is not None:
        value["claim_assessments"] = claims
    return value


def witnesses(text, quote, source_id="S1", supported=True):
    return [{"index": item["index"], "supported": supported,
             "source_id": source_id if supported else None,
             "source_quote": quote if supported else None}
            for item in build_public_claim_obligations([text])]


class Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.value)))


def verify(text, state=None, assessment=None, user="What happened in that preview?"):
    value = verdict(claims=assessment)
    client = Client(value)
    result = verify_public_factual_draft(client, "replaceable-model", user, text,
                                        json.dumps(state or packet()))
    return result, client


class PublicContentAuthorityTests(unittest.TestCase):
    def test_full_entity_name_cannot_be_split_into_two_relation_participants(self):
        text = "Avery and Morgan had a disagreement."
        body = "A preview called Avery Morgan exists."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)
        self.assertIn("entity_span_split", " ".join(result))

    def test_full_entity_span_preserves_identity_without_extra_content_obligation(self):
        text = "The preview is called Avery Morgan."
        result, client = verify(text)
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [text])
        self.assertEqual(client.calls[0]["format"], PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA)

    def test_two_separately_mentioned_entities_do_not_establish_a_relation(self):
        text = "Cora criticised Dax."
        body = "Cora appears in the preview. Dax appears in the same preview."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("relation_witness_missing", " ".join(result))

    def test_supported_directional_relation_with_actual_body_witness_passes(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text), witnesses(text, text))
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [text])

    def test_direction_reversal_cannot_be_rescued_by_positive_semantic_label(self):
        text, body = "Dax criticised Cora.", "Cora criticised Dax."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)

    def test_symmetric_relation_can_preserve_reversed_participant_order(self):
        text, body = "Dax collaborated with Cora.", "Cora worked with Dax."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertFalse(result)

    def test_named_entity_pair_in_title_does_not_override_real_separate_body_relation(self):
        text = "Avery and Morgan worked together."
        result, _ = verify(text, packet(text, title="Avery Morgan Preview"), witnesses(text, text))
        self.assertFalse(result)

    def test_relation_negation_does_not_support_positive_relation(self):
        text, body = "Cora defeated Dax.", "Cora did not defeat Dax."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("relation_polarity_mismatch", " ".join(result))

    def test_quoted_relation_is_not_source_world_authority(self):
        text, body = "Cora defeated Dax.", '"Cora defeated Dax."'
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)

    def test_conditional_relation_is_not_source_world_authority(self):
        text, body = "Cora defeated Dax.", "If Cora defeated Dax, the record would change."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)

    def test_unsupported_popularity_requires_more_than_a_preview_title(self):
        text = "People discussed Avery Morgan because the reveal was a fan-favourite moment."
        body = "A preview called Avery Morgan exists."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("explanation_witness_missing", " ".join(result))
        self.assertIn("reception_witness_missing", " ".join(result))

    def test_supported_popularity_and_reason_with_body_proposition_passes(self):
        text = "Fans loved Avery Morgan because the archive reveal surprised viewers."
        result, _ = verify(text, packet(text), witnesses(text, text))
        self.assertFalse(result)

    def test_reason_paraphrase_with_same_subject_and_cause_can_pass(self):
        text = "People discussed Avery Morgan because the archive opened."
        body = "Fans talked about Avery Morgan because the archive opened."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertFalse(result)

    def test_reason_for_another_named_subject_cannot_support_candidate(self):
        text = "People discussed Cora because the archive opened."
        body = "People discussed Dax because the archive opened."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("content_subject_mismatch", " ".join(result))

    def test_same_subject_and_reason_marker_cannot_support_a_different_cause(self):
        text = "People discussed Cora because the archive collapsed."
        body = "People discussed Cora because rain stopped."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("explanation_anchor_mismatch", " ".join(result))

    def test_reception_for_a_different_unnamed_topic_cannot_support_candidate(self):
        text, body = "People loved the exhibition.", "People loved the concert."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("reception_anchor_mismatch", " ".join(result))

    def test_denied_popularity_does_not_support_positive_popularity(self):
        text, body = "People loved the exhibition.", "People did not love the exhibition."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)

    def test_questioned_reason_does_not_support_asserted_reason(self):
        text, body = "People discussed Cora because the archive opened.", "Did people discuss Cora because the archive opened?"
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)

    def test_title_cannot_be_used_as_literal_content_witness(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(title=text), witnesses(text, text))
        self.assertTrue(result)
        self.assertIn("missing_admitted_body_witness", " ".join(result))

    def test_search_snippet_cannot_be_used_as_literal_content_witness(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(search_snippet=text), witnesses(text, text))
        self.assertTrue(result)

    def test_rejected_body_cannot_be_used_as_content_witness(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text, accepted_as_evidence=False), witnesses(text, text))
        self.assertTrue(result)

    def test_unreadable_body_cannot_be_used_as_content_witness(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text, read_success=False), witnesses(text, text))
        self.assertTrue(result)

    def test_unknown_source_id_cannot_supply_a_witness(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text), witnesses(text, text, source_id="S9"))
        self.assertTrue(result)

    def test_duplicate_source_ids_are_not_an_unambiguous_witness(self):
        state = packet("Cora criticised Dax.")
        state["sources"].append(copy.deepcopy(state["sources"][0]))
        self.assertFalse(admitted_body_sources(state))

    def test_candidate_prose_is_not_a_source_witness(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(), witnesses(text, text))
        self.assertTrue(result)

    def test_global_success_cannot_erase_negative_scoped_assessment(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text), witnesses(text, text, supported=False))
        self.assertTrue(result)
        self.assertEqual(result.sentence_assessments, [{"index": 1, "supported": False}])
        self.assertTrue(result.verification_state["global_supported"])
        self.assertFalse(result.verification_state["effective_supported"])

    def test_global_success_cannot_erase_missing_scoped_assessment(self):
        result, _ = verify("Cora criticised Dax.")
        self.assertTrue(result)
        self.assertIn("missing_claim_assessments", " ".join(result))

    def test_incomplete_scoped_assessment_fails_closed(self):
        text = "People discussed Cora because Cora criticised Dax."
        assessments = witnesses(text, text)[:-1]
        result, _ = verify(text, packet(text), assessments)
        self.assertTrue(result)

    def test_duplicate_scoped_assessment_fails_closed(self):
        text = "Cora criticised Dax."
        assessments = witnesses(text, text)
        result, _ = verify(text, packet(text), assessments + assessments)
        self.assertTrue(result)

    def test_wrong_scoped_boolean_type_fails_closed(self):
        text = "Cora criticised Dax."
        assessments = witnesses(text, text)
        assessments[0]["supported"] = "true"
        result, _ = verify(text, packet(text), assessments)
        self.assertTrue(result)

    def test_invalid_witness_excludes_only_its_sentence_from_salvage(self):
        text = "The preview is called Avery Morgan. Avery and Morgan had a disagreement."
        client = Client(verdict(sentences=2, claims=[{"index": 1, "supported": True,
                        "source_id": "S1", "source_quote": "A preview called Avery Morgan exists."}]))
        result = verify_public_factual_draft(client, "replaceable-model", "What was the preview?", text,
                                            json.dumps(packet()))
        self.assertTrue(result)
        self.assertEqual(result.accepted_sentences, ["The preview is called Avery Morgan."])
        self.assertEqual(result.sentence_assessments, [{"index": 1, "supported": True}, {"index": 2, "supported": False}])

    def test_truthful_unknown_reason_is_not_positive_reason_obligation(self):
        self.assertFalse(build_public_claim_obligations(["I cannot verify why people discussed that preview."]))

    def test_new_schema_does_not_mutate_legacy_schema(self):
        before = copy.deepcopy(PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA)
        generated = public_claim_assessment_schema(PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA)
        self.assertIn("claim_assessments", generated["required"])
        self.assertEqual(PUBLIC_FACTUAL_VERIFIER_RESPONSE_SCHEMA, before)

    def test_source_quote_and_obligation_are_snapshotted_in_verifier_state(self):
        text = "Cora criticised Dax."
        assessments = witnesses(text, text)
        result, _ = verify(text, packet(text), assessments)
        assessments[0]["source_quote"] = "changed"
        self.assertEqual(result.verification_state["claim_assessments"][0]["source_quote"], text)
        with self.assertRaises(TypeError):
            result.verification_state["claim_obligations"][0]["kind"] = "none"

    def test_nominal_relation_identity_cannot_be_replaced_by_same_participant_overlap(self):
        text = "A friendship between Avery and Morgan became official."
        body = "A rivalry between Avery and Morgan was reported."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("relation_witness_missing", " ".join(result))

    def test_supported_nominal_relation_with_same_literal_predicate_passes(self):
        text = "A friendship between Avery and Morgan was reported."
        result, _ = verify(text, packet(text), witnesses(text, text))
        self.assertFalse(result)

    def test_matching_nominal_relation_does_not_authorize_an_extra_relation_state(self):
        text = "A friendship between Avery and Morgan became official."
        body = "A friendship between Avery and Morgan was reported."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)

    def test_reference_to_general_discussion_preserves_completion_obligation(self):
        for request in ("What was that preview everyone was discussing?",
                        "Which result were they talking about?", "Why did others praise that result?"):
            with self.subTest(request=request):
                self.assertTrue(public_request_requires_relational_completion(request))

    def test_same_event_different_causal_outcome_does_not_support_reason(self):
        text = "People discussed Aurora because the launch succeeded."
        body = "People discussed Aurora because the launch was delayed."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("explanation_anchor_mismatch", " ".join(result))

    def test_negative_reception_plus_discussion_cannot_authorize_positive_appreciation(self):
        text = "Fans loved Aurora."
        body = "Fans hated Aurora, but people discussed Aurora."
        result, _ = verify(text, packet(body), witnesses(text, body))
        self.assertTrue(result)
        self.assertIn("reception_anchor_mismatch", " ".join(result))

    def test_core_exact_whole_body_clause_proof_needs_no_additional_annotation(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text))
        self.assertFalse(result)

    def test_present_malformed_dictionary_cannot_be_overridden_by_literal_body_proof(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text), assessment={"index": 1, "supported": True})
        self.assertTrue(result)
        self.assertIn("invalid_claim_assessments", " ".join(result))

    def test_present_malformed_string_cannot_be_overridden_by_literal_body_proof(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet(text), assessment="supported")
        self.assertTrue(result)
        self.assertIn("invalid_claim_assessments", " ".join(result))

    def test_present_malformed_null_cannot_be_overridden_by_literal_body_proof(self):
        text = "Cora criticised Dax."
        value = verdict()
        value["claim_assessments"] = None
        result = verify_public_factual_draft(Client(value), "replaceable-model", "What happened?", text,
                                            json.dumps(packet(text)))
        self.assertTrue(result)
        self.assertIn("invalid_claim_assessments", " ".join(result))

    def test_core_literal_substring_inside_conditional_source_is_not_a_whole_clause_proof(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet("If " + text))
        self.assertTrue(result)

    def test_scoped_model_cannot_strip_quotes_from_source_to_claim_assertion(self):
        text = "Cora criticised Dax."
        result, _ = verify(text, packet('"' + text + '"'), witnesses(text, text))
        self.assertTrue(result)

    def test_ordinary_past_epistemic_limitation_does_not_create_a_positive_reason_obligation(self):
        text = "I couldn't verify why people discussed Aurora."
        self.assertFalse(build_public_claim_obligations([text]))
        result, _ = verify(text)
        self.assertFalse(result)

    def test_past_epistemic_limitation_cannot_hide_appended_reason_claim(self):
        text = "I couldn't verify the event, but people discussed Aurora because the launch succeeded."
        self.assertTrue(build_public_claim_obligations([text]))
        result, _ = verify(text)
        self.assertTrue(result)

    def test_reason_request_makes_noncurrent_salvage_completion_required(self):
        ct = AnswerContractRuntime(intent="factual_question", authority="public_web", epistemic_mode="public_source_verified")
        self.assertTrue(requires_public_factual_salvage_completion(ct, packet(), user_input="Why did people discuss that preview?"))
        self.assertFalse(requires_public_factual_salvage_completion(ct, packet(), user_input="What was that preview called?"))

    def test_explicit_relation_request_requires_salvage_completion(self):
        self.assertTrue(public_request_requires_relational_completion("What was the relationship between those participants?"))

    def test_identity_only_subset_does_not_complete_reason_request(self):
        ct = AnswerContractRuntime(intent="factual_question", authority="public_web", epistemic_mode="public_source_verified")
        response = {"completed": False, "outcome": "incomplete", "request_fulfilled": False,
                    "required_claim_assessments": [], "violations": ["incomplete_request"]}
        client = Client(response)
        result = verify_public_factual_salvage_completion(client, "replaceable-model", "Why was that preview discussed?",
                    "The preview is called Avery Morgan.", ct, json.dumps(packet()))
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)

    def test_supported_identity_with_truthful_unverified_reason_completes_request(self):
        ct = AnswerContractRuntime(intent="factual_question", authority="public_web", epistemic_mode="public_source_verified")
        response = {"completed": True, "outcome": "bounded_limitation", "request_fulfilled": True,
                    "required_claim_assessments": [], "violations": []}
        client = Client(response)
        result = verify_public_factual_salvage_completion(client, "replaceable-model", "Why was that preview discussed?",
                    "The preview is called Avery Morgan. I cannot verify why people discussed it.", ct, json.dumps(packet()))
        self.assertFalse(result)
        self.assertIn("bounded limitation", client.calls[0]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
