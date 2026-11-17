"""INT-01 F12: real application/router, synthetic SQLite and Calendar only."""
import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.extend([str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parent)])
import test_core_sec02_external_data as offline
import test_core_sec03_calendar_outcomes as cal
import application_service as service
from continuity import chat_session_store as store
from core.conversation_state import append_visible_turn_to_model_history
from core.history_projection import project_action_history
from core.response_timer import ResponseTimer


class CalendarHistoryTests(unittest.TestCase):
    def setUp(self):
        self.f=cal.CalendarOutcomeTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.directory=self.f.stack.enter_context(tempfile.TemporaryDirectory())
        self.db=Path(self.directory)/'synthetic-chat.sqlite3'
        self.journal=[]
        self.f.stack.enter_context(mock.patch.object(service,'record_conversation_turn',side_effect=lambda **kw:self.journal.append(kw)))
        self.f.stack.enter_context(mock.patch.object(service,'record_chat_turn',side_effect=self.persist))
        self.f.stack.enter_context(mock.patch.object(service,'load_chat_session',side_effect=lambda sid:store.load_chat_session(sid,db_path=self.db)))
        for name in ('capture_user_preference','build_user_preference_recall_response'):
            self.f.stack.enter_context(mock.patch.object(service,name,return_value=None))

    def persist(self,**kwargs): return store.record_chat_turn(**kwargs,db_path=self.db)

    def app(self,provider=None):
        app=service.MaironApplication(user_name='Synthetic',core=cal.MaironCore(),
            local_ai={'client':object(),'module':provider or cal.ProposalProvider()},cloud_ai=None,create_providers=False)
        app._schedule_semantic_title_if_first_turn=lambda **kw:None
        return app

    def check(self,mode,approved=True,channel='text',provider=None):
        self.f.calendar=cal.RecordingCalendar(mode)
        app=self.app(provider)
        proposal=app.submit_text(cal.TEXT,channel=channel)
        self.assertEqual(proposal.status,'action_approval_required')
        self.assertEqual(self.f.calendar.attempted,[])
        if mode=='postprocess_error':
            self.f.stack.enter_context(mock.patch.object(cal.calendar_tools,'normalise_event',side_effect=ValueError(cal.PRIVATE)))
        if mode=='expired': app._pending.router_result.approval_ticket.revoke()
        result=app.resolve_pending_approval(approved)
        session=store.load_chat_session(app.session_id,db_path=self.db)
        self.assertEqual(len(session['turns']),1)
        self.assertEqual(session['turns'][0]['user_text'],cal.TEXT)
        self.assertEqual(session['turns'][0]['assistant_text'],result.answer)
        live=copy.deepcopy(app.local_state)
        self.assertEqual([(m['role'],m['content']) for m in live if m['role']!='system'],[('user',cal.TEXT),('assistant',result.answer)])
        count=len(self.f.calendar.attempted)
        self.assertEqual(app.resolve_pending_approval(True).status,'error')
        self.assertEqual(len(self.f.calendar.attempted),count)
        app.open_chat(app.session_id)
        self.assertEqual(app.local_state,live)
        self.assertEqual(len(self.f.calendar.attempted),count)
        return app,result

    def test_all_truthful_outcomes_text_voice_and_restore_exactly_once(self):
        cases=0
        for channel in ('text','voice'):
            for mode,approved in [('normal',True),('normal',False),('build_error',True),('execute_commit_timeout',True),('expired',True)]:
                with self.subTest(mode=mode,approved=approved,channel=channel):
                    _,result=self.check(mode,approved,channel)
                    if mode=='execute_commit_timeout': self.assertIn('could not be confirmed',result.answer)
                    cases+=1
        print('INT01_CALENDAR_PARITY '+json.dumps({'cases':cases,'duplicate_insertions':0,'visible_persisted_live_restored_equal':True}))

    def test_postprocess_error_stays_created_and_projected(self):
        _,result=self.check('postprocess_error')
        self.assertIn('Added Synthetic appointment',result.answer)

    def test_provider_already_appended_proposal_is_not_duplicated(self):
        class Appending(cal.ProposalProvider):
            def get_response(self,client,user_input,instructions,conversation=None,**kwargs):
                return None,list(conversation or [])+[{'role':'user','content':user_input},{'role':'assistant','content':'UNSHOWN PROPOSAL'}],None,copy.deepcopy(cal.ACTION)
        _,result=self.check('normal',provider=Appending())
        self.assertNotIn('UNSHOWN',result.answer)

    def test_final_sanitised_answer_is_only_projected_version(self):
        with mock.patch.object(service,'sanitise_visible_response',return_value=('Sanitised visible result.','synthetic')):
            _,result=self.check('normal')
        self.assertEqual(result.answer,'Sanitised visible result.')

    def test_persistence_before_and_after_commit_retries_do_not_repeat_effect(self):
        for after in (False,True):
            app=self.app(); app.submit_text(cal.TEXT)
            calls=[]
            def interrupted(**kw):
                calls.append(1)
                if after: self.persist(**kw)
                raise RuntimeError('synthetic store interruption')
            with mock.patch.object(service,'record_chat_turn',side_effect=interrupted):
                result=app.resolve_pending_approval(True)
                live=copy.deepcopy(app.local_state)
                with self.assertRaises(RuntimeError): app.new_chat()
            effects=len(self.f.calendar.attempted)
            self.assertTrue(app.retry_pending_history())
            self.assertTrue(app.retry_pending_history())
            self.assertEqual(len(self.f.calendar.attempted),effects)
            saved=store.load_chat_session(app.session_id,db_path=self.db)
            self.assertEqual(len(saved['turns']),1)
            self.assertEqual(saved['turns'][0]['assistant_text'],result.answer)
            app.open_chat(app.session_id);self.assertEqual(app.local_state,live)
        print('INT01_CALENDAR_INTERRUPTION {"cuts":2,"persisted_each":1,"effect_retries":0}')

    def test_projection_receipt_rejects_changed_content(self):
        values=dict(session_id='synthetic-session',user_text='Synthetic request',assistant_text='Synthetic result',operation_id='synthetic-operation')
        first=self.persist(**values)
        self.assertEqual(self.persist(**values),first)
        with self.assertRaises(ValueError):self.persist(**dict(values,assistant_text='Different'))
        self.assertEqual(len(store.load_chat_session('synthetic-session',db_path=self.db)['turns']),1)

    def test_failed_outcome_write_blocks_later_turn_from_reordering_history(self):
        app=self.app(); app.submit_text(cal.TEXT)
        def only_calendar_fails(**kw):
            if kw.get('operation_id'): raise RuntimeError('synthetic interruption')
            return self.persist(**kw)
        with mock.patch.object(service,'record_chat_turn',side_effect=only_calendar_fails):
            result=app.resolve_pending_approval(True)
            live=copy.deepcopy(app.local_state)
            later=app.submit_text('Thanks.')
            self.assertEqual(later.status,'error')
            self.assertEqual(app.local_state,live)
            self.assertIsNone(store.load_chat_session(app.session_id,db_path=self.db))
        self.assertTrue(app.retry_pending_history())
        self.assertEqual(len(self.f.calendar.attempted),1)
        saved=store.load_chat_session(app.session_id,db_path=self.db)
        self.assertEqual([r['assistant_text'] for r in saved['turns']],[result.answer])

    def test_delete_flushes_or_blocks_pending_outcome_and_cleans_receipt(self):
        app=self.app();app.submit_text(cal.TEXT)
        with mock.patch.object(service,'record_chat_turn',side_effect=RuntimeError('synthetic unavailable')):
            app.resolve_pending_approval(True)
            with mock.patch.object(service,'delete_chat_session') as delete:
                with self.assertRaises(RuntimeError):app.delete_chat(app.session_id)
                delete.assert_not_called()
        old=app.session_id
        with mock.patch.object(service,'delete_chat_session',side_effect=lambda sid:store.delete_chat_session(sid,db_path=self.db)):
            app.delete_chat(old)
        self.assertIsNone(store.load_chat_session(old,db_path=self.db))
        self.assertFalse(app._pending_history_records)
        with store._connection(self.db) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM chat_projection_receipts WHERE session_id=?',(old,)).fetchone()[0],0)

    def test_prior_equal_text_and_direct_replies_are_not_global_deduplicated(self):
        app=self.app()
        for _ in range(2):
            app._finalize_direct_response(user_text='Hello',answer='Hello again.',timer=ResponseTimer(),channel='text',intent='casual_conversation',authority='conversation')
        before=copy.deepcopy(app.local_state)
        app.submit_text(cal.TEXT);app.resolve_pending_approval(False)
        self.assertEqual(app.local_state[:len(before)],before)
        live=copy.deepcopy(app.local_state);app.open_chat(app.session_id)
        self.assertEqual(app.local_state,live)

    def test_terminal_action_finalisation_uses_same_sanitised_projection(self):
        # Execute the actual terminal finalisation block without startup/loop.
        path=Path(service.__file__).parent/'main.py'
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        loop=next(n for n in tree.body if isinstance(n,ast.While))
        start=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='published_answer' for t in n.targets))
        block=ast.Module(body=loop.body[start:],type_ignores=[])
        for approved in (True,False):
            app=self.app();app.submit_text(cal.TEXT)
            pending=app._pending.router_result
            result=cal.router.approve_pending_action(pending) if approved else cal.router.decline_pending_action(pending)
            emitted=[]
            ns={'result':result,'user_input':cal.TEXT,'local_state':result.local_state,'cloud_state':None,
                'response_timer':ResponseTimer(),'mairon_instructions':'Synthetic instructions',
                'sanitise_visible_response':service.sanitise_visible_response,'project_action_history':project_action_history,
                'emit_final_response':lambda **kw:emitted.append(kw),'append_visible_turn_to_model_history':append_visible_turn_to_model_history,
                'bounded_local_history':service.bounded_local_history}
            exec(compile(ast.fix_missing_locations(block),str(path),'exec'),ns)
            self.assertEqual(ns['local_state'][-1]['content'],emitted[0]['answer'])
            self.assertEqual(sum(m['role']=='user' for m in ns['local_state']),1)
            self.assertIs(cal.router.approve_pending_action(pending),result)


if __name__=='__main__': unittest.main(verbosity=2)
