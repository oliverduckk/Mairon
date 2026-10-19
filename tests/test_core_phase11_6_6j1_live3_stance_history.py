"""Neutral ownership and recurrent/contrastive USER-history authority."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.stance_ownership import find_user_stance_echo_violations, build_stance_ownership_frame
from core.user_history_obligations import build_user_history_packet, validate_user_history_assessments


def contract(**changes):
    return AnswerContractRuntime(**({"intent": "share_opinion", "authority": "conversation",
        "epistemic_mode": "conversation", "allow_new_factual_claims": False} | changes))


USER = "The Aurelia cycle is still one of my favourite works."
SHARED = "So we do not accidentally pack the cell into the case again."
CONTRAST = "I am glad you did not leave the cell in the charger this time."


class StanceEchoAuthorityTests(unittest.TestCase):
    def check(self, draft, user=USER, **kwargs):
        return find_user_stance_echo_violations(draft, user, contract(), **kwargs)

    def test_possessive_user_favourite_cannot_be_echoed_as_assistant(self):
        self.assertTrue(self.check(USER))

    def test_user_attributed_possessive_is_allowed(self):
        self.assertFalse(self.check("The Aurelia cycle is still one of your favourite works."))

    def test_brief_acknowledgement_is_allowed(self):
        self.assertFalse(self.check("Noted."))

    def test_positive_opinion_verb_ownership(self):
        self.assertTrue(self.check("I reckon amber is easier to shape.", "I reckon amber is easier to shape."))

    def test_negative_opinion_verb_ownership(self):
        self.assertTrue(self.check("I don't believe amber is easier to shape.", "I don't believe amber is easier to shape."))

    def test_positive_preference_verb_ownership(self):
        self.assertTrue(self.check("I prefer the wool version.", "I prefer the wool version."))

    def test_negative_preference_verb_ownership(self):
        self.assertTrue(self.check("I dislike the wool version.", "I dislike the wool version."))

    def test_negative_possessive_favourite_is_owned(self):
        user = "The Aurelia cycle is not one of my favourite works."
        self.assertTrue(self.check(user, user))

    def test_contracted_negative_possessive_is_owned(self):
        user = "The Aurelia cycle isn't my favourite."
        self.assertTrue(self.check(user, user))

    def test_inverted_favourite_is_owned(self):
        user = "My favourite work is Aurelia."
        self.assertTrue(self.check(user, user))

    def test_least_favourite_is_owned(self):
        user = "Aurelia is my least favourite."
        self.assertTrue(self.check(user, user))

    def test_american_spelling_is_owned(self):
        user = "Aurelia is my favorite."
        self.assertTrue(self.check(user, user))

    def test_quote_retains_user_owner(self):
        self.assertFalse(self.check('You said, "' + USER + '"'))

    def test_conditional_preference_does_not_assert_ownership(self):
        self.assertFalse(self.check("If Aurelia is my favourite later, I'll say so."))

    def test_explicit_assistant_opinion_question_uses_existing_opinion_lane(self):
        self.assertFalse(self.check(USER, USER + " What do you think?"))

    def test_separate_prior_accepted_assistant_stance_remains_available(self):
        self.assertFalse(self.check(USER, accepted_opinion_entry={"stance_text": USER}))

    def test_unrelated_prior_assistant_stance_does_not_authorize_echo(self):
        self.assertTrue(self.check(USER, accepted_opinion_entry={"stance_text": "I prefer warm tea."}))

    def test_prior_assistant_polarity_does_not_authorize_opposite(self):
        self.assertTrue(self.check(USER, accepted_opinion_entry={"stance_text": "The Aurelia cycle is not one of my favourite works."}))

    def test_user_correction_changes_user_stance_only(self):
        user = "Actually, I now prefer basalt."
        self.assertTrue(self.check("I prefer basalt.", user))
        self.assertFalse(self.check("You now prefer basalt.", user))

    def test_unrelated_assistant_preference_not_a_transport_match(self):
        self.assertFalse(self.check("I prefer concise explanations."))

    def test_no_contract_grants_no_reinterpretation(self):
        self.assertFalse(find_user_stance_echo_violations(USER, USER))

    def test_public_source_lane_is_outside_social_echo_adapter(self):
        self.assertFalse(find_user_stance_echo_violations(USER, USER,
            contract(authority="public_web", epistemic_mode="public_source_verified_opinion")))

    def test_existing_explicit_ack_adapter_is_not_widened(self):
        self.assertIsNone(build_stance_ownership_frame("I reckon amber is easier to shape.", contract()))

    def test_too_does_not_supply_independent_stance(self):
        self.assertTrue(self.check("I prefer basalt too.", "I prefer basalt."))

    def test_structured_accepted_pairwise_stance_remains_available(self):
        entry = {"kind": "pairwise_comparison", "left": "amber", "right": "basalt",
                 "position": "right", "stance_text": "Basalt over amber, easy."}
        self.assertFalse(self.check("I prefer basalt over amber.", "I prefer basalt over amber.",
                                    accepted_opinion_entry=entry))

    def test_structured_stance_does_not_authorize_opposite_user_echo(self):
        entry = {"kind": "pairwise_comparison", "left": "amber", "right": "basalt",
                 "position": "right", "stance_text": "Basalt over amber, easy."}
        self.assertTrue(self.check("I prefer amber over basalt.", "I prefer amber over basalt.",
                                   accepted_opinion_entry=entry))


class RecurrenceContrastAuthorityTests(unittest.TestCase):
    def packet(self, candidate=SHARED, user="My cell is in the silver pouch.", prior=None):
        sources = {"current_user": user}
        if prior is not None:
            sources["prior_user_1"] = prior
        return build_user_history_packet(candidate, sources)

    def assert_unsupported(self, packet):
        self.assertTrue(packet["obligations"], packet)
        self.assertTrue(validate_user_history_assessments({"supported": True}, packet))

    def test_inclusive_negative_again_requires_shared_history(self):
        self.assert_unsupported(self.packet())

    def test_shared_prior_event_supports_shared_again(self):
        self.assertFalse(self.packet(user="We packed the cell into the case before.")["obligations"])

    def test_user_alone_prior_event_does_not_prove_shared_event(self):
        self.assert_unsupported(self.packet(user="I packed the cell into the case before."))

    def test_different_shared_object_does_not_supply_history(self):
        self.assert_unsupported(self.packet(user="We packed the cable into the case before."))

    def test_different_shared_action_does_not_supply_history(self):
        self.assert_unsupported(self.packet(user="We cleaned the cell into the case before."))

    def test_current_location_does_not_supply_prior_packing(self):
        self.assert_unsupported(self.packet(user="The cell is inside the case."))

    def test_latest_shared_negative_defeats_stale_positive(self):
        self.assert_unsupported(self.packet(user="We did not pack the cell into the case before.",
            prior="We packed the cell into the case before."))

    def test_future_avoidance_still_has_prior_again_premise(self):
        self.assert_unsupported(self.packet("We will not pack the cell into the case again."))

    def test_negative_this_time_requires_prior_positive_event(self):
        self.assert_unsupported(self.packet(CONTRAST))

    def test_prior_user_event_authorizes_negative_this_time(self):
        self.assertFalse(self.packet(CONTRAST, "I left the cell in the charger before.")["obligations"])

    def test_prior_negative_does_not_authorize_positive_prior_premise(self):
        self.assert_unsupported(self.packet(CONTRAST, "I did not leave the cell in the charger before."))

    def test_latest_denial_defeats_this_time_earlier_positive(self):
        self.assert_unsupported(self.packet(CONTRAST, "I never left the cell in the charger before.",
            prior="I left the cell in the charger before."))

    def test_decide_wrapper_does_not_erase_concrete_prior_action(self):
        self.assert_unsupported(self.packet("I am glad you did not decide to leave the cell in the charger this time."))

    def test_prior_action_does_not_prove_prior_decision(self):
        candidate = "I am glad you did not decide to leave the cell in the charger this time."
        self.assert_unsupported(self.packet(candidate, "I left the cell in the charger before."))

    def test_matching_prior_decision_supports_decision_contrast(self):
        candidate = "I am glad you did not decide to misfile the record this time."
        self.assertFalse(self.packet(candidate, "I decided to misfile the record before.")["obligations"])

    def test_positive_this_time_keeps_prior_negative_contrast(self):
        candidate = "You indexed the record this time."
        self.assertFalse(self.packet(candidate, "I did not index the record before.")["obligations"])

    def test_positive_this_time_not_supported_by_prior_positive(self):
        self.assert_unsupported(self.packet("You indexed the record this time.", "I indexed the record before."))

    def test_shared_negative_this_time_preserves_shared_actor(self):
        packet = self.packet("We did not leave the cell in the charger this time.")
        self.assert_unsupported(packet)
        self.assertEqual(packet["obligations"][0]["subject"], "@shared:user_assistant")

    def test_conditional_shared_recurrence_remains_nonassertive(self):
        self.assertFalse(self.packet("If we pack the cell into the case again, label it.")["obligations"])

    def test_conditional_this_time_remains_nonassertive(self):
        self.assertFalse(self.packet("If you did not leave the cell in the charger this time, say so.")["obligations"])

    def test_quoted_shared_recurrence_is_not_user_history(self):
        self.assertFalse(self.packet('The example reads "We do not pack the cell into the case again."')["obligations"])

    def test_object_personification_remains_available(self):
        self.assertFalse(self.packet("Your compiler is begging for mercy again.")["obligations"])

    def test_assistant_source_key_does_not_supply_history(self):
        packet = build_user_history_packet(SHARED, {"current_user": "Hello.",
            "prior_assistant_1": "We packed the cell into the case before."})
        self.assert_unsupported(packet)

    def test_candidate_cannot_authorize_itself(self):
        self.assert_unsupported(self.packet())

    def test_positive_global_cannot_erase_history_obligation(self):
        packet = self.packet()
        self.assertTrue(validate_user_history_assessments({"supported": True,
            "history_assessments": [{"index": 1, "supported": True,
                "source_id": "current_user", "source_quote": "My cell is in the silver pouch."}]}, packet))

    def test_wrong_actor_cannot_be_laundered_with_literal_positive_assessment(self):
        packet = self.packet(user="I packed the cell into the case before.")
        checks = [{"index": item["index"], "supported": True, "source_id": "current_user",
            "source_quote": packet["sources"]["current_user"]} for item in packet["obligations"]]
        self.assertTrue(validate_user_history_assessments({"history_assessments": checks}, packet))

    def test_malformed_history_assessment_fails_closed(self):
        self.assertTrue(validate_user_history_assessments({"history_assessments": ["yes"]}, self.packet()))


if __name__ == "__main__":
    unittest.main()
