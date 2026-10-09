"""Core-owned, origin-independent acceptance policy for canonical candidates.

This evaluator neither publishes nor rewrites wording. Its bounded interpreter
supports conservative restatement and explicit authority checks, not arbitrary
natural-language entailment. Unresolved claims require replacement/review rather
than permission from a model verdict, a fallback origin, or a flattened string.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional, Tuple

from core.acceptance_semantics import (
    ClaimUnit, Proposition, UnitKind, canonical_statement, conflicting_propositions, interpret_text,
)
from core.answer_candidate import (
    AcceptanceDecision, AcceptanceStatus, AcceptedSentence, AnswerCandidate,
)
from core.evidence import Evidence, EvidenceKind, EvidenceStatus
from core.acceptance_typed import validate_typed_evidence


USER_FACT_CONSISTENCY = "user_fact_consistency"
USER_OBSERVATION_SUPPORT = "user_observation_support"
CONDITIONAL_SCOPE = "conditional_scope"
EVIDENCE_AUTHORITY = "evidence_authority"
SOURCE_SCOPE = "source_scope"
MODEL_KNOWLEDGE_NOT_PROOF = "model_knowledge_not_proof"
SERIOUS_CONTRACT_TONE = "serious_contract_tone"
UNCERTAINTY_PRESERVATION = "uncertainty_preservation"
SEMANTIC_COVERAGE = "semantic_coverage"
REQUIRED_CLAIMS = "required_claims"
ORIGIN_AUTHORITY = "origin_authority"
CONTRACT_COMPLETION = "contract_completion"

_USER_KINDS = frozenset({
    EvidenceKind.CURRENT_USER_TURN, EvidenceKind.LIVE_USER_FACT, EvidenceKind.USER_CORRECTION,
})
_SOURCE_KINDS = frozenset({EvidenceKind.PUBLIC_SOURCE, EvidenceKind.MEDIA_SOURCE})
_USER_PROVENANCE = frozenset({"current_user_turn", "live_user_authored"})
_MISSING_MODES = frozenset({
    "insufficient_user_context", "verification_declined", "private_state_uncertain",
})


@dataclass(frozen=True)
class _Fact:
    evidence: Evidence
    proposition: Proposition


def _truth_flag(value) -> bool:
    return value is True or (isinstance(value, str) and value.lower() in {"true", "high", "required"})


def _serious(contract) -> bool:
    return (
        contract.intent == "consequential_advice"
        or _truth_flag(contract.metadata.get("seriousness"))
        or bool(contract.metadata.get("consequence_domain"))
    )


def _speaker(item: Evidence) -> str:
    if item.kind in _USER_KINDS or item.kind == EvidenceKind.SUPPLIED_PREMISE:
        return "user"
    if item.kind == EvidenceKind.CORE_RESULT:
        return "core"
    return "source"


def _source_veto(item: Evidence) -> bool:
    data = item.data
    alignment = data.get("medium_alignment")
    read = data.get("read_result")
    return (
        any(key in data and data[key] is not True
            for key in ("accepted_as_evidence", "read_success"))
        or data.get("relevance_status") == "rejected"
        or ("read_result" in data and (
            not isinstance(read, Mapping) or read.get("success") is not True
        ))
        or (type(alignment) in (int, float) and alignment < 0)
        or (isinstance(alignment, str) and alignment in {"mismatch", "incompatible", "rejected"})
    )


def _eligible(item: Evidence) -> bool:
    """Typed eligibility is necessary; scoped provenance is necessary as well."""
    if item.status != EvidenceStatus.ADMISSIBLE or not item.claim.strip():
        return False
    if item.kind in _USER_KINDS:
        return item.authority_scope == "what_the_user_stated" and item.provenance in _USER_PROVENANCE
    if item.kind == EvidenceKind.SUPPLIED_PREMISE:
        return item.authority_scope == "conditional_premise" and item.provenance == "user_supplied_premise"
    if item.kind == EvidenceKind.CORE_RESULT:
        return (
            item.confidence == "verified" and item.provenance.startswith("core_")
            and item.authority_scope in {"core_result", "deterministic_result", "user_observation", "tool_observation"}
        )
    if item.kind in _SOURCE_KINDS:
        provenance = "core_public_source" if item.kind == EvidenceKind.PUBLIC_SOURCE else "core_media_source"
        return (
            item.authority_scope == "retrieved_source_assertions"
            and item.provenance == provenance and bool(item.source_url)
            and not _source_veto(item)
        )
    return False


def _same_statement(left: Proposition, right: Proposition) -> bool:
    # Canonicalization binds speaker roles, negation, and wording. It does not
    # infer arbitrary paraphrases, numerical causation, or stronger sentiments.
    return bool(left.canonical) and left.canonical == right.canonical


def _constraint_records(metadata: Mapping):
    """Walk only known canonical constraint containers, never source-body text."""
    yield metadata
    for field in ("bundles", "packet_constraints"):
        for record in metadata.get(field, ()):
            if isinstance(record, Mapping):
                yield from _constraint_records(record)


def _source_constraints(candidate: AnswerCandidate, item: Evidence, proposition: Proposition) -> Optional[str]:
    contract = candidate.contract
    records = [contract.metadata, *_constraint_records(candidate.evidence.metadata)]
    if item.kind == EvidenceKind.PUBLIC_SOURCE and contract.authority == "media_research":
        return "Public evidence cannot substitute for the requested media authority"
    if item.kind == EvidenceKind.MEDIA_SOURCE and contract.authority == "public_web":
        return "Media evidence cannot substitute for the requested public authority"
    if _truth_flag(contract.metadata.get("source_quality_required")) and item.quality_eligible is not True:
        return "This contract requires qualifying source authority; supporting/unknown quality is insufficient"
    required_tier = contract.metadata.get("required_authority_tier")
    if required_tier and item.authority_tier != required_tier:
        return "The source does not meet the contract's required authority tier"
    if proposition.personal:
        return "Public/media source text is not observation of the current user"
    if item.kind == EvidenceKind.MEDIA_SOURCE:
        for record in records:
            requested = record.get("requested_medium")
            if requested and item.data.get("source_medium") != requested:
                return "Media evidence does not establish the requested medium"
            answer_scope = record.get("answer_scope")
            if isinstance(answer_scope, Mapping):
                permitted = answer_scope.get("scope")
                # A content ceiling must be explicitly established by Core
                # selection; the evaluator cannot guess spoiler safety from prose.
                if permitted and item.data.get("content_scope") != permitted:
                    return "Media source content is not established within the required answer scope"
                classes = answer_scope.get("allowed_claim_classes")
                if classes and item.data.get("claim_class") not in classes:
                    return "Media source claim class is outside or unresolved under the answer scope"
                excluded = answer_scope.get("exclude_even_if_sourced", ())
                if item.data.get("claim_class") in excluded:
                    return "Core excluded this media claim class even if sourced"
    if contract.subject and item.data.get("subject") and item.data["subject"] != contract.subject:
        return "Source identity is outside the contract subject"
    for record in records:
        if _truth_flag(record.get("freshness_required")):
            runtime_date = record.get("runtime_date") or contract.metadata.get("runtime_date")
            if not runtime_date or item.data.get("current_as_of") != runtime_date:
                return "The source has not established the contract's current state"
    return None


def _deterministic(contract) -> bool:
    return contract.authority in {"core_arithmetic", "core_results", "verified_core"} or contract.epistemic_mode in {
        "deterministic_calculation", "tool_verified", "tool_result", "verified_core",
    }


def _payload_fact(candidate: AnswerCandidate, fact: _Fact) -> bool:
    """A valid report may be context without completing a verified task."""
    if _deterministic(candidate.contract):
        return fact.evidence.kind == EvidenceKind.CORE_RESULT
    if candidate.contract.authority == "public_web":
        return fact.evidence.kind == EvidenceKind.PUBLIC_SOURCE
    if candidate.contract.authority == "media_research":
        return fact.evidence.kind == EvidenceKind.MEDIA_SOURCE
    return True


def _allows_fact(candidate: AnswerCandidate, fact: _Fact, proposition: Proposition) -> Optional[str]:
    item, known = fact.evidence, fact.proposition
    if not _eligible(item):
        return "Evidence is rejected, unavailable, unassessed, or lacks trusted scoped provenance"
    if known.reported:
        if not proposition.reported or known.reporter != proposition.reporter:
            return "Reported dialogue/source assertions cannot establish the reported body's truth"
        if item.kind in _USER_KINDS and known.reporter != "$user":
            return "A user's quotation of prior assistant/third-party dialogue is not confirmation of its facts"
    if proposition.reported:
        if item.kind in _USER_KINDS and proposition.reporter != "$user":
            return "User-authored evidence can establish only the user's own reporting scope"
        if item.kind in _SOURCE_KINDS:
            identities = {canonical_statement(value, speaker="source") for value in (
                item.source_name, item.source_url, item.source_id,
            ) if value}
            if proposition.reporter not in identities:
                return "The candidate's attributed source is not the source whose evidence was supplied"
        if item.kind == EvidenceKind.CORE_RESULT and proposition.reporter not in {"core", "the core"}:
            return "A Core result cannot establish an unrelated speaker's attribution"
    if known.conditional and not proposition.conditional:
        return "A conditional source assertion cannot establish an unconditional claim"
    if known.condition and known.condition != proposition.condition:
        return "The candidate changed the condition under which evidence applies"
    if item.kind == EvidenceKind.SUPPLIED_PREMISE:
        if not proposition.conditional:
            return "A supplied premise can support only explicitly conditional reasoning"
        if candidate.contract.epistemic_mode not in {"user_premise_reasoning", "user_context_reasoning"}:
            return "This contract does not authorize premise-scoped reasoning"
        required_condition = item.data.get("condition") or known.condition or known.canonical
        if not isinstance(required_condition, str) or proposition.condition != canonical_statement(
            required_condition, speaker="user", user_name=candidate.contract.metadata.get("user_name")
        ):
            return "The candidate changed the premise's conditional scope"
    if _deterministic(candidate.contract) and not proposition.reported and item.kind != EvidenceKind.CORE_RESULT:
        return "A deterministic/tool-result contract requires corresponding verified Core results"
    if item.kind in _USER_KINDS:
        if candidate.contract.authority in {"public_web", "media_research"} and not proposition.personal and not proposition.reported:
            return "A user's external assertion is evidence of what they said, not public/media verification"
    if proposition.personal and item.kind == EvidenceKind.CORE_RESULT:
        if item.authority_scope not in {"user_observation", "tool_observation"}:
            return "A general Core result cannot establish a present observation of the user"
    if item.kind in _SOURCE_KINDS:
        return _source_constraints(candidate, item, proposition)
    return None


def _limitation_reasons(candidate: AnswerCandidate) -> Tuple[str, ...]:
    values = list(candidate.limitations)
    if candidate.evidence.uncertainty:
        values.append(candidate.evidence.uncertainty)
    for item in candidate.evidence.evidence:
        if item.kind == EvidenceKind.UNCERTAINTY:
            values.extend(item.limitations)
            if item.claim:
                values.append(item.claim)
    return tuple(dict.fromkeys(value for value in values if value))


def _acknowledges_limitation(unit: ClaimUnit, candidate: AnswerCandidate, reasons: Tuple[str, ...]) -> bool:
    if not unit.complete or unit.kind != UnitKind.LIMITATION or unit.propositions:
        return False
    normalized = canonical_statement(unit.text)
    if any(normalized == canonical_statement(reason) for reason in reasons):
        return True
    target = canonical_statement(unit.limitation_target)
    if not target or target in {"that", "this", "it", "the answer", "the result"}:
        return True
    subject = canonical_statement(candidate.contract.subject or "")
    explicit_scope = canonical_statement(candidate.contract.metadata.get("uncertainty_scope", ""))
    return bool((subject and subject in target) or (explicit_scope and explicit_scope == target)
                or any(target and target in canonical_statement(reason) for reason in reasons))


def _required_present(text: str, candidate: AnswerCandidate, typed_satisfied=()) -> bool:
    rendered = canonical_statement(text, user_name=candidate.contract.metadata.get("user_name"))
    return all(required in typed_satisfied or canonical_statement(required, user_name=candidate.contract.metadata.get("user_name")) in rendered
               for required in candidate.contract.required_claims)


def _requires_payload(contract) -> bool:
    return _deterministic(contract) or contract.authority in {"public_web", "media_research"} or contract.intent in {
        "factual_question", "consequential_advice", "conversation_recall", "order_status",
    } or contract.epistemic_mode in {
        "deterministic_calculation", "user_premise_reasoning", "user_context_reasoning",
    }


class CoreAcceptanceEvaluator:
    """Enforce scoped support, contradiction, task, and uncertainty invariants.

    All checks are derived from the contract, typed evidence, and interpreted
    task claims. Candidate origin and candidate validation_metadata are never
    consulted as authority. No model, tool, persistence, or publication is called.
    """

    def evaluate(self, candidate: AnswerCandidate) -> AcceptanceDecision:
        if not isinstance(candidate, AnswerCandidate):
            raise TypeError("Core acceptance requires an AnswerCandidate")
        user_name = candidate.contract.metadata.get("user_name")
        if user_name is not None and not isinstance(user_name, str):
            raise TypeError("Core user_name must be a scalar string")
        units = interpret_text(candidate.text, speaker="assistant", user_name=user_name)
        typed = validate_typed_evidence(candidate, units)
        facts = []
        superseded = {
            identity for item in candidate.evidence.evidence
            if item.kind == EvidenceKind.USER_CORRECTION and _eligible(item)
            for identity in item.supersedes
        }
        # Preserve associated records even for rejected source matches so the
        # rejection reason cannot disappear behind a matching literal string.
        for item in candidate.evidence.evidence:
            if item.kind in _USER_KINDS | {EvidenceKind.SUPPLIED_PREMISE} and item.evidence_id in superseded:
                continue
            for unit in interpret_text(item.claim, speaker=_speaker(item), user_name=user_name):
                if not unit.complete:
                    continue
                for proposition in unit.propositions:
                    facts.append(_Fact(item, proposition))
        facts = tuple(facts)
        limitations = _limitation_reasons(candidate)
        missing = bool(limitations) or candidate.contract.epistemic_mode in _MISSING_MODES
        serious = _serious(candidate.contract)
        applicable = [ORIGIN_AUTHORITY, EVIDENCE_AUTHORITY, SEMANTIC_COVERAGE, REQUIRED_CLAIMS, CONTRACT_COMPLETION]
        if any(item.kind in _USER_KINDS for item in candidate.evidence.evidence) or any(prop.personal for unit in units for prop in unit.propositions):
            applicable.extend([USER_FACT_CONSISTENCY, USER_OBSERVATION_SUPPORT])
        if any(item.kind == EvidenceKind.SUPPLIED_PREMISE for item in candidate.evidence.evidence) or any(prop.conditional for unit in units for prop in unit.propositions):
            applicable.append(CONDITIONAL_SCOPE)
        if any(item.kind in _SOURCE_KINDS for item in candidate.evidence.evidence) or candidate.contract.authority in {"public_web", "media_research"}:
            applicable.append(SOURCE_SCOPE)
        if candidate.evidence.model_knowledge_permitted or candidate.contract.epistemic_mode == "stable_model_knowledge":
            applicable.append(MODEL_KNOWLEDGE_NOT_PROOF)
        if serious:
            applicable.append(SERIOUS_CONTRACT_TONE)
        if missing:
            applicable.append(UNCERTAINTY_PRESERVATION)
        reasons, violations, accepted, reports = [], [], [], []
        global_reject = False
        replacement = False
        acknowledged = False
        payload = False
        typed_obligations = {profile.validator: set() for profile in typed}
        for profile in typed:
            if profile.global_violations:
                violations.extend(profile.global_violations)
                reasons.extend(profile.global_reasons)
                global_reject = True
        if not units:
            reasons.append("The candidate contains no assessable answer")
            violations.append(SEMANTIC_COVERAGE)
            replacement = True
        for unit in units:
            failures, unit_reasons, support = [], [], []
            unit_payload = False
            typed_proofs = [(profile, profile.units[unit.index]) for profile in typed if unit.index in profile.units]
            for profile, proof in typed_proofs:
                failures.extend(proof.violated_invariants)
                unit_reasons.extend(proof.reasons)
                support.extend(proof.evidence_ids)
                unit_payload = unit_payload or bool(proof.obligations)
            if serious and any(behavior in {"blame", "ridicule", "casual_roast"} for behavior in unit.behaviors):
                failures.append(SERIOUS_CONTRACT_TONE)
                unit_reasons.append("The serious/consequential contract forbids blame, ridicule, or casual roasting")
                global_reject = True
            caveat = missing and (
                any(proof.limitation_preserved and not proof.violated_invariants for _, proof in typed_proofs)
                if typed_proofs else _acknowledges_limitation(unit, candidate, limitations)
            )
            if caveat:
                acknowledged = True
            elif not typed_proofs and (not unit.complete or unit.kind == UnitKind.UNKNOWN):
                failures.append(SEMANTIC_COVERAGE)
                unit_reasons.append("Core cannot establish complete bounded semantic coverage for this unit")
                replacement = True
            elif not typed_proofs and unit.kind == UnitKind.LIMITATION:
                failures.append(UNCERTAINTY_PRESERVATION)
                unit_reasons.append("The limitation does not match Core's established uncertainty or task scope")
            elif unit.kind == UnitKind.QUESTION and not candidate.contract.allow_follow_up_question:
                failures.append(CONTRACT_COMPLETION)
                unit_reasons.append("The answer contract does not authorize a follow-up question")
            # Typed coverage replaces only the domain's generic support parse.
            # User contradictions and the serious-tone invariant still apply.
            for proposition in unit.propositions:
                current_support = any(
                    fact.evidence.kind in {EvidenceKind.CURRENT_USER_TURN, EvidenceKind.USER_CORRECTION}
                    and _eligible(fact.evidence) and not fact.proposition.conditional
                    and not fact.proposition.reported and _same_statement(proposition, fact.proposition)
                    for fact in facts
                )
                contradicted = any(
                    fact.evidence.kind in _USER_KINDS and _eligible(fact.evidence)
                    and not fact.proposition.conditional and not fact.proposition.reported
                    and not proposition.reported and conflicting_propositions(proposition, fact.proposition)
                    and (not current_support or fact.evidence.kind != EvidenceKind.LIVE_USER_FACT)
                    for fact in facts
                )
                if contradicted:
                    failures.append(USER_FACT_CONSISTENCY)
                    unit_reasons.append("The claim contradicts active current-turn/live user-authored evidence")
                    continue
                if caveat or typed_proofs:
                    continue
                matches = [fact for fact in facts if _same_statement(proposition, fact.proposition)]
                allowed = [fact for fact in matches if _allows_fact(candidate, fact, proposition) is None]
                if allowed:
                    support.extend(fact.evidence.evidence_id for fact in allowed if fact.evidence.evidence_id)
                    unit_payload = unit_payload or any(_payload_fact(candidate, fact) for fact in allowed)
                    continue
                if proposition.personal:
                    failures.append(USER_OBSERVATION_SUPPORT if proposition.observation else USER_FACT_CONSISTENCY)
                    unit_reasons.append("No corresponding scoped user/tool evidence establishes this personal action, state, or fact")
                elif any(fact.evidence.kind == EvidenceKind.SUPPLIED_PREMISE or fact.proposition.conditional for fact in matches):
                    failures.append(CONDITIONAL_SCOPE)
                    unit_reasons.append("The candidate asserts a premise or conditional claim outside its permitted condition")
                elif matches:
                    scoped = [fact for fact in matches if _eligible(fact.evidence)]
                    failures.append(SOURCE_SCOPE if scoped else EVIDENCE_AUTHORITY)
                    unit_reasons.append(_allows_fact(candidate, matches[0], proposition) or "The matching evidence cannot establish this claim")
                else:
                    failures.append(EVIDENCE_AUTHORITY)
                    unit_reasons.append("No admissible evidence establishes this assertion within the contract's authority scope")
                    replacement = True
                if candidate.evidence.model_knowledge_permitted:
                    failures.append(MODEL_KNOWLEDGE_NOT_PROOF)
                    unit_reasons.append("Stable-model-knowledge permission does not establish this particular claim as true")
                if missing:
                    failures.append(UNCERTAINTY_PRESERVATION)
                    unit_reasons.append("Candidate prose cannot fill an established evidence gap")
            failures = list(dict.fromkeys(failures))
            if not failures:
                accepted.append(AcceptedSentence(unit.index, unit.text))
                payload = payload or unit_payload or caveat
                for profile, proof in typed_proofs:
                    typed_obligations[profile.validator].update(proof.obligations)
            else:
                violations.extend(failures)
                reasons.extend(f"Sentence {unit.index}: {reason}" for reason in dict.fromkeys(unit_reasons))
            reports.append({"index": unit.index, "text": unit.text, "violated_invariants": failures,
                            "supported_by": tuple(dict.fromkeys(support))})
        global_missing = []
        if missing and not acknowledged:
            global_missing.append((UNCERTAINTY_PRESERVATION, "The candidate omits Core's explicit uncertainty or missing-evidence limitation"))
        subset = " ".join(item.text for item in accepted)
        typed_required = {
            claim for profile in typed for claim, obligations in profile.required_claim_obligations.items()
            if set(obligations) <= typed_obligations[profile.validator]
        }
        if not _required_present(subset, candidate, typed_required):
            global_missing.append((REQUIRED_CLAIMS, "The acceptable sentence subset does not retain the contract's required claims"))
        typed_complete = all(set(profile.completion_obligations) <= typed_obligations[profile.validator] for profile in typed)
        if (_requires_payload(candidate.contract) and not payload) or not typed_complete:
            global_missing.append((CONTRACT_COMPLETION, "The candidate has no supported answer or valid task-scoped limitation"))
        for invariant, reason in global_missing:
            violations.append(invariant)
            reasons.append(reason)
        if global_reject:
            status, subset_units = AcceptanceStatus.REJECTED, ()
        elif global_missing:
            # Definite authority violations still reject the current candidate;
            # absence/incomplete coverage requires a Core replacement.
            definite = any(invariant in {
                USER_FACT_CONSISTENCY, USER_OBSERVATION_SUPPORT, CONDITIONAL_SCOPE, SOURCE_SCOPE,
            } for invariant in violations) or any(report["violated_invariants"] == [EVIDENCE_AUTHORITY] for report in reports)
            status = AcceptanceStatus.REJECTED if definite and not replacement else AcceptanceStatus.REPLACEMENT_REQUIRED
            subset_units = ()
        elif not violations:
            status, subset_units = AcceptanceStatus.ACCEPTED, tuple(accepted)
        elif accepted:
            status, subset_units = AcceptanceStatus.SALVAGEABLE, tuple(accepted)
        elif replacement:
            status, subset_units = AcceptanceStatus.REPLACEMENT_REQUIRED, ()
        else:
            status, subset_units = AcceptanceStatus.REJECTED, ()
        return AcceptanceDecision(
            status=status, evaluated_text=candidate.text,
            reasons=tuple(dict.fromkeys(reasons)), violated_invariants=tuple(dict.fromkeys(violations)),
            accepted_sentences=subset_units,
            metadata={"applicable_invariants": tuple(dict.fromkeys(applicable)), "units": reports,
                      "limitations": limitations, "semantic_policy": "bounded_core_restatement",
                      "typed_validators": tuple(profile.validator for profile in typed),
                      **({"typed_diagnostics": {
                          profile.validator: profile.diagnostic_metadata
                          for profile in typed if profile.diagnostic_metadata
                      }} if any(profile.diagnostic_metadata for profile in typed) else {})},
        )
