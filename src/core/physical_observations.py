"""Bounded physical USER observations behind the existing grounding guard.

Core detects a small set of literal scene predicates and matches actual USER
witnesses. Topic/verb overlap, candidate prose and assistant history supply no
authority. This is not a general natural-language or visual scene parser.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping


_EXTRA_ACTIONS = {
    "pace": ("pace", "paces", "paced", "pacing"),
    "slump": ("slump", "slumps", "slumped", "slumping"),
    "wait": ("wait", "waits", "waited", "waiting"),
}
_BODY_STATES = {
    "shake": ("shake", "shakes", "shaking", "shook", "shaken"),
    "twitch": ("twitch", "twitches", "twitching", "twitched"),
    "water": ("water", "waters", "watering", "watered"),
    "tense": ("tense", "tensed", "tensing"),
    "tremble": ("tremble", "trembles", "trembling", "trembled"),
    "ache": ("ache", "aches", "aching", "ached"),
    "sore": ("sore",),
    "numb": ("numb",),
    "stiff": ("stiff",),
    "swell": ("swollen", "swelling", "swelled"),
    "sweat": ("sweat", "sweats", "sweating", "sweated"),
    "cross": ("crossed", "crossing"),
}
_PARTS = r"(?:hands?|fingers?|eyes?|shoulders?|arms?|legs?|neck|back|body|face|head|knees?|feet|foot|lips?|jaw|stomach|wrists?|toes?)"
_AUX = r"(?:am|are|is|was|were|have|had|has|haven't|hadn't|been|being|do|did|not|never|no\s+longer|don't|didn't|isn't|aren't|wasn't|weren't|still|already|just|even|finally|really|only|currently|will|would|could|might|may|can)"
_LINK = r"(?:and|but|while|when|before|after|because|since|so|then)"
_STOP_ARGUMENT = re.compile(r"[,;.!?]|\b(?:and|but|while|when|before|because|so|then|like|as\s+if)\b", re.I)
_RELATION = re.compile(r"\b(?P<link>from|after|since|because\s+of|due\s+to|for)\s+(?P<event>[^,;.!?]{1,100})", re.I)


def _text(value) -> str:
    value = re.sub(r"\s+", " ", str(value or "").replace("’", "'").replace("‘", "'")
                   .replace("“", '"').replace("”", '"')).strip()
    replacements = ((r"\bim\b|\bi'm\b", "I am"), (r"\bi've\b", "I have"),
                    (r"\bi'd\b", "I had"), (r"\bi'll\b", "I will"),
                    (r"\byou're\b", "you are"), (r"\byou've\b", "you have"),
                    (r"\byou'd\b", "you had"), (r"\byou'll\b", "you will"))
    for pattern, expanded in replacements:
        value = re.sub(pattern, expanded, value, flags=re.I)
    return value


def _tokens(value: str, speaker: str) -> tuple[str, ...]:
    words = []
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        if token in {"a", "an", "the", "this", "that"}:
            continue
        if token in {"my", "me", "i", "mine"}:
            token = "@" + speaker
        elif token in {"your", "you", "yours"}:
            token = "@" + ("assistant" if speaker == "user" else "user")
        words.append(token)
    return tuple(words)


@dataclass(frozen=True)
class PhysicalObservation:
    kind: str
    family: str
    body_part: str
    arguments: tuple[str, ...]
    polarity: str
    temporal: str
    mode: str
    continuing: bool
    prior_relation: tuple[str, tuple[str, ...]] | None
    span: str


def _quoted(value: str, start: int) -> bool:
    prefix = value[:start]
    if any(prefix.count(mark) % 2 for mark in ('"', '`')):
        return True
    return bool(re.search(r"(?:^|\s)'[^']*$", prefix))


def _mode(value: str, start: int, end: int, prefix: str, *, continuing=False,
          relation=None, fragment=False) -> str:
    """Scope this predicate rather than an unrelated outer future clause."""
    if _quoted(value, start):
        return "quoted"
    sentence_start = max(value.rfind(mark, 0, start) for mark in ".!?;") + 1
    sentence_end = min((position for mark in ".!?;" if (position := value.find(mark, end)) >= 0), default=len(value))
    before = value[sentence_start:start]
    sentence = value[sentence_start:sentence_end + 1]
    if re.search(r"\b(?:might|could|would|may|can)\b", prefix, re.I):
        return "conditional"
    # Explicit antecedents/imagination differ from 'we'll see if ... while
    # your hands are still ...': the latter contains an actual local premise.
    if re.search(r"(?:^|[,;])\s*(?:if|unless|suppose|supposing|imagine|hypothetically)\b", before, re.I):
        return "conditional"
    local = re.split(r"[,;]|\b(?:and|but|while|when)\b", before, flags=re.I)[-1]
    if re.search(r"\b(?:if|unless|imagine|suppose|hypothetically)\b", local, re.I):
        return "conditional"
    if re.search(r"\b(?:i|we)\s+(?:don't|do\s+not|cannot|can't)\s+"
                 r"(?:know|claim|assert|say|infer|assume|confirm|establish)\b[^.;!?]*$", before, re.I):
        return "unasserted"
    if re.search(r"\b(?:will|would)\b", prefix, re.I):
        return "future"
    wh_premise = bool(re.search(r"\b(?:why|when)\s+(?:are|is|was|were|have|has|had|aren't|isn't|weren't|wasn't)\s*$", before, re.I))
    if re.search(r"\b(?:when|once)\b", before, re.I) and not (continuing or relation or wh_premise) \
            and not re.search(r"\b(?:was|were|had)\b", prefix, re.I):
        return "conditional"
    if sentence.rstrip().endswith("?") and not fragment and not wh_premise \
            and not re.search(r",\s*(?:right|huh|then|eh)\?$", sentence, re.I):
        return "questioned"
    return "actual"


def _arguments(tail: str, family: str, speaker: str, *, body=False) -> tuple[str, ...]:
    tail = _RELATION.split(tail, maxsplit=1)[0]
    tail = _STOP_ARGUMENT.split(tail, maxsplit=1)[0].strip()
    tail = re.sub(r"(?:^|\s+)(?:right\s+now|now|currently|at\s+the\s+moment)$", "", tail, flags=re.I)
    tail = re.sub(r"^(?:here|there|down|up)\b\s*", "", tail, flags=re.I)
    if not body and family in {"sit", "stand", "slump"} and tail and not re.match(
            r"^(?:at|in|on|out|around|against|with|towards?|to|near|beside|by|behind|below|above|under|"
            r"over|inside|outside|indoors|outdoors|upstairs|downstairs|[a-z]+ly)\b", tail, re.I):
        # A posture does not absorb a following mood/reaction into its
        # physical argument. The existing semantic verifier still checks it.
        return ()
    # Bounded noun/preposition argument. A following participant/finite clause
    # or affective description is not folded into the scene identity.
    tail = re.split(r"\b(?:you|i|we|he|she|they|it)\s+(?:are|am|is|was|were|have|has|can|will)\b", tail,
                    maxsplit=1, flags=re.I)[0]
    # Keep a literal bounded complement rather than dropping an unfamiliar
    # preposition, location or intensity and thereby granting extra authority.
    return _tokens(tail, speaker)


def detect_user_physical_observations(text: str, *, speaker: str,
                                      action_families: Mapping[str, tuple]) -> tuple[PhysicalObservation, ...]:
    """One shared bounded detector for candidate predicates and USER witnesses."""
    if speaker not in {"user", "assistant"}:
        raise ValueError("invalid physical perspective")
    value = _text(text)
    person = "i" if speaker == "user" else "you"
    possessive = "my" if speaker == "user" else "your"
    families = dict(action_families) | _EXTRA_ACTIONS
    by_form = {form.lower(): family for family, forms in families.items() for form in forms}
    body_forms = {form.lower(): family for family, forms in _BODY_STATES.items() for form in forms}
    verbs = "|".join(re.escape(form) for form in sorted(by_form, key=len, reverse=True))
    body_verbs = "|".join(re.escape(form) for form in sorted(body_forms, key=len, reverse=True))
    direct = re.compile(r"\b" + person + r"\s+(?P<prefix>(?:" + _AUX + r"\s+)*)"
                        r"(?P<verb>" + verbs + r")\b", re.I)
    body_pattern = re.compile(r"\b" + possessive + r"\s+(?P<body>" + _PARTS + r")\s+"
                              r"(?P<prefix>(?:" + _AUX + r"\s+)*)"
                              r"(?P<verb>" + body_verbs + r")\b", re.I)
    records = []
    covered = []
    contexts = []

    def emit(match, *, body=False, fragment=False, inherited_prefix=""):
        verb = match.group("verb").lower()
        family = body_forms[verb] if body else by_form[verb]
        prefix = (match.groupdict().get("prefix") or inherited_prefix).lower()
        if body:
            wh = re.search(r"\b(?:why|when)\s+(?P<aux>are|is|was|were|have|has|had|aren't|isn't|weren't|wasn't)\s*$",
                           value[:match.start()], re.I)
            if wh:
                prefix = wh.group("aux").lower() + " " + prefix
        if fragment and not inherited_prefix:
            sentence_start = max(value.rfind(mark, 0, match.start()) for mark in ".!?;") + 1
            previous = [item for item in contexts if item[0] >= sentence_start and item[1] <= match.start()]
            if previous:
                prefix = previous[-1][2]
        tail_end = min((position for mark in ".!?;" if (position := value.find(mark, match.end())) >= 0), default=len(value))
        tail = value[match.end():tail_end]
        # Abstract 'looking at it differently/another way' is not a visual
        # observation. Imperatives never match this subject/scene grammar.
        if family == "look" and re.match(r"\s+(?:at\s+(?:it|this|that)\s+(?:another|a\s+different)\s+way|"
                                         r"for\s+(?:an?\s+)?(?:answer|solution|reason|way))\b", tail, re.I):
            return
        relation_match = _RELATION.search(tail.split(",", 1)[0])
        relation = None
        if relation_match:
            event = _STOP_ARGUMENT.split(relation_match.group("event"), maxsplit=1)[0]
            event_tokens = _tokens(event, speaker)
            if event_tokens:
                relation = (re.sub(r"\s+", " ", relation_match.group("link").lower()), event_tokens)
        continuing = bool(re.search(r"\bstill\b", prefix, re.I))
        mode = _mode(value, match.start(), match.end(), prefix,
                     continuing=continuing, relation=relation, fragment=fragment)
        negative = bool(re.search(r"\b(?:not|never|no\s+longer|don't|didn't|haven't|hadn't|isn't|aren't|wasn't|weren't)\b", prefix, re.I))
        temporal = "past" if re.search(r"\b(?:was|were|had|did|didn't|wasn't|weren't)\b", prefix) else "current"
        if not re.search(r"\b(?:am|are|is|been|being)\b", prefix) and verb in {
                form for forms in (families | _BODY_STATES).values() for form in forms
                if form.endswith("ed") or form in {"sat", "stood", "ran", "lay", "slept", "woke", "ate", "drank", "held", "wore", "drove", "left", "shook", "shaken"}}:
            temporal = "past"
        if mode == "future":
            temporal = "future"
        if body and not re.search(r"\b(?:am|are|is|been|being)\b", prefix) and re.search(
                r"\bi\s+(?:saw|watched|noticed|remember(?:ed)?|recall(?:ed)?)\b[^.;!?]*$",
                value[max(value.rfind(mark, 0, match.start()) for mark in ".!?;") + 1:match.start()], re.I):
            temporal = "past"
        args = _arguments(tail, family, speaker, body=body)
        # No observation is acquired from a gerund used as a topic/title.
        if fragment and re.search(r"\b(?:is|are|was|were|can|might|would|will)\b", tail.split(",", 1)[0], re.I):
            return
        record = PhysicalObservation("body_state" if body else "action", family,
                                     match.group("body").lower() if body else "", args,
                                     "negative" if negative else "positive", temporal, mode,
                                     continuing, relation, value[match.start():match.end()] + tail.split(",", 1)[0])
        if record not in records:
            records.append(record)
        covered.append((match.start(), match.end()))
        contexts.append((match.start(), match.end(), prefix))

    for match in direct.finditer(value):
        emit(match)
    for match in body_pattern.finditer(value):
        emit(match, body=True)

    # Linked participial descriptions inherit the USER scene subject, not the
    # authority of the first action. Each physical predicate is matched alone.
    ing_forms = [form for form in by_form if form.endswith("ing")]
    fragments = re.compile(r"(?:^|[.!?]\s*|,\s*)(?P<verb>" + "|".join(re.escape(form) for form in ing_forms)
                           + r")\b", re.I)
    for match in fragments.finditer(value):
        if any(start <= match.start("verb") < end for start, end in covered):
            continue
        before = value[:match.start("verb")]
        sentence_start = max(before.rfind(mark) for mark in ".!?;" ) + 1
        lead = value[sentence_start:match.start("verb")]
        # A comma fragment is physical only when this sentence already has a
        # USER scene/action anchor. A third party or object is not the USER.
        if lead.strip() and not any(start >= sentence_start for start, _ in covered):
            preceding = re.match(r"(?:sitting|standing|lying|pacing|walking|slumping)\b", lead.strip(), re.I)
            if not preceding:
                continue
        emit(match, fragment=True)

    # Preserve old bounded participial shapes without a comma: 'Sitting there
    # staring at nothing, you're ...' and 'stop staring ...' about the USER.
    secondary = re.compile(r"\b(?P<verb>" + "|".join(re.escape(form) for form in ing_forms) + r")\b", re.I)
    for match in secondary.finditer(value):
        if any(start <= match.start() < end for start, end in covered):
            continue
        before = value[max(value.rfind(mark, 0, match.start()) for mark in ".!?;" ) + 1:match.start()]
        linked_scene = any(end <= match.start() and match.start() - end <= 55
                           and re.fullmatch(r"(?:(?:here|there|still|just|down|up|and|while)\s*)*",
                                            value[end:match.start()].strip(), re.I)
                           for start, end in covered)
        user_transition = re.search(r"\b" + person + r"\s+(?:" + _AUX + r"\s+)*"
                                     r"(?:to\s+)?(?:stop|stopped|keep|kept|start|started|continue|continued)\s*$",
                                     before, re.I)
        if linked_scene or user_transition:
            emit(match, fragment=True)
    return tuple(records)


def _same_state(candidate: PhysicalObservation, witness: PhysicalObservation) -> bool:
    return (candidate.kind == witness.kind and candidate.family == witness.family
            and candidate.body_part == witness.body_part
            and candidate.arguments == witness.arguments and candidate.temporal == witness.temporal)


def _supported(candidate: PhysicalObservation, witness: PhysicalObservation) -> bool:
    identity = (candidate.kind == witness.kind and candidate.family == witness.family
                and candidate.body_part == witness.body_part and candidate.temporal == witness.temporal)
    return (witness.mode == "actual" and identity
            and (not candidate.arguments or candidate.arguments == witness.arguments)
            and candidate.polarity == witness.polarity
            and (not candidate.continuing or witness.continuing)
            and (candidate.prior_relation is None or candidate.prior_relation == witness.prior_relation))


def _correction_matches(candidate: PhysicalObservation, witness: PhysicalObservation) -> bool:
    same_predicate = (candidate.kind == witness.kind and candidate.family == witness.family
                      and candidate.body_part == witness.body_part and candidate.temporal == witness.temporal)
    return (same_predicate and (candidate.arguments == witness.arguments
                               or not candidate.arguments
                               or witness.polarity == "negative" and witness.arguments in {(), ("anything",), ("anywhere",)}))


def find_user_physical_state_violations(draft: str, sources: Mapping[str, str],
                                        action_families: Mapping[str, tuple]) -> list[str]:
    """Fail closed on unmatched literal physical predicates using USER only."""
    retained = {key: _text(value) for key, value in sources.items()
                if key == "current_user" or re.fullmatch(r"prior_user_\d+", str(key))}
    ordered = sorted((key for key in retained if key != "current_user"),
                     key=lambda key: int(key.rsplit("_", 1)[1]))
    if "current_user" in retained:
        ordered.append("current_user")
    witnesses = [item for key in ordered for item in detect_user_physical_observations(
        retained[key], speaker="user", action_families=action_families) if item.mode == "actual"]
    failures = []
    for candidate in detect_user_physical_observations(draft, speaker="assistant", action_families=action_families):
        if candidate.mode != "actual":
            continue
        matching = [item for item in witnesses if _correction_matches(candidate, item)]
        if matching and _supported(candidate, matching[-1]):
            continue
        label = "unsupported Oliver physical-action/state claim involving " + candidate.family
        if label not in failures:
            failures.append(label)
    return failures
