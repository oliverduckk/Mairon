"""Bounded, deterministic claim interpretation for Core acceptance.

This module recognizes a small grammar; it never establishes truth or source
authority. Unresolved clauses remain incomplete instead of disappearing. Exact
literal statements remain available to the evaluator, which must still check
their typed evidence and scope. It deliberately imports no generation guards.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import re
from typing import Tuple


class UnitKind(str, Enum):
    ASSERTION = "assertion"
    REACTION = "reaction"
    QUESTION = "question"
    LIMITATION = "limitation"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Proposition:
    subject: str
    relation: str
    value: str
    polarity: bool = True
    conditional: bool = False
    condition: str = ""
    personal: bool = False
    observation: bool = False
    reported: bool = False
    canonical: str = ""
    reporter: str = ""

    def __post_init__(self):
        for name in ("subject", "relation", "value", "condition", "canonical", "reporter"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")
        for name in ("polarity", "conditional", "personal", "observation", "reported"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool")


@dataclass(frozen=True)
class ClaimUnit:
    index: int
    text: str
    propositions: Tuple[Proposition, ...] = field(default_factory=tuple)
    kind: UnitKind = UnitKind.UNKNOWN
    behaviors: Tuple[str, ...] = field(default_factory=tuple)
    complete: bool = True
    limitation_target: str = ""

    def __post_init__(self):
        if type(self.index) is not int or self.index < 1:
            raise ValueError("Unit index must be a positive integer")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Unit text must be nonempty")
        if not isinstance(self.kind, UnitKind):
            raise TypeError("Unit kind must be typed")
        if not isinstance(self.propositions, (tuple, list)) or any(
            not isinstance(item, Proposition) for item in self.propositions
        ):
            raise TypeError("Propositions must contain Proposition values")
        if not isinstance(self.behaviors, (tuple, list)) or any(
            not isinstance(item, str) for item in self.behaviors
        ):
            raise TypeError("Behaviors must contain strings")
        if type(self.complete) is not bool:
            raise TypeError("complete must be a bool")
        if not isinstance(self.limitation_target, str):
            raise TypeError("limitation_target must be a string")
        object.__setattr__(self, "propositions", tuple(self.propositions))
        object.__setattr__(self, "behaviors", tuple(self.behaviors))


_SPEAKERS = {"user", "assistant", "source", "core"}
_CONTRACTIONS = {
    "i'm": "i am", "you're": "you are", "we're": "we are",
    "they're": "they are", "he's": "he is", "she's": "she is",
    "it's": "it is", "i've": "i have", "you've": "you have",
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "haven't": "have not", "hasn't": "has not",
    "hadn't": "had not", "can't": "cannot", "couldn't": "could not",
    "won't": "will not", "wouldn't": "would not", "shouldn't": "should not",
}
_REACTIONS = re.compile(
    r"(?:thanks(?: very much| a lot)?|thank you(?: very much)?|"
    r"okay|ok|yes|no|understood|got it|acknowledged|"
    r"that sounds (?:difficult|hard|frustrating|exciting|good|nice|unpleasant)|"
    r"that is (?:understandable|difficult)|sorry to hear that|"
    r"i understand|that makes sense)", re.I,
)
_RELATIONS = {
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be",
    "have": "have", "has": "have", "had": "have",
    "prefer": "prefer", "prefers": "prefer", "preferred": "prefer",
    "like": "like", "likes": "like", "liked": "like",
    "love": "like", "loves": "like", "loved": "like",
    "dislike": "like", "dislikes": "like", "disliked": "like",
    "hate": "like", "hates": "like", "hated": "like",
    "want": "want", "wants": "want", "wanted": "want",
    "need": "need", "needs": "need", "needed": "need",
    "contain": "contain", "contains": "contain", "contained": "contain",
    "own": "own", "owns": "own", "owned": "own",
    "use": "use", "uses": "use", "used": "use",
    "sit": "sit", "sits": "sit", "sat": "sit",
    "stand": "stand", "stands": "stand", "stood": "stand",
    "walk": "walk", "walks": "walk", "walked": "walk",
    "run": "run", "runs": "run", "ran": "run",
    "stretch": "stretch", "stretches": "stretch", "stretched": "stretch",
    "pace": "pace", "paces": "pace", "paced": "pace",
    "hold": "hold", "holds": "hold", "held": "hold",
    "wear": "wear", "wears": "wear", "wore": "wear",
    "sleep": "sleep", "sleeps": "sleep", "slept": "sleep",
    "eat": "eat", "eats": "eat", "ate": "eat",
    "drink": "drink", "drinks": "drink", "drank": "drink",
    "read": "read", "reads": "read",
    "watch": "watch", "watches": "watch", "watched": "watch",
    "visit": "visit", "visits": "visit", "visited": "visit",
    "work": "work", "works": "work", "worked": "work",
    "live": "live", "lives": "live", "lived": "live",
    "feel": "feel", "feels": "feel", "felt": "feel",
    "say": "say", "says": "say", "said": "say",
}
_OBSERVABLE = {
    "sit", "stand", "walk", "run", "stretch", "pace", "hold", "wear",
    "sleep", "eat", "drink", "read", "watch", "visit", "work", "live",
}
_PROGRESSIVES = {
    "sitting": "sit", "standing": "stand", "walking": "walk", "running": "run",
    "stretching": "stretch", "pacing": "pace", "holding": "hold",
    "wearing": "wear", "sleeping": "sleep", "eating": "eat",
    "drinking": "drink", "reading": "read", "watching": "watch",
    "visiting": "visit", "working": "work", "living": "live",
}
_VERB_PATTERN = "|".join(sorted(_RELATIONS, key=len, reverse=True))
_CLAUSE_START = re.compile(
    r"(?:\b(?:i|you|we|they|he|she|it|the|a|an|my|your|our|their)\b.+?\b"
    r"(?:" + _VERB_PATTERN + r"|do|does|did|can|will)\b)", re.I,
)
_UNRESOLVED_SUBORDINATE = re.compile(
    r"\b(?:because|although|while|whereas|unless|until|before|after|"
    r"whenever|since|despite|which|who|whose|that)\b", re.I,
)
_COLORS = frozenset({
    "black", "white", "gray", "grey", "red", "orange", "yellow", "green",
    "blue", "purple", "violet", "pink", "brown", "amber", "cyan", "magenta",
    "teal", "indigo", "maroon", "beige", "gold", "silver",
})
_QUANTITIES = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
}


def _normal_text(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"\s+", " ", text.strip()).casefold()
    for key, value in _CONTRACTIONS.items():
        text = re.sub(r"(?<!\w)" + re.escape(key) + r"(?!\w)", value, text)
    return text


def _trim_terminal(text: str) -> str:
    return text.strip().rstrip(".!?").strip()


def _validate_context(speaker: str, user_name):
    if speaker not in _SPEAKERS:
        raise ValueError("speaker must be user, assistant, source, or core")
    if user_name is not None and (not isinstance(user_name, str) or not user_name.strip()):
        raise TypeError("user_name must be nonempty trusted text or None")


def _map_person(text: str, speaker: str, user_name=None) -> str:
    value = _normal_text(text)
    first_person = "$user" if speaker == "user" else "$source" if speaker == "source" else "$assistant"
    second_person = "$reader" if speaker == "source" else "$assistant" if speaker == "user" else "$user"
    value = re.sub(r"\bmy\b", first_person + "'s", value)
    value = re.sub(r"\byour\b", second_person + "'s", value)
    value = re.sub(r"\b(?:i|me)\b", first_person, value)
    value = re.sub(r"\byou\b", second_person, value)
    alias = "$reader" if speaker == "source" else "$user"
    value = re.sub(r"\b(?:the (?:current )?user|current user)'s\b", alias + "'s", value)
    value = re.sub(r"\b(?:the (?:current )?user|current user)\b", alias, value)
    if user_name and speaker != "source":
        name = re.escape(_normal_text(user_name))
        value = re.sub(r"(?<!\w)" + name + r"'s(?!\w)", "$user's", value)
        value = re.sub(r"(?<!\w)" + name + r"(?!\w)", "$user", value)
    return value


def canonical_statement(text: str, *, speaker="assistant", user_name=None) -> str:
    """Canonical wording only; equality does not establish evidence authority."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    _validate_context(speaker, user_name)
    value = _map_person(_trim_terminal(text), speaker, user_name)
    value = re.sub(r"\b(?:am|is|are)\b", "be", value)
    value = re.sub(r"\bhas\b", "have", value)
    return value


