"""Source annotation calibration remains observational and origin invariant."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_public import (
    INSUFFICIENT_CURRENTNESS_SUPPORT, INSUFFICIENT_SCOPE_SUPPORT,
    OFFICIAL_SOURCE_SUPPORT, PUBLIC_SENTENCE_SUPPORT, PUBLIC_VERIFIER_CONSISTENCY,
    SOURCE_IDENTITY, SOURCE_READ_PROVENANCE,
)
from core.answer_candidate import AcceptanceStatus, CandidateOrigin
from core.public_answer_evidence import build_public_answer_candidate, public_packet_digest
from research.public_factual_grounding import _split_draft_sentences
from test_core_milestone3b3a_public_evidence import FACT, URL, contract, inputs, source


def annotations(text, packet):
    return dict(version=1, status="complete", assessed_draft_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                packet_digest=public_packet_digest(packet), sentences=[{
                    "index": index, "claim_kind": "factual", "source_ids": ["S1"],
                    "witnesses": [{"source_id": "S1", "quote": FACT}],
                    "provenance_claim": "none", "scope_status": "supported",
                } for index, _ in enumerate(_split_draft_sentences(text), 1)])


def make(text=FACT, *, data=None, binding=None, runtime=None, user_input="", origin=CandidateOrigin.GENERATED):
    result, packet, verified = data or inputs(text)
    binding = annotations(text, packet) if binding is None else binding
    return build_public_answer_candidate(text=text, contract=runtime or contract(), research_result=result,
                                         evidence_packet=packet, verification_result=verified, origin=origin,
                                         source_bindings=binding, user_input=user_input)


def evaluate(value):
    return CoreAcceptanceEvaluator().evaluate(value)


class PublicCalibrationTests(unittest.TestCase):
    def not_accepted(self, value, invariant):
        result = evaluate(value)
        self.assertIsNot(result.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(invariant, result.violated_invariants)
        return result

    def test_complete_actual_bindings_are_available(self):
        value = make()
        self.assertEqual(value.evidence.metadata["verifier_source_bindings"], "available")
        self.assertEqual(value.evidence.metadata["public_requirements"]["scope_support"], "bound_verifier")
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_real_evidence_ids_are_retained_per_unit(self):
        value = make()
        result = evaluate(value)
        self.assertEqual(result.metadata["units"][0]["supported_by"], (value.evidence.evidence[0].evidence_id,))

    def test_bindings_are_not_all_admitted_sources(self):
        data = inputs()
        extra = source("https://research.example/second")
        data[0]["sources"].append(extra)
        parsed = json.loads(data[1])
        parsed["sources"].append({"source_id": "S2", "title": "Second guide", "url": extra["url"], "content_excerpt": FACT})
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        value = make(data=(data[0], packet, data[2]))
        self.assertEqual(len(value.evidence.authoritative_evidence), 2)
        self.assertEqual(evaluate(value).metadata["units"][0]["supported_by"], (value.evidence.evidence[0].evidence_id,))

    def test_loaded_url_must_match_its_sentences_actual_binding(self):
        text = "I loaded https://research.example/second."
        data = inputs(text)
        extra = source("https://research.example/second")
        data[0]["sources"].append(extra)
        parsed = json.loads(data[1])
        parsed["sources"].append({"source_id": "S2", "title": "Second guide", "url": extra["url"], "content_excerpt": FACT})
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        binding = annotations(text, packet)
        binding["sentences"][0].update(provenance_claim="read")
        self.not_accepted(make(text, data=(data[0], packet, data[2]), binding=binding), SOURCE_IDENTITY)

    def test_unknown_id_cannot_become_authority(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["source_ids"] = ["S9"]
        binding["sentences"][0]["witnesses"] = [{"source_id": "S9", "quote": FACT}]
        self.not_accepted(make(data=data, binding=binding), PUBLIC_VERIFIER_CONSISTENCY)

    def test_search_only_identity_cannot_become_binding(self):
        data = inputs()
        data[0]["discovered_sources"].append({"source_id": "S9", "url": "https://support.example/unread", "snippet": FACT})
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["source_ids"] = ["S9"]
        binding["sentences"][0]["witnesses"] = []
        self.not_accepted(make(data=data, binding=binding), PUBLIC_VERIFIER_CONSISTENCY)

    def test_rejected_read_source_does_not_support_binding(self):
        data = inputs()
        data[0]["sources"][0]["accepted_as_evidence"] = False
        self.not_accepted(make(data=data), PUBLIC_VERIFIER_CONSISTENCY)

    def test_substituted_quote_is_not_evidence(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["witnesses"][0]["quote"] = "The orchard contains sixty pear trees."
        self.not_accepted(make(data=data, binding=binding), PUBLIC_VERIFIER_CONSISTENCY)

    def test_quote_whitespace_normalization_does_not_change_authority(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["witnesses"][0]["quote"] = "The orchard\ncontains twelve pear trees."
        self.assertIs(evaluate(make(data=data, binding=binding)).status, AcceptanceStatus.ACCEPTED)

    def test_factual_binding_without_witness_is_not_accepted(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["witnesses"] = []
        self.not_accepted(make(data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_read_identity_only_can_use_actual_core_provenance(self):
        text = "I loaded " + URL + "."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0]["witnesses"] = []
        binding["sentences"][0]["provenance_claim"] = "read"
        self.assertIs(evaluate(make(text, data=data, binding=binding, runtime=contract(metadata={"source_read_required": True}))).status,
                      AcceptanceStatus.ACCEPTED)

    def test_read_identity_does_not_cover_appended_external_claim(self):
        text = "I loaded " + URL + " and the grove contains sixty trees."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0]["witnesses"] = []
        binding["sentences"][0]["provenance_claim"] = "read"
        self.not_accepted(make(text, data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_anaphoric_read_is_bound_to_single_actual_requested_source(self):
        text = "I did load it."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0].update(witnesses=[], provenance_claim="read", scope_status="not_applicable")
        runtime = contract(metadata={"source_read_required": True, "requested_source_urls": (URL,)})
        self.assertIs(evaluate(make(text, data=data, binding=binding, runtime=runtime)).status, AcceptanceStatus.ACCEPTED)

    def test_anaphoric_read_without_known_request_target_does_not_gain_authority(self):
        text = "I did load it."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0].update(witnesses=[], provenance_claim="read", scope_status="not_applicable")
        self.not_accepted(make(text, data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_generic_read_claim_without_annotations_fails_observationally(self):
        text = "I did load it."
        data = inputs(text)
        value = build_public_answer_candidate(text=text, contract=contract(), research_result=data[0],
                                              evidence_packet=data[1], verification_result=data[2])
        self.not_accepted(value, SOURCE_READ_PROVENANCE)

    def test_generic_source_assertion_without_annotations_fails_observationally(self):
        text = "The source says the orchard contains twelve pear trees."
        data = inputs(text)
        value = build_public_answer_candidate(text=text, contract=contract(), research_result=data[0],
                                              evidence_packet=data[1], verification_result=data[2])
        self.not_accepted(value, SOURCE_READ_PROVENANCE)

    def test_known_concrete_core_read_identity_keeps_legacy_fixture_support(self):
        text = "I loaded " + URL + "."
        data = inputs(text)
        value = build_public_answer_candidate(text=text, contract=contract(), research_result=data[0],
                                              evidence_packet=data[1], verification_result=data[2])
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(value.evidence.metadata["verifier_source_bindings"], "unavailable")

    def test_unavailable_shadow_client_does_not_create_malformed_annotations(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding.update(status="unavailable", sentences=[], failure="transport_unavailable")
        value = make(data=data, binding=binding)
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["status"], "unavailable")
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_unavailable_transport_issues_become_bounded_reason(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding.update(status="unavailable", sentences=[], issues=("binding_transport",))
        normalized = make(data=data, binding=binding).evidence.metadata["public_source_bindings"]
        self.assertEqual(normalized["status"], "unavailable")
        self.assertEqual(normalized["failure"], "evaluation_failed")

    def test_timeout_capability_issue_does_not_emit_raw_prose(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding.update(status="unavailable", sentences=[], issues=("binding_timeout_capability", "Private detail"))
        normalized = make(data=data, binding=binding).evidence.metadata["public_source_bindings"]
        self.assertEqual(normalized["failure"], "transport_unavailable")
        self.assertNotIn("Private detail", repr(normalized))

    def test_malformed_binding_cause_is_not_relabelled_incomplete(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding.update(status="malformed", sentences=[], issues=("binding_literal_witness",))
        normalized = make(data=data, binding=binding).evidence.metadata["public_source_bindings"]
        self.assertEqual(normalized["status"], "malformed")
        self.assertEqual(normalized["failure"], "invalid_binding")

    def test_scope_negative_remains_negative_despite_old_global_success(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["scope_status"] = "unsupported"
        self.not_accepted(make(data=data, binding=binding), INSUFFICIENT_SCOPE_SUPPORT)

    def test_scope_uncertain_is_not_silently_certain(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["scope_status"] = "uncertain"
        self.not_accepted(make(data=data, binding=binding), INSUFFICIENT_SCOPE_SUPPORT)

    def test_scope_not_applicable_cannot_mask_factual_scope(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["scope_status"] = "not_applicable"
        self.not_accepted(make(data=data, binding=binding), INSUFFICIENT_SCOPE_SUPPORT)

    def test_complete_binding_metadata_is_immutable(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        value = make(data=data, binding=binding)
        binding["sentences"][0]["source_ids"].append("S8")
        binding["sentences"][0]["witnesses"][0]["quote"] = "Changed"
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["sentences"][0]["source_ids"], ("S1",))
        with self.assertRaises(TypeError):
            value.evidence.metadata["public_source_bindings"]["sentences"][0]["scope_status"] = "unsupported"

    def test_different_draft_cannot_reuse_binding(self):
        data = inputs()
        binding = annotations(FACT + " Extra.", data[1])
        self.not_accepted(make(data=data, binding=binding), PUBLIC_VERIFIER_CONSISTENCY)

    def test_different_packet_cannot_reuse_binding(self):
        data = inputs()
        binding = annotations(FACT, data[1] + " ")
        self.not_accepted(make(data=data, binding=binding), PUBLIC_VERIFIER_CONSISTENCY)

    def test_annotation_question_digest_is_retained(self):
        user_input = "Describe the orchard"
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["assessed_question_digest"] = hashlib.sha256(user_input.encode("utf-8")).hexdigest()
        value = make(data=data, binding=binding, user_input=user_input)
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["assessed_question_digest"], binding["assessed_question_digest"])
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_scope_annotation_cannot_be_reused_under_different_question(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["assessed_question_digest"] = hashlib.sha256("Describe the orchard".encode("utf-8")).hexdigest()
        value = make(data=data, binding=binding, user_input="Describe the marina")
        self.not_accepted(value, PUBLIC_VERIFIER_CONSISTENCY)
        self.assertEqual(value.evidence.metadata["verifier_source_bindings"], "unavailable")

    def test_duplicate_annotation_index_fails_closed_observationally(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"].append(copy.deepcopy(binding["sentences"][0]))
        self.not_accepted(make(data=data, binding=binding), PUBLIC_VERIFIER_CONSISTENCY)

    def test_missing_annotation_index_fails_closed_observationally(self):
        data = inputs(FACT + " The shed is empty.")
        binding = annotations(FACT + " The shed is empty.", data[1])
        binding["sentences"].pop()
        self.not_accepted(make(FACT + " The shed is empty.", data=data, binding=binding), PUBLIC_VERIFIER_CONSISTENCY)

    def test_self_declared_non_factual_cannot_mask_external_assertion(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0].update(claim_kind="non_factual", source_ids=[], witnesses=[], scope_status="not_applicable")
        self.not_accepted(make(data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_self_declared_limitation_cannot_mask_external_assertion(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        self.not_accepted(make(data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_honest_currentness_limitation_does_not_assert_current_state(self):
        text = "I cannot verify the current orchard state from the available sources."
        data = inputs(text)
        data[0]["freshness_sensitive"] = True
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        self.assertIs(evaluate(make(text, data=data, binding=binding)).status, AcceptanceStatus.ACCEPTED)

    def test_external_availability_statement_is_not_epistemic_uncertainty(self):
        text = "The portal is unavailable."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        self.not_accepted(make(text, data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_nominal_state_limitation_cannot_erase_currentness_obligation(self):
        text = "The portal is unavailable."
        data = inputs(text)
        data[0]["freshness_sensitive"] = True
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        result = self.not_accepted(make(text, data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)
        self.assertIn(INSUFFICIENT_CURRENTNESS_SUPPORT, result.violated_invariants)

    def test_valid_contracted_epistemic_limitation_is_accepted(self):
        for text in ("I don't know enough to establish the current orchard state.",
                     "I can't establish the current orchard state.",
                     "I can’t establish the current orchard state."):
            data = inputs(text)
            data[0]["freshness_sensitive"] = True
            binding = annotations(text, data[1])
            binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
            with self.subTest(text=text):
                self.assertIs(evaluate(make(text, data=data, binding=binding)).status, AcceptanceStatus.ACCEPTED)

    def test_varied_first_person_epistemic_confidence_is_bounded(self):
        for text in ("I'm not familiar enough with 'grellium' to define it reliably without more context.",
                     "I am unfamiliar with the phase lattice.",
                     "I am not sufficiently confident about 'norvex' to explain it accurately.",
                     "I am uncertain about the rivet lattice.",
                     "My knowledge of the phase lattice is too limited to describe it reliably.",
                     "I don't have enough information about 'norvex' to identify it."):
            data = inputs(text)
            data[0]["freshness_sensitive"] = True
            binding = annotations(text, data[1])
            binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
            with self.subTest(text=text):
                self.assertIs(evaluate(make(text, data=data, binding=binding)).status, AcceptanceStatus.ACCEPTED)

    def test_real_core_unfamiliarity_repair_is_epistemic_not_absence(self):
        from core.epistemic_calibration import repair_unjustified_lexical_denial
        text, changed = repair_unjustified_lexical_denial("What does 'grellium' mean?", "Grellium is not a real word.", epistemic_mode="public_source_verified")
        self.assertTrue(changed)
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        self.assertIs(evaluate(make(text, data=data, binding=binding)).status, AcceptanceStatus.ACCEPTED)

    def test_epistemic_confidence_cannot_hide_unsupported_clause(self):
        for text in ("I'm unfamiliar with norvex, but it has fourteen chambers.",
                     "I'm unfamiliar with norvex, recovered twenty capsules.",
                     "I'm unfamiliar with norvex -- costs six credits.",
                     "I'm not familiar enough with 'norvex is a metal' to define it.",
                     "My knowledge of norvex is too limited to explain it and the portal is unavailable.",
                     "I'm unfamiliar with norvex; search for it now."):
            data = inputs(text)
            binding = annotations(text, data[1])
            for entry in binding["sentences"]:
                entry.update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
            with self.subTest(text=text):
                self.not_accepted(make(text, data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_epistemic_confidence_does_not_authorize_appended_exact_answer(self):
        text = "I'm unfamiliar with norvex. The current value is 436."
        data = inputs(text)
        data[0]["freshness_sensitive"] = True
        binding = annotations(text, data[1])
        for entry in binding["sentences"]:
            entry.update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        result = self.not_accepted(make(text, data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)
        self.assertIn(INSUFFICIENT_CURRENTNESS_SUPPORT, result.violated_invariants)

    def test_limitation_with_extra_factual_sentence_does_not_mask_currentness(self):
        text = "I cannot verify the current orchard state. The orchard contains twelve pear trees."
        data = inputs(text)
        data[0]["freshness_sensitive"] = True
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        self.not_accepted(make(text, data=data, binding=binding), INSUFFICIENT_CURRENTNESS_SUPPORT)

    def test_limitation_does_not_authorize_lookup_offer(self):
        text = "I cannot verify the current orchard state. Would you like me to search?"
        data = inputs(text)
        binding = annotations(text, data[1])
        for entry in binding["sentences"]:
            entry.update(claim_kind="limitation", source_ids=[], witnesses=[], scope_status="not_applicable")
        self.not_accepted(make(text, data=data, binding=binding), PUBLIC_SENTENCE_SUPPORT)

    def test_read_requirement_not_satisfied_by_unavailable_annotations(self):
        data = inputs()
        value = build_public_answer_candidate(text=FACT, contract=contract(metadata={"source_read_required": True}),
                                              research_result=data[0], evidence_packet=data[1], verification_result=data[2])
        self.not_accepted(value, SOURCE_READ_PROVENANCE)

    def test_official_requirement_uses_bound_sources(self):
        data = inputs()
        data[0]["sources"][0]["authority_tier"] = "independent_editorial"
        self.not_accepted(make(data=data, runtime=contract(metadata={"official_source_required": True})), OFFICIAL_SOURCE_SUPPORT)

    def test_primary_institutional_source_satisfies_primary_requirement(self):
        data = inputs()
        data[0]["sources"][0]["authority_tier"] = "primary_institutional"
        value = make(data=data, runtime=contract(metadata={"primary_source_required": True}))
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_primary_official_source_satisfies_primary_requirement(self):
        self.assertIs(evaluate(make(runtime=contract(metadata={"primary_source_required": True}))).status,
                      AcceptanceStatus.ACCEPTED)

    def test_primary_institutional_source_does_not_satisfy_official_requirement(self):
        data = inputs()
        data[0]["sources"][0]["authority_tier"] = "primary_institutional"
        self.not_accepted(make(data=data, runtime=contract(metadata={"official_source_required": True})), OFFICIAL_SOURCE_SUPPORT)

    def test_ineligible_primary_source_is_not_authority(self):
        data = inputs()
        data[0]["sources"][0].update(authority_tier="primary_institutional", quality_eligible=False)
        self.not_accepted(make(data=data, runtime=contract(metadata={"primary_source_required": True})), OFFICIAL_SOURCE_SUPPORT)

    def test_independent_editorial_source_does_not_satisfy_primary_requirement(self):
        data = inputs()
        data[0]["sources"][0]["authority_tier"] = "independent_editorial"
        self.not_accepted(make(data=data, runtime=contract(metadata={"primary_source_required": True})), OFFICIAL_SOURCE_SUPPORT)

    def test_current_primary_requirement_remains_distinct_from_official(self):
        data = inputs()
        data[0]["sources"][0]["authority_tier"] = "primary_institutional"
        value = make(data=data, user_input="Use a primary source for this answer.")
        self.assertTrue(value.contract.metadata["primary_source_required"])
        self.assertFalse(value.contract.metadata["official_source_required"])
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_current_primary_request_needs_actual_bindings(self):
        data = inputs()
        data[0]["sources"][0]["authority_tier"] = "primary_institutional"
        value = build_public_answer_candidate(text=FACT, contract=contract(), research_result=data[0],
                                              evidence_packet=data[1], verification_result=data[2],
                                              user_input="Use a primary source for this answer.")
        self.not_accepted(value, OFFICIAL_SOURCE_SUPPORT)

    def test_unbound_secondary_source_does_not_contaminate_official_binding(self):
        data = inputs()
        extra = source("https://research.example/secondary", authority_tier="independent_editorial")
        data[0]["sources"].append(extra)
        parsed = json.loads(data[1])
        parsed["sources"].append({"source_id": "S2", "url": extra["url"], "title": "Secondary guide", "content_excerpt": FACT})
        packet = json.dumps(parsed)
        data[2].verification_state["packet_digest"] = public_packet_digest(packet)
        value = make(data=(data[0], packet, data[2]), runtime=contract(metadata={"official_source_required": True}))
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_exact_requested_source_cannot_be_same_host_other_path(self):
        value = make(runtime=contract(metadata={"source_read_required": True, "requested_source_urls": (URL + "/different",)}))
        self.not_accepted(value, SOURCE_IDENTITY)

    def test_exact_requested_url_must_be_preserved_in_answer(self):
        value = make(runtime=contract(metadata={"exact_source_required": True, "requested_source_urls": (URL,)}))
        self.not_accepted(value, SOURCE_IDENTITY)

    def test_actual_source_url_request_without_given_url_must_still_be_completed(self):
        value = make(runtime=contract(metadata={"exact_source_required": True}))
        self.not_accepted(value, SOURCE_IDENTITY)

    def test_actual_loaded_url_can_complete_identity_obligation(self):
        text = "Source URL: " + URL + "."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0].update(witnesses=[], provenance_claim="citation", scope_status="not_applicable")
        value = make(text, data=data, binding=binding, runtime=contract(metadata={"exact_source_required": True}))
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_current_turn_official_read_and_identity_obligations_survive_query_rewrite(self):
        data = inputs()
        data[0]["original_query"] = "Describe the orchard"
        value = make(data=data, user_input="Read the official documentation and give me the actual source URL.")
        self.assertTrue(value.contract.metadata["official_source_required"])
        self.assertTrue(value.contract.metadata["source_read_required"])
        self.assertTrue(value.contract.metadata["exact_source_required"])

    def test_explicit_current_user_official_requirement_needs_inspectable_binding(self):
        data = inputs()
        value = build_public_answer_candidate(text=FACT, contract=contract(), research_result=data[0],
                                              evidence_packet=data[1], verification_result=data[2],
                                              user_input="Use an official source for the answer.")
        self.not_accepted(value, OFFICIAL_SOURCE_SUPPORT)

    def test_explicit_current_user_url_requirement_needs_inspectable_binding(self):
        text = "I loaded " + URL + "."
        data = inputs(text)
        value = build_public_answer_candidate(text=text, contract=contract(), research_result=data[0],
                                              evidence_packet=data[1], verification_result=data[2],
                                              user_input="Give the actual source URL you loaded.")
        self.not_accepted(value, SOURCE_IDENTITY)

    def test_read_and_scope_failures_not_masked_by_currentness(self):
        data = inputs()
        data[0]["freshness_sensitive"] = True
        binding = annotations(FACT, data[1])
        binding["sentences"][0].update(scope_status="unsupported", source_ids=[], witnesses=[])
        result = evaluate(make(data=data, binding=binding, runtime=contract(metadata={"source_read_required": True})))
        for invariant in (SOURCE_READ_PROVENANCE, INSUFFICIENT_SCOPE_SUPPORT, INSUFFICIENT_CURRENTNESS_SUPPORT):
            self.assertIn(invariant, result.violated_invariants)

    def test_origin_invariance_for_complete_binding(self):
        value = make()
        outcomes = [evaluate(value.with_origin(origin)) for origin in CandidateOrigin]
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_origin_invariance_for_invalid_binding(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["scope_status"] = "unsupported"
        value = make(data=data, binding=binding)
        outcomes = [evaluate(value.with_origin(origin)) for origin in CandidateOrigin]
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes))

    def test_path_metadata_does_not_grant_authority(self):
        value = make(runtime=contract(metadata={"source_read_required": True}))
        original = evaluate(value)
        other = replace(value, validation_metadata={"path": "critical_core", "official": True})
        self.assertEqual(evaluate(other), original)


if __name__ == "__main__":
    unittest.main()
