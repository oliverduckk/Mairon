from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TurnState:
    """
    Structured representation of what Oliver is doing in the current turn.
    """

    raw_text: str
    speech_act: str = "unknown"
    intent: str = "unknown"
    subject: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)
    requested_action: Optional[str] = None

    is_follow_up: bool = False
    resolved_referents: Dict[str, str] = field(default_factory=dict)
    unresolved_referents: List[str] = field(default_factory=list)

    requires_private_data: bool = False
    requires_live_data: bool = False
    factuality: str = "unknown"
    preferred_authority: Optional[str] = None

    should_use_tools: bool = False
    should_answer_directly: bool = True
    should_recommend: bool = False
    should_continue_conversation: bool = False

    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def add_reason(self, reason: str) -> None:
        value = str(reason or "").strip()
        if value and value not in self.reasons:
            self.reasons.append(value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "speech_act": self.speech_act,
            "intent": self.intent,
            "subject": self.subject,
            "entities": dict(self.entities),
            "requested_action": self.requested_action,
            "is_follow_up": self.is_follow_up,
            "resolved_referents": dict(self.resolved_referents),
            "unresolved_referents": list(self.unresolved_referents),
            "requires_private_data": self.requires_private_data,
            "requires_live_data": self.requires_live_data,
            "factuality": self.factuality,
            "preferred_authority": self.preferred_authority,
            "should_use_tools": self.should_use_tools,
            "should_answer_directly": self.should_answer_directly,
            "should_recommend": self.should_recommend,
            "should_continue_conversation": self.should_continue_conversation,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }
