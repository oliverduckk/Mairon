import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# --------------------------------------------------
# Paths / configuration
# --------------------------------------------------

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

PRIVATE_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "private"
)

SPOILER_PROFILE_PATH = (
    PRIVATE_DATA_DIR
    / "spoiler_profiles.json"
)

MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)


# --------------------------------------------------
# Detection policy
# --------------------------------------------------

MEDIA_WORDS = [
    "anime",
    "manga",
    "animanga",
    "light novel",
    "light novels",
    "web novel",
    "web novels",
    "novel",
    "novels",
    "book",
    "books",
    "series",
    "show",
    "movie",
    "film",
    "game",
    "chapter",
    "episode",
    "arc",
    "volume",
    "season",
    "character",
    "characters",
]

HIGH_SPOILER_RISK_PATTERNS = [
    r"\bdoes .{1,80}\bdie\b",
    r"\bis .{1,80}\bdead\b",
    r"\bwho dies\b",
    r"\bwho killed\b",
    r"\bwho is the (?:real |actual )?(?:villain|traitor|killer)\b",
    r"\bwhat happens\b",
    r"\bwhat happened\b",
    r"\bwhat happens to\b",
    r"\bwhy did .{1,100}\b(?:die|leave|betray|kill|fight|become)\b",
    r"\bwhen does .{1,100}\b(?:die|appear|return|leave|fight|become)\b",
    r"\bdoes .{1,100}\b(?:become|join|leave|betray|return|win|lose)\b",
    r"\bending\b",
    r"\bfinale\b",
    r"\bfinal arc\b",
    r"\bfinal chapter\b",
    r"\bidentity\b",
    r"\bsecret identity\b",
    r"\bbig reveal\b",
    r"\breveal\b",
    r"\btwist\b",
    r"\btraitor\b",
    r"\bspoiler\b",
]

RELEASE_SENSITIVE_PATTERNS = [
    r"\blatest\b",
    r"\bnew chapter\b",
    r"\bnew episode\b",
    r"\bnew volume\b",
    r"\bnewest\b",
    r"\bcurrent chapter\b",
    r"\bcurrent episode\b",
    r"\bthis week(?:'s)? chapter\b",
    r"\bthis week(?:'s)? episode\b",
    r"\bjust released\b",
    r"\bdropped today\b",
    r"\breleased today\b",
]

PROGRESS_STATEMENT_PATTERNS = [
    r"\bi(?:'m| am) (?:only )?up to\b",
    r"\bi(?:'ve| have) (?:only )?(?:read|watched|finished|reached)\b",
    r"\bi(?:'m| am) caught up\b",
    r"\bi(?:'m| am) up to date\b",
    r"\bi(?:'m| am) anime only\b",
    r"\bi(?:'m| am) manga only\b",
    r"\bi(?:'m| am) (?:a )?light novel reader\b",
    r"\bi(?:'m| am) (?:a )?web novel reader\b",
    r"\bi read the latest chapter\b",
    r"\bi watched the latest episode\b",
    r"\bi(?:'ve| have) read the latest chapter\b",
    r"\bi(?:'ve| have) watched the latest episode\b",
]

MEDIUM_PATTERNS = [
    (
        "anime",
        [
            r"\banime[- ]only\b",
            r"\banime only\b",
            r"\bwatch(?:ing|ed)? the anime\b",
            r"\bup to date (?:on|with) the anime\b",
        ],
    ),
    (
        "manga",
        [
            r"\bmanga[- ]only\b",
            r"\bmanga only\b",
            r"\bread(?:ing)? the manga\b",
            r"\bup to date (?:on|with) the manga\b",
            r"\bcaught up (?:on|with) the manga\b",
            r"\blatest chapter\b",
        ],
    ),
    (
        "light_novel",
        [
            r"\blight novel\b",
            r"\blight novels\b",
            r"\bln reader\b",
        ],
    ),
    (
        "web_novel",
        [
            r"\bweb novel\b",
            r"\bweb novels\b",
            r"\bwn reader\b",
        ],
    ),
]

PROGRESS_VALUE_PATTERNS = [
    (
        "arc",
        r"\barc\s+([0-9]+(?:\.[0-9]+)?)\b",
    ),
    (
        "chapter",
        r"\bchapter\s+([0-9]+(?:\.[0-9]+)?)\b",
    ),
    (
        "episode",
        r"\bepisode\s+([0-9]+(?:\.[0-9]+)?)\b",
    ),
    (
        "volume",
        r"\bvolume\s+([0-9]+(?:\.[0-9]+)?)\b",
    ),
    (
        "season",
        r"\bseason\s+([0-9]+(?:\.[0-9]+)?)\b",
    ),
]

