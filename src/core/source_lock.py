import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# --------------------------------------------------
# Phase 6.8.9 — source-locked conversational anchors
# --------------------------------------------------
#
# This module is intentionally small. It is NOT a general-purpose NLP parser
# or knowledge graph. Its job is to preserve a few high-value structural facts
# that ordinary conversational generation must not silently rewrite:
#
#   - entity identity / possession;
#   - actor -> target direction;
#   - user/Mairon personal-history authority.
#
# The semantic verifier still handles fuzzy language. These anchors give Core a
# deterministic layer beneath that verifier so Qwen is not the only thing
# deciding whether Qwen changed the scene.


_WORD_RE = re.compile(
    r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?"
)

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+"
)


POSSESSION_BOUNDARIES = {
    "am", "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did", "can", "could",
    "will", "would", "shall", "should", "may", "might", "must",
    "got", "gets", "get", "came", "come", "arrived", "turned",
    "looks", "look", "feels", "feel", "seems", "seem",
    "at", "in", "on", "of", "for", "from", "with", "without", "before",
    "after", "during", "while", "when", "because", "if", "but", "and",
    "or", "so", "than", "that", "which", "who", "where", "to",

    # Pronouns/deictics and obvious temporal words terminate a possessive
    # noun phrase. Phase 6.8.11's token-only scan could otherwise turn
    # "my desk this morning. It..." into the absurd entity
    # "desk this morning it".
    "i", "me", "you", "he", "him", "she", "her", "we", "us",
    "they", "them", "it", "this", "these", "those",
    "today", "tonight", "tomorrow", "yesterday", "morning",
    "afternoon", "evening", "night", "now", "currently", "later",
    "next",
}


ACTION_SKIP_WORDS = {
    "am", "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did", "can", "could",
    "will", "would", "shall", "should", "may", "might", "must",
    "not", "never", "still", "just", "really", "actually", "probably",
    "apparently", "basically", "literally", "to", "the", "a", "an",
    "my", "your", "our", "their", "his", "her", "its", "this", "that",
    "need", "needs", "needed", "want", "wants", "wanted", "try", "tries",
    "tried", "supposed", "got", "gotta", "keep", "keeps", "kept",
    "and", "or", "but", "on", "at", "in", "of", "for", "with", "without",
    "up", "down", "out", "off", "back", "again",
}


TEMPORAL_STOP_WORDS = {
    "every", "each", "before", "after", "during", "tonight", "today",
    "tomorrow", "yesterday", "morning", "afternoon", "evening", "night",
    "week", "month", "year", "while", "when", "because", "if",
}


HISTORY_STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "been", "before",
    "being", "but", "did", "didn", "does", "doing", "earlier", "for",
    "from", "have", "had", "has", "here", "into", "just", "last", "least",
    "like", "me", "my", "once", "only", "other", "probably", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "time", "to",
    "was", "were", "what", "when", "where", "which", "while", "with", "you",
    "your", "yours", "i", "it", "its", "some", "thing", "things",
}


PERCENT_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}

PERCENT_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

ABSTRACT_SCENE_HEADS = {
    "amount", "anxiety", "idea", "point", "sense", "way", "kind", "sort",
    "state", "feeling", "feelings", "optimism", "dignity", "sympathy",
    "statement", "panic", "doom", "control", "percentage", "percent",
    "span", "ego", "sanity", "patience", "luck", "mood", "stress",
}

ABSTRACT_SCENE_SUFFIXES = (
    "tion", "sion", "ness", "ity", "ship", "ism", "ance", "ence", "hood",
)


# Phase 6.8.13: actor/target direction is not a universal ban on the
# opposite speaker ever acting on the other person. A user statement such as
# "I debug you" locks that MAINTENANCE relation; it does not mean Mairon may
# never mock, remember, thank, or otherwise refer to Oliver. Keep deterministic
# reversal checks only for the same lexical action or a high-confidence
# semantic action family. Fuzzier role interpretation remains the verifier's job.
RELATION_ACTION_FAMILIES = {
    "maintenance": {
        "debug", "debugs", "debugged", "debugging",
        "fix", "fixes", "fixed", "fixing",
        "patch", "patches", "patched", "patching",
        "repair", "repairs", "repaired", "repairing",
        "troubleshoot", "troubleshoots", "troubleshot", "troubleshooting",
        "maintain", "maintains", "maintained", "maintaining",
        "configure", "configures", "configured", "configuring",
        "focus", "focuses", "focused", "focusing",
        "program", "programs", "programmed", "programming",
        "test", "tests", "tested", "testing",
    },
    "memory": {
        "remember", "remembers", "remembered", "remembering",
        "forget", "forgets", "forgot", "forgotten", "forgetting",
        "recall", "recalls", "recalled", "recalling",
    },
    "social": {
        "mock", "mocks", "mocked", "mocking",
        "tease", "teases", "teased", "teasing",
        "insult", "insults", "insulted", "insulting",
    },
}


TEMPORAL_RELATION_PATTERNS = {
    "morning": (
        r"\b(?:this\s+|that\s+)?morning\b",
    ),
    "night": (
        r"\b(?:last\s+|this\s+|every\s+|each\s+)?night\b",
        r"\bovernight\b",
        r"\btonight\b",
    ),
    "today": (r"\btoday\b",),
    "tomorrow": (r"\btomorrow\b",),
    "yesterday": (r"\byesterday\b",),
    "before_work": (r"\bbefore\s+work\b",),
    "after_work": (r"\bafter\s+work\b",),
    "before_bed": (r"\bbefore\s+(?:bed|sleep)\b",),
    "after_bed": (r"\bafter\s+(?:bed|sleep)\b",),
}


@dataclass(frozen=True)
class PossessionAnchor:
    owner: str
    entity: str
    source_quote: str

    @property
    def key(self) -> str:
        return canonical_entity_key(
            self.entity
        )


@dataclass(frozen=True)
class DirectedRelation:
    actor: str
    action: str
    target: str
    source_quote: str


