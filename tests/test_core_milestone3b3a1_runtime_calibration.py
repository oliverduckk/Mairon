"""Source bindings execute in the real selected public production function.

Only model/network dependencies are scripted. The unchanged legacy verifier,
new bounded binder, canonical adapter, evaluator and history tail are real.
"""
from __future__ import annotations

import copy
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

from test_core_milestone3b3a_public_shadow_integration import TEXT, URL, contract, provider, research
from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_shadow import acceptance_shadow_events
from core.answer_candidate import AcceptanceStatus
from core.public_source_requirements import public_source_requirements
from research.public_factual_grounding import _split_draft_sentences


def entry(index=1, *, source_ids=("S1",), witnesses=None, scope="supported", kind="factual", provenance="none"):
    return {"index": index, "claim_kind": kind, "source_ids": list(source_ids),
            "witnesses": list(witnesses if witnesses is not None else [{"source_id": "S1", "quote": TEXT}]),
            "provenance_claim": provenance, "scope_status": scope}


class CalibratedClient:
    def __init__(self, text=TEXT, annotations=None, annotation_error=None):
        self.text = text
        self.annotations = annotations if annotations is not None else [entry()]
        self.annotation_error = annotation_error
        self.calls = []
        self.bounded_options = []
        self.closed = 0

    def with_options(self, **kwargs):
        self.bounded_options.append(kwargs)
        return SimpleNamespace(chat=self.chat, close=self.close)

    def close(self):
        self.closed += 1

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        properties = kwargs.get("format", {}).get("properties", {})
        if "sentences" in properties:
            if self.annotation_error:
                raise self.annotation_error
            content = json.dumps({"sentences": self.annotations})
        elif "sentence_assessments" in properties:
            content = json.dumps({"supported": True, "unsupported_claims": [],
                                  "sentence_assessments": [{"index": index, "supported": True}
                                      for index in range(1, len(_split_draft_sentences(self.text)) + 1)]})
        else:
            content = self.text
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")


class RuntimeCalibrationTests(unittest.TestCase):
    def run_path(self, *, client=None, current="What capability does the service document?", retained=None, observer=None):
        client = client or CalibratedClient()
        kwargs = {"retained": retained} if retained is not None else {}
        if observer is not None:
            kwargs["observer"] = observer
        run, _ = provider(**kwargs)
        candidates, decisions, events = [], [], []
        evaluate = CoreAcceptanceEvaluator.evaluate

        def capture(evaluator, candidate):
            candidates.append(candidate)
            decision = evaluate(evaluator, candidate)
            decisions.append(decision)
            return decision

        prior = [{"role": "assistant", "content": "A prior fabricated source description."}]
        with redirect_stdout(io.StringIO()), acceptance_shadow_events(events.append), patch.object(CoreAcceptanceEvaluator, "evaluate", capture):
            result = run(client, current, prior, core_answer_contract=contract())
        self.assertEqual(result[0], client.text)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": client.text})
        return result, client, candidates, decisions, events

    def test_normal_successful_runtime_has_real_source_bindings_at_core_boundary(self):
        result, client, candidates, decisions, events = self.run_path()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].evidence.metadata["verifier_source_bindings"], "available")
        bound = candidates[0].evidence.metadata["public_source_bindings"]["sentences"][0]
        self.assertEqual(bound["source_ids"], ("S1",))
        self.assertEqual(bound["evidence_ids"], (candidates[0].evidence.authoritative_evidence[0].evidence_id,))
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(len(client.bounded_options), 1)
        self.assertTrue(any("status=COMPLETE" in event for event in events))
        self.assertFalse(any("source_bindings_unavailable" in event for event in events))

    def test_first_turn_read_and_official_obligations_reach_core(self):
        text = TEXT + " Source: " + URL + "."
        annotations = [entry(), entry(2, provenance="citation")]
        _, _, candidates, decisions, _ = self.run_path(
            client=CalibratedClient(text, annotations),
            current="Please check the official documentation and give the actual source URL.",
        )
        metadata = candidates[0].contract.metadata
        self.assertTrue(metadata["source_read_required"])
        self.assertTrue(metadata["official_source_required"])
        self.assertTrue(metadata["exact_source_required"])
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)

    def test_first_turn_source_claim_without_bindings_is_rejected_but_still_published(self):
        text = "The page says queued export is supported."
        _, _, _, decisions, _ = self.run_path(client=CalibratedClient(text, [entry(source_ids=(), witnesses=(), provenance="source_assertion")]),
            current="Please read the official page and quote its explanation.")
        self.assertNotEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertIn("source_read_provenance", decisions[0].violated_invariants)

    def test_current_turn_primary_requirement_survives_an_ordinary_prior_search_query(self):
        retained = research()
        retained["official_documentation_required"] = False
        retained["sources"][0]["authority_tier"] = "independent_editorial"
        _, _, candidates, decisions, _ = self.run_path(retained=retained,
            current="Please consult a primary source for this claim.")
        self.assertTrue(candidates[0].contract.metadata["primary_source_required"])
        self.assertIn("official_source_support", decisions[0].violated_invariants)

    def test_scope_and_currentness_failures_coexist_on_real_runtime_candidate(self):
        retained = research()
        retained["freshness_sensitive"] = True
        retained["sources"][0]["title"] = "Specialized service edition guide"
        _, _, _, decisions, _ = self.run_path(retained=retained,
            client=CalibratedClient(annotations=[entry(scope="unsupported")]),
            current="What is the current state across all service editions?")
        self.assertIn("insufficient_scope_support", decisions[0].violated_invariants)
        self.assertIn("insufficient_currentness_support", decisions[0].violated_invariants)

    def test_truthful_immediate_hedge_is_a_limitation_without_a_background_job(self):
        text = "I don't know enough to define this reliably."
        annotations = [entry(kind="limitation", source_ids=(), witnesses=(), scope="not_applicable")]
        retained = research()
        retained["freshness_sensitive"] = True
        with patch("research.research_jobs.create_research_job") as create:
            _, _, candidates, decisions, _ = self.run_path(client=CalibratedClient(text, annotations), retained=retained)
        create.assert_not_called()
        self.assertEqual(decisions[0].status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(candidates[0].evidence.metadata["public_source_bindings"]["sentences"][0]["claim_kind"], "limitation")

    def test_binder_failure_never_changes_response_or_history(self):
        baseline, _, _, _, _ = self.run_path(observer=lambda **kwargs: None)
        result, _, _, _, events = self.run_path(client=CalibratedClient(annotation_error=RuntimeError("private contents")))
        self.assertEqual(result, baseline)
        self.assertNotIn("private contents", " ".join(events))

    def test_real_sink_fault_has_no_publication_authority(self):
        run, _ = provider()
        client = CalibratedClient()
        def fail(event):
            raise RuntimeError("private diagnostic")
        with redirect_stdout(io.StringIO()), acceptance_shadow_events(fail):
            result = run(client, "What capability does the service document?", [], core_answer_contract=contract())
        self.assertEqual(result[0], TEXT)
        self.assertEqual(result[1][-1]["content"], TEXT)

    def test_concurrent_binding_diagnostics_stay_request_local(self):
        barrier = Barrier(2)
        def worker(failed):
            run, _ = provider()
            events = []
            client = CalibratedClient(annotation_error=RuntimeError("private") if failed else None)
            with acceptance_shadow_events(events.append):
                barrier.wait(timeout=10)
                result = run(client, "What capability does the service document?", [], core_answer_contract=contract())
            return result[0], events
        with redirect_stdout(io.StringIO()), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, (False, True)))
        self.assertEqual([value[0] for value in results], [TEXT, TEXT])
        self.assertTrue(any("status=COMPLETE" in event for event in results[0][1]))
        self.assertFalse(any("status=COMPLETE" in event for event in results[1][1]))


