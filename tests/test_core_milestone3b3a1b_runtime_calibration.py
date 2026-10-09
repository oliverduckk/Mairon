"""Exercise the real selected-public function with offline scripted transport.

The legacy verifier, binder, canonical adapter, acceptance evaluator and
history tail are production code. Every new observation remains non-enforcing.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
from threading import Barrier
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_core_milestone3b3a1a_runtime_calibration as prior_runtime
from test_core_milestone3b3a1_runtime_calibration import CalibratedClient, entry
from test_core_milestone3b3a_public_shadow_integration import TEXT, URL, contract, provider, research
from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_public import (
    OFFICIAL_SOURCE_SUPPORT, PUBLIC_SENTENCE_SUPPORT, PUBLIC_VERIFIER_CONSISTENCY,
    SOURCE_IDENTITY, SOURCE_READ_PROVENANCE,
)
from core.acceptance_shadow import acceptance_shadow_events
from core.answer_candidate import AcceptedSentence, AcceptanceDecision, AcceptanceStatus, CandidateOrigin
from core.evidence import EvidenceKind


class RuntimeCalibrationTests(unittest.TestCase):
    # Reuse the already validated complete-function fixture, not a rewritten
    # implementation of the production path or a synthetic publication loop.
    run_path = prior_runtime.RuntimeCalibrationTests.run_path
    assert_published_unchanged = prior_runtime.RuntimeCalibrationTests.assert_published_unchanged

    def test_real_qualified_first_person_limitation_is_accepted_unchanged(self):
        text = 'I don\'t recognise the term "voralic conduit" in fluid mechanics.'
        annotation = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable")]
        with patch("research.research_jobs.create_research_job") as create:
            result, client, candidates, decisions, events = self.run_path(client=CalibratedClient(text, annotation))
        self.assert_published_unchanged(result, text)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(candidates[0].evidence.metadata["verifier_source_bindings"], "available")
        self.assertTrue(any("status=COMPLETE" in value for value in events))
        self.assertEqual(len(client.calls), 3)
        create.assert_not_called()

    def test_unfamiliarity_context_is_observed_without_starting_background_research(self):
        text = "I'm unfamiliar with 'mervic braid' in the context of computational geometry."
        annotation = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable")]
        with patch("research.research_jobs.create_research_job") as create:
            result, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, annotation))
        self.assert_published_unchanged(result, text)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        create.assert_not_called()

    def test_factual_context_tail_is_rejected_observationally_and_still_published(self):
        text = "I don't recognise 'voralic conduit' in mechanics, but it contains copper."
        annotation = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable")]
        result, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, annotation))
        self.assert_published_unchanged(result, text)
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, decisions[0].violated_invariants)
        self.assertNotEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)

    def test_quoted_numeric_topic_is_not_accepted_as_self_knowledge(self):
        text = "I don't recognise the term 'pressure 918' in mechanics."
        annotation = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable")]
        result, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, annotation))
        self.assert_published_unchanged(result, text)
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, decisions[0].violated_invariants)

    def test_annotation_capability_failure_alone_still_leaves_ordinary_facts_accepted(self):
        annotation = [entry(witnesses=[{"source_id": "S1", "quote": "An unretained literal."}])]
        result, _, candidates, decisions, events = self.run_path(client=CalibratedClient(annotations=annotation))
        self.assert_published_unchanged(result)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, decisions[0].violated_invariants)
        self.assertEqual(candidates[0].evidence.metadata["public_source_bindings"]["failure_domain"],
                         "annotation_capability")
        self.assertTrue(any("code=invalid_literal_witness" in value for value in events))

    def test_natural_exact_source_and_conditional_honesty_requirements_reach_core(self):
        annotation = [entry(witnesses=[{"source_id": "S1", "quote": "An unretained literal."}])]
        result, _, candidates, decisions, events = self.run_path(
            client=CalibratedClient(annotations=annotation),
            current="Which official link did you use? If you didn't actually read it, say so.")
        self.assert_published_unchanged(result)
        for name in ("official_source_required", "source_read_required", "exact_source_required"):
            self.assertTrue(candidates[0].contract.metadata[name])
        for invariant in (OFFICIAL_SOURCE_SUPPORT, SOURCE_READ_PROVENANCE, SOURCE_IDENTITY):
            self.assertIn(invariant, decisions[0].violated_invariants)
        self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, decisions[0].violated_invariants)
        self.assertTrue(any("domain=annotation_capability" in value for value in events))

    def test_which_link_from_and_conditional_check_request_remain_independent(self):
        annotation = [entry(witnesses=[{"source_id": "S1", "quote": "An unretained literal."}])]
        result, _, candidates, decisions, _ = self.run_path(
            client=CalibratedClient(annotations=annotation),
            current="Which link is that from? If you haven't actually checked it, be explicit.")
        self.assert_published_unchanged(result)
        self.assertTrue(candidates[0].contract.metadata["exact_source_required"])
        self.assertTrue(candidates[0].contract.metadata["source_read_required"])
        self.assertIn(SOURCE_IDENTITY, decisions[0].violated_invariants)
        self.assertIn(SOURCE_READ_PROVENANCE, decisions[0].violated_invariants)

    def test_bound_loaded_source_can_satisfy_natural_source_and_read_request(self):
        text = TEXT + " The source is right here: " + URL + "."
        annotation = [entry(), entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, candidates, decisions, _ = self.run_path(
            client=CalibratedClient(text, annotation),
            current="What URL did that come from? If you didn't load it, say that.")
        self.assert_published_unchanged(result, text)
        self.assertTrue(candidates[0].contract.metadata["exact_source_required"])
        self.assertTrue(candidates[0].contract.metadata["source_read_required"])
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)

    def test_terse_factual_answer_with_good_binding_remains_factual_and_accepted(self):
        text = "No, it doesn't. Here is the official source: " + URL + "."
        annotation = [entry(), entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, candidates, decisions, _ = self.run_path(
            client=CalibratedClient(text, annotation), current="Check the official page and give its source URL.")
        self.assert_published_unchanged(result, text)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(candidates[0].evidence.metadata["public_source_bindings"]["sentences"][0]["claim_kind"],
                         "factual")

    def test_mislabelled_terse_answer_is_not_exempted_by_yes_no_wording(self):
        text = "No, it doesn't. Here is the source: " + URL + "."
        annotation = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable"),
                      entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, annotation))
        self.assert_published_unchanged(result, text)
        self.assertIn(PUBLIC_SENTENCE_SUPPORT, decisions[0].violated_invariants)

    def test_indexed_diagnostic_identifies_terse_label_not_valid_caption(self):
        text = "No, it doesn't. Here is the source: " + URL + "."
        annotation = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable"),
                      entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, _, decisions, events = self.run_path(client=CalibratedClient(text, annotation))
        self.assert_published_unchanged(result, text)
        failures = decisions[0].metadata["typed_diagnostics"]["public_factual_verifier_provenance"]["public_sentence_failures"]
        self.assertEqual(failures, ({"sentence_index": 1, "annotation_kind": "limitation",
                                     "code": "annotation_limitation_mismatch"},))
        traces = [value for value in events if "Acceptance shadow sentence:" in value]
        self.assertEqual(len(traces), 1)
        self.assertIn("index=1; kind=limitation; code=annotation_limitation_mismatch", traces[0])
        for event in events:
            self.assertLessEqual(len(event), 180)
            self.assertNotIn(text, event)
            self.assertNotIn(URL, event)

    def test_indexed_nonfactual_label_mismatch_is_bounded_metadata(self):
        annotation = [entry(kind="non_factual", source_ids=(), witnesses=(), scope="not_applicable")]
        result, _, _, decisions, events = self.run_path(client=CalibratedClient(annotations=annotation))
        self.assert_published_unchanged(result)
        failures = decisions[0].metadata["typed_diagnostics"]["public_factual_verifier_provenance"]["public_sentence_failures"]
        self.assertEqual(failures, ({"sentence_index": 1, "annotation_kind": "non_factual",
                                     "code": "annotation_non_factual_mismatch"},))
        self.assertTrue(any("index=1; kind=non_factual; code=annotation_non_factual_mismatch" in event for event in events))

    def test_indexed_content_witness_failure_does_not_implicate_other_sentences(self):
        text = TEXT + " The page says the device predicts weather."
        annotation = [entry(), entry(2, witnesses=(), provenance="citation")]
        result, _, _, decisions, events = self.run_path(client=CalibratedClient(text, annotation))
        self.assert_published_unchanged(result, text)
        failures = decisions[0].metadata["typed_diagnostics"]["public_factual_verifier_provenance"]["public_sentence_failures"]
        self.assertEqual(failures, ({"sentence_index": 2, "annotation_kind": "factual",
                                     "code": "factual_witness_missing"},))
        self.assertTrue(any("index=2; kind=factual; code=factual_witness_missing" in event for event in events))

    def test_faulty_evaluator_cannot_leak_sentence_diagnostic_payloads(self):
        secret = "Private diagnostic content " + URL
        choice = AcceptanceDecision(AcceptanceStatus.REJECTED, TEXT,
            reasons=(secret,), violated_invariants=(SOURCE_IDENTITY,),
            metadata={"typed_diagnostics": {"public_factual_verifier_provenance": {
                "public_sentence_failures": (
                    {"sentence_index": 1, "annotation_kind": "limitation", "code": "annotation_limitation_mismatch", "text": secret},
                    {"sentence_index": 1, "annotation_kind": secret, "code": "annotation_limitation_mismatch"},
                    {"sentence_index": 1, "annotation_kind": "factual", "code": secret},
                    {"sentence_index": True, "annotation_kind": "factual", "code": "factual_witness_missing"},
                    {"sentence_index": 918, "annotation_kind": "factual", "code": "factual_witness_missing"},
                ),
            }}})
        result, _, _, _, events = self.run_path(decision=choice)
        self.assert_published_unchanged(result)
        traces = [value for value in events if "Acceptance shadow sentence:" in value]
        self.assertEqual(len(traces), 1)
        self.assertIn("index=1; kind=limitation; code=annotation_limitation_mismatch", traces[0])
        for event in events:
            self.assertLessEqual(len(event), 180)
            self.assertNotIn(secret, event)
            self.assertNotIn(URL, event)

    def test_false_official_url_caption_retains_identity_and_authority_failures(self):
        retained = research()
        retained["sources"][0]["authority_tier"] = "independent_editorial"
        text = "No, it doesn't. Here is the official source: http://docs.vendor.example/service/other."
        annotation = [entry(), entry(2, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, annotation), retained=retained)
        self.assert_published_unchanged(result, text)
        self.assertIn(SOURCE_IDENTITY, decisions[0].violated_invariants)
        self.assertIn(OFFICIAL_SOURCE_SUPPORT, decisions[0].violated_invariants)
        self.assertNotIn(PUBLIC_SENTENCE_SUPPORT, decisions[0].violated_invariants)

    def test_fetched_or_pulled_claim_with_bad_annotations_preserves_read_obligation(self):
        for text in ("I fetched the page.", "I pulled the text from the live site.",
                     "Just pulled the page text from the live site.",
                     "I did not load it, but I pulled the text from the live site.",
                     "I did not browse there, but just fetched the page text."):
            with self.subTest(text=text):
                annotation = [entry(witnesses=[{"source_id": "S1", "quote": "An unretained literal."}],
                                    provenance="read")]
                result, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, annotation))
                self.assert_published_unchanged(result, text)
                self.assertIn(SOURCE_READ_PROVENANCE, decisions[0].violated_invariants)
                self.assertNotIn(PUBLIC_VERIFIER_CONSISTENCY, decisions[0].violated_invariants)

    def test_actual_loaded_fetched_identity_can_remain_accepted(self):
        text = TEXT + " I fetched the page. Source: " + URL + "."
        annotation = [entry(), entry(2, witnesses=(), provenance="read", scope="not_applicable"),
                      entry(3, witnesses=(), provenance="citation", scope="not_applicable")]
        result, _, _, decisions, _ = self.run_path(
            client=CalibratedClient(text, annotation), current="Please read the source page and give its source URL.")
        self.assert_published_unchanged(result, text)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)

    def test_calibrated_public_decisions_have_no_publication_or_history_authority(self):
        baseline, _, _, _, _ = self.run_path(observer=lambda **kwargs: None)
        for status in AcceptanceStatus:
            with self.subTest(status=status):
                choice = AcceptanceDecision(
                    status, TEXT,
                    reasons=() if status == AcceptanceStatus.ACCEPTED else ("A bounded observational test failure.",),
                    violated_invariants=() if status == AcceptanceStatus.ACCEPTED else (SOURCE_IDENTITY,),
                    accepted_sentences=(AcceptedSentence(1, TEXT),) if status == AcceptanceStatus.SALVAGEABLE else (),
                )
                result, _, candidates, decisions, _ = self.run_path(decision=choice)
                self.assertEqual(result, baseline)
                self.assertEqual(len(candidates), 1)
                self.assertEqual(decisions[0].status, status)

    def test_evaluator_failure_remains_observational(self):
        result, _, _, _, events = self.run_path(evaluation_error=RuntimeError("Private evaluator payload"))
        self.assert_published_unchanged(result)
        self.assertTrue(any("EVALUATION_ERROR" in value for value in events))
        self.assertNotIn("Private evaluator payload", " ".join(events))

    def test_adapter_failure_remains_observational(self):
        with patch("core.public_answer_evidence.build_public_answer_candidate", side_effect=ValueError("Private adapter payload")):
            result, _, candidates, _, events = self.run_path()
        self.assert_published_unchanged(result)
        self.assertFalse(candidates)
        self.assertTrue(any("EVALUATION_ERROR" in value for value in events))
        self.assertNotIn("Private adapter payload", " ".join(events))

    def test_diagnostic_sink_failure_remains_observational(self):
        def unavailable(event):
            raise RuntimeError("Private sink payload")
        result, _, candidates, decisions, events = self.run_path(sink=unavailable)
        self.assert_published_unchanged(result)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertFalse(events)

    def test_normal_calibrated_candidate_does_not_promote_assistant_history(self):
        _, _, candidates, _, _ = self.run_path()
        self.assertTrue(all(item.kind == EvidenceKind.PUBLIC_SOURCE for item in candidates[0].evidence.evidence))
        self.assertFalse(any("previous dialogue" in item.claim or "substituted source" in str(item.data)
                             for item in candidates[0].evidence.evidence))

    def test_actual_runtime_semantics_are_origin_invariant(self):
        text = "I don't recognise the term 'mervic braid' in geometry."
        annotation = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable")]
        _, _, candidates, decisions, _ = self.run_path(client=CalibratedClient(text, annotation))
        for origin in CandidateOrigin:
            with self.subTest(origin=origin):
                self.assertEqual(CoreAcceptanceEvaluator().evaluate(candidates[0].with_origin(origin)), decisions[0])

    def test_concurrent_requests_keep_source_obligations_and_diagnostics_separate(self):
        barrier = Barrier(2)
        cases = (
            ("What capability does the service document?", AcceptanceStatus.ACCEPTED),
            ("Which official link did you use? If you didn't load it, say so.", AcceptanceStatus.REJECTED),
        )
        def worker(case):
            current, status = case
            client = CalibratedClient(annotations=[entry(witnesses=[{"source_id": "S1", "quote": "An unretained literal."}])])
            run, _ = provider()
            events = []
            with acceptance_shadow_events(events.append):
                barrier.wait(timeout=10)
                result = run(client, current, [], core_answer_contract=contract())
            return result, events, status
        with redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=2) as executor:
            pairs = list(executor.map(worker, cases))
        for result, events, status in pairs:
            self.assert_published_unchanged(result)
            self.assertTrue(any("Acceptance shadow: " + status.value.upper() in value for value in events))
            if status == AcceptanceStatus.ACCEPTED:
                self.assertFalse(any("source_identity" in value or "official_source_support" in value for value in events))
            else:
                self.assertTrue(any("source_identity" in value for value in events))
                self.assertTrue(any("source_read_provenance" in value for value in events))

    def test_all_nonpublic_contracts_and_media_remain_outside_this_calibration(self):
        for runtime in (
            contract(mode="stable_model_knowledge", authority="local_model_knowledge"),
            contract(intent="casual_conversation", mode="user_context", authority="live_conversation"),
            contract(intent="share_opinion", mode="subjective_opinion", authority="opinion"),
            contract(intent="recommendation_request", mode="model_knowledge", authority="local_model_knowledge"),
            contract(intent="share_opinion", mode="public_source_verified_opinion"),
            contract(intent="consequential_advice", mode="public_source_verified_advice"),
        ):
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

    def test_concurrent_sentence_failure_codes_remain_request_local(self):
        barrier = Barrier(2)
        cases = (("limitation", "annotation_limitation_mismatch"),
                 ("non_factual", "annotation_non_factual_mismatch"))
        def worker(case):
            kind, code = case
            client = CalibratedClient(annotations=[entry(kind=kind, source_ids=(), witnesses=(), scope="not_applicable")])
            run, _ = provider()
            events = []
            with acceptance_shadow_events(events.append):
                barrier.wait(timeout=10)
                result = run(client, "What capability does the service document?", [], core_answer_contract=contract())
            return result, events, kind, code
        with redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=2) as executor:
            pairs = list(executor.map(worker, cases))
        for result, events, kind, code in pairs:
            self.assert_published_unchanged(result)
            traces = [value for value in events if "Acceptance shadow sentence:" in value]
            self.assertEqual(len(traces), 1)
            self.assertIn("index=1; kind=" + kind + "; code=" + code, traces[0])
            other = "annotation_non_factual_mismatch" if kind == "limitation" else "annotation_limitation_mismatch"
            self.assertNotIn(other, " ".join(events))

    def test_sentence_salvage_still_does_not_enter_generated_public_observation(self):
        result, client, candidates, _, events = self.run_path(client=prior_runtime.SalvageClient())
        self.assert_published_unchanged(result)
        self.assertFalse(candidates)
        self.assertFalse(events)
        self.assertFalse(client.bounded_options)


if __name__ == "__main__":
    unittest.main()
