"""Neutral ownership/ledger regressions; an acknowledged opinion stays USER-owned."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.reasoning_trust import resolve_stance_continuity
from core.stance_ownership import (
    build_stance_ownership_frame, find_stance_ownership_violations,
    is_user_stance_acknowledgement, render_stance_ownership_instruction,
)
import personality.opinion_ledger as ledger


USER = "For our conversation, remember that I reckon amber is harder to shape than basalt."
PROPOSITION = "amber is harder to shape than basalt"
SUBJECT = ledger.classify_opinion_subject("Lumen clears Vale.")


def contract(**changes):
    return AnswerContractRuntime(**({"intent": "share_opinion", "authority": "conversation",
        "epistemic_mode": "conversation", "allow_new_factual_claims": False} | changes))


def frame(user=USER, **kwargs):
    return build_stance_ownership_frame(user, contract(), **kwargs)


class StanceOwnershipTests(unittest.TestCase):
    def test_explicit_acknowledgement_preserves_user_owner(self):
        current = frame()
        self.assertTrue(current.acknowledgement_only)
        self.assertEqual(current.user_stances[0].content, PROPOSITION)
        self.assertFalse(current.accepted_assistant_stances)

    def test_user_first_person_does_not_authorize_assistant_first_person(self):
        self.assertTrue(find_stance_ownership_violations("Noted. I reckon " + PROPOSITION + ".", frame=frame()))

    def test_user_attributed_restatement_is_allowed(self):
        self.assertFalse(find_stance_ownership_violations("You reckon " + PROPOSITION + ".", frame=frame()))

    def test_brief_acknowledgement_is_allowed(self):
        self.assertFalse(find_stance_ownership_violations("Noted.", frame=frame()))

    def test_belief_verb_variation_cannot_acquire_stance(self):
        for marker in ("I think", "I believe", "I feel", "My take is", "In my opinion", "For me,"):
            with self.subTest(marker=marker):
                self.assertTrue(find_stance_ownership_violations(marker + " " + PROPOSITION + ".", frame=frame()))

    def test_tentative_first_person_stance_still_needs_independent_authority(self):
        for marker in ("I'd say", "I would say", "I would pick"):
            with self.subTest(marker=marker):
                self.assertTrue(find_stance_ownership_violations(marker + " amber.", frame=frame()))

    def test_preference_cannot_be_owned_by_assistant_via_acknowledgement(self):
        current = frame("Please note that I prefer paper maps over audio guides.")
        self.assertTrue(find_stance_ownership_violations("I prefer paper maps over audio guides.", frame=current))
        self.assertFalse(find_stance_ownership_violations("Your preference is paper maps over audio guides.", frame=current))

    def test_negative_user_preference_does_not_become_assistant_preference(self):
        current = frame("Remember that I don't like bitter tea.")
        self.assertTrue(find_stance_ownership_violations("I don't like bitter tea either.", frame=current))

    def test_accepted_assistant_ledger_stance_remains_independent(self):
        prior = {"stance_text": "I think " + PROPOSITION + ".", "source": "conversation"}
        current = frame(accepted_opinion_entry=prior)
        self.assertFalse(find_stance_ownership_violations("I reckon " + PROPOSITION + ".", frame=current))
        self.assertEqual(len(current.accepted_assistant_stances), 1)

    def test_unrelated_assistant_stance_does_not_authorize_new_one(self):
        current = frame(accepted_opinion_entry={"stance_text": "I think violet clay is easier to shape."})
        self.assertTrue(find_stance_ownership_violations("I think " + PROPOSITION + ".", frame=current))

    def test_user_stance_match_cannot_reverse_assistant_polarity(self):
        current = frame(accepted_opinion_entry={"stance_text": "I don't think " + PROPOSITION + "."})
        self.assertTrue(find_stance_ownership_violations("I think " + PROPOSITION + ".", frame=current))

    def test_ledger_without_explicit_owned_stance_cannot_supply_one(self):
        current = frame(accepted_opinion_entry={"stance_text": "You reckon " + PROPOSITION + ".", "position": "left"})
        self.assertTrue(find_stance_ownership_violations("I reckon " + PROPOSITION + ".", frame=current))

    def test_existing_structured_assistant_preference_survives_implicit_rendering(self):
        prior = {"kind": "pairwise_comparison", "left": "Lumen", "right": "Vale",
                 "position": "right", "stance_text": "Vale over Lumen, easy."}
        current = frame("Remember that I prefer Lumen over Vale.", accepted_opinion_entry=prior)
        self.assertFalse(find_stance_ownership_violations("I prefer Vale over Lumen.", frame=current))
        self.assertTrue(find_stance_ownership_violations("I prefer Lumen over Vale.", frame=current))

    def test_structured_preference_does_not_establish_new_comparison_property(self):
        prior = {"kind": "pairwise_comparison", "left": "Lumen", "right": "Vale",
                 "position": "right", "stance_text": "Vale over Lumen, easy."}
        current = frame("Remember that I think Vale is harder to master than Lumen.", accepted_opinion_entry=prior)
        self.assertTrue(find_stance_ownership_violations("I think Vale is harder to master than Lumen.", frame=current))

    def test_exact_real_router_contract_preserves_user_stance_owner(self):
        from core.answer_contract import build_answer_contract
        from core.intent_router import classify_turn
        from core.epistemic_router import route_epistemic_authority
        turn = classify_turn(USER)
        routed = route_epistemic_authority(turn)
        real = build_answer_contract(turn, routed)
        self.assertEqual(real.intent, "share_opinion")
        self.assertEqual(real.epistemic_mode, "subjective")
        current = build_stance_ownership_frame(USER, real)
        self.assertIsNotNone(current)
        self.assertTrue(find_stance_ownership_violations("I think " + PROPOSITION + ".", frame=current))

    def test_exact_owned_stance_does_not_authorize_extra_reason(self):
        current = frame(accepted_opinion_entry={"stance_text": "I reckon " + PROPOSITION + "."})
        self.assertTrue(find_stance_ownership_violations("I reckon " + PROPOSITION + " because it always breaks.", frame=current))

    def test_numeric_decimal_identity_is_not_truncated(self):
        current = frame("Remember that I think the 3.25 design looks better.",
                        accepted_opinion_entry={"stance_text": "I think the 3.25 design looks better."})
        self.assertTrue(find_stance_ownership_violations("I think the 3.75 design looks better.", frame=current))

    def test_matching_chat_scope_suffix_is_ownership_neutral(self):
        current = frame(accepted_opinion_entry={"stance_text": "I think " + PROPOSITION + "."})
        self.assertFalse(find_stance_ownership_violations("I reckon " + PROPOSITION + " for this conversation.", frame=current))

    def test_direct_user_quote_remains_attributed(self):
        candidate = 'You said, "I reckon ' + PROPOSITION + '." Noted.'
        self.assertFalse(find_stance_ownership_violations(candidate, frame=frame()))

    def test_typographic_user_quote_remains_attributed(self):
        candidate = 'Your view was “I reckon ' + PROPOSITION + '.”'
        self.assertFalse(find_stance_ownership_violations(candidate, frame=frame()))

    def test_second_sentence_outside_quote_still_detected(self):
        candidate = 'You said "I reckon amber is hard." I think ' + PROPOSITION + '.'
        self.assertTrue(find_stance_ownership_violations(candidate, frame=frame()))

    def test_quoted_user_remember_request_does_not_create_frame(self):
        self.assertFalse(is_user_stance_acknowledgement('Someone said "remember that I prefer teal."', contract()))

    def test_conditional_user_stance_is_not_an_asserted_preference(self):
        self.assertFalse(is_user_stance_acknowledgement("Remember that if I prefer amber, I'll say so.", contract()))

    def test_questioned_user_stance_is_not_an_asserted_preference(self):
        self.assertFalse(is_user_stance_acknowledgement("Remember, do I think amber is harder?", contract()))

    def test_conditional_candidate_stance_is_not_adoption(self):
        self.assertFalse(find_stance_ownership_violations("If I prefer amber later, I'll say so.", frame=frame()))

    def test_metadiscourse_understanding_is_not_a_new_topic_stance(self):
        self.assertFalse(find_stance_ownership_violations("I think you mean " + PROPOSITION + ".", frame=frame()))

    def test_normal_shared_opinion_does_not_enter_acknowledgement_adapter(self):
        self.assertIsNone(build_stance_ownership_frame("I reckon " + PROPOSITION + ".", contract()))

    def test_reported_first_person_remembering_is_not_a_directive(self):
        self.assertFalse(is_user_stance_acknowledgement("I remember that I prefer amber.", contract()))

    def test_negated_remember_directive_does_not_enter_acknowledgement_adapter(self):
        self.assertFalse(is_user_stance_acknowledgement("Don't remember that I prefer amber.", contract()))

    def test_conditional_directive_does_not_become_a_current_request(self):
        self.assertFalse(is_user_stance_acknowledgement("If we discuss sculpture, remember that I prefer amber.", contract()))

    def test_reported_quoted_directive_is_not_a_current_request(self):
        self.assertFalse(is_user_stance_acknowledgement('I said, "remember that I prefer amber."', contract()))

    def test_reported_unquoted_directive_is_not_a_current_request(self):
        self.assertFalse(is_user_stance_acknowledgement("I said, remember that I prefer amber.", contract()))

    def test_future_request_is_not_a_current_directive(self):
        self.assertFalse(is_user_stance_acknowledgement("Later I'll ask you to remember that I prefer amber.", contract()))

    def test_real_polite_directive_remains_eligible(self):
        self.assertTrue(is_user_stance_acknowledgement("Please remember that I prefer amber.", contract()))

    def test_trailing_explicit_directive_remains_eligible(self):
        self.assertTrue(is_user_stance_acknowledgement("I prefer amber over basalt, remember that for this chat.", contract()))

    def test_independent_assistant_opinion_request_remains_outside_adapter(self):
        self.assertIsNone(build_stance_ownership_frame(USER + " What do you think?", contract()))

    def test_request_to_agree_remains_an_opinion_path(self):
        self.assertIsNone(build_stance_ownership_frame(USER + " Do you agree?", contract()))

    def test_debate_contract_remains_outside_adapter(self):
        self.assertIsNone(build_stance_ownership_frame(USER, contract(metadata={"debate_continuation": "true"})))

    def test_public_opinion_contract_remains_outside_adapter(self):
        self.assertIsNone(build_stance_ownership_frame(USER, contract(authority="public_web", epistemic_mode="public_source_verified_opinion")))

    def test_tool_contract_cannot_reinterpret_acknowledgement(self):
        self.assertIsNone(build_stance_ownership_frame(USER, contract(intent="email_send", authority="tool", epistemic_mode="core")))

    def test_inconsistent_action_task_cannot_reinterpret_acknowledgement(self):
        self.assertIsNone(build_stance_ownership_frame(USER, contract(task="email_send")))

    def test_negative_qualified_first_person_stance_still_needs_authority(self):
        self.assertTrue(find_stance_ownership_violations("I don't really think amber is harder.", frame=frame()))

    def test_missing_contract_does_not_grant_generation_frame(self):
        self.assertIsNone(build_stance_ownership_frame(USER, None))

    def test_explicit_speech_act_can_describe_acknowledgement_without_remember_word(self):
        current = build_stance_ownership_frame("I prefer paper maps.", contract(intent="acknowledge", speech_act="acknowledge"))
        self.assertIsNotNone(current)
        self.assertTrue(find_stance_ownership_violations("I prefer paper maps.", frame=current))

    def test_current_user_correction_retains_ownership(self):
        current = frame("Correction: remember that I now prefer basalt over amber.")
        self.assertEqual(current.user_stances[0].content, "basalt over amber")
        self.assertFalse(find_stance_ownership_violations("You now prefer basalt over amber.", frame=current))
        self.assertTrue(find_stance_ownership_violations("I prefer basalt over amber.", frame=current))

    def test_typed_user_stance_correction_needs_no_repeat_remember_directive(self):
        current = build_stance_ownership_frame("Actually, I now prefer basalt over amber.",
            contract(intent="self_correction", epistemic_mode="self_correction", authority="user_turn_and_live_conversation"))
        self.assertIsNotNone(current)
        self.assertFalse(find_stance_ownership_violations("You now prefer basalt over amber.", frame=current))
        self.assertTrue(find_stance_ownership_violations("I now prefer basalt over amber.", frame=current))

    def test_frame_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            frame().acknowledgement_only = False

    def test_instruction_preserves_owner_and_separates_prior_stance(self):
        rendered = render_stance_ownership_instruction(frame())
        self.assertIn("USER ACKNOWLEDGEMENT", rendered)
        self.assertIn("does not become your", rendered)
        self.assertIn("SEPARATE ACCEPTED ASSISTANT", rendered)

    def test_non_acknowledgement_adds_no_instruction_or_violation(self):
        self.assertIsNone(render_stance_ownership_instruction(None))
        self.assertFalse(find_stance_ownership_violations("I prefer amber.", frame=None))


class ExistingStanceBoundaryTests(unittest.TestCase):
    def test_record_cannot_create_ledger_stance_from_user_acknowledgement(self):
        with patch.object(ledger, "_load_state") as load, patch.object(ledger, "_save_state") as save:
            self.assertIsNone(ledger.record_opinion_if_needed(SUBJECT, "I prefer Lumen over Vale.",
                user_input="Remember that I prefer Lumen over Vale."))
            load.assert_not_called()
            save.assert_not_called()

    def test_record_preserves_independent_stance_during_user_correction(self):
        prior = {"position": "right", "stance_text": "I prefer Vale over Lumen."}
        with patch.object(ledger, "_save_state") as save:
            result = ledger.record_opinion_if_needed(SUBJECT, "You now prefer Lumen over Vale.",
                existing_entry=prior, user_input="Remember that I now prefer Lumen over Vale.")
            self.assertEqual(result, prior)
            self.assertIsNot(result, prior)
            save.assert_not_called()

    def test_journal_acknowledgement_is_not_recovered_as_assistant_stance(self):
        turn = {"id": 9, "user_text": "I prefer Lumen over Vale and remember that for our chat.",
                "assistant_text": "I prefer Lumen over Vale."}
        with patch.object(ledger, "search_relevant_turns", return_value=[turn]), patch.object(ledger, "_save_state") as save:
            self.assertIsNone(ledger.recover_opinion_from_journal("Lumen vs Vale", SUBJECT))
            save.assert_not_called()

    def test_journal_genuine_opinion_recovery_remains_available(self):
        turn = {"id": 7, "user_text": "Lumen clears Vale.", "assistant_text": "I prefer Vale over Lumen."}
        with patch.object(ledger, "search_relevant_turns", return_value=[turn]), \
                patch.object(ledger, "_load_state", return_value={"opinions": {}}), patch.object(ledger, "_save_state") as save:
            result = ledger.recover_opinion_from_journal("Lumen vs Vale", SUBJECT)
            self.assertEqual(result["position"], "right")
            save.assert_called_once()

    def test_continuity_does_not_infer_new_side_from_user_acknowledgement(self):
        conversation = [{"role": "user", "content": "I prefer Lumen over Vale and remember that for our chat."},
                        {"role": "assistant", "content": "I prefer Lumen over Vale."}]
        self.assertEqual(resolve_stance_continuity(opinion_subject=SUBJECT, opinion_entry=None, conversation=conversation), "unknown")

    def test_existing_assistant_side_survives_user_acknowledgement(self):
        conversation = [{"role": "user", "content": "Remember that I prefer Lumen over Vale."},
                        {"role": "assistant", "content": "You prefer Lumen over Vale."}]
        prior = {"position": "right", "stance_text": "I prefer Vale over Lumen."}
        self.assertEqual(resolve_stance_continuity(opinion_subject=SUBJECT, opinion_entry=prior, conversation=conversation), "right")

    def test_withheld_stance_survives_user_preference_acknowledgement(self):
        conversation = [{"role": "user", "content": "Remember that I prefer Lumen over Vale."},
                        {"role": "assistant", "content": "Noted."}]
        prior = {"stance_text": "I don't know enough to choose a side."}
        self.assertEqual(resolve_stance_continuity(opinion_subject=SUBJECT, opinion_entry=prior, conversation=conversation), "withheld")

    def test_ordinary_opinion_recording_still_establishes_assistant_side(self):
        with patch.object(ledger, "_load_state", return_value={"opinions": {}}), patch.object(ledger, "_save_state") as save:
            result = ledger.record_opinion_if_needed(SUBJECT, "I prefer Vale over Lumen.", user_input="Lumen clears Vale.")
            self.assertEqual(result["position"], "right")
            save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
