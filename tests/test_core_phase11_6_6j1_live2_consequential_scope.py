"""Consequential conditional procedures never select the user's applicability.

Neutral provider/jurisdiction fixtures exercise the existing public verifier
and production retry/publication path; no live research or extra model call.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.seriousness import find_consequential_role_violations
from research.consequential_obligations import consequential_claim_obligations
import test_core_phase11_6_6i_consequential_authority as unit
import test_core_phase11_6_6i_consequential_integration as production


USER = "I sent money to the wrong account. What should I do?"
SCOPED = "My provider is AlderPay. I am in Westhaven. My payment rail is CedarLine. " + USER
SCOPE = "Provider: AlderPay. Jurisdiction: Westhaven. Rail: CedarLine. "
GENERIC = production.GOOD
CONDITIONAL = "If it is an intra-provider transfer, they'll handle it."
OTHER = "For inter-provider transfers, you might have to contact the other provider."
OUTCOME = "They'll handle it."


def verify(text, *, user=USER, body=None, scoped=True, source_updates=None, conversation=None):
    body = body or SCOPE + text
    state = unit.packet(body, **(source_updates or {}))
    assessments = unit.assessments(text, quote=body) if scoped else None
    return unit.verify(text, user, state, assessments, conversation=conversation)


class ConditionalConsequentialScopeTests(unittest.TestCase):
    def assert_rejected(self, text, **kwargs):
        result, client = verify(text, **kwargs)
        self.assertTrue(result)
        self.assertEqual(result.accepted_sentences, [])
        self.assertEqual(len(client.calls), 1)
        return result

    def test_conditional_provider_outcome_creates_existing_scoped_obligations(self):
        items = consequential_claim_obligations([CONDITIONAL])
        self.assertIn("specific_procedure", [item["kind"] for item in items])
        self.assertIn("certain_outcome", [item["kind"] for item in items])

    def test_conditional_bank_outcome_does_not_become_nonassertive(self):
        self.assert_rejected("If it is an intra-bank transfer, they'll handle it.")

    def test_same_provider_conditional_cannot_choose_unknown_user_scope(self):
        result = self.assert_rejected(CONDITIONAL)
        self.assertIn("user_applicability_scope_unavailable", " ".join(result))

    def test_other_provider_instruction_is_not_a_generic_first_step(self):
        self.assertTrue(consequential_claim_obligations([OTHER]))
        self.assert_rejected(OTHER)

    def test_contact_recipient_institution_requires_applicability(self):
        self.assert_rejected("Contact the recipient's institution.")

    def test_contact_receiving_bank_requires_applicability(self):
        self.assert_rejected("Call the receiving bank.")

    def test_generic_contact_cannot_hide_other_institution_tail(self):
        self.assert_rejected("Contact your sending provider and the other provider.")

    def test_contracted_pronoun_guarantee_requires_applicability(self):
        self.assert_rejected(OUTCOME)

    def test_typographic_contracted_guarantee_requires_applicability(self):
        self.assert_rejected("They’ll resolve it.")

    def test_expanded_pronoun_outcome_requires_applicability(self):
        self.assert_rejected("They will handle it.")

    def test_institutional_guarantee_requires_applicability(self):
        self.assert_rejected("Your provider will resolve the transaction.")

    def test_conditional_nonfinancial_procedure_has_same_policy(self):
        text = "If the document was issued locally, submit Form Ravon."
        result, _ = unit.verify(text, "My identity document is missing. What should I do?",
                               unit.packet(SCOPE + text), unit.assessments(text, quote=SCOPE + text),
                               domain="identity_document")
        self.assertTrue(result)

    def test_unknown_scope_fails_even_with_every_scoped_verdict_positive(self):
        self.assert_rejected(CONDITIONAL)

    def test_missing_scoped_assessments_fail_closed(self):
        result = self.assert_rejected(CONDITIONAL, scoped=False)
        self.assertIn("invalid_consequential_assessments", " ".join(result))

    def test_matching_user_scope_and_literal_body_can_support_conditional_procedure(self):
        result, client = verify(CONDITIONAL, user=SCOPED)
        self.assertFalse(result)
        self.assertEqual(result.accepted_sentences, [CONDITIONAL])
        self.assertEqual(len(client.calls), 1)

    def test_matching_user_scope_and_literal_body_can_support_other_provider_instruction(self):
        result, _ = verify(OTHER, user=SCOPED)
        self.assertFalse(result)

    def test_different_user_provider_cannot_inherit_source_procedure(self):
        self.assert_rejected(CONDITIONAL, user=SCOPED.replace("AlderPay", "BriarPay"))

    def test_different_user_jurisdiction_cannot_inherit_source_procedure(self):
        self.assert_rejected(OTHER, user=SCOPED.replace("Westhaven", "Eastmere"))

    def test_mixed_source_scopes_do_not_become_one_applicable_process(self):
        body = SCOPE + CONDITIONAL + " Provider: BriarPay. Jurisdiction: Eastmere."
        result = self.assert_rejected(CONDITIONAL, user=SCOPED, body=body)
        self.assertIn("source_applicability_scope_unavailable", " ".join(result))

    def test_matching_scope_cannot_promote_mere_possible_outcome_to_guarantee(self):
        result = self.assert_rejected(OUTCOME, user=SCOPED, body=SCOPE + "They may handle it.")
        self.assertIn("certain_outcome_witness_missing", " ".join(result))

    def test_literal_witness_must_come_from_readable_admitted_body(self):
        self.assert_rejected(CONDITIONAL, user=SCOPED, source_updates={"read_success": False})

    def test_rejected_body_cannot_supply_procedure(self):
        self.assert_rejected(CONDITIONAL, user=SCOPED, source_updates={"accepted_as_evidence": False})

    def test_assistant_history_cannot_supply_applicability(self):
        self.assert_rejected(CONDITIONAL, conversation=[{"role": "assistant", "content": SCOPED}])

    def test_latest_user_scope_correction_wins(self):
        self.assert_rejected(CONDITIONAL, user="My provider is BriarPay. " + USER,
                             conversation=[{"role": "user", "content": SCOPED}])

    def test_generic_official_sending_provider_contact_stays_available(self):
        self.assertEqual(consequential_claim_obligations([GENERIC]), ())
        result, client = verify(GENERIC, scoped=False)
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_generic_uncertainty_question_to_provider_stays_available(self):
        text = "Ask your provider whether it can recover the payment."
        self.assertEqual(consequential_claim_obligations([text]), ())

    def test_conditional_generic_sending_provider_contact_stays_available(self):
        text = "If you need help, contact your sending provider through its official channel."
        self.assertEqual(consequential_claim_obligations([text]), ())

    def test_generic_details_record_does_not_invent_procedure(self):
        self.assertEqual(consequential_claim_obligations(["Keep records of your communication."]), ())

    def test_quoted_example_does_not_acquire_applicability(self):
        self.assertEqual(consequential_claim_obligations(['"They will handle it."']), ())

    def test_genuine_question_does_not_assert_provider_guarantee(self):
        self.assertEqual(consequential_claim_obligations(["Will they handle it?"]), ())

    def test_sender_contact_stays_sender_directed(self):
        self.assertFalse(find_consequential_role_violations(USER, GENERIC, domain="financial"))
        self.assertTrue(find_consequential_role_violations(USER, "Do not spend the money.", domain="financial"))


class ConsequentialProductionContinuationTests(unittest.TestCase):
    def assert_retry(self, bad, *, current=USER, evidence=None, verdict=None):
        evidence = evidence or production.retained(SCOPE + bad + " " + GENERIC)
        client = production.PublicAdviceClient([bad, GENERIC], [
            production.positive(bad, quote=SCOPE + bad) if verdict is None else verdict,
            production.positive(GENERIC),
        ])
        result, observations, _ = production.run(client, current, evidence=evidence)
        self.assertEqual(result[0], GENERIC)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": GENERIC})
        self.assertNotIn(bad, [message["content"] for message in result[1]])
        self.assertEqual(result[2:], (None, None))
        self.assertEqual((client.generations, client.verifications), (2, 2))
        self.assertEqual(len(client.calls), 4)
        self.assertFalse(observations, "Consequential advice remains outside public-generated shadow migration")
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def test_real_producer_rejects_conditional_provider_guarantee(self):
        self.assert_retry(CONDITIONAL)

    def test_real_producer_rejects_other_institution_instruction(self):
        self.assert_retry(OTHER)

    def test_real_producer_rejects_pronoun_guarantee(self):
        self.assert_retry(OUTCOME)

    def test_real_producer_rejects_global_positive_without_scoped_assessment(self):
        self.assert_retry(CONDITIONAL, verdict=production.positive(CONDITIONAL, scoped=False))

    def test_real_producer_rejects_mismatching_user_provider(self):
        self.assert_retry(CONDITIONAL, current=SCOPED.replace("AlderPay", "BriarPay"))

    def test_real_producer_preserves_supported_matching_conditional(self):
        evidence = production.retained(SCOPE + CONDITIONAL)
        client = production.PublicAdviceClient([CONDITIONAL], [
            production.positive(CONDITIONAL, quote=SCOPE + CONDITIONAL),
        ])
        result, observations, _ = production.run(client, SCOPED, evidence=evidence)
        self.assertEqual(result[0], CONDITIONAL)
        self.assertEqual(result[1][-1]["content"], CONDITIONAL)
        self.assertEqual((client.generations, client.verifications), (1, 1))
        self.assertFalse(observations)

    def test_real_producer_preserves_generic_contact_without_scope(self):
        client = production.PublicAdviceClient([GENERIC], [production.positive(GENERIC)])
        result, observations, _ = production.run(client, USER)
        self.assertEqual(result[0], GENERIC)
        self.assertEqual((client.generations, client.verifications), (1, 1))
        self.assertFalse(observations)

    def test_every_retry_gets_scoped_protocol_without_new_loop(self):
        client = self.assert_retry(CONDITIONAL)
        calls = [call for call in client.calls if "format" in call]
        self.assertEqual(len(calls), 2)
        self.assertIn("consequential_assessments", calls[0]["format"]["required"])


if __name__ == "__main__":
    unittest.main()
