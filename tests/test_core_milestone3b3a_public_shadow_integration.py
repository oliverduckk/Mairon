"""Execute the complete production direct-conversation function offline.

Unrelated runtime services are inert; retained research, packet construction,
public verifier, candidate adapter, common evaluator and history tail are real.
No live models, accounts, repositories or public services are contacted.
"""
from __future__ import annotations

import ast
import builtins
import copy
import io
import json
import sys
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
registry = types.ModuleType("tools.tool_registry")
registry.execute_tool = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Live tool forbidden"))
sys.modules.setdefault("tools.tool_registry", registry)

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_shadow import acceptance_shadow_events, observe_public_factual_response
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus, CandidateOrigin
from core.answer_contract_runtime import AnswerContractRuntime, contract_field_value, render_answer_contract
from core.evidence import EvidenceKind
from research.public_factual_grounding import verify_public_factual_draft
from research.public_factual_research import build_internal_public_factual_packet


TEXT = "The service supports queued export."
URL = "https://docs.vendor.example/service/export"


def research():
    source = {
        "title": "Service export documentation", "url": URL,
        "source_host": "docs.vendor.example", "source_quality": "primary",
        "authority_tier": "primary_official", "quality_eligible": True,
        "read_success": True, "accepted_as_evidence": True, "relevance_status": "accepted",
        "read_result": {"success": True, "url": URL, "content": TEXT},
    }
    return {"success": True, "query": "service export capability", "original_query": "service export capability",
            "sources": [source], "discovered_sources": [{"title": source["title"], "url": URL}],
            "freshness_sensitive": False, "official_documentation_required": False,
            "research_identity": {}, "query_resolution_required": False}


def contract(intent="factual_question", mode="public_source_verified", authority="public_web"):
    return AnswerContractRuntime(intent=intent, epistemic_mode=mode, authority=authority)


class Client:
    def __init__(self, *, first_unsupported=False):
        self.calls = []
        self.first_unsupported = first_unsupported
        self.verifications = 0

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if "format" in kwargs:
            self.verifications += 1
            supported = not (self.first_unsupported and self.verifications == 1)
            content = json.dumps({"supported": supported, "unsupported_claims": [] if supported else ["Unsupported assertion"],
                                  "sentence_assessments": [{"index": 1, "supported": supported}]})
        else:
            content = TEXT
        return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), done_reason="stop")


def provider(*, retained=None, observer=observe_public_factual_response):
    """Compile the whole unmodified production function with inert services."""
    path = ROOT / "src/ai/ollama_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "handle_direct_conversation")
    calls = {node.func.id for node in ast.walk(function) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)}
    namespace = {}
    for name in calls:
        if hasattr(builtins, name):
            continue
        if name.startswith("find_") and name != "find_active_research_job":
            namespace[name] = lambda *args, **kwargs: []
        elif name.startswith(("should_", "looks_like_", "is_")):
            namespace[name] = lambda *args, **kwargs: False
        else:
            namespace[name] = lambda *args, **kwargs: None
    namespace.update({
        "_core_contract_value": contract_field_value,
        "render_answer_contract": render_answer_contract,
        "CandidateOrigin": CandidateOrigin,
        "MAX_PERSONALITY_DRAFTS": 3,
        "GENERATION_TRUNCATION_VIOLATION": "generation stopped for length",
        "prepare_relationship_turn": lambda *args, **kwargs: {},
        "classify_conversation_policy": lambda *args, **kwargs: {},
        "prepare_spoiler_context": lambda *args, **kwargs: {},
        "build_restricted_generation_context": lambda messages: list(messages),
        "build_direct_generation_options": lambda *args, **kwargs: {},
        "build_runtime_output_budget": lambda *args, **kwargs: 256,
        "build_direct_context_window": lambda *args, **kwargs: 8192,
        "build_runtime_context_window": lambda **kwargs: kwargs["base_context_window"],
        "get_local_model_name": lambda: "replaceable-local-model",
        "get_runtime_context": lambda: "inert runtime context",
        "generation_debug_enabled": lambda: False,
        "generation_stopped_for_length": lambda *args, **kwargs: False,
        "_strip_internal_reasoning_markup": lambda value: value.strip(),
        "repair_core_restricted_draft": lambda **kwargs: kwargs["response_text"],
        "repair_factual_follow_up_tail": lambda text, **kwargs: (text, None),
        "repair_factual_personal_history_tail": lambda text, **kwargs: (text, None),
        "repair_factual_process_tail": lambda text, **kwargs: (text, None),
        "repair_unjustified_lexical_denial": lambda **kwargs: (kwargs["draft"], False),
        "gather_public_factual_research": lambda **kwargs: copy.deepcopy(retained if retained is not None else research()),
        "build_internal_public_factual_packet": build_internal_public_factual_packet,
        "verify_public_factual_draft": verify_public_factual_draft,
        "observe_public_factual_response": observer,
        "build_retry_instruction": lambda **kwargs: "Retry within the same evidence.",
        "build_public_factual_retry_instruction": lambda *args, **kwargs: "Retry within the same evidence.",
        "build_grounding_retry_instruction": lambda *args, **kwargs: "Retry within the same evidence.",
        "build_conversation_policy_text": lambda *args, **kwargs: "",
        "build_runtime_personality_instruction": lambda *args, **kwargs: "",
        "build_mairon_agency_modality_instruction": lambda *args, **kwargs: "",
        "build_core_spoiler_control_response": lambda *args, **kwargs: None,
        "assess_consequential_advice": lambda *args, **kwargs: SimpleNamespace(domain="general"),
        "build_contextual_opinion_research_query": lambda **kwargs: "service export capability",
        "build_consequential_research_query": lambda *args, **kwargs: "service export capability",
        "build_spoiler_guard_text": lambda *args, **kwargs: "",
        "_build_grounded_opinion_instruction": lambda: "",
        "build_consequential_advice_instruction": lambda **kwargs: "",
    })
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[function.name], namespace


