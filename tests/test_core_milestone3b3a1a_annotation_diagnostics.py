"""Annotation capability gaps cannot claim that trusted verification failed."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_public import (
    OFFICIAL_SOURCE_SUPPORT, PUBLIC_GLOBAL_SUPPORT, PUBLIC_SENTENCE_SUPPORT,
    PUBLIC_VERIFIER_CONSISTENCY, SOURCE_IDENTITY, SOURCE_READ_PROVENANCE,
)
from core.acceptance_shadow import AcceptanceShadowRecord, observe_public_factual_response
from core.answer_candidate import AcceptanceStatus, CandidateOrigin
from core.public_answer_evidence import build_public_answer_candidate, public_packet_digest
from core.public_source_bindings import collect_public_source_bindings
from test_core_milestone3b3a_public_evidence import FACT, URL, contract, inputs, source
from test_core_milestone3b3a1_public_calibration import annotations
from test_core_milestone3b3a1_source_bindings import _Client, entry


QUESTION = "Describe the orchard."


def invalid_annotation(*, failure="literal", text=FACT, data=None, user_input=QUESTION):
    data = data or inputs(text)
    record = entry(witnesses=[{"source_id": "S1", "quote": FACT}])
    if failure == "literal":
        record["witnesses"][0]["quote"] = "The orchard contains forty trees."
    elif failure == "source":
        record["source_ids"] = ["S7"]
        record["witnesses"] = [{"source_id": "S7", "quote": FACT}]
    elif failure == "witness":
        record["witnesses"] = []
    elif failure == "factual_source":
        record["source_ids"] = []
        record["witnesses"] = []
    payload = {"sentences": [record]}
    if failure == "incomplete":
        payload = {"sentences": []}
    elif failure == "json":
        payload = '{"sentences": ['
    elif failure == "model_domain":
        payload["failure_domain"] = "integrity"
    binding = collect_public_source_bindings(
        client=_Client(payload), model="replaceable-local-model", user_input=user_input,
        text=text, evidence_packet=data[1],
    )
    return data, binding


def candidate(*, data=None, binding=None, runtime=None, user_input=QUESTION):
    data = data or inputs()
    return build_public_answer_candidate(
        text=FACT, contract=runtime or contract(), research_result=data[0], evidence_packet=data[1],
        verification_result=data[2], source_bindings=binding, user_input=user_input,
    )


def evaluate(value):
    return CoreAcceptanceEvaluator().evaluate(value)


class AnnotationDomainTests(unittest.TestCase):
    def test_invalid_literal_is_annotation_capability_not_verifier_integrity(self):
        data, binding = invalid_annotation()
        self.assertEqual(binding["status"], "malformed")
        self.assertEqual(binding["failure_domain"], "annotation_capability")
        self.assertEqual(binding["failure_code"], "invalid_literal_witness")
        normalized = candidate(data=data, binding=binding).evidence.metadata["public_source_bindings"]
        self.assertEqual(normalized["status"], "malformed")
        self.assertEqual(normalized["failure"], "invalid_binding")
        self.assertEqual(normalized["failure_domain"], "annotation_capability")
        self.assertEqual(normalized["failure_code"], "invalid_literal_witness")
        self.assertEqual(normalized["sentences"], ())

    def test_annotation_failure_subtypes_are_distinct_and_bounded(self):
        expected = {
            "source": "invalid_source_id", "witness": "factual_witness_missing",
            "factual_source": "factual_source_missing", "incomplete": "incomplete_annotations",
            "json": "invalid_annotation_shape",
        }
        for failure, code in expected.items():
            with self.subTest(failure=failure):
                data, binding = invalid_annotation(failure=failure)
                normalized = candidate(data=data, binding=binding).evidence.metadata["public_source_bindings"]
                self.assertEqual(normalized["failure_domain"], "annotation_capability")
                self.assertEqual(normalized["failure_code"], code)
                self.assertEqual(normalized["sentences"], ())

    def test_model_cannot_choose_core_failure_domain(self):
        data, binding = invalid_annotation(failure="model_domain")
        self.assertEqual(binding["failure_domain"], "annotation_capability")
        self.assertEqual(binding["failure_code"], "invalid_annotation_shape")
        self.assertEqual(binding["status"], "malformed")

    def test_ordinary_supported_answer_survives_unusable_annotation(self):
        for failure in ("literal", "source", "witness", "factual_source", "incomplete", "json"):
            with self.subTest(failure=failure):
                data, binding = invalid_annotation(failure=failure)
                value = candidate(data=data, binding=binding)
                self.assertEqual(value.evidence.metadata["verifier_source_bindings"], "unavailable")
                decision = evaluate(value)
                self.assertIs(decision.status, AcceptanceStatus.ACCEPTED)
                self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, decision.violated_invariants)

    def test_origin_cannot_upgrade_or_downgrade_annotation_capability_gap(self):
        data, binding = invalid_annotation()
        value = candidate(data=data, binding=binding)
        baseline = evaluate(value)
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                outcome = evaluate(replace(value, origin=origin))
                self.assertEqual(outcome.status, baseline.status)
                self.assertEqual(outcome.violated_invariants, baseline.violated_invariants)

    def test_explicit_read_obligation_still_requires_inspectable_binding(self):
        data, binding = invalid_annotation()
        outcome = evaluate(candidate(data=data, binding=binding,
                                     runtime=contract(metadata={"source_read_required": True})))
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(SOURCE_READ_PROVENANCE, outcome.violated_invariants)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, outcome.violated_invariants)

    def test_explicit_official_obligation_keeps_its_own_failure(self):
        data, binding = invalid_annotation(user_input="Please check the official source.")
        outcome = evaluate(candidate(data=data, binding=binding, user_input="Please check the official source."))
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(OFFICIAL_SOURCE_SUPPORT, outcome.violated_invariants)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, outcome.violated_invariants)

    def test_explicit_source_identity_obligation_keeps_its_own_failure(self):
        data, binding = invalid_annotation()
        outcome = evaluate(candidate(data=data, binding=binding,
                                     runtime=contract(metadata={"exact_source_required": True})))
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(SOURCE_IDENTITY, outcome.violated_invariants)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, outcome.violated_invariants)

    def test_actual_global_verifier_failure_is_not_hidden_by_annotation_failure(self):
        data, binding = invalid_annotation()
        data[2].verification_state["global_supported"] = False
        data[2].verification_state["sentence_assessments"][0]["supported"] = False
        data[2].verification_state["effective_sentence_assessments"][0]["supported"] = False
        data[2].verification_state["effective_supported"] = False
        data[2].verification_state["unsupported_claim_count"] = 1
        outcome = evaluate(candidate(data=data, binding=binding))
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(PUBLIC_GLOBAL_SUPPORT, outcome.violated_invariants)

    def test_actual_sentence_failure_is_not_hidden_by_annotation_failure(self):
        data, binding = invalid_annotation()
        data[2].verification_state["sentence_assessments"][0]["supported"] = False
        data[2].verification_state["effective_sentence_assessments"][0]["supported"] = False
        data[2].verification_state["global_supported"] = False
        data[2].verification_state["effective_supported"] = False
        data[2].verification_state["unsupported_claim_count"] = 1
        outcome = evaluate(candidate(data=data, binding=binding))
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, outcome.violated_invariants)

    def test_unusable_annotation_cannot_hide_wrong_legacy_packet_digest(self):
        data, binding = invalid_annotation()
        data[2].verification_state["packet_digest"] = "0" * 64
        outcome = evaluate(candidate(data=data, binding=binding))
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, outcome.violated_invariants)

    def test_envelope_digest_checks_precede_capability_degradation(self):
        for field in ("assessed_draft_digest", "packet_digest", "assessed_question_digest"):
            with self.subTest(field=field):
                data, binding = invalid_annotation()
                altered = dict(binding)
                altered[field] = "0" * 64
                value = candidate(data=data, binding=altered)
                normalized = value.evidence.metadata["public_source_bindings"]
                self.assertEqual(normalized["failure_domain"], "integrity")
                self.assertEqual(normalized["failure_code"], "wrong_inputs")
                self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, evaluate(value).violated_invariants)

    def test_unavailable_status_does_not_bypass_envelope_integrity(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding.update(status="unavailable", sentences=[], issues=("binding_transport",), packet_digest="0" * 64)
        value = candidate(data=data, binding=binding)
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["failure_domain"], "integrity")
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, evaluate(value).violated_invariants)

    def test_collector_envelope_requires_question_digest(self):
        data, binding = invalid_annotation()
        altered = dict(binding)
        altered.pop("assessed_question_digest")
        value = candidate(data=data, binding=altered)
        normalized = value.evidence.metadata["public_source_bindings"]
        self.assertEqual(normalized["failure_domain"], "integrity")
        self.assertEqual(normalized["failure_code"], "wrong_inputs")
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, evaluate(value).violated_invariants)

    def test_legacy_manual_envelope_keeps_optional_question_digest(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        self.assertNotIn("assessed_question_digest", binding)
        self.assertNotIn("validator", binding)
        value = candidate(data=data, binding=binding)
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_unavailable_envelope_cannot_relabel_known_input_integrity_issue(self):
        for issue, code in (("binding_packet_identity", "invalid_packet_identity"),
                            ("binding_packet_sources", "invalid_packet_shape"),
                            ("binding_inputs", "wrong_inputs")):
            with self.subTest(issue=issue):
                data, binding = invalid_annotation()
                altered = dict(binding)
                altered.update(status="unavailable", sentences=(), issues=(issue,),
                               failure_domain="annotation_capability", failure_code="transport_failure")
                value = candidate(data=data, binding=altered)
                normalized = value.evidence.metadata["public_source_bindings"]
                self.assertEqual(normalized["status"], "malformed")
                self.assertEqual(normalized["failure_domain"], "integrity")
                self.assertEqual(normalized["failure_code"], code)
                self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, evaluate(value).violated_invariants)

    def test_one_valid_source_does_not_hide_another_packet_read_mismatch(self):
        data = list(inputs())
        annex_url = "https://support.example/annex"
        data[0]["sources"].append(source(annex_url, read_result={
            "success": True, "url": annex_url, "content": "The annex contains two storage rooms.",
        }))
        packet = json.loads(data[1])
        packet["sources"].append({"source_id": "S2", "title": "Annex field guide", "url": annex_url,
                                  "content_excerpt": "The annex contains eight storage rooms."})
        data[1] = json.dumps(packet)
        data[2].verification_state["packet_digest"] = public_packet_digest(data[1])
        data, binding = invalid_annotation(data=tuple(data))
        value = candidate(data=data, binding=binding)
        by_id = {item.source_id: item for item in value.evidence.evidence}
        self.assertTrue(by_id["S1"].data["excerpt_matches_read"])
        self.assertFalse(by_id["S2"].data["excerpt_matches_read"])
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["failure_domain"], "annotation_capability")
        outcome = evaluate(value)
        self.assertIsNot(outcome.status, AcceptanceStatus.ACCEPTED)
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, outcome.violated_invariants)

    def test_raw_claimed_complete_invalid_graph_remains_integrity_failure(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["source_ids"] = ["S9"]
        value = candidate(data=data, binding=binding)
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["failure_domain"], "integrity")
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, evaluate(value).violated_invariants)

    def test_raw_claimed_complete_invalid_witness_remains_integrity_failure(self):
        data = inputs()
        binding = annotations(FACT, data[1])
        binding["sentences"][0]["witnesses"][0]["quote"] = "An invented statement."
        value = candidate(data=data, binding=binding)
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["failure_domain"], "integrity")
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, evaluate(value).violated_invariants)

    def test_rejected_actual_read_cannot_become_annotation_capability(self):
        data = inputs()
        data[0]["sources"][0]["accepted_as_evidence"] = False
        value = candidate(data=data, binding=annotations(FACT, data[1]))
        normalized = value.evidence.metadata["public_source_bindings"]
        self.assertEqual(normalized["failure_domain"], "integrity")
        self.assertEqual(normalized["failure_code"], "unread_source")
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, evaluate(value).violated_invariants)

    def test_trusted_packet_identity_error_has_integrity_domain(self):
        packet = json.dumps({"sources": [{"source_id": "S1", "content_excerpt": FACT},
                                         {"source_id": "S1", "content_excerpt": FACT}]})
        binding = collect_public_source_bindings(client=_Client(), model="replaceable-local-model",
                                                user_input=QUESTION, text=FACT, evidence_packet=packet)
        self.assertEqual(binding["failure_domain"], "integrity")
        self.assertEqual(binding["failure_code"], "invalid_packet_identity")

    def test_malformed_packet_cannot_be_reported_as_model_annotation_failure(self):
        binding = collect_public_source_bindings(client=_Client(), model="replaceable-local-model",
                                                user_input=QUESTION, text=FACT, evidence_packet="not a packet")
        self.assertEqual(binding["failure_domain"], "integrity")
        self.assertEqual(binding["failure_code"], "invalid_packet_shape")

    def test_complete_binding_has_no_failure_domain_or_code(self):
        data = inputs()
        binding = collect_public_source_bindings(
            client=_Client({"sentences": [entry(witnesses=[{"source_id": "S1", "quote": FACT}])]}),
            model="replaceable-local-model", user_input=QUESTION, text=FACT, evidence_packet=data[1],
        )
        value = candidate(data=data, binding=binding)
        self.assertIsNone(binding["failure_domain"])
        self.assertIsNone(binding["failure_code"])
        self.assertEqual(value.evidence.metadata["verifier_source_bindings"], "available")
        self.assertIs(evaluate(value).status, AcceptanceStatus.ACCEPTED)

    def test_normalized_failure_metadata_is_an_immutable_snapshot(self):
        data, binding = invalid_annotation()
        value = candidate(data=data, binding=binding)
        with self.assertRaises(TypeError):
            value.evidence.metadata["public_source_bindings"]["failure_domain"] = "integrity"
        copied = dict(binding)
        copied["failure_code"] = "private content"
        self.assertEqual(value.evidence.metadata["public_source_bindings"]["failure_code"], "invalid_literal_witness")


class AnnotationDiagnosticTests(unittest.TestCase):
    def observe(self, *, failure="literal", emit=False):
        data, binding = invalid_annotation(failure=failure)
        record = observe_public_factual_response(
            text=FACT, contract=contract(), research_result=data[0], evidence_packet=data[1],
            verification_result=data[2], source_bindings=binding, user_input=QUESTION, emit=emit,
        )
        return record, data

    def test_safe_diagnostics_distinguish_literal_witness_failure(self):
        record, _ = self.observe()
        self.assertEqual(record.metadata["source_binding_status"], "malformed")
        self.assertEqual(record.metadata["source_binding_issue"], "invalid_binding")
        self.assertEqual(record.metadata["source_binding_failure_domain"], "annotation_capability")
        self.assertEqual(record.metadata["source_binding_failure_code"], "invalid_literal_witness")
        self.assertTrue(any("code=invalid_literal_witness" in event for event in record.events))
        self.assertTrue(all(len(event) <= 180 for event in record.events))
        self.assertIn("source_bindings_unavailable", record.metadata["diagnostic_limits"])

    def test_diagnostic_subcodes_differ_between_source_id_and_literal_failure(self):
        literal, _ = self.observe(failure="literal")
        source, _ = self.observe(failure="source")
        self.assertNotEqual(literal.metadata["source_binding_failure_code"],
                            source.metadata["source_binding_failure_code"])
        self.assertEqual(source.metadata["source_binding_failure_code"], "invalid_source_id")

    def test_unknown_or_private_diagnostic_metadata_is_not_emitted(self):
        secret = "private evidence and exception prose"
        record = AcceptanceShadowRecord(
            "public_generated_factual", CandidateOrigin.GENERATED,
            binding_status="malformed", binding_issue=secret,
            binding_failure_domain=secret, binding_failure_code=secret,
        )
        self.assertNotIn("source_binding_issue", record.metadata)
        self.assertNotIn("source_binding_failure_domain", record.metadata)
        self.assertNotIn("source_binding_failure_code", record.metadata)
        self.assertNotIn(secret, str(record.metadata) + str(record.events))

    def test_events_do_not_expose_answer_url_or_literal_evidence(self):
        record, _ = self.observe()
        rendered = str(record.metadata) + "\n".join(record.events)
        self.assertNotIn(FACT, rendered)
        self.assertNotIn(URL, rendered)
        self.assertNotIn("forty trees", rendered)
        self.assertNotIn(QUESTION, rendered)

    def test_diagnostics_failure_does_not_change_shadow_result(self):
        with patch("core.acceptance_shadow.emit_shadow_record", side_effect=RuntimeError("private exception")):
            record, _ = self.observe(emit=True)
        self.assertFalse(record.evaluation_failed)
        self.assertIs(record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertNotIn("private exception", str(record.metadata))


if __name__ == "__main__":
    unittest.main()
