"""Neutral purpose/necessity targets share the strict public explanation boundary."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research.public_explanation_targets import (
    explanation_target_obligations, explanation_target_failures, explanation_target_schema,
    explanation_target_instruction, explanation_limitation_complete, explanation_literal_target_complete,
    purpose_candidate_bound, purpose_claim_witness_issue,
)

USER = "Why does protocol Orion need exchange Relay?"
BODY = "Exchange Relay allows protocol Orion to establish shared state before normal data transfer."
GOOD = "Protocol Orion needs exchange Relay because it establishes shared state before normal transfer."
LET = "Exchange Relay lets protocol Orion establish shared state before normal transfer."


def packet(body=BODY, **changes):
    source = {"source_id": "S1", "title": "Protocol operations guide",
              "url": "https://docs.vendor.example/operations", "read_success": True,
              "accepted_as_evidence": True, "relevance_status": "accepted", "content_excerpt": body}
    source.update(changes)
    return {"research_kind": "public_factual", "sources": [source]}


def assessment(text=GOOD, source=BODY, **changes):
    value = {"index": 1, "outcome": "factual_explanation", "mechanism_bound": True,
             "effect_bound": True, "relationship_answered": True,
             "mechanism_quote": "Protocol Orion" if "Protocol Orion" in text else "protocol Orion",
             "effect_quote": "exchange Relay" if "exchange Relay" in text else "Exchange Relay",
             "answer_quote": text, "source_id": "S1", "source_quote": source}
    value.update(changes)
    return value


def failures(text=GOOD, body=BODY, user=USER, changes=None, sentences=None, evidence=None, raw=None):
    item = assessment(text, body, **(changes or {}))
    return explanation_target_failures(explanation_target_obligations(user),
                                       [item] if raw is None else raw,
                                       sentences or [text], evidence or packet(body))


class PurposeTargetTests(unittest.TestCase):
    def test_need_request_has_two_user_owned_roles(self):
        item = explanation_target_obligations(USER)[0]
        self.assertEqual((item["mechanism"], item["effect"]), ("protocol Orion", "exchange Relay"))
        self.assertEqual(item["relation_type"], "purpose_or_necessity")

    def test_needs_inflection_projects_same_roles(self):
        item = explanation_target_obligations("Explain why protocol Orion needs exchange Relay.")[0]
        self.assertEqual((item["mechanism"], item["effect"]), ("protocol Orion", "exchange Relay"))

    def test_required_stage_projects_subject_and_requirement(self):
        item = explanation_target_obligations("Why does component Vector require stage Cedar?")[0]
        self.assertEqual((item["mechanism"], item["effect"]), ("component Vector", "stage Cedar"))

    def test_reverse_necessary_request_keeps_beneficiary_direction(self):
        item = explanation_target_obligations("Why is exchange Relay necessary for protocol Orion?")[0]
        self.assertEqual((item["mechanism"], item["effect"]), ("protocol Orion", "exchange Relay"))

    def test_required_by_reverse_request_keeps_direction(self):
        item = explanation_target_obligations("Why is stage Cedar required by component Vector?")[0]
        self.assertEqual((item["mechanism"], item["effect"]), ("component Vector", "stage Cedar"))

    def test_explicit_why_reverse_form_projects_purpose(self):
        item = explanation_target_obligations("Explain why exchange Relay is needed for protocol Orion.")[0]
        self.assertEqual(item["relation_type"], "purpose_or_necessity")

    def test_request_offsets_preserve_exact_user_span(self):
        user = "Anyway, " + USER
        item = explanation_target_obligations(user)[0]
        self.assertEqual(user[item["request_start"]:item["request_end"]], USER)

    def test_causal_request_remains_causal(self):
        item = explanation_target_obligations("Why does feature Aspen cause symptom Birch?")[0]
        self.assertEqual(item["relation_type"], "causal_effect")
        self.assertEqual((item["mechanism"], item["effect"]), ("feature Aspen", "symptom Birch"))

    def test_condition_request_remains_condition(self):
        item = explanation_target_obligations("Why does symptom Birch occur when feature Aspen is on?")[0]
        self.assertEqual(item["relation_type"], "condition_effect")

    def test_later_need_word_cannot_replace_main_causal_relation(self):
        item = explanation_target_obligations("Why does feature Aspen cause component Birch to need stage Cedar?")[0]
        self.assertEqual(item["relation_type"], "causal_effect")
        self.assertEqual(item["mechanism"], "feature Aspen")

    def test_later_need_word_cannot_replace_main_condition(self):
        item = explanation_target_obligations("Why does symptom Birch appear when component Cedar needs stage Delta?")[0]
        self.assertEqual(item["relation_type"], "condition_effect")

    def test_unknown_cause_request_does_not_become_purpose(self):
        item = explanation_target_obligations("What causes component Vector to need stage Cedar?")[0]
        self.assertEqual(item["relation_type"], "causal_effect")
        self.assertIsNone(item["mechanism"])

    def test_no_named_subject_is_fabricated(self):
        item = explanation_target_obligations("Why is it needed?")[0]
        self.assertNotEqual(item["relation_type"], "purpose_or_necessity")

    def test_schema_keeps_ten_strict_fields_without_model_relation_type(self):
        schema = explanation_target_schema({"properties": {}, "required": []})
        item = schema["properties"]["explanation_target_assessments"]["items"]
        self.assertEqual(len(item["required"]), 10)
        self.assertNotIn("relation_type", item["properties"])
        self.assertFalse(item["additionalProperties"])

    def test_schema_does_not_mutate_base(self):
        base = {"properties": {}, "required": []}
        original = copy.deepcopy(base)
        explanation_target_schema(base)
        self.assertEqual(base, original)

    def test_instruction_explicitly_defines_legacy_role_names_for_purpose(self):
        instruction = explanation_target_instruction(explanation_target_obligations(USER), packet())
        self.assertIn("subject/beneficiary", instruction)
        self.assertIn("purpose_or_necessity", instruction)
        self.assertIn("S1", instruction)
        self.assertNotIn(BODY, instruction)

    def test_need_because_body_allows_is_valid(self):
        self.assertEqual(failures(), [])

    def test_lets_form_without_literal_need_is_valid(self):
        self.assertEqual(failures(LET), [])

    def test_allows_form_without_literal_need_is_valid(self):
        self.assertEqual(failures(BODY), [])

    def test_uses_to_function_is_valid(self):
        text = "Protocol Orion uses exchange Relay to establish shared state before normal transfer."
        self.assertEqual(failures(text), [])

    def test_uses_in_order_to_function_is_valid(self):
        text = "Protocol Orion uses exchange Relay in order to establish shared state before normal transfer."
        self.assertEqual(failures(text), [])

    def test_required_so_that_form_is_valid(self):
        text = "Exchange Relay is required so that protocol Orion can establish shared state before normal transfer."
        self.assertEqual(failures(text), [])

    def test_required_so_form_is_valid(self):
        text = "Exchange Relay is required so protocol Orion can establish shared state before normal transfer."
        self.assertEqual(failures(text), [])

    def test_establishes_for_subject_form_is_valid(self):
        text = "Exchange Relay establishes shared state for protocol Orion."
        self.assertEqual(failures(text), [])

    def test_ensures_form_has_actual_function_witness(self):
        text = "Exchange Relay ensures that protocol Orion establishes shared state before normal transfer."
        self.assertEqual(failures(text, text), [])

    def test_enable_form_has_matching_function(self):
        text = "Exchange Relay enables protocol Orion to establish shared state before normal transfer."
        self.assertEqual(failures(text), [])

    def test_permit_form_has_matching_function(self):
        text = "Exchange Relay permits protocol Orion to establish shared state before normal transfer."
        self.assertEqual(failures(text), [])

    def test_reverse_necessary_question_accepts_same_purpose_answer(self):
        self.assertEqual(failures(LET, user="Why is exchange Relay necessary for protocol Orion?"), [])

    def test_unrelated_domain_requires_stage_accepts_faithful_function(self):
        user = "Why does component Vector require stage Cedar?"
        body = "Stage Cedar enables component Vector to identify valid records before indexing."
        text = "Component Vector uses stage Cedar to identify valid records before indexing."
        item = assessment(text, body, mechanism_quote="Component Vector", effect_quote="stage Cedar")
        self.assertEqual(explanation_target_failures(explanation_target_obligations(user), [item], [text], packet(body)), [])

    def test_optional_advice_does_not_replace_valid_purpose(self):
        advice = "Try checking the configured exchange settings."
        self.assertEqual(failures(LET, sentences=[LET, advice]), [])

    def test_bare_use_is_not_explanation(self):
        text = "Protocol Orion uses exchange Relay."
        self.assertIn("purpose_candidate_relationship_unbound", failures(text))

    def test_message_count_is_not_explanation(self):
        text = "Exchange Relay consists of three messages."
        self.assertTrue(failures(text, changes={"mechanism_quote": "Exchange Relay"}))

    def test_reliability_property_is_not_explanation(self):
        text = "Protocol Orion is reliable."
        self.assertTrue(failures(text, changes={"effect_quote": "Protocol Orion"}))

    def test_requirement_existence_is_not_explanation(self):
        text = "Exchange Relay exists."
        self.assertTrue(failures(text, changes={"mechanism_quote": "Exchange Relay"}))

    def test_advice_only_is_not_explanation(self):
        text = "Try restarting component Cedar."
        self.assertTrue(failures(text, changes={"mechanism_quote": "component Cedar", "effect_quote": "component Cedar"}))

    def test_unrelated_cause_cannot_rescue_both_name_mentions(self):
        text = "Protocol Orion uses exchange Relay. The console stalls because its queue is full."
        self.assertIn("purpose_candidate_relationship_unbound", failures(text))

    def test_named_subject_with_requirement_missing_is_incomplete(self):
        text = "Protocol Orion establishes shared state before normal transfer."
        self.assertTrue(failures(text, changes={"effect_quote": "shared state"}))

    def test_named_requirement_with_subject_missing_is_incomplete(self):
        text = "Exchange Relay establishes shared state before normal transfer."
        self.assertTrue(failures(text, changes={"mechanism_quote": "shared state"}))

    def test_wrong_subject_cannot_borrow_requirement(self):
        text = "Exchange Relay allows protocol Cedar to establish shared state before normal transfer."
        self.assertTrue(failures(text, changes={"mechanism_quote": "protocol Cedar"}))

    def test_wrong_requirement_cannot_borrow_subject(self):
        text = "Exchange Delta allows protocol Orion to establish shared state before normal transfer."
        self.assertTrue(failures(text, changes={"effect_quote": "Exchange Delta"}))

    def test_reverse_beneficiary_candidate_fails(self):
        text = "Protocol Orion allows exchange Relay to establish shared state before normal transfer."
        self.assertIn("purpose_candidate_relationship_unbound", failures(text))

    def test_reverse_beneficiary_source_fails(self):
        body = "Protocol Orion allows exchange Relay to establish shared state before normal transfer."
        self.assertIn("purpose_source_relationship_unbound", failures(body=body))

    def test_source_both_mentions_without_function_fails(self):
        body = "Protocol Orion uses exchange Relay. Exchange Relay has three messages."
        self.assertIn("purpose_source_relationship_unbound", failures(body=body))

    def test_source_unrelated_benefit_cannot_authorize_candidate_function(self):
        body = "Exchange Relay allows protocol Orion to colour exported labels."
        self.assertIn("purpose_function_witness_mismatch", failures(body=body))

    def test_candidate_different_goal_fails(self):
        text = "Exchange Relay lets protocol Orion colour exported labels."
        self.assertIn("purpose_function_witness_mismatch", failures(text))

    def test_temporal_function_direction_is_preserved(self):
        text = "Exchange Relay lets protocol Orion establish shared state after normal transfer."
        self.assertIn("purpose_function_witness_mismatch", failures(text))

    def test_positive_source_cannot_support_negative_requirement(self):
        text = "Protocol Orion does not need exchange Relay because it establishes shared state before normal transfer."
        self.assertIn("purpose_relationship_polarity_mismatch", failures(text))

    def test_negative_source_cannot_support_positive_requirement(self):
        body = "Exchange Relay does not allow protocol Orion to establish shared state before normal data transfer."
        self.assertIn("purpose_relationship_polarity_mismatch", failures(body=body))

    def test_matching_bounded_denial_keeps_polarity(self):
        text = "Protocol Orion does not need exchange Relay because it establishes shared state before normal transfer."
        self.assertEqual(failures(text, text), [])

    def test_source_negative_enabled_function_cannot_support_positive_function(self):
        body = "Exchange Relay allows protocol Orion to not establish shared state before normal transfer."
        self.assertIn("purpose_function_polarity_mismatch", failures(LET, body))

    def test_candidate_negative_enabled_function_cannot_borrow_positive_function(self):
        text = "Exchange Relay lets protocol Orion not establish shared state before normal transfer."
        self.assertIn("purpose_function_polarity_mismatch", failures(text))

    def test_source_ensures_negative_function_cannot_support_positive_function(self):
        body = "Exchange Relay ensures that protocol Orion does not establish shared state before normal transfer."
        self.assertIn("purpose_function_polarity_mismatch", failures(LET, body))

    def test_candidate_ensures_negative_function_cannot_borrow_positive_function(self):
        text = "Exchange Relay ensures that protocol Orion does not establish shared state before normal transfer."
        self.assertIn("purpose_function_polarity_mismatch", failures(text))

    def test_source_no_longer_allows_is_relation_negation(self):
        body = "Exchange Relay no longer allows protocol Orion to establish shared state before normal transfer."
        self.assertIn("purpose_relationship_polarity_mismatch", failures(LET, body))

    def test_candidate_no_longer_lets_is_relation_negation(self):
        text = "Exchange Relay no longer lets protocol Orion establish shared state before normal transfer."
        self.assertIn("purpose_relationship_polarity_mismatch", failures(text))

    def test_source_no_longer_in_function_does_not_negate_outer_relation(self):
        body = "Exchange Relay allows protocol Orion to no longer establish shared state before normal transfer."
        self.assertIn("purpose_function_polarity_mismatch", failures(LET, body))

    def test_candidate_no_longer_in_function_does_not_negate_outer_relation(self):
        text = "Exchange Relay lets protocol Orion no longer establish shared state before normal transfer."
        self.assertIn("purpose_function_polarity_mismatch", failures(text))

    def test_matching_negative_function_remains_supportable(self):
        text = "Exchange Relay lets protocol Orion not establish shared state before normal transfer."
        self.assertEqual(failures(text, text), [])

    def test_matching_no_longer_relation_remains_supportable(self):
        text = "Exchange Relay no longer lets protocol Orion establish shared state before normal transfer."
        self.assertEqual(failures(text, text), [])

    def test_double_negation_does_not_collapse_into_positive_function(self):
        text = "Exchange Relay does not let protocol Orion not establish shared state before normal transfer."
        self.assertIn("purpose_relationship_polarity_mismatch", failures(text))

    def test_not_only_does_not_turn_source_function_negative(self):
        body = "Exchange Relay allows protocol Orion to not only establish shared state before normal transfer."
        self.assertEqual(failures(LET, body), [])

    def test_title_only_witness_is_not_body(self):
        self.assertTrue(failures(evidence=packet("The console has two ports.", title=BODY)))

    def test_unread_page_is_not_body(self):
        self.assertIn("missing_explanation_body_witness", failures(evidence=packet(read_success=False)))

    def test_rejected_page_is_not_body(self):
        self.assertIn("missing_explanation_body_witness", failures(evidence=packet(accepted_as_evidence=False)))

    def test_candidate_cannot_become_body(self):
        self.assertTrue(failures(evidence=packet("The system has a status screen.")))

    def test_wrong_source_id_fails(self):
        self.assertIn("missing_explanation_body_witness", failures(changes={"source_id": "S9"}))

    def test_nonliteral_body_quote_fails(self):
        self.assertIn("missing_explanation_body_witness", failures(changes={"source_quote": BODY.replace("normal", "rapid")}))

    def test_missing_target_assessments_fail_closed(self):
        result = explanation_target_failures(explanation_target_obligations(USER), None, [GOOD], packet())
        self.assertEqual(result, ["missing_explanation_target_assessments"])

    def test_incomplete_target_assessments_fail_closed(self):
        self.assertEqual(failures(raw=[]), ["incomplete_explanation_target_assessments"])

    def test_malformed_target_assessments_fail_closed(self):
        value = assessment()
        value["relationship_answered"] = "true"
        self.assertEqual(failures(raw=[value]), ["invalid_explanation_target_assessments"])

    def test_extra_model_relation_field_is_rejected(self):
        value = assessment()
        value["relation_type"] = "purpose_or_necessity"
        self.assertEqual(failures(raw=[value]), ["invalid_explanation_target_assessments"])

    def test_positive_flags_cannot_override_missing_function(self):
        text = "Protocol Orion uses exchange Relay."
        self.assertTrue(failures(text))

    def test_clear_subject_pronoun_binds_current_request(self):
        text = "It uses exchange Relay to establish shared state before normal transfer."
        self.assertEqual(failures(text, changes={"mechanism_quote": "It"}), [])

    def test_clear_requirement_pronoun_binds_current_request(self):
        text = "It lets protocol Orion establish shared state before normal transfer."
        self.assertEqual(failures(text, changes={"effect_quote": "It"}), [])

    def test_clear_prior_antecedent_remains_in_subset(self):
        first = "Exchange Relay controls shared state."
        second = "It lets protocol Orion establish shared state before normal transfer."
        self.assertEqual(failures(second, changes={"effect_quote": "It"}, sentences=[first, second]), [])

    def test_ambiguous_prior_antecedent_fails(self):
        first = "Protocol Orion and exchange Relay are available."
        second = "It lets protocol Orion establish shared state before normal transfer."
        self.assertTrue(failures(second, changes={"effect_quote": "It"}, sentences=[first, second]))

    def test_double_pronoun_cannot_establish_roles(self):
        text = "It lets that establish shared state before normal transfer."
        self.assertTrue(failures(text, changes={"mechanism_quote": "that", "effect_quote": "It"}))

    def test_deleted_antecedent_with_multiple_requests_fails(self):
        user = USER + " Why does protocol Cedar need exchange Delta?"
        text = "It lets protocol Orion establish shared state before normal transfer."
        second = assessment(index=2)
        result = explanation_target_failures(explanation_target_obligations(user),
                     [assessment(text, effect_quote="It"), second], [text], packet())
        self.assertTrue(result)

    def test_purpose_limitation_can_name_both_targets_without_need(self):
        text = "I cannot verify why protocol Orion uses exchange Relay from the available evidence."
        self.assertTrue(explanation_limitation_complete(explanation_target_obligations(USER), [text]))

    def test_unrelated_limitation_cannot_complete_purpose(self):
        self.assertFalse(explanation_limitation_complete(explanation_target_obligations(USER),
                                                        ["I cannot verify the label colour."]))

    def test_literal_body_copy_does_not_bypass_paired_target_protocol(self):
        self.assertFalse(explanation_literal_target_complete(explanation_target_obligations(USER), [BODY], packet()))

    def test_candidate_projection_is_not_evidence(self):
        self.assertTrue(purpose_candidate_bound(explanation_target_obligations(USER)[0], LET))
        self.assertTrue(purpose_claim_witness_issue(explanation_target_obligations(USER)[0], LET,
                                                  "Protocol Orion and exchange Relay are listed."))

    def test_advice_claim_does_not_bind_purpose(self):
        text = "Try restarting the console because its cache is stale."
        self.assertFalse(purpose_candidate_bound(explanation_target_obligations(USER)[0], text))

    def test_generic_causal_branch_does_not_accept_purpose_markers(self):
        user = "Why does feature Aspen cause symptom Birch?"
        text = "Feature Aspen allows symptom Birch to establish shared state."
        item = assessment(text, text, mechanism_quote="Feature Aspen", effect_quote="symptom Birch")
        self.assertTrue(explanation_target_failures(explanation_target_obligations(user), [item], [text], packet(text)))


if __name__ == "__main__":
    unittest.main()
