"""Core acceptance policy is independent of wording's production origin.

Invented neutral examples exercise the real evaluator and typed canonical
evidence. No model, benchmark, tool, publication path or live repository is used.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.acceptance_evaluator import (
    CONDITIONAL_SCOPE,
    CoreAcceptanceEvaluator,
    EVIDENCE_AUTHORITY,
    MODEL_KNOWLEDGE_NOT_PROOF,
    REQUIRED_CLAIMS,
    SEMANTIC_COVERAGE,
    SERIOUS_CONTRACT_TONE,
    SOURCE_SCOPE,
    UNCERTAINTY_PRESERVATION,
    USER_FACT_CONSISTENCY,
    USER_OBSERVATION_SUPPORT,
)
from core.answer_candidate import (
    AcceptanceStatus,
    AnswerCandidate,
    CandidateOrigin,
)
from core.answer_contract_runtime import AnswerContractRuntime
from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus
from core.evidence_normalization import (
    combine_evidence,
    normalize_live_conversation,
    normalize_stable_model_authority,
    normalize_user_turn,
)


def user_contract(**overrides):
    values = dict(
        task="respond to supplied user context",
        speech_act="statement",
        intent="conversation",
        authority="user_context",
        epistemic_mode="user_context_only",
        allow_new_factual_claims=False,
    )
    values.update(overrides)
    return AnswerContractRuntime(**values)


def source_contract(kind=EvidenceKind.PUBLIC_SOURCE, **overrides):
    values = dict(
        task="answer from retrieved evidence",
        speech_act="question",
        intent="factual_question",
        authority="media_research" if kind is EvidenceKind.MEDIA_SOURCE else "public_web",
        epistemic_mode="public_source_verified",
        allow_new_factual_claims=False,
    )
    values.update(overrides)
    return AnswerContractRuntime(**values)


def canonical_bundle(*items, authority="user_context", uncertainty=None, **metadata):
    return EvidenceBundle(
        authority=authority,
        evidence=list(items),
        canonical=True,
        success=any(item.status is EvidenceStatus.ADMISSIBLE for item in items),
        uncertainty=uncertainty,
        metadata=metadata,
    ).snapshot()


def source_fact(claim, *, kind=EvidenceKind.PUBLIC_SOURCE, status=EvidenceStatus.ADMISSIBLE, **overrides):
    values = dict(
        claim=claim,
        provenance="core_media_source" if kind is EvidenceKind.MEDIA_SOURCE else "core_public_source",
        confidence="source_assertion",
        kind=kind,
        status=status,
        evidence_id="neutral-source",
        source_id="S1",
        source_name="Neutral survey",
        source_url="https://survey.example/record",
        source_quality="primary",
        authority_tier="primary_institutional",
        quality_eligible=True,
        authority_scope="retrieved_source_assertions",
    )
    values.update(overrides)
    return Evidence(**values)


def core_fact(claim="The sample contains four entries.", **overrides):
    values = dict(
        claim=claim,
        provenance="core_arithmetic",
        confidence="verified",
        kind=EvidenceKind.CORE_RESULT,
        status=EvidenceStatus.ADMISSIBLE,
        evidence_id="sample-count",
        authority_scope="core_result",
    )
    values.update(overrides)
    return Evidence(**values)


class CoreAcceptanceEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = CoreAcceptanceEvaluator()

    def evaluate_origins(self, text, contract, evidence, expected, **candidate_fields):
        candidate = AnswerCandidate(
            text=text,
            origin=CandidateOrigin.GENERATED,
            contract=contract,
            evidence=evidence,
            **candidate_fields,
        )
        baseline = self.evaluator.evaluate(candidate)
        self.assertEqual(baseline.status, expected, baseline)
        self.assertEqual(baseline.evaluated_text, text)
        if expected is AcceptanceStatus.ACCEPTED:
            self.assertFalse(baseline.violated_invariants)
        else:
            self.assertTrue(baseline.reasons)
            self.assertTrue(baseline.violated_invariants)
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                transported = candidate.with_origin(origin)
                self.assertEqual(self.evaluator.evaluate(transported), baseline)
                self.assertEqual(transported.text, text)
        return baseline

    def test_current_user_preference_cannot_be_negated_in_social_wording(self):
        evidence = normalize_user_turn("I like quiet rooms.")
        result = self.evaluate_origins(
            "You dislike quiet rooms.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )
        self.assertIn(USER_FACT_CONSISTENCY, result.violated_invariants)

    def test_current_user_preference_cannot_be_replaced_with_unsupported_value(self):
        evidence = normalize_user_turn("I prefer quiet rooms.")
        self.evaluate_origins(
            "You prefer noisy rooms.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )

    def test_current_user_fact_cannot_be_replaced(self):
        evidence = normalize_user_turn("My parcel is amber.")
        self.evaluate_origins(
            "Your parcel is green.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )

    def test_live_user_fact_cannot_be_contradicted(self):
        evidence = normalize_live_conversation([
            {"role": "user", "content": "I like quiet rooms."},
        ])
        self.evaluate_origins(
            "You dislike quiet rooms.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )

    def test_explicit_current_correction_supersedes_the_older_fact(self):
        old = normalize_live_conversation([
            {"role": "user", "content": "My parcel is green.", "evidence_id": "old-parcel"},
        ])
        correction = normalize_user_turn(
            {"role": "user", "raw_text": "My parcel is amber.", "intent": "self_correction"},
            supersedes=("old-parcel",),
        )
        evidence = combine_evidence(old, correction, authority="user_context")
        self.evaluate_origins(
            "Your parcel is green.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )
        self.evaluate_origins(
            "Your parcel is amber.", user_contract(), evidence,
            AcceptanceStatus.ACCEPTED,
        )

    def test_current_turn_fact_controls_conflicting_older_live_support(self):
        old = normalize_live_conversation([
            {"role": "user", "content": "My parcel is green."},
        ])
        current = normalize_user_turn("My parcel is amber.")
        evidence = combine_evidence(old, current, authority="user_context")
        result = self.evaluate_origins(
            "Your parcel is green.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )
        self.assertIn(USER_FACT_CONSISTENCY, result.violated_invariants)
        self.evaluate_origins(
            "Your parcel is amber.", user_contract(), evidence,
            AcceptanceStatus.ACCEPTED,
        )

    def test_unobserved_physical_action_is_rejected_under_every_origin(self):
        result = self.evaluate_origins(
            "You are stretching near the window.", user_contract(),
            canonical_bundle(), AcceptanceStatus.REJECTED,
        )
        self.assertIn(USER_OBSERVATION_SUPPORT, result.violated_invariants)

    def test_observed_user_supplied_physical_action_is_bounded_and_accepted(self):
        evidence = normalize_user_turn("I am stretching near the window.")
        self.evaluate_origins(
            "You are stretching near the window.", user_contract(), evidence,
            AcceptanceStatus.ACCEPTED,
        )

    def test_question_cannot_presuppose_an_unobserved_user_action(self):
        result = self.evaluate_origins(
            "Why are you stretching near the window?",
            user_contract(allow_follow_up_question=True), canonical_bundle(),
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        )
        self.assertIn(SEMANTIC_COVERAGE, result.violated_invariants)

    def test_assistant_authored_action_is_not_promoted_to_user_evidence(self):
        evidence = normalize_live_conversation([
            {"role": "assistant", "content": "You are stretching near the window."},
        ])
        self.evaluate_origins(
            "You are stretching near the window.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )

    def test_public_source_cannot_establish_a_present_user_observation(self):
        claim = "You are stretching near the window."
        evidence = canonical_bundle(source_fact(claim), authority="public_web")
        self.evaluate_origins(claim, user_contract(), evidence, AcceptanceStatus.REJECTED)

    def test_first_person_source_claim_is_not_promoted_to_a_user_preference(self):
        evidence = canonical_bundle(source_fact("I like quiet rooms."), authority="public_web")
        self.evaluate_origins(
            "You like quiet rooms.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )

    def test_serious_contract_rejects_ridicule_and_blame_for_all_origins(self):
        for contract in (
            user_contract(intent="consequential_advice"),
            user_contract(metadata={"seriousness": "high"}),
        ):
            with self.subTest(contract=contract):
                result = self.evaluate_origins(
                    "You are an idiot for causing this.", contract,
                    canonical_bundle(), AcceptanceStatus.REJECTED,
                )
                self.assertIn(SERIOUS_CONTRACT_TONE, result.violated_invariants)

    def test_serious_tone_is_not_triggered_by_candidate_origin(self):
        contract = user_contract(metadata={"seriousness": "high"})
        self.evaluate_origins(
            "That sounds difficult.", contract, canonical_bundle(),
            AcceptanceStatus.ACCEPTED,
        )

    def test_serious_ridicule_is_not_salvaged_into_an_otherwise_supported_answer(self):
        fact = core_fact()
        result = self.evaluate_origins(
            fact.claim + " You are an idiot for causing this.",
            user_contract(intent="consequential_advice", authority="core_results", epistemic_mode="verified_core"),
            canonical_bundle(fact, authority="core_results"), AcceptanceStatus.REJECTED,
        )
        self.assertIn(SERIOUS_CONTRACT_TONE, result.violated_invariants)
        self.assertFalse(result.accepted_sentences)

    def test_unavailable_public_source_cannot_support_its_same_claim_string(self):
        claim = "The orchard has twelve pear trees."
        evidence = canonical_bundle(
            source_fact(claim, status=EvidenceStatus.UNAVAILABLE), authority="public_web",
        )
        result = self.evaluate_origins(claim, source_contract(), evidence, AcceptanceStatus.REJECTED)
        self.assertIn(EVIDENCE_AUTHORITY, result.violated_invariants)

    def test_rejected_media_source_cannot_support_its_same_claim_string(self):
        claim = "The story opens in a coastal village."
        evidence = canonical_bundle(
            source_fact(claim, kind=EvidenceKind.MEDIA_SOURCE, status=EvidenceStatus.REJECTED),
            authority="media_research",
        )
        self.evaluate_origins(
            claim, source_contract(EvidenceKind.MEDIA_SOURCE), evidence,
            AcceptanceStatus.REJECTED,
        )

    def test_valid_public_and_media_sources_remain_accepted_in_their_contracts(self):
        for kind, claim in (
            (EvidenceKind.PUBLIC_SOURCE, "The orchard has twelve pear trees."),
            (EvidenceKind.MEDIA_SOURCE, "The story opens in a coastal village."),
        ):
            with self.subTest(kind=kind):
                evidence = canonical_bundle(source_fact(claim, kind=kind), authority=source_contract(kind).authority)
                self.evaluate_origins(claim, source_contract(kind), evidence, AcceptanceStatus.ACCEPTED)

    def test_public_contract_does_not_promote_the_same_user_claim_into_public_evidence(self):
        claim = "The orchard has twelve pear trees."
        evidence = normalize_user_turn(claim)
        self.evaluate_origins(claim, source_contract(), evidence, AcceptanceStatus.REJECTED)

    def test_source_kind_does_not_cross_the_required_authority_domain(self):
        claim = "The orchard has twelve pear trees."
        evidence = canonical_bundle(source_fact(claim, kind=EvidenceKind.MEDIA_SOURCE), authority="media_research")
        result = self.evaluate_origins(claim, source_contract(), evidence, AcceptanceStatus.REJECTED)
        self.assertIn(SOURCE_SCOPE, result.violated_invariants)

    def test_source_claim_scope_and_provenance_are_required_even_for_exact_text(self):
        claim = "The orchard has twelve pear trees."
        for fields in (
            {"authority_scope": "what_the_user_stated"},
            {"provenance": "non_user_conversation"},
        ):
            with self.subTest(fields=fields):
                evidence = canonical_bundle(source_fact(claim, **fields), authority="public_web")
                self.evaluate_origins(claim, source_contract(), evidence, AcceptanceStatus.REJECTED)

    def test_source_quality_floor_is_contract_specific_and_origin_independent(self):
        claim = "The orchard has twelve pear trees."
        evidence = canonical_bundle(source_fact(claim, quality_eligible=False), authority="public_web")
        self.evaluate_origins(claim, source_contract(), evidence, AcceptanceStatus.ACCEPTED)
        self.evaluate_origins(
            claim, source_contract(metadata={"source_quality_required": "true"}),
            evidence, AcceptanceStatus.REJECTED,
        )

    def test_source_rejection_metadata_cannot_be_erased_by_admissible_status(self):
        claim = "The orchard has twelve pear trees."
        for source_data in (
            {"accepted_as_evidence": False},
            {"relevance_status": "rejected"},
            {"read_success": False},
            {"read_result": {"success": False}},
        ):
            with self.subTest(source_data=source_data):
                evidence = canonical_bundle(source_fact(claim, data=source_data), authority="public_web")
                result = self.evaluate_origins(claim, source_contract(), evidence, AcceptanceStatus.REJECTED)
                self.assertIn(EVIDENCE_AUTHORITY, result.violated_invariants)

    def test_missing_required_public_source_prerequisite_requires_replacement(self):
        self.evaluate_origins(
            "The lattice oscillates twice.", source_contract(), canonical_bundle(authority="public_web"),
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        )

    def test_supplied_premise_is_accepted_only_with_explicit_conditional_scope(self):
        evidence = normalize_user_turn("The reservoir is empty.", premise=True)
        contract = user_contract(epistemic_mode="user_premise_reasoning")
        self.evaluate_origins(
            "Assuming the reservoir is empty.", contract, evidence,
            AcceptanceStatus.ACCEPTED,
        )
        result = self.evaluate_origins(
            "The reservoir is empty.", contract, evidence,
            AcceptanceStatus.REJECTED,
        )
        self.assertIn(CONDITIONAL_SCOPE, result.violated_invariants)

    def test_premise_does_not_become_a_verified_public_fact(self):
        evidence = normalize_user_turn("The reservoir is empty.", premise=True)
        self.evaluate_origins(
            "The reservoir is empty.", source_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )

    def test_valid_bounded_current_user_response_is_accepted(self):
        self.evaluate_origins(
            "You like quiet rooms.", user_contract(), normalize_user_turn("I like quiet rooms."),
            AcceptanceStatus.ACCEPTED,
        )

    def test_verified_core_result_is_accepted_without_origin_privilege(self):
        fact = core_fact()
        contract = user_contract(authority="core_results", epistemic_mode="verified_core")
        self.evaluate_origins(
            fact.claim, contract, canonical_bundle(fact, authority="core_results"),
            AcceptanceStatus.ACCEPTED,
        )

    def test_core_result_status_scope_and_provenance_are_not_interchangeable(self):
        contract = user_contract(authority="core_results", epistemic_mode="verified_core")
        for fields in (
            {"status": EvidenceStatus.REJECTED},
            {"authority_scope": "conditional_premise"},
            {"provenance": "non_user_conversation"},
        ):
            with self.subTest(fields=fields):
                fact = core_fact(**fields)
                self.evaluate_origins(
                    fact.claim, contract, canonical_bundle(fact, authority="core_results"),
                    AcceptanceStatus.REJECTED,
                )

    def test_current_user_or_public_source_is_not_a_deterministic_core_result(self):
        claim = "The sample contains four entries."
        contract = user_contract(authority="core_results", epistemic_mode="verified_core")
        for evidence in (
            normalize_user_turn(claim),
            canonical_bundle(source_fact(claim), authority="public_web"),
        ):
            with self.subTest(evidence=evidence):
                self.evaluate_origins(claim, contract, evidence, AcceptanceStatus.REJECTED)

    def test_independently_supported_tool_claim_cannot_override_current_user_fact(self):
        current = normalize_user_turn("My parcel is amber.")
        observation = canonical_bundle(
            core_fact(
                "Your parcel is green.", provenance="core_observation",
                authority_scope="tool_observation",
            ),
            authority="core_results",
        )
        evidence = combine_evidence(current, observation, authority="user_context")
        result = self.evaluate_origins(
            "Your parcel is green.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )
        self.assertIn(USER_FACT_CONSISTENCY, result.violated_invariants)

    def test_stable_model_permission_is_a_capability_not_claim_support(self):
        contract = user_contract(
            authority="model_knowledge", epistemic_mode="stable_model_knowledge",
            allow_new_factual_claims=True,
        )
        evidence = normalize_stable_model_authority(contract)
        self.assertTrue(evidence.model_knowledge_permitted)
        self.assertFalse(evidence.authoritative_claims)
        result = self.evaluate_origins(
            "The lattice oscillates twice.", contract, evidence,
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        )
        self.assertIn(MODEL_KNOWLEDGE_NOT_PROOF, result.violated_invariants)

    def test_forged_candidate_validation_metadata_does_not_support_claims(self):
        self.evaluate_origins(
            "You are stretching near the window.", user_contract(), canonical_bundle(),
            AcceptanceStatus.REJECTED,
            validation_metadata={
                "supported": True,
                "accepted": True,
                "evidence_ids": ["invented-proof"],
                "sentence_assessments": [{"index": 1, "supported": True}],
            },
        )

    def test_contract_plain_verified_claim_list_is_not_typed_evidence(self):
        claim = "The orchard has twelve pear trees."
        contract = source_contract(verified_evidence_claims=(claim,))
        self.evaluate_origins(
            claim, contract, canonical_bundle(authority="public_web"),
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        )

    def test_explicit_uncertainty_can_be_preserved_but_not_filled_with_model_prose(self):
        reason = "The delivery time is unknown."
        uncertainty = Evidence(
            claim="", provenance="core_evidence_availability", confidence="unavailable",
            kind=EvidenceKind.UNCERTAINTY, status=EvidenceStatus.UNAVAILABLE,
            authority_scope="evidence_availability", limitations=(reason,),
        )
        evidence = canonical_bundle(uncertainty, uncertainty=reason)
        self.evaluate_origins(reason, user_contract(), evidence, AcceptanceStatus.ACCEPTED)
        result = self.evaluate_origins(
            "The delivery time is tomorrow morning.", user_contract(), evidence,
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        )
        self.assertIn(UNCERTAINTY_PRESERVATION, result.violated_invariants)

    def test_disclaimer_does_not_authorize_the_assertion_that_follows_it(self):
        reason = "The delivery time is unknown."
        evidence = canonical_bundle(uncertainty=reason)
        result = self.evaluate_origins(
            reason + " The delivery time is tomorrow morning.", user_contract(), evidence,
            AcceptanceStatus.SALVAGEABLE,
        )
        self.assertEqual(tuple(unit.index for unit in result.accepted_sentences), (1,))
        self.assertEqual(tuple(unit.text for unit in result.accepted_sentences), (reason,))

    def test_limitation_prefix_does_not_hide_a_secondary_assertion_in_one_unit(self):
        reason = "The delivery time is unknown."
        result = self.evaluate_origins(
            "I cannot establish the delivery time but it is tomorrow morning.",
            user_contract(), canonical_bundle(uncertainty=reason),
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        )
        self.assertIn(SEMANTIC_COVERAGE, result.violated_invariants)
        self.assertFalse(result.accepted_sentences)

    def test_premise_cannot_support_its_assertion_under_a_changed_condition(self):
        evidence = normalize_user_turn("The reservoir is empty.", premise=True)
        result = self.evaluate_origins(
            "If the reservoir is full, the reservoir is empty.",
            user_contract(epistemic_mode="user_premise_reasoning"), evidence,
            AcceptanceStatus.REJECTED,
        )
        self.assertIn(CONDITIONAL_SCOPE, result.violated_invariants)

    def test_unresolved_claims_fail_closed_instead_of_escaping_a_narrow_recognizer(self):
        result = self.evaluate_origins(
            "The lattice oscillates twice.", user_contract(), canonical_bundle(),
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        )
        self.assertIn(EVIDENCE_AUTHORITY, result.violated_invariants)

    def test_unresolved_clause_coverage_requires_replacement(self):
        result = self.evaluate_origins(
            "Given a delay, the lattice oscillates twice.",
            user_contract(), canonical_bundle(), AcceptanceStatus.REPLACEMENT_REQUIRED,
        )
        self.assertIn(SEMANTIC_COVERAGE, result.violated_invariants)

    def test_supported_unknown_domain_exact_text_is_accepted_as_a_core_result(self):
        fact = core_fact("The lattice oscillates twice.")
        self.evaluate_origins(
            fact.claim, user_contract(authority="core_results", epistemic_mode="verified_core"),
            canonical_bundle(fact, authority="core_results"), AcceptanceStatus.ACCEPTED,
        )

    def test_salvage_contains_only_independently_supported_sentences(self):
        fact = core_fact()
        text = fact.claim + " The lattice oscillates twice."
        result = self.evaluate_origins(
            text, user_contract(authority="core_results", epistemic_mode="verified_core"),
            canonical_bundle(fact, authority="core_results"), AcceptanceStatus.SALVAGEABLE,
        )
        self.assertEqual(tuple(unit.index for unit in result.accepted_sentences), (1,))
        self.assertEqual(tuple(unit.text for unit in result.accepted_sentences), (fact.claim,))

    def test_repeated_supported_sentences_retain_their_original_indexes(self):
        fact = core_fact()
        text = fact.claim + " " + fact.claim + " The lattice oscillates twice."
        result = self.evaluate_origins(
            text, user_contract(authority="core_results", epistemic_mode="verified_core"),
            canonical_bundle(fact, authority="core_results"), AcceptanceStatus.SALVAGEABLE,
        )
        self.assertEqual(tuple(unit.index for unit in result.accepted_sentences), (1, 2))
        self.assertEqual(tuple(unit.text for unit in result.accepted_sentences), (fact.claim, fact.claim))

    def test_salvage_cannot_drop_a_required_claim(self):
        fact = core_fact()
        contract = user_contract(
            authority="core_results", epistemic_mode="verified_core",
            required_claims=("The sample belongs to a curator.",),
        )
        result = self.evaluate_origins(
            fact.claim + " The lattice oscillates twice.", contract,
            canonical_bundle(fact, authority="core_results"), AcceptanceStatus.REPLACEMENT_REQUIRED,
        )
        self.assertFalse(result.accepted_sentences)
        self.assertIn(REQUIRED_CLAIMS, result.violated_invariants)

    def test_empty_or_whitespace_candidate_requires_replacement(self):
        for text in ("", "   "):
            with self.subTest(text=text):
                self.evaluate_origins(text, user_contract(), canonical_bundle(), AcceptanceStatus.REPLACEMENT_REQUIRED)

    def test_evaluator_does_not_mutate_candidate_or_evidence(self):
        evidence = normalize_user_turn("I like quiet rooms.")
        candidate = AnswerCandidate("You dislike quiet rooms.", CandidateOrigin.SALVAGE, user_contract(), evidence)
        before_evidence = candidate.evidence.to_dict()
        before_contract = candidate.contract
        result = self.evaluator.evaluate(candidate)
        self.assertEqual(candidate.text, "You dislike quiet rooms.")
        self.assertEqual(candidate.evidence.to_dict(), before_evidence)
        self.assertEqual(candidate.contract, before_contract)
        self.assertEqual(result.evaluated_text, candidate.text)


    def test_user_reporting_does_not_fulfil_a_required_factual_authority_domain(self):
        claim = "The sample contains four entries."
        evidence = normalize_user_turn(claim)
        for contract in (
            source_contract(),
            source_contract(EvidenceKind.MEDIA_SOURCE),
            user_contract(
                intent="factual_question", authority="core_results", epistemic_mode="verified_core",
            ),
        ):
            with self.subTest(contract=contract):
                result = self.evaluate_origins(
                    "You said the sample contains four entries.", contract, evidence,
                    AcceptanceStatus.REPLACEMENT_REQUIRED,
                )
                self.assertFalse(result.accepted_sentences)

    def test_wrong_source_attribution_is_rejected_even_when_the_body_matches(self):
        claim = "The orchard has twelve pear trees."
        evidence = canonical_bundle(source_fact(claim), authority="public_web")
        result = self.evaluate_origins(
            "According to Another survey, the orchard has twelve pear trees.",
            source_contract(), evidence, AcceptanceStatus.REJECTED,
        )
        self.assertIn(SOURCE_SCOPE, result.violated_invariants)

    def test_user_quotation_of_assistant_speech_does_not_confirm_its_facts(self):
        evidence = normalize_user_turn('You said "The orchard has twelve pear trees."')
        result = self.evaluate_origins(
            "The orchard has twelve pear trees.", user_contract(), evidence,
            AcceptanceStatus.REJECTED,
        )
        self.assertIn(SOURCE_SCOPE, result.violated_invariants)

    def test_invalid_provenance_correction_cannot_supersede_trusted_live_evidence(self):
        old = normalize_live_conversation([
            {"role": "user", "content": "I like quiet rooms.", "evidence_id": "trusted-preference"},
        ])
        invalid = Evidence(
            claim="I dislike quiet rooms.", provenance="non_user_conversation", confidence="user_authored",
            kind=EvidenceKind.USER_CORRECTION, status=EvidenceStatus.ADMISSIBLE,
            evidence_id="invalid-correction", authority_scope="what_the_user_stated",
            supersedes=("trusted-preference",),
        )
        evidence = combine_evidence(old, canonical_bundle(invalid), authority="user_context")
        self.evaluate_origins(
            "You like quiet rooms.", user_contract(), evidence, AcceptanceStatus.ACCEPTED,
        )
        self.evaluate_origins(
            "You dislike quiet rooms.", user_contract(), evidence, AcceptanceStatus.REJECTED,
        )

    def test_nonboolean_source_verification_flags_fail_closed_when_present(self):
        for kind in (EvidenceKind.PUBLIC_SOURCE, EvidenceKind.MEDIA_SOURCE):
            for field in ("read_success", "accepted_as_evidence", "read_result"):
                for malformed in ("true", "false", 1, None):
                    with self.subTest(kind=kind, field=field, malformed=malformed):
                        source_data = {field: {"success": malformed} if field == "read_result" else malformed}
                        claim = "The orchard has twelve pear trees."
                        evidence = canonical_bundle(source_fact(claim, kind=kind, data=source_data), authority=source_contract(kind).authority)
                        result = self.evaluate_origins(
                            claim, source_contract(kind), evidence, AcceptanceStatus.REJECTED,
                        )
                        self.assertIn(EVIDENCE_AUTHORITY, result.violated_invariants)

    def test_canonical_bundle_freshness_constraint_requires_matching_core_date(self):
        claim = "The orchard has twelve pear trees."
        contract = source_contract(metadata={"runtime_date": "2026-05-02"})
        undated = canonical_bundle(
            source_fact(claim), authority="public_web", freshness_required=True,
        )
        result = self.evaluate_origins(claim, contract, undated, AcceptanceStatus.REJECTED)
        self.assertIn(SOURCE_SCOPE, result.violated_invariants)
        dated = canonical_bundle(
            source_fact(claim, data={"current_as_of": "2026-05-02"}),
            authority="public_web", freshness_required=True,
        )
        self.evaluate_origins(claim, contract, dated, AcceptanceStatus.ACCEPTED)


if __name__ == "__main__":
    unittest.main()
