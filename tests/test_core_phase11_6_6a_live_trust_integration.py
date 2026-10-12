"""Offline real-provider regressions for bounded live trust calibration."""
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

from test_core_phase11_6_6_trust_integration import (
    ScriptedClient, run as run_conversation, social, valid_core,
)
from test_core_milestone3b3a_public_shadow_integration import provider, research, contract, TEXT
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import build_conversational_relation_obligations
from research.public_factual_research import build_public_factual_authority_context, actual_read_url
from research.public_factual_grounding import (
    build_public_factual_generation_instruction, requires_public_factual_salvage_completion,
    verify_public_factual_salvage_completion, build_supported_current_lookup_fallback,
    build_failed_public_factual_fallback,
)


def completion(complete=False, outcome="incomplete"):
    return {
        "completed": complete, "outcome": outcome, "request_fulfilled": complete,
        "required_claim_assessments": [],
        "violations": [] if complete else ["current_predicate_missing"],
    }


class PublicClient:
    def __init__(self, drafts, assessments, completions):
        self.drafts = iter(drafts)
        self.assessments = iter(assessments)
        self.completions = iter(completions)
        self.calls = []
        self.generations = 0
        self.completion_calls = 0

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = "\n".join(m["content"] for m in kwargs["messages"] if m["role"] == "system")
        if "INTERNAL supported-subset answer-completion verifier" in system:
            self.completion_calls += 1
            value = next(self.completions)
            if isinstance(value, Exception):
                raise value
            content = json.dumps(value)
        elif "INTERNAL public-factual evidence verifier" in system:
            statuses = next(self.assessments)
            content = json.dumps({
                "supported": all(statuses), "unsupported_claims": [] if all(statuses) else ["unsubstantiated assertion"],
                "sentence_assessments": [
                    {"index": index, "supported": status} for index, status in enumerate(statuses, 1)
                ],
            })
        else:
            self.generations += 1
            content = next(self.drafts)
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")


def run_public(client, *, current="Does the service support queued export right now?",
               freshness=True, established=False, overrides=None):
    retained = copy.deepcopy(research())
    retained["freshness_sensitive"] = freshness
    retained["sources"][0]["currentness_established"] = established
    fn, namespace = provider(retained=retained)
    observations = []
    namespace.update({
        "build_public_factual_authority_context": build_public_factual_authority_context,
        "build_public_factual_generation_instruction": build_public_factual_generation_instruction,
        "actual_read_url": actual_read_url,
        "should_verify_public_factual_salvage_completion": requires_public_factual_salvage_completion,
        "verify_public_factual_salvage_completion": verify_public_factual_salvage_completion,
        "build_supported_current_lookup_fallback": build_supported_current_lookup_fallback,
        "build_failed_public_factual_fallback": build_failed_public_factual_fallback,
        "observe_public_factual_response": lambda **kwargs: observations.append(kwargs),
    })
    if overrides:
        namespace.update(overrides)
    log = io.StringIO()
    with redirect_stdout(log):
        result = fn(client, current, [], core_answer_contract=contract())
    return result, observations, log.getvalue()


