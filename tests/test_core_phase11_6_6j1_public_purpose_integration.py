"""Neutral purpose explanations through the existing public verifier/producer.

Offline scripted assessments exercise the real verifier, packet, full provider,
retry and sentence-subset completion functions. No candidate is its own evidence,
and no additional model call, live service, tool or publication policy is used.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_candidate import CandidateOrigin
from research.public_claim_obligations import build_public_claim_obligations
from research.public_explanation_targets import explanation_target_obligations
from research.public_factual_grounding import (
    _split_draft_sentences, build_failed_public_factual_fallback,
    build_public_factual_generation_instruction, build_supported_current_lookup_fallback,
    requires_public_factual_salvage_completion, verify_public_factual_draft,
    verify_public_factual_salvage_completion,
)
from research.public_factual_research import actual_read_url, build_public_factual_authority_context
from test_core_milestone3b3a_public_shadow_integration import contract, provider, research
from test_core_phase11_6_6c_public_content_authority import Client, packet
from test_core_phase11_6_6j_public_target_integration import TargetClient

USER = "Why does protocol Elun need exchange Varo?"
GOOD = "Exchange Varo lets protocol Elun establish shared state before normal transfer."
BECAUSE = "Protocol Elun needs exchange Varo because it establishes shared state before normal transfer."
USES_TO = "Protocol Elun uses exchange Varo to establish shared state before normal transfer."
REQUIRED_SO = "Exchange Varo is required so that protocol Elun can establish shared state before normal transfer."
ADVICE = "Try inspecting the channel settings."
MENTION = "Protocol Elun uses exchange Varo."
MESSAGES = "Exchange Varo consists of three messages."
EXISTS = "Exchange Varo exists."
OTHER = "Exchange Varo lets component Nalo establish shared state before normal transfer."
REVERSED = "Protocol Elun lets exchange Varo establish shared state before normal transfer."
UNSUPPORTED = "Exchange Varo permanently repairs protocol Elun."
LIMITATION = "I cannot verify why protocol Elun needs exchange Varo from the available evidence."
BODY = GOOD + " " + ADVICE
MISSING = object()


def target(candidate=GOOD, *, source_quote=GOOD, outcome="factual_explanation",
           mechanism_quote="protocol Elun", effect_quote="Exchange Varo", answer_quote=None):
    if outcome == "incomplete":
        return [{"index": 1, "outcome": outcome, "mechanism_bound": False,
                 "effect_bound": False, "relationship_answered": False,
                 "mechanism_quote": None, "effect_quote": None, "answer_quote": None,
                 "source_id": None, "source_quote": None}]
    return [{"index": 1, "outcome": outcome, "mechanism_bound": True,
             "effect_bound": True, "relationship_answered": True,
             "mechanism_quote": mechanism_quote, "effect_quote": effect_quote,
             "answer_quote": candidate if answer_quote is None else answer_quote,
             "source_id": None if outcome == "bounded_limitation" else "S1",
             "source_quote": None if outcome == "bounded_limitation" else source_quote}]


def verification(candidate=GOOD, *, assessments=MISSING, statuses=None,
                 claim_quote=GOOD, claims=MISSING, current=USER):
    sentences = _split_draft_sentences(candidate)
    supported = [True] * len(sentences) if statuses is None else list(statuses)
    value = {"supported": all(supported),
             "unsupported_claims": [] if all(supported) else ["Unsupported detail"],
             "sentence_assessments": [{"index": index, "supported": status}
                                      for index, status in enumerate(supported, 1)]}
    obligations = build_public_claim_obligations(sentences, explanation_target_obligations(current))
    if claims is not MISSING:
        value["claim_assessments"] = copy.deepcopy(claims)
    elif obligations:
        value["claim_assessments"] = [
            {"index": item["index"], "supported": supported[item["sentence_index"] - 1],
             "source_id": "S1" if supported[item["sentence_index"] - 1] else None,
             "source_quote": claim_quote if supported[item["sentence_index"] - 1] else None}
            for item in obligations]
    if assessments is not MISSING:
        value["explanation_target_assessments"] = copy.deepcopy(assessments)
    return value


def completion(candidate=GOOD, *, assessments=MISSING, completed=True,
               outcome="factual_answer"):
    value = {"completed": completed, "outcome": outcome,
             "request_fulfilled": completed, "required_claim_assessments": [],
             "violations": [] if completed else ["incomplete_request"]}
    if assessments is not MISSING:
        value["explanation_target_assessments"] = copy.deepcopy(assessments)
    return value


def full(candidate=GOOD, *, payload=None, body=BODY, state=None, current=USER):
    client = Client(payload if payload is not None else verification(candidate, assessments=target(candidate)))
    result = verify_public_factual_draft(client, "replaceable-model", current, candidate,
                                        json.dumps(state if state is not None else packet(body)),
                                        core_answer_contract=contract())
    return result, client


def subset(candidate=GOOD, *, payload=None, body=BODY, state=None, current=USER):
    client = Client(payload if payload is not None else completion(candidate, assessments=target(candidate)))
    result = verify_public_factual_salvage_completion(
        client, "replaceable-model", current, candidate, contract(),
        json.dumps(state if state is not None else packet(body)))
    return result, client


def run(client, *, current=USER, body=BODY, observer=None, history=()):
    retained = copy.deepcopy(research())
    retained["query"] = retained["original_query"] = "protocol Elun exchange Varo purpose"
    retained["sources"][0]["title"] = "Protocol establishment technical guide"
    retained["sources"][0]["read_result"]["content"] = body
    fn, namespace = provider(retained=retained)
    observations = []
    namespace.update({
        "build_public_factual_authority_context": build_public_factual_authority_context,
        "build_public_factual_generation_instruction": build_public_factual_generation_instruction,
        "actual_read_url": actual_read_url,
        "verify_public_factual_draft": verify_public_factual_draft,
        "should_verify_public_factual_salvage_completion": requires_public_factual_salvage_completion,
        "verify_public_factual_salvage_completion": verify_public_factual_salvage_completion,
        "build_supported_current_lookup_fallback": build_supported_current_lookup_fallback,
        "build_failed_public_factual_fallback": build_failed_public_factual_fallback,
        "observe_public_factual_response": observer or (lambda **kwargs: observations.append(kwargs)),
    })
    log = io.StringIO()
    with redirect_stdout(log):
        result = fn(client, current, list(history), core_answer_contract=contract())
    return result, observations, log.getvalue()


class PurposeVerifierCompositionTests(unittest.TestCase):
    def assert_supported(self, candidate=GOOD, **kwargs):
        result, client = full(candidate, **kwargs)
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, _split_draft_sentences(candidate))
        self.assertEqual(len(client.calls), 1)
        return result, client

    def test_lets_purpose_does_not_require_literal_need(self):
        self.assert_supported()

    def test_need_because_candidate_accepts_literal_purpose_body(self):
        self.assert_supported(BECAUSE, payload=verification(BECAUSE, assessments=target(
            BECAUSE, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")))

    def test_uses_to_purpose_can_answer_necessity(self):
        self.assert_supported(USES_TO, payload=verification(USES_TO, assessments=target(
            USES_TO, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")))

    def test_required_so_that_can_answer_necessity(self):
        self.assert_supported(REQUIRED_SO)

    def test_passive_necessity_question_has_equivalent_supported_answer(self):
        self.assert_supported(current="Why is exchange Varo necessary for protocol Elun?")

    def test_component_require_question_accepts_source_backed_purpose(self):
        question = "Why does component Rulan require stage Sivan?"
        text = "Stage Sivan allows component Rulan to establish shared state before normal transfer."
        self.assert_supported(text, current=question, body=text,
                              payload=verification(text, current=question, claim_quote=text, assessments=target(text, source_quote=text,
                                  mechanism_quote="component Rulan", effect_quote="Stage Sivan")))

    def test_nested_purpose_cannot_waive_unrelated_outer_explanation(self):
        text = "The outage happened because exchange Varo lets protocol Elun establish shared state before normal transfer."
        result, client = full(text, payload=verification(text, assessments=target(
            text, effect_quote="exchange Varo")))
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)
        self.assertTrue(any("content obligation unsupported" in item for item in result))
        self.assertEqual(len(client.calls), 1)

    def test_positive_protocols_cannot_override_negated_source_function(self):
        body = "Exchange Varo allows protocol Elun to not establish shared state before normal transfer."
        result, client = full(GOOD, body=body, payload=verification(
            GOOD, claim_quote=body, assessments=target(GOOD, source_quote=body)))
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)
        self.assertEqual(len(client.calls), 1)

    def test_both_typed_protocols_are_required_in_same_existing_call(self):
        result, client = self.assert_supported(BECAUSE, payload=verification(BECAUSE, assessments=target(
            BECAUSE, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")))
        schema = client.calls[0]["format"]
        self.assertIn("claim_assessments", schema["required"])
        self.assertIn("explanation_target_assessments", schema["required"])
        self.assertTrue(result.verification_state["claim_assessments"])
        self.assertTrue(result.verification_state["explanation_target_assessments"])
        self.assertEqual(len(client.calls), 1)

    def test_composed_schema_cardinality_preserves_independent_protocols(self):
        _, client = self.assert_supported()
        properties = client.calls[0]["format"]["properties"]
        for name in ("claim_assessments", "explanation_target_assessments"):
            with self.subTest(name=name):
                self.assertEqual(properties[name]["minItems"], 1)
                self.assertEqual(properties[name]["maxItems"], 1)
                self.assertFalse(properties[name]["items"]["additionalProperties"])
        self.assertGreaterEqual(client.calls[0]["options"]["num_predict"], 320)
        self.assertLessEqual(client.calls[0]["options"]["num_predict"], 2400)

    def test_missing_claim_cannot_be_rescued_by_positive_target(self):
        value = verification(BECAUSE, assessments=target(BECAUSE,
            mechanism_quote="Protocol Elun", effect_quote="exchange Varo"))
        value.pop("claim_assessments")
        result, client = full(BECAUSE, payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)
        self.assertEqual(len(client.calls), 1)

    def test_empty_claims_cannot_be_rescued_by_positive_target(self):
        result, _ = full(BECAUSE, payload=verification(BECAUSE, claims=[], assessments=target(
            BECAUSE, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")))
        self.assertTrue(result)

    def test_wrong_claim_index_cannot_be_rescued_by_positive_target(self):
        result, _ = full(BECAUSE, payload=verification(BECAUSE, claims=[
            {"index": True, "supported": True, "source_id": "S1", "source_quote": GOOD}],
            assessments=target(BECAUSE, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")))
        self.assertTrue(result)

    def test_negative_claim_cannot_be_rescued_by_positive_target(self):
        result, _ = full(BECAUSE, payload=verification(BECAUSE, claims=[
            {"index": 1, "supported": False, "source_id": None, "source_quote": None}],
            assessments=target(BECAUSE, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")))
        self.assertTrue(result)

    def test_missing_target_cannot_be_rescued_by_positive_claims(self):
        result, _ = full(BECAUSE, payload=verification(BECAUSE))
        self.assertTrue(result)

    def test_malformed_target_cannot_be_rescued_by_positive_claims(self):
        value = target(BECAUSE, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")
        value[0]["relationship_answered"] = "true"
        result, _ = full(BECAUSE, payload=verification(BECAUSE, assessments=value))
        self.assertTrue(result)

    def test_negative_target_cannot_be_rescued_by_positive_claims(self):
        result, _ = full(BECAUSE, payload=verification(BECAUSE, assessments=target(outcome="incomplete")))
        self.assertTrue(result)

    def test_positive_flags_do_not_turn_use_only_into_purpose(self):
        result, _ = full(MENTION, payload=verification(MENTION, assessments=target(MENTION)))
        self.assertTrue(result)

    def test_message_count_does_not_answer_purpose(self):
        result, _ = full(MESSAGES, body=BODY + " " + MESSAGES,
                         payload=verification(MESSAGES, assessments=target(outcome="incomplete")))
        self.assertTrue(result)

    def test_topics_without_purpose_body_cannot_support_good_candidate(self):
        result, _ = full(body=MENTION)
        self.assertTrue(result)

    def test_reversed_body_purpose_cannot_support_correct_direction(self):
        result, _ = full(body=REVERSED,
                         payload=verification(GOOD, assessments=target(source_quote=REVERSED)))
        self.assertTrue(result)

    def test_reversed_candidate_cannot_borrow_correct_body(self):
        result, _ = full(REVERSED, payload=verification(REVERSED, assessments=target(
            REVERSED, mechanism_quote="Protocol Elun", effect_quote="exchange Varo")))
        self.assertTrue(result)

    def test_unread_body_cannot_prove_purpose(self):
        result, _ = full(state=packet(BODY, read_success=False))
        self.assertTrue(result)

    def test_title_identity_cannot_prove_purpose(self):
        result, _ = full(state=packet(MENTION, title=GOOD))
        self.assertTrue(result)

    def test_subset_equivalent_purpose_needs_one_existing_completion_call(self):
        result, client = subset()
        self.assertFalse(result, list(result))
        self.assertEqual(len(client.calls), 1)

    def test_subset_advice_only_still_incomplete(self):
        result, _ = subset(ADVICE, payload=completion(ADVICE, assessments=target(outcome="incomplete")))
        self.assertTrue(result)

    def test_subset_missing_target_fails_closed(self):
        result, _ = subset(payload=completion())
        self.assertTrue(result)

    def test_subset_reversed_body_cannot_complete(self):
        result, _ = subset(body=REVERSED, payload=completion(assessments=target(source_quote=REVERSED)))
        self.assertTrue(result)


class PublicPurposeProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for candidate in withheld:
            self.assertNotIn(candidate, [item["content"] for item in result[1]])

    def retry(self, bad, *, bad_assessment=MISSING, bad_verdict=None, body=BODY):
        verdict = verification(bad, assessments=bad_assessment) if bad_verdict is None else bad_verdict
        client = TargetClient([bad, GOOD], [verdict, verification(GOOD, assessments=target())])
        result, observations, log = run(client, body=body)
        self.assert_published(result, GOOD, bad)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["origin"], CandidateOrigin.RETRY)
        return client, log

    def test_supported_purpose_publishes_unchanged(self):
        client = TargetClient([GOOD], [verification(GOOD, assessments=target())])
        result, observations, _ = run(client)
        self.assert_published(result, GOOD)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))
        self.assertEqual(observations[0]["origin"], CandidateOrigin.GENERATED)

    def test_need_because_is_supported_by_real_purpose_packet(self):
        value = verification(BECAUSE, assessments=target(BECAUSE,
            mechanism_quote="Protocol Elun", effect_quote="exchange Varo"))
        client = TargetClient([BECAUSE], [value])
        result, _, _ = run(client)
        self.assert_published(result, BECAUSE)
        self.assertEqual(len(client.calls), 2)

    def test_purpose_and_optional_advice_publish_unchanged(self):
        candidate = GOOD + " " + ADVICE
        client = TargetClient([candidate], [verification(candidate, assessments=target(answer_quote=GOOD))])
        result, _, _ = run(client)
        self.assert_published(result, candidate)
        self.assertEqual(len(client.calls), 2)

    def test_necessity_for_question_preserves_successful_producer(self):
        client = TargetClient([GOOD], [verification(GOOD, assessments=target())])
        result, _, _ = run(client, current="Why is exchange Varo necessary for protocol Elun?")
        self.assert_published(result, GOOD)
        self.assertEqual(client.generations, 1)

    def test_use_only_does_not_publish_as_explanation(self):
        self.retry(MENTION, bad_assessment=target(outcome="incomplete"))

    def test_count_only_does_not_publish_as_explanation(self):
        self.retry(MESSAGES, bad_assessment=target(outcome="incomplete"), body=BODY + " " + MESSAGES)

    def test_existence_only_does_not_publish_as_explanation(self):
        self.retry(EXISTS, bad_assessment=target(outcome="incomplete"), body=BODY + " " + EXISTS)

    def test_advice_only_does_not_publish_as_explanation(self):
        self.retry(ADVICE, bad_assessment=target(outcome="incomplete"))

    def test_changed_subject_cannot_borrow_required_exchange(self):
        self.retry(OTHER, bad_assessment=target(OTHER, mechanism_quote="component Nalo"),
                   body=BODY + " " + OTHER)

    def test_global_positive_cannot_erase_missing_target_protocol(self):
        self.retry(MENTION)

    def test_positive_target_cannot_erase_missing_claim_protocol(self):
        value = verification(BECAUSE, assessments=target(BECAUSE,
            mechanism_quote="Protocol Elun", effect_quote="exchange Varo"))
        value.pop("claim_assessments")
        self.retry(BECAUSE, bad_verdict=value)

    def test_all_bounded_generation_attempts_recheck_target(self):
        client = TargetClient([MENTION, EXISTS], [
            verification(MENTION, assessments=target(outcome="incomplete")),
            verification(EXISTS, assessments=target(outcome="incomplete")),
        ])
        result, observations, _ = run(client)
        self.assert_published(result, build_failed_public_factual_fallback(), MENTION, EXISTS)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertEqual(len(client.calls), 4)
        self.assertFalse(observations)

    def test_supported_purpose_subset_salvages_without_generation_retry(self):
        draft = GOOD + " " + UNSUPPORTED
        client = TargetClient([draft], [verification(draft, assessments=target(), statuses=[True, False])],
                              [completion(GOOD, assessments=target())])
        result, observations, _ = run(client)
        self.assert_published(result, GOOD, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))
        self.assertFalse(observations, "Salvage remains outside generated-public shadow")

    def test_supported_purpose_and_advice_subset_salvage_together(self):
        good = GOOD + " " + ADVICE
        draft = good + " " + UNSUPPORTED
        client = TargetClient([draft], [verification(draft, assessments=target(), statuses=[True, True, False])],
                              [completion(good, assessments=target(answer_quote=GOOD))])
        result, _, _ = run(client)
        self.assert_published(result, good, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))

    def test_removed_explanation_cannot_leave_advice_as_answer(self):
        draft = UNSUPPORTED + " " + ADVICE
        client = TargetClient([draft, GOOD], [
            verification(draft, assessments=target(outcome="incomplete"), statuses=[False, True]),
            verification(GOOD, assessments=target()),
        ], [completion(ADVICE, assessments=target(outcome="incomplete"))])
        result, _, _ = run(client)
        self.assert_published(result, GOOD, draft, ADVICE)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))

    def test_use_only_subset_does_not_complete_necessity_question(self):
        draft = MENTION + " " + UNSUPPORTED
        client = TargetClient([draft, GOOD], [
            verification(draft, assessments=target(outcome="incomplete"), statuses=[True, False]),
            verification(GOOD, assessments=target()),
        ], [completion(MENTION, assessments=target(outcome="incomplete"))])
        result, _, _ = run(client)
        self.assert_published(result, GOOD, draft, MENTION)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))

    def test_missing_subset_assessment_uses_existing_retry(self):
        draft = GOOD + " " + UNSUPPORTED
        client = TargetClient([draft, GOOD], [
            verification(draft, assessments=target(), statuses=[True, False]),
            verification(GOOD, assessments=target()),
        ], [completion(GOOD)])
        result, _, _ = run(client)
        self.assert_published(result, GOOD, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))

    def test_subset_exception_uses_existing_retry_without_logging_payload(self):
        draft = GOOD + " " + UNSUPPORTED
        client = TargetClient([draft, GOOD], [
            verification(draft, assessments=target(), statuses=[True, False]),
            verification(GOOD, assessments=target()),
        ], [RuntimeError("Private source payload")])
        result, _, log = run(client)
        self.assert_published(result, GOOD, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))
        self.assertNotIn("Private source payload", log)

    def test_repeated_incomplete_subsets_do_not_add_retry_loop(self):
        draft = MENTION + " " + UNSUPPORTED
        value = verification(draft, assessments=target(outcome="incomplete"), statuses=[True, False])
        client = TargetClient([draft, draft], [value, value], [
            completion(MENTION, assessments=target(outcome="incomplete")),
            completion(MENTION, assessments=target(outcome="incomplete")),
        ])
        result, observations, _ = run(client)
        self.assert_published(result, build_failed_public_factual_fallback(), draft, MENTION)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 2))
        self.assertEqual(len(client.calls), 6)
        self.assertFalse(observations)

    def test_bounded_target_specific_limitation_remains_available(self):
        annotation = target(LIMITATION, outcome="bounded_limitation",
                            mechanism_quote="protocol Elun", effect_quote="exchange Varo")
        client = TargetClient([LIMITATION], [verification(LIMITATION, assessments=annotation)])
        result, _, _ = run(client)
        self.assert_published(result, LIMITATION)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))

    def test_shadow_rejection_cannot_replace_verified_purpose_answer(self):
        client = TargetClient([GOOD], [verification(GOOD, assessments=target())])
        result, _, _ = run(client, observer=lambda **kwargs: {
            "status": "REJECTED", "text": "Unpublished shadow replacement"})
        self.assert_published(result, GOOD, "Unpublished shadow replacement")

    def test_assistant_history_cannot_supply_ambiguous_current_reference(self):
        ambiguous = "It establishes that before normal transfer."
        client = TargetClient([ambiguous, GOOD], [
            verification(ambiguous, assessments=target(outcome="incomplete")),
            verification(GOOD, assessments=target()),
        ])
        result, _, _ = run(client, history=[{"role": "assistant", "content": GOOD}])
        self.assert_published(result, GOOD, ambiguous)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))


if __name__ == "__main__":
    unittest.main()