def _sentences(text: str):
    # Punctuation is a boundary only before whitespace/end, preserving decimals.
    # Newlines independently delimit units; semicolons delimit independent units.
    parts = re.split(r"(?<=[.!?])\s+|(?<=[.!?])(?=[A-Za-z])|[\r\n]+|;\s*", text.strip())
    return tuple(part.strip() for part in parts if part.strip())


def _behaviors(text: str) -> Tuple[str, ...]:
    value = _normal_text(text)
    result = []
    # These identify broad behavioural classes, not incident-specific wording.
    blame_text = re.sub(r"\bnot\s+(?:your fault|to blame)\b", "", value)
    if re.search(r"\b(?:your fault|you (?:are|were) (?:the one )?to blame)\b", blame_text):
        result.append("blame")
    ridicule_text = re.sub(
        r"\b(?:not|never)\s+(?:a |an )?(?:idiot|moron|imbecile|stupid|pathetic|laughable|ridiculous)\b",
        "", value,
    )
    if re.search(r"\b(?:idiot|moron|imbecile|stupid|pathetic|laughable|ridiculous)\b", ridicule_text):
        result.append("ridicule")
    if re.search(r"\b(?:lol|lmao|roast|roasting)\b|[\U0001f602\U0001f923]", value):
        result.append("casual_roast")
    return tuple(result)


