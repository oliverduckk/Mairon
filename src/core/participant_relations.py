"""Bounded, perspective-normalised participant relation candidates.

This module discovers obligations, not evidence or general English entailment.
Role nouns are data. Both candidate and USER witnesses use the same extractor;
assistant prose cannot become a source by changing a pronoun or model label.
"""
from __future__ import annotations

import re
from typing import Any


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("’", "'").replace("‘", "'")).strip()


def _participant(pronoun: str, speaker: str) -> str:
    word = pronoun.lower().strip()
    if word in {"i", "me", "my", "mine", "myself"}:
        return speaker
    if word in {"you", "your", "yours", "yourself"}:
        return "assistant" if speaker == "user" else "user"
    return ""


def _word_key(word: str) -> str:
    value = word.lower()
    # Grammatical inflection only: no role aliases or semantic synonyms.
    inflected = {"making": "make", "made": "make", "teaching": "teach", "taught": "teach",
                 "doing": "do", "did": "do", "asking": "ask", "asked": "ask",
                 "needing": "need", "needed": "need", "requiring": "require", "required": "require"}
    if value in inflected:
        return inflected[value]
    if len(value) > 5 and value.endswith("ing"):
        stem = value[:-3]
        return stem + "e" if stem + "e" in _RELATIONAL_ACTIVITIES else stem
    if len(value) > 4 and value.endswith("ed"):
        stem = value[:-2]
        return stem + "e" if stem + "e" in _RELATIONAL_ACTIVITIES else stem
    if len(value) > 4 and value.endswith("s"):
        return value[:-1]
    return value


def _content_key(value: str, speaker: str) -> str:
    tokens = []
    for word in re.findall(r"[a-z]+", value.lower()):
        participant = _participant(word, speaker)
        tokens.append("@" + participant if participant else _word_key(word))
    return " ".join(tokens)


def _clause(text: str, start: int, end: int) -> tuple[str, str]:
    left = max(text.rfind(mark, 0, start) for mark in ".!?;") + 1
    prefix = text[left:start]
    contrasts = list(re.finditer(r"\b(?:but|however|yet)\b", prefix, re.I))
    # An independent contrast resets an epistemic disclaimer; an unresolved
    # if/unless antecedent is conservatively retained across its conjunction.
    if contrasts and not re.search(r"\b(?:if|unless)\b", prefix, re.I):
        left += contrasts[-1].end()
    ends = [text.find(mark, end) for mark in ".!?;"]
    contrast = re.search(r"\b(?:but|however|yet)\b", text[end:], re.I)
    if contrast:
        ends.append(end + contrast.start())
    right = min((position + 1 for position in ends if position >= 0), default=len(text))
    return text[left:right], text[left:start]


def _mode(text: str, start: int, end: int) -> str:
    clause, prefix = _clause(text, start, end)
    for opening, closing in (("\"", "\""), ("`", "`"), ("“", "”")):
        if opening == closing:
            if prefix.count(opening) % 2:
                return "quoted"
        elif prefix.count(opening) > prefix.count(closing):
            return "quoted"
    if re.search(r"(?:^|\s)'[^']*$", prefix):
        return "quoted"
    if re.search(
        r"\b(?:i|we)\s+(?:do\s+not|don't|cannot|can't|could\s+not|couldn't|will\s+not|won't)\s+"
        r"(?:actually\s+)?(?:think|believe|know|confirm|verify|establish|claim|say|assert)\b[^.!?;]{0,100}$|"
        r"\b(?:not\s+(?:true|the\s+case)|false|untrue)\s+(?:that\s+)?[^.!?;]{0,50}$|"
        r"\bi\s+(?:deny|reject|dispute)\s+(?:that\s+)?[^.!?;]{0,50}$", prefix, re.I,
    ):
        return "unasserted"
    if "?" in clause:
        return "questioned"
    if re.search(r"\b(?:if|unless|suppose|supposing|hypothetically|would|could|might)\b", clause, re.I):
        return "conditional"
    if re.search(r"\b(?:should(?:n't|nt)?|ought|must|supposed\s+to)\b", clause, re.I):
        return "normative"
    if re.search(r"\bwill\b|'ll\b|\bwon't\b", clause, re.I):
        return "future"
    return "asserted"


_SUBJECT = r"(?P<subject>you|i)"
_MODIFIERS = r"(?:(?:apparently|actually|already|really|still|just|simply|always|often|routinely|habitually|repeatedly|usually|now)\s+)*"
_FREQUENCY = re.compile(r"\b(?:always|often|routinely|habitually|repeatedly|usually|keep|keeps|kept)\b", re.I)
_ROLE = r"(?P<role>[a-z][a-z-]*(?:\s+(?!(?:for|who|that|which|because|when|while|if|but|and|or|now|today|again|here|there)\b)[a-z][a-z-]*){0,5})"
_RELATIONAL_ACTIVITIES = {"do", "explain", "lecture", "research", "teach", "train", "instruct",
                          "manage", "supervise", "debug", "prepare", "handle", "help", "serve",
                          "work", "mentor", "support"}


