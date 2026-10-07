"""Explicit Core ingress adapters for candidate evidence.

These functions accept Core-owned ingress, not model-authored claims about
provenance. Raw source bodies remain data. Prefixes identify legacy transport
formats; they are not proof that arbitrary model text has Core authority.
No adapter generates facts, reclassifies intent, or decides final acceptance.
"""
from collections.abc import Mapping
from dataclasses import replace
import hashlib
import json
from typing import Any, Iterable, Optional

from core.answer_contract_runtime import AnswerContractRuntime
from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus


_PACKET_PREFIXES = (
    "CORE PUBLIC FACTUAL EVIDENCE PACKET:",
    "CORE PUBLIC-SOURCE EVIDENCE PACKET:",
    "CORE FINAL SYNTHESIS ROUND EVIDENCE:",
    "CORE FINAL SYNTHESIS EVIDENCE:",
)
_STATUS_PREFIXES = ("CORE PUBLIC FACTUAL RESEARCH STATUS:", "MEDIA RESEARCH RESULT:")
_SOURCE_METADATA = (
    "source_host", "published_date", "source_medium", "medium_alignment",
    "search_snippet", "relevance_status", "relevance_reasons",
)
_CONSTRAINT_KEYS = (
    "answer_scope", "requested_medium", "spoiler_profile", "recommendation_requested",
    "freshness_required", "forecast_requested", "quality",
)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _records(value: Any) -> tuple:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("Evidence records must be a list or tuple")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError("Evidence records must be mappings")
    return tuple(value)


