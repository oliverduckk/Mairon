"""Shadow acceptance exercises real Core/provider paths without enforcement.

Provider functions are compiled from their production AST with inert globals,
as in the existing provider-boundary regressions. No model, tool, account,
benchmark or private integration is contacted.
"""
from __future__ import annotations

import ast
import copy
import io
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_shadow import (
    AcceptanceShadowRecord,
    acceptance_shadow_events,
    emit_shadow_record,
    observe_core_result,
    observe_limitation_response,
    observe_time_budget,
)
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus, CandidateOrigin
from core.answer_contract_runtime import (
    AnswerContractRuntime,
    coerce_answer_contract_runtime,
    contract_field_value,
)
from core.claim_grounding import (
    build_insufficient_user_context_fallback,
    build_verification_declined_fallback,
)
from research.public_factual_grounding import build_failed_public_factual_fallback
from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus
from core.orchestrator import MaironCore
from core.task_budget import resolve_time_budget
from core.workflows.arithmetic import calculate_arithmetic


def _contract(mode="insufficient_user_context", *, intent="factual_question"):
    return AnswerContractRuntime(
        intent=intent, authority="user_context", epistemic_mode=mode,
        allow_follow_up_question=True,
    )


def _reject(candidate):
    return AcceptanceDecision(
        status=AcceptanceStatus.REJECTED, evaluated_text=candidate.text,
        reasons=("Private evaluator detail which must not be logged",),
        violated_invariants=("evidence_authority",),
    )


def _provider_function(name):
    path = SRC / "ai" / "ollama_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return path, next(node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name == name)


def _provider_globals():
    """Inert setup dependencies; the contract, observer and fallback are real."""
    return {
        "ensure_background_research_worker_started": lambda: None,
        "split_static_and_turn_instructions": lambda value: ("runtime context", value),
        "coerce_answer_contract_runtime": coerce_answer_contract_runtime,
        "_core_contract_value": contract_field_value,
        "explicit_calendar_write_request": lambda value: False,
        "should_expose_model_cloud": lambda **kwargs: False,
        "strip_ephemeral_core_contracts": lambda messages: list(messages),
        "_latest_user_authored_message": lambda messages: None,
        "reconstruct_bounded_factual_followup": lambda *args: None,
        "source_provenance_research_query": lambda *args: None,
        "should_use_restricted_generation_context": lambda *args, **kwargs: False,
        "prepare_relationship_turn": lambda value: {},
        "classify_conversation_policy": lambda value: {},
        "prepare_spoiler_context": lambda **kwargs: {},
        "record_accepted_relationship_response": lambda **kwargs: None,
        "get_runtime_context": lambda: "runtime context",
        "build_verification_declined_fallback": build_verification_declined_fallback,
        "build_insufficient_user_context_fallback": build_insufficient_user_context_fallback,
        "build_failed_public_factual_fallback": build_failed_public_factual_fallback,
        "build_failed_public_advice_fallback": lambda **kwargs: "Legacy serious fallback.",
        "build_failed_public_opinion_fallback": lambda: "Legacy opinion fallback.",
        "observe_limitation_response": observe_limitation_response,
    }


def _compile_provider(name):
    path, function = _provider_function(name)
    namespace = _provider_globals()
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def _compile_provider_branch(function_name, predicate, *, publish_tail=False):
    """Execute an actual fallback branch, without replaying rejected model drafts."""
    path, function = _provider_function(function_name)
    matches = [node for node in ast.walk(function)
               if isinstance(node, ast.If) and predicate(ast.unparse(node.test))]
    if len(matches) > 1:
        matches = [node for node in matches if any(isinstance(part, ast.Return) for part in ast.walk(node))]
    if len(matches) != 1:
        raise AssertionError("Expected one production fallback branch")
    body = copy.deepcopy(matches[0].body)
    if publish_tail:
        # The unchanged production tail records and returns the selected answer.
        start = next(index for index, node in enumerate(function.body)
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "working_conversation"
                             for target in node.targets)
                     and index > len(function.body) // 2)
        body.extend(copy.deepcopy(function.body[start:]))
    function = ast.FunctionDef(
        name="run_branch", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
            kw_defaults=[], defaults=[]), body=body, decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = _provider_globals()
    namespace.update({"user_input": "The task-specific material was not supplied.",
                      "conversation": [], "core_answer_contract": _contract(),
                      "core_is_consequential_advice": False, "core_is_grounded_opinion": False,
                      "relationship_context": {}, "opinion_subject": None,
                      "public_research_result": {"success": False, "sources": [],
                                                 "failure_reason": "Required evidence is unavailable."},
                      "consequential_domain": "neutral", "grounded_research_evidence": None})
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["run_branch"], namespace


