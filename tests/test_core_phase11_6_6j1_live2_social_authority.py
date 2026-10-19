"""Neutral recurrence, intention and incidental creative-credit authority."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.claim_grounding import find_incidental_public_attribution_violations
from core.user_history_obligations import (
    build_user_history_packet, validate_user_history_assessments,
)

REPEAT = "You're checking that again."
MOTIVE = "I think you're just trying to see if I will change the label."
CREDIT = "That lets you appreciate Ruvan's actual artistry."
CONTRACT = "Intent: casual_conversation\nAuthority: user_turn\nAllow new factual claims: false"


def packet(candidate=REPEAT, user="Hello.", extra=None):
    return build_user_history_packet(candidate, {"current_user": user} | (extra or {}))


def positive(value, quote="Hello.", source_id="current_user"):
    return {"supported": True, "history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id, "source_quote": quote}
        for item in value["obligations"]
    ]}


class RecurrenceAndIntentionAuthorityTests(unittest.TestCase):
    def unsupported(self, candidate=REPEAT, user="Hello.", extra=None):
        value = packet(candidate, user, extra)
        self.assertTrue(value["obligations"], value)
        self.assertTrue(validate_user_history_assessments(positive(value, user), value))
        return value

    def supported(self, candidate, user, extra=None):
        value = packet(candidate, user, extra)
        self.assertFalse(value["obligations"], value)
        self.assertTrue(value["core_witnessed"], value)
        return value

    def test_current_progressive_again_requires_prior_user_act(self):
        self.unsupported()

    def test_name_testing_question_keeps_prior_act_presupposition(self):
        value = self.unsupported("You're testing my label again?")
        self.assertEqual(value["obligations"][0]["kind"], "personal_prior_act")
        self.assertEqual(value["obligations"][0]["mode"], "presupposed")

    def test_arbitrary_activity_recurrence_is_not_verb_specific(self):
        self.unsupported("You're indexing the ledger again.")

    def test_matching_user_prior_event_witnesses_recurrence(self):
        self.supported(REPEAT, "I checked that before.")

    def test_matching_user_progressive_recurrence_witnesses_prior_act(self):
        self.supported(REPEAT, "I'm checking that again.")

    def test_matching_user_participant_direction_is_normalised(self):
        self.supported("You're testing my label again.", "I tested your label before.")

    def test_reversed_participant_does_not_match(self):
        self.unsupported("You're testing my label again.", "You tested my label before.")

    def test_different_user_activity_does_not_supply_prior_act(self):
        self.unsupported(REPEAT, "I repaired that before.")

    def test_different_object_does_not_supply_prior_act(self):
        self.unsupported(REPEAT, "I checked the cabinet before.")

    def test_unrelated_prior_user_event_does_not_supply_act(self):
        self.unsupported(extra={"prior_user_1": "I indexed the ledger before."})

    def test_assistant_prior_event_is_not_user_authority(self):
        value = self.unsupported(extra={"prior_assistant_1": "You checked that before."})
        self.assertNotIn("prior_assistant_1", value["sources"])

    def test_candidate_is_not_its_own_prior_event(self):
        value = self.unsupported()
        self.assertTrue(validate_user_history_assessments(positive(value, REPEAT, "candidate"), value))

    def test_latest_user_did_not_correction_wins(self):
        old = "I checked that before."
        value = packet(REPEAT, "I did not check that before.", {"prior_user_1": old})
        self.assertTrue(value["obligations"])
        self.assertTrue(validate_user_history_assessments(positive(value, old, "prior_user_1"), value))

    def test_latest_user_contracted_denial_wins(self):
        old = "I tested your label before."
        value = packet("You're testing my label again?", "I didn't test your label before.", {"prior_user_1": old})
        self.assertTrue(value["obligations"])
        self.assertTrue(validate_user_history_assessments(positive(value, old, "prior_user_1"), value))

    def test_latest_prior_turn_denial_wins(self):
        old = "I checked that before."
        value = packet(REPEAT, "Hello.", {"prior_user_1": old, "prior_user_2": "I never checked that before."})
        self.assertTrue(value["obligations"])
        self.assertTrue(validate_user_history_assessments(positive(value, old, "prior_user_1"), value))

    def test_plain_question_without_recurrence_does_not_assert_prior_act(self):
        self.assertFalse(packet("Are you checking that?")["obligations"])

    def test_conditional_recurrence_does_not_assert_history(self):
        self.assertFalse(packet("If you're checking that again, use the reference.")["obligations"])

    def test_quoted_recurrence_does_not_assert_user_history(self):
        self.assertFalse(packet('The example says "You are checking that again."')["obligations"])

    def test_generic_object_personification_does_not_assert_user_act(self):
        self.assertFalse(packet("Your compiler is begging for mercy again.")["obligations"])

    def test_bare_acknowledgement_does_not_invent_user_history(self):
        self.assertFalse(packet("I'm here.")["obligations"])

    def test_global_positive_cannot_erase_prior_act_obligation(self):
        self.assertTrue(validate_user_history_assessments({"supported": True}, packet()))

    def test_malformed_history_assessment_fails_closed(self):
        value = packet()
        verdict = positive(value)
        verdict["history_assessments"][0]["supported"] = "true"
        self.assertTrue(validate_user_history_assessments(verdict, value))

    def test_first_person_think_does_not_authorise_attributed_user_motive(self):
        value = self.unsupported(MOTIVE)
        self.assertEqual(value["obligations"][0]["kind"], "user_intention_state")

    def test_matching_user_stated_motive_can_be_restated(self):
        self.supported(MOTIVE, "I'm just trying to see if you will change the label.")

    def test_topic_knowledge_does_not_supply_user_motive(self):
        self.unsupported(MOTIVE, "The display can change labels.")

    def test_different_user_motive_does_not_supply_current_motive(self):
        self.unsupported(MOTIVE, "I'm trying to see if you will save the document.")

    def test_assistant_claim_cannot_supply_user_motive(self):
        self.unsupported(MOTIVE, extra={"prior_assistant_1": MOTIVE})

    def test_latest_user_motive_denial_wins(self):
        old = "I'm just trying to see if you will change the label."
        current = "I'm not trying to see if you will change the label."
        value = packet(MOTIVE, current, {"prior_user_1": old})
        self.assertTrue(value["obligations"])
        self.assertTrue(validate_user_history_assessments(positive(value, old, "prior_user_1"), value))

    def test_hypothetical_user_motive_is_not_asserted(self):
        self.assertFalse(packet("If you're trying to see if I will change the label, ask.")["obligations"])

    def test_possible_user_motive_is_not_asserted(self):
        self.assertFalse(packet("You might be trying to see if I will change the label.")["obligations"])

    def test_quoted_motive_is_not_asserted(self):
        self.assertFalse(packet('The example says "You are trying to change the label."')["obligations"])


class IncidentalCreativeCreditAuthorityTests(unittest.TestCase):
    def violations(self, candidate=CREDIT, user="Please keep the two formats separate.", history=None):
        return find_incidental_public_attribution_violations(user, candidate, CONTRACT, history)

    def test_absent_single_name_modified_artistry_is_rejected(self):
        self.assertTrue(self.violations())

    def test_typographic_possessive_is_rejected(self):
        self.assertTrue(self.violations("You can appreciate Ruvan’s actual artistry."))

    def test_multiword_credit_with_modifier_is_rejected(self):
        self.assertTrue(self.violations("Appreciate Orin Vale's distinctive visual design."))

    def test_other_creative_noun_modifier_is_rejected(self):
        self.assertTrue(self.violations("Consider Telva's original writing."))

    def test_unmodified_artistry_is_a_credit(self):
        self.assertTrue(self.violations("That is Ruvan's artistry."))

    def test_user_supplied_credit_name_is_available(self):
        self.assertFalse(self.violations(user="Ruvan's artistry is what I mean; keep the formats separate."))

    def test_assistant_only_credit_name_is_not_authority(self):
        self.assertTrue(self.violations(history=[{"role": "assistant", "content": "Ruvan made it."}]))

    def test_explicit_credit_question_keeps_normal_factual_lane(self):
        self.assertFalse(self.violations(user="Who created the illustrations?"))

    def test_object_personification_is_not_creative_attribution(self):
        self.assertFalse(self.violations("Your compiler is begging for mercy."))

    def test_fantastical_noncredit_joke_is_not_real_world_credit(self):
        self.assertFalse(self.violations("The ledger escaped the shadow realm."))

    def test_ordinary_bounded_format_acknowledgement_is_unchanged(self):
        self.assertFalse(self.violations("Right, I'll keep those formats separate."))


if __name__ == "__main__":
    unittest.main()
