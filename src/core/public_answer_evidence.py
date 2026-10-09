"""Canonical transport of a selected public draft's real research state.

The adapter does not admit candidate prose or infer source authority from it.
Packet excerpts are factual payload; discovery, page reads and Core admission
remain separate lifecycle facts. All retained inputs are detached snapshots.
"""
from collections.abc import Mapping
from dataclasses import replace
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from core.answer_candidate import AnswerCandidate, CandidateOrigin
from core.answer_contract_runtime import coerce_answer_contract_runtime
from core.evidence import Evidence, EvidenceBundle, EvidenceKind, EvidenceStatus
from core.evidence_normalization import _packet


def normalize_source_url(value):
    """Normalize syntax, not source equivalence or guessed redirects.

    Paths, queries and fragments remain significant. Only protocol/host case,
    default ports and an empty HTTP root path are normalized.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if any(character.isspace() for character in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        port = parsed.port
        if port is not None and (scheme, port) not in {("http", 80), ("https", 443)}:
            host += ":" + str(port)
        return urlunsplit((scheme, host, parsed.path or "/", parsed.query, parsed.fragment))
    except (ValueError, TypeError):
        return None


def public_packet_digest(value):
    if isinstance(value, str):
        rendered = value
    elif isinstance(value, Mapping):
        rendered = json.dumps(dict(value), ensure_ascii=False, sort_keys=True)
    else:
        raise TypeError("Public evidence packet must be a mapping or string")
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _records(value):
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, Mapping) for item in value):
        raise TypeError("Public research records must be mappings")
    return tuple(value)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _true(value):
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _read_url(source):
    read = source.get("read_result")
    return _text(read.get("url")) if isinstance(read, Mapping) else ""


def _identities(source):
    values = (source.get("url"), _read_url(source))
    return {normalized for value in values if (normalized := normalize_source_url(value))}


def _veto(source):
    return source.get("accepted_as_evidence") is False or source.get("relevance_status") == "rejected"


def _excerpt_matches_read(excerpt, raw_content):
    """Check the existing packet builder's whitespace/prefix transformation."""
    if not isinstance(raw_content, str):
        return False
    readable = re.sub(r"[ \t]+", " ", raw_content.strip())
    readable = re.sub(r"\n{3,}", "\n\n", readable).strip()
    marker = "\n[Core excerpt truncated.]"
    if excerpt.endswith(marker):
        prefix = excerpt[:-len(marker)]
        return bool(prefix) and len(readable) > len(prefix) and readable.startswith(prefix)
    return excerpt == readable


def _requirements(result, packet, user_input):
    result = dict(result)
    values = {
        "official_source_required": _true(result.get("official_documentation_required")),
        "freshness_required": _true(result.get("freshness_sensitive")) or _true(packet.get("freshness_required")),
        # The existing verifier checks scope in its prompt, but exposes no
        # source-to-sentence binding or separate precise scope verdict.
        "scope_support": "verifier_only",
        "currentness_support": "unestablished",
    }
    for key in ("original_query", "query", "search_query", "research_identity", "time_range",
                "query_resolution_required", "strict_relevance", "quality_evidence_required",
                "forecast_requested", "required_source_scope", "required_current_as_of",
                "currentness_established", "source_scope_established", "unresolved_query_constraints"):
        if key in result:
            values[key] = result[key]
    for key in ("research_query", "freshness_window", "answer_scope", "required_source_scope",
                "required_current_as_of"):
        if key in packet:
            values.setdefault(key, packet[key])
    from core.public_source_requirements import public_source_requirements
    current = public_source_requirements(user_input)
    values["current_user_requirements"] = dict(current)
    for key in ("official_source_required", "primary_source_required", "source_read_required", "exact_source_required"):
        values[key] = _true(values.get(key)) or _true(current.get(key))
    values["requested_source_urls"] = tuple(current.get("requested_source_urls", ()))
    return values


