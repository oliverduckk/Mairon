"""Actual public producer/history/shadow boundary with neutral retained reads."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from test_core_milestone3b3a_public_shadow_integration import provider, research, contract
from core.public_answer_evidence import public_packet_digest
from research.public_factual_grounding import (
    build_public_factual_generation_instruction, requires_public_factual_salvage_completion,
    verify_public_factual_salvage_completion,
)
from research.public_factual_research import build_public_factual_authority_context
from research.public_source_completion import complete_public_source_request, public_source_output_required

TEXT = 'The service supports queued export.'
URL = 'https://docs.vendor.example/service/export'


class PublicClient:
    def __init__(self, drafts=None, *, exclude_caption=False, exclude_tail=False):
        self.drafts = iter(drafts or [TEXT])
        self.calls = []
        self.generations = self.verifications = 0
        self.exclude_caption, self.exclude_tail = exclude_caption, exclude_tail

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = '\n'.join(m['content'] for m in kwargs['messages'] if m['role'] == 'system')
        if 'INTERNAL public-factual evidence verifier' in system:
            self.verifications += 1
            sentences = re.findall(r'^S(\d+): (.*)$', kwargs['messages'][-1]['content'], re.M)
            statuses = [(int(index), not (self.exclude_caption and text.startswith('Source: '))
                         and not (self.exclude_tail and text == 'An invented side claim.'))
                        for index, text in sentences]
            supported = all(value for _, value in statuses)
            content = json.dumps({'supported': supported,
                                  'unsupported_claims': [] if supported else ['unsupported'],
                                  'sentence_assessments': [{'index': i, 'supported': v} for i, v in statuses]})
        elif 'INTERNAL supported-subset answer-completion verifier' in system:
            content = json.dumps({'completed': True, 'outcome': 'answered', 'request_fulfilled': True,
                                  'required_claim_assessments': [], 'violations': []})
        else:
            self.generations += 1
            content = next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason='stop')


def run(current, *, retained=None, client=None, observer=None):
    fn, namespace = provider(retained=retained)
    observations = []
    namespace.update({
        'build_public_factual_authority_context': build_public_factual_authority_context,
        'build_public_factual_generation_instruction': build_public_factual_generation_instruction,
        'public_source_output_required': public_source_output_required,
        'complete_public_source_request': complete_public_source_request,
        'should_verify_public_factual_salvage_completion': requires_public_factual_salvage_completion,
        'verify_public_factual_salvage_completion': verify_public_factual_salvage_completion,
        'observe_public_factual_response': observer or (lambda **kw: observations.append(kw)),
    })
    chat = client or PublicClient()
    with redirect_stdout(io.StringIO()):
        result = fn(chat, current, [], core_answer_contract=contract())
    return result, observations, chat


class PublicSourceCompletionIntegrationTests(unittest.TestCase):
    def test_real_successful_producer_includes_loaded_official_url_on_first_turn(self):
        result, observations, client = run('Check the official source. Give me the actual source URL.')
        self.assertEqual(result[0], TEXT + '\n\nSource: ' + URL)
        self.assertEqual(result[1][-1]['content'], result[0])
        self.assertEqual(client.generations, 1)
        self.assertEqual(client.verifications, 1)
        self.assertEqual(len(observations), 1)

    def test_actual_caption_is_verified_and_digest_matches_final_candidate(self):
        result, observations, _ = run('Give me the source URL.')
        state = observations[0]['verification_result'].verification_state
        self.assertEqual(state['assessed_draft_digest'], public_packet_digest(result[0]))
        self.assertEqual(len(state['sentence_assessments']), 2)
        self.assertEqual(observations[0]['text'], result[0])

    def test_missing_retained_url_publishes_explicit_truthful_limitation(self):
        retained = research()
        retained['sources'][0]['read_result'].pop('url')
        result, _, _ = run('Give me the actual source URL.', retained=retained)
        self.assertNotIn('https://', result[0])
        self.assertIn('cannot verify a usable loaded source URL', result[0])

    def test_discovered_url_does_not_fill_missing_read_identity(self):
        retained = research()
        retained['sources'][0]['read_result']['url'] = None
        result, _, _ = run('Include the source URL.', retained=retained)
        self.assertNotIn(retained['sources'][0]['url'], result[0])
        self.assertIn('cannot verify', result[0])

    def test_normal_question_output_and_history_are_unchanged(self):
        result, _, client = run('Does queued export work?')
        self.assertEqual(result[0], TEXT)
        self.assertEqual(result[1][-1]['content'], TEXT)
        self.assertEqual(client.generations, 1)

    def test_actual_read_redirect_identity_is_attached_without_guessing(self):
        retained = research()
        retained['sources'][0]['url'] = 'http://docs.vendor.example/service/export'
        result, _, _ = run('Include the official source URL.', retained=retained)
        self.assertIn(URL, result[0])
        self.assertNotIn('http://docs.vendor.example/service/export', result[0])

    def test_source_request_does_not_add_an_extra_model_call(self):
        _, _, client = run('Give me the official source URL.')
        self.assertEqual(len(client.calls), 2)

    def test_requested_provenance_is_preserved_after_unsupported_tail_salvage(self):
        client = PublicClient([TEXT + ' An invented side claim.'], exclude_tail=True)
        result, observations, _ = run('Give me the source URL.', client=client)
        self.assertEqual(result[0], TEXT + ' Source: ' + URL)
        self.assertNotIn('invented', result[0])
        self.assertFalse(observations, 'salvage is still excluded from common generated-public acceptance')

    def test_core_attachment_can_restore_caption_deleted_by_sentence_subset(self):
        client = PublicClient(exclude_caption=True)
        result, observations, _ = run('Give me the source URL.', client=client)
        self.assertIn(URL, result[0])
        self.assertEqual(client.generations, 1)
        self.assertFalse(observations)

    def test_shadow_rejection_cannot_change_completed_public_answer(self):
        result, _, _ = run('Include the source URL.', observer=lambda **kw: ['REJECTED'])
        self.assertEqual(result[0], TEXT + '\n\nSource: ' + URL)

    def test_shadow_exception_cannot_change_completed_public_answer(self):
        def broken(**kw):
            raise RuntimeError('unreported private error')
        result, _, _ = run('Include the source URL.', observer=broken)
        self.assertEqual(result[0], TEXT + '\n\nSource: ' + URL)

    def test_input_research_state_is_not_mutated(self):
        retained = research()
        snapshot = copy.deepcopy(retained)
        run('Give me the source URL.', retained=retained)
        self.assertEqual(retained, snapshot)

    def test_multi_source_provenance_does_not_guess_one_exclusive_read(self):
        retained = research()
        second = copy.deepcopy(retained['sources'][0])
        second['url'] = second['read_result']['url'] = 'https://research.example/queued-export'
        retained['sources'].append(second)
        result, observations, _ = run('Give me the actual source URL.', retained=retained)
        self.assertIn(URL, result[0])
        self.assertIn(second['read_result']['url'], result[0])
        self.assertEqual(observations[0]['text'], result[0])


if __name__ == '__main__':
    unittest.main()