class CurrentRequestRequirementsTests(unittest.TestCase):
    def test_general_affirmative_read_forms(self):
        for text in ("Please read the handbook.", "Can you check the primary source?", "I need you to consult the official manual."):
            with self.subTest(text=text):
                self.assertTrue(public_source_requirements(text)["source_read_required"])

    def test_primary_is_a_requirement_not_an_authority_label(self):
        requirements = public_source_requirements("Use a primary source for the answer.")
        self.assertTrue(requirements["primary_source_required"])
        self.assertFalse(requirements["official_source_required"])

    def test_actual_source_url_is_an_explicit_completion_obligation(self):
        self.assertTrue(public_source_requirements("Give the actual source URL.")["exact_source_required"])

    def test_requested_url_keeps_path_and_query(self):
        requirements = public_source_requirements("Please read https://docs.vendor.example/other?revision=2.")
        self.assertEqual(requirements["requested_source_urls"], ("https://docs.vendor.example/other?revision=2",))

    def test_negated_conditional_and_quoted_read_commands_are_not_promoted(self):
        for text in ("Don't read the handbook.", "Do not read the manual.", "If you read the handbook, explain it.",
                     '"Please read the manual."', "Someone said read the handbook."):
            with self.subTest(text=text):
                self.assertFalse(public_source_requirements(text)["source_read_required"])

    def test_nonrequest_first_person_prior_read_does_not_create_current_read_obligation(self):
        self.assertFalse(public_source_requirements("I read the handbook last week.")["source_read_required"])

    def test_explicit_read_question_retains_provenance_obligation(self):
        for text in ("Did you actually read the manual?", "Have you loaded the source page?"):
            with self.subTest(text=text):
                self.assertTrue(public_source_requirements(text)["source_read_required"])

    def test_prior_official_read_report_does_not_constrain_new_source_authority(self):
        requirements = public_source_requirements("I already saw the official manual. What does the independent test show?")
        self.assertFalse(requirements["official_source_required"])

    def test_prior_reported_url_does_not_become_the_requested_source(self):
        requirements = public_source_requirements("Give the exact source URL. I used https://research.example/draft yesterday.")
        self.assertTrue(requirements["exact_source_required"])
        self.assertEqual(requirements["requested_source_urls"], ())

    def test_explicitly_declined_official_source_does_not_create_obligation(self):
        for text in ("Don't read the official manual.", "I don't need an official source."):
            with self.subTest(text=text):
                self.assertFalse(public_source_requirements(text)["official_source_required"])


if __name__ == "__main__":
    unittest.main()
