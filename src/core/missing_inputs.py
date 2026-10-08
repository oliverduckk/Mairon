"""Conservative Core descriptions of explicitly omitted user input.

The extractor reads a direct user omission statement and retains noun labels,
not facts about the missing material. The separate list parser consumes its
whole input: candidate prose cannot use extraction cleanup to discard a claim.
Both are deliberately bounded; ambiguous language keeps the generic limitation.
"""
from dataclasses import dataclass
import re
import unicodedata
from typing import Optional, Tuple


_MAX_DESCRIPTION = 180
_MAX_ITEMS = 16
_HAVE = r"(?:have\s+not|haven['’]?t)"
_DID = r"(?:did\s+not|didn['’]?t)"
_OMISSION = re.compile(
    r"\bi\s+(?:"
    + _HAVE + r"\s+(?P<past>attached|uploaded|provided|supplied|sent|given|told)"
    + r"|" + _DID + r"\s+(?P<base>attach|upload|provide|supply|send|give|tell))\b",
    re.IGNORECASE,
)
_AUXILIARY = re.compile(
    r"\b(?:am|is|are|was|were|be|being|been|has|have|had|do|does|did|"
    r"can|could|will|would|must|should|might|may)\b", re.IGNORECASE,
)
_CLAUSE = re.compile(
    r"\b(?:i|you|we|they|he|she|it)\b|"
    r"\b(?:equals|contains|weighs|costs|shows|says|proves|indicates)\s+\S|"
    r"\b(?:because|although|whereas|unless|until|however|therefore)\b",
    re.IGNORECASE,
)
_TERMINAL_ADJUNCT = re.compile(
    r"\s+(?:as\s+yet|yet|so\s+far|at\s+present|for\s+now|currently)"
    r"(?=\s|[,;]|$)", re.IGNORECASE,
)
_DISCOURSE_BOUNDARY = re.compile(
    r"\s*[,;]\s*(?:but|so|however|therefore|anyway|please|thanks)\b|"
    r"\s+(?:but|because|although|though|however|therefore)\s+|"
    r"\s*[,;]\s*(?:can|could|would|will)\s+you\b|"
    r"\s+and\s+(?:i|you|we|they|he|she|it)\b",
    re.IGNORECASE,
)
_CONDITIONAL = re.compile(r"\b(?:if|unless|assuming|suppose|supposing|hypothetically)\b", re.IGNORECASE)
_REPORTING = re.compile(r"\b(?:said|says|told|quoted|wrote|writes|reported|according)\b", re.IGNORECASE)
_SUPPLY_ADVERBS = r"(?:(?:just|already|now|actually)\s+){0,3}"
_SUPPLY_PAST = r"attached|uploaded|provided|supplied|sent|given|told"
_SUPPLY_BASE = r"attach|upload|provide|supply|send|give|tell"
_ACTIVE_SUPPLY = re.compile(
    r"\b(?:(?:i|we)(?:['’]ve|\s+(?:have|had))\s+" + _SUPPLY_ADVERBS
    + r"(?P<perfect>" + _SUPPLY_PAST + r")|(?:i|we)\s+(?:did\s+" + _SUPPLY_ADVERBS
    + r"(?P<base>" + _SUPPLY_BASE + r")|" + _SUPPLY_ADVERBS
    + r"(?P<past>" + _SUPPLY_PAST + r")))\b", re.IGNORECASE,
)
_PASSIVE_SUPPLY = re.compile(
    r"\b(?:(?:is|are|was|were)\s+" + _SUPPLY_ADVERBS
    + r"|(?:has|have)\s+" + _SUPPLY_ADVERBS + r"been\s+" + _SUPPLY_ADVERBS
    + r")(?P<verb>attached|uploaded|provided|supplied|sent|given)\b",
    re.IGNORECASE,
)
_SUPPLY_ADJUNCT = re.compile(
    r"\s+(?:as\s+yet|yet|so\s+far|at\s+present|for\s+now|currently|now|already)"
    r"(?=\s|[,;]|$)", re.IGNORECASE,
)


@dataclass(frozen=True)
class MissingInputs:
    items: Tuple[str, ...]
    description: str

    def __post_init__(self):
        if (not isinstance(self.items, tuple) or not self.items
                or len(self.items) > _MAX_ITEMS
                or any(not isinstance(item, str) or not item.strip() for item in self.items)):
            raise ValueError("Missing inputs require bounded, non-empty item labels")
        if (not isinstance(self.description, str) or not self.description.strip()
                or len(self.description) > _MAX_DESCRIPTION):
            raise ValueError("Missing inputs require a bounded description")


def _space(value):
    return " ".join(unicodedata.normalize("NFC", value).split())


