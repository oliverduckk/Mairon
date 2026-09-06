from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from typing import Optional, Sequence


NUMBER_PATTERN = (
    r"[+-]?"
    r"(?:"
    r"(?:\d{1,3}(?:,\d{3})+)"
    r"|(?:\d+(?:\.\d*)?)"
    r"|(?:\.\d+)"
    r")"
)

NUMBER_RE = re.compile(
    NUMBER_PATTERN
)

ARITHMETIC_REFERENT_RE = re.compile(
    r"\b(?:"
    r"those numbers|these numbers|the numbers|same numbers|them"
    r")\b",
    flags=re.IGNORECASE,
)

ARITHMETIC_RESULT_REFERENT_RE = re.compile(
    r"\b(?:it|that|the result|the total|that result|that total)\b",
    flags=re.IGNORECASE,
)

ADDITION_CUE_RE = re.compile(
    r"\b(?:add|addition|sum|total|together)\b",
    flags=re.IGNORECASE,
)

MULTIPLICATION_CUE_RE = re.compile(
    r"\b(?:multiply|multiplication|product)\b",
    flags=re.IGNORECASE,
)

SUBTRACTION_CUE_RE = re.compile(
    r"\b(?:subtract|subtraction|minus|difference)\b",
    flags=re.IGNORECASE,
)