def detect_participant_relations(text: str, *, speaker: str = "assistant") -> tuple[dict[str, Any], ...]:
    """Return Core-owned role/agency candidates with stable participant IDs.

    Only the two live conversational participants are resolved. Unknown names,
    third parties and open-ended language remain for specialised semantic
    validators. Conditionality is metadata, never proof of a literal relation.
    """
    if speaker not in {"user", "assistant"}:
        raise ValueError("invalid participant perspective")
    value = _text(text)
    records = []
    covered = []

    def add(match, kind, predicate, *, target="", content="", polarity=None):
        subject = _participant(match.group("subject"), speaker)
        span = match.group(0).strip()
        record = {
            "candidate_span": span, "predicate": predicate.lower().strip(),
            "subject": subject, "target": _participant(target, speaker),
            "relation_kind": kind,
            "polarity": polarity or ("negative" if re.search(r"\bnot\b|n't\b|\bnever\b", span, re.I) else "positive"),
            "mode": _mode(value, match.start(), match.end()),
            "recurrent": bool(_FREQUENCY.search(span)),
            "frequency": tuple("keep" if item.lower() in {"keep", "keeps", "kept"} else item.lower()
                               for item in _FREQUENCY.findall(span)),
            "content": _content_key(content, speaker),
        }
        if record not in records:
            records.append(record)
            covered.append((match.start(), match.end()))

    # Copular role assignment, including arbitrary article/adjective phrases.
    # A beneficiary comes from possession or an explicit for/to participant.
    role_pattern = re.compile(
        r"\b" + _SUBJECT + r"(?:'re|'m|\s+(?:(?:will|would|could|might|should)\s+be|are|am|were|was|act|acts|acted|work|works|worked))\s+"
        + _MODIFIERS + r"(?P<negative>not\s+|never\s+)?"
        + r"(?P<acting>(?:acting|working)\s+(?:like|as)\s+|(?:like|as)\s+)?"
        + r"(?P<determiner>my|your|a|an|the)\s+" + _ROLE
        + r"(?:\s+(?:for|to)\s+(?P<beneficiary>me|you))?", re.I,
    )
    for match in role_pattern.finditer(value):
        determiner = match.group("determiner").lower()
        target = determiner if determiner in {"my", "your"} else match.group("beneficiary") or ""
        subject = _participant(match.group("subject"), speaker)
        # A bare assistant self-evaluation is not a USER relationship fact.
        # Explicit possession/beneficiary or a relative USER-directed relation
        # remains audited. User article-role assignments do not get this guard.
        if subject == "assistant" and not target:
            relative = re.match(r"\s+(?:who|that)\s+[^.!?;]{0,80}\b(?:you|your)\b", value[match.end():], re.I)
            if not relative:
                continue
        if determiner == "the" and match.group("role").lower() == "one" and re.match(
                r"\s+who\b", value[match.end():], re.I):
            continue
        add(match, "role_acting" if match.group("acting") else "relationship_role",
            match.group("role"), target=target,
            polarity="negative" if match.group("negative") else "positive")

    # Explicit participant-to-participant agency. The action/complement remains
    # data; a shared expectation verb does not authorise a different action.
    agency_pattern = re.compile(
        r"\b" + _SUBJECT + r"(?:'m|'re|'ll|'d)?\s+"
        + r"(?:(?:am|are|was|were|do|did|do\s+not|don't|did\s+not|didn't|should|should\s+not|shouldn't|must|would|could|might|will|can|cannot|can't)\s+)?"
        + _MODIFIERS + r"(?:(?:keep|keeps|kept)\s+)?"
        + r"(?P<verb>expect(?:s|ed|ing)?|need(?:s|ed|ing)?|require(?:s|d|ing)?|ask(?:s|ed|ing)?|want(?:s|ed|ing)?|make|makes|making|made|force(?:s|d|ing)?|tell|tells|telling|told|teach|teaches|teaching|taught|help(?:s|ed|ing)?|let|lets|letting)\s+"
        + r"(?P<target>you|me)\b(?P<content>[^.!?;]{0,160})", re.I,
    )
    for match in agency_pattern.finditer(value):
        add(match, "participant_agency", _word_key(match.group("verb")),
            target=match.group("target"), content=match.group("content"))

    # A conditional gerund can transparently transform a complaint without
    # asserting past work or a professional role. Its agency still gets checked.
    gerund = re.compile(
        r"\b(?P<verb>making|asking|forcing|requiring)\s+(?P<target>you|me)\s+"
        r"(?P<content>[^.!?;]{1,100}?)\s+would\b", re.I,
    )
    for match in gerund.finditer(value):
        target = _participant(match.group("target"), speaker)
        clause, prefix = _clause(value, match.start(), match.end())
        tail = value[match.end():match.start() - len(prefix) + len(clause)]
        safe_transform = bool(re.fullmatch(
            r"\s+(?:be|feel|seem|amount\s+to)\s+[^.!?;]{1,100}[.!?;]?",
            tail, re.I,
        )) and not re.search(
            r"\b(?:i|me|my|you|your|because|since|when|whenever|always|keep|routinely|habitually)\b", tail, re.I,
        )
        record = {"candidate_span": match.group(0).strip(), "predicate": _word_key(match.group("verb")),
                  "subject": "assistant" if target == "user" else "user", "target": target,
                  "relation_kind": "participant_agency", "polarity": "positive", "mode": "conditional",
                  "recurrent": False, "frequency": (), "content": _content_key(match.group("content"), speaker),
                  "complaint_transform": safe_transform}
        if record not in records:
            records.append(record)
            covered.append((match.start(), match.end()))

    # Recurrent participant activity and work ownership need no role noun.
    activity_pattern = re.compile(
        r"\b" + _SUBJECT + r"(?:'m|'re)?\s+"
        + r"(?:(?:am|are|was|were|do|did|don't|didn't|should|shouldn't|would|could|might|will)\s+)?"
        + _MODIFIERS + r"(?:(?:keep|keeps|kept)\s+)?"
        + r"(?P<verb>[a-z][a-z-]*)\s+(?:"
        + r"(?P<direct_target>me|you)\b|"
        + r"(?P<content>(?:(?!\b(?:instead|rather|because|although|while|when|if|unless|and|but)\b)[^.!?;]){0,100}?)"
        + r"(?:\b(?:to|for)\s+(?P<target>me|you)\b|\b(?P<owner>my|your)\s+(?P<object>[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,3})))", re.I,
    )
    for match in activity_pattern.finditer(value):
        if any(left <= match.start() < right for left, right in covered):
            continue
        verb = _word_key(match.group("verb"))
        if verb in {"am", "are", "is", "was", "were", "a", "an", "the", "my", "your"}:
            continue
        # Generic participant-target sentences need not imply work or a role.
        # Only a bounded responsibility/activity family or explicit recurrence
        # is audited here; e.g. "I see your point" remains a normal acknowledgement.
        if verb not in _RELATIONAL_ACTIVITIES and not _FREQUENCY.search(match.group(0)):
            continue
        content = (match.group("content") or "") + (match.group("object") or "")
        add(match, "participant_activity", verb,
            target=match.group("target") or match.group("direct_target") or match.group("owner") or "", content=content)
    return tuple(sorted(records, key=lambda record: value.find(record["candidate_span"])))