def _semantic_text(value):
    # File/decimal identifiers are opaque names, not auxiliary verbs embedded
    # in an assertion. Dotted names still require exact typed-label matching.
    return re.sub(r"(?<![\w.])(?:[\w-]+\.)+[\w-]+(?![\w.])",
                  lambda match: "x" * len(match.group()), value)


def _nominal(value):
    semantic = _semantic_text(value)
    if not value or _AUXILIARY.search(semantic) or _CLAUSE.search(semantic):
        return False
    # Finite assertions, code, or punctuation introducing another sentence do
    # not become names merely by occurring after an omission/list delimiter.
    if any(character in ";:!?`{}[]\n\r" for character in value):
        return False
    if not any(character.isalpha() for character in value):
        return False
    if any(unicodedata.category(character) in {"So", "Sk", "Cf", "Cc"} for character in value):
        return False
    if re.search(r"\.(?=\s|$)", value):
        return False
    words = re.findall(r"[\w'-]+", semantic, flags=re.UNICODE)
    if not words or words[0].casefold() in {"and", "or", "but", "please"}:
        return False
    # These qualifiers change the scope of a negated conjunction. Refusing to
    # split them is preferable to declaring each component independently absent.
    if any(word.casefold() in {"both", "either", "except", "only"} for word in words):
        return False
    return True


def parse_missing_item_list(text: str) -> Optional[MissingInputs]:
    """Recognize a whole nominal list, without discarding candidate assertions.

    Numeric identifiers and filenames are opaque labels. Matching those labels
    to authoritative Core absence state is the caller's responsibility.
    """
    if not isinstance(text, str):
        return None
    value = _space(text).strip()
    if not value or len(value) > _MAX_DESCRIPTION:
        return None
    # A final sentence stop carries no information; internal stops remain and
    # are checked below. Extension/decimal dots inside a label are preserved.
    if value.endswith("."):
        value = value[:-1].rstrip()
    semantic = _semantic_text(value)
    if not value or _AUXILIARY.search(semantic) or _CLAUSE.search(semantic):
        return None
    separators = list(re.finditer(r",\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+", value, re.IGNORECASE))
    items, position = [], 0
    for separator in separators:
        item = value[position:separator.start()].strip()
        if not _nominal(item):
            return None
        items.append(item)
        position = separator.end()
    last = value[position:].strip()
    if not _nominal(last):
        return None
    items.append(last)
    if len(items) > _MAX_ITEMS:
        return None
    unique = tuple(dict.fromkeys(items))
    # The structured items establish list identity; rendering preserves the
    # cleaned user's punctuation/connectors instead of introducing a new style.
    return MissingInputs(unique, value)


def _inside_quote(text):
    quote = None
    for index, character in enumerate(text):
        previous = text[index - 1] if index else ""
        following = text[index + 1] if index + 1 < len(text) else ""
        if character in {"'", "’"} and previous.isalnum() and following.isalnum():
            continue  # An apostrophe inside a word is not a quotation boundary.
        if quote is not None:
            if character == quote or (quote == "‘" and character == "’") or (quote == "“" and character == "”"):
                quote = None
        elif character in {'"', "“", "‘", "`"} or (character == "'" and not previous.isalnum()):
            quote = character
    return quote is not None


def _direct_statement_prefix(prefix):
    if _inside_quote(prefix):
        return False
    sentence = re.split(r"[?!;]|\.(?=\s|$)", prefix)[-1].strip(" ,\t\r\n")
    if not sentence:
        return True
    if _CONDITIONAL.search(_semantic_text(sentence)) or _has_reporting(sentence):
        return False
    if sentence.casefold() in {"and", "but"}:
        return True
    # A directly voiced user clause may precede an omission in the same
    # sentence. A reported third-party body cannot use that continuation rule.
    return bool(re.search(r"(?:,\s*)?\b(?:and|but)\s*$", sentence, re.IGNORECASE))


def _has_reporting(value):
    # A direct negative 'I have not told you ...' is an omission rather than a
    # report. Other reporting language, including quoted third-party claims,
    # keeps its existing exclusion from authoritative supply state.
    direct_omissions = _OMISSION.sub(
        lambda match: " " * len(match.group())
        if (match.group("past") or match.group("base")).casefold() in {"told", "tell"}
        else match.group(), value,
    )
    direct_supplies = list(direct_omissions)
    for match in _ACTIVE_SUPPLY.finditer(direct_omissions):
        verb = next(item for item in match.groupdict().values() if item is not None)
        if verb.casefold() == "told" and _verb_inputs(direct_omissions, match, True) is not None:
            # Only an explicitly named nominal 'I told you <input>' supply is
            # exempt from the reporting guard. 'I told you that <assertion>'
            # remains reported language, not independent current evidence.
            direct_supplies[match.start():match.end()] = " " * (match.end() - match.start())
    return bool(_REPORTING.search(_semantic_text("".join(direct_supplies))))


