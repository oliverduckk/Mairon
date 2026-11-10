"""S3: bounded, purpose-specific cloud egress admission.

A model's tool permission is not permission to export the result.  Application
instructions, private Core evidence and provider histories are *not* cloud
payloads.  This module issues turn-local grants, constructs minimal requests,
and projects known public tool results; unknown classifications fail closed.

S4 will own historical context projections and response-ID compatibility.  Until
then no prior response handle or reconstructed provider history is exported.
"""
from dataclasses import dataclass, field
import hashlib
import json
import re
import time
from threading import Lock
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from core.authority_handoff import PreparedAuthority

_DESTINATION = "openai.responses"
_ISSUER = object()
_MAX_PROMPT = 12000
_MAX_INSTRUCTIONS = 2600
_MAX_OUTPUT = 13500
_ALLOWED_PURPOSES = frozenset({"explicit_cloud_request", "approved_cloud_escalation"})
_ALLOWED_TOOLS = frozenset({"get_weather", "web_search", "web_read"})
_SENSITIVE_PATTERN = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:api[_ -]?key|access[_ -]?token|"
    r"refresh[_ -]?token|password|secret[_ -]?key|authorization)\s*[=:]\s*"
    r"[^\s,;]{3,}|\bbearer\s+[^\s,;]{6,}|\bsk-[A-Za-z0-9_-]{12,})"
)

class CloudExportDenied(ValueError):
    """Payload or grant has not met the cloud export boundary."""


def _deny() -> None:
    # Never put rejected input, model arguments or tool results in diagnostics.
    raise CloudExportDenied("Cloud export was not authorised for this payload.")


