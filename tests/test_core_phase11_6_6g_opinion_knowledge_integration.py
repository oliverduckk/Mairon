"""Real bounded opinion generation/verification integration with neutral works."""
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_recent_user_grounding_context, find_unknown_media_opinion_overreach_violations,
    should_verify_core_grounding, verify_core_grounded_draft,
)
from personality.conversation_policy import classify_conversation_policy
from research.media_grounding import build_failed_grounding_fallback, verify_media_draft
from test_core_milestone3b3a_public_shadow_integration import provider
from test_core_phase11_6_6g_opinion_knowledge import REQUEST, SUBJECT, packet


def core_positive():
    return {"supported": True, "relevant": True, "source_faithful": True, "unsupported_claims": []}


class Client:
    def __init__(self, drafts, *, media_supported=True):
        self.drafts = iter(drafts)
        self.calls = []
        self.media_supported = media_supported

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = "\n".join(message["content"] for message in kwargs["messages"]
                            if message["role"] == "system")
        if "INTERNAL claim-grounding verifier" in system:
            value = json.dumps(core_positive())
        elif "INTERNAL factual-support verifier" in system:
            numbered = next(message["content"] for message in kwargs["messages"]
                            if "PROPOSED MAIRON DRAFT TO VERIFY, NUMBERED BY CORE:" in message["content"])
            indexes = [int(index) for index in re.findall(r"(?m)^\s*S(\d+):", numbered)]
            supported = self.media_supported
            value = json.dumps({
                "supported": supported, "scope_compliant": True,
                "unsupported_claims": [] if supported else ["Unsupported work property"],
                "out_of_scope_claims": [],
                "sentence_assessments": [{"index": index, "supported": supported,
                                          "scope_compliant": True} for index in indexes],
            })
        else:
            value = next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=value, tool_calls=[]), done_reason="stop")

    def calls_of(self, marker):
        return [call for call in self.calls if any(marker in message["content"]
                for message in call["messages"] if message["role"] == "system")]

    def generation_calls(self):
        return [call for call in self.calls if not any("INTERNAL " in message["content"]
                for message in call["messages"] if message["role"] == "system")]


