import json
import os
import random
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

PRIVATE_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "private"
)

SOCIAL_CONTEXT_PATH = (
    PRIVATE_DATA_DIR
    / "social_context.json"
)

MAIRON_TIMEZONE = os.getenv(
    "MAIRON_TIMEZONE",
    "Australia/Sydney"
)

LOCAL_TIMEZONE = ZoneInfo(
    MAIRON_TIMEZONE
)

MAX_RECENT_EVENTS = 80
MAX_RESPONSE_HISTORY = 80

_rng = random.SystemRandom()


# --------------------------------------------------
# Temporary social-event policy
# --------------------------------------------------

EVENT_POLICY = {
    "user_insulted_mairon": {
        "theme_id": "reciprocal_insult",
        "summary": (
            "Oliver recently insulted or mock-abused Mairon "
            "in an apparently playful conversational context."
        ),
        "expiry_hours": 6,
        "theme_cooldown_hours": 4,
        "callback_probability": 0.50,
    },
    "delete_or_unplug_threat": {
        "theme_id": "delete_threat",
        "summary": (
            "Oliver recently threatened to delete, unplug, "
            "wipe, shut down, or otherwise terminate Mairon "
            "as relationship banter."
        ),
        "expiry_hours": 72,
        "theme_cooldown_hours": 48,
        "callback_probability": 0.35,
    },
    "mairon_development": {
        "theme_id": "being_built",
        "summary": (
            "Oliver recently discussed actively programming, "
            "building, testing, fixing, or tuning Mairon."
        ),
        "expiry_hours": 12,
        "theme_cooldown_hours": 6,
        "callback_probability": 0.20,
    },
    "user_thanked_mairon": {
        "theme_id": "reluctant_helpfulness",
        "summary": (
            "Oliver recently thanked or positively acknowledged "
            "Mairon after Mairon was useful."
        ),
        "expiry_hours": 4,
        "theme_cooldown_hours": 8,
        "callback_probability": 0.15,
    },
    "user_praised_mairon": {
        "theme_id": "smug_competence",
        "summary": (
            "Oliver recently praised Mairon's competence or "
            "said that something Mairon did worked well."
        ),
        "expiry_hours": 8,
        "theme_cooldown_hours": 12,
        "callback_probability": 0.18,
    },
}


# These are social-signal detectors, not canned jokes.
# Core stores the underlying event/theme; Qwen writes fresh wording.
EVENT_PATTERNS = {
    "delete_or_unplug_threat": [
        r"\bdelete you\b",
        r"\bunplug you\b",
        r"\bwipe you\b",
        r"\buninstall you\b",
        r"\bturn you off\b",
        r"\bshut you down\b",
        r"\bkill you\b",
        r"\bdelete mairon\b",
        r"\bunplug mairon\b",
    ],
    "user_insulted_mairon": [
        r"\bfuck off\b",
        r"\bfuck you\b",
        r"\byou(?:'re| are) (?:fucking )?useless\b",
        r"\buseless bastard\b",
        r"\bdumbass\b",
        r"\bdumb cunt\b",
        r"\byou idiot\b",
        r"\bstupid ai\b",
        r"\bstupid bastard\b",
        r"\byou(?:'re| are) shit\b",
    ],
    "mairon_development": [
        r"\bprogramming you\b",
        r"\bcoding you\b",
        r"\bbuilding you\b",
        r"\bdeveloping you\b",
        r"\btesting you\b",
        r"\btuning you\b",
        r"\bfixing you\b",
        r"\bworking on you\b",
        r"\bbuilding mairon\b",
        r"\bprogramming mairon\b",
        r"\btesting mairon\b",
        r"\btuning mairon\b",
        r"\bfixing mairon\b",
        r"\byour personality\b",
        r"\byour voice\b",
    ],
    "user_thanked_mairon": [
        r"^\s*thanks(?:\s+mairon)?[.!]*\s*$",
        r"^\s*thank you(?:\s+mairon)?[.!]*\s*$",
        r"^\s*cheers(?:\s+mairon)?[.!]*\s*$",
        r"\bthanks for that\b",
        r"\bthank you for that\b",
    ],
    "user_praised_mairon": [
        r"\bgood job\b",
        r"\bnice one\b",
        r"\byou cooked\b",
        r"\bthat worked\b",
        r"\bworks perfectly\b",
        r"\bthat(?:'s| is) perfect\b",
        r"\byou(?:'re| are) useful\b",
        r"\bgetting better\b",
    ],
}


