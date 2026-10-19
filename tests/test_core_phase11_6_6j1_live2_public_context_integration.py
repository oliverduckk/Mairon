"""Source-local identity and immediate purpose context in the real public path.

All evidence is frozen invented readable text. Scripted typed results select
literal Core references; no test model, prior answer or candidate is evidence.
The existing producer, sentence salvage, completion and retry call budgets run.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_candidate import CandidateOrigin
from research.public_claim_obligations import build_public_claim_obligations
from research.public_explanation_targets import explanation_target_obligations, public_witness_catalog
from research.public_factual_grounding import _split_draft_sentences, build_failed_public_factual_fallback
from test_core_phase11_6_6c_public_content_authority import packet
from test_core_phase11_6_6j_public_target_integration import TargetClient
from test_core_phase11_6_6j1_public_purpose_integration import completion, full, run, subset

USER = "Why does ATP need exchange Belan?"
DEFINITION = "Arven Transfer Protocol (ATP) is documented."
FUNCTION = "Arven Transfer Protocol uses exchange Belan to establish shared state before transfer."
GOOD = "ATP uses exchange Belan to establish shared state before transfer."
BODY = DEFINITION + " " + FUNCTION
USAGE = "ATP uses exchange Belan."
PURPOSE = "Exchange Belan establishes shared state before transfer."
PAIR = USAGE + " " + PURPOSE
PAIR_BODY = DEFINITION + " " + PAIR
ADVICE = "Try inspecting the channel settings."
UNSUPPORTED = "The exchange permanently repairs the channel."


def _reference(choices, literal):
    """Choose actual literal values, never an assumed catalog ordinal."""
    return next(key for key, value in choices.items() if value == literal)


def assessment(candidate=GOOD, *, body=BODY, current=USER, witness=FUNCTION,
               answer=None, mechanism="ATP", requirement="exchange Belan",
               statuses=None, target_outcome="factual_explanation"):
    sentences = _split_draft_sentences(candidate)
    targets = explanation_target_obligations(current)
    state = packet(body)
    catalog = public_witness_catalog(targets, sentences, state)
    positive = [True] * len(sentences) if statuses is None else list(statuses)
    value = {"supported": all(positive),
             "unsupported_claims": [] if all(positive) else ["Unsupported detail"],
             "sentence_assessments": [dict(index=i, supported=flag)
                                      for i, flag in enumerate(positive, 1)]}
    body_ref = next(key for key, item in catalog["body"].items()
                    if item["source_id"] == "S1" and item["literal"] == witness)
    if target_outcome == "incomplete":
        target = dict(index=1, outcome="incomplete", mechanism_bound=False,
                      effect_bound=False, relationship_answered=False,
                      mechanism_quote=None, effect_quote=None, answer_quote=None,
                      source_id=None, source_quote=None)
    else:
        choices = catalog["targets"][1]
        target = dict(index=1, outcome=target_outcome, mechanism_bound=True,
                      effect_bound=True, relationship_answered=True,
                      mechanism_quote=_reference(choices["mechanism_quote"], mechanism),
                      effect_quote=_reference(choices["effect_quote"], requirement),
                      answer_quote=_reference(choices["answer_quote"], answer or candidate),
                      source_id="S1", source_quote=body_ref)
    value["explanation_target_assessments"] = [target]
    obligations = build_public_claim_obligations(sentences, targets, state)
    value["claim_assessments"] = [
        dict(index=item["index"], supported=positive[item["sentence_index"] - 1],
             source_id="S1" if positive[item["sentence_index"] - 1] else None,
             source_quote=body_ref if positive[item["sentence_index"] - 1] else None)
        for item in obligations]
    return value


def subset_assessment(candidate=GOOD, **kwargs):
    value = assessment(candidate, **kwargs)
    return completion(candidate, assessments=value["explanation_target_assessments"])


class PublicIdentityContextVerifierTests(unittest.TestCase):
    def assert_valid(self, candidate=GOOD, *, body=BODY, current=USER, **kwargs):
        value = assessment(candidate, body=body, current=current, **kwargs)
        result, client = full(candidate, body=body, current=current, payload=value)
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, _split_draft_sentences(candidate))
        self.assertEqual(len(client.calls), 1)
        return result, client

    def test_same_source_alias_definition_outside_selected_function_quote(self):
        result, _ = self.assert_valid()
        literal = result.verification_state["claim_assessments"][0]["source_quote"]
        self.assertEqual(literal, FUNCTION)
        self.assertNotIn(DEFINITION, literal)

    def test_full_name_request_accepts_source_defined_abbreviation(self):
        self.assert_valid(current="Why does Arven Transfer Protocol need exchange Belan?")

    def test_full_name_answer_accepts_source_defined_abbreviation_request(self):
        self.assert_valid(FUNCTION, mechanism="Arven Transfer Protocol")

    def test_discourse_prefix_is_not_a_new_proper_subject(self):
        self.assert_valid("First, " + GOOD)

    def test_supported_technical_nominal_refinement(self):
        body = DEFINITION + " Arven Transfer Protocol uses a three-step exchange Belan to establish shared state before transfer."
        text = "ATP needs a three-step exchange Belan because it establishes shared state before transfer."
        self.assert_valid(text, body=body,
                          witness=body.removeprefix(DEFINITION + " "))

    def test_adjacent_usage_and_function_are_one_bound_explanation(self):
        self.assert_valid(PAIR, body=PAIR_BODY, witness=PAIR, requirement="exchange Belan")

    def test_literal_pair_is_retained_in_both_independent_protocols(self):
        result, client = self.assert_valid(PAIR, body=PAIR_BODY, witness=PAIR)
        state = result.verification_state
        self.assertEqual(state["explanation_target_assessments"][0]["answer_quote"], PAIR)
        self.assertEqual(state["explanation_target_assessments"][0]["source_quote"], PAIR)
        self.assertTrue(state["claim_assessments"])
        self.assertTrue(all(item["source_quote"] == PAIR for item in state["claim_assessments"]))
        self.assertIn("claim_assessments", client.calls[0]["format"]["required"])
        self.assertIn("explanation_target_assessments", client.calls[0]["format"]["required"])

    def test_positive_global_cannot_erase_missing_target_assessment(self):
        value = assessment()
        value.pop("explanation_target_assessments")
        result, client = full(GOOD, body=BODY, current=USER, payload=value)
        self.assertTrue(result)
        self.assertTrue(any("explanation target" in item for item in result))
        self.assertEqual(len(client.calls), 1)

    def test_positive_global_cannot_erase_negative_relationship_assessment(self):
        value = assessment()
        value["explanation_target_assessments"][0]["relationship_answered"] = False
        result, _ = full(GOOD, body=BODY, current=USER, payload=value)
        self.assertTrue(result)

    def test_positive_target_cannot_erase_missing_claim_assessment(self):
        value = assessment()
        value.pop("claim_assessments")
        result, _ = full(GOOD, body=BODY, current=USER, payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_positive_target_cannot_erase_malformed_claim_boolean(self):
        value = assessment()
        value["claim_assessments"][0]["supported"] = "true"
        result, _ = full(GOOD, body=BODY, current=USER, payload=value)
        self.assertTrue(result)

    def test_selected_reversed_function_cannot_borrow_identity_definition(self):
        reverse = "ATP lets exchange Belan establish shared state before transfer."
        body = DEFINITION + " " + reverse
        value = assessment(body=body, witness=reverse)
        result, _ = full(GOOD, body=body, current=USER, payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_selected_negative_function_cannot_borrow_positive_candidate(self):
        negative = "ATP uses exchange Belan to not establish shared state before transfer."
        body = DEFINITION + " " + negative
        value = assessment(body=body, witness=negative)
        result, _ = full(GOOD, body=body, current=USER, payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_wrong_source_id_cannot_import_alias_or_literal_function(self):
        value = assessment()
        for item in value["claim_assessments"] + value["explanation_target_assessments"]:
            item["source_id"] = "S2"
        result, _ = full(GOOD, body=BODY, current=USER, payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_selected_pair_cannot_supply_deleted_candidate_usage(self):
        value = assessment(PURPOSE, body=PAIR_BODY, witness=PAIR,
                           target_outcome="incomplete")
        result, client = subset(PURPOSE, body=PAIR_BODY, current=USER,
                                payload=completion(PURPOSE, assessments=value["explanation_target_assessments"]))
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)


class PublicIdentityContextProductionTests(unittest.TestCase):
    def assert_published(self, result, expected, *withheld):
        self.assertEqual(result[0], expected)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": expected})
        self.assertEqual(result[2:], (None, None))
        for text in withheld:
            self.assertNotIn(text, [item["content"] for item in result[1]])

    def test_source_local_alias_success_publishes_unchanged(self):
        client = TargetClient([GOOD], [assessment()])
        result, observed, _ = run(client, body=BODY, current=USER)
        self.assert_published(result, GOOD)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(observed[0]["origin"], CandidateOrigin.GENERATED)

    def test_refined_head_succeeds_without_new_generation_or_verifier_call(self):
        body = DEFINITION + " Arven Transfer Protocol uses a three-step exchange Belan to establish shared state before transfer."
        text = "First, ATP needs a three-step exchange Belan because it establishes shared state before transfer."
        value = assessment(text, body=body, witness=body.removeprefix(DEFINITION + " "))
        client = TargetClient([text], [value])
        result, _, _ = run(client, body=body, current=USER)
        self.assert_published(result, text)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))

    def test_false_target_uses_one_existing_retry_then_publishes_good(self):
        bad = "Exchange Belan consists of three messages."
        body = BODY + " " + bad
        value = assessment(bad, body=body, target_outcome="incomplete")
        client = TargetClient([bad, GOOD], [value, assessment(body=body)])
        result, observed, _ = run(client, body=body, current=USER)
        self.assert_published(result, GOOD, bad)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(observed[0]["origin"], CandidateOrigin.RETRY)

    def test_missing_claims_rechecked_on_retry_without_history_leak(self):
        bad = "First, " + GOOD
        value = assessment(bad)
        value.pop("claim_assessments")
        client = TargetClient([bad, GOOD], [value, assessment()])
        result, _, _ = run(client, body=BODY, current=USER)
        self.assert_published(result, GOOD, bad)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))

    def test_adjacent_pair_supported_subset_salvages_in_existing_completion(self):
        draft = PAIR + " " + UNSUPPORTED
        value = assessment(draft, body=PAIR_BODY, witness=PAIR, answer=PAIR,
                           statuses=[True, True, False])
        retained = subset_assessment(PAIR, body=PAIR_BODY, witness=PAIR)
        client = TargetClient([draft], [value], [retained])
        result, observed, _ = run(client, body=PAIR_BODY, current=USER)
        self.assert_published(result, PAIR, draft)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))
        self.assertEqual(len(client.calls), 3)
        self.assertFalse(observed, "Existing sentence salvage remains outside generated-public shadow")

    def test_deleted_usage_subset_cannot_borrow_removed_antecedent(self):
        draft = PAIR
        value = assessment(draft, body=PAIR_BODY, witness=PAIR, statuses=[False, True])
        retained = subset_assessment(PURPOSE, body=PAIR_BODY, witness=PAIR,
                                     target_outcome="incomplete")
        client = TargetClient([draft, GOOD], [value, assessment(body=PAIR_BODY, witness=PAIR)], [retained])
        result, _, _ = run(client, body=PAIR_BODY, current=USER)
        self.assert_published(result, GOOD, draft, PURPOSE)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))

    def test_advice_only_subset_still_uses_bounded_retry(self):
        draft = UNSUPPORTED + " " + ADVICE
        body = BODY + " " + ADVICE
        value = assessment(draft, body=body, statuses=[False, True], target_outcome="incomplete")
        retained = subset_assessment(ADVICE, body=body, target_outcome="incomplete")
        client = TargetClient([draft, GOOD], [value, assessment(body=body)], [retained])
        result, _, _ = run(client, body=body, current=USER)
        self.assert_published(result, GOOD, draft, ADVICE)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 1))

    def test_repeated_incomplete_pair_does_not_expand_retry_budget(self):
        value = assessment(PURPOSE, body=PAIR_BODY, witness=PAIR, target_outcome="incomplete")
        client = TargetClient([PURPOSE, PURPOSE], [copy.deepcopy(value), copy.deepcopy(value)])
        result, observed, _ = run(client, body=PAIR_BODY, current=USER)
        self.assert_published(result, build_failed_public_factual_fallback(), PURPOSE)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertEqual(len(client.calls), 4)
        self.assertFalse(observed)

    def test_shadow_rejection_cannot_replace_valid_source_bound_answer(self):
        client = TargetClient([GOOD], [assessment()])
        result, _, _ = run(client, body=BODY, current=USER,
                           observer=lambda **kwargs: {"status": "REJECTED", "text": "not published"})
        self.assert_published(result, GOOD, "not published")
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))

    def test_assistant_history_cannot_supply_deleted_usage(self):
        value = assessment(PURPOSE, body=PAIR_BODY, witness=PAIR, target_outcome="incomplete")
        client = TargetClient([PURPOSE, GOOD], [value, assessment(body=PAIR_BODY, witness=PAIR)])
        result, _, _ = run(client, body=PAIR_BODY, current=USER,
                           history=[{"role": "assistant", "content": USAGE}])
        self.assert_published(result, GOOD, PURPOSE)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))


if __name__ == "__main__":
    unittest.main()
