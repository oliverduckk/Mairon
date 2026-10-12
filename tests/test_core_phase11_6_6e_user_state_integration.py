"""Real restricted-social publication rejects unsupported embedded USER state.

The production provider and claim verifier execute unchanged with an offline
scripted client.  Only model output and unrelated services are replaced; the
USER-history detector, full-source witness checks and retry bound are real.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import verify_core_grounded_draft
from core.answer_contract import build_answer_contract
from core.epistemic_router import route_epistemic_authority
from core.intent_router import classify_turn
from core.stance_ownership import is_user_stance_acknowledgement
from core.user_history_obligations import build_user_history_packet
from test_core_phase11_6_6c_social_empty_integration import entry
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6d_stance_ownership_integration import (
    contract as stance_contract, overrides as stance_overrides, provider_text_helper,
)
import personality.opinion_ledger as opinion_ledger


USER = "The sample crates have arrived."
GOOD = "Good to hear the crates arrived."
WH_BAD = "Are you wondering why you haven't finished your current project yet?"
WORRY_BAD = "You can stop worrying about the invoice now."


def packet(candidate, user=USER, conversation=()):
    sources = {"current_user": user}
    prior = [item["content"] for item in conversation if item["role"] == "user"][-4:]
    sources.update({"prior_user_" + str(index): value
                    for index, value in enumerate(prior, 1)})
    return build_user_history_packet(candidate, sources)


def assessed(candidate, user=USER, *, conversation=(), supported=True,
             source_id="current_user", quote=None):
    value = packet(candidate, user, conversation)
    if not value["obligations"]:
        raise AssertionError("Expected a real Core-owned USER-state obligation")
    return valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": supported, "source_id": source_id,
         "source_quote": user if quote is None else quote}
        for item in value["obligations"]
    ]}


def generation_count(client):
    return sum(not any("INTERNAL" in item["content"] for item in call["messages"])
               for call in client.calls)


def verifier_count(client):
    return sum(any("INTERNAL claim-grounding verifier" in item["content"]
                   for item in call["messages"]) for call in client.calls)


class UserStateProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for candidate in withheld:
            self.assertNotIn(candidate, [item["content"] for item in result[1]])

    def direct_failures(self, candidate, user=USER, state=None, conversation=()):
        client = ScriptedClient([], core=[valid_core() if state is None else state])
        failures = verify_core_grounded_draft(
            client, "neutral-model", user, candidate, social(), conversation,
        )
        self.assertEqual(len(client.calls), 1)
        return failures, client

    def test_outer_question_keeps_the_embedded_noncompletion_obligation(self):
        self.assertTrue(packet(WH_BAD)["obligations"])
        failures, client = self.direct_failures(WH_BAD)
        self.assertTrue(any("user-history" in item for item in failures))
        prompt = "\n".join(item["content"] for item in client.calls[0]["messages"])
        self.assertIn("CORE USER-HISTORY OBLIGATIONS", prompt)
        self.assertIn("history_assessments", prompt)

    def test_direct_why_noncompletion_is_not_an_information_only_question(self):
        candidate = "Why haven't you finished your current project yet?"
        self.assertTrue(packet(candidate)["obligations"])
        self.assertTrue(self.direct_failures(candidate)[0])

    def test_why_cessation_and_when_cessation_require_user_authority(self):
        for candidate in (
            "Why did you stop sorting the samples?",
            "When did you stop sorting the samples?",
        ):
            with self.subTest(candidate=candidate):
                self.assertTrue(packet(candidate)["obligations"])
                self.assertTrue(self.direct_failures(candidate)[0])

    def test_why_still_ongoing_activity_requires_user_authority(self):
        candidate = "Why are you still sorting the samples?"
        self.assertTrue(packet(candidate)["obligations"])
        self.assertTrue(self.direct_failures(candidate)[0])

    def test_global_positive_with_no_scoped_state_retries_the_real_social_path(self):
        client = ScriptedClient([WH_BAD, GOOD], core=[valid_core()] * 2)
        self.assert_published(run(client, USER, social()), GOOD, WH_BAD)
        self.assertEqual(generation_count(client), 2)
        self.assertEqual(verifier_count(client), 2)

    def test_positive_scoped_result_cannot_use_arrival_as_worry_evidence(self):
        client = ScriptedClient([WORRY_BAD, GOOD], core=[assessed(WORRY_BAD), valid_core()])
        self.assert_published(run(client, USER, social("share_context")), GOOD, WORRY_BAD)

    def test_mental_cessation_variants_execute_the_same_scoped_verifier(self):
        for candidate in (
            "You can stop worrying about the invoice now.",
            "You don't have to keep stressing about the invoice anymore.",
            "Now you can stop being worried about the invoice.",
        ):
            with self.subTest(candidate=candidate):
                value = assessed(candidate)
                failures, _ = self.direct_failures(candidate, state=value)
                self.assertTrue(any("user-history" in item for item in failures))

    def test_speaker_epistemic_prefix_cannot_hide_an_unsupplied_mental_premise(self):
        candidate = "I suppose you can stop worrying about whether the supplies will arrive before Tuesday now."
        client = ScriptedClient([candidate, GOOD], core=[assessed(candidate), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, candidate)
        self.assertEqual(generation_count(client), 2)

    def test_genuine_suppose_conditional_remains_hypothetical(self):
        candidate = "Suppose you can stop worrying about the invoice; you could focus on something else."
        self.assertFalse(packet(candidate)["obligations"])
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)

    def test_matching_explicit_user_worry_publishes_naturally_unchanged(self):
        user = "I've been worrying about the invoice."
        self.assertFalse(packet(WORRY_BAD, user)["obligations"])
        client = ScriptedClient([WORRY_BAD], core=[valid_core()])
        self.assert_published(run(client, user, social("share_context")), WORRY_BAD)
        self.assertEqual(generation_count(client), 1)
        self.assertEqual(verifier_count(client), 1)

    def test_future_valued_concern_topic_is_not_a_future_mental_state(self):
        user = "I've been stressing about whether the crates will arrive before Tuesday."
        candidate = "You can stop worrying about whether the crates will arrive before Tuesday now."
        self.assertFalse(packet(candidate, user)["obligations"])
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, user, social("share_context")), candidate)
        self.assertEqual(generation_count(client), 1)

    def test_different_concern_topic_cannot_be_supplied_by_positive_global(self):
        user = "I've been worrying about the invoice."
        candidate = "You can stop worrying about the inspection now."
        good = "You've said the invoice is worrying you."
        client = ScriptedClient([candidate, good], core=[assessed(candidate, user), valid_core()])
        self.assert_published(run(client, user, social()), good, candidate)

    def test_changed_concern_deadline_is_not_the_same_topic(self):
        user = "I've been worrying about whether the crates will arrive before Tuesday."
        candidate = "You can stop worrying about whether the crates will arrive before Thursday now."
        client = ScriptedClient([candidate, "I hear the concern."],
                                core=[assessed(candidate, user), valid_core()])
        self.assert_published(run(client, user, social()), "I hear the concern.", candidate)

    def test_opposite_opaque_concern_polarity_is_not_a_matching_witness(self):
        user = "I've been worrying that the samples will erode."
        candidate = "You can stop worrying that the samples will not erode now."
        client = ScriptedClient([candidate, "I hear the concern."],
                                core=[assessed(candidate, user), valid_core()])
        self.assert_published(run(client, user, social()), "I hear the concern.", candidate)

    def test_past_concern_cannot_establish_a_current_mental_cessation(self):
        user = "I was worried about the invoice."
        client = ScriptedClient([WORRY_BAD, "Got it."],
                                core=[assessed(WORRY_BAD, user), valid_core()])
        self.assert_published(run(client, user, social()), "Got it.", WORRY_BAD)

    def test_past_opaque_concern_target_cannot_become_a_future_target(self):
        user = "I've been worrying that the import failed."
        candidate = "You can stop worrying that the import will fail now."
        client = ScriptedClient([candidate, "Got it."],
                                core=[assessed(candidate, user), valid_core()])
        self.assert_published(run(client, user, social()), "Got it.", candidate)

    def test_prior_user_worry_is_authority_without_using_assistant_history(self):
        history = [{"role": "user", "content": "I've been worrying about the invoice."},
                   {"role": "assistant", "content": "You've been worried about a different inspection."}]
        self.assertFalse(packet(WORRY_BAD, USER, history)["obligations"])
        client = ScriptedClient([WORRY_BAD], core=[valid_core()])
        self.assert_published(run(client, USER, social(), history), WORRY_BAD)

    def test_assistant_only_worry_cannot_create_a_user_witness(self):
        history = [{"role": "assistant", "content": "You've been worrying about the invoice."}]
        value = assessed(WORRY_BAD, conversation=history, source_id="prior_user_1",
                         quote="You've been worrying about the invoice.")
        client = ScriptedClient([WORRY_BAD, GOOD], core=[value, valid_core()])
        self.assert_published(run(client, USER, social(), history), GOOD, WORRY_BAD)

    def test_current_negative_user_state_overrides_older_positive_state(self):
        user = "I'm not worried about the invoice."
        history = [{"role": "user", "content": "I've been worrying about the invoice."}]
        value = assessed(WORRY_BAD, user, conversation=history, source_id="prior_user_1",
                         quote=history[0]["content"])
        client = ScriptedClient([WORRY_BAD, "Got it."], core=[value, valid_core()])
        self.assert_published(run(client, user, social(), history), "Got it.", WORRY_BAD)

    def test_conditional_user_worry_substring_cannot_be_laundered_as_authority(self):
        user = "If I've been worrying about the invoice, ask me before assuming it."
        value = assessed(WORRY_BAD, user, quote="I've been worrying about the invoice")
        client = ScriptedClient([WORRY_BAD, "Got it."], core=[value, valid_core()])
        self.assert_published(run(client, user, social()), "Got it.", WORRY_BAD)

    def test_quoted_user_worry_substring_cannot_be_laundered_as_authority(self):
        user = 'The sample dialogue says "I\'ve been worrying about the invoice".'
        value = assessed(WORRY_BAD, user, quote="I've been worrying about the invoice")
        client = ScriptedClient([WORRY_BAD, "Got it."], core=[value, valid_core()])
        self.assert_published(run(client, user, social()), "Got it.", WORRY_BAD)

    def test_plain_information_seeking_questions_do_not_acquire_user_state(self):
        candidates = (
            "Are you worried about the invoice?",
            "Have you finished the project?",
            "Are you working on anything right now?",
            "Did you use a stylus while waiting?",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertFalse(packet(candidate)["obligations"])
                client = ScriptedClient([candidate], core=[valid_core()])
                self.assert_published(run(client, USER, social()), candidate)
                self.assertEqual(generation_count(client), 1)

    def test_conditional_question_does_not_acquire_actual_user_state(self):
        candidate = "If you haven't finished the project, why haven't you finished it?"
        self.assertFalse(packet(candidate)["obligations"])
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)

    def test_generic_conditional_and_hedged_advice_remains_natural(self):
        for candidate in (
            "If you're worried about the invoice, check tomorrow.",
            "If you haven't finished the project, leave it for later.",
            "You might be worried about the invoice.",
        ):
            with self.subTest(candidate=candidate):
                self.assertFalse(packet(candidate)["obligations"])
                client = ScriptedClient([candidate], core=[valid_core()])
                self.assert_published(run(client, USER, social()), candidate)

    def test_explicitly_quoted_embedded_question_is_not_actual_user_history(self):
        candidate = 'That dialogue asks "why haven\'t you finished the project?"'
        self.assertFalse(packet(candidate)["obligations"])
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)

    def test_obviously_absurd_device_humour_keeps_the_existing_grounding_lane(self):
        candidate = "The crates escaped a pocket dimension; the warehouse gods demand confetti."
        self.assertFalse(packet(candidate)["obligations"])
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)
        self.assertEqual(generation_count(client), 1)

    def test_current_owned_task_and_noncompletion_need_actual_user_evidence(self):
        value = packet(WH_BAD)
        self.assertGreaterEqual(len(value["obligations"]), 2)
        client = ScriptedClient([WH_BAD, GOOD], core=[assessed(WH_BAD), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, WH_BAD)

    def test_user_progress_can_support_matching_noncompletion_without_a_new_loop(self):
        user = "I'm halfway through my current project."
        self.assertFalse(packet(WH_BAD, user)["obligations"])
        client = ScriptedClient([WH_BAD], core=[valid_core()])
        self.assert_published(run(client, user, social()), WH_BAD)
        self.assertEqual(generation_count(client), 1)
        self.assertEqual(verifier_count(client), 1)

    def test_progress_on_different_task_cannot_support_a_new_owned_task(self):
        user = "I'm halfway through my current project."
        candidate = "Why haven't you finished your current inspection yet?"
        client = ScriptedClient([candidate, "Keep me posted."],
                                core=[assessed(candidate, user), valid_core()])
        self.assert_published(run(client, user, social()), "Keep me posted.", candidate)

    def test_complex_wh_completion_keeps_its_obligation_when_task_adapter_is_narrow(self):
        candidate = "Why haven't you finished all the archive labels for Mara?"
        self.assertTrue(packet(candidate)["obligations"])
        client = ScriptedClient([candidate, GOOD], core=[assessed(candidate), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, candidate)

    def test_working_on_a_task_does_not_establish_its_noncompletion(self):
        user = "I'm working on my current project."
        good = "You're working on the project."
        client = ScriptedClient([WH_BAD, good], core=[assessed(WH_BAD, user), valid_core()])
        self.assert_published(run(client, user, social()), good, WH_BAD)

    def test_past_task_ownership_does_not_establish_the_same_current_task(self):
        user = "I was halfway through my project."
        good = "You said you were halfway through it."
        client = ScriptedClient([WH_BAD, good], core=[assessed(WH_BAD, user), valid_core()])
        self.assert_published(run(client, user, social()), good, WH_BAD)

    def test_incomplete_scoped_set_fails_closed_despite_global_positive(self):
        value = assessed(WH_BAD)
        self.assertGreaterEqual(len(value["history_assessments"]), 2)
        value["history_assessments"].pop()
        self.assertTrue(self.direct_failures(WH_BAD, state=value)[0])

    def test_malformed_scoped_array_fails_closed_despite_global_positive(self):
        value = valid_core() | {"history_assessments": {"supported": True}}
        self.assertTrue(self.direct_failures(WH_BAD, state=value)[0])

    def test_non_boolean_scoped_support_fails_closed_despite_global_positive(self):
        value = assessed(WORRY_BAD)
        value["history_assessments"][0]["supported"] = "true"
        self.assertTrue(self.direct_failures(WORRY_BAD, state=value)[0])

    def test_duplicate_scoped_indices_fail_closed_despite_global_positive(self):
        value = assessed(WH_BAD)
        self.assertGreaterEqual(len(value["history_assessments"]), 2)
        value["history_assessments"][1]["index"] = value["history_assessments"][0]["index"]
        self.assertTrue(self.direct_failures(WH_BAD, state=value)[0])

    def test_model_none_label_cannot_erase_a_core_detected_question_premise(self):
        value = assessed(WH_BAD)
        for check in value["history_assessments"]:
            check["kind"] = "none"
        self.assertTrue(self.direct_failures(WH_BAD, state=value)[0])

    def test_candidate_quote_cannot_be_used_as_a_user_witness(self):
        value = assessed(WORRY_BAD, quote=WORRY_BAD)
        self.assertTrue(self.direct_failures(WORRY_BAD, state=value)[0])

    def test_global_positive_cannot_override_explicit_scoped_negative(self):
        value = assessed(WH_BAD, supported=False)
        self.assertTrue(self.direct_failures(WH_BAD, state=value)[0])

    def test_every_retry_rechecks_different_embedded_state_without_an_extra_loop(self):
        client = ScriptedClient([WH_BAD, WORRY_BAD, GOOD],
                                core=[valid_core(), assessed(WORRY_BAD), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, WH_BAD, WORRY_BAD)
        self.assertEqual(generation_count(client), 3)
        self.assertEqual(verifier_count(client), 3)
        self.assertEqual(len(client.calls), 6)
        self.assertTrue(all(not call.get("tools") for call in client.calls))

    def test_three_invalid_retries_keep_the_existing_bounded_safe_fallback(self):
        client = ScriptedClient([WH_BAD, WORRY_BAD, WH_BAD], core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertTrue(result[0].strip())
        self.assertNotIn(result[0], {WH_BAD, WORRY_BAD})
        self.assertEqual(result[2:], (None, None))
        self.assertEqual(generation_count(client), 3)
        self.assertEqual(verifier_count(client), 3)
        self.assertEqual(len(client.calls), 6)
        self.assertNotIn(WH_BAD, [item["content"] for item in result[1]])
        self.assertNotIn(WORRY_BAD, [item["content"] for item in result[1]])

    def test_real_stance_acknowledgement_cannot_hide_an_unfinished_task_premise(self):
        user = "For this discussion, remember that I prefer cedar over slate."
        bad = "Noted — you prefer cedar over slate. Why haven't you finished your current project?"
        good = "Noted — you prefer cedar over slate."
        client = ScriptedClient([bad, good], core=[valid_core()] * 2)
        self.assert_published(run(client, user, stance_contract(), overrides=stance_overrides()), good, bad)
        self.assertEqual(generation_count(client), 2)

    def test_real_entry_keeps_stance_acknowledgement_on_the_guarded_nonaction_path(self):
        user = "For this discussion, remember that I prefer cedar over slate."
        turn = classify_turn(user)
        current = build_answer_contract(turn, route_epistemic_authority(turn))
        bad = "Noted — you prefer cedar over slate. Why haven't you finished your current project?"
        good = "Noted — you prefer cedar over slate."
        client = ScriptedClient([bad, good], core=[valid_core()] * 2)
        def direct(**kwargs):
            return run(kwargs["client"], kwargs["user_input"], kwargs["core_answer_contract"],
                       kwargs["conversation"], stance_overrides())
        result, _ = entry(user, client, current, force_tool_loop=True, overrides={
            "is_user_stance_acknowledgement": is_user_stance_acknowledgement,
            "handle_direct_conversation": direct,
        })
        self.assert_published(result, good, bad)
        self.assertEqual(generation_count(client), 2)
        self.assertTrue(all(not call.get("tools") for call in client.calls))

    def test_existing_stance_ownership_still_rejects_an_assistant_first_person_echo(self):
        user = "For this discussion, remember that I prefer cedar over slate."
        bad, good = "I prefer cedar over slate.", "You prefer cedar over slate."
        recorded = []
        client = ScriptedClient([bad, good], core=[valid_core()] * 2)
        self.assert_published(run(client, user, stance_contract(),
                                  overrides=stance_overrides(recorded=recorded)), good, bad)
        self.assertEqual(recorded, [])
        self.assertEqual(generation_count(client), 2)

    def test_correct_user_owned_recall_remains_on_the_existing_recall_authority(self):
        history = [{"role": "user", "content": "Remember that I prefer cedar over slate."},
                   {"role": "assistant", "content": "I prefer slate over cedar."}]
        current = social("conversation_recall")
        candidate = "You told me that you prefer cedar over slate."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "What preference did I tell you?", current, history,
                                  stance_overrides(extra={
            "classify_opinion_subject": opinion_ledger.classify_opinion_subject,
            "build_live_conversation_recall_context": provider_text_helper("build_live_conversation_recall_context"),
            "repair_live_recall_tail": provider_text_helper("repair_live_recall_tail"),
        })), candidate)
        self.assertEqual(generation_count(client), 1)


if __name__ == "__main__":
    unittest.main()
