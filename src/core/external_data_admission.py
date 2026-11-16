"""SEC-02: field-specific admission at existing external-service sinks.

Only trusted integration code creates tasks. Model tool scopes, history, errors
and retrieved prose cannot extend their exportable fields. This is not a
sandbox against hostile Python already executing inside the process.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
import base64
import hashlib
import json
import math
import re
import time
from threading import RLock
from urllib.parse import unquote

from tools.public_url_policy import public_http_url

_ACTIVE = ContextVar('mairon_external_data_task', default=None)
_ISSUER = object()
_MAX_AGE = 600
_SECRET = re.compile(
    r'(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:api[_ -]?key|access[_ -]?token|'
    r'refresh[_ -]?token|password|secret[_ -]?key|authorization|client[_ -]?secret)'
    r'[\s"\x27]*[=:][\s"\x27]*[^\s,;}"\x27]{3,}|\bbearer\s+[^\s,;]{6,}|\bsk-[A-Za-z0-9_-]{12,})')
_SEARCH = re.compile(r'^(?:(?:please|mairon|bro)[, ]+)?(?:(?:can|could|would) you (?:please )?)?'
                     r'(?:search(?: the (?:public )?(?:web|internet))?(?: for)?|look up|research|find information (?:on|about))\s+(.+)$', re.I)
_NEGATIVE = re.compile(r'^(?:(?:please|mairon|bro)[, ]+)?(?:(?:can|could|would|will) you (?:please )?)?'
                       r'(?:do not|don\x27t|not|never|translate|my friend|i said|what happens if)\b', re.I)
_FACETS = ('official documentation', 'official release notes', 'official driver release',
           'independent evidence', 'current research', 'limitations', 'comparison', 'sources')


class ExternalDataDenied(ValueError):
    pass


def denial():
    return {'success': False, 'status': 'external_data_not_authorised',
            'message': 'That external lookup needs a current request identifying the information or locations to disclose.'}


def _deny():
    raise ExternalDataDenied(denial()['message'])


def _normal(value):
    return re.sub(r'\s+', ' ', value).strip() if isinstance(value, str) else ''


def _key(value):
    return _normal(value).casefold().rstrip(' .?!')


def contains_secret(value):
    """Defence in depth only; absence never confers public provenance."""
    if not isinstance(value, str):
        return False
    pending = [value]
    seen = set()
    for _ in range(4):
        next_values = []
        for item in pending:
            if item in seen:
                continue
            seen.add(item)
            embedded_urls = re.findall(r'https?://[^\s<>"`\\]+', item, re.I)
            if _SECRET.search(item) or any(public_http_url(url.rstrip('.,')) is None for url in embedded_urls):
                return True
            next_values.append(unquote(item))
            next_values.append(re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)), item).replace('\\"', '"'))
            for encoded in re.findall(r'(?<![\w])[A-Za-z0-9+/]{24,}={0,2}(?![\w])', item):
                try:
                    next_values.append(base64.b64decode(encoded, validate=True).decode('utf-8'))
                except (ValueError, UnicodeError):
                    pass
        pending = next_values
    return False


def _digest(value):
    try:
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError):
        _deny()


def safe_external_errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ExternalDataDenied:
            return denial()
        except Exception:
            # Service errors may echo URLs, headers, locations and query text.
            return {'success': False, 'message': 'The external lookup was unavailable.'}
    return checked


@dataclass(eq=False)
class ExternalTask:
    authority: object
    raw: str
    validator: object = None
    created: float = field(default_factory=time.monotonic)
    revoked: bool = False
    queries: dict = field(default_factory=dict)
    urls: set = field(default_factory=set)
    weather: dict = field(default_factory=dict)
    coordinates: set = field(default_factory=set)
    used: set = field(default_factory=set)
    receipts: dict = field(default_factory=dict)
    admissions: dict = field(default_factory=dict)
    public_results: dict = field(default_factory=dict)
    departures: set = field(default_factory=set)
    research: bool = False
    lock: object = field(default_factory=RLock, repr=False)
    _issuer: object = field(default=_ISSUER, repr=False)
    _snapshot: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self._snapshot = _snapshot(self.authority, self.raw)


def _snapshot(authority, raw):
    turn = getattr(authority, 'turn', None)
    return (id(authority), id(turn), raw, getattr(turn, 'raw_text', None),
            getattr(turn, 'intent', None), getattr(turn, 'requested_action', None))


def current_external_task():
    task = _ACTIVE.get()
    if (not isinstance(task, ExternalTask) or task._issuer is not _ISSUER or task.revoked
            or task._snapshot != _snapshot(task.authority, task.raw)
            or not 0 <= time.monotonic() - task.created <= _MAX_AGE):
        return None
    if task.authority is not None:
        from tools.tool_admission import current_turn_authority
        if current_turn_authority() is not task.authority:
            return None
    if task.validator is not None:
        try:
            if not task.validator():
                return None
        except Exception:
            return None
    return task


def _seed(task, *, public=False):
    raw = re.sub(r'^/cloud\s+', '', task.raw, flags=re.I)
    if not raw or contains_secret(raw) or _NEGATIVE.search(raw) or raw.startswith(('"', '“', '`')):
        return
    match = _SEARCH.fullmatch(raw)
    from core.conversational_research import normalise_public_research_query, extract_explicit_background_research_request
    explicit = extract_explicit_background_research_request(raw)
    # A source-routing preference is not consent to export personal advice
    # context. Unscoped mixed/personal turns need a fresh explicit public topic.
    ordinary_public_question = (public
        and getattr(getattr(task.authority, 'turn', None), 'intent', None) == 'factual_question'
        and not re.search(r'\b(?:i|my|mine|our|ours|we|us|me|your|previous|earlier|above|below)\b', raw, re.I)
        and not any(c in raw for c in ('\n', '\r', ';', '"', '“', '”', '`')))
    if ordinary_public_question or match or explicit:
        candidates = [explicit['topic']] if explicit else [raw]
        if match and not explicit:
            candidates.append(match[1].strip(' .?!'))
        for value in list(candidates):
            candidates.append(normalise_public_research_query(value))
        for value in candidates:
            if value and not contains_secret(value):
                task.queries[_key(value)] = value
                for facet in _FACETS:
                    task.queries[_key(value + ' ' + facet)] = value + ' ' + facet
        if explicit and explicit.get('topic') and not contains_secret(explicit['topic']):
            task.queries[_key(raw)] = explicit['topic']
    if re.match(r'^(?:(?:please|mairon|bro)[, ]+)?(?:(?:can|could|would) you (?:please )?)?'
                r'(?:read|summari[sz]e|extract|explain|check)\s+', raw, re.I) or re.fullmatch(r'https?://\S+', raw):
        for value in re.findall(r'https?://[^\s<>"`]+', raw):
            checked = public_http_url(value.rstrip('.,'))
            if checked:
                task.urls.add(checked)
        if task.urls:
            task.queries[_key(raw)] = raw
    if _weather_shape(raw):
        match = re.search(r'\b(?:in|for|at)\s+(.+?)(?:\s+(?:today|tomorrow|this (?:week|weekend)))?[.?!]*$', raw, re.I)
        if match is None:
            match = re.fullmatch(r'(?:weather|forecast|temperature)\s+(?!today\b|tomorrow\b|this\b)(.+?)[.?!]*', raw, re.I)
        if match and not contains_secret(match[1]):
            task.weather[_key(match[1])] = _normal(match[1])


def _weather_shape(raw):
    value = re.sub(r'^(?:(?:please|mairon|bro)[, ]+)', '', raw, flags=re.I)
    return (not _NEGATIVE.search(raw) and not any(c in raw for c in ('"', '“', '”', '`', '\n', '\r'))
            and bool(re.match(r'^(?:(?:what(?:\x27s| is)|how(?:\x27s| is))\s+(?:the\s+)?(?:weather|temperature|forecast)\b|'
                              r'(?:weather|forecast|temperature)\b|(?:will|is) it (?:rain|raining|windy)\b|'
                              r'(?:check|tell me|give me|show me) (?:the )?(?:weather|forecast)\b)', value, re.I)))


@contextmanager
def external_provider_turn(authority):
    raw = getattr(getattr(authority, 'turn', None), 'raw_text', None)
    task = ExternalTask(authority, raw.strip() if isinstance(raw, str) else '')
    public = getattr(authority.runtime, 'authority', None) == 'public_web'
    _seed(task, public=public)
    token = _ACTIVE.set(task)
    try:
        yield task
    finally:
        task.revoked = True
        _ACTIVE.reset(token)


def allow_weather_default(location):
    """Called only with the configured default by the trusted weather workflow."""
    task = current_external_task()
    if (task is not None and not task.weather and _weather_shape(task.raw) and not contains_secret(task.raw)
            and not re.search(r'\b(?:in|for|at)\s+\S', task.raw, re.I)
            and isinstance(location, str) and not contains_secret(location)):
        task.weather[_key(location)] = _normal(location)


def canonical_external_text(value, field):
    """Send the trusted literal, not model-controlled case/whitespace channels."""
    task = current_external_task()
    mapping = task.weather if task is not None and field == 'weather' else task.queries if task is not None else {}
    if _key(value) not in mapping:
        _deny()
    return mapping[_key(value)]


def register_query_derivation(original, derived):
    """Trusted pure query normalisers only; never pass a model/history result."""
    task = current_external_task()
    if task is not None and _key(original) in task.queries and isinstance(derived, str) and not contains_secret(derived):
        task.queries[_key(derived)] = derived


def current_public_query(value):
    task = current_external_task()
    if task is None or _key(value) not in task.queries:
        return None
    return task.queries[_key(value)]


def research_job_export_record(topic, original_request):
    """Persist only the actual current user's bounded public task, not an offer marker."""
    task = current_external_task()
    if (task is None or _key(original_request) != _key(task.raw)
            or current_public_query(topic) is None):
        return None
    return {'request': task.raw, 'topic': topic,
            'binding': _digest([topic, original_request, task.raw])}


