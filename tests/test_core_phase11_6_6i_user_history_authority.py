"""Actual USER mental transitions and transactions need matching USER history."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.user_history_obligations import (
    build_user_history_packet, detect_user_history, validate_user_history_assessments,
)

TOPIC = "The diagnostic panel now shows model metadata."
CEASED = "I've been useful since you stopped expecting me to inspect the archive."
PAID = "I'm more like the assistant you paid for."


def packet(candidate=CEASED, user=TOPIC, extra=None):
    return build_user_history_packet(candidate, {"current_user": user} | (extra or {}))


def positive(value, quote=TOPIC, source_id="current_user"):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class RelationshipHistoryAuthorityTests(unittest.TestCase):
    def assert_unproven(self, candidate=CEASED, user=TOPIC, extra=None):
        value = packet(candidate, user, extra)
        self.assertTrue(value["obligations"], candidate)
        self.assertTrue(validate_user_history_assessments(positive(value, user), value), candidate)
        return value

    def assert_witnessed(self, candidate=CEASED, user="I stopped expecting you to inspect the archive.", extra=None):
        value = packet(candidate, user, extra)
        self.assertFalse(value["obligations"], candidate)
        self.assertTrue(value["core_witnessed"], candidate)
        return value

    def assert_nonassertive(self, candidate):
        value = packet(candidate)
        self.assertFalse(value["obligations"], candidate)
        self.assertFalse(value["core_witnessed"], candidate)

    def test_since_cessation_projects_prior_premise_and_completed_change(self):
        value = self.assert_unproven()
        self.assertEqual({item["kind"] for item in value["obligations"]}, {"expectation_state", "expectation_cessation"})
        self.assertEqual({item["relation_temporal"] for item in value["obligations"]}, {"prior", "completed"})

    def test_explicit_user_cessation_supplies_both(self):
        self.assert_witnessed()

    def test_prior_expectation_alone_does_not_establish_cessation(self):
        value = self.assert_unproven(user="I used to expect you to inspect the archive.")
        self.assertEqual([item["kind"] for item in value["obligations"]], ["expectation_cessation"])

    def test_current_expectation_does_not_establish_prior_cessation(self):
        self.assert_unproven(user="I expect you to inspect the archive.")

    def test_current_nonexpectation_does_not_establish_cessation(self):
        self.assert_unproven(user="I don't expect you to inspect the archive.")

    def test_different_expected_action_cannot_supply_premise(self):
        self.assert_unproven(user="I stopped expecting you to amend the archive.")

    def test_different_expected_object_cannot_supply_premise(self):
        self.assert_unproven(user="I stopped expecting you to inspect the ledger.")

    def test_expectation_participant_direction_is_normalised(self):
        self.assert_witnessed("You expected me to inspect the archive.", "I expected you to inspect the archive.")

    def test_reversed_expectation_direction_is_not_user_history(self):
        self.assert_unproven(user="You stopped expecting me to inspect the archive.")

    def test_embedded_future_consequence_does_not_hide_completed_premise(self):
        self.assert_unproven("I'll be useful now that you stopped expecting me to inspect the archive.")

    def test_present_consequence_does_not_hide_after_premise(self):
        self.assert_unproven("I'm useful after you stopped expecting me to inspect the archive.")

    def test_conditional_cessation_remains_nonassertive(self):
        self.assert_nonassertive("If you stopped expecting me to inspect the archive, I could help.")

    def test_hypothetical_expectation_remains_nonassertive(self):
        self.assert_nonassertive("If you expected me to inspect the archive, that would be a separate task.")

    def test_plain_expectation_question_is_nonassertive(self):
        self.assert_nonassertive("Did you expect me to inspect the archive?")

    def test_quoted_cessation_is_not_actual_user_history(self):
        self.assert_nonassertive('The example says "you stopped expecting me to inspect the archive".')

    def test_future_cessation_does_not_supply_completed_change(self):
        self.assert_unproven(user="I will stop expecting you to inspect the archive.")

    def test_assistant_claim_is_not_user_authority(self):
        self.assert_unproven(extra={"prior_assistant_1": "I stopped expecting you to inspect the archive."})

    def test_candidate_claim_is_not_user_authority(self):
        self.assert_unproven(extra={"candidate": "I stopped expecting you to inspect the archive."})

    def test_latest_never_expected_defeats_prior_premise(self):
        self.assert_unproven(user="I never expected you to inspect the archive.",
                             extra={"prior_user_1": "I stopped expecting you to inspect the archive."})

    def test_latest_never_stopped_defeats_completed_change(self):
        self.assert_unproven(user="I never stopped expecting you to inspect the archive.",
                             extra={"prior_user_1": "I stopped expecting you to inspect the archive."})

    def test_latest_still_expecting_defeats_stale_cessation(self):
        self.assert_unproven(user="I still expect you to inspect the archive.",
                             extra={"prior_user_1": "I stopped expecting you to inspect the archive."})

    def test_latest_supplied_cessation_overrides_old_denial(self):
        self.assert_witnessed(extra={"prior_user_1": "I never stopped expecting you to inspect the archive."})

    def test_latest_different_topic_does_not_erase_matching_history(self):
        self.assert_witnessed(user="I expect you to update the ledger.",
                              extra={"prior_user_1": "I stopped expecting you to inspect the archive."})

    def test_current_negative_does_not_erase_distinct_prior_state(self):
        self.assert_witnessed("You expected me to inspect the archive.", "I don't expect you to inspect the archive.",
                              {"prior_user_1": "I expected you to inspect the archive."})

    def test_negated_expected_content_cannot_supply_affirmative_content(self):
        self.assert_unproven(user="I stopped expecting you not to inspect the archive.")

    def test_expected_modal_content_remains_distinct(self):
        self.assert_unproven("You expected me to inspect the archive.", "I expected you could inspect the archive.")

    def test_expected_future_topic_is_not_outer_future_scope(self):
        self.assert_witnessed("You expected me to inspect the archive tomorrow.", "I expected you to inspect the archive tomorrow.")

    def test_global_positive_cannot_erase_mental_obligations(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments({"supported": True}, value))

    def test_missing_one_mental_assessment_fails_closed(self):
        value = packet()
        parsed = positive(value)
        parsed["history_assessments"].pop()
        self.assertTrue(validate_user_history_assessments(parsed, value))

    def test_malformed_mental_assessment_fails_closed(self):
        value = packet()
        parsed = positive(value)
        parsed["history_assessments"][0]["supported"] = "true"
        self.assertTrue(validate_user_history_assessments(parsed, value))

    def test_forged_mental_quote_cannot_supply_history(self):
        value = packet()
        self.assertTrue(validate_user_history_assessments(positive(value, "I stopped expecting you to inspect the archive."), value))

    def test_self_relative_payment_requires_user_history(self):
        value = self.assert_unproven(PAID)
        self.assertEqual(value["obligations"][0]["relation_key"], ("for", "@assistant"))

    def test_user_payment_for_assistant_supports_self_relative(self):
        self.assert_witnessed(PAID, "I paid for you.")

    def test_outer_future_selfcomparison_does_not_hide_actual_payment_relative(self):
        self.assert_unproven("Maybe I'll start acting less like a switch and more like the assistant you paid for.")

    def test_user_payment_supports_bounded_future_selfcomparison(self):
        self.assert_witnessed("Maybe I'll start acting less like a switch and more like the assistant you paid for.", "I paid for you.")

    def test_outer_future_does_not_hide_a_separate_object_purchase(self):
        self.assert_unproven("I'll inspect the guide you purchased.")

    def test_simple_past_payment_is_projected(self):
        self.assert_unproven("You paid for the indexer.")

    def test_present_payment_is_not_completed_payment(self):
        self.assert_unproven(PAID, "I pay for you.")

    def test_matching_direct_payment_passes(self):
        self.assert_witnessed("You paid for the indexer.", "I paid for the indexer.")

    def test_different_paid_object_does_not_supply_purchase(self):
        self.assert_unproven("You paid for the indexer.", "I paid for the scanner.")

    def test_paid_to_and_paid_for_are_distinct(self):
        self.assert_unproven("You paid me.", "I paid for you.")

    def test_reverse_payment_direction_fails(self):
        self.assert_unproven("You paid me.", "You paid me.")

    def test_assistant_paid_user_requires_user_authorship(self):
        self.assert_unproven("I paid you.")

    def test_assistant_paid_user_can_be_user_supplied(self):
        self.assert_witnessed("I paid you.", "You paid me.")

    def test_bought_object_is_exact(self):
        self.assert_witnessed("You bought the indexer.", "I bought the indexer.")

    def test_bought_and_rented_are_not_aliases(self):
        self.assert_unproven("You bought the indexer.", "I rented the indexer.")

    def test_noun_relative_purchase_matches_direct_user_purchase(self):
        self.assert_witnessed("The guide you purchased is useful.", "I purchased the guide.")

    def test_noun_relative_wrong_object_fails(self):
        self.assert_unproven("The guide you purchased is useful.", "I purchased the atlas.")

    def test_hiring_matches_direction_and_work(self):
        self.assert_witnessed("You hired me to index the catalogue.", "I hired you to index the catalogue.")

    def test_hiring_different_work_fails(self):
        self.assert_unproven("You hired me to index the catalogue.", "I hired you to repair the catalogue.")

    def test_subscription_matches_same_subject(self):
        self.assert_witnessed("You subscribed to the archive service.", "I subscribed to the archive service.")

    def test_subscription_different_subject_fails(self):
        self.assert_unproven("You subscribed to the archive service.", "I subscribed to the registry service.")

    def test_generic_pricing_does_not_supply_user_transaction(self):
        self.assert_unproven(PAID, "The assistant service costs eight credits per cycle.")

    def test_generic_product_discussion_does_not_supply_purchase(self):
        self.assert_unproven("You bought the indexer.", "The indexer is available to purchase.")

    def test_generic_customer_pricing_is_not_personal_history(self):
        self.assert_nonassertive("Customers pay for the indexer.")

    def test_conditional_payment_is_nonassertive(self):
        self.assert_nonassertive("If you paid for the indexer, keep the receipt.")

    def test_hypothetical_hiring_is_nonassertive(self):
        self.assert_nonassertive("If you hired me to index the archive, I'd need the files.")

    def test_plain_payment_question_is_nonassertive(self):
        self.assert_nonassertive("Have you paid for the indexer?")

    def test_future_payment_not_completed_history(self):
        self.assert_unproven("You paid for the indexer.", "I will pay for the indexer.")

    def test_quoted_payment_cannot_supply_history(self):
        self.assert_unproven(PAID, 'The example is "I paid for you".')

    def test_conditional_user_payment_cannot_supply_history(self):
        self.assert_unproven(PAID, "If I paid for you, I'd keep the receipt.")

    def test_assistant_payment_prose_is_not_evidence(self):
        self.assert_unproven(PAID, extra={"prior_assistant_1": "I paid for you."})

    def test_candidate_payment_prose_is_not_evidence(self):
        self.assert_unproven(PAID, extra={"candidate": "I paid for you."})

    def test_latest_payment_negation_overrides_older_positive(self):
        self.assert_unproven(PAID, "I did not pay for you.", {"prior_user_1": "I paid for you."})

    def test_latest_purchase_negation_same_turn_wins(self):
        self.assert_unproven("You bought the indexer.", "I bought the indexer. I did not buy the indexer.")

    def test_latest_subscription_correction_overrides_old_positive(self):
        self.assert_unproven("You subscribed to the archive service.", "I never subscribed to the archive service.",
                             {"prior_user_1": "I subscribed to the archive service."})

    def test_latest_positive_payment_overrides_old_negative(self):
        self.assert_witnessed(PAID, "I paid for you.", {"prior_user_1": "I never paid for you."})

    def test_different_payment_correction_does_not_erase_matching_history(self):
        self.assert_witnessed(PAID, "I did not pay for the indexer.", {"prior_user_1": "I paid for you."})

    def test_global_positive_cannot_erase_transaction_obligation(self):
        value = packet(PAID)
        self.assertTrue(validate_user_history_assessments({"supported": True}, value))

    def test_forged_old_payment_quote_rejected_by_latest_correction(self):
        value = packet(PAID, "I never paid for you.", {"prior_user_1": "I paid for you."})
        errors = validate_user_history_assessments(positive(value, "I paid for you.", "prior_user_1"), value)
        self.assertTrue(any("latest" in error for error in errors))

    def test_ordinary_nonliteral_object_personification_remains_unprojected(self):
        self.assert_nonassertive("The compiler has hired chaos as its consultant.")

    def test_natural_nontransactional_banter_remains_unprojected(self):
        self.assert_nonassertive("Useful? My ego is already polishing its trophy.")


if __name__ == "__main__":
    unittest.main()
