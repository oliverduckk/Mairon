"""A modal record or current noun-relative cannot acquire USER behaviour."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.user_history_obligations import (
    build_user_history_packet, detect_user_history, validate_user_history_assessments,
)


TOPIC = "I prefer detailed manuals over short summaries."
RELATIVE = "That particular handbook you're currently stuck in."
RECORD = "That's a new record for how long you can stare at a bare cabinet while pretending to be efficient."


def packet(candidate=RELATIVE, user=TOPIC, extra=None):
    return build_user_history_packet(candidate, {"current_user": user} | (extra or {}))


def positive(value, quote=TOPIC, source_id="current_user"):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class CurrentActivityAuthorityTests(unittest.TestCase):
    def assert_unproven(self, candidate=RELATIVE, user=TOPIC, extra=None):
        value = packet(candidate, user, extra)
        self.assertTrue(value["obligations"], candidate)
        self.assertTrue(validate_user_history_assessments(positive(value, user), value), candidate)
        return value

    def assert_witnessed(self, candidate=RELATIVE, user="I'm stuck in the handbook.", extra=None):
        value = packet(candidate, user, extra)
        self.assertFalse(value["obligations"], candidate)
        self.assertTrue(value["core_witnessed"], candidate)
        return value

    def assert_no_assertion(self, candidate):
        value = packet(candidate)
        self.assertFalse(value["obligations"], candidate)
        self.assertFalse(value["core_witnessed"], candidate)

    def test_deictic_relative_current_state_has_core_obligation(self):
        value = self.assert_unproven()
        self.assertEqual(value["obligations"][0]["kind"], "current_activity_state")
        self.assertEqual(value["obligations"][0]["activity_key"], ("stuck", "in", "handbook"))

    def test_an_outer_future_does_not_hide_current_relative(self):
        self.assert_unproven("I won't analyse that particular handbook you're currently stuck in.")

    def test_markdown_emphasis_does_not_hide_current_relative(self):
        self.assert_unproven("I won't analyse *that* particular handbook you're currently stuck in.")

    def test_definite_relative_present_activity_requires_authority(self):
        self.assert_unproven("The ledger you're indexing needs patience.")

    def test_explicit_current_direct_predicate_requires_authority(self):
        self.assert_unproven("You're currently indexing the ledger.")

    def test_current_state_does_not_require_perfect_or_past_tense(self):
        self.assert_unproven("You are currently busy with the ledger.")

    def test_topic_does_not_establish_an_actual_current_item(self):
        self.assert_unproven(RELATIVE, "Dense handbooks can be better than concise ones.")

    def test_user_owned_current_activity_can_be_restated(self):
        self.assert_witnessed("The ledger you're currently indexing.", "I'm indexing my ledger.")

    def test_user_matching_current_state_is_preserved(self):
        self.assert_witnessed()

    def test_direct_explicit_current_restatement_is_preserved(self):
        self.assert_witnessed("You are currently indexing the ledger.", "I'm indexing the ledger.")

    def test_current_predicate_does_not_supply_a_different_object(self):
        self.assert_unproven(RELATIVE, "I'm stuck in the atlas.")

    def test_current_object_does_not_supply_a_different_predicate(self):
        self.assert_unproven(RELATIVE, "I'm cataloguing the handbook.")

    def test_current_negative_does_not_support_a_positive_predicate(self):
        self.assert_unproven(RELATIVE, "I am not stuck in the handbook.")

    def test_prior_current_state_does_not_override_latest_negative(self):
        value = self.assert_unproven(RELATIVE, "I am not stuck in the handbook.",
                                    {"prior_user_1": "I am stuck in the handbook."})
        forged = positive(value, "I am stuck in the handbook.", "prior_user_1")
        self.assertTrue(any("latest" in item for item in validate_user_history_assessments(forged, value)))

    def test_latest_positive_can_replace_prior_negative(self):
        self.assert_witnessed(RELATIVE, "I am stuck in the handbook.",
                              {"prior_user_1": "I am not stuck in the handbook."})

    def test_latest_no_longer_correction_overrides_prior_state(self):
        self.assert_unproven(RELATIVE, "I'm no longer stuck in the handbook.",
                             {"prior_user_1": "I'm stuck in the handbook."})

    def test_past_activity_does_not_supply_current_state(self):
        self.assert_unproven(RELATIVE, "I was stuck in the handbook.")

    def test_assistant_history_cannot_create_current_state(self):
        self.assert_unproven(extra={"prior_assistant_1": "I am stuck in the handbook."})

    def test_candidate_text_cannot_create_current_state(self):
        self.assert_unproven(extra={"candidate": "I am stuck in the handbook."})

    def test_quote_cannot_strip_if_scope_from_user_evidence(self):
        value = packet(RELATIVE, "If I am stuck in the handbook, I'll ask.")
        self.assertTrue(value["obligations"])
        forged = positive(value, "I am stuck in the handbook")
        self.assertTrue(validate_user_history_assessments(forged, value))

    def test_conditional_current_state_remains_nonassertive(self):
        self.assert_no_assertion("If you're currently stuck in the handbook, take a break.")

    def test_conditional_relative_current_state_remains_nonassertive(self):
        self.assert_no_assertion("If that handbook you're currently stuck in is too dense, ask.")

    def test_might_current_state_remains_nonassertive(self):
        self.assert_no_assertion("You are currently maybe busy with the ledger.")

    def test_perhaps_current_state_remains_nonassertive(self):
        self.assert_no_assertion("Perhaps you're currently stuck in the handbook.")

    def test_plain_current_activity_question_is_not_a_statement(self):
        self.assert_no_assertion("Are you currently indexing the ledger?")

    def test_plain_generic_can_advice_does_not_acquire_history(self):
        self.assert_no_assertion("You can stare at a cabinet if that helps.")

    def test_object_personification_does_not_acquire_user_current_state(self):
        self.assert_no_assertion("Your ledger is begging for mercy.")

    def test_self_personification_does_not_acquire_user_current_state(self):
        self.assert_no_assertion("I'm a furious filing cabinet.")

    def test_modal_record_projects_actual_personal_activity(self):
        value = self.assert_unproven(RECORD, "I haven't indexed in four days.")
        self.assertEqual(value["obligations"][0]["kind"], "personal_activity_record")
        self.assertEqual(value["obligations"][0]["record_type"], ("new",))

    def test_a_record_does_not_borrow_an_unrelated_lapse(self):
        self.assert_unproven(RECORD, "I have not cooked in four days.")

    def test_actual_activity_does_not_establish_a_new_record(self):
        self.assert_unproven(RECORD, "I've been staring at a bare cabinet while pretending to be efficient.")

    def test_explicit_user_record_can_be_restated(self):
        self.assert_witnessed(RECORD, "That's a new record for how long I can stare at a bare cabinet while pretending to be efficient.")

    def test_record_identity_retains_the_specific_activity(self):
        self.assert_unproven(RECORD, "That's a new record for how long I can inspect the ledger.")

    def test_record_identity_retains_newness(self):
        self.assert_unproven(RECORD, "That's a previous record for how long I can stare at a bare cabinet while pretending to be efficient.")

    def test_negated_record_does_not_supply_positive_record(self):
        self.assert_unproven(RECORD, "That's not a new record for how long I can stare at a bare cabinet while pretending to be efficient.")

    def test_generic_duration_capability_question_is_not_a_record(self):
        self.assert_no_assertion("How long can you stare at a cabinet?")

    def test_if_record_is_hypothetical(self):
        self.assert_no_assertion("If that's a new record for how long you can inspect a ledger, celebrate.")

    def test_perhaps_record_remains_nonassertive(self):
        self.assert_no_assertion("Perhaps that's a new record for how long you can inspect a ledger.")

    def test_global_positive_cannot_erase_new_core_obligation(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments({"supported": True}, value))

    def test_none_classification_cannot_erase_new_core_obligation(self):
        value = packet()
        result = positive(value)
        for item in result["history_assessments"]:
            item["kind"] = "none"
        self.assertTrue(validate_user_history_assessments(result, value))

    def test_malformed_scoped_assessment_fails_closed(self):
        value = packet()
        result = positive(value)
        result["history_assessments"][0]["supported"] = "true"
        self.assertTrue(validate_user_history_assessments(result, value))

    def test_missing_scoped_assessment_fails_closed(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments({"history_assessments": []}, value))


if __name__ == "__main__":
    unittest.main()
