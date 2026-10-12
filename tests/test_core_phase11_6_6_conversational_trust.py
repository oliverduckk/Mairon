"""User stance, speech acts and inferred causes do not create factual authority."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_acknowledgement_direction_violations,
    find_explicit_user_constraint_violations,
    should_verify_acknowledgement_grounding,
    should_verify_core_grounding,
    verify_core_grounded_draft,
    verify_factual_focus_fidelity,
)


class Client:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.verdict)))


SOCIAL = AnswerContractRuntime(
    intent="casual_conversation", speech_act="statement", authority="live_conversation",
    epistemic_mode="conversation", allow_new_factual_claims=False,
)
ACK = replace(SOCIAL, intent="acknowledge", speech_act="thanks", authority="conversation_model")
FACTUAL = replace(SOCIAL, intent="factual_question", speech_act="question",
                  epistemic_mode="stable_model_knowledge", allow_new_factual_claims=True)


def core(verdict, *, user="That hearing made me angry.", draft="That clearly upset you.",
         contract=SOCIAL, conversation=None, trust_context=None):
    client = Client(verdict)
    with patch("core.claim_grounding.find_deterministic_grounding_violations", return_value=[]):
        outcome = verify_core_grounded_draft(
            client=client, model="qwen-test", user_input=user, draft=draft,
            core_answer_contract=contract, conversation=conversation or [], trust_context=trust_context,
        )
    return outcome, client


def factual(verdict, *, trust_context=None, conversation=None):
    client = Client(verdict)
    outcome = verify_factual_focus_fidelity(
        client=client, model="qwen-test", user_input="The second measurement is much lower. What follows?",
        draft="That narrows the suspect path; it does not identify the exact cause.",
        core_answer_contract=FACTUAL, conversation=conversation or [], trust_context=trust_context,
    )
    return outcome, client


def prompt(client):
    return "\n".join(message["content"] for message in client.calls[0]["messages"])


class ConversationalTrustTests(unittest.TestCase):
    def test_pure_welcomes_remain_cheap(self):
        for reply in ("Anytime.", "You're welcome.", "No worries.", "Glad that helped.",
                      "Fine, you're welcome.", "You got it!", "Got it."):
            with self.subTest(reply=reply):
                self.assertFalse(should_verify_acknowledgement_grounding(ACK, reply))
                outcome, client = core({"supported": True}, user="Thanks", draft=reply, contract=ACK)
                self.assertEqual(outcome, [])
                self.assertEqual(client.calls, [])

    def test_legacy_acknowledgement_selector_remains_cheap(self):
        self.assertFalse(should_verify_core_grounding(ACK))

    def test_added_biography_makes_acknowledgement_rich(self):
        for reply in ("Anytime. You always forget to ask nicely.",
                      "No worries. Everyone else keeps ignoring you.",
                      "You're welcome; I watched you walk around earlier."):
            with self.subTest(reply=reply):
                self.assertTrue(should_verify_acknowledgement_grounding(ACK, reply))

    def test_rich_acknowledgement_uses_existing_verifier(self):
        outcome, client = core({"supported": False, "unsupported_claims": ["unseen recurring habit"]},
                               user="Thanks", draft="Anytime. You always forget to ask nicely.", contract=ACK)
        self.assertTrue(outcome)
        self.assertEqual(len(client.calls), 1)

    def test_thanks_direction_is_not_reversed(self):
        for reply in ("Thanks for that.", "Thank you for helping me.",
                      "Well, thanks for finally saying something.", "I appreciate your help."):
            with self.subTest(reply=reply):
                self.assertTrue(find_acknowledgement_direction_violations(
                    user_input="Thanks", draft=reply, core_answer_contract=ACK))

    def test_direction_check_does_not_police_non_thanks_acknowledgement(self):
        contract = replace(ACK, speech_act="acknowledgement")
        self.assertEqual(find_acknowledgement_direction_violations(
            user_input="Got it", draft="Thanks for checking.", core_answer_contract=contract), [])

    def test_direction_check_does_not_police_other_turns(self):
        self.assertEqual(find_acknowledgement_direction_violations(
            user_input="Here is the measured data", draft="Thanks for measuring it.",
            core_answer_contract=SOCIAL), [])

    def test_direction_failure_requires_no_model_call(self):
        outcome, client = core({"supported": True}, user="Thank you", draft="Thanks for the help.", contract=ACK)
        self.assertTrue(outcome)
        self.assertEqual(client.calls, [])

    def test_pure_ack_grammar_cannot_hide_factual_tail(self):
        self.assertTrue(should_verify_acknowledgement_grounding(ACK, "No worries, your colleague hates you."))

    def test_positive_verdict_cannot_override_negative_claim(self):
        outcome, _ = core({"supported": True, "unsupported_claims": ["unseen event motive"]})
        self.assertTrue(outcome)
        self.assertIn("unseen event motive", " ".join(outcome))

    def test_multiple_negative_claims_survive_positive_global_verdict(self):
        outcome, _ = core({"supported": True, "unsupported_claims": ["unseen motive", "future outcome"]})
        self.assertEqual(len(outcome), 2)

    def test_negative_relation_survives_positive_global_verdict(self):
        outcome, _ = core({"supported": True, "source_faithful": False, "unsupported_claims": []})
        self.assertTrue(outcome)

    def test_negative_relevance_survives_positive_global_verdict(self):
        outcome, _ = core({"supported": True, "relevant": False, "unsupported_claims": []})
        self.assertTrue(outcome)

    def test_negative_speech_act_survives_positive_global_verdict(self):
        outcome, _ = core({"supported": True, "speech_act_faithful": False, "unsupported_claims": []})
        self.assertTrue(outcome)

    def test_malformed_verdict_is_never_truthy_authority(self):
        for verdict in ("true", 1, None, [], {}):
            with self.subTest(verdict=verdict):
                outcome, _ = core({"supported": verdict, "unsupported_claims": []})
                self.assertTrue(outcome)

    def test_malformed_optional_flag_is_not_ignored(self):
        for key in ("source_faithful", "relevant", "speech_act_faithful"):
            with self.subTest(key=key):
                outcome, _ = core({"supported": True, key: "false", "unsupported_claims": []})
                self.assertTrue(outcome)

    def test_malformed_negative_claim_container_cannot_pass(self):
        for claims in ("unsupported event", None, {}, [3], [""]):
            with self.subTest(claims=claims):
                outcome, _ = core({"supported": True, "unsupported_claims": claims})
                self.assertTrue(outcome)

    def test_old_success_protocol_remains_compatible(self):
        outcome, _ = core({"supported": True, "unsupported_claims": []})
        self.assertEqual(outcome, [])

    def test_absence_of_optional_flags_is_not_new_negative_evidence(self):
        outcome, _ = core({"supported": True})
        self.assertEqual(outcome, [])

    def test_emotional_report_is_distinct_from_unseen_event_authority(self):
        _, client = core({"supported": True, "unsupported_claims": []})
        text = prompt(client)
        self.assertIn("establishes that user stance only", text)
        self.assertIn("another person's actions, motives", text)
        self.assertIn("Acknowledge the user's reaction", text)

    def test_sarcasm_does_not_exempt_plausible_premises(self):
        _, client = core({"supported": True, "unsupported_claims": []})
        text = prompt(client)
        self.assertIn("a hedge does not by itself exempt", text)
        self.assertIn("Decompose each meaningful proposition", text)

    def test_correct_complaint_is_not_new_relationship_history(self):
        _, client = core({"supported": True, "unsupported_claims": []},
                         user="You can check the catalog; I should not have to recite it.")
        self.assertIn("correction/complaint directed at Mairon", prompt(client))

    def test_trust_packet_reaches_existing_verifier_without_extra_call(self):
        context = "CORE TRUST STATE: no accepted stance; user data only"
        _, client = core({"supported": True, "unsupported_claims": []}, trust_context=context)
        self.assertIn(context, prompt(client))
        self.assertEqual(len(client.calls), 1)

    def test_prior_assistant_invention_is_not_recent_user_evidence(self):
        _, client = core({"supported": True, "unsupported_claims": []}, conversation=[
            {"role": "user", "content": "The hearing upset me."},
            {"role": "assistant", "content": "PRIVATE_FABRICATED_HISTORY"},
        ])
        self.assertNotIn("PRIVATE_FABRICATED_HISTORY", prompt(client))

    def test_factual_questions_remain_outside_user_only_claim_verifier(self):
        outcome, client = core({"supported": False}, contract=FACTUAL)
        self.assertEqual(outcome, [])
        self.assertEqual(client.calls, [])

    def test_factual_positive_cannot_override_negative_explanation(self):
        outcome, _ = factual({"faithful": True, "violations": ["untested cause presented as proven"]})
        self.assertTrue(outcome)

    def test_negative_inference_overrides_positive_fidelity(self):
        outcome, _ = factual({"faithful": True, "inference_faithful": False, "violations": []})
        self.assertTrue(outcome)

    def test_negative_constraint_overrides_positive_fidelity(self):
        outcome, _ = factual({"faithful": True, "constraints_faithful": False, "violations": []})
        self.assertTrue(outcome)

    def test_inference_and_constraint_failures_can_coexist(self):
        outcome, _ = factual({"faithful": True, "inference_faithful": False,
                               "constraints_faithful": False, "violations": []})
        self.assertEqual(len(outcome), 2)

    def test_factual_verifier_optional_flags_remain_strictly_typed(self):
        for flag in ("inference_faithful", "constraints_faithful"):
            with self.subTest(flag=flag):
                outcome, _ = factual({"faithful": True, flag: "true", "violations": []})
                self.assertTrue(outcome)

    def test_factual_malformed_negative_payload_cannot_pass(self):
        outcome, _ = factual({"faithful": True, "violations": "untested mechanism"})
        self.assertTrue(outcome)

    def test_factual_legacy_positive_remains_valid(self):
        outcome, _ = factual({"faithful": True, "violations": []})
        self.assertEqual(outcome, [])

    def test_factual_prompt_retains_hypothesis_ceiling(self):
        _, client = factual({"faithful": True, "violations": []})
        text = prompt(client)
        for category in ("observed fact", "eliminated hypothesis", "weakened hypothesis",
                         "plausible remaining hypothesis", "established cause"):
            self.assertIn(category, text)
        self.assertIn("does not alone establish a cause", text)
        self.assertIn("mechanism sounds technically plausible", text)

    def test_factual_prompt_distinguishes_useful_option_and_requirement(self):
        _, client = factual({"faithful": True, "violations": []})
        self.assertIn("useful optional approach is not a necessary requirement", prompt(client))

    def test_factual_trust_context_reuses_one_existing_call(self):
        _, client = factual({"faithful": True, "violations": []},
                            trust_context="CORE USER CONSTRAINT: excluded purchase assumptions")
        self.assertEqual(len(client.calls), 1)
        self.assertIn("CORE USER CONSTRAINT", prompt(client))

    def test_explicit_constraint_survives_a_task_followup(self):
        history = [{"role": "user", "content": "Compare portable recorders with long battery life. Don't assume my budget."}]
        self.assertTrue(find_explicit_user_constraint_violations(
            "What about battery life?", "Your budget makes the cheaper option better.", conversation=history))

    def test_assistant_constraint_has_no_user_authority(self):
        history = [{"role": "assistant", "content": "Don't assume my budget."}]
        self.assertEqual(find_explicit_user_constraint_violations(
            "What about battery life?", "Your budget makes the cheaper option better.", conversation=history), [])

    def test_new_task_does_not_inherit_unrelated_constraint(self):
        history = [{"role": "user", "content": "Compare portable recorders. Don't assume my budget."}]
        self.assertEqual(find_explicit_user_constraint_violations(
            "New topic: help me make a shopping budget.", "Your budget is the planning starting point.",
            conversation=history), [])

    def test_explicit_revision_is_resolved_semantically_not_frozen_lexically(self):
        history = [{"role": "user", "content": "Compare portable recorders. Don't assume my budget."}]
        self.assertEqual(find_explicit_user_constraint_violations(
            "Actually, my budget is now stated: 360 credits. Which recorder fits?",
            "Your budget is a useful constraint now.", conversation=history), [])


if __name__ == "__main__":
    unittest.main()
