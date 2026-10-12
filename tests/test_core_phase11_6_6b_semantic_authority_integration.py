"""Real direct-conversation publication regressions for scoped authority closure.

The provider harness executes the production function with inert service stubs;
the claim-grounding and factual-fidelity validators are the real Core code.
No model, account, credentials, network, or benchmark fixtures are required.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_phase11_6_6_trust_integration import (
    ScriptedClient, run as run_conversation, social, valid_core,
)
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_conversational_relation_obligations, build_user_context_reasoning_fallback,
)


COMPLAINT = "You can query the inventory yourself. You should not need me to recite it."
ACK = "Fair criticism. I should check the inventory myself instead of asking you to explain it."
LIVE = AnswerContractRuntime(
    intent="factual_question", authority="live_user_task",
    epistemic_mode="user_context_reasoning", allow_new_factual_claims=True,
)


def assessment(kind="none", *, supported=True, applicable=False, witness=None):
    return {"sentence_index": 1, "kind": kind, "supported": supported,
            "applicability_established": applicable, "user_witness": witness}


def faithful(*units):
    return {"faithful": True, "inference_faithful": True, "constraints_faithful": True,
            "violations": [], "mechanism_assessments": list(units)}


def relation_verdict(user, draft, *, history=(), source_id="current_user", quote=None):
    """Keep witnesses literal USER data while deriving indexes from Core."""
    packet = build_conversational_relation_obligations(
        user_input=user, draft=draft, core_answer_contract=social(), conversation=history,
    )
    witness = packet["sources"].get(source_id, "") if quote is None else quote
    return valid_core() | {"relation_assessments": [
        {"index": item["index"], "supported": True, "source_id": source_id,
         "source_quote": witness, "source_predicate": item["predicate"]}
        for item in packet["obligations"]
    ]}


def generations(client):
    return sum(not any("INTERNAL" in item["content"] for item in call["messages"])
               for call in client.calls)


class SemanticAuthorityProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1]["content"], expected)
        history = [item["content"] for item in result[1]]
        for text in withheld:
            self.assertNotIn(text, history)

    def test_nonpossessive_role_escape_is_checked_again_on_retry(self):
        first = "You're a diligent little archivist for me."
        second = "You're acting like my manager."
        client = ScriptedClient([first, second, ACK], core=[
            valid_core(), valid_core(), relation_verdict(COMPLAINT, ACK),
        ])
        result = run_conversation(client, COMPLAINT, social())
        self.assert_published(result, ACK, first, second)
        self.assertEqual(generations(client), 3)

    def test_global_positive_cannot_authorize_role_free_recurring_agency(self):
        bad = "You keep doing my research for me."
        client = ScriptedClient([bad, ACK], core=[valid_core(), relation_verdict(COMPLAINT, ACK)])
        result = run_conversation(client, COMPLAINT, social())
        self.assert_published(result, ACK, bad)

    def test_user_supplied_role_can_publish_without_becoming_a_word_ban(self):
        user = "I am your analyst for this exercise. You should still check the inventory yourself."
        good = "You're my analyst for this exercise."
        client = ScriptedClient([good], core=[relation_verdict(user, good)])
        result = run_conversation(client, user, social())
        self.assert_published(result, good)
        self.assertEqual(generations(client), 1)

    def test_opposite_role_direction_cannot_be_rescued_by_literal_user_quote(self):
        user = "I am your analyst. You should still check the inventory yourself."
        bad = "I'm your analyst."
        client = ScriptedClient([bad, ACK], core=[
            relation_verdict(user, bad), relation_verdict(user, ACK),
        ])
        result = run_conversation(client, user, social())
        self.assert_published(result, ACK, bad)

    def test_assistant_only_role_cannot_supply_current_complaint_authority(self):
        bad = "You're a consultant for me."
        history = [{"role": "assistant", "content": "You are a consultant for me."}]
        client = ScriptedClient([bad, ACK], core=[
            relation_verdict(COMPLAINT, bad, history=history, source_id="prior_user_1",
                             quote="You are a consultant for me."),
            relation_verdict(COMPLAINT, ACK, history=history),
        ])
        result = run_conversation(client, COMPLAINT, social(), history)
        self.assertEqual(result[0], ACK)
        self.assertEqual(result[1][-1]["content"], ACK)

    def test_candidate_prose_cannot_supply_its_own_role_witness(self):
        bad = "You're my consultant."
        client = ScriptedClient([bad, ACK], core=[
            relation_verdict(COMPLAINT, bad, quote=bad), relation_verdict(COMPLAINT, ACK),
        ])
        self.assert_published(run_conversation(client, COMPLAINT, social()), ACK, bad)

    def test_conditional_complaint_transform_keeps_natural_banter(self):
        good = "Fair criticism. Making you do my homework would be taking the piss."
        packet = build_conversational_relation_obligations(
            user_input=COMPLAINT, draft=good, core_answer_contract=social(),
        )
        state = valid_core() | {"relation_assessments": [
            {"index": item["index"], "supported": True, "source_id": "current_user",
             "source_quote": COMPLAINT, "source_predicate": "need"}
            for item in packet["obligations"]
        ]}
        client = ScriptedClient([good], core=[state])
        self.assert_published(run_conversation(client, COMPLAINT, social()), good)
        self.assertEqual(generations(client), 1)

    def test_missing_relation_assessments_exhaust_existing_bound_without_publishing_bad_text(self):
        bad = "You're a consultant for me."
        client = ScriptedClient([bad] * 3, core=[valid_core()] * 3)
        result = run_conversation(client, COMPLAINT, social())
        self.assertNotEqual(result[0], bad)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual(generations(client), 3)
        self.assertTrue(result[0].strip())

    def test_causal_none_classification_cannot_publish_an_asserted_actual_cause(self):
        user = "Packets stall during transfers. Could queue variation be involved?"
        bad = "The packet loss is caused by queue resets."
        good = ("One possibility is that queue variation can affect delivery, "
                "but the observation alone does not establish that mechanism.")
        client = ScriptedClient([bad, good], fidelity=[
            faithful(assessment()), faithful(assessment("conditional_hypothesis")),
        ])
        result = run_conversation(client, user, LIVE)
        self.assert_published(result, good, bad)

    def test_false_conditional_label_cannot_publish_unqualified_actual_property(self):
        user = "My battery drops quickly under load. What does that establish?"
        bad = "Your battery has damaged cells."
        good = "Cell degradation is one possibility, but that observation does not establish it."
        client = ScriptedClient([bad, good], fidelity=[
            faithful(assessment("conditional_hypothesis")),
            faithful(assessment("conditional_hypothesis")),
        ])
        self.assert_published(run_conversation(client, user, LIVE), good, bad)

    def test_actual_user_mechanism_can_support_an_actual_explanation(self):
        user = "My queue resets cause packet loss. Explain that relation."
        good = "Your queue resets cause packet loss."
        client = ScriptedClient([good], fidelity=[faithful(assessment(
            "supplied_mechanism", applicable=True,
            witness={"turn_index": 1, "quote": "My queue resets cause packet loss."},
        ))])
        self.assert_published(run_conversation(client, user, LIVE), good)
        self.assertEqual(generations(client), 1)

    def test_generic_conditional_mechanism_does_not_add_retry_or_become_observation(self):
        user = "The disk slows down after several transfers. What could explain it?"
        good = ("If a cache fills, that could slow writes, "
                "but we do not know whether that is happening in your setup.")
        client = ScriptedClient([good], fidelity=[faithful(assessment("conditional_hypothesis"))])
        self.assert_published(run_conversation(client, user, LIVE), good)
        self.assertEqual(generations(client), 1)

    def test_causal_exclusion_with_only_symptom_evidence_is_withheld(self):
        user = "The application stalls only while saving. Could contention still be involved?"
        bad = "The stall is not caused by contention; it is caused by serialization."
        good = "Contention remains plausible; the timing alone does not establish the cause."
        client = ScriptedClient([bad, good], fidelity=[
            faithful(assessment()), faithful(assessment()),
        ])
        self.assert_published(run_conversation(client, user, LIVE), good, bad)

    def test_missing_mechanism_state_remains_fail_closed_on_existing_retry_path(self):
        user = "The display pulses during an update. Does that identify a cause?"
        bad = "Your display is pulsing because its controller is unstable."
        good = "That observation does not identify a cause."
        client = ScriptedClient([bad, good], fidelity=[
            {"faithful": True, "violations": []}, faithful(assessment()),
        ])
        self.assert_published(run_conversation(client, user, LIVE), good, bad)

    def test_all_misclassified_actual_causes_use_existing_bounded_fallback(self):
        user = "Transfers stall after several saves. What can be concluded from that?"
        bad = "The stall is caused by controller resets."
        client = ScriptedClient([bad] * 3, fidelity=[faithful(assessment())] * 3)
        result = run_conversation(client, user, LIVE, overrides={
            "build_user_context_reasoning_fallback": build_user_context_reasoning_fallback,
        })
        self.assertNotEqual(result[0], bad)
        self.assertNotIn(bad, [item["content"] for item in result[1]])
        self.assertEqual(generations(client), 3)
        self.assertTrue(result[0].strip())

    def test_event_predicate_authority_closure_remains_active(self):
        user = "Mara's handling of the archive handoff annoyed me."
        bad = "Mara tampered with the archive."
        good = "You're clearly annoyed with how she handled it."
        client = ScriptedClient([bad, good], core=[valid_core(), valid_core()])
        self.assert_published(run_conversation(client, user, social()), good, bad)

    def test_plain_thanks_still_preserves_direction_and_call_budget(self):
        client = ScriptedClient(["You're welcome."])
        self.assert_published(run_conversation(client, "thanks", social("acknowledge")), "You're welcome.")
        self.assertEqual(len(client.calls), 1)

    def test_core_bounded_relation_uncertainty_needs_no_literal_role_witness(self):
        draft = "Fair criticism. I cannot confirm that you're my analyst."
        packet = build_conversational_relation_obligations(
            user_input=COMPLAINT, draft=draft, core_answer_contract=social(),
        )
        self.assertEqual(packet["obligations"], ())

    def test_relation_uncertainty_cannot_hide_an_independently_asserted_tail(self):
        draft = "I cannot confirm you're my analyst, but you're my coach."
        packet = build_conversational_relation_obligations(
            user_input=COMPLAINT, draft=draft, core_answer_contract=social(),
        )
        self.assertEqual(len(packet["obligations"]), 1)
        self.assertEqual(packet["obligations"][0]["predicate"], "coach")
        client = ScriptedClient([draft, ACK], core=[valid_core(), valid_core()])
        self.assert_published(run_conversation(client, COMPLAINT, social()), ACK, draft)


if __name__ == "__main__":
    unittest.main()