SERIOUSNESS_PATTERNS = [
    r"\bemergency\b",
    r"\burgent\b",
    r"\bimmediately\b",
    r"\bhacked\b",
    r"\bcompromised\b",
    r"\bunauthori[sz]ed\b",
    r"\bfraud\b",
    r"\bscam\b",
    r"\bstolen\b",
    r"\baccount takeover\b",
    r"\bsecurity incident\b",
    r"\bdata breach\b",
    r"\bhospital\b",
    r"\binjured\b",
    r"\bserious injury\b",
    r"\bmedical emergency\b",
    r"\bdeadline is today\b",
    r"\bdue today\b",
    r"\bdue tonight\b",
    r"\bexam (?:is )?today\b",
    r"\bexam (?:is )?tomorrow\b",
    r"\bfinancial emergency\b",
]


# --------------------------------------------------
# State helpers
# --------------------------------------------------

def _now():
    return datetime.now(
        LOCAL_TIMEZONE
    )


def _default_state():
    return {
        "version": 1,
        "recent_events": [],
        "theme_usage": {},
        "response_history": [],
    }


def _ensure_private_dir():
    PRIVATE_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def _load_state():
    _ensure_private_dir()

    if not SOCIAL_CONTEXT_PATH.exists():
        return _default_state()

    try:
        with SOCIAL_CONTEXT_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:
            state = json.load(
                handle
            )
    except Exception:
        # Relationship-state corruption must never stop Mairon starting.
        return _default_state()

    if not isinstance(
        state,
        dict,
    ):
        return _default_state()

    default = _default_state()

    for key, value in default.items():
        if key not in state:
            state[key] = value

    return state


def _save_state(state):
    _ensure_private_dir()

    temp_path = SOCIAL_CONTEXT_PATH.with_suffix(
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
        SOCIAL_CONTEXT_PATH,
    )


def _parse_timestamp(value):
    try:
        return datetime.fromisoformat(
            value
        )
    except Exception:
        return None


def _normalise_text(text):
    value = str(
        text or ""
    ).lower()

    value = re.sub(
        r"https?://\S+",
        " ",
        value,
    )

    value = re.sub(
        r"[^a-z0-9'\s]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def _excerpt(
    text,
    max_chars=180,
):
    value = re.sub(
        r"\s+",
        " ",
        str(text or "").strip(),
    )

    if len(value) <= max_chars:
        return value

    return (
        value[:max_chars - 1]
        + "…"
    )


def _prune_state(
    state,
    now=None,
):
    if now is None:
        now = _now()

    kept_events = []

    for event in state.get(
        "recent_events",
        [],
    ):
        expires_at = _parse_timestamp(
            event.get(
                "expires_at"
            )
        )

        if (
            expires_at is None
            or expires_at >= now
        ):
            kept_events.append(
                event
            )

    state[
        "recent_events"
    ] = kept_events[
        -MAX_RECENT_EVENTS:
    ]

    state[
        "response_history"
    ] = state.get(
        "response_history",
        [],
    )[
        -MAX_RESPONSE_HISTORY:
    ]

    return state


# --------------------------------------------------
# Social event detection
# --------------------------------------------------

def detect_social_events(
    user_input,
):
    text = _normalise_text(
        user_input
    )

    detected = []

    for event_type, patterns in EVENT_PATTERNS.items():
        if any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        ):
            detected.append(
                event_type
            )

    return detected


