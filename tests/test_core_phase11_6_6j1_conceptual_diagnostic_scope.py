"""Conceptual technical explanation is distinct from actual-setup diagnosis."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import find_user_diagnostic_overclaim_violations
from test_core_phase11_6_6_trust_integration import ScriptedClient, run


def contract(mode="stable_model_knowledge"):
    return AnswerContractRuntime(
        intent="factual_question", authority="stable_model_knowledge",
        epistemic_mode=mode, allow_new_factual_claims=True,
    )


def check(user, draft, history=(), mode="stable_model_knowledge"):
    return find_user_diagnostic_overclaim_violations(
        user, draft, contract(mode), list(history),
    )


def generation_count(client):
    return sum(not any("INTERNAL factual-answer source-fidelity verifier" in m["content"]
                       for m in call["messages"]) for call in client.calls)


def fidelity_count(client):
    return sum(any("INTERNAL factual-answer source-fidelity verifier" in m["content"]
                   for m in call["messages"]) for call in client.calls)


class ConceptualDiagnosticScopeTests(unittest.TestCase):
    def test_explain_what_component_does_is_conceptual(self):
        self.assertEqual(check("Explain what address rewriting does on a home router.",
                               "It operates at a logical network boundary alongside the firewall."), [])

    def test_what_does_mechanism_do_is_conceptual(self):
        self.assertEqual(check("What does mechanism Orin do on gateway Vela?",
                               "It logically sits between two networks and coordinates address mappings."), [])

    def test_function_question_can_mention_user_owned_component(self):
        self.assertEqual(check("What does address rewriting do on my router?",
                               "A router can place a firewall between network zones."), [])

    def test_how_component_works_is_conceptual(self):
        self.assertEqual(check("How does a router work?",
                               "Its logical network boundary can include a firewall."), [])

    def test_definition_request_is_conceptual(self):
        self.assertEqual(check("What is a router?",
                               "It forwards packets between networks; that role is separate from a firewall."), [])

    def test_generic_physical_example_is_not_actual_user_layout(self):
        self.assertEqual(check("Explain what wireless propagation does around a router.",
                               "Concrete absorbs some radio energy; this describes propagation in general."), [])

    def test_generic_topology_is_not_actual_user_layout(self):
        self.assertEqual(check("Explain what a router does between networks.",
                               "A gateway logically sits between network zones rather than a physical floor."), [])

    def test_new_concept_question_does_not_inherit_old_diagnosis(self):
        self.assertEqual(check("What does address rewriting do on a router?",
                               "It is distinct from firewall filtering.",
                               [{"role": "user", "content": "My router drops packets upstairs."}]), [])

    def test_current_failure_remains_a_diagnostic_task(self):
        self.assertTrue(check("Why does my connection fail when the router is upstairs?",
                              "The concrete wall is the cause of the signal loss."))

    def test_what_is_causing_does_not_become_definition(self):
        self.assertTrue(check("What is causing my router to lose signal?",
                              "The concrete wall is the cause."))

    def test_what_is_wrong_remains_diagnostic(self):
        self.assertTrue(check("What is wrong with my wireless connection?",
                              "A concrete wall blocks the signal."))

    def test_conceptual_prefix_does_not_erase_stated_failure(self):
        self.assertTrue(check("Explain what my router does when it fails upstairs.",
                              "The concrete wall is why the signal fails."))

    def test_firewall_is_not_a_physical_wall_in_diagnostic_context(self):
        self.assertEqual(check("My router drops packets. What should I test?",
                               "A firewall filters traffic by policy."), [])

    def test_floorplan_is_not_an_assertion_of_a_physical_floor(self):
        self.assertEqual(check("My router loses signal. What should I test?",
                               "A floorplan can document a network."), [])

    def test_firewall_in_user_context_does_not_authorize_a_wall(self):
        self.assertTrue(check("My router drops packets and has a firewall.",
                              "Your connection fails because a wall blocks it."))

    def test_floorplan_in_user_context_does_not_authorize_a_floor(self):
        self.assertTrue(check("My router loses signal; I have the floorplan.",
                              "Your floor blocks the signal."))

    def test_supplied_physical_detail_remains_available(self):
        self.assertEqual(check("My router is behind a concrete wall and loses signal.",
                               "The concrete wall can weaken radio signals."), [])

    def test_bounded_physical_hypothesis_remains_available(self):
        self.assertEqual(check("Why does my router lose signal upstairs?",
                               "One possibility is a concrete wall; that is not established by the symptom."), [])

    def test_unrelated_assistant_physical_detail_is_not_evidence(self):
        self.assertTrue(check("My router loses signal upstairs.",
                              "Your concrete wall blocks it.",
                              [{"role": "assistant", "content": "A concrete wall blocks your router."}]))

    def test_measured_followup_preserves_layout_guard(self):
        self.assertTrue(check("What does that reading rule out?",
                              "The concrete wall is definitely the cause.",
                              [{"role": "user", "content": "My router drops packets; I measured the signal upstairs."}]))

    def test_anaphoric_definition_shape_remains_diagnostic_followup(self):
        self.assertTrue(check("What is it then?",
                              "A concrete wall is blocking the signal.",
                              [{"role": "user", "content": "My router drops packets upstairs."}]))

    def test_anaphoric_function_shape_remains_diagnostic_followup(self):
        self.assertTrue(check("What does that do?",
                              "The steel is blocking your signal.",
                              [{"role": "user", "content": "My router drops packets upstairs."}]))

    def test_user_context_contract_still_guards_diagnosis(self):
        self.assertTrue(check("Why does my router lose signal upstairs?",
                              "A concrete wall is blocking it.", mode="user_context_reasoning"))

    def test_public_verified_contract_still_guards_diagnosis(self):
        self.assertTrue(check("Why does my router lose signal upstairs?",
                              "A concrete wall is blocking it.", mode="public_source_verified"))


class ConceptualDiagnosticProductionTests(unittest.TestCase):
    def publish(self, client, user, history=()):
        return run(client, user, contract(), history, {
            "find_user_diagnostic_overclaim_violations": find_user_diagnostic_overclaim_violations,
        })

    def test_real_stable_producer_publishes_conceptual_explanation_unchanged(self):
        text = "Address rewriting maps addresses at a logical network boundary; a firewall applies traffic policy."
        client = ScriptedClient([text], fidelity=[{"faithful": True, "violations": []}])
        result = self.publish(client, "Explain what address rewriting does on a home router.")
        self.assertEqual(result[0], text)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": text})
        self.assertEqual(generation_count(client), 1)
        self.assertEqual(fidelity_count(client), 1)

    def test_definition_with_generic_topology_remains_unchanged(self):
        text = "A router forwards packets between networks and can operate alongside a firewall."
        client = ScriptedClient([text], fidelity=[{"faithful": True, "violations": []}])
        self.assertEqual(self.publish(client, "What is a router?")[0], text)
        self.assertEqual(generation_count(client), 1)
        self.assertEqual(fidelity_count(client), 1)

    def test_old_diagnostic_history_does_not_reject_a_new_concept(self):
        text = "Address mapping is separate from firewall policy."
        client = ScriptedClient([text], fidelity=[{"faithful": True, "violations": []}])
        result = self.publish(client, "What does address rewriting do on a router?", [
            {"role": "user", "content": "My router loses signal upstairs."},
        ])
        self.assertEqual(result[0], text)
        self.assertEqual(generation_count(client), 1)

    def test_actual_diagnosis_rejects_layout_despite_positive_semantic_verdict(self):
        bad = "Your connection fails because a concrete wall blocks the signal."
        good = "The symptom alone does not identify the cause. Compare the same device near the source."
        client = ScriptedClient([bad, good], fidelity=[
            {"faithful": True, "violations": []}, {"faithful": True, "violations": []},
        ])
        result = self.publish(client, "Why does my connection fail when the router is upstairs?")
        self.assertEqual(result[0], good)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual(generation_count(client), 2)
        self.assertEqual(fidelity_count(client), 2)

    def test_every_retry_rechecks_actual_layout(self):
        first = "A concrete wall is causing your router's signal loss."
        second = "The steel between you and the router is causing it."
        good = "We need a controlled comparison before identifying the cause."
        client = ScriptedClient([first, second, good], fidelity=[
            {"faithful": True, "violations": []} for _ in range(3)
        ])
        result = self.publish(client, "Why is my router losing signal upstairs?")
        self.assertEqual(result[0], good)
        self.assertNotIn(first, [item["content"] for item in result[1]])
        self.assertNotIn(second, [item["content"] for item in result[1]])
        self.assertEqual(generation_count(client), 3)
        self.assertEqual(fidelity_count(client), 3)


if __name__ == "__main__":
    unittest.main()