def _id(kind: EvidenceKind, claim: str, provenance: str, identity: str = "") -> str:
    payload = json.dumps([kind.value, claim, provenance, identity], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bundle(authority: str, items: Iterable[Evidence], *, uncertainty=None, metadata=None) -> EvidenceBundle:
    items = list(items)
    return EvidenceBundle(
        authority=authority, evidence=items,
        success=any(item.is_authoritative_fact for item in items),
        uncertainty=uncertainty, canonical=True, metadata=dict(metadata or {}),
    ).snapshot()


def _uncertainty(reason: str) -> Evidence:
    return Evidence(
        claim="", provenance="core_evidence_availability", confidence="unavailable",
        kind=EvidenceKind.UNCERTAINTY, status=EvidenceStatus.UNAVAILABLE,
        limitations=(reason,), authority_scope="evidence_availability",
        evidence_id=_id(EvidenceKind.UNCERTAINTY, reason, "core_evidence_availability"),
    )


def _packet(value: Any) -> Mapping:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        raise TypeError("Research ingress must be a mapping or a Core packet string")
    value = value.strip()
    if value.startswith(_STATUS_PREFIXES):
        return {"success": False, "uncertainty": value, "sources": []}
    if not value.startswith("{"):
        if not value.startswith(_PACKET_PREFIXES):
            raise ValueError("Unrecognized research packet format")
        # Producers append one JSON object on its own line. Do not search
        # inside source strings or silently accept a second/trailing object.
        lines = value.splitlines(keepends=True)
        offset = 0
        for line in lines:
            if line.lstrip().startswith("{"):
                value = value[offset:]
                break
            offset += len(line)
        else:
            raise ValueError("Core research packet has no JSON payload")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Research packet must contain one JSON object")
    return parsed


def _identity(source: Mapping) -> str:
    return _text(source.get("url")) or _text(source.get("source_id"))


def _source_veto(source: Mapping) -> Optional[str]:
    if source.get("accepted_as_evidence") is False or source.get("relevance_status") == "rejected":
        return "Core source eligibility rejected this source"
    if source.get("read_success") is False:
        return "Source read failed"
    alignment = source.get("medium_alignment")
    if (isinstance(alignment, str) and alignment in {"mismatch", "incompatible", "rejected"}) or (
        type(alignment) in (int, float) and alignment < 0
    ):
        return "Source is outside the permitted media boundary"
    return None


def _constraints(payload: Mapping) -> dict:
    result = {key: payload[key] for key in _CONSTRAINT_KEYS if key in payload}
    aliases = {
        "research_query": "query", "freshness_window": "time_range",
        "freshness_required": "freshness_sensitive", "answer_mode": "research_mode",
    }
    for key, alias in aliases.items():
        if key in payload:
            result[key] = payload[key]
        elif alias in payload:
            result[key] = payload[alias]
    return result


def _research_source(source: Mapping, kind: EvidenceKind, *, veto=None, index=None, normalized=None) -> Evidence:
    index = _mapping(index)
    merged = dict(source)
    # Index provenance can constrain a packet, but cannot provide its content
    # or overwrite an explicit source rejection with an affirmative flag.
    for key in ("title", "url", "source_host", "source_quality", "authority_tier", "published_date"):
        if index.get(key) is not None:
            merged[key] = index[key]
    quality_eligible = source.get("quality_eligible")
    if index.get("quality_eligible") is False or quality_eligible is False:
        quality_eligible = False
    elif type(index.get("quality_eligible")) is bool:
        quality_eligible = index["quality_eligible"]
    if type(quality_eligible) is not bool:
        quality_eligible = None
    reason = veto or _source_veto(source) or _source_veto(index)
    read_result = _mapping(source.get("read_result"))
    if read_result.get("success") is False:
        reason = reason or "Source read result explicitly failed"
    content = _text(source.get("content_excerpt")) or _text(read_result.get("content"))
    raw_read = "read_result" in source
    malformed_flag = any(
        key in record and record[key] is not None and type(record[key]) is not bool
        for record in (source, index) for key in ("read_success", "accepted_as_evidence")
    )
    malformed_flag = malformed_flag or (
        "read_result" in source and not isinstance(source["read_result"], Mapping)
    ) or (
        "success" in read_result and type(read_result["success"]) is not bool
    )
    if reason:
        status = EvidenceStatus.REJECTED
    elif malformed_flag:
        status, reason = EvidenceStatus.UNASSESSED, "Source eligibility flags are malformed"
    elif raw_read and source.get("read_success") is not True:
        status, reason = EvidenceStatus.UNAVAILABLE, "Source read was not confirmed"
    elif not content:
        status, reason = EvidenceStatus.UNAVAILABLE, "No readable source content is available"
    else:
        status = EvidenceStatus.ADMISSIBLE
    if normalized is not None and not reason:
        status = normalized.status
    limitations = tuple(normalized.limitations) if normalized is not None else ()
    if reason and reason not in limitations:
        limitations += (reason,)
    url = _text(merged.get("url")) or None
    provenance = "core_public_source" if kind == EvidenceKind.PUBLIC_SOURCE else "core_media_source"
    data = {key: merged[key] for key in _SOURCE_METADATA if key in merged}
    snippet = source.get("search_snippet", source.get("snippet"))
    if snippet is not None:
        data["search_snippet"] = snippet
    return Evidence(
        claim=content, provenance=provenance, confidence="source_assertion",
        source_name=_text(merged.get("title")) or None,
        source_id=_text(source.get("source_id")) or None,
        source_url=url, source_quality=_text(merged.get("source_quality")) or None,
        authority_tier=_text(merged.get("authority_tier")) or None,
        quality_eligible=quality_eligible, data=data, kind=kind, status=status,
        evidence_id=_id(kind, content, provenance, url or ""),
        limitations=limitations,
        authority_scope="retrieved_source_assertions",
    )


def normalize_research_evidence(value: Any, *, kind: EvidenceKind) -> EvidenceBundle:
    """Normalize raw research, packets, or a final-synthesis envelope.

Core supplies the domain explicitly. Exclusion diagnostics and source-index
vetoes remain stronger than top-level success or a packet's implied eligibility.
An index/title/snippet/planner record alone never becomes factual evidence.
"""
    if kind not in {EvidenceKind.PUBLIC_SOURCE, EvidenceKind.MEDIA_SOURCE}:
        raise ValueError("Research domain must be public or media evidence")
    payload = _packet(value)
    index_records = _records(payload.get("source_index"))
    indexes = {}
    for source in index_records:
        identity = _identity(source)
        if identity:
            indexes.setdefault(identity, []).append(source)
    exclusions = {}
    diagnostic_records = []
    for field in ("rejected_sources", "skipped_medium_mismatch_sources", "skipped_spoiler_heavy_sources"):
        for source in _records(payload.get(field)):
            reason = "Core excluded source: " + field
            if _identity(source):
                exclusions[_identity(source)] = reason
            diagnostic_records.append((source, reason))
    sources = list(_records(payload.get("sources")))
    normalized_sources = []
    inherited_items = []
    inherited_uncertainty = []
    metadata = _constraints(payload)
    packet_constraints = []
    if "evidence_packets" in payload:
        for record in _records(payload["evidence_packets"]):
            child = _packet(record.get("packet"))
            # Normalize children first so their own exclusions/read failures
            # cannot disappear when flattening the envelope.
            child_bundle = normalize_research_evidence(child, kind=kind)
            packet_constraints.append({
                **dict(child_bundle.metadata), "authority": child_bundle.authority,
                "success": child_bundle.success, "uncertainty": child_bundle.uncertainty,
            })
            if child_bundle.uncertainty:
                inherited_uncertainty.append(child_bundle.uncertainty)
            for item in child_bundle.evidence:
                if item.kind == kind:
                    serialized = {
                        "content_excerpt": item.claim, "title": item.source_name,
                        "url": item.source_url, "source_id": item.source_id,
                        "source_quality": item.source_quality,
                        "authority_tier": item.authority_tier,
                        "quality_eligible": item.quality_eligible, **dict(item.data),
                    }
                    normalized_sources.append((serialized, item))
                elif item.kind == EvidenceKind.UNCERTAINTY:
                    inherited_items.append(item)
        metadata["packet_constraints"] = packet_constraints
    items = list(inherited_items)
    for source, normalized in [(source, None) for source in sources] + normalized_sources:
        identity = _identity(source)
        matching = indexes.get(identity, [])
        veto = exclusions.get(identity)
        for record in matching:
            veto = veto or _source_veto(record)
        merged_index = {}
        for record in matching:
            merged_index.update(record)
        if any(record.get("quality_eligible") is False for record in matching):
            merged_index["quality_eligible"] = False
        items.append(_research_source(source, kind, veto=veto, index=merged_index, normalized=normalized))
    # Metadata-only sources are diagnostic and have no factual claim.
    source_identities = {_identity(source) for source in sources}
    source_identities.update(_identity(source) for source, _ in normalized_sources)
    for source in index_records:
        if _identity(source) not in source_identities:
            provenance_only = {key: value for key, value in source.items()
                               if key not in {"content_excerpt", "read_result"}}
            items.append(_research_source(provenance_only, kind))
    for source, reason in diagnostic_records:
        items.append(_research_source(source, kind, veto=reason))
    uncertainty = _text(payload.get("uncertainty")) or None
    uncertainty = "; ".join(dict.fromkeys(
        ([uncertainty] if uncertainty else []) + inherited_uncertainty
    )) or None
    if payload.get("success") is False:
        uncertainty = uncertainty or "Research did not establish sufficient evidence"
    if not any(item.is_authoritative_fact for item in items):
        uncertainty = uncertainty or "No admissible source content is available"
    if uncertainty:
        items.append(_uncertainty(uncertainty))
    bundle = _bundle("public_web" if kind == EvidenceKind.PUBLIC_SOURCE else "media_research", items,
                     uncertainty=uncertainty, metadata=metadata)
    if payload.get("success") is False:
        bundle = replace(bundle, success=False).snapshot()
    return bundle


def _user_item(text: str, kind: EvidenceKind, *, identity=None, supersedes=(), data=None, current=False) -> Evidence:
    provenance = "current_user_turn" if current or kind == EvidenceKind.CURRENT_USER_TURN else "live_user_authored"
    if kind == EvidenceKind.SUPPLIED_PREMISE:
        provenance = "user_supplied_premise"
    return Evidence(
        claim=text, provenance=provenance, confidence="user_authored",
        kind=kind, status=EvidenceStatus.ADMISSIBLE if text else EvidenceStatus.UNAVAILABLE,
        evidence_id=identity or _id(kind, text, provenance), supersedes=supersedes,
        data=dict(data or {}), authority_scope=(
            "conditional_premise" if kind == EvidenceKind.SUPPLIED_PREMISE else "what_the_user_stated"
        ),
    )


def normalize_user_turn(value: Any, *, premise=False, supersedes=()) -> EvidenceBundle:
    """Current authored text; correction/premise status comes from Core, not regex."""
    if isinstance(value, str):
        text, intent, identity = value.strip(), "", None
    else:
        record = value if isinstance(value, Mapping) else vars(value)
        if record.get("role", "user") != "user":
            raise ValueError("Current user ingress must be user authored")
        text, intent = _text(record.get("raw_text")), record.get("intent")
        identity = _text(record.get("evidence_id")) or None
    kind = (EvidenceKind.SUPPLIED_PREMISE if premise else EvidenceKind.USER_CORRECTION
            if intent == "self_correction" else EvidenceKind.CURRENT_USER_TURN)
    if supersedes and kind != EvidenceKind.USER_CORRECTION:
        raise ValueError("Only an explicit Core-classified correction can supersede evidence")
    item = _user_item(text, kind, identity=identity, supersedes=supersedes, current=True)
    return _bundle("user_context", [item], uncertainty=None if text else "Current user text is unavailable")


def normalize_live_conversation(messages: Iterable[Any]) -> EvidenceBundle:
    """Only role-labelled USER messages supply live user-authored evidence."""
    items = []
    for message in messages:
        record = message if isinstance(message, Mapping) else vars(message)
        content = _text(record.get("content"))
        if record.get("role") == "user":
            kind = EvidenceKind.USER_CORRECTION if record.get("intent") == "self_correction" else EvidenceKind.LIVE_USER_FACT
            items.append(_user_item(content, kind, identity=_text(record.get("evidence_id")) or None,
                                    supersedes=record.get("supersedes", ()) if kind == EvidenceKind.USER_CORRECTION else ()))
        else:
            items.append(Evidence(
                claim=content, provenance="non_user_conversation", confidence="non_authoritative",
                kind=EvidenceKind.UNKNOWN, status=EvidenceStatus.REJECTED,
                limitations=("Prior assistant, system, tool, or roleless text is not user-authored evidence",),
                data={"role": record.get("role")},
            ))
    return _bundle("user_context", items)


def normalize_user_history(records: Iterable[Mapping]) -> EvidenceBundle:
    """Explicit adapter for Core-owned ConversationState.recent_user_turns."""
    messages = []
    for record in records:
        if not isinstance(record, Mapping) or record.get("role", "user") != "user":
            raise ValueError("Core user history must contain user records only")
        messages.append({**record, "role": "user", "content": record.get("text")})
    return normalize_live_conversation(messages)


def normalize_live_user_context(turn: Any) -> EvidenceBundle:
    """Use original structured continuity state, never ambiguous rendered prose."""
    record = turn if isinstance(turn, Mapping) else vars(turn)
    entities = _mapping(record.get("entities"))
    text = _text(entities.get("_conversation_context_user_text"))
    bundle = normalize_user_history([{
        "text": text, "intent": entities.get("_conversation_context_intent"),
    }])
    return replace(bundle, metadata={"resolved_referents": record.get("resolved_referents", {})}).snapshot()


def normalize_core_evidence(value: Any, *, kind: Optional[EvidenceKind] = None) -> EvidenceBundle:
    """Adapt a trusted Core bundle or its serialization; unknown provenance stays unassessed.

Legacy arithmetic is deterministically recognized. Other legacy producers must
provide an explicit Core domain instead of deriving authority from confidence.
"""
    record = value.to_dict() if isinstance(value, EvidenceBundle) else _mapping(value)
    if "authority" not in record or "evidence" not in record:
        raise ValueError("Core evidence ingress requires an EvidenceBundle shape")
    items = []
    for entry in _records(record.get("evidence")):
        item_kind = EvidenceKind(entry.get("kind", kind or EvidenceKind.UNKNOWN))
        provenance = _text(entry.get("provenance"))
        if item_kind == EvidenceKind.UNKNOWN and provenance == "core_arithmetic":
            item_kind = EvidenceKind.CORE_RESULT
        if item_kind == EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION and record.get("canonical") is not True:
            raise ValueError("Grant model knowledge through the explicit contract adapter")
        if "status" in entry:
            status = EvidenceStatus(entry["status"])
        else:
            status = (EvidenceStatus.ADMISSIBLE if item_kind != EvidenceKind.UNKNOWN
                      and entry.get("confidence") == "verified" else EvidenceStatus.UNASSESSED)
        data = dict(_mapping(entry.get("data")))
        if item_kind in {EvidenceKind.PUBLIC_SOURCE, EvidenceKind.MEDIA_SOURCE}:
            if _source_veto({**data, **entry}):
                status = EvidenceStatus.REJECTED
        claim = _text(entry.get("claim"))
        items.append(Evidence(
            claim=claim, provenance=provenance, confidence=_text(entry.get("confidence")),
            source_name=entry.get("source_name"), source_id=entry.get("source_id"),
            observed_at=entry.get("observed_at"), data=data, kind=item_kind, status=status,
            source_url=entry.get("source_url"), source_quality=entry.get("source_quality"),
            authority_tier=entry.get("authority_tier"), quality_eligible=entry.get("quality_eligible"),
            evidence_id=entry.get("evidence_id") or _id(item_kind, claim, provenance, _text(entry.get("source_url"))),
            supersedes=entry.get("supersedes", ()), limitations=entry.get("limitations", ()),
            authority_scope=entry.get("authority_scope") or "core_result",
        ))
    bundle = EvidenceBundle(
        authority=record["authority"], evidence=items, success=record.get("success") is True,
        uncertainty=record.get("uncertainty"), canonical=True,
        metadata=dict(_mapping(record.get("metadata"))),
    )
    return bundle.snapshot()


def normalize_stable_model_authority(contract: AnswerContractRuntime) -> EvidenceBundle:
    """A Core permission to use stable semantics, never a verified factual claim."""
    if not isinstance(contract, AnswerContractRuntime):
        raise TypeError("Model knowledge requires a structured Core runtime contract")
    permitted = (contract.epistemic_mode in {"stable_model_knowledge", "user_context_reasoning"}
                 and contract.allow_new_factual_claims is True)
    item = Evidence(
        claim="", provenance="core_answer_contract", confidence="permission_only",
        kind=EvidenceKind.STABLE_MODEL_KNOWLEDGE_PERMISSION,
        status=EvidenceStatus.ADMISSIBLE if permitted else EvidenceStatus.REJECTED,
        authority_scope="stable_explanation_within_supplied_premises",
        data={"task": contract.task, "intent": contract.intent, "authority": contract.authority,
              "epistemic_mode": contract.epistemic_mode, "subject": contract.subject},
        limitations=() if permitted else ("Stable model knowledge is not permitted by this contract",),
    )
    return _bundle(contract.authority, [item])


def combine_evidence(*bundles: EvidenceBundle, authority: str) -> EvidenceBundle:
    """Carry all canonical domains without collapsing their authority scopes."""
    if not all(isinstance(bundle, EvidenceBundle) and bundle.canonical for bundle in bundles):
        raise ValueError("Combine only normalized canonical bundles")
    uncertainty = "; ".join(dict.fromkeys(bundle.uncertainty for bundle in bundles if bundle.uncertainty)) or None
    return _bundle(authority, [item for bundle in bundles for item in bundle.evidence],
                   uncertainty=uncertainty,
                   metadata={"bundles": [{"authority": bundle.authority, **dict(bundle.metadata)} for bundle in bundles]})
