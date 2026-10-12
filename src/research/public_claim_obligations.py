"""Bounded source-body obligations for public relations and explanations.

Detection belongs to Core. A verifier may assess entailment, but cannot erase
an obligation by returning a positive global verdict. Search labels and titles
remain identities/metadata; only admitted readable body text can witness these
content propositions. This module does not publish or invoke a model.
"""
from __future__ import annotations

from collections.abc import Mapping
import re


_NAME = r"[A-Z][A-Za-z0-9'’\-]*(?:\s+[A-Z][A-Za-z0-9'’\-]*){0,3}"
_NON_NAMES = {"I", "You", "It", "They", "We", "He", "She", "The", "This", "That", "People", "Fans"}
# Semantic families, not topic/entity-specific bans. Symmetric families keep
# the same participants; directional families additionally keep their roles.
_FAMILIES = {
    "collaboration": (r"work(?:s|ed|ing)?\s+(?:together\s+)?with|collaborat(?:e|es|ed|ing)\s+with|team(?:s|ed|ing)?\s+up\s+with", True),
    "conflict": (r"disagree(?:s|d|ing)?\s+with|argu(?:e|es|ed|ing)\s+with|had\s+(?:a\s+)?(?:disagreement|argument)\s+with", True),
    "criticism": (r"criticis(?:e|es|ed|ing)|criticiz(?:e|es|ed|ing)|accus(?:e|es|ed|ing)|blam(?:e|es|ed|ing)", False),
    "defeat": (r"defeat(?:s|ed|ing)?|beat(?:s|en)?|outperform(?:s|ed|ing)?", False),
    "causation": (r"caus(?:e|es|ed|ing)", False),
    "relationship": (r"(?:is|was|are|were)\s+(?:related|connected|linked)\s+to|pair(?:s|ed|ing)?\s+(?:up\s+)?with", True),
}
_DIRECT = tuple((kind, symmetric, re.compile(
    rf"\b(?P<a>{_NAME})\s+(?:(?i:did\s+not|does\s+not|do\s+not|never)\s+)?"
    rf"(?P<predicate>(?i:{pattern}))\s+(?P<b>{_NAME})\b"
)) for kind, (pattern, symmetric) in _FAMILIES.items())
_BETWEEN = re.compile(rf"\b(?i:between)\s+(?P<a>{_NAME})\s+(?i:and)\s+(?P<b>{_NAME})\b")
_JOINT = re.compile(rf"\b(?P<a>{_NAME})\s+(?i:and)\s+(?P<b>{_NAME})\s+(?P<tail>[^.!?]{{0,90}})")
_REASON = re.compile(
    r"\bbecause\b|\bdue\s+to\b|\b(?:the|a|one)\s+reason\s+(?:is|was|for|why)\b|"
    r"\b(?:explains?|explained|explaining)\s+(?:why|the)\b|\b(?:is|was)\s+why\b", re.I,
)
_RECEPTION = re.compile(
    r"\b(?:people|fans|audiences?|viewers?|readers?|customers?)\b[^.!?]{0,90}"
    r"\b(?:lov(?:e|ed)|lik(?:e|ed)|celebrat(?:e|ed)|prais(?:e|ed)|talk(?:ing|ed)?\s+about|discuss(?:ed|ing)?)\b|"
    r"\b(?:fan[ -]favou?rite|became\s+popular|(?:is|was|are|were)\s+(?:very\s+)?popular|trend(?:ed|ing))\b", re.I,
)
_RECEPTION_VERBS = {
    "appreciation": r"lov(?:e|ed)|lik(?:e|ed)|celebrat(?:e|ed)|prais(?:e|ed)",
    "discussion": r"talk(?:ing|ed)?\s+about|discuss(?:ed|ing)?",
    "favourite": r"fan[ -]favou?rite",
    "popularity": r"became\s+popular|(?:is|was|are|were)\s+(?:very\s+)?popular|trend(?:ed|ing)",
}


