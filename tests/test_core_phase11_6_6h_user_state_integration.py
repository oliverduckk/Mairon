"""Real restricted-social publication checks implied USER current activity.

Only model responses are scripted.  The existing provider, history projection,
USER-source witness checks, scoped verifier aggregation and retry bound execute.
An ordinary global model approval cannot erase a Core-owned obligation.
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


USER = "The archive crates arrived."
GOOD = "Right, got you."
SUBORDINATE = "You're efficient while using the tablet."
CESSATION = "Stop indexing the ledger."


def packet(candidate, user=USER, conversation=()):
    sources = {"current_user": user}
    prior = [item["content"] for item in conversation if item["role"] == "user"][-4:]
    sources.update({"prior_user_" + str(index): value
                    for index, value in enumerate(prior, 1)})
    return build_user_history_packet(candidate, sources)


def positive_scoped(candidate, user=USER, *, conversation=(), source_id="current_user", quote=None):
    value = packet(candidate, user, conversation)
    if not value["obligations"]:
        raise AssertionError("Expected a Core-owned current-activity obligation")
    return valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id,
         "source_quote": user if quote is None else quote}
        for item in value["obligations"]
    ]}


class ImpliedActivityProductionTests(unittest.TestCase):
    def assert_published(self, result, text=GOOD, *withheld):
        self.assertEqual(result[0], text)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": text})
        self.assertEqual(result[2:], (None, None))
        for item in withheld:
            self.assertNotIn(item, [message["content"] for message in result[1]])

    def assert_retry(self, candidate, user=USER, *, verdict=None, history=()):
        client = ScriptedClient([candidate, GOOD], core=[valid_core() if verdict is None else verdict,
                                                       valid_core()])
        self.assert_published(run(client, user, social("share_context"), history), GOOD, candidate)
        self.assertEqual(generations(client), 2)
        self.assertEqual(verifications(client), 2)
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def assert_single(self, candidate, user=USER, history=()):
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, user, social("share_context"), history), candidate)
        self.assertEqual(generations(client), 1)
        self.assertEqual(verifications(client), 1)
        return client

    def direct(self, candidate, user=USER, *, verdict=None, history=()):
        client = ScriptedClient([], core=[valid_core() if verdict is None else verdict])
        errors = verify_core_grounded_draft(client, "neutral-model", user, candidate, social(), history)
        self.assertEqual(len(client.calls), 1, "Use the existing single scoped verifier call")
        self.assertTrue(any("user-history" in item for item in errors), errors)
        return errors, client

    def test_unsupplied_while_activity_cannot_publish_after_global_approval(self):
        self.assert_retry(SUBORDINATE)

    def test_modal_main_clause_does_not_hide_actual_subordinate_activity(self):
        candidate = "You can stop sorting files while using the tablet."
        self.assert_retry(candidate)

    def test_definite_someone_currently_clause_has_user_authority_requirement(self):
        self.assert_retry("That's impressive for someone currently using the old terminal.")

    def test_preposed_subordinate_requires_its_understood_user_activity(self):
        self.assert_retry("While indexing the ledger, you're using the tablet.")

    def test_matching_user_current_activity_publishes_without_a_retry(self):
        self.assert_single(SUBORDINATE, "I'm using the tablet.")

    def test_two_matching_current_activities_keep_a_faithful_restatement(self):
        user = "I'm indexing the ledger while using the tablet."
        candidate = "You're indexing the ledger while using the tablet."
        self.assert_single(candidate, user)

    def test_different_object_is_not_borrowed_from_a_matching_activity(self):
        user = "I'm using the terminal."
        self.assert_retry(SUBORDINATE, user, verdict=positive_scoped(SUBORDINATE, user))

    def test_different_activity_is_not_borrowed_from_a_matching_object(self):
        user = "I'm inspecting the tablet."
        self.assert_retry(SUBORDINATE, user, verdict=positive_scoped(SUBORDINATE, user))

    def test_past_activity_does_not_supply_immediate_activity(self):
        user = "I was using the tablet."
        self.assert_retry(SUBORDINATE, user, verdict=positive_scoped(SUBORDINATE, user))

    def test_latest_negative_correction_defeats_prior_positive_activity(self):
        user = "I'm not using the tablet now."
        history = [{"role": "user", "content": "I'm using the tablet."}]
        value = positive_scoped(SUBORDINATE, user, conversation=history,
                                source_id="prior_user_1", quote=history[0]["content"])
        self.assert_retry(SUBORDINATE, user, verdict=value, history=history)

    def test_latest_positive_correction_remains_available(self):
        history = [{"role": "user", "content": "I'm not using the tablet."}]
        self.assert_single(SUBORDINATE, "I'm using the tablet now.", history)

    def test_assistant_prior_activity_cannot_supply_a_witness(self):
        history = [{"role": "assistant", "content": "I'm using the tablet."}]
        value = positive_scoped(SUBORDINATE, conversation=history,
                                source_id="prior_user_1", quote=history[0]["content"])
        self.assert_retry(SUBORDINATE, verdict=value, history=history)

    def test_candidate_text_cannot_become_a_source(self):
        value = positive_scoped(SUBORDINATE, source_id="candidate", quote=SUBORDINATE)
        self.direct(SUBORDINATE, verdict=value)

    def test_quoted_user_activity_is_not_a_current_witness(self):
        user = 'The sample dialogue says "I am using the tablet".'
        value = positive_scoped(SUBORDINATE, user, quote="I am using the tablet")
        self.assert_retry(SUBORDINATE, user, verdict=value)

    def test_conditional_user_activity_is_not_a_current_witness(self):
        user = "If I'm using the tablet, ask me before assuming it."
        value = positive_scoped(SUBORDINATE, user, quote="I'm using the tablet")
        self.assert_retry(SUBORDINATE, user, verdict=value)

    def test_conditional_advice_does_not_assert_activity(self):
        self.assert_single("If you're using the tablet, check the port.")

    def test_generic_capability_with_subordinate_activity_is_nonassertive(self):
        self.assert_single("You could use the tablet while travelling.")

    def test_global_positive_cannot_erase_the_scoped_obligation(self):
        errors, client = self.direct(SUBORDINATE)
        self.assertTrue(any("missing or incomplete" in item for item in errors))
        prompt = "\n".join(message["content"] for message in client.calls[0]["messages"])
        self.assertIn("CORE USER-HISTORY OBLIGATIONS", prompt)
        self.assertIn("current_activity_state", prompt)
        self.assertIn("history_assessments", prompt)

    def test_malformed_scoped_result_cannot_publish(self):
        value = positive_scoped(SUBORDINATE)
        value["history_assessments"][0]["supported"] = "yes"
        errors, _ = self.direct(SUBORDINATE, verdict=value)
        self.assertTrue(any("malformed" in item for item in errors))

    def test_every_retry_is_checked_with_no_extra_model_loop(self):
        next_bad = "That's impressive for someone currently using the old terminal."
        client = ScriptedClient([SUBORDINATE, next_bad, GOOD], core=[valid_core()] * 3)
        self.assert_published(run(client, USER, social()), GOOD, SUBORDINATE, next_bad)
        self.assertEqual(generations(client), 3)
        self.assertEqual(verifications(client), 3)
        self.assertEqual(len(client.calls), 6)

    def test_three_invalid_current_activities_keep_existing_bounded_fallback(self):
        client = ScriptedClient([SUBORDINATE] * 3, core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertTrue(result[0].strip())
        self.assertNotEqual(result[0], SUBORDINATE)
        self.assertNotIn(SUBORDINATE, [item["content"] for item in result[1]])
        self.assertEqual(result[2:], (None, None))
        self.assertEqual(generations(client), 3)
        self.assertEqual(verifications(client), 3)

    def test_unsupplied_cessation_is_checked_by_the_same_verifier(self):
        self.assert_retry(CESSATION)

    def test_embedded_directed_cessation_is_not_hidden_by_assistant_waiting(self):
        self.assert_retry("I'm waiting for you to stop indexing the ledger.")

    def test_matching_current_user_activity_supports_cessation(self):
        self.assert_single(CESSATION, "I'm indexing the ledger.")

    def test_current_negative_defeats_stale_cessation_witness(self):
        user = "I'm not indexing the ledger now."
        history = [{"role": "user", "content": "I'm indexing the ledger."}]
        value = positive_scoped(CESSATION, user, conversation=history,
                                source_id="prior_user_1", quote=history[0]["content"])
        self.assert_retry(CESSATION, user, verdict=value, history=history)

    def test_cessation_cannot_change_the_activity_object(self):
        user = "I'm indexing the atlas."
        self.assert_retry(CESSATION, user, verdict=positive_scoped(CESSATION, user))

    def test_hypothetical_cessation_does_not_create_current_activity(self):
        self.assert_single("If you're indexing the ledger, stop indexing the ledger for a break.")

    def test_quoted_cessation_example_does_not_create_user_state(self):
        self.assert_single('The example instruction is "Stop indexing the ledger."')

    def test_generic_instruction_without_user_state_is_not_history(self):
        self.assert_single("When filing samples, stop using the old terminal if the display fails.")

    def test_existing_matching_concern_cessation_remains_supported(self):
        self.assert_single("You can stop worrying about the invoice now.",
                           "I've been worrying about the invoice.")

    def test_existing_unsupplied_concern_cessation_remains_rejected(self):
        candidate = "You can stop worrying about the invoice now."
        self.assert_retry(candidate, verdict=positive_scoped(candidate))

    def test_obvious_object_personification_keeps_ordinary_single_generation(self):
        self.assert_single("Your compiler is begging for mercy.", "My compiler is irritating me.")


if __name__ == "__main__":
    unittest.main()
