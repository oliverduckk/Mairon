"""S4 provider-state compatibility: ephemeral handles and bounded local views.

A cloud Responses ID is NOT a conversation transcript. A local history is NOT
an OpenAI response ID. Handles are process-local, model/session-bound, expire,
and have no authority to export saved/local private context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Any

_ISSUER = object()
_RESPONSE_ID = re.compile(r"[A-Za-z0-9_-]{1,160}\Z")
_MAX_HANDLE_AGE = 600.0
_MAX_CLOUD_TURNS = 4
_MAX_LOCAL_MESSAGES = 48
_MAX_LOCAL_CHARS = 56000


@dataclass(frozen=True)
class CloudContinuation:
    response_id: str
    owner_id: str
    model_id: str
    created_at: float
    depth: int
    _issuer: object = field(default=None, repr=False, compare=False)
    _backend_client: object = field(default=None, repr=False, compare=False)


def eligible_cloud_continuation(
    state: Any, *, owner_id: str | None, model_id: str,
    backend_client: Any = None,
) -> CloudContinuation | None:
    """Unknown, restored, fabricated, foreign and stale state is ineligible."""
    if not isinstance(state, CloudContinuation) or state._issuer is not _ISSUER:
        return None
    if not isinstance(owner_id, str) or not owner_id or owner_id != state.owner_id:
        return None
    if state.model_id != model_id or not _RESPONSE_ID.fullmatch(state.response_id):
        return None
    if backend_client is not None and state._backend_client is not backend_client:
        return None
    if not (1 <= state.depth < _MAX_CLOUD_TURNS):
        return None
    age = time.monotonic() - state.created_at
    if not (0 <= age <= _MAX_HANDLE_AGE):
        return None
    return state


def make_cloud_continuation(
    response_id: Any, *, owner_id: str | None,
    model_id: str, predecessor: CloudContinuation | None = None,
    backend_client: Any = None,
) -> CloudContinuation | None:
    """Issue only from a successful current cloud adapter result.

    Without a verified session owner, retain no continuation state.  This
    protects legacy callers, which can still use cloud for one isolated turn.
    """
    if not isinstance(owner_id, str) or not owner_id:
        return None
    if not isinstance(response_id, str) or not _RESPONSE_ID.fullmatch(response_id):
        return None
    if not isinstance(model_id, str) or not model_id or len(model_id) > 100:
        return None
    prior = eligible_cloud_continuation(
        predecessor, owner_id=owner_id, model_id=model_id,
        backend_client=backend_client,
    )
    return CloudContinuation(
        response_id=response_id, owner_id=owner_id,
        model_id=model_id, created_at=time.monotonic(),
        depth=(prior.depth + 1 if prior else 1), _issuer=_ISSUER,
        _backend_client=backend_client,
    )


def bounded_local_history(history: Any) -> list | None:
    """Budget a local-only live context without fabricating missing turns.

    Preserve actual Ollama message objects and any tool metadata for the
    retained suffix.  Keep the first system instruction when present, and
    drop older whole messages, never fragments of evidence or response text.
    A non-list provider state is not a valid local history.
    """
    if not isinstance(history, (tuple, list)):
        return None
    items = [
        message for message in history
        if (message.get("role") if isinstance(message, dict)
            else getattr(message, "role", None))
        in {"system", "user", "assistant", "tool"}
    ]
    system = None
    if items:
        first = items[0]
        role = first.get("role") if isinstance(first, dict) else getattr(first, "role", None)
        if role == "system":
            system = first
            items = items[1:]
    # A later system item is never an authorised instruction. The single
    # existing system entry, when supplied, must occupy the first position.
    items = [
        m for m in items
        if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) != "system"
    ]

    def size(value: Any) -> int:
        # Count metadata/tool-call arguments too, not just visible `content`.
        # Keep complete messages rather than manufacturing partial evidence.
        return len(repr(value))
    allowed = []
    remaining = _MAX_LOCAL_CHARS - (size(system) if system is not None else 0)
    # Do not cut content. A single oversized message must not break the budget.
    for message in reversed(items):
        length = size(message)
        if length > remaining or len(allowed) >= _MAX_LOCAL_MESSAGES - (1 if system else 0):
            break
        allowed.append(message)
        remaining -= length
    allowed.reverse()
    if system is not None and size(system) <= _MAX_LOCAL_CHARS:
        allowed.insert(0, system)
    return allowed or None


def adapt_local_provider_reply(value: Any) -> tuple[str | None, list | None, str | None, dict | None]:
    """Validate the incumbent four-field local adapter return shape."""
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("Local provider returned an unsupported result shape.")
    answer, history, escalation, action = value
    if answer is not None and not isinstance(answer, str):
        raise ValueError("Local provider returned an unsupported answer.")
    if history is not None and not isinstance(history, (tuple, list)):
        raise ValueError("Local provider returned an incompatible history.")
    if escalation is not None and not isinstance(escalation, str):
        raise ValueError("Local provider returned an unsupported escalation.")
    if action is not None and not isinstance(action, dict):
        raise ValueError("Local provider returned an unsupported pending action.")
    return answer, bounded_local_history(history), escalation, action


def adapt_cloud_provider_reply(value: Any) -> tuple[str, str | None]:
    """Validate the incumbent three-field cloud adapter result explicitly.

    A cloud result's third field is not a calendar action, escalation or local
    history. Any new provider feature needs a declared adapter, not inference.
    """
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError("Cloud provider returned an unsupported result shape.")
    answer, response_id, unsupported = value
    if not isinstance(answer, str) or unsupported is not None:
        raise ValueError("Cloud provider returned an unsupported result.")
    if response_id is not None and (
        not isinstance(response_id, str) or not _RESPONSE_ID.fullmatch(response_id)
    ):
        raise ValueError("Cloud provider returned an invalid continuation handle.")
    return answer, response_id


_CONTEXT_ONLY_PROMPTS = frozenset({
    "continue", "go on", "keep going", "tell me more", "elaborate",
    "can you elaborate", "could you elaborate", "expand on that",
    "what about that", "what about it", "why is that", "how so",
    "what did i just say", "what did you just say", "explain that",
})


def requires_prior_cloud_context(prompt: Any) -> bool:
    """Only reject clearly context-only cloud follow-ups; avoid broad guessing."""
    if not isinstance(prompt, str):
        return False
    return prompt.strip().lower().rstrip("?! .") in _CONTEXT_ONLY_PROMPTS
