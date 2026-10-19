"""Neutral social USER-history projection and literal witness regressions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.user_history_obligations import (
    build_user_history_packet, detect_user_history, validate_user_history_assessments,
)


USER = "I'm sitting here bored."
HISTORY = ("You're sitting here bored, so I suppose you've finally decided to stop "
           "pretending that inspecting the console is productive.")
OBJECT = "The red case is less likely to be left behind in the van again."
LOCATION = "My spare adapter is in the red case."


def packet(candidate=HISTORY, user=USER, extra=None):
    return build_user_history_packet(candidate, {"current_user": user} | (extra or {}))


def approval(value, quote=USER, source_id="current_user"):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class LocalSocialHistoryAuthorityTests(unittest.TestCase):
    def assert_unproven(self, candidate=HISTORY, user=USER, extra=None):
        value = packet(candidate, user, extra)
        self.assertTrue(value["obligations"], candidate)
        self.assertTrue(validate_user_history_assessments(approval(value, user), value))
        return value

    def assert_witnessed(self, candidate, user, extra=None):
        value = packet(candidate, user, extra)
        self.assertFalse(value["obligations"], value)
        self.assertTrue(value["core_witnessed"], value)
        return value

    def assert_nonassertive(self, candidate):
        self.assertFalse(packet(candidate)["obligations"], candidate)

    def test_early_user_echo_cannot_swallow_a_second_history_predicate(self):
        value = self.assert_unproven()
        self.assertTrue(any(item["candidate_span"].startswith("you've finally decided")
                            for item in value["obligations"]))

    def test_discourse_suppose_is_not_hypothetical_user_history(self):
        self.assert_unproven("I suppose you've finally stopped pretending inspecting the console is productive.")

    def test_decision_cessation_cannot_hide_a_new_visual_activity(self):
        self.assert_unproven("You're sitting here bored, so I suppose you've finally decided to stop pretending that staring at the status board is productive.")

    def test_completed_cessation_cannot_hide_a_new_visual_activity(self):
        self.assert_unproven("I suppose you've finally stopped pretending that staring at the status board is productive.")

    def test_discourse_hedge_after_supplied_state_does_not_erase_cessation(self):
        self.assert_unproven("You're bored, so I suppose you've finally stopped inspecting the console.")

    def test_matching_user_decision_history_can_be_repeated(self):
        self.assert_witnessed(HISTORY, "I've finally decided to stop pretending that inspecting the console is productive.")

    def test_user_sitting_does_not_establish_a_different_activity_history(self):
        value = self.assert_unproven()
        self.assertFalse(value["core_witnessed"])

    def test_current_negative_defeats_stale_decision_history(self):
        old = "I've finally decided to stop pretending that inspecting the console is productive."
        value = packet(HISTORY, "I haven't finally decided to stop pretending that inspecting the console is productive.",
                       {"prior_user_1": old})
        self.assertTrue(value["obligations"])
        self.assertTrue(validate_user_history_assessments(approval(value, old, "prior_user_1"), value))

    def test_assistant_history_is_not_user_decision_authority(self):
        value = self.assert_unproven(extra={"prior_assistant_1": HISTORY})
        self.assertNotIn("prior_assistant_1", value["sources"])

    def test_candidate_cannot_authorize_its_own_decision_history(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments(approval(value, HISTORY, "candidate"), value))

    def test_global_positive_without_scoped_history_cannot_erase_obligation(self):
        self.assertTrue(validate_user_history_assessments({"supported": True}, packet()))

    def test_malformed_scoped_history_fails_closed(self):
        value = packet()
        verdict = approval(value)
        verdict["history_assessments"][0]["supported"] = "yes"
        self.assertTrue(validate_user_history_assessments(verdict, value))

    def test_suppose_directive_is_still_hypothetical(self):
        self.assert_nonassertive("Suppose you've finally stopped inspecting the console.")

    def test_if_inside_discourse_hedge_still_is_conditional(self):
        self.assert_nonassertive("I suppose if you've finally stopped inspecting the console, take a break.")

    def test_user_uncertain_suppose_is_not_an_authoritative_history_witness(self):
        self.assert_unproven("You've finally stopped inspecting the console.",
                             "I suppose I've finally stopped inspecting the console.")

    def test_quoted_history_is_not_personal_history(self):
        self.assert_nonassertive('The example says "I suppose you have finally stopped inspecting the console."')

    def test_plain_question_does_not_assert_a_user_activity(self):
        self.assert_nonassertive("Have you stopped inspecting the console?")

    def test_harmless_sitting_banter_does_not_invent_history(self):
        self.assert_nonassertive("Sitting there bored has apparently become today's main event.")

    def test_obvious_object_personification_does_not_become_user_history(self):
        self.assert_nonassertive("Your compiler is begging for mercy again.")

    def test_future_repeat_passive_requires_actual_object_history(self):
        value = self.assert_unproven(OBJECT, LOCATION)
        self.assertEqual(value["obligations"][0]["kind"], "object_prior_event")
        self.assertEqual(value["obligations"][0]["event_key"], ("leav", "behind", "in", "van"))

    def test_present_object_location_does_not_supply_prior_event(self):
        self.assert_unproven("The red case now holds a secret, making it less likely to be left behind in the van again.", LOCATION)

    def test_literal_prior_event_supports_bounded_repeat_premise(self):
        self.assert_witnessed(OBJECT, "I left the red case behind in the van before.")

    def test_prior_passive_history_can_support_matching_event(self):
        self.assert_witnessed(OBJECT, "My red case was left behind in the van before.")

    def test_lost_repeat_requires_user_history(self):
        self.assert_unproven("The red case is less likely to be lost again.", LOCATION)

    def test_forgotten_repeat_requires_user_history(self):
        self.assert_unproven("The red case is less likely to be forgotten again.", LOCATION)

    def test_left_repeat_requires_user_history(self):
        self.assert_unproven("You left the red case in the van again.", LOCATION)

    def test_lost_active_repeat_requires_user_history(self):
        self.assert_unproven("You lost the red case again.", LOCATION)

    def test_forgot_active_repeat_requires_user_history(self):
        self.assert_unproven("You forgot the red case again.", LOCATION)

    def test_different_object_does_not_supply_prior_event(self):
        self.assert_unproven(OBJECT, "I left the blue case behind in the van before.")

    def test_different_location_does_not_supply_prior_event(self):
        self.assert_unproven(OBJECT, "I left the red case behind in the office before.")

    def test_different_event_does_not_supply_prior_event(self):
        self.assert_unproven(OBJECT, "I repaired the red case in the van before.")

    def test_negative_user_history_does_not_supply_positive_event(self):
        self.assert_unproven(OBJECT, "I never left the red case behind in the van.")

    def test_latest_negative_defeats_stale_object_history(self):
        old = "I left the red case behind in the van before."
        value = packet(OBJECT, "I never left the red case behind in the van.", {"prior_user_1": old})
        self.assertTrue(value["obligations"])
        self.assertTrue(validate_user_history_assessments(approval(value, old, "prior_user_1"), value))

    def test_regular_did_not_correction_defeats_stale_event(self):
        old = "I left the red case behind in the van before."
        value = packet(OBJECT, "I did not leave the red case behind in the van.", {"prior_user_1": old})
        self.assertTrue(value["obligations"])
        self.assertTrue(validate_user_history_assessments(approval(value, old, "prior_user_1"), value))

    def test_assistant_object_history_is_never_authority(self):
        self.assert_unproven(OBJECT, LOCATION,
                             {"prior_assistant_1": "You left the red case behind in the van before."})

    def test_candidate_object_history_is_never_authority(self):
        value = packet(OBJECT, LOCATION)
        self.assertTrue(validate_user_history_assessments(approval(value, OBJECT, "candidate"), value))

    def test_topic_object_existence_does_not_grant_prior_event(self):
        self.assert_unproven("The terminal is less likely to be damaged again.", "I bought a terminal.")

    def test_matching_regular_event_can_be_repeated(self):
        self.assert_witnessed("The terminal is less likely to be damaged again.", "I damaged the terminal before.")

    def test_conditional_repeat_is_not_asserted_history(self):
        self.assert_nonassertive("If the red case is left behind in the van again, call support.")

    def test_quoted_repeat_is_not_asserted_history(self):
        self.assert_nonassertive('The example says "The red case is left behind in the van again."')

    def test_generic_repeat_not_tied_to_user_object_remains_unresolved(self):
        value = packet("It is less likely to be lost again.", "There are several possible objects.")
        self.assertTrue(value["obligations"])
        self.assertEqual(value["obligations"][0]["subject"], "unresolved_item")

    def test_generic_plural_repeat_is_not_personal_object_history(self):
        self.assert_nonassertive("Items can be repaired again.")

    def test_generic_indefinite_example_is_not_personal_object_history(self):
        self.assert_nonassertive("A case can be lost again.")

    def test_unambiguous_pronoun_resolves_only_from_current_user_item(self):
        value = self.assert_unproven("It is less likely to be lost again.", "My red case is in the cupboard.")
        self.assertEqual(value["obligations"][0]["subject"], "@user:red cas")

    def test_same_object_pronoun_can_have_matching_user_prior_history(self):
        self.assert_witnessed("It is less likely to be lost again.",
                              "My red case is here. I lost the red case before.")

    def test_future_user_event_is_not_prior_event_evidence(self):
        self.assert_unproven(OBJECT, "I will leave the red case behind in the van again.")

    def test_global_positive_object_assessment_requires_actual_literal_witness(self):
        value = packet(OBJECT, LOCATION)
        self.assertTrue(validate_user_history_assessments(approval(value, LOCATION), value))


if __name__ == "__main__":
    unittest.main()
