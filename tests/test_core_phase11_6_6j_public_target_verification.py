"""Neutral target-binding regressions for both existing public verifier calls.

No live model or web is used. Core verifies literal candidate/source witnesses
in the scoped assessment; candidate prose is never factual evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_contract_runtime import AnswerContractRuntime
from research.public_factual_grounding import (
    _split_draft_sentences, verify_public_factual_draft,
    verify_public_factual_salvage_completion,
)
from test_core_phase11_6_6c_public_content_authority import (
    Client, packet, verdict, witnesses,
)

USER = "Why does phased gating cause stripe noise?"
EXPLANATION = (
    "Phased gating changes sampling timing, which can produce stripe noise "
    "when readings overlap."
)
ADVICE = "Try changing the aperture setting."
BODY = EXPLANATION + " " + ADVICE
LIMITATION = "I cannot verify why phased gating causes stripe noise from the available evidence."
CONTRACT = AnswerContractRuntime(
    intent="factual_question", authority="public_web",
    epistemic_mode="public_source_verified", subject="phased gating and stripe noise",
)


def target(text=EXPLANATION, source_quote=BODY, **changes):
    value = {
        "index": 1, "outcome": "factual_explanation", "mechanism_bound": True,
        "effect_bound": True, "relationship_answered": True,
        "mechanism_quote": "Phased gating", "effect_quote": "stripe noise",
        "answer_quote": text, "source_id": "S1", "source_quote": source_quote,
    }
    value.update(changes)
    return value


def full_payload(text=EXPLANATION, body=BODY, assessment=None, include=True):
    sentences = _split_draft_sentences(text)
    claims = []
    for sentence in sentences:
        for item in witnesses(sentence, body):
            item["index"] = len(claims) + 1
            claims.append(item)
    value = verdict(len(sentences), claims=claims if claims else None)
    if include:
        value["explanation_target_assessments"] = [assessment or target()]
    return value


def completion_payload(assessment=None, include=True, outcome="factual_answer"):
    value = {"completed": True, "outcome": outcome, "request_fulfilled": True,
             "required_claim_assessments": [], "violations": []}
    if include:
        value["explanation_target_assessments"] = [assessment or target()]
    return value


def full(text=EXPLANATION, *, payload=None, body=BODY, state=None,
         runtime=CONTRACT, current=USER, **kwargs):
    client = Client(payload if payload is not None else full_payload(text, body))
    result = verify_public_factual_draft(
        client, "replaceable-model", current, text, json.dumps(state or packet(body)),
        core_answer_contract=runtime, **kwargs,
    )
    return result, client


def subset(text=EXPLANATION, *, payload=None, body=BODY, state=None,
           runtime=CONTRACT, current=USER):
    client = Client(payload if payload is not None else completion_payload())
    result = verify_public_factual_salvage_completion(
        client, "replaceable-model", current, text, runtime,
        json.dumps(state or packet(body)),
    )
    return result, client


class PublicTargetVerificationTests(unittest.TestCase):
    def test_full_unknown_cause_exact_body_has_independent_literal_target_proof(self):
        current = "Why do people discuss Neri?"
        text = "People discuss Neri because Neri criticised Solan."
        result, client = full(text, current=current, body=text,
                              payload=full_payload(text, text, include=False))
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_full_exact_body_about_other_target_cannot_supply_completion(self):
        current = "Why do people discuss Neri?"
        text = "People discuss Tovan because Tovan criticised Solan."
        result, client = full(text, current=current, body=text,
                              payload=full_payload(text, text, include=False))
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)

    def test_salvage_unknown_cause_exact_body_has_independent_literal_target_proof(self):
        current = "Why do people discuss Neri?"
        text = "People discuss Neri because Neri criticised Solan."
        result, client = subset(text, current=current, body=text,
                                payload=completion_payload(include=False))
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_unknown_cause_literal_proof_cannot_use_unread_source(self):
        current = "Why do people discuss Neri?"
        text = "People discuss Neri because Neri criticised Solan."
        result, client = full(text, current=current, state=packet(text, read_success=False),
                              payload=full_payload(text, text, include=False))
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)

    def test_full_supported_bound_explanation_uses_one_existing_call(self):
        result, client = full()
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [EXPLANATION])
        self.assertEqual(len(client.calls), 1)
        self.assertIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_full_explanation_plus_supported_advice_remains_allowed(self):
        text = EXPLANATION + " " + ADVICE
        result, client = full(text)
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [EXPLANATION, ADVICE])
        self.assertEqual(len(client.calls), 1)

    def test_full_source_established_paraphrase_does_not_require_request_nouns(self):
        text = "Alternating gate timing can produce a banded readout artifact when readings overlap."
        body = ("Phased gating is also called alternating gate timing. "
                "Stripe noise is also known as banded readout artifact. " + text)
        response = full_payload(text, body, assessment=target(
            text=text, source_quote=body, mechanism_quote="Alternating gate timing",
            effect_quote="a banded readout artifact",
        ))
        result, _ = full(text, body=body, payload=response)
        self.assertFalse(result)

    def test_full_clear_candidate_antecedent_can_bind_pronoun(self):
        answer = "This feature can produce stripe noise when readings overlap."
        text = "Phased gating changes sampling timing. " + answer
        response = full_payload(text, assessment=target(
            text=answer, mechanism_quote="This feature",
        ))
        result, _ = full(text, payload=response)
        self.assertFalse(result)

    def test_full_ambiguous_candidate_antecedent_cannot_bind_pronoun(self):
        answer = "This feature can produce stripe noise when readings overlap."
        text = "Phased gating and stripe noise are both mentioned. " + answer
        response = full_payload(text, assessment=target(
            text=answer, mechanism_quote="This feature",
        ))
        result, _ = full(text, payload=response)
        self.assertTrue(result)

    def test_full_source_text_cannot_resolve_ambiguous_request_reference(self):
        text = "This feature can produce stripe noise when readings overlap."
        current = "Why does phased gating or cache sweeping cause stripe noise?"
        body = "Phased gating and cache sweeping can produce stripe noise when readings overlap."
        response = full_payload(text, body, assessment=target(
            text=text, mechanism_quote="This feature", source_quote=body))
        result, _ = full(text, payload=response, current=current, body=body)
        self.assertTrue(result)

    def test_full_positive_target_flags_cannot_bind_wrong_mechanism(self):
        text = "Static offset can produce stripe noise when readings overlap."
        body = EXPLANATION + " " + text
        response = full_payload(text, body, assessment=target(
            text=text, source_quote=body, mechanism_quote="Static offset",
        ))
        result, _ = full(text, body=body, payload=response)
        self.assertTrue(result)

    def test_full_positive_target_flags_cannot_bind_wrong_effect(self):
        text = "Phased gating can produce buffer delay when readings overlap."
        body = EXPLANATION + " " + text
        response = full_payload(text, body, assessment=target(
            text=text, source_quote=body, effect_quote="buffer delay",
        ))
        result, _ = full(text, body=body, payload=response)
        self.assertTrue(result)

    def test_full_global_positive_cannot_override_underbound_numeric_example(self):
        text = "When values jump from 12 to 31 to 18, the system keeps adjusting. " + ADVICE
        response = full_payload(text, body=text, assessment=target(
            text=text, source_quote=text, mechanism_quote="the system", effect_quote="adjusting",
            mechanism_bound=False, effect_bound=False, relationship_answered=False,
            outcome="incomplete",
        ))
        result, client = full(text, body=text, payload=response)
        self.assertTrue(result)
        self.assertTrue(result.verification_state["global_supported"])
        self.assertFalse(result.verification_state["effective_supported"])
        self.assertEqual(len(client.calls), 1)

    def test_full_mechanism_without_requested_effect_is_incomplete(self):
        text = "Phased gating changes sampling timing."
        response = full_payload(text, body=text, assessment=target(
            text=text, source_quote=text, effect_bound=False, effect_quote=None,
            relationship_answered=False, outcome="incomplete",
        ))
        result, _ = full(text, body=text, payload=response)
        self.assertTrue(result)

    def test_full_requested_effect_with_other_mechanism_is_incomplete(self):
        text = "Static offset can produce stripe noise when readings overlap."
        response = full_payload(text, body=text, assessment=target(
            text=text, source_quote=text, mechanism_bound=False,
            mechanism_quote="Static offset", relationship_answered=False, outcome="incomplete",
        ))
        result, _ = full(text, body=text, payload=response)
        self.assertTrue(result)

    def test_full_both_topics_without_requested_relation_is_incomplete(self):
        text = "Phased gating is available. Stripe noise is visible."
        response = full_payload(text, body=text, assessment=target(
            text=text, source_quote=text, relationship_answered=False, outcome="incomplete",
        ))
        result, _ = full(text, body=text, payload=response)
        self.assertTrue(result)

    def test_full_advice_only_remains_incomplete_even_with_target_positive(self):
        response = full_payload(ADVICE, body=ADVICE)
        result, _ = full(ADVICE, body=ADVICE, payload=response)
        self.assertTrue(result)

    def test_full_missing_scoped_assessment_fails_closed(self):
        result, _ = full(payload=full_payload(include=False))
        self.assertTrue(result)
        self.assertIn("explanation target", " ".join(result))

    def test_full_empty_scoped_assessment_fails_closed(self):
        response = full_payload()
        response["explanation_target_assessments"] = []
        result, _ = full(payload=response)
        self.assertTrue(result)

    def test_full_duplicate_scoped_assessment_fails_closed(self):
        response = full_payload()
        response["explanation_target_assessments"] *= 2
        result, _ = full(payload=response)
        self.assertTrue(result)

    def test_full_boolean_index_cannot_impersonate_index_one(self):
        result, _ = full(payload=full_payload(assessment=target(index=True)))
        self.assertTrue(result)

    def test_full_boolean_target_fields_are_strict(self):
        for name in ("mechanism_bound", "effect_bound", "relationship_answered"):
            for value in (1, "true", None):
                with self.subTest(name=name, value=value):
                    result, _ = full(payload=full_payload(assessment=target(**{name: value})))
                    self.assertTrue(result)

    def test_full_missing_target_field_fails_closed(self):
        value = target()
        value.pop("relationship_answered")
        result, _ = full(payload=full_payload(assessment=value))
        self.assertTrue(result)

    def test_full_invented_candidate_witness_fails_closed(self):
        result, _ = full(payload=full_payload(assessment=target(answer_quote="An unrelated assertion.")))
        self.assertTrue(result)

    def test_full_target_quote_absent_from_candidate_fails_closed(self):
        result, _ = full(payload=full_payload(assessment=target(mechanism_quote="rotary tuning")))
        self.assertTrue(result)

    def test_full_invented_source_witness_fails_closed(self):
        result, _ = full(payload=full_payload(assessment=target(source_quote="An unrelated source assertion.")))
        self.assertTrue(result)

    def test_full_unknown_source_id_cannot_supply_target_authority(self):
        result, _ = full(payload=full_payload(assessment=target(source_id="S99")))
        self.assertTrue(result)

    def test_full_unread_source_cannot_supply_target_authority(self):
        result, _ = full(state=packet(BODY, read_success=False))
        self.assertTrue(result)

    def test_full_rejected_source_cannot_supply_target_authority(self):
        result, _ = full(state=packet(BODY, accepted_as_evidence=False))
        self.assertTrue(result)

    def test_full_title_only_relation_cannot_supply_body_witness(self):
        state = packet("A settings document is listed.", title=EXPLANATION)
        result, _ = full(state=state)
        self.assertTrue(result)

    def test_full_truthful_bounded_limitation_needs_no_additional_assessment(self):
        result, client = full(LIMITATION, payload=full_payload(LIMITATION, include=False))
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_full_non_explanation_keeps_ordinary_schema(self):
        text = "Phased gating is available."
        result, client = full(text, current="Which feature is available?", body=text,
                              payload=full_payload(text, text, include=False))
        self.assertFalse(result)
        self.assertNotIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_full_non_public_contract_does_not_activate_target_protocol(self):
        text = "Phased gating changes sampling timing."
        runtime = AnswerContractRuntime(intent="opinion", authority="stable_model_knowledge",
                                       epistemic_mode="stable_model_knowledge")
        result, client = full(text, body=text, runtime=runtime,
                              payload=full_payload(text, text, include=False))
        self.assertFalse(result)
        self.assertNotIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_full_background_packet_does_not_activate_target_protocol(self):
        state = packet(BODY)
        state["research_kind"] = "background_research"
        result, client = full(state=state, payload=full_payload(include=False))
        self.assertFalse(result)
        self.assertNotIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_full_consequential_lane_does_not_activate_target_protocol(self):
        result, client = full(payload=full_payload(include=False), consequential_domain="financial")
        self.assertFalse(result)
        self.assertNotIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_full_transport_snapshots_target_assessment(self):
        response = full_payload()
        result, _ = full(payload=response)
        self.assertFalse(result)
        response["explanation_target_assessments"][0]["mechanism_bound"] = False
        self.assertTrue(result.verification_state["explanation_target_assessments"][0]["mechanism_bound"])

    def test_salvage_supported_bound_explanation_uses_one_existing_call(self):
        result, client = subset()
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_salvage_supported_explanation_plus_advice_can_complete(self):
        result, _ = subset(EXPLANATION + " " + ADVICE)
        self.assertFalse(result)

    def test_salvage_source_established_paraphrase_can_complete(self):
        text = "Alternating gate timing can produce a banded readout artifact when readings overlap."
        body = ("Phased gating is also called alternating gate timing. "
                "Stripe noise is also known as banded readout artifact. " + text)
        response = completion_payload(target(
            text=text, source_quote=body, mechanism_quote="Alternating gate timing",
            effect_quote="a banded readout artifact",
        ))
        result, _ = subset(text, body=body, payload=response)
        self.assertFalse(result)

    def test_salvage_deleted_antecedent_cannot_rescue_remaining_pronoun(self):
        text = "This feature can produce stripe noise when readings overlap."
        current = "Why does phased gating or cache sweeping cause stripe noise?"
        body = "Phased gating and cache sweeping can produce stripe noise when readings overlap."
        # The original deleted sentence could have selected one feature, but
        # neither this retained subset nor the ambiguous request selects it.
        response = completion_payload(target(
            text=text, mechanism_quote="This feature", source_quote=body))
        result, _ = subset(text, payload=response, current=current, body=body)
        self.assertTrue(result)

    def test_salvage_ambiguous_reference_remains_incomplete(self):
        answer = "This feature can produce stripe noise when readings overlap."
        text = "Phased gating and stripe noise are both mentioned. " + answer
        response = completion_payload(target(text=answer, mechanism_quote="This feature"))
        result, _ = subset(text, payload=response)
        self.assertTrue(result)

    def test_salvage_clear_retained_antecedent_can_complete(self):
        answer = "This feature can produce stripe noise when readings overlap."
        text = "Phased gating changes sampling timing. " + answer
        response = completion_payload(target(text=answer, mechanism_quote="This feature"))
        result, _ = subset(text, payload=response)
        self.assertFalse(result)

    def test_salvage_advice_only_cannot_complete_under_positive_global(self):
        result, client = subset(ADVICE)
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)

    def test_salvage_underbound_example_cannot_complete_under_positive_global(self):
        text = "The system keeps adjusting because values vary."
        response = completion_payload(target(
            text=text, source_quote=text, mechanism_bound=False, effect_bound=False,
            relationship_answered=False, mechanism_quote="The system", effect_quote="adjusting",
            outcome="incomplete",
        ))
        result, _ = subset(text, body=text, payload=response)
        self.assertTrue(result)

    def test_salvage_missing_scoped_assessment_fails_closed(self):
        result, _ = subset(payload=completion_payload(include=False))
        self.assertTrue(result)

    def test_salvage_missing_target_field_fails_closed(self):
        value = target()
        value.pop("effect_bound")
        result, _ = subset(payload=completion_payload(value))
        self.assertTrue(result)

    def test_salvage_false_target_field_cannot_be_erased_by_global_completion(self):
        for name in ("mechanism_bound", "effect_bound", "relationship_answered"):
            with self.subTest(name=name):
                result, _ = subset(payload=completion_payload(target(**{name: False})))
                self.assertTrue(result)

    def test_salvage_source_witness_must_still_be_retained_and_readable(self):
        for state in (packet(BODY, read_success=False),
                      packet(BODY, accepted_as_evidence=False),
                      packet("A settings document is listed.", title=EXPLANATION)):
            with self.subTest(state=state):
                result, _ = subset(state=state)
                self.assertTrue(result)

    def test_salvage_relevant_bounded_limitation_keeps_existing_schedule(self):
        result, client = subset(LIMITATION, payload=completion_payload(
            include=False, outcome="bounded_limitation"))
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_salvage_negative_request_completion_is_not_rescued_by_target(self):
        response = completion_payload()
        response["request_fulfilled"] = False
        result, _ = subset(payload=response)
        self.assertTrue(result)

    def test_full_positive_limitation_assessment_cannot_hide_factual_tail(self):
        for tail in ("; phased gating definitely causes stack noise.",
                     ", although phased gating always causes stack noise.",
                     ", so phased gating is safe."):
            with self.subTest(tail=tail):
                text = LIMITATION.rstrip(".") + tail
                assessment = target(text, None, outcome="bounded_limitation",
                                    mechanism_quote="phased gating", source_id=None)
                result, client = full(text, payload=full_payload(text, assessment=assessment))
                self.assertTrue(result)
                self.assertEqual(len(client.calls), 1)

    def test_salvage_positive_limitation_assessment_cannot_hide_factual_tail(self):
        for tail in ("; phased gating definitely causes stack noise.",
                     ", although phased gating always causes stack noise.",
                     ", so phased gating is safe."):
            with self.subTest(tail=tail):
                text = LIMITATION.rstrip(".") + tail
                assessment = target(text, None, outcome="bounded_limitation",
                                    mechanism_quote="phased gating", source_id=None)
                result, client = subset(text, payload=completion_payload(assessment))
                self.assertTrue(result)
                self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
