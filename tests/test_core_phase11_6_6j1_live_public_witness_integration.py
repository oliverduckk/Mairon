"""Core-selected literal references in the existing public verifier/producer.

Neutral fixed source packets; no network or live model. IDs select claims and
real source text, not truth. Every existing semantic/support check still runs.
"""
from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

from research.public_claim_obligations import build_public_claim_obligations, public_claim_failures
from research.public_explanation_targets import explanation_target_obligations, public_witness_catalog
from research.public_factual_grounding import _split_draft_sentences
from test_core_phase11_6_6c_public_content_authority import packet
from test_core_phase11_6_6j_public_target_integration import TargetClient
from test_core_phase11_6_6j1_public_purpose_integration import (
    USER, GOOD, ADVICE, UNSUPPORTED, BODY, BECAUSE,
    verification, completion, target, full, subset, run,
)


def references(text=GOOD, body=BODY, user=USER):
    catalog = public_witness_catalog(explanation_target_obligations(user),
                                     _split_draft_sentences(text), packet(body))
    choices = catalog['targets'][1]
    fields = {field: next(iter(values)) for field, values in choices.items()}
    fields['source_quote'] = next(ref for ref, entry in catalog['body'].items()
                                  if entry['literal'] == body.split(' Try ')[0].strip())
    return fields, catalog


def payload(text=GOOD, body=BODY, user=USER, statuses=None):
    fields, catalog = references(text, body, user)
    value = verification(text, current=user, statuses=statuses, assessments=target(text))
    value['explanation_target_assessments'][0].update(fields)
    obligations = build_public_claim_obligations(_split_draft_sentences(text),
                                                explanation_target_obligations(user), packet(body))
    value['claim_assessments'] = [dict(index=item['index'], supported=True,
                                     source_id='S1', source_quote=fields['source_quote'])
                                   for item in obligations]
    return value, catalog


