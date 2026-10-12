"""Participant authority cannot depend on possessive wording or model labels."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.participant_relations import detect_participant_relations, participant_relation_witnessed


COMPLAINT = "You can query the inventory yourself. You should not need me to recite it."


def relation(text):
    values = detect_participant_relations(text)
    if len(values) != 1:
        raise AssertionError(repr(values))
    return values[0]


def supported(candidate, source, quote=None):
    return participant_relation_witnessed(relation(candidate), quote or source, source_text=source)


class ParticipantAuthorityTests(unittest.TestCase):
    def test_possessive_user_role(self):
        value = relation("You're my coach.")
        self.assertEqual((value["subject"], value["target"], value["predicate"]), ("user", "assistant", "coach"))

    def test_nonpossessive_beneficiary_same_role(self):
        self.assertTrue(supported("You're a coach for me.", "I am your coach."))

    def test_nonpossessive_source_same_role(self):
        self.assertTrue(supported("You're my coach.", "I am a coach for you."))

    def test_acting_like_role_has_its_own_relation(self):
        value = relation("You're acting like my manager.")
        self.assertEqual(value["relation_kind"], "role_acting")
        self.assertTrue(supported("You're acting like my manager.", "I am acting like your manager."))

    def test_acting_as_source_and_candidate(self):
        self.assertTrue(supported("You're acting as my navigator.", "I act as your navigator."))

    def test_adverb_does_not_hide_assistant_role(self):
        self.assertTrue(supported("I'm apparently your researcher now.", "You are my researcher."))

    def test_arbitrary_role_labels_are_data(self):
        for role in ("auditor", "navigator", "coordinator", "librarian", "analyst"):
            with self.subTest(role=role):
                self.assertTrue(supported(f"You're a {role} for me.", f"I am your {role}."))

    def test_indefinite_adjectival_user_role_is_detected(self):
        value = relation("You're a diligent little analyst.")
        self.assertEqual(value["predicate"], "diligent little analyst")
        self.assertEqual(value["subject"], "user")

    def test_indefinite_user_role_needs_actual_user_fact(self):
        self.assertFalse(supported("You're a diligent analyst.", COMPLAINT))
        self.assertTrue(supported("You're a diligent analyst.", "I am a diligent analyst."))

    def test_user_role_adjectives_are_not_self_authorised(self):
        self.assertFalse(supported("You're a diligent analyst.", "I am an analyst."))

    def test_embedded_role_premise_does_not_disappear(self):
        value = relation("I'll stop pretending you're a diligent analyst who needs help.")
        self.assertEqual(value["predicate"], "diligent analyst")
        self.assertFalse(participant_relation_witnessed(value, COMPLAINT, source_text=COMPLAINT))

    def test_role_direction_reversal_rejected(self):
        self.assertFalse(supported("You're my navigator.", "You are my navigator."))

    def test_assistant_role_supported_in_correct_direction(self):
        self.assertTrue(supported("I'm your navigator.", "You are my navigator."))

    def test_role_and_acting_role_not_interchangeable(self):
        self.assertFalse(supported("You're my navigator.", "I am acting like your navigator."))

    def test_role_aliases_are_not_evidence(self):
        self.assertFalse(supported("You're my advisor.", "I am your mentor."))

    def test_assistant_bare_self_mockery_outside_user_relation_scope(self):
        self.assertEqual(detect_participant_relations("I'm a mess."), ())

    def test_assistant_deictic_responsibility_acknowledgement_outside_role_scope(self):
        self.assertEqual(detect_participant_relations("I'm the one who should check it."), ())

    def test_simple_acknowledgement_does_not_get_new_obligations(self):
        text = "Fair criticism. I should check the inventory myself instead of asking you to explain it."
        self.assertEqual(detect_participant_relations(text), ())

    def test_appreciation_is_not_a_professional_relation(self):
        self.assertEqual(detect_participant_relations("I appreciate you. I see your point."), ())

    def test_expectation_preserves_directed_action(self):
        self.assertTrue(supported("You expect me to do your preparation.", "I expect you to do my preparation."))

    def test_expectation_direction_reversal_fails(self):
        self.assertFalse(supported("You expect me to do your preparation.", "You expect me to do your preparation."))

    def test_different_required_action_fails(self):
        self.assertFalse(supported("You need me to check your inventory.", "I need you to check my itinerary."))

    def test_asking_does_not_mean_forcing(self):
        self.assertFalse(supported("You force me to explain it.", "I ask you to explain it."))

    def test_recurrent_explanation_preserves_target_and_action(self):
        self.assertTrue(supported("You keep making me explain things to you.", "I keep making you explain things to me."))

    def test_recurrence_cannot_come_from_single_action(self):
        self.assertFalse(supported("You keep making me explain it.", "I make you explain it."))

    def test_frequency_cannot_be_strengthened(self):
        self.assertFalse(supported("You always brief me.", "I usually brief you."))

    def test_arbitrary_recurring_direct_target_activity(self):
        self.assertTrue(supported("You routinely brief me.", "I routinely brief you."))
        self.assertFalse(supported("You routinely brief me.", COMPLAINT))

    def test_recurring_literal_lecture_is_not_blacklisted(self):
        self.assertTrue(supported("You habitually lecture me.", "I habitually lecture you."))

    def test_transitive_teaching_supported(self):
        self.assertTrue(supported("I'm teaching you.", "You are teaching me."))

    def test_teaching_direction_reversal_fails(self):
        self.assertFalse(supported("I'm teaching you.", "I am teaching you."))

    def test_research_work_ownership_supported(self):
        self.assertTrue(supported("You routinely do my research.", "I routinely do your research."))

    def test_owning_different_work_is_not_supported(self):
        self.assertFalse(supported("You routinely do my research.", "I routinely do my research."))

    def test_conditional_complaint_transform_keeps_responsibility_direction(self):
        self.assertTrue(supported("Making you do my preparation would be ridiculous.", COMPLAINT))

    def test_natural_conditional_banter_keeps_responsibility_direction(self):
        self.assertTrue(supported("Fair criticism. Making you do my homework would be taking the piss.", COMPLAINT))

    def test_conditional_banter_not_authority_for_reversed_agency(self):
        self.assertFalse(supported("Making me do your preparation would be ridiculous.", COMPLAINT))

    def test_conditionals_do_not_license_actual_relationship_roles(self):
        self.assertFalse(supported("You're my advisor.", COMPLAINT))

    def test_hypothetical_role_still_needs_user_role_support(self):
        self.assertFalse(supported("You could be my advisor.", COMPLAINT))

    def test_nonliteral_label_cannot_override_asserted_history(self):
        value = relation("You routinely do my research.") | {"complaint_transform": True}
        self.assertFalse(participant_relation_witnessed(value, COMPLAINT, source_text=COMPLAINT))

    def test_nonliteral_label_cannot_override_role(self):
        value = relation("You're my advisor.") | {"complaint_transform": True}
        self.assertFalse(participant_relation_witnessed(value, COMPLAINT, source_text=COMPLAINT))

    def test_factual_tail_prevents_bounded_complaint_transform(self):
        value = relation("Making you do my preparation would be sensible because you always do it.")
        self.assertFalse(value.get("complaint_transform"))

    def test_role_after_conditional_banter_still_requires_support(self):
        text = "Making you do my preparation would be ridiculous. You're my advisor."
        values = detect_participant_relations(text)
        self.assertEqual(len(values), 2)
        self.assertTrue(participant_relation_witnessed(values[0], COMPLAINT, source_text=COMPLAINT))
        self.assertFalse(participant_relation_witnessed(values[1], COMPLAINT, source_text=COMPLAINT))

    def test_normative_complaint_cannot_supply_asserted_positive_need(self):
        self.assertFalse(supported("I need you to recite it.", COMPLAINT))

    def test_conditional_source_cannot_become_actual_role(self):
        self.assertFalse(supported("You're my advisor.", "If I am your advisor, ask me first.", "I am your advisor"))

    def test_conditional_source_cannot_become_actual_activity(self):
        self.assertFalse(supported("You routinely brief me.", "If I routinely brief you, call it support.", "I routinely brief you"))

    def test_questioned_source_cannot_become_actual_role(self):
        self.assertFalse(supported("You're my advisor.", "I am your advisor?", "I am your advisor"))

    def test_quoted_source_cannot_become_actual_role(self):
        self.assertFalse(supported("You're my advisor.", 'He said "I am your advisor".', "I am your advisor"))

    def test_epistemic_negative_wrapper_cannot_supply_a_role(self):
        self.assertFalse(supported("You're my advisor.", "I don't think I am your advisor.", "I am your advisor"))

    def test_unverified_wrapper_cannot_supply_a_role(self):
        self.assertFalse(supported("You're my analyst.", "I cannot confirm I am your analyst.", "I am your analyst"))

    def test_denial_wrapper_cannot_supply_a_role(self):
        self.assertFalse(supported("You're my advisor.", "It is not true that I am your advisor.", "I am your advisor"))

    def test_explicit_denial_cannot_supply_a_role(self):
        self.assertFalse(supported("You're my advisor.", "I deny that I am your advisor.", "I am your advisor"))

    def test_unasserted_candidate_scope_does_not_erase_later_role(self):
        values = detect_participant_relations("I cannot confirm you're my analyst, but you're my coach.")
        self.assertEqual([value["mode"] for value in values], ["unasserted", "asserted"])

    def test_independent_user_contrast_can_supply_its_actual_role(self):
        self.assertTrue(supported("You're my coach.", "I cannot confirm I am your analyst, but I am your coach."))

    def test_conditional_user_antecedent_is_not_erased_by_contrast(self):
        self.assertFalse(supported("You're my coach.", "If I am your analyst but I am your coach, ask first.", "I am your coach"))

    def test_later_future_contrast_does_not_reclassify_prior_actual_role(self):
        self.assertTrue(supported("You're my coach.", "I am your coach, but I will be your navigator next month."))

    def test_negated_role_cannot_support_positive_role(self):
        self.assertFalse(supported("You're my advisor.", "I am not your advisor."))

    def test_actual_negative_role_can_be_preserved(self):
        self.assertTrue(supported("You're not my advisor.", "I am not your advisor."))

    def test_future_plan_cannot_become_current_role(self):
        self.assertFalse(supported("You're my advisor.", "I will be your advisor."))

    def test_existing_role_cannot_invent_future_commitment(self):
        self.assertFalse(supported("You will be my advisor.", "I am your advisor."))

    def test_false_quote_is_not_authority(self):
        self.assertFalse(supported("You're my advisor.", COMPLAINT, "I am your advisor."))

    def test_candidate_prose_is_not_its_user_witness(self):
        candidate = "You're my advisor."
        self.assertFalse(participant_relation_witnessed(relation(candidate), candidate, source_text=COMPLAINT))

    def test_unrelated_question_does_not_erase_a_real_prior_assertion(self):
        self.assertTrue(supported("You're my advisor.", "I am your advisor. What time is it?"))

    def test_apostrophe_morphology_preserves_identity(self):
        self.assertTrue(supported("You’re my advisor.", "I’m your advisor."))

    def test_helper_requires_explicit_known_perspective(self):
        with self.assertRaises(ValueError):
            detect_participant_relations("I'm your advisor.", speaker="system")


if __name__ == "__main__":
    unittest.main()
