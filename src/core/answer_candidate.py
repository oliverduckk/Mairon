"""Typed transport for Core evidence, answer candidates, and future decisions.

This module does not accept or publish answers. Origin describes how wording was
produced; it never grants factual authority or substitutes for Core acceptance.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Protocol, Tuple

from core.answer_contract_runtime import AnswerContractRuntime
from core.evidence import EvidenceBundle, freeze_metadata


class CandidateOrigin(str, Enum):
    GENERATED = "generated"
    RETRY = "retry"
    SALVAGE = "salvage"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    EXTRACTIVE_FALLBACK = "extractive_fallback"
    CRITICAL_CORE = "critical_core"


def _text_tuple(value: Any, name: str) -> Tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{name} must be a sequence of strings")
    if any(not isinstance(item, str) for item in value):
        raise TypeError(f"{name} must contain only strings")
    return tuple(value)


def _snapshot_contract(contract: AnswerContractRuntime) -> AnswerContractRuntime:
    """Detach the runtime's shallowly frozen dictionaries and claim sequences."""
    if not isinstance(contract, AnswerContractRuntime):
        raise TypeError("contract must be an AnswerContractRuntime")
    return replace(
        contract,
        required_claims=_text_tuple(contract.required_claims, "required_claims"),
        verified_evidence_claims=_text_tuple(
            contract.verified_evidence_claims, "verified_evidence_claims"
        ),
        forbidden_behaviours=_text_tuple(
            contract.forbidden_behaviours, "forbidden_behaviours"
        ),
        resolved_referents=freeze_metadata(contract.resolved_referents),
        metadata=freeze_metadata(contract.metadata),
    )


@dataclass(frozen=True)
class AnswerCandidate:
    """One wording candidate with detached, immutable Core context.

    Raw packets must be normalized before construction. The runtime contract
    remains the source of intent and authority; candidate prose and origin are
    not used to infer either. Validation metadata is a record attached to this
    wording, not a publication decision. There is deliberately no text-changing
    helper that could carry an earlier draft's validation into new wording.
    """

    text: str
    origin: CandidateOrigin
    contract: AnswerContractRuntime
    evidence: EvidenceBundle
    limitations: Tuple[str, ...] = field(default_factory=tuple)
    validation_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("candidate text must be a string")
        if not isinstance(self.origin, CandidateOrigin):
            raise TypeError("origin must be a CandidateOrigin")
        if not isinstance(self.evidence, EvidenceBundle):
            raise TypeError("evidence must be an EvidenceBundle")
        if self.evidence.canonical is not True:
            raise ValueError("candidate evidence must already be canonical")
        if not isinstance(self.validation_metadata, Mapping):
            raise TypeError("validation_metadata must be a mapping")
        object.__setattr__(self, "contract", _snapshot_contract(self.contract))
        object.__setattr__(self, "evidence", self.evidence.snapshot())
        object.__setattr__(
            self, "limitations", _text_tuple(self.limitations, "limitations")
        )
        object.__setattr__(
            self, "validation_metadata", freeze_metadata(self.validation_metadata)
        )

    @property
    def intent(self) -> str:
        return self.contract.intent

    @property
    def authority(self) -> str:
        return self.contract.authority

    @property
    def epistemic_mode(self) -> str:
        return self.contract.epistemic_mode

    def with_origin(self, origin: CandidateOrigin) -> "AnswerCandidate":
        """Change only the diagnostic production origin, retaining all context."""
        return replace(self, origin=origin)


class AcceptanceStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SALVAGEABLE = "salvageable"
    REPLACEMENT_REQUIRED = "replacement_required"


@dataclass(frozen=True)
class AcceptedSentence:
    """An approved unit identified by its original one-based verifier index."""

    index: int
    text: str

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 1:
            raise ValueError("sentence index must be a positive integer")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("sentence text must be a non-empty string")


@dataclass(frozen=True)
class AcceptanceDecision:
    """Future Core acceptance result, bound to the exact assessed wording.

    Sentence indexes refer to the evaluator's original segmentation. This
    transport validates subset structure, not sentence support or truth. A later
    Core evaluator must establish those facts under the candidate's contract and
    evidence. No production path invokes an evaluator in this milestone.
    """

    status: AcceptanceStatus
    evaluated_text: str
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    violated_invariants: Tuple[str, ...] = field(default_factory=tuple)
    accepted_sentences: Tuple[AcceptedSentence, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, AcceptanceStatus):
            raise TypeError("status must be an AcceptanceStatus")
        if not isinstance(self.evaluated_text, str):
            raise TypeError("evaluated_text must be a string")
        reasons = _text_tuple(self.reasons, "reasons")
        invariants = _text_tuple(self.violated_invariants, "violated_invariants")
        if not isinstance(self.accepted_sentences, (tuple, list)):
            raise TypeError("accepted_sentences must be a sequence")
        sentences = tuple(self.accepted_sentences)
        if any(not isinstance(item, AcceptedSentence) for item in sentences):
            raise TypeError("accepted_sentences must contain AcceptedSentence values")
        indexes = [item.index for item in sentences]
        if indexes != sorted(set(indexes)):
            raise ValueError("accepted sentence indexes must be unique and ordered")
        if any(item.text not in self.evaluated_text for item in sentences):
            raise ValueError("accepted sentence text must occur in evaluated_text")
        if self.status in {
            AcceptanceStatus.REJECTED,
            AcceptanceStatus.REPLACEMENT_REQUIRED,
        } and sentences:
            raise ValueError("rejected or replacement decisions cannot accept sentences")
        if self.status is AcceptanceStatus.SALVAGEABLE and not sentences:
            raise ValueError("salvageable decisions require an accepted sentence subset")
        if self.status is AcceptanceStatus.ACCEPTED and invariants:
            raise ValueError("accepted decisions cannot contain violated invariants")
        if self.status is not AcceptanceStatus.ACCEPTED and not (reasons or invariants):
            raise ValueError("non-accepted decisions require a reason or violated invariant")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "violated_invariants", invariants)
        object.__setattr__(self, "accepted_sentences", sentences)
        object.__setattr__(self, "metadata", freeze_metadata(self.metadata))


class AcceptanceEvaluator(Protocol):
    """Interface for a later Core-owned acceptance implementation."""

    def evaluate(self, candidate: AnswerCandidate) -> AcceptanceDecision:
        ...
