"""Bounded Core-owned obligations for plausible personal history in social prose.

The detector identifies historical premises, not general English truth.  USER
witnesses use the same perspective-normalised grammar.  Duration, recurrence,
activity and possession remain distinct; a temporal cue cannot supply a new
activity or a more specific elapsed time.  Candidate prose is never a source.
"""
from __future__ import annotations

import re
from typing import Any, Mapping


_TIME = r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)"
_SMALL_CARDINAL = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)"
_TENS = r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
_CARDINAL = r"(?:" + _TENS + r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|" + _SMALL_CARDINAL + r")"
_HUNDREDS = r"(?:" + _CARDINAL + r"\s+hundred(?:\s+(?:and\s+)?" + _CARDINAL + r")?|" + _CARDINAL + r")"
_NUMBER = r"(?:\d+(?:\.\d+)?|" + _HUNDREDS + r"(?:\s+thousand(?:\s+(?:and\s+)?" + _HUNDREDS + r")?)?|a|an|several|many|few)"
_DURATION = re.compile(
    r"\b(?P<relation>for|in|after|before|since|over)\s+"
    r"(?:(?P<qualifier>(?:the\s+)?(?:last|past|about|nearly|almost|over|more\s+than|at\s+least))\s+)?"
    r"(?P<quantity>" + _NUMBER + r")?\s*(?P<unit>" + _TIME + r")\b|"
    r"\b(?P<open_relation>for)\s+(?P<open_time>a\s+while|some\s+time)\b", re.I,
)
_FREQUENCY = re.compile(r"\b(?:always|often|usually|regularly|routinely|habitually|repeatedly|frequently|every\s+[a-z]+)\b", re.I)
_STOP = frozenset({
    "a", "an", "the", "it", "this", "that", "those", "these", "something",
    "as",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "did", "does", "not", "never", "no", "yet", "already", "just",
    "really", "actually", "completely", "apparently", "probably", "still", "finally",
    "always", "often", "usually", "regularly", "routinely", "habitually", "repeatedly",
    "frequently", "previously", "formerly", "once", "keep", "kept", "only",
    "last", "past", "about", "nearly", "almost",
    "than", "least", "more", "some", "time", "while", "now", "then", "back", "again",
})
_IRREGULAR = {"went": "go", "gone": "go", "got": "get", "gotten": "get",
              "took": "take", "taken": "take", "made": "make", "did": "do",
              "done": "do", "wore": "wear", "worn": "wear", "saw": "see",
              "seen": "see", "held": "hold", "holding": "hold", "spent": "spend",
              "bought": "buy", "left": "leave", "lost": "lose", "kept": "keep",
              "sat": "sit", "read": "read", "slept": "sleep", "forgot": "forget",
              "forgotten": "forget", "began": "begin", "begun": "begin"}
_NUMBERS = {name: str(index) for index, name in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
     "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"))}
_NUMBERS.update({name: str(value) for name, value in (
    ("twenty", 20), ("thirty", 30), ("forty", 40), ("fifty", 50),
    ("sixty", 60), ("seventy", 70), ("eighty", 80), ("ninety", 90))})


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("’", "'").replace("‘", "'")
                  .replace("“", '"').replace("”", '"')).strip()


def _lemma(word: str) -> str:
    word = word.lower()
    if word in _IRREGULAR:
        word = _IRREGULAR[word]
    # A stable morphological stem, not a semantic synonym table.
    if word.endswith("ying") and len(word) > 5:
        return word[:-4] + "y"
    if word.endswith("ied") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ing") and len(word) > 4:
        word = word[:-3]
        if len(word) > 2 and word[-1] == word[-2]:
            word = word[:-1]
    elif word.endswith("ed") and len(word) > 3:
        word = word[:-2]
    elif word.endswith("s") and len(word) > 3 and not word.endswith("ss"):
        word = word[:-1]
    return word[:-1] if len(word) > 2 and word.endswith("e") else word


def _key(value: str, speaker: str) -> tuple[str, ...]:
    result = []
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        if token in {"i", "me", "my", "mine", "myself"}:
            token = "@" + speaker
        elif token in {"you", "your", "yours", "yourself"}:
            token = "@" + ("assistant" if speaker == "user" else "user")
        elif token in _STOP:
            continue
        else:
            token = _lemma(token)
        result.append(token)
    return tuple(result)


def _durations(value: str) -> tuple[tuple[str, str, str, str], ...]:
    result = []
    for match in _DURATION.finditer(value):
        if match.group("open_time"):
            item = (match.group("open_relation").lower(), "", "open", "while")
        else:
            quantity = (match.group("quantity") or "unspecified").lower()
            if quantity in {"a", "an"}:
                quantity = "1"
            elif re.fullmatch(_HUNDREDS + r"(?:\s+thousand(?:\s+(?:and\s+)?" + _HUNDREDS + r")?)?", quantity, re.I):
                total = current = 0
                for word in re.split(r"[-\s]+", quantity):
                    if word in _NUMBERS:
                        current += int(_NUMBERS[word])
                    elif word == "hundred":
                        current *= 100
                    elif word == "thousand":
                        total += current * 1000
                        current = 0
                quantity = str(total + current)
            item = (match.group("relation").lower(), (match.group("qualifier") or "").lower(),
                    quantity, match.group("unit").lower().rstrip("s"))
        if item not in result:
            result.append(item)
    return tuple(result)


def _scope(clause: str, start: int, quote_prefix: str = "") -> str:
    prefix = clause[:start]
    quoted_prefix = quote_prefix + prefix
    for quote in ('"', "`"):
        if quoted_prefix.count(quote) % 2:
            return "quoted"
    if re.search(r"(?:^|\s)'[^']*$", quoted_prefix):
        return "quoted"
    if clause.rstrip().endswith("?") and not re.search(r",?\s+(?:then|huh|right|eh)\?$", clause, re.I):
        return "questioned"
    if re.search(r"\b(?:if|unless|suppose|supposing|hypothetically)\b", clause, re.I):
        return "conditional"
    if re.search(r"\b(?:might|could|would|may)\b", clause, re.I):
        return "hedged"
    if re.search(r"\bwill\b|'ll\b|\bwon't\b", clause, re.I):
        return "future"
    if re.search(
        r"\b(?:i|we)\s+(?:don't|do\s+not|cannot|can't|won't|will\s+not)\s+"
        r"(?:know|claim|assert|say|infer|assume|confirm|establish)\b[^.;!?]*$|"
        r"\b(?:doesn't|does\s+not)\s+(?:mean|establish|prove|show)\b[^.;!?]*$", prefix, re.I,
    ):
        return "unasserted"
    return "asserted"


def _clauses(value: str) -> tuple[str, ...]:
    return tuple(item.strip(" ,") for item in re.split(
        r"(?<=[.!?;])\s+|\b(?:but|however|yet)\s+(?=(?:you|your|i|my|it|its|the)\b)",
        value, flags=re.I,
    ) if item.strip(" ,"))


def _owned_items(value: str, speaker: str) -> tuple[str, ...]:
    possessive = "my" if speaker == "user" else "your"
    keys = []
    for match in re.finditer(
        r"\b" + possessive + r"\s+(?P<object>[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,3}?)\s+"
        r"(?:is|was|has|had|sits?|rests?|lies?|moved|moves|belongs?)\b", value, re.I,
    ):
        key = "@user:" + " ".join(_key(match.group("object"), speaker))
        if key not in keys:
            keys.append(key)
    return tuple(keys)