def _method_node(relative, class_name, method_name):
    path = SRC / relative
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(node for node in tree.body
                 if isinstance(node, ast.ClassDef) and node.name == class_name)
    return path, next(node for node in owner.body
                     if isinstance(node, ast.FunctionDef) and node.name == method_name)


def _execute_fragment(path, body, namespace):
    """Run unchanged production statements with inert surrounding dependencies."""
    module = ast.fix_missing_locations(ast.Module(body=copy.deepcopy(body), type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)


class ShadowIntegrationTests(unittest.TestCase):
    def _capture(self, action, *, result=None, error=None):
        candidates = []
        real_evaluate = CoreAcceptanceEvaluator.evaluate

        def evaluate(evaluator, candidate):
            candidates.append(candidate)
            if error is not None:
                raise error
            if result is not None:
                return result(candidate)
            return real_evaluate(evaluator, candidate)

        with patch.object(CoreAcceptanceEvaluator, "evaluate", evaluate):
            returned = action()
        self.assertEqual(len(candidates), 1)
        return returned, candidates[0]

    def test_arithmetic_real_core_path_constructs_supported_candidate(self):
        decision, candidate = self._capture(
            lambda: MaironCore().prepare_turn("add 23 and 19")
        )
        self.assertEqual(decision.direct_response, "The total is 42.")
        self.assertEqual(candidate.text, decision.direct_response)
        self.assertEqual(candidate.origin, CandidateOrigin.CRITICAL_CORE)
        self.assertEqual(candidate.contract.authority, "core_arithmetic")
        facts = candidate.evidence.authoritative_evidence
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].kind, EvidenceKind.CORE_RESULT)
        self.assertEqual(facts[0].provenance, "core_arithmetic")
        self.assertEqual(facts[0].data["result"], "42")
        self.assertEqual(decision.acceptance_shadow.decision.status, AcceptanceStatus.ACCEPTED)

    def test_rejected_shadow_never_changes_arithmetic_publication(self):
        decision, candidate = self._capture(
            lambda: MaironCore().prepare_turn("multiply 8 by 7"), result=_reject,
        )
        self.assertEqual(decision.direct_response, "The result is 56.")
        self.assertEqual(candidate.text, decision.direct_response)
        self.assertEqual(decision.acceptance_shadow.decision.status, AcceptanceStatus.REJECTED)
        self.assertIn("REJECTED", decision.acceptance_shadow.event)

    def test_evaluator_exception_never_changes_arithmetic_publication(self):
        decision, _ = self._capture(
            lambda: MaironCore().prepare_turn("subtract 9 from 40"),
            error=RuntimeError("private exception payload"),
        )
        self.assertEqual(decision.direct_response, "The result is 31.")
        self.assertTrue(decision.acceptance_shadow.evaluation_failed)
        self.assertIsNone(decision.acceptance_shadow.decision)
        self.assertNotIn("private exception payload", decision.acceptance_shadow.event)

    def test_evidence_adapter_failure_never_changes_arithmetic_publication(self):
        with patch("core.acceptance_shadow.normalize_core_evidence",
                   side_effect=ValueError("private adapter payload")):
            decision = MaironCore().prepare_turn("multiply 6 by 9")
        self.assertEqual(decision.direct_response, "The result is 54.")
        self.assertTrue(decision.acceptance_shadow.evaluation_failed)
        self.assertIsNone(decision.acceptance_shadow.decision)
        self.assertIn("EVALUATION_ERROR", decision.acceptance_shadow.event)
        self.assertNotIn("private adapter payload", decision.acceptance_shadow.event)

    def test_unsuccessful_arithmetic_is_not_promoted_to_verified_result(self):
        decision = MaironCore().prepare_turn("divide 8 by 0")
        self.assertFalse(decision.workflow_result.success)
        self.assertEqual(decision.direct_response, "I can't divide by zero.")
        self.assertIsNone(decision.acceptance_shadow)

    def test_time_budget_real_core_uses_structured_resolution(self):
        prompt = (
            "I have 50 minutes, walking 10 minutes, setup 15 minutes, "
            "reading 20 minutes. Does it fit?"
        )
        resolution = resolve_time_budget(prompt)
        self.assertIsNotNone(resolution)
        decision, candidate = self._capture(lambda: MaironCore().prepare_turn(prompt))
        self.assertEqual(decision.direct_response, resolution.answer)
        self.assertEqual(candidate.origin, CandidateOrigin.CRITICAL_CORE)
        facts = candidate.evidence.authoritative_evidence
        self.assertTrue(facts)
        self.assertTrue(all(item.kind == EvidenceKind.CORE_RESULT for item in facts))
        self.assertTrue(any("45" in str(item.data) for item in facts))

    def test_private_state_real_core_path_preserves_limitation(self):
        decision, candidate = self._capture(
            lambda: MaironCore().prepare_turn("What colour shirt am I wearing?")
        )
        self.assertEqual(decision.epistemic_route.mode, "private_state_uncertain")
        self.assertEqual(decision.direct_response,
                         "I can't see what you're wearing through this text chat, "
                         "so I don't know its colour or appearance.")
        self.assertTrue(candidate.limitations or candidate.evidence.uncertainty)
        self.assertTrue(any(item.kind == EvidenceKind.UNCERTAINTY
                            and item.status == EvidenceStatus.UNAVAILABLE
                            for item in candidate.evidence.evidence))
        self.assertFalse(any(item.kind == EvidenceKind.CORE_RESULT
                             for item in candidate.evidence.evidence))

    def test_valid_generic_missing_response_is_accepted_from_known_mode(self):
        record, candidate = self._capture(lambda: observe_limitation_response(
            text="Required user input is unavailable.",
            contract=_contract(), user_input="Please assess the unprovided material.",
            path="neutral.missing_input",
        ))
        self.assertEqual(record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertTrue(candidate.evidence.canonical)
        self.assertTrue(candidate.limitations or candidate.evidence.uncertainty)
        self.assertTrue(any(item.kind == EvidenceKind.UNCERTAINTY
                            for item in candidate.evidence.evidence))

    def test_answer_prose_never_becomes_limitation_evidence(self):
        published = "The missing material has twelve sections."
        record, candidate = self._capture(lambda: observe_limitation_response(
            text=published, contract=_contract(), user_input="The material was not supplied.",
            path="neutral.missing_input",
        ))
        self.assertNotEqual(record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertFalse(any(item.claim == published for item in candidate.evidence.evidence))
        self.assertFalse(any(item.kind == EvidenceKind.CORE_RESULT
                             for item in candidate.evidence.evidence))

    def test_assistant_dialogue_is_never_promoted_to_user_evidence(self):
        history = [
            {"role": "user", "content": "My parcel label is amber."},
            {"role": "assistant", "content": "Your parcel label is green."},
        ]
        original = copy.deepcopy(history)
        _, candidate = self._capture(lambda: observe_limitation_response(
            text="Required user input is unavailable.",
            contract=_contract(), user_input="The dimensions are unspecified.",
            conversation=history, path="neutral.missing_input",
        ))
        self.assertEqual(history, original)
        self.assertFalse(any(item.claim == history[1]["content"]
                             for item in candidate.evidence.authoritative_evidence))
        for item in candidate.evidence.evidence:
            if item.claim == history[1]["content"]:
                self.assertEqual(item.status, EvidenceStatus.REJECTED)
                self.assertEqual(item.kind, EvidenceKind.UNKNOWN)

    def test_current_and_live_user_context_are_distinct_and_snapshot_is_immutable(self):
        history = [{"role": "user", "content": "I prefer amber labels."}]
        _, candidate = self._capture(lambda: observe_limitation_response(
            text="Required user input is unavailable.",
            contract=_contract(), user_input="I have not supplied the measurements.",
            conversation=history, path="neutral.missing_input",
        ))
        kinds = {item.kind for item in candidate.evidence.authoritative_evidence}
        self.assertIn(EvidenceKind.CURRENT_USER_TURN, kinds)
        self.assertIn(EvidenceKind.LIVE_USER_FACT, kinds)
        history[0]["content"] = "I prefer green labels."
        self.assertTrue(any(item.claim == "I prefer amber labels."
                            for item in candidate.evidence.evidence))

    def test_candidate_origin_never_grants_authority(self):
        _, candidate = self._capture(lambda: observe_limitation_response(
            text="You are walking across the room.", contract=_contract(),
            user_input="The relevant information is missing.", path="neutral.missing_input",
        ))
        evaluator = CoreAcceptanceEvaluator()
        expected = evaluator.evaluate(candidate)
        self.assertNotEqual(expected.status, AcceptanceStatus.ACCEPTED)
        for origin in CandidateOrigin:
            self.assertEqual(evaluator.evaluate(candidate.with_origin(origin)), expected)

    def test_core_result_adapter_uses_existing_verified_result_not_published_text(self):
        workflow = calculate_arithmetic(expression="8 + 9", operation="add",
                                        operands="8|9", display_expression="8 + 9")
        runtime = _contract("deterministic_calculation", intent="calculate_arithmetic")
        runtime = replace(runtime, authority="core_arithmetic")
        record, candidate = self._capture(lambda: observe_core_result(
            text="The total is 99.", contract=runtime, evidence=workflow.evidence,
            path="neutral.core_result",
        ))
        self.assertEqual(candidate.evidence.authoritative_evidence[0].data["result"], "17")
        self.assertFalse(any(item.claim == candidate.text for item in candidate.evidence.evidence))
        self.assertNotEqual(record.decision.status, AcceptanceStatus.ACCEPTED)

    def test_unverified_deterministic_looking_prose_has_no_core_authority(self):
        evidence = EvidenceBundle(authority="core_arithmetic", success=True, evidence=[
            Evidence(claim="The total is 99.", provenance="model_output", confidence="verified")
        ])
        record, candidate = self._capture(lambda: observe_core_result(
            text="The total is 99.", contract=replace(_contract("deterministic_calculation"),
                                                authority="core_arithmetic"),
            evidence=evidence, path="neutral.core_result",
        ))
        self.assertFalse(any(item.kind == EvidenceKind.CORE_RESULT
                             for item in candidate.evidence.authoritative_evidence))
        self.assertNotEqual(record.decision.status, AcceptanceStatus.ACCEPTED)

    def test_shadow_event_contains_only_bounded_status_origin_and_invariants(self):
        record, _ = self._capture(lambda: observe_limitation_response(
            text="Private candidate material.", contract=_contract(),
            user_input="Private user material.", path="neutral.missing_input",
        ), result=_reject)
        self.assertIn("REJECTED", record.event)
        emitted = "\n".join(record.events)
        self.assertIn("evidence_authority", emitted)
        self.assertIn(CandidateOrigin.DETERMINISTIC_FALLBACK.value, record.event)
        self.assertNotIn("Private candidate material", emitted)
        self.assertNotIn("Private user material", emitted)
        self.assertNotIn("Private evaluator detail", emitted)
        self.assertTrue(all(len(event) <= 180 for event in record.events))

    def test_explicit_sink_failure_is_non_authoritative(self):
        record = observe_limitation_response(
            text="Required user input is unavailable.",
            contract=_contract(), user_input="The material is missing.", path="neutral.missing_input",
        )
        def broken_sink(event):
            raise RuntimeError("private sink detail")
        emit_shadow_record(record, broken_sink)

    def test_event_context_routes_only_current_shadow_events(self):
        events = []
        with acceptance_shadow_events(events.append):
            record = observe_limitation_response(
                text="Required user input is unavailable.",
                contract=_contract(), user_input="The material is missing.", path="neutral.missing_input",
            )
        self.assertEqual(events, [record.event])
        with redirect_stdout(io.StringIO()):
            observe_limitation_response(
                text="Required user input is unavailable.",
                contract=_contract(), user_input="Another material is missing.", path="neutral.missing_input",
            )
        self.assertEqual(events, [record.event])

    def test_nested_event_context_restores_outer_sink(self):
        outer, inner = [], []
        observe = lambda: observe_limitation_response(
            text="Required user input is unavailable.",
            contract=_contract(), user_input="The material is missing.", path="neutral.missing_input",
        )
        with acceptance_shadow_events(outer.append):
            observe()
            with acceptance_shadow_events(inner.append):
                observe()
            observe()
        self.assertEqual(len(outer), 2)
        self.assertEqual(len(inner), 1)

    def test_broken_context_sink_cannot_raise_or_expose_exception(self):
        def broken_sink(event):
            raise RuntimeError("private sink detail")
        with acceptance_shadow_events(broken_sink), redirect_stdout(io.StringIO()) as output:
            record = observe_limitation_response(
                text="Required user input is unavailable.",
                contract=_contract(), user_input="The material is missing.", path="neutral.missing_input",
            )
        self.assertIsNotNone(record)
        self.assertNotIn("private sink detail", output.getvalue())

    def test_provider_ingress_declined_real_function_publishes_unchanged(self):
        entry = _compile_provider("_get_response_impl")
        runtime = _contract("verification_declined")
        history = [{"role": "assistant", "content": "The unverified count is 700."}]
        original = copy.deepcopy(history)
        events = []
        with acceptance_shadow_events(events.append):
            returned, candidate = self._capture(lambda: entry(
                client=None, user_input="Give the current count without browsing.",
                instructions=runtime, conversation=history,
            ), result=_reject)
        expected = build_verification_declined_fallback()
        self.assertEqual(returned, (
            expected,
            history + [{"role": "system", "content": "runtime context"},
                       {"role": "user", "content": "Give the current count without browsing."},
                       {"role": "assistant", "content": expected}],
            None, None,
        ))
        self.assertEqual(history, original)
        self.assertEqual(candidate.epistemic_mode, "verification_declined")
        self.assertFalse(any(item.claim == history[0]["content"]
                             for item in candidate.evidence.authoritative_evidence))
        self.assertEqual(len(events), 2)
        self.assertIn("REJECTED", events[0])
        self.assertIn("evidence_authority", events[1])

    def test_direct_declined_real_function_survives_evaluator_failure(self):
        direct = _compile_provider("handle_direct_conversation")
        events = []
        with acceptance_shadow_events(events.append):
            returned, candidate = self._capture(lambda: direct(
                client=None, user_input="Do not verify the exact current count.", conversation=[],
                core_answer_contract=_contract("verification_declined"),
            ), error=RuntimeError("private evaluator exception"))
        self.assertEqual(returned[0], build_verification_declined_fallback())
        self.assertEqual(returned[1][-1], {"role": "assistant", "content": returned[0]})
        self.assertEqual(returned[2:], (None, None))
        self.assertTrue(candidate.limitations or candidate.evidence.uncertainty)
        self.assertEqual(len(events), 1)
        self.assertIn("EVALUATION_ERROR", events[0])
        self.assertNotIn("private evaluator exception", events[0])

    def test_real_missing_fallback_and_publication_tail_ignore_shadow_rejection(self):
        run_branch, namespace = _compile_provider_branch(
            "handle_direct_conversation",
            lambda condition: condition == "core_epistemic_mode == 'insufficient_user_context'",
            publish_tail=True,
        )
        namespace["user_input"] = "Please inspect the image; I forgot to upload it."
        expected = build_insufficient_user_context_fallback(namespace["user_input"])
        events = []
        with acceptance_shadow_events(events.append):
            returned, candidate = self._capture(run_branch, result=_reject)
        self.assertEqual(returned[0], expected)
        self.assertEqual(returned[1][-1]["content"], expected)
        self.assertEqual(returned[2:], (None, None))
        self.assertTrue(candidate.limitations or candidate.evidence.uncertainty)
        self.assertTrue(any(item.kind == EvidenceKind.UNCERTAINTY
                            for item in candidate.evidence.evidence))
        self.assertEqual(len(events), 2)
        self.assertIn("evidence_authority", events[1])

    def test_real_remaining_declined_fallback_preserves_output(self):
        run_branch, namespace = _compile_provider_branch(
            "handle_direct_conversation",
            lambda condition: condition == "core_epistemic_mode == 'verification_declined'",
            publish_tail=True,
        )
        namespace["core_answer_contract"] = _contract("verification_declined")
        returned, candidate = self._capture(run_branch, result=_reject)
        self.assertEqual(returned[0], build_verification_declined_fallback())
        self.assertEqual(returned[1][-1]["content"], returned[0])
        self.assertEqual(candidate.epistemic_mode, "verification_declined")

    def test_public_unavailable_fallback_only_shadows_pure_limitation(self):
        run_branch, namespace = _compile_provider_branch(
            "handle_direct_conversation",
            lambda condition: condition == "not public_factual_research_success",
        )
        namespace["build_stable_model_knowledge_fallback"] = lambda **kwargs: None
        namespace["core_answer_contract"] = replace(_contract("public_source_verified"),
                                                    authority="public_source")
        events = []
        with acceptance_shadow_events(events.append):
            returned, candidate = self._capture(run_branch, result=_reject)
        self.assertEqual(returned[0], build_failed_public_factual_fallback())
        self.assertEqual(returned[1][-1]["content"], returned[0])
        self.assertTrue(candidate.limitations or candidate.evidence.uncertainty)
        self.assertFalse(any(item.kind == EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION
                             for item in candidate.evidence.evidence))
        self.assertEqual(len(events), 2)
        self.assertIn("evidence_authority", events[1])

    def test_public_unavailable_does_not_migrate_stable_opinion_or_advice(self):
        run_branch, namespace = _compile_provider_branch(
            "handle_direct_conversation",
            lambda condition: condition == "not public_factual_research_success",
        )
        for scope in ("stable", "opinion", "advice"):
            with self.subTest(scope=scope):
                namespace["core_is_consequential_advice"] = scope == "advice"
                namespace["core_is_grounded_opinion"] = scope == "opinion"
                namespace["build_stable_model_knowledge_fallback"] = (
                    lambda **kwargs: "Legacy stable answer."
                )
                with patch.object(CoreAcceptanceEvaluator, "evaluate") as evaluate:
                    returned = run_branch()
                evaluate.assert_not_called()
                self.assertIn("Legacy", returned[0])

    def test_ordinary_core_paths_are_not_migrated(self):
        for prompt in ("hello", "recommend a board game", "What is a transistor?"):
            with self.subTest(prompt=prompt), patch.object(CoreAcceptanceEvaluator, "evaluate") as evaluate:
                decision = MaironCore().prepare_turn(prompt)
                evaluate.assert_not_called()
                self.assertIsNone(decision.acceptance_shadow)

    def test_time_budget_evidence_never_uses_rendered_answer(self):
        resolution = resolve_time_budget(
            "I have 60 minutes, walking 20 minutes, setup 10 minutes. Does it fit?"
        )
        self.assertIsNotNone(resolution)
        resolution = replace(resolution, answer="The remaining time is 900 minutes.")
        record, candidate = self._capture(lambda: observe_time_budget(
            text=resolution.answer, contract=_contract("user_premise_reasoning"),
            resolution=resolution, path="neutral.time_budget",
        ))
        self.assertNotEqual(record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertTrue(all(item.kind == EvidenceKind.CORE_RESULT
                            for item in candidate.evidence.authoritative_evidence))
        self.assertTrue(all(item.data["remaining_minutes"] == "30"
                            for item in candidate.evidence.authoritative_evidence))
        self.assertFalse(any(item.claim == resolution.answer
                             for item in candidate.evidence.evidence))

    def test_rejected_public_sources_remain_non_authoritative_in_shadow_bundle(self):
        rejected_fact = "The archive has twelve shelves."
        research = {
            "success": False, "sources": [{
                "source_id": "A1", "title": "Archive Survey",
                "url": "https://archive.example/survey",
                "content_excerpt": rejected_fact, "read_success": False,
                "accepted_as_evidence": False,
            }],
        }
        record, candidate = self._capture(lambda: observe_limitation_response(
            text=rejected_fact, contract=replace(_contract("public_source_verified"),
                                                authority="public_source"),
            user_input="Give the verified archive shelf count.",
            research_result=research, path="neutral.public_unavailable",
        ))
        self.assertNotEqual(record.decision.status, AcceptanceStatus.ACCEPTED)
        source = next(item for item in candidate.evidence.evidence
                      if item.kind == EvidenceKind.PUBLIC_SOURCE)
        self.assertEqual(source.status, EvidenceStatus.REJECTED)
        self.assertNotIn(source, candidate.evidence.authoritative_evidence)
        self.assertTrue(candidate.limitations or candidate.evidence.uncertainty)

    def test_wrong_evaluator_return_type_is_an_observable_shadow_error(self):
        events = []
        with acceptance_shadow_events(events.append), patch.object(
            CoreAcceptanceEvaluator, "evaluate", return_value="private invalid return"
        ):
            record = observe_limitation_response(
                text="Required user input is unavailable.", contract=_contract(),
                user_input="The material is missing.", path="neutral.missing_input",
            )
        self.assertTrue(record.evaluation_failed)
        self.assertIsNone(record.decision)
        self.assertEqual(len(events), 1)
        self.assertIn("EVALUATION_ERROR", events[0])
        self.assertNotIn("private invalid return", events[0])

    def test_diagnostic_invariants_are_allowlisted_without_reason_prose(self):
        decision = AcceptanceDecision(
            status=AcceptanceStatus.REJECTED, evaluated_text="private candidate",
            reasons=("private verifier detail",),
            violated_invariants=("private invariant prose", "evidence_authority"),
        )
        record = AcceptanceShadowRecord("neutral.test", CandidateOrigin.CRITICAL_CORE, decision)
        self.assertEqual(record.metadata["violated_invariants"],
                         ("unknown_invariant", "evidence_authority"))
        self.assertNotIn("private", record.event)
        self.assertIn("critical_core", record.event)
        self.assertLessEqual(len(record.event), 180)

    def test_simultaneous_request_contexts_do_not_cross_event_sinks(self):
        barrier = Barrier(2)

        def request(path):
            events = []
            with acceptance_shadow_events(events.append):
                barrier.wait(timeout=5)
                observe_limitation_response(
                    text="Required user input is unavailable.", contract=_contract(),
                    user_input="The material is missing.", path=path,
                )
            return events

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(request, "request.first")
            second = executor.submit(request, "request.second")
            first_events, second_events = first.result(timeout=10), second.result(timeout=10)
        self.assertEqual(len(first_events), 1)
        self.assertEqual(len(second_events), 1)
        self.assertIn("request.first", first_events[0])
        self.assertNotIn("request.second", first_events[0])
        self.assertIn("request.second", second_events[0])
        self.assertNotIn("request.first", second_events[0])

    def test_application_core_publication_forwards_record_without_enforcement(self):
        decision, _ = self._capture(
            lambda: MaironCore().prepare_turn("add 17 and 25"), result=_reject,
        )
        path, method = _method_node("application_service.py", "MaironApplication", "submit_text")
        branch = next(node for node in ast.walk(method)
                      if isinstance(node, ast.If)
                      and ast.unparse(node.test) == "core_decision.direct_response is not None")
        events, published = [], []
        namespace = {
            "self": SimpleNamespace(_emit_event=events.append,
                _finalize_direct_response=lambda **kwargs: published.append(kwargs)),
            "core_decision": decision, "emit_shadow_record": emit_shadow_record,
            "text": "add 17 and 25", "response_timer": object(), "channel_value": "text",
            "intent": decision.turn.intent, "authority": decision.epistemic_route.authority,
            "route_mode": decision.epistemic_route.mode, "workflow": "arithmetic",
            "agent_action": None,
        }
        body = copy.deepcopy(branch.body)
        # Preserve the actual return expression and arguments in a callable wrapper.
        wrapper = ast.FunctionDef(name="publish", args=ast.arguments(posonlyargs=[], args=[],
            kwonlyargs=[], kw_defaults=[], defaults=[]), body=body, decorator_list=[])
        _execute_fragment(path, [wrapper], namespace)
        namespace["publish"]()
        self.assertEqual([item["answer"] for item in published], [decision.direct_response])
        self.assertEqual(events, list(decision.acceptance_shadow.events))
        self.assertIn("REJECTED", events[0])

    def test_application_provider_context_forwards_event_and_preserves_router_result(self):
        from contextlib import nullcontext

        path, method = _method_node("application_service.py", "MaironApplication", "submit_text")
        context = next(node for node in ast.walk(method)
                       if isinstance(node, ast.With)
                       and any(isinstance(item.context_expr, ast.Call)
                               and isinstance(item.context_expr.func, ast.Name)
                               and item.context_expr.func.id == "acceptance_shadow_events"
                               for item in node.items))
        events = []
        legacy_result = SimpleNamespace(status="answered", answer="Legacy answer remains unchanged.")

        def route(*args):
            observe_limitation_response(
                text="The missing material has twelve sections.", contract=_contract(),
                user_input="The material is missing.", path="neutral.router_limit",
            )
            return legacy_result

        namespace = {
            "self": SimpleNamespace(_emit_event=events.append, session_id="neutral-session",
                local_ai=object(), cloud_ai=None, local_state=[], cloud_state=None),
            "channel_value": "text", "text": "The material is missing.",
            "turn_instructions": "contract instructions",
            "research_request_context": lambda **kwargs: nullcontext(),
            "acceptance_shadow_events": acceptance_shadow_events, "route_message": route,
        }
        _execute_fragment(path, [context], namespace)
        self.assertIs(namespace["result"], legacy_result)
        self.assertEqual(namespace["result"].answer, "Legacy answer remains unchanged.")
        self.assertEqual(len(events), 3)
        self.assertIn("REPLACEMENT_REQUIRED", events[0])
        emitted = "\n".join(events[1:])
        for invariant in ("evidence_authority", "uncertainty_preservation", "contract_completion"):
            self.assertIn(invariant, emitted)

    def test_terminal_core_publication_emits_diagnostic_then_original_answer(self):
        decision, _ = self._capture(
            lambda: MaironCore().prepare_turn("add 16 and 8"), result=_reject,
        )
        path = SRC / "main.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        branch = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.If)
                      and ast.unparse(node.test) == "core_decision.direct_response is not None")
        events, published = [], []
        namespace = {
            "core_decision": decision, "emit_shadow_record": emit_shadow_record,
            "print": events.append, "emit_final_response": lambda **kwargs: published.append(kwargs),
            "user_input": "add 16 and 8", "response_timer": object(),
            "local_state": [], "mairon_instructions": "runtime context",
            "append_visible_turn_to_model_history": lambda **kwargs: kwargs["current_state"] + [
                {"role": "user", "content": kwargs["user_input"]},
                {"role": "assistant", "content": kwargs["assistant_text"]},
            ],
        }
        # The real terminal branch ends in continue; one inert iteration preserves it.
        loop = ast.For(target=ast.Name(id="iteration", ctx=ast.Store()),
            iter=ast.Tuple(elts=[ast.Constant(value=1)], ctx=ast.Load()),
            body=copy.deepcopy(branch.body), orelse=[])
        _execute_fragment(path, [loop], namespace)
        self.assertEqual([item["answer"] for item in published], [decision.direct_response])
        self.assertEqual(namespace["local_state"][-1]["content"], decision.direct_response)
        self.assertEqual(events, list(decision.acceptance_shadow.events))

    def test_shadow_event_is_visible_through_existing_desktop_diagnostics(self):
        record = observe_core_result(
            text="The total is 42.", contract=replace(_contract("deterministic_calculation"),
                                                      authority="core_arithmetic"),
            evidence=calculate_arithmetic(expression="23 + 19", operation="add",
                operands="23|19", display_expression="23 + 19").evidence,
            path="neutral.core_result",
        )
        path, method = _method_node("desktop_app.py", "MaironDesktopApp", "_record_diagnostic_event")
        desktop = SimpleNamespace(_diagnostic_events=[], diagnostics_visible=False)
        namespace = {"MAX_DIAGNOSTIC_EVENTS": 12}
        _execute_fragment(path, [method], namespace)
        namespace["_record_diagnostic_event"](desktop, record.event)
        self.assertEqual(desktop._diagnostic_events, [record.event])

    def test_all_invariant_identifiers_survive_existing_desktop_event_limit(self):
        invariants = (
            "user_fact_consistency", "user_observation_support", "conditional_scope",
            "evidence_authority", "source_scope", "model_knowledge_not_proof",
            "serious_contract_tone", "uncertainty_preservation", "semantic_coverage",
            "required_claims", "origin_authority", "contract_completion",
        )
        decision = AcceptanceDecision(
            status=AcceptanceStatus.REJECTED, evaluated_text="private candidate",
            reasons=("private detail",), violated_invariants=invariants,
        )
        record = AcceptanceShadowRecord("x" * 48, CandidateOrigin.DETERMINISTIC_FALLBACK, decision)
        path, method = _method_node("desktop_app.py", "MaironDesktopApp", "_record_diagnostic_event")
        desktop = SimpleNamespace(_diagnostic_events=[], diagnostics_visible=False)
        namespace = {"MAX_DIAGNOSTIC_EVENTS": 12}
        _execute_fragment(path, [method], namespace)
        emit_shadow_record(record, lambda event: namespace["_record_diagnostic_event"](desktop, event))
        self.assertEqual(desktop._diagnostic_events, list(record.events))
        self.assertTrue(all(len(event) <= 180 for event in desktop._diagnostic_events))
        observed = ",".join(event.split(": ", 2)[2] for event in desktop._diagnostic_events[1:])
        self.assertEqual(set(observed.split(",")), set(invariants))
        self.assertNotIn("private", "\n".join(desktop._diagnostic_events))


if __name__ == "__main__":
    unittest.main()
