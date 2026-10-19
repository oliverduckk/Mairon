"""Existing producer retries enforce experience/embodiment/object-state guards."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import find_mairon_self_authority_violations
from core.user_history_obligations import build_user_history_packet
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications
from test_core_phase11_6_6j1_live3_self_authority_integration import recommendation


GOOD = "Right, got you."


def overrides():
    return {"find_mairon_self_authority_violations": find_mairon_self_authority_violations}


class SelfEmbodimentProductionTests(unittest.TestCase):
    def published(self, result, expected, *rejected, history=()):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        self.assertEqual([item["content"] for item in result[1][len(history):] if item["role"] == "assistant"],
                         [expected])
        for draft in rejected:
            self.assertNotIn(draft, [item["content"] for item in result[1][len(history):]])

    def self_retry(self, bad, user="Hello.", history=()):
        client = ScriptedClient([bad, GOOD], core=[valid_core()])
        self.published(run(client, user, social(), history, overrides()), GOOD, bad, history=history)
        # Shared deterministic authority runs before the one ordinary semantic
        # check of the valid retry. No dummy call or extra model loop exists.
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (2, 1, 3))
        self.assertTrue(all(not item.get("tools") for item in client.calls))
        return client

    def test_habitual_desire_is_rejected_before_semantic_verification(self):
        self.self_retry("Sometimes I find myself wanting to skip ahead to see whether the protagonist acts.")

    def test_skimming_habit_is_rejected(self):
        self.self_retry("I tend to skim those chapters.")

    def test_habitual_impatience_jump_is_rejected(self):
        self.self_retry("I usually get impatient and jump ahead.")

    def test_fast_forwarding_habit_is_rejected(self):
        self.self_retry("I always end up fast-forwarding those scenes.")

    def test_recommendation_has_same_experience_boundary(self):
        bad = "I tend to skim those chapters."
        good = "I'd prefer the shorter option based on your description."
        client = ScriptedClient([bad, good])
        self.published(run(client, "Recommend a concise story.", recommendation(), overrides=overrides()), good, bad)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (2, 0, 2))

    def test_general_opinion_has_same_experience_boundary(self):
        bad = "I often find myself skipping ahead in those stories."
        client = ScriptedClient([bad, GOOD], core=[valid_core()])
        self.published(run(client, "Can slower stories work?", social("share_opinion"), overrides=overrides()), GOOD, bad)
        self.assertEqual((generations(client), verifications(client)), (2, 1))

    def test_future_physical_inspection_does_not_publish(self):
        self.self_retry("I'll check the drawer.")

    def test_future_charging_does_not_publish(self):
        self.self_retry("I'll charge the cell.")

    def test_future_object_replacement_does_not_publish(self):
        self.self_retry("I'll put it back.")

    def test_combined_promise_and_prior_history_does_not_publish(self):
        self.self_retry("I'll make sure to check that silver pouch before I try to charge it again.",
                        "My spare cell is inside the silver pouch.")

    def test_typographic_physical_promise_cannot_bypass_shared_guard(self):
        self.self_retry("I’ll make sure to check that silver pouch before I try to charge it again.",
                        "My spare cell is inside the silver pouch.")

    def test_supplied_location_cannot_grant_physical_capability(self):
        self.self_retry("I'll charge the cell again.", "My cell is inside the silver pouch.")

    def test_assistant_history_cannot_grant_physical_capability(self):
        self.self_retry("I'll charge the cell again.", history=[
            {"role": "assistant", "content": "I charged that cell before."}])

    def test_self_authority_is_rechecked_on_every_retry(self):
        bad = ["I tend to skim those chapters.", "I'll charge the cell again."]
        client = ScriptedClient(bad + [GOOD], core=[valid_core()])
        self.published(run(client, "Hello.", social(), overrides=overrides()), GOOD, *bad)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (3, 1, 4))

    def test_invalid_attempts_exhaust_existing_bound_without_extra_calls(self):
        bad = "I'll charge the cell again."
        client = ScriptedClient([bad] * 3)
        result = run(client, "Hello.", social(), overrides=overrides())
        self.assertNotEqual(result[0], bad)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (3, 0, 3))

    def test_subjective_preference_publishes_unchanged(self):
        text = "I'd prefer tighter pacing."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "What sort of pacing works?", social(), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_conversation_scoped_location_acknowledgement_remains_available(self):
        text = "I'll remember that the cell is in the silver pouch for this conversation."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "For this conversation my cell is in the silver pouch.",
                           social("share_context"), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_nonliteral_object_personality_remains_available(self):
        text = "The silver pouch wins this round."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "My cell is in the silver pouch.", social(), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))


class ObjectConditionProductionTests(unittest.TestCase):
    BAD = "Your misplaced cells are in the pouch."

    def published(self, result, expected, *rejected):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for draft in rejected:
            self.assertNotIn(draft, [item["content"] for item in result[1] if item["role"] == "assistant"])

    def retry(self, user="My cells are in the pouch.", history=(), verdict=None):
        client = ScriptedClient([self.BAD, GOOD], core=[verdict or valid_core(), valid_core()])
        result = run(client, user, social(), history, overrides())
        self.published(result, GOOD, self.BAD)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (2, 2, 4))
        self.assertTrue(all(not item.get("tools") for item in client.calls))

    def test_new_item_condition_requires_authority_despite_global_positive(self):
        self.retry()

    def test_missing_scoped_assessments_fail_closed(self):
        self.retry(verdict=valid_core())

    def test_malformed_scoped_assessments_fail_closed(self):
        self.retry(verdict=valid_core() | {"history_assessments": ["yes"]})

    def test_unrelated_literal_quote_cannot_launder_item_condition(self):
        user = "My cells are in the pouch."
        packet = build_user_history_packet(self.BAD, {"current_user": user})
        verdict = valid_core() | {"history_assessments": [
            {"index": item["index"], "supported": True, "source_id": "current_user", "source_quote": user}
            for item in packet["obligations"]]}
        self.retry(user, verdict=verdict)

    def test_matching_user_item_state_publishes_unchanged(self):
        client = ScriptedClient([self.BAD], core=[valid_core()])
        self.published(run(client, "My cells are misplaced.", social(), overrides=overrides()), self.BAD)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (1, 1, 2))

    def test_latest_correction_defeats_previous_condition(self):
        self.retry("My cells are not misplaced.", [{"role": "user", "content": "My cells are misplaced."}])

    def test_assistant_history_is_not_user_object_authority(self):
        self.retry(history=[{"role": "assistant", "content": "Your cells are misplaced."}])

    def test_user_condition_on_different_object_cannot_be_borrowed(self):
        self.retry("My cables are misplaced.")

    def test_every_object_condition_retry_is_rechecked(self):
        other = "Your damaged adapters are in the case."
        client = ScriptedClient([self.BAD, other, GOOD], core=[valid_core()] * 3)
        self.published(run(client, "My cells are in the pouch.", social(), overrides=overrides()), GOOD,
                       self.BAD, other)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (3, 3, 6))


if __name__ == "__main__":
    unittest.main()
