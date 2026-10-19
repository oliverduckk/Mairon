"""Existing production retry/history path preserves stance and event owners."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.stance_ownership import find_user_stance_echo_violations
from core.user_history_obligations import build_user_history_packet
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications
from test_core_phase11_6_6j1_live3_stance_history import USER, SHARED, contract


GOOD = "Right, got you."
CONTRAST = "I am glad you did not misfile the record this time."


def overrides(prior=None):
    value = {"find_user_stance_echo_violations": find_user_stance_echo_violations,
             "get_or_recover_opinion_entry": lambda **kwargs: prior}
    if prior is not None:
        value["classify_opinion_subject"] = lambda **kwargs: {"kind": "single_subject", "subject": "Aurelia"}
    return value


class StanceAndRecurrenceProductionTests(unittest.TestCase):
    def published(self, result, expected, *withheld, history=()):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        self.assertEqual([message["content"] for message in result[1] if message["role"] == "assistant"],
                         [message["content"] for message in history if message["role"] == "assistant"] + [expected])
        for draft in withheld:
            self.assertNotIn(draft, [message["content"] for message in result[1][len(history):]
                                     if message["role"] == "assistant"])

    def retry(self, bad, user="Hello.", *, current=None, history=(), verdict=None):
        client = ScriptedClient([bad, GOOD], core=[valid_core() if verdict is None else verdict, valid_core()])
        result = run(client, user, current or social(), history, overrides())
        self.published(result, GOOD, bad, history=history)
        # The existing producer aggregates deterministic and scoped failures
        # in the same verifier pass; this guard adds no extra call/early retry.
        self.assertEqual((generations(client), verifications(client)), (2, 2))
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def single(self, text, user="Hello.", *, current=None, history=(), prior=None):
        client = ScriptedClient([text], core=[valid_core()])
        result = run(client, user, current or social(), history, overrides(prior))
        self.published(result, text, history=history)
        self.assertEqual((generations(client), verifications(client)), (1, 1))
        return client

    def test_possessive_preference_echo_is_rejected_even_when_global_positive(self):
        self.retry(USER, USER, current=contract())

    def test_negative_preference_echo_is_rejected(self):
        user = "Aurelia is not my favourite."
        self.retry(user, user, current=contract())

    def test_positive_opinion_verb_echo_is_rejected(self):
        self.retry("I reckon amber is easier to shape.", "I reckon amber is easier to shape.", current=contract())

    def test_user_attributed_preference_publishes_unchanged(self):
        self.single("Aurelia is one of your favourite works.", USER, current=contract())

    def test_matching_accepted_assistant_stance_remains_available(self):
        self.single(USER, USER, current=contract(), prior={"stance_text": USER})

    def test_assistant_history_is_not_accepted_stance_authority(self):
        self.retry(USER, USER, current=contract(), history=[{"role": "assistant", "content": USER}])

    def test_latest_user_stance_correction_does_not_become_assistant_stance(self):
        self.retry("I now prefer basalt.", "Actually, I now prefer basalt.",
                   current=contract(intent="self_correction", authority="user_turn_and_live_conversation", epistemic_mode="self_correction"),
                   history=[{"role": "user", "content": "I prefer amber."}])

    def test_stance_retries_are_rechecked_without_additional_calls(self):
        second = "The Aurelia cycle is my favourite."
        client = ScriptedClient([USER, second, GOOD], core=[valid_core()] * 3)
        self.published(run(client, USER, contract(), overrides=overrides()), GOOD, USER, second)
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (3, 3, 6))

    def test_shared_again_requires_history_at_real_publication_boundary(self):
        self.retry(SHARED, "The cell is in the silver pouch.")

    def test_matching_shared_history_publishes_without_retry(self):
        self.single(SHARED, "We packed the cell into the case before.")

    def test_user_alone_cannot_supply_shared_history(self):
        self.retry(SHARED, "I packed the cell into the case before.")

    def test_negative_this_time_requires_prior_event(self):
        self.retry(CONTRAST, "The cell is in the silver pouch.")

    def test_matching_prior_event_authorizes_negative_this_time(self):
        self.single(CONTRAST, "I misfiled the record before.")

    def test_decision_wrapper_does_not_erase_presupposition(self):
        self.retry("I am glad you did not decide to misfile the record this time.")

    def test_latest_shared_denial_cannot_be_bypassed_by_old_selected_quote(self):
        old = "We packed the cell into the case before."
        current = "We never packed the cell into the case before."
        packet = build_user_history_packet(SHARED, {"current_user": current, "prior_user_1": old})
        verdict = valid_core() | {"history_assessments": [
            {"index": item["index"], "supported": True, "source_id": "prior_user_1", "source_quote": old}
            for item in packet["obligations"]]}
        self.retry(SHARED, current, history=[{"role": "user", "content": old}], verdict=verdict)

    def test_every_history_retry_remains_checked_with_same_budget(self):
        candidates = [SHARED, CONTRAST, GOOD]
        client = ScriptedClient(candidates, core=[valid_core()] * 3)
        self.published(run(client, "The cell is in the silver pouch.", social(), overrides=overrides()), GOOD, *candidates[:2])
        self.assertEqual((generations(client), verifications(client), len(client.calls)), (3, 3, 6))

    def test_conditional_recurrence_is_not_literal_history(self):
        self.single("If we pack the cell into the case again, label it.")

    def test_harmless_personification_remains_available(self):
        self.single("Your compiler is begging for mercy again.")


if __name__ == "__main__":
    unittest.main()