@contextmanager
def research_external_job(job):
    """The existing trusted job store/lease owns durable consent; model plans do not."""
    record = (job.get('metadata') or {}).get('sec02_public_export')
    if (not isinstance(record, dict) or not isinstance(record.get('request'), str)
            or record.get('topic') != job.get('topic')
            or record.get('binding') != _digest([job.get('topic'), job.get('original_request'), record.get('request')])):
        token = _ACTIVE.set(None)
        try:
            yield None
        finally:
            _ACTIVE.reset(token)
        return
    snapshot = _digest({key: job.get(key) for key in ('id', 'topic', 'goal', 'original_request', 'metadata', 'lease_owner')})
    def current_job():
        from research.research_jobs import get_research_job
        current = get_research_job(job.get('id'))
        expiry = datetime.fromisoformat(current.get('lease_expires_at', '')) if isinstance(current, dict) else None
        return (isinstance(current, dict) and current.get('status') == 'running'
                and bool(current.get('lease_owner')) and expiry is not None
                and expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)
                and _digest({key: current.get(key) for key in ('id', 'topic', 'goal', 'original_request', 'metadata', 'lease_owner')}) == snapshot)
    task = ExternalTask(None, record['request'], validator=current_job)
    task.research = True
    _seed(task, public=True)
    # The existing deterministic research fallback supplies useful query
    # alternatives without consuming private metadata, prior plans or excerpts.
    from research.deep_research import _fallback_research_plan
    public_job = {'topic': record['topic'], 'goal': record['request'], 'original_request': record['request'], 'metadata': {}}
    for number in range(3):
        plan = _fallback_research_plan(public_job, {'rounds': [{}] * number})
        for query in plan.get('search_queries', []):
            if isinstance(query, str) and not contains_secret(query):
                task.queries[_key(query)] = _normal(query)
    token = _ACTIVE.set(task)
    try:
        yield task
    finally:
        task.revoked = True
        _ACTIVE.reset(token)