def _behaviour_transitions(clause: str, speaker: str, quote_prefix: str = "") -> tuple[dict[str, Any], ...]:
    """Project bounded transitions to their prior/current behaviour premises.

    A temporal cessation in a declarative observation presents the activity as
    real even if its verb is not past tense.  The transition is not a witness:
    the same USER-only activity/polarity checks used for explicit history must
    still establish it.  Plain exhortations and hypothetical advice are outside
    this small grammar; this is not a general presupposition parser.
    """
    subject = "i" if speaker == "user" else "you"
    person = r"\b" + subject + r"(?:'ve|'d|'re|'m)?\b"
    temporal = r"\b(?:once|after|now\s+that)\s+"
    finality = person + r"\s+(?:(?:have|had)\s+)?(?:finally|already)\s+"
    patterns = [
        (temporal + person + r"\s+(?:(?:have|had)\s+)?(?:finally\s+|actually\s+)?"
         r"(?:stop(?:ped)?|quit|cease(?:d)?)\s+(?P<activity>[a-z]+ing\b[^.;!?]{0,160})", "positive"),
        (finality + r"(?:stop(?:ped)?|quit|cease(?:d)?)\s+"
         r"(?P<activity>[a-z]+ing\b[^.;!?]{0,160})", "positive"),
        (temporal + person + r"\s+(?:(?:have|had)\s+)?(?:finally\s+)?"
         r"(?:start(?:ed)?|begin|began)\s+actually\s+"
         r"(?P<activity>[a-z]+ing\b[^.;!?]{0,160}?)\s+instead\b", "negative"),
        (finality + r"(?:start(?:ed)?|begin|began)\s+actually\s+"
         r"(?P<activity>[a-z]+ing\b[^.;!?]{0,160}?)\s+instead\b", "negative"),
        (r"\bwhen\s+" + person + r"\s+(?:(?:have|had)\s+)?"
         r"(?:start(?:ed)?|begin|began)\s+actually\s+"
         r"(?P<activity>[a-z]+ing\b[^.;!?]{0,160}?)\s+instead\b", "negative"),
        (person + r"\s+(?:(?:have|had)\s+)?(?:finally\s+)?"
         r"(?:start(?:ed)?|begin|began)\s+actually\s+"
         r"(?P<activity>[a-z]+ing\b[^.;!?]{0,160}?)\s+instead\b", "negative"),
    ]
    if speaker == "user":
        # A literal USER cessation supplies both its completed transition and
        # the preceding activity.  It is never inferred from assistant text.
        patterns.append((person + r"\s+(?:(?:have|had)\s+)?"
                         r"(?:stop(?:ped)?|quit|cease(?:d)?)\s+"
                         r"(?P<activity>[a-z]+ing\b[^.;!?]{0,160})", "positive"))
    records = []
    for pattern, polarity in patterns:
        for match in re.finditer(pattern, clause, re.I):
            if any(item["activity_start"] == match.start("activity") for item in records):
                continue
            activity = re.split(
                r",|\b(?:and|or|then)\s+(?=(?:you\s+)?(?:start|begin|stop|quit|can|will|should)\b)",
                match.group("activity"), maxsplit=1, flags=re.I,
            )[0].strip(" ,")
            if not activity or len(activity) > 160:
                continue
            # The source/candidate's outer conditional, quote, question,
            # epistemic or future scope remains authoritative.  A consequence
            # elsewhere in the sentence must not hide its actual premise.
            mode = _scope(clause[:match.start("activity")] + activity,
                          match.start(), quote_prefix)
            if re.search(r"\b(?:figuratively|metaphorically|rhetorically|as\s+a\s+metaphor)\b",
                         activity, re.I) and not (
                    _DURATION.search(activity) or _FREQUENCY.search(activity)
                    or re.search(r"\b(?:and|or|because|while|since|your|my)\b", activity, re.I)):
                mode = "unasserted"
            # Generic advice can mention a transition without saying the USER
            # has performed it.  A plain imperative never matches above.
            if re.search(r"\b(?:you|i)\s+(?:should|ought\s+to|need\s+to|can|could|may|must)\b|"
                         r"\b(?:try|consider|suggest|recommend)\b", clause[:match.start()], re.I):
                mode = "conditional"
            activity_end = match.start("activity") + len(activity)
            tail = clause[activity_end:]
            if match.start() == 0 and re.match(
                r"(?:\s+instead)?\s*,\s*(?:try|consider|check|use|choose|make|take|look|ask|ensure|remember)\b", tail, re.I,
            ):
                mode = "conditional"
            prefix = clause[match.start():match.start("activity")]
            completed = bool(re.search(r"\b(?:stopped|ceased|started|began)\b", prefix, re.I)
                             or re.search(r"\b(?:have|had)\s+(?:finally\s+)?quit\b|'(?:ve|d)\s+quit\b",
                                          prefix, re.I)
                             or re.search(r"\bfinally\s+quit\b", prefix, re.I)
                             or re.match(person + r"\s+start\b", prefix, re.I))
            event = re.search(r"\b(?:stop(?:ped)?|quit|cease(?:d)?|start(?:ed)?|begin|began)\s+"
                              r"(?:actually\s+)?$", prefix, re.I)
            records.append({"span": clause[match.start():activity_end], "activity": activity,
                            "mode": mode, "polarity": polarity,
                            "start": match.start(), "activity_start": match.start("activity"),
                            "completed_body": event.group(0) + activity if completed and event else ""})
    return tuple(records)


def _premise_scope(clause: str, start: int, predicate_end: int, quote_prefix: str, *, question=False, conversational_hedge=False) -> str:
    """Scope the actual premise, not a mental state's opaque future topic."""
    local = clause[:predicate_end].rstrip("? ")
    if conversational_hedge:
        before = re.sub(r"^\s*I\s+(?:suppose|guess|reckon)\s+(?:that\s+)?", "", local[:start], flags=re.I)
        local = before + local[start:]
        start = len(before)
    if question:
        # Capability of explaining is not modality of the embedded USER fact.
        # Preserve all outer if/quote/nonassertion markers around that request.
        before = re.sub(r"\b(?:can|could|would|will)\s+(?:you|u)\s+"
                        r"(?:explain|tell|clarify|remind|say)\b", "explain", local[:start], flags=re.I)
        local = before + local[start:]
        start = len(before)
    mode = _scope(local, start, quote_prefix)
    if mode in {"future", "hedged", "conditional", "quoted", "unasserted"}:
        return "unasserted" if mode == "hedged" else mode
    return "presupposed" if question else "asserted"


def _mental_topic(value: str, speaker: str) -> dict[str, Any]:
    """Retain the concern's bounded object/proposition without asserting it."""
    target = re.sub(r"\s+(?:now|anymore|any\s+more)$", "", value.strip(" ,?!."), flags=re.I)
    question = bool(re.match(r"^(?:whether|if)\b", target, re.I))
    target = re.sub(r"^(?:that|whether|if)\s+", "", target, flags=re.I)
    negative = bool(re.search(r"\b(?:not|never)\b|n't\b", target, re.I))
    # Tense/modal and polarity remain separate fields. They are not evidence
    # for the future proposition and cannot become the OUTER concern polarity.
    target = re.sub(r"\bwon't\b", "will not", target, flags=re.I)
    target = re.sub(r"'ll\b", " will", target, flags=re.I)
    modals = tuple(item.lower() for item in re.findall(r"\b(?:will|shall|would|could|might|may)\b", target, re.I))
    # An opaque topic is not an activity witness. Preserve its literal lexical
    # form instead of stemming past/current/future propositions into one key.
    words = []
    for token in re.findall(r"[a-z0-9]+", target.lower()):
        if token in {"i", "me", "my", "mine", "myself"}:
            token = "@" + speaker
        elif token in {"you", "your", "yours", "yourself"}:
            token = "@" + ("assistant" if speaker == "user" else "user")
        elif token in {"a", "an", "the", "not", "never", "will", "shall", "would", "could", "might", "may"}:
            continue
        words.append(token)
    tokens = tuple(words)
    return {"state_target": tokens, "target_question": question,
            "target_polarity": "negative" if negative else "positive", "target_modals": modals}