class PublicShadowIntegrationTests(unittest.TestCase):
    def run_path(self, *, response=None, error=None, client=None, retained=None, override=None, current_contract=None, sink=None):
        run, namespace = provider(retained=retained)
        if override:
            namespace.update(override)
        candidates, events = [], []
        evaluate = CoreAcceptanceEvaluator.evaluate

        def capture(evaluator, candidate):
            candidates.append(candidate)
            if error:
                raise error
            if response is not None:
                if isinstance(response, AcceptanceStatus):
                    return AcceptanceDecision(response, candidate.text,
                        reasons=() if response == AcceptanceStatus.ACCEPTED else ("Private evaluator reasoning",),
                        violated_invariants=() if response == AcceptanceStatus.ACCEPTED else ("evidence_authority",))
                return response
            return evaluate(evaluator, candidate)

        prior = [{"role": "assistant", "content": "An unverified prior assertion with a substituted URL."}]
        with redirect_stdout(io.StringIO()), acceptance_shadow_events(sink or events.append), patch.object(CoreAcceptanceEvaluator, "evaluate", capture):
            result = run(client or Client(), "Which export capability does the service document?", prior,
                         core_answer_contract=current_contract or contract())
        return result, candidates, events

    def assert_legacy(self, result):
        self.assertEqual(result[0], TEXT)
        self.assertEqual(result[1][-1], {"role": "assistant", "content": TEXT})
        self.assertEqual(result[2:], (None, None))

    def test_real_successful_full_function_constructs_candidate_and_executes_evaluator(self):
        result, candidates, events = self.run_path()
        self.assert_legacy(result)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertTrue(candidate.evidence.canonical)
        self.assertEqual(candidate.origin, CandidateOrigin.GENERATED)
        self.assertTrue(candidate.evidence.authoritative_evidence)
        self.assertTrue(all(item.kind == EvidenceKind.PUBLIC_SOURCE for item in candidate.evidence.evidence))
        self.assertIn("Acceptance shadow: ACCEPTED", events[0])
        self.assertIn("public_generated_factual", events[0])

    def test_accepted_shadow_preserves_entire_legacy_return_and_history(self):
        baseline, _, _ = self.run_path(override={"observe_public_factual_response": lambda **kwargs: None})
        result, _, _ = self.run_path(response=AcceptanceStatus.ACCEPTED)
        self.assertEqual(result, baseline)

    def test_rejected_shadow_preserves_entire_legacy_return_and_history(self):
        baseline, _, _ = self.run_path(override={"observe_public_factual_response": lambda **kwargs: None})
        result, _, events = self.run_path(response=AcceptanceStatus.REJECTED)
        self.assertEqual(result, baseline)
        self.assertIn("REJECTED", events[0])

    def test_replacement_shadow_preserves_entire_legacy_return_and_history(self):
        result, _, events = self.run_path(response=AcceptanceStatus.REPLACEMENT_REQUIRED)
        self.assert_legacy(result)
        self.assertIn("REPLACEMENT_REQUIRED", events[0])

    def test_evaluator_exception_does_not_change_publication(self):
        result, _, events = self.run_path(error=RuntimeError("Private error payload"))
        self.assert_legacy(result)
        self.assertIn("EVALUATION_ERROR", events[0])
        self.assertNotIn("Private", " ".join(events))

    def test_wrong_decision_type_does_not_change_publication(self):
        result, _, events = self.run_path(response=object())
        self.assert_legacy(result)
        self.assertIn("EVALUATION_ERROR", events[0])

    def test_malformed_typed_decision_does_not_change_publication(self):
        malformed = object.__new__(AcceptanceDecision)
        object.__setattr__(malformed, "status", "accepted")
        object.__setattr__(malformed, "evaluated_text", TEXT)
        object.__setattr__(malformed, "violated_invariants", ())
        result, _, events = self.run_path(response=malformed)
        self.assert_legacy(result)
        self.assertIn("EVALUATION_ERROR", events[0])

    def test_adapter_exception_does_not_change_publication(self):
        with patch("core.public_answer_evidence.build_public_answer_candidate", side_effect=ValueError("Private adapter")):
            result, candidates, events = self.run_path()
        self.assert_legacy(result)
        self.assertFalse(candidates)
        self.assertIn("EVALUATION_ERROR", events[0])

    def test_diagnostic_sink_exception_does_not_change_publication(self):
        def fail(*args):
            raise RuntimeError("Private diagnostic failure")
        result, candidates, events = self.run_path(sink=fail)
        self.assert_legacy(result)
        self.assertEqual(len(candidates), 1)
        self.assertFalse(events)

    def test_diagnostic_emitter_exception_does_not_change_publication(self):
        def fail(*args):
            raise RuntimeError("Private diagnostic failure")
        with patch("core.acceptance_shadow.emit_shadow_record", side_effect=fail):
            result, _, _ = self.run_path()
        self.assert_legacy(result)

    def test_observer_itself_can_fail_without_changing_history(self):
        def fail(**kwargs):
            raise RuntimeError("Observer unavailable")
        result, _, _ = self.run_path(override={"observe_public_factual_response": fail})
        self.assert_legacy(result)

    def test_retry_final_full_draft_uses_final_verifier_and_retry_origin(self):
        result, candidates, events = self.run_path(client=Client(first_unsupported=True))
        self.assert_legacy(result)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].origin, CandidateOrigin.RETRY)
        self.assertTrue(candidates[0].evidence.metadata["public_verification"]["global_supported"])
        self.assertIn("ACCEPTED", events[0])

    def test_assistant_history_never_becomes_public_evidence(self):
        _, candidates, _ = self.run_path()
        self.assertFalse(any("substituted URL" in item.claim for item in candidates[0].evidence.evidence))

    def test_other_generation_contracts_do_not_use_public_shadow(self):
        for current in (
            contract(mode="stable_model_knowledge", authority="local_model_knowledge"),
            contract(intent="casual_conversation", mode="user_context", authority="live_conversation"),
            contract(intent="share_opinion", mode="subjective_opinion", authority="opinion"),
            contract(intent="recommendation_request", mode="model_knowledge", authority="local_model_knowledge"),
            contract(intent="share_opinion", mode="public_source_verified_opinion"),
            contract(intent="consequential_advice", mode="public_source_verified_advice"),
        ):
            with self.subTest(intent=current.intent, mode=current.epistemic_mode):
                result, candidates, events = self.run_path(current_contract=current)
                self.assert_legacy(result)
                self.assertFalse(candidates)
                self.assertFalse(events)

    def test_media_domain_does_not_use_new_public_shadow(self):
        result, candidates, events = self.run_path(override={
            "prepare_spoiler_context": lambda **kwargs: {"domain_active": True}})
        self.assert_legacy(result)
        self.assertFalse(candidates)
        self.assertFalse(events)

    def test_concurrent_request_diagnostics_are_isolated(self):
        barrier = Barrier(2)
        retained = research()
        packet = build_internal_public_factual_packet(retained)
        verified = verify_public_factual_draft(client=Client(), model="local", user_input="service export", draft=TEXT, research_evidence=packet)

        def work(origin):
            events = []
            with acceptance_shadow_events(events.append):
                barrier.wait(timeout=10)
                record = observe_public_factual_response(text=TEXT, contract=contract(), research_result=retained,
                    evidence_packet=packet, verification_result=verified, origin=origin)
            return record, events

        with ThreadPoolExecutor(max_workers=2) as pool:
            pairs = list(pool.map(work, (CandidateOrigin.GENERATED, CandidateOrigin.RETRY)))
        for (record, events), origin in zip(pairs, (CandidateOrigin.GENERATED, CandidateOrigin.RETRY)):
            self.assertEqual(record.origin, origin)
            self.assertEqual(sum("Acceptance shadow:" in event for event in events), 1)
            self.assertIn("origin=" + origin.value, events[0])
            self.assertNotIn(TEXT, events[0])
            self.assertNotIn(URL, events[0])


if __name__ == "__main__":
    unittest.main()
