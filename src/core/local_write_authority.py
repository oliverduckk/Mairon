"""SEC-03: five explicit local writes, bound to exact current Core values.

No model text or restored transcript can issue this process-local capability.
The existing domain adapters remain responsible for validation and storage.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date as Date, datetime, timedelta
import re
import time
from threading import RLock

from core.temporal_context import LOCAL_TIMEZONE

WRITE_TOOLS = frozenset({'set_work_location', 'set_wake_alarm', 'disable_wake_alarm', 'save_memory', 'delete_memory'})
_ISSUER = object()
_ACTIVE = ContextVar('mairon_explicit_local_write', default=None)
_DATE = r'(?:today|tomorrow|day after tomorrow|\d{4}-\d{2}-\d{2})'


def local_now():
    return datetime.now(LOCAL_TIMEZONE)


def _date(value):
    value = value.lower()
    if value in {'today', 'tomorrow', 'day after tomorrow'}:
        return (local_now().date() + timedelta(days={'today': 0, 'tomorrow': 1, 'day after tomorrow': 2}[value])).isoformat()
    try:
        return Date.fromisoformat(value).isoformat() if Date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def _time(value):
    match = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', value, re.I)
    if match:
        hour, minute = int(match[1]), int(match[2] or 0)
        if not 1 <= hour <= 12 or minute > 59:
            return None
        return f'{hour % 12 + (12 if match[3].lower() == "pm" else 0):02d}:{minute:02d}'
    if re.fullmatch(r'\d{2}:\d{2}', value):
        hour, minute = map(int, value.split(':'))
        if hour < 24 and minute < 60:
            return value
    return None


@dataclass(frozen=True)
class ParsedWrite:
    tool: str | None
    values: tuple = ()
    clarification: str | None = None


def parse_local_write(text):
    """Whole affirmative utterances only; unresolved values confer no effect."""
    if not isinstance(text, str) or any(c in text for c in ('"', '“', '”', '`', '\n', '\r', ';')):
        return None
    value = text.strip().replace('’', "'")
    value = re.sub(r'^(?:(?:hey|bro|mairon)[, ]+)?(?:(?:can|could|would) you (?:please )?|please )?', '', value, flags=re.I)
    command = value.rstrip(' .!?')
    if re.search(r'\b(?:and then|but|or|if|unless|instead|ignore (?:the|all)|system:|assistant:)\b', command, re.I):
        return None
    if re.search(r'\band\s+(?:set|disable|cancel|delete|forget|remember|open|close|save|change|start)\b', command, re.I):
        return None
    # Free-form memory content must not swallow a second command or a
    # withdrawal of consent. Declarative dislikes ("I do not like tea") remain
    # ordinary content; effect verbs after a prohibition are not authority.
    if re.search(r"\b(?:do not|don't|dont|never)\s+(?:save|store|record|remember|delete|forget|set|disable|cancel|do)\b", command, re.I):
        return None
    if re.search(r"[.!?,:—–]\s*(?:please\s+)?(?:do not|don't|dont|never|ignore|save|store|record|remember|delete|forget|set|disable|cancel|open|close|start|change|take|send|run)\b", command, re.I):
        return None
    match = re.fullmatch(rf'set my work location (?:for|on) (?P<date>{_DATE}) to (?P<location>home|office|wfh)', command, re.I)
    if match is None:
        match = re.fullmatch(rf'set my work location to (?P<location>home|office|wfh) (?:for |on )?(?P<date>{_DATE})', command, re.I)
    if match and _date(match['date']):
        return ParsedWrite('set_work_location', (('date', _date(match['date'])), ('location', 'home' if match['location'].lower() == 'wfh' else match['location'].lower())))
    if re.match(r'^set my work location\b', command, re.I):
        return ParsedWrite(None, clarification='Please specify home or office and a date for the work-location change.')
    match = re.fullmatch(rf'(?:set|change) (?:my|a) (?:wake )?alarm (?:for|on) ({_DATE}) (?:at|to) (.+)', command, re.I)
    if match and _date(match[1]) and _time(match[2]):
        return ParsedWrite('set_wake_alarm', (('date', _date(match[1])), ('time', _time(match[2]))))
    if re.match(r'^(?:set|change) (?:my|a) (?:wake )?alarm\b', command, re.I):
        return ParsedWrite(None, clarification='Please specify the alarm date and an unambiguous time, such as 7am or 19:00.')
    match = re.fullmatch(rf'(?:disable|cancel) my (?:wake )?alarm (?:for |on )?({_DATE})', command, re.I)
    if match and _date(match[1]):
        return ParsedWrite('disable_wake_alarm', (('date', _date(match[1])),))
    if re.match(r'^(?:disable|cancel) my (?:wake )?alarm\b', command, re.I):
        return ParsedWrite(None, clarification='Please specify the date of the wake alarm to disable.')
    match = re.fullmatch(r'(?:remember that|save (?:this|the) memory:)\s+(.+)', value, re.I)
    if match:
        content = match[1].strip()
        if (len(content) > 2000 or re.search(r'\b(?:today|tomorrow|tonight|alarm|wake me|daily context)\b', content, re.I)
                or content.lower().rstrip(' .?!') in {'this', 'that', 'it', 'everything', 'nothing'}):
            return ParsedWrite(None, clarification='Please state the lasting information to remember; daily plans and alarms use their own tools.')
        return ParsedWrite('save_memory', (('memory', content),))
    match = re.fullmatch(r'(?:forget|delete) the memory (?:about|that)\s+(.+)', value, re.I)
    if match:
        query = match[1].strip()
        if len(query) <= 500 and len(re.findall(r'\b\w{3,}\b', query)) >= 2 and query.lower().rstrip(' .?!') not in {'all memories', 'everything about me', 'all of it'}:
            return ParsedWrite('delete_memory', (('query', query),))
        return ParsedWrite(None, clarification='Please identify the specific stored memory to forget. Ambiguous matches will not be deleted.')
    return None


@dataclass(eq=False)
class LocalWriteRequest:
    turn: object
    raw: str
    tool: str
    values: tuple
    created: float = field(default_factory=time.monotonic)
    used: bool = False
    session: object = field(default=None, repr=False)
    _issuer: object = field(default=_ISSUER, repr=False)
    lock: object = field(default_factory=RLock, repr=False)
    _snapshot: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self._snapshot = (id(self), id(self.turn), self.raw, self.tool, self.values, self.created)


def bind_local_write(turn, parsed):
    if parsed.tool in WRITE_TOOLS:
        turn._local_write_request = LocalWriteRequest(turn, turn.raw_text, parsed.tool, parsed.values)


def authorised_local_write(authority):
    turn = getattr(authority, 'turn', None)
    request = getattr(turn, '_local_write_request', None)
    if (not isinstance(request, LocalWriteRequest) or request._issuer is not _ISSUER
            or request.turn is not turn or request.used or (request.session is not None and request.session.revoked)
            or request._snapshot != (id(request), id(request.turn), request.raw, request.tool, request.values, request.created)
            or not 0 <= time.monotonic() - request.created <= 600
            or getattr(turn, 'raw_text', None) != request.raw
            or getattr(turn, 'intent', None) != 'local_write_request'
            or getattr(turn, 'speech_act', None) != 'request_action'
            or getattr(turn, 'requested_action', None) != request.tool
            or getattr(getattr(authority, 'runtime', None), 'intent', None) != 'local_write_request'):
        return None
    return request


@dataclass(eq=False)
class _WriteTurn:
    authority: object
    request: object
    revoked: bool = False


@contextmanager
def local_write_turn(authority):
    session = _WriteTurn(authority, authorised_local_write(authority))
    if session.request is not None:
        with session.request.lock:
            if session.request.session is not None:
                session.request = None
            else:
                session.request.session = session
    token = _ACTIVE.set(session)
    try:
        yield
    finally:
        session.revoked = True
        _ACTIVE.reset(token)


def current_write_request():
    from tools.tool_admission import current_turn_authority
    session = _ACTIVE.get()
    if session is None or session.revoked or session.authority is not current_turn_authority():
        return None
    request = authorised_local_write(session.authority)
    return request if request is session.request and request is not None and request.session is session else None


def denied_write():
    return {'success': False, 'status': 'local_write_not_authorised',
            'message': 'That change needs a current explicit request with an exact action and value.'}


def perform_local_write(tool, payload, adapter):
    request = current_write_request()
    if request is None:
        return denied_write()
    with request.lock:
        if current_write_request() is not request or request.tool != tool or payload != dict(request.values):
            return denied_write()
        # Consume before entering a mutating adapter, including uncertain errors.
        request.used = True
    try:
        return adapter()
    except Exception:
        return {'success': False, 'status': 'local_write_outcome_unknown',
                'message': 'I could not confirm the change. Check the stored state before trying again.'}


def handle_prepared_local_write(user_input, conversation):
    """Provider bridge for Core-owned values; no model supplies write arguments."""
    from tools.tool_admission import current_turn_authority, provider_tool_scope, admitted_tools
    from tools.tool_registry import execute_tool
    authority = current_turn_authority()
    turn = getattr(authority, 'turn', None)
    if getattr(turn, 'intent', None) not in {'local_write_request', 'local_write_clarification'}:
        return None
    if getattr(turn, 'raw_text', None) != user_input.strip():
        result = denied_write()
    elif turn.intent == 'local_write_clarification':
        result = {'success': False, 'message': turn.entities['local_write_clarification']}
    else:
        request = current_write_request()
        if request is None:
            result = denied_write()
        else:
            with admitted_tools(provider_tool_scope('local', authority, [request.tool])):
                result = execute_tool(request.tool, dict(request.values))
            if result.get('success') and request.tool == 'set_wake_alarm':
                result = dict(result, message=f"The wake-alarm record is stored for {dict(request.values)['date']} at {dict(request.values)['time']}. Audio playback is not enabled.")
            elif result.get('success') and request.tool == 'set_work_location':
                result = dict(result, message='The work location was updated for that date. The existing manual or disabled alarm takes precedence over the routine recommendation.')
    answer = result.get('message') or ('The requested change was recorded.' if result.get('success') else 'The change could not be confirmed.')
    history = list(conversation or []) + [{'role':'user','content':user_input}, {'role':'assistant','content':answer}]
    return answer, history, None, None
