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
from core.answer_candidate import AcceptanceDecision, AcceptanceStatus, AnswerCandidate, CandidateOrigin
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
    "public_verifier_consistency", "public_sentence_support", "public_global_support",
    "source_identity", "source_read_provenance", "official_source_support", "insufficient_scope_support",
    "insufficient_currentness_support",
})
_LIMITATION_MODES = frozenset({
    "insufficient_user_context", "verification_declined",
    "private_state_uncertain", "unobserved_private_state",
})
_PUBLIC_DIAGNOSTIC_LIMITS = frozenset({"scope_verifier_only", "source_bindings_unavailable"})
_BINDING_STATUSES = frozenset({"complete", "incomplete", "malformed", "unavailable"})
_BINDING_ISSUES = frozenset({
    "transport_unavailable", "evaluation_failed", "invalid_output", "incomplete_output",
    "input_limit", "invalid_binding", "unread_source", "wrong_inputs", "missing_annotations",
})
_BINDING_FAILURE_DOMAINS = frozenset({"annotation_capability", "integrity"})
_BINDING_FAILURE_CODES = frozenset({
    "wrong_inputs", "invalid_packet_shape", "invalid_packet_identity", "input_limit",
    "transport_unavailable", "transport_failure", "infrastructure_failure",
    "invalid_annotation_shape", "invalid_annotation_index", "invalid_annotation_semantics",
    "invalid_source_id", "factual_source_missing", "invalid_witness_shape",
    "invalid_literal_witness", "factual_witness_missing", "incomplete_annotations",
    "unread_source", "missing_annotations",
})
_PUBLIC_SENTENCE_FAILURE_CODES = frozenset({
    "legacy_sentence_unsupported", "annotation_limitation_mismatch",
    "annotation_non_factual_mismatch", "factual_witness_missing",
})
_PUBLIC_ANNOTATION_KINDS = frozenset({"factual", "limitation", "non_factual", "unknown"})


def _public_sentence_failures(decision):
    """Filter only bounded public-validator identifiers for developer events.

    Never consume unit text, reasons, witnesses or source contents. A wrong or
    hostile diagnostic payload cannot acquire authority or expose its prose.
    """
    if not isinstance(decision, AcceptanceDecision):
        return ()
    typed = decision.metadata.get("typed_diagnostics", {})
    typed = typed if isinstance(typed, Mapping) else {}
    public = typed.get("public_factual_verifier_provenance", {})
    public = public if isinstance(public, Mapping) else {}
    records = public.get("public_sentence_failures", ())
    if not isinstance(records, (tuple, list)):
        return ()
    safe, seen = [], set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        index, kind, code = (record.get("sentence_index"), record.get("annotation_kind"), record.get("code"))
        if (type(index) is not int or not 1 <= index <= 16
                or not isinstance(kind, str) or kind not in _PUBLIC_ANNOTATION_KINDS
                or not isinstance(code, str) or code not in _PUBLIC_SENTENCE_FAILURE_CODES):
            continue
        key = (index, kind, code)
        if key in seen:
            continue
        seen.add(key)
        safe.append({"sentence_index": index, "annotation_kind": kind, "code": code})
        if len(safe) == 16:
            break
    return tuple(safe)


