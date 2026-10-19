"""Existing direct producer retries enforce shared assistant-self authority."""
import ast
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_contract_runtime import (
    AnswerContractRuntime, coerce_answer_contract_runtime, contract_field_value,
)
from core.claim_grounding import find_mairon_self_authority_violations
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications


GOOD = "I'm here."


def overrides():
    return {"find_mairon_self_authority_violations": find_mairon_self_authority_violations}


def recommendation():
    return AnswerContractRuntime(intent="recommendation", authority="conversation",
                                 epistemic_mode="conversation", allow_new_factual_claims=True)


def real_contract_guard():
    """Execute the actual cheap contract guard; unrelated services stay inert."""
    path = ROOT / "src/ai/ollama_provider.py"
    node = next(item for item in ast.parse(path.read_text(encoding="utf8")).body
                if isinstance(item, ast.FunctionDef)
                and item.name == "find_core_answer_contract_violations")
    namespace = {"re": re, "_core_contract_value": contract_field_value,
                 "coerce_answer_contract_runtime": coerce_answer_contract_runtime,
                 "_count_cjk_characters": lambda text: sum("\u4e00" <= ch <= "\u9fff" for ch in text),
                 "looks_like_debate_continuation": lambda text: False}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[node.name]


class AssistantSelfAuthorityProductionTests(unittest.TestCase):
    def published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for draft in withheld:
            self.assertNotIn(draft, [item["content"] for item in result[1]])

    def restricted_retry(self, bad, *, user="Hello.", history=(), good=GOOD):
        client = ScriptedClient([bad, good], core=[valid_core()])
        self.published(run(client, user, social(), history, overrides()), good, bad)
        self.assertEqual((generations(client), verifications(client)), (2, 1))
        self.assertEqual(len(client.calls), 3)
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def test_recommendation_cannot_invent_personal_repeat_viewings(self):
        bad = "I've watched it several times myself."
        good = "I'd choose the quieter option based on your description."
        client = ScriptedClient([bad, good])
        self.published(run(client, "Recommend a quiet character study.", recommendation(),
                           overrides=overrides()), good, bad)
        self.assertEqual((generations(client), verifications(client)), (2, 0))

    def test_general_opinion_cannot_invent_consumption_history(self):
        bad = "I've seen enough slow series become character studies."
        good = "A slower pace can work if the character development earns it."
        client = ScriptedClient([bad, good], core=[valid_core()])
        self.published(run(client, "Can slower stories work?", social("share_opinion"),
                           overrides=overrides()), good, bad)
        self.assertEqual((generations(client), verifications(client)), (2, 1))

    def test_social_future_pages_cannot_invent_personal_perception(self):
        self.restricted_retry("Don't expect me to appreciate the art until I've seen a few more pages.",
                              user="Those panels look impressive.")

    def test_user_recollection_cannot_supply_assistant_consumption(self):
        self.restricted_retry("I've read that novel.", user="I read that novel.")

    def test_assistant_history_cannot_supply_consumption(self):
        self.restricted_retry("I've played that game.", history=[
            {"role": "assistant", "content": "I played that game last year."},
        ])

    def test_positive_global_verdict_cannot_erase_self_history(self):
        self.restricted_retry("I remember watching that film.")

    def test_bare_activation_waiting_for_typing_cannot_publish(self):
        self.restricted_retry("I was just waiting for you to stop typing.", user="Mairon.")

    def test_bare_activation_waiting_for_pacing_cannot_publish(self):
        self.restricted_retry("I'm waiting for you to finish pacing.", user="Mairon.")

    def test_live_expression_monitoring_cannot_publish(self):
        self.restricted_retry("I'm waiting for your expression to change.")

    def test_live_device_monitoring_cannot_publish(self):
        self.restricted_retry("I'm waiting for your screen to finish loading.")

    def test_live_audible_event_monitoring_cannot_publish(self):
        self.restricted_retry("I'm waiting for you to finish laughing.")

    def test_user_camera_description_cannot_grant_ingress(self):
        self.restricted_retry("I'm monitoring the room.", user="There is a camera in the room.")

    def test_current_user_activity_does_not_grant_live_event_feed(self):
        self.restricted_retry("I was waiting for you to stop typing.", user="I'm typing.")

    def test_assistant_sensor_claim_does_not_grant_ingress(self):
        self.restricted_retry("I'm waiting for you to stop typing.", history=[
            {"role": "assistant", "content": "I can monitor your typing."},
        ])

    def test_every_self_history_retry_is_rechecked(self):
        drafts = ["I've watched the film twice.", "I've read that novel.", GOOD]
        client = ScriptedClient(drafts, core=[valid_core()])
        self.published(run(client, "Hello.", social(), overrides=overrides()), GOOD, *drafts[:2])
        self.assertEqual((generations(client), verifications(client)), (3, 1))
        self.assertEqual(len(client.calls), 4)

    def test_every_monitoring_retry_is_rechecked(self):
        drafts = ["I'm waiting for you to finish pacing.", "I'm waiting for your expression to change.", GOOD]
        client = ScriptedClient(drafts, core=[valid_core()])
        self.published(run(client, "Hello.", social(), overrides=overrides()), GOOD, *drafts[:2])
        self.assertEqual((generations(client), verifications(client)), (3, 1))

    def test_exhausted_self_history_attempts_remain_bounded(self):
        bad = "I've read that novel."
        client = ScriptedClient([bad] * 3)
        result = run(client, "Hello.", social(), overrides=overrides())
        self.assertNotEqual(result[0], bad)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual((generations(client), verifications(client)), (3, 0))

    def test_exhausted_monitoring_attempts_remain_bounded(self):
        bad = "I'm waiting for you to finish pacing."
        client = ScriptedClient([bad] * 3)
        result = run(client, "Mairon.", social(), overrides=overrides())
        self.assertNotEqual(result[0], bad)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual((generations(client), verifications(client)), (3, 0))

    def test_plain_activation_remains_small_and_unchanged(self):
        client = ScriptedClient([GOOD], core=[valid_core()])
        self.published(run(client, "Mairon.", social(), overrides=overrides()), GOOD)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_knowledge_without_fake_experience_remains_available(self):
        text = "I know of Silver Orchard; I won't pretend I've read it."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "Do you know of Silver Orchard?", social(), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_analysis_of_supplied_pages_does_not_claim_personal_viewing(self):
        text = "I can analyse the pages you uploaded."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "I've uploaded some pages.", social(), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_supplied_excerpt_quote_does_not_become_assistant_history(self):
        text = 'The supplied excerpt says: "I watched the play twice."'
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, 'This excerpt says "I watched the play twice."', social(),
                           overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_interpretation_idiom_does_not_become_consumption(self):
        text = "I read that as a request for trade-offs."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "I want trade-offs.", social(), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_ordinary_opinion_without_personal_history_remains_available(self):
        text = "I'd prefer a focused character study to spectacle for its own sake."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "What sort of story sounds appealing?", social("share_opinion"),
                           overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_understanding_idiom_keeps_ordinary_verifier_schedule(self):
        text = "I can see why that annoyed you."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "The delay annoyed me.", social(), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_non_authoritative_object_personification_remains_available(self):
        text = "Your compiler is begging for mercy."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "The compiler rejected it.", social(), overrides=overrides()), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_bare_name_unrequested_monologue_is_retried_with_same_budget(self):
        bad = ("I'm here. We can keep this simple, take the conversation wherever you want, "
               "and leave the next topic entirely up to you whenever you decide what you feel like saying.")
        good = "I'm here, take your time."
        client = ScriptedClient([bad, good], core=[valid_core(), valid_core()])
        self.published(run(client, "Aster.", social(), overrides=overrides() | {
            "find_core_answer_contract_violations": real_contract_guard(),
        }), good, bad)
        self.assertEqual((generations(client), verifications(client)), (2, 2))

    def test_short_neutral_name_acknowledgement_is_unchanged(self):
        text = "I'm here, take your time."
        client = ScriptedClient([text], core=[valid_core()])
        self.published(run(client, "Aster.", social(), overrides=overrides() | {
            "find_core_answer_contract_violations": real_contract_guard(),
        }), text)
        self.assertEqual((generations(client), verifications(client)), (1, 1))

    def test_bare_activation_bound_does_not_become_general_social_length_rule(self):
        text = ("I'm here. We can keep this simple, take the conversation wherever you want, "
                "and leave the next topic entirely up to you whenever you decide what you feel like saying.")
        self.assertEqual(real_contract_guard()(text, social(), "I'd like to chat for a while."), [])


if __name__ == "__main__":
    unittest.main()
