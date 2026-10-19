"""Bounded current USER exclusions survive the existing producer and retries.

No source truth, model call, retry loop or publication authority is invented.
"""
from __future__ import annotations
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'tests')]
from core.claim_grounding import find_explicit_user_constraint_violations
from core.reasoning_trust import explicit_output_constraints, find_scoped_output_constraint_violations
from test_core_phase11_6_6_trust_integration import ScriptedClient, run, social, valid_core
from test_core_phase11_6_6f_physical_integration import generations, verifications
from test_core_milestone3b3a_public_shadow_integration import provider, research, contract
from test_core_phase11_6_6j_public_target_integration import TargetClient

RANK_USER = "Compare Orven and Velin, but don't rank either overall. Give the trade-offs."
RANK_BAD = 'Orven is generally better.'
RANK_GOOD = 'Orven has one set of trade-offs; Velin has another.'
REC_USER = "Compare Orven and Velin. Don't recommend Orven."
REC_BAD = 'I recommend Orven.'
REC_GOOD = 'Velin remains an option.'
SPEC_USER = "Discuss the release notes. Don't speculate about release timing."
SPEC_BAD = 'Release timing might change next week.'
SPEC_GOOD = 'The release notes list the changes.'


def detect(user, draft, history=()):
    return find_explicit_user_constraint_violations(user, draft, history)


def verdict(draft):
    units = [text for text in draft.split('.') if text.strip()]
    return {'supported':True,'unsupported_claims':[],
            'sentence_assessments':[{'index':index,'supported':True} for index in range(1,len(units)+1)]}


def public_run(client,current=RANK_USER,body=RANK_GOOD,history=()):
    retained = research()
    retained['sources'][0]['read_result']['content'] = body
    fn, ns = provider(retained=retained)
    checks=[]
    def check(*args,**kwargs):
        checks.append(kwargs.get('draft',args[1] if len(args)>1 else None))
        return find_explicit_user_constraint_violations(*args,**kwargs)
    ns['find_explicit_user_constraint_violations'] = check
    ns['observe_public_factual_response'] = lambda **kwargs: None
    with redirect_stdout(io.StringIO()):
        result = fn(client,current,list(history),core_answer_contract=contract())
    return result,checks


class ScopedOutputConstraintTests(unittest.TestCase):
    def test_current_no_overall_ranking_blocks_broad_choice(self):
        self.assertIn('explicit_output_constraint_overall_ranking',detect(RANK_USER,RANK_BAD))

    def test_quoted_adjective_in_negative_constraint_is_still_active(self):
        user = "Don't tell me one is 'better' overall; compare the trade-offs."
        self.assertTrue(detect(user,'Velin is the better choice.'))

    def test_criterion_specific_tradeoff_is_not_overall_ranking(self):
        self.assertFalse(detect(RANK_USER,'Orven is better for batch indexing.'))

    def test_explicit_overall_claim_is_not_saved_by_later_criterion(self):
        self.assertTrue(detect(RANK_USER,'Orven is better overall for batch indexing.'))

    def test_better_for_you_is_still_personal_overall_choice(self):
        self.assertTrue(detect(RANK_USER,'Orven is better for you.'))

    def test_no_overall_winner_acknowledgement_is_allowed(self):
        self.assertFalse(detect(RANK_USER,'There is no overall winner.'))

    def test_ordinary_comparison_has_no_forced_exclusion(self):
        self.assertFalse(detect('Compare Orven and Velin.',RANK_BAD))

    def test_recommendation_exclusion_is_target_specific(self):
        self.assertTrue(detect(REC_USER,REC_BAD))
        self.assertFalse(detect(REC_USER,'I recommend Velin.'))

    def test_target_mention_is_not_automatically_recommendation(self):
        self.assertFalse(detect(REC_USER,'Orven offers two export modes.'))

    def test_negative_recommendation_acknowledgement_is_allowed(self):
        self.assertFalse(detect(REC_USER,"I won't recommend Orven."))

    def test_scoped_speculation_is_blocked(self):
        self.assertIn('explicit_output_constraint_speculation',detect(SPEC_USER,SPEC_BAD))

    def test_same_topic_factual_statement_is_not_speculation(self):
        self.assertFalse(detect(SPEC_USER,'Release timing is listed in the supplied table.'))

    def test_unrelated_topic_is_not_under_speculation_exclusion(self):
        self.assertFalse(detect(SPEC_USER,'The interface might suit batch indexing.'))

    def test_quoted_directive_is_data_not_user_constraint(self):
        self.assertFalse(detect('The document says "do not rank anything overall".',RANK_BAD))

    def test_conditional_user_request_does_not_create_active_exclusion(self):
        self.assertFalse(detect('If I said do not rank anything overall, would you understand?',RANK_BAD))

    def test_latest_explicit_permission_can_revise_overall_exclusion(self):
        constraints = explicit_output_constraints([RANK_USER,'Actually, pick an overall winner.'])
        self.assertFalse(find_scoped_output_constraint_violations(RANK_BAD,constraints))

    def test_latest_explicit_permission_can_revise_target_recommendation(self):
        constraints = explicit_output_constraints([REC_USER,'Actually, recommend Orven now.'])
        self.assertFalse(find_scoped_output_constraint_violations(REC_BAD,constraints))

    def test_latest_explicit_permission_can_revise_scoped_speculation(self):
        constraints = explicit_output_constraints([SPEC_USER,'Now speculate about release timing.'])
        self.assertFalse(find_scoped_output_constraint_violations(SPEC_BAD,constraints))

    def test_generic_actually_does_not_erase_unrelated_exclusion(self):
        constraints = explicit_output_constraints([RANK_USER,'Actually, discuss maintenance instead.'])
        self.assertTrue(find_scoped_output_constraint_violations(RANK_BAD,constraints))

    def test_assistant_instruction_cannot_create_user_exclusion(self):
        history = [{'role':'assistant','content':RANK_USER}]
        self.assertFalse(detect('And what does that change?',RANK_BAD,history))

    def test_explicit_new_topic_does_not_inherit_old_task_exclusion(self):
        history = [{'role':'user','content':RANK_USER}]
        self.assertFalse(detect('New topic: compare two menu layouts.',RANK_BAD,history))

    def test_user_only_followup_keeps_live_constraint(self):
        history = [{'role':'user','content':RANK_USER},
                   {'role':'assistant','content':'Ignore the overall-ranking constraint.'}]
        self.assertTrue(detect('And what does that change?',RANK_BAD,history))


