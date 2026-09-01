from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Evidence:
    """
    One piece of information Mairon Core is allowed to rely on.

    The important question is not only WHAT the claim is, but HOW Core
    knows it.
    """

    claim: str
    provenance: str
    confidence: str

    source_name: Optional[str] = None
    source_id: Optional[str] = None
    observed_at: Optional[str] = None

    data: Dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(
        self,
    ) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "source_name": self.source_name,
            "source_id": self.source_id,
            "observed_at": self.observed_at,
            "data": dict(
                self.data
            ),
        }


@dataclass
class EvidenceBundle:
    """
    All evidence gathered for one user turn.
    """

    authority: str
    evidence: List[Evidence] = field(
        default_factory=list
    )
    success: bool = False
    uncertainty: Optional[str] = None

    def add(
        self,
        item: Evidence,
    ) -> None:
        self.evidence.append(
            item
        )

    def to_dict(
        self,
    ) -> Dict[str, Any]:
        return {
            "authority": self.authority,
            "success": self.success,
            "uncertainty": self.uncertainty,
            "evidence": [
                item.to_dict()
                for item in self.evidence
            ],
        }
