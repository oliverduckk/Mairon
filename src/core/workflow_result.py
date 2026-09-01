from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.evidence import EvidenceBundle


@dataclass
class WorkflowResult:
    """
    Structured output from a deterministic Core workflow.
    """

    success: bool
    status: str
    answer_fact: Optional[str] = None
    evidence: Optional[EvidenceBundle] = None

    data: Dict[str, Any] = field(
        default_factory=dict
    )

    error: Optional[str] = None
