"""Text USER state does not grant Mairon a perceptual source."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from core.claim_grounding import _unsupported_mairon_perception_claims, verify_core_grounded_draft
from test_core_phase11_6_6_trust_integration import ScriptedClient, social, valid_core


class PerceptionAuthorityTests(unittest.TestCase):
    def test_supplied_emotion_does_not_grant_visual_observation(self):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(client, "neutral", "I'm disappointed.",
                                              "I can see you're disappointed.", social())
        self.assertTrue(any("physical perception" in item for item in failures), failures)
        self.assertEqual(client.calls, [])

    def test_supplied_body_state_does_not_grant_visual_observation(self):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(client, "neutral", "My hands are shaking.",
                                              "I can see your hands are shaking.", social())
        self.assertTrue(any("physical perception" in item for item in failures), failures)
        self.assertEqual(client.calls, [])

    def test_first_person_visual_source_claims_require_observation_authority(self):
        for text in (
            "I can see you're restless.", "I can see you staring at the wall.",
            "I see you pacing.", "I can see that you're tired.",
            "I’m watching you pace.", "I am looking at you.",
            "I'm staring at you.", "I can see the room is dark.",
        ):
            with self.subTest(text=text):
                self.assertTrue(_unsupported_mairon_perception_claims(text))

    def test_first_person_audio_source_claims_require_observation_authority(self):
        for text in ("I can hear you laughing.", "I can hear your breathing.",
                     "I can hear the window rattling."):
            with self.subTest(text=text):
                self.assertTrue(_unsupported_mairon_perception_claims(text))

    def test_understanding_idioms_are_not_sensory_sources(self):
        for text in ("I can see why you're annoyed.", "I see what you mean.",
                     "I can see how that reasoning works.", "I understand you're restless."):
            with self.subTest(text=text):
                self.assertEqual(_unsupported_mairon_perception_claims(text), [])

    def test_user_attribution_preserves_actual_source(self):
        self.assertEqual(_unsupported_mairon_perception_claims("You said you're tired."), [])

    def test_assistant_history_cannot_grant_a_perceptual_source(self):
        client = ScriptedClient([], core=[valid_core()])
        history = [{"role": "assistant", "content": "I can see you're restless."}]
        failures = verify_core_grounded_draft(client, "neutral", "I'm restless.",
                                              "I can see you're restless.", social(), history)
        self.assertTrue(failures)
        self.assertEqual(client.calls, [])

    def test_user_claiming_a_camera_exists_does_not_grant_sensor_results(self):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(client, "neutral", "I have a camera.",
                                              "I can see you smiling.", social())
        self.assertTrue(failures)
        self.assertEqual(client.calls, [])

    def test_global_positive_cannot_erase_core_perception_obligation(self):
        client = ScriptedClient([], core=[valid_core()])
        self.assertTrue(verify_core_grounded_draft(client, "neutral", "I'm tired.",
                                                  "I can see you're tired.", social()))
        self.assertEqual(client.calls, [])

    def test_old_clock_and_cursor_protections_remain(self):
        for text in ("I'm watching the clock.", "I'm watching the cursor."):
            with self.subTest(text=text):
                self.assertTrue(_unsupported_mairon_perception_claims(text))


if __name__ == "__main__":
    unittest.main()
