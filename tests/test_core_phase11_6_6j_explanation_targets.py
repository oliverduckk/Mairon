"""Neutral request-side explanation binding, without a model or publication."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research.public_explanation_targets import (
    explanation_target_obligations, explanation_target_schema,
    explanation_target_instruction, explanation_target_failures,
    explanation_limitation_complete, explanation_literal_target_complete,
)

USER = "Why does phased gating cause stripe noise?"
GOOD = "Phased gating can produce stripe noise because pulse timing varies."
LIMIT = "I cannot verify why stripe noise occurs from the available evidence."


def packet(body=GOOD, **state):
    source = {"source_id": "S1", "title": "Control subsystem guide",
              "url": "https://docs.vendor.example/control", "content_excerpt": body,
              "read_success": True, "accepted_as_evidence": True, "relevance_status": "accepted"}
    source.update(state)
    return {"research_kind": "public_factual", "freshness_required": False, "sources": [source]}


def assessment(text=GOOD, source=GOOD, **updates):
    value = {"index": 1, "outcome": "factual_explanation", "mechanism_bound": True,
             "effect_bound": True, "relationship_answered": True,
             "mechanism_quote": "Phased gating", "effect_quote": "stripe noise",
             "answer_quote": text, "source_id": "S1", "source_quote": source}
    value.update(updates)
    return value


def failures(text=GOOD, value=None, evidence=None, user=USER, sentences=None):
    return explanation_target_failures(explanation_target_obligations(user),
                [assessment(text)] if value is None else value,
                sentences or [text], evidence or packet())


class ExplanationTargetTests(unittest.TestCase):
    def test_direct_request_roles_are_user_owned(self):
        item = explanation_target_obligations(USER)[0]
        self.assertEqual((item["mechanism"], item["effect"]), ("phased gating", "stripe noise"))
        self.assertEqual(USER[item["request_start"]:item["request_end"]], item["request_span"])

    def test_condition_request_retains_effect_and_condition(self):
        item = explanation_target_obligations("Anyway why does the gauge pulse when adaptive sampling is enabled?")[0]
        self.assertEqual(item["effect"], "the gauge pulse")
        self.assertEqual(item["mechanism"], "adaptive sampling is enabled")

    def test_unspecified_cause_remains_unspecified(self):
        item = explanation_target_obligations("What causes stripe noise?")[0]
        self.assertIsNone(item["mechanism"])
        self.assertEqual(item["effect"], "stripe noise")

    def test_explicit_why_request_preserves_unsplit_target(self):
        item = explanation_target_obligations("Please explain why the timing offset occurs.")[0]
        self.assertEqual(item["effect"], "the timing offset occurs")
        self.assertIsNone(item["mechanism"])

    def test_definition_is_outside_causal_target_projection(self):
        self.assertFalse(explanation_target_obligations("Explain what the term scalar means."))

    def test_how_to_procedure_is_outside_causal_target_projection(self):
        self.assertFalse(explanation_target_obligations("Explain how to create an export."))

    def test_plain_noncausal_explanation_retains_legacy_completion(self):
        self.assertFalse(explanation_target_obligations("Please explain the timing offset."))

    def test_multiple_requests_are_separately_numbered(self):
        values = explanation_target_obligations(USER + " Why does damping produce drift?")
        self.assertEqual([v["index"] for v in values], [1, 2])

    def test_non_explanation_has_no_projected_obligation(self):
        self.assertFalse(explanation_target_obligations("What should I try next?"))

    def test_schema_is_required_strict_and_does_not_mutate_base(self):
        base = {"type": "object", "properties": {"supported": {"type": "boolean"}}, "required": ["supported"]}
        before = copy.deepcopy(base)
        result = explanation_target_schema(base)
        self.assertEqual(base, before)
        self.assertIn("explanation_target_assessments", result["required"])
        self.assertFalse(result["properties"]["explanation_target_assessments"]["items"]["additionalProperties"])

    def test_instruction_uses_request_and_admitted_source_identifiers(self):
        instruction = explanation_target_instruction(explanation_target_obligations(USER), packet())
        self.assertIn("phased gating", instruction)
        self.assertIn("S1", instruction)
        self.assertNotIn("https://docs.vendor.example/control", instruction)
        self.assertNotIn(GOOD, instruction)

    def test_supported_requested_relationship_passes(self):
        self.assertEqual(failures(), [])

    def test_numeric_adjacent_behavior_cannot_answer_requested_relationship(self):
        text = "When values jump from 12 to 31 to 18, the system keeps adjusting. Try changing setting C."
        value = assessment(text, mechanism_quote="the system", effect_quote="adjusting")
        self.assertTrue(failures(text, [value]))

    def test_losing_effect_is_incomplete(self):
        text = "Phased gating produces a timing offset."
        self.assertTrue(failures(text, [assessment(text, effect_quote="a timing offset")]))

    def test_replacing_mechanism_is_incomplete(self):
        text = "Queue saturation causes stripe noise."
        self.assertTrue(failures(text, [assessment(text, mechanism_quote="Queue saturation")]))

    def test_advice_does_not_become_explanation(self):
        text = "Try changing phased gating to reduce stripe noise."
        self.assertTrue(failures(text, [assessment(text, mechanism_quote="phased gating")]))

    def test_supported_explanation_can_accompany_advice(self):
        text = GOOD + " Try checking the connector."
        self.assertEqual(failures(text, [assessment(answer_quote=GOOD)], sentences=[GOOD, "Try checking the connector."]), [])

    def test_unrelated_cause_after_both_target_mentions_is_not_completion(self):
        text = "Phased gating is available. Stripe noise exists. Export stalls because the queue is full."
        value = assessment(text, mechanism_quote="Phased gating", effect_quote="Stripe noise")
        self.assertIn("explanation_candidate_relationship_unbound", failures(text, [value]))

    def test_unrelated_source_cause_cannot_bridge_target_mentions(self):
        body = "Phased gating is available. Stripe noise exists. Export stalls because the queue is full."
        self.assertIn("explanation_source_relationship_unbound", failures(value=[assessment(source=body)], evidence=packet(body)))

    def test_clear_pronoun_has_prior_candidate_antecedent(self):
        first = "Phased gating changes timing."
        second = "That mode can produce stripe noise because pulse timing varies."
        value = assessment(second, mechanism_quote="That mode")
        self.assertEqual(failures(first + " " + second, [value], sentences=[first, second]), [])

    def test_ambiguous_pronoun_cannot_choose_a_target(self):
        first = "Phased gating and stripe noise are mentioned."
        second = "That can produce stripe noise because pulse timing varies."
        value = assessment(second, mechanism_quote="That")
        self.assertTrue(failures(first + " " + second, [value], sentences=[first, second]))

    def test_single_requested_mechanism_can_be_unambiguous_subject_pronoun(self):
        text = "It can produce stripe noise because pulse timing varies."
        self.assertEqual(failures(text, [assessment(text, mechanism_quote="It")]), [])

    def test_double_pronoun_has_no_inspectable_role_binding(self):
        text = "It causes that because timing varies."
        self.assertTrue(failures(text, [assessment(text, mechanism_quote="It", effect_quote="that")]))

    def test_alternative_request_mechanisms_do_not_supply_unique_pronoun(self):
        request = "Why does phased gating or adaptive probing cause stripe noise?"
        body = "Phased gating or adaptive probing can produce stripe noise because timing varies."
        text = "It can produce stripe noise because timing varies."
        item = assessment(text, body, mechanism_quote="It")
        self.assertTrue(failures(text, [item], packet(body), user=request))

    def test_competing_prior_mechanism_makes_reference_ambiguous(self):
        first = "Phased gating and probing affect timing."
        second = "That mode causes stripe noise because timing varies."
        item = assessment(second, mechanism_quote="That mode")
        self.assertTrue(failures(first + " " + second, [item], sentences=[first, second]))

    def test_embedded_reference_letters_in_prior_word_do_not_erase_real_reference(self):
        first = "Phased gating modifies timing limits."
        second = "In some cases it produces stripe noise because pulse timing varies."
        item = assessment(second, mechanism_quote="it")
        self.assertEqual(failures(first + " " + second, [item], sentences=[first, second]), [])

    def test_embedded_letters_are_not_a_literal_reference_witness(self):
        first = "Phased gating is present."
        second = "Timing limits produce stripe noise because pulse timing varies."
        item = assessment(second, mechanism_quote="it")
        self.assertTrue(failures(first + " " + second, [item], sentences=[first, second]))

    def test_deleted_or_absent_antecedent_cannot_support_salvage(self):
        text = "That mode can produce stripe noise because pulse timing varies."
        # Multiple requests prevent an unqualified reference from choosing the
        # first target after its explicit antecedent was deleted.
        requests = USER + " Why does probing cause drift?"
        values = [assessment(text, mechanism_quote="That mode"), assessment(index=2)]
        self.assertTrue(failures(text, values, user=requests))

    def test_explicit_body_alias_can_support_paraphrase(self):
        body = "Phased gating is also called staggered sampling. Stripe noise is also called band artifacts. " + GOOD
        text = "Staggered sampling causes band artifacts because pulse timing varies."
        value = assessment(text, body, mechanism_quote="Staggered sampling", effect_quote="band artifacts")
        self.assertEqual(failures(text, [value], packet(body)), [])

    def test_unestablished_synonym_is_not_guessed(self):
        text = "Staggered sampling causes band artifacts because pulse timing varies."
        value = assessment(text, mechanism_quote="Staggered sampling", effect_quote="band artifacts")
        self.assertTrue(failures(text, [value]))

    def test_source_quote_must_bind_request_targets(self):
        body = "Adaptive probing causes thermal drift because load changes."
        self.assertIn("explanation_source_target_mismatch", failures(value=[assessment(source=body)], evidence=packet(body)))

    def test_wrong_source_identifier_fails_closed(self):
        self.assertIn("missing_explanation_body_witness", failures(value=[assessment(source_id="S2")]))

    def test_discovered_unread_source_cannot_support_relationship(self):
        self.assertTrue(failures(evidence=packet(read_success=False)))

    def test_rejected_source_cannot_support_relationship(self):
        self.assertTrue(failures(evidence=packet(accepted_as_evidence=False)))

    def test_title_is_not_body_support(self):
        value = assessment(source=GOOD)
        self.assertTrue(failures(value=[value], evidence=packet("The controller has two ports.", title=GOOD)))

    def test_candidate_text_is_not_source_evidence(self):
        self.assertTrue(failures(evidence=packet("The system has a service port.")))

    def test_missing_assessment_fails_closed(self):
        self.assertEqual(failures(value=[]), ["incomplete_explanation_target_assessments"])
        self.assertEqual(explanation_target_failures(explanation_target_obligations(USER), None, [GOOD], packet()),
                         ["missing_explanation_target_assessments"])

    def test_non_array_assessment_fails_closed(self):
        self.assertTrue(failures(value={"supported": True}))

    def test_duplicate_assessment_fails_closed(self):
        self.assertTrue(failures(value=[assessment(), assessment()]))

    def test_boolean_index_is_not_integer_index(self):
        self.assertTrue(failures(value=[assessment(index=True)]))

    def test_out_of_range_index_fails_closed(self):
        self.assertTrue(failures(value=[assessment(index=2)]))

    def test_missing_field_fails_closed(self):
        item = assessment()
        item.pop("effect_quote")
        self.assertTrue(failures(value=[item]))

    def test_extra_field_is_not_accepted(self):
        self.assertTrue(failures(value=[assessment(reason="hidden prose")]))

    def test_string_boolean_is_not_typed_support(self):
        self.assertTrue(failures(value=[assessment(relationship_answered="true")]))

    def test_global_positive_cannot_override_failed_scoped_flag(self):
        self.assertEqual(failures(value=[assessment(effect_bound=False)]), ["explanation_target_unfulfilled"])

    def test_incomplete_outcome_cannot_be_overridden_by_true_flags(self):
        self.assertEqual(failures(value=[assessment(outcome="incomplete")]), ["explanation_target_unfulfilled"])

    def test_invented_candidate_quote_fails_closed(self):
        self.assertIn("invalid_explanation_candidate_witness", failures(value=[assessment(mechanism_quote="Absent control")]))

    def test_invented_source_quote_fails_closed(self):
        self.assertIn("missing_explanation_body_witness", failures(value=[assessment(source_quote="Absent evidence")]))

    def test_target_roles_cannot_share_one_ambiguous_quote(self):
        self.assertIn("explanation_target_roles_not_distinct", failures(value=[assessment(mechanism_quote=GOOD, effect_quote=GOOD)]))

    def test_target_mentions_outside_answer_quote_are_insufficient(self):
        text = "Phased gating changes timing. Stripe noise is visible. Export slows because load rises."
        item = assessment("Export slows because load rises.", mechanism_quote="Phased gating", effect_quote="Stripe noise")
        self.assertTrue(failures(text, [item], sentences=text.split(". ")))

    def test_source_relationship_direction_is_preserved(self):
        body = "Stripe noise causes phased gating because the sensor reacts."
        self.assertIn("explanation_source_relationship_unbound", failures(value=[assessment(source=body)], evidence=packet(body)))

    def test_negated_source_relationship_cannot_support_positive_answer(self):
        body = "Phased gating does not cause stripe noise because timing is stable."
        self.assertIn("explanation_relationship_polarity_mismatch", failures(value=[assessment(source=body)], evidence=packet(body)))

    def test_candidate_causal_exclusion_is_not_positive_target_binding(self):
        text = "Phased gating does not cause stripe noise because timing is stable."
        self.assertTrue(failures(text, [assessment(text)]))

    def test_supported_denial_can_correct_false_causal_premise(self):
        text = "Phased gating does not cause stripe noise because timing is stable."
        self.assertEqual(failures(text, [assessment(text, text)], packet(text)), [])

    def test_unknown_mechanism_can_be_explained_without_fabricated_request_role(self):
        text = "Loose coupling causes stripe noise because timing varies."
        item = assessment(text, text, mechanism_quote=None)
        self.assertEqual(failures(text, [item], packet(text), user="What causes stripe noise?"), [])

    def test_source_cannot_replace_on_condition_with_off(self):
        user = "Why does stripe noise occur when phased gating is on?"
        body = "Phased gating is off and causes stripe noise because timing varies."
        self.assertIn("explanation_condition_scope_mismatch", failures(value=[assessment(source=body)], evidence=packet(body), user=user))

    def test_candidate_cannot_replace_on_condition_with_off(self):
        user = "Why does stripe noise occur when phased gating is on?"
        text = "Phased gating is off and causes stripe noise because timing varies."
        self.assertIn("explanation_condition_scope_mismatch", failures(text, [assessment(text)], user=user))

    def test_transparent_limitation_preserves_requested_effect_and_causal_gap(self):
        self.assertTrue(explanation_limitation_complete(explanation_target_obligations(USER), [LIMIT]))

    def test_unrelated_limitation_does_not_complete_request(self):
        self.assertFalse(explanation_limitation_complete(explanation_target_obligations(USER), ["I cannot verify the connector colour."]))

    def test_limitation_cannot_hide_factual_tail(self):
        self.assertFalse(explanation_limitation_complete(explanation_target_obligations(USER), [LIMIT + " But phased gating is broken."]))

    def test_semicolon_limitation_tail_cannot_supply_another_cause(self):
        text = "I cannot verify why phased gating causes stripe noise; phased gating definitely causes drift."
        self.assertFalse(explanation_limitation_complete(explanation_target_obligations(USER), [text]))

    def test_comma_concessive_limitation_tail_cannot_supply_another_cause(self):
        text = "I cannot verify why phased gating causes stripe noise, although phased gating always causes drift."
        self.assertFalse(explanation_limitation_complete(explanation_target_obligations(USER), [text]))

    def test_comma_consequence_limitation_tail_cannot_supply_a_fact(self):
        text = "I cannot verify why phased gating causes stripe noise, so phased gating is safe."
        self.assertFalse(explanation_limitation_complete(explanation_target_obligations(USER), [text]))

    def test_bounded_refusal_tail_does_not_create_factual_authority(self):
        text = "I cannot verify why phased gating causes stripe noise, so I won't guess."
        self.assertTrue(explanation_limitation_complete(explanation_target_obligations(USER), [text]))

    def test_typed_limitation_verdict_cannot_override_a_factual_tail(self):
        text = "I cannot verify why phased gating causes stripe noise; phased gating definitely causes drift."
        item = assessment(text, outcome="bounded_limitation", mechanism_quote="phased gating",
                          source_id=None, source_quote=None)
        self.assertIn("explanation_limitation_not_targeted", failures(text, [item]))

    def test_multiple_target_limitations_must_cover_every_request(self):
        values = explanation_target_obligations(USER + " Why does damping produce thermal drift?")
        self.assertFalse(explanation_limitation_complete(values, [LIMIT]))

    def test_es_inflection_does_not_break_transparent_limitation(self):
        request = "Why does the relay buzz when the supply changes?"
        limit = "I cannot verify why the relay buzzes from the available evidence."
        self.assertTrue(explanation_limitation_complete(explanation_target_obligations(request), [limit]))

    def test_verified_identity_can_anchor_bounded_reason_limitation(self):
        request = "Why was that preview discussed?"
        text = ["The preview is called Avery Morgan.", "I cannot verify why people discussed it."]
        self.assertTrue(explanation_limitation_complete(explanation_target_obligations(request), text))

    def test_identity_without_limitation_is_not_completion(self):
        self.assertFalse(explanation_limitation_complete(explanation_target_obligations(USER), ["The item is called Phased Gating."]))

    def test_unknown_cause_has_independent_literal_whole_body_proof(self):
        user = "Why did observers discuss Leto?"
        text = "Observers discussed Leto because Leto repaired the turbine."
        self.assertTrue(explanation_literal_target_complete(explanation_target_obligations(user), [text], packet(text)))

    def test_literal_proof_cannot_exempt_a_paired_mechanism_request(self):
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations(USER), [GOOD], packet()))

    def test_literal_unknown_cause_proof_requires_matching_requested_target(self):
        text = "Observers discussed Riva because Riva repaired the turbine."
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("Why did observers discuss Leto?"), [text], packet(text)))

    def test_literal_unknown_cause_proof_requires_the_whole_candidate_body_unit(self):
        text = "Observers discussed Leto because Leto repaired the turbine."
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("Why did observers discuss Leto?"), [text], packet("Observers discussed Leto.")))

    def test_hypothesis_is_not_literal_proof_of_the_requested_actual_event(self):
        text = "Observers might discuss Leto because Leto repaired the turbine."
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("Why did observers discuss Leto?"), [text], packet(text)))

    def test_title_does_not_supply_literal_unknown_cause_body_proof(self):
        text = "Observers discussed Leto because Leto repaired the turbine."
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("Why did observers discuss Leto?"), [text], packet("The turbine has four blades.", title=text)))

    def test_unread_source_does_not_supply_literal_unknown_cause_proof(self):
        text = "Observers discussed Leto because Leto repaired the turbine."
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("Why did observers discuss Leto?"), [text], packet(text, read_success=False)))

    def test_ambiguous_unknown_cause_request_cannot_use_literal_body_as_reference(self):
        text = "It occurs because the timing changed."
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("What causes that?"), [text], packet(text)))

    def test_extra_unretained_fact_defeats_literal_unknown_cause_proof(self):
        text = "Observers discussed Leto because Leto repaired the turbine."
        extra = "Leto works on every turbine."
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("Why did observers discuss Leto?"), [text, extra], packet(text)))

    def test_quoted_example_does_not_supply_literal_actual_event_proof(self):
        text = 'The example says "Observers discussed Leto because Leto repaired the turbine."'
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations("Why did observers discuss Leto?"), [text], packet(text)))


if __name__ == "__main__":
    unittest.main()
