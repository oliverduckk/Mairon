"""Bounded request-to-answer binding for immediate public explanations.

This layer projects obligations from USER requests, never from proposed answers.
The existing semantic verifier judges entailment in its ordinary call. Core
requires complete typed verdicts and inspectable request/candidate/body bridges;
a positive whole-answer verdict cannot replace those bridges. This module does
not publish, route, retry, invoke a model, or grant source authority.
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
import json
import re

from research.public_claim_obligations import admitted_body_sources


_REQUEST = re.compile(
    r"\b(?:why\s+(?:does|do|did|is|are|was|were|can|could|would|has|have|had|will)|"
    r"what\s+(?:causes?|caused|makes?|made|explains?)|explain(?:\s+(?:why|how))?|"
    r"(?:the|a)\s+(?:cause|reason)\s+(?:of|for|behind))\b", re.I,
)
_DIRECT = re.compile(r"\b(?:causes?|caused|produces?|produced|creates?|created|generates?|"
                     r"generated|triggers?|triggered|leads?\s+to|results?\s+in|makes?|made)\b", re.I)
_CONDITION = re.compile(r"\b(?:when|whenever|while|with|under)\b", re.I)
_PURPOSE_REQUEST = re.compile(r"\b(?:needs?|requires?)\b", re.I)
_PURPOSE_REVERSE_REQUEST = re.compile(
    r"^(?P<requirement>.+?)\s+(?:(?:is|are|was|were)\s+)?"
    r"(?:necessary|required|needed)\s+(?:for|by)\s+(?P<subject>.+)$", re.I,
)
_RELATION = re.compile(
    r"\b(?:because|causes?|caused|produces?|produced|creates?|created|generates?|generated|"
    r"triggers?|triggered|makes?|made|explains?|explained|therefore|consequently|"
    r"leads?\s+to|results?\s+in|due\s+to|as\s+a\s+result|is\s+why|so\s+(?:it|this|that|the))\b",
    re.I,
)
_STOP = frozenset({"a", "an", "the", "my", "your", "our", "their", "its", "this", "that", "these", "those",
                   "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "can", "could",
                   "would", "will", "has", "have", "had", "on", "off", "in", "at", "of", "to", "for", "and",
                   "or", "when", "while", "with", "under", "why", "how", "please", "happen", "happens", "happened",
                   "occur", "occurs", "occurred", "appear", "appears", "appeared"})
_REFERENCE = re.compile(r"^(?:it|this|that|these|those|they|its|their)(?:\s+(?:behavio[u]?r|effect|"
                        r"process|mechanism|feature|condition|symptom|result|change|setting|mode))?$", re.I)
_LIMITATION = re.compile(
    r"^(?:I\s+(?:(?:can(?:not|\s+not)|can['’]t|could\s+not|couldn['’]t|do\s+not|don['’]t|"
    r"am\s+unable\s+to)\s+(?:verify|determine|establish|confirm|explain|tell|know)|"
    r"(?:do\s+not|don['’]t)\s+know)|"
    r"(?:the\s+)?(?:available|retained|readable|public)\s+(?:evidence|sources?)\s+"
    r"(?:does\s+not|do\s+not|doesn['’]t|don['’]t|cannot|can['’]t)\s+"
    r"(?:establish|explain|verify|determine|confirm))\b", re.I,
)
_REFUSAL_TAIL = re.compile(
    r"^(?:so\s+)?I\s+(?:will\s+not|won['’]t|am\s+not\s+going\s+to)\s+"
    r"(?:guess|invent(?:\s+(?:the|an|a)\s+answer)?|make\s+up\s+(?:the|an|a)\s+answer)[.!]?$", re.I,
)
_FIELDS = frozenset({"index", "outcome", "mechanism_bound", "effect_bound", "relationship_answered",
                     "mechanism_quote", "effect_quote", "answer_quote", "source_id", "source_quote"})


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().strip("?!.").strip()


def _atoms(value):
    """Literal anchors plus inflection only; no topic ontology or synonyms."""
    groups = []
    for original in re.findall(r"[A-Za-z][A-Za-z0-9'’\-]*|\d+", str(value or "")):
        word = original.casefold().replace("’", "'")
        if len(original) == 1 and original.isupper():
            groups.append(frozenset({"label:" + word}))
            continue
        if word in _STOP:
            continue
        variants = {word}
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            variants.add(word[:-1])
        if len(word) > 4 and word.endswith(("ses", "shes", "ches", "xes", "zes")):
            variants.add(word[:-2])
        if len(word) > 5 and word.endswith("ies"):
            variants.add(word[:-3] + "y")
        if len(word) > 5 and word.endswith("ing"):
            stem = word[:-3]
            if len(stem) > 2 and stem[-1] == stem[-2]:
                stem = stem[:-1]
            variants.update({stem, stem + "e"})
        if len(word) > 4 and word.endswith("ed"):
            variants.update({word[:-2], word[:-1]})
        groups.append(frozenset(variants))
    return tuple(groups)


def _covers(wanted, offered):
    required, available = _atoms(wanted), _atoms(offered)
    return bool(required) and all(any(group & other for other in available) for group in required)


def _literal_contains(text, quote):
    """A literal span cannot begin/end in the middle of another word."""
    if not isinstance(quote, str) or not quote:
        return False
    left = r"(?<!\w)" if quote[0].isalnum() or quote[0] == "_" else ""
    right = r"(?!\w)" if quote[-1].isalnum() or quote[-1] == "_" else ""
    return bool(re.search(left + re.escape(quote) + right, str(text)))


def explanation_target_obligations(user_input):
    """Project exact request-side roles without supplying a cause or evidence."""
    value = str(user_input or "")
    obligations = []
    # Question/sentence boundaries keep independently requested explanations
    # separate. Prefix conversation markers remain outside the request span.
    for part in re.finditer(r"[^.!?\n]+[.!?]?", value):
        text = part.group()
        marker = _REQUEST.search(text)
        if marker is None:
            continue
        request = text[marker.start():].strip()
        prefix = marker.group().casefold()
        payload = _clean(text[marker.end():])
        mechanism, effect = None, payload
        relation_type = "causal_effect"
        direct = _DIRECT.search(payload)
        condition = _CONDITION.search(payload)
        purpose = _PURPOSE_REQUEST.search(payload)
        reverse_purpose = _PURPOSE_REVERSE_REQUEST.fullmatch(payload)
        purpose_request = bool(not prefix.startswith("what ")
                               and (reverse_purpose or purpose and purpose.start() > 0
                                    and not (direct and direct.start() < purpose.start())
                                    and not (condition and condition.start() < purpose.start())))
        if prefix.startswith("explain"):
            # Definitions and instructions are not causal requests. The older
            # producer's generic explanation/completion guards still apply.
            # Project only a relationship explicitly present in this request.
            if (prefix.endswith("how") and re.match(r"^to\b", payload, re.I)):
                continue
            if (not prefix.endswith("why") and not direct and not condition and not purpose and not reverse_purpose
                    and not re.search(r"\b(?:cause|reason|why)\b", payload, re.I)):
                continue
        if purpose_request and reverse_purpose:
            mechanism = _clean(reverse_purpose.group("subject"))
            effect = _clean(reverse_purpose.group("requirement"))
            relation_type = "purpose_or_necessity"
        elif purpose_request and purpose and _clean(payload[purpose.end():]):
            mechanism, effect = _clean(payload[:purpose.start()]), _clean(payload[purpose.end():])
            relation_type = "purpose_or_necessity"
        elif direct and direct.start() > 0 and _clean(payload[direct.end():]):
            mechanism, effect = _clean(payload[:direct.start()]), _clean(payload[direct.end():])
        elif condition and condition.start() > 0 and _clean(payload[condition.end():]):
            effect, mechanism = _clean(payload[:condition.start()]), _clean(payload[condition.end():])
            relation_type = "condition_effect"
        elif prefix.startswith("what "):
            # Unknown cause is not fabricated as a named mechanism.
            effect = payload
        if not effect:
            effect = _clean(request)
        if mechanism and not _atoms(mechanism):
            mechanism = None
        obligations.append({
            "index": len(obligations) + 1,
            "request_span": request,
            "request_start": part.start() + marker.start(),
            "request_end": part.start() + marker.start() + len(request),
            "mechanism": mechanism,
            "effect": effect,
            "mechanism_span": mechanism,
            "effect_span": effect,
            "relation_type": relation_type,
        })
    return tuple(obligations)


def explanation_target_schema(base_schema):
    result = copy.deepcopy(base_schema)
    result["properties"]["explanation_target_assessments"] = {
        "type": "array", "items": {
            "type": "object", "properties": {
                "index": {"type": "integer", "minimum": 1},
                "outcome": {"type": "string", "enum": ["factual_explanation", "bounded_limitation", "incomplete"]},
                "mechanism_bound": {"type": "boolean"},
                "effect_bound": {"type": "boolean"},
                "relationship_answered": {"type": "boolean"},
                **{key: {"type": ["string", "null"]} for key in
                   ("mechanism_quote", "effect_quote", "answer_quote", "source_id", "source_quote")},
            }, "required": sorted(_FIELDS), "additionalProperties": False,
        },
    }
    result["required"].append("explanation_target_assessments")
    return result


def explanation_target_instruction(obligations, packet):
    return (
        "\nCORE REQUESTED EXPLANATION TARGETS:\n"
        "Core independently projected these request-side obligations. Return exactly one "
        "explanation_target_assessment for each, even when all sentences are supported. "
        "A positive global support/completion verdict cannot erase a missing mechanism, effect "
        "or requested relationship. Advice, adjacent system behaviour, numeric examples and a "
        "generic causal marker are insufficient. mechanism_quote/effect_quote must be distinct "
        "literal bounded target/reference spans from the candidate; answer_quote is the literal "
        "candidate explanatory proposition. Use null mechanism_quote when Core has no named "
        "mechanism. A factual_explanation requires all three booleans true and one admitted "
        "source_id with a literal source_quote (at most 800 characters) proving the SAME requested "
        "mechanism/effect relationship. Titles, snippets, model memory and candidate prose are "
        "not body evidence. Preserve target roles; source overlap alone is insufficient. "
        "A paraphrase needs an inspectable body bridge, including an explicit source alias where "
        "its terms differ; do not guess synonyms. A pronoun must have an unambiguous inspected "
        "antecedent. An ambiguous reference is incomplete. Bounded_limitation requires a truthful "
        "target-specific limitation, all three booleans true, literal candidate quotes and null "
        "source_id/source_quote. Deleted draft text cannot supply an antecedent for a subset. "
        "If a required target or relationship is absent, use incomplete and false flags.\n"
        "For relation_type=purpose_or_necessity, the existing mechanism fields bind the requested "
        "subject/beneficiary and effect fields bind its requirement, NOT a cause and symptom. "
        "The answer/body must establish what that requirement enables, achieves or is needed for "
        "that subject. It need not repeat need/require: allows/lets/enables, uses-to, required-so-that, "
        "and an explicit establishes/ensures-for relationship can answer the same purpose. Mere "
        "use, existence, message count or both-name overlap cannot. Preserve beneficiary direction "
        "and polarity. A source-written full name/abbreviation pair establishes identity within "
        "that same readable source even when the definition is outside the selected content "
        "unit; it does not establish a missing function. An adjacent 'A uses B. B establishes "
        "state' pair may carry one purpose relationship: select the complete surviving candidate "
        "pair and an actual contiguous body pair proving it, not a deleted antecedent or a "
        "function with a different beneficiary. A clear request-bound pronoun is permitted; "
        "an ambiguous one is incomplete. For purpose questions, relationship_answered concerns "
        "the explained function for the requested subject, not an invented assertion that the "
        "requirement is the only possible mechanism in every situation. Return the SAME strict "
        "assessment fields for every relation type.\n"
        + json.dumps(tuple(obligations), ensure_ascii=False)
        + "\nADMITTED READABLE BODY SOURCE IDENTIFIERS: "
        + json.dumps(tuple(admitted_body_sources(packet)), ensure_ascii=False)
    )


_WITNESS_PREFIX = "@core-witness:"
_WITNESS_JSON_BUDGET = 18000


def _bounded_witness_catalog(catalog):
    """Bound serialized prompt data by omitting whole transport choices only."""
    if len(json.dumps(catalog, ensure_ascii=False)) <= _WITNESS_JSON_BUDGET:
        return catalog
    catalog["truncated"] = True
    size = len(json.dumps(catalog, ensure_ascii=False))
    # Prefer retaining the first request and its first candidate/source units.
    # Removed entries never turn into shortened or fabricated witness strings.
    mappings = [target[field] for target in reversed(tuple(catalog["targets"].values()))
                for field in ("answer_quote", "mechanism_quote", "effect_quote")]
    mappings.append(catalog["body"])
    for choices in mappings:
        for reference in reversed(tuple(choices)):
            if size <= _WITNESS_JSON_BUDGET:
                return catalog
            removed_size = len(json.dumps({reference: choices[reference]}, ensure_ascii=False)) - 2
            if len(choices) > 1:
                removed_size += 2  # The removed comma and separating space.
            del choices[reference]
            size -= removed_size
    return catalog


def _literal_role_spans(target, sentence, source_body):
    """Select literal nominal/reference spans, without deciding entailment."""
    words = list(re.finditer(r"[A-Za-z][A-Za-z0-9'’\-]*|\d+", sentence))
    aliases = _aliases(source_body)

    def bound(value):
        return _covers(target, value) or any(
            (_covers(target, left) and _covers(right, value))
            or (_covers(target, right) and _covers(left, value))
            for left, right in aliases
        )

    spans = []
    for start in range(len(words)):
        for end in range(start + 1, min(len(words), start + 12) + 1):
            value = sentence[words[start].start():words[end - 1].end()]
            if not bound(value):
                continue
            # The first matching end is a minimal whole-word span from this
            # position; larger continuations must not become nominal roles.
            spans.append(value)
            break
    spans = [value for value in spans
             if not any(value != other and len(other) < len(value)
                        and _literal_contains(value, other) for other in spans)]
    for match in re.finditer(r"\b(?:it|this|that|these|those|they|its|their)"
                             r"(?:\s+(?:behavio[u]?r|effect|process|mechanism|feature|condition|"
                             r"symptom|result|change|setting|mode))?\b", sentence, re.I):
        spans.append(match.group())
    return tuple(dict.fromkeys(value for value in spans if len(value) <= 800))


def public_witness_catalog(obligations, sentences, packet):
    """Core-owned literal transport choices for the existing verifier call.

    Catalog entries copy only actual candidate spans or admitted readable body
    units. They are transport references, never semantic verdicts. In
    particular candidate entries supply no evidence for themselves. Oversized
    units are omitted whole; no truncation can masquerade as a literal unit.
    """
    result = {"version": 1, "targets": {}, "body": {}, "truncated": False}
    if not isinstance(sentences, (list, tuple)) or any(not isinstance(s, str) for s in sentences):
        return result
    sources = admitted_body_sources(packet)
    # A local adjacent pair may retain an explicit alias followed by its
    # functional proposition. Never invent a cross-source alias or bridge.
    body_characters = 0
    source_bodies = []
    for source_number, (source_id, source) in enumerate(sources.items(), 1):
        body = source["content_excerpt"]
        source_bodies.append(body)
        units = tuple(match for match in re.finditer(r"\S(?:.*?)(?=(?:(?<=[.!?])\s+)|\n+|$)", body)
                      if match.group().strip())
        choices = [unit.group().strip() for unit in units]
        # A usage statement and its function can be separate adjacent
        # sentences. Preserve their actual contiguous source span instead of
        # asking the model to combine/rewrite them into a fabricated quote.
        choices.extend(body[left.start():right.end()]
                       for left, right in zip(units, units[1:]))
        for unit_number, unit in enumerate(dict.fromkeys(choices), 1):
            if not unit or len(unit) > 800:
                result["truncated"] = True
                continue
            if len(result["body"]) >= 64 or body_characters + len(unit) > 10000:
                result["truncated"] = True
                break
            reference = f"{_WITNESS_PREFIX}b{source_number}:{unit_number}"
            result["body"][reference] = {"source_id": source_id, "literal": unit}
            body_characters += len(unit)
    literal_units = [sentence.strip() for sentence in sentences if sentence.strip()]
    candidate_units = tuple(dict.fromkeys(unit for unit in (
        *literal_units, *(left + " " + right for left, right in zip(literal_units, literal_units[1:])))
        if len(unit) <= 800))
    if len(candidate_units) > 32:
        result["truncated"] = True
        candidate_units = candidate_units[:32]
    for position, obligation in enumerate(obligations):
        if position >= 16:
            result["truncated"] = True
            break
        if not isinstance(obligation, Mapping) or type(obligation.get("index")) is not int:
            continue
        index = obligation["index"]
        choices = {"mechanism_quote": {}, "effect_quote": {}, "answer_quote": {}}
        for field, role in (("mechanism_quote", obligation.get("mechanism")),
                            ("effect_quote", obligation.get("effect"))):
            if not role:
                continue
            spans = tuple(dict.fromkeys(span for sentence in candidate_units
                                         for source_body in source_bodies or ("",)
                                         for span in _literal_role_spans(role, sentence, source_body)))
            if len(spans) > 32:
                result["truncated"] = True
            for span_number, span in enumerate(spans[:32], 1):
                reference = f"{_WITNESS_PREFIX}t{index}:{field}:{span_number}"
                choices[field][reference] = span
        for unit_number, unit in enumerate(candidate_units, 1):
            choices["answer_quote"][f"{_WITNESS_PREFIX}t{index}:answer_quote:{unit_number}"] = unit
        result["targets"][index] = choices
    return _bounded_witness_catalog(result)


def public_witness_schema(base_schema, catalog):
    """Constrain freehand copying to literal Core references, not truth flags."""
    schema = copy.deepcopy(base_schema)
    properties = schema.get("properties", {})
    target_item = properties.get("explanation_target_assessments", {}).get("items", {}).get("properties", {})
    for field in ("mechanism_quote", "effect_quote", "answer_quote"):
        if field in target_item:
            references = [reference for target in catalog.get("targets", {}).values()
                          for reference in target.get(field, {})]
            target_item[field] = {"type": ["string", "null"], "enum": [None, *references]}
    for array in ("claim_assessments", "explanation_target_assessments"):
        fields = properties.get(array, {}).get("items", {}).get("properties", {})
        if "source_quote" in fields:
            fields["source_quote"] = {"type": ["string", "null"], "enum": [None, *catalog.get("body", {})]}
            if "source_id" in fields:
                identities = tuple(dict.fromkeys(item["source_id"] for item in catalog.get("body", {}).values()))
                fields["source_id"] = {"type": ["string", "null"], "enum": [None, *identities]}
    return schema


def public_witness_instruction(catalog):
    return (
        "\nCORE LITERAL WITNESS TRANSPORT:\n"
        "For this response the quote fields use the catalog reference strings below, NOT freehand "
        "quotations or paraphrases. This changes serialization only: all support, role, polarity, "
        "relationship and source decisions remain independently required. Choose a target's own "
        "mechanism_quote/effect_quote/answer_quote reference in its matching field. Choose a body "
        "reference only with its actual source_id. Core resolves references to the unchanged literal "
        "text before checking them. Candidate catalog text is proposed prose, NEVER evidence. Body "
        "choices come only from admitted readable source content; a shared topic is insufficient. "
        "If no choice proves the requested relationship, mark the assessment incomplete/unsupported "
        "with the appropriate false flags and null witnesses. Do not fill a missing witness from "
        "model memory. The catalog does not establish a positive verdict.\n"
        + json.dumps(catalog, ensure_ascii=False)
    )


def resolve_public_witness_refs(parsed, catalog):
    """Resolve only explicit valid references; never repair a raw bad quote.

    Missing, malformed, negative and legacy literal assessments remain intact.
    A wrong-source/target/field reference becomes an invalid typed witness and
    consequently fails existing strict aggregation, even if hostile source or
    candidate text happens to contain that reference string itself.
    """
    result = copy.deepcopy(parsed)
    if not isinstance(result, dict):
        return result
    for array in ("claim_assessments", "explanation_target_assessments"):
        assessments = result.get(array)
        if not isinstance(assessments, list):
            continue
        for item in assessments:
            if not isinstance(item, dict):
                continue
            if array == "explanation_target_assessments":
                choices = catalog.get("targets", {}).get(item.get("index"), {}) if type(item.get("index")) is int else {}
                for field in ("mechanism_quote", "effect_quote", "answer_quote"):
                    reference = item.get(field)
                    if isinstance(reference, str) and reference.startswith(_WITNESS_PREFIX):
                        literal = choices.get(field, {}).get(reference)
                        if isinstance(literal, str):
                            item[field] = literal
                        else:
                            item[field] = {"invalid_core_witness_reference": True}
            reference = item.get("source_quote")
            if isinstance(reference, str) and reference.startswith(_WITNESS_PREFIX):
                witness = catalog.get("body", {}).get(reference)
                if isinstance(witness, Mapping) and witness.get("source_id") == item.get("source_id"):
                    item["source_quote"] = witness["literal"]
                else:
                    item["source_quote"] = {"invalid_core_witness_reference": True}
    return result


def _aliases(source_quote):
    # Only literal source-established nominal aliases, not semantic synonyms.
    nominal = r"[A-Za-z][A-Za-z0-9'’\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9'’\-]*){0,7}"
    pattern = re.compile(r"(?P<a>" + nominal + r")\s+(?:is|was)\s+(?:also\s+)?"
                         r"(?:called|known\s+as|named)\s+(?P<b>" + nominal + r")", re.I)
    pairs = [(_clean(match.group("a")), _clean(match.group("b")))
             for match in pattern.finditer(source_quote)]
    # An acronym is an alias only when the retained body writes the two
    # nominal identities together. Never expand initials from model memory,
    # the USER request, candidate prose or an unrelated source title.
    parenthetic = re.compile(r"(?P<left>" + nominal + r")\s*\((?P<right>" + nominal + r")\)")
    for match in parenthetic.finditer(str(source_quote)):
        left, right = _clean(match.group("left")), _clean(match.group("right"))
        if re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", right):
            words = left.split()
            for start in range(len(words)):
                full = words[start:]
                meaningful = [word for word in full if word.casefold() not in {"a", "an", "the", "of", "for", "and"}]
                if (meaningful and (len(meaningful) > 1
                        and "".join(word[0] for word in meaningful).upper() == right
                        or len(meaningful) == 1 and len(meaningful[0]) >= 4
                        and meaningful[0].upper().startswith(right))):
                    pairs.append((" ".join(full), right))
                    break
        elif re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", left.split()[-1]):
            short = left.split()[-1]
            meaningful = [word for word in right.split() if word.casefold() not in {"a", "an", "the", "of", "for", "and"}]
            if (meaningful and (len(meaningful) > 1
                    and "".join(word[0] for word in meaningful).upper() == short
                    or len(meaningful) == 1 and len(meaningful[0]) >= 4
                    and meaningful[0].upper().startswith(short))):
                pairs.append((short, right))
    # One short identifier must not silently choose between two different
    # source-written expansions. Keep direct literal identity available, but
    # do not transport an ambiguous acronym as an unambiguous alias.
    expansions = {}
    for left, right in pairs:
        for short, full in ((left, right), (right, left)):
            if re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", short) and not re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", full):
                key = re.sub(r"^(?:the|a|an)\s+", "", _clean(full), flags=re.I).casefold()
                expansions.setdefault(short, set()).add(key)
    ambiguous = {short for short, values in expansions.items() if len(values) > 1}
    return tuple(dict.fromkeys((left, right) for left, right in pairs
                               if left not in ambiguous and right not in ambiguous))


def _role_bridge(target, quote, source_quote):
    if _covers(target, quote):
        return True
    for left, right in _aliases(source_quote):
        if ((_covers(target, left) and _covers(right, quote))
                or (_covers(target, right) and _covers(left, quote))):
            return True
    return False


def public_role_bridge(target, offered, source_quote=""):
    """Bound a Core role by literal anchors or a retained body's explicit alias.

    This recognises identities only; it supplies neither entailment nor source
    admission and cannot establish an independently asserted extra subject.
    """
    return _role_bridge(target, offered, source_quote)


def public_nominal_role_bridge(target, offered, source_body="", *, nominal_witness=None):
    """Bound a whole nominal role, including body-written refinements only."""
    value = re.sub(r"^(?:the|a|an)\s+", "", _clean(offered), flags=re.I)
    if not re.fullmatch(r"[\w'’() -]+", value) or re.search(
            r"\b(?:that|who|which|because|failed|fails|is|are|was|were|does|did)\b", value, re.I):
        return False
    if not public_role_bridge(target, value, source_body):
        return False
    if public_role_bridge(value, target, source_body):
        return True
    witness = source_body if nominal_witness is None else nominal_witness
    return _literal_contains(str(witness).casefold(), value.casefold())


def public_alias_normalize(value, source_body):
    """Normalize only explicitly body-established nominal aliases.

    This is identity transport, not entailment: source content, function,
    polarity and directional roles still require their own literal witness.
    """
    result = str(value or "")
    for left, right in sorted(_aliases(source_body), key=lambda pair: -max(map(len, pair))):
        canonical = left if len(left) >= len(right) else right
        for nominal in (left, right):
            result = re.sub(r"(?<!\w)" + re.escape(nominal) + r"(?!\w)",
                            lambda match: canonical, result, flags=re.I)
    return result


def public_reference_bridge(target, reference, other_target, sentences, *, request_antecedent=False):
    return _reference_bridge(target, reference, other_target, sentences,
                             request_antecedent=request_antecedent)


def _reference_bridge(target, quote, other_target, sentences, *, request_antecedent=False):
    if not _REFERENCE.fullmatch(_clean(quote)):
        return False
    locations = [index for index, sentence in enumerate(sentences) if _literal_contains(sentence, quote)]
    if len(locations) != 1:
        return False
    before = sentences[:locations[0]]
    if not before:
        # The single request supplies one cause and one effect. A subject
        # pronoun with the OTHER role explicitly named is unambiguous; "it
        # does that" supplies neither role and remains unproven.
        current = str(sentences[locations[0]])
        return bool(request_antecedent and other_target
                    and not re.search(r"\b(?:and|or)\b|,", str(target), re.I)
                    and _covers(other_target, current)
                    and re.match(r"^\s*" + re.escape(quote) + r"\b", current, re.I))
    # The immediately preceding inspected clause must identify only this role.
    # A source quote or earlier rejected/deleted sentence is not an antecedent.
    previous = re.split(r"[.!?;]", str(before[-1]))[-2 if str(before[-1]).endswith((".", "!", "?")) else -1]
    finite = re.search(r"\b(?:is|are|was|were|can|could|changes?|produces?|causes?|controls?|"
                       r"varies|modifies|adjusts?|sets?|affects?)\b", previous, re.I)
    if finite and re.search(r"\b(?:and|or)\b|,", previous[:finite.start()], re.I):
        return False
    return _covers(target, previous) and not (other_target and _covers(other_target, previous))


_PURPOSE_ALLOW = re.compile(r"\b(?:allows?|lets?|enables?|permits?|helps?)\b", re.I)
_PURPOSE_USE = re.compile(r"\b(?:uses?|needs?|requires?|depends?\s+on)\b", re.I)
_PURPOSE_REQUIRED = re.compile(
    r"\b(?:is|are|was|were)\s+(?:not\s+)?(?:required|necessary|needed)\s+"
    r"(?:so\s+(?:that\s+)?|in\s+order\s+that\s+)", re.I,
)
_PURPOSE_FUNCTION = re.compile(
    r"\b(?:establish(?:es|ed)?|ensur(?:e|es|ed)|synchroni[sz](?:e|es|ed))\b", re.I,
)
_PURPOSE_SYNTAX = frozenset({"it", "this", "that", "they", "them", "its", "their", "so", "because",
                            "allows", "allow", "lets", "let", "enables", "enable",
                            "permits", "permit", "helps", "help", "depends", "depend", "uses", "use", "needs", "need", "requires", "require",
                            "required", "necessary", "needed", "not", "never", "cannot", "no", "longer"})


def _purpose_negative(value):
    # Relation negation and the enabled function's negation are different
    # propositions. In particular, not allowing a negative function cannot
    # establish the corresponding positive function. "Not only" is additive,
    # not a denial of the function that follows it.
    text = re.sub(r"\bnot\s+only\b", "", str(value), flags=re.I)
    return bool(re.search(r"\b(?:not|never|cannot|unable|no\s+longer)\b|n['’]t\b", text, re.I))


def _purpose_role_bound(target, field, source_quote, sentences=(), role_quote=None, other=None,
                        request_antecedent=False, nominal_witness=None):
    nominal = re.sub(r"^(?:(?:first|second|third|finally|also|therefore|however|instead|thus)\s*,\s*)+",
                     "", str(field).strip(), flags=re.I)
    nominal = re.sub(r"\s+(?:(?:does|do|did|can|could|may|might|will|would|must)(?:\s+not)?|"
                     r"never|no\s+longer|cannot|can't|doesn't|don't|didn't)\s*$", "", nominal, flags=re.I)
    if public_nominal_role_bridge(target, nominal, source_quote, nominal_witness=nominal_witness):
        return True
    # Demonstrative nominal references retain a literal head, unlike an
    # unconstrained synonym or a bare ambiguous "it". They are resolved only
    # inside the inspected adjacent usage/function pair below.
    if _purpose_nominal_reference(target, nominal, other):
        positions = [index for index, sentence in enumerate(sentences)
                     if _literal_contains(sentence, nominal)]
        if len(positions) == 1 and positions[0] > 0:
            previous = sentences[positions[0] - 1]
            if (_purpose_usage_roles(target, other, previous, source_quote, nominal_witness=nominal_witness)
                    or _purpose_usage_roles(other, target, previous, source_quote, nominal_witness=nominal_witness)):
                return True
    if not _REFERENCE.fullmatch(_clean(nominal)):
        return False
    if role_quote is None:
        role_quote = _clean(nominal)
    return bool(role_quote and _clean(role_quote) == _clean(nominal) and _literal_contains(field, role_quote)
                and _reference_bridge(target, role_quote, other, sentences,
                                      request_antecedent=request_antecedent))


def _purpose_nominal_reference(target, nominal, other):
    match = re.fullmatch(r"(?:this|that|the|such)\s+([a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,2})",
                         _clean(nominal), re.I)
    return bool(match and _covers(match.group(1), target)
                and not (other and _covers(match.group(1), other)))


def _purpose_usage_roles(subject, requirement, unit, source_quote, *, nominal_witness=None):
    """A positive complete usage is context, never itself a purpose proof."""
    if (not subject or not requirement or unit.endswith("?") or _purpose_negative(unit)
            or re.match(r'^["“]|^(?:if|suppose|imagine)\b', unit, re.I)):
        return False
    markers = tuple(_PURPOSE_USE.finditer(unit))
    if len(markers) != 1:
        return False
    marker = markers[0]
    left, right = _clean(unit[:marker.start()]), _clean(unit[marker.end():])
    if re.search(r"\b(?:and|or)\b|,", left + " " + right, re.I):
        return False
    return (public_nominal_role_bridge(subject, left, source_quote, nominal_witness=nominal_witness)
            and public_nominal_role_bridge(requirement, right, source_quote, nominal_witness=nominal_witness))


def _purpose_prefix(target, field, source_quote, sentences=(), role_quote=None, other=None,
                    request_antecedent=False, nominal_witness=None):
    """Split an initial beneficiary from its action, never a later topic mention."""
    words = list(re.finditer(r"[A-Za-z][A-Za-z0-9'’\-]*|\d+", field))
    limit = min(len(words), max(3, len(_atoms(target)) + 3))
    for end in range(1, limit + 1):
        prefix, remainder = field[:words[end - 1].end()], field[words[end - 1].end():].strip()
        if not remainder:
            continue
        if _purpose_role_bound(target, prefix, source_quote, sentences, role_quote, other,
                               request_antecedent, nominal_witness):
            remainder = re.sub(r"^(?:to|can|could|may|might|must|will|would)\s+", "", remainder, flags=re.I)
            if re.match(r"^(?:and|or|for|by|of|in|with|from)\b", remainder, re.I):
                continue
            return remainder
    return None


def _purpose_tail_valid(value):
    # A purpose needs a function/goal, not only a named entity or connective.
    return bool(_atoms(value)) and not re.fullmatch(r"(?:it|this|that|them|they|and|or|to|for)", _clean(value), re.I)


def _purpose_units(obligation, text, source_quote="", *, sentences=(), mq=None, eq=None,
                   request_antecedent=False, nominal_witness=None):
    """Project bounded beneficiary/requirement/function roles, not entailment.

    The legacy transport names mechanism/effect denote subject/requirement here.
    The existing semantic assessment still judges whether the quoted function
    entails the answer. These shapes cannot grant authority to candidate prose.
    """
    subject, requirement = obligation.get("mechanism"), obligation.get("effect")
    if not subject or not requirement:
        return ()
    result = []

    def bound(target, value, quote, other):
        return _purpose_role_bound(target, value, source_quote, sentences, quote, other,
                                   request_antecedent, nominal_witness)

    def add(subject_part, requirement_part, tail, principal):
        if (bound(subject, subject_part, mq, requirement)
                and bound(requirement, requirement_part, eq, subject)
                and _purpose_tail_valid(tail)):
            result.append((_purpose_negative(principal), _purpose_negative(tail), tail))

    units = tuple(unit.strip() for unit in re.split(r"(?<=[.!?;])\s+|\n+", str(text)) if unit.strip())
    if not sentences:
        sentences = units

    def bare_usage(unit):
        # Only an immediately adjacent, positive, complete nominal usage
        # proposition supplies reference context. It supplies no truth: the
        # selected readable-body pair must independently prove the function.
        if unit.endswith("?") or re.match(r"^[\"“]|^(?:if|suppose|imagine)\b", unit, re.I):
            return False
        markers = tuple(_PURPOSE_USE.finditer(unit))
        if len(markers) != 1 or _purpose_negative(unit):
            return False
        marker = markers[0]
        left, right = _clean(unit[:marker.start()]), _clean(unit[marker.end():])
        return (public_nominal_role_bridge(subject, left, source_quote, nominal_witness=nominal_witness)
                and public_nominal_role_bridge(requirement, right, source_quote, nominal_witness=nominal_witness))

    for position, unit in enumerate(units):
        # Questions/quoted examples do not establish an asserted body witness.
        if unit.endswith("?") or re.match(r"^[\"“]|^(?:if|suppose|imagine)\b", unit, re.I):
            continue
        # An explicit preposed beneficiary retains the same directional roles
        # as a postposed "for A"; it is not inferred from topic overlap.
        preposed = re.match(r"^For\s+([^,;.!?]+),\s+(.+)$", unit, re.I)
        if preposed:
            beneficiary, remainder = preposed.groups()
            for marker in _PURPOSE_FUNCTION.finditer(remainder):
                add(beneficiary, remainder[:marker.start()],
                    marker.group() + " " + remainder[marker.end():], remainder[:marker.start()])
        for marker in _PURPOSE_ALLOW.finditer(unit):
            requirement_part, rest = unit[:marker.start()], unit[marker.end():].strip()
            tail = _purpose_prefix(subject, rest, source_quote, sentences, mq, requirement,
                                   request_antecedent, nominal_witness)
            if tail is not None:
                # The prefix split already binds the beneficiary. The left
                # region, independently, must bind the actual requirement.
                add(subject, requirement_part, tail, requirement_part)
        for marker in _PURPOSE_USE.finditer(unit):
            subject_part, rest = unit[:marker.start()], unit[marker.end():].strip()
            separator = re.search(r"\b(?:because|so\s+(?:that\s+)?|in\s+order\s+to|to|for)\b", rest, re.I)
            if separator:
                add(subject_part, rest[:separator.start()], rest[separator.end():], subject_part)
        for marker in _PURPOSE_REQUIRED.finditer(unit):
            requirement_part, rest = unit[:marker.start()], unit[marker.end():].strip()
            tail = _purpose_prefix(subject, rest, source_quote, sentences, mq, requirement,
                                   request_antecedent, nominal_witness)
            if tail is not None:
                add(subject, requirement_part, tail, unit[:marker.end()])
        for marker in _PURPOSE_FUNCTION.finditer(unit):
            requirement_part, rest = unit[:marker.start()], unit[marker.end():].strip()
            separator = re.search(r"\bfor\b", rest, re.I)
            if separator:
                add(rest[separator.end():], requirement_part,
                    marker.group() + " " + rest[:separator.start()], requirement_part)
            else:
                rest = re.sub(r"^that\s+", "", rest, flags=re.I)
                tail = _purpose_prefix(subject, rest, source_quote, sentences, mq, requirement,
                                       request_antecedent, nominal_witness)
                if tail is not None:
                    add(subject, requirement_part, marker.group() + " " + tail, requirement_part)
                else:
                    previous = units[position - 1] if position else None
                    if previous is None:
                        locations = [index for index, sentence in enumerate(sentences) if sentence == unit]
                        if len(locations) == 1 and locations[0] > 0:
                            previous = sentences[locations[0] - 1]
                    # 'A uses B. B establishes state.' is one bounded purpose
                    # explanation when both sentences survive. Neither a
                    # removed antecedent nor an unrelated preceding subject
                    # can establish this binding.
                    if previous is not None and bare_usage(previous):
                        add(subject, requirement_part, marker.group() + " " + rest, requirement_part)
    return tuple(result)


def _purpose_function_bridge(obligation, wanted, offered, source_quote=""):
    # Retain literal function anchors and inflection; ignore only relation
    # scaffolding and the already checked nominal roles. No ontology/synonyms.
    roles = (obligation.get("mechanism"), obligation.get("effect"))
    role_groups = _atoms(roles[0]) + _atoms(roles[1])
    for left, right in _aliases(source_quote):
        if any(_covers(role, left) or _covers(role, right) for role in roles if role):
            role_groups += _atoms(left) + _atoms(right)
    def function_atoms(value):
        result = []
        for group in _atoms(re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", str(value))):
            variants = set(group)
            for word in group:
                if len(word) > 8 and word.endswith("ment"):
                    variants.add(word[:-4])
                if len(word) > 9 and word.endswith(("ization", "isation")):
                    variants.update({word[:-7] + "ize", word[:-7] + "ise"})
                if len(word) > 7 and word.endswith("ation"):
                    variants.add(word[:-5] + "ate")
                if len(word) > 7 and word.endswith("ction"):
                    variants.add(word[:-3])
            result.append(frozenset(variants))
        return tuple(result)
    groups = tuple(group for group in function_atoms(wanted)
                   if not group & _PURPOSE_SYNTAX and not any(group & role for role in role_groups))
    available = function_atoms(offered)
    return bool(groups) and all(any(group & other for other in available) for group in groups)


def canonical_purpose_witness(obligation, selected_quote, source_body):
    """Retain the smallest complete *literal* source-local purpose context.

    A verifier's selected sentence can omit an immediate usage antecedent or
    include an unrelated neighbouring assertion. Neither transport choice
    changes the scoped purpose proposition. Core may inspect actual contiguous
    body units; it may not supply an alias, beneficiary, function or truth from
    the proposed answer. Ambiguous/missing context leaves the original witness
    untouched so the ordinary strict validators fail closed.
    """
    if (not isinstance(obligation, Mapping)
            or obligation.get("relation_type") != "purpose_or_necessity"
            or not isinstance(selected_quote, str) or not isinstance(source_body, str)
            or not _literal_contains(source_body, selected_quote)):
        return selected_quote
    selected_units = tuple(match.group().strip() for match in re.finditer(
        r"\S(?:.*?)(?=(?:(?<=[.!?;])\s+)|\n+|$)", selected_quote) if match.group().strip())
    if len(selected_units) > 1:
        complete = [unit for unit in selected_units
                    if _purpose_units(obligation, unit, source_body, nominal_witness=unit)]
        other_markers = [unit for unit in selected_units if unit not in complete and
                         (_PURPOSE_ALLOW.search(unit) or _PURPOSE_USE.search(unit)
                          or _PURPOSE_REQUIRED.search(unit) or _PURPOSE_FUNCTION.search(unit))]
        if len(complete) == 1 and not other_markers:
            return complete[0]
        return selected_quote
    units = tuple(match for match in re.finditer(
        r"\S(?:.*?)(?=(?:(?<=[.!?;])\s+)|\n+|$)", source_body) if match.group().strip())
    locations = [index for index, match in enumerate(units) if match.group().strip() == selected_quote.strip()]
    if len(locations) != 1 or locations[0] == 0 or not _PURPOSE_FUNCTION.search(selected_quote):
        return selected_quote
    index = locations[0]
    previous = units[index - 1].group().strip()
    markers = tuple(_PURPOSE_USE.finditer(previous))
    if (len(markers) != 1 or _purpose_negative(previous) or previous.endswith("?")
            or re.match(r"^[\"“]|^(?:if|suppose|imagine)\b", previous, re.I)):
        return selected_quote
    marker = markers[0]
    if not (public_nominal_role_bridge(obligation.get("mechanism"), _clean(previous[:marker.start()]), source_body,
                                       nominal_witness=previous)
            and public_nominal_role_bridge(obligation.get("effect"), _clean(previous[marker.end():]), source_body,
                                           nominal_witness=previous)):
        return selected_quote
    pair = source_body[units[index - 1].start():units[index].end()]
    return (pair if len(pair) <= 800 and _purpose_units(obligation, pair, source_body, nominal_witness=pair)
            else selected_quote)


def purpose_candidate_bound(obligation, candidate, source_quote="", *, sentences=(), request_antecedent=False):
    """Candidate-only shape projection; it asserts no source or truth authority."""
    return bool(isinstance(obligation, Mapping)
                and obligation.get("relation_type") == "purpose_or_necessity"
                and _purpose_units(obligation, candidate, source_quote, sentences=sentences,
                                   request_antecedent=request_antecedent))


def _purpose_pair_issue(obligation, candidate, source_quote, *, sentences=(), mq=None, eq=None,
                        request_antecedent=False, source_context=None):
    if not isinstance(obligation, Mapping) or obligation.get("relation_type") != "purpose_or_necessity":
        return "purpose_target_missing"
    identity_context = source_context if isinstance(source_context, str) else source_quote
    source_units = _purpose_units(obligation, source_quote, identity_context, nominal_witness=source_quote)
    if not source_units:
        return "purpose_source_relationship_unbound"
    candidate_units = _purpose_units(obligation, candidate, identity_context, sentences=sentences,
                                    mq=mq, eq=eq, request_antecedent=request_antecedent,
                                    nominal_witness=source_quote)
    if not candidate_units:
        return "purpose_candidate_relationship_unbound"
    if not any(cp == sp for cp, _, _ in candidate_units for sp, _, _ in source_units):
        return "purpose_relationship_polarity_mismatch"
    if not any((cp, cf) == (sp, sf)
               for cp, cf, _ in candidate_units for sp, sf, _ in source_units):
        return "purpose_function_polarity_mismatch"
    if not any((cp, cf) == (sp, sf) and _purpose_function_bridge(obligation, tail, source_tail, identity_context)
               for cp, cf, tail in candidate_units for sp, sf, source_tail in source_units):
        return "purpose_function_witness_mismatch"
    return None


def purpose_claim_witness_issue(obligation, candidate, source_quote, *, source_context=None,
                                sentences=(), request_antecedent=False):
    """Shared content validator for a Core-requested purpose proposition."""
    return _purpose_pair_issue(obligation, candidate, source_quote, source_context=source_context,
                               sentences=sentences, request_antecedent=request_antecedent)


def _relationship_unit_bound(obligation, text, source_quote, *, sentences=(), mq=None, eq=None, negative=False,
                             request_antecedent=False):
    """Bind both roles to one causal clause, not unrelated paragraph mentions."""
    mechanism, effect = obligation.get("mechanism"), obligation.get("effect")
    units = [unit.strip() for unit in re.split(r"(?<=[.!?;])\s+|\n+", text) if unit.strip()]
    for unit in units:
        for marker in _RELATION.finditer(unit):
            left, right = unit[:marker.start()], unit[marker.end():]
            # A supported denial may correct the request's false premise; it
            # must not support the positive relation (or vice versa).
            negated = bool(re.search(r"\b(?:not|never|no|cannot|unable)\b|n['’]t\b", left[-64:], re.I))
            if negated != negative:
                continue
            relation = marker.group().casefold()
            reverse = relation in {"because", "due to"}
            if relation in {"cause", "causes", "caused"} and re.match(r"\s+by\b", right, re.I):
                reverse = True
                right = re.sub(r"^\s+by\s+", "", right, flags=re.I)
            mechanism_side, effect_side = (right, left) if reverse else (left, right)
            effect_ok = _role_bridge(effect, effect_side, source_quote)
            if not effect_ok and eq and _literal_contains(effect_side, eq):
                effect_ok = _reference_bridge(effect, eq, mechanism, sentences, request_antecedent=request_antecedent)
            mechanism_ok = not mechanism or _role_bridge(mechanism, mechanism_side, source_quote)
            if not mechanism_ok and mq and _literal_contains(mechanism_side, mq):
                mechanism_ok = _reference_bridge(mechanism, mq, effect, sentences, request_antecedent=request_antecedent)
            if mechanism_ok and effect_ok:
                return True
    return False


def _condition_state_conflict(target, text):
    """Preserve an explicitly requested on/off condition without an ontology."""
    expected = re.search(r"\b(?:is|are|was|were|be|being)\s+(on|off)\b", str(target or ""), re.I)
    if expected is None:
        return False
    subject = str(target)[:expected.start()]
    for clause in re.split(r"[.!?;,]|\b(?:but|while|whereas)\b", str(text), flags=re.I):
        for state in re.finditer(r"\b(?:is|are|was|were|be|being)\s+(on|off)\b", clause, re.I):
            if (_covers(subject, clause[:state.start()])
                    and state.group(1).casefold() != expected.group(1).casefold()):
                return True
    return False


def explanation_limitation_complete(obligations, sentences):
    """Transparent target-specific limitations need no annotation to be safe."""
    if not obligations or not isinstance(sentences, (list, tuple)) or not sentences:
        return False
    limitations, scaffolds = [], []
    for sentence in sentences:
        text = str(sentence or "").strip()
        # These independently verified sentences can establish a reference,
        # never a cause. No arbitrary declarative factual tail is exempted.
        citation = re.fullmatch(r"(?:Here(?:['’]s|\s+is)\s+(?:the\s+)?(?:official\s+)?source|"
                                r"(?:The\s+)?(?:official\s+)?source\s+is)\s*:?[ \t]+https?://\S+[.!]?", text, re.I)
        identity = re.fullmatch(r"(?:The|This|That|A|An)\s+[^.!?;]{1,80}\s+(?:is|was)\s+"
                                r"(?:called|titled|named)\s+[^.!?;]{1,160}[.!]?", text, re.I)
        if citation or identity:
            scaffolds.append(text)
            continue
        # A first-person limitation prefix must not hide another proposition
        # behind punctuation. Each independently phrased continuation must
        # itself remain a limitation or a bounded refusal to invent an answer.
        clauses = [clause.strip() for clause in re.split(r"[;,]", text) if clause.strip()]
        if any(not (_LIMITATION.search(clause) or _REFUSAL_TAIL.fullmatch(clause))
               for clause in clauses[1:]):
            return False
        if (not _LIMITATION.search(text) or re.search(r"\d|\b(?:but|however|because|therefore|consequently)\b", text, re.I)
                or re.search(r"\band\s+(?:it|they|the|this|that|your|you)\b", text, re.I)):
            return False
        limitations.append(text)
    if not limitations:
        return False
    for obligation in obligations:
        effect = obligation.get("effect")
        mechanism = obligation.get("mechanism")
        if not any((_covers(effect, text) or (scaffolds and re.search(r"\b(?:it|this|that)\b", text, re.I)
                   and _covers(effect, " ".join(scaffolds + [text]))))
                   and (not mechanism or _covers(mechanism, text)
                   or re.search(r"\b(?:why|cause|reason|explanation|mechanism)\b", text, re.I))
                   for text in limitations):
            return False
    return True


def explanation_literal_target_complete(obligations, sentences, packet):
    """A concrete unknown-cause request may have a complete literal body proof.

    Unlike semantic annotation, this proof performs no target inference,
    paraphrase mapping, pronoun resolution or supplied-mechanism substitution.
    Every retained sentence must be a whole admitted readable body unit. Each
    requested effect/predicate must occur on the correct side of an asserted
    causal clause. Paired mechanism/effect requests ALWAYS retain the strict
    target-assessment protocol, even if their prose is copied from a source.
    The ordinary global/sentence/source verifier remains independently required.
    """
    if (not obligations or any(item.get("mechanism") is not None for item in obligations)
            or not isinstance(sentences, (list, tuple)) or not sentences
            or any(not isinstance(sentence, str) or not sentence.strip() for sentence in sentences)):
        return False
    sources = admitted_body_sources(packet)
    body_units = {unit.strip() for source in sources.values()
                  for unit in re.split(r"(?<=[.!?])\s+|\n+", source["content_excerpt"])
                  if unit.strip()}
    # Candidate prose supplies no truth: the complete literal units must exist
    # independently in admitted evidence. Metadata and partial quotations do
    # not establish this proof.
    if any(sentence.strip() not in body_units for sentence in sentences):
        return False
    for obligation in obligations:
        effect = str(obligation.get("effect") or "")
        if re.search(r"\b(?:it|they|he|she|this|that|these|those)\b", effect, re.I):
            return False
        if not any(
            not re.search(r"[\"“”]|\b(?:if|when|whenever|while|suppose|imagine|may|might|can|could|"
                          r"would|possibly|perhaps|probably|hypothetically)\b", sentence, re.I)
            and _relationship_unit_bound(obligation, sentence, sentence)
            for sentence in sentences
        ):
            return False
    return True


def explanation_target_failures(obligations, raw_assessments, sentences, packet):
    """Strict typed aggregation; return safe codes, never candidate/source prose."""
    if not obligations:
        return []
    if not isinstance(raw_assessments, list):
        return ["missing_explanation_target_assessments"]
    assessments = {}
    for item in raw_assessments:
        if (not isinstance(item, Mapping) or set(item) != _FIELDS
                or type(item.get("index")) is not int or not 1 <= item["index"] <= len(obligations)
                or item["index"] in assessments
                or item.get("outcome") not in {"factual_explanation", "bounded_limitation", "incomplete"}
                or any(type(item.get(key)) is not bool for key in
                       ("mechanism_bound", "effect_bound", "relationship_answered"))
                or any(item.get(key) is not None and not isinstance(item[key], str)
                       for key in ("mechanism_quote", "effect_quote", "answer_quote", "source_id", "source_quote"))):
            return ["invalid_explanation_target_assessments"]
        assessments[item["index"]] = item
    if set(assessments) != set(range(1, len(obligations) + 1)):
        return ["incomplete_explanation_target_assessments"]
    if not isinstance(sentences, (list, tuple)) or not sentences or any(not isinstance(s, str) for s in sentences):
        return ["invalid_explanation_candidate_units"]
    candidate = " ".join(sentences)
    sources = admitted_body_sources(packet)
    failures = []
    for obligation in obligations:
        item = assessments[obligation["index"]]
        if item["outcome"] == "incomplete" or not all(item[key] for key in
                 ("mechanism_bound", "effect_bound", "relationship_answered")):
            failures.append("explanation_target_unfulfilled")
            continue
        mechanism, effect = obligation.get("mechanism"), obligation.get("effect")
        mq, eq, aq = item["mechanism_quote"], item["effect_quote"], item["answer_quote"]
        required = (eq, aq) + ((mq,) if mechanism else ())
        if (any(not isinstance(quote, str) or not quote.strip() or len(quote) > 800 or not _literal_contains(candidate, quote)
                for quote in required) or not mechanism and mq is not None):
            failures.append("invalid_explanation_candidate_witness")
            continue
        if mechanism and _clean(mq).casefold() == _clean(eq).casefold():
            failures.append("explanation_target_roles_not_distinct")
            continue
        if item["outcome"] == "bounded_limitation":
            if (item["source_id"] is not None or item["source_quote"] is not None
                    or not explanation_limitation_complete((obligation,), sentences)):
                failures.append("explanation_limitation_not_targeted")
            continue
        source = sources.get(item["source_id"]) if isinstance(item["source_id"], str) else None
        sq = item["source_quote"]
        if (source is None or not isinstance(sq, str) or not sq.strip() or len(sq) > 800
                or not _literal_contains(source["content_excerpt"], sq)):
            failures.append("missing_explanation_body_witness")
            continue
        # Aliases are identity evidence from this same admitted source, not
        # a requirement to duplicate their definition inside every content
        # quotation. The literal quote still has to prove the relationship.
        identity_context = source["content_excerpt"]
        if obligation.get("relation_type") == "purpose_or_necessity":
            sq = canonical_purpose_witness(obligation, sq, identity_context)
        if not _role_bridge(effect, sq, identity_context) or mechanism and not _role_bridge(mechanism, sq, identity_context):
            failures.append("explanation_source_target_mismatch")
            continue
        if mechanism and (_condition_state_conflict(mechanism, sq) or _condition_state_conflict(mechanism, candidate)):
            failures.append("explanation_condition_scope_mismatch")
            continue
        if obligation.get("relation_type") == "purpose_or_necessity":
            issue = _purpose_pair_issue(obligation, aq, sq, sentences=sentences, mq=mq, eq=eq,
                                        request_antecedent=len(obligations) == 1,
                                        source_context=identity_context)
            if issue:
                failures.append(issue)
                continue
        else:
            if not _RELATION.search(sq) or not _RELATION.search(aq):
                failures.append("explanation_relationship_unestablished")
                continue
            source_polarities = {polarity for polarity in (False, True)
                                 if _relationship_unit_bound(obligation, sq, sq, negative=polarity)}
            if not source_polarities:
                failures.append("explanation_source_relationship_unbound")
                continue
            candidate_polarities = {polarity for polarity in (False, True)
                                   if _relationship_unit_bound(obligation, aq, sq, sentences=sentences,
                                                               mq=mq, eq=eq, negative=polarity,
                                                               request_antecedent=len(obligations) == 1)}
            if not candidate_polarities:
                failures.append("explanation_candidate_relationship_unbound")
                continue
            if not candidate_polarities & source_polarities:
                failures.append("explanation_relationship_polarity_mismatch")
                continue
        if not (_role_bridge(effect, eq, identity_context) or _reference_bridge(effect, eq, mechanism, sentences,
                                                               request_antecedent=len(obligations) == 1)):
            failures.append("explanation_effect_binding_unestablished")
        if mechanism and not (_role_bridge(mechanism, mq, identity_context) or _reference_bridge(mechanism, mq, effect, sentences,
                                                                                request_antecedent=len(obligations) == 1)):
            failures.append("explanation_mechanism_binding_unestablished")
        # Merely pointing to an earlier subject plus an unrelated quoted cause
        # is not an answer to this relationship: the answer must carry each
        # assessed target/reference span itself.
        if any(not _literal_contains(aq, quote) for quote in ((eq, mq) if mechanism else (eq,))):
            failures.append("explanation_answer_target_unbound")
    return list(dict.fromkeys(failures))


def explanation_target_diagnostics(obligations, raw_assessments, sentences, packet):
    """Bounded observational projections; never expose proposed/source prose.

    These booleans describe the exact transport checked by Core. They supply
    no semantic authority and cannot change any verdict. In particular, a
    false model assessment is retained rather than inferred from the booleans.
    """
    sources = admitted_body_sources(packet)
    candidate = " ".join(str(sentence) for sentence in sentences)
    raw = {item.get("index"): item for item in raw_assessments
           if isinstance(item, Mapping) and type(item.get("index")) is int} if isinstance(raw_assessments, list) else {}
    result = []
    for obligation in tuple(obligations)[:16]:
        item = raw.get(obligation.get("index"), {})
        source = sources.get(item.get("source_id")) if isinstance(item.get("source_id"), str) else None
        quote = item.get("source_quote")
        body = source.get("content_excerpt", "") if source else ""
        literal = isinstance(quote, str) and bool(quote.strip()) and _literal_contains(body, quote)
        canonical = canonical_purpose_witness(obligation, quote, body) if literal else quote
        raw_text = quote if literal else ""
        text = canonical if literal else ""
        context = ("unchanged" if canonical == quote else
                   "expanded" if isinstance(canonical, str) and quote in canonical else "narrowed") if literal else "unavailable"
        result.append({
            "target_index": obligation.get("index"),
            "relation_type": obligation.get("relation_type") if obligation.get("relation_type") in
                {"purpose_or_necessity", "causal_effect", "condition_effect"} else "unknown",
            "assessment_present": bool(item),
            "assessment_outcome": item.get("outcome") if item.get("outcome") in
                {"factual_explanation", "bounded_limitation", "incomplete"} else "invalid",
            "relationship_answered": item.get("relationship_answered") is True,
            "subject_assessed_bound": item.get("mechanism_bound") is True,
            "requirement_assessed_bound": item.get("effect_bound") is True,
            "source_admitted": source is not None,
            "source_literal_valid": literal,
            "canonical_context": context,
            "source_subject_raw": bool(literal and _role_bridge(obligation.get("mechanism"), raw_text, body)),
            "source_requirement_raw": bool(literal and _role_bridge(obligation.get("effect"), raw_text, body)),
            "source_subject_canonical": bool(literal and _role_bridge(obligation.get("mechanism"), text, body)),
            "source_requirement_canonical": bool(literal and _role_bridge(obligation.get("effect"), text, body)),
            "candidate_subject_literal": _literal_contains(candidate, item.get("mechanism_quote")),
            "candidate_requirement_literal": _literal_contains(candidate, item.get("effect_quote")),
            "candidate_answer_literal": _literal_contains(candidate, item.get("answer_quote")),
            "source_purpose_bound": bool(literal and obligation.get("relation_type") == "purpose_or_necessity"
                                          and _purpose_units(obligation, text, body, nominal_witness=text)),
        })
    return tuple(result)