@dataclass(frozen=True)
class AcceptanceShadowRecord:
    """Runtime observation only; consumers emit ``event``, not the decision."""

    path: str
    origin: CandidateOrigin
    decision: Optional[AcceptanceDecision] = None
    evaluation_failed: bool = False
    diagnostic_limits: tuple[str, ...] = ()
    binding_status: Optional[str] = None
    binding_issue: Optional[str] = None
    binding_failure_domain: Optional[str] = None
    binding_failure_code: Optional[str] = None

    @property
    def metadata(self) -> dict:
        # Invariant identifiers are allowlisted so a faulty evaluator cannot
        # accidentally expose prose through this diagnostic transport.
        invariants = tuple(dict.fromkeys(
            value if value in _INVARIANTS else "unknown_invariant"
            for value in (self.decision.violated_invariants if self.decision else ())
        ))
        metadata = {
            "path": self.path,
            "candidate_origin": self.origin.value,
            "status": self.decision.status.value if self.decision else "evaluation_error",
            "violated_invariants": invariants,
            "evaluation_failed": self.evaluation_failed,
        }
        limits = tuple(dict.fromkeys(value for value in self.diagnostic_limits
                                     if value in _PUBLIC_DIAGNOSTIC_LIMITS))
        if limits:
            metadata["diagnostic_limits"] = limits
        if self.binding_status in _BINDING_STATUSES:
            metadata["source_binding_status"] = self.binding_status
        if self.binding_issue in _BINDING_ISSUES:
            metadata["source_binding_issue"] = self.binding_issue
        if self.binding_failure_domain in _BINDING_FAILURE_DOMAINS:
            metadata["source_binding_failure_domain"] = self.binding_failure_domain
        if self.binding_failure_code in _BINDING_FAILURE_CODES:
            metadata["source_binding_failure_code"] = self.binding_failure_code
        failures = _public_sentence_failures(self.decision)
        if failures:
            metadata["public_sentence_failures"] = failures
        return metadata

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
        events = (self.event,) + tuple(
            "[Core] Acceptance shadow invariants: " + self.path + ": "
            + ",".join(invariants[index:index + 2])
            for index in range(0, len(invariants), 2)
        )
        limits = self.metadata.get("diagnostic_limits", ())
        binding_status = self.metadata.get("source_binding_status")
        if binding_status:
            event = ("[Core] Acceptance shadow bindings: " + self.path
                     + "; status=" + binding_status.upper())
            issue = self.metadata.get("source_binding_issue")
            if issue:
                event += "; issue=" + issue
            events += (event[:180],)
        domain = self.metadata.get("source_binding_failure_domain")
        code = self.metadata.get("source_binding_failure_code")
        if domain or code:
            event = "[Core] Acceptance shadow binding failure: " + self.path
            if domain:
                event += "; domain=" + domain
            if code:
                event += "; code=" + code
            events += (event[:180],)
        for failure in self.metadata.get("public_sentence_failures", ()):
            events += (("[Core] Acceptance shadow sentence: " + self.path
                        + "; index=" + str(failure["sentence_index"])
                        + "; kind=" + failure["annotation_kind"]
                        + "; code=" + failure["code"])[:180],)
        if limits:
            return events + (("[Core] Acceptance shadow limits: " + self.path + ": "
                              + ",".join(limits))[:180],)
        return events


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


def observe_public_factual_response(*, text, contract, research_result, evidence_packet,
                                    verification_result, origin=CandidateOrigin.GENERATED,
                                    emit=True, user_input="", client=None, model=None,
                                    source_bindings=None) -> AcceptanceShadowRecord:
    """Observe a selected full public factual draft without publication authority.

    Only retained Core research and verifier state enters the adapter. There is
    deliberately no conversation argument, publication callback or replacement
    API. Infrastructure and diagnostics failures leave the caller's text alone.
    """
    path = "public_generated_factual"
    safe_origin = origin if isinstance(origin, CandidateOrigin) else CandidateOrigin.GENERATED
    try:
        from core.public_answer_evidence import build_public_answer_candidate
        if source_bindings is None and client is not None and model:
            from core.public_source_bindings import collect_public_source_bindings
            source_bindings = collect_public_source_bindings(
                client=client, model=model, user_input=user_input, text=text,
                evidence_packet=evidence_packet,
            )
        candidate = build_public_answer_candidate(
            text=text, contract=contract, research_result=research_result,
            evidence_packet=evidence_packet, verification_result=verification_result,
            origin=origin, source_bindings=source_bindings, user_input=user_input,
        )
        decision = CoreAcceptanceEvaluator().evaluate(candidate)
        # Do not let malformed/wrong-bound decision objects enter diagnostics.
        if (not isinstance(decision, AcceptanceDecision)
                or not isinstance(decision.status, AcceptanceStatus)
                or decision.evaluated_text != candidate.text
                or not isinstance(decision.violated_invariants, tuple)
                or any(not isinstance(value, str) for value in decision.violated_invariants)):
            raise TypeError("Invalid public shadow decision")
        limits = []
        requirements = candidate.evidence.metadata.get("public_requirements", {})
        if isinstance(requirements, Mapping) and requirements.get("scope_support") == "verifier_only":
            limits.append("scope_verifier_only")
        if candidate.evidence.metadata.get("verifier_source_bindings") == "unavailable":
            limits.append("source_bindings_unavailable")
        bindings = candidate.evidence.metadata.get("public_source_bindings", {})
        status = bindings.get("status") if isinstance(bindings, Mapping) else None
        issue = bindings.get("failure") if isinstance(bindings, Mapping) else None
        domain = bindings.get("failure_domain") if isinstance(bindings, Mapping) else None
        code = bindings.get("failure_code") if isinstance(bindings, Mapping) else None
        record = AcceptanceShadowRecord(
            path, safe_origin, decision, diagnostic_limits=tuple(limits),
            binding_status=status, binding_issue=issue,
            binding_failure_domain=domain, binding_failure_code=code,
        )
    except Exception:
        record = AcceptanceShadowRecord(path, safe_origin, evaluation_failed=True)
    if emit:
        try:
            emit_shadow_record(record)
        except Exception:
            # Also protect against a replaced/broken diagnostic implementation.
            pass
    return record
