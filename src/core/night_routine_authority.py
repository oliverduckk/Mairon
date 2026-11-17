"""SEC-01: current-turn authority for the existing night routine only.

Opaque Python capabilities stay outside model messages and persisted transcripts.
They are not a sandbox for hostile Python executing in the application process.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date as Date
from functools import wraps
from inspect import signature
import json
import re
import time
from threading import RLock


_ISSUER = object()
_TURN = ContextVar("mairon_night_provider_turn", default=None)
_EXECUTION = ContextVar("mairon_night_execution", default=None)
_MAX_AGE = 600.0


def _normal(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text.casefold().replace("’", "'")).strip()


def is_affirmative_night_request(text):
    """Accept the whole current utterance, never embedded quoted commands."""
    if not isinstance(text, str) or any(c in text for c in ('"', '“', '”', '`', '\n', '\r')):
        return False
    value = _normal(text)
    if not value or any(c in value for c in ('"', '“', '”', '`', '\n')):
        return False
    value = re.sub(r"[.!]+$", "", value).strip()
    value = re.sub(r"^(?:mairon[, ]+|please[, ]+)", "", value)
    value = re.sub(r"(?:,?\s+(?:please|now))$", "", value)
    return bool(re.fullmatch(
        r"(?:(?:i(?:'m|m| am) (?:going|heading|off) to (?:bed|sleep)|"
        r"heading to bed|off to bed|going to sleep|heading to sleep|"
        r"time for bed|bedtime)(?:,? mairon)?|goodnight mairon|good night mairon|"
        r"night mairon)", value))


def affirmative_work_location(text):
    """A location answer is usable only after an opaque pending capability."""
    if not isinstance(text, str) or any(c in text for c in ('"', '“', '”', '`', '\n', '\r')):
        return None
    value = _normal(text)
    value = re.sub(r"[.!]+$", "", value).strip()
    value = re.sub(r"^(?:i(?:'m|m| am)|i(?:'ll| will) be)\s+", "", value)
    value = re.sub(r"(?:,?\s+(?:tomorrow|please))$", "", value)
    if value in {"office", "the office", "in the office", "going to the office",
                 "going into the office", "work", "going to work"}:
        return "office"
    if value in {"home", "wfh", "work from home", "working from home", "at home"}:
        return "home"
    return None


@dataclass(eq=False)
class _Turn:
    authority: object
    owner: str | None
    created: float = field(default_factory=time.monotonic)
    issued: bool = False
    grant: object = field(default=None, repr=False)
    _lock: object = field(default_factory=RLock, repr=False)
    _snapshot: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self._snapshot = _turn_snapshot(self)


def _turn_snapshot(state):
    authority = state.authority
    turn = getattr(authority, "turn", None)
    return (id(authority), id(getattr(authority, "runtime", None)), id(turn), state.owner, state.created,
            getattr(turn, "raw_text", None), getattr(turn, "intent", None),
            getattr(turn, "speech_act", None), getattr(turn, "requested_action", None))


@contextmanager
def night_provider_turn(authority, owner=None):
    """Entered by provider_turn, not by model output or conversation text."""
    token = _TURN.set(_Turn(authority, owner if isinstance(owner, str) and owner else None))
    try:
        yield
    finally:
        _TURN.reset(token)


@dataclass(eq=False)
class NightAuthority:
    _turn: _Turn
    target_date: str
    mode: str
    location: str | None = None
    _issuer: object = field(default=None, repr=False)
    _created: float = field(default_factory=time.monotonic, repr=False)
    _used: bool = False
    _nested: bool = False
    _pending_issued: bool = False
    _effects: dict = field(default_factory=dict, repr=False)
    _lock: object = field(default_factory=RLock, repr=False)
    _snapshot: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self._snapshot = (id(self._turn), self.target_date, self.mode, self.location, self._created)


@dataclass(eq=False)
class _PendingNight:
    target_date: str
    owner: str
    created: float
    _issuer: object = field(default=None, repr=False)
    used: bool = False
    _lock: object = field(default_factory=RLock, repr=False)
    _snapshot: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self._snapshot = (id(self), self.target_date, self.owner, self.created)


class NightClarificationMessage(dict):
    """Ordinary role/content mapping; capability is never a serialized key."""
    pass


def _current():
    from tools.tool_admission import current_turn_authority
    state = _TURN.get()
    if state is None or state.authority is not current_turn_authority():
        return None
    if _turn_snapshot(state) != state._snapshot:
        return None
    if not 0 <= time.monotonic() - state.created <= _MAX_AGE:
        return None
    try:
        state.authority.require_local()
    except Exception:
        return None
    return state


def _pending_valid(pending, state):
    return (isinstance(pending, _PendingNight) and pending._issuer is _ISSUER
            and not pending.used and pending.owner == state.owner
            and pending._snapshot == (id(pending), pending.target_date, pending.owner, pending.created)
            and 0 <= time.monotonic() - pending.created <= _MAX_AGE)


def _date(value):
    try:
        return isinstance(value, str) and Date.fromisoformat(value).isoformat() == value
    except (ValueError, TypeError):
        return False


def _matches_input(state, text):
    turn = getattr(state.authority, "turn", None)
    return isinstance(text, str) and getattr(turn, "raw_text", None) == text.strip()


def issue_night_authority(text, target_date):
    state = _current()
    if state is None or state.issued or not _date(target_date):
        return None
    turn = state.authority.turn
    if (not _matches_input(state, text) or not is_affirmative_night_request(text)
            or state.authority.runtime.intent != "night_routine_request"
            or getattr(turn, "intent", None) != "night_routine_request"
            or getattr(turn, "requested_action", None) != "night_routine"
            or getattr(turn, "speech_act", None) != "request_action"):
        return None
    with state._lock:
        if state.issued:
            return None
        state.issued = True
        state.grant = NightAuthority(state, target_date, "prepare", _issuer=_ISSUER)
        return state.grant


def _valid(grant):
    return (isinstance(grant, NightAuthority) and grant._issuer is _ISSUER
            and _current() is grant._turn and _date(grant.target_date)
            and grant._turn.grant is grant
            and grant._snapshot == (id(grant._turn), grant.target_date, grant.mode, grant.location, grant._created)
            and 0 <= time.monotonic() - grant._created <= _MAX_AGE)


def denied_night_result():
    return {"success": False, "status": "not_authorised",
            "message": "The night routine requires a current, authorised request."}


def night_workflow(function):
    """Consume one workflow entry; completion may enter preparation once."""
    params = signature(function)
    mode = "complete" if function.__name__ == "complete_night_routine_work_location" else "prepare"
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            bound = params.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError:
            return denied_night_result()
        grant = bound.arguments.get("authority")
        target = bound.arguments.get("date") or getattr(grant, "target_date", None)
        if (not _valid(grant) or target != grant.target_date
                or type(bound.arguments.get("record_bedtime")) is not bool):
            return denied_night_result()
        current = _EXECUTION.get()
        with grant._lock:
            if current is grant:
                if grant.mode != "complete" or mode != "prepare" or grant._nested:
                    return denied_night_result()
                grant._nested = True
                return function(*args, **kwargs)
            if (current is not None or grant._used or grant.mode != mode
                    or (mode == "complete" and bound.arguments.get("location") != grant.location)):
                return denied_night_result()
            grant._used = True
        token = _EXECUTION.set(grant)
        try:
            return function(*args, **kwargs)
        finally:
            _EXECUTION.reset(token)
    return checked


def _fingerprint(payload):
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError):
        return None


@dataclass(eq=False, frozen=True)
class _NightEffect:
    grant: NightAuthority
    operation: str
    payload: str
    _issuer: object
    used: bool = False


def admit_night_effect(grant, operation, payload):
    """Bind the exact trusted, post-derivation payload before final dispatch."""
    if not _valid(grant) or _EXECUTION.get() is not grant or operation in grant._effects:
        return None
    if not isinstance(payload, dict):
        return None
    if operation == "alarm":
        valid = (set(payload) == {"date", "time", "label", "source", "metadata"}
                 and payload.get("date") == grant.target_date and payload.get("source") == "routine"
                 and all(isinstance(payload.get(k), str) for k in ("time", "label"))
                 and isinstance(payload.get("metadata"), dict))
    elif operation == "location":
        valid = (grant.mode == "complete" and set(payload) == {"date_string", "location"}
                 and payload.get("date_string") == grant.target_date
                 and payload.get("location") == grant.location)
    elif operation == "bedtime":
        valid = (set(payload) == {"event_type", "details", "retention_hours"}
                 and payload.get("event_type") == "bedtime" and payload.get("retention_hours") == 36
                 and isinstance(payload.get("details"), dict)
                 and payload["details"].get("next_date") == grant.target_date)
    else:
        valid = False
    fingerprint = _fingerprint(payload)
    if not valid or fingerprint is None:
        return None
    with grant._lock:
        if operation in grant._effects:
            return None
        effect = _NightEffect(grant, operation, fingerprint, _ISSUER)
        grant._effects[operation] = effect
        return effect


def execute_night_effect(effect, adapter, **payload):
    """Final routine bridge: deny stale, altered, replayed or foreign effects."""
    if not isinstance(effect, _NightEffect) or not _valid(effect.grant):
        return denied_night_result()
    with effect.grant._lock:
        if (effect._issuer is not _ISSUER or effect.used or not _valid(effect.grant)
                or _EXECUTION.get() is not effect.grant
                or effect.grant._effects.get(effect.operation) is not effect
                or _fingerprint(payload) != effect.payload):
            return denied_night_result()
        object.__setattr__(effect, "used", True)  # An uncertain outcome never retries the same effect.
    return adapter(**json.loads(effect.payload))


def perform_night_effect(grant, operation, adapter, **payload):
    return execute_night_effect(admit_night_effect(grant, operation, payload), adapter, **payload)


def attach_night_pending(message, grant):
    if (not _valid(grant) or not grant._used or grant._effects or grant._pending_issued
            or not grant._turn.owner):
        return dict(message)
    with grant._lock:
        if grant._pending_issued:
            return dict(message)
        grant._pending_issued = True
        result = NightClarificationMessage(message)
        result._night_pending = _PendingNight(grant.target_date, grant._turn.owner, grant._created, _ISSUER)
        from core.workflow_continuity import publish_night
        publish_night(result._night_pending)
        return result


def pending_night_authority(conversation):
    state = _current()
    if state is None or not state.owner or not isinstance(conversation, (list, tuple)):
        return None
    intervening_message = False
    for message in reversed(conversation):
        if isinstance(message, NightClarificationMessage):
            pending = getattr(message, "_night_pending", None)
            if _pending_valid(pending, state):
                # Only the next affirmative location reply may complete this
                # prompt. A cancellation, new request or unrelated turn cannot
                # leave old write authority waiting in conversation history.
                if (intervening_message or not affirmative_work_location(
                        getattr(state.authority.turn, "raw_text", None))):
                    with pending._lock:
                        pending.used = True
                    return None
                return pending
            return None
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
        if role in {"user", "assistant", "tool"}:
            # Core/cloud may have answered without entering this provider.
            # Their visible exchange also ends the pending write invitation.
            intervening_message = True
    return None


def issue_night_completion(text, pending, tomorrow):
    state = _current()
    location = affirmative_work_location(text)
    if (state is None or state.issued or not _matches_input(state, text) or not location
            or not _pending_valid(pending, state) or pending.target_date != tomorrow
            or getattr(state.authority.turn, "requested_action", None) is not None):
        return None
    with pending._lock, state._lock:
        if pending.used or state.issued:
            return None
        pending.used = True
        state.issued = True
        state.grant = NightAuthority(state, pending.target_date, "complete", location, _ISSUER)
        return state.grant
