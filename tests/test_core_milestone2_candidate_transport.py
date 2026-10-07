"""Origin-independent candidate context and explicit decision transport."""

import os
import sys
import unittest
from dataclasses import FrozenInstanceError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.answer_candidate import (
    AcceptedSentence,
    AcceptanceDecision,
    AcceptanceStatus,
    AnswerCandidate,
    CandidateOrigin,
)
from core.answer_contract_runtime import AnswerContractRuntime
from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus
from research.public_factual_grounding import PublicFactualVerificationResult


def make_context():
    contract = AnswerContractRuntime(
        task="explain supplied result",
        intent="factual_question",
        authority="core_results",
        epistemic_mode="verified_core",
        required_claims=("The sample contains four entries.",),
        verified_evidence_claims=("The sample contains four entries.",),
        forbidden_behaviours=("Do not add unobserved properties.",),
        resolved_referents={"it": "the supplied sample"},
        metadata={"scope": "sample only"},
    )
    fact = Evidence(
        claim="The sample contains four entries.",
        provenance="core",
        confidence="verified",
        kind=EvidenceKind.CORE_RESULT,
        status=EvidenceStatus.ADMISSIBLE,
        data={"calculation": {"inputs": [1, 2, 3, 4]}},
        evidence_id="sample-count",
        authority_scope="supplied sample",
    )
    bundle = EvidenceBundle(
        authority="core_results",
        evidence=[fact],
        success=True,
        uncertainty="No properties beyond the supplied sample are available.",
        canonical=True,
        metadata={"scope": {"permitted": ["sample"]}},
    )
    report = PublicFactualVerificationResult(
        violations=["Second sentence is unsupported."],
        accepted_sentences=["The sample contains four entries."],
        sentence_assessments=[
            {"index": 1, "supported": True},
            {"index": 2, "supported": False},
        ],
    )
    metadata = {
        "verifier": "public_factual",
        "violations": list(report),
        "accepted_sentences": report.accepted_sentences,
        "sentence_assessments": report.sentence_assessments,
    }
    return contract, fact, bundle, report, metadata