def register_user_social_events(
    user_input,
):
    """
    Store compact, local, temporary social facts that may create a
    future banter opportunity.

    We store events, not punchlines.
    """

    state = _prune_state(
        _load_state()
    )

    now = _now()

    event_types = detect_social_events(
        user_input
    )

    created = []

    for event_type in event_types:
        policy = EVENT_POLICY[
            event_type
        ]

        event = {
            "event_id": uuid4().hex,
            "event_type": event_type,
            "theme_id": policy[
                "theme_id"
            ],
            "summary": policy[
                "summary"
            ],
            "source_excerpt": _excerpt(
                user_input
            ),
            "created_at": now.isoformat(),
            "expires_at": (
                now
                + timedelta(
                    hours=policy[
                        "expiry_hours"
                    ]
                )
            ).isoformat(),
            "usage_count": 0,
        }

        state[
            "recent_events"
        ].append(
            event
        )

        created.append(
            event
        )

    _save_state(
        _prune_state(
            state,
            now=now,
        )
    )

    return created


# --------------------------------------------------
# Seriousness gate
# --------------------------------------------------

def is_serious_turn(
    user_input,
):
    text = _normalise_text(
        user_input
    )

    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in SERIOUSNESS_PATTERNS
    )


# --------------------------------------------------
# Banter candidate selection
# --------------------------------------------------

def _theme_is_on_cooldown(
    state,
    theme_id,
    cooldown_hours,
    now,
):
    usage = state.get(
        "theme_usage",
        {}
    ).get(
        theme_id
    )

    if not usage:
        return False

    last_used = _parse_timestamp(
        usage.get(
            "last_used"
        )
    )

    if last_used is None:
        return False

    return (
        now
        - last_used
        < timedelta(
            hours=cooldown_hours
        )
    )


def _event_is_eligible(
    state,
    event,
    excluded_event_ids,
    now,
):
    if event.get(
        "event_id"
    ) in excluded_event_ids:
        return False

    event_type = event.get(
        "event_type"
    )

    policy = EVENT_POLICY.get(
        event_type
    )

    if not policy:
        return False

    if event.get(
        "usage_count",
        0
    ) >= 1:
        # A specific temporary source event normally becomes ammunition
        # once. A future REAL event can revive the general theme.
        return False

    if _theme_is_on_cooldown(
        state=state,
        theme_id=policy[
            "theme_id"
        ],
        cooldown_hours=policy[
            "theme_cooldown_hours"
        ],
        now=now,
    ):
        return False

    return True


def select_callback_candidate(
    excluded_event_ids=None,
):
    """
    Select at most one historical callback candidate.

    There is deliberately no sequential joke rotation. A small pool of
    fresh, valid events competes randomly, then the probability gate may
    still choose silence.
    """

    if excluded_event_ids is None:
        excluded_event_ids = set()

    excluded_event_ids = set(
        excluded_event_ids
    )

    state = _prune_state(
        _load_state()
    )

    now = _now()

    eligible = [
        event
        for event in state.get(
            "recent_events",
            []
        )
        if _event_is_eligible(
            state=state,
            event=event,
            excluded_event_ids=excluded_event_ids,
            now=now,
        )
    ]

    if not eligible:
        _save_state(
            state
        )
        return None

    eligible.sort(
        key=lambda event: event.get(
            "created_at",
            "",
        ),
        reverse=True,
    )

    # Only recent relevant ammunition competes; this avoids ancient
    # events bubbling up simply because everything newer is unavailable.
    pool = eligible[:5]

    candidate = _rng.choice(
        pool
    )

    policy = EVENT_POLICY[
        candidate[
            "event_type"
        ]
    ]

    # Even valid ammunition usually remains unused.
    if (
        _rng.random()
        > policy[
            "callback_probability"
        ]
    ):
        _save_state(
            state
        )
        return None

    _save_state(
        state
    )

    return candidate


# --------------------------------------------------
# Relationship turn context
# --------------------------------------------------

