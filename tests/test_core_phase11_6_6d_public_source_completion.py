"""Neutral source-output contract checks; no live service or model calls."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.answer_contract_runtime import AnswerContractRuntime
from core.evidence import freeze_metadata
from research.public_source_completion import (
    complete_public_source_request, public_source_output_required,
    source_output_requirement,
)

URL = 'https://docs.vendor.example/products/export.html'
TEXT = 'Queued export is supported.'
CONTRACT = AnswerContractRuntime(intent='factual_question', epistemic_mode='public_source_verified', authority='public_web')


def context(**updates):
    source = dict(source_id='S1', read_success=True, accepted_as_evidence=True,
                  read_url=URL, discovered_url='http://docs.vendor.example/export',
                  authority_tier='primary_official', quality_eligible=True)
    source.update(updates)
    return dict(version=1, sources=[source], requirements={})


def complete(value=TEXT, current='Include the official source URL.', state=None, contract=CONTRACT):
    return complete_public_source_request(value, user_input=current,
                                         authority_context=context() if state is None else state,
                                         contract=contract)


class PublicSourceCompletionTests(unittest.TestCase):
    def test_explicit_url_request_attaches_actual_read_url(self):
        self.assertEqual(complete(), TEXT + '\n\nSource: ' + URL)

    def test_url_request_families(self):
        for current in ['Give me the actual source URL.', 'Could you show me the link?',
                        'Please cite the source.', 'Which source is that from?',
                        'I need the official URL.', 'URL please']:
            with self.subTest(current=current):
                self.assertTrue(public_source_output_required(current))
                self.assertIn(URL, complete(current=current))

    def test_ordinary_factual_request_is_byte_identical(self):
        self.assertEqual(complete(current='Is queued export supported?'), TEXT)

    def test_request_to_read_without_output_request_does_not_force_citation(self):
        self.assertEqual(complete(current='Check the official documentation for queued export.'), TEXT)

    def test_read_request_containing_url_does_not_force_citation(self):
        self.assertEqual(complete(current='Read ' + URL + ' and explain queued export.'), TEXT)

    def test_source_code_request_is_not_citation_request(self):
        self.assertFalse(public_source_output_required('Give me the source code for the exporter.'))

    def test_negated_source_output_is_not_request(self):
        for current in ["Don't include URLs.", 'No need to cite the source.', 'Without links please.']:
            self.assertFalse(public_source_output_required(current))

    def test_quoted_source_request_has_no_authority(self):
        self.assertFalse(public_source_output_required('"Give me the source URL."'))

    def test_conditional_source_request_has_no_fresh_obligation(self):
        self.assertFalse(public_source_output_required('If I ask later, give me the source URL.'))

    def test_reported_request_has_no_fresh_obligation(self):
        self.assertFalse(public_source_output_required('She asked give me the source URL.'))

    def test_existing_actual_url_remains_byte_identical(self):
        value = TEXT + '\nSource: ' + URL
        self.assertEqual(complete(value), value)

    def test_repeat_completion_is_idempotent(self):
        value = complete()
        self.assertEqual(complete(value), value)

    def test_actual_read_identity_is_used_after_retained_redirect(self):
        self.assertIn(URL, complete())
        self.assertNotIn('http://docs.vendor.example/export', complete())

    def test_scheme_and_path_equivalence_are_not_guessed(self):
        value = TEXT + '\nhttp://docs.vendor.example/products/export'
        result = complete(value)
        self.assertIn(URL, result)
        self.assertIn('http://docs.vendor.example/products/export', result)

    def test_discovered_but_unread_source_cannot_supply_url(self):
        result = complete(state=context(read_success=False, read_url=None))
        self.assertNotIn('http', result)
        self.assertIn('cannot verify', result)

    def test_read_without_retained_url_uses_truthful_limitation(self):
        result = complete(state=context(read_url=None))
        self.assertNotIn('http', result)
        self.assertIn('loaded official source URL', result)

    def test_rejected_read_cannot_supply_url(self):
        result = complete(state=context(accepted_as_evidence=False))
        self.assertNotIn('http', result)

    def test_official_requirement_not_satisfied_by_editorial_source(self):
        result = complete(state=context(authority_tier='independent_editorial'))
        self.assertNotIn(URL, result)
        self.assertIn('cannot verify', result)

    def test_official_label_in_source_title_is_not_authority(self):
        result = complete(state=context(authority_tier='unclassified', title='Official export guide'))
        self.assertNotIn(URL, result)

    def test_quality_veto_preserves_official_limitation(self):
        self.assertNotIn(URL, complete(state=context(quality_eligible=False)))

    def test_primary_institutional_source_satisfies_primary_request(self):
        self.assertIn(URL, complete(current='Give me the primary source URL.',
                                    state=context(authority_tier='primary_institutional')))

    def test_exact_requested_url_requires_actual_read_identity(self):
        requested = 'https://research.example/different'
        result = complete(current='Read ' + requested + ' and provide the actual source URL.')
        self.assertNotIn(URL, result)
        self.assertNotIn(requested, result)
        self.assertIn('cannot verify', result)

    def test_answer_prose_cannot_establish_read(self):
        value = 'I loaded the official page.'
        result = complete(value, state=context(read_url=None))
        self.assertNotIn(URL, result)
        self.assertIn('cannot verify', result)

    def test_invented_existing_url_is_not_silently_repaired(self):
        value = TEXT + '\nSource: https://invented.example/fact'
        self.assertIn('https://invented.example/fact', complete(value))

    def test_invalid_authority_snapshot_cannot_supply_url(self):
        self.assertNotIn(URL, complete(state={'version': 0, 'sources': context()['sources']}))

    def test_empty_generation_does_not_become_citation_only_answer(self):
        self.assertEqual(complete(''), '')

    def test_social_contract_remains_unchanged(self):
        social = AnswerContractRuntime(intent='share_context', epistemic_mode='user_provided', authority='user_turn')
        self.assertEqual(complete(contract=social), TEXT)

    def test_stable_model_contract_remains_unchanged(self):
        stable = AnswerContractRuntime(intent='factual_question', epistemic_mode='stable_model_knowledge', authority='local_model_knowledge')
        self.assertEqual(complete(contract=stable), TEXT)

    def test_immutable_snapshot_is_not_mutated(self):
        raw = context()
        original = copy.deepcopy(raw)
        self.assertIn(URL, complete(state=freeze_metadata(raw)))
        self.assertEqual(raw, original)

    def test_explicit_requirements_are_structured(self):
        result = source_output_requirement('Give me the actual official source URL.')
        self.assertTrue(result.required)
        self.assertTrue(result.official)
        self.assertFalse(result.primary)

    def test_multiple_admitted_reads_are_not_guessed_into_one_exclusive_source(self):
        state = context()
        second = dict(state['sources'][0], source_id='S2', read_url='https://research.example/export')
        state['sources'].append(second)
        result = complete(state=state)
        self.assertIn(URL, result)
        self.assertIn(second['read_url'], result)
        self.assertIn('Sources:', result)


if __name__ == '__main__':
    unittest.main()
