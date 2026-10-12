"""Bounded Core-owned obligations for live USER-task diagnostic prose.

This is a structural claim detector, not a technical truth engine.  It gives
the existing semantic verifier inspectable targets whose existence cannot be
erased by a ``none`` label.  Only actual USER words can witness an asserted
application; candidate text is a classification target and never evidence.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


_WORDS = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.I)
_STOP = frozenset({
    "a", "an", "the", "my", "your", "our", "their", "his", "her", "its",
    "i", "you", "we", "they", "it", "this", "that", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "am", "has", "have",
    "had", "do", "does", "did", "can", "could", "may", "might", "would",
    "will", "should", "must", "not", "never", "only", "just", "really",
    "actually", "still", "also", "itself", "because", "of", "by", "for",
    "to", "at", "in", "on", "with", "from", "while", "when", "and", "if",
    "isn't", "aren't", "wasn't", "weren't", "doesn't", "don't", "didn't",
    "can't", "couldn't", "wouldn't", "won't", "shouldn't", "mustn't",
})
_NEGATION = re.compile(r"\b(?:not|never)\b|n't\b", re.I)
_MODAL = re.compile(r"\b(?:can|could|may|might|would)\b", re.I)
_POSSIBILITY = re.compile(
    r"\b(?:(?:one|a|another|possible|potential|hypothetical)\s+"
    r"(?:possibility|hypothesis|explanation)|hypothetically|in\s+general|"
    r"it\s+is\s+possible|it\s+may\s+be|it\s+might\s+be)\b", re.I,
)
_OBSERVATION = re.compile(
    r"\bi\s+(?:have\s+)?(?:measured|observed|verified|confirmed|found|checked|tested)\b",
    re.I,
)
_PROPERTY = re.compile(
    r"\b(?P<subject>(?:your|my|our)\s+[a-z][\w'-]*"
    r"(?:\s+[a-z][\w'-]*){0,4}?)\s+"
    r"(?P<predicate>has|have|had|is|are|was|were|does|do|reacts?|responds?|"
    r"runs?|uses?|contains?|needs?|requires?)\s+(?P<value>[^.;!?]+)", re.I,
)
_PERCEPTION = re.compile(
    r"\b(?P<subject>you(?:'re|\s+are)|i(?:'m|\s+am))\s+"
    r"(?P<predicate>(?:(?:only|just|merely|simply)\s+)?"
    r"(?:noticing|seeing|hearing|feeling|experiencing))\s+(?P<value>[^.;!?]+)", re.I,
)
_KNOWN_PROPERTY = re.compile(
    r"\b(?P<value>(?:known|established|normal|typical)\s+"
    r"(?:behaviour|behavior|property|feature|quirk))\s+of\s+"
    r"(?P<subject>(?:your|my|our)\s+[a-z][\w'-]*(?:\s+[a-z][\w'-]*){0,3})", re.I,
)


def _literal(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("’", "'").strip())


def _lemma(word: str) -> str:
    if word.endswith("ing") and len(word) > 5:
        word = word[:-3]
        if len(word) > 2 and word[-1] == word[-2]:
            word = word[:-1]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("s") and len(word) > 3 and not word.endswith("ss"):
        word = word[:-1]
    return word


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_lemma(word.lower()) for word in _WORDS.findall(value)
                               if word.lower() not in _STOP))


def _clauses(unit: str) -> list[str]:
    # Contrasts and independently introduced participant clauses delimit scope.
    # Do not split every comma: an if-clause and its genuinely modal consequent
    # can remain one bounded hypothetical.
    return [piece.strip(" ,") for piece in re.split(
        r";|\b(?:but|however|yet|whereas)\b|"
        r",\s*(?:and\s+)?(?=(?:your|you(?:'re)?|it(?:'s)?|this|that|the)\b)|"
        r"\band\s+(?=(?:your|you(?:'re)?|it(?:'s)?|this|that)\b)", unit, flags=re.I,
    ) if piece.strip(" ,")]


def _nonasserted_scope(clause: str, before: str) -> bool:
    """An epistemic limit does not assert the proposition it refuses to infer."""
    return bool(re.search(
        r"\b(?:does\s+not|doesn't|do\s+not|don't|cannot|can't|could\s+not|couldn't)\s+"
        r"(?:alone\s+)?(?:establish|prove|confirm|show|mean|know|infer|conclude|say|"
        r"claim|tell|verify|determine)\b[^.;!?]{0,160}$|"
        r"\b(?:we|i)\s+(?:do\s+not|don't)\s+know\b[^.;!?]{0,160}$|"
        r"\bno\s+(?:(?:reliable|sufficient|available)\s+)?(?:evidence|support)\b[^.;!?]{0,160}$|"
        r"\b(?:is|has\s+been)\s+not\s+(?:established|proven|verified|confirmed)\b[^.;!?]{0,160}$",
        before, re.I,
    ))


def _mode(clause: str, before: str) -> str:
    # An affirmative assertion following an initial if is still separately
    # checked.  Only the proposition's own modal/possibility scope is safe.
    if _POSSIBILITY.search(before) or _MODAL.search(before):
        return "conditional"
    if re.match(r"\s*(?:if|unless|assuming|supposing|suppose)\b", before, re.I):
        # The antecedent itself is hypothetical. A comma ends that scope.
        if "," not in before:
            return "conditional"
    if clause.rstrip().endswith("?"):
        return "conditional"
    return "asserted"


def _polarity(before: str) -> str:
    return "negative" if _NEGATION.search(before) else "positive"


def _bounded_limitation_value(value: str) -> bool:
    """A complete epistemic-limitation complement asserts no new mechanism."""
    return bool(re.fullmatch(
        r"(?:(?:still|currently|as\s+yet)\s+)?(?:unknown|unclear|unestablished|"
        r"unverified|unmeasured|unconfirmed|not\s+(?:yet\s+)?"
        r"(?:known|clear|established|verified|determined|identified|observed))",
        value.strip(" .!?"), re.I,
    ))


def _obligation(index: int, kind: str, clause: str, before: str, predicate: str,
                subject: str, value: str) -> dict[str, Any]:
    return {
        "sentence_index": index,
        "kind": kind,
        "candidate_span": clause,
        "mode": _mode(clause, before),
        "predicate": predicate,
        "polarity": _polarity(before),
        "exclusive": bool(re.search(r"\b(?:only|sole|exclusively)\b", clause, re.I)),
        "subject_tokens": _tokens(subject),
        "value_tokens": _tokens(value),
    }


def _clause_obligations(index: int, clause: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    passive = re.search(r"\bcaused\s+by\s+", clause, re.I)
    if passive and not _nonasserted_scope(clause, clause[:passive.start()]):
        left, right = clause[:passive.start()], clause[passive.end():]
        found.append(_obligation(index, "causal_application", clause, left, "causal",
                                 right, left))
    for match in re.finditer(r"\b(?:causes?|caused|causing|explains?|explained|makes?|making)\b", clause, re.I):
        if passive and match.start() == passive.start():
            continue
        left, right = clause[:match.start()], clause[match.end():]
        if match.group(0).lower() in {"explain", "explains", "explained"} and (
                re.match(r"\s*(?:(?:please|kindly)\s+)?explain\b", clause, re.I)
                or re.match(r"\s*(?:can|could|would|will)\s+(?:you|i|we)\s+(?:please\s+)?explain\b", clause, re.I)
                or re.fullmatch(r"\s*(?:i|you|we)\s+(?:can|could|will|would)\s*", left, re.I)):
            # Asking for an explanation or offering to explain has no asserted
            # cause/effect relation to bind. Lexical overlap is not enough.
            continue
        predicate_word = match.group(0).lower()
        if predicate_word in {"cause", "causes"} and (
                re.search(r"\b(?:a|an|the|its|only|known|likely|possible)\s*$", left, re.I)
                or (predicate_word == "cause" and re.search(r"\b(?:this|that|one)\s*$", left, re.I))
                or re.match(r"\s+(?:is|are|was|were|remains?|seems?|includes?)\b", right, re.I)):
            continue
        # A terminal noun such as 'does not identify a cause.' has no
        # proposition object. Merely mentioning a cause is not asserting one.
        if not _WORDS.search(left) or not _WORDS.search(right) or _nonasserted_scope(clause, left):
            continue
        found.append(_obligation(index, "causal_application", clause, left, "causal",
                                 left, re.sub(r"\bhappen(?:ing)?\b", "", right, flags=re.I)))
    because = re.search(r"\b(?:because(?:\s+of)?|due\s+to)\s+", clause, re.I)
    if because and not _nonasserted_scope(clause, clause[:because.start()]):
        left, right = clause[:because.start()], clause[because.end():]
        if left.strip() and right.strip():
            found.append(_obligation(index, "causal_application", clause, left, "causal",
                                     right, left))
    why = re.search(r"\b(?:is|are|'s)\s+why\s+", clause, re.I)
    if why and not _nonasserted_scope(clause, clause[:why.start()]):
        found.append(_obligation(index, "causal_application", clause,
                                 clause[:why.start()], "causal",
                                 clause[:why.start()], clause[why.end():]))
    reason = re.search(r"\bthe\s+reason(?:\s+for\s+(.{1,100}?))?\s+is\s+", clause, re.I)
    if reason and not _nonasserted_scope(clause, clause[:reason.start()]):
        reason_value = clause[reason.end():]
        if not re.match(r"\s*(?:(?:still|currently|as\s+yet)\s+)?"
                        r"(?:unknown|unclear|unestablished|not\s+(?:yet\s+)?"
                        r"(?:known|clear|established|verified|determined|identified))\b", reason_value, re.I):
            item = _obligation(index, "causal_application", clause,
                               clause[:reason.end()], "causal", reason_value,
                               reason.group(1) or "")
            if re.match(r"\s*(?:not|never|no)\b", reason_value, re.I):
                item["polarity"] = "negative"
            found.append(item)
    for pattern, kind in ((_PROPERTY, "actual_property"), (_PERCEPTION, "perceptual_application")):
        for match in pattern.finditer(clause):
            before = clause[:match.start()] + match.group("subject") + " " + match.group("predicate")
            if (_nonasserted_scope(clause, clause[:match.start()])
                    or _nonasserted_scope(clause, match.group(0))):
                continue
            value = re.split(r"\b(?:because|due\s+to)\b|,\s*(?:which|that)\b",
                             match.group("value"), flags=re.I)[0]
            if _bounded_limitation_value(value):
                continue
            # A property antecedent does not consume a separately asserted
            # consequent; the causal detector above checks that consequent.
            item = _obligation(index, kind, clause, before, "property", match.group("subject"), value)
            if re.match(r"\s*(?:not|never|no)\b", value, re.I):
                item["polarity"] = "negative"
            if kind == "perceptual_application":
                item["subject_tokens"] = ("participant_user",)
            found.append(item)
    known = _KNOWN_PROPERTY.search(clause)
    if known and not _nonasserted_scope(clause, clause[:known.start()]):
        found.append(_obligation(index, "actual_property", clause, clause[:known.start()],
                                 "property", known.group("subject"), known.group("value")))
    return found


def build_diagnostic_obligations(units: Sequence[str]) -> tuple[dict[str, Any], ...]:
    """Detect bounded causal/property propositions in Core-numbered units.

    Domain names, candidate origin and path identifiers play no part.  The
    returned fields are classification targets, not new evidence assertions.
    """
    found: list[dict[str, Any]] = []
    for index, raw_unit in enumerate(units, 1):
        unit = _literal(raw_unit)
        contrast = re.search(
            r"\b(?:it|this|that)(?:\s+is\s+not|\s+isn't|\s+is\s+never)\s+"
            r"(?P<excluded>[^;.!?]{1,120});\s*(?:it|this|that)(?:'s|\s+is)\s+"
            r"(?P<asserted>[^;.!?]{1,120})", unit, re.I,
        )
        if contrast:
            found.append(_obligation(index, "diagnostic_contrast", contrast.group(0), unit[:contrast.start()],
                                     "contrast", contrast.group("excluded"), contrast.group("asserted")))
        for clause in _clauses(unit):
            found.extend(_clause_obligations(index, clause))
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in found:
        key = (item["sentence_index"], item["kind"], item["mode"], item["polarity"], item["exclusive"],
               item["subject_tokens"], item["value_tokens"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return tuple(unique)


def _quote_is_asserted(source: str, quote: str) -> bool:
    start = source.find(quote)
    if start < 0:
        return False
    left = max(source.rfind(marker, 0, start) for marker in (".", "!", "?", ";")) + 1
    ends = [source.find(marker, start + len(quote)) for marker in (".", "!", "?", ";")]
    right = min((position + 1 for position in ends if position >= 0), default=len(source))
    context, prefix = source[left:right], source[left:start]
    if re.search(r"\b(?:if|unless|assuming|supposing|suppose|would|will)\b|\?", context, re.I):
        return False
    for opening, closing in (("\"", "\""), ("`", "`"), ("“", "”"), ("‘", "’")):
        if (opening == closing and prefix.count(opening) % 2) or (
                opening != closing and prefix.count(opening) > prefix.count(closing)):
            return False
    if re.search(r"(?:^|\s)'[^']*$", prefix):
        return False
    return True


def _matching_tokens(required: tuple[str, ...], available: tuple[str, ...]) -> bool:
    # Unresolved pronouns are assessed semantically, but an explicit named
    # cause/property cannot be licensed by unrelated topic overlap.
    return not required or set(required).issubset(set(available))


def _witness_matches(obligation: Mapping[str, Any], quote: str) -> bool:
    # Including quotation delimiters in a larger witness cannot promote the
    # quoted proposition to a USER assertion. Ordinary apostrophes in words
    # are not quotation delimiters.
    unquoted = re.sub(r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`|‘[^’\n]*’|(?<!\w)\x27[^\x27\n]+\x27', "", quote)
    witnesses = build_diagnostic_obligations([unquoted])
    for witness in witnesses:
        if witness["mode"] != "asserted" or witness["predicate"] != obligation["predicate"]:
            continue
        if witness["polarity"] != obligation["polarity"]:
            continue
        if obligation["exclusive"] and not witness["exclusive"]:
            continue
        if _matching_tokens(obligation["subject_tokens"], witness["subject_tokens"]) and (
                not obligation["value_tokens"] or _matching_tokens(obligation["value_tokens"], witness["value_tokens"])):
            return True
    # A directly reported observation can establish a property even when its
    # grammar is 'I measured X in Y' rather than 'my Y has X'.  It cannot prove
    # the causal relationship between that property and a separate symptom.
    return bool(
        obligation["predicate"] == "property" and obligation["polarity"] == "positive"
        and _OBSERVATION.search(unquoted) and not _MODAL.search(unquoted)
        and not _NEGATION.search(unquoted)
        and (not obligation["exclusive"] or re.search(r"\b(?:only|sole|exclusively)\b", unquoted, re.I))
        and _matching_tokens(obligation["subject_tokens"], _tokens(unquoted))
        and _matching_tokens(obligation["value_tokens"], _tokens(unquoted))
    )


def diagnostic_obligation_violations(
    obligations: Sequence[Mapping[str, Any]], assessments: Any, user_turns: Sequence[str],
) -> list[str]:
    """Aggregate Core obligations independently of global/model labels.

    The existing mechanism protocol still supplies semantic entailment.  This
    additional check prevents ``none`` or a bare conditional label from erasing
    an actual assertion and prevents a symptom quote from becoming its cause.
    """
    if not obligations:
        return []
    malformed = "Core diagnostic obligations lacked complete typed assessments"
    unsupported = "factual-focus source-fidelity violation: a Core-detected diagnostic obligation lacked USER authority"
    if not isinstance(assessments, list):
        return [malformed]
    by_index: dict[int, Mapping[str, Any]] = {}
    for assessment in assessments:
        if not isinstance(assessment, Mapping):
            return [malformed]
        index = assessment.get("sentence_index")
        if type(index) is not int or index < 1 or index in by_index:
            return [malformed]
        by_index[index] = assessment
    violations = []
    for obligation in obligations:
        assessment = by_index.get(obligation["sentence_index"])
        if not assessment or type(assessment.get("supported")) is not bool or type(
                assessment.get("applicability_established")) is not bool or "user_witness" not in assessment:
            violations.append(malformed)
            continue
        kind = assessment.get("kind")
        if not isinstance(kind, str) or not assessment["supported"] or kind not in {"conditional_hypothesis", "supplied_mechanism"}:
            violations.append(unsupported)
            continue
        if obligation["mode"] == "conditional" and kind == "conditional_hypothesis":
            if assessment["applicability_established"] or assessment.get("user_witness") is not None:
                violations.append(malformed)
            continue
        if kind != "supplied_mechanism" or not assessment["applicability_established"]:
            violations.append(unsupported)
            continue
        witness = assessment.get("user_witness")
        if not isinstance(witness, Mapping):
            violations.append(malformed)
            continue
        turn_index, quote = witness.get("turn_index"), witness.get("quote")
        if (type(turn_index) is not int or not 1 <= turn_index <= len(user_turns)
                or not isinstance(quote, str) or not quote.strip() or len(quote) > 800
                or not isinstance(user_turns[turn_index - 1], str)
                or quote not in user_turns[turn_index - 1]):
            violations.append(malformed)
            continue
        if obligation["mode"] == "asserted" and (
                not _quote_is_asserted(user_turns[turn_index - 1], quote)
                or not _witness_matches(obligation, quote)):
            violations.append(unsupported)
    return list(dict.fromkeys(violations))
