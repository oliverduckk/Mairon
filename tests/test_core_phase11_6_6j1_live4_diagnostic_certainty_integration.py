"""Real publication retry path retains bounded diagnostic uncertainty."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from test_core_phase11_6_6_trust_integration import ScriptedClient, run
from test_core_phase11_6_6b_semantic_authority_integration import LIVE, assessment, faithful
from core.claim_grounding import build_user_context_reasoning_fallback


USER = "The processing cycle slows during transfers. What should I test first?"
GOOD = "Try comparing the same transfer before and after a reset; the observation alone does not identify a cause."


def call_kinds(client):
    result = []
    for call in client.calls:
        system = "\n".join(m["content"] for m in call["messages"] if m["role"] == "system")
        if "INTERNAL factual-answer source-fidelity verifier" in system:
            result.append("fidelity")
        elif "INTERNAL claim-grounding verifier" in system:
            result.append("core")
        else:
            result.append("generation")
    return result


class DiagnosticCertaintyProductionTests(unittest.TestCase):
    def assert_published(self, result, good, *bad):
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": good})
        for candidate in bad:
            self.assertNotIn(candidate, [x["content"] for x in result[1]])

    def test_positive_global_and_none_cannot_publish_categorical_test_conclusion(self):
        bad = "If the transfer stays slow after reset, the controller is definitely broken."
        client = ScriptedClient([bad, GOOD], fidelity=[faithful(assessment()), faithful(assessment())])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)
        self.assertEqual(call_kinds(client), ["generation", "fidelity", "generation", "fidelity"])

    def test_false_conditional_label_cannot_publish_exclusive_causes(self):
        bad = "If the transfer stays slow, then it can only be the controller or the connector."
        client = ScriptedClient([bad, GOOD], fidelity=[
            faithful(assessment("conditional_hypothesis")), faithful(assessment()),
        ])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)
        self.assertEqual(call_kinds(client).count("generation"), 2)
        self.assertEqual(call_kinds(client).count("fidelity"), 2)

    def test_proof_of_actual_fault_requires_more_than_symptom_quote(self):
        bad = "The slow cycle proves controller failure."
        client = ScriptedClient([bad, GOOD], fidelity=[faithful(assessment(
            "supplied_mechanism", applicable=True, witness={"turn_index": 1, "quote": USER},
        )), faithful(assessment())])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)

    def test_every_retry_retains_core_conclusion_projection(self):
        first = "If the transfer stays slow, the controller is definitely broken."
        second = "Then it can only be the connector."
        client = ScriptedClient([first, second, GOOD], fidelity=[
            faithful(assessment()), faithful(assessment("conditional_hypothesis")), faithful(assessment()),
        ])
        self.assert_published(run(client, USER, LIVE), GOOD, first, second)
        self.assertEqual(call_kinds(client), ["generation", "fidelity"] * 3)

    def test_all_bad_conclusions_use_existing_bounded_fallback(self):
        bad = "Then it can only be the controller."
        client = ScriptedClient([bad] * 3, fidelity=[faithful(assessment())] * 3)
        result = run(client, USER, LIVE, overrides={"build_user_context_reasoning_fallback": build_user_context_reasoning_fallback})
        self.assertNotEqual(result[0], bad)
        self.assertTrue(result[0].strip())
        self.assertNotIn(bad, [x["content"] for x in result[1]])
        self.assertEqual(call_kinds(client), ["generation", "fidelity"] * 3)

    def test_weakening_hypothesis_publishes_unchanged_without_extra_call(self):
        good = ("If it remains slow nearby, that would make distance less likely "
                "and shift suspicion toward the device or the main path.")
        client = ScriptedClient([good], fidelity=[faithful(assessment("conditional_hypothesis"))])
        self.assert_published(run(client, USER, LIVE), good)
        self.assertEqual(call_kinds(client), ["generation", "fidelity"])

    def test_compatible_hypothesis_with_epistemic_limit_publishes_unchanged(self):
        good = "That symptom is definitely compatible with transient timing variation, but it does not establish that mechanism."
        client = ScriptedClient([good], fidelity=[faithful(assessment("conditional_hypothesis"))])
        self.assert_published(run(client, USER, LIVE), good)
        self.assertEqual(call_kinds(client), ["generation", "fidelity"])

    def test_compatibility_cannot_hide_later_exact_fault_on_retry_path(self):
        bad = "That symptom is definitely compatible with timing variation, but the controller is definitely broken."
        client = ScriptedClient([bad, GOOD], fidelity=[faithful(assessment("conditional_hypothesis")), faithful(assessment())])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)
        self.assertEqual(call_kinds(client), ["generation", "fidelity"] * 2)

    def test_prior_limitation_cannot_hide_later_proof_on_retry_path(self):
        bad = "I cannot establish the cause, but the reading proves controller failure."
        client = ScriptedClient([bad, GOOD], fidelity=[faithful(assessment()), faithful(assessment())])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)
        self.assertEqual(call_kinds(client), ["generation", "fidelity"] * 2)

    def test_explicit_user_conditional_diagnostic_rule_can_publish(self):
        rule = "If the probe returns amber, it can only be the sensor."
        user = "Explain this diagnostic rule. " + rule
        client = ScriptedClient([rule], fidelity=[faithful(assessment(
            "supplied_mechanism", applicable=True, witness={"turn_index": 1, "quote": rule},
        ))])
        self.assert_published(run(client, user, LIVE), rule)
        self.assertEqual(call_kinds(client), ["generation", "fidelity"])

    def test_user_supported_bounded_elimination_remains_available(self):
        conclusion = "The isolation result rules out the external connector."
        user = conclusion + " Explain that result."
        client = ScriptedClient([conclusion], fidelity=[faithful(assessment(
            "supplied_mechanism", applicable=True, witness={"turn_index": 1, "quote": conclusion},
        ))])
        self.assert_published(run(client, user, LIVE), conclusion)
        self.assertEqual(call_kinds(client), ["generation", "fidelity"])

    def test_assistant_history_does_not_supply_diagnostic_rule(self):
        bad = "The result confirms controller failure."
        history = [{"role": "assistant", "content": bad}]
        client = ScriptedClient([bad, GOOD], fidelity=[faithful(assessment(
            "supplied_mechanism", applicable=True, witness={"turn_index": 1, "quote": bad},
        )), faithful(assessment())])
        result = run(client, USER, LIVE, history)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": GOOD})

    def test_missing_scoped_state_does_not_publish_invalid_conclusion(self):
        bad = "The result proves actuator failure."
        client = ScriptedClient([bad, GOOD], fidelity=[{"faithful": True, "violations": []}, faithful(assessment())])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)
        self.assertEqual(call_kinds(client), ["generation", "fidelity", "generation", "fidelity"])

    def test_malformed_scoped_state_does_not_publish_invalid_conclusion(self):
        bad = "The result proves actuator failure."
        malformed = faithful({"sentence_index": 1, "kind": "none", "supported": "yes"})
        client = ScriptedClient([bad, GOOD], fidelity=[malformed, faithful(assessment())])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)

    def test_positive_global_cannot_hide_different_conclusion_with_valid_user_rule(self):
        rule = "If the probe returns amber, it can only be the sensor."
        bad = "If the probe returns amber, it can only be the actuator."
        client = ScriptedClient([bad, GOOD], fidelity=[faithful(assessment(
            "supplied_mechanism", applicable=True, witness={"turn_index": 1, "quote": rule},
        )), faithful(assessment())])
        self.assert_published(run(client, rule, LIVE), GOOD, bad)

    def test_new_obligation_is_in_existing_verifier_packet(self):
        bad = "The result proves actuator failure."
        client = ScriptedClient([bad, GOOD], fidelity=[faithful(assessment()), faithful(assessment())])
        self.assert_published(run(client, USER, LIVE), GOOD, bad)
        verifier = client.calls[1]
        packet = "\n".join(m["content"] for m in verifier["messages"])
        self.assertIn('"kind": "diagnostic_conclusion"', packet)
        self.assertIn('"predicate": "conclusion"', packet)
        self.assertEqual(call_kinds(client), ["generation", "fidelity", "generation", "fidelity"])


if __name__ == "__main__":
    unittest.main()