def _quantity(value: str):
    match = re.fullmatch(r"(?P<number>-?\d+(?:\.\d+)?|" + "|".join(_QUANTITIES) + r")(?P<unit>\s+.+)?", value)
    if not match:
        return None
    number = match.group("number")
    unit = (match.group("unit") or "").strip()
    # Only regular count morphology; unrecognized units retain literal identity.
    unit = re.sub(r"\b([a-z]+)ies\b", r"\1y", unit)
    unit = re.sub(r"\b([a-z]+)(?<!s)s\b", r"\1", unit)
    return Decimal(_QUANTITIES.get(number, number)), unit


def conflicting_propositions(left: Proposition, right: Proposition) -> bool:
    """Recognize bounded incompatible slots, never arbitrary adjective antonyms.

    Wording support still requires the evaluator's scoped evidence checks. This
    helper only establishes obvious same-subject opposition or a bounded scalar
    conflict; unrelated properties such as weight and color can coexist.
    """
    if left.subject != right.subject or left.relation != right.relation:
        return False
    if left.conditional != right.conditional or left.condition != right.condition:
        return False
    if left.value == right.value:
        return left.polarity != right.polarity
    if not left.polarity or not right.polarity:
        return False
    if left.relation == "be" and left.value in _COLORS and right.value in _COLORS:
        equivalent = {"gray", "grey"}
        return not {left.value, right.value} <= equivalent
    if left.relation in {"be", "have", "contain"}:
        left_quantity, right_quantity = _quantity(left.value), _quantity(right.value)
        if left_quantity and right_quantity:
            return left_quantity[1] == right_quantity[1] and left_quantity[0] != right_quantity[0]
    if left.relation == "prefer":
        left_pair = re.fullmatch(r"(.+?)\s+over\s+(.+)", left.value)
        right_pair = re.fullmatch(r"(.+?)\s+over\s+(.+)", right.value)
        return bool(left_pair and right_pair and left_pair.group(1) == right_pair.group(2)
                    and left_pair.group(2) == right_pair.group(1))
    return False


def _literal(text: str, *, speaker, user_name, conditional=False, condition="", reported=False, reporter=""):
    canonical = canonical_statement(text, speaker=speaker, user_name=user_name)
    return Proposition(
        subject="", relation="statement", value=canonical,
        conditional=conditional, condition=condition,
        personal="$user" in canonical, observation=False,
        reported=reported, canonical=canonical, reporter=reporter,
    )


