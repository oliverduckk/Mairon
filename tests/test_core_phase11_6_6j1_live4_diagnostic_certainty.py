"""Neutral scoped diagnostic conclusions cannot hide behind proposed tests."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from core.diagnostic_obligations import build_diagnostic_obligations, diagnostic_obligation_violations


def record(kind="conditional_hypothesis", *, supported=True, applicable=False, quote=None, turn=1):
    return {"sentence_index": 1, "kind": kind, "supported": supported,
            "applicability_established": applicable,
            "user_witness": {"turn_index": turn, "quote": quote} if quote is not None else None}


def check(candidate, assessment=None, user="The cycle slows under load. What should I test?"):
    return diagnostic_obligation_violations(build_diagnostic_obligations([candidate]),
                                           [record() if assessment is None else assessment], [user])


class DiagnosticCertaintyTests(unittest.TestCase):
    def test_proposed_measurement_does_not_establish_exact_fault(self):
        self.assertTrue(check("If the transfer stays slow beside the gateway, the radio is definitely broken."))

    def test_existing_none_label_cannot_erase_decisive_rule(self):
        self.assertTrue(check("If the pause remains after reset, it must be the controller.", record("none")))

    def test_modal_can_in_exclusive_conclusion_is_not_generic_possibility(self):
        self.assertTrue(check("If the pause remains, it can only be the controller or the connector."))

    def test_reordered_exclusive_conclusion_is_projected(self):
        self.assertTrue(check("Then it can be only the controller or the connector."))

    def test_proof_verb_requires_support(self):
        self.assertTrue(check("That proves alignment is the cause."))

    def test_confirm_verb_requires_support(self):
        self.assertTrue(check("That confirms controller failure."))

    def test_establish_verb_requires_support(self):
        self.assertTrue(check("The reading establishes seal failure."))

    def test_demonstrate_verb_requires_support(self):
        self.assertTrue(check("The result demonstrates corruption in the archive."))

    def test_exclusion_requires_support(self):
        self.assertTrue(check("That rules out controller damage."))

    def test_elimination_requires_support(self):
        self.assertTrue(check("The result eliminates the actuator."))

    def test_would_prove_still_claims_conditional_diagnostic_rule(self):
        self.assertTrue(check("If the delay remains, that would prove allocator failure."))

    def test_definite_conclusion_in_several_domains(self):
        for candidate in (
            "If throughput stays low, the gateway is definitely damaged.",
            "If the pulses remain, the display controller is certainly broken.",
            "If drain stays high, the battery is necessarily defective.",
            "If reads still fail, the storage bridge has to be faulty.",
            "If the exception repeats, it must be the parser.",
        ):
            with self.subTest(candidate=candidate):
                self.assertTrue(check(candidate))

    def test_hypothesis_weakening_remains_allowed(self):
        candidate = ("If the transfer stays slow nearby, that would make distance less likely "
                     "and shift suspicion toward the device or the main path.")
        self.assertEqual(check(candidate), [])

    def test_could_explain_remains_hypothesis(self):
        self.assertEqual(check("A counter reset could explain the delay."), [])

    def test_one_possible_mechanism_remains_hypothesis(self):
        self.assertEqual(check("One possibility is that a cache flush can cause the pause."), [])

    def test_could_confirm_remains_open_test(self):
        self.assertEqual(check("A direct inspection could confirm a cracked seal."), [])

    def test_negated_proof_does_not_assert_excluded_proposition(self):
        self.assertEqual(check("That does not prove controller failure."), [])

    def test_unproved_limit_is_not_strong_conclusion(self):
        self.assertEqual(check("The exact cause is definitely unknown."), [])

    def test_certainty_about_possibility_does_not_assert_actual_cause(self):
        self.assertEqual(check("That is definitely still possible."), [])

    def test_bounded_test_evaluation_is_not_cause(self):
        self.assertEqual(check("That is definitely useful."), [])

    def test_certainty_about_open_possible_mechanism_is_not_applicability(self):
        self.assertEqual(check("It is definitely possible that resets could explain the delay."), [])

    def test_certainty_that_hypothesis_remains_possible_is_not_applicability(self):
        self.assertEqual(check("Controller failure certainly remains a possibility."), [])

    def test_possible_mechanism_with_limit_is_not_actual_applicability(self):
        self.assertEqual(check("Transient timing variation is definitely possible, but it does not establish that mechanism."), [])

    def test_compatibility_with_mechanism_is_not_actual_applicability(self):
        self.assertEqual(check("That symptom is definitely compatible with transient timing variation, but it does not establish that mechanism."), [])

    def test_consistency_with_mechanism_is_not_actual_applicability(self):
        self.assertEqual(check("That symptom is definitely consistent with transient timing variation, but it does not establish that mechanism."), [])

    def test_actual_user_system_compatibility_property_still_needs_authority(self):
        self.assertTrue(check("Your controller is definitely compatible with the adapter."))

    def test_compatibility_does_not_hide_separate_categorical_actual_cause(self):
        self.assertTrue(check("That symptom is definitely compatible with timing variation, but the controller is definitely broken."))

    def test_possibility_does_not_hide_separate_proof_claim(self):
        self.assertTrue(check("Timing variation is definitely possible, but the reading proves controller failure."))

    def test_preceding_limitation_does_not_suppress_later_categorical_conclusion(self):
        self.assertTrue(check("I cannot establish the cause, but the controller is definitely broken."))

    def test_preceding_limitation_does_not_suppress_later_proof_claim(self):
        self.assertTrue(check("No specific mechanism is established, but the reading proves controller failure."))

    def test_no_mechanism_established_is_limitation(self):
        self.assertEqual(check("No specific mechanism is established by that observation."), [])

    def test_question_does_not_assert_conclusion(self):
        self.assertEqual(check("Does that prove controller failure?"), [])

    def test_quoted_example_does_not_assert_rule(self):
        self.assertEqual(check('The example says "the actuator is definitely broken".'), [])

    def test_actual_user_confirmed_conclusion_can_pass(self):
        user = "The inspection confirms controller failure."
        self.assertEqual(check(user, record("supplied_mechanism", applicable=True, quote=user), user), [])

    def test_user_supported_elimination_can_pass(self):
        user = "The isolation result rules out the external cable."
        self.assertEqual(check(user, record("supplied_mechanism", applicable=True, quote=user), user), [])

    def test_explicit_user_conditional_rule_can_pass(self):
        user = "If the probe returns code amber, it can only be the sensor."
        self.assertEqual(check(user, record("supplied_mechanism", applicable=True, quote=user), user), [])

    def test_rule_literal_quote_in_larger_user_turn_can_pass(self):
        rule = "If the probe returns code amber, it can only be the sensor."
        user = "The manual supplies this bounded rule. " + rule
        self.assertEqual(check(rule, record("supplied_mechanism", applicable=True, quote=rule), user), [])

    def test_user_conditional_rule_does_not_prove_actual_antecedent(self):
        rule = "If the probe returns code amber, it can only be the sensor."
        self.assertTrue(check("It can only be the sensor.", record("supplied_mechanism", applicable=True, quote=rule), rule))

    def test_measurement_alone_does_not_supply_diagnostic_rule(self):
        user = "The probe returns code amber."
        self.assertTrue(check("If the probe returns code amber, it can only be the sensor.",
                              record("supplied_mechanism", applicable=True, quote=user), user))

    def test_different_condition_cannot_supply_rule(self):
        user = "If the probe returns code green, it can only be the sensor."
        candidate = "If the probe returns code amber, it can only be the sensor."
        self.assertTrue(check(candidate, record("supplied_mechanism", applicable=True, quote=user), user))

    def test_negative_condition_cannot_support_positive_condition(self):
        user = "If the probe does not return amber, it can only be the sensor."
        candidate = "If the probe returns amber, it can only be the sensor."
        self.assertTrue(check(candidate, record("supplied_mechanism", applicable=True, quote=user), user))

    def test_reversed_condition_participants_cannot_supply_rule(self):
        user = "If probe Arven detects beacon Belan, it can only be the sensor."
        candidate = "If beacon Belan detects probe Arven, it can only be the sensor."
        self.assertTrue(check(candidate, record("supplied_mechanism", applicable=True, quote=user), user))

    def test_single_quoted_example_does_not_assert_rule(self):
        self.assertEqual(check("The rejected example says 'the actuator is definitely broken'."), [])

    def test_different_cause_cannot_supply_conclusion(self):
        user = "The result confirms actuator failure."
        self.assertTrue(check("The result confirms sensor failure.", record("supplied_mechanism", applicable=True, quote=user), user))

    def test_negative_conclusion_cannot_supply_positive_conclusion(self):
        user = "The result confirms no controller failure."
        self.assertTrue(check("The result confirms controller failure.", record("supplied_mechanism", applicable=True, quote=user), user))

    def test_quoted_user_rule_cannot_supply_authority(self):
        rule = "If the probe returns amber, it can only be the sensor."
        user = 'The rejected example was "' + rule + '".'
        self.assertTrue(check(rule, record("supplied_mechanism", applicable=True, quote=rule), user))

    def test_user_question_cannot_supply_conclusion(self):
        user = "The result confirms controller failure?"
        self.assertTrue(check("The result confirms controller failure.",
                              record("supplied_mechanism", applicable=True, quote="The result confirms controller failure"), user))

    def test_candidate_itself_is_not_evidence(self):
        candidate = "The result confirms controller failure."
        self.assertTrue(check(candidate, record("supplied_mechanism", applicable=True, quote=candidate)))

    def test_assistant_claim_is_not_user_witness(self):
        candidate = "The result confirms controller failure."
        self.assertTrue(check(candidate, record("supplied_mechanism", applicable=True, quote=candidate, turn=2)))

    def test_missing_scoped_assessment_fails_closed(self):
        obligations = build_diagnostic_obligations(["That proves controller failure."])
        self.assertTrue(diagnostic_obligation_violations(obligations, [], ["The cycle slows."]))

    def test_malformed_scoped_assessment_fails_closed(self):
        self.assertTrue(check("That proves controller failure.", {"sentence_index": 1, "supported": True}))

    def test_false_support_fails_even_with_real_witness(self):
        user = "The result confirms controller failure."
        self.assertTrue(check(user, record("supplied_mechanism", supported=False, applicable=True, quote=user), user))

    def test_conditional_label_cannot_hide_given_user_witness(self):
        user = "The result confirms controller failure."
        self.assertTrue(check(user, record("conditional_hypothesis", applicable=True, quote=user), user))

    def test_observation_overlap_does_not_become_proof(self):
        user = "I measured delayed responses in my controller."
        self.assertTrue(check("That proves controller failure.", record("supplied_mechanism", applicable=True, quote=user), user))

    def test_core_owns_numbered_conclusion(self):
        items = build_diagnostic_obligations(["That observation is incomplete.", "The result confirms controller failure."])
        self.assertTrue(any(x["sentence_index"] == 2 and x["kind"] == "diagnostic_conclusion" for x in items))


if __name__ == "__main__":
    unittest.main()