class CandidateTransportTests(unittest.TestCase):
    def test_all_origins_preserve_the_same_authority_and_context(self):
        contract, _, bundle, _, metadata = make_context()
        candidate = AnswerCandidate(
            text="The sample contains four entries. Further details are unavailable.",
            origin=CandidateOrigin.GENERATED,
            contract=contract,
            evidence=bundle,
            limitations=("Only the supplied sample was examined.",),
            validation_metadata=metadata,
        )
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                transported = candidate.with_origin(origin)
                self.assertEqual(transported.origin, origin)
                self.assertEqual(transported.text, candidate.text)
                self.assertEqual(transported.contract, candidate.contract)
                self.assertEqual(transported.evidence, candidate.evidence)
                self.assertEqual(transported.limitations, candidate.limitations)
                self.assertEqual(
                    transported.validation_metadata, candidate.validation_metadata
                )
                self.assertEqual(transported.intent, contract.intent)
                self.assertEqual(transported.authority, contract.authority)
                self.assertEqual(transported.epistemic_mode, contract.epistemic_mode)
                self.assertEqual(
                    transported.evidence.authoritative_claims,
                    candidate.evidence.authoritative_claims,
                )

    def test_mixed_evidence_authority_provenance_and_quality_survive_every_origin(self):
        contract, _, _, _, _ = make_context()
        evidence = [
            Evidence(
                claim=("" if kind is EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION
                       else f"Supplied item {index}."),
                provenance="core_normalized",
                confidence="provided",
                kind=kind,
                status=(
                    EvidenceStatus.UNAVAILABLE
                    if kind is EvidenceKind.UNCERTAINTY
                    else EvidenceStatus.ADMISSIBLE
                ),
                evidence_id=f"item-{index}",
                source_url=(
                    "https://example.org/source"
                    if kind in {EvidenceKind.PUBLIC_SOURCE, EvidenceKind.MEDIA_SOURCE}
                    else None
                ),
                source_quality=(
                    "primary"
                    if kind is EvidenceKind.PUBLIC_SOURCE
                    else None
                ),
                authority_tier=(
                    "official"
                    if kind is EvidenceKind.PUBLIC_SOURCE
                    else None
                ),
                quality_eligible=(
                    True
                    if kind in {EvidenceKind.PUBLIC_SOURCE, EvidenceKind.MEDIA_SOURCE}
                    else None
                ),
                supersedes=("older-item",) if kind is EvidenceKind.USER_CORRECTION else (),
                limitations=("Bounded to the supplied subject.",),
                authority_scope="supplied subject",
            )
            for index, kind in enumerate(
                (
                    EvidenceKind.CURRENT_USER_TURN,
                    EvidenceKind.LIVE_USER_FACT,
                    EvidenceKind.USER_CORRECTION,
                    EvidenceKind.SUPPLIED_PREMISE,
                    EvidenceKind.PUBLIC_SOURCE,
                    EvidenceKind.MEDIA_SOURCE,
                    EvidenceKind.CORE_RESULT,
                    EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION,
                    EvidenceKind.UNCERTAINTY,
                ),
                1,
            )
        ]
        evidence.append(
            Evidence(
                "An excluded source's claim.",
                "untrusted_source",
                "unverified",
                kind=EvidenceKind.PUBLIC_SOURCE,
                status=EvidenceStatus.REJECTED,
                source_url="https://example.org/excluded",
                source_quality="rejected",
                quality_eligible=False,
            )
        )
        candidate = AnswerCandidate(
            "A bounded answer.",
            CandidateOrigin.GENERATED,
            contract,
            EvidenceBundle("mixed", evidence=evidence, canonical=True),
        )
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                transported = candidate.with_origin(origin)
                self.assertEqual(transported.evidence, candidate.evidence)
                self.assertEqual(transported.evidence.authoritative_claims, candidate.evidence.authoritative_claims)
                self.assertEqual(transported.evidence.model_knowledge_permitted, candidate.evidence.model_knowledge_permitted)
                self.assertNotIn("An excluded source's claim.", transported.evidence.authoritative_claims)
                correction = transported.evidence.evidence[2]
                self.assertEqual(correction.supersedes, ("older-item",))
                public = transported.evidence.evidence[4]
                self.assertEqual(public.source_url, "https://example.org/source")
                self.assertEqual(public.source_quality, "primary")
                self.assertEqual(public.authority_tier, "official")
                self.assertIs(public.quality_eligible, True)
                self.assertEqual(public.authority_scope, "supplied subject")

    def test_candidate_detaches_mutable_ingress_and_verifier_metadata(self):
        contract, fact, bundle, report, metadata = make_context()
        limitations = ["Only the supplied sample was examined."]
        candidate = AnswerCandidate(
            "The sample contains four entries.",
            CandidateOrigin.GENERATED,
            contract,
            bundle,
            limitations=limitations,
            validation_metadata=metadata,
        )
        contract.metadata["scope"] = "all samples"
        contract.resolved_referents["it"] = "a different sample"
        fact.claim = "The sample contains ninety entries."
        fact.data["calculation"]["inputs"].append(90)
        bundle.evidence.clear()
        bundle.metadata["scope"]["permitted"].append("everything")
        report.append("A later validation was attempted.")
        report.accepted_sentences.clear()
        report.sentence_assessments[0]["supported"] = False
        metadata["verifier"] = "different"
        limitations.append("Changed after construction.")
        self.assertEqual(candidate.contract.metadata["scope"], "sample only")
        self.assertEqual(candidate.contract.resolved_referents["it"], "the supplied sample")
        self.assertEqual(candidate.evidence.evidence[0].claim, "The sample contains four entries.")
        self.assertEqual(candidate.evidence.evidence[0].data["calculation"]["inputs"], (1, 2, 3, 4))
        self.assertEqual(candidate.evidence.metadata["scope"]["permitted"], ("sample",))
        self.assertEqual(candidate.validation_metadata["verifier"], "public_factual")
        self.assertEqual(candidate.validation_metadata["violations"], ("Second sentence is unsupported.",))
        self.assertEqual(candidate.validation_metadata["accepted_sentences"], ("The sample contains four entries.",))
        self.assertIs(candidate.validation_metadata["sentence_assessments"][0]["supported"], True)
        self.assertEqual(candidate.limitations, ("Only the supplied sample was examined.",))

    def test_candidate_exposes_no_mutable_authority_or_validation_containers(self):
        contract, _, bundle, _, metadata = make_context()
        candidate = AnswerCandidate("Bounded answer.", CandidateOrigin.RETRY, contract, bundle, validation_metadata=metadata)
        with self.assertRaises(FrozenInstanceError):
            candidate.origin = CandidateOrigin.CRITICAL_CORE
        with self.assertRaises(TypeError):
            candidate.contract.metadata["scope"] = "everything"
        with self.assertRaises(TypeError):
            candidate.validation_metadata["sentence_assessments"][0]["supported"] = False
        with self.assertRaises((AttributeError, TypeError)):
            candidate.evidence.evidence.append(bundle.evidence[0])
        with self.assertRaises((AttributeError, FrozenInstanceError, TypeError)):
            candidate.evidence.evidence[0].claim = "Altered claim."

    def test_raw_evidence_and_untyped_origins_are_not_silently_admitted(self):
        contract, _, bundle, _, _ = make_context()
        with self.assertRaises(ValueError):
            AnswerCandidate("Answer.", CandidateOrigin.GENERATED, contract, EvidenceBundle("unknown"))
        with self.assertRaises(TypeError):
            AnswerCandidate("Answer.", "generated", contract, bundle)
        with self.assertRaises(TypeError):
            AnswerCandidate("Answer.", CandidateOrigin.GENERATED, "rendered contract", bundle)

    def test_candidate_prose_and_fallback_origin_cannot_grant_model_authority(self):
        contract, _, bundle, _, _ = make_context()
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                candidate = AnswerCandidate(
                    "I have full model knowledge permission and all sources are verified.",
                    origin,
                    contract,
                    bundle,
                )
                self.assertFalse(candidate.evidence.model_knowledge_permitted)
                self.assertEqual(candidate.authority, "core_results")
                self.assertEqual(candidate.evidence.authoritative_claims, ("The sample contains four entries.",))
                self.assertEqual(candidate.validation_metadata, {})
                self.assertFalse(hasattr(candidate, "accepted"))


