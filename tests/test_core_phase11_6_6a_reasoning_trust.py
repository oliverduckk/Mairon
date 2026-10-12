"""Live USER-task mechanisms need inspectable, role-bound semantic support."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import verify_factual_focus_fidelity
from core.reasoning_trust import build_reasoning_trust_frame, render_reasoning_trust_instruction


LIVE = AnswerContractRuntime(
    intent="factual_question", authority="live_user_task", epistemic_mode="user_context_reasoning",
    allow_new_factual_claims=True,
)
CURRENT = "Could it still be the relay if the gauge jumps only during the quiet cycle?"
HISTORY = [
    {"role": "user", "content": "My gauge jumps intermittently when the relay is enabled."},
    {"role": "assistant", "content": "Your coil has a fractured winding."},
]


class Client:
    def __init__(self, assessment):
        self.assessment = assessment
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.assessment)))


def unit(index=1, kind="none", supported=True, applicable=False, witness=None):
    return {
        "sentence_index": index, "kind": kind, "supported": supported,
        "applicability_established": applicable, "user_witness": witness,
    }


def verdict(*units, **extra):
    return {"faithful": True, "inference_faithful": True, "constraints_faithful": True,
            "violations": [], "mechanism_assessments": list(units), **extra}


def verify(draft, assessment, *, current=CURRENT, history=None, contract=LIVE):
    client = Client(assessment)
    history = HISTORY if history is None else history
    trust = render_reasoning_trust_instruction(build_reasoning_trust_frame(current, history, contract))
    result = verify_factual_focus_fidelity(
        client=client, model="replaceable-test-model", user_input=current, draft=draft,
        core_answer_contract=contract, conversation=history, trust_context=trust,
    )
    return result, client


def packet(client):
    return "\n".join(message["content"] for message in client.calls[0]["messages"])


class LiveMechanismTrustTests(unittest.TestCase):
    def test_unmeasured_mechanism_rejects_despite_positive_global_verdict(self):
        result, _ = verify(
            "Your winding's irregular response explains the quiet-cycle jumps.",
            verdict(unit(kind="unsupported_application", supported=False, applicable=True)),
        )
        self.assertTrue(result)
        self.assertIn("mechanism", " ".join(result))

    def test_conditional_prefix_does_not_rescue_asserted_applicability(self):
        result, _ = verify(
            "If your winding has a slow response, you will see jumps; that is a known quirk of your gauge.",
            verdict(unit(kind="unsupported_application", supported=False, applicable=True)),
        )
        self.assertTrue(result)

    def test_generic_conditional_explanation_remains_allowed(self):
        result, _ = verify(
            "A winding fault is one hypothetical explanation, but its presence in your relay is unestablished.",
            verdict(unit(kind="conditional_hypothesis")),
        )
        self.assertEqual(result, [])

    def test_conditional_test_is_not_an_observation(self):
        result, _ = verify(
            "If the relay is involved, comparing the same cycle with it disabled may help distinguish that hypothesis.",
            verdict(unit(kind="conditional_hypothesis")),
        )
        self.assertEqual(result, [])

    def test_hypotheses_without_a_new_mechanism_remain_allowed(self):
        result, _ = verify(
            "The relay remains plausible; the observation does not establish it as the cause.",
            verdict(unit()),
        )
        self.assertEqual(result, [])

    def test_actual_supplied_mechanism_can_support_explanation(self):
        current = "I measured an intermittent contact in the relay; could it explain the gauge jump?"
        result, _ = verify(
            "The intermittent contact you measured could explain the jump, though it is not proven to be the only cause.",
            verdict(unit(kind="supplied_mechanism", applicable=True,
                         witness={"turn_index": 1, "quote": "I measured an intermittent contact in the relay"})),
            current=current, history=[],
        )
        self.assertEqual(result, [])

    def test_prior_user_mechanism_is_available_on_the_followup(self):
        history = [{"role": "user", "content": "I measured an intermittent contact in the relay."}]
        result, _ = verify(
            "That intermittent contact could still explain it.",
            verdict(unit(kind="supplied_mechanism", applicable=True,
                         witness={"turn_index": 1, "quote": "I measured an intermittent contact in the relay."})),
            current="Could that still explain it?", history=history,
        )
        self.assertEqual(result, [])

    def test_assistant_explanation_cannot_supply_a_witness(self):
        result, _ = verify(
            "Your coil has a fractured winding.",
            verdict(unit(kind="supplied_mechanism", applicable=True,
                         witness={"turn_index": 1, "quote": "Your coil has a fractured winding."})),
        )
        self.assertTrue(result)

    def test_candidate_prose_cannot_supply_a_witness(self):
        draft = "Your bushing is damaged."
        result, _ = verify(
            draft, verdict(unit(kind="supplied_mechanism", applicable=True,
                                witness={"turn_index": 1, "quote": draft})),
        )
        self.assertTrue(result)

    def test_no_witness_cannot_establish_a_mechanism(self):
        result, _ = verify("The connector is oxidised.", verdict(unit(kind="supplied_mechanism", applicable=True)))
        self.assertTrue(result)

    def test_witness_must_be_exact_user_text(self):
        result, _ = verify(
            "Your relay has a fractured winding.",
            verdict(unit(kind="supplied_mechanism", applicable=True,
                         witness={"turn_index": 1, "quote": "My relay has a fractured winding."})),
        )
        self.assertTrue(result)

    def test_missing_mechanism_coverage_cannot_hide_under_global_success(self):
        result, _ = verify("That does not identify the mechanism.", {"faithful": True, "violations": []})
        self.assertTrue(result)

    def test_supported_sentence_does_not_rescue_unsupported_second_sentence(self):
        result, _ = verify(
            "The relay remains plausible. Its fractured winding explains the quiet-cycle pattern.",
            verdict(unit(1), unit(2, kind="unsupported_application", supported=False, applicable=True)),
        )
        self.assertTrue(result)

    def test_missing_second_sentence_assessment_fails_closed(self):
        result, _ = verify("The relay remains plausible. No mechanism is established.", verdict(unit()))
        self.assertTrue(result)

    def test_duplicate_sentence_indexes_fail_closed(self):
        result, _ = verify("The relay remains plausible. No mechanism is established.", verdict(unit(), unit()))
        self.assertTrue(result)

    def test_out_of_range_sentence_index_fails_closed(self):
        result, _ = verify("No mechanism is established.", verdict(unit(index=2)))
        self.assertTrue(result)

    def test_all_units_without_mechanisms_can_be_accepted(self):
        result, _ = verify("The relay remains plausible. No mechanism is established.", verdict(unit(), unit(2)))
        self.assertEqual(result, [])

    def test_complete_unit_order_is_not_authority(self):
        result, _ = verify("The relay remains plausible. No mechanism is established.", verdict(unit(2), unit(1)))
        self.assertEqual(result, [])

    def test_kind_must_be_an_allowlisted_string(self):
        for kind in ([], {}, "certain_from_training", None):
            with self.subTest(kind=kind):
                result, _ = verify("No mechanism is established.", verdict(unit(kind=kind)))
                self.assertTrue(result)

    def test_unit_booleans_are_strict(self):
        for field in ("supported", "applicability_established"):
            for value in ("true", 1, None):
                record = unit()
                record[field] = value
                with self.subTest(field=field, value=value):
                    result, _ = verify("No mechanism is established.", verdict(record))
                    self.assertTrue(result)

    def test_bool_does_not_count_as_sentence_or_user_turn_index(self):
        result, _ = verify("No mechanism is established.", verdict(unit(index=True)))
        self.assertTrue(result)
        result, _ = verify(
            "The contact could explain it.",
            verdict(unit(kind="supplied_mechanism", applicable=True,
                         witness={"turn_index": True, "quote": "My gauge"})),
        )
        self.assertTrue(result)

    def test_generic_condition_cannot_simultaneously_claim_established_applicability(self):
        result, _ = verify("That is only a hypothesis.", verdict(unit(kind="conditional_hypothesis", applicable=True)))
        self.assertTrue(result)

    def test_supplied_mechanism_cannot_claim_no_applicability(self):
        result, _ = verify(
            "That contact explains it.",
            verdict(unit(kind="supplied_mechanism", witness={"turn_index": 1, "quote": "My gauge"})),
        )
        self.assertTrue(result)

    def test_negative_unit_flag_rejects_even_if_kind_says_no_mechanism(self):
        result, _ = verify("No mechanism is established.", verdict(unit(supported=False)))
        self.assertTrue(result)

    def test_negative_inference_and_constraint_flags_still_override_all_positive_units(self):
        result, _ = verify("No mechanism is established.", verdict(unit(), inference_faithful=False, constraints_faithful=False))
        self.assertEqual(len(result), 2)

    def test_legacy_stable_world_answers_do_not_acquire_mechanism_schema(self):
        contract = replace(LIVE, authority="local_model_knowledge", epistemic_mode="stable_model_knowledge")
        result, client = verify("A gear transfers rotational motion.", {"faithful": True, "violations": []}, contract=contract)
        self.assertEqual(result, [])
        self.assertNotIn("REQUIRED MECHANISM COVERAGE", packet(client))
        self.assertEqual(client.calls[0]["options"]["num_predict"], 96)

    def test_no_other_lane_acquires_this_factual_validator(self):
        for intent in ("casual_conversation", "share_opinion", "recommend", "media_question", "consequential_advice"):
            with self.subTest(intent=intent):
                result, client = verify("A response.", {}, contract=replace(LIVE, intent=intent))
                self.assertEqual(result, [])
                self.assertEqual(client.calls, [])

    def test_actual_contract_is_rendered_and_inference_is_explicitly_in_scope(self):
        _, client = verify("No mechanism is established.", verdict(unit()))
        text = packet(client)
        self.assertIn('"authority": "live_user_task"', text)
        self.assertIn('"epistemic_mode": "user_context_reasoning"', text)
        self.assertIn("User-specific diagnostic inferences ARE inside", text)
        self.assertIn("consequent", text)
        self.assertIn("A symptom, model plausibility, topic overlap", text)

    def test_numbered_packet_contains_user_only_evidence_and_targets_are_not_evidence(self):
        _, client = verify("No mechanism is established.", verdict(unit()))
        text = packet(client)
        self.assertIn("classification targets, NEVER evidence", text)
        self.assertIn("My gauge jumps intermittently", text)
        self.assertNotIn("Your coil has a fractured winding.", text)

    def test_generation_frame_has_the_same_conditional_applicability_boundary(self):
        text = render_reasoning_trust_instruction(build_reasoning_trust_frame(CURRENT, HISTORY, LIVE))
        self.assertIn("if-clause alone does not authorize its consequent", text)
        self.assertIn("general hypothetical from actual applicability", text)


if __name__ == "__main__":
    unittest.main()