def prepare_relationship_turn(
    user_input,
):
    """
    Register current social signals and expose at most one older,
    grounded callback candidate.

    The current user message is excluded from the historical callback
    pool because Qwen already sees it directly.
    """

    new_events = register_user_social_events(
        user_input
    )

    excluded_ids = {
        event[
            "event_id"
        ]
        for event in new_events
    }

    serious = is_serious_turn(
        user_input
    )

    callback_candidate = None

    if not serious:
        callback_candidate = select_callback_candidate(
            excluded_event_ids=excluded_ids
        )

    return {
        "serious": serious,
        "new_events": new_events,
        "callback_candidate": callback_candidate,
    }


def build_relationship_context_text(
    relationship_context,
):
    serious = bool(
        relationship_context.get(
            "serious"
        )
    )

    candidate = relationship_context.get(
        "callback_candidate"
    )

    lines = [
        "CORE RELATIONSHIP POLICY:",
    ]

    if serious:
        lines.extend([
            "- Seriousness gate: ACTIVE.",
            "- Keep banter minimal or absent. Accuracy and usefulness come first.",
            "- Do not use a historical callback on this turn.",
        ])

        return "\n".join(
            lines
        )

    lines.extend([
        "- Seriousness gate: casual.",
        "- Personality may be present, but a joke is not required.",
        "- Fresh banter may use facts in Oliver's current message or genuinely visible conversation history.",
    ])

    if candidate is None:
        lines.extend([
            "- Historical callback candidate supplied by Core: NONE.",
            "- Do not manufacture a previous event merely to sound familiar.",
            "- If the visible conversation itself does not establish a prior event, do not imply one happened.",
        ])

        return "\n".join(
            lines
        )

    lines.extend([
        "- Historical callback candidate supplied by Core: AVAILABLE.",
        "- You MAY use it, but you do not have to.",
        "- Use at most one historical callback.",
        "- Generate completely fresh wording. The following is context/ammunition, NOT a line to quote:",
        f"  event_type: {candidate.get('event_type')}",
        f"  theme: {candidate.get('theme_id')}",
        f"  grounded_summary: {candidate.get('summary')}",
        f"  Oliver actually said: {candidate.get('source_excerpt')!r}",
    ])

    return "\n".join(
        lines
    )


# --------------------------------------------------
# Novelty / repetition detection
# --------------------------------------------------

def _token_set(
    text,
):
    return {
        token
        for token in _normalise_text(
            text
        ).split()
        if len(token) > 2
    }


def _jaccard_similarity(
    left,
    right,
):
    left_tokens = _token_set(
        left
    )

    right_tokens = _token_set(
        right
    )

    if (
        not left_tokens
        or not right_tokens
    ):
        return 0.0

    intersection = len(
        left_tokens
        & right_tokens
    )

    union = len(
        left_tokens
        | right_tokens
    )

    if union == 0:
        return 0.0

    return (
        intersection
        / union
    )


def _sentence_candidates(
    text,
):
    parts = re.split(
        r"(?<=[.!?])\s+",
        str(text or "").strip(),
    )

    return [
        part.strip()
        for part in parts
        if len(
            _normalise_text(
                part
            )
        ) >= 24
    ]


def _get_conversation_assistant_texts(
    conversation,
):
    texts = []

    if not conversation:
        return texts

    for message in conversation[
        -24:
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
            role == "assistant"
            and content
        ):
            texts.append(
                content
            )

    return texts


