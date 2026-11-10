"""S2: transient, exact-payload, single-use approval authority.

A pending proposal is not permission. A ticket is issued by trusted router
code only, tied to a validated Core calendar intent and to the complete action.
Process restarts discard tickets rather than replaying old approvals.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
import json
from threading import Lock
from time import monotonic
from typing import Any

from core.authority_handoff import PreparedAuthority

_ISSUER = object()
_CALENDAR_EFFECT = ContextVar("mairon_calendar_effect", default=None)
_ALLOWED_FIELDS = frozenset({
    "type", "summary", "start_time", "end_time", "location", "description"
})


def _fingerprint(action):
    if not isinstance(action, dict) or set(action) - _ALLOWED_FIELDS:
        return None
    if action.get("type") != "create_calendar_event":
        return None
    if any(not isinstance(action.get(k), str) or not action[k].strip()
           for k in ("summary", "start_time", "end_time")):
        return None
    if any(k in action and action[k] is not None and not isinstance(action[k], str)
           for k in ("location", "description")):
        return None
    try:
        if datetime.fromisoformat(action["end_time"]) <= datetime.fromisoformat(action["start_time"]):
            return None
    except (ValueError, TypeError):
        return None
    return json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(eq=False)
class ApprovalTicket:
    _snapshot: str
    _issued_at: float
    _issuer: object = field(repr=False)
    _expires_after: float = 600.0
    _used: bool = False
    _revoked: bool = False
    _lock: Any = field(default_factory=Lock, repr=False)

    def revoke(self):
        with self._lock:
            self._revoked = True

    def consume(self, action):
        with self._lock:
            if (self._issuer is not _ISSUER or self._used or self._revoked
                    or monotonic() - self._issued_at > self._expires_after
                    or _fingerprint(action) != self._snapshot):
                return False
            self._used = True  # before the external effect (unknown outcomes do not retry)
            return True


def issue_calendar_ticket(action, authority):
    if not isinstance(authority, PreparedAuthority):
        return None
    try:
        authority.require_local()
    except Exception:
        return None
    if authority.runtime.intent != "calendar_event_creation_request":
        return None
    snapshot = _fingerprint(action)
    if snapshot is None:
        return None
    return ApprovalTicket(snapshot, monotonic(), _ISSUER)


@contextmanager
def authorised_calendar_effect(ticket, action):
    if not isinstance(ticket, ApprovalTicket) or not ticket.consume(action):
        yield False
        return
    # Only one low-level insertion per consumed approval, even if a helper
    # accidentally attempts multiple calls in the same action context.
    effect = {"action": ticket._snapshot, "unused": True}
    token = _CALENDAR_EFFECT.set(effect)
    try:
        yield True
    finally:
        _CALENDAR_EFFECT.reset(token)


def consume_calendar_effect(summary, start_time, end_time, location, description):
    effect = _CALENDAR_EFFECT.get()
    if not isinstance(effect, dict) or not effect.get("unused"):
        return False
    # The final adapter may receive the same fields as an approved action, and
    # must reject changed data even after the outer ticket was consumed.
    payload = {
        "type": "create_calendar_event", "summary": summary,
        "start_time": start_time, "end_time": end_time,
    }
    original = json.loads(effect["action"])
    for optional in ("location", "description"):
        candidate = location if optional == "location" else description
        if optional in original:
            payload[optional] = candidate
        elif candidate not in (None, ""):
            return False
    if _fingerprint(payload) != effect["action"]:
        return False
    effect["unused"] = False
    return True