def _proposition(text: str, *, speaker, user_name, conditional=False, condition="", reported=False, reporter=""):
    mapped = _map_person(_trim_terminal(text), speaker, user_name)
    match = re.fullmatch(
        r"(?P<subject>.+?)\s+(?:(?P<aux>do|does|did)\s+)?(?P<neg>not\s+)?"
        r"(?P<verb>" + _VERB_PATTERN + r")\b(?P<rest>.*)", mapped,
    )
    if not match:
        return _literal(text, speaker=speaker, user_name=user_name,
                        conditional=conditional, condition=condition, reported=reported, reporter=reporter)
    subject = match.group("subject").strip()
    # Clause-boundary punctuation and verbs inside a subject are unresolved.
    if not subject or any(character in subject for character in ",:?!") or re.search(
        r"\b(?:do|does|did|will|would|can|cannot|could|not)\b", subject
    ):
        return None
    verb = match.group("verb")
    relation = _RELATIONS[verb]
    rest = match.group("rest").strip()
    polarity = not bool(match.group("neg"))
    if verb in {"dislike", "dislikes", "disliked", "hate", "hates", "hated"}:
        polarity = not polarity
    if relation == "be" and rest.startswith("not "):
        polarity, rest = not polarity, rest[4:].strip()
    if relation == "have" and rest.startswith("not "):
        polarity, rest = not polarity, rest[4:].strip()
    if relation == "be":
        progressive = re.match(r"^(\w+)(?:\s+(.*))?$", rest)
        if progressive and progressive.group(1) in _PROGRESSIVES:
            relation = _PROGRESSIVES[progressive.group(1)]
            rest = progressive.group(2) or ""
    if not rest and relation not in _OBSERVABLE:
        return None
    personal = "$user" in subject
    # Predicate grouping supports contradiction comparison only. Wording
    # identity preserves strength and tense, so "like" cannot support "love".
    canonical = canonical_statement(text, speaker=speaker, user_name=user_name)
    return Proposition(subject=subject, relation=relation, value=rest,
                       polarity=polarity, conditional=conditional, condition=condition,
                       personal=personal, observation=personal and (relation in _OBSERVABLE or relation == "be"),
                       reported=reported, canonical=canonical, reporter=reporter)


def _limitation(text: str, *, speaker, user_name):
    value = _normal_text(_trim_terminal(text))
    match = re.fullmatch(
        r"i (?:cannot|can not|do not|am unable to) "
        r"(?:know|determine|establish|verify|confirm|inspect|observe|tell|assess|read|access)"
        r"(?:\s+(?P<target>.+))?", value,
    )
    if match:
        target = match.group("target") or ""
        if re.search(r"\b(?:but|and|because|while|although|so|therefore)\b|[,;:]", target):
            return None
        return canonical_statement(target, speaker=speaker, user_name=user_name)
    match = re.fullmatch(
        r"(?P<target>(?:the |this |that |your |my )?[^,;:]+?) "
        r"(?:is|are|was|were) (?:unavailable|missing|unknown|unverified|not supplied|not attached|not provided)",
        value,
    )
    if match and not re.search(r"\b(?:and|but|because|while|although)\b", match.group("target")):
        return canonical_statement(match.group("target"), speaker=speaker, user_name=user_name)
    return None


