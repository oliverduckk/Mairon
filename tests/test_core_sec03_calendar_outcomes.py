"""SEC-03 F13: inert final Calendar dispatch and visible/persisted outcomes."""
import copy
import json
from contextlib import ExitStack
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
# Install the unchanged SEC-02 synthetic environment and audit guard before
# application imports, including when this script runs without the audit runner.
import test_core_sec02_external_data as _offline_fixture  # noqa: F401
import s1_offline_bootstrap  # noqa: F401
dotenv = types.ModuleType('dotenv')
dotenv.load_dotenv = lambda *args, **kwargs: False
sys.modules['dotenv'] = dotenv

from core import action_manager, router
from core.action_approval import issue_calendar_ticket, authorised_calendar_effect
from core.authority_handoff import seal_prepared_turn
from core.orchestrator import MaironCore
from tools import calendar_tools
import application_service as service

PRIVATE = 'SYNTHETIC_PRIVATE_EXCEPTION_8841'
TEXT = 'Add a synthetic appointment to my calendar for Friday from 10am to 11am.'
ACTION = {'type': 'create_calendar_event', 'summary': 'Synthetic appointment',
          'start_time': '2026-11-20T10:00:00+11:00', 'end_time': '2026-11-20T11:00:00+11:00',
          'location': 'Synthetic Meeting Room', 'description': 'Synthetic approved description'}


class RecordingCalendar:
    def __init__(self, mode='normal'):
        self.mode = mode
        self.prepared = []
        self.attempted = []
        self.committed = []

    def events(self):
        if self.mode == 'events_error':
            raise RuntimeError(PRIVATE)
        return self

    def insert(self, **payload):
        if self.mode == 'build_error':
            raise RuntimeError(PRIVATE)
        self.prepared.append(copy.deepcopy(payload))
        return self

    def execute(self):
        self.attempted.append(copy.deepcopy(self.prepared[-1]))
        if self.mode == 'execute_no_commit':
            raise TimeoutError(PRIVATE)
        self.committed.append(copy.deepcopy(self.prepared[-1]))
        if self.mode == 'execute_commit_timeout':
            raise TimeoutError(PRIVATE)
        if self.mode == 'execute_commit_valueerror':
            raise ValueError(PRIVATE)
        if self.mode == 'empty_response': return {}
        if self.mode == 'none_response': return None
        if self.mode == 'list_response': return []
        if self.mode == 'error_response': return {'id': 'synthetic', 'error': PRIVATE}
        if self.mode == 'cancelled_response': return {'id': 'synthetic', 'status': 'cancelled'}
        response = copy.deepcopy(self.prepared[-1]['body'])
        if self.mode != 'no_id':
            response['id'] = 'synthetic_event_id'
        return response


class ProposalProvider:
    def get_response(self, client, user_input, instructions, conversation=None, **kwargs):
        return None, list(conversation or []), None, copy.deepcopy(ACTION)


class CalendarOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.calendar = RecordingCalendar()
        self.service_factory = self.stack.enter_context(mock.patch.object(calendar_tools, 'create_calendar_service', side_effect=lambda: self.calendar))
        self.authority = seal_prepared_turn(MaironCore().prepare_turn(TEXT))
        self.assertEqual(self.authority.runtime.intent, 'calendar_event_creation_request')

    def approved(self):
        ticket = issue_calendar_ticket(ACTION, self.authority)
        self.assertIsNotNone(ticket)
        return ticket

    def execute(self, ticket=None):
        return action_manager.execute_approved_action(ACTION, approval_ticket=ticket or self.approved())

    def assert_unknown(self, result):
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertTrue(result['dispatch_attempted'])
        self.assertFalse(result['retryable'])
        answer = action_manager.format_action_result(ACTION, result)
        self.assertIn('could not be confirmed', answer)
        self.assertIn('Check your calendar before', answer)
        self.assertNotIn("wasn't created", answer)
        self.assertNotIn('Added ', answer)
        self.assertNotIn(PRIVATE, json.dumps(result) + answer)

    def test_01_missing_expired_revoked_mutated_and_invalid_approvals(self):
        tickets = []
        ticket = self.approved(); ticket._issued_at -= 601; tickets.append(ticket)
        ticket = self.approved(); ticket.revoke(); tickets.append(ticket)
        tickets.append(None)
        for ticket in tickets:
            result = action_manager.execute_approved_action(ACTION, approval_ticket=ticket)
            self.assertEqual(result['status'], 'not_attempted')
            self.assertFalse(result['dispatch_attempted'])
        ticket = self.approved()
        result = action_manager.execute_approved_action(dict(ACTION, summary='Changed title'), approval_ticket=ticket)
        self.assertEqual(result['status'], 'not_attempted')
        invalid = (dict(ACTION, start_time='not a date'), dict(ACTION, end_time=ACTION['start_time']),
                   dict(ACTION, unexpected=PRIVATE), dict(ACTION, summary=''))
        for payload in invalid:
            self.assertIsNone(issue_calendar_ticket(payload, self.authority))
            self.assertFalse(action_manager.execute_approved_action(payload)['success'])
        self.assertFalse(calendar_tools.create_calendar_event(ACTION['summary'], ACTION['start_time'], ACTION['end_time'])['success'])
        self.service_factory.assert_not_called()
        self.assertEqual(self.calendar.attempted, [])
        self.assertEqual(self.calendar.committed, [])
        print('SEC03_CALENDAR_DENIED ' + json.dumps({'cases': 9, 'attempted': 0, 'committed': 0}))

    def test_02_confirmed_insert_exact_payload_and_ticket_replay(self):
        ticket = self.approved()
        result = self.execute(ticket)
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'confirmed_created')
        self.assertFalse(result['retryable'])
        self.assertEqual(len(self.calendar.attempted), 1)
        self.assertEqual(len(self.calendar.committed), 1)
        self.assertEqual(self.calendar.attempted[0], {'calendarId': 'primary', 'body': {
            'summary': ACTION['summary'], 'start': {'dateTime': ACTION['start_time'], 'timeZone': 'Australia/Sydney'},
            'end': {'dateTime': ACTION['end_time'], 'timeZone': 'Australia/Sydney'},
            'location': ACTION['location'], 'description': ACTION['description']}})
        self.assertIn('Added Synthetic appointment to your calendar', action_manager.format_action_result(ACTION, result))
        replay = self.execute(ticket)
        self.assertFalse(replay['success'])
        self.assertNotIn("wasn't created", action_manager.format_action_result(ACTION, replay))
        self.assertEqual(len(self.calendar.attempted), 1)
        print('SEC03_CALENDAR_CONFIRMED {"attempted": 1, "committed": 1, "replay_additional_attempts": 0}')

    def test_03_normalisation_failure_cannot_reverse_confirmed_creation(self):
        for error in (ValueError(PRIVATE), RuntimeError(PRIVATE)):
            with self.subTest(error=type(error).__name__), mock.patch.object(calendar_tools, 'normalise_event', side_effect=error):
                self.calendar = RecordingCalendar()
                ticket = self.approved()
                result = self.execute(ticket)
                self.assertTrue(result['success'])
                self.assertEqual(result['status'], 'confirmed_created')
                self.assertTrue(result['details_unavailable'])
                self.assertEqual(result['event'], {'summary': ACTION['summary'], 'start': ACTION['start_time'],
                    'end': ACTION['end_time'], 'all_day': False})
                self.assertNotIn('id', result['event'])
                self.assertNotIn('htmlLink', result['event'])
                answer = action_manager.format_action_result(ACTION, result)
                self.assertIn('Added Synthetic appointment', answer)
                self.assertIn('Additional event details are unavailable.', answer)
                self.assertNotIn(PRIVATE, json.dumps(result) + answer)
                self.assertFalse(self.execute(ticket)['success'])
                self.assertEqual(len(self.calendar.attempted), 1)
                self.assertEqual(len(self.calendar.committed), 1)
        print('SEC03_CALENDAR_POSTPROCESS {"cases": 2, "confirmed_created_each": true, "attempted_each": 1, "committed_each": 1}')

    def test_04_post_dispatch_errors_are_unknown_even_without_recorded_commit(self):
        for mode, committed in (('execute_no_commit', 0), ('execute_commit_timeout', 1), ('execute_commit_valueerror', 1)):
            with self.subTest(mode=mode):
                self.calendar = RecordingCalendar(mode)
                ticket = self.approved()
                result = self.execute(ticket)
                self.assert_unknown(result)
                self.assertFalse(self.execute(ticket)['success'])
                self.assertEqual(len(self.calendar.attempted), 1)
                self.assertEqual(len(self.calendar.committed), committed)
        print('SEC03_CALENDAR_UNCERTAIN {"cases": 3, "attempted_each": 1, "committed": [0, 1, 1], "retries": 0}')

    def test_05_pre_dispatch_failures_never_insert_or_echo_exception(self):
        for mode in ('events_error', 'build_error', 'service_error'):
            with self.subTest(mode=mode):
                self.calendar = RecordingCalendar(mode)
                ticket = self.approved()
                if mode == 'service_error':
                    with mock.patch.object(calendar_tools, 'create_calendar_service', side_effect=RuntimeError(PRIVATE)):
                        result = self.execute(ticket)
                else:
                    result = self.execute(ticket)
                self.assertEqual(result['status'], 'not_attempted')
                self.assertFalse(result['success'])
                self.assertFalse(result['dispatch_attempted'])
                self.assertNotIn(PRIVATE, json.dumps(result) + action_manager.format_action_result(ACTION, result))
                self.assertFalse(self.execute(ticket)['success'])
                self.assertEqual(self.calendar.attempted, [])
                self.assertEqual(self.calendar.committed, [])
        print('SEC03_CALENDAR_PREDISPATCH {"cases": 3, "attempted": 0, "committed": 0}')

    def test_06_malformed_acknowledgement_is_unknown(self):
        for mode in ('empty_response', 'none_response', 'list_response', 'error_response', 'cancelled_response'):
            with self.subTest(mode=mode):
                self.calendar = RecordingCalendar(mode)
                self.assert_unknown(self.execute())
                self.assertEqual(len(self.calendar.attempted), 1)
                self.assertEqual(len(self.calendar.committed), 1)

    def test_07_matching_acknowledgement_without_id_does_not_invent_one(self):
        self.calendar = RecordingCalendar('no_id')
        result = self.execute()
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'confirmed_created')
        self.assertNotIn('id', result['event'])
        self.assertNotIn('htmlLink', result['event'])

    def test_08_final_adapter_rechecks_changed_payload_and_single_use(self):
        ticket = self.approved()
        with authorised_calendar_effect(ticket, ACTION) as allowed:
            self.assertTrue(allowed)
            changed = calendar_tools.create_calendar_event('Changed title', ACTION['start_time'], ACTION['end_time'], ACTION['location'], ACTION['description'])
            self.assertFalse(changed['success'])
            self.assertEqual(self.calendar.attempted, [])
            valid = calendar_tools.create_calendar_event(ACTION['summary'], ACTION['start_time'], ACTION['end_time'], ACTION['location'], ACTION['description'])
            self.assertTrue(valid['success'])
            repeated = calendar_tools.create_calendar_event(ACTION['summary'], ACTION['start_time'], ACTION['end_time'], ACTION['location'], ACTION['description'])
            self.assertFalse(repeated['success'])
        self.assertEqual(len(self.calendar.attempted), 1)

    def test_09_unclassified_or_contradictory_results_cannot_claim_no_creation(self):
        for value in (None, [], {'success': False, 'message': PRIVATE}, {'success': True},
                      {'success': True, 'status': 'not_attempted'}, {'success': False, 'status': 'confirmed_created'},
                      {'success': False, 'status': 'not_attempted'},
                      {'success': False, 'status': 'not_attempted', 'dispatch_attempted': True},
                      {'success': False, 'status': 'not_attempted', 'dispatch_attempted': 'false'}):
            answer = action_manager.format_action_result(ACTION, value)
            self.assertIn('could not be confirmed', answer)
            self.assertNotIn(PRIVATE, answer)
            self.assertNotIn("wasn't created", answer)
            self.assertEqual(action_manager.calendar_action_outcome(value), 'outcome_unknown')

    def test_10_router_carries_outcome_to_terminal_formatter(self):
        for mode, outcome in (('normal', 'confirmed_created'), ('execute_commit_timeout', 'outcome_unknown'), ('build_error', 'not_attempted')):
            with self.subTest(mode=mode):
                self.calendar = RecordingCalendar(mode)
                result = router.RouteResult(status='action_approval_required', pending_action=copy.deepcopy(ACTION),
                    approval_ticket=self.approved(), core_authority=self.authority)
                returned = router.approve_pending_action(result)
                self.assertEqual(returned.action_outcome, outcome)
                self.assertNotIn(PRIVATE, returned.answer)
                if outcome == 'outcome_unknown': self.assertIn('could not be confirmed', returned.answer)
        for malformed in ({'success':False,'status':'confirmed_created','dispatch_attempted':True},
                          {'success':False,'status':'not_attempted','dispatch_attempted':True}):
            with mock.patch.object(router,'execute_approved_action',return_value=malformed):
                result=router.RouteResult(status='action_approval_required',pending_action=copy.deepcopy(ACTION),
                    approval_ticket=self.approved(),core_authority=self.authority)
                returned=router.approve_pending_action(result)
                self.assertEqual(returned.action_outcome,'outcome_unknown')
                self.assertIn('could not be confirmed',returned.answer)

    def test_11_real_application_text_and_voice_persist_truthful_visible_outcome(self):
        journal = []
        persisted = []
        safety = []
        original_sanitise = service.sanitise_visible_response
        def sanitise(user_text, answer, **kwargs):
            safety.append(kwargs.get('action_confirmed'))
            return original_sanitise(user_text, answer, **kwargs)
        for name in ('capture_user_preference', 'build_user_preference_recall_response'):
            self.stack.enter_context(mock.patch.object(service, name, return_value=None))
        self.stack.enter_context(mock.patch.object(service, 'record_conversation_turn', side_effect=lambda **kw: journal.append(kw)))
        self.stack.enter_context(mock.patch.object(service, 'record_chat_turn', side_effect=lambda **kw: persisted.append(kw)))
        self.stack.enter_context(mock.patch.object(service, 'sanitise_visible_response', side_effect=sanitise))
        for channel in ('text', 'voice'):
            for mode in ('normal', 'postprocess_error', 'execute_commit_timeout', 'build_error'):
                with self.subTest(channel=channel, mode=mode), ExitStack() as case:
                    self.calendar = RecordingCalendar(mode)
                    if mode == 'postprocess_error':
                        case.enter_context(mock.patch.object(calendar_tools, 'normalise_event', side_effect=ValueError(PRIVATE)))
                    app = service.MaironApplication(user_name='SyntheticUser', core=MaironCore(),
                        local_ai={'module': ProposalProvider(), 'client': object()}, cloud_ai=None, create_providers=False)
                    app._schedule_semantic_title_if_first_turn = lambda **kwargs: None
                    proposal = app.submit_text(TEXT, channel=channel)
                    self.assertEqual(proposal.status, 'action_approval_required')
                    self.assertEqual(self.calendar.attempted, [])
                    result = app.resolve_pending_approval(True)
                    self.assertEqual(result.status, 'answered')
                    self.assertFalse(app.has_pending_approval)
                    self.assertEqual(journal[-1]['assistant_text'], result.answer)
                    self.assertEqual(persisted[-1]['assistant_text'], result.answer)
                    self.assertEqual(persisted[-1]['channel'], channel)
                    self.assertNotIn(PRIVATE, result.answer)
                    if mode in ('normal', 'postprocess_error'):
                        self.assertIn('Added Synthetic appointment', result.answer)
                        self.assertTrue(safety[-1])
                    elif mode == 'execute_commit_timeout':
                        self.assertIn('could not be confirmed', result.answer)
                        self.assertNotIn("wasn't created", result.answer)
                        self.assertNotIn("haven't created", result.answer)
                        self.assertFalse(safety[-1])
                    else:
                        self.assertFalse(safety[-1])
                    before = len(self.calendar.attempted)
                    self.assertEqual(app.resolve_pending_approval(True).status, 'error')
                    self.assertEqual(len(self.calendar.attempted), before)
        print('SEC03_CALENDAR_APPLICATION {"text_voice_cases": 8, "unapproved_attempts": 0, "persisted_answers_match": true, "duplicate_approval_attempts": 0}')

    def test_12_unexpected_adapter_escape_is_unknown_and_sanitised(self):
        with mock.patch.object(action_manager, 'create_calendar_event', side_effect=RuntimeError(PRIVATE)):
            ticket = self.approved()
            result = self.execute(ticket)
            self.assert_unknown(result)
            self.assertFalse(self.execute(ticket)['success'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