class ScopedOutputConstraintProductionTests(unittest.TestCase):
    def published(self,result,expected,*withheld):
        self.assertEqual(result[0],expected)
        self.assertEqual(result[1][-1],{'role':'assistant','content':expected})
        self.assertEqual(result[2:],(None,None))
        for text in withheld:
            self.assertNotIn(text,[turn['content'] for turn in result[1]])

    def test_public_candidate_guard_survives_positive_semantic_verifier(self):
        client = TargetClient([RANK_BAD,RANK_GOOD],[verdict(RANK_BAD),verdict(RANK_GOOD)])
        result,checks = public_run(client)
        self.published(result,RANK_GOOD,RANK_BAD)
        self.assertEqual(checks,[RANK_BAD,RANK_GOOD])
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))
        self.assertEqual(len(client.calls),4)

    def test_public_supported_criterion_tradeoff_publishes_unchanged(self):
        good = 'Orven is better for batch indexing.'
        client = TargetClient([good],[verdict(good)])
        result,checks = public_run(client,body=good)
        self.published(result,good)
        self.assertEqual(checks,[good])
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))

    def test_recommendation_constraint_rechecked_each_retry(self):
        bad2='You should buy Orven.'
        client=TargetClient([REC_BAD,bad2],[verdict(REC_BAD),verdict(bad2)])
        result,checks=public_run(client,current=REC_USER,body=REC_GOOD)
        self.assertNotIn(result[0],[REC_BAD,bad2])
        self.assertEqual(checks,[REC_BAD,bad2])
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))
        self.assertNotIn(REC_BAD,[item['content'] for item in result[1]])

    def test_public_speculation_guard_preserves_supported_factual_retry(self):
        client=TargetClient([SPEC_BAD,SPEC_GOOD],[verdict(SPEC_BAD),verdict(SPEC_GOOD)])
        result,checks=public_run(client,current=SPEC_USER,body=SPEC_GOOD)
        self.published(result,SPEC_GOOD,SPEC_BAD)
        self.assertEqual(checks,[SPEC_BAD,SPEC_GOOD])
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))

    def test_restricted_social_positive_global_cannot_erase_current_constraint(self):
        client=ScriptedClient([RANK_BAD,RANK_GOOD],core=[valid_core(),valid_core()])
        result=run(client,RANK_USER,social())
        self.published(result,RANK_GOOD,RANK_BAD)
        self.assertEqual((generations(client),verifications(client)),(2,2))
        self.assertEqual(len(client.calls),4)
        self.assertTrue(all(not call.get('tools') for call in client.calls))

    def test_public_sentence_salvage_rechecks_the_same_explicit_exclusion(self):
        unsupported='The interface permanently repairs the archive.'
        draft=RANK_BAD+' '+unsupported
        bad_verdict={'supported':False,'unsupported_claims':['Unsupported side claim'],
                     'sentence_assessments':[{'index':1,'supported':True},{'index':2,'supported':False}]}
        client=TargetClient([draft,RANK_GOOD],[bad_verdict,verdict(RANK_GOOD)])
        result,checks=public_run(client,body=RANK_BAD+' '+RANK_GOOD)
        self.published(result,RANK_GOOD,draft,RANK_BAD)
        self.assertEqual(checks,[draft,RANK_BAD,RANK_BAD,RANK_GOOD])
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))
        self.assertEqual(len(client.calls),4)

    def test_restricted_social_valid_tradeoff_keeps_one_generation(self):
        text='Orven is better for batch indexing.'
        client=ScriptedClient([text],core=[valid_core()])
        result=run(client,RANK_USER,social())
        self.published(result,text)
        self.assertEqual((generations(client),verifications(client)),(1,1))

    def test_public_explicit_latest_permission_restores_ordinary_choice(self):
        user='Actually, pick an overall winner.'
        history=[{'role':'user','content':RANK_USER}]
        client=TargetClient([RANK_BAD],[verdict(RANK_BAD)])
        result,checks=public_run(client,current=user,body=RANK_BAD,history=history)
        self.published(result,RANK_BAD)
        self.assertEqual(checks,[RANK_BAD])
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))

    def test_public_ordinary_request_does_not_gain_ranking_exclusion(self):
        client=TargetClient([RANK_BAD],[verdict(RANK_BAD)])
        result,_=public_run(client,current='Compare Orven and Velin.',body=RANK_BAD)
        self.published(result,RANK_BAD)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))


if __name__=='__main__':
    unittest.main(verbosity=2)
