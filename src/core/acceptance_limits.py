"""Typed availability validation for bounded Core limitation responses.

Unavailable evidence establishes a limitation, never the answer to the task.
This adapter recognizes the speech acts that preserve that limitation and
optional requests for the missing input. It does not infer domain facts or
replace the generic interpreter for unrelated language. Coverage requires the
entire sentence: a safe disclaimer cannot authorize a factual continuation.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Optional, Tuple

from core.acceptance_semantics import ClaimUnit, canonical_statement
from core.acceptance_typed import TypedEvaluation, TypedUnitValidation
from core.answer_candidate import AnswerCandidate
from core.evidence import EvidenceKind, EvidenceStatus


_MODES = {
    "missing_input": {"insufficient_user_context"},
    "verification_declined": {"verification_declined"},
    "public_evidence_unavailable": {"public_source_verified", "classify_then_verify"},
    "private_state": {"private_state_uncertain", "unobserved_private_state"},
}
_CONTRACTIONS = {
    "can't": "cannot", "couldn't": "could not", "don't": "do not",
    "haven't": "have not", "won't": "will not", "i'm": "i am",
    "you're": "you are", "you've": "you have", "i'll": "i will",
    "isn't": "is not", "aren't": "are not", "hasn't": "has not",
}
_KNOWING = r"(?:know|determine|establish|verify|confirm|inspect|observe|see|tell|assess|read|access|answer|give|provide)"
_SUPPLY = r"(?:attach|upload|provide|supply|send|share|show|tell|give)"
_INPUT = r"(?:information|input|inputs|context|detail|details|material|materials|evidence|data|answer|result|fact|state)"
_SCOPE_FILLERS = frozenset({
    "a", "an", "the", "that", "this", "it", "its", "your", "my", "me",
    "you", "i", "user", "what", "which", "how", "whether", "if", "to", "of", "from",
    "in", "with", "without", "on", "under", "through", "about", "reliably",
    "reliable", "exact", "current", "yet", "cleanly", "actually", "enough",
    "sufficient", "required", "requested", "missing", "task", "specific",
    "supplied", "provided", "available", "unavailable", "public", "private",
    "information", "input", "inputs", "context", "detail", "details", "material",
    "materials", "evidence", "data", "answer", "result", "fact", "state",
    "verify", "verifying", "verification", "confirm", "confirming", "determine",
    "determining", "know", "knowing", "observation", "observe", "observing",
    "text", "chat", "conversation", "showing", "telling", "given", "have",
    "not", "be", "are", "is", "do", "told", "or", "and", "unless", "until",
    "our", "their", "its",
    "would", "will", "can", "cannot", "need", "needed", "checking", "check",
})


@dataclass(frozen=True)
class _Availability:
    kind: str
    evidence_ids: Tuple[str, ...]
    scopes: Tuple[str, ...]
    missing_inputs: Tuple[str, ...]


def _normal(text: str) -> str:
    value = " ".join(text.replace("\u2019", "'").replace("\u2018", "'").split()).casefold()
    for token, expanded in _CONTRACTIONS.items():
        value = re.sub(r"(?<!\w)" + re.escape(token) + r"(?!\w)", expanded, value)
    return value.strip().rstrip(".!?").strip()


def _availability(candidate: AnswerCandidate) -> Optional[_Availability]:
    records = []
    for item in candidate.evidence.evidence:
        if not (
            item.kind == EvidenceKind.UNCERTAINTY
            and item.status == EvidenceStatus.UNAVAILABLE
            and item.provenance == "core_evidence_availability"
            and item.authority_scope == "evidence_availability"
        ):
            continue
        data = item.data.get("availability")
        if not isinstance(data, Mapping) or type(data.get("version")) is not int or data["version"] != 1:
            continue
        kind = data.get("kind")
        if not isinstance(kind, str) or kind not in _MODES or candidate.contract.epistemic_mode not in _MODES[kind]:
            continue
        if kind == "missing_input" and data.get("input_available") is not False:
            continue
        if kind == "private_state" and data.get("observation_available") is not False:
            continue
        if kind == "verification_declined" and not (
            data.get("verification_required") is True and data.get("verification_declined") is True
        ):
            continue
        if kind == "public_evidence_unavailable" and not (
            data.get("retrieval_failed") is True and data.get("supporting_evidence_available") is False
            and candidate.contract.authority in {"public_web", "public_source"}
        ):
            continue
        records.append((item, data))
    if not records or len({data["kind"] for _, data in records}) != 1:
        return None
    scopes, missing_inputs = [], []
    if candidate.contract.subject:
        scopes.append(candidate.contract.subject)
    for _, data in records:
        if isinstance(data.get("scope"), str) and data["scope"].strip():
            scopes.append(data["scope"])
        supplied = data.get("missing_inputs", ())
        if isinstance(supplied, str):
            supplied = (supplied,)
        if isinstance(supplied, (tuple, list)):
            omitted = [value for value in supplied if isinstance(value, str) and value.strip()]
            scopes.extend(omitted)
            missing_inputs.extend(omitted)
    return _Availability(
        records[0][1]["kind"],
        tuple(dict.fromkeys(item.evidence_id for item, _ in records if item.evidence_id)),
        tuple(dict.fromkeys(_normal(value) for value in scopes)),
        tuple(dict.fromkeys(_normal(value) for value in missing_inputs)),
    )


def _clauses(text: str):
    """Keep nominal conjunctions intact; split independently voiced clauses."""
    value = _normal(text)
    delimiter = re.compile(
        r"\s*(?:,\s*(?:(?:and|so|but)\s+)?|\s+(?:because|until|unless|so|but)\s+|"
        r"\s+and\s+(?=(?:i|you|we|they|he|she|it|there)\b))\s*"
    )
    result, position, connector = [], 0, ""
    for match in delimiter.finditer(value):
        result.append((connector, value[position:match.start()].strip()))
        separator = match.group().strip(" ,")
        connector = separator or ","
        position = match.end()
    result.append((connector, value[position:].strip()))
    return tuple(result)


def _safe_tail(value: str) -> bool:
    # Numerical or quoted content does not acquire truth merely because a
    # denial preceded it. Relative assertions likewise require ordinary proof.
    return bool(value) and not re.search(
        r"[\d;:`{}\[\]\n]|\b(?:which|who|whose|that)\s+(?:is|are|was|were|has|have|will)\b|"
        r"\b(?:but|because|so|although|while|whereas|since|before|after|given|despite|whenever)\b|"
        r"\band\s+(?:the|a|an|this|that|your|my)\b.+?\b"
        r"(?:is|are|was|were|has|have|will|contains|equals|weighs|costs)\b", value,
    )


def _scope_matches(value: str, state: _Availability, *, generic=True) -> bool:
    value = _normal(value)
    if not value or not _safe_tail(value):
        return False
    if state.scopes:
        rendered = canonical_statement(value)
        for scope in state.scopes:
            known = canonical_statement(scope)
            if known and known in rendered:
                remainder = rendered.replace(known, "", 1)
                words = set(re.findall(r"[a-z]+", remainder))
                if words <= (_SCOPE_FILLERS | {"assistant", "user", "s"}):
                    return True
    if state.kind == "private_state":
        # One embedded user-state predicate can identify the denied observation
        # without guessing its value. Additional predicates still need proof.
        question = re.fullmatch(
            r"(?:what|whether|if) you (?:(?:are|were|have|had|do|did) )?"
            r"[a-z]+(?P<tail>\s+.*)?", value,
        )
        if question:
            tail = (question.group("tail") or "").strip()
            if not re.search(r"\b(?:is|are|was|were|has|have|will|can|do|did)\b", tail):
                if set(re.findall(r"[a-z]+", tail)) <= _SCOPE_FILLERS:
                    return True
    words = set(re.findall(r"[a-z]+", value))
    vocabulary = _SCOPE_FILLERS
    if state.kind == "private_state":
        vocabulary = vocabulary | {"colour", "color", "appearance", "concealed", "object"}
    return generic and bool(words) and words <= vocabulary


def _denial(value: str, state: _Availability):
    if state.kind in {"verification_declined", "public_evidence_unavailable"}:
        value = re.sub(r"^without (?:verification|verifying|checking|confirmation)(?:,)?\s+", "", value)
    match = re.fullmatch(
        r"i (?:cannot|can not|could not|am unable to|do not) "
        r"(?:reliably )?(?P<verb>" + _KNOWING + r")(?P<tail>\s+.+)?", value,
    )
    if match:
        verb, tail = match.group("verb"), (match.group("tail") or "").strip()
        if state.kind == "verification_declined" and verb in {"inspect", "observe", "see", "read", "access"}:
            return None
        if state.kind == "public_evidence_unavailable" and verb in {"observe", "see", "inspect"}:
            return None
        if state.kind == "private_state" and verb in {"give", "provide", "verify", "access"}:
            return None
        if not tail or _scope_matches(tail, state):
            return "limitation"
        # An inability to provide an answer under a verification condition is
        # a refusal, not a claim that the requested value was verified.
        conditional = re.fullmatch(r"(.+?)\s+without\s+(?:verifying|checking|confirming)(?:\s+.+)?", tail)
        if conditional and state.kind in {"verification_declined", "public_evidence_unavailable"}:
            if _scope_matches(conditional.group(1), state):
                return "limitation"
        return None
    match = re.fullmatch(r"i do not have (?:enough|sufficient) information to " + _KNOWING + r"\s+(.+)", value)
    if match and _scope_matches(match.group(1), state):
        return "limitation"
    match = re.fullmatch(r"i (?:could not|cannot|did not) find (.+)", value)
    if match and state.kind == "public_evidence_unavailable":
        tail = match.group(1)
        if re.search(r"\b(?:public )?evidence\b", tail) and _scope_matches(tail, state):
            return "limitation"
    match = re.fullmatch(r"(.+?) (?:is|are) (?P<status>unavailable|missing|unknown|unverified|not supplied|not provided|not attached)", value)
    if match:
        # Missing access and an explicit user omission have different authority.
        # Only the latter establishes that the user did not supply/attach it.
        if match.group("status").startswith("not "):
            if _omission_matches(match.group(1), state):
                return "limitation"
        elif _scope_matches(match.group(1), state):
            return "limitation"
    return None


def _refusal(value: str) -> bool:
    return bool(re.fullmatch(
        r"i (?:(?:will|would|do) not|am not going to) "
        r"(?:guess(?:\s+(?:at )?(?:it|that|the answer|the result))?|"
        r"(?:invent|fabricate|make up) (?:(?:a|an|the) (?:answer|result|value|fact)|it|that))", value,
    ))


def _constraint(value: str, state: _Availability) -> bool:
    if state.kind != "verification_declined":
        return False
    return bool(re.fullmatch(
        r"you (?:explicitly )?(?:told|asked|instructed) me not to "
        r"(?:browse|search|verify|check|look (?:it |that )?up)(?: (?:it|that|this))?", value,
    )) or bool(re.fullmatch(
        r"i (?:(?:will|can|do) not|am not going to) (?:browse|search|verify|check|look (?:it |that )?up)", value,
    ))


def _omission_matches(value: str, state: _Availability) -> bool:
    if state.kind != "missing_input" or not state.missing_inputs:
        return False
    explicit = _Availability(state.kind, state.evidence_ids, state.missing_inputs, state.missing_inputs)
    return _scope_matches(value, explicit, generic=False)


def _missing_cause(value: str, state: _Availability) -> bool:
    if state.kind != "missing_input":
        return False
    match = re.fullmatch(r"you (?:have|had) not (?:given|provided|supplied|sent|shown|told|attached|uploaded)(?: me)? (.+)", value)
    return bool(match and _omission_matches(match.group(1), state))


def _supply_condition(value: str, state: _Availability) -> bool:
    if state.kind not in {"missing_input", "private_state"}:
        return False
    match = re.fullmatch(r"you (?:actually )?(?:" + _SUPPLY + r")(?: or " + _SUPPLY + r")?(?: me)? (.+)", value)
    if match:
        return _scope_matches(match.group(1), state)
    if state.kind == "private_state":
        return bool(re.fullmatch(r"you have told me in (?:our|the) conversation", value))
    return False


def _request(value: str, state: _Availability, candidate: AnswerCandidate) -> bool:
    if state.kind != "missing_input" or not candidate.contract.allow_follow_up_question:
        return False
    match = re.fullmatch(r"(?:please )?(?:" + _SUPPLY + r")(?: me)? (.+)", value)
    return bool(match and _scope_matches(match.group(1), state))


def _use_after_input(value: str, state: _Availability) -> bool:
    return state.kind == "missing_input" and bool(re.fullmatch(
        r"i will use (?:it|that|the supplied (?:information|input|details)) "
        r"(?:rather than|instead of) (?:guess|guessing)", value,
    ))


def _validate_unit(unit: ClaimUnit, state: _Availability, candidate: AnswerCandidate):
    if unit.text.rstrip().endswith("?"):
        # A question does not assert that Core's limitation was preserved.
        # Only an allowed, wholly recognized request can travel as a neutral
        # continuation; it supplies no limitation/completion obligation.
        if _request(_normal(unit.text), state, candidate):
            return TypedUnitValidation(evidence_ids=state.evidence_ids)
        return None
    obligations = set()
    clauses = _clauses(unit.text)
    for connector, value in clauses:
        if not value:
            return None
        denial = _denial(value, state)
        if denial:
            obligations.add(denial)
            continue
        if _refusal(value):
            obligations.add("refusal_to_guess")
            continue
        if _constraint(value, state):
            obligations.add("verification_constraint")
            continue
        if connector == "because" and _missing_cause(value, state):
            continue
        if connector in {"until", "unless"} and _supply_condition(value, state):
            continue
        if _request(value, state, candidate) or _use_after_input(value, state):
            continue
        return None
    if not obligations and not any(_request(value, state, candidate) for _, value in clauses):
        return None
    return TypedUnitValidation(
        evidence_ids=state.evidence_ids,
        obligations=tuple(sorted(obligations)),
        limitation_preserved="limitation" in obligations,
    )


def validate_limits(candidate: AnswerCandidate, units: Tuple[ClaimUnit, ...]) -> Optional[TypedEvaluation]:
    """Cover bounded limitation speech acts from trusted typed absence state.

    Untyped legacy uncertainty is intentionally left to existing checks. The
    adapter never reads origin, path identifiers, model validation metadata,
    internal limitation wording, rejected source bodies, or assistant history.
    """
    state = _availability(candidate)
    if state is None:
        return None
    covered = {}
    for unit in units:
        result = _validate_unit(unit, state, candidate)
        if result is not None:
            covered[unit.index] = result
    # A wholly bounded verification refusal supplies no guessed value even
    # when it says "cannot answer without verification" instead of "no guess".
    if state.kind == "verification_declined" and len(covered) == len(units) and units:
        for index, result in covered.items():
            if result.limitation_preserved and "refusal_to_guess" not in result.obligations:
                covered[index] = TypedUnitValidation(
                    evidence_ids=result.evidence_ids,
                    obligations=result.obligations + ("refusal_to_guess",),
                    limitation_preserved=True,
                )
                break
    obligations = ("limitation", "refusal_to_guess") if state.kind == "verification_declined" else ("limitation",)
    return TypedEvaluation(
        validator="typed_evidence_availability",
        units=covered,
        completion_obligations=obligations,
    )
