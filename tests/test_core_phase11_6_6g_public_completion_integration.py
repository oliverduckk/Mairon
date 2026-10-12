"""Run the actual bounded legacy public producer/retry/salvage offline."""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_core_milestone3b3a_public_shadow_integration import provider, research, contract
from test_core_phase11_6_6c_public_content_authority import witnesses
from research.public_factual_grounding import (
    build_failed_public_factual_fallback, build_public_factual_generation_instruction,
    build_supported_current_lookup_fallback, requires_public_factual_salvage_completion,
    verify_public_factual_salvage_completion,
)
from research.public_factual_research import actual_read_url, build_public_factual_authority_context

USER = "Why does the relay buzz when the supply changes?"
ADVICE = "Try inspecting the connector or changing the current limit."
EXPLANATION = "Intermittent contact interrupts power because the connection briefly opens."
LIMITATION = "I cannot verify why the relay buzzes from the available evidence."
BAD = "The relay buzzes because the latch is permanently damaged."


def completion(fulfilled=True, outcome="factual_answer"):
    return {"completed": fulfilled, "outcome": outcome, "request_fulfilled": fulfilled,
            "required_claim_assessments": [], "violations": [] if fulfilled else ["incomplete_request"]}


def assessment(statuses, claims=()):
    value = {"supported": all(statuses), "unsupported_claims": [] if all(statuses) else ["Unsupported cause"],
             "sentence_assessments": [{"index": i, "supported": status} for i, status in enumerate(statuses,1)]}
    if claims:
        value["claim_assessments"] = list(claims)
    return value


def claim_results(*items):
    result=[]
    for text, body, supported in items:
        for item in witnesses(text, body, supported=supported):
            item["index"] = len(result)+1
            result.append(item)
    return result


class PublicClient:
    def __init__(self, drafts, verifications, completions=()):
        self.drafts=iter(drafts)
        self.verifications=iter(verifications)
        self.completions=iter(completions)
        self.calls=[]
        self.generations=self.verifier_calls=self.completion_calls=0

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system="\n".join(m["content"] for m in kwargs["messages"] if m["role"]=="system")
        if "INTERNAL supported-subset answer-completion verifier" in system:
            self.completion_calls+=1
            value=next(self.completions)
            if isinstance(value,Exception):
                raise value
            content=json.dumps(value)
        elif "INTERNAL public-factual evidence verifier" in system:
            self.verifier_calls+=1
            content=json.dumps(next(self.verifications))
        else:
            self.generations+=1
            content=next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=content,tool_calls=[]),done_reason="stop")


def run(client, current=USER, body=EXPLANATION+" "+ADVICE):
    retained=copy.deepcopy(research())
    retained["query"]=retained["original_query"]="relay supply behaviour"
    retained["sources"][0]["title"]="Relay maintenance guide"
    retained["sources"][0]["read_result"]["content"]=body
    fn,namespace=provider(retained=retained)
    observations=[]
    namespace.update({
        "build_public_factual_authority_context":build_public_factual_authority_context,
        "build_public_factual_generation_instruction":build_public_factual_generation_instruction,
        "actual_read_url":actual_read_url,
        "should_verify_public_factual_salvage_completion":requires_public_factual_salvage_completion,
        "verify_public_factual_salvage_completion":verify_public_factual_salvage_completion,
        "build_supported_current_lookup_fallback":build_supported_current_lookup_fallback,
        "build_failed_public_factual_fallback":build_failed_public_factual_fallback,
        "observe_public_factual_response":lambda **kwargs:observations.append(kwargs),
    })
    log=io.StringIO()
    with redirect_stdout(log):
        result=fn(client,current,[],core_answer_contract=contract())
    return result,observations,log.getvalue()


