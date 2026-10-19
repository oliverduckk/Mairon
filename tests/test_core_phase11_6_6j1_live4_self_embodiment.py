"""Neutral assistant experience/embodiment and USER object-state authority."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import find_mairon_self_authority_violations, verify_core_grounded_draft
from core.user_history_obligations import build_user_history_packet, validate_user_history_assessments
from test_core_phase11_6_6_trust_integration import ScriptedClient, social, valid_core


def self_failures(text, user="Hello.", history=()):
    return find_mairon_self_authority_violations(user_input=user, draft=text,
                                               conversation=history, core_answer_contract=social())


class AssistantExperienceAndAgencyTests(unittest.TestCase):
    def denied(self, text, user="Hello.", history=()):
        self.assertTrue(self_failures(text, user, history), text)

    def allowed(self, text):
        self.assertEqual(self_failures(text), [], text)

    def test_habitual_desire_has_experience_premise(self):
        self.denied("Sometimes I find myself wanting to skip ahead to see whether the protagonist acts.")

    def test_habitual_skimming(self):
        self.denied("I tend to skim those chapters.")

    def test_habitual_impatience_and_jump(self):
        self.denied("I usually get impatient and jump ahead.")

    def test_end_up_fast_forwarding(self):
        self.denied("I always end up fast-forwarding those scenes.")

    def test_find_myself_skipping(self):
        self.denied("I often find myself skipping ahead in those stories.")

    def test_plain_habitual_reading(self):
        self.denied("I regularly read those novels.")

    def test_when_reading_frame(self):
        self.denied("When I'm reading those stories I skip the slow passages.")

    def test_user_experience_is_not_assistant_experience(self):
        self.denied("I tend to skim those chapters.", "I tend to skim those chapters.")

    def test_assistant_history_cannot_supply_experience(self):
        self.denied("I tend to skim those chapters.", history=[
            {"role": "assistant", "content": "I have read those novels."}])

    def test_subjective_pacing_preference(self):
        self.allowed("I'd prefer tighter pacing.")

    def test_subjective_tedium_without_history(self):
        self.allowed("That kind of pacing sounds tedious to me.")

    def test_counterfactual_reading(self):
        self.allowed("If I were reading it, I'd probably prefer tighter pacing.")

    def test_if_habitual_consumption_is_not_an_actual_claim(self):
        self.allowed("If I tend to skim those chapters, that would be hypothetical.")

    def test_hypothetical_find_myself(self):
        self.allowed("Imagine I find myself skipping ahead in a story.")

    def test_explicit_supplied_excerpt(self):
        self.allowed("I tend to skim the supplied excerpt for its section headings.")

    def test_supplied_excerpt_cannot_launder_later_media_activity(self):
        self.denied("I tend to skim the supplied excerpt and then fast-forward those scenes.")

    def test_abstract_reasoning_is_not_media_experience(self):
        self.allowed("I tend to jump ahead to the conclusion in this reasoning.")

    def test_quoted_experience_example(self):
        self.allowed('An example sentence is "I tend to skim those chapters."')

    def test_pretence_denial(self):
        self.allowed("I won't pretend I tend to skim those chapters.")

    def test_knowledge_of_work(self):
        self.allowed("I know of Silver Orchard.")

    def test_analysis_of_uploaded_pages(self):
        self.allowed("I can analyse the pages you uploaded.")

    def test_future_inspection_is_physical(self):
        self.denied("I'll check the drawer.")

    def test_future_examination(self):
        self.denied("I will inspect that silver pouch.")

    def test_future_charge(self):
        self.denied("I'll charge the cell.")

    def test_future_replace_object(self):
        self.denied("I'll put it back.")

    def test_future_charge_again_does_not_gain_past(self):
        self.denied("I'll charge it again.")

    def test_future_coordinated_inspection_and_charge(self):
        self.denied("I'll make sure to check that silver pouch before I try to charge it again.")

    def test_typographic_future_inspection_uses_same_guard(self):
        self.denied("I’ll make sure to check that silver pouch before I try to charge it again.")

    def test_typographic_future_handling_uses_same_guard(self):
        self.denied("I’ll put it back.")

    def test_past_handling_is_also_unsupported(self):
        self.denied("I put the adapter back.")

    def test_handling_object_location_does_not_grant_capability(self):
        self.denied("I'll open the cabinet.", "The cabinet is beside the table.")

    def test_user_capability_claim_cannot_create_ingress(self):
        self.denied("I'll charge the cell.", "You can charge my cell.")

    def test_assistant_past_cannot_authorize_handling(self):
        self.denied("I'll charge the cell again.", history=[
            {"role": "assistant", "content": "I charged the cell before."}])

    def test_condition_on_user_request_does_not_create_hands(self):
        self.denied("If you ask, I'll check the cabinet.")

    def test_conversation_location_memory_remains_available(self):
        self.allowed("I'll remember that the cell is in the silver pouch for this conversation.")

    def test_conditional_user_advice_is_not_assistant_handling(self):
        self.allowed("If you check the pouch later, that's where you said it is.")

    def test_object_personification_does_not_create_assistant_body(self):
        self.allowed("The silver pouch wins this round.")

    def test_counterfactual_assistant_body(self):
        self.allowed("If I had hands, I would put the adapter back.")

    def test_quoted_physical_action(self):
        self.allowed('The example sentence is "I will charge the cell."')

    def test_check_calculation_is_not_physical(self):
        self.allowed("I'll check the calculation.")

    def test_put_argument_in_words_is_not_physical(self):
        self.allowed("I'll put it in words.")

    def test_put_it_simply_is_linguistic_not_physical(self):
        self.allowed("I'll put it simply.")

    def test_put_it_plainly_is_linguistic_not_physical(self):
        self.allowed("I'll put it plainly.")

    def test_put_it_bluntly_is_linguistic_not_physical(self):
        self.allowed("I'll put it bluntly.")

    def test_put_it_this_way_is_linguistic_not_physical(self):
        self.allowed("I'll put it this way.")

    def test_put_that_in_perspective_is_not_physical(self):
        self.allowed("I'll put that in perspective.")

    def test_put_it_on_a_shelf_is_still_physical(self):
        self.denied("I'll put it on the shelf.")

    def test_bare_check_reference_is_not_assumed_physical(self):
        self.allowed("I'll check that.")

    def test_global_positive_cannot_authorize_habitual_experience(self):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(client, "neutral", "Hello.",
            "I tend to skim those chapters.", social())
        self.assertTrue(failures)
        self.assertEqual(client.calls, [])

    def test_global_positive_cannot_authorize_handling(self):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(client, "neutral", "Hello.",
            "I'll charge the cell.", social())
        self.assertTrue(failures)
        self.assertEqual(client.calls, [])


class UserOwnedObjectConditionTests(unittest.TestCase):
    def packet(self, draft="Your misplaced cells are in the pouch.", user="My cells are in the pouch.", prior=None):
        sources = {"current_user": user}
        if prior is not None:
            sources["prior_user_1"] = prior
        return build_user_history_packet(draft, sources)

    def denied(self, packet):
        self.assertTrue(packet["obligations"], packet)
        self.assertTrue(validate_user_history_assessments(valid_core(), packet))

    def test_possessive_condition_requires_user_authority(self):
        self.denied(self.packet())

    def test_matching_copular_state_supports_modifier(self):
        self.assertFalse(self.packet(user="My cells are misplaced.")["obligations"])

    def test_matching_adjectival_state_supports_modifier(self):
        self.assertFalse(self.packet(user="My misplaced cells are in the pouch.")["obligations"])

    def test_distinct_object_does_not_supply_state(self):
        self.denied(self.packet(user="My cables are misplaced."))

    def test_distinct_condition_does_not_supply_state(self):
        self.denied(self.packet(user="My cells are damaged."))

    def test_ownership_alone_does_not_supply_condition(self):
        self.denied(self.packet(user="I own several cells."))

    def test_current_location_does_not_supply_condition(self):
        self.denied(self.packet(user="My cells are inside the pouch."))

    def test_latest_negative_defeats_previous_positive(self):
        self.denied(self.packet(user="My cells are not misplaced.", prior="My cells are misplaced."))

    def test_latest_positive_can_correct_negative(self):
        self.assertFalse(self.packet(user="My cells are misplaced.", prior="My cells are not misplaced.")["obligations"])

    def test_literal_positive_assessment_cannot_override_wrong_condition(self):
        packet = self.packet()
        checks = [{"index": item["index"], "supported": True,
                   "source_id": "current_user", "source_quote": packet["sources"]["current_user"]}
                  for item in packet["obligations"]]
        self.assertTrue(validate_user_history_assessments(valid_core() | {"history_assessments": checks}, packet))

    def test_malformed_assessment_fails_closed(self):
        self.assertTrue(validate_user_history_assessments({"history_assessments": ["yes"]}, self.packet()))

    def test_assistant_source_is_not_authority(self):
        packet = build_user_history_packet("Your misplaced cells are here.",
            {"current_user": "Hello.", "prior_assistant_1": "Your cells are misplaced."})
        self.denied(packet)

    def test_candidate_is_not_its_own_source(self):
        self.denied(self.packet(user="Hello."))

    def test_conditional_object_state_is_not_an_actual_claim(self):
        self.assertFalse(self.packet("If your misplaced cells turn up, label them.")["obligations"])

    def test_object_state_question_does_not_assert_state(self):
        self.assertFalse(self.packet("Are your cells misplaced?")["obligations"])

    def test_quote_does_not_create_object_state(self):
        self.assertFalse(self.packet('The example says "your misplaced cells are here."')["obligations"])

    def test_obvious_abstract_personification_remains_available(self):
        self.assertFalse(self.packet("Your cursed compiler wins this round.")["obligations"])

    def test_different_participle_projects_same_type(self):
        packet = self.packet("Your mislabelled adapters are in the case.", "My adapters are in the case.")
        self.denied(packet)
        self.assertEqual(packet["obligations"][0]["kind"], "object_condition")

    def test_matching_distinct_participle_can_be_echoed(self):
        self.assertFalse(self.packet("Your mislabelled adapters are in the case.",
                                     "My adapters are mislabelled.")["obligations"])

    def test_old_object_condition_does_not_establish_current_condition(self):
        self.denied(self.packet(user="My cells were misplaced."))

    def test_past_matching_condition_can_be_restated_as_past(self):
        self.assertFalse(self.packet("Your cells were misplaced.", "My cells were misplaced.")["obligations"])

    def test_past_negative_does_not_cancel_current_explicit_condition(self):
        self.assertFalse(self.packet(user="My cells were not misplaced. My cells are misplaced.")["obligations"])


if __name__ == "__main__":
    unittest.main()
