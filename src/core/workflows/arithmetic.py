from __future__ import annotations

from core.arithmetic import (
    ArithmeticEvaluationError,
    ArithmeticRequest,
    build_arithmetic_answer,
    evaluate_arithmetic_expression,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.workflow_result import (
    WorkflowResult,
)


def calculate_arithmetic(
    *,
    expression: str,
    operation: str,
    operands: str,
    display_expression: str,
) -> WorkflowResult:
    """
    Deterministically evaluate a Core-approved arithmetic expression.

    No shell, Python eval, model arithmetic, or arbitrary function execution is
    allowed here. The expression has already been narrowed by Core's arithmetic
    parser, and the evaluator independently permits arithmetic AST nodes only.
    """

    expression_value = str(
        expression
        or ""
    ).strip()

    operation_value = str(
        operation
        or "expression"
    ).strip().lower()

    display_value = str(
        display_expression
        or expression_value
    ).strip()

    packed_operands = str(
        operands
        or ""
    ).strip()

    operand_values = tuple(
        item.strip()
        for item in packed_operands.split(
            "|"
        )
        if item.strip()
    )

    request = ArithmeticRequest(
        expression=expression_value,
        operation=operation_value,
        operands=operand_values,
        display_expression=display_value,
        inherited=False,
    )

    try:
        result = evaluate_arithmetic_expression(
            expression_value
        )

    except ArithmeticEvaluationError as exc:
        return WorkflowResult(
            success=False,
            status="calculation_failed",
            error=str(
                exc
            ),
            data={
                "expression": expression_value,
                "operation": operation_value,
            },
        )

    answer_fact = build_arithmetic_answer(
        request=request,
        result=result,
    )

    evidence = EvidenceBundle(
        authority="core_arithmetic",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=answer_fact,
            provenance="core_arithmetic",
            confidence="verified",
            source_name="deterministic_arithmetic",
            data={
                "expression": expression_value,
                "operation": operation_value,
                "result": str(
                    result
                ),
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="calculated",
        answer_fact=answer_fact,
        evidence=evidence,
        data={
            "expression": expression_value,
            "operation": operation_value,
            "operands": list(
                operand_values
            ),
            "result": str(
                result
            ),
        },
    )