def _current_activity_projections(clause: str, speaker: str, quote_prefix: str = "") -> tuple[dict[str, Any], ...]:
    """Project a bounded actual current predicate, including noun relatives.

    An outer future response does not make 'the item you are currently using'
    hypothetical.  Conversely an actual if/quote or modal on that USER predicate
    must remain non-authoritative.  This is a small activity/state grammar, not
    an inference that a discussed topic is something the user is doing.
    """
    subject = "i" if speaker == "user" else "you"
    person = r"\b" + subject
    copula = r"(?:'m|'re|\s+(?:am|are))\b"
    prefix = r"(?P<prefix>(?:(?:not|never|no\s+longer|currently|still|actually|really|just|already|now|might|may|could|would|will)\s+)*)"
    predicate = r"(?P<predicate>[a-z]+ing|stuck|occupied|engaged|busy)\b"
    tail = r"(?P<tail>[^,.;!?]{0,120})"
    direct = re.compile(person + copula + r"\s+" + prefix + predicate + tail, re.I)
    relative = re.compile(
        r"(?P<object>\*{0,2}(?:the|that|this|your|my)\*{0,2}\s+"
        r"(?:[a-z][a-z-]*\s+){0,3}?[a-z][a-z-]*)\s+(?:that\s+)?"
        + person + copula + r"\s+" + prefix + predicate + tail, re.I,
    )
    records, covered = [], []

    def project(match, *, noun_relative=False):
        local_prefix = match.group("prefix")
        if (not noun_relative and speaker == "assistant"
                and not re.search(r"\b(?:currently|now)\b", local_prefix, re.I)
                and not re.search(r"\bwhile\s+(?:(?:not|still|currently|just)\s+)*[a-z]+ing\b", clause, re.I)):
            return
        complement = re.split(r"\b(?:and|but|while|when|because|like|as\s+if)\b", match.group("tail"),
                              maxsplit=1, flags=re.I)[0].strip()
        if noun_relative:
            target = re.sub(r"^\*{0,2}(?:my|your|the|this|that)\*{0,2}\s+"
                            r"(?:(?:particular|current|ongoing)\s+)*", "", match.group("object"), flags=re.I)
            # A trailing relational preposition belongs to the predicate:
            # 'the folder you are stuck in' -> 'stuck in the folder'.
            body = match.group("predicate") + (" " + complement if complement else "") + " " + target
        else:
            body = match.group("predicate") + (" " + complement if complement else "")
        body = re.sub(r"\b(?:my|your)\s+(?=[a-z])", "the ", body, flags=re.I)
        mode = _scope(clause[:match.end()], match.start(), quote_prefix)
        if mode not in {"quoted", "conditional", "unasserted"}:
            mode = "presupposed" if noun_relative else "asserted"
        if re.search(r"\b(?:might|may|could|would)\b", local_prefix, re.I) or (
                not noun_relative and re.search(r"(?:^|[,;])\s*(?:maybe|perhaps|possibly)\s*$", clause[:match.start()], re.I)):
            mode = "unasserted"
        elif re.search(r"\bwill\b", local_prefix, re.I):
            mode = "future"
        elif not noun_relative and clause.rstrip().endswith("?"):
            mode = "questioned"
        negative = bool(re.search(r"\b(?:not|never|no\s+longer)\b", local_prefix, re.I))
        key = _key(body, speaker)
        records.append({"kind": "current_activity_state", "span": match.group(0), "body": body,
                        "mode": mode, "start": match.start(), "end": match.end(),
                        "extra": {"activity_key": key, "state_temporal": "current",
                                  "polarity": "negative" if negative else "positive",
                                  "content_tokens": key, "activity_anchor": key[0] if key else ""}})
        covered.append((match.start(), match.end()))

    for match in relative.finditer(clause):
        project(match, noun_relative=True)
    for match in direct.finditer(clause):
        if not any(start <= match.start() < end for start, end in covered):
            project(match)
    return tuple(records)


def _immediate_activity_projections(clause: str, speaker: str, quote_prefix: str = "") -> tuple[dict[str, Any], ...]:
    """Project understood USER subjects without treating every gerund as fact.

    A while-participle attached to an asserted USER predicate and a bounded
    cessation's activity premise have the same current activity identity as a
    literal USER progressive. Advice, quotations, other participants and opaque
    embedded propositions cannot supply that identity. Existing duration and
    historical transitions keep their own more specific transport.
    """
    subject = "i" if speaker == "user" else "you"
    subject_pattern = r"\b" + subject + r"(?:'m|'re|'ve|'d|\s+(?:am|are|have|had|can|could|would|might|may|will|should|must|keep|kept|[a-z]+ing))\b"
    prefixes = r"(?P<prefix>(?:(?:not|never|no\s+longer|still|currently|actually|just|already|now)\s+)*)"
    activity = r"(?P<activity>[a-z]+ing\b[^,.;!?]{0,140})"
    records = []

    def emit(match, *, start=None, mode=None):
        body = re.split(r"\b(?:and|but|while|when|because|since|like|as\s+if)\b",
                        match.group("activity"), maxsplit=1, flags=re.I)[0].strip()
        prefix = match.groupdict().get("prefix", "") or ""
        purpose = re.search(r"\s+to\s+[a-z]+\b", body, re.I)
        if purpose is not None:
            nominal = body[:purpose.start()].strip()
            # A bounded use/activity + nominal object remains an actual
            # premise before an opaque purpose tail. An infinitival attitude
            # such as 'pretending to be X' has no such object and stays outside
            # this small current-activity projection. The ordinary semantic
            # verifier still assesses the complete sentence and purpose claim.
            if len(_key(nominal, speaker)) < 2:
                return
            body = nominal
        # This projection represents an immediate predicate with bounded
        # nominal/prepositional arguments, not a claimed role, opaque thought,
        # date/duration, or proposition hidden after a gerund.
        if (not body or _DURATION.search(body) or _FREQUENCY.search(body)
                or re.search(r"\b(?:that|whether|if|is|are|was|were|has|have)\b", body, re.I)):
            return
        if re.search(r"\b(?:figuratively|metaphorically|rhetorically|as\s+a\s+metaphor)\b", body, re.I):
            # Explicitly nonliteral activity has no plausible personal-world
            # premise in this bounded clause. Other clauses remain audited.
            return
        body = re.sub(r"\s+(?:right\s+now|now|currently|at\s+the\s+moment)$", "", body, flags=re.I)
        body = re.sub(r"\b(?:my|your)\s+(?=[a-z])", "the ", body, flags=re.I)
        key = _key(body, speaker)
        if not key:
            return
        start = match.start() if start is None else start
        if mode is None:
            mode = _premise_scope(clause, start, match.end(), quote_prefix,
                                  conversational_hedge=speaker == "assistant")
        records.append({"kind": "current_activity_state", "span": clause[start:match.end()],
                        "body": body, "mode": mode, "start": start, "end": match.end(),
                        "extra": {"activity_key": key, "state_temporal": "current",
                                  "polarity": "negative" if re.search(r"\b(?:not|never|no\s+longer)\b", prefix, re.I) else "positive",
                                  "content_tokens": key, "activity_anchor": key[0]}})

    def asserted_anchor_mode(anchor, match):
        local = clause[anchor.start():match.end()]
        mode = _premise_scope(clause, match.start(), match.end(), quote_prefix,
                              conversational_hedge=speaker == "assistant")
        if mode in {"quoted", "conditional", "unasserted"}:
            return mode
        # An ordinary modal/advice frame is a possibility, not current usage.
        # 'can stop X' differs: can modifies cessation of an existing premise.
        if re.search(r"\b(?:could|might|may|would|should|must|will)\b", local, re.I) \
                or re.search(r"\bcan\b(?!\s+(?:already\s+|now\s+)?(?:stop|quit|cease)\b)", local, re.I):
            return "conditional"
        return "questioned" if clause.rstrip().endswith("?") else "asserted"

    while_pattern = re.compile(r"\bwhile\s+" + prefixes + activity, re.I)
    for match in while_pattern.finditer(clause):
        before = clause[:match.start()]
        anchors = list(re.finditer(subject_pattern, before, re.I))
        anchor = anchors[-1] if anchors else None
        if anchor is not None:
            # A later explicit participant owns the subordinate: 'you asked
            # while she ...' or 'I told you while indexing' is not USER usage.
            between = before[anchor.end():]
            if re.search(r"\b(?:i|we|he|she|they|it)\s+(?:am|is|are|was|were|have|has|can|will)\b", between, re.I):
                anchor = None
        elif not before.strip(" ,"):
            # Preposed participles inherit a following finite USER subject.
            after = clause[match.end():]
            following = re.search(subject_pattern, after, re.I)
            if following is not None:
                anchor = following
                mode = _premise_scope(clause, match.start(), len(clause), quote_prefix,
                                      conversational_hedge=speaker == "assistant")
                if re.search(r"\b(?:could|might|may|would|should|must|will|can)\b", following.group(0), re.I):
                    mode = "conditional"
                if clause.rstrip().endswith("?"):
                    mode = "questioned"
                emit(match, mode=mode)
                continue
        if anchor is not None:
            emit(match, mode=asserted_anchor_mode(anchor, match))

    if speaker == "assistant":
        # In this bounded listener-directed attribution, 'someone currently
        # doing X' is a USER premise. A named third party or an ordinary generic
        # somebody statement is outside the projection.
        someone = re.compile(r"^(?:that|this|it)(?:'s|\s+is)\s+[^,.;!?]{1,60}?\bfor\s+someone\s+"
                             r"(?:currently|now|still)\s+" + prefixes + activity, re.I)
        for match in someone.finditer(clause):
            emit(match)

        # Bare USER-directed cessation and 'waiting for you to stop X' supply
        # a CURRENT premise, not evidence that the change has occurred. USER
        # instructions target Mairon, so never enter this listener projection.
        cessation = re.compile(r"(?:^\s*(?:please\s+|just\s+)?|\bfor\s+you\s+to\s+|"
                               r"\byou\s+(?:can\s+)?(?:now\s+)?)"
                               r"(?:stop|quit|cease)\s+" + activity, re.I)
        for match in cessation.finditer(clause):
            # Existing typed concern and temporal-transition projections own
            # their stronger semantics. Do not duplicate them as usage.
            if re.match(r"(?:worrying|stressing|being\s+worried)\s+about\b", match.group("activity"), re.I):
                continue
            if re.search(r"\b(?:once|after|now\s+that|finally|already)\s+(?:you\s+)?$", clause[:match.start()], re.I):
                continue
            mode = _premise_scope(clause, match.start(), match.end(), quote_prefix,
                                  conversational_hedge=True)
            if mode not in {"quoted", "conditional", "unasserted"}:
                mode = "presupposed"
            if clause.rstrip().endswith("?"):
                # Ordinary yes/no questions ask about the transition. The
                # existing wh projection owns actual why/when premises.
                mode = "questioned"
            if re.search(r"\b(?:for\s+example|example|sample)\s*[:,]?\s*$", clause[:match.start()], re.I):
                mode = "quoted"
            # A compound instruction is a generic step, not a claim that the
            # listener already performs its first instruction's activity.
            if re.search(r"\b(?:and|then)\s+(?:check|use|choose|take|look|ask|ensure|remember|inspect)\b",
                         match.group("activity"), re.I):
                mode = "conditional"
            emit(match, mode=mode)
    return tuple(records)


