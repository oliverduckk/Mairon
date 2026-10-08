"""Bounded Core publication exercises actual orchestration/provider statements.

Provider AST execution uses inert surrounding setup, as in the existing
provider-boundary regressions. The publication boundary itself is real. No
model, network, account, benchmark, or live repository is contacted.
"""
from __future__ import annotations

import ast
import copy
import io
import sys
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from core import acceptance_publication as publication
from core import acceptance_shadow as shadow
from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_shadow import acceptance_shadow_events
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus, AcceptedSentence, AnswerCandidate, CandidateOrigin
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import build_insufficient_user_context_fallback, build_verification_declined_fallback
from core.evidence import EvidenceBundle, EvidenceKind, EvidenceStatus
from core.orchestrator import MaironCore
from core.task_budget import resolve_time_budget
from core.workflows.arithmetic import calculate_arithmetic
from research.public_factual_grounding import build_failed_public_factual_fallback

from test_core_milestone3b1_shadow_integration import _provider_function, _provider_globals


def _contract(mode="insufficient_user_context", *, authority="user_context", subject=None):
    return AnswerContractRuntime(
        intent="factual_question", authority=authority, epistemic_mode=mode,
        subject=subject, allow_follow_up_question=mode == "insufficient_user_context",
    )


def _arith_contract():
    return AnswerContractRuntime(
        intent="calculate_arithmetic", authority="core_arithmetic",
        epistemic_mode="deterministic_calculation",
    )


def _budget():
    result = resolve_time_budget(
        "I have 93 minutes, checking 19 minutes, assembly 23 minutes, filing 17 minutes. Does it fit?"
    )
    assert result is not None
    return result


def _nonaccepted(candidate, status=AcceptanceStatus.REJECTED):
    subset = (AcceptedSentence(1, candidate.text),) if status == AcceptanceStatus.SALVAGEABLE else ()
    return AcceptanceDecision(
        status=status, evaluated_text=candidate.text,
        reasons=("Private evaluation details",), violated_invariants=("evidence_authority",),
        accepted_sentences=subset,
    )


def _provider_namespace(records):
    namespace = _provider_globals()

    def publish(**kwargs):
        # Instrumentation only: execute the real publication boundary and keep
        # its result for assertions; do not substitute a decision or answer.
        result = publication.publish_limitation_response(**kwargs)
        records.append(result)
        return result

    namespace["publish_limitation_response"] = publish
    for name in ("emit_publication_record", "emit_acceptance_publication"):
        if hasattr(publication, name):
            namespace[name] = getattr(publication, name)
    return namespace


def _provider_entry(name, records):
    path, function = _provider_function(name)
    namespace = _provider_namespace(records)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name], namespace


def _provider_branch(condition, records, *, publish_tail=False):
    path, function = _provider_function("handle_direct_conversation")
    matches = [node for node in ast.walk(function)
               if isinstance(node, ast.If) and ast.unparse(node.test) == condition]
    if len(matches) > 1:
        matches = [node for node in matches if any(isinstance(part, ast.Return) for part in ast.walk(node))]
    if len(matches) != 1:
        raise AssertionError("Expected one actual production branch")
    body = copy.deepcopy(matches[0].body)
    if publish_tail:
        start = next(index for index, node in enumerate(function.body)
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "working_conversation"
                             for target in node.targets)
                     and index > len(function.body) // 2)
        body.extend(copy.deepcopy(function.body[start:]))
    selected = ast.FunctionDef(
        name="run_branch", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
            kw_defaults=[], defaults=[]), body=body, decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[selected], type_ignores=[]))
    namespace = _provider_namespace(records)
    namespace.update({
        "user_input": "Please assess the diagram. I have not provided the diagram.",
        "conversation": [], "core_answer_contract": _contract(),
        "core_is_consequential_advice": False, "core_is_grounded_opinion": False,
        "relationship_context": {}, "opinion_subject": None,
        "public_research_result": {"success": False, "sources": [], "failure_reason": "No admissible evidence"},
        "consequential_domain": "neutral", "grounded_research_evidence": None,
    })
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["run_branch"], namespace