def _binding_failure(issues, status):
    values = tuple(issue for issue in issues if isinstance(issue, str)) if isinstance(issues, (list, tuple)) else ()
    mapping = (
        ({"binding_transport", "binding_infrastructure"}, "evaluation_failed"),
        ({"binding_timeout_capability"}, "transport_unavailable"),
        ({"binding_input_limit"}, "input_limit"),
        ({"annotation_binding", "binding_inputs"}, "wrong_inputs"),
        ({"inadmissible_source_id"}, "unread_source"),
        ({"unknown_source_id", "unsupported_witness", "annotation_source_ids", "annotation_witness",
          "annotation_witnesses", "binding_source_ids", "binding_factual_sources", "binding_witnesses",
          "binding_witness", "binding_literal_witness", "binding_factual_witness", "binding_packet_identity"}, "invalid_binding"),
        ({"binding_output", "binding_record", "binding_index", "binding_semantics", "binding_packet_sources",
          "binding_packet_source", "annotation_type", "annotation_records", "annotation_record", "annotation_index",
          "annotation_semantics", "annotation_status"}, "invalid_output"),
        ({"annotation_incomplete", "binding_incomplete"}, "incomplete_output"),
    )
    for recognized, failure in mapping:
        if any(issue in recognized for issue in values):
            return failure
    return "invalid_output" if status == "malformed" else ("incomplete_output" if status == "incomplete" else None)


def _binding_failure_details(issues, *, domain):
    from core.public_source_bindings import binding_failure_metadata
    details = binding_failure_metadata(issues)
    canonical_codes = {
        "annotation_binding": "wrong_inputs", "annotation_type": "invalid_annotation_shape",
        "annotation_records": "invalid_annotation_shape", "annotation_record": "invalid_annotation_shape",
        "annotation_index": "invalid_annotation_index", "annotation_semantics": "invalid_annotation_semantics",
        "annotation_source_ids": "invalid_source_id", "unknown_source_id": "invalid_source_id",
        "inadmissible_source_id": "unread_source", "annotation_witnesses": "invalid_witness_shape",
        "annotation_witness": "invalid_witness_shape", "unsupported_witness": "invalid_literal_witness",
        "annotation_incomplete": "incomplete_annotations", "annotation_status": "invalid_annotation_shape",
    }
    code = next((canonical_codes[issue] for issue in issues if isinstance(issue, str) and issue in canonical_codes),
                details["failure_code"])
    return {"failure_domain": domain, "failure_code": code}