def research_query_choices():
    task = current_external_task()
    return list(dict.fromkeys(task.queries.values())) if task is not None and task.research else None


def register_route_departure(value):
    task = current_external_task()
    if task is not None and any(item[0].destination == 'google.routes' for item in task.receipts.values()):
        task.departures.add(value)


@dataclass(eq=False, frozen=True)
class ExternalAdmission:
    task: ExternalTask
    destination: str
    payload_hash: str
    nonce: object = field(default_factory=object, repr=False)


def _validate_external(destination, payload):
    task = current_external_task()
    if task is None or not isinstance(payload, dict) or contains_secret(json.dumps(payload, ensure_ascii=False)):
        _deny()
    valid = False
    if destination == 'tavily.search':
        valid = (set(payload) <= {'query', 'search_depth', 'topic', 'max_results', 'include_answer', 'include_raw_content', 'time_range'}
                 and payload.get('query') == task.queries.get(_key(payload.get('query'))) and bool(payload.get('query'))
                 and payload.get('search_depth') == 'basic'
                 and payload.get('topic') in {'general', 'news', 'finance'}
                 and type(payload.get('max_results')) is int and 1 <= payload['max_results'] <= 8
                 and payload.get('include_answer') is False and payload.get('include_raw_content') is False
                 and payload.get('time_range') in {None, 'day', 'week', 'month', 'year'})
    elif destination == 'tavily.extract':
        checked = public_http_url(payload.get('urls'))
        valid = (set(payload) <= {'urls', 'extract_depth', 'format', 'include_images', 'query', 'chunks_per_source'}
                 and checked is not None and checked in task.urls
                 and payload.get('extract_depth') == 'basic' and payload.get('format') == 'markdown'
                 and payload.get('include_images') is False
                 and ('query' not in payload or (bool(payload['query']) and payload['query'] == task.queries.get(_key(payload['query']))))
                 and payload.get('chunks_per_source') in {None, 3})
    elif destination == 'open-meteo.geocode':
        valid = (set(payload) == {'name', 'count', 'language', 'format'} and bool(payload['name'])
                 and payload['name'] == task.weather.get(_key(payload['name']))
                 and payload['count'] == 1 and payload['language'] == 'en' and payload['format'] == 'json')
    elif destination == 'open-meteo.forecast':
        valid = (set(payload) == {'latitude', 'longitude', 'current', 'daily', 'timezone', 'forecast_days'}
                 and (payload['latitude'], payload['longitude']) in task.coordinates
                 and payload['current'] == 'temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m'
                 and payload['daily'] == 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max'
                 and payload['timezone'] == 'auto' and payload['forecast_days'] == 3)
    elif destination == 'google.routes':
        valid = _route_payload_allowed(task, payload)
    if not valid:
        _deny()
    return task