TITLE_STOP_PHRASES = {
    "the anime",
    "the manga",
    "the light novel",
    "the light novels",
    "the web novel",
    "the web novels",
    "anime",
    "manga",
    "light novel",
    "light novels",
    "web novel",
    "web novels",
    "this",
    "that",
    "it",
    "the series",
    "series",
}


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _now():
    return datetime.now(
        LOCAL_TIMEZONE
    )


def _normalise_text(text):
    value = str(
        text or ""
    ).strip()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


def _normalise_title_key(title):
    value = _normalise_text(
        title
    ).lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def _clean_title_candidate(value):
    title = _normalise_text(
        value
    )

    title = re.sub(
        r"^[\s,.:;!?-]+|[\s,.:;!?-]+$",
        "",
        title,
    )

    title = re.sub(
        r"^(?:the\s+)",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        (
            r"\s+(?:manga|anime|light novels?|web novels?|novels?|"
            r"series|show|characters?|chapter|episode|arc|volume|season)"
            r"\s*$"
        ),
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = title.strip()

    if not title:
        return None

    if (
        title.lower()
        in TITLE_STOP_PHRASES
    ):
        return None

    if len(title) < 2:
        return None

    if len(title) > 80:
        return None

    # Avoid obviously conversational fragments being treated as titles.
    bad_starts = (
        "what ",
        "why ",
        "how ",
        "who ",
        "does ",
        "did ",
        "do ",
        "is ",
        "are ",
        "can ",
        "could ",
        "would ",
        "should ",
        "i ",
        "im ",
        "i'm ",
        "you ",
        "your ",
        "my ",
    )

    if title.lower().startswith(
        bad_starts
    ):
        return None

    return title


def _default_state():
    return {
        "version": 1,
        "profiles": {},
    }


def _ensure_private_dir():
    PRIVATE_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def _load_state():
    _ensure_private_dir()

    if not SPOILER_PROFILE_PATH.exists():
        return _default_state()

    try:
        with SPOILER_PROFILE_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:
            value = json.load(
                handle
            )
    except Exception:
        return _default_state()

    if not isinstance(
        value,
        dict,
    ):
        return _default_state()

    value.setdefault(
        "version",
        1,
    )

    value.setdefault(
        "profiles",
        {},
    )

    return value


def _save_state(state):
    _ensure_private_dir()

    temp_path = SPOILER_PROFILE_PATH.with_suffix(
        ".json.tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            state,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temp_path,
        SPOILER_PROFILE_PATH,
    )


def _matches_any(
    text,
    patterns,
):
    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


# --------------------------------------------------
# Topic extraction
# --------------------------------------------------

def _known_profile_title_in_text(
    text,
    state,
):
    normalised = _normalise_title_key(
        text
    )

    candidates = []

    for key, profile in state.get(
        "profiles",
        {}
    ).items():
        aliases = {
            key,
            _normalise_title_key(
                profile.get(
                    "title",
                    "",
                )
            ),
        }

        aliases.update(
            _normalise_title_key(
                alias
            )
            for alias in profile.get(
                "aliases",
                []
            )
        )

        aliases = {
            alias
            for alias in aliases
            if alias
        }

        for alias in aliases:
            if re.search(
                r"(?<![a-z0-9])"
                + re.escape(
                    alias
                )
                + r"(?![a-z0-9])",
                normalised,
            ):
                candidates.append(
                    (
                        len(alias),
                        profile.get(
                            "title"
                        )
                        or key,
                    )
                )

    if not candidates:
        return None

    candidates.sort(
        reverse=True
    )

    return candidates[
        0
    ][1]


def _extract_title_from_progress_statement(
    text,
):
    patterns = [
        # "caught up with the One Piece manga"
        (
            r"\b(?:caught up|up to date)\s+(?:with|on)\s+(?:the\s+)?"
            r"(.+?)\s+(?:manga|anime|light novels?|web novels?)\b"
        ),
        # "I'm anime only for Re Zero"
        (
            r"\b(?:anime[- ]only|manga[- ]only|light novel reader|"
            r"web novel reader)\s+(?:for|with|on)\s+(.+?)(?:[,.!?]|$)"
        ),
        # "For Re Zero I'm anime only"
        (
            r"\bfor\s+(.+?)\s+i(?:'m| am)\s+(?:anime[- ]only|"
            r"manga[- ]only|a light novel reader|a web novel reader)\b"
        ),
        # "I'm up to arc 6 in Re Zero"
        (
            r"\b(?:up to|finished|reached|read|watched)\s+"
            r"(?:arc|chapter|episode|volume|season)\s+"
            r"[0-9]+(?:\.[0-9]+)?\s+(?:in|of|for)\s+(.+?)(?:[,.!?]|$)"
        ),
        # "I've read chapter 1172 of One Piece"
        (
            r"\b(?:read|watched|finished)\s+"
            r"(?:arc|chapter|episode|volume|season)\s+"
            r"[0-9]+(?:\.[0-9]+)?\s+(?:in|of|for)\s+(.+?)(?:[,.!?]|$)"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            candidate = _clean_title_candidate(
                match.group(
                    1
                )
            )

            if candidate:
                return candidate

    return None


def _extract_title_from_discussion(
    text,
):
    patterns = [
        # Opinion wording must be explicit. A generic phrase such as
        # "changed about when I cleaned it" is NOT a media-title signal.
        r"\bwhat\s+do\s+you\s+think\s+(?:about|of)\s+(.+?)(?:[?.!,]|$)",
        r"\bwhat(?:'s| is)\s+your\s+(?:opinion|take)\s+(?:on|about|of)\s+(.+?)(?:[?.!,]|$)",
        r"\bhow\s+do\s+you\s+feel\s+about\s+(.+?)(?:[?.!,]|$)",
        # "top 3 One Piece characters"
        r"\btop\s+\d+\s+(.+?)\s+characters?\b",
        # "favourite One Piece characters"
        r"\bfavou?rite\s+(.+?)\s+characters?\b",
        # "what happens in Re Zero"
        r"\b(?:happens|happened)\s+(?:in|to)\s+(.+?)(?:[?.!,]|$)",
        # "Re Zero anime"
        r"\b([A-Z][A-Za-z0-9:'\- ]{1,60}?)\s+(?:anime|manga|series)\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=0,
        )

        if match:
            candidate = _clean_title_candidate(
                match.group(
                    1
                )
            )

            if candidate:
                return candidate

    return None


def _conversation_texts(
    conversation,
):
    result = []

    if not conversation:
        return result

    for message in conversation[
        -10:
    ]:
        if isinstance(
            message,
            dict,
        ):
            role = message.get(
                "role"
            )

            content = message.get(
                "content"
            ) or ""
        else:
            role = getattr(
                message,
                "role",
                None,
            )

            content = getattr(
                message,
                "content",
                "",
            ) or ""

        if (
            role in (
                "user",
                "assistant",
            )
            and content
        ):
            result.append(
                content
            )

    return result


def resolve_media_title(
    user_input,
    conversation=None,
):
    """
    Resolve a media/franchise title conservatively.

    Priority:
    1. a known stored profile explicitly named now;
    2. explicit title inside a progress statement;
    3. a clear title-shaped phrase in the current question;
    4. recent conversational context.

    If Core cannot resolve a title confidently, it returns None rather
    than inventing one.
    """

    state = _load_state()

    known = _known_profile_title_in_text(
        user_input,
        state,
    )

    if known:
        return known

    progress_title = (
        _extract_title_from_progress_statement(
            user_input
        )
    )

    if progress_title:
        return progress_title

    discussion_title = (
        _extract_title_from_discussion(
            user_input
        )
    )

    if discussion_title:
        return discussion_title

    for previous in reversed(
        _conversation_texts(
            conversation
        )
    ):
        known = _known_profile_title_in_text(
            previous,
            state,
        )

        if known:
            return known

        candidate = (
            _extract_title_from_progress_statement(
                previous
            )
            or _extract_title_from_discussion(
                previous
            )
        )

        if candidate:
            return candidate

    return None


# --------------------------------------------------
# Progress extraction / persistence
# --------------------------------------------------

def _detect_medium(
    text,
):
    lowered = text.lower()

    # "anime only and not light novel" should resolve as anime, not LN.
    if re.search(
        r"\banime[- ]only\b",
        lowered,
    ):
        return "anime"

    if re.search(
        r"\bmanga[- ]only\b",
        lowered,
    ):
        return "manga"

    for medium, patterns in MEDIUM_PATTERNS:
        if _matches_any(
            lowered,
            patterns,
        ):
            return medium

    return None


def _detect_progress_value(
    text,
):
    for progress_type, pattern in PROGRESS_VALUE_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            raw_value = match.group(
                1
            )

            if "." in raw_value:
                value = float(
                    raw_value
                )
            else:
                value = int(
                    raw_value
                )

            return (
                progress_type,
                value,
            )

    return (
        None,
        None,
    )


def _detect_caught_up(
    text,
):
    return _matches_any(
        text,
        [
            r"\bi(?:'m| am) caught up\b",
            r"\bi(?:'m| am) up to date\b",
            r"\bi read the latest chapter\b",
            r"\bi(?:'ve| have) read the latest chapter\b",
            r"\bi watched the latest episode\b",
            r"\bi(?:'ve| have) watched the latest episode\b",
        ],
    )


def _is_explicit_progress_statement(
    text,
):
    return _matches_any(
        text,
        PROGRESS_STATEMENT_PATTERNS,
    )


def register_spoiler_progress_from_message(
    user_input,
    conversation=None,
):
    """
    Persist spoiler progress only when Oliver explicitly states it.

    Nothing is inferred from mere discussion or from Mairon's own text.
    """

    text = _normalise_text(
        user_input
    )

    if not _is_explicit_progress_statement(
        text
    ):
        return None

    title = resolve_media_title(
        user_input=text,
        conversation=conversation,
    )

    if not title:
        # Better to fail to save than attach progress to the wrong series.
        return None

    medium = _detect_medium(
        text
    )

    (
        progress_type,
        progress_value,
    ) = _detect_progress_value(
        text
    )

    caught_up = _detect_caught_up(
        text
    )

    if (
        not medium
        and not progress_type
        and not caught_up
    ):
        return None

    state = _load_state()

    key = _normalise_title_key(
        title
    )

    now = _now()

    profile = state[
        "profiles"
    ].get(
        key,
        {
            "title": title,
            "aliases": [
                title
            ],
            "medium": None,
            "progress_type": None,
            "progress_value": None,
            "caught_up": False,
            "caught_up_confirmed_at": None,
            "last_updated": None,
            "source_excerpt": None,
        }
    )

    profile[
        "title"
    ] = title

    aliases = {
        str(
            alias
        )
        for alias in profile.get(
            "aliases",
            []
        )
        if alias
    }

    aliases.add(
        title
    )

    profile[
        "aliases"
    ] = sorted(
        aliases
    )

    if medium:
        profile[
            "medium"
        ] = medium

    if progress_type:
        profile[
            "progress_type"
        ] = progress_type

        profile[
            "progress_value"
        ] = progress_value

        # A numerical ceiling is stronger than a vague old "caught up".
        # Do not erase caught_up, but future release-sensitive questions
        # still require Core to consider when it was confirmed.

    if caught_up:
        profile[
            "caught_up"
        ] = True

        profile[
            "caught_up_confirmed_at"
        ] = now.isoformat()

    profile[
        "last_updated"
    ] = now.isoformat()

    profile[
        "source_excerpt"
    ] = text[
        :300
    ]

    state[
        "profiles"
    ][
        key
    ] = profile

    _save_state(
        state
    )

    return dict(
        profile
    )


def get_spoiler_profile(
    title,
):
    if not title:
        return None

    state = _load_state()

    key = _normalise_title_key(
        title
    )

    direct = state[
        "profiles"
    ].get(
        key
    )

    if direct:
        return dict(
            direct
        )

    # Alias fallback.
    for profile in state[
        "profiles"
    ].values():
        aliases = [
            _normalise_title_key(
                alias
            )
            for alias in profile.get(
                "aliases",
                []
            )
        ]

        if key in aliases:
            return dict(
                profile
            )

    return None


# --------------------------------------------------
# Pending spoiler-question continuity
# --------------------------------------------------

def _conversation_messages(
    conversation,
):
    result = []

    if not conversation:
        return result

    for message in conversation[
        -12:
    ]:
        if isinstance(
            message,
            dict,
        ):
            role = message.get(
                "role"
            )

            content = message.get(
                "content"
            ) or ""
        else:
            role = getattr(
                message,
                "role",
                None,
            )

            content = getattr(
                message,
                "content",
                "",
            ) or ""

        if (
            role in (
                "user",
                "assistant",
            )
            and content
        ):
            result.append({
                "role": role,
                "content": content,
            })

    return result


def _last_assistant_message(
    conversation,
):
    for message in reversed(
        _conversation_messages(
            conversation
        )
    ):
        if message[
            "role"
        ] == "assistant":
            return message[
                "content"
            ]

    return None


def _assistant_was_asking_progress(
    conversation,
):
    last_assistant = (
        _last_assistant_message(
            conversation
        )
    )

    if not last_assistant:
        return False

    text = last_assistant.lower()

    progress_terms = [
        "where are you up to",
        "how far are you",
        "caught up",
        "anime-only",
        "anime only",
        "manga",
        "light novel",
        "web novel",
        "what episode",
        "which episode",
        "what chapter",
        "which chapter",
        "what arc",
        "which arc",
        "latest episodes",
        "latest episode",
        "latest chapter",
        "read it",
        "watched it",
    ]

    return (
        "?" in last_assistant
        and any(
            term in text
            for term in progress_terms
        )
    )


def _find_pending_spoiler_question(
    conversation,
):
    """
    Recover the real user question that caused Mairon to ask for spoiler
    progress.

    We only do this when the immediately previous Mairon message itself
    looks like a progress question. That prevents an unrelated old
    spoiler question from being revived merely because Oliver later
    volunteers a media preference.
    """

    if not _assistant_was_asking_progress(
        conversation
    ):
        return None

    for message in reversed(
        _conversation_messages(
            conversation
        )
    ):
        if message[
            "role"
        ] != "user":
            continue

        content = message[
            "content"
        ]

        if is_high_spoiler_risk(
            content
        ):
            return content

    return None


# --------------------------------------------------
# Risk / guard state
# --------------------------------------------------

def is_media_like_turn(
    user_input,
):
    """
    Detect explicit media vocabulary using lexical boundaries.

    Substring matching is intentionally forbidden here. The weather system
    already taught us what happens when "trains" secretly contains "rain".
    """

    text = str(
        user_input
        or ""
    ).lower()

    for word in MEDIA_WORDS:
        if re.search(
            r"(?<![a-z0-9])"
            + re.escape(
                word.lower()
            )
            + r"(?![a-z0-9])",
            text,
        ):
            return True

    return False


def empty_spoiler_context():
    """
    No-media sentinel used when the current turn has not earned access to the
    spoiler/media subsystem.
    """

    return {
        "domain_active": False,
        "title": None,
        "profile": None,
        "high_risk": False,
        "release_sensitive": False,
        "must_ask_progress": False,
        "must_complete_progress": False,
        "must_confirm_latest": False,
        "progress_updated": False,
        "pending_question": None,
        "progress_only_update": False,
    }


def _looks_like_media_follow_up(
    user_input,
):
    """
    Return True only for genuinely referential media follow-ups.

    Older logic treated almost any question beginning with "what", "why",
    "how", "is", etc. as a follow-up. That let a new-topic question such as
    "what are your top 3 Hollywood actors?" inherit One Piece from the prior
    turn and wake the spoiler/research subsystem.

    A follow-up now needs a deictic referent (it/that/he/she/they/etc.) or a
    question whose grammatical target is one of those referents.
    """

    text = _normalise_text(
        user_input
    )

    if not text:
        return False

    direct_deictic = re.search(
        r"^(?:and\s+|but\s+)?(?:what\s+about\s+)?"
        r"(?:it|that|this|he|him|she|her|they|them|those|these)\b",
        text,
        flags=re.IGNORECASE,
    )

    if direct_deictic:
        return True

    question_with_deictic_target = re.search(
        r"^(?:and\s+|but\s+)?"
        r"(?:who|what|why|how|when|where)\b"
        r".{0,40}?\b"
        r"(?:it|that|this|he|him|she|her|they|them|those|these)\b",
        text,
        flags=re.IGNORECASE,
    )

    return bool(
        question_with_deictic_target
    )


def should_activate_media_domain(
    user_input,
    conversation=None,
):
    """
    Decide whether media/spoiler machinery is allowed to inspect this turn.

    Strong current-turn evidence wins:
    - explicit media vocabulary;
    - an explicitly named title already known to the spoiler-profile store;
    - an explicit media-progress statement.

    A referential follow-up may inherit media domain only from very recent
    conversation that itself contains a strong media signal.

    Generic phrases such as "about when I cleaned it" never activate media.
    """

    current = str(
        user_input
        or ""
    ).strip()

    if not current:
        return False

    if is_media_like_turn(
        current
    ):
        return True

    state = _load_state()

    if _known_profile_title_in_text(
        current,
        state,
    ):
        return True

    if _is_explicit_progress_statement(
        _normalise_text(
            current
        )
    ):
        return True

    if not (
        conversation
        and _looks_like_media_follow_up(
            current
        )
    ):
        return False

    for previous in reversed(
        _conversation_texts(
            conversation
        )[-4:]
    ):
        if is_media_like_turn(
            previous
        ):
            return True

        if _known_profile_title_in_text(
            previous,
            state,
        ):
            return True

    return False


def is_high_spoiler_risk(
    user_input,
):
    return _matches_any(
        user_input,
        HIGH_SPOILER_RISK_PATTERNS,
    )


def is_release_sensitive(
    user_input,
):
    return _matches_any(
        user_input,
        RELEASE_SENSITIVE_PATTERNS,
    )


def _profile_has_useful_ceiling(
    profile,
):
    if not profile:
        return False

    # Knowing only the medium is NOT enough. "Anime-only" does not tell
    # Core whether Oliver is on episode 3 or fully caught up.
    return bool(
        (
            profile.get(
                "progress_type"
            )
            and profile.get(
                "progress_value"
            ) is not None
        )
        or profile.get(
            "caught_up"
        )
    )


def _caught_up_confirmed_today(
    profile,
):
    value = (
        profile
        or {}
    ).get(
        "caught_up_confirmed_at"
    )

    if not value:
        return False

    try:
        confirmed = datetime.fromisoformat(
            value
        )
    except Exception:
        return False

    return (
        confirmed.astimezone(
            LOCAL_TIMEZONE
        ).date()
        == _now().date()
    )


def prepare_spoiler_context(
    user_input,
    conversation=None,
):
    """
    Build spoiler state only after the current turn has been positively
    identified as media-related.

    Non-media conversation returns immediately without title extraction,
    progress persistence, or spoiler-state inference.
    """

    if not should_activate_media_domain(
        user_input=user_input,
        conversation=conversation,
    ):
        return empty_spoiler_context()

    updated_profile = (
        register_spoiler_progress_from_message(
            user_input=user_input,
            conversation=conversation,
        )
    )

    title = resolve_media_title(
        user_input=user_input,
        conversation=conversation,
    )

    profile = (
        updated_profile
        or get_spoiler_profile(
            title
        )
    )

    high_risk = is_high_spoiler_risk(
        user_input
    )

    release_sensitive = is_release_sensitive(
        user_input
    )

    # If the title cannot be resolved but the question is overtly
    # spoiler-sensitive, Core should still instruct Mairon to ask what
    # Oliver is up to rather than gamble.
    must_ask_progress = (
        high_risk
        and not _profile_has_useful_ceiling(
            profile
        )
    )

    must_confirm_latest = (
        bool(
            profile
        )
        and release_sensitive
        and bool(
            profile.get(
                "caught_up"
            )
        )
        and not _caught_up_confirmed_today(
            profile
        )
    )

    # "Anime-only" / "manga-only" tells Core WHICH medium is safe, but
    # not HOW FAR Oliver has reached. If Oliver has just answered a
    # spoiler check with medium-only information, immediately complete
    # the profile instead of pretending that a hard ceiling exists.
    must_complete_progress = (
        updated_profile is not None
        and bool(
            profile
        )
        and bool(
            profile.get(
                "medium"
            )
        )
        and not _profile_has_useful_ceiling(
            profile
        )
    )

    pending_question = None

    if updated_profile is not None:
        pending_question = (
            _find_pending_spoiler_question(
                conversation
            )
        )

    progress_only_update = (
        updated_profile is not None
        and pending_question is None
        and not must_complete_progress
        and not must_confirm_latest
    )

    return {
        "domain_active": True,
        "title": title,
        "profile": profile,
        "high_risk": high_risk,
        "release_sensitive": release_sensitive,
        "must_ask_progress": must_ask_progress,
        "must_complete_progress": must_complete_progress,
        "must_confirm_latest": must_confirm_latest,
        "progress_updated": updated_profile is not None,
        "pending_question": pending_question,
        "progress_only_update": progress_only_update,
    }


# --------------------------------------------------
# Deterministic Core spoiler-control responses
# --------------------------------------------------

def _medium_display(
    medium,
):
    mapping = {
        "anime": "anime",
        "manga": "manga",
        "light_novel": "light novels",
        "web_novel": "web novel",
    }

    return mapping.get(
        medium,
        str(
            medium
            or "source"
        ).replace(
            "_",
            " ",
        ),
    )


def build_core_spoiler_control_response(
    spoiler_context,
):
    """
    Return a deterministic Core-owned response for spoiler-control turns.

    These turns are state/safety operations, not creative conversation.
    Returning them directly prevents the model from adding unsolicited
    lore while Oliver is merely establishing his spoiler ceiling.

    Return None once Core has enough information and there is a real
    pending/user question that should proceed normally.
    """

    title = (
        spoiler_context.get(
            "title"
        )
        or (
            spoiler_context.get(
                "profile"
            )
            or {}
        ).get(
            "title"
        )
    )

    profile = spoiler_context.get(
        "profile"
    ) or {}

    medium = profile.get(
        "medium"
    )

    medium_text = _medium_display(
        medium
    )

    if spoiler_context.get(
        "must_ask_progress"
    ):
        if title:
            return (
                f"Before I answer that, what are you up to in {title}? "
                "Tell me which version you're following and roughly where "
                "you've reached so I don't spoil anything."
            )

        return (
            "Before I answer that, what version are you following and "
            "roughly where are you up to? I'm not gambling with spoilers."
        )

    if spoiler_context.get(
        "must_complete_progress"
    ):
        if title and medium:
            return (
                f"Got it — {medium_text} only for {title}. Are you fully "
                f"caught up with the {medium_text}, or where are you up to?"
            )

        if medium:
            return (
                f"Got it — {medium_text} only. Are you fully caught up, "
                "or where are you up to?"
            )

        return (
            "Got it. I still need your actual progress before I answer "
            "anything spoiler-sensitive — where are you up to?"
        )

    if spoiler_context.get(
        "must_confirm_latest"
    ):
        if title:
            return (
                f"Before I touch the latest {title} material: have you "
                "read or watched the current newest release?"
            )

        return (
            "Before I touch the newest material: have you read or watched "
            "the current latest release?"
        )

    if spoiler_context.get(
        "progress_only_update"
    ):
        details = []

        if title:
            details.append(
                title
            )

        if medium:
            details.append(
                medium_text
            )

        progress_type = profile.get(
            "progress_type"
        )

        progress_value = profile.get(
            "progress_value"
        )

        if (
            progress_type
            and progress_value is not None
        ):
            details.append(
                f"up to {progress_type} {progress_value}"
            )

        elif profile.get(
            "caught_up"
        ):
            details.append(
                "caught up"
            )

        if details:
            return (
                "Got it — "
                + ", ".join(
                    details
                )
                + ". I'll keep anything beyond that spoiler ceiling off-limits."
            )

        return (
            "Got it. I've updated your spoiler progress."
        )

    return None


# --------------------------------------------------
# Prompt / validation
# --------------------------------------------------

def _format_profile(
    profile,
):
    if not profile:
        return "No stored spoiler profile."

    pieces = []

    medium = profile.get(
        "medium"
    )

    if medium:
        pieces.append(
            f"medium={medium}"
        )

    progress_type = profile.get(
        "progress_type"
    )

    progress_value = profile.get(
        "progress_value"
    )

    if (
        progress_type
        and progress_value is not None
    ):
        pieces.append(
            f"{progress_type}={progress_value}"
        )

    if profile.get(
        "caught_up"
    ):
        pieces.append(
            "caught_up=true"
        )

    confirmed = profile.get(
        "caught_up_confirmed_at"
    )

    if confirmed:
        pieces.append(
            f"caught_up_confirmed_at={confirmed}"
        )

    if not pieces:
        return "Stored profile exists but has no useful progress ceiling."

    return ", ".join(
        pieces
    )


def build_spoiler_guard_text(
    spoiler_context,
):
    """
    Model-facing spoiler policy.

    Core supplies the factual ceiling. The model never gets permission
    to infer that Oliver has seen later material merely because it would
    make the answer easier.
    """

    title = spoiler_context.get(
        "title"
    )

    profile = spoiler_context.get(
        "profile"
    )

    lines = [
        "CORE SPOILER POLICY:",
        "- Never reveal story information beyond Oliver's confirmed progress.",
        "- Never assume Oliver knows later material because it is old, popular, adapted elsewhere, discussed online, or present in your training data.",
        "- Do not reveal future character appearances, deaths, identities, relationships, powers, villains, twists, locations, outcomes, arc names, chapter titles, or other information that itself acts as a spoiler.",
        "- Do not use teasing or banter to leak a spoiler indirectly.",
        "- Jokingly threatening to spoil something is allowed only if the joke contains zero spoiler information.",
        "- Research may internally encounter later material, but the final conversational answer must remain inside Oliver's spoiler ceiling.",
    ]

    if title:
        lines.append(
            f"- Current resolved franchise/topic: {title}."
        )

    if profile:
        lines.append(
            "- Stored spoiler profile: "
            + _format_profile(
                profile
            )
            + "."
        )

        medium = profile.get(
            "medium"
        )

        progress_type = profile.get(
            "progress_type"
        )

        progress_value = profile.get(
            "progress_value"
        )

        if medium:
            lines.append(
                f"- Treat Oliver as a {medium} consumer for this topic unless he explicitly updates that."
            )

        if (
            progress_type
            and progress_value is not None
        ):
            lines.append(
                f"- Hard spoiler ceiling: do not reveal material beyond {progress_type} {progress_value}."
            )

    else:
        lines.append(
            "- No reliable stored spoiler ceiling is available for this topic."
        )

    if spoiler_context.get(
        "must_ask_progress"
    ):
        lines.extend([
            "",
            "MANDATORY PROGRESS CHECK:",
            "- Do NOT answer the spoiler-bearing substance of Oliver's question yet.",
            "- Ask one concise, natural question establishing what medium he follows and/or where he is up to.",
            "- The progress question itself must contain no spoiler hints.",
            "- Do not mention future arcs, chapters, characters, events, adaptations, or reveals while asking.",
            "- Once Oliver answers, Core can store that ceiling and the conversation may continue.",
        ])

    if spoiler_context.get(
        "must_complete_progress"
    ):
        lines.extend([
            "",
            "MANDATORY PROGRESS COMPLETION:",
            "- Oliver has just told you which medium he follows, but Core still does not know how far he has reached.",
            "- Acknowledge that medium briefly, then ask ONE concise question establishing his actual progress or whether he is fully caught up in that medium.",
            "- Do not answer any pending spoiler-bearing question yet.",
            "- Do not change topic. This message is part of the existing spoiler-safety conversation.",
            "- Do not mention later arcs, chapters, characters, events, adaptations, or reveals while asking.",
        ])

    if spoiler_context.get(
        "must_confirm_latest"
    ):
        lines.extend([
            "",
            "MANDATORY LATEST-RELEASE CHECK:",
            "- Oliver previously said he was caught up, but that confirmation is not from today.",
            "- The current question concerns the latest/newest/current release.",
            "- Do NOT assume he has consumed a release that may have appeared since that confirmation.",
            "- Ask whether he has read/watched the current latest release before discussing its content.",
            "- Do not reveal the release title or any content while asking.",
        ])

    if spoiler_context.get(
        "progress_only_update"
    ):
        lines.extend([
            "",
            "PROFILE UPDATE ONLY:",
            "- Oliver is only updating his spoiler/media progress here; there is no pending spoiler question to answer.",
            "- Acknowledge the update briefly and naturally.",
            "- Do NOT volunteer plot claims, character claims, arc commentary, release commentary, theories, or invented lore.",
            "- Do NOT manufacture a new topic merely to keep talking.",
            "- One short personality-consistent acknowledgement is enough.",
        ])

    pending_question = spoiler_context.get(
        "pending_question"
    )

    if pending_question:
        lines.extend([
            "",
            "PENDING SPOILER-SAFE QUESTION:",
            f"- Oliver's actual pending question is: {pending_question!r}",
            "- His current progress message is an answer to Mairon's safety check.",
            "- Once the spoiler ceiling is sufficient, return to THIS question. Do not switch franchises or topics.",
        ])

    if (
        not spoiler_context.get(
            "must_ask_progress"
        )
        and not spoiler_context.get(
            "must_complete_progress"
        )
        and not spoiler_context.get(
            "must_confirm_latest"
        )
        and not spoiler_context.get(
            "progress_only_update"
        )
    ):
        lines.extend([
            "",
            "- If the stored ceiling is sufficient, answer naturally inside it.",
            "- If Oliver's current message is a progress update answering a spoiler-safety question, continue the exact pending question supplied by Core.",
            "- If you realise while answering that a useful point depends on later material, omit that point rather than hinting at it.",
        ])

    return "\n".join(
        lines
    )


def find_spoiler_guard_violations(
    response_text,
    spoiler_context,
):
    """
    Deterministic checks for the cases where Core required a spoiler
    progress question before any substantive answer.

    This cannot prove that an arbitrary answer contains no spoiler, but
    it prevents the most dangerous policy failure: ignoring a mandatory
    progress check and answering anyway.
    """

    if not (
        spoiler_context.get(
            "must_ask_progress"
        )
        or spoiler_context.get(
            "must_complete_progress"
        )
        or spoiler_context.get(
            "must_confirm_latest"
        )
    ):
        return []

    text = _normalise_text(
        response_text
    ).lower()

    violations = []

    if "?" not in text:
        violations.append(
            "spoiler guard required a progress question"
        )

    progress_language = [
        "up to",
        "caught up",
        "anime",
        "manga",
        "light novel",
        "web novel",
        "chapter",
        "episode",
        "arc",
        "volume",
        "season",
        "latest",
        "read it",
        "watched it",
        "seen it",
    ]

    if not any(
        phrase in text
        for phrase in progress_language
    ):
        violations.append(
            "spoiler progress question did not establish a spoiler ceiling"
        )

    # Mandatory progress-check replies should be brief. Long answers are
    # more likely to have leaked substantive story content before asking.
    if len(text) > 420:
        violations.append(
            "spoiler progress check included too much substantive content"
        )

    return violations


# --------------------------------------------------
# Diagnostics
# --------------------------------------------------

def get_spoiler_profile_path():
    return str(
        SPOILER_PROFILE_PATH
    )