@dataclass
class SourceLockPacket:
    current_user_text: str
    prior_user_texts: Tuple[str, ...] = field(
        default_factory=tuple
    )
    possessions: Tuple[PossessionAnchor, ...] = field(
        default_factory=tuple
    )
    relations: Tuple[DirectedRelation, ...] = field(
        default_factory=tuple
    )

    @property
    def all_user_texts(self) -> Tuple[str, ...]:
        values = list(
            self.prior_user_texts
        )

        if self.current_user_text:
            values.append(
                self.current_user_text
            )

        return tuple(
            values
        )

    def possession_keys(
        self,
        owner: str,
    ) -> set:
        return {
            item.key
            for item in self.possessions
            if item.owner == owner
            and item.key
        }

    def relation_pairs(
        self,
    ) -> set:
        return {
            (
                item.actor,
                item.target,
            )
            for item in self.relations
        }


# --------------------------------------------------
# Conversation helpers
# --------------------------------------------------


def _message_role_and_content(
    message: Any,
) -> Tuple[Optional[str], str]:
    if isinstance(
        message,
        dict,
    ):
        return (
            message.get(
                "role"
            ),
            str(
                message.get(
                    "content"
                )
                or ""
            ),
        )

    return (
        getattr(
            message,
            "role",
            None,
        ),
        str(
            getattr(
                message,
                "content",
                "",
            )
            or ""
        ),
    )


def recent_user_texts(
    conversation,
    max_messages: int = 4,
) -> Tuple[str, ...]:
    if int(
        max_messages
    ) <= 0:
        return tuple()

    collected = []

    for message in reversed(
        list(
            conversation
            or []
        )
    ):
        role, content = (
            _message_role_and_content(
                message
            )
        )

        if role != "user":
            continue

        value = re.sub(
            r"\s+",
            " ",
            str(
                content
                or ""
            ),
        ).strip()

        if not value:
            continue

        collected.append(
            value
        )

        if len(
            collected
        ) >= max(
            0,
            int(
                max_messages
            ),
        ):
            break

    collected.reverse()

    return tuple(
        collected
    )


def recommended_source_lock_prior_window(
    user_input: str,
    intent: Optional[str],
) -> int:
    """
    Match Phase 6.7 context isolation: prior USER text enters a source-lock
    packet only when the current wording genuinely points backward.
    """

    intent_value = str(
        intent
        or ""
    ).strip().lower()

    if intent_value == "conversation_recall":
        return 12

    text = str(
        user_input
        or ""
    ).strip().lower()

    if not text:
        return 0

    if re.search(
        r"\b(?:it|its|that|this|they|them|their|those|these|he|his|she|him|her)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return 1

    if any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in (
            r"^\s*at\s+least\b",
            r"^\s*also\b",
            r"^\s*and\b",
            r"^\s*but\b",
            r"^\s*same\b",
            r"^\s*back\s+to\b",
        )
    ):
        return 1

    return 0


# --------------------------------------------------
# Normalisation / extraction
# --------------------------------------------------


def _normalise_apostrophes(
    text: str,
) -> str:
    return str(
        text
        or ""
    ).replace(
        "’",
        "'",
    ).replace(
        "‘",
        "'",
    )