class LiteralReferenceVerifierTests(unittest.TestCase):
    def test_reference_payload_materializes_actual_literal_witnesses(self):
        value, _ = payload()
        result, client = full(payload=value)
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, [GOOD])
        state = result.verification_state
        self.assertEqual(state['explanation_target_assessments'][0]['answer_quote'], GOOD)
        self.assertEqual(state['claim_assessments'][0]['source_quote'], GOOD)
        self.assertEqual(len(client.calls), 1)

    def test_schema_constrains_source_and_candidate_reference_values(self):
        value, _ = payload()
        _, client = full(payload=value)
        properties = client.calls[0]['format']['properties']
        claim = properties['claim_assessments']['items']['properties']['source_quote']
        target_schema = properties['explanation_target_assessments']['items']['properties']
        self.assertIn(value['claim_assessments'][0]['source_quote'], claim['enum'])
        for field in ('mechanism_quote', 'effect_quote', 'answer_quote'):
            self.assertIn(value['explanation_target_assessments'][0][field], target_schema[field]['enum'])
        self.assertEqual(len(client.calls), 1)

    def test_freehand_paraphrased_candidate_still_fails(self):
        value = verification(GOOD, assessments=target(GOOD, mechanism_quote='the Elun protocol'))
        result, _ = full(payload=value)
        self.assertTrue(any('invalid_explanation_candidate_witness' in item for item in result))

    def test_freehand_paraphrased_source_is_not_repaired(self):
        value = verification(GOOD, claim_quote=GOOD.replace('lets', 'enables'),
                             assessments=target(GOOD, source_quote=GOOD.replace('lets', 'enables')))
        result, _ = full(payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_wrong_source_reference_cannot_select_other_source(self):
        value, _ = payload()
        value['explanation_target_assessments'][0]['source_id'] = 'S9'
        value['claim_assessments'][0]['source_id'] = 'S9'
        result, _ = full(payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_unknown_reference_is_not_recovered_by_scanning(self):
        value, _ = payload()
        value['claim_assessments'][0]['source_quote'] = '@core-witness:b999:999'
        result, _ = full(payload=value)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_candidate_reference_cannot_be_a_source(self):
        value, _ = payload()
        value['claim_assessments'][0]['source_quote'] = value['explanation_target_assessments'][0]['answer_quote']
        result, _ = full(payload=value)
        self.assertTrue(result)

    def test_missing_claim_array_remains_fail_closed(self):
        value, _ = payload()
        value.pop('claim_assessments')
        result, _ = full(payload=value)
        self.assertTrue(result)

    def test_missing_target_array_remains_fail_closed(self):
        value, _ = payload()
        value.pop('explanation_target_assessments')
        result, _ = full(payload=value)
        self.assertTrue(result)

    def test_false_target_cannot_be_turned_true_by_literal_catalog(self):
        value, _ = payload()
        value['explanation_target_assessments'][0]['relationship_answered'] = False
        result, _ = full(payload=value)
        self.assertTrue(result)

    def test_negative_claim_cannot_be_turned_true_by_literal_catalog(self):
        value, _ = payload()
        value['claim_assessments'][0]['supported'] = False
        result, _ = full(payload=value)
        self.assertTrue(result)

    def test_selected_reversed_body_cannot_support_positive_direction(self):
        body = 'Protocol Elun lets exchange Varo establish shared state before normal transfer.'
        value, catalog = payload()
        # The ref is valid transport even though the source proposition has
        # reversed roles. It supplies no semantic or directional authority.
        actual = public_witness_catalog(explanation_target_obligations(USER), [GOOD], packet(body))
        ref = next(iter(actual['body']))
        value['claim_assessments'][0]['source_quote'] = ref
        value['explanation_target_assessments'][0]['source_quote'] = ref
        result, _ = full(payload=value, body=body)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_selected_negative_function_cannot_support_positive_function(self):
        body = 'Exchange Varo lets protocol Elun not establish shared state before normal transfer.'
        value, _ = payload()
        result, _ = full(payload=value, body=body)
        self.assertTrue(result)
        self.assertFalse(result.accepted_sentences)

    def test_benign_technical_determiner_no_longer_breaks_content_subject(self):
        current = 'Why does the Elun protocol need exchange Varo?'
        text = 'The Elun protocol uses exchange Varo to establish shared state before normal transfer.'
        body = text.removeprefix('The ')
        value, _ = payload(text, body, current)
        result, _ = full(text, current=current, body=body, payload=value)
        self.assertFalse(result, list(result))

    def test_extra_proper_subject_is_not_deleted_by_technical_role_bridge(self):
        text = 'Protocol Elun needs exchange Varo because Ruvan establishes shared state before normal transfer.'
        items = build_public_claim_obligations([text], explanation_target_obligations(USER), packet(GOOD))
        self.assertTrue(public_claim_failures(items,
            [dict(index=item['index'], supported=True, source_id='S1', source_quote=GOOD) for item in items], packet(GOOD)))

    def test_source_established_acronym_works_in_target_and_content_protocol(self):
        current = 'Why does ETP need exchange Varo?'
        body = 'Elun Transfer Protocol (ETP) uses exchange Varo to establish shared state before normal transfer.'
        text = 'Elun Transfer Protocol uses exchange Varo to establish shared state before normal transfer.'
        value, _ = payload(text, body, current)
        result, _ = full(text, body=body, current=current, payload=value)
        self.assertFalse(result, list(result))

    def test_request_full_name_can_use_source_established_acronym(self):
        current = 'Why does Elun Transfer Protocol need exchange Varo?'
        body = 'Elun Transfer Protocol (ETP) uses exchange Varo to establish shared state before normal transfer.'
        text = 'ETP uses exchange Varo to establish shared state before normal transfer.'
        value, _ = payload(text, body, current)
        result, _ = full(text, body=body, current=current, payload=value)
        self.assertFalse(result, list(result))

    def test_purpose_because_head_preserves_explicit_alias_direction(self):
        current = 'Why does ETP need exchange Varo?'
        body = 'Elun Transfer Protocol (ETP) uses exchange Varo to establish shared state before normal transfer.'
        text = 'Elun Transfer Protocol needs exchange Varo because it establishes shared state before normal transfer.'
        value, _ = payload(text, body, current)
        result, _ = full(text, body=body, current=current, payload=value)
        self.assertFalse(result, list(result))

    def test_nominal_order_preserves_same_bounded_technical_role(self):
        body = 'The Elun protocol uses exchange Varo to establish shared state before normal transfer.'
        text = 'Protocol Elun uses exchange Varo to establish shared state before normal transfer.'
        value, _ = payload(text, body)
        result, _ = full(text, body=body, payload=value)
        self.assertFalse(result, list(result))

    def test_relative_factual_tail_cannot_be_hidden_in_purpose_head(self):
        text = 'Protocol Elun that failed needs exchange Varo because it establishes shared state before normal transfer.'
        items = build_public_claim_obligations([text], explanation_target_obligations(USER), packet(GOOD))
        self.assertFalse(any(item.get('explanation_targets') for item in items))
        self.assertTrue(public_claim_failures(items,
            [dict(index=item['index'], supported=True, source_id='S1', source_quote=GOOD) for item in items], packet(GOOD)))

    def test_unestablished_acronym_does_not_grant_authority(self):
        current = 'Why does ETP need exchange Varo?'
        text = 'Elun Transfer Protocol uses exchange Varo to establish shared state before normal transfer.'
        value = verification(text, current=current, claim_quote=text, assessments=target(
            text, source_quote=text, mechanism_quote='Elun Transfer Protocol', effect_quote='exchange Varo'))
        result, _ = full(text, body=text, current=current, payload=value)
        self.assertTrue(result)

    def test_subset_reference_protocol_uses_existing_single_completion_call(self):
        fields, _ = references()
        value = completion(assessments=target(GOOD))
        value['explanation_target_assessments'][0].update(fields)
        result, client = subset(payload=value)
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)


class LiteralReferenceProductionTests(unittest.TestCase):
    def test_real_successful_reference_answer_publishes_unchanged(self):
        value, _ = payload()
        client = TargetClient([GOOD], [value])
        result, observed, _ = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(result[1][-1]['content'], GOOD)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))
        self.assertEqual(len(observed), 1)

    def test_rejected_freehand_copy_then_reference_retry_is_bounded(self):
        bad = verification(GOOD, assessments=target(GOOD, mechanism_quote='the Elun protocol'))
        good, _ = payload()
        client = TargetClient([GOOD, GOOD], [bad, good])
        result, _, _ = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertEqual(sum(item['role'] == 'assistant' for item in result[1]), 1)

    def test_supported_subset_references_are_rebuilt_from_surviving_text(self):
        text = GOOD + ' ' + UNSUPPORTED
        value, _ = payload(text, statuses=[True, False])
        fields, _ = references()
        retained = completion(assessments=target(GOOD))
        retained['explanation_target_assessments'][0].update(fields)
        client = TargetClient([text], [value], [retained])
        result, _, _ = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertNotIn(UNSUPPORTED, result[1][-1]['content'])
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))

    def test_global_positive_advice_only_still_cannot_complete_purpose(self):
        bad = verification(ADVICE, assessments=target(ADVICE,
            mechanism_quote='the system', effect_quote='the settings'))
        good, _ = payload()
        client = TargetClient([ADVICE, GOOD], [bad, good])
        result, _, _ = run(client)
        self.assertEqual(result[0], GOOD)
        self.assertEqual((client.generations, client.verifier_calls), (2, 2))

    def test_shadow_exception_does_not_replace_verified_reference_answer(self):
        value, _ = payload()
        client = TargetClient([GOOD], [value])
        def broken_observer(**kwargs):
            raise RuntimeError('synthetic observational failure')
        result, _, _ = run(client, observer=broken_observer)
        self.assertEqual(result[0], GOOD)
        self.assertEqual((client.generations, client.verifier_calls), (1, 1))


if __name__ == '__main__':
    unittest.main()
