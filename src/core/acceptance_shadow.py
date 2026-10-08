"""Non-enforcing acceptance observations for explicitly scoped Core paths.

Evidence is constructed from pre-existing Core results or limitation state,
never from the candidate wording. A shadow record has no publication API.
Only bounded status identifiers are emitted; candidate text, evidence, reasons
and exception messages stay out of developer events. Observation and event
failures cannot change the legacy response.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

from core.acceptance_evaluator import (
    CONDITIONAL_SCOPE, CONTRACT_COMPLETION, EVIDENCE_AUTHORITY,
    MODEL_KNOWLEDGE_NOT_PROOF, ORIGIN_AUTHORITY, REQUIRED_CLAIMS,
    SEMANTIC_COVERAGE, SERIOUS_CONTRACT_TONE, SOURCE_SCOPE,
    UNCERTAINTY_PRESERVATION, USER_FACT_CONSISTENCY, USER_OBSERVATION_SUPPORT,
    CoreAcceptanceEvaluator,
)
from core.answer_candidate import AcceptanceDecision, AnswerCandidate, CandidateOrigin
from core.answer_contract_runtime import coerce_answer_contract_runtime
from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus
from core.evidence_normalization import (
    combine_evidence, normalize_core_evidence, normalize_live_conversation,
    normalize_research_evidence, normalize_user_history, normalize_user_turn,
)
from core.task_budget import TimeBudgetResolution


_EVENT_SINK = ContextVar("core_acceptance_shadow_event_sink", default=None)
_INVARIANTS = frozenset({
    CONDITIONAL_SCOPE, CONTRACT_COMPLETION, EVIDENCE_AUTHORITY,
    MODEL_KNOWLEDGE_NOT_PROOF, ORIGIN_AUTHORITY, REQUIRED_CLAIMS,
    SEMANTIC_COVERAGE, SERIOUS_CONTRACT_TONE, SOURCE_SCOPE,
    UNCERTAINTY_PRESERVATION, USER_FACT_CONSISTENCY, USER_OBSERVATION_SUPPORT,
})
_LIMITATION_MODES = frozenset({
    "insufficient_user_context", "verification_declined",
    "private_state_uncertain", "unobserved_private_state",
})


@dataclass(frozen=True)
class AcceptanceShadowRecord:
    """Runtime observation only; consumers emit ``event``, not the decision."""

    path: str
    origin: CandidateOrigin
    decision: Optional[AcceptanceDecision] = None
    evaluation_failed: bool = False

    @property
    def metadata(self) -> dict:
        # Invariant identifiers are allowlisted so a faulty evaluator cannot
        # accidentally expose prose through this diagnostic transport.
        invariants = tuple(dict.fromkeys(
            value if value in _INVARIANTS else "unknown_invariant"
            for value in (self.decision.violated_invariants if self.decision else ())
        ))
        return {
            "path": self.path,
            "candidate_origin": self.origin.value,
            "status": self.decision.status.value if self.decision else "evaluation_error",
            "violated_invariants": invariants,
            "evaluation_failed": self.evaluation_failed,
        }

    @property
    def event(self) -> str:
        value = self.metadata
        invariants = str(len(value["violated_invariants"])) if value["violated_invariants"] else "none"
        return (
            "[Core] Acceptance shadow: " + value["status"].upper()
            + "; origin=" + value["candidate_origin"]
            + "; path=" + value["path"]
            + "; invariants=" + invariants
        )[:180]

    @property
    def events(self) -> tuple[str, ...]:
        # The existing desktop clips each event at 180 characters. Separate
        # bounded identifier lines retain every violation without prose or
        # relying on a discarded provider record remaining inspectable.
        invariants = self.metadata["violated_invariants"]
        return (self.event,) + tuple(
            "[Core] Acceptance shadow invariants: " + self.path + ": "
            + ",".join(invariants[index:index + 2])
            for index in range(0, len(invariants), 2)
        )


@contextmanager
def acceptance_shadow_events(sink: Callable[[str], None]):
    """Route only shadow events to this request's existing developer sink."""
    token = _EVENT_SINK.set(sink if callable(sink) else None)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


def emit_shadow_record(record: Optional[AcceptanceShadowRecord], sink=None) -> None:
    """Diagnostic failure has no authority over the caller's response."""
    if record is None:
        return
    try:
        callback = sink if callable(sink) else _EVENT_SINK.get()
        callback = callback if callable(callback) else print
        for event in record.events:
            callback(event)
    except Exception:
        pass


def _observe(*, text, contract, origin, path, evidence_factory, emit=False):
    # Paths are static Core call-site identifiers, never user/model/source text.
    safe_path = "unknown"
    try:
        safe_path = "".join(character for character in path if character.isascii()
                            and (character.isalnum() or character in "_.-"))[:48]
        bundle = evidence_factory()
        limitations = tuple(dict.fromkeys(
            ([bundle.uncertainty] if bundle.uncertainty else [])
            + [reason for item in bundle.evidence if item.kind == EvidenceKind.UNCERTAINTY
               for reason in item.limitations]
        ))
        candidate = AnswerCandidate(
            text=text, origin=origin,
            contract=coerce_answer_contract_runtime(contract),
            evidence=bundle, limitations=limitations,
        )
        decision = CoreAcceptanceEvaluator().evaluate(candidate)
        if not isinstance(decision, AcceptanceDecision):
            raise TypeError("A shadow evaluator must return an AcceptanceDecision")
        record = AcceptanceShadowRecord(safe_path, origin, decision)
    except Exception:
        # Do not emit exception text: an exception may contain private inputs.
        record = AcceptanceShadowRecord(safe_path, origin, evaluation_failed=True)
    if emit:
        emit_shadow_record(record)
    return record