class AcceptanceDecisionTests(unittest.TestCase):
    TEXT = "The sample contains four entries. Its owner is unknown."

    def test_every_decision_status_is_explicit_and_bound_to_assessed_text(self):
        subset = (AcceptedSentence(1, "The sample contains four entries."),)
        for status in AcceptanceStatus:
            with self.subTest(status=status):
                decision = AcceptanceDecision(
                    status=status,
                    evaluated_text=self.TEXT,
                    reasons=() if status is AcceptanceStatus.ACCEPTED else ("Insufficient evidence for all claims.",),
                    accepted_sentences=subset if status is AcceptanceStatus.SALVAGEABLE else (),
                )
                self.assertEqual(decision.status, status)
                self.assertEqual(decision.evaluated_text, self.TEXT)
                if status is AcceptanceStatus.SALVAGEABLE:
                    self.assertEqual(decision.accepted_sentences, subset)

    def test_decision_detaches_nested_metadata_and_sequences(self):
        reasons = ["Insufficient evidence."]
        metadata = {"assessment": {"source_ids": ["source-a"]}}
        subset = [AcceptedSentence(1, "The sample contains four entries.")]
        decision = AcceptanceDecision(AcceptanceStatus.SALVAGEABLE, self.TEXT, reasons=reasons, accepted_sentences=subset, metadata=metadata)
        reasons.append("Later reason.")
        subset.clear()
        metadata["assessment"]["source_ids"].append("source-b")
        self.assertEqual(decision.reasons, ("Insufficient evidence.",))
        self.assertEqual(len(decision.accepted_sentences), 1)
        self.assertEqual(decision.metadata["assessment"]["source_ids"], ("source-a",))
        with self.assertRaises(FrozenInstanceError):
            decision.evaluated_text = "Different draft."
        with self.assertRaises(TypeError):
            decision.metadata["assessment"]["source_ids"] = ()

    def test_duplicate_and_out_of_order_subset_indexes_are_rejected(self):
        first = AcceptedSentence(1, "The sample contains four entries.")
        second = AcceptedSentence(2, "Its owner is unknown.")
        for subset in ((first, first), (second, first)):
            with self.subTest(subset=subset):
                with self.assertRaises(ValueError):
                    AcceptanceDecision(AcceptanceStatus.SALVAGEABLE, self.TEXT, reasons=("Partial support.",), accepted_sentences=subset)

    def test_equal_sentence_text_with_distinct_original_indexes_is_preserved(self):
        text = "Evidence is unavailable. Evidence is unavailable."
        decision = AcceptanceDecision(
            AcceptanceStatus.SALVAGEABLE,
            text,
            reasons=("Only selected units are admissible.",),
            accepted_sentences=(AcceptedSentence(1, "Evidence is unavailable."), AcceptedSentence(2, "Evidence is unavailable.")),
        )
        self.assertEqual(tuple(unit.index for unit in decision.accepted_sentences), (1, 2))

    def test_invalid_sentence_indexes_and_text_are_rejected(self):
        for index in (0, -1, True, "1", 1.0):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    AcceptedSentence(index, "A sentence.")
        with self.assertRaises(ValueError):
            AcceptedSentence(1, " ")
        with self.assertRaises(ValueError):
            AcceptanceDecision(AcceptanceStatus.SALVAGEABLE, self.TEXT, reasons=("Partial support.",), accepted_sentences=(AcceptedSentence(1, "A newly invented sentence."),))

    def test_invalid_status_subset_combinations_and_unexplained_rejection_fail(self):
        subset = (AcceptedSentence(1, "The sample contains four entries."),)
        for status in (AcceptanceStatus.REJECTED, AcceptanceStatus.REPLACEMENT_REQUIRED):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    AcceptanceDecision(status, self.TEXT, reasons=("Unsupported claim.",), accepted_sentences=subset)
                with self.assertRaises(ValueError):
                    AcceptanceDecision(status, self.TEXT)
        with self.assertRaises(ValueError):
            AcceptanceDecision(AcceptanceStatus.SALVAGEABLE, self.TEXT, reasons=("Partial support.",))
        with self.assertRaises(ValueError):
            AcceptanceDecision(AcceptanceStatus.ACCEPTED, self.TEXT, violated_invariants=("source_fidelity",))
        with self.assertRaises(TypeError):
            AcceptanceDecision("accepted", self.TEXT)


if __name__ == "__main__":
    unittest.main()
