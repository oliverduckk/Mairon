"""Real Core verification/retry transport cannot acquire plausible user history."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import verify_core_grounded_draft
from core.user_history_obligations import build_user_history_packet


USER = "I got back into reading the journal."
BAD = "You ignored the journal for four weeks."
GOOD = "Good to hear you're enjoying the journal."


def state(candidate, user=USER, *, supported=True, quote=None, source_id="current_user", extra=None):
    value = build_user_history_packet(candidate, {"current_user": user})
    result = valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": supported,
         "source_id": source_id, "source_quote": user if quote is None else quote}
        for item in value["obligations"]
    ]}
    if extra:
        for item in result["history_assessments"]:
            item.update(extra)
    return result


def calls(client):
    return sum(not any("INTERNAL" in item["content"] for item in value["messages"])
               for value in client.calls)


class UserHistoryProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1]["content"], expected)
        for item in withheld:
            self.assertNotIn(item, [value["content"] for value in result[1]])

    def verify(self, candidate, user=USER, value=None, history=(), contract=None):
        client = ScriptedClient([], core=[valid_core() if value is None else value])
        result = verify_core_grounded_draft(client, "neutral-model", user, candidate,
                                           contract or social(), history)
        return result, client

    def test_global_positive_without_history_witness_cannot_publish(self):
        client = ScriptedClient([BAD, GOOD], core=[valid_core(), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)
        self.assertEqual(calls(client), 2)

    def test_failed_history_witness_is_checked_again_on_retry(self):
        next_bad = "You always neglect the journal."
        client = ScriptedClient([BAD, next_bad, GOOD], core=[state(BAD), state(next_bad), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD, next_bad)
        self.assertEqual(calls(client), 3)

    def test_core_obligation_survives_a_model_none_classification(self):
        client = ScriptedClient([BAD, GOOD], core=[state(BAD, extra={"kind": "none"}), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)

    def test_negative_scoped_verdict_overrides_positive_global(self):
        errors, _ = self.verify(BAD, value=state(BAD, supported=False))
        self.assertTrue(any("user-history" in item for item in errors))

    def test_forged_candidate_quote_is_not_a_user_source(self):
        client = ScriptedClient([BAD, GOOD], core=[state(BAD, quote=BAD), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)

    def test_assistant_prior_history_cannot_ground_current_banter(self):
        history = [{"role": "assistant", "content": "You ignored the journal for four weeks."}]
        client = ScriptedClient([BAD, GOOD], core=[state(BAD, quote=BAD, source_id="prior_user_1"), valid_core()])
        self.assertEqual(run(client, USER, social(), history)[0], GOOD)

    def test_prior_user_history_can_support_the_same_duration(self):
        history = [{"role": "user", "content": "I ignored the journal for four weeks."}]
        client = ScriptedClient([BAD], core=[valid_core()])
        self.assert_published(run(client, USER, social(), history), BAD)
        self.assertEqual(calls(client), 1)

    def test_real_core_global_positive_cannot_override_current_negative_with_old_quote(self):
        user = "I do not usually shelve the maps."
        candidate = "You usually shelve the maps."
        history = [{"role": "user", "content": "I usually shelve the maps."}]
        old_witness = state(candidate, user=user, quote="I usually shelve the maps.", source_id="prior_user_1")
        errors, _ = self.verify(candidate, user=user, value=old_witness, history=history)
        self.assertTrue(any("current USER" in item for item in errors))

    def test_supplied_current_duration_publishes_without_new_output_requirement(self):
        user = "I haven't read in three weeks."
        candidate = "You haven't read in three weeks."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, user, social()), candidate)
        self.assertEqual(calls(client), 1)

    def test_number_word_variation_keeps_verified_user_history(self):
        user = "I haven't read in three weeks."
        candidate = "You haven't read in 3 weeks."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, user, social()), candidate)

    def test_safe_interruption_restates_reentry_without_adding_neglect(self):
        candidate = "You took a break from reading the journal."
        user = "I got back into reading the journal."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, user, social()), candidate)

    def test_implicit_return_fragment_is_not_authority_for_duration(self):
        candidate = "Welcome back after five weeks of avoiding the journal."
        client = ScriptedClient([candidate, GOOD], core=[valid_core(), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, candidate)

    def test_current_item_cannot_borrow_another_items_habit(self):
        user = "My folder is on the desk."
        candidate = "It moved from its usual hiding place."
        good = "At least you know where the folder is now."
        history = [{"role": "user", "content": "My notebook has its usual hiding place."}]
        bad_state = state(candidate, user=user, quote="My notebook has its usual hiding place.", source_id="prior_user_1")
        client = ScriptedClient([candidate, good], core=[bad_state, valid_core()])
        self.assert_published(run(client, user, social(), history), good, candidate)

    def test_emotional_metaphor_remains_natural_without_history_protocol(self):
        candidate = "You've been murdered emotionally by that chapter."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "The chapter was intense.", social()), candidate)
        self.assertEqual(calls(client), 1)

    def test_absurd_self_personification_does_not_acquire_user_history(self):
        candidate = "I've been a furious toaster for forty years."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "I'm bored.", social()), candidate)

    def test_real_verifier_uses_one_existing_call_with_scoped_history_targets(self):
        errors, client = self.verify(BAD)
        self.assertTrue(errors)
        self.assertEqual(len(client.calls), 1)
        prompt = "\n".join(item["content"] for item in client.calls[0]["messages"])
        self.assertIn("history_assessments", prompt)
        self.assertIn("CORE USER-HISTORY OBLIGATIONS", prompt)
        self.assertGreaterEqual(client.calls[0]["options"]["num_predict"], 480)

    def test_malformed_scoped_assessment_cannot_publish(self):
        value = state(BAD)
        value["history_assessments"][0]["supported"] = "yes"
        errors, _ = self.verify(BAD, value=value)
        self.assertTrue(any("history" in item for item in errors))

    def test_all_invalid_drafts_preserve_the_existing_retry_bound(self):
        client = ScriptedClient([BAD] * 3, core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertNotEqual(result[0], BAD)
        self.assertNotIn(BAD, [value["content"] for value in result[1]])
        self.assertEqual(calls(client), 3)
        self.assertTrue(result[0].strip())

    def test_non_social_trusted_core_lane_does_not_gain_user_only_protocol(self):
        contract = AnswerContractRuntime(intent="email_read", authority="core_context", epistemic_mode="core")
        errors, client = self.verify("You have received the parcel.", user="Read the notification.", contract=contract)
        self.assertFalse(errors)
        prompt = "\n".join(item["content"] for item in client.calls[0]["messages"])
        self.assertNotIn("CORE USER-HISTORY OBLIGATIONS", prompt)


if __name__ == "__main__":
    unittest.main()
