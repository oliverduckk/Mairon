import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.turn_state import TurnState


PRONOUN_PATTERN = re.compile(
    r"\b(it|that|this|they|them|those|these)\b",
    flags=re.IGNORECASE,
)


@dataclass
class ConversationState:
    """
    Short-lived active conversational state.

    This is not long-term memory. It exists so a follow-up like
    "check my emails to see if it has" can resolve "it" to the current
    Hype DC order without making Oliver repeat himself.
    """

    active_subject: Optional[str] = None
    active_intent: Optional[str] = None
    active_entities: Dict[str, str] = field(default_factory=dict)
    pending_question: Optional[str] = None
    pending_action: Optional[str] = None
    recent_subjects: List[str] = field(default_factory=list)

    def remember_subject(self, subject: Optional[str]) -> None:
        value = str(subject or "").strip()
        if not value:
            return

        self.active_subject = value
        self.recent_subjects = [
            item for item in self.recent_subjects if item != value
        ]
        self.recent_subjects.insert(0, value)
        self.recent_subjects = self.recent_subjects[:8]

    def update_from_turn(self, turn: TurnState) -> None:
        if turn.subject:
            self.remember_subject(turn.subject)

        if turn.intent:
            self.active_intent = turn.intent

        if turn.entities:
            for key, value in turn.entities.items():
                if value is None:
                    continue
                self.active_entities[str(key)] = str(value)

        if turn.requested_action:
            self.pending_action = turn.requested_action

        if turn.speech_act == "question":
            self.pending_question = turn.raw_text

    def resolve_follow_up(self, turn: TurnState) -> TurnState:
        text = turn.raw_text

        pronouns = [
            match.group(1).lower()
            for match in PRONOUN_PATTERN.finditer(text)
        ]

        if not pronouns:
            return turn

        if not self.active_subject:
            turn.unresolved_referents.extend(pronouns)
            turn.add_reason(
                "follow-up pronoun present but no active subject exists"
            )
            return turn

        for pronoun in pronouns:
            turn.resolved_referents[pronoun] = self.active_subject

        turn.is_follow_up = True

        if not turn.subject:
            turn.subject = self.active_subject

        if (
            turn.intent == "email_search"
            and self.active_intent == "order_status"
        ):
            turn.intent = "order_status"
            turn.requested_action = "check_order_status"
            turn.preferred_authority = "gmail"
            turn.requires_private_data = True
            turn.requires_live_data = True
            turn.should_use_tools = True
            turn.should_answer_directly = False
            turn.factuality = "tool_verified"

            if "merchant" in self.active_entities:
                turn.entities["merchant"] = self.active_entities["merchant"]

            turn.add_reason(
                "inherited active order-status workflow from conversation state"
            )

        return turn



def append_visible_turn_to_model_history(
    current_state,
    user_input,
    assistant_text,
    system_instructions=None,
):
    """
    Add a Core-owned visible exchange to the local provider's conversation
    history without calling the language model.

    This keeps one continuous live conversation even when Core answered a
    turn deterministically.

    Example:
        Oliver -> Core/Gmail -> "ready to collect"
        Oliver -> Qwen follow-up

    Qwen should see the first exchange rather than starting from a blank
    conversational history.
    """

    if current_state is None:
        state = []

        if system_instructions:
            state.append({
                "role": "system",
                "content": str(
                    system_instructions
                ),
            })

    else:
        state = list(
            current_state
        )

    state.append({
        "role": "user",
        "content": str(
            user_input
        ),
    })

    state.append({
        "role": "assistant",
        "content": str(
            assistant_text
        ),
    })

    return state
