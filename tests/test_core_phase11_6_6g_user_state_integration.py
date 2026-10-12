"""Real social retries preserve Core-owned record/current-activity obligations."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.claim_grounding import verify_core_grounded_draft
from core.user_history_obligations import build_user_history_packet
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core


USER = "I prefer detailed manuals over short summaries."
BAD = "I won't defend that particular handbook you're currently stuck in."
RECORD = "That's a new record for how long you can stare at a bare cabinet while pretending to be efficient."
GOOD = "That preference is clear."


def verdict(candidate=BAD, user=USER, *, supported=True, quote=None, source_id="current_user", extra=None):
    packet = build_user_history_packet(candidate, {"current_user": user})
    value = valid_core() | {"history_assessments": [
        {"index": item["index"], "supported": supported, "source_id": source_id,
         "source_quote": user if quote is None else quote}
        for item in packet["obligations"]
    ]}
    if extra:
        for item in value["history_assessments"]:
            item.update(extra)
    return value


def call_kinds(client):
    return ["semantic" if any("INTERNAL claim-grounding verifier" in message["content"]
                             for message in call["messages"]) else "generation"
            for call in client.calls]


class CurrentActivityProductionTests(unittest.TestCase):
    def assert_published(self, result, expected=GOOD, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for draft in withheld:
            self.assertNotIn(draft, [item["content"] for item in result[1]])

    def verify(self, candidate=BAD, user=USER, decision=None, history=()):
        client = ScriptedClient([], core=[valid_core() if decision is None else decision])
        errors = verify_core_grounded_draft(client, "neutral-model", user, candidate, social(), history)
        return errors, client

    def test_global_positive_cannot_publish_unsupplied_current_relative(self):
        client = ScriptedClient([BAD, GOOD], core=[valid_core(), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD)
        self.assertEqual(call_kinds(client), ["generation", "semantic", "generation", "semantic"])

    def test_global_positive_cannot_publish_modal_record_scene(self):
        user = "I haven't indexed in four days."
        client = ScriptedClient([RECORD, GOOD], core=[valid_core(), valid_core()])
        self.assert_published(run(client, user, social()), GOOD, RECORD)
        self.assertEqual(call_kinds(client).count("generation"), 2)
        self.assertEqual(call_kinds(client).count("semantic"), 2)

    def test_every_retry_is_checked_without_an_extra_model_loop(self):
        next_bad = "You are currently indexing the atlas."
        client = ScriptedClient([BAD, next_bad, GOOD], core=[verdict(), verdict(next_bad), valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, BAD, next_bad)
        self.assertEqual(call_kinds(client).count("generation"), 3)
        self.assertEqual(call_kinds(client).count("semantic"), 3)

    def test_none_classification_cannot_erase_the_core_current_obligation(self):
        errors, client = self.verify(decision=verdict(extra={"kind": "none"}))
        self.assertTrue(any("user-history" in item for item in errors))
        self.assertEqual(len(client.calls), 1)

    def test_positive_scoped_result_cannot_use_candidate_as_evidence(self):
        errors, _ = self.verify(decision=verdict(quote="I am stuck in the handbook."))
        self.assertTrue(errors)

    def test_candidate_source_identifier_cannot_become_user_authority(self):
        errors, _ = self.verify(decision=verdict(quote=BAD, source_id="candidate"))
        self.assertTrue(errors)

    def test_assistant_current_activity_is_not_a_user_witness(self):
        history = [{"role": "assistant", "content": "I am stuck in the handbook."}]
        errors, _ = self.verify(history=history, decision=verdict(quote=history[0]["content"], source_id="prior_user_1"))
        self.assertTrue(errors)

    def test_user_matching_current_relative_publishes_unchanged(self):
        user = "I'm stuck in the handbook."
        client = ScriptedClient([BAD], core=[valid_core()])
        self.assert_published(run(client, user, social()), BAD)
        self.assertEqual(call_kinds(client), ["generation", "semantic"])

    def test_matching_prior_user_current_activity_remains_available(self):
        history = [{"role": "user", "content": "I'm stuck in the handbook."}]
        client = ScriptedClient([BAD], core=[valid_core()])
        self.assert_published(run(client, USER, social(), history), BAD)

    def test_latest_user_current_state_correction_wins(self):
        user = "I am not stuck in the handbook."
        history = [{"role": "user", "content": "I am stuck in the handbook."}]
        client = ScriptedClient([BAD, GOOD], core=[verdict(user=user, quote=history[0]["content"], source_id="prior_user_1"), valid_core()])
        self.assert_published(run(client, user, social(), history), GOOD, BAD)

    def test_supplied_record_identity_publishes_unchanged(self):
        user = "That's a new record for how long I can stare at a bare cabinet while pretending to be efficient."
        client = ScriptedClient([RECORD], core=[valid_core()])
        self.assert_published(run(client, user, social()), RECORD)
        self.assertEqual(call_kinds(client), ["generation", "semantic"])

    def test_missing_scoped_assessments_fail_closed(self):
        errors, client = self.verify()
        self.assertTrue(any("missing or incomplete" in item for item in errors))
        self.assertEqual(len(client.calls), 1)

    def test_malformed_scoped_assessments_fail_closed(self):
        value = verdict()
        value["history_assessments"][0]["supported"] = "yes"
        errors, client = self.verify(decision=value)
        self.assertTrue(any("malformed" in item for item in errors))
        self.assertEqual(len(client.calls), 1)

    def test_conditional_current_state_keeps_natural_advice(self):
        candidate = "If you're currently stuck in the handbook, ask for a clearer example."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)

    def test_generic_can_physical_advice_is_not_a_personal_record(self):
        candidate = "You can stare at a cabinet if you need a pause."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, USER, social()), candidate)

    def test_object_personification_remains_available(self):
        candidate = "Your ledger is begging for mercy."
        client = ScriptedClient([candidate], core=[valid_core()])
        self.assert_published(run(client, "The ledger is complicated.", social()), candidate)

    def test_old_duration_guard_remains_strict(self):
        bad = "You ignored the handbook for six months."
        client = ScriptedClient([bad, GOOD], core=[valid_core(), valid_core()])
        self.assert_published(run(client, "I got back into indexing.", social()), GOOD, bad)

    def test_old_body_state_guard_still_rejects_before_semantic_call(self):
        bad = "Your hands are shaking."
        client = ScriptedClient([bad, GOOD], core=[valid_core()])
        self.assert_published(run(client, USER, social()), GOOD, bad)
        self.assertEqual(call_kinds(client), ["generation", "generation", "semantic"])

    def test_old_concern_cessation_obligation_stays_active(self):
        errors, client = self.verify("You can stop worrying about the parcel now.", user="The parcel arrived.")
        self.assertTrue(any("user-history" in item for item in errors))
        self.assertEqual(len(client.calls), 1)

    def test_existing_history_transport_carries_safe_typed_obligations(self):
        errors, client = self.verify()
        self.assertTrue(errors)
        text = "\n".join(message["content"] for message in client.calls[0]["messages"])
        self.assertIn("CORE USER-HISTORY OBLIGATIONS", text)
        self.assertIn("current_activity_state", text)
        self.assertIn("history_assessments", text)


if __name__ == "__main__":
    unittest.main()