def _user_perspective(value):
    # Swap once: the user's own 'my' becomes assistant-rendered 'your', while
    # their 'your' remains a distinct assistant-owned item identity ('my').
    return re.sub(r"\b(?:my|your)(?=\s+\S)",
                  lambda match: "your" if match.group().casefold() == "my" else "my",
                  value, flags=re.IGNORECASE)


def _remove_terminal_symbols(value):
    # Unicode character classes cover decorative symbol/variation sequences;
    # no specific pictograph or benchmark suffix is recognized.
    value = unicodedata.normalize("NFC", value).rstrip()
    while value and unicodedata.category(value[-1]) in {"So", "Sk", "Mn", "Me", "Cf"}:
        value = value[:-1].rstrip()
    return value


def _ingress_tail(text, supply=False):
    """Return a bounded user label and its end offset, never candidate cleanup."""
    # A period starts a new statement when followed by whitespace/end. Dots
    # within filenames and decimal identifiers do not end an item label.
    stop = re.search(r"[?!;]|\.{2,}|\.(?=\s|$)", text)
    end = stop.start() if stop else len(text)
    value = text[:end]
    if supply and stop and stop.group() == "?":
        # A directly questioned supply claim is not a correction. A separate
        # question after a discourse boundary does not question the first fact.
        question_boundary = _DISCOURSE_BOUNDARY.search(_semantic_text(value))
        if question_boundary is None:
            return None, end
    boundary = _DISCOURSE_BOUNDARY.search(_semantic_text(value))
    if boundary:
        end = boundary.start()
        value = value[:boundary.start()]
    # A nominal coordinator differs from one introducing a complete finite
    # assertion. Only ingress may stop before that independently voiced tail;
    # candidate-list parsing continues to reject the complete assertion.
    coordinated = list(re.finditer(r"(?:,\s*|\s+)(?:and|or)\s+", value, re.IGNORECASE))
    for match in reversed(coordinated):
        tail = _semantic_text(value[match.end():])
        if (re.match(r"(?:the|a|an|this|that|your|my|i|you|we|they|he|she|it)\b", tail, re.IGNORECASE)
                and _AUXILIARY.search(tail)):
            end = match.start()
            value = value[:match.start()]
            break
    if _CONDITIONAL.search(_semantic_text(value)):
        return None, end
    value = _remove_terminal_symbols(value)
    adjunct = (_SUPPLY_ADJUNCT if supply else _TERMINAL_ADJUNCT).search(value)
    if adjunct:
        end = adjunct.start()
        value = value[:adjunct.start()].strip(" ,")
    else:
        value = value.strip(" ,")
    # Ownership is rendered from the user's perspective only at ingress.
    # Candidate-list parsing never changes "my" into a user-owned "your".
    return _user_perspective(_space(value)), end


def _user_tail(text):
    return _ingress_tail(text)[0]


@dataclass(frozen=True)
class _InputEvent:
    position: int
    end: int
    supplied: bool
    inputs: MissingInputs


def _item_identity(item):
    value = _space(item).casefold()
    return re.sub(r"^(?:the|a|an)\s+", "", value)


def _verb_inputs(text, match, supply):
    verb = next(value for value in match.groupdict().values() if value is not None)
    offset = match.end()
    tail = text[offset:]
    leading = len(tail) - len(tail.lstrip())
    offset += leading
    tail = tail.lstrip()
    recipient = re.match(r"you\b\s*", tail, re.IGNORECASE)
    if verb.casefold() in {"told", "tell"} and recipient is None:
        return None
    if recipient is not None:
        offset += recipient.end()
        tail = tail[recipient.end():]
        if verb.casefold() in {"provided", "supplied", "provide", "supply"}:
            with_recipient = re.match(r"with\s+", tail, re.IGNORECASE)
            if with_recipient:
                offset += with_recipient.end()
                tail = tail[with_recipient.end():]
    value, end = _ingress_tail(tail, supply=supply)
    if supply and value is not None and re.search(r"\bor\b", _semantic_text(value), re.IGNORECASE):
        # Positive disjunction does not say which named item was supplied.
        return None
    parsed = parse_missing_item_list(value) if value is not None else None
    return _InputEvent(match.start(), offset + end, supply, parsed) if parsed is not None else None


