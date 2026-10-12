"""Bounded semantic acknowledgements use contracts, never model or history prose."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.answer_contract_runtime import AnswerContractRuntime, runtime_from_answer_contract
from core.social_acknowledgement import build_empty_social_acknowledgement


def contract(**overrides):
    values = dict(task="share_context", speech_act="declarative_share",
                  intent="share_context", authority="user_turn",
                  epistemic_mode="user_provided", allow_new_factual_claims=False)
    values.update(overrides)
    return AnswerContractRuntime(**values)


def acknowledge(text="I might try the new feature later.", current=None, **kwargs):
    return build_empty_social_acknowledgement(
        user_input=text, contract=current if current is not None else contract(), **kwargs)


class EmptySocialAcknowledgementTests(unittest.TestCase):
    def test_explicit_deferred_action_is_acknowledged_without_domain_details(self):
        self.assertEqual(acknowledge("I might run the utility, not asking you to do it yet."),
                         "Got it — no action for now.")

    def test_maybe_later_is_bounded_non_action(self):
        self.assertEqual(acknowledge("Maybe later I'll try sending a message."),
                         "Got it — no action for now.")

    def test_nonaction_mention_without_explicit_deferral_is_minimal(self):
        self.assertEqual(acknowledge("I'm thinking about reorganising my files."), "Got it.")

    def test_device_control_thought_does_not_claim_control(self):
        self.assertEqual(acknowledge("Perhaps later I will lower the lights."),
                         "Got it — no action for now.")

    def test_application_launch_thought_does_not_claim_launch(self):
        self.assertEqual(acknowledge("I might open the viewer, not now."),
                         "Got it — no action for now.")

    def test_arbitrary_future_capability_is_not_a_domain_branch(self):
        self.assertEqual(acknowledge("I might activate a zorbulator, not requesting you do anything."),
                         "Got it — no action for now.")

    def test_ordinary_shared_context_is_minimal(self):
        self.assertEqual(acknowledge("The parcel arrived."), "Got it.")

    def test_casual_statement_contract_is_allowed(self):
        current = contract(task="casual_conversation", intent="casual_conversation",
                           speech_act="statement", authority="live_conversation",
                           epistemic_mode="social_conversation")
        self.assertEqual(acknowledge("I'm bored.", current), "Got it.")

    def test_self_correction_does_not_repeat_or_invent_a_detail(self):
        current = contract(task="self_correction", intent="self_correction",
                           speech_act="self_correction", authority="user_turn_and_live_conversation",
                           epistemic_mode="self_correction")
        self.assertEqual(acknowledge("I meant the other connector.", current), "Got it.")

    def test_thanks_direction_is_preserved(self):
        current = contract(task="acknowledge", intent="acknowledge", speech_act="thanks",
                           authority="conversation_model", epistemic_mode="conversation")
        self.assertEqual(acknowledge("Thanks.", current), "You're welcome.")

    def test_no_persistence_or_reminder_promise_is_added(self):
        answer = acknowledge("Maybe later I will review the report.")
        self.assertEqual(answer, "Got it — no action for now.")
        self.assertNotRegex(answer.casefold(), r"remember|saved|stored|remind|scheduled|created")

    def test_user_contents_do_not_become_extra_facts(self):
        self.assertEqual(acknowledge("I think the gizmo can read minds."), "Got it.")

    def test_no_tool_or_other_state_interface_is_exposed(self):
        import inspect
        self.assertEqual(set(inspect.signature(build_empty_social_acknowledgement).parameters),
                         {"user_input", "contract", "tool_activity"})

    def test_tool_activity_prevents_acknowledgement(self):
        self.assertIsNone(acknowledge(tool_activity=True))

    def test_empty_user_turn_is_not_a_known_speech_act(self):
        self.assertIsNone(acknowledge("  "))

    def test_missing_contract_has_no_fallback_authority(self):
        self.assertIsNone(build_empty_social_acknowledgement(user_input="Hello.", contract=None))

    def test_unrelated_object_has_no_fallback_authority(self):
        self.assertIsNone(acknowledge(current=object()))

    def test_unknown_intent_is_not_social(self):
        self.assertIsNone(acknowledge(current=contract(intent="unknown")))

    def test_action_request_does_not_use_social_fallback(self):
        self.assertIsNone(acknowledge("Please move the file.", contract(
            task="action_request", intent="action_request", speech_act="request_action")))

    def test_action_speech_act_cannot_hide_inside_share_context(self):
        self.assertIsNone(acknowledge(current=contract(speech_act="request_action")))

    def test_action_task_cannot_hide_inside_share_context(self):
        self.assertIsNone(acknowledge(current=contract(task="send_message")))

    def test_factual_request_is_not_acknowledged_as_complete(self):
        self.assertIsNone(acknowledge(current=contract(intent="factual_question")))

    def test_private_authority_is_not_social_authority(self):
        self.assertIsNone(acknowledge(current=contract(authority="gmail")))

    def test_public_authority_is_not_social_authority(self):
        self.assertIsNone(acknowledge(current=contract(authority="public_web")))

    def test_unknown_authority_is_not_trusted(self):
        self.assertIsNone(acknowledge(current=contract(authority="unknown")))

    def test_verified_mode_is_not_a_nonaction_microact(self):
        self.assertIsNone(acknowledge(current=contract(epistemic_mode="public_source_verified")))

    def test_required_result_is_not_discarded(self):
        self.assertIsNone(acknowledge(current=contract(required_claims=("The check succeeded.",))))

    def test_verified_result_is_not_discarded(self):
        self.assertIsNone(acknowledge(current=contract(verified_evidence_claims=("The job is done.",))))

    def test_recommendation_obligation_is_not_discarded(self):
        self.assertIsNone(acknowledge(current=contract(allow_recommendations=True)))

    def test_factual_generation_permission_is_not_a_social_microact(self):
        self.assertIsNone(acknowledge(current=contract(allow_new_factual_claims=True)))

    def test_user_turn_and_runtime_are_not_mutated(self):
        current = contract(metadata={"neutral": "unchanged"})
        before = replace(current, metadata=dict(current.metadata))
        text = "Perhaps later I'll launch the tool."
        acknowledge(text, current)
        self.assertEqual(current, before)
        self.assertEqual(text, "Perhaps later I'll launch the tool.")

    def test_real_core_contract_is_accepted_without_parsing_model_instruction(self):
        from core.answer_contract import build_answer_contract
        from core.epistemic_router import EpistemicRoute
        from core.turn_state import TurnState
        turn = TurnState(raw_text="Maybe later I will try the switch.",
                         intent="share_context", speech_act="declarative_share")
        current = build_answer_contract(turn, EpistemicRoute(
            authority="user_turn", mode="user_provided", verification_required=False,
            allow_model_memory=False, reason="USER-authored declarative share"))
        self.assertEqual(acknowledge(turn.raw_text, current), "Got it — no action for now.")
        self.assertEqual(acknowledge(turn.raw_text, runtime_from_answer_contract(current)),
                         "Got it — no action for now.")


if __name__ == "__main__":
    unittest.main()
