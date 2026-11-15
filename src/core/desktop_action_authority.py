"""SEC-01: current Core turn -> one checked desktop workflow dispatch.

The legacy workflow/agent adapters remain trusted Python integration APIs.
Every production conversational desktop launch/control enters this bridge;
model prose and a restored target string are not dispatch capabilities.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic

from core.desktop_catalog import extract_desktop_action_request
from core.turn_state import TurnState
from core.workflow_result import WorkflowResult

_ISSUER = object()
_ACTIVE = ContextVar("mairon_desktop_action_authority", default=None)
_MAX_AGE = 30.0
_MAX_REFERENT_AGE = 600.0
_ACTION_INTENTS = {
    "open": "launch_application",
    "close": "close_application",
    "focus": "focus_application",
}


def _snapshot(turn):
    if not isinstance(turn, TurnState) or not isinstance(turn.entities, dict):
        return None
    return (
        turn.raw_text, turn.speech_act, turn.intent, turn.requested_action,
        turn.entities.get("desktop_action"), turn.entities.get("app_name"),
        turn.preferred_authority,
    )


@dataclass(frozen=True)
class _DesktopReferent:
    target: str
    created: float
    issuer: object = field(repr=False)


@dataclass(eq=False, frozen=True)
class DesktopActionAuthority:
    turn: TurnState
    state: object
    snapshot: tuple
    action: str
    target: str
    created: float
    issuer: object = field(repr=False)
    used: bool = False
    lock: object = field(default_factory=Lock, repr=False)


def _matches_current_request(turn, state, action, target):
    if not isinstance(turn, TurnState):
        return False
    expected = _ACTION_INTENTS.get(action)
    if (expected is None or turn.speech_act != "request_action"
            or turn.intent != expected or turn.requested_action != expected
            or turn.preferred_authority != "desktop"
            or not isinstance(turn.entities, dict)
            or turn.entities.get("app_name") != target
            or turn.entities.get("desktop_action") != action):
        return False
    request = extract_desktop_action_request(turn.raw_text, state)
    if not request or request["action"] != action or request["target_id"] != target:
        return False
    if request["inherited"]:
        referent = getattr(state, "_sec01_desktop_referent", None)
        if (not isinstance(referent, _DesktopReferent)
                or referent.issuer is not _ISSUER or referent.target != target
                or not 0 <= monotonic() - referent.created <= _MAX_REFERENT_AGE):
            return False
    return True


@contextmanager
def desktop_action_turn(turn, user_text, conversation_state):
    """Core's preparation scope; no effect occurs while issuing authority."""
    authority = None
    if isinstance(turn, TurnState) and turn.raw_text == str(user_text or "").strip():
        action = turn.entities.get("desktop_action") if isinstance(turn.entities, dict) else None
        target = turn.entities.get("app_name") if isinstance(turn.entities, dict) else None
        if _matches_current_request(turn, conversation_state, action, target):
            authority = DesktopActionAuthority(
                turn, conversation_state, _snapshot(turn), action, target,
                monotonic(), _ISSUER,
            )
    token = _ACTIVE.set(authority)
    try:
        yield authority
    finally:
        _ACTIVE.reset(token)


def dispatch_desktop_action(authority, *, turn, conversation_state, action,
                            target_id, launch, control):
    """Validate/consume immediately before a fixed trusted workflow call.

    `launch` and `control` are Core's existing Python adapters, not model-supplied
    functions. Consumption precedes dispatch, including uncertain failures.
    """
    allowed = False
    if isinstance(authority, DesktopActionAuthority):
        with authority.lock:
            allowed = (
                authority.issuer is _ISSUER and _ACTIVE.get() is authority
                and authority.turn is turn and authority.state is conversation_state
                and authority.snapshot == _snapshot(turn)
                and authority.action == action and authority.target == target_id
                and not authority.used
                and 0 <= monotonic() - authority.created <= _MAX_AGE
                and _matches_current_request(turn, conversation_state, action, target_id)
            )
            if allowed:
                object.__setattr__(authority, "used", True)
    if not allowed:
        return WorkflowResult(
            success=False, status="desktop_authority_unavailable",
            error="I couldn't authorise that desktop action for this turn.",
            data={"app_name": target_id, "action": action},
        )
    result = (launch(app_name=target_id) if action == "open"
              else control(app_name=target_id, action=action))
    if isinstance(result, WorkflowResult) and result.success:
        conversation_state._sec01_desktop_referent = _DesktopReferent(
            target_id, monotonic(), _ISSUER,
        )
    return result
