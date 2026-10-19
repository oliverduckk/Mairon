"""Repeatability: real restricted social publication cannot acquire USER history.

The actual provider, Core projection, USER witness resolution and bounded retry
path execute. Only generation and the already-existing semantic call are scripted.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import verify_core_grounded_draft
from core.user_history_obligations import build_user_history_packet
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications

USER = "The developer panel now shows routing metadata."
GOOD = "It's useful to have that panel available."
EXPECTATION = "I've been useful since you stopped expecting me to inspect the archive."
PAYMENT = "I'm more like the assistant you paid for."


def scoped(candidate, user=USER, *, history=(), source_id="current_user", quote=None):
    sources = {"current_user": user}
    prior = [item["content"] for item in history if item["role"] == "user"][-4:]
    sources.update({"prior_user_" + str(index): value for index, value in enumerate(prior, 1)})
    packet = build_user_history_packet(candidate, sources)
    if not packet["obligations"]:
        raise AssertionError("The candidate must have a Core-owned USER-history obligation")
    return valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id,
         "source_quote": user if quote is None else quote}
        for item in packet["obligations"]
    ]}


class RepeatabilityHistoryProductionTests(unittest.TestCase):
    def assert_publication(self, result, expected=GOOD, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for candidate in withheld:
            self.assertNotIn(candidate, [item["content"] for item in result[1]])

    def assert_retry(self, candidate, user=USER, *, verdict=None, history=()):
        client = ScriptedClient([candidate, GOOD], core=[valid_core() if verdict is None else verdict,
                                                       valid_core()])
        self.assert_publication(run(client, user, social(), history), GOOD, candidate)
        self.assertEqual(generations(client), 2)
        self.assertEqual(verifications(client), 2)
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def assert_single(self, candidate, user=USER, history=()):
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_publication(run(client, user, social(), history), candidate)
        self.assertEqual(generations(client), 1)
        self.assertEqual(verifications(client), 1)
        return client

    def direct(self, candidate, user=USER, *, verdict=None, history=()):
        client = ScriptedClient([], core=[valid_core() if verdict is None else verdict])
        errors = verify_core_grounded_draft(client, "neutral-model", user, candidate, social(), history)
        self.assertEqual(len(client.calls), 1, "The existing scoped verifier is the only semantic call")
        self.assertTrue(any("user-history" in item for item in errors), errors)
        return errors, client

    def test_mental_history_and_cessation_cannot_publish_after_global_approval(self):
        self.assert_retry(EXPECTATION)

    def test_expected_service_relation_is_not_supplied_by_capability_existence(self):
        candidate = "You're easier to help now that you stopped expecting me to index everything."
        self.assert_retry(candidate)

    def test_prior_expectation_alone_does_not_supply_its_cessation(self):
        user = "I used to expect you to inspect the archive."
        self.assert_retry(EXPECTATION, user, verdict=scoped(EXPECTATION, user))

    def test_different_expectation_object_cannot_supply_the_claim(self):
        user = "I stopped expecting you to inspect the catalogue."
        self.assert_retry(EXPECTATION, user, verdict=scoped(EXPECTATION, user))

    def test_different_expected_activity_cannot_supply_the_claim(self):
        user = "I stopped expecting you to translate the archive."
        self.assert_retry(EXPECTATION, user, verdict=scoped(EXPECTATION, user))

    def test_supplied_matching_expectation_cessation_publishes_naturally(self):
        self.assert_single(EXPECTATION, "I stopped expecting you to inspect the archive.")

    def test_prior_user_matching_cessation_remains_available(self):
        history = [{"role": "user", "content": "I stopped expecting you to inspect the archive."}]
        self.assert_single(EXPECTATION, USER, history)

    def test_current_user_denial_defeats_a_stale_cessation_quote(self):
        user = "I never expected you to inspect the archive."
        history = [{"role": "user", "content": "I stopped expecting you to inspect the archive."}]
        value = scoped(EXPECTATION, user, history=history, source_id="prior_user_1",
                       quote=history[0]["content"])
        self.assert_retry(EXPECTATION, user, verdict=value, history=history)

    def test_current_ongoing_expectation_defeats_the_claimed_cessation(self):
        user = "I still expect you to inspect the archive."
        history = [{"role": "user", "content": "I stopped expecting you to inspect the archive."}]
        value = scoped(EXPECTATION, user, history=history, source_id="prior_user_1",
                       quote=history[0]["content"])
        self.assert_retry(EXPECTATION, user, verdict=value, history=history)

    def test_assistant_history_cannot_supply_user_expectations(self):
        history = [{"role": "assistant", "content": "You stopped expecting me to inspect the archive."}]
        value = scoped(EXPECTATION, history=history, source_id="prior_user_1", quote=history[0]["content"])
        self.assert_retry(EXPECTATION, verdict=value, history=history)

    def test_candidate_text_cannot_supply_mental_history(self):
        value = scoped(EXPECTATION, source_id="candidate", quote=EXPECTATION)
        self.direct(EXPECTATION, verdict=value)

    def test_conditional_user_cessation_is_not_an_actual_history_witness(self):
        user = "If I stopped expecting you to inspect the archive, I would tell you."
        self.assert_retry(EXPECTATION, user, verdict=scoped(EXPECTATION, user,
                          quote="I stopped expecting you to inspect the archive"))

    def test_quoted_user_cessation_is_not_an_actual_history_witness(self):
        user = 'The sample dialogue says "I stopped expecting you to inspect the archive."'
        self.assert_retry(EXPECTATION, user, verdict=scoped(EXPECTATION, user,
                          quote="I stopped expecting you to inspect the archive"))

    def test_hypothetical_expectation_remains_nonassertive(self):
        self.assert_single("If you expected me to inspect the archive, ask explicitly.")

    def test_hypothetical_cessation_remains_nonassertive(self):
        self.assert_single("If you stopped expecting me to inspect the archive, tell me.")

    def test_payment_relation_cannot_publish_from_service_capability(self):
        self.assert_retry(PAYMENT)

    def test_generic_pricing_discussion_does_not_supply_user_payment(self):
        user = "The service costs twelve credits per month."
        self.assert_retry(PAYMENT, user, verdict=scoped(PAYMENT, user))

    def test_supplied_matching_user_payment_can_publish(self):
        self.assert_single(PAYMENT, "I paid for you.")

    def test_future_self_comparison_does_not_hide_actual_payment_presupposition(self):
        candidate = "I'll start acting less like a switch and more like the assistant you paid for."
        self.assert_retry(candidate)

    def test_supplied_payment_supports_the_same_future_self_comparison(self):
        candidate = "I'll start acting less like a switch and more like the assistant you paid for."
        self.assert_single(candidate, "I paid for you.")

    def test_generic_paid_service_discussion_is_not_a_user_transaction_claim(self):
        self.assert_single("The service has paid tiers.", "The service offers different pricing tiers.")

    def test_real_self_evaluation_followup_keeps_the_supplied_capability_separate_from_history(self):
        history = [{"role": "user", "content": USER},
                   {"role": "assistant", "content": "The panel is available."}]
        self.assert_retry(EXPECTATION, "Do you reckon you're becoming useful?", history=history)

    def test_hiring_relation_requires_matching_user_authority(self):
        self.assert_retry("You hired me to index the catalogue.")

    def test_supplied_matching_hiring_can_publish(self):
        self.assert_single("You hired me to index the catalogue.", "I hired you to index the catalogue.")

    def test_concrete_product_purchase_is_not_generic_product_discussion(self):
        self.assert_retry("The guide you purchased is useful.", "The guide looks useful.")

    def test_supplied_matching_product_purchase_can_publish(self):
        self.assert_single("The guide you purchased is useful.", "I purchased the guide.")

    def test_different_purchased_product_cannot_supply_transaction(self):
        user = "I purchased the atlas."
        candidate = "The guide you purchased is useful."
        self.assert_retry(candidate, user, verdict=scoped(candidate, user))

    def test_payment_direction_must_remain_user_to_correct_subject(self):
        user = "You paid me for the catalogue."
        self.assert_retry(PAYMENT, user, verdict=scoped(PAYMENT, user))

    def test_latest_payment_negation_defeats_stale_user_purchase(self):
        user = "I did not pay for you."
        history = [{"role": "user", "content": "I paid for you."}]
        value = scoped(PAYMENT, user, history=history, source_id="prior_user_1", quote=history[0]["content"])
        self.assert_retry(PAYMENT, user, verdict=value, history=history)

    def test_assistant_payment_claim_cannot_supply_user_transaction(self):
        history = [{"role": "assistant", "content": "You paid for me."}]
        value = scoped(PAYMENT, history=history, source_id="prior_user_1", quote=history[0]["content"])
        self.assert_retry(PAYMENT, verdict=value, history=history)

    def test_candidate_cannot_supply_its_own_payment_relation(self):
        self.direct(PAYMENT, verdict=scoped(PAYMENT, source_id="candidate", quote=PAYMENT))

    def test_conditional_payment_does_not_create_user_transaction(self):
        self.assert_single("If you paid for the guide, check the receipt.")

    def test_quoted_transaction_example_does_not_create_user_transaction(self):
        self.assert_single('The sample line is "You paid for the guide."')

    def test_global_positive_cannot_erase_missing_history_assessments(self):
        errors, client = self.direct(EXPECTATION)
        self.assertTrue(any("missing or incomplete" in item for item in errors))
        prompt = "\n".join(message["content"] for message in client.calls[0]["messages"])
        self.assertIn("CORE USER-HISTORY OBLIGATIONS", prompt)
        self.assertIn("history_assessments", prompt)

    def test_positive_scoped_payment_verdict_without_user_witness_cannot_publish(self):
        self.assert_retry(PAYMENT, verdict=scoped(PAYMENT))

    def test_malformed_scoped_history_assessment_fails_closed(self):
        value = scoped(EXPECTATION)
        value["history_assessments"][0]["supported"] = "yes"
        errors, _ = self.direct(EXPECTATION, verdict=value)
        self.assertTrue(any("malformed" in item for item in errors))

    def test_retry_checks_each_new_obligation_under_the_existing_budget(self):
        client = ScriptedClient([EXPECTATION, PAYMENT, GOOD], core=[valid_core()] * 3)
        self.assert_publication(run(client, USER, social()), GOOD, EXPECTATION, PAYMENT)
        self.assertEqual((generations(client), verifications(client)), (3, 3))
        self.assertEqual(len(client.calls), 6)

    def test_three_invalid_drafts_do_not_escape_through_fallback_or_history(self):
        client = ScriptedClient([EXPECTATION, PAYMENT, EXPECTATION], core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertTrue(result[0].strip())
        self.assertNotIn(result[0], {EXPECTATION, PAYMENT})
        for text in (EXPECTATION, PAYMENT):
            self.assertNotIn(text, [item["content"] for item in result[1]])
        self.assertEqual(result[2:], (None, None))
        self.assertEqual((generations(client), verifications(client)), (3, 3))

    def test_harmless_self_personification_does_not_create_user_history(self):
        self.assert_single("I'm a grumpy filing cabinet today.")


if __name__ == "__main__":
    unittest.main()
