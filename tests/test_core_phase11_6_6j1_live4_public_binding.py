"""Neutral purpose references and retained current-answer authority.

Frozen readable bodies exercise the actual target/content aggregators, full
verifier, existing subset completion and bounded producer. No live model or
research is used; candidate and assistant prose are never evidence.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from research.public_explanation_targets import (
    canonical_purpose_witness, explanation_target_diagnostics, explanation_target_obligations,
)
from research.public_factual_grounding import (
    _current_existence_answer_complete, _current_lookup_answer_integrity_indexes,
    _public_subset_authority_failures, build_failed_public_factual_fallback,
    verify_public_factual_salvage_completion,
)
from test_core_phase11_6_6j1_live3_public_context import failures
from test_core_phase11_6_6j1_live2_public_context_integration import assessment, subset_assessment
from test_core_phase11_6_6j1_live2_public_identity_context import packet, target_assessment
from test_core_phase11_6_6j1_public_purpose_integration import full, run, subset
from test_core_phase11_6_6j_public_target_integration import TargetClient
from test_core_phase11_6_6a_public_salvage_completion import Client, assessment as current_assessment, contract, PACKET
from test_core_phase11_6_6a_live_trust_integration import PublicClient, run_public, completion

USER = 'Why does protocol Orven need exchange Myra?'
USAGE = 'Protocol Orven uses exchange Myra.'
FUNCTION = 'This exchange establishes shared state before transfer.'
BODY = USAGE + ' ' + FUNCTION
GOOD = 'Protocol Orven uses exchange Myra to establish shared state before transfer.'
NOMINAL = 'Protocol Orven uses exchange Myra for shared state establishment before transfer.'
PREPOSED = 'For protocol Orven, exchange Myra establishes shared state before transfer.'
DIRECT = 'Exchange Myra allows protocol Orven to establish shared state before transfer.'
ADVICE = 'Try inspecting the channel settings.'
UNSUPPORTED = 'The exchange permanently repairs the channel.'
CURRENT_USER = 'Is the Morrow service accepting registrations today?'
CURRENT_GOOD = 'The Morrow service is accepting registrations today.'
CURRENT_SIDE = 'If you use archived clients, try the migration guide.'


def payload(candidate=GOOD, body=BODY, witness=FUNCTION, **changes):
    return assessment(candidate, body=body, current=USER, witness=witness,
                      mechanism='Protocol Orven', requirement='exchange Myra', **changes)


def authority(*, current=False, **changes):
    value = {
        'version': 1, 'freshness_required': True, 'requirements': {},
        'sources': [{'source_id': 'S1', 'title': 'Service notices',
                     'read_success': True, 'accepted_as_evidence': True,
                     'read_url': 'https://docs.vendor.example/notices',
                     'currentness_established': current}],
    }
    value.update(changes)
    return value


class SameSourcePurposeReferenceTests(unittest.TestCase):
    def test_demonstrative_function_keeps_immediate_literal_usage(self):
        target = explanation_target_obligations(USER)[0]
        self.assertEqual(canonical_purpose_witness(target, FUNCTION, BODY), BODY)
        self.assertEqual(failures(quote=FUNCTION, body=BODY), ([], {}))

    def test_same_context_is_shared_by_full_target_and_content_validation(self):
        result, client = full(GOOD, body=BODY, current=USER, payload=payload())
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, [GOOD])
        self.assertEqual(len(client.calls), 1)

    def test_explicit_preposed_beneficiary_is_directional(self):
        self.assertEqual(failures(quote=PREPOSED, body=PREPOSED), ([], {}))

    def test_nominalized_function_keeps_same_lexical_root(self):
        self.assertEqual(failures(NOMINAL, DIRECT, DIRECT), ([], {}))

    def test_different_nominalized_function_is_not_a_synonym_bridge(self):
        candidate = NOMINAL.replace('establishment', 'destruction')
        self.assertTrue(failures(candidate, DIRECT, DIRECT)[0])

    def test_direct_function_source_can_use_nominalized_candidate(self):
        result, client = full(NOMINAL, body=DIRECT, current=USER,
                              payload=payload(NOMINAL, DIRECT, DIRECT))
        self.assertFalse(result, list(result))
        self.assertEqual(len(client.calls), 1)

    def test_function_hyphen_is_not_a_different_role_or_function(self):
        answer = NOMINAL.replace('shared state', 'shared-state')
        self.assertEqual(failures(answer, DIRECT, DIRECT), ([], {}))

    def test_candidate_demonstrative_uses_only_surviving_adjacent_usage(self):
        pair = USAGE + ' ' + FUNCTION
        value = payload(pair, answer=pair)
        result, client = full(pair, body=BODY, current=USER, payload=value)
        self.assertFalse(result, list(result))
        self.assertEqual(result.accepted_sentences, [USAGE, FUNCTION])
        self.assertEqual(len(client.calls), 1)

    def test_missing_usage_cannot_invent_beneficiary(self):
        self.assertTrue(failures(quote=FUNCTION, body=FUNCTION)[0])

    def test_distant_usage_is_not_context(self):
        body = USAGE + ' The archive is indexed. ' + FUNCTION
        self.assertTrue(failures(quote=FUNCTION, body=body)[0])

    def test_unrelated_immediate_subject_cannot_be_borrowed(self):
        body = 'Protocol Velin uses exchange Myra. ' + FUNCTION
        self.assertTrue(failures(quote=FUNCTION, body=body)[0])

    def test_other_requirement_cannot_be_borrowed(self):
        body = 'Protocol Orven uses exchange Valen. ' + FUNCTION
        self.assertTrue(failures(quote=FUNCTION, body=body)[0])

    def test_reversed_usage_cannot_supply_requested_roles(self):
        body = 'Exchange Myra uses protocol Orven. ' + FUNCTION
        self.assertTrue(failures(quote=FUNCTION, body=body)[0])

    def test_negative_usage_cannot_establish_positive_purpose(self):
        body = 'Protocol Orven does not use exchange Myra. ' + FUNCTION
        self.assertTrue(failures(quote=FUNCTION, body=body)[0])

    def test_conditional_usage_cannot_establish_actual_beneficiary(self):
        body = 'If protocol Orven uses exchange Myra. ' + FUNCTION
        self.assertTrue(failures(quote=FUNCTION, body=body)[0])

    def test_ambiguous_bare_pronoun_is_not_demonstrative_identity(self):
        quote = 'It establishes shared state before transfer.'
        self.assertTrue(failures(quote=quote, body=USAGE + ' ' + quote)[0])

    def test_different_nominal_reference_does_not_guess_synonym(self):
        quote = FUNCTION.replace('exchange', 'procedure')
        self.assertTrue(failures(quote=quote, body=USAGE + ' ' + quote)[0])

    def test_two_possible_requirement_antecedents_are_not_resolved(self):
        usage = 'Protocol Orven uses exchange Myra and exchange Valen.'
        self.assertTrue(failures(quote=FUNCTION, body=usage + ' ' + FUNCTION)[0])

    def test_cross_source_usage_is_not_a_context_bridge(self):
        evidence = packet(FUNCTION)
        source = packet(USAGE)['sources'][0]
        source['source_id'] = 'S2'
        evidence['sources'].append(source)
        self.assertTrue(failures(quote=FUNCTION, body=FUNCTION, evidence=evidence)[0])

    def test_preposed_other_beneficiary_remains_rejected(self):
        body = PREPOSED.replace('Orven', 'Velin')
        self.assertTrue(failures(quote=body, body=body)[0])

    def test_preposed_negative_function_cannot_prove_positive(self):
        body = PREPOSED.replace('establishes', 'does not establish')
        self.assertTrue(failures(quote=body, body=body)[0])

    def test_false_typed_assessment_is_still_false(self):
        self.assertIn('explanation_target_unfulfilled',
                      failures(quote=FUNCTION, body=BODY,
                               changes={'relationship_answered': False})[0])

    def test_missing_typed_assessment_stays_fail_closed(self):
        value = payload()
        value.pop('explanation_target_assessments')
        result, client = full(GOOD, body=BODY, current=USER, payload=value)
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)

    def test_missing_content_assessment_stays_fail_closed(self):
        value = payload()
        value.pop('claim_assessments')
        result, _ = full(GOOD, body=BODY, current=USER, payload=value)
        self.assertTrue(result)

    def test_actual_subset_retains_same_nominal_context(self):
        value = subset_assessment(GOOD, body=BODY, current=USER, witness=FUNCTION,
                                  mechanism='Protocol Orven', requirement='exchange Myra')
        result, client = subset(GOOD, body=BODY, current=USER, payload=value)
        self.assertFalse(result)
        self.assertEqual(len(client.calls), 1)

    def test_real_producer_publishes_supported_nominal_reference_unchanged(self):
        client = TargetClient([GOOD], [payload()])
        result, observed, _ = run(client, current=USER, body=BODY)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(result[1][-1]['content'], GOOD)
        self.assertEqual(client.generations, 1)
        self.assertEqual(client.verifier_calls, 1)
        self.assertEqual(client.completion_calls, 0)
        self.assertEqual(len(observed), 1)

    def test_retry_rechecks_false_target_then_accepts_supported_target(self):
        bad = payload()
        bad['explanation_target_assessments'][0]['relationship_answered'] = False
        client = TargetClient([GOOD, GOOD], [bad, payload()])
        result, _, _ = run(client, current=USER, body=BODY)
        self.assertEqual(result[0], GOOD)
        self.assertEqual(client.generations, 2)
        self.assertEqual(client.verifier_calls, 2)

    def test_real_sentence_salvage_uses_same_literal_reference_context(self):
        draft = GOOD + ' ' + UNSUPPORTED
        value = payload(draft, answer=GOOD, statuses=[True, False])
        retained = subset_assessment(GOOD, body=BODY, current=USER, witness=FUNCTION,
                                      mechanism='Protocol Orven', requirement='exchange Myra')
        client = TargetClient([draft], [value], [retained])
        result, observations, _ = run(client, current=USER, body=BODY)
        self.assertEqual(result[0], GOOD)
        self.assertNotIn(draft, [item['content'] for item in result[1]])
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 1))
        self.assertFalse(observations)

    def test_repeated_false_target_is_not_repaired_by_source_context(self):
        value = payload()
        value['explanation_target_assessments'][0]['relationship_answered'] = False
        client = TargetClient([GOOD, GOOD], [copy.deepcopy(value), copy.deepcopy(value)])
        result, observed, _ = run(client, current=USER, body=BODY)
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (2, 2, 0))
        self.assertFalse(observed)

    def test_shadow_rejection_cannot_replace_supported_public_answer(self):
        client = TargetClient([GOOD], [payload()])
        result, _, _ = run(client, current=USER, body=BODY, observer=lambda **kwargs: {'status': 'REJECTED'})
        self.assertEqual(result[0], GOOD)
        self.assertEqual((client.generations, client.verifier_calls, client.completion_calls), (1, 1, 0))


class CurrentSubsetAuthorityTests(unittest.TestCase):
    def check(self, draft=CURRENT_SIDE, *, snapshot=None, outcome='factual_answer', current=CURRENT_USER):
        client = Client(current_assessment(outcome=outcome))
        result = verify_public_factual_salvage_completion(
            client, 'fixed-model', current, draft, contract(), PACKET,
            authority_context=snapshot)
        self.assertEqual(len(client.calls), 1, 'Uses the existing completion call only')
        return result

    def test_global_positive_cannot_make_conditional_advice_current_answer(self):
        self.assertTrue(self.check())

    def test_current_source_does_not_make_advice_answer_request(self):
        self.assertTrue(self.check(snapshot=authority(current=True)))

    def test_current_source_and_positive_global_cannot_make_side_fact_complete(self):
        self.assertTrue(self.check('The Orven module supports archived clients.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_matching_topic_alone_does_not_answer_current_existence(self):
        self.assertTrue(self.check('The Orven module improves compatibility.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_other_subject_availability_does_not_answer_current_target(self):
        self.assertTrue(self.check('A new Velin module is available now.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_other_clause_cannot_supply_target_for_unrelated_availability(self):
        self.assertTrue(self.check('A new Belan adapter is available; the Orven module supports archived clients.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_other_existential_object_cannot_borrow_a_following_target_clause(self):
        self.assertTrue(self.check('There is a new Belan adapter and the Orven module supports archived clients.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_current_target_with_availability_predicate_can_pass(self):
        self.assertEqual(self.check('A new Orven module is available now.',
                                    snapshot=authority(current=True),
                                    current='Is there a new Orven module right now?'), [])

    def test_fixed_historical_release_does_not_establish_new_current_item(self):
        self.assertTrue(self.check('The Orven module was released ten years ago.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_old_item_availability_does_not_establish_new_item(self):
        self.assertTrue(self.check('The old Orven module is available for archived clients.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_available_for_new_clients_is_not_a_new_item(self):
        self.assertTrue(self.check('The old Orven module is available for new clients.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_recent_release_event_answers_current_new_item(self):
        self.assertEqual(self.check('The Orven module was released today.',
                                    snapshot=authority(current=True),
                                    current='Is there a new Orven module right now?'), [])

    def test_current_target_with_changed_nominal_order_can_pass(self):
        self.assertEqual(self.check('The Orven module has a new release available now.',
                                    snapshot=authority(current=True),
                                    current='Is there a new release of the Orven module right now?'), [])

    def test_single_current_request_has_a_bounded_reference_answer(self):
        self.assertEqual(self.check('A new one is available now.',
                                    snapshot=authority(current=True),
                                    current='Is there a new Orven module right now?'), [])

    def test_direct_binary_answer_does_not_need_literal_user_nouns(self):
        self.assertEqual(self.check('No.', snapshot=authority(current=True),
                                    current='Is there a new Orven module right now?'), [])

    def test_direct_existential_new_item_answer_can_pass(self):
        self.assertEqual(self.check('There is a new Orven module available now.',
                                    snapshot=authority(current=True),
                                    current='Is there a new Orven module right now?'), [])

    def test_direct_existential_no_new_item_answer_can_pass(self):
        self.assertEqual(self.check('There is no new Orven module available now.',
                                    snapshot=authority(current=True),
                                    current='Is there a new Orven module right now?'), [])

    def test_conflicting_retained_antecedent_cannot_reuse_user_request_reference(self):
        self.assertTrue(self.check('The Belan adapter is compatible. Yes, it is available.',
                                  snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_first_answer_can_use_unambiguous_direct_reference(self):
        self.assertEqual(self.check('Yes, it is available now.', snapshot=authority(current=True),
                                    current='Is there a new Orven module right now?'), [])

    def test_explicit_unrelated_limitation_cannot_answer_current_target(self):
        for outcome in ('factual_answer', 'bounded_limitation'):
            with self.subTest(outcome=outcome):
                self.assertTrue(self.check('I cannot verify the price.', snapshot=authority(current=True),
                                          current='Is there a new Orven module right now?', outcome=outcome))

    def test_targeted_current_existence_limitation_is_allowed(self):
        self.assertEqual(self.check('I cannot verify whether a new Orven module is available.',
                                    snapshot=authority(), outcome='bounded_limitation',
                                    current='Is there a new Orven module right now?'), [])

    def test_generic_context_bound_limitation_is_allowed(self):
        self.assertEqual(self.check('I cannot verify that cleanly.', snapshot=authority(),
                                    outcome='bounded_limitation',
                                    current='Is there a new Orven module right now?'), [])

    def test_unanchored_demonstrative_does_not_guess_current_identity(self):
        self.assertTrue(self.check('That is available now.', snapshot=authority(current=True),
                                  current='Is there a new Orven module right now?'))

    def test_the_full_path_uses_same_current_target_integrity_check(self):
        state = packet('The Orven module supports archived clients.')
        flagged = _current_lookup_answer_integrity_indexes(state, 'Is there a new Orven module right now?',
                                                           ['The Orven module supports archived clients.'])
        self.assertEqual(flagged, {1})

    def test_explicit_source_alias_can_bind_a_current_target(self):
        state = packet('Orven module is also called Maven unit. A new Maven unit is available today.')
        self.assertTrue(_current_existence_answer_complete(state, 'Is there a new Orven module right now?',
                                                          ['A new Maven unit is available today.']))

    def test_limitation_label_cannot_hide_conditional_advice(self):
        self.assertTrue(self.check(snapshot=authority(current=True), outcome='bounded_limitation'))

    def test_limitation_label_cannot_hide_appended_factual_tail(self):
        draft = 'I cannot verify the registration state. The service accepts registrations today.'
        self.assertTrue(self.check(draft, snapshot=authority(current=True), outcome='bounded_limitation'))

    def test_natural_current_state_limitation_remains_available(self):
        draft = "I can't verify whether registrations are open right now from the available notices."
        self.assertEqual(self.check(draft, snapshot=authority(), outcome='bounded_limitation'), [])

    def test_current_predicate_with_verified_current_authority_passes(self):
        self.assertEqual(self.check(CURRENT_GOOD, snapshot=authority(current=True)), [])

    def test_current_claim_cannot_bypass_retained_currentness_failure(self):
        self.assertTrue(self.check(CURRENT_GOOD, snapshot=authority()))

    def test_report_of_historical_side_fact_is_not_current_authority(self):
        self.assertTrue(self.check('The source reports archived client compatibility.', snapshot=authority()))

    def test_bounded_limitation_does_not_need_invented_currentness(self):
        self.assertEqual(self.check(build_failed_public_factual_fallback(), snapshot=authority(),
                                    outcome='bounded_limitation'), [])

    def test_wrong_url_source_property_is_rechecked_after_deletion(self):
        draft = CURRENT_GOOD + ' Source: https://invented.example/notice'
        self.assertTrue(self.check(draft, snapshot=authority(current=True)))

    def test_requested_official_source_is_not_erased_by_subset(self):
        snapshot = authority(current=True, requirements={'official_source_required': True})
        self.assertTrue(self.check(CURRENT_GOOD, snapshot=snapshot))

    def test_requested_exact_source_read_is_not_erased_by_subset(self):
        snapshot = authority(current=True, requirements={'requested_source_urls': ['https://other.example/source']})
        self.assertTrue(self.check(CURRENT_GOOD, snapshot=snapshot))

    def test_current_as_of_must_match_retained_requirement(self):
        snapshot = authority(current=True, required_current_as_of='2032-04-05')
        snapshot['sources'][0]['current_as_of'] = '2031-04-05'
        self.assertTrue(self.check(CURRENT_GOOD, snapshot=snapshot))

    def test_matching_current_as_of_can_pass(self):
        snapshot = authority(current=True, required_current_as_of='2032-04-05')
        snapshot['sources'][0]['current_as_of'] = '2032-04-05'
        self.assertEqual(self.check(CURRENT_GOOD, snapshot=snapshot), [])

    def test_noncurrent_evergreen_completion_keeps_previous_scope(self):
        self.assertEqual(_public_subset_authority_failures([ADVICE], None, False, 'factual_answer'), [])

    def test_real_producer_does_not_publish_side_advice_after_current_rejection(self):
        draft = 'The service accepts queued export currently. ' + CURRENT_SIDE
        client = PublicClient([draft, draft], [[False, True], [False, True]],
                              [completion(True, 'factual_answer'), completion(True, 'factual_answer')])
        result, observations, log = run_public(client)
        self.assertNotEqual(result[0], CURRENT_SIDE)
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(client.generations, 2)
        self.assertEqual(client.completion_calls, 2)
        self.assertFalse(observations, 'Salvage remains outside generated-public common shadow')
        self.assertNotIn(CURRENT_SIDE, [item['content'] for item in result[1]])
        self.assertIn('Supported public sentence subset did not fulfill', log)


class SafeBindingDiagnosticTests(unittest.TestCase):
    def records(self, raw=None, body=BODY):
        raw = raw if raw is not None else target_assessment(
            GOOD, FUNCTION, mechanism_quote='Protocol Orven', effect_quote='exchange Myra')
        return explanation_target_diagnostics(explanation_target_obligations(USER), raw, [GOOD], packet(body))

    def test_records_only_bounded_types_and_structural_booleans(self):
        records = self.records()
        encoded = json.dumps(records)
        for secret in (GOOD, FUNCTION, BODY, 'Orven', 'Myra', 'https://'):
            self.assertNotIn(secret, encoded)
        self.assertEqual(records[0]['canonical_context'], 'expanded')
        self.assertFalse(records[0]['source_subject_raw'])
        self.assertTrue(records[0]['source_subject_canonical'])

    def test_raw_false_relationship_is_retained(self):
        raw = target_assessment(GOOD, FUNCTION, mechanism_quote='Protocol Orven', effect_quote='exchange Myra',
                                relationship_answered=False)
        self.assertFalse(self.records(raw)[0]['relationship_answered'])

    def test_missing_assessment_is_bounded_not_exception_text(self):
        value = self.records([])[0]
        self.assertEqual(value['assessment_outcome'], 'invalid')
        self.assertFalse(value['source_literal_valid'])

    def test_request_local_records_do_not_mutate_or_cross_contaminate(self):
        before = self.records()
        other = self.records(body=FUNCTION)
        self.assertEqual(before, self.records())
        self.assertNotEqual(before, other)

    def test_debug_off_by_default_and_opt_in_has_no_raw_text(self):
        bad = payload()
        bad['explanation_target_assessments'][0]['relationship_answered'] = False
        with patch.dict(os.environ, {'MAIRON_DEBUG_PUBLIC_BINDING': '1', 'MAIRON_DEBUG_GENERATION': '0'}):
            output = io.StringIO()
            with redirect_stdout(output):
                result, client = full(GOOD, body=BODY, current=USER, payload=bad)
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)
        diagnostic = '\n'.join(line for line in output.getvalue().splitlines() if 'Explanation target diagnostic:' in line)
        self.assertTrue(diagnostic)
        for forbidden in (GOOD, BODY, 'Orven', 'Myra', 'https://'):
            self.assertNotIn(forbidden, diagnostic)

    def test_no_structural_log_without_dedicated_opt_in(self):
        bad = payload()
        bad['explanation_target_assessments'][0]['relationship_answered'] = False
        with patch.dict(os.environ, {'MAIRON_DEBUG_PUBLIC_BINDING': '0', 'MAIRON_DEBUG_GENERATION': '0'}):
            output = io.StringIO()
            with redirect_stdout(output):
                result, _ = full(GOOD, body=BODY, current=USER, payload=bad)
        self.assertTrue(result)
        self.assertNotIn('Explanation target diagnostic:', output.getvalue())

    def test_diagnostic_sink_failure_cannot_change_verification(self):
        bad = payload()
        bad['explanation_target_assessments'][0]['relationship_answered'] = False
        with patch.dict(os.environ, {'MAIRON_DEBUG_PUBLIC_BINDING': '1'}), patch(
                'builtins.print', side_effect=RuntimeError('must never escape')):
            result, client = full(GOOD, body=BODY, current=USER, payload=bad)
        self.assertTrue(result)
        self.assertEqual(len(client.calls), 1)


if __name__ == '__main__':
    unittest.main()
