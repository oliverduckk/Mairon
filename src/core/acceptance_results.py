"""Typed numerical acceptance for bounded, verified Core result domains.

This adapter checks retained calculation fields rather than using answer prose
as evidence. Its grammar covers numerical reports, not arbitrary explanations.
A unit with an uncovered clause returns to the conservative semantic evaluator.
Neither candidate origin nor a diagnostic path selects or relaxes this policy.
"""
import ast
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from core.acceptance_typed import TypedEvaluation, TypedUnitValidation
from core.arithmetic import (
    ArithmeticEvaluationError, evaluate_arithmetic_expression, extract_arithmetic_request,
)
from core.evidence import EvidenceKind, EvidenceStatus


_NUMBER = r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)"
_AMOUNT = rf"(?P<number>{_NUMBER}|zero|no)\s*(?:-\s*)?(?P<unit>minutes?|mins?|hours?|hrs?)"
_AUTHORITY = "evidence_authority"
_CONDITION = "conditional_scope"
_TIME_MODES = frozenset({"user_premise_reasoning", "user_context_reasoning", "deterministic_calculation"})
_ARITHMETIC_MODES = frozenset({"deterministic_calculation", "tool_verified", "tool_result", "verified_core"})
_ARITHMETIC_OPERATIONS = frozenset({"add", "subtract", "multiply", "divide", "power", "percent", "expression"})


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("A typed numerical field must be a finite decimal")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("A typed numerical field must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError("A typed numerical field must be finite")
    return result


def _minutes(match, suffix=""):
    number = match["number" + suffix]
    amount = Decimal(0) if number in {"zero", "no"} else _rendered_decimal(number)
    return amount * 60 if match["unit" + suffix].lower().startswith(("hour", "hr")) else amount


def _rendered_decimal(value):
    # This helper receives only a fullmatched rendered numerical token. Core
    # evidence fields continue to require plain canonical decimal values.
    return _decimal(value.replace(",", ""))


def _text(value):
    return " ".join(value.lower().replace("\u2019", "'").split()).strip(" .!?")


def _expression(value):
    value = value.strip().lower().replace("\u00d7", "*").replace("\u00f7", "/").replace("^", "**")
    if "," in value:
        for token in re.findall(r"[+-]?(?:\d[\d,.]*|\.[\d,.]+)", value):
            if re.fullmatch(_NUMBER, token) is None:
                raise ValueError("Malformed numerical grouping")
        value = value.replace(",", "")
    percent = re.fullmatch(rf"({_NUMBER})\s*%\s+of\s+({_NUMBER})", value)
    return f"({percent[1]} / 100) * {percent[2]}" if percent else value


def _expression_key(value):
    """Numerical rendering equivalence; order remains significant outside +/*."""
    expression = _expression(value)
    tree = ast.parse(expression, mode="eval")

    def exact_number(node, negative=False):
        # Preserve the retained lexical operand, including digits beyond the
        # default Decimal context and Python's float AST representation.
        number = Decimal(ast.get_source_segment(expression, node) or str(node.value))
        if negative:
            number = number.copy_negate()
        rendered = format(number, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return ("number", "0" if rendered in {"-0", "+0"} else rendered)

    def key(node):
        if isinstance(node, ast.Expression):
            return key(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return exact_number(node)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            if isinstance(node.operand, ast.Constant):
                return exact_number(node.operand, negative=isinstance(node.op, ast.USub))
            return (type(node.op).__name__, key(node.operand))
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            operation = type(node.op).__name__
            left, right = key(node.left), key(node.right)
            if operation in {"Add", "Mult"}:
                parts = []
                for child in (left, right):
                    parts.extend(child[1:] if child[0] == operation else (child,))
                return (operation, *sorted(parts, key=repr))
            return (operation, left, right)
        raise ValueError("Unsupported numerical expression")

    return key(tree)


def _operation_scope(expression, operation):
    """Retain the producer's classification while binding precise word labels.

    The existing symbolic producer can classify unary signs as an operation.
    That compatibility label must not turn a power into proof of a difference.
    Explicit arithmetic requests also retain operations for signed operands.
    """
    tree = ast.parse(expression, mode="eval").body
    primary = ({ast.Add: "add", ast.Sub: "subtract", ast.Mult: "multiply",
                ast.Div: "divide", ast.Pow: "power"}.get(type(tree.op))
               if isinstance(tree, ast.BinOp) else None)
    recognized = extract_arithmetic_request(expression)
    compatible = {"expression", primary}
    if recognized is not None:
        compatible.add(recognized.operation)
    if (isinstance(tree, ast.BinOp) and isinstance(tree.op, ast.Mult)
            and isinstance(tree.left, ast.BinOp) and isinstance(tree.left.op, ast.Div)
            and isinstance(tree.left.right, ast.Constant)
            and tree.left.right.value == 100):
        compatible.add("percent")
    if operation not in compatible:
        raise ValueError("The retained operation does not match the Core expression")
    return primary


@dataclass(frozen=True)
class _Result:
    domain: str
    data: Mapping
    evidence_ids: tuple
    obligations: tuple


def _trusted(item):
    return (item.kind == EvidenceKind.CORE_RESULT
            and item.status == EvidenceStatus.ADMISSIBLE
            and item.confidence == "verified"
            and item.authority_scope in {"core_result", "deterministic_result"})


def _schema(candidate):
    contract = candidate.contract
    records = [item for item in candidate.evidence.evidence if _trusted(item)]
    time = [item for item in records if item.provenance == "core_time_budget"
            and item.data.get("result_kind") == "time_budget"]
    arithmetic = [item for item in records if item.provenance == "core_arithmetic"
                  and {"expression", "operation", "result"}.issubset(item.data)]
    if time and contract.epistemic_mode in _TIME_MODES and contract.authority in {
        "user_turn_reasoning", "user_context", "core_results", "verified_core",
    }:
        domain, selected = "time_budget", time
    elif arithmetic and contract.epistemic_mode in _ARITHMETIC_MODES and contract.authority in {
        "core_arithmetic", "core_results", "verified_core",
    }:
        domain, selected = "arithmetic", arithmetic
    else:
        return None
    data = dict(selected[0].data)
    if any(dict(item.data) != data for item in selected[1:]):
        raise ValueError("Conflicting typed Core results")
    ids = tuple(dict.fromkeys(item.evidence_id for item in selected if item.evidence_id))
    if domain == "time_budget":
        if data.get("conditional_on_supplied_inputs") is not True:
            raise ValueError("The time calculation must retain its supplied-input scope")
        for field in ("budget_minutes", "used_minutes", "remaining_minutes"):
            data[field] = _decimal(data[field])
        if data["budget_minutes"] < 0 or data["used_minutes"] < 0:
            raise ValueError("Negative time input")
        if data["remaining_minutes"] != data["budget_minutes"] - data["used_minutes"]:
            raise ValueError("Inconsistent remaining time")
        items = {}
        for item in data["items"]:
            if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
                raise ValueError("Malformed time item")
            name, minutes = _text(item["name"]), _decimal(item["minutes"])
            if not name or name in items or minutes < 0:
                raise ValueError("Ambiguous or negative time item")
            items[name] = minutes
        if not items or sum(items.values(), Decimal(0)) != data["used_minutes"]:
            raise ValueError("Inconsistent item total")
        data["items"] = items
        data["delay_minutes"] = _decimal(data.get("delay_minutes", "0"))
        if data["delay_minutes"] < 0 or (data["delay_minutes"] and data.get("delay_target") not in items):
            raise ValueError("Inconsistent delay input")
        if data["delay_minutes"] and data["delay_minutes"] > items[data["delay_target"]]:
            raise ValueError("The retained delay implies a negative original duration")
        outputs = candidate.contract.metadata.get("result_obligations", data.get(
            "required_outputs", ("used", "comparison", "remaining")))
        if not isinstance(outputs, (tuple, list)) or any(
            value not in {"used", "comparison", "remaining", "budget"} for value in outputs
        ) or not outputs:
            raise ValueError("Malformed result obligations")
        obligations = tuple(dict.fromkeys(outputs))
    else:
        if not isinstance(data["expression"], str) or data["operation"] not in _ARITHMETIC_OPERATIONS:
            raise ValueError("Malformed arithmetic result")
        data["result"] = _decimal(data["result"])
        if evaluate_arithmetic_expression(data["expression"]) != data["result"]:
            raise ValueError("Inconsistent arithmetic result")
        data["primary_operation"] = _operation_scope(data["expression"], data["operation"])
        data["expression_key"] = _expression_key(data["expression"])
        if contract.subject:
            try:
                subject_key = _expression_key(contract.subject)
            except (ValueError, SyntaxError):
                subject_key = None
            if subject_key is not None and subject_key != data["expression_key"]:
                raise ValueError("The Core result belongs to a different contracted calculation")
        obligations = ("result",)
    return _Result(domain, data, ids, obligations)


def _claim(tag, actual, expected, invariant=_AUTHORITY):
    if actual == expected:
        return (tag,), (), ()
    return (), (invariant,), ("The rendered numerical claim differs from the verified Core result",)


def _arithmetic_part(text, result):
    data = result.data
    literal = re.fullmatch(rf"(?:(?:the\s+)?(?P<label>answer|result|total|sum|product|difference|quotient)\s*(?:is|equals|=|:)\s*)?(?P<number>{_NUMBER})", text)
    if literal:
        labels = {"sum": "add", "product": "multiply", "difference": "subtract", "quotient": "divide"}
        if literal["label"] in labels and labels[literal["label"]] != data["primary_operation"]:
            return (), (_AUTHORITY,), ("The candidate changes the operation described by the Core result",)
        return _claim("result", _rendered_decimal(literal["number"]), data["result"])
    equation = re.fullmatch(rf"(?P<expression>.+?)\s*(?:=|equals|is)\s*(?P<number>{_NUMBER})", text)
    if equation:
        try:
            rendered = _expression(equation["expression"])
            rendered_result = evaluate_arithmetic_expression(rendered)
            key = _expression_key(rendered)
        except (ArithmeticEvaluationError, ValueError, SyntaxError):
            return None
        if key != data["expression_key"]:
            return (), (_CONDITION,), ("The candidate changes the numerical inputs or operation",)
        if rendered_result != data["result"]:
            return (), (_AUTHORITY,), ("The rendered expression does not reproduce the verified Core result",)
        return _claim("result", _rendered_decimal(equation["number"]), data["result"])
    return None


def _time_part(text, result):
    data = result.data
    remaining = data["remaining_minutes"]
    fits = remaining >= 0
    verdicts = {
        "yes": fits, "yes exactly": remaining == 0, "yes it fits": fits,
        "it fits": fits, "it fits within the budget": fits,
        "the activities fit": fits, "the tasks fit": fits,
        "no": not fits, "no it does not fit": not fits,
        "it does not fit": not fits, "it doesn't fit": not fits,
        "the activities do not fit": not fits, "the tasks do not fit": not fits,
        "with no extra time left": remaining == 0, "with no time left": remaining == 0,
        "no extra time remains": remaining == 0, "there is no time left": remaining == 0,
    }
    if text in verdicts:
        tags = ("comparison", "remaining") if text.startswith(("with no", "no extra", "there is no")) else ("comparison",)
        return (tags, (), ()) if verdicts[text] else ((), (_AUTHORITY,), ("The candidate reverses the computed time comparison",))
    heads = (
        ("used", r"(?:the\s+)?(?:time used|used time|total|total time|total duration|activities|tasks)(?:\s+(?:is|are|take|takes|use|uses|total|totals|require|requires|=|:))?"),
        ("budget", r"(?:the\s+|your\s+)?(?:time budget|budget|time limit|limit)(?:\s+(?:is|equals|=|:))?"),
        ("remaining", r"(?:the\s+)?(?:remaining time|time remaining|time left|spare time)(?:\s+(?:is|equals|=|:))?"),
    )
    for tag, head in heads:
        suffix = r"(?:\s+in total)?" if tag == "used" else ""
        match = re.fullmatch(head + r"\s+" + _AMOUNT + suffix, text)
        if match:
            return _claim(tag, _minutes(match), data[{"used": "used_minutes", "budget": "budget_minutes", "remaining": "remaining_minutes"}[tag]])
    patterns = (
        ("used", _AMOUNT + r"\s+(?:in total|total|used|altogether)"),
        ("remaining", r"(?:leaving|leaves|with|there are|there is)\s+" + _AMOUNT + r"\s*(?:spare|left|remaining|to spare)?"),
        ("remaining", _AMOUNT + r"\s+(?:remain|remains|left|remaining|spare|to spare)"),
        ("budget", r"against\s+(?:your|the|a)\s+" + _AMOUNT + r"\s+(?:limit|budget)"),
        ("budget", r"within\s+(?:your|the|a)\s+" + _AMOUNT + r"\s+(?:limit|budget)"),
    )
    for tag, pattern in patterns:
        match = re.fullmatch(pattern, text)
        if match:
            answer = _claim(tag, _minutes(match), data[{"used": "used_minutes", "budget": "budget_minutes", "remaining": "remaining_minutes"}[tag]])
            if text.startswith("within"):
                if not fits:
                    return (), (_AUTHORITY,), ("The candidate reverses the computed time comparison",)
                return tuple(dict.fromkeys((*answer[0], "comparison"))), answer[1], answer[2]
            return answer
    other_amount = _AMOUNT.replace("?P<number>", "?P<number2>").replace("?P<unit>", "?P<unit2>")
    over = re.fullmatch(
        r"(?:(?:so\s+)?(?:you(?:'re| are)|we(?:'re| are)|it is|that is|the total is)\s+)?"
        + _AMOUNT + r"\s+(?P<direction>over|under)(?:\s+(?:budget|the budget|the limit)|\s+(?:the|your|a)\s+"
        + other_amount + r"\s+(?:budget|limit))?", text)
    if over:
        signed = -_minutes(over) if over["direction"] == "over" else _minutes(over)
        answer = _claim("remaining", signed, remaining)
        correct_direction = remaining < 0 if over["direction"] == "over" else remaining > 0
        if not correct_direction:
            return (), (_AUTHORITY,), ("The candidate reverses the computed time comparison",)
        if over["number2"] is not None and _minutes(over, "2") != data["budget_minutes"]:
            return (), (_CONDITION,), ("The candidate changes the supplied time budget",)
        return tuple(dict.fromkeys((*answer[0], "comparison"))), answer[1], answer[2]
    exceeds = re.fullmatch(r"(?:exceeding|exceeds|over)\s+(?:the|your|a)\s+" + _AMOUNT
                          + r"\s+(?:budget|limit)\s+by\s+" + other_amount, text)
    if exceeds:
        if _minutes(exceeds) != data["budget_minutes"]:
            return (), (_CONDITION,), ("The candidate changes the supplied time budget",)
        if remaining >= 0:
            return (), (_AUTHORITY,), ("The candidate reverses the computed time comparison",)
        answer = _claim("remaining", -_minutes(exceeds, "2"), remaining)
        return tuple(dict.fromkeys((*answer[0], "comparison"))), answer[1], answer[2]
    equal = re.fullmatch(r"(?:exactly\s+)?(?:matching|matches|equals)\s+(?:the|your|a)\s+"
                         + _AMOUNT + r"\s+(?:budget|limit)", text)
    if equal:
        if _minutes(equal) != data["budget_minutes"]:
            return (), (_CONDITION,), ("The candidate changes the supplied time budget",)
        if remaining != 0:
            return (), (_AUTHORITY,), ("The candidate reverses the computed time comparison",)
        return ("comparison", "budget"), (), ()
    equation = re.fullmatch(rf"(?P<expression>{_NUMBER}(?:\s*\+\s*{_NUMBER})+)\s*=\s*{_AMOUNT}", text)
    if equation:
        terms = [_rendered_decimal(value) for value in re.findall(_NUMBER, equation["expression"])]
        if sorted(terms) != sorted(data["items"].values()):
            return (), (_CONDITION,), ("The equation changes the supplied time inputs",)
        return _claim("used", _minutes(equation), data["used_minutes"])
    for name, minutes in data["items"].items():
        item = re.fullmatch(re.escape(name) + r"\s+(?:(?:is|takes|uses|requires|=|:)\s+)?" + _AMOUNT, text)
        if item:
            return _claim("item:" + name, _minutes(item), minutes, _CONDITION)
    return None


def _validate_unit(text, result):
    if "?" in text:
        # Asking whether a result is true does not assert that verified result
        # or fulfill its obligation. Existing question policy remains in charge.
        return None
    text = _text(text)
    obligations, violations, reasons = [], [], []
    if result.domain == "time_budget":
        delay = re.match(r"with\s+(?:the|a)\s+" + _AMOUNT + r"\s+delay:\s*", text)
        if delay:
            if _minutes(delay) != result.data["delay_minutes"] or not result.data["delay_minutes"]:
                violations.append(_CONDITION)
                reasons.append("The candidate changes the supplied delay input")
            text = text[delay.end():]
        # Comparison conjunctions separate only bounded numerical clauses.
        text = re.sub(r"\s+against\s+", "; against ", text)
        text = re.sub(r"\s+within\s+(?=(?:your|the|a)\s+\d)", "; within ", text)
        text = re.sub(r"\s+and\s+(?=(?:\d|the |remaining |time |it |there ))", "; ", text)
        clauses = re.split(r"\s*(?:;|(?<!\d),(?!\d))\s*", text)
        if clauses[:2] == ["yes", "exactly"]:
            clauses[:2] = ["yes exactly"]
        parse = _time_part
    else:
        clauses = re.split(r"\s*;\s*", text)
        parse = _arithmetic_part
    for clause in clauses:
        clause = re.sub(r"^(?:and|so)\s+", "", clause).strip()
        if not clause:
            return None
        answer = parse(clause, result)
        if answer is None:
            return None
        obligations.extend(answer[0])
        violations.extend(answer[1])
        reasons.extend(answer[2])
    return TypedUnitValidation(
        evidence_ids=result.evidence_ids, obligations=tuple(dict.fromkeys(obligations)),
        violated_invariants=tuple(dict.fromkeys(violations)), reasons=tuple(dict.fromkeys(reasons)),
    )


def validate_results(candidate, units):
    """Return typed coverage only for recognized scoped Core calculation state."""
    try:
        result = _schema(candidate)
    except (ArithmeticEvaluationError, InvalidOperation, KeyError, TypeError, ValueError, SyntaxError):
        return TypedEvaluation(
            validator="core_numerical_result", units={}, global_violations=(_AUTHORITY,),
            global_reasons=("The retained typed Core result is malformed or internally inconsistent",),
        )
    if result is None:
        return None
    checked = {}
    for unit in units:
        validation = _validate_unit(unit.text, result)
        if validation is not None:
            checked[unit.index] = validation
    required = {}
    for claim in candidate.contract.required_claims:
        validation = _validate_unit(claim, result)
        if validation is not None and not validation.violated_invariants and validation.obligations:
            required[claim] = validation.obligations
    return TypedEvaluation(
        validator="core_" + result.domain, units=checked,
        required_claim_obligations=required, completion_obligations=result.obligations,
    )