DIVISION_CUE_RE = re.compile(
    r"\b(?:divide|division|divided)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ArithmeticRequest:
    expression: str
    operation: str
    operands: tuple[str, ...]
    display_expression: str
    inherited: bool = False


class ArithmeticEvaluationError(
    ValueError
):
    pass


def _parse_decimal(
    value: str,
) -> Decimal:
    text = str(
        value
        or ""
    ).strip().replace(
        ",",
        "",
    )

    try:
        return Decimal(
            text
        )

    except InvalidOperation as exc:
        raise ArithmeticEvaluationError(
            "That calculation contains an invalid number."
        ) from exc


def _canonical_decimal(
    value: Decimal,
) -> str:
    text = format(
        value,
        "f",
    )

    if "." in text:
        text = text.rstrip(
            "0"
        ).rstrip(
            "."
        )

    if text in {
        "",
        "-0",
    }:
        return "0"

    return text


def format_arithmetic_number(
    value: Decimal,
) -> str:
    text = _canonical_decimal(
        value
    )

    negative = text.startswith(
        "-"
    )

    if negative:
        text = text[
            1:
        ]

    if "." in text:
        integer_part, fractional_part = (
            text.split(
                ".",
                1,
            )
        )

    else:
        integer_part = text
        fractional_part = ""

    integer_value = int(
        integer_part
        or "0"
    )

    result = f"{integer_value:,}"

    if fractional_part:
        result += (
            "."
            + fractional_part
        )

    if negative:
        result = (
            "-"
            + result
        )

    return result


def _extract_numbers(
    text: str,
) -> list[Decimal]:
    values = []

    for match in NUMBER_RE.finditer(
        str(
            text
            or ""
        )
    ):
        values.append(
            _parse_decimal(
                match.group(
                    0
                )
            )
        )

    return values


def _build_request(
    operation: str,
    values: Sequence[Decimal],
    *,
    inherited: bool = False,
) -> Optional[
    ArithmeticRequest
]:
    operands = tuple(
        _canonical_decimal(
            value
        )
        for value in values
    )

    if len(
        operands
    ) < 2:
        return None

    symbols = {
        "add": " + ",
        "subtract": " - ",
        "multiply": " * ",
        "divide": " / ",
    }

    symbol = symbols.get(
        operation
    )

    if not symbol:
        return None

    expression = symbol.join(
        operands
    )

    return ArithmeticRequest(
        expression=expression,
        operation=operation,
        operands=operands,
        display_expression=expression,
        inherited=inherited,
    )


def _normalise_symbolic_expression(
    text: str,
) -> str:
    value = str(
        text
        or ""
    ).strip()

    value = value.replace(
        "×",
        "*",
    ).replace(
        "÷",
        "/",
    ).replace(
        "−",
        "-",
    )

    # Thousands separators are only stripped when they are inside a numeric
    # group. List separators such as "557, 528" therefore remain semantically
    # distinct from "1,000".
    value = re.sub(
        r"(?<=\d),(?=\d{3}\b)",
        "",
        value,
    )

    value = re.sub(
        r"(?<=\d)\s*[xX]\s*(?=[+-]?(?:\d|\.\d))",
        " * ",
        value,
    )

    value = re.sub(
        r"\bdivided\s+by\b",
        " / ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\btimes\b",
        " * ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\bplus\b",
        " + ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\bminus\b",
        " - ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"(?<=\d)\s*\^\s*(?=[+-]?(?:\d|\.\d))",
        " ** ",
        value,
    )

    value = re.sub(
        rf"({NUMBER_PATTERN})\s*%",
        r"(\1 / 100)",
        value,
    )

    value = re.sub(
        r"\bof\b",
        " * ",
        value,
        flags=re.IGNORECASE,
    )

    prefixes = [
        r"^\s*please\s+",
        r"^\s*can\s+you\s+",
        r"^\s*could\s+you\s+",
        r"^\s*would\s+you\s+",
        r"^\s*what(?:'s|\s+is)\s+",
        r"^\s*calculate\s+",
        r"^\s*compute\s+",
        r"^\s*work\s+out\s+",
        r"^\s*give\s+me\s+",
        r"^\s*tell\s+me\s+",
    ]

    changed = True

    while changed:
        changed = False

        for pattern in prefixes:
            updated = re.sub(
                pattern,
                "",
                value,
                flags=re.IGNORECASE,
            )

            if updated != value:
                value = updated
                changed = True

    return value.strip(
        " ?!."
    )


def _parse_symbolic_request(
    raw: str,
) -> Optional[
    ArithmeticRequest
]:
    expression = (
        _normalise_symbolic_expression(
            raw
        )
    )

    if not expression:
        return None

    if not re.search(
        r"(?:\+|-|\*|/|\*\*)",
        expression,
    ):
        return None

    # No names, function calls, indexing or arbitrary Python ever cross into
    # the evaluator. This is arithmetic syntax only.
    if not re.fullmatch(
        r"[0-9eE+\-*/().\s]+",
        expression,
    ):
        return None

    numbers = _extract_numbers(
        expression
    )

    if len(
        numbers
    ) < 2:
        return None

    operation = "expression"

    stripped = expression.replace(
        "**",
        "",
    )

    operator_types = set(
        re.findall(
            r"[+\-*/]",
            stripped,
        )
    )

    if operator_types == {
        "+"
    }:
        operation = "add"

    elif operator_types == {
        "-"
    }:
        operation = "subtract"

    elif operator_types == {
        "*"
    }:
        operation = "multiply"

    elif operator_types == {
        "/"
    }:
        operation = "divide"

    return ArithmeticRequest(
        expression=expression,
        operation=operation,
        operands=tuple(
            _canonical_decimal(
                value
            )
            for value in numbers
        ),
        display_expression=expression,
        inherited=False,
    )


def _active_arithmetic_operands(
    conversation_state,
) -> tuple[
    Decimal,
    ...,
]:
    if conversation_state is None:
        return ()

    if str(
        getattr(
            conversation_state,
            "active_intent",
            "",
        )
        or ""
    ) != "calculate_arithmetic":
        return ()

    active_entities = getattr(
        conversation_state,
        "active_entities",
        {},
    )

    if not isinstance(
        active_entities,
        dict,
    ):
        return ()

    packed = str(
        active_entities.get(
            "arithmetic_operands",
            "",
        )
        or ""
    ).strip()

    if not packed:
        return ()

    values = []

    for item in packed.split(
        "|"
    ):
        item = item.strip()

        if not item:
            continue

        try:
            values.append(
                _parse_decimal(
                    item
                )
            )

        except ArithmeticEvaluationError:
            return ()

    return tuple(
        values
    )


def _active_arithmetic_result(
    conversation_state,
) -> Optional[
    Decimal
]:
    """
    Recompute the previous verified arithmetic result from Core-owned state.

    We intentionally do not trust prior assistant prose as a result source.
    The active arithmetic expression was authored/validated by Core, so it can
    be evaluated again deterministically for deictic follow-ups such as
    "double it".
    """

    if conversation_state is None:
        return None

    if str(
        getattr(
            conversation_state,
            "active_intent",
            "",
        )
        or ""
    ) != "calculate_arithmetic":
        return None

    active_entities = getattr(
        conversation_state,
        "active_entities",
        {},
    )

    if not isinstance(
        active_entities,
        dict,
    ):
        return None

    expression = str(
        active_entities.get(
            "arithmetic_expression",
            "",
        )
        or ""
    ).strip()

    if not expression:
        return None

    try:
        return evaluate_arithmetic_expression(
            expression
        )

    except ArithmeticEvaluationError:
        return None


def _extract_result_follow_up_request(
    raw: str,
    conversation_state,
) -> Optional[
    ArithmeticRequest
]:
    text = str(
        raw
        or ""
    ).strip()

    if not text:
        return None

    previous_result = (
        _active_arithmetic_result(
            conversation_state
        )
    )

    if previous_result is None:
        return None

    if not ARITHMETIC_RESULT_REFERENT_RE.search(
        text
    ):
        return None

    # --------------------------------------------------
    # Common shorthand transformations.
    # --------------------------------------------------

    if re.fullmatch(
        r"\s*(?:please\s+)?double\s+(?:it|that|the result|the total)\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    ):
        return _build_request(
            "multiply",
            (
                previous_result,
                Decimal(
                    2
                ),
            ),
            inherited=True,
        )

    if re.fullmatch(
        r"\s*(?:please\s+)?triple\s+(?:it|that|the result|the total)\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    ):
        return _build_request(
            "multiply",
            (
                previous_result,
                Decimal(
                    3
                ),
            ),
            inherited=True,
        )

    if re.fullmatch(
        r"\s*(?:please\s+)?(?:halve|half)\s+(?:it|that|the result|the total)\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    ):
        return _build_request(
            "divide",
            (
                previous_result,
                Decimal(
                    2
                ),
            ),
            inherited=True,
        )

    if re.fullmatch(
        r"\s*(?:please\s+)?square\s+"
        r"(?:it|that|the result|the total)\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    ):
        value = _canonical_decimal(
            previous_result
        )

        return ArithmeticRequest(
            expression=(
                f"{value} ** 2"
            ),
            operation="power",
            operands=(
                value,
                "2",
            ),
            display_expression=(
                f"{value} ^ 2"
            ),
            inherited=True,
        )

    if re.fullmatch(
        r"\s*(?:please\s+)?cube\s+"
        r"(?:it|that|the result|the total)\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    ):
        value = _canonical_decimal(
            previous_result
        )

        return ArithmeticRequest(
            expression=(
                f"{value} ** 3"
            ),
            operation="power",
            operands=(
                value,
                "3",
            ),
            display_expression=(
                f"{value} ^ 3"
            ),
            inherited=True,
        )

    power_match = re.fullmatch(
        rf"\s*(?:please\s+)?(?:raise\s+)?"
        rf"(?:it|that|the result|the total)\s+"
        rf"(?:to\s+(?:the\s+)?)?"
        rf"(?:power\s+of\s+)?"
        rf"({NUMBER_PATTERN})"
        rf"(?:st|nd|rd|th)?"
        rf"(?:\s+power)?\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    )

    if power_match:
        exponent = _parse_decimal(
            power_match.group(
                1
            )
        )

        if exponent != exponent.to_integral_value():
            return None

        value = _canonical_decimal(
            previous_result
        )

        exponent_value = _canonical_decimal(
            exponent
        )

        return ArithmeticRequest(
            expression=(
                f"{value} ** {exponent_value}"
            ),
            operation="power",
            operands=(
                value,
                exponent_value,
            ),
            display_expression=(
                f"{value} ^ {exponent_value}"
            ),
            inherited=True,
        )

    # --------------------------------------------------
    # Explicit operations against the previous verified result.
    # --------------------------------------------------

    multiply_match = re.fullmatch(
        rf"\s*(?:please\s+)?multiply\s+"
        rf"(?:it|that|the result|the total)\s+by\s+"
        rf"({NUMBER_PATTERN})\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    )

    if multiply_match:
        return _build_request(
            "multiply",
            (
                previous_result,
                _parse_decimal(
                    multiply_match.group(
                        1
                    )
                ),
            ),
            inherited=True,
        )

    divide_match = re.fullmatch(
        rf"\s*(?:please\s+)?divide\s+"
        rf"(?:it|that|the result|the total)\s+by\s+"
        rf"({NUMBER_PATTERN})\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    )

    if divide_match:
        return _build_request(
            "divide",
            (
                previous_result,
                _parse_decimal(
                    divide_match.group(
                        1
                    )
                ),
            ),
            inherited=True,
        )

    add_match = re.fullmatch(
        rf"\s*(?:please\s+)?add\s+"
        rf"({NUMBER_PATTERN})\s+to\s+"
        rf"(?:it|that|the result|the total)\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    )

    if add_match:
        return _build_request(
            "add",
            (
                previous_result,
                _parse_decimal(
                    add_match.group(
                        1
                    )
                ),
            ),
            inherited=True,
        )

    subtract_match = re.fullmatch(
        rf"\s*(?:please\s+)?subtract\s+"
        rf"({NUMBER_PATTERN})\s+from\s+"
        rf"(?:it|that|the result|the total)\s*[.!?]*",
        text,
        flags=re.IGNORECASE,
    )

    if subtract_match:
        return _build_request(
            "subtract",
            (
                previous_result,
                _parse_decimal(
                    subtract_match.group(
                        1
                    )
                ),
            ),
            inherited=True,
        )

    return None


def _extract_follow_up_request(
    raw: str,
    conversation_state,
) -> Optional[
    ArithmeticRequest
]:
    text = str(
        raw
        or ""
    ).strip()

    values = _active_arithmetic_operands(
        conversation_state
    )

    if len(
        values
    ) < 2:
        return None

    if not ARITHMETIC_REFERENT_RE.search(
        text
    ):
        # Narrow correction continuation:
        # "No, I meant addition" can inherit the last Core-owned operands.
        if not re.search(
            r"\b(?:i\s+meant|meant)\s+"
            r"(?:addition|subtraction|multiplication|division)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return None

    operation = None

    if ADDITION_CUE_RE.search(
        text
    ):
        operation = "add"

    elif MULTIPLICATION_CUE_RE.search(
        text
    ):
        operation = "multiply"

    elif SUBTRACTION_CUE_RE.search(
        text
    ):
        operation = "subtract"

    elif DIVISION_CUE_RE.search(
        text
    ):
        operation = "divide"

    if operation is None:
        return None

    # "Subtract/divide those six numbers" has order semantics that need more
    # explicit wording. Addition and multiplication are safe across a list.
    if (
        operation
        in {
            "subtract",
            "divide",
        }
        and len(
            values
        ) != 2
    ):
        return None

    return _build_request(
        operation,
        values,
        inherited=True,
    )


def extract_arithmetic_request(
    raw: str,
    conversation_state=None,
) -> Optional[
    ArithmeticRequest
]:
    """
    Recognise unambiguous everyday arithmetic deterministically.

    This intentionally stays narrower than a general natural-language maths
    parser. Ambiguous syntax returns None rather than inviting Core to guess.
    """

    text = str(
        raw
        or ""
    ).strip()

    if not text:
        return None

    # --------------------------------------------------
    # Addition / sum / total
    # --------------------------------------------------

    if (
        re.search(
            r"^\s*(?:please\s+)?(?:add|sum)\b",
            text,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"\b(?:sum|total)\s+of\b",
            text,
            flags=re.IGNORECASE,
        )
    ):
        request = _build_request(
            "add",
            _extract_numbers(
                text
            ),
        )

        if request is not None:
            return request

    # --------------------------------------------------
    # Subtraction
    # --------------------------------------------------

    subtract_from = re.search(
        rf"\bsubtract\s+({NUMBER_PATTERN})\s+"
        rf"from\s+({NUMBER_PATTERN})\b",
        text,
        flags=re.IGNORECASE,
    )

    if subtract_from:
        first = _parse_decimal(
            subtract_from.group(
                1
            )
        )

        second = _parse_decimal(
            subtract_from.group(
                2
            )
        )

        return _build_request(
            "subtract",
            (
                second,
                first,
            ),
        )

    # --------------------------------------------------
    # Multiplication
    # --------------------------------------------------

    if (
        re.search(
            r"^\s*(?:please\s+)?multiply\b",
            text,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"\bproduct\s+of\b",
            text,
            flags=re.IGNORECASE,
        )
    ):
        request = _build_request(
            "multiply",
            _extract_numbers(
                text
            ),
        )

        if request is not None:
            return request

    # --------------------------------------------------
    # Division
    # --------------------------------------------------

    divide_match = re.search(
        rf"\bdivide\s+({NUMBER_PATTERN})\s+"
        rf"by\s+({NUMBER_PATTERN})\b",
        text,
        flags=re.IGNORECASE,
    )

    if divide_match:
        return _build_request(
            "divide",
            (
                _parse_decimal(
                    divide_match.group(
                        1
                    )
                ),
                _parse_decimal(
                    divide_match.group(
                        2
                    )
                ),
            ),
        )

    # --------------------------------------------------
    # Percentage-of phrases
    # --------------------------------------------------

    percent_match = re.search(
        rf"({NUMBER_PATTERN})\s*"
        rf"(?:%|percent)\s+of\s+"
        rf"({NUMBER_PATTERN})",
        text,
        flags=re.IGNORECASE,
    )

    if percent_match:
        percent = _parse_decimal(
            percent_match.group(
                1
            )
        )

        base = _parse_decimal(
            percent_match.group(
                2
            )
        )

        expression = (
            f"({_canonical_decimal(percent)} / 100) "
            f"* {_canonical_decimal(base)}"
        )

        return ArithmeticRequest(
            expression=expression,
            operation="percent",
            operands=(
                _canonical_decimal(
                    percent
                ),
                _canonical_decimal(
                    base
                ),
            ),
            display_expression=(
                f"{_canonical_decimal(percent)}% of "
                f"{_canonical_decimal(base)}"
            ),
            inherited=False,
        )

    # --------------------------------------------------
    # Symbolic / simple word expression
    # --------------------------------------------------

    symbolic = _parse_symbolic_request(
        text
    )

    if symbolic is not None:
        return symbolic

    # --------------------------------------------------
    # Follow-up using the previous Core-verified arithmetic result
    # --------------------------------------------------

    result_follow_up = (
        _extract_result_follow_up_request(
            text,
            conversation_state,
        )
    )

    if result_follow_up is not None:
        return result_follow_up

    # --------------------------------------------------
    # Follow-up correction using Core-owned previous operands
    # --------------------------------------------------

    return _extract_follow_up_request(
        text,
        conversation_state,
    )


def _evaluate_ast_node(
    node,
) -> Decimal:
    if isinstance(
        node,
        ast.Expression,
    ):
        return _evaluate_ast_node(
            node.body
        )

    if isinstance(
        node,
        ast.Constant,
    ):
        if isinstance(
            node.value,
            bool,
        ):
            raise ArithmeticEvaluationError(
                "Booleans are not valid arithmetic values."
            )

        if isinstance(
            node.value,
            int,
        ):
            return Decimal(
                node.value
            )

        if isinstance(
            node.value,
            float,
        ):
            return Decimal(
                str(
                    node.value
                )
            )

        raise ArithmeticEvaluationError(
            "That expression contains an unsupported value."
        )

    if isinstance(
        node,
        ast.UnaryOp,
    ):
        value = _evaluate_ast_node(
            node.operand
        )

        if isinstance(
            node.op,
            ast.UAdd,
        ):
            return value

        if isinstance(
            node.op,
            ast.USub,
        ):
            return -value

        raise ArithmeticEvaluationError(
            "That expression contains an unsupported unary operator."
        )

    if isinstance(
        node,
        ast.BinOp,
    ):
        left = _evaluate_ast_node(
            node.left
        )

        right = _evaluate_ast_node(
            node.right
        )

        if isinstance(
            node.op,
            ast.Add,
        ):
            return (
                left
                + right
            )

        if isinstance(
            node.op,
            ast.Sub,
        ):
            return (
                left
                - right
            )

        if isinstance(
            node.op,
            ast.Mult,
        ):
            return (
                left
                * right
            )

        if isinstance(
            node.op,
            ast.Div,
        ):
            if right == 0:
                raise ArithmeticEvaluationError(
                    "I can't divide by zero."
                )

            return (
                left
                / right
            )

        if isinstance(
            node.op,
            ast.Pow,
        ):
            if right != right.to_integral_value():
                raise ArithmeticEvaluationError(
                    "Fractional exponents aren't supported in deterministic "
                    "calculator mode yet."
                )

            exponent = int(
                right
            )

            if abs(
                exponent
            ) > 12:
                raise ArithmeticEvaluationError(
                    "That exponent is outside the calculator's safe range."
                )

            if (
                left == 0
                and exponent < 0
            ):
                raise ArithmeticEvaluationError(
                    "I can't raise zero to a negative power."
                )

            return (
                left
                ** exponent
            )

        raise ArithmeticEvaluationError(
            "That expression contains an unsupported operator."
        )

    raise ArithmeticEvaluationError(
        "That expression isn't supported by deterministic calculator mode."
    )


def evaluate_arithmetic_expression(
    expression: str,
) -> Decimal:
    value = str(
        expression
        or ""
    ).strip()

    if not value:
        raise ArithmeticEvaluationError(
            "There isn't an arithmetic expression to calculate."
        )

    if len(
        value
    ) > 500:
        raise ArithmeticEvaluationError(
            "That arithmetic expression is too long."
        )

    if not re.fullmatch(
        r"[0-9eE+\-*/().\s]+",
        value,
    ):
        raise ArithmeticEvaluationError(
            "That arithmetic expression contains unsupported characters."
        )

    try:
        tree = ast.parse(
            value,
            mode="eval",
        )

    except SyntaxError as exc:
        raise ArithmeticEvaluationError(
            "I couldn't parse that arithmetic expression."
        ) from exc

    with localcontext() as context:
        context.prec = 50

        try:
            return _evaluate_ast_node(
                tree
            )

        except (
            InvalidOperation,
            DivisionByZero,
            OverflowError,
        ) as exc:
            raise ArithmeticEvaluationError(
                "That calculation could not be evaluated safely."
            ) from exc


def build_arithmetic_answer(
    *,
    request: ArithmeticRequest,
    result: Decimal,
) -> str:
    formatted = format_arithmetic_number(
        result
    )

    if request.operation == "add":
        return (
            f"The total is {formatted}."
        )

    if request.operation == "percent":
        return (
            f"{request.display_expression} is {formatted}."
        )

    return (
        f"The result is {formatted}."
    )
