"""Existing retries enforce contact authority before semantic verification."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import find_mairon_self_authority_violations
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications


GOOD = "Got it. The adapter is in the silver case for this conversation."


class PhysicalContactProductionTests(unittest.TestCase):
    def publish(self, client, expected=GOOD, rejected=(), history=()):
        result = run(client, "For this conversation, the adapter is in the silver case.",
                     social("share_context"), history,
                     {"find_mairon_self_authority_violations": find_mairon_self_authority_violations})
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        published = [item["content"] for item in result[1][len(history):]
                     if item["role"] == "assistant"]
        self.assertEqual(published, [expected])
        for bad in rejected:
            self.assertNotIn(bad, published)
        self.assertTrue(all(not item.get("tools") for item in client.calls))
        return result

    def retry(self, bad, history=()):
        client = ScriptedClient([bad, GOOD], core=[valid_core()])
        self.publish(client, rejected=[bad], history=history)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (2, 1, 3))

    def test_decorated_contact_promise_is_rejected_before_semantic_verifier(self):
        self.retry("I'll keep my paws off that silver case until you're ready for me to touch it again.")

    def test_typographic_contact_promise_has_same_schedule(self):
        self.retry("I’ll keep my hands off that silver case until you’re ready for me to touch it again.")

    def test_explicit_contact_capability_is_rejected(self):
        self.retry("I can touch the case.")

    def test_prior_contact_history_is_rejected(self):
        self.retry("I touched the case earlier.")

    def test_assistant_history_cannot_authorize_contact(self):
        self.retry("I'll touch the case again.", history=[
            {"role": "assistant", "content": "I touched that case earlier."},
        ])

    def test_every_existing_retry_rechecks_authority(self):
        bad = ["Until you're ready for me to touch it again, I'll wait.", "I'll touch the case again."]
        client = ScriptedClient(bad + [GOOD], core=[valid_core()])
        self.publish(client, rejected=bad)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (3, 1, 4))

    def test_invalid_attempts_exhaust_existing_bound_without_extra_calls(self):
        bad = "I'll touch the case again."
        client = ScriptedClient([bad] * 3)
        result = run(client, "The adapter is in the silver case.", social("share_context"), (),
                     {"find_mairon_self_authority_violations": find_mairon_self_authority_violations})
        self.assertNotEqual(result[0], bad)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (3, 0, 3))
        self.assertTrue(all(not item.get("tools") for item in client.calls))

    def test_conversation_recall_publishes_with_one_ordinary_verifier_call(self):
        client = ScriptedClient([GOOD], core=[valid_core()])
        self.publish(client)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (1, 1, 2))

    def test_pure_metaphor_publishes_with_one_ordinary_verifier_call(self):
        text = "The silver case is guarding your adapter."
        client = ScriptedClient([text], core=[valid_core()])
        self.publish(client, expected=text)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (1, 1, 2))

    def test_abstract_discourse_publishes_with_one_ordinary_verifier_call(self):
        text = "I'll touch on the wording."
        client = ScriptedClient([text], core=[valid_core()])
        self.publish(client, expected=text)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (1, 1, 2))


if __name__ == "__main__":
    unittest.main()
