"""Trusted, idempotent calendar resolution projection; no effect authority."""
from dataclasses import dataclass, field
from uuid import uuid4
from core.provider_state import bounded_local_history
from core.conversation_state import append_visible_turn_to_model_history


@dataclass(eq=False)
class ActionProjection:
    base: object
    request: str
    operation_id: str = field(default_factory=lambda: 'calendar-resolution-'+uuid4().hex)
    answer: str | None = None
    state: object = None

    def project(self, user_text, answer, instructions=None):
        # The snapshot was captured before provider proposal construction. This
        # excludes unshown provider text and any already-appended proposal.
        if self.answer != answer or self.state is None:
            self.state = append_visible_turn_to_model_history(
                bounded_local_history(self.base), self.request or user_text, answer, instructions)
            self.answer = answer
        return bounded_local_history(self.state)


def project_action_history(result, user_text, answer, instructions=None):
    projection = getattr(result, 'history_projection', None)
    if isinstance(projection, ActionProjection):
        return projection.project(user_text, answer, instructions)
    return bounded_local_history(getattr(result, 'local_state', None))