def participant_relation_witnessed(obligation: dict[str, Any], quote: str, *, source_text: str) -> bool:
    """Check literal USER membership and bounded relation identity/direction.

    Semantic entailment still belongs to the scoped verifier. This gate cannot
    certify a candidate using an invented quote, an assistant interpretation,
    a role synonym, opposite agency, or a question/quoted conditional source.
    """
    if not isinstance(obligation, dict) or not isinstance(quote, str) or not isinstance(source_text, str):
        return False
    supplied = _text(source_text)
    witness = _text(quote)
    if not witness or len(witness) > 500 or witness not in supplied:
        return False
    witness_start = supplied.find(witness)
    for relation in detect_participant_relations(witness, speaker="user"):
        relation_start = supplied.find(relation["candidate_span"], witness_start, witness_start + len(witness))
        if relation_start < 0:
            continue
        actual_mode = _mode(supplied, relation_start, relation_start + len(relation["candidate_span"]))
        if relation["mode"] in {"quoted", "questioned", "conditional", "unasserted"} or actual_mode in {"quoted", "questioned", "conditional", "unasserted"}:
            continue
        relation["mode"] = actual_mode
        # Only a Core-recognised hypothetical delegation/evaluation can use the
        # actual complaint as a semantic transformation anchor. No new actual
        # role, history or task fact is thereby supplied. The scoped semantic
        # verifier still has to approve the transformation's entailment.
        delegation = {"expect", "need", "require", "ask", "want", "make", "force", "tell"}
        if (obligation.get("complaint_transform") is True
                and obligation.get("mode") == "conditional"
                and obligation.get("relation_kind") == "participant_agency"
                and obligation.get("recurrent") is False
                and obligation.get("predicate") in delegation
                and relation.get("relation_kind") == "participant_agency"
                and relation.get("predicate") in delegation
                and relation.get("mode") == "normative"
                and relation.get("polarity") == "negative"
                and all(obligation.get(key) == relation.get(key) for key in ("subject", "target"))):
            return True
        if any(obligation.get(key) != relation.get(key) for key in
               ("subject", "target", "relation_kind", "predicate", "polarity", "recurrent", "frequency", "content")):
            continue
        if obligation.get("mode") == "asserted" and relation["mode"] != "asserted":
            continue
        if obligation.get("mode") == "future" and relation["mode"] != "future":
            continue
        return True
    return False
