"""Bounded typed observation of selected public factual generation.

Existing sentence/global verifiers supply semantic support. This component
checks exact-wording binding and the provenance/contract envelope around those
results; it never substitutes model memory or performs publication.
"""
from collections.abc import Mapping
import hashlib
import re

from core.acceptance_typed import TypedEvaluation, TypedUnitValidation
from core.acceptance_semantics import UnitKind, interpret_text
from core.evidence import EvidenceKind, EvidenceStatus
from core.public_answer_evidence import normalize_source_url


PUBLIC_VERIFIER_CONSISTENCY = "public_verifier_consistency"
PUBLIC_SENTENCE_SUPPORT = "public_sentence_support"
PUBLIC_GLOBAL_SUPPORT = "public_global_support"
SOURCE_IDENTITY = "source_identity"
SOURCE_READ_PROVENANCE = "source_read_provenance"
OFFICIAL_SOURCE_SUPPORT = "official_source_support"
INSUFFICIENT_SCOPE_SUPPORT = "insufficient_scope_support"
INSUFFICIENT_CURRENTNESS_SUPPORT = "insufficient_currentness_support"
PUBLIC_INVARIANTS = frozenset({
    PUBLIC_VERIFIER_CONSISTENCY, PUBLIC_SENTENCE_SUPPORT, PUBLIC_GLOBAL_SUPPORT,
    SOURCE_IDENTITY, SOURCE_READ_PROVENANCE, OFFICIAL_SOURCE_SUPPORT,
    INSUFFICIENT_SCOPE_SUPPORT, INSUFFICIENT_CURRENTNESS_SUPPORT,
})
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.I)


