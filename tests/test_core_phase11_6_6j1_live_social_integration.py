"""Real restricted-social generation/retry/history integration, offline."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import verify_core_grounded_draft
from core.user_history_obligations import build_user_history_packet
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications
from test_core_phase11_6_6j1_live_social_authority import HISTORY, OBJECT, USER, LOCATION


GOOD = "That gives us a clear reference for this chat."


def positive_history(candidate, user=USER, *, history=(), source_id="current_user", quote=None):
    sources = {"current_user": user}
    prior = [item["content"] for item in history if item["role"] == "user"][-4:]
    sources.update({"prior_user_" + str(index): value for index, value in enumerate(prior, 1)})
    value = build_user_history_packet(candidate, sources)
    if not value["obligations"]:
        raise AssertionError("Test candidate must require a Core-owned history assessment")
    return valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id,
         "source_quote": user if quote is None else quote}
        for item in value["obligations"]
    ]}


class LiveSocialAuthorityProductionTests(unittest.TestCase):
    def assert_publication(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for text in withheld:
            self.assertNotIn(text, [item["content"] for item in result[1]])

    def retry(self, candidate, user=USER, *, verdict=None, history=()):
        client = ScriptedClient([candidate, GOOD], core=[valid_core() if verdict is None else verdict, valid_core()])
        self.assert_publication(run(client, user, social(), history), GOOD, candidate)
        self.assertEqual((generations(client), verifications(client)), (2, 2))
        self.assertEqual(len(client.calls), 4, "Reuse the ordinary semantic call; no additional loop")
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def single(self, candidate, user=USER, history=()):
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_publication(run(client, user, social(), history), candidate)
        self.assertEqual((generations(client), verifications(client)), (1, 1))
        return client

    def test_early_echo_and_discourse_suppose_do_not_authorize_user_history(self):
        self.retry(HISTORY)

    def test_supplied_user_decision_history_publishes_naturally(self):
        self.single(HISTORY, "I'm sitting here bored. I've finally decided to stop pretending that inspecting the console is productive.")

    def test_global_positive_with_unrelated_literal_quote_cannot_publish_history(self):
        self.retry(HISTORY, verdict=positive_history(HISTORY))

    def test_missing_scoped_history_assessment_fails_closed(self):
        client = ScriptedClient([], core=[valid_core()])
        errors = verify_core_grounded_draft(client, "neutral-model", USER, HISTORY, social(), [])
        self.assertTrue(any("user-history" in item and "missing" in item for item in errors), errors)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("CORE USER-HISTORY OBLIGATIONS", "\n".join(item["content"] for item in client.calls[0]["messages"]))

    def test_malformed_scoped_history_assessment_fails_closed(self):
        verdict = positive_history(HISTORY)
        verdict["history_assessments"][0]["supported"] = "yes"
        self.retry(HISTORY, verdict=verdict)

    def test_assistant_history_cannot_authorize_user_cessation(self):
        history = [{"role": "assistant", "content": "You've finally decided to stop pretending that inspecting the console is productive."}]
        self.retry(HISTORY, history=history)

    def test_current_user_denial_defeats_a_stale_user_history_quote(self):
        old = "I've finally decided to stop pretending that inspecting the console is productive."
        current = "I'm sitting here bored. I haven't finally decided to stop pretending that inspecting the console is productive."
        history = [{"role": "user", "content": old}]
        verdict = positive_history(HISTORY, current, history=history, source_id="prior_user_1", quote=old)
        self.retry(HISTORY, current, history=history, verdict=verdict)

    def test_presupposed_prior_object_event_cannot_publish_from_present_location(self):
        self.retry(OBJECT, LOCATION)

    def test_supplied_prior_object_event_publishes_naturally(self):
        self.single(OBJECT, "I left the red case behind in the van before.")

    def test_different_object_history_cannot_publish(self):
        current = "I left the blue case behind in the van before."
        self.retry(OBJECT, current, verdict=positive_history(OBJECT, current))

    def test_different_location_history_cannot_publish(self):
        current = "I left the red case behind in the office before."
        self.retry(OBJECT, current, verdict=positive_history(OBJECT, current))

    def test_assistant_history_cannot_supply_the_object_event(self):
        self.retry(OBJECT, LOCATION, history=[{"role": "assistant", "content": "You left the red case behind in the van before."}])

    def test_latest_user_negative_defeats_stale_prior_object_event(self):
        old = "I left the red case behind in the van before."
        current = "I never left the red case behind in the van."
        history = [{"role": "user", "content": old}]
        verdict = positive_history(OBJECT, current, history=history, source_id="prior_user_1", quote=old)
        self.retry(OBJECT, current, history=history, verdict=verdict)

    def test_harmless_object_personification_publishes(self):
        self.single("Your compiler is begging for mercy again.")

    def test_harmless_supplied_sitting_banter_publishes(self):
        self.single("Sitting there bored has apparently become today's main event.")

    def test_hypothetical_history_remains_nonassertive(self):
        self.single("If you've stopped inspecting the console, take a break.")

    def test_each_retry_checks_the_new_history_obligations(self):
        client = ScriptedClient([HISTORY, OBJECT, GOOD], core=[valid_core()] * 3)
        self.assert_publication(run(client, USER, social()), GOOD, HISTORY, OBJECT)
        self.assertEqual((generations(client), verifications(client)), (3, 3))
        self.assertEqual(len(client.calls), 6)

    def test_repeated_invalid_candidates_remain_bounded_and_absent_from_history(self):
        client = ScriptedClient([HISTORY, OBJECT, HISTORY], core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertTrue(result[0].strip())
        self.assertNotIn(result[0], {HISTORY, OBJECT})
        self.assertEqual(result[2:], (None, None))
        self.assertEqual((generations(client), verifications(client)), (3, 3))
        self.assertEqual(len(client.calls), 6)
        for text in (HISTORY, OBJECT):
            self.assertNotIn(text, [item["content"] for item in result[1]])


if __name__ == "__main__":
    unittest.main()
