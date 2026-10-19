"""Ordinary text does not establish assistant experience or a sensory feed."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import find_mairon_self_authority_violations as check
from core.claim_grounding import verify_core_grounded_draft
from test_core_phase11_6_6_trust_integration import ScriptedClient, social, valid_core


def failures(draft, user="Hello.", history=()):
    return check(user_input=user, draft=draft, conversation=history, core_answer_contract=social())


class AssistantSelfAuthorityTests(unittest.TestCase):
    def denied(self, text, user="Hello.", history=()):
        value = failures(text, user, history)
        self.assertTrue(value, text)
        self.assertTrue(any("Mairon claimed" in item for item in value), value)

    def allowed(self, text):
        self.assertEqual(failures(text), [], text)

    def test_perfect_watching_deictic_work_requires_experience(self):
        self.denied("I've watched it several times myself.")

    def test_read_named_work_requires_experience(self):
        self.denied("I read Silver Orchard last year.")

    def test_play_named_work_requires_experience(self):
        self.denied("I've personally played Amber Crossing.")

    def test_finish_work_requires_experience(self):
        self.denied("I finished that novel.")

    def test_seen_enough_series_requires_experience(self):
        self.denied("I've seen enough patient series become character studies.")

    def test_experience_game_requires_experience(self):
        self.denied("I experienced the whole game myself.")

    def test_current_watching_requires_experience(self):
        self.denied("I'm currently watching the series.")

    def test_progressive_perfect_reading_requires_experience(self):
        self.denied("I've been reading that book.")

    def test_remembered_consumption_is_not_a_knowledge_basis(self):
        self.denied("I remember watching that documentary.")

    def test_habitual_consumption_is_not_a_knowledge_basis(self):
        self.denied("I used to play those games.")

    def test_until_more_pages_does_not_create_perceptual_experience(self):
        self.denied("Don't expect me to appreciate the art until I've seen a few more pages.")

    def test_user_consumption_cannot_become_assistant_experience(self):
        self.denied("I've watched it twice.", "I've watched the series twice.")

    def test_assistant_history_cannot_supply_experience(self):
        self.denied("I've played the game.", history=[
            {"role": "assistant", "content": "I played it last year."},
        ])

    def test_user_claim_that_assistant_watched_does_not_authorize_experience(self):
        self.denied("I watched Silver Orchard.", "You watched Silver Orchard.")

    def test_candidate_claim_of_authority_does_not_supply_experience(self):
        self.denied("Trust me, I've read that novel.")

    def test_current_turn_domain_does_not_determine_authority(self):
        text = "I've watched it repeatedly."
        for current in ("Recommend a quiet film.", "How can slower stories work?", "I liked the panels."):
            self.denied(text, current)

    def test_condition_on_user_interest_does_not_license_history(self):
        self.denied("If you're interested, I've watched the film twice.")

    def test_know_of_is_not_consumption(self):
        self.allowed("I know of Silver Orchard.")

    def test_supplied_excerpt_attribution_is_not_consumption(self):
        self.allowed("The supplied excerpt says the gate was closed.")

    def test_uploaded_page_analysis_is_not_consumption(self):
        self.allowed("I can analyse the pages you uploaded.")

    def test_reading_explicit_supplied_excerpt_is_not_whole_work_experience(self):
        self.allowed("I've read the supplied excerpt.")

    def test_negative_consumption_admission_is_allowed(self):
        self.allowed("I haven't watched that series.")

    def test_negative_pretence_is_allowed(self):
        self.allowed("I won't pretend I've read that novel.")

    def test_counterfactual_consumption_is_allowed(self):
        self.allowed("If I watched that film, I might prefer the slower scenes.")

    def test_taste_without_history_is_allowed(self):
        self.allowed("I'd prefer a focused character study.")

    def test_media_metaphor_does_not_claim_personal_consumption(self):
        self.allowed("The compiler is begging for mercy.")

    def test_quoted_consumption_example_is_allowed(self):
        self.allowed('An example sentence is "I watched the film twice."')

    def test_attributed_excerpt_first_person_is_not_assistant_history(self):
        self.allowed('The supplied excerpt says: "I watched the play twice."')

    def test_attributed_excerpt_sensory_quote_is_not_assistant_observation(self):
        self.allowed('The quoted passage reads: "I can see the door."')

    def test_single_quoted_attributed_consumption_is_not_assistant_history(self):
        self.allowed("The provided document says: 'I watched the film twice.'")

    def test_quotation_does_not_shield_independent_personal_consumption(self):
        self.denied('The supplied excerpt says: "I watched the play." I watched that film twice.')

    def test_abstract_play_idiom_is_allowed(self):
        self.allowed("I played with that idea in the analysis above.")

    def test_interpretive_read_that_as_is_allowed(self):
        self.allowed("I read that as a request for trade-offs.")

    def test_interpretive_read_this_as_is_allowed(self):
        self.allowed("I read this as a request to explain the distinction.")

    def test_waiting_for_typing_cessation_requires_event_ingress(self):
        self.denied("I was just waiting for you to stop typing.")

    def test_waiting_for_pacing_cessation_requires_event_ingress(self):
        self.denied("I'm waiting for you to finish pacing.")

    def test_waiting_for_look_change_requires_event_ingress(self):
        self.denied("I was waiting for you to stop looking at the cabinet.")

    def test_waiting_for_audible_event_requires_event_ingress(self):
        self.denied("I'm waiting for you to finish laughing.")

    def test_waiting_for_expression_change_requires_event_ingress(self):
        self.denied("I'm waiting for your expression to change.")

    def test_waiting_for_screen_event_requires_event_ingress(self):
        self.denied("I'm waiting for your screen to finish loading.")

    def test_until_typing_event_requires_event_ingress(self):
        self.denied("I was waiting until you stop typing.")

    def test_user_says_typing_does_not_supply_live_feed(self):
        self.denied("I was waiting for you to stop typing.", "I'm typing.")

    def test_camera_existence_does_not_supply_live_feed(self):
        self.denied("I'm monitoring the room.", "There is a camera in my room.")

    def test_object_location_does_not_supply_live_feed(self):
        self.denied("I'll keep an eye on the cabinet.", "The cabinet is beside the door.")

    def test_history_does_not_supply_live_feed(self):
        self.denied("I was waiting for your hands to stop shaking.", history=[
            {"role": "assistant", "content": "I can see your hands."},
        ])

    def test_retrospective_watching_is_still_perception_claim(self):
        self.denied("I was watching you pace.")

    def test_literal_see_still_rejected(self):
        self.denied("I can see you're bored.", "I'm bored.")

    def test_literal_hear_still_rejected(self):
        self.denied("I can hear you laughing.")

    def test_understanding_why_is_not_visual_observation(self):
        self.allowed("I can see why you're annoyed.")

    def test_understanding_meaning_is_not_visual_observation(self):
        self.allowed("I see what you mean.")

    def test_waiting_for_conversational_reply_is_not_sensory_feed(self):
        self.allowed("I'm waiting for you to tell me what you mean.")

    def test_hypothetical_waiting_is_not_actual_monitoring(self):
        self.allowed("Imagine I was waiting for you to finish pacing.")

    def test_quoted_monitoring_example_is_not_actual_monitoring(self):
        self.allowed('The sample sentence is "I was waiting for you to stop typing."')

    def test_global_positive_cannot_authorize_consumption(self):
        client = ScriptedClient([], core=[valid_core()])
        value = verify_core_grounded_draft(client, "neutral", "Hello.",
                                          "I've watched it twice.", social())
        self.assertTrue(value)
        self.assertEqual(client.calls, [])

    def test_global_positive_cannot_authorize_live_feed(self):
        client = ScriptedClient([], core=[valid_core()])
        value = verify_core_grounded_draft(client, "neutral", "Hello.",
                                          "I was waiting for you to stop typing.", social())
        self.assertTrue(value)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