class BoundedPublicationTests(unittest.TestCase):
    def _capture(self, action, response=None):
        candidates = []
        real = CoreAcceptanceEvaluator.evaluate

        def evaluate(evaluator, candidate):
            candidates.append(candidate)
            if isinstance(response, BaseException):
                raise response
            return response(candidate) if response else real(evaluator, candidate)

        with patch.object(CoreAcceptanceEvaluator, "evaluate", evaluate):
            returned = action()
        self.assertLessEqual(len(candidates), 2)
        return returned, candidates

    def _assert_accepted(self, result, expected):
        self.assertEqual(result.text, expected)
        self.assertEqual(result.record.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(result.record.outcome, "accepted")
        self.assertFalse(result.record.replacement_used)

    def _assert_bounded_failure(self, result, invalid):
        self.assertNotEqual(result.text, invalid)
        self.assertTrue(result.text.strip())
        self.assertIn(result.record.outcome, {"replaced", "fail_closed"})
        if result.record.outcome == "replaced":
            self.assertEqual(result.record.replacement_decision.status, AcceptanceStatus.ACCEPTED)
            self.assertEqual(result.record.replacement_decision.evaluated_text, result.text)

    def test_real_arithmetic_accepts_unchanged_actual_core_result(self):
        decision, candidates = self._capture(lambda: MaironCore().prepare_turn("multiply 13 by 7"))
        self.assertEqual(decision.direct_response, "The result is 91.")
        self.assertIsNone(decision.acceptance_shadow)
        self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(all(item.kind == EvidenceKind.CORE_RESULT
                            for item in candidates[0].evidence.authoritative_evidence))

    def test_real_arithmetic_corrupted_rendering_is_not_published(self):
        workflow = calculate_arithmetic(expression="13 * 7", operation="multiply", operands="13|7", display_expression="13 * 7")
        invalid = "The result is 901."
        workflow.answer_fact = invalid
        with patch("core.orchestrator.calculate_arithmetic", return_value=workflow):
            decision, candidates = self._capture(lambda: MaironCore().prepare_turn("multiply 13 by 7"))
        self.assertNotEqual(decision.direct_response, invalid)
        self.assertTrue(decision.direct_response.strip())
        self.assertEqual(candidates[0].evidence.authoritative_evidence[0].data["result"], "91")
        self.assertNotEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)

    def test_real_time_budget_valid_answer_is_unchanged(self):
        expected = _budget()
        decision, candidates = self._capture(lambda: MaironCore().prepare_turn(
            "I have 93 minutes, checking 19 minutes, assembly 23 minutes, filing 17 minutes. Does it fit?"
        ))
        self.assertEqual(decision.direct_response, expected.answer)
        self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(len(candidates), 1)
        self.assertIsNone(decision.acceptance_shadow)

    def test_real_time_budget_wrong_total_remaining_or_direction_is_replaced(self):
        valid = _budget()
        for invalid in (
            "The total is 60 minutes, leaving 34 minutes spare within the 93-minute budget.",
            "The total is 59 minutes, leaving 35 minutes spare within the 93-minute budget.",
            "The total is 59 minutes, exceeding the 93-minute budget by 34 minutes.",
        ):
            with self.subTest(invalid=invalid), patch("core.orchestrator.resolve_time_budget", return_value=replace(valid, answer=invalid)):
                decision, candidates = self._capture(lambda: MaironCore().prepare_turn("Does it fit?"))
            self.assertNotEqual(decision.direct_response, invalid)
            self.assertEqual(decision.acceptance_publication.outcome, "replaced")
            self.assertEqual(decision.acceptance_publication.replacement_decision.status, AcceptanceStatus.ACCEPTED)
            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0].contract, candidates[1].contract)
            self.assertEqual(candidates[0].evidence, candidates[1].evidence)

    def test_real_time_budget_delay_cannot_be_changed_by_rendering(self):
        core = MaironCore()
        core.prepare_turn("I have 93 minutes, checking 19 minutes, assembly 23 minutes, filing 17 minutes. Does it fit?")
        actual = core.prepare_turn("Assembly is delayed by 8 minutes. Does it fit?")
        self.assertEqual(actual.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        invalid = actual.direct_response.replace("8-minute delay", "9-minute delay")
        self.assertNotEqual(invalid, actual.direct_response)
        real_resolve = resolve_time_budget

        def corrupt(*args, **kwargs):
            result = real_resolve(*args, **kwargs)
            return replace(result, answer=invalid)

        fresh = MaironCore()
        fresh.prepare_turn("I have 93 minutes, checking 19 minutes, assembly 23 minutes, filing 17 minutes. Does it fit?")
        with patch("core.orchestrator.resolve_time_budget", side_effect=corrupt):
            decision, _ = self._capture(lambda: fresh.prepare_turn("Assembly is delayed by 8 minutes. Does it fit?"))
        self.assertNotEqual(decision.direct_response, invalid)
        self.assertEqual(decision.acceptance_publication.outcome, "replaced")

    def test_real_private_limitation_valid_response_is_unchanged(self):
        decision, candidates = self._capture(lambda: MaironCore().prepare_turn("What number am I thinking of?"))
        self.assertTrue(decision.direct_response.strip())
        self.assertEqual(decision.direct_response, candidates[0].text)
        self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertIsNone(decision.acceptance_shadow)
        self.assertTrue(any(item.kind == EvidenceKind.UNCERTAINTY for item in candidates[0].evidence.evidence))

    def test_real_private_path_cannot_publish_corrupted_candidate(self):
        invalid = "You are walking beside the desk."
        real_publish = publication.publish_limitation_response

        def corrupt_candidate(**kwargs):
            # Fault injection changes only the legacy candidate passed to the
            # real boundary. Its contract, state, evaluator and publication
            # handling still execute in the actual Core path.
            return real_publish(**{**kwargs, "text": invalid})

        with patch("core.orchestrator.publish_limitation_response", side_effect=corrupt_candidate):
            decision, candidates = self._capture(lambda: MaironCore().prepare_turn("What number am I thinking of?"))
        self.assertEqual(candidates[0].text, invalid)
        self.assertNotEqual(decision.direct_response, invalid)
        self.assertEqual(decision.acceptance_publication.outcome, "replaced")

    def test_actual_provider_missing_input_valid_and_corrupt_candidates(self):
        for corrupted in (False, True):
            with self.subTest(corrupted=corrupted):
                records = []
                run, namespace = _provider_branch("core_epistemic_mode == 'insufficient_user_context'", records, publish_tail=True)
                expected = build_insufficient_user_context_fallback(namespace["user_input"])
                invalid = "The absent measurement is 441 units."
                if corrupted:
                    namespace["build_insufficient_user_context_fallback"] = lambda value: invalid
                events = []
                with acceptance_shadow_events(events.append):
                    returned, candidates = self._capture(run)
                self.assertEqual(returned[1][-1]["content"], returned[0])
                self.assertEqual(returned[2:], (None, None))
                self.assertEqual(len(records), 1)
                if corrupted:
                    self._assert_bounded_failure(records[0], invalid)
                else:
                    self._assert_accepted(records[0], expected)
                self.assertEqual(returned[0], records[0].text)
                self.assertTrue(events)
                self.assertTrue(any(item.kind == EvidenceKind.UNCERTAINTY for item in candidates[0].evidence.evidence))

    def test_actual_provider_declined_ingress_and_direct_paths_enforce(self):
        for name in ("_get_response_impl", "handle_direct_conversation"):
            for corrupted in (False, True):
                with self.subTest(name=name, corrupted=corrupted):
                    records = []
                    entry, namespace = _provider_entry(name, records)
                    invalid = "The exact current reading is 441 units."
                    if corrupted:
                        namespace["build_verification_declined_fallback"] = lambda: invalid
                    keywords = {"instructions": _contract("verification_declined")} if name == "_get_response_impl" else {"core_answer_contract": _contract("verification_declined")}
                    returned, _ = self._capture(lambda: entry(
                        client=None, user_input="Give the current reading, but do not verify it.", conversation=[], **keywords,
                    ))
                    self.assertEqual(len(records), 1)
                    if corrupted:
                        self._assert_bounded_failure(records[0], invalid)
                    else:
                        self._assert_accepted(records[0], build_verification_declined_fallback())
                    self.assertEqual(returned[0], records[0].text)
                    self.assertEqual(returned[1][-1]["content"], returned[0])

    def test_actual_public_unavailable_fallback_valid_and_corrupt_candidates(self):
        for corrupted in (False, True):
            with self.subTest(corrupted=corrupted):
                records = []
                run, namespace = _provider_branch("not public_factual_research_success", records)
                namespace["build_stable_model_knowledge_fallback"] = lambda **kwargs: None
                namespace["core_answer_contract"] = _contract("public_source_verified", authority="public_source")
                invalid = "The reservoir capacity is 441 units."
                if corrupted:
                    namespace["build_failed_public_factual_fallback"] = lambda: invalid
                returned, candidates = self._capture(run)
                if corrupted:
                    self._assert_bounded_failure(records[0], invalid)
                else:
                    self._assert_accepted(records[0], build_failed_public_factual_fallback())
                self.assertEqual(returned[0], records[0].text)
                self.assertTrue(any(item.kind == EvidenceKind.UNCERTAINTY for item in candidates[0].evidence.evidence))

    def test_rejected_public_source_and_assistant_history_do_not_become_proof(self):
        invalid = "The reservoir capacity is 441 units."
        history = [{"role": "assistant", "content": invalid}]
        result, candidates = self._capture(lambda: publication.publish_limitation_response(
            text=invalid, contract=_contract("public_source_verified", authority="public_web"),
            user_input="Verify the reservoir capacity.", conversation=history,
            research_result={"success": False, "sources": [{
                "source_id": "R1", "title": "Reservoir Record", "url": "https://record.example/capacity",
                "content_excerpt": invalid, "read_success": False, "accepted_as_evidence": False,
            }]}, path="neutral.public_unavailable", emit=False,
        ))
        self._assert_bounded_failure(result, invalid)
        self.assertFalse(any(item.claim == invalid for item in candidates[0].evidence.authoritative_evidence))
        self.assertTrue(any(item.status == EvidenceStatus.REJECTED for item in candidates[0].evidence.evidence))
        self.assertEqual(history, [{"role": "assistant", "content": invalid}])

    def test_every_nonaccepted_status_prevents_original_publication(self):
        invalid = "The total is 999 minutes."
        for status in (AcceptanceStatus.REJECTED, AcceptanceStatus.SALVAGEABLE, AcceptanceStatus.REPLACEMENT_REQUIRED):
            with self.subTest(status=status):
                result, candidates = self._capture(lambda: publication.publish_time_budget(
                    text=invalid, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                    resolution=_budget(), emit=False,
                ), lambda candidate: _nonaccepted(candidate, status))
                self._assert_bounded_failure(result, invalid)
                self.assertEqual(result.record.outcome, "fail_closed")
                self.assertLessEqual(len(candidates), 2)

    def test_evaluator_exception_never_releases_original_candidate(self):
        invalid = "The absent measurement is 441 units."
        result, candidates = self._capture(lambda: publication.publish_limitation_response(
            text=invalid, contract=_contract(), user_input="I have not provided the diagram.",
            path="neutral.input", emit=False,
        ), RuntimeError("Private evaluator payload"))
        self._assert_bounded_failure(result, invalid)
        self.assertTrue(result.record.evaluation_failed)
        self.assertEqual(result.record.outcome, "fail_closed")
        self.assertLessEqual(len(candidates), 2)

    def test_malformed_and_stale_acceptance_results_cannot_authorize_publication(self):
        invalid = "The total is 999 minutes."
        for response in (
            lambda candidate: None,
            lambda candidate: {"status": "accepted", "evaluated_text": candidate.text},
            lambda candidate: SimpleNamespace(status=AcceptanceStatus.ACCEPTED, evaluated_text=candidate.text),
            lambda candidate: AcceptanceDecision(status=AcceptanceStatus.ACCEPTED, evaluated_text="A different candidate."),
        ):
            with self.subTest(response=response):
                result, _ = self._capture(lambda: publication.publish_time_budget(
                    text=invalid, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                    resolution=_budget(), emit=False,
                ), response)
                self._assert_bounded_failure(result, invalid)
                self.assertEqual(result.record.outcome, "fail_closed")

    def test_tampered_accepted_decision_is_revalidated_before_publication(self):
        valid = _budget()
        real = CoreAcceptanceEvaluator.evaluate
        for field, value in (("accepted_sentences", ()), ("metadata", {}), ("status", "unrecognized")):
            def tampered(candidate):
                decision = real(CoreAcceptanceEvaluator(), candidate)
                object.__setattr__(decision, field, value)
                return decision

            with self.subTest(field=field):
                result, _ = self._capture(lambda: publication.publish_time_budget(
                    text=valid.answer, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                    resolution=valid, emit=False,
                ), tampered)
                self._assert_bounded_failure(result, valid.answer)
                self.assertTrue(result.record.evaluation_failed)
                self.assertEqual(result.record.outcome, "fail_closed")

    def test_one_replacement_attempt_uses_same_contract_and_evidence(self):
        invalid = "The total is 999 minutes."
        real = publication._canonical_replacement
        with patch.object(publication, "_canonical_replacement", wraps=real) as replacement:
            result, candidates = self._capture(lambda: publication.publish_time_budget(
                text=invalid, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                resolution=_budget(), emit=False,
            ))
        self.assertEqual(replacement.call_count, 1)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].evidence, candidates[1].evidence)
        self.assertEqual(candidates[0].contract, candidates[1].contract)
        self._assert_bounded_failure(result, invalid)

    def test_replacement_construction_failure_does_not_retry_or_publish_original(self):
        invalid = "The total is 999 minutes."
        with patch.object(publication, "_canonical_replacement", side_effect=ValueError("Private renderer payload")) as replacement:
            result, candidates = self._capture(lambda: publication.publish_time_budget(
                text=invalid, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                resolution=_budget(), emit=False,
            ))
        self._assert_bounded_failure(result, invalid)
        self.assertEqual(replacement.call_count, 1)
        self.assertLessEqual(len(candidates), 1)

    def test_evidence_factory_failure_fails_closed_before_evaluation(self):
        invalid = "The result is 441."
        workflow = calculate_arithmetic(expression="13 * 7", operation="multiply", operands="13|7", display_expression="13 * 7")
        with patch("core.acceptance_shadow.normalize_core_evidence", side_effect=ValueError("Private evidence payload")), patch.object(CoreAcceptanceEvaluator, "evaluate") as evaluate:
            result = publication.publish_core_result(text=invalid, contract=_arith_contract(), evidence=workflow.evidence)
        evaluate.assert_not_called()
        self._assert_bounded_failure(result, invalid)

    def test_unsuccessful_arithmetic_bundle_cannot_publish_admissible_looking_result(self):
        workflow = calculate_arithmetic(expression="13 * 7", operation="multiply", operands="13|7", display_expression="13 * 7")
        evidence = replace(workflow.evidence, success=False)
        result = publication.publish_core_result(
            text=workflow.answer_fact, contract=_arith_contract(), evidence=evidence,
        )
        self._assert_bounded_failure(result, workflow.answer_fact)
        self.assertEqual(result.record.outcome, "fail_closed")

    def test_limitation_factory_failure_preserves_known_contract_limitation(self):
        invalid = "The unverified quantity is 441 units."
        for mode in ("insufficient_user_context", "verification_declined", "private_state_uncertain", "public_source_verified"):
            with self.subTest(mode=mode):
                runtime = _contract(mode, authority="public_web" if mode == "public_source_verified" else "user_context")
                keywords = dict(
                    contract=runtime, user_input="Please assess the diagram. I have not provided the diagram.",
                    conversation=(), user_history=(), failure_reason=None,
                    research_result={"success": False, "sources": []} if mode == "public_source_verified" else None,
                )
                with patch("core.acceptance_shadow._limitation_evidence", side_effect=ValueError("Private adapter payload")):
                    result = publication.publish_limitation_response(
                        text=invalid, **keywords, path="neutral.limitation", emit=False,
                    )
                self._assert_bounded_failure(result, invalid)
                self.assertTrue(result.record.evaluation_failed)
                evidence = shadow._limitation_evidence(**keywords)
                checked = CoreAcceptanceEvaluator().evaluate(AnswerCandidate(
                    text=result.text, origin=CandidateOrigin.CRITICAL_CORE,
                    contract=runtime, evidence=evidence,
                ))
                self.assertEqual(checked.status, AcceptanceStatus.ACCEPTED)

    def test_candidate_construction_failure_uses_only_verified_replacement(self):
        workflow = calculate_arithmetic(expression="13 * 7", operation="multiply", operands="13|7", display_expression="13 * 7")
        result, candidates = self._capture(lambda: publication.publish_core_result(
            text=None, contract=_arith_contract(), evidence=workflow.evidence,
        ))
        self.assertEqual(result.text, "The result is 91.")
        self.assertEqual(result.record.outcome, "replaced")
        self.assertTrue(result.record.evaluation_failed)
        self.assertEqual(len(candidates), 1)

    def test_invalid_contract_evidence_and_result_types_never_release_candidate(self):
        invalid = "The result is 441."
        workflow = calculate_arithmetic(expression="13 * 7", operation="multiply", operands="13|7", display_expression="13 * 7")
        calls = (
            lambda: publication.publish_core_result(text=invalid, contract=None, evidence=workflow.evidence),
            lambda: publication.publish_core_result(text=invalid, contract=_contract(), evidence=workflow.evidence),
            lambda: publication.publish_core_result(text=invalid, contract=_arith_contract(), evidence=None),
            lambda: publication.publish_time_budget(text=invalid, contract=_arith_contract(), resolution=object()),
            lambda: publication.publish_limitation_response(text=invalid, contract=_contract("stable_model_knowledge"),
                                                            user_input="Give a definition.", path="neutral.input", emit=False),
        )
        for call in calls:
            with self.subTest(call=call):
                result = call()
                self._assert_bounded_failure(result, invalid)

    def test_diagnostic_sink_failure_has_no_publication_authority(self):
        def broken(event):
            raise ValueError("Private diagnostic payload")

        valid = _budget()
        with acceptance_shadow_events(broken), redirect_stdout(io.StringIO()):
            result = publication.publish_time_budget(
                text=valid.answer, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                resolution=valid, emit=True,
            )
        self._assert_accepted(result, valid.answer)

    def test_diagnostic_emitter_failure_does_not_discard_accepted_answer(self):
        valid = _budget()
        with patch.object(publication, "emit_publication_record", side_effect=ValueError("Private emitter payload")):
            result = publication.publish_time_budget(
                text=valid.answer, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                resolution=valid, emit=True,
            )
        self._assert_accepted(result, valid.answer)

    def test_enforced_events_are_bounded_and_never_expose_private_prose(self):
        invalid = "Private candidate material is 999 minutes."
        result, _ = self._capture(lambda: publication.publish_time_budget(
            text=invalid, contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
            resolution=_budget(), emit=False,
        ), lambda candidate: _nonaccepted(candidate))
        emitted = "\n".join(result.record.events)
        self.assertNotIn(invalid, emitted)
        self.assertNotIn("Private evaluation details", emitted)
        self.assertTrue(all(len(event) <= 180 for event in result.record.events))
        self.assertNotIn("Acceptance shadow:", emitted)
        self.assertIn("REJECTED", emitted)
        self.assertIn("evidence_authority", emitted)

    def test_candidate_origin_does_not_change_decision_or_published_result(self):
        for invalid in (False, True):
            expected = None
            for origin in CandidateOrigin:
                with self.subTest(origin=origin, invalid=invalid):
                    valid = _budget()
                    result = publication.publish_time_budget(
                        text="The total is 999 minutes." if invalid else valid.answer,
                        contract=_contract("user_premise_reasoning", authority="user_turn_reasoning"),
                        resolution=valid, origin=origin, emit=False,
                    )
                    value = (result.text, result.record.decision, result.record.replacement_decision,
                             result.record.outcome, result.record.replacement_used)
                    if expected is None:
                        expected = value
                    self.assertEqual(value, expected)

    def test_unscoped_core_conversation_and_unsuccessful_arithmetic_are_not_enforced(self):
        for prompt in ("hello", "recommend a tabletop game", "What is a semiconductor?", "divide 8 by 0"):
            with self.subTest(prompt=prompt), patch("core.orchestrator.publish_core_result") as core_publish, patch("core.orchestrator.publish_time_budget") as budget_publish, patch("core.orchestrator.publish_limitation_response") as limitation_publish:
                decision = MaironCore().prepare_turn(prompt)
                core_publish.assert_not_called()
                budget_publish.assert_not_called()
                limitation_publish.assert_not_called()
                self.assertIsNone(decision.acceptance_publication)

    def test_unavailable_stable_opinion_and_consequential_fallbacks_are_not_migrated(self):
        for scope in ("stable", "opinion", "advice"):
            with self.subTest(scope=scope):
                records = []
                run, namespace = _provider_branch("not public_factual_research_success", records)
                namespace["core_is_consequential_advice"] = scope == "advice"
                namespace["core_is_grounded_opinion"] = scope == "opinion"
                namespace["build_stable_model_knowledge_fallback"] = lambda **kwargs: "Legacy stable explanation."
                returned = run()
                self.assertFalse(records)
                self.assertIn("Legacy", returned[0])

    def test_generated_public_media_and_general_answer_lanes_have_no_new_gate(self):
        allowed = {
            "provider_ingress_verification_declined",
            "direct_verification_declined",
            "direct_verification_declined_fallback",
            "direct_missing_input_fallback",
            "direct_public_evidence_unavailable",
        }
        found = set()
        for name in ("_get_response_impl", "handle_direct_conversation"):
            _, function = _provider_function(name)
            parents = {child: parent for parent in ast.walk(function) for child in ast.iter_child_nodes(parent)}
            for call in ast.walk(function):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                    continue
                if not call.func.id.startswith("publish_"):
                    continue
                if call.func.id not in {"publish_core_result", "publish_time_budget", "publish_limitation_response"}:
                    continue
                self.assertEqual(call.func.id, "publish_limitation_response")
                path = next(keyword.value for keyword in call.keywords if keyword.arg == "path")
                self.assertIsInstance(path, ast.Constant)
                self.assertIn(path.value, allowed)
                found.add(path.value)
                guards, node = [], call
                while node in parents:
                    node = parents[node]
                    if isinstance(node, ast.If):
                        guards.append(ast.unparse(node.test))
                self.assertTrue(any(
                    "verification_declined" in guard or "insufficient_user_context" in guard
                    or "not public_factual_research_success" in guard for guard in guards
                ))
        self.assertEqual(found, allowed)

    def test_outer_provider_boundary_preserves_enforced_result_and_history(self):
        records = []
        inner, namespace = _provider_entry("_get_response_impl", records)
        invalid = "The exact current reading is 441 units."
        namespace["build_verification_declined_fallback"] = lambda: invalid
        path, outer = _provider_function("get_response")
        lease = []
        outer_namespace = {
            "begin_interactive_turn": lambda: lease.append("begin"),
            "end_interactive_turn": lambda: lease.append("end"),
            "_get_response_impl": inner,
            "sanitise_visible_response": lambda user, answer: (answer, None),
            "replace_visible_answer_in_history": lambda history, old, new: history,
        }
        exec(compile(ast.Module(body=[outer], type_ignores=[]), str(path), "exec"), outer_namespace)
        returned = outer_namespace["get_response"](
            client=None, user_input="Give the current reading, but do not verify it.",
            instructions=_contract("verification_declined"), conversation=[],
        )
        self.assertEqual(lease, ["begin", "end"])
        self.assertNotEqual(returned[0], invalid)
        self.assertEqual(returned[0], records[0].text)
        self.assertEqual(returned[1][-1]["content"], returned[0])
        self.assertEqual(records[0].record.outcome, "replaced")


if __name__ == "__main__":
    unittest.main()
