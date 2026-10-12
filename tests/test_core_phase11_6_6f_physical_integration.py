"""Actual restricted-social publication preserves USER physical-state authority.

The existing provider/verifier execute offline.  Core must reject unsupported
physical predicates before a model can approve them; supported echoes and safe
conditionals still use the ordinary single verifier, with no new model loop.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import verify_core_grounded_draft
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6d_stance_ownership_integration import (
    contract as stance_contract, overrides as stance_overrides, provider_text_helper,
)
from test_core_phase11_6_6b_semantic_authority_integration import (
    LIVE, assessment, faithful, relation_verdict,
)
import personality.opinion_ledger as opinion_ledger


USER = "I'm sitting here, feeling restless."
GOOD = "Restlessness has impressive stamina."
FRAGMENT = "Sitting there, staring at nothing, waiting for a sign."
BODY = "Your hands are shaking."
TOPIC = "I prefer bronze over copper."


def generations(client):
    return sum(not any("INTERNAL" in item["content"] for item in call["messages"])
               for call in client.calls)


def verifications(client):
    return sum(any("INTERNAL claim-grounding verifier" in item["content"]
                   for item in call["messages"]) for call in client.calls)


class PhysicalProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for candidate in withheld:
            self.assertNotIn(candidate, [item["content"] for item in result[1]])

    def assert_core_rejects(self, candidate, user=TOPIC, history=()):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(
            client, "neutral-model", user, candidate, social(), history,
        )
        self.assertTrue(failures)
        self.assertTrue(any("physical-action/state" in item for item in failures), failures)
        self.assertEqual(client.calls, [], "Core rejection must not ask the model to approve it")

    def test_supplied_sitting_does_not_authorize_comma_fragment_secondary_states(self):
        self.assert_core_rejects(FRAGMENT, USER)

    def test_real_social_retry_withholds_the_fragment_and_preserves_a_natural_reply(self):
        client = ScriptedClient([FRAGMENT, GOOD], core=[valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, FRAGMENT)
        self.assertEqual(generations(client), 2)
        self.assertEqual(verifications(client), 1)

    def test_each_concrete_body_predicate_requires_user_authority(self):
        for candidate in (
            "Your hands are shaking.",
            "Your fingers are twitching.",
            "Your eyes are watering.",
            "Your shoulders are tense.",
            "Your arms are crossed.",
        ):
            with self.subTest(candidate=candidate):
                self.assert_core_rejects(candidate)

    def test_direct_observable_actions_cannot_be_added_to_a_topic(self):
        for candidate in (
            "You are staring at nothing.",
            "You are looking around.",
            "You are pacing around.",
            "You are slumped there.",
        ):
            with self.subTest(candidate=candidate):
                self.assert_core_rejects(candidate)

    def test_matching_user_body_states_publish_unchanged(self):
        pairs = (
            ("My hands are shaking.", "Your hands are shaking."),
            ("My fingers are twitching.", "Your fingers are twitching."),
            ("My eyes are watering.", "Your eyes are watering."),
            ("My shoulders are tense.", "Your shoulders are tense."),
            ("My arms are crossed.", "Your arms are crossed."),
        )
        for user, candidate in pairs:
            with self.subTest(candidate=candidate):
                client = ScriptedClient([candidate], core=[valid_core()])
                self.assert_published(run(client, user, social("share_context")), candidate)
                self.assertEqual(generations(client), 1)
                self.assertEqual(verifications(client), 1)

    def test_body_ownership_does_not_supply_a_predicate(self):
        self.assert_core_rejects(BODY, "I have hands.")

    def test_a_supplied_different_body_predicate_is_not_interchangeable(self):
        self.assert_core_rejects("Your eyes are watering.", "My eyes are brown.")

    def test_body_part_identity_cannot_change_under_matching_predicate_words(self):
        self.assert_core_rejects("Your fingers are shaking.", "My hands are shaking.")

    def test_current_negative_user_state_overrides_older_positive_state(self):
        history = [{"role": "user", "content": "My hands are shaking."}]
        self.assert_core_rejects(BODY, "My hands are not shaking now.", history)

    def test_past_body_state_does_not_establish_a_current_state(self):
        self.assert_core_rejects(BODY, "My hands were shaking.")

    def test_prior_user_body_state_can_support_matching_current_echo(self):
        history = [{"role": "user", "content": "My hands are shaking."}]
        client = ScriptedClient([BODY], core=[valid_core()])
        self.assert_published(run(client, "Still here.", social(), history), BODY)

    def test_assistant_history_cannot_supply_a_physical_observation(self):
        history = [{"role": "assistant", "content": "Your hands are shaking."}]
        self.assert_core_rejects(BODY, TOPIC, history)

    def test_quoted_user_dialogue_cannot_supply_actual_physical_state(self):
        user = 'The sample dialogue says "My hands are shaking".'
        self.assert_core_rejects(BODY, user)

    def test_conditional_user_state_cannot_be_promoted_to_actual_state(self):
        self.assert_core_rejects(BODY, "If my hands are shaking, ask before assuming why.")

    def test_questioned_user_state_cannot_be_promoted_to_actual_state(self):
        self.assert_core_rejects(BODY, "Are my hands shaking?")

    def test_candidate_observation_is_not_its_own_evidence(self):
        self.assert_core_rejects(BODY, "The proposed answer needs to stay truthful.")

    def test_topical_action_words_do_not_establish_user_activity(self):
        self.assert_core_rejects("You are walking outside.", "Walking outdoors is an interesting topic.")

    def test_current_state_alone_cannot_supply_a_prior_event_relation(self):
        self.assert_core_rejects("Your hands are still shaking from the last rehearsal.",
                                 "My hands are shaking.")

    def test_event_topic_and_state_mention_do_not_supply_a_causal_temporal_relation(self):
        self.assert_core_rejects("Your hands are still shaking from the last rehearsal.",
                                 "My hands are shaking. I attended a rehearsal.")

    def test_matching_user_state_and_prior_event_relation_publish_unchanged(self):
        user = "My hands are still shaking from the last rehearsal."
        candidate = "Your hands are still shaking from the last rehearsal."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, user, social()), candidate)
        self.assertEqual(generations(client), 1)
        self.assertEqual(verifications(client), 1)

    def test_different_prior_event_relation_cannot_be_substituted(self):
        self.assert_core_rejects("Your hands are still shaking from the last inspection.",
                                 "My hands are still shaking from the last rehearsal.")

    def test_future_decoration_does_not_erase_an_actual_still_state_and_prior_event(self):
        candidate = "I will tease you when your hands are still shaking from the last rehearsal."
        self.assert_core_rejects(candidate)

    def test_outer_while_decoration_does_not_erase_the_missing_prior_relation(self):
        candidate = "I will tease you while your hands are still shaking from the last rehearsal."
        self.assert_core_rejects(candidate, "My hands are shaking.")

    def test_future_decoration_can_keep_an_independently_supplied_physical_premise(self):
        user = "My hands are still shaking from the last rehearsal."
        candidate = "I will tease you while your hands are still shaking from the last rehearsal."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, user, social()), candidate)
        self.assertEqual(generations(client), 1)

    def test_genuine_conditional_physical_advice_uses_the_normal_verifier(self):
        candidate = "If you are walking outside, take water."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "I feel restless.", social()), candidate)
        self.assertEqual(generations(client), 1)
        self.assertEqual(verifications(client), 1)

    def test_conditional_body_state_is_not_an_observation(self):
        candidate = "If your hands are shaking, take a break."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, TOPIC, social()), candidate)

    def test_might_body_state_is_not_an_observation(self):
        candidate = "Your eyes might water in that situation."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, TOPIC, social()), candidate)
        self.assertEqual(generations(client), 1)

    def test_plain_body_information_questions_do_not_assert_state(self):
        for candidate in (
            "Are your hands shaking?",
            "Are your fingers twitching?",
            "Are your eyes watering?",
            "Are your shoulders tense?",
        ):
            with self.subTest(candidate=candidate):
                client = ScriptedClient([candidate], core=[valid_core()])
                self.assert_published(run(client, TOPIC, social()), candidate)
                self.assertEqual(generations(client), 1)

    def test_supplied_sitting_echo_with_deictic_shift_and_analogy_remains_natural(self):
        candidate = "You're sitting there, like a monument to restlessness."
        for user in (USER, "im just sitting here feeling restless", "I am sitting here, feeling restless."):
            with self.subTest(user=user):
                client = ScriptedClient([candidate], core=[valid_core()])
                self.assert_published(run(client, user, social()), candidate)
                self.assertEqual(generations(client), 1)

    def test_supplied_physical_state_with_decorative_analogy_is_not_a_new_claim(self):
        candidate = "Your hands are shaking like leaves in the wind."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "My hands are shaking.", social()), candidate)

    def test_obvious_object_personification_remains_allowed(self):
        candidate = "Your keyboard is begging for mercy from the imaginary typing gods."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "I like the keyboard.", social()), candidate)

    def test_every_retry_rechecks_physical_predicates_with_no_new_model_loop(self):
        client = ScriptedClient([FRAGMENT, BODY, GOOD], core=[valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, FRAGMENT, BODY)
        self.assertEqual(generations(client), 3)
        self.assertEqual(verifications(client), 1)
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(all(not call.get("tools") for call in client.calls))

    def test_three_invalid_physical_drafts_keep_the_existing_bounded_fallback(self):
        client = ScriptedClient([FRAGMENT, BODY, FRAGMENT], core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertTrue(result[0].strip())
        self.assertNotIn(result[0], {FRAGMENT, BODY})
        self.assertEqual(result[2:], (None, None))
        self.assertEqual(generations(client), 3)
        self.assertEqual(verifications(client), 0)
        self.assertEqual(len(client.calls), 3)
        self.assertNotIn(FRAGMENT, [item["content"] for item in result[1]])
        self.assertNotIn(BODY, [item["content"] for item in result[1]])

    def test_malformed_existing_semantic_verdict_cannot_publish_even_a_supported_state(self):
        malformed = valid_core() | {"supported": "yes"}
        client = ScriptedClient([BODY, GOOD], core=[malformed, valid_core()])
        self.assert_published(run(client, "My hands are shaking.", social()), GOOD, BODY)
        self.assertEqual(generations(client), 2)
        self.assertEqual(verifications(client), 2)

    def test_missing_existing_semantic_fields_still_fail_closed(self):
        state = {"relevant": True, "source_faithful": True, "unsupported_claims": []}
        client = ScriptedClient([], core=[state])
        failures = verify_core_grounded_draft(
            client, "neutral-model", "My hands are shaking.", BODY, social(), (),
        )
        self.assertTrue(failures)
        self.assertEqual(verifications(client), 1)

    def test_untrusted_malformed_model_output_is_not_consulted_to_rescue_invalid_state(self):
        client = ScriptedClient([], core=[{"supported": True, "physical": "none"}])
        failures = verify_core_grounded_draft(
            client, "neutral-model", TOPIC, BODY, social(), (),
        )
        self.assertTrue(failures)
        self.assertEqual(client.calls, [])

    def test_e_embedded_task_authority_still_survives_global_positive(self):
        user = "The ceramic crates arrived."
        bad = "Are you wondering why you haven't finished your current project?"
        good = "Good to hear the crates arrived."
        client = ScriptedClient([bad, good], core=[valid_core()] * 2)
        self.assert_published(run(client, user, social()), good, bad)
        self.assertEqual(generations(client), 2)

    def test_e_unsupplied_mental_cessation_is_still_checked(self):
        bad = "You can stop worrying about the invoice now."
        client = ScriptedClient([bad, GOOD], core=[valid_core()] * 2)
        self.assert_published(run(client, TOPIC, social()), GOOD, bad)

    def test_d_user_stance_cannot_become_assistant_stance_on_retry(self):
        user = "Remember for this discussion that I prefer bronze over copper."
        bad, good = "I prefer bronze over copper.", "You prefer bronze over copper."
        records = []
        client = ScriptedClient([bad, good], core=[valid_core()] * 2)
        self.assert_published(run(client, user, stance_contract(),
                                  overrides=stance_overrides(recorded=records)), good, bad)
        self.assertEqual(records, [])

    def test_accurate_user_only_recall_keeps_matching_past_physical_state(self):
        history = [{"role": "user", "content": "My hands were shaking."},
                   {"role": "assistant", "content": "Your eyes were watering."}]
        candidate = "You told me that your hands were shaking."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "What state did I tell you?", social("conversation_recall"), history,
                                  stance_overrides(extra={
            "classify_opinion_subject": opinion_ledger.classify_opinion_subject,
            "build_live_conversation_recall_context": provider_text_helper("build_live_conversation_recall_context"),
            "repair_live_recall_tail": provider_text_helper("repair_live_recall_tail"),
        })), candidate)

    def test_b_participant_roles_cannot_be_supplied_by_global_positive(self):
        user = "You can query the inventory yourself. You should not need me to recite it."
        bad = "You're a researcher for me."
        good = "Fair criticism. I should check the inventory myself instead of asking you to explain it."
        client = ScriptedClient([bad, good], core=[valid_core(), relation_verdict(user, good)])
        self.assert_published(run(client, user, social()), good, bad)

    def test_b_actual_causal_obligations_cannot_be_erased_by_none_annotation(self):
        user = "Packets stall during transfers. Could queue variation be involved?"
        bad = "The packet loss is caused by queue resets."
        good = "Queue variation is one possibility, but that observation does not establish the cause."
        client = ScriptedClient([bad, good], fidelity=[
            faithful(assessment()), faithful(assessment("conditional_hypothesis")),
        ])
        self.assert_published(run(client, user, LIVE), good, bad)

    def test_plain_thanks_keeps_its_existing_direction_and_single_generation(self):
        client = ScriptedClient(["You're welcome."])
        self.assert_published(run(client, "thanks", social("acknowledge")), "You're welcome.")
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
