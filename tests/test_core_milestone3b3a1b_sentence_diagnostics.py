"""Indexed public sentence calibration never changes authority or publication.

Neutral terse answers remain factual: a positive legacy verdict and real source
witness support them, whereas an annotation label cannot exempt their content.
Safe diagnostics identify actual failing units without echoing source prose.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sys
from threading import Barrier
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_public import PUBLIC_SENTENCE_SUPPORT, SOURCE_IDENTITY
from core.acceptance_semantics import interpret_text
from core.acceptance_shadow import (
    AcceptanceShadowRecord, acceptance_shadow_events, emit_shadow_record,
    observe_public_factual_response,
)
from core.acceptance_typed import TypedEvaluation, validate_typed_evidence
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus, CandidateOrigin
from test_core_milestone3b3a_public_evidence import FACT, URL, contract, inputs
from test_core_milestone3b3a1_public_calibration import annotations, evaluate, make
from test_core_milestone3b3a1a_annotation_diagnostics import invalid_annotation
from test_core_milestone3b3a1a_semantic_calibration import identity_candidate


VALIDATOR = "public_factual_verifier_provenance"


def diagnostics(decision):
    return decision.metadata.get("typed_diagnostics", {}).get(VALIDATOR, {}).get("public_sentence_failures", ())


def label_candidate(text, kind, *, index=1):
    data = inputs(text)
    binding = annotations(text, data[1])
    binding["sentences"][index - 1].update(
        claim_kind=kind, source_ids=[], witnesses=[],
        provenance_claim="none", scope_status="not_applicable",
    )
    return make(text, data=data, binding=binding)


def safe_decision(records, *, text="Sensitive candidate wording.", more=None):
    metadata = {"typed_diagnostics": {VALIDATOR: {"public_sentence_failures": records}}}
    if more:
        metadata.update(more)
    return AcceptanceDecision(
        AcceptanceStatus.REJECTED, text,
        reasons=("Private source reasoning must not be emitted.",),
        violated_invariants=(PUBLIC_SENTENCE_SUPPORT,), metadata=metadata,
    )


def shadow_record(records, **kwargs):
    return AcceptanceShadowRecord("public_generated_factual", CandidateOrigin.GENERATED,
                                  safe_decision(records, **kwargs))


def failure(index=1, kind="non_factual", code="annotation_non_factual_mismatch", **extra):
    return dict(sentence_index=index, annotation_kind=kind, code=code, **extra)


class PublicSentenceDiagnosticsTests(unittest.TestCase):
    def test_terse_negative_answer_with_actual_support_remains_factual_and_accepted(self):
        for text in ("No, they do not.", "No, it does not.", "They do not."):
            with self.subTest(text=text):
                outcome = evaluate(make(text))
                self.assertIs(outcome.status, AcceptanceStatus.ACCEPTED)
                self.assertEqual(diagnostics(outcome), ())

    def test_terse_affirmative_answer_still_requires_real_factual_support(self):
        text = "Yes, they do."
        supported = evaluate(make(text))
        self.assertIs(supported.status, AcceptanceStatus.ACCEPTED)
        outcome = evaluate(label_candidate(text, "non_factual"))
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)

    def test_non_factual_mislabel_identifies_original_verifier_sentence(self):
        outcome = evaluate(label_candidate("No, they do not.", "non_factual"))
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)
        self.assertEqual(diagnostics(outcome), (failure(),))

    def test_limitation_mislabel_identifies_original_verifier_sentence(self):
        outcome = evaluate(label_candidate("No, they do not.", "limitation"))
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)
        self.assertEqual(diagnostics(outcome), (failure(kind="limitation", code="annotation_limitation_mismatch"),))

    def test_citation_only_sentence_has_no_false_content_failure(self):
        text = "Here is the official source: " + URL + "."
        outcome = evaluate(identity_candidate(text))
        self.assertIs(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(diagnostics(outcome), ())

    def test_wrong_citation_identity_is_not_reported_as_content_failure(self):
        text = "The official source is https://support.example/unread-page."
        outcome = evaluate(identity_candidate(text))
        self.assertIn(SOURCE_IDENTITY, outcome.violated_invariants)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)
        self.assertEqual(diagnostics(outcome), ())

    def test_diagnostic_index_comes_from_original_verifier_not_generic_url_units(self):
        text = "Here is the source: " + URL + ". No, they do not."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0].update(witnesses=[], provenance_claim="citation", scope_status="not_applicable")
        binding["sentences"][1].update(claim_kind="non_factual", source_ids=[], witnesses=[],
                                         provenance_claim="none", scope_status="not_applicable")
        outcome = evaluate(make(text, data=data, binding=binding))
        self.assertEqual(diagnostics(outcome), (failure(index=2),))

    def test_missing_factual_witness_has_distinct_failure_code(self):
        data = inputs(FACT)
        binding = annotations(FACT, data[1])
        # The annotation's citation label cannot hide a substantive assertion.
        binding["sentences"][0].update(witnesses=[], provenance_claim="citation")
        outcome = evaluate(make(FACT, data=data, binding=binding))
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)
        self.assertEqual(diagnostics(outcome), (failure(kind="factual", code="factual_witness_missing"),))

    def test_legacy_negative_sentence_has_distinct_failure_code(self):
        text = FACT + " The orchard has a greenhouse."
        data = inputs(text)
        state = data[2].verification_state
        state.update(global_supported=False, effective_supported=False, unsupported_claim_count=1)
        state["sentence_assessments"][1]["supported"] = False
        state["effective_sentence_assessments"][1]["supported"] = False
        outcome = evaluate(make(text, data=data))
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)
        self.assertEqual(diagnostics(outcome), (failure(index=2, kind="factual", code="legacy_sentence_unsupported"),))

    def test_annotation_capability_failure_alone_does_not_add_sentence_failure(self):
        data, binding = invalid_annotation()
        outcome = evaluate(make(data=data, binding=binding, user_input="Describe the orchard."))
        self.assertIs(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(diagnostics(outcome), ())

    def test_multiple_real_failure_causes_on_one_sentence_remain_distinguishable(self):
        text = "No, they do not."
        data = inputs(text)
        state = data[2].verification_state
        state.update(global_supported=False, effective_supported=False, unsupported_claim_count=1)
        state["sentence_assessments"][0]["supported"] = False
        state["effective_sentence_assessments"][0]["supported"] = False
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="non_factual", source_ids=[], witnesses=[],
                                         provenance_claim="none", scope_status="not_applicable")
        outcome = evaluate(make(text, data=data, binding=binding))
        self.assertEqual({value["code"] for value in diagnostics(outcome)},
                         {"legacy_sentence_unsupported", "annotation_non_factual_mismatch"})
        self.assertTrue(all(value["sentence_index"] == 1 for value in diagnostics(outcome)))

    def test_origin_never_changes_sentence_diagnostics_or_acceptance(self):
        candidate = label_candidate("No, they do not.", "non_factual")
        baseline = evaluate(candidate)
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                changed = evaluate(candidate.with_origin(origin))
                self.assertEqual(changed, baseline)

    def test_typed_diagnostic_snapshot_is_deeply_immutable(self):
        raw = {"public_sentence_failures": [failure()]}
        profile = TypedEvaluation("neutral", {}, diagnostic_metadata=raw)
        raw["public_sentence_failures"][0]["code"] = "Changed private prose."
        self.assertEqual(profile.diagnostic_metadata["public_sentence_failures"][0]["code"], "annotation_non_factual_mismatch")
        with self.assertRaises(TypeError):
            profile.diagnostic_metadata["public_sentence_failures"][0]["code"] = "changed"

    def test_typed_diagnostics_must_be_a_mapping(self):
        with self.assertRaises(TypeError):
            TypedEvaluation("neutral", {}, diagnostic_metadata="Private error text.")

    def test_diagnostic_metadata_is_not_an_acceptance_input(self):
        candidate = make()
        profiles = validate_typed_evidence(candidate, interpret_text(candidate.text))
        changed = tuple(replace(profile, diagnostic_metadata={"public_sentence_failures": [failure()]})
                        for profile in profiles)
        baseline = evaluate(candidate)
        with patch("core.acceptance_evaluator.validate_typed_evidence", return_value=changed):
            outcome = evaluate(candidate)
        self.assertEqual(outcome.status, baseline.status)
        self.assertEqual(outcome.violated_invariants, baseline.violated_invariants)
        self.assertEqual(outcome.accepted_sentences, baseline.accepted_sentences)

    def test_unknown_failure_code_never_leaks_into_events(self):
        secret = "Private candidate excerpt https://private.example/secret"
        record = shadow_record([failure(code=secret)])
        self.assertNotIn("public_sentence_failures", record.metadata)
        self.assertNotIn(secret, " ".join(record.events))

    def test_invalid_indexes_including_boolean_are_filtered(self):
        for index in (True, False, 0, -1, 17, "1", 1.0, None):
            with self.subTest(index=index):
                record = shadow_record([failure(index=index)])
                self.assertNotIn("public_sentence_failures", record.metadata)
        self.assertEqual(shadow_record([failure(index=16)]).metadata["public_sentence_failures"], (failure(index=16),))

    def test_unknown_or_non_scalar_annotation_kinds_are_filtered(self):
        for kind in ("Private classification prose.", {}, [], None):
            with self.subTest(kind=kind):
                record = shadow_record([failure(kind=kind)])
                self.assertNotIn("public_sentence_failures", record.metadata)

    def test_extra_raw_text_fields_are_never_emitted(self):
        secret = "Private evidence contents."
        record = shadow_record([failure(text=secret, witness=secret, source=secret, reason=secret)])
        self.assertEqual(record.metadata["public_sentence_failures"], (failure(),))
        self.assertNotIn(secret, str(record.metadata) + " ".join(record.events))

    def test_wrong_validator_namespace_cannot_enter_public_events(self):
        outcome = AcceptanceDecision(
            AcceptanceStatus.REJECTED, "Sensitive response.", reasons=("Sensitive reason.",),
            violated_invariants=(PUBLIC_SENTENCE_SUPPORT,),
            metadata={"typed_diagnostics": {"other_validator": {"public_sentence_failures": [failure()]}}},
        )
        record = AcceptanceShadowRecord("public_generated_factual", CandidateOrigin.GENERATED, outcome)
        self.assertNotIn("public_sentence_failures", record.metadata)

    def test_malformed_diagnostic_container_is_nonfatal_and_never_emitted(self):
        for records in ("Private diagnostic prose.", {"secret": "Private diagnostic prose."}, None):
            with self.subTest(records=records):
                record = shadow_record(records)
                self.assertNotIn("public_sentence_failures", record.metadata)
                self.assertNotIn("Private diagnostic prose", " ".join(record.events))

    def test_duplicate_diagnostics_are_deduplicated_and_capped(self):
        codes = ("legacy_sentence_unsupported", "annotation_limitation_mismatch",
                 "annotation_non_factual_mismatch", "factual_witness_missing")
        raw = [failure(index=index, code=code) for index in range(1, 17) for code in codes]
        record = shadow_record([raw[0], raw[0]] + raw)
        self.assertEqual(len(record.metadata["public_sentence_failures"]), 16)
        self.assertEqual(len({tuple(value.items()) for value in record.metadata["public_sentence_failures"]}), 16)
        self.assertTrue(all(len(value) <= 180 for value in record.events))

    def test_event_contains_only_index_kind_and_allowlisted_code(self):
        record = shadow_record([failure(index=4)])
        emitted = [value for value in record.events if "shadow sentence:" in value]
        self.assertEqual(emitted, ["[Core] Acceptance shadow sentence: public_generated_factual; index=4; kind=non_factual; code=annotation_non_factual_mismatch"])
        self.assertNotIn(record.decision.evaluated_text, " ".join(record.events))
        self.assertNotIn(record.decision.reasons[0], " ".join(record.events))

    def test_observer_exposes_specific_failure_without_candidate_or_source_prose(self):
        text = "No, they do not."
        data = inputs(text)
        candidate = label_candidate(text, "non_factual")
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="non_factual", source_ids=[], witnesses=[], provenance_claim="none", scope_status="not_applicable")
        events = []
        with acceptance_shadow_events(events.append):
            record = observe_public_factual_response(
                text=text, contract=contract(), research_result=data[0], evidence_packet=data[1],
                verification_result=data[2], source_bindings=binding,
            )
        self.assertEqual(record.decision, evaluate(candidate))
        self.assertTrue(any("index=1; kind=non_factual; code=annotation_non_factual_mismatch" in value for value in events))
        for private in (text, FACT, URL):
            self.assertNotIn(private, " ".join(events))

    def test_diagnostic_sink_failure_does_not_change_decision(self):
        text = "No, they do not."
        data = inputs(text)
        binding = annotations(text, data[1])
        binding["sentences"][0].update(claim_kind="non_factual", source_ids=[], witnesses=[], provenance_claim="none", scope_status="not_applicable")

        def broken(_):
            raise RuntimeError("Private sink error.")

        with acceptance_shadow_events(broken):
            record = observe_public_factual_response(
                text=text, contract=contract(), research_result=data[0], evidence_packet=data[1],
                verification_result=data[2], source_bindings=binding,
            )
        self.assertFalse(record.evaluation_failed)
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, record.decision.violated_invariants)
        self.assertEqual(record.metadata["public_sentence_failures"], (failure(),))

    def test_concurrent_request_sentence_diagnostics_remain_isolated(self):
        barrier = Barrier(2)

        def run(index):
            events = []
            with acceptance_shadow_events(events.append):
                barrier.wait()
                emit_shadow_record(shadow_record([failure(index=index)]))
            return events

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run, 3)
            second = pool.submit(run, 7)
            events_a, events_b = first.result(), second.result()
        self.assertTrue(any("index=3;" in value for value in events_a))
        self.assertTrue(any("index=7;" in value for value in events_b))
        self.assertFalse(any("index=7;" in value for value in events_a))
        self.assertFalse(any("index=3;" in value for value in events_b))

    def test_decision_diagnostic_metadata_is_immutable(self):
        outcome = evaluate(label_candidate("No, they do not.", "non_factual"))
        with self.assertRaises(TypeError):
            outcome.metadata["typed_diagnostics"][VALIDATOR]["public_sentence_failures"][0]["code"] = "changed"


if __name__ == "__main__":
    unittest.main()
