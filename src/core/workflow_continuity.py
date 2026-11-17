"""INT-01: process-local, owner-bound workflow context, never model history.

Three bounded entries only. Restoring a transcript creates a fresh empty state.
Existing final night, tool, route and durable research guards still own effects.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import re
import time
from uuid import uuid4

_ISSUER = object()
_PREPARING = ContextVar('mairon_workflow_preparation', default=None)
_ACTIVE = ContextVar('mairon_workflow_continuation', default=None)
_MANAGED = ContextVar('mairon_managed_workflow', default=False)
TTL = 600


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


@dataclass(eq=False)
class WorkflowEntry:
    kind: str
    payload: str
    owner: str
    source_turn: str
    sequence: int
    created: float = field(default_factory=time.monotonic)
    token: str = field(default_factory=lambda: uuid4().hex)
    proof: object = field(default=None, repr=False)
    used: bool = False
    export_issued: bool = False
    job_issued: bool = False
    _issuer: object = field(default=_ISSUER, repr=False)
    _seal: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self._seal = self.snapshot()

    def snapshot(self):
        return (id(self), self.kind, self.payload, self.owner, self.source_turn,
                self.sequence, self.created, self.token, id(self.proof))


class WorkflowState:
    def __init__(self, owner):
        self.owner = owner
        self._identity = (id(self), owner, _ISSUER)
        self.entries = {}
        self.research_restatement_required = False
        self.sequence = 0
        self.text = ''

    def valid(self, owner):
        return (isinstance(owner, str) and bool(owner) and self.owner == owner
                and self._identity == (id(self), owner, _ISSUER))

    def get(self, kind):
        entry = self.entries.get(kind)
        if (not isinstance(entry, WorkflowEntry) or entry._issuer is not _ISSUER
                or entry._seal != entry.snapshot() or entry.used or entry.owner != self.owner
                or not 0 <= time.monotonic() - entry.created <= TTL):
            if entry is not None and kind == 'research': self.research_restatement_required = True
            self.entries.pop(kind, None)
            return None
        return entry

    def clear(self, kind=None):
        if kind in (None, 'research') and self.entries.get('research') is not None:
            self.research_restatement_required = True
        for entry in list(self.entries.values()) if kind is None else [self.entries.get(kind)]:
            if isinstance(entry, WorkflowEntry): entry.used = True
        if kind is None: self.entries.clear()
        else: self.entries.pop(kind, None)

    def begin(self, text, owner):
        if not self.valid(owner):
            self.clear()
            return
        self.sequence += 1
        self.text = text.strip()
        for kind in tuple(self.entries): self.get(kind)
        from core.night_routine_authority import affirmative_work_location
        if not affirmative_work_location(text): self.clear('night')
        if re.match(r'^/cloud\b', text, re.I) or text.lower().strip(' .!?') in {'cancel', 'never mind', 'nevermind'}:
            self.clear()
        if re.search(r'\bfrom\b.+\bto\b', text, re.I): self.clear('route')
        if re.match(r'^(?:please )?(?:research|search|look up)\b', text, re.I): self.clear('research')
        from core.debate_state import extract_pairwise_comparison
        if extract_pairwise_comparison(text) is not None: self.clear('research')


@contextmanager
def preparing(state, owner, text):
    value = state if isinstance(state, WorkflowState) and state.valid(owner) and state.text == text.strip() else None
    token = _PREPARING.set(value)
    try: yield
    finally: _PREPARING.reset(token)


def _route_reply(text):
    from core.external_data_admission import contains_secret
    if (not isinstance(text, str) or contains_secret(text)
            or any(c in text for c in ('"', '“', '”', '`', '\n', '\r', ';'))): return None
    value = text.strip()
    normal = re.fullmatch(r'(?:please )?(?:(?:go|take|use|show me) )?(?:my |the )?(?:normal|usual|preferred|regular) (?:route|way)(?: again)?[.!?]*', value, re.I)
    if normal: return []
    match = re.fullmatch(r'(?:what if (?:I|we) (?:go|went)|what about(?: going)?|go|route|drive)?\s*(?:through|via)\s+(.+?)(?:\s+instead)?[.!?]*', value, re.I)
    if not match: return None
    place = match[1].strip(' .?!')
    if (not place or len(place) > 180 or re.search(r'\b(?:and|but|if|unless|my|our|previous|ignore|system|assistant|then)\b', place, re.I)):
        return None
    return [place]


def bind_followup(turn):
    state = _PREPARING.get()
    if state is None: return False
    from core.night_routine_authority import affirmative_work_location
    from core.conversational_research import classify_research_permission_reply
    kind = None
    if state.get('night') and affirmative_work_location(turn.raw_text): kind = 'night'
    elif (state.get('research') or state.research_restatement_required) and classify_research_permission_reply(turn.raw_text): kind = 'research'
    elif state.get('route') and _route_reply(turn.raw_text) is not None: kind = 'route'
    if kind is None: return False
    turn._workflow_followup = (state, state.sequence, state.get(kind), turn.raw_text)
    turn.intent = 'workflow_continuation'
    turn.speech_act = 'request_action'
    turn.requested_action = None  # Never a generic local-write or desktop grant.
    turn.requires_private_data = True
    turn.should_use_tools = True
    turn.should_answer_directly = False
    turn.preferred_authority = 'local_tools'
    turn.add_reason('owner-bound current workflow continuation; final effect checks still required')
    return True


@contextmanager
def workflow_turn(state, owner, authority):
    valid = (isinstance(state, WorkflowState) and state.valid(owner)
             and state.text == getattr(getattr(authority, 'turn', None), 'raw_text', None))
    token = _ACTIVE.set((state, authority) if valid else None)
    managed_token = _MANAGED.set(state is not None)
    try: yield
    finally:
        _ACTIVE.reset(token)
        _MANAGED.reset(managed_token)


def managed():
    return _MANAGED.get()


def active():
    from tools.tool_admission import current_turn_authority
    value = _ACTIVE.get()
    if value is None: return None
    state, authority = value
    if not state.valid(state.owner) or current_turn_authority() is not authority: return None
    if state.text != getattr(authority.turn, 'raw_text', None): return None
    authority.require_local()
    return state


def current_entry(kind):
    state = active()
    if state is None: return None
    entry = state.get(kind)
    authority = _ACTIVE.get()[1]
    marker = getattr(authority.turn, '_workflow_followup', None)
    if (entry is None or marker != (state, state.sequence, entry, state.text)
            or authority.runtime.intent != 'workflow_continuation'):
        return None
    return entry


def _put(kind, payload, proof=None):
    state = active()
    if state is None: return None
    encoded = _json(payload)
    if len(encoded) > 6000: return None
    state.clear(kind)
    if kind == 'research': state.research_restatement_required = False
    entry = WorkflowEntry(kind, encoded, state.owner, state.text, state.sequence, proof=proof)
    state.entries[kind] = entry
    return entry


def publish_night(pending):
    from core.night_routine_authority import _current, _pending_valid
    state = _current()
    if state is not None and _pending_valid(pending, state):
        return _put('night', {'date':pending.target_date}, pending)


def pending_night():
    entry = current_entry('night')
    return entry.proof if entry is not None else None


def publish_route(arguments, result):
    from core.external_data_admission import current_external_task
    task = current_external_task()
    if (task is None or not isinstance(result, dict) or result.get('success') is not True
            or not any(receipt[0].destination == 'google.routes' for receipt in task.receipts.values())): return
    from tools.tool_registry import validate_tool_arguments
    parsed, error = validate_tool_arguments('get_route', arguments, model_origin=True)
    if error is None:
        _put('route', {**parsed, 'result':{k:result[k] for k in ('duration_minutes','total_duration_minutes') if k in result}})


def route_context():
    entry = current_entry('route')
    return json.loads(entry.payload) if entry is not None else None


def route_request_text():
    entry = current_entry('route')
    if entry is None: return None
    state = active()
    payload = json.loads(entry.payload)
    via = _route_reply(state.text)
    if via is None or (via and payload['mode'] != 'drive'): return None
    suffix = ' by public transport' if payload['mode'] in {'transit','park_and_ride'} else ''
    return f"Give me a route from {payload['origin']} to {payload['destination']}" + (' via '+via[0] if via else '') + suffix


def publish_research(proposal):
    state = active()
    if state is None: return
    state.clear('research')
    if not isinstance(proposal, dict): return
    from core.debate_state import extract_pairwise_comparison
    from core.external_data_admission import current_public_query, contains_secret
    topic = proposal.get('topic')
    if not isinstance(topic, str) or contains_secret(topic): return
    comparison = extract_pairwise_comparison(state.text)
    allowed = current_public_query(topic) is not None or (
        comparison is not None and topic == comparison['label']
        and not re.search(r'\b(?:my|our|me|private|secret|password|token)\b', topic, re.I)
        and not any(c in state.text for c in ('"','“','”','`','\n','\r',';')))
    if not allowed or proposal.get('original_request') != state.text: return
    # Only bounded public topic leaves this sidecar; discard history/metadata.
    return _put('research', {'proposal_id':proposal.get('proposal_id'), 'topic':topic,
        'goal':'Research trustworthy public information about '+topic+'.', 'original_request':state.text,
        'priority':'background','depth':'deep','metadata':{}})


def research_proposal():
    entry = current_entry('research')
    return json.loads(entry.payload) if entry is not None else None


def consume_research(proposal, decision):
    entry = current_entry('research')
    if entry is None or json.loads(entry.payload) != proposal: return None
    from core.conversational_research import classify_research_permission_reply
    if classify_research_permission_reply(active().text) != decision: return None
    entry.used = True
    active().research_restatement_required = True
    if decision == 'decline': return True
    # SEC-02 validates this exact consumed entry at durable job creation.
    return entry


def approved_research_record(topic, original_request):
    state = active()
    if state is None: return None
    entry = state.entries.get('research')
    from core.conversational_research import classify_research_permission_reply
    from core.external_data_admission import _digest
    if (not isinstance(entry, WorkflowEntry) or not entry.used or entry.export_issued or entry._seal != entry.snapshot()
            or entry.owner != state.owner or not 0 <= time.monotonic()-entry.created <= TTL
            or classify_research_permission_reply(state.text) != 'approve'
            or getattr(_ACTIVE.get()[1].turn, '_workflow_followup', None) != (state,state.sequence,entry,state.text)):
        return None
    payload = json.loads(entry.payload)
    if topic != payload['topic'] or original_request != payload['original_request']: return None
    entry.export_issued = True
    request = 'Research '+topic
    return {'request':request,'topic':topic,'binding':_digest([topic,original_request,request])}


def require_research_creation(entry, topic, goal, original_request, *, export_record=None, final=False):
    """Recheck the consumed offer at the durable insertion boundary."""
    state = active()
    if (state is None or not isinstance(entry, WorkflowEntry)
            or state.entries.get('research') is not entry or entry._issuer is not _ISSUER
            or not entry.used or entry.job_issued or entry._seal != entry.snapshot()
            or entry.owner != state.owner or not 0 <= time.monotonic()-entry.created <= TTL
            or getattr(_ACTIVE.get()[1].turn, '_workflow_followup', None) != (state,state.sequence,entry,state.text)):
        raise PermissionError('Current research continuation authority is unavailable.')
    payload = json.loads(entry.payload)
    if (topic, goal, original_request) != (payload['topic'], payload['goal'], payload['original_request']):
        raise PermissionError('Research continuation content changed.')
    if final:
        from core.external_data_admission import _digest
        request = 'Research '+topic
        expected = {'request':request,'topic':topic,'binding':_digest([topic,original_request,request])}
        if not entry.export_issued or export_record != expected:
            raise PermissionError('Research continuation export authority is unavailable.')
        entry.job_issued = True
