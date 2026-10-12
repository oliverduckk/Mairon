"""Core projects bounded USER premises without inventing their authority."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.user_history_obligations import (
    build_user_history_packet, detect_user_history, validate_user_history_assessments,
)


WH = "Why haven't you finished your current workshop project yet?"
CONCERN = "You can stop worrying about the assessment now."
PARTIAL = "I'm halfway through my current workshop project."
WORRY = "I'm worried about the assessment."
OTHER = "The delivery arrived today."


def packet(candidate=CONCERN, user=OTHER, extra=None):
    return build_user_history_packet(candidate, {"current_user": user} | (extra or {}))


def positive(value, quote=OTHER, source_id="current_user"):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class UserStateAuthorityTests(unittest.TestCase):
    def assert_unproven(self, candidate=CONCERN, user=OTHER, extra=None):
        value = packet(candidate, user, extra)
        self.assertTrue(value["obligations"], candidate)
        self.assertTrue(validate_user_history_assessments(positive(value, user), value), candidate)
        return value

    def assert_witnessed(self, candidate=CONCERN, user=WORRY, extra=None):
        value = packet(candidate, user, extra)
        self.assertFalse(value["obligations"], candidate)
        self.assertTrue(value["core_witnessed"], candidate)
        return value

    def assert_no_assertion(self, candidate):
        value = packet(candidate)
        self.assertFalse(value["obligations"], candidate)
        self.assertFalse(value["core_witnessed"], candidate)

    def test_direct_why_noncompletion_has_owned_identity_and_completion(self):
        value = self.assert_unproven(WH)
        self.assertEqual({item["kind"] for item in value["obligations"]},
                         {"user_task_identity", "task_completion_presupposition"})

    def test_outer_question_does_not_erase_why_noncompletion(self):
        self.assert_unproven("Are you trying to justify why you haven't finished your current workshop project yet?")

    def test_outer_capability_question_keeps_the_embedded_fact(self):
        self.assert_unproven("Could you explain why you haven't finished your current workshop project yet?")

    def test_embedded_simple_past_cessation_is_a_premise(self):
        self.assert_unproven("Can you explain why you stopped indexing?")

    def test_matching_user_cessation_supports_embedded_simple_past(self):
        self.assert_witnessed("Can you explain why you stopped indexing?", "I stopped indexing.")

    def test_direct_when_cessation_is_a_premise(self):
        self.assert_unproven("When did you stop indexing?")

    def test_direct_why_cessation_is_a_premise(self):
        self.assert_unproven("Why did you stop indexing?")

    def test_direct_why_ongoing_is_a_premise(self):
        self.assert_unproven("Why are you still indexing?")

    def test_matching_ongoing_user_activity_supports_current_wh(self):
        self.assert_witnessed("Why are you still indexing?", "I'm indexing.")

    def test_current_activity_does_not_supply_a_completed_cessation(self):
        self.assert_unproven("Why did you stop indexing?", "I'm indexing.")

    def test_complex_completion_target_retains_generic_core_obligation(self):
        value = self.assert_unproven("Why haven't you finished all the archive labels for Mara?")
        self.assertEqual(value["obligations"][0]["kind"], "embedded_user_state")

    def test_plain_completion_question_does_not_assert_noncompletion(self):
        self.assert_no_assertion("Have you finished the workshop project?")

    def test_plain_worry_question_does_not_assert_worry(self):
        self.assert_no_assertion("Are you worried about the assessment?")

    def test_plain_working_question_does_not_assert_current_task(self):
        self.assert_no_assertion("Are you working on anything right now?")

    def test_plain_stop_question_does_not_presuppose_cessation(self):
        self.assert_no_assertion("Did you stop indexing?")

    def test_plain_device_question_does_not_assert_device_history(self):
        self.assert_no_assertion("Did you use a stylus while waiting?")

    def test_outer_if_keeps_wh_hypothetical(self):
        self.assert_no_assertion("If you haven't finished the project, why haven't you finished it?")

    def test_quoted_wh_question_is_not_user_state(self):
        self.assert_no_assertion('That dialogue asks "why haven\'t you finished your current project?"')

    def test_hypothetical_wh_modal_does_not_assert_completion(self):
        self.assert_no_assertion("Why might you not have finished the workshop project?")

    def test_explicit_nonassertion_keeps_wh_unasserted(self):
        self.assert_no_assertion("I don't claim that why you haven't finished your project is known.")

    def test_if_worry_remains_advice(self):
        self.assert_no_assertion("If you're worried about the assessment, check tomorrow.")

    def test_if_noncompletion_remains_advice(self):
        self.assert_no_assertion("If you haven't finished the project, leave it for later.")

    def test_you_might_be_worried_is_not_asserted_history(self):
        self.assert_no_assertion("You might be worried about the assessment.")

    def test_future_worry_does_not_supply_current_worry(self):
        self.assert_no_assertion("You will be worrying about the assessment tomorrow.")

    def test_arrival_does_not_supply_worry(self):
        self.assert_unproven()

    def test_delay_does_not_supply_worry(self):
        self.assert_unproven(user="The delivery was delayed.")

    def test_anticipation_does_not_supply_worry(self):
        self.assert_unproven(user="I'm looking forward to the assessment.")

    def test_explicit_worry_supports_matching_cessation(self):
        self.assert_witnessed()

    def test_explicit_stress_supports_bounded_concern_family(self):
        self.assert_witnessed(user="I've been stressing about the assessment.")

    def test_positive_deontic_cessation_does_not_invent_negative_habit(self):
        value = self.assert_witnessed("You don't have to keep stressing about the assessment anymore.")
        self.assertEqual(value["core_witnessed"][0]["polarity"], "positive")
        self.assertEqual(value["core_witnessed"][0]["frequency"], ())

    def test_stop_being_worried_preserves_same_topic(self):
        self.assert_witnessed("Now you can stop being worried about the assessment.")

    def test_different_concern_topic_does_not_support_cessation(self):
        self.assert_unproven(user="I'm worried about the shipment.")

    def test_past_mental_state_does_not_supply_current_cessation(self):
        self.assert_unproven(user="I was worried about the assessment.")

    def test_simple_past_worry_does_not_supply_current_cessation(self):
        self.assert_unproven(user="I worried about the assessment last week.")

    def test_completed_perfect_worry_is_not_ongoing_worry(self):
        self.assert_unproven(user="I've worried about the assessment.")

    def test_ongoing_perfect_worry_can_supply_current_cessation(self):
        self.assert_witnessed(user="I've been worried about the assessment.")

    def test_used_to_worry_is_not_current_worry(self):
        self.assert_unproven(user="I used to worry about the assessment.")

    def test_current_negative_worry_rejects_positive_premise(self):
        self.assert_unproven(user="I'm not worried about the assessment anymore.")

    def test_questioned_user_worry_is_not_a_witness(self):
        self.assert_unproven(user="Am I worrying about the assessment?")

    def test_conditional_user_worry_is_not_a_witness(self):
        self.assert_unproven(user="If I'm worried about the assessment, I'll ask.")

    def test_quoted_user_worry_is_not_a_witness(self):
        self.assert_unproven(user='I said the character says "I am worried about the assessment."')

    def test_future_user_worry_is_not_a_witness(self):
        self.assert_unproven(user="I will be worrying about the assessment tomorrow.")

    def test_speculative_user_mental_state_is_not_a_witness(self):
        self.assert_unproven(user="I suppose I might be worrying about the assessment.")

    def test_candidate_speaker_hedge_does_not_erase_real_presupposition(self):
        self.assert_unproven("I suppose you can stop worrying about the assessment now.")

    def test_genuine_suppose_hypothesis_remains_nonassertive(self):
        self.assert_no_assertion("Suppose you can stop worrying about the assessment now.")

    def test_candidate_may_cessation_remains_nonassertive(self):
        self.assert_no_assertion("You might stop worrying about the assessment later.")

    def test_opaque_future_topic_keeps_outer_concern_actual(self):
        value = self.assert_witnessed("You can stop worrying about whether the parcel will arrive before Friday now.",
                                     "I've been stressing that the parcel won't arrive before Friday.")
        item = value["core_witnessed"][0]
        self.assertEqual(item["state_temporal"], "current")
        self.assertEqual(item["polarity"], "positive")
        self.assertEqual(item["target_modals"], ("will",))

    def test_opposite_asserted_target_polarity_is_not_the_same_concern(self):
        self.assert_unproven("You can stop worrying that the parcel will arrive before Friday now.",
                             "I've been stressing that the parcel won't arrive before Friday.")

    def test_different_deadline_is_not_same_concern(self):
        self.assert_unproven("You can stop worrying about whether the parcel will arrive before Monday now.",
                             "I've been stressing that the parcel won't arrive before Friday.")

    def test_different_future_subject_is_not_same_concern(self):
        self.assert_unproven("You can stop worrying about whether the crates will arrive before Friday now.",
                             "I've been stressing that the parcel won't arrive before Friday.")

    def test_different_future_predicate_is_not_same_concern(self):
        self.assert_unproven("You can stop worrying about whether the parcel will break before Friday now.",
                             "I've been stressing that the parcel won't arrive before Friday.")

    def test_past_topic_does_not_supply_future_topic(self):
        self.assert_unproven("You can stop worrying about whether the parcel will fail now.",
                             "I'm worrying about whether the parcel failed.")

    def test_current_topic_does_not_supply_future_topic(self):
        self.assert_unproven("You can stop worrying about whether the parcel will fail now.",
                             "I'm worrying about whether the parcel fails.")

    def test_conditional_inside_opaque_target_does_not_erase_actual_worry(self):
        self.assert_witnessed("You can stop worrying about if the shipment will arrive now.",
                              "I'm worried about if the shipment will arrive.")

    def test_current_single_topic_can_resolve_bounded_it_anaphor(self):
        self.assert_witnessed("You can stop worrying about whether it'll arrive before Friday now.",
                              "I've been stressing that the parcel won't arrive before Friday.")

    def test_multiple_current_topics_do_not_resolve_it_anaphor(self):
        self.assert_unproven("You can stop worrying about whether it'll arrive before Friday now.",
                             "I'm worried that the parcel won't arrive before Friday. I'm worried that the crate won't arrive before Friday.")

    def test_unbound_it_topic_does_not_borrow_prior_subject(self):
        self.assert_unproven("You can stop worrying about whether it'll arrive before Friday now.", OTHER,
                             {"prior_user_1": "I'm worried whether it will arrive before Friday."})

    def test_resolved_it_cannot_change_opaque_deadline(self):
        self.assert_unproven("You can stop worrying about whether it'll arrive before Tuesday now.",
                             "I'm worried whether the parcel will arrive before Friday.")

    def test_resolved_it_cannot_change_opaque_predicate(self):
        self.assert_unproven("You can stop worrying about whether it'll break before Friday now.",
                             "I'm worried whether the parcel will arrive before Friday.")

    def test_latest_prior_negative_concern_blocks_older_positive(self):
        value = self.assert_unproven(extra={"prior_user_1": WORRY,
                                           "prior_user_2": "I'm not worried about the assessment anymore."})
        self.assertTrue(validate_user_history_assessments(positive(value, WORRY, "prior_user_1"), value))

    def test_latest_current_negative_concern_blocks_older_positive(self):
        self.assert_unproven(user="I'm not worried about the assessment anymore.", extra={"prior_user_1": WORRY})

    def test_later_different_concern_correction_does_not_erase_original(self):
        self.assert_witnessed(user=OTHER, extra={"prior_user_1": WORRY,
                                                "prior_user_2": "I'm not worried about the shipment anymore."})

    def test_latest_positive_concern_supersedes_older_negative(self):
        self.assert_witnessed(user=OTHER, extra={"prior_user_1": "I'm not worried about the assessment.",
                                                "prior_user_2": WORRY})

    def test_sources_order_is_numeric_turn_order_not_mapping_insertion(self):
        self.assert_unproven(extra={"prior_user_2": "I'm not worried about the assessment.", "prior_user_1": WORRY})

    def test_assistant_mental_prose_cannot_supply_worry(self):
        self.assert_unproven(extra={"assistant_1": WORRY})

    def test_explicit_partial_progress_proves_same_noncompletion(self):
        self.assert_witnessed(WH, PARTIAL)

    def test_partway_progress_proves_same_noncompletion(self):
        self.assert_witnessed(WH, "I'm partway through my current workshop project.")

    def test_explicit_unfinished_task_proves_noncompletion(self):
        self.assert_witnessed(WH, "My unfinished workshop project is on the desk.")

    def test_working_on_does_not_prove_noncompletion(self):
        self.assert_unproven(WH, "I'm working on my current workshop project.")

    def test_making_progress_does_not_prove_noncompletion(self):
        self.assert_unproven(WH, "I'm making progress on my current workshop project.")

    def test_different_task_cannot_prove_noncompletion(self):
        self.assert_unproven(WH, "I'm halfway through my current storage project.")

    def test_missing_task_owner_cannot_supply_user_ownership(self):
        self.assert_unproven(WH, "I'm halfway through the current workshop project.")

    def test_past_task_does_not_prove_current_task(self):
        self.assert_unproven(WH, "I was halfway through my workshop project.")

    def test_finished_task_cannot_prove_noncompletion(self):
        self.assert_unproven(WH, "I've finished my current workshop project.")

    def test_task_qualifier_cannot_be_invented(self):
        self.assert_unproven("Why haven't you finished your current existing workshop project?", PARTIAL)

    def test_latest_prior_completion_blocks_older_unfinished_task(self):
        value = self.assert_unproven(WH, OTHER, {"prior_user_1": PARTIAL,
                                               "prior_user_2": "I've finished my current workshop project."})
        self.assertTrue(validate_user_history_assessments(positive(value, PARTIAL, "prior_user_1"), value))

    def test_latest_no_current_task_blocks_older_owned_task(self):
        self.assert_unproven(WH, "I don't have a current workshop project.", {"prior_user_1": PARTIAL})

    def test_current_unfinished_task_supersedes_older_completed_task(self):
        self.assert_witnessed(WH, PARTIAL, {"prior_user_1": "I've finished my current workshop project."})

    def test_different_task_completion_does_not_erase_original(self):
        self.assert_witnessed(WH, OTHER, {"prior_user_1": PARTIAL,
                                          "prior_user_2": "I've finished my current storage project."})

    def test_reentry_to_other_activity_does_not_prove_task_or_behaviour(self):
        self.assert_unproven("Why did you stop indexing?", "I got back into arranging the archive.")

    def test_positive_global_without_scoped_assessments_fails_closed(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments({"supported": True}, value))

    def test_positive_global_cannot_erase_failed_scoped_assessment(self):
        value = packet()
        checked = positive(value)
        checked["history_assessments"][0]["supported"] = False
        self.assertTrue(validate_user_history_assessments(checked, value))

    def test_malformed_scoped_assessment_fails_closed(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments({"supported": True, "history_assessments": ["none"]}, value))

    def test_forged_positive_quote_cannot_supply_state(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments(positive(value, WORRY), value))

    def test_substring_quote_cannot_remove_outer_if_scope(self):
        user = "If I am worried about the assessment, I will ask."
        value = packet(user=user)
        self.assertTrue(validate_user_history_assessments(positive(value, "I am worried about the assessment"), value))

    def test_substring_quote_cannot_remove_quote_scope(self):
        user = 'The line is "I am worried about the assessment."'
        value = packet(user=user)
        self.assertTrue(validate_user_history_assessments(positive(value, "I am worried about the assessment"), value))

    def test_candidate_prose_is_not_a_source(self):
        self.assert_unproven(extra={"candidate": WORRY})

    def test_absurd_device_personification_is_not_user_state(self):
        self.assert_no_assertion("The processor is begging for mercy.")

    def test_absurd_return_metaphor_is_not_user_history(self):
        self.assert_no_assertion("The device returned from a shadow realm.")

    def test_fictional_divine_humour_is_not_user_history(self):
        self.assert_no_assertion("The fictional gods finally forgave you.")

    def test_source_snapshot_retains_only_core_user_ids(self):
        value = packet(extra={"assistant_1": WORRY, "model": WORRY})
        self.assertEqual(value["sources"], {"current_user": OTHER})

    def test_each_new_draft_rebuilds_obligations(self):
        for candidate in (CONCERN, "Now you can stop being worried about the assessment.",
                          "You don't have to keep stressing about the assessment anymore."):
            self.assert_unproven(candidate)


if __name__ == "__main__":
    unittest.main()