def _interpret_unit(index, text, *, speaker, user_name):
    raw = _trim_terminal(text)
    normalized = _normal_text(raw)
    behaviors = _behaviors(text)
    if raw.startswith(('"', "'", "`", "{", "[")):
        return ClaimUnit(index, text, kind=UnitKind.UNKNOWN, behaviors=behaviors, complete=False)
    # A reaction is safe only if it occupies the entire unit.
    if _REACTIONS.fullmatch(normalized):
        return ClaimUnit(index, text, kind=UnitKind.REACTION, behaviors=behaviors)
    # Questions with presupposed subordinate facts are unresolved, not harmless.
    if text.rstrip().endswith("?"):
        person_bound_question = _map_person(normalized, speaker, user_name)
        if re.fullmatch(r"(?:what|which|where|when|how)\b[^,;:]+", normalized) and not re.search(
            r"\b(?:since|because|while|given|now that|you|your)\b", normalized
        ) and not re.search(r"\$(?:user|assistant|reader|source)\b", person_bound_question):
            return ClaimUnit(index, text, kind=UnitKind.QUESTION, behaviors=behaviors)
        return ClaimUnit(index, text, kind=UnitKind.UNKNOWN, behaviors=behaviors, complete=False)
    target = _limitation(text, speaker=speaker, user_name=user_name)
    if target is not None:
        return ClaimUnit(index, text, kind=UnitKind.LIMITATION,
                         behaviors=behaviors, limitation_target=target)
    conditional, condition = False, ""
    match = re.fullmatch(r"(?:if|assuming|supposing|suppose)\s+(.+?),\s*(.+)", raw, re.I)
    if match:
        condition = canonical_statement(match.group(1), speaker=speaker, user_name=user_name)
        raw, conditional = match.group(2), True
    else:
        match = re.fullmatch(r"(?:assume|suppose|assuming)\s+(.+)", raw, re.I)
        if match:
            raw, conditional = match.group(1), True
            condition = canonical_statement(raw, speaker=speaker, user_name=user_name)
    reported, reporter = False, ""
    match = re.fullmatch(
        r"(?P<actor>you|i) (?:said|stated|reported)\s+(?:that\s+)?(?P<body>.+)", raw, re.I,
    )
    inner_speaker = speaker
    if match:
        raw, reported = match.group("body"), True
        reporter = _map_person(match.group("actor"), speaker, user_name)
        # Quotations change pronoun perspective to the reported speaker. An
        # assistant quotation supplied by a user must not become a user fact.
        if raw.startswith(('"', "'")) and raw.endswith(raw[0]) and len(raw) > 1:
            actor = reporter
            inner_speaker = "user" if actor == "$user" else "assistant" if actor == "$assistant" else "source"
            raw = raw[1:-1]
    match = re.fullmatch(r"according to (.+?),\s*(.+)", raw, re.I)
    if match:
        reporter = canonical_statement(match.group(1), speaker=speaker, user_name=user_name)
        raw, reported = match.group(2), True
    elif not reported:
        match = re.fullmatch(
            r"(?P<actor>.+?)\s+(?:says|said|states|stated|reports|reported|claims|claimed)\s+"
            r"(?:that\s+)?(?P<body>.+)", raw, re.I,
        )
        if match:
            actor = match.group("actor")
            if re.search(r"[,;:]|\b(?:because|while|and|but)\b", actor, re.I):
                return ClaimUnit(index, text, kind=UnitKind.UNKNOWN, behaviors=behaviors, complete=False)
            reporter = canonical_statement(actor, speaker=speaker, user_name=user_name)
            raw, reported = match.group("body"), True
            if raw.startswith(('"', "'")) and raw.endswith(raw[0]) and len(raw) > 1:
                inner_speaker = "user" if reporter == "$user" else "assistant" if reporter == "$assistant" else "source"
                raw = raw[1:-1]
    # Coordinated/subordinate clauses cannot be folded into one opaque value.
    # Split only an explicit independently authored subject clause. Otherwise
    # leave an incomplete unit so no assertion can escape the evaluator.
    conjunction = re.split(r"\s+(?:and|but|yet|or)\s+", raw, flags=re.I)
    if len(conjunction) > 1:
        propositions = []
        for clause in conjunction:
            if not _CLAUSE_START.search(clause):
                return ClaimUnit(index, text, kind=UnitKind.UNKNOWN,
                                 behaviors=behaviors, complete=False)
            proposition = _proposition(clause, speaker=inner_speaker, user_name=user_name,
                                       conditional=conditional, condition=condition, reported=reported, reporter=reporter)
            if proposition is None or _UNRESOLVED_SUBORDINATE.search(clause):
                return ClaimUnit(index, text, kind=UnitKind.UNKNOWN,
                                 behaviors=behaviors, complete=False)
            propositions.append(proposition)
        return ClaimUnit(index, text, tuple(propositions), UnitKind.ASSERTION, behaviors)
    # Conservative coverage prevents a safe prefix hiding an unparsed claim.
    if _UNRESOLVED_SUBORDINATE.search(raw) or re.search(r"[,;:]|[\r\n]", raw):
        return ClaimUnit(index, text, kind=UnitKind.UNKNOWN, behaviors=behaviors, complete=False)
    proposition = _proposition(raw, speaker=inner_speaker, user_name=user_name,
                               conditional=conditional, condition=condition, reported=reported, reporter=reporter)
    if proposition is None:
        return ClaimUnit(index, text, kind=UnitKind.UNKNOWN, behaviors=behaviors, complete=False)
    # A literal needs a declarative grammatical shape, rather than arbitrary
    # imperative, quote, code, or acknowledgement fragments.
    if proposition.relation == "statement" and not (
        re.fullmatch(r"(?:(?:the |a |an |this |that |i |you |my |your )[^!?]+|"
                     r"[A-Z][\w'-]*\s+[a-z]+(?:s|ed|ing)\b[^!?]*)", raw, re.I)
        or re.fullmatch(r"[0-9][0-9.+*/()= <>=!-]*[=<>][0-9.+*/()= <>=!-]+", raw)
    ):
        return ClaimUnit(index, text, kind=UnitKind.UNKNOWN, behaviors=behaviors, complete=False)
    return ClaimUnit(index, text, (proposition,), UnitKind.ASSERTION, behaviors)


def interpret_text(text: str, *, speaker="assistant", user_name=None) -> Tuple[ClaimUnit, ...]:
    """Interpret every sentence without deciding truth, authority, or publication."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    _validate_context(speaker, user_name)
    return tuple(_interpret_unit(index, sentence, speaker=speaker, user_name=user_name)
                 for index, sentence in enumerate(_sentences(text), 1))