def _personal_record_projections(clause: str, speaker: str, quote_prefix: str = "") -> tuple[dict[str, Any], ...]:
    """A literal record of USER activity contains a premise despite 'can'.

    Ordinary capability questions and advice are not records of behaviour.
    Neither an unrelated lapse nor topic overlap establishes the record or its
    embedded activity; the matching record must come from an actual USER source.
    """
    subject = "i" if speaker == "user" else "you"
    pattern = re.compile(r"\b(?P<record>(?:(?:a|the|my|your|new|personal|previous|longest)\s+)*record)\s+"
                         r"(?:for|of)\s+how\s+long\s+" + subject + r"\s+(?:can\s+)?"
                         r"(?P<activity>[a-z]+\b[^.;!?]{0,160})", re.I)
    records = []
    for match in pattern.finditer(clause):
        activity = match.group("activity").split(",", 1)[0].strip()
        if re.search(r"\b(?:figuratively|metaphorically|rhetorically|hypothetically)\b", activity, re.I):
            continue
        mode = _scope(clause[:match.end()], match.start(), quote_prefix)
        if re.match(r"^(?:maybe|perhaps|possibly)\b", clause, re.I):
            mode = "unasserted"
        key = _key(activity, speaker)
        record_type = tuple(word.lower() for word in re.findall(r"\b(?:new|personal|previous|longest)\b", match.group("record"), re.I))
        negative = bool(re.search(r"\b(?:not|never|isn't|wasn't)\s*$", clause[:match.start()], re.I))
        records.append({"kind": "personal_activity_record", "span": match.group(0), "body": activity,
                        "mode": mode, "start": match.start(), "end": match.end(),
                        "extra": {"record_type": record_type, "activity_key": key,
                                  "polarity": "negative" if negative else "positive",
                                  "content_tokens": key, "activity_anchor": key[0] if key else ""}})
    return tuple(records)


