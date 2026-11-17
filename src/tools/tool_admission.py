"""S2: turn-scoped, fail-closed admission for tool adapters.

Only trusted Python integration code creates scopes; model messages supply neither
scope nor caller identity. This is not an authentication mechanism for hostile
Python code inside Mairon's process. Domain adapters retain their own guards.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import FrozenSet

_ACTIVE_SCOPE = ContextVar("mairon_active_tool_scope", default=None)
_ACTIVE_TURN = ContextVar("mairon_prepared_authority", default=None)
_ISSUER = object()


@dataclass(frozen=True)
class ToolScope:
    caller: str
    names: FrozenSet[str]
    _issuer: object

    def permits(self, name):
        return self._issuer is _ISSUER and name in self.names


def _issue(caller, names):
    return ToolScope(caller=caller, names=frozenset(names), _issuer=_ISSUER)


@contextmanager
def admitted_tools(scope):
    if not isinstance(scope, ToolScope) or scope._issuer is not _ISSUER:
        raise ValueError("Trusted tool execution scope is missing.")
    token = _ACTIVE_SCOPE.set(scope)
    try:
        yield
    finally:
        _ACTIVE_SCOPE.reset(token)


def current_tool_scope():
    return _ACTIVE_SCOPE.get()


# Model-requested writes must be grounded in the Core turn's requested action.
# Unknown intents cannot widen permissions; exact user consent still belongs to
# domain-specific action guards (e.g., calendar proposals).
_PUBLIC_READS = frozenset({"get_weather", "web_search", "web_read", "get_route"})
_LOCAL_PRIVATE_READS = frozenset({
    "get_system_info", "get_calendar_events", "get_next_calendar_event",
    "get_recent_emails", "find_emails", "read_email",
    "get_routine_context", "get_wake_alarm", "get_upcoming_alarms",
    "search_memory", "list_memories",
})
_WRITES = frozenset({
    "launch_application", "set_work_location", "set_wake_alarm",
    "disable_wake_alarm", "save_memory", "delete_memory",
})
_NO_TOOL_INTENTS = frozenset({
    "calendar_event_creation_request", "launch_application", "order_status",
    "email_search", "self_correction", "conversation_recall", "acknowledge",
    "casual_conversation", "share_context", "share_opinion",
})


def provider_tool_scope(provider, core_authority, advertised_names):
    """Intersect actual advertised tools, provider boundary and Core task.

    The caller must pass S1's trusted PreparedAuthority, never a parsed prompt.
    """
    from core.authority_handoff import PreparedAuthority
    if not isinstance(core_authority, PreparedAuthority):
        return _issue("untrusted_provider", ())
    try:
        if provider == "cloud":
            core_authority.require_cloud()
        elif provider == "local":
            core_authority.require_local()
        else:
            return _issue("untrusted_provider", ())
    except Exception:
        return _issue("untrusted_provider", ())

    intent = core_authority.runtime.intent
    turn = getattr(core_authority, "turn", None)
    action = str(getattr(turn, "requested_action", "") or "").strip()
    if intent in _NO_TOOL_INTENTS:
        allowed = frozenset()
    elif provider == "cloud":
        allowed = _PUBLIC_READS - {"get_route"}
    else:
        allowed = _PUBLIC_READS
        if core_authority.private_data_required or bool(
            getattr(turn, "requires_private_data", False)
        ):
            allowed = allowed | _LOCAL_PRIVATE_READS
        # Core must have resolved an action before a model may ask for a write.
        from core.local_write_authority import WRITE_TOOLS, authorised_local_write
        if action in _WRITES and (action not in WRITE_TOOLS or authorised_local_write(core_authority) is not None):
            allowed = allowed | {action}
    from tools.tool_registry import LOCAL_TOOLS, CLOUD_TOOLS
    provider_names = {
        tool["name"] for tool in (CLOUD_TOOLS if provider == "cloud" else LOCAL_TOOLS)
    }
    return _issue(provider, set(advertised_names) & provider_names & allowed)


_INTERNAL_CALLERS = {
    "core.email_read": {"read_email"},
    "core.email_search": {"find_emails"},
    "core.order_status": {"find_emails", "read_email"},
    "research.media": {"web_search", "web_read"},
    "research.public": {"web_search", "web_read"},
    "local.specialised": {
        "find_emails", "get_recent_emails", "get_weather", "get_route",
        "get_calendar_events", "get_routine_context", "get_wake_alarm",
        "read_email", "web_read",
    },
}


def internal_scope(caller):
    if caller not in _INTERNAL_CALLERS:
        return _issue("unknown_internal_caller", ())
    return _issue(caller, _INTERNAL_CALLERS[caller])


def run_internal_tool(caller, tool_name, arguments=None):
    """Explicit allowlisted bridge for Core/research routines, never model calls."""
    from tools.tool_registry import execute_tool
    with admitted_tools(internal_scope(caller)):
        return execute_tool(tool_name, arguments)


@contextmanager
def provider_turn(core_authority, *, state_owner_id=None):
    """Only the router may establish a trusted Core→provider session."""
    from core.authority_handoff import PreparedAuthority
    if not isinstance(core_authority, PreparedAuthority):
        raise ValueError("Missing trusted prepared authority.")
    core_authority.require_local()
    from core.night_routine_authority import night_provider_turn
    from core.external_data_admission import external_provider_turn
    from core.local_write_authority import local_write_turn
    token = _ACTIVE_TURN.set(core_authority)
    try:
        with night_provider_turn(core_authority, state_owner_id), external_provider_turn(core_authority), local_write_turn(core_authority):
            yield
    finally:
        _ACTIVE_TURN.reset(token)


def current_turn_authority():
    return _ACTIVE_TURN.get()
