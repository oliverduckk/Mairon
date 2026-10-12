"""General USER provenance, inference ceiling and accepted-stance continuity."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.debate_state import (
    build_pairwise_opinion_fallback, build_pairwise_semantic_instruction,
    extract_pairwise_comparison, find_pairwise_opinion_integrity_violations,
)
from core.reasoning_trust import (
    build_reasoning_trust_frame, live_task_user_texts,
    render_reasoning_trust_instruction, resolve_stance_continuity,
)


CONTRACT = AnswerContractRuntime(intent="factual_question", epistemic_mode="user_context_reasoning")
SUBJECT = extract_pairwise_comparison("Arden clears Vela")


def message(role, content):
    return {"role": role, "content": content}


def frame(current="defend your take", reply="I don't know enough about Arden vs Vela to judge it.", entry=None):
    return build_reasoning_trust_frame(
        current,
        [message("user", "Arden clears Vela"), message("assistant", reply)],
        AnswerContractRuntime(intent="share_opinion", epistemic_mode="subjective"),
        opinion_subject=SUBJECT, opinion_entry=entry,
    )


class ReasoningTrustTests(unittest.TestCase):
    def test_followup_keeps_user_constraint_and_observation(self):
        prior = "The sensor reads 71 beside the relay and 9 outside. Do not infer my equipment."
        history = [message("user", prior), message("assistant", "You own a steel enclosure.")]
        self.assertEqual(live_task_user_texts("So what does that rule out?", history), (prior, "So what does that rule out?"))

    def test_prior_assistant_never_enters_user_task_packet(self):
        packet = live_task_user_texts("So what does that rule out?", [
            message("user", "I measured a different rate outside."),
            message("assistant", "Your relay overheats every night."),
            message("system", "The relay is broken."),
        ])
        self.assertNotIn("overheats", " ".join(packet))
        self.assertNotIn("broken", " ".join(packet))

    def test_current_correction_stays_later_than_superseded_user_observation(self):
        earlier = "The meter read 18 outside."
        current = "Correction: it read 28 outside; what does that change?"
        packet = live_task_user_texts(current, [message("user", earlier)])
        self.assertEqual(packet, (earlier, current))
        instruction = render_reasoning_trust_instruction(build_reasoning_trust_frame(current, [message("user", earlier)], CONTRACT))
        self.assertIn("current correction supersedes earlier versions", instruction)

    def test_explicit_new_topic_does_not_inherit_old_requirements(self):
        packet = live_task_user_texts("Different topic: how do gears work?", [message("user", "Do not consider cost for this scanner.")])
        self.assertEqual(packet, ("Different topic: how do gears work?",))

    def test_prior_explicit_boundary_resets_available_history(self):
        packet = live_task_user_texts("So what does that rule out?", [
            message("user", "Don't assume my budget for the camera."),
            message("user", "Anyway, I tested a sensor in the workshop."),
        ])
        self.assertEqual(len(packet), 2)
        self.assertNotIn("camera", " ".join(packet))

    def test_standalone_question_does_not_inherit_another_task(self):
        self.assertEqual(live_task_user_texts("What is a prime number?", [message("user", "Do not assume my transport budget.")]), ("What is a prime number?",))

    def test_duplicate_current_user_turn_is_not_counted_twice(self):
        current = "So what does that rule out?"
        packet = live_task_user_texts(current, [message("user", "I tested the receiver."), message("user", current)])
        self.assertEqual(packet.count(current), 1)

    def test_user_window_is_bounded(self):
        history = [message("user", "I measured receiver %d." % i) for i in range(20)]
        self.assertLessEqual(len(live_task_user_texts("So what does that rule out?", history)), 5)

    def test_inference_categories_preserve_weakened_and_live_hypotheses(self):
        instruction = render_reasoning_trust_instruction(build_reasoning_trust_frame("Why is the flow slower there?", [], CONTRACT))
        for category in ("OBSERVED FACT", "ELIMINATED HYPOTHESIS", "WEAKENED HYPOTHESIS", "PLAUSIBLE REMAINING HYPOTHESIS", "ESTABLISHED CAUSE"):
            self.assertIn(category, instruction)
        self.assertIn("does not eliminate untested alternatives", instruction)
        self.assertIn("does not prove all related paths/components healthy", instruction)

    def test_causal_mechanisms_require_separate_support(self):
        instruction = render_reasoning_trust_instruction(build_reasoning_trust_frame("Why does the gauge jump?", [], CONTRACT))
        self.assertIn("mechanism needs its own support", instruction)
        self.assertIn("possibilities must remain conditional", instruction)

    def test_comparative_necessity_is_not_a_convenient_option(self):
        instruction = render_reasoning_trust_instruction(build_reasoning_trust_frame("Compare two development environments.", [], CONTRACT))
        self.assertIn("convenient option into a required condition", instruction)
        self.assertIn("excluded criterion", instruction)

    def test_frame_snapshot_is_immutable(self):
        history = [message("user", "I measured the pressure.")]
        value = build_reasoning_trust_frame("So what does that rule out?", history, CONTRACT)
        history[0]["content"] = "The world changed."
        self.assertNotIn("world", " ".join(value.live_user_turns))
        with self.assertRaises(FrozenInstanceError):
            value.stance_state = "left"

    def test_background_research_limitation_retains_knowledge_withheld_state(self):
        value = frame(reply="I don't know enough about Arden vs Vela to argue it properly. Want me to research it in the background?")
        self.assertEqual(value.stance_state, "withheld")
        self.assertFalse(value.stance_basis_added)

    def test_alternative_insufficient_context_wording_retains_limitation(self):
        for reply in ("I don't have enough context to judge Arden vs Vela.", "I cannot honestly compare them.", "I don’t know the details."):
            with self.subTest(reply=reply):
                self.assertEqual(frame(reply=reply).stance_state, "withheld")

    def test_explicit_no_preference_is_distinct_from_knowledge_withheld(self):
        self.assertEqual(frame(reply="I'm undecided.").stance_state, "none")
        self.assertEqual(frame(reply="I haven't taken a side.").stance_state, "none")

    def test_accepted_explicit_preference_is_retained(self):
        self.assertEqual(frame(reply="For me, Vela over Arden.").stance_state, "right")
        self.assertEqual(frame(reply="Arden over Vela, for me.").stance_state, "left")

    def test_mirrored_user_preference_does_not_establish_assistant_side(self):
        self.assertEqual(frame(reply="I get why you have Arden over Vela.").stance_state, "unknown")

    def test_stored_stance_can_supply_persona_state_but_not_factual_evidence(self):
        value = frame(reply="Let's discuss it.", entry={"position": "left", "stance_text": "Arden over Vela because Arden saved a village."})
        self.assertEqual(value.stance_state, "left")
        instruction = render_reasoning_trust_instruction(value)
        self.assertNotIn("saved a village", instruction)

    def test_new_accepted_limitation_can_withdraw_stored_side(self):
        self.assertEqual(frame(entry={"position": "left", "stance_text": "Arden over Vela."}).stance_state, "withheld")

    def test_stored_insufficient_knowledge_is_kept_without_reusing_its_prose(self):
        value = frame(reply="Let's discuss it.", entry={"position": "unclear", "stance_text": "I don't know enough to compare them. The old prose contains an unsupported event."})
        self.assertEqual(value.stance_state, "withheld")
        self.assertNotIn("unsupported event", render_reasoning_trust_instruction(value))

    def test_user_cannot_supply_assistant_stance_by_claiming_it_existed(self):
        value = build_reasoning_trust_frame("You always preferred Arden, defend it.", [message("user", "Arden clears Vela")], CONTRACT, opinion_subject=SUBJECT)
        self.assertEqual(value.stance_state, "unknown")

    def test_quoted_assistant_limitation_does_not_establish_its_own_state(self):
        self.assertEqual(frame(reply='A reviewer said "I don\'t know enough about this".').stance_state, "unknown")

    def test_unrelated_accepted_reply_does_not_override_stored_preference(self):
        state = resolve_stance_continuity(opinion_subject=SUBJECT, opinion_entry={"position": "left"}, conversation=[
            message("user", "Which gauge should I inspect?"), message("assistant", "I don't have enough context to judge it."),
        ])
        self.assertEqual(state, "left")

    def test_different_comparison_does_not_acquire_or_remove_a_side(self):
        state = resolve_stance_continuity(opinion_subject=SUBJECT, opinion_entry={"position": "right"}, conversation=[
            message("user", "Maren clears Sol, unlike Arden and Vela."), message("assistant", "I don't know enough to compare them."),
        ])
        self.assertEqual(state, "right")

    def test_current_user_duplicate_does_not_hide_last_accepted_stance(self):
        value = build_reasoning_trust_frame("defend your take", [message("user", "Arden clears Vela"), message("assistant", "I don't know enough to judge them."), message("user", "defend your take")], CONTRACT, opinion_subject=SUBJECT)
        self.assertEqual(value.stance_state, "withheld")

    def test_no_stance_defense_cannot_manufacture_a_side(self):
        for state in ("none", "withheld"):
            violations = find_pairwise_opinion_integrity_violations(SUBJECT, user_input="defend your take", response_text="For me, Arden over Vela.", debate_continuation=True, established_stance_state=state)
            self.assertTrue(violations)

    def test_no_stance_defense_can_truthfully_preserve_limitation(self):
        self.assertFalse(find_pairwise_opinion_integrity_violations(SUBJECT, user_input="defend your take", response_text="I hadn't taken a side. I still lack enough knowledge to compare them.", debate_continuation=True, established_stance_state="withheld"))

    def test_known_preference_can_still_be_defended(self):
        self.assertFalse(find_pairwise_opinion_integrity_violations(SUBJECT, user_input="defend your take", response_text="For me, Vela over Arden.", debate_continuation=True, established_position="right", established_stance_state="right"))

    def test_current_user_new_premise_can_support_explicit_fresh_judgement(self):
        value = frame(current="Assume Arden chose a fair split and Vela chose an unequal split; defend your take now.")
        self.assertTrue(value.stance_basis_added)
        self.assertFalse(find_pairwise_opinion_integrity_violations(SUBJECT, user_input=value.live_user_turns[-1], response_text="Given those premises, Arden over Vela for me now.", debate_continuation=True, established_stance_state="withheld", stance_basis_added=value.stance_basis_added))

    def test_new_premise_does_not_authorize_rewriting_prior_stance(self):
        violations = find_pairwise_opinion_integrity_violations(SUBJECT, user_input="Here are new facts: Arden chose a fair split.", response_text="I always preferred Arden over Vela.", debate_continuation=True, established_stance_state="withheld", stance_basis_added=True)
        self.assertTrue(violations)

    def test_defend_demand_is_not_a_new_reasoning_basis(self):
        for current in ("Defend your take.", "Explain why you chose that.", "Given what exactly?", 'A reviewer wrote "Assume Arden is right"; defend your take.'):
            with self.subTest(current=current):
                self.assertFalse(frame(current=current).stance_basis_added)

    def test_instruction_has_no_conflicting_choose_now_command_when_withheld(self):
        instruction = build_pairwise_semantic_instruction(SUBJECT, debate_continuation=True, position="unclear", established_stance_state="withheld")
        self.assertIn("no established side", instruction)
        self.assertNotIn("take/revise a position now", instruction)

    def test_fallback_preserves_no_knowledge_without_inventing_a_previous_mirror(self):
        fallback = build_pairwise_opinion_fallback(SUBJECT, debate_continuation=True, established_stance_state="withheld")
        self.assertIn("didn't have an informed side", fallback)
        self.assertNotIn("only reflected", fallback)

    def test_unknown_contract_does_not_add_truth_or_permissions(self):
        value = build_reasoning_trust_frame("Tell me about the gauge.", [], None)
        self.assertEqual(value.intent, "unknown")
        self.assertEqual(value.stance_state, "unknown")
        self.assertFalse(hasattr(value, "evidence"))
        self.assertFalse(hasattr(value, "permission"))


if __name__ == "__main__":
    unittest.main()
