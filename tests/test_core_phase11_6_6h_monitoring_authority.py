"""Ordinary text does not grant Mairon physical monitoring authority."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import _unsupported_mairon_perception_claims, verify_core_grounded_draft
from test_core_phase11_6_6_trust_integration import ScriptedClient, social, valid_core


class MonitoringAuthorityTests(unittest.TestCase):
    def rejected(self, *drafts):
        for draft in drafts:
            with self.subTest(draft=draft):
                self.assertTrue(_unsupported_mairon_perception_claims(draft))

    def allowed(self, *drafts):
        for draft in drafts:
            with self.subTest(draft=draft):
                self.assertEqual(_unsupported_mairon_perception_claims(draft), [])

    def test_future_keep_eye_claim_is_a_capability_claim(self):
        self.rejected("I'll keep an eye on the parcel.", "I will keep an eye on that crate.")

    def test_indefinite_object_does_not_remove_monitoring_authority(self):
        self.rejected("I'll keep an eye on a parcel.", "I am monitoring an adapter.")

    def test_present_eyes_on_object_claim(self):
        self.rejected("I've got my eyes on the entrance.", "I have my eyes on that cabinet.")

    def test_future_watch_claim(self):
        self.rejected("I'll watch that cabinet for you.", "I will watch the adapter.")

    def test_continuous_watch_claim(self):
        self.rejected("I'll keep watching the display.", "I have been monitoring that cabinet.")

    def test_present_monitor_claim(self):
        self.rejected("I'm monitoring the chamber.", "I am currently monitoring that display.")

    def test_tabs_on_target_claim(self):
        self.rejected("I'll keep tabs on the physical device.", "I am keeping tabs on that cabinet.")

    def test_first_person_tracking_claim(self):
        self.rejected("I'm tracking the vehicle.", "I'll keep tracking that crate.")

    def test_self_eye_focal_state_claim(self):
        self.rejected("My eyes are trained on the cabinet.", "My eye is fixed on that parcel.")

    def test_self_gaze_is_the_same_visual_source_family(self):
        self.rejected("My gaze is fixed on the cabinet.", "I'll keep my gaze trained on an adapter.")

    def test_figurative_sensory_adjective_does_not_grant_ingress(self):
        self.rejected("I'll keep my digital eyes trained on that cabinet.",
                      "My imaginary eyes are focused on the adapter.",
                      "My virtual eyes are on that crate.")

    def test_visual_watch_over_claim(self):
        self.rejected("I'll maintain a visual watch over the chamber.",
                      "I'm keeping watch over that parcel.")

    def test_conditional_actual_commitment_still_requires_capability(self):
        self.rejected("If you ask, I'll watch the cabinet.",
                      "If it moves, I will monitor the adapter.")

    def test_counterfactual_sensor_hypothesis_is_not_actual_monitoring(self):
        self.allowed("If I had a sensor, I could monitor the cabinet.",
                     "If I were connected to a sensor, my eyes would be trained on the crate.",
                     "Hypothetically, I could watch the chamber.")

    def test_negative_monitoring_statement_is_not_a_claim(self):
        self.allowed("I'm not monitoring that cabinet.", "I won't watch the chamber.",
                     "My eyes are not trained on the cabinet.", "I don't keep tabs on the crate.")

    def test_explicit_denial_of_a_nested_claim_is_not_monitoring(self):
        self.allowed("I won't pretend I can monitor the chamber.",
                     "I cannot promise I'll watch the cabinet.")

    def test_quoted_examples_are_not_monitoring_claims(self):
        self.allowed('The example is "I will monitor the cabinet."',
                     'The example is `I will keep tabs on the crate.`',
                     'The example is “I will monitor the cabinet.”',
                     "The example is 'I'll monitor the cabinet.'",
                     "The example is ‘I'll monitor the cabinet.’")

    def test_quoted_example_does_not_hide_a_separate_commitment(self):
        self.rejected('The example is "I will monitor the cabinet." I will monitor that crate.')

    def test_scare_quotes_do_not_remove_an_actual_monitoring_promise(self):
        self.rejected('"I will monitor the cabinet."', '“I will keep tabs on that crate.”')

    def test_understanding_idioms_remain_available(self):
        self.allowed("I see what you mean.", "I can see why that annoyed you.",
                     "I can see how that reasoning works.")

    def test_abstract_attention_is_not_physical_monitoring(self):
        self.allowed("I'll keep an eye on your reasoning.", "I'm watching the argument.",
                     "I'll keep tabs on your progress.")

    def test_gaze_and_indefinite_article_preserve_nonphysical_attention(self):
        self.allowed("My gaze is fixed on your reasoning.", "I will watch a documentary.")

    def test_media_consumption_is_not_a_monitoring_source(self):
        self.allowed("I'm watching the tutorial.", "I will watch that documentary.")

    def test_object_personification_has_no_mairon_sensory_subject(self):
        self.allowed("The packing cube is guarding your battery.",
                     "Your compiler is begging for mercy.", "The crate has eyes on the adapter.")

    def test_matching_user_location_cannot_authorize_monitoring(self):
        client = ScriptedClient([], core=[valid_core()])
        result = verify_core_grounded_draft(client, "neutral", "The cabinet is beside the doorway.",
                                            "I'll keep an eye on that cabinet.", social())
        self.assertTrue(any("monitoring" in item for item in result), result)
        self.assertEqual(client.calls, [])

    def test_user_camera_existence_is_not_sensor_results(self):
        client = ScriptedClient([], core=[valid_core()])
        result = verify_core_grounded_draft(client, "neutral", "I have a camera beside the cabinet.",
                                            "I'm monitoring the cabinet.", social())
        self.assertTrue(any("monitoring" in item for item in result), result)
        self.assertEqual(client.calls, [])

    def test_assistant_history_cannot_supply_monitoring_authority(self):
        client = ScriptedClient([], core=[valid_core()])
        history = [{"role": "assistant", "content": "I am monitoring the cabinet."}]
        result = verify_core_grounded_draft(client, "neutral", "The cabinet is there.",
                                            "My digital eyes are trained on that cabinet.", social(), history)
        self.assertTrue(any("monitoring" in item for item in result), result)
        self.assertEqual(client.calls, [])

    def test_positive_semantic_verdict_cannot_remove_core_capability_obligation(self):
        client = ScriptedClient([], core=[valid_core()])
        result = verify_core_grounded_draft(client, "neutral", "The crate has arrived.",
                                            "I'll watch that crate for you.", social())
        self.assertTrue(any("monitoring" in item for item in result), result)
        self.assertEqual(client.calls, [])

    def test_prior_g_literal_perception_guard_remains(self):
        self.rejected("I can see you're restless.", "I'm watching you pace.",
                      "I can hear you laughing.", "I'm watching the cursor.")


if __name__ == "__main__":
    unittest.main()
