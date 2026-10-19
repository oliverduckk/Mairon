"""Bounded knowledge-basis checks for work-specific opinion prose.

Subjective preference is not the same proposition as having an informed basis
for claims about a work's writing, pacing or appeal. This adapter projects the
latter before the existing semantic grounding/verifier calls. It creates no
knowledge, permission, persistent opinion or research request.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any, Tuple

from core.evidence import EvidenceBundle, EvidenceKind, EvidenceStatus
from core.stance_ownership import is_user_stance_acknowledgement


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("’", "'").replace("‘", "'")).strip()


def _normal(value: Any) -> str:
    return _text(value).casefold().strip(" .!?;,:\"“”'")


_REQUEST = re.compile(
    r"\bwhat\s+do\s+you\s+(?:(?:actually|really)\s+)?think\s+(?:of|about)\s+"
    r"(?P<think>[^?!\n]+)|"
    r"\bwhat(?:'s|\s+is)\s+your\s+(?:(?:own|actual|honest)\s+)?"
    r"(?:take|opinion|view)\s+(?:on|of|about)\s+(?P<take>[^?!\n]+)", re.I,
)
_DIMENSION = re.compile(
    r"\b(?P<dimension>writing(?:\s+style)?|prose|pacing|world[- ]?building|"
    r"character\s+(?:writing|work|development)|plot|story|dialogue|exposition|"
    r"ending|themes?|combat|romance|appeal|content|narrative|art(?:work)?|"
    r"animation|acting|soundtrack|gameplay|controls|level\s+design|"
    r"updates?|release\s+schedule)\b", re.I,
)
_PREDICATE = re.compile(
    r"^\s*(?:really\s+|actually\s+|generally\s+|mostly\s+|often\s+|usually\s+)*"
    r"(?:(?:is|are|was|were|feels?|seems?|remains?|looks?)\b\s*"
    r"|(?:does|doesn't|does\s+not|doesn['’]?t|does|has|have|had|keeps?|"
    r"drags?|works?|lacks?|uses?|relies|comes?|moves?|spends?|makes?|"
    r"focuses|repeats|develops|handles|balances|rewards|suffers|offers|"
    r"holds?\s+up|stands?\s+up)\b\s*)"
    r"(?P<property>.+)$", re.I,
)
_QUALITY_PRESERVATION = re.compile(
    r"^\s*(?:(?:really|actually|generally|mostly|still)\s+)*"
    r"(?:holds?|stands?)\s+up(?:\s+.+)?$", re.I,
)
_CONSUMPTION_PREDICATE = (
    r"(?P<copula>\s+(?:is|was)|'s)\s+(?:just\s+|quite\s+|really\s+|"
    r"a\s+|an\s+)*(?P<quality>[a-z][a-z -]{0,55}?)\s+"
    r"(?P<experience>read|watch|play|experience|entertainment)\b"
)
_CONSUMPTION = re.compile(
    r"\b(?:it|this|that|the\s+(?:book|work|series|film|show|game|story))"
    + _CONSUMPTION_PREDICATE, re.I,
)
# Attributive appraisals have the same authority requirement as predicate
# appraisals: "it has measured pacing" is not less specific than "the pacing
# is measured". Recognise a bounded grammatical slot rather than a list of
# approved/disallowed aesthetic adjectives.
_ATTRIBUTE_BOUNDARY = re.compile(
    r"\b(?:has|have|had|with|offers?|provides?|features?|boasts?|and)\b|[,;:]|['’]s\b", re.I,
)
_ATTRIBUTE_SYNTAX = frozenset({
    "a", "an", "the", "its", "their", "our", "my", "your", "his", "her",
    "it", "this", "that", "these", "those", "is", "are", "was", "were",
    "i", "you", "we", "they", "whether", "what", "which", "whose", "how",
    "to", "of", "for", "about", "on", "at", "in", "from", "by", "as",
    "can", "could", "would", "should", "might", "may", "will", "must",
    "like", "prefer", "enjoy", "want", "value", "need", "needs", "more", "less",
})


def _attributive_property(clause: str, start: int, end: int) -> str:
    """Bounded nominal work-property assertion, never an adjective witness.

    Only a modifier slot following possession/list grammar or a standalone
    nominal appraisal is projected. Generic first-person taste and infinitive
    discussion are not statements that this work possesses the property.
    """
    prefix = clause[:start]
    boundaries = list(_ATTRIBUTE_BOUNDARY.finditer(prefix))
    modifier = prefix[boundaries[-1].end():] if boundaries else prefix
    modifier = re.sub(r"^\s*(?:a|an|the)\s+", "", modifier, flags=re.I).strip()
    words = re.findall(r"[a-z]+(?:[-'][a-z]+)*", modifier, re.I)
    if not words or len(words) > 4 or " ".join(words).casefold() != modifier.casefold():
        return ""
    if any(word.casefold() in _ATTRIBUTE_SYNTAX for word in words):
        return ""
    if not boundaries and re.search(r"\S", clause[end:]):
        return ""  # A bare nominal fragment is bounded at its property noun.
    # A later list item cannot borrow a property assertion from generic taste.
    if re.match(r"^\s*i\s+(?:like|prefer|enjoy|want|value)\b", clause, re.I):
        if not re.search(r"\b(?:it|this|that)\s+(?:has|offers?|provides?|features?|boasts?)\b",
                         prefix, re.I):
            return ""
    return _normal(modifier)
_NONASSERTIVE = re.compile(
    r"^\s*(?:(?:well|honestly|personally)\s*[,;:]\s*)?"
    r"(?:if\b|unless\b|assuming\b|suppose\b|imagine\b|"
    r"(?:is|are|does|do|did|have|has|had|am|can|could|would|might|how|what|whether)\b|"
    r"i\s+(?:would|might|could)\s+(?:like|prefer|enjoy|value|want)\b|"
    r"i\s+(?:don't|do\s+not)\s+know\b|"
    r"i\s+(?:can't|cannot)\s+(?:judge|assess|evaluate|give)\b|"
    r"i\s+(?:won't|will\s+not|don't|do\s+not)\s+(?:pretend|claim|say)\b|"
    r"i(?:'m|\s+am)\s+(?:not\s+sure|unfamiliar|not\s+familiar)\b)", re.I,
)


@dataclass(frozen=True)
class WorkAppraisalObligation:
    """A concrete property, not evidence that the property is true."""

    index: int
    dimension: str
    predicate: str
    sentence: str


def _clauses(value: str):
    # A disclaimer before a semicolon/but must not shield a later assertion.
    raw = str(value or "").replace("’", "'").replace("‘", "'")
    return tuple(_text(part) for part in re.split(
        r"[.!?](?=\s|$)|[;\n]+|\bbut\b|\bhowever\b|,\s*(?:and|yet|although)\s+",
        raw, flags=re.I,
    ) if part.strip())


def opinion_request_subject(user_input: str, opinion_subject: Any = None) -> str:
    """Resolve the current named request; a ledger hint cannot overwrite it."""
    match = _REQUEST.search(_text(user_input))
    if match:
        subject = next((value for value in match.groupdict().values() if value), "")
        subject = re.split(r"\.(?=\s|$)|\b(?:don't|dont|do\s+not)\s+just\s+agree\b",
                           subject, flags=re.I)[0].strip()
        if subject:
            subject = subject.strip('"“”')
            if isinstance(opinion_subject, Mapping) and opinion_subject.get("kind") == "overall_opinion":
                title = _text(opinion_subject.get("title"))
                prefix = re.sub(r"^(?:the|a|an)\s+", "", _normal(subject))
                bounded = re.sub(r"^(?:novel|book|story|work|series|film|show|game)\s+"
                                 r"(?:(?:called|titled)\s+)?", "", prefix)
                if title and bounded == _normal(title):
                    return title
            return subject
    if isinstance(opinion_subject, Mapping) and opinion_subject.get("kind") == "overall_opinion":
        return _text(opinion_subject.get("title"))
    return ""


def asserted_opinion_clauses(draft: str) -> Tuple[str, ...]:
    """Shared bounded assertion scope for legacy and projected opinion checks."""
    result = []
    for clause in _clauses(draft):
        if _NONASSERTIVE.search(clause):
            # A real conditional/question scopes its clause. A self-limitation
            # scopes only what is not known; an independently asserted finite
            # clause after a comma/colon does not inherit that limitation.
            limitation = re.match(r"^\s*i\s+(?:don't|do\s+not|can't|cannot|won't|will\s+not)\b|"
                                  r"^\s*i(?:'m|\s+am)\s+(?:not\s+sure|unfamiliar|not\s+familiar)\b",
                                  clause, re.I)
            tails = re.split(r"[,—:]\s*(?=(?:the|its|their|this|that|it|I|[A-Z][\w'-]*'s)\b)", clause)
            if not limitation or len(tails) < 2:
                continue
            clause = " ".join(tails[1:])
        result.append(clause)
    return tuple(result)


def project_work_appraisals(draft: str, *, subject: str = "") -> Tuple[WorkAppraisalObligation, ...]:
    """Project bounded work properties without inferring knowledge from prose."""
    found = []
    for index, clause in enumerate(asserted_opinion_clauses(draft), 1):
        literal = re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)',
                         lambda match: " " * len(match.group()), clause)
        for match in _DIMENSION.finditer(literal):
            # Mentioning a property in a nonassertive question is not appraisal.
            prefix = literal[:match.start()]
            if re.search(r"\b(?:whether|if|how)\b", prefix, re.I):
                continue
            dimension = _normal(match.group("dimension"))
            tail = literal[match.end():]
            if _PREDICATE.match(tail) or _QUALITY_PRESERVATION.match(tail):
                found.append(WorkAppraisalObligation(index, dimension, _normal(tail), clause))
            modifier = _attributive_property(literal, match.start(), match.end())
            if modifier:
                copula = "are" if dimension in {"updates", "themes", "controls"} else "is"
                found.append(WorkAppraisalObligation(index, dimension, copula + " " + modifier, clause))
        experience = _CONSUMPTION.search(literal)
        if not experience and subject:
            experience = re.search(
                r"(?<!\w)" + re.escape(subject) + r"(?!\w)" + _CONSUMPTION_PREDICATE,
                literal, re.I,
            )
        if experience:
            found.append(WorkAppraisalObligation(
                index, "consumption_appraisal",
                ("was" if _normal(experience.group("copula")) == "was" else "is")
                + " " + _normal(experience.group("quality"))
                + " " + _normal(experience.group("experience")), clause,
            ))
    return tuple(found)


def _same_subject(subject: str, value: str) -> bool:
    return bool(subject and re.search(
        r"(?<!\w)" + re.escape(_normal(subject)) + r"(?!\w)", _normal(value), re.I,
    ))


def _user_property_witnesses(user_input: str, conversation: Any, subject: str):
    """Latest matching USER assertions; topic/dimension mention is insufficient."""
    turns = []
    for message in list(conversation or []):
        role = message.get("role") if isinstance(message, Mapping) else getattr(message, "role", "")
        content = message.get("content") if isinstance(message, Mapping) else getattr(message, "content", "")
        if str(role).lower() == "user" and _text(content):
            turns.append(_text(content))
    turns.append(_text(user_input))
    latest = {}
    # A current direct opinion question is not a supplied appraisal. An older
    # named statement can establish it; unrelated/deictic turns cannot.
    for turn in turns[-5:]:
        if not _same_subject(subject, turn):
            continue
        for item in project_work_appraisals(turn, subject=subject):
            latest[item.dimension] = item.predicate
    return latest


def _admitted_subject_research(research_evidence: Any, subject: str) -> bool:
    """Readable subject-matching ingress defers entailment to its real verifier."""
    if research_evidence is None:
        return False
    packets = research_evidence if isinstance(research_evidence, tuple) else (research_evidence,)
    for value in packets:
        if not value:
            continue
        try:
            if isinstance(value, EvidenceBundle):
                bundle = value
            else:
                # Ordinary conversation carries no research ingress. Keep the
                # existing lightweight claim-grounding import boundary intact;
                # load the canonical adapter only in the real research lane.
                from core.evidence_normalization import normalize_research_evidence
                bundle = normalize_research_evidence(value, kind=EvidenceKind.MEDIA_SOURCE)
            if not bundle.canonical or not bundle.success:
                continue
            for item in bundle.authoritative_evidence:
                if item.kind not in {EvidenceKind.MEDIA_SOURCE, EvidenceKind.PUBLIC_SOURCE}:
                    continue
                if item.status != EvidenceStatus.ADMISSIBLE or item.quality_eligible is False:
                    continue
                if item.authority_scope != "retrieved_source_assertions":
                    continue
                # A query or title alone cannot authorize content. Subject must
                # occur in the actually retained admissible readable body.
                if _same_subject(subject, item.claim):
                    return True
        except (TypeError, ValueError, AttributeError):
            continue
    return False


def has_admitted_work_research_basis(user_input: str, research_evidence: Any = None,
                                    opinion_subject: Any = None) -> bool:
    """An existing real research lane may use its own strict source verifier.

    This is a capability to validate against that packet, never a positive
    verdict about the current candidate or a grant from a confidence label.
    """
    subject = opinion_request_subject(user_input, opinion_subject)
    return bool(subject and _admitted_subject_research(research_evidence, subject))


def _claimed_personal_consumption(draft: str, subject: str) -> bool:
    # Reading a retained excerpt is not a human consumption history. A positive
    # claim of consuming the requested whole work is incompatible with the
    # existing knowledge-honesty policy even when research is available.
    object_shape = r"(?:it|(?:this|that|the)\s+(?:whole\s+)?(?:work|book|novel|series|film|show|game)|" + re.escape(subject) + r")"
    pattern = re.compile(
        r"\bi(?:'ve|\s+have|\s+had)?\s+(?:(?:personally|actually|already|fully)\s+)?"
        r"(?:read|watched|played|finished|seen|consumed|experienced)\s+"
        r"(?:(?:reading|watching|playing)\s+)?" + object_shape + r"(?!\w)", re.I,
    )
    for clause in asserted_opinion_clauses(draft):
        def named_object(match):
            quoted = match.group(0)[1:-1]
            return quoted if _normal(quoted) == _normal(subject) else ""
        literal = re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', named_object, clause)
        if pattern.search(literal):
            return True
    return False


def find_opinion_knowledge_violations(
    user_input: str, draft: str, conversation=None, *,
    research_evidence: Any = None, opinion_entry: Any = None,
    opinion_subject: Any = None,
) -> list[str]:
    """Default-unknown work properties require an actual authoritative basis.

    Qualifiers and the candidate's claim of confidence never supply that basis.
    Existing media/public sentence verification still decides entailment when
    readable research is available. Matching USER properties retain USER scope;
    the ordinary semantic verifier still checks the rest of the response.
    The passed accepted opinion entry grants no work-property authority: pure
    prior preferences remain available via the existing ledger/stance checks,
    but factual reasons in its old prose must be independently supported.
    """
    if is_user_stance_acknowledgement(user_input):
        return []  # The existing ownership guard governs this distinct act.
    subject = opinion_request_subject(user_input, opinion_subject)
    if not subject:
        return []
    if _claimed_personal_consumption(draft, subject):
        return ["unknown-media opinion claimed human-style media consumption rather than an evidence-backed knowledge basis"]
    obligations = project_work_appraisals(draft, subject=subject)
    if not obligations:
        return []
    if _admitted_subject_research(research_evidence, subject):
        return []
    supplied = _user_property_witnesses(user_input, conversation, subject)
    for item in obligations:
        if supplied.get(item.dimension) == item.predicate:
            continue
        return ["unknown-media opinion presented detailed work-specific familiarity without an authoritative knowledge basis"]
    return []
