"""Personal history requires an actual USER proposition, not plausible banter."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.user_history_obligations import (
    build_user_history_packet, detect_user_history, user_history_witnessed,
    validate_user_history_assessments,
)


def packet(candidate, user):
    return build_user_history_packet(candidate, {"current_user": user})


def verdict(value, quote, *, source_id="current_user", supported=True):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": supported,
         "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class UserHistoryAuthorityTests(unittest.TestCase):
    def assert_unproven(self, candidate, user):
        value = packet(candidate, user)
        self.assertTrue(value["obligations"], candidate)
        self.assertTrue(validate_user_history_assessments(verdict(value, user), value), candidate)

    def assert_witnessed(self, candidate, user):
        value = packet(candidate, user)
        self.assertFalse(value["obligations"], candidate)
        self.assertTrue(value["core_witnessed"], candidate)

    def test_specific_elapsed_duration_is_detected(self):
        value = detect_user_history("You avoided the index for four weeks.")[0]
        self.assertEqual(value["duration"], (("for", "", "4", "week"),))

    def test_supplied_negative_duration_can_be_mirrored(self):
        self.assert_witnessed("You have not read in three weeks.", "I have not read in three weeks.")

    def test_number_word_and_numeral_share_quantity(self):
        self.assert_witnessed("You have not read in 3 weeks.", "I have not read in three weeks.")

    def test_specific_cardinal_duration_above_twelve_is_detected(self):
        self.assert_unproven("You used a stylus for sixteen days.", "My scanner arrived.")

    def test_teen_cardinal_and_numeral_share_quantity(self):
        self.assert_witnessed("You used a stylus for sixteen days.", "I used a stylus for 16 days.")

    def test_hyphenated_cardinal_and_numeral_share_quantity(self):
        self.assert_witnessed("You used a stylus for twenty-one days.", "I used a stylus for 21 days.")

    def test_spaced_cardinal_and_numeral_share_quantity(self):
        self.assert_witnessed("You used a stylus for twenty one days.", "I used a stylus for 21 days.")

    def test_hundreds_cardinal_and_numeral_share_quantity(self):
        self.assert_witnessed("You used a stylus for one hundred and twenty-one days.", "I used a stylus for 121 days.")

    def test_thousands_cardinal_and_numeral_share_quantity(self):
        self.assert_witnessed("You used a stylus for one thousand and sixteen days.", "I used a stylus for 1016 days.")

    def test_cardinal_equivalence_does_not_erase_approximation(self):
        self.assert_unproven("You used a stylus for sixteen days.", "I used a stylus for nearly sixteen days.")

    def test_typographic_apostrophe_does_not_change_history(self):
        self.assert_witnessed("You’ve been shelving maps for two days.", "I've been shelving maps for two days.")

    def test_morphological_activity_keeps_its_identity(self):
        self.assert_witnessed("You used a stylus for four days.", "I was using a stylus for four days.")

    def test_new_activity_cannot_come_from_learning_that_activity(self):
        self.assert_unproven("You used a stylus for four days.", "I was learning to use a stylus for four days.")

    def test_interruption_does_not_supply_elapsed_months(self):
        self.assert_unproven("You ignored the journal for four months.", "I got back into reading the journal.")

    def test_open_duration_is_not_supplied_by_reentry(self):
        self.assert_unproven("You've been holding out for a while.", "The journal is still my favourite.")

    def test_preference_continuity_does_not_supply_abandonment(self):
        self.assert_unproven("You have not abandoned the journal yet.", "The journal is still my favourite.")

    def test_preference_continuity_can_be_echoed(self):
        value = packet("The journal is still your favourite.", "The journal is still my favourite.")
        self.assertFalse(value["obligations"])

    def test_ordinary_arrival_is_not_history_acquisition(self):
        self.assertFalse(packet("Your scanner finally arrived.", "My scanner finally arrived.")["obligations"])

    def test_arrival_does_not_supply_interim_equipment(self):
        self.assert_unproven("You used a stylus for four days.", "My scanner finally arrived.")

    def test_imperative_banter_still_has_an_interim_premise(self):
        self.assert_unproven("Stop pretending to be efficient while using a stylus for four days.", "My scanner arrived.")

    def test_interim_equipment_is_allowed_when_user_supplied_it(self):
        self.assert_witnessed("Stop pretending to be efficient while using a stylus for four days.",
                              "I was using a stylus for four days.")

    def test_implicit_return_duration_is_a_personal_obligation(self):
        self.assert_unproven("Welcome back after five weeks of avoiding the index.", "I got back into indexing.")

    def test_rhetorical_question_tag_does_not_hide_history(self):
        self.assert_unproven("Back after months of avoiding the index, then?", "I got back into indexing.")

    def test_bare_interruption_can_follow_explicit_reentry(self):
        self.assert_witnessed("You took a break.", "I got back into indexing.")

    def test_matching_interruption_activity_can_follow_reentry(self):
        self.assert_witnessed("You took a break from indexing.", "I got back into indexing.")

    def test_reentry_does_not_supply_a_different_interruption(self):
        self.assert_unproven("You took a break from weaving.", "I got back into indexing.")

    def test_reentry_does_not_establish_neglect(self):
        self.assert_unproven("You have been neglecting the index.", "I got back into indexing.")

    def test_habitual_activity_needs_actual_history(self):
        self.assert_unproven("You always misplace the cards.", "The cards are on the cabinet.")

    def test_matching_habitual_activity_is_supported(self):
        self.assert_witnessed("You usually shelve the maps.", "I usually shelve the maps.")

    def test_frequency_cannot_be_upgraded(self):
        self.assert_unproven("You always shelve the maps.", "I sometimes shelve the maps.")

    def test_one_action_is_not_recurrence(self):
        self.assert_unproven("You keep shelving the maps.", "I shelved the maps.")

    def test_present_location_is_not_previous_location(self):
        self.assert_unproven("Your notebook was on the rack before.", "My notebook is on the desk.")

    def test_supplied_prior_owned_location_is_supported(self):
        self.assert_witnessed("Your notebook was on the rack before.", "My notebook was on the rack before.")

    def test_prior_location_cannot_change_the_owned_object(self):
        self.assert_unproven("Your bag was on the rack before.", "My notebook was on the rack before.")

    def test_prior_possession_is_not_the_same_as_location(self):
        self.assert_unproven("Your scanner had toner before.", "My scanner was near toner before.")

    def test_usual_item_location_does_not_follow_present_location(self):
        self.assert_unproven("It moved from its usual hiding place.", "My notebook is on the rack.")

    def test_user_can_supply_matching_usual_place(self):
        self.assert_witnessed("It moved from its usual hiding place.", "My notebook has its usual hiding place.")

    def test_duration_quantity_cannot_change(self):
        self.assert_unproven("You avoided the index for five weeks.", "I avoided the index for four weeks.")

    def test_duration_unit_cannot_change(self):
        self.assert_unproven("You avoided the index for four months.", "I avoided the index for four weeks.")

    def test_unspecified_duration_is_not_exact_quantity(self):
        self.assert_unproven("You avoided the index for four weeks.", "I avoided the index for weeks.")

    def test_duration_qualification_cannot_be_erased(self):
        self.assert_unproven("You avoided the index for four weeks.", "I avoided the index for nearly four weeks.")

    def test_duration_relation_cannot_change(self):
        self.assert_unproven("You avoided the index after four weeks.", "I avoided the index for four weeks.")

    def test_temporal_ordering_cannot_reverse(self):
        self.assert_unproven("Your notebook was on the rack after work.", "My notebook was on the rack before work.")

    def test_negative_history_does_not_prove_positive_history(self):
        self.assert_unproven("You have abandoned the journal.", "I have not abandoned the journal.")

    def test_positive_history_does_not_prove_negative_history(self):
        self.assert_unproven("You have not abandoned the journal.", "I have abandoned the journal.")

    def test_questioned_user_quote_does_not_supply_history(self):
        self.assert_unproven("You have ignored the index.", "Have I ignored the index?")

    def test_conditional_user_quote_does_not_supply_history(self):
        self.assert_unproven("You have ignored the index.", "If I have ignored the index, tell me.")

    def test_quoted_user_history_is_not_asserted(self):
        self.assert_unproven("You have ignored the index.", 'The note says "I have ignored the index".')

    def test_future_user_statement_does_not_supply_completed_history(self):
        self.assert_unproven("You have ignored the index.", "I will say I have ignored the index.")

    def test_hypothetical_candidate_does_not_assert_history(self):
        self.assertFalse(packet("If you have ignored the index, you can resume it.", "I like the index.")["obligations"])

    def test_hedged_actual_history_still_needs_a_witness(self):
        self.assert_unproven("You might have ignored the index for four weeks.", "I got back into indexing.")

    def test_refusal_to_infer_history_is_not_a_history_assertion(self):
        self.assertFalse(packet("I don't know whether you have ignored the index for four weeks.", "I like the index.")["obligations"])

    def test_metaphorical_entity_has_no_personal_history_premise(self):
        self.assertFalse(packet("The atlas gods have awakened.", "I like the atlas.")["obligations"])

    def test_emotional_metaphor_has_no_temporal_biography(self):
        self.assertFalse(packet("That chapter murdered you emotionally.", "The chapter was intense.")["obligations"])

    def test_absurd_self_personification_is_not_user_history(self):
        self.assertFalse(packet("I've been a furious toaster for forty years.", "I'm bored.")["obligations"])

    def test_assistant_source_label_cannot_be_used(self):
        value = build_user_history_packet("You avoided the index for four weeks.",
                                         {"current_user": "I resumed indexing.",
                                          "assistant": "I avoided the index for four weeks."})
        self.assertNotIn("assistant", value["sources"])
        state = verdict(value, "I avoided the index for four weeks.", source_id="assistant")
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_current_explicit_negative_prevents_stale_core_auto_witness(self):
        value = build_user_history_packet("You usually shelve the maps.",
                                         {"current_user": "I do not usually shelve the maps.",
                                          "prior_user_1": "I usually shelve the maps."})
        self.assertTrue(value["obligations"])
        self.assertFalse(value["core_witnessed"])

    def test_prior_positive_quote_cannot_override_current_explicit_negative(self):
        value = build_user_history_packet("You usually shelve the maps.",
                                         {"current_user": "I do not usually shelve the maps.",
                                          "prior_user_1": "I usually shelve the maps."})
        state = verdict(value, "I usually shelve the maps.", source_id="prior_user_1")
        failures = validate_user_history_assessments(state, value)
        self.assertTrue(any("current USER" in item for item in failures))

    def test_latest_asserted_repeated_positive_keeps_its_actual_position(self):
        user = "I usually shelve the maps. I do not usually shelve the maps. I usually shelve the maps."
        value = packet("You usually shelve the maps.", user)
        self.assertFalse(value["obligations"])
        self.assertTrue(value["core_witnessed"])

    def test_later_quoted_repeat_does_not_override_current_negative(self):
        current = 'I do not usually shelve the maps. A note says "I usually shelve the maps."'
        value = build_user_history_packet("You usually shelve the maps.",
                                         {"current_user": current,
                                          "prior_user_1": "I usually shelve the maps."})
        self.assertTrue(value["obligations"])
        state = verdict(value, "I usually shelve the maps.", source_id="prior_user_1")
        self.assertTrue(any("current USER" in item for item in validate_user_history_assessments(state, value)))

    def test_global_positive_cannot_erase_missing_scoped_assessment(self):
        value = packet("You avoided the index for four weeks.", "I resumed indexing.")
        self.assertTrue(validate_user_history_assessments({"supported": True}, value))

    def test_model_none_label_cannot_erase_a_core_obligation(self):
        value = packet("You avoided the index for four weeks.", "I resumed indexing.")
        state = verdict(value, "I resumed indexing.")
        state["history_assessments"][0]["kind"] = "none"
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_negative_assessment_overrides_positive_global(self):
        value = packet("You avoided the index for four weeks.", "I resumed indexing.")
        self.assertTrue(validate_user_history_assessments(verdict(value, "I resumed indexing.", supported=False), value))

    def test_forged_user_quote_is_rejected(self):
        value = packet("You avoided the index for four weeks.", "I resumed indexing.")
        self.assertTrue(validate_user_history_assessments(verdict(value, "I avoided the index for four weeks."), value))

    def test_incomplete_multiple_obligations_fail_closed(self):
        value = packet("You avoided the index for four weeks. You always leave the cards there.", "I resumed indexing.")
        self.assertEqual(len(value["obligations"]), 2)
        state = verdict(value, "I resumed indexing.")
        state["history_assessments"].pop()
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_duplicate_assessment_indexes_fail_closed(self):
        value = packet("You avoided the index for four weeks. You always leave the cards there.", "I resumed indexing.")
        state = verdict(value, "I resumed indexing.")
        state["history_assessments"][1]["index"] = 1
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_nonboolean_support_is_malformed(self):
        value = packet("You avoided the index for four weeks.", "I resumed indexing.")
        self.assertTrue(validate_user_history_assessments(verdict(value, "I resumed indexing.", supported="yes"), value))

    def test_quote_cannot_omit_a_conditional_scope(self):
        item = detect_user_history("You have ignored the index.")[0]
        self.assertFalse(user_history_witnessed(item, "I have ignored the index", source_text="If I have ignored the index, tell me."))

    def test_curly_double_quotes_are_not_a_user_history_assertion(self):
        self.assert_unproven("You used to read Rowan for three weeks.", "“I used to read Rowan for three weeks.”")

    def test_quote_scope_survives_multiple_sentences(self):
        self.assert_unproven("You used to read Rowan for three weeks.", 'A note says "First, a warning. I used to read Rowan for three weeks."')

    def test_other_conjuncts_cannot_supply_the_activity_object(self):
        self.assert_unproven("You had ignored Vale for three weeks.",
                             "I had ignored Rowan and discussed Vale for three weeks.")

    def test_other_frequency_clause_cannot_supply_the_object(self):
        self.assert_unproven("You always read Vale.", "I always read Rowan and sometimes skimmed Vale.")

    def test_argument_direction_cannot_be_reversed(self):
        self.assert_unproven("You used to lend Mira to your tablet.", "I used to lend my tablet to Mira.")

    def test_argument_relation_cannot_change_despite_same_order(self):
        self.assert_unproven("You used to transfer cards to the rack.", "I used to transfer cards from the rack.")

    def test_unresolved_habit_cannot_borrow_another_item_state(self):
        value = build_user_history_packet("It moved from its usual hiding place.",
                                         {"current_user": "My folder is on the desk.",
                                          "prior_user_1": "My notebook has its usual hiding place."})
        self.assertTrue(value["obligations"])
        state = verdict(value, "My notebook has its usual hiding place.", source_id="prior_user_1")
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_ambiguous_current_items_do_not_authorise_an_unresolved_habit(self):
        value = build_user_history_packet("It moved from its usual hiding place.",
                                         {"current_user": "My folder is on the desk. My notebook is on the rack.",
                                          "prior_user_1": "My notebook has its usual hiding place."})
        self.assertTrue(value["obligations"])
        state = verdict(value, "My notebook has its usual hiding place.", source_id="prior_user_1")
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_named_matching_habitual_item_is_allowed(self):
        self.assert_witnessed("Your notebook moved from its usual hiding place.",
                              "My notebook has its usual hiding place.")

    def test_unqualified_passive_history_remains_an_obligation(self):
        self.assert_unproven("You've been excluded by the committee.", "I enjoyed the meeting.")

    def test_perfect_aspect_emotional_metaphor_stays_available(self):
        value = packet("You've been murdered emotionally by that chapter.", "The chapter was intense.")
        self.assertFalse(value["obligations"])

    def test_marked_figurative_passive_does_not_acquire_chronology(self):
        self.assertFalse(packet("You've been destroyed figuratively by that chapter.", "The chapter was intense.")["obligations"])

    def test_metaphor_does_not_hide_a_concrete_duration(self):
        self.assert_unproven("You've been destroyed figuratively for four weeks.", "The chapter was intense.")

    def test_metaphor_does_not_hide_a_personal_agent(self):
        self.assert_unproven("You've been managed figuratively by your neighbour.", "The chapter was intense.")


if __name__ == "__main__":
    unittest.main()