def _state_projections(clause: str, speaker: str, quote_prefix: str = "") -> tuple[dict[str, Any], ...]:
    """Bounded hidden USER-state premises; ordinary questions stay questions.

    Core identifies these propositions before semantic judgement. All matching
    still needs a literal authoritative USER source. The grammar is intentionally
    small: wh-presuppositions, concern cessation and explicit current tasks.
    """
    subject = "i" if speaker == "user" else "you"
    possessive = "my" if speaker == "user" else "your"
    person = r"\b" + subject + r"(?:'ve|'d|'re|'m)?\b"
    specs = list(_current_activity_projections(clause, speaker, quote_prefix))
    specs.extend(_personal_record_projections(clause, speaker, quote_prefix))
    specs.extend(_immediate_activity_projections(clause, speaker, quote_prefix))

    def record(kind, match, body, mode, **extra):
        specs.append({"kind": kind, "span": match.group(0), "body": body, "mode": mode,
                      "start": match.start(), "end": match.end(), "extra": extra})

    # Interrogative syntax does not erase the asserted proposition inside why
    # or when. Yes/no completion, worry and current-activity questions do not
    # enter this family. Ordinary outer if/quote/future scope still applies.
    auxiliary = r"(?:have|haven't|had|hadn't|do|don't|did|didn't|are|aren't|were|weren't|was|wasn't|am|am\s+not)"
    wh_patterns = (
        r"\b(?:why|when)\s+(?P<aux>" + auxiliary + r")\s+" + person + r"\s+(?P<tail>[^.;!?]{1,160})",
        r"\b(?:why|when)\s+" + person + r"\s+(?P<aux>" + auxiliary + r")\s+(?P<tail>[^.;!?]{1,160})",
        r"\b(?:why|when)\s+" + person + r"\s+(?P<aux>)(?P<tail>(?:[a-z]+ed|quit|"
        + "|".join(_IRREGULAR) + r")\b[^.;!?]{0,140})",
    )
    wh = []
    for pattern in wh_patterns:
        for match in re.finditer(pattern, clause, re.I):
            tail = match.group("tail").split(",", 1)[0].strip()
            if not tail or re.search(r"\b(?:could|might|may|would|will|if|unless)\b", tail, re.I):
                continue
            # Restrict the predicate class. A wh word alone is not permission
            # to treat every topic or imagined question as a personal fact.
            if not re.match(r"(?:(?:still|already|not|never|always|usually|just)\s+)*"
                            r"(?:[a-z]+ing|[a-z]+ed|finish|complete|stop|quit|start|continue|"
                            r"worry|stress|use|do|work|read|rely|have|keep|" + "|".join(_IRREGULAR) + r")\b",
                            tail, re.I):
                continue
            mode = _premise_scope(clause, match.start(), match.end(), quote_prefix, question=True)
            body = match.group("aux") + " " + tail
            temporal = ("current" if match.group("aux").lower() in {"are", "aren't", "am", "am not", "do", "don't"}
                        else "past" if match.group("aux").lower() in {"", "did", "didn't", "was", "wasn't", "were", "weren't", "had", "hadn't"}
                        else "perfect")
            record("embedded_user_state", match, body, mode, state_temporal=temporal)
            wh.append((match, body, mode))

    mental = r"(?:worry(?:ing|ied)?|worried|stress(?:ing|ed)?)"
    # A cessation/deontic statement presupposes POSITIVE concern; don't/can
    # modify the need to continue, not whether the USER had that concern.
    cessation = re.compile(person + r"\s+(?:(?:can|may|might|could|should|now)\s+)*"
                            r"(?:(?:don't|do\s+not|no\s+longer)\s+(?:have|need)\s+to\s+)?"
                            r"(?:stop|quit|cease|keep)\s+(?:being\s+)?(?P<mental>" + mental + r")\s+"
                            r"(?P<link>about|that|whether|if)\s+(?P<target>[^.;!?]{1,180})", re.I)
    direct = re.compile(person + r"\s+(?P<prefix>(?:(?:have|had|am|are|was|were|been|not|never|do|don't|didn't|"
                          r"still|already|really|always|usually|will|might|could|would|be)\s+)*)"
                        r"(?P<mental>" + mental + r")\s+(?P<link>about|that|whether|if)\s+"
                        r"(?P<target>[^.;!?]{1,180})", re.I)
    mental_matches = []
    for pattern, transition in ((cessation, True), (direct, False)):
        for match in pattern.finditer(clause):
            if any(old[0] <= match.start() < old[1] for old in mental_matches):
                continue
            target = match.group("target").split(",", 1)[0]
            topic = _mental_topic((match.group("link") + " " if match.group("link").lower() != "about" else "")
                                  + target, speaker)
            if not topic["state_target"] or len(topic["state_target"]) > 32:
                continue
            mode = _premise_scope(clause, match.start(), match.start("mental"), quote_prefix,
                                  conversational_hedge=transition and speaker == "assistant")
            if not transition and clause.rstrip().endswith("?"):
                mode = "questioned"
            prefix = match.group("prefix") if not transition else ""
            outer_negative = bool(re.search(r"\b(?:not|never|don't|didn't)\b", prefix, re.I))
            past_state = bool(re.search(r"\b(?:was|were|had)\b", prefix, re.I)
                              or not transition and match.group("mental").lower().endswith("ed")
                              and not re.search(r"\b(?:am|are|been)\b", prefix, re.I)
                              and not re.search(r"'(?:m|re)\b", match.group(0)[:match.start("mental") - match.start()], re.I))
            body = ("not " if outer_negative else "") + "concern"
            record("mental_state_presupposition" if transition else "mental_state", match, body, mode,
                   **topic, state_type="concern", state_temporal="past" if past_state else "current",
                   polarity="negative" if outer_negative else "positive",
                   content_tokens=("concern",) + topic["state_target"],
                   activity_anchor="concern")
            mental_matches.append((match.start(), match.end()))

    def task_fields(target, *, current=False):
        target = re.sub(r"\s+(?:yet|now|anymore|at\s+the\s+moment)$", "", target.strip(" ,?!."), flags=re.I)
        noun = re.fullmatch(r"(?P<owner>my|your|the|this|that)\s+"
                            r"(?P<qualifiers>(?:(?:current|unfinished|ongoing|incomplete|existing)\s+)*)"
                            r"(?P<name>[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,3})", target, re.I)
        if not noun:
            return None
        flags = tuple(noun.group("qualifiers").lower().split())
        return {"task_key": _key(noun.group("name"), speaker),
                "task_current": current or "current" in flags or "ongoing" in flags,
                "task_owned": noun.group("owner").lower() == possessive,
                "task_unfinished": "unfinished" in flags or "incomplete" in flags,
                "task_qualifiers": tuple(flag for flag in flags if flag not in {"current", "unfinished", "ongoing", "incomplete"})}

    def task_record(match, target, mode, *, unfinished=None, current=False, temporal="current"):
        fields = task_fields(target, current=current)
        if fields is None or not fields["task_key"]:
            return False
        task = " ".join(fields["task_key"])
        fields["task_temporal"] = temporal
        if unfinished is None and fields["task_unfinished"]:
            unfinished = True
        if unfinished is True:
            fields["task_unfinished"] = True
        if fields["task_owned"]:
            record("user_task_identity", match, task, mode, **fields,
                   content_tokens=fields["task_key"], activity_anchor="task", owned_predicate="task")
        if unfinished is not None:
            record("task_completion_presupposition", match, ("not " if unfinished else "") + "finish " + task,
                   mode, **fields, content_tokens=("finish",) + fields["task_key"],
                   activity_anchor="finish", owned_predicate="completion",
                   polarity="negative" if unfinished else "positive")
        return True

    for match, body, mode in wh:
        completed = re.search(r"\b(?P<verb>finish(?:ed)?|complete(?:d)?)\s+(?P<target>[^.;!?]{1,120})", body, re.I)
        if completed:
            negative = bool(re.search(r"\bnot\b|n't\b", body[:completed.start()], re.I))
            # The wh projection and typed completion describe the SAME fact;
            # do not leave a second generic key whose possessive/qualifier
            # rendering defeats a legitimate progress witness.
            if task_record(match, completed.group("target"), mode, unfinished=negative, current=True,
                           temporal="past" if re.match(r"(?:had|hadn't|did|didn't)\b", body, re.I) else "current"):
                specs[:] = [item for item in specs if not (item["kind"] == "embedded_user_state" and item["span"] == match.group(0))]
        else:
            owned_task = re.search(r"\b" + possessive + r"\s+(?:(?:current|unfinished|ongoing|incomplete)\s+)+"
                                   r"[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,2}", body, re.I)
            if owned_task:
                task_record(match, owned_task.group(0), mode, current=True)

    if speaker == "user":
        # Literal explicit progress establishes noncompletion only for this
        # same task. Re-entry into another activity is never a progress proof.
        progress = re.compile(person + r"\s+(?:am\s+)?(?P<progress>(?:halfway|partway|partially)\s+"
                               r"(?:through|done\s+with)|(?:working|making\s+progress)\s+on)\s+"
                               r"(?P<target>[^.;!?]{1,120})", re.I)
        for match in progress.finditer(clause):
            task_record(match, match.group("target").split(",", 1)[0],
                        _premise_scope(clause, match.start(), match.end(), quote_prefix),
                        unfinished=True if re.match(r"(?:halfway|partway|partially)\b", match.group("progress"), re.I) else None,
                        current=True)
        completion = re.compile(person + r"\s+(?P<prefix>(?:(?:have|haven't|had|hadn't|not|never|already|still|"
                                 r"do|don't|didn't)\s+)*)"
                                r"(?P<verb>finish(?:ed)?|complete(?:d)?)\s+(?P<target>[^.;!?]{1,120})", re.I)
        for match in completion.finditer(clause):
            mode = _premise_scope(clause, match.start(), match.end(), quote_prefix)
            if clause.rstrip().endswith("?"):
                mode = "questioned"
            negative = bool(re.search(r"\b(?:not|never|don't|didn't)\b|n't\b", match.group("prefix"), re.I))
            task_record(match, match.group("target").split(",", 1)[0], mode,
                        unfinished=negative, current=True,
                        temporal="past" if re.search(r"\b(?:had|hadn't)\b", match.group("prefix"), re.I)
                        else "current")
        owned = re.compile(r"\bmy\s+(?:(?:current|unfinished|ongoing|incomplete|existing)\s+)*"
                           r"[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,2}?(?=\s+(?:is|was|has|had)\b|[.!?;]|$)", re.I)
        for match in owned.finditer(clause):
            if any(item["kind"] == "user_task_identity" and item["start"] <= match.start() < item["end"]
                   for item in specs):
                # A bare owned noun inside an explicit progress/completion
                # record does not erase that same statement's status facet.
                continue
            mode = _premise_scope(clause, match.start(), match.end(), quote_prefix)
            if clause.rstrip().endswith("?"):
                mode = "questioned"
            past_owned = bool(re.match(r"\s+(?:was|had)\b", clause[match.end():], re.I))
            task_record(match, match.group(0), mode, current=not past_owned,
                        temporal="past" if past_owned else "current")
        absent = re.compile(person + r"\s+(?:(?:don't|do\s+not)\s+have\s+(?:(?:a|any|my)\s+)?|have\s+no\s+)"
                            r"(?P<target>current\s+[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,2})", re.I)
        for match in absent.finditer(clause):
            mode = _premise_scope(clause, match.start(), match.end(), quote_prefix)
            if clause.rstrip().endswith("?"):
                mode = "questioned"
            fields = task_fields("my " + match.group("target"), current=True)
            if fields is not None:
                record("user_task_identity", match, "not " + " ".join(fields["task_key"]), mode,
                       **fields, content_tokens=fields["task_key"], polarity="negative",
                       activity_anchor="task", owned_predicate="task", task_temporal="current")
    return tuple(specs)


