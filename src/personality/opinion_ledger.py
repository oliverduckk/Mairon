import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from continuity.conversation_journal import (
    search_relevant_turns,
)


# --------------------------------------------------
# Paths
# --------------------------------------------------

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

PRIVATE_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "private"
)

OPINION_LEDGER_PATH = (
    PRIVATE_DATA_DIR
    / "mairon_opinions.json"
)

MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)


# --------------------------------------------------
# Subject classification
# --------------------------------------------------

TOP_RANKING_PATTERNS = [
    r"\btop\s+(\d+)\b.{0,80}\bcharacters?\b",
    r"\bfavou?rite\s+(\d+)\b.{0,80}\bcharacters?\b",
]

GENERAL_CHARACTER_PATTERNS = [
    r"\bfavou?rite\s+characters?\b",
    r"\bbest\s+characters?\b",
    r"\bcharacter\s+ranking\b",
]

OVERALL_OPINION_PATTERNS = [
    r"\bwhat do you think (?:of|about)\b",
    r"\bwhat's your opinion (?:of|on|about)\b",
    r"\bwhat is your opinion (?:of|on|about)\b",
]

REVISION_LANGUAGE = [
    r"\byou convinced me\b",
    r"\byou've convinced me\b",
    r"\byou have convinced me\b",
    r"\bchanged my mind\b",
    r"\bi change my mind\b",
    r"\bi'm changing\b",
    r"\bi am changing\b",
    r"\brevised (?:list|ranking|opinion)\b",
    r"\bupdated (?:list|ranking|opinion)\b",
    r"\breplace .{1,60} with\b",
    r"\bmoves? into my top\b",
]

EXPLICIT_REVISION_REQUESTS = [
    r"\bchange your mind\b",
    r"\bchange your ranking\b",
    r"\bupdate your ranking\b",
    r"\brevise your ranking\b",
    r"\bnew top\s+\d+\b",
    r"\bupdated top\s+\d+\b",
    r"\bfinal official top\s+\d+\b",
]

RANK_COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

GENERIC_RANKING_PATTERN = re.compile(
    r"\b(?:your|you)\s+(?:current\s+)?top\s+"
    r"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?P<domain>[a-z][a-z0-9'&\- ]{0,80})$",
    flags=re.IGNORECASE,
)

RANKING_SUBJECT_TRAILING_QUALIFIERS = (
    "of all time",
    "right now",
    "currently",
    "today",
    "overall",
)

# Linguistic aliases preserve existing ledger keys for common singular/plural
# variants without restricting which ranked subjects Mairon may persist.
RANKING_SUBJECT_ALIASES = {
    "mangas": "manga",
    "animes": "anime",
    "books": "book",
    "novels": "novel",
    "games": "game",
    "movies": "movie",
    "films": "movie",
    "film": "movie",
    "shows": "show",
    "artists": "artist",
    "albums": "album",
}


def _now():
    return datetime.now(
        LOCAL_TIMEZONE
    )


