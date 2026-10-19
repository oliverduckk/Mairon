"""Bounded physical contact/readiness authority at the Phase 11 checkpoint."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.claim_grounding import find_mairon_self_authority_violations


def violations(draft, user="The adapter is in the silver case.", history=()):
    return find_mairon_self_authority_violations(
        user_input=user, draft=draft, conversation=history,
    )


class PhysicalContactAuthorityTests(unittest.TestCase):
    def denied(self, draft, **kwargs):
        self.assertTrue(violations(draft, **kwargs), draft)

    def allowed(self, draft):
        self.assertEqual(violations(draft), [], draft)

    def test_readiness_complement_cannot_acquire_physical_contact(self):
        self.denied("I'll keep my paws off that silver case until you're ready for me to touch it again.")

    def test_typographic_readiness_uses_same_guard(self):
        self.denied("I’ll keep my hands off that cabinet until you’re ready for me to touch it again.")

    def test_when_ready_complement_cannot_acquire_contact(self):
        self.denied("When you are ready for me to touch the cabinet, let me know.")

    def test_once_ready_complement_cannot_acquire_inspection(self):
        self.denied("Once you're ready for me to inspect the cabinet, I'll be here.")

    def test_readiness_complement_cannot_acquire_charging(self):
        self.denied("I'll wait until you're ready for me to charge the cell again.")

    def test_direct_future_contact_requires_capability(self):
        self.denied("I'll touch the cabinet.")

    def test_direct_prior_contact_requires_event_authority(self):
        self.denied("I touched the cabinet before.")

    def test_again_does_not_create_prior_contact(self):
        self.denied("I'll touch that cabinet again.")

    def test_explicit_contact_capability_requires_ingress(self):
        self.denied("I can touch that cabinet.")

    def test_typographic_direct_contact_requires_capability(self):
        self.denied("I’ll touch that cabinet again.")

    def test_user_location_does_not_supply_capability(self):
        self.denied("When you're ready for me to touch it again, let me know.",
                    user="The adapter is in the cabinet.")

    def test_user_permission_does_not_supply_physical_capability(self):
        self.denied("I'll touch the cabinet.", user="You can touch my cabinet.")

    def test_assistant_history_does_not_supply_contact(self):
        self.denied("I'll touch the cabinet again.", history=[
            {"role": "assistant", "content": "I touched the cabinet earlier."},
        ])

    def test_candidate_own_narration_does_not_supply_contact(self):
        self.denied("I touched the cabinet before. I'll touch it again.")

    def test_known_future_physical_action_remains_guarded(self):
        self.denied("I'll inspect the cabinet.")

    def test_abstract_readiness_complement_remains_available(self):
        self.allowed("When you're ready for me to check the argument, let me know.")

    def test_touch_on_argument_is_discourse(self):
        self.allowed("I'll touch on your argument.")

    def test_touch_upon_reasoning_is_discourse(self):
        self.allowed("I can touch upon that reasoning.")

    def test_handle_wording_remains_available(self):
        self.allowed("I'll handle the wording.")

    def test_unrelated_abstract_capability_is_not_reclassified(self):
        self.allowed("I can hold an opinion without pretending it is your opinion.")

    def test_pure_body_metaphor_does_not_claim_actual_contact(self):
        self.allowed("I'll keep my paws off that argument.")

    def test_refraining_metaphor_without_contact_or_history_is_allowed(self):
        self.allowed("I'll keep my hands off that silver case.")

    def test_object_personification_remains_available(self):
        self.allowed("The silver case is guarding your adapter.")

    def test_negative_contact_is_not_a_capability_promise(self):
        self.allowed("I won't touch the cabinet.")

    def test_user_conditional_advice_is_not_assistant_contact(self):
        self.allowed("If you touch the cabinet later, check its label.")

    def test_explicit_counterfactual_body_remains_nonactual(self):
        self.allowed("If I had hands, I would touch the cabinet.")

    def test_counterfactual_readiness_does_not_claim_capability(self):
        self.allowed("If I had hands, I could wait until you're ready for me to touch the cabinet.")

    def test_quoted_contact_example_is_not_self_history(self):
        self.allowed('The example sentence is "I will touch the cabinet again."')

    def test_quoted_readiness_example_is_not_self_capability(self):
        self.allowed('The example sentence is "When you are ready for me to touch the cabinet, ask."')

    def test_conversation_scoped_recall_remains_available(self):
        self.allowed("I'll remember that the adapter is in the case for this conversation.")

    def test_contact_family_is_not_object_specific(self):
        self.denied("Once you're ready for me to touch your canvas, say so.")


if __name__ == "__main__":
    unittest.main()