class PublicExplanationIntegrationTests(unittest.TestCase):
    def test_full_draft_advice_only_cannot_publish_under_positive_support(self):
        client=PublicClient([ADVICE,LIMITATION],[assessment([True]),assessment([True])])
        result,observations,_=run(client)
        self.assertEqual(result[0],LIMITATION)
        self.assertEqual(result[1][-1]["content"],LIMITATION)
        self.assertNotIn(ADVICE,[m["content"] for m in result[1]])
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))
        self.assertEqual(len(observations),1)

    def test_two_advice_only_drafts_use_existing_bounded_public_fallback(self):
        client=PublicClient([ADVICE,ADVICE],[assessment([True]),assessment([True])])
        result,observations,_=run(client)
        self.assertEqual(result[0],build_failed_public_factual_fallback())
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,0))
        self.assertFalse(observations)
        self.assertNotIn(ADVICE,[m["content"] for m in result[1]])

    def test_supported_explanation_with_optional_advice_publishes_unchanged(self):
        good=EXPLANATION+" "+ADVICE
        client=PublicClient([good],[assessment([True,True],claim_results((EXPLANATION,EXPLANATION,True)))])
        result,observations,_=run(client)
        self.assertEqual(result[0],good)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))
        self.assertEqual(len(observations),1)

    def test_supported_explanation_without_literal_question_tokens_publishes(self):
        client=PublicClient([EXPLANATION],[assessment([True],claim_results((EXPLANATION,EXPLANATION,True)))])
        result,_,_=run(client)
        self.assertEqual(result[0],EXPLANATION)
        self.assertEqual(client.generations,1)

    def test_supported_advice_subset_cannot_publish_with_positive_completion(self):
        bad=BAD+" "+ADVICE
        client=PublicClient([bad,LIMITATION],[
            assessment([False,True],claim_results((BAD,None,False))),assessment([True]),
        ],[completion()])
        result,_,log=run(client)
        self.assertEqual(result[0],LIMITATION)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,1))
        self.assertNotIn(ADVICE,[m["content"] for m in result[1]])
        self.assertIn("did not fulfill the required answer",log)

    def test_repeated_advice_only_subsets_remain_bounded_and_fail_closed(self):
        bad=BAD+" "+ADVICE
        response=assessment([False,True],claim_results((BAD,None,False)))
        client=PublicClient([bad,bad],[response,response],[completion(),completion()])
        result,observations,_=run(client)
        self.assertEqual(result[0],build_failed_public_factual_fallback())
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(2,2,2))
        self.assertFalse(observations)

    def test_supported_explanatory_subset_can_still_be_salvaged(self):
        good=EXPLANATION+" "+ADVICE
        bad=good+" "+BAD
        client=PublicClient([bad],[assessment([True,True,False],claim_results(
            (EXPLANATION,EXPLANATION,True),(BAD,None,False)))],[completion()])
        result,observations,_=run(client)
        self.assertEqual(result[0],good)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,1))
        self.assertFalse(observations,"salvage remains outside common generated-public shadow lane")

    def test_truthful_limitation_subset_can_still_be_salvaged(self):
        bad=BAD+" "+LIMITATION
        client=PublicClient([bad],[assessment([False,True],claim_results((BAD,None,False)))],
                            [completion(outcome="bounded_limitation")])
        result,observations,_=run(client)
        self.assertEqual(result[0],LIMITATION)
        self.assertEqual(client.completion_calls,1)
        self.assertFalse(observations)

    def test_completion_exception_does_not_publish_advice_subset(self):
        bad=BAD+" "+ADVICE
        client=PublicClient([bad,LIMITATION],[assessment([False,True],claim_results((BAD,None,False))),
                                            assessment([True])],[RuntimeError("private payload")])
        result,_,log=run(client)
        self.assertEqual(result[0],LIMITATION)
        self.assertNotIn("private payload",log)
        self.assertEqual(client.generations,2)

    def test_plain_explain_request_cannot_bypass_subset_completion_applicability(self):
        bad=BAD+" "+ADVICE
        client=PublicClient([bad,LIMITATION],[assessment([False,True],claim_results((BAD,None,False))),
                                            assessment([True])],[completion()])
        result,_,_=run(client,current="Explain the intermittent supply.")
        self.assertEqual(result[0],LIMITATION)
        self.assertEqual(client.completion_calls,1)

    def test_non_explanatory_advice_request_retains_existing_behavior(self):
        client=PublicClient([ADVICE],[assessment([True])])
        result,observations,_=run(client,current="What should I try next?")
        self.assertEqual(result[0],ADVICE)
        self.assertEqual((client.generations,client.verifier_calls,client.completion_calls),(1,1,0))
        self.assertEqual(len(observations),1)

    def test_completion_violation_diagnostics_do_not_emit_draft_or_source_text(self):
        client=PublicClient([ADVICE,LIMITATION],[assessment([True]),assessment([True])])
        _,_,log=run(client)
        self.assertIn("explanation request received advice",log)
        self.assertNotIn(ADVICE,log)
        self.assertNotIn(EXPLANATION,log)


if __name__=="__main__":
    unittest.main()