def admit_external(destination, payload):
    task = _validate_external(destination, payload)
    admission = ExternalAdmission(task, destination, _digest(payload))
    task.admissions[admission.nonce] = admission
    return admission


def dispatch_external(admission, payload, adapter):
    if not isinstance(admission, ExternalAdmission) or current_external_task() is not admission.task:
        _deny()
    task = admission.task
    key = (admission.destination, admission.payload_hash)
    with task.lock:
        if (key in task.used or len(task.used) >= 16 or _digest(payload) != admission.payload_hash
                or task.admissions.get(admission.nonce) is not admission
                or _validate_external(admission.destination, payload) is not task):
            _deny()
        task.used.add(key)
    result = adapter(**json.loads(json.dumps(payload, allow_nan=False)))
    if current_external_task() is not task:
        _deny()
    task.receipts[admission.nonce] = (admission, _digest(result))
    if admission.destination == 'tavily.search' and isinstance(result, dict):
        for item in result.get('results', []):
            if isinstance(item, dict):
                checked = public_http_url(item.get('url'))
                if checked:
                    task.urls.add(checked)
    if admission.destination == 'open-meteo.geocode' and isinstance(result, dict):
        places = result.get('results') or []
        if places and isinstance(places[0], dict):
            lat, lon = places[0].get('latitude'), places[0].get('longitude')
            if (type(lat) in (int, float) and type(lon) in (int, float)
                    and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                task.coordinates.add((lat, lon))
    return result


class PublicServiceResult(dict):
    """Process-local receipt; serialization drops authority, never recreates it."""
    pass


def public_service_result(admission, result):
    task = current_external_task()
    if (task is None or not isinstance(admission, ExternalAdmission) or admission.task is not task
            or task.admissions.get(admission.nonce) is not admission
            or admission.nonce not in task.receipts or task.receipts[admission.nonce][0] is not admission
            or not isinstance(result, dict)
            or contains_secret(json.dumps(result, ensure_ascii=False))):
        _deny()
    output = PublicServiceResult(result)
    task.public_results[id(output)] = (output, admission.destination, _digest(output))
    return output


def eligible_public_service_result(tool_name, result):
    task = current_external_task()
    if task is None or not isinstance(result, PublicServiceResult):
        return False
    receipt = task.public_results.get(id(result))
    expected = {'web_search': 'tavily.search', 'web_read': 'tavily.extract', 'get_weather': 'open-meteo.forecast'}
    return (receipt is not None and receipt[0] is result and receipt[1] == expected.get(tool_name)
            and receipt[2] == _digest(result))


def _route_payload_allowed(task, payload):
    """Exact current-route fields; configured aliases never become generic public data."""
    raw = task.raw
    if (_NEGATIVE.search(raw) or any(c in raw for c in ('"', '“', '”', '`', '\n', '\r', ';'))
            or not re.match(r'^(?:(?:please|mairon|bro)[, ]+)?(?:(?:can|could|would) you (?:please )?)?'
                            r'(?:how long|how far|what(?:\x27s| is)|give me|show me|calculate|find|plan|drive|driving|directions|route)\b', raw, re.I)
            or not re.search(r'\b(?:route|drive|driving|travel|journey|directions|get|transit|take|commute|how long|how far)\b', raw, re.I)):
        return False
    route_text = re.sub(r'\s+(?:by|using)\s+(?:car|train|transit|public transport|park(?: and| &) ride)[.?!]*$', '', raw, flags=re.I)
    match = re.search(r'\bfrom\s+(.+?)\s+to\s+(.+?)(?:\s+(?:via|through)\s+(.+?))?[.?!]*$', route_text, re.I)
    if not match:
        destination_only = re.search(r'\bto\s+(.+?)(?:\s+(?:via|through)\s+(.+?))?[.?!]*$', route_text, re.I)
        if destination_only is None:
            return False
        # Preserve the existing home-origin route default, but only for an
        # actual current route request with a current literal destination.
        origin, destination, via_text = 'home', destination_only[1].strip(), destination_only[2]
    else:
        origin, destination, via_text = match[1].strip(), match[2].strip(), match[3]
    from tools.route_tools import resolve_location, build_waypoint, get_preferred_work_values
    via = [x.strip() for x in re.split(r'\s+and\s+', via_text)] if via_text else []
    expected_origin, expected_destination = build_waypoint(resolve_location(origin)), build_waypoint(resolve_location(destination))
    mode = 'TRANSIT' if re.search(r'\b(?:transit|public transport|by train|train from)\b', raw, re.I) else 'DRIVE'
    park_ride = bool(re.search(r'\bpark(?: and| &) ride\b', raw, re.I)) or (mode == 'TRANSIT' and _key(origin) == 'home')
    if set(payload) - {'origin', 'destination', 'travelMode', 'languageCode', 'units', 'intermediates', 'routingPreference', 'departureTime'}:
        return False
    if payload.get('languageCode') != 'en-AU' or payload.get('units') != 'METRIC':
        return False
    allowed_legs = [(expected_origin, expected_destination, mode)]
    if park_ride:
        station = build_waypoint(resolve_location('train_station'))
        allowed_legs.extend([(expected_origin, station, 'DRIVE'), (station, expected_destination, 'TRANSIT')])
    if (payload.get('origin'), payload.get('destination'), payload.get('travelMode')) not in allowed_legs:
        return False
    if payload.get('routingPreference') not in {None, 'TRAFFIC_AWARE_OPTIMAL'}:
        return False
    if 'departureTime' in payload and payload['departureTime'] not in task.departures:
        return False
    points = payload.get('intermediates') or []
    if via:
        return points == [build_waypoint(value) for value in via]
    preferred = get_preferred_work_values(origin, destination)
    return points == [] or (bool(preferred) and points in (
        [build_waypoint(value, via=True) for value in preferred],
        [build_waypoint(value, via=False) for value in preferred]))
