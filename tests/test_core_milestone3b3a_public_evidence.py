"""Typed public provenance observation uses invented neutral research state.

These are transport/evaluator regressions. No live service or repository,
benchmark fixture, model knowledge or publication authority is involved.
"""
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_public import (
    INSUFFICIENT_CURRENTNESS_SUPPORT, INSUFFICIENT_SCOPE_SUPPORT,
    OFFICIAL_SOURCE_SUPPORT, PUBLIC_GLOBAL_SUPPORT, PUBLIC_SENTENCE_SUPPORT,
    PUBLIC_VERIFIER_CONSISTENCY, SOURCE_IDENTITY, SOURCE_READ_PROVENANCE,
    validate_public,
)
from core.acceptance_semantics import interpret_text
from core.answer_candidate import AcceptanceStatus, CandidateOrigin
from core.answer_contract_runtime import AnswerContractRuntime
from core.evidence import EvidenceKind, EvidenceStatus
from core.public_answer_evidence import (
    build_public_answer_candidate, normalize_public_answer_evidence,
    normalize_source_url, public_packet_digest,
)
from research.public_factual_grounding import (
    PublicFactualVerificationResult, _split_draft_sentences, verify_public_factual_draft,
)


FACT = "The orchard contains twelve pear trees."
URL = "https://docs.vendor.example/orchard"


def contract(**changes):
    fields = dict(task="answer from public evidence", intent="factual_question",
                  speech_act="question", authority="public_web",
                  epistemic_mode="public_source_verified", subject="orchard",
                  allow_new_factual_claims=False)
    fields.update(changes)
    return AnswerContractRuntime(**fields)


def source(url=URL, **changes):
    fields = dict(title="Orchard field guide", url=url, source_host="docs.vendor.example",
                  source_quality="official_or_publisher", authority_tier="primary_official",
                  quality_eligible=True, authority_reason="identity_anchor_matches_source_host",
                  published_date="2024-04-02", read_success=True,
                  accepted_as_evidence=True, relevance_status="accepted",
                  relevance_reasons=[], identity_anchors=["orchard"],
                  read_result={"success": True, "url": url, "content": FACT})
    fields.update(changes)
    return fields


def inputs(text=FACT):
    raw_source = source()
    result = dict(success=True, query="Describe the orchard", research_identity="orchard",
                  freshness_sensitive=False, official_documentation_required=False,
                  sources=[raw_source], discovered_sources=[{
                      "title": raw_source["title"], "url": URL, "snippet": "Search summary",
                  }], rejected_sources=[])
    packet = json.dumps({"research_kind": "public_factual", "research_query": result["query"],
                         "freshness_required": False, "sources": [{
                             "source_id": "S1", "title": raw_source["title"], "url": URL,
                             "source_host": raw_source["source_host"],
                             "authority_tier": raw_source["authority_tier"],
                             "quality_eligible": True, "content_excerpt": FACT,
                         }]})
    sentences = _split_draft_sentences(text)
    assessments = [{"index": index, "supported": True}
                   for index in range(1, len(sentences) + 1)]
    state = dict(version=1, assessed_draft_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                 packet_digest=public_packet_digest(packet), assessed_sentences=sentences,
                 global_supported=True, unsupported_claim_count=0, assessment_complete=True,
                 sentence_assessments=assessments,
                 effective_sentence_assessments=copy.deepcopy(assessments), effective_supported=True)
    return result, packet, SimpleNamespace(verification_state=state)


def candidate(text=FACT, *, data=None, runtime=None, origin=CandidateOrigin.GENERATED):
    result, packet, verification = data or inputs(text)
    return build_public_answer_candidate(text=text, contract=runtime or contract(),
                                         research_result=result, evidence_packet=packet,
                                         verification_result=verification, origin=origin)


def decision(value):
    return CoreAcceptanceEvaluator().evaluate(value)


