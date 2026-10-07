"""Core evidence and immutable canonical snapshots.

Admissible evidence supports reasoning within its authority scope. A user
assertion or retrieved source is not promoted to independently verified truth.
Legacy gatherers remain mutable; candidate transport uses normalized snapshots.
"""
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Tuple


class EvidenceKind(str, Enum):
    UNKNOWN = "unknown"
    CURRENT_USER_TURN = "current_user_turn"
    LIVE_USER_FACT = "live_user_fact"
    USER_CORRECTION = "user_correction"
    SUPPLIED_PREMISE = "supplied_premise"
    PUBLIC_SOURCE = "public_source"
    MEDIA_SOURCE = "media_source"
    CORE_RESULT = "core_result"
    STABLE_MODEL_KNOWLEDGE_PERMISSION = "stable_model_knowledge_permission"
    UNCERTAINTY = "uncertainty"


class EvidenceStatus(str, Enum):
    UNASSESSED = "unassessed"
    ADMISSIBLE = "admissible"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


def freeze_metadata(value: Any) -> Any:
    """Snapshot JSON-like data without retaining mutable ingress references."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Evidence metadata keys must be strings")
        return MappingProxyType({key: freeze_metadata(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_metadata(item) for item in value)
    raise TypeError(f"Unsupported mutable evidence metadata: {type(value).__name__}")


def thaw_metadata(value: Any) -> Any:
    """Return independently mutable JSON-compatible serialization data."""
    if isinstance(value, Mapping):
        return {key: thaw_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_metadata(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


class _ReadOnlySnapshot:
    def __setattr__(self, name, value):
        if self.__dict__.get("_sealed", False):
            raise FrozenInstanceError("Canonical evidence snapshots are read-only")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if self.__dict__.get("_sealed", False):
            raise FrozenInstanceError("Canonical evidence snapshots are read-only")
        object.__delattr__(self, name)

    def _seal(self):
        object.__setattr__(self, "_sealed", True)
        return self


@dataclass
class Evidence(_ReadOnlySnapshot):
    claim: str
    provenance: str
    confidence: str
    source_name: Optional[str] = None
    source_id: Optional[str] = None
    observed_at: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    # Appended fields preserve existing positional constructors and builders.
    kind: EvidenceKind = EvidenceKind.UNKNOWN
    status: EvidenceStatus = EvidenceStatus.UNASSESSED
    source_url: Optional[str] = None
    source_quality: Optional[str] = None
    authority_tier: Optional[str] = None
    quality_eligible: Optional[bool] = None
    evidence_id: Optional[str] = None
    supersedes: Tuple[str, ...] = field(default_factory=tuple)
    limitations: Tuple[str, ...] = field(default_factory=tuple)
    authority_scope: str = ""

    @property
    def is_authoritative_fact(self) -> bool:
        return (
            self.status == EvidenceStatus.ADMISSIBLE
            and self.kind not in {
                EvidenceKind.UNKNOWN, EvidenceKind.UNCERTAINTY,
                EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION,
            }
            and bool(self.claim.strip())
        )

    def snapshot(self) -> "Evidence":
        for name in ("claim", "provenance", "confidence", "authority_scope"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")
        for name in ("source_name", "source_id", "observed_at", "source_url",
                     "source_quality", "authority_tier", "evidence_id"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")
        if not isinstance(self.kind, EvidenceKind) or not isinstance(self.status, EvidenceStatus):
            raise TypeError("Canonical evidence kind and status must be typed enums")
        if self.quality_eligible is not None and type(self.quality_eligible) is not bool:
            raise TypeError("quality_eligible must be a bool or None")
        if not isinstance(self.data, Mapping):
            raise TypeError("Evidence data must be a mapping")
        for name in ("supersedes", "limitations"):
            value = getattr(self, name)
            if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
                raise TypeError(f"{name} must be a sequence of strings")
        if self.kind == EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION and self.claim:
            raise ValueError("A model-knowledge permission cannot assert a verified claim")
        return replace(
            self, data=freeze_metadata(self.data),
            supersedes=tuple(self.supersedes), limitations=tuple(self.limitations),
        )._seal()

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "claim": self.claim, "provenance": self.provenance,
            "confidence": self.confidence, "source_name": self.source_name,
            "source_id": self.source_id, "observed_at": self.observed_at,
            "data": thaw_metadata(self.data),
        }
        # Preserve legacy serialization for unmigrated builders.
        if self.kind != EvidenceKind.UNKNOWN or self.status != EvidenceStatus.UNASSESSED:
            result.update({
                "kind": self.kind.value, "status": self.status.value,
                "source_url": self.source_url, "source_quality": self.source_quality,
                "authority_tier": self.authority_tier,
                "quality_eligible": self.quality_eligible,
                "evidence_id": self.evidence_id, "supersedes": list(self.supersedes),
                "limitations": list(self.limitations), "authority_scope": self.authority_scope,
            })
        return result


@dataclass
class EvidenceBundle(_ReadOnlySnapshot):
    authority: str
    evidence: List[Evidence] = field(default_factory=list)
    success: bool = False
    uncertainty: Optional[str] = None
    canonical: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add(self, item: Evidence) -> None:
        self.evidence.append(item)

    def snapshot(self) -> "EvidenceBundle":
        if not isinstance(self.authority, str):
            raise TypeError("Bundle authority must be a string")
        if type(self.success) is not bool or type(self.canonical) is not bool:
            raise TypeError("Bundle success and canonical flags must be booleans")
        if self.uncertainty is not None and not isinstance(self.uncertainty, str):
            raise TypeError("Bundle uncertainty must be a string or None")
        if not isinstance(self.evidence, (list, tuple)) or any(not isinstance(item, Evidence) for item in self.evidence):
            raise TypeError("Bundle evidence must contain Evidence objects")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("Bundle metadata must be a mapping")
        return replace(
            self, evidence=tuple(item.snapshot() for item in self.evidence),
            metadata=freeze_metadata(self.metadata),
        )._seal()

    @property
    def authoritative_evidence(self) -> Tuple[Evidence, ...]:
        if not self.canonical:
            raise ValueError("Normalize legacy evidence before consuming canonical authority")
        superseded = {
            identity for item in self.evidence
            if item.kind == EvidenceKind.USER_CORRECTION and item.is_authoritative_fact
            for identity in item.supersedes
        }
        user_domains = {
            EvidenceKind.CURRENT_USER_TURN, EvidenceKind.LIVE_USER_FACT,
            EvidenceKind.USER_CORRECTION, EvidenceKind.SUPPLIED_PREMISE,
        }
        return tuple(item for item in self.evidence if item.is_authoritative_fact
                     and not (item.kind in user_domains and item.evidence_id in superseded))

    @property
    def authoritative_claims(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(item.claim for item in self.authoritative_evidence))

    @property
    def model_knowledge_permitted(self) -> bool:
        if not self.canonical:
            raise ValueError("Normalize legacy evidence before consuming canonical authority")
        return any(item.kind == EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION
                   and item.status == EvidenceStatus.ADMISSIBLE for item in self.evidence)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "authority": self.authority, "success": self.success,
            "uncertainty": self.uncertainty,
            "evidence": [item.to_dict() for item in self.evidence],
        }
        if self.canonical or self.metadata:
            result.update({"canonical": self.canonical, "metadata": thaw_metadata(self.metadata)})
        return result