class LiveTrustIntegrationTests(unittest.TestCase):
    def test_positive_social_summary_cannot_authorize_new_event_nominal(self):
        user = "Mara's handling of the archive handoff is annoying me."
        bad = "Mara's record tampering feels like betrayal."
        good = "You're clearly annoyed with how she handled it."
        client = ScriptedClient([bad, good], core=[valid_core(), valid_core()])
        result = run_conversation(client, user, social())
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1]["content"], good)
        self.assertNotIn(bad, [item["content"] for item in result[1]])

    def test_positive_social_summary_cannot_authorize_new_relationship_role(self):
        user = "You can query the references; you should not need me to explain them."
        bad = "Fine, I'll stop pretending you're my coach since I am failing without the lesson."
        good = "Fair point. I should check the reference myself instead of asking you to explain it."
        client = ScriptedClient([bad, good], core=[valid_core(), valid_core()])
        result = run_conversation(client, user, social())
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1]["content"], good)

    def test_explicit_user_event_can_support_a_specific_relation(self):
        user = "Mara's handling of the handoff annoyed me. Mara deleted the log."
        text = "Mara deleted the log."
        packet = build_conversational_relation_obligations(
            user_input=user, draft=text, core_answer_contract=social(),
        )
        verdict = valid_core() | {"relation_assessments": [
            {"index": item["index"], "supported": True, "source_id": "current_user",
             "source_quote": "Mara deleted the log", "source_predicate": "deleted"}
            for item in packet["obligations"]
        ]}
        result = run_conversation(ScriptedClient([text], core=[verdict]), user, social())
        self.assertEqual(result[0], text)

    def test_safe_emotional_mirror_uses_the_existing_single_verifier_call(self):
        client = ScriptedClient(["You're clearly frustrated with that response."], core=[valid_core()])
        result = run_conversation(client, "Mara's response is frustrating me.", social())
        self.assertEqual(result[0], "You're clearly frustrated with that response.")
        self.assertEqual(len(client.calls), 2)

    def test_thanks_direction_still_uses_no_semantic_call_for_plain_welcome(self):
        client = ScriptedClient(["You're welcome."])
        self.assertEqual(run_conversation(client, "thanks", social("acknowledge"))[0], "You're welcome.")
        self.assertEqual(len(client.calls), 1)

    def test_live_mechanism_negative_unit_overrides_positive_summary(self):
        bad = "Your valve's delayed response explains the pulsing."
        good = "The control unit remains plausible, but these observations do not establish the cause."
        client = ScriptedClient([bad, good], fidelity=[
            {"faithful": True, "violations": [], "mechanism_assessments": [
                {"sentence_index": 1, "kind": "unsupported_application", "supported": False,
                 "applicability_established": True, "user_witness": None}]},
            {"faithful": True, "violations": [], "mechanism_assessments": [
                {"sentence_index": 1, "kind": "none", "supported": True,
                 "applicability_established": False, "user_witness": None}]},
        ])
        ct = AnswerContractRuntime(intent="factual_question", authority="live_user_task",
                                   epistemic_mode="user_context_reasoning", allow_new_factual_claims=True)
        result = run_conversation(client, "The pump pulses only at low load; could the control unit still be involved?", ct)
        self.assertEqual(result[0], good)
        self.assertNotIn(bad, [item["content"] for item in result[1]])

    def test_live_mechanism_missing_units_do_not_publish_under_global_success(self):
        bad = "Your valve's response time explains this."
        good = "No specific mechanism is established by that observation."
        client = ScriptedClient([bad, good], fidelity=[
            {"faithful": True, "violations": []},
            {"faithful": True, "violations": [], "mechanism_assessments": [
                {"sentence_index": 1, "kind": "none", "supported": True,
                 "applicability_established": False, "user_witness": None}]},
        ])
        ct = AnswerContractRuntime(intent="factual_question", authority="live_user_task",
                                   epistemic_mode="user_context_reasoning", allow_new_factual_claims=True)
        self.assertEqual(run_conversation(client, "The pump pulses only at low load; what follows from that?", ct)[0], good)

    def test_supported_side_advice_cannot_publish_instead_of_current_predicate(self):
        bad = "The service currently supports export. If you use the legacy client, you could wait before enabling it."
        good = "I cannot verify whether queued export is available right now."
        client = PublicClient([bad, good], [[False, True], [True]], [completion()])
        result, observations, log = run_public(client)
        self.assertEqual(result[0], good)
        self.assertEqual(result[1][-1]["content"], good)
        self.assertEqual(client.completion_calls, 1)
        self.assertEqual(client.generations, 2)
        self.assertNotIn("If you use the legacy client, you could wait before enabling it.", [item["content"] for item in result[1]])
        self.assertIn("did not fulfill the required answer", log)
        self.assertIn("public factual sentence salvage did not complete the requested answer", log)

    def test_incomplete_subsets_exhaust_existing_retry_and_use_existing_fallback(self):
        bad = "The service currently supports export. If you use the legacy client, you could wait before enabling it."
        client = PublicClient([bad, bad], [[False, True], [False, True]], [completion(), completion()])
        result, observations, _ = run_public(client)
        self.assertEqual(result[0], build_failed_public_factual_fallback())
        self.assertEqual(client.generations, 2)
        self.assertEqual(client.completion_calls, 2)
        self.assertFalse(observations)
        self.assertNotIn(bad, [item["content"] for item in result[1]])

    def test_truthful_current_limitation_can_be_salvaged_unchanged(self):
        limitation = "I cannot verify whether queued export is available right now."
        bad = "The service currently supports export. " + limitation
        client = PublicClient([bad], [[False, True]], [completion(True, "bounded_limitation")])
        result, observations, _ = run_public(client)
        self.assertEqual(result[0], limitation)
        self.assertEqual(client.completion_calls, 1)
        self.assertEqual(client.generations, 1)
        self.assertFalse(observations, "salvage must remain outside generated-public common shadow")

    def test_supported_complete_current_subset_can_be_salvaged_unchanged(self):
        bad = TEXT + " Nearby customers celebrated it."
        client = PublicClient([bad], [[True, False]], [completion(True, "factual_answer")])
        result, observations, _ = run_public(client, established=True)
        self.assertEqual(result[0], TEXT)
        self.assertEqual(client.generations, 1)
        self.assertFalse(observations)

    def test_completion_exception_cannot_publish_incomplete_subset(self):
        bad = "The service currently supports export. If you use the legacy client, you could wait before enabling it."
        good = "I cannot verify whether queued export is available right now."
        client = PublicClient([bad, good], [[False, True], [True]], [RuntimeError("private exception payload")])
        result, _, log = run_public(client)
        self.assertEqual(result[0], good)
        self.assertNotIn("private exception payload", log)

    def test_wrong_completion_interface_type_cannot_publish_subset(self):
        bad = "The service currently supports export. If you use the legacy client, you could wait before enabling it."
        good = "I cannot verify whether queued export is available right now."
        client = PublicClient([bad, good], [[False, True], [True]], [])
        result, _, _ = run_public(client, overrides={"verify_public_factual_salvage_completion": lambda **kwargs: None})
        self.assertEqual(result[0], good)

    def test_malformed_completion_applicability_cannot_silently_skip_check(self):
        bad = "The service currently supports export. If you use the legacy client, you could wait before enabling it."
        good = "I cannot verify whether queued export is available right now."
        client = PublicClient([bad, good], [[False, True], [True]], [])
        result, _, _ = run_public(client, overrides={"should_verify_public_factual_salvage_completion": lambda **kwargs: None})
        self.assertEqual(result[0], good)

    def test_evergreen_simple_salvage_preserves_legacy_call_budget(self):
        bad = TEXT + " Nearby customers celebrated it."
        client = PublicClient([bad], [[True, False]], [])
        result, observations, _ = run_public(client, current="Which export capability does the service document?", freshness=False)
        self.assertEqual(result[0], TEXT)
        self.assertEqual(client.completion_calls, 0)
        self.assertEqual(len(client.calls), 2)
        self.assertFalse(observations)


if __name__ == "__main__":
    unittest.main()
