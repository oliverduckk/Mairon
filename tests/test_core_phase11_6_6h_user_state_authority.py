"""Core owns implicit social USER activities; prose cannot supply them."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.user_history_obligations import (
    build_user_history_packet, detect_user_history, validate_user_history_assessments,
)


TOPIC = "The shipment arrived."
WHILE = "You're efficient while using the tablet."
STOP = "Stop indexing the ledger."


def packet(candidate=WHILE, user=TOPIC, extra=None):
    return build_user_history_packet(candidate, {"current_user": user} | (extra or {}))


def positive(value, quote=TOPIC, source_id="current_user"):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class ImmediateUserStateAuthorityTests(unittest.TestCase):
    def assert_unproven(self, candidate=WHILE, user=TOPIC, extra=None):
        value = packet(candidate, user, extra)
        self.assertTrue(value["obligations"], candidate)
        self.assertTrue(validate_user_history_assessments(positive(value, user), value), candidate)
        return value

    def assert_witnessed(self, candidate=WHILE, user="I'm using the tablet.", extra=None):
        value = packet(candidate, user, extra)
        self.assertFalse(value["obligations"], candidate)
        self.assertTrue(value["core_witnessed"], candidate)
        return value

    def assert_nonassertive(self, candidate):
        value = packet(candidate)
        self.assertFalse(value["obligations"], candidate)
        self.assertFalse(value["core_witnessed"], candidate)

    def test_while_understood_subject_is_current_activity(self):
        value = self.assert_unproven()
        self.assertEqual(value["obligations"][0]["kind"], "current_activity_state")
        self.assertEqual(value["obligations"][0]["activity_key"], ("us", "tablet"))
        self.assertEqual(value["obligations"][0]["state_temporal"], "current")

    def test_matching_user_progressive_supports_while(self):
        self.assert_witnessed()

    def test_different_object_cannot_supply_while(self):
        self.assert_unproven(user="I'm using the terminal.")

    def test_different_activity_cannot_supply_while(self):
        self.assert_unproven(user="I'm repairing the tablet.")

    def test_device_possession_is_not_usage(self):
        self.assert_unproven(user="My tablet is on the desk.")

    def test_negative_user_activity_does_not_supply_positive(self):
        self.assert_unproven(user="I'm not using the tablet.")

    def test_matching_negative_subordinate_is_preserved(self):
        self.assert_witnessed("You're efficient while not using the tablet.", "I'm not using the tablet.")

    def test_positive_user_activity_does_not_supply_negative(self):
        self.assert_unproven("You're efficient while not using the tablet.", "I'm using the tablet.")

    def test_latest_negative_defeats_older_matching_activity(self):
        value = self.assert_unproven(user="I'm not using the tablet.",
                                    extra={"prior_user_1": "I'm using the tablet."})
        errors = validate_user_history_assessments(positive(value, "I'm using the tablet.", "prior_user_1"), value)
        self.assertTrue(any("latest" in error for error in errors))

    def test_latest_no_longer_defeats_older_activity(self):
        self.assert_unproven(user="I'm no longer using the tablet.",
                             extra={"prior_user_1": "I'm using the tablet."})

    def test_latest_positive_replaces_older_negative(self):
        self.assert_witnessed(extra={"prior_user_1": "I'm not using the tablet."})

    def test_latest_same_turn_correction_wins(self):
        self.assert_unproven(user="I'm using the tablet. I'm not using the tablet now.")

    def test_past_activity_is_not_current_usage(self):
        self.assert_unproven(user="I was using the tablet.")

    def test_future_activity_is_not_current_usage(self):
        self.assert_unproven(user="I will be using the tablet.")

    def test_assistant_history_is_not_a_source(self):
        self.assert_unproven(extra={"prior_assistant_1": "I'm using the tablet."})

    def test_candidate_prose_is_not_a_source(self):
        self.assert_unproven(extra={"candidate": "I'm using the tablet."})

    def test_user_instruction_to_mairon_does_not_supply_user_activity(self):
        self.assert_unproven(STOP, "Stop indexing the ledger.")

    def test_user_waiting_for_mairon_does_not_supply_user_activity(self):
        self.assert_unproven(STOP, "I'm waiting for you to stop indexing the ledger.")

    def test_current_user_to_assistant_argument_is_perspective_normalised(self):
        self.assert_witnessed("Quit staring at me.", "I'm staring at you.")

    def test_a_different_participant_does_not_create_user_activity(self):
        self.assert_nonassertive("I am efficient while using the tablet.")

    def test_an_object_you_does_not_own_a_participle(self):
        self.assert_nonassertive("I told you about the ledger while indexing the cabinet.")

    def test_preposed_participle_and_main_predicate_are_separate(self):
        candidate = "While indexing the ledger, you're using the tablet."
        value = self.assert_witnessed(candidate, "I'm indexing the ledger while using the tablet.")
        self.assertEqual({item["activity_key"] for item in value["core_witnessed"]},
                         {("index", "ledger"), ("us", "tablet")})

    def test_preposed_participle_cannot_borrow_only_main_activity(self):
        self.assert_unproven("While indexing the ledger, you're using the tablet.", "I'm using the tablet.")

    def test_main_activity_cannot_borrow_only_preposed_predicate(self):
        self.assert_unproven("While indexing the ledger, you're using the tablet.", "I'm indexing the ledger.")

    def test_listener_someone_attribution_requires_current_activity(self):
        self.assert_unproven("That is impressive for someone currently using the old terminal.")

    def test_listener_someone_attribution_matching_user_is_preserved(self):
        self.assert_witnessed("That's impressive for someone currently using the old terminal.",
                              "I'm using the old terminal.")

    def test_third_party_someone_attribution_does_not_become_user(self):
        self.assert_nonassertive("Avery is impressive for someone currently using the old terminal.")

    def test_conversational_suppose_does_not_hide_current_subordinate(self):
        self.assert_unproven("I suppose that means you can stop sorting files while using the tablet.")

    def test_conversational_suppose_matching_both_activities_is_preserved(self):
        self.assert_witnessed("I suppose that means you can stop sorting files while using the tablet.",
                              "I'm sorting files while using the tablet.")

    def test_cessation_and_subordinate_have_independent_user_identity(self):
        self.assert_unproven("You can stop sorting files while using the tablet.", "I'm using the tablet.")

    def test_purpose_tail_cannot_hide_unsupplied_usage(self):
        value = self.assert_unproven(
            "I suppose that means you can stop sorting files while using the tablet to inspect the ledger.",
            "I'm sorting files.")
        self.assertIn(("us", "tablet"), [item["activity_key"] for item in value["obligations"]])

    def test_matching_current_usage_supports_bounded_purpose_head(self):
        self.assert_witnessed("You're efficient while using the tablet to inspect the ledger.")

    def test_infinitival_attitude_is_not_projected_as_concrete_usage(self):
        self.assert_nonassertive("Stop pretending to be efficient.")

    def test_hypothetical_purpose_tail_does_not_create_usage(self):
        self.assert_nonassertive("You could work while using the tablet to inspect the ledger.")

    def test_bare_cessation_has_a_current_premise(self):
        value = self.assert_unproven(STOP)
        self.assertEqual(value["obligations"][0]["activity_key"], ("index", "ledger"))
        self.assertEqual(value["obligations"][0]["mode"], "presupposed")

    def test_matching_current_user_supports_bare_cessation(self):
        self.assert_witnessed(STOP, "I'm indexing the ledger.")

    def test_quit_alternate_activity_has_same_current_requirement(self):
        self.assert_unproven("Quit cataloguing the cabinet.")

    def test_quit_matching_activity_is_preserved(self):
        self.assert_witnessed("Quit cataloguing the cabinet.", "I'm cataloguing the cabinet.")

    def test_waiting_for_you_cessation_has_a_current_premise(self):
        self.assert_unproven("I'm waiting for you to stop indexing the ledger.")

    def test_outer_future_wait_does_not_hide_the_cessation_premise(self):
        self.assert_unproven("I'll wait for you to stop indexing the ledger.")

    def test_waiting_cessation_matching_user_can_pass(self):
        self.assert_witnessed("I'll wait for you to stop indexing the ledger.", "I'm indexing the ledger.")

    def test_current_negative_correction_blocks_bare_cessation(self):
        self.assert_unproven(STOP, "I'm not indexing the ledger.",
                             {"prior_user_1": "I'm indexing the ledger."})

    def test_different_object_blocks_bare_cessation(self):
        self.assert_unproven(STOP, "I'm indexing the atlas.")

    def test_different_activity_blocks_bare_cessation(self):
        self.assert_unproven(STOP, "I'm carrying the ledger.")

    def test_existing_current_concern_cessation_is_preserved(self):
        value = self.assert_witnessed("You can stop worrying about the parcel now.",
                                      "I'm worried about the parcel.")
        self.assertEqual(value["core_witnessed"][0]["kind"], "mental_state_presupposition")

    def test_anticipation_is_not_concern_evidence(self):
        self.assert_unproven("You can stop worrying about the parcel now.", "The parcel finally arrived.")

    def test_if_current_activity_remains_nonassertive(self):
        self.assert_nonassertive("If you're using the tablet, check the port.")

    def test_hypothetical_while_frame_remains_nonassertive(self):
        self.assert_nonassertive("You could use the tablet while travelling.")

    def test_can_advice_does_not_create_current_usage(self):
        self.assert_nonassertive("You can work while using the terminal.")

    def test_preposed_advice_does_not_create_current_activity(self):
        self.assert_nonassertive("While indexing the ledger, you could use the tablet.")

    def test_if_cessation_remains_nonassertive(self):
        self.assert_nonassertive("If you stop indexing the ledger, check the labels.")

    def test_hypothetical_cessation_imperative_remains_nonassertive(self):
        self.assert_nonassertive("Stop indexing the ledger if the port fails.")

    def test_plain_transition_question_remains_a_question(self):
        self.assert_nonassertive("Did you stop indexing the ledger?")

    def test_ordinary_activity_question_does_not_assert_state(self):
        self.assert_nonassertive("Are you using the tablet?")

    def test_quoted_cessation_remains_nonassertive(self):
        self.assert_nonassertive('The example is "Stop indexing the ledger."')

    def test_quote_delimiter_from_earlier_clause_is_retained(self):
        self.assert_nonassertive('The example says "Hello. Stop indexing the ledger."')

    def test_quoted_while_remains_nonassertive(self):
        self.assert_nonassertive('The sample says "You are efficient while using the tablet."')

    def test_generic_compound_instruction_remains_nonassertive(self):
        self.assert_nonassertive("Stop filing cards carelessly and check their labels.")

    def test_real_suppose_hypothesis_remains_nonassertive(self):
        self.assert_nonassertive("Suppose you can stop sorting files while using the tablet.")

    def test_explicitly_nonliteral_activity_remains_nonassertive(self):
        self.assert_nonassertive("Stop wrestling cosmic dragons metaphorically.")

    def test_object_personification_remains_nonassertive(self):
        self.assert_nonassertive("Your compiler is begging for mercy.")

    def test_historical_duration_interim_transport_is_preserved(self):
        value = self.assert_witnessed("Stop pretending to be efficient while using a stylus for four days.",
                                      "I've been using a stylus for four days.")
        self.assertEqual(value["core_witnessed"][0]["kind"], "interim_activity")

    def test_positive_global_without_scoped_assessment_fails_closed(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments({"supported": True}, value))

    def test_positive_global_with_false_scoped_assessment_fails_closed(self):
        value = packet()
        checks = positive(value)
        checks["history_assessments"][0]["supported"] = False
        self.assertTrue(validate_user_history_assessments(checks, value))

    def test_malformed_scoped_assessment_fails_closed(self):
        value = packet()
        for malformed in (None, {}, [], [True], [{"index": "1", "supported": True}],
                          [{"index": 1, "supported": "true"}]):
            with self.subTest(malformed=malformed):
                self.assertTrue(validate_user_history_assessments(
                    {"supported": True, "history_assessments": malformed}, value))

    def test_truncated_quote_cannot_erase_user_conditional_scope(self):
        value = self.assert_unproven(user="If I'm using the tablet, I'll tell you.")
        self.assertTrue(validate_user_history_assessments(positive(value, "I'm using the tablet"), value))

    def test_each_new_candidate_gets_its_own_activity_obligation(self):
        first = self.assert_unproven()
        second = self.assert_unproven("You're efficient while repairing the cabinet.")
        self.assertNotEqual(first["obligations"][0]["activity_key"], second["obligations"][0]["activity_key"])


if __name__ == "__main__":
    unittest.main()
