"""Publication authority for the bounded, typed Core calculation/absence lanes.

Call sites select these lanes from existing Core state. Origin is diagnostic
metadata only. A candidate cannot publish on an evaluator/adapter error, and a
replacement is rendered only from independently checked pre-publication state.
No generated repair, source prose, or rejected answer supplies that state.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from core import acceptance_shadow as shadow
from core.acceptance_evaluator import CoreAcceptanceEvaluator
from core.acceptance_limits import _availability, validate_limits
from core.acceptance_results import _schema, validate_results
from core.acceptance_semantics import interpret_text
from core.answer_candidate import (
    AcceptanceDecision, AcceptanceStatus, AcceptedSentence, AnswerCandidate, CandidateOrigin,
)
from core.answer_contract_runtime import coerce_answer_contract_runtime
from core.evidence import EvidenceBundle, EvidenceKind, EvidenceStatus


_CALCULATION_REFUSAL = "I cannot safely provide the requested calculation result."
_UNESTABLISHED_REFUSAL = "I cannot safely determine the requested answer from the available information."
_LIMITATION_TEXT = {
    "missing_input": "I cannot determine the requested answer until you provide the required information.",
    "verification_declined": "I cannot reliably provide the exact current answer without verification. I will not guess.",
    "public_evidence_unavailable": "I could not find sufficient reliable public evidence. I will not invent the answer.",
    "private_state": "I cannot observe the requested private state from the available context.",
}


def _safe_path(value):
    if not isinstance(value, str):
        return "unknown"
    return "".join(character for character in value if character.isascii()
                   and (character.isalnum() or character in "_.-"))[:48] or "unknown"


@dataclass(frozen=True)
class AcceptancePublicationRecord:
    """Private assessment transport; only bounded ``events`` are emitted."""

    path: str
    origin: CandidateOrigin
    decision: Optional[AcceptanceDecision] = None
    replacement_decision: Optional[AcceptanceDecision] = None
    evaluation_failed: bool = False
    replacement_used: bool = False
    outcome: str = "fail_closed"

    def __post_init__(self):
        object.__setattr__(self, "path", _safe_path(self.path))
        if not isinstance(self.origin, CandidateOrigin):
            object.__setattr__(self, "origin", CandidateOrigin.DETERMINISTIC_FALLBACK)
        if self.outcome not in {"accepted", "replaced", "fail_closed"}:
            raise ValueError("Unknown bounded publication outcome")

    @property
    def metadata(self):
        invariants = tuple(dict.fromkeys(
            value if value in shadow._INVARIANTS else "unknown_invariant"
            for decision in (self.decision, self.replacement_decision) if decision is not None
            for value in decision.violated_invariants
        ))
        return {
            "path": self.path, "candidate_origin": self.origin.value,
            "status": self.decision.status.value if self.decision is not None else "evaluation_error",
            "replacement_status": (self.replacement_decision.status.value
                                   if self.replacement_decision is not None else None),
            "violated_invariants": invariants, "evaluation_failed": self.evaluation_failed,
            "replacement_used": self.replacement_used, "outcome": self.outcome,
        }

    @property
    def event(self):
        value = self.metadata
        return (
            "[Core] Acceptance enforced: " + value["status"].upper()
            + "; outcome=" + value["outcome"]
            + "; replacement=" + ("yes" if value["replacement_used"] else "no")
            + "; origin=" + value["candidate_origin"]
            + "; path=" + value["path"]
        )[:180]

    @property
    def events(self):
        invariants = self.metadata["violated_invariants"]
        return (self.event,) + tuple(
            ("[Core] Acceptance enforced invariants: " + self.path + ": "
             + ",".join(invariants[index:index + 2]))[:180]
            for index in range(0, len(invariants), 2)
        )


@dataclass(frozen=True)
class PublicationResult:
    text: str
    record: AcceptancePublicationRecord


def emit_publication_record(record, sink=None):
    """Use the request's existing diagnostics sink without publishing its data."""
    try:
        # The event sink is shared; the record's enforced prefix distinguishes
        # authority from the unchanged observational shadow records.
        shadow.emit_shadow_record(record, sink=sink)
    except Exception:
        pass


def _limitations(bundle):
    return tuple(dict.fromkeys(
        ([bundle.uncertainty] if bundle.uncertainty else [])
        + [reason for item in bundle.evidence if item.kind == EvidenceKind.UNCERTAINTY
           for reason in item.limitations]
    ))