def _normalized_bindings(value, items, verification, packet_digest, user_input):
    """Bind shadow annotations to actual admitted Core source identities.

    An annotation cannot add source authority or fabricate a read. Literal
    witnesses must occur in the retained packet excerpt, not candidate prose.
    """
    if value is None:
        return {"version": 1, "status": "unavailable", "sentences": (), "issues": (), "failure": "missing_annotations",
                "failure_domain": "annotation_capability", "failure_code": "missing_annotations"}
    if not isinstance(value, Mapping):
        return {"version": 1, "status": "malformed", "sentences": (), "issues": ("annotation_type",), "failure": "invalid_output",
                "failure_domain": "integrity", "failure_code": "invalid_annotation_shape"}
    question_digest = value.get("assessed_question_digest")
    wrong_question = ((question_digest is not None or value.get("validator") == "public_source_bindings_v1")
                      and question_digest != hashlib.sha256(str(user_input or "").encode("utf-8")).hexdigest())
    if (wrong_question or type(value.get("version")) is not int or value.get("version") != 1
            or value.get("assessed_draft_digest") != verification.get("assessed_draft_digest")
            or value.get("packet_digest") != packet_digest):
        return {"version": 1, "status": "malformed", "sentences": (), "issues": ("annotation_binding",),
                "failure": "wrong_inputs", "assessed_question_digest": question_digest,
                "failure_domain": "integrity", "failure_code": "wrong_inputs"}
    producer_issues = value.get("issues", ())
    producer_issues = producer_issues if isinstance(producer_issues, (list, tuple)) else ()
    from core.public_source_bindings import binding_failure_metadata
    producer_details = binding_failure_metadata(producer_issues)
    if producer_details["failure_domain"] == "integrity":
        return {"version": 1, "status": "malformed", "sentences": (),
                "issues": tuple(issue for issue in producer_issues if isinstance(issue, str)
                                and binding_failure_metadata((issue,))["failure_code"] is not None),
                "failure": _binding_failure(producer_issues, "malformed"),
                "assessed_question_digest": question_digest,
                "assessed_draft_digest": value.get("assessed_draft_digest"), "packet_digest": value.get("packet_digest"),
                **producer_details}
    # The collector has already rejected unusable model annotations. Its Core
    # envelope is bound to these exact inputs, and no partial annotation can
    # acquire authority. Do not relabel that capability gap as an inconsistent
    # legacy verifier or an invalid canonical evidence graph.
    if (value.get("validator") == "public_source_bindings_v1"
            and value.get("status") in {"malformed", "incomplete", "unavailable"}
            and value.get("failure_domain") == "annotation_capability"
            and producer_details["failure_domain"] == "annotation_capability"
            and value.get("failure_code") == producer_details["failure_code"]):
        return {"version": 1, "status": value["status"], "sentences": (),
                "issues": tuple(issue for issue in producer_issues if isinstance(issue, str)
                                and binding_failure_metadata((issue,))["failure_code"] is not None),
                "failure": _binding_failure(producer_issues, value["status"]),
                "assessed_question_digest": question_digest,
                "assessed_draft_digest": value.get("assessed_draft_digest"), "packet_digest": value.get("packet_digest"),
                **producer_details}
    if value.get("status") == "unavailable" and not value.get("sentences"):
        failure = _binding_failure(value.get("issues", ()), "unavailable")
        if failure is None and value.get("failure") in {"transport_unavailable", "evaluation_failed", "input_limit", "missing_annotations"}:
            failure = value["failure"]
        return {"version": 1, "status": "unavailable", "sentences": (), "issues": (), "failure": failure,
                "assessed_question_digest": question_digest,
                **_binding_failure_details(producer_issues, domain="annotation_capability")}
    issues = []
    records = value.get("sentences")
    if not isinstance(records, (list, tuple)):
        records = ()
        issues.append("annotation_records")
    source_lookup = {item.source_id: item for item in items if item.source_id and item.data.get("admitted_in_packet")}
    expected = len(verification.get("assessed_sentences", ()))
    normalized, indexes = [], set()
    for record in records:
        if not isinstance(record, Mapping):
            issues.append("annotation_record")
            continue
        index = record.get("index")
        if type(index) is not int or index < 1 or index > expected or index in indexes:
            issues.append("annotation_index")
            continue
        indexes.add(index)
        kind = record.get("claim_kind")
        provenance = record.get("provenance_claim")
        scope = record.get("scope_status")
        if (not isinstance(kind, str) or kind not in {"factual", "limitation", "non_factual"}
                or not isinstance(provenance, str) or provenance not in {"none", "read", "source_assertion", "citation"}
                or not isinstance(scope, str) or scope not in {"supported", "unsupported", "uncertain", "not_applicable"}):
            issues.append("annotation_semantics")
        source_ids = record.get("source_ids")
        if (not isinstance(source_ids, (list, tuple)) or any(not isinstance(identity, str) or not identity for identity in source_ids)
                or len(set(source_ids)) != len(source_ids)):
            source_ids = ()
            issues.append("annotation_source_ids")
        evidence_ids = []
        for identity in source_ids:
            source = source_lookup.get(identity)
            if source is None:
                issues.append("unknown_source_id")
            elif (source.status != EvidenceStatus.ADMISSIBLE or source.data.get("read_success") is not True
                  or source.data.get("accepted_as_evidence") is not True or source.data.get("excerpt_matches_read") is not True):
                issues.append("inadmissible_source_id")
            elif source.evidence_id:
                evidence_ids.append(source.evidence_id)
        witnesses = record.get("witnesses")
        valid_witnesses = []
        if not isinstance(witnesses, (list, tuple)):
            witnesses = ()
            issues.append("annotation_witnesses")
        for witness in witnesses:
            if not isinstance(witness, Mapping):
                issues.append("annotation_witness")
                continue
            identity, quote = witness.get("source_id"), witness.get("quote")
            source = source_lookup.get(identity) if isinstance(identity, str) else None
            if (identity not in source_ids or source is None or not isinstance(quote, str) or not quote.strip()
                    or re.sub(r"\s+", " ", quote.strip()) not in re.sub(r"\s+", " ", source.claim.strip())):
                issues.append("unsupported_witness")
            else:
                valid_witnesses.append({"source_id": identity, "quote": quote})
        normalized.append({"index": index, "claim_kind": kind, "provenance_claim": provenance,
                           "scope_status": scope, "source_ids": tuple(source_ids),
                           "evidence_ids": tuple(evidence_ids), "witnesses": tuple(valid_witnesses)})
    if indexes != set(range(1, expected + 1)) or expected == 0:
        issues.append("annotation_incomplete")
    status = value.get("status")
    if status not in {"complete", "incomplete", "malformed", "unavailable"}:
        issues.append("annotation_status")
    if issues:
        status = "malformed" if status == "malformed" or any(issue != "annotation_incomplete" for issue in issues) else "incomplete"
    failure = _binding_failure(tuple(value.get("issues", ())) + tuple(issues), status) if isinstance(value.get("issues", ()), (list, tuple)) else _binding_failure(issues, status)
    return {"version": 1, "status": status, "sentences": tuple(normalized),
            "issues": tuple(dict.fromkeys(issues)),
            "failure": failure,
            "assessed_question_digest": question_digest,
            "assessed_draft_digest": value.get("assessed_draft_digest"), "packet_digest": value.get("packet_digest"),
            **(_binding_failure_details(tuple(producer_issues) + tuple(issues), domain="integrity")
               if status != "complete" else {"failure_domain": None, "failure_code": None})}