def detect_user_history(text: str, *, speaker: str = "assistant", preserve_occurrences: bool = False) -> tuple[dict[str, Any], ...]:
    """Detect bounded literal historical propositions in either perspective.

    Ordinary emotions/preferences and an isolated current event remain outside
    this grammar, except for the bounded concern-state projections above.
    Prior perfect/progressive activity, elapsed time,
    recurrence, possession/location and bounded behaviour presuppositions are
    inspectable candidates.  USER present-progressive activity may witness a
    transition's premise without supplying cessation or another activity.
    """
    if speaker not in {"user", "assistant"}:
        raise ValueError("invalid history perspective")
    value = _text(text)
    records = []
    subject = "i" if speaker == "user" else "you"
    possessive = "my" if speaker == "user" else "your"
    personal = re.compile(r"\b" + subject + r"(?:'ve|'d|'re|'m)?\b(?P<body>[^.;!?]{1,240})", re.I)

    def add(kind: str, span: str, body: str, mode: str, *, owner: str = "@user", owned_predicate: str = "", extra=None):
        duration = _durations(body)
        frequency = tuple(item.lower() for item in _FREQUENCY.findall(body))
        if re.search(r"\b(?:keep|kept)\s+[a-z]+ing\b", body, re.I):
            frequency += ("repeated",)
        # Duration/frequency are separate invariant dimensions.  Removing them
        # here cannot turn lexical overlap into proof of elapsed time.
        content = _DURATION.sub(" ", body)
        content = _FREQUENCY.sub(" ", content)
        negative = bool(re.search(r"\b(?:not|never)\b|n't\b", content, re.I))
        ordering = tuple(item.lower() for item in re.findall(r"\b(?:before|after|since|until)\b", content, re.I))
        content = re.sub(r"\bused\s+to\s+", " ", content, flags=re.I)
        content = re.sub(r"n't\b|\b(?:have|has|had|was|were|are|am|did|do)\b|'ve\b|'d\b|'re\b|'m\b", " ", content, flags=re.I)
        tokens = _key(content, speaker)
        # Re-entry proves an interruption only; it supplies neither a duration
        # nor neglect/avoidance of the activity during that interruption.
        interruption = bool(re.search(r"\b(?:got\s+back\s+(?:to|into)|resumed|returned\s+to)\b", body, re.I))
        if re.search(r"\b(?:took|taking|taken|had)\s+(?:a\s+)?(?:break|pause)\b", body, re.I):
            interruption = True
        interruption_content = tuple(token for token in tokens
                                     if token not in {"get", "tak", "break", "paus", "resum", "return", "from", "to", "into"})
        record = {"kind": kind, "candidate_span": span, "subject": owner,
                  "mode": mode, "polarity": "negative" if negative else "positive",
                  "content_tokens": tokens, "duration": duration, "frequency": frequency,
                  "ordering": ordering,
                  "activity_anchor": tokens[0] if tokens else "", "owned_predicate": owned_predicate,
                  "interruption_only": interruption and not duration and not frequency,
                  "interruption_content": interruption_content}
        if extra:
            record.update(extra)
        if preserve_occurrences or record not in records:
            records.append(record)

    offset = 0
    for clause in _clauses(value):
        start = value.find(clause, offset)
        quote_prefix = value[:start] if start >= 0 else ""
        offset = start + len(clause) if start >= 0 else offset
        projected_states = _state_projections(clause, speaker, quote_prefix)
        for item in projected_states:
            add(item["kind"], item["span"], item["body"], item["mode"], extra=item["extra"])
        transitions = _behaviour_transitions(clause, speaker, quote_prefix)
        for transition in transitions:
            premise = transition["activity"]
            if transition["polarity"] == "negative":
                premise = "not " + premise
            add("behaviour_presupposition", transition["span"], premise, transition["mode"])
            if transition["completed_body"]:
                add("prior_activity", transition["span"], transition["completed_body"], transition["mode"])
        for match in personal.finditer(clause):
            if any(item["kind"] not in {"current_activity_state", "personal_activity_record"}
                   and item["start"] <= match.start() < item["end"] for item in projected_states):
                continue
            if any(item["start"] <= match.start() < item["activity_start"] for item in transitions):
                # The typed projections above preserve the premise and, where
                # asserted, the completed change.  Do not fold the following
                # consequence into that history proposition's activity key.
                continue
            body = match.group("body")
            mode = _scope(clause, match.start(), quote_prefix)
            # Expand subject contractions solely for grammatical recognition.
            expanded = match.group(0).replace("'ve", " have").replace("'d", " had")
            history = bool(re.search(
                r"\b(?:have|haven't|had|hadn't)\s+(?:not\s+)?(?:[a-z]+ly\s+|completely\s+|already\s+|still\s+|never\s+)*"
                r"(?:been|[a-z]+ed|" + "|".join(_IRREGULAR) + r")\b|"
                r"\b(?:was|were)\s+(?:[a-z]+ly\s+)?[a-z]+ing\b|"
                r"\bused\s+to\s+[a-z]+\b|\b(?:previously|formerly|once)\s+"
                r"(?!(?:you|your|i|my)\b)[a-z]+\b|"
                r"\b(?:got\s+back\s+(?:to|into)|resumed|returned\s+to|took\s+(?:a\s+)?(?:break|pause))\b",
                expanded, re.I,
            ))
            duration = bool(_DURATION.search(body))
            habitual = bool(_FREQUENCY.search(body) or re.search(r"\b(?:keep|kept)\s+[a-z]+ing\b", body, re.I))
            ongoing_user = speaker == "user" and bool(re.match(
                r"(?:am|'m)\s+(?:not\s+)?(?:[a-z]+ly\s+)*[a-z]+ing\b",
                expanded[len(subject):].strip(), re.I,
            ))
            present_user_state = speaker == "user" and bool(re.match(
                r"(?:am|'m)\s+(?:not\s+)?[a-z]+\b",
                expanded[len(subject):].strip(), re.I,
            ))
            affect_transform = bool(re.fullmatch(
                r"(?:have|haven't|had|hadn't)\s+(?:not\s+)?been\s+[a-z]+ed\s+"
                r"(?:emotionally|figuratively|metaphorically|rhetorically)"
                r"(?:\s+by\s+(?:this|that|the)\s+[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,3})?",
                expanded[len(subject):].strip(), re.I,
            ))
            if affect_transform and not duration and not habitual:
                # Explicitly affective/figurative passive transformations do
                # not by aspect alone acquire a literal historical activity.
                # Concrete time, recurrence, personal-agent or extra-clause
                # premises are never covered by this bounded form.  Existing
                # semantic grounding still checks any referenced entity.
                history = False
            if duration or habitual or history or ongoing_user or present_user_state:
                add("duration" if duration else "habitual_activity" if habitual else
                    "prior_activity" if history else "current_activity" if ongoing_user else "current_state",
                    match.group(0), body, mode)

        # An imperative addresses the user without requiring a literal 'you'.
        # Only a concrete duration/recurrence or interim-activity premise is
        # audited; plain exhortations do not become asserted user history.
        implicit = re.search(r"\b(?:stop|quit)\s+[^.;!?]{0,100}?\b(?:while|after|before)\s+(?P<body>[^.;!?]{1,160})", clause, re.I)
        if (implicit and (_DURATION.search(implicit.group("body")) or re.match(r"[a-z]+ing\b", implicit.group("body"), re.I))
                and not any(item["kind"] == "current_activity_state"
                            and implicit.start("body") >= item["start"]
                            and implicit.start("body") < item["end"] for item in projected_states)):
            add("interim_activity", implicit.group(0), implicit.group("body"), _scope(clause, implicit.start(), quote_prefix))

        if speaker == "assistant":
            returning = re.match(
                r"(?:welcome\s+back|back|finally\s+back)\s+(?P<body>after\s+[^.;!?]{1,180})", clause, re.I,
            )
            if returning and _DURATION.search(returning.group("body")):
                body = re.sub(r",?\s+(?:then|huh|right|eh)$", "", returning.group("body"), flags=re.I)
                add("duration", returning.group(0), body, _scope(clause, returning.start(), quote_prefix))

        owned = re.search(
            r"\b" + possessive + r"\s+(?P<object>[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,3}?)\s+"
            r"(?P<body>(?:was|were|had|used\s+to|is|has|usually|always|often|regularly|"
            r"routinely|habitually|previously|formerly)\s+[^.;!?]{1,180})", clause, re.I,
        )
        if owned and (_DURATION.search(owned.group("body")) or _FREQUENCY.search(owned.group("body"))
                      or re.match(r"(?:was|were|had|used\s+to|previously|formerly)\b", owned.group("body"), re.I)):
            object_key = _key(owned.group("object"), speaker)
            add("owned_history", owned.group(0), owned.group("object") + " " + owned.group("body"),
                _scope(clause, owned.start(), quote_prefix), owner="@user:" + " ".join(object_key),
                owned_predicate=("be" if re.match(r"(?:was|were|is)\b", owned.group("body"), re.I)
                                 else "have" if re.match(r"(?:had|has)\b", owned.group("body"), re.I)
                                 else "activity"))

        # Historical location/possession is an obligation even if the candidate
        # uses 'its' rather than falsely claiming a new explicit USER owner.
        habitual_noun = re.search(
            r"\b(?P<owner>" + possessive + r"|its|the)\s+(?P<body>(?:usual|customary|habitual|previous|former)\s+"
            r"[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,4})", clause, re.I,
        )
        if habitual_noun:
            owner = "@user" if habitual_noun.group("owner").lower() == possessive else "unresolved_item"
            local_items = _owned_items(clause, speaker)
            if owner == "unresolved_item" and len(local_items) == 1:
                owner = local_items[0]
            add("habitual_state", habitual_noun.group(0), habitual_noun.group("body"),
                _scope(clause, habitual_noun.start(), quote_prefix), owner=owner)

    for index, record in enumerate(records, 1):
        record["index"] = index
    return tuple(records)