def canonical_entity_key(
    entity: str,
) -> str:
    value = _normalise_apostrophes(
        entity
    ).lower()

    value = re.sub(
        r"\b([a-z0-9]+)'s\b",
        r"\1",
        value,
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _words_with_spans(
    text: str,
):
    return list(
        _WORD_RE.finditer(
            _normalise_apostrophes(
                text
            )
        )
    )


def _sentence_for_span(
    text: str,
    start: int,
    end: int,
) -> str:
    left_candidates = [
        text.rfind(
            marker,
            0,
            start,
        )
        for marker in (
            ".",
            "!",
            "?",
        )
    ]

    left = max(
        left_candidates
    )

    right_candidates = [
        position
        for position in (
            text.find(
                marker,
                end,
            )
            for marker in (
                ".",
                "!",
                "?",
            )
        )
        if position != -1
    ]

    right = (
        min(
            right_candidates
        )
        + 1
        if right_candidates
        else len(
            text
        )
    )

    return re.sub(
        r"\s+",
        " ",
        text[
            left + 1:right
        ],
    ).strip()


def _extract_possessions(
    text: str,
    perspective: str,
) -> List[PossessionAnchor]:
    """
    Extract explicit possessive noun phrases.

    perspective="user":
        my/our -> Oliver, your -> Mairon

    perspective="assistant":
        your -> Oliver, my/our -> Mairon
    """

    value = _normalise_apostrophes(
        text
    )

    words = _words_with_spans(
        value
    )

    results = []

    for index, match in enumerate(
        words
    ):
        determiner = match.group(
            0
        ).lower()

        if determiner not in {
            "my",
            "our",
            "your",
        }:
            continue

        if perspective == "assistant":
            owner = (
                "Oliver"
                if determiner == "your"
                else "Mairon"
            )
        else:
            owner = (
                "Mairon"
                if determiner == "your"
                else "Oliver"
            )

        entity_words = []
        previous_match = match

        for next_match in words[
            index + 1:index + 5
        ]:
            # Never let a possessive noun phrase cross punctuation or a
            # sentence/clause boundary. _WORD_RE deliberately ignores
            # punctuation, so without this span check "your desk, Oliver.
            # Now you..." became one giant fake entity.
            separator = value[
                previous_match.end():next_match.start()
            ]

            if re.search(
                r"[.!?,;:\n\r]",
                separator,
            ):
                break

            token = next_match.group(
                0
            )

            token_lower = token.lower()

            if token_lower in POSSESSION_BOUNDARIES:
                break

            entity_words.append(
                token
            )

            previous_match = next_match

        if not entity_words:
            continue

        entity = " ".join(
            entity_words
        ).strip()

        # Source-lock possession anchors are for concrete identity/ownership.
        # Abstract personal qualities such as "your attention span" or
        # "my dignity" are better left to semantic grounding; treating them
        # as interchangeable concrete objects creates false substitution alarms.
        entity_head = canonical_entity_key(
            entity_words[-1]
        )

        if (
            entity_head in ABSTRACT_SCENE_HEADS
            or entity_head.endswith(
                ABSTRACT_SCENE_SUFFIXES
            )
        ):
            continue

        source_quote = _sentence_for_span(
            value,
            match.start(),
            words[
                min(
                    index + len(
                        entity_words
                    ),
                    len(
                        words
                    ) - 1,
                )
            ].end(),
        )

        anchor = PossessionAnchor(
            owner=owner,
            entity=entity,
            source_quote=source_quote,
        )

        if anchor.key and anchor not in results:
            results.append(
                anchor
            )

    return results


def _extract_action_word(
    text: str,
    prefer_last: bool = False,
) -> Optional[str]:
    tokens = [
        token.group(
            0
        ).lower()
        for token in _WORD_RE.finditer(
            _normalise_apostrophes(
                text
            )
        )
    ]

    candidates = []

    for token in tokens:
        if token in TEMPORAL_STOP_WORDS:
            if candidates:
                break

            continue

        if token in ACTION_SKIP_WORDS:
            continue

        if token.endswith(
            "ly"
        ):
            continue

        candidates.append(
            token
        )

    if not candidates:
        return None

    return (
        candidates[-1]
        if prefer_last
        else candidates[0]
    )


def _normalise_contractions_for_relations(
    text: str,
) -> str:
    value = _normalise_apostrophes(
        text
    )

    replacements = (
        (r"\bI'm\b", "I am"),
        (r"\bI've\b", "I have"),
        (r"\bI'll\b", "I will"),
        (r"\bI'd\b", "I would"),
        (r"\byou're\b", "you are"),
        (r"\byou've\b", "you have"),
        (r"\byou'll\b", "you will"),
        (r"\byou'd\b", "you would"),
    )

    for pattern, replacement in replacements:
        value = re.sub(
            pattern,
            replacement,
            value,
            flags=re.IGNORECASE,
        )

    return value


def _relation_roles(
    perspective: str,
    subject_token: str,
    object_token: str,
) -> Tuple[Optional[str], Optional[str]]:
    subject = subject_token.lower()
    object_value = object_token.lower()

    if perspective == "assistant":
        subject_map = {
            "i": "Mairon",
            "you": "Oliver",
        }
        object_map = {
            "me": "Mairon",
            "you": "Oliver",
        }
    else:
        subject_map = {
            "i": "Oliver",
            "you": "Mairon",
        }
        object_map = {
            "me": "Oliver",
            "you": "Mairon",
        }

    return (
        subject_map.get(
            subject
        ),
        object_map.get(
            object_value
        ),
    )


def _extract_direct_relations(
    text: str,
    perspective: str,
) -> List[DirectedRelation]:
    value = _normalise_contractions_for_relations(
        text
    )

    results = []

    patterns = (
        re.compile(
            r"\b(?P<subject>I|you)\b(?P<middle>[^.!?]{1,70}?)"
            r"\b(?P<object>you|me)\b",
            flags=re.IGNORECASE,
        ),
    )

    for pattern in patterns:
        for match in pattern.finditer(
            value
        ):
            actor, target = _relation_roles(
                perspective=perspective,
                subject_token=match.group(
                    "subject"
                ),
                object_token=match.group(
                    "object"
                ),
            )

            if not actor or not target:
                continue

            middle = match.group(
                "middle"
            )

            # High-confidence relation extraction only. A later "you/me" can
            # start a new clause or be the object of a preposition rather than
            # the target of the earlier subject's action:
            #
            #   "I'll stop acting like a god while you're debugging me."
            #   "I'll keep my code clean enough for you to sleep."
            #
            # Treating those as I->you relations caused live false positives.
            # Source-lock should under-detect ambiguous syntax rather than
            # manufacture a relation and reject otherwise good generation.
            if re.search(
                r"\b(?:while|when|because|if|although|though|unless|until|"
                r"whereas|before|after|for)\b",
                middle,
                flags=re.IGNORECASE,
            ):
                continue

            # Do not mistake a copular noun phrase for a transitive action.
            # Example: "I'm still the thing you have to debug". Here the
            # later "you" starts a relative clause; it is not the object of
            # an action performed by "I".
            if (
                re.search(
                    r"\b(?:am|is|are|was|were)\b",
                    middle,
                    flags=re.IGNORECASE,
                )
                and re.search(
                    r"\b(?:the|a|an)\b",
                    middle,
                    flags=re.IGNORECASE,
                )
            ):
                continue

            # The lexical item nearest the object pronoun is normally the
            # transitive action ("debug you", "keep mocking you"). Using the
            # first lexical item incorrectly promoted nouns such as "code".
            action = _extract_action_word(
                middle,
                prefer_last=True,
            )

            if not action:
                continue

            relation = DirectedRelation(
                actor=actor,
                action=action,
                target=target,
                source_quote=_sentence_for_span(
                    value,
                    match.start(),
                    match.end(),
                ),
            )

            if relation not in results:
                results.append(
                    relation
                )

    return results


def _extract_relative_you_relation(
    text: str,
) -> List[DirectedRelation]:
    """
    Handle ordinary user constructions where the target is the earlier "you":

        "You're still the assistant I have to debug every night."

    The relation direction is structurally clear even though the object of
    "debug" is represented by the relative-clause antecedent rather than a
    second literal "you" token.
    """

    value = _normalise_contractions_for_relations(
        text
    )

    results = []

    pattern = re.compile(
        r"\byou\s+(?:are|were|have\s+been)\b"
        r"(?P<descriptor>[^.!?]{0,100}?)"
        r"\bI\b(?P<middle>[^.!?]{1,65})",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(
        value
    ):
        action = _extract_action_word(
            match.group(
                "middle"
            )
        )

        if not action:
            continue

        relation = DirectedRelation(
            actor="Oliver",
            action=action,
            target="Mairon",
            source_quote=_sentence_for_span(
                value,
                match.start(),
                match.end(),
            ),
        )

        if relation not in results:
            results.append(
                relation
            )

    return results


def _extract_assistant_possession_actions(
    text: str,
) -> List[DirectedRelation]:
    """
    Detect assistant claims that Mairon is acting on something Oliver owns.

    Two ordinary grammatical shapes matter here:

        direct:
            "I'll focus on your code."
            "I can fix your laptop."

        embedded first-person infinitive:
            "Don't expect me to fix your code."
            "You can't get me to rewrite your notes."

    The second shape was the live Phase 6.8.9 miss. Grammatically, "me" is
    still the understood actor of the infinitive, so Core must preserve the
    Mairon -> Oliver direction even when the clause does not contain a second
    literal "I" token.

    This remains structural rather than verb-specific: the action word is
    extracted from the clause instead of enumerating "fix", "debug", etc.
    """

    value = _normalise_contractions_for_relations(
        text
    )

    results = []

    direct_pattern = re.compile(
        r"\bI\b(?P<middle>[^.!?]{1,90}?)\byour\s+"
        r"(?P<entity>[A-Za-z0-9]+(?:['’][A-Za-z]+)?)",
        flags=re.IGNORECASE,
    )

    embedded_pattern = re.compile(
        r"\bme\b\s+(?:to\s+)?(?P<middle>[^.!?]{1,70}?)\byour\s+"
        r"(?P<entity>[A-Za-z0-9]+(?:['’][A-Za-z]+)?)",
        flags=re.IGNORECASE,
    )

    for pattern in (
        direct_pattern,
        embedded_pattern,
    ):
        for match in pattern.finditer(
            value
        ):
            action = _extract_action_word(
                match.group(
                    "middle"
                ),
                prefer_last=True,
            )

            if not action:
                continue

            relation = DirectedRelation(
                actor="Mairon",
                action=action,
                target="Oliver",
                source_quote=_sentence_for_span(
                    value,
                    match.start(),
                    match.end(),
                ),
            )

            if relation not in results:
                results.append(
                    relation
                )

    return results


def _parse_percent_word_phrase(
    phrase: str,
) -> Optional[int]:
    value = str(
        phrase
        or ""
    ).lower().replace(
        "-",
        " ",
    )

    parts = [
        part
        for part in value.split()
        if part
    ]

    if not parts:
        return None

    if len(parts) == 1:
        if parts[0] in PERCENT_ONES:
            return PERCENT_ONES[
                parts[0]
            ]

        if parts[0] in PERCENT_TENS:
            return PERCENT_TENS[
                parts[0]
            ]

        if parts[0] == "hundred":
            return 100

        return None

    if (
        len(parts) == 2
        and parts[0] in PERCENT_TENS
        and parts[1] in PERCENT_ONES
        and PERCENT_ONES[parts[1]] < 10
    ):
        return (
            PERCENT_TENS[parts[0]]
            + PERCENT_ONES[parts[1]]
        )

    if parts == ["one", "hundred"]:
        return 100

    return None


def _extract_percentage_values(
    text: str,
) -> set:
    value = _normalise_apostrophes(
        text
    ).lower()

    percentages = set()

    for match in re.finditer(
        r"\b(100|[0-9]{1,2})\s*%",
        value,
    ):
        percentages.add(
            int(
                match.group(
                    1
                )
            )
        )

    word_pattern = (
        r"\b("
        r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
        r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
        r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
        r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?"
        r"|one[- ]hundred"
        r")\s+percent\b"
    )

    for match in re.finditer(
        word_pattern,
        value,
        flags=re.IGNORECASE,
    ):
        parsed = _parse_percent_word_phrase(
            match.group(
                1
            )
        )

        if parsed is not None:
            percentages.add(
                parsed
            )

    return percentages


def _extract_article_scene_candidates(
    text: str,
) -> List[Tuple[str, str]]:
    value = _normalise_apostrophes(
        text
    )

    words = _words_with_spans(
        value
    )

    candidates = []

    for index, match in enumerate(
        words
    ):
        article = match.group(
            0
        ).lower()

        if article not in {
            "a",
            "an",
            "the",
        }:
            continue

        phrase_words = []

        for next_match in words[
            index + 1:index + 4
        ]:
            token = next_match.group(
                0
            )

            if token.lower() in POSSESSION_BOUNDARIES:
                break

            phrase_words.append(
                token
            )

        if not phrase_words:
            continue

        phrase = " ".join(
            phrase_words
        ).strip()

        head = canonical_entity_key(
            phrase_words[-1]
        )

        if not head:
            continue

        if head in ABSTRACT_SCENE_HEADS:
            continue

        if head.endswith(
            ABSTRACT_SCENE_SUFFIXES
        ):
            continue

        candidates.append((
            phrase,
            head,
        ))

    return candidates


def _copular_predicate_signature(
    anchor: PossessionAnchor,
) -> Optional[str]:
    """
    Extract a small surface predicate bound to a possessive entity.

    This is intentionally conservative. It only handles explicit copular
    forms such as:
        "my iPad is fully charged" -> "fully charged"
        "my monitor is 4K"         -> "4k"

    The goal is not general semantic parsing; it is to stop an explicit
    source-bound property from migrating to a different concrete entity.
    """

    quote = _normalise_apostrophes(
        anchor.source_quote
    )

    entity_pattern = re.escape(
        anchor.entity
    )

    match = re.search(
        entity_pattern
        + r"\s+(?:is|are|was|were)\s+"
        + r"(?P<predicate>[^.!?,;:]{1,48})",
        quote,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    predicate = canonical_entity_key(
        match.group(
            "predicate"
        )
    )

    # Stop before obvious discourse continuation.
    predicate = re.split(
        r"\b(?:but|and|while|because|before|after|though|although)\b",
        predicate,
        maxsplit=1,
    )[0].strip()

    if not predicate:
        return None

    return predicate


def _source_copular_predicate_bindings(
    packet: SourceLockPacket,
) -> Dict[str, set]:
    bindings: Dict[str, set] = {}

    for anchor in packet.possessions:
        signature = _copular_predicate_signature(
            anchor
        )

        if not signature:
            continue

        bindings.setdefault(
            signature,
            set(),
        ).add(
            anchor.key
        )

    return bindings


def _source_percentage_bindings(
    packet: SourceLockPacket,
) -> Dict[int, set]:
    bindings: Dict[int, set] = {}

    for anchor in packet.possessions:
        values = _extract_percentage_values(
            anchor.source_quote
        )

        for value in values:
            bindings.setdefault(
                value,
                set(),
            ).add(
                anchor.key
            )

    return bindings


def build_source_lock_packet(
    user_input: str,
    conversation=None,
    max_prior_user_messages: int = 4,
) -> SourceLockPacket:
    current = re.sub(
        r"\s+",
        " ",
        str(
            user_input
            or ""
        ),
    ).strip()

    prior = recent_user_texts(
        conversation=conversation,
        max_messages=max_prior_user_messages,
    )

    source_texts = list(
        prior
    )

    if current:
        source_texts.append(
            current
        )

    possessions = []
    relations = []

    for source_text in source_texts:
        for anchor in _extract_possessions(
            source_text,
            perspective="user",
        ):
            if anchor not in possessions:
                possessions.append(
                    anchor
                )

        for relation in _extract_direct_relations(
            source_text,
            perspective="user",
        ):
            if relation not in relations:
                relations.append(
                    relation
                )

        for relation in _extract_relative_you_relation(
            source_text
        ):
            if relation not in relations:
                relations.append(
                    relation
                )

    return SourceLockPacket(
        current_user_text=current,
        prior_user_texts=prior,
        possessions=tuple(
            possessions
        ),
        relations=tuple(
            relations
        ),
    )


# --------------------------------------------------
# Rendering for generation / semantic verification
# --------------------------------------------------


def build_source_lock_instruction(
    user_input: str,
    conversation=None,
    intent: Optional[str] = None,
    max_prior_user_messages: int = 4,
) -> Optional[str]:
    relevant_intents = {
        "share_context",
        "casual_conversation",
        "conversation_recall",
        "self_correction",
        "factual_question",
    }

    if intent and intent not in relevant_intents:
        return None

    packet = build_source_lock_packet(
        user_input=user_input,
        conversation=conversation,
        max_prior_user_messages=max_prior_user_messages,
    )

    lines = [
        "CORE SOURCE-LOCK ANCHORS:",
        "These are structural locks derived only from USER-authored text. They do not add new facts.",
    ]

    if packet.possessions:
        lines.append(
            "Locked possession/entity anchors:"
        )

        for item in packet.possessions:
            lines.append(
                f"- {item.owner} -> {item.entity!r} [user quote: {item.source_quote!r}]"
            )
    else:
        lines.append(
            "Locked possession/entity anchors: none extracted."
        )

    if packet.relations:
        lines.append(
            "Locked directed relations:"
        )

        for item in packet.relations:
            lines.append(
                f"- {item.actor} --{item.action}--> {item.target} "
                f"[user quote: {item.source_quote!r}]"
            )
    else:
        lines.append(
            "Locked directed relations: none extracted."
        )

    lines.extend([
        "Source-lock rules:",
        "- Never substitute a different concrete entity for a locked entity merely because it is plausible or related.",
        "- Never reverse actor/target direction. Oliver -> Mairon does not authorise Mairon -> Oliver.",
        "- A new Oliver-owned or Mairon-owned object is not implied by a locked object.",
        "- Personal history or prior Mairon actions require USER-authored support from the supplied conversation; do not invent callbacks.",
        "- Obvious personification of an already locked entity is fine when it adds no new concrete scene premise.",
    ])

    return "\n".join(
        lines
    )


def build_draft_source_lock_diagnostics(
    draft: str,
) -> str:
    possessions = _extract_possessions(
        draft,
        perspective="assistant",
    )

    relations = _extract_direct_relations(
        draft,
        perspective="assistant",
    )

    relations.extend(
        _extract_assistant_possession_actions(
            draft
        )
    )

    lines = [
        "CORE DRAFT SOURCE-LOCK CANDIDATES:",
        "Core extracted these structural candidates from the proposed draft. Check them explicitly rather than relying on topic similarity.",
    ]

    if possessions:
        lines.append(
            "Draft possession/entity candidates:"
        )

        for item in possessions:
            lines.append(
                f"- {item.owner} -> {item.entity!r} [draft quote: {item.source_quote!r}]"
            )
    else:
        lines.append(
            "Draft possession/entity candidates: none extracted."
        )

    if relations:
        lines.append(
            "Draft directed-relation candidates:"
        )

        for item in relations:
            lines.append(
                f"- {item.actor} --{item.action}--> {item.target} "
                f"[draft quote: {item.source_quote!r}]"
            )
    else:
        lines.append(
            "Draft directed-relation candidates: none extracted."
        )

    return "\n".join(
        lines
    )


def _relation_action_family(
    action: str,
) -> Optional[str]:
    key = canonical_entity_key(
        action
    )

    if not key:
        return None

    for family, variants in RELATION_ACTION_FAMILIES.items():
        if key in variants:
            return family

    return None


def _relation_actions_share_lock(
    source_action: str,
    draft_action: str,
) -> bool:
    source_key = canonical_entity_key(
        source_action
    )
    draft_key = canonical_entity_key(
        draft_action
    )

    if (
        source_key
        and draft_key
        and source_key == draft_key
    ):
        return True

    source_family = _relation_action_family(
        source_action
    )
    draft_family = _relation_action_family(
        draft_action
    )

    return bool(
        source_family
        and draft_family
        and source_family == draft_family
    )


def _temporal_relation_categories(
    text: str,
) -> set:
    value = _normalise_apostrophes(
        text
    )

    categories = set()

    for category, patterns in TEMPORAL_RELATION_PATTERNS.items():
        if any(
            re.search(
                pattern,
                value,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        ):
            categories.add(
                category
            )

    return categories


# --------------------------------------------------
# Deterministic source-lock checks
# --------------------------------------------------


def find_structural_source_lock_violations(
    user_input: str,
    draft: str,
    conversation=None,
    max_prior_user_messages: int = 4,
) -> List[str]:
    packet = build_source_lock_packet(
        user_input=user_input,
        conversation=conversation,
        max_prior_user_messages=max_prior_user_messages,
    )

    draft_possessions = _extract_possessions(
        draft,
        perspective="assistant",
    )

    draft_relations = _extract_direct_relations(
        draft,
        perspective="assistant",
    )

    draft_relations.extend(
        _extract_assistant_possession_actions(
            draft
        )
    )

    violations = []

    source_text_norm = canonical_entity_key(
        " ".join(
            packet.all_user_texts
        )
    )

    # Phase 6.8.12 deliberately does NOT reject every newly phrased
    # possessive noun merely because some other possession was locked.
    # "your head", "your clutter", or "your ego" can appear in harmless
    # metaphor and are not automatically substitutions for "your desk".
    # Concrete identity substitution is enforced only when a source-bound
    # predicate/value is actually transferred to the novel entity (see
    # quantitative and copular-predicate bindings below).

    # Preserve quantitative bindings. If Oliver attached a percentage to a
    # locked entity, a draft may talk elliptically about the percentage, but it
    # must not use that same scalar to introduce a different plausible scene
    # object. This catches substitutions such as XM6s@40% -> "a dying phone"
    # without knowing anything about headphones or phones specifically.
    percentage_bindings = _source_percentage_bindings(
        packet
    )

    if percentage_bindings:
        source_norm = canonical_entity_key(
            " ".join(
                packet.all_user_texts
            )
        )

        for sentence in _SENTENCE_SPLIT_RE.split(
            str(
                draft
                or ""
            ).strip()
        ):
            draft_values = _extract_percentage_values(
                sentence
            )

            for value in (
                draft_values
                & set(
                    percentage_bindings
                )
            ):
                locked_entities = percentage_bindings[
                    value
                ]

                for phrase, head in _extract_article_scene_candidates(
                    sentence
                ):
                    if head in source_norm:
                        continue

                    if any(
                        locked in head
                        or head in locked
                        for locked in locked_entities
                    ):
                        continue

                    violations.append(
                        "unsupported Core-grounded claim: source-lock quantitative binding "
                        f"moved {value}% away from locked entity/entities "
                        f"{sorted(locked_entities)!r} onto novel scene candidate {phrase!r}"
                    )

    # Preserve explicit copular property bindings. If Oliver says
    # "my iPad is fully charged", Core may not silently rewrite that as
    # "your phone is fully charged". This is the general property-transfer
    # check that replaces the old blanket "any new possession is bad" rule.
    copular_bindings = _source_copular_predicate_bindings(
        packet
    )

    if copular_bindings:
        for candidate in draft_possessions:
            if candidate.owner != "Oliver":
                continue

            signature = _copular_predicate_signature(
                candidate
            )

            if not signature:
                continue

            locked_entities = copular_bindings.get(
                signature
            )

            if not locked_entities:
                continue

            if candidate.key in locked_entities:
                continue

            if any(
                locked in candidate.key
                or candidate.key in locked
                for locked in locked_entities
            ):
                continue

            violations.append(
                "unsupported Core-grounded claim: source-lock entity substitution/"
                f"invention: draft moved predicate {signature!r} from locked "
                f"entity/entities {sorted(locked_entities)!r} onto "
                f"Oliver-owned entity {candidate.entity!r}"
            )

    # A percentage can also be transferred onto a possessive noun phrase
    # ("Forty percent ... your phone") rather than an article phrase
    # ("a dying phone"). Catch both surfaces.
    if percentage_bindings:
        for sentence in _SENTENCE_SPLIT_RE.split(
            str(
                draft
                or ""
            ).strip()
        ):
            draft_values = _extract_percentage_values(
                sentence
            )

            shared_values = (
                draft_values
                & set(
                    percentage_bindings
                )
            )

            if not shared_values:
                continue

            sentence_possessions = _extract_possessions(
                sentence,
                perspective="assistant",
            )

            for value in shared_values:
                locked_entities = percentage_bindings[
                    value
                ]

                for candidate in sentence_possessions:
                    if candidate.owner != "Oliver":
                        continue

                    if candidate.key in locked_entities:
                        continue

                    if any(
                        locked in candidate.key
                        or candidate.key in locked
                        for locked in locked_entities
                    ):
                        continue

                    violations.append(
                        "unsupported Core-grounded claim: source-lock entity substitution/"
                        f"invention: draft moved {value}% from locked "
                        f"entity/entities {sorted(locked_entities)!r} onto "
                        f"Oliver-owned entity {candidate.entity!r}"
                    )

    # Phase 6.8.13: actor/target direction is scoped to the relation itself,
    # not globally to the two participants. "Oliver debugs Mairon" does not
    # prohibit Mairon from mocking or remembering Oliver. Reject the opposite
    # direction only when the draft uses the same action or a high-confidence
    # semantic action family (for example debug <-> fix/repair).
    source_relations_by_pair = {}

    for source_relation in packet.relations:
        pair = (
            source_relation.actor,
            source_relation.target,
        )

        source_relations_by_pair.setdefault(
            pair,
            [],
        ).append(
            source_relation
        )

    if source_relations_by_pair:
        for relation in draft_relations:
            pair = (
                relation.actor,
                relation.target,
            )

            reverse_pair = (
                relation.target,
                relation.actor,
            )

            if pair in source_relations_by_pair:
                continue

            reverse_sources = source_relations_by_pair.get(
                reverse_pair,
                [],
            )

            if not reverse_sources:
                continue

            matching_source = next(
                (
                    source_relation
                    for source_relation in reverse_sources
                    if _relation_actions_share_lock(
                        source_action=source_relation.action,
                        draft_action=relation.action,
                    )
                ),
                None,
            )

            if matching_source is None:
                continue

            violations.append(
                "unsupported Core-grounded claim: source-lock relation reversal: "
                f"draft asserted {relation.actor} --{relation.action}--> "
                f"{relation.target} but user-authored evidence locks "
                f"{matching_source.actor} --{matching_source.action}--> "
                f"{matching_source.target}"
            )

    # Concrete temporal relations are source-locked too. If a draft attaches a
    # new morning/night/today/etc. relation to an explicitly locked entity, that
    # temporal premise must appear somewhere in the user-authored source packet.
    source_temporal_categories = set()

    for source_text in packet.all_user_texts:
        source_temporal_categories.update(
            _temporal_relation_categories(
                source_text
            )
        )

    locked_entity_keys = {
        item.key
        for item in packet.possessions
        if item.key
    }

    if locked_entity_keys:
        for sentence in _SENTENCE_SPLIT_RE.split(
            str(
                draft
                or ""
            ).strip()
        ):
            draft_temporal = _temporal_relation_categories(
                sentence
            )

            novel_temporal = (
                draft_temporal
                - source_temporal_categories
            )

            if not novel_temporal:
                continue

            sentence_key = canonical_entity_key(
                sentence
            )

            mentioned_locked = sorted(
                key
                for key in locked_entity_keys
                if re.search(
                    r"\b" + re.escape(key) + r"\b",
                    sentence_key,
                    flags=re.IGNORECASE,
                )
            )

            if not mentioned_locked:
                continue

            violations.append(
                "unsupported Core-grounded claim: source-lock temporal relation invention: "
                f"draft attached {sorted(novel_temporal)!r} to locked "
                f"entity/entities {mentioned_locked!r} without user-authored support"
            )

    return list(
        dict.fromkeys(
            violations
        )
    )


# --------------------------------------------------
# Source-lock retry guidance
# --------------------------------------------------


def build_source_lock_retry_instruction(
    user_input: str,
    violations: Sequence[str],
    conversation=None,
    intent: Optional[str] = None,
    max_prior_user_messages: int = 4,
) -> Optional[str]:
    """
    Turn structural rejection details into a compact retry instruction.

    Phase 6.8.9 kept the original source-lock anchors in every retry, but a
    social micro-act retry did not explicitly tell Qwen WHAT structural rule
    the previous draft had broken. That allowed a later attempt to reintroduce
    the same substituted entity.

    This helper is intentionally generic: it names the already-extracted locked
    entities/relations and the actual violation text. It never contains
    product-, topic-, or verb-specific repair rules.
    """

    relevant = [
        str(item).strip()
        for item in (violations or [])
        if "source-lock" in str(item).lower()
    ]

    if not relevant:
        return None

    packet = build_source_lock_packet(
        user_input=user_input,
        conversation=conversation,
        max_prior_user_messages=max_prior_user_messages,
    )

    lines = [
        "CORE SOURCE-LOCK RETRY:",
        "The previous draft changed user-authored structure. Rewrite from the locked anchors instead of inventing a replacement.",
    ]

    if packet.possessions:
        locked = []

        for item in packet.possessions:
            locked.append(
                f"{item.owner} -> {item.entity!r}"
            )

        lines.append(
            "Locked entities/possessions: "
            + ", ".join(locked)
        )

    if packet.relations:
        locked_relations = []

        for item in packet.relations:
            locked_relations.append(
                f"{item.actor} --{item.action}--> {item.target}"
            )

        lines.append(
            "Locked directed relations: "
            + ", ".join(locked_relations)
        )

    lines.extend([
        "Previous structural violations:",
        *("- " + item for item in relevant[:6]),
        "Repair rules:",
        "- Keep the exact locked concrete entity when referring to the supplied fact; do not swap in a plausible related object.",
        "- Preserve actor -> target direction, including embedded clauses such as 'me to ... your ...'.",
        "- Do not compensate for a rejected factual embellishment by adding a different unsupported fact.",
    ])

    if str(intent or "").strip().lower() in {
        "share_context",
        "casual_conversation",
    }:
        lines.append(
            "- This is a social reaction, not an advice request: react without telling Oliver what he should do."
        )

    return "\n".join(lines)


# --------------------------------------------------
# Factual-answer truth-first integrity
# --------------------------------------------------


FACTUAL_RETRACTION_PATTERNS = (
    r"\bjust\s+kidding\b",
    r"\bkidding\b",
    r"\bj\s*/?\s*k\b",
    r"\bsike\b",
    r"\bsyke\b",
    r"\bpsych\b",
)


def find_factual_answer_integrity_violations(
    draft: str,
) -> List[str]:
    """
    Enforce truth-first ordering for ordinary factual answers.

    This does NOT fact-check the answer. Core simply rejects a response that
    explicitly marks an earlier answer as a deliberate fake/joke and then
    retracts it. In a future voice interface Oliver may interrupt Mairon after
    the first sentence, so knowingly-wrong-first humour is not a safe factual
    protocol even when the correction arrives immediately afterwards.

    Personality is still allowed AFTER the answer; it just cannot depend on
    presenting a disposable factual answer first.
    """

    value = str(
        draft
        or ""
    ).strip()

    if not value:
        return []

    for pattern in FACTUAL_RETRACTION_PATTERNS:
        match = re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        prefix = value[:match.start()].strip(
            " \t\r\n([{-—–"
        )

        # A retraction marker at the very beginning is just banter. We care
        # specifically about an earlier substantive answer being presented
        # before the marker.
        if not prefix:
            continue

        if re.search(
            r"[A-Za-z0-9]",
            prefix,
        ):
            return [
                "factual-focus answer-integrity violation: draft presented an answer before explicitly retracting it as a joke"
            ]

    return []


# --------------------------------------------------
# Factual-answer process/meta commentary guard
# --------------------------------------------------


FACTUAL_PROCESS_COMMENTARY_PATTERNS = (
    r"\bI\s+(?:know|remember|think|believe)\b.{0,80}\b(?:answer|fact|this|that|one)\b",
    r"\bI\s+(?:can|could)\s+answer\b",
    r"\bI\s+(?:don't|do not|didn't|did not|won't|will not)\s+(?:need|have)\b.{0,80}\b(?:check|look|search|verify|consult)\b",
    r"\bwithout\s+(?:needing|having)\s+to\s+(?:check|look|search|verify|consult)\b",
    r"\bwithout\s+(?:checking|looking|searching|verifying|consulting)\b",
    r"\bI\s+(?:checked|looked up|searched|verified|consulted)\b.{0,80}\b(?:answer|fact|map|source|web|internet)\b",
    r"\b(?:hard[- ]coded|training data|model memory|system fact|correct answer)\b",
    r"\bI(?:'ll| will)\s+(?:stick|go)\s+with\b.{0,40}\b(?:answer|that|this)\b",
)


def find_factual_process_commentary_violations(
    draft: str,
) -> List[str]:
    """
    Block model self-commentary about HOW it produced a straightforward factual
    answer. The factual lane may use local-model world knowledge, but prose such
    as "I know this without checking a map" is neither the requested fact nor
    authoritative Core state.

    This guard is intentionally about epistemic/process commentary, not ordinary
    personality about the subject itself.
    """

    value = _normalise_apostrophes(
        draft
    )

    for pattern in FACTUAL_PROCESS_COMMENTARY_PATTERNS:
        if re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        ):
            return [
                "factual-focus answer-generation/process commentary is not allowed"
            ]

    return []


# --------------------------------------------------
# Factual-answer personal/history tail guard
# --------------------------------------------------


def _history_candidate_sentence(
    sentence: str,
) -> bool:
    value = _normalise_apostrophes(
        sentence
    )

    first_person_history = re.search(
        r"\bI\s+(?:have|had|was|were|did|didn't|got|went|read|saw|heard|"
        r"visited|checked|researched|looked|forgot|remembered|learned|found)\b",
        value,
        flags=re.IGNORECASE,
    )

    first_person_contracted = re.search(
        r"\bI(?:'ve|'d)\b",
        value,
        flags=re.IGNORECASE,
    )

    second_person_history = re.search(
        r"\byou\s+(?:have|had|were|did|got|went|read|saw|heard|visited|"
        r"checked|forgot|remembered|once|previously)\b",
        value,
        flags=re.IGNORECASE,
    )

    second_person_contracted = re.search(
        r"\byou(?:'ve|'d)\b",
        value,
        flags=re.IGNORECASE,
    )

    callback_marker = (
        re.search(
            r"\b(?:again|this time|last time|previously|earlier)\b",
            value,
            flags=re.IGNORECASE,
        )
        and re.search(
            r"\b(?:I|you|me|my|your)\b",
            value,
            flags=re.IGNORECASE,
        )
    )

    return bool(
        first_person_history
        or first_person_contracted
        or second_person_history
        or second_person_contracted
        or callback_marker
    )


def _distinctive_history_tokens(
    text: str,
) -> set:
    return {
        token.lower()
        for token in re.findall(
            r"[A-Za-z0-9']+",
            _normalise_apostrophes(
                text
            ),
        )
        if len(
            token
        ) >= 4
        and token.lower() not in HISTORY_STOPWORDS
    }


def _history_candidate_has_user_support(
    sentence: str,
    source_texts: Sequence[str],
) -> bool:
    sentence_norm = canonical_entity_key(
        sentence
    )

    for source in source_texts:
        source_norm = canonical_entity_key(
            source
        )

        if (
            sentence_norm
            and sentence_norm in source_norm
        ):
            return True

    candidate_tokens = _distinctive_history_tokens(
        sentence
    )

    if not candidate_tokens:
        return False

    source_tokens = set()

    for source in source_texts:
        source_tokens.update(
            _distinctive_history_tokens(
                source
            )
        )

    # Requiring two distinctive overlaps avoids an unrelated old mention of a
    # generic word such as "book" or "city" from authorising an invented event.
    return len(
        candidate_tokens
        & source_tokens
    ) >= 2


def find_factual_personal_history_violations(
    user_input: str,
    draft: str,
    conversation=None,
    max_prior_user_messages: int = 4,
) -> List[str]:
    source_texts = list(
        recent_user_texts(
            conversation=conversation,
            max_messages=max_prior_user_messages,
        )
    )

    current = str(
        user_input
        or ""
    ).strip()

    if current:
        source_texts.append(
            current
        )

    violations = []

    for sentence in _SENTENCE_SPLIT_RE.split(
        str(
            draft
            or ""
        ).strip()
    ):
        sentence = sentence.strip()

        if not sentence:
            continue

        if not _history_candidate_sentence(
            sentence
        ):
            continue

        if _history_candidate_has_user_support(
            sentence=sentence,
            source_texts=source_texts,
        ):
            continue

        violations.append(
            "factual-focus source-fidelity violation: unsupported personal/history tail: "
            + sentence
        )

    return violations


def repair_factual_personal_history_tail(
    user_input: str,
    draft: str,
    conversation=None,
    max_prior_user_messages: int = 4,
) -> Tuple[str, List[str]]:
    """
    Remove CLEAR sentence-separated personal/history decoration from a factual
    answer while preserving the factual answer itself.

    We only delete unsupported history sentences AFTER at least one earlier
    sentence remains. If the first sentence itself mixes the factual answer and
    unsupported history, leave it intact and let verification/retry handle it.
    """

    original = str(
        draft
        or ""
    ).strip()

    if not original:
        return (
            original,
            [],
        )

    sentences = [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_RE.split(
            original
        )
        if sentence.strip()
    ]

    if len(
        sentences
    ) <= 1:
        return (
            original,
            [],
        )

    source_texts = list(
        recent_user_texts(
            conversation=conversation,
            max_messages=max_prior_user_messages,
        )
    )

    current = str(
        user_input
        or ""
    ).strip()

    if current:
        source_texts.append(
            current
        )

    kept = []
    removed = []

    for index, sentence in enumerate(
        sentences
    ):
        unsupported_history = (
            _history_candidate_sentence(
                sentence
            )
            and not _history_candidate_has_user_support(
                sentence=sentence,
                source_texts=source_texts,
            )
        )

        if (
            index > 0
            and kept
            and unsupported_history
        ):
            removed.append(
                sentence
            )
            continue

        kept.append(
            sentence
        )

    repaired = " ".join(
        kept
    ).strip()

    return (
        repaired
        or original,
        removed,
    )
