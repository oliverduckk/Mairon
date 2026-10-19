"""Production retry/history closure for generic USER recurrence and credit."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import find_incidental_public_attribution_violations, verify_core_grounded_draft
from core.user_history_obligations import build_user_history_packet
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications
from test_core_phase11_6_6j1_live2_social_authority import REPEAT, MOTIVE, CREDIT

GOOD = "I'm here."


def approval(candidate, user, *, quote=None, source_id="current_user", history=()):
    sources = {"current_user": user}
    prior = [item["content"] for item in history if item["role"] == "user"][-4:]
    sources.update({"prior_user_" + str(index): value for index, value in enumerate(prior, 1)})
    value = build_user_history_packet(candidate, sources)
    if not value["obligations"]:
        raise AssertionError("This fixture requires an independent Core-owned obligation")
    return valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id,
         "source_quote": user if quote is None else quote}
        for item in value["obligations"]
    ]}


class SocialRecurrenceAndCreditProductionTests(unittest.TestCase):
    def published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for text in withheld:
            self.assertNotIn(text, [item["content"] for item in result[1]])

    def retry_history(self, candidate=REPEAT, user="Hello.", verdict=None, history=()):
        client = ScriptedClient([candidate, GOOD], core=[valid_core() if verdict is None else verdict, valid_core()])
        self.published(run(client, user, social(), history), GOOD, candidate)
        self.assertEqual((generations(client), verifications(client)), (2, 2))
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(all(not call.get("tools") for call in client.calls))
        return client

    def single(self, candidate, user="Hello.", history=(), overrides=None):
        client = ScriptedClient([candidate], core=[valid_core()])
        self.published(run(client, user, social(), history, overrides), candidate)
        self.assertEqual((generations(client), verifications(client)), (1, 1))
        return client

    def test_bare_activation_does_not_supply_repeated_user_action(self):
        self.retry_history("You're testing my label again?", "Mairon.")

    def test_global_positive_cannot_erase_missing_prior_act(self):
        self.retry_history()

    def test_global_positive_with_wrong_literal_quote_cannot_supply_prior_act(self):
        self.retry_history(verdict=approval(REPEAT, "Hello."))

    def test_matching_user_prior_act_allows_natural_recurrence(self):
        self.single(REPEAT, "I checked that before.")

    def test_unrelated_user_prior_act_does_not_authorize_it(self):
        self.retry_history(user="I repaired that before.")

    def test_assistant_prior_claim_does_not_authorize_recurrence(self):
        self.retry_history(history=[{"role": "assistant", "content": "You checked that before."}])

    def test_latest_denial_prevents_selecting_stale_positive_quote(self):
        old = "I checked that before."
        history = [{"role": "user", "content": old}]
        user = "I did not check that before."
        self.retry_history(user=user, history=history,
                           verdict=approval(REPEAT, user, quote=old, source_id="prior_user_1", history=history))

    def test_current_motive_is_not_authorised_by_i_think(self):
        self.retry_history(MOTIVE)

    def test_matching_user_motive_allows_faithful_echo(self):
        self.single(MOTIVE, "I'm just trying to see if you will change the label.")

    def test_conditional_motive_remains_nonassertive(self):
        self.single("If you're trying to change the label, tell me.")

    def test_harmless_object_personification_remains_available(self):
        self.single("Your compiler is begging for mercy again.")

    def test_simple_activation_acknowledgement_remains_available(self):
        self.single(GOOD, "Mairon.")

    def test_missing_scoped_assessment_fails_closed_with_one_existing_call(self):
        client = ScriptedClient([], core=[valid_core()])
        failures = verify_core_grounded_draft(client, "neutral-model", "Hello.", REPEAT, social(), [])
        self.assertTrue(any("user-history" in item and "missing" in item for item in failures), failures)
        self.assertEqual(len(client.calls), 1)

    def test_every_retry_is_checked_under_same_prior_act_rule(self):
        candidates = [REPEAT, "You're testing my label again?", GOOD]
        client = ScriptedClient(candidates, core=[valid_core()] * 3)
        self.published(run(client, "Hello.", social()), GOOD, *candidates[:2])
        self.assertEqual((generations(client), verifications(client)), (3, 3))
        self.assertEqual(len(client.calls), 6)

    def test_repeated_invalid_histories_remain_bounded(self):
        client = ScriptedClient([REPEAT] * 3, core=[valid_core()] * 3)
        result = run(client, "Hello.", social())
        self.assertNotEqual(result[0], REPEAT)
        self.assertNotIn(REPEAT, [item["content"] for item in result[1]])
        self.assertEqual((generations(client), verifications(client)), (3, 3))

    def test_modified_incidental_credit_survives_no_global_positive_override(self):
        client = ScriptedClient([CREDIT, GOOD], core=[valid_core(), valid_core()])
        self.published(run(client, "Keep the two formats separate.", social(), overrides={
            "find_incidental_public_attribution_violations": find_incidental_public_attribution_violations,
        }), GOOD, CREDIT)
        self.assertEqual((generations(client), verifications(client)), (2, 2))
        self.assertEqual(len(client.calls), 4)

    def test_user_supplied_credit_name_does_not_force_retry(self):
        self.single(CREDIT, "Ruvan's artistry is what I mean; keep the formats separate.", overrides={
            "find_incidental_public_attribution_violations": find_incidental_public_attribution_violations,
        })

    def test_every_credit_retry_is_rechecked_with_existing_verifier_schedule(self):
        bad2 = "That highlights Telva's original writing."
        client = ScriptedClient([CREDIT, bad2, GOOD], core=[valid_core()] * 3)
        self.published(run(client, "Keep the formats separate.", social(), overrides={
            "find_incidental_public_attribution_violations": find_incidental_public_attribution_violations,
        }), GOOD, CREDIT, bad2)
        self.assertEqual((generations(client), verifications(client)), (3, 3))
        self.assertEqual(len(client.calls), 6)


if __name__ == "__main__":
    unittest.main()
