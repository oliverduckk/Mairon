"""Core-owned applicability obligations for consequential public advice.

One public verifier may judge meaning, but cannot select a user's provider,
jurisdiction or procedure from the sources it happened to retrieve. Concrete
procedures use one admitted readable body witness and matching USER scope.
This module never publishes, performs research, or calls a model.
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
import re

from research.public_claim_obligations import admitted_body_sources


_SCOPE_ROLES = {
    "provider": r"(?:bank|provider|insurer|carrier|service|platform|institution|issuer|authority)",
    "jurisdiction": r"(?:country|jurisdiction|region|territory|state)",
    "rail": r"(?:(?:payment|transfer|transaction)\s+(?:rail|method|network|type)|rail)",
}
_NAME = r"[\w][\w'’ -]{0,75}"
_ACT = re.compile(
    r"\b(?:file|lodge|submit|appeal|escalat\w*|disput\w*|cancel\w*|revers\w*|"
    r"recall\w*|recover\w*|reimburse\w*|refund\w*|freeze\w*|block\w*|"
    r"regulator\w*|legal|entitle\w*|require\w*|complaint|cancellation|"
    r"follow\s+up|contact|call|report|request|notify|process|procedure)\b", re.I,
)
_RULE = re.compile(
    r"\b(?:must|have\s+to|need\s+to|will|always|guarantee\w*|automatically|"
    r"eligible|entitled|can\s+be|cannot\s+be|can['’]t\s+be)\b", re.I,
)
_EXCLUSIVE = re.compile(
    r"\b(?:only|sole|solely|entirely|always|never|guarantee\w*|certain(?:ly)?|"
    r"no\s+other|nothing\s+else)\b", re.I,
)
# A conditional procedural consequence still makes a claim about a provider's
# process. It does not become applicable merely because its antecedent starts
# with "if". Pronouns retain that obligation even when the institutional noun
# appeared in an earlier sentence.
_PROVIDER_OUTCOME = re.compile(
    r"\b(?:they|it|(?:the|your|sending|receiving|other)\s+"
    r"(?:bank|provider|service|authority|institution|issuer))\s*"
    r"(?:(?:will|shall|can|may|might|could|should|does|do)\s+|['’]ll\s+)?"
    r"(?:handle|resolve|process|recover|refund|reimburse|cancel|reverse|stop|return|complete)\w*\b", re.I,
)
_CERTAIN_OUTCOME = re.compile(
    r"\b(?:they|it|(?:the|your|sending|receiving|other)\s+"
    r"(?:bank|provider|service|authority|institution|issuer))\s*"
    r"(?:(?:will|shall)\s+|['’]ll\s+)"
    r"(?:handle|resolve|process|recover|refund|reimburse|cancel|reverse|stop|return|complete)\w*\b", re.I,
)
_OTHER_INSTITUTION = re.compile(
    r"\b(?:other|recipient(?:['’]s)?|receiving|beneficiary(?:['’]s)?)\s+"
    r"(?:bank|provider|service|authority|institution|issuer)\b", re.I,
)
_NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
                 "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
                 "fourteen": 14, "fifteen": 15, "sixteen": 16,
                 "seventeen": 17, "eighteen": 18, "nineteen": 19,
                 "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
                 "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_NUMBER = r"(?:" + "|".join(_NUMBER_WORDS) + r"|hundred|thousand)"
_NUM = rf"(?:\d+(?:\.\d+)?|{_WORD_NUMBER}(?:[ -]+(?:and\s+)?{_WORD_NUMBER}){{0,5}})"
_DURATION = re.compile(
    rf"\b(?:(?P<relation>within|before|after|by|at\s+least|up\s+to|no\s+later\s+than|takes?)\s+)?"
    rf"(?P<a>{_NUM})(?:\s*(?:to|through|[-–])\s*(?P<b>{_NUM}))?[ -]+"
    r"(?P<business>business\s+|working\s+)?(?P<unit>minutes?|hours?|days?|weeks?|months?|years?)\b", re.I,
)
_CADENCE = re.compile(r"\b(?:daily|weekly|monthly|every\s+(?:day|week|month))\b", re.I)
_REFERENCE = re.compile(r"\b[A-Z][A-Z0-9]{1,11}\b|\b[A-Z][a-z][A-Za-z0-9]*(?:\s+[A-Z][a-z][A-Za-z0-9]*){0,3}\b")


def _normal(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold().replace("’", "'")


def _name(value):
    value = re.split(r"\b(?:but|and|where|which|what|please|now|via|through|using|in)\b",
                     str(value or ""), maxsplit=1, flags=re.I)[0]
    return _normal(value).strip(" .,:;\"'“”")


def _unasserted(text):
    value = str(text or "").strip()
    return bool(value.endswith("?") or re.match(r"^(?:[\"“'‘]|if\b|suppose\b|imagine\b)", value, re.I))


def _without_quoted_scope(text):
    # Keep quote boundaries across sentence splits. A quoted three-sentence
    # example cannot become three unquoted USER scope assertions. Apostrophes
    # inside contractions/names are not quote openers.
    value = str(text or "")
    result = list(value)
    opener = None
    start = None
    pairs = {'"': '"', '“': '”', "'": "'", '‘': '’'}
    for index, char in enumerate(value):
        if opener is not None:
            if char == pairs[opener] and not (char in {"'", "’"} and index + 1 < len(value)
                                              and value[index + 1].isalnum()):
                result[start:index + 1] = " " * (index + 1 - start)
                opener = start = None
        elif char in pairs and not (char in {"'", "‘"} and index and value[index - 1].isalnum()):
            opener, start = char, index
    if opener is not None:
        result[start:] = " " * (len(value) - start)
    return "".join(result)


def _scope_events(text, *, user):
    """Extract only bounded named applicability, never topic/token overlap.

    Bare country names/domains/titles are not scope. No country/provider list
    or alias inference is needed. Source bodies retain their own stated scope;
    a missing source scope stays unknown instead of being inferred from URLs.
    """
    events = []
    # Preserve question/quote scope until authority is assessed. Removing '?' 
    # first would turn 'My provider is ArborBank?' into an asserted scope.
    value = _without_quoted_scope(text) if user else str(text or "")
    for clause in re.split(r"(?<=[.!?;])\s+|\n+|\bbut\b", value, flags=re.I):
        clause = clause.strip()
        if not clause or _unasserted(clause) or re.search(
                r"\b(?:if|might|maybe|may|suppose|imagine|would|could|hypothetical|example|whether|"
                r"uncertain|unsure|wonder|said|claimed|thought|believed)\b|"
                r"\b(?:not\s+sure|don['’]t\s+know|do\s+not\s+know|cannot\s+confirm|can't\s+confirm)\b", clause, re.I):
            continue
        for role, label in _SCOPE_ROLES.items():
            prefix = r"(?:my|our|the\s+sending|the)\s+" if user else r"(?:the\s+|this\s+|our\s+)?"
            pattern = (rf"\b{prefix}{label}\s*(?P<aux>isn't|wasn't|is|was|:|=|called)\s*"
                       rf"(?P<negative>not\s+|no\s+longer\s+)?(?P<name>{_NAME})")
            for match in re.finditer(pattern, clause, re.I):
                name = _name(match.group("name"))
                if name:
                    events.append((role, name, not bool(match.group("negative") or "n't" in match.group("aux"))))
        # First-person actual locality is USER jurisdiction; a source's
        # declarative procedure locality is its jurisdiction, never the user's.
        locality = (rf"\b(?:I\s+am|I'm|we\s+are|we're|I\s+live|we\s+live)\s+"
                    rf"(?P<negative>not\s+|no\s+longer\s+)?(?:based\s+)?in\s+(?P<name>{_NAME})"
                    if user else rf"\b(?:in|within)\s+(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){{0,2}})\b")
        flags = re.I if user else 0
        for match in re.finditer(locality, clause, flags):
            name = _name(match.group("name"))
            if name:
                events.append(("jurisdiction", name, not bool(match.groupdict().get("negative"))))
        if user:
            for match in re.finditer(
                rf"\b(?:I|we)\s+(?:am\s+|are\s+)?(?P<negative>not\s+|no\s+longer\s+)?"
                rf"(?:bank(?:ing)?\s+with|use|used|using)\s+(?P<name>{_NAME})", clause, re.I,
            ):
                name = _name(match.group("name"))
                if name:
                    events.append(("provider", name, not bool(match.group("negative"))))
        else:
            # These body relations identify a scope without a country/provider
            # ontology. A mere name elsewhere in a page remains insufficient.
            for role, pattern in (
                ("provider", rf"\b(?:customers|accounts|members)\s+(?:of|at|with)\s+(?P<name>{_NAME})"),
                ("rail", rf"\b(?:payments?|transfers?|transactions?)\s+(?:via|through|using)\s+(?P<name>{_NAME})"),
            ):
                for match in re.finditer(pattern, clause, re.I):
                    name = _name(match.group("name"))
                    if name:
                        events.append((role, name, True))
    return events


def consequential_user_scope(user_input, conversation=None):
    """USER-only actual scope with latest named correction/negation winning."""
    texts = []
    if isinstance(conversation, (list, tuple)):
        for message in conversation:
            if isinstance(message, Mapping) and message.get("role") == "user":
                texts.append(message.get("content", ""))
    texts.append(user_input)
    state = {}
    for text in texts:
        for role, name, positive in _scope_events(text, user=True):
            if positive:
                state[role] = name
            elif state.get(role) == name:
                state.pop(role)
    return state


def _source_scope(source):
    result = {}
    ambiguous = set()
    for role, name, positive in _scope_events(source.get("content_excerpt", ""), user=False):
        if not positive:
            continue
        if role in result and result[role] != name:
            ambiguous.add(role)
        result[role] = name
    for role in ambiguous:
        result.pop(role, None)
    return result, ambiguous


def _durations(text):
    def number(value):
        if value is None:
            return None
        word = value.lower()
        if re.fullmatch(r"\d+(?:\.\d+)?", word):
            return word
        total = current = 0
        for atom in re.split(r"[ -]+", word):
            if atom == "and":
                continue
            if atom == "hundred":
                current = (current or 1) * 100
            elif atom == "thousand":
                total += (current or 1) * 1000
                current = 0
            else:
                current += _NUMBER_WORDS.get(atom, 0)
        return str(total + current)
    return tuple((number(match.group("a")), number(match.group("b")), _normal(match.group("relation")),
                  bool(match.group("business")), match.group("unit").lower().rstrip("s"))
                 for match in _DURATION.finditer(str(text or "")))


def _named_references(value):
    result = []
    for match in _REFERENCE.finditer(value):
        name = match.group()
        if match.start() == 0:
            words = name.split()
            first = words[0]
            if (_ACT.fullmatch(first) or first.casefold() in {
                    "the", "your", "you", "i", "we", "it", "this", "that", "for", "if", "do", "don't", "use",
                    "promptly", "immediately", "please", "because", "then", "first", "ask", "check", "confirm"}):
                name = " ".join(words[1:])
        if name:
            result.append(name)
    return result


def _generic_first_step(value):
    """A narrow support-contact/uncertainty response asserts no procedure."""
    if (_DURATION.search(value) or _CADENCE.search(value) or _EXCLUSIVE.search(value)
            or _OTHER_INSTITUTION.search(value)):
        return False
    named = _named_references(value)
    if named:
        return False
    if re.search(r"\b(?:ask|check|confirm)\b[^.!?]{0,90}\bwhether\b", value, re.I) and not re.search(
            r"\b(?:but|however|and\s+(?:the|your|it|they))\b", value, re.I):
        return True
    if re.search(r"\b(?:I|we)\s+(?:cannot|can't|couldn't|won't|do\s+not)\s+"
                 r"(?:guess|verify|establish|promise|guarantee|know)\b", value, re.I) and not re.search(
            r"\b(?:but|however|and\s+(?:the|your|it|they))\b", value, re.I):
        return True
    if _PROVIDER_OUTCOME.search(value):
        return False
    if not re.search(r"\b(?:contact|call|report|follow|use)\b", value, re.I):
        return False
    if not re.search(r"\b(?:your|the|sending|relevant|issuing)\b[^.!?]{0,35}"
                     r"\b(?:bank|provider|service|authority|institution|issuer)\b", value, re.I):
        return False
    return not re.search(r"\b(?:file|lodge|appeal|escalat\w*|disput\w*|cancel\w*|revers\w*|"
                         r"recall\w*|recover\w*|refund\w*|reimburse\w*|freeze\w*|block\w*|"
                         r"legal|regulator\w*|eligible|entitled|will|must|guarantee\w*)\b", value, re.I)


def consequential_claim_obligations(sentences):
    """Core decides which concrete advice needs independently scoped support."""
    items = []
    for sentence_index, sentence in enumerate(sentences, 1):
        value = str(sentence or "").strip()
        if not value or value.endswith("?") or re.match(r"^[\"“'‘]", value):
            continue
        # Hypothetical framing cannot erase an asserted procedural consequent.
        # Pure examples/questions remain unasserted; safe conditional provider
        # contact remains covered by the same narrow first-step exemption.
        if (_unasserted(value) and not (_ACT.search(value) or _RULE.search(value)
                                       or _PROVIDER_OUTCOME.search(value))):
            continue
        if _generic_first_step(value):
            continue
        kinds = []
        if _DURATION.search(value) or _CADENCE.search(value):
            kinds.append("procedure_time")
        if _EXCLUSIVE.search(value):
            kinds.append("exclusive_outcome")
        if _CERTAIN_OUTCOME.search(value):
            kinds.append("certain_outcome")
        if _ACT.search(value) or _PROVIDER_OUTCOME.search(value) or _RULE.search(value) and re.search(
                r"\b(?:bank|provider|service|authority|transfer|payment|transaction|account|claim)\b", value, re.I):
            kinds.append("specific_procedure")
        if re.search(r"\b(?:rails?|networks?|schemes?|systems?|providers?|banks?|jurisdictions?|"
                     r"countries|regions?|services?)\b", value, re.I) and _named_references(value):
            kinds.append("named_applicability")
        for kind in kinds:
            items.append({"index": len(items) + 1, "sentence_index": sentence_index,
                          "kind": kind, "candidate_span": value})
    return tuple(items)


def consequential_assessment_schema(base_schema):
    result = copy.deepcopy(base_schema)
    result["properties"]["consequential_assessments"] = {
        "type": "array", "items": {
            "type": "object", "properties": {
                "index": {"type": "integer", "minimum": 1}, "supported": {"type": "boolean"},
                "source_id": {"type": ["string", "null"]}, "source_quote": {"type": ["string", "null"]},
            }, "required": ["index", "supported", "source_id", "source_quote"],
            "additionalProperties": False,
        },
    }
    result["required"].append("consequential_assessments")
    return result


def consequential_claim_failures(obligations, assessments, packet, user_scope):
    """A positive semantic verdict never substitutes source scope for USER scope."""
    failures = {}

    def fail(item, reason):
        failures.setdefault(item["sentence_index"], set()).add(reason)

    if not obligations:
        return failures
    known = {}
    if isinstance(assessments, list):
        for value in assessments:
            if (not isinstance(value, Mapping) or set(value) != {"index", "supported", "source_id", "source_quote"}
                    or type(value.get("index")) is not int or value["index"] in known
                    or not 1 <= value["index"] <= len(obligations) or type(value.get("supported")) is not bool):
                known = {}
                break
            known[value["index"]] = value
    complete = set(known) == set(range(1, len(obligations) + 1))
    sources = admitted_body_sources(packet)
    for item in obligations:
        if not user_scope:
            fail(item, "user_applicability_scope_unavailable")
        if not complete:
            fail(item, "invalid_consequential_assessments")
            continue
        assessment = known[item["index"]]
        if assessment["supported"] is not True:
            fail(item, "unsupported_consequential_proposition")
            continue
        source = sources.get(assessment["source_id"]) if isinstance(assessment["source_id"], str) else None
        quote = assessment["source_quote"]
        if (source is None or not isinstance(quote, str) or not quote.strip() or len(quote) > 800
                or quote not in source["content_excerpt"]):
            fail(item, "missing_admitted_procedure_witness")
            continue
        source_scope, ambiguous = _source_scope(source)
        if not source_scope or ambiguous:
            fail(item, "source_applicability_scope_unavailable")
        elif any(user_scope.get(role) != name for role, name in source_scope.items()):
            fail(item, "consequential_applicability_mismatch")
        candidate = item["candidate_span"]
        for role, name, positive in _scope_events(candidate, user=False):
            if positive and user_scope.get(role) != name:
                fail(item, "candidate_applicability_mismatch")
        if item["kind"] == "procedure_time":
            if not set(_durations(candidate)).issubset(_durations(quote)):
                fail(item, "procedure_time_witness_mismatch")
            if any(_normal(match.group()) not in _normal(quote) for match in _CADENCE.finditer(candidate)):
                fail(item, "procedure_cadence_witness_mismatch")
        elif item["kind"] == "exclusive_outcome":
            if not _EXCLUSIVE.search(quote):
                fail(item, "exclusive_outcome_witness_missing")
        elif item["kind"] == "certain_outcome":
            if not (_CERTAIN_OUTCOME.search(quote) or _EXCLUSIVE.search(quote)):
                fail(item, "certain_outcome_witness_missing")
        # Proper identifiers/acronyms in procedure prose stay attached to this
        # single admitted witness. Same-topic evidence from another source
        # cannot fill a missing provider/rail or change it by token overlap.
        names = _named_references(candidate)
        if any(_normal(name) not in _normal(quote) for name in names):
            fail(item, "procedure_identity_witness_mismatch")
        if _unasserted(quote):
            fail(item, "procedure_assertion_scope_mismatch")
    return failures
