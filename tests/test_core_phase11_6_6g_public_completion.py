"""Neutral legacy-public explanation completion obligations (offline)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_contract_runtime import AnswerContractRuntime
from research.public_factual_grounding import (
    _public_advice_only_completion, _public_explanation_requested,
    _split_draft_sentences, requires_public_factual_salvage_completion,
    verify_public_factual_draft, verify_public_factual_salvage_completion,
)
from test_core_phase11_6_6c_public_content_authority import (
    Client, packet, verdict, witnesses,
)

USER = "Why does the relay buzz when the supply changes?"
ADVICE = "Try changing the setting or updating the controller if it persists."
EXPLANATION = "Intermittent contact interrupts power because the connection briefly opens."
LIMITATION = "I cannot verify why the relay buzzes from the available evidence."
CONTRACT = AnswerContractRuntime(intent="factual_question", authority="public_web",
                                epistemic_mode="public_source_verified")


def completion(*, fulfilled=True, outcome="factual_answer"):
    return {"completed": fulfilled, "outcome": outcome, "request_fulfilled": fulfilled,
            "required_claim_assessments": [],
            "violations": [] if fulfilled else ["incomplete_request"]}


def verify(text, current=USER, body=EXPLANATION, response=None):
    sentences = _split_draft_sentences(text)
    claims = []
    for sentence in sentences:
        # Witness indices refer to all Core obligations in their existing order.
        for item in witnesses(sentence, body):
            item["index"] = len(claims) + 1
            claims.append(item)
    client = Client(response or verdict(len(sentences), claims=claims if claims else None))
    result = verify_public_factual_draft(client, "replaceable-model", current, text,
                                        json.dumps(packet(body)))
    return result, client


class PublicExplanationCompletionTests(unittest.TestCase):
    def advice_only(self, text, current=USER):
        return _public_advice_only_completion(current, _split_draft_sentences(text))

    def test_why_request_creates_core_completion_obligation(self):
        self.assertTrue(_public_explanation_requested(USER))
        self.assertTrue(requires_public_factual_salvage_completion(CONTRACT, packet(), user_input=USER))

    def test_explain_request_creates_core_completion_obligation(self):
        self.assertTrue(_public_explanation_requested("Please explain the supply interruption."))
        self.assertTrue(requires_public_factual_salvage_completion(
            CONTRACT, packet(), user_input="Please explain the supply interruption."))

    def test_cause_request_creates_core_completion_obligation(self):
        self.assertTrue(_public_explanation_requested("What causes these interruptions?"))

    def test_ordinary_capability_request_has_no_explanation_obligation(self):
        self.assertFalse(_public_explanation_requested("Which operation does the service support?"))

    def test_imperative_advice_does_not_answer_why(self):
        self.assertTrue(self.advice_only(ADVICE))

    def test_modal_suggestion_does_not_answer_why(self):
        self.assertTrue(self.advice_only("You could inspect the cable."))

    def test_first_person_recommendation_does_not_answer_why(self):
        self.assertTrue(self.advice_only("I suggest checking the connector."))

    def test_next_step_does_not_answer_why(self):
        self.assertTrue(self.advice_only("The next step is a controlled test."))

    def test_advice_in_unrelated_domains_is_still_incomplete(self):
        for text in ("Try restarting the exporter.", "Check the feed rollers.",
                     "Consider replacing the seal.", "Reduce the current limit."):
            with self.subTest(text=text):
                self.assertTrue(self.advice_only(text))

    def test_worth_trying_suggestion_does_not_answer_why(self):
        self.assertTrue(self.advice_only("It might be worth checking the connector."))

    def test_bullet_suggestions_do_not_answer_why(self):
        self.assertTrue(self.advice_only("- Try a lower setting.\n- Inspect the connector."))

    def test_advice_heading_cannot_turn_advice_into_explanation(self):
        self.assertTrue(self.advice_only("Here are a few things to try:\nTry a lower setting."))

    def test_two_supported_suggestions_do_not_form_an_explanation(self):
        self.assertTrue(self.advice_only("Try a lower setting. You could inspect the connector."))

    def test_acknowledgement_cannot_turn_advice_into_explanation(self):
        self.assertTrue(self.advice_only("Okay. Try a lower setting."))

    def test_source_caption_cannot_turn_advice_into_explanation(self):
        self.assertTrue(self.advice_only("Try a lower setting. The source is https://docs.vendor.example/device."))

    def test_supported_explanation_plus_advice_is_not_advice_only(self):
        self.assertFalse(self.advice_only(EXPLANATION + " " + ADVICE))

    def test_explanation_inside_advice_remains_for_body_support_verifier(self):
        self.assertFalse(self.advice_only("Try a lower setting because high load deforms the seal."))

    def test_explanation_need_not_copy_request_words(self):
        self.assertFalse(self.advice_only(EXPLANATION))
        result, client = verify(EXPLANATION)
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_bounded_truthful_limitation_remains_available(self):
        self.assertFalse(self.advice_only(LIMITATION))
        result, _ = verify(LIMITATION)
        self.assertFalse(result)

    def test_ordinary_advice_request_is_unchanged(self):
        result, client = verify(ADVICE, current="What should I try next?")
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_positive_global_and_sentence_verdict_cannot_publish_advice_only(self):
        result, client = verify(ADVICE)
        self.assertTrue(result)
        self.assertIn("explanation request received advice", " ".join(result))
        self.assertEqual(result.accepted_sentences, [ADVICE], "truth support is separate from answer completion")
        self.assertEqual(len(client.calls), 1)

    def test_complete_verifier_state_retains_core_completion_rejection(self):
        result, _ = verify(ADVICE)
        self.assertTrue(result.verification_state["global_supported"])
        self.assertFalse(result.verification_state["effective_supported"])
        self.assertTrue(result.verification_state["assessment_complete"])

    def test_completion_positive_cannot_authorize_advice_only_subset(self):
        client = Client(completion())
        result = verify_public_factual_salvage_completion(client, "replaceable-model", USER,
                    ADVICE, CONTRACT, json.dumps(packet(EXPLANATION)))
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1, "existing bounded completion call schedule is retained")

    def test_completion_positive_can_accept_supported_explanation_subset(self):
        client = Client(completion())
        result = verify_public_factual_salvage_completion(client, "replaceable-model", USER,
                    EXPLANATION + " " + ADVICE, CONTRACT, json.dumps(packet(EXPLANATION)))
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_completion_positive_can_accept_truthful_limitation_subset(self):
        client = Client(completion(outcome="bounded_limitation"))
        result = verify_public_factual_salvage_completion(client, "replaceable-model", USER,
                    LIMITATION, CONTRACT, json.dumps(packet(EXPLANATION)))
        self.assertFalse(result)

    def test_negative_completion_remains_rejected(self):
        client = Client(completion(fulfilled=False, outcome="incomplete"))
        result = verify_public_factual_salvage_completion(client, "replaceable-model", USER,
                    EXPLANATION, CONTRACT, json.dumps(packet(EXPLANATION)))
        self.assertTrue(result)

    def test_malformed_completion_remains_fail_closed(self):
        client = Client({"completed": True})
        result = verify_public_factual_salvage_completion(client, "replaceable-model", USER,
                    ADVICE, CONTRACT, json.dumps(packet(EXPLANATION)))
        self.assertTrue(result)

    def test_unsupported_explanation_is_not_rescued_by_structural_completeness(self):
        response = verdict(1, claims=witnesses(EXPLANATION, None, supported=False), supported=False)
        result, _ = verify(EXPLANATION, response=response)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_plain_source_identity_retains_ordinary_legacy_behavior(self):
        result, _ = verify("The preview is called Avery Morgan.", current="What was it called?",
                           body="A preview called Avery Morgan exists.")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