def observe_core_result(*, text, contract, evidence, path="arithmetic") -> AcceptanceShadowRecord:
    """Use the workflow's actual evidence, including its trusted provenance."""
    return _observe(
        text=text, contract=contract, origin=CandidateOrigin.CRITICAL_CORE,
        path=path, evidence_factory=lambda: normalize_core_evidence(evidence),
    )


def _time_budget_evidence(resolution: TimeBudgetResolution) -> EvidenceBundle:
    if not isinstance(resolution, TimeBudgetResolution):
        raise TypeError("Time-budget evidence requires the Core result object")
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in (
        resolution.budget_minutes, resolution.used_minutes,
    )):
        raise ValueError("The Core result must contain finite numerical values")
    data = {
        "result_kind": "time_budget",
        "budget_minutes": str(resolution.budget_minutes),
        "used_minutes": str(resolution.used_minutes),
        "remaining_minutes": str(resolution.budget_minutes - resolution.used_minutes),
        "items": [{"name": name, "minutes": str(minutes)} for name, minutes in resolution.items],
        "conditional_on_supplied_inputs": True,
        "delay_minutes": str(resolution.delay_minutes),
        "delay_target": resolution.delay_target,
        "required_outputs": ("used", "comparison", "remaining"),
    }
    # Atomic claims are rendered from retained calculation fields. In
    # particular, resolution.answer and the published text are never evidence.
    claims = (
        ("budget", f"The time budget is {data['budget_minutes']} minutes."),
        ("used", f"The time used is {data['used_minutes']} minutes."),
        ("remaining", f"The remaining time is {data['remaining_minutes']} minutes."),
    )
    return EvidenceBundle(
        authority="user_turn_reasoning", canonical=True, success=True,
        evidence=[Evidence(
            claim=claim, provenance="core_time_budget", confidence="verified",
            kind=EvidenceKind.CORE_RESULT, status=EvidenceStatus.ADMISSIBLE,
            authority_scope="deterministic_result", evidence_id="time_budget:" + name,
            data=data,
        ) for name, claim in claims],
    ).snapshot()


def observe_time_budget(*, text, contract, resolution, path="time_budget") -> AcceptanceShadowRecord:
    return _observe(
        text=text, contract=contract, origin=CandidateOrigin.CRITICAL_CORE,
        path=path, evidence_factory=lambda: _time_budget_evidence(resolution),
    )


def _limitation_evidence(*, contract, user_input, conversation, user_history, failure_reason, research_result):
    runtime = coerce_answer_contract_runtime(contract)
    if runtime is None:
        raise ValueError("A limitation observation requires an established Core contract")
    mode = runtime.epistemic_mode
    research_failed = isinstance(research_result, Mapping) and research_result.get("success") is False
    if mode not in _LIMITATION_MODES and not research_failed:
        raise ValueError("A limitation must exist before the answer is constructed")
    if mode == "insufficient_user_context":
        reason = "Required user input is unavailable."
    elif mode == "verification_declined":
        reason = "Exact current information cannot be verified under the user's verification constraint."
    elif mode in {"private_state_uncertain", "unobserved_private_state"}:
        reason = "The requested private state is not observable from the supplied context."
    else:
        reason = "Required public evidence is unavailable."
    availability = {"version": 1, "scope": runtime.subject}
    if mode == "insufficient_user_context":
        # Reuse the existing Core extractor of explicitly omitted input. It
        # reads the user turn and never infers absence from response wording.
        from core.missing_inputs import extract_missing_inputs
        missing = extract_missing_inputs(user_input)
        availability.update({
            "kind": "missing_input", "input_available": False,
            "missing_inputs": missing.items if missing is not None else (),
        })
    elif mode == "verification_declined":
        availability.update({
            "kind": "verification_declined", "verification_required": True,
            "verification_declined": True,
        })
    elif mode in {"private_state_uncertain", "unobserved_private_state"}:
        availability.update({"kind": "private_state", "observation_available": False})
    else:
        availability.update({
            "kind": "public_evidence_unavailable", "verification_required": True,
            "retrieval_failed": True, "supporting_evidence_available": False,
        })
    limitations = (reason,)
    if isinstance(failure_reason, str) and failure_reason.strip():
        limitations += (failure_reason.strip(),)
    limitation = EvidenceBundle(
        authority=runtime.authority, canonical=True, success=False, uncertainty=reason,
        evidence=[Evidence(
            claim="", provenance="core_evidence_availability", confidence="unavailable",
            kind=EvidenceKind.UNCERTAINTY, status=EvidenceStatus.UNAVAILABLE,
            authority_scope="evidence_availability", limitations=limitations,
            evidence_id="limitation:" + mode,
            data={"epistemic_mode": mode, "research_failed": research_failed, "availability": availability},
        )],
    ).snapshot()
    bundles = [normalize_user_turn(user_input), normalize_live_conversation(conversation), limitation]
    if user_history:
        bundles.append(normalize_user_history(user_history))
    if research_failed:
        bundles.append(normalize_research_evidence(research_result, kind=EvidenceKind.PUBLIC_SOURCE))
    return combine_evidence(*bundles, authority=runtime.authority)


def observe_limitation_response(*, text, contract, user_input, conversation=(), user_history=(), path,
                                failure_reason=None, research_result=None,
                                origin=CandidateOrigin.DETERMINISTIC_FALLBACK,
                                emit=True) -> AcceptanceShadowRecord:
    """Observe a selected Core fallback, using pre-answer absence/failure state."""
    return _observe(
        text=text, contract=contract, origin=origin,
        path=path, evidence_factory=lambda: _limitation_evidence(
            contract=contract, user_input=user_input, conversation=conversation, user_history=user_history,
            failure_reason=failure_reason, research_result=research_result,
        ), emit=emit,
    )
