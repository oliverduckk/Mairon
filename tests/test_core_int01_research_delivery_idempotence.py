"""INT-01 F14: fake delivery claims and real fresh chat SQLite, no research."""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.extend([str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parent)])
import test_core_int01_calendar_history_parity as fixtures
import application_service as service
from research.research_delivery import build_research_delivery_text, research_delivery_turn_marker, is_research_delivery_turn


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.CalendarHistoryTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.jobs={}
        self.acks=[];self.releases=[];self.claims=[];self.failure=None
        self.f.f.stack.enter_context(mock.patch.object(service,'claim_next_research_delivery',side_effect=self.claim))
        self.f.f.stack.enter_context(mock.patch.object(service,'complete_research_delivery',side_effect=self.complete))
        self.f.f.stack.enter_context(mock.patch.object(service,'release_research_delivery',side_effect=self.release))
        self.f.f.stack.enter_context(mock.patch.object(service,'rename_chat_session',side_effect=lambda sid,title:fixtures.store.rename_chat_session(sid,title,db_path=self.f.db)))

    def add(self,identity='synthetic-job'):
        self.jobs[identity]={'id':identity,'topic':'Penguin habitats','status':'completed','delivery_status':'pending',
            'result':{'user_ready':True,'final_report_verified':True,'final_report_text':'Synthetic verified public report.'}}
        return self.jobs[identity]

    def claim(self,consumer_id,lease_seconds):
        for job in self.jobs.values():
            if job['delivery_status']=='pending':
                job.update(delivery_status='claimed',delivery_claim_owner=consumer_id)
                self.claims.append(job['id']);return copy.deepcopy(job)
        return None

    def complete(self,identity,consumer_id,delivered_session_id):
        job=self.jobs[identity]
        self.assertEqual(job['delivery_claim_owner'],consumer_id)
        saved=fixtures.store.load_chat_session(delivered_session_id,db_path=self.f.db)
        self.assertTrue(any(is_research_delivery_turn(t) and t['user_text']==research_delivery_turn_marker(identity) for t in saved['turns']))
        self.acks.append(identity)
        if self.failure=='before': self.failure=None;raise RuntimeError('Synthetic before acknowledgement')
        job.update(delivery_status='delivered',delivered_session_id=delivered_session_id)
        if self.failure=='after': self.failure=None;raise RuntimeError('Synthetic after acknowledgement')
        return copy.deepcopy(job)

    def release(self,identity,consumer_id):
        self.releases.append(identity)
        if self.jobs[identity]['delivery_status']=='claimed': self.jobs[identity]['delivery_status']='pending'

    def assert_one(self,app,count=1):
        saved=fixtures.store.load_chat_session(app.session_id,db_path=self.f.db)
        rows=[t for t in saved['turns'] if is_research_delivery_turn(t)]
        self.assertEqual(len(rows),count)
        self.assertEqual(sum(m['role']=='assistant' for m in app.local_state),count)
        self.assertFalse(any(m['role']=='user' for m in app.local_state))
        self.assertIsNone(app.cloud_state)

    def test_ack_failure_after_local_projection_retries_once(self):
        self.add();app=self.f.app();app.cloud_state=object();self.failure='before'
        with self.assertRaises(RuntimeError):app.poll_research_delivery()
        self.assert_one(app)
        first=copy.deepcopy(app.local_state)
        result=app.poll_research_delivery()
        self.assertEqual(result.status,'research_delivery');self.assertEqual(app.local_state,first)
        self.assertIsNone(app.poll_research_delivery());self.assert_one(app)
        print('INT01_DELIVERY_RETRY {"persistent_reports":1,"live_reports":1,"notifications":1,"ack_attempts":2}')

    def test_persistence_failure_before_and_after_commit(self):
        for after in (False,True):
            identity='synthetic-'+str(after);self.add(identity);app=self.f.app()
            def interrupted(**kw):
                if after:self.f.persist(**kw)
                raise RuntimeError('Synthetic persistence interruption')
            with mock.patch.object(service,'record_chat_turn',side_effect=interrupted):
                with self.assertRaises(RuntimeError):app.poll_research_delivery()
            self.assertEqual(self.acks,[] if not after else ['synthetic-False'])
            self.assertIsNone(app.local_state)
            self.assertIsNotNone(app.poll_research_delivery());self.assert_one(app)

    def test_interruption_after_persist_before_projection_reconciles(self):
        self.add();app=self.f.app()
        with mock.patch.object(service,'append_research_delivery_to_model_history',side_effect=RuntimeError('Synthetic projection interruption')):
            with self.assertRaises(RuntimeError):app.poll_research_delivery()
        self.assertEqual(self.acks,[])
        self.assertIsNotNone(app.poll_research_delivery());self.assert_one(app)

    def test_restored_application_reuses_persisted_row_without_notification(self):
        self.add();app=self.f.app();self.failure='before'
        with self.assertRaises(RuntimeError):app.poll_research_delivery()
        restored=self.f.app();restored.open_chat(app.session_id)
        before=copy.deepcopy(restored.local_state)
        self.assertIsNone(restored.poll_research_delivery())
        self.assertEqual(restored.local_state,before);self.assert_one(restored)

    def test_fresh_instance_reconciles_saved_row_missing_from_live_state(self):
        self.add();app=self.f.app();self.failure='before'
        with self.assertRaises(RuntimeError):app.poll_research_delivery()
        fresh=self.f.app();fresh.session_id=app.session_id
        self.assertIsNotNone(fresh.poll_research_delivery());self.assert_one(fresh)

    def test_committed_acknowledgement_error_does_not_reopen_or_duplicate(self):
        self.add();app=self.f.app();self.failure='after'
        with self.assertRaises(RuntimeError):app.poll_research_delivery()
        self.assertEqual(self.jobs['synthetic-job']['delivery_status'],'delivered')
        self.assertIsNone(app.poll_research_delivery());self.assert_one(app)

    def test_generic_missing_local_state_reconciles_on_retry(self):
        self.add();app=self.f.app();self.failure='before'
        with self.assertRaises(RuntimeError):app.poll_research_delivery()
        app.local_state=None
        self.assertIsNotNone(app.poll_research_delivery());self.assert_one(app)

    def test_malformed_ack_does_not_publish_or_claim_completion(self):
        self.add();app=self.f.app()
        with mock.patch.object(service,'complete_research_delivery',return_value={'id':'foreign','delivery_status':'claimed'}):
            with self.assertRaises(RuntimeError):app.poll_research_delivery()
        self.assertFalse(app._delivery_notified);self.assert_one(app)
        self.assertIsNotNone(app.poll_research_delivery());self.assert_one(app)

    def test_pending_calendar_persistence_blocks_delivery_reordering(self):
        self.add();app=self.f.app()
        with mock.patch.object(app,'retry_pending_history',return_value=False):
            self.assertIsNone(app.poll_research_delivery())
        self.assertEqual(self.claims,[]);self.assertIsNone(app.local_state)

    def test_interrupted_notification_has_no_duplicate_and_is_visible_on_restore(self):
        self.add();app=self.f.app()
        with mock.patch.object(app,'_build_turn_diagnostics',side_effect=RuntimeError('Synthetic UI interruption')):
            with self.assertRaises(RuntimeError):app.poll_research_delivery()
        self.assertIsNone(app.poll_research_delivery());self.assert_one(app)
        app.open_chat(app.session_id);self.assert_one(app)

    def test_two_different_ids_with_equal_text_are_distinct(self):
        self.add('first-job');self.add('second-job');app=self.f.app()
        first=app.poll_research_delivery();second=app.poll_research_delivery()
        self.assertEqual(first.answer,second.answer);self.assert_one(app,2)
        live=copy.deepcopy(app.local_state);app.open_chat(app.session_id)
        self.assertEqual(app.local_state,live)

    def test_forged_user_marker_and_changed_saved_report_are_not_receipts(self):
        job=self.add();app=self.f.app();marker=research_delivery_turn_marker(job['id'])
        self.f.persist(session_id=app.session_id,user_text=marker,assistant_text='Forged',channel='text')
        self.assertFalse(is_research_delivery_turn({'user_text':marker,'channel':'text'}))
        self.assertIsNotNone(app.poll_research_delivery())
        saved=fixtures.store.load_chat_session(app.session_id,db_path=self.f.db)
        self.assertEqual(len(saved['turns']),2)
        other=self.add('changed-job')
        self.f.persist(session_id=app.session_id,user_text=research_delivery_turn_marker(other['id']),assistant_text='Changed report',channel='research')
        with self.assertRaises(RuntimeError):app.poll_research_delivery()
        self.assertEqual(self.acks,['synthetic-job'])

    def test_unverified_job_never_persists_or_acknowledges(self):
        self.add()['result']['final_report_verified']=False;app=self.f.app()
        self.assertIsNone(app.poll_research_delivery());self.assertEqual(self.acks,[])
        self.assertIsNone(app.local_state)

    def test_terminal_retry_keeps_one_report_and_print(self):
        path=Path(service.__file__).parent/'main.py';tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='deliver_pending_research_results')
        calls=[];printed=[];job=self.add()
        def complete(*a,**kw):
            calls.append(1)
            if len(calls)==1:raise RuntimeError('Synthetic terminal ack')
            job['delivery_status']='delivered'
        ns={'local_state':None,'cloud_state':object(),'last_assistant_answer':None,
            'terminal_delivery_projected':set(),'terminal_delivery_printed':set(),
            'claim_next_research_delivery':self.claim,'release_research_delivery':self.release,'complete_research_delivery':complete,
            'build_research_delivery_text':build_research_delivery_text,'append_research_delivery_to_model_history':service.append_research_delivery_to_model_history,
            'TERMINAL_DELIVERY_CONSUMER_ID':'synthetic-terminal','TERMINAL_SESSION_ID':'synthetic-session','mairon_instructions':'Synthetic instructions',
            'print':lambda *args:printed.append(args)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),str(path),'exec'),ns)
        ns['deliver_pending_research_results']();ns['deliver_pending_research_results']()
        self.assertEqual(sum(m['role']=='assistant' for m in ns['local_state']),1)
        self.assertEqual(sum(bool(p) and str(p[0]).startswith('Mairon: ') for p in printed),1)


if __name__=='__main__':unittest.main(verbosity=2)