def _safe_text(value: Any, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _deny()
    if "\x00" in value or _SENSITIVE_PATTERN.search(value):
        _deny()
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CloudExportManifest:
    destination: str
    purpose: str
    data_classes: tuple[str, ...]
    field_names: tuple[str, ...]
    total_bytes: int


@dataclass(frozen=True)
class CloudExportAdmission:
    payload: dict[str, Any]
    manifest: CloudExportManifest
    _issuer: object = field(default=None, repr=False)
    _payload_hash: str = field(default="", repr=False)


@dataclass
class CloudExportGrant:
    purpose: str
    prompt_digest: str
    _issuer: object = field(repr=False)
    _created: float = field(repr=False)
    _revoked: bool = field(default=False, repr=False)
    policy_flags: tuple[bool, bool, bool] = field(default=(False, False, False), repr=False)
    _initial_used: bool = field(default=False, repr=False)
    _followup_used: bool = field(default=False, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def revoke(self) -> None:
        with self._lock:
            self._revoked = True

    def consume(self, stage: str, prompt: str) -> None:
        """One initial SDK request and at most one same-turn follow-up."""
        with self._lock:
            self.require(prompt)
            if stage == "initial" and not self._initial_used:
                self._initial_used = True
            elif stage == "followup" and self._initial_used and not self._followup_used:
                self._followup_used = True
            else:
                _deny()

    def require(self, prompt: str) -> None:
        if (self._issuer is not _ISSUER or self._revoked
                or self.purpose not in _ALLOWED_PURPOSES
                or time.monotonic() - self._created > 600
                or not isinstance(prompt, str)
                or self.prompt_digest != _digest(prompt)):
            _deny()


def issue_cloud_export_grant(authority: PreparedAuthority, prompt: str,
                             *, purpose: str) -> CloudExportGrant:
    """Only the router may use this for a verified explicit or approved route.

    The grant covers the *current user prompt*, not stored history, app
    instructions, private records, or arbitrary tools.  Approval to run a cloud
    model never grants export of other data classes.
    """
    if not isinstance(authority, PreparedAuthority) or purpose not in _ALLOWED_PURPOSES:
        _deny()
    try:
        authority.require_cloud()
    except Exception as exc:
        raise CloudExportDenied("Core has not authorised cloud export for this turn.") from None
    _safe_text(prompt, maximum=_MAX_PROMPT)
    r = authority.runtime
    return CloudExportGrant(
        purpose, _digest(prompt), _ISSUER, time.monotonic(),
        policy_flags=(r.allow_recommendations, r.allow_new_factual_claims,
                      r.allow_follow_up_question),
    )


# A static, reviewed instruction subset, NOT the application's full personal
# identity/continuity/contract string.  Keep cloud Core obligations limited to
# those supported by S1's require_cloud() check.
_CLOUD_INSTRUCTIONS = (
    "You are Mairon. Respond to the user's current message naturally, accurately "
    "and concisely. Be conversational and independent-minded, without invented "
    "personal experiences or fabricated prior conversation. Do not claim to have "
    "accessed memories, private accounts or files. Only use the current user's "
    "message and explicitly admitted public tool results as task context. "
    "Do not claim an action was performed without a successful admitted tool result. "
    "If evidence is missing, state the limitation. Do not infer hidden user history."
)


# Tool advertisements are outbound data too.  Do not forward the registry's
# free-form descriptions: some include local personalisation.  These static
# declarations contain only the three reviewed public tool interfaces.
_REVIEWED_CLOUD_FUNCTIONS = (
    ("get_weather", "Get current public weather for a location.",
     {"location": {"type": "string"}}, ("location",)),
    ("web_search", "Search the public internet for current information.",
     {"query": {"type": "string"},
      "topic": {"type": "string", "enum": ["general", "news", "finance"]},
      "time_range": {"type": "string", "enum": ["none", "day", "week", "month", "year"]}},
     ("query", "topic", "time_range")),
    ("web_read", "Read a publicly accessible web page.",
     {"url": {"type": "string"}, "focus": {"type": "string"}},
     ("url", "focus")),
)


def admit_cloud_tool_definitions(registry_tools: Any) -> list[dict]:
    """Verify registered tool schemas, then emit only reviewed public fields."""
    if not isinstance(registry_tools, list):
        _deny()
    names = [x.get("name") for x in registry_tools if isinstance(x, dict)]
    if (len(names) != len(registry_tools) or not all(isinstance(x, str) for x in names)
            or sorted(names) != sorted(x[0] for x in _REVIEWED_CLOUD_FUNCTIONS)):
        _deny()
    output = []
    for name, description, properties, required in _REVIEWED_CLOUD_FUNCTIONS:
        entry = next(x for x in registry_tools if x.get("name") == name)
        schema = entry.get("parameters")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            _deny()
        if set(schema.get("properties", {})) != set(properties):
            _deny()
        if set(schema.get("required", [])) != set(required):
            _deny()
        for key, expected in properties.items():
            field = schema["properties"].get(key)
            if not isinstance(field, dict) or any(field.get(k) != v for k, v in expected.items()):
                _deny()
        output.append({
            "type": "function", "name": name, "description": description,
            "parameters": {
                "type": "object", "properties": properties,
                "required": list(required), "additionalProperties": False,
            },
            "strict": True,
        })
    return output


def _instructions_for(grant: CloudExportGrant) -> str:
    recommendations, new_facts, followups = grant.policy_flags
    restrictions = []
    if not recommendations:
        restrictions.append("Do not make unsolicited recommendations.")
    if not new_facts:
        restrictions.append("Do not add factual claims absent from admitted evidence.")
    if not followups:
        restrictions.append("Do not append a follow-up question.")
    return _CLOUD_INSTRUCTIONS + (" " + " ".join(restrictions) if restrictions else "")


def _payload_digest(payload: dict) -> str:
    try:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        _deny()
    return _digest(encoded)


def _admission(grant: CloudExportGrant, payload: dict,
               classes: tuple[str, ...]) -> CloudExportAdmission:
    return CloudExportAdmission(
        payload, _manifest(grant, payload, classes), _ISSUER, _payload_digest(payload),
    )


def _manifest(grant: CloudExportGrant, payload: dict, classes: tuple[str, ...]) -> CloudExportManifest:
    return CloudExportManifest(
        destination=_DESTINATION, purpose=grant.purpose,
        data_classes=classes, field_names=tuple(sorted(payload)),
        total_bytes=len(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
    )


def admit_cloud_initial(grant: CloudExportGrant, prompt: str,
                        *, previous_state: Any = None) -> CloudExportAdmission:
    """Final outbound request builder: no application prose or history.

    In S3 an old response ID (or restored message list) has no verified egress
    lineage.  S4 will add qualified handle support; never forward it here.
    """
    if not isinstance(grant, CloudExportGrant):
        _deny()
    grant.require(prompt)
    _safe_text(prompt, maximum=_MAX_PROMPT)
    # No previous_response_id on the initial request, regardless of the shape
    # of previous_state.  Avoid forwarding unknown handles rather than treating
    # them as proof of an approved historical context projection.
    payload = {"instructions": _instructions_for(grant), "input": prompt,
               "previous_response_id": None}
    return _admission(
        grant, payload, ("user_current_prompt", "reviewed_cloud_instructions")
    )


def admit_cloud_sdk_request(grant: CloudExportGrant, prompt: str,
                            admission: CloudExportAdmission, *, model: str,
                            registry_tools: Any) -> CloudExportAdmission:
    """Produce the COMPLETE outbound SDK argument set and field manifest.

    The caller has no second path for adding arbitrary instructions or tool
    output after this admission.  Both initial and follow-up requests use it.
    """
    if not isinstance(grant, CloudExportGrant) or not isinstance(admission, CloudExportAdmission):
        _deny()
    grant.require(prompt)
    if admission._issuer is not _ISSUER or _payload_digest(admission.payload) != admission._payload_hash:
        _deny()
    if admission.payload.get("instructions") != _instructions_for(grant):
        _deny()
    if set(admission.payload) != {"instructions", "input", "previous_response_id"}:
        _deny()
    safe_model = _safe_text(model, maximum=100)
    projected_tools = admit_cloud_tool_definitions(registry_tools)
    payload = {
        **admission.payload, "model": safe_model, "tools": projected_tools,
        "parallel_tool_calls": False,
    }
    return _admission(
        grant, payload, admission.manifest.data_classes +
        ("reviewed_public_tool_schemas", "provider_model_id"),
    )


def _public_url(value: Any) -> str:
    text = _safe_text(value, maximum=1800)
    try:
        p = urlsplit(text)
        if (p.scheme not in {"https", "http"} or not p.hostname or p.username
                or p.password or p.query or p.fragment):
            _deny()
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except ValueError:
        _deny()


def _project_number(data: dict, name: str, output: dict) -> None:
    if name in data:
        value = data[name]
        if not isinstance(value, (float, int)) or isinstance(value, bool):
            _deny()
        output[name] = value


def _project_text(data: dict, name: str, output: dict, limit: int = 800) -> None:
    if name in data:
        output[name] = _safe_text(data[name], maximum=limit)


def _project_weather(result: dict) -> dict:
    projected = {"success": True}
    if "location" in result:
        item = result["location"]
        if not isinstance(item, dict): _deny()
        loc = {}
        for key in ("name", "country", "region"):
            if item.get(key) is not None:
                _project_text(item, key, loc, 200)
        for key in ("latitude", "longitude"):
            _project_number(item, key, loc)
        projected["location"] = loc
    if "current" in result:
        item = result["current"]
        if not isinstance(item, dict): _deny()
        current = {}
        _project_text(item, "conditions", current, 150)
        for key in ("temperature_c", "feels_like_c", "precipitation_mm", "wind_speed_kmh"):
            _project_number(item, key, current)
        projected["current"] = current
    if "forecast" in result:
        entries = result["forecast"]
        if not isinstance(entries, list) or len(entries) > 3: _deny()
        projected["forecast"] = []
        for item in entries:
            if not isinstance(item, dict): _deny()
            forecast = {}
            _project_text(item, "date", forecast, 20)
            _project_text(item, "conditions", forecast, 150)
            for key in ("max_temperature_c", "min_temperature_c", "precipitation_probability_percent"):
                _project_number(item, key, forecast)
            projected["forecast"].append(forecast)
    return projected


def _project_web_search(result: dict) -> dict:
    projected = {"success": True}
    for key in ("query", "topic", "time_range"):
        if result.get(key) is not None:
            _project_text(result, key, projected, 500)
    if "results" in result:
        results = result["results"]
        if not isinstance(results, list) or len(results) > 5: _deny()
        projected["results"] = []
        for entry in results:
            if not isinstance(entry, dict): _deny()
            public = {}
            for key in ("title", "content", "published_date"):
                if entry.get(key) is not None:
                    _project_text(entry, key, public, 1600 if key == "content" else 280)
            if entry.get("url") is not None:
                public["url"] = _public_url(entry["url"])
            _project_number(entry, "score", public)
            projected["results"].append(public)
    return projected


def _project_web_read(result: dict) -> dict:
    projected = {"success": True}
    if result.get("url") is not None:
        projected["url"] = _public_url(result["url"])
    for key, limit in (("focus", 500), ("content", 7000)):
        if result.get(key) is not None:
            _project_text(result, key, projected, limit)
    return projected


def project_cloud_tool_result(tool_name: str, result: Any) -> str:
    """Allow only known public result fields; never serialize arbitrary output.

    External error/exception text, provenance metadata and unknown nested keys
    are deliberately excluded.  A private tool name can receive only a generic
    denial (the S2 executor separately denies the actual invocation).
    """
    if tool_name not in _ALLOWED_TOOLS:
        projected = {"success": False, "message": "Tool result not eligible for cloud export."}
    elif not isinstance(result, dict) or not isinstance(result.get("success"), bool):
        _deny()
    elif not result["success"]:
        projected = {"success": False, "message": "Public lookup was unavailable."}
    elif tool_name == "get_weather":
        projected = _project_weather(result)
    elif tool_name == "web_search":
        projected = _project_web_search(result)
    else:
        projected = _project_web_read(result)
    serialized = json.dumps(projected, ensure_ascii=False, allow_nan=False)
    if len(serialized.encode("utf-8")) > _MAX_OUTPUT:
        _deny()
    return serialized


def admit_cloud_tool_followup(grant: CloudExportGrant, prompt: str,
                              *, tool_name: str, tool_result: Any,
                              call_id: str, response_id: str) -> CloudExportAdmission:
    """Re-check original grant before every request, including tool output."""
    if not isinstance(grant, CloudExportGrant): _deny()
    grant.require(prompt)
    if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", call_id):
        _deny()
    if not isinstance(response_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", response_id):
        _deny()
    output = project_cloud_tool_result(tool_name, tool_result)
    payload = {
        "instructions": _instructions_for(grant),
        "previous_response_id": response_id,
        "input": [{"type": "function_call_output", "call_id": call_id, "output": output}],
    }
    return _admission(
        grant, payload,
        ("public_tool_result_projection", "reviewed_cloud_instructions", "same_request_response_handle")
    )