def _normalise(text):
    value = str(
        text or ""
    ).lower()

    value = re.sub(
        r"[^a-z0-9'\s]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _normalise_key(text):
    value = _normalise(
        text
    )

    return value.replace(
        " ",
        "_",
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


def _parse_rank_count(
    value,
):
    token = str(
        value
        or ""
    ).strip().lower()

    if token.isdigit():
        return int(
            token
        )

    return RANK_COUNT_WORDS.get(
        token
    )


def _normalise_ranking_subject_phrase(
    value,
):
    subject = _normalise(
        value
    )

    for qualifier in RANKING_SUBJECT_TRAILING_QUALIFIERS:
        suffix = (
            " "
            + qualifier
        )

        if subject.endswith(
            suffix
        ):
            subject = subject[
                :-len(
                    suffix
                )
            ].strip()
            break

    # Keep the category semantic and generic. The ledger does not need a
    # hard-coded vocabulary of manga/anime/actors/exercises/etc.; any concise
    # explicit ranked subject can become stable persona state.
    words = subject.split()

    if not words or len(words) > 8:
        return None

    subject = RANKING_SUBJECT_ALIASES.get(
        subject,
        subject,
    )

    return subject


def _classify_generic_category_ranking(
    text,
):
    match = GENERIC_RANKING_PATTERN.search(
        text
    )

    if not match:
        return None

    count = _parse_rank_count(
        match.group(
            "count"
        )
    )

    domain = _normalise_ranking_subject_phrase(
        match.group(
            "domain"
        )
    )

    if not count or not domain:
        return None

    domain_key = _normalise_key(
        domain
    )

    return {
        "key": (
            f"general::{domain_key}::top_{count}"
        ),
        "title": domain.title(),
        "domain": domain,
        "kind": "category_ranking",
        "count": count,
        "label": (
            f"Mairon top {count} {domain}"
        ),
    }


def classify_opinion_subject(
    user_input,
    media_title=None,
):
    """
    Return a stable opinion subject for common recurring media debates.

    v1 intentionally focuses on categories where continuity matters
    immediately: rankings, favourite characters, and overall stance.
    """

    text = _normalise(
        user_input
    )

    generic_category_ranking = (
        _classify_generic_category_ranking(
            text
        )
    )

    if generic_category_ranking:
        return generic_category_ranking

    title = (
        str(
            media_title
        ).strip()
        if media_title
        else None
    )

    if not title:
        return None

    for pattern in TOP_RANKING_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            count = int(
                match.group(
                    1
                )
            )

            return {
                "key": (
                    _normalise_key(
                        title
                    )
                    + f"::top_{count}_characters"
                ),
                "title": title,
                "kind": "character_ranking",
                "count": count,
                "label": (
                    f"{title} top {count} characters"
                ),
            }

    if _matches_any(
        text,
        GENERAL_CHARACTER_PATTERNS,
    ):
        return {
            "key": (
                _normalise_key(
                    title
                )
                + "::favourite_characters"
            ),
            "title": title,
            "kind": "character_preference",
            "count": None,
            "label": (
                f"{title} favourite characters"
            ),
        }

    if _matches_any(
        text,
        OVERALL_OPINION_PATTERNS,
    ):
        return {
            "key": (
                _normalise_key(
                    title
                )
                + "::overall_opinion"
            ),
            "title": title,
            "kind": "overall_opinion",
            "count": None,
            "label": (
                f"{title} overall opinion"
            ),
        }

    return None


# --------------------------------------------------
# Storage
# --------------------------------------------------

def _default_state():
    return {
        "version": 1,
        "opinions": {},
    }


def _ensure_private_dir():
    PRIVATE_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def _load_state():
    _ensure_private_dir()

    if not OPINION_LEDGER_PATH.exists():
        return _default_state()

    try:
        with OPINION_LEDGER_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:
            state = json.load(
                handle
            )
    except Exception:
        return _default_state()

    if not isinstance(
        state,
        dict,
    ):
        return _default_state()

    state.setdefault(
        "version",
        1,
    )

    state.setdefault(
        "opinions",
        {},
    )

    return state


def _save_state(
    state,
):
    _ensure_private_dir()

    temp_path = OPINION_LEDGER_PATH.with_suffix(
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
        OPINION_LEDGER_PATH,
    )


def get_opinion_entry(
    subject,
):
    if not subject:
        return None

    state = _load_state()

    entry = state[
        "opinions"
    ].get(
        subject[
            "key"
        ]
    )

    if not entry:
        return None

    return dict(
        entry
    )


# --------------------------------------------------
# Journal recovery
# --------------------------------------------------

def _looks_like_matching_historical_prompt(
    text,
    subject,
):
    value = _normalise(
        text
    )

    kind = subject.get(
        "kind"
    )

    if kind == "category_ranking":
        recovered_subject = (
            _classify_generic_category_ranking(
                value
            )
        )

        return bool(
            recovered_subject
            and recovered_subject.get(
                "key"
            )
            == subject.get(
                "key"
            )
        )

    if kind == "character_ranking":
        count = subject.get(
            "count"
        )

        return bool(
            re.search(
                rf"\btop\s+{count}\b",
                value,
            )
            and re.search(
                r"\bcharacters?\b",
                value,
            )
        )

    if kind == "character_preference":
        return bool(
            re.search(
                r"\b(?:favourite|favorite|best)\b",
                value,
            )
            and re.search(
                r"\bcharacters?\b",
                value,
            )
        )

    if kind == "overall_opinion":
        return bool(
            re.search(
                r"\bwhat do you think\b|\bopinion\b",
                value,
            )
        )

    return False


def recover_opinion_from_journal(
    user_input,
    subject,
):
    """
    Recover Mairon's latest matching historical stance from the private
    conversation journal.

    This is deliberately stronger than generic Context Manager retrieval:
    the recovered assistant response becomes explicit persona state.
    """

    if not subject:
        return None

    turns = search_relevant_turns(
        user_input=user_input,
        limit=6,
    )

    candidates = [
        turn
        for turn in turns
        if _looks_like_matching_historical_prompt(
            turn.get(
                "user_text",
                "",
            ),
            subject,
        )
    ]

    if not candidates:
        return None

    def authority_score(
        turn,
    ):
        user_text = _normalise(
            turn.get(
                "user_text",
                "",
            )
        )

        assistant_text = _normalise(
            turn.get(
                "assistant_text",
                "",
            )
        )

        score = 0

        # Explicitly settled opinions outrank later accidental model drift.
        settled_phrases = [
            "final official",
            "official top",
            "final top",
            "settled top",
            "lock in",
            "locked in",
        ]

        if any(
            phrase in user_text
            for phrase in settled_phrases
        ):
            score += 1000

        if any(
            phrase in assistant_text
            for phrase in settled_phrases
        ):
            score += 500

        # Recency still breaks ties between equally authoritative entries.
        score += int(
            turn.get(
                "id",
                0,
            )
        )

        return score

    candidates.sort(
        key=authority_score,
        reverse=True,
    )

    selected = candidates[
        0
    ]

    assistant_text = str(
        selected.get(
            "assistant_text",
            "",
        )
    ).strip()

    if not assistant_text:
        return None

    now = _now().isoformat()

    entry = {
        "subject_key": subject[
            "key"
        ],
        "label": subject[
            "label"
        ],
        "title": subject[
            "title"
        ],
        "domain": subject.get(
            "domain"
        ),
        "kind": subject[
            "kind"
        ],
        "count": subject.get(
            "count"
        ),
        "stance_text": assistant_text,
        "created_at": now,
        "last_updated": now,
        "source": "conversation_journal_recovery",
        "source_turn_id": selected.get(
            "id"
        ),
        "confidence": "established_previous_stance",
    }

    state = _load_state()

    state[
        "opinions"
    ][
        subject[
            "key"
        ]
    ] = entry

    _save_state(
        state
    )

    return dict(
        entry
    )


def get_or_recover_opinion_entry(
    user_input,
    subject,
):
    entry = get_opinion_entry(
        subject
    )

    if entry:
        return entry

    return recover_opinion_from_journal(
        user_input=user_input,
        subject=subject,
    )


# --------------------------------------------------
# Prompt context
# --------------------------------------------------

def build_opinion_context_text(
    entry,
):
    if not entry:
        return None

    return (
        "CORE MAIRON OPINION LEDGER:\n"
        f"Subject: {entry.get('label')}\n"
        f"Status: {entry.get('confidence')}\n\n"
        "Mairon's established previous stance is reproduced below:\n"
        "-----\n"
        f"{entry.get('stance_text', '')}\n"
        "-----\n\n"
        "This is PERSONA STATE, not objective truth. Preserve the underlying "
        "subjective stance/selection unless the current conversation gives "
        "Mairon an actual reason to revise it. Do not silently swap "
        "characters/items simply because the question was asked again. "
        "IMPORTANT: factual/canon claims inside the historical wording are "
        "NOT authoritative and must be independently verified before reuse. "
        "Preserve the preference, not old misinformation. If Mairon changes "
        "its mind, the change must be explicit and reasoned."
    )


# --------------------------------------------------
# Recording / revision
# --------------------------------------------------

def _revision_is_explicit(
    user_input,
    response_text,
):
    return bool(
        _matches_any(
            _normalise(
                user_input
            ),
            EXPLICIT_REVISION_REQUESTS,
        )
        or _matches_any(
            _normalise(
                response_text
            ),
            REVISION_LANGUAGE,
        )
    )


def record_opinion_if_needed(
    subject,
    response_text,
    existing_entry=None,
    user_input="",
    research_used=False,
):
    """
    Store a new stance, or update an established stance only when the
    response/current turn explicitly indicates a revision.

    This prevents random model drift from silently rewriting Mairon's
    personality every time Oliver asks the same ranking again.
    """

    if not subject:
        return None

    response_value = str(
        response_text or ""
    ).strip()

    if not response_value:
        return None

    if (
        existing_entry
        and not _revision_is_explicit(
            user_input=user_input,
            response_text=response_value,
        )
    ):
        return dict(
            existing_entry
        )

    now = _now().isoformat()

    previous_created = (
        existing_entry.get(
            "created_at"
        )
        if existing_entry
        else now
    )

    entry = {
        "subject_key": subject[
            "key"
        ],
        "label": subject[
            "label"
        ],
        "title": subject[
            "title"
        ],
        "domain": subject.get(
            "domain"
        ),
        "kind": subject[
            "kind"
        ],
        "count": subject.get(
            "count"
        ),
        "stance_text": response_value,
        "created_at": previous_created,
        "last_updated": now,
        "source": (
            "researched_conversation"
            if research_used
            else "conversation"
        ),
        "source_turn_id": None,
        "confidence": (
            "informed"
            if research_used
            else "provisional"
        ),
    }

    state = _load_state()

    state[
        "opinions"
    ][
        subject[
            "key"
        ]
    ] = entry

    _save_state(
        state
    )

    return dict(
        entry
    )


def get_opinion_ledger_path():
    return str(
        OPINION_LEDGER_PATH
    )