def normalize_public_answer_evidence(research_result, evidence_packet, verification_result,
                                     *, source_bindings=None, user_input=""):
    """Snapshot packet authority and lifecycle state without broadening it.

    A successful read outside the supplied packet is retained diagnostically
    but cannot support this answer. A search snippet never becomes page content.
    """
    if not isinstance(research_result, Mapping):
        raise TypeError("Public research state must be a mapping")
    packet = _packet(evidence_packet)
    packet_sources = _records(packet.get("sources"))
    attempted = _records(research_result.get("sources"))
    discovered = _records(research_result.get("discovered_sources"))
    rejected = _records(research_result.get("rejected_sources"))
    rejected_urls = {url for record in rejected for url in _identities(record)}
    discovered_urls = {url for record in discovered for url in _identities(record)}
    items = []
    represented = set()

    def item_for(source, packet_source=None, *, discovered_only=False, rejected_only=False):
        packet_source = packet_source or {}
        source = dict(source)
        read = source.get("read_result")
        read_mapping = read if isinstance(read, Mapping) else {}
        read_attempted = not discovered_only and not rejected_only and "read_result" in source
        read_success = (source.get("read_success") is True and read_mapping.get("success") is True
                        and bool(_text(read_mapping.get("content"))))
        url = _text(packet_source.get("url")) or _text(source.get("url"))
        aliases = _identities(source)
        content = _text(packet_source.get("content_excerpt"))
        admitted = bool(packet_source) and bool(content)
        excerpt_matches_read = bool(content) and _excerpt_matches_read(content, read_mapping.get("content"))
        rejected_here = rejected_only or _veto(source) or bool(aliases & rejected_urls)
        packet_veto = _veto(packet_source) or packet_source.get("read_success") is False
        if rejected_here or packet_veto:
            status = EvidenceStatus.REJECTED
        elif admitted and read_success and not excerpt_matches_read:
            status = EvidenceStatus.REJECTED
        elif read_success and admitted and source.get("accepted_as_evidence") is True:
            status = EvidenceStatus.ADMISSIBLE
        else:
            status = EvidenceStatus.UNAVAILABLE
        data = {
            "discovered": bool(aliases & discovered_urls) or read_attempted,
            "read_attempted": read_attempted,
            "read_success": read_success,
            "read_status": "succeeded" if read_success else ("unavailable" if read_attempted else "not_attempted"),
            "admitted_in_packet": admitted,
            "excerpt_matches_read": excerpt_matches_read,
            "accepted_as_evidence": source.get("accepted_as_evidence"),
            "packet_url": _text(packet_source.get("url")) or None,
            "read_url": _read_url(source) or None,
            "requested_url": _text(source.get("url")) or None,
        }
        # Retain only real structured metadata, never source-body instructions.
        for key in ("source_host", "published_date", "source_quality", "authority_tier",
                    "quality_eligible", "authority_reason", "authority_anchor_matches",
                    "relevance_status", "relevance_reasons", "identity_anchors",
                    "matched_identity_anchors", "unresolved_query_constraints", "stage",
                    "source_scope", "current_as_of", "currentness_established"):
            if key in source:
                data[key] = source[key]
            elif key in packet_source:
                data[key] = packet_source[key]
        # A snippet is explicitly diagnostic, not a factual claim payload.
        snippet = source.get("snippet", packet_source.get("search_snippet"))
        if snippet is not None:
            data["search_snippet"] = snippet
        quality_eligible = source.get("quality_eligible", packet_source.get("quality_eligible"))
        if type(quality_eligible) is not bool:
            quality_eligible = None
        source_id = _text(packet_source.get("source_id")) or _text(source.get("source_id")) or None
        identity = json.dumps([url, source_id, content, status.value, len(items)], ensure_ascii=False)
        limitations = () if status == EvidenceStatus.ADMISSIBLE else ("No admitted loaded page authority",)
        return Evidence(
            claim=content, provenance="core_public_source", confidence="source_assertion",
            kind=EvidenceKind.PUBLIC_SOURCE, status=status,
            source_name=_text(packet_source.get("title")) or _text(source.get("title")) or None,
            source_id=source_id, source_url=url or None,
            source_quality=_text(source.get("source_quality", packet_source.get("source_quality"))) or None,
            authority_tier=_text(source.get("authority_tier", packet_source.get("authority_tier"))) or None,
            quality_eligible=quality_eligible, data=data, limitations=limitations,
            evidence_id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            authority_scope="retrieved_source_assertions",
        )

    for packet_source in packet_sources:
        packet_identity = normalize_source_url(packet_source.get("url"))
        matching = [source for source in attempted if packet_identity and packet_identity in _identities(source)]
        # Multiple attempted records sharing one identity cannot hide a veto.
        if matching:
            chosen = next((source for source in matching if _veto(source)), matching[0])
            represented.update(id(source) for source in matching)
        else:
            chosen = {"url": packet_source.get("url")}
        items.append(item_for(chosen, packet_source))
    for source in attempted:
        if id(source) not in represented:
            items.append(item_for(source))
    attempted_urls = {url for source in attempted for url in _identities(source)}
    for source in discovered:
        if not (_identities(source) & attempted_urls):
            items.append(item_for(source, discovered_only=True))
    for source in rejected:
        if not (_identities(source) & attempted_urls):
            items.append(item_for(source, rejected_only=True))
    verification = getattr(verification_result, "verification_state", None)
    verification = dict(verification) if isinstance(verification, Mapping) else {}
    digest = public_packet_digest(evidence_packet)
    bindings = _normalized_bindings(source_bindings, items, verification, digest, user_input)
    requirements = _requirements(research_result, packet, user_input)
    if bindings["status"] == "complete" and bindings["sentences"]:
        requirements["scope_support"] = ("bound_verifier" if all(
            entry["scope_status"] in {"supported", "not_applicable"} for entry in bindings["sentences"]
        ) else "unresolved")
    metadata = {
        "public_verification": verification,
        "public_packet_digest": digest,
        "public_requirements": requirements,
        "public_source_bindings": bindings,
        "public_transport_version": 1,
        "public_source_ids_valid": (
            bool(packet_sources)
            and all(_text(record.get("source_id")) and normalize_source_url(record.get("url"))
                    for record in packet_sources)
            and len({_text(record.get("source_id")) for record in packet_sources}) == len(packet_sources)
        ),
        "verifier_source_bindings": "available" if bindings["status"] == "complete" else "unavailable",
    }
    return EvidenceBundle(
        authority="public_web", evidence=items, canonical=True,
        success=any(item.status == EvidenceStatus.ADMISSIBLE and item.claim for item in items),
        metadata=metadata,
    ).snapshot()


def build_public_answer_candidate(*, text, contract, research_result, evidence_packet,
                                  verification_result, origin=CandidateOrigin.GENERATED,
                                  source_bindings=None, user_input=""):
    runtime = coerce_answer_contract_runtime(contract)
    if runtime is None:
        raise TypeError("A public candidate requires a Core answer contract")
    bundle = normalize_public_answer_evidence(research_result, evidence_packet, verification_result,
                                               source_bindings=source_bindings, user_input=user_input)
    requirements = bundle.metadata["public_requirements"]
    metadata = dict(runtime.metadata)
    for field in ("official_source_required", "primary_source_required", "freshness_required", "source_read_required", "exact_source_required"):
        metadata[field] = _true(metadata.get(field)) or requirements[field]
    if requirements["requested_source_urls"]:
        metadata["requested_source_urls"] = requirements["requested_source_urls"]
    runtime = replace(runtime, metadata=metadata)
    return AnswerCandidate(text=text, origin=origin, contract=runtime, evidence=bundle)