def _trusted_state(candidate, domain):
    """Check structured state independently of the evaluator's prose decision."""
    if domain in {"arithmetic", "time_budget"}:
        if candidate.evidence.success is not True:
            raise ValueError("A verified calculation requires successful Core evidence")
        result = _schema(candidate)
        if result is None or result.domain != domain:
            raise ValueError("The bounded calculation lacks trusted structured state")
        return result
    state = _availability(candidate)
    if state is None:
        raise ValueError("The bounded limitation lacks trusted availability state")
    # Require every matching Core availability record to agree. A malformed or
    # conflicting record cannot disappear merely because another one matched.
    records = [item for item in candidate.evidence.evidence
               if item.kind == EvidenceKind.UNCERTAINTY
               and item.provenance == "core_evidence_availability"
               and "availability" in item.data]
    for item in records:
        data = item.data.get("availability")
        if (item.status != EvidenceStatus.UNAVAILABLE
                or item.authority_scope != "evidence_availability"
                or not isinstance(data, Mapping)
                or type(data.get("version")) is not int or data["version"] != 1
                or data.get("kind") != state.kind):
            raise ValueError("Inconsistent Core availability state")
        required = {
            "missing_input": {"input_available": False},
            "verification_declined": {"verification_required": True, "verification_declined": True},
            "public_evidence_unavailable": {
                "verification_required": True, "retrieval_failed": True,
                "supporting_evidence_available": False,
            },
            "private_state": {"observation_available": False},
        }[state.kind]
        if any(data.get(field) is not expected for field, expected in required.items()):
            raise ValueError("The Core availability obligation is not established")
    return state


def _number(value: Decimal):
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", "+0"} else rendered


def _canonical_replacement(state, domain):
    """Render only verified numeric fields or an established absence kind."""
    if domain == "arithmetic":
        return "The result is " + _number(state.data["result"]) + "."
    if domain == "time_budget":
        data = state.data
        prefix = ("With the " + _number(data["delay_minutes"]) + "-minute delay: "
                  if data["delay_minutes"] else "")
        return (prefix + "The total is " + _number(data["used_minutes"]) + " minutes. "
                + "The budget is " + _number(data["budget_minutes"]) + " minutes. "
                + "The remaining time is " + _number(data["remaining_minutes"]) + " minutes. "
                + ("It fits." if data["remaining_minutes"] >= 0 else "It does not fit."))
    return _LIMITATION_TEXT[state.kind]


def _checked_decision(candidate, domain):
    decision = CoreAcceptanceEvaluator().evaluate(candidate)
    if type(decision) is not AcceptanceDecision:
        raise TypeError("Bounded acceptance requires the typed decision model")
    # Reconstruct to enforce transport checks even if a frozen object was
    # tampered with after construction. Never emit its reasons or metadata.
    decision = AcceptanceDecision(
        status=decision.status, evaluated_text=decision.evaluated_text,
        reasons=decision.reasons, violated_invariants=decision.violated_invariants,
        accepted_sentences=decision.accepted_sentences, metadata=decision.metadata,
    )
    if decision.evaluated_text != candidate.text:
        raise ValueError("The decision assesses different wording")
    if decision.status is not AcceptanceStatus.ACCEPTED:
        return decision
    units = interpret_text(candidate.text, speaker="assistant",
                           user_name=candidate.contract.metadata.get("user_name"))
    expected = tuple(AcceptedSentence(unit.index, unit.text) for unit in units)
    if not units or decision.accepted_sentences != expected or decision.violated_invariants:
        raise ValueError("An accepted decision must cover the entire candidate")
    validator = "typed_evidence_availability" if domain == "limitation" else "core_" + domain
    metadata = decision.metadata
    validators = metadata.get("typed_validators")
    if (metadata.get("semantic_policy") != "bounded_core_restatement"
            or not isinstance(validators, (tuple, list))
            or any(not isinstance(value, str) for value in validators)
            or validator not in validators):
        raise ValueError("The accepted decision lacks the bounded typed assessment")
    reports = metadata.get("units")
    if not isinstance(reports, (tuple, list)) or len(reports) != len(units):
        raise ValueError("The accepted decision has incomplete unit diagnostics")
    for unit, report in zip(units, reports):
        if (not isinstance(report, Mapping) or type(report.get("index")) is not int
                or report.get("index") != unit.index
                or report.get("text") != unit.text or report.get("violated_invariants") != ()):
            raise ValueError("The accepted decision has inconsistent unit diagnostics")
    # This boundary publishes only wholly bounded numerical reports or
    # limitation speech acts. Generic support for an additional fact cannot
    # enlarge this milestone's scope, including a partial source assertion in
    # an unavailable-public-evidence lane. Reuse the existing typed validator.
    profile = (validate_limits(candidate, units) if domain == "limitation"
               else validate_results(candidate, units))
    if (profile is None or profile.global_violations
            or set(profile.units) != {unit.index for unit in units}
            or any(proof.violated_invariants for proof in profile.units.values())):
        raise ValueError("The accepted candidate exceeds its bounded typed domain")
    fulfilled = {obligation for proof in profile.units.values() for obligation in proof.obligations}
    if not set(profile.completion_obligations) <= fulfilled:
        raise ValueError("The accepted candidate omits a bounded typed obligation")
    return decision