def _true(value):
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _normal(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _loaded(item):
    return (item.kind == EvidenceKind.PUBLIC_SOURCE
            and item.status == EvidenceStatus.ADMISSIBLE
            and item.provenance == "core_public_source"
            and item.authority_scope == "retrieved_source_assertions"
            and bool(item.claim.strip()) and bool(normalize_source_url(item.source_url))
            and item.data.get("read_attempted") is True
            and item.data.get("read_success") is True
            and item.data.get("admitted_in_packet") is True
            and item.data.get("excerpt_matches_read") is True
            and item.data.get("accepted_as_evidence") is True
            and item.data.get("relevance_status") != "rejected")


def _urls(text):
    for match in _URL.finditer(text):
        value = match.group().rstrip(".,;:!?")
        # A closing parenthesis in Markdown/prose is punctuation only when
        # there is no corresponding opening parenthesis within the URL.
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        yield normalize_source_url(value)


def _assessment_map(value, count):
    if not isinstance(value, (tuple, list)):
        return None
    values = {}
    for item in value:
        if not isinstance(item, Mapping):
            return None
        index = item.get("index")
        supported = item.get("supported")
        if (type(index) is not int or index < 1 or index > count or index in values
                or type(supported) is not bool):
            return None
        values[index] = supported
    return values if set(values) == set(range(1, count + 1)) else None


def _scope_issue(candidate, sources, requirements):
    required = candidate.contract.metadata.get("required_source_scope") or requirements.get("required_source_scope")
    if required is not None:
        if not isinstance(required, (str, Mapping)) or not required:
            return True
        # A declared source scope is a bound, not a model-inferred ontology.
        if not sources or any(source.data.get("source_scope") != required for source in sources):
            return True
    if requirements.get("unresolved_query_constraints"):
        return True
    return any(source.data.get("unresolved_query_constraints") for source in sources)


def _currentness_issue(candidate, sources, requirements):
    required = _true(candidate.contract.metadata.get("freshness_required")) or _true(requirements.get("freshness_required"))
    if not required:
        return False
    expected = candidate.contract.metadata.get("required_current_as_of") or requirements.get("required_current_as_of")
    # Publication/search dates alone do not establish contemporary correctness.
    # Only explicit trusted state can support this obligation; current B37
    # generally retains no such field, so shadow diagnostics expose that gap.
    if expected:
        return not sources or any(source.data.get("current_as_of") != expected for source in sources)
    return not sources or any(source.data.get("currentness_established") is not True for source in sources)


def _source_attribution_issue(text, sources):
    """Detect bounded explicit load/attribution claims, not arbitrary entailment.

    URLs are always checked separately. A named-source claim must carry a
    retained title/ID/identity; unlabeled 'the source' remains the verifier's
    semantic task. This intentionally does not create product/topic rules.
    """
    identities = tuple(_normal(value).casefold() for source in sources
                       for value in (source.source_name, source.source_id, source.source_url,
                                     source.data.get("read_url")) if value)
    generic = {"source", "page", "documentation", "evidence", "public source", "public page",
               "sources", "pages", "official documentation", "official source", "it", "that", "this"}
    names = []
    for match in re.finditer(
        r"\b(?:i|we)\s+(?:(?:did|have)\s+)?(?:actually\s+)?"
        r"(?:read|loaded|retrieved|consulted|checked|inspected|reviewed)\s+"
        r"(?:the\s+)?(?P<name>[^.!?\n]+)", text, re.I,
    ):
        names.append(match.group("name"))
    for claim in _retrieval_claims(text):
        tail = _normal(text)[claim.end():]
        match = re.match(r"\s+from\s+(?:the\s+)?([^;\n\u2014\u2013]+)", tail, re.I)
        if match:
            location = match.group(1).rstrip(".!?")
            if location.lower() not in {"site", "live site", "page", "source", "website", "public page", "public site"}:
                names.append(location)
    # Bounded named-source attribution shapes. A verifier may assess the
    # substantive assertion positively while overlooking a substituted title.
    # The authority of that name still comes from retained source identity.
    for match in re.finditer(
        r"(?:^|[.!?]\s+)(?:the\s+)?(?P<name>[A-Za-z][^.!?\n:]{0,120}?)\s+"
        r"(?:says|states|reports|documents|confirms|indicates)\b", text, re.I,
    ):
        names.append(match.group("name"))
    for match in re.finditer(
        r"\baccording\s+to\s+(?:the\s+)?(?P<name>[^,;.!?\n]+)", text, re.I,
    ):
        names.append(match.group("name"))
    for retained in names:
        name = _normal(retained).casefold().rstrip(".,")
        if any(_urls(retained)):
            continue
        if name in generic:
            continue
        if not any(identity and (name == identity or name.startswith(identity + " ")) for identity in identities):
            return True
    return False


def _confidence_topic(value):
    value = value.strip()
    if len(value) > 180 or any(character.isnumeric() for character in value):
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    quoted = re.fullmatch(r"(?:a|an|the)\s+(['\"])(.+)\1", value, re.I)
    if quoted:
        value = quoted.group(2).strip()
    # Only a simple nominal label qualifies. Commas, detached dashes and
    # markup can introduce unparsed factual tails; do not ignore those tails.
    if (any(not (character.isalnum() or character in " -'") for character in value)
            or re.search(r"(?<!\w)-|-(?!\w)", value)):
        return False
    return bool(value) and any(character.isalpha() for character in value) and not re.search(
        r"[;:!?`{}\[\]\n\r]|\.(?:\s|$)|"
        r"\b(?:is|are|was|were|has|have|had|does|did|can|could|will|would|must|should|may|might|"
        r"contains|equals|means|causes|weighs|costs|proves|shows|says|and|but|because|so|therefore|"
        r"although|while|if|unless|until|which|who|whose|where|when|whether|that|it|you|we|they|he|she)\b", value, re.I,
    )


def _confidence_subject(value):
    """Validate nominal topic/context separately, consuming every character.

    A term/word wrapper and a domain qualifier describe the extent of the
    speaker's knowledge. Neither may contain an embedded factual proposition.
    Quotation is syntax only, not authority for its contents.
    """
    value = value.strip()
    if len(value) > 180:
        return False
    value = re.sub(r"^(?:(?:a|an|the)\s+)?(?:term|word|phrase|concept|name|expression|label)\s+",
                   "", value, flags=re.I)
    value = re.sub(r"^(?:a|an|the)\s+(?=['\"])", "", value, flags=re.I)
    if value.startswith(("'", '"')):
        match = re.fullmatch(r"(['\"])(.*?)\1(.*)", value)
        if not match or not _confidence_topic(match.group(2)):
            return False
        tail = match.group(3)
        if not tail:
            return True
        qualifier = re.fullmatch(r"\s+in\s+(?:the\s+context\s+of\s+)?(.+)", tail, re.I)
        return bool(qualifier and _confidence_topic(qualifier.group(1)))
    parts = re.split(r"\s+in\s+(?:the\s+context\s+of\s+)?", value, maxsplit=1, flags=re.I)
    return all(_confidence_topic(part) for part in parts)


def _epistemic_confidence(text):
    """Recognize whole uncertainty-of-knowledge statements, not world facts.

    A simple nominal topic and bounded language task may qualify confidence.
    Extra asserted clauses, instructions and follow-up offers are not ignored.
    This does not infer source truth or the meaning of the unfamiliar topic.
    """
    value = (_normal(text).replace("\u2019", "'").replace("\u2018", "'")
             .replace("\u201c", '"').replace("\u201d", '"'))
    value = re.sub(r"^I'm\b", "I am", value, flags=re.I)
    value = re.sub(r"^I don't\b", "I do not", value, flags=re.I).rstrip(".")
    task = (r"(?:\s+to\s+(?:define|explain|identify|describe|assess|evaluate|answer|discuss|interpret)\s+"
            r"(?:it|this|that|the\s+(?:term|topic|question))(?:\s+(?:reliably|accurately|confidently|with\s+confidence))?)?")
    context = r"(?:\s+(?:without|from)\s+(?:more|enough|further|additional|available|sufficient)\s+(?:context|information|evidence|details?))?"
    domain = r"(?P<domain>\s+in\s+(?:the\s+context\s+of\s+)?[^\n]+)?"
    patterns = (
        r"I do not know what\s+(?P<topic>.+?)\s+(?:is|means)" + domain,
        r"I am (?:not sure|uncertain) what\s+(?P<topic>.+?)\s+(?:is|means)" + domain,
        r"I do not recogni[sz]e\s+(?P<topic>.+?)",
        r"I am (?:not\s+(?:(?:sufficiently|very)\s+)?(?:familiar|confident|certain|sure)(?:\s+enough)?|unfamiliar|uncertain)\s+(?:with|about|of)\s+(?P<topic>.+?)" + task + context,
        r"I (?:do not know enough|have insufficient knowledge|do not have enough (?:knowledge|information))\s+(?:about|of)\s+(?P<topic>.+?)" + task + context,
        r"My (?:knowledge|understanding) of\s+(?P<topic>.+?)\s+is\s+(?:too limited|insufficient)" + task + context,
    )
    return any(match and _confidence_subject(match.group("topic") + (match.groupdict().get("domain") or "")) for pattern in patterns
               if (match := re.fullmatch(pattern, value, re.I)))


def _bounded_limitation(text, candidate):
    # Nominal availability statements ('the portal is unavailable') assert an
    # external present state. A model's limitation label does not establish it.
    # This lane has no typed absence fact; only a bounded epistemic denial can
    # legitimately avoid making an unsupported external-world assertion.
    value = _normal(text).replace("\u2019", "'").replace("\u2018", "'")
    if _epistemic_confidence(value):
        return True
    # Embedded question topics use the stricter nominal recognizer above.
    # Its failure must not fall through to the more general limitation parser,
    # which does not validate the quoted topic's internal assertion structure.
    if re.match(r"^I\s+(?:do\s+not|don't)\s+know\s+what\b", value, re.I):
        return False
    if not re.match(r"^I\s+(?:cannot|can\s+not|can't|do\s+not|don't|am\s+unable\s+to)\s+"
                    r"(?:know|determine|establish|verify|confirm|tell|assess)\b", value, re.I):
        return False
    units = interpret_text(text, user_name=candidate.contract.metadata.get("user_name"))
    return bool(units) and all(unit.kind == UnitKind.LIMITATION and unit.complete and not unit.propositions
                               and not re.search(r"\d", unit.limitation_target)
                               for unit in units)


def _non_factual(text, candidate):
    units = interpret_text(text, user_name=candidate.contract.metadata.get("user_name"))
    return bool(units) and all(unit.kind == UnitKind.REACTION and unit.complete and not unit.propositions for unit in units)


def _citation_identity(text):
    """Classify a complete source caption, independently of its truth.

    A caption asserts identity/authority, not page contents. The URL and any
    authority label must still be checked against retained Core evidence.
    Full consumption prevents a citation prefix from hiding a factual tail.
    """
    value = _normal(text).replace("\u2019", "'").rstrip(".!?")
    label = r"(?:(?P<authority>official|primary)\s+)?(?:source(?:\s+url)?|url|reference)"
    location = r"<?(?P<url>https?://[^\s<>\"'`]+)>?"
    patterns = (
        r"(?:here\s+is|here's)\s+(?:the\s+)?" + label + r"\s*:\s*" + location,
        r"(?:the\s+)?" + label + r"\s*(?::|\bis\b)\s*" + location,
        r"(?:the\s+)?" + label + r"\s+is\s+(?:right\s+)?(?:here|there)\s*:\s*" + location,
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value, re.I)
        if match:
            url = normalize_source_url(match.group("url"))
            if url:
                return url, (match.group("authority") or "").lower()
    return None


def _known_read_target(sources, candidate):
    required = candidate.evidence.metadata.get("public_requirements", {})
    read_required = _true(candidate.contract.metadata.get("source_read_required")) or _true(required.get("source_read_required"))
    requested = candidate.contract.metadata.get("requested_source_urls") or required.get("requested_source_urls", ())
    identities = {normalize_source_url(value) for item in sources for value in (item.source_url, item.data.get("read_url")) if value}
    return len(sources) == 1 and read_required and (not requested or all(normalize_source_url(value) in identities for value in requested))


def _identity_only(text, sources, candidate):
    value = _normal(text).replace("\u2019", "'").rstrip(".!?")
    if _citation_identity(value):
        # Semantic classification grants no URL or source-authority support.
        return True
    direct = re.sub(r"^(?:source(?:\s+url)?|url|loaded\s+url)\s*:\s*", "", value, flags=re.I)
    direct_url = normalize_source_url(direct)
    retained_urls = {normalize_source_url(value) for item in sources for value in (item.source_url, item.data.get("read_url")) if value}
    if direct_url:
        return direct_url in retained_urls
    anaphora = re.fullmatch(r"(?:I|We)\s+(?:(?:did|have)\s+)?(?:actually\s+)?(?:read|load(?:ed)?|open(?:ed)?|retrieved|consulted|check(?:ed)?|inspect(?:ed)?|review(?:ed)?)\s+(?:it|that|the\s+(?:page|source|documentation))", value, re.I)
    if anaphora:
        return _known_read_target(sources, candidate)
    retrieval = _retrieval_claims(value)
    if len(retrieval) == 1 and retrieval[0].start() == 0:
        tail = value[retrieval[0].end():].strip()
        if not tail:
            return _known_read_target(sources, candidate)
        location = re.fullmatch(r"from\s+(?:the\s+)?(.+)", tail, re.I)
        if location:
            name = location.group(1)
            if name.casefold() in {"site", "live site", "page", "source", "website", "public page", "public site"}:
                return _known_read_target(sources, candidate)
            url = normalize_source_url(name)
            if url:
                return url in retained_urls
            return name.casefold() in {_normal(identifier).casefold() for item in sources
                                      for identifier in (item.source_name, item.source_id) if identifier}
    match = re.fullmatch(r"(?:I|We)\s+(?:actually\s+)?(?:read|loaded|retrieved|consulted|checked|inspected|reviewed)\s+(?:the\s+)?(.+)", value, re.I)
    if not match:
        return False
    name = match.group(1).strip()
    if re.search(r"\b(?:and|but|because|which|that|while|so)\b", name, re.I):
        return False
    identities = {normalize_source_url(item.source_url) for item in sources}
    identities.update(normalize_source_url(item.data.get("read_url")) for item in sources)
    url = normalize_source_url(name)
    if url:
        return url in identities
    return name.casefold() in {_normal(value).casefold() for item in sources for value in (item.source_name, item.source_id) if value}


def _caption_authority_issue(caption, sources):
    if not caption or not caption[1]:
        return False
    url, authority = caption
    matched = tuple(item for item in sources if url in {
        normalize_source_url(item.source_url), normalize_source_url(item.data.get("read_url"))
    })
    permitted = {"primary_official"} if authority == "official" else {"primary_official", "primary_institutional"}
    return not matched or any(item.quality_eligible is not True or item.authority_tier not in permitted
                              for item in matched)


def _retrieval_claims(text):
    """Bounded affirmative page/text retrieval assertions, never evidence.

    Past-tense first-person assertions and explicit subject-elided continuations
    require retained read provenance. Negation, questions, conditionals and
    quoted/reported speech cannot manufacture a positive retrieval assertion.
    """
    value = _normal(text).replace("\u2019", "'").replace("\u2018", "'")
    if (value.endswith("?") or value.startswith(('"', "'", "“", "‘"))
            or re.match(r"^(?:if|unless|suppose|imagine|hypothetically)\b", value, re.I)
            or re.match(r"^(?:he|she|they|someone)\s+(?:said|wrote|asked)\b", value, re.I)):
        return ()
    # Mask quotations without changing offsets. Apostrophes inside words are
    # contractions/possessives, not quotation delimiters. This prevents an
    # embedded quoted contrastive clause from asserting a Core retrieval.
    masked, quote = [], None
    for index, character in enumerate(value):
        marker = '"' if character in {"“", "”"} else character
        apostrophe = (marker == "'" and index > 0 and index + 1 < len(value)
                      and value[index - 1].isalnum() and value[index + 1].isalnum())
        if quote is not None:
            masked.append(" ")
            if marker == quote and not apostrophe:
                quote = None
        elif marker in {"'", '"'} and not apostrophe:
            quote = marker
            masked.append(" ")
        else:
            masked.append(character)
    past = r"(?:fetched|pulled|retrieved|downloaded|obtained)"
    pattern = (
        r"(?:^|[;\n]\s*(?:(?:and|but)\s+)?|,\s*(?:and|but)\s+|[\u2014\u2013]\s*)"
        r"(?:(?:I|we)(?:'ve)?\s+(?:(?:have\s+)?(?:(?:actually|just|already)\s+)?" + past
        + r"|did\s+(?:actually\s+)?(?:fetch|pull|retrieve|download|obtain))|just\s+" + past + r")\s+"
        r"(?:the\s+)?(?:(?:(?:source|page|document)\s+)?(?:text|content)|"
        r"(?:web\s+)?page|document|article|report|data)\b"
    )
    return tuple(re.finditer(pattern, "".join(masked), re.I))


def _explicit_provenance_claim(text):
    return bool(re.search(
        r"\b(?:I|we)\s+(?:(?:have|did)\s+)?(?:actually\s+)?(?:read|load(?:ed)?|open(?:ed)?|retrieved|consulted|check(?:ed)?|inspect(?:ed)?|review(?:ed)?)\b|"
        r"\b(?:the|this|that)\s+(?:source|page|documentation|manual|article|report)\s+"
        r"(?:says|states|reports|confirms|indicates)\b", text, re.I,
    ) or _retrieval_claims(text))


def validate_public(candidate, units):
    """Consume typed verifier/provenance state independently of candidate origin."""
    contract = candidate.contract
    if not (contract.intent == "factual_question" and contract.authority == "public_web"
            and contract.epistemic_mode == "public_source_verified"
            and candidate.evidence.metadata.get("public_transport_version") == 1):
        return None
    state = candidate.evidence.metadata.get("public_verification")
    requirements = candidate.evidence.metadata.get("public_requirements")
    state = state if isinstance(state, Mapping) else {}
    requirements = requirements if isinstance(requirements, Mapping) else {}
    annotations = candidate.evidence.metadata.get("public_source_bindings")
    annotations = annotations if isinstance(annotations, Mapping) else {}
    annotation_status = annotations.get("status", "unavailable")
    sources = tuple(item for item in candidate.evidence.evidence if _loaded(item))
    violations, reasons, sentence_failures = [], [], []

    def fail(invariant, reason):
        violations.append(invariant)
        reasons.append(reason)

    def sentence_failure(index, kind, code):
        sentence_failures.append({"sentence_index": index, "annotation_kind": kind
                                  if kind in {"factual", "limitation", "non_factual"} else "unknown", "code": code})

    sentences = state.get("assessed_sentences")
    count = len(sentences) if isinstance(sentences, (tuple, list)) else 0
    raw = _assessment_map(state.get("sentence_assessments"), count)
    effective = _assessment_map(state.get("effective_sentence_assessments"), count)
    global_supported = state.get("global_supported")
    unsupported_count = state.get("unsupported_claim_count")
    coherent = (type(state.get("version")) is int and state["version"] == 1
                and type(candidate.evidence.metadata.get("public_transport_version")) is int
                and state.get("assessment_complete") is True
                and count > 0 and all(isinstance(value, str) and value.strip() for value in sentences)
                and raw is not None and effective is not None
                and type(global_supported) is bool and type(unsupported_count) is int and unsupported_count >= 0
                and type(state.get("effective_supported")) is bool)
    if coherent:
        coherent = (global_supported == all(raw.values())
                    and (not global_supported or unsupported_count == 0)
                    and all(not effective[index] or raw[index] for index in raw)
                    and (not state["effective_supported"] or all(effective.values())))
    if (not coherent
            or state.get("assessed_draft_digest") != hashlib.sha256(candidate.text.encode("utf-8")).hexdigest()
            or state.get("packet_digest") != candidate.evidence.metadata.get("public_packet_digest")):
        fail(PUBLIC_VERIFIER_CONSISTENCY, "The retained public verifier state is incomplete, inconsistent, or bound to different inputs")
    if candidate.evidence.metadata.get("public_source_ids_valid") is not True:
        fail(PUBLIC_VERIFIER_CONSISTENCY, "The retained packet has missing, duplicate, or invalid source identities")
    if any(item.kind == EvidenceKind.PUBLIC_SOURCE and item.data.get("admitted_in_packet") is True
           and not _loaded(item) for item in candidate.evidence.evidence):
        # Packet admission must agree with the actual retained read and source
        # state, even when the separate annotation capability is unavailable.
        # Rejected/discovered sources outside the packet remain diagnostics.
        fail(PUBLIC_VERIFIER_CONSISTENCY, "Packet evidence is inconsistent with retained source reads or admission")
    if coherent and (not global_supported or not state["effective_supported"]):
        fail(PUBLIC_GLOBAL_SUPPORT, "The existing public verifier did not accept the complete draft")
    if coherent and not all(effective.values()):
        fail(PUBLIC_SENTENCE_SUPPORT, "At least one original public sentence lacks verifier support")
        for index, supported in effective.items():
            if not supported:
                kind = next((item.get("claim_kind") for item in annotations.get("sentences", ())
                             if isinstance(item, Mapping) and item.get("index") == index), "unknown")
                sentence_failure(index, kind, "legacy_sentence_unsupported")
    entries = {item.get("index"): item for item in annotations.get("sentences", ()) if isinstance(item, Mapping)}
    loaded_by_id = {item.source_id: item for item in sources if item.source_id}
    sentence_bindings, limitation_indexes, non_factual_indexes = {}, set(), set()
    if (annotation_status in {"incomplete", "malformed"}
            and annotations.get("failure_domain") != "annotation_capability"):
        fail(PUBLIC_VERIFIER_CONSISTENCY, "The retained source-binding transport has an integrity inconsistency")
    if annotation_status == "complete" and coherent:
        for index, sentence in enumerate(sentences, 1):
            entry = entries.get(index, {})
            bound = tuple(loaded_by_id[identity] for identity in entry.get("source_ids", ()) if identity in loaded_by_id)
            sentence_bindings[index] = bound
            bound_urls = {normalize_source_url(value) for item in bound for value in (item.source_url, item.data.get("read_url")) if value}
            if any(url not in bound_urls for url in _urls(sentence)):
                fail(SOURCE_IDENTITY, "A sentence attributes a URL outside its actual supporting source bindings")
            if _source_attribution_issue(sentence, bound):
                fail(SOURCE_READ_PROVENANCE, "A sentence attributes a named source outside its actual supporting source bindings")
            caption = _citation_identity(sentence)
            if _caption_authority_issue(caption, bound):
                fail(OFFICIAL_SOURCE_SUPPORT, "The source caption's authority claim is not established by retained metadata")
            kind = entry.get("claim_kind")
            if kind == "limitation":
                if _bounded_limitation(sentence, candidate) and not entry.get("source_ids") and entry.get("provenance_claim") == "none":
                    limitation_indexes.add(index)
                else:
                    fail(PUBLIC_SENTENCE_SUPPORT, "A shadow limitation label contains a claim Core cannot independently classify as a bounded limitation")
                    sentence_failure(index, kind, "annotation_limitation_mismatch")
            elif kind == "non_factual":
                if _non_factual(sentence, candidate) and not entry.get("source_ids") and entry.get("provenance_claim") == "none":
                    non_factual_indexes.add(index)
                else:
                    fail(PUBLIC_SENTENCE_SUPPORT, "A shadow non-factual label cannot grant authority to an unassessed assertion")
                    sentence_failure(index, kind, "annotation_non_factual_mismatch")
            else:
                declared = entry.get("source_ids", ())
                if not declared or len(bound) != len(declared):
                    fail(SOURCE_READ_PROVENANCE, "A factual sentence lacks valid bindings to admitted loaded evidence")
                witnessed = {witness.get("source_id") for witness in entry.get("witnesses", ()) if isinstance(witness, Mapping)}
                identity_only = _identity_only(sentence, bound, candidate)
                if not identity_only and any(identity not in witnessed for identity in declared):
                    fail(PUBLIC_SENTENCE_SUPPORT, "A factual source binding has no literal witness in the retained evidence")
                    sentence_failure(index, kind, "factual_witness_missing")
                if entry.get("scope_status") != "supported" and not (identity_only and entry.get("scope_status") == "not_applicable"):
                    fail(INSUFFICIENT_SCOPE_SUPPORT, "The separate shadow verifier did not establish the factual sentence's requested scope")
    all_bounded = bool(count) and len(limitation_indexes | non_factual_indexes) == count and bool(limitation_indexes)
    if count and len(non_factual_indexes) == count:
        fail("contract_completion", "A factual answer contract is not completed by non-factual reactions alone")
    if not sources and not all_bounded:
        fail(SOURCE_READ_PROVENANCE, "No loaded admitted packet source establishes authority for this answer")
    loaded_urls = {url for source in sources for value in (source.source_url, source.data.get("read_url"))
                   if (url := normalize_source_url(value))}
    if any(url is None or url not in loaded_urls for url in _urls(candidate.text)):
        fail(SOURCE_IDENTITY, "The answer emits a source identity absent from loaded admitted evidence")
    if _source_attribution_issue(candidate.text, sources):
        fail(SOURCE_READ_PROVENANCE, "The answer claims a named source read that retained provenance does not establish")
    if coherent and any(_caption_authority_issue(_citation_identity(sentence), sources) for sentence in sentences):
        fail(OFFICIAL_SOURCE_SUPPORT, "A source caption claims authority absent from its retained source identity")
    official = (_true(contract.metadata.get("official_source_required"))
                or _true(requirements.get("official_source_required"))
                or contract.metadata.get("required_authority_tier") == "primary_official")
    current_requirements = requirements.get("current_user_requirements", {})
    current_requirements = current_requirements if isinstance(current_requirements, Mapping) else {}
    if _true(current_requirements.get("official_source_required")) and annotation_status != "complete" and not all_bounded:
        fail(OFFICIAL_SOURCE_SUPPORT, "The current user's official-source obligation lacks inspectable source bindings")
    relevant_sources = (tuple({item.evidence_id: item for values in sentence_bindings.values() for item in values}.values())
                        if annotation_status == "complete" else sources)
    if official and not all_bounded and (not relevant_sources or any(source.authority_tier != "primary_official"
                                       or source.quality_eligible is not True for source in relevant_sources)):
        fail(OFFICIAL_SOURCE_SUPPORT, "The actual admitted source metadata does not establish the required official authority")
    primary = _true(contract.metadata.get("primary_source_required")) or _true(requirements.get("primary_source_required"))
    if _true(current_requirements.get("primary_source_required")) and annotation_status != "complete" and not all_bounded:
        fail(OFFICIAL_SOURCE_SUPPORT, "The current user's primary-source obligation lacks inspectable source bindings")
    if primary and not all_bounded and (not relevant_sources or any(
        source.authority_tier not in {"primary_official", "primary_institutional"} or source.quality_eligible is not True
        for source in relevant_sources
    )):
        fail(OFFICIAL_SOURCE_SUPPORT, "The actual admitted source metadata does not establish qualifying primary authority")
    if (_true(contract.metadata.get("source_quality_required")) or _true(requirements.get("quality_evidence_required"))) and any(source.quality_eligible is not True for source in relevant_sources):
        fail(OFFICIAL_SOURCE_SUPPORT, "The actual admitted source metadata does not meet required source quality")
    if not all_bounded and _scope_issue(candidate, relevant_sources, requirements):
        fail(INSUFFICIENT_SCOPE_SUPPORT, "An explicit structured source-scope obligation remains unsupported")
    if not all_bounded and _currentness_issue(candidate, relevant_sources, requirements):
        fail(INSUFFICIENT_CURRENTNESS_SUPPORT, "The required contemporary state is not established by retained structured evidence")
    read_required = _true(contract.metadata.get("source_read_required")) or _true(requirements.get("source_read_required"))
    requested = contract.metadata.get("requested_source_urls") or requirements.get("requested_source_urls", ())
    exact_required = _true(contract.metadata.get("exact_source_required")) or _true(requirements.get("exact_source_required"))
    if _true(current_requirements.get("exact_source_required")) and annotation_status != "complete" and not all_bounded:
        fail(SOURCE_IDENTITY, "The current user's actual-source identity obligation lacks inspectable source bindings")
    if annotation_status != "complete" and coherent and any(
        _explicit_provenance_claim(sentence) and not _identity_only(sentence, sources, candidate)
        for sentence in sentences
    ):
        fail(SOURCE_READ_PROVENANCE, "An explicit read or source-assertion claim lacks inspectable source bindings")
    if read_required and not all_bounded:
        if annotation_status != "complete" or not relevant_sources:
            fail(SOURCE_READ_PROVENANCE, "The user's explicit source-read obligation lacks inspectable source bindings")
        required_urls = tuple(normalize_source_url(url) for url in requested)
        relevant_urls = {normalize_source_url(value) for item in relevant_sources for value in (item.source_url, item.data.get("read_url")) if value}
        if required_urls and any(url not in relevant_urls for url in required_urls):
            fail(SOURCE_IDENTITY, "The actual read evidence does not identify the source the user requested")
    if exact_required and not all_bounded:
        emitted = set(_urls(candidate.text))
        if ((requested and any(normalize_source_url(url) not in emitted for url in requested))
                or (not requested and not emitted.intersection(loaded_urls))):
            fail(SOURCE_IDENTITY, "The answer does not preserve the explicitly requested source identity")

    proofs = {}
    # The generic interpreter may split URLs or semicolons more finely than
    # the public verifier. Map original text spans; do not reinterpret support
    # from strings or bind an earlier draft's verdict to changed wording.
    rendered = _normal(candidate.text)
    sentence_spans = []
    cursor = 0
    if coherent:
        for index, sentence in enumerate(sentences, 1):
            value = _normal(sentence)
            start = rendered.find(value, cursor)
            if start < 0 or rendered[cursor:start].strip():
                fail(PUBLIC_VERIFIER_CONSISTENCY, "Verifier sentence text does not completely cover the original candidate")
                sentence_spans = []
                break
            sentence_spans.append((start, start + len(value), index))
            cursor = start + len(value)
        if sentence_spans and rendered[cursor:].strip():
            fail(PUBLIC_VERIFIER_CONSISTENCY, "Verifier sentence text omits part of the original candidate")
            sentence_spans = []
    cursor = 0
    if sentence_spans:
        for unit in units:
            value = _normal(unit.text)
            start = rendered.find(value, cursor)
            if start < 0:
                fail(PUBLIC_VERIFIER_CONSISTENCY, "Public unit coverage cannot be bound to the original candidate")
                break
            end = start + len(value)
            owner = next((index for low, high, index in sentence_spans if low <= start and end <= high), None)
            if owner is None:
                fail(PUBLIC_VERIFIER_CONSISTENCY, "A public unit extends outside its original verifier sentence")
                break
            failed = () if effective[owner] else (PUBLIC_SENTENCE_SUPPORT,)
            proofs[unit.index] = TypedUnitValidation(
                evidence_ids=tuple(source.evidence_id for source in sentence_bindings.get(owner, ()) if source.evidence_id),
                obligations=("public_answer",) if not failed else (),
                violated_invariants=failed,
                reasons=("The original public sentence lacks verifier support",) if failed else (),
            )
            cursor = end
    if not proofs and not violations:
        fail(PUBLIC_VERIFIER_CONSISTENCY, "No original public units were completely assessed")
    return TypedEvaluation(
        validator="public_factual_verifier_provenance", units=proofs,
        completion_obligations=("public_answer",),
        global_violations=tuple(dict.fromkeys(violations)), global_reasons=tuple(dict.fromkeys(reasons)),
        diagnostic_metadata={"public_sentence_failures": tuple(sentence_failures)} if sentence_failures else {},
    )
