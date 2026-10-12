"""Actual restricted provider retries reject fabricated sensory provenance."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications


class PerceptionProductionTests(unittest.TestCase):
    def assert_retry(self, user, bad, good):
        client = ScriptedClient([bad, good], core=[valid_core()])
        result = run(client, user, social())
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": good})
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual(result[2:], (None, None))
        self.assertEqual(generations(client), 2)
        self.assertEqual(verifications(client), 1)

    def test_known_emotion_still_cannot_be_claimed_as_visual(self):
        self.assert_retry("I'm restless.", "I can see you're restless.",
                          "Restlessness has impressive stamina.")

    def test_known_action_cannot_be_claimed_as_watched(self):
        self.assert_retry("I'm pacing.", "I'm watching you pace.",
                          "You said you're pacing. Restlessness has impressive stamina.")

    def test_known_sound_cannot_be_claimed_as_heard(self):
        self.assert_retry("I'm laughing.", "I can hear you laughing.",
                          "You said you're laughing.")

    def test_known_scene_cannot_be_claimed_as_seen(self):
        self.assert_retry("The room is dark.", "I can see the room is dark.",
                          "You said the room is dark.")

    def test_understanding_idiom_uses_ordinary_single_verifier(self):
        text = "I can see why that delay annoyed you."
        client = ScriptedClient([text], core=[valid_core()])
        result = run(client, "The delay annoyed me.", social())
        self.assertEqual(result[0], text)
        self.assertEqual(generations(client), 1)
        self.assertEqual(verifications(client), 1)

    def test_every_retry_is_checked_without_an_extra_model_loop(self):
        bad = "I can see you're tired."
        client = ScriptedClient([bad] * 3, core=[valid_core()])
        result = run(client, "I'm tired.", social())
        self.assertNotEqual(result[0], bad)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual(generations(client), 3)
        self.assertEqual(verifications(client), 0)
        self.assertEqual(result[2:], (None, None))

    def test_obvious_personification_remains_available(self):
        text = "Your code is committing crimes."
        client = ScriptedClient([text], core=[valid_core()])
        result = run(client, "My code is irritating me.", social())
        self.assertEqual(result[0], text)
        self.assertEqual(generations(client), 1)


if __name__ == "__main__":
    unittest.main()