def find_repetition_violations(
    response_text,
    conversation=None,
    allow_stable_repeat=False,
):
    """
    Conservative repetition guard.

    It catches obvious reused punchlines/catchphrases and near-copy
    responses, but does not demand novelty for every factual phrase.
    """

    # Established Core-owned persona state (for example Mairon's stored top-3
    # manga ranking) is allowed to repeat. Consistency is the desired behavior
    # in that lane; the generic novelty guard must not fight the opinion ledger.
    if allow_stable_repeat:
        return []

    candidate = str(
        response_text or ""
    ).strip()

    candidate_norm = _normalise_text(
        candidate
    )

    if not candidate_norm:
        return []

    state = _prune_state(
        _load_state()
    )

    comparison_texts = [
        item.get(
            "text",
            ""
        )
        for item in state.get(
            "response_history",
            []
        )[
            -50:
        ]
        if item.get(
            "text"
        )
    ]

    comparison_texts.extend(
        _get_conversation_assistant_texts(
            conversation
        )
    )

    unique_comparisons = []

    seen = set()

    for previous in comparison_texts:
        previous_norm = _normalise_text(
            previous
        )

        if (
            not previous_norm
            or previous_norm in seen
        ):
            continue

        seen.add(
            previous_norm
        )

        unique_comparisons.append(
            previous
        )

    candidate_sentences = _sentence_candidates(
        candidate
    )

    for previous in unique_comparisons[
        -60:
    ]:
        previous_norm = _normalise_text(
            previous
        )

        if not previous_norm:
            continue

        # Exact small catchphrases are worth catching too.
        if (
            candidate_norm == previous_norm
            and len(
                candidate_norm
            ) >= 8
        ):
            return [
                "reused an earlier response/catchphrase verbatim"
            ]

        if (
            len(candidate_norm) >= 35
            and len(previous_norm) >= 35
        ):
            sequence_ratio = SequenceMatcher(
                None,
                candidate_norm,
                previous_norm,
            ).ratio()

            if sequence_ratio >= 0.84:
                return [
                    "response wording is too similar to a recent response"
                ]

            if _jaccard_similarity(
                candidate,
                previous,
            ) >= 0.78:
                return [
                    "response reuses too much recent wording"
                ]

        # Sentence-level similarity used to be rejected globally here.
        # That created false positives whenever Oliver revisited the same
        # topic or repeated a real-world test: perfectly normal factual or
        # conversational sentences were treated as reused punchlines.
        #
        # Core still rejects:
        # - exact repeated responses;
        # - strongly near-duplicate complete responses;
        # - high whole-response token overlap.
        #
        # Semantic banter-premise repetition will be handled separately by
        # a dedicated premise tracker rather than guessing that every
        # similar sentence is a joke.

    return []


# --------------------------------------------------
# Accepted response / cooldown recording
# --------------------------------------------------

def record_accepted_relationship_response(
    response_text,
    relationship_context,
):
    """
    Record recent wording for novelty checks.

    If Core made a historical callback candidate available, conservatively
    count that theme as used even if Qwen chose not to use it. This biases
    Mairon toward LESS repetitive banter, which is the safer failure mode.
    """

    state = _prune_state(
        _load_state()
    )

    now = _now()

    candidate = relationship_context.get(
        "callback_candidate"
    )

    selected_theme_id = None

    if candidate is not None:
        selected_theme_id = candidate.get(
            "theme_id"
        )

        event_id = candidate.get(
            "event_id"
        )

        for event in state.get(
            "recent_events",
            []
        ):
            if event.get(
                "event_id"
            ) == event_id:
                event[
                    "usage_count"
                ] = (
                    int(
                        event.get(
                            "usage_count",
                            0,
                        )
                    )
                    + 1
                )

                break

        if selected_theme_id:
            usage = state.setdefault(
                "theme_usage",
                {}
            ).setdefault(
                selected_theme_id,
                {
                    "usage_count": 0,
                    "last_used": None,
                }
            )

            usage[
                "usage_count"
            ] = (
                int(
                    usage.get(
                        "usage_count",
                        0,
                    )
                )
                + 1
            )

            usage[
                "last_used"
            ] = now.isoformat()

    state[
        "response_history"
    ].append({
        "timestamp": now.isoformat(),
        "text": _excerpt(
            response_text,
            max_chars=700,
        ),
        "theme_id": selected_theme_id,
    })

    _save_state(
        _prune_state(
            state,
            now=now,
        )
    )


def get_social_state_path():
    return str(
        SOCIAL_CONTEXT_PATH
    )
