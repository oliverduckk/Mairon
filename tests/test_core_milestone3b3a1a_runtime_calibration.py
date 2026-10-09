"""Calibrated annotation failures remain observational in the real public lane.

The complete current production direct-conversation function is executed with
scripted model/network dependencies. Legacy verification, source annotation,
canonical evidence, common evaluation, final selection and history are real.
No live repository, model, account, source or benchmark fixture is accessed.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_milestone3b3a_public_shadow_integration import TEXT, URL, contract, provider
from test_core_milestone3b3a1_runtime_calibration import CalibratedClient, entry
from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_public import (
    OFFICIAL_SOURCE_SUPPORT, PUBLIC_SENTENCE_SUPPORT, PUBLIC_VERIFIER_CONSISTENCY,
    SOURCE_IDENTITY, SOURCE_READ_PROVENANCE,
)
from core.acceptance_shadow import acceptance_shadow_events, observe_public_factual_response
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus, CandidateOrigin
from core.evidence import EvidenceKind


class SalvageClient(CalibratedClient):
    """A coherent legacy verifier approves only the first original sentence."""

    def __init__(self):
        super().__init__(TEXT + " The service predicts the weather.")

    def chat(self, **kwargs):
        if "sentence_assessments" in kwargs.get("format", {}).get("properties", {}):
            self.calls.append(kwargs)
            content = json.dumps({
                "supported": False,
                "unsupported_claims": ["The second sentence is unsupported."],
                "sentence_assessments": [
                    {"index": 1, "supported": True},
                    {"index": 2, "supported": False},
                ],
            })
            return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")
        return super().chat(**kwargs)


class RuntimeCalibrationTests(unittest.TestCase):
    def run_path(self, *, client=None, current="What capability does the service document?",
                 retained=None, observer=None, decision=None, evaluation_error=None,
                 sink=None, runtime=None, overrides=None):
        client = client or CalibratedClient()
        kwargs = {"retained": retained} if retained is not None else {}
        if observer is not None:
            kwargs["observer"] = observer
        run, namespace = provider(**kwargs)
        if overrides:
            namespace.update(overrides)
        candidates, decisions, events = [], [], []
        evaluate = CoreAcceptanceEvaluator.evaluate

        def capture(evaluator, candidate):
            candidates.append(candidate)
            if evaluation_error is not None:
                raise evaluation_error
            if decision is not None:
                if isinstance(decision, AcceptanceStatus):
                    result = AcceptanceDecision(
                        decision, candidate.text,
                        reasons=() if decision == AcceptanceStatus.ACCEPTED else ("A bounded test rejection.",),
                        violated_invariants=() if decision == AcceptanceStatus.ACCEPTED else (SOURCE_IDENTITY,),
                    )
                else:
                    result = decision
            else:
                result = evaluate(evaluator, candidate)
            decisions.append(result)
            return result

        prior = [{"role": "assistant", "content": "Unverified previous dialogue with a substituted source."}]
        with redirect_stdout(io.StringIO()), acceptance_shadow_events(sink or events.append), \
                patch.object(CoreAcceptanceEvaluator, "evaluate", capture):
            result = run(client, current, prior, core_answer_contract=runtime or contract())
        return result, client, candidates, decisions, events

    def assert_published_unchanged(self, result, text=TEXT):
        self.assertEqual(result[0], text)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": text})
        self.assertEqual(result[2:], (None, None))

    def assert_capability_gap(self, candidate, events, code):
        bindings = candidate.evidence.metadata["public_source_bindings"]
        self.assertEqual(bindings["failure_domain"], "annotation_capability")
        self.assertEqual(bindings["failure_code"], code)
        self.assertEqual(candidate.evidence.metadata["verifier_source_bindings"], "unavailable")
        self.assertTrue(any("source_bindings_unavailable" in value for value in events))
        self.assertTrue(any("domain=annotation_capability" in value and "code=" + code in value for value in events))
        for event in events:
            self.assertLessEqual(len(event), 180)
            self.assertNotIn(TEXT, event)
            self.assertNotIn(URL, event)

    def test_actual_invalid_literal_annotation_is_a_capability_gap_not_a_verifier_failure(self):
        baseline, _, _, _, _ = self.run_path(observer=lambda **kwargs: None)
        annotations = [entry(witnesses=[{"source_id": "S1", "quote": "A private invented literal."}])]
        result, client, candidates, decisions, events = self.run_path(client=CalibratedClient(annotations=annotations))
        self.assertEqual(result, baseline)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, decisions[0].violated_invariants)
        self.assert_capability_gap(candidates[0], events, "invalid_literal_witness")
        self.assertNotIn("private invented literal", " ".join(events))
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(len(client.bounded_options), 1)
        self.assertEqual(client.closed, 1)

    def test_actual_invalid_source_id_is_observational_and_cannot_add_source_authority(self):
        annotations = [entry(source_ids=("S9",), witnesses=[{"source_id": "S9", "quote": TEXT}])]
        result, _, candidates, decisions, events = self.run_path(client=CalibratedClient(annotations=annotations))
        self.assert_published_unchanged(result)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assert_capability_gap(candidates[0], events, "invalid_source_id")
        self.assertEqual(len(candidates[0].evidence.authoritative_evidence), 1)
        self.assertTrue(all(item.kind == EvidenceKind.PUBLIC_SOURCE for item in candidates[0].evidence.evidence))
        self.assertFalse(any("S9" in str(item.data) for item in candidates[0].evidence.evidence))

    def test_incomplete_runtime_annotations_do_not_accuse_a_complete_legacy_verifier(self):
        result, _, candidates, decisions, events = self.run_path(client=CalibratedClient(annotations=[]))
        self.assert_published_unchanged(result)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertTrue(candidates[0].evidence.metadata["public_verification"]["assessment_complete"])
        self.assert_capability_gap(candidates[0], events, "incomplete_annotations")

    def test_missing_bindings_preserve_explicit_source_read_obligation_and_specific_failure(self):
        annotations = [entry(witnesses=[{"source_id": "S1", "quote": "An invented quotation."}])]
        result, _, candidates, decisions, events = self.run_path(
            client=CalibratedClient(annotations=annotations), current="Please read the source page before answering.")
        self.assert_published_unchanged(result)
        self.assertTrue(candidates[0].contract.metadata["source_read_required"])
        self.assertNotEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertIn(SOURCE_READ_PROVENANCE, decisions[0].violated_invariants)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, decisions[0].violated_invariants)
        self.assert_capability_gap(candidates[0], events, "invalid_literal_witness")

    def test_missing_bindings_do_not_satisfy_combined_official_and_exact_source_obligations(self):
        annotations = [entry(source_ids=("S9",), witnesses=[{"source_id": "S9", "quote": TEXT}])]
        result, _, candidates, decisions, events = self.run_path(
            client=CalibratedClient(annotations=annotations), current="Use an official source and give the actual source URL.")
        self.assert_published_unchanged(result)
        self.assertTrue(candidates[0].contract.metadata["official_source_required"])
        self.assertTrue(candidates[0].contract.metadata["exact_source_required"])
        self.assertIn(OFFICIAL_SOURCE_SUPPORT, decisions[0].violated_invariants)
        self.assertIn(SOURCE_IDENTITY, decisions[0].violated_invariants)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, decisions[0].violated_invariants)
        self.assert_capability_gap(candidates[0], events, "invalid_source_id")

    def test_real_selected_citation_caption_needs_identity_but_not_a_content_witness(self):
        text = TEXT + " Here is the official source: " + URL + "."
        annotations = [entry(), entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, candidates, decisions, events = self.run_path(
            client=CalibratedClient(text, annotations), current="Use the official source and give the actual source URL.")
        self.assert_published_unchanged(result, text)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(candidates[0].evidence.metadata["verifier_source_bindings"], "available")
        self.assertTrue(any("status=COMPLETE" in event for event in events))

    def test_real_selected_citation_with_unloaded_url_keeps_identity_rejection_without_content_false_positive(self):
        text = TEXT + " The source is https://docs.vendor.example/service/other."
        annotations = [entry(), entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, candidates, decisions, _ = self.run_path(client=CalibratedClient(text, annotations))
        self.assert_published_unchanged(result, text)
        self.assertEqual(candidates[0].evidence.metadata["verifier_source_bindings"], "available")
        self.assertNotEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertIn(SOURCE_IDENTITY, decisions[0].violated_invariants)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, decisions[0].violated_invariants)

    def test_real_selected_caption_cannot_promote_third_party_authority_by_saying_official(self):
        from test_core_milestone3b3a_public_shadow_integration import research
        retained = research()
        retained["sources"][0]["authority_tier"] = "independent_editorial"
        text = TEXT + " Here is the official source: " + URL + "."
        annotations = [entry(), entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, annotations), retained=retained)
        self.assert_published_unchanged(result, text)
        self.assertIn(OFFICIAL_SOURCE_SUPPORT, decisions[0].violated_invariants)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, decisions[0].violated_invariants)

    def test_real_selected_bounded_epistemic_sentence_is_accepted_without_factual_witness(self):
        text = "I don't know what a 'lattice cadence' is."
        annotations = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable")]
        with patch("research.research_jobs.create_research_job") as create:
            result, _, candidates, decisions, _ = self.run_path(client=CalibratedClient(text, annotations))
        self.assert_published_unchanged(result, text)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(candidates[0].evidence.metadata["verifier_source_bindings"], "available")
        create.assert_not_called()

    def test_shadow_statuses_cannot_change_current_publication_or_history(self):
        baseline, _, _, _, _ = self.run_path(observer=lambda **kwargs: None)
        for status in (AcceptanceStatus.ACCEPTED, AcceptanceStatus.REJECTED, AcceptanceStatus.REPLACEMENT_REQUIRED):
            with self.subTest(status=status):
                result, _, candidates, decisions, events = self.run_path(decision=status)
                self.assertEqual(result, baseline)
                self.assertEqual(len(candidates), 1)
                self.assertEqual(decisions[0].status, status)
                self.assertTrue(any("Acceptance shadow: " + status.value.upper() in value for value in events))

    def test_evaluator_exception_leaves_publication_and_history_unchanged(self):
        result, _, candidates, _, events = self.run_path(evaluation_error=RuntimeError("Private evaluator content"))
        self.assert_published_unchanged(result)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(any("EVALUATION_ERROR" in value for value in events))
        self.assertNotIn("Private evaluator content", " ".join(events))

    def test_malformed_evaluator_return_leaves_publication_and_history_unchanged(self):
        result, _, candidates, _, events = self.run_path(decision=object())
        self.assert_published_unchanged(result)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(any("EVALUATION_ERROR" in value for value in events))

    def test_adapter_exception_leaves_publication_and_history_unchanged(self):
        with patch("core.public_answer_evidence.build_public_answer_candidate", side_effect=ValueError("Private adapter content")):
            result, _, candidates, _, events = self.run_path()
        self.assert_published_unchanged(result)
        self.assertFalse(candidates)
        self.assertTrue(any("EVALUATION_ERROR" in value for value in events))
        self.assertNotIn("Private adapter content", " ".join(events))

    def test_diagnostic_sink_exception_cannot_own_publication(self):
        def fail(event):
            raise RuntimeError("Private sink content")
        result, _, candidates, decisions, events = self.run_path(sink=fail)
        self.assert_published_unchanged(result)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertFalse(events)

    def test_trusted_draft_digest_mismatch_still_rejects_substantively(self):
        def corrupt(**kwargs):
            state = dict(kwargs["verification_result"].verification_state)
            state["assessed_draft_digest"] = "0" * 64
            kwargs["verification_result"] = SimpleNamespace(verification_state=state)
            return observe_public_factual_response(**kwargs)
        result, _, _, decisions, events = self.run_path(observer=corrupt)
        self.assert_published_unchanged(result)
        self.assertNotEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertIn(PUBLIC_VERIFIER_CONSISTENCY, decisions[0].violated_invariants)
        self.assertTrue(any("domain=integrity" in event and "code=wrong_inputs" in event for event in events))

    def test_actual_annotation_failure_decision_is_origin_invariant(self):
        annotations = [entry(witnesses=[{"source_id": "S1", "quote": "Absent literal."}])]
        _, _, candidates, decisions, _ = self.run_path(client=CalibratedClient(annotations=annotations))
        initial = decisions[0]
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                changed = CoreAcceptanceEvaluator().evaluate(candidates[0].with_origin(origin))
                self.assertEqual(changed.status, initial.status)
                self.assertEqual(changed.violated_invariants, initial.violated_invariants)
                self.assertEqual(changed.reasons, initial.reasons)
                self.assertEqual(changed.metadata, initial.metadata)

    def test_assistant_history_is_not_source_evidence_during_annotation_failure(self):
        _, _, candidates, _, _ = self.run_path(client=CalibratedClient(annotations=[]))
        self.assertFalse(any("previous dialogue" in item.claim or "substituted source" in str(item.data)
                             for item in candidates[0].evidence.evidence))

    def test_annotation_failure_subtypes_remain_request_local_under_concurrency(self):
        barrier = Barrier(2)
        cases = (
            ([entry(witnesses=[{"source_id": "S1", "quote": "Absent literal."}])], "invalid_literal_witness"),
            ([entry(source_ids=("S9",), witnesses=[{"source_id": "S9", "quote": TEXT}])], "invalid_source_id"),
        )
        def worker(case):
            annotations, code = case
            run, _ = provider()
            client, events = CalibratedClient(annotations=annotations), []
            with acceptance_shadow_events(events.append):
                barrier.wait(timeout=10)
                result = run(client, "What capability does the service document?", [], core_answer_contract=contract())
            return result, events, code
        with redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=2) as pool:
            pairs = list(pool.map(worker, cases))
        for result, events, code in pairs:
            self.assert_published_unchanged(result)
            failures = [value for value in events if "Acceptance shadow binding failure:" in value]
            self.assertEqual(len(failures), 1)
            self.assertIn("code=" + code, failures[0])
            other = "invalid_source_id" if code == "invalid_literal_witness" else "invalid_literal_witness"
            self.assertNotIn(other, " ".join(events))
            self.assertTrue(any("Acceptance shadow: ACCEPTED" in value for value in events))

    def test_nonpublic_generation_contracts_and_media_do_not_enter_calibrated_lane(self):
        excluded = (
            contract(mode="stable_model_knowledge", authority="local_model_knowledge"),
            contract(intent="casual_conversation", mode="user_context", authority="live_conversation"),
            contract(intent="share_opinion", mode="subjective_opinion", authority="opinion"),
            contract(intent="recommendation_request", mode="model_knowledge", authority="local_model_knowledge"),
            contract(intent="share_opinion", mode="public_source_verified_opinion"),
            contract(intent="consequential_advice", mode="public_source_verified_advice"),
        )
        for runtime in excluded:
            with self.subTest(intent=runtime.intent, mode=runtime.epistemic_mode):
                result, client, candidates, _, events = self.run_path(runtime=runtime)
                self.assert_published_unchanged(result)
                self.assertFalse(candidates)
                self.assertFalse(events)
                self.assertFalse(client.bounded_options)
        result, client, candidates, _, events = self.run_path(overrides={
            "prepare_spoiler_context": lambda **kwargs: {"domain_active": True},
        })
        self.assert_published_unchanged(result)
        self.assertFalse(candidates)
        self.assertFalse(events)
        self.assertFalse(client.bounded_options)

    def test_legacy_sentence_salvage_does_not_enter_new_generated_shadow_lane(self):
        result, client, candidates, _, events = self.run_path(client=SalvageClient())
        self.assert_published_unchanged(result)
        self.assertFalse(candidates)
        self.assertFalse(events)
        self.assertFalse(client.bounded_options)
        self.assertEqual(len(client.calls), 2)


if __name__ == "__main__":
    unittest.main()
