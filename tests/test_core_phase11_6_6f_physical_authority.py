"""Literal USER physical predicates require matching USER authority."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.claim_grounding import USER_PHYSICAL_ACTION_FAMILIES
from core.physical_observations import (
    detect_user_physical_observations, find_user_physical_state_violations,
)


FAMILIES = USER_PHYSICAL_ACTION_FAMILIES
SIT = "I am sitting here bored."
BODY = "Your fingers are still twitching from the last rehearsal."
BODY_SOURCE = "My fingers are still twitching from the last rehearsal."


def violations(draft, user="I prefer the first option.", extra=None):
    return find_user_physical_state_violations(draft, {"current_user": user} | (extra or {}), FAMILIES)


class PhysicalAuthorityTests(unittest.TestCase):
    def assert_rejected(self, draft, user="I prefer the first option.", extra=None, family=None):
        value = violations(draft, user, extra)
        self.assertTrue(value, draft)
        if family:
            self.assertIn("unsupported Oliver physical-action/state claim involving " + family, value)
        return value

    def assert_allowed(self, draft, user="I prefer the first option.", extra=None):
        self.assertEqual(violations(draft, user, extra), [], draft)

    def test_comma_secondary_stare_is_not_supplied_by_sitting(self):
        self.assert_rejected("Sitting there, staring at nothing, you're a statue.", SIT, family="stare")

    def test_comma_secondary_wait_is_not_supplied_by_sitting(self):
        self.assert_rejected("Sitting there, waiting for a signal, you're a statue.", SIT, family="wait")

    def test_comma_chain_has_independent_predicates(self):
        value = self.assert_rejected("Sitting there, staring at the door, waiting for a signal.", SIT)
        self.assertEqual(set(value), {
            "unsupported Oliver physical-action/state claim involving stare",
            "unsupported Oliver physical-action/state claim involving wait",
        })

    def test_supported_comma_chain_can_preserve_the_supplied_scene(self):
        self.assert_allowed("Sitting there, staring at the door.", "I am sitting here, staring at the door.")

    def test_sentence_initial_stare_remains_an_observation(self):
        self.assert_rejected("Staring at the ceiling? You're a statue.", SIT, family="stare")

    def test_noncomma_secondary_stare_remains_checked(self):
        self.assert_rejected("Sitting there staring at the ceiling, you're a statue.", SIT, family="stare")

    def test_direct_stare_requires_source(self):
        self.assert_rejected("You are staring at the ceiling.", family="stare")

    def test_direct_look_requires_source(self):
        self.assert_rejected("You are looking out the window.", family="look")

    def test_direct_pacing_requires_source(self):
        self.assert_rejected("You are pacing around the studio.", family="pace")

    def test_direct_slumped_requires_source(self):
        self.assert_rejected("You are slumped beside the crate.", family="slump")

    def test_matching_pacing_can_be_echoed(self):
        self.assert_allowed("You are pacing around your studio.", "I am pacing around my studio.")

    def test_matching_slumped_can_be_echoed(self):
        self.assert_allowed("You are slumped beside the crate.", "I am slumped beside the crate.")

    def test_matching_look_can_be_echoed(self):
        self.assert_allowed("You are looking out the window.", "I'm looking out the window.")

    def test_matching_stare_can_be_echoed(self):
        self.assert_allowed("You are staring at the ceiling.", "I'm staring at the ceiling.")

    def test_shaking_hands_need_state_not_ownership(self):
        self.assert_rejected("Your hands are shaking.", "My hands are on the desk.", family="shake")

    def test_twitching_fingers_need_state_not_activity_topic(self):
        self.assert_rejected("Your fingers are twitching.", "I enjoy rehearsals.", family="twitch")

    def test_watering_eyes_need_state(self):
        self.assert_rejected("Your eyes are watering.", family="water")

    def test_tense_shoulders_need_state(self):
        self.assert_rejected("Your shoulders are tense.", family="tense")

    def test_crossed_arms_need_state(self):
        self.assert_rejected("Your arms are crossed.", family="cross")

    def test_sore_neck_needs_state(self):
        self.assert_rejected("Your neck is sore.", family="sore")

    def test_numb_feet_need_state(self):
        self.assert_rejected("Your feet are numb.", family="numb")

    def test_matching_body_state_can_be_echoed(self):
        self.assert_allowed("Your hands are shaking.", "My hands are shaking.")

    def test_matching_crossed_arms_can_be_echoed(self):
        self.assert_allowed("Your arms are crossed.", "My arms are crossed.")

    def test_matching_adjective_body_state_can_be_echoed(self):
        self.assert_allowed("Your shoulders are tense.", "My shoulders are tense.")

    def test_different_body_part_is_not_supported(self):
        self.assert_rejected("Your fingers are shaking.", "My hands are shaking.")

    def test_plural_body_part_does_not_become_singular(self):
        self.assert_rejected("Your hand is shaking.", "My hands are shaking.")

    def test_different_body_predicate_is_not_supported(self):
        self.assert_rejected("Your fingers are twitching.", "My fingers are aching.")

    def test_stronger_body_intensity_needs_matching_authority(self):
        self.assert_rejected("Your hands are shaking violently.", "My hands are shaking.")

    def test_matching_body_intensity_can_be_echoed(self):
        self.assert_allowed("Your hands are shaking violently.", "My hands are shaking violently.")

    def test_weaker_body_restatement_can_omit_supplied_intensity(self):
        self.assert_allowed("Your hands are shaking.", "My hands are shaking violently.")

    def test_past_irregular_body_state_cannot_supply_current_state(self):
        self.assert_rejected("Your hands are shaking.", "My hands shook.")

    def test_past_regular_body_state_cannot_supply_current_state(self):
        self.assert_rejected("Your fingers are twitching.", "My fingers twitched.")

    def test_explicit_past_body_state_can_be_echoed_as_past(self):
        self.assert_allowed("Your hands were shaking.", "My hands were shaking.")

    def test_past_observation_wrapper_is_not_a_current_witness(self):
        self.assert_rejected("Your hands are shaking.", "I saw my hands shaking yesterday.")

    def test_remembered_body_scene_is_not_current_state(self):
        self.assert_rejected("Your fingers are twitching.", "I remember my fingers twitching after rehearsal.")

    def test_completed_perfect_action_does_not_prove_ongoing_action(self):
        self.assert_rejected("You are holding the tablet.", "I have held the tablet.")

    def test_ongoing_perfect_action_can_supply_current_action(self):
        self.assert_allowed("You are holding the tablet.", "I've been holding the tablet.")

    def test_matching_prior_event_state_requires_both_parts(self):
        self.assert_allowed(BODY, BODY_SOURCE)

    def test_prior_event_topic_without_bodily_state_is_not_authority(self):
        self.assert_rejected(BODY, "I had a rehearsal yesterday.")

    def test_body_state_without_prior_event_relation_is_not_authority(self):
        self.assert_rejected(BODY, "My fingers are still twitching.")

    def test_state_and_event_in_separate_sentences_do_not_supply_relation(self):
        self.assert_rejected(BODY, "My fingers are still twitching. I had a rehearsal yesterday.")

    def test_prior_event_identity_cannot_change(self):
        self.assert_rejected(BODY, "My fingers are still twitching from the last exercise.")

    def test_prior_event_order_cannot_change(self):
        self.assert_rejected(BODY, "My fingers are still twitching after the last rehearsal.")

    def test_current_state_does_not_supply_continuity_upgrade(self):
        self.assert_rejected(BODY, "My fingers are twitching from the last rehearsal.")

    def test_weaker_state_can_omit_supported_prior_relation(self):
        self.assert_allowed("Your fingers are twitching.", BODY_SOURCE)

    def test_outer_future_does_not_erase_actual_still_state(self):
        self.assert_rejected("We'll see how that goes when you try again while your fingers are still twitching from the last rehearsal.")

    def test_outer_if_question_does_not_erase_actual_still_state(self):
        self.assert_rejected("I suppose we'll see if you can prove it when you try again while your fingers are still twitching from the last rehearsal.")

    def test_supported_still_state_survives_outer_future_decoration(self):
        self.assert_allowed("We'll see when you try again while your fingers are still twitching from the last rehearsal.", BODY_SOURCE)

    def test_direct_if_body_state_is_a_hypothesis(self):
        self.assert_allowed("If your hands are shaking, rest.")

    def test_if_still_prior_body_state_remains_hypothetical(self):
        self.assert_allowed("If your fingers are still twitching from the last rehearsal, rest.")

    def test_might_body_state_is_a_hypothesis(self):
        self.assert_allowed("Your hands might shake under strain.")

    def test_generic_can_body_property_is_not_an_observation(self):
        self.assert_allowed("Your hands can shake under strain.")

    def test_can_action_advice_is_not_an_observation(self):
        self.assert_allowed("You can sit down if you want.")

    def test_might_scene_scope_is_shared_with_linked_fragment(self):
        self.assert_allowed("You might sit down, staring at the ceiling.")

    def test_future_scene_scope_is_shared_with_linked_fragment(self):
        self.assert_allowed("You will sit down, staring at the ceiling.")

    def test_when_future_body_state_without_actual_still_premise_is_conditional(self):
        self.assert_allowed("When you arrive, your hands are shaking.")

    def test_plain_body_question_is_not_an_observation(self):
        self.assert_allowed("Are your shoulders tense?")

    def test_plain_action_question_is_not_an_observation(self):
        self.assert_allowed("Are you pacing around the studio?")

    def test_why_body_question_preserves_actual_premise(self):
        self.assert_rejected("Why are your hands shaking?")

    def test_supported_why_body_question_can_preserve_actual_premise(self):
        self.assert_allowed("Why are your hands shaking?", "My hands are shaking.")

    def test_when_past_body_question_preserves_past_premise(self):
        self.assert_rejected("When were your hands shaking?")

    def test_matching_past_body_question_can_be_supported(self):
        self.assert_allowed("When were your hands shaking?", "My hands were shaking.")

    def test_quoted_candidate_body_state_is_not_user_state(self):
        self.assert_allowed('The script says "your hands are shaking."')

    def test_quote_user_cannot_supply_actual_state(self):
        self.assert_rejected("Your hands are shaking.", 'The script says "my hands are shaking."')

    def test_conditional_user_cannot_supply_actual_state(self):
        self.assert_rejected("Your hands are shaking.", "If my hands are shaking, I will rest.")

    def test_questioned_user_cannot_supply_actual_state(self):
        self.assert_rejected("Your hands are shaking.", "Are my hands shaking?")

    def test_future_user_cannot_supply_actual_state(self):
        self.assert_rejected("Your hands are shaking.", "My hands will shake later.")

    def test_capability_user_cannot_supply_actual_action(self):
        self.assert_rejected("You are holding the tablet.", "I can hold the tablet.")

    def test_third_party_transition_is_not_user_physical_authority(self):
        self.assert_rejected("You are staring at the floor.", "I told Lee to stop staring at the floor.")

    def test_third_party_requested_transition_is_not_user_action(self):
        self.assert_rejected("You are walking outside.", "I asked Lee to stop walking outside.")

    def test_third_party_body_state_is_not_user_state(self):
        self.assert_rejected("Your hands are shaking.", "Lee's hands are shaking.")

    def test_generic_nominal_activity_topic_is_not_user_action(self):
        self.assert_rejected("You are walking outside.", "Walking outdoors is an interesting topic.")

    def test_nominal_body_topic_is_not_personal_state(self):
        self.assert_rejected("Your hands are shaking.", "Shaking hands can be an interesting topic.")

    def test_same_family_word_without_participant_is_not_authority(self):
        self.assert_rejected("You are holding a tablet.", "The instructions mention holding a tablet.")

    def test_source_action_object_must_match(self):
        self.assert_rejected("You are holding a tablet.", "I am holding a pencil.")

    def test_source_location_must_match(self):
        self.assert_rejected("You are sitting near a crate.", "I am sitting.")

    def test_source_visual_target_must_match(self):
        self.assert_rejected("You are staring into a cupboard.", "I am staring.")

    def test_source_direction_must_match(self):
        self.assert_rejected("You are walking outside.", "I am walking indoors.")

    def test_matching_source_location_is_allowed(self):
        self.assert_allowed("You are sitting near the crate.", "I am sitting near a crate.")

    def test_matching_source_object_is_allowed(self):
        self.assert_allowed("You are holding your tablet.", "I am holding my tablet.")

    def test_weaker_action_can_omit_known_object(self):
        self.assert_allowed("You are holding something.", "I am holding something.")

    def test_unqualified_action_can_omit_known_specific_object(self):
        self.assert_allowed("You are holding.", "I am holding the tablet.")

    def test_latest_current_negation_overrides_older_body_state(self):
        self.assert_rejected("Your hands are shaking.", "My hands are not shaking now.",
                             {"prior_user_1": "My hands are shaking."})

    def test_latest_prior_negation_overrides_older_body_state(self):
        self.assert_rejected("Your hands are shaking.", "I prefer the first option.",
                             {"prior_user_1": "My hands are shaking.", "prior_user_2": "My hands are not shaking."})

    def test_latest_negative_state_blocks_prior_relation_too(self):
        self.assert_rejected(BODY, "My fingers are not twitching now.", {"prior_user_1": BODY_SOURCE})

    def test_negative_anything_cannot_support_positive_object(self):
        self.assert_rejected("You are holding a tablet.", "I am not holding anything.")

    def test_latest_negative_anything_overrides_old_object_state(self):
        self.assert_rejected("You are holding a tablet.", "I am not holding anything.",
                             {"prior_user_1": "I am holding a tablet."})

    def test_current_positive_can_supersede_old_generic_negative(self):
        self.assert_allowed("You are holding.", "I am holding a tablet.",
                            {"prior_user_1": "I am not holding anything."})

    def test_different_body_correction_does_not_erase_actual_other_state(self):
        self.assert_allowed("Your hands are shaking.", "My shoulders are not tense.",
                            {"prior_user_1": "My hands are shaking."})

    def test_source_turn_order_is_numeric_not_mapping_order(self):
        self.assert_rejected("Your hands are shaking.", "I prefer the first option.",
                             {"prior_user_2": "My hands are not shaking.", "prior_user_1": "My hands are shaking."})

    def test_no_longer_correction_overrides_old_state(self):
        self.assert_rejected("Your hands are shaking.", "My hands are no longer shaking.",
                             {"prior_user_1": "My hands are shaking."})

    def test_assistant_text_is_not_a_source(self):
        self.assert_rejected("Your hands are shaking.", extra={"assistant_1": "My hands are shaking."})

    def test_candidate_text_is_not_a_source(self):
        self.assert_rejected("Your hands are shaking.", extra={"candidate": "My hands are shaking."})

    def test_core_contract_instructions_are_not_user_witnesses(self):
        self.assert_rejected("Your hands are shaking.", extra={"core_contract": "My hands are shaking."})

    def test_object_personification_is_not_user_physical_state(self):
        self.assert_allowed("The chair is judging your choices.")

    def test_absurd_object_return_does_not_acquire_user_history(self):
        self.assert_allowed("The device returned from another dimension.")

    def test_known_sitting_can_keep_decorative_statue_analogy(self):
        self.assert_allowed("You're sitting there like a statue.", SIT)

    def test_known_sitting_mood_echo_is_not_an_added_physical_argument(self):
        self.assert_allowed("You're sitting there bored, apparently unimpressed.", SIT)

    def test_shorthand_first_person_and_deictic_echo_remain_supported(self):
        self.assert_allowed("You're sitting there.", "im sitting here bored")

    def test_typographic_first_person_echo_remains_supported(self):
        self.assert_allowed("You’re sitting there.", "I’m sitting here.")

    def test_abstract_look_for_answer_is_not_visual_observation(self):
        self.assert_allowed("You're looking for an answer.")

    def test_abstract_alternative_perspective_is_not_visual_observation(self):
        self.assert_allowed("You're looking at it another way.")

    def test_old_before_sat_down_guard_is_preserved(self):
        self.assert_rejected("Before you've even sat down, the plan changed.", family="sit")

    def test_old_rushing_out_guard_is_preserved(self):
        self.assert_rejected("It happened while you were rushing out.", family="rush")

    def test_matching_old_rushing_out_guard_can_pass(self):
        self.assert_allowed("You were rushing out.", "I was rushing out before work.")

    def test_existing_transition_stare_is_preserved(self):
        self.assert_rejected("I've been waiting for you to stop staring at the floor.", family="stare")

    def test_one_family_diagnostic_is_bounded_and_contains_no_text(self):
        value = self.assert_rejected("Your hands are shaking from the private rehearsal.")
        self.assertEqual(value, ["unsupported Oliver physical-action/state claim involving shake"])

    def test_detected_record_is_immutable(self):
        record = detect_user_physical_observations(BODY, speaker="assistant", action_families=FAMILIES)[0]
        with self.assertRaises(FrozenInstanceError):
            record.family = "another"

    def test_prior_relation_and_current_state_are_distinct_typed_facets(self):
        record = detect_user_physical_observations(BODY, speaker="assistant", action_families=FAMILIES)[0]
        self.assertEqual(record.kind, "body_state")
        self.assertEqual(record.body_part, "fingers")
        self.assertEqual(record.temporal, "current")
        self.assertTrue(record.continuing)
        self.assertEqual(record.prior_relation, ("from", ("last", "rehearsal")))

    def test_every_retry_candidate_gets_its_own_obligations(self):
        for draft in ("Your hands are shaking.", "Your shoulders are tense.", BODY):
            self.assert_rejected(draft)


if __name__ == "__main__":
    unittest.main()