def fallback():
    path = ROOT / "src/ai/ollama_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "build_substantive_opinion_fallback")
    namespace = {"re": re, "build_recent_user_grounding_context": build_recent_user_grounding_context,
                 "build_spoiler_safe_discussion_fallback": lambda *args, **kwargs: None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[node.name]


def run(client, *, current=REQUEST, conversation=(), retained_media=None, overrides=None):
    function, namespace = provider()
    namespace.update({
        "classify_conversation_policy": classify_conversation_policy,
        "find_unknown_media_opinion_overreach_violations": find_unknown_media_opinion_overreach_violations,
        "should_verify_core_grounding": should_verify_core_grounding,
        "verify_core_grounded_draft": verify_core_grounded_draft,
        "build_substantive_opinion_fallback": fallback(),
        "build_failed_grounding_fallback": build_failed_grounding_fallback,
    })
    contract = AnswerContractRuntime(intent="share_opinion", authority="conversation",
                                    epistemic_mode="conversation", allow_new_factual_claims=False)
    if retained_media is not None:
        namespace.update({
            "prepare_spoiler_context": lambda **kwargs: {"domain_active": True, "title": SUBJECT},
            "should_research_media_turn": lambda **kwargs: True,
            "build_spoiler_safe_media_evidence": lambda **kwargs: "CORE PUBLIC-SOURCE EVIDENCE PACKET:\n" + json.dumps(retained_media),
            "verify_media_draft": verify_media_draft,
        })
        # Existing researched media authority is handled by its real dedicated
        # source verifier, rather than an ordinary USER-only verifier.
        contract = AnswerContractRuntime(intent="share_opinion", authority="media_research",
                                        epistemic_mode="conversation", allow_new_factual_claims=True)
    if overrides:
        namespace.update(overrides)
    with redirect_stdout(io.StringIO()):
        result = function(client, current, list(conversation), core_answer_contract=contract)
    return result


class OpinionKnowledgeProductionTests(unittest.TestCase):
    def test_unqualified_consumption_appraisal_is_retried_not_published(self):
        bad = "It's a decent read. The writing is consistent."
        good = "I don't know enough about Silver Orchard to give a real take."
        client = Client([bad, good])
        result = run(client)
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": good})
        self.assertNotIn(bad, [message["content"] for message in result[1]])
        self.assertEqual(len(client.generation_calls()), 2)

    def test_global_positive_cannot_erase_an_unknown_work_property(self):
        bad = "The prose is clear."
        good = "I don't know enough about Silver Orchard to judge its prose."
        client = Client([bad, good])
        result = run(client)
        self.assertEqual(result[0], good)
        self.assertNotIn(bad, [message["content"] for message in result[1]])

    def test_confidence_qualifier_does_not_grant_a_knowledge_basis(self):
        bad = "From what I know, the pacing is steady."
        good = "I don't know enough to give an informed opinion on Silver Orchard."
        result = run(Client([bad, good]))
        self.assertEqual(result[0], good)

    def test_every_retry_has_the_same_knowledge_ceiling(self):
        drafts = ["The prose is clear.", "The writing is consistent.", "The pacing is steady."]
        client = Client(drafts)
        result = run(client)
        self.assertNotIn(result[0], drafts)
        self.assertIn("don't know enough", result[0])
        self.assertNotIn(result[0], {"Got it.", "Yeah, fair enough."})
        self.assertEqual(len(client.generation_calls()), 3)
        self.assertTrue(all(text not in [message["content"] for message in result[1]] for text in drafts))

    def test_truthful_unknown_answer_publishes_naturally_without_research(self):
        good = "I don't know enough about Silver Orchard to give a proper take yet."
        calls = []
        client = Client([good])
        result = run(client, overrides={"build_spoiler_safe_media_evidence": lambda **kwargs: calls.append(kwargs)})
        self.assertEqual(result[0], good)
        self.assertEqual(result[2:], (None, None))
        self.assertFalse(calls)
        self.assertEqual(len(client.generation_calls()), 1)

    def test_supported_user_property_remains_available(self):
        good = "The writing is consistent."
        client = Client([good])
        result = run(client, conversation=[{"role": "user", "content": "Silver Orchard's writing is consistent."}])
        self.assertEqual(result[0], good)
        self.assertEqual(len(client.generation_calls()), 1)

    def test_user_topic_mention_does_not_license_a_property(self):
        bad = "The prose is clear."
        good = "I don't know enough about Silver Orchard to judge that."
        result = run(Client([bad, good]), conversation=[{"role": "user", "content": "I like Silver Orchard."}])
        self.assertEqual(result[0], good)

    def test_assistant_prior_property_does_not_create_familiarity(self):
        bad = "The prose is clear."
        good = "I don't know enough about Silver Orchard to judge it."
        result = run(Client([bad, good]), conversation=[{"role": "assistant", "content": "Silver Orchard's prose is clear."}])
        self.assertEqual(result[0], good)

    def test_real_admitted_media_packet_still_uses_existing_media_verifier(self):
        good = "The prose is clear."
        client = Client([good])
        result = run(client, retained_media=packet())
        self.assertEqual(result[0], good)
        self.assertEqual(len(client.generation_calls()), 1)
        self.assertEqual(len(client.calls_of("INTERNAL factual-support verifier")), 1)
        self.assertEqual(len(client.calls_of("INTERNAL claim-grounding verifier")), 0)

    def test_real_informed_work_appraisal_is_not_rejected_by_old_word_count(self):
        good = "The prose is clear. The pacing is steady. The dialogue is excellent."
        evidence = packet(content=SUBJECT + " has clear prose, steady pacing and excellent dialogue.")
        client = Client([good])
        result = run(client, retained_media=evidence)
        self.assertEqual(result[0], good)
        self.assertEqual(len(client.generation_calls()), 1)
        self.assertEqual(len(client.calls_of("INTERNAL factual-support verifier")), 1)

    def test_existing_source_verifier_can_still_reject_an_unrelated_property(self):
        bad = "The dialogue is excellent."
        client = Client([bad] * 3, media_supported=False)
        result = run(client, retained_media=packet())
        self.assertNotEqual(result[0], bad)
        self.assertIsInstance(result[0], str)
        self.assertEqual(len(client.generation_calls()), 2)
        self.assertEqual(len(client.calls_of("INTERNAL factual-support verifier")), 2)
        self.assertNotIn(bad, [message["content"] for message in result[1]])

    def test_rejected_readable_packet_does_not_grant_familiarity(self):
        bad = "The prose is clear."
        good = "I don't know enough about Silver Orchard to judge it."
        result = run(Client([bad, good]), retained_media=packet(rejected=True))
        self.assertEqual(result[0], good)

    def test_established_assistant_preference_stays_available(self):
        subject = {"kind": "overall_opinion", "key": "silver_orchard::overall_opinion", "title": SUBJECT}
        entry = {"key": subject["key"], "stance_text": "I still like Silver Orchard.", "kind": "overall_opinion"}
        text = entry["stance_text"]
        result = run(Client([text]), overrides={
            "classify_opinion_subject": lambda **kwargs: subject,
            "get_or_recover_opinion_entry": lambda **kwargs: entry,
        })
        self.assertEqual(result[0], text)

    def test_prior_stance_cannot_license_new_property_reasons(self):
        subject = {"kind": "overall_opinion", "key": "silver_orchard::overall_opinion", "title": SUBJECT}
        entry = {"key": subject["key"], "stance_text": "I like Silver Orchard.", "kind": "overall_opinion"}
        bad = "I like Silver Orchard because the prose is clear."
        good = "I still like Silver Orchard."
        result = run(Client([bad, good]), overrides={
            "classify_opinion_subject": lambda **kwargs: subject,
            "get_or_recover_opinion_entry": lambda **kwargs: entry,
        })
        self.assertEqual(result[0], good)

    def test_supported_user_polarity_cannot_be_overwritten_by_model_confidence(self):
        bad = "The prose is clear."
        good = "The prose is not clear."
        client = Client([bad, good])
        result = run(client, conversation=[{"role": "user", "content": "Silver Orchard's prose is not clear."}])
        self.assertEqual(result[0], good)
        self.assertNotIn(bad, [message["content"] for message in result[1]])
        self.assertEqual(len(client.generation_calls()), 2)

    def test_conditional_taste_reasoning_does_not_force_research(self):
        good = "If the character work is strong, I can enjoy a slower story."
        result = run(Client([good]))
        self.assertEqual(result[0], good)

    def test_approved_background_offer_remains_a_separate_early_return(self):
        offer = "I need a better basis. Would you like me to research it properly?"
        client = Client([])
        result = run(client, overrides={
            "build_pairwise_background_research_opportunity": lambda **kwargs: {"topic": SUBJECT},
            "build_background_research_offer_text": lambda _: offer,
            "_build_research_marker_result": lambda **kwargs: (kwargs["answer"], [], None, None),
            "uuid": SimpleNamespace(uuid4=lambda: "neutral-proposal"),
            "PENDING_RESEARCH_PROPOSAL_PREFIX": "pending",
        })
        self.assertEqual(result[0], offer)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