def _publish(*, text, contract, origin, path, domain, evidence_factory, emit, public_failed=False):
    initial = replacement_decision = None
    failed = False
    used = False
    outcome = "fail_closed"
    result_text = _CALCULATION_REFUSAL if domain != "limitation" else _UNESTABLISHED_REFUSAL
    safe_origin = origin if isinstance(origin, CandidateOrigin) else CandidateOrigin.DETERMINISTIC_FALLBACK
    try:
        runtime = coerce_answer_contract_runtime(contract)
        if domain == "limitation" and runtime is not None:
            known_kind = {
                "insufficient_user_context": "missing_input",
                "verification_declined": "verification_declined",
                "private_state_uncertain": "private_state",
                "unobserved_private_state": "private_state",
            }.get(runtime.epistemic_mode)
            if (known_kind is None and public_failed
                    and runtime.epistemic_mode in {"public_source_verified", "classify_then_verify"}
                    and runtime.authority in {"public_web", "public_source"}):
                known_kind = "public_evidence_unavailable"
            if known_kind is not None:
                # The established contract/result state retains its limitation
                # even if canonical normalization itself is unavailable.
                result_text = _LIMITATION_TEXT[known_kind]
        bundle = evidence_factory()
        probe = AnswerCandidate(text="", origin=safe_origin, contract=runtime,
                                evidence=bundle, limitations=_limitations(bundle))
        state = _trusted_state(probe, domain)
        if domain == "limitation":
            # This is a Core-owned statement of established absence, safe even
            # if the evaluator infrastructure prevents ordinary publication.
            result_text = _LIMITATION_TEXT[state.kind]
    except Exception:
        failed = True
    else:
        try:
            candidate = AnswerCandidate(text=text, origin=origin, contract=probe.contract,
                                        evidence=probe.evidence, limitations=probe.limitations)
            initial = _checked_decision(candidate, domain)
        except Exception:
            failed = True
        if initial is not None and initial.status is AcceptanceStatus.ACCEPTED:
            result_text, outcome = candidate.text, "accepted"
        else:
            # Exactly one replacement candidate/evaluation. A rejected subset
            # is never published and no recursive repair path is entered.
            used = True
            try:
                replacement_text = _canonical_replacement(state, domain)
                replacement = AnswerCandidate(
                    text=replacement_text, origin=CandidateOrigin.DETERMINISTIC_FALLBACK,
                    contract=probe.contract, evidence=probe.evidence,
                    limitations=probe.limitations,
                )
                replacement_decision = _checked_decision(replacement, domain)
                if replacement_decision.status is AcceptanceStatus.ACCEPTED:
                    result_text, outcome = replacement.text, "replaced"
            except Exception:
                failed = True
    record = AcceptancePublicationRecord(
        path=_safe_path(path), origin=safe_origin, decision=initial,
        replacement_decision=replacement_decision, evaluation_failed=failed,
        replacement_used=used, outcome=outcome,
    )
    if emit:
        try:
            emit_publication_record(record)
        except Exception:
            # A diagnostic hook cannot undo the already bounded publication
            # result or turn an unaccepted candidate into an output.
            pass
    return PublicationResult(result_text, record)


def publish_core_result(*, text, contract, evidence, path="arithmetic",
                        origin=CandidateOrigin.CRITICAL_CORE, emit=False):
    return _publish(
        text=text, contract=contract, origin=origin, path=path, domain="arithmetic",
        evidence_factory=lambda: shadow.normalize_core_evidence(evidence), emit=emit,
    )


def publish_time_budget(*, text, contract, resolution, path="time_budget",
                        origin=CandidateOrigin.CRITICAL_CORE, emit=False):
    return _publish(
        text=text, contract=contract, origin=origin, path=path, domain="time_budget",
        evidence_factory=lambda: shadow._time_budget_evidence(resolution), emit=emit,
    )


def publish_limitation_response(*, text, contract, user_input, conversation=(), user_history=(), path,
                                failure_reason=None, research_result=None,
                                origin=CandidateOrigin.DETERMINISTIC_FALLBACK, emit=True):
    try:
        public_failed = isinstance(research_result, Mapping) and research_result.get("success") is False
    except Exception:
        public_failed = False
    return _publish(
        text=text, contract=contract, origin=origin, path=path, domain="limitation",
        evidence_factory=lambda: shadow._limitation_evidence(
            contract=contract, user_input=user_input, conversation=conversation,
            user_history=user_history, failure_reason=failure_reason, research_result=research_result,
        ), emit=emit, public_failed=public_failed,
    )
