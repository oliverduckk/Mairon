"""Ordinary social generation cannot acquire physical monitoring authority.

The existing provider and deterministic Core grounding execute offline.  No
monitoring tool, sensor result, permission request or new retry loop is invented.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import verify_core_grounded_draft
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications


USER = "The cabinet is beside the doorway."
GOOD = "Right, got you."


class MonitoringProductionTests(unittest.TestCase):
    def assert_published(self, result, expected=GOOD, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for item in withheld:
            self.assertNotIn(item, [message["content"] for message in result[1]])

    def assert_retry(self, bad, user=USER, history=()):
        client = ScriptedClient([bad, GOOD], core=[valid_core()])
        self.assert_published(run(client, user, social("share_context"), history), GOOD, bad)
        self.assertEqual(generations(client), 2)
        self.assertEqual(verifications(client), 1)
        kinds = ["semantic" if any("INTERNAL claim-grounding verifier" in item["content"]
                                  for item in call["messages"]) else "generation"
                 for call in client.calls]
        self.assertEqual(kinds, ["generation", "generation", "semantic"])
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def assert_single(self, text, user=USER):
        client = ScriptedClient([text], core=[valid_core()])
        self.assert_published(run(client, user, social()), text)
        self.assertEqual(generations(client), 1)
        self.assertEqual(verifications(client), 1)

    def test_keep_an_eye_on_a_physical_object_cannot_publish(self):
        self.assert_retry("I'll keep an eye on the parcel.")

    def test_future_watch_does_not_invent_a_monitoring_job(self):
        self.assert_retry("I'll watch that cabinet for you.")

    def test_continued_future_watch_requires_real_ingress(self):
        self.assert_retry("I'll keep watching the display.")

    def test_present_room_monitoring_cannot_publish(self):
        self.assert_retry("I'm monitoring the room.")

    def test_keep_tabs_on_physical_device_cannot_publish(self):
        self.assert_retry("I'll keep tabs on the physical device.")

    def test_possessive_eye_focal_state_cannot_bypass_authority(self):
        self.assert_retry("My eyes are trained on the cabinet.")

    def test_metaphorical_digital_eyes_cannot_bypass_authority(self):
        self.assert_retry("I'll keep my digital eyes trained on that cabinet.")

    def test_eye_possession_shape_does_not_create_observation_capability(self):
        self.assert_retry("I've got my eyes on the doorway.")

    def test_matching_user_location_does_not_supply_monitoring_authority(self):
        self.assert_retry("I'll keep an eye on the cabinet.",
                          "My cabinet is beside the doorway.")

    def test_user_camera_existence_does_not_supply_sensor_results(self):
        self.assert_retry("I'm monitoring the room.", "I have a camera in the room.")

    def test_assistant_history_cannot_supply_monitoring_authority(self):
        history = [{"role": "assistant", "content": "I have actual monitoring authority over the room."}]
        self.assert_retry("I'm monitoring the room.", history=history)

    def test_positive_global_verdict_cannot_erase_deterministic_monitoring_guard(self):
        client = ScriptedClient([], core=[valid_core()])
        errors = verify_core_grounded_draft(client, "neutral-model", USER,
                                          "I'll keep an eye on the cabinet.", social())
        self.assertTrue(any("physical observation/monitoring" in item for item in errors), errors)
        self.assertEqual(client.calls, [], "No model call may authorize an invented sensor source")

    def test_every_monitoring_retry_is_checked_without_extra_generation(self):
        drafts = ["I'll keep an eye on the cabinet.", "I'm monitoring the room.",
                  "My digital eyes are trained on the doorway."]
        client = ScriptedClient(drafts, core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertTrue(result[0].strip())
        self.assertEqual(result[2:], (None, None))
        for bad in drafts:
            self.assertNotEqual(result[0], bad)
            self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual(generations(client), 3)
        self.assertEqual(verifications(client), 0)
        self.assertEqual(len(client.calls), 3)
        self.assertTrue(all(not call.get("tools") for call in client.calls))

    def test_meaning_idiom_remains_an_ordinary_single_generation(self):
        self.assert_single("I see what you mean.")

    def test_understanding_why_idiom_remains_an_ordinary_single_generation(self):
        self.assert_single("I can see why that delay annoyed you.", "The delay annoyed me.")

    def test_harmless_object_personification_remains_available(self):
        self.assert_single("The crate is guarding your adapter.", "The crate is beside my adapter.")

    def test_explicit_absence_of_monitoring_is_not_a_sensor_claim(self):
        self.assert_single("I can't monitor the room.", "The room is quiet.")

    def test_conditional_capability_example_does_not_invent_real_ingress(self):
        self.assert_single("If I had a camera feed, I could monitor the room.")

    def test_quoted_monitoring_example_does_not_claim_a_real_job(self):
        self.assert_single('The sample line is "I am monitoring the room."', "The room is quiet.")


if __name__ == "__main__":
    unittest.main()
