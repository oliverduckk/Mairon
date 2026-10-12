"""Production retries must preserve Core-owned behaviour presuppositions."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from core.claim_grounding import verify_core_grounded_draft
from core.user_history_obligations import build_user_history_packet


USER = "I got back into cataloguing the archive."
BAD = "The catalogue looks better once you stop filing cards carelessly."
GOOD = "Good to hear you're enjoying the archive again."


def state(candidate=BAD, user=USER, *, quote=None, source_id="current_user", supported=True):
    value = build_user_history_packet(candidate, {"current_user": user})
    return valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": supported,
         "source_id": source_id, "source_quote": user if quote is None else quote}
        for item in value["obligations"]
    ]}


def generations(client):
    return sum(not any("INTERNAL" in item["content"] for item in call["messages"])
               for call in client.calls)


class UserPresuppositionProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1]["content"], expected)
        for candidate in withheld:
            self.assertNotIn(candidate, [item["content"] for item in result[1]])

    def test_global_positive_without_scoped_assessment_retries_real_social_path(self):
        client = ScriptedClient([BAD, GOOD], core=[valid_core(), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)
        self.assertEqual(generations(client), 2)

    def test_positive_scoped_assessment_without_matching_user_activity_is_rejected(self):
        client = ScriptedClient([BAD, GOOD], core=[state(), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)

    def test_retry_presupposition_is_checked_again(self):
        later_bad = "The shelf improves after you quit stacking boxes unevenly."
        client = ScriptedClient([BAD, later_bad, GOOD], core=[state(), state(later_bad), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD, later_bad)
        self.assertEqual(generations(client), 3)

    def test_model_none_label_cannot_suppress_core_presupposition(self):
        value = state()
        value["history_assessments"][0]["kind"] = "none"
        client = ScriptedClient([BAD, GOOD], core=[value, valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)

    def test_supported_user_activity_publishes_natural_transition_unchanged(self):
        user = "I've been filing cards carelessly."
        client = ScriptedClient([BAD], core=[valid_core()])
        self.assert_published(run(client, user, social()), BAD)
        self.assertEqual(generations(client), 1)

    def test_current_user_progressive_publishes_bounded_transition_unchanged(self):
        client = ScriptedClient([BAD], core=[valid_core()])
        self.assert_published(run(client, "I'm filing cards carelessly.", social()), BAD)

    def test_prior_user_activity_can_ground_the_transition(self):
        history = [{"role": "user", "content": "I've been filing cards carelessly."}]
        client = ScriptedClient([BAD], core=[valid_core()])
        self.assert_published(run(client, USER, social(), history), BAD)

    def test_assistant_prior_activity_is_not_authority(self):
        history = [{"role": "assistant", "content": "You've been filing cards carelessly."}]
        value = state(quote="You've been filing cards carelessly.", source_id="prior_user_1")
        client = ScriptedClient([BAD, GOOD], core=[value, valid_core()])
        self.assert_published(run(client, USER, social(), history), GOOD, BAD)

    def test_conditional_activity_is_not_promoted_by_scoped_positive(self):
        user = "If I've been filing cards carelessly, tell me."
        client = ScriptedClient([BAD, GOOD], core=[state(user=user), valid_core()])
        self.assert_published(run(client, user, social()), GOOD, BAD)

    def test_generic_conditional_explanation_remains_unchanged(self):
        candidate = "If you stop filing cards carelessly, the catalogue might improve."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)

    def test_explicitly_figurative_humour_remains_unchanged(self):
        candidate = "The archive gods will applaud once you stop wrestling cosmic dragons metaphorically."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)

    def test_scoped_negative_survives_global_positive(self):
        client = ScriptedClient([], core=[state(supported=False)])
        failures = verify_core_grounded_draft(client, "neutral-model", USER, BAD, social(), ())
        self.assertTrue(any("user-history" in item for item in failures))

    def test_malformed_scoped_support_still_fails_closed(self):
        value = state()
        value["history_assessments"][0]["supported"] = "yes"
        client = ScriptedClient([BAD, GOOD], core=[value, valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)

    def test_repeated_invalid_candidates_preserve_existing_three_attempt_bound(self):
        client = ScriptedClient([BAD] * 3, core=[valid_core()] * 3)
        result = run(client, USER, social())
        self.assertNotEqual(result[0], BAD)
        self.assertNotIn(BAD, [item["content"] for item in result[1]])
        self.assertEqual(generations(client), 3)
        self.assertTrue(result[0].strip())

    def test_no_new_verifier_call_or_assessment_interface_is_required(self):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(client, "neutral-model", USER, BAD, social(), ())
        self.assertTrue(failures)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("history_assessments", "\n".join(item["content"] for item in client.calls[0]["messages"]))


if __name__ == "__main__":
    unittest.main()
