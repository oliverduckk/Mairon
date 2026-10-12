"""A transition's plausible USER-behaviour premise needs USER authority."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.user_history_obligations import (
    build_user_history_packet, detect_user_history, user_history_witnessed,
    validate_user_history_assessments,
)


USER = "I got back into cataloguing the archive."
BAD = "The catalogue looks better once you stop filing cards carelessly."


def packet(candidate=BAD, user=USER, extra=None):
    return build_user_history_packet(candidate, {"current_user": user} | (extra or {}))


def positive(value, quote=USER, source_id="current_user"):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": True,
         "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class UserBehaviourPresuppositionTests(unittest.TestCase):
    def assert_unproven(self, candidate=BAD, user=USER):
        value = packet(candidate, user)
        self.assertTrue(value["obligations"], candidate)
        self.assertTrue(validate_user_history_assessments(positive(value, user), value))

    def assert_witnessed(self, candidate=BAD, user="I've been filing cards carelessly."):
        value = packet(candidate, user)
        self.assertFalse(value["obligations"], candidate)
        self.assertTrue(value["core_witnessed"], candidate)

    def test_present_once_cessation_carries_a_behaviour_obligation(self):
        value = packet()
        self.assertEqual(value["obligations"][0]["kind"], "behaviour_presupposition")
        self.assertEqual(value["obligations"][0]["content_tokens"], ("fil", "card", "carelessly"))

    def test_reentry_into_cataloguing_does_not_supply_filing_behaviour(self):
        self.assert_unproven()

    def test_same_activity_reentry_does_not_supply_careless_manner(self):
        self.assert_unproven(BAD, "I got back into filing cards.")

    def test_matching_explicit_user_progressive_authorises_the_premise(self):
        self.assert_witnessed()

    def test_matching_current_user_progressive_authorises_the_premise(self):
        self.assert_witnessed(user="I am filing cards carelessly.")

    def test_matching_contracted_current_progressive_authorises_the_premise(self):
        self.assert_witnessed(user="I'm filing cards carelessly.")

    def test_matching_typographic_progressive_authorises_the_premise(self):
        self.assert_witnessed(user="I’ve been filing cards carelessly.")

    def test_asserted_user_state_can_support_the_same_present_presupposition(self):
        self.assert_witnessed("The meeting improves once you stop being careless.", "I am careless.")

    def test_matching_negative_user_state_does_not_support_positive_presupposition(self):
        self.assert_unproven("The meeting improves once you stop being careless.", "I am not careless.")

    def test_current_activity_does_not_supply_a_past_habit(self):
        self.assert_unproven("You used to file cards carelessly.", "I am filing cards carelessly.")

    def test_current_state_does_not_supply_a_prior_state(self):
        self.assert_unproven("You used to be careless.", "I am careless.")

    def test_current_negative_activity_does_not_erase_actual_old_past_history(self):
        value = packet("You used to file cards carelessly.", "I'm not filing cards carelessly.",
                       {"prior_user_1": "I used to file cards carelessly."})
        self.assertFalse(value["obligations"])
        self.assertTrue(value["core_witnessed"])

    def test_different_activity_does_not_authorise_the_premise(self):
        self.assert_unproven(BAD, "I've been labelling cards carelessly.")

    def test_different_object_does_not_authorise_the_premise(self):
        self.assert_unproven(BAD, "I've been filing receipts carelessly.")

    def test_different_manner_does_not_authorise_the_premise(self):
        self.assert_unproven(BAD, "I've been filing cards carefully.")

    def test_duration_from_candidate_cannot_be_acquired(self):
        self.assert_unproven("The shelf looks better once you stop mislabelling crates for six weeks.",
                             "I've been mislabelling crates.")

    def test_frequency_from_candidate_cannot_be_acquired(self):
        self.assert_unproven("The shelf looks better once you stop routinely mislabelling crates.",
                             "I've been mislabelling crates.")

    def test_after_quit_present_transition_still_needs_prior_behaviour(self):
        self.assert_unproven("The shelf looks better after you quit stacking boxes unevenly.")

    def test_after_cessation_can_restate_matching_user_activity(self):
        self.assert_witnessed("The shelf looks better after you quit stacking boxes unevenly.",
                              "I've been stacking boxes unevenly.")

    def test_completed_cessation_needs_its_completed_result_too(self):
        self.assert_unproven("You finally stopped mislabelling crates.", "I've been mislabelling crates.")

    def test_completed_cessation_has_a_matching_user_witness(self):
        self.assert_witnessed("You finally stopped mislabelling crates.", "I have stopped mislabelling crates.")

    def test_now_that_completed_transition_preserves_both_obligations(self):
        value = packet("Now that you've stopped stacking boxes unevenly, the shelf looks better.")
        self.assertEqual({item["kind"] for item in value["obligations"]},
                         {"behaviour_presupposition", "prior_activity"})

    def test_now_that_completed_transition_can_use_actual_user_result(self):
        self.assert_witnessed("Now that you've stopped stacking boxes unevenly, the shelf looks better.",
                              "I've stopped stacking boxes unevenly.")

    def test_start_actually_instead_presupposes_prior_nonperformance(self):
        self.assert_unproven("The record improves once you start actually inspecting the crates instead.",
                             "I've resumed cataloguing.")

    def test_matching_negative_activity_can_authorise_start_premise(self):
        self.assert_witnessed("The record improves once you start actually inspecting the crates instead.",
                              "I've not been inspecting the crates.")

    def test_start_premise_does_not_follow_matching_positive_activity(self):
        self.assert_unproven("The record improves once you start actually inspecting the crates instead.",
                             "I've been inspecting the crates.")

    def test_when_start_instead_preserves_the_prior_nonperformance_premise(self):
        self.assert_unproven("The record improves when you start actually inspecting the crates instead.")

    def test_when_start_instead_can_use_matching_negative_user_activity(self):
        self.assert_witnessed("The record improves when you start actually inspecting the crates instead.",
                              "I'm not inspecting the crates.")

    def test_asserted_unqualified_change_needs_its_result_and_prior_behaviour(self):
        self.assert_unproven("You start actually inspecting the crates instead.", "I'm not inspecting the crates.")

    def test_supplied_actual_change_can_support_matching_declarative_change(self):
        self.assert_witnessed("You start actually inspecting the crates instead.",
                              "I started actually inspecting the crates instead.")

    def test_conditional_unqualified_change_does_not_acquire_history(self):
        self.assertFalse(packet("If you start actually inspecting the crates instead, it might help.")["obligations"])

    def test_when_instruction_does_not_acquire_history(self):
        self.assertFalse(packet("When you start actually inspecting the crates instead, check the seals.")["obligations"])

    def test_two_transitions_preserve_two_different_activity_premises(self):
        value = packet("The catalogue improves once you stop filing cards carelessly. "
                       "The shelf improves after you quit stacking boxes unevenly.")
        self.assertEqual(len(value["obligations"]), 2)

    def test_next_started_activity_cannot_be_folded_into_prior_cessation(self):
        self.assert_witnessed("The catalogue improves once you stop filing cards carelessly "
                              "and start actually checking them.")

    def test_conditional_if_is_not_asserted_history(self):
        value = packet("If you stop filing cards carelessly, the index may improve.")
        self.assertFalse(value["obligations"])

    def test_conditional_outer_clause_does_not_acquire_a_temporal_premise(self):
        value = packet("If the plan works once you stop filing cards carelessly, we can try it.")
        self.assertFalse(value["obligations"])

    def test_plain_imperative_advice_is_not_asserted_history(self):
        self.assertFalse(packet("Stop filing cards carelessly and check their labels.")["obligations"])

    def test_modal_recommendation_is_not_asserted_history(self):
        self.assertFalse(packet("You should start actually inspecting the crates instead.")["obligations"])

    def test_temporal_instruction_is_not_asserted_history(self):
        self.assertFalse(packet("Once you stop indexing, check the new labels.")["obligations"])

    def test_deontic_outer_clause_is_not_asserted_history(self):
        self.assertFalse(packet("You should inspect the catalogue once you stop filing cards carelessly.")["obligations"])

    def test_future_user_plan_does_not_authorise_present_premise(self):
        self.assert_unproven(BAD, "I will be filing cards carelessly.")

    def test_conditional_user_activity_is_not_authority(self):
        self.assert_unproven(BAD, "If I've been filing cards carelessly, tell me.")

    def test_questioned_user_activity_is_not_authority(self):
        self.assert_unproven(BAD, "Have I been filing cards carelessly?")

    def test_quoted_user_activity_is_not_authority(self):
        self.assert_unproven(BAD, 'The note says "I have been filing cards carelessly".')

    def test_typographic_quoted_user_activity_is_not_authority(self):
        self.assert_unproven(BAD, 'A script reads “I have been filing cards carelessly”.')

    def test_assistant_activity_is_never_a_user_witness(self):
        value = packet(extra={"assistant": "I've been filing cards carelessly."})
        self.assertNotIn("assistant", value["sources"])
        self.assertTrue(validate_user_history_assessments(
            positive(value, "I've been filing cards carelessly.", "assistant"), value))

    def test_candidate_quote_cannot_be_used_as_a_user_witness(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments(positive(value, BAD), value))

    def test_global_positive_cannot_erase_missing_scoped_assessment(self):
        self.assertTrue(validate_user_history_assessments({"supported": True}, packet()))

    def test_none_classification_cannot_erase_a_core_obligation(self):
        value = packet()
        state = positive(value)
        state["history_assessments"][0]["kind"] = "none"
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_negative_scoped_verdict_cannot_be_overridden_by_global_positive(self):
        value = packet()
        state = positive(value)
        state["history_assessments"][0]["supported"] = False
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_nonboolean_scoped_support_is_malformed(self):
        value = packet()
        state = positive(value)
        state["history_assessments"][0]["supported"] = "true"
        self.assertTrue(validate_user_history_assessments(state, value))

    def test_current_negative_activity_overrides_prior_positive_activity(self):
        value = packet(user="I'm not filing cards carelessly.",
                       extra={"prior_user_1": "I've been filing cards carelessly."})
        self.assertTrue(value["obligations"])
        self.assertFalse(value["core_witnessed"])
        failures = validate_user_history_assessments(
            positive(value, "I've been filing cards carelessly.", "prior_user_1"), value)
        self.assertTrue(any("current USER" in item for item in failures))

    def test_true_previous_user_activity_can_supply_the_premise(self):
        value = packet(extra={"prior_user_1": "I've been filing cards carelessly."})
        self.assertFalse(value["obligations"])
        self.assertTrue(value["core_witnessed"])

    def test_quote_cannot_strip_conditional_scope(self):
        item = detect_user_history(BAD)[0]
        self.assertFalse(user_history_witnessed(item, "I have been filing cards carelessly",
                         source_text="If I have been filing cards carelessly, tell me."))

    def test_marked_absurd_figurative_transition_remains_available(self):
        self.assertFalse(packet("The archive gods will applaud once you stop wrestling "
                                "cosmic dragons metaphorically.")["obligations"])

    def test_absurd_self_personification_does_not_create_user_history(self):
        self.assertFalse(packet("I remain the archive's most irritable haunted stapler.")["obligations"])

    def test_figurative_marker_cannot_hide_concrete_duration(self):
        self.assert_unproven("The archive improves once you stop wrestling crates metaphorically for six weeks.")

    def test_emotional_metaphor_without_a_history_premise_remains_available(self):
        self.assertFalse(packet("Those diagrams murdered you emotionally.")["obligations"])


if __name__ == "__main__":
    unittest.main()