def _compatible(candidate: Mapping[str, Any], witness: Mapping[str, Any]) -> bool:
    if witness["mode"] not in {"asserted", "presupposed"} or candidate["polarity"] != witness["polarity"]:
        return False
    if candidate["subject"] == "unresolved_item" or candidate["subject"] != witness["subject"]:
        return False
    if candidate["kind"] == "current_activity_state":
        return (witness["kind"] == "current_activity_state"
                and candidate.get("activity_key") == witness.get("activity_key")
                and candidate.get("state_temporal") == witness.get("state_temporal"))
    if candidate["kind"] == "personal_activity_record":
        return (witness["kind"] == "personal_activity_record"
                and candidate.get("activity_key") == witness.get("activity_key")
                and candidate.get("record_type") == witness.get("record_type"))
    if candidate["kind"] in {"mental_state_presupposition", "mental_state"}:
        if (witness["kind"] != "mental_state" or witness.get("state_type") != candidate.get("state_type")
                or witness.get("state_temporal") != ("current" if candidate["kind"] == "mental_state_presupposition"
                                                      else candidate.get("state_temporal"))
                or candidate.get("state_target") != witness.get("state_target")
                or candidate.get("target_modals") != witness.get("target_modals")
                or (not candidate.get("target_question")
                    and candidate.get("target_polarity") != witness.get("target_polarity"))):
            return False
    if candidate["kind"] in {"user_task_identity", "task_completion_presupposition"}:
        if (witness["kind"] != candidate["kind"] or candidate.get("task_key") != witness.get("task_key")
                or candidate.get("task_qualifiers") != witness.get("task_qualifiers")
                or candidate.get("task_temporal") != witness.get("task_temporal")
                or (candidate.get("task_current") and not witness.get("task_current"))
                or (candidate.get("task_unfinished") and not witness.get("task_unfinished"))
                or (candidate.get("task_owned") and not witness.get("task_owned"))):
            return False
    if witness["kind"] in {"current_activity", "current_state", "current_activity_state"} and not (
            candidate["kind"] == "behaviour_presupposition"
            or candidate["kind"] == "embedded_user_state" and candidate.get("state_temporal") == "current"):
        # A supplied present activity/state can establish the premise of a
        # present transition.  It does not establish its cessation, a past
        # habit or a prior state merely because the lexical activity matches.
        return False
    if (candidate["duration"] != witness["duration"] or candidate["frequency"] != witness["frequency"]
            or candidate["ordering"] != witness["ordering"]):
        return False
    if candidate["interruption_only"] and witness["interruption_only"]:
        # A bare interruption is a temporal consequence of explicit re-entry.
        # The ordinary semantic verifier still checks topic/referent fidelity.
        return not candidate["interruption_content"] or candidate["interruption_content"] == witness["interruption_content"]
    if (candidate["activity_anchor"] != witness["activity_anchor"]
            or candidate["owned_predicate"] != witness["owned_predicate"]):
        return False
    content = candidate["content_tokens"]
    return bool(content) and content == witness["content_tokens"]


def user_history_witnessed(candidate: Mapping[str, Any], quote: str, *, source_text: str) -> bool:
    """Require a literal USER quote whose complete scope proves this premise."""
    source, literal = _text(source_text), _text(quote)
    if not literal or len(literal) > 600 or literal not in source:
        return False
    # Parse the complete source, preventing an omitted 'if' or quote delimiter
    # from laundering a non-asserted proposition into an affirmative witness.
    for full in detect_user_history(source, speaker="user"):
        if full["candidate_span"] in literal and _compatible(candidate, full):
            return True
    return False