def _normal(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold().replace("’", "'")


def _relations(text):
    found = []
    for kind, symmetric, pattern in _DIRECT:
        for match in pattern.finditer(str(text or "")):
            a, b = match.group("a").strip(), match.group("b").strip()
            if a not in _NON_NAMES and b not in _NON_NAMES and a != b:
                relation = {"kind": kind, "a": a, "b": b, "symmetric": symmetric}
                if kind == "relationship":
                    relation["nominal"] = ("pairing",) if re.search(r"\bpair", match.group("predicate"), re.I) else ("relationship",)
                found.append(relation)
    for match in _BETWEEN.finditer(str(text or "")):
        # "between" explicitly separates participants, independently of the
        # surrounding relation noun (which remains for semantic entailment).
        a, b = match.group("a").strip(), match.group("b").strip()
        if a not in _NON_NAMES and b not in _NON_NAMES and a != b:
            prefix = str(text or "")[:match.start()]
            prefix = re.split(r"[.!?;:]|\b(?:because|but|and)\b", prefix, flags=re.I)[-1]
            atoms = _literal_atoms(prefix)
            words = [word for word in re.findall(r"[a-z][a-z0-9'-]*", _normal(prefix)) if word in atoms]
            tail = str(text or "")[match.end():]
            tail = re.split(r"[.!?;]|\b(?:because|but)\b", tail, maxsplit=1, flags=re.I)[0]
            tail_atoms = _stem_atoms(_literal_atoms(tail)) if re.match(
                r"^\s+(?:is|was|are|were|became|becomes|has|had)\b", tail, re.I,
            ) else set()
            found.append({"kind": "relationship", "a": a, "b": b, "symmetric": True,
                          "nominal": tuple(words[-2:]), "state_atoms": tuple(sorted(tail_atoms))})
    for match in _JOINT.finditer(str(text or "")):
        tail = match.group("tail")
        kind = None
        if re.search(r"\b(?:worked|collaborated|teamed)\s+together\b", tail, re.I):
            kind = "collaboration"
        elif re.search(r"\b(?:had\s+(?:a\s+)?(?:disagreement|argument)|disagreed|argued)\b", tail, re.I):
            kind = "conflict"
        elif re.search(r"\b(?:relationship|pair|paired|related|connected)\b", tail, re.I):
            kind = "relationship"
        a, b = match.group("a").strip(), match.group("b").strip()
        if kind and a not in _NON_NAMES and b not in _NON_NAMES and a != b:
            relation = {"kind": kind, "a": a, "b": b, "symmetric": True}
            if kind == "relationship":
                relation["nominal"] = ("pairing",) if re.search(r"\bpair", tail, re.I) else ("relationship",)
            found.append(relation)
    return tuple(found)


def admitted_body_sources(packet):
    sources = packet.get("sources", ()) if isinstance(packet, Mapping) else ()
    if not isinstance(sources, (list, tuple)):
        return {}
    result = {}
    for index, source in enumerate(sources, 1):
        if not isinstance(source, Mapping):
            continue
        if (source.get("read_success") is False or source.get("accepted_as_evidence") is False
                or source.get("relevance_status") in {"rejected", "unreadable", "unavailable"}):
            continue
        body = source.get("content_excerpt")
        source_id = source.get("source_id") or f"packet_source_{index}"
        if not isinstance(body, str) or not body.strip() or not isinstance(source_id, str):
            continue
        # Duplicate identifiers cannot select an unambiguous evidence witness.
        if source_id in result:
            result[source_id] = None
        else:
            result[source_id] = source
    return {key: value for key, value in result.items() if value is not None}


def build_public_claim_obligations(sentences):
    """Recognise bounded relational/reason content; never infer its truth."""
    obligations = []
    for sentence_index, sentence in enumerate(sentences, 1):
        value = str(sentence or "").strip()
        # A quoted question or truthful bounded epistemic target does not
        # assert the relation nested in that target. Independent factual tails
        # still enter the normal sentence verifier and its factuality checks.
        if value.endswith("?") or re.match(
            r"^I\s+(?:cannot|can['’]t|could\s+not|couldn['’]t|do\s+not|don['’]t|did\s+not|didn['’]t|"
            r"am\s+unable\s+to|was\s+unable\s+to|haven['’]t\s+been\s+able\s+to)\s+"
            r"(?:verify|confirm|establish|determine|know)\b"
            r"[^.!?;]+[.!]?$", value, re.I,
        ) and not re.search(r"\b(?:but|however|because|and\s+(?:it|they|the|this))\b", value, re.I):
            continue
        claims = [("entity_relation", relation) for relation in _relations(value)]
        if _REASON.search(value):
            claims.append(("explanation", None))
        if _RECEPTION.search(value):
            claims.append(("reception", None))
        for kind, relation in claims:
            entry = {"index": len(obligations) + 1, "sentence_index": sentence_index,
                     "kind": kind, "candidate_span": value}
            if relation:
                entry["relation"] = relation
            obligations.append(entry)
    return tuple(obligations)


def public_claim_assessment_schema(base_schema):
    import copy
    result = copy.deepcopy(base_schema)
    result["properties"]["claim_assessments"] = {
        "type": "array", "items": {
            "type": "object", "properties": {
                "index": {"type": "integer", "minimum": 1},
                "supported": {"type": "boolean"},
                "source_id": {"type": ["string", "null"]},
                "source_quote": {"type": ["string", "null"]},
            }, "required": ["index", "supported", "source_id", "source_quote"],
            "additionalProperties": False,
        },
    }
    result["required"].append("claim_assessments")
    return result


def _relation_matches(candidate, witness):
    if candidate["kind"] != witness["kind"]:
        return False
    pair = (_normal(candidate["a"]), _normal(candidate["b"]))
    other = (_normal(witness["a"]), _normal(witness["b"]))
    if not (pair == other or candidate["symmetric"] and pair == other[::-1]):
        return False
    if candidate["kind"] == "relationship":
        required = set(candidate.get("nominal", ()))
        offered = set(witness.get("nominal", ()))
        states = set(candidate.get("state_atoms", ()))
        return bool(required) and required.issubset(offered) and states.issubset(witness.get("state_atoms", ()))
    return True


def _factual_scope(text):
    value = str(text or "").strip()
    if value.endswith("?") or re.match(r"^(?:[\"“]|if\b|suppose\b|imagine\b)", value, re.I):
        return "unasserted"
    return "negative" if re.search(r"\b(?:not|never|no)\b|n['’]t\b", value, re.I) else "positive"


def _body_clauses(body):
    return tuple(part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", str(body or "")) if part.strip())


def _body_quote_scope_matches(body, quote, candidate):
    units = [unit for unit in _body_clauses(body) if quote in unit]
    if not units:
        # A multi-sentence witness retains all its context itself. It cannot
        # select an isolated substring from one quoted/conditional sentence.
        return bool(len(_body_clauses(quote)) > 1 and _factual_scope(quote) == _factual_scope(candidate))
    return any(_factual_scope(unit) == _factual_scope(candidate) for unit in units)


def _literal_atoms(text):
    # A deliberately small structural anchor vocabulary. This does not infer
    # synonyms or truth: the semantic assessment still owns entailment. An
    # unrelated clause cannot stand in as a witness just because it says why.
    stop = {"a", "an", "the", "this", "that", "it", "its", "they", "their", "them", "is", "was", "were",
            "are", "be", "been", "had", "has", "have", "to", "of", "for", "and", "or", "with", "as", "by",
            "in", "on", "at", "from", "about", "because", "due", "people", "fans", "audience", "audiences",
            "readers", "viewers", "customers", "very", "so", "a", "reason", "why", "not", "no", "never",
            "love", "loved", "like", "liked", "celebrate", "celebrated", "praise", "praised", "talked", "talking",
            "discussed", "discussing", "popular", "became", "trended", "trending"}
    return {word for word in re.findall(r"[a-z][a-z0-9'-]*", _normal(text)) if word not in stop}


def _stem_atoms(values):
    result = set()
    for value in values:
        if len(value) > 5 and value.endswith("ing"):
            value = value[:-3]
            if len(value) > 2 and value[-1] == value[-2]:
                value = value[:-1]
        elif len(value) > 4 and value.endswith("ed"):
            value = value[:-2]
        elif len(value) > 4 and value.endswith("s"):
            value = value[:-1]
        result.add(value)
    return result


def _reception_propositions(text):
    found = []
    for kind, pattern in _RECEPTION_VERBS.items():
        for match in re.finditer(rf"\b(?:{pattern})\b", str(text or ""), re.I):
            prefix = str(text or "")[:match.start()]
            suffix = str(text or "")[match.end():]
            suffix = re.split(r"[.!?;]|\b(?:because|due\s+to|but)\b", suffix, maxsplit=1, flags=re.I)[0]
            if kind in {"favourite", "popularity"}:
                # Adjectival popularity attaches to its preceding subject.
                target = re.split(r"[.!?;]|\b(?:because|but)\b", prefix, flags=re.I)[-1]
            else:
                target = suffix
            negative = bool(re.search(r"\b(?:not|never|no)\b|n['’]t\b", prefix[-50:], re.I))
            found.append((kind, negative, _stem_atoms(_literal_atoms(target))))
    return found


def _content_witness_issue(item, quote):
    candidate = item["candidate_span"]
    if _factual_scope(quote) != _factual_scope(candidate):
        return "content_assertion_scope_mismatch"
    # Preserve proper entity anchors. A source about a different named subject
    # cannot satisfy this proposition through a shared popularity/reason verb.
    names = [name for name in re.findall(_NAME, candidate) if name not in _NON_NAMES]
    if names and any(_normal(name) not in _normal(quote) for name in names):
        return "content_subject_mismatch"
    if item["kind"] == "explanation":
        claim_marker, source_marker = _REASON.search(candidate), _REASON.search(quote)
        if not source_marker:
            return "explanation_witness_missing"
        # For explicit because/due-to clauses, check each side independently.
        # A shared event title cannot rescue a completely different cause.
        if (claim_marker and claim_marker.group().lower() in {"because", "due to"}
                and source_marker.group().lower() in {"because", "due to"}):
            for claim_part, source_part in (
                (candidate[:claim_marker.start()], quote[:source_marker.start()]),
                (candidate[claim_marker.end():], quote[source_marker.end():]),
            ):
                wanted, offered = _stem_atoms(_literal_atoms(claim_part)), _stem_atoms(_literal_atoms(source_part))
                if wanted and not wanted.issubset(offered):
                    return "explanation_anchor_mismatch"
    elif item["kind"] == "reception":
        if not _RECEPTION.search(quote):
            return "reception_witness_missing"
        candidate_reception = _reception_propositions(candidate)
        source_reception = _reception_propositions(quote)
        for kind, negative, wanted in candidate_reception:
            if not any(kind == other_kind and negative == other_negative and wanted.issubset(offered)
                       for other_kind, other_negative, offered in source_reception):
                return "reception_anchor_mismatch"
    return None


def public_claim_failures(obligations, raw_assessments, packet, annotation_present=None):
    """Return bounded reasons by sentence; failed units cannot be salvaged."""
    failures = {}

    def fail(item, reason):
        failures.setdefault(item["sentence_index"], set()).add(reason)

    if not obligations:
        return failures
    if not isinstance(raw_assessments, list):
        present = raw_assessments is not None if annotation_present is None else annotation_present
        if present is not False:
            for item in obligations:
                fail(item, "invalid_claim_assessments")
            return failures
        # A whole literal clause retained in an admitted body is a strict Core
        # proof, unlike entity/topic overlap. Older callers need no annotation
        # to re-establish that exact proposition. Present malformed or negative
        # assessments are still evaluated below and cannot be overridden.
        sources = admitted_body_sources(packet)
        literal = []
        for item in obligations:
            match = next(((key, source) for key, source in sources.items()
                          if item["candidate_span"] in _body_clauses(source["content_excerpt"])), None)
            if match:
                literal.append({"index": item["index"], "supported": True,
                                "source_id": match[0], "source_quote": item["candidate_span"]})
            else:
                fail(item, "missing_claim_assessments")
        if not failures:
            return public_claim_failures(obligations, literal, packet)
        return failures
    assessments = {}
    malformed = False
    for value in raw_assessments:
        if (not isinstance(value, dict)
                or set(value) != {"index", "supported", "source_id", "source_quote"}
                or type(value["index"]) is not int or value["index"] in assessments
                or not 1 <= value["index"] <= len(obligations)
                or type(value["supported"]) is not bool):
            malformed = True
            break
        assessments[value["index"]] = value
    if malformed or set(assessments) != set(range(1, len(obligations) + 1)):
        for item in obligations:
            fail(item, "invalid_claim_assessments")
        return failures
    sources = admitted_body_sources(packet)
    for item in obligations:
        assessment = assessments[item["index"]]
        if assessment["supported"] is not True:
            fail(item, "unsupported_content_proposition")
            continue
        source_id, quote = assessment["source_id"], assessment["source_quote"]
        source = sources.get(source_id) if isinstance(source_id, str) else None
        if (source is None or not isinstance(quote, str) or not quote.strip()
                or len(quote) > 800 or quote not in source["content_excerpt"]):
            fail(item, "missing_admitted_body_witness")
            continue
        if not _body_quote_scope_matches(source["content_excerpt"], quote, item["candidate_span"]):
            fail(item, "relation_polarity_mismatch" if item["kind"] == "entity_relation"
                 else "content_assertion_scope_mismatch")
            continue
        if item["kind"] == "entity_relation":
            relation = item["relation"]
            source_relations = _relations(quote)
            matches = [other for other in source_relations if _relation_matches(relation, other)]
            if not matches:
                full = _normal(relation["a"] + " " + relation["b"])
                retained_span = any(re.search(r"\b" + re.escape(full) + r"\b", _normal(source.get(key)))
                                    for key in ("title", "search_snippet", "content_excerpt"))
                separately_named = any({_normal(other["a"]), _normal(other["b"])}
                                       == {_normal(relation["a"]), _normal(relation["b"])}
                                       for other in source_relations)
                fail(item, "entity_span_split" if retained_span and not separately_named
                     else "relation_witness_missing")
            # Quoting a negated relation cannot support its positive assertion.
            elif _factual_scope(quote) != _factual_scope(item["candidate_span"]):
                fail(item, "relation_polarity_mismatch")
        else:
            issue = _content_witness_issue(item, quote)
            if issue:
                fail(item, issue)
    return failures


def public_request_requires_relational_completion(user_input):
    """A reason or explicitly relational request cannot be met by topic overlap."""
    value = str(user_input or "").strip()
    return bool(re.search(
        r"\bwhy\b|\bwhat\s+(?:caused|explains?|was\s+the\s+reason)\b|"
        r"\b(?:the|their|a)\s+(?:relationship|relation|connection|disagreement|collaboration)\b|"
        r"\b(?:people|fans|audiences?|viewers?|readers?|everyone|everybody|others|they)\b[^.!?]{0,60}"
        r"\b(?:talk(?:ing|ed)?\s+about|discuss(?:ing|ed)?|lov(?:e|ed)|prais(?:e|ed))\b",
        value, re.I,
    ))


# These are literal identity/date roles, not a subject ontology. They deliberately
# do not normalise away interior punctuation, split names or infer event dates
# from search/publication labels. The legacy semantic verifier still assesses
# entailment for the whole sentence after these mandatory Core checks.
_QUOTED_IDENTITY = re.compile(
    r"\b(?:titled|entitled|called|named|known\s+as|title\s+(?:is|was))\s*:?\s*"
    r"[\"“‘](?P<identity>[^\"”\n]{1,160})[\"”’]", re.I,
)
_UNQUOTED_IDENTITY = re.compile(
    r"(?i:\b(?:titled|entitled|called|named|known\s+as|title\s+(?:is|was))\s*:?\s*)"
    rf"(?P<identity>{_NAME}(?:\s*(?:(?i:and|or)|[&+/,:;–—])\s*{_NAME})?)"
)
_SPLIT_NAME = re.compile(
    rf"\b(?P<a>{_NAME})\s*(?P<separator>(?i:and|or)|[&+/,:;]|\s[-–—]\s)\s*(?P<b>{_NAME})\b"
)
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|(?:" + "|".join(_MONTHS) +
    r")\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{1,2}(?:st|nd|rd|th)?\s+(?:" +
    "|".join(_MONTHS) + r")(?:,?\s+\d{4})?)\b", re.I,
)
_RELATIVE_DATE = re.compile(r"\b(?:around\s+then|then|(?:at|around|on)\s+that\s+(?:time|date|day))\b", re.I)
_DATE_ROLES = (
    ("air", r"air(?:ed|s)?|broadcast(?:ed|s)?"),
    ("release", r"releas(?:e|ed|es)"),
    ("launch", r"launch(?:ed|es)?"),
    ("premiere", r"premier(?:e|ed|es)"),
    ("debut", r"debut(?:ed|s)?"),
    ("posting", r"post(?:ed|s)?|upload(?:ed|s)?"),
    ("publication", r"publish(?:ed|es)?"),
    ("drop", r"drop(?:ped|s)?"),
    ("occurrence", r"(?:took|takes?)\s+place|(?:was|is)\s+held|occur(?:red|s)?|happen(?:ed|s)?"),
)
_DATE_PREDICATES = tuple((role, re.compile(
    rf"\b(?P<verb>{verbs})\b(?P<tail>[^.!?;\n]{{0,160}})", re.I,
)) for role, verbs in _DATE_ROLES)
_SOURCE_PUBLICATION_SUBJECT = re.compile(r"^(?:the|this|that|a)\s+(?:source|article|page|post|report|document)$", re.I)


def _identity_normal(value):
    # Typography/casing outside the identity is harmless. Interior punctuation
    # remains meaningful: A B, A & B and A/B are three different identities.
    return re.sub(r"\s+", " ", str(value or "").strip().strip('"“”‘’')).casefold().replace("’", "'")


def _bounded_identity_occurs(identity, text):
    wanted = _identity_normal(identity)
    value = _identity_normal(text)
    return bool(wanted and re.search(r"(?<![\w])" + re.escape(wanted) + r"(?![\w])", value))


def _asserted_body_identity(source, identity):
    for clause in _body_clauses(source.get("content_excerpt")):
        if (_factual_scope(clause) == "positive" and _bounded_identity_occurs(identity, clause)):
            return True
    return False


def _literal_identity_witness(source, item):
    identity = item["identity"]
    title = str(source.get("title") or "")
    quoted_titles = re.findall(r'["“]([^"”\n]{1,160})["”]|‘([^"”\n]{1,160})’', title)
    quoted_titles = [double or single for double, single in quoted_titles]
    if _bounded_identity_occurs(identity, title):
        # A quoted identity must match the whole quoted span. Mere substring
        # overlap cannot truncate a two-token entity to one participant.
        partial_quote = any(_bounded_identity_occurs(identity, quoted)
                            and _identity_normal(identity) != _identity_normal(quoted)
                            for quoted in quoted_titles)
        if not partial_quote:
            return True
    for clause in _body_clauses(source.get("content_excerpt")):
        if _factual_scope(clause) != "positive":
            continue
        # A complete standalone body heading is bounded literal identity.
        if _identity_normal(clause.rstrip(".")) == _identity_normal(identity):
            return True
        for match in _identity_mentions(clause):
            if (_identity_normal(match["identity"]) == _identity_normal(identity)
                    and _date_subject(clause[:match.start()]) == item["subject"]):
                return True
    return False


def _identity_mentions(value):
    # Quoted and unquoted titles carry the same identity authority. The latter
    # is limited to explicit naming predicates and proper identity spans, not
    # arbitrary description prose or attribution/source captions.
    return tuple(sorted((*_QUOTED_IDENTITY.finditer(value), *_UNQUOTED_IDENTITY.finditer(value)),
                        key=lambda match: match.start()))


def _date_key(value):
    text = _normal(value)
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return (int(iso[1]), int(iso[2]), int(iso[3]))
    clean = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b|,", "", text)
    words = clean.split()
    if not 2 <= len(words) <= 3:
        return None
    if words[0] in _MONTHS:
        month, day = _MONTHS.index(words[0]) + 1, words[1]
    elif words[1] in _MONTHS:
        month, day = _MONTHS.index(words[1]) + 1, words[0]
    else:
        return None
    if not day.isdigit() or len(words) == 3 and not words[2].isdigit():
        return None
    return (int(words[2]) if len(words) == 3 else None, month, int(day))


def _date_subject(value):
    clean = re.sub(r"\b(?:is|was|were|has|had|been|will|be|first|initially|officially|actually)\b", " ", _normal(value))
    return re.sub(r"\s+", " ", clean).strip(" ,:—–-")


def _date_claims(text, reference_date=None):
    """Extract only an explicit event/date relation, preserving its role."""
    value = str(text or "").strip()
    if value.endswith("?") or _factual_scope(value) == "unasserted":
        return ()
    claims = []
    for role, pattern in _DATE_PREDICATES:
        for match in pattern.finditer(value):
            date = _DATE.search(match["tail"])
            relative = None if date else _RELATIVE_DATE.search(match["tail"])
            marker = date or relative
            if not marker:
                continue
            prefix = re.split(r"[.!?;]|\b(?:but|and|while)\b", value[:match.start()], flags=re.I)[-1]
            subject = _date_subject(prefix)
            # Distinguish a passive event ('was released') from an active agent
            # ('A released B'). The latter needs the named object as well.
            object_text = match["tail"][:marker.start()]
            object_text = re.sub(r"\b(?:on|in|at|around|by|during)\s*$", "", object_text, flags=re.I).strip()
            earlier_dates = {_date_key(found.group()) for found in _DATE.finditer(value[:match.start()])}
            resolved_date = (next(iter(earlier_dates)) if len(earlier_dates) == 1 else None) if earlier_dates else reference_date
            claims.append({"role": role, "date": _date_key(date.group()) if date else resolved_date,
                           "subject": subject, "object": _normal(object_text),
                           "polarity": _factual_scope(value)})
    return tuple(claims)


def _body_date_claims(body):
    reference = None
    result = []
    for clause in _body_clauses(body):
        if _factual_scope(clause) == "unasserted":
            continue
        result.extend(_date_claims(clause, reference_date=reference))
        dates = {_date_key(match.group()) for match in _DATE.finditer(clause)}
        if dates:
            reference = next(iter(dates)) if len(dates) == 1 else None
    return tuple(result)


def _date_subject_matches(candidate, witness, source):
    subject = candidate["subject"]
    other = witness["subject"]
    if subject in {"it", "this", "that", "they"}:
        # An anaphoric answer may use the one source-supported item, but may
        # not borrow a neighbouring schedule entry or another named object.
        numbers = set(re.findall(r"\b\d+\b", str(source.get("title") or "")))
        offered_numbers = set(re.findall(r"\b\d+\b", other))
        # Date labels in the title are not item identifiers.
        for date in _DATE.finditer(str(source.get("title") or "")):
            numbers.difference_update(re.findall(r"\b\d+\b", date.group()))
        if not other or other in {"it", "this", "that", "they"}:
            return False
        if numbers:
            return numbers.issubset(offered_numbers)
        # Without item identifiers, a retained quoted identity may establish
        # which actual item the pronoun denotes. A different named item in the
        # same readable page must not lend its date to this one. Unresolved
        # unnumbered/anaphoric scope stays conservative for the legacy verifier.
        identities = re.findall(r'["“]([^"”\n]{1,160})["”]', str(source.get("title") or ""))
        return any(_bounded_identity_occurs(identity, other) for identity in identities)
    if subject == other:
        return True
    # Articles/determiners are rendering details; no synonym or token-overlap
    # entity matching is used to turn a different event into this one.
    return re.sub(r"^(?:the|a|an)\s+", "", subject) == re.sub(r"^(?:the|a|an)\s+", "", other)


def public_identity_date_obligations(sentences):
    """Core-owned identity and date-role propositions, independent of verdicts."""
    result = []
    reference = None
    for index, sentence in enumerate(sentences, 1):
        value = str(sentence or "").strip()
        if value.endswith("?") or _factual_scope(value) == "unasserted":
            continue
        if (re.match(r"^I\s+(?:cannot|can['’]t|could\s+not|couldn['’]t|do\s+not|don['’]t|"
                     r"was\s+unable\s+to|am\s+unable\s+to)\s+(?:verify|confirm|establish|determine|know)\b",
                     value, re.I)
                and not re.search(r"\b(?:but|however|because|and\s+(?:it|they|the|this))\b", value, re.I)):
            continue
        if _factual_scope(value) == "positive":
            for match in _identity_mentions(value):
                result.append({"sentence_index": index, "kind": "literal_identity", "identity": match["identity"],
                               "subject": _date_subject(value[:match.start()])})
            for match in _SPLIT_NAME.finditer(value):
                a, b = match["a"].strip(), match["b"].strip()
                if a not in _NON_NAMES and b not in _NON_NAMES:
                    result.append({"sentence_index": index, "kind": "entity_segmentation",
                                   "identity": match.group(), "unsplit": a + " " + b})
        for claim in _date_claims(value, reference_date=reference):
            result.append({"sentence_index": index, "kind": "date_role", **claim})
        dates = {_date_key(match.group()) for match in _DATE.finditer(value)}
        if dates:
            reference = next(iter(dates)) if len(dates) == 1 else None
    return tuple(result)


def public_identity_date_failures(obligations, packet):
    """Literal metadata may prove identity, never an event/date relationship."""
    sources = admitted_body_sources(packet)
    failures = {}
    for item in obligations:
        reason = None
        if item["kind"] in {"literal_identity", "entity_segmentation"}:
            proven = any(_literal_identity_witness(source, item) if item["kind"] == "literal_identity"
                         else _bounded_identity_occurs(item["identity"], source.get("title"))
                         or _asserted_body_identity(source, item["identity"]) for source in sources.values())
            if proven:
                continue
            if item["kind"] == "entity_segmentation":
                # Only an actual retained one-span entity activates this check.
                # Separately named people remain for c's relational verifier.
                unsplit = any(_bounded_identity_occurs(item["unsplit"], source.get("title"))
                              or _asserted_body_identity(source, item["unsplit"]) for source in sources.values())
                if not unsplit:
                    continue
                reason = "entity_identity_split"
            else:
                reason = "literal_identity_witness_missing"
        elif item["kind"] == "date_role":
            proven = False
            if item["date"] is None:
                failures.setdefault(item["sentence_index"], set()).add("event_date_reference_unresolved")
                continue
            for source in sources.values():
                # Structured search publication metadata is authority only for
                # the source/page's publication date, not an item's release.
                published = str(source.get("published_date") or "")
                if (item["role"] == "publication" and item["polarity"] == "positive" and not item["object"]
                        and _SOURCE_PUBLICATION_SUBJECT.fullmatch(item["subject"])
                        and _date_key(published) == item["date"]):
                    proven = True
                if any(other["polarity"] == item["polarity"]
                       and other["role"] == item["role"] and other["date"] == item["date"]
                       and other["object"] == item["object"]
                       and _date_subject_matches(item, other, source)
                       for other in _body_date_claims(source["content_excerpt"])):
                    proven = True
                if proven:
                    break
            if not proven:
                reason = "event_date_role_witness_missing"
        if reason:
            failures.setdefault(item["sentence_index"], set()).add(reason)
    return failures


def public_request_requires_identity_date_completion(user_input, obligations):
    """Deletion of a requested identity/date cannot leave an unrelated fragment.

    Only actual Core-detected propositions from the assessed draft activate
    this additional obligation. The ordinary evergreen completion budget is
    unchanged when no such proposition was removed.
    """
    if not isinstance(obligations, (list, tuple)):
        raise ValueError("invalid identity/date obligations")
    kinds = set()
    for item in obligations:
        if (not isinstance(item, Mapping) or type(item.get("sentence_index")) is not int
                or item["sentence_index"] < 1
                or item.get("kind") not in {"literal_identity", "entity_segmentation", "date_role"}):
            raise ValueError("invalid identity/date obligation")
        kinds.add(item["kind"])
    value = str(user_input or "")
    identity = bool(re.search(r"\b(?:what\s+(?:is|was)|which)\b|\b(?:title|name|called|titled|named)\b", value, re.I))
    date = bool(re.search(r"\bwhen\b|\b(?:what|which)\s+(?:is\s+|was\s+|the\s+)?date\b", value, re.I))
    return bool(identity and kinds & {"literal_identity", "entity_segmentation"}
                or date and "date_role" in kinds)