def _direct_supply_prefix(prefix):
    if _inside_quote(prefix):
        return False
    sentence = re.split(r"[?!;]|\.(?=\s|$)", prefix)[-1]
    if _CONDITIONAL.search(_semantic_text(sentence)) or _has_reporting(sentence):
        return False
    return not sentence.strip(" ,\t\r\n") or bool(
        re.search(r"(?:[,;]|\b(?:and|but|however))\s*$", sentence, re.IGNORECASE)
    )


def _passive_events(text, prior_events):
    events = []
    for match in _PASSIVE_SUPPLY.finditer(text):
        suffix, end = _ingress_tail(text[match.end():], supply=True)
        if suffix is None or not re.fullmatch(r"(?:(?:now|already|currently)\s*)*", suffix, re.IGNORECASE):
            continue
        prefix = text[:match.start()]
        stops = list(re.finditer(r"[?!;]|\.(?=\s|$)", prefix))
        beginning = stops[-1].end() if stops else 0
        starts = {beginning}
        for delimiter in re.finditer(r",\s*|\b(?:and|but|however)\s+", prefix[beginning:], re.IGNORECASE):
            starts.add(beginning + delimiter.end())
        for start in sorted(starts):
            # A delimiter inside an earlier omission's object is a nominal
            # list separator, not the subject of this later affirmative fact.
            if any(event.position <= start < event.end for event in prior_events):
                continue
            if not _direct_supply_prefix(text[:start]):
                continue
            subject = _space(prefix[start:]).strip(" ,")
            # Subject labels use the same user-perspective ownership as direct
            # object labels. No alias, substring or source-content match exists.
            subject = _user_perspective(subject)
            parsed = parse_missing_item_list(subject)
            if parsed is not None and re.search(r"\bor\b", _semantic_text(subject), re.IGNORECASE):
                # This whole subject is a disjunctive list. Retrying only its
                # last comma fragment would fabricate an unambiguous supply.
                break
            if parsed is None and subject.casefold() == "it":
                preceding = [event for event in prior_events + events if event.position < start]
                previous = max(preceding, key=lambda event: event.position) if preceding else None
                if previous is not None and not previous.supplied and len(previous.inputs.items) == 1:
                    gap = text[previous.end:start]
                    gap = "".join(character for character in gap
                                  if unicodedata.category(character) not in {"So", "Sk", "Mn", "Me", "Cf"})
                    if re.fullmatch(
                        r"\s*(?:(?:as\s+yet|yet|so\s+far|at\s+present|for\s+now|currently)\s*)?"
                        r"[,.;!]*\s*(?:(?:and|but)\s*)?", gap, re.IGNORECASE,
                    ):
                        parsed = previous.inputs
            if parsed is not None:
                events.append(_InputEvent(start, match.end() + end, True, parsed))
                break
    return events


def _input_events(text):
    events = []
    for pattern, supplied in ((_OMISSION, False), (_ACTIVE_SUPPLY, True)):
        for match in pattern.finditer(text):
            if not _direct_statement_prefix(text[:match.start()]):
                continue
            event = _verb_inputs(text, match, supplied)
            if event is not None:
                events.append(event)
    events.extend(_passive_events(text, events))
    return sorted(events, key=lambda event: event.position)


def _resolved_inputs(user_texts):
    pending = {}
    for text in user_texts:
        for event in _input_events(text):
            for item in event.inputs.items:
                identity = _item_identity(item)
                if event.supplied:
                    pending.pop(identity, None)
                else:
                    pending[identity] = (item, event.inputs)
    if not pending:
        return None
    items = tuple(item for item, _ in pending.values())
    first_description = next(iter(pending.values()))[1]
    if items == first_description.items and all(group == first_description for _, group in pending.values()):
        return first_description
    description = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]
    if len(items) > _MAX_ITEMS or len(description) > _MAX_DESCRIPTION:
        return None
    return MissingInputs(items, description)


def extract_missing_inputs(text: str) -> Optional[MissingInputs]:
    """Resolve this user turn's explicit omissions and item-level corrections."""
    if not isinstance(text, str):
        return None
    return _resolved_inputs((text,))


def resolve_missing_inputs(conversation, user_input=None) -> Optional[MissingInputs]:
    """Fold chronological USER evidence; assistant/candidate prose has no role.

    An affirmative supply cancels only the same normalized nominal identity.
    Unsupported or ambiguous language cannot manufacture a state correction.
    """
    user_texts = []
    for record in conversation or ():
        if isinstance(record, dict):
            role, content = record.get("role"), record.get("content")
        else:
            role, content = getattr(record, "role", None), getattr(record, "content", None)
        if str(getattr(role, "value", role) or "").casefold() == "user" and isinstance(content, str):
            user_texts.append(content)
    if isinstance(user_input, str):
        user_texts.append(user_input)
    return _resolved_inputs(user_texts)