def _current_history_contradiction(candidate: Mapping[str, Any], current_user: str) -> bool:
    """Latest explicit matching USER proposition overrides older polarity.

    This is deliberately narrower than general correction interpretation.  It
    compares the same bounded activity and arguments, not synonyms or the
    interruption consequence of re-entry; negative re-entry alone does not
    establish that no interruption happened.
    """
    facets = ("subject", "content_tokens", "duration", "frequency", "ordering",
              "activity_anchor", "owned_predicate", "interruption_only")
    matching = [item for item in detect_user_history(current_user, speaker="user", preserve_occurrences=True)
                if item["mode"] in {"asserted", "presupposed"}
                and (item["kind"] not in {"current_activity", "current_state", "current_activity_state"}
                     or candidate["kind"] == "behaviour_presupposition")
                and (candidate["kind"] not in {"mental_state_presupposition", "mental_state"}
                     or item["kind"] == "mental_state" and item.get("state_temporal") == candidate.get("state_temporal")
                     and candidate.get("target_modals") == item.get("target_modals")
                     and (candidate.get("target_question")
                          or candidate.get("target_polarity") == item.get("target_polarity")))
                and (candidate["kind"] not in {"user_task_identity", "task_completion_presupposition"}
                     or item["kind"] == candidate["kind"]
                     and candidate.get("task_qualifiers") == item.get("task_qualifiers")
                     and candidate.get("task_temporal") == item.get("task_temporal"))
                and all(candidate[name] == item[name] for name in facets)]
    return bool(matching and matching[-1]["polarity"] != candidate["polarity"])


def _latest_typed_state(candidate: Mapping[str, Any], sources: Mapping[str, str]):
    """Resolve only the new concern/task CURRENT states in USER turn order.

    The bounded window is supplied by Core. Older historical witnesses retain
    their existing rules; a later matching current-state correction cannot be
    bypassed by selecting an earlier positive quote.
    """
    mental = candidate["kind"] in {"mental_state_presupposition", "mental_state"}
    task = candidate["kind"] in {"user_task_identity", "task_completion_presupposition"}
    activity = candidate["kind"] == "current_activity_state"
    if not (mental or task or activity) or (mental and candidate.get("state_temporal") != "current") \
            or (task and candidate.get("task_temporal") != "current"):
        return None
    ordered = sorted((key for key in sources if re.fullmatch(r"prior_user_\d+", key)),
                     key=lambda key: int(key.rsplit("_", 1)[1]))
    if "current_user" in sources:
        ordered.append("current_user")
    latest = None
    for key in ordered:
        for item in detect_user_history(sources[key], speaker="user", preserve_occurrences=True):
            if item["mode"] not in {"asserted", "presupposed"}:
                continue
            if mental:
                matches = (item["kind"] == "mental_state" and item.get("state_temporal") == "current"
                           and item.get("state_type") == candidate.get("state_type")
                           and item.get("state_target") == candidate.get("state_target")
                           and item.get("target_modals") == candidate.get("target_modals")
                           and (candidate.get("target_question")
                                or item.get("target_polarity") == candidate.get("target_polarity")))
            elif activity:
                matches = (item["kind"] == "current_activity_state"
                           and item.get("activity_key") == candidate.get("activity_key")
                           and item.get("state_temporal") == "current")
            else:
                matches = (item["kind"] == candidate["kind"] and item.get("task_temporal") == "current"
                           and item.get("task_key") == candidate.get("task_key")
                           and item.get("task_qualifiers") == candidate.get("task_qualifiers"))
            if matches:
                latest = (key, item)
    return latest


def _resolve_current_concern(candidate: Mapping[str, Any], current_user: str) -> dict[str, Any]:
    """Resolve a simple opaque 'it' topic from ONE matching current USER topic.

    This is bounded anaphora over actual concern records, not evidence from the
    candidate. Multiple possible subjects, absent topics and different modal,
    predicate or deadline content remain unresolved.
    """
    target = candidate.get("state_target", ())
    if candidate["kind"] not in {"mental_state_presupposition", "mental_state"} \
            or not target or target[0] != "it":
        return dict(candidate)
    options = {item["state_target"] for item in detect_user_history(current_user, speaker="user")
               if item["kind"] == "mental_state" and item["mode"] in {"asserted", "presupposed"}
               and item.get("state_temporal") == "current" and item.get("target_modals") == candidate.get("target_modals")
               and len(item["state_target"]) == len(target) and item["state_target"][1:] == target[1:]
               and (candidate.get("target_question")
                    or item.get("target_polarity") == candidate.get("target_polarity"))}
    if len(options) != 1:
        return dict(candidate) | {"state_target": ("unresolved_topic",) + target,
                                  "content_tokens": ("concern", "unresolved_topic") + target}
    resolved = next(iter(options))
    return dict(candidate) | {"state_target": resolved, "content_tokens": ("concern",) + resolved}


def build_user_history_packet(draft: str, sources: Mapping[str, str]) -> dict[str, Any]:
    """Snapshot Core-assigned USER sources and obligations needing assessment.

    Trivial structural USER restatements are already witnessed by Core and do
    not add a semantic-output requirement.  Other candidates must be explicitly
    assessed in the existing verifier call; a global positive cannot erase them.
    """
    retained = {key: _text(value) for key, value in sources.items()
                if key == "current_user" or re.fullmatch(r"prior_user_\d+", str(key))}
    obligations, witnessed = [], []
    current_items = _owned_items(retained.get("current_user", ""), "user")
    for item in detect_user_history(draft):
        if item["mode"] in {"quoted", "questioned", "conditional", "future", "unasserted"}:
            continue
        item = _resolve_current_concern(item, retained.get("current_user", ""))
        if item["subject"] == "unresolved_item" and len(current_items) == 1:
            # The referent comes from an explicit single current USER-owned
            # object.  Prior assistant prose or an arbitrary matching habit
            # cannot supply it; ambiguous/absent current referents stay unknown.
            item = item | {"subject": current_items[0]}
        latest = _latest_typed_state(item, retained)
        if latest is not None:
            known = latest[0] if _compatible(item, latest[1]) else None
        else:
            known = None if _current_history_contradiction(item, retained.get("current_user", "")) else next(
                (key for key, value in retained.items() if user_history_witnessed(item, value, source_text=value)), None,
            )
        if known is not None:
            witnessed.append(item | {"source_id": known})
        else:
            obligations.append(item | {"index": len(obligations) + 1})
    return {"sources": retained, "obligations": tuple(obligations), "core_witnessed": tuple(witnessed)}


def validate_user_history_assessments(parsed: Mapping[str, Any], packet: Mapping[str, Any]) -> list[str]:
    required = packet["obligations"]
    if not required:
        return []
    checks = parsed.get("history_assessments")
    if not isinstance(checks, list) or len(checks) != len(required):
        return ["Core user-history assessment is missing or incomplete"]
    by_index = {}
    for check in checks:
        if (not isinstance(check, dict) or type(check.get("index")) is not int
                or check["index"] in by_index or type(check.get("supported")) is not bool):
            return ["Core user-history assessment is malformed"]
        by_index[check["index"]] = check
    if set(by_index) != {item["index"] for item in required}:
        return ["Core user-history assessment is missing or incomplete"]
    failures = []
    for item in required:
        check = by_index[item["index"]]
        label = "unsupported Core user-history " + item["kind"]
        latest = _latest_typed_state(item, packet["sources"])
        if latest is not None and not _compatible(item, latest[1]):
            failures.append(label + " conflicts with the latest matching USER state")
            continue
        if _current_history_contradiction(item, packet["sources"].get("current_user", "")):
            failures.append(label + " contradicts the current USER proposition")
            continue
        quote, source_id = check.get("source_quote"), check.get("source_id")
        source = packet["sources"].get(source_id) if isinstance(source_id, str) else None
        if check["supported"] is not True or not isinstance(quote, str) or not isinstance(source, str):
            failures.append(label)
        elif not user_history_witnessed(item, quote, source_text=source):
            failures.append(label + " lacks a matching literal USER witness")
    return failures
