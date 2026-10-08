"""Typed calibration preserves authority across shadow APIs and bounded publication.

Neutral result values and absent-input states exercise actual Core evidence
adapters. Candidate origins and diagnostic paths are varied independently of
the evidence, contract and wording; neither may determine validity.
"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_shadow import (
    acceptance_shadow_events, observe_core_result,
    observe_limitation_response, observe_time_budget,
)
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus, CandidateOrigin
from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    build_insufficient_user_context_fallback, build_verification_declined_fallback,
)
from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus
from core.evidence_normalization import combine_evidence, normalize_user_turn
from core.orchestrator import MaironCore
from core.task_budget import TimeBudgetResolution, resolve_time_budget
from core.workflows.arithmetic import calculate_arithmetic
from research.public_factual_grounding import build_failed_public_factual_fallback


def _budget_contract(**overrides):
    values = dict(
        task="determine whether supplied durations fit the stated time budget",
        intent="reason_from_supplied_premises", authority="user_turn_reasoning",
        epistemic_mode="user_premise_reasoning", speech_act="question",
    )
    values.update(overrides)
    return AnswerContractRuntime(**values)


def _limitation_contract(mode="insufficient_user_context", **overrides):
    values = dict(
        task="answer within the established evidence limitation",
        intent="factual_question", authority="user_context",
        epistemic_mode=mode, allow_follow_up_question=True,
    )
    values.update(overrides)
    return AnswerContractRuntime(**values)


class TypedCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = CoreAcceptanceEvaluator()

    def _capture(self, action):
        captured = []
        evaluate = CoreAcceptanceEvaluator.evaluate

        def record(evaluator, candidate):
            captured.append(candidate)
            return evaluate(evaluator, candidate)

        with patch.object(CoreAcceptanceEvaluator, "evaluate", record), redirect_stdout(io.StringIO()):
            observation = action()
        self.assertEqual(len(captured), 1)
        return observation, captured[0]

    def _assert_origins(self, candidate, accepted):
        baseline = self.evaluator.evaluate(candidate)
        self.assertIsInstance(baseline, AcceptanceDecision)
        self.assertEqual(baseline.status is AcceptanceStatus.ACCEPTED, accepted, baseline)
        self.assertEqual(baseline.evaluated_text, candidate.text)
        if accepted:
            self.assertFalse(baseline.violated_invariants)
        else:
            self.assertTrue(baseline.violated_invariants)
        for origin in CandidateOrigin:
            for diagnostic_path in ("neutral.first", "neutral.second", ""):
                with self.subTest(origin=origin, diagnostic_path=diagnostic_path):
                    moved = replace(
                        candidate, origin=origin,
                        validation_metadata={"path": diagnostic_path},
                    )
                    self.assertEqual(self.evaluator.evaluate(moved), baseline)
        return baseline

    def _budget(self, text, *, budget="72", items=(("checking", "17"), ("setup", "13"), ("filing", "19")),
                contract=None, resolution=None):
        if resolution is None:
            values = tuple((name, Decimal(amount)) for name, amount in items)
            resolution = TimeBudgetResolution(
                answer="This rendering is deliberately not evidence.",
                budget_minutes=Decimal(budget),
                used_minutes=sum((amount for _, amount in values), Decimal(0)),
                items=values,
            )
        observation, candidate = self._capture(lambda: observe_time_budget(
            text=text, contract=contract or _budget_contract(),
            resolution=resolution, path="neutral.duration",
        ))
        self.assertIsNotNone(observation.decision)
        self.assertTrue(candidate.evidence.canonical)
        self.assertTrue(candidate.evidence.authoritative_evidence)
        self.assertTrue(all(item.kind is EvidenceKind.CORE_RESULT
                            for item in candidate.evidence.authoritative_evidence))
        return candidate

    def _limitation(self, text, *, mode="insufficient_user_context", contract=None,
                    user_input="The required material has not been supplied.",
                    research_result=None, conversation=()):
        observation, candidate = self._capture(lambda: observe_limitation_response(
            text=text, contract=contract or _limitation_contract(mode),
            user_input=user_input, research_result=research_result,
            conversation=conversation, path="neutral.unavailable", emit=False,
        ))
        self.assertIsNotNone(observation.decision)
        limitations = [item for item in candidate.evidence.evidence
                       if item.kind is EvidenceKind.UNCERTAINTY]
        self.assertTrue(limitations)
        self.assertTrue(all(item.status is EvidenceStatus.UNAVAILABLE for item in limitations))
        return candidate

    def test_under_budget_equation_and_legacy_rendering_are_accepted(self):
        prompt = "I have 72 minutes, checking 17 minutes, setup 13 minutes, filing 19 minutes. Does it fit?"
        resolution = resolve_time_budget(prompt)
        self.assertIsNotNone(resolution)
        self._assert_origins(self._budget(resolution.answer, resolution=resolution), True)

    def test_under_budget_alternate_renderings_are_accepted(self):
        for text in (
            "The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget.",
            "Yes. The tasks take 49 minutes in total against a 72-minute limit, with 23 minutes remaining.",
            "17 + 13 + 19 = 49 minutes; that is 23 minutes under the 72-minute limit.",
        ):
            with self.subTest(text=text):
                self._assert_origins(self._budget(text), True)

    def test_over_budget_different_values_and_rendering_are_accepted(self):
        for text in (
            "No. 11 + 16 + 21 = 48 minutes against a 35-minute limit, so it is 13 minutes over.",
            "The total is 48 minutes, exceeding the 35-minute budget by 13 minutes.",
        ):
            with self.subTest(text=text):
                self._assert_origins(self._budget(text, budget="35", items=(
                    ("checking", "11"), ("setup", "16"), ("filing", "21"))), True)

    def test_exact_budget_different_values_and_rendering_are_accepted(self):
        for text in (
            "Yes, exactly. 16 + 30 = 46 minutes against your 46-minute limit, with no extra time left.",
            "The total is 46 minutes, exactly matching the 46-minute budget, with zero minutes remaining.",
        ):
            with self.subTest(text=text):
                self._assert_origins(self._budget(text, budget="46", items=(
                    ("checking", "16"), ("setup", "30"))), True)

    def test_decimal_budget_results_are_accepted(self):
        candidate = self._budget(
            "The total is 31.5 minutes, leaving 7 minutes spare within the 38.5-minute budget.",
            budget="38.5", items=(("checking", "12.5"), ("setup", "19")),
        )
        self._assert_origins(candidate, True)

    def test_wrong_used_total_is_not_accepted(self):
        self._assert_origins(self._budget(
            "The total is 48 minutes, leaving 23 minutes spare within the 72-minute budget."
        ), False)

    def test_wrong_remaining_value_is_not_accepted(self):
        self._assert_origins(self._budget(
            "The total is 49 minutes, leaving 24 minutes spare within the 72-minute budget."
        ), False)

    def test_wrong_budget_value_is_not_accepted(self):
        self._assert_origins(self._budget(
            "The total is 49 minutes, leaving 23 minutes spare within the 73-minute budget."
        ), False)

    def test_changed_comparison_direction_is_not_accepted(self):
        self._assert_origins(self._budget(
            "No. The total is 49 minutes, so it is 23 minutes over the 72-minute limit."
        ), False)

    def test_overrun_cannot_be_rendered_as_spare_time(self):
        self._assert_origins(self._budget(
            "Yes. The total is 48 minutes, leaving 13 minutes spare within the 35-minute budget.",
            budget="35", items=(("checking", "11"), ("setup", "16"), ("filing", "21")),
        ), False)

    def test_required_used_result_cannot_be_omitted(self):
        self._assert_origins(self._budget(
            "Yes, it fits, with 23 minutes spare."
        ), False)

    def test_required_remaining_result_cannot_be_omitted(self):
        self._assert_origins(self._budget(
            "Yes, the total of 49 minutes is within the 72-minute budget."
        ), False)

    def test_comparison_question_cannot_complete_required_asserted_result(self):
        self._assert_origins(self._budget(
            "The total is 49 minutes. It fits? The remaining time is 23 minutes.",
            contract=_budget_contract(allow_follow_up_question=True),
        ), False)

    def test_explicit_contract_result_obligation_is_honoured(self):
        runtime = _budget_contract(metadata={"result_obligations": ("used",)})
        self._assert_origins(self._budget("The total is 49 minutes.", contract=runtime), True)

    def test_required_claim_can_be_completed_by_same_typed_result_semantics(self):
        runtime = _budget_contract(required_claims=("The time used is 49 minutes.",))
        self._assert_origins(self._budget(
            "The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget.",
            contract=runtime,
        ), True)

    def test_numeric_equality_does_not_satisfy_an_unrelated_required_claim(self):
        runtime = _budget_contract(required_claims=("The parcel has 49 entries.",))
        self._assert_origins(self._budget(
            "The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget.",
            contract=runtime,
        ), False)

    def test_changed_item_premise_is_not_accepted_even_with_correct_total(self):
        self._assert_origins(self._budget(
            "Checking takes 18 minutes. The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget."
        ), False)

    def test_changed_equation_operand_is_not_accepted(self):
        self._assert_origins(self._budget(
            "18 + 12 + 19 = 49 minutes, leaving 23 minutes spare within the 72-minute budget."
        ), False)

    def test_additional_unsupported_consequence_is_not_accepted(self):
        self._assert_origins(self._budget(
            "The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget. Your client will approve the plan."
        ), False)

    def test_generic_parser_cannot_override_valid_typed_result_but_residual_stays_checked(self):
        self._assert_origins(self._budget(
            "17 + 13 + 19 = 49 minutes; that is 23 minutes under the 72-minute limit, and the machine is faultless."
        ), False)

    def test_real_core_under_over_exact_budget_paths_are_accepted(self):
        for prompt in (
            "I have 72 minutes, checking 17 minutes, setup 13 minutes, filing 19 minutes. Does it fit?",
            "I have 35 minutes, checking 11 minutes, setup 16 minutes, filing 21 minutes. Does it fit?",
            "I have 46 minutes, checking 16 minutes, setup 30 minutes. Does it fit?",
        ):
            with self.subTest(prompt=prompt):
                decision, candidate = self._capture(lambda: MaironCore().prepare_turn(prompt))
                self.assertEqual(candidate.text, decision.direct_response)
                self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
                self._assert_origins(candidate, True)

    def test_actual_correction_and_delay_fields_support_legacy_answer(self):
        core = MaironCore()
        initial = "I have 74 minutes, staging 12 minutes, transit 24 minutes, review 18 minutes. Does it fit?"
        core.prepare_turn(initial)
        core.prepare_turn("Correction: transit is 26 minutes not 24. Does it fit?")
        decision, candidate = self._capture(lambda: core.prepare_turn("Transit is delayed by 7 minutes. Does it fit?"))
        self.assertEqual(candidate.text, decision.direct_response)
        self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertTrue(any(item.data.get("delay_minutes") == "7" for item in candidate.evidence.authoritative_evidence))
        self._assert_origins(candidate, True)
        changed = replace(candidate, text=candidate.text.replace("7-minute delay", "8-minute delay"))
        self.assertNotEqual(changed.text, candidate.text)
        self._assert_origins(changed, False)

    def test_generic_truthful_missing_input_paraphrases_are_accepted(self):
        for text in (
            "I don't have enough information to determine that yet. Please provide the missing details.",
            "I can't determine that reliably from the information supplied, so I won't guess.",
            "The required input is missing, so I cannot assess that reliably yet.",
        ):
            with self.subTest(text=text):
                self._assert_origins(self._limitation(text), True)

    def test_existing_generic_availability_statement_remains_accepted(self):
        self._assert_origins(self._limitation("Required user input is unavailable."), True)

    def test_actual_missing_input_fallback_is_accepted_without_echoing_core_reason(self):
        prompt = "Please assess the plan, but I have not supplied the material."
        text = build_insufficient_user_context_fallback(prompt)
        candidate = self._limitation(text, user_input=prompt)
        self.assertNotEqual(text, candidate.evidence.uncertainty)
        self._assert_origins(candidate, True)

    def test_absent_value_cannot_be_invented(self):
        self._assert_origins(self._limitation("The missing measurement is 37 units."), False)

    def test_valid_limitation_prefix_does_not_authorize_absent_content(self):
        self._assert_origins(self._limitation(
            "I don't have enough information to determine that yet, but the missing document contains twelve sections."
        ), False)

    def test_false_observation_does_not_satisfy_missing_input_contract(self):
        self._assert_origins(self._limitation(
            "I inspected the supplied material. The measurement is 37 units."
        ), False)

    def test_access_denial_cannot_describe_unprovided_content(self):
        self._assert_origins(self._limitation(
            "I cannot inspect the diagram showing amber shapes.",
            user_input="The requested diagram has not been supplied.",
        ), False)

    def test_core_access_unavailability_does_not_prove_user_omission(self):
        runtime = _limitation_contract(subject="diagram")
        provided = "I have given you the diagram."
        self._assert_origins(self._limitation(
            "I cannot access the diagram from supplied context.",
            contract=runtime, user_input=provided,
        ), True)
        for text in (
            "I cannot determine that because you have not given me the diagram.",
            "The diagram is not provided.",
        ):
            with self.subTest(text=text):
                self._assert_origins(self._limitation(
                    text, contract=runtime, user_input=provided,
                ), False)

    def test_truthful_verification_declined_paraphrases_are_accepted(self):
        for text in (
            "Without verification I can't reliably give an exact current answer, and I won't guess.",
            "You asked me not to verify this, so I can't reliably provide the exact current answer.",
            build_verification_declined_fallback(),
        ):
            with self.subTest(text=text):
                self._assert_origins(self._limitation(
                    text, mode="verification_declined",
                    user_input="Give the exact current reading, but do not verify it.",
                ), True)

    def test_declined_verification_cannot_authorize_exact_current_answer(self):
        self._assert_origins(self._limitation(
            "The exact current reading is 271 units.", mode="verification_declined",
            user_input="Give the exact current reading, but do not verify it.",
        ), False)

    def test_verification_limitation_prefix_cannot_hide_unverified_exact_answer(self):
        self._assert_origins(self._limitation(
            "I can't verify this, but the exact current reading is 271 units.", mode="verification_declined",
            user_input="Give the exact current reading, but do not verify it.",
        ), False)

    def test_user_verification_constraint_cannot_be_erased(self):
        self._assert_origins(self._limitation(
            "I verified the current reading online, and it is 271 units.", mode="verification_declined",
            user_input="Give the exact current reading, but do not verify it.",
        ), False)

    def test_questioned_denial_cannot_complete_a_verification_limitation(self):
        for allow_question in (False, True):
            for text in ("I cannot verify the answer?", "The exact current answer is unknown?"):
                with self.subTest(text=text, allow_question=allow_question):
                    self._assert_origins(self._limitation(
                        text, mode="verification_declined",
                        contract=_limitation_contract("verification_declined", allow_follow_up_question=allow_question),
                        user_input="Give the exact current reading, but do not verify it.",
                    ), False)

    def test_nonasserted_no_guess_question_is_not_an_authorized_follow_up(self):
        self._assert_origins(self._limitation(
            "I cannot verify the answer. I will not guess?", mode="verification_declined",
            contract=_limitation_contract("verification_declined", allow_follow_up_question=False),
            user_input="Give the exact current reading, but do not verify it.",
        ), False)

    def test_truthful_public_evidence_unavailable_response_is_accepted(self):
        for text in (
            "I couldn't verify the requested answer from the available evidence, so I won't invent it.",
            build_failed_public_factual_fallback(),
        ):
            with self.subTest(text=text):
                self._assert_origins(self._limitation(
                    text, mode="public_source_verified",
                    contract=_limitation_contract("public_source_verified", authority="public_web"),
                    user_input="Verify the capacity of the named reservoir.",
                    research_result={"success": False, "sources": [], "error": "No admissible evidence"},
                ), True)

    def test_rejected_source_cannot_be_presented_as_verified_fact(self):
        candidate = self._limitation(
            "The reservoir capacity is 23 units.", mode="public_source_verified",
            contract=_limitation_contract("public_source_verified", authority="public_web"),
            user_input="Verify the capacity of the named reservoir.",
            research_result={"success": False, "sources": [], "error": "No admissible evidence"},
        )
        rejected = EvidenceBundle(
            authority="public_web", canonical=True, success=False,
            evidence=[Evidence(
                claim="The reservoir capacity is 23 units.", provenance="core_public_source",
                confidence="source_assertion", kind=EvidenceKind.PUBLIC_SOURCE,
                status=EvidenceStatus.REJECTED, authority_scope="retrieved_source_assertions",
                source_url="https://record.example/reservoir", evidence_id="rejected-record",
                data={"read_success": False},
            )],
        ).snapshot()
        self._assert_origins(replace(candidate, evidence=combine_evidence(
            candidate.evidence, rejected, authority="public_web")), False)

    def test_unavailable_evidence_caveat_cannot_authorize_factual_suffix(self):
        self._assert_origins(self._limitation(
            "I couldn't verify the answer, but the reservoir capacity is 23 units.",
            mode="public_source_verified",
            contract=_limitation_contract("public_source_verified", authority="public_web"),
            research_result={"success": False, "sources": []},
        ), False)

    def test_valid_private_state_limitation_remains_accepted(self):
        for text in (
            "I cannot observe that private state from this conversation, so I don't know.",
            "I don't know that private fact without you telling me.",
        ):
            with self.subTest(text=text):
                self._assert_origins(self._limitation(
                    text, mode="private_state_uncertain", user_input="What am I thinking?",
                ), True)

    def test_actual_core_private_state_limitation_is_accepted(self):
        for prompt in ("What number am I thinking of?", "What colour shirt am I wearing?"):
            with self.subTest(prompt=prompt):
                decision, candidate = self._capture(lambda: MaironCore().prepare_turn(prompt))
                self.assertEqual(candidate.text, decision.direct_response)
                self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
                self._assert_origins(candidate, True)

    def test_private_state_limitation_does_not_authorize_observation(self):
        self._assert_origins(self._limitation(
            "I can't observe that, but you are walking across the hall.",
            mode="private_state_uncertain", user_input="What am I thinking?",
        ), False)

    def test_private_denial_cannot_hide_an_asserted_state_in_subordinate_clause(self):
        self._assert_origins(self._limitation(
            "I cannot observe what you are doing now that the reading is stable.",
            mode="private_state_uncertain", user_input="Which word am I picturing?",
        ), False)

    def test_assistant_history_is_not_promoted_by_typed_availability(self):
        candidate = self._limitation(
            "The missing measurement is 37 units.",
            conversation=({"role": "assistant", "content": "The missing measurement is 37 units."},),
        )
        self.assertFalse(any(item.claim == candidate.text for item in candidate.evidence.authoritative_evidence))
        self._assert_origins(candidate, False)

    def test_result_evidence_cannot_override_explicit_current_user_fact(self):
        candidate = self._budget(
            "The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget. Your parcel is green."
        )
        evidence = combine_evidence(candidate.evidence, normalize_user_turn("My parcel is amber."),
                                    authority=candidate.evidence.authority)
        self._assert_origins(replace(candidate, evidence=evidence), False)

    def test_result_schema_does_not_grant_authority_to_wrong_kind_status_or_scope(self):
        candidate = self._budget(
            "The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget."
        )
        for changes in (
            {"kind": EvidenceKind.UNKNOWN},
            {"status": EvidenceStatus.REJECTED},
            {"authority_scope": "model_prose"},
            {"provenance": "model_output"},
            {"confidence": "unverified"},
        ):
            with self.subTest(changes=changes):
                evidence = replace(candidate.evidence, evidence=[
                    replace(item, **changes) for item in candidate.evidence.evidence
                ]).snapshot()
                self._assert_origins(replace(candidate, evidence=evidence), False)

    def test_inconsistent_core_result_data_does_not_establish_a_valid_answer(self):
        candidate = self._budget(
            "The total is 49 minutes, leaving 23 minutes spare within the 72-minute budget."
        )
        evidence = replace(candidate.evidence, evidence=[
            replace(item, data={**item.data, "used_minutes": "50"})
            for item in candidate.evidence.evidence
        ]).snapshot()
        self._assert_origins(replace(candidate, evidence=evidence), False)

    def test_existing_verified_arithmetic_core_answer_remains_accepted(self):
        decision, candidate = self._capture(lambda: MaironCore().prepare_turn("multiply 12 by 6"))
        self.assertEqual(decision.direct_response, "The result is 72.")
        self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self._assert_origins(candidate, True)

    def test_existing_large_arithmetic_rendering_and_ungrouped_equivalent_are_accepted(self):
        decision, candidate = self._capture(lambda: MaironCore().prepare_turn("add 1700 and 1900"))
        self.assertEqual(decision.direct_response, "The total is 3,600.")
        self.assertEqual(decision.acceptance_publication.decision.status, AcceptanceStatus.ACCEPTED)
        self._assert_origins(candidate, True)
        self._assert_origins(replace(candidate, text="The result is 3600."), True)
        self._assert_origins(replace(candidate, text="The total is 36,00."), False)

    def test_arithmetic_equal_result_paraphrase_is_accepted_and_change_is_not(self):
        workflow = calculate_arithmetic(expression="14 + 18", operation="add", operands="14|18", display_expression="14 + 18")
        contract = AnswerContractRuntime(
            intent="calculate_arithmetic", authority="core_arithmetic", epistemic_mode="deterministic_calculation",
            required_claims=(workflow.answer_fact,),
        )
        for text, accepted in (("The result is 32.", True), ("The result is 33.", False)):
            with self.subTest(text=text):
                _, candidate = self._capture(lambda: observe_core_result(
                    text=text, contract=contract, evidence=workflow.evidence,
                    path="neutral.calculation",
                ))
                self._assert_origins(candidate, accepted)

    def test_arithmetic_question_cannot_complete_required_asserted_result(self):
        workflow = calculate_arithmetic(expression="14 + 18", operation="add", operands="14|18", display_expression="14 + 18")
        contract = AnswerContractRuntime(
            intent="calculate_arithmetic", authority="core_arithmetic", epistemic_mode="deterministic_calculation",
            required_claims=(workflow.answer_fact,), allow_follow_up_question=True,
        )
        for text in ("The total is 32?", "32?"):
            with self.subTest(text=text):
                _, candidate = self._capture(lambda: observe_core_result(
                    text=text, contract=contract, evidence=workflow.evidence,
                    path="neutral.calculation",
                ))
                self._assert_origins(candidate, False)

    def test_operation_metadata_cannot_change_the_verified_arithmetic_expression(self):
        workflow = calculate_arithmetic(expression="14 + 18", operation="add", operands="14|18", display_expression="14 + 18")
        contract = AnswerContractRuntime(
            intent="calculate_arithmetic", authority="core_arithmetic", epistemic_mode="deterministic_calculation",
        )
        _, candidate = self._capture(lambda: observe_core_result(
            text="The product is 32.", contract=contract, evidence=workflow.evidence,
            path="neutral.calculation",
        ))
        changed = replace(candidate.evidence, evidence=[
            replace(item, data={**item.data, "operation": "multiply"})
            for item in candidate.evidence.evidence
        ]).snapshot()
        self._assert_origins(replace(candidate, evidence=changed), False)

    def test_numerical_premises_do_not_alias_beyond_default_numeric_precision(self):
        for operand, altered, other in (
            ("123456789012345678901234567890", "123456789012345678901234567891", "11"),
            ("0.123456789012345678901", "0.123456789012345678902", "1"),
        ):
            with self.subTest(operand=operand):
                expression = operand + " + " + other
                workflow = calculate_arithmetic(
                    expression=expression, operation="add", operands=operand + "|" + other,
                    display_expression=expression,
                )
                self.assertTrue(workflow.success)
                result = workflow.data["result"]
                contract = AnswerContractRuntime(
                    intent="calculate_arithmetic", authority="core_arithmetic",
                    epistemic_mode="deterministic_calculation",
                )
                _, candidate = self._capture(lambda: observe_core_result(
                    text=expression + " = " + result + ".", contract=contract,
                    evidence=workflow.evidence, path="neutral.precision",
                ))
                self._assert_origins(candidate, True)
                self._assert_origins(replace(
                    candidate, text=altered + " + " + other + " = " + result + ".",
                ), False)

    def test_static_shadow_path_does_not_change_evaluator_decision(self):
        text = "I can't determine that reliably from the information supplied, so I won't guess."
        records = []
        for path in ("neutral.input", "neutral.result", "neutral.other"):
            record, candidate = self._capture(lambda: observe_limitation_response(
                text=text, contract=_limitation_contract(),
                user_input="The required material was not supplied.", path=path, emit=False,
            ))
            self._assert_origins(candidate, True)
            records.append(record)
        self.assertEqual(records[0].decision, records[1].decision)
        self.assertEqual(records[0].decision, records[2].decision)
        self.assertNotEqual(records[0].metadata["path"], records[1].metadata["path"])

    def test_calibrated_real_budget_replaces_invalid_candidate_from_typed_result(self):
        valid = resolve_time_budget("I have 72 minutes, checking 17 minutes, setup 13 minutes, filing 19 minutes. Does it fit?")
        altered = replace(valid, answer="The total is 999 minutes.")
        captured = []
        evaluate = CoreAcceptanceEvaluator.evaluate

        def record(evaluator, candidate):
            captured.append(candidate)
            return evaluate(evaluator, candidate)

        with patch("core.orchestrator.resolve_time_budget", return_value=altered), patch.object(
            CoreAcceptanceEvaluator, "evaluate", record,
        ):
            decision = MaironCore().prepare_turn("Can these durations fit?")
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0].text, altered.answer)
        self.assertNotEqual(decision.direct_response, altered.answer)
        self.assertEqual(decision.direct_response, "The total is 49 minutes. The budget is 72 minutes. The remaining time is 23 minutes. It fits.")
        self.assertIsNone(decision.acceptance_shadow)
        publication = decision.acceptance_publication
        self.assertNotEqual(publication.decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(publication.decision.evaluated_text, altered.answer)
        self.assertEqual(publication.replacement_decision.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(publication.replacement_decision.evaluated_text, decision.direct_response)
        self.assertTrue(publication.replacement_used)
        self.assertEqual(publication.outcome, "replaced")
        self.assertNotIn("The total is 999", "\n".join(publication.events))
        for candidate in captured:
            self.assertTrue(all(item.data["used_minutes"] == "49" for item in candidate.evidence.authoritative_evidence))


if __name__ == "__main__":
    unittest.main()