class PublicEvidenceTests(unittest.TestCase):
    def assertNotAccepted(self, value, invariant=None):
        outcome = decision(value)
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        if invariant:
            self.assertIn(invariant, outcome.violated_invariants)
        return outcome

    def test_valid_evergreen_verifier_backed_candidate_is_accepted(self):
        outcome = decision(candidate())
        self.assertIs(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn("public_factual_verifier_provenance", outcome.metadata["typed_validators"])

    def test_actual_existing_verifier_results_feed_typed_acceptance(self):
        result, packet, _ = inputs()
        client = SimpleNamespace(chat=lambda **kwargs: SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "supported": True, "unsupported_claims": [],
            "sentence_assessments": [{"index": 1, "supported": True}],
        }))))
        verified = verify_public_factual_draft(client=client, model="neutral-local",
                                              user_input="Describe the orchard", draft=FACT,
                                              research_evidence=packet)
        self.assertEqual(list(verified), [])
        value = candidate(data=(result, packet, verified))
        self.assertIs(decision(value).status, AcceptanceStatus.ACCEPTED)

    def test_packet_excerpts_are_factual_payload_not_candidate_prose(self):
        text = "The orchard contains twelve pear trees. There is also a glasshouse."
        value = candidate(text)
        self.assertEqual(value.evidence.authoritative_claims, (FACT,))
        self.assertNotIn("glasshouse", repr(value.evidence.evidence[0].data))

    def test_search_discovery_without_read_remains_unavailable(self):
        data = inputs()
        data[0]["discovered_sources"].append({"url": "https://support.example/unread", "title": "Unread guide",
                                              "snippet": "The invented number is forty."})
        value = candidate(data=data)
        unread = next(item for item in value.evidence.evidence if item.source_name == "Unread guide")
        self.assertIs(unread.status, EvidenceStatus.UNAVAILABLE)
        self.assertTrue(unread.data["discovered"])
        self.assertFalse(unread.data["read_attempted"])
        self.assertFalse(unread.data["read_success"])
        self.assertEqual(unread.claim, "")
        self.assertNotIn("forty", " ".join(value.evidence.authoritative_claims))

    def test_read_attempt_failure_remains_rejected(self):
        data = inputs()
        data[0]["sources"].append(source("https://support.example/failed", read_success=False,
                                         accepted_as_evidence=False, relevance_status="rejected",
                                         read_result={"success": False, "url": "https://support.example/failed"}))
        item = candidate(data=data).evidence.evidence[-1]
        self.assertIs(item.status, EvidenceStatus.REJECTED)
        self.assertTrue(item.data["read_attempted"])
        self.assertFalse(item.data["read_success"])

    def test_rejected_loaded_packet_record_cannot_become_authoritative(self):
        data = inputs()
        data[0]["sources"][0]["accepted_as_evidence"] = False
        data[0]["sources"][0]["relevance_status"] = "rejected"
        value = candidate(data=data)
        self.assertEqual(value.evidence.authoritative_claims, ())
        self.assertNotAccepted(value, SOURCE_READ_PROVENANCE)

    def test_rejected_diagnostic_veto_cannot_disappear_behind_packet(self):
        data = inputs()
        data[0]["rejected_sources"].append({"url": URL, "stage": "post_read_relevance", "reasons": ["out_of_scope"]})
        self.assertNotAccepted(candidate(data=data), SOURCE_READ_PROVENANCE)

    def test_success_flag_and_snippet_do_not_establish_loaded_packet(self):
        data = inputs()
        data[0]["sources"] = []
        value = candidate(data=data)
        self.assertEqual(value.evidence.authoritative_claims, ())
        self.assertNotAccepted(value, SOURCE_READ_PROVENANCE)

    def test_read_outside_packet_does_not_broaden_authority(self):
        data = inputs()
        data[0]["sources"].append(source("https://research.example/outside"))
        value = candidate(data=data)
        item = next(item for item in value.evidence.evidence if item.source_url.endswith("outside"))
        self.assertTrue(item.data["read_success"])
        self.assertFalse(item.data["admitted_in_packet"])
        self.assertIs(item.status, EvidenceStatus.UNAVAILABLE)

    def test_packet_id_title_and_authority_metadata_survive(self):
        item = candidate().evidence.evidence[0]
        self.assertEqual(item.source_id, "S1")
        self.assertEqual(item.source_name, "Orchard field guide")
        self.assertEqual(item.source_url, URL)
        self.assertEqual(item.authority_tier, "primary_official")
        self.assertEqual(item.data["published_date"], "2024-04-02")
        self.assertEqual(item.data["authority_reason"], "identity_anchor_matches_source_host")
        self.assertIs(item.kind, EvidenceKind.PUBLIC_SOURCE)

    def test_unknown_cited_url_is_not_fully_accepted(self):
        self.assertNotAccepted(candidate(FACT + " See https://support.example/not-loaded."), SOURCE_IDENTITY)

    def test_search_only_url_is_not_loaded_identity(self):
        text = FACT + " I loaded https://support.example/search-only."
        data = inputs(text)
        data[0]["discovered_sources"].append({"url": "https://support.example/search-only", "title": "Search only"})
        self.assertNotAccepted(candidate(text, data=data), SOURCE_IDENTITY)

    def test_truthful_loaded_url_survives_generic_url_segmentation(self):
        text = FACT + " I loaded " + URL + "."
        self.assertIs(decision(candidate(text)).status, AcceptanceStatus.ACCEPTED)

    def test_same_host_different_path_is_not_same_source(self):
        self.assertNotAccepted(candidate(FACT + " See https://docs.vendor.example/another-guide."), SOURCE_IDENTITY)

    def test_query_component_is_part_of_source_identity(self):
        self.assertNotAccepted(candidate(FACT + " See " + URL + "?revision=other."), SOURCE_IDENTITY)

    def test_actual_retained_read_url_can_establish_identity(self):
        text = FACT + " I loaded https://docs.vendor.example/readable-orchard."
        data = inputs(text)
        data[0]["sources"][0]["read_result"]["url"] = "https://docs.vendor.example/readable-orchard"
        self.assertIs(decision(candidate(text, data=data)).status, AcceptanceStatus.ACCEPTED)

    def test_guessed_redirect_alias_is_not_accepted(self):
        text = FACT + " I loaded https://docs.vendor.example/readable-orchard."
        self.assertNotAccepted(candidate(text), SOURCE_IDENTITY)

    def test_url_normalization_preserves_significant_components(self):
        self.assertEqual(normalize_source_url("HTTPS://DOCS.VENDOR.EXAMPLE:443/orchard"), URL)
        self.assertNotEqual(normalize_source_url(URL + "/"), normalize_source_url(URL))
        self.assertNotEqual(normalize_source_url(URL + "#section"), normalize_source_url(URL))
        self.assertIsNone(normalize_source_url("https://person:secret@docs.vendor.example/orchard"))

    def test_unknown_named_read_is_not_fully_accepted(self):
        self.assertNotAccepted(candidate(FACT + " I read the Unretained handbook."), SOURCE_READ_PROVENANCE)

    def test_unloaded_named_source_says_does_not_establish_identity(self):
        self.assertNotAccepted(candidate("Unretained handbook says the orchard contains twelve pear trees."), SOURCE_READ_PROVENANCE)

    def test_retained_named_source_says_is_accepted(self):
        self.assertIs(decision(candidate("Orchard field guide says the orchard contains twelve pear trees.")).status, AcceptanceStatus.ACCEPTED)

    def test_unretained_source_identifier_is_not_attribution_authority(self):
        self.assertNotAccepted(candidate("According to S9, the orchard contains twelve pear trees."), SOURCE_READ_PROVENANCE)

    def test_retained_source_identifier_is_attribution_authority(self):
        self.assertIs(decision(candidate("According to S1, the orchard contains twelve pear trees.")).status, AcceptanceStatus.ACCEPTED)

    def test_retained_title_read_claim_is_accepted(self):
        self.assertIs(decision(candidate(FACT + " I read the Orchard field guide.")).status, AcceptanceStatus.ACCEPTED)

    def test_official_requirement_is_copied_from_actual_research(self):
        data = inputs()
        data[0]["official_documentation_required"] = True
        value = candidate(data=data)
        self.assertIs(value.contract.metadata["official_source_required"], True)
        self.assertIs(value.evidence.metadata["public_requirements"]["official_source_required"], True)
        self.assertIs(decision(value).status, AcceptanceStatus.ACCEPTED)

    def test_existing_core_official_requirement_is_preserved(self):
        value = candidate(runtime=contract(metadata={"official_source_required": "true"}))
        self.assertIs(value.contract.metadata["official_source_required"], True)

    def test_candidate_official_label_does_not_supply_official_authority(self):
        text = "Official documentation confirms twelve pear trees."
        data = inputs(text)
        data[0]["official_documentation_required"] = True
        data[0]["sources"][0]["authority_tier"] = "independent_editorial"
        self.assertNotAccepted(candidate(text, data=data), OFFICIAL_SOURCE_SUPPORT)

    def test_unknown_official_metadata_preserves_limitation(self):
        data = inputs()
        data[0]["official_documentation_required"] = True
        data[0]["sources"][0]["authority_tier"] = "legacy_curated"
        self.assertNotAccepted(candidate(data=data), OFFICIAL_SOURCE_SUPPORT)

    def test_actual_quality_requirement_is_preserved(self):
        data = inputs()
        data[0]["quality_evidence_required"] = True
        data[0]["sources"][0]["quality_eligible"] = False
        self.assertNotAccepted(candidate(data=data), OFFICIAL_SOURCE_SUPPORT)

    def test_substituted_packet_content_is_not_loaded_evidence(self):
        data = inputs()
        parsed = json.loads(data[1])
        parsed["sources"][0]["content_excerpt"] = "The orchard contains twenty pear trees."
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        value = candidate(data=(data[0], packet, data[2]))
        self.assertIs(value.evidence.evidence[0].status, EvidenceStatus.REJECTED)
        self.assertNotAccepted(value, SOURCE_READ_PROVENANCE)

    def test_actual_compacted_truncated_packet_content_is_retained(self):
        data = inputs()
        data[0]["sources"][0]["read_result"]["content"] = FACT + " Additional content follows."
        parsed = json.loads(data[1])
        parsed["sources"][0]["content_excerpt"] = FACT + "\n[Core excerpt truncated.]"
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        self.assertIs(decision(candidate(data=(data[0], packet, data[2]))).status, AcceptanceStatus.ACCEPTED)

    def test_duplicate_packet_source_ids_fail_observationally(self):
        data = inputs()
        parsed = json.loads(data[1])
        parsed["sources"].append(copy.deepcopy(parsed["sources"][0]))
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        self.assertNotAccepted(candidate(data=(data[0], packet, data[2])), PUBLIC_VERIFIER_CONSISTENCY)

    def test_missing_packet_source_id_fails_observationally(self):
        data = inputs()
        parsed = json.loads(data[1])
        del parsed["sources"][0]["source_id"]
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        self.assertNotAccepted(candidate(data=(data[0], packet, data[2])), PUBLIC_VERIFIER_CONSISTENCY)

    def test_typed_proof_does_not_invent_sentence_to_source_bindings(self):
        value = candidate()
        profile = validate_public(value, interpret_text(value.text))
        self.assertEqual(profile.units[1].evidence_ids, ())

    def test_raw_global_positive_cannot_override_negative_sentence(self):
        text = FACT + " The warehouse contains fourteen stalls."
        data = inputs(text)
        data[2].verification_state["effective_sentence_assessments"][1]["supported"] = False
        data[2].verification_state["effective_supported"] = False
        self.assertNotAccepted(candidate(text, data=data), PUBLIC_SENTENCE_SUPPORT)

    def test_raw_global_failure_cannot_be_overridden_by_sources(self):
        data = inputs()
        state = data[2].verification_state
        state["global_supported"] = False
        state["sentence_assessments"][0]["supported"] = False
        state["effective_sentence_assessments"][0]["supported"] = False
        state["effective_supported"] = False
        self.assertNotAccepted(candidate(data=data), PUBLIC_GLOBAL_SUPPORT)

    def test_global_sentence_contradiction_fails_observationally(self):
        data = inputs()
        data[2].verification_state["sentence_assessments"][0]["supported"] = False
        self.assertNotAccepted(candidate(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_missing_sentence_verdict_fails_observationally(self):
        data = inputs(FACT + " The shed is empty.")
        data[2].verification_state["effective_sentence_assessments"].pop()
        self.assertNotAccepted(candidate(FACT + " The shed is empty.", data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_duplicate_sentence_verdict_fails_observationally(self):
        data = inputs()
        data[2].verification_state["sentence_assessments"].append({"index": 1, "supported": True})
        self.assertNotAccepted(candidate(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_nonboolean_verdict_fails_observationally(self):
        data = inputs()
        data[2].verification_state["global_supported"] = "true"
        self.assertNotAccepted(candidate(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_boolean_schema_version_is_not_an_integer_version(self):
        data = inputs()
        data[2].verification_state["version"] = True
        self.assertNotAccepted(candidate(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_boolean_transport_version_fails_observationally(self):
        value = candidate()
        metadata = dict(value.evidence.metadata)
        metadata["public_transport_version"] = True
        value = replace(value, evidence=replace(value.evidence, metadata=metadata))
        self.assertNotAccepted(value, PUBLIC_VERIFIER_CONSISTENCY)

    def test_missing_verifier_snapshot_fails_observationally(self):
        data = inputs()
        data = (data[0], data[1], PublicFactualVerificationResult())
        self.assertNotAccepted(candidate(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_changed_draft_cannot_reuse_previous_verification(self):
        self.assertNotAccepted(candidate("The orchard contains thirty pear trees.", data=inputs()), PUBLIC_VERIFIER_CONSISTENCY)

    def test_changed_packet_cannot_reuse_previous_verification(self):
        data = inputs()
        data = (data[0], data[1] + " ", data[2])
        self.assertNotAccepted(candidate(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_assessed_sentence_payload_must_completely_cover_candidate(self):
        data = inputs()
        data[2].verification_state["assessed_sentences"] = ["The orchard contains twelve pear trees"]
        self.assertNotAccepted(candidate(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_source_and_verifier_snapshots_are_deeply_immutable(self):
        data = inputs()
        value = candidate(data=data)
        data[0]["sources"][0]["relevance_reasons"].append("changed")
        data[2].verification_state["sentence_assessments"][0]["supported"] = False
        self.assertEqual(value.evidence.evidence[0].data["relevance_reasons"], ())
        self.assertTrue(value.evidence.metadata["public_verification"]["sentence_assessments"][0]["supported"])
        with self.assertRaises(TypeError):
            value.evidence.metadata["public_verification"]["sentence_assessments"][0]["supported"] = False
        with self.assertRaises(FrozenInstanceError):
            value.evidence.evidence[0].claim = "Altered"

    def test_same_valid_semantics_have_origin_invariant_decision(self):
        value = candidate()
        decisions = [decision(value.with_origin(origin)) for origin in CandidateOrigin]
        self.assertTrue(all(outcome == decisions[0] for outcome in decisions))

    def test_same_invalid_semantics_have_origin_invariant_decision(self):
        value = candidate(FACT + " See https://support.example/unloaded.")
        decisions = [decision(value.with_origin(origin)) for origin in CandidateOrigin]
        self.assertTrue(all(outcome == decisions[0] for outcome in decisions))
        self.assertIsNot(decisions[0].status, AcceptanceStatus.ACCEPTED)

    def test_source_count_does_not_rescue_global_failure(self):
        data = inputs()
        data[0]["sources"].extend(source("https://research.example/page" + str(index)) for index in range(5))
        data[2].verification_state["effective_supported"] = False
        for origin in CandidateOrigin:
            self.assertNotAccepted(candidate(data=data, origin=origin), PUBLIC_GLOBAL_SUPPORT)

    def test_scope_verifier_limitation_is_retained_without_universal_rejection(self):
        value = candidate()
        self.assertEqual(value.evidence.metadata["public_requirements"]["scope_support"], "verifier_only")
        self.assertEqual(value.evidence.metadata["verifier_source_bindings"], "unavailable")
        self.assertIs(decision(value).status, AcceptanceStatus.ACCEPTED)

    def test_explicit_scope_mismatch_is_representable_generically(self):
        data = inputs()
        data[0]["required_source_scope"] = {"region": "north"}
        data[0]["sources"][0]["source_scope"] = {"region": "south"}
        self.assertNotAccepted(candidate(data=data), INSUFFICIENT_SCOPE_SUPPORT)

    def test_matching_explicit_scope_can_satisfy_scope_obligation(self):
        data = inputs()
        data[0]["required_source_scope"] = {"region": "north"}
        data[0]["sources"][0]["source_scope"] = {"region": "north"}
        self.assertIs(decision(candidate(data=data)).status, AcceptanceStatus.ACCEPTED)

    def test_unresolved_structured_query_constraint_is_not_certainty(self):
        data = inputs()
        data[0]["unresolved_query_constraints"] = [{"kind": "regional_scope"}]
        self.assertNotAccepted(candidate(data=data), INSUFFICIENT_SCOPE_SUPPORT)

    def test_currentness_requirement_is_retained(self):
        data = inputs()
        data[0]["freshness_sensitive"] = True
        value = candidate(data=data)
        self.assertIs(value.contract.metadata["freshness_required"], True)
        self.assertNotAccepted(value, INSUFFICIENT_CURRENTNESS_SUPPORT)

    def test_packet_freshness_requirement_is_retained(self):
        data = inputs()
        parsed = json.loads(data[1])
        parsed["freshness_required"] = True
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        value = candidate(data=(data[0], packet, data[2]))
        self.assertNotAccepted(value, INSUFFICIENT_CURRENTNESS_SUPPORT)

    def test_published_date_alone_does_not_establish_currentness(self):
        data = inputs()
        data[0]["freshness_sensitive"] = True
        data[0]["sources"][0]["published_date"] = "2029-01-01"
        self.assertNotAccepted(candidate(data=data), INSUFFICIENT_CURRENTNESS_SUPPORT)

    def test_explicit_core_current_as_of_support_can_satisfy_obligation(self):
        data = inputs()
        data[0]["freshness_sensitive"] = True
        data[0]["required_current_as_of"] = "2027-03-14"
        data[0]["sources"][0]["current_as_of"] = "2027-03-14"
        self.assertIs(decision(candidate(data=data)).status, AcceptanceStatus.ACCEPTED)

    def test_evergreen_without_date_is_accepted(self):
        data = inputs()
        del data[0]["sources"][0]["published_date"]
        self.assertIs(decision(candidate(data=data)).status, AcceptanceStatus.ACCEPTED)

    def test_assistant_history_is_not_an_adapter_input(self):
        data = inputs()
        data[0]["conversation"] = [{"role": "assistant", "content": "The orchard contains eighty trees."}]
        self.assertEqual(candidate(data=data).evidence.authoritative_claims, (FACT,))

    def test_other_contract_lanes_do_not_apply_public_validator(self):
        value = candidate()
        for runtime in (contract(intent="share_opinion"), contract(intent="consequential_advice"),
                        contract(authority="media_research"), contract(epistemic_mode="stable_model_knowledge"),
                        contract(intent="recommendation_request"), contract(intent="casual_conversation")):
            with self.subTest(runtime=runtime):
                other = replace(value, contract=runtime)
                self.assertIsNone(validate_public(other, interpret_text(other.text)))


if __name__ == "__main__":
    unittest.main()
