"""Literal source-local purpose context is transport, never candidate authority.

Frozen neutral body packets reproduce omitted usage context and unrelated
neighbouring negative text. Existing global/scoped verifiers remain required.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from core.answer_candidate import CandidateOrigin
from research.public_explanation_targets import canonical_purpose_witness, explanation_target_obligations
from research.public_factual_grounding import build_failed_public_factual_fallback
from test_core_phase11_6_6j1_live2_public_identity_context import target_result, claim_result, packet
from test_core_phase11_6_6j1_live2_public_context_integration import assessment, subset_assessment
from test_core_phase11_6_6j1_public_purpose_integration import full, run, subset, completion
from test_core_phase11_6_6j_public_target_integration import TargetClient

USER = 'Why does protocol Orven need exchange Myra?'
USAGE = 'Protocol Orven uses exchange Myra.'
FUNCTION = 'Exchange Myra establishes shared state before transfer.'
PAIR = USAGE + ' ' + FUNCTION
ANSWER = 'Protocol Orven uses exchange Myra to establish shared state before transfer.'
DIRECT = 'Exchange Myra lets protocol Orven establish shared state before transfer.'
NEGATIVE = 'It does not transfer application records.'
MIXED = DIRECT + ' ' + NEGATIVE
ADVICE = 'Try inspecting the channel settings.'
UNSUPPORTED = 'The exchange permanently repairs the channel.'
TARGET = explanation_target_obligations(USER)[0]


def raw(candidate=ANSWER, quote=FUNCTION, body=PAIR, **changes):
    return assessment(candidate, body=body, current=USER, witness=quote,
                      mechanism='Protocol Orven' if candidate.startswith('Protocol') else 'protocol Orven',
                      requirement='exchange Myra' if candidate.startswith('Protocol') else 'Exchange Myra', **changes)


def failures(answer=ANSWER, quote=FUNCTION, body=PAIR, **changes):
    roles = {'mechanism_quote': 'Protocol Orven' if answer.startswith('Protocol') else 'protocol Orven',
             'effect_quote': 'exchange Myra' if answer.startswith('Protocol') else 'Exchange Myra'}
    roles.update(changes.pop('changes', {}))
    return (target_result(answer, quote, body=body, user=USER, changes=roles, **changes),
            claim_result(answer, quote, body=body, user=USER))


class LiteralPurposeWitnessTests(unittest.TestCase):
    def test_selected_function_retains_immediate_positive_usage(self):
        self.assertEqual(canonical_purpose_witness(TARGET, FUNCTION, PAIR), PAIR)
        self.assertEqual(failures(), ([], {}))

    def test_selected_pair_retains_its_literal_whitespace(self):
        body = USAGE + '\n\n' + FUNCTION
        self.assertEqual(canonical_purpose_witness(TARGET, FUNCTION, body), body)
        self.assertEqual(failures(body=body), ([], {}))

    def test_complete_purpose_unit_ignores_unrelated_negative_neighbour(self):
        self.assertEqual(canonical_purpose_witness(TARGET, MIXED, MIXED), DIRECT)
        self.assertEqual(failures(DIRECT, MIXED, MIXED), ([], {}))

    def test_unrelated_negative_before_complete_purpose(self):
        body = NEGATIVE + ' ' + DIRECT
        self.assertEqual(canonical_purpose_witness(TARGET, body, body), DIRECT)
        self.assertEqual(failures(DIRECT, body, body), ([], {}))

    def test_single_complete_quote_is_unchanged(self):
        self.assertEqual(canonical_purpose_witness(TARGET, DIRECT, MIXED), DIRECT)

    def test_body_without_usage_cannot_invent_beneficiary(self):
        self.assertTrue(failures(body=FUNCTION)[0])
        self.assertTrue(failures(body=FUNCTION)[1])

    def test_unrelated_previous_sentence_cannot_supply_usage(self):
        body = 'Protocol Orven is documented. ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_distant_usage_cannot_supply_context(self):
        body = USAGE + ' The archive is documented. ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_wrong_usage_beneficiary_is_not_imported(self):
        body = 'Protocol Velin uses exchange Myra. ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_wrong_usage_requirement_is_not_imported(self):
        body = 'Protocol Orven uses exchange Valen. ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_reversed_usage_roles_remain_rejected(self):
        body = 'Exchange Myra uses protocol Orven. ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_negative_usage_cannot_supply_positive_beneficiary(self):
        body = 'Protocol Orven does not use exchange Myra. ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_question_usage_cannot_supply_actual_beneficiary(self):
        body = 'Does protocol Orven use exchange Myra? ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_conditional_usage_cannot_supply_actual_beneficiary(self):
        body = 'If protocol Orven uses exchange Myra. ' + FUNCTION
        self.assertTrue(failures(body=body)[0])

    def test_negative_function_is_not_narrowed_into_positive(self):
        function = 'Exchange Myra does not establish shared state before transfer.'
        self.assertTrue(failures(quote=function, body=USAGE + ' ' + function)[0])

    def test_direct_negative_function_cannot_support_positive(self):
        body = 'Exchange Myra does not let protocol Orven establish shared state before transfer.'
        self.assertTrue(failures(DIRECT, body, body)[0])

    def test_negative_candidate_cannot_borrow_positive_source(self):
        answer = 'Protocol Orven does not use exchange Myra to establish shared state before transfer.'
        self.assertTrue(failures(answer)[0])

    def test_competing_positive_and_negative_purpose_is_not_cherry_picked(self):
        opposite = 'Exchange Myra does not let protocol Orven establish shared state before transfer.'
        body = DIRECT + ' ' + opposite
        self.assertEqual(canonical_purpose_witness(TARGET, body, body), body)
        self.assertTrue(failures(DIRECT, body, body)[1])

    def test_two_different_purpose_statements_are_not_silently_narrowed(self):
        body = DIRECT + ' Exchange Myra lets protocol Orven establish private state before transfer.'
        self.assertEqual(canonical_purpose_witness(TARGET, body, body), body)

    def test_missing_literal_quote_is_not_reconstructed(self):
        quote = 'Exchange Myra establishes state before transfer.'
        self.assertEqual(canonical_purpose_witness(TARGET, quote, PAIR), quote)
        self.assertTrue(failures(quote=quote)[0])

    def test_duplicate_function_occurrences_are_ambiguous(self):
        body = PAIR + ' ' + FUNCTION
        self.assertEqual(canonical_purpose_witness(TARGET, FUNCTION, body), FUNCTION)
        self.assertTrue(failures(body=body)[0])

    def test_other_source_usage_cannot_supply_context(self):
        evidence = packet(FUNCTION)
        extra = packet(USAGE)['sources'][0]
        extra['source_id'] = 'S2'
        evidence['sources'].append(extra)
        self.assertTrue(target_result(ANSWER, FUNCTION, body=FUNCTION, user=USER, evidence=evidence,
                                     changes={'mechanism_quote':'Protocol Orven'}))

    def test_rejected_body_has_no_context_authority(self):
        evidence = packet(PAIR, accepted_as_evidence=False)
        self.assertTrue(target_result(ANSWER, FUNCTION, user=USER, evidence=evidence,
                                     changes={'mechanism_quote':'Protocol Orven'}))

    def test_title_usage_cannot_supply_body_context(self):
        evidence = packet(FUNCTION, title=USAGE)
        self.assertTrue(target_result(ANSWER, FUNCTION, user=USER, evidence=evidence,
                                     changes={'mechanism_quote':'Protocol Orven'}))

    def test_false_typed_target_is_not_overridden(self):
        self.assertIn('explanation_target_unfulfilled', failures(changes={'relationship_answered':False})[0])

    def test_false_claim_assessment_is_not_overridden(self):
        value = raw()
        value['claim_assessments'][0]['supported'] = False
        result, _ = full(ANSWER, body=PAIR, current=USER, payload=value)
        self.assertTrue(result)

    def test_missing_target_assessment_still_fails_closed(self):
        value = raw()
        value.pop('explanation_target_assessments')
        result, _ = full(ANSWER, body=PAIR, current=USER, payload=value)
        self.assertTrue(result)

    def test_missing_claim_assessment_still_fails_closed(self):
        value = raw()
        value.pop('claim_assessments')
        result, _ = full(ANSWER, body=PAIR, current=USER, payload=value)
        self.assertTrue(result)

    def test_context_closure_does_not_mutate_evidence_or_typed_verdict(self):
        evidence, value = packet(PAIR), raw()
        before = copy.deepcopy((evidence, value))
        full(ANSWER, body=PAIR, state=evidence, current=USER, payload=value)
        self.assertEqual((evidence, value), before)

    def test_causal_relation_is_not_canonicalized_by_purpose_rule(self):
        target = explanation_target_obligations('Why does feature Orven cause symptom Myra?')[0]
        self.assertEqual(canonical_purpose_witness(target, DIRECT, MIXED), DIRECT)

    def test_non_purpose_neighbour_not_candidate_evidence(self):
        answer = 'Protocol Orven uses exchange Myra to permanently repair the channel.'
        self.assertTrue(failures(answer)[0])


class LiteralPurposeProductionTests(unittest.TestCase):
    def assert_published(self, result, answer, *withheld):
        self.assertEqual(result[0], answer)
        self.assertEqual(result[1][-1], {'role':'assistant','content':answer})
        self.assertEqual(result[2:], (None,None))
        for item in withheld:
            self.assertNotIn(item, [turn['content'] for turn in result[1]])

    def test_full_draft_literal_function_closure_publishes(self):
        client = TargetClient([ANSWER], [raw()])
        result, observed, _ = run(client, body=PAIR, current=USER)
        self.assert_published(result, ANSWER)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))
        self.assertEqual(observed[0]['origin'], CandidateOrigin.GENERATED)

    def test_full_draft_negative_nonfunction_neighbour_publishes(self):
        client = TargetClient([DIRECT], [raw(DIRECT,MIXED,MIXED)])
        result, _, _ = run(client, body=MIXED, current=USER)
        self.assert_published(result, DIRECT)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))

    def test_wrong_beneficiary_rejected_then_valid_retry_publishes(self):
        bad = 'Protocol Orven uses exchange Myra to permanently repair the channel.'
        client = TargetClient([bad,ANSWER], [raw(bad),raw()])
        result, _, _ = run(client, body=PAIR, current=USER)
        self.assert_published(result, ANSWER,bad)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))

    def test_supported_subset_closure_uses_existing_completion_once(self):
        draft = ANSWER + ' ' + UNSUPPORTED
        value = raw(draft, answer=ANSWER, statuses=[True,False])
        retained = subset_assessment(ANSWER,body=PAIR,current=USER,witness=FUNCTION,
                                     mechanism='Protocol Orven',requirement='exchange Myra')
        client = TargetClient([draft],[value],[retained])
        result, observed, _ = run(client,body=PAIR,current=USER)
        self.assert_published(result, ANSWER,draft)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,1))
        self.assertFalse(observed)

    def test_advice_only_subset_cannot_complete_requested_purpose(self):
        draft = UNSUPPORTED + ' ' + ADVICE
        body = PAIR + ' ' + ADVICE
        value = raw(draft,body=body,target_outcome='incomplete',statuses=[False,True])
        retained = completion(ADVICE,assessments=value['explanation_target_assessments'])
        client = TargetClient([draft,ANSWER],[value,raw(body=body)],[retained])
        result, _, _ = run(client,body=body,current=USER)
        self.assert_published(result, ANSWER,draft,ADVICE)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,1))

    def test_repeated_false_target_remains_bounded_fail_closed(self):
        value = raw(target_outcome='incomplete')
        client = TargetClient([ANSWER,ANSWER],[copy.deepcopy(value),copy.deepcopy(value)])
        result, observed, _ = run(client,body=PAIR,current=USER)
        self.assert_published(result,build_failed_public_factual_fallback(),ANSWER)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))
        self.assertFalse(observed)

    def test_shadow_rejection_still_cannot_change_valid_publication(self):
        client = TargetClient([ANSWER],[raw()])
        result, _, _ = run(client,body=PAIR,current=USER,observer=lambda **kwargs:{'status':'REJECTED'})
        self.assert_published(result,ANSWER)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))

    def test_materialized_verifier_literal_selection_stays_original(self):
        result, client = full(ANSWER,body=PAIR,current=USER,payload=raw())
        self.assertFalse(result)
        state = result.verification_state
        self.assertEqual(state['explanation_target_assessments'][0]['source_quote'],FUNCTION)
        self.assertEqual(state['claim_assessments'][0]['source_quote'],FUNCTION)
        self.assertEqual(len(client.calls),1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
